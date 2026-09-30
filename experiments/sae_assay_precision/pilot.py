"""Fixed 12-text precision-transport diagnostic, never assay qualification.

The caller owns authorization, the frozen whole plan, backend construction and
closure. This module never loads production weights, generates text, or calls a
service. Each text gets four uncached transformer forwards, without retries.
The promoted-weight FP32 SAE is a NEW readout, not the native BF16 authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time

import numpy as np
import torch
import torch.nn.functional as F

from experiments.sae_assay_diagnostic.backend import _canonical_encode, _fp32_math
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.protocol import canonical, sha
from experiments.sae_assay_diagnostic.runner import write_once
from experiments.sae_assay_repair.feasibility import active_support_projection

SCHEMA = "sae_precision_pilot_v1"
DIRECTORY = "precision_pilot"
MODES = ("native_zero", "precision_sham", "suppression", "amplification")
AUTHORITY = "full_promoted_bf16_fp32_token1_v1"
SCOPE = "Engineering components only; not overall assay qualification"
CAPTURE_KEYS = {
    "pre", "requested", "post", "token_ids", "valid", "native_before",
    "promoted_before", "promoted_after", "promoted_preact_before",
    "projection_coefficients", "projection_scale", "native_rounded_after",
}


def _hash(value):
    return hashlib.sha256((canonical(value) + "\n").encode()).hexdigest()


def pilot_texts(plan):
    """Selection is frozen order, never exposure or outcome dependent."""
    first, families, identifiers = [], set(), set()
    for item in plan["texts"]:
        if item["id"] in identifiers or not re.fullmatch(r"[\w-]+", item["id"]):
            raise ValueError("Duplicate or unsafe text ID")
        identifiers.add(item["id"])
        if item["split"] == "discovery" and item["family"] not in families:
            first.append(item)
            families.add(item["family"])
    config = plan["precision_pilot"]
    if len(first) != 12 or config["texts"] != first:
        raise ValueError("Pilot must contain exactly the first discovery text per 12 families")
    expected = {"modes": list(MODES), "change": .75, "norm_cap": .04,
                "layer_index": 50,
                "fidelity": {"minimum_fraction": .95, "minimum_cosine": .95,
                             "maximum_relative_error": .20},
                "norm": {"minimum_fraction": .95, "maximum_clean_ratio": .05}}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Frozen pilot constants changed; no tuning is allowed")
    ids = plan["target_feature_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 6 or len(set(ids)) != len(ids)
            or any(type(i) is not int or i < 0 for i in ids)):
        raise ValueError("Invalid target IDs")
    return first


def _inventory(plan):
    items = plan["certificate"]["items"]
    inventory = {item["id"]: item for item in items}
    if len(inventory) != len(items):
        raise ValueError("Duplicate certified token inventory")
    for item in pilot_texts(plan):
        entry = inventory[item["id"]]
        tokens, mask = entry["token_ids"], entry["special_tokens_mask"]
        if (entry["text_sha256"] != hashlib.sha256(item["text"].encode()).hexdigest()
                or not 2 <= len(tokens) <= 256 or len(tokens) != len(mask)
                or any(type(t) is not int or t < 0 for t in tokens)
                or any(type(m) is not bool for m in mask) or all(mask)):
            raise ValueError("Invalid certified pilot text/token inventory")
    return inventory


def _row_id(item, mode):
    return "precision-pilot:" + item["id"] + ":" + mode


def _deadline(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Deadline must be timezone aware")
        value = value.timestamp()
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Deadline must be an absolute finite timestamp")
    return value


def _check_deadline(deadline):
    if time.time() >= deadline:
        raise TimeoutError("Precision pilot deadline reached; no further forward authorized")


def validate_model_math(device):
    """Cold preflight, callable before loading any model or allocating CUDA."""
    if torch.is_autocast_enabled(torch.device(device).type):
        raise ValueError("Pilot requires autocast disabled; native zero must not change math settings")
    precision = torch.get_float32_matmul_precision()
    # The shared backend context restores a boolean, which maps medium to high.
    if precision == "medium":
        raise ValueError("Shared math helper cannot preserve medium matmul precision; no silent change allowed")
    return {"allow_tf32": torch.backends.cuda.matmul.allow_tf32,
            "autocast_enabled": False, "float32_matmul_precision": precision}


def _exposure_reference(out, item, plan_hash, freeze, ids, token_ids):
    """Reuse exact existing clean evidence, not newly selected exposure."""
    from safetensors.torch import load_file
    row_path = Path(out) / "rows" / ("clean-" + item["id"] + ".json")
    row = json.loads(row_path.read_text())
    if (row["plan_sha256"] != plan_hash or row["freeze_commit"] != freeze
            or row["text_id"] != item["id"] or row["feature_ids"] != ids or row["token_ids"] != token_ids
            or row["capture"]["path"] != "residuals/" + item["id"] + ".safetensors"):
        raise ValueError("Clean exposure baseline binding mismatch")
    path = Path(out) / row["capture"]["path"]
    if sha(path) != row["capture"]["sha256"]:
        raise ValueError("Clean exposure capture hash mismatch")
    tensors = load_file(str(path))
    if (set(tensors) != {"hidden", "token_ids"} or tensors["hidden"].dtype != torch.bfloat16
            or tensors["token_ids"].tolist() != [row["token_ids"]]):
        raise ValueError("Invalid clean exposure capture")
    native = np.asarray([row["activations"][str(i)] for i in ids]).T.tolist()
    return tensors["hidden"], native, {"row_path": "rows/" + row_path.name,
        "row_sha256": sha(row_path), "capture_path": row["capture"]["path"],
        "capture_sha256": row["capture"]["sha256"]}


def _metrics(pre, requested, post):
    """FP64 CPU oracle on retained actual tensors, including cancellation."""
    h, r, p = (v.detach().cpu().double().reshape(-1, v.shape[-1])
               for v in (pre, requested, post))
    actual = p - h
    rn, an, hn = (torch.linalg.vector_norm(v, dim=-1) for v in (r, actual, h))
    nz = rn > 0
    tiny = torch.finfo(torch.float64).tiny
    cosine = (r * actual).sum(-1) / (rn * an).clamp_min(tiny)
    error = torch.linalg.vector_norm(actual - r, dim=-1)
    return {"requested_norm": rn.tolist(), "realized_norm": an.tolist(),
            "clean_norm": hn.tolist(), "nonzero_requested": nz.tolist(),
            "identity": (p == h).all(-1).tolist(),
            "cosine": torch.where(nz, cosine.clamp(-1, 1), 1.).tolist(),
            "relative_error": torch.where(nz, error / rn.clamp_min(tiny), 0.).tolist(),
            "realized_clean_ratio": (an / hn.clamp_min(tiny)).tolist()}


def _readout(hidden, encoder, bias, index):
    # A fixed FULL-width token-one GEMM precedes selection; never selected GEMMs.
    selected = []
    with _fp32_math(hidden.device):
        for position in hidden.reshape(-1, hidden.shape[-1]):
            full = F.linear(position[None], encoder, bias)
            if not bool(torch.isfinite(full).all()):
                raise FloatingPointError("Nonfinite full-width SAE readout")
            selected.append(full.index_select(1, index))
    preact = torch.cat(selected)
    return preact, F.relu(preact)


def _requests(pre, native, promoted_preact, selected_encoder, valid):
    e64 = selected_encoder.cpu().double().numpy()
    gram = e64 @ e64.T
    clean_norm = torch.linalg.vector_norm(pre.float(), dim=-1).reshape(-1)
    result = {}
    for mode in MODES[2:]:
        projection = active_support_projection(
            gram, promoted_preact.cpu().double().numpy(), native.cpu().double().numpy(),
            clean_norm.cpu().double().numpy(), mode=mode, change=.75, norm_cap=.04)
        coeff = torch.as_tensor(projection["coefficients"], device=pre.device, dtype=torch.float32)
        coeff = torch.where(valid.reshape(-1, 1), coeff, 0.)
        with _fp32_math(pre.device):
            request = torch.cat([F.linear(row[None], selected_encoder.T) for row in coeff])
        result[mode] = (request.reshape_as(pre), coeff,
                        torch.as_tensor(projection["scale"], device=pre.device, dtype=torch.float32),
                        {"uncapped_norm": projection["uncapped_norm"].tolist(),
                         "continuous_capped_norm": projection["norm"].tolist(),
                         "continuous_predicted_activation": projection["predicted_activation"].tolist()})
    return result, gram.tolist()


def _save_tensors(path, tensors):
    from safetensors.torch import save
    # Exclusive creation, including against an interrupted prior write.
    with path.open("xb") as stream:
        stream.write(save({key: value.detach().cpu().contiguous().clone()
                           for key, value in tensors.items()}, metadata={"schema": SCHEMA}))
        stream.flush()
        import os
        os.fsync(stream.fileno())
    return {"path": "tensors/" + path.name, "sha256": sha(path),
            "tensors": {key: {"shape": list(value.shape), "dtype": str(value.dtype)}
                        for key, value in tensors.items()}}


@torch.inference_mode()
def run_pilot(backend, plan, plan_hash, freeze, out, deadline):
    """Write a new non-resumable subdirectory and return its offline summary.

    A failed run is preserved. Retrying it under the same directory is forbidden;
    the parent must explicitly authorize and freeze any new run. Deadline checks
    precede every forward and SAE readout, but do not interrupt an active kernel.
    """
    from .bridge import precision_bridge, qualify_bridge

    texts, inventory = pilot_texts(plan), _inventory(plan)
    deadline = _deadline(deadline)
    if not time.time() < deadline <= time.time() + 7200:
        raise ValueError("Deadline must be future and within the parent's two-hour ceiling")
    if plan_hash != _hash(plan) or not re.fullmatch("[0-9a-f]{40}", freeze):
        raise ValueError("Invalid whole-plan hash or freeze binding")
    test_only = backend.metadata.get("test_only", False)
    if (backend.dtype != torch.bfloat16 or backend.model.training
            or (not test_only and (backend.layer_index != 50 or backend.device.type != "cuda"))):
        raise ValueError("Pilot requires an eval-mode native BF16 backend; production is CUDA layer 50")
    model_math = validate_model_math(backend.device)
    ids = plan["target_feature_ids"]
    encoder, bias = backend._sae[:2]
    if (encoder.dtype != torch.bfloat16 or bias.dtype != torch.bfloat16
            or max(ids) >= len(encoder)):
        raise ValueError("Native BF16 SAE weights required")
    root = Path(out) / DIRECTORY
    root.mkdir(parents=True, exist_ok=False)
    (root / "rows").mkdir()
    (root / "tensors").mkdir()
    row_ids = [_row_id(item, mode) for item in texts for mode in MODES]
    ledger = EventLedger(root / "receipts.jsonl", plan_hash, freeze, row_ids)
    ledger.bind("runtime", {"kind": "runtime", "scope": SCOPE, "test_only": test_only,
                           "deadline_utc": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
                           "maximum_full_model_forwards": 48, "model_math": model_math})
    write_once(root / "binding.json", {"schema": SCHEMA, "plan_sha256": plan_hash,
                                      "freeze_commit": freeze, "text_ids": [x["id"] for x in texts]})
    completed = 0
    try:
        _check_deadline(deadline)
        qualification = qualify_bridge(backend.device)
        write_once(root / "qualification.json", qualification)
        ledger.bind("qualification", {"kind": "qualification", "sha256": sha(root / "qualification.json")})
        if qualification.get("pass") is not True:
            raise ValueError("Synthetic bridge qualification failed")
        promoted_e, promoted_b = encoder.float(), bias.float()
        index = torch.tensor(ids, device=encoder.device)
        selected_e = promoted_e.index_select(0, index)
        for item in texts:
            entry = inventory[item["id"]]
            exposure_h, exposure_z, exposure_receipt = _exposure_reference(
                out, item, plan_hash, freeze, ids, entry["token_ids"])
            tokens = backend._tokenize(item["text"])
            if (tokens[0].tolist() != entry["token_ids"] or
                    [x in backend.tokenizer.all_special_ids for x in entry["token_ids"]]
                    != entry["special_tokens_mask"]):
                raise ValueError("Runtime tokenization differs from frozen certificate")
            valid = torch.tensor([[not x for x in entry["special_tokens_mask"]]], device=tokens.device)
            clean, sham, native_h, native_z, before_p, before_z, requests = (None,) * 7
            for mode in MODES:
                _check_deadline(deadline)
                rid = _row_id(item, mode)
                ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid,
                                               "ordinal": completed, "full_model_forwards": 1})

                def request_callback(observed):
                    if not torch.equal(observed, native_h):
                        raise ValueError("Pre-edit state differs from frozen native clean baseline")
                    return requests[mode][0]

                with precision_bridge(backend, native_zero=mode == "native_zero",
                                      edit_callback=request_callback if mode in MODES[2:] else None) as bridge:
                    if (torch.backends.cuda.matmul.allow_tf32 != model_math["allow_tf32"]
                            or torch.get_float32_matmul_precision() != model_math["float32_matmul_precision"]
                            or torch.is_autocast_enabled(backend.device.type)):
                        raise ValueError("Model math settings changed before forward")
                    output = backend.model.model(input_ids=tokens, use_cache=False, return_dict=True)
                if len(bridge.records) != 1:
                    raise ValueError("Expected one bridge boundary firing per full forward")
                record = bridge.records[0]
                pre = record["clean_native"].to(backend.device)
                requested = record["requested_fp32"].to(backend.device)
                post = record["edited_state"].to(backend.device)
                final = output.last_hidden_state
                if final.dtype != torch.bfloat16:
                    raise ValueError("Final norm must deliver BF16 to the unchanged head")
                _check_deadline(deadline)
                if mode == "native_zero":
                    clean, native_h = final, pre
                    native_z = _canonical_encode(pre, encoder, bias, index).reshape(-1, len(ids)).float()
                    if not torch.equal(pre.cpu(), exposure_h) or native_z.cpu().tolist() != exposure_z:
                        raise ValueError("Pilot native baseline differs from prior clean exposure")
                    before_p, before_z = _readout(pre.float(), promoted_e, promoted_b, index)
                    requests, gram = _requests(pre, native_z, before_p, selected_e, valid)
                elif not torch.equal(pre, native_h):
                    raise ValueError("All arms must share the exact native pre-edit baseline")
                if mode == "precision_sham":
                    sham = final
                _, after_z = _readout(post.float(), promoted_e, promoted_b, index)
                rounded_z = _canonical_encode(post.to(torch.bfloat16), encoder, bias, index).reshape(-1, len(ids)).float()
                cn, en, kl_native = backend._losses(clean, final, tokens)
                if sham is not None:
                    sn, _, kl_sham = backend._losses(sham, final, tokens)
                else:
                    sn, kl_sham = None, None
                coeff = (requests[mode][1] if mode in MODES[2:] else torch.zeros_like(native_z))
                scale = (requests[mode][2] if mode in MODES[2:]
                         else torch.ones(len(native_z), device=pre.device))
                tensors = {"pre": pre, "requested": requested, "post": post,
                           "token_ids": tokens, "valid": valid, "native_before": native_z,
                           "promoted_before": before_z, "promoted_after": after_z,
                           "promoted_preact_before": before_p, "projection_coefficients": coeff,
                           "projection_scale": scale, "native_rounded_after": rounded_z}
                capture = _save_tensors(root / "tensors" / f"{completed:03d}.safetensors", tensors)
                row = {"schema": SCHEMA, "row_id": rid, "text_id": item["id"],
                       "family": item["family"], "split": "discovery", "mode": mode,
                       "plan_sha256": plan_hash, "freeze_commit": freeze,
                       "feature_ids": ids, "token_ids": entry["token_ids"],
                       "special_tokens_mask": entry["special_tokens_mask"],
                       "sae_authority": AUTHORITY, "sae_full_width": len(encoder),
                       "native_before": native_z.cpu().tolist(),
                       "promoted_before": before_z.cpu().tolist(), "promoted_after": after_z.cpu().tolist(),
                       "native_rounded_after": rounded_z.cpu().tolist(),
                       "precision_readout_shift": (before_z - native_z).cpu().tolist(),
                       "paired_promoted_edit_delta": (after_z - before_z).cpu().tolist(),
                       "delivery": _metrics(pre, requested, post),
                       "native_nll": cn, "nll": en, "kl_native_to_mode": kl_native,
                       "sham_nll": sn, "kl_sham_to_mode": kl_sham,
                       "loss_alignment": "index i predicts token_ids[i]; index 0 is null",
                       "returned_original_output": record["returned_original_output"],
                       "bridge": bridge.metadata, "boundary_trace": bridge.boundary_trace,
                       "test_only": test_only, "capture": capture, "clean_exposure": exposure_receipt,
                       "model_math": model_math, "sae_request_math": {"allow_tf32": False, "autocast_enabled": False}}
                row["projection"] = {"operator": "active_support_projection", "change": .75,
                    "norm_cap": .04, "gram": gram, "gram_dtype": "float64",
                    "coefficients_dtype": "float32", "support": "native_before > 0",
                    "baseline": "prior_clean_exposure_native_bf16", "rounding_adaptation": False,
                    "special_position_requests": "exact zero", "solver_before_special_mask":
                    requests[mode][3] if mode in MODES[2:] else None}
                path = root / "rows" / f"{completed:03d}.json"
                write_once(path, row)
                validate_row(row, plan, root)
                ledger.append_row(rid, {"path": "rows/" + path.name, "sha256": sha(path),
                                        "capture_sha256": capture["sha256"]})
                completed += 1
                del output, final
        ledger.assert_complete()
        result = summarize([json.loads(p.read_text()) for p in sorted((root / "rows").glob("*.json"))])
        write_once(root / "summary.json", result)
        ledger.bind("complete", {"kind": "complete", "full_model_forwards": completed,
                                 "summary_sha256": sha(root / "summary.json")})
        validate_run(out, plan, plan_hash, freeze)
        return result
    except BaseException as exc:
        failure = {"schema": SCHEMA, "completed_forward_records": completed,
                   "error_type": type(exc).__name__, "message": str(exc),
                   "retry_permitted": False}
        write_once(root / "failure.json", failure)
        ledger.bind("failure", {"kind": "failure", "sha256": sha(root / "failure.json")})
        raise


def validate_row(row, plan, root=None):
    """Offline structural check. Scientific failure is valid retained evidence."""
    texts = {item["id"]: item for item in pilot_texts(plan)}
    entry = _inventory(plan).get(row.get("text_id"))
    item, mode = texts.get(row.get("text_id")), row.get("mode")
    if (item is None or mode not in MODES or entry is None or row.get("schema") != SCHEMA
            or row.get("row_id") != _row_id(item, mode) or row.get("family") != item["family"]
            or row.get("split") != "discovery" or row.get("feature_ids") != plan["target_feature_ids"]
            or row.get("token_ids") != entry["token_ids"]
            or row.get("special_tokens_mask") != entry["special_tokens_mask"]
            or row.get("sae_authority") != AUTHORITY or row.get("plan_sha256") != _hash(plan)):
        raise ValueError("Invalid row/plan/selection binding")
    n, k = len(entry["token_ids"]), len(plan["target_feature_ids"])
    math_flags = row["model_math"]
    if (set(math_flags) != {"allow_tf32", "autocast_enabled", "float32_matmul_precision"}
            or type(math_flags["allow_tf32"]) is not bool or math_flags["autocast_enabled"] is not False
            or math_flags["float32_matmul_precision"] not in ("highest", "high", "medium")
            or row["sae_request_math"] != {"allow_tf32": False, "autocast_enabled": False}):
        raise ValueError("Invalid model/SAE math provenance")
    if type(row["test_only"]) is not bool or not re.fullmatch("[0-9a-f]{40}", row["freeze_commit"]):
        raise ValueError("Invalid test/freeze marker")
    projection = row["projection"]
    if any(projection.get(key) != value for key, value in {
            "operator": "active_support_projection", "change": .75, "norm_cap": .04,
            "gram_dtype": "float64", "coefficients_dtype": "float32", "support": "native_before > 0",
            "baseline": "prior_clean_exposure_native_bf16", "rounding_adaptation": False,
            "special_position_requests": "exact zero"}.items()):
        raise ValueError("Projection configuration changed")
    gram = np.asarray(projection["gram"], dtype=float)
    if (gram.shape != (k, k) or not np.isfinite(gram).all() or not np.array_equal(gram, gram.T)
            or np.linalg.eigvalsh(gram)[0] <= 0):
        raise ValueError("Invalid projection Gram")
    matrices = {}
    for key in ("native_before", "promoted_before", "promoted_after", "native_rounded_after", "precision_readout_shift",
                "paired_promoted_edit_delta"):
        value = np.asarray(row[key], dtype=float)
        if value.shape != (n, k) or not np.isfinite(value).all():
            raise ValueError("Invalid readout matrix: " + key)
        matrices[key] = value
    for key in ("native_before", "promoted_before", "promoted_after", "native_rounded_after"):
        if np.any(matrices[key] < 0):
            raise ValueError("Negative ReLU activation")
    for key, left, right in (("precision_readout_shift", "promoted_before", "native_before"),
                             ("paired_promoted_edit_delta", "promoted_after", "promoted_before")):
        expected = (matrices[left].astype(np.float32) - matrices[right].astype(np.float32)).astype(float)
        if not np.array_equal(matrices[key], expected):
            raise ValueError("Same-precision delta/readout shift mismatch")
    for key in ("native_nll", "nll", "kl_native_to_mode", "sham_nll", "kl_sham_to_mode"):
        values = row[key]
        if mode == "native_zero" and key in ("sham_nll", "kl_sham_to_mode"):
            if values is not None:
                raise ValueError("Unrun sham comparison must be null")
        elif (not isinstance(values, list) or len(values) != n or values[0] is not None
              or not all(type(v) in (int, float) and math.isfinite(v) for v in values[1:])):
            raise ValueError("Incomplete per-position loss array")
    metric_keys = {"requested_norm", "realized_norm", "clean_norm", "nonzero_requested", "identity",
                   "cosine", "relative_error", "realized_clean_ratio"}
    if set(row["delivery"]) != metric_keys:
        raise ValueError("Incomplete delivery metric schema")
    for key, values in row["delivery"].items():
        if (not isinstance(values, list) or len(values) != n or not np.isfinite(values).all()
                or (key in ("identity", "nonzero_requested") and any(type(v) is not bool for v in values))
                or (key not in ("identity", "nonzero_requested")
                    and any(type(v) not in (float, int) for v in values))):
            raise ValueError("Invalid delivery array: " + key)
    if mode in MODES[:2]:
        if (not all(row["delivery"]["identity"]) or any(row["delivery"]["nonzero_requested"])
                or not np.array_equal(matrices["promoted_before"], matrices["promoted_after"])):
            raise ValueError("Frozen no-op identity failed")
    if mode == "native_zero":
        if (row["returned_original_output"] is not True or row["boundary_trace"]
                or row["native_nll"] != row["nll"] or any(row["kl_native_to_mode"][1:])):
            raise ValueError("Native-zero must be the unchanged native path")
    elif row["returned_original_output"] is not False or not row["boundary_trace"]:
        raise ValueError("Actual downstream precision bridge evidence required")
    bridge = row["bridge"]
    native_mode = mode == "native_zero"
    bridge_expected = {"bridge_version": "fp32_residual_bf16_postnorm_cast_v1", "hooks_removed": True,
        "fp32_shadow_only": False, "readout_authority": AUTHORITY,
        "sublayer_dtype": "torch.bfloat16", "higher_precision_residual_model": not native_mode,
        "new_operator": not native_mode,
        "residual_dtype": "torch.bfloat16" if native_mode else "torch.float32",
        "arm": mode if mode in MODES[:2] else "signed_edit",
        "normalization_boundary": "unchanged native" if native_mode else
            "existing FP32 RMSNorm output, including weight multiplication, cast to BF16"}
    if any(bridge.get(key) != value for key, value in bridge_expected.items()):
        raise ValueError("Removed actual-model bridge hooks required")
    for trace in row["boundary_trace"]:
        if (trace["input_dtype"] != "torch.float32" or trace["output_dtype"] != "torch.float32"
                or trace["returned_dtype"] != "torch.bfloat16"):
            raise ValueError("Downstream FP32 residual/BF16 norm boundary mismatch")
    if not row["test_only"]:
        expected_modules = [f"model.layers.{i}.{name}" for i in range(51, 80)
                            for name in ("input_layernorm", "post_attention_layernorm")] + ["model.norm"]
        if (bridge["hook_layer"] != "model.layers.50.output" or row["sae_full_width"] != 65536
                or (not native_mode and [t["module"] for t in row["boundary_trace"]] != expected_modules)):
            raise ValueError("Production bridge/full-width architecture mismatch")
    capture = row["capture"]
    if (set(capture["tensors"]) != CAPTURE_KEYS or
            not re.fullmatch(r"tensors/\d{3}\.safetensors", capture["path"])):
        raise ValueError("Invalid precision capture schema/path")
    if root is not None:
        from safetensors.torch import load_file
        path = Path(root) / capture["path"]
        if sha(path) != capture["sha256"]:
            raise ValueError("Capture hash mismatch")
        tensors = load_file(str(path))
        if set(tensors) != CAPTURE_KEYS:
            raise ValueError("Unexpected raw tensor keys")
        for key, value in tensors.items():
            if capture["tensors"][key] != {"shape": list(value.shape), "dtype": str(value.dtype)}:
                raise ValueError("Capture tensor metadata mismatch")
            if not bool(torch.isfinite(value).all()):
                raise ValueError("Nonfinite raw tensor")
            if key in CAPTURE_KEYS - {"pre", "requested", "post", "token_ids", "valid"}:
                expected_shape = (n,) if key == "projection_scale" else (n, k)
                if value.dtype != torch.float32 or tuple(value.shape) != expected_shape:
                    raise ValueError("Raw readout/projection shape or dtype mismatch")
        pre, request, post = (tensors[key] for key in ("pre", "requested", "post"))
        if (pre.ndim != 3 or pre.shape[:2] != (1, n) or post.shape != pre.shape
                or request.shape != pre.shape or pre.dtype != torch.bfloat16
                or request.dtype != torch.float32 or post.dtype !=
                (torch.bfloat16 if mode == "native_zero" else torch.float32)):
            raise ValueError("Raw state shape/dtype mismatch")
        if not row["test_only"] and pre.shape[-1] != 8192:
            raise ValueError("Production hidden width mismatch")
        if path.stat().st_size > 21 * 1024**2:
            raise ValueError("Capture exceeds the fixed activation-only size ceiling")
        if tensors["token_ids"].dtype != torch.int64 or tensors["token_ids"].tolist() != [row["token_ids"]]:
            raise ValueError("Captured token inventory mismatch")
        expected_valid = torch.tensor([[not x for x in entry["special_tokens_mask"]]])
        if tensors["valid"].dtype != torch.bool or not torch.equal(tensors["valid"], expected_valid):
            raise ValueError("Captured exposure mask mismatch")
        if bool(torch.count_nonzero(request[~expected_valid])):
            raise ValueError("Special positions must have exact zero requests")
        if (bool(torch.count_nonzero(tensors["projection_coefficients"][~expected_valid.reshape(-1)]))
                or bool(((tensors["projection_scale"] <= 0) | (tensors["projection_scale"] > 1)).any())):
            raise ValueError("Invalid masked coefficients/cap scale")
        if not torch.equal(tensors["promoted_before"], F.relu(tensors["promoted_preact_before"])):
            raise ValueError("Promoted preactivation/activation mismatch")
        if mode in MODES[:2] and (bool(torch.count_nonzero(request)) or not torch.equal(post, pre.float())):
            raise ValueError("Raw zero/sham identity failed")
        if mode != "native_zero" and not torch.equal(post, pre.float() + request):
            raise ValueError("Captured post is not actual FP32 request delivery")
        for key in ("native_before", "promoted_before", "promoted_after", "native_rounded_after"):
            if tensors[key].dtype != torch.float32 or tensors[key].tolist() != row[key]:
                raise ValueError("Raw SAE readout mismatch")
        if _metrics(pre, request, post) != row["delivery"]:
            raise ValueError("Raw delivery reconstruction mismatch")
        exposure_h, exposure_z, receipt = _exposure_reference(
            Path(root).parent, item, row["plan_sha256"], row["freeze_commit"], row["feature_ids"], row["token_ids"])
        if (receipt != row["clean_exposure"] or not torch.equal(pre, exposure_h)
                or exposure_z != row["native_before"]):
            raise ValueError("Pilot baseline does not match prior clean exposure")
    canonical(row)
    return {"structural_pass": True, "scope": SCOPE}


def _fraction(pass_count, denominator):
    return pass_count / denominator if denominator else None


def summarize(rows):
    """Offline descriptive component summaries; no global qualification verdict."""
    rows = list(rows)
    if (len(rows) != 48 or len({row["row_id"] for row in rows}) != 48
            or len({row["text_id"] for row in rows}) != 12):
        raise ValueError("All 12 texts and four modes are required without selection")
    if len({row["test_only"] for row in rows}) != 1:
        raise ValueError("Cannot pool synthetic and production rows")
    if any(row["model_math"] != rows[0]["model_math"] for row in rows):
        raise ValueError("Model math settings differ between paired forwards")
    for text_id in {row["text_id"] for row in rows}:
        group = [row for row in rows if row["text_id"] == text_id]
        if set(row["mode"] for row in group) != set(MODES):
            raise ValueError("Missing required mode")
        for key in ("native_before", "promoted_before", "native_nll", "token_ids", "special_tokens_mask"):
            if any(row[key] != group[0][key] for row in group):
                raise ValueError("Paired arms have inconsistent native baselines")
        sham_nll = next(row["nll"] for row in group if row["mode"] == "precision_sham")
        if any(row["sham_nll"] != sham_nll for row in group if row["mode"] != "native_zero"):
            raise ValueError("Paired arms have inconsistent precision sham baseline")
    result = {"schema": SCHEMA, "scope": SCOPE, "completed": True,
              "full_model_forwards": 48, "text_count": 12, "modes": {},
              "sae_authority": AUTHORITY, "test_only": all(row["test_only"] for row in rows),
              "exposure_is_selection_criterion": False, "overall_assay_qualified": False,
              "baseline_shift_and_exposure_do_not_gate_completion": True}
    for mode in MODES:
        group = [row for row in rows if row["mode"] == mode]
        mask = np.concatenate([~np.asarray(row["special_tokens_mask"]) for row in group])
        delivery = {key: np.concatenate([row["delivery"][key] for row in group])
                    for key in group[0]["delivery"]}
        nonzero = mask & delivery["nonzero_requested"].astype(bool)
        good = nonzero & (delivery["cosine"] >= .95) & (delivery["relative_error"] <= .20)
        realized_nonzero = mask & (delivery["realized_norm"] > 0)
        norm_good = realized_nonzero & (delivery["realized_clean_ratio"] <= .05)
        fidelity = _fraction(int(good.sum()), int(nonzero.sum()))
        norm = _fraction(int(norm_good.sum()), int(realized_nonzero.sum()))
        summary = {"all_positions": int(len(mask)), "nonspecial_positions": int(mask.sum()),
                   "nonzero_requests": int(nonzero.sum()), "zero_requests": int((mask & ~nonzero).sum()),
                   "fidelity": {"passing_positions": int(good.sum()), "denominator": int(nonzero.sum()),
                                "fraction": fidelity, "pass": fidelity is not None and fidelity >= .95},
                   "norm": {"passing_positions": int(norm_good.sum()), "denominator": int(realized_nonzero.sum()),
                            "fraction": norm, "pass": norm is not None and norm >= .95},
                   "norm_all_nonspecial_secondary": {
                       "passing_positions": int((mask & (delivery["realized_clean_ratio"] <= .05)).sum()),
                       "denominator": int(mask.sum())},
                   "features": {}}
        for loss in ("native_nll", "nll", "kl_native_to_mode", "sham_nll", "kl_sham_to_mode"):
            values = [value for row in group if row[loss] is not None
                      for value, special in zip(row[loss], row["special_tokens_mask"])
                      if value is not None and not special]
            summary[loss] = {"mean": float(np.mean(values)) if values else None, "count": len(values)}
        before = np.concatenate([row["native_before"] for row in group])
        promoted = np.concatenate([row["promoted_before"] for row in group])
        after = np.concatenate([row["promoted_after"] for row in group])
        for j, feature in enumerate(group[0]["feature_ids"]):
            active = mask & (before[:, j] > 0)
            paired = active & (promoted[:, j] > 0)
            invalid_pairs = active & ~paired
            direction = -1 if mode == "suppression" else 1
            delta = direction * (after[:, j] - promoted[:, j])
            summary["features"][str(feature)] = {
                "nonspecial_denominator": int(mask.sum()), "native_active_positions": int(active.sum()),
                "promoted_active_positions": int((mask & (promoted[:, j] > 0)).sum()),
                "native_active_texts": sum(any(z[j] > 0 and not special for z, special in
                    zip(row["native_before"], row["special_tokens_mask"])) for row in group),
                "support_disagreements": int((mask & ((before[:, j] > 0) != (promoted[:, j] > 0))).sum()),
                "readout_shift_mean": float(np.mean((promoted[:, j] - before[:, j])[mask])),
                "primary_eligible_native_active_positions": int(active.sum()),
                "paired_promoted_defined_positions": int(paired.sum()),
                "paired_promoted_undefined_positions": int(invalid_pairs.sum()),
                "native_anchor_after_ratio_median": float(np.median(after[active, j] / before[active, j]))
                    if active.any() else None,
                "paired_delta_over_requested_native_change_median":
                    float(np.median(delta[active] / (.75 * before[active, j]))) if active.any() else None,
                "paired_promoted_after_ratio_median": float(np.median(after[paired, j] / promoted[paired, j]))
                    if paired.any() and not invalid_pairs.any() else None,
                "paired_promoted_defined_only_after_ratio_median":
                    float(np.median(after[paired, j] / promoted[paired, j])) if paired.any() else None,
                "paired_promoted_fraction_median": float(np.median(delta[paired] / promoted[paired, j]))
                    if paired.any() and not invalid_pairs.any() else None,
                "efficacy_qualified": False}
        result["modes"][mode] = summary
    return result


def validate_run(out, plan, plan_hash, freeze):
    """Read-only hash-chain, complete-inventory and tensor reconstruction audit."""
    root = Path(out) / DIRECTORY
    expected = {_row_id(item, mode) for item in pilot_texts(plan) for mode in MODES}
    if plan_hash != _hash(plan):
        raise ValueError("Plan hash mismatch")
    binding = {"schema": SCHEMA, "plan_sha256": plan_hash, "freeze_commit": freeze,
               "text_ids": [item["id"] for item in pilot_texts(plan)]}
    if json.loads((root / "binding.json").read_text()) != binding:
        raise ValueError("Pilot binding artifact mismatch")
    raw = (root / "receipts.jsonl").read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("Truncated receipt ledger")
    previous, seen, records, events = None, set(), {}, []
    for seq, line in enumerate(raw.splitlines()):
        event = json.loads(line)
        body = {key: value for key, value in event.items() if key != "sha256"}
        if (canonical(event).encode() != line or event["seq"] != seq
                or event["plan_sha256"] != plan_hash or event["freeze_commit"] != freeze
                or event["previous_sha256"] != previous or event["id"] in seen
                or hashlib.sha256(canonical(body).encode()).hexdigest() != event["sha256"]):
            raise ValueError("Receipt hash chain mismatch")
        seen.add(event["id"])
        previous = event["sha256"]
        events.append(event)
        data = event["data"]
        if data["kind"] == "row":
            rid, payload = data["row_id"], data["payload"]
            if rid not in expected or rid in records or not re.fullmatch(r"rows/\d{3}\.json", payload["path"]):
                raise ValueError("Invalid receipt row inventory")
            path = root / payload["path"]
            if sha(path) != payload["sha256"]:
                raise ValueError("Row hash mismatch")
            row = json.loads(path.read_text())
            if (row["row_id"] != rid or row["freeze_commit"] != freeze
                    or row["capture"]["sha256"] != payload["capture_sha256"]):
                raise ValueError("Receipt/row binding mismatch")
            validate_row(row, plan, root)
            records[rid] = row
    if (set(records) != expected or events[0]["data"] != {"kind": "binding", "row_ids": sorted(expected)}
            or events[-1]["data"].get("kind") != "complete"
            or events[-1]["data"].get("full_model_forwards") != 48
            or events[-1]["data"].get("summary_sha256") != sha(root / "summary.json")):
        raise ValueError("Incomplete pilot receipt inventory")
    dispatch = [e["data"]["row_id"] for e in events if e["data"]["kind"] == "dispatch"]
    ordered = [_row_id(item, mode) for item in pilot_texts(plan) for mode in MODES]
    if dispatch != ordered:
        raise ValueError("Pilot forward inventory mismatch")
    event_ids = ["binding", "runtime", "qualification"]
    for ordinal, rid in enumerate(ordered):
        event_ids.extend(["dispatch:" + rid, "row:" + rid])
        data = next(e["data"] for e in events if e["id"] == "dispatch:" + rid)
        if data != {"kind": "dispatch", "row_id": rid, "ordinal": ordinal, "full_model_forwards": 1}:
            raise ValueError("Unexpected forward dispatch or retry")
    if [e["id"] for e in events] != event_ids + ["complete"]:
        raise ValueError("Unexpected receipt events/order")
    qualifications = [e["data"] for e in events if e["id"] == "qualification"]
    qualification = json.loads((root / "qualification.json").read_text())
    if (qualifications != [{"kind": "qualification", "sha256": sha(root / "qualification.json")}]
            or qualification.get("pass") is not True or qualification.get("synthetic_only") is not True
            or qualification.get("production_model_loaded") is not False
            or not qualification.get("checks") or not all(v is True for v in qualification["checks"].values())
            or qualification.get("bridge_version") != "fp32_residual_bf16_postnorm_cast_v1"
            or (not all(row["test_only"] for row in records.values())
                and not qualification.get("device", "").startswith("cuda"))):
        raise ValueError("Synthetic bridge qualification binding or checks failed")
    summary = summarize(records.values())
    if summary != json.loads((root / "summary.json").read_text()):
        raise ValueError("Summary reconstruction mismatch")
    if {p.name for p in (root / "rows").iterdir()} != {f"{i:03d}.json" for i in range(48)}:
        raise ValueError("Unexpected or missing row files")
    if {p.name for p in (root / "tensors").iterdir()} != {f"{i:03d}.safetensors" for i in range(48)}:
        raise ValueError("Unexpected or missing tensor files")
    return {"structural_pass": True, "row_count": 48, "scope": SCOPE}
