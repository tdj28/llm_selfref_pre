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
C3_CODE_COMMIT = "7223ec9f4fcdf1e413a7143f9aebe9ee45648e21"
E3_QUALIFICATION_FREEZE_COMMIT = (
    "44d9e178567bbf31e524b79e4434474a4e5d888e"
)
C3_QUALIFICATION_DIRECTORY_NAME = "audit_recovery_host_qualification_v3"
C3_QUALIFICATION_POD_ID = "6am4twond0cd8v"
C4_REJECTED_POD_IDS = [
    "wl8obvtuq0ax8t",
    "69d9kxugxuf6up",
    "g2azyjkpm17f1s",
    C3_QUALIFICATION_POD_ID,
]
C4_CYCLE_ID = "signed-dose-audit-only-recovery-v4-20260717"
C4_AUTHORITY_STATEMENT = "Authorize C4"
C4_QUALIFICATION_PROTOCOL = (
    "consciousness_sae_signed_dose_scan_v1."
    "audit_recovery_host_qualification_v4"
)
C4_RECOVERY_PROTOCOL = (
    "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v4"
)
C4_AUTHORITY_BINDING_SHA256 = (
    "adc2c34302af92ec8da6b40d5a8c3745e9ced1be93f3fbaae31b691afabc20b8"
)
C4_LEDGER_FILE_SHA256 = (
    "1f9f88f9bb2946454801f336893e6622c74157f2aff0e957029f5e9b692e00f9"
)
C4_LEDGER_RECEIPT_SHA256 = (
    "68adc657a12191f612cc81d079cdc247daf8d55d16508b9cfd847f9aa89d1250"
)
C4_STATUS_MAP_FILE_SHA256 = (
    "195e3dcb9ecee2ca4c0b13ea81f7f17ca6aa25f40438b2e0e5e0620f1e344935"
)
C4_STATUS_MAP_RECEIPT_SHA256 = (
    "31eaffabf9863e086221a6452db228f791effe0a90ee3a3e630ab6b3d2ae58d7"
)
C3_QUALIFICATION_EVIDENCE_SPECS = {
    "ATTEMPT_STARTED.json": (
        3604,
        "53ea4f59f0871c06368c05bacc0a224ca4b3591185b079b9195c3d5b3154c5a3",
        "2a468b8a8235a410bd7ecae9406b88b5b2f6bf833d62e756ec8196a1d09f650c",
        "receipt_sha256",
    ),
    "QUALIFICATION_FROZEN_TERMINATION.json": (
        1434,
        "342edd53d24f402e1a0766481c9bec3f39712c46713f06ad2f445c8421730ec2",
        "2142e57c89a0c4eeed8692889040265b00bb638b0ba089561088b9730a962ce1",
        "receipt_sha256",
    ),
    "QUALIFICATION_POSTDELETE_INVENTORY.json": (
        493,
        "19d18dfe1301437df4a09a7d18cf6504dcb2dde1a950013ece262a342539e9e5",
        "31616fb9459f7a23c3acc9f60be89882bd00e6fa95146fc3156180ec00349687",
        "receipt_sha256",
    ),
    "QUALIFICATION_TERMINATION_AUDIT.json": (
        777,
        "1ae77d7521b3a2937ea8bf9e0f883299f5a5d189c0814277b5fddd98af3a22d0",
        "07b26522ce89a72fe090becc5ce3eca3df81759ff43ccbe25753fb5d0acf1327",
        "receipt_sha256",
    ),
    "RECOVERY_EQUIVALENCE_PACKET.json": (
        53164,
        "e0d01accdf7423f9d48b1a42bb8153c85e51eb27d662e8081e92529cce5c532f",
        "196844210145811a14389de3091a7334f3655a0a5e4e0bd6181b70e0073dea75",
        "packet_sha256",
    ),
    "RECOVERY_EQUIVALENCE_VERIFICATION.json": (
        1247,
        "a6d24e46ea22af62a1d143e3b52e4941c76c8f7aa7bf80bc7a0cd4429acf22fa",
        "6d4f514f8b50955e5c54b4dcfb345ed383d488e13514cb83ff7030cdbdc6f5c4",
        "receipt_sha256",
    ),
    "TARGET_HOST_QUALIFICATION.json": (
        15799,
        "10fac1fcf3e22c22459bd3ac79c483ff763d6ce12df2baa6d6df6e77212af3f8",
        "b2d304c7ada76e972e3d0220d0b1888b0ca590ffcc370eff3400c7f9e9fc75f5",
        "receipt_sha256",
    ),
    "TARGET_HOST_QUALIFICATION_VERIFICATION.json": (
        3595,
        "c6343d84bb63482deb2efe2996b1ff1a0d5a2b843a733c72c9ae01c4b4698023",
        "7df61ffee1a47d16124854f43af597915b06500ef203f3679ac47f50dabebc74",
        "receipt_sha256",
    ),
}
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


def _load_exact_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    """Load an exact physically anchored JSON object, independent of layout."""

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
    ):
        raise QualificationIncidentVerificationError(
            f"{label} is not single-link JSON"
        )
    return value, raw


def _verify_c2_incident_for_c3(incident_dir: Path) -> dict[str, Any]:
    """Independently authenticate the zero-forward C2 qualification failure."""

    root = incident_dir.expanduser().absolute()
    if root.name != C2_INCIDENT_DIRECTORY_NAME:
        raise QualificationIncidentVerificationError(
            "C2 qualification namespace differs"
        )
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
        raise QualificationIncidentVerificationError(
            "C2 evidence inventory differs"
        )
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
            raise QualificationIncidentVerificationError(
                "C2 evidence row differs"
            )
        path = root / str(row["name"])
        try:
            details = path.lstat()
            raw = path.read_bytes()
        except OSError as exc:
            raise QualificationIncidentVerificationError(
                "C2 evidence is unreadable"
            ) from exc
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
            or len(raw) != row["bytes"]
            or hashlib.sha256(raw).hexdigest() != row["physical_sha256"]
        ):
            raise QualificationIncidentVerificationError(
                "C2 evidence physical hash differs"
            )
        content_hash = row.get("content_sha256")
        if content_hash is None:
            if row["name"] != "QUALIFICATION_STDERR.log":
                raise QualificationIncidentVerificationError(
                    "C2 unhashed-content role differs"
                )
            continue
        if HEX64.fullmatch(str(content_hash)) is None:
            raise QualificationIncidentVerificationError(
                "C2 evidence content hash differs"
            )
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise QualificationIncidentVerificationError(
                "C2 evidence JSON differs"
            ) from exc
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
            raise QualificationIncidentVerificationError(
                "C2 evidence self hash differs"
            )
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
        raise QualificationIncidentVerificationError(
            "C2 incident semantics differ"
        )
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
    """Independently bind the C2 incident to the frozen one-shot C3 cycle."""

    incident = _verify_c2_incident_for_c3(incident_dir)
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
        raise QualificationIncidentVerificationError(
            "C3 successor authority differs"
        )
    return {**dict(authority), "binding_sha256": C3_AUTHORITY_BINDING_SHA256}


def _verify_c3_qualification_for_c4(
    qualification_dir: Path,
) -> dict[str, Any]:
    """Independently authenticate the successful E3 qualification receipts."""

    root = qualification_dir.expanduser().absolute()
    if root.name != C3_QUALIFICATION_DIRECTORY_NAME:
        raise QualificationIncidentVerificationError(
            "C3 qualification namespace differs"
        )
    try:
        names = sorted(path.name for path in root.iterdir())
    except OSError as exc:
        raise QualificationIncidentVerificationError(
            "C3 qualification directory is unreadable"
        ) from exc
    if names != sorted(C3_QUALIFICATION_EVIDENCE_SPECS):
        raise QualificationIncidentVerificationError(
            "C3 qualification inventory differs"
        )
    values: dict[str, dict[str, Any]] = {}
    for name, (size, expected_file_sha, expected_receipt, field) in (
        C3_QUALIFICATION_EVIDENCE_SPECS.items()
    ):
        value, raw = _load_exact_json(root / name, f"C3 qualification {name}")
        if (
            raw != canonical_json_bytes(value) + b"\n"
            or len(raw) != size
            or hashlib.sha256(raw).hexdigest() != expected_file_sha
            or _self_hash(value, field, f"C3 qualification {name}")
            != expected_receipt
        ):
            raise QualificationIncidentVerificationError(
                f"C3 qualification receipt differs: {name}"
            )
        values[name] = value

    marker = values["ATTEMPT_STARTED.json"]
    qualification = values["TARGET_HOST_QUALIFICATION.json"]
    verification = values["TARGET_HOST_QUALIFICATION_VERIFICATION.json"]
    packet = values["RECOVERY_EQUIVALENCE_PACKET.json"]
    packet_verification = values["RECOVERY_EQUIVALENCE_VERIFICATION.json"]
    termination = values["QUALIFICATION_FROZEN_TERMINATION.json"]
    termination_audit = values["QUALIFICATION_TERMINATION_AUDIT.json"]
    postdelete = values["QUALIFICATION_POSTDELETE_INVENTORY.json"]
    fresh_pod = qualification.get("fresh_pod")
    raw_guard = qualification.get("raw_access_guard")
    zero_forward = qualification.get("zero_forward_guard")
    if (
        marker.get("status") != "attempt_started_irrevocably"
        or marker.get("global_qualification_ordinal") != 3
        or marker.get("attempt_number") != 1
        or marker.get("successor_qualification_attempt") != 1
        or marker.get("retry_authorized") is not False
        or marker.get("successor_authority_binding_sha256")
        != C3_AUTHORITY_BINDING_SHA256
        or marker.get("authorized_raw_input_paths") != []
        or marker.get("model_forward_count") != 0
        or marker.get("target_prompt_render_count") != 0
        or qualification.get("status")
        != "pass_one_shot_zero_forward_target_host_qualification"
        or qualification.get("code_freeze_commit") != C3_CODE_COMMIT
        or qualification.get("global_qualification_ordinal") != 3
        or qualification.get("attempt_number") != 1
        or qualification.get("retry_authorized") is not False
        or qualification.get("model_forward_count") != 0
        or qualification.get("target_prompt_render_count") != 0
        or qualification.get("target_feature_vector_count") != 0
        or qualification.get("analysis_data_inputs") != []
        or qualification.get("outcome_input_paths") != []
        or qualification.get("raw_input_paths") != []
        or not isinstance(fresh_pod, Mapping)
        or fresh_pod.get("pod_id") != C3_QUALIFICATION_POD_ID
        or fresh_pod.get("status") != "pass_fresh_owned_guest_cache_chain"
        or fresh_pod.get("prior_outcome_inputs") != []
        or not isinstance(raw_guard, Mapping)
        or raw_guard.get("raw_forbidden_attempt_count") != 0
        or raw_guard.get("path_guard_rejected_attempt_count") != 0
        or not isinstance(zero_forward, Mapping)
        or any(value != 0 for value in zero_forward.values())
        or verification.get("status")
        != "pass_independent_target_host_qualification_verified"
        or verification.get("code_freeze_commit") != C3_CODE_COMMIT
        or verification.get("global_qualification_ordinal") != 3
        or verification.get("attempt_number") != 1
        or verification.get("retry_authorized") is not False
        or verification.get("raw_run_opened") is not False
        or verification.get("compact_result_opened") is not False
        or verification.get("analysis_data_inputs") != []
        or verification.get("model_forward_count") != 0
        or verification.get("target_prompt_render_count") != 0
        or verification.get("target_feature_vector_count") != 0
        or verification.get("qualification_receipt_file_sha256")
        != C3_QUALIFICATION_EVIDENCE_SPECS["TARGET_HOST_QUALIFICATION.json"][1]
        or verification.get("qualification_receipt_sha256")
        != C3_QUALIFICATION_EVIDENCE_SPECS["TARGET_HOST_QUALIFICATION.json"][2]
        or packet.get("status")
        != "pass_source_design_and_compatibility_bound_no_outcomes_loaded"
        or packet.get("raw_run_opened") is not False
        or packet.get("compact_result_opened") is not False
        or packet.get("analysis_data_inputs") != []
        or packet.get("outcome_input_paths") != []
        or packet.get("model_forward_count") != 0
        or packet.get("target_prompt_render_count") != 0
        or packet.get("target_feature_vector_count") != 0
        or packet_verification.get("status")
        != "pass_outcome_blind_recovery_equivalence_verified"
        or packet_verification.get("raw_run_opened") is not False
        or packet_verification.get("compact_result_opened") is not False
        or packet_verification.get("analysis_data_inputs") != []
        or packet_verification.get("model_forward_count") != 0
        or packet_verification.get("target_prompt_render_count") != 0
        or packet_verification.get("target_feature_vector_count") != 0
        or termination.get("status") != "deleted_verified"
        or termination.get("pod_id") != C3_QUALIFICATION_POD_ID
        or termination.get("absent_from_account_inventory") is not True
        or termination.get("other_pods_mutated") is not False
        or termination_audit.get("status")
        != "deleted_exact_owned_pod_unrelated_inventory_unchanged"
        or termination_audit.get("pod_id") != C3_QUALIFICATION_POD_ID
        or postdelete.get("status") != "captured_read_only"
        or postdelete.get("phase") != "postdelete"
        or postdelete.get("all_account_pod_count") != 0
        or postdelete.get("pods") != []
    ):
        raise QualificationIncidentVerificationError(
            "C3 qualification semantics differ"
        )
    return {
        "e3_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "global_qualification_ordinal": 3,
        "model_forward_count": 0,
        "pod_id": C3_QUALIFICATION_POD_ID,
        "raw_run_opened": False,
        "target_prompt_render_count": 0,
        "termination_proven": True,
    }


def successor_c4_authority_binding(
    predecessor_qualification_dir: Path,
    recovery_cycle_ledger_path: Path,
) -> dict[str, Any]:
    """Independently reconstruct and verify the one-shot C4 authority."""

    predecessor = _verify_c3_qualification_for_c4(
        predecessor_qualification_dir
    )
    ledger, ledger_raw = _load_exact_json(
        recovery_cycle_ledger_path, "C4 recovery cycle ledger"
    )
    status_map, status_raw = _load_exact_json(
        recovery_cycle_ledger_path.parent / "RECOVERY_C4_STATUS_MAP.json",
        "C4 status map",
    )
    ledger_receipt = _self_hash(
        ledger, "receipt_sha256", "C4 recovery cycle ledger"
    )
    status_receipt = _self_hash(
        status_map, "receipt_sha256", "C4 status map"
    )
    expected_authority = {
        "authority_minted_at_utc": "2026-07-17T16:00:00Z",
        "c3_code_commit": C3_CODE_COMMIT,
        "c3_evidence_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "cycle_id": C4_CYCLE_ID,
        "global_qualification_ordinal": 4,
        "hard_deadline_utc": "2026-07-17T18:00:00Z",
        "human_authorization_statement": C4_AUTHORITY_STATEMENT,
        "new_paid_review_call_count": 0,
        "no_automatic_retry": True,
        "no_model_forward": True,
        "predecessor_qualification_pod_id": C3_QUALIFICATION_POD_ID,
        "qualification_and_review_raw_or_outcome_access": False,
        "qualification_attempt_number": 1,
        "qualification_namespace": "audit_recovery_host_qualification_v4",
        "qualification_protocol_version": C4_QUALIFICATION_PROTOCOL,
        "recovery_namespace": "audit_only_recovery_v4",
        "recovery_protocol_version": C4_RECOVERY_PROTOCOL,
        "rejected_pod_ids": C4_REJECTED_POD_IDS,
        "review_artifact_inventory_sha256": (
            "bcdd58053d7f5d65e1937a01cf532ae597e94426c130aea80de13741c872d172"
        ),
        "review_input_anchor_commit": E3_QUALIFICATION_FREEZE_COMMIT,
        "review_namespace": "audit_recovery_pro_review_v3",
        "status_map_file_sha256": C4_STATUS_MAP_FILE_SHA256,
        "status_map_receipt_sha256": C4_STATUS_MAP_RECEIPT_SHA256,
        "study_id": "consciousness_sae_signed_dose_scan_v1",
    }
    authority = ledger.get("successor_authority_binding")
    cardinality = ledger.get("cardinality_limits")
    limits = ledger.get("time_and_cost_limits")
    usage = ledger.get("usage_at_freeze")
    authorization = ledger.get("authorization_state")
    review = ledger.get("review_reuse_binding")
    lineage = ledger.get("lineage_contract")
    if (
        hashlib.sha256(ledger_raw).hexdigest() != C4_LEDGER_FILE_SHA256
        or ledger_receipt != C4_LEDGER_RECEIPT_SHA256
        or hashlib.sha256(status_raw).hexdigest() != C4_STATUS_MAP_FILE_SHA256
        or status_receipt != C4_STATUS_MAP_RECEIPT_SHA256
        or ledger.get("receipt_kind")
        != "consciousness_sae_signed_dose_scan_recovery_cycle_ledger_v4"
        or ledger.get("status") != "frozen_c4_cycle_authorized_pending_pushed_c4"
        or ledger.get("cycle_id") != C4_CYCLE_ID
        or ledger.get("qualification_protocol_version")
        != C4_QUALIFICATION_PROTOCOL
        or ledger.get("recovery_protocol_version") != C4_RECOVERY_PROTOCOL
        or authority != expected_authority
        or ledger.get("successor_authority_binding_sha256")
        != C4_AUTHORITY_BINDING_SHA256
        or canonical_sha256(expected_authority) != C4_AUTHORITY_BINDING_SHA256
        or cardinality
        != {
            "audit_only_recovery_attempts": 1,
            "automatic_retries": 0,
            "new_paid_top_level_review_calls": 0,
            "provider_capacity_retries": 0,
            "replacement_target_qualification_attempts": 1,
        }
        or not isinstance(limits, Mapping)
        or limits.get("hard_deadline_utc") != "2026-07-17T18:00:00Z"
        or limits.get("qualification_cap_seconds") != 1800
        or limits.get("qualification_cap_usd") != "3.00"
        or limits.get("recovery_cap_seconds") != 3600
        or limits.get("recovery_cap_usd") != "6.00"
        or limits.get("new_paid_top_level_review_cap_usd") != "0.00"
        or limits.get("successor_additional_cycle_envelope_usd") != "9.00"
        or not isinstance(usage, Mapping)
        or usage.get("replacement_target_qualification_attempts_used") != 0
        or usage.get("audit_only_recovery_attempts_used") != 0
        or usage.get("new_paid_top_level_review_calls_used") != 0
        or usage.get("automatic_retries_used") != 0
        or usage.get("provider_capacity_retries_used") != 0
        or not isinstance(authorization, Mapping)
        or authorization.get("explicit_human_authorization_observed") is not True
        or authorization.get("explicit_human_authorization_statement")
        != C4_AUTHORITY_STATEMENT
        or authorization.get("qualification_and_review_outcome_blind") is not True
        or not isinstance(review, Mapping)
        or review.get("new_paid_review_call_count") != 0
        or review.get("paid_review_call_count_inherited") != 1
        or review.get("review_input_anchor_commit")
        != E3_QUALIFICATION_FREEZE_COMMIT
        or review.get("paid_artifact_inventory_sha256")
        != expected_authority["review_artifact_inventory_sha256"]
        or not isinstance(lineage, Mapping)
        or lineage.get("global_qualification_ordinal") != 4
        or lineage.get("predecessor_global_qualification_ordinal") != 3
        or lineage.get("predecessor_qualification_pod_id")
        != predecessor["pod_id"]
        or lineage.get("rejected_pod_ids") != C4_REJECTED_POD_IDS
        or status_map.get("base_commit") != E3_QUALIFICATION_FREEZE_COMMIT
        or status_map.get("status") != "frozen_allowed_surface_pending_c4_commit"
        or status_map.get("e3_to_c4", {}).get("required_direct_parent")
        != E3_QUALIFICATION_FREEZE_COMMIT
        or status_map.get("e3_to_c4", {}).get("other_paths_forbidden") is not True
        or status_map.get("c4_to_e4", {}).get("added_directory")
        != "docs/consciousness_sae_signed_dose_scan/audit_recovery_host_qualification_v4"
        or status_map.get("c4_to_e4", {}).get("other_paths_forbidden") is not True
    ):
        raise QualificationIncidentVerificationError(
            "C4 successor authority differs"
        )
    return {
        **expected_authority,
        "binding_sha256": C4_AUTHORITY_BINDING_SHA256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--incident-dir", type=Path, required=True)
    parser.add_argument("--recovery-cycle-ledger", type=Path)
    args = parser.parse_args()
    if args.recovery_cycle_ledger is None:
        value = verify_incident(args.incident_dir)
    elif args.recovery_cycle_ledger.name == "RECOVERY_CYCLE_LEDGER_V4.json":
        value = successor_c4_authority_binding(
            args.incident_dir, args.recovery_cycle_ledger
        )
    elif args.recovery_cycle_ledger.name == "RECOVERY_CYCLE_LEDGER_V3.json":
        value = successor_c3_authority_binding(
            args.incident_dir, args.recovery_cycle_ledger
        )
    else:
        value = successor_authority_binding(
            args.incident_dir, args.recovery_cycle_ledger
        )
    print(json.dumps(value, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
