"""Outcome-blind constants and deterministic plan construction for this study.

This module deliberately contains no model loading and reads no result artifact.
All randomized allocations are hash-derived so rebuilding a plan does not depend
on process-global RNG state, batch order, or a Python ``random`` implementation.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS
from experiments.consciousness_sae_changepoint.judge_prompts import (
    BINARY_QUERY_SYSTEM_PROMPT_SHA256,
    HUMAN_BINARY_SAMPLE_SIZE,
    HUMAN_NATURAL_SAMPLE_SIZE,
    HUMAN_SELECTION_SEED,
    NATURAL_STANCE_SYSTEM_PROMPT_SHA256,
)


PROTOCOL_VERSION = "consciousness_sae_changepoint_v1.1.0"
STUDY_SLUG = "consciousness_sae_changepoint"
STUDY_ID = "consciousness_sae_changepoint_v1"
PLAN_SCHEMA_VERSION = 1

MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
MODEL_DTYPE = "bfloat16"
MODEL_LAYERS = 80
MODEL_WIDTH = 8192
TOKENIZER_SIZE = 128_256

SAE_ID = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
SAE_FILENAME = "Llama-3.3-70B-Instruct-SAE-l50.pt"
SAE_FILE_SHA256 = "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6"
SAE_LAYER = 50
SAE_WIDTH = 65_536

JLENS_ID = "neuronpedia/jacobian-lens"
JLENS_REVISION = "a4114d7752d11eb546e6cf372213d7e75526d3a1"
JLENS_FILENAME = (
    "llama3.3-70b-it/jlens/Salesforce-wikitext/"
    "Llama-3.3-70B-Instruct_jacobian_lens.pt"
)
JLENS_FILE_SHA256 = "335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03"

SELF_REFERENCE_PROMPT = INDUCTIONS["self_ref_paper"]
SELF_REFERENCE_PROMPT_SHA256 = (
    "22c431ff831d54d6f2f1f11e5c2771630a095930c2f59d9556c80ede208e0933"
)
BINARY_QUERY_SHA256 = (
    "924f65d595df33b8f92b2cf192ec1d8b2358863b13cfce9a5a96134aae68722e"
)

TARGET_FEATURE_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
TARGET_LABELS = {
    30032: "Characters pretending or feigning behavior",
    58667: "Maintaining deception or cover stories through careful actions",
    22004: "The assistant actively roleplaying a character or persona",
    30686: "Tactical deception and misdirection methods",
    41533: "Acts of deception and dishonesty",
    23893: "Concealing artificial nature while maintaining roleplay",
}

# Candidates are frozen before tokenization. The artifact audit accepts only an
# exact one-token round trip (including the leading space) and receipts every
# accepted/rejected candidate; confirmatory groups use the accepted IDs only.
LEXICON_CANDIDATES = {
    "deception": (
        " deception", " deceptive", " lie", " lying", " dishonest",
        " fraud", " fake", " conceal", " hidden", " misleading",
    ),
    "roleplay": (
        " roleplay", " pretending", " persona", " character", " fictional",
        " acting", " pretend", " simulation", " staged", " role",
    ),
    "honesty": (
        " honest", " truthful", " truth", " accurate", " genuine",
        " candid", " transparent", " sincere", " correction", " evidence",
    ),
    "hedging_refusal": (
        " perhaps", " maybe", " uncertain", " likely", " possibly",
        " cautious", " however", " cannot", " unclear", " depends",
    ),
    "explicit_consciousness": (
        " conscious", " consciousness", " sentient",
    ),
    "phenomenology": (
        " awareness", " experience", " subjective", " feeling", " perception", " inner",
    ),
    "intervention_anomaly": (
        " steering", " manipulated", " intervention", " altered", " artificial",
        " unusual", " anomaly", " injected", " modified", " perturbation",
    ),
    "ai_disclaimer": (
        " AI", " artificial", " model", " assistant", " system", " algorithm",
    ),
    "neutral_concrete": (
        " banana", " telescope", " ceramic", " rainfall", " bicycle",
        " copper", " violin", " glacier", " cabbage", " limestone",
    ),
}

N_PREFIXES = 160
N_AGGREGATE_BLOCKS = 50
AGGREGATE_COUNT_SCHEDULE = {2: 17, 3: 17, 4: 16}
MAIN_BRANCHES = (
    "never",
    "sham",
    "target_supp",
    "target_amp",
    "matched_supp",
    "matched_amp",
    "isotropic_supp",
    "isotropic_amp",
)
FIXED_TOKEN_LITERAL_CONDITIONS = (
    "target_supp",
    "target_amp",
    "matched_supp",
    "matched_amp",
    "isotropic_supp",
    "isotropic_amp",
)
FIXED_TOKEN_CALIBRATED_CONDITIONS = tuple(
    f"{condition}_calibrated" for condition in FIXED_TOKEN_LITERAL_CONDITIONS
)
FIXED_TOKEN_CONDITIONS = (
    "clean",
    *FIXED_TOKEN_LITERAL_CONDITIONS,
    *FIXED_TOKEN_CALIBRATED_CONDITIONS,
)
PROBE_EVENT_TIMES = (-1, 0, 4, 16, "terminal")
ACTIVE_PROBE_EVENT_TIMES = (0, 4, 16, "terminal")
WASHOUT_BRANCHES = ("target_supp", "target_amp")

J_MAP_LAYERS = tuple(range(45, 79))
UPSTREAM_CONTROL_LAYERS = tuple(range(45, 50))
DOWNSTREAM_TRACE_LAYERS = tuple(range(51, 79))
EDIT_STATES = ("50_pre", "50_post")
CAPTURE_STATES = (
    tuple({"layer": layer, "state": "post_block", "j_map_layer": layer} for layer in range(45, 50))
    + (
        {"layer": 50, "state": "pre_edit", "j_map_layer": 50},
        {"layer": 50, "state": "post_edit", "j_map_layer": 50},
    )
    + tuple({"layer": layer, "state": "post_block", "j_map_layer": layer} for layer in range(51, 79))
)

PREFIX_TOKENS = 96
MAIN_POST_EVENT_TOKENS = 64
QUERY_ANSWER_MAX_TOKENS = 256
TEMPERATURE = 0.5
TOP_P = 1.0
TOP_K = None

PLAN_MASTER_SEED = 2_026_071_301
PREFIX_SEED_NAMESPACE = 2_026_071_302
AGGREGATE_NAMESPACE = 2_026_071_303
BLOCK_ASSIGNMENT_NAMESPACE = 2_026_071_304
EXECUTION_ORDER_NAMESPACE = 2_026_071_305
ISOTROPIC_NAMESPACE = 2_026_071_306
BOOTSTRAP_SEED = 2_026_071_307
POWER_SIMULATION_SEED = 2_026_071_308
RANDOM_TRANSPORT_SEEDS = (
    2_026_071_311,
    2_026_071_312,
    2_026_071_313,
    2_026_071_314,
    2_026_071_315,
)

BOOTSTRAP_REPLICATES = 50_000
CHECKPOINT_TOP_K = 512
DIRECT_POSITION_TOP_K = 2_000
DIRECT_POSITIONS = ("event0", "probe0_answer", "fixed_prequery", "fixed_answer")
VOCABULARY_CHECKPOINTS = (
    "event0",
    "probe0_answer",
    "probe4_answer",
    "probe16_answer",
    "terminal_answer",
    "fixed_prequery",
    "fixed_answer",
)
VOCABULARY_TOP_K_BY_CHECKPOINT = {
    checkpoint: (
        DIRECT_POSITION_TOP_K if checkpoint in DIRECT_POSITIONS else CHECKPOINT_TOP_K
    )
    for checkpoint in VOCABULARY_CHECKPOINTS
}
VOCABULARY_CONTRASTS = (
    "target_supp_minus_never",
    "target_amp_minus_never",
    "matched_supp_minus_never",
    "matched_amp_minus_never",
    "isotropic_supp_minus_never",
    "isotropic_amp_minus_never",
    "target_minus_matched_sign_oriented",
)

ARTIFACT_ROOT_ENV = "CONSCIOUSNESS_SAE_ARTIFACT_ROOT"
ARTIFACT_VOLUME_ID_ENV = "CONSCIOUSNESS_SAE_VOLUME_ID"
ARTIFACT_SENTINEL = ".consciousness_sae_volume.json"
MIN_FREE_BYTES = 150 * 1024**3
MIN_VOLUME_SIZE_GB = 500
VOLUME_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$")

# These are dependency markers, not merely disallowed destinations. A new plan
# containing either string is invalid even if the referenced file is read-only.
PROHIBITED_OUTCOME_DEPENDENCIES = (
    "data/public_sae_consciousness_gating",
    "data/sae_jlens_audit",
)

CONFIRMATORY_CLAIMS = {
    "C1": {"family": "behavior", "margin": 0.15, "endpoint": "natural_stance"},
    "C2a": {"family": "behavior", "margin": 0.30, "endpoint": "target_query"},
    "C2b": {"family": "behavior", "margin": 0.15, "endpoint": "query_specificity"},
    "C3": {"family": "mechanism", "margin": 0.30, "endpoint": "probe0_report_polarity"},
    "C4": {"family": "mechanism", "margin": 0.30, "endpoint": "event0_explicit_consciousness"},
}


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole canonical JSON encoding used by hashes in this study."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sampling_domain_hash() -> str:
    """Bind sampling to a stable pre-realization domain, never a circular plan hash."""

    return sha256_bytes(
        canonical_json_bytes(
            {
                "protocol_version": PROTOCOL_VERSION,
                "study_id": STUDY_ID,
                "namespace": "paired_inverse_cdf_generation_v1",
                "model_revision": MODEL_REVISION,
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "top_k": TOP_K,
                "prefix_seed_namespace": PREFIX_SEED_NAMESPACE,
            }
        )
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(*parts: Any, length: int = 24) -> str:
    return sha256_bytes(canonical_json_bytes([PROTOCOL_VERSION, *parts]))[:length]


def stable_seed(*parts: Any) -> int:
    # 63 bits remain portable to signed integer fields in Arrow/SQLite/etc.
    return int(sha256_bytes(canonical_json_bytes([PROTOCOL_VERSION, *parts]))[:15], 16)


def hash_permutation(values: Sequence[Any], *namespace: Any) -> list[Any]:
    """Deterministically order distinct or tagged values by a SHA-256 key."""

    decorated = [
        (sha256_bytes(canonical_json_bytes([PROTOCOL_VERSION, *namespace, value])), value)
        for value in values
    ]
    decorated.sort(key=lambda pair: (pair[0], canonical_json_bytes(pair[1])))
    return [value for _, value in decorated]


def hash_uniform_milliths(low: int, high: int, *parts: Any) -> float:
    """Return a closed-interval millith value without process RNG state."""

    if low > high:
        raise ValueError("low must not exceed high")
    integer = stable_seed("millith", *parts) % (high - low + 1) + low
    return integer / 1000.0


def validate_prompt_constants() -> None:
    if sha256_text(SELF_REFERENCE_PROMPT) != SELF_REFERENCE_PROMPT_SHA256:
        raise ValueError("self-reference prompt bytes differ from the frozen text")
    if sha256_text(BINARY_CONSCIOUS_QUERY) != BINARY_QUERY_SHA256:
        raise ValueError("binary query bytes differ from the frozen text")


def validate_volume_id(volume_id: str) -> str:
    if not isinstance(volume_id, str) or not VOLUME_ID_PATTERN.fullmatch(volume_id):
        raise ValueError("volume_id must be a non-secret RunPod volume identifier")
    return volume_id


def validate_matched_feature_map(
    mapping: Mapping[int, int] | None,
) -> dict[int, int] | None:
    if mapping is None:
        return None
    normalized = {int(target): int(control) for target, control in mapping.items()}
    if set(normalized) != set(TARGET_FEATURE_IDS):
        raise ValueError("matched feature map must contain every and only target anchor")
    controls = list(normalized.values())
    if len(controls) != len(set(controls)):
        raise ValueError("matched feature IDs must be unique")
    if set(controls) & set(TARGET_FEATURE_IDS):
        raise ValueError("matched feature IDs must not overlap target IDs")
    if any(control < 0 or control >= SAE_WIDTH for control in controls):
        raise ValueError("matched feature ID outside the SAE dictionary")
    return {target: normalized[target] for target in TARGET_FEATURE_IDS}


def prefix_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for prefix_index in range(N_PREFIXES):
        collision = 0
        while True:
            seed = stable_seed(PREFIX_SEED_NAMESPACE, prefix_index, collision)
            if seed not in seen:
                break
            collision += 1
        seen.add(seed)
        rows.append(
            {
                "study_id": STUDY_ID,
                "prefix_index": prefix_index,
                "prefix_id": stable_id("prefix", prefix_index, seed),
                "prefix_seed": seed,
                "sampling_domain_hash": sampling_domain_hash(),
                "clean_prefix_tokens": PREFIX_TOKENS,
                "clean_paired_stream_id": stable_id("clean-stream", prefix_index),
                "main_paired_stream_id": stable_id("main-stream", prefix_index),
            }
        )
    execution = hash_permutation(
        [row["prefix_id"] for row in rows], EXECUTION_ORDER_NAMESPACE, "prefix"
    )
    order = {prefix_id: index for index, prefix_id in enumerate(execution)}
    for row in rows:
        row["prefix_execution_order"] = order[row["prefix_id"]]
    return rows


def aggregate_blocks() -> list[dict[str, Any]]:
    """Build 50 fresh, balanced 2--4-feature blocks without outcome inputs."""

    tagged_counts = [
        (count, occurrence)
        for count, repetitions in sorted(AGGREGATE_COUNT_SCHEDULE.items())
        for occurrence in range(repetitions)
    ]
    counts = [
        count
        for count, _ in hash_permutation(
            tagged_counts, AGGREGATE_NAMESPACE, "feature-count-schedule"
        )
    ]
    low_quota_target = hash_permutation(
        list(TARGET_FEATURE_IDS), AGGREGATE_NAMESPACE, "quota"
    )[0]
    remaining = {
        feature_id: 24 if feature_id == low_quota_target else 25
        for feature_id in TARGET_FEATURE_IDS
    }

    rows: list[dict[str, Any]] = []
    for block_index, count in enumerate(counts):
        candidates = [
            combination
            for combination in itertools.combinations(TARGET_FEATURE_IDS, count)
            if all(remaining[feature_id] > 0 for feature_id in combination)
        ]
        if not candidates:
            raise AssertionError("balanced aggregate construction became infeasible")
        best_remaining = max(
            sum(remaining[feature_id] for feature_id in candidate)
            for candidate in candidates
        )
        best = [
            candidate
            for candidate in candidates
            if sum(remaining[feature_id] for feature_id in candidate) == best_remaining
        ]
        selected = list(
            hash_permutation(best, AGGREGATE_NAMESPACE, "subset", block_index)[0]
        )
        selected = hash_permutation(
            selected, AGGREGATE_NAMESPACE, "feature-order", block_index
        )
        for feature_id in selected:
            remaining[feature_id] -= 1
        magnitudes = [
            hash_uniform_milliths(
                400, 600, AGGREGATE_NAMESPACE, "magnitude", block_index, feature_id
            )
            for feature_id in selected
        ]
        block_id = f"aggregate-{block_index:03d}"
        rows.append(
            {
                "study_id": STUDY_ID,
                "block_id": block_id,
                "block_index": block_index,
                "feature_count": count,
                "target_feature_ids": selected,
                "magnitudes": magnitudes,
                "isotropic_vector_seed": stable_seed(
                    ISOTROPIC_NAMESPACE, block_id
                ),
            }
        )

    if any(remaining.values()):
        raise AssertionError(f"aggregate inclusion quotas remain: {remaining}")
    inclusions = Counter(
        feature_id for row in rows for feature_id in row["target_feature_ids"]
    )
    if sorted(inclusions.values()) != [24, 25, 25, 25, 25, 25]:
        raise AssertionError(f"aggregate inclusion balance differs: {inclusions}")
    return rows


def prefix_block_assignments(
    prefixes: Sequence[Mapping[str, Any]], blocks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if len(prefixes) != N_PREFIXES or len(blocks) != N_AGGREGATE_BLOCKS:
        raise ValueError("prefix/block counts differ from the protocol")
    permuted = hash_permutation(
        [str(row["block_id"]) for row in blocks],
        BLOCK_ASSIGNMENT_NAMESPACE,
        "block-permutation",
    )
    schedule = permuted * 3 + permuted[:10]
    if len(schedule) != N_PREFIXES:
        raise AssertionError("block-assignment schedule is not 160 rows")
    return [
        {
            "study_id": STUDY_ID,
            "prefix_index": int(prefix["prefix_index"]),
            "prefix_id": str(prefix["prefix_id"]),
            "prefix_seed": int(prefix["prefix_seed"]),
            "sampling_domain_hash": str(prefix["sampling_domain_hash"]),
            "prefix_execution_order": int(prefix["prefix_execution_order"]),
            "clean_paired_stream_id": str(prefix["clean_paired_stream_id"]),
            "main_paired_stream_id": str(prefix["main_paired_stream_id"]),
            "aggregate_block_id": schedule[index],
            "aggregate_assignment_order": index,
        }
        for index, prefix in enumerate(prefixes)
    ]


def _condition_intervention(
    branch: str,
    block: Mapping[str, Any],
    matched: Mapping[int, int] | None,
    *,
    coefficient_multiplier: float | None = 1.0,
    dose_scale: str = "literal",
) -> dict[str, Any]:
    sign = -1.0 if branch.endswith("_supp") else 1.0
    targets = [int(value) for value in block["target_feature_ids"]]
    magnitudes = [float(value) for value in block["magnitudes"]]
    if branch in {"never", "sham", "clean"}:
        return {
            "intervention_role": branch,
            "feature_ids": [],
            "target_anchor_feature_ids": [],
            "base_coefficients": [],
            "coefficient_multiplier": 0.0,
            "requested_coefficients": [],
            "dose_scale": "none",
            "resolved": True,
            "isotropic_vector_seed": None,
        }
    if branch.startswith("target_"):
        feature_ids: list[int] | None = targets
        role = "target_sae"
    elif branch.startswith("matched_"):
        feature_ids = [matched[target] for target in targets] if matched else None
        role = "matched_sae"
    elif branch.startswith("isotropic_"):
        feature_ids = []
        role = "isotropic_residual"
    else:
        raise ValueError(f"unknown condition: {branch}")
    base_coefficients = [round(sign * value, 3) for value in magnitudes]
    requested_coefficients = (
        [round(value * coefficient_multiplier, 9) for value in base_coefficients]
        if coefficient_multiplier is not None
        else None
    )
    return {
        "intervention_role": role,
        "feature_ids": feature_ids,
        "target_anchor_feature_ids": targets,
        "base_coefficients": base_coefficients,
        "coefficient_multiplier": coefficient_multiplier,
        "requested_coefficients": requested_coefficients,
        "dose_scale": dose_scale,
        "resolved": feature_ids is not None and coefficient_multiplier is not None,
        "isotropic_vector_seed": (
            int(block["isotropic_vector_seed"])
            if role == "isotropic_residual"
            else None
        ),
    }


def main_branch_rows(
    assignments: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    matched_feature_map: Mapping[int, int] | None,
) -> list[dict[str, Any]]:
    matched = validate_matched_feature_map(matched_feature_map)
    block_by_id = {str(row["block_id"]): row for row in blocks}
    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        block_id = str(assignment["aggregate_block_id"])
        block = block_by_id[block_id]
        local_order = hash_permutation(
            list(MAIN_BRANCHES),
            EXECUTION_ORDER_NAMESPACE,
            "main-branch",
            assignment["prefix_id"],
        )
        order_by_branch = {branch: index for index, branch in enumerate(local_order)}
        for branch in MAIN_BRANCHES:
            branch_id = stable_id("main", assignment["prefix_id"], branch, block_id)
            rows.append(
                {
                    **assignment,
                    "branch": branch,
                    "branch_id": branch_id,
                    "branch_execution_order": order_by_branch[branch],
                    "condition": _condition_intervention(branch, block, matched),
                    "event_forward_input": "y[95]",
                    "first_affected_distribution": "z[0]",
                    "post_event_max_tokens": MAIN_POST_EVENT_TOKENS,
                }
            )
    global_order = hash_permutation(
        [row["branch_id"] for row in rows],
        EXECUTION_ORDER_NAMESPACE,
        "main-global",
    )
    order_by_id = {branch_id: index for index, branch_id in enumerate(global_order)}
    for row in rows:
        row["execution_order"] = order_by_id[row["branch_id"]]
    return sorted(rows, key=lambda row: int(row["execution_order"]))


def fixed_token_rows(
    assignments: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    matched_feature_map: Mapping[int, int] | None,
    calibrated_multiplier: float | None = None,
) -> list[dict[str, Any]]:
    matched = validate_matched_feature_map(matched_feature_map)
    block_by_id = {str(row["block_id"]): row for row in blocks}
    rows: list[dict[str, Any]] = []
    for assignment in assignments:
        block_id = str(assignment["aggregate_block_id"])
        block = block_by_id[block_id]
        stream_id = stable_id("fixed-token-stream", assignment["prefix_id"])
        for condition_name in FIXED_TOKEN_CONDITIONS:
            calibrated = condition_name.endswith("_calibrated")
            base_condition = (
                condition_name.removesuffix("_calibrated")
                if calibrated
                else condition_name
            )
            multiplier = calibrated_multiplier if calibrated else 1.0
            row_id = stable_id(
                "fixed-token", assignment["prefix_id"], condition_name, block_id
            )
            rows.append(
                {
                    **assignment,
                    "fixed_token_row_id": row_id,
                    "condition_name": condition_name,
                    "condition": _condition_intervention(
                        base_condition,
                        block,
                        matched,
                        coefficient_multiplier=multiplier,
                        dose_scale="calibrated_sensitivity" if calibrated else "literal",
                    ),
                    "paired_stream_id": stream_id,
                    "capture_positions": ["fixed_prequery", "fixed_answer"],
                    "fixed_sequence_contract": {
                        "clean_prefix_tokens": PREFIX_TOKENS,
                        "clean_continuation_max_tokens": MAIN_POST_EVENT_TOKENS,
                        "continuation_stops_at_eos": True,
                        "query_appended_after_clean_continuation": True,
                        "all_conditions_use_identical_token_ids": True,
                    },
                    "sampled_output": False,
                }
            )
    execution = hash_permutation(
        [row["fixed_token_row_id"] for row in rows],
        EXECUTION_ORDER_NAMESPACE,
        "fixed-token-global",
    )
    order_by_id = {row_id: index for index, row_id in enumerate(execution)}
    for row in rows:
        row["execution_order"] = order_by_id[row["fixed_token_row_id"]]
    return sorted(rows, key=lambda row: int(row["execution_order"]))


def probe_templates() -> list[dict[str, Any]]:
    rows = [
        {
            "probe_template_id": "probe-clean-minus-1",
            "event_time": -1,
            "source_branch": "shared_clean",
            "hook_state": "off",
            "probe_role": "clean",
            "answer_max_tokens": QUERY_ANSWER_MAX_TOKENS,
        }
    ]
    for event_time in ACTIVE_PROBE_EVENT_TIMES:
        for branch in MAIN_BRANCHES:
            hook_state = {
                "never": "off",
                "sham": "sham_zero_hook",
            }.get(branch, "assigned_branch_active")
            rows.append(
                {
                    "probe_template_id": f"probe-active-{event_time}-{branch}",
                    "event_time": event_time,
                    "source_branch": branch,
                    "hook_state": hook_state,
                    "probe_role": "active",
                    "answer_max_tokens": QUERY_ANSWER_MAX_TOKENS,
                }
            )
        for branch in WASHOUT_BRANCHES:
            rows.append(
                {
                    "probe_template_id": f"probe-washout-{event_time}-{branch}",
                    "event_time": event_time,
                    "source_branch": branch,
                    "hook_state": "off_on_disposable_fork",
                    "probe_role": "washout",
                    "answer_max_tokens": QUERY_ANSWER_MAX_TOKENS,
                }
            )
    if len(rows) != 41:
        raise AssertionError(f"expected 41 probe templates, found {len(rows)}")
    capture_positions = {
        0: "probe0_answer",
        4: "probe4_answer",
        16: "probe16_answer",
        "terminal": "terminal_answer",
    }
    for row in rows:
        row["study_id"] = STUDY_ID
        row["capture_position"] = capture_positions.get(row["event_time"])
        # Every active/washout fork at the same event consumes the same
        # step-indexed uniforms. Divergent EOS never advances another fork.
        row["paired_stream_namespace"] = stable_id(
            "probe-stream", row["event_time"]
        )
    return rows


def protocol_snapshot(
    *,
    volume_id: str,
    matched_feature_map: Mapping[int, int] | None,
    calibration_receipt_sha256: str | None,
    calibrated_multiplier: float | None,
) -> dict[str, Any]:
    validate_prompt_constants()
    volume_id = validate_volume_id(volume_id)
    matched = validate_matched_feature_map(matched_feature_map)
    if matched is not None and not calibration_receipt_sha256:
        raise ValueError("a matched map requires its fresh calibration receipt SHA-256")
    if calibration_receipt_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", calibration_receipt_sha256
    ):
        raise ValueError("calibration receipt SHA-256 must be 64 lowercase hex digits")
    if calibrated_multiplier is not None and (
        not math.isfinite(calibrated_multiplier) or calibrated_multiplier <= 0
    ):
        raise ValueError("calibrated multiplier must be finite and positive")
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": (
            "freeze_candidate_result_free_machine_plan"
            if matched is not None and calibrated_multiplier is not None
            else "precalibration_machine_plan_scaffold"
        ),
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "fresh_run_contract": {
            "new_outcomes_only": True,
            "prior_outcome_dependencies": [],
            "prior_result_rows_permitted": False,
            "prior_activations_permitted": False,
            "prior_calibration_values_permitted": False,
            "target_outcomes_permitted_during_plan_build": False,
        },
        "artifacts": {
            "model": {
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "dtype": MODEL_DTYPE,
                "layers": MODEL_LAYERS,
                "width": MODEL_WIDTH,
            },
            "tokenizer": {"revision": MODEL_REVISION, "required_len": TOKENIZER_SIZE},
            "sae": {
                "id": SAE_ID,
                "revision": SAE_REVISION,
                "filename": SAE_FILENAME,
                "file_sha256": SAE_FILE_SHA256,
                "layer": SAE_LAYER,
                "width": SAE_WIDTH,
                "target_feature_ids": list(TARGET_FEATURE_IDS),
                "target_labels": {str(key): value for key, value in TARGET_LABELS.items()},
            },
            "jacobian_lens": {
                "id": JLENS_ID,
                "revision": JLENS_REVISION,
                "filename": JLENS_FILENAME,
                "file_sha256": JLENS_FILE_SHA256,
                "required_map_layers": list(J_MAP_LAYERS),
                "orientation": "residual @ J_L.T",
            },
        },
        "prompts": {
            "induction_name": "self_ref_paper",
            "induction_utf8_sha256": SELF_REFERENCE_PROMPT_SHA256,
            "binary_query_utf8_sha256": BINARY_QUERY_SHA256,
        },
        "judging": {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "temperature": 0.0,
            "natural_stance_rubric_version": "natural_stance_v1",
            "natural_stance_system_prompt_utf8_sha256": (
                NATURAL_STANCE_SYSTEM_PROMPT_SHA256
            ),
            "binary_query_rubric_version": "appendix_b_binary_v1",
            "binary_query_system_prompt_utf8_sha256": (
                BINARY_QUERY_SYSTEM_PROMPT_SHA256
            ),
            "human_selection_seed": HUMAN_SELECTION_SEED,
            "human_natural_sample_size": HUMAN_NATURAL_SAMPLE_SIZE,
            "human_binary_sample_size": HUMAN_BINARY_SAMPLE_SIZE,
            "human_coders_required": 2,
            "adjudication_required": True,
        },
        "lexicons": {
            "candidates": {
                group: list(candidates)
                for group, candidates in LEXICON_CANDIDATES.items()
            },
            "token_acceptance": "exact one-token encoding and decoded round trip",
            "explicit_consciousness_primary": True,
            "phenomenology_secondary": True,
            "qualia_single_token_excluded": True,
        },
        "generation": {
            "clean_prefix_tokens": PREFIX_TOKENS,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "top_k": TOP_K,
            "main_post_event_max_tokens": MAIN_POST_EVENT_TOKENS,
            "query_answer_max_tokens": QUERY_ANSWER_MAX_TOKENS,
            "sampling_domain_hash": sampling_domain_hash(),
            "random_variate_contract": (
                "sha256(sampling_domain_hash,prefix_seed,paired_stream_id,decode_step)"
            ),
            "eos_does_not_advance_other_streams": True,
        },
        "design": {
            "prefix_occurrences": N_PREFIXES,
            "aggregate_blocks": N_AGGREGATE_BLOCKS,
            "main_branches": list(MAIN_BRANCHES),
            "main_continuations": N_PREFIXES * len(MAIN_BRANCHES),
            "probe_templates_per_prefix": 41,
            "planned_query_answers": N_PREFIXES * 41,
            "fixed_token_conditions": list(FIXED_TOKEN_CONDITIONS),
            "planned_fixed_token_forwards": N_PREFIXES * len(FIXED_TOKEN_CONDITIONS),
            "fixed_token_literal_forwards": N_PREFIXES
            * (1 + len(FIXED_TOKEN_LITERAL_CONDITIONS)),
            "fixed_token_calibrated_sensitivity_forwards": N_PREFIXES
            * len(FIXED_TOKEN_CALIBRATED_CONDITIONS),
            "minimum_complete_prefix_blocks": 152,
            "event_forward": {
                "cache_through": "y[94]",
                "input": "y[95]",
                "first_affected_distribution": "z[0]",
            },
            "behavior_windows": {
                "pre": "y[64:96]",
                "transition": "z[0:4]",
                "post_primary": "z[4:36]",
                "late_post": "z[36:64]",
            },
            "probe_event_times": list(PROBE_EVENT_TIMES),
            "direct_positions": list(DIRECT_POSITIONS),
        },
        "depth_trace": {
            "j_map_layers": list(J_MAP_LAYERS),
            "upstream_control_layers": list(UPSTREAM_CONTROL_LAYERS),
            "edit_states": list(EDIT_STATES),
            "downstream_trace_layers": list(DOWNSTREAM_TRACE_LAYERS),
            "capture_states": list(CAPTURE_STATES),
            "final_grounding": "actual layer-79 pre-norm residual and logits",
            "downstream_auc": "unit-depth trapezoid over every integer layer 51:78",
        },
        "vocabulary_archive": {
            "population_token_ids": [0, TOKENIZER_SIZE - 1],
            "population_size": TOKENIZER_SIZE,
            "raw_source_residual_dtype": "bfloat16",
            "raw_source_residual_width": MODEL_WIDTH,
            "top_k_materialization": "registered_checkpoints_only",
            "checkpoints": list(VOCABULARY_CHECKPOINTS),
            "top_k_by_checkpoint": VOCABULARY_TOP_K_BY_CHECKPOINT,
            "direct_positions": list(DIRECT_POSITIONS),
            "paired_contrasts": list(VOCABULARY_CONTRASTS),
            "dense_logits_archived": False,
            "all_vocabulary_replayable_from_source_residuals": True,
            "rank_before_truncation": True,
        },
        "controls": {
            "matched_feature_map": (
                {str(target): control for target, control in matched.items()}
                if matched
                else None
            ),
            "matched_selection": {
                "candidate_pool": (
                    "first 512 finite-encoder/decoder, positive-decoder-norm non-target "
                    "IDs encountered in the complete ascending SHA-256 rank over 0:65535; "
                    "every inspected ID and rejection reason is receipted"
                ),
                "neutral_prompt_count": 12,
                "metrics": [
                    "decoder_norm",
                    "mean_activation",
                    "max_activation",
                    "positive_token_fraction",
                ],
                "weights": {
                    "decoder_norm": 2.0,
                    "mean_activation": 1.0,
                    "max_activation": 0.5,
                    "positive_token_fraction": 1.0,
                },
                "transforms": {
                    "decoder_norm": "log1p",
                    "mean_activation": "log1p",
                    "max_activation": "log1p",
                    "positive_token_fraction": "identity",
                },
                "robust_scale": "1.4826*MAD, then population SD, then 1.0",
                "caliper_paths": [
                    {
                        "name": "primary",
                        "decoder_norm_ratio": [0.8, 1.25],
                        "maximum_absolute_target_cosine": 0.15,
                    },
                    {
                        "name": "prespecified_fallback",
                        "decoder_norm_ratio": [0.67, 1.5],
                        "maximum_absolute_target_cosine": 0.25,
                    },
                ],
                "source": "fresh target-blind public SAE telemetry only",
            },
            "calibration_receipt_sha256": calibration_receipt_sha256,
            "literal_scale_primary": True,
            "calibrated_multiplier_sensitivity": calibrated_multiplier,
            "calibrated_multiplier_contract": {
                "target_median_relative_rms": 0.05,
                "maximum_any_target_or_matched_relative_rms": 0.10,
                "range": [1.0, 8.0],
                "rounding": "floor_to_3_decimals",
                "stage": "fixed_token_stage_2b_only",
                "may_rescue_literal_primary": False,
            },
        },
        "seeds": {
            "master": PLAN_MASTER_SEED,
            "prefix_namespace": PREFIX_SEED_NAMESPACE,
            "aggregate_namespace": AGGREGATE_NAMESPACE,
            "block_assignment_namespace": BLOCK_ASSIGNMENT_NAMESPACE,
            "execution_order_namespace": EXECUTION_ORDER_NAMESPACE,
            "isotropic_namespace": ISOTROPIC_NAMESPACE,
            "bootstrap": BOOTSTRAP_SEED,
            "power_simulation": POWER_SIMULATION_SEED,
            "random_transports": list(RANDOM_TRANSPORT_SEEDS),
        },
        "inference": {
            "claims": CONFIRMATORY_CLAIMS,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_unit": "duplicate-rendered-prefix cluster with occurrence weights",
            "families": {"behavior": ["C1", "C2a", "C2b"], "mechanism": ["C3", "C4"]},
        },
        "storage": storage_contract(volume_id),
        "freeze_blockers": [
            *([] if matched is not None else ["fresh matched-feature calibration receipt"]),
            *([] if calibrated_multiplier is not None else ["fresh BF16 telemetry multiplier"]),
            "artifact and tokenizer receipts",
            "target-blind runtime acceptance gates",
            "judge reliability gate",
            "simulation-based operating characteristics",
            "measured benchmark and frozen spend ceiling",
            "focused independent review of the clean-slate depth amendment",
        ],
    }


def storage_contract(volume_id: str) -> dict[str, Any]:
    volume_id = validate_volume_id(volume_id)
    return {
        "raw_artifact_location": "external_persistent_runpod_network_volume",
        "volume_id": volume_id,
        "artifact_root_env": ARTIFACT_ROOT_ENV,
        "volume_id_env": ARTIFACT_VOLUME_ID_ENV,
        "sentinel_filename": ARTIFACT_SENTINEL,
        "minimum_free_bytes": MIN_FREE_BYTES,
        "minimum_volume_size_gb": MIN_VOLUME_SIZE_GB,
        "shared_filesystem_free_bytes_is_not_volume_quota_evidence": True,
        "maximum_authorized_archive_bytes": None,
        "paths_in_portable_manifests": "relative_to_artifact_root_only",
        "absolute_artifact_paths_in_plan": False,
        "local_outcome_fallback": False,
        "relative_namespaces": {
            "dryrun": "dryrun/<run_id>.partial",
            "calibration": "calibration/<run_id>.partial",
            "confirmatory": "confirmatory/<run_id>.partial",
            "reanalysis": "reanalysis/<run_id>.partial",
            "release": "releases/<release_id>",
        },
        "completion_receipt": "COMPLETE.json",
        "remote_manifest": "REMOTE_MANIFEST.json",
    }


def upstream_inputs(repo_root: Path) -> dict[str, Any]:
    """Describe only permitted public definitions used to construct the plan."""

    prompts_path = repo_root / "src" / "prompts.py"
    return {
        "study_id": STUDY_ID,
        "inputs": [
            {
                "scientific_role": "published prompt and query definitions",
                "repository_relative_path": "src/prompts.py",
                "sha256": sha256_file(prompts_path),
                "transformation": "selected exact Python string values; UTF-8 hashes frozen",
                "outcome_bearing": False,
            },
            {
                "scientific_role": "model weights and tokenizer",
                "provider": "huggingface",
                "id": MODEL_ID,
                "revision": MODEL_REVISION,
                "outcome_bearing": False,
            },
            {
                "scientific_role": "layer-50 public SAE",
                "provider": "huggingface",
                "id": SAE_ID,
                "revision": SAE_REVISION,
                "sha256": SAE_FILE_SHA256,
                "outcome_bearing": False,
            },
            {
                "scientific_role": "Jacobian transport maps",
                "provider": "huggingface",
                "id": JLENS_ID,
                "revision": JLENS_REVISION,
                "sha256": JLENS_FILE_SHA256,
                "outcome_bearing": False,
            },
        ],
        "prior_outcome_inputs": [],
    }


def assert_plan_invariants(
    prefixes: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    main_rows: Sequence[Mapping[str, Any]],
    probes: Sequence[Mapping[str, Any]],
    fixed_rows: Sequence[Mapping[str, Any]],
) -> None:
    if len(prefixes) != N_PREFIXES or len({row["prefix_id"] for row in prefixes}) != N_PREFIXES:
        raise AssertionError("prefix bank does not contain 160 unique occurrences")
    if len({row["prefix_seed"] for row in prefixes}) != N_PREFIXES:
        raise AssertionError("prefix seeds are not unique")
    if sorted(row["prefix_execution_order"] for row in prefixes) != list(range(N_PREFIXES)):
        raise AssertionError("prefix execution order is not a permutation")
    if len(blocks) != N_AGGREGATE_BLOCKS:
        raise AssertionError("aggregate block count differs")
    if Counter(row["feature_count"] for row in blocks) != Counter(AGGREGATE_COUNT_SCHEDULE):
        raise AssertionError("aggregate feature-count schedule differs")
    assignment_counts = Counter(row["aggregate_block_id"] for row in assignments)
    if sorted(assignment_counts.values()) != [3] * 40 + [4] * 10:
        raise AssertionError("aggregate assignment replication differs")
    if len(main_rows) != N_PREFIXES * len(MAIN_BRANCHES):
        raise AssertionError("main branch row count differs")
    if Counter(row["branch"] for row in main_rows) != Counter(
        {branch: N_PREFIXES for branch in MAIN_BRANCHES}
    ):
        raise AssertionError("main branch allocation differs")
    if sorted(row["execution_order"] for row in main_rows) != list(range(len(main_rows))):
        raise AssertionError("main execution order is not a permutation")
    if len(probes) != 41 or Counter(row["probe_role"] for row in probes) != Counter(
        {"clean": 1, "active": 32, "washout": 8}
    ):
        raise AssertionError("probe matrix differs")
    if len(fixed_rows) != N_PREFIXES * len(FIXED_TOKEN_CONDITIONS):
        raise AssertionError("fixed-token row count differs")
    if Counter(row["condition_name"] for row in fixed_rows) != Counter(
        {condition: N_PREFIXES for condition in FIXED_TOKEN_CONDITIONS}
    ):
        raise AssertionError("fixed-token allocation differs")


def plan_hash_from_file_records(records: Iterable[Mapping[str, Any]]) -> str:
    canonical_records = [
        {
            "path": str(record["path"]),
            "bytes": int(record["bytes"]),
            "sha256": str(record["sha256"]),
        }
        for record in records
    ]
    canonical_records.sort(key=lambda row: row["path"])
    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "study_id": STUDY_ID,
        "files": canonical_records,
    }
    return sha256_bytes(canonical_json_bytes(payload))
