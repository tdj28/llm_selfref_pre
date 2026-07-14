"""Fail-closed RunPod ownership, guest, cache, and cumulative-budget gates.

This module is intentionally network-free.  The lifecycle client supplies a
compact provider receipt; the guest validates it against PID-1/provider
identity and the mounted filesystem before staging or any model forward.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

from . import protocol


SCHEMA_VERSION = 1
EXPECTED_VOLUME_ID = "qf2lwehl89"
EXPECTED_DATA_CENTER_ID = "US-NE-1"
EXPECTED_GPU_TYPE = "NVIDIA B200"
VOLUME_MOUNT_PATH = "/workspace"
POD_NAME_PREFIX = "consciousness-sae-realization-validation-v1-"
MIN_MOUNTED_FREE_BYTES = 96 * 1024**3
EXPECTED_PROVIDER_VOLUME_BYTES = 500 * 1000**3
MAX_TOTAL_SECONDS = int(protocol.RESOURCE_LIMITS["max_walltime_seconds"])
MAX_TOTAL_SPEND_USD = float(protocol.RESOURCE_LIMITS["max_spend_usd"])
MAX_NO_PROGRESS_SECONDS = 20 * 60
POD_ID_RE = re.compile(r"[a-z0-9]{6,32}")
NONCE_RE = re.compile(r"[0-9a-f]{32}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")
POD_INVENTORY_FIELDS = (
    "pod_id",
    "pod_name",
    "desired_status",
    "gpu_type",
    "gpu_count",
)
LEGACY_PUBLIC_ARTIFACT_ROOT = (
    "/workspace/consciousness_readout_validation/"
    "consciousness_readout_validation_v1/public_artifacts"
)
PUBLIC_ARTIFACT_ROOT = (
    LEGACY_PUBLIC_ARTIFACT_ROOT
)
LEGACY_PUBLIC_ARTIFACT_MANIFEST_PATH = Path(__file__).with_name(
    "legacy_public_artifact_manifest.json"
)
LEGACY_PUBLIC_ARTIFACT_FILE_COUNT = 45
LEGACY_PUBLIC_ARTIFACT_BYTES = 156_023_372_845
LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256 = (
    "326e85683c4302dea27824923fa9b550738edd40f89a70b6e0b780530c8e5a96"
)
LEGACY_MODEL_FILE_INVENTORY_SHA256 = (
    "3c687d36b2977f77b0440839a48fe0351b585af2cdf756e644f64b62a8ff3db0"
)


class PreflightError(RuntimeError):
    """Raised before volume mutation or a model forward."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PreflightError("value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def with_self_hash(core: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(core)
    value["receipt_sha256"] = canonical_sha256(value)
    return value


def _self_hash(receipt: Mapping[str, Any], label: str) -> None:
    supplied = receipt.get("receipt_sha256")
    if not isinstance(supplied, str) or HEX64_RE.fullmatch(supplied) is None:
        raise PreflightError(f"{label} receipt hash is malformed")
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    if canonical_sha256(core) != supplied:
        raise PreflightError(f"{label} receipt self-hash differs")


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PreflightError(f"{label} is not UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PreflightError(f"{label} is malformed") from exc
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PreflightError("lifecycle time is timezone-naive")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def provider_terminate_after(created_at: datetime) -> str:
    """Return the provider-enforced six-hour kill deadline."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise PreflightError("provider creation time is timezone-naive")
    created = created_at.astimezone(timezone.utc).replace(microsecond=0)
    return _utc_text(created + timedelta(seconds=MAX_TOTAL_SECONDS))


def canonical_unrelated_inventory(
    pods: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Freeze an allowlisted view of unrelated pods without mutating them."""

    if not isinstance(pods, Sequence) or isinstance(pods, (str, bytes)):
        raise PreflightError("provider pod inventory is malformed")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for pod in pods:
        if not isinstance(pod, Mapping):
            raise PreflightError("provider pod inventory row is malformed")
        row = {field: pod.get(field) for field in POD_INVENTORY_FIELDS}
        pod_id = row["pod_id"]
        pod_name = row["pod_name"]
        if (
            not isinstance(pod_id, str)
            or POD_ID_RE.fullmatch(pod_id) is None
            or pod_id in seen_ids
            or not isinstance(pod_name, str)
            or not pod_name
        ):
            raise PreflightError("provider pod inventory identity is malformed")
        if pod_name.startswith(POD_NAME_PREFIX):
            raise PreflightError("pre-existing validation pod/name collision")
        seen_ids.add(pod_id)
        rows.append(row)
    return tuple(sorted(rows, key=lambda row: str(row["pod_id"])))


def validate_precreate_inventory(pods: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    inventory = canonical_unrelated_inventory(pods)
    return {
        "unrelated_pod_count": len(inventory),
        "unrelated_inventory_sha256": canonical_sha256(inventory),
    }


def build_create_contract(
    *, created_at: datetime, nonce: str, provider_pods: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Build the exact request contract; this does not call RunPod."""

    unrelated = validate_precreate_inventory(provider_pods)
    if not isinstance(nonce, str) or NONCE_RE.fullmatch(nonce) is None:
        raise PreflightError("ownership nonce is malformed")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise PreflightError("provider creation time is timezone-naive")
    created = created_at.astimezone(timezone.utc).replace(microsecond=0)
    core = {
        "schema_version": SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "pod_name": f"{POD_NAME_PREFIX}{created.strftime('%Y%m%d')}-{nonce}",
        "ownership_nonce": nonce,
        "network_volume_id": EXPECTED_VOLUME_ID,
        "provider_volume_size_bytes": EXPECTED_PROVIDER_VOLUME_BYTES,
        "data_center_id": EXPECTED_DATA_CENTER_ID,
        "gpu_type": EXPECTED_GPU_TYPE,
        "gpu_count": 1,
        "volume_mount_path": VOLUME_MOUNT_PATH,
        "terminate_after": provider_terminate_after(created),
        "created_at": _utc_text(created),
        "max_total_seconds": MAX_TOTAL_SECONDS,
        "max_total_spend_usd": MAX_TOTAL_SPEND_USD,
        "precreate_unrelated_pod_count": unrelated["unrelated_pod_count"],
        "precreate_unrelated_inventory_sha256": unrelated[
            "unrelated_inventory_sha256"
        ],
    }
    return {**core, "create_contract_sha256": canonical_sha256(core)}


CREATE_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "study_id",
        "protocol_version",
        "pod_name",
        "ownership_nonce",
        "network_volume_id",
        "provider_volume_size_bytes",
        "data_center_id",
        "gpu_type",
        "gpu_count",
        "volume_mount_path",
        "terminate_after",
        "created_at",
        "max_total_seconds",
        "max_total_spend_usd",
        "precreate_unrelated_pod_count",
        "precreate_unrelated_inventory_sha256",
        "create_contract_sha256",
    }
)


def validate_create_contract(
    contract: Mapping[str, Any], *, precreate_pods: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not isinstance(contract, Mapping) or set(contract) != CREATE_CONTRACT_FIELDS:
        raise PreflightError("create contract schema differs")
    core = dict(contract)
    supplied = core.pop("create_contract_sha256")
    if not isinstance(supplied, str) or canonical_sha256(core) != supplied:
        raise PreflightError("create contract hash differs")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "network_volume_id": EXPECTED_VOLUME_ID,
        "provider_volume_size_bytes": EXPECTED_PROVIDER_VOLUME_BYTES,
        "data_center_id": EXPECTED_DATA_CENTER_ID,
        "gpu_type": EXPECTED_GPU_TYPE,
        "gpu_count": 1,
        "volume_mount_path": VOLUME_MOUNT_PATH,
        "max_total_seconds": MAX_TOTAL_SECONDS,
        "max_total_spend_usd": MAX_TOTAL_SPEND_USD,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise PreflightError("create contract frozen scope differs")
    if (
        not isinstance(contract["pod_name"], str)
        or not contract["pod_name"].startswith(POD_NAME_PREFIX)
        or NONCE_RE.fullmatch(str(contract["ownership_nonce"])) is None
        or contract["ownership_nonce"] not in contract["pod_name"]
    ):
        raise PreflightError("create contract pod name/nonce differs")
    created = _utc(str(contract["created_at"]), "create contract created_at")
    deadline = _utc(
        str(contract["terminate_after"]), "create contract terminate_after"
    )
    if deadline - created != timedelta(seconds=MAX_TOTAL_SECONDS):
        raise PreflightError("create contract provider deadline differs")
    inventory = canonical_unrelated_inventory(precreate_pods)
    if (
        contract["precreate_unrelated_pod_count"] != len(inventory)
        or contract["precreate_unrelated_inventory_sha256"]
        != canonical_sha256(inventory)
    ):
        raise PreflightError("create contract precreate inventory differs")
    return dict(contract)


OWNERSHIP_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "pod_id",
        "pod_name",
        "ownership_nonce",
        "network_volume_id",
        "provider_volume_size_bytes",
        "data_center_id",
        "gpu_type",
        "gpu_count",
        "volume_mount_path",
        "created_at",
        "terminate_after",
        "create_contract_sha256",
        "upstream_lifecycle_receipt_sha256",
        "provider_container_image_attestation",
        "desired_status",
        "locked",
        "precreate_unrelated_pod_count",
        "precreate_unrelated_inventory_sha256",
        "receipt_sha256",
    }
)


def validate_ownership_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or set(receipt) != OWNERSHIP_FIELDS:
        raise PreflightError("ownership receipt schema differs")
    _self_hash(receipt, "ownership")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["status"] != "owned_running_isolated"
        or receipt["study_id"] != protocol.STUDY_ID
        or receipt["protocol_version"] != protocol.PROTOCOL_VERSION
    ):
        raise PreflightError("ownership receipt identity/status differs")
    if not isinstance(receipt["pod_id"], str) or POD_ID_RE.fullmatch(receipt["pod_id"]) is None:
        raise PreflightError("owned pod ID is malformed")
    if (
        not isinstance(receipt["pod_name"], str)
        or not receipt["pod_name"].startswith(POD_NAME_PREFIX)
        or receipt["ownership_nonce"] not in receipt["pod_name"]
        or NONCE_RE.fullmatch(str(receipt["ownership_nonce"])) is None
    ):
        raise PreflightError("owned pod name/nonce differs")
    expected = {
        "network_volume_id": EXPECTED_VOLUME_ID,
        "provider_volume_size_bytes": EXPECTED_PROVIDER_VOLUME_BYTES,
        "data_center_id": EXPECTED_DATA_CENTER_ID,
        "gpu_type": EXPECTED_GPU_TYPE,
        "gpu_count": 1,
        "volume_mount_path": VOLUME_MOUNT_PATH,
        "desired_status": "RUNNING",
        "locked": False,
    }
    if any(receipt[key] != value for key, value in expected.items()):
        raise PreflightError("owned provider resources differ")
    if (
        isinstance(receipt["precreate_unrelated_pod_count"], bool)
        or not isinstance(receipt["precreate_unrelated_pod_count"], int)
        or receipt["precreate_unrelated_pod_count"] < 0
        or not isinstance(receipt["precreate_unrelated_inventory_sha256"], str)
        or HEX64_RE.fullmatch(receipt["precreate_unrelated_inventory_sha256"]) is None
    ):
        raise PreflightError("unrelated provider inventory binding is malformed")
    created = _utc(receipt["created_at"], "created_at")
    deadline = _utc(receipt["terminate_after"], "terminate_after")
    if deadline <= created or deadline - created != timedelta(seconds=MAX_TOTAL_SECONDS):
        raise PreflightError("provider terminateAfter is not the exact six-hour guard")
    if not isinstance(receipt["create_contract_sha256"], str) or HEX64_RE.fullmatch(
        receipt["create_contract_sha256"]
    ) is None:
        raise PreflightError("create-contract hash is malformed")
    if not isinstance(
        receipt["upstream_lifecycle_receipt_sha256"], str
    ) or HEX64_RE.fullmatch(receipt["upstream_lifecycle_receipt_sha256"]) is None:
        raise PreflightError("upstream lifecycle receipt hash is malformed")
    image_attestation = receipt["provider_container_image_attestation"]
    if not isinstance(image_attestation, Mapping) or set(image_attestation) != {
        "source",
        "immutable_reference",
        "graphql_create_snapshot_source",
        "create_request_sha256",
        "final_rest_proof_source",
        "rest_image_fields",
        "upstream_lifecycle_receipt_sha256",
    }:
        raise PreflightError("provider container-image attestation schema differs")
    rest_image_fields = image_attestation["rest_image_fields"]
    if (
        image_attestation["source"]
        != "validated_graphql_create_plus_final_rest_readback_v1"
        or image_attestation["immutable_reference"]
        != protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]
        or image_attestation["graphql_create_snapshot_source"]
        != "graphql_create_plus_rest_volume_proof"
        or not isinstance(image_attestation["create_request_sha256"], str)
        or HEX64_RE.fullmatch(image_attestation["create_request_sha256"]) is None
        or image_attestation["final_rest_proof_source"]
        != "rest_v1_pod_get_final_after_graphql_locked_state"
        or not isinstance(rest_image_fields, list)
        or rest_image_fields != sorted(rest_image_fields)
        or not rest_image_fields
        or len(rest_image_fields) != len(set(rest_image_fields))
        or any(field not in {"image", "imageName"} for field in rest_image_fields)
        or image_attestation["upstream_lifecycle_receipt_sha256"]
        != receipt["upstream_lifecycle_receipt_sha256"]
    ):
        raise PreflightError("provider container-image attestation differs")
    return dict(receipt)


FROZEN_UPSTREAM_OWNERSHIP_FIELDS = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "study_id",
        "status",
        "agent_owned",
        "other_pods_mutated",
        "created_at_utc",
        "hard_deadline_utc",
        "provider_terminate_after_utc",
        "authorization",
        "request_sha256",
        "pod",
        "graphql_locked_state_proof",
        "rest_corroboration",
        "receipt_sha256",
    }
)


def build_successor_ownership_receipt(
    *,
    upstream_ownership: Mapping[str, Any],
    create_contract: Mapping[str, Any],
    precreate_pods: Sequence[Mapping[str, Any]],
    postcreate_pods: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bridge the audited nested lifecycle receipt into the flat guest authority."""

    contract = validate_create_contract(
        create_contract, precreate_pods=precreate_pods
    )
    if (
        not isinstance(upstream_ownership, Mapping)
        or set(upstream_ownership) != FROZEN_UPSTREAM_OWNERSHIP_FIELDS
    ):
        raise PreflightError("upstream lifecycle ownership schema differs")
    upstream = dict(upstream_ownership)
    upstream_hash = upstream.pop("receipt_sha256", None)
    if (
        not isinstance(upstream_hash, str)
        or HEX64_RE.fullmatch(upstream_hash) is None
        or canonical_sha256(upstream) != upstream_hash
    ):
        raise PreflightError("upstream lifecycle ownership hash differs")
    upstream["receipt_sha256"] = upstream_hash
    if (
        upstream["schema_version"] != 1
        or upstream["receipt_kind"] != "runpod_pod_ownership_v1"
        or upstream["study_id"] != protocol.STUDY_ID
        or upstream["status"] != "created"
        or upstream["agent_owned"] is not True
        or upstream["other_pods_mutated"] is not False
        or upstream["created_at_utc"] != contract["created_at"]
        or upstream["hard_deadline_utc"] != contract["terminate_after"]
        or upstream["provider_terminate_after_utc"] != contract["terminate_after"]
        or upstream["authorization"] != {"max_usd": "36", "max_hours": "6"}
        or not isinstance(upstream["request_sha256"], str)
        or HEX64_RE.fullmatch(upstream["request_sha256"]) is None
    ):
        raise PreflightError("upstream lifecycle ownership scope differs")
    pod = upstream["pod"]
    graphql = upstream["graphql_locked_state_proof"]
    rest = upstream["rest_corroboration"]
    if not all(isinstance(value, Mapping) for value in (pod, graphql, rest)):
        raise PreflightError("upstream provider proofs are malformed")
    rest_observed_fields = rest.get("observed_config_fields")
    rest_image_fields = (
        sorted({"image", "imageName"}.intersection(rest_observed_fields))
        if isinstance(rest_observed_fields, list)
        and all(isinstance(field, str) for field in rest_observed_fields)
        else []
    )
    provider_image = pod.get("image")
    if (
        pod.get("identity_source") != "graphql_create_plus_rest_volume_proof"
        or provider_image
        != protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]
        or rest.get("proof_source")
        != "rest_v1_pod_get_final_after_graphql_locked_state"
        or rest.get("all_present_config_fields_match") is not True
        or not rest_image_fields
    ):
        raise PreflightError(
            "upstream provider container-image observations differ"
        )
    expected_pod = {
        "name": contract["pod_name"],
        "network_volume_id": contract["network_volume_id"],
        "network_volume_size_gb": (
            contract["provider_volume_size_bytes"] // 1_000_000_000
        ),
        "data_center_id": contract["data_center_id"],
        "network_volume_data_center_id": contract["data_center_id"],
        "gpu_type_id_requested": contract["gpu_type"],
        "gpu_type_id": contract["gpu_type"],
        "gpu_count": contract["gpu_count"],
        "volume_mount_path": contract["volume_mount_path"],
        "locked": False,
    }
    if any(pod.get(key) != value for key, value in expected_pod.items()):
        raise PreflightError("upstream owned pod differs from create contract")
    pod_id = pod.get("id")
    if not isinstance(pod_id, str) or POD_ID_RE.fullmatch(pod_id) is None:
        raise PreflightError("upstream owned pod ID is malformed")
    proof_expected = {
        "id": pod_id,
        "name": contract["pod_name"],
        "desired_status": "RUNNING",
    }
    if (
        any(graphql.get(key) != value for key, value in proof_expected.items())
        or graphql.get("locked") is not False
        or any(rest.get(key) != value for key, value in proof_expected.items())
        or rest.get("all_present_config_fields_match") is not True
    ):
        raise PreflightError("upstream running/locked provider proof differs")
    try:
        hourly = Decimal(str(pod.get("cost_per_hour_usd")))
        rest_hourly = Decimal(str(rest.get("cost_per_hour_usd")))
    except (InvalidOperation, ValueError) as exc:
        raise PreflightError("upstream provider rate is malformed") from exc
    if (
        not hourly.is_finite()
        or not rest_hourly.is_finite()
        or hourly <= 0
        or rest_hourly <= 0
        or max(hourly, rest_hourly) * Decimal(6) > Decimal(36)
    ):
        raise PreflightError("upstream six-hour provider rate exceeds $36")
    before = canonical_unrelated_inventory(precreate_pods)
    owned_rows = [
        row
        for row in postcreate_pods
        if row.get("pod_id") == pod_id
        and row.get("pod_name") == contract["pod_name"]
    ]
    if len(owned_rows) != 1:
        raise PreflightError("post-create inventory lacks one exact owned pod")
    after = canonical_unrelated_inventory(
        [row for row in postcreate_pods if row is not owned_rows[0]]
    )
    if before != after:
        raise PreflightError("unrelated provider inventory changed during create")
    core = {
        "schema_version": SCHEMA_VERSION,
        "status": "owned_running_isolated",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "pod_id": pod_id,
        "pod_name": contract["pod_name"],
        "ownership_nonce": contract["ownership_nonce"],
        "network_volume_id": contract["network_volume_id"],
        "provider_volume_size_bytes": contract["provider_volume_size_bytes"],
        "data_center_id": contract["data_center_id"],
        "gpu_type": contract["gpu_type"],
        "gpu_count": contract["gpu_count"],
        "volume_mount_path": contract["volume_mount_path"],
        "created_at": contract["created_at"],
        "terminate_after": contract["terminate_after"],
        "create_contract_sha256": contract["create_contract_sha256"],
        "upstream_lifecycle_receipt_sha256": upstream_hash,
        "provider_container_image_attestation": {
            "source": "validated_graphql_create_plus_final_rest_readback_v1",
            # This value is copied from the validated provider snapshot, not
            # synthesized from the successor protocol by the guest launcher.
            "immutable_reference": provider_image,
            "graphql_create_snapshot_source": pod["identity_source"],
            "create_request_sha256": upstream["request_sha256"],
            "final_rest_proof_source": rest["proof_source"],
            "rest_image_fields": rest_image_fields,
            "upstream_lifecycle_receipt_sha256": upstream_hash,
        },
        "desired_status": "RUNNING",
        "locked": False,
        "precreate_unrelated_pod_count": len(before),
        "precreate_unrelated_inventory_sha256": canonical_sha256(before),
    }
    receipt = with_self_hash(core)
    validate_ownership_receipt(receipt)
    return receipt


def validate_inventory_after_create(
    *,
    precreate_pods: Sequence[Mapping[str, Any]],
    postcreate_pods: Sequence[Mapping[str, Any]],
    ownership_receipt: Mapping[str, Any],
) -> None:
    """Require exactly one new owned pod and byte-stable unrelated inventory."""

    ownership = validate_ownership_receipt(ownership_receipt)
    before = canonical_unrelated_inventory(precreate_pods)
    owned_rows = [
        pod for pod in postcreate_pods if pod.get("pod_id") == ownership["pod_id"]
    ]
    if len(owned_rows) != 1 or owned_rows[0].get("pod_name") != ownership["pod_name"]:
        raise PreflightError("exact owned pod is absent or duplicated after create")
    after_unrelated = [
        pod for pod in postcreate_pods if pod.get("pod_id") != ownership["pod_id"]
    ]
    after = canonical_unrelated_inventory(after_unrelated)
    if before != after:
        raise PreflightError("unrelated pod inventory changed during create")
    if (
        len(before) != ownership["precreate_unrelated_pod_count"]
        or canonical_sha256(before)
        != ownership["precreate_unrelated_inventory_sha256"]
    ):
        raise PreflightError("ownership receipt unrelated-inventory binding differs")


def validate_inventory_after_delete(
    *,
    precreate_pods: Sequence[Mapping[str, Any]],
    postdelete_pods: Sequence[Mapping[str, Any]],
    ownership_receipt: Mapping[str, Any],
) -> None:
    """Prove exact-ID deletion left every unrelated pod unchanged."""

    ownership = validate_ownership_receipt(ownership_receipt)
    if any(pod.get("pod_id") == ownership["pod_id"] for pod in postdelete_pods):
        raise PreflightError("owned pod still exists after exact-ID delete")
    if canonical_unrelated_inventory(precreate_pods) != canonical_unrelated_inventory(
        postdelete_pods
    ):
        raise PreflightError("unrelated pod inventory changed during delete")


def require_exact_owned_pod_id(
    requested_pod_id: str, *, ownership_receipt: Mapping[str, Any]
) -> str:
    ownership = validate_ownership_receipt(ownership_receipt)
    if requested_pod_id != ownership["pod_id"]:
        raise PreflightError("provider operation is not scoped to the exact owned pod ID")
    return requested_pod_id


RUNPOD_IDENTITY_ENV = (
    "RUNPOD_POD_ID",
    "RUNPOD_VOLUME_ID",
    "RUNPOD_DC_ID",
)
MAX_PID1_ENVIRON_BYTES = 1024 * 1024
MAX_PID1_ENVIRON_ENTRIES = 16_384
MAX_MOUNTINFO_BYTES = 4 * 1024**2
MAX_MOUNTINFO_LINES = 65_536


def _default_read_pid1_environ() -> bytes:
    try:
        with Path("/proc/1/environ").open("rb") as handle:
            payload = handle.read(MAX_PID1_ENVIRON_BYTES + 1)
    except OSError as exc:
        raise PreflightError("provider PID-1 environment could not be read") from exc
    if len(payload) > MAX_PID1_ENVIRON_BYTES:
        raise PreflightError("provider PID-1 environment exceeds its parser limit")
    return payload


def _provider_pid1_identity(
    payload: bytes, *, ownership: Mapping[str, Any]
) -> tuple[dict[str, str], str]:
    expected = {
        "RUNPOD_POD_ID": str(ownership["pod_id"]),
        "RUNPOD_VOLUME_ID": EXPECTED_VOLUME_ID,
        "RUNPOD_DC_ID": EXPECTED_DATA_CENTER_ID,
    }
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > MAX_PID1_ENVIRON_BYTES
        or not payload.endswith(b"\0")
    ):
        raise PreflightError("provider PID-1 environment is malformed")
    entries = payload[:-1].split(b"\0")
    if not entries or len(entries) > MAX_PID1_ENVIRON_ENTRIES:
        raise PreflightError("provider PID-1 environment structure is unsafe")
    allowlist = {name.encode("ascii"): name for name in RUNPOD_IDENTITY_ENV}
    observed: dict[str, str] = {}
    for entry in entries:
        if not entry or len(entry) > 64 * 1024:
            raise PreflightError("provider PID-1 environment entry is unsafe")
        name, separator, raw_value = entry.partition(b"=")
        if not separator or not name:
            raise PreflightError("provider PID-1 environment entry is malformed")
        selected = allowlist.get(name)
        if selected is None:
            continue
        if selected in observed or len(raw_value) > 256:
            raise PreflightError("provider PID-1 identity is duplicated or oversized")
        try:
            observed[selected] = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PreflightError("provider PID-1 identity is not UTF-8") from exc
    if observed != expected:
        raise PreflightError("provider PID-1 identity differs from ownership")
    return observed, canonical_sha256(observed)


def _default_read_mountinfo() -> str:
    try:
        with Path("/proc/self/mountinfo").open("rb") as handle:
            payload = handle.read(MAX_MOUNTINFO_BYTES + 1)
    except OSError as exc:
        raise PreflightError("mountinfo could not be read") from exc
    if len(payload) > MAX_MOUNTINFO_BYTES:
        raise PreflightError("mountinfo exceeds its parser limit")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightError("mountinfo is not UTF-8") from exc


def _decode_mountinfo_path(value: str) -> str:
    replacements = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
            continue
        code = value[index + 1 : index + 4]
        if len(code) != 3 or code not in replacements:
            raise PreflightError("mountinfo path escape is unsupported")
        output.append(replacements[code])
        index += 4
    return "".join(output)


def _mount_identity(
    root: Path,
    *,
    mountinfo_text: str,
    is_mount: Callable[[str], bool],
    require_exact_mount_path: bool,
) -> tuple[str, str]:
    if root.is_symlink() or not root.is_dir():
        raise PreflightError("workspace root is not a real directory")
    if require_exact_mount_path and root.as_posix() != VOLUME_MOUNT_PATH:
        raise PreflightError("guest builder requires exact /workspace")
    if not is_mount(str(root)):
        raise PreflightError("workspace is not an operating-system mount point")
    try:
        payload = mountinfo_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PreflightError("mountinfo is not UTF-8") from exc
    lines = mountinfo_text.splitlines()
    if (
        not lines
        or len(payload) > MAX_MOUNTINFO_BYTES
        or len(lines) > MAX_MOUNTINFO_LINES
    ):
        raise PreflightError("mountinfo bounds differ")
    matches: list[dict[str, str]] = []
    root_text = str(root)
    for line in lines:
        if line.count(" - ") != 1:
            raise PreflightError("mountinfo line structure is malformed")
        left, _, right = line.partition(" - ")
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            raise PreflightError("mountinfo line fields are malformed")
        if _decode_mountinfo_path(left_fields[4]) != root_text:
            continue
        filesystem_type = right_fields[0]
        device = left_fields[2]
        if (
            re.fullmatch(r"[A-Za-z0-9._+-]+", filesystem_type) is None
            or re.fullmatch(r"[0-9]+:[0-9]+", device) is None
            or not left_fields[3].startswith("/")
        ):
            raise PreflightError("workspace mount identity is malformed")
        matches.append(
            {
                "filesystem_type": filesystem_type,
                "device_major_minor": device,
                "mount_root_raw_sha256": hashlib.sha256(
                    left_fields[3].encode("utf-8")
                ).hexdigest(),
                "mount_source_raw_sha256": hashlib.sha256(
                    right_fields[1].encode("utf-8")
                ).hexdigest(),
            }
        )
    if len(matches) != 1:
        raise PreflightError("mountinfo lacks one exact workspace entry")
    evidence_hash = canonical_sha256(matches[0])
    return evidence_hash, evidence_hash


GUEST_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "ownership_receipt_sha256",
        "attested_at_utc",
        "identity_source",
        "provider_identity_sha256",
        "observed_pod_id",
        "observed_volume_id",
        "observed_data_center_id",
        "mount_path",
        "mount_is_network_volume",
        "filesystem_id",
        "mount_evidence_sha256",
        "provider_volume_size_bytes",
        "logical_bytes_on_volume",
        "allocated_bytes_on_volume",
        "accounted_usage_bytes",
        "quota_remaining_bytes",
        "statvfs_free_bytes_diagnostic",
        "minimum_required_free_bytes",
        "model_forward_count",
        "target_prompt_render_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)


def build_guest_receipt(
    *,
    ownership_receipt: Mapping[str, Any],
    volume_root: Path = Path(VOLUME_MOUNT_PATH),
    read_pid1_environ: Callable[[], bytes] = _default_read_pid1_environ,
    read_mountinfo: Callable[[], str] = _default_read_mountinfo,
    is_mount: Callable[[str], bool] = os.path.ismount,
    statvfs: Callable[[Path], Any] = os.statvfs,
    now: datetime | None = None,
    require_exact_mount_path: bool = True,
) -> dict[str, Any]:
    """Measure the guest and issue a self-hashed pre-model receipt."""

    ownership = validate_ownership_receipt(ownership_receipt)
    root = Path(volume_root)
    try:
        identity, identity_hash = _provider_pid1_identity(
            read_pid1_environ(), ownership=ownership
        )
        filesystem_id, mount_hash = _mount_identity(
            root,
            mountinfo_text=read_mountinfo(),
            is_mount=is_mount,
            require_exact_mount_path=require_exact_mount_path,
        )
        usage = measure_volume_usage(root)
        filesystem = statvfs(root)
        statvfs_free = int(filesystem.f_bavail) * int(filesystem.f_frsize)
    except PreflightError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise PreflightError("guest filesystem measurement failed") from exc
    if statvfs_free < 0:
        raise PreflightError("statvfs diagnostic is negative")
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise PreflightError("guest attestation time is timezone-naive")
    core = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "attested_at_utc": _utc_text(observed.replace(microsecond=0)),
        "identity_source": "provider_pid1_environment",
        "provider_identity_sha256": identity_hash,
        "observed_pod_id": identity["RUNPOD_POD_ID"],
        "observed_volume_id": identity["RUNPOD_VOLUME_ID"],
        "observed_data_center_id": identity["RUNPOD_DC_ID"],
        "mount_path": VOLUME_MOUNT_PATH,
        "mount_is_network_volume": True,
        "filesystem_id": filesystem_id,
        "mount_evidence_sha256": mount_hash,
        "provider_volume_size_bytes": ownership["provider_volume_size_bytes"],
        "logical_bytes_on_volume": usage["logical_bytes_on_volume"],
        "allocated_bytes_on_volume": usage["allocated_bytes_on_volume"],
        "accounted_usage_bytes": usage["accounted_usage_bytes"],
        "quota_remaining_bytes": usage["quota_remaining_bytes"],
        "statvfs_free_bytes_diagnostic": statvfs_free,
        "minimum_required_free_bytes": MIN_MOUNTED_FREE_BYTES,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "prior_outcome_inputs": [],
    }
    receipt = with_self_hash(core)
    validate_guest_receipt(receipt, ownership_receipt=ownership)
    return receipt


def validate_guest_receipt(
    receipt: Mapping[str, Any], *, ownership_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    ownership = validate_ownership_receipt(ownership_receipt)
    if not isinstance(receipt, Mapping) or set(receipt) != GUEST_FIELDS:
        raise PreflightError("guest receipt schema differs")
    _self_hash(receipt, "guest")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["status"] != "pass"
        or receipt["study_id"] != protocol.STUDY_ID
        or receipt["protocol_version"] != protocol.PROTOCOL_VERSION
        or receipt["ownership_receipt_sha256"] != ownership["receipt_sha256"]
    ):
        raise PreflightError("guest receipt identity/binding differs")
    attested = _utc(receipt["attested_at_utc"], "attested_at_utc")
    created = _utc(ownership["created_at"], "created_at")
    deadline = _utc(ownership["terminate_after"], "terminate_after")
    if attested < created or attested >= deadline:
        raise PreflightError("guest receipt time is outside owned lifecycle")
    if (
        receipt["identity_source"] != "provider_pid1_environment"
        or not isinstance(receipt["provider_identity_sha256"], str)
        or HEX64_RE.fullmatch(receipt["provider_identity_sha256"]) is None
        or not isinstance(receipt["mount_evidence_sha256"], str)
        or HEX64_RE.fullmatch(receipt["mount_evidence_sha256"]) is None
    ):
        raise PreflightError("guest provider/mount evidence is malformed")
    if (
        receipt["observed_pod_id"] != ownership["pod_id"]
        or receipt["observed_volume_id"] != EXPECTED_VOLUME_ID
        or receipt["observed_data_center_id"] != EXPECTED_DATA_CENTER_ID
        or receipt["mount_path"] != VOLUME_MOUNT_PATH
        or receipt["mount_is_network_volume"] is not True
    ):
        raise PreflightError("guest/provider ownership differs")
    if not isinstance(receipt["filesystem_id"], str) or not receipt["filesystem_id"]:
        raise PreflightError("mounted filesystem identity is missing")
    numeric_fields = (
        "provider_volume_size_bytes",
        "logical_bytes_on_volume",
        "allocated_bytes_on_volume",
        "accounted_usage_bytes",
        "quota_remaining_bytes",
        "statvfs_free_bytes_diagnostic",
    )
    values: dict[str, int] = {}
    for field in numeric_fields:
        value = receipt[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PreflightError(f"guest capacity field is invalid: {field}")
        values[field] = value
    if values["provider_volume_size_bytes"] != ownership[
        "provider_volume_size_bytes"
    ]:
        raise PreflightError("guest/control-plane volume size differs")
    if values["accounted_usage_bytes"] != max(
        values["logical_bytes_on_volume"], values["allocated_bytes_on_volume"]
    ):
        raise PreflightError("quota accounting is not conservative")
    if values["quota_remaining_bytes"] != max(
        0,
        values["provider_volume_size_bytes"] - values["accounted_usage_bytes"],
    ):
        raise PreflightError("quota remaining is miscomputed")
    if (
        values["quota_remaining_bytes"] < MIN_MOUNTED_FREE_BYTES
        or receipt["minimum_required_free_bytes"] != MIN_MOUNTED_FREE_BYTES
    ):
        raise PreflightError("provider-volume quota gate failed")
    if receipt["model_forward_count"] != 0 or receipt["target_prompt_render_count"] != 0:
        raise PreflightError("guest gate ran after model/target access")
    if receipt["prior_outcome_inputs"] != []:
        raise PreflightError("guest gate used a prior outcome")
    return dict(receipt)


def measure_volume_usage(root: Path) -> dict[str, int]:
    """Measure logical and allocated bytes without following symlinks.

    Logical size is retained alongside ``st_blocks * 512`` and the larger is
    charged, so sparse files cannot manufacture apparent quota headroom.
    """

    root_path = Path(root)
    root_stat = root_path.lstat()
    if not root_path.is_dir() or root_path.is_symlink():
        raise PreflightError("volume root is not a real directory")
    logical = int(root_stat.st_size)
    allocated = int(root_stat.st_blocks) * 512
    stack = [root_path]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise PreflightError("volume usage scan failed") from exc
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise PreflightError("volume usage stat failed") from exc
            logical += int(stat.st_size)
            allocated += int(stat.st_blocks) * 512
            if entry.is_symlink():
                # Charge the link inode itself but never traverse its target.
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            elif not entry.is_file(follow_symlinks=False):
                raise PreflightError("non-regular volume object encountered")
    accounted = max(logical, allocated)
    return {
        "logical_bytes_on_volume": logical,
        "allocated_bytes_on_volume": allocated,
        "accounted_usage_bytes": accounted,
        "quota_remaining_bytes": max(0, EXPECTED_PROVIDER_VOLUME_BYTES - accounted),
    }


def validate_study_owned_output_tree(root: Path) -> dict[str, int]:
    """Reject symlinks/special objects inside a successor-owned output tree."""

    output_root = Path(root)
    try:
        root_stat = output_root.lstat()
    except OSError as exc:
        raise PreflightError("study output root is unreadable") from exc
    if output_root.is_symlink() or not output_root.is_dir():
        raise PreflightError("study output root is not a real directory")
    file_count = 0
    logical = int(root_stat.st_size)
    allocated = int(root_stat.st_blocks) * 512
    stack = [output_root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise PreflightError("study output tree walk failed") from exc
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
                logical += int(stat.st_size)
                allocated += int(stat.st_blocks) * 512
                if entry.is_symlink():
                    raise PreflightError("study output tree contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    file_count += 1
                else:
                    raise PreflightError("study output tree contains a special object")
            except PreflightError:
                raise
            except OSError as exc:
                raise PreflightError("study output tree stat failed") from exc
    return {
        "file_count": file_count,
        "logical_bytes": logical,
        "allocated_bytes": allocated,
    }


PUBLIC_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "source_role",
        "cache_root",
        "file_count",
        "retained_bytes",
        "file_inventory_sha256",
        "files",
    }
)
PUBLIC_MANIFEST_FILE_FIELDS = frozenset({"bytes", "path", "sha256"})


def load_legacy_public_artifact_manifest(
    path: Path = LEGACY_PUBLIC_ARTIFACT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Load and validate the prospective 45-file public-input allowlist."""

    manifest_path = Path(path)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PreflightError("public-artifact manifest is not a real file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("public-artifact manifest is unreadable") from exc
    if not isinstance(manifest, Mapping) or set(manifest) != PUBLIC_MANIFEST_FIELDS:
        raise PreflightError("public-artifact manifest schema differs")
    if (
        manifest["schema_version"] != SCHEMA_VERSION
        or manifest["source_role"] != "immutable_public_artifact_inputs_only"
        or manifest["cache_root"] != LEGACY_PUBLIC_ARTIFACT_ROOT
        or manifest["file_count"] != LEGACY_PUBLIC_ARTIFACT_FILE_COUNT
        or manifest["retained_bytes"] != LEGACY_PUBLIC_ARTIFACT_BYTES
        or manifest["file_inventory_sha256"]
        != LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
    ):
        raise PreflightError("public-artifact manifest binding differs")
    rows = manifest["files"]
    if not isinstance(rows, list) or len(rows) != LEGACY_PUBLIC_ARTIFACT_FILE_COUNT:
        raise PreflightError("public-artifact manifest file count differs")
    observed_paths: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != PUBLIC_MANIFEST_FILE_FIELDS:
            raise PreflightError("public-artifact manifest file schema differs")
        relative = row["path"]
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise PreflightError("public-artifact manifest path is malformed")
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or str(pure) != relative
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise PreflightError("public-artifact manifest path is unsafe")
        byte_count = row["bytes"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise PreflightError("public-artifact manifest byte count is invalid")
        digest = row["sha256"]
        if not isinstance(digest, str) or HEX64_RE.fullmatch(digest) is None:
            raise PreflightError("public-artifact manifest digest is malformed")
        observed_paths.append(relative)
    if observed_paths != sorted(observed_paths) or len(set(observed_paths)) != len(rows):
        raise PreflightError("public-artifact manifest paths are not unique/sorted")
    if sum(int(row["bytes"]) for row in rows) != LEGACY_PUBLIC_ARTIFACT_BYTES:
        raise PreflightError("public-artifact manifest retained bytes differ")
    if canonical_sha256(rows) != LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256:
        raise PreflightError("public-artifact manifest inventory hash differs")
    model_inventory = [
        {
            "path": str(row["path"])[len("model_snapshot/") :],
            "sha256": row["sha256"],
        }
        for row in rows
        if str(row["path"]).startswith("model_snapshot/")
    ]
    if canonical_sha256(model_inventory) != LEGACY_MODEL_FILE_INVENTORY_SHA256:
        raise PreflightError("pinned model inventory hash differs")
    by_path = {str(row["path"]): row for row in rows}
    pinned_files = {
        "sae/Llama-3.3-70B-Instruct-SAE-l50.pt": protocol.SAE_SPEC["sha256"],
        "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt": protocol.J_LENS_SPEC[
            "sha256"
        ],
    }
    if any(by_path.get(name, {}).get("sha256") != digest for name, digest in pinned_files.items()):
        raise PreflightError("pinned SAE/J-lens manifest digest differs")
    return dict(manifest)


def _hash_open_regular_file(path: Path, expected_size: int) -> str:
    """Hash one unchanged regular file while refusing symlink substitution."""

    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise PreflightError("public-artifact cache contains a non-regular file")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise PreflightError("public artifact changed before hashing")
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
    except PreflightError:
        raise
    except OSError as exc:
        raise PreflightError("public-artifact cache file could not be hashed") from exc
    stable_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    stable_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if stable_before != stable_after or after.st_size != expected_size:
        raise PreflightError("public artifact changed during hashing or has wrong size")
    return digest.hexdigest()


def rehash_artifact_tree(
    cache_root: Path, *, expected_files: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any], ...]:
    """Independently rehash an exact tree; useful for small fixture tests too."""

    root = Path(cache_root)
    try:
        if root.is_symlink() or not root.is_dir():
            raise PreflightError("public-artifact cache root is not a real directory")
    except OSError as exc:
        raise PreflightError("public-artifact cache root is unreadable") from exc
    expected = {str(row["path"]): dict(row) for row in expected_files}
    if len(expected) != len(expected_files):
        raise PreflightError("public-artifact expected path set is duplicated")
    observed_paths: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            raise PreflightError("public-artifact cache walk failed") from exc
        for entry in entries:
            relative = Path(entry.path).relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    raise PreflightError("public-artifact cache contains a symlink")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    observed_paths.append(relative)
                else:
                    raise PreflightError("public-artifact cache contains a special object")
            except OSError as exc:
                raise PreflightError("public-artifact cache walk failed") from exc
    if set(observed_paths) != set(expected) or len(observed_paths) != len(expected):
        raise PreflightError("public-artifact cache has missing or extra files")
    observed: list[dict[str, Any]] = []
    for relative in sorted(observed_paths):
        row = expected[relative]
        expected_size = row.get("bytes")
        expected_digest = row.get("sha256")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
            or not isinstance(expected_digest, str)
            or HEX64_RE.fullmatch(expected_digest) is None
        ):
            raise PreflightError("public-artifact expected inventory is malformed")
        digest = _hash_open_regular_file(root / relative, expected_size)
        if digest != expected_digest:
            raise PreflightError(f"public-artifact digest differs: {relative}")
        observed.append(
            {"bytes": expected_size, "path": relative, "sha256": digest}
        )
    return tuple(observed)


def rehash_legacy_public_artifact_cache(
    cache_root: Path = Path(LEGACY_PUBLIC_ARTIFACT_ROOT),
    *,
    manifest_path: Path = LEGACY_PUBLIC_ARTIFACT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Rehash the exact existing 156 GB public cache without copying it."""

    root = Path(cache_root)
    if root.as_posix() != LEGACY_PUBLIC_ARTIFACT_ROOT:
        raise PreflightError("only the exact legacy public-artifact root is admissible")
    manifest = load_legacy_public_artifact_manifest(manifest_path)
    observed = list(rehash_artifact_tree(root, expected_files=manifest["files"]))
    if (
        len(observed) != LEGACY_PUBLIC_ARTIFACT_FILE_COUNT
        or sum(int(row["bytes"]) for row in observed) != LEGACY_PUBLIC_ARTIFACT_BYTES
        or canonical_sha256(observed) != LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
    ):
        raise PreflightError("independent public-artifact rehash summary differs")
    model_rows = [
        {
            "path": str(row["path"])[len("model_snapshot/") :],
            "sha256": row["sha256"],
        }
        for row in observed
        if str(row["path"]).startswith("model_snapshot/")
    ]
    if canonical_sha256(model_rows) != LEGACY_MODEL_FILE_INVENTORY_SHA256:
        raise PreflightError("independently rehashed model inventory differs")
    by_path = {str(row["path"]): row for row in observed}
    model_bytes = sum(
        int(row["bytes"])
        for row in observed
        if str(row["path"]).startswith("model_snapshot/")
    )
    return {
        "cache_root": LEGACY_PUBLIC_ARTIFACT_ROOT,
        "full_file_count": len(observed),
        "full_retained_bytes": sum(int(row["bytes"]) for row in observed),
        "full_file_inventory_sha256": canonical_sha256(observed),
        "components": [
            {
                "component": "model",
                "revision": protocol.MODEL_SPEC["revision"],
                "relative_path": "model_snapshot",
                "byte_count": model_bytes,
                "sha256": LEGACY_MODEL_FILE_INVENTORY_SHA256,
                "verified": True,
            },
            {
                "component": "sae",
                "revision": protocol.SAE_SPEC["revision"],
                "relative_path": "sae/Llama-3.3-70B-Instruct-SAE-l50.pt",
                "byte_count": by_path[
                    "sae/Llama-3.3-70B-Instruct-SAE-l50.pt"
                ]["bytes"],
                "sha256": protocol.SAE_SPEC["sha256"],
                "verified": True,
            },
            {
                "component": "j_lens",
                "revision": protocol.J_LENS_SPEC["revision"],
                "relative_path": (
                    "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"
                ),
                "byte_count": by_path[
                    "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"
                ]["bytes"],
                "sha256": protocol.J_LENS_SPEC["sha256"],
                "verified": True,
            },
        ],
    }


CACHE_COMPONENTS = ("model", "sae", "j_lens")
CACHE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "study_id",
        "protocol_version",
        "guest_receipt_sha256",
        "cache_root",
        "cache_role",
        "read_only",
        "independently_rehashed",
        "full_file_count",
        "full_retained_bytes",
        "full_file_inventory_sha256",
        "components",
        "model_forward_count",
        "target_prompt_render_count",
        "prior_outcome_inputs",
        "receipt_sha256",
    }
)
CACHE_COMPONENT_FIELDS = frozenset(
    {"component", "revision", "relative_path", "byte_count", "sha256", "verified"}
)


def build_cache_receipt(
    *,
    guest_receipt: Mapping[str, Any],
    ownership_receipt: Mapping[str, Any],
    cache_root: Path = Path(LEGACY_PUBLIC_ARTIFACT_ROOT),
    manifest_path: Path = LEGACY_PUBLIC_ARTIFACT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Perform the complete rehash and issue the only admissible cache receipt."""

    guest = validate_guest_receipt(
        guest_receipt, ownership_receipt=ownership_receipt
    )
    rehash = rehash_legacy_public_artifact_cache(
        cache_root, manifest_path=manifest_path
    )
    core = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "guest_receipt_sha256": guest["receipt_sha256"],
        "cache_root": rehash["cache_root"],
        "cache_role": "immutable_public_artifacts_only",
        # The rehash path is opened only for reads; new raw/results use the
        # successor namespace and never mutate or duplicate this directory.
        "read_only": True,
        "independently_rehashed": True,
        "full_file_count": rehash["full_file_count"],
        "full_retained_bytes": rehash["full_retained_bytes"],
        "full_file_inventory_sha256": rehash["full_file_inventory_sha256"],
        "components": rehash["components"],
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
        "prior_outcome_inputs": [],
    }
    return with_self_hash(core)


def validate_cache_receipt(
    receipt: Mapping[str, Any],
    *,
    guest_receipt: Mapping[str, Any],
    ownership_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    guest = validate_guest_receipt(guest_receipt, ownership_receipt=ownership_receipt)
    if not isinstance(receipt, Mapping) or set(receipt) != CACHE_FIELDS:
        raise PreflightError("cache receipt schema differs")
    _self_hash(receipt, "cache")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["status"] != "pass"
        or receipt["study_id"] != protocol.STUDY_ID
        or receipt["protocol_version"] != protocol.PROTOCOL_VERSION
        or receipt["guest_receipt_sha256"] != guest["receipt_sha256"]
    ):
        raise PreflightError("cache receipt identity/binding differs")
    if (
        receipt["cache_root"] != LEGACY_PUBLIC_ARTIFACT_ROOT
        or receipt["cache_role"] != "immutable_public_artifacts_only"
        or receipt["read_only"] is not True
        or receipt["independently_rehashed"] is not True
        or receipt["full_file_count"] != LEGACY_PUBLIC_ARTIFACT_FILE_COUNT
        or receipt["full_retained_bytes"] != LEGACY_PUBLIC_ARTIFACT_BYTES
        or receipt["full_file_inventory_sha256"]
        != LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
    ):
        raise PreflightError("validation public-artifact cache binding differs")
    rows = receipt["components"]
    if not isinstance(rows, list) or tuple(row.get("component") for row in rows) != CACHE_COMPONENTS:
        raise PreflightError("artifact cache inventory/order differs")
    expected_revisions = {
        "model": protocol.MODEL_SPEC["revision"],
        "sae": protocol.SAE_SPEC["revision"],
        "j_lens": protocol.J_LENS_SPEC["revision"],
    }
    expected_hashes = {
        "model": LEGACY_MODEL_FILE_INVENTORY_SHA256,
        "sae": protocol.SAE_SPEC["sha256"],
        "j_lens": protocol.J_LENS_SPEC["sha256"],
    }
    expected_paths = {
        "model": "model_snapshot",
        "sae": "sae/Llama-3.3-70B-Instruct-SAE-l50.pt",
        "j_lens": "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt",
    }
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != CACHE_COMPONENT_FIELDS:
            raise PreflightError("artifact cache component schema differs")
        name = row["component"]
        relative = row["relative_path"]
        if (
            row["revision"] != expected_revisions[name]
            or row["verified"] is not True
            or isinstance(row["byte_count"], bool)
            or not isinstance(row["byte_count"], int)
            or row["byte_count"] <= 0
            or not isinstance(relative, str)
            or relative != expected_paths[name]
        ):
            raise PreflightError("artifact cache component differs")
        if not isinstance(row["sha256"], str) or HEX64_RE.fullmatch(row["sha256"]) is None:
            raise PreflightError("artifact cache component hash is malformed")
        if row["sha256"] != expected_hashes[name]:
            raise PreflightError("pinned artifact hash differs")
    if receipt["model_forward_count"] != 0 or receipt["target_prompt_render_count"] != 0:
        raise PreflightError("artifact cache gate ran after model/target access")
    if receipt["prior_outcome_inputs"] != []:
        raise PreflightError("artifact cache gate used a prior outcome")
    return dict(receipt)


@dataclass
class CumulativeMeter:
    """One budget clock spanning staging, Stage A, audit, and Stage B."""

    provider_created_at: datetime
    provider_terminate_after: datetime
    hourly_price_usd: float
    prior_elapsed_seconds: float = 0.0
    prior_spend_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.provider_created_at.tzinfo is None or self.provider_terminate_after.tzinfo is None:
            raise PreflightError("cumulative meter timestamps are timezone-naive")
        if self.provider_terminate_after - self.provider_created_at != timedelta(
            seconds=MAX_TOTAL_SECONDS
        ):
            raise PreflightError("cumulative meter deadline differs from provider kill")
        if not math.isfinite(self.hourly_price_usd) or self.hourly_price_usd <= 0:
            raise PreflightError("hourly price is invalid")
        if self.hourly_price_usd * MAX_TOTAL_SECONDS / 3600 > MAX_TOTAL_SPEND_USD:
            raise PreflightError("six-hour worst-case price exceeds $36")
        if (
            not math.isfinite(self.prior_elapsed_seconds)
            or not math.isfinite(self.prior_spend_usd)
            or self.prior_elapsed_seconds < 0
            or self.prior_spend_usd < 0
        ):
            raise PreflightError("prior cumulative usage is invalid")

    def check(
        self,
        *,
        observed_at: datetime,
        current_process_elapsed_seconds: float,
        seconds_since_progress: float,
    ) -> dict[str, float]:
        if observed_at.tzinfo is None:
            raise PreflightError("observed lifecycle clock is timezone-naive")
        if not math.isfinite(current_process_elapsed_seconds) or current_process_elapsed_seconds < 0:
            raise PreflightError("current elapsed time is invalid")
        if not math.isfinite(seconds_since_progress) or seconds_since_progress < 0:
            raise PreflightError("progress age is invalid")
        if seconds_since_progress >= MAX_NO_PROGRESS_SECONDS:
            raise PreflightError("no-progress watchdog expired")
        wall_elapsed = (
            observed_at.astimezone(timezone.utc)
            - self.provider_created_at.astimezone(timezone.utc)
        ).total_seconds()
        if wall_elapsed < 0:
            raise PreflightError("observed lifecycle clock predates pod creation")
        cumulative_elapsed = self.prior_elapsed_seconds + current_process_elapsed_seconds
        metered_spend = (
            self.prior_spend_usd
            + current_process_elapsed_seconds * self.hourly_price_usd / 3600
        )
        # RunPod bills while the pod exists, including staging/audit gaps.
        cumulative_spend = max(
            metered_spend, wall_elapsed * self.hourly_price_usd / 3600
        )
        if observed_at >= self.provider_terminate_after:
            raise PreflightError("provider terminateAfter reached")
        if wall_elapsed >= MAX_TOTAL_SECONDS or cumulative_elapsed >= MAX_TOTAL_SECONDS:
            raise PreflightError("cumulative six-hour ceiling reached")
        if cumulative_spend >= MAX_TOTAL_SPEND_USD:
            raise PreflightError("cumulative $36 ceiling reached")
        return {
            "provider_wall_elapsed_seconds": wall_elapsed,
            "cumulative_metered_seconds": cumulative_elapsed,
            "cumulative_estimated_spend_usd": cumulative_spend,
            "seconds_since_progress": seconds_since_progress,
        }


GUEST_RECEIPT_FILENAME = "GUEST_PREFLIGHT.json"
CACHE_RECEIPT_FILENAME = "CACHE_PREFLIGHT.json"
MAX_INPUT_RECEIPT_BYTES = 1024 * 1024


def _read_receipt_path(path: Path, label: str) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PreflightError(f"{label} receipt path is missing or unsafe")
    try:
        if candidate.stat().st_size > MAX_INPUT_RECEIPT_BYTES:
            raise PreflightError(f"{label} receipt is oversized")
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except PreflightError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{label} receipt is unreadable") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{label} receipt is not an object")
    return value


def _fresh_external_receipt_directory(path: Path) -> Path:
    candidate = Path(path)
    if candidate.name in {"", ".", ".."} or candidate.is_symlink() or candidate.exists():
        raise PreflightError("preflight receipt directory must be fresh")
    try:
        parent = candidate.parent.expanduser().resolve(strict=True)
    except OSError as exc:
        raise PreflightError("preflight receipt parent is missing") from exc
    resolved = parent / candidate.name
    forbidden_roots = (
        Path(VOLUME_MOUNT_PATH),
        Path(__file__).resolve().parents[2],
    )
    for forbidden in forbidden_roots:
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            continue
        raise PreflightError("preflight receipts must remain outside workspace/repository")
    try:
        resolved.mkdir(mode=0o700)
    except OSError as exc:
        raise PreflightError("preflight receipt directory could not be created") from exc
    return resolved


def _write_receipt_path(path: Path, receipt: Mapping[str, Any]) -> Path:
    payload = canonical_json_bytes(dict(receipt)) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise PreflightError("preflight receipt publication failed") from exc
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    guest = commands.add_parser("guest")
    guest.add_argument("--ownership-receipt", type=Path, required=True)
    guest.add_argument("--receipt-dir", type=Path, required=True)
    cache = commands.add_parser("cache")
    cache.add_argument("--ownership-receipt", type=Path, required=True)
    cache.add_argument("--guest-receipt", type=Path, required=True)
    cache.add_argument("--receipt-dir", type=Path, required=True)
    all_gates = commands.add_parser("all")
    all_gates.add_argument("--ownership-receipt", type=Path, required=True)
    all_gates.add_argument("--receipt-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build guest/cache receipts; the cache command always rehashes 45 files."""

    args = parse_args(argv)
    ownership = _read_receipt_path(args.ownership_receipt, "ownership")
    directory = _fresh_external_receipt_directory(args.receipt_dir)
    if args.command == "guest":
        guest = build_guest_receipt(ownership_receipt=ownership)
        output = _write_receipt_path(directory / GUEST_RECEIPT_FILENAME, guest)
        print(str(output))
        return 0
    if args.command == "cache":
        guest = _read_receipt_path(args.guest_receipt, "guest")
        cache = build_cache_receipt(
            guest_receipt=guest, ownership_receipt=ownership
        )
        output = _write_receipt_path(directory / CACHE_RECEIPT_FILENAME, cache)
        print(str(output))
        return 0
    guest = build_guest_receipt(ownership_receipt=ownership)
    guest_path = _write_receipt_path(directory / GUEST_RECEIPT_FILENAME, guest)
    cache = build_cache_receipt(
        guest_receipt=guest, ownership_receipt=ownership
    )
    cache_path = _write_receipt_path(directory / CACHE_RECEIPT_FILENAME, cache)
    print(str(guest_path))
    print(str(cache_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
