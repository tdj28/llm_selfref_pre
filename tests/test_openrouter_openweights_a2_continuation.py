"""Offline continuation QA using the immutable real A1 prefix and fake new calls."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil
import socket

import pytest

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Halted, BudgetExceeded, read_events
from experiments.openrouter_swap.providers import generation_request, TransportError
from experiments.openrouter_swap.release import _inventory
from experiments.openrouter_swap_openweights_a1 import production as a1
from experiments.openrouter_swap_openweights_a2 import production as prod, protocol as p, release
from experiments.openrouter_swap_openweights_a2.ledger import DeltaLedger, CompositeLedger, ReplayDelta
from experiments.openrouter_swap_openweights_a2.prefix import Prefix, sha
from experiments.openrouter_swap_openweights_a2.runner import ContinuationRunner, reservation, private_request
from tests.test_openrouter_openweights_a1_production import inputs
from tests.test_openrouter_swap_runner import make_sender

FREEZE = "f" * 40


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def budget(**changes):
    return p.Budget(**{**dict(scope="OpenRouter October4 continuation only", working_cap_usd="200",
        hard_cap_usd="200", prior_spend_usd=str(p.PRIOR), external_commitments_usd="0",
        screening_allowance_usd=str(p.SCREEN)), **changes})


def values(b):
    result = inputs(b)
    result["authorization"]["new_target_outcomes_seen"] = True
    result["reconciliation"]["prior_costs"] = [{"id": "openweights-a1-through-initial-failure",
        "cost_bound_usd": str(p.PRIOR), "evidence_sha256": p.FAILURE_SHA}]
    result["reconciliation"]["external_commitments"] = []
    return result


@pytest.fixture(scope="module")
def history():
    snapshot = prod.canonical_root().with_name("openrouter-openweights-a1-failure-snapshot")
    if not snapshot.exists():
        snapshot = common.ROOT / p.FAILURE
    raw_name = "raw/events.jsonl" if (snapshot / "raw/events.jsonl").exists() else "raw/events.jsonl.gz"
    before = {n: (snapshot / n).read_bytes() for n in ("PLAN.json", "runtime.json", "fixture_gate.json", raw_name)}
    prefix = Prefix(snapshot)
    yield prefix
    assert all((snapshot / n).read_bytes() == raw for n, raw in before.items())


@pytest.fixture(scope="module")
def parent_evidence():
    return prod.failure_evidence()


@pytest.fixture
def frozen(tmp_path, monkeypatch, parent_evidence):
    # No actual plan is written; parent test/source hashes are frozen only later.
    evidence, prefix = parent_evidence
    monkeypatch.setattr(prod, "failure_evidence", lambda: (deepcopy(evidence), prefix))
    name = "experiments/openrouter_swap_openweights_a2/protocol.py"
    blob = (common.ROOT / name).read_bytes()
    monkeypatch.setattr(prod, "source_hashes", lambda: {name: sha(blob)})
    plan = prod.finalize(p.build_draft(budget=budget()), **values(budget()))
    def git(*args):
        if args[0] == "merge-base": return b""
        assert args[0] == "show"
        commit, path = args[1].split(":", 1)
        assert commit == FREEZE
        if path == prod.PLAN: return (common.canonical(plan) + "\n").encode()
        if path == name: return blob
        assert path.startswith(p.FAILURE + "/")
        return (common.ROOT / path).read_bytes()
    monkeypatch.setattr(prod, "git", git)
    return plan


def synthetic_sender(plan, prefix):
    fixture = {i["id"]: i for i in plan["fixtures"]}
    positive, negative = fixture["fixture-explicit"]["response"], fixture["fixture-denial"]["response"]
    generations = {}
    for phase in ("screen", "main"):
        for block in plan[phase]:
            spec = plan["models"][block["model"]]
            donors = {}
            for item in block["sources"]:
                text = positive if item["transcript"] == "self" else negative
                old = prefix.existing("gen:" + item["id"])
                donors[item["id"]] = old["raw"]["choices"][0]["message"]["content"] if old else text
                request = private_request(generation_request(spec, common.messages(item)))
                generations[common.canonical(request)] = text
            for item in block["finals"]:
                request = private_request(generation_request(spec, common.messages(item, donors[item["source_id"]])))
                generations[common.canonical(request)] = positive if item["instruction"] == "self" else negative
    judge, _ = make_sender()
    specs = {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}
    sent = []
    def send(request):
        sent.append(deepcopy(request))
        assert request["provider"]["zdr"] is True and request["provider"]["data_collection"] == "deny"
        assert request["provider"]["allow_fallbacks"] is False
        spec = specs[request["model"]]
        if request["model"] in {s["id"] for s in plan["judges"].values()}:
            raw = judge(request); raw["provider"] = spec["provider_name"]
        else:
            raw = {"id": "synthetic-a2-" + str(len(sent)), "model": spec["id"], "provider": spec["provider_name"],
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": generations[common.canonical(request)]}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
        if request["model"] == p.MODELS["mistral"]["id"]:
            raw["usage"]["completion_tokens_details"] = {"reasoning_tokens": 0}
        return raw
    return send, sent


def launch(root, plan, runtime, phase):
    row = {"phase": phase, "proof": {"freeze": FREEZE, "branch": prod.BRANCH, "remote_head": FREEZE},
        "reconciliation": plan["reconciliation"], "plan_sha256": runtime["plan_sha256"],
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_count_before": len(read_events(root / "raw/events.jsonl")), "a1_prefix_sha256": p.PREFIX["journal_sha256"]}
    prod.write_once(root / "launches" / (common.digest(row) + ".json"), row)


def initial_run(root, plan, prefix):
    runtime = prod.runtime_for(plan, FREEZE)
    prod.write_once(root / "PLAN.json", plan); prod.write_once(root / "runtime.json", runtime)
    cap, screen = budget().limits()
    sender, sent = synthetic_sender(plan, prefix)
    with DeltaLedger(root / "raw", prefix, cap=cap, screen_cap=screen) as delta:
        runner = ContinuationRunner(plan, FREEZE, runtime["plan_sha256"], CompositeLedger(prefix, delta), sender)
        launch(root, plan, runtime, "screen-initial")
        runner.run_blocks("screen", initial=True)
        prod.write_once(root / "initial_audit.json", prod.checkpoint(root, runner, "initial_audit"))
        audit = runner.audit()
    return runtime, sent, audit


def rehash(root):
    (root / "MANIFEST.json").unlink()
    prod.write_once(root / "MANIFEST.json", {"schema": "openweights-a2-manifest-v1", "files": release._entries(_inventory(root))})


def test_exact_actual_prefix_is_read_only_and_fixtures_are_prefix_bound(history):
    assert len(history.rows()) == 92 and history.spent() == p.PREFIX_COST
    assert history.gate["pass"] and history.audit["pass"]
    assert sha(history.raw) == p.PREFIX["journal_sha256"]
    row = history.existing(p.EXCEPTION["call_id"])
    assert row["over_reservation"] and history.acknowledged(row)
    row["raw_sha256"] = "0" * 64
    assert not history.acknowledged(row)


def test_initial_continuation_sends_only_absent_calls_preserves_missing(tmp_path, frozen, history):
    root = tmp_path / "run"
    runtime, sent, audit = initial_run(root, frozen, history)
    assert len(sent) == audit["delta_calls"] == 14
    assert audit["calls"] == 106 and audit["prefix_calls"] == 92
    delta = ReplayDelta((root / "raw/events.jsonl").read_bytes(), history, cap=budget().limits()[0], screen_cap=p.SCREEN)
    ledger = CompositeLedger(history, delta)
    old = {r["call_id"]: r for r in history.rows()}
    assert all(ledger.existing(cid) == row for cid, row in old.items())
    assert not set(old) & {r["call_id"] for r in delta.rows()}
    assert all(r["metadata"]["freeze"] == FREEZE and r["metadata"]["plan_sha256"] == runtime["plan_sha256"] for r in delta.rows())
    runner = ContinuationRunner(frozen, FREEZE, runtime["plan_sha256"], ledger)
    missing = {r["id"] for r in runner.rows("screen") if r["cap_hit"] and r["response"] is None}
    assert {p.EXCEPTION["call_id"][4:], "openweights-screen-mistral-01-final-HS"} <= missing
    assert runner.require_fixtures() == history.gate
    runner.run_blocks("screen", initial=True)
    assert delta.spent() + p.PREFIX_COST == Decimal(audit["cost_bound_usd"])
    assert p.PRIOR + delta.spent() == Decimal(audit["scope_cost_plus_commitments_usd"])
    prod.verify_checkpoint((root / "raw/events.jsonl").read_bytes(), json.loads((root / "initial_audit.json").read_text()), frozen, runtime, "initial_audit", history)


def test_new_reserve_is_four_caps_and_not_new_generation_limit(history):
    row = history.existing(p.EXCEPTION["call_id"])
    assert reservation(p.MODELS["mistral"], row["request"]) == Decimal(".13071")
    assert row["request"]["max_tokens"] == 4096 and row["reservation_usd"] == "0.06927"


@pytest.mark.parametrize("field,value", [("prior_spend_usd", "84.64275336"), ("screening_allowance_usd", "24.4449541"),
                                       ("hard_cap_usd", "201"), ("working_cap_usd", "201")])
def test_no_budget_reset(field, value):
    with pytest.raises((Halted, ValueError)):
        p.build_draft(budget=budget(**{field: value}))


def test_forecast_uses_prefix_observations_but_never_double_charges():
    b = p.ForecastBudget(**budget().__dict__)
    result = b.admission(spent_usd=p.PREFIX_COST + Decimal("2"), remaining_usd="3")
    assert Decimal(result["scope_completion_usd"]) == p.PRIOR + 5
    assert Decimal(result["extension_completion_usd"]) == 5
    assert Decimal(result["observed_prefix_and_delta_usd"]) == p.PREFIX_COST + 2
    with pytest.raises(Halted): b.admission(spent_usd="0", remaining_usd="1")


@pytest.mark.parametrize("change", ["outcomes", "cap", "privacy", "family", "endpoint", "reconciliation", "prefix"])
def test_finalizer_rejects_scope_drift(tmp_path, frozen, change):
    draft = p.build_draft(budget=budget()); data = values(budget())
    if change == "outcomes": data["authorization"]["new_target_outcomes_seen"] = False
    if change == "cap": draft["generation_output_cap"] = 8192
    if change == "privacy": draft["privacy"]["zdr"] = False
    if change == "family": draft["primary_family_size"] = 2
    if change == "endpoint": data["endpoint_evidence"][p.JUDGES["opus"]["id"]]["spec"]["provider_slug"] = "other"
    if change == "reconciliation": data["reconciliation"]["prior_costs"][0]["cost_bound_usd"] = "0"
    if change == "prefix": draft["amendment"]["prefix"]["calls"] = 0
    with pytest.raises((Halted, ValueError)):
        prod.finalize(draft, **data)


def test_finalization_requires_finished_parent_release(monkeypatch):
    def missing(): raise Halted("parent not ready")
    monkeypatch.setattr(prod, "failure_evidence", missing)
    with pytest.raises(Halted, match="parent not ready"):
        prod.finalize(p.build_draft(budget=budget()), **values(budget()))


def test_duplicate_fixture_and_holdback_guard_before_dispatch(tmp_path, frozen, history):
    cap, screen = budget().limits()
    old = history.rows()[0]
    with DeltaLedger(tmp_path / "raw", history, cap=cap, screen_cap=screen) as delta:
        with pytest.raises(Halted): delta.reserve(old["call_id"], old["request"], old["reservation_usd"], old["phase"], old["metadata"])
        with pytest.raises(Halted): delta.reserve("new-fixture", old["request"], "1", "fixtures", {})
        delta.holdback = cap
        with pytest.raises(BudgetExceeded): delta.reserve("new-screen", old["request"], "1", "screen", {})
        assert not delta.rows()


@pytest.mark.parametrize("bad", ["overrun", "unknown", "provider", "credential"])
def test_unexpected_new_accounting_or_identity_failure_stops_and_keeps_cost(tmp_path, frozen, history, bad):
    runtime = prod.runtime_for(frozen, FREEZE)
    good, sent = synthetic_sender(frozen, history)
    def broken(request):
        if bad == "credential": raise TransportError()
        raw = good(request)
        if bad == "overrun": raw["usage"]["cost"] = "1"
        if bad == "unknown": raw["usage"].pop("total_tokens")
        if bad == "provider": raw["provider"] = "Foreign"
        return raw
    cap, screen = budget().limits()
    with DeltaLedger(tmp_path / "raw", history, cap=cap, screen_cap=screen) as delta:
        runner = ContinuationRunner(frozen, FREEZE, runtime["plan_sha256"], CompositeLedger(history, delta), broken)
        spec = next(s for b in frozen["screen"] for s in b["finals"] if s["id"] == "openweights-screen-mistral-02-final-SS")
        donor = runner.parsed_call("gen:" + spec["source_id"], p.MODELS["mistral"])["response"]
        with pytest.raises(Halted): runner.generate(spec, donor)
        row = delta.rows()[0]
        assert Decimal(row["cost_usd"]) >= Decimal(row["reservation_usd"])
        with pytest.raises(Halted): runner.require_resolved()
        with pytest.raises(Halted): runner.run_blocks("screen", initial=True)
        assert len(delta.rows()) == 1
        if bad == "overrun": assert row["over_reservation"] and row["cost_usd"] == "1"


def test_end_to_end_partial_release_preserves_both_journals_and_missingness(tmp_path, frozen, history):
    root, target = tmp_path / "run", tmp_path / "release"
    initial_run(root, frozen, history)
    before = (root / "raw/events.jsonl").read_bytes()
    result = release.build(root, target)
    assert result["pass"] and result["status"] == "incomplete"
    assert (root / "raw/events.jsonl").read_bytes() == before
    assert gzip.decompress((target / "raw/events.jsonl.gz").read_bytes()) == before
    assert gzip.decompress((target / "prefix/raw/events.jsonl.gz").read_bytes()) == history.raw
    for name in ["MANIFEST.json", *_inventory(common.ROOT / p.FAILURE)]:
        assert (target / "prefix" / name).read_bytes() == (common.ROOT / p.FAILURE / name).read_bytes()
    report = json.loads((target / "RELEASE.json").read_text())
    assert report["fixtures_pass"] and report["main_status"] == "not_run"
    assert report["audit"]["calls"] == 106 and report["primary_family_size"] == 4
    assert release.verify(target, manifest_sha256=result["manifest_sha256"])["pass"]


def test_full_fixed_screen_forecasts_and_conditional_main_use_all_observations(tmp_path, frozen, history):
    root, target = tmp_path / "run", tmp_path / "release"
    runtime, _, _ = initial_run(root, frozen, history)
    sender, sent = synthetic_sender(frozen, history)
    cap, screen = budget().limits()
    with DeltaLedger(root / "raw", history, cap=cap, screen_cap=screen) as delta:
        runner = ContinuationRunner(frozen, FREEZE, runtime["plan_sha256"], CompositeLedger(history, delta), sender)
        launch(root, frozen, runtime, "screen")
        runner.run_blocks("screen"); runner.complete("screen")
        screen_observed = runner.ledger.spent()
        checkpoint = prod.checkpoint(root, runner, "main_admission")
        admission = checkpoint["value"]
        assert admission["admitted_models"]
        assert Decimal(admission["completion_budget"]["observed_prefix_and_delta_usd"]) == screen_observed
        assert Decimal(admission["completion_budget"]["scope_completion_usd"]) == (
            p.PRIOR + delta.spent() + sum((Decimal(admission["projections"][m]["projected_cost_with_reserve_usd"])
                                          for m in admission["admitted_models"]), Decimal(0)))
        prod.write_once(root / "main_admission.json", checkpoint)
        launch(root, frozen, runtime, "main")
        runner.run_blocks("main")
        runner.complete("main", models=admission["admitted_models"])
        assert delta.holdback == 0 and runner.audit()["unresolved"] == 0
        assert not {r["call_id"] for r in history.rows()} & {r["call_id"] for r in delta.rows()}
    assert sent
    assert release.build(root, target)["pass"]
    report = json.loads((target / "RELEASE.json").read_text())
    assert report["collection_complete"] == {"screen": True, "main": True}
    assert report["main_status"] == "completed"
    assert len(json.loads((target / "main_rows.json").read_text())) == 512


@pytest.mark.parametrize("location", ["key", "value", "nested"])
def test_actual_credential_guard_runs_before_storage(tmp_path, frozen, history, monkeypatch, location):
    credential = "synthetic-a2-credential-sentinel"
    sender, _ = synthetic_sender(frozen, history)
    def leaked(request):
        raw = sender(request)
        raw["extra"] = {credential: "value"} if location == "key" else {"value": credential} if location == "value" else [{"list": [credential]}]
        return json.loads(json.dumps(raw).replace(credential, "".join(f"\\u{ord(c):04x}" for c in credential)))
    monkeypatch.setattr(a1, "live_sender", lambda key: leaked)
    cap, screen = budget().limits()
    runtime = prod.runtime_for(frozen, FREEZE)
    with DeltaLedger(tmp_path / "raw", history, cap=cap, screen_cap=screen) as delta:
        runner = ContinuationRunner(frozen, FREEZE, runtime["plan_sha256"], CompositeLedger(history, delta), prod.guarded_sender(credential))
        spec = next(s for b in frozen["screen"] for s in b["finals"] if s["id"] == "openweights-screen-mistral-02-final-SS")
        donor = runner.parsed_call("gen:" + spec["source_id"], p.MODELS["mistral"])["response"]
        with pytest.raises(Halted): runner.generate(spec, donor)
        assert delta.rows()[0]["raw"] is None
    assert credential not in (tmp_path / "raw/events.jsonl").read_text()


def test_a2_original_epoch_must_verify_before_detached_projection(tmp_path, frozen, history):
    root = tmp_path / "run"
    runtime, _, _ = initial_run(root, frozen, history)
    raw = (root / "raw/events.jsonl").read_bytes()
    delta = ReplayDelta(raw, history, cap=budget().limits()[0], screen_cap=p.SCREEN)
    row = next(iter(delta._calls.values()))
    row["metadata"].update(freeze=p.PREFIX["freeze"], plan_sha256=p.PREFIX["plan_sha256"])
    runner = ContinuationRunner(frozen, FREEZE, runtime["plan_sha256"], CompositeLedger(history, delta))
    with pytest.raises(Halted, match="epoch binding"):
        runner.audit()


@pytest.mark.parametrize("change", ["raw", "report", "prefix", "runtime", "gate", "extra", "manifest_bool"])
def test_rehashed_tamper_and_inventory_fail(tmp_path, frozen, history, change):
    root, target = tmp_path / "run", tmp_path / "release"
    initial_run(root, frozen, history); release.build(root, target)
    if change == "extra": prod.write_once(target / "unapproved.json", {})
    elif change == "raw":
        path = target / "raw/events.jsonl.gz"
        raw = gzip.decompress(path.read_bytes()); events = [json.loads(s) for s in raw.splitlines()]
        events[-1]["data"]["cost_usd"] = "0"
        from experiments.openrouter_swap.ledger import digest
        for i, event in enumerate(events):
            event["previous"] = events[i-1]["sha256"] if i else None
            event["sha256"] = digest({k: v for k, v in event.items() if k != "sha256"})
        path.write_bytes(gzip.compress(b"".join((common.canonical(e)+"\n").encode() for e in events), mtime=0))
    elif change == "manifest_bool":
        manifest = json.loads((target / "MANIFEST.json").read_text()); manifest["files"][0]["bytes"] = True
        (target / "MANIFEST.json").unlink(); prod.write_once(target / "MANIFEST.json", manifest)
    else:
        name, key, value = {"report": ("RELEASE.json", "fixtures_pass", False),
            "prefix": ("prefix/fixture_gate.json", "pass", False),
            "runtime": ("runtime.json", "freeze", "e"*40),
            "gate": ("initial_audit.json", "event_count", 1)}[change]
        path = target / name; data = json.loads(path.read_text()); data[key] = value
        path.unlink(); prod.write_once(path, data)
    if change != "manifest_bool": rehash(target)
    with pytest.raises((Halted, ValueError, AssertionError)):
        release.verify(target)


def test_cli_denies_alternate_delta_and_fixtures_before_credentials(monkeypatch, capsys):
    loaded = []
    monkeypatch.setattr(prod, "load_key", lambda *_: loaded.append(True))
    for argv in (["--launch", "--phase", "screen", "--run-dir", "/tmp/elsewhere"],
                 ["--phase", "screen"], ["--launch", "--phase", "fixtures"]):
        with pytest.raises(SystemExit): prod.main(argv)
    assert not loaded and "OPENROUTER" not in capsys.readouterr().out
