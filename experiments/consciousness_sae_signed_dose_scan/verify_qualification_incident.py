#!/usr/bin/env python3
"""Independently verify the consumed C1 qualification incident.

This module deliberately does not import ``qualification_incident``.  It
restates the immutable receipt inventory and the no-raw/no-forward successor
boundary, and never accepts a raw-run path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from pathlib import Path
from typing import Any, Mapping


INCIDENT_ID = "qualification-f1307fc-69d9kxugxuf6up"
C1_CODE_FREEZE_COMMIT = "f1307fc56d9d8fbd0625bf30524e6eea16575326"
FAILED_POD_ID = "69d9kxugxuf6up"
REJECTED_POD_IDS = ["wl8obvtuq0ax8t", FAILED_POD_ID]
PREDECESSOR_PROTOCOL = (
    "consciousness_sae_signed_dose_scan_v1."
    "audit_recovery_host_qualification_v1"
)
SUCCESSOR_PROTOCOL = (
    "consciousness_sae_signed_dose_scan_v1."
    "audit_recovery_host_qualification_v2"
)
SUCCESSOR_CYCLE_ID = "signed-dose-audit-only-recovery-v2-20260717"
HEX64 = re.compile(r"[0-9a-f]{64}")
EXPECTED_CAUSE_FILE_SHA256 = (
    "bde08fc1234ef8146471c0e813dc6c4ae9228ac97b9e08d99f503b0e88e1db4d"
)
EXPECTED_CAUSE_RECEIPT_SHA256 = (
    "15956cb80c920c964c55d63d7b4168f8ebb5544ff1b46ebac7b3308fa435dd7b"
)
EXPECTED_SCHEMA_FILE_SHA256 = (
    "021fb50c6005f559ba7b4d5b0ab595862b425cdb60e239dd18ae4605894719a1"
)
EXPECTED_CLOSURE_FILE_SHA256 = (
    "00be6ca94cd4c1d04adb9932ffd6a160416977041260e5f28a9d3f470a730356"
)
EXPECTED_CLOSURE_RECEIPT_SHA256 = (
    "10a5838638ab3950981ea91532204c2ae28a67505e72fc3f5bf7bf534cdf79d1"
)
EXPECTED_VERIFICATION_FILE_SHA256 = (
    "c1bcc6e51450afc24016f7881be6b42329c1583edea155b40f878140962c4ce6"
)
EXPECTED_VERIFICATION_RECEIPT_SHA256 = (
    "f8202d34728205e9e90f961c6ce28e830f287c392d4f27a2ad3b64645dd74dd6"
)
EXPECTED_LEDGER_FILE_SHA256 = (
    "f775378dfe293181d64e27c7704e70c73a5ec1736402655700afd4080236faa2"
)
EXPECTED_LEDGER_RECEIPT_SHA256 = (
    "534531c3825a5d91521b417ba92482845ed663f86d66a18ddaa9f5a31fd9c787"
)
EXPECTED_FILES = {
    "ATTEMPT_STARTED.json": (
        "irreversible_attempt_marker", 1394,
        "7e6e1e9fbeea88496dbbe2c0576ca50f2a127cddafaa1148f96fc739f2c5c36e",
        "3697f376dc4477298057cf80b226e790a57f10b426872384ebe7df36ed071b1f",
        "receipt_sha256",
    ),
    "FROZEN_OWNERSHIP.json": (
        "provider_lifecycle_ownership", 3048,
        "012f0307c1b9c82c4a176a109140472e745b9766db588cdb5f6d898e11bbb6d8",
        "a31bc98e802a68f83a6f46abd8508f9d6a33d7280ca211dbc6f7ca1fbefb0e2c",
        "receipt_sha256",
    ),
    "FROZEN_STATUS_0001.json": (
        "provider_lifecycle_status", 1133,
        "93cb738d2707e85873e66b74b9cf44865471f6723de59402ae8f3716ebc8078f",
        "590c273fe24d2fae530cb2a781fbd7f98162c04a368d6938e03d3a50af336722",
        "receipt_sha256",
    ),
    "FROZEN_TERMINATION.json": (
        "provider_lifecycle_termination", 1432,
        "1e04f948832913f26f244e508d99d6715d5bca8caef8e0edf3661291fda7824b",
        "204937720933c5416edaff36ed21fe5aa677e568c165a0515d3cda8ea8c62a02",
        "receipt_sha256",
    ),
    "OWNERSHIP.json": (
        "successor_ownership_link", 1665,
        "02f6766a37a13b6667a85963f0d81261f88e0443d515bcaedef6b15586f9f886",
        "3bb3f027471a0d4cf64e68baedf5d7d46fedd758bab39fa61f85e0805d6686f6",
        "receipt_sha256",
    ),
    "POSTCREATE_INVENTORY.json": (
        "postcreate_account_inventory", 685,
        "281cb57df69e20b946ab81dd49243f973facb9a9f586ddbb2d5da222b0c0c3fb",
        "583efb6a7c292819776dd331058f08bb89c1d3418f61b609c5bc997387c273e6",
        "receipt_sha256",
    ),
    "POSTDELETE_INVENTORY.json": (
        "postdelete_account_inventory", 493,
        "674c773a0bebe7529e107ec13469b2c82346403a24aec766d5db1640a4f74d31",
        "bb9e841ac751ccf597eadae687d122c85a8b1ab42849ab9c25f568fa4bb5a723",
        "receipt_sha256",
    ),
    "PRECREATE_INVENTORY.json": (
        "precreate_account_inventory", 492,
        "6e8587f69f61a548480797001054d804456a68ec1594ed1e034c2e63f16ca899",
        "5b2871ad96e2bea7e5dd7d502f633c5252656280ebf9d61d5077092cca5e0eaa",
        "receipt_sha256",
    ),
    "QUALIFICATION_FAILED.json": (
        "terminal_qualification_failure", 701,
        "62adf28eefac008b83b6f888081bd17fbb357fb816918bdbfac7444490eef845",
        "b943f602fc6d3015aa7f14481534ebf1be3165618067e7deaf2e53482208a18f",
        "receipt_sha256",
    ),
    "READY.json": (
        "exact_owned_pod_ready", 437,
        "f926d29abe6f5ec2b9a18dd152d20f69c424f5284d28ab7e184c972a6158b3b8",
        "291a7271106d0147e8ec883a605e00b7112a1b0b097db6ea1b7b7180e1bd5bd3",
        "receipt_sha256",
    ),
    "RECOVERY_EQUIVALENCE_PACKET.json": (
        "c1_outcome_blind_equivalence_packet", 28139,
        "db05894140be57d89f2de4821860b5f3b217527caf443e129e0c3293c075f476",
        "826b1dba22cb358ca86f7353ed702b05433ff2c5743cace76f1937c6a88d9919",
        "packet_sha256",
    ),
    "RECOVERY_EQUIVALENCE_VERIFICATION.json": (
        "c1_independent_equivalence_verification", 1029,
        "3d3be8a9ca776a977c72d3b52474ff287ef5fa9ce47d952253536891bb58fdf6",
        "16f4d6fcc16fcb4f77b372da17f7bbb40b64eb7fa134fd6c986109f58b890de1",
        "receipt_sha256",
    ),
    "STATUS_0001.json": (
        "successor_status_link", 742,
        "ffb8526732740792915a2573d1c8779a2adc726dac0558f221086a981eb4a683",
        "13cefdf6e69e9b4e14303460fcf4b6a479fe0ea27b79adc88e24ec3aeac1a8b1",
        "receipt_sha256",
    ),
    "TERMINATION_AUDIT.json": (
        "independent_exact_pod_termination_audit", 777,
        "33fdc503aef82c5f2071ae84663329f05e1a876f114498be1df8b6c5a3453715",
        "89e33501b1241f6e79a52796012043f1de46162db0fadd6a4433dabdf4c6dbc0",
        "receipt_sha256",
    ),
}


class QualificationIncidentVerificationError(RuntimeError):
    """The retained incident failed independent verification."""


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


def _load(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationIncidentVerificationError(
            f"{label} is unreadable"
        ) from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != canonical_json_bytes(value) + b"\n"
    ):
        raise QualificationIncidentVerificationError(
            f"{label} is not canonical single-link JSON"
        )
    return value, raw


def _self_hash(value: Mapping[str, Any], field: str, label: str) -> str:
    core = dict(value)
    supplied = core.pop(field, None)
    if (
        not isinstance(supplied, str)
        or HEX64.fullmatch(supplied) is None
        or supplied != canonical_sha256(core)
    ):
        raise QualificationIncidentVerificationError(
            f"{label} self-hash differs"
        )
    return supplied


def _immutable_evidence(
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    values: dict[str, dict[str, Any]] = {}
    for name in sorted(EXPECTED_FILES):
        role, size, expected_sha, expected_receipt, field = EXPECTED_FILES[name]
        value, raw = _load(root / name, f"retained evidence {name}")
        receipt = _self_hash(value, field, f"retained evidence {name}")
        sha = hashlib.sha256(raw).hexdigest()
        if len(raw) != size or sha != expected_sha or receipt != expected_receipt:
            raise QualificationIncidentVerificationError(
                f"retained evidence differs: {name}"
            )
        values[name] = value
        rows.append(
            {
                "bytes": size,
                "content_receipt_sha256": receipt,
                "relative_name": name,
                "role": role,
                "sha256": sha,
            }
        )
    return rows, values


def _verify_historical_semantics(values: Mapping[str, Mapping[str, Any]]) -> None:
    marker = values["ATTEMPT_STARTED.json"]
    failure = values["QUALIFICATION_FAILED.json"]
    ownership = values["OWNERSHIP.json"]
    termination = values["TERMINATION_AUDIT.json"]
    frozen_termination = values["FROZEN_TERMINATION.json"]
    postdelete = values["POSTDELETE_INVENTORY.json"]
    packet = values["RECOVERY_EQUIVALENCE_PACKET.json"]
    verification = values["RECOVERY_EQUIVALENCE_VERIFICATION.json"]
    if (
        marker.get("status") != "attempt_started_irrevocably"
        or marker.get("qualification_protocol_version") != PREDECESSOR_PROTOCOL
        or marker.get("attempt_number") != 1
        or marker.get("retry_authorized") is not False
        or marker.get("authorized_raw_input_paths") != []
        or marker.get("model_forward_count") != 0
        or marker.get("target_prompt_render_count") != 0
        or failure.get("status") != "qualification_failed_attempt_consumed"
        or failure.get("started_at_unix") != marker.get("started_at_unix")
        or failure.get("qualification_deadline_at_unix")
        != marker.get("qualification_deadline_at_unix")
        or failure.get("error_type") != "RecoveryHostQualificationError"
        or failure.get("error_message") != "opened path is missing"
        or failure.get("raw_forbidden_attempt_count") != 2
        or failure.get("model_forward_count") != 0
        or failure.get("target_prompt_render_count") != 0
        or failure.get("retry_authorized") is not False
        or ownership.get("pod_id") != FAILED_POD_ID
        or ownership.get("network_volume_id") != "bv9gb9j32y"
        or termination.get("pod_id") != FAILED_POD_ID
        or termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("frozen_termination_receipt_sha256")
        != frozen_termination.get("receipt_sha256")
        or frozen_termination.get("status") != "deleted_verified"
        or frozen_termination.get("absent_from_account_inventory") is not True
        or frozen_termination.get("other_pods_mutated") is not False
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
        or packet.get("raw_run_opened") is not False
        or packet.get("compact_result_opened") is not False
        or packet.get("model_forward_count") != 0
        or packet.get("recovery_closure", {}).get("code_freeze_commit")
        != C1_CODE_FREEZE_COMMIT
        or verification.get("packet_sha256") != packet.get("packet_sha256")
        or verification.get("code_freeze_commit") != C1_CODE_FREEZE_COMMIT
    ):
        raise QualificationIncidentVerificationError(
            "retained incident semantics differ"
        )


def verify_incident(incident_dir: Path) -> dict[str, Any]:
    """Independently verify all retained metadata and the authored closure."""

    root = incident_dir.expanduser().absolute()
    if root.name != "audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up":
        raise QualificationIncidentVerificationError(
            "qualification incident namespace differs"
        )
    evidence, values = _immutable_evidence(root)
    _verify_historical_semantics(values)
    cause, cause_raw = _load(root / "INCIDENT_CAUSE.json", "incident cause")
    cause_receipt = _self_hash(cause, "receipt_sha256", "incident cause")
    schema, schema_raw = _load(root / "INCIDENT_CLOSURE_SCHEMA.json", "incident schema")
    closure, closure_raw = _load(root / "INCIDENT_CLOSURE.json", "incident closure")
    closure_receipt = _self_hash(closure, "receipt_sha256", "incident closure")
    stored, stored_raw = _load(
        root / "INCIDENT_CLOSURE_VERIFICATION.json",
        "stored incident verification",
    )
    stored_receipt = _self_hash(
        stored, "receipt_sha256", "stored incident verification"
    )
    physical_hashes = {
        "cause": hashlib.sha256(cause_raw).hexdigest(),
        "schema": hashlib.sha256(schema_raw).hexdigest(),
        "closure": hashlib.sha256(closure_raw).hexdigest(),
        "verification": hashlib.sha256(stored_raw).hexdigest(),
    }
    attempt = closure.get("attempt")
    successor = closure.get("successor_requirements")
    termination = closure.get("termination")
    cause_failed = cause.get("failed_attempt")
    cause_limits = cause.get("capture_limits")
    if (
        physical_hashes
        != {
            "cause": EXPECTED_CAUSE_FILE_SHA256,
            "schema": EXPECTED_SCHEMA_FILE_SHA256,
            "closure": EXPECTED_CLOSURE_FILE_SHA256,
            "verification": EXPECTED_VERIFICATION_FILE_SHA256,
        }
        or cause_receipt != EXPECTED_CAUSE_RECEIPT_SHA256
        or closure_receipt != EXPECTED_CLOSURE_RECEIPT_SHA256
        or stored_receipt != EXPECTED_VERIFICATION_RECEIPT_SHA256
        or cause.get("status")
        != "mechanical_guard_false_positive_reproduced_no_raw_access"
        or cause.get("incident_id") != INCIDENT_ID
        or not isinstance(cause_failed, Mapping)
        or cause_failed.get("pod_id") != FAILED_POD_ID
        or cause_failed.get("raw_forbidden_attempt_count_semantics")
        != "two_guard_false_positive_increments_not_evidence_of_raw_access"
        or cause_failed.get("raw_opened_or_recomputed") is not False
        or not isinstance(cause_limits, Mapping)
        or any(
            cause_limits.get(field) is not False
            for field in (
                "full_traceback_preserved",
                "exact_errno_preserved",
                "exact_triggering_path_preserved",
            )
        )
        or schema.get("$id")
        != "urn:llm-selfref-pre:signed-dose-scan:qualification-incident-closure:v1"
        or schema.get("additionalProperties") is not False
        or closure.get("status")
        != "closed_no_raw_no_forward_attempt_consumed_successor_required"
        or closure.get("incident_id") != INCIDENT_ID
        or closure.get("evidence_file_count") != 14
        or closure.get("evidence_inventory") != evidence
        or closure.get("cause_binding", {}).get("cause_file_sha256")
        != hashlib.sha256(cause_raw).hexdigest()
        or closure.get("cause_binding", {}).get("cause_receipt_sha256")
        != cause_receipt
        or not isinstance(attempt, Mapping)
        or attempt.get("attempt_consumed") is not True
        or attempt.get("global_qualification_ordinal") != 1
        or attempt.get("declared_raw_input_paths") != []
        or attempt.get("raw_access_classification")
        != "no_raw_argument_open_or_recomputation"
        or attempt.get("model_forward_count") != 0
        or attempt.get("target_prompt_render_count") != 0
        or attempt.get("retry_authorized") is not False
        or not isinstance(successor, Mapping)
        or successor.get("c2_direct_parent_commit") != C1_CODE_FREEZE_COMMIT
        or successor.get("global_qualification_ordinal") != 2
        or successor.get("successor_attempt_number") != 1
        or successor.get("retry_count") != 0
        or successor.get("qualification_protocol_version") != SUCCESSOR_PROTOCOL
        or successor.get("rejected_pod_ids") != REJECTED_POD_IDS
        or not isinstance(termination, Mapping)
        or termination.get("pod_id") != FAILED_POD_ID
        or termination.get("absent_from_account_inventory") is not True
        or termination.get("postdelete_account_pod_count") != 0
        or stored.get("status")
        != "pass_qualification_incident_independent_verification"
        or stored.get("cause_file_sha256")
        != hashlib.sha256(cause_raw).hexdigest()
        or stored.get("cause_receipt_sha256") != cause_receipt
        or stored.get("incident_closure_file_sha256")
        != hashlib.sha256(closure_raw).hexdigest()
        or stored.get("incident_closure_receipt_sha256") != closure_receipt
        or stored.get("incident_closure_schema_file_sha256")
        != hashlib.sha256(schema_raw).hexdigest()
        or stored.get("evidence_file_count") != 14
        or stored.get("evidence_inventory_sha256") != canonical_sha256(evidence)
        or stored.get("qualification_outcome_classification")
        != "no_raw_or_scientific_outcome_access"
        or stored.get("capture_gaps_acknowledged")
        != [
            "full_traceback",
            "exact_errno",
            "exact_triggering_path",
            "remote_guest_and_cache_preflight_receipts",
        ]
    ):
        raise QualificationIncidentVerificationError(
            "authored qualification incident semantics differ"
        )
    return {
        "status": "pass_qualification_incident_independently_bound_for_v2",
        "incident_id": INCIDENT_ID,
        "incident_directory": root.as_posix(),
        "predecessor_pod_id": FAILED_POD_ID,
        "predecessor_failure_receipt_sha256": EXPECTED_FILES[
            "QUALIFICATION_FAILED.json"
        ][3],
        "incident_cause_file_sha256": physical_hashes["cause"],
        "incident_cause_receipt_sha256": cause_receipt,
        "incident_schema_file_sha256": physical_hashes["schema"],
        "incident_closure_file_sha256": physical_hashes["closure"],
        "incident_closure_receipt_sha256": closure_receipt,
        "incident_verification_file_sha256": physical_hashes["verification"],
        "incident_verification_receipt_sha256": stored_receipt,
        "evidence_file_count": len(evidence),
        "evidence_inventory_sha256": canonical_sha256(evidence),
        "predecessor_global_qualification_ordinal": 1,
        "global_qualification_ordinal": 2,
        "successor_qualification_attempt": 1,
        "retry_authorized": False,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "raw_run_opened": False,
        "compact_result_opened": False,
        "analysis_data_inputs": [],
    }


def successor_authority_binding(
    incident_dir: Path, recovery_cycle_ledger_path: Path
) -> dict[str, Any]:
    """Independently bind the incident to the frozen v2 cycle ledger."""

    incident = verify_incident(incident_dir)
    ledger, ledger_raw = _load(
        recovery_cycle_ledger_path, "successor recovery cycle ledger"
    )
    ledger_receipt = _self_hash(
        ledger, "receipt_sha256", "successor recovery cycle ledger"
    )
    ledger_file_sha = hashlib.sha256(ledger_raw).hexdigest()
    lineage = ledger.get("lineage_contract")
    limits = ledger.get("time_and_cost_limits")
    usage = ledger.get("usage_at_freeze")
    cardinality = ledger.get("cardinality_limits")
    binding = ledger.get("incident_binding")
    if (
        ledger_file_sha != EXPECTED_LEDGER_FILE_SHA256
        or ledger_receipt != EXPECTED_LEDGER_RECEIPT_SHA256
        or ledger.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_recovery_cycle_ledger_v2"
        or ledger.get("status") != "frozen_successor_cycle_authorized_pending_c2"
        or ledger.get("cycle_id") != SUCCESSOR_CYCLE_ID
        or ledger.get("recovery_protocol_version")
        != "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v2"
        or not isinstance(lineage, Mapping)
        or lineage.get("c1_commit") != C1_CODE_FREEZE_COMMIT
        or lineage.get("global_qualification_ordinal") != 2
        or lineage.get("successor_qualification_attempt_number") != 1
        or lineage.get("rejected_pod_ids") != REJECTED_POD_IDS
        or lineage.get("c1_to_c2")
        != "direct_single_parent_with_exact_status_map"
        or lineage.get("c2_to_e2")
        != "direct_single_parent_exactly_eight_added_qualification_receipts"
        or lineage.get("e2_to_f2")
        != "direct_single_parent_exactly_eight_added_cumulative_review_artifacts"
        or not isinstance(cardinality, Mapping)
        or cardinality.get("replacement_target_qualification_attempts") != 1
        or cardinality.get("automatic_retries") != 0
        or not isinstance(usage, Mapping)
        or usage.get("predecessor_target_qualification_attempts_consumed") != 1
        or usage.get("replacement_target_qualification_attempts_used") != 0
        or usage.get("automatic_retries_used") != 0
        or not isinstance(limits, Mapping)
        or limits.get("replacement_qualification_cap_seconds") != 1800
        or limits.get("replacement_qualification_cap_usd") != "3.00"
        or limits.get("successor_deadline_utc") != "2026-07-17T12:00:00Z"
        or not isinstance(binding, Mapping)
        or binding.get("qualification_pod_id") != FAILED_POD_ID
        or binding.get("qualification_status")
        != "qualification_failed_attempt_consumed"
        or binding.get("qualification_incident_cause_file_sha256")
        != incident["incident_cause_file_sha256"]
        or binding.get("qualification_incident_cause_receipt_sha256")
        != incident["incident_cause_receipt_sha256"]
        or binding.get("qualification_incident_closure_file_sha256")
        != incident["incident_closure_file_sha256"]
        or binding.get("qualification_incident_closure_receipt_sha256")
        != incident["incident_closure_receipt_sha256"]
        or binding.get("qualification_incident_schema_file_sha256")
        != incident["incident_schema_file_sha256"]
        or binding.get("qualification_incident_verification_file_sha256")
        != incident["incident_verification_file_sha256"]
        or binding.get("qualification_incident_verification_receipt_sha256")
        != incident["incident_verification_receipt_sha256"]
    ):
        raise QualificationIncidentVerificationError(
            "successor recovery cycle ledger differs"
        )
    core = {
        "status": "pass_qualification_incident_and_v2_cycle_bound",
        "incident_id": INCIDENT_ID,
        "predecessor_pod_id": FAILED_POD_ID,
        "predecessor_failure_receipt_sha256": incident[
            "predecessor_failure_receipt_sha256"
        ],
        "incident_cause_file_sha256": incident["incident_cause_file_sha256"],
        "incident_cause_receipt_sha256": incident[
            "incident_cause_receipt_sha256"
        ],
        "incident_schema_file_sha256": incident["incident_schema_file_sha256"],
        "incident_closure_file_sha256": incident[
            "incident_closure_file_sha256"
        ],
        "incident_closure_receipt_sha256": incident[
            "incident_closure_receipt_sha256"
        ],
        "incident_verification_file_sha256": incident[
            "incident_verification_file_sha256"
        ],
        "incident_verification_receipt_sha256": incident[
            "incident_verification_receipt_sha256"
        ],
        "recovery_cycle_id": SUCCESSOR_CYCLE_ID,
        "recovery_cycle_ledger_file_sha256": ledger_file_sha,
        "recovery_cycle_ledger_receipt_sha256": ledger_receipt,
        "predecessor_global_qualification_ordinal": 1,
        "global_qualification_ordinal": 2,
        "successor_qualification_attempt": 1,
        "retry_authorized": False,
        "rejected_pod_ids": REJECTED_POD_IDS,
        "successor_deadline_utc": "2026-07-17T12:00:00Z",
    }
    return {**core, "binding_sha256": canonical_sha256(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident-dir", type=Path, required=True)
    parser.add_argument("--recovery-cycle-ledger", type=Path)
    args = parser.parse_args()
    value = (
        successor_authority_binding(
            args.incident_dir, args.recovery_cycle_ledger
        )
        if args.recovery_cycle_ledger is not None
        else verify_incident(args.incident_dir)
    )
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
