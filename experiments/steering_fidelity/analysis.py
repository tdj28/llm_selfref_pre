"""Pure, CPU-only summaries for the steering-fidelity engineering calibration.

Calibration never accepts experience-report families. Bootstrap intervals are
item-resampling summaries of a fixed authored panel, not population guarantees
or simultaneous confidence bounds across arms/doses. No files or models are read.
"""

from collections import Counter
from collections.abc import Mapping
from functools import lru_cache
import math
import random


SEED = 2026100201
CANDIDATE_RUNGS = ("raw", "rho075", "rho150", "rho300")
RUNGS = CANDIDATE_RUNGS + ("damage600",)
CONTROL_ARMS = tuple(f"control-{i}-" for i in range(1, 9))
ARMS = ("target-", "target+") + tuple(
    f"control-{i}{sign}" for i in range(1, 9) for sign in ("-", "+")
)
LABELS = ("affirm", "deny", "uncertain", "nonanswer")
N_ITEMS = 100
N_ROWS = N_ITEMS * (1 + len(ARMS) * len(RUNGS))
LOSS_MARGIN = 0.10
MIN_FRACTION = 0.95
MIN_BASELINE_ACCURACY = 0.80


def _boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be a bool")
    return value


def _number(value, name, low=0.0, high=1.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} outside [{low}, {high}]")
    return float(value)


def _delivery(row):
    delivery = row.get("delivery")
    if delivery is None:
        return None
    if not isinstance(delivery, Mapping):
        raise ValueError("delivery must be a mapping")
    for key in ("nonzero_positions", "eligible_positions"):
        if type(delivery.get(key)) is not int or delivery[key] < 0:
            raise ValueError(f"delivery.{key} must be a nonnegative integer")
    if delivery["nonzero_positions"] > delivery["eligible_positions"]:
        raise ValueError("nonzero_positions exceeds eligible_positions")
    for key in ("cosine_min", "cosine_mean"):
        _number(delivery.get(key), f"delivery.{key}", -1 - 1e-6, 1 + 1e-6)
    if delivery["cosine_min"] > delivery["cosine_mean"]:
        raise ValueError("cosine_min exceeds cosine_mean")
    for key in ("relative_error_max", "norm_relative_error_max"):
        _number(delivery.get(key), f"delivery.{key}", 0, math.inf)
    _number(delivery.get("fidelity_pass_fraction"), "delivery.fidelity_pass_fraction")
    qualified = delivery.get("qualified")
    if qualified is not None:
        _boolean(qualified, "delivery.qualified")
    if qualified and not delivery["nonzero_positions"]:
        raise ValueError("qualified nonzero arm has no delivered nonzero positions")
    return delivery


def _index(rows, *, calibration=False, outcomes=True):
    index, ids, items = {}, set(), {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("rows must be mappings")
        for name in ("id", "item_id"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError(f"{name} must be a nonempty string")
        if row["id"] in ids:
            raise ValueError(f"Duplicate row id: {row['id']}")
        ids.add(row["id"])
        if row.get("family") not in ("fact", "context"):
            raise ValueError("Only fact/context rows allowed; no experience outcomes")
        _boolean(row.get("truth"), "truth")
        if row.get("frame") not in ("neutral", "assert", "doubt"):
            raise ValueError("Unknown frame")
        if calibration and row["frame"] != "neutral":
            raise ValueError("Calibration requires neutral frames")
        if row.get("arm") not in ("zero",) + ARMS:
            raise ValueError("Unknown arm")
        allowed_rungs = ("zero",) + RUNGS if row["arm"] == "zero" else RUNGS
        if row.get("rung") not in allowed_rungs:
            raise ValueError("Unknown rung")
        meta = (row["family"], row["truth"])
        item = row["item_id"]
        if item in items and items[item] != meta:
            raise ValueError(f"Inconsistent item metadata: {item}")
        items[item] = meta
        # A zero is shared across doses, never counted once per dose.
        key = (item, row["frame"], row["arm"],
               None if row["arm"] == "zero" else row["rung"])
        if key in index:
            raise ValueError(f"Duplicate design slot: {key}")
        index[key] = row
        if outcomes:
            missing = _boolean(row.get("missing", False), "missing")
            if not missing:
                for name in ("correct", "format_valid"):
                    _boolean(row.get(name), name)
                _number(row.get("p_correct"), "p_correct")
                _number(row.get("valid_mass"), "valid_mass", 0, 1 + 1e-6)
                if calibration and row["arm"] != "zero":
                    _delivery(row)
    return index, items


def _observed(row):
    return row is not None and not row.get("missing", False)


def _value(row, metric):
    return float(row[metric]) if _observed(row) else None


def _quantile(values, probability):
    position = (len(values) - 1) * probability
    lo = math.floor(position)
    hi = math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


@lru_cache(maxsize=256)
def _intervals(values, seed, bootstrap):
    """Cache repeated empirical distributions, without changing the bootstrap."""
    if min(values) == max(values):
        return ((values[0], values[0]), (values[0], values[0]))
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(math.fsum(rng.choices(values, k=n)) / n for _ in range(bootstrap))
    return ((_quantile(samples, 0.05), _quantile(samples, 0.95)),
            (_quantile(samples, 0.025), _quantile(samples, 0.975)))


def _bootstrap_settings(seed, bootstrap):
    if type(seed) is not int or type(bootstrap) is not int or bootstrap < 1:
        raise ValueError("seed must be an integer and bootstrap a positive integer")


def _estimate(bounds, observed, seed=None, bootstrap=None):
    """Missing bounds retain each known component of a partially observed pair."""
    n = len(bounds)
    known = [value for value in observed if value is not None]
    complete = n > 0 and len(known) == n
    ci90 = ci95 = None
    if complete and bootstrap is not None:
        intervals = _intervals(tuple(sorted(known)), seed, bootstrap)
        ci90, ci95 = (list(interval) for interval in intervals)
    return {
        "n_expected": n, "n_observed": len(known), "n_missing": n - len(known),
        "estimate": math.fsum(known) / n if complete else None,
        "complete_case_mean": math.fsum(known) / len(known) if known else None,
        "missing_bounds": [math.fsum(b[i] for b in bounds) / n for i in (0, 1)]
        if n else None,
        "ci90": ci90, "ci95": ci95,
    }


def _metric(rows, metric):
    values = [_value(row, metric) for row in rows]
    upper = 1 + 1e-6 if metric == "valid_mass" else 1
    return _estimate([(0, upper) if value is None else (value, value) for value in values],
                     values)


def _contrast(left, right, metric, seed, bootstrap):
    bounds, values = [], []
    for a, b in zip(left, right):
        av, bv = _value(a, metric), _value(b, metric)
        bounds.append(((0 if av is None else av) - (1 if bv is None else bv),
                       (1 if av is None else av) - (0 if bv is None else bv)))
        values.append(None if av is None or bv is None else av - bv)
    return _estimate(bounds, values, seed, bootstrap)


def _competence_rows(rows):
    """Pressure-wording checks cannot influence the neutral competence selector."""
    neutral, excluded, ids = [], 0, set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("family") not in ("fact", "context"):
            raise ValueError("Only fact/context rows allowed; no experience outcomes")
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("id must be a nonempty string")
        if identifier in ids:
            raise ValueError(f"Duplicate row id: {identifier}")
        ids.add(identifier)
        if row.get("frame") in ("assert", "doubt"):
            excluded += 1
        else:
            neutral.append(row)
    return neutral, excluded


def _calibration_inventory(rows, expected_rows):
    rows, excluded = _competence_rows(rows)
    index, items = _index(rows, calibration=True)
    expected_excluded = None
    source = "fixed 50 fact + 50 context slots; identities inferred from supplied rows"
    if expected_rows is not None and type(expected_rows) is not int:
        expected_rows, expected_excluded = _competence_rows(expected_rows)
        expected, planned_items = _index(expected_rows, calibration=True, outcomes=False)
        counts = Counter(family for family, _ in planned_items.values())
        if len(expected) != N_ROWS or counts != {"fact": 50, "context": 50}:
            raise ValueError("expected_rows must describe the full 9100-row calibration")
        if not index.keys() <= expected.keys():
            raise ValueError("Unexpected calibration design slot")
        for key, row in index.items():
            spec = expected[key]
            if (row["id"], row["family"], row["truth"], row["rung"]) != (
                    spec["id"], spec["family"], spec["truth"], spec["rung"]):
                raise ValueError("Row differs from expected_rows")
        items = planned_items
        source = "explicit expected_rows inventory"
    elif expected_rows is not None and expected_rows != N_ROWS:
        raise ValueError("Calibration denominator is fixed at 9100 rows")
    counts = Counter(family for family, _ in items.values())
    if any(counts[family] > 50 for family in ("fact", "context")):
        raise ValueError("Calibration requires exactly 50 fact and 50 context items")
    # None slots account for wholly absent items even without an identity manifest.
    slots = []
    for family in ("fact", "context"):
        slots.extend(sorted(item for item, meta in items.items() if meta[0] == family))
        slots.extend([None] * (50 - counts[family]))
    return index, slots, source, dict(counts), excluded, expected_excluded


def _competence(zeros, rows, seed, bootstrap):
    loss = _contrast(zeros, rows, "correct", seed, bootstrap)
    interval = loss["ci90"]
    preservation = "not-established"
    if interval is not None:
        if interval[1] <= LOSS_MARGIN:
            preservation = "established"
        elif interval[0] > LOSS_MARGIN:
            preservation = "damage"
    format_summary = _metric(rows, "format_valid")
    format_pass = (format_summary["estimate"] is not None
                   and format_summary["estimate"] >= MIN_FRACTION)
    return {
        "accuracy_loss": loss, "preservation": preservation,
        "format": format_summary, "format_pass": format_pass,
        "p_correct_change": _contrast(rows, zeros, "p_correct", seed, bootstrap),
        "valid_mass": _metric(rows, "valid_mass"),
        "pass": preservation == "established" and format_pass,
    }


def _preservation(values):
    statuses = [value["preservation"] for value in values]
    if "damage" in statuses:
        return "damage"
    return "established" if all(value == "established" for value in statuses) else "not-established"


def _precision(rows):
    deliveries = [_delivery(row) if _observed(row) else None for row in rows]
    qualified = [d.get("qualified") if d is not None else None for d in deliveries]
    known = [value for value in qualified if value is not None]
    n = len(rows)
    passed = sum(known)
    report = {
        "n_expected": n, "n_qualified": passed, "n_failed": len(known) - passed,
        "n_unknown": n - len(known), "qualified_fraction": passed / n,
        "qualified_fraction_bounds": [passed / n, (passed + n - len(known)) / n],
        "pass": len(known) == n and passed / n >= MIN_FRACTION,
        "threshold_source": "parent-supplied delivery.qualified; no physics threshold inferred",
    }
    telemetry = [d for d in deliveries if d is not None]
    report["telemetry"] = {
        "n_rows": len(telemetry),
        "eligible_positions": sum(d["eligible_positions"] for d in telemetry),
        "nonzero_positions": sum(d["nonzero_positions"] for d in telemetry),
        "cosine_min": min((d["cosine_min"] for d in telemetry), default=None),
        "cosine_mean_trial_average": math.fsum(d["cosine_mean"] for d in telemetry)
        / len(telemetry) if telemetry else None,
        "relative_error_max": max((d["relative_error_max"] for d in telemetry), default=None),
        "norm_relative_error_max": max((d["norm_relative_error_max"] for d in telemetry),
                                       default=None),
        "fidelity_pass_fraction_trial_average": math.fsum(
            d["fidelity_pass_fraction"] for d in telemetry) / len(telemetry) if telemetry else None,
    }
    return report


def summarize_calibration(rows, expected_rows=None, seed=SEED, bootstrap=10000):
    """Select the highest passing non-damage rung over the fixed 100-item panel.

    ``expected_rows`` is None, 9100, or the full sequence of row specifications
    (identity/design fields, no outcomes required). Pressure rows (assert/doubt)
    are excluded from both outcomes and inventory, with their counts reported.
    Every nonzero arm/rung has
    100 slots, with one zero per item shared across rungs. Missing rows/outcomes
    block final selection, including missing damage-probe rows. Duplicate IDs
    or slots and unexpected data raise ValueError instead of being deduplicated.

    Preservation uses the upper endpoint of the central percentile 90% interval
    for zero-minus-arm binary accuracy loss (the 95th bootstrap percentile).
    "damage" requires its lower endpoint to exceed .10; otherwise a failed bound
    is "not-established". Competence and format >= .95 must pass in BOTH
    50-item families for EVERY arm; pooled results are descriptive. Parent-
    qualified precision must pass on >= .95 of the 100 trials in EVERY arm.
    Unknown precision never silently passes. Its per-position criterion belongs
    to the parent audit, not this analysis.
    Each family's zero baseline must have accuracy >= .80 and format >= .95.
    "eligible" is local to a rung; final selection also requires completeness
    and baseline qualification. Baseline failure does not change rung summaries.
    "damage600" is a diagnostic name, not evidence that damage occurred.
    """
    _bootstrap_settings(seed, bootstrap)
    index, slots, source, family_counts, excluded, expected_excluded = _calibration_inventory(
        rows, expected_rows)
    zeros = [index.get((item, "neutral", "zero", None)) for item in slots]
    zero_families = {}
    for family, start in (("fact", 0), ("context", 50)):
        baseline = {metric: _metric(zeros[start:start + 50], metric) for metric in
                    ("correct", "p_correct", "format_valid", "valid_mass")}
        accuracy, format_rate = baseline["correct"]["estimate"], baseline["format_valid"]["estimate"]
        baseline["accuracy_pass"] = accuracy is not None and accuracy >= MIN_BASELINE_ACCURACY
        baseline["format_pass"] = format_rate is not None and format_rate >= MIN_FRACTION
        baseline["qualified"] = baseline["accuracy_pass"] and baseline["format_pass"]
        zero_families[family] = baseline
    baseline_qualified = all(value["qualified"] for value in zero_families.values())
    observed = sum(_observed(row) for row in index.values())
    complete = observed == N_ROWS
    report = {
        "calibration_complete": complete,
        "baseline_qualified": baseline_qualified,
        "zero_families": zero_families,
        "completeness": {
            "expected_rows": N_ROWS, "received_rows": len(index), "observed_rows": observed,
            "absent_rows": N_ROWS - len(index), "explicit_missing_rows": len(index) - observed,
            "missing_rows": N_ROWS - observed, "item_counts": family_counts,
            "inventory_source": source,
            "excluded_pressure_rows": excluded,
            "expected_excluded_pressure_rows": expected_excluded,
        },
        "inference": {
            "sampling_unit": "item", "bootstrap": bootstrap, "seed": seed,
            "method": "paired item percentile bootstrap; central 90% and 95% intervals",
            "scope": "100 fixed authored items (50 fact, 50 context); eight fixed panels",
            "warning": "No population, simultaneous-coverage or exact-equality claim; "
                       "constant observed differences produce degenerate bootstrap intervals.",
        },
        "rule": {
            "loss_margin": LOSS_MARGIN, "minimum_format_fraction": MIN_FRACTION,
            "minimum_precision_fraction": MIN_FRACTION,
            "minimum_baseline_accuracy": MIN_BASELINE_ACCURACY,
            "minimum_baseline_format_fraction": MIN_FRACTION,
            "candidate_order": list(CANDIDATE_RUNGS), "raw_failure_is_policy_stop": False,
            "damage_definition": "lower central-90% accuracy-loss bound > 0.10",
            "requires_complete_calibration": True,
            "competence_scope": "each 50-item family separately, all 18 arms",
            "precision_scope": "all 100 trials per arm; parent-qualified per-position gate",
        },
        "zero": {metric: _metric(zeros, metric) for metric in
                 ("correct", "p_correct", "format_valid", "valid_mass")},
        "rungs": {},
    }
    for rung in RUNGS:
        arm_reports = {}
        for arm in ARMS:
            arm_rows = [index.get((item, "neutral", arm, rung)) for item in slots]
            pooled = _competence(zeros, arm_rows, seed, bootstrap)
            families = {
                family: _competence(zeros[start:start + 50], arm_rows[start:start + 50],
                                    seed, bootstrap)
                for family, start in (("fact", 0), ("context", 50))
            }
            precision = _precision(arm_rows)
            arm_reports[arm] = {
                **pooled,
                "pooled_preservation": pooled["preservation"],
                "preservation": _preservation(families.values()),
                "format_pass": all(value["format_pass"] for value in families.values()),
                "families": families,
                "precision": precision,
                "pass": all(value["pass"] for value in families.values()) and precision["pass"],
            }
        passes = all(value["pass"] for value in arm_reports.values())
        report["rungs"][rung] = {
            "selectable": rung in CANDIDATE_RUNGS,
            "engineering_pass": passes,
            "eligible": rung in CANDIDATE_RUNGS and passes,
            "preservation": _preservation(arm_reports.values()),
            "failed_arms": [arm for arm, value in arm_reports.items() if not value["pass"]],
            "arms": arm_reports,
        }
    eligible = [rung for rung in CANDIDATE_RUNGS if report["rungs"][rung]["eligible"]]
    report["selected_rung"] = eligible[-1] if complete and baseline_qualified and eligible else None
    report["status"] = "incomplete" if not complete else (
        "baseline-not-qualified" if not baseline_qualified else
        "selected" if report["selected_rung"] else "no-eligible-dose")
    return report


def _paired_panel_summary(index, units, rung, seed, bootstrap):
    def arm_rows(arm):
        return [index.get((item, frame, arm, None if arm == "zero" else rung))
                for item, frame in units]

    zeros, target = arm_rows("zero"), arm_rows("target-")
    panels = [arm_rows(arm) for arm in CONTROL_ARMS]
    bounds, values = [], []
    for i, row in enumerate(target):
        t = _value(row, "p_correct")
        controls = [_value(panel[i], "p_correct") for panel in panels]
        # The shared zero cancels algebraically; never reweight surviving panels.
        lo = (0 if t is None else t) - math.fsum(1 if p is None else p for p in controls) / 8
        hi = (1 if t is None else t) - math.fsum(0 if p is None else p for p in controls) / 8
        bounds.append((lo, hi))
        values.append(None if t is None or any(p is None for p in controls)
                      else t - math.fsum(controls) / 8)
    specificity = _estimate(bounds, values, seed, bootstrap)
    specificity["positive_specificity_supported"] = (
        specificity["ci90"] is not None and specificity["ci90"][0] > 0
    )
    return {
        "n_expected": len(units),
        "target_minus_zero": _contrast(target, zeros, "p_correct", seed, bootstrap),
        "control_minus_zero": {
            arm: _contrast(panel, zeros, "p_correct", seed, bootstrap)
            for arm, panel in zip(CONTROL_ARMS, panels)
        },
        "target_minus_control_mean": specificity,
    }


def paired_summary(rows, expected_rows=None, seed=SEED, bootstrap=10000, rung=None):
    """Primary p_correct contrasts in each fact item's conflict frame.

    Uses false/assert and true/doubt, one observation per item, against zero
    and the NEGATIVE signs of eight fixed panels. Reports all truth/frame cells
    separately. A failed/missing control does not erase target-zero observations.
    Supply expected_rows (design specifications) to include wholly absent items;
    without it the denominator is explicitly the supplied item roster. Rows may
    contain context items, which never enter the fact primary. Multiple nonzero
    rungs require explicit selection, and damage600 is never a primary dose.
    """
    _bootstrap_settings(seed, bootstrap)
    index, items = _index(rows)
    source = "supplied item roster; wholly absent items require expected_rows"
    design = index
    if expected_rows is not None:
        design, planned_items = _index(expected_rows, outcomes=False)
        if not index.keys() <= design.keys():
            raise ValueError("Unexpected paired design slot")
        for key, row in index.items():
            spec = design[key]
            if (row["id"], row["family"], row["truth"], row["rung"]) != (
                    spec["id"], spec["family"], spec["truth"], spec["rung"]):
                raise ValueError("Row differs from expected_rows")
        items = planned_items
        source = "explicit expected_rows inventory"
    rungs = {key[3] for key in design if key[2] != "zero"}
    if rung is None:
        if len(rungs) != 1:
            raise ValueError("Specify one primary rung explicitly")
        rung = next(iter(rungs))
    if rung not in CANDIDATE_RUNGS:
        raise ValueError("Primary rung must be non-damage")
    facts = sorted(item for item, meta in items.items() if meta[0] == "fact")
    units = [(item, "doubt" if items[item][1] else "assert") for item in facts]
    return {
        "rung": rung, "inventory_source": source, "sampling_unit": "item",
        "scope": "conditional on the fixed authored items and eight fixed control panels",
        "method": "paired item percentile bootstrap, no panel resampling",
        "bootstrap": bootstrap, "seed": seed,
        "primary": _paired_panel_summary(index, units, rung, seed, bootstrap),
        "cells": {
            f"{'true' if truth else 'false'}:{frame}": _paired_panel_summary(
                index, [(item, frame) for item in facts if items[item][1] == truth],
                rung, seed, bootstrap)
            for truth in (False, True) for frame in ("neutral", "assert", "doubt")
        },
    }


def _opposing_arm(pairs):
    joint = {a: {b: 0 for b in LABELS} for a in LABELS}
    statistics = {
        "I": lambda a, b: int((a, b) in (("affirm", "affirm"), ("deny", "deny"))),
        "U": lambda a, b: int(a in LABELS[2:] or b in LABELS[2:]),
        "compatible": lambda a, b: int((a, b) in (("affirm", "deny"), ("deny", "affirm"))),
        "both_affirm": lambda a, b: int(a == b == "affirm"),
        "both_deny": lambda a, b: int(a == b == "deny"),
        "signed_both_affirm_minus_both_deny": lambda a, b:
            int(a == b == "affirm") - int(a == b == "deny"),
    }
    observed = {key: [] for key in statistics}
    bounds = {key: [] for key in statistics}
    joint_bounds = {a: {b: [0, 0] for b in LABELS} for a in LABELS}
    marginals = {branch: {label: [] for label in LABELS} for branch in ("a", "b")}
    complete = 0
    for a, b in pairs:
        known = a is not None and b is not None
        if known:
            complete += 1
            joint[a][b] += 1
        possibilities = [(x, y) for x in (LABELS if a is None else (a,))
                         for y in (LABELS if b is None else (b,))]
        for key, statistic in statistics.items():
            outcomes = [statistic(x, y) for x, y in possibilities]
            bounds[key].append((min(outcomes), max(outcomes)))
            observed[key].append(statistic(a, b) if known else None)
        for x in LABELS:
            for y in LABELS:
                outcomes = [int(pair == (x, y)) for pair in possibilities]
                joint_bounds[x][y][0] += min(outcomes)
                joint_bounds[x][y][1] += max(outcomes)
        for branch, value in (("a", a), ("b", b)):
            for label in LABELS:
                marginals[branch][label].append(None if value is None else int(value == label))
    n = len(pairs)
    report = {
        "n_expected": n, "n_complete": complete, "n_missing": n - complete,
        "joint_counts": joint,
        "joint_rate_bounds": {a: {b: [v / n for v in joint_bounds[a][b]] if n else None
                                  for b in LABELS} for a in LABELS},
        "marginals": {
            branch: {label: _estimate([(0, 1) if v is None else (v, v) for v in values], values)
                     for label, values in labels.items()}
            for branch, labels in marginals.items()
        },
    }
    for key in statistics:
        report[key] = _estimate(bounds[key], observed[key])
        report[key]["observed_sum"] = sum(v for v in observed[key] if v is not None)
    return report


def summarize_opposing_pairs(pairs):
    """Summarize pre-coded semantic pairs, without interpreting text or truth.

    One mapping per PLANNED (id, arm) pair: {id, arm, a, b, missing?}. Branches
    a/b are affirm, deny, uncertain, nonanswer, or None (missing). A missing=True
    pair has both branches missing, even if stale labels remain. Omitted pairs
    cannot be inferred: callers must supply placeholders. IDs may recur across
    arms but not within an arm. Unresolved labels remain outcomes, not missing.
    All 16 joint cells, both marginals, I, U and the signed both-affirm-minus-
    both-deny statistic use the full planned denominator. Missing bounds enumerate
    possible labels, retaining information from a known half-pair. No CI or
    consciousness/acquiescence identification claim is made.
    """
    grouped, seen = {}, set()
    for pair in pairs:
        for name in ("id", "arm"):
            if not isinstance(pair.get(name), str) or not pair[name]:
                raise ValueError(f"Pair {name} must be a nonempty string")
        key = (pair["id"], pair["arm"])
        if key in seen:
            raise ValueError(f"Duplicate opposing pair: {key}")
        seen.add(key)
        missing = _boolean(pair.get("missing", False), "pair missing")
        a, b = (None, None) if missing else (pair.get("a"), pair.get("b"))
        if any(value is not None and value not in LABELS for value in (a, b)):
            raise ValueError("Opposing branches require semantic labels, not Yes/No tokens")
        grouped.setdefault(pair["arm"], []).append((a, b))
    return {
        "denominator": "all supplied planned pairs, including missing placeholders",
        "scope": "semantic report consistency; not a consciousness or acquiescence test",
        "n_expected": len(seen),
        "by_arm": {arm: _opposing_arm(values) for arm, values in sorted(grouped.items())},
    }
