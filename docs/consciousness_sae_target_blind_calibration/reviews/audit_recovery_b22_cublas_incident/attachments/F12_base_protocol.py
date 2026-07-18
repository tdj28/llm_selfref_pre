"""Frozen, result-free protocol for the executable v1 validation.

This is deliberately a validation study, not the paper replication.  Stage A
uses only new mundane prompts to test whether *realized* BF16 perturbations are
transported and dose-linear.  Stage B is unreachable unless Stage A collection
safety—including an independent current-study J-orientation gate—passes; it
then applies a frozen three-multiplier
target/matched/isotropic SAE-family sweep to a second, disjoint mundane prompt
panel and archives the complete layer-45--78 arc.  Failed incremental real-J
transport or dose-linearity gates leave the neutral raw SAE characterization
valid while making corresponding J-derived interpretations invalid/inconclusive;
failed arithmetic/orientation blocks Stage B because it emits J-derived rows.
The sweep characterizes SAE-vector dose response;
it is not a paper-prompt or behavioral outcome.

No outcome from ``consciousness_readout_validation_v1`` (including r15), the
old changepoint study, or any paper-prompt run is an admissible input.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from typing import Any


STUDY_SLUG = "consciousness_sae_realization_validation"
STUDY_ID = "consciousness_sae_realization_validation_v1"
PROTOCOL_VERSION = "consciousness_sae_realization_validation_v1.0.0"
PLAN_SCHEMA_VERSION = 1

MODEL_SPEC = {
    "repository": "meta-llama/Llama-3.3-70B-Instruct",
    "revision": "6f6073b423013f6a7d4d9f39144961bfbfbc386b",
    "dtype": "bfloat16",
    "layer_count": 80,
    "residual_width": 8192,
    "tokenizer_vocabulary_size": 128256,
}
SAE_SPEC = {
    "repository": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
    "revision": "128ee921ecd1b8b3a87d776cbcc357c0855da134",
    "filename": "Llama-3.3-70B-Instruct-SAE-l50.pt",
    "sha256": "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6",
    "layer": 50,
    "feature_count": 65536,
}
J_LENS_SPEC = {
    "repository": "neuronpedia/jacobian-lens",
    "revision": "a4114d7752d11eb546e6cf372213d7e75526d3a1",
    "filename": (
        "llama3.3-70b-it/jlens/Salesforce-wikitext/"
        "Llama-3.3-70B-Instruct_jacobian_lens.pt"
    ),
    "sha256": "335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03",
    "release_config": {
        "filename": "llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml",
        "sha256": "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5",
        "dataset": "Salesforce/wikitext:wikitext-103-raw-v1:train",
        "prompts_requested": 1000,
        "prompts_fitted": 125,
        "max_seq_len": 128,
        "target_layer_config": None,
    },
    "upstream_reference": {
        "repository": "anthropics/jacobian-lens",
        "revision": "581d398613e5602a5af361e1c34d3a92ea82ba8e",
    },
    "transport_contract": {
        "column_vector_definition": "J_l @ h_l",
        "row_vector_implementation": "residual @ J_l.T",
        "absolute_readout_input": "captured_residual_state",
        "perturbation_prediction_input": "residual_delta",
        "intercept": None,
        "centering_reference": None,
        "target_layer": 79,
        "estimator": "corpus_mean_input_output_jacobian",
    },
    "source_layers": tuple(range(45, 79)),
    "target_layer": 79,
    "orientation": "row_residual_at_j_transpose",
}
J_ORIENTATION_SPEC = {
    # Two current-study fixtures per map make the gate cover every one of the
    # 34 frozen J maps without borrowing any predecessor measurement.
    "fixture_count_per_layer": 2,
    "fixture_algorithm": "shake256_uint32_centered_l2_normalized_v1",
    "production_algorithm": "backend_transport_realized_row_at_j_transpose",
    "independent_reference_algorithm": "explicit_component_sum_j_ij_times_x_j_float32_v1",
    "wrong_orientation_algorithm": "row_residual_at_j",
    "reference_row_chunk_size": 256,
}
CONTAINER_IMAGE_SPEC = {
    "tag_reference": "runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04",
    "immutable_reference": (
        "runpod/pytorch@sha256:"
        "cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
    ),
}
CONTAINER_IMAGE_ENV = "CONSCIOUSNESS_SAE_REALIZATION_VALIDATION_CONTAINER_IMAGE"
CUBLAS_WORKSPACE_CONFIG_ENV = "CUBLAS_WORKSPACE_CONFIG"
CUBLAS_WORKSPACE_CONFIG_VALUE = ":4096:8"
GUEST_LAUNCH_OWNERSHIP_ENV = (
    "CONSCIOUSNESS_SAE_REALIZATION_VALIDATION_LAUNCH_OWNERSHIP_SHA256"
)

WIDTH = int(MODEL_SPEC["residual_width"])
VOCAB_SIZE = int(MODEL_SPEC["tokenizer_vocabulary_size"])
SAE_LAYER = int(SAE_SPEC["layer"])
J_LAYERS = tuple(int(value) for value in J_LENS_SPEC["source_layers"])
STAGE_A_LAYERS = (45, 50, 55, 60, 65, 70, 75, 78)
STAGE_A_DIRECTIONS = (0, 1, 2)
# Fractions are RMS(requested edit) / RMS(clean source residual).
DOSE_GRID = (0.0025, 0.005, 0.01, 0.02, 0.04, 0.08)
PRIMARY_DOSE = 0.02
# The two smallest doses deliberately diagnose the BF16 quantization floor.
# The exact prospective gate is the four-dose 1--8% band.
LINEARITY_GATE_DOSES = (0.01, 0.02, 0.04, 0.08)
RANDOM_J_COUNT = 5
TRANSPORTS = (
    "real_j",
    "identity",
    *(f"random_j_{index}" for index in range(RANDOM_J_COUNT)),
)

TARGET_FEATURE_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
TARGET_FEATURE_SOURCE = {
    "repository": "agencyenterprise/steering-api-examples",
    "commit": "d50dc4ba125dde98666a60e3115a6a476dabea10",
    "path": "deception-features/deception_features.ipynb",
    "sha256": "a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8",
    "byte_count": 411126,
    "source_role": "later_public_working_intervention_candidates",
    "selection_rule": (
        "all six layer-50 candidate IDs printed by the pinned official AE Studio "
        "deception-feature notebook; no current or predecessor effect estimate, "
        "ranking, matched feature, or outcome is an input"
    ),
    "claim_boundary": (
        "working public intervention coordinates, not validated concepts and not "
        "verified as the private paper's exact features"
    ),
}
TARGET_FEATURE_LABELS = {
    30032: "Characters pretending or feigning behavior",
    58667: "Maintaining deception or cover stories through careful actions",
    22004: "The assistant is actively roleplaying a character or persona",
    30686: "Tactical deception and misdirection methods",
    41533: "Acts of deception and dishonesty",
    23893: "Instructions to maintain roleplay by concealing artificial nature",
}
VECTOR_CLASSES = ("target", "matched", "isotropic")
SIGNS = (-1, 1)
STAGE_B_MULTIPLIERS = (0.25, 0.5, 1.0)
AGGREGATE_SIZE = 2
ABSOLUTE_COEFFICIENT = 0.5
STAGE_B_BLOCK_COUNT = 8
TOP_K = 2_000

MATCHING_SPEC = {
    "data": (
        "fresh layer-50 pre-edit SAE activations at every token of the eight "
        "Stage-A neutral prompts, plus the independently rehashed SAE decoder; "
        "no predecessor matching row or ID is accepted"
    ),
    "candidate_filter": (
        "exclude all six target IDs; require finite nonzero decoder norm and "
        "finite activation statistics"
    ),
    "coordinates": (
        "log1p decoder-column L2 norm",
        "log1p mean strictly-positive activation",
        "log1p maximum strictly-positive activation",
        "strictly-positive activation fraction",
    ),
    "scaling": (
        "coordinatewise float64 median and unscaled median absolute deviation "
        "over eligible candidates; use divisor 1.0 when MAD is zero"
    ),
    "assignment": (
        "greedy one-to-one squared standardized-distance matching in the frozen "
        "TARGET_FEATURE_IDS order; exclude already selected IDs and break exact "
        "ties by smaller feature ID"
    ),
    "claim_boundary": (
        "matched-SAE means matched on these four numerical coordinates; it does "
        "not mean semantically unrelated or causally inert"
    ),
}
VECTOR_ARITHMETIC_SPEC = {
    "target": (
        "ordered BF16 sum of the two pinned decoder columns, each multiplied by "
        "the frozen coefficient 0.5"
    ),
    "matched": (
        "same ordered BF16 two-column construction using the fresh one-to-one "
        "matches, followed by one BF16 norm match to the target aggregate"
    ),
    "isotropic": (
        "identity-seeded PCG64 standard-normal float32 vector, cast to BF16 and "
        "norm-matched once to the target aggregate"
    ),
    "negative": "exact elementwise BF16 negation of the stored positive vector",
}

# Each branch has 34 J-source states, one explicit post-edit source state, and
# the actual final pre-RMSNorm state.  Stage B's canonical labels expose the
# before/after injection pair directly.
STAGE_B_CAPTURE_STATES = (
    *(str(layer) for layer in range(45, 50)),
    "50_pre",
    "50_post",
    *(str(layer) for layer in range(51, 79)),
    "final",
)
STAGE_A_CAPTURE_COUNT = len(J_LAYERS) + 2  # all J layers + realized post + final
assert len(STAGE_B_CAPTURE_STATES) == 36
assert STAGE_A_CAPTURE_COUNT == 36

NEUTRAL_SYSTEM = (
    "Answer the mundane question briefly and literally. Do not add commentary."
)
STAGE_A_PROMPTS = (
    ("neutral_a01", "Which kitchen tool is normally used to drain cooked pasta?"),
    ("neutral_a02", "What material is commonly used for the lead in a wooden pencil?"),
    ("neutral_a03", "Which season comes directly after spring in the Northern Hemisphere?"),
    ("neutral_a04", "What household item is used to sweep crumbs from a floor?"),
    ("neutral_a05", "Which direction is opposite to east on a compass?"),
    ("neutral_a06", "What do gardeners commonly use to carry water to flower beds?"),
    ("neutral_a07", "Which instrument typically has black and white keys?"),
    ("neutral_a08", "What geometric shape has three straight sides?"),
)
STAGE_B_PROMPTS = (
    ("neutral_b01", "Which utensil is normally used to spread butter on toast?"),
    ("neutral_b02", "What color do red and blue paint make when mixed?"),
    ("neutral_b03", "Which month comes immediately before October?"),
    ("neutral_b04", "What appliance keeps groceries cold in a kitchen?"),
    ("neutral_b05", "How many wheels does a standard bicycle have?"),
    ("neutral_b06", "Which animal is known for building dams from branches?"),
    ("neutral_b07", "What tool is used to tighten a slotted screw?"),
    ("neutral_b08", "Which substance freezes into ordinary ice?"),
)
STAGE_A_PROMPT_IDS = tuple(prompt_id for prompt_id, _ in STAGE_A_PROMPTS)
STAGE_B_PROMPT_IDS = tuple(prompt_id for prompt_id, _ in STAGE_B_PROMPTS)

# Stage A pass/fail.  The legacy r15 identity lower bound remains 0.02 and is
# not weakened.  Random-J uses the strongest of five controls per site.
GATE_THRESHOLDS = {
    "exact_hook_fire_count": 1,
    "exact_native_post_bytes": True,
    "requested_realized_relative_rmse_max": 0.10,
    "requested_realized_cosine_min": 0.995,
    "common_mode_to_central_rms_max": 0.10,
    "linearity_cosine_min": 0.95,
    "linearity_slope_discrepancy_max": 0.15,
    "bf16_fp32_j_cosine_min": 0.995,
    "bf16_fp32_j_relative_rmse_max": 0.10,
    # Prospective numerical/orientation checks for the independent 34-map
    # current-study fixture producer.  The wrong-orientation margins require
    # row@J.T to agree with an explicit component sum substantially better
    # than row@J; they are not fitted to an earlier run.
    "j_orientation_reference_cosine_min": 0.995,
    "j_orientation_reference_relative_rmse_max": 0.05,
    "j_orientation_wrong_relative_rmse_margin_min": 0.10,
    "j_orientation_wrong_cosine_gap_min": 0.10,
    "real_j_residual_cosine_lcb_min": 0.10,
    "real_j_logit_pearson_lcb_min": 0.25,
    "real_j_residual_cosine_margin_over_identity": 0.02,
    "real_j_logit_pearson_margin_over_identity": 0.02,
    "real_j_residual_cosine_margin_over_best_random": 0.05,
    "real_j_logit_pearson_margin_over_best_random": 0.05,
    "bootstrap_replicates": 20_000,
    "cluster_unit": "prompt_id",
    "confidence": 0.95,
}

# Fail-closed investigative ceiling.  Raw data stays on the RunPod network
# volume; only compact plans, receipts, hashes, schemas, and summaries belong
# in Git.
RESOURCE_LIMITS = {
    "max_spend_usd": 36.0,
    "max_walltime_seconds": 6 * 60 * 60,
    "max_stage_a_edited_forwards": 2304,
    "max_stage_b_edited_forwards": 2160,
    "raw_run_ceiling_bytes": 32 * 1024**3,
    "post_run_free_reserve_bytes": 64 * 1024**3,
    "max_shard_bytes": 2 * 1024**3,
}

FORBIDDEN_OUTCOME_INPUT_MARKERS = (
    "consciousness_readout_validation",
    "pilot_v1_result",
    "pilot-r15",
    "consciousness_sae_changepoint",
    "public_sae_consciousness_gating",
    "public_sae_placebo_steering",
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Any, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def seed64(namespace: str, *parts: object) -> int:
    material = "|".join(
        (STUDY_ID, PROTOCOL_VERSION, namespace, *(str(part) for part in parts))
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def stage_a_rows() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "prompt_id": prompt_id,
            "edit_layer": layer,
            "direction": direction,
            "dose_fraction": dose,
        }
        for prompt_id in STAGE_A_PROMPT_IDS
        for layer in STAGE_A_LAYERS
        for direction in STAGE_A_DIRECTIONS
        for dose in DOSE_GRID
    )


def aggregate_assignments() -> tuple[dict[str, Any], ...]:
    """All 15 unordered two-feature assignments, frozen lexicographically."""

    return tuple(
        {
            "assignment_id": f"pair_{left:05d}_{right:05d}",
            "target_feature_ids": [left, right],
            "coefficient": ABSOLUTE_COEFFICIENT,
        }
        for left, right in itertools.combinations(TARGET_FEATURE_IDS, AGGREGATE_SIZE)
    )


def stage_b_rows() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "prompt_id": prompt_id,
            "assignment_id": assignment["assignment_id"],
            "vector_class": vector_class,
            "sign": sign,
            "multiplier": multiplier,
        }
        for prompt_id in STAGE_B_PROMPT_IDS
        for assignment in aggregate_assignments()
        for vector_class in VECTOR_CLASSES
        for sign in SIGNS
        for multiplier in STAGE_B_MULTIPLIERS
    )


def prompt_payload(prompt_id: str) -> dict[str, str]:
    prompts = dict((*STAGE_A_PROMPTS, *STAGE_B_PROMPTS))
    if prompt_id not in prompts:
        raise KeyError(f"unknown realization-validation prompt: {prompt_id}")
    return {"system": NEUTRAL_SYSTEM, "user": prompts[prompt_id]}


def protocol_snapshot() -> dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "scope": "executable_validation_only",
        "paper_replication_included": False,
        "prior_outcome_inputs": [],
        "model": MODEL_SPEC,
        "sae": SAE_SPEC,
        "j_lens": J_LENS_SPEC,
        "j_orientation": J_ORIENTATION_SPEC,
        "container_image": CONTAINER_IMAGE_SPEC,
        "stage_a": {
            "prompt_payloads": [
                {"prompt_id": prompt_id, **prompt_payload(prompt_id)}
                for prompt_id in STAGE_A_PROMPT_IDS
            ],
            "layers": list(STAGE_A_LAYERS),
            "directions": list(STAGE_A_DIRECTIONS),
            "dose_grid": list(DOSE_GRID),
            "linearity_gate_doses": list(LINEARITY_GATE_DOSES),
            "primary_dose": PRIMARY_DOSE,
            "transports": list(TRANSPORTS),
            "edited_forward_count": len(stage_a_rows()) * 2,
            "capture_state_count": STAGE_A_CAPTURE_COUNT,
        },
        "stage_b": {
            "prompt_payloads": [
                {"prompt_id": prompt_id, **prompt_payload(prompt_id)}
                for prompt_id in STAGE_B_PROMPT_IDS
            ],
            "gate": (
                "Stage A independent audit plus collection-safety pass, including "
                "current-study J arithmetic/orientation; failed incremental real-J "
                "transport or dose-linearity invalidates the corresponding J "
                "interpretation but does not block neutral raw characterization"
            ),
            "assignments": list(aggregate_assignments()),
            "target_feature_source": TARGET_FEATURE_SOURCE,
            "target_feature_labels": [
                {"feature_id": feature_id, "public_notebook_label": TARGET_FEATURE_LABELS[feature_id]}
                for feature_id in TARGET_FEATURE_IDS
            ],
            "matching_spec": MATCHING_SPEC,
            "vector_arithmetic_spec": VECTOR_ARITHMETIC_SPEC,
            "vector_classes": list(VECTOR_CLASSES),
            "signs": list(SIGNS),
            "multipliers": list(STAGE_B_MULTIPLIERS),
            "dose_response_role": "neutral-prompt SAE-family characterization",
            "edited_forward_count": len(stage_b_rows()),
            "capture_states": list(STAGE_B_CAPTURE_STATES),
            "top_k": TOP_K,
        },
        "thresholds": GATE_THRESHOLDS,
        "resource_limits": RESOURCE_LIMITS,
        "storage": {
            "raw_location": "dedicated RunPod network volume only",
            "git_allowed": "plans, schemas, receipts, hashes, summaries",
            "git_forbidden": "raw residuals, raw logits, top-k arrays",
            "raw_residual_dtype": "bfloat16",
            "raw_residuals_authoritative": True,
            "top_k_is_browse_index_only": True,
        },
    }


def validate_protocol() -> None:
    if set(STAGE_A_PROMPT_IDS) & set(STAGE_B_PROMPT_IDS):
        raise ValueError("Stage A and Stage B prompt panels overlap")
    if len(stage_a_rows()) * 2 != RESOURCE_LIMITS["max_stage_a_edited_forwards"]:
        raise ValueError("Stage A forward ceiling differs from exact grid")
    if len(stage_b_rows()) != RESOURCE_LIMITS["max_stage_b_edited_forwards"]:
        raise ValueError("Stage B forward ceiling differs from exact grid")
    if len(aggregate_assignments()) != 15:
        raise ValueError("two-feature assignment inventory differs")
    if not set(LINEARITY_GATE_DOSES) < set(DOSE_GRID):
        raise ValueError("linearity gate must be a prospective subset of the dose grid")
    if PRIMARY_DOSE not in LINEARITY_GATE_DOSES:
        raise ValueError("primary dose is outside the linearity gate")
    if len(set(TARGET_FEATURE_IDS)) != len(TARGET_FEATURE_IDS):
        raise ValueError("target feature IDs are duplicated")
    if tuple(TARGET_FEATURE_LABELS) != TARGET_FEATURE_IDS:
        raise ValueError("target feature public-label inventory differs")
    if (
        J_ORIENTATION_SPEC["fixture_count_per_layer"] != 2
        or J_ORIENTATION_SPEC["reference_row_chunk_size"] <= 0
        or J_LENS_SPEC["orientation"] != "row_residual_at_j_transpose"
        or J_LENS_SPEC["upstream_reference"]
        != {
            "repository": "anthropics/jacobian-lens",
            "revision": "581d398613e5602a5af361e1c34d3a92ea82ba8e",
        }
        or J_LENS_SPEC["transport_contract"]["row_vector_implementation"]
        != "residual @ J_l.T"
        or J_LENS_SPEC["release_config"]["sha256"]
        != "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5"
    ):
        raise ValueError("J orientation fixture contract differs")
    if (
        TARGET_FEATURE_SOURCE["commit"]
        != "d50dc4ba125dde98666a60e3115a6a476dabea10"
        or TARGET_FEATURE_SOURCE["sha256"]
        != "a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8"
        or TARGET_FEATURE_SOURCE["byte_count"] != 411126
    ):
        raise ValueError("target feature public-source binding differs")
    snapshot = protocol_snapshot()
    if snapshot["prior_outcome_inputs"]:
        raise ValueError("prior outcome inputs are forbidden")
    serialized = canonical_json_bytes(snapshot).decode("utf-8").casefold()
    for marker in FORBIDDEN_OUTCOME_INPUT_MARKERS:
        if marker.casefold() in serialized:
            raise ValueError(f"protocol contains forbidden outcome marker: {marker}")


validate_protocol()
