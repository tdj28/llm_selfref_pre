"""Independent CPU arithmetic on retained exposure/pilot evidence, not human validation.

No scientific implementation is imported. Clean counts come from raw JSON;
delivery comes from CPU float64 NumPy arithmetic on retained safetensors.
This does not verify model execution, re-encode an SAE, or replace receipt audits.
Exit 0 means the checked arithmetic agrees, NOT that scientific gates passed.

Example (use a new ignored output filename):
  python scripts/check_sae_exposure_arithmetic.py --plan PLAN.json --run RUN \
      --freeze COMMIT --out data/sae_assay_exposure/arithmetic_checks/check.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FEATURES = (30032, 58667, 22004, 30686, 41533, 23893)
MODES = ("native_zero", "precision_sham", "suppression", "amplification")
SPLITS = ("discovery", "validation", "representative")
RTOL, ATOL = 1e-10, 1e-12


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON constant: " + value)

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=nonfinite)


def compare(expected, observed, label, errors):
    """Compare specified fields only; floats tolerate CPU reduction order, counts do not."""
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            errors.append(label + ": expected object")
            return
        for key, value in expected.items():
            if key not in observed:
                errors.append(label + "." + key + ": missing")
            else:
                compare(value, observed[key], label + "." + key, errors)
    elif isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(observed):
            errors.append(label + ": list length/type mismatch")
        else:
            for index, (left, right) in enumerate(zip(expected, observed)):
                compare(left, right, f"{label}[{index}]", errors)
    else:
        equal = type(expected) is type(observed) and expected == observed
        if isinstance(expected, float):
            equal = (type(observed) in (int, float) and math.isfinite(observed)
                     and math.isclose(expected, observed, rel_tol=RTOL, abs_tol=ATOL))
        if not equal:
            errors.append(f"{label}: reconstructed {expected!r}, recorded {observed!r}")


def finite_array(value, shape, name, *, nonnegative=False):
    result = np.asarray(value)
    require(result.shape == shape and result.dtype.kind in "fi", name + ": shape/numeric type")
    require(bool(np.isfinite(result).all()), name + ": nonfinite")
    require(not nonnegative or bool((result >= 0).all()), name + ": negative")
    return result.astype(np.float64)


def clean_counts(plan, rows):
    items = {item["id"]: item for item in plan["texts"]}
    certificates = {item["id"]: item for item in plan["certificate"]["items"]}
    require(len(items) == len(plan["texts"]) and set(items) == set(certificates), "Invalid text inventory")
    require(len(certificates) == len(plan["certificate"]["items"]), "Duplicate certificate")
    by_id = {}
    for row in rows:
        rid = row["text_id"]
        require(rid in items and rid not in by_id, "Duplicate/unplanned clean row")
        item, cert = items[rid], certificates[rid]
        require(row["id"] == "clean-" + rid and row["feature_ids"] == list(FEATURES), "Clean identity/features")
        require(row["family"] == item["family"] and row["split"] == item["split"], "Clean split/family")
        require(row["token_ids"] == cert["token_ids"] and
                row["special_tokens_mask"] == cert["special_tokens_mask"], "Clean frozen tokens/mask")
        mask = cert["special_tokens_mask"]
        require(len(mask) == len(row["token_ids"]) and all(type(v) is bool for v in mask)
                and all(type(v) is bool for v in row["special_tokens_mask"])
                and not all(mask), "Invalid special mask")
        require(all(type(v) is int for v in row["token_ids"]), "Invalid token IDs")
        require(set(row["activations"]) == {str(f) for f in FEATURES}, "All six clean features required")
        valid = ~np.asarray(mask, dtype=bool)
        counts = {str(f): int(((finite_array(row["activations"][str(f)], (len(mask),),
                    "clean activations", nonnegative=True) > 0) & valid).sum()) for f in FEATURES}
        by_id[rid] = {"family": item["family"], "split": item["split"],
                      "nonspecial_positions": int(valid.sum()), "positive_positions": counts}
    require(set(by_id) == set(items), "Incomplete clean panel; missing rows are not zero exposure")

    def panel(ids):
        features = []
        for feature in FEATURES:
            active = [rid for rid in ids if by_id[rid]["positive_positions"][str(feature)] > 0]
            count = sum(by_id[rid]["positive_positions"][str(feature)] for rid in ids)
            features.append({"feature_id": feature, "active_positions": count, "active_texts": len(active),
                "active_families": len({by_id[rid]["family"] for rid in active}),
                "exposure_minimum_met": count >= 100 and len(active) >= 6})
        return {"text_count": len(ids), "nonspecial_positions": sum(by_id[r]["nonspecial_positions"] for r in ids),
                "features": features, "all_six_exposure_minima_met": all(f["exposure_minimum_met"] for f in features)}

    split_ids = {split: [rid for rid, r in by_id.items() if r["split"] == split] for split in SPLITS}
    require(sum(map(len, split_ids.values())) == len(by_id), "Unknown clean split")
    selections, union = [], set()
    for feature in FEATURES:
        chosen, families = [], Counter()
        for rid in sorted(split_ids["discovery"], key=lambda r: (-by_id[r]["positive_positions"][str(feature)], r)):
            family = by_id[rid]["family"]
            if by_id[rid]["positive_positions"][str(feature)] == 0 or families[family] == 6:
                continue
            chosen.append(rid)
            families[family] += 1
            if len(chosen) == 12:
                break
        union.update(chosen)
        selections.append({"feature_id": feature, "selected_ids": chosen, "unfilled_slots": 12 - len(chosen)})
    panels = {split: panel(ids) for split, ids in split_ids.items()}
    selected = panel(sorted(union))
    return {"rows": len(rows), "split_counts": {s: len(ids) for s, ids in split_ids.items()},
            "panels": panels, "discovery": {"per_feature": selections, "selected_ids": sorted(union),
                "screened_panel": panels["discovery"], "selected_panel": selected},
            "exposure_minima_met": selected["all_six_exposure_minima_met"] and
                panels["validation"]["all_six_exposure_minima_met"]}, by_id


def delivery_metrics(pre, requested, post):
    h, r, p = [np.asarray(v, dtype=np.float64) for v in (pre, requested, post)]
    require(h.ndim == 3 and h.shape[0] == 1 and h.shape == r.shape == p.shape, "State shapes differ")
    require(all(bool(np.isfinite(v).all()) for v in (h, r, p)), "Nonfinite state")
    h, r, p = [v[0] for v in (h, r, p)]
    actual = p - h
    norm = lambda v: np.sqrt(np.sum(v * v, axis=1, dtype=np.float64))
    rn, an, hn = norm(r), norm(actual), norm(h)
    require(bool((hn > 0).all()), "Nonpositive clean norm")
    nz = rn > 0
    tiny = np.finfo(np.float64).tiny
    cosine = np.sum(r * actual, axis=1) / np.maximum(rn * an, tiny)
    error = norm(actual - r) / np.maximum(rn, tiny)
    return {"requested_norm": rn.tolist(), "realized_norm": an.tolist(), "clean_norm": hn.tolist(),
            "nonzero_requested": nz.tolist(), "identity": (p == h).all(axis=1).tolist(),
            "cosine": np.where(nz, np.clip(cosine, -1, 1), 1.).tolist(),
            "relative_error": np.where(nz, error, 0.).tolist(),
            "realized_clean_ratio": (an / hn).tolist()}


def fraction_report(passing, denominator):
    fraction = passing / denominator if denominator else None
    return {"passing_positions": passing, "denominator": denominator, "fraction": fraction,
            "pass": fraction is not None and fraction >= .95}


def precision_counts(records):
    """Records contain tensor-reconstructed metrics/readouts, never JSON delivery inputs."""
    modes, zero_accounting = {}, {}
    for mode in MODES:
        group = [r for r in records if r["mode"] == mode]
        require(bool(group), "Missing precision mode: " + mode)
        valid = np.concatenate([~np.asarray(r["special_tokens_mask"], dtype=bool) for r in group])
        metrics = {k: np.concatenate([r["delivery"][k] for r in group]) for k in group[0]["delivery"]}
        request_nz = valid & (metrics["requested_norm"] > 0)
        realized_nz = valid & (metrics["realized_norm"] > 0)
        good = request_nz & (metrics["cosine"] >= .95) & (metrics["relative_error"] <= .20)
        norm_good = realized_nz & (metrics["realized_clean_ratio"] <= .05)
        count = lambda mask: int(mask.sum())
        output = {"all_positions": len(valid), "nonspecial_positions": count(valid),
            "nonzero_requests": count(request_nz), "zero_requests": count(valid & ~request_nz),
            "fidelity": fraction_report(count(good), count(request_nz)),
            "norm": fraction_report(count(norm_good), count(realized_nz)),
            "norm_all_nonspecial_secondary": {"passing_positions": count(valid & (metrics["realized_clean_ratio"] <= .05)),
                                              "denominator": count(valid)}, "features": {}}
        zero_accounting[mode] = {"zero_realized": count(valid & ~realized_nz),
            "nonzero_request_zero_realized": count(request_nz & ~realized_nz),
            "zero_request_nonzero_realized": count(realized_nz & ~request_nz)}
        before, promoted, after = [np.concatenate([r[key] for r in group]) for key in
                                   ("native_before", "promoted_before", "promoted_after")]
        for j, feature in enumerate(FEATURES):
            active = valid & (before[:, j] > 0)
            paired = active & (promoted[:, j] > 0)
            invalid = active & ~paired
            delta = (after[:, j] - promoted[:, j]) * (-1 if mode == "suppression" else 1)
            median = lambda values: float(statistics.median(values)) if len(values) else None
            output["features"][str(feature)] = {
                "nonspecial_denominator": count(valid), "native_active_positions": count(active),
                "promoted_active_positions": count(valid & (promoted[:, j] > 0)),
                "native_active_texts": sum(any(z[j] > 0 and not special for z, special in
                    zip(row["native_before"], row["special_tokens_mask"])) for row in group),
                "support_disagreements": count(valid & ((before[:, j] > 0) != (promoted[:, j] > 0))),
                "readout_shift_mean": float(np.mean((promoted[:, j] - before[:, j])[valid])),
                "primary_eligible_native_active_positions": count(active),
                "paired_promoted_defined_positions": count(paired), "paired_promoted_undefined_positions": count(invalid),
                "native_anchor_after_ratio_median": median(after[active, j] / before[active, j]),
                "paired_delta_over_requested_native_change_median": median(delta[active] / (.75 * before[active, j])),
                "paired_promoted_after_ratio_median": None if invalid.any() else median(after[paired, j] / promoted[paired, j]),
                "paired_promoted_defined_only_after_ratio_median": median(after[paired, j] / promoted[paired, j]),
                "paired_promoted_fraction_median": None if invalid.any() else median(delta[paired] / promoted[paired, j]),
                "efficacy_qualified": False}
        modes[mode] = output
    return {"modes": modes}, zero_accounting


class Evidence:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.hashes = {}

    def path(self, relative):
        path = self.root / relative
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts, "Unsafe evidence path")
        require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlinked evidence")
        require(path.is_file() and path.resolve().is_relative_to(self.root), "Missing evidence: " + relative)
        digest = sha(path)
        require(relative not in self.hashes or self.hashes[relative] == digest, "Evidence changed during check")
        self.hashes[relative] = digest
        return path

    def json(self, relative):
        return read_json(self.path(relative))

    def tensors(self, relative, digest):
        from safetensors.torch import load_file
        path = self.path(relative)
        require(self.hashes[relative] == digest, "Capture hash mismatch: " + relative)
        return load_file(str(path), device="cpu")


def tensor_record(evidence, row, clean, certificate, errors):
    import torch
    n = len(certificate["token_ids"])
    capture = row["capture"]
    tensors = evidence.tensors("precision_pilot/" + capture["path"], capture["sha256"])
    require(set(tensors) == set(capture["tensors"]), "Tensor metadata inventory mismatch")
    for key, value in tensors.items():
        require(capture["tensors"][key] == {"shape": list(value.shape), "dtype": str(value.dtype)}, "Tensor metadata mismatch")
        require(bool(torch.isfinite(value).all()), "Nonfinite captured tensor")
    valid = [not m for m in certificate["special_tokens_mask"]]
    require(tensors["valid"].dtype == torch.bool and tensors["valid"].tolist() == [valid], "Captured frozen mask differs")
    require(tensors["token_ids"].dtype == torch.int64 and
            tensors["token_ids"].tolist() == [certificate["token_ids"]], "Captured frozen tokens differ")
    pre, request, post = [tensors[k] for k in ("pre", "requested", "post")]
    require(pre.ndim == 3 and tuple(pre.shape[:2]) == (1, n) and pre.shape == request.shape == post.shape, "State shape mismatch")
    require(pre.dtype == torch.bfloat16 and request.dtype == torch.float32 and
            post.dtype == (torch.bfloat16 if row["mode"] == "native_zero" else torch.float32), "State dtype mismatch")
    require(row["test_only"] or pre.shape[-1] == 8192, "Production state width mismatch")
    arrays = [v.double().numpy() for v in (pre, request, post)]
    require(not np.any(arrays[1][0][~np.asarray(valid)]), "Nonzero request on special token")
    metrics = delivery_metrics(*arrays)
    compare(metrics, row["delivery"], row["row_id"] + ".delivery", errors)
    if row["mode"] in MODES[:2]:
        require(not any(metrics["nonzero_requested"]) and all(metrics["identity"]), "Native/sham boundary not identity")
    reference = row["clean_exposure"]
    require(reference == {"row_path": "rows/" + clean["id"] + ".json",
        "row_sha256": evidence.hashes["rows/" + clean["id"] + ".json"],
        "capture_path": clean["capture"]["path"], "capture_sha256": clean["capture"]["sha256"]}, "Clean reference binding mismatch")
    baseline = evidence.tensors(clean["capture"]["path"], clean["capture"]["sha256"])
    require(baseline["hidden"].dtype == torch.bfloat16 and torch.equal(pre, baseline["hidden"])
            and baseline["token_ids"].tolist() == [certificate["token_ids"]], "Pilot pre differs from clean capture")
    record = {**row, "delivery": metrics}
    for key in ("native_before", "promoted_before", "promoted_after"):
        value = tensors[key]
        require(value.dtype == torch.float32 and tuple(value.shape) == (n, 6), "Readout dtype/shape mismatch")
        record[key] = finite_array(value.double().numpy(), (n, 6), key, nonnegative=True)
        require(record[key].tolist() == row[key], "Readout differs from raw JSON: " + key)
    native = [[clean["activations"][str(f)][i] for f in FEATURES] for i in range(n)]
    require(record["native_before"].tolist() == native, "Native anchor differs from clean raw activations")
    return record


def verify(plan_path, run, freeze):
    plan_path = Path(plan_path)
    plan, plan_hash = read_json(plan_path), sha(plan_path)
    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "Exact execution freeze required")
    require(plan["target_feature_ids"] == list(FEATURES), "All six frozen feature IDs required")
    rules = plan["rules"]
    require(all(rules[k] == v for k, v in {"minimum_positions_per_feature": 100,
        "minimum_distinct_texts_per_feature": 6, "per_feature_limit": 12, "per_feature_family_cap": 6}.items()), "Exposure thresholds changed")
    config = plan["precision_pilot"]
    require(config["modes"] == list(MODES) and config["change"] == .75 and config["fidelity"] ==
        {"minimum_fraction": .95, "minimum_cosine": .95, "maximum_relative_error": .20} and
        config["norm"] == {"minimum_fraction": .95, "maximum_clean_ratio": .05}, "Precision thresholds changed")
    require(len(plan["texts"]) == 224 and len(config["texts"]) == 12, "Full 224/12-text design required")
    families, pilot_texts = set(), []
    for item in plan["texts"]:
        if item["split"] == "discovery" and item["family"] not in families:
            pilot_texts.append(item)
            families.add(item["family"])
    require(config["texts"] == pilot_texts, "Pilot is not first discovery text per family")
    evidence, errors = Evidence(run), []
    binding = {"plan_sha256": plan_hash, "freeze_commit": freeze}
    clean = []
    for item in plan["texts"]:
        row = evidence.json("rows/clean-" + item["id"] + ".json")
        require(all(row[k] == v for k, v in binding.items()), "Clean plan/freeze mismatch")
        clean.append(row)
    expected_clean = {"clean-" + item["id"] + ".json" for item in plan["texts"]} | {"qualification-live.json"}
    require({p.name for p in (evidence.root / "rows").iterdir()} == expected_clean, "Unexpected/missing clean row files")
    clean_summary, per_text = clean_counts(plan, clean)
    compare({**binding, **clean_summary}, evidence.json("summary.json"), "clean_summary", errors)
    by_id = {r["text_id"]: r for r in clean}
    certs = {r["id"]: r for r in plan["certificate"]["items"]}
    records, checks = [], []
    expected_paths, expected_captures = set(), set()
    test_only = set()
    for ordinal, (item, mode) in enumerate((item, mode) for item in config["texts"] for mode in MODES):
        relative = f"precision_pilot/rows/{ordinal:03d}.json"
        expected_paths.add(Path(relative).name)
        row = evidence.json(relative)
        rid = "precision-pilot:" + item["id"] + ":" + mode
        cert = certs[item["id"]]
        fixed = {**binding, "row_id": rid, "text_id": item["id"], "family": item["family"],
                 "split": "discovery", "mode": mode, "feature_ids": list(FEATURES),
                 "token_ids": cert["token_ids"], "special_tokens_mask": cert["special_tokens_mask"]}
        require(all(row[k] == v for k, v in fixed.items()), "Precision identity/mask/binding mismatch: " + rid)
        require(type(row["test_only"]) is bool, "Missing synthetic/production distinction")
        test_only.add(row["test_only"])
        require(row["capture"]["path"] == f"tensors/{ordinal:03d}.safetensors", "Capture inventory mismatch")
        expected_captures.add(f"{ordinal:03d}.safetensors")
        before = len(errors)
        record = tensor_record(evidence, row, by_id[item["id"]], cert, errors)
        records.append(record)
        checks.append({"row_id": rid, "delivery_arrays_agree": len(errors) == before})
    require(len(test_only) == 1, "Mixed synthetic/production pilot")
    for item in config["texts"]:
        group = [r for r in records if r["text_id"] == item["id"]]
        for key in ("native_before", "promoted_before"):
            require(all(np.array_equal(r[key], group[0][key]) for r in group), "Paired readout baselines differ")
    require({p.name for p in (evidence.root / "precision_pilot/rows").iterdir()} == expected_paths, "Precision row inventory differs")
    require({p.name for p in (evidence.root / "precision_pilot/tensors").iterdir()} == expected_captures, "Precision capture inventory differs")
    precision, zero_accounting = precision_counts(records)
    precision.update(full_model_forwards=48, text_count=12, test_only=next(iter(test_only)))
    for path in ("precision_pilot/summary.json", "precision-pilot-summary.json"):
        compare(precision, evidence.json(path), path, errors)
    for path, digest in list(evidence.hashes.items()):
        require(sha(evidence.root / path) == digest, "Input changed during verification: " + path)
    require(sha(plan_path) == plan_hash, "Plan changed during verification")
    return {"schema": "sae_exposure_independent_arithmetic_v1", "arithmetic_matches": not errors,
        "scope": "Automated independent arithmetic, not human validation, execution attestation or assay qualification",
        **binding, "verifier_sha256": sha(__file__), "float_comparison": {"rtol": RTOL, "atol": ATOL},
        "clean": clean_summary, "clean_per_text": per_text, "precision": precision,
        "zero_accounting": zero_accounting, "delivery_checks": checks, "mismatches": errors,
        "input_sha256": evidence.hashes,
        "not_checked": ["receipt chains", "model forwards/dtype delivery", "SAE encoding from weights",
                        "NLL/KL", "scientific or behavioral qualification"]}


def output_path(path, run):
    path = Path(path).absolute()
    require(not path.exists() and not any(p.is_symlink() for p in (path, *path.parents)), "Output must be new and not symlinked")
    path = path.resolve()
    require(path.is_relative_to(ROOT) and not path.is_relative_to(Path(run).resolve()), "Output must be outside raw run, inside repo")
    ignored = subprocess.run(["git", "check-ignore", "-q", "--", str(path)], cwd=ROOT, check=False)
    require(ignored.returncode == 0, "Output must be ignored; do not change release allowlists")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("plan", "run", "freeze", "out"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    out = output_path(args.out, args.run)
    try:
        result = verify(args.plan, args.run, args.freeze)
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {"schema": "sae_exposure_independent_arithmetic_v1", "arithmetic_matches": False,
                  "incomplete_or_invalid": True, "error": str(error),
                  "scope": "No arithmetic clearance; missingness is not zero exposure"}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"arithmetic_matches": result["arithmetic_matches"], "output": str(out)}))
    return 0 if result["arithmetic_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
