from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from experiments.consciousness_sae_signed_dose_scan import (
    audit_recovery,
    protocol,
    recovery_equivalence,
    verify_recovery_equivalence,
)


class _Watchdog:
    def __init__(self) -> None:
        self.checks = 0

    def check(self) -> None:
        self.checks += 1


def _checkpoint(maps: dict[Any, Any], **metadata: Any) -> dict[str, Any]:
    return {
        "J": maps,
        "n_prompts": protocol.J_LENS_SPEC["release_config"]["prompts_fitted"],
        "d_model": protocol.WIDTH,
        **metadata,
    }


def _load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: dict[str, Any],
) -> tuple[Path, Any, dict[str, Any], dict[str, Any]]:
    path = tmp_path / "j.pt"
    path.write_bytes(b"pinned-test-checkpoint")
    fake_dtype = object()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float16=fake_dtype))
    monkeypatch.setattr(
        audit_recovery, "PUBLIC_J_CHECKPOINT_BYTES", path.stat().st_size
    )
    for value in checkpoint.get("J", {}).values():
        if type(value) is _FakeJMap:
            value.dtype = fake_dtype
    monkeypatch.setattr(
        protocol,
        "sha256_file",
        lambda candidate: (
            protocol.J_LENS_SPEC["sha256"]
            if Path(candidate) == path
            else "0" * 64
        ),
    )
    monkeypatch.setattr(
        audit_recovery, "_torch_load_checkpoint", lambda _path: checkpoint
    )
    return audit_recovery.load_j_checkpoint_superset(path, _Watchdog())


class _FakeJMap:
    shape = (protocol.WIDTH, protocol.WIDTH)

    def __init__(self) -> None:
        self.dtype: object | None = None


def test_authentic_zero_through_78_superset_is_behaviorally_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {str(layer): _FakeJMap() for layer in range(79)}
    path, filtered, record, inventory = _load(
        tmp_path, monkeypatch, _checkpoint(values)
    )
    assert path == (tmp_path / "j.pt")
    assert tuple(filtered) == tuple(range(45, 79))
    assert all(filtered[layer] is values[str(layer)] for layer in filtered)
    assert record == {
        "sha256": protocol.J_LENS_SPEC["sha256"],
        "map_count": 34,
        "revision": protocol.J_LENS_SPEC["revision"],
    }
    assert inventory["status"] == "pass_pinned_canonical_superset_filtered"
    assert inventory["available_layers"] == list(range(79))
    assert inventory["required_layers"] == list(range(45, 79))
    assert inventory["unused_extra_layers"] == list(range(45))
    core = dict(inventory)
    supplied = core.pop("receipt_sha256")
    assert supplied == protocol.canonical_sha256(core)


def test_superset_loader_rejects_a_missing_study_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {layer: _FakeJMap() for layer in range(79) if layer != 61}
    with pytest.raises(
        audit_recovery.AuditRecoveryError, match="lacks a required study layer"
    ):
        _load(tmp_path, monkeypatch, _checkpoint(values))


@pytest.mark.parametrize(
    "maps",
    [
        {45: object(), "45": object()},
        {"045": object()},
        {"+45": object()},
        {True: object()},
        {45.0: object()},
        {79: object()},
    ],
)
def test_normalizer_rejects_duplicate_or_noncanonical_keys(
    maps: dict[Any, Any]
) -> None:
    with pytest.raises(audit_recovery.AuditRecoveryError, match="J-lens layer key"):
        audit_recovery.normalize_j_map_keys(maps)


def test_superset_loader_binds_checkpoint_metadata_and_records_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    values = {layer: _FakeJMap() for layer in range(79)}
    _path, _maps, _record, inventory = _load(
        tmp_path, monkeypatch, _checkpoint(values, harmless_release_note=1)
    )
    assert inventory["checkpoint_n_prompts"] == int(
        protocol.J_LENS_SPEC["release_config"]["prompts_fitted"]
    )
    assert inventory["checkpoint_d_model"] == protocol.WIDTH
    assert inventory["checkpoint_bytes"] == len(b"pinned-test-checkpoint")
    assert inventory["source_map_shape"] == [protocol.WIDTH, protocol.WIDTH]
    assert inventory["source_map_dtype"] == "torch.float16"
    assert inventory["computation_dtype"] == "torch.bfloat16"

    bad = _checkpoint(values)
    bad["n_prompts"] = int(bad["n_prompts"]) + 1
    with pytest.raises(
        audit_recovery.AuditRecoveryError, match="checkpoint metadata differs"
    ):
        _load(tmp_path, monkeypatch, bad)


def test_superset_loader_rejects_wrong_source_shape_or_dtype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong_shape = {layer: _FakeJMap() for layer in range(79)}
    wrong_shape[45].shape = (1, protocol.WIDTH)
    with pytest.raises(
        audit_recovery.AuditRecoveryError,
        match="source map shape differs at layer 45",
    ):
        _load(tmp_path, monkeypatch, _checkpoint(wrong_shape))

    class _WrongDtypeMap(_FakeJMap):
        pass

    wrong_dtype = {layer: _FakeJMap() for layer in range(79)}
    wrong_dtype[45] = _WrongDtypeMap()
    # _load assigns the authenticated dtype only to the exact fixture class.
    with pytest.raises(
        audit_recovery.AuditRecoveryError,
        match="source map dtype differs at layer 45",
    ):
        _load(tmp_path, monkeypatch, _checkpoint(wrong_dtype))


def test_zero_forward_guard_blocks_module_calls_and_model_loads() -> None:
    class FakeModule:
        def __init__(self) -> None:
            pass

        def _call_impl(self) -> str:
            return "called"

        def forward(self) -> str:
            return "forwarded"

        def load_state_dict(self, _state: dict[str, object]) -> None:
            pass

    class FakePretrained:
        @classmethod
        def from_pretrained(cls, _name: str) -> str:
            return cls.__name__

    class FakeAutoModel:
        @classmethod
        def from_pretrained(cls, _name: str) -> str:
            return cls.__name__

    def disguised_forward(_module: object) -> str:
        return "child-forwarded"

    class FakeChild(FakeModule):
        forward = disguised_forward

    fake_torch = SimpleNamespace(nn=SimpleNamespace(Module=FakeModule))
    fake_transformers = SimpleNamespace(PreTrainedModel=FakePretrained)
    original_call = FakeModule._call_impl
    original_loader = FakePretrained.__dict__["from_pretrained"]
    existing_module = FakeChild()
    saved_bound_forward = existing_module.forward
    original_child_forward = FakeChild.__dict__["forward"]
    with audit_recovery.zero_forward_guard(
        torch_module=fake_torch,
        transformers_module=fake_transformers,
        auto_model_base=FakeAutoModel,
    ) as counts:
        with pytest.raises(audit_recovery.AuditRecoveryError, match="Module calls"):
            existing_module._call_impl()
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model loads"):
            FakePretrained.from_pretrained("forbidden")
        with pytest.raises(audit_recovery.AuditRecoveryError, match="forward access"):
            existing_module.forward()
        with pytest.raises(audit_recovery.AuditRecoveryError, match="forward call"):
            type(existing_module).forward(existing_module)
        with pytest.raises(audit_recovery.AuditRecoveryError, match="construction"):
            FakeChild()
        with pytest.raises(
            audit_recovery.AuditRecoveryError, match="new torch.nn.Module subclasses"
        ):
            class ForbiddenFutureModule(FakeChild):
                pass
        with pytest.raises(audit_recovery.AuditRecoveryError, match="state loading"):
            existing_module.load_state_dict({})
        with pytest.raises(audit_recovery.AuditRecoveryError, match="forward call"):
            saved_bound_forward()
        with pytest.raises(audit_recovery.AuditRecoveryError, match="forward call"):
            saved_bound_forward()
        assert counts == {
            "torch_module_calls": 1,
            "transformers_model_load_calls": 1,
            "direct_forward_attribute_access": 4,
            "model_construction_calls": 2,
            "model_state_load_calls": 1,
        }
    assert FakeModule._call_impl is original_call
    assert FakePretrained.__dict__["from_pretrained"] is original_loader
    assert FakeChild.__dict__["forward"] is original_child_forward


def test_zero_forward_guard_blocks_auto_from_config() -> None:
    class FakeModule:
        def __init__(self) -> None:
            pass

        def _call_impl(self) -> None:
            pass

        def load_state_dict(self, _state: object) -> None:
            pass

    class FakePretrained:
        @classmethod
        def from_pretrained(cls, _name: str) -> object:
            return object()

    class FakeAutoModel:
        @classmethod
        def from_config(cls, _config: object) -> object:
            return object()

    fake_torch = SimpleNamespace(nn=SimpleNamespace(Module=FakeModule))
    fake_transformers = SimpleNamespace(PreTrainedModel=FakePretrained)
    with audit_recovery.zero_forward_guard(
        torch_module=fake_torch,
        transformers_module=fake_transformers,
        auto_model_base=FakeAutoModel,
    ) as counts:
        with pytest.raises(audit_recovery.AuditRecoveryError, match="model loads"):
            FakeAutoModel.from_config(object())
        assert counts["transformers_model_load_calls"] == 1


def test_fresh_watchdog_does_not_consume_historical_campaign_clock() -> None:
    now = 10_000.0
    authorization = {
        "recovery_started_at_unix": now,
        "recovery_deadline_at_unix": now + 60,
        "hourly_price_usd": 6.0,
        "max_spend_usd": 1.0,
    }
    watchdog = audit_recovery.RecoveryWatchdog(
        authorization, audit_started_at_unix=now + 1, clock=lambda: now + 2
    )
    watchdog.check()
    assert watchdog.started == now
    assert watchdog.deadline == now + 60


def test_full_raw_tree_ledger_detects_post_hash_mutation(tmp_path: Path) -> None:
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"before")
    record = {
        "path": "payload.bin",
        "bytes": payload.stat().st_size,
        "sha256": protocol.sha256_file(payload),
    }
    core = {
        "run_id": "signed-dose-test",
        "records": [record],
    }
    complete = {**core, "receipt_sha256": protocol.canonical_sha256(core)}
    (tmp_path / "RUN_COMPLETE.json").write_bytes(
        protocol.canonical_json_bytes(complete) + b"\n"
    )
    before = audit_recovery.raw_tree_ledger(tmp_path)
    assert before["file_count"] == 2
    payload.write_bytes(b"after")
    with pytest.raises(audit_recovery.AuditRecoveryError, match="raw manifest differs"):
        audit_recovery.raw_tree_ledger(tmp_path)


def _execution_paths(root: Path, *, attempt_root: Path, raw_root: Path) -> dict[str, str]:
    plan = root / "plan"
    model = root / "model"
    plan.mkdir(exist_ok=True)
    model.mkdir(exist_ok=True)
    raw_root.mkdir(exist_ok=True)
    files = {}
    for name in ("j.pt", "ownership.json", "guest.json", "cache.json", "auth.json"):
        path = root / name
        path.write_bytes(b"fixture")
        files[name] = path
    return {
        "attempt_root": attempt_root.as_posix(),
        "output_directory": (attempt_root / "result").as_posix(),
        "attempt_marker": (attempt_root / "ATTEMPT_CLAIMED.json").as_posix(),
        "failure_receipt": (attempt_root / "RECOVERY_FAILED.json").as_posix(),
        "plan_dir": plan.as_posix(),
        "raw_root": raw_root.as_posix(),
        "model_snapshot": model.as_posix(),
        "j_lens_path": files["j.pt"].as_posix(),
        "original_ownership": files["ownership.json"].as_posix(),
        "original_guest": files["guest.json"].as_posix(),
        "original_cache": files["cache.json"].as_posix(),
        "original_authorization": files["auth.json"].as_posix(),
        "artifact_device": "cuda:0",
    }


def test_claim_rejects_output_namespace_inside_raw_before_marker(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    execution = _execution_paths(tmp_path, attempt_root=raw, raw_root=raw)
    marker = Path(execution["attempt_marker"])
    with pytest.raises(audit_recovery.AuditRecoveryError, match="output namespace"):
        audit_recovery._claim_attempt({"execution": execution})
    assert not marker.exists()


def test_claim_rejects_attempt_root_parent_symlink_before_marker(
    tmp_path: Path,
) -> None:
    real_attempt = tmp_path / "real-attempt"
    real_attempt.mkdir()
    alias = tmp_path / "attempt-alias"
    alias.symlink_to(real_attempt, target_is_directory=True)
    raw = tmp_path / "raw"
    execution = _execution_paths(tmp_path, attempt_root=alias, raw_root=raw)
    marker = Path(execution["attempt_marker"])
    with pytest.raises(audit_recovery.AuditRecoveryError, match="symlink"):
        audit_recovery._claim_attempt({"execution": execution})
    assert not marker.exists()


def test_recovery_source_never_imports_predecessor_recovery_mutable_state() -> None:
    source = Path(audit_recovery.__file__).read_text(encoding="utf-8")
    assert "from experiments.consciousness_sae_target_blind_calibration import audit_recovery" not in source
    assert "predecessor_recovery." not in source


def test_authorization_schema_names_explicit_cef_freezes() -> None:
    required = {
        "code_freeze_commit",
        "evidence_freeze_commit",
        "final_freeze_commit",
        "source_test_files",
        "qualification_files",
        "cumulative_review_files",
        "recovery_adjudication",
        "fresh_pod",
        "incident",
    }
    assert required <= audit_recovery.RECOVERY_AUTHORIZATION_FIELDS
    assert not {"C", "E", "F"} & audit_recovery.RECOVERY_AUTHORIZATION_FIELDS


def test_c_closure_matches_both_equivalence_implementations() -> None:
    expected = audit_recovery.MANDATORY_C_SOURCE_TEST_INCIDENT_PATHS
    assert recovery_equivalence.RECOVERY_CLOSURE_PATHS == expected
    assert verify_recovery_equivalence.RECOVERY_CLOSURE_PATHS == expected


def test_c4_freeze_surface_matches_the_frozen_status_map() -> None:
    root = Path(audit_recovery.__file__).resolve().parents[2]
    status_map = json.loads(
        (
            root
            / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C4_STATUS_MAP.json"
        ).read_text(encoding="utf-8")
    )
    frozen = status_map["e3_to_c4"]
    expected = {
        **{path: "A" for path in frozen["added"]},
        **{path: "M" for path in frozen["modified"]},
    }
    assert frozen["deleted"] == []
    assert audit_recovery.E3_TO_C4_NAME_STATUS == expected
    assert audit_recovery.C3_RECOVERY_FREEZE_COMMIT == status_map["c3_code_commit"]
    assert audit_recovery.E3_QUALIFICATION_FREEZE_COMMIT == status_map["base_commit"]
    assert audit_recovery.RECOVERY_PROTOCOL_VERSION.endswith(
        ".audit_only_recovery_v4"
    )
    assert audit_recovery.QUALIFICATION_DIRECTORY.endswith(
        "/audit_recovery_host_qualification_v4"
    )
    assert len(expected) == len(set(expected))
    assert audit_recovery.ORIGINAL_TO_C1_NAME_STATUS == (
        recovery_equivalence.ORIGINAL_TO_C1_NAME_STATUS
    )
    assert audit_recovery.ORIGINAL_TO_C1_NAME_STATUS == (
        verify_recovery_equivalence.ORIGINAL_TO_C1_NAME_STATUS
    )
    assert audit_recovery.C1_TO_C2_NAME_STATUS == (
        recovery_equivalence.C1_TO_C2_NAME_STATUS
    )
    assert audit_recovery.C1_TO_C2_NAME_STATUS == (
        verify_recovery_equivalence.C1_TO_C2_NAME_STATUS
    )


@pytest.mark.parametrize(
    "relative",
    (
        "experiments/consciousness_sae_signed_dose_scan/audit.py",
        "experiments/consciousness_sae_signed_dose_scan/protocol.py",
        "experiments/consciousness_sae_realization_validation/runpod_preflight.py",
    ),
)
def test_c_to_f_drift_in_live_recovery_dependencies_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    assert relative in audit_recovery.MANDATORY_C_SOURCE_TEST_INCIDENT_PATHS

    def divergent_blob(
        _repo_root: Path, commit: str, observed_relative: str
    ) -> tuple[str, bytes]:
        assert observed_relative == relative
        if commit == "C":
            return "a" * 40, b"code-at-C"
        return "b" * 40, b"drifted-at-F"

    monkeypatch.setattr(audit_recovery, "_git_blob", divergent_blob)
    with pytest.raises(audit_recovery.AuditRecoveryError, match="changed across"):
        audit_recovery._freeze_inventory(
            tmp_path,
            first_commit="C",
            final_commit="F",
            paths=[relative],
            label="source/test closure",
        )


@pytest.mark.parametrize("label", ("evidence freeze", "final freeze"))
def test_extra_e_or_f_changed_path_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str
) -> None:
    expected = {"required.json": "A"}

    def fake_git(_repo: Path, *args: str, **_kwargs: Any) -> Any:
        assert args[:3] == ("diff", "--name-status", "--no-renames")
        return SimpleNamespace(stdout="A\trequired.json\nA\textra.json\n")

    monkeypatch.setattr(audit_recovery, "_git", fake_git)
    with pytest.raises(audit_recovery.AuditRecoveryError, match="name-status map"):
        audit_recovery._require_exact_name_status(
            tmp_path,
            parent="parent",
            child="child",
            expected=expected,
            label=label,
        )


def test_merge_commit_is_not_a_direct_freeze_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = "a" * 40
    parent = "b" * 40

    def fake_git(_repo: Path, *args: str, **_kwargs: Any) -> Any:
        assert args == ("rev-list", "--parents", "-n", "1", child)
        return SimpleNamespace(stdout=f"{child} {parent} {'c' * 40}\n")

    monkeypatch.setattr(audit_recovery, "_git", fake_git)
    with pytest.raises(audit_recovery.AuditRecoveryError, match="parent differs"):
        audit_recovery._require_direct_parent(tmp_path, child, parent, "final freeze")


def test_swapped_second_review_input_is_rejected(tmp_path: Path) -> None:
    brief = tmp_path / "RECOVERY_PRO_REVIEW_BRIEF.md"
    context = tmp_path / "RECOVERY_PRO_REVIEW_CONTEXT.md"
    brief.write_text("brief\n", encoding="utf-8")
    context.write_text("context\n", encoding="utf-8")

    def row(role: str, path: Path) -> dict[str, Any]:
        raw = path.read_bytes()
        return {
            "role": role,
            "path": path.as_posix(),
            "bytes": len(raw),
            "characters": len(raw.decode("utf-8")),
            "sha256": audit_recovery.hashlib.sha256(raw).hexdigest(),
        }

    manifest = {
        "artifacts": [
            row("compact research-director plan brief", brief),
            row("synthesized context 1", brief),
        ]
    }
    with pytest.raises(audit_recovery.AuditRecoveryError, match="artifact binding"):
        audit_recovery._review_input_artifacts(
            manifest, brief_path=brief, context_path=context
        )


def test_empty_recovery_adjudication_decisions_are_rejected() -> None:
    with pytest.raises(audit_recovery.AuditRecoveryError, match="decisions are empty"):
        audit_recovery._adjudication_decision_ids([], [], ["B01"])


def test_authentic_provider_verdict_and_empty_findings_are_accepted() -> None:
    review = """# Verdict

The bounded recovery is execution-ready.

READY TO FREEZE

# Blocking findings

None.

# Important non-blocking findings

None.

# What should remain unchanged

Preserve the narrow claim boundary.
"""
    assert audit_recovery._provider_verdict(review) == "READY TO FREEZE"
    assert audit_recovery._provider_finding_headings(review) == []
    assert audit_recovery._adjudication_decision_ids([], [], []) == []


@pytest.mark.parametrize(
    "review",
    (
        "# Verdict\nREADY TO FREEZE\nMore verdict-section prose.\n",
        "# Verdict\nREADY TO FREEZE\n# Notes\nREADY TO FREEZE\n",
        "# Verdict\nREADY TO FREEZE\n# Notes\nNOT READY TO FREEZE\n",
        "# Verdict\nREADY TO FREEZE\n# Notes\n**NOT READY TO FREEZE**\n",
        "# Verdict\nREADY TO FREEZE \n# Notes\nDone.\n",
        "# Verdict\nREADY TO FREEZE\n# Verdict\nREADY TO FREEZE\n",
    ),
)
def test_provider_verdict_rejects_nonfinal_duplicate_or_conflicting_lines(
    review: str,
) -> None:
    with pytest.raises(audit_recovery.AuditRecoveryError, match="verdict"):
        audit_recovery._provider_verdict(review)


def test_provider_finding_parser_ignores_historical_ids_outside_sections() -> None:
    review = """# Verdict
Prior B01 and I01 remain historical.
# Blocking findings
### B07 — current blocker
details
# Important non-blocking findings
#### I03: current note
details
# What should remain unchanged
B02 is historical.
READY TO FREEZE
"""
    assert audit_recovery._provider_finding_headings(review) == ["B07", "I03"]


def test_one_none_finding_section_retains_exact_other_section_coverage() -> None:
    review = """# Blocking findings
None.
# Important non-blocking findings
### I03 — current note
details
# What should remain unchanged
I99 is historical.
"""
    assert audit_recovery._provider_finding_headings(review) == ["I03"]
    decisions = [
        {
            "finding_id": "I03",
            "disposition": "defer_nonblocking",
            "blocks_execution": False,
        }
    ]
    assert audit_recovery._adjudication_decision_ids(
        decisions, ["I03"], ["I03"]
    ) == ["I03"]
    with pytest.raises(audit_recovery.AuditRecoveryError, match="coverage"):
        audit_recovery._adjudication_decision_ids(decisions, ["I04"], ["I03"])


@pytest.mark.parametrize(
    "blocking,important",
    (
        ("", "None."),
        ("No findings.", "None."),
        ("None.\n### B01 — impossible mixture", "None."),
        ("### B01 — duplicate\n### B01 — duplicate again", "None."),
        ("### I01 — wrong section", "None."),
    ),
)
def test_provider_finding_parser_rejects_ambiguous_empty_or_duplicate_sections(
    blocking: str, important: str
) -> None:
    review = (
        f"# Blocking findings\n{blocking}\n"
        f"# Important non-blocking findings\n{important}\n"
        "# What should remain unchanged\nPreserve it.\n"
    )
    with pytest.raises(audit_recovery.AuditRecoveryError, match="finding"):
        audit_recovery._provider_finding_headings(review)


def _review_cost_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    usage = {
        "input_tokens": 29_731,
        "input_tokens_details": {
            "cache_write_tokens": 0,
            "cached_tokens": 0,
        },
        "output_tokens": 11_229,
        "output_tokens_details": {"reasoning_tokens": 9_050},
        "total_tokens": 40_960,
    }
    return (
        {"usage": usage},
        {
            "usage": usage,
            "input_rate_usd_per_million": 5.0,
            "cache_write_rate_usd_per_million": 6.25,
            "output_rate_usd_per_million": 30.0,
            "completed_response_cost_usd_conservative": 0.485525,
        },
    )


def test_authentic_provider_usage_and_cache_write_rate_are_accepted() -> None:
    response, manifest = _review_cost_fixture()
    assert audit_recovery._validated_review_cost(response, manifest) == pytest.approx(
        0.485525
    )


def test_nonzero_cache_write_tokens_are_charged_at_frozen_rate() -> None:
    usage = {
        "input_tokens": 100,
        "input_tokens_details": {"cache_write_tokens": 80},
        "output_tokens": 10,
    }
    response = {"usage": usage}
    manifest = {
        "usage": usage,
        "input_rate_usd_per_million": 5.0,
        "cache_write_rate_usd_per_million": 6.25,
        "output_rate_usd_per_million": 30.0,
        "completed_response_cost_usd_conservative": 0.0013,
    }
    assert audit_recovery._validated_review_cost(response, manifest) == pytest.approx(
        0.0013
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("cache_write_rate_usd_per_million", 0.0),
        ("cache_write_rate_usd_per_million", 6.24),
        ("completed_response_cost_usd_conservative", 0.485524),
        ("completed_response_cost_usd_conservative", float("nan")),
    ),
)
def test_provider_cost_rate_or_total_tampering_is_rejected(
    field: str, value: float
) -> None:
    response, manifest = _review_cost_fixture()
    manifest[field] = value
    with pytest.raises(audit_recovery.AuditRecoveryError, match="usage/cost"):
        audit_recovery._validated_review_cost(response, manifest)


def test_provider_usage_tampering_is_rejected() -> None:
    response, manifest = _review_cost_fixture()
    response["usage"] = {
        **response["usage"],
        "input_tokens": response["usage"]["input_tokens"] + 1,
    }
    with pytest.raises(audit_recovery.AuditRecoveryError, match="usage/cost"):
        audit_recovery._validated_review_cost(response, manifest)


def _hashed(core: dict[str, Any], field: str = "receipt_sha256") -> dict[str, Any]:
    return {**core, field: protocol.canonical_sha256(core)}


def _qualification_fixture(root: Path, *, commit: str) -> list[dict[str, str]]:
    source_root = Path(audit_recovery.__file__).resolve().parents[2]
    incident_target = root / audit_recovery.QUALIFICATION_INCIDENT_ROOT
    incident_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source_root / audit_recovery.QUALIFICATION_INCIDENT_ROOT,
        incident_target,
    )
    ledger_target = (
        root
        / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V4.json"
    )
    shutil.copy2(
        source_root
        / "docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V4.json",
        ledger_target,
    )
    shutil.copy2(
        source_root
        / "docs/consciousness_sae_signed_dose_scan/RECOVERY_C4_STATUS_MAP.json",
        ledger_target.parent / "RECOVERY_C4_STATUS_MAP.json",
    )
    successor_authority = (
        audit_recovery.verify_qualification_incident.successor_c4_authority_binding(
            incident_target, ledger_target
        )
    )
    relative_parent = (
        audit_recovery.QUALIFICATION_DIRECTORY
    )
    parent = root / relative_parent
    parent.mkdir(parents=True)
    closure_hash = "1" * 64
    packet = _hashed(
        {
            "status": "pass_source_design_and_compatibility_bound_no_outcomes_loaded",
            "recovery_closure": {
                "code_freeze_commit": commit,
                "inventory_sha256": closure_hash,
            },
            "compatibility_proof": {
                "compatibility_change_count": 1,
                "new_model_forwards": 0,
                "new_scientific_observations": 0,
                "required_layers": list(range(45, 79)),
                "pinned_available_layers": list(range(79)),
                "scientific_field_projection_unchanged": True,
            },
            "raw_run_opened": False,
            "compact_result_opened": False,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "outcome_input_paths": [],
            "analysis_data_inputs": [],
        },
        "packet_sha256",
    )
    equivalence = _hashed(
        {
            "status": "pass_outcome_blind_recovery_equivalence_verified",
            "packet_sha256": packet["packet_sha256"],
            "code_freeze_commit": commit,
            "recovery_closure_inventory_sha256": closure_hash,
            "raw_run_opened": False,
            "compact_result_opened": False,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "analysis_data_inputs": [],
        }
    )
    started = 1_000.0
    deadline = started + audit_recovery.QUALIFICATION_MAX_SECONDS
    completed = started + 30.0
    hourly_price = 5.0
    inputs = [
        {
            "role": role,
            "path": f"/qualification-inputs/{role}",
            "bytes": 1,
            "sha256": "9" * 64,
        }
        for role in (
            "equivalence_packet",
            "fresh_cache",
            "fresh_guest",
            "fresh_ownership",
            "independent_plan_audit",
            "pinned_j_checkpoint",
            "predecessor_qualification_attempt_marker",
            "predecessor_qualification_frozen_termination",
            "predecessor_qualification_postdelete_inventory",
            "predecessor_qualification_termination_audit",
            "predecessor_recovery_equivalence_packet",
            "predecessor_recovery_equivalence_verification",
            "predecessor_target_host_qualification",
            "predecessor_target_host_qualification_verification",
            "recovery_c4_status_map",
            "recovery_cycle_ledger_v4",
        )
    ]
    declared_inputs = [
        {"role": row["role"], "path": row["path"]} for row in inputs
    ]
    marker = _hashed(
        {
            "status": "attempt_started_irrevocably",
            "qualification_protocol_version": "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4",
            "qualification_cycle_version": "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4",
            "global_qualification_ordinal": 4,
            "successor_qualification_attempt": 1,
            "attempt_number": 1,
            "retry_authorized": False,
            "successor_authority_binding_sha256": successor_authority[
                "binding_sha256"
            ],
            "started_at_unix": started,
            "qualification_deadline_at_unix": deadline,
            "hourly_price_usd": hourly_price,
            "max_spend_usd": audit_recovery.QUALIFICATION_MAX_SPEND_USD,
            "declared_input_paths": declared_inputs,
            "declared_input_paths_sha256": protocol.canonical_sha256(
                declared_inputs
            ),
            "authorized_raw_input_paths": [],
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
        }
    )
    empty_inventory = protocol.canonical_sha256([])
    pod = {
        "pod_id": "qualification-pod",
        "gpu_type": protocol.GPU_TYPE,
        "gpu_count": 1,
        "ownership_receipt_sha256": "2" * 64,
        "guest_receipt_sha256": "3" * 64,
        "cache_receipt_sha256": "4" * 64,
        "precreate_unrelated_pod_count": 0,
        "precreate_unrelated_inventory_sha256": empty_inventory,
    }
    cast_probe = _hashed(
        {
            "status": "pass_exact_frozen_fp16_source_to_bf16_full_cast",
            "frozen_entrypoint": (
                "experiments.consciousness_sae_signed_dose_scan.audit."
                "_ArtifactJBackend.j_matrix"
            ),
            "source_layer": 45,
            "source_shape": [protocol.WIDTH, protocol.WIDTH],
            "source_dtype": "torch.float16",
            "computation_shape": [protocol.WIDTH, protocol.WIDTH],
            "computation_dtype": "torch.bfloat16",
            "device": "cuda:0",
            "device_name": "NVIDIA B200",
            "tiny_cross_device_probe_shape": [16, 16],
            "tiny_cpu_cast_matches_full_cuda_cast": True,
            "full_cast_finite": True,
            "backend_watchdog_check_count": 1,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
        }
    )
    checkpoint = _hashed(
        {
            "checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
            "checkpoint_revision": protocol.J_LENS_SPEC["revision"],
            "available_layers": list(range(79)),
            "required_layers": list(range(45, 79)),
            "filtered_layers": list(range(45, 79)),
            "missing_required_layer_negative": "pass_rejected_missing_required_layer_45",
            "checkpoint_bytes": audit_recovery.PUBLIC_J_CHECKPOINT_BYTES,
            "required_map_source_dtype": "torch.float16",
            "required_map_computation_dtype": "torch.bfloat16",
            "required_map_shape": [protocol.WIDTH, protocol.WIDTH],
            "frozen_bf16_cast_probe": cast_probe,
        }
    )
    target = _hashed(
        {
            "status": "pass_one_shot_zero_forward_target_host_qualification",
            "qualification_protocol_version": "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4",
            "qualification_cycle_version": "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4",
            "global_qualification_ordinal": 4,
            "successor_qualification_attempt": 1,
            "attempt_number": 1,
            "retry_authorized": False,
            "started_at_unix": started,
            "completed_at_unix": completed,
            "qualification_watchdog": {
                "status": "pass_independent_qualification_time_cost_cap",
                "started_at_unix": started,
                "qualification_deadline_at_unix": deadline,
                "maximum_seconds": audit_recovery.QUALIFICATION_MAX_SECONDS,
                "hourly_price_usd": hourly_price,
                "max_spend_usd": audit_recovery.QUALIFICATION_MAX_SPEND_USD,
                "maximum_theoretical_spend_usd": hourly_price * 0.5,
                "completed_at_unix": completed,
            },
            "attempt_marker_receipt_sha256": marker["receipt_sha256"],
            "successor_authority_binding_sha256": successor_authority[
                "binding_sha256"
            ],
            "successor_authority": successor_authority,
            "equivalence_verification": equivalence,
            "code_freeze_commit": commit,
            "recovery_closure_inventory_sha256": closure_hash,
            "fresh_pod": pod,
            "j_checkpoint": checkpoint,
            "cuda_startup": {
                "status": "pass_frozen_startup_and_real_bf16_cublas",
                "device_name": "NVIDIA B200",
                "model_forward_count": 0,
            },
            "zero_forward_guard": dict(audit_recovery.ZERO_GUARD_COUNTS),
            "raw_access_guard": {
                "status": "pass_no_forbidden_raw_or_path_guard_rejection",
                "forbidden_raw_root": "/workspace/consciousness_sae_signed_dose_scan/consciousness_sae_signed_dose_scan_v1/raw",
                "raw_forbidden_attempt_count": 0,
                "path_guard_rejected_attempt_count": 0,
                "allowed_outside_raw_enotdir_probe_count": 0,
                "allowed_outside_raw_proc_self_maps_probe_count": 1,
                "counter_semantics": {
                    "raw_forbidden_attempt_count": "lexically_inside_forbidden_raw_root",
                    "path_guard_rejected_attempt_count": "pre_containment_symlink_noncanonical_or_unresolvable_rejection",
                    "allowed_outside_raw_enotdir_probe_count": "errno_ENOTDIR_after_verified_non_symlink_ancestors",
                    "allowed_outside_raw_proc_self_maps_probe_count": "exact_kernel_proc_self_maps_alias_to_current_numeric_pid",
                },
                "path_diagnostic_limit": 16,
                "path_diagnostics": [
                    {
                        "classification": "allowed_outside_raw_proc_self_maps",
                        "errno": None,
                        "path_sha256": "8f9bcd1250f4c9fbe2eb0de0e4f9f2d4702ba9b7d168c54a35496ca5e51d7665",
                    }
                ],
                "path_diagnostics_sha256": protocol.canonical_sha256(
                    [
                        {
                            "classification": "allowed_outside_raw_proc_self_maps",
                            "errno": None,
                            "path_sha256": "8f9bcd1250f4c9fbe2eb0de0e4f9f2d4702ba9b7d168c54a35496ca5e51d7665",
                        }
                    ]
                ),
            },
            "inputs": inputs,
            "input_inventory_sha256": protocol.canonical_sha256(inputs),
            "raw_input_paths": [],
            "outcome_input_paths": [],
            "analysis_data_inputs": [],
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
        }
    )
    verified = _hashed(
        {
            "status": "pass_independent_target_host_qualification_verified",
            "qualification_protocol_version": "consciousness_sae_signed_dose_scan_v1.audit_recovery_host_qualification_v4",
            "qualification_cycle_version": "consciousness_sae_signed_dose_scan_v1.audit_only_recovery_cycle_v4",
            "global_qualification_ordinal": 4,
            "successor_qualification_attempt": 1,
            "qualification_receipt_sha256": target["receipt_sha256"],
            "attempt_marker_receipt_sha256": marker["receipt_sha256"],
            "successor_authority_binding_sha256": successor_authority[
                "binding_sha256"
            ],
            "successor_authority": successor_authority,
            "equivalence_packet_sha256": packet["packet_sha256"],
            "code_freeze_commit": commit,
            "recovery_closure_inventory_sha256": closure_hash,
            "j_checkpoint_evidence_sha256": checkpoint["receipt_sha256"],
            "j_checkpoint_sha256": protocol.J_LENS_SPEC["sha256"],
            "attempt_number": 1,
            "retry_authorized": False,
            "raw_run_opened": False,
            "compact_result_opened": False,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "target_feature_vector_count": 0,
            "analysis_data_inputs": [],
        }
    )
    postdelete = _hashed(
        {
            "status": "captured_read_only",
            "receipt_kind": "runpod_sanitized_full_inventory_v1",
            "phase": "postdelete",
            "pods": [],
            "all_account_pod_count": 0,
            "inventory_sha256": empty_inventory,
        }
    )
    frozen = _hashed(
        {
            "status": "deleted_verified",
            "receipt_kind": "runpod_termination_v1",
            "pod_id": pod["pod_id"],
            "agent_owned": True,
            "delete_http_status": 204,
            "post_delete_direct_http_status": 404,
            "absent_from_account_inventory": True,
            "other_pods_mutated": False,
            "budget_meter": {
                "elapsed_seconds": "30",
                "conservative_estimated_compute_usd": "0.1",
                "metered_cost_per_hour_usd": str(hourly_price),
                "max_usd": "36",
                "budget_exhausted": False,
            },
        }
    )
    termination = _hashed(
        {
            "status": "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            "receipt_kind": "runpod_successor_termination_audit_v1",
            "pod_id": pod["pod_id"],
            "successor_ownership_receipt_sha256": pod[
                "ownership_receipt_sha256"
            ],
            "frozen_termination_receipt_sha256": frozen["receipt_sha256"],
            "precreate_inventory_sha256": empty_inventory,
            "postdelete_inventory_sha256": empty_inventory,
        }
    )
    values = {
        "RECOVERY_EQUIVALENCE_PACKET.json": packet,
        "RECOVERY_EQUIVALENCE_VERIFICATION.json": equivalence,
        "ATTEMPT_STARTED.json": marker,
        "TARGET_HOST_QUALIFICATION.json": target,
        "TARGET_HOST_QUALIFICATION_VERIFICATION.json": verified,
        "QUALIFICATION_TERMINATION_AUDIT.json": termination,
        "QUALIFICATION_FROZEN_TERMINATION.json": frozen,
        "QUALIFICATION_POSTDELETE_INVENTORY.json": postdelete,
    }
    rows = []
    for name, value in sorted(values.items()):
        (parent / name).write_bytes(protocol.canonical_json_bytes(value) + b"\n")
        rows.append({"path": f"{relative_parent}/{name}"})
    return rows


def test_mandatory_E_qualification_receipts_are_semantically_bound(
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    rows = _qualification_fixture(tmp_path, commit=commit)
    result = audit_recovery._validate_qualification_evidence(
        rows, repo_root=tmp_path, code_freeze_commit=commit
    )
    assert result["qualification_pod_id"] == "qualification-pod"
    assert result["zero_forward_guard"] == audit_recovery.ZERO_GUARD_COUNTS

    target = next(
        tmp_path / row["path"]
        for row in rows
        if row["path"].endswith("TARGET_HOST_QUALIFICATION.json")
    )
    value = json.loads(target.read_text(encoding="utf-8"))
    value["zero_forward_guard"]["direct_forward_attribute_access"] = 1
    core = dict(value)
    core.pop("receipt_sha256")
    value["receipt_sha256"] = protocol.canonical_sha256(core)
    target.write_bytes(protocol.canonical_json_bytes(value) + b"\n")
    with pytest.raises(audit_recovery.AuditRecoveryError):
        audit_recovery._validate_qualification_evidence(
            rows, repo_root=tmp_path, code_freeze_commit=commit
        )


def test_qualification_rejects_self_consistent_false_full_j_cast(
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    rows = _qualification_fixture(tmp_path, commit=commit)
    target = next(
        tmp_path / row["path"]
        for row in rows
        if row["path"].endswith("TARGET_HOST_QUALIFICATION.json")
    )
    value = json.loads(target.read_text(encoding="utf-8"))
    cast = value["j_checkpoint"]["frozen_bf16_cast_probe"]
    cast["full_cast_finite"] = False
    cast_core = dict(cast)
    cast_core.pop("receipt_sha256")
    cast["receipt_sha256"] = protocol.canonical_sha256(cast_core)
    checkpoint_core = dict(value["j_checkpoint"])
    checkpoint_core.pop("receipt_sha256")
    value["j_checkpoint"]["receipt_sha256"] = protocol.canonical_sha256(
        checkpoint_core
    )
    target_core = dict(value)
    target_core.pop("receipt_sha256")
    value["receipt_sha256"] = protocol.canonical_sha256(target_core)
    target.write_bytes(protocol.canonical_json_bytes(value) + b"\n")

    with pytest.raises(
        audit_recovery.AuditRecoveryError,
        match="target-host qualification evidence differs",
    ):
        audit_recovery._validate_qualification_evidence(
            rows, repo_root=tmp_path, code_freeze_commit=commit
        )


def test_incident_closure_and_cycle_are_independently_revalidated() -> None:
    root = Path(audit_recovery.__file__).resolve().parents[2]
    docs = root / "docs/consciousness_sae_signed_dose_scan"
    result = audit_recovery.verify_incident_closure.verify_paths(
        docs / "INCIDENT_CLOSURE.json",
        schema_path=docs / "INCIDENT_CLOSURE_SCHEMA.json",
        recovery_ledger_path=docs / "RECOVERY_CYCLE_LEDGER.json",
    )
    assert result["receipt_sha256"] == (
        audit_recovery.EXPECTED_INCIDENT_VERIFICATION_RECEIPT_SHA256
    )
    assert result["raw_records_sha256"] == audit_recovery.EXPECTED_RAW_RECORDS_SHA256
