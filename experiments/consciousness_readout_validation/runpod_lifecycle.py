"""Budget-guarded RunPod lifecycle receipts for the readout-validation pilot.

Create and terminate are dry-run operations unless ``--execute`` is supplied.
The API credential is accepted only through ``RUNPOD_API_KEY``.  Receipts are
compact allowlisted records written outside the repository; raw provider
responses and credentials are never serialized.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import ssl
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from . import paths, protocol


REST_API_HOST = "rest.runpod.io"
REST_API_PREFIX = "/v1"
GRAPHQL_API_HOST = "api.runpod.io"
GRAPHQL_API_PATH = "/graphql"
API_KEY_ENV = "RUNPOD_API_KEY"
GPU_TYPE = "NVIDIA B200"
GPU_DISPLAY_NAME = "B200"
ON_DEMAND_MUTATION = "podFindAndDeployOnDemand"
ON_DEMAND_POD_TYPE = "RESERVED"
REST_CORROBORATION_PROOF_SOURCE = "rest_v1_pod_get_present_fields"
FINAL_REST_CORROBORATION_PROOF_SOURCE = (
    "rest_v1_pod_get_final_after_graphql_locked_state"
)
POD_NAME_PREFIX = "consciousness-readout-validation-v1-"
PORTS = ("22/tcp",)
VOLUME_MOUNT_PATH = "/workspace"
CONTAINER_DISK_GB = 50
MIN_NETWORK_VOLUME_GB = 200
RECEIPT_SCHEMA_VERSION = 1
POD_ID_RE = re.compile(r"^[a-z0-9]{6,32}$")
POD_NAME_RE = re.compile(
    rf"^{re.escape(POD_NAME_PREFIX)}[0-9]{{8}}-[0-9a-f]{{32}}$"
)
VOLUME_ID_RE = re.compile(r"^[a-z0-9]{6,32}$")
PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,128}$")
DATA_CENTER_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9-]{2,24}$")
DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?$")
RFC3339_UTC_SECONDS_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
SAFE_DIAGNOSTIC_TEXT_RE = re.compile(r"^[A-Za-z0-9 ._+:/()\-]{1,24}$")
CONTAINER_IMAGE_RE = re.compile(
    r"^(?:(?:docker\.io|index\.docker\.io)/)?"
    r"runpod/pytorch@(sha256:[0-9a-f]{64})$"
)
GRAPHQL_IDENTITY_DIAGNOSTIC_FIELDS = frozenset(
    {
        "name",
        "desired_status",
        "image",
        "locked",
        "container_disk_gb",
        "volume_mount_path",
        "gpu_type_id",
        "gpu_count",
        "data_center_id",
        "secure_cloud",
        "network_volume_id",
        "network_volume_data_center_id",
        "ports",
        "pod_type",
    }
)
GRAPHQL_IDENTITY_HASH_FIELDS = frozenset(
    {
        "name",
        "image",
        "data_center_id",
        "network_volume_id",
        "network_volume_data_center_id",
    }
)
REST_REQUIRED_TOP_LEVEL_FIELDS = (
    "desiredStatus",
    "containerDiskInGb",
    "volumeMountPath",
    "gpuCount",
    "ports",
    "costPerHr",
)
COMMON_SECRET_RE = re.compile(
    rb"(?i)(?:bearer\s+[a-z0-9._-]{12,}|hf_[a-z0-9]{16,}|rpa_[a-z0-9]{16,})"
)
GRAPHQL_CREATE_QUERY = """mutation createPod($input: PodFindAndDeployOnDemandInput!) {
  podFindAndDeployOnDemand(input: $input) {
    id
    name
    imageName
    desiredStatus
    costPerHr
    containerDiskInGb
    volumeInGb
    volumeMountPath
    gpuCount
    memoryInGb
    vcpuCount
    ports
    lastStatusChange
    lastStartedAt
    machineId
    networkVolumeId
    locked
    podType
    machine {
      id
      dataCenterId
      secureCloud
      gpuTypeId
      gpuDisplayName
      location
      podHostId
    }
    runtime {
      ports {
        ip
        isIpPublic
        privatePort
        publicPort
        type
      }
    }
  }
}"""
GRAPHQL_POD_READ_QUERY = """query pod($input: PodFilter) {
  pod(input: $input) {
    id
    name
    locked
    podType
    desiredStatus
  }
}"""

ApiCall = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]
GraphQLCall = Callable[[Mapping[str, Any]], tuple[int, Any]]


class LifecycleError(RuntimeError):
    """Raised when ownership, budget, identity, or deletion cannot be proven."""


class GraphQLCreateError(LifecycleError):
    """Sanitized GraphQL creation failure, optionally carrying a created pod ID."""

    def __init__(self, message: str, *, pod_id: str | None = None) -> None:
        super().__init__(message)
        self.pod_id = pod_id


class NameReconciliationError(LifecycleError):
    """Pre-create exact-name inventory failure with compact evidence."""

    def __init__(self, message: str, *, evidence: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.evidence = dict(evidence)


class ProviderSnapshotIncomplete(LifecycleError):
    """A successful REST response whose create-time metadata is still hydrating."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise LifecycleError("receipt UTC timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LifecycleError("receipt UTC timestamp is malformed") from exc
    return parsed.astimezone(timezone.utc)


def _provider_deadline(
    observed_now: Any, *, max_hours: Decimal
) -> tuple[datetime, datetime, str]:
    """Return a conservative whole-second start and exact RunPod deadline."""

    if (
        not isinstance(observed_now, datetime)
        or observed_now.tzinfo is None
        or observed_now.utcoffset() is None
    ):
        raise LifecycleError("lifecycle clock must be a timezone-aware datetime")
    observed_utc = observed_now.astimezone(timezone.utc)
    conservative_start = observed_utc.replace(microsecond=0)
    duration_seconds = max_hours * Decimal(3600)
    integral_seconds = duration_seconds.to_integral_value()
    if duration_seconds != integral_seconds or integral_seconds <= 0:
        raise LifecycleError(
            "max hours is not exactly representable at RunPod's RFC3339-second precision"
        )
    try:
        deadline = conservative_start + timedelta(seconds=int(integral_seconds))
        exact_authorized_ceiling = observed_utc + timedelta(
            seconds=int(integral_seconds)
        )
    except (OverflowError, ValueError) as exc:
        raise LifecycleError("authorized deadline is outside the datetime range") from exc
    if deadline <= observed_utc or deadline > exact_authorized_ceiling:
        raise LifecycleError("provider deadline is not conservatively authorization-bounded")
    deadline_text = deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
    if (
        RFC3339_UTC_SECONDS_RE.fullmatch(deadline_text) is None
        or _parse_utc(deadline_text) != deadline
    ):
        raise LifecycleError("provider deadline is not exact RFC3339 UTC")
    return conservative_start, deadline, deadline_text


def _decimal(text: str, label: str) -> Decimal:
    if not DECIMAL_RE.fullmatch(text):
        raise LifecycleError(f"{label} must be an exact positive decimal literal")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - regex already narrows
        raise LifecycleError(f"{label} is invalid") from exc
    if not value.is_finite() or value <= 0:
        raise LifecycleError(f"{label} must be positive")
    return value


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _reject_secret_bytes(payload: bytes, *, api_key: str = "") -> None:
    if api_key and api_key.encode("utf-8") in payload:
        raise LifecycleError("API credential appeared in arguments or receipt bytes")
    if COMMON_SECRET_RE.search(payload):
        raise LifecycleError("credential-shaped material appeared in arguments or receipt bytes")


def reject_secret_argv(argv: Sequence[str], *, api_key: str = "") -> None:
    _reject_secret_bytes("\0".join(argv).encode("utf-8"), api_key=api_key)
    if any("api-key" in item.lower() or "authorization:" in item.lower() for item in argv):
        raise LifecycleError("API credentials may not be supplied on the command line")


def _sealed(kind: str, core: Mapping[str, Any], *, api_key: str = "") -> dict[str, Any]:
    value = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_kind": kind,
        "study_id": protocol.STUDY_ID,
        **dict(core),
    }
    _reject_secret_bytes(protocol.canonical_json_bytes(value), api_key=api_key)
    value["receipt_sha256"] = protocol.canonical_sha256(value)
    return value


def _write_receipt(path: Path, value: Mapping[str, Any], *, api_key: str = "") -> Path:
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    _reject_secret_bytes(payload, api_key=api_key)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path


def _external_directory(path: Path, *, fresh: bool) -> Path:
    if path.is_symlink():
        raise LifecycleError("lifecycle receipt directory may not be a symlink")
    parent = path.expanduser().parent.resolve(strict=True)
    if not parent.is_dir() or path.expanduser().parent.is_symlink():
        raise LifecycleError("lifecycle receipt parent is unsafe")
    repo = paths.REPO_ROOT.resolve(strict=True)
    try:
        parent.relative_to(repo)
    except ValueError:
        pass
    else:
        raise LifecycleError("lifecycle receipts must remain outside the repository")
    candidate = parent / path.name
    if fresh:
        if candidate.exists() or candidate.is_symlink():
            raise LifecycleError("lifecycle receipt directory must be fresh")
        candidate.mkdir(mode=0o700)
    elif candidate.is_symlink() or not candidate.is_dir():
        raise LifecycleError("lifecycle receipt directory is missing or unsafe")
    return candidate.resolve(strict=True)


def _load_ownership(path: Path, *, api_key: str = "") -> tuple[Path, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise LifecycleError("ownership receipt is missing or unsafe")
    directory = _external_directory(path.parent, fresh=False)
    resolved = path.resolve(strict=True)
    if resolved.parent != directory or resolved.name != "OWNERSHIP.json":
        raise LifecycleError("ownership receipt path is not canonical")
    raw = resolved.read_bytes()
    _reject_secret_bytes(raw, api_key=api_key)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LifecycleError("ownership receipt is invalid JSON") from exc
    if not isinstance(value, dict):
        raise LifecycleError("ownership receipt is malformed")
    if raw != protocol.canonical_json_bytes(value) + b"\n":
        raise LifecycleError("ownership receipt is not exact canonical JSON")
    observed_hash = value.pop("receipt_sha256", None)
    if observed_hash != protocol.canonical_sha256(value):
        raise LifecycleError("ownership receipt self-hash differs")
    value["receipt_sha256"] = observed_hash
    required = {
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
    if set(value) != required:
        raise LifecycleError("ownership receipt fields differ")
    if (
        value["schema_version"] != RECEIPT_SCHEMA_VERSION
        or value["receipt_kind"] != "runpod_pod_ownership_v1"
        or value["study_id"] != protocol.STUDY_ID
        or value["status"] != "created"
        or value["agent_owned"] is not True
        or value["other_pods_mutated"] is not False
    ):
        raise LifecycleError("ownership receipt identity differs")
    created = _parse_utc(value["created_at_utc"])
    deadline = _parse_utc(value["hard_deadline_utc"])
    provider_deadline_text = value["provider_terminate_after_utc"]
    if (
        not isinstance(provider_deadline_text, str)
        or RFC3339_UTC_SECONDS_RE.fullmatch(provider_deadline_text) is None
        or provider_deadline_text != value["hard_deadline_utc"]
        or _parse_utc(provider_deadline_text) != deadline
        or created.microsecond != 0
        or deadline.microsecond != 0
    ):
        raise LifecycleError("provider termination deadline binding differs")
    max_usd, max_hours = _validate_authorization(value["authorization"])
    expected_duration_us = int(max_hours * Decimal(3_600_000_000))
    observed_duration = deadline - created
    observed_duration_us = (
        observed_duration.days * 86_400_000_000
        + observed_duration.seconds * 1_000_000
        + observed_duration.microseconds
    )
    if observed_duration_us != expected_duration_us:
        raise LifecycleError("ownership deadline differs from the exact hours authorization")
    if not isinstance(value["request_sha256"], str) or re.fullmatch(
        r"[0-9a-f]{64}", value["request_sha256"]
    ) is None:
        raise LifecycleError("ownership request hash is malformed")
    snapshot = _validate_owned_snapshot(value["pod"], expected=None)
    _validate_stored_graphql_locked_state_proof(
        value["graphql_locked_state_proof"], expected=snapshot
    )
    _validate_stored_rest_corroboration(
        value["rest_corroboration"], expected=snapshot
    )
    if _provider_cost(snapshot["cost_per_hour_usd"]) * max_hours > max_usd:
        raise LifecycleError("owned pod price exceeds its recorded authorization")
    return directory, value


def _validate_authorization(value: Any) -> tuple[Decimal, Decimal]:
    if not isinstance(value, Mapping) or set(value) != {"max_usd", "max_hours"}:
        raise LifecycleError("budget authorization is malformed")
    return _decimal(str(value["max_usd"]), "max USD"), _decimal(
        str(value["max_hours"]), "max hours"
    )


def build_create_request(
    *,
    pod_name: str,
    volume_id: str,
    data_center_id: str,
    terminate_after_utc: str,
) -> dict[str, Any]:
    if not POD_NAME_RE.fullmatch(pod_name):
        raise LifecycleError("pod name is not a unique pilot name")
    if not VOLUME_ID_RE.fullmatch(volume_id):
        raise LifecycleError("network volume ID is invalid")
    if not DATA_CENTER_RE.fullmatch(data_center_id):
        raise LifecycleError("data center ID is invalid")
    if (
        not isinstance(terminate_after_utc, str)
        or RFC3339_UTC_SECONDS_RE.fullmatch(terminate_after_utc) is None
        or _parse_utc(terminate_after_utc).microsecond != 0
    ):
        raise LifecycleError("provider termination deadline is not RFC3339 UTC seconds")
    graphql_input = {
        "cloudType": "SECURE",
        "containerDiskInGb": CONTAINER_DISK_GB,
        "dataCenterId": data_center_id,
        "gpuCount": 1,
        "gpuTypeId": GPU_TYPE,
        "imageName": protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        "name": pod_name,
        "networkVolumeId": volume_id,
        "ports": ",".join(PORTS),
        "startSsh": True,
        "terminateAfter": terminate_after_utc,
        "volumeMountPath": VOLUME_MOUNT_PATH,
    }
    return {
        "query": GRAPHQL_CREATE_QUERY,
        "variables": {"input": graphql_input},
    }


def _provider_cost(value: Any) -> Decimal:
    try:
        cost = Decimal(str(value))
    except InvalidOperation as exc:
        raise LifecycleError("provider hourly cost is malformed") from exc
    if not cost.is_finite() or cost <= 0:
        raise LifecycleError("provider hourly cost is malformed")
    return cost


def _quantity_text(value: Any, label: str, *, positive: bool) -> str:
    try:
        quantity = Decimal(str(value))
    except InvalidOperation as exc:
        raise LifecycleError(f"provider {label} is malformed") from exc
    if not quantity.is_finite() or quantity < 0 or (positive and quantity <= 0):
        raise LifecycleError(f"provider {label} is malformed")
    normalized = quantity.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _provider_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LifecycleError(f"provider {label} is malformed")
    return value


def _provider_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or PROVIDER_ID_RE.fullmatch(value) is None:
        raise LifecycleError(f"provider {label} is malformed")
    return value


def _diagnostic_sha256(value: Any) -> str:
    try:
        payload = protocol.canonical_json_bytes(value)
    except (TypeError, ValueError):
        payload = f"unencodable:{type(value).__name__}".encode("ascii")
    return protocol.sha256_bytes(payload)


def _diagnostic_digest(value: Any) -> str:
    return _diagnostic_sha256(value)[:16]


def _diagnostic_value_sha256(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return protocol.sha256_bytes(value.encode("utf-8"))
    return _diagnostic_sha256(value)


def _canonical_container_image(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = CONTAINER_IMAGE_RE.fullmatch(value)
    if match is None or match.group(1) != protocol.CONTAINER_IMAGE_SPEC["manifest_digest"]:
        return None
    return f"runpod/pytorch@{match.group(1)}"


def _bounded_diagnostic_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and SAFE_DIAGNOSTIC_TEXT_RE.fullmatch(value):
        return value
    return f"sha256:{_diagnostic_digest(value)}"


def _safe_graphql_observed(field: str, value: Any) -> str:
    if field not in GRAPHQL_IDENTITY_DIAGNOSTIC_FIELDS:
        raise LifecycleError("internal GraphQL diagnostic field is not allowlisted")
    if value is None:
        return "null"
    if field in GRAPHQL_IDENTITY_HASH_FIELDS:
        return f"sha256:{_diagnostic_digest(value)}"
    if isinstance(value, bool) or (isinstance(value, int) and not isinstance(value, bool)):
        return json.dumps(value, separators=(",", ":"))
    if field == "ports" and isinstance(value, list):
        if (
            len(value) <= 4
            and all(
                isinstance(item, str)
                and re.fullmatch(r"[0-9]{1,5}/(?:tcp|udp|http)", item)
                for item in value
            )
        ):
            return json.dumps(value, separators=(",", ":"))
        return f"sha256:{_diagnostic_digest(value)}"
    if isinstance(value, str) and SAFE_DIAGNOSTIC_TEXT_RE.fullmatch(value):
        return json.dumps(value, separators=(",", ":"))
    return f"sha256:{_diagnostic_digest(value)}"


def _graphql_identity_mismatch_summary(mismatches: Sequence[tuple[str, Any]]) -> str:
    selected = list(mismatches[:3])
    parts = [
        f"{field}={_safe_graphql_observed(field, observed)}"
        for field, observed in selected
    ]
    if len(mismatches) > len(selected):
        parts.append(f"additional_mismatch_count={len(mismatches) - len(selected)}")
    summary = f"GraphQL identity mismatch: {'; '.join(parts)}"
    if len(summary) > 240:
        raise LifecycleError("internal GraphQL diagnostic exceeded its size bound")
    return summary


def _normalize_ports(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        ports = [] if not value else [item.strip() for item in value.split(",")]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        ports = list(value)
    else:
        raise LifecycleError(f"provider {label} is malformed")
    if any(not item or len(item) > 64 for item in ports):
        raise LifecycleError(f"provider {label} is malformed")
    return ports


def _compact_runtime_port_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {"row_count": 0, "public_ssh_endpoint_present": False}
    if not isinstance(value, Mapping) or set(value) != {"ports"}:
        raise LifecycleError("GraphQL runtime metadata is malformed")
    rows = value.get("ports")
    if rows is None:
        return {"row_count": 0, "public_ssh_endpoint_present": False}
    if not isinstance(rows, list):
        raise LifecycleError("GraphQL runtime port metadata is malformed")
    public_ssh_endpoint_present = False
    required = {"ip", "isIpPublic", "privatePort", "publicPort", "type"}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != required:
            raise LifecycleError("GraphQL runtime port metadata is malformed")
        ip = row.get("ip")
        port_type = row.get("type")
        public_port = row.get("publicPort")
        if ip is not None and (not isinstance(ip, str) or len(ip) > 128):
            raise LifecycleError("GraphQL runtime port IP is malformed")
        if not isinstance(row.get("isIpPublic"), bool):
            raise LifecycleError("GraphQL runtime port visibility is malformed")
        private_port = _provider_int(row.get("privatePort"), "private port", minimum=1)
        if public_port is not None:
            public_port = _provider_int(public_port, "public port", minimum=1)
        if not isinstance(port_type, str) or not port_type or len(port_type) > 16:
            raise LifecycleError("GraphQL runtime port type is malformed")
        public_ssh_endpoint_present = public_ssh_endpoint_present or (
            row["isIpPublic"] is True
            and private_port == 22
            and public_port is not None
            and port_type.lower() == "tcp"
        )
    return {
        "row_count": len(rows),
        "public_ssh_endpoint_present": public_ssh_endpoint_present,
    }


def _compact_network_volume(
    value: Any, *, expected_id: str, expected_data_center_id: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LifecycleError("network-volume response is malformed")
    required = {"id", "name", "size", "dataCenterId"}
    if not required.issubset(value):
        raise LifecycleError("network-volume response fields are incomplete")
    name = value.get("name")
    if not isinstance(name, str) or not name or len(name) > 256:
        raise LifecycleError("network-volume name is malformed")
    size = _provider_int(
        value.get("size"), "network-volume size", minimum=MIN_NETWORK_VOLUME_GB
    )
    if value.get("id") != expected_id or value.get("dataCenterId") != expected_data_center_id:
        raise LifecycleError("network-volume identity or data center differs")
    return {
        "id": expected_id,
        "name_sha256": _diagnostic_value_sha256(name),
        "size_gb": size,
        "data_center_id": expected_data_center_id,
        "proof_source": "rest_v1_networkvolume_get",
    }


def _compact_graphql_created_pod(
    value: Any,
    *,
    expected_name: str,
    expected_volume_id: str,
    expected_data_center_id: str,
    network_volume: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LifecycleError("GraphQL created pod is malformed")
    required = {
        "id",
        "name",
        "imageName",
        "desiredStatus",
        "costPerHr",
        "containerDiskInGb",
        "volumeInGb",
        "volumeMountPath",
        "gpuCount",
        "memoryInGb",
        "vcpuCount",
        "ports",
        "lastStatusChange",
        "lastStartedAt",
        "machineId",
        "networkVolumeId",
        "locked",
        "podType",
        "machine",
        "runtime",
    }
    if set(value) != required:
        raise LifecycleError("GraphQL created-pod fields differ from the fixed selection")
    machine = value.get("machine")
    machine_fields = {
        "id",
        "dataCenterId",
        "secureCloud",
        "gpuTypeId",
        "gpuDisplayName",
        "location",
        "podHostId",
    }
    if not isinstance(machine, Mapping) or set(machine) != machine_fields:
        raise LifecycleError("GraphQL machine fields differ from the fixed selection")
    pod_id = _provider_id(value.get("id"), "pod ID")
    machine_id_sha256 = _diagnostic_value_sha256(value.get("machineId"))
    machine_record_id_sha256 = _diagnostic_value_sha256(machine.get("id"))
    pod_host_id_sha256 = _diagnostic_value_sha256(machine.get("podHostId"))
    location = machine.get("location")
    if not isinstance(location, str) or not location or len(location) > 256:
        raise LifecycleError("GraphQL machine location is malformed")
    pod_type = value.get("podType")
    ports = _normalize_ports(value.get("ports"), "GraphQL ports")
    raw_image = value.get("imageName")
    raw_locked = value.get("locked")
    canonical_image = _canonical_container_image(raw_image)
    snapshot = {
        "identity_source": "graphql_create_plus_rest_volume_proof",
        "on_demand_mutation": ON_DEMAND_MUTATION,
        "id": pod_id,
        "name": value.get("name"),
        "desired_status": value.get("desiredStatus"),
        "image": canonical_image,
        # GraphQL may leave this nullable during creation.  The owned
        # canonical state remains false and REST must prove it before publish.
        "locked": False,
        "pod_type": pod_type,
        "container_disk_gb": _provider_int(
            value.get("containerDiskInGb"), "container disk", minimum=1
        ),
        "volume_gb": _quantity_text(value.get("volumeInGb"), "volume size", positive=False),
        "volume_mount_path": value.get("volumeMountPath"),
        "gpu_type_id_requested": GPU_TYPE,
        "gpu_type_id": machine.get("gpuTypeId"),
        "gpu_display_name": _bounded_diagnostic_text(machine.get("gpuDisplayName")),
        "gpu_count": _provider_int(value.get("gpuCount"), "GPU count", minimum=1),
        "memory_gb": _quantity_text(value.get("memoryInGb"), "memory", positive=True),
        "vcpu_count": _quantity_text(value.get("vcpuCount"), "vCPU count", positive=True),
        "machine_id_sha256": machine_id_sha256,
        "machine_record_id_sha256": machine_record_id_sha256,
        "pod_host_id_sha256": pod_host_id_sha256,
        "machine_location_sha256": _diagnostic_value_sha256(location),
        "data_center_id": machine.get("dataCenterId"),
        "secure_cloud": machine.get("secureCloud"),
        "network_volume_id": value.get("networkVolumeId"),
        "network_volume_data_center_id": network_volume.get("data_center_id"),
        "network_volume_name_sha256": network_volume.get("name_sha256"),
        "network_volume_size_gb": network_volume.get("size_gb"),
        "network_volume_proof_source": network_volume.get("proof_source"),
        "ports": ports,
        "runtime_port_summary": _compact_runtime_port_summary(value.get("runtime")),
        "cost_per_hour_usd": _decimal_text(_provider_cost(value.get("costPerHr"))),
        "last_status_change_present": value.get("lastStatusChange") is not None,
        "last_started_at_present": value.get("lastStartedAt") is not None,
    }
    checks = (
        ("name", snapshot["name"], expected_name),
        ("desired_status", snapshot["desired_status"], frozenset({"CREATED", "RUNNING"})),
        ("image", raw_image, protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]),
        ("locked", raw_locked, frozenset({None, False})),
        ("container_disk_gb", snapshot["container_disk_gb"], CONTAINER_DISK_GB),
        ("volume_mount_path", snapshot["volume_mount_path"], VOLUME_MOUNT_PATH),
        ("gpu_type_id", snapshot["gpu_type_id"], GPU_TYPE),
        ("gpu_count", snapshot["gpu_count"], 1),
        ("data_center_id", snapshot["data_center_id"], expected_data_center_id),
        ("secure_cloud", snapshot["secure_cloud"], True),
        ("network_volume_id", snapshot["network_volume_id"], expected_volume_id),
        (
            "network_volume_data_center_id",
            snapshot["network_volume_data_center_id"],
            expected_data_center_id,
        ),
        ("ports", snapshot["ports"], list(PORTS)),
        ("pod_type", snapshot["pod_type"], ON_DEMAND_POD_TYPE),
    )
    mismatches = []
    for field, observed, expected in checks:
        if field == "desired_status":
            matches = isinstance(observed, str) and observed in expected
        elif field == "locked":
            matches = observed is None or observed is False
        elif field == "image":
            matches = canonical_image == expected
        else:
            matches = observed == expected
        if not matches:
            mismatches.append((field, observed))
    if mismatches:
        raise LifecycleError(_graphql_identity_mismatch_summary(mismatches))
    return _validate_owned_snapshot(snapshot, expected=None)


def _validate_owned_snapshot(
    snapshot: Any, *, expected: Mapping[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping):
        raise LifecycleError("pod snapshot is malformed")
    required = {
        "identity_source",
        "on_demand_mutation",
        "id",
        "name",
        "desired_status",
        "image",
        "locked",
        "pod_type",
        "container_disk_gb",
        "volume_gb",
        "volume_mount_path",
        "gpu_type_id_requested",
        "gpu_type_id",
        "gpu_display_name",
        "gpu_count",
        "memory_gb",
        "vcpu_count",
        "machine_id_sha256",
        "machine_record_id_sha256",
        "pod_host_id_sha256",
        "machine_location_sha256",
        "data_center_id",
        "secure_cloud",
        "network_volume_id",
        "network_volume_data_center_id",
        "network_volume_name_sha256",
        "network_volume_size_gb",
        "network_volume_proof_source",
        "ports",
        "runtime_port_summary",
        "cost_per_hour_usd",
        "last_status_change_present",
        "last_started_at_present",
    }
    if set(snapshot) != required or not POD_ID_RE.fullmatch(str(snapshot["id"])):
        raise LifecycleError("pod snapshot fields or ID differ")
    if (
        snapshot["identity_source"] != "graphql_create_plus_rest_volume_proof"
        or snapshot["on_demand_mutation"] != ON_DEMAND_MUTATION
        or not POD_NAME_RE.fullmatch(str(snapshot["name"]))
        or not isinstance(snapshot["desired_status"], str)
        or snapshot["desired_status"] not in {"CREATED", "RUNNING"}
        or snapshot["image"] != protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]
        or snapshot["locked"] is not False
        or snapshot["pod_type"] != ON_DEMAND_POD_TYPE
        or snapshot["container_disk_gb"] != CONTAINER_DISK_GB
        or snapshot["volume_mount_path"] != VOLUME_MOUNT_PATH
        or snapshot["gpu_type_id_requested"] != GPU_TYPE
        or snapshot["gpu_type_id"] != GPU_TYPE
        or snapshot["gpu_count"] != 1
        or snapshot["secure_cloud"] is not True
        or snapshot["ports"] != list(PORTS)
        or snapshot["data_center_id"] != snapshot["network_volume_data_center_id"]
        or not VOLUME_ID_RE.fullmatch(str(snapshot["network_volume_id"]))
        or not DATA_CENTER_RE.fullmatch(str(snapshot["data_center_id"]))
        or snapshot["network_volume_proof_source"] != "rest_v1_networkvolume_get"
        or isinstance(snapshot["network_volume_size_gb"], bool)
        or not isinstance(snapshot["network_volume_size_gb"], int)
        or snapshot["network_volume_size_gb"] < MIN_NETWORK_VOLUME_GB
        or not isinstance(snapshot["last_status_change_present"], bool)
        or not isinstance(snapshot["last_started_at_present"], bool)
    ):
        raise LifecycleError("provider pod identity differs from the bound pilot request")
    if (
        (
            snapshot["machine_id_sha256"] is not None
            and (
                not isinstance(snapshot["machine_id_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", snapshot["machine_id_sha256"])
                is None
            )
        )
        or (
            snapshot["machine_record_id_sha256"] is not None
            and (
                not isinstance(snapshot["machine_record_id_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", snapshot["machine_record_id_sha256"])
                is None
            )
        )
        or (
            snapshot["gpu_display_name"] is not None
            and (
                not isinstance(snapshot["gpu_display_name"], str)
                or SAFE_DIAGNOSTIC_TEXT_RE.fullmatch(snapshot["gpu_display_name"])
                is None
            )
        )
        or any(
            item is not None
            and (
                not isinstance(item, str)
                or re.fullmatch(r"[0-9a-f]{64}", item) is None
            )
            for item in (
                snapshot["pod_host_id_sha256"],
                snapshot["machine_location_sha256"],
                snapshot["network_volume_name_sha256"],
            )
        )
    ):
        raise LifecycleError("provider diagnostic metadata is malformed")
    runtime_summary = snapshot["runtime_port_summary"]
    if (
        not isinstance(runtime_summary, Mapping)
        or set(runtime_summary) != {"row_count", "public_ssh_endpoint_present"}
        or isinstance(runtime_summary.get("row_count"), bool)
        or not isinstance(runtime_summary.get("row_count"), int)
        or runtime_summary["row_count"] < 0
        or not isinstance(runtime_summary.get("public_ssh_endpoint_present"), bool)
    ):
        raise LifecycleError("provider runtime-port summary is malformed")
    _quantity_text(snapshot["volume_gb"], "volume size", positive=False)
    _quantity_text(snapshot["memory_gb"], "memory", positive=True)
    _quantity_text(snapshot["vcpu_count"], "vCPU count", positive=True)
    _provider_cost(snapshot["cost_per_hour_usd"])
    if expected is not None and dict(snapshot) != dict(expected):
        raise LifecycleError("pod snapshot differs")
    return dict(snapshot)


def _require_rest_cleanup_authority(
    value: Any, *, expected: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Authorize cleanup from only the mutation ID and exact nonce name."""

    if not isinstance(value, Mapping):
        raise LifecycleError("REST pod readback is malformed")
    if value.get("id") != expected["id"] or value.get("name") != expected["name"]:
        raise LifecycleError("REST pod ID or exact nonce name differs")
    return value


def _build_graphql_pod_read_request(pod_id: str) -> dict[str, Any]:
    if POD_ID_RE.fullmatch(pod_id) is None:
        raise LifecycleError("GraphQL pod-read ID is malformed")
    return {
        "query": GRAPHQL_POD_READ_QUERY,
        "variables": {"input": {"podId": pod_id}},
    }


def _compact_graphql_locked_state_proof(
    status: Any,
    value: Any,
    *,
    expected_id: str,
    expected_name: str,
    request_sha256: str,
    poll_attempts: int,
) -> dict[str, Any]:
    if isinstance(status, bool) or not isinstance(status, int):
        raise LifecycleError("GraphQL pod read returned a malformed HTTP status")
    if status != 200:
        raise LifecycleError(f"GraphQL pod read returned HTTP {status}")
    if not isinstance(value, Mapping):
        raise LifecycleError("GraphQL pod read response is malformed")
    errors = value.get("errors")
    if errors not in (None, []):
        raise LifecycleError("GraphQL pod read returned an error")
    data = value.get("data")
    if not isinstance(data, Mapping) or "pod" not in data:
        raise LifecycleError("GraphQL pod read data is malformed")
    pod = data.get("pod")
    if pod is None:
        raise ProviderSnapshotIncomplete("GraphQL pod read has not exposed the pod")
    required = {"id", "name", "locked", "podType", "desiredStatus"}
    if not isinstance(pod, Mapping) or set(pod) != required:
        raise LifecycleError("GraphQL pod read fields differ from the fixed selection")
    if pod.get("id") != expected_id or pod.get("name") != expected_name:
        raise LifecycleError("GraphQL pod read ID or exact nonce name differs")
    pod_type = pod.get("podType")
    desired_status = pod.get("desiredStatus")
    locked = pod.get("locked")
    if pod_type is not None and pod_type != ON_DEMAND_POD_TYPE:
        raise LifecycleError("GraphQL pod read pod type is not RESERVED")
    if desired_status not in (None, "CREATED", "RUNNING"):
        raise LifecycleError("GraphQL pod read state is not RUNNING")
    if locked is not None and locked is not False:
        raise LifecycleError("GraphQL pod read did not prove locked=false")
    if pod_type is None or desired_status in (None, "CREATED") or locked is None:
        raise ProviderSnapshotIncomplete("GraphQL pod read remains transient")
    return {
        "proof_source": "graphql_pod_filter_locked_state",
        "request_sha256": request_sha256,
        "http_status": 200,
        "id": expected_id,
        "name": expected_name,
        "locked": False,
        "pod_type": ON_DEMAND_POD_TYPE,
        "desired_status": "RUNNING",
        "poll_attempts": poll_attempts,
    }


def _validate_stored_graphql_locked_state_proof(
    value: Any, *, expected: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "proof_source",
        "request_sha256",
        "http_status",
        "id",
        "name",
        "locked",
        "pod_type",
        "desired_status",
        "poll_attempts",
    }:
        raise LifecycleError("stored GraphQL locked-state proof fields differ")
    expected_request = _build_graphql_pod_read_request(str(expected["id"]))
    if (
        value.get("proof_source") != "graphql_pod_filter_locked_state"
        or value.get("request_sha256")
        != protocol.canonical_sha256(expected_request)
        or value.get("http_status") != 200
        or value.get("id") != expected["id"]
        or value.get("name") != expected["name"]
        or value.get("locked") is not False
        or value.get("pod_type") != ON_DEMAND_POD_TYPE
        or value.get("desired_status") != "RUNNING"
        or isinstance(value.get("poll_attempts"), bool)
        or not isinstance(value.get("poll_attempts"), int)
        or value.get("poll_attempts") < 1
        or value.get("poll_attempts") > 60
    ):
        raise LifecycleError("stored GraphQL locked-state proof differs")
    return dict(value)


def _compact_rest_corroboration(
    value: Any,
    *,
    expected: Mapping[str, Any],
    require_cost_equal: bool = True,
    require_state_equal: bool = True,
    proof_source: str = REST_CORROBORATION_PROOF_SOURCE,
) -> dict[str, Any]:
    """Check every present REST configuration field; tolerate absent hydration."""

    if proof_source not in {
        REST_CORROBORATION_PROOF_SOURCE,
        FINAL_REST_CORROBORATION_PROOF_SOURCE,
    }:
        raise LifecycleError("REST corroboration proof source is invalid")

    pod = _require_rest_cleanup_authority(value, expected=expected)
    missing = [
        field
        for field in REST_REQUIRED_TOP_LEVEL_FIELDS
        if field not in pod or pod.get(field) is None
    ]
    if not any(pod.get(field) is not None for field in ("imageName", "image")):
        missing.append("imageName|image")
    if missing:
        raise ProviderSnapshotIncomplete(
            "REST reliable top-level corroboration remains incomplete; "
            f"missing={','.join(missing)}"
        )
    observed_fields: list[str] = []

    def compare(
        provider_key: str,
        expected_key: str,
        *,
        source: Mapping[str, Any] = pod,
        normalize: Callable[[Any], Any] | None = None,
        label: str | None = None,
    ) -> None:
        if provider_key not in source or source.get(provider_key) is None:
            return
        observed_fields.append(label or provider_key)
        observed = source.get(provider_key)
        if normalize is not None:
            observed = normalize(observed)
        if observed != expected[expected_key]:
            raise LifecycleError(
                f"REST corroboration differs at {label or provider_key}"
            )

    for image_key in ("imageName", "image"):
        compare(image_key, "image", normalize=_canonical_container_image)
    compare("containerDiskInGb", "container_disk_gb")
    compare(
        "volumeInGb",
        "volume_gb",
        normalize=lambda item: _quantity_text(item, "REST volume size", positive=False),
    )
    compare("volumeMountPath", "volume_mount_path")
    compare("gpuCount", "gpu_count")
    compare(
        "memoryInGb",
        "memory_gb",
        normalize=lambda item: _quantity_text(item, "REST memory", positive=True),
    )
    compare(
        "vcpuCount",
        "vcpu_count",
        normalize=lambda item: _quantity_text(item, "REST vCPU count", positive=True),
    )
    compare("ports", "ports", normalize=lambda item: _normalize_ports(item, "REST ports"))
    compare("networkVolumeId", "network_volume_id")
    compare("gpuTypeId", "gpu_type_id")
    compare("dataCenterId", "data_center_id")
    compare("secureCloud", "secure_cloud")
    compare("podType", "pod_type")
    if pod.get("cloudType") is not None:
        observed_fields.append("cloudType")
        if pod.get("cloudType") != "SECURE":
            raise LifecycleError("REST corroboration cloud type differs")
    optional_false_field_status: dict[str, str] = {}
    for optional_field in ("interruptible", "locked"):
        if optional_field not in pod:
            optional_false_field_status[optional_field] = "absent"
            continue
        observed_fields.append(optional_field)
        optional_value = pod.get(optional_field)
        if optional_value is None:
            optional_false_field_status[optional_field] = "observed_null"
            continue
        if optional_value is not False:
            if optional_field == "interruptible":
                raise LifecycleError("REST corroboration is interruptible")
            raise LifecycleError("REST corroboration locked state differs")
        optional_false_field_status[optional_field] = "observed_false"
    if pod.get("machineId") is not None:
        observed_fields.append("machineId")
        _diagnostic_value_sha256(pod.get("machineId"))

    nested_specs = (
        (
            "machine",
            {
                "dataCenterId": "data_center_id",
                "secureCloud": "secure_cloud",
                "gpuTypeId": "gpu_type_id",
            },
        ),
        (
            "networkVolume",
            {
                "id": "network_volume_id",
                "dataCenterId": "network_volume_data_center_id",
            },
        ),
        ("gpu", {"count": "gpu_count"}),
    )
    for parent, fields in nested_specs:
        nested = pod.get(parent)
        if nested is None:
            continue
        if not isinstance(nested, Mapping):
            raise LifecycleError(f"REST corroboration {parent} is malformed")
        if parent == "machine" and nested.get("id") is not None:
            observed_fields.append("machine.id")
            _diagnostic_value_sha256(nested.get("id"))
        if parent == "machine" and nested.get("location") is not None:
            observed_fields.append("machine.location")
            _diagnostic_value_sha256(nested.get("location"))
        if parent == "machine" and nested.get("podHostId") is not None:
            observed_fields.append("machine.podHostId")
            _diagnostic_value_sha256(nested.get("podHostId"))
        diagnostic_display_key = (
            "gpuDisplayName" if parent == "machine" else "displayName" if parent == "gpu" else None
        )
        if diagnostic_display_key is not None and nested.get(diagnostic_display_key) is not None:
            observed_fields.append(f"{parent}.{diagnostic_display_key}")
            _bounded_diagnostic_text(nested.get(diagnostic_display_key))
        for provider_key, expected_key in fields.items():
            compare(
                provider_key,
                expected_key,
                source=nested,
                label=f"{parent}.{provider_key}",
            )

    desired_status = pod.get("desiredStatus")
    if not isinstance(desired_status, str) or not desired_status:
        raise LifecycleError("REST desired status is missing or malformed")
    if require_state_equal and desired_status != expected["desired_status"]:
        raise LifecycleError("REST desired status differs from GraphQL creation state")
    live_rate = _decimal_text(_provider_cost(pod.get("costPerHr")))
    if require_cost_equal and _provider_cost(live_rate) != _provider_cost(
        expected["cost_per_hour_usd"]
    ):
        raise LifecycleError("REST hourly cost differs from GraphQL creation cost")
    return {
        "proof_source": proof_source,
        "id": expected["id"],
        "name": expected["name"],
        "desired_status": desired_status,
        "cost_per_hour_usd": live_rate,
        "optional_false_field_status": optional_false_field_status,
        "observed_config_fields": sorted(observed_fields),
        "all_present_config_fields_match": True,
    }


def _validate_stored_rest_corroboration(
    value: Any, *, expected: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "proof_source",
        "id",
        "name",
        "desired_status",
        "cost_per_hour_usd",
        "optional_false_field_status",
        "observed_config_fields",
        "all_present_config_fields_match",
    }:
        raise LifecycleError("stored REST corroboration fields differ")
    fields = value.get("observed_config_fields")
    optional_status = value.get("optional_false_field_status")
    if (
        value.get("proof_source") != FINAL_REST_CORROBORATION_PROOF_SOURCE
        or value.get("id") != expected["id"]
        or value.get("name") != expected["name"]
        or value.get("desired_status") != "RUNNING"
        or value.get("all_present_config_fields_match") is not True
        or not isinstance(optional_status, Mapping)
        or set(optional_status) != {"interruptible", "locked"}
        or any(
            optional_status.get(field)
            not in {"absent", "observed_null", "observed_false"}
            for field in ("interruptible", "locked")
        )
        or not isinstance(fields, list)
        or fields != sorted(fields)
        or len(fields) != len(set(fields))
        or any(not isinstance(item, str) or not item for item in fields)
        or any(
            (optional_status.get(field) == "absent") == (field in fields)
            for field in ("interruptible", "locked")
        )
        or "containerDiskInGb" not in fields
        or "volumeMountPath" not in fields
        or "gpuCount" not in fields
        or "ports" not in fields
        or not ({"imageName", "image"} & set(fields))
        or _provider_cost(value.get("cost_per_hour_usd"))
        != _provider_cost(expected["cost_per_hour_usd"])
    ):
        raise LifecycleError("stored REST corroboration differs")
    return dict(value)


def _rollback(
    api: ApiCall,
    pod_id: str,
    *,
    expected_name: str,
    sleeper: Callable[[float], None] = time.sleep,
    verification_attempts: int = 5,
) -> bool:
    try:
        pre_status, pre_response = api("GET", f"/pods/{pod_id}", None)
        if pre_status == 200:
            if not isinstance(pre_response, Mapping) or (
                pre_response.get("id") != pod_id
                or pre_response.get("name") != expected_name
            ):
                return False
        elif pre_status == 404:
            list_status, listing = api(
                "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
            )
            if list_status != 200:
                return False
            matching_id = [
                row for row in _validated_inventory_rows(listing) if row["id"] == pod_id
            ]
            if len(matching_id) > 1 or (
                matching_id and matching_id[0]["name"] != expected_name
            ):
                return False
        else:
            return False
        status, _ = api("DELETE", f"/pods/{pod_id}", None)
    except Exception:
        return False
    if status != 204 or verification_attempts < 1 or verification_attempts > 60:
        return False
    for attempt in range(verification_attempts):
        try:
            direct_status, _ = api("GET", f"/pods/{pod_id}", None)
            list_status, listing = api(
                "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
            )
            if (
                direct_status == 404
                and list_status == 200
                and _inventory_proves_absent(listing, pod_id=pod_id)
            ):
                return True
        except Exception:
            pass
        if attempt + 1 < verification_attempts:
            sleeper(1.0)
    return False


def _sanitize_graphql_message(value: Any, *, api_key: str) -> str:
    if not isinstance(value, str):
        return "provider returned an unspecified GraphQL error"
    text = " ".join(value.split())[:240]
    if api_key:
        text = text.replace(api_key, "[redacted]")
    encoded = COMMON_SECRET_RE.sub(b"[redacted]", text.encode("utf-8", errors="replace"))
    return encoded.decode("utf-8", errors="replace") or "provider returned an empty GraphQL error"


def _graphql_candidate_pod(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    data = value.get("data")
    if not isinstance(data, Mapping):
        return None
    pod = data.get("podFindAndDeployOnDemand")
    return pod if isinstance(pod, Mapping) else None


def _graphql_authorized_candidate_id(value: Any, *, expected_name: str) -> str | None:
    pod = _graphql_candidate_pod(value)
    if pod is None or pod.get("name") != expected_name:
        return None
    pod_id = pod.get("id")
    return str(pod_id) if POD_ID_RE.fullmatch(str(pod_id)) else None


def _parse_graphql_create(
    status: int, value: Any, *, api_key: str, expected_name: str
) -> dict[str, Any]:
    pod = _graphql_candidate_pod(value)
    pod_id = _graphql_authorized_candidate_id(value, expected_name=expected_name)
    errors = value.get("errors") if isinstance(value, Mapping) else None
    if errors is not None and (
        not isinstance(errors, Sequence) or isinstance(errors, (str, bytes))
    ):
        raise GraphQLCreateError(
            "RunPod GraphQL create returned malformed errors", pod_id=pod_id
        )
    if isinstance(errors, Sequence) and not isinstance(errors, (str, bytes)) and errors:
        messages = []
        for row in list(errors)[:3]:
            message = row.get("message") if isinstance(row, Mapping) else None
            messages.append(_sanitize_graphql_message(message, api_key=api_key))
        raise GraphQLCreateError(
            f"RunPod GraphQL create failed: {' | '.join(messages)}", pod_id=pod_id
        )
    if status != 200:
        raise GraphQLCreateError(
            f"RunPod GraphQL create returned HTTP {status}", pod_id=pod_id
        )
    if pod_id is None:
        raise GraphQLCreateError(
            "RunPod GraphQL create returned no valid exact-name pod authority",
            pod_id=None,
        )
    if pod is None:  # narrowed by pod_id, retained for type checkers
        raise GraphQLCreateError("RunPod GraphQL create returned no pod", pod_id=None)
    return dict(pod)


def _validated_inventory_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise LifecycleError("RunPod account inventory is malformed")
    rows: list[Mapping[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise LifecycleError("RunPod account inventory contains a malformed row")
        pod_id = row.get("id")
        name = row.get("name")
        if (
            not isinstance(pod_id, str)
            or POD_ID_RE.fullmatch(pod_id) is None
            or not isinstance(name, str)
            or not name
            or len(name) > 256
        ):
            raise LifecycleError("RunPod account inventory row identity is malformed")
        rows.append(row)
    return rows


def _exact_name_matches(value: Any, *, pod_name: str) -> list[Mapping[str, Any]]:
    return [
        row for row in _validated_inventory_rows(value) if row["name"] == pod_name
    ]


def _inventory_proves_absent(value: Any, *, pod_id: str) -> bool:
    return all(row["id"] != pod_id for row in _validated_inventory_rows(value))


def _name_reconciliation(
    *,
    method: str,
    inventory_http_status: int | None,
    exact_name_match_count: int | None,
    candidate_pod_id: str | None,
    rollback_verified: bool | None,
    outcome: str,
    inventory_poll_attempts: int = 1,
    resolution_status: str = "resolved",
    manual_cleanup_required: bool = False,
    retry_allowed: bool = False,
) -> dict[str, Any]:
    """Return the fixed, compact evidence shape used in create receipts."""

    return {
        "method": method,
        "inventory_http_status": inventory_http_status,
        "exact_name_match_count": exact_name_match_count,
        "candidate_pod_id": candidate_pod_id,
        "rollback_verified": rollback_verified,
        "outcome": outcome,
        "inventory_poll_attempts": inventory_poll_attempts,
        "resolution_status": resolution_status,
        "manual_cleanup_required": manual_cleanup_required,
        "retry_allowed": retry_allowed,
    }


def _preflight_unique_pod_name(rest_api: ApiCall, *, pod_name: str) -> dict[str, Any]:
    try:
        status, listing = rest_api(
            "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
        )
    except Exception as exc:
        evidence = _name_reconciliation(
            method="precreate_exact_name_inventory",
            inventory_http_status=None,
            exact_name_match_count=None,
            candidate_pod_id=None,
            rollback_verified=None,
            outcome="inventory_transport_failure_no_create_attempted",
        )
        raise NameReconciliationError(
            f"pre-create account inventory failed ({type(exc).__name__})",
            evidence=evidence,
        ) from exc
    if status != 200:
        evidence = _name_reconciliation(
            method="precreate_exact_name_inventory",
            inventory_http_status=status,
            exact_name_match_count=None,
            candidate_pod_id=None,
            rollback_verified=None,
            outcome="inventory_http_failure_no_create_attempted",
        )
        raise NameReconciliationError(
            f"pre-create account inventory returned HTTP {status}", evidence=evidence
        )
    try:
        matches = _exact_name_matches(listing, pod_name=pod_name)
    except LifecycleError as exc:
        evidence = _name_reconciliation(
            method="precreate_exact_name_inventory",
            inventory_http_status=200,
            exact_name_match_count=None,
            candidate_pod_id=None,
            rollback_verified=None,
            outcome="inventory_schema_failure_no_create_attempted",
        )
        raise NameReconciliationError(str(exc), evidence=evidence) from exc
    if matches:
        evidence = _name_reconciliation(
            method="precreate_exact_name_inventory",
            inventory_http_status=200,
            exact_name_match_count=len(matches),
            candidate_pod_id=None,
            rollback_verified=None,
            outcome="exact_name_already_present_no_create_attempted",
        )
        raise NameReconciliationError(
            "pre-create pod name is not unique in the account inventory",
            evidence=evidence,
        )
    return _name_reconciliation(
        method="precreate_exact_name_inventory",
        inventory_http_status=200,
        exact_name_match_count=0,
        candidate_pod_id=None,
        rollback_verified=None,
        outcome="name_absent_before_create",
        resolution_status="precreate_name_absent",
        retry_allowed=True,
    )


def _preflight_network_volume(
    rest_api: ApiCall, *, volume_id: str, data_center_id: str
) -> dict[str, Any]:
    try:
        status, response = rest_api("GET", f"/networkvolumes/{volume_id}", None)
    except Exception as exc:
        raise LifecycleError(
            f"network-volume preflight failed ({type(exc).__name__})"
        ) from exc
    if status != 200:
        raise LifecycleError(f"network-volume preflight returned HTTP {status}")
    return _compact_network_volume(
        response, expected_id=volume_id, expected_data_center_id=data_center_id
    )


def _reconcile_ambiguous_create(
    rest_api: ApiCall,
    *,
    pod_name: str,
    sleeper: Callable[[float], None],
    inventory_attempts: int,
) -> dict[str, Any]:
    if inventory_attempts < 1 or inventory_attempts > 60:
        raise LifecycleError("post-create inventory attempt count is unsafe")
    last_status: int | None = None
    last_match_count: int | None = None
    last_observation = "inventory_not_observed"
    for attempt in range(1, inventory_attempts + 1):
        try:
            status, listing = rest_api(
                "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
            )
            last_status = status
            if status != 200:
                last_match_count = None
                last_observation = "inventory_http_failure"
            else:
                matches = _exact_name_matches(listing, pod_name=pod_name)
                last_match_count = len(matches)
                last_observation = "exact_name_absent_so_far"
                if len(matches) > 1:
                    return _name_reconciliation(
                        method="post_create_exact_name_inventory_poll",
                        inventory_http_status=200,
                        exact_name_match_count=len(matches),
                        candidate_pod_id=None,
                        rollback_verified=None,
                        outcome="ambiguous_exact_name_matches_no_mutation",
                        inventory_poll_attempts=attempt,
                        resolution_status="unresolved_possible_creation",
                        manual_cleanup_required=True,
                        retry_allowed=False,
                    )
                if len(matches) == 1:
                    pod_id = matches[0].get("id")
                    if not POD_ID_RE.fullmatch(str(pod_id)):
                        return _name_reconciliation(
                            method="post_create_exact_name_inventory_poll",
                            inventory_http_status=200,
                            exact_name_match_count=1,
                            candidate_pod_id=None,
                            rollback_verified=None,
                            outcome="unique_match_has_invalid_id_no_mutation",
                            inventory_poll_attempts=attempt,
                            resolution_status="unresolved_possible_creation",
                            manual_cleanup_required=True,
                            retry_allowed=False,
                        )
                    rollback = _rollback(
                        rest_api,
                        str(pod_id),
                        expected_name=pod_name,
                        sleeper=sleeper,
                    )
                    return _name_reconciliation(
                        method="post_create_exact_name_inventory_poll",
                        inventory_http_status=200,
                        exact_name_match_count=1,
                        candidate_pod_id=str(pod_id),
                        rollback_verified=rollback,
                        outcome=(
                            "unique_exact_name_match_rollback_verified"
                            if rollback
                            else "unique_exact_name_match_rollback_unverified"
                        ),
                        inventory_poll_attempts=attempt,
                        resolution_status=(
                            "resolved_rollback_verified"
                            if rollback
                            else "unresolved_possible_creation"
                        ),
                        manual_cleanup_required=not rollback,
                        retry_allowed=rollback,
                    )
        except Exception:
            last_status = None
            last_match_count = None
            last_observation = "inventory_transport_or_schema_failure"
        if attempt < inventory_attempts:
            sleeper(1.0)
    return _name_reconciliation(
        method="post_create_exact_name_inventory_poll",
        inventory_http_status=last_status,
        exact_name_match_count=last_match_count,
        candidate_pod_id=None,
        rollback_verified=None,
        outcome=(
            f"{last_observation}_manual_cleanup_required"
        ),
        inventory_poll_attempts=inventory_attempts,
        resolution_status="unresolved_possible_creation",
        manual_cleanup_required=True,
        retry_allowed=False,
    )


def _known_id_reconciliation(pod_id: str, rollback: bool) -> dict[str, Any]:
    return _name_reconciliation(
        method="graphql_response_id",
        inventory_http_status=None,
        exact_name_match_count=None,
        candidate_pod_id=pod_id,
        rollback_verified=rollback,
        outcome=("known_id_rollback_verified" if rollback else "known_id_rollback_unverified"),
        resolution_status=(
            "resolved_rollback_verified" if rollback else "unresolved_possible_creation"
        ),
        manual_cleanup_required=not rollback,
        retry_allowed=rollback,
    )


def _write_create_failure(
    directory: Path,
    *,
    stage: str,
    summary: str,
    request_sha256: str,
    rollback_verified: bool | None,
    candidate_pod_id: str | None,
    name_reconciliation: Mapping[str, Any],
    api_key: str,
) -> None:
    sanitized = _sanitize_graphql_message(summary, api_key=api_key)
    receipt = _sealed(
        "runpod_create_failure_v1",
        {
            "status": "failed_no_ownership_published",
            "failure_stage": stage,
            "sanitized_summary": sanitized,
            "request_sha256": request_sha256,
            "candidate_pod_id": candidate_pod_id,
            "rollback_verified": rollback_verified,
            "manual_cleanup_required": bool(
                name_reconciliation.get("manual_cleanup_required", False)
            ),
            "retry_allowed": bool(name_reconciliation.get("retry_allowed", False)),
            "name_reconciliation": dict(name_reconciliation),
        },
        api_key=api_key,
    )
    _write_receipt(directory / "CREATE_FAILURE.json", receipt, api_key=api_key)


def create_lifecycle(
    *,
    receipt_dir: Path,
    pod_name: str,
    volume_id: str,
    data_center_id: str,
    max_usd_text: str,
    max_hours_text: str,
    execute: bool,
    graphql_api: GraphQLCall | None = None,
    rest_api: ApiCall | None = None,
    api_key: str = "",
    now: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    rest_fetch_attempts: int = 30,
) -> Path:
    max_usd = _decimal(max_usd_text, "max USD")
    max_hours = _decimal(max_hours_text, "max hours")
    created_at, deadline, provider_deadline_text = _provider_deadline(
        now(), max_hours=max_hours
    )
    request = build_create_request(
        pod_name=pod_name,
        volume_id=volume_id,
        data_center_id=data_center_id,
        terminate_after_utc=provider_deadline_text,
    )
    if execute and (graphql_api is None or rest_api is None or not api_key):
        raise LifecycleError("execute requires RUNPOD_API_KEY from the environment")
    if rest_fetch_attempts < 1 or rest_fetch_attempts > 60:
        raise LifecycleError("REST verification attempt count is unsafe")
    directory = _external_directory(receipt_dir, fresh=True)
    request_sha = protocol.canonical_sha256(request)
    authorization = {
        "max_usd": _decimal_text(max_usd),
        "max_hours": _decimal_text(max_hours),
    }
    if not execute:
        receipt = _sealed(
            "runpod_create_dry_run_v1",
            {
                "status": "dry_run_no_api_call",
                "authorization": authorization,
                "request": request,
                "request_sha256": request_sha,
            },
            api_key=api_key,
        )
        return _write_receipt(directory / "CREATE_DRY_RUN.json", receipt, api_key=api_key)
    _write_receipt(
        directory / "CREATE_REQUEST.json",
        _sealed(
            "runpod_create_request_v1",
            {"status": "authorized", "authorization": authorization, "request": request,
             "request_sha256": request_sha},
            api_key=api_key,
        ),
        api_key=api_key,
    )
    try:
        preflight = _preflight_unique_pod_name(rest_api, pod_name=pod_name)
    except NameReconciliationError as exc:
        _write_create_failure(
            directory,
            stage="precreate_name_inventory",
            summary=str(exc),
            request_sha256=request_sha,
            rollback_verified=None,
            candidate_pod_id=None,
            name_reconciliation=exc.evidence,
            api_key=api_key,
        )
        raise LifecycleError(f"create blocked before GraphQL: {exc}") from exc
    try:
        network_volume = _preflight_network_volume(
            rest_api, volume_id=volume_id, data_center_id=data_center_id
        )
    except LifecycleError as exc:
        _write_create_failure(
            directory,
            stage="precreate_network_volume",
            summary=str(exc),
            request_sha256=request_sha,
            rollback_verified=None,
            candidate_pod_id=None,
            name_reconciliation=preflight,
            api_key=api_key,
        )
        raise LifecycleError(f"create blocked before GraphQL: {exc}") from exc
    _write_receipt(
        directory / "CREATE_PREFLIGHT.json",
        _sealed(
            "runpod_create_preflight_v1",
            {
                "status": "pass_name_absent_and_volume_bound",
                "request_sha256": request_sha,
                "name_reconciliation": preflight,
                "network_volume": network_volume,
            },
            api_key=api_key,
        ),
        api_key=api_key,
    )
    try:
        graphql_status, graphql_response = graphql_api(request)
        graphql_pod = _parse_graphql_create(
            graphql_status,
            graphql_response,
            api_key=api_key,
            expected_name=pod_name,
        )
    except GraphQLCreateError as exc:
        if exc.pod_id is not None:
            rollback = _rollback(
                rest_api, exc.pod_id, expected_name=pod_name, sleeper=sleeper
            )
            reconciliation = _known_id_reconciliation(exc.pod_id, rollback)
        else:
            reconciliation = _reconcile_ambiguous_create(
                rest_api,
                pod_name=pod_name,
                sleeper=sleeper,
                inventory_attempts=rest_fetch_attempts,
            )
            rollback = reconciliation["rollback_verified"]
        _write_create_failure(
            directory,
            stage="graphql_create",
            summary=str(exc),
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=reconciliation["candidate_pod_id"],
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(
            "GraphQL create failed; "
            f"reconciliation={reconciliation['outcome']}; "
            f"rollback_verified={rollback}: {exc}"
        ) from exc
    except Exception as exc:
        summary = f"RunPod GraphQL transport failed ({type(exc).__name__})"
        reconciliation = _reconcile_ambiguous_create(
            rest_api,
            pod_name=pod_name,
            sleeper=sleeper,
            inventory_attempts=rest_fetch_attempts,
        )
        _write_create_failure(
            directory,
            stage="graphql_transport",
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=reconciliation["rollback_verified"],
            candidate_pod_id=reconciliation["candidate_pod_id"],
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(
            f"{summary}; reconciliation={reconciliation['outcome']}; "
            f"rollback_verified={reconciliation['rollback_verified']}"
        ) from exc
    try:
        snapshot = _compact_graphql_created_pod(
            graphql_pod,
            expected_name=pod_name,
            expected_volume_id=volume_id,
            expected_data_center_id=data_center_id,
            network_volume=network_volume,
        )
        if _provider_cost(snapshot["cost_per_hour_usd"]) * max_hours > max_usd:
            raise LifecycleError("GraphQL price exceeds the explicit run authorization")
    except LifecycleError as exc:
        pod_id = str(graphql_pod["id"])
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        _write_create_failure(
            directory,
            stage="graphql_identity_or_budget",
            summary=str(exc),
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(
            f"GraphQL identity validation failed; rollback_verified={rollback}: {exc}"
        ) from exc
    except Exception as exc:
        # A valid exact-name pod ID is already known at this point.  Any
        # unexpected provider-shape or parser error must therefore take the
        # same fail-closed cleanup path without serializing the raw response.
        pod_id = str(graphql_pod["id"])
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        summary = f"GraphQL identity parsing failed ({type(exc).__name__})"
        _write_create_failure(
            directory,
            stage="graphql_identity_or_budget",
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(
            f"{summary}; rollback_verified={rollback}"
        ) from exc

    pod_id = str(snapshot["id"])
    rest_status: int | None = None
    rest_corroboration: dict[str, Any] | None = None
    rest_failure: LifecycleError | None = None
    try:
        for attempt in range(rest_fetch_attempts):
            rest_status, response = rest_api(
                "GET",
                f"/pods/{pod_id}?includeMachine=true&includeNetworkVolume=true",
                None,
            )
            if rest_status == 404 and attempt + 1 < rest_fetch_attempts:
                sleeper(1.0)
                continue
            if rest_status != 200:
                break
            try:
                candidate_corroboration = _compact_rest_corroboration(
                    response,
                    expected=snapshot,
                    require_cost_equal=True,
                    require_state_equal=False,
                )
                if candidate_corroboration["desired_status"] != "RUNNING":
                    raise ProviderSnapshotIncomplete(
                        "REST pod has not reached RUNNING readiness"
                    )
                rest_corroboration = candidate_corroboration
            except ProviderSnapshotIncomplete as exc:
                rest_failure = exc
                if attempt + 1 < rest_fetch_attempts:
                    sleeper(1.0)
                    continue
            except LifecycleError as exc:
                rest_failure = exc
            break
    except Exception as exc:
        rest_failure = LifecycleError(
            f"post-create REST corroboration failed ({type(exc).__name__})"
        )
    if rest_corroboration is None:
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        if rest_failure is not None:
            summary = str(rest_failure)
            stage = "rest_corroboration_incomplete_or_mismatch"
        else:
            summary = f"post-create REST corroboration returned HTTP {rest_status}"
            stage = "rest_corroboration_http"
        _write_create_failure(
            directory,
            stage=stage,
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(f"{summary}; rollback_verified={rollback}")
    conservative_rate = max(
        _provider_cost(snapshot["cost_per_hour_usd"]),
        _provider_cost(rest_corroboration["cost_per_hour_usd"]),
    )
    if conservative_rate * max_hours > max_usd:
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        summary = "conservative corroborated price exceeds the explicit authorization"
        _write_create_failure(
            directory,
            stage="rest_corroboration_budget",
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(f"{summary}; rollback_verified={rollback}")
    graphql_pod_read_request = _build_graphql_pod_read_request(pod_id)
    graphql_pod_read_request_sha = protocol.canonical_sha256(
        graphql_pod_read_request
    )
    graphql_locked_state_proof: dict[str, Any] | None = None
    graphql_locked_state_failure: str | None = None
    for attempt in range(1, rest_fetch_attempts + 1):
        try:
            read_status, read_response = graphql_api(graphql_pod_read_request)
        except Exception as exc:
            graphql_locked_state_failure = (
                f"GraphQL pod-read transport failed ({type(exc).__name__})"
            )
            break
        try:
            graphql_locked_state_proof = _compact_graphql_locked_state_proof(
                read_status,
                read_response,
                expected_id=pod_id,
                expected_name=pod_name,
                request_sha256=graphql_pod_read_request_sha,
                poll_attempts=attempt,
            )
        except ProviderSnapshotIncomplete:
            if attempt < rest_fetch_attempts:
                sleeper(1.0)
                continue
            graphql_locked_state_failure = (
                "GraphQL pod read remained transient after the bounded poll"
            )
        except LifecycleError as exc:
            graphql_locked_state_failure = str(exc)
        except Exception as exc:
            graphql_locked_state_failure = (
                f"GraphQL pod-read parsing failed ({type(exc).__name__})"
            )
        break
    if graphql_locked_state_proof is None:
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        summary = (
            graphql_locked_state_failure
            or "GraphQL locked-state proof is unavailable"
        )
        _write_create_failure(
            directory,
            stage="graphql_locked_state_readback",
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(f"{summary}; rollback_verified={rollback}")
    final_rest_corroboration: dict[str, Any] | None = None
    final_rest_failure: str | None = None
    try:
        final_rest_status, final_rest_response = rest_api(
            "GET",
            f"/pods/{pod_id}?includeMachine=true&includeNetworkVolume=true",
            None,
        )
        if final_rest_status != 200:
            final_rest_failure = (
                f"final post-GraphQL REST confirmation returned HTTP {final_rest_status}"
            )
        else:
            try:
                candidate_final_corroboration = _compact_rest_corroboration(
                    final_rest_response,
                    expected=snapshot,
                    require_cost_equal=True,
                    require_state_equal=False,
                    proof_source=FINAL_REST_CORROBORATION_PROOF_SOURCE,
                )
                if candidate_final_corroboration["desired_status"] != "RUNNING":
                    raise LifecycleError(
                        "final post-GraphQL REST confirmation is not RUNNING"
                    )
                final_rest_corroboration = candidate_final_corroboration
            except LifecycleError as exc:
                final_rest_failure = str(exc)
    except Exception as exc:
        final_rest_failure = (
            f"final post-GraphQL REST confirmation failed ({type(exc).__name__})"
        )
    if final_rest_corroboration is None:
        rollback = _rollback(
            rest_api, pod_id, expected_name=pod_name, sleeper=sleeper
        )
        reconciliation = _known_id_reconciliation(pod_id, rollback)
        summary = final_rest_failure or "final post-GraphQL REST proof is unavailable"
        _write_create_failure(
            directory,
            stage="final_rest_confirmation",
            summary=summary,
            request_sha256=request_sha,
            rollback_verified=rollback,
            candidate_pod_id=pod_id,
            name_reconciliation=reconciliation,
            api_key=api_key,
        )
        raise LifecycleError(f"{summary}; rollback_verified={rollback}")
    rest_corroboration = final_rest_corroboration
    try:
        ownership = _sealed(
            "runpod_pod_ownership_v1",
            {
                "status": "created",
                "agent_owned": True,
                "other_pods_mutated": False,
                "created_at_utc": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "hard_deadline_utc": provider_deadline_text,
                "provider_terminate_after_utc": provider_deadline_text,
                "authorization": authorization,
                "request_sha256": request_sha,
                "pod": snapshot,
                "graphql_locked_state_proof": graphql_locked_state_proof,
                "rest_corroboration": rest_corroboration,
            },
            api_key=api_key,
        )
        return _write_receipt(directory / "OWNERSHIP.json", ownership, api_key=api_key)
    except Exception as exc:
        rollback = _rollback(
            rest_api,
            str(snapshot["id"]),
            expected_name=pod_name,
            sleeper=sleeper,
        )
        raise LifecycleError(
            f"ownership receipt publication failed; rollback_verified={rollback}"
        ) from exc


def _budget_meter(
    ownership: Mapping[str, Any],
    observed_at: datetime,
    *,
    live_rate: Decimal | None = None,
) -> dict[str, Any]:
    max_usd, _ = _validate_authorization(ownership["authorization"])
    created = _parse_utc(ownership["created_at_utc"])
    deadline = _parse_utc(ownership["hard_deadline_utc"])
    delta = observed_at - created
    elapsed_microseconds = (
        delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    )
    elapsed = max(Decimal(0), Decimal(elapsed_microseconds) / Decimal(1_000_000))
    owned_rate = _provider_cost(ownership["pod"]["cost_per_hour_usd"])
    rate = max(owned_rate, live_rate) if live_rate is not None else owned_rate
    estimated = rate * elapsed / Decimal(3600)
    return {
        "elapsed_seconds": _decimal_text(elapsed),
        "conservative_estimated_compute_usd": _decimal_text(estimated),
        "metered_cost_per_hour_usd": _decimal_text(rate),
        "max_usd": _decimal_text(max_usd),
        "hard_deadline_utc": ownership["hard_deadline_utc"],
        "budget_exhausted": observed_at >= deadline or estimated >= max_usd,
    }


def _next_status_path(directory: Path) -> Path:
    for index in range(1, 10000):
        candidate = directory / f"STATUS_{index:04d}.json"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise LifecycleError("status receipt sequence is exhausted")


def status_lifecycle(
    *, ownership_path: Path, api: ApiCall, api_key: str,
    now: Callable[[], datetime] = _utc_now,
) -> tuple[Path, bool]:
    if not api_key:
        raise LifecycleError("status requires RUNPOD_API_KEY from the environment")
    directory, ownership = _load_ownership(ownership_path, api_key=api_key)
    pod_id = str(ownership["pod"]["id"])
    status, response = api("GET", f"/pods/{pod_id}?includeMachine=true&includeNetworkVolume=true", None)
    if status != 200:
        raise LifecycleError(f"owned pod status returned HTTP {status}")
    live = _compact_rest_corroboration(
        response,
        expected=ownership["pod"],
        require_cost_equal=False,
        require_state_equal=False,
    )
    observed = now().astimezone(timezone.utc)
    meter = _budget_meter(
        ownership, observed, live_rate=_provider_cost(live["cost_per_hour_usd"])
    )
    receipt = _sealed(
        "runpod_status_v1",
        {"status": "pass", "observed_at_utc": _utc_text(observed), "pod": live,
         "budget_meter": meter},
        api_key=api_key,
    )
    path = _write_receipt(_next_status_path(directory), receipt, api_key=api_key)
    return path, bool(meter["budget_exhausted"])


def terminate_lifecycle(
    *, ownership_path: Path, execute: bool, api: ApiCall | None = None,
    api_key: str = "", now: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    directory, ownership = _load_ownership(ownership_path, api_key=api_key)
    pod_id = str(ownership["pod"]["id"])
    if not execute:
        receipt = _sealed(
            "runpod_termination_dry_run_v1",
            {"status": "dry_run_no_api_call", "pod_id": pod_id,
             "ownership_receipt_sha256": ownership["receipt_sha256"]},
            api_key=api_key,
        )
        return _write_receipt(directory / "TERMINATION_DRY_RUN.json", receipt, api_key=api_key)
    if api is None or not api_key:
        raise LifecycleError("execute requires RUNPOD_API_KEY from the environment")
    pre_status, response = api(
        "GET", f"/pods/{pod_id}?includeMachine=true&includeNetworkVolume=true", None
    )
    if pre_status == 404:
        list_status, listing = api(
            "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
        )
        if list_status != 200:
            raise LifecycleError("owned pod account inventory is unavailable")
        matching_id = [
            row for row in _validated_inventory_rows(listing) if row["id"] == pod_id
        ]
        if not matching_id:
            observed = now().astimezone(timezone.utc)
            receipt = _sealed(
                "runpod_termination_v1",
                {
                    "status": "already_absent_verified",
                    "agent_owned": True,
                    "other_pods_mutated": False,
                    "pod_id": pod_id,
                    "deleted_at_utc": _utc_text(observed),
                    "delete_http_status": None,
                    "post_delete_direct_http_status": 404,
                    "absent_from_account_inventory": True,
                    "predelete_corroboration": "already_absent",
                    "budget_meter": _budget_meter(ownership, observed),
                    "ownership_receipt_sha256": ownership["receipt_sha256"],
                },
                api_key=api_key,
            )
            return _write_receipt(
                directory / "TERMINATION.json", receipt, api_key=api_key
            )
        if (
            len(matching_id) != 1
            or matching_id[0]["name"] != ownership["pod"]["name"]
        ):
            raise LifecycleError("owned pod exact-name cleanup authority differs")
        response = matching_id[0]
        pre_status = 200
    if pre_status != 200:
        raise LifecycleError(f"owned pod pre-termination lookup returned HTTP {pre_status}")
    _require_rest_cleanup_authority(response, expected=ownership["pod"])
    live_rate: Decimal | None = None
    try:
        predelete = _compact_rest_corroboration(
            response,
            expected=ownership["pod"],
            require_cost_equal=False,
            require_state_equal=False,
        )
        live_rate = _provider_cost(predelete["cost_per_hour_usd"])
    except LifecycleError:
        predelete = {
            "proof_source": "mutation_id_plus_exact_nonce_rest_name",
            "id": pod_id,
            "name": ownership["pod"]["name"],
            "status": "config_unavailable_or_mismatch_cleanup_proceeded",
        }
    delete_status, _ = api("DELETE", f"/pods/{pod_id}", None)
    if delete_status != 204:
        raise LifecycleError(f"RunPod termination returned HTTP {delete_status}")
    direct_status: int | None = None
    absent_from_inventory = False
    for attempt in range(5):
        direct_status, _ = api("GET", f"/pods/{pod_id}", None)
        list_status, listing = api("GET", "/pods?includeMachine=true&includeNetworkVolume=true", None)
        if list_status != 200:
            raise LifecycleError("post-termination account inventory is unavailable")
        absent_from_inventory = _inventory_proves_absent(listing, pod_id=pod_id)
        if direct_status == 404 and absent_from_inventory:
            break
        if attempt < 4:
            sleeper(1.0)
    if direct_status != 404 or not absent_from_inventory:
        raise LifecycleError("pod deletion could not be verified by both provider views")
    observed = now().astimezone(timezone.utc)
    receipt = _sealed(
        "runpod_termination_v1",
        {
            "status": "deleted_verified",
            "agent_owned": True,
            "other_pods_mutated": False,
            "pod_id": pod_id,
            "deleted_at_utc": _utc_text(observed),
            "delete_http_status": 204,
            "post_delete_direct_http_status": 404,
            "absent_from_account_inventory": True,
            "predelete_corroboration": predelete,
            "budget_meter": _budget_meter(
                ownership,
                observed,
                live_rate=live_rate,
            ),
            "ownership_receipt_sha256": ownership["receipt_sha256"],
        },
        api_key=api_key,
    )
    return _write_receipt(directory / "TERMINATION.json", receipt, api_key=api_key)


class RunPodRestClient:
    """Tiny fixed-host REST client; it does not follow redirects."""

    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        if len(api_key) < 16 or any(character.isspace() for character in api_key):
            raise LifecycleError("RUNPOD_API_KEY environment value is missing or malformed")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def __call__(
        self, method: str, path: str, payload: Mapping[str, Any] | None
    ) -> tuple[int, Any]:
        pod_item = re.fullmatch(
            rf"/pods/({POD_ID_RE.pattern[1:-1]})(?:\?includeMachine=true&includeNetworkVolume=true)?",
            path,
        )
        pod_list = path == "/pods?includeMachine=true&includeNetworkVolume=true"
        volume_item = re.fullmatch(
            rf"/networkvolumes/({VOLUME_ID_RE.pattern[1:-1]})", path
        )
        allowed = payload is None and (
            (
                method == "GET"
                and (pod_item is not None or pod_list or volume_item is not None)
            )
            or (method == "DELETE" and pod_item is not None and "?" not in path)
        )
        if not allowed:
            raise LifecycleError("RunPod API request is outside the lifecycle allowlist")
        body = None
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPSConnection(
            REST_API_HOST, timeout=self._timeout, context=ssl.create_default_context()
        )
        try:
            connection.request(method, REST_API_PREFIX + path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(4 * 1024**2 + 1)
            if len(raw) > 4 * 1024**2:
                raise LifecycleError("RunPod API response exceeds the fixed size limit")
            if not raw:
                parsed: Any = None
            else:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise LifecycleError("RunPod API returned invalid JSON") from exc
            return int(response.status), parsed
        finally:
            connection.close()


class RunPodGraphQLClient:
    """Fixed-host client for the fixed create and read-only ownership queries."""

    def __init__(self, api_key: str, *, timeout_seconds: int = 30) -> None:
        if len(api_key) < 16 or any(character.isspace() for character in api_key):
            raise LifecycleError("RUNPOD_API_KEY environment value is missing or malformed")
        self._api_key = api_key
        self._timeout = timeout_seconds

    def __call__(self, payload: Mapping[str, Any]) -> tuple[int, Any]:
        if set(payload) != {"query", "variables"}:
            raise LifecycleError("RunPod GraphQL request is outside the lifecycle allowlist")
        query = payload.get("query")
        if query == GRAPHQL_POD_READ_QUERY:
            variables = payload.get("variables")
            read_input = variables.get("input") if isinstance(variables, Mapping) else None
            pod_id = read_input.get("podId") if isinstance(read_input, Mapping) else None
            if (
                not isinstance(variables, Mapping)
                or set(variables) != {"input"}
                or not isinstance(read_input, Mapping)
                or set(read_input) != {"podId"}
                or not isinstance(pod_id, str)
                or POD_ID_RE.fullmatch(pod_id) is None
            ):
                raise LifecycleError("RunPod GraphQL pod read is outside the allowlist")
        elif query != GRAPHQL_CREATE_QUERY:
            raise LifecycleError("RunPod GraphQL request is outside the lifecycle allowlist")
        body = protocol.canonical_json_bytes(payload)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        connection = http.client.HTTPSConnection(
            GRAPHQL_API_HOST,
            timeout=self._timeout,
            context=ssl.create_default_context(),
        )
        try:
            connection.request("POST", GRAPHQL_API_PATH, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(4 * 1024**2 + 1)
            if len(raw) > 4 * 1024**2:
                raise LifecycleError("RunPod GraphQL response exceeds the fixed size limit")
            if not raw:
                parsed: Any = {}
            else:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {}
            return int(response.status), parsed
        finally:
            connection.close()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--receipt-dir", type=Path, required=True)
    create.add_argument("--pod-name", required=True)
    create.add_argument("--network-volume-id", required=True)
    create.add_argument("--data-center-id", required=True)
    create.add_argument("--max-usd", required=True)
    create.add_argument("--max-hours", required=True)
    create.add_argument("--execute", action="store_true")
    status = subparsers.add_parser("status")
    status.add_argument("--ownership-receipt", type=Path, required=True)
    terminate = subparsers.add_parser("terminate")
    terminate.add_argument("--ownership-receipt", type=Path, required=True)
    terminate.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    api_key = os.environ.get(API_KEY_ENV, "")
    reject_secret_argv(raw_argv, api_key=api_key)
    args = parse_args(raw_argv)
    if args.command == "create":
        rest_client = RunPodRestClient(api_key) if args.execute else None
        graphql_client = RunPodGraphQLClient(api_key) if args.execute else None
        output = create_lifecycle(
            receipt_dir=args.receipt_dir,
            pod_name=args.pod_name,
            volume_id=args.network_volume_id,
            data_center_id=args.data_center_id,
            max_usd_text=args.max_usd,
            max_hours_text=args.max_hours,
            execute=bool(args.execute),
            graphql_api=graphql_client,
            rest_api=rest_client,
            api_key=api_key,
        )
        print(str(output))
        return 0
    client = RunPodRestClient(api_key) if args.command == "status" or args.execute else None
    if args.command == "status":
        output, exhausted = status_lifecycle(
            ownership_path=args.ownership_receipt, api=client, api_key=api_key
        )
        print(str(output))
        return 3 if exhausted else 0
    output = terminate_lifecycle(
        ownership_path=args.ownership_receipt,
        execute=bool(args.execute),
        api=client,
        api_key=api_key,
    )
    print(str(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
