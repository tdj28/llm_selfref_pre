#!/usr/bin/env python3
"""Independently verify the signed-dose incident closure and cycle ledger.

This verifier deliberately restates the historical authority, physical file
identities, attempt classifications, raw-ledger commitment, and recovery
ceilings.  It imports neither the closure producer nor the scientific runner or
auditor, so a mutually consistent rewrite of producer output is not sufficient
to pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


class IncidentClosureVerificationError(RuntimeError):
    """The closure or ledger is missing, malformed, or historically false."""


EXPECTED_SCHEMA_SHA256 = (
    "3179e4c8ae25b5d858d4779e224ad83123720cb84346f626ce316c3fea82f174"
)
EXPECTED_RAW_RECORDS_SHA256 = (
    "b5c784f4feb87ba01a9fc5d9b2f22d12eee01930d98718cd5c54e3d398692cf4"
)
EXPECTED_RUN_COMPLETE_FILE_SHA256 = (
    "a5818ad5e208c9008df6ad0bede630fddafb06e07b5f0190d02b3b80ceefeb4b"
)
EXPECTED_RUN_COMPLETE_RECEIPT_SHA256 = (
    "f714f16e2f6d5bb532d522c3ad0e2985e6f6b169ff5875911d296f42cd8fdc7d"
)
EXPECTED_EMPTY_INVENTORY_SHA256 = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(child) for child in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _finite_json(child)
            for key, child in value.items()
        )
    return False


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncidentClosureVerificationError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict) or not _finite_json(value):
        raise IncidentClosureVerificationError(f"non-object or non-finite JSON: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IncidentClosureVerificationError(message)


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} field inventory differs")


def _self_hash(value: Mapping[str, Any], label: str) -> str:
    supplied = value.get("receipt_sha256")
    _require(isinstance(supplied, str), f"{label} self-hash is missing")
    core = dict(value)
    del core["receipt_sha256"]
    _require(supplied == canonical_sha256(core), f"{label} self-hash differs")
    return supplied


def _evidence(
    role: str,
    relative_name: str,
    byte_count: int,
    sha256: str,
    content_receipt_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "relative_name": relative_name,
        "bytes": byte_count,
        "sha256": sha256,
        "content_receipt_sha256": content_receipt_sha256,
    }


# This inventory is an independent historical anchor.  It must not be derived
# from the closure being checked or imported from its producer.
EXPECTED_EVIDENCE = sorted(
    [
        _evidence(
            "ownership_receipt",
            "OWNERSHIP.json",
            1665,
            "a75782a605bcc2e71f1e72c1c35e4db761cecc7ffc716066bb374d3ceb291cce",
            "70799f1762922a7d06701a3a4f00f1dc2a71aee275eab8ab0700e1c6068f4979",
        ),
        _evidence(
            "guest_preflight",
            "GUEST_PREFLIGHT.json",
            1223,
            "e4955405f32e1ad4d1076f8f30109510b2cb43d26ac144bbf8fe5246a2105c90",
            "6e9f4e69d253075b7c40bcf904a9582c1f5a2ff2c646c1484ccec73940399db7",
        ),
        _evidence(
            "cache_preflight",
            "CACHE_PREFLIGHT.json",
            1522,
            "2d85c9bd807398721b81cc1195f4381cec81da8f5457f260b384b2660e22de1e",
            "77a738771e8073d381bb519beb58525534c3d192be9f94237c74c76043b11187",
        ),
        _evidence(
            "llama70b_v1_authorization",
            "AUTHORIZATION.json",
            3279,
            "8ae87ded7d9c7c6ac083bebab8ef217be9d7709875f49989993c1f15976a6ded",
            "c2d327a64958cab80e7a3ce82a382310033df0a53a51409f849604a22d8e318b",
        ),
        _evidence(
            "llama70b_v2_authorization",
            "AUTHORIZATION_V2.json",
            3279,
            "79933cc2f51ecb9015a903c2814c6a34c5e2288b577c5f548b55652b6c057e47",
            "687837a3a2fdf0de6cea7559ec7f2725ef4b014e56a0d014a8b30788325039b7",
        ),
        _evidence(
            "small_model_promotion_gate",
            "SMALL_MODEL_PROMOTION_GATE.json",
            2329,
            "5eb0e6a03206dc037aedd3682de82cc47a95508684e98c0af47022c87a0316e6",
            "f5417228aa80eed0004d1f1ac59f96abf937f9cb94590cb06d4957cdf4aba02b",
        ),
        _evidence(
            "gemma_v1_failure_receipt",
            "GEMMA_V1_INCIDENT/RUN_FAILED.json",
            757,
            "54193444cce49d83ff54b66a01e8a1ce16056d68c7dbc107d2f824070503e716",
        ),
        _evidence(
            "gemma_v1_status",
            "GEMMA_V1_INCIDENT/STATUS",
            49,
            "ddfbceedc38d280fe0d67aad7c98b6cc4fc9fc60fe62adf2b228c93dcd87b42d",
        ),
        _evidence(
            "gemma_v1_log",
            "GEMMA_V1_INCIDENT/signed-dose-gemma-a084caa.log",
            5449,
            "f7e8095253cf8ea5390984fb25742e1e70ebd110222cd7759500269a24ec808b",
        ),
        _evidence(
            "gemma_v2_audit",
            "GEMMA_V2_PASS/AUDIT.json",
            2329,
            "5eb0e6a03206dc037aedd3682de82cc47a95508684e98c0af47022c87a0316e6",
            "f5417228aa80eed0004d1f1ac59f96abf937f9cb94590cb06d4957cdf4aba02b",
        ),
        _evidence(
            "gemma_v2_run_manifest",
            "GEMMA_V2_PASS/RUN_MANIFEST.json",
            7633,
            "6ef8e3bea3d90886599bf56c98a6489efca245744f8e8bd921de8e46bbefa76b",
        ),
        _evidence(
            "gemma_v2_status",
            "GEMMA_V2_PASS/STATUS",
            49,
            "f857c56cc28e9ae73f5126cdf060e04c955d4598c35390a5f5f78a2cea8936b6",
        ),
        _evidence(
            "gemma_v2_log",
            "GEMMA_V2_PASS/signed-dose-gemma-a084caa-v2.log",
            1062,
            "d5ff556c15b356a4759dc37fdedc567ac5a538d3f43d72119de6345d6d753ff4",
        ),
        _evidence(
            "llama70b_v1_status",
            "V1_LAUNCH_INCIDENT/STATUS",
            51,
            "cbd363a0a4cfcd236b2d84141691f19c652aecd919627b50a971c68511ada21e",
        ),
        _evidence(
            "llama70b_v1_log",
            "V1_LAUNCH_INCIDENT/run.log",
            131,
            "5fe2b5d8d7df37860ee58cdeb85a7f5e83e14a11b2586ece23062ff4a4116248",
        ),
        _evidence(
            "llama70b_v2_run_complete",
            "V2_INCIDENT/RUN_COMPLETE.json",
            9987,
            EXPECTED_RUN_COMPLETE_FILE_SHA256,
            EXPECTED_RUN_COMPLETE_RECEIPT_SHA256,
        ),
        _evidence(
            "llama70b_v2_status",
            "V2_INCIDENT/STATUS",
            49,
            "41e31e05845259a45a830e7174b47ae6f1548ccfbc85aae2df8721fcfcd3cc05",
        ),
        _evidence(
            "llama70b_v2_execution_binding",
            "V2_INCIDENT/execution_binding.json",
            3078,
            "e1dbd1b1ff69297159a1d6a848ae8db5314e2d261b0e31fa9089db897f86b7c2",
        ),
        _evidence(
            "llama70b_v2_j_orientation",
            "V2_INCIDENT/j_orientation_receipt.json",
            1077,
            "58e63625f7301e8868cc2b858eaaa090468da1375200f4794787896badf73f3f",
        ),
        _evidence(
            "llama70b_v2_log",
            "V2_INCIDENT/run.log",
            4204,
            "c5309b1ff480041b4c50c81ed75ef42ec22121969ddd41a0d90109037a4134f6",
        ),
        _evidence(
            "llama70b_v2_runner_time",
            "V2_INCIDENT/runner.time",
            93,
            "1077570e358703942817d0c0f171df667824b3cb0bf9aae2d2a0472d582e0f17",
        ),
        _evidence(
            "llama70b_v2_runtime_metadata",
            "V2_INCIDENT/runtime_metadata.json",
            3201,
            "09462acc9df1365130242e68bafc7bdde835cb16110be04681842f5cb598948d",
        ),
        _evidence(
            "termination_audit",
            "TERMINATION_AUDIT.json",
            777,
            "3180a922744937adac0641dfc8e6f27db3b813e0c58cc43da7d693b9eab3ea67",
            "4147d073fb7d1debdd182e13f72be4610ed25cb1e783a3215ae7f66ed16faa04",
        ),
        _evidence(
            "postdelete_inventory",
            "POSTDELETE_INVENTORY.json",
            493,
            "2264249e9dfce51d6a78c4386a4d1dff6d64a7a4e00ed4bf664a87a70d92225c",
            "6022801ebd4c23fd0da32ccbc21ce4ff065b0935b99a77db2a1df0bc5c7fb47c",
        ),
        _evidence(
            "gemma_v1_wrapper",
            "run_signed_dose_gemma_gate.sh",
            1692,
            "330fcf3d64ae8692d9c827ea83b027df5c2e585c8a351d53654def1c3f4f17c5",
        ),
        _evidence(
            "gemma_v2_wrapper",
            "run_signed_dose_gemma_gate_v2.sh",
            1695,
            "23d64db6b9e2603d1dd40ade67dddcb016a219c5cb6306a1d184fe4e04c6c89a",
        ),
        _evidence(
            "llama70b_v1_wrapper",
            "run_signed_dose_70b_once.sh",
            3308,
            "2d1ab8d41900a8fda9205449b3d017db1de5b8379126c7725c88fc9a6358f820",
        ),
        _evidence(
            "llama70b_v2_wrapper",
            "run_signed_dose_70b_v2.sh",
            4025,
            "527c87909c6a4eb261f50da525bd56b7982041d9de28b83dfc47de840bba09ac",
        ),
        _evidence(
            "frozen_plan_manifest",
            "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716/PLAN_MANIFEST.json",
            1537,
            "559f43884221ec309e40b6b83cc9f4e23dbd13196a0ec506f805b329a1d5554e",
        ),
        _evidence(
            "frozen_protocol",
            "docs/consciousness_sae_signed_dose_scan/PROTOCOL.md",
            10999,
            "ff48ac9166ec782132d55b5a6f064ec8091c2a47fc57aa5b802f0bd62b59bb69",
        ),
        _evidence(
            "frozen_review_adjudication",
            "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_ADJUDICATION.json",
            3534,
            "732f32e17c8df49062d87fbcfb8e4493d576f6ba71643ce8b724ac02dfc7a53d",
            "234254e67f8b897ea837590117932e4bfdfc261df7fc4eb460acf7047edba0d8",
        ),
        _evidence(
            "incident_closure_schema",
            "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json",
            8833,
            EXPECTED_SCHEMA_SHA256,
        ),
    ],
    key=lambda row: row["role"],
)


EXPECTED_ATTEMPTS = [
    {
        "attempt_id": "gemma_operational_validation_v1",
        "role": "smaller_model_operational_gate",
        "terminal_status": "failed",
        "outcome_access_classification": "startup_not_reached",
        "execution_boundary": "tokenizer_resolution_failed_before_model_load_or_forward",
        "model_load_reached": False,
        "model_forward_count": 0,
        "guest_launcher_reached": False,
        "raw_artifacts_final": False,
        "raw_opened_or_recomputed_by_audit": False,
        "compact_outputs_produced": False,
        "semantic_outcomes_collected": False,
        "scientific_claims_authorized": False,
        "authority_disposition": "not_a_scientific_authorization",
        "evidence_roles": [
            "gemma_v1_wrapper",
            "gemma_v1_failure_receipt",
            "gemma_v1_status",
            "gemma_v1_log",
        ],
    },
    {
        "attempt_id": "gemma_operational_validation_v2",
        "role": "smaller_model_operational_gate",
        "terminal_status": "pass_small_model_promotion_gate",
        "outcome_access_classification": "operational_validation_completed",
        "execution_boundary": "independent_artifact_replay_completed",
        "model_load_reached": True,
        "model_forward_count": 122,
        "guest_launcher_reached": False,
        "raw_artifacts_final": True,
        "raw_opened_or_recomputed_by_audit": True,
        "compact_outputs_produced": True,
        "semantic_outcomes_collected": False,
        "scientific_claims_authorized": False,
        "authority_disposition": (
            "promotion_scope_runner_mechanics_only_not_scientific_protocol"
        ),
        "evidence_roles": [
            "gemma_v2_wrapper",
            "gemma_v2_run_manifest",
            "gemma_v2_audit",
            "gemma_v2_status",
            "gemma_v2_log",
            "small_model_promotion_gate",
        ],
    },
    {
        "attempt_id": "signed-dose-a084caa-wl8obvtuq0ax8t-v1",
        "role": "llama70b_scientific_attempt",
        "terminal_status": "failed_exit_127",
        "outcome_access_classification": "startup_not_reached",
        "execution_boundary": (
            "wrapper_failed_on_missing_usr_bin_time_before_guest_launcher"
        ),
        "model_load_reached": False,
        "model_forward_count": 0,
        "guest_launcher_reached": False,
        "raw_artifacts_final": False,
        "raw_opened_or_recomputed_by_audit": False,
        "compact_outputs_produced": False,
        "semantic_outcomes_collected": False,
        "scientific_claims_authorized": False,
        "authority_disposition": "consumed_and_permanently_rejected",
        "evidence_roles": [
            "llama70b_v1_wrapper",
            "llama70b_v1_authorization",
            "llama70b_v1_status",
            "llama70b_v1_log",
        ],
    },
    {
        "attempt_id": "signed-dose-a084caa-wl8obvtuq0ax8t-v2",
        "role": "llama70b_scientific_attempt",
        "terminal_status": "collection_complete_audit_failed",
        "outcome_access_classification": "raw_inputs_opened_or_recomputed",
        "execution_boundary": (
            "strict_j_lens_inventory_rejection_during_independent_raw_recomputation"
        ),
        "model_load_reached": True,
        "model_forward_count": 2896,
        "guest_launcher_reached": True,
        "raw_artifacts_final": True,
        "raw_opened_or_recomputed_by_audit": True,
        "compact_outputs_produced": False,
        "semantic_outcomes_collected": False,
        "scientific_claims_authorized": False,
        "authority_disposition": "consumed_and_permanently_rejected",
        "evidence_roles": [
            "llama70b_v2_wrapper",
            "llama70b_v2_authorization",
            "llama70b_v2_run_complete",
            "llama70b_v2_status",
            "llama70b_v2_execution_binding",
            "llama70b_v2_j_orientation",
            "llama70b_v2_runner_time",
            "llama70b_v2_runtime_metadata",
            "llama70b_v2_log",
        ],
    },
]


EXPECTED_AUTHORITY = {
    "freeze_commit": "a084caafc2ec27860044d80d3b33912f656fd08a",
    "plan_git_head_commit": "6a065b1c64b8451a8f4fa408770f699ce7f5ff3f",
    "plan_manifest_sha256": (
        "79810742bd2899ae0805e294fb5b9640870a21fe60e4c85a73b241b92963c51d"
    ),
    "plan_manifest_file_sha256": (
        "559f43884221ec309e40b6b83cc9f4e23dbd13196a0ec506f805b329a1d5554e"
    ),
    "review_adjudication_receipt_sha256": (
        "234254e67f8b897ea837590117932e4bfdfc261df7fc4eb460acf7047edba0d8"
    ),
    "review_model": "gpt-5.6-sol",
    "review_response_id": "resp_0771e3684280ebf7016a595c85174c8198ae40e01f160772f0",
    "pod_id": "wl8obvtuq0ax8t",
    "volume_id": "bv9gb9j32y",
    "data_center_id": "US-CA-2",
    "gpu_type": "NVIDIA B200",
}

EXPECTED_TERMINATION = {
    "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
    "pod_id": "wl8obvtuq0ax8t",
    "termination_receipt_sha256": (
        "4147d073fb7d1debdd182e13f72be4610ed25cb1e783a3215ae7f66ed16faa04"
    ),
    "postdelete_account_pod_count": 0,
    "postdelete_inventory_sha256": EXPECTED_EMPTY_INVENTORY_SHA256,
    "network_volume_retained": True,
}

EXPECTED_DISPOSITION = {
    "rejected_authorized_run_ids": [
        "signed-dose-a084caa-wl8obvtuq0ax8t-v1",
        "signed-dose-a084caa-wl8obvtuq0ax8t-v2",
    ],
    "rejected_authorization_receipt_sha256": [
        "c2d327a64958cab80e7a3ce82a382310033df0a53a51409f849604a22d8e318b",
        "687837a3a2fdf0de6cea7559ec7f2725ef4b014e56a0d014a8b30788325039b7",
    ],
    "rejected_pod_ids": ["wl8obvtuq0ax8t"],
    "compact_publication_status": "not_produced",
    "scientific_plan_changed": False,
    "raw_outcome_bytes_changed": False,
    "raw_reuse_scope": (
        "audit_only_recovery_after_fresh_authority_and_verified_cycle_ledger"
    ),
    "scientific_result_release_status": (
        "blocked_pending_passing_independent_audit"
    ),
    "closure_grants_launch_authority": False,
}


def verify_closure(value: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(
        value,
        {
            "schema_version",
            "receipt_kind",
            "status",
            "study_id",
            "protocol_version",
            "authority",
            "evidence_inventory",
            "attempt_classifications",
            "raw_ledger",
            "termination",
            "terminal_disposition",
            "receipt_sha256",
        },
        "incident closure",
    )
    receipt = _self_hash(value, "incident closure")
    _require(value["schema_version"] == 1, "closure schema version differs")
    _require(
        value["receipt_kind"]
        == "consciousness_sae_signed_dose_scan_incident_closure_v1",
        "closure kind differs",
    )
    _require(
        value["status"] == "closed_recovery_required_no_compact_publication",
        "closure status differs",
    )
    _require(
        value["study_id"] == "consciousness_sae_signed_dose_scan_v1",
        "closure study differs",
    )
    _require(
        value["protocol_version"]
        == "consciousness_sae_signed_dose_scan_v1.0.0",
        "closure protocol differs",
    )
    _require(value["authority"] == EXPECTED_AUTHORITY, "authority differs")
    _require(
        value["evidence_inventory"] == EXPECTED_EVIDENCE,
        "historical evidence inventory differs",
    )
    _require(
        value["attempt_classifications"] == EXPECTED_ATTEMPTS,
        "attempt classification differs",
    )
    _require(value["termination"] == EXPECTED_TERMINATION, "termination differs")
    _require(
        value["terminal_disposition"] == EXPECTED_DISPOSITION,
        "terminal disposition differs",
    )

    raw = value["raw_ledger"]
    _require(isinstance(raw, dict), "raw ledger is not an object")
    _exact_fields(
        raw,
        {
            "run_id",
            "storage_role",
            "file_count",
            "stored_bytes",
            "records_sha256",
            "run_complete_file_sha256",
            "run_complete_receipt_sha256",
            "records",
        },
        "raw ledger",
    )
    _require(
        raw["run_id"] == "signed-dose-a084caa-wl8obvtuq0ax8t-v2",
        "raw run differs",
    )
    _require(
        raw["storage_role"] == "immutable_runpod_network_volume_raw_not_git",
        "raw storage role differs",
    )
    _require(raw["file_count"] == 35, "raw file count differs")
    _require(raw["stored_bytes"] == 2_229_288_980, "raw bytes differ")
    _require(
        raw["records_sha256"] == EXPECTED_RAW_RECORDS_SHA256,
        "raw ledger declared commitment differs",
    )
    _require(
        raw["run_complete_file_sha256"] == EXPECTED_RUN_COMPLETE_FILE_SHA256,
        "raw RUN_COMPLETE physical hash differs",
    )
    _require(
        raw["run_complete_receipt_sha256"]
        == EXPECTED_RUN_COMPLETE_RECEIPT_SHA256,
        "raw RUN_COMPLETE receipt differs",
    )
    records = raw["records"]
    _require(isinstance(records, list) and len(records) == 35, "raw records differ")
    seen: set[str] = set()
    ordered_paths: list[str] = []
    total = 0
    for index, row in enumerate(records):
        _require(isinstance(row, dict), f"raw row {index} is not an object")
        _exact_fields(row, {"path", "bytes", "sha256"}, f"raw row {index}")
        path = row["path"]
        byte_count = row["bytes"]
        digest = row["sha256"]
        _require(
            isinstance(path, str)
            and path
            and not path.startswith("/")
            and ".." not in Path(path).parts
            and "\\" not in path,
            f"raw row {index} path is unsafe",
        )
        _require(
            isinstance(byte_count, int)
            and not isinstance(byte_count, bool)
            and byte_count > 0,
            f"raw row {index} bytes are invalid",
        )
        _require(
            isinstance(digest, str)
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest),
            f"raw row {index} hash is invalid",
        )
        _require(path not in seen, f"raw row {index} path is duplicated")
        seen.add(path)
        ordered_paths.append(path)
        total += byte_count
    _require(ordered_paths == sorted(ordered_paths), "raw paths are not sorted")
    _require(total == 2_229_288_980, "raw record byte sum differs")
    _require(
        canonical_sha256(records) == EXPECTED_RAW_RECORDS_SHA256,
        "raw records differ from independent commitment",
    )
    return {
        "status": "pass_incident_closure_independent_verification",
        "incident_closure_receipt_sha256": receipt,
        "raw_record_count": 35,
        "raw_stored_bytes": 2_229_288_980,
        "raw_records_sha256": EXPECTED_RAW_RECORDS_SHA256,
    }


def verify_recovery_ledger(
    value: Mapping[str, Any],
    *,
    closure_receipt_sha256: str,
    closure_file_sha256: str,
) -> dict[str, Any]:
    _exact_fields(
        value,
        {
            "schema_version",
            "receipt_kind",
            "status",
            "study_id",
            "recovery_protocol_version",
            "cycle_id",
            "incident_binding",
            "immutable_scientific_contract",
            "cardinality_limits",
            "usage_at_freeze",
            "time_and_cost_limits",
            "authorization_state",
            "closure_table",
            "terminal_action",
            "receipt_sha256",
        },
        "recovery ledger",
    )
    receipt = _self_hash(value, "recovery ledger")
    _require(value["schema_version"] == 1, "recovery ledger schema differs")
    _require(
        value["receipt_kind"]
        == "consciousness_sae_signed_dose_scan_recovery_cycle_ledger_v1",
        "recovery ledger kind differs",
    )
    _require(
        value["status"] == "frozen_pending_explicit_review_authorization",
        "recovery ledger status differs",
    )
    _require(
        value["study_id"] == "consciousness_sae_signed_dose_scan_v1",
        "recovery ledger study differs",
    )
    _require(
        value["recovery_protocol_version"]
        == "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v1",
        "recovery protocol differs",
    )
    _require(
        value["cycle_id"] == "signed-dose-audit-only-recovery-v1-20260717",
        "recovery cycle identity differs",
    )
    _require(
        value["incident_binding"]
        == {
            "incident_closure_receipt_sha256": closure_receipt_sha256,
            "incident_closure_file_sha256": closure_file_sha256,
            "failed_run_id": "signed-dose-a084caa-wl8obvtuq0ax8t-v2",
            "raw_records_sha256": EXPECTED_RAW_RECORDS_SHA256,
            "raw_run_complete_receipt_sha256": (
                EXPECTED_RUN_COMPLETE_RECEIPT_SHA256
            ),
        },
        "recovery incident binding differs",
    )
    _require(
        value["immutable_scientific_contract"]
        == {
            "scientific_plan_changed": False,
            "raw_outcome_bytes_changed": False,
            "prompts_changed": False,
            "directions_changed": False,
            "dose_grid_changed": False,
            "endpoints_changed": False,
            "analysis_changed": False,
            "allowed_scope": "audit_only_mechanical_j_inventory_repair",
            "raw_input_run_id": "signed-dose-a084caa-wl8obvtuq0ax8t-v2",
            "fresh_compact_output_required": True,
        },
        "immutable scientific contract differs",
    )
    _require(
        value["cardinality_limits"]
        == {
            "local_closure_passes": 1,
            "target_qualification_attempts": 1,
            "paid_cumulative_review_calls": 1,
            "audit_only_recovery_attempts": 1,
            "automatic_retries": 0,
            "provider_capacity_retries": 0,
        },
        "recovery cardinality differs",
    )
    _require(
        value["usage_at_freeze"]
        == {
            "local_closure_passes": 0,
            "target_qualification_attempts": 0,
            "paid_cumulative_review_calls": 0,
            "audit_only_recovery_attempts": 0,
        },
        "recovery usage-at-freeze differs",
    )
    _require(
        value["time_and_cost_limits"]
        == {
            "cycle_deadline_utc": "2026-07-17T08:00:00Z",
            "maximum_additional_cycle_cost_usd": 12.0,
            "pre_recovery_estimated_spend_usd": 19.6,
            "overall_user_hard_ceiling_usd": 50.0,
            "target_qualification": {
                "maximum_walltime_seconds": 1800,
                "maximum_cost_usd": 3.0,
            },
            "paid_cumulative_review": {"maximum_cost_usd": 1.25},
            "audit_only_recovery": {
                "maximum_walltime_seconds": 3600,
                "maximum_cost_usd": 6.0,
            },
            "nonexecution_reserve_usd": 1.75,
        },
        "recovery cost or deadline differs",
    )
    _require(
        value["authorization_state"]
        == {
            "local_closure_authorized": True,
            "target_qualification_authorized": True,
            "paid_cumulative_review_authorized": False,
            "paid_cumulative_review_requires_explicit_human_approval": True,
            "audit_only_recovery_authorized": False,
            "incident_closure_grants_launch_authority": False,
        },
        "recovery authorization state differs",
    )
    rows = value["closure_table"]
    _require(isinstance(rows, list) and len(rows) == 3, "closure table row count differs")
    required_columns = {
        "failure_id",
        "production_command",
        "target_platform_rehearsal",
        "negative_regression",
        "independent_verifier_rule",
        "receipt_field",
        "launch_gate_check",
    }
    for index, row in enumerate(rows):
        _require(isinstance(row, dict), f"closure table row {index} differs")
        _exact_fields(row, required_columns, f"closure table row {index}")
        _require(
            all(isinstance(item, str) and item for item in row.values()),
            f"closure table row {index} has an empty cell",
        )
    _require(
        [row["failure_id"] for row in rows]
        == [
            "INC-GEMMA-CACHE-001",
            "INC-70B-WRAPPER-001",
            "INC-70B-J-INVENTORY-001",
        ],
        "closure table failure identities differ",
    )
    _require(
        value["terminal_action"]
        == {
            "all_gates_green": "launch_exactly_one_audit_only_recovery_in_same_execution_turn",
            "any_gate_red": "stop_and_report_blocker",
            "cycle_budget_exhausted": "stop_requires_human_approved_new_cycle_amendment",
            "review_new_blocker": "stop_requires_human_approved_new_cycle_amendment",
            "recovery_failure": "preserve_failure_and_stop_no_retry",
        },
        "recovery terminal action differs",
    )
    return {
        "status": "pass_recovery_cycle_ledger_independent_verification",
        "recovery_cycle_ledger_receipt_sha256": receipt,
    }


def verify_paths(
    closure_path: Path,
    *,
    schema_path: Path,
    recovery_ledger_path: Path,
) -> dict[str, Any]:
    closure_path = closure_path.expanduser().absolute()
    closure = _load(closure_path)
    result = verify_closure(closure)
    schema_path = schema_path.expanduser().absolute()
    schema_file_sha256 = sha256_file(schema_path)
    _require(
        schema_file_sha256 == EXPECTED_SCHEMA_SHA256,
        "physical closure schema differs",
    )
    recovery_ledger_path = recovery_ledger_path.expanduser().absolute()
    ledger = _load(recovery_ledger_path)
    closure_file_sha256 = sha256_file(closure_path)
    cycle = verify_recovery_ledger(
        ledger,
        closure_receipt_sha256=result["incident_closure_receipt_sha256"],
        closure_file_sha256=closure_file_sha256,
    )
    core = {
        "schema_version": 1,
        "receipt_kind": (
            "consciousness_sae_signed_dose_scan_incident_closure_verification_v1"
        ),
        "status": "pass_incident_closure_and_cycle_independent_verification",
        "incident_closure_file_sha256": closure_file_sha256,
        "incident_closure_receipt_sha256": result[
            "incident_closure_receipt_sha256"
        ],
        "incident_closure_schema_file_sha256": schema_file_sha256,
        "recovery_cycle_ledger_file_sha256": sha256_file(recovery_ledger_path),
        "recovery_cycle_ledger_receipt_sha256": cycle[
            "recovery_cycle_ledger_receipt_sha256"
        ],
        "raw_record_count": result["raw_record_count"],
        "raw_stored_bytes": result["raw_stored_bytes"],
        "raw_records_sha256": result["raw_records_sha256"],
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
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _write_fresh(path: Path, value: Mapping[str, Any]) -> None:
    destination = path.expanduser().absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise IncidentClosureVerificationError(
            "verification output must be fresh in an existing directory"
        )
    payload = canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--recovery-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = verify_paths(
        args.closure,
        schema_path=args.schema,
        recovery_ledger_path=args.recovery_ledger,
    )
    if args.output is not None:
        _write_fresh(args.output, result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
