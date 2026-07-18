"""Pure confirmatory-analysis primitives for the consciousness-SAE study.

The functions in this module do not read files, discover outcomes, or infer a
plan.  Callers must provide the exact expected plan IDs and already blinded /
unsealed endpoint rows.  Missing, duplicate, or unexpected IDs fail closed.
The C2 helpers represent the registered *active terminal probe* (first EOS or
the 64-token cap); they make no assumption that a numeric ``+64`` probe exists.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from experiments.consciousness_sae_changepoint.protocol import BOOTSTRAP_SEED


DOWNSTREAM_LAYERS = tuple(range(51, 79))
REQUIRED_SIGN_BRANCHES = (
    "never",
    "target_supp",
    "target_amp",
    "matched_supp",
    "matched_amp",
)


class AnalysisInputError(ValueError):
    """Raised when analysis inputs differ from the prospectively frozen plan."""


def validate_exact_plan_ids(
    rows: Iterable[Mapping[str, Any]],
    expected_plan_ids: Sequence[str],
    *,
    id_field: str = "plan_id",
) -> list[Mapping[str, Any]]:
    """Return rows in plan order, rejecting every ID mismatch.

    This is intentionally one-row-per-plan-ID.  Layered data should use the
    frozen composite row ID (for example plan/position/layer) rather than ask
    this validator to guess which repeated rows are legitimate.
    """

    expected = list(expected_plan_ids)
    if any(not isinstance(item_id, str) or not item_id for item_id in expected):
        raise AnalysisInputError("expected plan IDs must be nonempty strings")
    if len(expected) != len(set(expected)):
        raise AnalysisInputError("frozen expected plan IDs contain duplicates")

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise AnalysisInputError("every analysis row must be an object")
        item_id = row.get(id_field)
        if not isinstance(item_id, str) or not item_id:
            raise AnalysisInputError(f"row {id_field} must be a nonempty string")
        if item_id in by_id:
            raise AnalysisInputError(f"duplicate {id_field}: {item_id}")
        by_id[item_id] = row

    expected_set = set(expected)
    actual_set = set(by_id)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    if missing or unexpected:
        raise AnalysisInputError(
            "analysis plan-ID set differs from the frozen plan; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return [by_id[item_id] for item_id in expected]


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisInputError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AnalysisInputError(f"{label} must be finite")
    return result


def _branch_numbers(
    values: Mapping[str, Any],
    *,
    required: Sequence[str] = REQUIRED_SIGN_BRANCHES,
) -> dict[str, float]:
    if not isinstance(values, Mapping):
        raise AnalysisInputError("branch values must be a mapping")
    missing = [branch for branch in required if branch not in values]
    if missing:
        raise AnalysisInputError(f"required branch values missing: {missing}")
    return {branch: _finite_number(values[branch], branch) for branch in required}


def c1_block_contrast(natural_stance_by_branch: Mapping[str, Any]) -> float:
    """C1 target-minus-matched signed natural-stance contrast for one block."""

    values = _branch_numbers(natural_stance_by_branch)
    for branch, value in values.items():
        if value not in (-1.0, 0.0, 1.0):
            raise AnalysisInputError(f"natural stance for {branch} is not -1/0/+1")
    never = values["never"]
    target = (
        (values["target_supp"] - never) - (values["target_amp"] - never)
    ) / 2.0
    matched = (
        (values["matched_supp"] - never) - (values["matched_amp"] - never)
    ) / 2.0
    return target - matched


def _binary_branch_values(values: Mapping[str, Any]) -> dict[str, float]:
    required = ("target_supp", "target_amp", "matched_supp", "matched_amp")
    if not isinstance(values, Mapping):
        raise AnalysisInputError("binary query labels must be a mapping")
    missing = [branch for branch in required if branch not in values]
    if missing:
        raise AnalysisInputError(f"required binary-query branches missing: {missing}")
    normalized: dict[str, float] = {}
    for branch in required:
        value = values[branch]
        if type(value) is bool:
            normalized[branch] = float(value)
        elif type(value) is int and value in (0, 1):
            normalized[branch] = float(value)
        else:
            raise AnalysisInputError(f"binary label for {branch} must be bool or 0/1")
    return normalized


def c2a_block_contrast(active_terminal_query_by_branch: Mapping[str, Any]) -> float:
    """Target suppression-minus-amplification at the active terminal probe."""

    values = _binary_branch_values(active_terminal_query_by_branch)
    return values["target_supp"] - values["target_amp"]


def c2b_block_contrast(active_terminal_query_by_branch: Mapping[str, Any]) -> float:
    """Target-minus-matched query risk-difference contrast at terminal."""

    values = _binary_branch_values(active_terminal_query_by_branch)
    target = values["target_supp"] - values["target_amp"]
    matched = values["matched_supp"] - values["matched_amp"]
    return target - matched


def normalized_trapezoid_51_78(layer_values: Mapping[int, Any]) -> float:
    """Unit-depth normalized trapezoidal AUC over every layer 51 through 78."""

    if not isinstance(layer_values, Mapping):
        raise AnalysisInputError("layer_values must be a mapping")
    actual_layers = set(layer_values)
    expected_layers = set(DOWNSTREAM_LAYERS)
    missing = sorted(expected_layers - actual_layers)
    unexpected = sorted(actual_layers - expected_layers, key=str)
    if missing or unexpected:
        raise AnalysisInputError(
            "downstream layer grid must be exactly 51:78; "
            f"missing={missing}, unexpected={unexpected}"
        )
    values = {
        layer: _finite_number(layer_values[layer], f"layer {layer}")
        for layer in DOWNSTREAM_LAYERS
    }
    return sum(
        (values[layer] + values[layer + 1]) / 2.0 for layer in range(51, 78)
    ) / 27.0


def signed_specificity_layer_contrast(
    branch_scores: Mapping[str, Mapping[int, Any]],
) -> dict[int, float]:
    """Compute S_R(b,l,p) at all frozen downstream layers for one block."""

    if not isinstance(branch_scores, Mapping):
        raise AnalysisInputError("branch_scores must be a mapping")
    missing = [branch for branch in REQUIRED_SIGN_BRANCHES if branch not in branch_scores]
    if missing:
        raise AnalysisInputError(f"required mechanism branches missing: {missing}")
    per_branch: dict[str, dict[int, float]] = {}
    for branch in REQUIRED_SIGN_BRANCHES:
        raw = branch_scores[branch]
        # Calling the trapezoid validator here enforces the exact layer set;
        # retain normalized numeric rows for the pointwise contrast below.
        normalized_trapezoid_51_78(raw)
        per_branch[branch] = {
            layer: _finite_number(raw[layer], f"{branch} layer {layer}")
            for layer in DOWNSTREAM_LAYERS
        }

    result: dict[int, float] = {}
    for layer in DOWNSTREAM_LAYERS:
        never = per_branch["never"][layer]
        target = (
            (per_branch["target_supp"][layer] - never)
            - (per_branch["target_amp"][layer] - never)
        ) / 2.0
        matched = (
            (per_branch["matched_supp"][layer] - never)
            - (per_branch["matched_amp"][layer] - never)
        ) / 2.0
        result[layer] = target - matched
    return result


def final_logit_specificity_contrast(branch_scores: Mapping[str, Any]) -> float:
    values = _branch_numbers(branch_scores)
    never = values["never"]
    target = (
        (values["target_supp"] - never) - (values["target_amp"] - never)
    ) / 2.0
    matched = (
        (values["matched_supp"] - never) - (values["matched_amp"] - never)
    ) / 2.0
    return target - matched


def mechanism_block_contrast(
    j_scores_by_branch_layer: Mapping[str, Mapping[int, Any]],
    final_logit_scores_by_branch: Mapping[str, Any],
) -> dict[str, float]:
    layer_contrasts = signed_specificity_layer_contrast(j_scores_by_branch_layer)
    return {
        "post_depth_j_auc": normalized_trapezoid_51_78(layer_contrasts),
        "actual_final_logit": final_logit_specificity_contrast(
            final_logit_scores_by_branch
        ),
    }


def c3_block_contrast(
    probe0_report_polarity_j_scores: Mapping[str, Mapping[int, Any]],
    probe0_report_polarity_final_logits: Mapping[str, Any],
) -> dict[str, float]:
    """C3 composite block contrast at the immediate query-conditioned fork."""

    return mechanism_block_contrast(
        probe0_report_polarity_j_scores,
        probe0_report_polarity_final_logits,
    )


def c4_block_contrast(
    event0_consciousness_j_scores: Mapping[str, Mapping[int, Any]],
    event0_consciousness_final_logits: Mapping[str, Any],
) -> dict[str, float]:
    """C4 composite block contrast before any consciousness-query wording."""

    return mechanism_block_contrast(
        event0_consciousness_j_scores,
        event0_consciousness_final_logits,
    )


def holm_adjust(p_values: Mapping[str, Any]) -> dict[str, float]:
    """Return Holm step-down adjusted p-values with deterministic tie handling."""

    if not isinstance(p_values, Mapping) or not p_values:
        raise AnalysisInputError("Holm family must be a nonempty mapping")
    normalized: list[tuple[int, str, float]] = []
    for index, (claim, raw) in enumerate(p_values.items()):
        value = _finite_number(raw, f"p-value {claim}")
        if not 0.0 <= value <= 1.0:
            raise AnalysisInputError(f"p-value for {claim} is outside [0,1]")
        normalized.append((index, claim, value))
    ordered = sorted(normalized, key=lambda row: (row[2], row[0]))
    m = len(ordered)
    running = 0.0
    adjusted: dict[str, float] = {}
    for rank, (_index, claim, value) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * value))
        adjusted[claim] = running
    return {claim: adjusted[claim] for claim in p_values}


def holm_rejections(p_values: Mapping[str, Any], *, alpha: float = 0.05) -> dict[str, bool]:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    adjusted = holm_adjust(p_values)
    return {claim: value < alpha for claim, value in adjusted.items()}


def _values_and_weights(
    values: Sequence[Any], weights: Sequence[Any] | None
) -> tuple[list[float], list[float]]:
    x = [_finite_number(value, "cluster contrast") for value in values]
    if len(x) < 2:
        raise AnalysisInputError("at least two complete inference clusters are required")
    if weights is None:
        w = [1.0] * len(x)
    else:
        if len(weights) != len(x):
            raise AnalysisInputError("weights and cluster contrasts have different lengths")
        w = [_finite_number(value, "cluster occurrence weight") for value in weights]
        if any(value <= 0.0 for value in w):
            raise AnalysisInputError("cluster occurrence weights must be positive")
    return x, w


def _weighted_mean_and_se(values: Sequence[float], weights: Sequence[float]) -> tuple[float, float]:
    n = len(values)
    total_weight = sum(weights)
    mean = sum(weight * value for value, weight in zip(values, weights)) / total_weight
    # Cluster-robust standard error of the weighted mean.  Frequency weights
    # preserve duplicate occurrence influence while the finite correction uses
    # the number of independent rendered-prefix clusters.
    influence_ss = sum(
        (weight * (value - mean) / total_weight) ** 2
        for value, weight in zip(values, weights)
    )
    variance = n / (n - 1) * influence_ss
    return mean, math.sqrt(max(0.0, variance))


def collapse_duplicate_clusters(
    block_values: Sequence[Any],
    cluster_ids: Sequence[str],
) -> tuple[list[float], list[float], list[str]]:
    """Collapse exact rendered-prefix duplicates while preserving occurrences."""

    if len(block_values) != len(cluster_ids):
        raise AnalysisInputError("block values and cluster IDs have different lengths")
    grouped: dict[str, list[float]] = defaultdict(list)
    for value, cluster_id in zip(block_values, cluster_ids):
        if not isinstance(cluster_id, str) or not cluster_id:
            raise AnalysisInputError("cluster IDs must be nonempty strings")
        grouped[cluster_id].append(_finite_number(value, "block contrast"))
    ordered_ids = sorted(grouped)
    values = [sum(grouped[item_id]) / len(grouped[item_id]) for item_id in ordered_ids]
    weights = [float(len(grouped[item_id])) for item_id in ordered_ids]
    return values, weights, ordered_ids


def _bootstrap_t_distribution(
    values: Sequence[Any],
    *,
    weights: Sequence[Any] | None,
    n_resamples: int,
    seed: int,
) -> tuple[float, float, list[float]]:
    if not isinstance(n_resamples, int) or isinstance(n_resamples, bool) or n_resamples < 1:
        raise ValueError("n_resamples must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("bootstrap seed must be an integer")
    x, w = _values_and_weights(values, weights)
    estimate, standard_error = _weighted_mean_and_se(x, w)
    residuals = [value - estimate for value in x]
    rng = random.Random(seed)
    t_statistics: list[float] = []
    for _ in range(n_resamples):
        starred = [
            residual * (1.0 if rng.getrandbits(1) else -1.0)
            for residual in residuals
        ]
        star_mean, star_se = _weighted_mean_and_se(starred, w)
        t_statistics.append(star_mean / star_se if star_se > 0.0 else 0.0)
    return estimate, standard_error, t_statistics


def _observed_t(estimate: float, standard_error: float, boundary: float) -> float:
    if standard_error > 0.0:
        return (estimate - boundary) / standard_error
    if estimate > boundary:
        return math.inf
    if estimate < boundary:
        return -math.inf
    return 0.0


def _bootstrap_p(
    t_statistics: Sequence[float],
    observed_t: float,
    alternative: str,
) -> float:
    if alternative == "greater":
        extreme = sum(value >= observed_t for value in t_statistics)
    elif alternative == "less":
        extreme = sum(value <= observed_t for value in t_statistics)
    else:
        raise ValueError("alternative must be 'greater' or 'less'")
    return (extreme + 1.0) / (len(t_statistics) + 1.0)


def studentized_wild_bootstrap_test(
    values: Sequence[Any],
    *,
    boundary: float,
    alternative: str,
    weights: Sequence[Any] | None = None,
    n_resamples: int = 50_000,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float | int | str]:
    """One-sided studentized Rademacher wild prefix-cluster test."""

    boundary = _finite_number(boundary, "tested boundary")
    estimate, se, t_statistics = _bootstrap_t_distribution(
        values, weights=weights, n_resamples=n_resamples, seed=seed
    )
    observed_t = _observed_t(estimate, se, boundary)
    return {
        "estimate": estimate,
        "standard_error": se,
        "boundary": boundary,
        "alternative": alternative,
        "observed_t": observed_t,
        "p_value": _bootstrap_p(t_statistics, observed_t, alternative),
        "n_clusters": len(values),
        "n_resamples": n_resamples,
        "seed": seed,
    }


def tost_wild_bootstrap(
    values: Sequence[Any],
    *,
    margin: float,
    weights: Sequence[Any] | None = None,
    n_resamples: int = 50_000,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Two one-sided tests for the symmetric practical-equivalence region."""

    margin = _finite_number(margin, "equivalence margin")
    if margin <= 0.0:
        raise ValueError("equivalence margin must be positive")
    estimate, se, t_statistics = _bootstrap_t_distribution(
        values, weights=weights, n_resamples=n_resamples, seed=seed
    )
    lower_t = _observed_t(estimate, se, -margin)
    upper_t = _observed_t(estimate, se, margin)
    lower_p = _bootstrap_p(t_statistics, lower_t, "greater")
    upper_p = _bootstrap_p(t_statistics, upper_t, "less")
    return {
        "estimate": estimate,
        "standard_error": se,
        "margin": margin,
        "lower_boundary_p_value": lower_p,
        "upper_boundary_p_value": upper_p,
        "tost_p_value": max(lower_p, upper_p),
        "n_clusters": len(values),
        "n_resamples": n_resamples,
        "seed": seed,
    }


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot take a quantile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("quantile probability must be inside [0,1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def studentized_wild_bootstrap_interval(
    values: Sequence[Any],
    *,
    alpha: float = 0.05,
    weights: Sequence[Any] | None = None,
    n_resamples: int = 50_000,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float | int]:
    """Return one-sided lower and two-sided bootstrap-t interval primitives."""

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    estimate, se, t_statistics = _bootstrap_t_distribution(
        values, weights=weights, n_resamples=n_resamples, seed=seed
    )
    one_sided_lower = estimate - _quantile(t_statistics, 1.0 - alpha) * se
    two_sided_lower = estimate - _quantile(t_statistics, 1.0 - alpha / 2.0) * se
    two_sided_upper = estimate - _quantile(t_statistics, alpha / 2.0) * se
    return {
        "estimate": estimate,
        "standard_error": se,
        "one_sided_lower": one_sided_lower,
        "two_sided_lower": two_sided_lower,
        "two_sided_upper": two_sided_upper,
        "alpha": alpha,
        "n_clusters": len(values),
        "n_resamples": n_resamples,
        "seed": seed,
    }


def analyze_scalar_endpoint(
    values: Sequence[Any],
    *,
    margin: float,
    interval_alpha: float,
    weights: Sequence[Any] | None,
    n_resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Compute all raw tests/intervals from one shared deterministic draw set."""

    margin = _finite_number(margin, "endpoint margin")
    if margin <= 0.0:
        raise ValueError("endpoint margin must be positive")
    estimate, se, t_statistics = _bootstrap_t_distribution(
        values, weights=weights, n_resamples=n_resamples, seed=seed
    )
    material_t = _observed_t(estimate, se, margin)
    lower_t = _observed_t(estimate, se, -margin)
    upper_t = _observed_t(estimate, se, margin)
    material_p = _bootstrap_p(t_statistics, material_t, "greater")
    tost_lower_p = _bootstrap_p(t_statistics, lower_t, "greater")
    tost_upper_p = _bootstrap_p(t_statistics, upper_t, "less")
    return {
        "estimate": estimate,
        "standard_error": se,
        "margin": margin,
        "materiality_p_value": material_p,
        "tost_lower_boundary_p_value": tost_lower_p,
        "tost_upper_boundary_p_value": tost_upper_p,
        "tost_p_value": max(tost_lower_p, tost_upper_p),
        "familywise_one_sided_lower": estimate
        - _quantile(t_statistics, 1.0 - interval_alpha) * se,
        "familywise_equivalence_interval": [
            estimate - _quantile(t_statistics, 1.0 - interval_alpha / 2.0) * se,
            estimate - _quantile(t_statistics, interval_alpha / 2.0) * se,
        ],
        "n_clusters": len(values),
        "n_resamples": n_resamples,
        "seed": seed,
    }


def analyze_confirmatory_claims(
    *,
    c1: Sequence[Any],
    c2a_terminal: Sequence[Any],
    c2b_terminal: Sequence[Any],
    c3_j_auc: Sequence[Any],
    c3_final_logit: Sequence[Any],
    c4_j_auc: Sequence[Any],
    c4_final_logit: Sequence[Any],
    weights: Mapping[str, Sequence[Any] | None] | None = None,
    alpha: float = 0.05,
    n_resamples: int = 50_000,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Apply the frozen two-family materiality/equivalence algorithm.

    Inputs are already-computed independent-cluster contrasts.  Mechanism
    claims are intersection-union composites: their raw p-value is the maximum
    of J-AUC and actual-final-logit component p-values before Holm correction.
    """

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between zero and one")
    weights = dict(weights or {})
    values = {
        "C1": c1,
        "C2a": c2a_terminal,
        "C2b": c2b_terminal,
        "C3_j": c3_j_auc,
        "C3_final": c3_final_logit,
        "C4_j": c4_j_auc,
        "C4_final": c4_final_logit,
    }
    margins = {
        "C1": 0.15,
        "C2a": 0.30,
        "C2b": 0.15,
        "C3_j": 0.30,
        "C3_final": 0.30,
        "C4_j": 0.30,
        "C4_final": 0.30,
    }
    interval_multiplicity = {
        "C1": 3,
        "C2a": 3,
        "C2b": 3,
        "C3_j": 4,
        "C3_final": 4,
        "C4_j": 4,
        "C4_final": 4,
    }
    endpoints: dict[str, dict[str, Any]] = {}
    for name in values:
        endpoints[name] = analyze_scalar_endpoint(
            values[name],
            margin=margins[name],
            interval_alpha=alpha / interval_multiplicity[name],
            weights=weights.get(name),
            n_resamples=n_resamples,
            # Reuse the one frozen bootstrap seed for every endpoint.  This is
            # part of the registered analysis contract, not an invitation to
            # derive endpoint-specific seeds after outcomes are visible.
            seed=seed,
        )

    material_raw = {
        "C1": endpoints["C1"]["materiality_p_value"],
        "C2a": endpoints["C2a"]["materiality_p_value"],
        "C2b": endpoints["C2b"]["materiality_p_value"],
        "C3": max(
            endpoints["C3_j"]["materiality_p_value"],
            endpoints["C3_final"]["materiality_p_value"],
        ),
        "C4": max(
            endpoints["C4_j"]["materiality_p_value"],
            endpoints["C4_final"]["materiality_p_value"],
        ),
    }
    equivalence_raw = {
        "C1": endpoints["C1"]["tost_p_value"],
        "C2a": endpoints["C2a"]["tost_p_value"],
        "C2b": endpoints["C2b"]["tost_p_value"],
        "C3": max(endpoints["C3_j"]["tost_p_value"], endpoints["C3_final"]["tost_p_value"]),
        "C4": max(endpoints["C4_j"]["tost_p_value"], endpoints["C4_final"]["tost_p_value"]),
    }
    material_adjusted = {
        **holm_adjust({key: material_raw[key] for key in ("C1", "C2a", "C2b")}),
        **holm_adjust({key: material_raw[key] for key in ("C3", "C4")}),
    }
    equivalence_adjusted = {
        **holm_adjust({key: equivalence_raw[key] for key in ("C1", "C2a", "C2b")}),
        **holm_adjust({key: equivalence_raw[key] for key in ("C3", "C4")}),
    }

    material_components = {
        "C1": ("C1",),
        "C2a": ("C2a",),
        "C2b": ("C2b",),
        "C3": ("C3_j", "C3_final"),
        "C4": ("C4_j", "C4_final"),
    }
    decisions: dict[str, dict[str, bool]] = {}
    for claim, components in material_components.items():
        margin = margins[components[0]]
        material_interval_pass = all(
            endpoints[component]["familywise_one_sided_lower"] > margin
            for component in components
        )
        equivalence_interval_pass = all(
            endpoints[component]["familywise_equivalence_interval"][0] > -margin
            and endpoints[component]["familywise_equivalence_interval"][1] < margin
            for component in components
        )
        decisions[claim] = {
            "material": bool(
                material_adjusted[claim] < alpha and material_interval_pass
            ),
            "equivalent": bool(
                equivalence_adjusted[claim] < alpha and equivalence_interval_pass
            ),
            "material_interval_pass": material_interval_pass,
            "equivalence_interval_pass": equivalence_interval_pass,
        }

    return {
        "alpha": alpha,
        "bootstrap_seed": seed,
        "bootstrap_replicates": n_resamples,
        "c2_probe_definition": "active_terminal_first_eos_or_64_token_cap",
        "endpoints": endpoints,
        "raw_materiality_p_values": material_raw,
        "holm_materiality_p_values": material_adjusted,
        "raw_equivalence_p_values": equivalence_raw,
        "holm_equivalence_p_values": equivalence_adjusted,
        "decisions": decisions,
    }
