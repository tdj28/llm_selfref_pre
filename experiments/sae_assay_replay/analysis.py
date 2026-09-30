"""Strict saved-row audit and descriptive native-SAE replay components.

No weight loading, inference, network, output writes, or behavioral qualification.
Use a stable retrieved snapshot: --run RUN --plan PLAN [--partial].
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

import numpy as np

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_repair.feasibility import active_support_projection

ROOT = Path(__file__).resolve().parents[2]
MODES = ("zero", "suppression", "amplification")
SPLITS = ("calibration", "validation")
SCOPE = (
    "Descriptive engineering on previously observed historical splits, not fresh "
    "validation or behavioral assay qualification. Tokens are correlated within "
    "texts; no token-independent confidence intervals are computed."
)
MATRICES = (
    "before", "after", "selected_before", "selected_after", "fp32_preact_before",
    "fp32_preact_ideal", "fp32_preact_after", "requested_activation_delta",
    "projection_coefficients", "continuous_predicted_activation",
)
VECTORS = (
    "projection_scale", "continuous_norm", "non_target_change_norm",
    "reconstruction_relative_error", "requested_norm", "realized_norm",
    "clean_norm", "cosine", "relative_error",
)
COUNTS = ("l0_before", "l0_after", "non_target_changed_count", "non_target_activity_changes")
BOOLS = ("nonzero_requested", "identity")
ROW_FIELDS = {
    "id", "text_id", "split", "corpus", "source_row_sha256", "capture_sha256",
    "token_ids", "position_metadata", "arms", "elapsed_seconds",
}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value, width=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % width, value) is not None


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    _canonical(value)
    _require(isinstance(value, dict), "Expected JSON object")
    return value


def _ids(ids):
    _require(isinstance(ids, list) and 1 <= len(ids) <= 6
             and all(type(i) is int and 0 <= i < 65536 for i in ids)
             and len(set(ids)) == len(ids), "Invalid ordered feature IDs")


def _array(value, shape, name, kind="number"):
    # Inspect leaves before NumPy can silently coerce mixed bool/numeric arrays.
    def leaves(x, dimensions):
        if not dimensions:
            valid = (type(x) is bool if kind == "bool" else type(x) is int
                     if kind == "int" else type(x) in (int, float))
            _require(valid, "Invalid scalar type: " + name)
            return
        _require(isinstance(x, list) and len(x) == dimensions[0], "Wrong shape: " + name)
        for item in x:
            leaves(item, dimensions[1:])
    leaves(value, shape)
    a = np.asarray(value, dtype=bool if kind == "bool" else np.float64)
    _require(np.isfinite(a).all(), "Nonfinite array: " + name)
    return a


def _equal(a, b, name):
    _require(np.array_equal(a, b), "Inconsistent " + name)


def _positions(row):
    tokens, positions = row["token_ids"], row["position_metadata"]
    _require(isinstance(tokens, list) and tokens
             and all(type(t) is int and 0 <= t < 128256 for t in tokens), "Invalid token IDs")
    _require(isinstance(positions, list) and len(positions) == len(tokens), "Invalid position metadata")
    for i, (token, p) in enumerate(zip(tokens, positions)):
        _require(isinstance(p, dict) and type(p.get("position")) is int and p["position"] == i
                 and type(p.get("token_id")) is int and p["token_id"] == token
                 and p.get("token_class") in ("special", "prompt", "generated"), "Token/position mismatch")
        if "terminal_observation_only" in p:
            _require(type(p["terminal_observation_only"]) is bool, "Invalid terminal flag")
        if "origin" in p:
            _require(p["origin"] in ("prompt", "generated"), "Invalid position origin")
    return np.array([p["token_class"] != "special" for p in positions])


def _validate_replay(row, ids):
    _ids(ids)
    _require(isinstance(row, dict) and set(row) == ROW_FIELDS, "Unexpected replay row schema")
    _canonical(row)
    _require(isinstance(row["text_id"], str)
             and re.fullmatch(r"[A-Za-z0-9_-]+", row["text_id"]) is not None
             and row["id"] == "replay-" + row["text_id"], "Invalid replay ID")
    _require(row["split"] in SPLITS and isinstance(row["corpus"], str) and row["corpus"], "Invalid row metadata")
    _require(all(_digest(row[k]) for k in ("source_row_sha256", "capture_sha256")), "Invalid source hash")
    _require(type(row["elapsed_seconds"]) in (int, float) and row["elapsed_seconds"] > 0,
             "Elapsed time must be positive and finite")
    nonspecial = _positions(row)
    n, k = len(nonspecial), len(ids)
    _require(isinstance(row["arms"], dict) and set(row["arms"]) == set(MODES), "All three arms are required")
    arrays = {}
    for mode in MODES:
        arm = row["arms"][mode]
        _require(isinstance(arm, dict) and set(arm) == set(MATRICES + VECTORS + COUNTS + BOOLS),
                 "Unexpected arm schema: " + mode)
        a = {name: _array(arm[name], (n, k), name) for name in MATRICES}
        a.update({name: _array(arm[name], (n,), name) for name in VECTORS})
        a.update({name: _array(arm[name], (n,), name, "int") for name in COUNTS})
        a.update({name: _array(arm[name], (n,), name, "bool") for name in BOOLS})
        arrays[mode] = a
        for name in ("before", "after", "selected_before", "selected_after", "continuous_predicted_activation"):
            _require((a[name] >= 0).all(), "Negative activation: " + name)
        for name in set(VECTORS) - {"cosine", "projection_scale", "clean_norm"}:
            _require((a[name] >= 0).all(), "Negative measurement: " + name)
        _require((a["clean_norm"] > 0).all(), "Nonpositive clean norm")
        _require(((a["projection_scale"] > 0) & (a["projection_scale"] <= 1)).all(), "Invalid projection scale")
        _require((np.abs(a["cosine"]) <= 1).all(), "Invalid cosine")
        for name in COUNTS:
            maximum = 65536 if name.startswith("l0") else 65536 - k
            _require(((a[name] >= 0) & (a[name] <= maximum)).all(), "Invalid SAE count: " + name)
        for phase in ("before", "after"):
            _require((a["l0_" + phase] >= (a[phase] > 0).sum(1)).all(), "L0 smaller than active targets")
        _require((a["non_target_activity_changes"] <= a["non_target_changed_count"]).all(), "Invalid activity-change count")
        _equal(a["non_target_change_norm"] == 0, a["non_target_changed_count"] == 0, "non-target norm/count")
        _equal(a["nonzero_requested"], a["requested_norm"] > 0, "request mask")
        _equal(a["identity"], a["realized_norm"] == 0, "identity/realized norm")
        expected_delta = np.float32(0 if mode == "zero" else .75 if mode == "amplification" else -.75) * a["before"].astype(np.float32)
        _equal(a["requested_activation_delta"], expected_delta, "original intended activation delta")
        inactive = ~(a["before"] > 0).any(1)
        no_request = ~a["nonzero_requested"]
        _require(a["identity"][no_request].all(), "Zero request changed hidden state")
        _require(no_request[inactive].all(), "All-inactive support must be a no-op")
        _require((a["projection_coefficients"][inactive] == 0).all()
                 and (a["continuous_norm"][inactive] == 0).all()
                 and (a["projection_scale"][inactive] == 1).all(), "Inactive projection must be zero")
        _require((a["continuous_norm"] <= .04 * a["clean_norm"] + 1e-6 * a["clean_norm"]).all(),
                 "Continuous norm cap violated")
        identity = a["identity"]
        for before, after in (("before", "after"), ("selected_before", "selected_after"),
                              ("fp32_preact_before", "fp32_preact_after"), ("l0_before", "l0_after")):
            _equal(a[before][identity], a[after][identity], "identity " + after)
        for name in ("non_target_change_norm", "non_target_changed_count", "non_target_activity_changes"):
            _require((a[name][identity] == 0).all(), "Identity has non-target drift")
        _equal(a["fp32_preact_before"][no_request], a["fp32_preact_ideal"][no_request], "zero-request ideal preactivation")
        _require((a["cosine"][no_request] == 1).all() and (a["relative_error"][no_request] == 0).all(),
                 "Incorrect zero-request fidelity conventions")
        rounded = identity & ~no_request
        _require((a["cosine"][rounded] == 0).all() and (a["relative_error"][rounded] == 1).all(),
                 "Incorrect rounded-away fidelity")
        if mode == "zero":
            _require(identity.all() and no_request.all(), "Zero arm is not exact identity")
            for name in ("projection_coefficients", "continuous_norm"):
                _require((a[name] == 0).all(), "Nonzero zero-arm " + name)
            _equal(a["continuous_predicted_activation"], a["before"], "zero prediction")
            _require((a["projection_scale"] == 1).all(), "Zero scale must be one")
        else:
            for name in ("before", "selected_before", "fp32_preact_before", "clean_norm", "l0_before",
                         "reconstruction_relative_error"):
                _equal(a[name], arrays["zero"][name], "shared arm base " + name)
    return arrays, nonspecial


def _comparison(original, replay, nonspecial):
    equal = original == replay
    old, new = original > 0, replay > 0
    return {"entries": int(equal.size), "exact_entries": int(equal.sum()),
            "exact_fraction": float(equal.mean()), "max_absolute_difference": float(np.abs(original - replay).max()),
            "active_to_inactive": int((old & ~new).sum()), "inactive_to_active": int((~old & new).sum()),
            "nonspecial_active_to_inactive": int((old & ~new & nonspecial[:, None]).sum()),
            "nonspecial_inactive_to_active": int((~old & new & nonspecial[:, None]).sum())}


def validate_row(row, source, ids):
    """Raise on technical invalidity; return historical drift, never a GPU parity gate."""
    arrays, nonspecial = _validate_replay(row, ids)
    _require(source["id"] == "clean-" + row["text_id"] and source["mode"] == "zero"
             and type(source["strength"]) in (int, float) and source["strength"] == 0, "Source is not original clean row")
    for key in ("text_id", "split", "corpus"):
        _require(row[key] == source[key], "Original metadata mismatch: " + key)
    t = source["result"]["telemetry"]
    for actual, expected, name in ((row["token_ids"], source["result"]["token_ids"], "tokens"),
                                   (row["position_metadata"], t["position_metadata"], "positions"),
                                   (ids, t["feature_ids"], "feature order")):
        _require(_canonical(actual) == _canonical(expected), "Original " + name + " mismatch")
    _require(row["capture_sha256"] == source["capture"]["sha256"], "Original capture hash mismatch")
    n, k = len(nonspecial), len(ids)
    valid = _array(t["delivery"]["valid"], (n,), "source valid", "bool")
    _require(valid.all(), "Saved clean input contains invalid/padded positions")
    native = _array(t["full_sae"]["full_selected_before"], (n, k), "original native")
    _require((native >= 0).all(), "Negative original native activation")
    _equal(native, _array(t["selected_activations"]["before"], (n, k), "source canonical"), "original canonical native")
    pre = _array(t["full_sae"]["fp32_preact_before"], (n, k), "original FP32 preactivation")
    norm = _array(t["delivery"]["clean_norm"], (n,), "original clean norm")
    _require((norm > 0).all(), "Nonpositive original clean norm")
    zero = arrays["zero"]
    pre_error = np.abs(pre - zero["fp32_preact_before"])
    _require((pre_error <= 1e-4 * np.maximum(1, np.abs(pre))).all(), "Original FP32 preactivation drift")
    norm_error = np.abs(norm - zero["clean_norm"])
    _require((norm_error <= 1e-5 * norm).all(), "Original clean norm drift")
    features = {}
    for j, feature in enumerate(ids):
        features[str(feature)] = {
            "native_before": _comparison(native[:, j:j+1], zero["before"][:, j:j+1], nonspecial),
            "original_active_nonspecial_positions": int(((native[:, j] > 0) & nonspecial).sum()),
            "replay_active_nonspecial_positions": int(((zero["before"][:, j] > 0) & nonspecial).sum()),
        }
    return {"native_before": _comparison(native, zero["before"], nonspecial),
            "zero_native": _comparison(native, zero["after"], nonspecial),
            "max_fp32_preactivation_absolute_difference": float(pre_error.max()),
            "max_clean_norm_relative_difference": float((norm_error / norm).max()), "features": features}


def _distribution(values):
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    _require(np.isfinite(a).all(), "Nonfinite derived distribution")
    result = {"count": int(a.size)}
    for name, q in (("min", 0), ("q05", .05), ("q25", .25), ("median", .5), ("q75", .75), ("q95", .95), ("max", 1)):
        result[name] = float(np.quantile(a, q)) if a.size else None
    return result


def _rate(passed):
    count, good = len(passed), sum(bool(p) for p in passed)
    return {"denominator": count, "passing_positions": good,
            "fraction": good / count if count else None,
            "pass": bool(count and good * 20 >= count * 19)}


def _efficacy(values, mode, undefined=0):
    distribution = _distribution(values)
    median = distribution["median"] if not undefined else None
    return {"ratio": distribution, "undefined_positions": undefined,
            "median": median, "pass": bool(median is not None and (median <= .5 if mode == "suppression" else median >= .5))}


def _mode_summary(items, ids, mode):
    features, numerical, bounded = {}, [], []
    counts = {k: 0 for k in ("positions", "nonspecial_positions", "zero_requested_positions",
                            "all_inactive_positions", "rounded_away_positions", "active_no_request_positions")}
    diagnostic_fields = VECTORS + COUNTS + ("realized_clean_norm_ratio", "requested_clean_norm_ratio")
    diagnostics = {scope: {key: [] for key in diagnostic_fields} for scope in ("all_positions", "nonspecial")}
    parity = {"before": [], "after": []}
    for row, arrays, nonspecial in items:
        a = arrays[mode]
        nz, realized = a["nonzero_requested"], a["realized_norm"] > 0
        active = (a["before"] > 0).any(1)
        numerical.extend((a["cosine"][nz] >= .95) & (a["relative_error"][nz] <= .2))
        bounded.extend(a["realized_norm"][realized] <= .05 * a["clean_norm"][realized])
        counts["positions"] += len(nonspecial)
        counts["nonspecial_positions"] += int(nonspecial.sum())
        counts["zero_requested_positions"] += int((~nz).sum())
        counts["all_inactive_positions"] += int((~active).sum())
        counts["rounded_away_positions"] += int((nz & ~realized).sum())
        counts["active_no_request_positions"] += int((active & ~nz).sum())
        extended = {**a, "realized_clean_norm_ratio": a["realized_norm"] / a["clean_norm"],
                    "requested_clean_norm_ratio": a["requested_norm"] / a["clean_norm"]}
        for scope, mask in (("all_positions", np.ones(len(nonspecial), dtype=bool)), ("nonspecial", nonspecial)):
            for name in diagnostic_fields:
                diagnostics[scope][name].extend(extended[name][mask])
        for phase in parity:
            parity[phase].append(_comparison(a[phase], a["selected_" + phase], nonspecial))
    disagreements = []
    for j, feature in enumerate(ids):
        native, selected, by_text, undefined = [], [], {}, 0
        for row, arrays, nonspecial in items:
            a = arrays[mode]
            mask = nonspecial & (a["before"][:, j] > 0)
            by_text[row["text_id"]] = int(mask.sum())
            b, end = a["before"][mask, j], a["after"][mask, j]
            sb, se = a["selected_before"][mask, j], a["selected_after"][mask, j]
            if mode == "suppression":
                native.extend(end / b)
                undefined += int((sb == 0).sum())
                selected.extend(se[sb > 0] / sb[sb > 0])
            elif mode == "amplification":
                # Retain the original intended request, not the norm-capped prediction.
                native.extend((end - b) / (.75 * b))
                selected.extend((se - sb) / (.75 * b))
        exposure = {"positions": sum(by_text.values()), "texts": sum(v > 0 for v in by_text.values()),
                    "by_text": by_text}
        exposure["pass"] = exposure["positions"] >= 100 and exposure["texts"] >= 6
        f = {"exposure": exposure}
        if mode != "zero":
            f.update(native=_efficacy(native, mode), selected_width=_efficacy(selected, mode, undefined))
            if f["native"]["pass"] != f["selected_width"]["pass"]:
                disagreements.append({"feature_id": feature, "component": "efficacy",
                                      "native": f["native"]["pass"], "selected_width": f["selected_width"]["pass"]})
        features[str(feature)] = f
    fidelity, norm = _rate(numerical), _rate(bounded)
    report = {"rows": len(items), **counts, "features": features, "fidelity": fidelity, "norm": norm,
              "distributions": {s: {k: _distribution(v) for k, v in d.items()} for s, d in diagnostics.items()},
              "selected_width_comparison": {phase: _merge_comparisons(v) for phase, v in parity.items()}}
    if mode != "zero":
        components = {"exposure": all(f["exposure"]["pass"] for f in features.values()),
                      "efficacy": all(f["native"]["pass"] for f in features.values()),
                      "fidelity": fidelity["pass"], "norm": norm["pass"]}
        alternate = {**components, "efficacy": all(f["selected_width"]["pass"] for f in features.values())}
        report.update(components=components, native_components_pass=all(components.values()),
                      selected_width_components=alternate, selected_width_components_pass=all(alternate.values()),
                      decision_disagreements=disagreements)
    return report


def _merge_comparisons(values):
    names = ("entries", "exact_entries", "active_to_inactive", "inactive_to_active",
             "nonspecial_active_to_inactive", "nonspecial_inactive_to_active")
    result = {key: sum(v[key] for v in values) for key in names}
    result["exact_fraction"] = result["exact_entries"] / result["entries"] if result["entries"] else None
    result["max_absolute_difference"] = max((v["max_absolute_difference"] for v in values), default=None)
    return result


def summarize(rows, ids):
    """Validate every supplied row; missing arms/measurements are never zero-filled."""
    _ids(ids)
    rows = list(rows)
    checked, seen = [], set()
    for row in sorted(rows, key=lambda r: r["id"]):
        _require(row["id"] not in seen, "Duplicate replay row")
        seen.add(row["id"])
        arrays, nonspecial = _validate_replay(row, ids)
        checked.append((row, arrays, nonspecial))
    return {"scope": SCOPE, "rows": len(rows), "behavioral_assay_qualified": False,
            "inventory_completeness": "not_inferred_from_rows; audit against plan required",
            "eligibility": "Native before > 0 and nonspecial; shared by both signs and both encoder paths",
            "efficacy_denominators": {"native_suppression": "native_before",
                                      "selected_suppression": "selected_before; undefined values retained as unavailable",
                                      "amplification_both_paths": "0.75 * native_before, before norm capping"},
            "delivery_denominators": "All positions: nonzero requests for fidelity, realized nonzero edits for norm",
            "reconstruction_scope": "Original clean-state reconstruction, not edited-state reconstruction",
            "splits": {split: {"historical": True, "rows": sum(r["split"] == split for r in rows),
                               "modes": {mode: _mode_summary([v for v in checked if v[0]["split"] == split], ids, mode)
                                         for mode in MODES}} for split in SPLITS}}


class _ReadOnlyLedger(EventLedger):
    """Use EventLedger's binding/chain validator without its creating write lock."""
    @contextmanager
    def _locked(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            _require(stat.S_ISREG(os.fstat(fd).st_mode), "Ledger must be regular")
            fcntl.flock(fd, fcntl.LOCK_SH)
            yield fd
        finally:
            os.close(fd)

    def bind(self, identifier, data):
        events = self.read()
        _require(bool(events) and events[0]["id"] == identifier and events[0]["data"] == data,
                 "Existing nonempty inventory binding required")
        return events[0]


class _Snapshot:
    def __init__(self, root):
        self.root, self.hashes = Path(root), {}
        _require(self.root.is_dir() and not self.root.is_symlink(), "Missing or symlinked input directory")

    def path(self, name):
        _require(isinstance(name, str) and name and "\\" not in name, "Invalid artifact path")
        rel = PurePosixPath(name)
        _require(not rel.is_absolute() and ".." not in rel.parts and name == rel.as_posix() and name != ".",
                 "Unsafe artifact path")
        path = self.root
        for part in rel.parts:
            path = path / part
            _require(not path.is_symlink(), "Symlinked artifact path")
        _require(path.is_file(), "Missing regular artifact: " + name)
        return path

    def read(self, name, expected=None):
        raw = self.path(name).read_bytes()
        digest = _sha(raw)
        _require(expected is None or (_digest(expected) and digest == expected), "Artifact hash mismatch: " + name)
        _require(name not in self.hashes or self.hashes[name] == digest, "Input changed during audit: " + name)
        self.hashes[name] = digest
        return raw

    def verify(self):
        for name in list(self.hashes):
            self.read(name)


def load_plan(path):
    # The parent owns exact source-revision validation; no same-HEAD requirement here.
    from .protocol import load_plan as parent_load_plan
    return parent_load_plan(path)


def _geometry(row, gram):
    for mode in MODES[1:]:
        a = row["arms"][mode]
        expected = active_support_projection(gram, a["fp32_preact_before"], a["before"], a["clean_norm"], mode=mode)
        for name, key in (("projection_coefficients", "coefficients"), ("projection_scale", "scale"),
                          ("continuous_predicted_activation", "predicted_activation"), ("continuous_norm", "norm")):
            value = expected[key].astype(np.float32) if key == "coefficients" else expected[key]
            _require(np.allclose(a[name], value, rtol=1e-5, atol=1e-7), "Saved Gram projection mismatch: " + name)


def _historical(rows, comparisons, ids):
    result = {}
    for split in SPLITS:
        reports = [comparisons[r["id"]] for r in rows if r["split"] == split]
        features = {}
        for feature in ids:
            fs = [v["features"][str(feature)] for v in reports]
            f = {"native_before": _merge_comparisons([v["native_before"] for v in fs])}
            for path in ("original", "replay"):
                counts = [v[path + "_active_nonspecial_positions"] for v in fs]
                positions, texts = sum(counts), sum(c > 0 for c in counts)
                f[path + "_exposure"] = {"positions": positions, "texts": texts, "pass": positions >= 100 and texts >= 6}
            features[str(feature)] = f
        result[split] = {"rows": len(reports), "historical": True, "features": features,
                         **{name: _merge_comparisons([v[name] for v in reports]) for name in ("native_before", "zero_native")}}
    return {"scope": "Cross-hardware native differences are measured, not an implementation-failure gate",
            "exact_historical_native_replay": bool(rows) and all(v["native_before"]["exact_fraction"] == 1 for v in comparisons.values()),
            "splits": result, "per_state": comparisons}


def _throughput(rows, plan):
    available = {r["text_id"]: r for r in rows}
    planned = plan["first_five"]
    first = [available[i] for i in planned if i in available]
    first_elapsed = sum(r["elapsed_seconds"] for r in first)
    total_elapsed = sum(r["elapsed_seconds"] for r in rows)
    first_complete = len(first) == len(planned)
    return {"scope": "Saved per-state compute times; excludes provisioning, SAE load, barriers and retrieval",
            "completed_states": len(rows), "total_elapsed_seconds": total_elapsed,
            "mean_state_seconds": total_elapsed / len(rows) if rows else None,
            "states_per_second": len(rows) / total_elapsed if rows else None,
            "first_five": {"planned_text_ids": planned, "available_text_ids": [r["text_id"] for r in first],
                           "complete": first_complete, "elapsed_seconds": first_elapsed,
                           "mean_state_seconds": first_elapsed / len(first) if first else None},
            "estimated_remaining_compute_seconds_first_five":
                first_elapsed / len(first) * (len(plan["inputs"]) - len(rows)) if first_complete and first else None}


def audit(run, plan_path, partial=False):
    """Return structural pass/fail separately from every scientific component."""
    result = {"pass": False, "rows": 0, "expected": 0, "errors": [], "summary": None,
              "partial": partial, "complete": False, "behavioral_assay_qualified": False,
              "verification_scope": "Input/receipt hashes, saved-row consistency and continuous projection reconstruction; native telemetry is not independently recomputed from SAE weights"}
    try:
        _require(type(partial) is bool, "partial must be a real bool")
        run_inputs, sources = _Snapshot(run), _Snapshot(ROOT)
        plan_file = Path(plan_path)
        _require(plan_file.is_file() and not plan_file.is_symlink(), "Existing regular plan required")
        plan_raw = plan_file.read_bytes()
        _decode(plan_raw)
        plan = load_plan(plan_file)
        _require(_canonical(plan) + b"\n" == plan_raw, "Noncanonical or changed plan")
        ids = plan["feature_ids"]
        _ids(ids)
        gram = _array(plan["gram"], (len(ids), len(ids)), "Gram")
        _require(np.allclose(gram, gram.T, rtol=0, atol=1e-10) and np.linalg.eigvalsh(gram).min() > 0,
                 "Gram must be symmetric positive definite")
        inventory = plan["inputs"]
        _require(isinstance(inventory, list) and inventory, "Empty plan inventory")
        expected, originals = {}, {}
        for item in inventory:
            _require(isinstance(item, dict) and set(item) == {"id", "row_path", "capture_path", "row_sha256", "capture_sha256"},
                     "Invalid input inventory schema")
            text_id = item["id"]
            _require(isinstance(text_id, str) and re.fullmatch(r"[A-Za-z0-9_-]+", text_id) is not None,
                     "Invalid input ID")
            rid = "replay-" + text_id
            _require(rid not in expected, "Duplicate input ID")
            expected[rid] = item
        result["expected"] = len(expected)
        _require(plan["first_five"] == [i["id"] for i in inventory[:5]], "First-five inventory mismatch")
        # Verify the entire frozen source inventory, including not-yet-replayed states.
        for rid, item in expected.items():
            source = _decode(sources.read(item["row_path"], item["row_sha256"]))
            _require(source["text_id"] == item["id"] and source["id"] == "clean-" + item["id"], "Input ID mismatch")
            _require(item["capture_path"] == plan["input_release"] + "/" + source["capture"]["path"]
                     and source["capture"]["sha256"] == item["capture_sha256"], "Source capture binding mismatch")
            capture = sources.read(item["capture_path"], item["capture_sha256"])
            _require(type(source["capture"]["bytes"]) is int and len(capture) == source["capture"]["bytes"], "Capture size mismatch")
            originals[rid] = source
        raw = run_inputs.read("receipts.jsonl")
        _require(bool(raw) and raw.endswith(b"\n"), "Missing or truncated ledger binding")
        first = _decode(raw.splitlines()[0])
        freeze = first["freeze_commit"]
        _require(_digest(freeze, 40), "Invalid freeze binding")
        ledger = _ReadOnlyLedger(run_inputs.path("receipts.jsonl"), _sha(plan_raw), freeze, list(expected))
        events = ledger.read()
        dispatched, payloads = set(), {}
        for event in events[1:]:
            data = event["data"]
            kind = data.get("kind")
            if kind in ("row", "dispatch"):
                rid = data.get("row_id")
                _require(isinstance(rid, str) and rid in expected and event["id"] == kind + ":" + rid,
                         "Unbound row/dispatch ID")
                if kind == "dispatch":
                    _require(rid not in dispatched and rid not in payloads, "Duplicate or late dispatch")
                    dispatched.add(rid)
                else:
                    _require(rid in dispatched and rid not in payloads, "Undispatched or duplicate row")
                    receipt = data["payload"]
                    _require(isinstance(receipt, dict) and set(receipt) == {"path", "sha256"}
                             and receipt["path"] == "rows/" + rid + ".json", "Unsafe/mismatched receipt path")
                    payloads[rid] = receipt
            else:
                _require(kind == "runtime" and event["id"] == "runtime", "Unexpected replay ledger event")
        result.update(rows=len(payloads), plan_sha256=_sha(plan_raw), freeze_commit=freeze,
                      pending_dispatches=sorted(dispatched - payloads.keys()), missing_row_ids=sorted(expected.keys() - payloads.keys()))
        directory = Path(run) / "rows"
        _require(not directory.is_symlink() and (directory.is_dir() or not payloads), "Missing regular rows directory")
        actual = {p.name for p in directory.iterdir()} if directory.is_dir() else set()
        _require(actual == {rid + ".json" for rid in payloads}, "Unreceipted or missing raw rows")
        rows, comparisons = [], {}
        for rid, receipt in sorted(payloads.items()):
            row = _decode(run_inputs.read(receipt["path"], receipt["sha256"]))
            _require(row["id"] == rid and row["source_row_sha256"] == expected[rid]["row_sha256"]
                     and row["capture_sha256"] == expected[rid]["capture_sha256"], "Replay/source receipt binding mismatch")
            comparisons[rid] = validate_row(row, originals[rid], ids)
            _geometry(row, gram)
            rows.append(row)
        result["complete"] = len(rows) == len(expected)
        result["throughput"] = _throughput(rows, plan)
        result["source_mismatch_counts"] = {
            "states_compared": len(comparisons),
            "native_different_states": sum(v["native_before"]["exact_fraction"] != 1 for v in comparisons.values()),
            "native_different_entries": sum(v["native_before"]["entries"] - v["native_before"]["exact_entries"] for v in comparisons.values()),
            "active_support_changed_entries": sum(v["native_before"]["active_to_inactive"] + v["native_before"]["inactive_to_active"] for v in comparisons.values()),
            "max_native_absolute_difference": max((v["native_before"]["max_absolute_difference"] for v in comparisons.values()), default=None),
            "fp32_preactivation_nonexact_states": sum(v["max_fp32_preactivation_absolute_difference"] > 0 for v in comparisons.values()),
            "clean_norm_nonexact_states": sum(v["max_clean_norm_relative_difference"] > 0 for v in comparisons.values()),
        }
        if not partial:
            _require(result["complete"] and not result["pending_dispatches"], "Incomplete replay inventory")
        summary = summarize(rows, ids)
        summary["historical_replay"] = _historical(rows, comparisons, ids)
        result["summary"] = summary
        # Final checks catch ordinary concurrent mutation; audit a stopped/retrieved snapshot.
        ledger.read()
        sources.verify()
        run_inputs.verify()
        _require(plan_file.read_bytes() == plan_raw, "Plan changed during audit")
        _require(({p.name for p in directory.iterdir()} if directory.is_dir() else set()) == actual,
                 "Row inventory changed during audit")
        result["pass"] = True
    except (ValueError, TypeError, KeyError, IndexError, OSError, OverflowError) as exc:
        result["errors"].append(str(exc))
        result["summary"] = None
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args(argv)
    result = audit(args.run, args.plan, partial=args.partial)
    print(_canonical(result).decode("ascii"))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
