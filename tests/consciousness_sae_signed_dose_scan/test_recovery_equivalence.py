from __future__ import annotations

from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import recovery_equivalence
from experiments.consciousness_sae_signed_dose_scan import validate_plan
from experiments.consciousness_sae_signed_dose_scan import (
    verify_recovery_equivalence,
)


FAKE_CODE_FREEZE = "f" * 40
PLAN_DIR = (
    recovery_equivalence.REPO_ROOT
    / "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716"
)


def _write(path: Path, value: object) -> None:
    path.write_bytes(recovery_equivalence.canonical_json_bytes(value) + b"\n")


def _packet_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    plan_audit = validate_plan.validate(PLAN_DIR)
    plan_audit_path = tmp_path / "PLAN_AUDIT.json"
    _write(plan_audit_path, plan_audit)
    packet = recovery_equivalence.build_packet(
        plan_audit_path=plan_audit_path,
        code_freeze_commit=FAKE_CODE_FREEZE,
        enforce_git=False,
    )
    packet_path = tmp_path / "RECOVERY_EQUIVALENCE_PACKET.json"
    _write(packet_path, packet)
    return packet_path, plan_audit_path, packet


def test_packet_and_independent_verifier_are_outcome_blind(tmp_path: Path) -> None:
    packet_path, plan_audit_path, packet = _packet_fixture(tmp_path)
    verified = verify_recovery_equivalence.verify_packet(
        packet_path,
        plan_audit_path=plan_audit_path,
        enforce_git=False,
    )

    assert verified["status"] == (
        "pass_outcome_blind_recovery_equivalence_verified"
    )
    assert verified["code_freeze_commit"] == FAKE_CODE_FREEZE
    assert packet["outcome_input_paths"] == []
    assert packet["raw_run_opened"] is False
    assert packet["compact_result_opened"] is False
    assert packet["model_forward_count"] == 0
    proof = packet["compatibility_proof"]
    assert proof["compatibility_change_count"] == 1
    assert proof["pinned_available_layers"] == list(range(79))
    assert proof["required_layers"] == list(range(45, 79))
    assert proof["filtered_layers_handed_to_frozen_auditor"] == list(
        range(45, 79)
    )
    assert proof["scientific_field_projection_unchanged"] is True


def test_independent_verifier_rejects_rehashed_semantic_tamper(
    tmp_path: Path,
) -> None:
    packet_path, plan_audit_path, packet = _packet_fixture(tmp_path)
    packet["compatibility_proof"]["required_layers"] = list(range(46, 79))
    core = dict(packet)
    core.pop("packet_sha256")
    packet["packet_sha256"] = recovery_equivalence.canonical_sha256(core)
    _write(packet_path, packet)

    with pytest.raises(
        verify_recovery_equivalence.RecoveryEquivalenceVerificationError,
        match="compatibility proof differs",
    ):
        verify_recovery_equivalence.verify_packet(
            packet_path,
            plan_audit_path=plan_audit_path,
            enforce_git=False,
        )


def test_independent_verifier_rejects_live_closure_tamper(
    tmp_path: Path,
) -> None:
    packet_path, plan_audit_path, _packet = _packet_fixture(tmp_path)
    original = recovery_equivalence.REPO_ROOT
    alternate = tmp_path / "repo"
    alternate.mkdir()
    for relative in recovery_equivalence.RECOVERY_CLOSURE_PATHS:
        destination = alternate / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((original / relative).read_bytes())
    # Original plan and precedent reads still come from the real repository.
    def reader(_commit: str, relative: str) -> bytes:
        candidate = alternate / relative
        return (
            candidate.read_bytes()
            if candidate.exists()
            else (original / relative).read_bytes()
        )

    victim = (
        alternate
        / "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py"
    )
    victim.write_bytes(victim.read_bytes() + b"\n")
    with pytest.raises(
        verify_recovery_equivalence.RecoveryEquivalenceVerificationError,
        match="recovery closure differs|live recovery closure differs",
    ):
        verify_recovery_equivalence.verify_packet(
            packet_path,
            plan_audit_path=plan_audit_path,
            repo_root=alternate,
            enforce_git=False,
            blob_reader=reader,
        )


def test_scientific_projection_is_affirmative() -> None:
    audit = {field: field for field in recovery_equivalence.SCIENTIFIC_AUDIT_FIELDS}
    summary = {
        field: field for field in recovery_equivalence.SCIENTIFIC_SUMMARY_FIELDS
    }
    projected = recovery_equivalence.scientific_projection(audit, summary)
    assert tuple(projected["audit"]) == recovery_equivalence.SCIENTIFIC_AUDIT_FIELDS
    del audit[recovery_equivalence.SCIENTIFIC_AUDIT_FIELDS[-1]]
    with pytest.raises(recovery_equivalence.RecoveryEquivalenceError):
        recovery_equivalence.scientific_projection(audit, summary)
