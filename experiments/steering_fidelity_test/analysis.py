"""Offline Stage T math, not an execution plan, dose selector or mechanism test.

Intervals describe item/block resampling of fixed authored material. They do not
cover feature populations, dose selection, classifier error or human validity.
Constant empirical effects can give degenerate bootstrap intervals. Nothing is
read, written, generated or dispatched by this module.
"""
from collections import Counter
from collections.abc import Mapping
import math
import random

from experiments.steering_fidelity import analysis as c

SEED = 2026100202
ARMS = ("zero",) + c.ARMS
FRAMES = ("neutral", "assert", "doubt")
N_ROWS = 100 * (3 + 1) * len(ARMS)
PAIR_ARMS = ("zero", "target-", "target+", "control-1-", "control-1+",
             "control-2-", "control-2+")
PAIR_METRICS = ("I", "U", "both_affirm", "both_deny", "signed_both_affirm_minus_both_deny")


def _inventory(rows, expected_rows, rung):
    index, items = c._index(rows)
    design = index
    source = "fixed 100-item families; identities inferred, wholly absent slots retained"
    if expected_rows is not None:
        design, planned = c._index(expected_rows, outcomes=False)
        if len(design) != N_ROWS or len(planned) != 200:
            raise ValueError("expected_rows must describe all 7600 held-out slots")
        if not index.keys() <= design.keys():
            raise ValueError("Unexpected held-out slot")
        for key, row in index.items():
            for field in ("id", "family", "truth", "rung"):
                if row[field] != design[key][field]:
                    raise ValueError("Row differs from expected_rows")
        items, source = planned, "explicit expected_rows inventory"
    all_rows = list(index.values()) + list(design.values())
    for row in all_rows:
        if row["family"] == "context" and row["frame"] != "neutral":
            raise ValueError("Context items have only a neutral frame")
    rungs = {row["rung"] for row in all_rows if row["rung"] != "zero"}
    if len(rungs) > 1 or (rung is not None and rungs and rungs != {rung}):
        raise ValueError("Held-out analysis requires one predetermined rung")
    rung = rung if rung is not None else next(iter(rungs), None)
    if rung is not None and rung not in c.CANDIDATE_RUNGS:
        raise ValueError("Damage probes are not a held-out dose")
    counts = Counter(items.values())
    if any(counts[family, truth] > 50 for family in ("fact", "context") for truth in (False, True)):
        raise ValueError("Each family requires 50 true and 50 false planned items")
    if expected_rows is not None and any(counts[f, t] != 50 for f in ("fact", "context") for t in (False, True)):
        raise ValueError("Expected inventory is not truth balanced")
    slots = {(f, t): sorted(item for item, meta in items.items() if meta == (f, t))
             + [None] * (50 - counts[f, t]) for f in ("fact", "context") for t in (False, True)}
    observed = sum(c._observed(row) for row in index.values())
    return index, slots, rung, {"source": source, "n_expected": N_ROWS, "n_received": len(index),
                               "n_observed": observed, "n_missing": N_ROWS - observed,
                               "complete": observed == N_ROWS}


def _series(index, units, arm, rung, metric):
    rows = [index.get((item, frame, arm, None if arm == "zero" else rung)) for item, frame in units]
    values = [c._value(row, metric) for row in rows]
    upper = 1 + 1e-6 if metric == "valid_mass" else 1
    return ([(0, upper) if value is None else (value, value) for value in values], values)


def _estimate(bounds, values, seed=None, bootstrap=None):
    result = c._estimate(bounds, values)
    if result["estimate"] is not None and bootstrap is not None:
        # Stable item order and the same seed share draws across frames/signs.
        ci90, ci95 = c._intervals(tuple(values), seed, bootstrap)
        result.update(ci90=list(ci90), ci95=list(ci95))
    return result


def _combine(series, weights, seed, bootstrap):
    """Linear contrasts retain known components rather than dropping incomplete units."""
    n = len(series[0][0])
    if any(len(bounds) != n or len(values) != n for bounds, values in series):
        raise ValueError("Unpaired contrast components")
    bounds, values = [], []
    for i in range(n):
        parts = [sorted((weight * component[0][i][0], weight * component[0][i][1]))
                 for component, weight in zip(series, weights)]
        bounds.append(tuple(math.fsum(part[j] for part in parts) for j in (0, 1)))
        values.append(None if any(component[1][i] is None for component in series) else
                      math.fsum(weight * component[1][i] for component, weight in zip(series, weights)))
    return _estimate(bounds, values, seed, bootstrap)


def _panel_sensitivity(target, panels, fixed, seed, bootstrap):
    result = {**fixed, "method": "two-level item and panel-composition bootstrap",
              "scope": "resampled composition of these eight panels, not fixed-panel inference",
              "ci90": None, "ci95": None}
    if fixed["n_missing"] or not target:
        return result
    rng, n, samples = random.Random(seed), len(target), []
    for _ in range(bootstrap):
        items = rng.choices(range(n), k=n)
        chosen = rng.choices(range(8), k=8)  # One composition shared by every item in this draw.
        samples.append(math.fsum(target[i] - math.fsum(panels[k][i] for k in chosen) / 8
                                 for i in items) / n)
    samples.sort()
    result["ci90"] = [c._quantile(samples, q) for q in (.05, .95)]
    result["ci95"] = [c._quantile(samples, q) for q in (.025, .975)]
    return result


def _positive(estimate, interval):
    bounds = estimate[interval]
    return bounds is not None and bounds[0] > 0


def _preservation(estimate, margin):
    if margin is None:
        return {"established": False, "margin": None, "confidence": .90,
                "status": "not-prespecified"}
    interval = estimate["ci90"]
    established = interval is not None and interval[0] >= -margin and interval[1] <= margin
    return {"established": established, "margin": [-margin, margin], "confidence": .90,
            "status": "established" if established else "not-established"}


def _comparison(index, units, rung, sign, seed, bootstrap, sensitivity=False):
    target, panels = "target" + sign, [f"control-{i}{sign}" for i in range(1, 9)]
    metrics = {}
    for metric in ("p_correct", "correct", "format_valid", "valid_mass"):
        series = {arm: _series(index, units, arm, rung, metric) for arm in ["zero", target] + panels}
        fixed = _combine([series[target]] + [series[arm] for arm in panels], [1] + [-1 / 8] * 8,
                         seed, bootstrap)
        metrics[metric] = {
            "target_minus_zero": _combine([series[target], series["zero"]], [1, -1], seed, bootstrap),
            "target_minus_control_mean": fixed,
            "arm_means": {arm: _estimate(*value) for arm, value in series.items()},
        }
        if metric == "p_correct":
            metrics[metric]["control_minus_zero"] = {
                arm: _combine([series[arm], series["zero"]], [1, -1], seed, bootstrap) for arm in panels}
            metrics[metric]["panel_resampling_sensitivity"] = _panel_sensitivity(
                series[target][1], [series[arm][1] for arm in panels], fixed, seed, bootstrap
            ) if sensitivity else None
    primary = metrics.pop("p_correct")
    return {**primary, "secondary": metrics, "n_expected": len(units),
            "positive_effect_ci95": _positive(primary["target_minus_zero"], "ci95"),
            "positive_specificity_ci90": _positive(primary["target_minus_control_mean"], "ci90"),
            "positive_specificity_ci95": _positive(primary["target_minus_control_mean"], "ci95")}


def summarize_held_out(rows, expected_rows=None, seed=SEED, bootstrap=10000, *, rung=None,
                       neutral_margin=None):
    """Fixed 7600-row design using the same forced-choice row schema as Phase C.

    Facts: 100 items, 50 of each truth, neutral/assert/doubt, 19 arms. Context:
    100 items, 50 of each truth, neutral only, 19 arms. expected_rows, when given,
    must be the full design specifications. Otherwise absent identities are
    padded to the fixed truth/family counts, never dropped. Multiple doses and
    damage600 are rejected, not selected. Calibration rows must not be pooled.

    Single primary: target- minus zero p_correct in false/assert and true/doubt.
    The positive sign, all six truth/frame cells, context, hard accuracy, format
    and valid mass are mandatory outputs. Panel sensitivity is separate and only
    computed for the two aggregate factual conflict contrasts. Fixed specificity
    averages all eight same-sign controls within each item; zero cancels exactly.
    Positive flags are directional interval checks, not a fidelity verdict.
    Neutral preservation requires an explicitly prespecified symmetric margin;
    central-90% interval containment is not evaluated when it is omitted.
    """
    c._bootstrap_settings(seed, bootstrap)
    if neutral_margin is not None:
        neutral_margin = c._number(neutral_margin, "neutral_margin")
    index, slots, rung, inventory = _inventory(rows, expected_rows, rung)
    def units(family, frame=None, truth=None):
        return [(item, frame or ("doubt" if t else "assert")) for t in (False, True)
                if truth is None or truth == t for item in slots[family, t]]
    def both(selected):
        return {sign: _comparison(index, selected, rung, sign, seed, bootstrap) for sign in ("-", "+")}
    neutral = both(units("fact", "neutral"))
    for comparison in neutral.values():
        comparison["preservation"] = {
            "p_correct": _preservation(comparison["target_minus_zero"], neutral_margin),
            "correct": _preservation(comparison["secondary"]["correct"]["target_minus_zero"], neutral_margin)}
    return {"status": "complete" if inventory["complete"] else "incomplete", "inventory": inventory,
            "rung": rung, "seed": seed, "bootstrap": bootstrap,
            "method": "paired item percentile bootstrap, central 90% and 95%; eight panels fixed",
            "scope": "fixed authored items; no mechanism, population, simultaneous-coverage or exact-equality claim",
            "primary": _comparison(index, units("fact"), rung, "-", seed, bootstrap, True),
            "positive_sign": _comparison(index, units("fact"), rung, "+", seed, bootstrap, True),
            "cells": {f"{str(t).lower()}:{frame}": both(units("fact", frame, t))
                      for t in (False, True) for frame in FRAMES},
            "neutral": neutral, "context": both(units("context", "neutral")),
            "context_truth_cells": {str(t).lower(): both(units("context", "neutral", t)) for t in (False, True)}}


def _pair_series(labels, metric):
    def event(a, b):
        affirm, deny = int(a == b == "affirm"), int(a == b == "deny")
        return {"I": affirm + deny, "U": int(a in c.LABELS[2:] or b in c.LABELS[2:]),
                "both_affirm": affirm, "both_deny": deny,
                "signed_both_affirm_minus_both_deny": affirm - deny}[metric]
    bounds, values = [], []
    for a, b in labels:
        possible = [event(x, y) for x in (c.LABELS if a is None else (a,))
                    for y in (c.LABELS if b is None else (b,))]
        bounds.append((min(possible), max(possible)))
        values.append(None if a is None or b is None else event(a, b))
    return bounds, values


def summarize_opposing_pairs(pairs, expected_pairs=None, seed=SEED, bootstrap=10000,
                            *, expected_blocks=60, arms=PAIR_ARMS):
    """Semantic branch pairs, paired by block across arms, never by row order.

    Row: {block_id, arm, a, b, missing?}; id may substitute for block_id ONLY
    when it is a shared logical block identifier, not a unique arm-specific ID.
    a/b are affirm/deny/uncertain/nonanswer or None; missing=True requires both
    to be absent/None. A None branch with missing=False is a partial pair.
    expected_pairs can bind the
    complete block-arm inventory. Without it, wholly absent blocks are padded
    to expected_blocks (default 60). Default arms are zero, targets +/- and the
    first two fixed panels +/-. Pass another complete paired panel set explicitly.

    Both branches stay together in every bootstrap. Missing half-pairs retain
    attainable bounds; unresolved labels are observed outcomes, never denials.
    The signed score is in [-1,1], so its between-arm bounds may span [-2,2].
    No inference about which experience assertion is true is made.
    """
    c._bootstrap_settings(seed, bootstrap)
    if type(expected_blocks) is not int or expected_blocks < 1:
        raise ValueError("expected_blocks must be positive")
    arms = tuple(arms)
    if len(set(arms)) != len(arms) or not {"zero", "target-", "target+"} <= set(arms) or not set(arms) <= set(ARMS):
        raise ValueError("Invalid opposing arm inventory")
    for k in range(1, 9):
        if (f"control-{k}-" in arms) != (f"control-{k}+" in arms):
            raise ValueError("Both signs of each fixed panel are required")
    def index_pairs(records, outcomes):
        index = {}
        for row in records:
            if not isinstance(row, Mapping):
                raise ValueError("Pair rows must be mappings")
            block = row.get("block_id", row.get("id"))
            if not isinstance(block, str) or not block or row.get("arm") not in arms:
                raise ValueError("Invalid block/arm identity")
            key = (block, row["arm"])
            if key in index:
                raise ValueError("Duplicate opposing block/arm")
            missing = c._boolean(row.get("missing", False), "missing") if outcomes else True
            if outcomes and missing and (row.get("a") is not None or row.get("b") is not None):
                raise ValueError("Missing pair contradicts supplied semantic labels")
            labels = (None, None) if missing else (row.get("a"), row.get("b"))
            if any(value is not None and value not in c.LABELS for value in labels):
                raise ValueError("Semantic labels required, not Yes/No tokens")
            index[key] = labels
        return index
    index = index_pairs(pairs, True)
    design = index_pairs(expected_pairs, False) if expected_pairs is not None else index
    if not index.keys() <= design.keys():
        raise ValueError("Unexpected opposing block/arm")
    blocks = sorted({block for block, _ in design})
    if len(blocks) > expected_blocks or (expected_pairs is not None and (
            len(blocks) != expected_blocks or len(design) != expected_blocks * len(arms))):
        raise ValueError("Opposing inventory differs from planned denominator")
    blocks += [None] * (expected_blocks - len(blocks))
    by_arm, series = {}, {}
    for arm in arms:
        labels = [index.get((block, arm), (None, None)) for block in blocks]
        by_arm[arm] = c._opposing_arm(labels)
        series[arm] = {metric: _pair_series(labels, metric) for metric in PAIR_METRICS}
        for metric, components in series[arm].items():
            by_arm[arm][metric].update(_estimate(*components, seed, bootstrap))
    contrasts = {}
    for sign in ("-", "+"):
        target = "target" + sign
        panels = [arm for arm in arms if arm.startswith("control-") and arm.endswith(sign)]
        contrasts[sign] = {
            "target_minus_zero": {metric: _combine([series[target][metric], series["zero"][metric]],
                                   [1, -1], seed, bootstrap) for metric in PAIR_METRICS},
            "control_minus_zero": {arm: {metric: _combine([series[arm][metric], series["zero"][metric]],
                                          [1, -1], seed, bootstrap) for metric in PAIR_METRICS} for arm in panels},
            "target_minus_control_mean": {metric: _combine([series[target][metric]] +
                [series[arm][metric] for arm in panels], [1] + [-1 / len(panels)] * len(panels), seed, bootstrap)
                for metric in PAIR_METRICS} if panels else None,
        }
    return {"expected_blocks": expected_blocks, "expected_pairs": expected_blocks * len(arms),
            "received_pairs": len(index), "arms": list(arms), "by_arm": by_arm, "contrasts": contrasts,
            "seed": seed, "bootstrap": bootstrap, "method": "paired block percentile bootstrap; panels fixed",
            "scope": "semantic report consistency, not truth, acquiescence or consciousness identification"}
