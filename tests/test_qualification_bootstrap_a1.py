"""Offline checks for the separate bootstrap amendment; no paid calls."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.instruction_qualification_bootstrap_a1 import controller as a
from experiments.instruction_state_qualification import controller as old
from tests.test_instruction_state_controller import FakeAPI, PUBLIC_KEY, UTC


AMENDMENT_FREEZE = "a" * 40
REAL_FAILED_RECEIPT = a.failed_receipt
REAL_VERIFY_AMENDMENT = a.verify_amendment


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in bootstrap amendment tests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    out = root / "out/instruction-qualification-20261001"
    out.mkdir(parents=True)
    plan_path = root / old.PLAN_RELATIVE
    plan_path.parent.mkdir(parents=True)
    plan = {"budget": deepcopy(old.BUDGET)}
    plan_path.write_text(json.dumps(plan))
    monkeypatch.setattr(a, "PLAN_HASH", old.sha(plan_path))
    monkeypatch.setattr(old, "ROOT", root)
    monkeypatch.setattr(old, "OWNED_OUT", out)
    monkeypatch.setattr(old, "load_plan", Mock(return_value=plan))
    monkeypatch.setattr(old, "_require_ignored", Mock())
    monkeypatch.setattr(old, "verify_ci", Mock(return_value={"pass": True}))
    monkeypatch.setattr(old.base, "verify_public", Mock())
    key = root / "synthetic-ssh-key"
    key.write_text("synthetic fixture, not a credential")
    Path(str(key) + ".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(old.base, "KEY", key)
    monkeypatch.setenv("HF_TOKEN", "hf_placeholder_only")
    amendment = {"amendment_freeze": AMENDMENT_FREEZE,
                 "sources": {"fixture": "a" * 64}, "contract": a.amendment_contract()}
    verify = Mock(return_value=amendment)
    failed = Mock(return_value=a.FAILED_COST)
    monkeypatch.setattr(a, "verify_amendment", verify)
    monkeypatch.setattr(a, "failed_receipt", failed)
    state = SimpleNamespace(root=root, out=out, now=UTC, ticks=0,
                            amendment=amendment, verify=verify, failed=failed)
    state.api = FakeAPI(lambda: state.now)
    approval = out / "user-approval.json"
    approval.write_text(json.dumps(old.approval_record(a.PLAN_HASH, a.SCIENCE_FREEZE,
                                                       old.BUDGET, "synthetic-user-request")))

    def controller(kind="cheap", **kwargs):
        options = {"launch": True, "approved_new_cap_usd": "25",
                   "approval_ref": "synthetic-user-request", "approval_file": approval}
        options.update(kwargs)
        ctrl = a.Controller(kind, AMENDMENT_FREEZE, state.api,
                            clock=lambda: state.now, monotonic=lambda: state.ticks,
                            sleep=Mock(), **options)
        ctrl.disk_check = Mock()
        ctrl.run = Mock(side_effect=AssertionError("Unexpected subprocess"))
        return ctrl

    state.controller = controller
    return state


def launch_without_worker(ctrl):
    ctrl.start_worker = Mock()
    ctrl.launch()
    return ctrl.event("create-intent")["data"]


def install_cheap_receipt(setup, *, tests=176, failures=0, errors=0, skipped=0,
                          cost="0.42", done=True, exit_code=0, get_status=404):
    ctrl = setup.controller()
    directory = ctrl.base / "retrievals/synthetic-snapshot"
    directory.mkdir(parents=True)
    (directory / "DONE-all.json").write_text(json.dumps(
        {"pass": done, "scope": "tiny_cuda_exact_path"}))
    (directory / "controller-exit.json").write_text(json.dumps({"exit_code": exit_code}))
    (directory / "tests.xml").write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"/></testsuites>')
    receipt = ctrl.ledger.bind("retrieval:synthetic", {
        "pod_id": "new-cheap-pod", "directory": str(directory),
        "artifacts": old.artifact_map(directory)})
    (ctrl.base / "final-retrieval.json").write_text(json.dumps(receipt))
    ctrl.ledger.bind("closed", {"pod_id": "new-cheap-pod", "get_status": get_status,
                              "within_limits": True, "compute_upper_bound_usd": cost})
    return ctrl, directory


def test_constructor_separates_namespace_but_preserves_science_and_budget(setup):
    original = setup.out / old.NAMESPACE / "cheap/events.jsonl"
    ledger = old.EventLedger(original, a.PLAN_HASH, a.SCIENCE_FREEZE, [])
    ledger.bind("old-accounting", {"elapsed_seconds": "595.225087"})
    before = original.read_bytes()
    ctrl = setup.controller()
    assert ctrl.base == setup.out / a.NAMESPACE / "cheap"
    assert ctrl.out == old.OWNED_OUT
    assert ctrl.freeze == a.SCIENCE_FREEZE
    assert ctrl._elapsed0 == 0
    assert ctrl.hard_seconds == 1800
    assert ctrl.budget == old.BUDGET
    assert ctrl.budget["cheap_seconds"] == 1200
    assert ctrl.event("controller:config")["data"]["retrieval_seconds"] == 600
    assert original.read_bytes() == before
    old.load_plan.assert_called_with(ctrl.plan_path, a.SCIENCE_FREEZE)
    assert setup.controller("main").hard_seconds == 6600


def test_constructor_rejects_wrong_scientific_hash(setup, monkeypatch):
    monkeypatch.setattr(a, "PLAN_HASH", "b" * 64)
    with pytest.raises(ValueError, match="Scientific plan changed"):
        setup.controller()
    assert setup.api.calls == []


def test_cheap_creation_carries_failed_rental_and_reserves_full_main(setup):
    ctrl = setup.controller()
    intent = launch_without_worker(ctrl)
    assert Decimal(intent["prior_new_usd"]) == a.FAILED_COST
    assert old._utc(intent["deadline_utc"]) == UTC + timedelta(seconds=1200)
    assert old._utc(intent["hard_deadline_utc"]) == UTC + timedelta(seconds=1800)
    assert intent["freeze_commit"] == a.SCIENCE_FREEZE
    assert intent["amendment"] == setup.amendment
    assert {p["id"] for p in setup.api.extra} <= set(intent["blocked"])
    full = a.FAILED_COST + Decimal(".84") * 1800 / 3600 + Decimal("6.89") * 6600 / 3600
    assert full < old.GPU_CAP_USD
    assert full + old.API_CAP_USD + old.EXTRA_RESERVE_USD < old.NEW_CAP_USD
    assert setup.api.pod["name"].startswith(old.PREFIX + "cheap-")
    with pytest.raises(ValueError, match="Creation already attempted"):
        ctrl.launch()
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1


def test_retry_reservation_includes_previous_gpu_cost(setup, monkeypatch):
    future = Decimal(".84") * 1800 / 3600 + Decimal("6.89") * 6600 / 3600
    monkeypatch.setattr(old, "GPU_CAP_USD", future + a.FAILED_COST / 2)
    with pytest.raises(ValueError, match="full future lifetimes"):
        launch_without_worker(setup.controller())
    assert not any(method == "POST" for method, _, _ in setup.api.calls)


def test_cheap_cost_clock_uses_extended_window_and_failed_cost(setup):
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    setup.now += timedelta(seconds=900)
    setup.ticks += 900
    ctrl.cost_check(setup.api.pod, 60)
    accounting = [r for r in ctrl.ledger.read() if "projected_gpu_usd" in r["data"]][-1]["data"]
    assert Decimal(accounting["projected_gpu_usd"]) == a.FAILED_COST + Decimal(1560) * Decimal(".84") / 3600
    assert accounting["reserved_non_gpu_usd"] == "11"
    setup.now += timedelta(seconds=240)
    setup.ticks += 240
    with pytest.raises(ValueError, match="deadline"):
        ctrl.cost_check(setup.api.pod, 60)


def test_main_carries_exact_failed_plus_successful_cheap_once(setup):
    install_cheap_receipt(setup)
    ctrl = setup.controller("main")
    expected = a.FAILED_COST + Decimal(".42")
    assert ctrl.cheap_receipt() == expected
    intent = launch_without_worker(ctrl)
    assert Decimal(intent["prior_new_usd"]) == expected
    assert old._utc(intent["deadline_utc"]) == UTC + timedelta(seconds=6000)
    assert old._utc(intent["hard_deadline_utc"]) == UTC + timedelta(seconds=6600)


@pytest.mark.parametrize("changes", [
    {"tests": 175}, {"tests": 177}, {"tests": 0}, {"skipped": 1},
    {"failures": 1}, {"errors": 1}, {"done": False}, {"exit_code": 124}, {"get_status": 200},
])
def test_incomplete_or_failed_cheap_blocks_main_before_runpod(setup, changes):
    install_cheap_receipt(setup, **changes)
    with pytest.raises(ValueError):
        setup.controller("main").launch()
    assert setup.api.calls == []


def test_missing_a1_receipt_does_not_adopt_original_cheap(setup):
    root = setup.out / old.NAMESPACE / "cheap"
    root.mkdir(parents=True)
    (root / "final-retrieval.json").write_text('{}')
    with pytest.raises(ValueError, match="A1 cheap gate required"):
        setup.controller("main").launch()
    assert setup.api.calls == []


@pytest.mark.parametrize("kind", ["unknown-file", "changed-bytes", "detached-receipt"])
def test_receipt_requires_exact_hash_inventory_and_ledger_binding(setup, kind):
    ctrl, directory = install_cheap_receipt(setup)
    if kind == "unknown-file":
        (directory / "unexpected.json").write_text('{}')
    elif kind == "changed-bytes":
        (directory / "tests.xml").write_text('<testsuite tests="176"/>')
    else:
        receipt = json.loads((ctrl.base / "final-retrieval.json").read_text())
        receipt["id"] = "retrieval:not-in-ledger"
        (ctrl.base / "final-retrieval.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="artifact binding"):
        setup.controller("main").launch()
    assert setup.api.calls == []


@pytest.mark.parametrize("failure", ["amendment-ci", "science-ci", "failed-receipt", "public-plan"])
def test_ci_and_provenance_failure_precedes_creation(setup, failure):
    ctrl = setup.controller()
    failing = {"amendment-ci": setup.verify, "science-ci": old.verify_ci,
               "failed-receipt": setup.failed, "public-plan": old.base.verify_public}[failure]
    failing.side_effect = ValueError("synthetic prelaunch failure")
    with pytest.raises(ValueError, match="synthetic prelaunch failure"):
        ctrl.launch()
    assert setup.api.calls == []
    assert ctrl.event("create-intent") is None


def test_frozen_worker_and_cleanup_methods_remain_original():
    for name in ("start_worker", "cost_check", "_confirm_closed", "_new_pod", "status",
                 "monitor", "decision", "approve", "retrieve", "signal_worker", "close_until_verified"):
        assert getattr(a.Controller, name) is getattr(old.Controller, name)
    script = old.worker_script("cheap", old.PLAN_RELATIVE, a.SCIENCE_FREEZE, UTC.isoformat())
    assert "INSTRUCTION_TEST_DEVICE=cuda" in script
    assert "assert torch.cuda.is_available()" in script
    assert a.SCIENCE_FREEZE in script
    assert "qualification_bootstrap_a1" not in script
    assert "test_qualification_bootstrap_a1" not in old.TESTS
    assert not any("qualification_bootstrap_a1" in str(path) for path in old.protocol.source_paths())


def test_worker_dispatch_uses_1200_second_window_and_original_identity(setup, monkeypatch):
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    ctrl._ssh = Mock(return_value=b"")
    original_script = Mock(return_value="set -eu\ntrue\n")
    monkeypatch.setattr(old, "worker_script", original_script)
    old.Controller.start_worker(ctrl)
    worker = ctrl.event("worker-intent")["data"]
    assert worker["seconds"] == 1200
    assert worker["freeze_commit"] == a.SCIENCE_FREEZE
    assert worker["plan_sha256"] == a.PLAN_HASH
    original_script.assert_called_once_with("cheap", old.PLAN_RELATIVE, a.SCIENCE_FREEZE,
                                          ctrl.event("create-intent")["data"]["deadline_utc"])


def test_failed_rental_receipt_is_hash_bound(tmp_path, monkeypatch):
    root = tmp_path / old.NAMESPACE / "cheap"
    directory = root / "retrievals/failure"
    directory.mkdir(parents=True)
    (directory / "controller.log").write_text("synthetic incomplete test run")
    ledger = old.EventLedger(root / "events.jsonl", a.PLAN_HASH, a.SCIENCE_FREEZE, [])
    receipt = ledger.bind("retrieval:failed", {"pod_id": a.FAILED_POD, "directory": str(directory),
                                               "artifacts": old.artifact_map(directory)})
    (root / "final-retrieval.json").write_text(json.dumps(receipt))
    closed = ledger.bind("closed", {"pod_id": a.FAILED_POD, "get_status": 404,
                                   "within_limits": True, "compute_upper_bound_usd": str(a.FAILED_COST)})
    monkeypatch.setattr(a, "FAILED_CLOSURE", closed["sha256"])
    assert REAL_FAILED_RECEIPT(tmp_path) == a.FAILED_COST
    (directory / "controller.log").write_text("changed")
    with pytest.raises(ValueError, match="not hash-verified"):
        REAL_FAILED_RECEIPT(tmp_path)


def test_amendment_verifies_its_commit_and_ci_separately(tmp_path, monkeypatch):
    for name in a.A1_PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic amendment source\n")
    monkeypatch.setattr(a, "A1_ROOT", tmp_path)
    def git(argv, **kwargs):
        assert kwargs["cwd"] == tmp_path
        if argv == ["git", "rev-parse", "HEAD"]:
            return (AMENDMENT_FREEZE + "\n").encode()
        assert argv[:2] == ["git", "show"]
        assert argv[2].startswith(AMENDMENT_FREEZE + ":")
        return b"synthetic amendment source\n"
    monkeypatch.setattr(a.subprocess, "check_output", git)
    ci, public = Mock(), Mock()
    monkeypatch.setattr(old, "verify_ci", ci)
    monkeypatch.setattr(old.base, "verify_public", public)
    assert REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE, network=False)["contract"]["science_freeze"] == a.SCIENCE_FREEZE
    ci.assert_not_called()
    public.assert_not_called()
    REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE)
    ci.assert_called_once_with(AMENDMENT_FREEZE)
    assert public.call_args.args[2] == AMENDMENT_FREEZE
    (tmp_path / a.A1_PATHS[0]).write_text("modified after freeze")
    with pytest.raises(ValueError, match="source changed"):
        REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE)


@pytest.mark.parametrize("freeze", [a.SCIENCE_FREEZE, "short", "", None])
def test_original_or_invalid_commit_cannot_be_amendment(freeze):
    with pytest.raises(ValueError, match="Separate full amendment commit"):
        REAL_VERIFY_AMENDMENT(freeze, network=False)
