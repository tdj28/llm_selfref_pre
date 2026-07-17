from __future__ import annotations

import errno
import hashlib
import json
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pytest

from experiments.consciousness_sae_signed_dose_scan import protocol
from experiments.consciousness_sae_signed_dose_scan import (
    recovery_host_qualification as qualification,
)
from experiments.consciousness_sae_signed_dose_scan import (
    verify_recovery_host_qualification as verifier,
)


ZERO_COUNTS = dict(qualification.EXPECTED_ZERO_FORWARD_COUNTS)


def _write(path: Path, payload: bytes = b"fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _iso(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _checkpoint_evidence(checkpoint: Path) -> dict[str, Any]:
    core = {
        "status": "pass_exact_pinned_superset_and_required_filter",
        "checkpoint_path": checkpoint.as_posix(),
        "checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
        "checkpoint_revision": protocol.J_LENS_SPEC["revision"],
        "checkpoint_n_prompts": int(
            protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
        ),
        "checkpoint_d_model": protocol.WIDTH,
        "available_layers": list(range(79)),
        "required_layers": list(range(45, 79)),
        "unused_extra_layers": list(range(45)),
        "filtered_layers": list(range(45, 79)),
        "available_map_count": 79,
        "required_map_count": 34,
        "required_map_shape": [protocol.WIDTH, protocol.WIDTH],
        "required_map_dtype": "torch.bfloat16",
        "selected_map_object_contract": (
            "same_checkpoint_objects_no_numeric_transform"
        ),
        "missing_required_layer_negative": (
            "pass_rejected_missing_required_layer_45"
        ),
        "loader_watchdog_check_count": 2,
        "frozen_audit_record": {
            "sha256": protocol.J_LENS_SPEC["sha256"],
            "map_count": 34,
            "revision": protocol.J_LENS_SPEC["revision"],
        },
    }
    return {**core, "receipt_sha256": qualification.canonical_sha256(core)}


def _cuda_evidence() -> dict[str, Any]:
    return {
        "status": "pass_frozen_startup_and_real_bf16_cublas",
        "configured_via": (
            "experiments.consciousness_sae_signed_dose_scan.audit."
            "_configure_artifact_device"
        ),
        "device": "cuda:0",
        "device_count": 1,
        "device_name": "NVIDIA B200",
        "device_total_memory_bytes": 180 * 1024**3,
        "cublas_workspace_config": ":4096:8",
        "deterministic_algorithms_enabled": True,
        "matmul_allow_tf32": False,
        "cudnn_allow_tf32": False,
        "flash_sdp_enabled": False,
        "mem_efficient_sdp_enabled": False,
        "math_sdp_enabled": True,
        "probe_operation": "torch.matmul",
        "probe_shape": [16, 16],
        "probe_dtype": "torch.bfloat16",
        "probe_finite": True,
        "probe_exact_identity_product": True,
        "torch_module_calls": 0,
        "transformers_model_load_calls": 0,
        "direct_forward_attribute_access": 0,
        "model_forward_count": 0,
        "target_prompt_render_count": 0,
    }


@contextmanager
def _zero_guard() -> Iterator[dict[str, int]]:
    yield dict(ZERO_COUNTS)


def test_required_map_filter_preserves_objects_and_rejects_missing() -> None:
    maps = {layer: object() for layer in range(79)}
    selected = qualification.select_required_maps(maps)
    assert tuple(selected) == tuple(range(45, 79))
    assert all(selected[layer] is maps[layer] for layer in selected)
    del maps[45]
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="missing required layers",
    ):
        qualification.select_required_maps(maps)


def test_independent_watchdog_enforces_1800_seconds_and_three_dollars() -> None:
    started = 2_000_000_000.0
    watchdog = qualification.QualificationWatchdog(
        started_at_unix=started,
        hourly_price_usd=6.0,
        clock=lambda: started + 1799,
    )
    assert watchdog.check() == started + 1799
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="time/cost authority differs",
    ):
        qualification.QualificationWatchdog(
            started_at_unix=started,
            hourly_price_usd=6.01,
            clock=lambda: started,
        )
    expired = qualification.QualificationWatchdog(
        started_at_unix=started,
        hourly_price_usd=5.0,
        clock=lambda: started + 1800,
    )
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="watchdog expired",
    ):
        expired.check()


def test_production_mode_rejects_test_only_bypasses(tmp_path: Path) -> None:
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="test-only qualification override",
    ):
        qualification.qualify_host(
            packet_path=tmp_path / "packet",
            plan_audit_path=tmp_path / "plan",
            ownership_path=tmp_path / "ownership",
            guest_path=tmp_path / "guest",
            cache_path=tmp_path / "cache",
            j_lens_path=tmp_path / "J.pt",
            hourly_price_usd=5.0,
            output_dir=tmp_path / "attempt",
            install_raw_audit_hook=False,
        )


def test_raw_guard_rejects_direct_and_parent_symlink_aliases(tmp_path: Path) -> None:
    raw_root = tmp_path / "study" / "v1" / "raw"
    secret = _write(raw_root / "RUN_COMPLETE.json")
    guard = qualification.RawPathAuditGuard(raw_root)

    with pytest.raises(qualification.RecoveryHostQualificationError):
        guard("open", (secret.as_posix(), "r", 0))

    alias = tmp_path / "alias"
    alias.symlink_to(raw_root.parent, target_is_directory=True)
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="symlink component",
    ):
        guard("open", ((alias / "raw" / secret.name).as_posix(), "r", 0))
    assert guard.raw_forbidden_attempt_count == 1
    assert guard.path_guard_rejected_attempt_count == 1
    assert guard.allowed_outside_raw_enotdir_probe_count == 0
    assert [row["classification"] for row in guard.path_diagnostics] == [
        "raw_forbidden",
        "path_guard_rejected",
    ]


def test_raw_guard_allows_linux_egg_info_child_probe_below_regular_file(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "study" / "v1" / "raw"
    raw_root.mkdir(parents=True)
    egg_info = _write(
        tmp_path / "site-packages" / "blinker-1.4.egg-info",
        b"Metadata-Version: 1.0\n",
    )
    probed = egg_info / "entry_points.txt"
    guard = qualification.RawPathAuditGuard(raw_root)

    with pytest.raises(OSError) as observed:
        probed.open("rb")
    assert observed.value.errno == errno.ENOTDIR == 20
    resolved, tolerated_errno = qualification._strict_path_resolution(  # noqa: SLF001
        probed, "Linux import probe", must_exist=False
    )
    assert resolved == probed
    assert tolerated_errno == errno.ENOTDIR
    guard("open", (probed.as_posix(), "r", 0))
    assert guard.open_event_count == 1
    assert guard.raw_forbidden_attempt_count == 0
    assert guard.path_guard_rejected_attempt_count == 0
    assert guard.allowed_outside_raw_enotdir_probe_count == 1
    assert guard.path_diagnostics == [
        {
            "classification": "allowed_outside_raw_enotdir",
            "errno": 20,
            "path_sha256": hashlib.sha256(
                probed.as_posix().encode("utf-8")
            ).hexdigest(),
        }
    ]


def test_raw_guard_still_rejects_enotdir_probe_lexically_inside_raw(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "study" / "v1" / "raw"
    egg_info = _write(
        raw_root / "blinker-1.4.egg-info",
        b"Metadata-Version: 1.0\n",
    )
    guard = qualification.RawPathAuditGuard(raw_root)

    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="raw access is forbidden",
    ):
        guard("open", ((egg_info / "entry_points.txt").as_posix(), "r", 0))
    assert guard.raw_forbidden_attempt_count == 1
    assert guard.path_guard_rejected_attempt_count == 0
    assert guard.allowed_outside_raw_enotdir_probe_count == 0


def test_enotdir_probe_does_not_weaken_strict_existing_or_symlink_checks(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    egg_info = _write(tmp_path / "real" / "blinker-1.4.egg-info")
    probed = egg_info / "entry_points.txt"
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="missing",
    ):
        qualification._strict_path(  # noqa: SLF001
            probed, "strict input", must_exist=True
        )

    alias = tmp_path / "alias"
    alias.symlink_to(egg_info)
    guard = qualification.RawPathAuditGuard(raw_root)
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="symlink component",
    ):
        guard("open", ((alias / "entry_points.txt").as_posix(), "r", 0))
    assert guard.raw_forbidden_attempt_count == 0
    assert guard.path_guard_rejected_attempt_count == 1
    assert guard.allowed_outside_raw_enotdir_probe_count == 0


def test_strict_input_path_rejects_parent_symlink(tmp_path: Path) -> None:
    real = tmp_path / "real"
    fixture = _write(real / "packet.json")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="symlink component",
    ):
        qualification._input_record(alias / fixture.name, raw_root)  # noqa: SLF001


def test_zero_forward_guard_blocks_direct_forward_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Module:
        def forward(self, value: object) -> object:
            return value

    fake_torch = types.SimpleNamespace(nn=types.SimpleNamespace(Module=Module))

    @contextmanager
    def inherited_guard() -> Iterator[dict[str, int]]:
        yield {
            "torch_module_calls": 0,
            "transformers_model_load_calls": 0,
            "direct_forward_attribute_access": 0,
            "model_construction_calls": 0,
            "model_state_load_calls": 0,
        }

    model = Module()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        qualification.audit_recovery, "zero_forward_guard", inherited_guard
    )
    with qualification.qualification_zero_forward_guard() as counts:
        with pytest.raises(
            qualification.RecoveryHostQualificationError,
            match="direct torch module forward access",
        ):
            model.forward(object())
    assert counts["direct_forward_attribute_access"] == 1


def test_checkpoint_inspection_exercises_missing_negative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _write(tmp_path / "J.pt")
    fake_dtype = object()

    class Tensor:
        shape = (protocol.WIDTH, protocol.WIDTH)
        dtype = fake_dtype

    filtered = {layer: Tensor() for layer in range(45, 79)}
    audit_record = {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": 34,
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    inventory = {
        "available_layers": list(range(79)),
        "required_layers": list(range(45, 79)),
        "unused_extra_layers": list(range(45)),
        "checkpoint_n_prompts": int(
            protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
        ),
        "checkpoint_d_model": protocol.WIDTH,
    }
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(bfloat16=fake_dtype))
    monkeypatch.setattr(
        qualification.audit_recovery,
        "load_j_checkpoint_superset",
        lambda *_args: (checkpoint, filtered, audit_record, inventory),
    )
    evidence = qualification.inspect_pinned_checkpoint(checkpoint)
    assert evidence["available_layers"] == list(range(79))
    assert evidence["filtered_layers"] == list(range(45, 79))
    assert evidence["missing_required_layer_negative"] == (
        "pass_rejected_missing_required_layer_45"
    )


def test_frozen_cuda_probe_calls_exact_entrypoint_and_raw_matmul(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Tensor:
        def reshape(self, *_shape: int) -> Tensor:
            return self

    class Scalar:
        def all(self) -> Scalar:
            return self

        def item(self) -> bool:
            return True

    cuda = types.SimpleNamespace(
        get_device_properties=lambda _device: types.SimpleNamespace(
            name="NVIDIA B200", total_memory=180 * 1024**3
        ),
        device_count=lambda: 1,
        synchronize=lambda _device: calls.append("synchronize"),
    )
    backends = types.SimpleNamespace(
        cuda=types.SimpleNamespace(
            matmul=types.SimpleNamespace(allow_tf32=False),
            flash_sdp_enabled=lambda: False,
            mem_efficient_sdp_enabled=lambda: False,
            math_sdp_enabled=lambda: True,
        ),
        cudnn=types.SimpleNamespace(allow_tf32=False),
    )
    fake_torch = types.SimpleNamespace(
        bfloat16="torch.bfloat16",
        cuda=cuda,
        backends=backends,
        arange=lambda *_args, **_kwargs: Tensor(),
        eye=lambda *_args, **_kwargs: Tensor(),
        matmul=lambda left, _right: calls.append("matmul") or left,
        isfinite=lambda _value: Scalar(),
        equal=lambda _left, _right: True,
        are_deterministic_algorithms_enabled=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        qualification.frozen_audit,
        "_configure_artifact_device",
        lambda device: calls.append(f"configure:{device}") or device,
    )
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    evidence = qualification._exercise_frozen_cuda_startup()  # noqa: SLF001
    assert calls == ["configure:cuda:0", "matmul", "synchronize"]
    assert evidence["probe_operation"] == "torch.matmul"


def _synthetic_inputs(tmp_path: Path, started: float) -> dict[str, Any]:
    raw_root = tmp_path / "mounted" / "study" / "v1" / "raw"
    raw_root.mkdir(parents=True)
    cache_root = tmp_path / "cache"
    checkpoint = _write(cache_root / "jlens" / "J.pt")
    paths = {
        "packet": _write(tmp_path / "packet.json"),
        "plan": _write(tmp_path / "plan.json"),
        "ownership": _write(tmp_path / "ownership.json"),
        "guest": _write(tmp_path / "guest.json"),
        "cache": _write(tmp_path / "cache.json"),
        "checkpoint": checkpoint,
    }
    ownership = {
        "pod_id": "qualification-pod",
        "network_volume_id": protocol.NETWORK_VOLUME_ID,
        "data_center_id": protocol.DATA_CENTER_ID,
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "precreate_unrelated_pod_count": 0,
        "precreate_unrelated_inventory_sha256": qualification.canonical_sha256([]),
        "created_at": _iso(started - 60),
        "terminate_after": _iso(started + 3600),
        "receipt_sha256": "1" * 64,
    }
    guest = {
        "attested_at_utc": _iso(started - 30),
        "receipt_sha256": "2" * 64,
    }
    cache = {
        "cache_root": cache_root.as_posix(),
        "components": [
            {
                "component": "j_lens",
                "relative_path": "jlens/J.pt",
                "sha256": protocol.J_LENS_SPEC["sha256"],
                "revision": protocol.J_LENS_SPEC["revision"],
                "verified": True,
            }
        ],
        "receipt_sha256": "3" * 64,
    }
    hashes = {
        name: hashlib.sha256(paths[name].read_bytes()).hexdigest()
        for name in ("ownership", "guest", "cache")
    }
    chain = verifier._expected_chain_record(  # noqa: SLF001
        ownership,
        guest,
        cache,
        hashes,
        ownership_path=paths["ownership"],
        guest_path=paths["guest"],
        cache_path=paths["cache"],
    )
    equivalence = {
        "status": "pass_outcome_blind_recovery_equivalence_verified",
        "packet_sha256": "4" * 64,
        "code_freeze_commit": "5" * 40,
        "recovery_closure_inventory_sha256": "6" * 64,
    }
    return {
        "raw_root": raw_root,
        "paths": paths,
        "ownership": ownership,
        "guest": guest,
        "cache": cache,
        "hashes": hashes,
        "chain": chain,
        "equivalence": equivalence,
    }


def test_one_shot_receipt_and_independent_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = 2_000_000_000.0
    fixture = _synthetic_inputs(tmp_path, started)
    paths = fixture["paths"]
    attempt = tmp_path / "attempt"
    receipt = qualification.qualify_host(
        packet_path=paths["packet"],
        plan_audit_path=paths["plan"],
        ownership_path=paths["ownership"],
        guest_path=paths["guest"],
        cache_path=paths["cache"],
        j_lens_path=paths["checkpoint"],
        output_dir=attempt,
        now_unix=started,
        hourly_price_usd=5.0,
        enforce_git=False,
        install_raw_audit_hook=False,
        equivalence_verifier=lambda *_args, **_kwargs: fixture["equivalence"],
        chain_validator=lambda *_args, **_kwargs: fixture["chain"],
        checkpoint_inspector=lambda path: _checkpoint_evidence(path),
        cuda_probe=_cuda_evidence,
        forward_guard_factory=_zero_guard,
        forbidden_raw_root=fixture["raw_root"],
    )
    assert receipt["status"] == (
        "pass_one_shot_zero_forward_target_host_qualification"
    )
    assert set(path.name for path in attempt.iterdir()) == {
        qualification.ATTEMPT_MARKER_NAME,
        qualification.SUCCESS_NAME,
    }
    with pytest.raises(FileExistsError):
        qualification.qualify_host(
            packet_path=paths["packet"],
            plan_audit_path=paths["plan"],
            ownership_path=paths["ownership"],
            guest_path=paths["guest"],
            cache_path=paths["cache"],
            j_lens_path=paths["checkpoint"],
            output_dir=attempt,
            now_unix=started,
            hourly_price_usd=5.0,
            enforce_git=False,
            install_raw_audit_hook=False,
            forbidden_raw_root=fixture["raw_root"],
        )

    monkeypatch.setattr(
        verifier.verify_recovery_equivalence,
        "verify_packet",
        lambda *_args, **_kwargs: fixture["equivalence"],
    )
    monkeypatch.setattr(
        verifier,
        "_validated_receipt_chain",
        lambda *_args: (
            fixture["ownership"],
            fixture["guest"],
            fixture["cache"],
            fixture["hashes"],
        ),
    )
    monkeypatch.setattr(
        verifier,
        "_verify_checkpoint",
        lambda value, _path: value["receipt_sha256"],
    )
    verified = verifier.verify_qualification(
        receipt_path=attempt / qualification.SUCCESS_NAME,
        marker_path=attempt / qualification.ATTEMPT_MARKER_NAME,
        packet_path=paths["packet"],
        plan_audit_path=paths["plan"],
        ownership_path=paths["ownership"],
        guest_path=paths["guest"],
        cache_path=paths["cache"],
        j_lens_path=paths["checkpoint"],
        enforce_git=False,
        forbidden_raw_root=fixture["raw_root"],
    )
    assert verified["status"] == (
        "pass_independent_target_host_qualification_verified"
    )
    assert verified["attempt_number"] == 1
    assert verified["global_qualification_ordinal"] == 2
    assert verified["successor_qualification_attempt"] == 1
    assert verified["model_forward_count"] == 0

    success_path = attempt / qualification.SUCCESS_NAME
    tampered = json.loads(success_path.read_text(encoding="utf-8"))
    tampered["qualification_watchdog"]["qualification_deadline_at_unix"] += 1
    tampered_core = dict(tampered)
    tampered_core.pop("receipt_sha256")
    tampered["receipt_sha256"] = qualification.canonical_sha256(tampered_core)
    success_path.write_bytes(qualification.canonical_json_bytes(tampered) + b"\n")
    with pytest.raises(
        verifier.RecoveryHostQualificationVerificationError,
        match="qualification receipt differs",
    ):
        verifier.verify_qualification(
            receipt_path=success_path,
            marker_path=attempt / qualification.ATTEMPT_MARKER_NAME,
            packet_path=paths["packet"],
            plan_audit_path=paths["plan"],
            ownership_path=paths["ownership"],
            guest_path=paths["guest"],
            cache_path=paths["cache"],
            j_lens_path=paths["checkpoint"],
            enforce_git=False,
            forbidden_raw_root=fixture["raw_root"],
        )


def test_failed_attempt_is_consumed(tmp_path: Path) -> None:
    started = 2_000_000_000.0
    fixture = _synthetic_inputs(tmp_path, started)
    paths = fixture["paths"]
    attempt = tmp_path / "failed-attempt"

    def fail(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("synthetic qualification failure")

    with pytest.raises(RuntimeError, match="synthetic qualification failure"):
        qualification.qualify_host(
            packet_path=paths["packet"],
            plan_audit_path=paths["plan"],
            ownership_path=paths["ownership"],
            guest_path=paths["guest"],
            cache_path=paths["cache"],
            j_lens_path=paths["checkpoint"],
            output_dir=attempt,
            now_unix=started,
            hourly_price_usd=5.0,
            enforce_git=False,
            install_raw_audit_hook=False,
            equivalence_verifier=fail,
            forward_guard_factory=_zero_guard,
            forbidden_raw_root=fixture["raw_root"],
        )
    assert set(path.name for path in attempt.iterdir()) == {
        qualification.ATTEMPT_MARKER_NAME,
        qualification.FAILURE_NAME,
    }
    failed = json.loads(
        (attempt / qualification.FAILURE_NAME).read_text(encoding="utf-8")
    )
    assert failed["global_qualification_ordinal"] == 2
    assert failed["successor_qualification_attempt"] == 1
    assert failed["raw_forbidden_attempt_count"] == 0
    assert failed["path_guard_rejected_attempt_count"] == 0
    assert failed["allowed_outside_raw_enotdir_probe_count"] == 0
    assert failed["zero_forward_guard_observation_status"] == "observed"
    assert failed["zero_forward_guard"] == ZERO_COUNTS


def test_symlink_input_is_rejected_after_attempt_marker(tmp_path: Path) -> None:
    started = 2_000_000_000.0
    fixture = _synthetic_inputs(tmp_path, started)
    paths = fixture["paths"]
    alias = tmp_path / "packet-alias.json"
    alias.symlink_to(paths["packet"])
    attempt = tmp_path / "symlink-attempt"

    with pytest.raises(
        qualification.RecoveryHostQualificationError,
        match="symlink component",
    ):
        qualification.qualify_host(
            packet_path=alias,
            plan_audit_path=paths["plan"],
            ownership_path=paths["ownership"],
            guest_path=paths["guest"],
            cache_path=paths["cache"],
            j_lens_path=paths["checkpoint"],
            output_dir=attempt,
            now_unix=started,
            hourly_price_usd=5.0,
            enforce_git=False,
            install_raw_audit_hook=False,
            forward_guard_factory=_zero_guard,
            forbidden_raw_root=fixture["raw_root"],
        )
    assert set(path.name for path in attempt.iterdir()) == {
        qualification.ATTEMPT_MARKER_NAME,
        qualification.FAILURE_NAME,
    }
