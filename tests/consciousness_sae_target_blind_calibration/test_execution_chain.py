from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from experiments.consciousness_sae_realization_validation import (
    protocol as base_protocol,
    runtime,
)
from experiments.consciousness_sae_target_blind_calibration import (
    authorize,
    guest_launcher,
    orientation,
    protocol,
    runner,
)
from tests.consciousness_sae_realization_validation.test_guest_launcher import (
    _ownership_receipt,
)


def test_watchdog_reserves_the_frozen_audit_window() -> None:
    now = [1_000.0]
    campaign_seconds = protocol.RESOURCE_LIMITS["max_walltime_seconds"]
    runner_seconds = runner._runner_watchdog_seconds()
    watchdog = runner._Watchdog(
        started=1_000.0,
        deadline=1_000.0 + campaign_seconds,
        hourly_price=6.0,
        clock=lambda: now[0],
    )
    assert watchdog.runner_deadline == 1_000.0 + runner_seconds
    assert campaign_seconds - runner_seconds == protocol.AUDIT_RESERVE_SECONDS
    watchdog.check()
    now[0] = 1_000.0 + runner_seconds - 0.001
    watchdog.check()
    now[0] = 1_000.0 + runner_seconds
    with pytest.raises(runner.CalibrationExecutionError, match="watchdog budget"):
        watchdog.check()
    with pytest.raises(runner.CalibrationExecutionError, match="authority differs"):
        runner._Watchdog(
            started=1_000.0,
            deadline=1_000.0 + campaign_seconds,
            hourly_price=5.89,
        )
    assert authorize.CONSERVATIVE_RATE_USD_PER_HOUR == 6.0


def test_runtime_contract_receipts_bind_the_frozen_protocol() -> None:
    assert runner._contract_hashes() == {
        "intervention_state_contract_sha256": protocol.canonical_sha256(
            protocol.INTERVENTION_STATE_CONTRACT
        ),
        "j_state_contract_sha256": protocol.canonical_sha256(protocol.J_STATE_CONTRACT),
        "fixed_panel_estimand_sha256": protocol.canonical_sha256(
            protocol.FIXED_PANEL_ESTIMAND
        ),
    }


def test_runtime_token_telemetry_binds_the_cached_prefix_boundary() -> None:
    receipts = []
    for index, prompt_id in enumerate(protocol.PROMPT_IDS):
        token_ids = [100 + index, 200 + index, 300 + index]
        receipts.append(
            {
                "prompt_id": prompt_id,
                "token_ids": token_ids,
                "token_count": 3,
                "prefix_token_count": 2,
                "edited_token_index": 2,
                "continuation_token_id": token_ids[-1],
                "continuation_forward_sequence_length": 1,
            }
        )
    telemetry = runner._execution_token_telemetry(receipts)
    assert telemetry == {
        "forward_inventory": protocol.FORWARD_INVENTORY,
        "total_rendered_token_count": 3 * len(protocol.PROMPT_IDS),
        "prefix_uncached_token_count": 2 * len(protocol.PROMPT_IDS),
        "continuation_uncached_token_count": 8 + 240,
        "total_uncached_token_count": 2 * len(protocol.PROMPT_IDS) + 8 + 240,
    }

    receipts[0]["edited_token_index"] = 1
    with pytest.raises(runner.CalibrationExecutionError, match="boundary"):
        runner._execution_token_telemetry(receipts)


def test_pre_backend_cache_rehash_is_exact_and_detects_mutation() -> None:
    observed = {
        "cache_root": "/workspace/artifact_cache",
        "full_file_count": 3,
        "full_retained_bytes": 12_345,
        "full_file_inventory_sha256": "a" * 64,
        "components": [
            {
                "component": "model",
                "revision": protocol.MODEL_SPEC["revision"],
                "sha256": "b" * 64,
            }
        ],
    }
    cache = {**observed, "receipt_sha256": "c" * 64}
    receipt = runner._rehash_bound_public_cache(
        cache, rehash=lambda _path: dict(observed)
    )
    assert receipt["status"] == "pass_exact_pre_backend_rehash"
    core = dict(receipt)
    supplied = core.pop("receipt_sha256")
    assert supplied == protocol.canonical_sha256(core)

    mutated = {**observed, "full_file_inventory_sha256": "d" * 64}
    with pytest.raises(runner.CalibrationExecutionError, match="differs"):
        runner._rehash_bound_public_cache(cache, rehash=lambda _path: dict(mutated))

    execute_source = inspect.getsource(runner.execute)
    rehash_offset = execute_source.index("live_cache_rehash = watchdog.guard")
    backend_offset = execute_source.index("backend = watchdog.guard")
    assert rehash_offset < backend_offset
    assert execute_source.index("_rehash_bound_public_cache", rehash_offset) < (
        execute_source.index("runtime.V2Backend", backend_offset)
    )


def test_safe_metrics_archive_zero_realization_with_full_signed_schema() -> None:
    torch = pytest.importorskip("torch")
    clean = torch.tensor([1.0, 2.0, -1.0, -2.0], dtype=torch.bfloat16)
    requested_fp32 = torch.tensor([0.25, -0.5, 0.75, -1.0])
    requested = requested_fp32.to(dtype=torch.bfloat16)

    def trace(*, final: object) -> runtime.ArcTrace:
        return runtime.ArcTrace(
            token_ids_sha256="e" * 64,
            residual_by_layer={},
            final_residual=final,
            pre_edit=clean.clone(),
            post_edit=clean.clone(),
            requested_vector=requested.clone(),
            hook_fire_count=1,
        )

    zero_final = torch.zeros_like(clean)
    metrics, realized, final = runner._realization_metrics(
        clean,
        trace(final=zero_final),
        trace(final=zero_final),
        requested,
        requested_fp32,
    )
    assert {
        "requested_plus_realized_relative_rmse",
        "requested_minus_realized_relative_rmse",
        "requested_realized_central_relative_rmse",
        "requested_plus_realized_cosine",
        "requested_minus_realized_cosine",
        "requested_realized_central_cosine",
    } <= metrics.keys()
    assert metrics["requested_plus_realized_cosine"] == 0.0
    assert metrics["requested_minus_realized_cosine"] == 0.0
    assert metrics["requested_realized_central_cosine"] == 0.0
    assert metrics["common_mode_to_central_rms"] == 0.0
    assert metrics["finite"] is True
    assert torch.count_nonzero(realized) == 0
    assert torch.count_nonzero(final) == 0


def test_fp32_shadow_archives_degenerate_vectors() -> None:
    torch = pytest.importorskip("torch")

    class Backend:
        device = torch.device("cpu")

        def __init__(self) -> None:
            self.torch = torch

        @staticmethod
        def j_matrix(_layer: int) -> object:
            return torch.zeros((4, 4), dtype=torch.bfloat16)

        @staticmethod
        def shadow_matrix(_layer: int) -> object:
            return torch.zeros((4, 4), dtype=torch.float32)

    result = runner._fp32_shadow_metrics(
        Backend(),
        edit_layer=protocol.EDIT_LAYER,
        realized_central=torch.zeros(4),
        final_central=torch.zeros(4),
    )
    assert result["bf16_fp32_j_cosine"] == 0.0
    assert result["bf16_fp32_j_relative_rmse"] == 0.0
    assert result["fp32_j_actual_final_cosine"] == 0.0
    assert result["finite"] is True


def test_transport_logits_are_centered_on_the_signed_final_midpoint() -> None:
    torch = pytest.importorskip("torch")

    class Backend:
        device = torch.device("cpu")

        def __init__(self) -> None:
            self.torch = torch

        @staticmethod
        def j_matrix(_layer: int) -> object:
            return torch.eye(2, dtype=torch.bfloat16)

        @staticmethod
        def selected_logits_from_state(state, _token_ids):
            return state.float().square()

    telemetry = runner._transport_metrics(
        Backend(),
        final_midpoint=torch.tensor([3.0, 4.0]),
        source_delta=torch.tensor([1.0, 1.0]),
        final_central=torch.tensor([1.0, 1.0]),
        actual_selected_logits=torch.tensor([6.0, 8.0]),
        layer=protocol.EDIT_LAYER,
        transport="identity",
        selected_token_ids=(1, 2),
    )
    assert telemetry["predicted_logit_center"] == "signed_final_midpoint"
    assert torch.equal(
        telemetry["_predicted_selected_logit_delta"], torch.tensor([6.0, 8.0])
    )
    assert telemetry["fixed_token_logit_delta_pearson"] == pytest.approx(1.0)


def test_finite_orientation_failure_is_valid_archived_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(protocol, "WIDTH", 2)
    monkeypatch.setattr(protocol, "J_LAYERS", (protocol.EDIT_LAYER,))
    monkeypatch.setattr(orientation, "FIXTURE_COUNT", 2)
    monkeypatch.setattr(orientation, "EXPECTED_ROW_COUNT", 2)

    class Backend:
        def __init__(self) -> None:
            self.torch = torch

        @staticmethod
        def j_matrix(_layer: int) -> object:
            return torch.zeros((2, 2), dtype=torch.bfloat16)

    rows, receipt = orientation.execute(Backend(), plan_manifest_sha256="f" * 64)
    assert receipt["status"] == "fail"
    assert all(row["status"] == "fail" and row["finite"] for row in rows)
    orientation.validate(rows, receipt, plan_hash="f" * 64)
    assert runner._orientation_status(receipt) == "fail"


def test_runner_validates_every_exact_runtime_pin(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("alpha-package==1.2.3\nbeta==4.5.6\n", encoding="utf-8")
    expected = {"alpha-package": "1.2.3", "beta": "4.5.6"}
    assert (
        runner._validate_runtime_requirements(
            requirements, version=expected.__getitem__
        )
        == expected
    )
    with pytest.raises(runner.CalibrationExecutionError, match="versions differ"):
        runner._validate_runtime_requirements(
            requirements,
            version=lambda name: "0.0.0" if name == "beta" else expected[name],
        )


def test_v2_seed_material_is_fresh_relative_to_predecessor() -> None:
    for namespace, coordinates in (
        ("generic-layer50-direction", (0,)),
        ("fixed-token-panel-v2", ()),
        ("random-j-v2", (50, 0)),
        ("j-orientation-fixture-v2", (50, 0)),
    ):
        assert protocol.seed64(namespace, *coordinates) != base_protocol.seed64(
            namespace, *coordinates
        )
    assert orientation.fixture_seed(50, 0) == protocol.seed64(
        protocol.J_ORIENTATION_SPEC["fixture_seed_namespace"], 50, 0
    )


def test_namespace_rejects_symlinked_study_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume = tmp_path / "workspace"
    outside = tmp_path / "outside"
    volume.mkdir()
    outside.mkdir()
    (volume / protocol.STUDY_SLUG).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(protocol, "VOLUME_MOUNT_PATH", str(volume))
    with pytest.raises(runner.CalibrationExecutionError, match="real directory"):
        runner._initialize_namespace(volume, volume_id=protocol.NETWORK_VOLUME_ID)


def test_calibration_launcher_derives_authority_and_rejects_override(
    tmp_path: Path,
) -> None:
    ownership = _ownership_receipt()
    child = guest_launcher._set_attested_environment(
        ownership_receipt=ownership, environ={}
    )
    assert (
        child[base_protocol.GUEST_LAUNCH_OWNERSHIP_ENV] == ownership["receipt_sha256"]
    )
    with pytest.raises(guest_launcher.GuestLaunchError, match="caller override"):
        guest_launcher._set_attested_environment(
            ownership_receipt=ownership,
            environ={base_protocol.CUBLAS_WORKSPACE_CONFIG_ENV: ":16:8"},
        )
    with pytest.raises(guest_launcher.GuestLaunchError, match="launcher-owned"):
        guest_launcher._forwarded_arguments(
            ("--ownership-receipt", "/tmp/swapped.json")
        )

    path = tmp_path / "OWNERSHIP.json"
    path.write_bytes(base_protocol.canonical_json_bytes(ownership) + b"\n")
    captured: dict[str, object] = {}

    class ExecIntercept(RuntimeError):
        pass

    def intercept(executable, argv, environment):
        captured.update(
            executable=executable, argv=tuple(argv), environment=dict(environment)
        )
        raise ExecIntercept

    with pytest.raises(ExecIntercept):
        guest_launcher.launch(
            ownership_receipt_path=path,
            forwarded_args=("--", "--plan-dir", "/frozen/plan"),
            environ={},
            loaded_module_names=(),
            executable="/usr/bin/python3",
            execve=intercept,
        )
    argv = captured["argv"]
    assert argv[:5] == (
        "/usr/bin/python3",
        "-B",
        "-u",
        "-m",
        guest_launcher.RUNNER_MODULE,
    )
    assert argv.count("--ownership-receipt") == 1


def test_live_remote_freeze_requires_head_local_tracking_and_live_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit = "a" * 40
    responses = {
        ("rev-parse", "--verify", "HEAD"): commit,
        ("symbolic-ref", "--quiet", "--short", "HEAD"): "main",
        ("check-ref-format", "--branch", "main"): "main",
        ("rev-parse", "--verify", "refs/remotes/origin/main"): commit,
        (
            "ls-remote",
            "--exit-code",
            "origin",
            "refs/heads/main",
        ): f"{commit}\trefs/heads/main",
    }
    monkeypatch.setattr(authorize, "_git", lambda *args: responses[args])
    freeze = authorize._live_remote_freeze()
    assert freeze["git_head_commit"] == commit
    assert freeze["git_local_remote_commit"] == commit
    assert freeze["git_live_remote_commit"] == commit

    responses[("ls-remote", "--exit-code", "origin", "refs/heads/main")] = (
        f"{'b' * 40}\trefs/heads/main"
    )
    with pytest.raises(authorize.AuthorizationError, match="differ"):
        authorize._live_remote_freeze()
