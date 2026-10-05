"""Synthetic CPU/mocked tests; none establish CUDA qualification."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from experiments.kolibri_bootstrap_a4 import adapter as a, production as p
from experiments.kolibri_bootstrap_a3 import adapter as a3
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments import kolibri_judge_transport as t
from experiments.kolibri_swap import production as prod, protocol, gpu_smoke as old, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_swap_production import FREEZE, NOW, write, tree_hashes, saved_controller, rechain_controller, finish_controller
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval
from tests.test_kolibri_swap_runtime import senders, receipt
from tests.test_kolibri_judge_transport import TIMEOUT, filtered, judge_one

CARRY = "1.02856524106372729000000001"


@pytest.mark.parametrize("kind", ["cheap", "main"])
def test_worker_delta_is_only_local_storage_setup(kind):
    before = a3.worker_script(kind, FREEZE, protocol.PLAN, 900)
    after = a.worker_script(kind, FREEZE, protocol.PLAN, 900)
    assert after.replace(a.storage_setup(), "").replace(a.LOCAL_VENV, a.bootstrap.REMOTE + "/venv") == before
    assert subprocess.run(["bash", "-n"], input=after, text=True, capture_output=True).returncode == 0
    assert "/workspace/kolibri/venv" not in after
    assert "--require-hashes" in after and "kolibri-pip-cache" in after
    assert "experiments.kolibri_bootstrap_a3.smoke" in after if kind == "cheap" else True


@pytest.mark.parametrize("mutation", [None, "network", "tmpfs", "same_device", "low_space", "existing"])
def test_installation_preflight_rejects_wrong_storage(monkeypatch, capsys, mutation):
    kind = {"network": "nfs4", "tmpfs": "tmpfs"}.get(mutation, "overlay")
    mounts = f"1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / /tmp rw - {kind} local rw\n"
    monkeypatch.setattr(Path, "read_text", lambda *args: mounts)
    monkeypatch.setattr(Path, "stat", lambda path: NS(st_dev=1 if mutation == "same_device" or str(path) == "/tmp" else 2))
    monkeypatch.setattr(Path, "exists", lambda path: mutation == "existing")
    monkeypatch.setattr(a.shutil, "disk_usage", lambda path: NS(free=1 if mutation == "low_space" else a.MIN_LOCAL_FREE_BYTES))
    if mutation is None:
        exec(a.storage_preflight(), {})
    else:
        with pytest.raises(AssertionError):
            exec(a.storage_preflight(), {})
    result = json.loads(capsys.readouterr().out)
    assert result["venv"] == a.LOCAL_VENV and result["pip_cache"] == a.LOCAL_PIP_CACHE


@pytest.mark.parametrize("failure", [TimeoutError(), ConnectionError(), a.old.base.ApiError(503),
    a.old.base.ApiError(429), RuntimeError("RunPod transport outcome unknown; do not retry mutation")])
def test_transient_get_retries_are_identical_bounded_and_guarded(failure):
    api = Mock(writable=True)
    api.request.side_effect = [failure, failure, (200, {"synthetic": True})]
    guard, record, sleep = Mock(), Mock(), Mock()
    wrapper = a.ReadRetryAPI(api, guard, record, sleep)
    assert wrapper.request("GET", "/pods/synthetic") == (200, {"synthetic": True})
    assert [call.args for call in api.request.call_args_list] == [("GET", "/pods/synthetic", None)] * 3
    assert [call.args for call in sleep.call_args_list] == [(2,), (5,)]
    assert [call.args for call in guard.call_args_list] == [(30,), (32,), (30,), (35,), (30,)]
    assert record.call_count == 2 and "error_type" in record.call_args.args[1]


@pytest.mark.parametrize("failure", [a.old.base.ApiError(404), a.old.base.ApiError(401),
                                   ValueError("identity"), RuntimeError("unrecognized")])
def test_nontransient_get_is_not_retried(failure):
    api = Mock(writable=True)
    api.request.side_effect = failure
    with pytest.raises(type(failure)):
        a.ReadRetryAPI(api, Mock(), Mock(), Mock()).request("GET", "/pods/synthetic")
    assert api.request.call_count == 1


@pytest.mark.parametrize("method,cleanup", [("POST", False), ("DELETE", False), ("GET", True)])
def test_mutation_and_cleanup_never_stack_inner_retries(method, cleanup):
    api = Mock(writable=True)
    api.request.side_effect = TimeoutError()
    guard = Mock()
    wrapper = a.ReadRetryAPI(api, guard, Mock(), Mock())
    wrapper.cleanup = cleanup
    with pytest.raises(TimeoutError):
        wrapper.request(method, "/pods/synthetic")
    assert api.request.call_count == 1
    guard.assert_not_called()


@pytest.mark.parametrize("blocked", ["before_wait", "after_wait", "exhausted"])
def test_retry_halts_on_guard_or_exhaustion(blocked):
    api = Mock(writable=True)
    api.request.side_effect = TimeoutError()
    guard = Mock(side_effect={"before_wait": [None, Halted("deadline")],
                              "after_wait": [None, None, Halted("deadline")],
                              "exhausted": None}[blocked])
    sleep = Mock()
    with pytest.raises(TimeoutError if blocked == "exhausted" else Halted):
        a.ReadRetryAPI(api, guard, Mock(), sleep).request("GET", "/pods/synthetic")
    assert api.request.call_count == (3 if blocked == "exhausted" else 1)
    assert sleep.call_count == {"before_wait": 0, "after_wait": 1, "exhausted": 2}[blocked]


def test_read_guard_reserves_cleanup_and_deadline():
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = "cheap", {"predecessor": {"cost_usd": CARRY}}
    clock = Clock()
    ctl.clock, ctl.elapsed = clock, lambda: Decimal(100)
    ctl.event = lambda name: {"data": {"quote": {"hourly_rate_usd": ".74"},
        "deadline_utc": (clock() + timedelta(seconds=100)).isoformat()}}
    ctl.read_guard(30)
    with pytest.raises(Halted):
        ctl.read_guard(101)
    ctl.elapsed = lambda: Decimal(4000)
    with pytest.raises(Halted):
        ctl.read_guard(30)


@pytest.mark.parametrize("kind,spent,passes", [("cheap", ".5", True), ("cheap", ".9", False),
                                            ("main", "21", True), ("main", "22.5", False)])
def test_carry_and_reduced_main_cap_reserve_cleanup(monkeypatch, kind, spent, passes):
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = kind, {"predecessor": {"cost_usd": CARRY}}
    monkeypatch.setattr(a.old.Controller, "cost_check", lambda *args: Decimal(spent))
    pod = {"cost": ".74" if kind == "cheap" else "4.59"}
    if passes:
        assert ctl.cost_check(pod) == Decimal(spent)
    else:
        with pytest.raises(Halted, match="subcap"):
            ctl.cost_check(pod)


def test_all_frozen_bytes_are_unchanged():
    records = [prod.load(protocol.ROOT / path) for path in (protocol.PLAN, a1.AMENDMENT, a2.AMENDMENT, a3.AMENDMENT, t.PLAN)]
    hashes = {name: digest for record in records for name, digest in record["source_hashes"].items()}
    assert len(hashes) == 108
    assert all(protocol.sha(protocol.ROOT / name) == digest for name, digest in hashes.items())
    own = a.sources()
    assert "tests/test_kolibri_bootstrap_a4.py" in own
    assert not any(name in own for name in hashes)
    assert "experiments/kolibri_release.py" not in own


def test_candidate_is_offline_and_changes_only_operational_budget(monkeypatch):
    prior = prod.load(protocol.ROOT / a3.AMENDMENT)
    monkeypatch.setattr(a3, "verify", lambda: prior)
    monkeypatch.setattr(a, "predecessor", lambda prior: {"cost_usd": CARRY})
    value = a.build()
    assert value["scientific_plan_sha256"] == a1.ORIGINAL_PLAN_SHA
    assert value["cheap_total_cap_usd"] == "2" and value["main_cap_usd"] == "23"
    assert Decimal(value["cheap_remaining_usd"]) + Decimal(CARRY) == 2
    assert value["science_changed"] is value["research_outcomes_observed"] is False
    assert value["judge_policy"]["freeze"] == a.JUDGE_FREEZE


@pytest.mark.parametrize("mutation", [None, "raw_hash", "closed", "retrieval", "exit", "report", "error", "completed"])
def test_predecessor_preserves_four_failures_and_rejects_changed_history(tmp_path, monkeypatch, mutation):
    root = tmp_path / "predecessor"
    directory = root / "controller/cheap/retrievals/synthetic"
    write(directory / "exit.json", {"exit_code": 1 if mutation == "exit" else 143})
    log = directory / "worker.log"
    log.write_text("Installing collected packages: synthetic\nTerminated\n")
    digest = protocol.sha(log)
    if mutation == "raw_hash":
        log.write_text("changed raw bytes\n")
    elif mutation == "completed":
        log.write_text("Installing collected packages: synthetic\nSuccessfully installed synthetic\n")
        digest = protocol.sha(log)
    if mutation == "report":
        write(directory / "gpu-smoke.json", {"status": "passed"})
    write(root / "controller/cheap/final-retrieval.json", {"data": {"directory": str(directory)}})
    write(root / "controller/cheap/events.jsonl", {"synthetic": "closed"})
    receipt = {"cost_usd": "0.4844722072845518966666666667",
               "closed_sha256": "0" * 64 if mutation == "closed" else a.CLOSED_SHA,
               "retrieval_sha256": "0" * 64 if mutation == "retrieval" else a.RETRIEVAL_SHA}
    monkeypatch.setattr(a3, "root", lambda: root)
    monkeypatch.setattr(a, "WORKER_SHA", digest)
    monkeypatch.setattr(prod, "closed_receipt", lambda *args: deepcopy(receipt))
    monkeypatch.setattr(prod, "controller_events", lambda *args: ([], {
        "created": {"data": {"id": a.FAILED_POD}},
        "monitor-failure:191": {"data": {"error_type": "ValueError" if mutation == "error" else "TimeoutError"}}}))
    prior = {"predecessor": {"exact_sum_usd": "0.54409303377917539333333333333",
        "cost_usd": "0.54409303377917539333333334", "attempts": [{"synthetic": i} for i in range(3)]}}
    before = tree_hashes(root)
    if mutation is None:
        result = a.predecessor(prior)
        assert result["cost_usd"] == CARRY and len(result["attempts"]) == 4
        assert Decimal(result["cost_usd"]) >= Decimal(result["exact_sum_usd"])
    else:
        with pytest.raises(Halted, match="preserved"):
            a.predecessor(prior)
    assert tree_hashes(root) == before


def test_owned_lifecycle_same_post_once_new_root(tmp_path, monkeypatch):
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    body = (protocol.ROOT / protocol.PLAN).read_bytes()
    repo, base = tmp_path / "repo", tmp_path / "run"
    write(repo / a.AMENDMENT, {"predecessor": {"cost_usd": CARRY}})
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(a, "verify", lambda freeze: prod.load(repo / a.AMENDMENT))
    monkeypatch.setattr(protocol, "verify", lambda path: plan)
    monkeypatch.setattr(a.old, "canonical_root", lambda: base)
    monkeypatch.setattr(a.old, "quote", lambda api, kind: {"hourly_rate_usd": ".74", "storage_hourly_usd": ".10"})
    monkeypatch.setattr(a.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    key = repo / "synthetic-key"
    key.write_text("synthetic fixture, not a credential")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA synthetic")
    monkeypatch.setattr(a.old.base, "KEY", key)
    clock = Clock()
    class API(FakeAPI):
        def request(self, method, path, body=None):
            if method == "GET" and path.startswith("/pods?"):
                return 200, {"pods": self.inventory(), "pagination": {"hasNextPage": False}}
            status, value = super().request(method, path, body)
            if method == "POST":
                self.pod["cost"] = value["cost"] = ".74"
            return status, value
    api = API(clock)
    ctl = a.Controller(FREEZE, "cheap", api, clock=clock, sleep=clock.sleep)
    assert ctl.base == base / "bootstrap-a4/controller/cheap"
    for pod in (a.FAILED_POD, a3.FAILED_POD, a2.FAILED_POD, a1.FAILED_POD):
        assert not ctl._new_pod({"id": pod}, {})
    ctl._ssh = Mock(side_effect=lambda pod, command, **kwargs: b"ready" if command == "printf ready" else b"dispatched")
    ctl.launch()
    upload = next(call.kwargs["data"] for call in ctl._ssh.call_args_list if "data" in call.kwargs)
    assert b"/tmp/kolibri-venv" in upload and b"experiments.kolibri_bootstrap_a3.smoke" in upload
    assert api.calls.count(("POST", "/pods")) == 1
    assert Decimal(ctl.event("create-intent")["data"]["cap_usd"]) + Decimal(CARRY) == 2
    with pytest.raises(Halted, match="already attempted"):
        ctl.launch()
    saved_retrieval(ctl)
    clock.sleep(60)
    assert ctl.terminate()["data"]["get_status"] == 404


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    original = protocol.ROOT
    plan = protocol.verify(original / protocol.PLAN)
    repo, root = tmp_path / "repo", tmp_path / "run/bootstrap-a4"
    for name in (*t.SOURCES, t.PLAN, protocol.PLAN):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes((original / name).read_bytes())
    (repo / "bridge.py").write_text("# Synthetic A4 binding, not production source\n")
    policy = prod.load(repo / t.PLAN)
    amendment = {"source_hashes": {"bridge.py": protocol.sha(repo / "bridge.py")},
        "dependency_source_hashes": {}, "predecessor": {"cost_usd": CARRY},
        "judge_policy": {"freeze": a.JUDGE_FREEZE, "path": t.PLAN, "sha256": protocol.sha(repo / t.PLAN),
                         "original_worker_freeze": a.A2_FREEZE, "policy_changed": False}}
    write(repo / a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    return plan, root, amendment, policy


def qualified_controller(root, plan_hash, amendment):
    ledger = saved_controller(root, "cheap", closed=True, plan_hash=plan_hash)
    ledger.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT),
        "prior_cheap_usd": CARRY, "a3_freeze": a.A3_FREEZE})
    base = root / "controller/cheap"
    path = base / "retrievals/synthetic/gpu-smoke.json"
    value = prod.load(path)
    value.update(amendment="kolibri-bootstrap-a3-v1", parser={"official_passed": 70, "skipped": 0})
    value["gpu"].update(llm_options=old.LLM_OPTIONS, checkpoint={"fp8_matrices": 186},
        forward=[{"tokens": 8, "prompt_tokens": len(prompt)} for prompt in old.PROMPTS],
        workers=[{"status": "passed", "linear_errors": [], "layers": 6, "custom_routing_layers": 6,
                  "fp8_weights": True, "checkpoint_fp32_block_scales": True,
                  "modules": [{"name": "synthetic"}], "operator_sources": {"synthetic": "f" * 64},
                  "linears": [{"name": f"model.layers.{i}.{name}", "storage": "official_marlin_e4m3fn_packed_int32",
                               "exact_checkpoint_reconstruction": True} for i in range(6) for name in
                               ("self_attn.qkv_proj", "self_attn.o_proj", "mlp.shared_experts.gate_up_proj",
                                "mlp.shared_experts.down_proj")]}])
    write(path, value)
    rows = ledger.read()
    next(row for row in rows if row["id"] == "retrieval:6")["data"]["artifacts"]["gpu-smoke.json"] = protocol.sha(path)
    rechain_controller(base, rows)
    return value


def main_controller(root, plan_hash):
    ledger = saved_controller(root, "main", plan_hash=plan_hash)
    ledger.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT),
        "prior_cheap_usd": CARRY, "a3_freeze": a.A3_FREEZE})
    return ledger


@contextmanager
def opened_bridge(bridge, local=None, judge=None):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", FREEZE, digest) as receipts:
        binding = p.bridge_binding(FREEZE, amendment, policy)
        if receipts.decision("judge_transport") is None:
            receipts.append("decision", {"name": "judge_transport", "value": binding})
        runner = p.Runner(plan, FREEZE, digest, ledger, receipts, local, judge,
                          amendment=amendment, transport_plan=policy, sleep=Mock())
        yield runner


@pytest.mark.parametrize("mutation", [None, "missing", "failed", "old_amendment", "no_modules", "linear",
                                    "forward", "carry", "GET200", "hash"])
def test_main_creation_requires_exact_a3_pass_and_get404(bridge, mutation):
    plan, root, amendment, _ = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    value = qualified_controller(root, digest, amendment)
    base, path = root / "controller/cheap", root / "controller/cheap/retrievals/synthetic/gpu-smoke.json"
    rows, _ = prod.controller_events(root, "cheap", digest, FREEZE)
    if mutation == "missing":
        path.unlink()
    elif mutation in {"failed", "old_amendment", "no_modules", "linear", "forward", "hash"}:
        if mutation in {"failed", "hash"}:
            value["status"] = "failed"
        elif mutation == "old_amendment":
            value["amendment"] = "kolibri-bootstrap-a2-v1"
        elif mutation == "no_modules":
            value["gpu"]["workers"][0]["modules"] = []
        elif mutation == "linear":
            value["gpu"]["workers"][0]["linears"].pop()
        else:
            value["gpu"]["forward"].pop()
        write(path, value)
        if mutation != "hash":
            next(row for row in rows if row["id"] == "retrieval:6")["data"]["artifacts"]["gpu-smoke.json"] = protocol.sha(path)
    elif mutation == "carry":
        next(row for row in rows if row["id"] == "controller:config")["data"]["prior_cheap_usd"] = "0"
    elif mutation == "GET200":
        next(row for row in rows if row["id"] == "closed")["data"]["get_status"] = 200
    rechain_controller(base, rows)
    ctl = object.__new__(a.Controller)
    ctl.out, ctl.freeze, ctl.plan_hash, ctl.amendment = root, FREEZE, digest, amendment
    ctl.kind, ctl.api, ctl.event = "main", Mock(writable=True), Mock(return_value=None)
    if mutation is None:
        before = tree_hashes(root)
        assert ctl.cheap_pass()["cost_usd"] == "0.25"
        assert tree_hashes(root) == before
    else:
        with pytest.raises((Halted, ValueError, OSError)):
            ctl.launch()
        ctl.api.inventory.assert_not_called()
        ctl.api.request.assert_not_called()


@pytest.mark.parametrize("mode", ["retry", "refusal", "external_stop"])
def test_bridge_reuses_exact_retry_missing_and_external_stop_safeguards(bridge, mode):
    _, good, _, _ = senders()
    seen = []
    holder = {}
    def sender(request):
        seen.append(request)
        if len(seen) == 1:
            if mode == "external_stop":
                holder["runner"].stop.set()
            return receipt(filtered(request, good)) if mode == "refusal" else TIMEOUT
        return good(request)
    with opened_bridge(bridge, judge=sender) as runner:
        holder["runner"] = runner
        runner.guard = Mock()
        if mode == "external_stop":
            with pytest.raises(Halted):
                judge_one(runner)
            assert len(seen) == 1 and runner.stop.is_set()
        else:
            result = judge_one(runner)
            assert result["status"] == ("ok" if mode == "retry" else "incomplete_judge")
            assert len(seen) == (2 if mode == "retry" else 1)
            report = runner.audit()
            assert report["physical_unresolved"] == 1
            assert report["terminal_refusal_calls"] if mode == "refusal" else report["pass"]
        for row in runner.receipts.records().values():
            assert row["metadata"]["freeze"] == FREEZE
            if "transport_retry" in row["metadata"]:
                assert row["metadata"]["transport_retry"]["operational_freeze"] == a.JUDGE_FREEZE
        assert runner._exchange.__func__ is t.Runner._exchange
        assert runner.logical_reader.__func__ is t.Runner.logical_reader


def test_full_owned_chain_generates_main_before_stop_retrieval_and_judge_tail(bridge):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    qualified_controller(root, digest, amendment)
    main = main_controller(root, digest)
    local, judge, generated, judged = senders()
    with opened_bridge(bridge, local, judge) as runner:
        runner.guard = a.StudyGuard(root, plan, FREEZE, digest, runner.ledger, amendment=amendment, clock=lambda: NOW)
        baseline = prod.StudyGuard(root, plan, FREEZE, digest, runner.ledger, clock=lambda: NOW)
        assert runner.guard.state()["gpu_usd"] == baseline.state()["gpu_usd"] + Decimal(CARRY)
        assert prod.phase(runner, "fixtures", root)["pass"]
        assert prod.phase(runner, "generate-screen-initial", root)["generation_calls"] == 12
        with pytest.raises(Halted):
            prod.phase(runner, "generate-screen", root)
        assert prod.phase(runner, "judge-screen-initial", root)["pass"]
        assert prod.phase(runner, "generate-screen", root)["generation_calls"] == 72
        assert prod.phase(runner, "judge-screen", root)["eligible_models"] == ["kolibri"]
        assert prod.phase(runner, "main-admission", root)["fits"]
        before_judges = len(judged)
        runner.sender = None
        assert prod.phase(runner, "generate-main", root)["generation_calls"] == 384
        assert len(generated) == 457 and len(judged) == before_judges
        assert prod.phase(runner, "stop-server", root)["deletion_verified"] is False
        assert (root / "controller/main/STOP_SERVER").is_file()
        with pytest.raises((Halted, KeyError)):
            prod.phase(runner, "judge-main", root)
        assert len(judged) == before_judges
        finish_controller(root, "main", main, plan_hash=digest)
        runner.sender = judge
        assert prod.phase(runner, "judge-main", root)["complete"]
        assert runner.audit()["generation_calls"] == 457
        write(root / "collection/runtime.json", prod.binding(plan, FREEZE, digest))
        for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", a.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
            p.save_bytes(root / "collection" / name, (protocol.ROOT / source).read_bytes())
    before = tree_hashes(root)
    with p.saved_runner(root, plan, digest, amendment, policy, FREEZE) as reader:
        assert reader.audit()["pass"] and len(reader.rows("main")) == 256
    assert tree_hashes(root) == before


@pytest.mark.parametrize("mutation", ["bridge_source", "judge_policy", "amendment", "worker_binding"])
def test_bridge_tamper_blocks_replay_or_dispatch(bridge, mutation):
    _, root, amendment, policy = bridge
    with opened_bridge(bridge) as runner:
        if mutation == "bridge_source":
            (protocol.ROOT / "bridge.py").write_text("# changed synthetic source\n")
        elif mutation == "judge_policy":
            changed = deepcopy(policy)
            changed["additional_attempts"] = 3
            write(protocol.ROOT / t.PLAN, changed)
        elif mutation == "amendment":
            write(protocol.ROOT / a.AMENDMENT, {**amendment, "predecessor": {"cost_usd": "0"}})
        else:
            runner.transport_plan["worker_freeze"] = FREEZE
        with pytest.raises(Halted):
            runner.check_sources()


def test_bridge_binds_exact_saved_plan_bytes_without_rewriting_policy(bridge):
    _, _, amendment, policy = bridge
    path = protocol.ROOT / t.PLAN
    before = path.read_bytes()
    binding = p.bridge_binding(FREEZE, amendment, policy)
    assert binding["amendment_sha256"] == protocol.sha(protocol.ROOT / a.AMENDMENT)
    assert binding["judge_policy_sha256"] == protocol.sha(path)
    assert binding["judge_policy_original_worker_freeze"] == a.A2_FREEZE
    assert binding["worker_freeze"] == FREEZE and binding["judge_operational_freeze"] == a.JUDGE_FREEZE
    assert path.read_bytes() == before
    with pytest.raises(Halted, match="Bridge input"):
        p.bridge_binding(FREEZE, {**amendment, "extra": True}, policy)


def test_exact_byte_bridge_saved_replay_and_cli_are_read_only(bridge, monkeypatch):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    _, judge, _, _ = senders()
    with opened_bridge(bridge, judge=judge) as runner:
        runner.guard = Mock()
        assert judge_one(runner)["status"] == "ok"
        write(root / "collection/runtime.json", prod.binding(plan, FREEZE, digest))
        for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", a.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
            p.save_bytes(root / "collection" / name, (protocol.ROOT / source).read_bytes())
    before = tree_hashes(root)
    with p.saved_runner(root, plan, digest, amendment, policy, FREEZE) as reader:
        assert reader.audit()["physical_calls"] == 1
    monkeypatch.setattr(a, "verify", lambda freeze=None: deepcopy(amendment))
    monkeypatch.setattr(t, "verify", lambda path: deepcopy(policy))
    monkeypatch.setattr(protocol, "verify", lambda path: deepcopy(plan))
    monkeypatch.setattr(prod, "local_key", Mock(side_effect=AssertionError("no credentials")))
    monkeypatch.setattr(runtime, "http_sender", Mock(side_effect=AssertionError("no HTTP")))
    assert p.main(["--freeze", FREEZE, "--run-dir", str(root), "--phase", "audit"]) == 0
    assert tree_hashes(root) == before
    prod.local_key.assert_not_called()
    runtime.http_sender.assert_not_called()
