from __future__ import annotations

import argparse
import contextlib
import errno
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from experiments.consciousness_sae_realization_validation import runtime as full_runtime
from experiments.consciousness_sae_target_blind_calibration import (
    audit,
    audit_recovery,
    audit_runtime_shim,
    landlock_launcher,
    protocol,
    recovery_bundle_verifier,
)


class _Watchdog:
    def check(self) -> None:
        return None


def _checkpoint(maps: dict) -> dict:
    return {
        "J": maps,
        "n_prompts": protocol.J_LENS_SPEC["release_config"]["prompts_fitted"],
        "d_model": protocol.WIDTH,
    }


def _install_fake_checkpoint(monkeypatch, checkpoint: dict) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(
        protocol, "sha256_file", lambda _path: protocol.J_LENS_SPEC["sha256"]
    )
    monkeypatch.setattr(torch, "load", lambda *_args, **_kwargs: checkpoint)


def test_recovery_loader_accepts_authentic_superset_and_filters_to_required(
    tmp_path: Path, monkeypatch
) -> None:
    required = tuple(protocol.J_LAYERS)
    values = {layer: object() for layer in range(79)}
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    audit_recovery._OBSERVED_J_INVENTORY = None  # noqa: SLF001
    _path, filtered, record = audit_recovery._load_j_checkpoint_recovery(
        path, _Watchdog()
    )
    assert tuple(filtered) == required
    assert all(filtered[layer] is values[layer] for layer in required)
    assert record == {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": len(required),
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    assert audit_recovery._OBSERVED_J_INVENTORY == {  # noqa: SLF001
        "available_layers": list(range(79)),
        "required_layers": list(required),
        "unused_extra_layers": list(range(45)),
        "available_map_count": 79,
        "required_map_count": len(required),
        "inventory_sha256": protocol.canonical_sha256(list(range(79))),
    }


@pytest.mark.parametrize(
    "extra_layers",
    [
        (),
        (-3, 7, 44, 79, 120),
    ],
)
def test_recovery_loader_accepts_any_inventory_containing_required_layers(
    tmp_path: Path, monkeypatch, extra_layers: tuple[int, ...]
) -> None:
    required = tuple(protocol.J_LAYERS)
    values = {layer: object() for layer in (*required, *extra_layers)}
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    audit_recovery._OBSERVED_J_INVENTORY = None  # noqa: SLF001

    _path, filtered, record = audit_recovery._load_j_checkpoint_recovery(
        path, _Watchdog()
    )

    available = sorted(set(required) | set(extra_layers))
    extras = sorted(set(extra_layers) - set(required))
    assert list(filtered) == list(required)
    assert all(filtered[layer] is values[layer] for layer in required)
    assert record == {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": len(required),
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    assert audit_recovery._OBSERVED_J_INVENTORY == {  # noqa: SLF001
        "available_layers": available,
        "required_layers": list(required),
        "unused_extra_layers": extras,
        "available_map_count": len(available),
        "required_map_count": len(required),
        "inventory_sha256": protocol.canonical_sha256(available),
    }


@pytest.mark.parametrize("missing", [50, 78])
def test_recovery_loader_rejects_missing_required_layer(
    tmp_path: Path, monkeypatch, missing: int
) -> None:
    values = {layer: object() for layer in range(79) if layer != missing}
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="map inventory"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_recovery_loader_rejects_duplicate_normalized_layer(
    tmp_path: Path, monkeypatch
) -> None:
    values = {layer: object() for layer in range(79)}
    values["50"] = object()
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="duplicated"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


@pytest.mark.parametrize("key", ["050", "5.0"])
def test_recovery_loader_rejects_noncanonical_layer_identifier(
    tmp_path: Path, monkeypatch, key
) -> None:
    values = {layer: object() for layer in range(79)}
    values[key] = object()
    _install_fake_checkpoint(monkeypatch, _checkpoint(values))
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="noncanonical|duplicated"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_inventory_normalizer_rejects_boolean_identifier() -> None:
    with pytest.raises(audit.CalibrationAuditError, match="noncanonical"):
        audit_recovery._normalize_j_inventory({True: object()})


def test_recovery_loader_rejects_wrong_metadata(tmp_path: Path, monkeypatch) -> None:
    checkpoint = _checkpoint({layer: object() for layer in range(79)})
    checkpoint["n_prompts"] = 124
    _install_fake_checkpoint(monkeypatch, checkpoint)
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned")
    with pytest.raises(audit.CalibrationAuditError, match="metadata"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_recovery_loader_rejects_wrong_physical_hash(
    tmp_path: Path, monkeypatch
) -> None:
    pytest.importorskip("torch")
    monkeypatch.setattr(protocol, "sha256_file", lambda _path: "0" * 64)
    path = tmp_path / "j.pt"
    path.write_bytes(b"wrong")
    with pytest.raises(audit.CalibrationAuditError, match="hash"):
        audit_recovery._load_j_checkpoint_recovery(path, _Watchdog())


def test_zero_forward_guard_blocks_and_restores_torch_module_calls() -> None:
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    layer = torch.nn.Linear(2, 2)
    with audit_recovery._zero_forward_guards() as counts:
        with pytest.raises(audit_recovery.AuditRecoveryError, match="Module call"):
            layer(torch.ones(2))
        assert counts["torch_module_calls"] == 1
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model load"):
            transformers.PreTrainedModel.from_pretrained("forbidden")
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model load"):
            transformers.AutoModelForSequenceClassification.from_pretrained("forbidden")
        assert counts["transformers_model_load_calls"] == 2
    assert tuple(layer(torch.ones(2)).shape) == (2,)


def test_audit_runtime_shim_is_byte_equivalent_to_frozen_tensor_hasher() -> None:
    torch = pytest.importorskip("torch")
    values = torch.arange(42, dtype=torch.float32).reshape(6, 7).T[1:]
    for value in (values, values.to(torch.bfloat16), values.to(torch.int64)):
        assert audit_runtime_shim.tensor_sha256(value) == full_runtime.tensor_sha256(
            value
        )


def test_landlock_policy_is_the_frozen_abi4_narrow_claim() -> None:
    assert audit_recovery.LANDLOCK_WRITE_ACCESS_MASK == 0x7FF2
    assert audit_recovery.LANDLOCK_OUTPUT_ACCESS_MASK == 0x1B2
    assert audit_recovery.LANDLOCK_PROC_SELF_TASK_ACCESS_MASK == 0x4002
    assert audit_recovery.LANDLOCK_POLICY["directory_rule_count"] == 3
    assert audit_recovery.LANDLOCK_POLICY["device_rule_access_fs"] == 0x2
    assert audit_recovery.LANDLOCK_POLICY["metadata_and_device_ioctl_outside_claim"]


def test_relocated_bound_path_uses_canonical_posix_containment() -> None:
    root = Path("/remote/qualification/probe/output")
    child = root / "cache"
    assert audit_recovery._inside_bound_path(  # noqa: SLF001
        root, child, require_live_paths=False
    )
    assert not audit_recovery._inside_bound_path(  # noqa: SLF001
        root, root.parent / "escape", require_live_paths=False
    )
    assert not audit_recovery._inside_bound_path(  # noqa: SLF001
        root, child, require_live_paths=True
    )


def test_recovery_validator_accepts_exact_launcher_receipt_schema(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    canary_output = tmp_path / "canary-output"
    receipt_path = output / "LANDLOCK_ENFORCEMENT.json"
    child = ["/usr/bin/python3.11", "-B", "-c", "pass"]
    core = {
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
            "protected_roots": ["/workspace/raw"],
        },
        "mapping_audit": {
            "status": "pass_no_shared_file_backed_mappings",
            "mapping_count": 1,
            "shared_file_backed": [],
        },
        "directory_rules": [
            {
                "role": "output_root",
                "path": output.as_posix(),
                "allowed_access_fs": 0x1B2,
            },
            {
                "role": "canary_output_root",
                "path": canary_output.as_posix(),
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
                "st_rdev": 3,
                "major": 195,
                "minor": 0,
                "allowed_access_fs": 0x2,
            }
        ],
        "protected_checks": [
            {
                "path": "/workspace/raw/RUN_COMPLETE.json",
                "operation": "protected_file_open_write_no_write",
                "status": "denied",
                "errno": 13,
            }
        ],
        "canary_checks": {
            "status": "pass_protected_unchanged_output_empty",
            "protected_inventory_sha256_before": "a" * 64,
            "protected_inventory_sha256_after": "a" * 64,
            "protected_unchanged": True,
            "output_empty_before": True,
            "output_empty_after": True,
            "preconfinement_writable_baseline": [
                {"operation": name, "status": "allowed"}
                for name in audit_recovery.PROTECTED_CANARY_WRITABLE_BASELINE
            ],
            "protected_operations": [
                {"operation": name, "status": "denied", "errno": 13}
                for name in audit_recovery.PROTECTED_CANARY_OPERATIONS
            ],
            "output_operations": [
                {"operation": name, "status": "allowed"}
                for name in audit_recovery.OUTPUT_CANARY_ALLOWED_OPERATIONS
            ]
            + [
                {
                    "operation": name,
                    "status": "denied",
                    "errno": (
                        errno.EXDEV
                        if name == "output_cross_directory_link"
                        else errno.EACCES
                    ),
                }
                for name in audit_recovery.OUTPUT_CANARY_DENIED_OPERATIONS
            ],
        },
        "child_argv": child,
        "child_argv_sha256": protocol.canonical_sha256(child),
        "source_sha256": audit_recovery._sha256(Path(landlock_launcher.__file__)),
        "receipt_path": receipt_path.as_posix(),
        "authorization_sha256": "b" * 64,
        "preflight_receipt_sha256": "c" * 64,
    }
    receipt = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    observed = audit_recovery._validate_landlock_receipt(
        receipt,
        purpose="audit_recovery",
        receipt_path=receipt_path,
        output_root=output,
        protected_roots=[Path("/workspace/raw")],
        protected_files=[Path("/workspace/raw/RUN_COMPLETE.json")],
        canary_output_root=canary_output,
        device_files=[Path("/dev/nvidia0")],
        expected_authorization_sha256="b" * 64,
        expected_preflight_receipt_sha256="c" * 64,
        require_current_pid=False,
    )
    assert observed == receipt


def _execution_args(commit: str, stamp: str = "20260715T010203Z") -> argparse.Namespace:
    attempt_id = f"calv2-r3-audit-recovery-{commit[:7]}-{stamp}"
    root = Path(audit_recovery.RECOVERY_ATTEMPT_PARENT) / attempt_id
    original = root / "evidence/original"
    superseded = root / "evidence/superseded_recovery_host"
    fresh = root / "evidence/fresh"
    preflight = root / "preflight"
    output = root / "output"
    canary = root / "landlock_canary"
    return argparse.Namespace(
        attempt_id=attempt_id,
        active_root=Path("/root/consciousness_sae_audit_recovery")
        / attempt_id
        / "active",
        python_executable=Path(audit_recovery.sys.executable).resolve(),
        roots_manifest=root / audit_recovery.BOOTSTRAP_MANIFEST_RELATIVE,
        roots_manifest_sha256="d" * 64,
        provenance_root=root / "provenance_repo",
        plan_dir=(root / "provenance_repo" / protocol.CANONICAL_PLAN_RELATIVE_PATH),
        raw_root=Path("/workspace") / audit_recovery.RAW_RELATIVE,
        run_complete=original / "RUN_COMPLETE.json",
        raw_ledger=original / "REMOTE_RAW_SHA256SUMS.txt",
        raw_inventory=original / "REMOTE_RAW_INVENTORY.txt",
        failure_log=original / "calibration_audit_1a16572.log",
        original_ownership=original / "OWNERSHIP.json",
        original_guest=original / "GUEST_PREFLIGHT.json",
        original_cache=original / "CACHE_PREFLIGHT.json",
        original_authorization=original / "CALIBRATION_AUTHORIZATION.json",
        termination_audit=original / "TERMINATION_AUDIT.json",
        postdelete_inventory=original / "POSTDELETE_INVENTORY.json",
        frozen_termination=original / "frozen_lifecycle/TERMINATION.json",
        superseded_runtime_block=superseded / "PREEXECUTION_RUNTIME_BLOCK.json",
        superseded_termination_audit=superseded / "TERMINATION_AUDIT.json",
        superseded_frozen_termination=(
            superseded / "frozen_lifecycle/TERMINATION.json"
        ),
        superseded_postdelete_inventory=superseded / "POSTDELETE_INVENTORY.json",
        fresh_ownership=fresh / "OWNERSHIP.json",
        fresh_guest=fresh / "GUEST_PREFLIGHT.json",
        fresh_cache=fresh / "CACHE_PREFLIGHT.json",
        preflight_landlock=preflight / "output/LANDLOCK_ENFORCEMENT.json",
        preflight_probe=preflight / "output/LANDLOCK_CUDA_PREFLIGHT.json",
        local_test_receipt=root / "evidence/tests/LOCAL_TEST_RECEIPT.json",
        target_host_test_receipt=(
            root / "evidence/tests/TARGET_HOST_TEST_RECEIPT.json"
        ),
        target_qualification_ownership=(
            root / "evidence/tests" / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
        ),
        target_qualification_landlock=(
            root / "evidence/tests" / audit_recovery.TARGET_QUALIFICATION_LANDLOCK_NAME
        ),
        target_qualification_cuda_preflight=(
            root / "evidence/tests" / audit_recovery.TARGET_QUALIFICATION_CUDA_NAME
        ),
        preflight_output_root=preflight / "output",
        preflight_canary_protected_root=preflight / "canary/protected",
        preflight_canary_output_root=preflight / "canary/output",
        recovery_authorization=root / "RECOVERY_AUTHORIZATION.json",
        output_root=output,
        canary_protected_root=canary / "protected",
        canary_output_root=canary / "output",
        landlock_receipt=output / "LANDLOCK_ENFORCEMENT.json",
        device_file=[Path("/dev/nvidia-uvm"), Path("/dev/nvidia0")],
        model_snapshot=Path(audit_recovery.MODEL_SNAPSHOT_PATH),
        j_lens_path=Path(audit_recovery.J_LENS_PATH),
        artifact_device="cuda:0",
        audit_out=output / "compact/CALIBRATION_AUDIT.json",
        summary_out=output / "compact/CALIBRATION_SUMMARY.json",
        attempt_marker=output / "ATTEMPT_STARTED.json",
        failure_out=output / "FAILURE.json",
    )


def _sealed(core: dict) -> dict:
    return {**core, "receipt_sha256": protocol.canonical_sha256(core)}


def _write_canonical(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(protocol.canonical_json_bytes(value) + b"\n")


def _qualification_probe_files(tmp_path: Path) -> tuple[Path, Path]:
    ownership_path = tmp_path / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
    landlock_path = tmp_path / audit_recovery.TARGET_QUALIFICATION_LANDLOCK_NAME
    cuda_path = tmp_path / audit_recovery.TARGET_QUALIFICATION_CUDA_NAME
    ownership = _sealed(
        {
            "schema_version": 1,
            "status": "owned_running_isolated",
            "pod_id": "qualification-pod",
            "created_at": "2026-07-15T00:00:00.250Z",
        }
    )
    landlock = _sealed(
        {
            "schema_version": 1,
            "status": "pass_landlock_enforced",
            "purpose": "preauthorization_probe",
            "observed_abi": 6,
        }
    )
    cuda = _sealed(
        {
            "schema_version": 1,
            "status": "pass_target_free_landlock_cuda_preflight",
            "landlock_receipt_sha256": landlock["receipt_sha256"],
            "recovery_closure_sha256": "9" * 64,
            "package_versions": dict(audit_recovery.PINNED_PROBE_PACKAGE_VERSIONS),
            "provider": {
                "pod_id": "qualification-pod",
                "volume_id": protocol.NETWORK_VOLUME_ID,
                "data_center_id": protocol.DATA_CENTER_ID,
            },
            "cuda": {
                "available": True,
                "device": "cuda:0",
                "device_count": 1,
                "device_name": "NVIDIA B200",
                "device_capability": [10, 0],
                "matmul_finite": True,
                "synchronized": True,
                "raw_tensor_operations_only": True,
            },
            "model_forward_count": 0,
            "torch_module_call_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "external_or_prior_outcome_inputs": [],
            "completed_at_utc": "2026-07-15T00:01:00Z",
        }
    )
    _write_canonical(ownership_path, ownership)
    _write_canonical(landlock_path, landlock)
    _write_canonical(cuda_path, cuda)
    return landlock_path, cuda_path


def _fixture_qualification_probe_binding(
    ownership_path: Path,
    landlock_path: Path,
    cuda_path: Path,
    *,
    expected_source_test_files: list[dict],
) -> dict:
    del expected_source_test_files
    ownership = audit_recovery._json(ownership_path)
    landlock = audit_recovery._json(landlock_path)
    cuda = audit_recovery._json(cuda_path)
    return {
        "ownership_file": audit_recovery._file_record(ownership_path),
        "ownership_receipt_sha256": ownership["receipt_sha256"],
        "landlock_file": audit_recovery._file_record(landlock_path),
        "landlock_receipt_sha256": landlock["receipt_sha256"],
        "cuda_preflight_file": audit_recovery._file_record(cuda_path),
        "cuda_preflight_receipt_sha256": cuda["receipt_sha256"],
        "cuda_preflight_completed_at_utc": cuda["completed_at_utc"],
        "provider": cuda["provider"],
    }


def _test_receipt_fixture(
    tmp_path: Path, kind: str
) -> tuple[dict, list[dict], Path | None, Path | None]:
    source_test_files = audit_recovery._source_test_records()
    code_freeze = "a" * 40
    receipt_path = tmp_path / (
        audit_recovery.TARGET_HOST_TEST_RECEIPT_NAME
        if kind == "target_host"
        else audit_recovery.LOCAL_TEST_RECEIPT_NAME
    )
    landlock_path: Path | None = None
    cuda_path: Path | None = None
    target_host = None
    qualification_probe = None
    command_tail = [
        "test-receipt",
        "--kind",
        kind,
        "--code-freeze-commit",
        code_freeze,
    ]
    passed_ids = list(audit_recovery.TARGET_DESIGNATED_TEST_IDS)
    skipped_ids: list[str] = []
    if kind == "target_host":
        landlock_path, cuda_path = _qualification_probe_files(tmp_path)
        ownership_path = tmp_path / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
        qualification_probe = _fixture_qualification_probe_binding(
            ownership_path,
            landlock_path,
            cuda_path,
            expected_source_test_files=source_test_files,
        )
        target_host = {
            "pod_id": "qualification-pod",
            "volume_id": protocol.NETWORK_VOLUME_ID,
            "data_center_id": protocol.DATA_CENTER_ID,
            "kernel_release": "6.8.0",
            "landlock_abi": 6,
            "gpu": {
                "device_count": 1,
                "device_name": "NVIDIA B200",
                "device_capability": [10, 0],
                "total_memory_bytes": 180 * 1024**3,
            },
            "created_at_utc": "2026-07-15T00:00:00.250Z",
            "test_started_host_age_seconds": 119.75,
            "test_completed_host_age_seconds": 179.75,
        }
        command_tail.extend(
            [
                "--host-created-at-utc",
                target_host["created_at_utc"],
                "--qualification-ownership",
                ownership_path.as_posix(),
                "--qualification-landlock",
                landlock_path.as_posix(),
                "--qualification-cuda-preflight",
                cuda_path.as_posix(),
            ]
        )
    else:
        passed_ids = []
        skipped_ids = list(audit_recovery.TARGET_DESIGNATED_TEST_IDS)
    command_tail.extend(["--output", receipt_path.as_posix()])
    command_argv = [
        "/usr/bin/python3",
        "-m",
        "experiments.consciousness_sae_target_blind_calibration.audit_recovery",
        *command_tail,
    ]
    collected_ids = sorted({*passed_ids, *skipped_ids})
    dependencies = [
        {"name": name, "version": version}
        for name, version in sorted(
            audit_recovery.PINNED_PROBE_PACKAGE_VERSIONS.items()
        )
    ]
    core = {
        "schema_version": 1,
        "receipt_type": audit_recovery.TEST_RECEIPT_TYPE,
        "kind": kind,
        "status": audit_recovery.TEST_RECEIPT_STATUS,
        "code_freeze_commit": code_freeze,
        "observed_git_head_commit": code_freeze,
        "source_test_files": source_test_files,
        "source_test_file_count": len(source_test_files),
        "source_test_inventory_sha256": protocol.canonical_sha256(source_test_files),
        "command_argv": command_argv,
        "command": audit_recovery.shlex.join(command_argv),
        "command_argv_sha256": protocol.canonical_sha256(command_argv),
        "receipt_path": receipt_path.as_posix(),
        "pytest_argv": list(audit_recovery.FOCUSED_PYTEST_ARGV),
        "interpreter": {
            "executable": "/opt/qualification/bin/python",
            "implementation": "CPython",
            "version": "3.11.13",
            "cache_tag": "cpython-311",
        },
        "platform": {
            "system": "Linux" if kind == "target_host" else "Darwin",
            "release": "6.8.0" if kind == "target_host" else "25.5.0",
            "version": "fixture",
            "machine": "x86_64" if kind == "target_host" else "arm64",
        },
        "dependencies": dependencies,
        "dependency_inventory_sha256": protocol.canonical_sha256(dependencies),
        "collected_ids": collected_ids,
        "passed_ids": sorted(passed_ids),
        "failed_ids": [],
        "skipped_ids": sorted(skipped_ids),
        "not_run_ids": [],
        "collected_count": len(collected_ids),
        "passed_count": len(passed_ids),
        "failed_count": 0,
        "skipped_count": len(skipped_ids),
        "not_run_count": 0,
        "designated_target_ids": list(audit_recovery.TARGET_DESIGNATED_TEST_IDS),
        "started_at_utc": "2026-07-15T00:02:00Z",
        "completed_at_utc": "2026-07-15T00:03:00Z",
        "exit_code": 0,
        "target_host": target_host,
        "qualification_probe": qualification_probe,
    }
    return _sealed(core), source_test_files, landlock_path, cuda_path


def test_test_receipts_bind_code_freeze_outcomes_and_disposable_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_recovery,
        "_qualification_probe_binding",
        _fixture_qualification_probe_binding,
    )
    local, source_files, _landlock, _cuda = _test_receipt_fixture(
        tmp_path / "local", "local"
    )
    target, target_source_files, landlock, cuda = _test_receipt_fixture(
        tmp_path / "target", "target_host"
    )
    authorized_at = audit_recovery._utc("2026-07-15T00:05:00Z", "fixture authorization")
    assert (
        audit_recovery._validate_test_receipt(
            local,
            kind="local",
            expected_source_test_files=source_files,
            authorized_at=authorized_at,
        )
        == local
    )
    assert (
        audit_recovery._validate_test_receipt(
            target,
            kind="target_host",
            expected_source_test_files=target_source_files,
            qualification_ownership_path=(
                landlock.parent / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
            ),
            qualification_landlock_path=landlock,
            qualification_cuda_path=cuda,
            authorized_at=authorized_at,
        )
        == target
    )
    assert target["observed_git_head_commit"] == target["code_freeze_commit"]
    assert target["target_host"]["test_completed_host_age_seconds"] == 179.75


def test_target_receipt_producer_preserves_fractional_time_through_both_validators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code_freeze = "a" * 40
    created_at = "2026-07-15T00:00:00.250Z"
    started_at = datetime(2026, 7, 15, 0, 2, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 7, 15, 0, 3, 0, tzinfo=timezone.utc)
    receipt_root = tmp_path / "target"
    receipt_root.mkdir()
    output = receipt_root / audit_recovery.TARGET_HOST_TEST_RECEIPT_NAME
    ownership_path = receipt_root / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
    landlock_path = receipt_root / audit_recovery.TARGET_QUALIFICATION_LANDLOCK_NAME
    cuda_path = receipt_root / audit_recovery.TARGET_QUALIFICATION_CUDA_NAME
    ownership = {
        "pod_id": "qualification-pod",
        "network_volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "created_at": created_at,
    }
    provider = {
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
    }
    qualification_probe = {
        "provider": provider,
        "cuda_preflight_completed_at_utc": "2026-07-15T00:01:00Z",
    }
    target_host = {
        "pod_id": ownership["pod_id"],
        "volume_id": ownership["network_volume_id"],
        "data_center_id": ownership["data_center_id"],
        "kernel_release": "6.8.0",
        "landlock_abi": 6,
        "gpu": {
            "device_count": 1,
            "device_name": "NVIDIA B200",
            "device_capability": [10, 0],
            "total_memory_bytes": 180 * 1024**3,
        },
    }
    source_test_files = audit_recovery._source_test_records()
    dependencies = [
        {"name": name, "version": version}
        for name, version in sorted(
            audit_recovery.PINNED_PROBE_PACKAGE_VERSIONS.items()
        )
    ]
    command_argv = [
        str(audit_recovery.sys.executable),
        "-m",
        "experiments.consciousness_sae_target_blind_calibration.audit_recovery",
        "test-receipt",
        "--kind",
        "target_host",
        "--code-freeze-commit",
        code_freeze,
        "--host-created-at-utc",
        created_at,
        "--qualification-ownership",
        ownership_path.as_posix(),
        "--qualification-landlock",
        landlock_path.as_posix(),
        "--qualification-cuda-preflight",
        cuda_path.as_posix(),
        "--output",
        output.as_posix(),
    ]

    class _ReceiptDateTime(datetime):
        values = iter((started_at, completed_at))

        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            value = next(cls.values)
            return value if tz is None else value.astimezone(tz)

    def _fake_pytest_main(argv, *, plugins):  # noqa: ANN001
        assert argv == list(audit_recovery.FOCUSED_PYTEST_ARGV)
        collector = plugins[0]
        items = [
            argparse.Namespace(nodeid=node_id)
            for node_id in audit_recovery.TARGET_DESIGNATED_TEST_IDS
        ]
        collector.pytest_collection_finish(argparse.Namespace(items=items))
        for node_id in audit_recovery.TARGET_DESIGNATED_TEST_IDS:
            collector.pytest_runtest_logreport(
                argparse.Namespace(
                    nodeid=node_id,
                    failed=False,
                    skipped=False,
                    when="call",
                    passed=True,
                )
            )
        return 0

    monkeypatch.setattr(audit_recovery, "datetime", _ReceiptDateTime)
    monkeypatch.setattr(audit_recovery, "_git_head", lambda: code_freeze)
    monkeypatch.setattr(
        audit_recovery,
        "_require_code_freeze_ancestor",
        lambda _code_freeze, _observed_head: None,
    )
    monkeypatch.setattr(
        audit_recovery, "_source_test_records", lambda: source_test_files
    )
    monkeypatch.setattr(
        audit_recovery, "_validate_qualification_ownership", lambda _path: ownership
    )
    monkeypatch.setattr(
        audit_recovery,
        "_qualification_probe_binding",
        lambda *_args, **_kwargs: qualification_probe,
    )
    monkeypatch.setattr(
        audit_recovery, "_target_host_test_environment", lambda _value: target_host
    )
    monkeypatch.setattr(
        audit_recovery, "_installed_distributions", lambda: dependencies
    )
    monkeypatch.setattr(audit_recovery.sys, "orig_argv", command_argv)
    monkeypatch.setattr(audit_recovery.platform, "system", lambda: "Linux")
    monkeypatch.setattr(audit_recovery.platform, "release", lambda: "6.8.0")
    monkeypatch.setattr(audit_recovery.platform, "version", lambda: "fixture")
    monkeypatch.setattr(audit_recovery.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        audit_recovery.platform, "python_implementation", lambda: "CPython"
    )
    monkeypatch.setattr(audit_recovery.platform, "python_version", lambda: "3.11.13")
    monkeypatch.setattr(pytest, "main", _fake_pytest_main)

    receipt, exit_code = audit_recovery.run_test_receipt(
        argparse.Namespace(
            kind="target_host",
            code_freeze_commit=code_freeze,
            host_created_at_utc=created_at,
            qualification_ownership=ownership_path,
            qualification_landlock=landlock_path,
            qualification_cuda_preflight=cuda_path,
            output=output,
        )
    )

    assert exit_code == 0
    assert receipt["target_host"]["created_at_utc"] == created_at
    assert receipt["target_host"]["test_started_host_age_seconds"] == 119.75
    assert receipt["target_host"]["test_completed_host_age_seconds"] == 179.75
    authorized_at = audit_recovery._utc("2026-07-15T00:05:00Z", "fixture authorization")
    assert (
        audit_recovery._validate_test_receipt(
            receipt,
            kind="target_host",
            expected_source_test_files=source_test_files,
            qualification_ownership_path=ownership_path,
            qualification_landlock_path=landlock_path,
            qualification_cuda_path=cuda_path,
            authorized_at=authorized_at,
        )
        == receipt
    )
    monkeypatch.setattr(
        recovery_bundle_verifier,
        "_validate_qualification_chain",
        lambda **_kwargs: (
            {"pod_id": ownership["pod_id"], "created_at": created_at},
            datetime(2026, 7, 15, 0, 1, 0, tzinfo=timezone.utc),
        ),
    )
    assert (
        recovery_bundle_verifier._validate_test_receipt(
            receipt,
            kind="target_host",
            expected_source_test_files=source_test_files,
            qualification_ownership={},
            qualification_landlock={},
            qualification_cuda={},
            qualification_ownership_path=ownership_path,
            qualification_landlock_path=landlock_path,
            qualification_cuda_path=cuda_path,
            authorized_at=datetime(2026, 7, 15, 0, 5, 0, tzinfo=timezone.utc),
        )
        == receipt
    )


def test_target_test_receipt_rejects_skipped_designated_live_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_recovery,
        "_qualification_probe_binding",
        _fixture_qualification_probe_binding,
    )
    target, source_files, landlock, cuda = _test_receipt_fixture(
        tmp_path, "target_host"
    )
    designated = audit_recovery.TARGET_DESIGNATED_TEST_IDS[0]
    target["passed_ids"] = []
    target["skipped_ids"] = [designated]
    target["passed_count"] = 0
    target["skipped_count"] = 1
    core = dict(target)
    core.pop("receipt_sha256")
    target["receipt_sha256"] = protocol.canonical_sha256(core)
    with pytest.raises(audit_recovery.AuditRecoveryError, match="target-host"):
        audit_recovery._validate_test_receipt(
            target,
            kind="target_host",
            expected_source_test_files=source_files,
            qualification_ownership_path=(
                landlock.parent / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
            ),
            qualification_landlock_path=landlock,
            qualification_cuda_path=cuda,
            authorized_at=audit_recovery._utc(
                "2026-07-15T00:05:00Z", "fixture authorization"
            ),
        )


def test_target_test_receipt_rejects_changed_qualification_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_recovery,
        "_qualification_probe_binding",
        _fixture_qualification_probe_binding,
    )
    target, source_files, landlock, cuda = _test_receipt_fixture(
        tmp_path, "target_host"
    )
    assert landlock is not None and cuda is not None
    cuda.write_bytes(cuda.read_bytes() + b" ")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="target-host"):
        audit_recovery._validate_test_receipt(
            target,
            kind="target_host",
            expected_source_test_files=source_files,
            qualification_ownership_path=(
                landlock.parent / audit_recovery.TARGET_QUALIFICATION_OWNERSHIP_NAME
            ),
            qualification_landlock_path=landlock,
            qualification_cuda_path=cuda,
            authorized_at=audit_recovery._utc(
                "2026-07-15T00:05:00Z", "fixture authorization"
            ),
        )


def test_test_receipt_parser_exposes_frozen_receipt_command() -> None:
    parsed = audit_recovery.build_parser().parse_args(
        [
            "test-receipt",
            "--kind",
            "local",
            "--code-freeze-commit",
            "a" * 40,
            "--output",
            "/tmp/LOCAL_TEST_RECEIPT.json",
        ]
    )
    assert parsed.command == "test-receipt"
    assert parsed.kind == "local"


def test_provider_host_creation_preserves_canonical_fractional_utc() -> None:
    value = "2026-07-15T00:00:00.250123456Z"
    observed = audit_recovery._provider_utc(value, "provider timestamp")
    assert observed.microsecond == 250_123
    assert value.endswith(".250123456Z")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="canonical UTC"):
        audit_recovery._provider_utc(
            "2026-07-15T00:00:00.1234567890Z", "provider timestamp"
        )


def _roots_manifest_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, str, dict]:
    active = (tmp_path / "active").resolve()
    dependency = (tmp_path / "dependency").resolve()
    bootstrap_path = active / audit_recovery.confined_bootstrap.BOOTSTRAP_RELATIVE_PATH
    bootstrap_path.parent.mkdir(parents=True)
    bootstrap_path.write_bytes(
        Path(audit_recovery.confined_bootstrap.__file__).read_bytes()
    )
    dependency.mkdir()
    manifest = audit_recovery.confined_bootstrap.build_roots_manifest(
        python_executable=Path(audit_recovery.sys.executable).resolve(),
        active_root=active,
        dependency_roots=(("approved_dependencies", dependency),),
    )
    path = (tmp_path / "bootstrap/APPROVED_IMPORT_ROOTS.json").resolve()
    path.parent.mkdir()
    physical_sha256 = audit_recovery.confined_bootstrap.write_roots_manifest_exclusive(
        path, manifest
    )
    return active, path, physical_sha256, manifest


def test_audit_authority_revalidates_full_bootstrap_manifest_and_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        audit_recovery.sys,
        "executable",
        Path(audit_recovery.sys.executable).resolve().as_posix(),
    )
    active, path, physical_sha256, manifest = _roots_manifest_fixture(tmp_path)
    monkeypatch.setattr(
        audit_recovery.confined_bootstrap,
        "__file__",
        (active / audit_recovery.confined_bootstrap.BOOTSTRAP_RELATIVE_PATH).as_posix(),
    )
    binding = audit_recovery._bootstrap_manifest_binding(
        path,
        expected_file_sha256=physical_sha256,
        active_root=active,
    )
    assert binding["manifest"] == manifest
    assert binding["physical_file"]["sha256"] == physical_sha256
    roots, files = audit_recovery._bootstrap_protected_paths(binding)
    assert active in roots
    assert path.parent in roots
    assert path in files
    assert (active / audit_recovery.confined_bootstrap.BOOTSTRAP_RELATIVE_PATH) in files

    guards = {
        "status": "process_lifetime_guards_installed",
        "forbidden_module_import_attempts": 0,
        "forbidden_startup_import_attempts": 0,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "patched_modules": list(audit_recovery.BOOTSTRAP_GUARDED_MODULES),
    }
    core = {
        "schema_version": audit_recovery.confined_bootstrap.SCHEMA_VERSION,
        "status": "pass_hash_bound_confined_bootstrap",
        "mode": "preflight-child",
        "pid": 123,
        "active_root": active.as_posix(),
        "python_executable": Path(audit_recovery.sys.executable).resolve().as_posix(),
        "roots_manifest_path": path.as_posix(),
        "roots_manifest_file_sha256": physical_sha256,
        "roots_manifest_receipt_sha256": manifest["receipt_sha256"],
        "roots_inventory_sha256": manifest["roots_inventory_sha256"],
        "sys_path": manifest["sys_path"],
        "bootstrap_sha256": manifest["bootstrap_sha256"],
        "site_imported": False,
        "startup_project_or_ml_module_count": 0,
        "guards": guards,
    }
    attestation = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    observed = audit_recovery._validate_bootstrap_attestation(
        attestation,
        mode="preflight-child",
        expected_pid=123,
        active_root=active,
        python_executable=Path(audit_recovery.sys.executable).resolve(),
        roots_manifest_path=path,
        roots_manifest_sha256=physical_sha256,
        manifest=manifest,
    )
    phase = audit_recovery._bootstrap_phase_record(
        audit_recovery.BOOTSTRAP_PREFLIGHT_PHASE, observed
    )
    assert (
        audit_recovery._self_hash(phase, "bootstrap phase") == phase["receipt_sha256"]
    )

    (active / "unbound.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="manifest differs"):
        audit_recovery._bootstrap_manifest_binding(
            path,
            expected_file_sha256=physical_sha256,
            active_root=active,
        )


def test_execution_binding_is_exact_and_commit_scoped() -> None:
    commit = "a" * 40
    args = _execution_args(commit)
    binding = audit_recovery._execution_binding(
        args, git_head=commit, validate_execute_paths=True
    )
    assert binding["attempt_id"] == args.attempt_id
    assert binding["paths"]["provenance_root"] == args.provenance_root.as_posix()
    assert binding["confined_child_argv"][0] == args.python_executable.as_posix()
    assert binding["confined_child_argv_sha256"] == protocol.canonical_sha256(
        binding["confined_child_argv"]
    )
    child_argv = binding["confined_child_argv"]
    separator = child_argv.index("--")
    parsed = audit_recovery.build_parser().parse_args(
        ["execute-confined", *child_argv[separator + 1 :]]
    )
    assert parsed.command == "execute-confined"
    assert parsed.active_root == args.active_root
    assert parsed.python_executable == args.python_executable
    assert parsed.roots_manifest == args.roots_manifest
    assert parsed.roots_manifest_sha256 == args.roots_manifest_sha256
    assert child_argv[1:5] == ["-B", "-E", "-s", "-S"]
    assert (
        child_argv[5]
        == (
            args.active_root / audit_recovery.confined_bootstrap.BOOTSTRAP_RELATIVE_PATH
        ).as_posix()
    )
    assert "-m" not in child_argv[:separator]
    args.summary_out = args.summary_out.with_name("OTHER.json")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="path binding"):
        audit_recovery._execution_binding(
            args, git_head=commit, validate_execute_paths=True
        )


def test_execution_binding_rejects_non_nvidia_device() -> None:
    commit = "a" * 40
    args = _execution_args(commit)
    args.device_file = [Path("/dev/null")]
    with pytest.raises(audit_recovery.AuditRecoveryError, match="device-file"):
        audit_recovery._execution_binding(
            args, git_head=commit, validate_execute_paths=True
        )


def test_issue_output_is_bound_to_authorized_path() -> None:
    commit = "a" * 40
    args = _execution_args(commit)
    binding = audit_recovery._execution_binding(
        args, git_head=commit, validate_execute_paths=False
    )
    expected = Path(binding["paths"]["recovery_authorization"])
    assert audit_recovery._validate_issue_output(expected, binding) == expected
    with pytest.raises(audit_recovery.AuditRecoveryError, match="output binding"):
        audit_recovery._validate_issue_output(expected.with_name("OTHER.json"), binding)


def test_inside_rejects_lexical_parent_escape(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    assert audit_recovery._inside(output, output)
    assert audit_recovery._inside(output, output / "cache")
    assert not audit_recovery._inside(output, output / ".." / "raw")


def test_confined_environment_rejects_forbidden_and_parent_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    for name, value in audit_recovery.CONFINED_FIXED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    for name in audit_recovery.CONFINED_WRITABLE_PATH_ENVIRONMENT:
        monkeypatch.setenv(name, output.as_posix())
    for name in audit_recovery.FORBIDDEN_CONFINED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    observed = audit_recovery._validate_confinement_environment(output)
    assert observed["PYTHONNOUSERSITE"] == "1"

    monkeypatch.setenv("PYTHONPATH", "/tmp/injected")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="forbidden"):
        audit_recovery._validate_confinement_environment(output)
    monkeypatch.delenv("PYTHONPATH")
    monkeypatch.setenv("PYTHONSTARTUP", "")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="forbidden"):
        audit_recovery._validate_confinement_environment(output)
    monkeypatch.delenv("PYTHONSTARTUP")
    monkeypatch.setenv("TMPDIR", (output / ".." / "raw").as_posix())
    with pytest.raises(audit_recovery.AuditRecoveryError, match="escaped"):
        audit_recovery._validate_confinement_environment(output)


def test_preflight_child_argv_binds_exact_executable_cwd_and_inputs() -> None:
    argv = audit_recovery._preflight_child_argv(
        python_executable="/opt/venv/bin/python",
        active_root="/root/active",
        roots_manifest="/workspace/attempt/bootstrap/APPROVED_IMPORT_ROOTS.json",
        roots_manifest_sha256="d" * 64,
        landlock_receipt="/workspace/attempt/preflight/output/LANDLOCK_ENFORCEMENT.json",
        output_root="/workspace/attempt/preflight/output",
        canary_protected_root="/workspace/attempt/preflight/canary/protected",
        canary_output_root="/workspace/attempt/preflight/canary/output",
        device_files=["/dev/nvidia0", "/dev/nvidiactl"],
        output="/workspace/attempt/preflight/output/LANDLOCK_CUDA_PREFLIGHT.json",
    )
    separator = argv.index("--")
    parsed = audit_recovery.build_parser().parse_args(
        ["preflight-child", *argv[separator + 1 :]]
    )
    assert parsed.command == "preflight-child"
    assert parsed.active_root == Path("/root/active")
    assert parsed.python_executable == Path("/opt/venv/bin/python")
    assert parsed.roots_manifest == Path(
        "/workspace/attempt/bootstrap/APPROVED_IMPORT_ROOTS.json"
    )
    assert parsed.roots_manifest_sha256 == "d" * 64
    assert parsed.device_file == [Path("/dev/nvidia0"), Path("/dev/nvidiactl")]
    assert argv[1:5] == ["-B", "-E", "-s", "-S"]
    assert argv[5] == (
        "/root/active/" + audit_recovery.confined_bootstrap.BOOTSTRAP_RELATIVE_PATH
    )


def test_fresh_authority_clock_cannot_be_renewed_by_rehashing_receipt() -> None:
    created = datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc).timestamp()
    ownership = {
        "created_at": "2026-07-15T01:00:00Z",
        "terminate_after": "2026-07-15T07:00:00Z",
    }
    receipt = {
        "recovery_started_at_unix": created,
        "recovery_deadline_at_unix": created + 3600,
        "provider_deadline_at_unix": created + 21600,
        "authorized_at_utc": "2026-07-15T01:02:00Z",
    }
    audit_recovery._validate_fresh_authority_clock(
        receipt, ownership, now_unix=created + 300
    )
    tampered = dict(receipt)
    tampered["recovery_started_at_unix"] += 60
    tampered["recovery_deadline_at_unix"] += 60
    with pytest.raises(audit_recovery.AuditRecoveryError, match="ownership-bound"):
        audit_recovery._validate_fresh_authority_clock(
            tampered, ownership, now_unix=created + 300
        )


def test_provenance_tree_requires_exact_hash_bound_inventory(tmp_path: Path) -> None:
    root = tmp_path / "provenance"
    (root / "nested").mkdir(parents=True)
    first = root / "a.txt"
    second = root / "nested/b.txt"
    first.write_bytes(b"alpha")
    second.write_bytes(b"beta")
    rows = [
        {"path": "a.txt", "bytes": 5, "sha256": audit_recovery._sha256(first)},
        {
            "path": "nested/b.txt",
            "bytes": 4,
            "sha256": audit_recovery._sha256(second),
        },
    ]
    receipt = audit_recovery._validate_provenance_tree(root, rows)
    assert receipt["file_count"] == 2
    second.write_bytes(b"changed")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="provenance differs"):
        audit_recovery._validate_provenance_tree(root, rows)


@pytest.mark.parametrize("kind", ["extra_directory", "fifo"])
def test_provenance_tree_rejects_unmanifested_topology(
    tmp_path: Path, kind: str
) -> None:
    root = tmp_path / "provenance"
    root.mkdir()
    first = root / "a.txt"
    first.write_bytes(b"alpha")
    rows = [{"path": "a.txt", "bytes": 5, "sha256": audit_recovery._sha256(first)}]
    if kind == "extra_directory":
        (root / "extra").mkdir()
    else:
        os.mkfifo(root / "extra.fifo")
    with pytest.raises(
        audit_recovery.AuditRecoveryError,
        match="extra directory|special file",
    ):
        audit_recovery._validate_provenance_tree(root, rows)


@pytest.mark.parametrize("kind", ["extra_directory", "fifo"])
def test_raw_tree_rejects_unmanifested_topology(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    ledger = tmp_path / "REMOTE_RAW_SHA256SUMS.txt"
    ledger.write_text("", encoding="utf-8")
    if kind == "extra_directory":
        (root / "extra").mkdir()
    else:
        os.mkfifo(root / "extra.fifo")
    with pytest.raises(
        audit_recovery.AuditRecoveryError,
        match="extra directory|special file",
    ):
        audit_recovery._rehash_raw_tree(root, ledger)


def test_superseded_recovery_host_evidence_is_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sealed(core: dict) -> dict:
        return {**core, "receipt_sha256": protocol.canonical_sha256(core)}

    frozen = sealed(
        {
            "pod_id": audit_recovery.SUPERSEDED_RECOVERY_POD_ID,
            "status": "deleted_verified",
            "absent_from_account_inventory": True,
            "other_pods_mutated": False,
        }
    )
    postdelete = sealed({"pods": [], "all_account_pod_count": 0})
    termination = sealed(
        {
            "pod_id": audit_recovery.SUPERSEDED_RECOVERY_POD_ID,
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            "frozen_termination_receipt_sha256": frozen["receipt_sha256"],
        }
    )
    runtime_core = {
        "receipt_type": "audit_recovery_preexecution_runtime_block_v1",
        "status": "blocked_before_attempt_claim_missing_cap_sys_admin",
        "pod_id": audit_recovery.SUPERSEDED_RECOVERY_POD_ID,
        "attempt_id": audit_recovery.SUPERSEDED_RECOVERY_ATTEMPT_ID,
        "audit_execute_invoked": False,
        "attempt_marker_exists_at_pretermination": False,
        "failure_receipt_exists_at_pretermination": False,
        "compact_directory_exists_at_pretermination": False,
        "landlock_abi": 4,
        "network_volume_deleted": False,
        "provider_postdelete_pod_count": 0,
        "termination_audit_receipt_sha256": termination["receipt_sha256"],
        "frozen_termination_receipt_sha256": frozen["receipt_sha256"],
        "postdelete_inventory_receipt_sha256": postdelete["receipt_sha256"],
    }
    runtime = sealed(runtime_core)
    paths = {
        "superseded_runtime_block": tmp_path / "PREEXECUTION_RUNTIME_BLOCK.json",
        "superseded_termination_audit": tmp_path / "TERMINATION_AUDIT.json",
        "superseded_frozen_termination": tmp_path / "TERMINATION.json",
        "superseded_postdelete_inventory": tmp_path / "POSTDELETE_INVENTORY.json",
    }
    for name, value in (
        ("superseded_runtime_block", runtime),
        ("superseded_termination_audit", termination),
        ("superseded_frozen_termination", frozen),
        ("superseded_postdelete_inventory", postdelete),
    ):
        paths[name].write_bytes(protocol.canonical_json_bytes(value) + b"\n")
    monkeypatch.setattr(
        audit_recovery, "SUPERSEDED_RUNTIME_BLOCK_SHA256", runtime["receipt_sha256"]
    )
    monkeypatch.setattr(
        audit_recovery,
        "SUPERSEDED_TERMINATION_AUDIT_SHA256",
        termination["receipt_sha256"],
    )
    monkeypatch.setattr(
        audit_recovery,
        "SUPERSEDED_FROZEN_TERMINATION_SHA256",
        frozen["receipt_sha256"],
    )
    monkeypatch.setattr(
        audit_recovery,
        "SUPERSEDED_POSTDELETE_INVENTORY_SHA256",
        postdelete["receipt_sha256"],
    )
    observed = audit_recovery._validate_superseded_recovery_host(
        argparse.Namespace(**paths)
    )
    assert observed["audit_execute_invoked"] is False
    assert observed["attempt_marker_present"] is False

    tampered = sealed({**runtime_core, "audit_execute_invoked": True})
    paths["superseded_runtime_block"].write_bytes(
        protocol.canonical_json_bytes(tampered) + b"\n"
    )
    monkeypatch.setattr(
        audit_recovery, "SUPERSEDED_RUNTIME_BLOCK_SHA256", tampered["receipt_sha256"]
    )
    with pytest.raises(audit_recovery.AuditRecoveryError, match="evidence differs"):
        audit_recovery._validate_superseded_recovery_host(argparse.Namespace(**paths))


def test_historical_incomplete_review_evidence_remains_immutable() -> None:
    observed = audit_recovery._validate_historical_incomplete_review_evidence()
    assert observed["final_decision"] == "NOT_READY_TO_EXECUTE"
    assert observed["execution_authorized"] is False
    assert observed["provider_review"]["response_status"] == "incomplete"


@pytest.mark.parametrize(
    ("verdict_section", "expected"),
    [
        ("A positive explanation only mentions READY TO FREEZE.", "terminal verdict"),
        ("NOT READY TO FREEZE", "NOT READY TO FREEZE"),
        ("**READY AFTER SPECIFIED FIXES**", "READY AFTER SPECIFIED FIXES"),
        ("READY TO FREEZE", "READY TO FREEZE"),
        (
            "NOT READY TO FREEZE\nREADY TO FREEZE",
            "terminal verdict differs",
        ),
    ],
)
def test_completed_review_terminal_verdict_is_exact(
    verdict_section: str, expected: str
) -> None:
    review = f"# Verdict\n\n{verdict_section}\n\n# Blocking findings\n\nnone\n"
    if expected in audit_recovery.PRO_REVIEW_TERMINAL_VERDICTS:
        assert audit_recovery._terminal_review_verdict(review) == expected  # noqa: SLF001
    else:
        with pytest.raises(audit_recovery.AuditRecoveryError, match=expected):
            audit_recovery._terminal_review_verdict(review)  # noqa: SLF001


def test_review_finding_ids_use_real_word_boundaries() -> None:
    review = "B06 I04 XB07Y B06 B9 I123 B08."
    assert audit_recovery._review_finding_ids(review) == [  # noqa: SLF001
        "B06",
        "B08",
        "I04",
    ]


def test_historical_v2_completed_negative_review_is_pinned() -> None:
    observed = audit_recovery._validate_historical_v2_review_evidence()
    assert observed["terminal_verdict"] == "NOT READY TO FREEZE"
    assert observed["remaining_blocking_findings"] == ["B06", "B07", "B08", "B09"]
    assert observed["input_tokens"] == 823115
    assert observed["output_tokens"] == 30179
    assert observed["reasoning_tokens"] == 11842
    assert observed["reconstructed_cost_usd"] == 5.020945


def test_historical_v3_completed_negative_review_is_pinned() -> None:
    observed = audit_recovery._validate_historical_v3_negative_review_evidence()
    assert observed["terminal_verdict"] == "NOT READY TO FREEZE"
    assert observed["remaining_blocking_findings"] == ["B10", "B11"]
    assert observed["input_tokens"] == 1_051_523
    assert observed["output_tokens"] == 28_895
    assert observed["reasoning_tokens"] == 10_935
    assert observed["reconstructed_cost_usd"] == 6.124465


def test_historical_v4_completed_negative_review_is_pinned() -> None:
    observed = audit_recovery._validate_historical_v4_negative_review_evidence()
    assert observed["terminal_verdict"] == "NOT READY TO FREEZE"
    assert observed["remaining_blocking_findings"] == ["B12"]
    assert observed["input_tokens"] == 1_129_614
    assert observed["output_tokens"] == 27_987
    assert observed["reasoning_tokens"] == 8_904
    assert observed["reconstructed_cost_usd"] == 6.48768


def test_v5_review_packet_includes_equivalence_receipts_and_v4_negative() -> None:
    paths = {path for path, _role in audit_recovery.PRO_REVIEW_V5_PACKET}
    roles = [role for _path, role in audit_recovery.PRO_REVIEW_V5_PACKET]
    assert not paths & set(audit_recovery.FINAL_V5_PRO_REVIEW_OUTPUT_PATHS)
    assert {
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
        audit_recovery.V5_LOCAL_TEST_RECEIPT_SNAPSHOT,
        audit_recovery.V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
        *audit_recovery.V4_TIMED_QUALIFICATION_PHYSICAL_SHA256,
        f"{audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review.md",
        f"{audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
    } <= paths
    assert {
        f"{audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review.md",
        f"{audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
    }.isdisjoint(paths)
    assert roles == [
        "complete experiment plan",
        *(f"bounded context {index}" for index in range(1, len(roles))),
    ]


def test_v5_review_resource_ceilings_are_symmetric_and_cover_hard_cap() -> None:
    assert audit_recovery.PRO_REVIEW_BUDGET_AUTHORIZATION_USD == (
        recovery_bundle_verifier.COMPLETED_REVIEW_COST_CEILING_USD
    )
    assert audit_recovery.PRO_REVIEW_MAX_INPUT_CHARACTERS == 1_450_000
    assert audit_recovery.PRO_REVIEW_MAX_INPUT_TOKENS == 450_000
    assert audit_recovery.PRO_REVIEW_CHARS_PER_TOKEN_ASSUMPTION == 3.5
    limits = audit_recovery._validate_v5_packet_limits(  # noqa: SLF001
        "x" * audit_recovery.PRO_REVIEW_MAX_INPUT_CHARACTERS,
        "",
    )
    assert limits["estimated_budget_reserve_usd"] <= (
        audit_recovery.PRO_REVIEW_BUDGET_AUTHORIZATION_USD
    )


def test_v5_review_input_uses_real_newline_delimited_artifact_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "plan.md").write_text("# frozen plan\n", encoding="utf-8")
    (tmp_path / "context.txt").write_text("bounded context\n", encoding="utf-8")
    monkeypatch.setattr(audit_recovery, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        audit_recovery,
        "PRO_REVIEW_V5_PACKET",
        (
            ("plan.md", "complete experiment plan"),
            ("context.txt", "bounded context 1"),
        ),
    )
    value = audit_recovery._expected_v5_pro_review_input()
    assert "<artifact_1>\n# frozen plan\n\n</artifact_1>" in value
    assert "<artifact_2>\nbounded context\n\n</artifact_2>" in value
    request = "# Developer instructions\n\nreview rules\n\n" + value
    assert request.startswith(
        "# Developer instructions\n\nreview rules\n\n# Review packet\n"
    )


def test_v5_review_git_chain_rejects_nonancestor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        audit_recovery,
        "_git_command",
        lambda *parts, **kwargs: argparse.Namespace(returncode=1),
    )
    with pytest.raises(audit_recovery.AuditRecoveryError, match="C<=E<=F"):
        audit_recovery._validate_v5_git_chain(
            code_freeze_commit="1" * 40,
            reviewed_packet_git_head_commit="2" * 40,
            final_git_head_commit="3" * 40,
        )


def _v5_adjudication_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict, Path]:
    review_root = tmp_path / "review"
    review_root.mkdir()
    for name in (
        "response.json",
        "review_manifest.json",
        "request_payload.json",
        "review_request.md",
    ):
        (review_root / name).write_text(f"{name}\n", encoding="utf-8")
    (tmp_path / "plan.md").write_text("frozen packet\n", encoding="utf-8")
    finding_ids = list(audit_recovery.HISTORICAL_V4_NEGATIVE_FINDING_IDS)
    markdown_path = tmp_path / "ADJUDICATION.md"
    markdown_path.write_text(
        "# V5 adjudication\n\n"
        + " ".join(finding_ids)
        + "\n\nFinal execution decision: **READY TO EXECUTE**.\n",
        encoding="utf-8",
    )
    json_path = tmp_path / "ADJUDICATION.json"
    monkeypatch.setattr(audit_recovery, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(audit_recovery, "FINAL_V5_PRO_REVIEW_DIRECTORY", "review")
    monkeypatch.setattr(
        audit_recovery,
        "FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON",
        "ADJUDICATION.json",
    )
    monkeypatch.setattr(
        audit_recovery,
        "FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN",
        "ADJUDICATION.md",
    )
    monkeypatch.setattr(
        audit_recovery,
        "HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON",
        "historical-v4/ADJUDICATION.json",
    )
    monkeypatch.setattr(
        audit_recovery,
        "PRO_REVIEW_V5_PACKET",
        (("plan.md", "complete experiment plan"),),
    )
    historical_v4 = {
        "adjudication_json_sha256": "6" * 64,
        "adjudication_receipt_sha256": "7" * 64,
        "response_id": "resp_historical_v4",
        "terminal_verdict": "NOT READY TO FREEZE",
        "remaining_blocking_findings": ["B12"],
        "finding_ids": list(finding_ids),
    }
    reviewed_evidence = {"code_freeze_commit": "1" * 40}
    response = {"id": "resp_v5"}
    review_sha256 = "3" * 64
    response_semantic_sha256 = "4" * 64
    review_input_sha256 = "5" * 64
    reviewed_packet_commit = "2" * 40
    review_binding = {
        "review_directory": "review",
        "provider_response_id": "resp_v5",
        "provider_response_file_sha256": audit_recovery._sha256(  # noqa: SLF001
            review_root / "response.json"
        ),
        "provider_response_semantic_sha256": response_semantic_sha256,
        "provider_review_sha256": review_sha256,
        "provider_manifest_file_sha256": audit_recovery._sha256(  # noqa: SLF001
            review_root / "review_manifest.json"
        ),
        "request_payload_file_sha256": audit_recovery._sha256(  # noqa: SLF001
            review_root / "request_payload.json"
        ),
        "review_request_file_sha256": audit_recovery._sha256(  # noqa: SLF001
            review_root / "review_request.md"
        ),
        "review_input_sha256": review_input_sha256,
        "review_instructions_sha256": audit_recovery.PRO_REVIEW_INSTRUCTIONS_SHA256,
        "reviewed_packet_git_head_commit": reviewed_packet_commit,
        "code_freeze_commit": reviewed_evidence["code_freeze_commit"],
        "adjudication_markdown_path": "ADJUDICATION.md",
        "adjudication_markdown_sha256": audit_recovery._sha256(  # noqa: SLF001
            markdown_path
        ),
    }
    core = {
        "schema_version": 5,
        "artifact_type": "completed_provider_review_v5_adjudication",
        "review_binding": review_binding,
        "historical_v4_binding": {
            "adjudication_path": "historical-v4/ADJUDICATION.json",
            "adjudication_file_sha256": historical_v4[
                "adjudication_json_sha256"
            ],
            "adjudication_receipt_sha256": historical_v4[
                "adjudication_receipt_sha256"
            ],
            "provider_response_id": historical_v4["response_id"],
            "terminal_verdict": historical_v4["terminal_verdict"],
            "remaining_blocking_findings": ["B12"],
        },
        "reviewed_qualification_evidence": reviewed_evidence,
        "finding_ids": finding_ids,
        "findings": [
            {
                "id": finding_id,
                "blocking": finding_id.startswith("B"),
                "disposition": (
                    "fixed" if finding_id.startswith("B") else "rejected"
                ),
                "rationale": "exact reviewed-byte disposition",
                "changed_paths": (
                    ["plan.md"] if finding_id.startswith("B") else []
                ),
            }
            for finding_id in finding_ids
        ],
        "resolved_v4_remaining_findings": ["B12"],
        "final_decision": "READY_TO_EXECUTE",
    }
    _write_canonical(json_path, _sealed(core))
    kwargs = {
        "root": review_root,
        "response": response,
        "response_semantic_sha256": response_semantic_sha256,
        "review_sha256": review_sha256,
        "review_input_sha256": review_input_sha256,
        "finding_ids": finding_ids,
        "historical_v4": historical_v4,
        "reviewed_evidence": reviewed_evidence,
        "reviewed_packet_git_head_commit": reviewed_packet_commit,
    }
    return core, kwargs, json_path


def test_v5_ready_only_adjudication_accepts_exact_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _core, kwargs, _json_path = _v5_adjudication_fixture(tmp_path, monkeypatch)
    observed = audit_recovery._validate_v5_review_adjudication(**kwargs)
    assert observed["fixed_finding_ids"] == [
        finding
        for finding in audit_recovery.HISTORICAL_V4_NEGATIVE_FINDING_IDS
        if finding.startswith("B")
    ]
    assert observed["rejected_finding_ids"] == [
        finding
        for finding in audit_recovery.HISTORICAL_V4_NEGATIVE_FINDING_IDS
        if finding.startswith("I")
    ]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_b12", "omitted a historical finding ID"),
        ("recycled_b05", "recycled a reserved finding ID"),
        ("outside_packet", "finding rows differ"),
        ("not_ready", "binding differs"),
    ],
)
def test_v5_ready_only_adjudication_rejects_invalid_closure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    message: str,
) -> None:
    core, kwargs, json_path = _v5_adjudication_fixture(tmp_path, monkeypatch)
    if mutation == "missing_b12":
        core["finding_ids"].remove("B12")
        core["findings"] = [row for row in core["findings"] if row["id"] != "B12"]
        kwargs["finding_ids"] = core["finding_ids"]
    elif mutation == "recycled_b05":
        core["finding_ids"] = sorted([*core["finding_ids"], "B05"])
        core["findings"].append(
            {
                "id": "B05",
                "blocking": True,
                "disposition": "fixed",
                "rationale": "invalid recycled identifier",
                "changed_paths": ["plan.md"],
            }
        )
        kwargs["finding_ids"] = core["finding_ids"]
    elif mutation == "outside_packet":
        next(row for row in core["findings"] if row["id"] == "B12")[
            "changed_paths"
        ] = ["outside.txt"]
    else:
        core["final_decision"] = "NOT_READY_TO_EXECUTE"
    _write_canonical(json_path, _sealed(core))
    with pytest.raises(audit_recovery.AuditRecoveryError, match=message):
        audit_recovery._validate_v5_review_adjudication(**kwargs)


def test_attempt_claim_is_one_shot_and_failure_receipt_is_sealed(
    tmp_path: Path,
) -> None:
    source_hash = "a" * 64
    output = tmp_path / "output"
    output.mkdir()
    landlock_receipt = output / "LANDLOCK_ENFORCEMENT.json"
    landlock_receipt.write_text("{}", encoding="utf-8")
    args = argparse.Namespace(
        output_root=output,
        landlock_receipt=landlock_receipt,
        attempt_marker=output / "ATTEMPT_STARTED.json",
        failure_out=output / "FAILURE.json",
        audit_out=output / "compact/CALIBRATION_AUDIT.json",
    )
    authorization = {
        "receipt_sha256": "b" * 64,
        "recovery_started_at_unix": 0.0,
        "recovery_deadline_at_unix": 4_000_000_000.0,
        "execution": {
            "attempt_id": "test-attempt",
            "attempt_root": tmp_path.as_posix(),
            "command_sha256": "c" * 64,
            "paths": {
                "output_root": output.as_posix(),
                "landlock_receipt": landlock_receipt.as_posix(),
            },
        },
        "recovery_bound_files": [
            {
                "path": (
                    "experiments/consciousness_sae_target_blind_calibration/"
                    "audit_recovery.py"
                ),
                "bytes": 1,
                "sha256": source_hash,
            }
        ],
    }
    confinement = {"receipt_sha256": "d" * 64, "pid": 123}
    marker = audit_recovery._claim_attempt(args, authorization, confinement)
    audit_recovery._write_failure_receipt(
        args,
        authorization,
        marker,
        confinement,
        RuntimeError("expected failure"),
    )
    failure = json.loads(args.failure_out.read_text())
    assert failure["status"] == "failed_no_compact_success_publication"
    assert audit_recovery._self_hash(failure, "failure") == failure["receipt_sha256"]
    with pytest.raises(audit_recovery.AuditRecoveryError, match="not fresh"):
        audit_recovery._claim_attempt(args, authorization, confinement)


def test_execute_rehashes_raw_and_provenance_before_publication(
    tmp_path: Path, monkeypatch
) -> None:
    events: list[str] = []
    confined_child = ["python", "-m", "audit", "execute-confined"]
    raw = tmp_path / "raw"
    provenance = tmp_path / "provenance"
    raw.mkdir()
    provenance.mkdir()
    run_complete = tmp_path / "RUN_COMPLETE.json"
    run_complete.write_text(
        json.dumps({"resource": {"run_completed_at_unix": 1.0}}), encoding="utf-8"
    )
    args = argparse.Namespace(
        recovery_authorization=tmp_path / "authorization.json",
        landlock_receipt=tmp_path / "output/LANDLOCK_ENFORCEMENT.json",
        output_root=tmp_path / "output",
        active_root=Path.cwd().resolve(),
        python_executable=Path(audit_recovery.sys.executable).resolve(),
        roots_manifest=tmp_path / "bootstrap/APPROVED_IMPORT_ROOTS.json",
        roots_manifest_sha256="6" * 64,
        canary_protected_root=tmp_path / "landlock_canary/protected",
        canary_output_root=tmp_path / "landlock_canary/output",
        device_file=[Path("/dev/nvidia0")],
        raw_root=raw,
        provenance_root=provenance,
        raw_ledger=tmp_path / "ledger.txt",
        run_complete=run_complete,
        plan_dir=provenance / protocol.CANONICAL_PLAN_RELATIVE_PATH,
        model_snapshot=Path(audit_recovery.MODEL_SNAPSHOT_PATH),
        j_lens_path=Path(audit_recovery.J_LENS_PATH),
        original_ownership=tmp_path / "old-ownership.json",
        original_guest=tmp_path / "old-guest.json",
        original_cache=tmp_path / "old-cache.json",
        original_authorization=tmp_path / "old-authorization.json",
        artifact_device="cuda:0",
        audit_out=tmp_path / "compact/CALIBRATION_AUDIT.json",
        summary_out=tmp_path / "compact/CALIBRATION_SUMMARY.json",
    )
    authorization = {
        "receipt_sha256": "a" * 64,
        "historical_provenance_files": [],
        "execution": {
            "attempt_id": "attempt",
            "confined_child_argv": confined_child,
            "confined_child_argv_sha256": protocol.canonical_sha256(confined_child),
            "python_executable": Path(audit_recovery.sys.executable)
            .resolve()
            .as_posix(),
            "active_root": Path.cwd().resolve().as_posix(),
        },
        "preflight": {
            "probe_receipt": {"receipt_sha256": "9" * 64},
            "landlock_receipt": {"receipt_sha256": "8" * 64},
            "device_rules": [{"path": "/dev/nvidia0"}],
        },
    }
    monkeypatch.setattr(audit_recovery, "_json", lambda _path: authorization)
    monkeypatch.setattr(
        audit_recovery,
        "_bootstrap_manifest_binding",
        lambda *_args, **_kwargs: {
            "path": args.roots_manifest.as_posix(),
            "manifest": {"roots": []},
        },
    )
    monkeypatch.setattr(
        audit_recovery,
        "_bootstrap_protected_paths",
        lambda *_args: ([], []),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_current_bootstrap_attestation",
        lambda **_kwargs: {"receipt_sha256": "6" * 64},
    )
    monkeypatch.setattr(
        audit_recovery,
        "validate_recovery_authorization",
        lambda *_args, **_kwargs: authorization,
    )
    monkeypatch.setattr(
        audit_recovery,
        "_validate_landlock_receipt",
        lambda *_args, **_kwargs: {
            "receipt_sha256": "7" * 64,
            "pid": 123,
            "device_rules": [{"path": "/dev/nvidia0"}],
            "child_argv": confined_child,
            "child_argv_sha256": protocol.canonical_sha256(confined_child),
        },
    )
    monkeypatch.setattr(
        audit_recovery,
        "_validate_confinement_environment",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        audit_recovery,
        "_claim_attempt",
        lambda *_args: {"receipt_sha256": "b" * 64},
    )
    monkeypatch.setattr(
        audit_recovery,
        "_validate_executable_isolation",
        lambda *_args: {"receipt_sha256": "e" * 64},
    )

    def provenance_rehash(*_args) -> dict:
        events.append("provenance_rehash")
        return {"receipt_sha256": "f" * 64, "file_inventory_sha256": "1" * 64}

    def raw_rehash(*_args) -> dict:
        events.append("raw_rehash")
        return {"receipt_sha256": "0" * 64, "file_inventory_sha256": "2" * 64}

    monkeypatch.setattr(audit_recovery, "_validate_provenance_tree", provenance_rehash)
    monkeypatch.setattr(audit_recovery, "_rehash_raw_tree", raw_rehash)
    monkeypatch.setattr(
        audit_recovery,
        "_historical_provenance_context",
        lambda *_args: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_patched_audit_runtime",
        lambda *_args: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_forbidden_module_guard",
        lambda: contextlib.nullcontext({"forbidden_module_import_attempts": 0}),
    )
    monkeypatch.setattr(
        audit_recovery,
        "_zero_forward_guards",
        lambda: contextlib.nullcontext(
            {"torch_module_calls": 0, "transformers_model_load_calls": 0}
        ),
    )

    def metrics(*_args, **_kwargs) -> tuple[dict, dict]:
        events.append("metrics")
        return {}, {}

    monkeypatch.setattr(audit_recovery.audit, "audit", metrics)

    def metadata(**_kwargs) -> dict:
        events.append("metadata")
        return {"receipt_sha256": "3" * 64}

    monkeypatch.setattr(audit_recovery, "_recovery_metadata", metadata)
    monkeypatch.setattr(
        audit_recovery,
        "_enrich_outputs",
        lambda *_args, **_kwargs: ({}, {}),
    )

    def publish(*_args) -> Path:
        events.append("publish")
        return Path(_args[0]).parent

    monkeypatch.setattr(audit_recovery, "_publish_recovery_pair_atomic", publish)
    monkeypatch.setattr(
        audit_recovery.sys,
        "argv",
        ["audit_recovery.py", "execute-confined"],
    )
    result = audit_recovery.execute_recovery(args)
    assert result == args.audit_out.parent
    assert events == [
        "provenance_rehash",
        "raw_rehash",
        "metrics",
        "raw_rehash",
        "provenance_rehash",
        "metadata",
        "publish",
    ]


def test_real_recovery_metadata_constructor_discloses_bound_hashes(
    monkeypatch,
) -> None:
    bound_paths = {
        "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md",
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py",
        "experiments/consciousness_sae_target_blind_calibration/confined_bootstrap.py",
        "experiments/consciousness_sae_target_blind_calibration/"
        "scientific_equivalence.py",
        "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py",
        "experiments/consciousness_sae_target_blind_calibration/"
        "recovery_bundle_verifier.py",
        "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py",
        "tests/consciousness_sae_target_blind_calibration/test_confined_bootstrap.py",
        "tests/consciousness_sae_target_blind_calibration/"
        "test_scientific_equivalence.py",
        "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py",
        "tests/consciousness_sae_target_blind_calibration/"
        "test_recovery_bundle_verifier.py",
        audit_recovery.HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN,
        audit_recovery.HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
        f"{audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/response.json",
        f"{audit_recovery.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON,
        audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN,
        f"{audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/response.json",
        f"{audit_recovery.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json",
        audit_recovery.FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON,
        audit_recovery.FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN,
        f"{audit_recovery.FINAL_V5_PRO_REVIEW_DIRECTORY}/response.json",
        f"{audit_recovery.FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json",
        audit_recovery.V5_LOCAL_TEST_RECEIPT_SNAPSHOT,
        audit_recovery.V5_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        audit_recovery.V5_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json",
        "docs/consciousness_sae_target_blind_calibration/"
        "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md",
    }
    rows = [
        {"path": path, "bytes": 1, "sha256": f"{index + 1:064x}"}
        for index, path in enumerate(sorted(bound_paths))
    ]
    authorization = {
        "receipt_sha256": "a" * 64,
        "review": {
            "provider_status": "completed",
            "provider_approval_claimed": False,
            "provider_ready_to_freeze_verdict": True,
            "source_and_tests_reviewed_by_provider": True,
            "reviewed_packet_was_pre_fix": False,
            "final_source_reviewed_by_provider": True,
            "provider_reviewed_final_bytes_unchanged": True,
        },
        "execution": {"attempt_id": "attempt", "command_sha256": "b" * 64},
        "recovery_bound_paths_sha256": "c" * 64,
        "plan_manifest_sha256": "d" * 64,
        "recovery_bound_files": rows,
        "original_receipts": {"ownership": "e" * 64},
        "superseded_recovery_host": {"status": "validated_superseded"},
        "fresh_receipts": {"ownership": "f" * 64},
        "fresh_pod_id": "pod123456",
        "bootstrap_import_roots": {"status": "bound"},
        "test_receipts": {
            "local": {
                "receipt_sha256": "1" * 64,
                "code_freeze_commit": "2" * 40,
                "source_test_inventory_sha256": "3" * 64,
            },
            "target_host": {
                "receipt_sha256": "4" * 64,
                "code_freeze_commit": "2" * 40,
                "source_test_inventory_sha256": "3" * 64,
            },
        },
    }
    monkeypatch.setattr(
        audit_recovery,
        "_OBSERVED_J_INVENTORY",
        {
            "available_layers": list(range(79)),
            "required_layers": list(range(45, 79)),
            "unused_extra_layers": list(range(45)),
        },
    )

    def sealed(status: str, **extra) -> dict:
        core = {"status": status, **extra}
        return {**core, "receipt_sha256": protocol.canonical_sha256(core)}

    preflight_landlock = sealed("preflight_landlock")
    preflight_probe = sealed("preflight_probe")
    confinement = sealed("confinement")
    isolation = sealed("isolation")
    provenance_pre = sealed(
        "provenance_pre",
        file_inventory_sha256="5" * 64,
        directory_inventory_sha256="6" * 64,
    )
    provenance_post = sealed(
        "provenance_post",
        file_inventory_sha256="5" * 64,
        directory_inventory_sha256="6" * 64,
    )
    raw_pre = sealed(
        "raw_pre",
        file_inventory_sha256="8" * 64,
        directory_inventory_sha256="9" * 64,
    )
    raw_post = sealed(
        "raw_post",
        file_inventory_sha256="8" * 64,
        directory_inventory_sha256="9" * 64,
    )
    bootstrap_attestation = {"receipt_sha256": "7" * 64}
    bootstrap_entry = audit_recovery._bootstrap_phase_record(
        audit_recovery.BOOTSTRAP_EXECUTE_ENTRY_PHASE,
        bootstrap_attestation,
    )
    bootstrap_prepublication = audit_recovery._bootstrap_phase_record(
        audit_recovery.BOOTSTRAP_PREPUBLICATION_PHASE,
        bootstrap_attestation,
    )
    receipt = audit_recovery._recovery_metadata(
        authorization=authorization,
        confinement=confinement,
        preflight_landlock=preflight_landlock,
        preflight_probe=preflight_probe,
        executable_isolation=isolation,
        provenance_pre_rehash=provenance_pre,
        provenance_post_rehash=provenance_post,
        pre_rehash=raw_pre,
        post_rehash=raw_post,
        guards={"torch_module_calls": 0, "transformers_model_load_calls": 0},
        module_guards={"forbidden_module_import_attempts": 0},
        bootstrap_entry_phase=bootstrap_entry,
        bootstrap_prepublication_phase=bootstrap_prepublication,
        marker={"receipt_sha256": "0" * 64},
    )
    assert receipt["historical_provenance_unchanged"] is True
    assert receipt["raw_unchanged"] is True
    assert receipt["historical_review_adjudication_json_sha256"] in {
        row["sha256"] for row in rows
    }
    assert receipt["historical_v3_review_adjudication_json_sha256"] in {
        row["sha256"] for row in rows
    }
    assert receipt["historical_v4_review_adjudication_json_sha256"] in {
        row["sha256"] for row in rows
    }
    assert receipt["final_v5_review_adjudication_json_sha256"] in {
        row["sha256"] for row in rows
    }
    assert receipt["historical_v2_review_adjudication_json_sha256"] in {
        row["sha256"] for row in rows
    }
    assert receipt["provider_review_source_and_tests_seen"] is True
    assert receipt["provider_reviewed_packet_was_pre_fix"] is False
    assert receipt["provider_reviewed_final_source"] is True
    assert receipt["bootstrap_import_roots"] == {"status": "bound"}
    assert receipt["bootstrap_execute_entry_phase"] == bootstrap_entry
    assert receipt["bootstrap_prepublication_phase"] == bootstrap_prepublication
    nested = {
        "preflight_landlock_receipt": preflight_landlock,
        "preflight_probe_receipt": preflight_probe,
        "landlock_confinement_receipt": confinement,
        "executable_isolation_receipt": isolation,
        "provenance_pre_rehash_receipt": provenance_pre,
        "provenance_post_rehash_receipt": provenance_post,
        "pre_rehash_receipt": raw_pre,
        "post_rehash_receipt": raw_post,
    }
    for name, expected in nested.items():
        assert receipt[name] == expected
        assert (
            audit_recovery._self_hash(receipt[name], name)
            == receipt[f"{name.removesuffix('_receipt')}_receipt_sha256"]
        )
    assert audit_recovery._self_hash(receipt, "recovery") == receipt["receipt_sha256"]


def test_enrichment_preserves_original_clock_and_records_recovery_campaign() -> None:
    audit_core = {
        "status": "pass",
        "campaign_started_at_unix": audit_recovery.ORIGINAL_CAMPAIGN_STARTED_AT_UNIX,
        "campaign_deadline_at_unix": (
            audit_recovery.ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX
        ),
        "hourly_price_usd": audit_recovery.ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD,
    }
    audit_receipt = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = {
        "status": "pass",
        "audit_receipt_sha256": audit_receipt["receipt_sha256"],
    }
    summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }
    authorization = {
        "recovery_started_at_unix": 100.0,
        "recovery_deadline_at_unix": 1900.0,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 3.0,
    }
    recovery = {
        "status": "pass_disclosed_post_run_technical_recovery",
        "receipt_sha256": "a" * 64,
        "correction": "required_j_layers_subset_of_hash_pinned_release_inventory",
        "provider_review_status": "incomplete",
    }
    enriched_audit, enriched_summary = audit_recovery._enrich_outputs(
        audit_receipt,
        summary,
        authorization=authorization,
        recovery=recovery,
    )
    assert enriched_audit["original_execution_campaign"] == {
        "campaign_started_at_unix": audit_recovery.ORIGINAL_CAMPAIGN_STARTED_AT_UNIX,
        "campaign_deadline_at_unix": (
            audit_recovery.ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX
        ),
        "hourly_price_usd": audit_recovery.ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD,
    }
    assert (
        enriched_audit["campaign_started_at_unix"]
        == audit_recovery.ORIGINAL_CAMPAIGN_STARTED_AT_UNIX
    )
    assert (
        enriched_audit["campaign_deadline_at_unix"]
        == audit_recovery.ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX
    )
    assert (
        enriched_audit["hourly_price_usd"]
        == audit_recovery.ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD
    )
    recovery_campaign = {
        "started_at_unix": 100.0,
        "deadline_at_unix": 1900.0,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 3.0,
    }
    assert enriched_audit["recovery_execution_campaign"] == recovery_campaign
    assert enriched_summary["recovery_execution_campaign"] == recovery_campaign
    assert enriched_summary["audit_receipt_sha256"] == enriched_audit["receipt_sha256"]
    for value in (enriched_audit, enriched_summary):
        core = dict(value)
        supplied = core.pop("receipt_sha256")
        assert supplied == protocol.canonical_sha256(core)

    tampered = {
        **audit_receipt,
        "campaign_started_at_unix": 777.0,
        "campaign_deadline_at_unix": 888.0,
        "hourly_price_usd": 9.0,
    }
    with pytest.raises(audit_recovery.AuditRecoveryError, match="campaign fields"):
        audit_recovery._enrich_outputs(
            tampered,
            summary,
            authorization=authorization,
            recovery=recovery,
        )


def test_recovery_publication_uses_distinct_fresh_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "output"
    parent.mkdir()
    compact = parent / "compact"
    audit_out = compact / "CALIBRATION_AUDIT.json"
    summary_out = compact / "CALIBRATION_SUMMARY.json"
    recovery_campaign = {
        "started_at_unix": 100.0,
        "deadline_at_unix": 1900.0,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 3.0,
    }
    audit_core = {
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "audit_started_at_unix": 110.0,
        "campaign_deadline_at_unix": 20.0,
        "recovery_execution_campaign": recovery_campaign,
    }
    audit_receipt = {
        **audit_core,
        "receipt_sha256": protocol.canonical_sha256(audit_core),
    }
    summary_core = {"recovery_execution_campaign": recovery_campaign}
    summary = {
        **summary_core,
        "receipt_sha256": protocol.canonical_sha256(summary_core),
    }

    class Watchdog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def check(self) -> None:
            pass

    monkeypatch.setattr(audit_recovery.audit, "_AuditBudgetWatchdog", Watchdog)
    monkeypatch.setattr(audit_recovery.time, "time", lambda: 120.0)
    published = audit_recovery._publish_recovery_pair_atomic(
        audit_out, summary_out, audit_receipt, summary
    )
    assert published == summary_out
    observed_audit = json.loads(audit_out.read_text())
    publication = json.loads((compact / "PUBLICATION_COMPLETE.json").read_text())
    assert observed_audit["campaign_deadline_at_unix"] == 20.0
    assert publication["recovery_deadline_at_unix"] == 1900.0
    assert "campaign_deadline_at_unix" not in publication
    assert (
        audit_recovery._self_hash(publication, "publication")
        == publication["receipt_sha256"]
    )


def test_original_r3_auditor_source_is_still_physically_frozen() -> None:
    assert (
        protocol.sha256_file(
            audit_recovery.REPO_ROOT
            / "experiments/consciousness_sae_target_blind_calibration/audit.py"
        )
        == "271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465"
    )
