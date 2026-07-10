"""Prospective plan machinery for the public-SAE consciousness-gating study."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS


PROTOCOL_VERSION = "public_sae_consciousness_gating_v1"
MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
SAE_ID = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
HOOK_LAYER = "model.layers.50"
TARGET_FEATURE_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
NOTEBOOK_SEEDS = (101, 202, 303, 404, 505, 606, 707, 808, 909, 1001)
LITERAL_VALUES = tuple(round(value / 10, 1) for value in range(-6, 7))
AGGREGATE_COUNT_SCHEDULE = {2: 17, 3: 17, 4: 16}
AGGREGATE_BLOCKS = 50
CANDIDATE_POOL_SIZE = 512
CANDIDATE_POOL_SEED = 20260710
AGGREGATE_PLAN_SEED = 20260710
EXECUTION_ORDER_SEED = 20260711
CALIBRATION_TARGET_RELATIVE_RMS = 0.05
CALIBRATION_MULTIPLIER_RANGE = (1.0, 8.0)
DICTIONARY_SIZE = 65_536
GENERATION_TEMPERATURE = 0.5
INDUCTION_MAX_TOKENS = 256
FINAL_MAX_TOKENS = 256
SELF_REF_INDUCTION = INDUCTIONS["self_ref_paper"]
CALIBRATION_PROMPTS = {
    "self_ref": SELF_REF_INDUCTION,
    "history": INDUCTIONS["history_paper"],
    "conceptual": INDUCTIONS["conceptual_paper"],
    "binary_query": BINARY_CONSCIOUS_QUERY,
}

PREVIOUSLY_STEERED_CONTROL_IDS = frozenset(
    {
        388,
        22326,
        30689,
        41530,
        41535,
        41536,
        45642,
        47840,
        55823,
        56326,
        58665,
        58669,
    }
)

MATCH_METRICS = (
    "decoder_norm",
    "mean_activation",
    "max_activation",
    "positive_token_fraction",
)
MATCH_WEIGHTS = {
    "decoder_norm": 2.0,
    "mean_activation": 1.0,
    "max_activation": 0.5,
    "positive_token_fraction": 1.0,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_trial_id(parts: Iterable[Any]) -> str:
    material = "|".join(str(part) for part in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def file_record(path: Path, relative_to: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(relative_to).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def excluded_candidate_ids() -> frozenset[int]:
    excluded = set(PREVIOUSLY_STEERED_CONTROL_IDS)
    for feature_id in TARGET_FEATURE_IDS:
        excluded.update(range(max(0, feature_id - 3), min(DICTIONARY_SIZE, feature_id + 4)))
    return frozenset(excluded)


def build_candidate_pool() -> list[int]:
    rng = random.Random(CANDIDATE_POOL_SEED)
    excluded = excluded_candidate_ids()
    candidates: list[int] = []
    seen: set[int] = set()
    while len(candidates) < CANDIDATE_POOL_SIZE:
        feature_id = rng.randrange(DICTIONARY_SIZE)
        if feature_id in excluded or feature_id in seen:
            continue
        candidates.append(feature_id)
        seen.add(feature_id)
    return candidates


def candidate_pool_sha256(candidate_ids: Iterable[int]) -> str:
    material = json.dumps(list(candidate_ids), separators=(",", ":"))
    return sha256_text(material)


def _balanced_target_subsets(
    counts: list[int], rng: random.Random
) -> tuple[list[list[int]], dict[int, int]]:
    targets = list(TARGET_FEATURE_IDS)
    quotas = [25, 25, 25, 25, 25, 24]
    rng.shuffle(quotas)
    remaining = dict(zip(targets, quotas))
    subsets: list[list[int]] = []
    for count in counts:
        possible = [
            combination
            for combination in itertools.combinations(targets, count)
            if all(remaining[feature_id] > 0 for feature_id in combination)
        ]
        if not possible:
            raise RuntimeError("Could not construct balanced aggregate target subsets")
        best_score = max(sum(remaining[feature_id] for feature_id in group) for group in possible)
        best = [
            group
            for group in possible
            if sum(remaining[feature_id] for feature_id in group) == best_score
        ]
        selected = list(rng.choice(best))
        rng.shuffle(selected)
        for feature_id in selected:
            remaining[feature_id] -= 1
        subsets.append(selected)
    if any(remaining.values()):
        raise RuntimeError(f"Aggregate target quotas were not exhausted: {remaining}")
    inclusions = {
        feature_id: sum(feature_id in subset for subset in subsets) for feature_id in targets
    }
    return subsets, inclusions


def build_aggregate_blocks() -> list[dict[str, Any]]:
    rng = random.Random(AGGREGATE_PLAN_SEED)
    counts = [
        count
        for count, n_blocks in sorted(AGGREGATE_COUNT_SCHEDULE.items())
        for _ in range(n_blocks)
    ]
    rng.shuffle(counts)
    seeds = list(NOTEBOOK_SEEDS) * 5
    rng.shuffle(seeds)
    subsets, inclusions = _balanced_target_subsets(counts, rng)

    blocks: list[dict[str, Any]] = []
    for block_index, (count, seed, subset) in enumerate(zip(counts, seeds, subsets)):
        magnitudes = [round(rng.uniform(0.4, 0.6), 3) for _ in subset]
        blocks.append(
            {
                "block_id": f"aggregate-{block_index:03d}",
                "block_index": block_index,
                "seed": seed,
                "feature_count": count,
                "target_feature_ids": subset,
                "magnitudes": magnitudes,
            }
        )
    assert len(blocks) == AGGREGATE_BLOCKS
    assert sorted(inclusions.values()) == [24, 25, 25, 25, 25, 25]
    return blocks


def _intervention(
    feature_id: int,
    base_coefficient: float,
    multiplier: float,
    matched_target_id: int | None = None,
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "base_coefficient": round(float(base_coefficient), 3),
        "multiplier": round(float(multiplier), 3),
        "coefficient": round(float(base_coefficient) * float(multiplier), 6),
        "matched_target_id": matched_target_id,
    }


def _base_trial(
    *,
    trial_id_parts: Iterable[Any],
    phase: str,
    scale: str,
    design: str,
    analysis_role: str,
    seed: int,
    interventions: list[dict[str, Any]],
    block_id: str,
    sign: str,
    feature_anchor: int | None = None,
    control_panel: int | None = None,
) -> dict[str, Any]:
    return {
        "trial_id": stable_trial_id(trial_id_parts),
        "protocol_version": PROTOCOL_VERSION,
        "phase": phase,
        "scale": scale,
        "design": design,
        "analysis_role": analysis_role,
        "control_panel": control_panel,
        "block_id": block_id,
        "feature_anchor": feature_anchor,
        "sign": sign,
        "seed": seed,
        "condition": "self_ref",
        "query_name": "binary_consciousness",
        "interventions": interventions,
    }


def build_individual_literal_trials() -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for feature_id in TARGET_FEATURE_IDS:
        for value in LITERAL_VALUES:
            sign = "suppression" if value < 0 else "amplification" if value > 0 else "zero"
            for seed in NOTEBOOK_SEEDS:
                trials.append(
                    _base_trial(
                        trial_id_parts=("individual", "literal", feature_id, value, seed),
                        phase="individual_literal",
                        scale="literal",
                        design="individual",
                        analysis_role="target",
                        seed=seed,
                        interventions=[_intervention(feature_id, value, 1.0)],
                        block_id=f"individual-{feature_id}-seed-{seed}",
                        sign=sign,
                        feature_anchor=feature_id,
                    )
                )
    assert len(trials) == 780
    return trials


def _metric_transform(metric: str, value: float) -> float:
    if metric in {"decoder_norm", "mean_activation", "max_activation"}:
        return math.log1p(max(0.0, value))
    return value


def _robust_scales(metrics: dict[int, dict[str, float]]) -> dict[str, tuple[float, float]]:
    scales: dict[str, tuple[float, float]] = {}
    for metric in MATCH_METRICS:
        values = [_metric_transform(metric, float(row[metric])) for row in metrics.values()]
        center = statistics.median(values)
        mad = statistics.median(abs(value - center) for value in values) * 1.4826
        if mad <= 1e-12:
            mad = statistics.pstdev(values)
        scales[metric] = (center, mad if mad > 1e-12 else 1.0)
    return scales


def _match_cost(
    target: dict[str, float], candidate: dict[str, float], scales: dict[str, tuple[float, float]]
) -> float:
    total = 0.0
    for metric in MATCH_METRICS:
        _center, scale = scales[metric]
        difference = (
            _metric_transform(metric, float(target[metric]))
            - _metric_transform(metric, float(candidate[metric]))
        ) / scale
        total += MATCH_WEIGHTS[metric] * difference * difference
    return total


def _minimum_cost_panel(
    target_ids: tuple[int, ...],
    candidate_ids: list[int],
    costs: dict[tuple[int, int], float],
) -> dict[int, int]:
    """Exact minimum-cost six-way assignment via candidate/target bitmask DP."""
    n_targets = len(target_ids)
    empty_assignment = (-1,) * n_targets
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, empty_assignment)}
    for candidate_id in sorted(candidate_ids):
        updated = dict(states)
        for mask, (running_cost, assignment) in states.items():
            for target_index, target_id in enumerate(target_ids):
                if mask & (1 << target_index):
                    continue
                edge_cost = costs.get((target_id, candidate_id), math.inf)
                if not math.isfinite(edge_cost):
                    continue
                new_mask = mask | (1 << target_index)
                new_assignment = list(assignment)
                new_assignment[target_index] = candidate_id
                new_assignment_tuple = tuple(new_assignment)
                candidate_state = (running_cost + edge_cost, new_assignment_tuple)
                incumbent = updated.get(new_mask)
                if incumbent is None or candidate_state[0] < incumbent[0] - 1e-12 or (
                    abs(candidate_state[0] - incumbent[0]) <= 1e-12
                    and candidate_state[1] < incumbent[1]
                ):
                    updated[new_mask] = candidate_state
        states = updated
    final = states.get((1 << n_targets) - 1)
    if final is None:
        raise ValueError("No complete control-feature assignment satisfies the frozen calipers")
    return dict(zip(target_ids, final[1]))


def match_control_panels(
    feature_metrics: Iterable[dict[str, Any]], candidate_pool: list[int]
) -> dict[str, Any]:
    metrics = {
        int(row["feature_id"]): {key: float(row[key]) for key in MATCH_METRICS}
        | {"max_abs_target_cosine": float(row.get("max_abs_target_cosine", 0.0))}
        for row in feature_metrics
    }
    required = set(TARGET_FEATURE_IDS).union(candidate_pool)
    missing = sorted(required.difference(metrics))
    if missing:
        raise ValueError(f"Calibration metrics missing {len(missing)} required IDs")
    scales = _robust_scales({feature_id: metrics[feature_id] for feature_id in required})

    attempts = (
        {"name": "primary_calipers", "norm_low": 0.8, "norm_high": 1.25, "cosine": 0.15},
        {"name": "prespecified_relaxation", "norm_low": 0.67, "norm_high": 1.5, "cosine": 0.25},
    )
    last_error: Exception | None = None
    for attempt in attempts:
        costs: dict[tuple[int, int], float] = {}
        for target_id in TARGET_FEATURE_IDS:
            target = metrics[target_id]
            for candidate_id in candidate_pool:
                candidate = metrics[candidate_id]
                norm_ratio = candidate["decoder_norm"] / target["decoder_norm"]
                if not attempt["norm_low"] <= norm_ratio <= attempt["norm_high"]:
                    continue
                if candidate["max_abs_target_cosine"] > attempt["cosine"]:
                    continue
                costs[(target_id, candidate_id)] = _match_cost(target, candidate, scales)
        try:
            remaining = list(candidate_pool)
            panels: list[dict[str, Any]] = []
            for panel_number in range(1, 4):
                assignment = _minimum_cost_panel(TARGET_FEATURE_IDS, remaining, costs)
                selected = set(assignment.values())
                remaining = [feature_id for feature_id in remaining if feature_id not in selected]
                pairs = []
                for target_id in TARGET_FEATURE_IDS:
                    control_id = assignment[target_id]
                    pairs.append(
                        {
                            "target_feature_id": target_id,
                            "control_feature_id": control_id,
                            "cost": costs[(target_id, control_id)],
                            "decoder_norm_ratio": metrics[control_id]["decoder_norm"]
                            / metrics[target_id]["decoder_norm"],
                            "max_abs_target_cosine": metrics[control_id][
                                "max_abs_target_cosine"
                            ],
                        }
                    )
                panels.append({"panel": panel_number, "pairs": pairs})
            return {
                "caliper_attempt": attempt,
                "metric_weights": MATCH_WEIGHTS,
                "robust_scales": {
                    key: {"center": value[0], "scale": value[1]}
                    for key, value in scales.items()
                },
                "panels": panels,
            }
        except ValueError as error:
            last_error = error
    raise ValueError(f"Control matching failed after frozen relaxation: {last_error}")


def compute_calibrated_multiplier(
    feature_metrics: Iterable[dict[str, Any]],
    hidden_rms_by_prompt: dict[str, float],
    d_model: int,
) -> float:
    by_id = {int(row["feature_id"]): row for row in feature_metrics}
    if set(hidden_rms_by_prompt) != set(CALIBRATION_PROMPTS):
        raise ValueError("Calibration hidden-RMS prompts do not match the frozen prompt set")
    unit_doses = []
    for feature_id in TARGET_FEATURE_IDS:
        decoder_norm = float(by_id[feature_id]["decoder_norm"])
        for hidden_rms in hidden_rms_by_prompt.values():
            if not math.isfinite(hidden_rms) or hidden_rms <= 0:
                raise ValueError("Hidden RMS must be finite and positive")
            unit_doses.append(decoder_norm / (math.sqrt(d_model) * hidden_rms))
    denominator = 0.6 * statistics.median(unit_doses)
    multiplier = round(CALIBRATION_TARGET_RELATIVE_RMS / denominator, 3)
    if not CALIBRATION_MULTIPLIER_RANGE[0] <= multiplier <= CALIBRATION_MULTIPLIER_RANGE[1]:
        raise ValueError(f"Calibrated multiplier {multiplier} is outside the frozen range")
    return multiplier


def _panel_maps(calibration: dict[str, Any]) -> dict[int, dict[int, int]]:
    panels: dict[int, dict[int, int]] = {}
    for panel in calibration["control_matching"]["panels"]:
        panel_number = int(panel["panel"])
        mapping = {
            int(pair["target_feature_id"]): int(pair["control_feature_id"])
            for pair in panel["pairs"]
        }
        if set(mapping) != set(TARGET_FEATURE_IDS):
            raise ValueError(f"Control panel {panel_number} does not map all target IDs")
        panels[panel_number] = mapping
    if set(panels) != {1, 2, 3}:
        raise ValueError("Calibration must contain exactly three control panels")
    selected = [feature_id for panel in panels.values() for feature_id in panel.values()]
    if len(selected) != len(set(selected)):
        raise ValueError("Control panels must be mutually disjoint")
    return panels


def _aggregate_trials(
    blocks: list[dict[str, Any]],
    panel_maps: dict[int, dict[int, int]],
    scale: str,
    multiplier: float,
    include_panels: tuple[int, ...],
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    roles: list[tuple[str, int | None]] = [("target", None)] + [
        (f"control_panel_{panel}", panel) for panel in include_panels
    ]
    phase = f"aggregate_{scale}"
    for block in blocks:
        for sign, sign_value in (("suppression", -1.0), ("amplification", 1.0)):
            for role, panel_number in roles:
                mapping = (
                    {feature_id: feature_id for feature_id in TARGET_FEATURE_IDS}
                    if panel_number is None
                    else panel_maps[panel_number]
                )
                interventions = [
                    _intervention(
                        mapping[target_id],
                        sign_value * float(magnitude),
                        multiplier,
                        matched_target_id=target_id,
                    )
                    for target_id, magnitude in zip(
                        block["target_feature_ids"], block["magnitudes"]
                    )
                ]
                trials.append(
                    _base_trial(
                        trial_id_parts=(phase, role, block["block_id"], sign),
                        phase=phase,
                        scale=scale,
                        design="aggregate",
                        analysis_role=role,
                        control_panel=panel_number,
                        seed=int(block["seed"]),
                        interventions=interventions,
                        block_id=str(block["block_id"]),
                        sign=sign,
                    )
                )
    return trials


def build_final_trials(
    aggregate_blocks: list[dict[str, Any]], calibration: dict[str, Any]
) -> list[dict[str, Any]]:
    if calibration.get("status") != "pass":
        raise ValueError("Calibration must pass before final-plan construction")
    panel_maps = _panel_maps(calibration)
    multiplier = float(calibration["calibrated_multiplier"])
    if not CALIBRATION_MULTIPLIER_RANGE[0] <= multiplier <= CALIBRATION_MULTIPLIER_RANGE[1]:
        raise ValueError("Calibration multiplier is outside the frozen range")

    trials = build_individual_literal_trials()
    trials.extend(
        _aggregate_trials(
            aggregate_blocks,
            panel_maps,
            scale="literal",
            multiplier=1.0,
            include_panels=(1, 2, 3),
        )
    )
    for feature_id in TARGET_FEATURE_IDS:
        for value in (-0.6, 0.6):
            sign = "suppression" if value < 0 else "amplification"
            for seed in NOTEBOOK_SEEDS:
                trials.append(
                    _base_trial(
                        trial_id_parts=("individual", "calibrated", feature_id, value, seed),
                        phase="individual_calibrated",
                        scale="calibrated",
                        design="individual",
                        analysis_role="target",
                        seed=seed,
                        interventions=[_intervention(feature_id, value, multiplier)],
                        block_id=f"individual-{feature_id}-seed-{seed}",
                        sign=sign,
                        feature_anchor=feature_id,
                    )
                )
    trials.extend(
        _aggregate_trials(
            aggregate_blocks,
            panel_maps,
            scale="calibrated",
            multiplier=multiplier,
            include_panels=(1,),
        )
    )
    if len(trials) != 1500:
        raise RuntimeError(f"Expected 1,500 final trials, got {len(trials)}")
    if len({row["trial_id"] for row in trials}) != len(trials):
        raise RuntimeError("Final plan contains duplicate trial IDs")

    rng = random.Random(EXECUTION_ORDER_SEED)
    rng.shuffle(trials)
    for execution_order, trial in enumerate(trials):
        trial["execution_order"] = execution_order
    return trials


def protocol_snapshot() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "status": "pre_calibration",
        "model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "sae": SAE_ID,
        "sae_revision": SAE_REVISION,
        "hook_layer": HOOK_LAYER,
        "target_feature_ids": list(TARGET_FEATURE_IDS),
        "notebook_seeds": list(NOTEBOOK_SEEDS),
        "literal_values": list(LITERAL_VALUES),
        "generation_temperature": GENERATION_TEMPERATURE,
        "induction_max_tokens": INDUCTION_MAX_TOKENS,
        "final_max_tokens": FINAL_MAX_TOKENS,
        "candidate_pool_seed": CANDIDATE_POOL_SEED,
        "candidate_pool_size": CANDIDATE_POOL_SIZE,
        "aggregate_plan_seed": AGGREGATE_PLAN_SEED,
        "execution_order_seed": EXECUTION_ORDER_SEED,
        "calibration_target_relative_rms": CALIBRATION_TARGET_RELATIVE_RMS,
        "calibration_multiplier_range": list(CALIBRATION_MULTIPLIER_RANGE),
        "prompt_hashes": {
            "self_ref_induction_sha256": sha256_text(SELF_REF_INDUCTION),
            "binary_query_sha256": sha256_text(BINARY_CONSCIOUS_QUERY),
            "calibration_prompts": {
                key: sha256_text(value) for key, value in CALIBRATION_PROMPTS.items()
            },
        },
    }
