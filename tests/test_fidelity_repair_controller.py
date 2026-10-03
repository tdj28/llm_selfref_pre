"""Synthetic repair lifecycle tests: no provider, SSH, downloads or outcomes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import urllib.parse
from unittest.mock import Mock

import pytest

from experiments.steering_fidelity_repair import controller as c

FREEZE = "a" * 40
UTC = datetime(2026, 10, 3, tzinfo=timezone.utc)
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test-only"


def stub_protocol(monkeypatch, module):
    import experiments.steering_fidelity_repair as package
    monkeypatch.setitem(sys.modules, "experiments.steering_fidelity_repair.protocol", module)
    monkeypatch.setattr(package, "protocol", module, raising=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Network forbidden in controller tests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", fail)
    monkeypatch.setattr("socket.socket.connect", fail)


class FakeAPI:
    writable = True

    def __init__(self, clock):
        self.clock, self.calls, self.pod = clock, [], None
        self.lost_response, self.hide_pod, self.deleted = False, False, False
        self.delete_disappears = True
        self.offers = {kind: {"id": gpu, "memory": memory, "secure": True,
            "price": {"secure": str(rate)}, "availability": "LOW"}
            for kind, (gpu, rate, memory) in c.base.HARDWARE.items()}

    def inventory(self):
        self.calls.append(("GET", "/pods", None))
        return [{"id": "foreign1", "name": c.PREFIX + "main-000000000000"}] + (
            [deepcopy(self.pod)] if self.pod and not self.deleted and not self.hide_pod else [])

    def request(self, method, path, body=None):
        self.calls.append((method, path, deepcopy(body)))
        if path.startswith("/catalog/"):
            name = urllib.parse.unquote(path.split("/catalog/gpus/")[1].split("?")[0])
            return 200, next(o for o in self.offers.values() if o["id"] == name)
        if method == "POST":
            offer = next(o for o in self.offers.values() if o["id"] == body["gpu"]["id"])
            identifier = "owned" + str(sum(m == "POST" for m, _, _ in self.calls))
            self.pod = {**deepcopy(body), "id": identifier, "createdAt": self.clock().isoformat(),
                "cost": offer["price"]["secure"], "status": "RUNNING",
                "gpu": {"id": offer["id"], "count": 1, "memory": offer["memory"]},
                "ssh": {"direct": {"host": "192.0.2.1", "port": 12345, "username": "root"}}}
            self.deleted = False
            if self.lost_response:
                raise RuntimeError("Synthetic lost POST response")
            return 201, deepcopy(self.pod)
        assert self.pod and path == "/pods/" + self.pod["id"], "Foreign ID accessed"
        if method == "DELETE":
            self.deleted = self.delete_disappears
            return 204, None
        if self.deleted:
            raise c.base.ApiError(404)
        return 200, deepcopy(self.pod)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    out = root / "out" / c.NAMESPACE
    plan = root / c.PLAN_RELATIVE
    plan.parent.mkdir(parents=True)
    plan_data = {"budget": deepcopy(c.BUDGET), "counts": {
        "calibration_forwards": 520, "liveness_reserved_seconds": 900}}
    plan.write_bytes(c._canonical(plan_data))
    key = root / "key"
    key.write_text("synthetic placeholder only")
    key.with_suffix(".pub").write_text(PUBLIC_KEY)
    r = SimpleNamespace(root=root, out=out, plan=plan, plan_data=plan_data, now=UTC, ticks=0)
    r.api = FakeAPI(lambda: r.now)
    r.public, r.ci = Mock(), Mock(return_value={"pass": True})
    for module, name, value in ((c, "ROOT", root), (c, "OWNED_OUT", out),
            (c, "load_plan", lambda *_: json.loads(plan.read_bytes())),
            (c, "_require_ignored", Mock()), (c, "verify_ci", r.ci),
            (c, "sparse_paths", lambda *_: [c.PLAN_RELATIVE]),
            (c.base, "KEY", key), (c.base, "verify_public", r.public)):
        monkeypatch.setattr(module, name, value)
    monkeypatch.setenv("HF_TOKEN", "hf_placeholder_only")

    def advance(seconds):
        r.now += timedelta(seconds=seconds)
        r.ticks += seconds

    def controller(kind="cheap", attempt=1, *, authorize=True, **kwargs):
        approval = out / f"approval-{kind}-{attempt}.json"
        options = dict(launch=True, approved_new_cap_usd="15", approval_ref="synthetic-user-request",
                       approval_file=approval, attempt=attempt)
        options.update(kwargs)
        ctrl = c.Controller(plan, FREEZE, out, kind, r.api, clock=lambda: r.now,
            monotonic=lambda: r.ticks, sleep=advance, run=Mock(side_effect=AssertionError("Unexpected subprocess")),
            **options)
        ctrl.disk_check = Mock()
        if authorize:
            approval.write_bytes(c._canonical(c.approval_record(ctrl.plan_hash, FREEZE, c.BUDGET,
                "synthetic-user-request", kind=kind, attempt=attempt)))
        return ctrl

    def launch(ctrl):
        original = ctrl.start_worker
        ctrl.start_worker = Mock()
        try:
            ctrl.launch()
        finally:
            ctrl.start_worker = original
        return ctrl

    def snapshot(ctrl, files=None, *, corrupt=False, fail=False):
        files = dict(files or {"forwards/one.json": b'{"id":"one"}', "controller.log": b"progress"})
        if not ctrl.event("worker-intent"):
            ctrl.ledger.bind("worker-intent", {"worker_id": "b" * 32, "pod_id": ctrl.owned()["id"],
                "plan_sha256": ctrl.plan_hash, "freeze_commit": FREEZE})
        actions = []

        def signal(pod, action):
            assert pod["id"] == ctrl.owned()["id"]
            actions.append(action)
            if action == "stop":
                files["controller-stopped.json"] = b'{"stopped":true}'
            return {"verified": True, "action": action}

        def ssh(pod, command, **kwargs):
            assert pod["id"] == ctrl.owned()["id"]
            return c._canonical({n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()})

        def run(argv, **kwargs):
            assert argv[0] == "rsync"
            destination = Path(argv[-1])
            for name, raw in files.items():
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw + (b"corrupt" if corrupt else b""))
            return subprocess.CompletedProcess(argv, int(fail), b"", b"")

        ctrl.signal_worker, ctrl._ssh, ctrl.run = Mock(side_effect=signal), Mock(side_effect=ssh), Mock(side_effect=run)
        return actions

    def complete_cheap(attempt=1, *, failed=False, seconds=120):
        ctrl = launch(controller(attempt=attempt))
        if not failed:
            snapshot(ctrl, {"DONE-all.json": b'{"pass":true,"scope":"tiny_cuda_exact_path"}',
                "controller-exit.json": b'{"exit_code":0}',
                "tests.xml": b'<testsuites><testsuite tests="10" failures="0" errors="0" skipped="0"/></testsuites>'})
        advance(seconds)
        ctrl.terminate()
        return ctrl

    def main_started():
        complete_cheap()
        ctrl = launch(controller("main"))
        ctrl.ledger.bind("worker-intent", {"worker_id": "c" * 32, "pod_id": ctrl.owned()["id"],
            "plan_sha256": ctrl.plan_hash, "freeze_commit": FREEZE})
        ctrl.ledger.bind("worker-started", {"utc": r.now.isoformat()})
        return ctrl

    def barrier(ctrl, name="first-rows", *, timing=1):
        n = c.BARRIER_FORWARDS[name]
        value = {"barrier": name, "forwards": n, "plan_sha256": ctrl.plan_hash, "freeze_commit": FREEZE}
        files = {"WAITING-" + name + ".json": value, "_approvals": {}}
        if name == "throughput":
            ctrl.ledger.bind("approved:first-rows", {"plan_sha256": ctrl.plan_hash})
            files["_approvals"]["APPROVE-first-rows"] = ctrl.plan_hash
        directory = ctrl.base / "retrievals" / name
        directory.mkdir(parents=True)
        (directory / ("WAITING-" + name + ".json")).write_bytes(c._canonical(value))
        receipt = ctrl.record("retrieval", {"directory": str(directory), "pod_id": ctrl.owned()["id"],
                                            "artifacts": c.artifact_map(directory)})
        report = {"pass": True, "forwards": n, "forward_seconds": [timing] * n, "unresolved_forward_ids": []}
        monkeypatch.setattr(c, "audit", Mock(return_value=report))
        ctrl.status = Mock(return_value={"pod": deepcopy(r.api.pod), "files": files})
        ctrl._ssh = Mock(return_value=b"")
        return files, report, receipt

    r.advance, r.controller, r.launch, r.snapshot = advance, controller, launch, snapshot
    r.complete_cheap, r.main_started, r.barrier = complete_cheap, main_started, barrier
    return r


def test_fresh_namespace_and_corrected_transport_only():
    assert c.NAMESPACE == "steering-fidelity-repair-20261003"
    assert c.PLAN_RELATIVE == "data/steering_fidelity_repair/pilot_plan_20261003/PLAN.json"
    assert c.BARRIER_FORWARDS == {"first-rows": 5, "throughput": 20}
    assert c.Controller.signal_worker is c.CorrectedLifecycle.signal_worker
    for name in ("retrieve", "terminate", "_snapshot", "owned", "_ssh", "reconcile_create", "_register"):
        assert getattr(c.Controller, name) is getattr(c.transport.Controller, name)
    assert not hasattr(c.Controller, "decision")
    assert all("bilingual" not in p and not p.startswith("data/") for p in c.LIFECYCLE_SOURCES)


@pytest.mark.parametrize("options", [{"launch": False}, {"approved_new_cap_usd": "170"},
    {"approved_new_cap_usd": "25"}, {"approved_new_cap_usd": None},
    {"approval_file": None}, {"approval_ref": None}])
def test_authorization_precedes_all_network(rig, options):
    with pytest.raises(ValueError):
        rig.controller(**options).launch()
    assert not rig.api.calls
    rig.public.assert_not_called()


def test_missing_approval_never_written(rig):
    ctrl = rig.controller(authorize=False)
    with pytest.raises(ValueError):
        ctrl.launch()
    assert not ctrl.approval_file.exists()
    assert not rig.api.calls


def test_canonical_path_and_changed_plan_block_budget_reset(rig):
    with pytest.raises(ValueError, match="canonical"):
        c.Controller(rig.plan, FREEZE, rig.root / "elsewhere", "cheap", rig.api)
    ctrl = rig.controller()
    rig.plan.write_bytes(c._canonical({**rig.plan_data, "changed": True}))
    with pytest.raises(ValueError, match="changed"):
        ctrl.launch()
    with pytest.raises(ValueError):
        rig.controller()
    assert not rig.api.calls


def test_historical_approval_and_plan_rejected(rig):
    ctrl = rig.controller()
    approval = json.loads(ctrl.approval_file.read_bytes())
    approval["scope"] = "steering_fidelity_phase_c_only"
    ctrl.approval_file.write_bytes(c._canonical(approval))
    with pytest.raises(ValueError, match="Approval"):
        ctrl.launch()
    with pytest.raises(ValueError, match="Exact repair"):
        c._safe_path("data/steering_fidelity/calibration_plan_20261002/PLAN.json")
    assert not rig.api.calls


def test_no_adoption_before_creation(rig):
    ctrl = rig.controller()
    with pytest.raises(ValueError):
        ctrl.get_pod()
    with pytest.raises(ValueError):
        ctrl.terminate()
    assert not rig.api.calls


def test_exact_ci_gate_before_provider(rig):
    rig.ci.side_effect = ValueError("CI pending")
    with pytest.raises(ValueError):
        rig.controller().launch()
    assert not rig.api.calls


def test_sparse_dependency_preflight_before_provider(rig, monkeypatch):
    monkeypatch.setattr(c, "sparse_paths", lambda _: [c.REQUIREMENTS])
    with pytest.raises(ValueError, match="Missing sparse"):
        rig.controller().launch()
    assert not rig.api.calls


def test_intent_names_timers_and_reentry_no_repeat(rig):
    ctrl = rig.launch(rig.controller())
    intent = ctrl.event("create-intent")["data"]
    assert intent["payload"]["name"].startswith(c.PREFIX + "cheap-")
    assert intent["prior_new_usd"] == "0"
    assert intent["prior_total_usd"] == "9.657774"
    assert c._utc(intent["deadline_utc"]) == UTC + timedelta(seconds=1200)
    assert c._utc(intent["hard_deadline_utc"]) == UTC + timedelta(seconds=1800)
    assert "foreign1" in intent["blocked"]
    with pytest.raises(ValueError, match="already attempted"):
        rig.controller().launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_uncertain_post_reconciles_exact_name_once(rig):
    rig.api.lost_response = True
    ctrl = rig.launch(rig.controller())
    assert ctrl.owned()["id"] == "owned1"
    assert any(e["id"].startswith("create-reconciled:") for e in ctrl.ledger.read())
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_unresolved_post_blocks_new_attempt_without_adoption(rig):
    rig.api.lost_response = rig.api.hide_pod = True
    with pytest.raises(RuntimeError, match="unresolved"):
        rig.controller().launch()
    with pytest.raises(ValueError, match="unresolved"):
        rig.controller(attempt=2).launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_failed_startup_retry_and_historical_cost_carried_once(rig):
    first = rig.complete_cheap(failed=True)
    cost = Decimal(first.event("closed")["data"]["compute_upper_bound_usd"])
    assert cost == Decimal("120") * (Decimal("0.74") + c.base.STORAGE) / 3600
    second = rig.launch(rig.controller(attempt=2))
    intent = second.event("create-intent")["data"]
    assert Decimal(intent["prior_new_usd"]) == cost
    assert Decimal(intent["prior_total_usd"]) == c.PRIOR_USD
    rig.advance(60)
    second.terminate()
    closed = second.event("closed")["data"]
    cumulative = cost * Decimal("1.5")
    assert Decimal(closed["cumulative_gpu_upper_bound_usd"]) == cumulative
    assert Decimal(closed["new_all_in_upper_bound_usd"]) == cumulative + 3
    assert Decimal(closed["all_in_upper_bound_usd"]) == c.PRIOR_USD + cumulative + 3


def test_retry_requires_specific_new_approval(rig):
    first = rig.complete_cheap(failed=True)
    ctrl = rig.controller(attempt=2)
    ctrl.approval_file.write_bytes(first.approval_file.read_bytes())
    before = len(rig.api.calls)
    with pytest.raises(ValueError, match="Approval"):
        ctrl.launch()
    assert len(rig.api.calls) == before


def test_new_cap_does_not_subtract_historical_spend(monkeypatch):
    result = c.budget_projection("12")
    assert result["pass"]
    assert result["projected_new_usd"] == "15"
    assert result["projected_all_in_usd"] == "24.657774"
    assert not c.budget_projection("12.00001")["pass"]
    monkeypatch.setattr(c, "TOTAL_USD", Decimal("24.657773"))
    assert not c.budget_projection("12")["pass"]
    monkeypatch.setattr(c, "TOTAL_USD", Decimal("170"))
    monkeypatch.setattr(c, "NEW_CAP_USD", Decimal("14.99"))
    assert not c.budget_projection("12")["pass"]


@pytest.mark.parametrize("key,value", [("prior_usd", "0"), ("new_cap_usd", "170"),
    ("gpu_cap_usd", "15"), ("storage_reserve_usd", "0"), ("total_usd", "200"),
    ("main_seconds", 4801), ("cheap_seconds", 1801), ("reserve_seconds", 0),
    ("api_cap_usd", "1"), ("new_paid_judge_calls", 1), ("new_pro_calls", 1)])
def test_frozen_budget_cannot_expand_or_reallocate(key, value):
    with pytest.raises(ValueError, match="Repair must retain"):
        c.checked_budget({"budget": {**c.BUDGET, key: value}})


def test_full_cheap_and_main_lifetimes_fit_new_budget():
    cheap = (c.base.HARDWARE["cheap"][1] + c.base.STORAGE) * c.CHEAP_SECONDS / 3600
    main = (c.base.HARDWARE["main"][1] + c.base.STORAGE) * c.MAIN_SECONDS / 3600
    assert c.budget_projection(cheap + main)["pass"]
    assert c.MAIN_SECONDS == 4800 and c.CHEAP_SECONDS == 1800 and c.RESERVE_SECONDS == 600


def test_failed_attempt_reduces_later_headroom(rig, monkeypatch):
    rig.complete_cheap(failed=True)
    full = (Decimal(".74") + c.base.STORAGE) * c.CHEAP_SECONDS / 3600
    full += (Decimal("6.79") + c.base.STORAGE) * c.MAIN_SECONDS / 3600
    monkeypatch.setattr(c, "GPU_CAP_USD", full)
    with pytest.raises(ValueError, match="Failed attempts"):
        rig.controller(attempt=2).launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_main_requires_passing_cheap_and_get404(rig):
    ctrl = rig.controller("main")
    with pytest.raises(ValueError, match="cheap CUDA"):
        ctrl.launch()
    assert not rig.api.calls
    rig.complete_cheap(failed=True)
    with pytest.raises((ValueError, FileNotFoundError)):
        ctrl.launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 1


def test_main_combines_cheap_cost_and_native_b200(rig):
    cheap = rig.complete_cheap()
    ctrl = rig.launch(rig.controller("main"))
    intent = ctrl.event("create-intent")["data"]
    assert intent["prior_new_usd"] == cheap.event("closed")["data"]["compute_upper_bound_usd"]
    assert intent["prior_total_usd"] == "9.657774"
    assert intent["payload"]["gpu"]["id"] == "NVIDIA B200"
    assert rig.api.pod["gpu"]["memory"] == 180
    assert c._utc(intent["hard_deadline_utc"]) - c._utc(intent["created_utc"]) == timedelta(seconds=4800)
    assert c._utc(intent["deadline_utc"]) - c._utc(intent["created_utc"]) == timedelta(seconds=4200)


def test_main_cannot_rerun_after_dispatch(rig, monkeypatch):
    ctrl = rig.main_started()
    rig.snapshot(ctrl)
    monkeypatch.setattr(c, "audit", Mock(side_effect=ValueError("partial failed")))
    ctrl.terminate()
    assert ctrl.event("final-structural-audit")["data"]["status"] == "failed"
    with pytest.raises(ValueError, match="cannot be rerun"):
        rig.controller("main", attempt=2).launch()
    assert sum(m == "POST" for m, _, _ in rig.api.calls) == 2


def test_cost_drift_and_clock_rollback_fail(rig):
    ctrl = rig.launch(rig.controller())
    ctrl.cost_check(rig.api.pod)
    for change in ({"cost": None}, {"cost": ".75"}, {"image": "other"}, {"id": "foreign1"}):
        with pytest.raises(ValueError):
            ctrl.cost_check({**rig.api.pod, **change})
    rig.advance(60)
    ctrl.cost_check(rig.api.pod)
    rig.advance(-1)
    with pytest.raises(ValueError, match="backward"):
        ctrl.cost_check(rig.api.pod)


def test_restart_keeps_elapsed_and_retrieval_deadline(rig):
    ctrl = rig.launch(rig.controller())
    rig.advance(1000)
    ctrl.cost_check(rig.api.pod, 30)
    restarted = rig.controller()
    assert restarted._elapsed(restarted.event("create-intent")["data"]) >= 1000
    rig.advance(140)
    with pytest.raises(ValueError, match="deadline"):
        restarted.cost_check(rig.api.pod)


def test_worker_single_dispatch_and_only_hf_credential(rig):
    ctrl = rig.launch(rig.controller())
    ctrl._ssh = Mock(return_value=b"")
    ctrl.start_worker()
    transfer = ctrl._ssh.call_args_list[1]
    assert transfer.kwargs["data"] == b"export HF_TOKEN=''\n"
    dispatch = ctrl._ssh.call_args_list[-1].args[1]
    assert "RUNPOD_API_KEY" not in dispatch and "OPENAI_API_KEY" not in dispatch
    assert ctrl.event("worker-intent")["data"]["seconds"] == 1200
    with pytest.raises(ValueError):
        ctrl.start_worker()


def test_snapshot_pause_resume_and_corruption_blocks_delete(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl, corrupt=True)
    with pytest.raises(ValueError, match="hashes"):
        ctrl.retrieve()
    assert actions == ["pause", "resume"]
    with pytest.raises(ValueError):
        ctrl.terminate()
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_retrieval_failure_resumes_worker(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl, fail=True)
    with pytest.raises(RuntimeError):
        ctrl.retrieve()
    assert actions == ["pause", "resume"]


def test_final_addition_after_snapshot_prevents_delete(rig):
    ctrl = rig.launch(rig.controller())
    rig.snapshot(ctrl)
    receipt = ctrl.retrieve(final=True)
    (Path(receipt["data"]["directory"]) / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        ctrl.terminate()
    assert not any(m == "DELETE" for m, _, _ in rig.api.calls)


def test_delete_requires_snapshot_then_exact_get404(rig):
    ctrl = rig.launch(rig.controller())
    actions = rig.snapshot(ctrl)
    rig.advance(100)
    result = ctrl.terminate()
    assert actions == ["stop"]
    assert result["data"]["get_status"] == 404 and result["data"]["within_limits"]
    assert (ctrl.base / "final-retrieval.json").is_file()
    assert rig.api.calls[-3:] == [("DELETE", "/pods/owned1", None), ("GET", "/pods/owned1", None), ("GET", "/pods", None)]


def test_unverified_delete_never_repeated(rig):
    ctrl = rig.launch(rig.controller())
    rig.api.delete_disappears = False
    for _ in range(2):
        with pytest.raises(ValueError, match="Deletion unverified"):
            ctrl.terminate()
    assert sum(m == "DELETE" for m, _, _ in rig.api.calls) == 1
    rig.api.deleted = True
    assert ctrl.terminate()["data"]["get_status"] == 404


def test_cleanup_retry_accounts_time_and_reports_overrun(rig):
    ctrl = rig.launch(rig.controller())
    original = ctrl.terminate
    ctrl.terminate = Mock(side_effect=[RuntimeError("retrieval failed"), RuntimeError("retry"), None])
    rig.advance(1801)
    assert ctrl.close_until_verified() is None
    rows = [e for e in ctrl.ledger.read() if e["id"].startswith("cleanup-retry:")]
    assert len(rows) == 2 and all(e["data"]["hard_deadline_exceeded"] for e in rows)
    ctrl.terminate = original
    assert ctrl.terminate()["data"]["within_limits"] is False


@pytest.mark.parametrize("name", c.BARRIERS)
def test_approval_requires_owned_retrieved_audited_fixed_batch(rig, name):
    ctrl = rig.main_started()
    rig.advance(1000)
    rig.barrier(ctrl, name)
    with pytest.raises(ValueError):
        ctrl.approve(name, "0" * 64)
    assert not ctrl._ssh.called
    result = ctrl.approve(name, ctrl.plan_hash)
    assert result["data"]["plan_sha256"] == ctrl.plan_hash
    assert ctrl._ssh.call_args.kwargs["data"] == (ctrl.plan_hash + "\n").encode()
    if name == "throughput":
        assert any(e["id"].startswith("throughput-gate:") and e["data"]["pass"] for e in ctrl.ledger.read())


@pytest.mark.parametrize("bad", ["pass", "count", "binding", "timing", "unresolved", "bytes"])
def test_bad_initial_rows_never_release(rig, bad):
    ctrl = rig.main_started()
    rig.advance(1000)
    files, report, receipt = rig.barrier(ctrl)
    if bad == "pass":
        report["pass"] = False
    elif bad == "count":
        report["forwards"] = 4
    elif bad == "binding":
        files["WAITING-first-rows.json"]["freeze_commit"] = "f" * 40
    elif bad == "timing":
        report["forward_seconds"][0] = 0
    elif bad == "unresolved":
        report["unresolved_forward_ids"] = ["unknown"]
    else:
        (Path(receipt["data"]["directory"]) / "WAITING-first-rows.json").write_text("{}")
    with pytest.raises(ValueError):
        ctrl.approve("first-rows", ctrl.plan_hash)
    assert not ctrl._ssh.called


def test_throughput_cannot_skip_first_rows(rig):
    ctrl = rig.main_started()
    rig.advance(1000)
    files, _, _ = rig.barrier(ctrl, "throughput")
    files["_approvals"].clear()
    with pytest.raises(ValueError, match="Initial real rows"):
        ctrl.approve("throughput", ctrl.plan_hash)


def test_slow_20_forward_gate_permanently_blocks_bulk(rig):
    ctrl = rig.main_started()
    rig.advance(1000)
    _, report, _ = rig.barrier(ctrl, "throughput", timing=10)
    with pytest.raises(ValueError, match="no longer fits"):
        ctrl.approve("throughput", ctrl.plan_hash)
    report["forward_seconds"] = [1] * 20
    with pytest.raises(ValueError, match="permanent"):
        ctrl.approve("throughput", ctrl.plan_hash)
    assert not ctrl._ssh.called


def projection(timings=None, **kwargs):
    options = dict(total_forwards=520, elapsed_seconds=1000, hourly_usd="6.89",
                   prior_gpu_usd="1", liveness_reserved_seconds=900)
    options.update(kwargs)
    return c.conservative_projection([1] * 20 if timings is None else timings, **options)


def test_throughput_includes_prior_startup_reserve_and_30_percent():
    result = projection()
    lifetime = Decimal("1000") + Decimal("1.30") * 500 + 900 + 600
    assert Decimal(result["projected_lifetime_seconds"]) == lifetime
    gpu = 1 + lifetime * Decimal("6.89") / 3600
    assert Decimal(result["projected_gpu_usd"]) == gpu
    assert Decimal(result["projected_all_in_usd"]) == c.PRIOR_USD + gpu + 3
    assert result["projected_full_forced_forward_seconds"] == "520"
    assert result["liveness_reserved_seconds"] == 900
    assert "not measured" in result["liveness_projection"]
    assert result["pass"]


def test_choice_prefix_projects_every_conditional_forward_before_decode():
    result = projection([".1"] * 10 + [".3"] * 10)
    assert Decimal(result["choice_mean_seconds"]) == Decimal(".2")
    assert Decimal(result["remaining_forward_seconds"]) == Decimal(".2") * 500
    assert Decimal(result["projected_full_forced_forward_seconds"]) == Decimal(".2") * 520
    assert Decimal(result["projected_lifetime_seconds"]) == 1000 + Decimal("1.30") * 100 + 900 + 600


@pytest.mark.parametrize("timings", [[1] * 19, [1] * 21, [1] * 200, [0] * 20,
                                    [float("nan")] * 20, [-1] * 20, [51] * 20])
def test_invalid_choice_timing_fails_closed(timings):
    with pytest.raises(ValueError):
        projection(timings)


@pytest.mark.parametrize("count", [None, True, 400, 448, 519, 521, 520.0])
def test_projection_always_budgets_maximum_conditional_work(count):
    with pytest.raises(ValueError):
        projection(total_forwards=count)


@pytest.mark.parametrize("reserve", [None, 0, 450, 899, 900.0, True, 1800])
def test_liveness_allowance_must_be_frozen_900_seconds(reserve):
    with pytest.raises(ValueError):
        projection(liveness_reserved_seconds=reserve)


def test_lifetime_gate_is_strict_even_when_dollars_fit():
    assert projection(elapsed_seconds=2649, prior_gpu_usd=0)["pass"]
    at_limit = projection(elapsed_seconds=2650, prior_gpu_usd=0)
    assert Decimal(at_limit["projected_lifetime_seconds"]) == 4800
    assert Decimal(at_limit["projected_gpu_usd"]) < 12
    assert not at_limit["pass"]


@pytest.mark.parametrize("count", [0, 368, 448, 520])
def test_final_audit_accepts_conditional_inventories_not_exact_520(rig, monkeypatch, count):
    ctrl = rig.main_started()
    rig.snapshot(ctrl, {"complete.json": b'{"complete":true}', "controller-exit.json": b'{"exit_code":0}'})
    report = {"pass": True, "complete": True, "forwards": count,
              "forward_seconds": [1] * count, "unresolved_forward_ids": []}
    monkeypatch.setattr(c, "audit", Mock(return_value=report))
    result = ctrl.terminate()
    final = ctrl.event("final-structural-audit")["data"]
    assert final["status"] == "audited" and final["report"] == report
    assert result["data"]["get_status"] == 404


def test_audit_cannot_expand_maximum_inventory(rig):
    ctrl = rig.main_started()
    _, report, receipt = rig.barrier(ctrl)
    report.update(forwards=521, forward_seconds=[1] * 521)
    with pytest.raises(ValueError, match="forward audit"):
        ctrl._audit_receipt(receipt)


def test_audit_uses_fresh_signature_and_leaves_conditional_completeness_to_auditor(monkeypatch):
    fake = Mock(return_value={"pass": True, "complete": True, "forwards": 448})
    module = SimpleNamespace(audit_raw_window=fake)
    monkeypatch.setitem(sys.modules, "experiments.steering_fidelity_repair.audit", module)
    plan = {"counts": {"calibration_forwards": 520}}
    assert c.audit(Path("synthetic"), plan, "b" * 64, FREEZE)["forwards"] == 448
    fake.assert_called_once_with(Path("synthetic"), plan, "b" * 64, FREEZE, partial=True)


def test_monitor_startup_no_progress_bounded(rig):
    ctrl = rig.main_started()
    ctrl.status = Mock(return_value={"pod": deepcopy(rig.api.pod), "files": {}})
    ctrl.retrieve = Mock()
    ctrl.close_until_verified = Mock(return_value="closed")
    assert ctrl.monitor() == "closed"
    assert rig.ticks <= 120 + c.STARTUP_STALL_SECONDS + 30


def test_barrier_heartbeat_does_not_extend_wait(rig):
    ctrl = rig.main_started()
    _, _, receipt = rig.barrier(ctrl)
    original_status = ctrl.status

    def status():
        state = original_status()
        state["files"]["_progress"] = {"progress.json": [rig.ticks, rig.ticks]}
        return state
    ctrl.status = status
    ctrl.retrieve = Mock(return_value=receipt)
    ctrl.close_until_verified = Mock(return_value="closed")
    assert ctrl.monitor() == "closed"
    assert rig.ticks <= 120 + c.BARRIER_WAIT_SECONDS + 30


def test_sparse_worker_contract_shell_and_no_external_audits(monkeypatch):
    stub_protocol(monkeypatch, SimpleNamespace(source_paths=lambda: []))
    plan = {"input_hashes": {"data/steering_fidelity_repair/input.json": "b" * 64}}
    for kind in ("cheap", "main"):
        script = c.worker_script(kind, c.PLAN_RELATIVE, FREEZE, UTC.isoformat(), plan)
        subprocess.run(["bash", "-n"], input=script.encode(), capture_output=True, check=True)
        assert script.index("sparse-checkout set --no-cone") < script.index("git checkout --detach")
        assert "--no-checkout" in script and "--filter=blob:none" in script
        assert "test -f " + c.REQUIREMENTS in script
        assert "-m pip install -r " + c.REQUIREMENTS in script
        assert "jlens" not in script.lower() and "bilingual" not in script
        assert "APPROVE" not in script and "RUNPOD_API_KEY" not in script
        assert "scaling" not in script and "agent-skill-documents" not in script
        assert "experiments.steering_fidelity_repair.controller import load_plan" in script
        if kind == "cheap":
            assert "BERG_TEST_DEVICE=cuda" in script
            assert "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1" in script
            assert all(p in script for p in c.TESTS)
        else:
            assert "experiments.steering_fidelity_repair.runner" in script
            assert all(arg in script for arg in ("--plan", "--freeze", "--out", "--cache", "--deadline-utc"))
    compile(c.STATUS_SCRIPT, "status", "exec")


def test_cheap_tests_cover_repair_and_position_cuda_fixture():
    expected = {"tests/test_fidelity_repair_" + name + ".py" for name in
                ("items", "pressure_gate", "protocol", "runner", "audit", "controller", "liveness", "analysis")}
    expected |= {"tests/test_fidelity_position_probe.py", "tests/test_steering_fidelity_backend.py"}
    assert set(c.TESTS) == expected and len(c.TESTS) == len(expected)
    position = (c.ROOT / "tests/test_fidelity_position_probe.py").read_text()
    backend = (c.ROOT / "tests/test_steering_fidelity_backend.py").read_text()
    assert "from tests.test_steering_fidelity_backend import tiny" in position
    assert 'os.environ.get("BERG_TEST_DEVICE", "cpu")' in backend
    assert "torch.cuda.is_bf16_supported()" in backend


def test_sparse_lifecycle_imports_without_original_checkout(tmp_path):
    paths = [*c.LIFECYCLE_SOURCES, "experiments/steering_fidelity_repair/controller.py"]
    for name in paths:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(c.ROOT / name, destination)
    code = ("import sys; sys.path.insert(0," + repr(str(tmp_path)) + "); "
            "from experiments.steering_fidelity_repair import controller; "
            "assert controller.NAMESPACE == 'steering-fidelity-repair-20261003'")
    subprocess.run([sys.executable, "-I", "-B", "-c", code], cwd=tmp_path,
                   check=True, capture_output=True, timeout=30)


def status_output(path):
    script = c.STATUS_SCRIPT.replace(repr(c.REMOTE + "/out"), repr(str(path)))
    result = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True)
    return json.loads(result.stdout)


def test_status_ignores_heartbeat_chatter(tmp_path):
    for name in ("progress.json", "receipts.jsonl", "controller.log"):
        (tmp_path / name).write_text("{}")
    assert status_output(tmp_path)["_progress"] == {}


def test_scientific_complete_waits_for_worker_exit(tmp_path):
    (tmp_path / "complete.json").write_text('{"pass":true}')
    assert not any(name in status_output(tmp_path) for name in c.base.TERMINAL)
    (tmp_path / "controller-exit.json").write_text('{"exit_code":0}')
    assert status_output(tmp_path)["controller-exit.json"] == {"exit_code": 0}


def test_all_choice_teacher_and_generation_artifacts_are_progress(tmp_path):
    directory = tmp_path / "forwards"
    directory.mkdir()
    for task in ("choice", "teacher", "generation"):
        (directory / (task + ".json")).write_bytes(b"{}")
    assert status_output(tmp_path)["_progress"] == {"forwards/": {"files": 3, "bytes": 6}}


def test_source_paths_covers_lifecycle_tests_and_adapter():
    assert set(c.LIFECYCLE_SOURCES) | set(c.TESTS) <= set(c.source_paths())
    assert "experiments/steering_fidelity_repair/controller.py" in c.source_paths()
    assert all((c.ROOT / p).is_file() for p in c.LIFECYCLE_SOURCES)
    assert sum((c.ROOT / p).stat().st_size for p in c.LIFECYCLE_SOURCES) < 400_000
    assert not any(p.startswith("data/") for p in c.source_paths())


def test_inspect_is_offline_and_does_not_create_ledger(rig, capsys):
    c.main(["--plan", str(rig.plan), "--freeze", FREEZE, "--kind", "main", "--action", "inspect"])
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] and result["network_calls"] == 0
    assert result["creation_authorized"] is False
    assert result["budget"]["new_cap_usd"] == "15"
    assert result["budget"]["prior_usd"] == "9.657774"
    assert not rig.api.calls and not rig.out.exists()


@pytest.mark.parametrize("path", ["../escape.py", "data/", "/absolute.py", ".env", "cache/weights.json"])
def test_sparse_paths_reject_unsafe_payload(monkeypatch, path):
    stub_protocol(monkeypatch, SimpleNamespace(source_paths=lambda: [path]))
    with pytest.raises(ValueError):
        c.sparse_paths({})


@pytest.mark.parametrize("counts", [{"calibration_forwards": 400}, {"calibration_forwards": True},
    {"liveness_reserved_seconds": 899}, {"liveness_reserved_seconds": 900.0}])
def test_load_plan_rejects_underbudgeted_or_untyped_counts(monkeypatch, counts):
    plan = {"budget": deepcopy(c.BUDGET), "counts": {
        "calibration_forwards": 520, "liveness_reserved_seconds": 900, **counts}}
    stub_protocol(monkeypatch, SimpleNamespace(ROOT=c.ROOT, BUDGET=c.BUDGET, load_plan=lambda *_: plan))
    with pytest.raises(ValueError, match="520 possible forwards"):
        c.load_plan("synthetic", FREEZE)


def test_load_plan_verifies_lifecycle_hashes(monkeypatch, tmp_path):
    root = tmp_path.resolve()
    source = root / "controller.py"
    source.write_text("# synthetic\n")
    plan = {"budget": deepcopy(c.BUDGET), "counts": {
        "calibration_forwards": 520, "liveness_reserved_seconds": 900},
        "source_hashes": {"controller.py": c.sha(source)}}
    monkeypatch.setattr(c, "ROOT", root)
    monkeypatch.setattr(c, "source_paths", lambda: ["controller.py"])
    stub_protocol(monkeypatch, SimpleNamespace(ROOT=root, BUDGET=c.BUDGET, load_plan=lambda *_: plan))
    assert c.load_plan("synthetic", FREEZE) == plan
    source.write_text("# changed\n")
    with pytest.raises(ValueError, match="source binding differs"):
        c.load_plan("synthetic", FREEZE)
    plan["source_hashes"].clear()
    with pytest.raises(ValueError, match="omits lifecycle"):
        c.load_plan("synthetic", FREEZE)


@pytest.mark.parametrize("bad", [None, "sha", "pending", "failed", "missing", "pagination"])
def test_hosted_ci_requires_exact_commit_and_all_checks(bad):
    run = {"head_sha": FREEZE, "status": "completed", "conclusion": "success", "id": 42}
    names = ["Public release boundary"] + [label + " / Python " + version for label in
             ("Tests", "Current paper evidence", "Compile tracked sources") for version in ("3.10", "3.12")]
    jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in names]
    if bad == "sha":
        run["head_sha"] = "f" * 40
    elif bad == "pending":
        run["status"] = "in_progress"
    elif bad == "failed":
        jobs[-1]["conclusion"] = "failure"
    elif bad == "missing":
        jobs.pop()
    responses = [{"workflow_runs": [run], "total_count": 2 if bad == "pagination" else 1},
                 {"jobs": jobs, "total_count": len(jobs)}]
    opener = Mock()
    opener.open.side_effect = [io.BytesIO(c._canonical(value)) for value in responses]
    if bad is not None:
        with pytest.raises(ValueError):
            c.verify_ci(FREEZE, opener=opener)
    else:
        assert c.verify_ci(FREEZE, opener=opener) == {
            "freeze_commit": FREEZE, "run_id": 42, "jobs": 7, "pass": True}


def test_live_cli_needs_launch_and_has_no_stage_t():
    with pytest.raises(SystemExit):
        c.main(["--freeze", FREEZE, "--kind", "main", "--action", "create"])
    with pytest.raises(SystemExit):
        c.main(["--freeze", FREEZE, "--kind", "test", "--action", "inspect"])
