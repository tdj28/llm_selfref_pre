from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import incident_closure
from experiments.consciousness_sae_signed_dose_scan import (
    verify_incident_closure as independent,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLOSURE_PATH = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE.json"
)
SCHEMA_PATH = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json"
)
LEDGER_PATH = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER.json"
)
VERIFICATION_PATH = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_VERIFICATION.json"
)


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rehash(value: dict[str, object]) -> dict[str, object]:
    rewritten = copy.deepcopy(value)
    rewritten.pop("receipt_sha256", None)
    rewritten["receipt_sha256"] = independent.canonical_sha256(rewritten)
    return rewritten


def test_generated_closure_and_cycle_ledger_pass_independently() -> None:
    result = independent.verify_paths(
        CLOSURE_PATH,
        schema_path=SCHEMA_PATH,
        recovery_ledger_path=LEDGER_PATH,
    )
    assert result == {
        "schema_version": 1,
        "receipt_kind": (
            "consciousness_sae_signed_dose_scan_incident_closure_verification_v1"
        ),
        "status": "pass_incident_closure_and_cycle_independent_verification",
        "incident_closure_file_sha256": (
            "7afe9aa8bae10c2965f40eab92fbbb331a51ad0fd2a0895d6fc55bd0af7cbd3c"
        ),
        "incident_closure_receipt_sha256": (
            "172ebb2e4ea06160df7d3a3d9e356dfdc0996ffb50019c6bc35a48a724103dd4"
        ),
        "incident_closure_schema_file_sha256": (
            "3179e4c8ae25b5d858d4779e224ad83123720cb84346f626ce316c3fea82f174"
        ),
        "recovery_cycle_ledger_file_sha256": (
            "b7921997024ef9d23bc2c5ae6ecbb21bf013a935313d8247868b709bbbfb5cb5"
        ),
        "recovery_cycle_ledger_receipt_sha256": (
            "72f2d473c68698a24160523265a9786b9382a14432e418d24a2f6596f910314b"
        ),
        "raw_record_count": 35,
        "raw_stored_bytes": 2_229_288_980,
        "raw_records_sha256": (
            "b5c784f4feb87ba01a9fc5d9b2f22d12eee01930d98718cd5c54e3d398692cf4"
        ),
        "checks": [
            "canonical_self_hash",
            "independently_anchored_authority",
            "exact_evidence_and_wrapper_inventory",
            "exact_attempt_classifications",
            "full_raw_ledger_commitment",
            "exact_termination_and_rejected_authorities",
            "bounded_recovery_cycle_and_non_authority",
            "complete_closure_table",
        ],
        "receipt_sha256": (
            "92c969a06bbd0c776e2f0f31357e04cca749c8244a25e3f4bc871cfd8ff3c2d8"
        ),
    }
    assert _load(VERIFICATION_PATH) == result
    assert VERIFICATION_PATH.read_bytes() == independent.canonical_json_bytes(result) + b"\n"


def test_closure_is_canonical_metadata_only_and_portable() -> None:
    value = _load(CLOSURE_PATH)
    raw = CLOSURE_PATH.read_bytes()
    assert raw == independent.canonical_json_bytes(value) + b"\n"
    assert b"/Users/" not in raw
    assert b"/private/tmp/" not in raw
    assert b"/root/" not in raw
    assert b"/workspace/" not in raw
    ledger = value["raw_ledger"]
    assert isinstance(ledger, dict)
    records = ledger["records"]
    assert isinstance(records, list)
    assert len(records) == 35
    assert sum(row["bytes"] for row in records) == 2_229_288_980


def test_broken_closure_self_hash_fails() -> None:
    value = _load(CLOSURE_PATH)
    value["status"] = "closed"
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="self-hash differs",
    ):
        independent.verify_closure(value)


def test_semantic_attempt_tamper_fails_after_rehash() -> None:
    value = _load(CLOSURE_PATH)
    attempts = value["attempt_classifications"]
    assert isinstance(attempts, list)
    attempts[0]["model_load_reached"] = True
    attempts[0]["model_forward_count"] = 1
    tampered = _rehash(value)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="attempt classification differs",
    ):
        independent.verify_closure(tampered)


def test_raw_ledger_tamper_fails_after_all_dependent_rehashes() -> None:
    value = _load(CLOSURE_PATH)
    raw = value["raw_ledger"]
    assert isinstance(raw, dict)
    records = raw["records"]
    assert isinstance(records, list)
    records[0]["sha256"] = "0" * 64
    raw["records_sha256"] = independent.canonical_sha256(records)
    tampered = _rehash(value)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="declared commitment differs",
    ):
        independent.verify_closure(tampered)


def test_wrapper_hash_tamper_fails_after_rehash() -> None:
    value = _load(CLOSURE_PATH)
    inventory = value["evidence_inventory"]
    assert isinstance(inventory, list)
    wrapper = next(row for row in inventory if row["role"] == "llama70b_v1_wrapper")
    wrapper["sha256"] = "1" * 64
    tampered = _rehash(value)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="historical evidence inventory differs",
    ):
        independent.verify_closure(tampered)


def test_historical_authority_tamper_fails_after_rehash() -> None:
    value = _load(CLOSURE_PATH)
    authority = value["authority"]
    assert isinstance(authority, dict)
    authority["freeze_commit"] = "0" * 40
    tampered = _rehash(value)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="authority differs",
    ):
        independent.verify_closure(tampered)


def test_cycle_cannot_silently_authorize_review_or_recovery() -> None:
    closure = _load(CLOSURE_PATH)
    ledger = _load(LEDGER_PATH)
    state = ledger["authorization_state"]
    assert isinstance(state, dict)
    state["paid_cumulative_review_authorized"] = True
    state["audit_only_recovery_authorized"] = True
    tampered = _rehash(ledger)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="authorization state differs",
    ):
        independent.verify_recovery_ledger(
            tampered,
            closure_receipt_sha256=str(closure["receipt_sha256"]),
            closure_file_sha256=independent.sha256_file(CLOSURE_PATH),
        )


def test_cycle_cannot_expand_cardinality_after_rehash() -> None:
    closure = _load(CLOSURE_PATH)
    ledger = _load(LEDGER_PATH)
    limits = ledger["cardinality_limits"]
    assert isinstance(limits, dict)
    limits["target_qualification_attempts"] = 2
    tampered = _rehash(ledger)
    with pytest.raises(
        independent.IncidentClosureVerificationError,
        match="cardinality differs",
    ):
        independent.verify_recovery_ledger(
            tampered,
            closure_receipt_sha256=str(closure["receipt_sha256"]),
            closure_file_sha256=independent.sha256_file(CLOSURE_PATH),
        )


def test_producer_refuses_changed_evidence(tmp_path: Path) -> None:
    spec = incident_closure.WRAPPER_SPECS[0]
    changed = tmp_path / spec.relative_name
    changed.write_bytes(b"not the historical wrapper")
    with pytest.raises(
        incident_closure.IncidentClosureError,
        match="physical identity differs",
    ):
        incident_closure._artifact(changed, spec)


def test_independent_verifier_does_not_import_the_producer() -> None:
    source = Path(independent.__file__).read_text(encoding="utf-8")
    assert "from experiments.consciousness_sae_signed_dose_scan import incident_closure" not in source
    assert "import incident_closure" not in source
