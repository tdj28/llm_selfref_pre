from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from experiments.consciousness_sae_signed_dose_scan import (
    qualification_incident,
    verify_qualification_incident,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
INCIDENT_DIR = REPO_ROOT / (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up"
)
LEDGER = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V2.json"
)
C2_INCIDENT_DIR = REPO_ROOT / (
    "docs/consciousness_sae_signed_dose_scan/"
    "audit_recovery_qualification_incident_79db4e7_g2azyjkpm17f1s"
)
C3_LEDGER = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V3.json"
)
C3_STATUS_MAP = (
    REPO_ROOT
    / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C3_STATUS_MAP.json"
)


def _rewrite_rehashed(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    value.pop("receipt_sha256", None)
    value["receipt_sha256"] = qualification_incident.canonical_sha256(value)
    path.write_bytes(qualification_incident.canonical_json_bytes(value) + b"\n")


def _copy_fixture(tmp_path: Path) -> tuple[Path, Path]:
    incident = tmp_path / INCIDENT_DIR.name
    shutil.copytree(INCIDENT_DIR, incident)
    ledger = tmp_path / LEDGER.name
    shutil.copy2(LEDGER, ledger)
    return incident, ledger


def _copy_c3_fixture(tmp_path: Path) -> tuple[Path, Path]:
    incident = tmp_path / C2_INCIDENT_DIR.name
    shutil.copytree(C2_INCIDENT_DIR, incident)
    ledger = tmp_path / C3_LEDGER.name
    shutil.copy2(C3_LEDGER, ledger)
    shutil.copy2(C3_STATUS_MAP, tmp_path / C3_STATUS_MAP.name)
    return incident, ledger


def test_producer_and_independent_successor_bindings_are_identical() -> None:
    produced = qualification_incident.successor_authority_binding(
        INCIDENT_DIR, LEDGER
    )
    verified = verify_qualification_incident.successor_authority_binding(
        INCIDENT_DIR, LEDGER
    )
    assert produced == verified
    assert produced["binding_sha256"] == (
        "41c7a12dde095fdf19dc00a0f211afe8b0d2f12299b7ab1a5e12f70b5eee8f26"
    )
    assert produced["global_qualification_ordinal"] == 2
    assert produced["successor_qualification_attempt"] == 1
    assert produced["retry_authorized"] is False


def test_c3_producer_and_independent_authority_bindings_are_identical() -> None:
    produced = qualification_incident.successor_c3_authority_binding(
        C2_INCIDENT_DIR, C3_LEDGER
    )
    verified = verify_qualification_incident.successor_c3_authority_binding(
        C2_INCIDENT_DIR, C3_LEDGER
    )
    assert produced == verified
    assert produced["binding_sha256"] == (
        "f4358f97989936e3a4c366568a3a5acb54f1f144eff082be1df9a11bd9e55950"
    )
    assert produced["global_qualification_ordinal"] == 3
    assert produced["qualification_attempt_number"] == 1
    assert produced["no_automatic_retry"] is True
    assert produced["qualification_and_review_raw_or_outcome_access"] is False


def test_independent_verifier_does_not_import_producer() -> None:
    source = Path(verify_qualification_incident.__file__).read_text(
        encoding="utf-8"
    )
    assert "from experiments.consciousness_sae_signed_dose_scan import qualification_incident" not in source
    assert "import qualification_incident" not in source


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("INCIDENT_CAUSE.json", lambda value: value.__setitem__("cause_confidence", "certain")),
        (
            "INCIDENT_CLOSURE.json",
            lambda value: value["successor_requirements"].__setitem__(
                "retry_count", 1
            ),
        ),
        (
            "INCIDENT_CLOSURE_VERIFICATION.json",
            lambda value: value.__setitem__(
                "qualification_outcome_classification", "unknown"
            ),
        ),
    ],
)
def test_rehashed_authored_incident_tamper_is_rejected(
    tmp_path: Path, name: str, mutate
) -> None:
    incident, _ledger = _copy_fixture(tmp_path)
    _rewrite_rehashed(incident / name, mutate)
    with pytest.raises(qualification_incident.QualificationIncidentError):
        qualification_incident.validate_incident(incident)
    with pytest.raises(
        verify_qualification_incident.QualificationIncidentVerificationError
    ):
        verify_qualification_incident.verify_incident(incident)


def test_rehashed_ledger_authority_tamper_is_rejected(tmp_path: Path) -> None:
    incident, ledger = _copy_fixture(tmp_path)
    _rewrite_rehashed(
        ledger,
        lambda value: value["cardinality_limits"].__setitem__(
            "automatic_retries", 1
        ),
    )
    with pytest.raises(qualification_incident.QualificationIncidentError):
        qualification_incident.successor_authority_binding(incident, ledger)
    with pytest.raises(
        verify_qualification_incident.QualificationIncidentVerificationError
    ):
        verify_qualification_incident.successor_authority_binding(
            incident, ledger
        )


def test_c3_rehashed_authority_and_incident_tamper_are_rejected(
    tmp_path: Path,
) -> None:
    incident, ledger = _copy_c3_fixture(tmp_path)
    _rewrite_rehashed(
        ledger,
        lambda value: value["cardinality_limits"].__setitem__(
            "automatic_retries", 1
        ),
    )
    with pytest.raises(qualification_incident.QualificationIncidentError):
        qualification_incident.successor_c3_authority_binding(incident, ledger)
    with pytest.raises(
        verify_qualification_incident.QualificationIncidentVerificationError
    ):
        verify_qualification_incident.successor_c3_authority_binding(
            incident, ledger
        )

    incident, ledger = _copy_c3_fixture(tmp_path / "incident-tamper")
    _rewrite_rehashed(
        incident / "QUALIFICATION_FAILED.json",
        lambda value: value.__setitem__("retry_authorized", True),
    )
    with pytest.raises(qualification_incident.QualificationIncidentError):
        qualification_incident.successor_c3_authority_binding(incident, ledger)
    with pytest.raises(
        verify_qualification_incident.QualificationIncidentVerificationError
    ):
        verify_qualification_incident.successor_c3_authority_binding(
            incident, ledger
        )


def test_immutable_predecessor_receipt_tamper_is_rejected(tmp_path: Path) -> None:
    incident, _ledger = _copy_fixture(tmp_path)
    _rewrite_rehashed(
        incident / "QUALIFICATION_FAILED.json",
        lambda value: value.__setitem__("retry_authorized", True),
    )
    with pytest.raises(qualification_incident.QualificationIncidentError):
        qualification_incident.validate_incident(incident)
    with pytest.raises(
        verify_qualification_incident.QualificationIncidentVerificationError
    ):
        verify_qualification_incident.verify_incident(incident)
