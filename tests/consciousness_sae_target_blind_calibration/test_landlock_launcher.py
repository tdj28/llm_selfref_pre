from __future__ import annotations

import ast
import errno
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.consciousness_sae_target_blind_calibration import landlock_launcher


def _receipt_core(tmp_path: Path) -> dict:
    child = ["/usr/bin/python3", "-B", "-c", "pass"]
    return {
        "schema_version": 1,
        "status": "pass_landlock_enforced",
        "purpose": "audit_recovery",
        "pid": 123,
        "observed_abi": 4,
        "required_abi": 4,
        "handled_access_fs": 0x7FF2,
        "output_allowed_access_fs": 0x1B2,
        "no_new_privs": True,
        "thread_ids": [123],
        "descriptor_audit": {
            "status": "pass_no_escaping_writable_or_protected_descriptors",
            "descriptor_count": 3,
            "descriptors": [],
        },
        "mapping_audit": {
            "status": "pass_no_shared_file_backed_mappings",
            "mapping_count": 10,
            "shared_file_backed": [],
        },
        "directory_rules": [
            {
                "role": "output_root",
                "path": (tmp_path / "output").as_posix(),
                "allowed_access_fs": 0x1B2,
            },
            {
                "role": "canary_output_root",
                "path": (tmp_path / "canary-output").as_posix(),
                "allowed_access_fs": 0x1B2,
            },
            {
                "role": "proc_self_task_thread_names",
                "path": "/proc/self/task",
                "allowed_access_fs": 0x4002,
            },
        ],
        "device_rules": [
            {
                "path": "/dev/nvidia0",
                "st_dev": 1,
                "st_ino": 2,
                "st_rdev": os.makedev(195, 0),
                "major": 195,
                "minor": 0,
                "allowed_access_fs": 0x2,
            }
        ],
        "protected_checks": [],
        "canary_checks": {"status": "pass_protected_unchanged_output_empty"},
        "child_argv": child,
        "child_argv_sha256": landlock_launcher.canonical_sha256(child),
        "source_sha256": "a" * 64,
        "receipt_path": (tmp_path / "output/LANDLOCK_ENFORCEMENT.json").as_posix(),
        "authorization_sha256": "b" * 64,
        "preflight_receipt_sha256": "c" * 64,
    }


def test_launcher_source_imports_only_the_standard_library() -> None:
    source = Path(landlock_launcher.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}
    assert not ({"torch", "transformers", "numpy", "safetensors"} & imported)


def test_frozen_policy_masks_are_exact() -> None:
    landlock_launcher.validate_policy()
    assert landlock_launcher.HANDLED_ACCESS_FS == 0x7FF2
    assert landlock_launcher.OUTPUT_ALLOWED_ACCESS_FS == 0x1B2
    assert landlock_launcher.DEVICE_ALLOWED_ACCESS_FS == 0x2
    assert landlock_launcher.PROC_SELF_TASK_ALLOWED_ACCESS_FS == 0x4002
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="policy differs"):
        landlock_launcher.validate_policy(handled_access_fs=0x1B2)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="policy differs"):
        landlock_launcher.validate_policy(output_allowed_access_fs=0x1B3)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="policy differs"):
        landlock_launcher.validate_policy(proc_self_task_allowed_access_fs=0x2)


@pytest.mark.parametrize(
    ("purpose", "authorization", "preflight"),
    [
        ("preauthorization_probe", "a" * 64, None),
        ("preauthorization_probe", None, "b" * 64),
        ("audit_recovery", None, None),
        ("audit_recovery", "a" * 64, None),
    ],
)
def test_purpose_hashes_fail_closed(
    purpose: str, authorization: str | None, preflight: str | None
) -> None:
    with pytest.raises(landlock_launcher.LandlockLaunchError):
        landlock_launcher.validate_purpose_hashes(purpose, authorization, preflight)
    landlock_launcher.validate_purpose_hashes("preauthorization_probe", None, None)
    landlock_launcher.validate_purpose_hashes("audit_recovery", "a" * 64, "b" * 64)


def test_syscall_numbers_are_frozen_for_supported_architectures() -> None:
    for name in ("x86_64", "amd64", "aarch64", "arm64"):
        assert landlock_launcher.syscall_numbers(name) == (444, 445, 446)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="unsupported"):
        landlock_launcher.syscall_numbers("mips64")


def test_device_rule_record_binds_full_character_device_identity() -> None:
    details = SimpleNamespace(
        st_mode=stat.S_IFCHR | 0o660,
        st_dev=44,
        st_ino=55,
        st_rdev=os.makedev(195, 7),
    )
    record = landlock_launcher._device_rule_record(Path("/dev/nvidia7"), details)
    assert record == {
        "path": "/dev/nvidia7",
        "st_dev": 44,
        "st_ino": 55,
        "st_rdev": os.makedev(195, 7),
        "major": 195,
        "minor": 7,
        "allowed_access_fs": 0x2,
    }
    regular = SimpleNamespace(**{**vars(details), "st_mode": stat.S_IFREG | 0o600})
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="character"):
        landlock_launcher._device_rule_record(Path("/dev/nvidia7"), regular)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="closed NVIDIA"):
        landlock_launcher._device_rule_record(Path("/tmp/nvidia7"), details)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="closed NVIDIA"):
        landlock_launcher._device_rule_record(Path("/dev/null"), details)


def test_launcher_requires_direct_no_site_no_bytecode_startup() -> None:
    script = Path(landlock_launcher.__file__).resolve()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "LD_AUDIT",
            "LD_PRELOAD",
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONPATH",
            "PYTHONPLATLIBDIR",
            "PYTHONSTARTUP",
            "PYTHONUSERBASE",
            "PYTHONDONTWRITEBYTECODE",
        }
    }
    environment["PYTHONNOUSERSITE"] = "1"
    without_no_site = subprocess.run(
        [sys.executable, "-B", script.as_posix(), "--help"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert without_no_site.returncode != 0
    assert "requires Python -S" in without_no_site.stderr

    without_no_bytecode = subprocess.run(
        [sys.executable, "-S", script.as_posix(), "--help"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert without_no_bytecode.returncode != 0
    assert "requires Python -B" in without_no_bytecode.stderr

    without_ignore_environment = subprocess.run(
        [sys.executable, "-B", "-s", "-S", script.as_posix(), "--help"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert without_ignore_environment.returncode != 0
    assert "requires Python -E" in without_ignore_environment.stderr

    without_no_user_site = subprocess.run(
        [sys.executable, "-B", "-E", "-S", script.as_posix(), "--help"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert without_no_user_site.returncode != 0
    assert "requires Python -s" in without_no_user_site.stderr

    exact = subprocess.run(
        [sys.executable, "-B", "-E", "-s", "-S", script.as_posix(), "--help"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert exact.returncode == 0, exact.stderr

    with pytest.raises(landlock_launcher.LandlockLaunchError, match="Python -S"):
        landlock_launcher.launch(SimpleNamespace())

    unsafe = {**environment, "PYTHONPATH": "/tmp/injected"}
    unsafe_result = subprocess.run(
        [sys.executable, "-B", "-E", "-s", "-S", script.as_posix(), "--help"],
        env=unsafe,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert unsafe_result.returncode != 0
    assert "unsafe launcher environment" in unsafe_result.stderr


def test_directory_layout_rejects_equal_or_nested_roots(tmp_path: Path) -> None:
    output = tmp_path / "output"
    protected = tmp_path / "protected"
    canary_output = tmp_path / "canary-output"
    landlock_launcher.validate_directory_layout(
        output_root=output,
        canary_protected_root=protected,
        canary_output_root=canary_output,
    )
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="distinct"):
        landlock_launcher.validate_directory_layout(
            output_root=output,
            canary_protected_root=protected,
            canary_output_root=output,
        )
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="overlap"):
        landlock_launcher.validate_directory_layout(
            output_root=output,
            canary_protected_root=protected,
            canary_output_root=output / "nested",
        )


def test_protected_roots_cannot_overlap_writable_roots(tmp_path: Path) -> None:
    output = tmp_path / "output"
    canary_output = tmp_path / "canary-output"
    protected = tmp_path / "raw"
    landlock_launcher.validate_protected_roots(
        [protected], output_root=output, canary_output_root=canary_output
    )
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="overlaps"):
        landlock_launcher.validate_protected_roots(
            [output.parent], output_root=output, canary_output_root=canary_output
        )
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="duplicated"):
        landlock_launcher.validate_protected_roots(
            [protected, protected],
            output_root=output,
            canary_output_root=canary_output,
        )


@pytest.mark.parametrize(
    ("target_kind", "target", "expected"),
    [
        ("protected", "raw/stdio.log", "protected descriptor"),
        ("escaping", "remote-stderr.log", "was inherited"),
    ],
)
def test_descriptor_audit_does_not_exempt_standard_stream_regular_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_kind: str,
    target: str,
    expected: str,
) -> None:
    output = tmp_path / "output"
    canary_protected = tmp_path / "canary-protected"
    canary_output = tmp_path / "canary-output"
    protected = tmp_path / "raw"
    target_path = (
        protected / target.removeprefix("raw/")
        if target_kind == "protected"
        else tmp_path / target
    )
    details = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
    monkeypatch.setattr(os, "listdir", lambda _path: ["2"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_WRONLY)
    monkeypatch.setattr(os, "readlink", lambda _path: target_path.as_posix())
    with pytest.raises(landlock_launcher.LandlockLaunchError, match=expected):
        landlock_launcher._descriptor_audit(
            output_root=output,
            canary_protected_root=canary_protected,
            canary_output_root=canary_output,
            protected_roots=[protected],
            protected_files=[],
            device_records=[],
        )


def test_descriptor_audit_allows_standard_stream_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = SimpleNamespace(st_mode=stat.S_IFIFO | 0o600)
    monkeypatch.setattr(os, "listdir", lambda _path: ["1"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_WRONLY)
    monkeypatch.setattr(os, "readlink", lambda _path: "pipe:[123]")
    receipt = landlock_launcher._descriptor_audit(
        output_root=tmp_path / "output",
        canary_protected_root=tmp_path / "canary-protected",
        canary_output_root=tmp_path / "canary-output",
        protected_roots=[tmp_path / "raw"],
        protected_files=[],
        device_records=[],
    )
    assert receipt["descriptors"] == [
        {
            "fd": 1,
            "target": "pipe:[123]",
            "kind": "fifo",
            "access_mode": os.O_WRONLY,
            "writable": True,
            "allowed_reason": "standard_stream",
        }
    ]


def test_descriptor_audit_excludes_only_its_known_proc_inventory_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory_fd = 9
    closed: list[int] = []

    def fake_open(path: str, flags: int) -> int:
        assert path == "/proc/self/fd"
        assert flags & os.O_RDONLY == os.O_RDONLY
        assert flags & landlock_launcher._O_DIRECTORY
        return inventory_fd

    def fake_listdir(path: int) -> list[str]:
        assert path == inventory_fd
        return ["1", str(inventory_fd)]

    monkeypatch.setattr(landlock_launcher.sys, "platform", "linux")
    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "listdir", fake_listdir)
    monkeypatch.setattr(
        os,
        "fstat",
        lambda fd: SimpleNamespace(st_mode=stat.S_IFIFO | 0o600) if fd == 1 else None,
    )
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_WRONLY)
    monkeypatch.setattr(os, "readlink", lambda _path: "pipe:[123]")
    monkeypatch.setattr(os, "close", closed.append)

    receipt = landlock_launcher._descriptor_audit(
        output_root=tmp_path / "output",
        canary_protected_root=tmp_path / "canary-protected",
        canary_output_root=tmp_path / "canary-output",
        protected_roots=[tmp_path / "raw"],
        protected_files=[],
        device_records=[],
    )

    assert closed == [inventory_fd]
    assert receipt["descriptors"] == [
        {
            "fd": 1,
            "target": "pipe:[123]",
            "kind": "fifo",
            "access_mode": os.O_WRONLY,
            "writable": True,
            "allowed_reason": "standard_stream",
        }
    ]


def test_descriptor_audit_skips_only_a_proc_entry_that_is_already_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(landlock_launcher.sys, "platform", "darwin")
    monkeypatch.setattr(os, "listdir", lambda _path: ["4"])

    def closed_descriptor(_fd: int) -> None:
        raise OSError(errno.EBADF, "descriptor closed by procfs enumeration")

    monkeypatch.setattr(os, "fstat", closed_descriptor)
    receipt = landlock_launcher._descriptor_audit(
        output_root=tmp_path / "output",
        canary_protected_root=tmp_path / "canary-protected",
        canary_output_root=tmp_path / "canary-output",
        protected_roots=[tmp_path / "raw"],
        protected_files=[],
        device_records=[],
    )
    assert receipt["descriptors"] == []


def test_descriptor_audit_rejects_standard_stream_gpu_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rdev = os.makedev(195, 0)
    details = SimpleNamespace(
        st_mode=stat.S_IFCHR | 0o660,
        st_dev=10,
        st_ino=20,
        st_rdev=rdev,
    )
    device = {
        "path": "/dev/nvidia0",
        "st_dev": 10,
        "st_ino": 20,
        "st_rdev": rdev,
    }
    monkeypatch.setattr(os, "listdir", lambda _path: ["0"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_RDWR)
    monkeypatch.setattr(os, "readlink", lambda _path: "/dev/nvidia0")
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="GPU-device"):
        landlock_launcher._descriptor_audit(
            output_root=tmp_path / "output",
            canary_protected_root=tmp_path / "canary-protected",
            canary_output_root=tmp_path / "canary-output",
            protected_roots=[tmp_path / "raw"],
            protected_files=[],
            device_records=[device],
        )


def test_descriptor_audit_rejects_unenumerated_gpu_and_writable_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rdev = os.makedev(195, 9)
    details = SimpleNamespace(
        st_mode=stat.S_IFCHR | 0o660,
        st_dev=10,
        st_ino=29,
        st_rdev=rdev,
    )
    monkeypatch.setattr(os, "listdir", lambda _path: ["3"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_RDWR)
    monkeypatch.setattr(os, "readlink", lambda _path: "/dev/nvidia9")
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="GPU-device"):
        landlock_launcher._descriptor_audit(
            output_root=tmp_path / "output",
            canary_protected_root=tmp_path / "canary-protected",
            canary_output_root=tmp_path / "canary-output",
            protected_roots=[tmp_path / "raw"],
            protected_files=[],
            device_records=[],
        )

    monkeypatch.setattr(os, "readlink", lambda _path: "/dev/null")
    with pytest.raises(
        landlock_launcher.LandlockLaunchError,
        match="writable character/block-device",
    ):
        landlock_launcher._descriptor_audit(
            output_root=tmp_path / "output",
            canary_protected_root=tmp_path / "canary-protected",
            canary_output_root=tmp_path / "canary-output",
            protected_roots=[tmp_path / "raw"],
            protected_files=[],
            device_records=[],
        )


def test_descriptor_audit_rejects_standard_stream_canary_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = SimpleNamespace(st_mode=stat.S_IFREG | 0o600)
    target = tmp_path / "canary-output/stderr.log"
    monkeypatch.setattr(os, "listdir", lambda _path: ["2"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_WRONLY)
    monkeypatch.setattr(os, "readlink", lambda _path: target.as_posix())
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="canary-output"):
        landlock_launcher._descriptor_audit(
            output_root=tmp_path / "output",
            canary_protected_root=tmp_path / "canary-protected",
            canary_output_root=tmp_path / "canary-output",
            protected_roots=[tmp_path / "raw"],
            protected_files=[],
            device_records=[],
        )


def test_protected_snapshot_binds_bytes_topology_and_rejects_links(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected"
    nested = protected / "nested"
    nested.mkdir(parents=True)
    seed = nested / "seed.txt"
    seed.write_bytes(b"seed")
    before = landlock_launcher._snapshot_tree(protected)
    assert landlock_launcher.canonical_sha256(before)
    seed.write_bytes(b"changed")
    assert landlock_launcher._snapshot_tree(protected) != before
    link = protected / "link"
    link.symlink_to(seed)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="symlink"):
        landlock_launcher._snapshot_tree(protected)


def test_denied_requires_eacces_and_rejects_success() -> None:
    def access_denied() -> None:
        raise PermissionError(errno.EACCES, "denied")

    assert landlock_launcher._denied("test", access_denied) == {
        "operation": "test",
        "status": "denied",
        "errno": errno.EACCES,
    }

    def wrong_error() -> None:
        raise OSError(errno.EROFS, "read only")

    with pytest.raises(landlock_launcher.LandlockLaunchError, match="not EACCES"):
        landlock_launcher._denied("test", wrong_error)
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="succeeded"):
        landlock_launcher._denied("test", lambda: None)


def test_denied_supports_landlock_refer_exdev() -> None:
    def refer_denied() -> None:
        raise OSError(errno.EXDEV, "Landlock cross-directory refer denied")

    assert landlock_launcher._denied(
        "output_cross_directory_link",
        refer_denied,
        expected_errno=errno.EXDEV,
    ) == {
        "operation": "output_cross_directory_link",
        "status": "denied",
        "errno": errno.EXDEV,
    }


def test_maps_parser_preserves_path_with_spaces() -> None:
    row = landlock_launcher._parse_maps_line(
        "7f00-7f10 rw-s 00000000 08:01 42 /tmp/a mapped file.bin\n"
    )
    assert row["permissions"] == "rw-s"
    assert row["pathname"] == "/tmp/a mapped file.bin"
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="malformed"):
        landlock_launcher._parse_maps_line("not-a-map")


def test_mapping_audit_rejects_read_only_shared_file_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _self, **_kwargs: "1000-2000 r--s 00000000 08:01 123 /tmp/shared.bin\n",
    )
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="shared"):
        landlock_launcher._mapping_audit()


def test_descriptor_audit_rejects_io_uring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = SimpleNamespace(st_mode=stat.S_IFIFO | 0o600)
    monkeypatch.setattr(os, "listdir", lambda _path: ["4"])
    monkeypatch.setattr(os, "fstat", lambda _fd: details)
    monkeypatch.setattr(landlock_launcher.fcntl, "fcntl", lambda *_args: os.O_RDONLY)
    monkeypatch.setattr(os, "readlink", lambda _path: "anon_inode:[io_uring]")
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="io_uring"):
        landlock_launcher._descriptor_audit(
            output_root=tmp_path / "output",
            canary_protected_root=tmp_path / "canary-protected",
            canary_output_root=tmp_path / "canary-output",
            protected_roots=[tmp_path / "raw"],
            protected_files=[],
            device_records=[],
        )


def test_receipt_has_exact_schema_and_canonical_self_hash(tmp_path: Path) -> None:
    core = _receipt_core(tmp_path)
    receipt = landlock_launcher.seal_receipt(core)
    assert set(receipt) == (
        set(landlock_launcher.RECEIPT_REQUIRED_FIELDS)
        | set(landlock_launcher.RECEIPT_OPTIONAL_FIELDS)
    )
    assert landlock_launcher.validate_receipt(receipt) == receipt
    physical = landlock_launcher.canonical_json_bytes(receipt) + b"\n"
    assert json.loads(physical) == receipt

    extra = {**receipt, "unexpected": True}
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="field inventory"):
        landlock_launcher.validate_receipt(extra)
    tampered = dict(receipt)
    tampered["handled_access_fs"] = 0x1B2
    with pytest.raises(landlock_launcher.LandlockLaunchError, match="self-hash"):
        landlock_launcher.validate_receipt(tampered)


def test_receipt_without_optional_hashes_is_valid(tmp_path: Path) -> None:
    core = _receipt_core(tmp_path)
    core["purpose"] = "preauthorization_probe"
    core.pop("authorization_sha256")
    core.pop("preflight_receipt_sha256")
    receipt = landlock_launcher.seal_receipt(core)
    assert set(receipt) == set(landlock_launcher.RECEIPT_REQUIRED_FIELDS)
    landlock_launcher.validate_receipt(receipt)


@pytest.mark.parametrize("mask", [0x2, 0x4082])
def test_receipt_rejects_narrowed_or_broadened_proc_task_rule(
    tmp_path: Path, mask: int
) -> None:
    core = _receipt_core(tmp_path)
    core["directory_rules"] = [dict(row) for row in core["directory_rules"]]
    core["directory_rules"][2]["allowed_access_fs"] = mask
    with pytest.raises(
        landlock_launcher.LandlockLaunchError, match="directory-rule receipt differs"
    ):
        landlock_launcher.validate_receipt(landlock_launcher.seal_receipt(core))


def test_parser_captures_exact_child_command_after_separator(tmp_path: Path) -> None:
    parser = landlock_launcher.build_parser()
    args = parser.parse_args(
        [
            "--purpose",
            "audit_recovery",
            "--output-root",
            str(tmp_path / "output"),
            "--canary-protected-root",
            str(tmp_path / "protected"),
            "--canary-output-root",
            str(tmp_path / "canary-output"),
            "--protected-root",
            str(tmp_path / "raw"),
            "--protected-file",
            str(tmp_path / "raw.json"),
            "--device-file",
            "/dev/nvidia0",
            "--receipt",
            str(tmp_path / "output/receipt.json"),
            "--authorization-sha256",
            "a" * 64,
            "--preflight-receipt-sha256",
            "b" * 64,
            "--",
            "/usr/bin/python3",
            "-B",
            "-c",
            "pass",
        ]
    )
    assert args.purpose == "audit_recovery"
    assert args.protected_file == [tmp_path / "raw.json"]
    assert args.protected_root == [tmp_path / "raw"]
    assert args.device_file == [Path("/dev/nvidia0")]
    assert args.child_argv == ["--", "/usr/bin/python3", "-B", "-c", "pass"]


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_linux_launcher_enforces_policy_and_same_pid_exec(tmp_path: Path) -> None:
    if not Path("/proc/self/task").is_dir():
        pytest.skip("procfs is unavailable")
    try:
        abi = landlock_launcher.landlock_abi()
        landlock_launcher.syscall_numbers()
    except landlock_launcher.LandlockLaunchError as exc:
        pytest.skip(str(exc))
    if abi < 4:
        pytest.skip(f"Landlock ABI {abi} is below ABI 4")
    device = next(
        (
            candidate
            for candidate in (
                Path("/dev/nvidia0"),
                Path("/dev/nvidiactl"),
                Path("/dev/nvidia-uvm"),
                Path("/dev/nvidia-uvm-tools"),
            )
            if candidate.exists() and stat.S_ISCHR(candidate.stat().st_mode)
        ),
        None,
    )
    if device is None:
        pytest.skip("no canonical NVIDIA character device")

    output = (tmp_path / "output").resolve()
    canary_protected = (tmp_path / "canary-protected").resolve()
    canary_output = (tmp_path / "canary-output").resolve()
    output.mkdir()
    canary_protected.mkdir()
    canary_output.mkdir()
    (canary_protected / "seed.txt").write_bytes(b"protected\n")
    protected_file = (tmp_path / "real-protected.txt").resolve()
    protected_file.write_bytes(b"real protected\n")
    receipt_path = output / "LANDLOCK_ENFORCEMENT.json"
    child_code = "import os; print('CHILD_OK_PID=' + str(os.getpid()), flush=True)"
    command = [
        sys.executable,
        "-B",
        "-E",
        "-s",
        "-S",
        Path(landlock_launcher.__file__).resolve().as_posix(),
        "--purpose",
        "preauthorization_probe",
        "--output-root",
        output.as_posix(),
        "--canary-protected-root",
        canary_protected.as_posix(),
        "--canary-output-root",
        canary_output.as_posix(),
        "--protected-root",
        canary_protected.as_posix(),
        "--protected-file",
        protected_file.as_posix(),
        "--device-file",
        device.resolve().as_posix(),
        "--receipt",
        receipt_path.as_posix(),
        "--",
        sys.executable,
        "-B",
        "-c",
        child_code,
    ]
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    for name in landlock_launcher._FORBIDDEN_STARTUP_ENVIRONMENT:
        environment.pop(name, None)
    completed = subprocess.run(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    lines = completed.stdout.splitlines()
    assert len(lines) == 2
    disk_bytes = receipt_path.read_bytes()
    assert lines[0] + b"\n" == disk_bytes
    receipt = json.loads(disk_bytes)
    landlock_launcher.validate_receipt(receipt)
    assert receipt["pid"] == int(lines[1].decode().removeprefix("CHILD_OK_PID="))
    assert receipt["observed_abi"] >= 4
    assert receipt["canary_checks"]["protected_unchanged"] is True
    assert list(canary_output.iterdir()) == []
    assert protected_file.read_bytes() == b"real protected\n"
