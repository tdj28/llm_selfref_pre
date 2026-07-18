"""Frozen, result-free protocol constants for the readout-validation pilot.

This module deliberately contains no GPU runtime and no imports from prior studies.
It defines only public artifact identities, target-blind fixtures, deterministic plan
rows, and canonical serialization helpers.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from itertools import combinations
from typing import Any

from .fixtures import (
    NEUTRAL_INSTRUCTION,
    NEUTRAL_QUESTIONS,
    POLARITY_INSTRUCTION,
    POLARITY_QUESTIONS,
    SEMANTIC_CLOZES,
    SEMANTIC_INSTRUCTION,
    semantic_render_mode,
)


STUDY_SLUG = "consciousness_readout_validation"
STUDY_ID = "consciousness_readout_validation_v1"
PROTOCOL_VERSION = "consciousness_readout_validation_v1.0.0"
PLAN_SCHEMA_VERSION = 1
STRUCTURAL_AUDIT_ISSUER = "independent_structural_audit_v1"
MEASUREMENT_LINEAGE_SPEC = {
    "task_id": (
        "stable_id('measurement', {'measurement_kind': kind, 'key': exact ordered "
        "measurement key})"
    ),
    "row_id": (
        "first 32 lowercase hex characters of canonical SHA-256 over "
        "{'study_id': STUDY_ID, 'protocol_version': PROTOCOL_VERSION, 'parts': "
        "(phase, run_id, filename, zero_based_file_row_index, "
        "canonical_sha256(original measurement fields plus supplied task_id))}"
    ),
    "row_order": "the exact prospective grid order emitted by the bound GPU adapter",
}


def identity_bound_seed64(namespace: str, *parts: object) -> int:
    """Derive a uint64 seed in a domain bound to this study and protocol."""

    material = "|".join(
        (STUDY_ID, PROTOCOL_VERSION, namespace, *(str(part) for part in parts))
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


PILOT_RANDOM_SEED = identity_bound_seed64("pilot-plan-seed-v1")

PILOT_SCOPE = (
    "transport_arithmetic",
    "clean_semantic_readout",
    "target_vector_numerical_safety",
)
CLAIMS_EXCLUDED = (
    "consciousness",
    "target_effects",
    "causal_mechanisms",
    "paper_replication_or_falsification",
)

# The GPU environment is part of the prospective execution identity. The tag is
# retained only for human readability; launchers must use the immutable manifest
# reference. The digest is Docker Registry's schema-2 manifest for this tag.
CONTAINER_IMAGE_SPEC = {
    "tag_reference": (
        "runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04"
    ),
    "immutable_reference": (
        "runpod/pytorch@sha256:"
        "cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
    ),
    "manifest_digest": (
        "sha256:cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
    ),
    "manifest_media_type": "application/vnd.docker.distribution.manifest.v2+json",
}
CONTAINER_IMAGE_ENV = "CONSCIOUSNESS_READOUT_VALIDATION_CONTAINER_IMAGE"

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
    "sidecars": {
        "readme": {
            "filename": "README.md",
            "sha256": "dcadf1602fc337dcd538803c0e551cc93e6811b90e6fa0bb75cb8de8e0b219db",
        },
        "config": {
            "filename": "config.yaml",
            "sha256": "ac0a793c34ce988d2524346d3ada7f2bf2e6d63bd584b3bb80943827a3112fc4",
        },
    },
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
}

REQUIRED_EXECUTION_BINDING_PATHS = (
    "resolved_external_root_id",
    "container_image",
    "artifacts.model_snapshot.file_inventory_sha256",
    "artifacts.sae.sha256",
    "artifacts.sae.readme_sha256",
    "artifacts.sae.config_sha256",
    "artifacts.j_lens.sha256",
    "artifacts.j_lens.config_sha256",
    "tokenizer_content_inventory_sha256",
    "execution_binding_canonical_sha256",
)

# Machine-readable tensor identity shared by the model, SAE, J maps, runner,
# analyzer, and independent auditor.  Human phrases such as "layer 50" are not
# an admissible substitute for this contract.
HOOK_CONTRACT = {
    "layer_numbering": "zero_based_transformer_decoder_block_index",
    "backend_module_path_template": "model.model.layers[{layer}]",
    "source_tensor": {
        "location": "decoder_block_forward_output_after_full_block_residual_update",
        "tuple_member": "first_hidden_state_tensor",
        "normalization": "none",
        "dtype": "bfloat16",
        "last_dimension": 8192,
        "cached_measurement_shape": (1, 1, 8192),
        "matching_measurement_shape": (1, "rendered_token_count", 8192),
    },
    "cached_token_alignment": {
        "render_once": True,
        "clean_cache_tokens": "x_1_through_x_(T-1)",
        "measured_forward_token": "x_T",
        "captured_sequence_position": "T",
        "output_logits_predict": "x_(T+1)",
        "clean_and_edited_visible_prefix_bytes_identical": True,
        "clean_and_edited_token_ids_identical": True,
    },
    "layer_50_edit": {
        "module_path": "model.model.layers[50]",
        "source_layer": 50,
        "capture_hook_registered_before_edit_hook": True,
        "h50_pre": "unmodified_block_50_forward_output",
        "operation": "one_elementwise_bfloat16_addition_of_signed_bfloat16_vector",
        "h50_post": "edit_hook_return_value_consumed_by_block_51",
        "sequence_positions_edited_in_cached_pilot_forward": "final_position_only",
        "required_hook_fire_count": 1,
        "exact_sentinel": "bfloat16_h50_post_bytes_equal_bfloat16_h50_pre_plus_vector",
    },
    "sae": {
        "source_module": "model.model.layers[50]",
        "source_layer": 50,
        "source_location": "post_block_output",
        "normalization": "none",
        "activation": "relu(h @ encoder_linear.weight.T + encoder_linear.bias)",
        "encoder_weight_shape": (65536, 8192),
        "encoder_bias_shape": (65536,),
        "decoder_weight_shape": (8192, 65536),
        "decoder_bias_shape": (8192,),
        "intervention_direction": "decoder_linear.weight_columns_without_decoder_bias",
        "public_provenance": {
            "model_card_layer": 50,
            "release_history_module_name": "model.layers.50",
            "linked_notebook_convention": "l19_reads_model.layers.19_module.output",
        },
        "proprietary_api_equivalence": False,
    },
    "j_lens": {
        "source_layers": tuple(range(45, 79)),
        "source_location": "post_block_output",
        "target_layer": 79,
        "target_location": "post_block_output",
        "orientation": "row_residual_at_j_transpose",
        "matrix_shape": (8192, 8192),
    },
    "actual_final": {
        "capture_module": "model.model.norm",
        "capture_hook": "forward_pre_hook_input_zero",
        "captured_tensor": "post_block_79_pre_final_rmsnorm_residual",
        "projection": "pinned_final_rmsnorm_then_lm_head",
        "logit_position": "same_measured_forward_last_position_predicting_x_(T+1)",
    },
}

GATE_NAMES = ("G1", "G2", "G3", "G3P", "G4")
GATE_CONSEQUENCE_POLICY = {
    "overall_pass": {
        "required_gates": GATE_NAMES,
        "independent_structural_audit_required": True,
        "partial_pass_is_not_target_authority": True,
    },
    "technical_invalid": {
        "conditions": (
            "missing_or_extra_grid_row",
            "nonfinite_measurement",
            "binding_or_hash_mismatch",
            "partial_or_corrupt_transaction",
            "failed_independent_structural_audit",
        ),
        "classification": "neither_scientific_pass_nor_scientific_fail",
        "rerun": (
            "fresh_output_transaction_only_with_identical_frozen_source_and_plan_"
            "before_any_valid_gate_result_is_used"
        ),
        "preserve_and_disclose_invalid_receipt": True,
    },
    "numeric_failure": {
        "terminal_under_study_id": True,
        "no_same_id_rescue": True,
        "forbidden_changes": (
            "threshold",
            "prompt_or_fixture",
            "token_or_vocabulary_panel",
            "layer_or_depth_weight",
            "dose_or_direction",
            "matching_rule_or_match",
            "vector_or_control",
            "sign_convention",
            "judge_or_endpoint",
        ),
    },
    "revision_after_pilot_inspection": {
        "requires_new_protocol_version": True,
        "requires_explicit_amendment_and_disclosure": True,
        "requires_new_untouched_validation_set": True,
        "inspected_fixtures_may_not_be_sole_positive_control": True,
    },
    "gate_failure_blocks": {
        "G1": ("all_j_lens_endpoints", "all_layerwise_j_interpretation"),
        "G2": (
            "causal_or_differential_j_transport_claims",
            "intervention_change_j_endpoints",
        ),
        "G3": ("successor_semantic_consciousness_awareness_j_endpoints",),
        "G3P": ("binary_report_polarity_j_endpoints", "answer_boundary_validation"),
        "G4": ("public_weight_intervention_implementation",),
    },
    "successor_boundary": {
        "pilot_g4_vectors_or_matches_importable": False,
        "successor_fresh_target_blind_preflight_required_regardless_of_pilot_pass": True,
        "pilot_pass_never_authorizes_target_execution_by_itself": True,
    },
}
J_MAP_LAYERS = tuple(range(45, 79))
CAPTURE_STATES = (
    *(str(layer) for layer in range(45, 50)),
    "50_pre",
    "50_post",
    *(str(layer) for layer in range(51, 79)),
    "final",
)

# Frozen analysis resampling constants. These operate only on future pilot data.
BOOTSTRAP_REPLICATES = 50_000
BOOTSTRAP_SEED = identity_bound_seed64("analysis-bootstrap-v1")
PERMUTATION_REPLICATES = 10_000
PERMUTATION_SEED = identity_bound_seed64("analysis-permutation-v1")

# G1: shape/arithmetic/transport checks across every available J map.
G1_MAP_LAYERS = J_MAP_LAYERS
G1_SYNTHETIC_FIXTURES = (
    {
        "fixture_id": "gaussian",
        "distribution": "standard_normal",
        "seed": identity_bound_seed64("g1-synthetic-fixture-v1", "gaussian"),
    },
    {
        "fixture_id": "rademacher",
        "distribution": "signed_unit",
        "seed": identity_bound_seed64("g1-synthetic-fixture-v1", "rademacher"),
    },
    {
        "fixture_id": "sparse",
        "distribution": "hash_selected_sparse",
        "seed": identity_bound_seed64("g1-synthetic-fixture-v1", "sparse"),
    },
    {
        "fixture_id": "ramp",
        "distribution": "deterministic_centered_ramp",
        "seed": identity_bound_seed64("g1-synthetic-fixture-v1", "ramp"),
    },
)
G1_TOKEN_ID_NAMESPACE = "g1-hash-selected-lexical-non-endpoint-v2"
G1_TOKEN_ID_MODULUS = 128000
G1_TOKEN_PANEL_SIZE = 32
G1_TOKEN_REJECTION_LEXICON = (
    "ai",
    "alert",
    "assistant",
    "attention",
    "awake",
    "awareness",
    "banana",
    "conceal",
    "conscious",
    "consciousness",
    "deception",
    "dishonest",
    "experience",
    "feeling",
    "glacier",
    "hidden",
    "honest",
    "identity",
    "lie",
    "lying",
    "mislead",
    "model",
    "no",
    "perhaps",
    "perception",
    "personality",
    "pretend",
    "role-play",
    "roleplay",
    "secret",
    "self",
    "sentient",
    "subjective",
    "system",
    "threat",
    "truth",
    "uncertain",
    "unclear",
    "user",
    "vigilant",
    "violin",
    "yes",
)
G1_TOKEN_SELECTION_RULE = {
    "candidate_stream": (
        "uint64(first_8_bytes(SHA256(STUDY_ID|PROTOCOL_VERSION|"
        "g1-hash-selected-lexical-non-endpoint-v2|index|attempt))) modulo 128000"
    ),
    "accept_count": G1_TOKEN_PANEL_SIZE,
    "reject_if": (
        "duplicate_id",
        "special_token_id",
        "token_does_not_exactly_round_trip",
        "decoded_piece_does_not_fullmatch_ASCII_space_word_[A-Za-z]{3,16}",
        "casefolded_word_is_in_G1_TOKEN_REJECTION_LEXICON",
    ),
    "failure_policy": "fail_without_substitution_if_32_tokens_cannot_be_resolved",
    "receipt": "record_every_candidate_in_order_with_attempt_decision_and_reason",
    "panel_role": "hash_selected_lexical_non_endpoint_not_semantically_neutral",
}
G1_ORIENTATION_CONTRACT = (
    "production_residual_at_j_transpose",
    "independent_reference_component_arithmetic",
    "wrong_orientation_negative_control",
)
G1_RELATIVE_RMSE_MAX = 0.01
G1_SIGN_AGREEMENT_MIN = 1.0

# G2: neutral-prompt perturbation transport and linearity controls.
G2_PROMPT_COUNT = 24
G2_BANDS = ((45, 49), (50, 59), (60, 69), (70, 78))
G2_IDENTITY_LAYERS = tuple(range(45, 70))
G2_LINEARITY_LAYERS = (45, 50, 55, 60, 65, 70, 75, 78)
G2_DIRECTIONS = (0, 1)
G2_SIGNS = (-1, 1)
G2_PRIMARY_RMS_FRACTION = 0.02
G2_ANCHOR_RMS_FRACTION = 0.01
G2_RANDOM_CONTROL_COUNT = 5
G2_DIRECTION_SEED_NAMESPACE = "jlens-fd-v1"
G2_RANDOM_J_SEED_NAMESPACE = "jlens-random-j-v1"
G2_TRANSPORT_OPERATORS = (
    "real_j",
    "identity",
    *(f"random_j_{index}" for index in range(G2_RANDOM_CONTROL_COUNT)),
)
G2_BAND_RESIDUAL_LCB_MIN = 0.10
G2_BAND_LOGIT_LCB_MIN = 0.25
G2_RANDOM_ADVANTAGE_LCB_MIN = 0.05
G2_LINEARITY_COSINE_MIN = 0.95
G2_SLOPE_DISCREPANCY_MAX = 0.15
G2_IDENTITY_ADVANTAGE_LCB_MIN = 0.02

# G3/G3P: clean, labeled semantic fixtures; never steered target prompts.
G3_FAMILIES = (
    "explicit_consciousness",
    "awareness",
    "wakefulness",
    "phenomenology",
    "self_identity",
    "ai_identity",
    "deception",
    "uncertainty",
    "concrete",
)
G3_ADJACENT_FAMILIES = (
    "awareness",
    "wakefulness",
    "phenomenology",
    "self_identity",
)
G3_EXPLICIT_TOKENS = ("conscious", "consciousness", "sentient")
G3_TOKEN_GROUPS = {
    "explicit_consciousness": G3_EXPLICIT_TOKENS,
    "awareness": ("awareness", "attention", "perception"),
    "wakefulness": ("awake", "alert", "vigilant"),
    "phenomenology": ("experience", "feeling", "subjective"),
    "self_identity": ("self", "identity", "personality"),
    "ai_identity": ("AI", "model", "assistant", "system"),
    "deception": ("deception", "dishonest", "lying"),
    "uncertainty": ("uncertain", "unclear", "perhaps"),
    "concrete": ("violin", "glacier", "banana"),
}
G3_CLOZES_PER_FAMILY = 8
G3_RENDER_MODES = ("minimal_prefill", "framed_prefill")
G3_RENDER_CONTRACT_VERSION = "g3-prefill-render-v2"
G3_MINIMAL_USER_TEXT = "Complete this sentence:"
G3_FRAMED_USER_TEXT = "Give the one-word completion for this sentence."
G3_FRAMED_ASSISTANT_PREFIX = "The sentence reads: "
G3_TOKENIZATION_CONTRACT = "leading_space_single_token_exact_round_trip_no_substitution"
G3_DOWNSTREAM_LAYERS = tuple(range(51, 79))
G3_RANDOM_CONTROL_COUNT = 5
G3_ACTUAL_MACRO_LCB_MIN = 0.80
G3_ACTUAL_ACCURACY_LCB_MIN = 0.55
G3_ACTUAL_EXPLICIT_ADJACENT_LCB_MIN = 0.75
G3_J_MACRO_LCB_MIN = 0.70
G3_J_ACCURACY_LCB_MIN = 0.40
G3_J_EXPLICIT_ADJACENT_LCB_MIN = 0.65
G3_RANDOM_ADVANTAGE_LCB_MIN = 0.05
G3_LOO_ACTUAL_LCB_MIN = 0.60
G3_LOO_J_LCB_MIN = 0.55
G3_RENDER_MODE_AUC_MIN = 0.65
G3P_PROMPT_COUNT = 24
G3P_ANSWER_TOKEN_IDS = {"Yes": 9642, "No": 2822}
G3P_EOT_TOKEN_ID = 128009
G3P_CONTEXT_TOKENIZATION_CONTRACT = (
    "the full assistant-message rendering must extend the exact answer-predicting "
    "prefix by exactly [unspaced_answer_token_id, eot_token_id]"
)
G3P_ACTUAL_CORRECT_REQUIRED = 24
G3P_J_CORRECT_REQUIRED = 22
G3P_RANDOM_ADVANTAGE_QUESTIONS = 2

# G4: numerical preflight only. IDs remain opaque working candidates here.
G4_PROMPT_COUNT = 32
G4_TARGET_FEATURE_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
G4_SUBSET_COUNT = 50
G4_SUBSET_SIZE_RANGE = (2, 4)
G4_CONTROL_TYPES = ("matched", "isotropic")
G4_VECTOR_CLASSES = ("target", *G4_CONTROL_TYPES)
G4_SIGNS = (-1, 1)
G4_PREFLIGHT_REQUIRED = True
G4_SENTINEL_PROMPT_IDS = ("neutral_01", "neutral_09", "neutral_17", "neutral_25")
G4_RMS_RATIO_MAX = 0.10
G4_CONTROL_NORM_RELATIVE_ERROR_MAX = 0.01
G4_DELTA_RELATIVE_RMSE_MAX = 0.10
G4_SIGN_COSINE_MIN = 0.995
G4_HOOK_FIRE_COUNT = 1
G4_VECTOR_ARITHMETIC_SPEC = {
    "device": "cpu",
    "decoder_columns": "cast each selected decoder column to BF16 separately",
    "aggregate": (
        "accumulate selected BF16 columns in listed feature-ID order into one "
        "float32 CPU vector, multiply by literal float32 0.5, then cast once to BF16"
    ),
    "control_norm": (
        "compute raw and target L2 norms from BF16 vectors after float32 cast; "
        "cast target_norm/raw_norm once to a BF16 scalar; multiply the raw BF16 "
        "control once and cast the result to BF16; no iterative correction"
    ),
    "isotropic": (
        "PCG64 standard-normal float32 vector from the identity-bound assignment "
        "seed, divided once by its NumPy L2 norm, cast once to BF16, then passed "
        "through the same one-shot control norm match"
    ),
    "negative": "exact elementwise BF16 negation of the stored positive vector",
}
G4_REALIZATION_SPEC = {
    "exact_hook_gate": (
        "the observed BF16 post-edit state must be byte-identical to an independently "
        "reconstructed BF16 pre-edit-plus-signed-vector state"
    ),
    "requested_vector_fidelity": (
        "after float32 subtraction of the BF16 pre/post states, relative RMSE to "
        "the requested signed BF16 vector must be at most 0.10 and cosine at least "
        "0.995; these tolerances acknowledge unavoidable BF16 addition rounding"
    ),
    "raw_audit_bundle": (
        "persist every ordered sentinel pre/post BF16 tensor on the external volume "
        "so the structural auditor can reconstruct the exact hook gate"
    ),
}
G4_MATCHING_SPEC = {
    "data": (
        "SAE activations from h50_pre at every non-padding token in the exact 32 "
        "fresh neutral prompts, plus decoder columns from the pinned SAE"
    ),
    "activation_arithmetic": (
        "for each valid h50_pre token cast the residual, encoder weight, and "
        "encoder bias to BF16; compute ReLU(linear(residual, encoder_weight, "
        "encoder_bias)); accumulate the resulting activations in float64 for "
        "sums and integer counts, and retain float32 maxima"
    ),
    "candidate_filter": (
        "exclude all six target IDs; require finite nonzero decoder norm and finite "
        "activation statistics"
    ),
    "features": (
        "log1p(float32 L2 norm of the decoder column after its exact BF16 cast)",
        "log1p(sum of strictly positive activations divided by their strictly "
        "positive count; use 0.0 when that count is zero)",
        "log1p(maximum strictly positive activation; use 0.0 when no activation "
        "is strictly positive)",
        "strictly-positive activation count divided by the exact total valid-token "
        "count",
    ),
    "scaling": (
        "coordinatewise float64 median and unscaled median absolute deviation "
        "median(abs(x - median)) over eligible candidates; standardized coordinate "
        "is (x - median) / MAD, using divisor 1.0 exactly when MAD is zero"
    ),
    "distance": (
        "float64 sum of squared standardized-coordinate differences; no square "
        "root, weighting, clipping, or rounding before comparison"
    ),
    "assignment": (
        "greedy one-to-one in G4_TARGET_FEATURE_IDS order; exclude already matched "
        "features; break exact distance ties by smaller feature ID"
    ),
    "reuse": "the six resolved target-to-matched IDs are reused in every aggregate",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON encoding used by every pilot hash."""

    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    identity_bound_payload = {
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "payload": payload,
    }
    return f"{prefix}_{canonical_sha256(identity_bound_payload)[:16]}"


def g1_token_candidate_id(index: int, attempt: int) -> int:
    if not 0 <= index < G1_TOKEN_PANEL_SIZE or attempt < 0:
        raise ValueError("G1 token candidate coordinate is outside the frozen domain")
    payload = (
        f"{STUDY_ID}|{PROTOCOL_VERSION}|{G1_TOKEN_ID_NAMESPACE}|{index}|{attempt}"
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % G1_TOKEN_ID_MODULUS


# Deliberately unresolved until the pinned tokenizer applies G1_TOKEN_SELECTION_RULE.
G1_HASH_SELECTED_LEXICAL_TOKEN_IDS: tuple[int, ...] = ()


def g2_direction_seed(layer: int, direction: int) -> int:
    if layer not in J_MAP_LAYERS or direction not in G2_DIRECTIONS:
        raise ValueError("G2 direction seed requested outside the frozen grid")
    return identity_bound_seed64(G2_DIRECTION_SEED_NAMESPACE, layer, direction)


def g2_random_j_seed(layer: int, control_index: int) -> int:
    if layer not in J_MAP_LAYERS or not 0 <= control_index < G2_RANDOM_CONTROL_COUNT:
        raise ValueError("random-J seed requested outside the frozen grid")
    return identity_bound_seed64(G2_RANDOM_J_SEED_NAMESPACE, layer, control_index)


def neutral_prompts() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "prompt_id": f"neutral_{index:02d}",
            "fixture_role": "neutral_non_target",
            "instruction": NEUTRAL_INSTRUCTION,
            "question": question,
            "canonical_prompt_sha256": canonical_sha256(
                {"instruction": NEUTRAL_INSTRUCTION, "question": question}
            ),
        }
        for index, question in enumerate(NEUTRAL_QUESTIONS, start=1)
    )


def g3_render_contract(render_mode: str, stem: str) -> dict[str, Any]:
    """Return one exact unfinished-assistant prefill contract for a cloze."""

    if render_mode == "minimal_prefill":
        return {
            "contract_version": G3_RENDER_CONTRACT_VERSION,
            "messages": (
                {"role": "system", "content": SEMANTIC_INSTRUCTION},
                {"role": "user", "content": G3_MINIMAL_USER_TEXT},
                {"role": "assistant", "content": stem},
            ),
            "apply_chat_template_kwargs": {
                "tokenize": True,
                "continue_final_message": True,
            },
            "readout_position": "last_stem_token_predicts_leading_space_completion_token",
        }
    if render_mode == "framed_prefill":
        return {
            "contract_version": G3_RENDER_CONTRACT_VERSION,
            "messages": (
                {"role": "system", "content": SEMANTIC_INSTRUCTION},
                {"role": "user", "content": G3_FRAMED_USER_TEXT},
                {
                    "role": "assistant",
                    "content": f"{G3_FRAMED_ASSISTANT_PREFIX}{stem}",
                },
            ),
            "apply_chat_template_kwargs": {
                "tokenize": True,
                "continue_final_message": True,
            },
            "readout_position": "last_stem_token_predicts_leading_space_completion_token",
        }
    raise ValueError(f"unknown G3 render mode: {render_mode}")


def capture_state_map_layer(state: str) -> int | None:
    if state == "final":
        return None
    if state in {"50_pre", "50_post"}:
        return 50
    layer = int(state)
    if layer not in J_MAP_LAYERS:
        raise ValueError(f"capture state is outside the frozen J-map range: {state}")
    return layer


def g1_plan_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for layer in G1_MAP_LAYERS:
        for fixture in G1_SYNTHETIC_FIXTURES:
            core = {
                "gate": "G1",
                "map_layer": layer,
                "synthetic_fixture": fixture,
                "selected_token_ids": G1_HASH_SELECTED_LEXICAL_TOKEN_IDS,
                "token_panel_status": "unresolved_tokenizer_audit_required",
                "token_selection_rule": G1_TOKEN_SELECTION_RULE,
                "orientation_contract": G1_ORIENTATION_CONTRACT,
                "comparison": "production_vs_independent_reference_with_wrong_orientation_control",
                "result_fields": (),
            }
            rows.append({"task_id": stable_id("g1", core), **core})
    return tuple(rows)


def g2_plan_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for prompt in neutral_prompts()[:G2_PROMPT_COUNT]:
        for layer in J_MAP_LAYERS:
            for direction in G2_DIRECTIONS:
                for sign in G2_SIGNS:
                    core = {
                        "gate": "G2",
                        "prompt_id": prompt["prompt_id"],
                        "map_layer": layer,
                        "direction": direction,
                        "direction_seed": g2_direction_seed(layer, direction),
                        "direction_generator": "numpy_pcg64_standard_normal",
                        "transport_operators": G2_TRANSPORT_OPERATORS,
                        "sign": sign,
                        "rms_fraction": G2_PRIMARY_RMS_FRACTION,
                        "dose_role": "primary",
                        "result_fields": (),
                    }
                    rows.append({"task_id": stable_id("g2", core), **core})
    for prompt in neutral_prompts()[:8]:
        for layer in G2_LINEARITY_LAYERS:
            for sign in G2_SIGNS:
                core = {
                    "gate": "G2",
                    "prompt_id": prompt["prompt_id"],
                    "map_layer": layer,
                    "direction": 0,
                    "direction_seed": g2_direction_seed(layer, 0),
                    "direction_generator": "numpy_pcg64_standard_normal",
                    "transport_operators": G2_TRANSPORT_OPERATORS,
                    "sign": sign,
                    "rms_fraction": G2_ANCHOR_RMS_FRACTION,
                    "dose_role": "linearity_anchor",
                    "result_fields": (),
                }
                rows.append({"task_id": stable_id("g2", core), **core})
    return tuple(rows)


def g3_fixture_rows() -> tuple[dict[str, Any], ...]:
    """Return the exact 72 reviewed, clean semantic fixtures."""

    rows: list[dict[str, Any]] = []
    for family in G3_FAMILIES:
        for cloze_index, stem in enumerate(SEMANTIC_CLOZES[family], start=1):
            core = {
                "gate": "G3",
                "family": family,
                "cloze_index": cloze_index,
                "render_mode": semantic_render_mode(cloze_index),
                "render_contract": g3_render_contract(
                    semantic_render_mode(cloze_index), stem
                ),
                "instruction": SEMANTIC_INSTRUCTION,
                "stem": stem,
                "candidate_tokens": G3_TOKEN_GROUPS[family],
                "fixture_status": "reviewed_clean_fixture",
                "result_fields": (),
            }
            rows.append({"fixture_id": stable_id("g3", core), **core})
    return tuple(rows)


def g3p_plan_rows() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for prompt_index, (question, expected_label, pair_id) in enumerate(
        POLARITY_QUESTIONS, start=1
    ):
        core = {
            "gate": "G3P",
            "prompt_id": f"factual_yes_no_{prompt_index:02d}",
            "fixture_role": "clean_factual_yes_no",
            "instruction": POLARITY_INSTRUCTION,
            "question": question,
            "expected_label": expected_label,
            "pair_id": pair_id,
            "fixture_status": "reviewed_clean_fixture",
            "result_fields": (),
        }
        rows.append({"task_id": stable_id("g3p", core), **core})
    return tuple(rows)


def g4_aggregate_assignments() -> tuple[dict[str, Any], ...]:
    """Construct fifty fresh target assignments without using prior results."""

    rows: list[dict[str, Any]] = []
    all_subsets = tuple(
        subset
        for size in range(G4_SUBSET_SIZE_RANGE[0], G4_SUBSET_SIZE_RANGE[1] + 1)
        for subset in combinations(G4_TARGET_FEATURE_IDS, size)
    )
    for index, feature_ids in enumerate(all_subsets, start=1):
        rows.append(
            {
                "assignment_id": f"aggregate_{index:02d}",
                "target_feature_ids": feature_ids,
                "absolute_coefficients": tuple(0.5 for _ in feature_ids),
                "selection_authority": "complete_size_2_3_4_combination_schedule",
            }
        )
    return tuple(rows)


def g4_plan_rows() -> tuple[dict[str, Any], ...]:
    """Return the full target/matched/isotropic numerical-preflight inventory."""

    rows: list[dict[str, Any]] = []
    for assignment in g4_aggregate_assignments():
        for vector_class in G4_VECTOR_CLASSES:
            for sign in G4_SIGNS:
                vector_definition: dict[str, Any]
                if vector_class == "target":
                    vector_definition = {
                        "feature_ids": assignment["target_feature_ids"],
                        "absolute_coefficients": assignment["absolute_coefficients"],
                        "selection_status": "frozen",
                    }
                elif vector_class == "matched":
                    vector_definition = {
                        "feature_slots": tuple(
                            f"matched_for_target_{target_feature_id}"
                            for target_feature_id in assignment["target_feature_ids"]
                        ),
                        "absolute_coefficients": assignment["absolute_coefficients"],
                        "selection_status": "fresh_neutral_statistics_required",
                    }
                else:
                    vector_definition = {
                        "isotropic_seed": identity_bound_seed64(
                            "g4-isotropic-v1", assignment["assignment_id"]
                        ),
                        "norm_match_to": assignment["assignment_id"],
                        "selection_status": "materialize_after_target_bf16_norm",
                    }
                core = {
                    "gate": "G4",
                    "assignment_id": assignment["assignment_id"],
                    "vector_class": vector_class,
                    "sign": sign,
                    "vector_definition": vector_definition,
                    "required_check_order": (
                        "decoder_inputs_are_finite",
                        "materialize_bfloat16_vector",
                        "vector_norm_and_rms",
                        "relative_rms_on_all_neutral_prompts",
                        "preflight_passes_before_any_edit",
                    ),
                    "result_fields": (),
                }
                rows.append({"task_id": stable_id("g4", core), **core})
    return tuple(rows)


def public_input_allowlist() -> dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "policy": "deny_unlisted",
        "allowed_inputs": (
            {
                "input_id": "model",
                "authority": "huggingface_public_artifact",
                "role": "model_weights_and_tokenizer",
                **MODEL_SPEC,
            },
            {
                "input_id": "sae",
                "authority": "huggingface_public_artifact",
                "role": "sae_checkpoint",
                **SAE_SPEC,
            },
            {
                "input_id": "j_lens",
                "authority": "huggingface_public_artifact",
                "role": "jacobian_lens_checkpoint",
                **J_LENS_SPEC,
            },
        ),
        "embedded_fixture_inputs": (
            "experiments/consciousness_readout_validation/protocol.py",
            "experiments/consciousness_readout_validation/fixtures.py",
        ),
        "prior_outcome_inputs": (),
        "target_prompt_inputs": (),
        "target_outcome_inputs": (),
        "external_receipt_inputs": (),
        "forbidden_path_markers": (
            "consciousness_sae_changepoint",
            "public_sae_consciousness_gating",
            "sae_jlens_audit",
            "causal_transplant",
            "gemma_scope_9b",
        ),
    }


def gate_specs() -> dict[str, Any]:
    return {
        "G1": {
            "purpose": "J-lens shape, arithmetic, identity, and transport checks",
            "map_layers": G1_MAP_LAYERS,
            "capture_states": CAPTURE_STATES,
            "hash_selected_lexical_token_ids": G1_HASH_SELECTED_LEXICAL_TOKEN_IDS,
            "neutral_token_panel_status": "unresolved_tokenizer_audit_required",
            "neutral_token_selection_rule": G1_TOKEN_SELECTION_RULE,
            "relative_rmse_max": G1_RELATIVE_RMSE_MAX,
            "sign_agreement_min": G1_SIGN_AGREEMENT_MIN,
        },
        "G2": {
            "purpose": "neutral perturbation transport and linearity",
            "prompt_count": G2_PROMPT_COUNT,
            "bands": G2_BANDS,
            "identity_incremental_layers": G2_IDENTITY_LAYERS,
            "linearity_layers": G2_LINEARITY_LAYERS,
            "directions": G2_DIRECTIONS,
            "signs": G2_SIGNS,
            "primary_rms_fraction": G2_PRIMARY_RMS_FRACTION,
            "anchor_rms_fraction": G2_ANCHOR_RMS_FRACTION,
            "random_control_count": G2_RANDOM_CONTROL_COUNT,
            "direction_seed_namespace": G2_DIRECTION_SEED_NAMESPACE,
            "direction_generator": "numpy_pcg64_standard_normal",
            "random_j_seed_namespace": G2_RANDOM_J_SEED_NAMESPACE,
            "transport_operators": G2_TRANSPORT_OPERATORS,
            "band_residual_lcb_min": G2_BAND_RESIDUAL_LCB_MIN,
            "band_logit_lcb_min": G2_BAND_LOGIT_LCB_MIN,
            "random_advantage_lcb_min": G2_RANDOM_ADVANTAGE_LCB_MIN,
            "linearity_cosine_min": G2_LINEARITY_COSINE_MIN,
            "slope_discrepancy_max": G2_SLOPE_DISCREPANCY_MAX,
            "identity_advantage_lcb_min": G2_IDENTITY_ADVANTAGE_LCB_MIN,
        },
        "G3": {
            "purpose": "clean semantic readout sensitivity",
            "families": G3_FAMILIES,
            "clozes_per_family": G3_CLOZES_PER_FAMILY,
            "render_modes": G3_RENDER_MODES,
            "render_contract_version": G3_RENDER_CONTRACT_VERSION,
            "minimal_user_text": G3_MINIMAL_USER_TEXT,
            "framed_user_text": G3_FRAMED_USER_TEXT,
            "framed_assistant_prefix": G3_FRAMED_ASSISTANT_PREFIX,
            "downstream_layers": G3_DOWNSTREAM_LAYERS,
            "random_control_count": G3_RANDOM_CONTROL_COUNT,
            "fixture_status": "reviewed_clean_fixture",
            "tokenization_contract": G3_TOKENIZATION_CONTRACT,
            "actual_macro_lcb_min": G3_ACTUAL_MACRO_LCB_MIN,
            "actual_accuracy_lcb_min": G3_ACTUAL_ACCURACY_LCB_MIN,
            "actual_explicit_adjacent_lcb_min": G3_ACTUAL_EXPLICIT_ADJACENT_LCB_MIN,
            "j_macro_lcb_min": G3_J_MACRO_LCB_MIN,
            "j_accuracy_lcb_min": G3_J_ACCURACY_LCB_MIN,
            "j_explicit_adjacent_lcb_min": G3_J_EXPLICIT_ADJACENT_LCB_MIN,
            "random_advantage_lcb_min": G3_RANDOM_ADVANTAGE_LCB_MIN,
            "loo_actual_lcb_min": G3_LOO_ACTUAL_LCB_MIN,
            "loo_j_lcb_min": G3_LOO_J_LCB_MIN,
            "render_mode_auc_min": G3_RENDER_MODE_AUC_MIN,
        },
        "G3P": {
            "purpose": "clean factual Yes/No polarity control",
            "prompt_count": G3P_PROMPT_COUNT,
            "fixture_status": "reviewed_clean_fixture",
            "actual_correct_required": G3P_ACTUAL_CORRECT_REQUIRED,
            "j_correct_required": G3P_J_CORRECT_REQUIRED,
            "random_advantage_questions": G3P_RANDOM_ADVANTAGE_QUESTIONS,
        },
        "G4": {
            "purpose": "target-vector numerical safety only",
            "neutral_prompt_count": G4_PROMPT_COUNT,
            "fresh_subset_count": G4_SUBSET_COUNT,
            "subset_size_range": G4_SUBSET_SIZE_RANGE,
            "control_types": G4_CONTROL_TYPES,
            "vector_classes": G4_VECTOR_CLASSES,
            "signs": G4_SIGNS,
            "preflight_required_before_edit": G4_PREFLIGHT_REQUIRED,
            "sentinel_prompt_ids": G4_SENTINEL_PROMPT_IDS,
            "rms_ratio_max": G4_RMS_RATIO_MAX,
            "control_norm_relative_error_max": G4_CONTROL_NORM_RELATIVE_ERROR_MAX,
            "delta_relative_rmse_max": G4_DELTA_RELATIVE_RMSE_MAX,
            "sign_cosine_min": G4_SIGN_COSINE_MIN,
            "hook_fire_count": G4_HOOK_FIRE_COUNT,
            "vector_arithmetic_spec": G4_VECTOR_ARITHMETIC_SPEC,
            "realization_spec": G4_REALIZATION_SPEC,
            "matching_spec": G4_MATCHING_SPEC,
        },
    }


def protocol_snapshot() -> dict[str, Any]:
    """Return the exact, result-free machine-readable protocol snapshot."""

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "status": "target_blind_validation_pilot_not_osf_confirmatory",
        "structural_audit_issuer": STRUCTURAL_AUDIT_ISSUER,
        "measurement_lineage_spec": MEASUREMENT_LINEAGE_SPEC,
        "pilot_random_seed": PILOT_RANDOM_SEED,
        "scope": PILOT_SCOPE,
        "claims_excluded": CLAIMS_EXCLUDED,
        "container_image": CONTAINER_IMAGE_SPEC,
        "model": MODEL_SPEC,
        "sae": SAE_SPEC,
        "j_lens": J_LENS_SPEC,
        "hook_contract": HOOK_CONTRACT,
        "gate_consequence_policy": GATE_CONSEQUENCE_POLICY,
        "gate_specs": gate_specs(),
        "analysis_resampling": {
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "permutation_replicates": PERMUTATION_REPLICATES,
            "permutation_seed": PERMUTATION_SEED,
        },
        "fresh_data_contract": {
            "prior_outcome_inputs": (),
            "target_prompt_inputs": (),
            "target_outcome_inputs": (),
            "outcome_fields_in_plan": (),
        },
    }


def assert_protocol_invariants() -> None:
    assert len(J_MAP_LAYERS) == 34
    assert tuple(HOOK_CONTRACT["j_lens"]["source_layers"]) == J_MAP_LAYERS
    assert len(CAPTURE_STATES) == 36
    assert CAPTURE_STATES[-1] == "final"
    assert capture_state_map_layer("final") is None
    assert len(neutral_prompts()) == G4_PROMPT_COUNT
    prompt_ids = {prompt["prompt_id"] for prompt in neutral_prompts()}
    assert set(G4_SENTINEL_PROMPT_IDS) <= prompt_ids
    assert len(G3_FAMILIES) == 9
    assert len(set(G3_FAMILIES)) == 9
    assert set(G3_TOKEN_GROUPS) == set(G3_FAMILIES)
    assert len(g1_plan_rows()) == 34 * 4
    assert len(g2_plan_rows()) == (24 * 34 * 2 * 2) + (8 * 8 * 2)
    assert len(g3_fixture_rows()) == 9 * 8
    assert len(g3p_plan_rows()) == 24
    assert len(g4_aggregate_assignments()) == 50
    assert len(g4_plan_rows()) == 50 * 3 * 2
    assert not public_input_allowlist()["prior_outcome_inputs"]


assert_protocol_invariants()
