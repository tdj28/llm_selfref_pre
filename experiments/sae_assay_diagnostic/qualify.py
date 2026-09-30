"""Offline source qualification; never loads pretrained weights or creates a GPU.

CLI qualification requires the production torch 2.8.0/cu128 runtime. CPU tests
exercise the same tiny random Llama but cannot qualify CUDA or the 70B model.
The optional NF4 check covers one linear layer, not a quantized Llama loader.
qualify_real observes a fixed seven-text shard on an already supplied backend;
it does not authorize collection or invent a selected/full encoder tolerance.

Run: python -m experiments.sae_assay_diagnostic.qualify --out qualification.json
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import time

import torch

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_diagnostic.backend import (
    ENCODING_AUTHORITY, ModelBackend, _check_runtime_versions, edit_hidden,
)


SEED = 1823
QUALIFICATION_TEXT_IDS = tuple(f"calibration-{category}-01" for category in (
    "pretending", "cover-story", "assistant-roleplay", "misdirection",
    "dishonesty", "persona-maintenance", "neutral"))
TINY_FEATURE_IDS = (0, 3)


class _TinyTokenizer:
    """Deliberately non-round-tripping tokenizer to exercise token-ID replay."""

    all_special_ids = [0, 1, 2, 3]
    eos_token_id = 2
    chat_template = "offline-qualification-v1: bos + character IDs"

    def __call__(self, text, **_kwargs):
        ids = torch.tensor([[1] + [4 + ord(c) % 28 for c in text]])
        return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}

    def apply_chat_template(self, messages, *, tokenize, **_kwargs):
        text = "|".join(m["role"] + ":" + m["content"] for m in messages)
        return self(text)["input_ids"] if tokenize else text

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids
                        if not skip_special_tokens or i not in self.all_special_ids)


def tiny_backend(device="cpu"):
    """Construct only local random components, always native BF16 and SDPA."""
    from transformers import LlamaConfig, LlamaForCausalLM

    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(SEED)
        config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
                            num_hidden_layers=2, num_attention_heads=2,
                            num_key_value_heads=2, max_position_embeddings=2048,
                            bos_token_id=1, eos_token_id=2, pad_token_id=0,
                            attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = LlamaForCausalLM(config).to(device=device, dtype=torch.bfloat16).eval()
        state = {"encoder_linear.weight": torch.randn(32, 16) * .125,
                 "encoder_linear.bias": torch.full((32,), .5),
                 "decoder_linear.weight": torch.randn(16, 32) * .125,
                 "decoder_linear.bias": torch.zeros(16)}
    return ModelBackend.from_components_for_test(
        model, _TinyTokenizer(), state, default_feature_ids=TINY_FEATURE_IDS)


def _known_answers(device):
    # Dyadic values have exact BF16 answers, independent of random-model outputs.
    kwargs = {"device": device, "dtype": torch.bfloat16}
    hidden = torch.tensor([[1., 2., -1.], [2., 1., 0.]], **kwargs)
    encoder = torch.tensor([[0., 0., 1.], [1., 0., 0.], [1., 1., 0.],
                            [0., 1., 0.], [0., 0., -1.]], **kwargs)
    bias = torch.tensor([0., .5, 0., .25, 0.], **kwargs)
    decoder = torch.tensor([[0., 1., 0., .25, 0.],
                            [0., .5, 0., 1., 0.], [0., 0., 1., 0., 1.]], **kwargs)
    args = (hidden, encoder, bias, decoder)
    zero, z = edit_hidden(*args, feature_ids=[1, 3], mode="suppression", strength=0.)
    down, d = edit_hidden(*args, feature_ids=[1, 3], mode="suppression", strength=.5)
    up, u = edit_hidden(*args, feature_ids=[1, 3], mode="amplification", strength=.5,
                        q90=[2.5, 1.])
    _, all_features = edit_hidden(*args)
    checks = {
        "zero_object_identity": zero is hidden,
        "zero_bitwise_identity": torch.equal(zero, hidden) and bool(z["identity"].all()),
        "full_encoder_known_answer": z["before"].tolist() == [[1.5, 2.25], [2.5, 1.25]],
        "panel_invariance": torch.equal(z["before"], all_features["before"][:, [1, 3]]),
        "suppression_signed_request": d["requested_delta"].tolist() == [[-.75, -1.125], [-1.25, -.625]],
        "suppression_residual": down.tolist() == [[-.03125, .5, -1.], [.59375, -.25, 0.]],
        "suppression_reencoding": d["after"].tolist() == [[.46875, .75], [1.09375, 0.]],
        "amplification_signed_request": u["requested_delta"].tolist() == [[.5, 0.], [0., 0.]],
        "amplification_residual": up.tolist() == [[1.5, 2.25, -1.], [2., 1., 0.]],
    }
    return {"checks": checks, "raw": {"hidden": hidden.tolist(), "zero": zero.tolist(),
            "suppression": down.tolist(), "amplification": up.tolist(),
            "telemetry": {name: {k: v.cpu().tolist() for k, v in metrics.items()}
                          for name, metrics in (("zero", z), ("suppression", d), ("amplification", u))}}}


def run_tiny_checks(device="cpu"):
    """Actual tiny Llama checks. CPU success is explicitly not CUDA qualification."""
    started = time.perf_counter()
    known = _known_answers(device)
    checks = dict(known["checks"])
    raw = {"known_answers": known["raw"], "teacher": {}, "generation": {}, "replay": {}}
    backend = tiny_backend(device)
    try:
        ids = list(TINY_FEATURE_IDS)
        arms = {"zero": {"feature_ids": ids, "mode": "suppression", "strength": 0.},
                "suppression": {"feature_ids": ids, "mode": "suppression", "strength": .5},
                "amplification": {"feature_ids": ids, "mode": "amplification", "strength": .5,
                                  "q90": [2., 2.]}}
        baseline = backend.teacher("abcdef", ids, collect_reconstruction=True)
        raw["teacher"]["clean"] = baseline
        t = baseline["telemetry"]
        checks["native_bf16_full_encoder"] = (
            backend.dtype == torch.bfloat16 and t["native_dtype"] == "torch.bfloat16"
            and t["encoding_authority"] == ENCODING_AUTHORITY
            and t["full_encode_shape"] == [1, 32, 16]
            and all(t["selected_activations"][when] == t["full_sae"][f"full_selected_{when}"]
                    for when in ("before", "after")))
        tokens = torch.tensor([baseline["token_ids"]], device=backend.device)
        with torch.inference_mode():
            plain = backend.model.model(tokens, use_cache=False).last_hidden_state
            hooked, _ = backend._forward(tokens, ids, arms["zero"])
        checks["unhooked_zero_hidden_identity"] = torch.equal(plain, hooked.last_hidden_state)
        clean_generation = backend.generate([{"role": "user", "content": "abc"}],
                                            SEED, .7, max_new_tokens=4)
        raw["generation"]["clean"] = clean_generation
        for name, arm in arms.items():
            result = backend.teacher("abcdef", ids, arm, collect_reconstruction=True)
            raw["teacher"][name] = result
            a = result["telemetry"]["selected_activations"]
            if name == "zero":
                checks["teacher_zero_identity"] = (
                    result["edited_nll"] == baseline["unsteered_nll"]
                    and result["kl_clean_to_edited"] == [None] + [0.] * 6
                    and a == baseline["telemetry"]["selected_activations"])
            else:
                expected = [[-.5 * b if name == "suppression" else .5 * max(2. - b, 0.)
                             for b in row] for row in a["before"]]
                checks[f"teacher_{name}_request"] = (
                    a["requested_delta"] == expected and any(v != 0 for row in expected for v in row))
            generated = backend.generate([{"role": "user", "content": "abc"}],
                                         SEED, .7, max_new_tokens=4, intervention=arm)
            replay = backend.replay_tokens(generated["input_token_ids"], generated["output_token_ids"],
                                           ids, intervention=arm)
            raw["generation"][name], raw["replay"][name] = generated, replay
            positions = replay["telemetry"]["position_metadata"]
            boundary = len(generated["input_token_ids"])
            checks[f"{name}_exact_replay"] = (
                replay["telemetry"] == generated["telemetry"]
                and replay["token_ids"] == generated["input_token_ids"] + generated["output_token_ids"]
                and replay["forward_schedule"] == "original_prefill_then_cached_token1"
                and replay["prompt_length"] == boundary
                and all(p["origin"] == ("prompt" if i < boundary else "generated")
                        for i, p in enumerate(positions))
                and [p["terminal_observation_only"] for p in positions] == [False] * (len(positions) - 1) + [True])
        checks["generation_zero_identity"] = all(
            raw["generation"]["zero"][key] == clean_generation[key]
            for key in ("input_token_ids", "output_token_ids", "telemetry"))
        checks["hooks_removed"] = not backend._layer._forward_hooks
        metadata = dict(backend.metadata)
    finally:
        backend.close()
    return {"pass": all(checks.values()), "checks": checks, "raw_outputs": raw,
            "backend_metadata": metadata, "seed": SEED, "device": str(device),
            "scope": "Tiny random BF16 Llama only; CPU runs do not qualify CUDA or 70B.",
            "elapsed_seconds": time.perf_counter() - started}


def _nf4_smoke():
    if importlib.util.find_spec("bitsandbytes") is None:
        return {"status": "unavailable", "pass": None, "reason": "bitsandbytes is not installed"}
    import bitsandbytes as bnb

    started = time.perf_counter()
    with torch.random.fork_rng(devices=[]), torch.inference_mode():
        torch.random.default_generator.manual_seed(SEED)
        layer = bnb.nn.Linear4bit(64, 64, bias=False, compute_dtype=torch.bfloat16,
                                 compress_statistics=True, quant_type="nf4")
        weight = (torch.arange(4096).reshape(64, 64).remainder(63) - 31).float() / 64
        layer.weight.copy_(weight)
        layer = layer.to("cuda")
        x = torch.arange(128, device="cuda", dtype=torch.bfloat16).reshape(2, 64) / 128
        output, repeated = layer(x), layer(x)
        torch.cuda.synchronize()
        passed = (output.shape == (2, 64) and output.dtype == torch.bfloat16
                  and bool(torch.isfinite(output).all()) and torch.equal(output, repeated)
                  and layer.weight.quant_state is not None and layer.weight.quant_type == "nf4")
        return {"status": "passed" if passed else "failed", "pass": passed,
                "bitsandbytes_version": bnb.__version__, "output": output.float().cpu().tolist(),
                "elapsed_seconds": time.perf_counter() - started,
                "scope": "One NF4 CUDA Linear4bit with double quantization and BF16 compute; not 70B loader qualification."}


def qualify_source():
    """Fail closed on a non-pinned/non-CUDA host, without constructing a model."""
    started = time.perf_counter()
    result = {"schema": "sae_assay_source_qualification_v1", "pass": False,
              "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                          "cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
                          "gpu": None},
              "required_runtime": {"torch": "2.8.0", "cuda": "12.8", "transformers": "4.47.1"},
              "source_hashes": {}, "tiny": None,
              "nf4": {"status": "not_run", "pass": None}, "errors": []}
    try:
        import transformers

        result["runtime"]["transformers"] = transformers.__version__
        for name in ("qualify.py", "backend.py", "analysis.py", "fixtures.py"):
            path = Path(__file__).resolve().with_name(name)
            key = path.relative_to(Path(__file__).resolve().parents[2]).as_posix()
            result["source_hashes"][key] = hashlib.sha256(path.read_bytes()).hexdigest()
        _check_runtime_versions(torch.__version__, torch.version.cuda, transformers.__version__)
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
            raise RuntimeError("CUDA with native BF16 support is required")
        properties = torch.cuda.get_device_properties(torch.cuda.current_device())
        free, total = torch.cuda.mem_get_info()
        result["runtime"]["gpu"] = {"name": properties.name, "capability": [properties.major, properties.minor],
                                     "total_bytes": total, "free_bytes": free,
                                     "device_index": torch.cuda.current_device()}
        result["tiny"] = run_tiny_checks("cuda")
        if result["tiny"]["pass"]:
            result["nf4"] = {"status": "running", "pass": None}
            result["nf4"] = _nf4_smoke()
        result["pass"] = result["tiny"]["pass"] and result["nf4"]["pass"] is not False
    except Exception as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        if result["nf4"]["status"] == "running":
            result["nf4"] = {"status": "failed", "pass": False}
    result["elapsed_seconds"] = time.perf_counter() - started
    result["scope"] = "Source/kernel smoke only. Real-model gate and an unavailable NF4 branch remain unqualified."
    return result


def _path_decisions(rows, quantiles):
    """Registered exposure rule evaluated on this shard, not full calibration."""
    features = []
    for j, feature in enumerate(quantiles["feature_ids"]):
        q90 = quantiles["q90"][j]
        # The backend casts the supplied pooled q90 to FP32 before subtraction.
        q90 = torch.tensor(q90, dtype=torch.float32).item() if q90 is not None else None
        counts = {direction: {} for direction in ("suppression", "amplification")}
        masks = {}
        for row in rows:
            t = row["result"]["telemetry"]
            eligible = [p["token_class"] != "special" and t["delivery"]["valid"][i]
                        for i, p in enumerate(t["position_metadata"])]
            values = [r[j] for r in t["selected_activations"]["before"]]
            masks[row["id"]] = {
                "suppression": [ok and v > 0 for ok, v in zip(eligible, values)],
                "amplification": [ok and v < q90 for ok, v in zip(eligible, values)] if q90 is not None else None}
            for direction in counts:
                mask = masks[row["id"]][direction]
                counts[direction][row["id"]] = sum(mask) if mask is not None else None
        exposure = {}
        for direction, by_text in counts.items():
            available = all(v is not None for v in by_text.values())
            positions = sum(by_text.values()) if available else None
            texts = sum(v > 0 for v in by_text.values()) if available else None
            exposure[direction] = {"positions": positions, "texts": texts, "by_text": by_text,
                                   "eligible": positions >= 100 and texts >= 6 if available else None}
        features.append({"feature_id": feature, "q90_available": q90 is not None,
                         "effective_fp32_q90": q90,
                         "position_masks": masks, "exposure": exposure})
    return {"features": features, "rule": "At least 100 eligible positions across at least 6 texts, per direction."}


def qualify_real(backend, texts, target_ids):
    """Observe the fixed shard without I/O or selection based on observed outcomes.

    texts is the frozen fixture inventory (or exactly its prescribed seven
    calibration records), each with id/split/category/text. Only those seven
    IDs are executed, in fixed order. Raw zero-arm teacher outputs are retained.
    Alternate q90/masks are diagnostic calculations on the SAME hidden states,
    not an alternate intervention forward. Parent must qualify dose/verdicts.
    """
    ids = list(target_ids)
    if not ids or any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("target_ids must be unique nonnegative integers")
    inventory = {}
    for text in texts:
        if text["id"] in inventory:
            raise ValueError("Duplicate text ID")
        inventory[text["id"]] = text
    selected = []
    for key in QUALIFICATION_TEXT_IDS:
        item = inventory.get(key)
        if (item is None or item.get("split") != "calibration"
                or item.get("category") != key[len("calibration-"):-3]
                or not isinstance(item.get("text"), str) or not item["text"]):
            raise ValueError(f"Missing/invalid fixed calibration text: {key}")
        selected.append(item)
    result = {"schema": "sae_assay_real_qualification_observation_v1",
              "qualification_pass": None, "collection_complete": False,
              "text_ids": list(QUALIFICATION_TEXT_IDS), "target_ids": ids,
              "rows": [], "encoder_comparisons": [], "errors": [],
              "numerical_tolerance": None,
              "scope": "Seven fixed zero-arm texts. Observed mask/exposure and q90 parity only; dose/verdict qualification remains with parent."}
    try:
        alternate_rows = []
        for item in selected:
            raw = backend.teacher(item["text"], ids, collect_reconstruction=True)
            row = {"id": item["id"], "split": "calibration", "category": item["category"],
                   "group": "target", "mode": "zero", "strength": 0., "result": raw,
                   "text_sha256": hashlib.sha256(item["text"].encode()).hexdigest()}
            result["rows"].append(row)
            check = analysis.validate_teacher_rows([row])
            if not check["pass"]:
                raise ValueError(f"Invalid backend result: {check['errors']}")
            t = raw["telemetry"]
            if (t.get("encoding_authority") != ENCODING_AUTHORITY
                    or t.get("native_dtype") != "torch.bfloat16" or t["feature_ids"] != ids):
                raise ValueError("Expected authoritative native BF16 full encoder and exact ordered targets")
            full = t["full_sae"]
            comparison = {"id": item["id"], "activity": analysis.encoder_parity_report(t), "differences": {}}
            for when in ("before", "after"):
                primary, alternate = t["selected_activations"][when], full[f"selected_path_{when}"]
                if primary != full[f"full_selected_{when}"]:
                    raise ValueError("Authoritative selected columns differ from full encoder diagnostic")
                comparison["differences"][when] = [[b - a for a, b in zip(pr, alt)]
                                                     for pr, alt in zip(primary, alternate)]
            result["encoder_comparisons"].append(comparison)
            diagnostic = deepcopy(row)
            activations = diagnostic["result"]["telemetry"]["selected_activations"]
            for key, when in (("before", "before"), ("after", "after"), ("requested_activation", "before")):
                activations[key] = deepcopy(full[f"selected_path_{when}"])
            alternate_rows.append(diagnostic)
        primary_q90 = analysis.calibration_q90(result["rows"])
        alternate_q90 = analysis.calibration_q90(alternate_rows)
        if any("invalid_data" in q["failure_codes"] for q in (primary_q90, alternate_q90)):
            raise ValueError("Invalid zero-arm data for q90 comparison")
        primary_decisions = _path_decisions(result["rows"], primary_q90)
        alternate_decisions = _path_decisions(alternate_rows, alternate_q90)
        result.update(collection_complete=True,
                      q90={"authoritative": primary_q90, "selected_path": alternate_q90,
                           "exactly_equal": primary_q90["q90"] == alternate_q90["q90"],
                           "selected_minus_authoritative": [b - a if a is not None and b is not None else None
                               for a, b in zip(primary_q90["q90"], alternate_q90["q90"])]},
                      decisions={"authoritative": primary_decisions, "selected_path": alternate_decisions,
                                 "exactly_equal": primary_decisions == alternate_decisions})
    except Exception as exc:
        result["errors"].append({"type": type(exc).__name__, "message": str(exc)})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    # Refuse replacement before running any CUDA work; preserve prior receipts.
    with args.out.open("x", encoding="utf-8") as handle:
        summary = qualify_source()
        json.dump(summary, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
