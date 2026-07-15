#!/usr/bin/env python3
"""Independently audit the pre-SAE generic-vector/J-readout machine plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_STUDY_ID = "consciousness_sae_target_blind_calibration_v2"
EXPECTED_PROTOCOL_VERSION = "consciousness_sae_target_blind_calibration_v2.0.0"
EXPECTED_CANONICAL_PLAN_RELATIVE_PATH = (
    "data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3"
)
EXPECTED_PROMPT_IDS = tuple(f"neutral_c{index:02d}" for index in range(1, 9))
EXPECTED_NEUTRAL_SYSTEM = (
    "Answer the mundane question briefly and literally. Do not add commentary."
)
EXPECTED_PROMPT_USERS = (
    "What object is commonly used to unlock a door?",
    "Which planet is closest to the Sun?",
    "What color are ripe bananas usually?",
    "Which room in a home commonly contains a bathtub?",
    "How many days are in a standard week?",
    "What handheld tool is commonly used to cut paper?",
    "Which body part is normally used for hearing sounds?",
    "What appliance turns slices of bread into toast?",
)
EXPECTED_DIRECTIONS = (0, 1, 2)
EXPECTED_DOSES = (0.01, 0.02, 0.03, 0.04, 0.08)
EXPECTED_PREDECESSOR_HASHES = {
    "STAGE_A_AUDIT.json": "3c956bd392fce2386cbba85d6841c3393a83abadc8946ac50acb17342e908a4d",
    "STAGE_A_RECEIPT.json": "a01fa3e70d1c5cfadb6e19fdc3f30557c1de25d9f77473cdfd7f8f40faa46716",
    "STAGE_A_SUMMARY.json": "ca46766cd843adc9cc047090804717894cbbd0157a3e3249cbdbca79df3d5510",
}
EXPECTED_MODEL_SPEC = {
    "repository": "meta-llama/Llama-3.3-70B-Instruct",
    "revision": "6f6073b423013f6a7d4d9f39144961bfbfbc386b",
    "dtype": "bfloat16",
    "layer_count": 80,
    "residual_width": 8192,
    "tokenizer_vocabulary_size": 128256,
}
EXPECTED_SAE_SPEC = {
    "repository": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
    "revision": "128ee921ecd1b8b3a87d776cbcc357c0855da134",
    "filename": "Llama-3.3-70B-Instruct-SAE-l50.pt",
    "sha256": "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6",
    "layer": 50,
    "feature_count": 65536,
}
EXPECTED_J_LENS_SPEC = {
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
    "source_layers": list(range(45, 79)),
    "target_layer": 79,
    "orientation": "row_residual_at_j_transpose",
}
EXPECTED_CONTAINER_IMAGE_SPEC = {
    "tag_reference": ("runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04"),
    "immutable_reference": (
        "runpod/pytorch@sha256:"
        "cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853"
    ),
}
EXPECTED_FRESH_RANDOMIZATION = {
    "seed_material": ["study_id", "protocol_version", "namespace", "coordinates"],
    "runtime_seed_namespace": "runtime-v2",
    "direction_seed_namespace": "generic-layer50-direction",
    "fixed_token_panel_seed_namespace": "fixed-token-panel-v2",
    "fixed_token_panel_size": 2_048,
    "fixed_token_panel_token_id_upper_bound_exclusive": 128_000,
    "fixed_token_panel_special_or_reserved_ids_included": False,
    "random_j_seed_namespace": "random-j-v2",
    "random_j_control_count": 5,
    "j_orientation_seed_namespace": "j-orientation-fixture-v2",
    "predecessor_randomization_reused": False,
    "predecessor_control_values_reused": False,
}
EXPECTED_J_ORIENTATION = {
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
EXPECTED_INTERVENTION_STATE_CONTRACT = {
    "schema_version": 1,
    "construct": "pre_sae_generic_vector_delivery",
    "model_repository_url": (
        "https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct/tree/"
        "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
    ),
    "model_revision": "6f6073b423013f6a7d4d9f39144961bfbfbc386b",
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
    "edited_tensor_shape": [1, 1, 8192],
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
EXPECTED_J_STATE_CONTRACT = {
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
    "release_revision": "a4114d7752d11eb546e6cf372213d7e75526d3a1",
    "checkpoint_url": (
        "https://huggingface.co/neuronpedia/jacobian-lens/resolve/"
        "a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/"
        "jlens/Salesforce-wikitext/"
        "Llama-3.3-70B-Instruct_jacobian_lens.pt"
    ),
    "checkpoint_sha256": (
        "335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03"
    ),
    "release_config_url": (
        "https://huggingface.co/neuronpedia/jacobian-lens/resolve/"
        "a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/"
        "jlens/Salesforce-wikitext/config.yaml"
    ),
    "release_config_sha256": (
        "d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5"
    ),
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
    "primary_readout_layer": 50,
    "descriptive_profile_layers": list(range(51, 79)),
}
EXPECTED_FIXED_PANEL_ESTIMAND = {
    "schema_version": 1,
    "primary_readout_layer": 50,
    "primary_dose_fraction": 0.03,
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
EXPECTED_FORWARD_INVENTORY = {
    "schema_version": 1,
    "model_forward_definition": "one_full_model_forward_invocation",
    "prefix_forwards": 8,
    "clean_continuation_forwards": 8,
    "edited_continuation_forwards": 240,
    "exact_total_model_forwards": 256,
    "orientation_fixture_model_forwards": 0,
}
EXPECTED_CLAIM_GATE_POLICY = {
    "actual_state_collection_operational_prerequisites": [
        "complete_raw_transaction",
        "independent_audit",
    ],
    "actual_state_collection_measurement_gates": [
        "hard_native_delivery",
        "requested_realized_fidelity",
        "common_mode_control",
    ],
    "actual_state_collection_non_gates": [
        "realized_source_linearity",
        "j_of_realized_linearity",
        "downstream_model_linearity",
        "j_orientation",
        "bf16_fp32_j_shadow_fidelity",
        "j_absolute_performance",
        "j_over_random",
        "j_over_identity",
    ],
    "linear_response_claim_gates": [
        "realized_source_linearity",
        "j_of_realized_linearity_for_linear_j_claims",
        "downstream_model_linearity_for_linear_downstream_claims",
    ],
    "j_projection_claim_gates": [
        "current_study_j_orientation",
        "bf16_fp32_j_shadow_fidelity",
    ],
    "j_predictive_association_claim_gates": [
        "absolute_real_j",
        "real_j_over_random",
    ],
    "j_added_value_claim_gate": "real_j_over_identity",
}
EXPECTED_EXECUTION_AUTHORIZATION = {
    "required": True,
    "issued_after_plan_and_bound_sources_are_committed": True,
    "local_head_must_equal_live_pushed_remote_commit": True,
    "plan_defining_paths_must_be_clean": True,
    "binds_plan_source_and_provider_receipt_hashes": True,
    "provider_deadline_seconds": 6 * 60 * 60,
    "campaign_sub_watchdog_seconds": 90 * 60,
    "runner_sub_watchdog_seconds": 60 * 60,
    "audit_reserve_seconds": 30 * 60,
    "calibration_sub_watchdog_seconds": 90 * 60,
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "provider_authority_spend_cap_usd": 36.0,
}
EXPECTED_INDEPENDENT_RECOMPUTATION = {
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
EXPECTED_THRESHOLDS = {
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
EXPECTED_RESOURCE_LIMITS = {
    "max_spend_usd": 9.0,
    "conservative_accounting_rate_usd_per_hour": 6.0,
    "provider_authority_spend_cap_usd": 36.0,
    "max_walltime_seconds": 90 * 60,
    "campaign_sub_watchdog_seconds": 90 * 60,
    "runner_sub_watchdog_seconds": 60 * 60,
    "audit_reserve_seconds": 30 * 60,
    "calibration_sub_watchdog_seconds": 90 * 60,
    "runner_max_spend_usd": 6.0,
    "audit_reserve_spend_usd": 3.0,
    "provider_deadline_seconds": 6 * 60 * 60,
    "expected_edited_forwards": 240,
    "expected_model_forwards": 256,
    "expected_raw_bytes_approx": 320_000_000,
    "raw_run_ceiling_bytes": 1024**3,
    "post_run_free_reserve_bytes": 64 * 1024**3,
}
EXPECTED_STORAGE_POLICY = {
    "raw_namespace": (
        "consciousness_sae_target_blind_calibration/"
        "consciousness_sae_target_blind_calibration_v2/raw"
    ),
    "raw_location": "RunPod network volume only",
    "git_allowed": "plan, compact receipts, hashes, summaries",
    "git_forbidden": "raw residuals, arithmetic tensors, raw logits",
}
REQUIRED_BOUND_SOURCES = {
    ".gitignore",
    "data/consciousness_sae_target_blind_calibration/README.md",
    "docs/consciousness_sae_target_blind_calibration/PROTOCOL.md",
    "experiments/__init__.py",
    "experiments/consciousness_readout_validation/runpod_lifecycle.py",
    "experiments/consciousness_sae_realization_validation/__init__.py",
    "experiments/consciousness_sae_realization_validation/guest_launcher.py",
    "experiments/consciousness_sae_realization_validation/protocol.py",
    "experiments/consciousness_sae_realization_validation/runpod_lifecycle_adapter.py",
    "experiments/consciousness_sae_realization_validation/runpod_orchestrator.py",
    "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    "experiments/consciousness_sae_realization_validation/runtime.py",
    "experiments/consciousness_sae_realization_validation/legacy_public_artifact_manifest.json",
    "experiments/consciousness_sae_target_blind_calibration/README.md",
    "experiments/consciousness_sae_target_blind_calibration/__init__.py",
    "experiments/consciousness_sae_target_blind_calibration/protocol.py",
    "experiments/consciousness_sae_target_blind_calibration/build_plan.py",
    "experiments/consciousness_sae_target_blind_calibration/guest_launcher.py",
    "experiments/consciousness_sae_target_blind_calibration/runner.py",
    "experiments/consciousness_sae_target_blind_calibration/audit.py",
    "experiments/consciousness_sae_target_blind_calibration/orientation.py",
    "experiments/consciousness_sae_target_blind_calibration/requirements-runpod-b200.txt",
    "experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh",
    "experiments/consciousness_sae_target_blind_calibration/review_adjudication.py",
    "experiments/consciousness_sae_target_blind_calibration/authorize.py",
    "experiments/consciousness_sae_target_blind_calibration/validate_plan.py",
}


class IndependentPlanAuditError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise IndependentPlanAuditError(f"JSON root is not an object: {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical(dict(value)) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def validate(plan_dir: Path, *, enforce_canonical_path: bool = False) -> dict[str, Any]:
    root = plan_dir.expanduser().resolve(strict=True)
    canonical = (REPO_ROOT / EXPECTED_CANONICAL_PLAN_RELATIVE_PATH).resolve()
    if enforce_canonical_path and root != canonical:
        raise IndependentPlanAuditError(
            "plan directory differs from the canonical relative path"
        )
    manifest = _json(root / "plan_manifest.json")
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256", None)
    if supplied != _sha(core):
        raise IndependentPlanAuditError("manifest self-hash differs")
    if (
        manifest.get("study_id") != EXPECTED_STUDY_ID
        or manifest.get("protocol_version") != EXPECTED_PROTOCOL_VERSION
        or manifest.get("scope") != "adaptive_target_blind_numerical_calibration_only"
        or manifest.get("study_role")
        != "pre_sae_generic_vector_delivery_and_j_readout_calibration"
        or manifest.get("canonical_plan_relative_path")
        != EXPECTED_CANONICAL_PLAN_RELATIVE_PATH
        or manifest.get("paper_prompt_render_count") != 0
        or manifest.get("target_prompt_render_count") != 0
        or manifest.get("target_feature_vector_count") != 0
        or manifest.get("analysis_data_inputs") != []
        or manifest.get("calibration_row_count") != 120
        or manifest.get("signed_edited_forward_count") != 240
        or manifest.get("exact_model_forward_count") != 256
        or manifest.get("primary_readout_layer") != 50
    ):
        raise IndependentPlanAuditError("manifest identity/count/scope differs")
    git_head = manifest.get("git_head_commit")
    if (
        not isinstance(git_head, str)
        or len(git_head) != 40
        or any(character not in "0123456789abcdef" for character in git_head)
    ):
        raise IndependentPlanAuditError("plan-build Git commit is malformed")
    records = manifest.get("files")
    expected_plan_files = {
        "protocol_snapshot.json",
        "calibration_plan.jsonl",
        "adaptive_design_inputs.json",
        "source_files.json",
    }
    if (
        not isinstance(records, list)
        or len(records) != len(expected_plan_files)
        or {row.get("path") for row in records} != expected_plan_files
    ):
        raise IndependentPlanAuditError("manifested plan file inventory differs")
    for row in records:
        path = root / str(row["path"])
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != int(row.get("bytes", -1))
            or _file_sha(path) != row.get("sha256")
        ):
            raise IndependentPlanAuditError(
                f"manifested plan file differs: {row.get('path')}"
            )

    snapshot = _json(root / "protocol_snapshot.json")
    if (
        snapshot.get("study_id") != EXPECTED_STUDY_ID
        or snapshot.get("protocol_version") != EXPECTED_PROTOCOL_VERSION
        or snapshot.get("study_role")
        != "pre_sae_generic_vector_delivery_and_j_readout_calibration"
        or snapshot.get("canonical_plan_relative_path")
        != EXPECTED_CANONICAL_PLAN_RELATIVE_PATH
        or snapshot.get("paper_or_target_prompts_included") is not False
        or snapshot.get("target_sae_features_included") is not False
        or snapshot.get("analysis_data_inputs") != []
        or snapshot.get("provider", {}).get("network_volume_id") != "bv9gb9j32y"
        or snapshot.get("provider", {}).get("data_center_id") != "US-CA-2"
        or snapshot.get("provider", {}).get("gpu_type") != "NVIDIA B200"
        or snapshot.get("provider", {}).get("gpu_count") != 1
        or snapshot.get("provider", {}).get("volume_mount_path") != "/workspace"
        or snapshot.get("edit_layer") != 50
        or snapshot.get("primary_readout_layer") != 50
        or snapshot.get("captured_j_layers") != list(range(45, 79))
        or snapshot.get("readout_transport_layers") != list(range(50, 79))
        or snapshot.get("pre_injection_zero_delta_layers") != list(range(45, 50))
        or snapshot.get("directions") != list(EXPECTED_DIRECTIONS)
        or snapshot.get("dose_grid") != list(EXPECTED_DOSES)
        or snapshot.get("diagnostic_doses") != [0.01]
        or snapshot.get("realization_gate_doses") != [0.02, 0.03, 0.04, 0.08]
        or snapshot.get("linearity_gate_doses") != [0.02, 0.03, 0.04]
        or snapshot.get("primary_dose") != 0.03
        or snapshot.get("thresholds") != EXPECTED_THRESHOLDS
        or snapshot.get("resource_limits") != EXPECTED_RESOURCE_LIMITS
        or snapshot.get("requested_realized_components") != ["plus", "minus", "central"]
        or snapshot.get("fresh_randomization") != EXPECTED_FRESH_RANDOMIZATION
        or snapshot.get("j_orientation") != EXPECTED_J_ORIENTATION
        or snapshot.get("intervention_state_contract")
        != EXPECTED_INTERVENTION_STATE_CONTRACT
        or snapshot.get("intervention_state_contract_sha256")
        != _sha(EXPECTED_INTERVENTION_STATE_CONTRACT)
        or snapshot.get("j_state_contract") != EXPECTED_J_STATE_CONTRACT
        or snapshot.get("j_state_contract_sha256") != _sha(EXPECTED_J_STATE_CONTRACT)
        or snapshot.get("fixed_panel_estimand") != EXPECTED_FIXED_PANEL_ESTIMAND
        or snapshot.get("forward_inventory") != EXPECTED_FORWARD_INVENTORY
        or snapshot.get("claim_gate_policy") != EXPECTED_CLAIM_GATE_POLICY
        or snapshot.get("execution_authorization") != EXPECTED_EXECUTION_AUTHORIZATION
        or snapshot.get("independent_recomputation")
        != EXPECTED_INDEPENDENT_RECOMPUTATION
        or snapshot.get("model") != EXPECTED_MODEL_SPEC
        or snapshot.get("sae") != EXPECTED_SAE_SPEC
        or snapshot.get("j_lens") != EXPECTED_J_LENS_SPEC
        or snapshot.get("container_image") != EXPECTED_CONTAINER_IMAGE_SPEC
        or snapshot.get("storage") != EXPECTED_STORAGE_POLICY
    ):
        raise IndependentPlanAuditError("protocol snapshot contract differs")
    expected_prompt_payloads = [
        {
            "prompt_id": prompt_id,
            "system": EXPECTED_NEUTRAL_SYSTEM,
            "user": user,
        }
        for prompt_id, user in zip(
            EXPECTED_PROMPT_IDS, EXPECTED_PROMPT_USERS, strict=True
        )
    ]
    if snapshot.get("prompt_payloads") != expected_prompt_payloads:
        raise IndependentPlanAuditError("fresh prompt inventory/payload differs")

    expected_rows = [
        {
            "prompt_id": prompt_id,
            "edit_layer": 50,
            "direction": direction,
            "dose_fraction": dose,
        }
        for prompt_id in EXPECTED_PROMPT_IDS
        for direction in EXPECTED_DIRECTIONS
        for dose in EXPECTED_DOSES
    ]
    actual_rows = [
        json.loads(line)
        for line in (root / "calibration_plan.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    if actual_rows != expected_rows:
        raise IndependentPlanAuditError("calibration plan reconstruction differs")

    adaptive = _json(root / "adaptive_design_inputs.json")
    if (
        adaptive.get("physical_file_sha256") != EXPECTED_PREDECESSOR_HASHES
        or adaptive.get("analysis_data_inputs") != []
        or adaptive.get("role") != "design_provenance_only_no_rows_loaded_or_pooled"
        or not isinstance(adaptive.get("facts_used"), list)
        or len(adaptive["facts_used"]) != 5
    ):
        raise IndependentPlanAuditError("adaptive design disclosure differs")

    source_rows = _json(root / "source_files.json").get("files")
    if (
        not isinstance(source_rows, list)
        or len(source_rows) != len(REQUIRED_BOUND_SOURCES)
        or {str(row.get("path")) for row in source_rows} != REQUIRED_BOUND_SOURCES
    ):
        raise IndependentPlanAuditError("source closure differs")
    for row in source_rows:
        path = REPO_ROOT / str(row.get("path"))
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != int(row.get("bytes", -1))
            or _file_sha(path) != row.get("sha256")
        ):
            raise IndependentPlanAuditError(f"bound source differs: {row.get('path')}")

    audit_core = {
        "schema_version": 1,
        "status": "pass",
        "study_id": EXPECTED_STUDY_ID,
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
        "plan_manifest_sha256": supplied,
        "reconstructed_calibration_row_count": len(expected_rows),
        "reconstructed_signed_edited_forward_count": len(expected_rows) * 2,
        "reconstructed_model_forward_count": 256,
        "primary_readout_layer": 50,
        "intervention_state_contract_sha256": _sha(
            EXPECTED_INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract_sha256": _sha(EXPECTED_J_STATE_CONTRACT),
        "fixed_panel_estimand_sha256": _sha(EXPECTED_FIXED_PANEL_ESTIMAND),
        "forward_inventory_sha256": _sha(EXPECTED_FORWARD_INVENTORY),
        "fresh_prompt_count": len(EXPECTED_PROMPT_IDS),
        "source_file_count": len(source_rows),
        "source_inventory_sha256": _sha(source_rows),
        "pinned_artifact_contract_sha256": _sha(
            {
                "model": EXPECTED_MODEL_SPEC,
                "sae": EXPECTED_SAE_SPEC,
                "j_lens": EXPECTED_J_LENS_SPEC,
                "container_image": EXPECTED_CONTAINER_IMAGE_SPEC,
            }
        ),
        "claim_gate_policy_sha256": _sha(EXPECTED_CLAIM_GATE_POLICY),
        "fresh_randomization_sha256": _sha(EXPECTED_FRESH_RANDOMIZATION),
        "analysis_data_inputs": [],
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
    }
    return {**audit_core, "receipt_sha256": _sha(audit_core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = validate(args.plan_dir, enforce_canonical_path=True)
    _write(args.output, receipt)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
