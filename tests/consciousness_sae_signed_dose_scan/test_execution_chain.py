from __future__ import annotations

from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import (
    audit,
    authorize,
    build_plan,
    orientation,
    protocol,
    review_adjudication,
    runner,
)
from experiments.consciousness_sae_target_blind_calibration import (
    orientation as predecessor_orientation,
)
from experiments.consciousness_sae_target_blind_calibration import runner as engine


def _write_canonical(path: Path, value: dict[str, object]) -> None:
    path.write_bytes(protocol.canonical_json_bytes(value) + b"\n")


def test_runner_rebinds_successor_plan_and_orientation() -> None:
    old = (
        engine.protocol,
        engine.build_plan,
        engine.authorize,
        engine.orientation,
        engine._validate_plan,
        engine._validate_runtime_requirements,
        engine._validate_authorization,
    )
    try:
        runner._patch_engine()
        assert engine.protocol is protocol
        assert engine.build_plan is build_plan
        assert engine.authorize is authorize
        assert engine.orientation is orientation
        assert engine._validate_plan is runner._validate_plan
    finally:
        (
            engine.protocol,
            engine.build_plan,
            engine.authorize,
            engine.orientation,
            engine._validate_plan,
            engine._validate_runtime_requirements,
            engine._validate_authorization,
        ) = old


def test_orientation_rebinds_every_import_time_constant() -> None:
    old = (
        predecessor_orientation.protocol,
        predecessor_orientation.FIXTURE_COUNT,
        predecessor_orientation.SEED_NAMESPACE,
        predecessor_orientation.EXPECTED_ROW_COUNT,
    )
    try:
        orientation._bind()
        expected_count = int(protocol.J_ORIENTATION_SPEC["fixture_count_per_layer"])
        assert predecessor_orientation.protocol is protocol
        assert predecessor_orientation.FIXTURE_COUNT == expected_count
        assert predecessor_orientation.SEED_NAMESPACE == (
            protocol.FRESH_RANDOMIZATION_SPEC["j_orientation_seed_namespace"]
        )
        assert predecessor_orientation.EXPECTED_ROW_COUNT == (
            len(protocol.J_LAYERS) * expected_count
        )
    finally:
        (
            predecessor_orientation.protocol,
            predecessor_orientation.FIXTURE_COUNT,
            predecessor_orientation.SEED_NAMESPACE,
            predecessor_orientation.EXPECTED_ROW_COUNT,
        ) = old


def test_small_model_receipt_contract_accepts_only_exact_grid(tmp_path: Path) -> None:
    core = {
        "status": "pass_small_model_promotion_gate",
        "dose_basis_points_sha256": protocol.canonical_sha256(
            list(protocol.DOSE_BASIS_POINTS)
        ),
        "nonzero_dose_count": 60,
        "signed_pair_count": 60,
        "edited_forward_count": 120,
        "zero_baseline_count": 1,
        "model_id": "google/gemma-2-9b-it",
        "model_revision": "11c9b309abf73637e4b6f9a3fa1e92e615547819",
        "sae_repo": "google/gemma-scope-9b-it-res",
        "sae_revision": "e86af97a5b6fbbccca28ab654f2fda1b0768f770",
        "sae_folder": "layer_20/width_16k/average_l0_91",
        "sae_feature_id": 1_295,
        "required_gates": ["structural", "numeric", "hook", "artifact_replay"],
        "promotion_scope": "runner_mechanics_only_not_scientific_protocol",
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    path = tmp_path / "promotion.json"
    _write_canonical(path, receipt)
    observed, observed_path = authorize._small_gate(path)
    assert observed == receipt
    assert observed_path == path

    broken = dict(core)
    broken["edited_forward_count"] = 118
    broken = {**broken, "receipt_sha256": protocol.canonical_sha256(broken)}
    path.unlink()
    _write_canonical(path, broken)
    with pytest.raises(authorize.AuthorizationError, match="promotion gate"):
        authorize._small_gate(path)


def test_frozen_source_closure_contains_every_executable_boundary() -> None:
    required = {
        "experiments/consciousness_sae_signed_dose_scan/runner.py",
        "experiments/consciousness_sae_signed_dose_scan/audit.py",
        "experiments/consciousness_sae_signed_dose_scan/authorize.py",
        "experiments/consciousness_sae_signed_dose_scan/orientation.py",
        "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation.py",
        "experiments/consciousness_sae_signed_dose_scan/gemma9b_validation_audit.py",
        "experiments/consciousness_sae_target_blind_calibration/runner.py",
        "experiments/consciousness_sae_target_blind_calibration/orientation.py",
        "experiments/consciousness_sae_realization_validation/runtime.py",
        "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    }
    assert required <= set(build_plan.SOURCE_PATHS)
    source = Path(audit.__file__).read_text(encoding="utf-8")
    assert 'seed64("runtime-v2")' not in source
    assert 'seed64("random-j-v2"' not in source
    assert 'seed64("fixed-token-panel-v2")' not in source


def test_runner_and_audit_reconstruct_same_fresh_token_panel() -> None:
    old_protocol = engine.protocol
    try:
        engine.protocol = protocol
        assert engine._fixed_token_panel() == audit._fixed_token_panel()
    finally:
        engine.protocol = old_protocol


def test_review_verdict_must_be_final_and_unopposed() -> None:
    assert review_adjudication.terminal_verdict(
        "No blockers remain.\n\n**READY TO FREEZE**\n"
    ) == "READY TO FREEZE"
    with pytest.raises(review_adjudication.ReviewAdjudicationError):
        review_adjudication.terminal_verdict(
            "READY TO FREEZE\n\nNOT READY TO FREEZE: unresolved blocker\n"
        )
    with pytest.raises(review_adjudication.ReviewAdjudicationError):
        review_adjudication.terminal_verdict(
            "READY TO FREEZE\n\nTrailing qualification.\n"
        )


def test_review_scope_matches_the_frozen_director_review() -> None:
    assert (
        review_adjudication.EXPECTED_REVIEW_SCOPE
        == "director_level_plan_review"
    )


def test_runner_binds_one_run_id_per_authorization(tmp_path: Path) -> None:
    path = tmp_path / "authorization.json"
    _write_canonical(path, {"authorized_run_id": "signed-scan-run-001"})
    runner._validate_authorized_run_id(path, "signed-scan-run-001")
    with pytest.raises(engine.CalibrationExecutionError, match="one-attempt"):
        runner._validate_authorized_run_id(path, "signed-scan-run-002")


def test_primary_actual_state_arc_rows_cover_every_downstream_state() -> None:
    torch = pytest.importorskip("torch")
    clean = torch.ones((len(protocol.J_LAYERS) + 1, 4), dtype=torch.bfloat16)
    plus = torch.ones((len(protocol.J_LAYERS) + 2, 4), dtype=torch.bfloat16)
    minus = torch.ones_like(plus)
    plus[-2] = 1.1015625
    minus[-2] = 0.8984375
    plus[6:-2] = 1.203125
    minus[6:-2] = 0.796875
    plus[-1] = 1.296875
    minus[-1] = 0.703125
    realized = (plus[-2].float() - minus[-2].float()) * 0.5
    rows = audit._primary_actual_state_arc_rows(
        prompt_id=protocol.PROMPT_IDS[0],
        direction=0,
        dose=0.03,
        clean_arc=clean,
        plus_arc=plus,
        minus_arc=minus,
        realized_source=realized,
    )
    assert len(rows) == 30
    assert [row["state_index"] for row in rows] == list(range(50, 80))
    assert rows[0]["state_label"] == "explicit_post_edit_block_50_output"
    assert rows[-1]["state_label"].endswith("final_rmsnorm_input")
    assert all(row["requested_dose_basis_points"] == 300 for row in rows)
