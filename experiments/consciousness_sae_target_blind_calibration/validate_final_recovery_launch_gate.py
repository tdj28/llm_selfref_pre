#!/usr/bin/env python3
"""Validate a retrieved final-recovery launch-gate receipt and exec marker."""

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
EXPECTED_CONTROLLER_PATH = "/root/final_recovery_controller_f11.sh"
EXPECTED_CONTROLLER_SHA256 = (
    "ca9d6606b992507dd9e76afbb9fc219222c858831c93a385de22ac56d4b80006"
)
REJECTED_CONTROLLER_SHA256 = [
    "1a1baa67fa9c12b8af309581ff85d1e200af907b80cd0b8185eb8f9a68cd08cc",
    "6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c",
    "a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2",
]
REJECTED_POD_IDS = ["9n5f5a82p1gw1e", "eeo1skjkwjqot5", "j7xr357tdlpq3f"]
REJECTED_ATTEMPT_IDS = [
    "calv2-r3-audit-recovery-2479ed0-20260715T155035Z",
    "calv2-r3-audit-recovery-2479ed0-20260715T165648Z",
    "calv2-r3-audit-recovery-497b0f8-20260715T191757Z",
]
REJECTED_OWNERSHIP_RECEIPT_SHA256 = [
    "b7563a26c01646a68cb7618107b17743f38b14c87bc6bbf306e87a852a40ab2f",
    "54e0f4754b1dfd0a009da42ccae287d447cb6acbcd4d7394f3c149fbcac176b2",
    "6eb967c18c93cb008f273c507364b7610b3ca811d869cf275db9d594cd6f7e45",
]
REJECTED_AUTHORIZATION_RECEIPT_SHA256 = [
    "f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358",
    "8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4",
]
REJECTED_AUTHORIZATION_FILE_SHA256 = [
    "897a0fe5fac8e898f6367b8115a982a7580c0224843a76e2514589f6277274a7",
    "682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff",
]
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
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
POD_RE = re.compile(r"[a-z0-9]{6,32}\Z")
CREATED_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
ATTEMPT_RE = re.compile(
    r"calv2-r3-audit-recovery-([0-9a-f]{7})-([0-9]{8}T[0-9]{6}Z)\Z"
)
INPUT_ROOT_RE = re.compile(r"/root/final-recovery-inputs-[A-Za-z0-9._-]+\Z")


class ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


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


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValidationError(f"non-finite JSON number: {value}")


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


def _read_bound_file(path: Path, *, max_bytes: int) -> bytes:
    try:
        resolved = path.resolve(strict=True)
        link_info = path.lstat()
    except OSError as exc:
        raise ValidationError(f"could not inspect {path}: {exc}") from exc
    _require(path.is_absolute() and resolved == path, f"path is not canonical: {path}")
    _require(not stat.S_ISLNK(link_info.st_mode), f"path is a symbolic link: {path}")
    _require(stat.S_ISREG(link_info.st_mode), f"path is not a regular file: {path}")
    _require(link_info.st_nlink == 1, f"path link count is not one: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValidationError(f"could not open {path}: {exc}") from exc
    try:
        opened_info = os.fstat(fd)
        _require(_stat_binding(opened_info) == _stat_binding(link_info), f"file changed during open: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            _require(total <= max_bytes, f"file is unexpectedly large: {path}")
            chunks.append(chunk)
        final_info = os.fstat(fd)
        _require(_stat_binding(final_info) == _stat_binding(link_info), f"file changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = _read_bound_file(path, max_bytes=16 * 1024 * 1024)
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not parse {path}: {exc}") from exc
    _require(type(value) is dict, f"JSON root is not an object: {path}")
    return value, raw


def _parse_utc(value: Any, label: str) -> dt.datetime:
    _require(type(value) is str and CREATED_RE.fullmatch(value) is not None, f"invalid {label}")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValidationError(f"invalid {label}") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _validate_self_hashed_canonical(
    path: Path,
    *,
    require_trailing_newline: bool,
) -> tuple[dict[str, Any], bytes]:
    value, raw = _load(path)
    claimed = value.get("receipt_sha256")
    _require(type(claimed) is str and SHA256_RE.fullmatch(claimed) is not None, f"invalid receipt SHA-256: {path}")
    core = dict(value)
    core.pop("receipt_sha256")
    _require(_canonical_sha256(core) == claimed, f"self-hash differs: {path}")
    expected = _canonical_bytes(value) + (b"\n" if require_trailing_newline else b"")
    if require_trailing_newline:
        _require(raw == expected, f"receipt bytes are not canonical: {path}")
    else:
        _require(raw in (expected, expected + b"\n"), f"receipt bytes are not canonical: {path}")
    return value, raw


def _absence_paths(attempt_id: str) -> list[str]:
    base = Path("/root/consciousness_sae_audit_recovery") / attempt_id
    attempt = Path("/workspace/csae") / attempt_id
    output = attempt / "output"
    return [
        base.as_posix(),
        attempt.as_posix(),
        (attempt / "RECOVERY_AUTHORIZATION.json").as_posix(),
        output.as_posix(),
        (output / "ATTEMPT_STARTED.json").as_posix(),
        (output / "FAILURE.json").as_posix(),
        (output / "compact" / "CALIBRATION_AUDIT.json").as_posix(),
        (output / "compact" / "CALIBRATION_SUMMARY.json").as_posix(),
        (output / "compact" / "PUBLICATION_COMPLETE.json").as_posix(),
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--ownership-receipt", required=True, type=Path)
    parser.add_argument("--controller-log", required=True, type=Path)
    parser.add_argument("--expected-pod-id", required=True)
    parser.add_argument("--expected-created-at", required=True)
    parser.add_argument("--expected-attempt-id", required=True)
    parser.add_argument("--expected-input-root", required=True)
    parser.add_argument("--expected-gate-source-sha256", required=True)
    parser.add_argument("--expected-code-freeze", required=True)
    parser.add_argument("--expected-reviewed-packet-commit", required=True)
    parser.add_argument("--expected-final-freeze", required=True)
    parser.add_argument("--retrieved-authorization", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _require(POD_RE.fullmatch(args.expected_pod_id) is not None, "expected pod id is malformed")
    _require(args.expected_pod_id not in REJECTED_POD_IDS, "expected pod id is rejected")
    _require(CREATED_RE.fullmatch(args.expected_created_at) is not None, "expected created_at is malformed")
    attempt_match = ATTEMPT_RE.fullmatch(args.expected_attempt_id)
    _require(attempt_match is not None, "expected attempt id is malformed")
    _require(args.expected_attempt_id not in REJECTED_ATTEMPT_IDS, "expected attempt id is rejected")
    _require(INPUT_ROOT_RE.fullmatch(args.expected_input_root) is not None, "expected input root is malformed")
    for rejected in REJECTED_POD_IDS + REJECTED_ATTEMPT_IDS:
        _require(rejected not in args.expected_input_root, "expected input root contains a rejected identifier")
    _require(SHA256_RE.fullmatch(args.expected_gate_source_sha256) is not None, "expected gate source SHA-256 is malformed")
    runtime_commits = (
        args.expected_code_freeze,
        args.expected_reviewed_packet_commit,
        args.expected_final_freeze,
    )
    _require(
        all(re.fullmatch(r"[0-9a-f]{40}", value) for value in runtime_commits),
        "expected runtime commit binding is malformed",
    )
    _require(
        attempt_match.group(1) == args.expected_final_freeze[:7],
        "expected attempt id does not bind final-freeze short commit",
    )

    receipt, _ = _validate_self_hashed_canonical(
        args.receipt,
        require_trailing_newline=True,
    )
    ownership, ownership_raw = _validate_self_hashed_canonical(
        args.ownership_receipt,
        require_trailing_newline=False,
    )
    expected_keys = {
        "schema_version",
        "protocol_version",
        "status",
        "recorded_at",
        "gate_delivery",
        "gate_source_sha256",
        "gate_python_executable",
        "gate_python_flags",
        "gate_sys_path",
        "gate_process_environment",
        "gate_process_environment_sha256",
        "code_freeze_commit",
        "reviewed_packet_git_head_commit",
        "final_freeze_commit",
        "pod_id",
        "provider_created_at",
        "attempt_id",
        "input_root",
        "ownership_receipt_path",
        "ownership_receipt_sha256",
        "ownership_file_sha256",
        "ownership_stat",
        "ownership_terminate_after",
        "controller_path",
        "controller_sha256",
        "rejected_controller_sha256",
        "controller_stat",
        "controller_argv",
        "controller_argv_sha256",
        "controller_exec_environment",
        "controller_exec_environment_sha256",
        "controller_exec_method",
        "controller_exec_threat_boundary",
        "absence_checks",
        "rejected_pod_ids",
        "rejected_attempt_ids",
        "rejected_authorization_receipt_sha256",
        "rejected_authorization_file_sha256",
        "launch_receipt_path",
        "receipt_sha256",
    }
    _require(set(receipt) == expected_keys, "launch receipt field set differs")
    exact_fields = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "status": "launch_gate_prepared_for_immediate_exec",
        "gate_delivery": "python3.11_-I_-S_-B_stdin_external_source_sha256_binding",
        "gate_source_sha256": args.expected_gate_source_sha256,
        "gate_python_executable": "/usr/bin/python3.11",
        "gate_python_flags": EXPECTED_GATE_FLAGS,
        "gate_process_environment": CLEAN_EXEC_ENV,
        "gate_process_environment_sha256": _canonical_sha256(CLEAN_EXEC_ENV),
        "code_freeze_commit": args.expected_code_freeze,
        "reviewed_packet_git_head_commit": args.expected_reviewed_packet_commit,
        "final_freeze_commit": args.expected_final_freeze,
        "pod_id": args.expected_pod_id,
        "provider_created_at": args.expected_created_at,
        "attempt_id": args.expected_attempt_id,
        "input_root": args.expected_input_root,
        "controller_path": EXPECTED_CONTROLLER_PATH,
        "controller_sha256": EXPECTED_CONTROLLER_SHA256,
        "controller_exec_environment": CLEAN_EXEC_ENV,
        "controller_exec_environment_sha256": _canonical_sha256(CLEAN_EXEC_ENV),
        "controller_exec_method": CONTROLLER_EXEC_METHOD,
        "controller_exec_threat_boundary": CONTROLLER_EXEC_THREAT_BOUNDARY,
        "rejected_controller_sha256": REJECTED_CONTROLLER_SHA256,
        "rejected_pod_ids": REJECTED_POD_IDS,
        "rejected_attempt_ids": REJECTED_ATTEMPT_IDS,
        "rejected_authorization_receipt_sha256": REJECTED_AUTHORIZATION_RECEIPT_SHA256,
        "rejected_authorization_file_sha256": REJECTED_AUTHORIZATION_FILE_SHA256,
        "launch_receipt_path": f"/root/final-recovery-launch-gate-{args.expected_pod_id}.json",
    }
    for key, expected in exact_fields.items():
        _require(type(receipt.get(key)) is type(expected) and receipt.get(key) == expected, f"launch receipt field differs: {key}")
    _require(
        type(receipt.get("recorded_at")) is str
        and CREATED_RE.fullmatch(receipt["recorded_at"]) is not None,
        "recorded_at is malformed",
    )
    gate_sys_path = receipt.get("gate_sys_path")
    _require(type(gate_sys_path) is list and gate_sys_path, "gate sys.path is invalid")
    for entry in gate_sys_path:
        _require(type(entry) is str and entry.startswith("/"), "gate sys.path entry is not absolute")
        _require(entry not in ("", ".", "/root"), "gate sys.path includes the remote working directory")
        _require(
            "site-packages" not in entry and "dist-packages" not in entry,
            "gate sys.path includes a package installation root",
        )
    expected_ownership_remote = f"{args.expected_input_root}/fresh/OWNERSHIP.json"
    _require(receipt["ownership_receipt_path"] == expected_ownership_remote, "ownership remote path differs")
    _require(receipt["ownership_receipt_sha256"] == ownership["receipt_sha256"], "ownership self-hash binding differs")
    _require(ownership["receipt_sha256"] not in REJECTED_OWNERSHIP_RECEIPT_SHA256, "ownership receipt is rejected")
    _require(receipt["ownership_file_sha256"] == hashlib.sha256(ownership_raw).hexdigest(), "ownership file-hash binding differs")
    for key, expected in {
        "pod_id": args.expected_pod_id,
        "created_at": args.expected_created_at,
        "network_volume_id": "bv9gb9j32y",
        "data_center_id": "US-CA-2",
        "gpu_type": "NVIDIA B200",
        "gpu_count": 1,
        "status": "owned_running_isolated",
    }.items():
        _require(type(ownership.get(key)) is type(expected) and ownership.get(key) == expected, f"ownership field differs: {key}")
    _require(type(ownership.get("locked")) is bool and ownership["locked"] is False, "ownership lock state differs")
    _require(
        type(ownership.get("precreate_unrelated_pod_count")) is int
        and ownership["precreate_unrelated_pod_count"] >= 0,
        "ownership unrelated-pod count is invalid",
    )
    _require(
        type(ownership.get("precreate_unrelated_inventory_sha256")) is str
        and SHA256_RE.fullmatch(ownership["precreate_unrelated_inventory_sha256"]) is not None,
        "ownership unrelated-inventory SHA-256 is invalid",
    )
    _require(receipt["ownership_terminate_after"] == ownership.get("terminate_after"), "ownership termination binding differs")

    created = _parse_utc(args.expected_created_at, "expected created_at")
    recorded = _parse_utc(receipt["recorded_at"], "recorded_at")
    terminate_after = _parse_utc(ownership.get("terminate_after"), "ownership terminate_after")
    attempt_time = dt.datetime.strptime(
        attempt_match.group(2), "%Y%m%dT%H%M%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    _require(recorded >= created - dt.timedelta(minutes=5), "gate predates pod creation beyond skew")
    _require(recorded <= created + dt.timedelta(hours=6), "gate did not use a fresh pod receipt")
    _require(terminate_after > recorded and terminate_after > created, "ownership was expired at gate time")
    _require(abs(attempt_time - created) <= dt.timedelta(hours=6), "attempt and creation times differ")

    expected_argv = [
        EXPECTED_CONTROLLER_PATH,
        args.expected_code_freeze,
        args.expected_reviewed_packet_commit,
        args.expected_final_freeze,
        args.expected_pod_id,
        args.expected_created_at,
        args.expected_attempt_id,
        args.expected_input_root,
    ]
    expected_argv_sha256 = _canonical_sha256(expected_argv)
    _require(receipt["controller_argv"] == expected_argv, "controller argv differs")
    _require(receipt["controller_argv_sha256"] == expected_argv_sha256, "controller argv digest differs")
    expected_absence = [
        {"path": path, "status": "absent"}
        for path in _absence_paths(args.expected_attempt_id)
    ]
    _require(receipt["absence_checks"] == expected_absence, "absence checks differ")

    for label in ("controller_stat", "ownership_stat"):
        value = receipt.get(label)
        _require(type(value) is dict, f"{label} is not an object")
        _require(
            set(value)
            == {"device", "inode", "mode", "nlink", "uid", "gid", "bytes", "mtime_ns", "ctime_ns"},
            f"{label} field set differs",
        )
        _require(all(type(item) is int and item >= 0 for item in value.values()), f"{label} values are invalid")
        _require(value["nlink"] == 1, f"{label} link count differs")
        _require(stat.S_IMODE(value["mode"]) == value["mode"], f"{label} mode is invalid")
    _require(receipt["controller_stat"]["bytes"] > 0, "controller size is empty")
    _require(receipt["ownership_stat"]["bytes"] == len(ownership_raw), "ownership stat size differs")
    _require(receipt["controller_stat"]["mode"] & stat.S_IXUSR != 0, "controller was not owner executable")
    _require(receipt["controller_stat"]["mode"] & (stat.S_IWGRP | stat.S_IWOTH) == 0, "controller was group/other writable")

    marker = (
        "FINAL_RECOVERY_LAUNCH_GATE_BOUND "
        f"receipt_sha256={receipt['receipt_sha256']} "
        f"controller_sha256={EXPECTED_CONTROLLER_SHA256} "
        f"argv_sha256={expected_argv_sha256} "
        f"env_sha256={_canonical_sha256(CLEAN_EXEC_ENV)}"
    )
    try:
        log_text = _read_bound_file(
            args.controller_log,
            max_bytes=256 * 1024 * 1024,
        ).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValidationError(f"could not read controller log: {exc}") from exc
    log_lines = log_text.splitlines()
    marker_indexes = [index for index, line in enumerate(log_lines) if line == marker]
    _require(len(marker_indexes) == 1, "exact final hash-and-exec marker is not present once")
    controller_start_indexes = [
        index
        for index, line in enumerate(log_lines)
        if line.startswith("FINAL_RECOVERY_CONTROLLER_START ")
    ]
    _require(len(controller_start_indexes) == 1, "exact controller-start stage is not present once")
    _require(controller_start_indexes[0] > marker_indexes[0], "controller-start stage does not follow gate marker")
    _parse_utc(
        log_lines[controller_start_indexes[0]].removeprefix("FINAL_RECOVERY_CONTROLLER_START "),
        "controller-start timestamp",
    )
    if args.retrieved_authorization is not None:
        authorization, authorization_raw = _validate_self_hashed_canonical(
            args.retrieved_authorization,
            require_trailing_newline=False,
        )
        _require(
            authorization["receipt_sha256"]
            not in REJECTED_AUTHORIZATION_RECEIPT_SHA256,
            "retrieved recovery authorization is explicitly rejected",
        )
        _require(
            hashlib.sha256(authorization_raw).hexdigest()
            not in REJECTED_AUTHORIZATION_FILE_SHA256,
            "retrieved recovery authorization file bytes are explicitly rejected",
        )
        _require(
            authorization.get("git_head_commit") == args.expected_final_freeze,
            "retrieved recovery authorization final Git commit differs",
        )
        _require(
            authorization.get("fresh_pod_id") == args.expected_pod_id,
            "retrieved recovery authorization pod id differs",
        )
        execution = authorization.get("execution")
        _require(type(execution) is dict, "retrieved recovery authorization execution is invalid")
        _require(
            execution.get("attempt_id") == args.expected_attempt_id,
            "retrieved recovery authorization attempt id differs",
        )
    print(
        "FINAL_RECOVERY_LAUNCH_GATE_VALIDATED "
        f"receipt_sha256={receipt['receipt_sha256']} "
        f"controller_sha256={EXPECTED_CONTROLLER_SHA256} "
        f"argv_sha256={expected_argv_sha256} "
        f"env_sha256={_canonical_sha256(CLEAN_EXEC_ENV)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"FINAL_RECOVERY_LAUNCH_GATE_VALIDATION_FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
