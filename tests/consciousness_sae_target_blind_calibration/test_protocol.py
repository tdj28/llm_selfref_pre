from __future__ import annotations

import json

import pytest

from experiments.consciousness_sae_target_blind_calibration import (
    build_plan,
    protocol,
    validate_plan,
)


def test_protocol_has_separate_adaptive_identity_and_exact_grid() -> None:
    assert protocol.STUDY_ID == "consciousness_sae_target_blind_calibration_v2"
    assert protocol.EDIT_LAYER == 50
    assert protocol.PRIMARY_READOUT_LAYER == 50
    assert protocol.DOSE_GRID == (0.01, 0.02, 0.03, 0.04, 0.08)
    assert protocol.DIAGNOSTIC_DOSES == (0.01,)
    assert protocol.REALIZATION_GATE_DOSES == (0.02, 0.03, 0.04, 0.08)
    assert protocol.LINEARITY_GATE_DOSES == (0.02, 0.03, 0.04)
    assert len(protocol.rows()) == 120
    assert protocol.RESOURCE_LIMITS["expected_model_forwards"] == 256
    assert protocol.FORWARD_INVENTORY == {
        "schema_version": 1,
        "model_forward_definition": "one_full_model_forward_invocation",
        "prefix_forwards": 8,
        "clean_continuation_forwards": 8,
        "edited_continuation_forwards": 240,
        "exact_total_model_forwards": 256,
        "orientation_fixture_model_forwards": 0,
    }
    assert protocol.ADAPTIVE_DESIGN_INPUTS["analysis_data_inputs"] == []
    snapshot = protocol.protocol_snapshot()
    assert snapshot["target_sae_features_included"] is False
    assert snapshot["study_role"] == (
        "pre_sae_generic_vector_delivery_and_j_readout_calibration"
    )
    assert snapshot["requested_realized_components"] == ["plus", "minus", "central"]
    assert snapshot["claim_gate_policy"][
        "actual_state_collection_measurement_gates"
    ] == (
        "hard_native_delivery",
        "requested_realized_fidelity",
        "common_mode_control",
    )
    non_gates = set(snapshot["claim_gate_policy"]["actual_state_collection_non_gates"])
    assert {
        "realized_source_linearity",
        "j_orientation",
        "bf16_fp32_j_shadow_fidelity",
        "j_over_identity",
    } <= non_gates
    assert snapshot["claim_gate_policy"]["j_projection_claim_gates"] == (
        "current_study_j_orientation",
        "bf16_fp32_j_shadow_fidelity",
    )

    intervention = snapshot["intervention_state_contract"]
    assert intervention["continuation_token_index"] == "token_ids[-1]"
    assert intervention["hook_boundary"] == (
        "zero_based_block_50_output_post_block_pre_block_51"
    )
    assert intervention["edited_tensor_shape"] == [1, 1, 8192]
    assert (
        intervention["prefix_cache_contract"][
            "branch_cache_objects_are_independent_clones"
        ]
        is True
    )
    assert snapshot["intervention_state_contract_sha256"] == (
        protocol.canonical_sha256(intervention)
    )

    j_state = snapshot["j_state_contract"]
    assert j_state["primary_source_coordinate"] == (
        "explicit_post_edit_block_50_output"
    )
    assert j_state["release_target_layer_default"] == 79
    assert j_state["checkpoint_sha256"] == protocol.J_LENS_SPEC["sha256"]
    assert snapshot["j_state_contract_sha256"] == protocol.canonical_sha256(j_state)

    estimand = snapshot["fixed_panel_estimand"]
    assert estimand["primary_readout_layer"] == 50
    assert estimand["population_generalization_claim"] is False
    assert estimand["other_readout_layers_role"] == (
        "descriptive_profile_only_no_eligibility_gate"
    )
    assert estimand["across_layer_selection"] is False


def test_protocol_freezes_fresh_controls_authorization_and_resource_window() -> None:
    snapshot = protocol.protocol_snapshot()
    fresh = snapshot["fresh_randomization"]
    assert fresh["runtime_seed_namespace"] == "runtime-v2"
    assert fresh["fixed_token_panel_seed_namespace"] == "fixed-token-panel-v2"
    assert fresh["fixed_token_panel_token_id_upper_bound_exclusive"] == 128_000
    assert fresh["fixed_token_panel_special_or_reserved_ids_included"] is False
    assert fresh["random_j_seed_namespace"] == "random-j-v2"
    assert fresh["j_orientation_seed_namespace"] == "j-orientation-fixture-v2"
    assert fresh["predecessor_randomization_reused"] is False
    assert fresh["predecessor_control_values_reused"] is False
    assert snapshot["j_orientation"]["current_study_only"] is True

    limits = snapshot["resource_limits"]
    assert limits["calibration_sub_watchdog_seconds"] == 90 * 60
    assert limits["campaign_sub_watchdog_seconds"] == 90 * 60
    assert limits["runner_sub_watchdog_seconds"] == 60 * 60
    assert limits["audit_reserve_seconds"] == 30 * 60
    assert (
        limits["runner_sub_watchdog_seconds"] + limits["audit_reserve_seconds"]
        == limits["campaign_sub_watchdog_seconds"]
    )
    assert limits["runner_max_spend_usd"] == 6.0
    assert limits["audit_reserve_spend_usd"] == 3.0
    assert limits["provider_deadline_seconds"] == 6 * 60 * 60
    assert limits["conservative_accounting_rate_usd_per_hour"] == 6.0
    assert limits["max_spend_usd"] == 9.0
    assert limits["provider_authority_spend_cap_usd"] == 36.0
    assert limits["expected_raw_bytes_approx"] == 320_000_000
    assert (
        limits["calibration_sub_watchdog_seconds"] < limits["provider_deadline_seconds"]
    )

    authorization = snapshot["execution_authorization"]
    assert authorization["issued_after_plan_and_bound_sources_are_committed"] is True
    assert authorization["local_head_must_equal_live_pushed_remote_commit"] is True
    assert authorization["plan_defining_paths_must_be_clean"] is True
    assert authorization["runner_sub_watchdog_seconds"] == 60 * 60
    assert authorization["audit_reserve_seconds"] == 30 * 60
    recomputation = snapshot["independent_recomputation"]
    assert recomputation["full_model_forward_required"] is False
    assert recomputation["pinned_model_weights_required"] is True
    assert recomputation["j_lens_checkpoint_required"] is True


def test_build_plan_binds_sources_and_has_no_target_rows(tmp_path, monkeypatch) -> None:
    assert set(build_plan.SOURCE_PATHS) == validate_plan.REQUIRED_BOUND_SOURCES
    monkeypatch.setattr(build_plan, "_git_head", lambda: "a" * 40)
    output = tmp_path / "plan"
    manifest_path = build_plan.build(output)
    manifest = json.loads(manifest_path.read_text())
    core = dict(manifest)
    supplied = core.pop("plan_manifest_sha256")
    assert supplied == protocol.canonical_sha256(core)
    assert manifest["calibration_row_count"] == 120
    assert manifest["signed_edited_forward_count"] == 240
    assert manifest["exact_model_forward_count"] == 256
    assert manifest["primary_readout_layer"] == 50
    assert manifest["target_prompt_render_count"] == 0
    assert manifest["target_feature_vector_count"] == 0
    assert manifest["analysis_data_inputs"] == []
    assert (
        len(
            json.loads((output / "protocol_snapshot.json").read_text())[
                "prompt_payloads"
            ]
        )
        == 8
    )
    audit = validate_plan.validate(output)
    assert audit["status"] == "pass"
    assert audit["reconstructed_model_forward_count"] == 256
    assert audit["source_file_count"] == len(validate_plan.REQUIRED_BOUND_SOURCES)
    assert len(audit["source_inventory_sha256"]) == 64
    assert len(audit["pinned_artifact_contract_sha256"]) == 64
    assert len(audit["claim_gate_policy_sha256"]) == 64
    assert len(audit["fresh_randomization_sha256"]) == 64
    assert audit["primary_readout_layer"] == 50
    assert len(audit["intervention_state_contract_sha256"]) == 64
    assert len(audit["j_state_contract_sha256"]) == 64
    assert len(audit["fixed_panel_estimand_sha256"]) == 64
    assert len(audit["forward_inventory_sha256"]) == 64


def test_independent_validator_rejects_collection_gate_drift(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(build_plan, "_git_head", lambda: "b" * 40)
    output = tmp_path / "plan"
    build_plan.build(output)

    snapshot_path = output / "protocol_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["claim_gate_policy"]["actual_state_collection_measurement_gates"].append(
        "realized_source_linearity"
    )
    snapshot_path.write_bytes(protocol.canonical_json_bytes(snapshot) + b"\n")

    manifest_path = output / "plan_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        if row["path"] == "protocol_snapshot.json":
            row["bytes"] = snapshot_path.stat().st_size
            row["sha256"] = protocol.sha256_file(snapshot_path)
    core = dict(manifest)
    core.pop("plan_manifest_sha256")
    manifest["plan_manifest_sha256"] = protocol.canonical_sha256(core)
    manifest_path.write_bytes(protocol.canonical_json_bytes(manifest) + b"\n")

    with pytest.raises(
        validate_plan.IndependentPlanAuditError,
        match="protocol snapshot contract differs",
    ):
        validate_plan.validate(output)
