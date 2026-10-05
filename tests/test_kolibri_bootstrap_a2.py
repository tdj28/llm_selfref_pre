"""Synthetic local fixtures; never providers, credentials, SSH or CUDA calls."""
from copy import deepcopy
from decimal import Decimal
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
from unittest.mock import Mock

import pytest

from experiments.kolibri_bootstrap_a2 import adapter as a, production as p
from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_swap import bootstrap, protocol, production as old, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_swap_production import (NOW, FREEZE, PLAN_HASH, saved_controller,
    tree_hashes, write)
from tests.test_kolibri_swap_runtime import senders
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval

CARRY = "0.20653345641250872666666667"


@pytest.mark.parametrize("kind", ["cheap", "main"])
def test_worker_delta_is_only_path_and_bounded_tool_checks(kind):
    original = bootstrap.worker_script(kind, FREEZE, protocol.PLAN, 1200)
    result = a.worker_script(kind, FREEZE, protocol.PLAN, 1200)
    addition = ('export PATH="/workspace/kolibri/venv/bin:$PATH"\n'
                + shlex.join(["/workspace/kolibri/venv/bin/python", "-c", a.tool_preflight()]) + "\n")
    assert result.count(addition) == 1 and result.replace(addition, "") == original
    assert result.index("pip install --require-hashes") < result.index(addition)
    target = "-m experiments.kolibri_swap.gpu_smoke" if kind == "cheap" else "/venv/bin/vllm serve"
    assert result.index(addition) < result.index(target)
    assert subprocess.run(["bash", "-n"], input=result, text=True, capture_output=True).returncode == 0


@pytest.mark.parametrize("mode", ["pass", "custom_banner", "stderr_banner", "wrong_ninja", "missing_nvcc",
                                 "wrong_distribution", "missing_distribution", "empty_banner", "timeout", "nonzero"])
def test_tool_preflight_records_tools_or_fails_before_cuda(monkeypatch, capsys, mode):
    import importlib.metadata
    import shutil
    prefix = Path(sys.executable).parent
    banner = "unrelated executable banner" if mode == "custom_banner" else "1.13.2.g7659b.kitware.jobserver-pipe-1"
    def version(name):
        assert name == "ninja"
        if mode == "missing_distribution":
            raise importlib.metadata.PackageNotFoundError(name)
        return "1.13.1" if mode == "wrong_distribution" else "1.13.2"
    def which(name):
        if mode == "wrong_ninja" and name == "ninja":
            return "/synthetic/system/ninja"
        if mode == "missing_nvcc" and name == "nvcc":
            return None
        return str(prefix/name) if name == "ninja" else "/synthetic/toolchain/" + name
    def run(command, **kwargs):
        assert kwargs == {"check": True, "capture_output": True, "text": True, "timeout": 20}
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 20)
        if mode == "nonzero":
            raise subprocess.CalledProcessError(1, command)
        value = banner if command[0].endswith("ninja") else "synthetic version"
        if mode == "empty_banner":
            value = ""
        return Mock(stdout="" if mode == "stderr_banner" else value + "\n",
                    stderr=value + "\n" if mode == "stderr_banner" else "")
    monkeypatch.setattr(importlib.metadata, "version", version)
    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=run))
    if mode in {"pass", "custom_banner", "stderr_banner"}:
        exec(compile(a.tool_preflight(), "<synthetic-preflight>", "exec"), {})
        result = json.loads(capsys.readouterr().out)
        assert result["schema"] == "kolibri-build-tools-v1"
        assert set(result["tools"]) == {"ninja", "nvcc", "c++"}
        assert result["tools"]["ninja"]["path"] == str(prefix/"ninja")
        assert result["tools"]["ninja"]["distribution_version"] == "1.13.2"
        assert result["tools"]["ninja"]["version"] == banner
        assert subprocess.run.call_count == 3
    else:
        with pytest.raises((RuntimeError, subprocess.SubprocessError, importlib.metadata.PackageNotFoundError)):
            exec(compile(a.tool_preflight(), "<synthetic-preflight>", "exec"), {})
        if mode in {"wrong_ninja", "wrong_distribution", "missing_distribution"}:
            subprocess.run.assert_not_called()


def test_predecessor_preserves_exact_costs_and_rounds_only_admission_up(tmp_path, monkeypatch):
    root = tmp_path / "a1"
    directory = root / "controller/cheap/retrievals/synthetic"
    write(directory / "gpu-smoke.json", {"status": "failed", "scientific_generation": False,
                                         "parser": {"official_passed": 70}})
    write(directory / "exit.json", {"exit_code": 1})
    (directory / "worker.log").write_text("FileNotFoundError: [Errno 2] No such file or directory: 'ninja'\n")
    write(root / "controller/cheap/final-retrieval.json", {"data": {"directory": str(directory)}})
    write(root / "controller/cheap/events.jsonl", {"synthetic": "bound failure"})
    monkeypatch.setattr(a1, "root", lambda: root)
    monkeypatch.setattr(a, "A1_WORKER_SHA", protocol.sha(directory / "worker.log"))
    receipt = {"cost_usd": "0.1258143659791753933333333333", "closed_sha256": a.A1_CLOSED_SHA,
               "retrieval_sha256": a.A1_RETRIEVAL_SHA}
    monkeypatch.setattr(old, "closed_receipt", lambda *args: deepcopy(receipt))
    monkeypatch.setattr(old, "controller_events", lambda *args: ([], {"closed": {"data": {"pod_id": a.FAILED_POD}}}))
    first = {"predecessor": {"cost_usd": "0.08071909043333333333333333333"}}
    result = a.predecessor(first)
    assert result["exact_sum_usd"] == "0.20653345641250872666666666663"
    assert result["cost_usd"] == CARRY
    assert result["attempts"][0] == first["predecessor"]
    assert result["attempts"][1]["cost_usd"] == receipt["cost_usd"]
    assert Decimal(result["cost_usd"]) >= Decimal(result["exact_sum_usd"])
    receipt["closed_sha256"] = "0"*64
    with pytest.raises(Halted, match="preserved"):
        a.predecessor(first)


@pytest.fixture
def repair(tmp_path, monkeypatch):
    original_bytes = (protocol.ROOT / protocol.PLAN).read_bytes()
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    repo, root = tmp_path / "repo", tmp_path / "run/bootstrap-a2"
    source = repo / "repair.py"
    source.parent.mkdir()
    source.write_text("# Synthetic A2 binding\n")
    (repo / "a1.py").write_text("# Synthetic immutable A1 dependency\n")
    (repo / protocol.PLAN).parent.mkdir(parents=True)
    (repo / protocol.PLAN).write_bytes(original_bytes)
    amendment = {"source_hashes": {"repair.py": protocol.sha(source)},
                 "dependency_source_hashes": {"a1.py": protocol.sha(repo / "a1.py")},
                 "predecessor": {"cost_usd": CARRY}}
    write(repo / a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    return plan, root, amendment


def bind_controllers(root):
    for kind in ("cheap", "main"):
        ledger = saved_controller(root, kind, closed=kind == "cheap")
        ledger.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT)})


def test_reuses_a1_status_logic_without_global_changes():
    assert a.Controller.status is a1.Controller.status
    assert a.Controller.cost_check is a1.Controller.cost_check
    assert a.Controller.cheap_pass is a1.Controller.cheap_pass


def test_new_owned_attempt_preserves_both_predecessors_and_deletes(repair, monkeypatch):
    plan, root, amendment = repair
    for name in ("controller", "bootstrap-a1/controller"):
        write(root.parent / name / "cheap/events.jsonl", {"synthetic": "preserved"})
    before = {name: tree_hashes(root.parent / name) for name in ("controller", "bootstrap-a1/controller")}
    clock = Clock()
    class CheapAPI(FakeAPI):
        def request(self, method, path, body=None):
            status, value = super().request(method, path, body)
            if method == "POST":
                self.pod["cost"] = value["cost"] = ".74"
            return status, value
    api = CheapAPI(clock)
    monkeypatch.setattr(a, "verify", lambda freeze: amendment)
    monkeypatch.setattr(protocol, "verify", lambda path: plan)
    monkeypatch.setattr(a.old, "canonical_root", lambda: root.parent)
    monkeypatch.setattr(a.old, "quote", lambda api, kind: {"hourly_rate_usd": ".74", "storage_hourly_usd": ".10"})
    monkeypatch.setattr(a.old.urllib.request, "urlopen", lambda *args, **kwargs:
                        io.BytesIO((protocol.ROOT / protocol.PLAN).read_bytes()))
    key = protocol.ROOT / "synthetic-key"
    key.write_text("synthetic fixture, not a credential")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA synthetic")
    monkeypatch.setattr(a.old.base, "KEY", key)
    ctl = a.Controller(FREEZE, "cheap", api, clock=clock, sleep=clock.sleep)
    assert ctl.base == root / "controller/cheap"
    for pod in (a.FAILED_POD, a1.FAILED_POD):
        assert not ctl._new_pod({"id": pod}, {})
    ctl._ssh = Mock(side_effect=lambda pod, command, **kw: b"ready" if command == "printf ready" else b"dispatched")
    ctl.launch()
    upload = next(call.kwargs["data"] for call in ctl._ssh.call_args_list if "data" in call.kwargs)
    assert b'export PATH="/workspace/kolibri/venv/bin:$PATH"' in upload
    assert ctl.event("worker-intent")["data"]["sha256"] == a.hashlib.sha256(upload).hexdigest()
    assert api.calls.count(("POST", "/pods")) == 1
    with pytest.raises(ValueError, match="already attempted"):
        ctl.launch()
    saved_retrieval(ctl)
    clock.sleep(60)
    closed = ctl.terminate()
    assert closed["data"]["get_status"] == 404
    assert Decimal(closed["data"]["compute_upper_bound_usd"]) + Decimal(CARRY) < Decimal("1.25")
    assert api.calls[-1] == ("GET", "/pods/kolibri-owned-1")
    assert before == {name: tree_hashes(root.parent / name) for name in before}


@pytest.mark.parametrize("spent,accept", [(".80", True), (".90", False)])
def test_both_failures_count_in_live_cleanup_reserve(monkeypatch, spent, accept):
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = "cheap", {"predecessor": {"cost_usd": CARRY}}
    monkeypatch.setattr(a.old.Controller, "cost_check", lambda *args: Decimal(spent))
    if accept:
        assert ctl.cost_check({"cost": ".74"}) == Decimal(spent)
    else:
        with pytest.raises(Halted, match="Cumulative cheap"):
            ctl.cost_check({"cost": ".74"})


def test_production_fixed_fixtures_guard_and_forecast_include_both_costs(repair):
    plan, root, amendment = repair
    bind_controllers(root)
    local, judge, generated, judged = senders()
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", FREEZE, PLAN_HASH) as receipts:
        runner = p.Runner(plan, FREEZE, PLAN_HASH, ledger, receipts, local, judge, amendment=amendment)
        runner.guard = a.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, amendment=amendment, clock=lambda: NOW)
        original = old.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, clock=lambda: NOW)
        assert runner.guard.state()["gpu_usd"] == original.state()["gpu_usd"] + Decimal(CARRY)
        assert old.phase(runner, "fixtures", root)["pass"]
        assert len(generated) == 1 and len(judged) == 24 and runner.audit()["calls"] == 25
        measured = Mock()
        measured.main_admission.return_value = {"main_seconds_with_margin": "600"}
        runner.guard.admission(measured)
        assert Decimal(measured.main_admission.call_args.kwargs["gpu_spent_usd"]) == runner.guard.state()["gpu_usd"]
        (protocol.ROOT / "a1.py").write_text("# Changed dependency\n")
        with pytest.raises(Halted, match="Technical repair changed"):
            runner.generate_blocks("screen", initial=True)


@pytest.mark.parametrize("mutation", ["carry", "binding", "failed_smoke"])
def test_main_guard_rejects_overrun_foreign_or_failed_cheap(repair, mutation):
    plan, root, amendment = repair
    bind_controllers(root)
    if mutation == "carry":
        amendment = deepcopy(amendment)
        amendment["predecessor"]["cost_usd"] = "1.01"
    elif mutation == "binding":
        write(protocol.ROOT / a.AMENDMENT, {"synthetic": "different binding"})
    else:
        path = root / "controller/cheap/retrievals/synthetic/gpu-smoke.json"
        value = old.load(path)
        value["status"] = "failed"
        write(path, value)
    with Ledger(root / "judges", cap="45", screen_cap="10") as ledger:
        with pytest.raises(Halted):
            a.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, amendment=amendment, clock=lambda: NOW)


def test_candidate_never_writes_scientific_or_technical_plan(monkeypatch):
    original = (protocol.ROOT / protocol.PLAN).read_bytes()
    monkeypatch.setattr(a, "predecessor", lambda prior: {"cost_usd": CARRY, "synthetic": True})
    result = a.build()
    assert result["science_changed"] is result["smoke_computation_changed"] is False
    assert result["cheap_remaining_usd"] == str(Decimal("1.25") - Decimal(CARRY))
    assert (protocol.ROOT / protocol.PLAN).read_bytes() == original
    assert not set(result["source_hashes"]) & (set(result["dependency_source_hashes"]) |
                                             set(protocol.verify(protocol.ROOT / protocol.PLAN)["source_hashes"]))


def test_amendment_tamper_fails_before_pushed_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    write(tmp_path / a.AMENDMENT, {"schema": "tampered"})
    monkeypatch.setattr(a, "build", lambda: {"schema": "expected"})
    proof = Mock(side_effect=AssertionError("no network"))
    monkeypatch.setattr(protocol, "verify", proof)
    with pytest.raises(Halted, match="binding differs"):
        a.verify(FREEZE)
    assert not proof.called
