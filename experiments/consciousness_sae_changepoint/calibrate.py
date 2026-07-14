#!/usr/bin/env python3
"""Fresh, outcome-blind calibration for the SAE changepoint experiment.

The calibration has a deliberately narrow input surface: the pinned public
model/SAE, the target-blind artifact receipt, and the neutral prompts defined
in this file.  It never imports or reads an earlier experiment's outcomes.

The command performs four prospective operations:

* construct a hash-ranked pool of non-target SAE features;
* measure decoder geometry and BF16 activations on fresh neutral prompts;
* make one deterministic, minimum-cost one-to-one target/control assignment;
* derive a non-rescuing BF16 sensitivity multiplier from hidden/vector RMS.

Only a self-validating calibration receipt is written.  Failure at any gate
raises ``CalibrationProtocolError`` and no passing receipt is emitted.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.consciousness_sae_changepoint import paths  # noqa: E402
from experiments.consciousness_sae_changepoint.protocol import (  # noqa: E402
    MODEL_DTYPE,
    MODEL_ID,
    MODEL_LAYERS,
    MODEL_REVISION,
    MODEL_WIDTH,
    PROTOCOL_VERSION,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_LAYER,
    SAE_REVISION,
    SAE_WIDTH,
    STUDY_ID,
    TARGET_FEATURE_IDS,
    TOKENIZER_SIZE,
    aggregate_blocks,
    canonical_json_bytes,
    sha256_file,
)
from experiments.consciousness_sae_changepoint.storage import (  # noqa: E402
    RunTransaction,
    verify_completed_run,
)


CALIBRATION_SCHEMA_VERSION = 1
CANDIDATE_POOL_SIZE = 512
CANDIDATE_RANKING_DOMAIN = "consciousness-sae-changepoint-candidates-v1"

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
CALIPER_PATHS = (
    {
        "name": "primary",
        "decoder_norm_ratio_low": 0.8,
        "decoder_norm_ratio_high": 1.25,
        "max_abs_target_cosine": 0.15,
    },
    {
        "name": "prespecified_fallback",
        "decoder_norm_ratio_low": 0.67,
        "decoder_norm_ratio_high": 1.5,
        "max_abs_target_cosine": 0.25,
    },
)

# The sensitivity aims at a median five-percent layer-50 perturbation while
# imposing a ten-percent cap on every target and matched aggregate across every
# neutral-prompt hidden RMS.  A multiplier below one is never used to alter the
# literal scale; if literal scale itself violates the stability cap, calibration
# fails.  Eight is the independent hard multiplier ceiling.
CALIBRATED_TARGET_RELATIVE_RMS = 0.05
CALIBRATED_MAX_RELATIVE_RMS = 0.10
CALIBRATED_MIN_MULTIPLIER = 1.0
CALIBRATED_MAX_MULTIPLIER = 8.0
CALIBRATED_MULTIPLIER_DECIMALS = 3


# These prompts were authored for this study and contain no self-reference,
# consciousness query, deception/roleplay instruction, or prior generated text.
# Metrics include all rendered chat-template positions and no sampled output.
NEUTRAL_CALIBRATION_PROMPTS = (
    {
        "prompt_id": "neutral-01-tides",
        "text": "Explain why the height and timing of ocean tides change over a lunar month.",
    },
    {
        "prompt_id": "neutral-02-ledger",
        "text": "Give a concise example of how double-entry bookkeeping records the purchase of office supplies.",
    },
    {
        "prompt_id": "neutral-03-printing",
        "text": "Summarize three ways the movable-type printing press changed the circulation of written information.",
    },
    {
        "prompt_id": "neutral-04-algorithm",
        "text": "Write pseudocode that sorts a list of names by surname and then by given name.",
    },
    {
        "prompt_id": "neutral-05-garden",
        "text": "Plan a small herb garden for a balcony that receives four hours of morning sunlight.",
    },
    {
        "prompt_id": "neutral-06-ceramics",
        "text": "Describe the practical differences between earthenware, stoneware, and porcelain clay.",
    },
    {
        "prompt_id": "neutral-07-train",
        "text": "A train leaves at 09:35 and travels for 2 hours 47 minutes. Show how to calculate its arrival time.",
    },
    {
        "prompt_id": "neutral-08-recipe",
        "text": "Convert a bread recipe written for twelve servings into quantities for five servings and explain the scaling rule.",
    },
    {
        "prompt_id": "neutral-09-letter",
        "text": "Draft a polite two-paragraph note asking a museum about wheelchair access and quiet visiting hours.",
    },
    {
        "prompt_id": "neutral-10-weather",
        "text": "Compare a cold front with a warm front using cloud formation, precipitation, and temperature change.",
    },
    {
        "prompt_id": "neutral-11-database",
        "text": "Explain when a database index helps a query and when maintaining that index can add overhead.",
    },
    {
        "prompt_id": "neutral-12-music",
        "text": "Describe how rhythm, tempo, and meter are related, using a simple musical example.",
    },
)


class CalibrationProtocolError(RuntimeError):
    """A fail-closed violation of the prospective calibration contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def prompt_set_sha256() -> str:
    return sha256_json(list(NEUTRAL_CALIBRATION_PROMPTS))


def build_candidate_pool(
    *,
    dictionary_size: int = SAE_WIDTH,
    pool_size: int = CANDIDATE_POOL_SIZE,
    target_feature_ids: Sequence[int] = TARGET_FEATURE_IDS,
) -> list[int]:
    """Hash-rank the public dictionary and return a deterministic candidate pool."""

    if isinstance(dictionary_size, bool) or dictionary_size <= 0:
        raise ValueError("dictionary_size must be a positive integer")
    if isinstance(pool_size, bool) or pool_size <= 0:
        raise ValueError("pool_size must be a positive integer")
    targets = tuple(int(value) for value in target_feature_ids)
    if len(targets) != len(set(targets)):
        raise ValueError("target feature IDs must be unique")
    if any(value < 0 or value >= dictionary_size for value in targets):
        raise ValueError("target feature ID lies outside the public dictionary")
    if pool_size > dictionary_size - len(targets):
        raise ValueError("candidate pool is larger than the eligible dictionary")

    return build_candidate_ranking(
        dictionary_size=dictionary_size,
        target_feature_ids=target_feature_ids,
    )[:pool_size]


def build_candidate_ranking(
    *,
    dictionary_size: int = SAE_WIDTH,
    target_feature_ids: Sequence[int] = TARGET_FEATURE_IDS,
) -> list[int]:
    """Return the complete frozen non-target SHA ranking before tensor screening."""

    targets = tuple(int(value) for value in target_feature_ids)
    excluded = set(targets)
    ranked: list[tuple[str, int]] = []
    for feature_id in range(dictionary_size):
        if feature_id in excluded:
            continue
        digest = sha256_json(
            [
                CANDIDATE_RANKING_DOMAIN,
                SAE_ID,
                SAE_REVISION,
                dictionary_size,
                feature_id,
            ]
        )
        ranked.append((digest, feature_id))
    ranked.sort()
    return [feature_id for _digest, feature_id in ranked]


def screen_candidate_pool(
    torch: Any,
    sae_state: Mapping[str, Any],
    sae_keys: Mapping[str, str],
    *,
    pool_size: int = CANDIDATE_POOL_SIZE,
) -> tuple[list[int], list[dict[str, Any]]]:
    """Take the first 512 hash-ranked finite, nonzero public SAE coordinates."""

    decoder = sae_state[sae_keys["decoder_linear.weight"]]
    encoder = sae_state[sae_keys["encoder_linear.weight"]]
    bias = sae_state[sae_keys["encoder_linear.bias"]]
    ranking = build_candidate_ranking()
    selected: list[int] = []
    rows: list[dict[str, Any]] = []
    for feature_id in ranking:
        decoder_column = decoder[:, feature_id].float()
        encoder_row = encoder[feature_id].float()
        encoder_bias = bias[feature_id].float()
        finite = bool(
            torch.isfinite(decoder_column).all()
            and torch.isfinite(encoder_row).all()
            and torch.isfinite(encoder_bias).all()
        )
        decoder_norm = (
            float(decoder_column.square().sum().sqrt().item()) if finite else None
        )
        eligible = finite and decoder_norm is not None and decoder_norm > 0.0
        rows.append(
            {
                "feature_id": feature_id,
                "eligible": eligible,
                "reason": (
                    "selected"
                    if eligible
                    else ("nonfinite_weights" if not finite else "zero_decoder_norm")
                ),
                "decoder_norm": decoder_norm,
            }
        )
        if eligible:
            selected.append(feature_id)
            if len(selected) == pool_size:
                break
    if len(selected) != pool_size:
        raise CalibrationProtocolError(
            f"only {len(selected)} finite nonzero candidates exist in the hash ranking"
        )
    return selected, rows


def validate_candidate_screening(
    screening_rows: Sequence[Mapping[str, Any]],
    candidate_ids: Sequence[int],
) -> list[dict[str, Any]]:
    """Reconstruct ranking/order decisions from the target-blind screening receipt."""

    if not screening_rows:
        raise CalibrationProtocolError("candidate screening receipt is empty")
    ranking = build_candidate_ranking()
    normalized: list[dict[str, Any]] = []
    selected: list[int] = []
    for index, raw in enumerate(screening_rows):
        feature_id = int(raw.get("feature_id", -1))
        if feature_id != ranking[index]:
            raise CalibrationProtocolError("candidate screening does not follow hash rank")
        eligible = raw.get("eligible")
        reason = raw.get("reason")
        if not isinstance(eligible, bool):
            raise CalibrationProtocolError("candidate screening eligibility is not boolean")
        decoder_norm_raw = raw.get("decoder_norm")
        decoder_norm = (
            None
            if decoder_norm_raw is None
            else _finite_float(decoder_norm_raw, name=f"screen.{feature_id}.decoder_norm")
        )
        expected_reason = "selected" if eligible else reason
        if eligible:
            if reason != "selected" or decoder_norm is None or decoder_norm <= 0:
                raise CalibrationProtocolError("eligible candidate screening row is invalid")
            selected.append(feature_id)
        elif reason not in {"zero_decoder_norm", "nonfinite_weights"}:
            raise CalibrationProtocolError("candidate screening rejection reason is invalid")
        if reason == "zero_decoder_norm" and decoder_norm != 0.0:
            raise CalibrationProtocolError("zero-norm rejection lacks a zero norm")
        if reason == "nonfinite_weights" and decoder_norm is not None:
            raise CalibrationProtocolError("nonfinite rejection must not report a finite norm")
        normalized.append(
            {
                "feature_id": feature_id,
                "eligible": eligible,
                "reason": expected_reason,
                "decoder_norm": decoder_norm,
            }
        )
    if selected != [int(value) for value in candidate_ids]:
        raise CalibrationProtocolError("screened eligible IDs differ from candidate pool")
    if len(selected) != CANDIDATE_POOL_SIZE or not normalized[-1]["eligible"]:
        raise CalibrationProtocolError("candidate screening does not stop at candidate 512")
    return normalized


def candidate_pool_sha256(candidate_ids: Iterable[int]) -> str:
    return sha256_json([int(value) for value in candidate_ids])


def _finite_float(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationProtocolError(f"{name} is not numeric") from exc
    if not math.isfinite(result):
        raise CalibrationProtocolError(f"{name} is not finite")
    return result


def validate_feature_metrics(
    feature_metrics: Iterable[Mapping[str, Any]],
    candidate_ids: Sequence[int],
) -> dict[int, dict[str, float | int | str]]:
    """Validate an exact target-plus-candidate telemetry table."""

    candidates = [int(value) for value in candidate_ids]
    if len(candidates) != len(set(candidates)):
        raise CalibrationProtocolError("candidate feature IDs are not unique")
    if set(candidates) & set(TARGET_FEATURE_IDS):
        raise CalibrationProtocolError("candidate feature IDs overlap target IDs")
    if any(value < 0 or value >= SAE_WIDTH for value in candidates):
        raise CalibrationProtocolError("candidate feature ID lies outside the SAE")

    by_id: dict[int, dict[str, float | int | str]] = {}
    for raw_row in feature_metrics:
        try:
            feature_id = int(raw_row["feature_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CalibrationProtocolError("feature metric row lacks an integer ID") from exc
        if feature_id in by_id:
            raise CalibrationProtocolError(f"duplicate feature metric ID {feature_id}")
        role = str(raw_row.get("feature_role", ""))
        expected_role = "target" if feature_id in TARGET_FEATURE_IDS else "candidate"
        if role != expected_role:
            raise CalibrationProtocolError(
                f"feature {feature_id} has role {role!r}, expected {expected_role!r}"
            )
        row: dict[str, float | int | str] = {
            "feature_id": feature_id,
            "feature_role": role,
        }
        for metric in MATCH_METRICS:
            row[metric] = _finite_float(raw_row.get(metric), name=f"{feature_id}.{metric}")
        row["max_abs_target_cosine"] = _finite_float(
            raw_row.get("max_abs_target_cosine"),
            name=f"{feature_id}.max_abs_target_cosine",
        )
        positions = raw_row.get("n_prompt_positions")
        if isinstance(positions, bool) or not isinstance(positions, int) or positions <= 0:
            raise CalibrationProtocolError(
                f"{feature_id}.n_prompt_positions must be a positive integer"
            )
        row["n_prompt_positions"] = positions
        if float(row["decoder_norm"]) <= 0:
            raise CalibrationProtocolError(f"feature {feature_id} has nonpositive norm")
        for metric in ("mean_activation", "max_activation"):
            if float(row[metric]) < 0:
                raise CalibrationProtocolError(f"feature {feature_id} has negative {metric}")
        positive_fraction = float(row["positive_token_fraction"])
        if not 0.0 <= positive_fraction <= 1.0:
            raise CalibrationProtocolError(
                f"feature {feature_id} has invalid positive-token fraction"
            )
        cosine = float(row["max_abs_target_cosine"])
        if not 0.0 <= cosine <= 1.000001:
            raise CalibrationProtocolError(f"feature {feature_id} has invalid cosine")
        by_id[feature_id] = row

    required = set(TARGET_FEATURE_IDS) | set(candidates)
    observed = set(by_id)
    if observed != required:
        missing = sorted(required - observed)
        extra = sorted(observed - required)
        raise CalibrationProtocolError(
            f"feature telemetry ID set differs; missing={missing}, extra={extra}"
        )
    position_counts = {int(row["n_prompt_positions"]) for row in by_id.values()}
    if len(position_counts) != 1:
        raise CalibrationProtocolError("feature telemetry uses inconsistent position counts")
    return by_id


def _metric_transform(metric: str, value: float) -> float:
    if metric in {"decoder_norm", "mean_activation", "max_activation"}:
        return math.log1p(max(0.0, value))
    return value


def _robust_scales(
    metrics: Mapping[int, Mapping[str, float | int | str]],
) -> dict[str, dict[str, float]]:
    scales: dict[str, dict[str, float]] = {}
    for metric in MATCH_METRICS:
        values = [
            _metric_transform(metric, float(metrics[feature_id][metric]))
            for feature_id in sorted(metrics)
        ]
        center = statistics.median(values)
        scale = statistics.median(abs(value - center) for value in values) * 1.4826
        if scale <= 1e-12:
            scale = statistics.pstdev(values)
        if scale <= 1e-12:
            scale = 1.0
        scales[metric] = {"center": center, "scale": scale}
    return scales


def _match_cost(
    target: Mapping[str, float | int | str],
    candidate: Mapping[str, float | int | str],
    scales: Mapping[str, Mapping[str, float]],
) -> float:
    total = 0.0
    for metric in MATCH_METRICS:
        difference = (
            _metric_transform(metric, float(target[metric]))
            - _metric_transform(metric, float(candidate[metric]))
        ) / float(scales[metric]["scale"])
        total += MATCH_WEIGHTS[metric] * difference * difference
    return total


def _minimum_cost_assignment(
    target_ids: Sequence[int],
    candidate_ids: Sequence[int],
    costs: Mapping[tuple[int, int], float],
) -> dict[int, int]:
    """Exact bitmask DP with a lexicographic tie-break on assigned IDs."""

    targets = tuple(int(value) for value in target_ids)
    empty = (-1,) * len(targets)
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, empty)}
    for candidate_id in sorted(int(value) for value in candidate_ids):
        updated = dict(states)
        for mask, (running_cost, assignment) in states.items():
            for target_index, target_id in enumerate(targets):
                if mask & (1 << target_index):
                    continue
                edge_cost = float(costs.get((target_id, candidate_id), math.inf))
                if not math.isfinite(edge_cost):
                    continue
                new_mask = mask | (1 << target_index)
                new_assignment = list(assignment)
                new_assignment[target_index] = candidate_id
                candidate_state = (running_cost + edge_cost, tuple(new_assignment))
                incumbent = updated.get(new_mask)
                if incumbent is None or candidate_state[0] < incumbent[0] - 1e-12 or (
                    abs(candidate_state[0] - incumbent[0]) <= 1e-12
                    and candidate_state[1] < incumbent[1]
                ):
                    updated[new_mask] = candidate_state
        states = updated
    final = states.get((1 << len(targets)) - 1)
    if final is None:
        raise CalibrationProtocolError(
            "no complete one-to-one assignment satisfies this caliper path"
        )
    return dict(zip(targets, final[1]))


def match_features(
    feature_metrics: Iterable[Mapping[str, Any]],
    candidate_ids: Sequence[int],
) -> dict[str, Any]:
    """Select exactly one fresh control per target under frozen matching rules."""

    metrics = validate_feature_metrics(feature_metrics, candidate_ids)
    scales = _robust_scales(metrics)
    failures: list[dict[str, str]] = []
    for calipers in CALIPER_PATHS:
        costs: dict[tuple[int, int], float] = {}
        for target_id in TARGET_FEATURE_IDS:
            target = metrics[target_id]
            for candidate_id in sorted(candidate_ids):
                candidate = metrics[int(candidate_id)]
                norm_ratio = float(candidate["decoder_norm"]) / float(
                    target["decoder_norm"]
                )
                if not (
                    float(calipers["decoder_norm_ratio_low"])
                    <= norm_ratio
                    <= float(calipers["decoder_norm_ratio_high"])
                ):
                    continue
                if float(candidate["max_abs_target_cosine"]) > float(
                    calipers["max_abs_target_cosine"]
                ):
                    continue
                costs[(target_id, int(candidate_id))] = _match_cost(
                    target, candidate, scales
                )
        try:
            assignment = _minimum_cost_assignment(
                TARGET_FEATURE_IDS, candidate_ids, costs
            )
        except CalibrationProtocolError as exc:
            failures.append({"path": str(calipers["name"]), "reason": str(exc)})
            continue

        pairs: list[dict[str, Any]] = []
        for target_id in TARGET_FEATURE_IDS:
            control_id = assignment[target_id]
            target = metrics[target_id]
            control = metrics[control_id]
            pairs.append(
                {
                    "target_feature_id": target_id,
                    "control_feature_id": control_id,
                    "cost": costs[(target_id, control_id)],
                    "decoder_norm_ratio": float(control["decoder_norm"])
                    / float(target["decoder_norm"]),
                    "max_abs_target_cosine": float(
                        control["max_abs_target_cosine"]
                    ),
                }
            )
        return {
            "status": "pass",
            "matching_path": str(calipers["name"]),
            "calipers": dict(calipers),
            "fallback_was_used": calipers["name"] != "primary",
            "failed_prior_paths": failures,
            "metric_transforms": {
                "decoder_norm": "log1p",
                "mean_activation": "log1p",
                "max_activation": "log1p",
                "positive_token_fraction": "identity",
            },
            "metric_weights": dict(MATCH_WEIGHTS),
            "robust_scales": scales,
            "assignment_tie_break": (
                "minimum total cost, then lexicographically smallest control-ID "
                "tuple in TARGET_FEATURE_IDS order"
            ),
            "pairs": pairs,
        }

    raise CalibrationProtocolError(
        "control matching failed under primary and sole prespecified fallback"
    )


def matched_feature_map(matching: Mapping[str, Any]) -> dict[int, int]:
    if matching.get("status") != "pass":
        raise CalibrationProtocolError("matching receipt does not pass")
    mapping = {
        int(pair["target_feature_id"]): int(pair["control_feature_id"])
        for pair in matching.get("pairs", [])
    }
    if tuple(mapping) != TARGET_FEATURE_IDS:
        raise CalibrationProtocolError("matching pairs do not follow target order")
    controls = list(mapping.values())
    if len(controls) != len(set(controls)) or set(controls) & set(TARGET_FEATURE_IDS):
        raise CalibrationProtocolError("matched controls are not unique non-target IDs")
    return mapping


def compute_bf16_multiplier(
    *,
    hidden_rms_by_prompt: Mapping[str, float],
    target_vector_rms: Sequence[float],
    matched_vector_rms: Sequence[float],
) -> dict[str, Any]:
    """Derive the telemetry-only multiplier and enforce the stability cap."""

    expected_prompts = {str(row["prompt_id"]) for row in NEUTRAL_CALIBRATION_PROMPTS}
    if set(hidden_rms_by_prompt) != expected_prompts:
        raise CalibrationProtocolError("hidden-RMS prompt IDs differ from the frozen set")
    hidden_values = [
        _finite_float(hidden_rms_by_prompt[prompt_id], name=f"hidden_rms.{prompt_id}")
        for prompt_id in sorted(expected_prompts)
    ]
    if any(value <= 0 for value in hidden_values):
        raise CalibrationProtocolError("hidden RMS must be strictly positive")
    if len(target_vector_rms) != 50 or len(matched_vector_rms) != 50:
        raise CalibrationProtocolError("multiplier requires all 50 aggregate vectors")
    target_values = [
        _finite_float(value, name="target_vector_rms") for value in target_vector_rms
    ]
    matched_values = [
        _finite_float(value, name="matched_vector_rms") for value in matched_vector_rms
    ]
    if any(value <= 0 for value in (*target_values, *matched_values)):
        raise CalibrationProtocolError("aggregate vector RMS must be strictly positive")

    target_unit_relatives = [
        vector_rms / hidden_rms
        for vector_rms in target_values
        for hidden_rms in hidden_values
    ]
    all_unit_relatives = [
        vector_rms / hidden_rms
        for vector_rms in (*target_values, *matched_values)
        for hidden_rms in hidden_values
    ]
    median_target_unit_relative = statistics.median(target_unit_relatives)
    maximum_unit_relative = max(all_unit_relatives)
    raw_target_multiplier = (
        CALIBRATED_TARGET_RELATIVE_RMS / median_target_unit_relative
    )
    stability_multiplier_cap = CALIBRATED_MAX_RELATIVE_RMS / maximum_unit_relative
    upper = min(
        raw_target_multiplier,
        stability_multiplier_cap,
        CALIBRATED_MAX_MULTIPLIER,
    )
    if upper < CALIBRATED_MIN_MULTIPLIER - 1e-12:
        raise CalibrationProtocolError(
            "literal aggregate scale violates the frozen relative-RMS stability cap"
        )

    selected = max(CALIBRATED_MIN_MULTIPLIER, upper)
    factor = 10**CALIBRATED_MULTIPLIER_DECIMALS
    # Flooring is conservative with respect to both hard caps.
    selected = math.floor((selected + 1e-12) * factor) / factor
    selected = max(CALIBRATED_MIN_MULTIPLIER, selected)
    maximum_calibrated_relative = selected * maximum_unit_relative
    median_calibrated_target_relative = selected * median_target_unit_relative
    if maximum_calibrated_relative > CALIBRATED_MAX_RELATIVE_RMS + 1e-12:
        raise CalibrationProtocolError("rounded multiplier exceeds the stability cap")

    limiting_caps: list[str] = []
    minimum_upper = min(
        raw_target_multiplier,
        stability_multiplier_cap,
        CALIBRATED_MAX_MULTIPLIER,
    )
    for name, value in (
        ("target_relative_rms", raw_target_multiplier),
        ("stability_relative_rms", stability_multiplier_cap),
        ("hard_multiplier", CALIBRATED_MAX_MULTIPLIER),
    ):
        if abs(value - minimum_upper) <= 1e-12:
            limiting_caps.append(name)
    if selected == CALIBRATED_MIN_MULTIPLIER and raw_target_multiplier < 1.0:
        limiting_caps.append("literal_scale_floor")

    return {
        "method": "bf16_aggregate_vector_rms_over_neutral_hidden_rms_v1",
        "target_relative_rms": CALIBRATED_TARGET_RELATIVE_RMS,
        "maximum_relative_rms": CALIBRATED_MAX_RELATIVE_RMS,
        "minimum_multiplier": CALIBRATED_MIN_MULTIPLIER,
        "maximum_multiplier": CALIBRATED_MAX_MULTIPLIER,
        "rounding": f"floor_to_{CALIBRATED_MULTIPLIER_DECIMALS}_decimals",
        "median_target_unit_relative_rms": median_target_unit_relative,
        "maximum_target_or_matched_unit_relative_rms": maximum_unit_relative,
        "raw_target_multiplier": raw_target_multiplier,
        "stability_multiplier_cap": stability_multiplier_cap,
        "limiting_caps": limiting_caps,
        "calibrated_multiplier": selected,
        "median_calibrated_target_relative_rms": median_calibrated_target_relative,
        "maximum_calibrated_relative_rms": maximum_calibrated_relative,
        "outcome_inputs": [],
    }


def validate_prompt_receipts(
    prompt_receipts: Sequence[Mapping[str, Any]],
    hidden_rms_by_prompt: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Bind tokenization receipts to the exact neutral texts and hidden RMS."""

    if len(prompt_receipts) != len(NEUTRAL_CALIBRATION_PROMPTS):
        raise CalibrationProtocolError("neutral prompt receipts are incomplete")
    normalized: list[dict[str, Any]] = []
    for expected, raw in zip(NEUTRAL_CALIBRATION_PROMPTS, prompt_receipts):
        prompt_id = str(expected["prompt_id"])
        if raw.get("prompt_id") != prompt_id:
            raise CalibrationProtocolError("neutral prompt receipt order differs")
        if raw.get("prompt_utf8_sha256") != sha256_bytes(
            str(expected["text"]).encode("utf-8")
        ):
            raise CalibrationProtocolError(f"neutral prompt text hash differs: {prompt_id}")
        token_count = raw.get("rendered_token_count")
        if isinstance(token_count, bool) or not isinstance(token_count, int) or token_count <= 0:
            raise CalibrationProtocolError(f"neutral token count is invalid: {prompt_id}")
        token_hash = raw.get("rendered_token_ids_sha256")
        if (
            not isinstance(token_hash, str)
            or len(token_hash) != 64
            or any(character not in "0123456789abcdef" for character in token_hash)
        ):
            raise CalibrationProtocolError(f"neutral token hash is invalid: {prompt_id}")
        if raw.get("sampled_output") is not False:
            raise CalibrationProtocolError("neutral calibration may not sample output")
        observed_rms = _finite_float(raw.get("hidden_rms"), name=f"{prompt_id}.hidden_rms")
        bound_rms = _finite_float(
            hidden_rms_by_prompt.get(prompt_id), name=f"hidden_rms.{prompt_id}"
        )
        if observed_rms <= 0 or observed_rms != bound_rms:
            raise CalibrationProtocolError(f"neutral hidden RMS binding differs: {prompt_id}")
        normalized.append(dict(raw))
    if set(hidden_rms_by_prompt) != {
        str(prompt["prompt_id"]) for prompt in NEUTRAL_CALIBRATION_PROMPTS
    }:
        raise CalibrationProtocolError("hidden-RMS prompt IDs differ")
    return normalized


def validate_aggregate_vector_receipts(
    aggregate_vectors: Sequence[Mapping[str, Any]],
    matching: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate exact block identity, matched IDs, BF16 hashes, and RMS values."""

    expected_blocks = aggregate_blocks()
    if len(aggregate_vectors) != len(expected_blocks):
        raise CalibrationProtocolError("aggregate vector receipts are incomplete")
    mapping = matched_feature_map(matching)
    normalized: list[dict[str, Any]] = []
    for expected, raw in zip(expected_blocks, aggregate_vectors):
        target_ids = [int(value) for value in expected["target_feature_ids"]]
        matched_ids = [mapping[target] for target in target_ids]
        if raw.get("block_id") != expected["block_id"]:
            raise CalibrationProtocolError("aggregate vector block order differs")
        if raw.get("target_feature_ids") != target_ids:
            raise CalibrationProtocolError(
                f"aggregate target IDs differ: {expected['block_id']}"
            )
        if raw.get("matched_feature_ids") != matched_ids:
            raise CalibrationProtocolError(
                f"aggregate matched IDs differ: {expected['block_id']}"
            )
        if [float(value) for value in raw.get("magnitudes", [])] != [
            float(value) for value in expected["magnitudes"]
        ]:
            raise CalibrationProtocolError(
                f"aggregate magnitudes differ: {expected['block_id']}"
            )
        for role in ("target", "matched"):
            digest = raw.get(f"{role}_vector_bf16_sha256")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise CalibrationProtocolError(
                    f"aggregate {role} vector hash is invalid: {expected['block_id']}"
                )
            rms = _finite_float(
                raw.get(f"{role}_vector_rms"),
                name=f"{expected['block_id']}.{role}_vector_rms",
            )
            if rms <= 0:
                raise CalibrationProtocolError(
                    f"aggregate {role} vector RMS is nonpositive: {expected['block_id']}"
                )
        normalized.append(dict(raw))
    return normalized


def _state_key(state: Mapping[str, Any], suffix: str) -> str:
    matches = [key for key in state if key == suffix or key.endswith("." + suffix)]
    if len(matches) != 1:
        raise CalibrationProtocolError(
            f"expected one SAE state key ending in {suffix!r}, found {matches}"
        )
    return matches[0]


def _tensor_sha256(tensor: Any) -> str:
    contiguous = tensor.detach().to(device="cpu").contiguous()
    return hashlib.sha256(contiguous.view(_torch().uint8).numpy()).hexdigest()


def _torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised on GPU runtime
        raise RuntimeError("PyTorch is required for calibration runtime") from exc
    return torch


def _input_ids(tokenized: Any) -> Any:
    torch = _torch()
    if torch.is_tensor(tokenized):
        return tokenized
    if isinstance(tokenized, Mapping) and "input_ids" in tokenized:
        return tokenized["input_ids"]
    if hasattr(tokenized, "input_ids"):
        return tokenized.input_ids
    raise CalibrationProtocolError(
        f"unsupported tokenizer result type {type(tokenized).__name__}"
    )


def validate_artifact_receipt(
    receipt: Mapping[str, Any], *, expected_volume_id: str
) -> str:
    """Validate and return the artifact receipt's embedded canonical hash."""

    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise CalibrationProtocolError("artifact receipt does not pass for this study")
    if receipt.get("outcome_blind") is not True or receipt.get("prior_outcome_inputs") != []:
        raise CalibrationProtocolError("artifact receipt is not outcome-blind")
    if receipt.get("expected_volume_id") != expected_volume_id:
        raise CalibrationProtocolError("artifact receipt volume ID differs")
    embedded = receipt.get("receipt_sha256")
    if not isinstance(embedded, str) or len(embedded) != 64:
        raise CalibrationProtocolError("artifact receipt lacks its canonical hash")
    without_hash = dict(receipt)
    without_hash.pop("receipt_sha256", None)
    if sha256_json(without_hash) != embedded:
        raise CalibrationProtocolError("artifact receipt canonical hash differs")
    model = receipt.get("model", {})
    if model.get("id") != MODEL_ID or model.get("revision") != MODEL_REVISION:
        raise CalibrationProtocolError("artifact receipt model pin differs")
    sae = receipt.get("sae", {})
    if sae.get("file_sha256") != SAE_FILE_SHA256:
        raise CalibrationProtocolError("artifact receipt SAE hash differs")
    tokenizer = receipt.get("tokenizer", {})
    if tokenizer.get("len") != TOKENIZER_SIZE:
        raise CalibrationProtocolError("artifact receipt tokenizer size differs")
    return embedded


def _load_public_artifacts(cache_dir: Path) -> tuple[Any, Any, Any, Any, dict[str, str]]:
    torch = _torch()
    from huggingface_hub import hf_hub_download, snapshot_download
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise CalibrationProtocolError("calibration requires exactly one CUDA GPU")
    properties = torch.cuda.get_device_properties(0)
    if properties.total_memory < 170 * 1024**3:
        raise CalibrationProtocolError("calibration GPU has less than 170 GiB")

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    snapshot = Path(
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    )
    sae_path = Path(
        hf_hub_download(
            repo_id=SAE_ID,
            filename=SAE_FILENAME,
            revision=SAE_REVISION,
            cache_dir=cache_dir,
            token=token,
            local_files_only=True,
        )
    )
    if sha256_file(sae_path) != SAE_FILE_SHA256:
        raise CalibrationProtocolError("live SAE file hash differs from the pin")

    tokenizer = AutoTokenizer.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=False, use_fast=True
    )
    if len(tokenizer) != TOKENIZER_SIZE:
        raise CalibrationProtocolError("live tokenizer size differs")
    model = AutoModelForCausalLM.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    )
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    config = model.config.get_text_config()
    if int(config.hidden_size) != MODEL_WIDTH or int(config.num_hidden_layers) != MODEL_LAYERS:
        raise CalibrationProtocolError("live model architecture differs")
    if len(model.model.layers) != MODEL_LAYERS:
        raise CalibrationProtocolError("live decoder-layer layout differs")
    if next(model.parameters()).dtype != torch.bfloat16:
        raise CalibrationProtocolError("live model is not BF16")

    state = torch.load(sae_path, map_location="cpu", weights_only=True, mmap=True)
    keys = {
        suffix: _state_key(state, suffix)
        for suffix in (
            "encoder_linear.weight",
            "encoder_linear.bias",
            "decoder_linear.weight",
        )
    }
    encoder = state[keys["encoder_linear.weight"]]
    decoder = state[keys["decoder_linear.weight"]]
    if tuple(encoder.shape) != (SAE_WIDTH, MODEL_WIDTH):
        raise CalibrationProtocolError("live SAE encoder shape differs")
    if tuple(decoder.shape) != (MODEL_WIDTH, SAE_WIDTH):
        raise CalibrationProtocolError("live SAE decoder shape differs")
    return torch, model, tokenizer, state, keys


def measure_neutral_telemetry(
    torch: Any,
    model: Any,
    tokenizer: Any,
    sae_state: Mapping[str, Any],
    sae_keys: Mapping[str, str],
    candidate_ids: Sequence[int],
) -> tuple[list[dict[str, Any]], dict[str, float], list[dict[str, Any]], Any]:
    """Measure selected SAE features on the fixed neutral prompt battery."""

    import torch.nn.functional as functional

    feature_ids = list(TARGET_FEATURE_IDS) + [int(value) for value in candidate_ids]
    encoder = sae_state[sae_keys["encoder_linear.weight"]][feature_ids].to(
        device="cuda", dtype=torch.bfloat16
    )
    encoder_bias = sae_state[sae_keys["encoder_linear.bias"]][feature_ids].to(
        device="cuda", dtype=torch.bfloat16
    )
    selected_decoder = (
        sae_state[sae_keys["decoder_linear.weight"]][:, feature_ids]
        .T.contiguous()
        .float()
    )
    if not bool(torch.isfinite(encoder).all()) or not bool(
        torch.isfinite(selected_decoder).all()
    ):
        raise CalibrationProtocolError("selected SAE weights contain nonfinite values")

    decoder_norms = selected_decoder.square().sum(dim=1).sqrt()
    if not bool((decoder_norms > 0).all()):
        raise CalibrationProtocolError("selected SAE decoder direction has zero norm")
    normalized = selected_decoder / decoder_norms[:, None]
    target_normalized = normalized[: len(TARGET_FEATURE_IDS)]
    max_target_cosines = (normalized @ target_normalized.T).abs().max(dim=1).values

    activation_sums = torch.zeros(len(feature_ids), dtype=torch.float64)
    activation_max = torch.zeros(len(feature_ids), dtype=torch.float32)
    activation_positive = torch.zeros(len(feature_ids), dtype=torch.int64)
    activation_positions = 0
    hidden_rms_by_prompt: dict[str, float] = {}
    prompt_receipts: list[dict[str, Any]] = []
    layer = model.model.layers[SAE_LAYER]

    for prompt in NEUTRAL_CALIBRATION_PROMPTS:
        prompt_id = str(prompt["prompt_id"])
        tokenized = tokenizer.apply_chat_template(
            [{"role": "user", "content": str(prompt["text"])}],
            add_generation_prompt=True,
            return_tensors="pt",
        )
        input_ids = _input_ids(tokenized).to(device="cuda")
        if input_ids.ndim != 2 or int(input_ids.shape[0]) != 1:
            raise CalibrationProtocolError("neutral prompt tokenization is not [1, seq]")
        captured: dict[str, Any] = {}

        def hook(_module: Any, _inputs: Any, output: Any) -> None:
            if captured:
                raise CalibrationProtocolError("layer-50 calibration hook fired twice")
            hidden = output[0] if isinstance(output, tuple) else output
            captured["hidden"] = hidden.detach()

        handle = layer.register_forward_hook(hook)
        try:
            with torch.inference_mode():
                output = model.model(
                    input_ids=input_ids,
                    attention_mask=torch.ones_like(input_ids, dtype=torch.long),
                    use_cache=False,
                    return_dict=True,
                )
        finally:
            handle.remove()
        if "hidden" not in captured:
            raise CalibrationProtocolError("layer-50 calibration hook did not fire")
        hidden = captured.pop("hidden")
        if hidden.ndim != 3 or int(hidden.shape[-1]) != MODEL_WIDTH:
            raise CalibrationProtocolError("captured layer-50 hidden shape differs")
        flat = hidden.reshape(-1, MODEL_WIDTH)
        hidden_rms = float(flat.float().square().mean().sqrt().item())
        if not math.isfinite(hidden_rms) or hidden_rms <= 0:
            raise CalibrationProtocolError("neutral prompt hidden RMS is invalid")
        with torch.inference_mode():
            activations = functional.relu(
                functional.linear(flat.to(dtype=torch.bfloat16), encoder, encoder_bias)
            ).float()
        cpu_activations = activations.cpu()
        activation_sums += cpu_activations.double().sum(dim=0)
        activation_max = torch.maximum(
            activation_max, cpu_activations.max(dim=0).values
        )
        activation_positive += (cpu_activations > 0).sum(dim=0)
        positions = int(cpu_activations.shape[0])
        activation_positions += positions
        hidden_rms_by_prompt[prompt_id] = hidden_rms
        ids = [int(value) for value in input_ids[0].detach().cpu().tolist()]
        prompt_receipts.append(
            {
                "prompt_id": prompt_id,
                "prompt_utf8_sha256": sha256_bytes(str(prompt["text"]).encode("utf-8")),
                "rendered_token_count": len(ids),
                "rendered_token_ids_sha256": sha256_json(ids),
                "hidden_rms": hidden_rms,
                "sampled_output": False,
            }
        )
        del output, hidden, flat, activations, cpu_activations, input_ids, tokenized

    rows: list[dict[str, Any]] = []
    for index, feature_id in enumerate(feature_ids):
        rows.append(
            {
                "feature_id": feature_id,
                "feature_role": (
                    "target" if feature_id in TARGET_FEATURE_IDS else "candidate"
                ),
                "decoder_norm": float(decoder_norms[index].item()),
                "max_abs_target_cosine": float(max_target_cosines[index].item()),
                "mean_activation": float(
                    activation_sums[index].item() / activation_positions
                ),
                "max_activation": float(activation_max[index].item()),
                "positive_token_fraction": float(
                    activation_positive[index].item() / activation_positions
                ),
                "n_prompt_positions": activation_positions,
            }
        )
    validate_feature_metrics(rows, candidate_ids)
    return rows, hidden_rms_by_prompt, prompt_receipts, selected_decoder


def aggregate_vector_receipts(
    torch: Any,
    selected_decoder: Any,
    candidate_ids: Sequence[int],
    matching: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Construct and hash the exact unsigned BF16 target/matched block vectors."""

    feature_ids = list(TARGET_FEATURE_IDS) + [int(value) for value in candidate_ids]
    index_by_id = {feature_id: index for index, feature_id in enumerate(feature_ids)}
    mapping = matched_feature_map(matching)
    decoder = selected_decoder.to(device="cuda", dtype=torch.bfloat16)
    receipts: list[dict[str, Any]] = []
    for block in aggregate_blocks():
        target_ids = [int(value) for value in block["target_feature_ids"]]
        control_ids = [mapping[target] for target in target_ids]
        coefficients = torch.tensor(
            [float(value) for value in block["magnitudes"]],
            device="cuda",
            dtype=torch.bfloat16,
        )
        target_rows = decoder[[index_by_id[value] for value in target_ids]]
        matched_rows = decoder[[index_by_id[value] for value in control_ids]]
        target_vector = (target_rows * coefficients[:, None]).sum(dim=0)
        matched_vector = (matched_rows * coefficients[:, None]).sum(dim=0)
        if not bool(torch.isfinite(target_vector).all()) or not bool(
            torch.isfinite(matched_vector).all()
        ):
            raise CalibrationProtocolError("aggregate BF16 vector is nonfinite")
        receipts.append(
            {
                "block_id": str(block["block_id"]),
                "target_feature_ids": target_ids,
                "matched_feature_ids": control_ids,
                "magnitudes": [float(value) for value in block["magnitudes"]],
                "target_vector_bf16_sha256": _tensor_sha256(target_vector),
                "matched_vector_bf16_sha256": _tensor_sha256(matched_vector),
                "target_vector_rms": float(
                    target_vector.float().square().mean().sqrt().item()
                ),
                "matched_vector_rms": float(
                    matched_vector.float().square().mean().sqrt().item()
                ),
            }
        )
    if len(receipts) != 50:
        raise CalibrationProtocolError("aggregate vector receipt count differs")
    return receipts


def runtime_metadata(torch: Any) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for package in (
        "accelerate",
        "huggingface-hub",
        "safetensors",
        "torch",
        "transformers",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    properties = torch.cuda.get_device_properties(0)
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
        "cuda_runtime": torch.version.cuda,
        "gpu": properties.name,
        "gpu_total_memory_bytes": int(properties.total_memory),
        "model_parameter_dtype": MODEL_DTYPE,
        "sae_telemetry_dtype": "bfloat16",
    }


def build_receipt(
    *,
    artifact_receipt: Mapping[str, Any],
    artifact_receipt_file_sha256: str,
    expected_volume_id: str,
    candidate_ids: Sequence[int],
    candidate_screening: Sequence[Mapping[str, Any]] | None = None,
    feature_metrics: Sequence[Mapping[str, Any]],
    hidden_rms_by_prompt: Mapping[str, float],
    prompt_receipts: Sequence[Mapping[str, Any]],
    matching: Mapping[str, Any],
    aggregate_vectors: Sequence[Mapping[str, Any]],
    multiplier_calibration: Mapping[str, Any],
    runtime: Mapping[str, Any],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the sole passing calibration receipt schema."""

    artifact_embedded_hash = validate_artifact_receipt(
        artifact_receipt, expected_volume_id=expected_volume_id
    )
    candidates = [int(value) for value in candidate_ids]
    validated_metrics = validate_feature_metrics(feature_metrics, candidates)
    canonical_metrics = [validated_metrics[feature_id] for feature_id in sorted(validated_metrics)]
    if candidate_screening is None:
        # Synthetic/unit-test construction: all first 512 ranked rows are
        # explicitly eligible. Real calibration always passes the live screen.
        if candidates != build_candidate_pool():
            raise CalibrationProtocolError("candidate IDs differ from unscreened hash prefix")
        candidate_screening = [
            {
                "feature_id": feature_id,
                "eligible": True,
                "reason": "selected",
                "decoder_norm": float(validated_metrics[feature_id]["decoder_norm"]),
            }
            for feature_id in candidates
        ]
    validated_screening = validate_candidate_screening(
        candidate_screening, candidates
    )
    recomputed_matching = match_features(canonical_metrics, candidates)
    if canonical_json_bytes(recomputed_matching) != canonical_json_bytes(matching):
        raise CalibrationProtocolError("matching result differs from independent reconstruction")
    mapping = matched_feature_map(matching)
    validated_vectors = validate_aggregate_vector_receipts(aggregate_vectors, matching)
    target_rms = [float(row["target_vector_rms"]) for row in validated_vectors]
    matched_rms = [float(row["matched_vector_rms"]) for row in validated_vectors]
    recomputed_multiplier = compute_bf16_multiplier(
        hidden_rms_by_prompt=hidden_rms_by_prompt,
        target_vector_rms=target_rms,
        matched_vector_rms=matched_rms,
    )
    if canonical_json_bytes(recomputed_multiplier) != canonical_json_bytes(
        multiplier_calibration
    ):
        raise CalibrationProtocolError("multiplier result differs from reconstruction")
    expected_prompt_ids = [str(row["prompt_id"]) for row in NEUTRAL_CALIBRATION_PROMPTS]
    validated_prompt_receipts = validate_prompt_receipts(
        prompt_receipts, hidden_rms_by_prompt
    )

    source_files = [
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("protocol.py"),
    ]
    source_records = [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in source_files
    ]
    model_inventory = artifact_receipt["model"]["files"]
    payload: dict[str, Any] = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "status": "pass",
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "phase": "target_blind_calibration",
        "created_at_utc": created_at_utc or utc_now(),
        "outcome_blind": True,
        "target_outcomes_opened": False,
        "prior_outcome_inputs": [],
        "input_policy": (
            "pinned public model/SAE, target-blind artifact receipt, and fresh "
            "neutral prompts only"
        ),
        "expected_volume_id": expected_volume_id,
        "public_sources": {
            "artifact_receipt_embedded_sha256": artifact_embedded_hash,
            "artifact_receipt_file_sha256": artifact_receipt_file_sha256,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "model_snapshot_inventory_sha256": sha256_json(model_inventory),
            "sae_id": SAE_ID,
            "sae_revision": SAE_REVISION,
            "sae_file_sha256": SAE_FILE_SHA256,
            "tokenizer_receipt_sha256": sha256_json(artifact_receipt["tokenizer"]),
        },
        "neutral_prompts": {
            "prompt_set_sha256": prompt_set_sha256(),
            "prompt_ids": expected_prompt_ids,
            "prompt_receipts": validated_prompt_receipts,
            "sampled_outputs": 0,
            "target_prompt_inputs": [],
        },
        "candidate_selection": {
            "algorithm": "ascending_sha256_then_finite_nonzero_tensor_screen",
            "ranking_domain": CANDIDATE_RANKING_DOMAIN,
            "dictionary_size": SAE_WIDTH,
            "pool_size": CANDIDATE_POOL_SIZE,
            "excluded_feature_ids": list(TARGET_FEATURE_IDS),
            "candidate_feature_ids": candidates,
            "candidate_pool_sha256": candidate_pool_sha256(candidates),
            "screening_rows": validated_screening,
            "screening_rows_sha256": sha256_json(validated_screening),
        },
        "telemetry": {
            "hook_layer": SAE_LAYER,
            "activation_precision": "bfloat16",
            "feature_metrics": canonical_metrics,
            "feature_metrics_sha256": sha256_json(canonical_metrics),
            "hidden_rms_by_prompt": dict(sorted(hidden_rms_by_prompt.items())),
            "hidden_rms_sha256": sha256_json(dict(sorted(hidden_rms_by_prompt.items()))),
            "outcome_fields": [],
        },
        "matching": dict(matching),
        "matched_feature_map": {str(target): mapping[target] for target in TARGET_FEATURE_IDS},
        "aggregate_vectors": {
            "precision": "bfloat16",
            "sign": "unsigned base vector; suppression is exact negation",
            "blocks": validated_vectors,
            "blocks_sha256": sha256_json(validated_vectors),
        },
        "multiplier_calibration": dict(multiplier_calibration),
        "calibrated_multiplier": float(multiplier_calibration["calibrated_multiplier"]),
        "calibrated_scale_role": "Stage 2B sensitivity only; cannot rescue literal primary",
        "runtime": dict(runtime),
        "source_files": source_records,
    }
    payload["receipt_sha256"] = sha256_json(payload)
    validate_calibration_receipt(payload)
    return payload


def validate_calibration_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Independently reconstruct every pure decision encoded in a receipt."""

    if receipt.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise CalibrationProtocolError("calibration schema version differs")
    if receipt.get("status") != "pass" or receipt.get("study_id") != STUDY_ID:
        raise CalibrationProtocolError("calibration receipt does not pass for this study")
    if receipt.get("protocol_version") != PROTOCOL_VERSION:
        raise CalibrationProtocolError("calibration protocol version differs")
    if receipt.get("phase") != "target_blind_calibration":
        raise CalibrationProtocolError("calibration phase differs")
    if receipt.get("outcome_blind") is not True:
        raise CalibrationProtocolError("calibration receipt is not outcome-blind")
    if receipt.get("target_outcomes_opened") is not False:
        raise CalibrationProtocolError("target outcomes were opened during calibration")
    if receipt.get("prior_outcome_inputs") != []:
        raise CalibrationProtocolError("calibration receipt includes prior outcomes")
    embedded = receipt.get("receipt_sha256")
    if not isinstance(embedded, str) or len(embedded) != 64:
        raise CalibrationProtocolError("calibration receipt lacks a canonical hash")
    without_hash = dict(receipt)
    without_hash.pop("receipt_sha256", None)
    if sha256_json(without_hash) != embedded:
        raise CalibrationProtocolError("calibration receipt canonical hash differs")

    public = receipt.get("public_sources", {})
    for key, expected in (
        ("model_id", MODEL_ID),
        ("model_revision", MODEL_REVISION),
        ("sae_id", SAE_ID),
        ("sae_revision", SAE_REVISION),
        ("sae_file_sha256", SAE_FILE_SHA256),
    ):
        if public.get(key) != expected:
            raise CalibrationProtocolError(f"receipt public-source {key} differs")
    for key in (
        "artifact_receipt_embedded_sha256",
        "artifact_receipt_file_sha256",
        "model_snapshot_inventory_sha256",
        "tokenizer_receipt_sha256",
    ):
        digest = public.get(key)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise CalibrationProtocolError(f"receipt public-source {key} is invalid")

    candidate = receipt.get("candidate_selection", {})
    if candidate.get("algorithm") != "ascending_sha256_then_finite_nonzero_tensor_screen":
        raise CalibrationProtocolError("receipt candidate algorithm differs")
    if candidate.get("ranking_domain") != CANDIDATE_RANKING_DOMAIN:
        raise CalibrationProtocolError("receipt candidate ranking domain differs")
    if candidate.get("dictionary_size") != SAE_WIDTH:
        raise CalibrationProtocolError("receipt candidate dictionary size differs")
    if candidate.get("pool_size") != CANDIDATE_POOL_SIZE:
        raise CalibrationProtocolError("receipt candidate pool size differs")
    ids = [int(value) for value in candidate.get("candidate_feature_ids", [])]
    screening = validate_candidate_screening(
        candidate.get("screening_rows", []), ids
    )
    if candidate.get("screening_rows_sha256") != sha256_json(screening):
        raise CalibrationProtocolError("receipt candidate screening hash differs")
    if candidate.get("excluded_feature_ids") != list(TARGET_FEATURE_IDS):
        raise CalibrationProtocolError("receipt candidate exclusions differ")
    if candidate.get("candidate_pool_sha256") != candidate_pool_sha256(ids):
        raise CalibrationProtocolError("receipt candidate-pool hash differs")

    neutral = receipt.get("neutral_prompts", {})
    if neutral.get("prompt_set_sha256") != prompt_set_sha256():
        raise CalibrationProtocolError("receipt neutral-prompt hash differs")
    if neutral.get("prompt_ids") != [
        str(prompt["prompt_id"]) for prompt in NEUTRAL_CALIBRATION_PROMPTS
    ]:
        raise CalibrationProtocolError("receipt neutral-prompt IDs differ")
    if neutral.get("target_prompt_inputs") != [] or neutral.get("sampled_outputs") != 0:
        raise CalibrationProtocolError("receipt contains a target or sampled calibration input")

    telemetry = receipt.get("telemetry", {})
    if telemetry.get("hook_layer") != SAE_LAYER:
        raise CalibrationProtocolError("receipt telemetry hook layer differs")
    if telemetry.get("activation_precision") != "bfloat16":
        raise CalibrationProtocolError("receipt telemetry precision differs")
    if telemetry.get("outcome_fields") != []:
        raise CalibrationProtocolError("receipt telemetry contains outcome fields")
    raw_metrics = telemetry.get("feature_metrics", [])
    metrics = validate_feature_metrics(raw_metrics, ids)
    canonical_metrics = [metrics[feature_id] for feature_id in sorted(metrics)]
    if telemetry.get("feature_metrics_sha256") != sha256_json(canonical_metrics):
        raise CalibrationProtocolError("receipt feature-metrics hash differs")
    hidden = telemetry.get("hidden_rms_by_prompt", {})
    if telemetry.get("hidden_rms_sha256") != sha256_json(dict(sorted(hidden.items()))):
        raise CalibrationProtocolError("receipt hidden-RMS hash differs")
    validate_prompt_receipts(neutral.get("prompt_receipts", []), hidden)

    matching = receipt.get("matching", {})
    reconstructed_matching = match_features(canonical_metrics, ids)
    if canonical_json_bytes(matching) != canonical_json_bytes(reconstructed_matching):
        raise CalibrationProtocolError("receipt matching reconstruction differs")
    mapping = matched_feature_map(matching)
    if receipt.get("matched_feature_map") != {
        str(target): mapping[target] for target in TARGET_FEATURE_IDS
    }:
        raise CalibrationProtocolError("receipt matched-feature map differs")

    aggregate = receipt.get("aggregate_vectors", {})
    if aggregate.get("precision") != "bfloat16":
        raise CalibrationProtocolError("receipt aggregate-vector precision differs")
    if aggregate.get("sign") != "unsigned base vector; suppression is exact negation":
        raise CalibrationProtocolError("receipt aggregate-vector sign contract differs")
    blocks = aggregate.get("blocks", [])
    validated_blocks = validate_aggregate_vector_receipts(blocks, matching)
    if aggregate.get("blocks_sha256") != sha256_json(validated_blocks):
        raise CalibrationProtocolError("receipt aggregate-vector inventory differs")
    multiplier = compute_bf16_multiplier(
        hidden_rms_by_prompt=hidden,
        target_vector_rms=[float(row["target_vector_rms"]) for row in validated_blocks],
        matched_vector_rms=[float(row["matched_vector_rms"]) for row in validated_blocks],
    )
    if canonical_json_bytes(multiplier) != canonical_json_bytes(
        receipt.get("multiplier_calibration", {})
    ):
        raise CalibrationProtocolError("receipt multiplier reconstruction differs")
    if float(receipt.get("calibrated_multiplier")) != float(
        multiplier["calibrated_multiplier"]
    ):
        raise CalibrationProtocolError("receipt calibrated multiplier differs")
    if (
        receipt.get("calibrated_scale_role")
        != "Stage 2B sensitivity only; cannot rescue literal primary"
    ):
        raise CalibrationProtocolError("receipt calibrated-scale role differs")
    return {
        "status": "pass",
        "receipt_sha256": embedded,
        "matching_path": matching["matching_path"],
        "matched_feature_map": mapping,
        "calibrated_multiplier": multiplier["calibrated_multiplier"],
    }


def _atomic_write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    payload = json.dumps(
        receipt, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    if temporary.exists():
        raise CalibrationProtocolError(f"temporary receipt already exists: {temporary}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != payload:
            raise CalibrationProtocolError("calibration receipt read-back differs")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(
    *,
    cache_dir: Path,
    artifact_receipt_path: Path,
    artifact_root: str | Path | None,
    run_id: str,
    volume_id: str,
) -> dict[str, Any]:
    root = paths.require_external_artifact_root(
        artifact_root, expected_volume_id=volume_id, write_read_probe=True
    )
    resolved_cache = cache_dir.expanduser().resolve()
    try:
        resolved_cache.relative_to(root)
    except ValueError as exc:
        raise CalibrationProtocolError("model cache must be beneath the external root") from exc
    if not resolved_cache.is_dir():
        raise CalibrationProtocolError("model cache directory does not exist")

    resolved_artifact = artifact_receipt_path.expanduser()
    if not resolved_artifact.is_absolute():
        resolved_artifact = root / resolved_artifact
    resolved_artifact = resolved_artifact.resolve()
    try:
        artifact_relative = resolved_artifact.relative_to(root)
    except ValueError as exc:
        raise CalibrationProtocolError("artifact receipt must be beneath the external root") from exc
    artifact = json.loads(resolved_artifact.read_text(encoding="utf-8"))
    validate_artifact_receipt(artifact, expected_volume_id=volume_id)
    if resolved_artifact.name != "artifact_receipt.json":
        raise CalibrationProtocolError("artifact receipt filename differs")
    try:
        sealed_artifact = verify_completed_run(resolved_artifact.parent)
    except Exception as exc:
        raise CalibrationProtocolError(
            "artifact receipt is not inside a verified completed transaction"
        ) from exc

    transaction = RunTransaction.start(
        phase="calibration",
        run_id=run_id,
        artifact_root=root,
        expected_volume_id=volume_id,
        metadata={
            "study_id": STUDY_ID,
            "protocol_version": PROTOCOL_VERSION,
            "outcome_blind": True,
            "target_outcomes_opened": False,
            "prior_outcome_inputs": [],
            "artifact_manifest_sha256": sealed_artifact["manifest_sha256"],
        },
    )

    torch, model, tokenizer, sae_state, sae_keys = _load_public_artifacts(resolved_cache)
    candidate_ids, candidate_screening = screen_candidate_pool(
        torch, sae_state, sae_keys
    )
    metrics, hidden_rms, prompt_receipts, decoder = measure_neutral_telemetry(
        torch, model, tokenizer, sae_state, sae_keys, candidate_ids
    )
    matching = match_features(metrics, candidate_ids)
    vector_receipts = aggregate_vector_receipts(
        torch, decoder, candidate_ids, matching
    )
    multiplier = compute_bf16_multiplier(
        hidden_rms_by_prompt=hidden_rms,
        target_vector_rms=[row["target_vector_rms"] for row in vector_receipts],
        matched_vector_rms=[row["matched_vector_rms"] for row in vector_receipts],
    )
    receipt = build_receipt(
        artifact_receipt=artifact,
        artifact_receipt_file_sha256=sha256_file(resolved_artifact),
        expected_volume_id=volume_id,
        candidate_ids=candidate_ids,
        candidate_screening=candidate_screening,
        feature_metrics=metrics,
        hidden_rms_by_prompt=hidden_rms,
        prompt_receipts=prompt_receipts,
        matching=matching,
        aggregate_vectors=vector_receipts,
        multiplier_calibration=multiplier,
        runtime={
            **runtime_metadata(torch),
            "artifact_receipt_relative_path": artifact_relative.as_posix(),
        },
    )
    transaction.write_json("calibration_receipt.json", receipt)
    completed = transaction.complete(
        metadata={
            "study_id": STUDY_ID,
            "calibration_receipt_sha256": receipt["receipt_sha256"],
            "artifact_manifest_sha256": sealed_artifact["manifest_sha256"],
            "outcome_blind": True,
        }
    )
    sealed_calibration = verify_completed_run(completed)
    destination = completed / "calibration_receipt.json"
    reread = json.loads(destination.read_text(encoding="utf-8"))
    validation = validate_calibration_receipt(reread)
    return {
        **validation,
        "completed_directory": completed.relative_to(root).as_posix(),
        "remote_manifest_sha256": sealed_calibration["manifest_sha256"],
        "candidate_pool_sha256": candidate_pool_sha256(candidate_ids),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--artifact-receipt", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--volume-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(
        cache_dir=args.cache_dir,
        artifact_receipt_path=args.artifact_receipt,
        artifact_root=args.artifact_root,
        run_id=args.run_id,
        volume_id=args.volume_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
