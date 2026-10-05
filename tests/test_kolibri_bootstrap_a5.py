"""Synthetic CPU lifecycle/CLI tests; real Linux parser preflight is mandatory remotely."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import io
from pathlib import Path
import shlex
import subprocess
from unittest.mock import Mock

import pytest

from experiments.kolibri_bootstrap_a5 import adapter as a, cli, production as p
from experiments.kolibri_bootstrap_a4 import adapter as a4
from experiments import kolibri_judge_transport as t
from experiments.kolibri_swap import production as prod, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval
from tests.test_kolibri_swap_production import FREEZE, NOW, write, tree_hashes, saved_controller, finish_controller
from tests.test_kolibri_swap_runtime import senders, receipt
from tests.test_kolibri_judge_transport import TIMEOUT, filtered, judge_one

CARRY = "1.94695653900638706083333335"
REMAINING = "22.2267159218906735625"
CHEAP = {"cost_usd": ".1451072198333333333333333333", "ledger_sha256": a.QUALIFIED_CLOSED_SHA,
         "closed_sha256": a.QUALIFIED_CLOSED_SHA, "retrieval_sha256": a.QUALIFIED_RETRIEVAL_SHA}


def test_full_production_argv_changes_only_obsolete_logging_flag():
    before = a4.worker_script("main", FREEZE, protocol.PLAN, 900)
    after = a.worker_script("main", FREEZE, protocol.PLAN, 900)
    preflight = shlex.join([a4.LOCAL_VENV + "/bin/python", "-m", "experiments.kolibri_bootstrap_a5.cli"])
    assert after.replace(preflight + "\n", "").replace("--no-enable-log-requests", "--disable-log-requests") == before
    assert shlex.join(cli.serve_argv()) in after
    assert after.index(preflight) < after.index("-m experiments.kolibri_swap.model_files") < after.index(shlex.join(cli.serve_argv()))
    assert subprocess.run(["bash", "-n"], input=after, text=True, capture_output=True).returncode == 0
    with pytest.raises(Halted):
        a.worker_script("cheap", FREEZE, protocol.PLAN, 900)


def synthetic_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_tag")
    for name in ("revision", "tokenizer-revision", "host", "kv-cache-dtype", "reasoning-parser", "generation-config"):
        parser.add_argument("--" + name)
    parser.add_argument("--served-model-name", nargs="+")
    for name in ("port", "max-model-len", "max-num-seqs", "seed"):
        parser.add_argument("--" + name, type=int)
    parser.add_argument("--gpu-memory-utilization", type=float)
    parser.add_argument("--enforce-eager", action="store_true")
    parser.add_argument("--enable-log-requests", action=argparse.BooleanOptionalAction, default=False)
    return parser


@pytest.mark.parametrize("mutation", [None, "obsolete", "unknown", "logging", "model", "context"])
def test_full_argv_preflight_never_ignores_unknowns_or_semantic_changes(monkeypatch, mutation):
    parser, validate = synthetic_parser(), Mock()
    argv = cli.serve_argv()
    if mutation == "obsolete":
        argv[-1] = "--disable-log-requests"
    elif mutation == "unknown":
        argv.append("--invented-flag")
    elif mutation == "logging":
        argv[-1] = "--enable-log-requests"
    elif mutation == "model":
        argv[2] = "synthetic-other-model"
    elif mutation == "context":
        argv[argv.index("--max-model-len") + 1] = "8192"
    monkeypatch.setattr(cli, "serve_argv", lambda: argv)
    if mutation:
        with pytest.raises((SystemExit, AssertionError)):
            cli.validate_parser(parser, validate)
    else:
        result = cli.validate_parser(parser, validate)
        assert result["argv"] == argv and result["argv_sha256"] == protocol.digest(argv)
        assert result["parsed"]["enable_log_requests"] is False
        assert result["model_loaded"] is result["scientific_generation"] is False
        validate.assert_called_once()


def test_installed_version_mismatch_fails_before_parser_import(monkeypatch):
    monkeypatch.setattr(cli, "version", lambda name: "0.28.0")
    with pytest.raises(AssertionError, match="distribution"):
        cli.main()


@pytest.mark.parametrize("mutation", [None, "closed", "exit", "log", "model", "collection"])
def test_predecessor_cost_carry_and_read_only_failure_binding(tmp_path, monkeypatch, mutation):
    prior = prod.load(protocol.ROOT / a4.AMENDMENT)
    base, directory = tmp_path / "a4", tmp_path / "a4/controller/main/retrievals/synthetic"
    frozen = prod.load(protocol.ROOT / protocol.PLAN)["metadata"]["model_artifacts"]["files"]
    model = {"files": [{"path": name, "sha256": value["sha256"], "bytes": value["size"]}
                       for name, value in frozen.items()], "verified": True, "config_verified": True,
             "weight_map_verified": True, "revision": a.bootstrap.MODEL_REVISION, "model": a.bootstrap.MODEL,
             "plan_sha256": a.a4.a1.ORIGINAL_PLAN_SHA, "frozen_files_verified": len(frozen)}
    if mutation == "model":
        model["files"][0]["sha256"] = "0" * 64
    write(directory / "model-files.json", model)
    write(directory / "exit.json", {"exit_code": 0 if mutation == "exit" else 2})
    (directory / "worker.log").write_text("synthetic failure\n" + ("different error" if mutation == "log" else
        "vllm: error: unrecognized arguments: --disable-log-requests"))
    for kind in ("cheap", "main"):
        write(base / f"controller/{kind}/events.jsonl", {"synthetic": True})
        write(base / f"controller/{kind}/final-retrieval.json", {"data": {"directory": str(directory)}})
    if mutation == "collection":
        (base / "collection").mkdir()
    receipt = {"cost_usd": ".7732840781093264375", "ledger_sha256": a.CLOSED_SHA,
        "closed_sha256": "0" * 64 if mutation == "closed" else a.CLOSED_SHA, "retrieval_sha256": a.RETRIEVAL_SHA}
    monkeypatch.setattr(a4, "root", lambda: base)
    monkeypatch.setattr(a, "qualification", lambda prior: deepcopy(CHEAP))
    monkeypatch.setattr(prod, "closed_receipt", lambda *args: receipt)
    monkeypatch.setattr(prod, "controller_events", lambda *args: ([], {"created": {"data": {"id": a.FAILED_POD}}}))
    before = tree_hashes(base)
    if mutation:
        with pytest.raises(Halted):
            a.predecessor(prior)
    else:
        carry, cheap, remaining = a.predecessor(prior)
        assert carry["cost_usd"] == CARRY and len(carry["attempts"]) == 6
        assert remaining == REMAINING and cheap == CHEAP
        assert Decimal(CARRY) + Decimal(REMAINING) < 25
    assert tree_hashes(base) == before


def test_all_113_prior_frozen_source_bytes_remain_unchanged():
    prior = prod.load(protocol.ROOT / a4.AMENDMENT)
    hashes = {**prod.load(protocol.ROOT / protocol.PLAN)["source_hashes"],
              **prior["dependency_source_hashes"], **prior["source_hashes"]}
    assert len(hashes) == 113
    assert not set(a.sources()) & set(hashes)
    assert all(protocol.sha(protocol.ROOT / name) == digest for name, digest in hashes.items())
    assert "experiments/kolibri_release.py" not in a.sources()
    assert cli.WHEEL_SHA256 in (protocol.ROOT / "experiments/kolibri_swap/requirements-gpu.lock").read_text()


@pytest.mark.parametrize("mutation", ["closed", "retrieval", "pod"])
def test_reused_qualification_requires_exact_closed_identity(monkeypatch, mutation):
    record = deepcopy(CHEAP)
    if mutation in {"closed", "retrieval"}:
        record[mutation + "_sha256"] = "0" * 64
    monkeypatch.setattr(a4, "qualified_cheap", lambda *args: record)
    monkeypatch.setattr(prod, "controller_events", lambda *args: ([], {"created": {"data": {
        "id": "foreign" if mutation == "pod" else a.QUALIFIED_POD}}}))
    with pytest.raises(Halted, match="qualified"):
        a.qualification({})


@pytest.mark.parametrize("spent,passes", [("21", True), ("21.5", False)])
def test_remaining_main_cap_retains_cleanup(monkeypatch, spent, passes):
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = "main", {"main_cap_usd": REMAINING}
    monkeypatch.setattr(a.old.Controller, "cost_check", lambda *args: Decimal(spent))
    if passes:
        assert ctl.cost_check({"cost": "4.59"}) == Decimal(spent)
    else:
        with pytest.raises(Halted):
            ctl.cost_check({"cost": "4.59"})


def test_owned_retry_cannot_create_cheap_or_resend_post(tmp_path, monkeypatch):
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    body = (protocol.ROOT / protocol.PLAN).read_bytes()
    repo, base = tmp_path / "repo", tmp_path / "run"
    amendment = {"predecessor": {"cost_usd": CARRY}, "main_cap_usd": REMAINING,
                 "qualification": {"freeze": a.A4_FREEZE, "pod_id": a.QUALIFIED_POD, **CHEAP}}
    write(repo / a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(a, "verify", lambda freeze: amendment)
    monkeypatch.setattr(protocol, "verify", lambda path: plan)
    monkeypatch.setattr(a.old, "canonical_root", lambda: base)
    monkeypatch.setattr(a, "qualification", lambda prior: deepcopy(CHEAP))
    monkeypatch.setattr(a4, "verify", lambda: {})
    monkeypatch.setattr(a.old, "quote", lambda api, kind: {"hourly_rate_usd": "4.59", "storage_hourly_usd": ".10"})
    monkeypatch.setattr(a4.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    key = repo / "synthetic-key"; key.write_text("synthetic fixture, not a credential")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA synthetic")
    monkeypatch.setattr(a.old.base, "KEY", key)
    clock = Clock()
    class API(FakeAPI):
        def request(self, method, path, body=None):
            if method == "GET" and path.startswith("/pods?"):
                return 200, {"pods": self.inventory(), "pagination": {"hasNextPage": False}}
            status, value = super().request(method, path, body)
            if method == "POST":
                self.pod["cost"] = value["cost"] = "4.59"
            return status, value
    api = API(clock)
    with pytest.raises(Halted):
        a.Controller(FREEZE, "cheap", api)
    ctl = a.Controller(FREEZE, "main", api, clock=clock, sleep=clock.sleep)
    assert not (ctl.out / "controller/cheap").exists()
    ctl._ssh = Mock(side_effect=lambda pod, command, **kwargs: b"ready" if command == "printf ready" else b"dispatched")
    ctl.launch()
    upload = next(call.kwargs["data"] for call in ctl._ssh.call_args_list if "data" in call.kwargs)
    assert b"--no-enable-log-requests" in upload and b"--disable-log-requests" not in upload
    assert b"experiments.kolibri_bootstrap_a5.cli" in upload
    assert api.calls.count(("POST", "/pods")) == 1
    assert ctl.event("create-intent")["data"]["cap_usd"] == REMAINING
    with pytest.raises(Halted):
        ctl.launch()
    saved_retrieval(ctl); clock.sleep(60)
    assert ctl.terminate()["data"]["get_status"] == 404


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    original = protocol.ROOT
    plan = protocol.verify(original / protocol.PLAN)
    repo, root = tmp_path / "repo", tmp_path / "run/bootstrap-a5"
    for name in (*t.SOURCES, t.PLAN, protocol.PLAN):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes((original / name).read_bytes())
    (repo / "bridge.py").write_text("# Synthetic A5 binding, not production source\n")
    policy = prod.load(repo / t.PLAN)
    amendment = {"source_hashes": {"bridge.py": protocol.sha(repo / "bridge.py")}, "dependency_source_hashes": {},
        "predecessor": {"cost_usd": CARRY}, "main_cap_usd": REMAINING,
        "qualification": {"freeze": a.A4_FREEZE, "pod_id": a.QUALIFIED_POD, **CHEAP},
        "judge_policy": {"freeze": a.JUDGE_FREEZE, "path": t.PLAN, "sha256": protocol.sha(repo / t.PLAN),
                         "original_worker_freeze": a.A2_FREEZE, "policy_changed": False}}
    write(repo / a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(a, "qualification", lambda prior: deepcopy(CHEAP))
    monkeypatch.setattr(a4, "verify", lambda: {})
    return plan, root, amendment, policy


@contextmanager
def opened(bridge, local=None, judge=None):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", FREEZE, digest) as receipts:
        receipts.append("decision", {"name": "judge_transport", "value": p.bridge_binding(FREEZE, amendment, policy)})
        yield p.Runner(plan, FREEZE, digest, ledger, receipts, local, judge,
                       amendment=amendment, transport_plan=policy, sleep=Mock())


@pytest.mark.parametrize("mode", ["retry", "refusal", "external_stop"])
def test_unchanged_judge_policy_bridge(bridge, mode):
    _, good, _, _ = senders()
    seen, holder = [], {}
    def sender(request):
        seen.append(request)
        if len(seen) == 1:
            if mode == "external_stop":
                holder["runner"].stop.set()
            return receipt(filtered(request, good)) if mode == "refusal" else TIMEOUT
        return good(request)
    with opened(bridge, judge=sender) as runner:
        holder["runner"] = runner; runner.guard = Mock()
        if mode == "external_stop":
            with pytest.raises(Halted):
                judge_one(runner)
            assert len(seen) == 1 and runner.stop.is_set()
        else:
            value = judge_one(runner)
            assert value["status"] == ("ok" if mode == "retry" else "incomplete_judge")
            assert len(seen) == (2 if mode == "retry" else 1)
            assert runner.audit()["physical_unresolved"] == 1
        assert runner._exchange.__func__ is t.Runner._exchange


def test_full_chain_reuses_qualification_and_deletes_before_judge_tail(bridge):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    main = saved_controller(root, "main", plan_hash=digest)
    main.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT),
        "a4_freeze": a.A4_FREEZE, "qualification": amendment["qualification"], "prior_gpu_usd": CARRY,
        "cap_usd": REMAINING})
    local, judge, generated, judged = senders()
    with opened(bridge, local, judge) as runner:
        runner.guard = a.StudyGuard(root, plan, FREEZE, digest, runner.ledger, amendment=amendment, clock=lambda: NOW)
        state = runner.guard.state()
        assert state["gpu_usd"] == state["main_usd"] + Decimal(CARRY)
        assert not (root / "controller/cheap").exists()
        assert prod.phase(runner, "fixtures", root)["pass"]
        assert prod.phase(runner, "generate-screen-initial", root)["generation_calls"] == 12
        with pytest.raises(Halted):
            prod.phase(runner, "generate-screen", root)
        assert prod.phase(runner, "judge-screen-initial", root)["pass"]
        assert prod.phase(runner, "generate-screen", root)["generation_calls"] == 72
        assert prod.phase(runner, "judge-screen", root)["eligible_models"] == ["kolibri"]
        assert prod.phase(runner, "main-admission", root)["fits"]
        before = len(judged); runner.sender = None
        assert prod.phase(runner, "generate-main", root)["generation_calls"] == 384
        assert len(generated) == 457 and len(judged) == before
        assert prod.phase(runner, "stop-server", root)["deletion_verified"] is False
        with pytest.raises((Halted, KeyError)):
            prod.phase(runner, "judge-main", root)
        finish_controller(root, "main", main, plan_hash=digest)
        runner.sender = judge
        assert prod.phase(runner, "judge-main", root)["complete"]
        write(root / "collection/runtime.json", prod.binding(plan, FREEZE, digest))
        for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", a.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
            p.save_bytes(root / "collection" / name, (protocol.ROOT / source).read_bytes())
    before = tree_hashes(root)
    with p.saved_runner(root, plan, digest, amendment, policy, FREEZE) as runner:
        assert runner.audit()["pass"] and len(runner.rows("main")) == 256
    assert tree_hashes(root) == before


@pytest.mark.parametrize("mutation", ["source", "judge", "amendment"])
def test_source_tampering_blocks_dispatch(bridge, mutation):
    with opened(bridge) as runner:
        path = protocol.ROOT / {"source": "bridge.py", "judge": t.PLAN, "amendment": a.AMENDMENT}[mutation]
        path.write_text("{}\n")
        with pytest.raises(Halted):
            runner.check_sources()
