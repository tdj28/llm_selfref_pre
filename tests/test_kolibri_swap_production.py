"""Synthetic saved receipts and mocked CLI only: no provider, SSH, or GPU calls."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import tarfile
from unittest.mock import Mock

import pytest

from experiments.kolibri_swap import production as p, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.sae_assay_diagnostic.budget import EventLedger
from tests.test_kolibri_swap_runtime import senders
from tests.test_kolibri_swap_controller import setup as controller_setup, owned, tar_bytes

FREEZE, PLAN_HASH = "a"*40, "b"*64
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


@pytest.fixture
def plan():
    value = protocol.build({})
    value["source_hashes"] = {n: protocol.sha(protocol.ROOT/n) for n in (
        "experiments/kolibri_swap/production.py", "experiments/kolibri_swap/runtime.py",
        "tests/test_kolibri_swap_production.py")}
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(protocol.canonical(value)+"\n")


def saved_controller(root, kind, *, closed=False, plan_hash=PLAN_HASH, elapsed=60):
    base = root/"controller"/kind
    ledger = EventLedger(base/"events.jsonl", plan_hash, FREEZE, [])
    pod_id = "synthetic-"+kind
    name = p.controller.PREFIX+kind+"-"+"a"*12
    rate = ".74" if kind == "cheap" else "4.59"
    ledger.bind("create-intent", {"plan_sha256": plan_hash, "freeze_commit": FREEZE,
        "created_utc": (NOW-timedelta(seconds=elapsed)).isoformat(),
        "deadline_utc": (NOW+timedelta(seconds=15000-elapsed)).isoformat(),
        "cleanup_deadline_utc": (NOW+timedelta(seconds=15600-elapsed)).isoformat(),
        "quote": {"hourly_rate_usd": rate, "storage_hourly_usd": ".10"},
        "payload": {"name": name}, "blocked": []})
    ledger.bind("created", {"id": pod_id, "name": name})
    ledger.bind("worker-started", {"pod_id": pod_id})
    ledger.bind("health:4", {"worker": {"ready": True}, "pod": {"id": pod_id}})
    ledger.bind("accounting:5", {"elapsed_seconds": str(elapsed), "upper_bound_usd": ".08"})
    if closed:
        finish_controller(root, kind, ledger, plan_hash=plan_hash)
    return ledger


def finish_controller(root, kind, ledger, *, plan_hash=PLAN_HASH):
    base = root/"controller"/kind
    directory = base/"retrievals"/"synthetic"
    result = {"schema": "kolibri-tiny-qualification-v1", "status": "passed", "mode": "gpu",
        "scientific_generation": False, "expected_versions": p.gpu_smoke.VERSIONS,
        "versions": p.gpu_smoke.VERSIONS, "gpu": {"official_routing_cpu_cuda": True},
        "upstream": {"revision": p.gpu_smoke.UPSTREAM_SHA, "source_sha256": p.gpu_smoke.SOURCE_HASHES}}
    write(directory/"gpu-smoke.json", result)
    write(directory/"exit.json", {"exit_code": 0})
    artifacts = {f.name: protocol.sha(f) for f in directory.iterdir()}
    receipt = ledger.bind("retrieval:6", {"pod_id": "synthetic-"+kind,
        "directory": str(directory), "artifacts": artifacts, "retrieval_verified": True})
    write(base/"final-retrieval.json", receipt)
    ledger.bind("closed", {"get_status": 404, "pod_id": "synthetic-"+kind,
                           "compute_upper_bound_usd": ".25", "elapsed_seconds": "120"})


def tree_hashes(root):
    return {str(f.relative_to(root)): protocol.sha(f) for f in root.rglob("*") if f.is_file()}


@contextmanager
def live_fixture(root, plan, *, local=None, judge=None):
    saved_controller(root, "cheap", closed=True)
    saved_controller(root, "main")
    with Ledger(root/"collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root/"collection/http", FREEZE, PLAN_HASH) as journal:
        runner = p.ProductionRunner(plan, FREEZE, PLAN_HASH, ledger, journal, local, judge)
        runner.guard = p.StudyGuard(root, plan, FREEZE, PLAN_HASH, ledger, clock=lambda: NOW)
        yield runner


def test_real_initial_phases_use_fixed_runtime_and_saved_controller(tmp_path, plan):
    local, judge, seen, paid = senders()
    with live_fixture(tmp_path, plan, local=local, judge=judge) as runner:
        assert p.phase(runner, "fixtures", tmp_path)["pass"]
        with pytest.raises(Halted):
            p.phase(runner, "generate-screen", tmp_path)
        assert p.phase(runner, "generate-screen-initial", tmp_path)["generation_calls"] == 12
        report = p.phase(runner, "judge-screen-initial", tmp_path)
        assert report["pass"] and runner.receipts.decision("screen_initial") == report
        count = len(seen)+len(paid)
        assert p.phase(runner, "judge-screen-initial", tmp_path) == report
        assert len(seen)+len(paid) == count
        assert p.phase(runner, "generate-screen", tmp_path)["generation_calls"] == 72
        assert len(seen) == 73 and len(paid) == 56
        assert runner.audit()["unresolved"] == 0


def test_controller_verification_is_read_only_and_binds_actual_smoke_schema(tmp_path):
    saved_controller(tmp_path, "cheap", closed=True)
    before = tree_hashes(tmp_path)
    result = p.closed_receipt(tmp_path, "cheap", PLAN_HASH, FREEZE, smoke=True)
    assert result["cost_usd"] == "0.25" and before == tree_hashes(tmp_path)
    with pytest.raises(ValueError):
        p.closed_receipt(tmp_path, "cheap", "c"*64, FREEZE, smoke=True)


@pytest.mark.parametrize("mutation", ["hash", "extra", "missing", "symlink", "foreign_path", "gate", "deletion", "recovery_failed"])
def test_saved_controller_tamper_never_qualifies(tmp_path, mutation):
    ledger = saved_controller(tmp_path, "cheap", closed=True)
    base = tmp_path/"controller/cheap"
    directory = base/"retrievals/synthetic"
    if mutation == "hash":
        (directory/"exit.json").write_text('{"exit_code":1}')
    elif mutation == "extra":
        (directory/"extra.json").write_text('{}')
    elif mutation == "missing":
        (directory/"exit.json").unlink()
    elif mutation == "symlink":
        (directory/"link").symlink_to(directory/"exit.json")
    elif mutation == "foreign_path":
        receipt = p.load(base/"final-retrieval.json")
        receipt["data"]["directory"] = str(tmp_path/"other")
        write(base/"final-retrieval.json", receipt)
    else:
        rows = ledger.read()
        if mutation == "gate":
            result = p.load(directory/"gpu-smoke.json")
            result["status"] = "failed"
            write(directory/"gpu-smoke.json", result)
            next(r for r in rows if r["id"] == "retrieval:6")["data"]["artifacts"]["gpu-smoke.json"] = protocol.sha(directory/"gpu-smoke.json")
        elif mutation == "deletion":
            rows[-1]["data"]["get_status"] = 200
        else:
            data = next(r for r in rows if r["id"] == "retrieval:6")["data"]
            data.update(retrieval_verified=False, recovery_failed=True)
        rechain_controller(base, rows)
    with pytest.raises((Halted, OSError, ValueError)):
        p.closed_receipt(tmp_path, "cheap", PLAN_HASH, FREEZE, smoke=True)


def rechain_controller(base, rows):
    from experiments.sae_assay_diagnostic.budget import _canonical
    import hashlib
    previous = None
    for row in rows:
        row["previous_sha256"] = previous
        row.pop("sha256", None)
        row["sha256"] = hashlib.sha256(_canonical(row)).hexdigest()
        previous = row["sha256"]
    (base/"events.jsonl").write_bytes(b"".join(_canonical(r)+b"\n" for r in rows))
    write(base/"final-retrieval.json", next(r for r in rows if r["id"] == "retrieval:6"))


def test_budget_guard_accounts_pending_reserves_and_full_http_horizon(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        request = runtime.judges.judge_request(plan["judges"]["astra"], "paper", "synthetic")
        runner.guard.before_call("judge", "screen", plan["judges"]["astra"], request)
        runner.ledger.spent = lambda: Decimal("15")
        with pytest.raises(Halted, match="pilot"):
            runner.guard.before_call("judge", "screen", plan["judges"]["astra"], request)
        runner.ledger.spent = lambda: Decimal("44.999")
        with pytest.raises(Halted, match="allowance"):
            runner.guard.before_call("judge", "main", plan["judges"]["astra"], request)
        runner.ledger.spent = lambda: Decimal(0)
        runner.guard.clock = lambda: NOW+timedelta(seconds=14650)
        with pytest.raises(Halted, match="deadline"):
            runner.guard.before_call("local", "main", plan["models"]["kolibri"], {})


def test_admission_uses_measured_runtime_and_controller_carry(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        runner.main_admission = Mock(return_value={"fits": True, "main_seconds_with_margin": "1200"})
        assert runner.guard.admission(runner)["fits"]
        evidence = runner.main_admission.call_args.kwargs
        assert Decimal(evidence["gpu_spent_usd"]) > Decimal(".25")
        assert evidence["remaining_overhead_seconds"] == "600"
        assert evidence["storage_bound_usd"] == "5"
        runner.main_admission.return_value["main_seconds_with_margin"] = "19000"
        with pytest.raises(Halted, match="controller allowance"):
            runner.guard.admission(runner)


def test_stop_marker_is_not_deletion_and_main_judging_requires_closed_receipt(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        runner.complete_generation = Mock(return_value={"generation_calls": 384, "complete": True})
        runner.judge_blocks = Mock()
        runner.complete = Mock()
        runner.rows = Mock(return_value=[{}]*256)
        with pytest.raises(KeyError):
            p.phase(runner, "judge-main", tmp_path)
        assert not runner.judge_blocks.called
        value = p.phase(runner, "stop-server", tmp_path)
        assert value["deletion_verified"] is False
        assert (tmp_path/"controller/main/STOP_SERVER").is_file()
        assert not (tmp_path/"controller/main/final-retrieval.json").exists()
        with pytest.raises(Halted, match="cleanup"):
            runner.guard.state(running=True)
        ledger = EventLedger(tmp_path/"controller/main/events.jsonl", PLAN_HASH, FREEZE, [])
        finish_controller(tmp_path, "main", ledger)
        assert p.phase(runner, "judge-main", tmp_path)["rows"] == 256
        runner.judge_blocks.assert_called_once_with("main", False)
        assert runner.guard.state()["active"] is False


def test_abort_preserves_incomplete_scientific_state(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        with pytest.raises(Halted):
            p.phase(runner, "stop-server", tmp_path)
        assert not (tmp_path/"controller/main/STOP_SERVER").exists()
        value = p.phase(runner, "stop-server", tmp_path, abort=True)
        assert value == {"operational_abort": True, "deletion_verified": False}
        assert not runner.receipts.records()


def reconciliation_record(root):
    write(root/"out/synthetic-budget.json", {"synthetic": True})
    return {"as_of": NOW.isoformat(), "openrouter_prior_and_reserved_usd": "136",
            "runpod_prior_and_reserved_usd": "50", "source_hashes": {
                "out/synthetic-budget.json": protocol.sha(root/"out/synthetic-budget.json")}}


@pytest.mark.parametrize("mutation", [None, "stale", "future", "api", "gpu", "absolute", "hash", "empty"])
def test_explicit_fresh_cumulative_reconciliation(tmp_path, plan, monkeypatch, mutation):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    record = reconciliation_record(tmp_path)
    if mutation in {"stale", "future"}:
        record["as_of"] = (NOW+timedelta(seconds=-901 if mutation == "stale" else 1)).isoformat()
    elif mutation in {"api", "gpu"}:
        record[("openrouter" if mutation == "api" else "runpod")+"_prior_and_reserved_usd"] = "199"
    elif mutation == "absolute":
        record["source_hashes"] = {str(tmp_path/"out/synthetic-budget.json"): "a"*64}
    elif mutation == "hash":
        record["source_hashes"]["out/synthetic-budget.json"] = "0"*64
    elif mutation == "empty":
        record["source_hashes"] = {}
    if mutation:
        with pytest.raises(Halted):
            p.reconciliation(plan, record, NOW)
    else:
        assert p.reconciliation(plan, record, NOW) == record


def test_read_only_audit_does_not_touch_saved_evidence(tmp_path, plan):
    plan_hash = runtime.sha((protocol.canonical(plan)+"\n").encode())
    write(tmp_path/"collection/PLAN.json", plan)
    write(tmp_path/"collection/runtime.json", p.binding(plan, FREEZE, plan_hash))
    with Ledger(tmp_path/"collection/judges", cap="45", screen_cap="10"), \
            runtime.ReceiptJournal(tmp_path/"collection/http", FREEZE, plan_hash):
        pass
    before = tree_hashes(tmp_path)
    with p.saved_runner(tmp_path, plan, FREEZE, plan_hash) as runner:
        assert runner.audit()["calls"] == 0
    assert tree_hashes(tmp_path) == before


@pytest.mark.parametrize("argv", [["--phase", "fixtures"], ["--phase", "audit", "--execute"],
    ["--phase", "fixtures", "--execute", "--run-dir", "/private/tmp/alternative"],
    ["--phase", "fixtures", "--execute", "--tokenizer-dir", "/private/tmp/tokenizer"],
    ["--phase", "audit", "--abort"]])
def test_cli_rejects_authority_or_reset_bypass_before_loading_secrets(monkeypatch, argv, capsys):
    key, verify = Mock(side_effect=AssertionError("must not load")), Mock(side_effect=AssertionError("must not verify"))
    monkeypatch.setattr(p, "local_key", key)
    monkeypatch.setattr(protocol, "verify", verify)
    with pytest.raises(SystemExit) as error:
        p.main(["--freeze", FREEZE, *argv])
    assert error.value.code == 1 and not key.called and not verify.called
    assert "failed closed" in capsys.readouterr().err


def test_cli_derived_context_audit_is_offline_only(tmp_path, plan, monkeypatch, capsys):
    write(tmp_path/protocol.PLAN, plan)
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    verify = Mock(return_value=plan)
    monkeypatch.setattr(protocol, "verify", verify)
    monkeypatch.setattr(p, "local_key", Mock(side_effect=AssertionError("no credentials")))
    monkeypatch.setattr(runtime, "http_sender", Mock(side_effect=AssertionError("no network")))
    runner = Mock()
    runner.serialization_audit.return_value = {"derived_not_raw": True, "contexts": []}
    @contextmanager
    def saved(*args):
        yield runner
    monkeypatch.setattr(p, "saved_runner", saved)
    directory = tmp_path/"tokenizer"
    assert p.main(["--phase", "audit", "--freeze", FREEZE, "--run-dir", str(tmp_path),
                   "--tokenizer-dir", str(directory)]) == 0
    runner.serialization_audit.assert_called_once_with(directory)
    assert not runner.audit.called and verify.call_args.args[1] is None
    assert json.loads(capsys.readouterr().out)["derived_not_raw"]


def test_main_admission_does_not_advance_or_rewrite_previous_decision(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        result = {"fits": True, "evidence": {"synthetic": True}}
        runner.guard.admission = Mock(return_value=result)
        runner.main_admission = Mock(return_value=result)
        runner.approve_main = lambda r: runner.receipts.append("decision", {"name": "main_admission", "value": r})
        runner.generate_blocks = Mock(side_effect=AssertionError("no automatic main"))
        assert p.phase(runner, "main-admission", tmp_path) == result
        assert p.phase(runner, "main-admission", tmp_path) == result
        assert len([e for e in runner.receipts.events if e["kind"] == "decision"]) == 2
        assert not runner.generate_blocks.called


def test_guard_failure_precedes_any_http_reservation(tmp_path, plan):
    local, judge, seen, paid = senders()
    with live_fixture(tmp_path, plan, local=local, judge=judge) as runner:
        runner.guard.before_call = Mock(side_effect=Halted("synthetic budget halt"))
        with pytest.raises(Halted):
            runner.run_fixtures()
        assert not runner.receipts.records() and not runner.ledger.rows()
        assert seen == paid == []


def test_mocked_cli_fixture_roundtrip_and_credential_free_audit(tmp_path, plan, monkeypatch, capsys):
    repo, root = tmp_path/"repo", tmp_path/"run"
    plan["launch_authorized"], plan["metadata_blockers"] = True, []
    write(repo/protocol.PLAN, plan)
    plan_hash = protocol.sha(repo/protocol.PLAN)
    saved_controller(root, "cheap", closed=True, plan_hash=plan_hash)
    saved_controller(root, "main", plan_hash=plan_hash)
    reconciliation = reconciliation_record(repo)
    write(repo/"reconciliation.json", reconciliation)
    monkeypatch.setattr(protocol, "ROOT", repo)
    verify = Mock(return_value=plan)
    monkeypatch.setattr(protocol, "verify", verify)
    monkeypatch.setattr(p.controller, "canonical_root", lambda: root)
    original_guard = p.StudyGuard
    monkeypatch.setattr(p, "StudyGuard", lambda *args: original_guard(*args, clock=lambda: NOW))
    original_reconcile = p.reconciliation
    monkeypatch.setattr(p, "reconciliation", lambda a, b, now: original_reconcile(a, b, NOW))
    key = Mock(return_value="synthetic-credential-never-printed")
    monkeypatch.setattr(p, "local_key", key)
    local, judge, seen, paid = senders()
    def factory(endpoint, *, timeout_seconds, api_key=None):
        if endpoint == p.ENDPOINT:
            assert timeout_seconds == 600 and api_key == key.return_value
            return judge
        assert endpoint == "http://127.0.0.1:12345/v1/chat/completions"
        assert timeout_seconds == 300 and api_key is None
        return local
    transport = Mock(side_effect=factory)
    monkeypatch.setattr(runtime, "http_sender", transport)
    args = ["--freeze", FREEZE, "--execute", "--phase", "fixtures", "--port", "12345",
            "--reconciliation", str(repo/"reconciliation.json")]
    assert p.main(args) == 0
    verify.assert_called_with(repo/protocol.PLAN, FREEZE)
    assert len(seen) == 1 and len(paid) == 24 and key.call_count == 1
    assert "synthetic-credential" not in capsys.readouterr().out
    before = tree_hashes(root)
    key.reset_mock(); transport.reset_mock()
    assert p.main(["--freeze", FREEZE, "--run-dir", str(root)]) == 0
    verify.assert_called_with(repo/protocol.PLAN, None)
    assert not key.called and not transport.called and tree_hashes(root) == before
    assert p.main(["--freeze", FREEZE, "--execute", "--phase", "stop-server", "--abort"]) == 0
    verify.assert_called_with(repo/protocol.PLAN, None)
    assert not key.called and not transport.called
    assert (root/"controller/main/STOP_SERVER").is_file()


def test_missing_controller_evidence_is_not_created(tmp_path):
    before = tree_hashes(tmp_path)
    with pytest.raises(OSError):
        p.controller_events(tmp_path, "main", PLAN_HASH, FREEZE)
    assert tree_hashes(tmp_path) == before


def test_incomplete_main_forecast_never_approves_or_dispatches(tmp_path, plan):
    with live_fixture(tmp_path, plan) as runner:
        runner.guard.admission = Mock(return_value={"fits": False})
        runner.approve_main = Mock()
        runner.generate_blocks = Mock()
        for name in ("main-admission", "generate-main"):
            with pytest.raises(Halted):
                p.phase(runner, name, tmp_path)
        assert not runner.approve_main.called and not runner.generate_blocks.called


@pytest.mark.parametrize("bound", [True, False])
def test_metadata_accounting_basis_outside_data_requires_exact_freeze(tmp_path, plan, monkeypatch, bound):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    record = reconciliation_record(tmp_path)
    name = "experiments/kolibri_swap/budget_basis.json"
    write(tmp_path/name, {"synthetic_accounting": True})
    digest = protocol.sha(tmp_path/name)
    record["source_hashes"] = {name: digest}
    plan["metadata"]["spend_reconciliation"] = record
    if bound:
        plan["source_hashes"][name] = digest
        assert p.reconciliation(plan, record, NOW) == record
    else:
        with pytest.raises(Halted, match="Unsafe"):
            p.reconciliation(plan, record, NOW)


def test_actual_controller_stop_retrieval_deletion_precedes_judge_main(controller_setup, monkeypatch):
    ctl, api, _ = owned(controller_setup)
    ctl.ledger.bind("worker-intent", {"sha256": "c"*64, "seconds": 3600})
    ctl.ledger.bind("worker-started", {"pod_id": api.pod["id"]})
    observed = []
    files = {"worker.log": b"synthetic shutdown\r\n", "exit.json": b'{"exit_code":143}\n'}
    hashes = {n: runtime.sha(value) for n, value in files.items()}
    raw = tar_bytes([(n, value, tarfile.REGTYPE) for n, value in files.items()])
    def ssh(pod, command, **kwargs):
        assert pod["id"] == api.pod["id"]
        if command == p.controller.bootstrap.stop_command(ctl.plan_hash):
            observed.append("worker_stopped")
            return json.dumps({"stopped": True, "binding": ctl.plan_hash}).encode()
        if command == p.controller.artifact_command():
            observed.append("manifest")
            return json.dumps(hashes).encode()
        if command == p.controller.artifact_command(pack=True):
            observed.append("archive")
            return raw
        assert command == "mkdir -p /workspace/kolibri/out"
        return b""
    monkeypatch.setattr(ctl, "_ssh", ssh)
    monkeypatch.setattr(ctl, "status", lambda: {"pod": api.pod, "worker": {"ready": True}})
    original_request = api.request
    def request(method, path, body=None):
        if method == "DELETE":
            assert observed == ["worker_stopped", "manifest", "archive", "manifest"]
            observed.append("delete")
        return original_request(method, path, body)
    monkeypatch.setattr(api, "request", request)
    runner = Mock(freeze=ctl.freeze, plan_hash=ctl.plan_hash)
    runner.receipts.decision.return_value = None
    runner.complete_generation.return_value = {"complete": True, "generation_calls": 384}
    runner.audit.return_value = {"pass": True}
    runner.rows.return_value = [{}]*256
    assert p.phase(runner, "stop-server", ctl.out)["deletion_verified"] is False
    assert not api.deleted
    assert ctl.monitor()["data"]["get_status"] == 404 and api.deleted
    closed = p.closed_receipt(ctl.out, "main", ctl.plan_hash, ctl.freeze)
    assert closed["retrieval_sha256"] == ctl._verify_final()["sha256"]
    def judged(*args):
        assert api.deleted and ctl.event("closed")["data"]["get_status"] == 404
        observed.append("judged")
    runner.judge_blocks.side_effect = judged
    assert p.phase(runner, "judge-main", ctl.out)["rows"] == 256
    assert observed[-2:] == ["delete", "judged"]
