"""Outcome-free protocol candidate for a wide signed generic-vector dose scan.

This successor characterizes the full requested intervention curve from zero
through 30% of the clean layer-50 residual RMS in 0.5 percentage-point steps.
The nonzero magnitudes are executed as exact signed BF16 pairs.  Zero is a
single shared clean continuation per prompt, never a duplicated direction row.

The completed target-blind calibration informed this design, but its raw rows
are not loaded, pooled, or treated as observations in this successor.  This
module defines a prospectively frozen plan; it does not authorize GPU execution.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.consciousness_sae_target_blind_calibration import (
    protocol as predecessor,
)


STUDY_SLUG = "consciousness_sae_signed_dose_scan"
STUDY_ID = "consciousness_sae_signed_dose_scan_v1"
PROTOCOL_VERSION = "consciousness_sae_signed_dose_scan_v1.0.0"
PLAN_SCHEMA_VERSION = 1
CANONICAL_PLAN_RELATIVE_PATH = (
    "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716"
)

NETWORK_VOLUME_ID = predecessor.NETWORK_VOLUME_ID
DATA_CENTER_ID = predecessor.DATA_CENTER_ID
GPU_TYPE = predecessor.GPU_TYPE
VOLUME_MOUNT_PATH = predecessor.VOLUME_MOUNT_PATH

MODEL_SPEC = copy.deepcopy(predecessor.MODEL_SPEC)
SAE_SPEC = copy.deepcopy(predecessor.SAE_SPEC)
J_LENS_SPEC = copy.deepcopy(predecessor.J_LENS_SPEC)
CONTAINER_IMAGE_SPEC = copy.deepcopy(predecessor.CONTAINER_IMAGE_SPEC)
WIDTH = predecessor.WIDTH
VOCAB_SIZE = predecessor.VOCAB_SIZE
J_LAYERS = predecessor.J_LAYERS
EDIT_LAYER = predecessor.EDIT_LAYER
PRIMARY_READOUT_LAYER = EDIT_LAYER
READOUT_LAYERS = predecessor.READOUT_LAYERS
RANDOM_J_COUNT = predecessor.RANDOM_J_COUNT
TRANSPORTS = predecessor.TRANSPORTS
TOP_K = predecessor.TOP_K

# Store dose coordinates as integers.  JSON float spellings and binary float
# accumulation must never define plan membership or row identity.
DOSE_STEP_BASIS_POINTS = 50
MAX_DOSE_BASIS_POINTS = 3_000
DOSE_BASIS_POINTS = tuple(
    range(DOSE_STEP_BASIS_POINTS, MAX_DOSE_BASIS_POINTS + 1, DOSE_STEP_BASIS_POINTS)
)
DOSE_GRID = tuple(value / 10_000 for value in DOSE_BASIS_POINTS)
REPORTED_SIGNED_DOSE_BASIS_POINTS = tuple(
    range(
        -MAX_DOSE_BASIS_POINTS,
        MAX_DOSE_BASIS_POINTS + 1,
        DOSE_STEP_BASIS_POINTS,
    )
)
ZERO_DOSE_BASIS_POINTS = 0
REFERENCE_ONLINE_J_DOSE_BASIS_POINTS = 300
PRIMARY_DOSE = REFERENCE_ONLINE_J_DOSE_BASIS_POINTS / 10_000
REALIZATION_GATE_DOSES = (0.02, 0.03, 0.04, 0.08)
LINEARITY_GATE_DOSES = (0.02, 0.03, 0.04)
DIAGNOSTIC_DOSES = tuple(
    dose
    for basis_points, dose in zip(DOSE_BASIS_POINTS, DOSE_GRID)
    if basis_points not in {200, 300, 400, 800}
)
REQUESTED_REALIZED_COMPONENTS = ("plus", "minus", "central")

DIRECTIONS = predecessor.DIRECTIONS
PROMPTS = predecessor.PROMPTS
PROMPT_IDS = predecessor.PROMPT_IDS
NEUTRAL_SYSTEM = predecessor.NEUTRAL_SYSTEM

FRESH_RANDOMIZATION_SPEC = {
    "seed_material": ("study_id", "protocol_version", "namespace", "coordinates"),
    "runtime_seed_namespace": "signed-dose-scan-runtime-v1",
    "direction_seed_namespace": "signed-dose-scan-generic-layer50-direction-v1",
    "fixed_token_panel_seed_namespace": "signed-dose-scan-fixed-token-panel-v1",
    "fixed_token_panel_size": 2_048,
    "fixed_token_panel_token_id_upper_bound_exclusive": 128_000,
    "fixed_token_panel_special_or_reserved_ids_included": False,
    "random_j_seed_namespace": "signed-dose-scan-random-j-v1",
    "random_j_control_count": RANDOM_J_COUNT,
    "j_orientation_seed_namespace": "signed-dose-scan-j-orientation-v1",
    "predecessor_randomization_reused": False,
    "predecessor_control_values_reused": False,
}

J_ORIENTATION_SPEC = copy.deepcopy(predecessor.J_ORIENTATION_SPEC)
J_ORIENTATION_SPEC.update(
    {
        "fixture_seed_namespace": FRESH_RANDOMIZATION_SPEC[
            "j_orientation_seed_namespace"
        ],
        "current_study_only": True,
    }
)

GATE_THRESHOLDS = copy.deepcopy(predecessor.GATE_THRESHOLDS)

ZERO_BASELINE_CONTRACT = {
    "dose_basis_points": ZERO_DOSE_BASIS_POINTS,
    "execution": "one_clean_continuation_per_prompt",
    "direction_specific_duplicates": False,
    "signed_pair": False,
    "curve_role": "shared_origin",
}

SMALL_MODEL_PROMOTION_SPEC = {
    "role": "operational_only_smaller_model_validation",
    "required_before_large_model_authorization": True,
    "model_id": "google/gemma-2-9b-it",
    "model_revision": "11c9b309abf73637e4b6f9a3fa1e92e615547819",
    "sae_repo": "google/gemma-scope-9b-it-res",
    "sae_revision": "e86af97a5b6fbbccca28ab654f2fda1b0768f770",
    "sae_folder": "layer_20/width_16k/average_l0_91",
    "sae_feature_id": 1_295,
    "prompt_id": "neutral_calendar_continuation_v1",
    "nonzero_dose_count": 60,
    "signed_pair_count": 60,
    "edited_forward_count": 120,
    "zero_baseline_count": 1,
    "required_gates": ["structural", "numeric", "hook", "artifact_replay"],
    "promotion_scope": "runner_mechanics_only_not_scientific_protocol",
    "semantic_outcome_gate": False,
    "effect_size_gate": False,
    "dose_threshold_tuning_gate": False,
}

GENERIC_DIRECTION_SPEC = {
    "count": len(DIRECTIONS),
    "coordinates": list(DIRECTIONS),
    "generator": "numpy.random.Generator(PCG64(seed64(namespace,direction)))",
    "draw_distribution": "independent_standard_normal_float32_per_residual_coordinate",
    "residual_width": WIDTH,
    "normalization": "divide_by_sqrt_mean_square_to_unit_rms_float32",
    "seed_namespace": FRESH_RANDOMIZATION_SPEC["direction_seed_namespace"],
    "sign_orientation": "seed_committed_draw_no_posthoc_sign_flip",
    "outcome_dependent_selection": False,
    "semantic_or_sae_selection": False,
    "rejection_rule": "reject_only_nonfinite_or_zero_rms_as_mechanical_failure",
    "population_sample_claim": False,
}

PRIMARY_ACTUAL_STATE_ESTIMAND = {
    "claim": (
        "For the exact frozen three directions and eight prompts in the pinned "
        "Llama model, describe the clean-referenced continuation-token residual "
        "response at every frozen signed dose and downstream state; make no "
        "semantic or population claim."
    ),
    "panel_role": "fixed_census_not_random_population_sample",
    "edited_token": "last_rendered_generation_prompt_token_in_one_token_continuation",
    "edit_site": "explicit_post_block_50_output_pre_block_51",
    "observed_sites": [
        "explicit_post_edit_block_50_output",
        *[f"post_block_{layer}_output" for layer in range(51, 79)],
        "post_block_79_output_equal_to_final_rmsnorm_input",
    ],
    "clean_state": "h_zero[p,state]",
    "positive_state": "h_plus[p,d,b,state]",
    "negative_state": "h_minus[p,d,b,state]",
    "direction_definition": "u_d_has_unit_RMS_in_float32",
    "requested_fp32": "q_fp32=u_d*RMS(h_zero[p,block50])*b/10000",
    "requested_native": "q_bf16=BF16(q_fp32)_with_one_cast",
    "realized_plus": "e_plus=h_plus_post50-h_plus_pre50",
    "realized_minus": "e_minus=h_minus_post50-h_minus_pre50",
    "realized_central": "e=(h_plus_post50-h_minus_post50)/2",
    "requested_dose_basis_points": "b",
    "realized_dose_basis_points": "10000*RMS(e)/RMS(h_zero[p,block50])",
    "positive_clean_referenced": "B_plus=h_plus-h_zero",
    "negative_clean_referenced": "B_minus=h_minus-h_zero",
    "central": "C=(h_plus-h_minus)/2",
    "common_mode": "M=(h_plus+h_minus)/2-h_zero",
    "primary_output": (
        "one row per prompt,direction,nonzero magnitude,state containing signed "
        "branch coordinates, realized central dose, RMS(B_plus)/RMS(h_zero), "
        "RMS(B_minus)/RMS(h_zero), RMS(C)/RMS(h_zero), "
        "RMS(M)/RMS(h_zero), RMS(M)/RMS(C), and RMS(C)/RMS(e)"
    ),
    "primary_row_count": (
        len(PROMPT_IDS) * len(DIRECTIONS) * len(DOSE_BASIS_POINTS) * 30
    ),
    "shared_zero": "one executed clean origin per prompt_with_response_zero_by_definition",
    "all_coordinates_retained": True,
    "prompt_direction_curves_retained": True,
    "aggregates_role": "diagnostic_summaries_of_exact_census_only",
    "confidence_intervals_on_primary_curve": False,
    "model_forward_count_is_not_sample_size": True,
}

LARGE_MODEL_VALIDITY_HIERARCHY = {
    "transaction_integrity": {
        "requirements": [
            "complete_atomic_raw_transaction_and_manifest",
            "one_hook_fire_per_edited_forward",
            "pre_edit_equals_clean_and_layers_45_through_49_equal_clean",
            "native_bfloat16_post_edit_bytes_exact",
            "all_required_shapes_dtypes_hashes_rows_and_files_exact",
            "all_arithmetic_finite",
            "independent_archive_replay_exact_with_frozen_numeric_tolerance",
        ],
        "failure_scope": "entire_transaction_invalid_no_scientific_null_or_primary_curve",
    },
    "anchor_delivery": {
        "dose_fractions": list(REALIZATION_GATE_DOSES),
        "components": ["plus", "minus", "central"],
        "relative_rmse_max_inclusive": GATE_THRESHOLDS[
            "requested_realized_relative_rmse_max"
        ],
        "cosine_min_inclusive": GATE_THRESHOLDS["requested_realized_cosine_min"],
        "common_mode_to_central_rms_max_inclusive": GATE_THRESHOLDS[
            "common_mode_to_central_rms_max"
        ],
        "failure_scope": (
            "fixed_panel_primary_result_ineligible_and_reported_invalid_not_null; "
            "all rows remain archived and disclosed"
        ),
    },
    "diagnostic_delivery": {
        "dose_fractions": list(DIAGNOSTIC_DOSES),
        "same_numeric_thresholds_reported": True,
        "failure_scope": "row_retained_and_flagged_no_deletion_no_global_invalidation",
    },
    "local_linearity": {
        "dose_fractions": list(LINEARITY_GATE_DOSES),
        "cosine_min_inclusive": GATE_THRESHOLDS["linearity_cosine_min"],
        "slope_discrepancy_max_inclusive": GATE_THRESHOLDS[
            "linearity_slope_discrepancy_max"
        ],
        "failure_scope": "nonlinearity_is_a_descriptive_result_not_invalid_delivery",
    },
    "j_projection": {
        "orientation_cosine_min_inclusive": GATE_THRESHOLDS[
            "j_orientation_reference_cosine_min"
        ],
        "orientation_relative_rmse_max_inclusive": GATE_THRESHOLDS[
            "j_orientation_reference_relative_rmse_max"
        ],
        "bf16_fp32_cosine_min_inclusive": GATE_THRESHOLDS[
            "bf16_fp32_j_cosine_min"
        ],
        "bf16_fp32_relative_rmse_max_inclusive": GATE_THRESHOLDS[
            "bf16_fp32_j_relative_rmse_max"
        ],
        "failure_scope": "j_claims_ineligible_actual_state_curve_unaffected",
    },
    "null_interpretation": (
        "a_small_or_null_actual_state_response_is_interpretable_only_if_transaction_"
        "integrity_and_all_anchor_delivery_checks_pass"
    ),
}

EXECUTION_TRANSACTION_POLICY = {
    "full_coordinate_schedule_committed_before_execution": True,
    "outcome_inspection_during_model_transaction": False,
    "scientific_oddity_can_stop_or_replace_attempt": False,
    "early_stop_reasons": [
        "provider_or_campaign_watchdog_expired",
        "storage_ceiling_or_free_reserve_failed",
        "dependency_or_pinned_artifact_mismatch",
        "nonfinite_arithmetic",
        "hook_or_replay_or_manifest_integrity_failure",
        "infrastructure_or_io_failure",
    ],
    "partial_attempt_status": "aborted_incomplete_invalid_retained_and_disclosed",
    "same_authorization_retry_permitted": False,
    "retry_requires": (
        "new_user_in_scope_authority_new_review_adjudicated_if_plan_changes_new_"
        "short_lived_authorization_and_fresh_run_id"
    ),
    "retry_reasons": "enumerated_mechanical_failure_only_never_scientific_outcome",
    "canonical_attempt_rule": "first_complete_independently_audited_atomic_transaction",
    "all_attempts_linked_and_disclosed": True,
    "incomplete_campaign_reporting": (
        "report_incomplete_with_attempt_receipt_and_no_primary_or_selected_subset_summary"
    ),
}

RANDOM_J_CONTROL_SPEC = {
    "count": RANDOM_J_COUNT,
    "generator": "fresh_seeded_signed_permutation_of_each_frozen_learned_J",
    "seed_namespace": FRESH_RANDOMIZATION_SPEC["random_j_seed_namespace"],
    "coordinates": "layer_and_control_index_zero_through_four",
    "comparison_scope": "only_these_exact_five_fixed_controls_at_the_3_percent_reference",
    "distributional_random_j_superiority_claim": False,
}

INTENDED_USE_POLICY = {
    "current_use": (
        "diagnose_signed_intervention_mechanics_and_generate_safe_range_hypotheses_"
        "for_a_separately_reviewed_future_semantic_or_SAE_study"
    ),
    "preferred_dose_selected_by_this_scan": False,
    "future_dose_rule_requires_separate_prospective_review": True,
}

DOSE_CURVE_ESTIMAND = {
    "status": "exploratory_full_curve",
    "requested_axis": "signed_residual_rms_basis_points",
    "realized_axis_also_reported": True,
    "nonzero_magnitudes": list(DOSE_BASIS_POINTS),
    "signed_branches": ["minus", "plus"],
    "zero_baseline": ZERO_BASELINE_CONTRACT,
    "components_reported_separately": ["plus", "minus", "central", "common_mode"],
    "all_grid_points_reported": True,
    "favorable_dose_selection": False,
    "dose_failure_deletion": False,
    "population_generalization_claim": False,
    "high_dose_role": "stress_regime_not_gentle_steering",
}

REFERENCE_ONLINE_J_READOUT = {
    "dose_basis_points": REFERENCE_ONLINE_J_DOSE_BASIS_POINTS,
    "dose_fraction": REFERENCE_ONLINE_J_DOSE_BASIS_POINTS / 10_000,
    "role": "storage_bounded_reference_not_privileged_curve_endpoint",
    "layers": list(READOUT_LAYERS),
    "transports": list(TRANSPORTS),
    "fixed_token_count": 2_048,
    "cannot_rescue_or_replace_actual_state_curve": True,
}

FIXED_PANEL_ESTIMAND = copy.deepcopy(predecessor.FIXED_PANEL_ESTIMAND)
FIXED_PANEL_ESTIMAND.update(
    {
        "primary_readout_layer": PRIMARY_READOUT_LAYER,
        "primary_dose_fraction": PRIMARY_DOSE,
        "other_readout_layers_role": "descriptive_profile_only_no_eligibility_gate",
        "full_dose_curve_role": "actual_state_exploratory_all_points_reported",
        "reference_j_role": "storage_bounded_secondary_diagnostic",
        "across_layer_selection": False,
        "across_dose_selection": False,
    }
)

INTERVENTION_STATE_CONTRACT = copy.deepcopy(predecessor.INTERVENTION_STATE_CONTRACT)
INTERVENTION_STATE_CONTRACT.update(
    {
        "construct": "generic_vector_signed_residual_rms_dose_scan",
        "dose_coordinate": "integer_basis_points_of_clean_layer50_source_rms",
        "nonzero_dose_basis_points": list(DOSE_BASIS_POINTS),
        "zero_dose_role": ZERO_BASELINE_CONTRACT,
    }
)
J_STATE_CONTRACT = copy.deepcopy(predecessor.J_STATE_CONTRACT)
J_STATE_CONTRACT.update(
    {
        "curve_role": "secondary_descriptive_transport",
        "reference_online_j_dose_basis_points": REFERENCE_ONLINE_J_DOSE_BASIS_POINTS,
        "actual_residual_arcs_are_primary_archive": True,
    }
)

PAIR_COUNT = len(PROMPT_IDS) * len(DIRECTIONS) * len(DOSE_BASIS_POINTS)
EDITED_FORWARD_COUNT = 2 * PAIR_COUNT
FORWARD_INVENTORY = {
    "schema_version": 1,
    "model_forward_definition": "one_full_model_forward_invocation",
    "prefix_forwards": len(PROMPT_IDS),
    "clean_continuation_forwards": len(PROMPT_IDS),
    "edited_continuation_forwards": EDITED_FORWARD_COUNT,
    "exact_total_model_forwards": (
        2 * len(PROMPT_IDS) + EDITED_FORWARD_COUNT
    ),
    "orientation_fixture_model_forwards": 0,
}

RUNNER_WATCHDOG_SECONDS = 60 * 60
AUDIT_RESERVE_SECONDS = 30 * 60
CAMPAIGN_WATCHDOG_SECONDS = RUNNER_WATCHDOG_SECONDS + AUDIT_RESERVE_SECONDS
PROVIDER_DEADLINE_SECONDS = 6 * 60 * 60

CLAIM_GATE_POLICY = {
    "full_curve_role": "exploratory_all_points_reported_no_dose_selection",
    "actual_state_collection_operational_prerequisites": (
        "complete_raw_transaction",
        "independent_audit",
    ),
    "actual_state_collection_measurement_gates": (
        "hard_native_delivery",
        "requested_realized_fidelity_at_prespecified_gate_doses",
        "common_mode_control_at_prespecified_gate_doses",
    ),
    "realization_gate_doses": REALIZATION_GATE_DOSES,
    "diagnostic_non_gating_doses": DIAGNOSTIC_DOSES,
    "diagnostic_failures_delete_rows": False,
    "j_projection_claim_gates": (
        "current_study_j_orientation",
        "bf16_fp32_j_shadow_fidelity",
    ),
    "reference_j_role": "secondary_descriptive_cannot_rescue_actual_state_curve",
    "population_generalization_claim": False,
}

INDEPENDENT_RECOMPUTATION_SPEC = {
    "full_model_forward_required": False,
    "pinned_model_weights_required": True,
    "j_lens_checkpoint_required": True,
    "rehash_manifested_raw_files": True,
    "rehash_bound_plan_sources": True,
    "rehash_pinned_public_artifacts_before_model_load": True,
    "reconstruct_signed_realized_edits_from_pre_post_arcs": True,
    "recompute_every_nonzero_magnitude_and_shared_zero": True,
    "recompute_request_fidelity_common_mode_and_realized_dose": True,
    "recompute_reference_transport_from_archived_tensors": True,
    "reject_unmanifested_missing_duplicate_nonfinite_or_partial_data": True,
}

RESOURCE_LIMITS = {
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "provider_deadline_seconds": PROVIDER_DEADLINE_SECONDS,
    "provider_authority_spend_cap_usd": 36.0,
    "runner_sub_watchdog_seconds": RUNNER_WATCHDOG_SECONDS,
    "audit_reserve_seconds": AUDIT_RESERVE_SECONDS,
    "campaign_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "calibration_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "max_walltime_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "max_spend_usd": 9.0,
    "runner_max_spend_usd": 6.0,
    "audit_reserve_spend_usd": 3.0,
    "expected_signed_pairs": PAIR_COUNT,
    "expected_edited_forwards": EDITED_FORWARD_COUNT,
    "expected_model_forwards": FORWARD_INVENTORY["exact_total_model_forwards"],
    "expected_raw_bytes_approx": 2_300_000_000,
    "raw_run_ceiling_bytes": 4 * 1024**3,
    "post_run_free_reserve_bytes": 64 * 1024**3,
}

EXECUTION_AUTHORIZATION_SPEC = {
    "required": True,
    "candidate_currently_authorized": False,
    "issued_only_after_runner_audit_plan_review_and_tests_are_frozen": True,
    "local_head_must_equal_live_pushed_remote_commit": True,
    "plan_defining_paths_must_be_clean": True,
    "binds_plan_source_provider_and_review_receipt_hashes": True,
    "provider_deadline_seconds": PROVIDER_DEADLINE_SECONDS,
    "campaign_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "runner_sub_watchdog_seconds": RUNNER_WATCHDOG_SECONDS,
    "audit_reserve_seconds": AUDIT_RESERVE_SECONDS,
    "calibration_sub_watchdog_seconds": CAMPAIGN_WATCHDOG_SECONDS,
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "campaign_spend_cap_usd": 9.0,
    "provider_authority_spend_cap_usd": 36.0,
}

PREDECESSOR_RESULT_INDEX = (
    "docs/consciousness_sae_target_blind_calibration/results/"
    "calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/RESULT_SUMMARY.json"
)
DESIGN_PROVENANCE = {
    "role": "design_provenance_only_no_rows_loaded_or_pooled",
    "predecessor_study_id": predecessor.STUDY_ID,
    "predecessor_run_id": "calv2-r3-1a16572-20260715T002344Z",
    "predecessor_result_index": PREDECESSOR_RESULT_INDEX,
    "predecessor_result_index_file_sha256": (
        "35cc3aa2f94bc7b78d592eb30f3b1137042a30ed33ebb9276b0625fea0083cf7"
    ),
    "facts_used": [
        "one-percent requested-direction fidelity failed in all 24 predecessor rows",
        "two-through-eight-percent predecessor edits passed delivery",
        "the predecessor downstream response was nonlinear over two/three/four percent",
        "the learned J did not establish residual-space added value over identity",
        "the user prospectively requested a zero-through-thirty-percent half-point scan",
    ],
    "raw_data_inputs": [],
    "analysis_data_inputs": [],
    "predecessor_rows_loaded": 0,
}
ADAPTIVE_DESIGN_INPUTS = DESIGN_PROVENANCE

STORAGE_POLICY = {
    "raw_namespace": f"{STUDY_SLUG}/{STUDY_ID}/raw",
    "raw_location": "RunPod network volume only",
    "raw_transaction_is_new": True,
    "predecessor_raw_namespace_is_input": False,
    "git_allowed": "plan, source, documentation, compact receipts, hashes, summaries",
    "git_forbidden": "raw residuals, arithmetic tensors, logits, row data, runtime logs",
    "archive_policy": (
        "complete signed residual arcs at every magnitude; online full J transport only "
        "at the 300-basis-point reference; arbitrary later replay from raw arcs"
    ),
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
        raise KeyError(f"unknown dose-scan prompt: {prompt_id}")
    return {"system": NEUTRAL_SYSTEM, "user": prompts[prompt_id]}


def dose_fraction(dose_basis_points: int) -> float:
    if dose_basis_points not in DOSE_BASIS_POINTS:
        raise ValueError("dose is outside the frozen nonzero grid")
    return dose_basis_points / 10_000


def rows() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "prompt_id": prompt_id,
            "edit_layer": EDIT_LAYER,
            "direction": direction,
            "dose_basis_points": dose_basis_points,
            "dose_fraction": dose_fraction(dose_basis_points),
        }
        for prompt_id in PROMPT_IDS
        for direction in DIRECTIONS
        for dose_basis_points in DOSE_BASIS_POINTS
    )


def protocol_snapshot() -> dict[str, Any]:
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "status": "prospective_execution_requires_review_freeze_and_small_model_gate",
        "execution_authorized": False,
        "study_slug": STUDY_SLUG,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "scope": "exploratory_target_blind_generic_vector_signed_dose_curve",
        "canonical_plan_relative_path": CANONICAL_PLAN_RELATIVE_PATH,
        "paper_or_target_prompts_included": False,
        "target_sae_features_included": False,
        "generic_vector_scan": True,
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
        "directions": list(DIRECTIONS),
        "edit_layer": EDIT_LAYER,
        "captured_j_layers": list(J_LAYERS),
        "dose_step_basis_points": DOSE_STEP_BASIS_POINTS,
        "max_dose_basis_points": MAX_DOSE_BASIS_POINTS,
        "nonzero_dose_basis_points": list(DOSE_BASIS_POINTS),
        "reported_signed_dose_basis_points": list(
            REPORTED_SIGNED_DOSE_BASIS_POINTS
        ),
        "zero_baseline": ZERO_BASELINE_CONTRACT,
        "small_model_promotion": SMALL_MODEL_PROMOTION_SPEC,
        "generic_directions": GENERIC_DIRECTION_SPEC,
        "primary_actual_state_estimand": PRIMARY_ACTUAL_STATE_ESTIMAND,
        "large_model_validity_hierarchy": LARGE_MODEL_VALIDITY_HIERARCHY,
        "execution_transaction_policy": EXECUTION_TRANSACTION_POLICY,
        "random_j_controls": RANDOM_J_CONTROL_SPEC,
        "intended_use": INTENDED_USE_POLICY,
        "dose_curve_estimand": DOSE_CURVE_ESTIMAND,
        "reference_online_j_readout": REFERENCE_ONLINE_J_READOUT,
        "fixed_panel_estimand": FIXED_PANEL_ESTIMAND,
        "fresh_randomization": FRESH_RANDOMIZATION_SPEC,
        "j_orientation": J_ORIENTATION_SPEC,
        "intervention_state_contract": INTERVENTION_STATE_CONTRACT,
        "intervention_state_contract_sha256": canonical_sha256(
            INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract": J_STATE_CONTRACT,
        "j_state_contract_sha256": canonical_sha256(J_STATE_CONTRACT),
        "forward_inventory": FORWARD_INVENTORY,
        "requested_realized_components": list(REQUESTED_REALIZED_COMPONENTS),
        "diagnostic_doses": list(DIAGNOSTIC_DOSES),
        "realization_gate_doses": list(REALIZATION_GATE_DOSES),
        "linearity_gate_doses": list(LINEARITY_GATE_DOSES),
        "primary_dose": PRIMARY_DOSE,
        "primary_readout_layer": PRIMARY_READOUT_LAYER,
        "thresholds": GATE_THRESHOLDS,
        "claim_gate_policy": CLAIM_GATE_POLICY,
        "execution_authorization": EXECUTION_AUTHORIZATION_SPEC,
        "independent_recomputation": INDEPENDENT_RECOMPUTATION_SPEC,
        "resource_limits": RESOURCE_LIMITS,
        "design_provenance": DESIGN_PROVENANCE,
        "analysis_data_inputs": [],
        "storage": STORAGE_POLICY,
    }


def validate_protocol() -> None:
    expected_bps = tuple(range(50, 3_001, 50))
    if DOSE_BASIS_POINTS != expected_bps or len(DOSE_BASIS_POINTS) != 60:
        raise ValueError("signed dose magnitude grid differs")
    if 0 in DOSE_BASIS_POINTS or REPORTED_SIGNED_DOSE_BASIS_POINTS[60] != 0:
        raise ValueError("zero-dose baseline contract differs")
    if REPORTED_SIGNED_DOSE_BASIS_POINTS != tuple(range(-3_000, 3_001, 50)):
        raise ValueError("reported signed grid differs")
    if REFERENCE_ONLINE_J_DOSE_BASIS_POINTS not in DOSE_BASIS_POINTS:
        raise ValueError("reference online J dose is outside the grid")
    if len(rows()) != 1_440 or PAIR_COUNT != 1_440:
        raise ValueError("dose-scan pair inventory differs")
    if (
        EDITED_FORWARD_COUNT != 2_880
        or FORWARD_INVENTORY["exact_total_model_forwards"] != 2_896
        or RESOURCE_LIMITS["expected_model_forwards"] != 2_896
    ):
        raise ValueError("dose-scan forward inventory differs")
    if ZERO_BASELINE_CONTRACT != {
        "dose_basis_points": 0,
        "execution": "one_clean_continuation_per_prompt",
        "direction_specific_duplicates": False,
        "signed_pair": False,
        "curve_role": "shared_origin",
    }:
        raise ValueError("zero-dose execution differs")
    if (
        SMALL_MODEL_PROMOTION_SPEC["nonzero_dose_count"]
        != len(DOSE_BASIS_POINTS)
        or SMALL_MODEL_PROMOTION_SPEC["signed_pair_count"]
        != len(DOSE_BASIS_POINTS)
        or SMALL_MODEL_PROMOTION_SPEC["edited_forward_count"]
        != 2 * len(DOSE_BASIS_POINTS)
        or SMALL_MODEL_PROMOTION_SPEC["zero_baseline_count"] != 1
        or SMALL_MODEL_PROMOTION_SPEC["required_gates"]
        != ["structural", "numeric", "hook", "artifact_replay"]
        or any(
            SMALL_MODEL_PROMOTION_SPEC[key]
            for key in (
                "semantic_outcome_gate",
                "effect_size_gate",
                "dose_threshold_tuning_gate",
            )
        )
    ):
        raise ValueError("small-model promotion boundary differs")
    if (
        GENERIC_DIRECTION_SPEC["count"] != len(DIRECTIONS)
        or GENERIC_DIRECTION_SPEC["seed_namespace"]
        != FRESH_RANDOMIZATION_SPEC["direction_seed_namespace"]
        or GENERIC_DIRECTION_SPEC["outcome_dependent_selection"] is not False
        or PRIMARY_ACTUAL_STATE_ESTIMAND["primary_row_count"] != PAIR_COUNT * 30
        or PRIMARY_ACTUAL_STATE_ESTIMAND["panel_role"]
        != "fixed_census_not_random_population_sample"
        or LARGE_MODEL_VALIDITY_HIERARCHY["anchor_delivery"]["dose_fractions"]
        != list(REALIZATION_GATE_DOSES)
        or EXECUTION_TRANSACTION_POLICY["same_authorization_retry_permitted"]
        is not False
        or EXECUTION_TRANSACTION_POLICY[
            "scientific_oddity_can_stop_or_replace_attempt"
        ]
        is not False
        or RANDOM_J_CONTROL_SPEC["count"] != RANDOM_J_COUNT
        or INTENDED_USE_POLICY["preferred_dose_selected_by_this_scan"] is not False
    ):
        raise ValueError("review-repair scientific boundary differs")
    if DESIGN_PROVENANCE["analysis_data_inputs"] or DESIGN_PROVENANCE["raw_data_inputs"]:
        raise ValueError("predecessor rows may not enter successor analysis")
    if STORAGE_POLICY["raw_namespace"] == (
        "consciousness_sae_target_blind_calibration/"
        "consciousness_sae_target_blind_calibration_v2/raw"
    ):
        raise ValueError("successor raw namespace collides with predecessor")
    if not all(
        value.startswith("signed-dose-scan-")
        for key, value in FRESH_RANDOMIZATION_SPEC.items()
        if key.endswith("_namespace")
    ):
        raise ValueError("successor randomization namespace is not fresh")
    if (
        RESOURCE_LIMITS["expected_raw_bytes_approx"]
        >= RESOURCE_LIMITS["raw_run_ceiling_bytes"]
        or RESOURCE_LIMITS["runner_sub_watchdog_seconds"]
        + RESOURCE_LIMITS["audit_reserve_seconds"]
        != RESOURCE_LIMITS["campaign_sub_watchdog_seconds"]
    ):
        raise ValueError("resource envelope differs")
    if (
        PRIMARY_DOSE != 0.03
        or PRIMARY_READOUT_LAYER != 50
        or set(DIAGNOSTIC_DOSES) & set(REALIZATION_GATE_DOSES)
        or set(DIAGNOSTIC_DOSES) | set(REALIZATION_GATE_DOSES) != set(DOSE_GRID)
        or not set(LINEARITY_GATE_DOSES) <= set(REALIZATION_GATE_DOSES)
        or REQUESTED_REALIZED_COMPONENTS != ("plus", "minus", "central")
        or J_ORIENTATION_SPEC["fixture_seed_namespace"]
        != FRESH_RANDOMIZATION_SPEC["j_orientation_seed_namespace"]
    ):
        raise ValueError("runner compatibility contract differs")
    if (
        RESOURCE_LIMITS["max_spend_usd"]
        > RESOURCE_LIMITS["provider_authority_spend_cap_usd"]
        or RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
        * RESOURCE_LIMITS["campaign_sub_watchdog_seconds"]
        / 3600
        != RESOURCE_LIMITS["max_spend_usd"]
        or RESOURCE_LIMITS["conservative_accounting_rate_usd_per_hour"]
        * RESOURCE_LIMITS["provider_deadline_seconds"]
        / 3600
        != RESOURCE_LIMITS["provider_authority_spend_cap_usd"]
    ):
        raise ValueError("spend authority differs")


validate_protocol()
