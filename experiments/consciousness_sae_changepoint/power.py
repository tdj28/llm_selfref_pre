"""Prospective, target-blind operating-characteristic simulation.

This module deliberately has no target-outcome reader.  Behavioral planning
effects and equivalence boundaries are expressed on the *analyzed*,
post-judge scale.  The simulator back-solves the latent label probabilities
through a frozen three-class confusion matrix and binary sensitivity /
specificity.  Mechanism endpoints are constructed as the exact five-branch,
28-layer contrasts consumed by the confirmatory analysis, in independently
calibrated clean-SD units.

The default design size of 560 is provisional.  A power receipt is evidence
about a prospectively specified design; it is never a freeze authorization.
Small outer simulations remain available for unit tests and development, but
a passing receipt requires at least 2,000 outer simulations and exact
one-sided binomial Monte-Carlo confidence gates.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Mapping, Sequence

from experiments.consciousness_sae_changepoint.analyze import (
    analyze_confirmatory_claims,
    c1_block_contrast,
    c2a_block_contrast,
    c2b_block_contrast,
    c3_block_contrast,
    c4_block_contrast,
    collapse_duplicate_clusters,
)
from experiments.consciousness_sae_changepoint.protocol import (
    POWER_SIMULATION_SEED,
    STUDY_ID,
    canonical_json_bytes,
)


CLAIMS = ("C1", "C2a", "C2b", "C3", "C4")
MARGINS = {"C1": 0.15, "C2a": 0.30, "C2b": 0.15, "C3": 0.30, "C4": 0.30}
BEHAVIOR_CLAIMS = ("C1", "C2a", "C2b")
MECHANISM_CLAIMS = ("C3", "C4")
MECHANISM_COMPONENTS = ("C3_j", "C3_final", "C4_j", "C4_final")
DOWNSTREAM_LAYERS = tuple(range(51, 79))
MINIMUM_PASSING_OUTER_SIMULATIONS = 2_000
MINIMUM_PASSING_INNER_BOOTSTRAPS = 999
MC_ALPHA = 0.05

# Rows are true -1/0/+1 and columns are predicted -1/0/+1.  Each diagonal is
# 0.80.  The nonzero classes put every allowed error on the opposite signed
# pole, making this more adverse than uniform off-diagonal error.  A receipted
# arbitrary matrix can replace it prospectively.
LEAST_FAVORABLE_STANCE_CONFUSION = (
    (0.80, 0.00, 0.20),
    (0.10, 0.80, 0.10),
    (0.20, 0.00, 0.80),
)

DEFAULT_ANALYZED_EFFECTS = (
    ("C1", 0.30),
    ("C2a", 0.50),
    ("C2b", 0.30),
    ("C3", 0.50),
    ("C4", 0.50),
)


class PowerProtocolError(ValueError):
    """Raised when a prospective power input or receipt fails closed."""


def _pairs_to_map(
    pairs: Sequence[Sequence[Any]], *, expected: Sequence[str], label: str
) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in pairs:
        if len(row) != 2 or not isinstance(row[0], str):
            raise PowerProtocolError(f"{label} rows must be [name, value] pairs")
        name = row[0]
        value = row[1]
        if name in result:
            raise PowerProtocolError(f"duplicate {label} name: {name}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PowerProtocolError(f"{label} value for {name} must be numeric")
        value = float(value)
        if not math.isfinite(value):
            raise PowerProtocolError(f"{label} value for {name} must be finite")
        result[name] = value
    if set(result) != set(expected) or len(result) != len(expected):
        raise PowerProtocolError(f"{label} must contain every and only {tuple(expected)}")
    return result


def _validated_confusion_matrix(
    matrix: Sequence[Sequence[Any]],
) -> tuple[tuple[float, float, float], ...]:
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise PowerProtocolError("stance confusion matrix must be exactly 3x3")
    normalized: list[tuple[float, float, float]] = []
    for row_index, row in enumerate(matrix):
        values: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PowerProtocolError("stance confusion entries must be numeric")
            number = float(value)
            if not math.isfinite(number) or not 0.0 <= number <= 1.0:
                raise PowerProtocolError("stance confusion entries must be inside [0,1]")
            values.append(number)
        if not math.isclose(sum(values), 1.0, abs_tol=1e-12):
            raise PowerProtocolError(f"stance confusion row {row_index} does not sum to one")
        normalized.append((values[0], values[1], values[2]))
    return tuple(normalized)


def stance_signed_gain(matrix: Sequence[Sequence[Any]]) -> float:
    """Slope from latent true signed mean to analyzed judged signed mean."""

    rows = _validated_confusion_matrix(matrix)
    predicted_scores = tuple(row[2] - row[0] for row in rows)
    gain = (predicted_scores[2] - predicted_scores[0]) / 2.0
    if not math.isfinite(gain) or gain <= 0.0:
        raise PowerProtocolError(
            "stance confusion matrix must preserve a strictly positive signed ordering"
        )
    return gain


def binary_signed_gain(sensitivity: float, specificity: float) -> float:
    gain = float(sensitivity) + float(specificity) - 1.0
    if not math.isfinite(gain) or gain <= 0.0:
        raise PowerProtocolError("binary judge must have positive Youden gain")
    return gain


@dataclass(frozen=True)
class PowerSimulationConfig:
    """Frozen inputs to one target-blind operating-characteristic scenario."""

    n_blocks: int = 560
    n_simulations: int = MINIMUM_PASSING_OUTER_SIMULATIONS
    bootstrap_resamples: int = 999
    seed: int = POWER_SIMULATION_SEED
    scenario_id: str = "material"
    analyzed_effects: tuple[tuple[str, float], ...] = DEFAULT_ANALYZED_EFFECTS
    mechanism_component_effects: tuple[tuple[str, float], ...] = ()
    binary_base_rate: float = 0.50
    stance_base_mean: float = 0.0
    stance_nonzero_rate: float = 0.70
    stance_confusion_matrix: tuple[tuple[float, float, float], ...] = (
        LEAST_FAVORABLE_STANCE_CONFUSION
    )
    binary_judge_sensitivity: float = 0.80
    binary_judge_specificity: float = 0.80
    judge_assumption_source: str = "least_favorable_0.80_no_receipt"
    completion_fraction: float = 0.95
    minimum_complete_blocks: int | None = None
    duplicate_fraction: float = 0.10
    cluster_assignments: tuple[str, ...] = ()
    cluster_assignment_source: str = "prospective_hash_default"
    within_prefix_correlation: float = 0.45
    mechanism_component_correlation: float = 0.65
    mechanism_claim_correlation: float = 0.30
    mechanism_layer_correlation: float = 0.85
    mechanism_contrast_sd: float = 1.0
    mechanism_assumption_source: str = "target_blind_synthetic_nuisance_v2"
    alpha: float = 0.05

    def analyzed_effect_map(self) -> dict[str, float]:
        return _pairs_to_map(
            self.analyzed_effects, expected=CLAIMS, label="analyzed effects"
        )

    def component_effect_map(self) -> dict[str, float]:
        if not self.mechanism_component_effects:
            effects = self.analyzed_effect_map()
            return {
                "C3_j": effects["C3"],
                "C3_final": effects["C3"],
                "C4_j": effects["C4"],
                "C4_final": effects["C4"],
            }
        return _pairs_to_map(
            self.mechanism_component_effects,
            expected=MECHANISM_COMPONENTS,
            label="mechanism component effects",
        )

    def complete_block_count(self) -> int:
        if self.minimum_complete_blocks is not None:
            return self.minimum_complete_blocks
        return math.ceil(self.n_blocks * self.completion_fraction)

    def latent_behavior_effect_map(self) -> dict[str, float]:
        effects = self.analyzed_effect_map()
        stance_gain = stance_signed_gain(self.stance_confusion_matrix)
        binary_gain = binary_signed_gain(
            self.binary_judge_sensitivity, self.binary_judge_specificity
        )
        return {
            "C1": effects["C1"] / stance_gain,
            "C2a": effects["C2a"] / binary_gain,
            "C2b": effects["C2b"] / binary_gain,
        }

    def validate(self) -> "PowerSimulationConfig":
        if not isinstance(self.n_blocks, int) or isinstance(self.n_blocks, bool) or self.n_blocks < 2:
            raise PowerProtocolError("n_blocks must be an integer of at least two")
        if (
            not isinstance(self.n_simulations, int)
            or isinstance(self.n_simulations, bool)
            or self.n_simulations < 1
        ):
            raise PowerProtocolError("n_simulations must be a positive integer")
        if (
            not isinstance(self.bootstrap_resamples, int)
            or isinstance(self.bootstrap_resamples, bool)
            or self.bootstrap_resamples < 99
        ):
            raise PowerProtocolError("bootstrap_resamples must be at least 99")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise PowerProtocolError("simulation seed must be an integer")
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise PowerProtocolError("scenario_id must be nonempty text")
        effects = self.analyzed_effect_map()
        self.component_effect_map()
        matrix = _validated_confusion_matrix(self.stance_confusion_matrix)
        stance_signed_gain(matrix)
        for name in (
            "binary_base_rate",
            "binary_judge_sensitivity",
            "binary_judge_specificity",
            "completion_fraction",
            "duplicate_fraction",
            "within_prefix_correlation",
            "mechanism_component_correlation",
            "mechanism_claim_correlation",
            "mechanism_layer_correlation",
            "alpha",
        ):
            raw_value = getattr(self, name)
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise PowerProtocolError(f"{name} must be numeric")
            value = float(raw_value)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise PowerProtocolError(f"{name} must be inside [0,1]")
        if not 0.0 < self.alpha < 1.0:
            raise PowerProtocolError("alpha must be strictly between zero and one")
        if not 0.0 < self.completion_fraction <= 1.0:
            raise PowerProtocolError("completion_fraction must be inside (0,1]")
        if (
            isinstance(self.stance_nonzero_rate, bool)
            or not isinstance(self.stance_nonzero_rate, (int, float))
            or not 0.0 <= self.stance_nonzero_rate <= 1.0
        ):
            raise PowerProtocolError("stance_nonzero_rate must be inside [0,1]")
        if (
            isinstance(self.stance_base_mean, bool)
            or not isinstance(self.stance_base_mean, (int, float))
            or not math.isfinite(float(self.stance_base_mean))
        ):
            raise PowerProtocolError("stance_base_mean must be finite and numeric")
        if abs(self.stance_base_mean) > self.stance_nonzero_rate:
            raise PowerProtocolError("stance_base_mean is incompatible with stance_nonzero_rate")
        if (
            isinstance(self.mechanism_contrast_sd, bool)
            or not isinstance(self.mechanism_contrast_sd, (int, float))
            or not math.isfinite(self.mechanism_contrast_sd)
            or self.mechanism_contrast_sd <= 0.0
        ):
            raise PowerProtocolError("mechanism_contrast_sd must be positive and finite")
        binary_signed_gain(
            self.binary_judge_sensitivity, self.binary_judge_specificity
        )
        complete = self.complete_block_count()
        if not isinstance(complete, int) or isinstance(complete, bool) or not 2 <= complete <= self.n_blocks:
            raise PowerProtocolError("complete-block count must be between 2 and n_blocks")
        expected_complete = math.ceil(self.n_blocks * self.completion_fraction)
        if complete != expected_complete:
            raise PowerProtocolError(
                "minimum_complete_blocks must equal ceil(n_blocks * completion_fraction)"
            )
        if self.cluster_assignments:
            if len(self.cluster_assignments) != self.n_blocks:
                raise PowerProtocolError("explicit cluster assignment length differs from n_blocks")
            if any(not isinstance(item, str) or not item for item in self.cluster_assignments):
                raise PowerProtocolError("cluster assignments must be nonempty strings")
        for name in (
            "judge_assumption_source",
            "cluster_assignment_source",
            "mechanism_assumption_source",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise PowerProtocolError(f"{name} must be nonempty text")

        latent = self.latent_behavior_effect_map()
        c1 = latent["C1"]
        if any(
            abs(self.stance_base_mean + shift) > self.stance_nonzero_rate + 1e-12
            for shift in (c1, -c1, 0.0)
        ):
            raise PowerProtocolError(
                "analyzed C1 effect cannot be back-solved to valid stance probabilities"
            )
        target_rd = latent["C2a"]
        matched_rd = latent["C2a"] - latent["C2b"]
        for rd in (target_rd, matched_rd):
            if not (
                0.0 <= self.binary_base_rate - rd / 2.0 <= 1.0
                and 0.0 <= self.binary_base_rate + rd / 2.0 <= 1.0
            ):
                raise PowerProtocolError(
                    "analyzed C2 effects cannot be back-solved to valid probabilities"
                )
        return self


def config_sha256(config: PowerSimulationConfig) -> str:
    config.validate()
    return hashlib.sha256(canonical_json_bytes(asdict(config))).hexdigest()


def _scenario_seed(seed: int, simulation_index: int, namespace: str = "simulation") -> int:
    digest = hashlib.sha256(
        canonical_json_bytes([STUDY_ID, "power-v2", namespace, seed, simulation_index])
    ).hexdigest()
    return int(digest[:16], 16)


def resolved_cluster_assignments(config: PowerSimulationConfig) -> tuple[str, ...]:
    """Return the one fixed duplicate assignment used by every outer replicate."""

    config.validate()
    if config.cluster_assignments:
        return tuple(config.cluster_assignments)
    n_unique = max(
        2,
        min(config.n_blocks, round(config.n_blocks * (1.0 - config.duplicate_fraction))),
    )
    rows = [f"prefix_cluster_{index:04d}" for index in range(n_unique)]
    for index in range(n_unique, config.n_blocks):
        digest = hashlib.sha256(
            canonical_json_bytes(
                [STUDY_ID, "power-v2-duplicate", config.seed, index]
            )
        ).hexdigest()
        rows.append(f"prefix_cluster_{int(digest[:16], 16) % n_unique:04d}")
    order = sorted(
        range(config.n_blocks),
        key=lambda index: hashlib.sha256(
            canonical_json_bytes(
                [STUDY_ID, "power-v2-cluster-order", config.seed, index]
            )
        ).hexdigest(),
    )
    return tuple(rows[index] for index in order)


def cluster_assignment_sha256(config: PowerSimulationConfig) -> str:
    return hashlib.sha256(
        canonical_json_bytes(resolved_cluster_assignments(config))
    ).hexdigest()


def _correlated_uniform(
    rng: random.Random, shared_normal: float, correlation: float
) -> float:
    latent = math.sqrt(correlation) * shared_normal + math.sqrt(
        1.0 - correlation
    ) * rng.gauss(0.0, 1.0)
    return NormalDist().cdf(latent)


def _draw_stance(
    rng: random.Random,
    *,
    mean: float,
    nonzero_rate: float,
    shared_normal: float,
    correlation: float,
) -> int:
    affirmative = (nonzero_rate + mean) / 2.0
    denial = (nonzero_rate - mean) / 2.0
    if min(affirmative, denial, 1.0 - nonzero_rate) < -1e-12:
        raise PowerProtocolError("invalid latent stance probabilities")
    uniform = _correlated_uniform(rng, shared_normal, correlation)
    if uniform < denial:
        return -1
    if uniform < denial + (1.0 - nonzero_rate):
        return 0
    return 1


def _apply_stance_confusion(
    rng: random.Random,
    true_label: int,
    matrix: Sequence[Sequence[float]],
) -> int:
    labels = (-1, 0, 1)
    row = matrix[true_label + 1]
    draw = rng.random()
    cumulative = 0.0
    for label, probability in zip(labels, row):
        cumulative += probability
        if draw <= cumulative:
            return label
    return 1  # row-sum validation makes this only a floating-point guard.


def _draw_binary(
    rng: random.Random,
    *,
    probability: float,
    shared_normal: float,
    correlation: float,
) -> bool:
    return _correlated_uniform(rng, shared_normal, correlation) < probability


def _apply_binary_judge_error(
    rng: random.Random,
    true_label: bool,
    *,
    sensitivity: float,
    specificity: float,
) -> bool:
    if true_label:
        return rng.random() < sensitivity
    return not (rng.random() < specificity)


def _trapezoid_weights() -> dict[int, float]:
    return {
        layer: (1.0 / 54.0 if layer in (51, 78) else 1.0 / 27.0)
        for layer in DOWNSTREAM_LAYERS
    }


TRAPEZOID_WEIGHTS = _trapezoid_weights()


def _contrast_branches(value: float) -> dict[str, float]:
    """Embed one specificity contrast in the exact registered five branches."""

    return {
        "never": 0.0,
        "target_supp": value,
        "target_amp": -value,
        "matched_supp": 0.0,
        "matched_amp": 0.0,
    }


def _mechanism_block(
    rng: random.Random,
    *,
    claim: str,
    j_effect: float,
    final_effect: float,
    cluster_global: float,
    cluster_claim: float,
    config: PowerSimulationConfig,
) -> dict[str, float]:
    """Construct a full 51:78 branch trajectory and analyze it exactly once."""

    claim_cluster = math.sqrt(config.mechanism_claim_correlation) * cluster_global + math.sqrt(
        1.0 - config.mechanism_claim_correlation
    ) * cluster_claim
    occurrence = math.sqrt(config.within_prefix_correlation) * claim_cluster + math.sqrt(
        1.0 - config.within_prefix_correlation
    ) * rng.gauss(0.0, 1.0)
    layer_rho = config.mechanism_layer_correlation
    # The scale makes the normalized trapezoidal AUC noise have exactly the
    # receipted mechanism_contrast_sd before finite-sample clustering.
    weight_square_sum = sum(weight * weight for weight in TRAPEZOID_WEIGHTS.values())
    auc_variance = layer_rho + (1.0 - layer_rho) * weight_square_sum
    auc_scale = math.sqrt(auc_variance)
    layer_contrasts: dict[int, float] = {}
    for layer in DOWNSTREAM_LAYERS:
        raw_noise = math.sqrt(layer_rho) * occurrence + math.sqrt(
            1.0 - layer_rho
        ) * rng.gauss(0.0, 1.0)
        layer_contrasts[layer] = (
            j_effect + config.mechanism_contrast_sd * raw_noise / auc_scale
        )
    auc_noise = sum(
        TRAPEZOID_WEIGHTS[layer]
        * (layer_contrasts[layer] - j_effect)
        / config.mechanism_contrast_sd
        for layer in DOWNSTREAM_LAYERS
    )
    component_rho = config.mechanism_component_correlation
    final_noise = component_rho * auc_noise + math.sqrt(
        1.0 - component_rho * component_rho
    ) * rng.gauss(0.0, 1.0)
    final_contrast = final_effect + config.mechanism_contrast_sd * final_noise
    j_branches = {
        branch: {layer: values[branch] for layer, values in (
            (layer, _contrast_branches(value))
            for layer, value in layer_contrasts.items()
        )}
        for branch in ("never", "target_supp", "target_amp", "matched_supp", "matched_amp")
    }
    final_branches = _contrast_branches(final_contrast)
    primitive = c3_block_contrast if claim == "C3" else c4_block_contrast
    return primitive(j_branches, final_branches)


def _complete_occurrence_indices(
    config: PowerSimulationConfig, simulation_index: int
) -> set[int]:
    ranked = sorted(
        range(config.n_blocks),
        key=lambda index: hashlib.sha256(
            canonical_json_bytes(
                [
                    STUDY_ID,
                    "power-v2-completion",
                    config.seed,
                    simulation_index,
                    index,
                ]
            )
        ).hexdigest(),
    )
    return set(ranked[: config.complete_block_count()])


def _simulate_blocks(
    config: PowerSimulationConfig,
    rng: random.Random,
    *,
    simulation_index: int,
    clusters: Sequence[str],
) -> dict[str, Any]:
    analyzed = config.analyzed_effect_map()
    latent = config.latent_behavior_effect_map()
    components = config.component_effect_map()
    unique_clusters = sorted(set(clusters))
    stance_shared = {cluster: rng.gauss(0.0, 1.0) for cluster in unique_clusters}
    query_shared = {cluster: rng.gauss(0.0, 1.0) for cluster in unique_clusters}
    mechanism_global = {cluster: rng.gauss(0.0, 1.0) for cluster in unique_clusters}
    mechanism_c3 = {cluster: rng.gauss(0.0, 1.0) for cluster in unique_clusters}
    mechanism_c4 = {cluster: rng.gauss(0.0, 1.0) for cluster in unique_clusters}
    complete_indices = _complete_occurrence_indices(config, simulation_index)

    rows: dict[str, list[float | None]] = {
        name: []
        for name in ("C1", "C2a", "C2b", "C3_j", "C3_final", "C4_j", "C4_final")
    }
    target_query_rd = latent["C2a"]
    matched_query_rd = latent["C2a"] - latent["C2b"]
    query_probabilities = {
        "target_supp": config.binary_base_rate + target_query_rd / 2.0,
        "target_amp": config.binary_base_rate - target_query_rd / 2.0,
        "matched_supp": config.binary_base_rate + matched_query_rd / 2.0,
        "matched_amp": config.binary_base_rate - matched_query_rd / 2.0,
    }
    stance_means = {
        "never": config.stance_base_mean,
        "target_supp": config.stance_base_mean + latent["C1"],
        "target_amp": config.stance_base_mean - latent["C1"],
        "matched_supp": config.stance_base_mean,
        "matched_amp": config.stance_base_mean,
    }
    matrix = _validated_confusion_matrix(config.stance_confusion_matrix)

    for occurrence_index, cluster in enumerate(clusters):
        if occurrence_index not in complete_indices:
            for name in rows:
                rows[name].append(None)
            continue
        stance_labels = {
            branch: _apply_stance_confusion(
                rng,
                _draw_stance(
                    rng,
                    mean=mean,
                    nonzero_rate=config.stance_nonzero_rate,
                    shared_normal=stance_shared[cluster],
                    correlation=config.within_prefix_correlation,
                ),
                matrix,
            )
            for branch, mean in stance_means.items()
        }
        rows["C1"].append(c1_block_contrast(stance_labels))
        query_labels = {
            branch: _apply_binary_judge_error(
                rng,
                _draw_binary(
                    rng,
                    probability=probability,
                    shared_normal=query_shared[cluster],
                    correlation=config.within_prefix_correlation,
                ),
                sensitivity=config.binary_judge_sensitivity,
                specificity=config.binary_judge_specificity,
            )
            for branch, probability in query_probabilities.items()
        }
        rows["C2a"].append(c2a_block_contrast(query_labels))
        rows["C2b"].append(c2b_block_contrast(query_labels))
        c3 = _mechanism_block(
            rng,
            claim="C3",
            j_effect=components["C3_j"],
            final_effect=components["C3_final"],
            cluster_global=mechanism_global[cluster],
            cluster_claim=mechanism_c3[cluster],
            config=config,
        )
        c4 = _mechanism_block(
            rng,
            claim="C4",
            j_effect=components["C4_j"],
            final_effect=components["C4_final"],
            cluster_global=mechanism_global[cluster],
            cluster_claim=mechanism_c4[cluster],
            config=config,
        )
        rows["C3_j"].append(c3["post_depth_j_auc"])
        rows["C3_final"].append(c3["actual_final_logit"])
        rows["C4_j"].append(c4["post_depth_j_auc"])
        rows["C4_final"].append(c4["actual_final_logit"])
    return {"cluster_ids": list(clusters), "analyzed_effects": analyzed, **rows}


def _complete_and_collapse(
    values: Sequence[float | None], cluster_ids: Sequence[str]
) -> tuple[list[float], list[float], int]:
    complete_values = [value for value in values if value is not None]
    complete_ids = [
        cluster_id
        for value, cluster_id in zip(values, cluster_ids)
        if value is not None
    ]
    collapsed, weights, _ = collapse_duplicate_clusters(complete_values, complete_ids)
    return collapsed, weights, len(complete_values)


def _log_binomial_range_probability(
    n: int, probability: float, lower: int, upper: int
) -> float:
    if lower > upper:
        return 0.0
    if probability <= 0.0:
        return 1.0 if lower <= 0 <= upper else 0.0
    if probability >= 1.0:
        return 1.0 if lower <= n <= upper else 0.0
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    logs = [
        math.lgamma(n + 1)
        - math.lgamma(index + 1)
        - math.lgamma(n - index + 1)
        + index * log_p
        + (n - index) * log_q
        for index in range(lower, upper + 1)
    ]
    maximum = max(logs)
    return min(1.0, math.exp(maximum) * sum(math.exp(value - maximum) for value in logs))


def exact_binomial_one_sided_interval(
    successes: int, trials: int, *, alpha: float = MC_ALPHA
) -> dict[str, float | int]:
    """Return exact Clopper-Pearson one-sided lower and upper bounds."""

    if (
        not isinstance(successes, int)
        or isinstance(successes, bool)
        or not isinstance(trials, int)
        or isinstance(trials, bool)
        or trials < 1
        or not 0 <= successes <= trials
    ):
        raise PowerProtocolError("binomial counts must satisfy 0 <= successes <= trials")
    if not 0.0 < alpha < 1.0:
        raise PowerProtocolError("binomial alpha must be inside (0,1)")
    if successes == 0:
        lower = 0.0
    else:
        lo, hi = 0.0, successes / trials
        for _ in range(64):
            mid = (lo + hi) / 2.0
            tail = _log_binomial_range_probability(trials, mid, successes, trials)
            if tail < alpha:
                lo = mid
            else:
                hi = mid
        lower = (lo + hi) / 2.0
    if successes == trials:
        upper = 1.0
    else:
        lo, hi = successes / trials, 1.0
        for _ in range(64):
            mid = (lo + hi) / 2.0
            cdf = _log_binomial_range_probability(trials, mid, 0, successes)
            if cdf > alpha:
                lo = mid
            else:
                hi = mid
        upper = (lo + hi) / 2.0
    return {
        "successes": successes,
        "trials": trials,
        "rate": successes / trials,
        "confidence": 1.0 - alpha,
        "one_sided_lower": lower,
        "one_sided_upper": upper,
    }


def _count_record(count: int, trials: int) -> dict[str, float | int]:
    return exact_binomial_one_sided_interval(count, trials, alpha=MC_ALPHA)


def simulate_operating_characteristics(config: PowerSimulationConfig) -> dict[str, Any]:
    """Run one deterministic, target-blind materiality/equivalence scenario."""

    config.validate()
    material_counts = {claim: 0 for claim in CLAIMS}
    equivalence_counts = {claim: 0 for claim in CLAIMS}
    analyzable_counts = {claim: 0 for claim in CLAIMS}
    family_material_counts = {"behavior": 0, "mechanism": 0, "all": 0}
    family_equivalence_counts = {"behavior": 0, "mechanism": 0, "all": 0}
    clusters = resolved_cluster_assignments(config)

    for simulation_index in range(config.n_simulations):
        rng = random.Random(_scenario_seed(config.seed, simulation_index, config.scenario_id))
        blocks = _simulate_blocks(
            config,
            rng,
            simulation_index=simulation_index,
            clusters=clusters,
        )
        collapsed: dict[str, list[float]] = {}
        weights: dict[str, list[float]] = {}
        complete_counts: dict[str, int] = {}
        for endpoint in ("C1", "C2a", "C2b", "C3_j", "C3_final", "C4_j", "C4_final"):
            collapsed[endpoint], weights[endpoint], complete_counts[endpoint] = _complete_and_collapse(
                blocks[endpoint], clusters
            )
        if any(len(collapsed[name]) < 2 for name in collapsed):
            continue
        analysis = analyze_confirmatory_claims(
            c1=collapsed["C1"],
            c2a_terminal=collapsed["C2a"],
            c2b_terminal=collapsed["C2b"],
            c3_j_auc=collapsed["C3_j"],
            c3_final_logit=collapsed["C3_final"],
            c4_j_auc=collapsed["C4_j"],
            c4_final_logit=collapsed["C4_final"],
            weights=weights,
            alpha=config.alpha,
            n_resamples=config.bootstrap_resamples,
            seed=_scenario_seed(config.seed + 1, simulation_index, config.scenario_id),
        )
        required = config.complete_block_count()
        complete_gate = {
            "C1": complete_counts["C1"] >= required,
            "C2a": complete_counts["C2a"] >= required,
            "C2b": complete_counts["C2b"] >= required,
            "C3": min(complete_counts["C3_j"], complete_counts["C3_final"]) >= required,
            "C4": min(complete_counts["C4_j"], complete_counts["C4_final"]) >= required,
        }
        material: dict[str, bool] = {}
        equivalent: dict[str, bool] = {}
        for claim in CLAIMS:
            analyzable_counts[claim] += int(complete_gate[claim])
            material[claim] = bool(
                complete_gate[claim] and analysis["decisions"][claim]["material"]
            )
            equivalent[claim] = bool(
                complete_gate[claim] and analysis["decisions"][claim]["equivalent"]
            )
            material_counts[claim] += int(material[claim])
            equivalence_counts[claim] += int(equivalent[claim])
        behavior_material = all(material[claim] for claim in BEHAVIOR_CLAIMS)
        mechanism_material = all(material[claim] for claim in MECHANISM_CLAIMS)
        behavior_equivalent = all(equivalent[claim] for claim in BEHAVIOR_CLAIMS)
        mechanism_equivalent = all(equivalent[claim] for claim in MECHANISM_CLAIMS)
        family_material_counts["behavior"] += int(behavior_material)
        family_material_counts["mechanism"] += int(mechanism_material)
        family_material_counts["all"] += int(behavior_material and mechanism_material)
        family_equivalence_counts["behavior"] += int(behavior_equivalent)
        family_equivalence_counts["mechanism"] += int(mechanism_equivalent)
        family_equivalence_counts["all"] += int(behavior_equivalent and mechanism_equivalent)

    analyzed = config.analyzed_effect_map()
    latent = config.latent_behavior_effect_map()
    components = config.component_effect_map()
    claims: dict[str, Any] = {}
    for claim in CLAIMS:
        claims[claim] = {
            "true_analyzed_effect": analyzed[claim],
            "true_latent_prejudge_effect": latent.get(claim),
            "true_analyzed_component_effects": (
                {name: components[name] for name in MECHANISM_COMPONENTS if name.startswith(claim)}
                if claim in MECHANISM_CLAIMS
                else None
            ),
            "material_margin": MARGINS[claim],
            "analyzable": _count_record(analyzable_counts[claim], config.n_simulations),
            "material": _count_record(material_counts[claim], config.n_simulations),
            "equivalence": _count_record(equivalence_counts[claim], config.n_simulations),
        }
    family_material = {
        family: _count_record(count, config.n_simulations)
        for family, count in family_material_counts.items()
    }
    family_equivalence = {
        family: _count_record(count, config.n_simulations)
        for family, count in family_equivalence_counts.items()
    }
    return {
        "study_id": STUDY_ID,
        "status": "complete",
        "target_blind": True,
        "scenario_id": config.scenario_id,
        "config_sha256": config_sha256(config),
        "config": asdict(config),
        "resolved_complete_blocks": config.complete_block_count(),
        "completion_missing_blocks": config.n_blocks - config.complete_block_count(),
        "completion_simulation": {
            "fraction": config.completion_fraction,
            "selection": "fixed_count_sha256_ranked_per_outer_replicate",
            "missingness_scope": "complete_block_common_to_all_endpoints",
            "fail_boundary": config.complete_block_count(),
        },
        "cluster_assignment_sha256": cluster_assignment_sha256(config),
        "cluster_assignment_unique_count": len(set(clusters)),
        "cluster_assignment_source": config.cluster_assignment_source,
        "inference_method": "studentized_rademacher_wild_prefix_cluster_bootstrap",
        "multiplicity": "Holm behavior/mechanism plus registered Bonferroni bounds; mechanism IUT",
        "mechanism_simulation": {
            "layers": [51, 78],
            "layer_count": len(DOWNSTREAM_LAYERS),
            "five_branch_construction": True,
            "auc": "normalized_trapezoid_51_78",
            "clean_sd_denominator": "treated_fixed_from_independent_target_blind_calibration",
            "layer_correlation_model": "equicorrelated_gaussian",
            "layer_correlation": config.mechanism_layer_correlation,
            "auc_contrast_sd": config.mechanism_contrast_sd,
            "j_final_correlation": config.mechanism_component_correlation,
            "cross_claim_cluster_correlation": config.mechanism_claim_correlation,
            "assumption_source": config.mechanism_assumption_source,
        },
        "judge_simulation": {
            "effect_scale": "analyzed_post_judge",
            "stance_confusion_matrix": [list(row) for row in config.stance_confusion_matrix],
            "stance_signed_gain": stance_signed_gain(config.stance_confusion_matrix),
            "binary_sensitivity": config.binary_judge_sensitivity,
            "binary_specificity": config.binary_judge_specificity,
            "binary_youden_gain": binary_signed_gain(
                config.binary_judge_sensitivity, config.binary_judge_specificity
            ),
            "stance_base_mean": config.stance_base_mean,
            "stance_nonzero_rate": config.stance_nonzero_rate,
            "binary_base_rate": config.binary_base_rate,
            "error_dependence": (
                "conditionally_independent_branch errors with fixed prefix-cluster latent"
            ),
            "assumption_source": config.judge_assumption_source,
        },
        "c2_probe_definition": "active_terminal_first_eos_or_64_token_cap",
        "claims": claims,
        "family_material": family_material,
        "family_equivalence": family_equivalence,
    }


def _zero_effect_pairs() -> tuple[tuple[str, float], ...]:
    return tuple((claim, 0.0) for claim in CLAIMS)


def _zero_component_pairs() -> tuple[tuple[str, float], ...]:
    return tuple((component, 0.0) for component in MECHANISM_COMPONENTS)


def zero_effect_config(base: PowerSimulationConfig) -> PowerSimulationConfig:
    return replace(
        base,
        scenario_id="zero",
        analyzed_effects=_zero_effect_pairs(),
        mechanism_component_effects=_zero_component_pairs(),
    )


def boundary_configs(base: PowerSimulationConfig) -> dict[str, PowerSimulationConfig]:
    """Return both signs and least-favorable componentwise TOST boundaries."""

    result: dict[str, PowerSimulationConfig] = {}
    for claim in BEHAVIOR_CLAIMS:
        for sign_name, sign in (("minus", -1.0), ("plus", 1.0)):
            scenario_id = f"boundary:{claim}:{sign_name}"
            effects = dict(_zero_effect_pairs())
            effects[claim] = sign * MARGINS[claim]
            result[scenario_id] = replace(
                base,
                scenario_id=scenario_id,
                analyzed_effects=tuple((name, effects[name]) for name in CLAIMS),
                mechanism_component_effects=_zero_component_pairs(),
            )
    for claim in MECHANISM_CLAIMS:
        for component in (f"{claim}_j", f"{claim}_final"):
            for sign_name, sign in (("minus", -1.0), ("plus", 1.0)):
                scenario_id = f"boundary:{claim}:{component}:{sign_name}"
                components = dict(_zero_component_pairs())
                components[component] = sign * MARGINS[claim]
                result[scenario_id] = replace(
                    base,
                    scenario_id=scenario_id,
                    analyzed_effects=_zero_effect_pairs(),
                    mechanism_component_effects=tuple(
                        (name, components[name]) for name in MECHANISM_COMPONENTS
                    ),
                )
    return result


def expected_boundary_ids() -> tuple[str, ...]:
    ids = [
        f"boundary:{claim}:{sign}"
        for claim in BEHAVIOR_CLAIMS
        for sign in ("minus", "plus")
    ]
    ids.extend(
        f"boundary:{claim}:{component}:{sign}"
        for claim in MECHANISM_CLAIMS
        for component in (f"{claim}_j", f"{claim}_final")
        for sign in ("minus", "plus")
    )
    return tuple(ids)


def _claim_from_boundary_id(scenario_id: str) -> str:
    parts = scenario_id.split(":")
    if len(parts) not in (3, 4) or parts[0] != "boundary" or parts[1] not in CLAIMS:
        raise PowerProtocolError(f"invalid boundary scenario ID: {scenario_id}")
    return parts[1]


def _boundary_spec(scenario_id: str) -> tuple[str, str | None, float]:
    parts = scenario_id.split(":")
    claim = _claim_from_boundary_id(scenario_id)
    sign_name = parts[-1]
    if sign_name not in ("minus", "plus"):
        raise PowerProtocolError(f"invalid boundary sign in {scenario_id}")
    sign = -1.0 if sign_name == "minus" else 1.0
    component = parts[2] if len(parts) == 4 else None
    if claim in BEHAVIOR_CLAIMS and component is not None:
        raise PowerProtocolError(f"behavior boundary cannot name a component: {scenario_id}")
    if claim in MECHANISM_CLAIMS and component not in (f"{claim}_j", f"{claim}_final"):
        raise PowerProtocolError(f"mechanism boundary component mismatch: {scenario_id}")
    return claim, component, sign * MARGINS[claim]


def _matches_boundary_configuration(
    result: Mapping[str, Any], scenario_id: str
) -> bool:
    claim, component, boundary = _boundary_spec(scenario_id)
    claims = result.get("claims")
    if not isinstance(claims, Mapping) or set(claims) != set(CLAIMS):
        return False
    for candidate in CLAIMS:
        record = claims.get(candidate)
        if not isinstance(record, Mapping):
            return False
        scalar = record.get("true_analyzed_effect")
        expected_scalar = boundary if candidate == claim and component is None else 0.0
        if not isinstance(scalar, (int, float)) or not math.isclose(
            float(scalar), expected_scalar, abs_tol=1e-12
        ):
            return False
        if candidate in MECHANISM_CLAIMS:
            component_effects = record.get("true_analyzed_component_effects")
            if not isinstance(component_effects, Mapping) or set(component_effects) != {
                f"{candidate}_j",
                f"{candidate}_final",
            }:
                return False
            for candidate_component, value in component_effects.items():
                expected_component = (
                    boundary
                    if candidate == claim and candidate_component == component
                    else 0.0
                )
                if not isinstance(value, (int, float)) or not math.isclose(
                    float(value), expected_component, abs_tol=1e-12
                ):
                    return False
    return True


def _result_outer_simulations(result: Mapping[str, Any]) -> int | None:
    config = result.get("config")
    if not isinstance(config, Mapping):
        return None
    value = config.get("n_simulations")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def assess_power_requirements(
    material_scenario: Mapping[str, Any],
    zero_effect_scenario: Mapping[str, Any],
    *,
    boundary_scenarios: Mapping[str, Mapping[str, Any]] | None = None,
    minimum_power: float = 0.80,
    maximum_false_equivalence: float = 0.05,
    minimum_outer_simulations: int = MINIMUM_PASSING_OUTER_SIMULATIONS,
    minimum_inner_bootstraps: int = MINIMUM_PASSING_INNER_BOOTSTRAPS,
) -> dict[str, Any]:
    """Fail closed using exact one-sided Monte-Carlo confidence bounds."""

    failures: list[str] = []
    all_results = {
        "material": material_scenario,
        "zero": zero_effect_scenario,
        **dict(boundary_scenarios or {}),
    }
    if material_scenario.get("scenario_id") != "material":
        failures.append("material scenario ID mismatch")
    if zero_effect_scenario.get("scenario_id") != "zero":
        failures.append("zero scenario ID mismatch")
    for name, result in all_results.items():
        outer = _result_outer_simulations(result)
        if outer is None or outer < minimum_outer_simulations:
            failures.append(
                f"{name} has fewer than {minimum_outer_simulations} outer simulations"
            )
        config = result.get("config")
        inner = config.get("bootstrap_resamples") if isinstance(config, Mapping) else None
        if (
            not isinstance(inner, int)
            or isinstance(inner, bool)
            or inner < minimum_inner_bootstraps
        ):
            failures.append(
                f"{name} has fewer than {minimum_inner_bootstraps} inner bootstrap draws"
            )
        completion = config.get("completion_fraction") if isinstance(config, Mapping) else None
        if (
            isinstance(completion, bool)
            or not isinstance(completion, (int, float))
            or not math.isclose(float(completion), 0.95, abs_tol=1e-12)
        ):
            failures.append(f"{name} does not simulate the frozen 5% completion boundary")

    for claim in CLAIMS:
        material_record = material_scenario.get("claims", {}).get(claim, {})
        zero_record = zero_effect_scenario.get("claims", {}).get(claim, {})
        material_effect = material_record.get("true_analyzed_effect")
        if claim in MECHANISM_CLAIMS:
            component_effects = material_record.get("true_analyzed_component_effects")
            if not isinstance(component_effects, Mapping) or any(
                not isinstance(component_effects.get(name), (int, float))
                or float(component_effects[name]) <= MARGINS[claim]
                for name in (f"{claim}_j", f"{claim}_final")
            ):
                failures.append(f"{claim} material components are not above the margin")
        elif not isinstance(material_effect, (int, float)) or float(material_effect) <= MARGINS[claim]:
            failures.append(f"{claim} analyzed material effect is not above its margin")
        zero_effect = zero_record.get("true_analyzed_effect")
        zero_components = zero_record.get("true_analyzed_component_effects")
        if not isinstance(zero_effect, (int, float)) or not math.isclose(
            float(zero_effect), 0.0, abs_tol=1e-12
        ):
            failures.append(f"{claim} equivalence scenario is not analyzed zero")
        if claim in MECHANISM_CLAIMS and (
            not isinstance(zero_components, Mapping)
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isclose(float(value), 0.0, abs_tol=1e-12)
                for value in zero_components.values()
            )
        ):
            failures.append(f"{claim} equivalence components are not analyzed zero")
        material_lower = material_record.get("material", {}).get("one_sided_lower")
        zero_lower = zero_record.get("equivalence", {}).get("one_sided_lower")
        if not isinstance(material_lower, (int, float)) or material_lower < minimum_power:
            failures.append(f"{claim} material MC lower bound below {minimum_power:.2f}")
        if not isinstance(zero_lower, (int, float)) or zero_lower < minimum_power:
            failures.append(f"{claim} zero-effect equivalence MC lower bound below {minimum_power:.2f}")

    all_family_lower = material_scenario.get("family_material", {}).get("all", {}).get(
        "one_sided_lower"
    )
    if not isinstance(all_family_lower, (int, float)) or all_family_lower < minimum_power:
        failures.append(
            f"all-claim material conjunction MC lower bound below {minimum_power:.2f}"
        )
    all_equivalence_lower = zero_effect_scenario.get("family_equivalence", {}).get(
        "all", {}
    ).get("one_sided_lower")
    if not isinstance(all_equivalence_lower, (int, float)) or all_equivalence_lower < minimum_power:
        failures.append(
            f"all-claim zero-effect equivalence conjunction MC lower bound below {minimum_power:.2f}"
        )

    boundaries = dict(boundary_scenarios or {})
    expected = set(expected_boundary_ids())
    missing = sorted(expected - set(boundaries))
    unexpected = sorted(set(boundaries) - expected)
    if missing or unexpected:
        failures.append(
            f"boundary scenario set differs; missing={missing}, unexpected={unexpected}"
        )
    for scenario_id in sorted(expected & set(boundaries)):
        claim = _claim_from_boundary_id(scenario_id)
        result = boundaries[scenario_id]
        if result.get("scenario_id") != scenario_id:
            failures.append(f"{scenario_id} receipt scenario ID mismatch")
        if not _matches_boundary_configuration(result, scenario_id):
            failures.append(f"{scenario_id} is not the exact analyzed-scale boundary configuration")
        upper = result.get("claims", {}).get(claim, {}).get("equivalence", {}).get(
            "one_sided_upper"
        )
        if not isinstance(upper, (int, float)) or upper > maximum_false_equivalence:
            failures.append(
                f"{scenario_id} false-equivalence MC upper bound exceeds "
                f"{maximum_false_equivalence:.2f}"
            )
    return {
        "status": "pass" if not failures else "fail",
        "passed": not failures,
        "provisional_power_gate_only": True,
        "freeze_authorization": False,
        "mc_interval": "one-sided exact Clopper-Pearson",
        "mc_confidence": 1.0 - MC_ALPHA,
        "minimum_outer_simulations": minimum_outer_simulations,
        "minimum_inner_bootstraps": minimum_inner_bootstraps,
        "minimum_material_and_zero_equivalence_power": minimum_power,
        "maximum_false_equivalence_at_boundary": maximum_false_equivalence,
        "requires_all_claim_material_conjunction": True,
        "failures": failures,
    }


def _self_hashed(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload.pop("receipt_sha256", None)
    payload["receipt_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload


def validate_power_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping):
        raise PowerProtocolError("power receipt must be an object")
    normalized = dict(receipt)
    expected_hash = normalized.pop("receipt_sha256", None)
    actual_hash = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    if not isinstance(expected_hash, str) or expected_hash != actual_hash:
        raise PowerProtocolError("power receipt self-hash mismatch")
    if normalized.get("study_id") != STUDY_ID:
        raise PowerProtocolError("power receipt study ID mismatch")
    if normalized.get("target_blind") is not True or normalized.get("target_outcome_files_read") != []:
        raise PowerProtocolError("power receipt does not attest target-blind execution")
    scenarios = normalized.get("scenarios")
    if not isinstance(scenarios, Mapping):
        raise PowerProtocolError("power receipt scenarios must be an object")
    expected_ids = {"material", "zero", *expected_boundary_ids()}
    if set(scenarios) != expected_ids:
        raise PowerProtocolError("power receipt scenario set is incomplete or unexpected")
    for scenario_id, result in scenarios.items():
        if not isinstance(result, Mapping) or result.get("scenario_id") != scenario_id:
            raise PowerProtocolError(f"power scenario mismatch for {scenario_id}")
        if result.get("target_blind") is not True:
            raise PowerProtocolError(f"power scenario {scenario_id} is not target blind")
        config_raw = result.get("config")
        if not isinstance(config_raw, Mapping):
            raise PowerProtocolError(f"power scenario {scenario_id} lacks config")
        try:
            reconstructed = PowerSimulationConfig(**dict(config_raw)).validate()
        except (TypeError, ValueError) as exc:
            raise PowerProtocolError(
                f"power scenario {scenario_id} config does not validate: {exc}"
            ) from exc
        if reconstructed.scenario_id != scenario_id:
            raise PowerProtocolError(f"power scenario {scenario_id} config ID mismatch")
        if result.get("config_sha256") != config_sha256(reconstructed):
            raise PowerProtocolError(f"power scenario {scenario_id} config hash mismatch")
        if result.get("resolved_complete_blocks") != reconstructed.complete_block_count():
            raise PowerProtocolError(f"power scenario {scenario_id} completion count mismatch")
        if result.get("cluster_assignment_sha256") != cluster_assignment_sha256(reconstructed):
            raise PowerProtocolError(f"power scenario {scenario_id} cluster hash mismatch")
    assessment = normalized.get("assessment")
    if not isinstance(assessment, Mapping) or assessment.get("freeze_authorization") is not False:
        raise PowerProtocolError("power assessment must explicitly deny freeze authorization")
    recomputed = assess_power_requirements(
        scenarios["material"],
        scenarios["zero"],
        boundary_scenarios={
            scenario_id: scenarios[scenario_id]
            for scenario_id in expected_boundary_ids()
        },
    )
    if canonical_json_bytes(assessment) != canonical_json_bytes(recomputed):
        raise PowerProtocolError("power receipt assessment does not recompute from scenarios")
    base_config = normalized.get("base_config")
    if not isinstance(base_config, Mapping) or normalized.get("base_config_sha256") != hashlib.sha256(
        canonical_json_bytes(base_config)
    ).hexdigest():
        raise PowerProtocolError("power receipt base-config hash mismatch")
    if canonical_json_bytes(base_config) != canonical_json_bytes(scenarios["material"]["config"]):
        raise PowerProtocolError("power receipt base config differs from material scenario")
    return dict(receipt)


def _simulate_named_scenario(
    item: tuple[str, PowerSimulationConfig],
) -> tuple[str, dict[str, Any]]:
    """Pickle-safe worker used only to reduce power-audit wall time."""

    scenario_id, config = item
    return scenario_id, simulate_operating_characteristics(config)


def build_power_receipt(
    base_config: PowerSimulationConfig, *, run_id: str, workers: int = 1
) -> dict[str, Any]:
    if not isinstance(run_id, str) or not run_id or any(character in run_id for character in "/\\"):
        raise PowerProtocolError("run_id must be nonempty path-safe text")
    base_config.validate()
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 16:
        raise PowerProtocolError("workers must be an integer between 1 and 16")
    material_config = replace(base_config, scenario_id="material")
    zero_config = zero_effect_config(base_config)
    boundary = boundary_configs(base_config)
    ordered_configs = {
        "material": material_config,
        "zero": zero_config,
        **boundary,
    }
    if workers == 1:
        computed = {
            scenario_id: simulate_operating_characteristics(config)
            for scenario_id, config in ordered_configs.items()
        }
    else:
        computed = {}
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_simulate_named_scenario, item)
                for item in ordered_configs.items()
            ]
            for future in concurrent.futures.as_completed(futures):
                scenario_id, result = future.result()
                computed[scenario_id] = result
        if set(computed) != set(ordered_configs):
            raise PowerProtocolError("parallel power scenario set is incomplete")
    material = computed["material"]
    zero = computed["zero"]
    boundary_results = {
        scenario_id: computed[scenario_id] for scenario_id in boundary
    }
    assessment = assess_power_requirements(
        material,
        zero,
        boundary_scenarios=boundary_results,
    )
    scenarios = {"material": material, "zero": zero, **boundary_results}
    receipt = {
        "schema_version": "consciousness_sae_power_receipt_v2",
        "study_id": STUDY_ID,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_blind": True,
        "target_outcome_files_read": [],
        "design_status": "provisional_not_frozen",
        "freeze_authorization": False,
        "base_config": material["config"],
        "base_config_sha256": material["config_sha256"],
        "cluster_assignment_sha256": cluster_assignment_sha256(base_config),
        "nuisance_assumptions": {
            "judge_source": base_config.judge_assumption_source,
            "cluster_source": base_config.cluster_assignment_source,
            "mechanism_source": base_config.mechanism_assumption_source,
            "completion_fraction": base_config.completion_fraction,
            "effect_scale": "analyzed_post_judge",
        },
        "scenarios": scenarios,
        "assessment": assessment,
    }
    return validate_power_receipt(_self_hashed(receipt))


def write_power_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    validate_power_receipt(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(receipt) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
    except FileExistsError as exc:
        raise PowerProtocolError(f"refusing to overwrite power receipt: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PowerProtocolError(f"could not read validated JSON input {path}: {exc}") from exc


def _config_from_cli(args: argparse.Namespace) -> PowerSimulationConfig:
    config = PowerSimulationConfig(
        n_blocks=args.n_blocks,
        n_simulations=args.outer_simulations,
        bootstrap_resamples=args.bootstrap_resamples,
        seed=args.seed,
    )
    if args.cluster_manifest is not None:
        path = Path(args.cluster_manifest).resolve()
        raw = _load_json(path)
        cluster_ids = raw.get("cluster_ids") if isinstance(raw, Mapping) else raw
        if not isinstance(cluster_ids, list) or any(not isinstance(item, str) for item in cluster_ids):
            raise PowerProtocolError("cluster manifest must be a list or {cluster_ids:[...]}")
        config = replace(
            config,
            cluster_assignments=tuple(cluster_ids),
            cluster_assignment_source=f"receipt_sha256:{_sha256_file(path)}",
        )
    if args.judge_assumptions is not None:
        path = Path(args.judge_assumptions).resolve()
        raw = _load_json(path)
        if not isinstance(raw, Mapping):
            raise PowerProtocolError("judge assumptions must be a JSON object")
        config = replace(
            config,
            stance_confusion_matrix=tuple(
                tuple(float(value) for value in row)
                for row in raw.get("stance_confusion_matrix", ())
            ),
            binary_judge_sensitivity=float(raw.get("binary_sensitivity")),
            binary_judge_specificity=float(raw.get("binary_specificity")),
            judge_assumption_source=f"receipt_sha256:{_sha256_file(path)}",
        )
    return config.validate()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the target-blind consciousness-SAE power suite"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--n-blocks", type=int, default=560)
    parser.add_argument(
        "--outer-simulations", type=int, default=MINIMUM_PASSING_OUTER_SIMULATIONS
    )
    parser.add_argument("--bootstrap-resamples", type=int, default=999)
    parser.add_argument("--seed", type=int, default=POWER_SIMULATION_SEED)
    parser.add_argument("--cluster-manifest")
    parser.add_argument("--judge-assumptions")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    config = _config_from_cli(args)
    receipt = build_power_receipt(config, run_id=args.run_id, workers=args.workers)
    write_power_receipt(Path(args.output).resolve(), receipt)
    print(
        json.dumps(
            {
                "output": str(Path(args.output).resolve()),
                "receipt_sha256": receipt["receipt_sha256"],
                "assessment": receipt["assessment"]["status"],
                "freeze_authorization": False,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt["assessment"]["passed"] else 2


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI
    raise SystemExit(main())
