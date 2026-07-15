#!/usr/bin/env python3
"""Stdlib-only Landlock launcher for the audit-recovery process.

This module is intentionally separate from the scientific package entry point.
It installs the filesystem policy before importing project, Torch, Transformers,
or CUDA code, publishes one exclusive enforcement receipt, and then replaces
itself with the receipt-bound child via :func:`os.execve`.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import stat
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = 1
REQUIRED_LANDLOCK_ABI = 4

# ABI-4 filesystem content/topology mutation rights only. Read and execute
# remain unhandled and therefore available for the audit inputs.
LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12
LANDLOCK_ACCESS_FS_REFER = 1 << 13
LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14

HANDLED_ACCESS_FS = 0x7FF2
OUTPUT_ALLOWED_ACCESS_FS = 0x1B2
DEVICE_ALLOWED_ACCESS_FS = LANDLOCK_ACCESS_FS_WRITE_FILE
PROC_SELF_TASK_ALLOWED_ACCESS_FS = (
    LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE
)
PROC_SELF_TASK_PATH = Path("/proc/self/task")

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
PR_GET_NO_NEW_PRIVS = 39

# Linux uses the generic syscall numbering for both architectures supported by
# the frozen RunPod image family.
_SYSCALL_NUMBERS = {
    "x86_64": (444, 445, 446),
    "amd64": (444, 445, 446),
    "aarch64": (444, 445, 446),
    "arm64": (444, 445, 446),
}

_O_PATH = getattr(os, "O_PATH", 0o10000000)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_NVIDIA_DEVICE_PATH = re.compile(
    r"(?:/dev/nvidia[0-9]+|/dev/nvidiactl|/dev/nvidia-uvm|"
    r"/dev/nvidia-uvm-tools|/dev/nvidia-caps/nvidia-cap[0-9]+)"
)
_PURPOSES = ("preauthorization_probe", "audit_recovery")

_FORBIDDEN_PRECONFINEMENT_MODULE_ROOTS = frozenset(
    {"experiments", "numpy", "safetensors", "torch", "transformers"}
)
_FORBIDDEN_STARTUP_ENVIRONMENT = (
    "LD_AUDIT",
    "LD_PRELOAD",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONPLATLIBDIR",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
)
_REQUIRED_STARTUP_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C"}

RECEIPT_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "purpose",
        "pid",
        "observed_abi",
        "required_abi",
        "handled_access_fs",
        "output_allowed_access_fs",
        "no_new_privs",
        "thread_ids",
        "descriptor_audit",
        "mapping_audit",
        "directory_rules",
        "device_rules",
        "protected_checks",
        "canary_checks",
        "child_argv",
        "child_argv_sha256",
        "source_sha256",
        "receipt_path",
        "receipt_sha256",
    }
)
RECEIPT_OPTIONAL_FIELDS = frozenset(
    {"authorization_sha256", "preflight_receipt_sha256"}
)


class LandlockLaunchError(RuntimeError):
    """The requested confinement could not be proven exactly."""


def validate_startup_state() -> None:
    """Require direct, no-site, no-bytecode interpreter startup.

    The launcher must be invoked as an absolute script with
    ``python -B -E -s -S``.
    Running it as a package module would import project package initializers
    before Landlock is installed; enabling ``site`` would likewise permit a
    sitecustomize import before this source gains control.
    """

    loaded_forbidden = sorted(
        name
        for name in sys.modules
        if name.partition(".")[0] in _FORBIDDEN_PRECONFINEMENT_MODULE_ROOTS
    )
    if sys.flags.no_site != 1:
        raise LandlockLaunchError("launcher requires Python -S (no site imports)")
    if not sys.dont_write_bytecode:
        raise LandlockLaunchError("launcher requires Python -B (no bytecode writes)")
    if sys.flags.ignore_environment != 1:
        raise LandlockLaunchError("launcher requires Python -E (ignore Python env)")
    if sys.flags.no_user_site != 1:
        raise LandlockLaunchError("launcher requires Python -s (no user site)")
    if __package__ not in (None, ""):
        raise LandlockLaunchError("launcher must run by absolute script path, not -m")
    if os.environ.get("PYTHONNOUSERSITE") != "1":
        raise LandlockLaunchError("launcher requires PYTHONNOUSERSITE=1")
    present_unsafe = [
        name for name in _FORBIDDEN_STARTUP_ENVIRONMENT if name in os.environ
    ]
    incorrect_required = {
        name: os.environ.get(name)
        for name, expected in _REQUIRED_STARTUP_ENVIRONMENT.items()
        if os.environ.get(name) != expected
    }
    if present_unsafe:
        raise LandlockLaunchError(
            "unsafe launcher environment is present: " + ", ".join(present_unsafe)
        )
    if incorrect_required:
        raise LandlockLaunchError("launcher requires LANG=C and LC_ALL=C")
    if loaded_forbidden:
        raise LandlockLaunchError(
            "project or ML module loaded before confinement: "
            + ", ".join(loaded_forbidden)
        )


class _LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _LandlockPathBeneathAttr(ctypes.Structure):
    # The kernel structure is explicitly packed. For these two scalar fields,
    # ctypes' packed MS layout is the same 12-byte layout and avoids Python
    # 3.14's deprecated implicit-layout behavior; older guest Pythons ignore
    # the otherwise harmless _layout_ selector.
    _layout_ = "ms"
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's canonical JSON representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LandlockLaunchError("receipt value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(8 * 1024 * 1024):
                digest.update(block)
    except OSError as exc:
        raise LandlockLaunchError(f"could not hash file: {path}") from exc
    return digest.hexdigest()


def _require_hex64(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if _HEX64.fullmatch(value) is None:
        raise LandlockLaunchError(f"{label} is not a lowercase SHA-256")
    return value


def validate_purpose_hashes(
    purpose: str,
    authorization_sha256: str | None,
    preflight_receipt_sha256: str | None,
) -> None:
    supplied = (authorization_sha256 is not None, preflight_receipt_sha256 is not None)
    if purpose == "preauthorization_probe" and supplied != (False, False):
        raise LandlockLaunchError(
            "preauthorization probe must not carry authority hashes"
        )
    if purpose == "audit_recovery" and supplied != (True, True):
        raise LandlockLaunchError("audit recovery requires both authority hashes")


def validate_policy(
    *,
    required_abi: int = REQUIRED_LANDLOCK_ABI,
    handled_access_fs: int = HANDLED_ACCESS_FS,
    output_allowed_access_fs: int = OUTPUT_ALLOWED_ACCESS_FS,
    device_allowed_access_fs: int = DEVICE_ALLOWED_ACCESS_FS,
    proc_self_task_allowed_access_fs: int = PROC_SELF_TASK_ALLOWED_ACCESS_FS,
) -> None:
    """Fail if any frozen policy bit or ABI has drifted."""

    expected_handled = sum(
        (
            LANDLOCK_ACCESS_FS_WRITE_FILE,
            LANDLOCK_ACCESS_FS_REMOVE_DIR,
            LANDLOCK_ACCESS_FS_REMOVE_FILE,
            LANDLOCK_ACCESS_FS_MAKE_CHAR,
            LANDLOCK_ACCESS_FS_MAKE_DIR,
            LANDLOCK_ACCESS_FS_MAKE_REG,
            LANDLOCK_ACCESS_FS_MAKE_SOCK,
            LANDLOCK_ACCESS_FS_MAKE_FIFO,
            LANDLOCK_ACCESS_FS_MAKE_BLOCK,
            LANDLOCK_ACCESS_FS_MAKE_SYM,
            LANDLOCK_ACCESS_FS_REFER,
            LANDLOCK_ACCESS_FS_TRUNCATE,
        )
    )
    expected_output = sum(
        (
            LANDLOCK_ACCESS_FS_WRITE_FILE,
            LANDLOCK_ACCESS_FS_REMOVE_DIR,
            LANDLOCK_ACCESS_FS_REMOVE_FILE,
            LANDLOCK_ACCESS_FS_MAKE_DIR,
            LANDLOCK_ACCESS_FS_MAKE_REG,
        )
    )
    expected_proc_self_task = (
        LANDLOCK_ACCESS_FS_WRITE_FILE | LANDLOCK_ACCESS_FS_TRUNCATE
    )
    if (
        required_abi != 4
        or handled_access_fs != expected_handled
        or handled_access_fs != 0x7FF2
        or output_allowed_access_fs != expected_output
        or output_allowed_access_fs != 0x1B2
        or device_allowed_access_fs != LANDLOCK_ACCESS_FS_WRITE_FILE
        or device_allowed_access_fs != 0x2
        or proc_self_task_allowed_access_fs != expected_proc_self_task
        or proc_self_task_allowed_access_fs != 0x4002
        or output_allowed_access_fs & ~handled_access_fs
        or device_allowed_access_fs & ~handled_access_fs
        or proc_self_task_allowed_access_fs & ~handled_access_fs
    ):
        raise LandlockLaunchError("frozen Landlock policy differs")


def syscall_numbers(machine: str | None = None) -> tuple[int, int, int]:
    normalized = (machine or platform.machine()).lower()
    try:
        return _SYSCALL_NUMBERS[normalized]
    except KeyError as exc:
        raise LandlockLaunchError(
            f"unsupported Linux architecture for Landlock: {normalized}"
        ) from exc


def _canonical_existing(path: Path, *, kind: str) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise LandlockLaunchError(f"{kind} is missing: {lexical}") from exc
    if lexical.as_posix() != resolved.as_posix() or lexical.is_symlink():
        raise LandlockLaunchError(f"{kind} is not a canonical symlink-free path")
    return resolved


def _canonical_directory(path: Path, label: str) -> Path:
    resolved = _canonical_existing(path, kind=label)
    try:
        details = resolved.stat()
    except OSError as exc:
        raise LandlockLaunchError(f"{label} is unreadable") from exc
    if not stat.S_ISDIR(details.st_mode):
        raise LandlockLaunchError(f"{label} is not a directory")
    return resolved


def _canonical_regular_file(path: Path, label: str) -> Path:
    resolved = _canonical_existing(path, kind=label)
    try:
        details = resolved.stat()
    except OSError as exc:
        raise LandlockLaunchError(f"{label} is unreadable") from exc
    if not stat.S_ISREG(details.st_mode):
        raise LandlockLaunchError(f"{label} is not a regular file")
    return resolved


def _canonical_new_file(path: Path, *, parent: Path, label: str) -> Path:
    lexical = Path(os.path.abspath(path.expanduser()))
    if lexical.exists() or lexical.is_symlink():
        raise LandlockLaunchError(f"{label} must not already exist")
    resolved_parent = _canonical_directory(lexical.parent, f"{label} parent")
    if resolved_parent != parent or lexical.parent != parent:
        raise LandlockLaunchError(f"{label} is outside its exact output root")
    return lexical


def _contains(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_directory_layout(
    *, output_root: Path, canary_protected_root: Path, canary_output_root: Path
) -> None:
    roots = (output_root, canary_protected_root, canary_output_root)
    if len(set(roots)) != 3:
        raise LandlockLaunchError("Landlock directory roots are not distinct")
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            if _contains(left, right) or _contains(right, left):
                raise LandlockLaunchError("Landlock directory roots overlap")


def validate_protected_roots(
    protected_roots: Sequence[Path],
    *,
    output_root: Path,
    canary_output_root: Path,
) -> None:
    if not protected_roots or len(set(protected_roots)) != len(protected_roots):
        raise LandlockLaunchError("protected-root list is empty or duplicated")
    for protected_root in protected_roots:
        if (
            _contains(protected_root, output_root)
            or _contains(output_root, protected_root)
            or _contains(protected_root, canary_output_root)
            or _contains(canary_output_root, protected_root)
        ):
            raise LandlockLaunchError("protected root overlaps a writable root")


def _device_rule_record(path: Path, details: os.stat_result) -> dict[str, int | str]:
    if not path.is_absolute() or _NVIDIA_DEVICE_PATH.fullmatch(path.as_posix()) is None:
        raise LandlockLaunchError("device-file path is outside the closed NVIDIA set")
    if not stat.S_ISCHR(details.st_mode):
        raise LandlockLaunchError(f"device-file is not a character device: {path}")
    return {
        "path": path.as_posix(),
        "st_dev": int(details.st_dev),
        "st_ino": int(details.st_ino),
        "st_rdev": int(details.st_rdev),
        "major": int(os.major(details.st_rdev)),
        "minor": int(os.minor(details.st_rdev)),
        "allowed_access_fs": DEVICE_ALLOWED_ACCESS_FS,
    }


def _canonical_device(path: Path) -> tuple[Path, dict[str, int | str]]:
    resolved = _canonical_existing(path, kind="device-file")
    try:
        details = resolved.stat()
    except OSError as exc:
        raise LandlockLaunchError(f"device-file is unreadable: {resolved}") from exc
    return resolved, _device_rule_record(resolved, details)


def _snapshot_tree(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_regular_inodes: set[tuple[int, int]] = set()
    try:
        paths = sorted(root.rglob("*"), key=lambda value: value.as_posix())
    except OSError as exc:
        raise LandlockLaunchError("could not inventory protected canary") from exc
    for path in paths:
        if path.is_symlink():
            raise LandlockLaunchError("protected canary contains a symlink")
        try:
            details = path.stat()
        except OSError as exc:
            raise LandlockLaunchError("protected canary is unreadable") from exc
        relative = path.relative_to(root).as_posix()
        if stat.S_ISDIR(details.st_mode):
            rows.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(details.st_mode):
            identity = (int(details.st_dev), int(details.st_ino))
            if details.st_nlink != 1 or identity in seen_regular_inodes:
                raise LandlockLaunchError("protected canary contains a hard link")
            seen_regular_inodes.add(identity)
            rows.append(
                {
                    "path": relative,
                    "type": "regular_file",
                    "bytes": int(details.st_size),
                    "sha256": sha256_file(path),
                }
            )
        else:
            raise LandlockLaunchError("protected canary contains a special file")
    if not any(row["type"] == "regular_file" for row in rows):
        raise LandlockLaunchError("protected canary has no regular seed file")
    return rows


def _first_seed_file(root: Path, snapshot: Sequence[Mapping[str, Any]]) -> Path:
    for row in snapshot:
        if row.get("type") == "regular_file":
            return root / str(row["path"])
    raise LandlockLaunchError("protected canary seed file is absent")


def _require_empty_directory(root: Path, label: str) -> None:
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise LandlockLaunchError(f"{label} is unreadable") from exc
    if entries:
        raise LandlockLaunchError(f"{label} is not empty")


def _thread_audit() -> list[int]:
    if sys.platform != "linux":
        raise LandlockLaunchError("Landlock enforcement requires Linux")
    try:
        tids = sorted(int(name) for name in os.listdir("/proc/self/task"))
    except (OSError, ValueError) as exc:
        raise LandlockLaunchError("could not inventory process threads") from exc
    if tids != [os.getpid()]:
        raise LandlockLaunchError("launcher is not exactly single-threaded")
    return tids


def _fd_kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular_file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    return "other"


def _descriptor_audit(
    *,
    output_root: Path,
    canary_protected_root: Path,
    canary_output_root: Path,
    protected_roots: Sequence[Path],
    protected_files: Sequence[Path],
    device_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    protected_text = {path.as_posix() for path in protected_files}
    device_identities = {
        (int(row["st_dev"]), int(row["st_ino"]), int(row["st_rdev"]))
        for row in device_records
    }
    rows: list[dict[str, Any]] = []
    inventory_fd: int | None = None
    try:
        if sys.platform == "linux":
            # Hold a known procfs directory descriptor while enumerating.
            # ``os.listdir('/proc/self/fd')`` otherwise exposes its own anonymous
            # short-lived descriptor in the returned names and can close it
            # before the following ``fstat``.  The known self-created descriptor
            # is removed before auditing the inherited set.
            inventory_fd = os.open(
                "/proc/self/fd", os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC
            )
            names = os.listdir(inventory_fd)
        else:  # Unit tests exercise the pure audit logic away from Linux.
            names = os.listdir("/proc/self/fd")
        own_inventory_fd = inventory_fd
        if inventory_fd is not None:
            inventory_fd = None
            os.close(own_inventory_fd)
        fd_names = sorted(
            (
                name
                for name in names
                if name.isdigit() and int(name) != own_inventory_fd
            ),
            key=int,
        )
    except OSError as exc:
        if inventory_fd is not None:
            os.close(inventory_fd)
        raise LandlockLaunchError("could not inventory inherited descriptors") from exc
    for name in fd_names:
        fd = int(name)
        try:
            details = os.fstat(fd)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError as exc:
            # procfs enumeration itself may transiently duplicate the held
            # directory descriptor and close that duplicate before inspection.
            # In this already-proven single-threaded launcher, ENOENT/EBADF both
            # establish that the named descriptor is no longer open and thus is
            # not an inherited write escape.  Every still-open descriptor must
            # continue through the full audit below.
            if exc.errno in (errno.ENOENT, errno.EBADF):
                continue
            raise LandlockLaunchError("could not inspect inherited descriptor") from exc
        access_mode = flags & os.O_ACCMODE
        writable = access_mode in (os.O_WRONLY, os.O_RDWR)
        kind = _fd_kind(details.st_mode)
        target_path = Path(target) if target.startswith("/") else None
        target_in_output = target_path is not None and _contains(
            output_root, target_path
        )
        target_in_canary_output = target_path is not None and _contains(
            canary_output_root, target_path
        )
        target_in_canary_protected = target_path is not None and _contains(
            canary_protected_root, target_path
        )
        target_in_protected_root = target_path is not None and any(
            _contains(root, target_path) for root in protected_roots
        )
        # Standard streams are not a blanket exemption: a controller redirect
        # to a protected/GPU/canary path or to an escaping writable regular file
        # would otherwise be a pre-opened-FD bypass.
        if (
            target in protected_text
            or target_in_canary_protected
            or target_in_protected_root
        ):
            raise LandlockLaunchError("protected descriptor was inherited")
        if target_in_canary_output:
            raise LandlockLaunchError("canary-output descriptor was inherited")
        if target == "anon_inode:[io_uring]":
            raise LandlockLaunchError("io_uring descriptor was inherited")
        device_identity = (
            (
                int(details.st_dev),
                int(details.st_ino),
                int(details.st_rdev),
            )
            if kind == "character_device"
            else None
        )
        target_is_nvidia = (
            kind == "character_device"
            and target_path is not None
            and _NVIDIA_DEVICE_PATH.fullmatch(target_path.as_posix()) is not None
        )
        if kind == "character_device" and (
            device_identity in device_identities or target_is_nvidia
        ):
            raise LandlockLaunchError("GPU-device descriptor was inherited")
        if (
            fd not in (0, 1, 2)
            and writable
            and kind
            in {
                "character_device",
                "block_device",
            }
        ):
            raise LandlockLaunchError(
                "writable character/block-device descriptor was inherited"
            )
        if writable and kind in {"regular_file", "directory"}:
            raise LandlockLaunchError(
                "writable regular-file/directory descriptor was inherited"
            )
        if fd in (0, 1, 2):
            allowed_reason = "standard_stream"
        elif target_in_output:
            allowed_reason = "durable_output_root"
        elif not writable:
            allowed_reason = "read_only_descriptor"
        else:
            allowed_reason = "non_regular_non_directory_descriptor"
        rows.append(
            {
                "fd": fd,
                "target": target,
                "kind": kind,
                "access_mode": int(access_mode),
                "writable": writable,
                "allowed_reason": allowed_reason,
            }
        )
    return {
        "status": "pass_no_escaping_writable_or_protected_descriptors",
        "protected_roots": [path.as_posix() for path in protected_roots],
        "descriptor_count": len(rows),
        "descriptors": rows,
    }


def _parse_maps_line(line: str) -> dict[str, Any]:
    fields = line.rstrip("\n").split(maxsplit=5)
    if len(fields) < 5:
        raise LandlockLaunchError("/proc/self/maps row is malformed")
    address, permissions, offset, device, inode = fields[:5]
    pathname = fields[5] if len(fields) == 6 else ""
    if len(permissions) != 4:
        raise LandlockLaunchError("/proc/self/maps permissions are malformed")
    return {
        "address": address,
        "permissions": permissions,
        "offset": offset,
        "device": device,
        "inode": inode,
        "pathname": pathname,
    }


def _mapping_audit() -> dict[str, Any]:
    try:
        lines = Path("/proc/self/maps").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LandlockLaunchError("could not inventory process mappings") from exc
    forbidden: list[dict[str, Any]] = []
    for line in lines:
        row = _parse_maps_line(line)
        pathname = str(row["pathname"])
        file_backed = bool(pathname) and not pathname.startswith("[")
        permissions = str(row["permissions"])
        if file_backed and permissions[3] == "s":
            forbidden.append(row)
    if forbidden:
        raise LandlockLaunchError("shared file-backed mapping is inherited")
    return {
        "status": "pass_no_shared_file_backed_mappings",
        "mapping_count": len(lines),
        "shared_file_backed": [],
    }


def _libc() -> ctypes.CDLL:
    library = ctypes.CDLL(None, use_errno=True)
    library.syscall.restype = ctypes.c_long
    library.prctl.restype = ctypes.c_int
    return library


def _syscall(library: ctypes.CDLL, number: int, *args: Any) -> int:
    ctypes.set_errno(0)
    result = int(library.syscall(number, *args))
    if result < 0:
        supplied = ctypes.get_errno()
        raise OSError(supplied, os.strerror(supplied))
    return result


def landlock_abi() -> int:
    if sys.platform != "linux":
        raise LandlockLaunchError("Landlock enforcement requires Linux")
    create_number, _add_number, _restrict_number = syscall_numbers()
    try:
        observed = _syscall(
            _libc(),
            create_number,
            ctypes.c_void_p(),
            ctypes.c_size_t(0),
            ctypes.c_uint(LANDLOCK_CREATE_RULESET_VERSION),
        )
    except OSError as exc:
        raise LandlockLaunchError("Landlock ABI query failed") from exc
    return observed


def _open_rule_path(path: Path, expected: Mapping[str, Any] | None = None) -> int:
    flags = _O_PATH | _O_CLOEXEC | _O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        details = os.fstat(fd)
    except OSError as exc:
        raise LandlockLaunchError(f"could not open Landlock rule path: {path}") from exc
    if expected is not None and (
        int(details.st_dev) != int(expected["st_dev"])
        or int(details.st_ino) != int(expected["st_ino"])
        or int(details.st_rdev) != int(expected["st_rdev"])
        or not stat.S_ISCHR(details.st_mode)
    ):
        os.close(fd)
        raise LandlockLaunchError("device identity changed before rule installation")
    return fd


def _add_path_rule(
    library: ctypes.CDLL,
    *,
    add_rule_number: int,
    ruleset_fd: int,
    path: Path,
    allowed_access: int,
    expected: Mapping[str, Any] | None = None,
) -> None:
    path_fd = _open_rule_path(path, expected)
    try:
        attributes = _LandlockPathBeneathAttr(
            allowed_access=allowed_access,
            parent_fd=path_fd,
        )
        _syscall(
            library,
            add_rule_number,
            ctypes.c_int(ruleset_fd),
            ctypes.c_int(LANDLOCK_RULE_PATH_BENEATH),
            ctypes.byref(attributes),
            ctypes.c_uint(0),
        )
    except OSError as exc:
        raise LandlockLaunchError(f"could not add Landlock path rule: {path}") from exc
    finally:
        os.close(path_fd)


def _install_landlock(
    *,
    output_root: Path,
    canary_output_root: Path,
    device_records: Sequence[Mapping[str, Any]],
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    validate_policy()
    observed_abi = landlock_abi()
    if observed_abi < REQUIRED_LANDLOCK_ABI:
        raise LandlockLaunchError(
            f"Landlock ABI {observed_abi} is below required ABI {REQUIRED_LANDLOCK_ABI}"
        )
    create_number, add_number, restrict_number = syscall_numbers()
    library = _libc()
    attributes = _LandlockRulesetAttr(handled_access_fs=HANDLED_ACCESS_FS)
    try:
        ruleset_fd = _syscall(
            library,
            create_number,
            ctypes.byref(attributes),
            ctypes.c_size_t(ctypes.sizeof(attributes)),
            ctypes.c_uint(0),
        )
    except OSError as exc:
        raise LandlockLaunchError("could not create Landlock ruleset") from exc
    directory_rules = [
        {
            "role": "output_root",
            "path": output_root.as_posix(),
            "allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
        },
        {
            "role": "canary_output_root",
            "path": canary_output_root.as_posix(),
            "allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
        },
        {
            "role": "proc_self_task_thread_names",
            "path": PROC_SELF_TASK_PATH.as_posix(),
            "allowed_access_fs": PROC_SELF_TASK_ALLOWED_ACCESS_FS,
        },
    ]
    ordered_devices = sorted(
        (dict(row) for row in device_records), key=lambda row: str(row["path"])
    )
    try:
        for row in directory_rules:
            _add_path_rule(
                library,
                add_rule_number=add_number,
                ruleset_fd=ruleset_fd,
                path=Path(str(row["path"])),
                allowed_access=int(row["allowed_access_fs"]),
            )
        for row in ordered_devices:
            _add_path_rule(
                library,
                add_rule_number=add_number,
                ruleset_fd=ruleset_fd,
                path=Path(str(row["path"])),
                allowed_access=DEVICE_ALLOWED_ACCESS_FS,
                expected=row,
            )
        ctypes.set_errno(0)
        if library.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            supplied = ctypes.get_errno()
            raise OSError(supplied, os.strerror(supplied))
        _syscall(
            library,
            restrict_number,
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint(0),
        )
        ctypes.set_errno(0)
        no_new_privs = int(library.prctl(PR_GET_NO_NEW_PRIVS, 0, 0, 0, 0))
        if no_new_privs != 1:
            supplied = ctypes.get_errno()
            raise OSError(supplied, "no_new_privs was not retained")
    except OSError as exc:
        raise LandlockLaunchError("could not enter the frozen Landlock domain") from exc
    finally:
        os.close(ruleset_fd)
    return observed_abi, directory_rules, ordered_devices


def _denied(
    operation: str,
    action: Callable[[], Any],
    *,
    expected_errno: int = errno.EACCES,
    cleanup: Callable[[], None] | None = None,
) -> dict[str, Any]:
    try:
        result = action()
    except OSError as exc:
        if exc.errno != expected_errno:
            expected_name = errno.errorcode.get(expected_errno, str(expected_errno))
            raise LandlockLaunchError(
                f"{operation} failed with errno {exc.errno}, not {expected_name}"
            ) from exc
        return {"operation": operation, "status": "denied", "errno": expected_errno}
    else:
        if isinstance(result, int):
            try:
                os.close(result)
            except OSError:
                pass
        if cleanup is not None:
            try:
                cleanup()
            except OSError:
                pass
        raise LandlockLaunchError(f"{operation} unexpectedly succeeded")


def _protected_canary_checks(
    root: Path, snapshot: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    seed = _first_seed_file(root, snapshot)
    created = root / ".landlock-create-deny"
    created_directory = root / ".landlock-mkdir-deny"
    created_symlink = root / ".landlock-symlink-deny"
    created_link = root / ".landlock-link-deny"
    renamed = seed.with_name(seed.name + ".landlock-rename-deny")
    checks = [
        _denied(
            "protected_create",
            lambda: os.open(
                created,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC,
                0o600,
            ),
            cleanup=lambda: created.unlink(),
        ),
        _denied(
            "protected_mkdir",
            lambda: os.mkdir(created_directory, 0o700),
            cleanup=lambda: created_directory.rmdir(),
        ),
        _denied(
            "protected_symlink",
            lambda: os.symlink(seed.name, created_symlink),
            cleanup=lambda: created_symlink.unlink(),
        ),
        _denied(
            "protected_link",
            lambda: os.link(seed, created_link),
            cleanup=lambda: created_link.unlink(),
        ),
        _denied("protected_unlink", lambda: os.unlink(seed)),
        _denied("protected_rename", lambda: os.rename(seed, renamed)),
        _denied(
            "protected_truncate",
            lambda: os.open(
                seed,
                os.O_WRONLY | os.O_TRUNC | _O_CLOEXEC | _O_NOFOLLOW,
            ),
        ),
        _denied(
            "protected_open_write",
            lambda: os.open(seed, os.O_WRONLY | _O_CLOEXEC | _O_NOFOLLOW),
        ),
    ]
    return checks


def _protected_canary_writable_baseline(root: Path) -> list[dict[str, str]]:
    seed = _canonical_regular_file(root / "seed.txt", "protected canary seed")
    try:
        descriptor = os.open(seed, os.O_WRONLY | _O_CLOEXEC | _O_NOFOLLOW)
        os.close(descriptor)
        scratch = root / ".landlock-baseline-create"
        _write_new_file(scratch, b"preconfinement-writable-baseline\n")
        os.unlink(scratch)
        directory = root / ".landlock-baseline-directory"
        os.mkdir(directory, 0o700)
        os.rmdir(directory)
    except OSError as exc:
        raise LandlockLaunchError(
            "protected canary is not writable before policy"
        ) from exc
    return [
        {"operation": "baseline_seed_open_write_no_write", "status": "allowed"},
        {"operation": "baseline_create_unlink", "status": "allowed"},
        {"operation": "baseline_mkdir_rmdir", "status": "allowed"},
    ]


def _write_new_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise LandlockLaunchError("short write during canary check")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _output_canary_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    first = root / ".landlock-allowed-create"
    renamed = root / ".landlock-allowed-renamed"
    _write_new_file(first, b"landlock-output-allow\n")
    os.rename(first, renamed)
    os.unlink(renamed)
    checks.extend(
        [
            {"operation": "output_create_write_fsync", "status": "allowed"},
            {"operation": "output_same_directory_rename", "status": "allowed"},
            {"operation": "output_unlink", "status": "allowed"},
        ]
    )

    allowed_directory = root / ".landlock-allowed-directory"
    os.mkdir(allowed_directory, 0o700)
    os.rmdir(allowed_directory)
    checks.extend(
        [
            {"operation": "output_mkdir", "status": "allowed"},
            {"operation": "output_rmdir", "status": "allowed"},
        ]
    )

    truncate_path = root / ".landlock-deny-truncate"
    truncate_payload = b"must-not-truncate\n"
    _write_new_file(truncate_path, truncate_payload)
    checks.append(
        _denied(
            "output_truncate",
            lambda: os.open(
                truncate_path,
                os.O_WRONLY | os.O_TRUNC | _O_CLOEXEC | _O_NOFOLLOW,
            ),
        )
    )
    if truncate_path.read_bytes() != truncate_payload:
        raise LandlockLaunchError("denied output truncate changed bytes")
    os.unlink(truncate_path)

    symlink_path = root / ".landlock-deny-symlink"
    checks.append(
        _denied(
            "output_symlink",
            lambda: os.symlink("relative-target", symlink_path),
            cleanup=lambda: symlink_path.unlink(),
        )
    )
    fifo_path = root / ".landlock-deny-fifo"
    checks.append(
        _denied(
            "output_fifo",
            lambda: os.mkfifo(fifo_path, 0o600),
            cleanup=lambda: fifo_path.unlink(),
        )
    )

    socket_path = root / ".landlock-deny-socket"
    unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        checks.append(
            _denied(
                "output_unix_socket",
                lambda: unix_socket.bind(socket_path.as_posix()),
                cleanup=lambda: socket_path.unlink(),
            )
        )
    finally:
        unix_socket.close()

    source = root / ".landlock-cross-source"
    destination_directory = root / ".landlock-cross-directory"
    destination = destination_directory / "linked"
    _write_new_file(source, b"cross-directory-link\n")
    os.mkdir(destination_directory, 0o700)
    checks.append(
        _denied(
            "output_cross_directory_link",
            lambda: os.link(source, destination),
            expected_errno=errno.EXDEV,
            cleanup=lambda: destination.unlink(),
        )
    )
    os.unlink(source)
    os.rmdir(destination_directory)
    return checks


def _real_protected_checks(paths: Sequence[Path]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for path in paths:
        result = _denied(
            "protected_file_open_write_no_write",
            lambda path=path: os.open(path, os.O_WRONLY | _O_CLOEXEC | _O_NOFOLLOW),
        )
        checks.append({"path": path.as_posix(), **result})
    return checks


def seal_receipt(core: Mapping[str, Any]) -> dict[str, Any]:
    if "receipt_sha256" in core:
        raise LandlockLaunchError("receipt core already contains a self-hash")
    value = dict(core)
    return {**value, "receipt_sha256": canonical_sha256(value)}


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(value)
    fields = set(receipt)
    optional = fields & RECEIPT_OPTIONAL_FIELDS
    if fields != set(RECEIPT_REQUIRED_FIELDS | optional):
        raise LandlockLaunchError("Landlock receipt field inventory differs")
    core = dict(receipt)
    supplied = core.pop("receipt_sha256", None)
    if _require_hex64(supplied, "receipt_sha256") != canonical_sha256(core):
        raise LandlockLaunchError("Landlock receipt self-hash differs")
    for name in optional:
        _require_hex64(str(receipt[name]), name)
    validate_purpose_hashes(
        str(receipt.get("purpose")),
        receipt.get("authorization_sha256"),
        receipt.get("preflight_receipt_sha256"),
    )
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("status") != "pass_landlock_enforced"
        or receipt.get("purpose") not in _PURPOSES
        or receipt.get("required_abi") != REQUIRED_LANDLOCK_ABI
        or not isinstance(receipt.get("observed_abi"), int)
        or isinstance(receipt.get("observed_abi"), bool)
        or int(receipt["observed_abi"]) < REQUIRED_LANDLOCK_ABI
        or receipt.get("handled_access_fs") != HANDLED_ACCESS_FS
        or receipt.get("output_allowed_access_fs") != OUTPUT_ALLOWED_ACCESS_FS
        or receipt.get("no_new_privs") is not True
        or _require_hex64(str(receipt.get("child_argv_sha256")), "child_argv_sha256")
        != canonical_sha256(receipt.get("child_argv"))
        or _require_hex64(str(receipt.get("source_sha256")), "source_sha256") is None
    ):
        raise LandlockLaunchError("Landlock receipt identity differs")
    directories = receipt.get("directory_rules")
    expected_directory_roles = (
        ("output_root", OUTPUT_ALLOWED_ACCESS_FS),
        ("canary_output_root", OUTPUT_ALLOWED_ACCESS_FS),
        ("proc_self_task_thread_names", PROC_SELF_TASK_ALLOWED_ACCESS_FS),
    )
    if not isinstance(directories, list) or len(directories) != len(
        expected_directory_roles
    ):
        raise LandlockLaunchError("Landlock directory-rule receipt differs")
    for row, (role, allowed_access_fs) in zip(
        directories, expected_directory_roles, strict=True
    ):
        if (
            not isinstance(row, Mapping)
            or set(row) != {"role", "path", "allowed_access_fs"}
            or row.get("role") != role
            or row.get("allowed_access_fs") != allowed_access_fs
            or (
                role == "proc_self_task_thread_names"
                and row.get("path") != PROC_SELF_TASK_PATH.as_posix()
            )
        ):
            raise LandlockLaunchError("Landlock directory-rule receipt differs")
    devices = receipt.get("device_rules")
    expected_device_fields = {
        "path",
        "st_dev",
        "st_ino",
        "st_rdev",
        "major",
        "minor",
        "allowed_access_fs",
    }
    if (
        not isinstance(devices, list)
        or not devices
        or any(
            not isinstance(row, Mapping)
            or set(row) != expected_device_fields
            or row.get("allowed_access_fs") != DEVICE_ALLOWED_ACCESS_FS
            for row in devices
        )
        or [str(row["path"]) for row in devices]
        != sorted(str(row["path"]) for row in devices)
    ):
        raise LandlockLaunchError("Landlock device-rule receipt differs")
    return receipt


def _write_receipt_exclusive(path: Path, receipt: Mapping[str, Any]) -> bytes:
    validated = validate_receipt(receipt)
    payload = canonical_json_bytes(validated) + b"\n"
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC,
            0o600,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise LandlockLaunchError("short write publishing Landlock receipt")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory_fd = os.open(path.parent, os.O_RDONLY | _O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise LandlockLaunchError(
            "exclusive Landlock receipt publication failed"
        ) from exc
    return payload


def _normalize_child_argv(values: Sequence[str]) -> list[str]:
    child = list(values)
    if child and child[0] == "--":
        child = child[1:]
    if not child or not child[0]:
        raise LandlockLaunchError("a child command after -- is required")
    executable = child[0]
    if not os.path.isabs(executable):
        executable = shutil.which(executable) or ""
    if not executable:
        raise LandlockLaunchError("child executable could not be resolved")
    resolved = _canonical_regular_file(Path(executable), "child executable")
    if not os.access(resolved, os.X_OK):
        raise LandlockLaunchError("child executable is not executable")
    child[0] = resolved.as_posix()
    return child


def _normalized_inputs(args: argparse.Namespace) -> dict[str, Any]:
    validate_policy()
    output_root = _canonical_directory(args.output_root, "output root")
    canary_protected_root = _canonical_directory(
        args.canary_protected_root, "protected canary root"
    )
    canary_output_root = _canonical_directory(
        args.canary_output_root, "output canary root"
    )
    validate_directory_layout(
        output_root=output_root,
        canary_protected_root=canary_protected_root,
        canary_output_root=canary_output_root,
    )
    receipt = _canonical_new_file(
        args.receipt, parent=output_root, label="Landlock receipt"
    )
    _require_empty_directory(output_root, "output root")
    _require_empty_directory(canary_output_root, "output canary root")
    protected_files = sorted(
        (
            _canonical_regular_file(path, "protected file")
            for path in args.protected_file
        ),
        key=lambda path: path.as_posix(),
    )
    if not protected_files or len(set(protected_files)) != len(protected_files):
        raise LandlockLaunchError("protected-file list is empty or duplicated")
    for path in protected_files:
        if _contains(output_root, path) or _contains(canary_output_root, path):
            raise LandlockLaunchError("protected file is inside a writable root")
    protected_roots = [
        _canonical_directory(path, "protected root") for path in args.protected_root
    ]
    if canary_protected_root not in protected_roots:
        protected_roots.append(canary_protected_root)
    protected_roots = sorted(set(protected_roots), key=lambda path: path.as_posix())
    validate_protected_roots(
        protected_roots,
        output_root=output_root,
        canary_output_root=canary_output_root,
    )
    device_pairs = [_canonical_device(path) for path in args.device_file]
    device_paths = [path for path, _record in device_pairs]
    if not device_paths or len(set(device_paths)) != len(device_paths):
        raise LandlockLaunchError("device-file list is empty or duplicated")
    device_records = [record for _path, record in device_pairs]
    source_path = _canonical_regular_file(Path(__file__), "launcher source")
    source_sha256 = sha256_file(source_path)
    supplied_source = _require_hex64(args.source_sha256, "source_sha256")
    if supplied_source is not None and supplied_source != source_sha256:
        raise LandlockLaunchError("launcher source hash differs")
    authorization_sha256 = _require_hex64(
        args.authorization_sha256, "authorization_sha256"
    )
    preflight_receipt_sha256 = _require_hex64(
        args.preflight_receipt_sha256, "preflight_receipt_sha256"
    )
    validate_purpose_hashes(
        args.purpose, authorization_sha256, preflight_receipt_sha256
    )
    child_argv = _normalize_child_argv(args.child_argv)
    return {
        "output_root": output_root,
        "canary_protected_root": canary_protected_root,
        "canary_output_root": canary_output_root,
        "receipt": receipt,
        "protected_files": protected_files,
        "protected_roots": protected_roots,
        "device_records": device_records,
        "source_sha256": source_sha256,
        "authorization_sha256": authorization_sha256,
        "preflight_receipt_sha256": preflight_receipt_sha256,
        "child_argv": child_argv,
    }


def launch(args: argparse.Namespace) -> None:
    """Install the policy, publish its receipt, and exec the child in-place."""

    validate_startup_state()
    values = _normalized_inputs(args)
    writable_baseline = _protected_canary_writable_baseline(
        values["canary_protected_root"]
    )
    protected_snapshot = _snapshot_tree(values["canary_protected_root"])
    protected_snapshot_sha256 = canonical_sha256(protected_snapshot)
    thread_ids = _thread_audit()
    descriptor_audit = _descriptor_audit(
        output_root=values["output_root"],
        canary_protected_root=values["canary_protected_root"],
        canary_output_root=values["canary_output_root"],
        protected_roots=values["protected_roots"],
        protected_files=values["protected_files"],
        device_records=values["device_records"],
    )
    mapping_audit = _mapping_audit()
    observed_abi, directory_rules, device_rules = _install_landlock(
        output_root=values["output_root"],
        canary_output_root=values["canary_output_root"],
        device_records=values["device_records"],
    )
    # Re-resolve every device after restriction. Metadata reads are unhandled;
    # any identity drift invalidates the receipt before publication.
    for expected in device_rules:
        _path, observed = _canonical_device(Path(str(expected["path"])))
        if observed != expected:
            raise LandlockLaunchError("device identity changed after confinement")

    protected_canary = _protected_canary_checks(
        values["canary_protected_root"], protected_snapshot
    )
    output_canary = _output_canary_checks(values["canary_output_root"])
    protected_checks = _real_protected_checks(values["protected_files"])
    protected_after = _snapshot_tree(values["canary_protected_root"])
    if protected_after != protected_snapshot:
        raise LandlockLaunchError("protected canary bytes or topology changed")
    _require_empty_directory(values["canary_output_root"], "output canary root")
    canary_checks = {
        "status": "pass_protected_unchanged_output_empty",
        "protected_inventory_sha256_before": protected_snapshot_sha256,
        "protected_inventory_sha256_after": canonical_sha256(protected_after),
        "protected_unchanged": True,
        "output_empty_before": True,
        "output_empty_after": True,
        "preconfinement_writable_baseline": writable_baseline,
        "protected_operations": protected_canary,
        "output_operations": output_canary,
    }
    child_argv = values["child_argv"]
    core: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass_landlock_enforced",
        "purpose": args.purpose,
        "pid": os.getpid(),
        "observed_abi": observed_abi,
        "required_abi": REQUIRED_LANDLOCK_ABI,
        "handled_access_fs": HANDLED_ACCESS_FS,
        "output_allowed_access_fs": OUTPUT_ALLOWED_ACCESS_FS,
        "no_new_privs": True,
        "thread_ids": thread_ids,
        "descriptor_audit": descriptor_audit,
        "mapping_audit": mapping_audit,
        "directory_rules": directory_rules,
        "device_rules": device_rules,
        "protected_checks": protected_checks,
        "canary_checks": canary_checks,
        "child_argv": child_argv,
        "child_argv_sha256": canonical_sha256(child_argv),
        "source_sha256": values["source_sha256"],
        "receipt_path": values["receipt"].as_posix(),
    }
    if values["authorization_sha256"] is not None:
        core["authorization_sha256"] = values["authorization_sha256"]
    if values["preflight_receipt_sha256"] is not None:
        core["preflight_receipt_sha256"] = values["preflight_receipt_sha256"]
    receipt = seal_receipt(core)
    payload = _write_receipt_exclusive(values["receipt"], receipt)
    # This is the only launcher output. It lets the controller compare the
    # locally captured bytes with the confined on-disk receipt.
    try:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except (AttributeError, BrokenPipeError, OSError) as exc:
        raise LandlockLaunchError(
            "Landlock receipt was published but stdout attestation failed"
        ) from exc
    os.execve(child_argv[0], child_argv, dict(os.environ))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", choices=_PURPOSES, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--canary-protected-root", type=Path, required=True)
    parser.add_argument("--canary-output-root", type=Path, required=True)
    parser.add_argument("--protected-root", type=Path, action="append", required=True)
    parser.add_argument("--protected-file", type=Path, action="append", required=True)
    parser.add_argument("--device-file", type=Path, action="append", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-sha256")
    parser.add_argument("--authorization-sha256")
    parser.add_argument("--preflight-receipt-sha256")
    parser.add_argument("child_argv", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    validate_startup_state()
    args = build_parser().parse_args(argv)
    try:
        launch(args)
    except LandlockLaunchError as exc:
        print(f"landlock launcher failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            f"landlock launcher failed after policy setup: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3
    return 0  # os.execve does not return on success.


if __name__ == "__main__":
    raise SystemExit(main())
