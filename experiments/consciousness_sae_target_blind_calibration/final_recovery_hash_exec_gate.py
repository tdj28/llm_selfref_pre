#!/usr/bin/env python3
"""Fail-closed hash-and-exec gate for the generic F14 recovery controller.

This program is intentionally delivered to ``/usr/bin/python3.11 -B -`` on
standard input by the local supervisor.  The supervisor separately binds the
SHA-256 of this source file.  This gate then binds the exact reviewed
controller bytes, the fresh lifecycle ownership receipt, the new namespace,
and the exact controller argv before replacing itself with the controller.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
PROTOCOL_VERSION = "final_recovery_hash_exec_gate_v1.1.0"
EXPECTED_CONTROLLER_PATH = Path("/root/final_recovery_controller_f11.sh")
EXPECTED_CONTROLLER_SHA256 = (
    "ca9d6606b992507dd9e76afbb9fc219222c858831c93a385de22ac56d4b80006"
)
REJECTED_CONTROLLER_SHA256 = frozenset(
    {
        "1a1baa67fa9c12b8af309581ff85d1e200af907b80cd0b8185eb8f9a68cd08cc",
        "6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c",
        "a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2",
    }
)
REJECTED_POD_IDS = frozenset(
    {"9n5f5a82p1gw1e", "eeo1skjkwjqot5", "j7xr357tdlpq3f"}
)
REJECTED_ATTEMPT_IDS = frozenset(
    {
        "calv2-r3-audit-recovery-2479ed0-20260715T155035Z",
        "calv2-r3-audit-recovery-2479ed0-20260715T165648Z",
        "calv2-r3-audit-recovery-497b0f8-20260715T191757Z",
    }
)
REJECTED_OWNERSHIP_RECEIPT_SHA256 = frozenset(
    {
        "b7563a26c01646a68cb7618107b17743f38b14c87bc6bbf306e87a852a40ab2f",
        "54e0f4754b1dfd0a009da42ccae287d447cb6acbcd4d7394f3c149fbcac176b2",
        "6eb967c18c93cb008f273c507364b7610b3ca811d869cf275db9d594cd6f7e45",
    }
)
REJECTED_AUTHORIZATION_RECEIPT_SHA256 = frozenset(
    {
        "f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358",
        "8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4",
    }
)
REJECTED_AUTHORIZATION_FILE_SHA256 = frozenset(
    {
        "897a0fe5fac8e898f6367b8115a982a7580c0224843a76e2514589f6277274a7",
        "682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff",
    }
)
EXPECTED_NETWORK_VOLUME_ID = "bv9gb9j32y"
EXPECTED_DATA_CENTER_ID = "US-CA-2"
EXPECTED_GPU_TYPE = "NVIDIA B200"
EXPECTED_GPU_COUNT = 1
EXPECTED_OWNERSHIP_STATUS = "owned_running_isolated"
CLEAN_EXEC_ENV = {
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
EXPECTED_GATE_FLAGS = {
    "dont_write_bytecode": 1,
    "ignore_environment": 1,
    "isolated": 1,
    "no_site": 1,
    "no_user_site": 1,
    "safe_path": True,
}
CONTROLLER_EXEC_METHOD = "path_execve_after_second_open_full_stat_and_sha256"
CONTROLLER_EXEC_THREAT_BOUNDARY = (
    "single_trusted_root_host; second open/full-stat/SHA-256 binds the canonical "
    "root-owned non-group/other-writable path immediately before pathname execve; "
    "a hostile concurrent root could still replace or rewrite it after the final check"
)
MAX_FRESH_AGE = dt.timedelta(hours=6)
MAX_FUTURE_SKEW = dt.timedelta(minutes=5)
POD_RE = re.compile(r"[a-z0-9]{6,32}\Z")
ATTEMPT_RE = re.compile(
    r"calv2-r3-audit-recovery-([0-9a-f]{7})-([0-9]{8}T[0-9]{6}Z)\Z"
)
CREATED_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
INPUT_ROOT_RE = re.compile(r"/root/final-recovery-inputs-[A-Za-z0-9._-]+\Z")


class GateError(RuntimeError):
    """A fail-closed launch-gate rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise GateError(f"non-finite JSON number: {value}")


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"invalid JSON in {label}: {exc}") from exc
    _require(type(value) is dict, f"JSON root is not an object: {label}")
    return value


def _parse_utc(value: str, label: str) -> dt.datetime:
    _require(type(value) is str and CREATED_RE.fullmatch(value) is not None, f"invalid {label}")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise GateError(f"invalid {label}") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _sha256_fd(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _stat_binding(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _stat_record(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": stat.S_IMODE(info.st_mode),
        "nlink": info.st_nlink,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "bytes": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def _open_bound_controller(path: Path) -> tuple[int, os.stat_result, str]:
    _require(path == EXPECTED_CONTROLLER_PATH, "controller path differs")
    _require(path.is_absolute(), "controller path is not absolute")
    try:
        resolved = path.resolve(strict=True)
        link_info = path.lstat()
    except OSError as exc:
        raise GateError(f"controller path inspection failed: {exc}") from exc
    _require(resolved == path, "controller path is not canonical")
    _require(not stat.S_ISLNK(link_info.st_mode), "controller is a symbolic link")
    _require(stat.S_ISREG(link_info.st_mode), "controller is not a regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GateError(f"controller open failed: {exc}") from exc
    try:
        info = os.fstat(fd)
        _require(_stat_binding(info) == _stat_binding(link_info), "controller changed during open")
        _require(stat.S_ISREG(info.st_mode), "opened controller is not regular")
        _require(info.st_nlink == 1, "controller link count is not one")
        _require(info.st_uid == os.geteuid(), "controller owner differs from effective user")
        _require(info.st_mode & stat.S_IXUSR != 0, "controller is not owner-executable")
        _require(info.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0, "controller is group/other writable")
        observed_sha256 = _sha256_fd(fd)
        _require(
            observed_sha256 not in REJECTED_CONTROLLER_SHA256,
            "explicitly rejected superseded controller SHA-256",
        )
        _require(observed_sha256 == EXPECTED_CONTROLLER_SHA256, "controller SHA-256 differs")
        return fd, info, observed_sha256
    except BaseException:
        os.close(fd)
        raise


def _inspect_regular_file(path: Path, label: str) -> os.stat_result:
    try:
        resolved = path.resolve(strict=True)
        info = path.lstat()
    except OSError as exc:
        raise GateError(f"{label} inspection failed: {exc}") from exc
    _require(resolved == path, f"{label} path is not canonical")
    _require(not stat.S_ISLNK(info.st_mode), f"{label} is a symbolic link")
    _require(stat.S_ISREG(info.st_mode), f"{label} is not a regular file")
    _require(info.st_nlink == 1, f"{label} link count is not one")
    return info


def _validate_ownership(
    path: Path,
    *,
    pod_id: str,
    created_at: str,
    now: dt.datetime,
) -> dict[str, Any]:
    info = _inspect_regular_file(path, "ownership receipt")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise GateError(f"ownership receipt open failed: {exc}") from exc
    try:
        opened_info = os.fstat(fd)
        _require(_stat_binding(opened_info) == _stat_binding(info), "ownership receipt changed during open")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            _require(total <= 16 * 1024 * 1024, "ownership receipt is unexpectedly large")
            chunks.append(chunk)
        final_info = os.fstat(fd)
        _require(_stat_binding(final_info) == _stat_binding(info), "ownership receipt changed during read")
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    receipt = _decode_json_object(raw, path.as_posix())
    _require(raw in (_canonical_bytes(receipt), _canonical_bytes(receipt) + b"\n"), "ownership receipt is not canonical JSON")
    _require(type(receipt.get("receipt_sha256")) is str, "ownership receipt SHA-256 is missing")
    claimed = receipt["receipt_sha256"]
    _require(SHA256_RE.fullmatch(claimed) is not None, "ownership receipt SHA-256 is malformed")
    core = dict(receipt)
    core.pop("receipt_sha256")
    _require(_canonical_sha256(core) == claimed, "ownership receipt self-hash differs")
    _require(claimed not in REJECTED_OWNERSHIP_RECEIPT_SHA256, "rejected failed-attempt ownership receipt")
    expected_fields = {
        "pod_id": pod_id,
        "created_at": created_at,
        "network_volume_id": EXPECTED_NETWORK_VOLUME_ID,
        "data_center_id": EXPECTED_DATA_CENTER_ID,
        "gpu_type": EXPECTED_GPU_TYPE,
        "gpu_count": EXPECTED_GPU_COUNT,
        "status": EXPECTED_OWNERSHIP_STATUS,
    }
    for key, expected in expected_fields.items():
        _require(type(receipt.get(key)) is type(expected) and receipt.get(key) == expected, f"ownership field differs: {key}")
    _require(receipt["pod_id"] not in REJECTED_POD_IDS, "rejected failed-attempt pod id")
    _require(type(receipt.get("locked")) is bool and receipt["locked"] is False, "ownership lock state differs")
    _require(type(receipt.get("precreate_unrelated_pod_count")) is int, "ownership unrelated-pod count is invalid")
    _require(receipt["precreate_unrelated_pod_count"] >= 0, "ownership unrelated-pod count is negative")
    _require(
        type(receipt.get("precreate_unrelated_inventory_sha256")) is str
        and SHA256_RE.fullmatch(receipt["precreate_unrelated_inventory_sha256"]) is not None,
        "ownership unrelated-inventory SHA-256 is invalid",
    )
    created = _parse_utc(receipt["created_at"], "ownership created_at")
    age = now - created
    _require(age >= -MAX_FUTURE_SKEW, "ownership receipt is too far in the future")
    _require(age <= MAX_FRESH_AGE, "ownership receipt is stale")
    terminate_after = _parse_utc(receipt.get("terminate_after"), "ownership terminate_after")
    _require(terminate_after > now, "ownership receipt has expired")
    _require(terminate_after > created, "ownership termination time is not after creation")
    return {
        "receipt_sha256": claimed,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "stat": _stat_record(info),
        "terminate_after": receipt["terminate_after"],
    }


def _absence_paths(attempt_id: str) -> list[Path]:
    base = Path("/root/consciousness_sae_audit_recovery") / attempt_id
    attempt = Path("/workspace/csae") / attempt_id
    output = attempt / "output"
    return [
        base,
        attempt,
        attempt / "RECOVERY_AUTHORIZATION.json",
        output,
        output / "ATTEMPT_STARTED.json",
        output / "FAILURE.json",
        output / "compact" / "CALIBRATION_AUDIT.json",
        output / "compact" / "CALIBRATION_SUMMARY.json",
        output / "compact" / "PUBLICATION_COMPLETE.json",
    ]


def _validate_input_root(path: Path, rejected_values: tuple[str, ...]) -> None:
    value = path.as_posix()
    _require(path.is_absolute(), "input root is not absolute")
    _require(INPUT_ROOT_RE.fullmatch(value) is not None, "input root naming differs")
    for rejected in rejected_values:
        _require(rejected not in value, "input root contains a rejected failed-attempt identifier")
    try:
        resolved = path.resolve(strict=True)
        info = path.lstat()
    except OSError as exc:
        raise GateError(f"input root inspection failed: {exc}") from exc
    _require(resolved == path, "input root path is not canonical")
    _require(not stat.S_ISLNK(info.st_mode), "input root is a symbolic link")
    _require(stat.S_ISDIR(info.st_mode), "input root is not a directory")


def _write_receipt_exclusive(path: Path, core: dict[str, Any]) -> tuple[str, bytes]:
    _require(path.is_absolute(), "launch receipt path is not absolute")
    _require(path.parent.resolve(strict=True) == path.parent, "launch receipt parent is not canonical")
    receipt_sha256 = _canonical_sha256(core)
    receipt = dict(core)
    receipt["receipt_sha256"] = receipt_sha256
    payload = _canonical_bytes(receipt) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise GateError(f"exclusive launch receipt creation failed: {exc}") from exc
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise GateError("short launch receipt write")
            view = view[written:]
        os.fsync(fd)
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "launch receipt stat differs")
    finally:
        os.close(fd)
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(path.parent, directory_flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return receipt_sha256, payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bind and exec the exact reviewed generic F14 recovery controller",
        allow_abbrev=False,
    )
    parser.add_argument("--code-freeze", required=True)
    parser.add_argument("--reviewed-packet-commit", required=True)
    parser.add_argument("--final-freeze", required=True)
    parser.add_argument("--pod-id", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--gate-source-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _require(sys.argv[0] == "-", "gate source was not delivered on Python stdin")
    _require(sys.version_info[:2] == (3, 11), "gate requires Python 3.11")
    try:
        exact_python = os.path.samefile(sys.executable, "/usr/bin/python3.11")
    except OSError as exc:
        raise GateError(f"Python executable inspection failed: {exc}") from exc
    _require(exact_python, "Python executable differs from /usr/bin/python3.11")
    observed_gate_flags = {
        "dont_write_bytecode": sys.flags.dont_write_bytecode,
        "ignore_environment": sys.flags.ignore_environment,
        "isolated": sys.flags.isolated,
        "no_site": sys.flags.no_site,
        "no_user_site": sys.flags.no_user_site,
        "safe_path": sys.flags.safe_path,
    }
    _require(observed_gate_flags == EXPECTED_GATE_FLAGS, "Python isolation flags differ")
    observed_gate_env = dict(os.environ)
    _require(observed_gate_env == CLEAN_EXEC_ENV, "gate process environment is not exact-clean")
    observed_gate_sys_path = list(sys.path)
    _require(observed_gate_sys_path, "isolated Python sys.path is empty")
    cwd = Path.cwd().resolve(strict=True).as_posix()
    for entry in observed_gate_sys_path:
        _require(type(entry) is str and entry.startswith("/"), "isolated Python sys.path entry is not absolute")
        _require(entry not in ("", ".", cwd), "isolated Python sys.path includes the working directory")
        _require(
            "site-packages" not in entry and "dist-packages" not in entry,
            "isolated Python sys.path includes a package installation root",
        )
    commits = (
        args.code_freeze,
        args.reviewed_packet_commit,
        args.final_freeze,
    )
    _require(
        all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) for value in commits),
        "runtime commit binding is malformed",
    )
    _require(POD_RE.fullmatch(args.pod_id) is not None, "pod id is malformed")
    _require(args.pod_id not in REJECTED_POD_IDS, "rejected failed-attempt pod id")
    _require(CREATED_RE.fullmatch(args.created_at) is not None, "provider-created timestamp is malformed")
    attempt_match = ATTEMPT_RE.fullmatch(args.attempt_id)
    _require(attempt_match is not None, "attempt id is malformed")
    _require(args.attempt_id not in REJECTED_ATTEMPT_IDS, "rejected failed-attempt id")
    _require(
        attempt_match.group(1) == args.final_freeze[:7],
        "attempt id does not bind the final-freeze short commit",
    )
    _require(SHA256_RE.fullmatch(args.gate_source_sha256) is not None, "gate source SHA-256 is malformed")

    now = dt.datetime.now(dt.timezone.utc)
    created = _parse_utc(args.created_at, "provider-created timestamp")
    attempt_time = dt.datetime.strptime(attempt_match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
    for value, label in ((created, "provider-created timestamp"), (attempt_time, "attempt id")):
        age = now - value
        _require(age >= -MAX_FUTURE_SKEW, f"{label} is too far in the future")
        _require(age <= MAX_FRESH_AGE, f"{label} is stale")
    _require(abs(attempt_time - created) <= MAX_FRESH_AGE, "attempt and pod creation times are not contemporaneous")

    input_root = Path(args.input_root)
    _validate_input_root(
        input_root,
        tuple(sorted(REJECTED_POD_IDS | REJECTED_ATTEMPT_IDS)),
    )
    ownership_path = input_root / "fresh" / "OWNERSHIP.json"
    ownership = _validate_ownership(
        ownership_path,
        pod_id=args.pod_id,
        created_at=args.created_at,
        now=now,
    )

    absence_paths = _absence_paths(args.attempt_id)
    for path in absence_paths:
        _require(not os.path.lexists(path), f"new recovery namespace is not absent: {path}")

    launch_receipt_path = Path(f"/root/final-recovery-launch-gate-{args.pod_id}.json")
    _require(not os.path.lexists(launch_receipt_path), "launch receipt already exists")

    controller_fd, controller_info, controller_sha256 = _open_bound_controller(
        EXPECTED_CONTROLLER_PATH
    )
    try:
        controller_argv = [
            EXPECTED_CONTROLLER_PATH.as_posix(),
            args.code_freeze,
            args.reviewed_packet_commit,
            args.final_freeze,
            args.pod_id,
            args.created_at,
            args.attempt_id,
            input_root.as_posix(),
        ]
        controller_argv_sha256 = _canonical_sha256(controller_argv)
        controller_exec_environment = dict(CLEAN_EXEC_ENV)
        controller_exec_environment_sha256 = _canonical_sha256(
            controller_exec_environment
        )
        core: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "status": "launch_gate_prepared_for_immediate_exec",
            "recorded_at": now.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gate_delivery": "python3.11_-I_-S_-B_stdin_external_source_sha256_binding",
            "gate_source_sha256": args.gate_source_sha256,
            "gate_python_executable": "/usr/bin/python3.11",
            "gate_python_flags": observed_gate_flags,
            "gate_sys_path": observed_gate_sys_path,
            "gate_process_environment": observed_gate_env,
            "gate_process_environment_sha256": _canonical_sha256(observed_gate_env),
            "code_freeze_commit": args.code_freeze,
            "reviewed_packet_git_head_commit": args.reviewed_packet_commit,
            "final_freeze_commit": args.final_freeze,
            "pod_id": args.pod_id,
            "provider_created_at": args.created_at,
            "attempt_id": args.attempt_id,
            "input_root": input_root.as_posix(),
            "ownership_receipt_path": ownership_path.as_posix(),
            "ownership_receipt_sha256": ownership["receipt_sha256"],
            "ownership_file_sha256": ownership["file_sha256"],
            "ownership_stat": ownership["stat"],
            "ownership_terminate_after": ownership["terminate_after"],
            "controller_path": EXPECTED_CONTROLLER_PATH.as_posix(),
            "controller_sha256": controller_sha256,
            "rejected_controller_sha256": sorted(REJECTED_CONTROLLER_SHA256),
            "controller_stat": _stat_record(controller_info),
            "controller_argv": controller_argv,
            "controller_argv_sha256": controller_argv_sha256,
            "controller_exec_environment": controller_exec_environment,
            "controller_exec_environment_sha256": controller_exec_environment_sha256,
            "controller_exec_method": CONTROLLER_EXEC_METHOD,
            "controller_exec_threat_boundary": CONTROLLER_EXEC_THREAT_BOUNDARY,
            "absence_checks": [
                {"path": path.as_posix(), "status": "absent"}
                for path in absence_paths
            ],
            "rejected_pod_ids": sorted(REJECTED_POD_IDS),
            "rejected_attempt_ids": sorted(REJECTED_ATTEMPT_IDS),
            "rejected_authorization_receipt_sha256": sorted(
                REJECTED_AUTHORIZATION_RECEIPT_SHA256
            ),
            "rejected_authorization_file_sha256": sorted(
                REJECTED_AUTHORIZATION_FILE_SHA256
            ),
            "launch_receipt_path": launch_receipt_path.as_posix(),
        }
        receipt_sha256, _ = _write_receipt_exclusive(launch_receipt_path, core)

        # Open the pathname again only after the durable receipt exists.  Bind
        # the second descriptor, complete stat tuple, and bytes to the first
        # observation, then immediately emit the marker and exec the pathname.
        final_fd, final_info, final_sha256 = _open_bound_controller(
            EXPECTED_CONTROLLER_PATH
        )
        try:
            _require(
                _stat_binding(final_info) == _stat_binding(controller_info),
                "controller stat changed before exec",
            )
            _require(final_sha256 == controller_sha256, "controller bytes changed before exec")
            marker = (
                "FINAL_RECOVERY_LAUNCH_GATE_BOUND "
                f"receipt_sha256={receipt_sha256} "
                f"controller_sha256={final_sha256} "
                f"argv_sha256={controller_argv_sha256} "
                f"env_sha256={controller_exec_environment_sha256}"
            )
            print(marker, flush=True)
            os.execve(
                EXPECTED_CONTROLLER_PATH.as_posix(),
                controller_argv,
                controller_exec_environment,
            )
        finally:
            os.close(final_fd)
    finally:
        os.close(controller_fd)
    raise AssertionError("os.execve unexpectedly returned")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        print(f"FINAL_RECOVERY_LAUNCH_GATE_REJECTED: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2)
