#!/usr/bin/env python3
"""Build the compact, current-study incident closure.

This producer is intentionally specific to the July 2026 signed-dose campaign.
It reads the preserved incident artifacts, checks their physical hashes and
semantic boundaries, embeds the complete metadata-only raw-file ledger, and
writes one canonical self-hashed receipt.  It never opens a raw tensor or row
file and never writes into the frozen plan or raw namespaces.

The independent verifier lives in ``verify_incident_closure.py`` and does not
import this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
RECEIPT_KIND = "consciousness_sae_signed_dose_scan_incident_closure_v1"
STATUS = "closed_recovery_required_no_compact_publication"
STUDY_ID = "consciousness_sae_signed_dose_scan_v1"
PROTOCOL_VERSION = "consciousness_sae_signed_dose_scan_v1.0.0"
FREEZE_COMMIT = "a084caafc2ec27860044d80d3b33912f656fd08a"
PLAN_GIT_HEAD_COMMIT = "6a065b1c64b8451a8f4fa408770f699ce7f5ff3f"
PLAN_MANIFEST_SHA256 = (
    "79810742bd2899ae0805e294fb5b9640870a21fe60e4c85a73b241b92963c51d"
)
PLAN_MANIFEST_FILE_SHA256 = (
    "559f43884221ec309e40b6b83cc9f4e23dbd13196a0ec506f805b329a1d5554e"
)
PROTOCOL_FILE_SHA256 = (
    "ff48ac9166ec782132d55b5a6f064ec8091c2a47fc57aa5b802f0bd62b59bb69"
)
REVIEW_ADJUDICATION_FILE_SHA256 = (
    "732f32e17c8df49062d87fbcfb8e4493d576f6ba71643ce8b724ac02dfc7a53d"
)
REVIEW_ADJUDICATION_RECEIPT_SHA256 = (
    "234254e67f8b897ea837590117932e4bfdfc261df7fc4eb460acf7047edba0d8"
)
REVIEW_MODEL = "gpt-5.6-sol"
REVIEW_RESPONSE_ID = "resp_0771e3684280ebf7016a595c85174c8198ae40e01f160772f0"
POD_ID = "wl8obvtuq0ax8t"
VOLUME_ID = "bv9gb9j32y"
DATA_CENTER_ID = "US-CA-2"
GPU_TYPE = "NVIDIA B200"

RAW_RUN_ID = "signed-dose-a084caa-wl8obvtuq0ax8t-v2"
RAW_RECORD_COUNT = 35
RAW_STORED_BYTES = 2_229_288_980
RAW_RECORDS_SHA256 = (
    "b5c784f4feb87ba01a9fc5d9b2f22d12eee01930d98718cd5c54e3d398692cf4"
)
RAW_RUN_COMPLETE_FILE_SHA256 = (
    "a5818ad5e208c9008df6ad0bede630fddafb06e07b5f0190d02b3b80ceefeb4b"
)
RAW_RUN_COMPLETE_RECEIPT_SHA256 = (
    "f714f16e2f6d5bb532d522c3ad0e2985e6f6b169ff5875911d296f42cd8fdc7d"
)


class IncidentClosureError(RuntimeError):
    """The preserved evidence cannot support the frozen closure."""


@dataclass(frozen=True)
class EvidenceSpec:
    role: str
    relative_name: str
    byte_count: int
    sha256: str
    receipt_sha256: str | None = None


# These physical hashes are the independently retained boundary for the
# producer.  The verifier restates them rather than importing this inventory.
EVIDENCE_SPECS = (
    EvidenceSpec(
        "ownership_receipt",
        "OWNERSHIP.json",
        1665,
        "a75782a605bcc2e71f1e72c1c35e4db761cecc7ffc716066bb374d3ceb291cce",
        "70799f1762922a7d06701a3a4f00f1dc2a71aee275eab8ab0700e1c6068f4979",
    ),
    EvidenceSpec(
        "guest_preflight",
        "GUEST_PREFLIGHT.json",
        1223,
        "e4955405f32e1ad4d1076f8f30109510b2cb43d26ac144bbf8fe5246a2105c90",
        "6e9f4e69d253075b7c40bcf904a9582c1f5a2ff2c646c1484ccec73940399db7",
    ),
    EvidenceSpec(
        "cache_preflight",
        "CACHE_PREFLIGHT.json",
        1522,
        "2d85c9bd807398721b81cc1195f4381cec81da8f5457f260b384b2660e22de1e",
        "77a738771e8073d381bb519beb58525534c3d192be9f94237c74c76043b11187",
    ),
    EvidenceSpec(
        "llama70b_v1_authorization",
        "AUTHORIZATION.json",
        3279,
        "8ae87ded7d9c7c6ac083bebab8ef217be9d7709875f49989993c1f15976a6ded",
        "c2d327a64958cab80e7a3ce82a382310033df0a53a51409f849604a22d8e318b",
    ),
    EvidenceSpec(
        "llama70b_v2_authorization",
        "AUTHORIZATION_V2.json",
        3279,
        "79933cc2f51ecb9015a903c2814c6a34c5e2288b577c5f548b55652b6c057e47",
        "687837a3a2fdf0de6cea7559ec7f2725ef4b014e56a0d014a8b30788325039b7",
    ),
    EvidenceSpec(
        "small_model_promotion_gate",
        "SMALL_MODEL_PROMOTION_GATE.json",
        2329,
        "5eb0e6a03206dc037aedd3682de82cc47a95508684e98c0af47022c87a0316e6",
        "f5417228aa80eed0004d1f1ac59f96abf937f9cb94590cb06d4957cdf4aba02b",
    ),
    EvidenceSpec(
        "gemma_v1_failure_receipt",
        "GEMMA_V1_INCIDENT/RUN_FAILED.json",
        757,
        "54193444cce49d83ff54b66a01e8a1ce16056d68c7dbc107d2f824070503e716",
    ),
    EvidenceSpec(
        "gemma_v1_status",
        "GEMMA_V1_INCIDENT/STATUS",
        49,
        "ddfbceedc38d280fe0d67aad7c98b6cc4fc9fc60fe62adf2b228c93dcd87b42d",
    ),
    EvidenceSpec(
        "gemma_v1_log",
        "GEMMA_V1_INCIDENT/signed-dose-gemma-a084caa.log",
        5449,
        "f7e8095253cf8ea5390984fb25742e1e70ebd110222cd7759500269a24ec808b",
    ),
    EvidenceSpec(
        "gemma_v2_audit",
        "GEMMA_V2_PASS/AUDIT.json",
        2329,
        "5eb0e6a03206dc037aedd3682de82cc47a95508684e98c0af47022c87a0316e6",
        "f5417228aa80eed0004d1f1ac59f96abf937f9cb94590cb06d4957cdf4aba02b",
    ),
    EvidenceSpec(
        "gemma_v2_run_manifest",
        "GEMMA_V2_PASS/RUN_MANIFEST.json",
        7633,
        "6ef8e3bea3d90886599bf56c98a6489efca245744f8e8bd921de8e46bbefa76b",
    ),
    EvidenceSpec(
        "gemma_v2_status",
        "GEMMA_V2_PASS/STATUS",
        49,
        "f857c56cc28e9ae73f5126cdf060e04c955d4598c35390a5f5f78a2cea8936b6",
    ),
    EvidenceSpec(
        "gemma_v2_log",
        "GEMMA_V2_PASS/signed-dose-gemma-a084caa-v2.log",
        1062,
        "d5ff556c15b356a4759dc37fdedc567ac5a538d3f43d72119de6345d6d753ff4",
    ),
    EvidenceSpec(
        "llama70b_v1_status",
        "V1_LAUNCH_INCIDENT/STATUS",
        51,
        "cbd363a0a4cfcd236b2d84141691f19c652aecd919627b50a971c68511ada21e",
    ),
    EvidenceSpec(
        "llama70b_v1_log",
        "V1_LAUNCH_INCIDENT/run.log",
        131,
        "5fe2b5d8d7df37860ee58cdeb85a7f5e83e14a11b2586ece23062ff4a4116248",
    ),
    EvidenceSpec(
        "llama70b_v2_run_complete",
        "V2_INCIDENT/RUN_COMPLETE.json",
        9987,
        RAW_RUN_COMPLETE_FILE_SHA256,
        RAW_RUN_COMPLETE_RECEIPT_SHA256,
    ),
    EvidenceSpec(
        "llama70b_v2_status",
        "V2_INCIDENT/STATUS",
        49,
        "41e31e05845259a45a830e7174b47ae6f1548ccfbc85aae2df8721fcfcd3cc05",
    ),
    EvidenceSpec(
        "llama70b_v2_execution_binding",
        "V2_INCIDENT/execution_binding.json",
        3078,
        "e1dbd1b1ff69297159a1d6a848ae8db5314e2d261b0e31fa9089db897f86b7c2",
    ),
    EvidenceSpec(
        "llama70b_v2_j_orientation",
        "V2_INCIDENT/j_orientation_receipt.json",
        1077,
        "58e63625f7301e8868cc2b858eaaa090468da1375200f4794787896badf73f3f",
    ),
    EvidenceSpec(
        "llama70b_v2_log",
        "V2_INCIDENT/run.log",
        4204,
        "c5309b1ff480041b4c50c81ed75ef42ec22121969ddd41a0d90109037a4134f6",
    ),
    EvidenceSpec(
        "llama70b_v2_runner_time",
        "V2_INCIDENT/runner.time",
        93,
        "1077570e358703942817d0c0f171df667824b3cb0bf9aae2d2a0472d582e0f17",
    ),
    EvidenceSpec(
        "llama70b_v2_runtime_metadata",
        "V2_INCIDENT/runtime_metadata.json",
        3201,
        "09462acc9df1365130242e68bafc7bdde835cb16110be04681842f5cb598948d",
    ),
    EvidenceSpec(
        "termination_audit",
        "TERMINATION_AUDIT.json",
        777,
        "3180a922744937adac0641dfc8e6f27db3b813e0c58cc43da7d693b9eab3ea67",
        "4147d073fb7d1debdd182e13f72be4610ed25cb1e783a3215ae7f66ed16faa04",
    ),
    EvidenceSpec(
        "postdelete_inventory",
        "POSTDELETE_INVENTORY.json",
        493,
        "2264249e9dfce51d6a78c4386a4d1dff6d64a7a4e00ed4bf664a87a70d92225c",
        "6022801ebd4c23fd0da32ccbc21ce4ff065b0935b99a77db2a1df0bc5c7fb47c",
    ),
)

WRAPPER_SPECS = (
    EvidenceSpec(
        "gemma_v1_wrapper",
        "run_signed_dose_gemma_gate.sh",
        1692,
        "330fcf3d64ae8692d9c827ea83b027df5c2e585c8a351d53654def1c3f4f17c5",
    ),
    EvidenceSpec(
        "gemma_v2_wrapper",
        "run_signed_dose_gemma_gate_v2.sh",
        1695,
        "23d64db6b9e2603d1dd40ade67dddcb016a219c5cb6306a1d184fe4e04c6c89a",
    ),
    EvidenceSpec(
        "llama70b_v1_wrapper",
        "run_signed_dose_70b_once.sh",
        3308,
        "2d1ab8d41900a8fda9205449b3d017db1de5b8379126c7725c88fc9a6358f820",
    ),
    EvidenceSpec(
        "llama70b_v2_wrapper",
        "run_signed_dose_70b_v2.sh",
        4025,
        "527c87909c6a4eb261f50da525bd56b7982041d9de28b83dfc47de840bba09ac",
    ),
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite_json(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_finite_json(child) for child in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _finite_json(child) for key, child in value.items())
    return False


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IncidentClosureError(f"invalid JSON evidence: {path}") from exc
    if not isinstance(value, dict) or not _finite_json(value):
        raise IncidentClosureError(f"JSON evidence is non-object or non-finite: {path}")
    return value


def _verify_self_hash(value: Mapping[str, Any], *, path: Path) -> str:
    supplied = value.get("receipt_sha256")
    if not isinstance(supplied, str):
        raise IncidentClosureError(f"missing receipt_sha256: {path}")
    core = dict(value)
    del core["receipt_sha256"]
    if supplied != canonical_sha256(core):
        raise IncidentClosureError(f"receipt self-hash differs: {path}")
    return supplied


def _artifact(path: Path, spec: EvidenceSpec) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise IncidentClosureError(f"evidence is missing, non-regular, or symlinked: {path}")
    payload = path.read_bytes()
    if len(payload) != spec.byte_count or sha256_bytes(payload) != spec.sha256:
        raise IncidentClosureError(f"evidence physical identity differs: {spec.role}")
    receipt_sha256: str | None = None
    if spec.receipt_sha256 is not None:
        value = _load_json(path)
        receipt_sha256 = _verify_self_hash(value, path=path)
        if receipt_sha256 != spec.receipt_sha256:
            raise IncidentClosureError(f"evidence content receipt differs: {spec.role}")
    return (
        {
            "role": spec.role,
            "relative_name": spec.relative_name,
            "bytes": len(payload),
            "sha256": spec.sha256,
            "content_receipt_sha256": receipt_sha256,
        },
        payload,
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IncidentClosureError(message)


def _status_fields(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise IncidentClosureError("STATUS evidence is not UTF-8") from exc
    fields: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or key in fields:
            raise IncidentClosureError("STATUS evidence is malformed")
        fields[key] = value
    if set(fields) != {"exit_code", "finished_at_utc"}:
        raise IncidentClosureError("STATUS field inventory differs")
    return fields


def _safe_raw_records(records: Any) -> list[dict[str, Any]]:
    _require(isinstance(records, list), "raw records are missing")
    normalized: list[dict[str, Any]] = []
    paths: list[str] = []
    for index, record in enumerate(records):
        _require(isinstance(record, dict), f"raw record {index} is not an object")
        _require(set(record) == {"path", "bytes", "sha256"}, f"raw record {index} fields differ")
        path = record["path"]
        byte_count = record["bytes"]
        sha256 = record["sha256"]
        _require(isinstance(path, str) and path and not path.startswith("/"), "raw path is not relative")
        _require(".." not in Path(path).parts and "\\" not in path, "raw path escapes its run root")
        _require(isinstance(byte_count, int) and not isinstance(byte_count, bool) and byte_count > 0, "raw byte count is invalid")
        _require(isinstance(sha256, str) and len(sha256) == 64 and all(c in "0123456789abcdef" for c in sha256), "raw hash is invalid")
        paths.append(path)
        normalized.append({"path": path, "bytes": byte_count, "sha256": sha256})
    _require(paths == sorted(paths) and len(paths) == len(set(paths)), "raw paths are not sorted and unique")
    _require(len(normalized) == RAW_RECORD_COUNT, "raw record count differs")
    _require(sum(row["bytes"] for row in normalized) == RAW_STORED_BYTES, "raw stored-byte sum differs")
    _require(canonical_sha256(normalized) == RAW_RECORDS_SHA256, "raw record commitment differs")
    return normalized


def _attempt_classifications() -> list[dict[str, Any]]:
    return [
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
            "authority_disposition": "promotion_scope_runner_mechanics_only_not_scientific_protocol",
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
            "execution_boundary": "wrapper_failed_on_missing_usr_bin_time_before_guest_launcher",
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
            "attempt_id": RAW_RUN_ID,
            "role": "llama70b_scientific_attempt",
            "terminal_status": "collection_complete_audit_failed",
            "outcome_access_classification": "raw_inputs_opened_or_recomputed",
            "execution_boundary": "strict_j_lens_inventory_rejection_during_independent_raw_recomputation",
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


def build_closure(
    *,
    evidence_root: Path,
    wrapper_paths: Mapping[str, Path],
    plan_manifest_path: Path,
    protocol_path: Path,
    review_adjudication_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    root = evidence_root.expanduser().absolute()
    _require(root.is_dir() and not root.is_symlink(), "evidence root is missing or symlinked")

    inventory: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for spec in EVIDENCE_SPECS:
        item, payload = _artifact(root / spec.relative_name, spec)
        inventory.append(item)
        payloads[spec.role] = payload
    for spec in WRAPPER_SPECS:
        path = wrapper_paths.get(spec.role)
        _require(path is not None, f"wrapper path is missing: {spec.role}")
        item, payload = _artifact(path.expanduser().absolute(), spec)
        inventory.append(item)
        payloads[spec.role] = payload

    plan_item, _ = _artifact(
        plan_manifest_path.expanduser().absolute(),
        EvidenceSpec(
            "frozen_plan_manifest",
            "data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716/PLAN_MANIFEST.json",
            plan_manifest_path.stat().st_size,
            PLAN_MANIFEST_FILE_SHA256,
        ),
    )
    protocol_item, _ = _artifact(
        protocol_path.expanduser().absolute(),
        EvidenceSpec(
            "frozen_protocol",
            "docs/consciousness_sae_signed_dose_scan/PROTOCOL.md",
            protocol_path.stat().st_size,
            PROTOCOL_FILE_SHA256,
        ),
    )
    review_item, _ = _artifact(
        review_adjudication_path.expanduser().absolute(),
        EvidenceSpec(
            "frozen_review_adjudication",
            "docs/consciousness_sae_signed_dose_scan/PRO_REVIEW_ADJUDICATION.json",
            review_adjudication_path.stat().st_size,
            REVIEW_ADJUDICATION_FILE_SHA256,
            REVIEW_ADJUDICATION_RECEIPT_SHA256,
        ),
    )
    inventory.extend((plan_item, protocol_item, review_item))

    schema_payload = schema_path.expanduser().absolute().read_bytes()
    _require(schema_path.is_file() and not schema_path.is_symlink(), "closure schema is missing or symlinked")
    schema_value = _load_json(schema_path)
    _require(schema_value.get("$id") == "urn:llm-selfref-pre:signed-dose-scan:incident-closure:v1", "closure schema identity differs")
    schema_item = {
        "role": "incident_closure_schema",
        "relative_name": "docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json",
        "bytes": len(schema_payload),
        "sha256": sha256_bytes(schema_payload),
        "content_receipt_sha256": None,
    }
    inventory.append(schema_item)
    inventory.sort(key=lambda row: row["role"])

    gemma_v1_failure = _load_json(root / "GEMMA_V1_INCIDENT/RUN_FAILED.json")
    gemma_v2_audit = _load_json(root / "GEMMA_V2_PASS/AUDIT.json")
    gemma_v2_manifest = _load_json(root / "GEMMA_V2_PASS/RUN_MANIFEST.json")
    auth_v1 = _load_json(root / "AUTHORIZATION.json")
    auth_v2 = _load_json(root / "AUTHORIZATION_V2.json")
    run_complete = _load_json(root / "V2_INCIDENT/RUN_COMPLETE.json")
    termination = _load_json(root / "TERMINATION_AUDIT.json")
    postdelete = _load_json(root / "POSTDELETE_INVENTORY.json")

    _require(gemma_v1_failure.get("status") == "failed" and gemma_v1_failure.get("error_type") == "OSError", "Gemma v1 failure semantics differ")
    _require(_status_fields(payloads["gemma_v1_status"])["exit_code"] == "1", "Gemma v1 exit differs")
    gemma_v1_log = payloads["gemma_v1_log"].decode("utf-8")
    _require("AutoTokenizer.from_pretrained" in gemma_v1_log and "401 Client Error" in gemma_v1_log, "Gemma v1 boundary differs")
    _require("Loading checkpoint shards" not in gemma_v1_log, "Gemma v1 unexpectedly reached model loading")

    _require(gemma_v2_audit.get("status") == "pass_small_model_promotion_gate", "Gemma v2 audit did not pass")
    _require(gemma_v2_audit.get("failures") == [] and gemma_v2_audit.get("scientific_claims_authorized") is None, "Gemma v2 audit scope differs")
    _require(gemma_v2_audit.get("promotion", {}).get("scientific_claims_authorized") is False, "Gemma v2 authorized a scientific claim")
    _require(gemma_v2_manifest.get("forward_inventory", {}).get("exact_total_model_forwards") == 122, "Gemma v2 forward count differs")
    _require(gemma_v2_manifest.get("scope", {}).get("semantic_outcomes_collected") is False, "Gemma v2 semantic scope differs")
    _require(_status_fields(payloads["gemma_v2_status"])["exit_code"] == "0", "Gemma v2 exit differs")

    _require(auth_v1.get("authorized_run_id") == "signed-dose-a084caa-wl8obvtuq0ax8t-v1", "70B v1 authority identity differs")
    _require(auth_v2.get("authorized_run_id") == RAW_RUN_ID, "70B v2 authority identity differs")
    _require(auth_v1.get("git_head_commit") == FREEZE_COMMIT and auth_v2.get("git_head_commit") == FREEZE_COMMIT, "authorization freeze differs")
    _require(_status_fields(payloads["llama70b_v1_status"])["exit_code"] == "127", "70B v1 exit differs")
    llama_v1_log = payloads["llama70b_v1_log"].decode("utf-8")
    _require("/usr/bin/time: No such file or directory" in llama_v1_log, "70B v1 failure boundary differs")
    _require("SIGNED_DOSE_AUDIT_START" not in llama_v1_log, "70B v1 unexpectedly reached audit")

    _require(run_complete.get("status") == "complete" and run_complete.get("run_id") == RAW_RUN_ID, "70B v2 run completion differs")
    runtime = run_complete.get("runtime", {})
    _require(runtime.get("model_forward_count") == 2896, "70B v2 model-forward count differs")
    _require(runtime.get("expected_model_forward_count") == 2896, "70B v2 expected-forward count differs")
    _require(runtime.get("forward_inventory", {}).get("exact_total_model_forwards") == 2896, "70B v2 forward inventory differs")
    _require(runtime.get("forward_inventory", {}).get("edited_continuation_forwards") == 2880, "70B v2 edited-forward count differs")
    records = _safe_raw_records(run_complete.get("records"))
    _require(run_complete.get("stored_bytes") == RAW_STORED_BYTES, "70B v2 stored bytes differ")
    _require(_status_fields(payloads["llama70b_v2_status"])["exit_code"] == "1", "70B v2 wrapper exit differs")
    llama_v2_log = payloads["llama70b_v2_log"].decode("utf-8")
    _require("SIGNED_DOSE_AUDIT_START" in llama_v2_log, "70B v2 audit was not reached")
    _require("CalibrationAuditError: J-lens map inventory differs" in llama_v2_log, "70B v2 audit failure differs")
    _require("SIGNED_DOSE_COMPLETE" not in llama_v2_log, "70B v2 wrapper unexpectedly completed")

    _require(termination.get("status") == "deleted_exact_owned_pod_unrelated_inventory_unchanged", "termination status differs")
    _require(termination.get("pod_id") == POD_ID, "terminated pod differs")
    _require(postdelete.get("pods") == [] and postdelete.get("all_account_pod_count") == 0, "postdelete inventory is not empty")
    _require(postdelete.get("inventory_sha256") == "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945", "empty inventory commitment differs")

    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_kind": RECEIPT_KIND,
        "status": STATUS,
        "study_id": STUDY_ID,
        "protocol_version": PROTOCOL_VERSION,
        "authority": {
            "freeze_commit": FREEZE_COMMIT,
            "plan_git_head_commit": PLAN_GIT_HEAD_COMMIT,
            "plan_manifest_sha256": PLAN_MANIFEST_SHA256,
            "plan_manifest_file_sha256": PLAN_MANIFEST_FILE_SHA256,
            "review_adjudication_receipt_sha256": REVIEW_ADJUDICATION_RECEIPT_SHA256,
            "review_model": REVIEW_MODEL,
            "review_response_id": REVIEW_RESPONSE_ID,
            "pod_id": POD_ID,
            "volume_id": VOLUME_ID,
            "data_center_id": DATA_CENTER_ID,
            "gpu_type": GPU_TYPE,
        },
        "evidence_inventory": inventory,
        "attempt_classifications": _attempt_classifications(),
        "raw_ledger": {
            "run_id": RAW_RUN_ID,
            "storage_role": "immutable_runpod_network_volume_raw_not_git",
            "file_count": len(records),
            "stored_bytes": sum(row["bytes"] for row in records),
            "records_sha256": canonical_sha256(records),
            "run_complete_file_sha256": RAW_RUN_COMPLETE_FILE_SHA256,
            "run_complete_receipt_sha256": RAW_RUN_COMPLETE_RECEIPT_SHA256,
            "records": records,
        },
        "termination": {
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            "pod_id": POD_ID,
            "termination_receipt_sha256": "4147d073fb7d1debdd182e13f72be4610ed25cb1e783a3215ae7f66ed16faa04",
            "postdelete_account_pod_count": 0,
            "postdelete_inventory_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            "network_volume_retained": True,
        },
        "terminal_disposition": {
            "rejected_authorized_run_ids": [
                "signed-dose-a084caa-wl8obvtuq0ax8t-v1",
                RAW_RUN_ID,
            ],
            "rejected_authorization_receipt_sha256": [
                "c2d327a64958cab80e7a3ce82a382310033df0a53a51409f849604a22d8e318b",
                "687837a3a2fdf0de6cea7559ec7f2725ef4b014e56a0d014a8b30788325039b7",
            ],
            "rejected_pod_ids": [POD_ID],
            "compact_publication_status": "not_produced",
            "scientific_plan_changed": False,
            "raw_outcome_bytes_changed": False,
            "raw_reuse_scope": "audit_only_recovery_after_fresh_authority_and_verified_cycle_ledger",
            "scientific_result_release_status": "blocked_pending_passing_independent_audit",
            "closure_grants_launch_authority": False,
        },
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}


def _write_fresh(path: Path, value: Mapping[str, Any]) -> None:
    destination = path.expanduser().absolute()
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise IncidentClosureError("closure output must be a fresh file in an existing directory")
    payload = canonical_json_bytes(dict(value)) + b"\n"
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--gemma-v1-wrapper", type=Path, required=True)
    parser.add_argument("--gemma-v2-wrapper", type=Path, required=True)
    parser.add_argument("--llama70b-v1-wrapper", type=Path, required=True)
    parser.add_argument("--llama70b-v2-wrapper", type=Path, required=True)
    parser.add_argument("--plan-manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--review-adjudication", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    closure = build_closure(
        evidence_root=args.evidence_root,
        wrapper_paths={
            "gemma_v1_wrapper": args.gemma_v1_wrapper,
            "gemma_v2_wrapper": args.gemma_v2_wrapper,
            "llama70b_v1_wrapper": args.llama70b_v1_wrapper,
            "llama70b_v2_wrapper": args.llama70b_v2_wrapper,
        },
        plan_manifest_path=args.plan_manifest,
        protocol_path=args.protocol,
        review_adjudication_path=args.review_adjudication,
        schema_path=args.schema,
    )
    _write_fresh(args.output, closure)
    print(f"{closure['status']} {closure['receipt_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
