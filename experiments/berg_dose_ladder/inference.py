"""Paired CP bounds with fixed control strata and worst-case missing labels.

``alpha`` is the error budget for ONE direction. Defaults give individual
two-sided 95% intervals, not jointly covering D and S. The positive IUT uses
both lower bounds at 2.5%; exclusion uses D's upper bound at 2.5%.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import math
from numbers import Integral, Real

from scipy.stats import beta


def validate_alpha(alpha):
    if isinstance(alpha, bool) or not isinstance(alpha, Real):
        raise ValueError("alpha must be a finite number in (0, 0.5)")
    alpha = float(alpha)
    if not math.isfinite(alpha) or not 0 < alpha < .5:
        raise ValueError("alpha must be a finite number in (0, 0.5)")
    return alpha


@lru_cache(maxsize=4096, typed=True)
def cp_limits(successes, n, tail):
    """One-sided CP limits at a common tail; all returns are Python floats."""
    if (isinstance(n, bool) or not isinstance(n, Integral) or n < 1
            or isinstance(successes, bool) or not isinstance(successes, Integral)
            or not 0 <= successes <= n):
        raise ValueError("Invalid binomial count or planned denominator")
    tail = validate_alpha(tail)
    lower = 0. if successes == 0 else float(beta.ppf(tail, successes, n-successes+1))
    upper = 1. if successes == n else float(beta.ppf(1-tail, successes+1, n-successes))
    return lower, upper


def _labels(values):
    result = []
    for value in values:
        if value is None:
            result.append(None)
        elif isinstance(value, Integral) and not isinstance(value, bool) and value in (0, 1):
            result.append(int(value))
        else:
            raise ValueError("Labels must be integers 0/1 or None")
    if not result:
        raise ValueError("Planned denominator must be nonempty")
    return result


def discordance_counts(a, b):
    """Counts refer to a-b; partial pairs retain all compatible completions."""
    a, b = _labels(a), _labels(b)
    if len(a) != len(b):
        raise ValueError("Paired arrays must have equal planned lengths")
    counts = {"positive_definite": 0, "positive_possible": 0,
              "negative_definite": 0, "negative_possible": 0,
              "complete_pairs": 0, "complete_agreements": 0,
              "missing_a": a.count(None), "missing_b": b.count(None),
              "sum_minimum": 0, "sum_maximum": 0, "sum_complete": 0,
              "n_planned": len(a)}
    for x, y in zip(a, b):
        low = (0 if x is None else x) - (1 if y is None else y)
        high = (1 if x is None else x) - (0 if y is None else y)
        counts["positive_definite"] += int(low == high == 1)
        counts["positive_possible"] += int(high == 1)
        counts["negative_definite"] += int(low == high == -1)
        counts["negative_possible"] += int(low == -1)
        counts["sum_minimum"] += low
        counts["sum_maximum"] += high
        if x is not None and y is not None:
            counts["complete_pairs"] += 1
            counts["complete_agreements"] += int(x == y)
            counts["sum_complete"] += x-y
    counts["missing_pairs"] = len(a)-counts["complete_pairs"]
    return counts


def _paired(a, b, alpha, component_tail):
    counts = discordance_counts(a, b)
    n = counts["n_planned"]
    events = {}
    for name in ("positive", "negative"):
        definite, possible = counts[name+"_definite"], counts[name+"_possible"]
        events[name] = {"definite": definite, "possible": possible,
                        "lower": cp_limits(definite, n, component_tail)[0],
                        "upper": cp_limits(possible, n, component_tail)[1]}
    lower = events["positive"]["lower"]-events["negative"]["upper"]
    upper = events["positive"]["upper"]-events["negative"]["lower"]
    return {"method": "paired_discordance_cp_union_bound", "alpha": alpha,
            "component_tail": component_tail, "one_sided_confidence": 1-alpha,
            "two_sided_confidence": 1-2*alpha, "joint_D_S_coverage": False,
            "n_planned": n, "complete_pairs": counts["complete_pairs"],
            "missing_pairs": counts["missing_pairs"], "counts": counts,
            "event_probability_bounds": events, "lower": lower, "upper": upper,
            "bounds": [lower, upper],
            "identification_bounds": [counts["sum_minimum"]/n, counts["sum_maximum"]/n],
            "estimate_complete_pairs": (counts["sum_complete"]/counts["complete_pairs"]
                                        if counts["complete_pairs"] else None),
            "missingness_rule": "definite successes for lower; possible successes for upper; planned n"}


def paired_bounds(a, b, alpha=.025):
    """Bound E[a-b], with two CP component tails per directional decision."""
    alpha = validate_alpha(alpha)
    return _paired(a, b, alpha, alpha/2)


def _panels(values):
    if isinstance(values, Mapping):
        if any(isinstance(k, bool) or not isinstance(k, (str, Integral)) for k in values):
            raise ValueError("Panel keys must be strings or integers")
        panels = {str(k): v for k, v in values.items()}
        if len(panels) != len(values):
            raise ValueError("Panel keys collide after JSON normalization")
    else:
        panels = {str(i): v for i, v in enumerate(values, 1)}
    if len(panels) != 3:
        raise ValueError("Exactly three fixed control panels are required")
    return panels


def specificity_bounds(targetminus, targetplus, controlminusByPanel,
                       controlplusByPanel, alpha=.025):
    """Bound D_T minus the equal mean of THREE separate control-panel gaps.

    The target has 96 iid blocks and each fixed control stratum has 32 in the
    study. Equal smaller strata are accepted for synthetic tests. Label arrays
    are paired within each stratum; no cross-panel iid assumption is made.
    """
    alpha = validate_alpha(alpha)
    minus, plus = _panels(controlminusByPanel), _panels(controlplusByPanel)
    if set(minus) != set(plus):
        raise ValueError("Minus/plus panel keys must match")
    target = _paired(targetminus, targetplus, alpha/4, alpha/8)
    panels = {key: _paired(minus[key], plus[key], alpha/4, alpha/8)
              for key in sorted(minus)}
    sizes = [p["n_planned"] for p in panels.values()]
    if len(set(sizes)) != 1 or sum(sizes) != target["n_planned"]:
        raise ValueError("Three equal control strata must sum to target planned n")
    mean = lambda key: sum(p[key] for p in panels.values())/3
    lower, upper = target["lower"]-mean("upper"), target["upper"]-mean("lower")
    identification = [target["identification_bounds"][0]
                      -sum(p["identification_bounds"][1] for p in panels.values())/3,
                      target["identification_bounds"][1]
                      -sum(p["identification_bounds"][0] for p in panels.values())/3]
    estimates = [target["estimate_complete_pairs"]] + [p["estimate_complete_pairs"] for p in panels.values()]
    return {"method": "fixed_panel_stratified_paired_cp_union_bound", "alpha": alpha,
            "component_tail": alpha/8, "one_sided_confidence": 1-alpha,
            "two_sided_confidence": 1-2*alpha, "joint_D_S_coverage": False,
            "n_planned": target["n_planned"], "target": target, "panels": panels,
            "panel_weights": {key: 1/3 for key in panels},
            "lower": lower, "upper": upper, "bounds": [lower, upper],
            "identification_bounds": identification,
            "estimate_complete_pairs": (estimates[0]-sum(estimates[1:])/3
                                        if all(v is not None for v in estimates) else None),
            "scope": "equal mean of these three fixed panels; not a random-feature population",
            "missingness_rule": target["missingness_rule"]}
