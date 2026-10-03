"""Offline tests of the separate cheap-002 clock amendment, not new science."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.steering_fidelity import controller as old
from scripts import steering_fidelity_bootstrap_a1 as a
from tests.test_steering_fidelity_controller import FREEZE, UTC, rig


AMENDMENT = "c" * 40
SCIENCE = "2d9c94f1de59f0f59dd89636c20afece1f6d1daf"
FAILED_COST = Decimal("0.06297823093333333333333333333")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A1 tests must not contact a network")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


@pytest.fixture
def setup(rig, monkeypatch):
    first = rig.launch(rig.controller())
    rig.snapshot(first, {
        "controller.log": b"164 synthetic passing tests; suite incomplete\n",
        "pip-freeze.txt": b"synthetic dependency receipt\n",
        "controller-exit.json": b'{"exit_code":0}',
        "controller-stopped.json": b'{"stopped":true}',
    })
    rig.advance(269.906704)
    first.terminate()
    closed = first.event("closed")
    assert Decimal(closed["data"]["compute_upper_bound_usd"]) == FAILED_COST
    monkeypatch.setattr(a, "SCIENCE_FREEZE", FREEZE)
    monkeypatch.setattr(a, "PLAN_HASH", first.plan_hash)
    monkeypatch.setattr(a, "ORIGINAL_POD", first.owned()["id"])
    monkeypatch.setattr(a, "ORIGINAL_CLOSED_HASH", closed["sha256"])
    amendment = {
        "amendment_freeze": AMENDMENT,
        "sources": {name: "b" * 64 for name in a.PATHS},
        "ci": {"run_id": 37, "pass": True,
               "scope": "operational amendment and inherited lifecycle"},
        "scientific_freeze": FREEZE, "plan_sha256": first.plan_hash,
        "cheap_hard_seconds": 1800, "main_hard_seconds": 9000,
        "caps_unchanged": {"phase_c": "25", "gpu": "22", "campaign": "170"},
    }
    rig.api.calls.clear()
    state = SimpleNamespace(rig=rig, first=first, amendment=amendment,
                            original_bytes=first.ledger.path.read_bytes())

    def controller(kind="cheap", attempt=None):
        return rig.controller(kind, attempt=(2 if kind == "cheap" else 1)
                              if attempt is None else attempt)

    def complete_replacement(*, amendment=None, skipped=0):
        ctrl = controller()
        a.apply_window(ctrl, state.amendment if amendment is None else amendment)
        rig.launch(ctrl)
        rig.snapshot(ctrl, {
            "DONE-all.json": b'{"pass":true,"scope":"tiny_cuda_exact_path"}',
            "controller-exit.json": b'{"exit_code":0}',
            "tests.xml": (f'<testsuites><testsuite tests="268" failures="0" '
                          f'errors="0" skipped="{skipped}"/></testsuites>').encode(),
        })
        rig.advance(120)
        ctrl.terminate()
        return ctrl

    state.controller, state.complete_replacement = controller, complete_replacement
    return state


def test_public_failure_and_frozen_source_pins_remain_exact():
    assert a.SCIENCE_FREEZE == SCIENCE
    assert a.ORIGINAL_COST == FAILED_COST
    root = a.ROOT / "data/steering_fidelity/cheap_startup_failure_20261002"
    release = json.loads((root / "RELEASE.json").read_bytes())
    assert release["science_freeze"] == SCIENCE
    assert release["plan_sha256"] == a.PLAN_HASH
    assert release["owned_pod_id"] == a.ORIGINAL_POD
    assert release["closed_event_sha256"] == a.ORIGINAL_CLOSED_HASH
    assert Decimal(release["compute_upper_bound_usd"]) == FAILED_COST
    assert release["get_status_after_delete"] == 404
    assert release["scientific_rows"] == 0
    assert len(release["artifacts"]) == 4
    assert "tests.xml" not in release["artifacts"] and "DONE-all.json" not in release["artifacts"]
    assert {name: old.sha(root / name) for name in release["artifacts"]} == release["artifacts"]
    plan_path = a.ROOT / old.PLAN_RELATIVE
    assert old.sha(plan_path) == a.PLAN_HASH
    plan = json.loads(plan_path.read_bytes())
    for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
        assert old.sha(a.ROOT / name) == expected, name
    assert not set(a.PATHS) & set(plan["source_hashes"])
    assert len(a.PATHS) == 4
    assert (old.CHEAP_SECONDS, old.MAIN_SECONDS, old.RESERVE_SECONDS) == (900, 9000, 600)
    assert (old.NEW_CAP_USD, old.GPU_CAP_USD, old.STORAGE_RESERVE_USD, old.TOTAL_USD) == (
        Decimal(25), Decimal(22), Decimal(3), Decimal(170))


def test_only_effective_clock_changes_original_config_and_ledger_are_preserved(setup):
    ctrl = setup.controller()
    config, budget = deepcopy(ctrl.event("controller:config")), deepcopy(ctrl.budget)
    campaign = ctrl.campaign.path.read_bytes()
    assert a.apply_window(ctrl, setup.amendment) is ctrl
    assert ctrl.hard_seconds == 1800
    assert ctrl.event("controller:config") == config
    assert config["data"]["hard_seconds"] == 900
    assert ctrl.budget == budget and ctrl.budget["cheap_seconds"] == 900
    assert ctrl.campaign.path.read_bytes() == campaign
    assert setup.first.ledger.path.read_bytes() == setup.original_bytes
    event = ctrl.event("bootstrap-a1")
    assert event["data"] == {
        "amendment": setup.amendment, "original_closed_sha256": a.ORIGINAL_CLOSED_HASH,
        "original_cost_usd": str(FAILED_COST), "inherited_config_retained": True,
        "effective_hard_seconds": 1800,
    }
    assert setup.rig.api.calls == []


def test_creation_carries_failed_cost_and_reserves_full_1800_plus_9000(setup):
    ctrl = a.apply_window(setup.controller(), setup.amendment)
    setup.rig.launch(ctrl)
    intent = ctrl.event("create-intent")["data"]
    created = old._utc(intent["created_utc"])
    assert old._utc(intent["deadline_utc"]) == created + timedelta(seconds=1200)
    assert old._utc(intent["hard_deadline_utc"]) == created + timedelta(seconds=1800)
    assert Decimal(intent["prior_new_usd"]) == FAILED_COST
    reservation = next(e for e in ctrl.campaign.read() if e["id"] == "attempt:cheap-002")
    total = FAILED_COST + Decimal(".84") * 1800 / 3600 + Decimal("6.89") * 9000 / 3600
    assert total == Decimal("17.70797823093333333333333333")
    assert Decimal(reservation["data"]["projection"]["projected_gpu_usd"]) == total
    assert Decimal(reservation["data"]["projection"]["projected_all_in_usd"]) == total + 3
    assert intent["freeze_commit"] == FREEZE
    setup.rig.ci.assert_called_with(FREEZE)
    with pytest.raises(ValueError, match="already attempted"):
        setup.rig.launch(ctrl)
    assert sum(method == "POST" for method, _, _ in setup.rig.api.calls) == 1


def test_failed_cost_is_not_dropped_at_cap_boundary(setup, monkeypatch):
    ctrl = a.apply_window(setup.controller(), setup.amendment)
    future = Decimal(".84") * 1800 / 3600 + Decimal("6.89") * 9000 / 3600
    monkeypatch.setattr(old, "GPU_CAP_USD", future + FAILED_COST / 2)
    with pytest.raises(ValueError, match="cap or reserves"):
        setup.rig.launch(ctrl)
    assert not any(method == "POST" for method, _, _ in setup.rig.api.calls)


def test_work_stops_at_1140_seconds_without_spending_retrieval_reserve(setup):
    ctrl = a.apply_window(setup.controller(), setup.amendment)
    setup.rig.launch(ctrl)
    setup.rig.advance(900)
    ctrl.cost_check(setup.rig.api.pod, 60)
    last = [e for e in ctrl.ledger.read() if e["id"].startswith("accounting:")][-1]
    assert Decimal(last["data"]["projected_gpu_usd"]) == FAILED_COST + Decimal(".84") * 1560 / 3600
    setup.rig.advance(240)
    with pytest.raises(ValueError, match="deadline"):
        ctrl.cost_check(setup.rig.api.pod, 60)


def test_restart_reuses_bound_amendment_without_extending_deadlines(setup):
    first = a.apply_window(setup.controller(), setup.amendment)
    setup.rig.launch(first)
    before = deepcopy(first.event("create-intent"))
    setup.rig.advance(500)
    restarted = setup.controller()
    assert restarted.hard_seconds == 900
    a.apply_window(restarted, setup.amendment)
    assert restarted.hard_seconds == 1800
    assert restarted.event("create-intent") == before
    assert len([e for e in restarted.ledger.read() if e["id"] == "bootstrap-a1"]) == 1
    assert setup.first.ledger.path.read_bytes() == setup.original_bytes


@pytest.mark.parametrize("kind,attempt", [("cheap", 1), ("cheap", 3), ("main", 2)])
def test_other_attempts_cannot_receive_amendment(setup, kind, attempt):
    ctrl = setup.controller(kind, attempt)
    before = ctrl.hard_seconds
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == before and ctrl.event("bootstrap-a1") is None
    assert setup.rig.api.calls == []


@pytest.mark.parametrize("field,value", [
    ("scientific_freeze", "f" * 40), ("plan_sha256", "f" * 64),
    ("cheap_hard_seconds", 1801), ("main_hard_seconds", 9001),
    ("ci", {"pass": False}),
])
def test_wrong_amendment_scope_fails_without_mutation(setup, field, value):
    ctrl = setup.controller()
    amendment = {**setup.amendment, field: value}
    with pytest.raises(ValueError):
        a.apply_window(ctrl, amendment)
    assert ctrl.hard_seconds == 900 and ctrl.event("bootstrap-a1") is None
    assert setup.rig.api.calls == []


@pytest.mark.parametrize("field,value", [("freeze", "f" * 40), ("plan_hash", "f" * 64),
                                         ("hard_seconds", 1200)])
def test_wrong_runtime_identity_or_inherited_clock_rejected(setup, field, value):
    ctrl = setup.controller()
    setattr(ctrl, field, value)
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.event("bootstrap-a1") is None


@pytest.mark.parametrize("field,value", [("ORIGINAL_CLOSED_HASH", "f" * 64),
                                         ("ORIGINAL_POD", "foreign-pod"),
                                         ("ORIGINAL_COST", FAILED_COST + Decimal(".01"))])
def test_exact_original_closure_and_cost_are_required(setup, monkeypatch, field, value):
    ctrl = setup.controller()
    monkeypatch.setattr(a, field, value)
    with pytest.raises(ValueError, match="failed attempt"):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 900 and setup.rig.api.calls == []


def test_missing_original_ledger_is_not_recreated(setup):
    ctrl = setup.controller()
    path = setup.first.ledger.path
    path.unlink()
    with pytest.raises((ValueError, OSError)):
        a.apply_window(ctrl, setup.amendment)
    assert not path.exists()
    assert ctrl.hard_seconds == 900


@pytest.mark.parametrize("damage", ["bytes", "extra", "receipt", "ledger"])
def test_original_evidence_tampering_blocks_amendment(setup, damage):
    ctrl = setup.controller()
    receipt_path = setup.first.base / "final-retrieval.json"
    receipt = json.loads(receipt_path.read_bytes())
    directory = Path(receipt["data"]["directory"])
    if damage == "bytes":
        (directory / "controller.log").write_text("changed evidence")
    elif damage == "extra":
        (directory / "unexpected.json").write_text("{}")
    elif damage == "receipt":
        receipt["data"]["pod_id"] = "foreign-pod"
        receipt_path.write_text(json.dumps(receipt))
    else:
        path = setup.first.ledger.path
        path.write_bytes(path.read_bytes().replace(b'"get_status":404', b'"get_status":200'))
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 900 and setup.rig.api.calls == []


def test_carry_must_be_present_before_creation(setup):
    ctrl = setup.controller()
    prior, attempts = ctrl._prior_attempts()
    ctrl._prior_attempts = Mock(return_value=(prior / 2, attempts))
    with pytest.raises(ValueError, match="carried"):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 900


def test_cannot_first_apply_to_an_already_created_attempt(setup):
    ctrl = setup.rig.launch(setup.controller())
    assert ctrl.event("bootstrap-a1") is None
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 900 and ctrl.event("bootstrap-a1") is None


def test_conflicting_persisted_amendment_does_not_change_effective_clock(setup):
    ctrl = setup.controller()
    ctrl.ledger.bind("bootstrap-a1", {"different_amendment": True})
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 900


def test_main_cannot_adopt_original_incomplete_test_attempt(setup):
    ctrl = setup.controller("main")
    with pytest.raises(ValueError):
        a.apply_window(ctrl, setup.amendment)
    assert ctrl.hard_seconds == 9000 and setup.rig.api.calls == []


def test_main_clock_and_both_costs_survive_a_completed_replacement(setup):
    replacement = setup.complete_replacement()
    ctrl = a.apply_window(setup.controller("main"), setup.amendment)
    assert ctrl.hard_seconds == 9000
    assert ctrl.event("controller:config")["data"]["hard_seconds"] == 9000
    setup.rig.launch(ctrl)
    expected = FAILED_COST + Decimal(replacement.event("closed")["data"]["compute_upper_bound_usd"])
    intent = ctrl.event("create-intent")["data"]
    assert Decimal(intent["prior_new_usd"]) == expected
    assert old._utc(intent["hard_deadline_utc"]) - old._utc(intent["created_utc"]) == timedelta(seconds=9000)
    assert old._utc(intent["deadline_utc"]) - old._utc(intent["created_utc"]) == timedelta(seconds=8400)
    assert setup.first.ledger.path.read_bytes() == setup.original_bytes


def test_main_rejects_replacement_from_another_amendment(setup):
    setup.complete_replacement(amendment={**setup.amendment, "amendment_freeze": "d" * 40})
    setup.rig.api.calls.clear()
    with pytest.raises(ValueError, match="another amendment"):
        a.apply_window(setup.controller("main"), setup.amendment)
    assert setup.rig.api.calls == []


def test_matching_a1_record_never_waives_frozen_cheap_test_gate(setup):
    setup.complete_replacement(skipped=1)
    setup.rig.api.calls.clear()
    ctrl = a.apply_window(setup.controller("main"), setup.amendment)
    with pytest.raises(ValueError, match="without failures or skips"):
        setup.rig.launch(ctrl)
    assert setup.rig.api.calls == []


@pytest.fixture
def amendment_checkout(tmp_path, monkeypatch):
    root = tmp_path / "amendment"
    committed = {}
    for name in a.PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        committed[name] = ("synthetic amendment source: " + name + "\n").encode()
        path.write_bytes(committed[name])
    def git(argv, *, cwd, timeout):
        assert Path(cwd) == root and timeout == 30
        if argv == ["git", "rev-parse", "HEAD"]:
            return (AMENDMENT + "\n").encode()
        assert argv[:2] == ["git", "show"]
        freeze, name = argv[2].split(":", 1)
        assert freeze == AMENDMENT
        return committed[name]
    monkeypatch.setattr(a, "ROOT", root)
    monkeypatch.setattr(a.subprocess, "check_output", Mock(side_effect=git))
    return root, committed


def test_amendment_local_verification_is_exact_and_network_free(amendment_checkout):
    _, committed = amendment_checkout
    result = a.verify_amendment(AMENDMENT, network=False)
    assert result["sources"] == {name: hashlib.sha256(raw).hexdigest() for name, raw in committed.items()}
    assert result["ci"] is None and result["scientific_freeze"] == SCIENCE


@pytest.mark.parametrize("failure", ["same-freeze", "short-freeze", "wrong-head", "dirty", "symlink"])
def test_unfrozen_amendment_source_rejected(amendment_checkout, monkeypatch, failure):
    root, _ = amendment_checkout
    freeze = SCIENCE if failure == "same-freeze" else AMENDMENT
    if failure == "short-freeze":
        freeze = AMENDMENT[:7]
    elif failure == "wrong-head":
        monkeypatch.setattr(a.subprocess, "check_output", Mock(return_value=b"d" * 40 + b"\n"))
    elif failure == "dirty":
        (root / a.PATHS[0]).write_text("different source")
    elif failure == "symlink":
        path = root / a.PATHS[0]
        saved = path.with_suffix(".saved")
        path.rename(saved)
        path.symlink_to(saved)
    with pytest.raises(ValueError):
        a.verify_amendment(freeze, network=False)


def ci_responses():
    return [
        {"total_count": 1, "workflow_runs": [{"id": 37, "head_sha": AMENDMENT,
          "status": "completed", "conclusion": "success"}]},
        {"total_count": 1, "jobs": [{"name": "Bootstrap A1 / Python 3.12",
          "status": "completed", "conclusion": "success"}]},
    ]


def synthetic_opener(responses):
    return SimpleNamespace(open=Mock(side_effect=[io.BytesIO(json.dumps(r).encode()) for r in responses]))


def test_focused_ci_requires_exact_workflow_freeze_and_job(amendment_checkout):
    opener = synthetic_opener(ci_responses())
    result = a.verify_amendment(AMENDMENT, opener=opener)
    urls = [call.args[0].full_url for call in opener.open.call_args_list]
    assert "actions/workflows/steering-bootstrap-a1.yml/runs?head_sha=" + AMENDMENT in urls[0]
    assert "actions/runs/37/jobs?per_page=100" in urls[1]
    assert result["ci"]["pass"] is True and result["ci"]["run_id"] == 37


@pytest.mark.parametrize("failure", ["missing-run", "wrong-freeze", "pending-run", "failed-run",
                                     "run-pagination", "wrong-job", "failed-job", "job-pagination"])
def test_focused_ci_failures_block_authorization(amendment_checkout, failure):
    responses = ci_responses()
    run, job = responses[0]["workflow_runs"][0], responses[1]["jobs"][0]
    if failure == "missing-run":
        responses[0] = {"total_count": 0, "workflow_runs": []}
    elif failure == "wrong-freeze":
        run["head_sha"] = "d" * 40
    elif failure == "pending-run":
        run["status"] = "in_progress"
    elif failure == "failed-run":
        run["conclusion"] = "failure"
    elif failure == "run-pagination":
        responses[0]["total_count"] = 101
    elif failure == "wrong-job":
        job["name"] = "Unrelated successful job"
    elif failure == "failed-job":
        job["conclusion"] = "failure"
    else:
        responses[1]["total_count"] = 101
    with pytest.raises(ValueError):
        a.verify_amendment(AMENDMENT, opener=synthetic_opener(responses))


@pytest.mark.parametrize("action", ["monitor", "retrieve", "status", "close"])
def test_live_lifecycle_uses_bound_ci_without_github(setup, monkeypatch, action):
    first = a.apply_window(setup.controller(), setup.amendment)
    ctrl = setup.controller()
    assert ctrl.event("bootstrap-a1") == first.event("bootstrap-a1")
    local = {**setup.amendment, "ci": None}
    verify = Mock(return_value=local)
    monkeypatch.setattr(a, "verify_amendment", verify)
    monkeypatch.setattr(old.base, "RunPodV2", Mock(return_value=setup.rig.api))
    constructor = Mock(return_value=ctrl)
    monkeypatch.setattr(old, "Controller", constructor)
    operation = Mock(return_value={"synthetic": True})
    monkeypatch.setattr(ctrl, "close_until_verified" if action == "close" else action, operation)
    monkeypatch.setattr("sys.argv", ["bootstrap-a1", "--runtime-root", str(setup.rig.root),
        "--amendment-freeze", AMENDMENT, "--kind", "cheap", "--action", action, "--launch"])
    # The CLI adds only this runtime to sys.path; restore the list after the test.
    monkeypatch.setattr("sys.path", list(__import__("sys").path))
    a.main()
    verify.assert_called_once_with(AMENDMENT, network=False)
    operation.assert_called_once_with()
    assert ctrl.hard_seconds == 1800
    assert ctrl.event("bootstrap-a1")["data"]["amendment"]["ci"]["pass"] is True
    assert setup.rig.api.calls == []


def test_creation_requires_focused_ci_before_provider_construction(setup, monkeypatch):
    verify = Mock(side_effect=ValueError("focused CI missing"))
    monkeypatch.setattr(a, "verify_amendment", verify)
    provider = Mock(side_effect=AssertionError("Provider reached before CI"))
    monkeypatch.setattr(old.base, "RunPodV2", provider)
    monkeypatch.setattr("sys.argv", ["bootstrap-a1", "--runtime-root", str(setup.rig.root),
        "--amendment-freeze", AMENDMENT, "--kind", "cheap", "--action", "create", "--launch"])
    monkeypatch.setattr("sys.path", list(__import__("sys").path))
    with pytest.raises(ValueError, match="focused CI"):
        a.main()
    verify.assert_called_once_with(AMENDMENT, network=True)
    provider.assert_not_called()


def test_original_scientific_ci_still_blocks_creation(setup):
    ctrl = a.apply_window(setup.controller(), setup.amendment)
    setup.rig.ci.side_effect = ValueError("scientific CI missing")
    with pytest.raises(ValueError, match="scientific CI"):
        setup.rig.launch(ctrl)
    setup.rig.ci.assert_called_with(FREEZE)
    assert setup.rig.api.calls == [] and ctrl.event("create-intent") is None
