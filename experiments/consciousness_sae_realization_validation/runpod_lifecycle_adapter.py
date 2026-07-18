"""Dedicated-process adapter for the frozen audited RunPod lifecycle client.

The old source is never edited.  This adapter temporarily rebinds only the
study identity, immutable image metadata, and pod-name grammar while the CLI
call executes, then restores the imported module.  Run this module with
``python -m`` so no other study shares the process.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from . import protocol
from . import runpod_preflight
from .runpod_preflight import (
    EXPECTED_DATA_CENTER_ID,
    EXPECTED_VOLUME_ID,
    POD_NAME_PREFIX,
)


POD_NAME_RE = re.compile(
    rf"^{re.escape(POD_NAME_PREFIX)}[0-9]{{8}}-[0-9a-f]{{32}}$"
)
CONTAINER_DISK_GB = 20


def _compat_protocol() -> SimpleNamespace:
    immutable = str(protocol.CONTAINER_IMAGE_SPEC["immutable_reference"])
    digest = immutable.rsplit("@", 1)[1]
    image = {
        **protocol.CONTAINER_IMAGE_SPEC,
        "manifest_digest": digest,
        "manifest_media_type": "application/vnd.docker.distribution.manifest.v2+json",
    }
    return SimpleNamespace(
        STUDY_ID=protocol.STUDY_ID,
        CONTAINER_IMAGE_SPEC=image,
        canonical_json_bytes=protocol.canonical_json_bytes,
        canonical_sha256=protocol.canonical_sha256,
        sha256_bytes=lambda payload: hashlib.sha256(payload).hexdigest(),
    )


def _load_audited_lifecycle() -> ModuleType:
    """Load exactly one target-free audited source without its old package.

    The predecessor package initializer and protocol transitively import broad
    semantic fixtures.  The lifecycle implementation itself is target-free and
    only needs a protocol identity/hash surface plus ``paths.REPO_ROOT``.  A
    private synthetic package supplies precisely those dependencies, so the
    minimal guest never deploys or imports the predecessor fixture closure.
    """

    source = (
        Path(__file__).resolve().parents[1]
        / "consciousness_readout_validation"
        / "runpod_lifecycle.py"
    )
    if source.is_symlink() or not source.is_file():
        raise ImportError(f"audited lifecycle source is missing: {source}")
    package_name = "_consciousness_sae_realization_validation_lifecycle"
    package = ModuleType(package_name)
    package.__path__ = [str(source.parent)]  # type: ignore[attr-defined]
    package.__package__ = package_name
    protocol_module = ModuleType(f"{package_name}.protocol")
    for key, value in vars(_compat_protocol()).items():
        setattr(protocol_module, key, value)
    paths_module = ModuleType(f"{package_name}.paths")
    paths_module.REPO_ROOT = Path(__file__).resolve().parents[2]
    module_name = f"{package_name}.runpod_lifecycle"
    sys.modules[package_name] = package
    sys.modules[protocol_module.__name__] = protocol_module
    sys.modules[paths_module.__name__] = paths_module
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError("could not construct audited lifecycle module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module


frozen = _load_audited_lifecycle()


@contextmanager
def configured_frozen_lifecycle() -> Iterator[object]:
    """Rebind narrowly and restore, making test-process contamination impossible."""

    prior_protocol = frozen.protocol
    prior_prefix = frozen.POD_NAME_PREFIX
    prior_name_re = frozen.POD_NAME_RE
    prior_min_volume = frozen.MIN_NETWORK_VOLUME_GB
    prior_container_disk = frozen.CONTAINER_DISK_GB
    frozen.protocol = _compat_protocol()
    frozen.POD_NAME_PREFIX = POD_NAME_PREFIX
    frozen.POD_NAME_RE = POD_NAME_RE
    frozen.MIN_NETWORK_VOLUME_GB = 500
    frozen.CONTAINER_DISK_GB = CONTAINER_DISK_GB
    try:
        yield frozen
    finally:
        frozen.protocol = prior_protocol
        frozen.POD_NAME_PREFIX = prior_prefix
        frozen.POD_NAME_RE = prior_name_re
        frozen.MIN_NETWORK_VOLUME_GB = prior_min_volume
        frozen.CONTAINER_DISK_GB = prior_container_disk


def _flag_value(argv: Sequence[str], flag: str) -> str | None:
    try:
        index = list(argv).index(flag)
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    return str(argv[index + 1])


def _validate_cli_scope(argv: Sequence[str]) -> None:
    if not argv or argv[0] != "create":
        return
    expected = {
        "--network-volume-id": EXPECTED_VOLUME_ID,
        "--data-center-id": EXPECTED_DATA_CENTER_ID,
        "--max-usd": "36",
        "--max-hours": "6",
    }
    if any(_flag_value(argv, flag) != value for flag, value in expected.items()):
        raise frozen.LifecycleError(
            "create arguments differ from the frozen volume/location/$36/6h scope"
        )
    pod_name = _flag_value(argv, "--pod-name")
    if pod_name is None or POD_NAME_RE.fullmatch(pod_name) is None:
        raise frozen.LifecycleError("create pod name is outside the new-study namespace")


def compact_provider_inventory(value: Any) -> tuple[dict[str, Any], ...]:
    """Normalize the read-only RunPod account inventory to the frozen five fields."""

    if not isinstance(value, list):
        raise frozen.LifecycleError("RunPod account inventory is malformed")
    compact: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise frozen.LifecycleError("RunPod account inventory row is malformed")
        pod_id = raw.get("pod_id", raw.get("id"))
        pod_name = raw.get("pod_name", raw.get("name"))
        desired = raw.get("desired_status", raw.get("desiredStatus"))
        gpu_count = raw.get("gpu_count", raw.get("gpuCount"))
        machine = raw.get("machine")
        gpu_type = raw.get("gpu_type", raw.get("gpuTypeId"))
        if gpu_type is None and isinstance(machine, Mapping):
            gpu_type = machine.get("gpuTypeId")
        compact.append(
            {
                "pod_id": pod_id,
                "pod_name": pod_name,
                "desired_status": desired,
                "gpu_type": gpu_type,
                "gpu_count": gpu_count,
            }
        )
    # This validates IDs/names, duplicates, and pre-existing successor names.
    return runpod_preflight.canonical_unrelated_inventory(compact)


def load_and_build_successor_ownership(
    *,
    upstream_ownership_path: Path,
    create_contract: Mapping[str, Any],
    precreate_inventory: Sequence[Mapping[str, Any]],
    postcreate_inventory: Sequence[Mapping[str, Any]],
    api_key: str = "",
) -> dict[str, Any]:
    """Fully validate frozen OWNERSHIP.json and bridge it into successor authority."""

    precreate = compact_provider_inventory(list(precreate_inventory))
    # The post snapshot contains the newly owned successor pod, so validate its
    # rows without applying the pre-create prefix-collision rule to that one.
    postcreate: list[dict[str, Any]] = []
    for raw in postcreate_inventory:
        if not isinstance(raw, Mapping):
            raise frozen.LifecycleError("post-create inventory row is malformed")
        machine = raw.get("machine")
        gpu_type = raw.get("gpu_type", raw.get("gpuTypeId"))
        if gpu_type is None and isinstance(machine, Mapping):
            gpu_type = machine.get("gpuTypeId")
        postcreate.append(
            {
                "pod_id": raw.get("pod_id", raw.get("id")),
                "pod_name": raw.get("pod_name", raw.get("name")),
                "desired_status": raw.get(
                    "desired_status", raw.get("desiredStatus")
                ),
                "gpu_type": gpu_type,
                "gpu_count": raw.get("gpu_count", raw.get("gpuCount")),
            }
        )
    with configured_frozen_lifecycle() as lifecycle:
        _, upstream = lifecycle._load_ownership(  # type: ignore[attr-defined]
            Path(upstream_ownership_path), api_key=api_key
        )
        contract = runpod_preflight.validate_create_contract(
            create_contract, precreate_pods=precreate
        )
        request = lifecycle.build_create_request(
            pod_name=contract["pod_name"],
            volume_id=contract["network_volume_id"],
            data_center_id=contract["data_center_id"],
            terminate_after_utc=contract["terminate_after"],
        )
        if protocol.canonical_sha256(request) != upstream["request_sha256"]:
            raise frozen.LifecycleError(
                "upstream GraphQL create-request hash differs from contract"
            )
    return runpod_preflight.build_successor_ownership_receipt(
        upstream_ownership=upstream,
        create_contract=create_contract,
        precreate_pods=precreate,
        postcreate_pods=postcreate,
    )


def publish_successor_ownership(
    *,
    output_path: Path,
    upstream_ownership_path: Path,
    create_contract: Mapping[str, Any],
    precreate_inventory: Sequence[Mapping[str, Any]],
    postcreate_inventory: Sequence[Mapping[str, Any]],
    api_key: str = "",
) -> Path:
    receipt = load_and_build_successor_ownership(
        upstream_ownership_path=upstream_ownership_path,
        create_contract=create_contract,
        precreate_inventory=precreate_inventory,
        postcreate_inventory=postcreate_inventory,
        api_key=api_key,
    )
    return runpod_preflight._write_receipt_path(Path(output_path), receipt)


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    _validate_cli_scope(raw_argv)
    with configured_frozen_lifecycle() as lifecycle:
        return lifecycle.main(raw_argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
