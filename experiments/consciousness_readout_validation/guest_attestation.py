"""Attest the owned RunPod guest before touching its network volume.

This gate is intentionally separate from public-artifact staging.  It performs
only read-only guest checks, never imports Torch or a model, never creates the
study volume sentinel, and publishes a compact self-hashed receipt outside
both the repository and ``/workspace`` only after every check passes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths, protocol, runtime


GUEST_ATTESTATION_SCHEMA_VERSION = 3
GUEST_ATTESTATION_RECEIPT_FILENAME = "GUEST_ATTESTATION_RECEIPT.json"
GUEST_ATTESTATION_RECEIPT_KIND = "runpod_guest_attestation_v3"
EXPECTED_VOLUME_ID = "qf2lwehl89"
EXPECTED_DATA_CENTER_ID = "US-NE-1"
WORKSPACE_ROOT = Path("/workspace")
RUNPOD_IDENTITY_ENV = (
    "RUNPOD_POD_ID",
    "RUNPOD_VOLUME_ID",
    "RUNPOD_DC_ID",
)
PID1_ENVIRON_PATH = Path("/proc/1/environ")
MAX_PID1_ENVIRON_BYTES = 1024 * 1024
MAX_PID1_ENVIRON_ENTRIES = 16_384
MAX_PID1_ENVIRON_ENTRY_BYTES = 64 * 1024
MAX_PID1_IDENTITY_VALUE_BYTES = 256
PYTHONDONTWRITEBYTECODE_ENV = "PYTHONDONTWRITEBYTECODE"
GUEST_ATTESTATION_MODULE = (
    "experiments.consciousness_readout_validation.guest_attestation"
)
STAGE_PUBLIC_ARTIFACTS_MODULE = (
    "experiments.consciousness_readout_validation.stage_public_artifacts"
)

# Exact selected bytes resolved at the three frozen public revisions.  This is
# a pre-network capacity gate; the stager independently resolves and verifies
# every selected remote file before downloading it.
FROZEN_PUBLIC_ARTIFACT_COMPONENT_BYTES = {
    "model": 141_124_876_012,
    "sae": 4_295_268_226,
    "j_lens": 10_603_228_607,
}
FROZEN_PUBLIC_ARTIFACT_BYTES = sum(FROZEN_PUBLIC_ARTIFACT_COMPONENT_BYTES.values())
MIN_STAGE_HEADROOM_BYTES = 40 * 1024**3
MIN_FINAL_FREE_BYTES = 32 * 1024**3
MIN_GPU_MEMORY_BYTES = 160 * 1024**3
MAX_RECEIPT_AGE_SECONDS = 15 * 60
MAX_FUTURE_CLOCK_SKEW_SECONDS = 30
MAX_RECEIPT_BYTES = 64 * 1024
MAX_MOUNTINFO_BYTES = 4 * 1024**2
MAX_MOUNTINFO_LINES = 65_536
MAX_MOUNTINFO_FIELD_BYTES = 4_096
MAX_PROCESS_CMDLINE_BYTES = 64 * 1024
MAX_PROCESS_ARGUMENTS = 256
MAX_PROCESS_ARGUMENT_BYTES = 4_096
_BOOT_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


class GuestAttestationError(RuntimeError):
    """Raised before publication or volume mutation when guest identity is unsafe."""


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_expected_identity(
    *, owned_pod_id: str, volume_id: str, data_center_id: str
) -> None:
    if not runtime.SAFE_RUN_ID.fullmatch(owned_pod_id):
        raise GuestAttestationError("owned pod ID is malformed")
    if volume_id != EXPECTED_VOLUME_ID:
        raise GuestAttestationError("volume ID differs from the frozen pilot volume")
    if data_center_id != EXPECTED_DATA_CENTER_ID:
        raise GuestAttestationError("data-center ID differs from the frozen pilot location")


def _expected_environment(
    *, owned_pod_id: str, volume_id: str, data_center_id: str
) -> dict[str, str]:
    return {
        "RUNPOD_POD_ID": owned_pod_id,
        "RUNPOD_VOLUME_ID": volume_id,
        "RUNPOD_DC_ID": data_center_id,
    }


def _default_read_pid1_environ() -> bytes:
    try:
        with PID1_ENVIRON_PATH.open("rb") as handle:
            payload = handle.read(MAX_PID1_ENVIRON_BYTES + 1)
    except OSError:
        raise
    if len(payload) > MAX_PID1_ENVIRON_BYTES:
        raise GuestAttestationError("provider PID 1 environment exceeds its parser limit")
    return payload


def _provider_pid1_identity_record(
    payload: bytes,
    *,
    owned_pod_id: str,
    volume_id: str,
    data_center_id: str,
) -> dict[str, Any]:
    expected = _expected_environment(
        owned_pod_id=owned_pod_id,
        volume_id=volume_id,
        data_center_id=data_center_id,
    )
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > MAX_PID1_ENVIRON_BYTES
        or not payload.endswith(b"\0")
    ):
        raise GuestAttestationError("provider PID 1 environment is malformed")
    entries = payload[:-1].split(b"\0")
    if (
        not entries
        or len(entries) > MAX_PID1_ENVIRON_ENTRIES
        or any(not entry or len(entry) > MAX_PID1_ENVIRON_ENTRY_BYTES for entry in entries)
    ):
        raise GuestAttestationError("provider PID 1 environment structure is unsafe")
    allowlist = {name.encode("ascii"): name for name in RUNPOD_IDENTITY_ENV}
    observed: dict[str, str] = {}
    for entry in entries:
        name, separator, raw_value = entry.partition(b"=")
        if not separator or not name:
            raise GuestAttestationError("provider PID 1 environment entry is malformed")
        selected_name = allowlist.get(name)
        if selected_name is None:
            # Non-allowlisted values remain opaque bytes: they are never decoded,
            # returned, logged, or written to the receipt.
            continue
        if selected_name in observed or len(raw_value) > MAX_PID1_IDENTITY_VALUE_BYTES:
            raise GuestAttestationError("provider PID 1 identity variables are malformed")
        try:
            observed[selected_name] = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GuestAttestationError(
                "provider PID 1 identity variables are not UTF-8"
            ) from exc
    del entry, name, separator, raw_value, selected_name
    if observed != expected:
        raise GuestAttestationError("provider PID 1 identity variables differ")
    # Drop the bounded raw container promptly. Python cannot promise physical
    # memory erasure, so the receipt makes only the narrower, testable claim
    # that non-allowlisted values were not decoded or persisted.
    del entries
    del payload
    return {
        "provenance": "provider_pid1_environment",
        "provider_process_id": 1,
        "allowlisted_values": expected,
        "non_allowlisted_values_decoded": False,
        "non_allowlisted_values_emitted": False,
        "non_allowlisted_values_logged": False,
        "non_allowlisted_values_persisted": False,
    }


def expected_python_launch_contract(module: str) -> dict[str, Any]:
    return {
        "entry_module": module,
        "pythondontwritebytecode_environment": "1",
        "python_minus_b_flag_present": True,
        "runtime_dont_write_bytecode": True,
    }


def _default_read_process_cmdline() -> bytes:
    try:
        with Path("/proc/self/cmdline").open("rb") as handle:
            payload = handle.read(MAX_PROCESS_CMDLINE_BYTES + 1)
    except OSError:
        raise
    if len(payload) > MAX_PROCESS_CMDLINE_BYTES:
        raise GuestAttestationError("Python process command line exceeds its parser limit")
    return payload


def _python_launch_record(
    environ: Mapping[str, str],
    *,
    expected_module: str,
    read_process_cmdline: Callable[[], bytes],
    runtime_dont_write_bytecode: bool | None,
) -> dict[str, Any]:
    if environ.get(PYTHONDONTWRITEBYTECODE_ENV) != "1":
        raise GuestAttestationError("PYTHONDONTWRITEBYTECODE must be exact literal 1")
    observed_runtime_flag = (
        bool(sys.flags.dont_write_bytecode)
        if runtime_dont_write_bytecode is None
        else runtime_dont_write_bytecode
    )
    if observed_runtime_flag is not True:
        raise GuestAttestationError("Python runtime bytecode suppression is not active")
    try:
        payload = read_process_cmdline()
    except OSError as exc:
        raise GuestAttestationError("Python process command line could not be read") from exc
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > MAX_PROCESS_CMDLINE_BYTES
        or not payload.endswith(b"\0")
    ):
        raise GuestAttestationError("Python process command line is malformed")
    arguments = payload[:-1].split(b"\0")
    if (
        len(arguments) < 4
        or len(arguments) > MAX_PROCESS_ARGUMENTS
        or any(
            not argument or len(argument) > MAX_PROCESS_ARGUMENT_BYTES
            for argument in arguments
        )
    ):
        raise GuestAttestationError("Python process argument structure is unsafe")
    expected_prefix = (b"-B", b"-m", expected_module.encode("ascii"))
    if tuple(arguments[1:4]) != expected_prefix:
        raise GuestAttestationError("Python must use exact -B and bound module launch")
    return expected_python_launch_contract(expected_module)


def _repository_source_record(
    repository_root: Path,
    *,
    workspace: Path,
) -> dict[str, Any]:
    if repository_root.is_symlink():
        raise GuestAttestationError("bound repository source root may not be a symlink")
    try:
        resolved_repository = repository_root.resolve(strict=True)
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise GuestAttestationError("bound repository source root could not be resolved") from exc
    if not resolved_repository.is_dir():
        raise GuestAttestationError("bound repository source root is not a directory")
    if _is_within(resolved_repository, resolved_workspace):
        raise GuestAttestationError("bound repository source root must be outside /workspace")
    return {
        "outside_workspace": True,
        "resolved_path_sha256": hashlib.sha256(
            str(resolved_repository).encode("utf-8")
        ).hexdigest(),
    }


def _default_nvidia_smi() -> str:
    command = (
        "nvidia-smi",
        "--query-gpu=index,name,memory.total",
        "--format=csv,noheader,nounits",
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GuestAttestationError("nvidia-smi could not be executed read-only") from exc
    if completed.returncode != 0:
        raise GuestAttestationError(
            f"nvidia-smi read-only query failed with code {completed.returncode}"
        )
    return completed.stdout


def _gpu_record(output: str) -> dict[str, Any]:
    try:
        rows = [
            tuple(field.strip() for field in row)
            for row in csv.reader(output.splitlines())
            if row
        ]
    except csv.Error as exc:
        raise GuestAttestationError("nvidia-smi output is malformed") from exc
    if len(rows) != 1 or len(rows[0]) != 3:
        raise GuestAttestationError("exactly one nvidia-smi CUDA GPU is required")
    index, name, memory_mib_text = rows[0]
    if index != "0" or not name or re.search(r"\bB200\b", name, re.IGNORECASE) is None:
        raise GuestAttestationError("the sole CUDA GPU must be an NVIDIA B200")
    try:
        memory_mib = int(memory_mib_text)
    except ValueError as exc:
        raise GuestAttestationError("nvidia-smi memory.total is not an integer MiB value") from exc
    total_memory_bytes = memory_mib * 1024**2
    if total_memory_bytes < MIN_GPU_MEMORY_BYTES:
        raise GuestAttestationError("B200 memory is below the frozen 160-GiB minimum")
    return {
        "attestation_tool": "nvidia-smi",
        "cuda_gpu_count": 1,
        "index": 0,
        "name": name,
        "total_memory_bytes": total_memory_bytes,
        "minimum_total_memory_bytes": MIN_GPU_MEMORY_BYTES,
    }


def _decode_mount_point(value: str) -> str:
    """Decode only the kernel escapes needed to compare the mount point."""

    try:
        raw_bytes = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise GuestAttestationError("/proc/self/mountinfo field is not UTF-8") from exc
    if not raw_bytes or len(raw_bytes) > MAX_MOUNTINFO_FIELD_BYTES:
        raise GuestAttestationError("/proc/self/mountinfo field length is unsafe")
    replacements = {
        r"\040": " ",
        r"\011": "\t",
        r"\012": "\n",
        r"\134": "\\",
    }
    decoded: list[str] = []
    cursor = 0
    while cursor < len(value):
        if value[cursor] != "\\":
            decoded.append(value[cursor])
            cursor += 1
            continue
        escaped = value[cursor : cursor + 4]
        literal = replacements.get(escaped)
        if literal is None:
            raise GuestAttestationError(
                "/proc/self/mountinfo mount-point escape is malformed"
            )
        decoded.append(literal)
        cursor += 4
    result = "".join(decoded)
    if any(ord(character) < 32 or ord(character) == 127 for character in result):
        raise GuestAttestationError("/proc/self/mountinfo field contains control data")
    return result


def _bounded_mountinfo_lines(mountinfo_text: str) -> list[str]:
    try:
        payload = mountinfo_text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise GuestAttestationError("/proc/self/mountinfo is not UTF-8") from exc
    if len(payload) > MAX_MOUNTINFO_BYTES:
        raise GuestAttestationError("/proc/self/mountinfo exceeds the bounded parser limit")
    lines = mountinfo_text.splitlines()
    if not lines or len(lines) > MAX_MOUNTINFO_LINES:
        raise GuestAttestationError("/proc/self/mountinfo line count is unsafe")
    return lines


def _bounded_raw_mountinfo_field(value: str, *, label: str) -> str:
    """Validate an opaque mountinfo field without interpreting backslash notation."""

    try:
        raw_bytes = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise GuestAttestationError(f"/workspace {label} is not UTF-8") from exc
    if not raw_bytes or len(raw_bytes) > MAX_MOUNTINFO_FIELD_BYTES:
        raise GuestAttestationError(f"/workspace {label} length is unsafe")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise GuestAttestationError(f"/workspace {label} contains control data")
    return value


def _raw_mountinfo_field_sha256(value: str) -> str:
    """Hash exact UTF-8 field bytes without decoding FUSE or kernel notation."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mount_record(
    workspace: Path,
    *,
    mountinfo_text: str,
    is_mount: Callable[[str], bool],
    access: Callable[[str, int], bool],
) -> dict[str, Any]:
    if workspace.is_symlink():
        raise GuestAttestationError("/workspace may not be a symlink")
    try:
        resolved = workspace.resolve(strict=True)
    except OSError as exc:
        raise GuestAttestationError("/workspace is missing") from exc
    if resolved != WORKSPACE_ROOT or not resolved.is_dir():
        raise GuestAttestationError("artifact root must be the exact /workspace directory")
    if not is_mount(str(resolved)):
        raise GuestAttestationError("/workspace is not an operating-system mount point")

    matches: list[tuple[str, str, str, str]] = []
    for line in _bounded_mountinfo_lines(mountinfo_text):
        try:
            line_bytes = line.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise GuestAttestationError("/proc/self/mountinfo line is not UTF-8") from exc
        if not line_bytes or len(line_bytes) > MAX_MOUNTINFO_FIELD_BYTES * 4:
            raise GuestAttestationError("/proc/self/mountinfo line length is unsafe")
        if line.count(" - ") != 1:
            raise GuestAttestationError("/proc/self/mountinfo line structure is malformed")
        left, separator, right = line.partition(" - ")
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            raise GuestAttestationError("/proc/self/mountinfo line structure is malformed")
        mount_point = _decode_mount_point(left_fields[4])
        if mount_point == str(resolved):
            mount_root = _bounded_raw_mountinfo_field(
                left_fields[3], label="raw mount-root field"
            )
            mount_source = _bounded_raw_mountinfo_field(
                right_fields[1], label="raw mount-source field"
            )
            matches.append(
                (right_fields[0], left_fields[2], mount_root, mount_source)
            )
    if len(matches) != 1:
        raise GuestAttestationError("/proc/self/mountinfo lacks one exact /workspace entry")
    filesystem_type, device_major_minor, mount_root, mount_source = matches[0]
    if not filesystem_type or re.fullmatch(r"[A-Za-z0-9._+-]+", filesystem_type) is None:
        raise GuestAttestationError("/workspace filesystem type is malformed")
    if re.fullmatch(r"[0-9]+:[0-9]+", device_major_minor) is None:
        raise GuestAttestationError("/workspace mount device identity is malformed")
    if not mount_root.startswith("/"):
        raise GuestAttestationError("/workspace mount root is malformed")
    if not access(str(resolved), os.R_OK | os.W_OK | os.X_OK):
        raise GuestAttestationError("/workspace is not readable, writable, and searchable")
    return {
        "mount_point": str(resolved),
        "path_is_mount": True,
        "mountinfo_exact_entry": True,
        "filesystem_type": filesystem_type,
        "device_major_minor": device_major_minor,
        "raw_field_hash_semantics": (
            "sha256_utf8_of_exact_raw_mountinfo_field_without_unescaping"
        ),
        "mount_root_raw_field_sha256": _raw_mountinfo_field_sha256(mount_root),
        "mount_source_raw_field_sha256": _raw_mountinfo_field_sha256(mount_source),
        "read_write_search_access": True,
    }


def _disk_record(
    workspace: Path, *, disk_usage: Callable[[Path], Any]
) -> dict[str, Any]:
    try:
        free_bytes = int(disk_usage(workspace).free)
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise GuestAttestationError("/workspace free-space query failed") from exc
    required_before = FROZEN_PUBLIC_ARTIFACT_BYTES + MIN_STAGE_HEADROOM_BYTES
    predicted_final = free_bytes - FROZEN_PUBLIC_ARTIFACT_BYTES
    if free_bytes < required_before:
        raise GuestAttestationError(
            "insufficient free bytes for frozen artifacts plus 40-GiB headroom"
        )
    if predicted_final < MIN_FINAL_FREE_BYTES:
        raise GuestAttestationError("predicted post-stage free bytes are below 32 GiB")
    return {
        "free_bytes": free_bytes,
        "frozen_public_artifact_bytes": FROZEN_PUBLIC_ARTIFACT_BYTES,
        "minimum_stage_headroom_bytes": MIN_STAGE_HEADROOM_BYTES,
        "required_free_before_stage_bytes": required_before,
        "predicted_free_after_stage_bytes": predicted_final,
        "minimum_final_free_bytes": MIN_FINAL_FREE_BYTES,
    }


def _sentinel_record(workspace: Path, *, volume_id: str) -> dict[str, Any]:
    sentinel = workspace / paths.VOLUME_SENTINEL
    if not sentinel.exists() and not sentinel.is_symlink():
        return {"state": "absent_safe_for_stager_initialization"}
    if sentinel.is_symlink() or not sentinel.is_file():
        raise GuestAttestationError("existing study volume sentinel is not a regular file")
    if sentinel.stat().st_size > 4096:
        raise GuestAttestationError("existing study volume sentinel is oversized")
    try:
        payload = sentinel.read_bytes()
        observed = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuestAttestationError("existing study volume sentinel is invalid") from exc
    expected = {
        "schema_version": 1,
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "volume_id": volume_id,
    }
    if observed != expected:
        raise GuestAttestationError("existing study volume sentinel differs from this pilot")
    return {
        "state": "exact_existing_match",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
    }


def _boot_id_sha256(read_boot_id: Callable[[], str]) -> str:
    try:
        value = read_boot_id().strip().lower()
    except OSError as exc:
        raise GuestAttestationError("guest boot ID could not be read") from exc
    if _BOOT_ID.fullmatch(value) is None:
        raise GuestAttestationError("guest boot ID is malformed")
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _default_read_boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii")


def _default_read_mountinfo() -> str:
    try:
        with Path("/proc/self/mountinfo").open("rb") as handle:
            payload = handle.read(MAX_MOUNTINFO_BYTES + 1)
    except OSError:
        raise
    if len(payload) > MAX_MOUNTINFO_BYTES:
        raise GuestAttestationError("/proc/self/mountinfo exceeds the bounded parser limit")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GuestAttestationError("/proc/self/mountinfo is not UTF-8") from exc


def _utc_timestamp(now: datetime | None) -> str:
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise GuestAttestationError("attestation clock must be timezone-aware")
    return (
        observed.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _safe_receipt_directory(receipt_dir: Path, *, workspace: Path) -> Path:
    if receipt_dir.name in {"", ".", ".."} or not runtime.SAFE_RUN_ID.fullmatch(
        receipt_dir.name
    ):
        raise GuestAttestationError("receipt directory name is unsafe")
    if receipt_dir.exists() or receipt_dir.is_symlink():
        raise GuestAttestationError("receipt directory must be fresh and non-symlinked")
    try:
        parent = receipt_dir.parent.expanduser().resolve(strict=True)
    except OSError as exc:
        raise GuestAttestationError("receipt directory parent is missing") from exc
    if not parent.is_dir():
        raise GuestAttestationError("receipt directory parent is not a directory")
    candidate = parent / receipt_dir.name
    repository = paths.REPO_ROOT.resolve(strict=True)
    workspace_resolved = workspace.resolve(strict=True)
    if _is_within(candidate, repository) or _is_within(candidate, workspace_resolved):
        raise GuestAttestationError("receipt directory must be outside repository and /workspace")
    return candidate


def _write_receipt_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(protocol.canonical_json_bytes(dict(value)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def attest_guest(
    *,
    owned_pod_id: str,
    volume_id: str,
    data_center_id: str,
    receipt_dir: Path,
    environ: Mapping[str, str] | None = None,
    workspace: Path = WORKSPACE_ROOT,
    nvidia_smi: Callable[[], str] = _default_nvidia_smi,
    read_mountinfo: Callable[[], str] = _default_read_mountinfo,
    is_mount: Callable[[str], bool] = os.path.ismount,
    access: Callable[[str, int], bool] = os.access,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    read_pid1_environ: Callable[[], bytes] = _default_read_pid1_environ,
    read_boot_id: Callable[[], str] = _default_read_boot_id,
    read_process_cmdline: Callable[[], bytes] = _default_read_process_cmdline,
    runtime_dont_write_bytecode: bool | None = None,
    repository_root: Path = paths.REPO_ROOT,
    now: datetime | None = None,
) -> Path:
    """Run all read-only guest checks and publish one fresh pass receipt."""

    _validate_expected_identity(
        owned_pod_id=owned_pod_id,
        volume_id=volume_id,
        data_center_id=data_center_id,
    )
    current_environment = environ if environ is not None else os.environ
    try:
        pid1_environment = read_pid1_environ()
    except OSError as exc:
        raise GuestAttestationError(
            "provider PID 1 environment could not be read"
        ) from exc
    identity_binding = _provider_pid1_identity_record(
        pid1_environment,
        owned_pod_id=owned_pod_id,
        volume_id=volume_id,
        data_center_id=data_center_id,
    )
    launch_contract = _python_launch_record(
        current_environment,
        expected_module=GUEST_ATTESTATION_MODULE,
        read_process_cmdline=read_process_cmdline,
        runtime_dont_write_bytecode=runtime_dont_write_bytecode,
    )
    repository_source = _repository_source_record(
        repository_root,
        workspace=workspace,
    )
    gpu = _gpu_record(nvidia_smi())
    try:
        mountinfo_text = read_mountinfo()
    except OSError as exc:
        raise GuestAttestationError("/proc/self/mountinfo could not be read") from exc
    mount = _mount_record(
        workspace,
        mountinfo_text=mountinfo_text,
        is_mount=is_mount,
        access=access,
    )
    disk = _disk_record(workspace, disk_usage=disk_usage)
    sentinel = _sentinel_record(workspace, volume_id=volume_id)
    boot_hash = _boot_id_sha256(read_boot_id)
    destination = _safe_receipt_directory(receipt_dir, workspace=workspace)
    timestamp = _utc_timestamp(now)
    core = {
        "schema_version": GUEST_ATTESTATION_SCHEMA_VERSION,
        "receipt_kind": GUEST_ATTESTATION_RECEIPT_KIND,
        "status": "pass",
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "owned_pod_id": owned_pod_id,
        "volume_id": volume_id,
        "data_center_id": data_center_id,
        "artifact_root": str(WORKSPACE_ROOT),
        "identity_binding": identity_binding,
        "python_launch_contract": launch_contract,
        "repository_source": repository_source,
        "guest_boot_id_sha256": boot_hash,
        "attested_at_utc": timestamp,
        "maximum_receipt_age_seconds": MAX_RECEIPT_AGE_SECONDS,
        "gpu": gpu,
        "mount": mount,
        "disk": disk,
        "volume_sentinel": sentinel,
        "receipt_directory": str(destination),
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt_path = destination / GUEST_ATTESTATION_RECEIPT_FILENAME
    _write_receipt_exclusive(receipt_path, receipt)
    return receipt_path


def _load_receipt(path: Path, *, artifact_root: Path) -> tuple[Path, dict[str, Any]]:
    if path.name != GUEST_ATTESTATION_RECEIPT_FILENAME:
        raise GuestAttestationError("guest-attestation receipt filename differs")
    if path.is_symlink() or not path.is_file():
        raise GuestAttestationError("guest-attestation receipt is missing or unsafe")
    resolved = path.resolve(strict=True)
    repository = paths.REPO_ROOT.resolve(strict=True)
    root = artifact_root.resolve(strict=True)
    if _is_within(resolved, repository) or _is_within(resolved, root):
        raise GuestAttestationError("guest-attestation receipt must remain external")
    if resolved.stat().st_size > MAX_RECEIPT_BYTES:
        raise GuestAttestationError("guest-attestation receipt is oversized")
    try:
        raw = resolved.read_bytes()
        receipt = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuestAttestationError("guest-attestation receipt is invalid JSON") from exc
    if not isinstance(receipt, dict):
        raise GuestAttestationError("guest-attestation receipt must be a JSON object")
    if raw != protocol.canonical_json_bytes(receipt) + b"\n":
        raise GuestAttestationError("guest-attestation receipt encoding is not canonical")
    return resolved, receipt


def _parse_attested_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GuestAttestationError("guest-attestation timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GuestAttestationError("guest-attestation timestamp is malformed") from exc
    return parsed.astimezone(timezone.utc)


def validate_guest_attestation_receipt(
    receipt_path: Path,
    *,
    expected_owned_pod_id: str,
    expected_volume_id: str,
    expected_data_center_id: str,
    expected_artifact_root: Path,
    environ: Mapping[str, str] | None = None,
    workspace: Path = WORKSPACE_ROOT,
    nvidia_smi: Callable[[], str] = _default_nvidia_smi,
    read_mountinfo: Callable[[], str] = _default_read_mountinfo,
    is_mount: Callable[[str], bool] = os.path.ismount,
    access: Callable[[str, int], bool] = os.access,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    read_pid1_environ: Callable[[], bytes] = _default_read_pid1_environ,
    read_boot_id: Callable[[], str] = _default_read_boot_id,
    read_process_cmdline: Callable[[], bytes] = _default_read_process_cmdline,
    runtime_dont_write_bytecode: bool | None = None,
    repository_root: Path = paths.REPO_ROOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Revalidate a fresh receipt and current read-only guest state pre-staging."""

    _validate_expected_identity(
        owned_pod_id=expected_owned_pod_id,
        volume_id=expected_volume_id,
        data_center_id=expected_data_center_id,
    )
    current_environment_mapping = environ if environ is not None else os.environ
    current_stage_launch = _python_launch_record(
        current_environment_mapping,
        expected_module=STAGE_PUBLIC_ARTIFACTS_MODULE,
        read_process_cmdline=read_process_cmdline,
        runtime_dont_write_bytecode=runtime_dont_write_bytecode,
    )
    current_repository_source = _repository_source_record(
        repository_root,
        workspace=workspace,
    )
    try:
        resolved_root = expected_artifact_root.resolve(strict=True)
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as exc:
        raise GuestAttestationError("expected /workspace artifact root is missing") from exc
    if (
        expected_artifact_root.is_symlink()
        or resolved_root != WORKSPACE_ROOT
        or resolved_workspace != WORKSPACE_ROOT
    ):
        raise GuestAttestationError("staging artifact root must be exact /workspace")
    resolved_path, receipt = _load_receipt(
        receipt_path, artifact_root=expected_artifact_root
    )
    required_fields = {
        "schema_version",
        "receipt_kind",
        "status",
        "study_slug",
        "study_id",
        "protocol_version",
        "owned_pod_id",
        "volume_id",
        "data_center_id",
        "artifact_root",
        "identity_binding",
        "python_launch_contract",
        "repository_source",
        "guest_boot_id_sha256",
        "attested_at_utc",
        "maximum_receipt_age_seconds",
        "gpu",
        "mount",
        "disk",
        "volume_sentinel",
        "receipt_directory",
        "model_weights_loaded",
        "model_forward_count",
        "prior_outcome_inputs",
        "target_prompt_inputs",
        "target_outcome_inputs",
        "receipt_sha256",
    }
    if set(receipt) != required_fields:
        raise GuestAttestationError("guest-attestation receipt field set differs")
    core = dict(receipt)
    embedded_hash = core.pop("receipt_sha256")
    if not isinstance(embedded_hash, str) or embedded_hash != protocol.canonical_sha256(core):
        raise GuestAttestationError("guest-attestation receipt self-hash differs")
    expected_identity = {
        "schema_version": GUEST_ATTESTATION_SCHEMA_VERSION,
        "receipt_kind": GUEST_ATTESTATION_RECEIPT_KIND,
        "status": "pass",
        "study_slug": protocol.STUDY_SLUG,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "owned_pod_id": expected_owned_pod_id,
        "volume_id": expected_volume_id,
        "data_center_id": expected_data_center_id,
        "artifact_root": str(WORKSPACE_ROOT),
        "python_launch_contract": expected_python_launch_contract(
            GUEST_ATTESTATION_MODULE
        ),
        "maximum_receipt_age_seconds": MAX_RECEIPT_AGE_SECONDS,
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "prior_outcome_inputs": [],
        "target_prompt_inputs": [],
        "target_outcome_inputs": [],
    }
    if any(receipt.get(key) != value for key, value in expected_identity.items()):
        raise GuestAttestationError("guest-attestation identity or empty-input contract differs")
    if receipt.get("receipt_directory") != str(resolved_path.parent):
        raise GuestAttestationError("guest-attestation receipt directory binding differs")
    if receipt.get("repository_source") != current_repository_source:
        raise GuestAttestationError("bound repository source-root binding differs")

    try:
        pid1_environment = read_pid1_environ()
    except OSError as exc:
        raise GuestAttestationError(
            "provider PID 1 environment could not be reread"
        ) from exc
    current_identity_binding = _provider_pid1_identity_record(
        pid1_environment,
        owned_pod_id=expected_owned_pod_id,
        volume_id=expected_volume_id,
        data_center_id=expected_data_center_id,
    )
    if receipt.get("identity_binding") != current_identity_binding:
        raise GuestAttestationError("guest-attestation provider identity binding differs")
    current_boot_hash = _boot_id_sha256(read_boot_id)
    if receipt.get("guest_boot_id_sha256") != current_boot_hash:
        raise GuestAttestationError("guest-attestation receipt came from another guest boot")

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise GuestAttestationError("validation clock must be timezone-aware")
    age = (
        current_time.astimezone(timezone.utc)
        - _parse_attested_at(receipt.get("attested_at_utc"))
    ).total_seconds()
    if age < -MAX_FUTURE_CLOCK_SKEW_SECONDS or age > MAX_RECEIPT_AGE_SECONDS:
        raise GuestAttestationError("guest-attestation receipt is stale or future-dated")

    current_gpu = _gpu_record(nvidia_smi())
    if receipt.get("gpu") != current_gpu:
        raise GuestAttestationError("current B200 inventory differs from guest attestation")
    try:
        mountinfo_text = read_mountinfo()
    except OSError as exc:
        raise GuestAttestationError("/proc/self/mountinfo could not be reread") from exc
    current_mount = _mount_record(
        workspace,
        mountinfo_text=mountinfo_text,
        is_mount=is_mount,
        access=access,
    )
    if receipt.get("mount") != current_mount:
        raise GuestAttestationError("current /workspace mount differs from guest attestation")
    current_disk = _disk_record(workspace, disk_usage=disk_usage)
    attested_disk = receipt.get("disk")
    if not isinstance(attested_disk, Mapping):
        raise GuestAttestationError("guest-attestation disk record is malformed")
    frozen_disk_fields = {
        "frozen_public_artifact_bytes": FROZEN_PUBLIC_ARTIFACT_BYTES,
        "minimum_stage_headroom_bytes": MIN_STAGE_HEADROOM_BYTES,
        "required_free_before_stage_bytes": (
            FROZEN_PUBLIC_ARTIFACT_BYTES + MIN_STAGE_HEADROOM_BYTES
        ),
        "minimum_final_free_bytes": MIN_FINAL_FREE_BYTES,
    }
    if any(attested_disk.get(key) != value for key, value in frozen_disk_fields.items()):
        raise GuestAttestationError("guest-attestation frozen disk budget differs")
    free_at_attestation = attested_disk.get("free_bytes")
    predicted_at_attestation = attested_disk.get("predicted_free_after_stage_bytes")
    if (
        isinstance(free_at_attestation, bool)
        or not isinstance(free_at_attestation, int)
        or isinstance(predicted_at_attestation, bool)
        or not isinstance(predicted_at_attestation, int)
        or predicted_at_attestation != free_at_attestation - FROZEN_PUBLIC_ARTIFACT_BYTES
        or free_at_attestation
        < FROZEN_PUBLIC_ARTIFACT_BYTES + MIN_STAGE_HEADROOM_BYTES
        or predicted_at_attestation < MIN_FINAL_FREE_BYTES
    ):
        raise GuestAttestationError("guest-attestation disk arithmetic or capacity differs")
    current_sentinel = _sentinel_record(workspace, volume_id=expected_volume_id)
    if receipt.get("volume_sentinel") != current_sentinel:
        raise GuestAttestationError("study volume sentinel changed after attestation")

    return {
        "receipt_sha256": embedded_hash,
        "attested_at_utc": receipt["attested_at_utc"],
        "owned_pod_id": expected_owned_pod_id,
        "volume_id": expected_volume_id,
        "data_center_id": expected_data_center_id,
        "artifact_root": str(WORKSPACE_ROOT),
        "repository_source_root_sha256": current_repository_source[
            "resolved_path_sha256"
        ],
        "stage_python_launch_contract": current_stage_launch,
        "current_free_bytes": current_disk["free_bytes"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owned-pod-id", required=True)
    parser.add_argument("--volume-id", required=True)
    parser.add_argument("--data-center-id", required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt_path = attest_guest(
        owned_pod_id=args.owned_pod_id,
        volume_id=args.volume_id,
        data_center_id=args.data_center_id,
        receipt_dir=args.receipt_dir,
    )
    print(str(receipt_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
