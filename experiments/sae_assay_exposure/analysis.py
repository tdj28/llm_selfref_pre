"""Structural checks and fixed-panel exposure reports; no outcome generation.

All selection is delegated to the previously authored exposure helper. Poor
exposure, reconstruction, and selected-width agreement are scientific results,
not malformed data. Missing/nonfinite telemetry is never replaced with zeros.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from experiments.sae_assay_replay import exposure


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "sae_assay_exposure_row_v1"
AUTHORITY = "full_native_token1_v1"
HIDDEN_SIZE = 8192
MAX_CAPTURE_BYTES = 400_000_000
TOKENIZER_INVENTORY_SHA256 = "fa0ca62507ab02cf41e70bdaafe1e268638b50c4f64b20502e49023463e904ca"
TOKENIZATION_SHA256 = "586f2813f207be1389e223329b07fcbfe82c56e4858790c8ad5a49e1380cc49f"
ROW_KEYS = {
    "schema", "id", "text_id", "family", "split", "category", "text_sha256",
    "plan_sha256", "freeze_commit", "feature_ids", "encoding_authority",
    "token_ids", "special_tokens_mask", "activations", "diagnostics", "capture",
    "elapsed_seconds",
}
DIAGNOSTIC_KEYS = {
    "clean_norm", "reconstruction_error_norm", "reconstruction_relative_error",
    "l0", "selected_path_activations", "selected_path_max_abs_error",
    "selected_path_positive_mask_disagreements",
}


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def json_sha(value):
    """Hash the canonical on-disk JSON convention, including its final newline."""
    return hashlib.sha256((exposure.canonical(value) + "\n").encode("ascii")).hexdigest()


def _hash(value, length=64):
    if (not isinstance(value, str) or len(value) != length
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("Invalid hash binding")


def _number(value, name, *, nonnegative=True):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (nonnegative and value < 0)):
        raise ValueError("Invalid finite numeric field: " + name)


def _vector(value, length, name):
    if not isinstance(value, list) or len(value) != length:
        raise ValueError("Invalid array shape: " + name)
    for entry in value:
        _number(entry, name)


def _activations(value, n):
    if not isinstance(value, dict) or set(value) != {str(f) for f in exposure.TARGETS}:
        raise ValueError("All six feature activation arrays are required")
    for feature, values in value.items():
        _vector(values, n, "activation " + feature)


def checked_design(plan):
    """Validate the runtime part of the parent-owned plan, without changing it.

    Parent protocol.load_plan additionally authenticates source hashes, input
    files and the public freeze. Metadata such as hardware/source_hashes may be
    present at the top level; none can override the fixed scientific inputs.
    """
    if plan.get("schema") != "sae_exposure_v1":
        raise ValueError("Unsupported exposure plan schema")
    rows, certificate = plan["texts"], plan["certificate"]
    if plan["rules"] != exposure.selection_rules():
        raise ValueError("Exposure rules changed")
    inventory = exposure._checked_inventory(rows, certificate)
    if json_sha(certificate) != TOKENIZATION_SHA256:
        raise ValueError("Not the already certified 224-row tokenization")
    if certificate["tokenizer_sha256"] != TOKENIZER_INVENTORY_SHA256:
        raise ValueError("Tokenizer inventory/certificate mismatch")
    if plan["target_feature_ids"] != list(exposure.TARGETS):
        raise ValueError("Require all six ordered feature IDs")
    if "model" in plan and plan["model"] != {"id": "meta-llama/Llama-3.3-70B-Instruct",
                         "revision": exposure.MODEL_REVISION, "precision": "bf16"}:
        raise ValueError("Require the pinned BF16 model")
    if "sae" in plan and plan["sae"] != {"id": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
                       "revision": exposure.SAE_REVISION, "sha256": exposure.SAE_SHA256}:
        raise ValueError("Require the pinned full-width SAE")
    if "first_five" in plan and plan["first_five"] != [row["id"] for row in rows[:5]]:
        raise ValueError("First-five order changed")
    return inventory


def validate_row(row, item, certificate_item, *, plan_sha256=None, freeze_commit=None):
    if not isinstance(row, dict) or set(row) != ROW_KEYS:
        raise ValueError("Unexpected activation-only raw row schema")
    fixed = {"schema": SCHEMA, "id": "clean-" + item["id"], "text_id": item["id"],
             "family": item["family"], "split": item["split"], "category": item["category"],
             "text_sha256": exposure.text_digest(item["text"]),
             "feature_ids": list(exposure.TARGETS), "encoding_authority": AUTHORITY}
    if any(row[k] != v for k, v in fixed.items()):
        raise ValueError("Raw row identity/design mismatch")
    _hash(row["plan_sha256"])
    _hash(row["freeze_commit"], 40)
    if ((plan_sha256 is not None and row["plan_sha256"] != plan_sha256)
            or (freeze_commit is not None and row["freeze_commit"] != freeze_commit)):
        raise ValueError("Raw row plan/freeze mismatch")
    tokens, mask = row["token_ids"], row["special_tokens_mask"]
    if (not isinstance(tokens, list) or any(type(t) is not int for t in tokens)
            or tokens != certificate_item["token_ids"] or not isinstance(mask, list)
            or any(type(m) is not bool for m in mask)
            or mask != certificate_item["special_tokens_mask"]):
        raise ValueError("Actual tokens/special mask differ from certificate")
    n = len(tokens)
    _activations(row["activations"], n)
    d = row["diagnostics"]
    if not isinstance(d, dict) or set(d) != DIAGNOSTIC_KEYS:
        raise ValueError("Incomplete diagnostics")
    for key in ("clean_norm", "reconstruction_error_norm", "reconstruction_relative_error"):
        _vector(d[key], n, key)
    for norm, error, relative in zip(d["clean_norm"], d["reconstruction_error_norm"],
                                     d["reconstruction_relative_error"]):
        if norm <= 0 or not math.isclose(relative, error / norm, rel_tol=1e-5, abs_tol=1e-7):
            raise ValueError("Nonpositive clean norm or inconsistent reconstruction ratio")
    if (not isinstance(d["l0"], list) or len(d["l0"]) != n
            or any(type(v) is not int or not 0 <= v <= 65536 for v in d["l0"])):
        raise ValueError("Invalid full-SAE sparsity")
    if any(d["l0"][i] < sum(values[i] > 0 for values in row["activations"].values()) for i in range(n)):
        raise ValueError("Full-SAE sparsity smaller than positive target count")
    _activations(d["selected_path_activations"], n)
    differences = [abs(a - b) for feature in row["activations"] for a, b in
                   zip(row["activations"][feature], d["selected_path_activations"][feature])]
    disagreements = sum((a > 0) != (b > 0) for feature in row["activations"] for a, b in
                        zip(row["activations"][feature], d["selected_path_activations"][feature]))
    _number(d["selected_path_max_abs_error"], "selected_path_max_abs_error")
    if (d["selected_path_max_abs_error"] != max(differences)
            or type(d["selected_path_positive_mask_disagreements"]) is not int
            or d["selected_path_positive_mask_disagreements"] != disagreements):
        raise ValueError("Selected-path diagnostic inconsistent with recorded arrays")
    capture = row["capture"]
    if (not isinstance(capture, dict) or set(capture) != {"path", "sha256", "bytes"}
            or capture["path"] != "residuals/" + item["id"] + ".safetensors"
            or type(capture["bytes"]) is not int
            or not n * HIDDEN_SIZE * 2 <= capture["bytes"] <= n * (HIDDEN_SIZE * 2 + 8) + 4096):
        raise ValueError("Invalid capture inventory entry")
    _hash(capture["sha256"])
    _number(row["elapsed_seconds"], "elapsed_seconds")
    if row["elapsed_seconds"] <= 0:
        raise ValueError("Positive elapsed time required")
    return {"id": item["id"], "token_ids": tokens, "activations": row["activations"]}


def validate_capture(out, row):
    """Read one small shard at a time; hash and check dtype, shape and token IDs."""
    from safetensors.torch import load_file
    import torch

    capture = row["capture"]
    path = Path(out) / capture["path"]
    if (path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(out).resolve())
            or path.stat().st_size != capture["bytes"] or sha(path) != capture["sha256"]):
        raise ValueError("Residual capture hash/size/path mismatch")
    tensors = load_file(str(path))
    if set(tensors) != {"hidden", "token_ids"}:
        raise ValueError("Unexpected capture tensors")
    hidden, tokens = tensors["hidden"], tensors["token_ids"]
    n = len(row["token_ids"])
    if (hidden.dtype != torch.bfloat16 or hidden.shape != (1, n, HIDDEN_SIZE)
            or tokens.dtype != torch.int64 or tokens.shape != (1, n)
            or tokens[0].tolist() != row["token_ids"] or not bool(torch.isfinite(hidden).all())):
        raise ValueError("Residual capture dtype/shape/tokens/finite mismatch")
    norms = torch.linalg.vector_norm(hidden.float(), dim=-1)[0]
    if not torch.allclose(norms, torch.tensor(row["diagnostics"]["clean_norm"]), rtol=1e-5, atol=1e-6):
        raise ValueError("Capture norm disagrees with raw telemetry")


def summarize(rows, plan, *, plan_sha256=None, freeze_commit=None):
    inventory = checked_design(plan)
    by_id = {item["id"]: item for item in plan["texts"]}
    measurements, seen = {split: [] for split in exposure.SPLITS}, set()
    bindings = set()
    for row in rows:
        text_id = row.get("text_id")
        if text_id not in by_id or text_id in seen:
            raise ValueError("Duplicate or unplanned row")
        seen.add(text_id)
        measurement = validate_row(row, by_id[text_id], inventory[text_id],
                                   plan_sha256=plan_sha256, freeze_commit=freeze_commit)
        measurements[row["split"]].append(measurement)
        bindings.add((row["plan_sha256"], row["freeze_commit"]))
    if seen != set(by_id) or len(bindings) != 1:
        raise ValueError("Incomplete or mixed-run panel; missingness is not zero exposure")
    discovery = exposure.select_discovery(plan["texts"], measurements["discovery"],
                                          certificate=plan["certificate"])
    panels = {split: exposure.report_exposure(plan["texts"], measurements[split], split=split,
                                              certificate=plan["certificate"])
              for split in exposure.SPLITS}
    passed = (discovery["selected_panel"]["all_six_exposure_minima_met"]
              and panels["validation"]["all_six_exposure_minima_met"])
    return {"schema": "sae_assay_exposure_summary_v1", "structural_pass": True,
            "rows": len(rows), "split_counts": dict(Counter(r["split"] for r in rows)),
            "plan_sha256": next(iter(bindings))[0], "freeze_commit": next(iter(bindings))[1],
            "discovery": discovery, "panels": panels,
            "exposure_minima_met": passed,
            "scientific_status": "exposure_minima_met_only" if passed else "insufficient_exposure_unresolved",
            "assay_qualification": "not_evaluated", "behavioral_assay_qualified": False,
            "diagnostics": {
                "selected_path_max_abs_error": max(r["diagnostics"]["selected_path_max_abs_error"] for r in rows),
                "selected_path_positive_mask_disagreements": sum(
                    r["diagnostics"]["selected_path_positive_mask_disagreements"] for r in rows),
                "maximum_reconstruction_relative_error": max(
                    max(r["diagnostics"]["reconstruction_relative_error"]) for r in rows)},
            "inference_unit": "authored text family; positions and variants are not independent draws"}


def audit_run(out, plan, plan_sha256, freeze_commit, *, complete=True):
    """Reconcile dispatch, receipt, raw rows, captures and full file identities."""
    from experiments.sae_assay_diagnostic.budget import EventLedger

    out = Path(out)
    if not (out / "receipts.jsonl").is_file():
        raise ValueError("Missing receipts ledger")
    inventory = checked_design(plan)
    expected = {"clean-" + item["id"]: item for item in plan["texts"]}
    all_ids = ["qualification-live", *expected]
    ledger = EventLedger(out / "receipts.jsonl", plan_sha256, freeze_commit, all_ids)
    events = ledger.read()
    dispatches = [e for e in events if e["data"].get("kind") == "dispatch"]
    dispatched = {e["data"]["row_id"] for e in dispatches}
    if (len(dispatches) != len(dispatched)
            or any(e["id"] != "dispatch:" + e["data"]["row_id"] for e in dispatches)):
        raise ValueError("Duplicate or mismatched dispatch event")
    receipts = {e["data"]["row_id"]: e["data"]["payload"] for e in events if e["data"].get("kind") == "row"}
    if not set(receipts) <= dispatched <= set(all_ids):
        raise ValueError("Receipt/dispatch inventory mismatch")
    dispatch_seq = {e["data"]["row_id"]: e["seq"] for e in dispatches}
    if any(dispatch_seq[e["data"]["row_id"]] >= e["seq"] for e in events if e["data"].get("kind") == "row"):
        raise ValueError("Receipt precedes its dispatch")
    raw_files = {p.relative_to(out).as_posix() for p in (out / "rows").rglob("*") if p.is_file()}
    capture_files = {p.relative_to(out).as_posix() for p in (out / "residuals").rglob("*") if p.is_file()}
    if raw_files != {"rows/" + rid + ".json" for rid in receipts}:
        raise ValueError("Unreceipted, missing or unplanned raw row")
    rows, captures = [], set()
    for rid, receipt in receipts.items():
        path = out / ("rows/" + rid + ".json")
        if (set(receipt) != {"path", "sha256"} or receipt["path"] != path.relative_to(out).as_posix()
                or path.is_symlink() or not path.resolve().is_relative_to(out.resolve())
                or sha(path) != receipt["sha256"]):
            raise ValueError("Raw row hash/path mismatch")
        row = json.loads(path.read_text())
        if rid == "qualification-live":
            validate_qualification(row, plan_sha256, freeze_commit)
            continue
        validate_row(row, expected[rid], inventory[expected[rid]["id"]],
                     plan_sha256=plan_sha256, freeze_commit=freeze_commit)
        validate_capture(out, row)
        rows.append(row)
        captures.add(row["capture"]["path"])
    if capture_files != captures:
        raise ValueError("Missing, orphaned or unplanned residual capture")
    if sum(row["capture"]["bytes"] for row in rows) > MAX_CAPTURE_BYTES:
        raise ValueError("Residual capture inventory exceeds 400 MB bound")
    if complete and (set(receipts) != set(all_ids) or dispatched != set(all_ids)):
        raise ValueError("Incomplete 224-row inventory")
    return rows


def validate_qualification(row, plan_sha256, freeze_commit):
    if (set(row) != {"id", "plan_sha256", "freeze_commit", "pass", "checks", "token_ids"}
            or row["id"] != "qualification-live" or row["plan_sha256"] != plan_sha256
            or row["freeze_commit"] != freeze_commit or row["pass"] is not True
            or row["checks"] != {"clean_identity": True, "activation_identity": True,
                                 "no_edit": True, "hook_removed": True}
            or any(value is not True for value in row["checks"].values())
            or not isinstance(row["token_ids"], list) or not row["token_ids"]
            or any(type(t) is not int or t < 0 for t in row["token_ids"])):
        raise ValueError("Invalid or failed live qualification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    rows = audit_run(args.run, plan, sha(args.plan), args.freeze)
    print(exposure.canonical(summarize(rows, plan, plan_sha256=sha(args.plan), freeze_commit=args.freeze)))


if __name__ == "__main__":
    main()
