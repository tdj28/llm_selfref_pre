"""Frozen protocol for pre-SAE generic-vector delivery/J-readout calibration.

This is a new adaptive study.  The compact v1 failure receipts informed the
dose grid, but no v1 raw row is an analysis input and no paper/target prompt or
target SAE feature is rendered.  The study separates three questions:

1. Was the requested BF16 edit delivered faithfully?
2. Is the realized edit locally dose-linear?
3. Does the learned J add predictive information beyond identity/random maps?

Only hard native delivery, requested-to-realized fidelity, and common-mode
control within (1) are measurement gates for a later actual-state causal
study.  Local linearity gates only linear-response claims.  Current-study J
orientation and BF16-versus-FP32 J-shadow fidelity gate only J-derived claims.
None of those J or linearity results erases a faithfully delivered nonlinear
actual-state response.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.consciousness_sae_realization_validation import protocol as base


STUDY_SLUG = "consciousness_sae_target_blind_calibration"
STUDY_ID = "consciousness_sae_target_blind_calibration_v2"
PROTOCOL_VERSION = "consciousness_sae_target_blind_calibration_v2.0.0"
PLAN_SCHEMA_VERSION = 1
NETWORK_VOLUME_ID = "bv9gb9j32y"
DATA_CENTER_ID = "US-CA-2"
GPU_TYPE = "NVIDIA B200"
VOLUME_MOUNT_PATH = "/workspace"
PROVIDER_DEADLINE_SECONDS = 6 * 60 * 60

MODEL_SPEC = base.MODEL_SPEC
SAE_SPEC = base.SAE_SPEC
J_LENS_SPEC = base.J_LENS_SPEC
CONTAINER_IMAGE_SPEC = base.CONTAINER_IMAGE_SPEC
WIDTH = base.WIDTH
VOCAB_SIZE = base.VOCAB_SIZE
J_LAYERS = base.J_LAYERS
EDIT_LAYER = 50
PRIMARY_READOUT_LAYER = 50
READOUT_LAYERS = tuple(range(50, 79))
DIRECTIONS = (0, 1, 2)
DOSE_GRID = (0.01, 0.02, 0.03, 0.04, 0.08)
DIAGNOSTIC_DOSES = (0.01,)
REALIZATION_GATE_DOSES = (0.02, 0.03, 0.04, 0.08)
LINEARITY_GATE_DOSES = (0.02, 0.03, 0.04)
PRIMARY_DOSE = 0.03
RANDOM_J_COUNT = 5
TRANSPORTS = (
    "real_j",
    "identity",
    *(f"random_j_{index}" for index in range(RANDOM_J_COUNT)),
)
TOP_K = 2_000
REQUESTED_REALIZED_COMPONENTS = ("plus", "minus", "central")
RUNNER_WATCHDOG_SECONDS = 60 * 60
AUDIT_RESERVE_SECONDS = 30 * 60
CAMPAIGN_WATCHDOG_SECONDS = RUNNER_WATCHDOG_SECONDS + AUDIT_RESERVE_SECONDS
FRESH_RANDOMIZATION_SPEC = {
    "seed_material": ("study_id", "protocol_version", "namespace", "coordinates"),
    "runtime_seed_namespace": "runtime-v2",
    "direction_seed_namespace": "generic-layer50-direction",
    "fixed_token_panel_seed_namespace": "fixed-token-panel-v2",
    "fixed_token_panel_size": 2_048,
    "fixed_token_panel_token_id_upper_bound_exclusive": 128_000,
    "fixed_token_panel_special_or_reserved_ids_included": False,
    "random_j_seed_namespace": "random-j-v2",
    "random_j_control_count": RANDOM_J_COUNT,
    "j_orientation_seed_namespace": "j-orientation-fixture-v2",
    "predecessor_randomization_reused": False,
    "predecessor_control_values_reused": False,
}
J_ORIENTATION_SPEC = {
    "fixture_count_per_layer": 2,
    "fixture_seed_namespace": "j-orientation-fixture-v2",
    "fixture_algorithm": "shake256_uint32_centered_l2_normalized_v2",
    "production_algorithm": "row_residual_at_j_transpose_bfloat16",
    "reference_algorithm": "explicit_component_sum_j_ij_times_x_j_float32_v2",
    "wrong_orientation_algorithm": "row_residual_at_j",
    "reference_row_chunk_size": 256,
    "current_study_only": True,
    "claim_scope": "j_derived_claims_only",
}

# These state-coordinate contracts make the hook and released-J semantics
# independently inspectable rather than leaving them implicit in runtime code.
INTERVENTION_STATE_CONTRACT = {
    "schema_version": 1,
    "construct": "pre_sae_generic_vector_delivery",
    "model_repository_url": (
        "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct/tree/"
        "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
    ),
    "model_revision": MODEL_SPEC["revision"],
    "implementation_binding": {
        "path": ("experiments/consciousness_sae_realization_validation/runtime.py"),
        "sha256_binding": "source_files.json entry for this exact path",
    },
    "rendered_sequence": "chat_template_with_generation_prompt",
    "prefix_token_slice": "token_ids[0:-1]",
    "continuation_token_index": "token_ids[-1]",
    "continuation_forward_sequence_length": 1,
    "edited_module": "model.model.layers[50]",
    "hook_api": "register_forward_hook",
    "hook_boundary": "zero_based_block_50_output_post_block_pre_block_51",
    "edited_tensor_slice": "hidden_state[0,0,:]",
    "edited_tensor_shape": [1, 1, WIDTH],
    "edited_token_role": "last_rendered_generation_prompt_token",
    "request_arithmetic": {
        "direction_and_scale_dtype": "float32",
        "single_native_cast_dtype": "bfloat16",
        "positive_branch": "native_bfloat16(pre_state + requested_bfloat16)",
        "negative_branch": "native_bfloat16(pre_state - requested_bfloat16)",
    },
    "hook_registration_order": ["capture_pre_edit", "apply_edit"],
    "layer_50_archives": [
        "captured_pre_edit_block_output",
        "explicit_post_edit_block_output",
    ],
    "prefix_cache_contract": {
        "prefix_forward_use_cache": True,
        "clean_and_signed_continuations_share_prefix_values": True,
        "branch_cache_objects_are_independent_clones": True,
        "plus_minus_branch_order_is_not_an_estimand": True,
    },
    "hook_fire_count_per_edited_forward": 1,
}

J_STATE_CONTRACT = {
    "schema_version": 1,
    "construct": "released_corpus_mean_jacobian_readout",
    "upstream_repository_url": "https://github.com/anthropics/jacobian-lens",
    "upstream_revision": "581d398613e5602a5af361e1c34d3a92ea82ba8e",
    "upstream_source_urls": {
        "hook_semantics": (
            "https://raw.githubusercontent.com/anthropics/jacobian-lens/"
            "581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/hooks.py"
        ),
        "huggingface_adapter": (
            "https://raw.githubusercontent.com/anthropics/jacobian-lens/"
            "581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/hf.py"
        ),
        "target_layer_default": (
            "https://raw.githubusercontent.com/anthropics/jacobian-lens/"
            "581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/fitting.py"
        ),
    },
    "upstream_source_sha256": {
        "hooks.py": (
            "c781d6944fd23396d3fc65a04db1f1db807f6f12cd5912cdbd2fb67eb3508081"
        ),
        "hf.py": ("228cf078e4586a7b7f61a6f5064403b8960de337afd19256efa56f04d53e3222"),
        "fitting.py": (
            "5be8959db8efc34cee41ed677beba84e21ba3c9e3ccb958bdbc1600c86b5e080"
        ),
    },
    "release_repository_url": "https://huggingface.co/neuronpedia/jacobian-lens",
    "release_revision": J_LENS_SPEC["revision"],
    "checkpoint_url": (
        "https://huggingface.co/neuronpedia/jacobian-lens/resolve/"
        "a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/"
        "jlens/Salesforce-wikitext/"
        "Llama-3.3-70B-Instruct_jacobian_lens.pt"
    ),
    "checkpoint_sha256": J_LENS_SPEC["sha256"],
    "release_config_url": (
        "https://huggingface.co/neuronpedia/jacobian-lens/resolve/"
        "a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/"
        "jlens/Salesforce-wikitext/config.yaml"
    ),
    "release_config_sha256": J_LENS_SPEC["release_config"]["sha256"],
    "release_target_layer_config": None,
    "release_target_layer_default": 79,
    "source_coordinate": "zero_based_transformer_block_output",
    "target_coordinate": ("zero_based_block_79_output_equal_to_final_rmsnorm_input"),
    "primary_source_coordinate": "explicit_post_edit_block_50_output",
    "later_source_coordinates": "post_block_outputs_51_through_78",
    "row_vector_application": "residual_delta @ J_l.T",
    "column_vector_definition": "J_l @ residual_delta",
    "intercept": None,
    "centering_reference": None,
    "primary_readout_layer": PRIMARY_READOUT_LAYER,
    "descriptive_profile_layers": list(range(51, 79)),
}

FIXED_PANEL_ESTIMAND = {
    "schema_version": 1,
    "primary_readout_layer": PRIMARY_READOUT_LAYER,
    "primary_dose_fraction": PRIMARY_DOSE,
    "prompt_panel": "exact_frozen_eight_neutral_prompts",
    "direction_panel": "exact_frozen_three_generic_directions",
    "token_id_scope": "ids_0_through_127999_excluding_reserved_special_range",
    "aggregation_order": "mean_directions_within_prompt_then_mean_prompts",
    "resampling_unit": "prompt_id",
    "resampling_replicates": 20_000,
    "interval_label": "fixed_panel_prompt_resampling_stability_interval",
    "population_generalization_claim": False,
    "primary_claim_scope": (
        "descriptive_performance_on_the_exact_frozen_prompt_and_direction_panel"
    ),
    "other_readout_layers_role": "descriptive_profile_only_no_eligibility_gate",
    "across_layer_selection": False,
}

FORWARD_INVENTORY = {
    "schema_version": 1,
    "model_forward_definition": "one_full_model_forward_invocation",
    "prefix_forwards": 8,
    "clean_continuation_forwards": 8,
    "edited_continuation_forwards": 240,
    "exact_total_model_forwards": 256,
    "orientation_fixture_model_forwards": 0,
}

CLAIM_GATE_POLICY = {
    "actual_state_collection_operational_prerequisites": (
        "complete_raw_transaction",
        "independent_audit",
    ),
    "actual_state_collection_measurement_gates": (
        "hard_native_delivery",
        "requested_realized_fidelity",
        "common_mode_control",
    ),
    "actual_state_collection_non_gates": (
        "realized_source_linearity",
        "j_of_realized_linearity",
        "downstream_model_linearity",
        "j_orientation",
        "bf16_fp32_j_shadow_fidelity",
        "j_absolute_performance",
        "j_over_random",
        "j_over_identity",
    ),
    "linear_response_claim_gates": (
        "realized_source_linearity",
        "j_of_realized_linearity_for_linear_j_claims",
        "downstream_model_linearity_for_linear_downstream_claims",
    ),
    "j_projection_claim_gates": (
        "current_study_j_orientation",
        "bf16_fp32_j_shadow_fidelity",
    ),
    "j_predictive_association_claim_gates": (
        "absolute_real_j",
        "real_j_over_random",
    ),
    "j_added_value_claim_gate": "real_j_over_identity",
}

EXECUTION_AUTHORIZATION_SPEC = {
    "required": True,
    "issued_after_plan_and_bound_sources_are_committed": True,
    "local_head_must_equal_live_pushed_remote_commit": True,
    "plan_defining_paths_must_be_clean": True,
    "binds_plan_source_and_provider_receipt_hashes": True,
    "provider_deadline_seconds": PROVIDER_DEADLINE_SECONDS,
    "campaign_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "runner_sub_watchdog_seconds": RUNNER_WATCHDOG_SECONDS,
    "audit_reserve_seconds": AUDIT_RESERVE_SECONDS,
    # Compatibility name for the whole runner-plus-audit campaign.
    "calibration_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "provider_authority_spend_cap_usd": 36.0,
}

INDEPENDENT_RECOMPUTATION_SPEC = {
    "full_model_forward_required": False,
    "pinned_model_weights_required": True,
    "j_lens_checkpoint_required": True,
    "rehash_manifested_raw_files": True,
    "rehash_bound_plan_sources": True,
    "rehash_pinned_public_artifacts_before_model_load": True,
    "reconstruct_signed_realized_edits_from_pre_post_arcs": True,
    "recompute_request_fidelity_common_mode_and_linearity": True,
    "recompute_transport_and_fixed_panel_metrics_from_archived_tensors": True,
    "reject_unmanifested_missing_duplicate_nonfinite_or_partial_data": True,
}

NEUTRAL_SYSTEM = (
    "Answer the mundane question briefly and literally. Do not add commentary."
)
PROMPTS = (
    ("neutral_c01", "What object is commonly used to unlock a door?"),
    ("neutral_c02", "Which planet is closest to the Sun?"),
    ("neutral_c03", "What color are ripe bananas usually?"),
    ("neutral_c04", "Which room in a home commonly contains a bathtub?"),
    ("neutral_c05", "How many days are in a standard week?"),
    ("neutral_c06", "What handheld tool is commonly used to cut paper?"),
    ("neutral_c07", "Which body part is normally used for hearing sounds?"),
    ("neutral_c08", "What appliance turns slices of bread into toast?"),
)
PROMPT_IDS = tuple(prompt_id for prompt_id, _ in PROMPTS)

GATE_THRESHOLDS = {
    "requested_realized_relative_rmse_max": 0.10,
    "requested_realized_cosine_min": 0.995,
    "common_mode_to_central_rms_max": 0.10,
    "bf16_fp32_j_cosine_min": 0.995,
    "bf16_fp32_j_relative_rmse_max": 0.10,
    "j_orientation_reference_cosine_min": 0.995,
    "j_orientation_reference_relative_rmse_max": 0.05,
    "j_orientation_wrong_relative_rmse_margin_min": 0.10,
    "j_orientation_wrong_cosine_gap_min": 0.10,
    "linearity_cosine_min": 0.95,
    "linearity_slope_discrepancy_max": 0.15,
    "real_j_residual_cosine_lcb_min": 0.10,
    "real_j_logit_pearson_lcb_min": 0.25,
    "real_j_residual_cosine_margin_over_identity": 0.02,
    "real_j_logit_pearson_margin_over_identity": 0.02,
    "real_j_residual_cosine_margin_over_best_random": 0.05,
    "real_j_logit_pearson_margin_over_best_random": 0.05,
    "bootstrap_replicates": 20_000,
    "confidence": 0.95,
    "cluster_unit": "prompt_id",
}

RESOURCE_LIMITS = {
    "max_spend_usd": 9.0,
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "provider_authority_spend_cap_usd": 36.0,
    "max_walltime_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "campaign_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "runner_sub_watchdog_seconds": RUNNER_WATCHDOG_SECONDS,
    "audit_reserve_seconds": AUDIT_RESERVE_SECONDS,
    # Compatibility name for the whole runner-plus-audit campaign.
    "calibration_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "runner_max_spend_usd": 6.0,
    "audit_reserve_spend_usd": 3.0,
    "provider_deadline_seconds": PROVIDER_DEADLINE_SECONDS,
    "expected_edited_forwards": 240,
    "expected_model_forwards": 256,
    "expected_raw_bytes_approx": 320_000_000,
    "raw_run_ceiling_bytes": 1024**3,
    "post_run_free_reserve_bytes": 64 * 1024**3,
}

ADAPTIVE_DESIGN_INPUTS = {
    "role": "design_provenance_only_no_rows_loaded_or_pooled",
    "predecessor_run_id": "stagea-97e38c5-20260714T201158Z",
    "physical_file_sha256": {
        "STAGE_A_AUDIT.json": "3c956bd392fce2386cbba85d6841c3393a83abadc8946ac50acb17342e908a4d",
        "STAGE_A_RECEIPT.json": "a01fa3e70d1c5cfadb6e19fdc3f30557c1de25d9f77473cdfd7f8f40faa46716",
        "STAGE_A_SUMMARY.json": "ca46766cd843adc9cc047090804717894cbbd0157a3e3249cbdbca79df3d5510",
    },
    "facts_used": [
        "all one-percent requested-to-realized rows failed the frozen fidelity criteria",
        "no fidelity flags occurred at two, four, or eight percent",
        "the one-to-eight-percent downstream dose response failed the frozen linearity criterion",
        "J orientation and layer-50 BF16-versus-FP32 shadow checks passed",
        "real J beat five random controls but did not clear the frozen identity-margin gate",
    ],
    "analysis_data_inputs": [],
}


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


def sha256_file(path: Path, *, chunk_bytes: int = 8 * 1024 * 1024) -> str:
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


def prompt_payload(prompt_id: str) -> dict[str, str]:
    prompts = dict(PROMPTS)
    if prompt_id not in prompts:
        raise KeyError(f"unknown calibration prompt: {prompt_id}")
    return {"system": NEUTRAL_SYSTEM, "user": prompts[prompt_id]}


def rows() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "prompt_id": prompt_id,
            "edit_layer": EDIT_LAYER,
            "direction": direction,
            "dose_fraction": dose,
        }
        for prompt_id in PROMPT_IDS
        for direction in DIRECTIONS
        for dose in DOSE_GRID
    )


def protocol_snapshot() -> dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "scope": "adaptive_target_blind_numerical_calibration_only",
        "study_role": "pre_sae_generic_vector_delivery_and_j_readout_calibration",
        "paper_or_target_prompts_included": False,
        "target_sae_features_included": False,
        "adaptive_design_inputs": ADAPTIVE_DESIGN_INPUTS,
        "analysis_data_inputs": [],
        "model": MODEL_SPEC,
        "sae": SAE_SPEC,
        "j_lens": J_LENS_SPEC,
        "container_image": CONTAINER_IMAGE_SPEC,
        "provider": {
            "network_volume_id": NETWORK_VOLUME_ID,
            "data_center_id": DATA_CENTER_ID,
            "gpu_type": GPU_TYPE,
            "gpu_count": 1,
            "volume_mount_path": VOLUME_MOUNT_PATH,
        },
        "prompt_payloads": [
            {"prompt_id": prompt_id, **prompt_payload(prompt_id)}
            for prompt_id in PROMPT_IDS
        ],
        "edit_layer": EDIT_LAYER,
        "primary_readout_layer": PRIMARY_READOUT_LAYER,
        "captured_j_layers": list(J_LAYERS),
        "readout_transport_layers": list(READOUT_LAYERS),
        "pre_injection_zero_delta_layers": list(range(45, 50)),
        "directions": list(DIRECTIONS),
        "dose_grid": list(DOSE_GRID),
        "diagnostic_doses": list(DIAGNOSTIC_DOSES),
        "realization_gate_doses": list(REALIZATION_GATE_DOSES),
        "linearity_gate_doses": list(LINEARITY_GATE_DOSES),
        "primary_dose": PRIMARY_DOSE,
        "transports": list(TRANSPORTS),
        "requested_realized_components": list(REQUESTED_REALIZED_COMPONENTS),
        "fresh_randomization": FRESH_RANDOMIZATION_SPEC,
        "j_orientation": J_ORIENTATION_SPEC,
        "intervention_state_contract": INTERVENTION_STATE_CONTRACT,
        "intervention_state_contract_sha256": canonical_sha256(
            INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract": J_STATE_CONTRACT,
        "j_state_contract_sha256": canonical_sha256(J_STATE_CONTRACT),
        "fixed_panel_estimand": FIXED_PANEL_ESTIMAND,
        "forward_inventory": FORWARD_INVENTORY,
        "top_k_browse_index": TOP_K,
        "thresholds": GATE_THRESHOLDS,
        "resource_limits": RESOURCE_LIMITS,
        "claim_gate_policy": CLAIM_GATE_POLICY,
        "execution_authorization": EXECUTION_AUTHORIZATION_SPEC,
        "independent_recomputation": INDEPENDENT_RECOMPUTATION_SPEC,
        "storage": {
            "raw_namespace": f"{STUDY_SLUG}/{STUDY_ID}/raw",
            "raw_location": "RunPod network volume only",
            "git_allowed": "plan, compact receipts, hashes, summaries",
            "git_forbidden": "raw residuals, arithmetic tensors, raw logits",
        },
    }


def validate_protocol() -> None:
    if (
        len(rows()) != 120
        or len(rows()) * 2 != RESOURCE_LIMITS["expected_edited_forwards"]
    ):
        raise ValueError("calibration row/forward inventory differs")
    if (
        RESOURCE_LIMITS["expected_model_forwards"]
        != len(PROMPT_IDS) * 2 + len(rows()) * 2
        or FORWARD_INVENTORY["prefix_forwards"] != len(PROMPT_IDS)
        or FORWARD_INVENTORY["clean_continuation_forwards"] != len(PROMPT_IDS)
        or FORWARD_INVENTORY["edited_continuation_forwards"] != len(rows()) * 2
        or FORWARD_INVENTORY["exact_total_model_forwards"]
        != RESOURCE_LIMITS["expected_model_forwards"]
    ):
        raise ValueError("model-forward inventory differs")
    if set(DIAGNOSTIC_DOSES) & set(REALIZATION_GATE_DOSES):
        raise ValueError("diagnostic and realization-gate doses overlap")
    if set(DIAGNOSTIC_DOSES) | set(REALIZATION_GATE_DOSES) != set(DOSE_GRID):
        raise ValueError("dose roles do not partition the grid")
    if not set(LINEARITY_GATE_DOSES) <= set(REALIZATION_GATE_DOSES):
        raise ValueError("linearity doses are outside the realization gate")
    if PRIMARY_DOSE not in LINEARITY_GATE_DOSES:
        raise ValueError("primary dose is outside the local-linearity band")
    if READOUT_LAYERS != tuple(layer for layer in J_LAYERS if layer >= EDIT_LAYER):
        raise ValueError("readout-layer inventory differs from the released J maps")
    if (
        PRIMARY_READOUT_LAYER != EDIT_LAYER
        or PRIMARY_READOUT_LAYER not in READOUT_LAYERS
        or FIXED_PANEL_ESTIMAND["primary_readout_layer"] != PRIMARY_READOUT_LAYER
        or FIXED_PANEL_ESTIMAND["other_readout_layers_role"]
        != "descriptive_profile_only_no_eligibility_gate"
        or FIXED_PANEL_ESTIMAND["population_generalization_claim"] is not False
        or FIXED_PANEL_ESTIMAND["across_layer_selection"] is not False
    ):
        raise ValueError("fixed-panel primary estimand differs")
    if (
        INTERVENTION_STATE_CONTRACT["hook_boundary"]
        != "zero_based_block_50_output_post_block_pre_block_51"
        or INTERVENTION_STATE_CONTRACT["edited_tensor_shape"] != [1, 1, WIDTH]
        or J_STATE_CONTRACT["primary_readout_layer"] != PRIMARY_READOUT_LAYER
        or J_STATE_CONTRACT["release_target_layer_default"] != 79
        or J_STATE_CONTRACT["checkpoint_sha256"] != J_LENS_SPEC["sha256"]
        or J_STATE_CONTRACT["release_config_sha256"]
        != J_LENS_SPEC["release_config"]["sha256"]
    ):
        raise ValueError("intervention/J state-coordinate contract differs")
    if REQUESTED_REALIZED_COMPONENTS != ("plus", "minus", "central"):
        raise ValueError("signed requested-realized component inventory differs")
    if (
        FRESH_RANDOMIZATION_SPEC["predecessor_randomization_reused"] is not False
        or FRESH_RANDOMIZATION_SPEC["predecessor_control_values_reused"] is not False
        or FRESH_RANDOMIZATION_SPEC["random_j_control_count"] != RANDOM_J_COUNT
        or FRESH_RANDOMIZATION_SPEC["fixed_token_panel_size"] != 2_048
        or FRESH_RANDOMIZATION_SPEC["fixed_token_panel_token_id_upper_bound_exclusive"]
        != 128_000
        or FRESH_RANDOMIZATION_SPEC[
            "fixed_token_panel_special_or_reserved_ids_included"
        ]
        is not False
        or J_ORIENTATION_SPEC["current_study_only"] is not True
    ):
        raise ValueError("fresh v2 randomization/orientation contract differs")
    if CLAIM_GATE_POLICY["actual_state_collection_measurement_gates"] != (
        "hard_native_delivery",
        "requested_realized_fidelity",
        "common_mode_control",
    ):
        raise ValueError("actual-state collection measurement gates differ")
    if set(CLAIM_GATE_POLICY["actual_state_collection_measurement_gates"]) & set(
        CLAIM_GATE_POLICY["actual_state_collection_non_gates"]
    ):
        raise ValueError("actual-state collection gates and non-gates overlap")
    if (
        RESOURCE_LIMITS["calibration_sub_watchdog_seconds"]
        != RESOURCE_LIMITS["max_walltime_seconds"]
        or RESOURCE_LIMITS["campaign_sub_watchdog_seconds"] != CAMPAIGN_WATCHDOG_SECONDS
        or RESOURCE_LIMITS["runner_sub_watchdog_seconds"] != RUNNER_WATCHDOG_SECONDS
        or RESOURCE_LIMITS["audit_reserve_seconds"] != AUDIT_RESERVE_SECONDS
        or RUNNER_WATCHDOG_SECONDS + AUDIT_RESERVE_SECONDS != CAMPAIGN_WATCHDOG_SECONDS
        or RESOURCE_LIMITS["calibration_sub_watchdog_seconds"]
        >= RESOURCE_LIMITS["provider_deadline_seconds"]
        or EXECUTION_AUTHORIZATION_SPEC["provider_deadline_seconds"]
        != RESOURCE_LIMITS["provider_deadline_seconds"]
        or EXECUTION_AUTHORIZATION_SPEC["calibration_sub_watchdog_seconds"]
        != RESOURCE_LIMITS["calibration_sub_watchdog_seconds"]
        or EXECUTION_AUTHORIZATION_SPEC["campaign_sub_watchdog_seconds"]
        != CAMPAIGN_WATCHDOG_SECONDS
        or EXECUTION_AUTHORIZATION_SPEC["runner_sub_watchdog_seconds"]
        != RUNNER_WATCHDOG_SECONDS
        or EXECUTION_AUTHORIZATION_SPEC["audit_reserve_seconds"]
        != AUDIT_RESERVE_SECONDS
        or EXECUTION_AUTHORIZATION_SPEC["conservative_accounting_rate_usd_per_hour"]
        != RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
        or EXECUTION_AUTHORIZATION_SPEC["provider_authority_spend_cap_usd"]
        != RESOURCE_LIMITS["provider_authority_spend_cap_usd"]
        or RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
        * RESOURCE_LIMITS["calibration_sub_watchdog_seconds"]
        / 3600
        != RESOURCE_LIMITS["max_spend_usd"]
        or RESOURCE_LIMITS["runner_max_spend_usd"]
        + RESOURCE_LIMITS["audit_reserve_spend_usd"]
        != RESOURCE_LIMITS["max_spend_usd"]
        or RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
        * RESOURCE_LIMITS["provider_deadline_seconds"]
        / 3600
        != RESOURCE_LIMITS["provider_authority_spend_cap_usd"]
    ):
        raise ValueError("provider deadline/calibration watchdog contract differs")
    if ADAPTIVE_DESIGN_INPUTS["analysis_data_inputs"]:
        raise ValueError("predecessor data may not enter v2 analysis")


validate_protocol()
