from __future__ import annotations

from experiments.consciousness_sae_signed_dose_scan import protocol


def test_protocol_freezes_exact_integer_grid_and_shared_zero() -> None:
    protocol.validate_protocol()
    assert protocol.STUDY_ID == "consciousness_sae_signed_dose_scan_v1"
    assert protocol.DOSE_STEP_BASIS_POINTS == 50
    assert protocol.MAX_DOSE_BASIS_POINTS == 3_000
    assert protocol.DOSE_BASIS_POINTS == tuple(range(50, 3_001, 50))
    assert len(protocol.DOSE_BASIS_POINTS) == 60
    assert 0 not in protocol.DOSE_BASIS_POINTS
    assert protocol.REPORTED_SIGNED_DOSE_BASIS_POINTS == tuple(
        range(-3_000, 3_001, 50)
    )
    assert len(protocol.REPORTED_SIGNED_DOSE_BASIS_POINTS) == 121
    assert protocol.REPORTED_SIGNED_DOSE_BASIS_POINTS[60] == 0
    assert protocol.ZERO_BASELINE_CONTRACT == {
        "dose_basis_points": 0,
        "execution": "one_clean_continuation_per_prompt",
        "direction_specific_duplicates": False,
        "signed_pair": False,
        "curve_role": "shared_origin",
    }


def test_protocol_freezes_row_order_and_forward_inventory() -> None:
    rows = protocol.rows()
    assert len(rows) == 1_440
    assert rows[0] == {
        "prompt_id": "neutral_c01",
        "edit_layer": 50,
        "direction": 0,
        "dose_basis_points": 50,
        "dose_fraction": 0.005,
    }
    assert rows[59]["dose_basis_points"] == 3_000
    assert rows[60]["direction"] == 1
    assert rows[-1] == {
        "prompt_id": "neutral_c08",
        "edit_layer": 50,
        "direction": 2,
        "dose_basis_points": 3_000,
        "dose_fraction": 0.3,
    }
    assert len({
        (row["prompt_id"], row["direction"], row["dose_basis_points"])
        for row in rows
    }) == len(rows)
    assert protocol.PAIR_COUNT == 1_440
    assert protocol.EDITED_FORWARD_COUNT == 2_880
    assert protocol.FORWARD_INVENTORY == {
        "schema_version": 1,
        "model_forward_definition": "one_full_model_forward_invocation",
        "prefix_forwards": 8,
        "clean_continuation_forwards": 8,
        "edited_continuation_forwards": 2_880,
        "exact_total_model_forwards": 2_896,
        "orientation_fixture_model_forwards": 0,
    }


def test_snapshot_is_target_blind_exploratory_and_keeps_every_point() -> None:
    snapshot = protocol.protocol_snapshot()
    assert snapshot["status"] == (
        "prospective_execution_requires_review_freeze_and_small_model_gate"
    )
    assert snapshot["execution_authorized"] is False
    assert snapshot["paper_or_target_prompts_included"] is False
    assert snapshot["target_sae_features_included"] is False
    assert snapshot["generic_vector_scan"] is True
    assert snapshot["analysis_data_inputs"] == []
    assert snapshot["dose_curve_estimand"]["status"] == "exploratory_full_curve"
    assert snapshot["dose_curve_estimand"]["all_grid_points_reported"] is True
    assert snapshot["dose_curve_estimand"]["favorable_dose_selection"] is False
    assert snapshot["dose_curve_estimand"]["dose_failure_deletion"] is False
    assert snapshot["dose_curve_estimand"]["population_generalization_claim"] is False
    assert snapshot["reference_online_j_readout"]["dose_basis_points"] == 300
    assert (
        snapshot["reference_online_j_readout"][
            "cannot_rescue_or_replace_actual_state_curve"
        ]
        is True
    )


def test_successor_has_fresh_controls_and_distinct_storage() -> None:
    snapshot = protocol.protocol_snapshot()
    fresh = snapshot["fresh_randomization"]
    for key in (
        "runtime_seed_namespace",
        "direction_seed_namespace",
        "fixed_token_panel_seed_namespace",
        "random_j_seed_namespace",
        "j_orientation_seed_namespace",
    ):
        assert fresh[key].startswith("signed-dose-scan-")
    assert fresh["predecessor_randomization_reused"] is False
    assert fresh["predecessor_control_values_reused"] is False
    assert snapshot["storage"] == protocol.STORAGE_POLICY
    assert snapshot["storage"]["raw_transaction_is_new"] is True
    assert snapshot["storage"]["predecessor_raw_namespace_is_input"] is False
    assert snapshot["storage"]["raw_namespace"] == (
        "consciousness_sae_signed_dose_scan/"
        "consciousness_sae_signed_dose_scan_v1/raw"
    )
    provenance = snapshot["design_provenance"]
    assert provenance["role"] == "design_provenance_only_no_rows_loaded_or_pooled"
    assert provenance["raw_data_inputs"] == []
    assert provenance["analysis_data_inputs"] == []
    assert provenance["predecessor_rows_loaded"] == 0


def test_gate_doses_do_not_hide_diagnostics_or_change_exploratory_scope() -> None:
    assert protocol.PRIMARY_DOSE == 0.03
    assert protocol.REALIZATION_GATE_DOSES == (0.02, 0.03, 0.04, 0.08)
    assert protocol.LINEARITY_GATE_DOSES == (0.02, 0.03, 0.04)
    assert set(protocol.DIAGNOSTIC_DOSES).isdisjoint(
        protocol.REALIZATION_GATE_DOSES
    )
    assert set(protocol.DIAGNOSTIC_DOSES) | set(
        protocol.REALIZATION_GATE_DOSES
    ) == set(protocol.DOSE_GRID)
    assert 0.005 in protocol.DIAGNOSTIC_DOSES
    assert 0.01 in protocol.DIAGNOSTIC_DOSES
    assert protocol.CLAIM_GATE_POLICY["diagnostic_failures_delete_rows"] is False


def test_resource_and_archive_envelope_matches_inventory() -> None:
    limits = protocol.RESOURCE_LIMITS
    assert limits["expected_signed_pairs"] == 1_440
    assert limits["expected_edited_forwards"] == 2_880
    assert limits["expected_model_forwards"] == 2_896
    assert limits["expected_raw_bytes_approx"] == 2_300_000_000
    assert limits["raw_run_ceiling_bytes"] == 4 * 1024**3
    assert limits["post_run_free_reserve_bytes"] == 64 * 1024**3
    assert limits["expected_raw_bytes_approx"] < limits["raw_run_ceiling_bytes"]
    assert protocol.INDEPENDENT_RECOMPUTATION_SPEC[
        "recompute_every_nonzero_magnitude_and_shared_zero"
    ] is True
