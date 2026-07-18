from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import audit_recovery
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
C3_STATUS_MAP_PATH = (
    recovery_equivalence.REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C3_STATUS_MAP.json"
)
C4_STATUS_MAP_PATH = (
    recovery_equivalence.REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C4_STATUS_MAP.json"
)
C5_STATUS_MAP_PATH = (
    recovery_equivalence.REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C5_STATUS_MAP.json"
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

    assert verified["status"] == ("pass_outcome_blind_recovery_equivalence_verified")
    assert verified["code_freeze_commit"] == FAKE_CODE_FREEZE
    assert packet["recovery_equivalence_protocol_version"].endswith("_v5")
    lineage = packet["freeze_lineage"]
    assert lineage["direct_parent_chain"] == [
        recovery_equivalence.ORIGINAL_FREEZE_COMMIT,
        recovery_equivalence.C1_RECOVERY_FREEZE_COMMIT,
        recovery_equivalence.C2_RECOVERY_FREEZE_COMMIT,
        recovery_equivalence.C3_RECOVERY_FREEZE_COMMIT,
        recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT,
        recovery_equivalence.C4_RECOVERY_FREEZE_COMMIT,
        recovery_equivalence.E4_QUALIFICATION_FREEZE_COMMIT,
        FAKE_CODE_FREEZE,
    ]
    assert {
        row["path"]: row["status"] for row in lineage["original_to_c1_name_status"]
    } == recovery_equivalence.ORIGINAL_TO_C1_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["c1_to_c2_name_status"]
    } == recovery_equivalence.C1_TO_C2_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["c2_to_c3_name_status"]
    } == recovery_equivalence.C2_TO_C3_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["c3_to_e3_name_status"]
    } == recovery_equivalence.C3_TO_E3_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["e3_to_c4_name_status"]
    } == recovery_equivalence.E3_TO_C4_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["c4_to_e4_name_status"]
    } == recovery_equivalence.C4_TO_E4_NAME_STATUS
    assert {
        row["path"]: row["status"] for row in lineage["e4_to_c5_name_status"]
    } == recovery_equivalence.E4_TO_C5_NAME_STATUS
    assert lineage["original_science_mutation_paths"] == []
    assert packet["outcome_input_paths"] == []
    assert packet["raw_run_opened"] is False
    assert packet["compact_result_opened"] is False
    assert packet["model_forward_count"] == 0
    proof = packet["compatibility_proof"]
    assert proof["compatibility_change_count"] == 1
    assert proof["pinned_available_layers"] == list(range(79))
    assert proof["required_layers"] == list(range(45, 79))
    assert proof["filtered_layers_handed_to_frozen_auditor"] == list(range(45, 79))
    assert proof["scientific_field_projection_unchanged"] is True
    authority = packet["c5_authority_documents"]
    assert authority["global_qualification_ordinal"] == 4
    assert authority["new_qualification_attempt_count"] == 0
    assert authority["new_paid_review_call_count"] == 0
    assert authority["review_input_anchor_commit"] == (
        recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT
    )


def test_v3_packet_remains_buildable_and_verifiable(tmp_path: Path) -> None:
    plan_audit = validate_plan.validate(PLAN_DIR)
    plan_audit_path = tmp_path / "PLAN_AUDIT.json"
    _write(plan_audit_path, plan_audit)
    packet = recovery_equivalence.build_packet(
        plan_audit_path=plan_audit_path,
        code_freeze_commit=FAKE_CODE_FREEZE,
        enforce_git=False,
        equivalence_protocol_version=(
            recovery_equivalence.RECOVERY_EQUIVALENCE_PROTOCOL_VERSION_V3
        ),
    )
    packet_path = tmp_path / "RECOVERY_EQUIVALENCE_PACKET_V3.json"
    _write(packet_path, packet)

    verified = verify_recovery_equivalence.verify_packet(
        packet_path,
        plan_audit_path=plan_audit_path,
        enforce_git=False,
    )

    assert packet["packet_type"].endswith("_v3")
    assert "c4_authority_documents" not in packet
    assert verified["recovery_equivalence_protocol_version"].endswith("_v3")


def test_v4_packet_remains_buildable_and_verifiable(tmp_path: Path) -> None:
    plan_audit = validate_plan.validate(PLAN_DIR)
    plan_audit_path = tmp_path / "PLAN_AUDIT.json"
    _write(plan_audit_path, plan_audit)
    packet = recovery_equivalence.build_packet(
        plan_audit_path=plan_audit_path,
        code_freeze_commit=FAKE_CODE_FREEZE,
        enforce_git=False,
        equivalence_protocol_version=(
            recovery_equivalence.RECOVERY_EQUIVALENCE_PROTOCOL_VERSION_V4
        ),
    )
    packet_path = tmp_path / "RECOVERY_EQUIVALENCE_PACKET_V4.json"
    _write(packet_path, packet)

    verified = verify_recovery_equivalence.verify_packet(
        packet_path,
        plan_audit_path=plan_audit_path,
        enforce_git=False,
    )

    assert packet["packet_type"].endswith("_v4")
    assert "c4_authority_documents" in packet
    assert "c5_authority_documents" not in packet
    assert verified["recovery_equivalence_protocol_version"].endswith("_v4")


def test_c3_status_map_matches_both_independent_lineage_restatements() -> None:
    status_map = json.loads(C3_STATUS_MAP_PATH.read_bytes())
    core = dict(status_map)
    claimed = core.pop("receipt_sha256")
    assert claimed == recovery_equivalence.canonical_sha256(core)
    surface = status_map["c2_to_c3"]
    expected = {
        **{path: "A" for path in surface["added"]},
        **{path: "M" for path in surface["modified"]},
        **{path: "D" for path in surface["deleted"]},
    }
    assert expected == recovery_equivalence.C2_TO_C3_NAME_STATUS
    assert expected == verify_recovery_equivalence.C2_TO_C3_NAME_STATUS
    assert set(expected) <= set(recovery_equivalence.RECOVERY_CLOSURE_PATHS)
    assert set(expected) <= set(verify_recovery_equivalence.RECOVERY_CLOSURE_PATHS)


def test_c4_status_map_matches_both_independent_lineage_restatements() -> None:
    status_map = json.loads(C4_STATUS_MAP_PATH.read_bytes())
    core = dict(status_map)
    claimed = core.pop("receipt_sha256")
    assert claimed == recovery_equivalence.canonical_sha256(core)
    surface = status_map["e3_to_c4"]
    expected = {
        **{path: "A" for path in surface["added"]},
        **{path: "M" for path in surface["modified"]},
        **{path: "D" for path in surface["deleted"]},
    }
    assert expected == recovery_equivalence.E3_TO_C4_NAME_STATUS
    assert expected == verify_recovery_equivalence.E3_TO_C4_NAME_STATUS
    assert recovery_equivalence.C4_TO_E4_NAME_STATUS == (
        verify_recovery_equivalence.C4_TO_E4_NAME_STATUS
    )
    assert recovery_equivalence.E4_TO_F4_NAME_STATUS == (
        verify_recovery_equivalence.E4_TO_F4_NAME_STATUS
    )
    assert set(expected) <= set(recovery_equivalence.RECOVERY_CLOSURE_PATHS)


def test_c5_status_map_matches_both_independent_lineage_restatements() -> None:
    status_map = json.loads(C5_STATUS_MAP_PATH.read_bytes())
    core = dict(status_map)
    claimed = core.pop("receipt_sha256")
    assert claimed == recovery_equivalence.canonical_sha256(core)
    surface = status_map["e4_to_c5"]
    expected = {
        **{path: "A" for path in surface["added"]},
        **{path: "M" for path in surface["modified"]},
        **{path: "D" for path in surface["deleted"]},
    }
    assert expected == recovery_equivalence.E4_TO_C5_NAME_STATUS
    assert expected == verify_recovery_equivalence.E4_TO_C5_NAME_STATUS
    assert recovery_equivalence.C5_TO_E5_NAME_STATUS == (
        verify_recovery_equivalence.C5_TO_E5_NAME_STATUS
    )
    assert recovery_equivalence.E5_TO_F5_NAME_STATUS == (
        verify_recovery_equivalence.E5_TO_F5_NAME_STATUS
    )
    assert set(expected) <= set(recovery_equivalence.RECOVERY_CLOSURE_PATHS)


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


def test_independent_verifier_rejects_rehashed_lineage_tamper(
    tmp_path: Path,
) -> None:
    packet_path, plan_audit_path, packet = _packet_fixture(tmp_path)
    packet["freeze_lineage"]["c2_to_c3_name_status"][0]["status"] = "D"
    core = dict(packet)
    core.pop("packet_sha256")
    packet["packet_sha256"] = recovery_equivalence.canonical_sha256(core)
    _write(packet_path, packet)

    with pytest.raises(
        verify_recovery_equivalence.RecoveryEquivalenceVerificationError,
        match="freeze lineage binding differs",
    ):
        verify_recovery_equivalence.verify_packet(
            packet_path,
            plan_audit_path=plan_audit_path,
            enforce_git=False,
        )


def test_independent_verifier_rejects_rehashed_c5_authority_tamper(
    tmp_path: Path,
) -> None:
    packet_path, plan_audit_path, packet = _packet_fixture(tmp_path)
    packet["c5_authority_documents"]["new_paid_review_call_count"] = 1
    core = dict(packet)
    core.pop("packet_sha256")
    packet["packet_sha256"] = recovery_equivalence.canonical_sha256(core)
    _write(packet_path, packet)

    with pytest.raises(
        verify_recovery_equivalence.RecoveryEquivalenceVerificationError,
        match="authority-document binding differs",
    ):
        verify_recovery_equivalence.verify_packet(
            packet_path,
            plan_audit_path=plan_audit_path,
            enforce_git=False,
        )


def test_both_final_chain_validators_bind_dynamic_c4_e4_f4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c4 = "4" * 40
    e4 = "5" * 40
    f4 = "6" * 40
    parents = {
        c4: recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT,
        e4: c4,
        f4: e4,
    }

    def builder_git(*args: str, repo_root: Path) -> bytes:
        if args[0] == "rev-parse":
            return args[1].split("^", 1)[0].encode() + b"\n"
        if args[0] == "rev-list":
            child = args[-1]
            return f"{child} {parents[child]}\n".encode()
        raise AssertionError(args)

    def verifier_git(_repo_root: Path, *args: str) -> bytes:
        return builder_git(*args, repo_root=_repo_root)

    edge_maps = {
        (recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT, c4): (
            recovery_equivalence.E3_TO_C4_NAME_STATUS
        ),
        (c4, e4): recovery_equivalence.C4_TO_E4_NAME_STATUS,
        (e4, f4): recovery_equivalence.E4_TO_F4_NAME_STATUS,
    }
    monkeypatch.setattr(recovery_equivalence, "_git", builder_git)
    monkeypatch.setattr(
        recovery_equivalence,
        "_observed_name_status",
        lambda parent, child, *, repo_root: edge_maps[(parent, child)],
    )
    monkeypatch.setattr(verify_recovery_equivalence, "_git", verifier_git)
    monkeypatch.setattr(
        verify_recovery_equivalence,
        "_observed_name_status",
        lambda repo_root, parent, child: edge_maps[(parent, child)],
    )

    built = recovery_equivalence.verify_v4_final_freeze_lineage(
        code_freeze_commit=c4,
        evidence_freeze_commit=e4,
        final_freeze_commit=f4,
    )
    independently_verified = verify_recovery_equivalence.verify_v4_final_freeze_lineage(
        code_freeze_commit=c4,
        evidence_freeze_commit=e4,
        final_freeze_commit=f4,
    )

    assert built == independently_verified
    assert built["direct_parent_chain"] == [
        recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT,
        c4,
        e4,
        f4,
    ]


def test_both_v5_preflight_validators_consume_the_direct_authentic_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c5 = "5" * 40
    e5 = "6" * 40
    f5 = "7" * 40
    monkeypatch.setattr(
        audit_recovery,
        "RECOVERY_PROTOCOL_VERSION",
        "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v5",
    )
    receipt = audit_recovery.validate_physical_authentic_review_bundle(
        code_freeze_commit=c5
    )
    receipt_raw = recovery_equivalence.canonical_json_bytes(receipt) + b"\n"

    def reader(commit: str, path: str) -> bytes:
        if path == recovery_equivalence.C5_PREFLIGHT_PATH and commit in {e5, f5}:
            return receipt_raw
        return (recovery_equivalence.REPO_ROOT / path).read_bytes()

    built = recovery_equivalence._v5_preflight_evidence(
        code_freeze_commit=c5,
        evidence_freeze_commit=e5,
        final_freeze_commit=f5,
        reader=reader,
    )
    independently_verified = verify_recovery_equivalence._verify_v5_preflight_evidence(
        code_freeze_commit=c5,
        evidence_freeze_commit=e5,
        final_freeze_commit=f5,
        reader=reader,
    )

    assert built == independently_verified
    assert built["adjudication_receipt_sha256"] == (
        recovery_equivalence.AUTHENTIC_REVIEW_ADJUDICATION_RECEIPT_SHA256
    )
    assert built["new_paid_review_call_count"] == 0
    assert built["outcome_input_paths"] == []

    parents = {
        recovery_equivalence.C4_RECOVERY_FREEZE_COMMIT: (
            recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT
        ),
        recovery_equivalence.E4_QUALIFICATION_FREEZE_COMMIT: (
            recovery_equivalence.C4_RECOVERY_FREEZE_COMMIT
        ),
        c5: recovery_equivalence.E4_QUALIFICATION_FREEZE_COMMIT,
        e5: c5,
        f5: e5,
    }

    def builder_git(*args: str, repo_root: Path) -> bytes:
        if args[0] == "rev-parse":
            return args[1].split("^", 1)[0].encode() + b"\n"
        if args[0] == "rev-list":
            child = args[-1]
            return f"{child} {parents[child]}\n".encode()
        raise AssertionError(args)

    def verifier_git(_repo_root: Path, *args: str) -> bytes:
        return builder_git(*args, repo_root=_repo_root)

    edge_maps = {
        (
            recovery_equivalence.E3_QUALIFICATION_FREEZE_COMMIT,
            recovery_equivalence.C4_RECOVERY_FREEZE_COMMIT,
        ): recovery_equivalence.E3_TO_C4_NAME_STATUS,
        (
            recovery_equivalence.C4_RECOVERY_FREEZE_COMMIT,
            recovery_equivalence.E4_QUALIFICATION_FREEZE_COMMIT,
        ): recovery_equivalence.C4_TO_E4_NAME_STATUS,
        (
            recovery_equivalence.E4_QUALIFICATION_FREEZE_COMMIT,
            c5,
        ): recovery_equivalence.E4_TO_C5_NAME_STATUS,
        (c5, e5): recovery_equivalence.C5_TO_E5_NAME_STATUS,
        (e5, f5): recovery_equivalence.E5_TO_F5_NAME_STATUS,
    }
    monkeypatch.setattr(recovery_equivalence, "_git", builder_git)
    monkeypatch.setattr(
        recovery_equivalence,
        "_observed_name_status",
        lambda parent, child, *, repo_root: edge_maps[(parent, child)],
    )
    monkeypatch.setattr(verify_recovery_equivalence, "_git", verifier_git)
    monkeypatch.setattr(
        verify_recovery_equivalence,
        "_observed_name_status",
        lambda repo_root, parent, child: edge_maps[(parent, child)],
    )
    final_built = recovery_equivalence.verify_v5_final_freeze_lineage(
        code_freeze_commit=c5,
        evidence_freeze_commit=e5,
        final_freeze_commit=f5,
        blob_reader=reader,
    )
    final_verified = verify_recovery_equivalence.verify_v5_final_freeze_lineage(
        code_freeze_commit=c5,
        evidence_freeze_commit=e5,
        final_freeze_commit=f5,
        blob_reader=reader,
    )
    assert final_built == final_verified
    assert final_built["direct_parent_chain"][-3:] == [c5, e5, f5]


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
        alternate / "experiments/consciousness_sae_signed_dose_scan/audit_recovery.py"
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
    summary = {field: field for field in recovery_equivalence.SCIENTIFIC_SUMMARY_FIELDS}
    projected = recovery_equivalence.scientific_projection(audit, summary)
    assert tuple(projected["audit"]) == recovery_equivalence.SCIENTIFIC_AUDIT_FIELDS
    del audit[recovery_equivalence.SCIENTIFIC_AUDIT_FIELDS[-1]]
    with pytest.raises(recovery_equivalence.RecoveryEquivalenceError):
        recovery_equivalence.scientific_projection(audit, summary)
