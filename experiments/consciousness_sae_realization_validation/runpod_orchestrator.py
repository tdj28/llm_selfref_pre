#!/usr/bin/env python3
"""Exact-scope local orchestration for the successor RunPod experiment.

The command owns only a newly created, receipt-bound pod.  It records a
sanitized view of every account pod before and after creation, delegates the
single create/delete mutations to the frozen audited lifecycle implementation,
and proves that unrelated inventory is unchanged.  Provider receipts are
always stored outside the repository.

``create`` and ``terminate`` are network-free unless ``--execute`` is present.
``status`` is read-only.  ``RUNPOD_API_KEY`` is accepted only from the process
environment and is never included in arguments or receipts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import protocol
from . import runpod_lifecycle_adapter as adapter
from . import runpod_preflight as preflight


API_KEY_ENV = "RUNPOD_API_KEY"
ACCOUNT_INVENTORY_PATH = "/pods?includeMachine=true&includeNetworkVolume=true"
UPSTREAM_DIRECTORY_NAME = "frozen_lifecycle"
UPSTREAM_OWNERSHIP_NAME = "OWNERSHIP.json"
SUCCESSOR_OWNERSHIP_NAME = "OWNERSHIP.json"
CREATE_CONTRACT_NAME = "CREATE_CONTRACT.json"
PRECREATE_INVENTORY_NAME = "PRECREATE_INVENTORY.json"
POSTCREATE_INVENTORY_NAME = "POSTCREATE_INVENTORY.json"
POSTDELETE_INVENTORY_NAME = "POSTDELETE_INVENTORY.json"
POSTROLLBACK_INVENTORY_NAME = "POSTROLLBACK_INVENTORY.json"
POSTCREATE_FAILURE_NAME = "POSTCREATE_FAILURE.json"
READY_NAME = "READY.json"
TERMINATION_AUDIT_NAME = "TERMINATION_AUDIT.json"
MAX_RECEIPT_BYTES = 4 * 1024**2
READINESS_ATTEMPTS = 30
READINESS_POLL_SECONDS = 2.0
SAFE_PROVIDER_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,256}$")

RestApi = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]
GraphQLApi = Callable[[Mapping[str, Any]], tuple[int, Any]]


class OrchestrationError(RuntimeError):
    """A fail-closed local orchestration or receipt-chain failure."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OrchestrationError("orchestration clock is timezone-naive")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _environment_api_key(*, required: bool) -> str:
    """Load the credential from exactly one source: the process environment."""

    value = os.environ.get(API_KEY_ENV, "")
    if required and (
        len(value) < 16 or any(character.isspace() for character in value)
    ):
        raise OrchestrationError(
            "RUNPOD_API_KEY environment value is missing or malformed"
        )
    return value


def _reject_secret_bytes(payload: bytes, *, api_key: str) -> None:
    try:
        adapter.frozen._reject_secret_bytes(payload, api_key=api_key)
    except adapter.frozen.LifecycleError as exc:
        raise OrchestrationError(
            "credential-shaped material reached receipt bytes"
        ) from exc


def _outside_repository(path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    try:
        path.relative_to(repo)
    except ValueError:
        return
    raise OrchestrationError(
        "orchestration receipts must remain outside the repository"
    )


def _fresh_external_directory(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if (
        candidate.name in {"", ".", ".."}
        or candidate.exists()
        or candidate.is_symlink()
        or candidate.parent.is_symlink()
    ):
        raise OrchestrationError("orchestration receipt directory must be fresh")
    try:
        parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise OrchestrationError("orchestration receipt parent is missing") from exc
    resolved = parent / candidate.name
    _outside_repository(resolved)
    try:
        resolved.mkdir(mode=0o700)
    except OSError as exc:
        raise OrchestrationError(
            "orchestration receipt directory could not be created"
        ) from exc
    return resolved


def _existing_external_directory(path: Path) -> Path:
    candidate = Path(path).expanduser()
    if (
        candidate.is_symlink()
        or not candidate.is_dir()
        or candidate.parent.is_symlink()
    ):
        raise OrchestrationError("orchestration receipt directory is missing or unsafe")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise OrchestrationError(
            "orchestration receipt directory is unreadable"
        ) from exc
    _outside_repository(resolved)
    return resolved


def _write_json(path: Path, value: Mapping[str, Any], *, api_key: str) -> Path:
    payload = protocol.canonical_json_bytes(dict(value)) + b"\n"
    _reject_secret_bytes(payload, api_key=api_key)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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
        raise OrchestrationError("orchestration receipt publication failed") from exc
    return path


def _read_json(path: Path, *, label: str, api_key: str) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise OrchestrationError(f"{label} receipt is missing or unsafe")
    try:
        raw = candidate.read_bytes()
    except OSError as exc:
        raise OrchestrationError(f"{label} receipt is unreadable") from exc
    if len(raw) > MAX_RECEIPT_BYTES:
        raise OrchestrationError(f"{label} receipt is oversized")
    _reject_secret_bytes(raw, api_key=api_key)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OrchestrationError(f"{label} receipt is invalid JSON") from exc
    if (
        not isinstance(value, dict)
        or raw != protocol.canonical_json_bytes(value) + b"\n"
    ):
        raise OrchestrationError(f"{label} receipt is not canonical JSON")
    return value


def _sealed(kind: str, core: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "receipt_kind": kind,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        **dict(core),
    }
    value["receipt_sha256"] = protocol.canonical_sha256(value)
    return value


def _validate_self_hash(value: Mapping[str, Any], *, label: str) -> None:
    supplied = value.get("receipt_sha256")
    core = dict(value)
    core.pop("receipt_sha256", None)
    if (
        not isinstance(supplied, str)
        or re.fullmatch(r"[0-9a-f]{64}", supplied) is None
        or protocol.canonical_sha256(core) != supplied
    ):
        raise OrchestrationError(f"{label} receipt self-hash differs")


def _bounded_optional_text(value: Any, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or SAFE_PROVIDER_TEXT_RE.fullmatch(value) is None:
        raise OrchestrationError(f"provider {label} is malformed")
    return value


def sanitize_full_inventory(
    value: Any, *, allowed_successor: tuple[str, str] | None = None
) -> tuple[dict[str, Any], ...]:
    """Retain every pod but only five bounded, non-secret identity fields."""

    if not isinstance(value, list):
        raise OrchestrationError("RunPod account inventory is malformed")
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    successor_count = 0
    for raw in value:
        if not isinstance(raw, Mapping):
            raise OrchestrationError("RunPod account inventory row is malformed")
        pod_id = raw.get("pod_id", raw.get("id"))
        pod_name = raw.get("pod_name", raw.get("name"))
        desired_status = raw.get("desired_status", raw.get("desiredStatus"))
        gpu_count = raw.get("gpu_count", raw.get("gpuCount"))
        machine = raw.get("machine")
        gpu_type = raw.get("gpu_type", raw.get("gpuTypeId"))
        if gpu_type is None and isinstance(machine, Mapping):
            gpu_type = machine.get("gpuTypeId")
        if (
            not isinstance(pod_id, str)
            or preflight.POD_ID_RE.fullmatch(pod_id) is None
            or pod_id in seen_ids
        ):
            raise OrchestrationError("provider pod ID is malformed or duplicated")
        pod_name = _bounded_optional_text(pod_name, label="pod name")
        if pod_name is None:
            raise OrchestrationError("provider pod name is missing")
        desired_status = _bounded_optional_text(
            desired_status, label="desired status"
        )
        gpu_type = _bounded_optional_text(gpu_type, label="GPU type")
        if gpu_count is not None and (
            isinstance(gpu_count, bool)
            or not isinstance(gpu_count, int)
            or gpu_count < 0
            or gpu_count > 1024
        ):
            raise OrchestrationError("provider GPU count is malformed")
        if pod_name.startswith(preflight.POD_NAME_PREFIX):
            if allowed_successor != (pod_id, pod_name):
                raise OrchestrationError(
                    "unexpected successor-namespace pod is present"
                )
            successor_count += 1
        seen_ids.add(pod_id)
        rows.append(
            {
                "pod_id": pod_id,
                "pod_name": pod_name,
                "desired_status": desired_status,
                "gpu_type": gpu_type,
                "gpu_count": gpu_count,
            }
        )
    if allowed_successor is not None and successor_count != 1:
        raise OrchestrationError("post-create inventory lacks the exact successor pod")
    return tuple(sorted(rows, key=lambda row: str(row["pod_id"])))


def _fetch_inventory(rest_api: RestApi) -> list[Mapping[str, Any]]:
    status, value = rest_api("GET", ACCOUNT_INVENTORY_PATH, None)
    if status != 200 or not isinstance(value, list):
        raise OrchestrationError("RunPod full account inventory is unavailable")
    if not all(isinstance(row, Mapping) for row in value):
        raise OrchestrationError(
            "RunPod full account inventory contains a malformed row"
        )
    return list(value)


def _inventory_receipt(
    *, phase: str, rows: Sequence[Mapping[str, Any]], captured_at: datetime
) -> dict[str, Any]:
    canonical_rows = [dict(row) for row in rows]
    return _sealed(
        "runpod_sanitized_full_inventory_v1",
        {
            "status": "captured_read_only",
            "phase": phase,
            "captured_at": _utc_text(captured_at),
            "all_account_pod_count": len(canonical_rows),
            "pods": canonical_rows,
            "inventory_sha256": protocol.canonical_sha256(canonical_rows),
        },
    )


def _load_inventory_receipt(
    path: Path, *, phase: str, api_key: str
) -> tuple[dict[str, Any], ...]:
    value = _read_json(path, label=f"{phase} inventory", api_key=api_key)
    _validate_self_hash(value, label=f"{phase} inventory")
    if (
        value.get("receipt_kind") != "runpod_sanitized_full_inventory_v1"
        or value.get("study_id") != protocol.STUDY_ID
        or value.get("protocol_version") != protocol.PROTOCOL_VERSION
        or value.get("status") != "captured_read_only"
        or value.get("phase") != phase
        or not isinstance(value.get("pods"), list)
    ):
        raise OrchestrationError(f"{phase} inventory receipt identity differs")
    rows = sanitize_full_inventory(value["pods"])
    if (
        value.get("all_account_pod_count") != len(rows)
        or value.get("inventory_sha256")
        != protocol.canonical_sha256([dict(row) for row in rows])
    ):
        raise OrchestrationError(f"{phase} inventory receipt binding differs")
    return rows


def _load_successor_ownership(directory: Path, *, api_key: str) -> dict[str, Any]:
    value = _read_json(
        directory / SUCCESSOR_OWNERSHIP_NAME,
        label="successor ownership",
        api_key=api_key,
    )
    try:
        return preflight.validate_ownership_receipt(value)
    except preflight.PreflightError as exc:
        raise OrchestrationError("successor ownership receipt is invalid") from exc


def _load_bound_upstream(
    directory: Path, *, api_key: str, successor: Mapping[str, Any]
) -> tuple[Path, dict[str, Any]]:
    path = directory / UPSTREAM_DIRECTORY_NAME / UPSTREAM_OWNERSHIP_NAME
    try:
        with adapter.configured_frozen_lifecycle() as lifecycle:
            _, upstream = lifecycle._load_ownership(path, api_key=api_key)
    except adapter.frozen.LifecycleError as exc:
        raise OrchestrationError(
            "frozen lifecycle ownership receipt is invalid"
        ) from exc
    if (
        upstream.get("receipt_sha256")
        != successor.get("upstream_lifecycle_receipt_sha256")
        or upstream.get("pod", {}).get("id") != successor.get("pod_id")
        or upstream.get("pod", {}).get("name") != successor.get("pod_name")
    ):
        raise OrchestrationError("successor/frozen ownership receipt binding differs")
    return path, upstream


def _read_frozen_status(
    path: Path,
    *,
    api_key: str,
    successor: Mapping[str, Any],
) -> dict[str, Any]:
    value = _read_json(path, label="frozen lifecycle status", api_key=api_key)
    _validate_self_hash(value, label="frozen lifecycle status")
    pod = value.get("pod")
    if (
        value.get("receipt_kind") != "runpod_status_v1"
        or value.get("study_id") != protocol.STUDY_ID
        or value.get("status") != "pass"
        or not isinstance(pod, Mapping)
        or pod.get("id") != successor.get("pod_id")
        or pod.get("name") != successor.get("pod_name")
    ):
        raise OrchestrationError("frozen lifecycle status identity differs")
    return value


def _next_path(directory: Path, prefix: str) -> Path:
    for index in range(1, 10_000):
        candidate = directory / f"{prefix}_{index:04d}.json"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise OrchestrationError(f"{prefix.lower()} receipt sequence is exhausted")


def _safe_exception_type(error: BaseException) -> str:
    name = type(error).__name__
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) is None:
        return "Exception"
    return name


def _rollback_postcreate_failure(
    *,
    directory: Path,
    upstream_path: Path,
    precreate: Sequence[Mapping[str, Any]],
    rest_api: RestApi,
    api_key: str,
    now: Callable[[], datetime],
    sleeper: Callable[[float], None],
    failure_stage: str,
    error: BaseException,
) -> Path:
    """Delete only the frozen-receipt pod and preserve compact failure proof."""

    allowed_stages = {
        "load_upstream_ownership",
        "capture_postcreate_inventory",
        "publish_postcreate_inventory",
        "bridge_successor_ownership",
        "validate_postcreate_isolation",
        "poll_exact_owned_readiness",
    }
    if failure_stage not in allowed_stages:
        failure_stage = "load_upstream_ownership"
    pod_id: str | None = None
    upstream_hash: str | None = None
    termination_hash: str | None = None
    termination_status: str | None = None
    provider_absence_verified = False
    unrelated_inventory_unchanged: bool | None = None
    rollback_error_type: str | None = None

    try:
        with adapter.configured_frozen_lifecycle() as lifecycle:
            _, upstream = lifecycle._load_ownership(upstream_path, api_key=api_key)
            pod_id = str(upstream["pod"]["id"])
            upstream_hash = str(upstream["receipt_sha256"])
            termination_path = lifecycle.terminate_lifecycle(
                ownership_path=upstream_path,
                execute=True,
                api=rest_api,
                api_key=api_key,
                now=now,
                sleeper=sleeper,
            )
        termination = _read_json(
            termination_path,
            label="post-create rollback termination",
            api_key=api_key,
        )
        _validate_self_hash(termination, label="post-create rollback termination")
        termination_hash = str(termination.get("receipt_sha256"))
        termination_status = str(termination.get("status"))
        provider_absence_verified = (
            termination.get("receipt_kind") == "runpod_termination_v1"
            and termination.get("study_id") == protocol.STUDY_ID
            and termination.get("pod_id") == pod_id
            and termination.get("status")
            in {"deleted_verified", "already_absent_verified"}
            and termination.get("absent_from_account_inventory") is True
            and termination.get("post_delete_direct_http_status") == 404
        )
        if not provider_absence_verified:
            raise OrchestrationError(
                "post-create rollback did not prove exact owned-pod absence"
            )
        rollback_inventory_raw = _fetch_inventory(rest_api)
        rollback_inventory = sanitize_full_inventory(rollback_inventory_raw)
        rollback_receipt = _inventory_receipt(
            phase="postrollback", rows=rollback_inventory, captured_at=now()
        )
        _write_json(
            directory / POSTROLLBACK_INVENTORY_NAME,
            rollback_receipt,
            api_key=api_key,
        )
        before = preflight.canonical_unrelated_inventory(precreate)
        after = preflight.canonical_unrelated_inventory(rollback_inventory)
        unrelated_inventory_unchanged = before == after
    except BaseException as rollback_error:
        rollback_error_type = _safe_exception_type(rollback_error)

    rollback_verified = provider_absence_verified
    failure = _sealed(
        "runpod_successor_postcreate_failure_v1",
        {
            "status": (
                "postcreate_failure_exact_rollback_verified"
                if rollback_verified
                else "postcreate_failure_manual_cleanup_required"
            ),
            "failure_stage": failure_stage,
            "failure_type": _safe_exception_type(error),
            "pod_id": pod_id,
            "upstream_lifecycle_receipt_sha256": upstream_hash,
            "termination_receipt_sha256": termination_hash,
            "termination_status": termination_status,
            "provider_absence_verified": provider_absence_verified,
            "unrelated_inventory_unchanged": unrelated_inventory_unchanged,
            "rollback_error_type": rollback_error_type,
            "create_retried": False,
            "manual_cleanup_required": not rollback_verified,
        },
    )
    return _write_json(
        directory / POSTCREATE_FAILURE_NAME,
        failure,
        api_key=api_key,
    )


def status_successor(
    *,
    receipt_dir: Path,
    pod_id: str,
    rest_api: RestApi | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> tuple[Path, bool, str]:
    """Read only the exact receipt-owned pod and publish a compact status link."""

    api_key = _environment_api_key(required=True)
    directory = _existing_external_directory(receipt_dir)
    successor = _load_successor_ownership(directory, api_key=api_key)
    try:
        exact_id = preflight.require_exact_owned_pod_id(
            pod_id, ownership_receipt=successor
        )
    except preflight.PreflightError as exc:
        raise OrchestrationError("status pod ID is not the exact owned pod") from exc
    upstream_path, _ = _load_bound_upstream(
        directory, api_key=api_key, successor=successor
    )
    observed_at = now()
    with adapter.configured_frozen_lifecycle() as lifecycle:
        client = rest_api or lifecycle.RunPodRestClient(api_key)
        frozen_path, exhausted = lifecycle.status_lifecycle(
            ownership_path=upstream_path,
            api=client,
            api_key=api_key,
            now=lambda: observed_at,
        )
    frozen_status = _read_frozen_status(
        frozen_path, api_key=api_key, successor=successor
    )
    desired_status = str(frozen_status["pod"]["desired_status"])
    summary = _sealed(
        "runpod_successor_status_link_v1",
        {
            "status": "pass_exact_owned_pod_read",
            "observed_at": _utc_text(observed_at),
            "pod_id": exact_id,
            "pod_name": successor["pod_name"],
            "provider_desired_status": desired_status,
            "budget_exhausted": bool(exhausted),
            "frozen_status_receipt_sha256": frozen_status["receipt_sha256"],
            "successor_ownership_receipt_sha256": successor["receipt_sha256"],
        },
    )
    output = _write_json(
        _next_path(directory, "STATUS"), summary, api_key=api_key
    )
    return output, bool(exhausted), desired_status


def _poll_readiness(
    *,
    receipt_dir: Path,
    pod_id: str,
    rest_api: RestApi,
    now: Callable[[], datetime],
    sleeper: Callable[[float], None],
    attempts: int,
) -> Path:
    if attempts < 1 or attempts > 120:
        raise OrchestrationError("readiness poll attempt count is unsafe")
    last_status = "not_observed"
    last_status_path: Path | None = None
    for attempt in range(1, attempts + 1):
        last_status_path, exhausted, last_status = status_successor(
            receipt_dir=receipt_dir,
            pod_id=pod_id,
            rest_api=rest_api,
            now=now,
        )
        if exhausted:
            raise OrchestrationError(
                "provider budget/deadline was exhausted before readiness"
            )
        if last_status == "RUNNING":
            api_key = _environment_api_key(required=True)
            status_value = _read_json(
                last_status_path, label="successor status", api_key=api_key
            )
            ready = _sealed(
                "runpod_successor_ready_v1",
                {
                    "status": "ready_exact_owned_pod",
                    "pod_id": pod_id,
                    "attempts": attempt,
                    "status_receipt_sha256": status_value["receipt_sha256"],
                },
            )
            return _write_json(
                _existing_external_directory(receipt_dir) / READY_NAME,
                ready,
                api_key=api_key,
            )
        if attempt < attempts:
            sleeper(READINESS_POLL_SECONDS)
    raise OrchestrationError(
        f"exact owned pod did not become RUNNING ({last_status})"
    )


def create_successor(
    *,
    receipt_dir: Path,
    execute: bool,
    rest_api: RestApi | None = None,
    graphql_api: GraphQLApi | None = None,
    now: Callable[[], datetime] = _utc_now,
    nonce_factory: Callable[[], str] = lambda: secrets.token_hex(16),
    sleeper: Callable[[float], None] = time.sleep,
    readiness_attempts: int = READINESS_ATTEMPTS,
) -> Path:
    """Create at most one frozen-lifecycle pod and bridge it to successor authority."""

    api_key = _environment_api_key(required=execute)
    observed_at = now()
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise OrchestrationError("orchestration clock is timezone-naive")
    nonce = nonce_factory()
    directory = _fresh_external_directory(receipt_dir)

    if not execute:
        contract = preflight.build_create_contract(
            created_at=observed_at,
            nonce=nonce,
            provider_pods=(),
        )
        _write_json(
            directory / "CREATE_CONTRACT_DRY_RUN.json", contract, api_key=api_key
        )
        with adapter.configured_frozen_lifecycle() as lifecycle:
            frozen_path = lifecycle.create_lifecycle(
                receipt_dir=directory / UPSTREAM_DIRECTORY_NAME,
                pod_name=contract["pod_name"],
                volume_id=preflight.EXPECTED_VOLUME_ID,
                data_center_id=preflight.EXPECTED_DATA_CENTER_ID,
                max_usd_text="36",
                max_hours_text="6",
                execute=False,
                api_key=api_key,
                now=lambda: observed_at,
                sleeper=sleeper,
            )
        frozen_value = _read_json(
            frozen_path, label="frozen create dry run", api_key=api_key
        )
        dry_run = _sealed(
            "runpod_successor_orchestration_dry_run_v1",
            {
                "status": "dry_run_no_api_call",
                "create_contract_sha256": contract["create_contract_sha256"],
                "frozen_create_receipt_sha256": frozen_value["receipt_sha256"],
                "assumed_precreate_pod_count": 0,
            },
        )
        return _write_json(
            directory / "ORCHESTRATION_DRY_RUN.json", dry_run, api_key=api_key
        )

    if (rest_api is None) != (graphql_api is None):
        raise OrchestrationError(
            "execute requires either both injected clients or both live clients"
        )
    with adapter.configured_frozen_lifecycle() as lifecycle:
        rest_client = rest_api or lifecycle.RunPodRestClient(api_key)
        graphql_client = graphql_api or lifecycle.RunPodGraphQLClient(api_key)

    precreate_raw = _fetch_inventory(rest_client)
    precreate = sanitize_full_inventory(precreate_raw)
    precreate_receipt = _inventory_receipt(
        phase="precreate", rows=precreate, captured_at=now()
    )
    _write_json(
        directory / PRECREATE_INVENTORY_NAME,
        precreate_receipt,
        api_key=api_key,
    )
    contract = preflight.build_create_contract(
        created_at=observed_at,
        nonce=nonce,
        provider_pods=precreate,
    )
    _write_json(directory / CREATE_CONTRACT_NAME, contract, api_key=api_key)

    # Exactly one create call.  One captured time feeds both contract and
    # frozen lifecycle, so request hashes cannot race across a UTC second.
    with adapter.configured_frozen_lifecycle() as lifecycle:
        upstream_path = lifecycle.create_lifecycle(
            receipt_dir=directory / UPSTREAM_DIRECTORY_NAME,
            pod_name=contract["pod_name"],
            volume_id=preflight.EXPECTED_VOLUME_ID,
            data_center_id=preflight.EXPECTED_DATA_CENTER_ID,
            max_usd_text="36",
            max_hours_text="6",
            execute=True,
            graphql_api=graphql_client,
            rest_api=rest_client,
            api_key=api_key,
            now=lambda: observed_at,
            sleeper=sleeper,
        )

    stage = "load_upstream_ownership"
    try:
        upstream_value = _read_json(
            upstream_path, label="frozen lifecycle ownership", api_key=api_key
        )
        upstream_pod = upstream_value.get("pod")
        if not isinstance(upstream_pod, Mapping):
            raise OrchestrationError("frozen lifecycle ownership lacks a pod")
        expected_owned = (str(upstream_pod.get("id")), contract["pod_name"])

        stage = "capture_postcreate_inventory"
        postcreate_raw = _fetch_inventory(rest_client)
        postcreate = sanitize_full_inventory(
            postcreate_raw, allowed_successor=expected_owned
        )
        postcreate_receipt = _inventory_receipt(
            phase="postcreate", rows=postcreate, captured_at=now()
        )
        stage = "publish_postcreate_inventory"
        _write_json(
            directory / POSTCREATE_INVENTORY_NAME,
            postcreate_receipt,
            api_key=api_key,
        )

        stage = "bridge_successor_ownership"
        adapter.publish_successor_ownership(
            output_path=directory / SUCCESSOR_OWNERSHIP_NAME,
            upstream_ownership_path=upstream_path,
            create_contract=contract,
            precreate_inventory=precreate,
            postcreate_inventory=postcreate,
            api_key=api_key,
        )
        successor = _load_successor_ownership(directory, api_key=api_key)

        stage = "validate_postcreate_isolation"
        preflight.validate_inventory_after_create(
            precreate_pods=precreate,
            postcreate_pods=postcreate,
            ownership_receipt=successor,
        )

        stage = "poll_exact_owned_readiness"
        _poll_readiness(
            receipt_dir=directory,
            pod_id=successor["pod_id"],
            rest_api=rest_client,
            now=now,
            sleeper=sleeper,
            attempts=readiness_attempts,
        )
    except BaseException as error:
        failure_path = _rollback_postcreate_failure(
            directory=directory,
            upstream_path=upstream_path,
            precreate=precreate,
            rest_api=rest_client,
            api_key=api_key,
            now=now,
            sleeper=sleeper,
            failure_stage=stage,
            error=error,
        )
        raise OrchestrationError(
            f"post-create orchestration failed; rollback receipt: {failure_path}"
        ) from error
    return directory / SUCCESSOR_OWNERSHIP_NAME


def terminate_successor(
    *,
    receipt_dir: Path,
    pod_id: str,
    execute: bool,
    rest_api: RestApi | None = None,
    now: Callable[[], datetime] = _utc_now,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    """Terminate only the exact receipt-owned ID and prove account isolation."""

    api_key = _environment_api_key(required=execute)
    directory = _existing_external_directory(receipt_dir)
    successor = _load_successor_ownership(directory, api_key=api_key)
    try:
        exact_id = preflight.require_exact_owned_pod_id(
            pod_id, ownership_receipt=successor
        )
    except preflight.PreflightError as exc:
        raise OrchestrationError(
            "termination pod ID is not the exact owned pod"
        ) from exc
    upstream_path, _ = _load_bound_upstream(
        directory, api_key=api_key, successor=successor
    )
    observed_at = now()
    with adapter.configured_frozen_lifecycle() as lifecycle:
        client = rest_api or (
            lifecycle.RunPodRestClient(api_key) if execute else None
        )
        frozen_path = lifecycle.terminate_lifecycle(
            ownership_path=upstream_path,
            execute=execute,
            api=client,
            api_key=api_key,
            now=lambda: observed_at,
            sleeper=sleeper,
        )
    frozen_value = _read_json(
        frozen_path, label="frozen lifecycle termination", api_key=api_key
    )
    if not execute:
        dry = _sealed(
            "runpod_successor_termination_dry_run_v1",
            {
                "status": "dry_run_no_api_call",
                "pod_id": exact_id,
                "frozen_termination_receipt_sha256": frozen_value["receipt_sha256"],
                "successor_ownership_receipt_sha256": successor["receipt_sha256"],
            },
        )
        return _write_json(
            directory / "TERMINATION_DRY_RUN.json", dry, api_key=api_key
        )

    if client is None:  # pragma: no cover - execute construction is exhaustive
        raise OrchestrationError("internal termination client is absent")
    postdelete_raw = _fetch_inventory(client)
    postdelete = sanitize_full_inventory(postdelete_raw)
    postdelete_receipt = _inventory_receipt(
        phase="postdelete", rows=postdelete, captured_at=now()
    )
    _write_json(
        directory / POSTDELETE_INVENTORY_NAME,
        postdelete_receipt,
        api_key=api_key,
    )
    precreate = _load_inventory_receipt(
        directory / PRECREATE_INVENTORY_NAME,
        phase="precreate",
        api_key=api_key,
    )
    try:
        preflight.validate_inventory_after_delete(
            precreate_pods=precreate,
            postdelete_pods=postdelete,
            ownership_receipt=successor,
        )
    except preflight.PreflightError as exc:
        raise OrchestrationError(
            "post-delete absence/unrelated-inventory proof failed"
        ) from exc
    audit = _sealed(
        "runpod_successor_termination_audit_v1",
        {
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            "pod_id": exact_id,
            "frozen_termination_receipt_sha256": frozen_value["receipt_sha256"],
            "precreate_inventory_sha256": protocol.canonical_sha256(
                [dict(row) for row in precreate]
            ),
            "postdelete_inventory_sha256": protocol.canonical_sha256(
                [dict(row) for row in postdelete]
            ),
            "successor_ownership_receipt_sha256": successor["receipt_sha256"],
        },
    )
    return _write_json(
        directory / TERMINATION_AUDIT_NAME, audit, api_key=api_key
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--receipt-dir", type=Path, required=True)
    create.add_argument("--execute", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--receipt-dir", type=Path, required=True)
    status.add_argument("--pod-id", required=True)
    terminate = commands.add_parser("terminate")
    terminate.add_argument("--receipt-dir", type=Path, required=True)
    terminate.add_argument("--pod-id", required=True)
    terminate.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    api_key = _environment_api_key(required=False)
    try:
        adapter.frozen.reject_secret_argv(raw_argv, api_key=api_key)
    except adapter.frozen.LifecycleError as exc:
        raise OrchestrationError(
            "credentials may not be supplied as arguments"
        ) from exc
    args = parse_args(raw_argv)
    if args.command == "create":
        output = create_successor(
            receipt_dir=args.receipt_dir,
            execute=bool(args.execute),
        )
        print(str(output))
        return 0
    if args.command == "status":
        output, exhausted, _ = status_successor(
            receipt_dir=args.receipt_dir,
            pod_id=args.pod_id,
        )
        print(str(output))
        return 3 if exhausted else 0
    output = terminate_successor(
        receipt_dir=args.receipt_dir,
        pod_id=args.pod_id,
        execute=bool(args.execute),
    )
    print(str(output))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
