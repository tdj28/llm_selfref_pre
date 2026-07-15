from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest

from experiments.consciousness_sae_target_blind_calibration import (
    audit_recovery,
    recovery_bundle_verifier as verifier,
)


def _seal(core: dict) -> dict:
    return {**core, "receipt_sha256": verifier.canonical_sha256(core)}


def test_superseded_c6_qualification_evidence_is_separate_and_pinned() -> None:
    assert verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256 == (
        audit_recovery.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256
    )
    assert set(verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256) <= set(
        verifier.RECOVERY_DOCUMENT_PATHS
    )
    assert set(verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256) <= set(
        audit_recovery.RECOVERY_DOCUMENT_PATHS
    )
    packet_paths = [path for path, _role in audit_recovery.PRO_REVIEW_V6_PACKET]
    assert not set(verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256) & {
        verifier.V6_LOCAL_TEST_RECEIPT_SNAPSHOT,
        verifier.V6_TARGET_HOST_TEST_RECEIPT_SNAPSHOT,
        verifier.V6_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT,
        verifier.V6_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT,
        verifier.V6_TARGET_QUALIFICATION_CUDA_SNAPSHOT,
    }
    for (
        relative,
        expected,
    ) in verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256.items():
        path = audit_recovery.REPO_ROOT / relative
        assert verifier.sha256_file(path) == expected
        assert packet_paths.count(relative) == 1
        receipt = json.loads(path.read_text(encoding="utf-8"))
        supplied = receipt.pop("receipt_sha256")
        assert verifier.canonical_sha256(receipt) == supplied


def test_failed_c7_qualification_archive_is_separate_pinned_context() -> None:
    assert verifier.C7_FAILED_QUALIFICATION_PHYSICAL_SHA256 == (
        audit_recovery.C7_FAILED_QUALIFICATION_PHYSICAL_SHA256
    )
    packet_paths = [path for path, _role in audit_recovery.PRO_REVIEW_V6_PACKET]
    for relative, expected in verifier.C7_FAILED_QUALIFICATION_PHYSICAL_SHA256.items():
        path = audit_recovery.REPO_ROOT / relative
        assert verifier.sha256_file(path) == expected
        assert packet_paths.count(relative) == 1
        assert relative in verifier.RECOVERY_DOCUMENT_PATHS
        assert relative in audit_recovery.RECOVERY_DOCUMENT_PATHS
    root = (
        audit_recovery.REPO_ROOT / verifier.C7_FAILED_QUALIFICATION_DIRECTORY
    )
    status = json.loads((root / "QUALIFICATION_STATUS.json").read_text())
    assert status == {
        "archived_at_utc": "2026-07-15T13:57:27Z",
        "code_freeze_commit": "4a7abd249d5bbc16e859bafb700f648de5245a50",
        "exit_code": 2,
        "pod_id": "t915ydw4gqfb8a",
        "remote_qualification_root": "/root/q7-4a7abd2",
        "schema_version": 1,
        "status": "failed",
    }
    assert (root / "remote.stderr").read_text(encoding="utf-8").endswith(
        "landlock launcher failed: writable regular-file/directory descriptor "
        "was inherited\n"
    )
    ledger = (root / "SHA256SUMS").read_text(encoding="utf-8")
    assert (
        "49caca53952b9c00ab27536b78d2df928094dd986450074a4d66f77ae405315a  "
        "./controller/run_target_qualification.sh"
    ) in ledger


def test_independent_verifier_rejects_overlong_bound_canary_socket_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verifier,
        "RECOVERY_ATTEMPT_PARENT",
        "/workspace/" + "x" * 160,
    )
    with pytest.raises(
        verifier.RecoveryBundleVerificationError,
        match="Unix-socket canary path exceeds",
    ):
        verifier._expected_paths(  # noqa: SLF001
            "calv2-r3-audit-recovery-aaaaaaa-20260715T010203Z"
        )


def test_historical_v6_review_is_pinned_nonadjudicable_context_for_v7() -> None:
    assert verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256 == (
        audit_recovery.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256
    )
    assert set(verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256) <= set(
        verifier.RECOVERY_DOCUMENT_PATHS
    )
    v7_paths = {path for path, _role in audit_recovery.PRO_REVIEW_V7_PACKET}
    assert {
        f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md",
        f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json",
    } <= v7_paths
    assert verifier.FINAL_V6_PRO_REVIEW_ADJUDICATION_JSON not in v7_paths
    assert verifier.FINAL_V6_PRO_REVIEW_ADJUDICATION_MARKDOWN not in v7_paths
    assert verifier.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256 == (
        audit_recovery.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256
    )
    assert verifier.HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256 == (
        audit_recovery.HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256
    )
    assert verifier.B20_COMPACT_EVIDENCE_PHYSICAL_SHA256 == (
        audit_recovery.B20_COMPACT_EVIDENCE_PHYSICAL_SHA256
    )
    assert verifier.V8_LOCAL_TEST_RECEIPT_SNAPSHOT == (
        audit_recovery.V8_LOCAL_TEST_RECEIPT_SNAPSHOT
    )
    assert verifier.RECOVERY_BOUND_PATHS == audit_recovery.RECOVERY_BOUND_PATHS


def test_independent_verifier_rejects_socket_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verifier, "OUTPUT_CANARY_SOCKET_NAME", ".other")
    with pytest.raises(
        verifier.RecoveryBundleVerificationError,
        match="Unix-socket canary path exceeds",
    ):
        verifier._expected_paths(  # noqa: SLF001
            "calv2-r3-audit-recovery-aaaaaaa-20260715T010203Z"
        )


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(verifier.canonical_json_bytes(value) + b"\n")


def _file_record(path: Path) -> dict:
    return {"bytes": path.stat().st_size, "sha256": verifier.sha256_file(path)}


def _device(*, inode: int = 7) -> dict:
    rdev = 49920
    return {
        "path": "/dev/nvidia0",
        "st_dev": 23,
        "st_ino": inode,
        "st_rdev": rdev,
        "major": 195,
        "minor": 0,
        "allowed_access_fs": verifier.DEVICE_ALLOWED_ACCESS_FS,
    }


def _qualification_ownership() -> dict:
    nonce = "1" * 32
    upstream = "2" * 64
    return _seal(
        {
            "schema_version": 1,
            "status": "owned_running_isolated",
            "study_id": verifier.OWNERSHIP_STUDY_ID,
            "protocol_version": verifier.OWNERSHIP_PROTOCOL_VERSION,
            "pod_id": "qualpod",
            "pod_name": f"{verifier.OWNERSHIP_POD_NAME_PREFIX}19700101-{nonce}",
            "ownership_nonce": nonce,
            "network_volume_id": verifier.NETWORK_VOLUME_ID,
            "provider_volume_size_bytes": (
                verifier.OWNERSHIP_PROVIDER_VOLUME_SIZE_BYTES
            ),
            "data_center_id": verifier.DATA_CENTER_ID,
            "gpu_type": verifier.GPU_TYPE,
            "gpu_count": 1,
            "volume_mount_path": "/workspace",
            "created_at": "1970-01-01T00:10:00Z",
            "terminate_after": "1970-01-01T06:10:00Z",
            "create_contract_sha256": "3" * 64,
            "upstream_lifecycle_receipt_sha256": upstream,
            "provider_container_image_attestation": {
                "source": "validated_graphql_create_plus_final_rest_readback_v1",
                "immutable_reference": verifier.OWNERSHIP_IMAGE_IMMUTABLE_REFERENCE,
                "graphql_create_snapshot_source": (
                    "graphql_create_plus_rest_volume_proof"
                ),
                "create_request_sha256": "4" * 64,
                "final_rest_proof_source": (
                    "rest_v1_pod_get_final_after_graphql_locked_state"
                ),
                "rest_image_fields": ["image", "imageName"],
                "upstream_lifecycle_receipt_sha256": upstream,
            },
            "desired_status": "RUNNING",
            "locked": False,
            "precreate_unrelated_pod_count": 0,
            "precreate_unrelated_inventory_sha256": "5" * 64,
        }
    )


def _descriptor_audit(protected_roots: list[str]) -> dict:
    rows = [
        {
            "fd": 0,
            "target": "/dev/null",
            "kind": "character_device",
            "access_mode": os.O_RDONLY,
            "writable": False,
            "allowed_reason": "standard_stream",
        },
        {
            "fd": 1,
            "target": "pipe:[100]",
            "kind": "fifo",
            "access_mode": os.O_WRONLY,
            "writable": True,
            "allowed_reason": "standard_stream",
        },
        {
            "fd": 2,
            "target": "pipe:[101]",
            "kind": "fifo",
            "access_mode": os.O_WRONLY,
            "writable": True,
            "allowed_reason": "standard_stream",
        },
    ]
    return {
        "status": "pass_no_escaping_writable_or_protected_descriptors",
        "protected_roots": sorted(set(protected_roots)),
        "descriptor_count": len(rows),
        "descriptors": rows,
    }


def _canary() -> dict:
    inventory = "c" * 64
    return {
        "status": "pass_protected_unchanged_output_empty",
        "protected_inventory_sha256_before": inventory,
        "protected_inventory_sha256_after": inventory,
        "protected_unchanged": True,
        "output_empty_before": True,
        "output_empty_after": True,
        "preconfinement_writable_baseline": [
            {"operation": name, "status": "allowed"}
            for name in verifier.PRECONFINEMENT_WRITABLE_BASELINE
        ],
        "protected_operations": [
            {"operation": name, "status": "denied", "errno": 13}
            for name in verifier.PROTECTED_OPERATIONS
        ],
        "output_operations": [
            *(
                {"operation": name, "status": "allowed"}
                for name in verifier.OUTPUT_ALLOWED_OPERATIONS
            ),
            *(
                {
                    "operation": name,
                    "status": "denied",
                    "errno": (
                        errno.EXDEV
                        if name == "output_cross_directory_link"
                        else errno.EACCES
                    ),
                }
                for name in verifier.OUTPUT_DENIED_OPERATIONS
            ),
        ],
    }


def _landlock(
    *,
    purpose: str,
    pid: int,
    receipt_path: str,
    output_root: str,
    protected_roots: list[str],
    protected_files: list[str],
    canary_output_root: str,
    child_argv: list[str],
    devices: list[dict],
    authorization_sha256: str | None = None,
    preflight_sha256: str | None = None,
    handled_access_fs: int = verifier.HANDLED_ACCESS_FS,
) -> dict:
    core = {
        "schema_version": 1,
        "status": "pass_landlock_enforced",
        "purpose": purpose,
        "pid": pid,
        "observed_abi": 4,
        "required_abi": 4,
        "handled_access_fs": handled_access_fs,
        "output_allowed_access_fs": verifier.OUTPUT_ALLOWED_ACCESS_FS,
        "no_new_privs": True,
        "thread_ids": [pid],
        "descriptor_audit": _descriptor_audit(protected_roots),
        "mapping_audit": {
            "status": "pass_no_shared_file_backed_mappings",
            "mapping_count": 20,
            "shared_file_backed": [],
        },
        "directory_rules": [
            {
                "role": "output_root",
                "path": output_root,
                "allowed_access_fs": verifier.OUTPUT_ALLOWED_ACCESS_FS,
            },
            {
                "role": "canary_output_root",
                "path": canary_output_root,
                "allowed_access_fs": verifier.OUTPUT_ALLOWED_ACCESS_FS,
            },
            {
                "role": "proc_self_task_thread_names",
                "path": verifier.PROC_SELF_TASK_PATH,
                "allowed_access_fs": verifier.PROC_SELF_TASK_ALLOWED_ACCESS_FS,
            },
        ],
        "device_rules": devices,
        "protected_checks": [
            {
                "path": path,
                "operation": "protected_file_open_write_no_write",
                "status": "denied",
                "errno": 13,
            }
            for path in sorted(protected_files)
        ],
        "canary_checks": _canary(),
        "child_argv": child_argv,
        "child_argv_sha256": verifier.canonical_sha256(child_argv),
        "source_sha256": "9" * 64,
        "receipt_path": receipt_path,
    }
    if authorization_sha256 is not None:
        core["authorization_sha256"] = authorization_sha256
    if preflight_sha256 is not None:
        core["preflight_receipt_sha256"] = preflight_sha256
    return _seal(core)


def _raw_rehash(
    inventory: str,
    *,
    directory_count: int = 8,
    directory_inventory: str = "4" * 64,
) -> dict:
    return _seal(
        {
            "status": "pass_exact_36_file_rehash",
            "raw_root": f"/workspace/{verifier.RAW_RELATIVE}",
            "file_count": 36,
            "total_bytes": 323375434,
            "file_inventory_sha256": inventory,
            "directory_count": directory_count,
            "directory_inventory_sha256": directory_inventory,
            "run_receipt_sha256": verifier.ORIGINAL_RUN_RECEIPT_SHA256,
            "external_ledger_file_sha256": verifier.ORIGINAL_RAW_LEDGER_SHA256,
        }
    )


def _provenance_rehash(
    inventory: str,
    attempt_root: str,
    *,
    file_count: int,
    directory_count: int = 3,
    directory_inventory: str = "5" * 64,
) -> dict:
    return _seal(
        {
            "status": "pass_exact_nonimportable_historical_provenance",
            "root": f"{attempt_root}/provenance_repo",
            "file_count": file_count,
            "file_inventory_sha256": inventory,
            "directory_count": directory_count,
            "directory_inventory_sha256": directory_inventory,
        }
    )


def _snapshot(root: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def _bootstrap_root(
    *,
    name: str,
    role: str,
    path: str,
    files: list[dict],
    directories: list[str],
) -> dict:
    core = {
        "name": name,
        "role": role,
        "path": path,
        "files": files,
        "directories": directories,
        "file_count": len(files),
        "directory_count": len(directories),
        "total_bytes": sum(int(row["bytes"]) for row in files),
        "file_inventory_sha256": verifier.canonical_sha256(files),
        "directory_inventory_sha256": verifier.canonical_sha256(directories),
    }
    return {**core, "inventory_sha256": verifier.canonical_sha256(core)}


def _bootstrap_manifest(
    *,
    active_root: str,
    python_executable: str,
    closure: list[dict],
    bootstrap_sha256: str,
) -> dict:
    active = _bootstrap_root(
        name="active_root",
        role="active",
        path=active_root,
        files=closure,
        directories=verifier._expected_directory_inventory(  # noqa: SLF001
            verifier.RECOVERY_BOUND_PATHS
        ),
    )
    dependency_files = [{"path": "torch/__init__.py", "bytes": 7, "sha256": "d" * 64}]
    dependency = _bootstrap_root(
        name="runtime_dependencies",
        role="dependency",
        path=f"{active_root}/.venv/lib/python3.11/site-packages",
        files=dependency_files,
        directories=["torch"],
    )
    roots = [active, dependency]
    return _seal(
        {
            "schema_version": 1,
            "status": verifier.BOOTSTRAP_MANIFEST_STATUS,
            "python_executable": {
                "path": python_executable,
                "bytes": 1000,
                "sha256": "e" * 64,
            },
            "bootstrap_relative_path": verifier.BOOTSTRAP_RELATIVE_PATH,
            "bootstrap_sha256": bootstrap_sha256,
            "active_root": active_root,
            "roots": roots,
            "sys_path": [active_root, dependency["path"]],
            "roots_inventory_sha256": verifier.canonical_sha256(roots),
        }
    )


def _bootstrap_attestation(
    *,
    mode: str,
    pid: int,
    active_root: str,
    python_executable: str,
    roots_manifest_path: str,
    roots_manifest_sha256: str,
    manifest: dict,
) -> dict:
    return _seal(
        {
            "schema_version": 1,
            "status": "pass_hash_bound_confined_bootstrap",
            "mode": mode,
            "pid": pid,
            "active_root": active_root,
            "python_executable": python_executable,
            "roots_manifest_path": roots_manifest_path,
            "roots_manifest_file_sha256": roots_manifest_sha256,
            "roots_manifest_receipt_sha256": manifest["receipt_sha256"],
            "roots_inventory_sha256": manifest["roots_inventory_sha256"],
            "sys_path": manifest["sys_path"],
            "bootstrap_sha256": manifest["bootstrap_sha256"],
            "site_imported": False,
            "startup_project_or_ml_module_count": 0,
            "guards": {
                "status": "process_lifetime_guards_installed",
                "forbidden_module_import_attempts": 0,
                "forbidden_startup_import_attempts": 0,
                "torch_module_calls": 0,
                "transformers_model_load_calls": 0,
                "patched_modules": list(verifier.BOOTSTRAP_GUARDED_MODULES),
            },
        }
    )


def _bootstrap_phase(phase: str, attestation: dict) -> dict:
    return _seal(
        {
            "status": "pass_hash_bound_bootstrap_phase",
            "phase": phase,
            "attestation": attestation,
            "attestation_receipt_sha256": attestation["receipt_sha256"],
        }
    )


def _test_receipt_evidence(
    root: Path,
    recovery_bound_files: list[dict],
    *,
    mutation: str | None,
    code_freeze: str,
) -> tuple[dict, dict, Path, Path, Path, Path, Path]:
    source_test_files = [
        row
        for row in recovery_bound_files
        if row["path"] in set(verifier.SOURCE_TEST_BOUND_PATHS)
    ]
    designated = verifier.TARGET_DESIGNATED_TEST_IDS[0]
    dependencies = [
        {"name": name, "version": version}
        for name, version in sorted(verifier.EXPECTED_PACKAGES.items())
    ]
    qualification_ownership = _qualification_ownership()
    if mutation == "qualification_ownership_clock":
        ownership_core = dict(qualification_ownership)
        ownership_core.pop("receipt_sha256")
        ownership_core["terminate_after"] = "1970-01-01T06:10:01Z"
        qualification_ownership = _seal(ownership_core)
    qualification_ownership_path = (
        root / verifier.TARGET_QUALIFICATION_OWNERSHIP_RELATIVE
    )
    _write(qualification_ownership_path, qualification_ownership)
    qualification_output_root = Path("/root/qualification/probe/output")
    embedded_ownership_path = (
        Path("/root/qualification/evidence")
        / verifier.TARGET_QUALIFICATION_OWNERSHIP_NAME
    )
    embedded_landlock_path = (
        qualification_output_root / verifier.TARGET_QUALIFICATION_LANDLOCK_NAME
    )
    embedded_cuda_path = (
        qualification_output_root / verifier.TARGET_QUALIFICATION_CUDA_NAME
    )
    if mutation == "qualification_origin_ownership_inside_output":
        embedded_ownership_path = (
            qualification_output_root / verifier.TARGET_QUALIFICATION_OWNERSHIP_NAME
        )
    elif mutation == "qualification_origin_landlock_outside_output":
        embedded_landlock_path = (
            Path("/root/qualification/elsewhere")
            / verifier.TARGET_QUALIFICATION_LANDLOCK_NAME
        )
    target_test_root = Path("/root/qualification/test")
    active_root = "/root/qualification/active"
    python_executable = f"{active_root}/.venv/bin/python"
    roots_manifest_path = "/root/qualification/bootstrap/APPROVED_IMPORT_ROOTS.json"
    roots_manifest_sha256 = "6" * 64
    root_paths = [active_root, "/root/qualification/dependencies"]
    sys_path = list(root_paths)
    bootstrap_sha256 = next(
        row["sha256"]
        for row in source_test_files
        if row["path"] == verifier.BOOTSTRAP_RELATIVE_PATH
    )
    bootstrap_commitment = {
        "path": roots_manifest_path,
        "file_sha256": roots_manifest_sha256,
        "receipt_sha256": "7" * 64,
        "roots_inventory_sha256": "8" * 64,
        "bootstrap_sha256": bootstrap_sha256,
        "active_root": active_root,
        "python_executable": python_executable,
        "root_paths": root_paths,
        "sys_path": sys_path,
    }
    qualification_landlock_path = root / verifier.TARGET_QUALIFICATION_LANDLOCK_RELATIVE
    qualification_cuda_path = root / verifier.TARGET_QUALIFICATION_CUDA_RELATIVE
    canary_protected_root = "/root/qualification/canary/protected"
    canary_output_root = "/root/qualification/canary/output"
    devices = [_device(inode=17)]
    qualification_child = verifier._expected_preflight_argv(  # noqa: SLF001
        python_executable,
        active_root,
        {"roots_manifest": roots_manifest_path},
        roots_manifest_sha256,
        [row["path"] for row in devices],
        closure_scope="source_test_qualification",
        qualification_ownership=embedded_ownership_path.as_posix(),
        landlock_receipt=embedded_landlock_path.as_posix(),
        output_root=qualification_output_root.as_posix(),
        canary_protected_root=canary_protected_root,
        canary_output_root=canary_output_root,
        output=embedded_cuda_path.as_posix(),
    )
    if mutation == "qualification_child_argv":
        qualification_child[-1] = "/wrong/qualification.json"
    qualification_landlock = _landlock(
        purpose="preauthorization_probe",
        pid=91,
        receipt_path=embedded_landlock_path.as_posix(),
        output_root=qualification_output_root.as_posix(),
        protected_roots=[
            canary_protected_root,
            *sorted({*root_paths, str(Path(roots_manifest_path).parent)}),
        ],
        protected_files=[
            f"{canary_protected_root}/seed.txt",
            roots_manifest_path,
            f"{active_root}/{verifier.BOOTSTRAP_RELATIVE_PATH}",
            embedded_ownership_path.as_posix(),
        ],
        canary_output_root=canary_output_root,
        child_argv=qualification_child,
        devices=(
            [{**_device(inode=18), "path": "/dev/nvidiactl"}]
            if mutation == "qualification_device"
            else devices
        ),
    )
    qualification_landlock_path = root / verifier.TARGET_QUALIFICATION_LANDLOCK_RELATIVE
    _write(qualification_landlock_path, qualification_landlock)
    qualification_attestation = _bootstrap_attestation(
        mode="preflight-child",
        pid=91,
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=roots_manifest_path,
        roots_manifest_sha256=roots_manifest_sha256,
        manifest={
            "receipt_sha256": bootstrap_commitment["receipt_sha256"],
            "roots_inventory_sha256": bootstrap_commitment["roots_inventory_sha256"],
            "sys_path": sys_path,
            "bootstrap_sha256": bootstrap_sha256,
        },
    )
    if mutation == "qualification_bootstrap":
        qualification_attestation = {
            **qualification_attestation,
            "active_root": "/root/wrong",
        }
        core = dict(qualification_attestation)
        core.pop("receipt_sha256")
        qualification_attestation = _seal(core)
    qualification_environment = dict(verifier.FIXED_ENVIRONMENT)
    qualification_environment.update(
        {
            name: f"{qualification_output_root.as_posix()}/writable/{name.lower()}"
            for name in verifier.DYNAMIC_ENVIRONMENT
        }
    )
    qualification_closure = [dict(row) for row in source_test_files]
    if mutation == "qualification_closure":
        qualification_closure[0]["bytes"] += 1
    qualification_cuda = _seal(
        {
            "schema_version": 1,
            "status": "pass_target_free_landlock_cuda_preflight",
            "pid": 91,
            "python_executable": python_executable,
            "active_root": active_root,
            "closure_scope": "source_test_qualification",
            "closure_files": qualification_closure,
            "closure_file_count": len(qualification_closure),
            "closure_inventory_sha256": verifier.canonical_sha256(
                qualification_closure
            ),
            "landlock_receipt_sha256": qualification_landlock["receipt_sha256"],
            "recovery_closure_sha256": verifier.canonical_sha256(qualification_closure),
            "bootstrap_roots_manifest": bootstrap_commitment,
            "qualification_ownership_receipt_sha256": qualification_ownership[
                "receipt_sha256"
            ],
            "package_versions": dict(verifier.EXPECTED_PACKAGES),
            "imported_package_versions": dict(verifier.EXPECTED_IMPORTED_PACKAGES),
            "environment": qualification_environment,
            "absent_environment_variables": list(verifier.FORBIDDEN_ENVIRONMENT),
            "provider": {
                "pod_id": qualification_ownership["pod_id"],
                "volume_id": verifier.NETWORK_VOLUME_ID,
                "data_center_id": verifier.DATA_CENTER_ID,
            },
            "cuda": {
                "available": True,
                "device": "cuda:0",
                "device_count": 1,
                "device_name": "NVIDIA B200",
                "device_capability": [10, 0],
                "dtype": "torch.bfloat16",
                "shape": [16, 16],
                "matmul_finite": True,
                "synchronized": True,
                "raw_tensor_operations_only": True,
            },
            "model_forward_count": 0,
            "torch_module_call_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "external_or_prior_outcome_inputs": [],
            "bootstrap": _bootstrap_phase(
                verifier.BOOTSTRAP_PREFLIGHT_PHASE,
                qualification_attestation,
            ),
            "completed_at_utc": "1970-01-01T00:11:00Z",
        }
    )
    qualification_cuda_path = root / verifier.TARGET_QUALIFICATION_CUDA_RELATIVE
    _write(qualification_cuda_path, qualification_cuda)

    def receipt(kind: str) -> dict:
        target = kind == "target_host"
        receipt_source_test_files = [dict(row) for row in source_test_files]
        if mutation == "target_source_inventory" and target:
            receipt_source_test_files[0]["bytes"] += 1
        receipt_path = (
            target_test_root / verifier.TARGET_HOST_TEST_RELATIVE.name
            if target
            else root / verifier.LOCAL_TEST_RELATIVE
        )
        passed_ids = [designated] if target else []
        skipped_ids = [] if target else [designated]
        if mutation == "target_designated_skip" and target:
            passed_ids = []
            skipped_ids = [designated]
        target_host = None
        probe_summary = None
        command_tail = [
            "test-receipt",
            "--kind",
            kind,
            "--code-freeze-commit",
            code_freeze,
        ]
        if target:
            target_host = {
                "pod_id": (
                    "test-pod"
                    if mutation == "target_same_recovery_pod"
                    else qualification_ownership["pod_id"]
                ),
                "volume_id": verifier.NETWORK_VOLUME_ID,
                "data_center_id": verifier.DATA_CENTER_ID,
                "kernel_release": "6.8.0",
                "landlock_abi": 6,
                "gpu": {
                    "device_count": 1,
                    "device_name": "NVIDIA B200",
                    "device_capability": [10, 0],
                    "total_memory_bytes": 180 * 1024**3,
                },
                "created_at_utc": qualification_ownership["created_at"],
                "test_started_host_age_seconds": 120.0,
                "test_completed_host_age_seconds": 180.0,
            }
            probe_summary = {
                "ownership_file": _file_record(qualification_ownership_path),
                "ownership_receipt_sha256": qualification_ownership["receipt_sha256"],
                "ownership_created_at_utc": qualification_ownership["created_at"],
                "landlock_file": _file_record(qualification_landlock_path),
                "landlock_receipt_sha256": qualification_landlock["receipt_sha256"],
                "landlock_status": qualification_landlock["status"],
                "landlock_observed_abi": qualification_landlock["observed_abi"],
                "cuda_preflight_file": _file_record(qualification_cuda_path),
                "cuda_preflight_receipt_sha256": qualification_cuda["receipt_sha256"],
                "cuda_preflight_status": qualification_cuda["status"],
                "cuda_preflight_closure_scope": qualification_cuda["closure_scope"],
                "cuda_preflight_closure_inventory_sha256": qualification_cuda[
                    "closure_inventory_sha256"
                ],
                "cuda_preflight_completed_at_utc": qualification_cuda[
                    "completed_at_utc"
                ],
                "cuda_preflight_completed_host_age_seconds": 60,
                "bootstrap_roots_manifest_receipt_sha256": bootstrap_commitment[
                    "receipt_sha256"
                ],
                "python_executable": python_executable,
                "active_root": active_root,
                "device_files": [row["path"] for row in devices],
                "child_argv_sha256": qualification_landlock["child_argv_sha256"],
                "provider": qualification_cuda["provider"],
                "cuda": {
                    name: qualification_cuda["cuda"][name]
                    for name in (
                        "device",
                        "device_count",
                        "device_name",
                        "device_capability",
                        "matmul_finite",
                        "synchronized",
                        "raw_tensor_operations_only",
                    )
                },
            }
            command_tail.extend(
                [
                    "--host-created-at-utc",
                    target_host["created_at_utc"],
                    "--qualification-ownership",
                    (
                        target_test_root
                        / verifier.TARGET_QUALIFICATION_OWNERSHIP_RELATIVE.name
                    ).as_posix(),
                    "--qualification-landlock",
                    (
                        target_test_root
                        / verifier.TARGET_QUALIFICATION_LANDLOCK_RELATIVE.name
                    ).as_posix(),
                    "--qualification-cuda-preflight",
                    (
                        target_test_root
                        / verifier.TARGET_QUALIFICATION_CUDA_RELATIVE.name
                    ).as_posix(),
                ]
            )
        command_tail.extend(["--output", receipt_path.as_posix()])
        command_argv = [
            "/usr/bin/python3",
            "-m",
            "experiments.consciousness_sae_target_blind_calibration.audit_recovery",
            *command_tail,
        ]
        collected_ids = sorted({*passed_ids, *skipped_ids})
        core = {
            "schema_version": 1,
            "receipt_type": verifier.TEST_RECEIPT_TYPE,
            "kind": kind,
            "status": verifier.TEST_RECEIPT_STATUS,
            "code_freeze_commit": code_freeze,
            "observed_git_head_commit": (
                "b" * 40
                if target and mutation == "target_observed_head"
                else code_freeze
            ),
            "source_test_files": receipt_source_test_files,
            "source_test_file_count": len(receipt_source_test_files),
            "source_test_inventory_sha256": verifier.canonical_sha256(
                receipt_source_test_files
            ),
            "command_argv": command_argv,
            "command": verifier.shlex.join(command_argv),
            "command_argv_sha256": verifier.canonical_sha256(command_argv),
            "receipt_path": receipt_path.as_posix(),
            "pytest_argv": list(verifier.FOCUSED_PYTEST_ARGV),
            "interpreter": {
                "executable": "/opt/qualification/bin/python",
                "implementation": "CPython",
                "version": "3.11.13",
                "cache_tag": "cpython-311",
            },
            "platform": {
                "system": "Linux" if target else "Darwin",
                "release": "6.8.0" if target else "25.5.0",
                "version": "fixture",
                "machine": "x86_64" if target else "arm64",
            },
            "dependencies": dependencies,
            "dependency_inventory_sha256": verifier.canonical_sha256(dependencies),
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
            "designated_target_ids": list(verifier.TARGET_DESIGNATED_TEST_IDS),
            "started_at_utc": "1970-01-01T00:12:00Z",
            "completed_at_utc": "1970-01-01T00:13:00Z",
            "exit_code": 0,
            "target_host": target_host,
            "qualification_probe": probe_summary,
        }
        return _seal(core)

    local = receipt("local")
    target = receipt("target_host")
    local_path = root / verifier.LOCAL_TEST_RELATIVE
    target_path = root / verifier.TARGET_HOST_TEST_RELATIVE
    _write(local_path, local)
    _write(target_path, target)
    return (
        local,
        target,
        local_path,
        target_path,
        qualification_landlock_path,
        qualification_cuda_path,
        qualification_ownership_path,
    )


def _build_bundle(tmp_path: Path, *, mutation: str | None = None) -> Path:
    git_head = "abcdef0" + "1" * 33
    attempt_id = "calv2-r3-audit-recovery-abcdef0-20260715T010203Z"
    root = tmp_path / attempt_id
    root.mkdir()
    paths = verifier._expected_paths(attempt_id)  # noqa: SLF001
    if mutation == "superseded_path":
        paths = dict(paths)
        paths["superseded_runtime_block"] = f"{paths['output_root']}/wrong.json"
    attempt_root = paths["output_root"].removesuffix("/output")
    devices = [_device()]
    pod_id = "test-pod"
    active_root = f"/root/consciousness_sae_audit_recovery/{attempt_id}/active"
    python_executable = f"{active_root}/.venv/bin/python"
    closure_hashes = {
        path: verifier.canonical_sha256({"closure_path": path})
        for path in verifier.RECOVERY_BOUND_PATHS
    }
    closure_hashes[
        "experiments/consciousness_sae_target_blind_calibration/audit_recovery.py"
    ] = "b" * 64
    closure_hashes[
        "experiments/consciousness_sae_target_blind_calibration/landlock_launcher.py"
    ] = "9" * 64
    closure_hashes.update(verifier.HISTORICAL_INCOMPLETE_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.HISTORICAL_V2_PRO_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.HISTORICAL_V3_NEGATIVE_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.HISTORICAL_V4_NEGATIVE_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.V4_TIMED_QUALIFICATION_PHYSICAL_SHA256)
    closure_hashes.update(verifier.HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(
        verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256
    )
    closure_hashes.update(verifier.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256)
    closure_hashes.update(verifier.B18_COMPACT_EVIDENCE_PHYSICAL_SHA256)
    closure_hashes.update(verifier.B20_COMPACT_EVIDENCE_PHYSICAL_SHA256)
    closure_hashes.update(verifier.C6_SUPERSEDED_QUALIFICATION_PHYSICAL_SHA256)
    closure_hashes.update(verifier.C7_FAILED_QUALIFICATION_PHYSICAL_SHA256)
    if mutation == "historical_review_physical":
        closure_hashes[verifier.HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON] = (
            "0" * 64
        )
    if mutation == "historical_v2_review_physical":
        closure_hashes[verifier.HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON] = "0" * 64
    if mutation == "historical_v3_review_physical":
        closure_hashes[verifier.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON] = (
            "0" * 64
        )
    if mutation == "historical_v4_review_physical":
        closure_hashes[verifier.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON] = (
            "0" * 64
        )
    if mutation == "historical_v5_review_physical":
        closure_hashes[verifier.FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON] = "0" * 64
    if mutation == "historical_v6_review_physical":
        first_v6_path = next(
            iter(verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256)
        )
        closure_hashes[first_v6_path] = "0" * 64
    if mutation == "historical_v7_review_physical":
        first_v7_path = next(
            iter(verifier.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256)
        )
        closure_hashes[first_v7_path] = "0" * 64
    if mutation == "b20_incident_physical":
        first_b20_path = next(iter(verifier.B20_COMPACT_EVIDENCE_PHYSICAL_SHA256))
        closure_hashes[first_b20_path] = "0" * 64
    recovery_bound_files = [
        {"path": path, "bytes": 100 + index, "sha256": closure_hashes[path]}
        for index, path in enumerate(verifier.RECOVERY_BOUND_PATHS)
    ]
    if mutation == "closure_order":
        recovery_bound_files[0], recovery_bound_files[1] = (
            recovery_bound_files[1],
            recovery_bound_files[0],
        )
    (
        local_test_receipt,
        target_host_test_receipt,
        local_test_receipt_path,
        target_host_test_receipt_path,
        qualification_landlock_path,
        qualification_cuda_path,
        qualification_ownership_path,
    ) = _test_receipt_evidence(
        root,
        recovery_bound_files,
        mutation=mutation,
        code_freeze="c" * 40,
    )
    snapshot_paths = {
        verifier.V8_LOCAL_TEST_RECEIPT_SNAPSHOT: local_test_receipt_path,
        verifier.V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT: target_host_test_receipt_path,
        verifier.V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT: (
            qualification_ownership_path
        ),
        verifier.V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT: (
            qualification_landlock_path
        ),
        verifier.V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT: qualification_cuda_path,
    }
    for row in recovery_bound_files:
        snapshot = snapshot_paths.get(row["path"])
        if snapshot is not None:
            row.update(_file_record(snapshot))
            closure_hashes[row["path"]] = row["sha256"]
    if mutation == "reviewed_snapshot_mismatch":
        for row in recovery_bound_files:
            if row["path"] == verifier.V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT:
                row["sha256"] = "0" * 64
                closure_hashes[row["path"]] = row["sha256"]
                break
    bootstrap_manifest = _bootstrap_manifest(
        active_root=active_root,
        python_executable=python_executable,
        closure=recovery_bound_files,
        bootstrap_sha256=closure_hashes[verifier.BOOTSTRAP_RELATIVE_PATH],
    )
    if mutation == "bootstrap_manifest_inventory":
        manifest_core = dict(bootstrap_manifest)
        manifest_core.pop("receipt_sha256")
        manifest_core["roots_inventory_sha256"] = "0" * 64
        bootstrap_manifest = _seal(manifest_core)
    bootstrap_manifest_path = root / verifier.BOOTSTRAP_MANIFEST_RELATIVE
    _write(bootstrap_manifest_path, bootstrap_manifest)
    roots_manifest_sha256 = verifier.sha256_file(bootstrap_manifest_path)
    bootstrap_roots, bootstrap_files = verifier._bootstrap_protected_paths(  # noqa: SLF001
        bootstrap_manifest, paths
    )
    _plan, _provenance_paths, historical_provenance_files = (
        audit_recovery._validate_pre_gpu_issue_inputs(  # noqa: SLF001
            audit_recovery.REPO_ROOT / verifier.CANONICAL_PLAN_RELATIVE_PATH
        )
    )
    if mutation == "auth_provenance_semantic":
        historical_provenance_files = [dict(row) for row in historical_provenance_files]
        historical_provenance_files[0]["sha256"] = "0" * 64

    preflight_child = verifier._expected_preflight_argv(  # noqa: SLF001
        python_executable,
        active_root,
        paths,
        roots_manifest_sha256,
        [row["path"] for row in devices],
    )
    if mutation == "preflight_argv":
        preflight_child = [*preflight_child[:-2], "--output", "/wrong/output.json"]
    preflight_landlock = _landlock(
        purpose="preauthorization_probe",
        pid=101,
        receipt_path=paths["preflight_landlock"],
        output_root=paths["preflight_output_root"],
        protected_roots=[paths["preflight_canary_protected_root"], *bootstrap_roots],
        protected_files=[
            f"{paths['preflight_canary_protected_root']}/seed.txt",
            *bootstrap_files,
        ],
        canary_output_root=paths["preflight_canary_output_root"],
        child_argv=preflight_child,
        devices=devices,
    )
    if mutation == "protected_check_preflight":
        landlock_core = dict(preflight_landlock)
        landlock_core.pop("receipt_sha256")
        landlock_core["protected_checks"] = []
        preflight_landlock = _seal(landlock_core)
    preflight_landlock_path = root / verifier.PREFLIGHT_ENFORCEMENT_RELATIVE
    _write(preflight_landlock_path, preflight_landlock)

    environment = dict(verifier.FIXED_ENVIRONMENT)
    environment.update(
        {
            name: f"{paths['preflight_output_root']}/writable/{name.lower()}"
            for name in verifier.DYNAMIC_ENVIRONMENT
        }
    )
    if mutation == "environment_lexical_escape":
        environment["HOME"] = f"{paths['preflight_output_root']}/../raw"
    preflight_bootstrap_attestation = _bootstrap_attestation(
        mode="preflight-child",
        pid=101,
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=paths["roots_manifest"],
        roots_manifest_sha256=roots_manifest_sha256,
        manifest=bootstrap_manifest,
    )
    if mutation == "bootstrap_preflight_attestation":
        attestation_core = dict(preflight_bootstrap_attestation)
        attestation_core.pop("receipt_sha256")
        attestation_core["site_imported"] = True
        preflight_bootstrap_attestation = _seal(attestation_core)
    preflight_cuda_core = {
        "schema_version": 1,
        "status": "pass_target_free_landlock_cuda_preflight",
        "pid": 101,
        "python_executable": python_executable,
        "active_root": (
            "/root/wrong-active-root" if mutation == "cuda_active_root" else active_root
        ),
        "closure_scope": "final_recovery",
        "closure_files": recovery_bound_files,
        "closure_file_count": len(recovery_bound_files),
        "closure_inventory_sha256": verifier.canonical_sha256(recovery_bound_files),
        "recovery_closure_sha256": (
            "0" * 64
            if mutation == "recovery_closure"
            else verifier.canonical_sha256(recovery_bound_files)
        ),
        "bootstrap_roots_manifest": {
            "path": paths["roots_manifest"],
            "file_sha256": roots_manifest_sha256,
            "receipt_sha256": bootstrap_manifest["receipt_sha256"],
            "roots_inventory_sha256": bootstrap_manifest["roots_inventory_sha256"],
            "bootstrap_sha256": bootstrap_manifest["bootstrap_sha256"],
            "active_root": active_root,
            "python_executable": python_executable,
            "root_paths": sorted(row["path"] for row in bootstrap_manifest["roots"]),
            "sys_path": bootstrap_manifest["sys_path"],
        },
        "qualification_ownership_receipt_sha256": None,
        "landlock_receipt_sha256": preflight_landlock["receipt_sha256"],
        "package_versions": dict(verifier.EXPECTED_PACKAGES),
        "imported_package_versions": dict(verifier.EXPECTED_IMPORTED_PACKAGES),
        "environment": environment,
        "absent_environment_variables": list(verifier.FORBIDDEN_ENVIRONMENT),
        "provider": {
            "pod_id": pod_id,
            "volume_id": verifier.NETWORK_VOLUME_ID,
            "data_center_id": verifier.DATA_CENTER_ID,
        },
        "cuda": {
            "available": True,
            "device": "cuda:0",
            "device_count": 1,
            "device_name": "NVIDIA B200",
            "device_capability": [10, 0],
            "dtype": "torch.bfloat16",
            "shape": [16, 16],
            "matmul_finite": True,
            "synchronized": True,
            "raw_tensor_operations_only": True,
        },
        "model_forward_count": 1 if mutation == "cuda_forward" else 0,
        "torch_module_call_count": 0,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "external_or_prior_outcome_inputs": [],
        "bootstrap": _bootstrap_phase(
            verifier.BOOTSTRAP_PREFLIGHT_PHASE,
            preflight_bootstrap_attestation,
        ),
        "completed_at_utc": "2026-07-15T01:02:03Z",
    }
    if mutation == "absent_environment":
        preflight_cuda_core["absent_environment_variables"] = list(
            verifier.FORBIDDEN_ENVIRONMENT[:-1]
        )
    preflight_cuda = _seal(preflight_cuda_core)
    preflight_cuda_path = root / verifier.PREFLIGHT_CUDA_RELATIVE
    _write(preflight_cuda_path, preflight_cuda)
    execution_core = {
        "attempt_id": attempt_id,
        "attempt_root": attempt_root,
        "paths": paths,
        "artifact_device": "cuda:0",
        "device_files": [row["path"] for row in devices],
        "launcher_mode": "audit_recovery",
        "active_root": active_root,
        "python_executable": python_executable,
        "roots_manifest_sha256": roots_manifest_sha256,
        "confined_child_argv": verifier._expected_confined_argv(  # noqa: SLF001
            python_executable,
            active_root,
            attempt_id,
            paths,
            roots_manifest_sha256,
            [row["path"] for row in devices],
        ),
    }
    execution_core["confined_child_argv_sha256"] = verifier.canonical_sha256(
        execution_core["confined_child_argv"]
    )
    execution = {
        **execution_core,
        "command_sha256": verifier.canonical_sha256(execution_core),
    }
    original_receipts = dict(verifier.ORIGINAL_RECEIPTS)
    fresh_receipts = {"ownership": "7" * 64, "guest": "8" * 64, "cache": "a" * 64}
    superseded_recovery_host = dict(verifier.SUPERSEDED_RECOVERY_HOST)
    if mutation == "superseded_block":
        superseded_recovery_host["audit_execute_invoked"] = True
    external_files = {
        name: {
            "bytes": 300 + index,
            "sha256": verifier.canonical_sha256({"external": name}),
        }
        for index, name in enumerate(sorted(verifier.EXTERNAL_FILE_KEYS))
    }
    external_files["preflight_landlock"] = _file_record(preflight_landlock_path)
    external_files["preflight_probe"] = _file_record(preflight_cuda_path)
    external_files["roots_manifest"] = _file_record(bootstrap_manifest_path)
    external_files["local_test_receipt"] = _file_record(local_test_receipt_path)
    external_files["target_host_test_receipt"] = _file_record(
        target_host_test_receipt_path
    )
    external_files["target_qualification_ownership"] = _file_record(
        qualification_ownership_path
    )
    external_files["target_qualification_landlock"] = _file_record(
        qualification_landlock_path
    )
    external_files["target_qualification_cuda_preflight"] = _file_record(
        qualification_cuda_path
    )
    if mutation == "superseded_file_record":
        external_files["superseded_runtime_block"] = {
            "bytes": 100,
            "sha256": "A" * 64,
        }
    qualification_ownership = json.loads(qualification_ownership_path.read_text())
    qualification_landlock = json.loads(qualification_landlock_path.read_text())
    qualification_cuda = json.loads(qualification_cuda_path.read_text())
    review = {
        "model": "gpt-5.6-sol",
        "provider_status": "completed",
        "provider_terminal_verdict": "READY TO FREEZE",
        "response_id": "resp_test",
        "input_tokens": 1000,
        "output_tokens": 200,
        "reasoning_tokens": 50,
        "reconstructed_cost_usd": 0.02,
        "provider_approval_claimed": False,
        "provider_ready_to_freeze_verdict": True,
        "source_and_tests_reviewed_by_provider": True,
        "reviewed_packet_was_pre_fix": False,
        "final_source_reviewed_by_provider": True,
        "provider_reviewed_final_bytes_unchanged": True,
        "reviewed_packet_git_head_commit": "e" * 40,
        "final_git_head_commit": git_head,
        "code_freeze_commit": local_test_receipt["code_freeze_commit"],
        "source_test_inventory_sha256": local_test_receipt[
            "source_test_inventory_sha256"
        ],
        "historical_v2_terminal_verdict": "NOT READY TO FREEZE",
        "historical_v2_adjudication_receipt_sha256": (
            verifier.HISTORICAL_V2_ADJUDICATION_RECEIPT_SHA256
        ),
        "historical_v2_remaining_blocking_findings": ["B06", "B07", "B08", "B09"],
        "historical_v3_terminal_verdict": "NOT READY TO FREEZE",
        "historical_v3_adjudication_receipt_sha256": (
            verifier.HISTORICAL_V3_NEGATIVE_ADJUDICATION_RECEIPT_SHA256
        ),
        "historical_v3_remaining_blocking_findings": ["B10", "B11"],
        "historical_v4_terminal_verdict": "NOT READY TO FREEZE",
        "historical_v4_adjudication_receipt_sha256": (
            verifier.HISTORICAL_V4_NEGATIVE_ADJUDICATION_RECEIPT_SHA256
        ),
        "historical_v4_remaining_blocking_findings": ["B12"],
        "historical_v4_input_tokens_preflight": (
            verifier.HISTORICAL_V4_INPUT_TOKENS_PREFLIGHT
        ),
        "historical_v4_recorded_cost_usd": verifier.HISTORICAL_V4_RECORDED_COST_USD,
        "historical_v4_retrospective_long_context_cost_usd": (
            verifier.HISTORICAL_V4_RETROSPECTIVE_LONG_CONTEXT_COST_USD
        ),
        "historical_v4_budget_authorization_usd": (
            verifier.HISTORICAL_V4_BUDGET_AUTHORIZATION_USD
        ),
        "historical_v4_pricing_disclosure_status": (
            "historical_manifest_short_rate_plus_retrospective_long_context_"
            "reconstruction_not_invoice"
        ),
        "historical_v5_terminal_verdict": "READY TO FREEZE",
        "historical_v5_response_id": (
            "resp_0322d12a79eb8aa5016a576d65fc94819ba2ed3994c7f8cbf0"
        ),
        "historical_v5_review_sha256": (
            verifier.HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V5_PRO_REVIEW_DIRECTORY}/review.md"
            ]
        ),
        "historical_v5_adjudication_receipt_sha256": (
            "05e23d2f90de9458b75ef7d84be23d73018ab8a4f46b3edcac12217793607257"
        ),
        "historical_v5_adjudication_json_sha256": (
            verifier.HISTORICAL_V5_POSITIVE_REVIEW_PHYSICAL_SHA256[
                verifier.FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON
            ]
        ),
        "historical_v5_superseded_reason": (
            "post_review_authentic_issue_gate_failed_b14"
        ),
        "historical_v5_input_tokens_preflight": (
            verifier.HISTORICAL_V5_INPUT_TOKENS_PREFLIGHT
        ),
        "historical_v5_recorded_cost_usd": verifier.HISTORICAL_V5_RECORDED_COST_USD,
        "historical_v5_retrospective_long_context_cost_usd": (
            verifier.HISTORICAL_V5_RETROSPECTIVE_LONG_CONTEXT_COST_USD
        ),
        "historical_v5_budget_authorization_usd": (
            verifier.HISTORICAL_V5_BUDGET_AUTHORIZATION_USD
        ),
        "historical_v5_pricing_disclosure_status": (
            "historical_manifest_short_rate_plus_retrospective_long_context_"
            "reconstruction_not_invoice"
        ),
        "historical_v6_terminal_verdict": "READY TO FREEZE",
        "historical_v6_response_id": (
            "resp_096bfc4229fd22e6016a57992e0f648199913ca0849879a9a3"
        ),
        "historical_v6_review_sha256": (
            verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md"
            ]
        ),
        "historical_v6_manifest_file_sha256": (
            verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json"
            ]
        ),
        "historical_v6_response_file_sha256": (
            verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json"
            ]
        ),
        "historical_v6_request_payload_file_sha256": (
            verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json"
            ]
        ),
        "historical_v6_review_request_file_sha256": (
            verifier.HISTORICAL_V6_NONADJUDICABLE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md"
            ]
        ),
        "historical_v6_reviewed_packet_git_head_commit": (
            "4e8752ebc89ff69924c1604022720cb5258cbbdd"
        ),
        "historical_v6_nonadjudicable_reason": (
            "b16_prose_wide_identifier_extraction_included_nonfinding_b05"
        ),
        "historical_v6_authorization_status": (
            "historical_ready_verdict_nonadjudicable"
        ),
        "historical_v7_terminal_verdict": "READY TO FREEZE",
        "historical_v7_response_id": (
            "resp_0162174969ec5bcb016a57a36b0030819ba940698d372c5f40"
        ),
        "historical_v7_review_sha256": (
            verifier.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256[
                f"{verifier.FINAL_V7_PRO_REVIEW_DIRECTORY}/review.md"
            ]
        ),
        "historical_v7_adjudication_receipt_sha256": (
            "029ae539291a6307c2c49609655bfb427a42a11629e6c9283f212ae2b5e8f93c"
        ),
        "historical_v7_adjudication_json_sha256": (
            verifier.HISTORICAL_V7_POSITIVE_REVIEW_PHYSICAL_SHA256[
                verifier.FINAL_V7_PRO_REVIEW_ADJUDICATION_JSON
            ]
        ),
        "historical_v7_final_git_head_commit": (
            "2479ed0c767fba7c872dbbd48666b5a598e2b9f6"
        ),
        "historical_b17_terminal_verdict": "READY AFTER SPECIFIED FIXES",
        "historical_b17_response_id": (
            "resp_0038445e5c1ea968016a57b46d6378819893a1587d331ce1a6"
        ),
        "historical_b17_review_sha256": (
            verifier.HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256[
                f"{verifier.HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review.md"
            ]
        ),
        "historical_b17_manifest_file_sha256": (
            verifier.HISTORICAL_B17_PRO_REVIEW_PHYSICAL_SHA256[
                f"{verifier.HISTORICAL_B17_PRO_REVIEW_DIRECTORY}/review_manifest.json"
            ]
        ),
        "historical_b17_finding_ids": list(verifier.HISTORICAL_B17_FINDING_IDS),
        "historical_b17_recorded_cost_usd": 1.830595,
        "historical_b17_incomplete_response_id": (
            "resp_0a3a9f471779e79c016a57b366162481988f0d8b2d3f04e061"
        ),
        "historical_b17_incomplete_cost_usd": 3.00996,
        "b18_closure_receipt_sha256": (
            "7d1d702efeace1d16010fec2bc1093069b1ed3c43a24bf669485ff283a6ca35f"
        ),
        "b20_closure_receipt_sha256": (
            "3f5dee0ccbef6af18302667c0cea95be0c7e4c4cd6d1f9b0d61a4222c1e157d9"
        ),
        "b20_verification_receipt_sha256": (
            "49376b10210fb4ac0409c560287ff817bbc21bc0fadbf1e28c6fc1d36f9de84d"
        ),
        "b20_attempt_id": (
            "calv2-r3-audit-recovery-2479ed0-20260715T165648Z"
        ),
        "b20_pod_id": "eeo1skjkwjqot5",
        "b20_scientific_result_status": "none_produced",
        "timed_qualification_receipt_sha256": (
            "0c83eea18a0b4ed622e02846d224457421ca970c1d72b980ee9825a8420e4d34"
        ),
        "timed_qualification_termination_receipt_sha256": (
            "cc5be37fcbc739d3bd15d6df245138910872e717e7abdfaa4f05f9d2abffb1c5"
        ),
        "timed_qualification_pod_id": "sguho6ni8p5nbo",
        "timed_qualification_authorization_ready_host_age_seconds": 958,
        "timed_qualification_seconds_remaining": 2642,
        "timed_qualification_reserve_surplus_seconds": 842,
        "timed_qualification_public_artifact_file_count": 45,
        "timed_qualification_public_artifact_total_bytes": 156_023_372_845,
        "timed_qualification_cuda_preflight_closure_scope": (
            "source_test_qualification"
        ),
        "timed_qualification_final_recovery_scope_must_repeat": True,
        "finding_ids": sorted([*verifier.HISTORICAL_B17_FINDING_IDS, "B20"]),
        "review_sha256": closure_hashes[
            f"{verifier.FINAL_V8_PRO_REVIEW_DIRECTORY}/review.md"
        ],
        "adjudication_receipt_sha256": "6" * 64,
        "adjudication_json_sha256": closure_hashes[
            verifier.FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON
        ],
        "adjudication_markdown_sha256": closure_hashes[
            verifier.FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "fixed_finding_ids": sorted([*verifier.HISTORICAL_B17_FINDING_IDS, "B20"]),
        "rejected_finding_ids": [],
        "reviewed_local_test_receipt_file_sha256": _file_record(
            local_test_receipt_path
        )["sha256"],
        "reviewed_local_test_receipt_receipt_sha256": local_test_receipt[
            "receipt_sha256"
        ],
        "reviewed_target_host_test_receipt_file_sha256": _file_record(
            target_host_test_receipt_path
        )["sha256"],
        "reviewed_target_host_test_receipt_receipt_sha256": target_host_test_receipt[
            "receipt_sha256"
        ],
        "reviewed_target_qualification_ownership_file_sha256": _file_record(
            qualification_ownership_path
        )["sha256"],
        "reviewed_target_qualification_ownership_receipt_sha256": (
            qualification_ownership["receipt_sha256"]
        ),
        "reviewed_target_qualification_landlock_file_sha256": _file_record(
            qualification_landlock_path
        )["sha256"],
        "reviewed_target_qualification_landlock_receipt_sha256": (
            qualification_landlock["receipt_sha256"]
        ),
        "reviewed_target_qualification_cuda_file_sha256": _file_record(
            qualification_cuda_path
        )["sha256"],
        "reviewed_target_qualification_cuda_receipt_sha256": qualification_cuda[
            "receipt_sha256"
        ],
        "historical_pre_v2_paid_call_count": 2,
        "historical_v2_paid_call_count": 1,
        "historical_v3_paid_call_count": 1,
        "historical_v4_paid_call_count": 1,
        "completed_v5_paid_call_count": 1,
        "completed_v6_paid_call_count": 1,
        "completed_v7_paid_call_count": 1,
        "incomplete_b17_paid_call_count": 1,
        "completed_b17_paid_call_count": 1,
        "completed_v8_paid_call_count": 1,
        "cumulative_disclosed_paid_call_count": 11,
    }
    authorization_core = {
        "schema_version": 1,
        "status": "authorized_audit_only_recovery_landlock_confined",
        "study_id": verifier.STUDY_ID,
        "protocol_version": verifier.PROTOCOL_VERSION,
        "recovery_protocol_version": verifier.RECOVERY_PROTOCOL_VERSION,
        "run_id": verifier.RUN_ID,
        "raw_root": f"/workspace/{verifier.RAW_RELATIVE}",
        "raw_run_receipt_sha256": verifier.ORIGINAL_RUN_RECEIPT_SHA256,
        "plan_manifest_sha256": verifier.PLAN_MANIFEST_SHA256,
        "recovery_bound_files": recovery_bound_files,
        "recovery_bound_paths_sha256": verifier.canonical_sha256(
            verifier.RECOVERY_BOUND_PATHS
        ),
        "historical_provenance_files": historical_provenance_files,
        "historical_provenance_inventory_sha256": verifier.canonical_sha256(
            historical_provenance_files
        ),
        "bootstrap_import_roots": {
            "path": paths["roots_manifest"],
            "physical_file": _file_record(bootstrap_manifest_path),
            "manifest": bootstrap_manifest,
        },
        "original_receipts": original_receipts,
        "superseded_recovery_host": superseded_recovery_host,
        "fresh_receipts": fresh_receipts,
        "preflight": {
            "landlock_receipt": preflight_landlock,
            "landlock_file": _file_record(preflight_landlock_path),
            "probe_receipt": preflight_cuda,
            "probe_file": _file_record(preflight_cuda_path),
            "device_rules": devices,
        },
        "test_receipts": {
            "local": local_test_receipt,
            "target_host": target_host_test_receipt,
        },
        "external_files": external_files,
        "fresh_pod_id": pod_id,
        "volume_id": verifier.NETWORK_VOLUME_ID,
        "data_center_id": verifier.DATA_CENTER_ID,
        "gpu_type": verifier.GPU_TYPE,
        "gpu_count": 1,
        "recovery_started_at_unix": 1000.0,
        "recovery_deadline_at_unix": 4600.0,
        "provider_deadline_at_unix": 5000.0,
        "max_walltime_seconds": 3600,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 6.0,
        "authorized_at_utc": "1970-01-01T00:20:00Z",
        "model_forward_limit": 0,
        "target_prompt_render_limit": 0,
        "target_feature_vector_limit": 0,
        "external_or_prior_outcome_inputs": [],
        "write_confinement": dict(verifier.LANDLOCK_POLICY),
        "execution": execution,
        "review": review,
        "git_head_commit": git_head,
        "git_remote_ref": "refs/heads/main",
        "git_local_remote_ref": "refs/remotes/origin/main",
        "git_local_remote_commit": git_head,
        "git_live_remote_commit": git_head,
    }
    if mutation == "auth_path_hash":
        authorization_core["recovery_bound_paths_sha256"] = "0" * 64
    elif mutation == "auth_plan_hash":
        authorization_core["plan_manifest_sha256"] = "0" * 64
    elif mutation == "auth_external_missing":
        authorization_core["external_files"] = dict(external_files)
        authorization_core["external_files"].pop("failure_log")
    elif mutation == "auth_git_mismatch":
        authorization_core["git_live_remote_commit"] = "1" * 40
    elif mutation == "auth_review_overclaim":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["provider_approval_claimed"] = True
    elif mutation == "auth_review_final_bytes":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["provider_reviewed_final_bytes_unchanged"] = False
    elif mutation == "auth_review_call_count":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["cumulative_disclosed_paid_call_count"] = 2
    elif mutation == "auth_review_git_head":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["final_git_head_commit"] = "F" * 40
    elif mutation == "auth_review_terminal":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["provider_terminal_verdict"] = "READY_TO_EXECUTE"
    elif mutation == "auth_review_b17_omitted":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["finding_ids"] = [
            finding for finding in review["finding_ids"] if finding != "B17"
        ]
        authorization_core["review"]["fixed_finding_ids"] = [
            finding for finding in review["fixed_finding_ids"] if finding != "B17"
        ]
    elif mutation == "auth_review_b20_omitted":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["finding_ids"] = [
            finding for finding in review["finding_ids"] if finding != "B20"
        ]
        authorization_core["review"]["fixed_finding_ids"] = [
            finding for finding in review["fixed_finding_ids"] if finding != "B20"
        ]
    elif mutation == "auth_review_historical_b17":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["historical_b17_finding_ids"] = [
            "B17",
            "B18",
            "B19",
        ]
    elif mutation == "auth_review_historical_v4_blocker":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["historical_v4_remaining_blocking_findings"] = [
            "B11"
        ]
    elif mutation == "auth_review_historical_pricing":
        authorization_core["review"] = dict(review)
        authorization_core["review"][
            "historical_v5_retrospective_long_context_cost_usd"
        ] = verifier.HISTORICAL_V5_RECORDED_COST_USD
    elif mutation == "auth_review_reserved_finding_id":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["finding_ids"] = sorted(
            [*review["finding_ids"], "B05"]
        )
        authorization_core["review"]["fixed_finding_ids"] = sorted(
            [*review["fixed_finding_ids"], "B05"]
        )
    elif mutation == "auth_review_new_blocker":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["finding_ids"] = sorted(
            [*review["finding_ids"], "B21"]
        )
        authorization_core["review"]["fixed_finding_ids"] = sorted(
            [*review["fixed_finding_ids"], "B21"]
        )
    elif mutation == "auth_review_snapshot_receipt":
        authorization_core["review"] = dict(review)
        authorization_core["review"][
            "reviewed_target_qualification_ownership_receipt_sha256"
        ] = "0" * 64
    elif mutation == "auth_review_cost_boundary":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["reconstructed_cost_usd"] = (
            verifier.COMPLETED_REVIEW_COST_CEILING_USD
        )
    elif mutation == "auth_review_cost_over":
        authorization_core["review"] = dict(review)
        authorization_core["review"]["reconstructed_cost_usd"] = (
            verifier.COMPLETED_REVIEW_COST_CEILING_USD + 0.000001
        )
    elif mutation == "auth_clock":
        authorization_core["provider_deadline_at_unix"] = 4500.0
    authorization = _seal(authorization_core)
    _write(root / verifier.AUTHORIZATION_RELATIVE, authorization)

    confinement_devices = (
        [_device(inode=8)] if mutation == "device_mismatch" else devices
    )
    confinement = _landlock(
        purpose="audit_recovery",
        pid=202,
        receipt_path=paths["landlock_receipt"],
        output_root=paths["output_root"],
        protected_roots=[
            paths["raw_root"],
            paths["provenance_root"],
            paths["canary_protected_root"],
            *bootstrap_roots,
        ],
        protected_files=[
            f"{paths['raw_root']}/RUN_COMPLETE.json",
            (
                f"{paths['provenance_root']}/{verifier.CANONICAL_PLAN_RELATIVE_PATH}/"
                "plan_manifest.json"
            ),
            paths["recovery_authorization"],
            *bootstrap_files,
        ],
        canary_output_root=paths["canary_output_root"],
        child_argv=execution["confined_child_argv"],
        devices=confinement_devices,
        authorization_sha256=authorization["receipt_sha256"],
        preflight_sha256=preflight_cuda["receipt_sha256"],
        handled_access_fs=(
            0x7FF0 if mutation == "policy_mask" else verifier.HANDLED_ACCESS_FS
        ),
    )
    if mutation in {
        "descriptor_output_writable",
        "descriptor_unenumerated_nvidia",
        "descriptor_writable_block",
        "descriptor_io_uring",
        "mapping_schema",
        "baseline_missing",
        "protected_check_execution",
    }:
        confinement_core = dict(confinement)
        confinement_core.pop("receipt_sha256")
        if mutation.startswith("descriptor_"):
            descriptor = dict(confinement_core["descriptor_audit"])
            rows = [dict(row) for row in descriptor["descriptors"]]
            if mutation == "descriptor_output_writable":
                rows.append(
                    {
                        "fd": 3,
                        "target": f"{paths['output_root']}/already-open.json",
                        "kind": "regular_file",
                        "access_mode": os.O_WRONLY,
                        "writable": True,
                        "allowed_reason": "durable_output_root",
                    }
                )
            elif mutation == "descriptor_unenumerated_nvidia":
                rows.append(
                    {
                        "fd": 3,
                        "target": "/dev/nvidia9",
                        "kind": "character_device",
                        "access_mode": os.O_RDONLY,
                        "writable": False,
                        "allowed_reason": "read_only_descriptor",
                    }
                )
            elif mutation == "descriptor_writable_block":
                rows.append(
                    {
                        "fd": 3,
                        "target": "/dev/sda",
                        "kind": "block_device",
                        "access_mode": os.O_WRONLY,
                        "writable": True,
                        "allowed_reason": "non_regular_non_directory_descriptor",
                    }
                )
            else:
                rows.append(
                    {
                        "fd": 3,
                        "target": "anon_inode:[io_uring]",
                        "kind": "other",
                        "access_mode": os.O_RDONLY,
                        "writable": False,
                        "allowed_reason": "read_only_descriptor",
                    }
                )
            descriptor["descriptors"] = rows
            descriptor["descriptor_count"] = len(rows)
            confinement_core["descriptor_audit"] = descriptor
        elif mutation == "mapping_schema":
            confinement_core["mapping_audit"] = {
                "status": "pass_no_writable_shared_file_backed_mappings",
                "mapping_count": 20,
                "writable_shared_file_backed": [],
            }
        elif mutation == "baseline_missing":
            canary = dict(confinement_core["canary_checks"])
            canary["preconfinement_writable_baseline"] = canary[
                "preconfinement_writable_baseline"
            ][:-1]
            confinement_core["canary_checks"] = canary
        else:
            confinement_core["protected_checks"] = confinement_core["protected_checks"][
                :-1
            ]
        confinement = _seal(confinement_core)
    _write(root / verifier.CONFINEMENT_RELATIVE, confinement)

    marker = _seal(
        {
            "schema_version": 1,
            "status": "claimed_exactly_once",
            "study_id": verifier.STUDY_ID,
            "run_id": verifier.RUN_ID,
            "attempt_id": attempt_id,
            "claimed_at_utc": "2026-07-15T01:02:04Z",
            "claimed_at_unix": 2000.0,
            "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
            "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
            "landlock_pid": 203 if mutation == "pid_crosslink" else 202,
            "command_sha256": execution["command_sha256"],
            "recovery_source_sha256": "b" * 64,
        }
    )
    _write(root / verifier.ATTEMPT_MARKER_RELATIVE, marker)

    raw_pre = _raw_rehash("1" * 64)
    raw_post = _raw_rehash(
        "1" * 64,
        directory_inventory=(
            "6" * 64
            if mutation == "raw_directory_hash"
            else "A" * 64
            if mutation == "raw_directory_format"
            else "4" * 64
        ),
    )
    if mutation == "raw_schema_extra":
        raw_core = dict(raw_post)
        raw_core.pop("receipt_sha256")
        raw_core["unexpected"] = True
        raw_post = _seal(raw_core)
    provenance_inventory = verifier.canonical_sha256(historical_provenance_files)
    provenance_pre = _provenance_rehash(
        provenance_inventory,
        attempt_root,
        file_count=len(historical_provenance_files),
    )
    provenance_post = _provenance_rehash(
        provenance_inventory,
        attempt_root,
        file_count=len(historical_provenance_files),
        directory_count=(-1 if mutation == "provenance_directory_count" else 3),
    )
    executable_directories = verifier._expected_directory_inventory(  # noqa: SLF001
        verifier.RECOVERY_BOUND_PATHS
    )
    isolation = _seal(
        {
            "status": "pass_minimal_audit_only_executable",
            "active_root": execution["active_root"],
            "historical_provenance_root": paths["provenance_root"],
            "file_count": len(recovery_bound_files),
            "file_inventory_sha256": verifier.canonical_sha256(recovery_bound_files),
            "directory_count": len(executable_directories),
            "directory_inventory_sha256": verifier.canonical_sha256(
                executable_directories
            ),
            "forbidden_module_count": 0,
            "model_runtime_replaced_by": (
                "experiments.consciousness_sae_target_blind_calibration."
                "audit_runtime_shim"
            ),
        }
    )
    if mutation == "isolation_directory_hash":
        isolation_core = dict(isolation)
        isolation_core.pop("receipt_sha256")
        isolation_core["directory_inventory_sha256"] = "0" * 64
        isolation = _seal(isolation_core)
    j_inventory = {
        "available_layers": list(range(79)),
        "required_layers": list(range(45, 79)),
        "unused_extra_layers": list(range(45)),
        "available_map_count": 79,
        "required_map_count": 34,
        "inventory_sha256": verifier.canonical_sha256(list(range(79))),
    }
    if mutation == "j_inventory":
        j_inventory["unused_extra_layers"] = list(range(44))
    nested_preflight = dict(preflight_landlock)
    if mutation == "nested_receipt":
        nested_core = dict(nested_preflight)
        nested_core.pop("receipt_sha256")
        nested_core["observed_abi"] = 5
        nested_preflight = _seal(nested_core)
    execute_bootstrap_attestation = _bootstrap_attestation(
        mode="execute-confined",
        pid=202,
        active_root=active_root,
        python_executable=python_executable,
        roots_manifest_path=paths["roots_manifest"],
        roots_manifest_sha256=roots_manifest_sha256,
        manifest=bootstrap_manifest,
    )
    bootstrap_execute_entry_phase = _bootstrap_phase(
        verifier.BOOTSTRAP_EXECUTE_ENTRY_PHASE,
        execute_bootstrap_attestation,
    )
    bootstrap_prepublication_phase = _bootstrap_phase(
        verifier.BOOTSTRAP_PREPUBLICATION_PHASE,
        execute_bootstrap_attestation,
    )
    recovery_core = {
        "recovery_protocol_version": verifier.RECOVERY_PROTOCOL_VERSION,
        "status": "pass_disclosed_post_run_technical_recovery",
        "correction": "required_j_layers_subset_of_hash_pinned_release_inventory",
        "provider_review_status": "completed",
        "provider_review_approval_claimed": False,
        "provider_review_ready_to_freeze_verdict": True,
        "provider_review_source_and_tests_seen": True,
        "provider_reviewed_packet_was_pre_fix": False,
        "provider_reviewed_final_source": True,
        "provider_reviewed_final_bytes_unchanged": True,
        "recovery_authorization_receipt_sha256": authorization["receipt_sha256"],
        "attempt_id": attempt_id,
        "attempt_marker_receipt_sha256": marker["receipt_sha256"],
        "command_sha256": execution["command_sha256"],
        "recovery_bound_paths_sha256": authorization["recovery_bound_paths_sha256"],
        "plan_manifest_sha256": verifier.PLAN_MANIFEST_SHA256,
        "local_test_receipt_sha256": local_test_receipt["receipt_sha256"],
        "target_host_test_receipt_sha256": target_host_test_receipt["receipt_sha256"],
        "code_freeze_commit": local_test_receipt["code_freeze_commit"],
        "source_test_inventory_sha256": local_test_receipt[
            "source_test_inventory_sha256"
        ],
        "recovery_plan_sha256": closure_hashes[
            "docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_20260714.md"
        ],
        "recovery_source_sha256": marker["recovery_source_sha256"],
        "confined_bootstrap_sha256": closure_hashes[verifier.BOOTSTRAP_RELATIVE_PATH],
        "scientific_equivalence_source_sha256": closure_hashes[
            "experiments/consciousness_sae_target_blind_calibration/"
            "scientific_equivalence.py"
        ],
        "scientific_equivalence_test_sha256": closure_hashes[
            "tests/consciousness_sae_target_blind_calibration/"
            "test_scientific_equivalence.py"
        ],
        "scientific_equivalence_json_sha256": closure_hashes[
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json"
        ],
        "scientific_equivalence_markdown_sha256": closure_hashes[
            "docs/consciousness_sae_target_blind_calibration/"
            "AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.md"
        ],
        "landlock_launcher_sha256": confinement["source_sha256"],
        "bundle_verifier_sha256": closure_hashes[
            "experiments/consciousness_sae_target_blind_calibration/"
            "recovery_bundle_verifier.py"
        ],
        "recovery_test_sha256": closure_hashes[
            "tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py"
        ],
        "confined_bootstrap_test_sha256": closure_hashes[
            "tests/consciousness_sae_target_blind_calibration/"
            "test_confined_bootstrap.py"
        ],
        "landlock_test_sha256": closure_hashes[
            "tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py"
        ],
        "bundle_verifier_test_sha256": closure_hashes[
            "tests/consciousness_sae_target_blind_calibration/"
            "test_recovery_bundle_verifier.py"
        ],
        "historical_review_adjudication_json_sha256": closure_hashes[
            verifier.HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_JSON
        ],
        "historical_review_adjudication_markdown_sha256": closure_hashes[
            verifier.HISTORICAL_INCOMPLETE_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "historical_v2_review_adjudication_json_sha256": closure_hashes[
            verifier.HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_JSON
        ],
        "historical_v2_review_adjudication_markdown_sha256": closure_hashes[
            verifier.HISTORICAL_V2_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "historical_v3_review_adjudication_json_sha256": closure_hashes[
            verifier.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_JSON
        ],
        "historical_v3_review_adjudication_markdown_sha256": closure_hashes[
            verifier.HISTORICAL_V3_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "historical_v3_review_response_sha256": closure_hashes[
            f"{verifier.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/response.json"
        ],
        "historical_v3_review_manifest_sha256": closure_hashes[
            f"{verifier.HISTORICAL_V3_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json"
        ],
        "historical_v4_review_adjudication_json_sha256": closure_hashes[
            verifier.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_JSON
        ],
        "historical_v4_review_adjudication_markdown_sha256": closure_hashes[
            verifier.HISTORICAL_V4_NEGATIVE_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "historical_v4_review_response_sha256": closure_hashes[
            f"{verifier.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/response.json"
        ],
        "historical_v4_review_manifest_sha256": closure_hashes[
            f"{verifier.HISTORICAL_V4_NEGATIVE_REVIEW_DIRECTORY}/review_manifest.json"
        ],
        "historical_v5_review_adjudication_json_sha256": closure_hashes[
            verifier.FINAL_V5_PRO_REVIEW_ADJUDICATION_JSON
        ],
        "historical_v5_review_adjudication_markdown_sha256": closure_hashes[
            verifier.FINAL_V5_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "historical_v5_review_response_sha256": closure_hashes[
            f"{verifier.FINAL_V5_PRO_REVIEW_DIRECTORY}/response.json"
        ],
        "historical_v5_review_manifest_sha256": closure_hashes[
            f"{verifier.FINAL_V5_PRO_REVIEW_DIRECTORY}/review_manifest.json"
        ],
        "historical_v6_review_request_payload_sha256": closure_hashes[
            f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/request_payload.json"
        ],
        "historical_v6_review_response_sha256": closure_hashes[
            f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/response.json"
        ],
        "historical_v6_review_sha256": closure_hashes[
            f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review.md"
        ],
        "historical_v6_review_manifest_sha256": closure_hashes[
            f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review_manifest.json"
        ],
        "historical_v6_review_request_sha256": closure_hashes[
            f"{verifier.FINAL_V6_PRO_REVIEW_DIRECTORY}/review_request.md"
        ],
        "final_v8_review_adjudication_json_sha256": closure_hashes[
            verifier.FINAL_V8_PRO_REVIEW_ADJUDICATION_JSON
        ],
        "final_v8_review_adjudication_markdown_sha256": closure_hashes[
            verifier.FINAL_V8_PRO_REVIEW_ADJUDICATION_MARKDOWN
        ],
        "final_v8_review_response_sha256": closure_hashes[
            f"{verifier.FINAL_V8_PRO_REVIEW_DIRECTORY}/response.json"
        ],
        "final_v8_review_manifest_sha256": closure_hashes[
            f"{verifier.FINAL_V8_PRO_REVIEW_DIRECTORY}/review_manifest.json"
        ],
        "reviewed_local_test_receipt_snapshot_sha256": closure_hashes[
            verifier.V8_LOCAL_TEST_RECEIPT_SNAPSHOT
        ],
        "reviewed_target_host_test_receipt_snapshot_sha256": closure_hashes[
            verifier.V8_TARGET_HOST_TEST_RECEIPT_SNAPSHOT
        ],
        "reviewed_target_qualification_ownership_snapshot_sha256": closure_hashes[
            verifier.V8_TARGET_QUALIFICATION_OWNERSHIP_SNAPSHOT
        ],
        "reviewed_target_qualification_landlock_snapshot_sha256": closure_hashes[
            verifier.V8_TARGET_QUALIFICATION_LANDLOCK_SNAPSHOT
        ],
        "reviewed_target_qualification_cuda_snapshot_sha256": closure_hashes[
            verifier.V8_TARGET_QUALIFICATION_CUDA_SNAPSHOT
        ],
        "original_failed_audit_log_sha256": verifier.ORIGINAL_FAILURE_LOG_SHA256,
        "original_raw_run_receipt_sha256": authorization["raw_run_receipt_sha256"],
        "original_receipts": original_receipts,
        "superseded_recovery_host": superseded_recovery_host,
        "fresh_receipts": fresh_receipts,
        "fresh_pod_id": pod_id,
        "bootstrap_import_roots": authorization["bootstrap_import_roots"],
        "bootstrap_execute_entry_phase": bootstrap_execute_entry_phase,
        "bootstrap_prepublication_phase": bootstrap_prepublication_phase,
        "bootstrap_postdispatch_assertion": (
            "same_process_bootstrap_assert_clean_runs_after_recovery_dispatch_returns"
        ),
        "preflight_landlock_receipt": nested_preflight,
        "preflight_landlock_receipt_sha256": nested_preflight["receipt_sha256"],
        "preflight_probe_receipt": preflight_cuda,
        "preflight_probe_receipt_sha256": preflight_cuda["receipt_sha256"],
        "landlock_confinement_receipt": confinement,
        "landlock_confinement_receipt_sha256": confinement["receipt_sha256"],
        "write_confinement_policy": dict(verifier.LANDLOCK_POLICY),
        "write_confinement_claim": verifier.WRITE_CONFINEMENT_CLAIM,
        "landlock_limitations": dict(verifier.LANDLOCK_LIMITATIONS),
        "executable_isolation_receipt": isolation,
        "executable_isolation_receipt_sha256": isolation["receipt_sha256"],
        "provenance_pre_rehash_receipt": provenance_pre,
        "provenance_pre_rehash_receipt_sha256": provenance_pre["receipt_sha256"],
        "provenance_post_rehash_receipt": provenance_post,
        "provenance_post_rehash_receipt_sha256": provenance_post["receipt_sha256"],
        "historical_provenance_unchanged": True,
        "pre_rehash_receipt": raw_pre,
        "pre_rehash_receipt_sha256": raw_pre["receipt_sha256"],
        "post_rehash_receipt": raw_post,
        "post_rehash_receipt_sha256": raw_post["receipt_sha256"],
        "raw_unchanged": True,
        "zero_forward_guards": {
            "torch_module_calls": 0,
            "transformers_model_load_calls": 0,
        },
        "forbidden_module_guards": {"forbidden_module_import_attempts": 0},
        "j_checkpoint_inventory": j_inventory,
        "scientific_metrics_thresholds_layers_and_rows_changed": False,
        "fresh_model_execution_performed": False,
        "target_prompt_render_count": 0,
        "target_feature_vector_count": 0,
        "external_or_prior_outcome_inputs": [],
    }
    if mutation == "recovery_closure_link":
        recovery_core["bundle_verifier_sha256"] = "0" * 64
    elif mutation == "scientific_equivalence_link":
        recovery_core["scientific_equivalence_json_sha256"] = "0" * 64
    elif mutation == "bootstrap_recovery_phase":
        phase_core = dict(bootstrap_prepublication_phase)
        phase_core.pop("receipt_sha256")
        attestation_core = dict(phase_core["attestation"])
        attestation_core.pop("receipt_sha256")
        attestation_core["site_imported"] = True
        phase_core["attestation"] = _seal(attestation_core)
        phase_core["attestation_receipt_sha256"] = phase_core["attestation"][
            "receipt_sha256"
        ]
        recovery_core["bootstrap_prepublication_phase"] = _seal(phase_core)
    elif mutation == "disclosure_claim_stripped":
        recovery_core["write_confinement_claim"] = "Landlock confined"
    elif mutation == "disclosure_limitations_stripped":
        recovery_core["landlock_limitations"] = dict(verifier.LANDLOCK_LIMITATIONS)
        recovery_core["landlock_limitations"].pop(
            "preopened_file_descriptors_unmediated"
        )
    elif mutation == "disclosure_provider_overclaim":
        recovery_core["provider_review_approval_claimed"] = True
    elif mutation == "recovery_final_bytes":
        recovery_core["provider_reviewed_final_bytes_unchanged"] = False
    recovery = _seal(recovery_core)
    original_campaign = {
        "campaign_started_at_unix": verifier.ORIGINAL_CAMPAIGN_STARTED_AT_UNIX,
        "campaign_deadline_at_unix": verifier.ORIGINAL_CAMPAIGN_DEADLINE_AT_UNIX,
        "hourly_price_usd": verifier.ORIGINAL_CAMPAIGN_HOURLY_PRICE_USD,
    }
    if mutation == "original_campaign":
        original_campaign = {
            "campaign_started_at_unix": 777.0,
            "campaign_deadline_at_unix": 888.0,
            "hourly_price_usd": 9.0,
        }
    recovery_campaign = {
        "started_at_unix": 1000.0,
        "deadline_at_unix": 4600.0,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 6.0,
    }
    audit = _seal(
        {
            "schema_version": 1,
            "status": "pass",
            "study_id": verifier.STUDY_ID,
            "protocol_version": verifier.PROTOCOL_VERSION,
            "run_id": verifier.RUN_ID,
            "raw_run_receipt_sha256": authorization["raw_run_receipt_sha256"],
            "campaign_started_at_unix": original_campaign["campaign_started_at_unix"],
            "campaign_deadline_at_unix": original_campaign["campaign_deadline_at_unix"],
            "hourly_price_usd": original_campaign["hourly_price_usd"],
            "original_execution_campaign": original_campaign,
            "recovery_execution_campaign": recovery_campaign,
            "analysis_data_inputs": [],
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "recovery_audit": recovery,
        }
    )
    audit_path = root / verifier.AUDIT_RELATIVE
    _write(audit_path, audit)
    summary_recovery = dict(recovery)
    if mutation == "summary_recovery":
        summary_recovery = dict(recovery)
        summary_recovery["fresh_model_execution_performed"] = True
    summary = _seal(
        {
            "schema_version": 1,
            "status": "pass",
            "study_id": verifier.STUDY_ID,
            "protocol_version": verifier.PROTOCOL_VERSION,
            "run_id": verifier.RUN_ID,
            "raw_run_receipt_sha256": authorization["raw_run_receipt_sha256"],
            "audit_receipt_sha256": audit["receipt_sha256"],
            "later_actual_state_collection_eligibility": "pass",
            "analysis_data_inputs": [],
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "recovery_execution_campaign": recovery_campaign,
            "recovery_audit": summary_recovery,
        }
    )
    summary_path = root / verifier.SUMMARY_RELATIVE
    _write(summary_path, summary)
    publication = _seal(
        {
            "schema_version": 1,
            "status": "complete",
            "study_id": verifier.STUDY_ID,
            "protocol_version": verifier.PROTOCOL_VERSION,
            "audit_receipt_sha256": audit["receipt_sha256"],
            "summary_receipt_sha256": summary["receipt_sha256"],
            "audit_file_sha256": (
                "f" * 64
                if mutation == "publication_physical_hash"
                else verifier.sha256_file(audit_path)
            ),
            "summary_file_sha256": verifier.sha256_file(summary_path),
            "publication_completed_at_unix": 3000.0,
            "recovery_deadline_at_unix": 4600.0,
        }
    )
    _write(root / verifier.PUBLICATION_RELATIVE, publication)

    if mutation == "failure_present":
        _write(root / verifier.FAILURE_RELATIVE, _seal({"status": "failed"}))
    elif mutation == "compact_extra":
        (root / verifier.COMPACT_RELATIVE / "EXTRA.txt").write_text("extra")
    elif mutation == "hardlink":
        os.link(
            root / verifier.ATTEMPT_MARKER_RELATIVE,
            root / "output/ATTEMPT_STARTED_COPY.json",
        )
    elif mutation == "symlink":
        (root / "output/unsafe-link").symlink_to("ATTEMPT_STARTED.json")
    return root


def test_valid_bundle_and_exclusive_external_cli_receipt(tmp_path: Path) -> None:
    root = _build_bundle(tmp_path)
    before = _snapshot(root)
    receipt = verifier.verify_bundle(root)
    assert receipt["status"] == "pass_recovery_bundle_verified_offline"
    assert receipt["verified_file_count"] == 14
    assert receipt["receipt_sha256"] == verifier.canonical_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )

    output = tmp_path / "VERIFICATION.json"
    assert verifier.main(["--bundle-root", str(root), "--output", str(output)]) == 0
    assert json.loads(output.read_text()) == receipt
    assert _snapshot(root) == before
    with pytest.raises(
        verifier.RecoveryBundleVerificationError, match="not fresh/safe"
    ):
        verifier.main(["--bundle-root", str(root), "--output", str(output)])


def test_preflight_child_argv_is_frozen_and_device_sorted() -> None:
    python = "/active/.venv/bin/python"
    active = "/active"
    paths = {
        "preflight_landlock": "/attempt/preflight/output/LANDLOCK_ENFORCEMENT.json",
        "preflight_output_root": "/attempt/preflight/output",
        "preflight_canary_protected_root": "/attempt/preflight/canary/protected",
        "preflight_canary_output_root": "/attempt/preflight/canary/output",
        "preflight_probe": "/attempt/preflight/output/LANDLOCK_CUDA_PREFLIGHT.json",
        "roots_manifest": "/attempt/bootstrap/APPROVED_IMPORT_ROOTS.json",
    }
    roots_sha256 = "a" * 64
    assert verifier._expected_preflight_argv(  # noqa: SLF001
        python,
        active,
        paths,
        roots_sha256,
        ["/dev/nvidiactl", "/dev/nvidia0"],
    ) == [
        python,
        "-B",
        "-E",
        "-s",
        "-S",
        f"{active}/{verifier.BOOTSTRAP_RELATIVE_PATH}",
        "--mode",
        "preflight-child",
        "--active-root",
        active,
        "--roots-manifest",
        paths["roots_manifest"],
        "--roots-manifest-sha256",
        roots_sha256,
        "--",
        "--python-executable",
        python,
        "--active-root",
        active,
        "--roots-manifest",
        paths["roots_manifest"],
        "--roots-manifest-sha256",
        roots_sha256,
        "--landlock-receipt",
        paths["preflight_landlock"],
        "--output-root",
        paths["preflight_output_root"],
        "--canary-protected-root",
        paths["preflight_canary_protected_root"],
        "--canary-output-root",
        paths["preflight_canary_output_root"],
        "--closure-scope",
        "final_recovery",
        "--device-file",
        "/dev/nvidia0",
        "--device-file",
        "/dev/nvidiactl",
        "--output",
        paths["preflight_probe"],
    ]


def test_linux_device_identity_is_decoded_independently_of_host_abi() -> None:
    assert verifier._linux_device_major(49920) == 195  # noqa: SLF001
    assert verifier._linux_device_minor(49920) == 0  # noqa: SLF001
    assert verifier._validate_device_rules([_device()], "devices") == [  # noqa: SLF001
        _device()
    ]
    invalid = _device()
    invalid["major"] = 194
    with pytest.raises(
        verifier.RecoveryBundleVerificationError, match="identity/access"
    ):
        verifier._validate_device_rules([invalid], "devices")  # noqa: SLF001


def test_superseded_host_contract_and_confined_evidence_argv_are_frozen() -> None:
    assert verifier.SUPERSEDED_RECOVERY_HOST == {
        "status": "validated_superseded_preclaim_recovery_host",
        "pod_id": "faz2t3bcrdwymn",
        "attempt_id": "calv2-r3-audit-recovery-e0dd9a6-20260715T015420Z",
        "audit_execute_invoked": False,
        "attempt_marker_present": False,
        "runtime_block_receipt_sha256": (
            "bf8ddbb31b3ddab99c2126d1100691f8d0878c1a0d1d4a091776e5d3f2bc207d"
        ),
        "termination_audit_receipt_sha256": (
            "a7fa432b64f594926fac22070a59c5081e68e8a4cc230ae4a2ffc0032dd30300"
        ),
        "frozen_termination_receipt_sha256": (
            "0bc9fd91dc816e70e95809da50b667cb67bc6b0674d7b4c84415b3287bbebbd0"
        ),
        "postdelete_inventory_receipt_sha256": (
            "7d0c31b4830fdedad2e985e28168418a86483241ced2bd415d45ff12eecf1d06"
        ),
    }
    attempt_id = "calv2-r3-audit-recovery-abcdef0-20260715T010203Z"
    paths = verifier._expected_paths(attempt_id)  # noqa: SLF001
    argv = verifier._expected_confined_argv(  # noqa: SLF001
        "/active/python",
        "/active",
        attempt_id,
        paths,
        "a" * 64,
        ["/dev/nvidia0"],
    )
    for name in verifier.SUPERSEDED_EXTERNAL_KEYS:
        flag = f"--{name.replace('_', '-')}"
        index = argv.index(flag)
        assert argv[index + 1] == paths[name]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("policy_mask", "identity/ABI"),
        ("device_mismatch", "inventories"),
        ("cuda_forward", "zero-forward"),
        ("cuda_active_root", "package/CUDA/zero-forward"),
        ("recovery_closure", "package/CUDA/zero-forward"),
        ("preflight_argv", "preflight Landlock child command differs"),
        ("bootstrap_preflight_attestation", "confined bootstrap attestation differs"),
        ("bootstrap_manifest_inventory", "bootstrap_manifest semantic links differ"),
        ("environment_lexical_escape", "canonical single-leading-slash"),
        ("absent_environment", "absent environment inventory"),
        ("protected_check_preflight", "protected_checks differs"),
        ("protected_check_execution", "protected_checks differs"),
        ("closure_order", "not sorted and unique"),
        ("auth_path_hash", "recovery path hash differs"),
        ("auth_plan_hash", "identity/science boundary differs"),
        ("auth_provenance_semantic", "historical provenance authority differs"),
        ("auth_external_missing", "external_files keys differ"),
        ("auth_git_mismatch", "git head differs"),
        ("target_designated_skip", "target environment differs"),
        ("target_source_inventory", "review semantics differ"),
        ("target_same_recovery_pod", "target environment differs"),
        ("target_observed_head", "target environment differs"),
        ("qualification_ownership_clock", "ownership resource binding differs"),
        ("qualification_closure", "qualification CUDA closure"),
        ("qualification_bootstrap", "qualification bootstrap phase differs"),
        ("qualification_child_argv", "qualification evidence path/scope differs"),
        (
            "qualification_origin_ownership_inside_output",
            "qualification evidence path/scope differs",
        ),
        (
            "qualification_origin_landlock_outside_output",
            "qualification evidence path/scope differs",
        ),
        ("qualification_device", "child/device binding differs"),
        ("auth_review_overclaim", "review semantics differ"),
        ("auth_review_final_bytes", "review semantics differ"),
        ("auth_review_call_count", "review semantics differ"),
        ("auth_review_git_head", "review semantics differ"),
        ("auth_review_terminal", "review semantics differ"),
        ("auth_review_b17_omitted", "review semantics differ"),
        ("auth_review_b20_omitted", "review semantics differ"),
        ("auth_review_historical_b17", "review semantics differ"),
        ("auth_review_historical_v4_blocker", "review semantics differ"),
        ("auth_review_historical_pricing", "review semantics differ"),
        ("auth_review_reserved_finding_id", "review semantics differ"),
        ("auth_review_new_blocker", "review semantics differ"),
        ("auth_review_snapshot_receipt", "reviewed snapshot binding differs"),
        ("auth_review_cost_over", "review semantics differ"),
        (
            "historical_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v2_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v3_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v4_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v5_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v6_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "historical_v7_review_physical",
            "immutable historical review physical evidence differs",
        ),
        (
            "b20_incident_physical",
            "immutable historical review physical evidence differs",
        ),
        ("reviewed_snapshot_mismatch", "reviewed snapshot binding differs"),
        ("auth_clock", "ownership-bound clocks differ"),
        ("superseded_path", "authorization execution paths differ"),
        ("superseded_block", "authorization identity/science boundary differs"),
        ("superseded_file_record", "must be lowercase SHA-256"),
        ("raw_directory_hash", "raw pre/post file or directory hashes differ"),
        ("raw_directory_format", "must be lowercase SHA-256"),
        ("provenance_directory_count", "directory_count"),
        ("raw_schema_extra", "keys differ"),
        ("isolation_directory_hash", "executable isolation differs"),
        ("recovery_closure_link", "closure hash links differ"),
        ("scientific_equivalence_link", "closure hash links differ"),
        ("bootstrap_recovery_phase", "confined bootstrap attestation differs"),
        ("disclosure_claim_stripped", "metadata cross-links differ"),
        ("disclosure_limitations_stripped", "metadata cross-links differ"),
        ("disclosure_provider_overclaim", "metadata cross-links differ"),
        ("recovery_final_bytes", "metadata cross-links differ"),
        ("descriptor_output_writable", "writable regular/directory"),
        ("descriptor_unenumerated_nvidia", "forbidden GPU FD"),
        ("descriptor_writable_block", "writable device FD"),
        ("descriptor_io_uring", "io_uring"),
        ("mapping_schema", "mapping_audit.*keys differ"),
        ("baseline_missing", "canary checks differ"),
        ("pid_crosslink", "marker cross-links"),
        ("j_inventory", "J inventory"),
        ("nested_receipt", "preflight_landlock_receipt link"),
        ("summary_recovery", "audit/summary semantic links"),
        ("original_campaign", "audit/summary semantic links"),
        ("publication_physical_hash", "publication receipt links"),
        ("failure_present", "FAILURE.json"),
        ("compact_extra", "compact file set differs"),
        ("hardlink", "hard-linked"),
        ("symlink", "symlink"),
    ],
)
def test_tampering_fails_closed(tmp_path: Path, mutation: str, message: str) -> None:
    root = _build_bundle(tmp_path, mutation=mutation)
    with pytest.raises(verifier.RecoveryBundleVerificationError, match=message):
        verifier.verify_bundle(root)


def test_completed_review_cost_ceiling_accepts_exact_boundary(tmp_path: Path) -> None:
    root = _build_bundle(tmp_path, mutation="auth_review_cost_boundary")
    assert verifier.verify_bundle(root)["status"] == (
        "pass_recovery_bundle_verified_offline"
    )


def test_verification_receipt_cannot_be_written_inside_bundle(tmp_path: Path) -> None:
    root = _build_bundle(tmp_path)
    receipt = verifier.verify_bundle(root)
    with pytest.raises(verifier.RecoveryBundleVerificationError, match="outside"):
        verifier.write_verification_receipt(
            root / "output/VERIFICATION.json", receipt, bundle_root=root
        )
