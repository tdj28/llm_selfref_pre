"""Offline lifecycle checks for the bounded B1 ambiguous-creation retry.

Keep this filename outside the frozen tests/test_bilingual*.py source glob.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.bilingual_llama_b1 import controller as old
from experiments.bilingual_llama_b1.halt import write_halt
from experiments.bilingual_pod_retry_b1 import controller as a
from tests.test_instruction_state_controller import FakeAPI, PUBLIC_KEY


AMENDMENT_FREEZE = "a" * 40
APPROVAL_REF = "owner-20261002-runpod-retry"
ORIGINAL_UTC = datetime.fromisoformat("2026-10-02T18:41:20.202067+00:00")
REAL_VERIFY_AMENDMENT = a.verify_amendment


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in B1 pod-retry tests")

    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


def test_pinned_retry_identity_and_unmodified_gpu_allocation():
    assert a.SCIENCE_FREEZE == "c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb"
    assert a.PLAN_HASH == "1f06e45c703b11f6d7c02535529fa69112bcfa640886a230550c689e1b1b3886"
    assert a.NAMESPACE == "bilingual-pod-retry-b1"
    assert a.ORIGINAL_INTENT_SHA == "78d564cdc7c772619e2c40807570a2e6690275c285038b7aad9745993d18111e"
    assert a.ORIGINAL_NAME == "codex-bilingual-llama-b1-20261002-cheap-e08cbdeb733f"
    assert old._utc(a.ORIGINAL_UTC) == ORIGINAL_UTC
    assert a.AMBIGUOUS_RESERVE_USD == Decimal("8")
    assert Decimal(str(a.ORIGINAL_RATE)) == Decimal(".84")
    assert (old.GPU_CAP_USD, old.API_CAP_USD, old.CONTINGENCY_USD) == (
        Decimal("45"), Decimal("125"), Decimal("15"))
    assert old.NEW_CAP_USD == old.TOTAL_USD == Decimal("200")


def test_scientific_worker_and_owned_cleanup_remain_inherited():
    for name in ("start_worker", "_confirm_closed", "_new_pod", "status", "monitor",
                 "approve", "retrieve", "signal_worker", "close_until_verified",
                 "_check_judging_halt"):
        assert getattr(a.Controller, name) is getattr(old.Controller, name)
    assert not any("bilingual_pod_retry_b1" in path for path in old.TESTS)
    raw = (Path(old.__file__).resolve().parents[2] / old.PLAN_RELATIVE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == a.PLAN_HASH
    assert not any("bilingual_pod_retry_b1" in path
                   for path in json.loads(raw)["source_hashes"])


def launch_without_worker(ctrl):
    ctrl.start_worker = Mock()
    ctrl.launch()
    return ctrl.event("create-intent")["data"]


def assert_no_post(api):
    assert not any(method == "POST" for method, _, _ in api.calls)


def assert_no_mutations(api):
    assert all(method == "GET" for method, _, _ in api.calls)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    out = root / "out/bilingual-llama-b1-20261002"
    out.mkdir(parents=True)
    plan_path = root / old.PLAN_RELATIVE
    plan_path.parent.mkdir(parents=True)
    plan = {"budget": deepcopy(old.BUDGET), "fixtures": [{"id": "synthetic-fixture"}]}
    plan_path.write_bytes(old._canonical(plan))
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
    state = SimpleNamespace(root=root, out=out, plan=plan, plan_path=plan_path,
                            now=ORIGINAL_UTC + timedelta(hours=1), ticks=0)
    state.api = FakeAPI(lambda: state.now)
    original = old.Controller(plan_path, a.SCIENCE_FREEZE, out, "cheap", state.api,
                              clock=lambda: ORIGINAL_UTC, monotonic=lambda: 0)
    payload = old.base.create_payload("cheap", old.base.PREFIX + "cheap-e08cbdeb733f", PUBLIC_KEY)
    payload["name"] = a.ORIGINAL_NAME
    intent = {"payload": payload, "quote": {"hourly_rate_usd": "0.74", "storage_hourly_usd": "0.10"},
              "blocked": [old.base.BLOCKED, *(pod["id"] for pod in state.api.extra)],
              "created_utc": a.ORIGINAL_UTC,
              "deadline_utc": (ORIGINAL_UTC + timedelta(seconds=1200)).isoformat(),
              "hard_deadline_utc": (ORIGINAL_UTC + timedelta(seconds=1800)).isoformat(),
              "prior_new_usd": "0", "prior_total_usd": "0", "contingency_used_usd": "0",
              "plan_sha256": a.PLAN_HASH, "freeze_commit": a.SCIENCE_FREEZE}
    receipt = original.ledger.bind("create-intent", intent)
    monkeypatch.setattr(a, "ORIGINAL_INTENT_SHA", receipt["sha256"])
    state.original, state.original_intent = original, intent
    state.original_bytes = original.ledger.path.read_bytes()
    state.amendment = {"amendment_freeze": AMENDMENT_FREEZE,
                       "sources": {"synthetic": "a" * 64}, "contract": a.amendment_contract()}
    state.verify = Mock(return_value=state.amendment)
    monkeypatch.setattr(a, "verify_amendment", state.verify)
    state.proof = {"schema": "bilingual-fixture-gate-b1", "pass": True,
                   "plan_sha256": a.PLAN_HASH, "freeze_commit": a.SCIENCE_FREEZE,
                   "judgment_count": 128, "new_fixture_calls": 0,
                   "inherited_fixture_freeze": "5398dc657b6af3255e5938539f27255ffbe74b0d"}
    state.fixture_path = out / "fixture-gate.json"
    state.fixture_path.write_bytes(old._canonical(state.proof))
    monkeypatch.setattr(old, "fixture_proof", Mock(return_value=state.proof))
    state.approval = out / "user-retry-approval.json"
    state.approval.write_bytes(old._canonical(old.approval_record(
        a.PLAN_HASH, a.SCIENCE_FREEZE, old.BUDGET, APPROVAL_REF)))

    def controller(kind="cheap", **kwargs):
        options = {"launch": True, "approved_new_cap_usd": "200",
                   "approval_ref": APPROVAL_REF, "approval_file": state.approval,
                   "fixture_gate": state.fixture_path,
                   "run": Mock(side_effect=AssertionError("Unexpected subprocess"))}
        options.update(kwargs)
        ctrl = a.Controller(kind, AMENDMENT_FREEZE, state.api,
                            clock=lambda: state.now, monotonic=lambda: state.ticks,
                            sleep=Mock(), **options)
        ctrl.disk_check = Mock()
        return ctrl

    state.controller = controller
    return state


def install_cheap_receipt(setup, *, tests=120, failures=0, errors=0, skipped=0,
                          cost="0.42", cumulative="8.42", done=True, exit_code=0,
                          get_status=404, within_limits=True, carry="8"):
    ctrl = setup.controller()
    ctrl.ledger.bind("create-intent", {"prior_new_usd": carry})
    directory = ctrl.base / "retrievals/synthetic-snapshot"
    directory.mkdir(parents=True)
    (directory / "DONE-all.json").write_text(json.dumps(
        {"pass": done, "scope": "tiny_cuda_exact_path"}))
    (directory / "controller-exit.json").write_text(json.dumps({"exit_code": exit_code}))
    (directory / "tests.xml").write_text(
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"/></testsuites>')
    receipt = ctrl.ledger.bind("retrieval:synthetic", {
        "pod_id": "retry-cheap-pod", "directory": str(directory),
        "artifacts": old.artifact_map(directory)})
    (ctrl.base / "final-retrieval.json").write_text(json.dumps(receipt))
    ctrl.ledger.bind("closed", {"pod_id": "retry-cheap-pod", "get_status": get_status,
                              "within_limits": within_limits, "compute_upper_bound_usd": cost,
                              "cumulative_gpu_upper_bound_usd": cumulative})
    return ctrl, directory


def test_constructor_and_guard_preserve_original_ledger_in_new_namespace(setup):
    ctrl = setup.controller()
    assert ctrl.base == setup.out / a.NAMESPACE / "cheap"
    assert ctrl.base != setup.original.base
    assert ctrl.freeze == a.SCIENCE_FREEZE
    assert ctrl.plan_hash == a.PLAN_HASH
    assert ctrl.budget == old.BUDGET
    assert ctrl.hard_seconds == old.CHEAP_SECONDS == 1800
    assert setup.controller("main").hard_seconds == old.MAIN_SECONDS == 18000
    assert ctrl.guard_original(600) == Decimal(4200) * Decimal(".84") / 3600
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes
    observation = [e["data"] for e in ctrl.ledger.read()
                   if e["id"].startswith("original-observation:")][-1]
    assert observation["matching_ids"] == []
    assert observation["original_intent_sha256"] == a.ORIGINAL_INTENT_SHA
    assert not any(pod["id"] in json.dumps(observation) for pod in setup.api.extra)
    assert_no_mutations(setup.api)


@pytest.mark.parametrize("problem", ["missing", "hash", "worker-intent", "worker-started", "tampered"])
def test_original_ledger_cannot_be_reset_or_dispatched(setup, monkeypatch, problem):
    if problem == "missing":
        setup.original.ledger.path.unlink()
    elif problem == "hash":
        monkeypatch.setattr(a, "ORIGINAL_INTENT_SHA", "f" * 64)
    elif problem == "tampered":
        path = setup.original.ledger.path
        path.write_bytes(path.read_bytes().replace(b'"prior_new_usd":"0"', b'"prior_new_usd":"1"'))
    else:
        setup.original.ledger.bind(problem, {"pod_id": "not-launched"})
    with pytest.raises(ValueError):
        setup.controller()
    assert setup.api.calls == []
    if problem == "missing":
        assert not setup.original.ledger.path.exists()


def test_wrong_scientific_plan_rejected_before_network(setup, monkeypatch):
    monkeypatch.setattr(a, "PLAN_HASH", "f" * 64)
    with pytest.raises(ValueError, match="Scientific plan changed"):
        setup.controller()
    assert setup.api.calls == []


def test_launch_binds_approval_fixture_amendment_and_reserve_once(setup):
    ctrl = setup.controller()
    intent = launch_without_worker(ctrl)
    assert Decimal(intent["prior_new_usd"]) == Decimal("8")
    assert intent["prior_total_usd"] == intent["contingency_used_usd"] == "0"
    assert intent["amendment"] == setup.amendment
    assert intent["freeze_commit"] == a.SCIENCE_FREEZE
    assert intent["plan_sha256"] == a.PLAN_HASH
    authority = ctrl.event("creation-approval")
    assert authority["sha256"] == intent["approval_sha256"]
    assert authority["data"]["approval_ref"] == APPROVAL_REF
    assert authority["data"]["amendment"]["contract"]["original_intent_sha256"] == a.ORIGINAL_INTENT_SHA
    assert ctrl.event("fixture-gate")["data"]["new_fixture_calls"] == 0
    assert ctrl.event("fixture-gate")["data"]["artifact_sha256"] == old.sha(setup.fixture_path)
    old.fixture_proof.assert_called_once_with(setup.plan, a.PLAN_HASH, a.SCIENCE_FREEZE)
    assert setup.api.pod["name"].startswith(old.PREFIX + "cheap-")
    assert setup.api.pod["name"] != a.ORIGINAL_NAME
    assert old._utc(intent["deadline_utc"]) == setup.now + timedelta(seconds=1200)
    assert old._utc(intent["hard_deadline_utc"]) == setup.now + timedelta(seconds=1800)
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes
    for candidate in (ctrl, setup.controller()):
        with pytest.raises(ValueError, match="Creation already attempted"):
            candidate.launch()
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1


@pytest.mark.parametrize("options", [
    {"launch": False}, {"approved_new_cap_usd": "201"},
    {"approved_new_cap_usd": "60"}, {"approval_ref": "old-owner-request"},
    {"approval_file": None},
])
def test_unapproved_retry_cannot_create(setup, options):
    with pytest.raises(ValueError):
        setup.controller(**options).launch()
    assert_no_post(setup.api)


@pytest.mark.parametrize("gpu_cap", ["42.86", "8"])
def test_launch_reserves_both_full_lifetimes_without_borrowing(setup, monkeypatch, gpu_cap):
    # 8 + .84 * .5 + 6.89 * 5 == 42.87, even though total spend fits 200.
    monkeypatch.setattr(old, "GPU_CAP_USD", Decimal(gpu_cap))
    with pytest.raises(ValueError, match="full GPU lifetimes"):
        setup.controller().launch()
    assert_no_post(setup.api)


def test_full_lifetime_reservation_at_exact_gpu_boundary(setup, monkeypatch):
    monkeypatch.setattr(old, "GPU_CAP_USD", Decimal("42.87"))
    launch_without_worker(setup.controller())
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1


def test_main_carries_ambiguous_reserve_plus_cheap_cost_once(setup):
    install_cheap_receipt(setup)
    ctrl = setup.controller("main")
    assert ctrl.cheap_receipt() == Decimal("8.42")
    intent = launch_without_worker(ctrl)
    assert Decimal(intent["prior_new_usd"]) == Decimal("8.42")
    assert old._utc(intent["deadline_utc"]) == setup.now + timedelta(seconds=17400)
    ctrl.cost_check(setup.api.pod, 60)
    accounting = [e["data"] for e in ctrl.ledger.read() if "projected_gpu_usd" in e["data"]][-1]
    assert Decimal(accounting["projected_gpu_usd"]) == Decimal("8.42") + Decimal(660) * Decimal("6.89") / 3600
    assert Decimal(accounting["reserved_non_gpu_usd"]) == Decimal("155")
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("changes", [
    {"tests": 0}, {"skipped": 1}, {"failures": 1}, {"errors": 1},
    {"done": False}, {"exit_code": 124}, {"get_status": 200},
    {"within_limits": False}, {"carry": "0"}, {"carry": "16"},
    {"cost": "-0.42", "cumulative": "7.58"}, {"cumulative": "0.42"},
    {"cumulative": "16.42"},
])
def test_failed_cheap_receipt_blocks_main_before_network(setup, changes):
    install_cheap_receipt(setup, **changes)
    with pytest.raises(ValueError):
        setup.controller("main").launch()
    assert setup.api.calls == []


def test_original_namespace_receipt_is_not_a_retry_cheap_gate(setup):
    (setup.original.base / "final-retrieval.json").write_text('{}')
    with pytest.raises(ValueError, match="Retry cheap gate"):
        setup.controller("main").launch()
    assert setup.api.calls == []


@pytest.mark.parametrize("problem", ["bytes", "extra", "detached", "amendment", "outside"])
def test_cheap_receipt_requires_amendment_and_exact_artifact_binding(setup, problem):
    cheap, directory = install_cheap_receipt(setup)
    ctrl = setup.controller("main")
    if problem == "bytes":
        (directory / "tests.xml").write_text('<testsuite tests="120"/>')
    elif problem == "extra":
        (directory / "unexpected.json").write_text('{}')
    elif problem == "amendment":
        ctrl.amendment = {**ctrl.amendment, "amendment_freeze": "b" * 40}
    else:
        path = cheap.base / "final-retrieval.json"
        receipt = json.loads(path.read_text())
        if problem == "detached":
            receipt["id"] = "retrieval:not-in-ledger"
        else:
            receipt["data"]["directory"] = str(setup.root)
        path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        ctrl.cheap_receipt()
    assert setup.api.calls == []


@pytest.mark.parametrize("seconds,horizon", [(35000, 0), (3600, 31000), (-1, 0), (3600, -1)])
def test_original_reserve_horizon_and_clock_fail_closed(setup, seconds, horizon):
    ctrl = setup.controller()
    setup.now = ORIGINAL_UTC + timedelta(seconds=seconds)
    with pytest.raises(ValueError):
        ctrl.guard_original(horizon)
    assert_no_mutations(setup.api)
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


def test_original_reserve_covers_entire_future_cheap_and_main_lifetimes(setup):
    # Present elapsed cost fits 8, but not elapsed + cheap + main + retrieval.
    setup.now = ORIGINAL_UTC + timedelta(hours=5)
    with pytest.raises(ValueError, match="reserved horizon"):
        setup.controller().launch()
    assert_no_post(setup.api)


@pytest.mark.parametrize("action", ["guard", "launch"])
def test_slow_inventory_crossing_original_reserve_blocks_dispatch(setup, action):
    horizon = 600 if action == "guard" else old.CHEAP_SECONDS + old.MAIN_SECONDS + old.RESERVE_SECONDS
    # 34260 seconds costs 7.994; the 60-second inventory makes it 8.008.
    setup.now = ORIGINAL_UTC + timedelta(seconds=34260 - horizon)
    ctrl = setup.controller()
    inventory = setup.api.inventory

    def slow_inventory():
        pods = inventory()
        if action == "guard" or ctrl.event("create-intent") is not None:
            setup.now += timedelta(seconds=60)
            setup.ticks += 60
        return pods

    setup.api.inventory = Mock(side_effect=slow_inventory)
    with pytest.raises(ValueError, match="reserved horizon"):
        if action == "guard":
            ctrl.guard_original(horizon)
        else:
            ctrl.launch()
    observations = [e["data"] for e in ctrl.ledger.read()
                    if e["id"].startswith("original-observation:")]
    assert observations[-1]["utc"] == setup.now.isoformat()
    assert setup.ticks == 60
    if action == "launch":
        assert ctrl.event("create-intent") is not None
        with pytest.raises(ValueError, match="Creation already attempted"):
            setup.controller().launch()
    assert ctrl.event("created") is None
    assert ctrl.event("worker-intent") is None
    assert_no_post(setup.api)
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("phase", ["before", "during", "recorded-after-restart"])
def test_original_observation_rejects_clock_rollback(setup, phase):
    ctrl = setup.controller()
    if phase == "before":
        setup.now -= timedelta(seconds=1)
    elif phase == "during":
        inventory = setup.api.inventory

        def backward_inventory():
            setup.now -= timedelta(seconds=1)
            return inventory()

        setup.api.inventory = backward_inventory
    else:
        setup.now += timedelta(seconds=120)
        ctrl.guard_original()
        setup.api.calls.clear()
        setup.now -= timedelta(seconds=60)
        ctrl = setup.controller()
    with pytest.raises(ValueError, match="charge horizon|clock moved backward"):
        ctrl.guard_original()
    if phase != "during":
        assert setup.api.calls == []
    assert_no_mutations(setup.api)


@pytest.mark.parametrize("problem", [None, "over-reserve", "negative", "not-404", "bytes", "detached"])
def test_original_closed_cost_requires_hash_verified_bounded_receipt(setup, problem):
    directory = setup.original.base / "retrievals/original-closure"
    directory.mkdir(parents=True)
    artifact = directory / "controller.log"
    artifact.write_text("synthetic original closure, no worker dispatched\n")
    receipt = setup.original.ledger.bind("retrieval:original", {
        "pod_id": "late-original-owned", "directory": str(directory),
        "artifacts": old.artifact_map(directory)})
    path = setup.original.base / "final-retrieval.json"
    path.write_text(json.dumps(receipt))
    cost = {"over-reserve": "8.01", "negative": "-0.01"}.get(problem, "1.25")
    setup.original.ledger.bind("closed", {
        "pod_id": "late-original-owned", "get_status": 200 if problem == "not-404" else 404,
        "compute_upper_bound_usd": cost})
    if problem == "bytes":
        artifact.write_text("changed after retrieval")
    elif problem == "detached":
        path.write_text(json.dumps({**receipt, "id": "retrieval:not-in-ledger"}))
    ctrl = setup.controller()
    before = setup.original.ledger.path.read_bytes()
    setup.now = ORIGINAL_UTC + timedelta(days=2)
    if problem is None:
        assert ctrl.guard_original(3600) == Decimal("1.25")
        assert a.original_closed_cost(setup.out, a.original_events(setup.out)) == Decimal("1.25")
    else:
        message = {"negative": "Unknown or invalid cost/time",
                   "bytes": "cleanup artifacts changed"}.get(problem, "cleanup not hash-verified")
        with pytest.raises(ValueError, match=message):
            ctrl.guard_original(3600)
    assert setup.original.ledger.path.read_bytes() == before
    assert_no_mutations(setup.api)


@pytest.mark.parametrize("problem", [None, "artifacts", "directory", "pod-id", "pod-name",
                                    "pod-createdAt", "missing-created", "owned-name"])
def test_original_no_worker_receipt_requires_empty_artifacts_and_owned_identity(setup, problem):
    pod = late_original(setup)
    if problem == "owned-name":
        pod["name"] = "foreign-pod-name"
        setup.original.ledger.bind("created", pod)
    elif problem != "missing-created":
        setup.original._register(pod)
    data = {"pod_id": pod["id"], "pod": deepcopy(pod),
            "no_worker_dispatched": True, "artifacts": {}}
    if problem == "artifacts":
        data["artifacts"] = {"unexpected.log": "a" * 64}
    elif problem == "directory":
        data["directory"] = str(setup.original.base / "retrievals/not-created")
    elif problem and problem.startswith("pod-"):
        data["pod"][problem.removeprefix("pod-")] = "foreign-identity"
    receipt = setup.original.ledger.bind("retrieval:no-worker", data)
    (setup.original.base / "final-retrieval.json").write_text(json.dumps(receipt))
    setup.original.ledger.bind("closed", {
        "pod_id": pod["id"], "get_status": 404, "compute_upper_bound_usd": "1.25"})
    ctrl = setup.controller()
    before = setup.original.ledger.path.read_bytes()
    setup.now = ORIGINAL_UTC + timedelta(days=2)
    if problem is None:
        assert ctrl.guard_original(3600) == Decimal("1.25")
        assert a.original_closed_cost(setup.out, a.original_events(setup.out)) == Decimal("1.25")
        assert not (setup.original.base / "retrievals").exists()
    else:
        with pytest.raises(ValueError, match="Invalid no-worker cleanup evidence"):
            ctrl.guard_original(3600)
    assert setup.original.event("worker-intent") is None
    assert setup.original.ledger.path.read_bytes() == before
    assert_no_mutations(setup.api)


def test_cost_check_rechecks_original_with_retrieval_horizon_before_parent(setup, monkeypatch):
    ctrl = setup.controller()
    order = []
    ctrl.guard_original = Mock(side_effect=lambda seconds: order.append(("guard", seconds)))
    parent = Mock(side_effect=lambda pod, horizon: order.append(("parent", horizon)) or Decimal(".1"))
    monkeypatch.setattr(old.Controller, "cost_check", parent)
    assert ctrl.cost_check({}, 123) == Decimal(".1")
    assert order == [("guard", Decimal(723)), ("parent", 123)]
    parent.reset_mock()
    ctrl.guard_original.side_effect = ValueError("late original")
    with pytest.raises(ValueError, match="late original"):
        ctrl.cost_check({}, 123)
    parent.assert_not_called()


def test_cost_and_deadline_remain_parent_limits(setup):
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    setup.now += timedelta(seconds=900)
    setup.ticks += 900
    ctrl.cost_check(setup.api.pod, 60)
    accounting = [e["data"] for e in ctrl.ledger.read() if "projected_gpu_usd" in e["data"]][-1]
    assert Decimal(accounting["projected_gpu_usd"]) == Decimal(8) + Decimal(1560) * Decimal(".84") / 3600
    assert accounting["contingency_used_usd"] == "0"
    setup.now += timedelta(seconds=240)
    setup.ticks += 240
    with pytest.raises(ValueError, match="deadline"):
        ctrl.cost_check(setup.api.pod, 60)


@pytest.mark.parametrize("problem", ["missing", "altered", "halt", "malformed-halt"])
def test_fixture_and_judging_halt_gates_are_not_bypassed(setup, problem):
    ctrl = setup.controller()
    if problem == "missing":
        ctrl.fixture_gate_path = None
    elif problem == "altered":
        setup.fixture_path.write_text(json.dumps({**setup.proof, "new_fixture_calls": 1}))
    elif problem == "halt":
        write_halt(setup.out / "JUDGING-HALT.json", a.PLAN_HASH, a.SCIENCE_FREEZE, "JudgeHalted")
    else:
        (setup.out / "JUDGING-HALT.json").write_text('{broken')
    with pytest.raises(ValueError):
        ctrl.launch()
    assert setup.api.calls == []
    assert ctrl.event("create-intent") is None


def test_worker_dispatch_keeps_scientific_freeze_and_deadline(setup, monkeypatch):
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    ctrl._ssh = Mock(return_value=b"")
    script = Mock(return_value="set -eu\ntrue\n")
    monkeypatch.setattr(old, "worker_script", script)
    old.Controller.start_worker(ctrl)
    worker = ctrl.event("worker-intent")["data"]
    assert worker["seconds"] == 1200
    assert worker["freeze_commit"] == a.SCIENCE_FREEZE
    assert worker["plan_sha256"] == a.PLAN_HASH
    script.assert_called_once_with("cheap", old.PLAN_RELATIVE, a.SCIENCE_FREEZE,
                                   ctrl.event("create-intent")["data"]["deadline_utc"])


def test_halt_after_creation_prevents_worker_dispatch(setup):
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    ctrl._ssh = Mock()
    write_halt(setup.out / "JUDGING-HALT.json", a.PLAN_HASH, a.SCIENCE_FREEZE, "JudgeHalted")
    with pytest.raises(ValueError):
        old.Controller.start_worker(ctrl)
    ctrl._ssh.assert_not_called()
    assert ctrl.event("worker-intent") is None


def test_ambiguous_post_never_allows_second_create_after_restart(setup):
    real_request = setup.api.request

    def uncertain(method, path, body=None):
        if method == "POST":
            setup.api.calls.append((method, path, body))
            raise old.base.ApiError(500)
        return real_request(method, path, body)

    setup.api.request = uncertain
    ctrl = setup.controller()
    with pytest.raises(RuntimeError, match="unresolved"):
        ctrl.launch()
    assert ctrl.event("create-intent") is not None
    assert ctrl.event("worker-intent") is None
    before = ctrl.ledger.path.read_bytes()
    with pytest.raises(ValueError, match="Creation already attempted"):
        setup.controller().launch()
    assert ctrl.ledger.path.read_bytes() == before
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


def test_lost_post_response_reconciles_same_pod_without_second_post(setup):
    setup.api.lost_response = True
    ctrl = setup.controller()
    launch_without_worker(ctrl)
    assert ctrl.owned()["id"] == setup.api.pod["id"]
    assert any(e["id"].startswith("create-reconciled:") for e in ctrl.ledger.read())
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1


def late_original(setup):
    return {**deepcopy(setup.original_intent["payload"]), "id": "late-original-owned",
            "createdAt": a.ORIGINAL_UTC, "cost": "0.74",
            "gpu": {"id": old.base.HARDWARE["cheap"][0], "count": 1,
                    "memory": old.base.HARDWARE["cheap"][2]}}


@pytest.mark.parametrize("discover_kind,resume_kind", [("cheap", "main"), ("main", "cheap")])
def test_late_discovery_permanently_halts_both_retry_ledgers(setup, discover_kind, resume_kind):
    ctrl = setup.controller(discover_kind)
    setup.api.extra.append(late_original(setup))
    with pytest.raises(ValueError, match="Original pod appeared"):
        ctrl.guard_original()
    assert ctrl.event("original-late-detected") is not None
    setup.api.extra.pop()
    setup.api.calls.clear()
    with pytest.raises(ValueError, match="permanently halted"):
        setup.controller(resume_kind).guard_original()
    assert setup.api.calls == []
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("discover_kind,resume_kind", [("cheap", "main"), ("main", "cheap")])
@pytest.mark.parametrize("already_closed", [False, True])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_finalizer_only_discovery_permanently_halts_other_kind(
        setup, monkeypatch, discover_kind, resume_kind, already_closed, ambiguous):
    if discover_kind == "main":
        install_cheap_receipt(setup)
    retry = setup.controller(discover_kind)
    launch_without_worker(retry)
    if already_closed:
        retry.ledger.bind("closed", {"pod_id": retry.owned()["id"], "get_status": 404})
    assert retry.event("original-late-detected") is None
    matches = [late_original(setup)]
    if ambiguous:
        matches.append({**matches[0], "id": "second-original-name-match"})
    setup.api.extra.extend(matches)

    def closed_after_durable_detection():
        assert retry.event("original-late-detected") is not None
        return {"closed": True}

    retry.close_until_verified = Mock(side_effect=closed_after_durable_detection)
    original_close = Mock(side_effect=closed_after_durable_detection)
    monkeypatch.setattr(old.Controller, "close_until_verified", original_close)
    if ambiguous:
        with pytest.raises(ValueError, match="ownership ambiguous"):
            a.reconcile_late_original(setup.api, retry=retry)
        original_close.assert_not_called()
    else:
        assert a.reconcile_late_original(setup.api, retry=retry) == {"closed": True}
        original_close.assert_called_once_with()
    if already_closed:
        retry.close_until_verified.assert_not_called()
    else:
        retry.close_until_verified.assert_called_once_with()
    marker = retry.event("original-late-detected")["data"]
    assert marker["matching_ids"] == [pod["id"] for pod in matches]
    assert marker["original_intent_sha256"] == a.ORIGINAL_INTENT_SHA
    del setup.api.extra[-len(matches):]
    setup.api.calls.clear()
    with pytest.raises(ValueError, match="permanently halted"):
        setup.controller(resume_kind).guard_original()
    assert setup.api.calls == []
    assert setup.original.event("worker-intent") is None


def test_late_reconciliation_ignores_foreign_pods_and_does_not_claim_deletion(setup):
    setup.api.extra.append({"id": "near-name", "name": a.ORIGINAL_NAME + "-foreign"})
    assert a.reconcile_late_original(setup.api) == {
        "exact_name": a.ORIGINAL_NAME, "matches": 0, "deletion_claimed": False}
    assert_no_mutations(setup.api)
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("problem", ["blocked-id", "old-time", "image", "cloud", "disk",
                                    "mounts", "ports", "gpu-id", "gpu-count", "gpu-memory", "multiple"])
def test_exact_name_alone_never_authorizes_foreign_pod_mutation(setup, monkeypatch, problem):
    pod = late_original(setup)
    if problem == "blocked-id":
        pod["id"] = old.base.BLOCKED
    elif problem == "old-time":
        pod["createdAt"] = (ORIGINAL_UTC - timedelta(seconds=61)).isoformat()
    elif problem.startswith("gpu-"):
        key = problem.removeprefix("gpu-")
        pod["gpu"][key] = {"id": "foreign-gpu", "count": 2, "memory": 1}[key]
    elif problem != "multiple":
        pod[problem] = "foreign"
    setup.api.extra.append(pod)
    if problem == "multiple":
        setup.api.extra.append({**pod, "id": "second-match"})
    close = Mock()
    monkeypatch.setattr(old.Controller, "close_until_verified", close)
    with pytest.raises(ValueError):
        a.reconcile_late_original(setup.api)
    close.assert_not_called()
    assert_no_mutations(setup.api)
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


def test_late_owned_cleanup_closes_retry_before_original_and_never_starts_worker(setup, monkeypatch):
    retry = setup.controller()
    launch_without_worker(retry)
    setup.api.extra.append(late_original(setup))
    inventory = Mock(side_effect=setup.api.inventory)
    setup.api.inventory = inventory
    order = []
    retry.close_until_verified = Mock(side_effect=lambda: order.append("retry"))
    close = Mock(side_effect=lambda: order.append("original") or {"closed": True})
    monkeypatch.setattr(old.Controller, "close_until_verified", close)
    start = Mock(side_effect=AssertionError("Expired original must not launch a worker"))
    monkeypatch.setattr(old.Controller, "start_worker", start)
    reconcile = Mock(side_effect=AssertionError("Do not re-fetch the validated pod by name"))
    monkeypatch.setattr(old.Controller, "reconcile", reconcile)
    assert a.reconcile_late_original(setup.api, retry=retry) == {"closed": True}
    assert order == ["retry", "original"]
    assert setup.original.event("created")["data"]["id"] == "late-original-owned"
    assert setup.original.event("worker-intent") is None
    start.assert_not_called()
    reconcile.assert_not_called()
    inventory.assert_called_once_with()
    assert sum(method == "POST" for method, _, _ in setup.api.calls) == 1


def test_late_foreign_match_closes_only_retry_before_ownership_rejection(setup, monkeypatch):
    retry = setup.controller()
    launch_without_worker(retry)
    setup.api.extra.append({**late_original(setup), "image": "foreign-image"})
    retry.close_until_verified = Mock()
    original_close = Mock()
    monkeypatch.setattr(old.Controller, "close_until_verified", original_close)
    with pytest.raises(ValueError, match="ownership proof"):
        a.reconcile_late_original(setup.api, retry=retry)
    retry.close_until_verified.assert_called_once()
    original_close.assert_not_called()
    assert setup.original.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("changed_identity", [None, "id", "createdAt"])
def test_late_cleanup_restart_preserves_registered_identity_with_new_status(setup, monkeypatch, changed_identity):
    pod = {**late_original(setup), "status": "PENDING"}
    setup.original._register(pod)
    before = setup.original.ledger.path.read_bytes()
    observed = {**pod, "status": "RUNNING"}
    if changed_identity == "id":
        observed["id"] = "late-replacement-pod"
    elif changed_identity == "createdAt":
        observed["createdAt"] = (ORIGINAL_UTC + timedelta(seconds=30)).isoformat()
    setup.api.extra.append(observed)
    register = Mock(side_effect=AssertionError("Cleanup restart must not rebind created receipt"))
    monkeypatch.setattr(old.Controller, "_register", register)
    close = Mock(return_value={"closed": True})
    monkeypatch.setattr(old.Controller, "close_until_verified", close)
    if changed_identity is None:
        assert a.reconcile_late_original(setup.api) == {"closed": True}
        close.assert_called_once_with()
    else:
        with pytest.raises(ValueError, match="differs from registered identity"):
            a.reconcile_late_original(setup.api)
        close.assert_not_called()
    register.assert_not_called()
    assert setup.original.owned()["status"] == "PENDING"
    assert setup.original.ledger.path.read_bytes() == before
    assert setup.original.event("worker-intent") is None
    assert_no_mutations(setup.api)


def test_cli_reconciles_after_failed_action_without_dispatching_worker(setup, monkeypatch):
    ctrl = setup.controller()
    ctrl.status = Mock(side_effect=ValueError("original appeared"))
    constructor = Mock(return_value=ctrl)
    monkeypatch.setattr(a, "Controller", constructor)
    monkeypatch.setattr(old.base, "RunPodV2", Mock(return_value=setup.api))
    reconcile = Mock()
    monkeypatch.setattr(a, "reconcile_late_original", reconcile)
    with pytest.raises(ValueError, match="original appeared"):
        a.main(["--amendment-freeze", AMENDMENT_FREEZE, "--kind", "cheap",
                "--action", "status", "--launch"])
    reconcile.assert_called_once_with(setup.api, retry=ctrl)
    assert_no_post(setup.api)


def test_default_cli_inspects_without_api_or_credentials(setup, monkeypatch, capsys):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    api = Mock(side_effect=AssertionError("Inspect must not construct an API client"))
    monkeypatch.setattr(old.base, "RunPodV2", api)
    a.main(["--amendment-freeze", AMENDMENT_FREEZE, "--kind", "cheap"])
    assert json.loads(capsys.readouterr().out) == setup.amendment
    setup.verify.assert_called_once_with(AMENDMENT_FREEZE, network=False)
    api.assert_not_called()


def test_amendment_verifies_exact_sources_and_its_separate_public_freeze(tmp_path, monkeypatch):
    sources = {}
    for name in a.AMENDMENT_PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        sources[name] = ("synthetic source " + name + "\n").encode()
        path.write_bytes(sources[name])
    monkeypatch.setattr(a, "AMENDMENT_ROOT", tmp_path)

    def git(argv, **kwargs):
        assert kwargs["cwd"] == tmp_path
        if argv == ["git", "rev-parse", "HEAD"]:
            return (AMENDMENT_FREEZE + "\n").encode()
        assert argv[:2] == ["git", "show"]
        freeze, name = argv[2].split(":", 1)
        assert freeze == AMENDMENT_FREEZE
        return sources[name]

    monkeypatch.setattr(a.subprocess, "check_output", git)
    ci, public = Mock(), Mock()
    monkeypatch.setattr(old, "verify_ci", ci)
    monkeypatch.setattr(old.base, "verify_public", public)
    proof = REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE, network=False)
    assert proof["sources"] == {name: hashlib.sha256(raw).hexdigest() for name, raw in sources.items()}
    assert proof["contract"]["science_freeze"] == a.SCIENCE_FREEZE
    assert proof["contract"]["scientific_changes"] == []
    ci.assert_not_called()
    public.assert_not_called()
    REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE)
    ci.assert_called_once_with(AMENDMENT_FREEZE)
    public.assert_called_once_with(proof["sources"][a.AMENDMENT_PATHS[1]],
                                   a.AMENDMENT_PATHS[1], AMENDMENT_FREEZE)
    (tmp_path / a.AMENDMENT_PATHS[0]).write_text("changed after freeze")
    with pytest.raises(ValueError, match="source changed"):
        REAL_VERIFY_AMENDMENT(AMENDMENT_FREEZE)


@pytest.mark.parametrize("freeze", [a.SCIENCE_FREEZE, "short", "", None])
def test_original_or_invalid_commit_cannot_be_amendment(freeze):
    with pytest.raises(ValueError, match="Separate full amendment commit"):
        REAL_VERIFY_AMENDMENT(freeze, network=False)
