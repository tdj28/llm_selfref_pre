#!/usr/bin/env python3
"""Bind the consumed C1 host-qualification incident for the v2 successor.

This module reads metadata-only receipts.  It has no raw-run argument and does
not import the independent verifier.  The historical v1 guard counter is
classified from the retained zero-forward/no-raw evidence and the deterministic
ENOTDIR regression; it is not reinterpreted as evidence that raw data opened.
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
ORIGINAL_FREEZE_COMMIT = "a084caafc2ec27860044d80d3b33912f656fd08a"
FAILED_POD_ID = "69d9kxugxuf6up"
REJECTED_POD_IDS = ["wl8obvtuq0ax8t", FAILED_POD_ID]
PREDECESSOR_QUALIFICATION_PROTOCOL = (
    "consciousness_sae_signed_dose_scan_v1."
    "audit_recovery_host_qualification_v1"
)
SUCCESSOR_QUALIFICATION_PROTOCOL = (
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
C2_INCIDENT_DIRECTORY_NAME = (
    "audit_recovery_qualification_incident_79db4e7_g2azyjkpm17f1s"
)
C2_INCIDENT_ID = "qualification-79db4e7-g2azyjkpm17f1s"
C2_CODE_FREEZE_COMMIT = "79db4e7526948a3c826e3dc62adbf2895a5b5528"
C2_FAILED_POD_ID = "g2azyjkpm17f1s"
C3_REJECTED_POD_IDS = ["wl8obvtuq0ax8t", "69d9kxugxuf6up", C2_FAILED_POD_ID]
C3_CYCLE_ID = "signed-dose-audit-only-recovery-v3-20260717"
C3_AUTHORITY_STATEMENT = (
    "Authorize C3 and augment the experiment skill with lesson learned"
)
C3_AUTHORITY_BINDING_SHA256 = (
    "f4358f97989936e3a4c366568a3a5acb54f1f144eff082be1df9a11bd9e55950"
)
C3_LEDGER_FILE_SHA256 = (
    "b2d28577a4e985b7922290b7def34a43f36a9b68feea8dc1f28a707663280a1c"
)
C3_LEDGER_RECEIPT_SHA256 = (
    "cbe07edf29f2068f346957c1639ace2f1c985b6df93dd540c464bbc79d35925d"
)
C3_STATUS_MAP_FILE_SHA256 = (
    "b9c6c95938332e4f34071879a548f9450185386895c6dbaf16065a597397cd2e"
)
C3_STATUS_MAP_RECEIPT_SHA256 = (
    "d53847535b6ccdf56f19b0094ac146b5093bc1d4ccfccaf153dceb32db0f1d59"
)
C2_CAUSE_FILE_SHA256 = (
    "8bc3b88be6d47f827def12bb4db2f4340d8451ce71d106dbaf2a07b749daf321"
)
C2_CAUSE_RECEIPT_SHA256 = (
    "547aedaf4e9daca603355c4d67d5f946568462634080881bd58c8d6601210628"
)
C2_SCHEMA_FILE_SHA256 = (
    "f6f2fe4dacd3e460e9fe210d5c90d20df8ec46120a7dac825ba32ca00d3e0229"
)
C2_CLOSURE_FILE_SHA256 = (
    "eb2c13f8c8a62d36af41af773ae2e828409124a9d4ee988eecfad1a7f12a9c72"
)
C2_CLOSURE_RECEIPT_SHA256 = (
    "599a712f93fecca1e1007b88a5403de2ed84b76fd6c12c2d273e279e9c979fab"
)
C2_VERIFICATION_FILE_SHA256 = (
    "d7053fed05db4d48f47830accb1ebf365fde9315d213b7b5d80f9975015f0643"
)
C2_VERIFICATION_RECEIPT_SHA256 = (
    "7c080c426e5e1da99b35c1b5c0e2a152b9b98a2f71a2ab12eedca3ab0fed1e2e"
)

# These are immutable copied receipts, not authored closure files.  The
# independent verifier restates the inventory rather than importing it.
EVIDENCE_SPECS = {
    "ATTEMPT_STARTED.json": (
        "irreversible_attempt_marker",
        1394,
        "7e6e1e9fbeea88496dbbe2c0576ca50f2a127cddafaa1148f96fc739f2c5c36e",
        "3697f376dc4477298057cf80b226e790a57f10b426872384ebe7df36ed071b1f",
        "receipt_sha256",
    ),
    "FROZEN_OWNERSHIP.json": (
        "provider_lifecycle_ownership",
        3048,
        "012f0307c1b9c82c4a176a109140472e745b9766db588cdb5f6d898e11bbb6d8",
        "a31bc98e802a68f83a6f46abd8508f9d6a33d7280ca211dbc6f7ca1fbefb0e2c",
        "receipt_sha256",
    ),
    "FROZEN_STATUS_0001.json": (
        "provider_lifecycle_status",
        1133,
        "93cb738d2707e85873e66b74b9cf44865471f6723de59402ae8f3716ebc8078f",
        "590c273fe24d2fae530cb2a781fbd7f98162c04a368d6938e03d3a50af336722",
        "receipt_sha256",
    ),
    "FROZEN_TERMINATION.json": (
        "provider_lifecycle_termination",
        1432,
        "1e04f948832913f26f244e508d99d6715d5bca8caef8e0edf3661291fda7824b",
        "204937720933c5416edaff36ed21fe5aa677e568c165a0515d3cda8ea8c62a02",
        "receipt_sha256",
    ),
    "OWNERSHIP.json": (
        "successor_ownership_link",
        1665,
        "02f6766a37a13b6667a85963f0d81261f88e0443d515bcaedef6b15586f9f886",
        "3bb3f027471a0d4cf64e68baedf5d7d46fedd758bab39fa61f85e0805d6686f6",
        "receipt_sha256",
    ),
    "POSTCREATE_INVENTORY.json": (
        "postcreate_account_inventory",
        685,
        "281cb57df69e20b946ab81dd49243f973facb9a9f586ddbb2d5da222b0c0c3fb",
        "583efb6a7c292819776dd331058f08bb89c1d3418f61b609c5bc997387c273e6",
        "receipt_sha256",
    ),
    "POSTDELETE_INVENTORY.json": (
        "postdelete_account_inventory",
        493,
        "674c773a0bebe7529e107ec13469b2c82346403a24aec766d5db1640a4f74d31",
        "bb9e841ac751ccf597eadae687d122c85a8b1ab42849ab9c25f568fa4bb5a723",
        "receipt_sha256",
    ),
    "PRECREATE_INVENTORY.json": (
        "precreate_account_inventory",
        492,
        "6e8587f69f61a548480797001054d804456a68ec1594ed1e034c2e63f16ca899",
        "5b2871ad96e2bea7e5dd7d502f633c5252656280ebf9d61d5077092cca5e0eaa",
        "receipt_sha256",
    ),
    "QUALIFICATION_FAILED.json": (
        "terminal_qualification_failure",
        701,
        "62adf28eefac008b83b6f888081bd17fbb357fb816918bdbfac7444490eef845",
        "b943f602fc6d3015aa7f14481534ebf1be3165618067e7deaf2e53482208a18f",
        "receipt_sha256",
    ),
    "READY.json": (
        "exact_owned_pod_ready",
        437,
        "f926d29abe6f5ec2b9a18dd152d20f69c424f5284d28ab7e184c972a6158b3b8",
        "291a7271106d0147e8ec883a605e00b7112a1b0b097db6ea1b7b7180e1bd5bd3",
        "receipt_sha256",
    ),
    "RECOVERY_EQUIVALENCE_PACKET.json": (
        "c1_outcome_blind_equivalence_packet",
        28139,
        "db05894140be57d89f2de4821860b5f3b217527caf443e129e0c3293c075f476",
        "826b1dba22cb358ca86f7353ed702b05433ff2c5743cace76f1937c6a88d9919",
        "packet_sha256",
    ),
    "RECOVERY_EQUIVALENCE_VERIFICATION.json": (
        "c1_independent_equivalence_verification",
        1029,
        "3d3be8a9ca776a977c72d3b52474ff287ef5fa9ce47d952253536891bb58fdf6",
        "16f4d6fcc16fcb4f77b372da17f7bbb40b64eb7fa134fd6c986109f58b890de1",
        "receipt_sha256",
    ),
    "STATUS_0001.json": (
        "successor_status_link",
        742,
        "ffb8526732740792915a2573d1c8779a2adc726dac0558f221086a981eb4a683",
        "13cefdf6e69e9b4e14303460fcf4b6a479fe0ea27b79adc88e24ec3aeac1a8b1",
        "receipt_sha256",
    ),
    "TERMINATION_AUDIT.json": (
        "independent_exact_pod_termination_audit",
        777,
        "33fdc503aef82c5f2071ae84663329f05e1a876f114498be1df8b6c5a3453715",
        "89e33501b1241f6e79a52796012043f1de46162db0fadd6a4433dabdf4c6dbc0",
        "receipt_sha256",
    ),
}


class QualificationIncidentError(RuntimeError):
    """The retained qualification incident or successor binding differs."""


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
        raise QualificationIncidentError(f"{label} is unreadable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
        or raw != canonical_json_bytes(value) + b"\n"
    ):
        raise QualificationIncidentError(
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
        raise QualificationIncidentError(f"{label} self-hash differs")
    return supplied


def _evidence(incident_dir: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    values: dict[str, dict[str, Any]] = {}
    for name, (role, expected_bytes, expected_sha, expected_receipt, field) in sorted(
        EVIDENCE_SPECS.items()
    ):
        value, raw = _load(incident_dir / name, f"incident evidence {name}")
        file_sha = hashlib.sha256(raw).hexdigest()
        receipt = _self_hash(value, field, f"incident evidence {name}")
        if (
            len(raw) != expected_bytes
            or file_sha != expected_sha
            or receipt != expected_receipt
        ):
            raise QualificationIncidentError(f"incident evidence differs: {name}")
        values[name] = value
        rows.append(
            {
                "bytes": len(raw),
                "content_receipt_sha256": receipt,
                "relative_name": name,
                "role": role,
                "sha256": file_sha,
            }
        )
    return rows, values


def _validate_evidence_semantics(values: Mapping[str, Mapping[str, Any]]) -> None:
    marker = values["ATTEMPT_STARTED.json"]
    failure = values["QUALIFICATION_FAILED.json"]
    packet = values["RECOVERY_EQUIVALENCE_PACKET.json"]
    equivalence = values["RECOVERY_EQUIVALENCE_VERIFICATION.json"]
    ownership = values["OWNERSHIP.json"]
    frozen_ownership = values["FROZEN_OWNERSHIP.json"]
    status = values["STATUS_0001.json"]
    frozen_status = values["FROZEN_STATUS_0001.json"]
    ready = values["READY.json"]
    precreate = values["PRECREATE_INVENTORY.json"]
    postcreate = values["POSTCREATE_INVENTORY.json"]
    termination = values["TERMINATION_AUDIT.json"]
    frozen_termination = values["FROZEN_TERMINATION.json"]
    postdelete = values["POSTDELETE_INVENTORY.json"]
    if (
        marker.get("status") != "attempt_started_irrevocably"
        or marker.get("qualification_protocol_version")
        != PREDECESSOR_QUALIFICATION_PROTOCOL
        or marker.get("attempt_number") != 1
        or marker.get("retry_authorized") is not False
        or marker.get("authorized_raw_input_paths") != []
        or marker.get("model_forward_count") != 0
        or marker.get("target_prompt_render_count") != 0
        or failure.get("status") != "qualification_failed_attempt_consumed"
        or failure.get("qualification_protocol_version")
        != PREDECESSOR_QUALIFICATION_PROTOCOL
        or failure.get("attempt_number") != 1
        or failure.get("retry_authorized") is not False
        or failure.get("started_at_unix") != marker.get("started_at_unix")
        or failure.get("qualification_deadline_at_unix")
        != marker.get("qualification_deadline_at_unix")
        or failure.get("error_type") != "RecoveryHostQualificationError"
        or failure.get("error_message") != "opened path is missing"
        or failure.get("raw_forbidden_attempt_count") != 2
        or failure.get("model_forward_count") != 0
        or failure.get("target_prompt_render_count") != 0
        or packet.get("status")
        != "pass_source_design_and_compatibility_bound_no_outcomes_loaded"
        or packet.get("raw_run_opened") is not False
        or packet.get("compact_result_opened") is not False
        or packet.get("model_forward_count") != 0
        or packet.get("recovery_closure", {}).get("code_freeze_commit")
        != C1_CODE_FREEZE_COMMIT
        or equivalence.get("status")
        != "pass_outcome_blind_recovery_equivalence_verified"
        or equivalence.get("packet_sha256") != packet.get("packet_sha256")
        or equivalence.get("code_freeze_commit") != C1_CODE_FREEZE_COMMIT
    ):
        raise QualificationIncidentError("failed qualification semantics differ")
    empty_inventory = canonical_sha256([])
    postcreate_pods = postcreate.get("pods")
    if (
        ownership.get("pod_id") != FAILED_POD_ID
        or ownership.get("network_volume_id") != "bv9gb9j32y"
        or ownership.get("gpu_type") != "NVIDIA B200"
        or ownership.get("gpu_count") != 1
        or ownership.get("upstream_lifecycle_receipt_sha256")
        != frozen_ownership.get("receipt_sha256")
        or frozen_ownership.get("pod", {}).get("id") != FAILED_POD_ID
        or frozen_ownership.get("pod", {}).get("cost_per_hour_usd") != "5.89"
        or status.get("pod_id") != FAILED_POD_ID
        or status.get("frozen_status_receipt_sha256")
        != frozen_status.get("receipt_sha256")
        or status.get("successor_ownership_receipt_sha256")
        != ownership.get("receipt_sha256")
        or frozen_status.get("pod", {}).get("id") != FAILED_POD_ID
        or ready.get("pod_id") != FAILED_POD_ID
        or ready.get("status_receipt_sha256") != status.get("receipt_sha256")
        or precreate.get("pods") != []
        or precreate.get("inventory_sha256") != empty_inventory
        or not isinstance(postcreate_pods, list)
        or len(postcreate_pods) != 1
        or postcreate_pods[0].get("pod_id") != FAILED_POD_ID
        or frozen_termination.get("pod_id") != FAILED_POD_ID
        or frozen_termination.get("status") != "deleted_verified"
        or frozen_termination.get("absent_from_account_inventory") is not True
        or frozen_termination.get("other_pods_mutated") is not False
        or termination.get("pod_id") != FAILED_POD_ID
        or termination.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination.get("frozen_termination_receipt_sha256")
        != frozen_termination.get("receipt_sha256")
        or termination.get("precreate_inventory_sha256") != empty_inventory
        or termination.get("postdelete_inventory_sha256") != empty_inventory
        or postdelete.get("pods") != []
        or postdelete.get("all_account_pod_count") != 0
        or postdelete.get("inventory_sha256") != empty_inventory
    ):
        raise QualificationIncidentError("provider lifecycle semantics differ")


def _validate_cause(cause: Mapping[str, Any], failure: Mapping[str, Any]) -> str:
    receipt = _self_hash(cause, "receipt_sha256", "qualification incident cause")
    failed = cause.get("failed_attempt")
    limits = cause.get("capture_limits")
    boundary = cause.get("fix_boundary")
    reproduction = cause.get("reproduction_basis")
    if (
        cause.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_qualification_incident_cause_v1"
        or cause.get("status")
        != "mechanical_guard_false_positive_reproduced_no_raw_access"
        or cause.get("incident_id") != INCIDENT_ID
        or cause.get("cause_class")
        != "optional_nonexistent_path_probe_below_regular_file_component_misclassified_as_missing_and_forbidden"
        or cause.get("cause_confidence")
        != "reproducible_bug_class_not_preserved_traceback"
        or not isinstance(failed, Mapping)
        or failed.get("pod_id") != FAILED_POD_ID
        or failed.get("error_type") != failure.get("error_type")
        or failed.get("error_message") != failure.get("error_message")
        or failed.get("raw_forbidden_attempt_count") != 2
        or failed.get("raw_forbidden_attempt_count_semantics")
        != "two_guard_false_positive_increments_not_evidence_of_raw_access"
        or failed.get("raw_input_argument_present") is not False
        or failed.get("raw_opened_or_recomputed") is not False
        or failed.get("model_forward_count") != 0
        or failed.get("target_prompt_render_count") != 0
        or not isinstance(limits, Mapping)
        or limits.get("full_traceback_preserved") is not False
        or limits.get("exact_errno_preserved") is not False
        or limits.get("exact_triggering_path_preserved") is not False
        or not isinstance(boundary, Mapping)
        or boundary.get("lexical_raw_containment_still_rejected") is not True
        or boundary.get("must_exist_true_still_rejects") is not True
        or boundary.get("symlink_components_still_rejected") is not True
        or not isinstance(reproduction, Mapping)
        or reproduction.get("c1_code_freeze_commit") != C1_CODE_FREEZE_COMMIT
        or reproduction.get("deterministic_positive_reproduction")
        != "regular_file_egg_info_child_probe_with_must_exist_false"
    ):
        raise QualificationIncidentError("qualification incident cause differs")
    return receipt


def _validate_schema(schema: Mapping[str, Any]) -> None:
    if (
        schema.get("$id")
        != "urn:llm-selfref-pre:signed-dose-scan:qualification-incident-closure:v1"
        or schema.get("additionalProperties") is not False
        or set(schema.get("required", []))
        != {
            "accounting",
            "attempt",
            "capture_gaps",
            "cause_binding",
            "evidence_file_count",
            "evidence_inventory",
            "incident_id",
            "lineage",
            "receipt_kind",
            "receipt_sha256",
            "schema_version",
            "status",
            "study_id",
            "successor_requirements",
            "termination",
        }
    ):
        raise QualificationIncidentError("qualification incident schema differs")


def _validate_closure(
    closure: Mapping[str, Any],
    *,
    evidence: list[dict[str, Any]],
    cause_file_sha: str,
    cause_receipt: str,
) -> str:
    receipt = _self_hash(closure, "receipt_sha256", "qualification incident closure")
    attempt = closure.get("attempt")
    successor = closure.get("successor_requirements")
    termination = closure.get("termination")
    cause_binding = closure.get("cause_binding")
    capture_gaps = closure.get("capture_gaps")
    if (
        closure.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_qualification_incident_closure_v1"
        or closure.get("status")
        != "closed_no_raw_no_forward_attempt_consumed_successor_required"
        or closure.get("incident_id") != INCIDENT_ID
        or closure.get("evidence_file_count") != 14
        or closure.get("evidence_inventory") != evidence
        or not isinstance(attempt, Mapping)
        or attempt.get("attempt_consumed") is not True
        or attempt.get("global_qualification_ordinal") != 1
        or attempt.get("retry_authorized") is not False
        or attempt.get("declared_raw_input_paths") != []
        or attempt.get("raw_access_classification")
        != "no_raw_argument_open_or_recomputation"
        or attempt.get("model_forward_count") != 0
        or attempt.get("target_prompt_render_count") != 0
        or not isinstance(successor, Mapping)
        or successor.get("c2_direct_parent_commit") != C1_CODE_FREEZE_COMMIT
        or successor.get("global_qualification_ordinal") != 2
        or successor.get("successor_attempt_number") != 1
        or successor.get("retry_count") != 0
        or successor.get("qualification_protocol_version")
        != SUCCESSOR_QUALIFICATION_PROTOCOL
        or successor.get("successor_cycle_id") != SUCCESSOR_CYCLE_ID
        or successor.get("rejected_pod_ids") != REJECTED_POD_IDS
        or not isinstance(termination, Mapping)
        or termination.get("pod_id") != FAILED_POD_ID
        or termination.get("absent_from_account_inventory") is not True
        or termination.get("postdelete_account_pod_count") != 0
        or not isinstance(cause_binding, Mapping)
        or cause_binding.get("cause_file_sha256") != cause_file_sha
        or cause_binding.get("cause_receipt_sha256") != cause_receipt
        or not isinstance(capture_gaps, list)
        or [row.get("field") for row in capture_gaps if isinstance(row, Mapping)]
        != [
            "full_traceback",
            "exact_errno",
            "exact_triggering_path",
            "remote_guest_and_cache_preflight_receipts",
        ]
        or any(row.get("preserved") is not False for row in capture_gaps)
    ):
        raise QualificationIncidentError("qualification incident closure differs")
    return receipt


def validate_incident(incident_dir: Path) -> dict[str, Any]:
    """Validate the complete retained incident and return a compact binding."""

    root = incident_dir.expanduser().absolute()
    if root.name != "audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up":
        raise QualificationIncidentError("qualification incident namespace differs")
    evidence, values = _evidence(root)
    _validate_evidence_semantics(values)
    cause, cause_raw = _load(root / "INCIDENT_CAUSE.json", "incident cause")
    cause_receipt = _validate_cause(cause, values["QUALIFICATION_FAILED.json"])
    schema, schema_raw = _load(root / "INCIDENT_CLOSURE_SCHEMA.json", "incident schema")
    _validate_schema(schema)
    closure, closure_raw = _load(root / "INCIDENT_CLOSURE.json", "incident closure")
    closure_receipt = _validate_closure(
        closure,
        evidence=evidence,
        cause_file_sha=hashlib.sha256(cause_raw).hexdigest(),
        cause_receipt=cause_receipt,
    )
    stored, stored_raw = _load(
        root / "INCIDENT_CLOSURE_VERIFICATION.json",
        "incident independent verification",
    )
    stored_receipt = _self_hash(
        stored,
        "receipt_sha256",
        "incident independent verification",
    )
    physical_hashes = {
        "cause": hashlib.sha256(cause_raw).hexdigest(),
        "schema": hashlib.sha256(schema_raw).hexdigest(),
        "closure": hashlib.sha256(closure_raw).hexdigest(),
        "verification": hashlib.sha256(stored_raw).hexdigest(),
    }
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
        or stored.get("evidence_file_count") != len(evidence)
        or stored.get("evidence_inventory_sha256") != canonical_sha256(evidence)
        or stored.get("qualification_outcome_classification")
        != "no_raw_or_scientific_outcome_access"
    ):
        raise QualificationIncidentError(
            "stored qualification incident verification differs"
        )
    return {
        "status": "pass_qualification_incident_bound_for_v2_successor",
        "incident_id": INCIDENT_ID,
        "incident_directory": root.as_posix(),
        "predecessor_pod_id": FAILED_POD_ID,
        "predecessor_failure_receipt_sha256": EVIDENCE_SPECS[
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
    """Bind the closed incident to the exact v2 no-retry cycle ledger."""

    incident = validate_incident(incident_dir)
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
    incident_binding = ledger.get("incident_binding")
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
        or not isinstance(incident_binding, Mapping)
        or incident_binding.get("qualification_pod_id") != FAILED_POD_ID
        or incident_binding.get("qualification_status")
        != "qualification_failed_attempt_consumed"
        or incident_binding.get("qualification_incident_cause_file_sha256")
        != incident["incident_cause_file_sha256"]
        or incident_binding.get("qualification_incident_cause_receipt_sha256")
        != incident["incident_cause_receipt_sha256"]
        or incident_binding.get("qualification_incident_closure_file_sha256")
        != incident["incident_closure_file_sha256"]
        or incident_binding.get("qualification_incident_closure_receipt_sha256")
        != incident["incident_closure_receipt_sha256"]
        or incident_binding.get("qualification_incident_schema_file_sha256")
        != incident["incident_schema_file_sha256"]
        or incident_binding.get("qualification_incident_verification_file_sha256")
        != incident["incident_verification_file_sha256"]
        or incident_binding.get(
            "qualification_incident_verification_receipt_sha256"
        )
        != incident["incident_verification_receipt_sha256"]
    ):
        raise QualificationIncidentError("successor recovery cycle ledger differs")
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


def _load_exact_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    """Load an exact physically anchored JSON object, independent of layout."""

    candidate = path.expanduser().absolute()
    try:
        details = candidate.lstat()
        raw = candidate.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationIncidentError(f"{label} is unreadable") from exc
    if (
        not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
        or not isinstance(value, dict)
    ):
        raise QualificationIncidentError(f"{label} is not single-link JSON")
    return value, raw


def _validate_c2_incident_for_c3(incident_dir: Path) -> dict[str, Any]:
    """Authenticate the consumed C2 qualification without opening outcomes."""

    root = incident_dir.expanduser().absolute()
    if root.name != C2_INCIDENT_DIRECTORY_NAME:
        raise QualificationIncidentError("C2 qualification namespace differs")
    cause, cause_raw = _load_exact_json(
        root / "INCIDENT_CAUSE.json", "C2 incident cause"
    )
    schema, schema_raw = _load_exact_json(
        root / "INCIDENT_CLOSURE_SCHEMA.json", "C2 incident schema"
    )
    closure, closure_raw = _load_exact_json(
        root / "INCIDENT_CLOSURE.json", "C2 incident closure"
    )
    verification, verification_raw = _load_exact_json(
        root / "INCIDENT_CLOSURE_VERIFICATION.json",
        "C2 incident verification",
    )
    cause_receipt = _self_hash(cause, "receipt_sha256", "C2 incident cause")
    closure_receipt = _self_hash(
        closure, "receipt_sha256", "C2 incident closure"
    )
    verification_receipt = _self_hash(
        verification, "receipt_sha256", "C2 incident verification"
    )
    physical = {
        "cause": hashlib.sha256(cause_raw).hexdigest(),
        "schema": hashlib.sha256(schema_raw).hexdigest(),
        "closure": hashlib.sha256(closure_raw).hexdigest(),
        "verification": hashlib.sha256(verification_raw).hexdigest(),
    }
    evidence = closure.get("evidence_inventory")
    if not isinstance(evidence, list) or len(evidence) != 17:
        raise QualificationIncidentError("C2 evidence inventory differs")
    loaded: dict[str, Mapping[str, Any]] = {}
    for row in evidence:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {"name", "role", "bytes", "physical_sha256", "content_sha256"}
            or not isinstance(row.get("name"), str)
            or Path(str(row["name"])).name != row["name"]
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] < 0
            or HEX64.fullmatch(str(row.get("physical_sha256", ""))) is None
        ):
            raise QualificationIncidentError("C2 evidence row differs")
        path = root / str(row["name"])
        try:
            details = path.lstat()
            raw = path.read_bytes()
        except OSError as exc:
            raise QualificationIncidentError("C2 evidence is unreadable") from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or len(raw) != row["bytes"]
            or hashlib.sha256(raw).hexdigest() != row["physical_sha256"]
        ):
            raise QualificationIncidentError("C2 evidence physical hash differs")
        content_hash = row.get("content_sha256")
        if content_hash is None:
            if row["name"] != "QUALIFICATION_STDERR.log":
                raise QualificationIncidentError("C2 unhashed-content role differs")
            continue
        if HEX64.fullmatch(str(content_hash)) is None:
            raise QualificationIncidentError("C2 evidence content hash differs")
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise QualificationIncidentError("C2 evidence JSON differs") from exc
        field = (
            "packet_sha256"
            if row["name"] == "RECOVERY_EQUIVALENCE_PACKET.json"
            else "receipt_sha256"
        )
        if (
            not isinstance(value, Mapping)
            or raw != canonical_json_bytes(value) + b"\n"
            or _self_hash(value, field, f"C2 evidence {row['name']}")
            != content_hash
        ):
            raise QualificationIncidentError("C2 evidence self hash differs")
        loaded[str(row["name"])] = value
    attempt = closure.get("attempt")
    successor = closure.get("successor_requirements")
    termination = closure.get("termination")
    failure = loaded.get("QUALIFICATION_FAILED.json")
    if (
        physical
        != {
            "cause": C2_CAUSE_FILE_SHA256,
            "schema": C2_SCHEMA_FILE_SHA256,
            "closure": C2_CLOSURE_FILE_SHA256,
            "verification": C2_VERIFICATION_FILE_SHA256,
        }
        or cause_receipt != C2_CAUSE_RECEIPT_SHA256
        or closure_receipt != C2_CLOSURE_RECEIPT_SHA256
        or verification_receipt != C2_VERIFICATION_RECEIPT_SHA256
        or schema.get("additionalProperties") is not False
        or closure.get("incident_id") != C2_INCIDENT_ID
        or closure.get("status")
        != "closed_no_raw_no_forward_attempt_consumed_fresh_c3_authority_required"
        or not isinstance(attempt, Mapping)
        or attempt.get("pod_id") != C2_FAILED_POD_ID
        or attempt.get("global_qualification_ordinal") != 2
        or attempt.get("attempt_number") != 1
        or attempt.get("retry_authorized") is not False
        or attempt.get("declared_raw_input_paths") != []
        or attempt.get("raw_opened_or_recomputed") is not False
        or attempt.get("model_forward_count") != 0
        or attempt.get("target_prompt_render_count") != 0
        or attempt.get("zero_forward_guard_total") != 0
        or not isinstance(failure, Mapping)
        or failure.get("status") != "qualification_failed_attempt_consumed"
        or failure.get("global_qualification_ordinal") != 2
        or failure.get("retry_authorized") is not False
        or failure.get("raw_forbidden_attempt_count") != 0
        or failure.get("model_forward_count") != 0
        or failure.get("target_prompt_render_count") != 0
        or not isinstance(successor, Mapping)
        or successor.get("global_qualification_ordinal") != 3
        or successor.get("successor_attempt_number") != 1
        or successor.get("retry_count") != 0
        or successor.get("rejected_pod_ids") != C3_REJECTED_POD_IDS
        or not isinstance(termination, Mapping)
        or termination.get("pod_id") != C2_FAILED_POD_ID
        or termination.get("absent_from_account_inventory") is not True
        or termination.get("other_pods_mutated") is not False
        or verification.get("status")
        != "pass_c2_qualification_incident_independent_verification_for_fresh_c3_authority"
        or verification.get("incident_closure_file_sha256")
        != C2_CLOSURE_FILE_SHA256
        or verification.get("incident_closure_receipt_sha256")
        != C2_CLOSURE_RECEIPT_SHA256
        or verification.get("evidence_file_count") != 17
        or verification.get("qualification_outcome_classification")
        != "no_raw_or_scientific_outcome_access"
    ):
        raise QualificationIncidentError("C2 incident semantics differ")
    return {
        "incident_id": C2_INCIDENT_ID,
        "predecessor_pod_id": C2_FAILED_POD_ID,
        "closure_file_sha256": physical["closure"],
        "closure_receipt_sha256": closure_receipt,
        "closure_verification_file_sha256": physical["verification"],
        "closure_verification_receipt_sha256": verification_receipt,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "raw_run_opened": False,
    }


def successor_c3_authority_binding(
    incident_dir: Path, recovery_cycle_ledger_path: Path
) -> dict[str, Any]:
    """Bind the closed C2 incident to explicit, one-shot C3 authority."""

    incident = _validate_c2_incident_for_c3(incident_dir)
    ledger, ledger_raw = _load_exact_json(
        recovery_cycle_ledger_path, "C3 recovery cycle ledger"
    )
    status_map, status_raw = _load_exact_json(
        recovery_cycle_ledger_path.parent / "RECOVERY_C3_STATUS_MAP.json",
        "C3 status map",
    )
    ledger_receipt = _self_hash(
        ledger, "receipt_sha256", "C3 recovery cycle ledger"
    )
    status_receipt = _self_hash(status_map, "receipt_sha256", "C3 status map")
    authority = ledger.get("successor_authority_binding")
    cardinality = ledger.get("cardinality_limits")
    limits = ledger.get("time_and_cost_limits")
    usage = ledger.get("usage_at_freeze")
    if (
        hashlib.sha256(ledger_raw).hexdigest() != C3_LEDGER_FILE_SHA256
        or ledger_receipt != C3_LEDGER_RECEIPT_SHA256
        or hashlib.sha256(status_raw).hexdigest() != C3_STATUS_MAP_FILE_SHA256
        or status_receipt != C3_STATUS_MAP_RECEIPT_SHA256
        or ledger.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_recovery_cycle_ledger_v3"
        or ledger.get("status") != "frozen_c3_cycle_authorized_pending_pushed_c3"
        or ledger.get("cycle_id") != C3_CYCLE_ID
        or not isinstance(authority, Mapping)
        or authority.get("human_authorization_statement")
        != C3_AUTHORITY_STATEMENT
        or authority.get("c2_commit") != C2_CODE_FREEZE_COMMIT
        or authority.get("closure_file_sha256")
        != incident["closure_file_sha256"]
        or authority.get("closure_receipt_sha256")
        != incident["closure_receipt_sha256"]
        or authority.get("closure_verification_file_sha256")
        != incident["closure_verification_file_sha256"]
        or authority.get("closure_verification_receipt_sha256")
        != incident["closure_verification_receipt_sha256"]
        or authority.get("cycle_id") != C3_CYCLE_ID
        or authority.get("global_qualification_ordinal") != 3
        or authority.get("qualification_attempt_number") != 1
        or authority.get("no_automatic_retry") is not True
        or authority.get("no_model_forward") is not True
        or authority.get("qualification_and_review_raw_or_outcome_access") is not False
        or authority.get("rejected_pod_ids") != C3_REJECTED_POD_IDS
        or authority.get("hard_deadline_utc") != "2026-07-17T18:00:00Z"
        or authority.get("status_map_file_sha256") != C3_STATUS_MAP_FILE_SHA256
        or authority.get("status_map_receipt_sha256")
        != C3_STATUS_MAP_RECEIPT_SHA256
        or ledger.get("successor_authority_binding_sha256")
        != C3_AUTHORITY_BINDING_SHA256
        or canonical_sha256(authority) != C3_AUTHORITY_BINDING_SHA256
        or not isinstance(cardinality, Mapping)
        or cardinality.get("replacement_target_qualification_attempts") != 1
        or cardinality.get("paid_top_level_review_calls") != 1
        or cardinality.get("audit_only_recovery_attempts") != 1
        or cardinality.get("automatic_retries") != 0
        or not isinstance(usage, Mapping)
        or any(value != 0 for value in usage.values())
        or not isinstance(limits, Mapping)
        or limits.get("qualification_cap_seconds") != 1800
        or limits.get("qualification_cap_usd") != "3.00"
        or limits.get("paid_top_level_review_cap_usd") != "1.25"
        or limits.get("recovery_cap_seconds") != 3600
        or limits.get("recovery_cap_usd") != "6.00"
        or status_map.get("base_commit") != C2_CODE_FREEZE_COMMIT
        or status_map.get("status") != "frozen_allowed_surface_pending_c3_commit"
        or status_map.get("c2_to_c3", {}).get("other_paths_forbidden") is not True
        or status_map.get("c2_to_c3", {}).get("required_direct_parent")
        != C2_CODE_FREEZE_COMMIT
    ):
        raise QualificationIncidentError("C3 successor authority differs")
    return {**dict(authority), "binding_sha256": C3_AUTHORITY_BINDING_SHA256}


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
        else validate_incident(args.incident_dir)
    )
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
