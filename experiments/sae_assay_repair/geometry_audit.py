"""Portable post-outcome arithmetic diagnostic; NumPy and stdlib only.

python -m experiments.sae_assay_repair.geometry_audit --run RUN --out fresh.json

Reads worker receipts.jsonl, every receipted rows/*.json, and target-q90.json
when available. No controller logs, source checkout, weights, GPU, runtime
imports, or network are needed. Run on a stable retrieved snapshot. Output must
be fresh and outside RUN. This does not change or certify scientific gates.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import numpy as np


OPERATORS = ("literal", "decoder_span", "encoder_min_norm")
EPS = np.finfo(np.float32).eps
NORM_RTOL, NORM_ATOL = 1e-5, 1e-7
LIMITS = [
    "Post-outcome arithmetic diagnostic of available rows only; no selection or gate changes.",
    "Worker chain consistency is not external authentication or proof against whole-chain replacement.",
    "Frozen plan/source, intended inventory, residual captures, lifecycle, release manifest and final completeness validation are delegated to the existing release auditor.",
    "target-q90.json is separately content-hashed, not worker-row-receipt-bound; its values are recomputed only when all declared calibration inputs are available.",
    "Saved geometry/preactivations/readouts are not independently recomputed from model/SAE weights; edited hidden vectors are unavailable.",
    "Minimum norm is conditional on the saved Gram matrix and exact linear equalities, not an impossibility bound for softer median-efficacy gates, native BF16 targets, or semantics.",
    "Position counts are descriptive and correlated within texts, not independent samples; no consciousness or natural semantic validity claim.",
]


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    _require(isinstance(value, dict), "Expected JSON object")
    _canonical(value)  # Reject NaN, infinities and overflowing JSON numbers.
    return value


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


class _Inputs:
    def __init__(self, run):
        self.run, self.hashes = Path(run), {}

    def read(self, name):
        path = self.run / name
        _require(not path.is_symlink() and path.is_file(), "Missing or symlinked input: " + name)
        raw = path.read_bytes()
        self.hashes[name] = _sha(raw)
        return raw

    def verify_unchanged(self):
        for name, digest in list(self.hashes.items()):
            _require(_sha(self.read(name)) == digest, "Input changed during audit: " + name)


def _read_rows(inputs):
    directory = inputs.run / "rows"
    _require(directory.is_dir() and not directory.is_symlink(), "Missing or symlinked rows directory")
    raw = inputs.read("receipts.jsonl")
    _require(raw.endswith(b"\n"), "Empty or truncated worker receipt ledger")
    previous, bindings, bound = None, None, set()
    seen, dispatched, rows = set(), set(), {}
    fields = {"id", "seq", "data", "plan_sha256", "freeze_commit", "previous_sha256", "sha256"}
    lines = raw.splitlines(keepends=True)
    for seq, line in enumerate(lines):
        event = _decode(line)
        _require(set(event) == fields and _canonical(event) + b"\n" == line,
                 "Malformed/noncanonical worker receipt")
        body = {k: v for k, v in event.items() if k != "sha256"}
        _require(type(event["seq"]) is int and event["seq"] == seq
                 and event["previous_sha256"] == previous and _sha(_canonical(body)) == event["sha256"],
                 "Worker receipt hash/sequence mismatch")
        pair = (event["plan_sha256"], event["freeze_commit"])
        _require(all(isinstance(v, str) and re.fullmatch(r"[0-9a-f]{%d}" % n, v)
                     for v, n in zip(pair, (64, 40))), "Invalid worker source binding")
        bindings = pair if bindings is None else bindings
        _require(pair == bindings, "Worker source binding changed")
        eid, data = event["id"], event["data"]
        _require(isinstance(eid, str) and eid and eid not in seen and isinstance(data, dict),
                 "Duplicate/malformed worker event")
        seen.add(eid)
        if seq == 0:
            ids = data.get("row_ids")
            _require(eid == "binding" and data.get("kind") == "binding" and isinstance(ids, list)
                     and all(_identifier(i) for i in ids) and ids == sorted(set(ids)),
                     "Missing/invalid worker inventory binding")
            bound = set(ids)
        elif data.get("kind") in ("row", "dispatch"):
            rid, kind = data.get("row_id"), data["kind"]
            _require(_identifier(rid) and rid in bound and eid == kind + ":" + rid,
                     "Unbound worker row/dispatch")
            if kind == "dispatch":
                _require(rid not in dispatched and rid not in rows, "Duplicate/late dispatch")
                dispatched.add(rid)
            else:
                _require(rid in dispatched and rid not in rows, "Undispatched/duplicate row")
                payload = data["payload"]
                name = "rows/" + rid + ".json"
                _require(payload["path"] == name, "Unsafe/mismatched row path")
                row_raw = inputs.read(name)
                _require(_sha(row_raw) == payload["sha256"], "Raw row hash mismatch: " + rid)
                row = _decode(row_raw)
                _require(row.get("id") == rid, "Receipt/raw row ID mismatch")
                rows[rid] = row
        previous = event["sha256"]
    _require({p.name for p in directory.iterdir()} == {rid + ".json" for rid in rows},
             "Unreceipted or missing raw rows")
    return rows, {"plan_sha256_recorded": bindings[0], "freeze_commit_recorded": bindings[1],
                  "worker_receipts_sha256": _sha(raw), "worker_tail_sha256": previous,
                  "worker_events": len(lines), "bound_inventory_count": len(bound),
                  "available_rows": len(rows), "unmaterialized_bound_ids": len(bound - rows.keys()),
                  "inflight_count": len(dispatched - rows.keys()),
                  "inflight_row_ids": sorted(dispatched - rows.keys()),
                  "scope": "available_snapshot_only_not_complete_release_certification"}


def _array(value, shape, name, boolean=False):
    a = np.asarray(value)
    _require(a.shape == shape, "Wrong shape: " + name)
    _require(a.dtype.kind == "b" if boolean else a.dtype.kind in "fiu", "Wrong type: " + name)
    _require(np.isfinite(a).all(), "Nonfinite array: " + name)
    return a if boolean else a.astype(np.float64)


class _Checks:
    def __init__(self):
        self.counts, self.errors, self.maxima = Counter(), [], {}

    def check(self, ok, name, row=""):
        self.counts[name] += 1
        if not bool(ok):
            self.errors.append({"check": name, "row_id": row})

    def equal(self, left, right, name, row=""):
        self.check(np.array_equal(left, right), name, row)

    def maximum(self, name, values, row):
        values = np.asarray(values)
        if not values.size:
            return
        value = float(np.abs(values).max())
        if name not in self.maxima or value > self.maxima[name]["value"]:
            self.maxima[name] = {"value": value, "row_id": row}


def _teacher(row, ids, checks):
    rid, result = row["id"], row["result"]
    t = result["telemetry"]
    n, k = len(result["token_ids"]), len(ids)
    _require(n > 0 and all(type(v) is int and v >= 0 for v in result["token_ids"]), "Invalid tokens: " + rid)
    checks.equal(t["feature_ids"], ids, "feature_order", rid)
    checks.equal(t["repair_operator"], row["group"], "operator_binding", rid)
    valid = _array(t["delivery"]["valid"], (n,), "valid", boolean=True)
    positions = t["position_metadata"]
    _require(len(positions) == n and all(p["token_class"] in ("special", "prompt", "generated")
                                       for p in positions), "Invalid position metadata: " + rid)
    checks.equal([p["token_id"] for p in positions], result["token_ids"], "token_alignment", rid)
    checks.equal([p["position"] for p in positions], list(range(n)), "position_alignment", rid)
    nonspecial = valid & np.array([p["token_class"] != "special" for p in positions])
    a, full = t["selected_activations"], t["full_sae"]
    values = {name: _array(a[name], (n, k), name) for name in
              ("before", "after", "requested_delta", "requested_activation")}
    values.update({name: _array(full[name], (n, k), name) for name in
                   ("fp32_preact_before", "fp32_preact_after", "ideal_fp32_before", "ideal_fp32_after", "actual_fp32_after")})
    for phase in ("before", "after"):
        checks.equal(values[phase], _array(full["full_selected_" + phase], (n, k), phase), "full_native_identity", rid)
    checks.check(np.all(values["before"] >= 0) and np.all(values["after"] >= 0), "nonnegative_native", rid)
    checks.equal(np.maximum(values["fp32_preact_before"], 0), values["ideal_fp32_before"], "before_relu", rid)
    checks.equal(np.maximum(values["fp32_preact_after"], 0), values["actual_fp32_after"], "after_relu", rid)
    for name in ("before", "fp32_preact_before"):
        checks.equal(values[name], values[name].astype(np.float32), "fp32_representable_input", rid)
    values["clean_norm"] = _array(t["delivery"]["clean_norm"], (n,), "clean_norm")
    values["requested_norm"] = _array(t["delivery"]["requested_norm"], (n,), "requested_norm")
    checks.check(np.all(values["clean_norm"] > 0) and np.all(values["requested_norm"] >= 0), "valid_norms", rid)
    _require(np.all(values["clean_norm"] > 0), "Cannot form norm ratios with nonpositive clean norm")
    return values, valid, nonspecial


def _q90(inputs, clean, ids, values, checks):
    path = inputs.run / "target-q90.json"
    if not path.exists() and not path.is_symlink():
        return None, {"status": "not_available"}
    saved = _decode(inputs.read("target-q90.json"))
    checks.equal(saved["feature_ids"], ids, "q90_feature_order")
    q = _array(saved["q90"], (len(ids),), "q90")
    _require(np.all(q >= 0) and type(saved["row_count"]) is int and saved["row_count"] > 0,
             "Invalid saved q90/count")
    calibration = [r for r in clean if r["split"] == "calibration"]
    _require(len(calibration) <= saved["row_count"], "More calibration rows than saved q90 inputs")
    info = {"status": "supplied_only_incomplete_calibration", "available_calibration_rows": len(calibration),
            "saved_calibration_rows": saved["row_count"], "saved_q90": q.tolist(),
            "sha256": inputs.hashes["target-q90.json"], "scope": "positive_valid_nonspecial_calibration"}
    if len(calibration) == saved["row_count"]:
        counts, quantiles = [], []
        for j in range(len(ids)):
            pooled = np.concatenate([values[r["id"]][0]["before"][values[r["id"]][2], j] for r in calibration])
            positive = pooled[pooled > 0]
            counts.append(len(positive))
            quantiles.append(float(np.quantile(positive, .9)) if len(positive) else None)
        checks.check(all(v is not None for v in quantiles) and np.allclose(q, quantiles, rtol=0, atol=1e-14),
                     "q90_recomputed")
        info.update(status="recomputed_from_available_calibration", recomputed_q90=quantiles,
                    positive_counts=counts)
    return q.astype(np.float32), info


def _distribution(values):
    a = np.asarray(values, dtype=np.float64)
    return {"count": int(a.size), "min": float(a.min()) if a.size else None,
            "median": float(np.median(a)) if a.size else None, "max": float(a.max()) if a.size else None}


def audit(run):
    """Return a public-path-free report; reject structurally corrupt snapshots."""
    inputs, checks = _Inputs(run), _Checks()
    rows, provenance = _read_rows(inputs)
    _require("qualification-live" in rows, "Receipted qualification-live geometry required")
    geometry = rows["qualification-live"]["geometry"]
    ids = geometry["feature_ids"]
    _require(isinstance(ids, list) and ids and all(type(i) is int and i >= 0 for i in ids)
             and len(set(ids)) == len(ids), "Invalid geometry feature IDs")
    matrices = {op: _array(geometry[name], (len(ids), len(ids)), name) for op, name in
                (("decoder_span", "encoder_decoder_response"), ("encoder_min_norm", "encoder_gram"))}
    conditions = {op: float(np.linalg.cond(m)) for op, m in matrices.items()}
    gram = matrices["encoder_min_norm"]
    checks.equal(gram, gram.T, "gram_symmetry")
    teachers = [r for rid, r in rows.items() if rid.startswith(("clean-", "edit-"))]
    clean, edits, values = [], [], {}
    for row in teachers:
        rid, mode, op, dose = row["id"], row["mode"], row["group"], row["strength"]
        _require(_identifier(row["text_id"]) and op in OPERATORS and type(dose) in (float, int)
                 and row["split"] in ("calibration", "validation"), "Invalid teacher metadata: " + rid)
        if rid.startswith("clean-"):
            checks.check(mode == "zero" and dose == 0 and op == "literal" and rid == "clean-" + row["text_id"],
                         "clean_arm_binding", rid)
            clean.append(row)
        else:
            _require(mode in ("suppression", "amplification") and dose in (.5, 1.), "Invalid edit arm: " + rid)
            checks.equal(rid, f"edit-{op}-{row['text_id']}-{mode}-{int(dose*100):03d}", "edit_arm_binding", rid)
            edits.append(row)
        values[rid] = _teacher(row, ids, checks)
    q90, q_info = _q90(inputs, clean, ids, values, checks)
    for row in clean:
        v = values[row["id"]][0]
        checks.equal(v["before"], v["after"], "clean_native_identity", row["id"])
        checks.equal(v["fp32_preact_before"], v["fp32_preact_after"], "clean_preact_identity", row["id"])
        checks.equal(v["requested_delta"], np.zeros_like(v["before"]), "clean_zero_request", row["id"])
        checks.equal(v["requested_activation"], v["before"], "clean_target_identity", row["id"])
        checks.equal(v["requested_norm"], np.zeros_like(v["requested_norm"]), "clean_zero_norm", row["id"])
    norm_groups, arms = defaultdict(list), Counter()
    edit_coordinates = repair_coordinates = 0
    for row in edits:
        rid, op, mode, dose = row["id"], row["group"], row["mode"], row["strength"]
        t = row["result"]["telemetry"]
        full = t["full_sae"]
        v, valid, nonspecial = values[rid]
        paired = "clean-" + row["text_id"]
        _require(paired in values, "Missing paired clean row: " + rid)
        checks.equal(row["result"]["token_ids"], rows[paired]["result"]["token_ids"], "paired_tokens", rid)
        for name in ("before", "fp32_preact_before", "clean_norm"):
            checks.equal(v[name], values[paired][0][name], "paired_" + name, rid)
        checks.equal(valid, values[paired][1], "paired_valid_mask", rid)
        checks.equal(nonspecial, values[paired][2], "paired_nonspecial_mask", rid)
        z, p = v["before"].astype(np.float32), v["fp32_preact_before"].astype(np.float32)
        if mode == "suppression":
            delta, target, eligible = -np.float32(dose)*z, (1-np.float32(dose))*z, z > 0
            checks.check(t["q90"] is None, "suppression_no_q90", rid)
        else:
            _require(q90 is not None, "Amplification requires saved target-q90.json")
            checks.equal(t["q90"], q90, "amplification_q90", rid)
            delta = np.float32(dose) * np.maximum(q90-z, np.float32(0))
            target, eligible = z + delta, delta > 0
        checks.equal(v["requested_delta"], delta, "activation_delta", rid)
        checks.equal(v["requested_activation"], target, "activation_target", rid)
        edit_coordinates += z.size
        arms[f"{row['split']}/{op}/{mode}/{dose:g}"] += 1
        if op == "literal":
            product = delta.astype(np.float64) @ matrices["decoder_span"].T
        else:
            desired = np.where(eligible, target, p)
            shift = desired - p
            checks.equal(_array(full["repair_eligible"], z.shape, "eligible", boolean=True), eligible, "repair_eligible", rid)
            checks.equal(_array(full["repair_desired_preact"], z.shape, "desired_preact"), desired, "preact_target", rid)
            checks.equal(_array(full["repair_requested_preact_delta"], z.shape, "shift"), shift, "preact_shift", rid)
            matrix = matrices[op]
            _require(np.isfinite(conditions[op]), "Singular used solve matrix: " + op)
            coef = _array(full["repair_solve_coefficients"], z.shape, "coefficients")
            product = coef @ matrix.T
            residual = product - shift.astype(np.float64)
            recorded = _array(full["repair_solve_residual"], z.shape, "solve_residual")
            k = len(ids)
            bound = k*EPS/(1-k*EPS) * (np.abs(coef) @ np.abs(matrix).T)
            bound += EPS*(np.abs(product) + np.abs(shift)) + np.finfo(np.float32).tiny
            checks.check(np.all(np.abs(residual-recorded) <= bound), "recorded_solve_roundoff", rid)
            checks.check(np.all(np.abs(residual) <= .001*np.maximum(1, np.abs(shift)))
                         and np.all(np.abs(recorded) <= .001*np.maximum(1, np.abs(shift))), "solve_numerical_tolerance", rid)
            for name, a in (("solve_reconstructed", residual), ("solve_recorded", recorded),
                            ("solve_recorded_discrepancy", residual-recorded)):
                checks.maximum(name, a, rid)
            repair_coordinates += z.size
            if op == "encoder_min_norm":
                _require(np.all(np.linalg.eigvalsh(gram) > 0), "Used Gram matrix must be positive definite")
                solved = np.linalg.solve(gram, shift.astype(np.float64).T).T
                minimum = np.sqrt(np.maximum(np.einsum("ij,ij->i", shift, solved), 0))
                error = v["requested_norm"] - minimum
                positive = minimum > 0
                checks.check(np.all(np.abs(error[positive]) <= NORM_ATOL + NORM_RTOL*minimum[positive])
                             and np.all(v["requested_norm"][~positive] == 0), "minimum_norm", rid)
                checks.maximum("minimum_norm_absolute_error", error, rid)
                checks.maximum("minimum_norm_relative_error_nonzero", error[positive]/minimum[positive], rid)
                ratio = minimum/(.05*v["clean_norm"])
                for scope, mask in (("all_valid", valid), ("nonspecial_valid", nonspecial)):
                    norm_groups[f"{row['split']}/{mode}/{dose:g}/{scope}"].extend(zip(ratio[mask].tolist(), positive[mask].tolist()))
        checks.maximum(op + "_ideal_vs_geometry", v["ideal_fp32_after"] - np.maximum(p+product, 0), rid)
        checks.maximum("native_after_vs_actual_fp32_after", v["after"] - v["actual_fp32_after"], rid)
        checks.maximum(op + "_actual_vs_ideal_fp32_after", v["actual_fp32_after"] - v["ideal_fp32_after"], rid)
    norm_report = {}
    for key, entries in sorted(norm_groups.items()):
        ratios = [r for r, _ in entries]
        norm_report[key] = {"ratio_all": _distribution(ratios),
                            "ratio_nonzero": _distribution([r for r, p in entries if p]),
                            "above_five_percent_clean": sum(r > 1 for r in ratios)}
    inputs.verify_unchanged()
    _require({p.name for p in (inputs.run / "rows").iterdir()} == {rid + ".json" for rid in rows},
             "Rows changed during audit")
    _require((inputs.run / "target-q90.json").exists() == (q90 is not None), "q90 changed during audit")
    return {"schema": "sae_assay_repair_geometry_audit_v1", "pass": not checks.errors,
            "provenance": provenance, "input_sha256": dict(sorted(inputs.hashes.items())),
            "counts": {"clean": len(clean), "edits": len(edits), "qualification": 1,
                       "other_rows_hash_checked_only": len(rows)-len(teachers)-1,
                       "edit_coordinates": edit_coordinates, "repair_coordinates": repair_coordinates},
            "available_arms": dict(sorted(arms.items())), "feature_ids": ids, "q90": q_info,
            "geometry_conditions": {op: v if np.isfinite(v) else None for op, v in conditions.items()},
            "max_absolute_errors": checks.maxima,
            "minimum_norm_ratios_descriptive_only": norm_report,
            "tolerances": {"solve": "0.001 * max(1, abs(u)); engineering arithmetic only",
                           "recorded_residual": "gamma_k * (abs(a) @ abs(M).T) + eps32*(abs(Ma)+abs(u)) + tiny32",
                           "minimum_norm_rtol": NORM_RTOL, "minimum_norm_atol": NORM_ATOL,
                           "ideal_geometry_and_native_readout_gaps": "descriptive only, not solve residual tests"},
            "check_counts": dict(checks.counts), "errors": checks.errors, "limitations": LIMITS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        _require(args.out.resolve() != args.run.resolve() and args.run.resolve() not in args.out.resolve().parents,
                 "Output must be outside the immutable input run")
        _require(not args.out.exists() and not args.out.is_symlink(), "Output must be a fresh JSON file")
        result = audit(args.run)
        with args.out.open("x", encoding="ascii") as handle:
            handle.write(_canonical(result).decode("ascii") + "\n")
    except (OSError, ValueError, KeyError, TypeError, np.linalg.LinAlgError) as exc:
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Malformed or unavailable input/output"
        print(json.dumps({"pass": False, "error": message, "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({"pass": result["pass"], "counts": result["counts"],
                      "inflight_count": result["provenance"]["inflight_count"], "errors": result["errors"]}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
