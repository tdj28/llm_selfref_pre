"""Synthetic offline publication QA, not scientific or provider validation."""

from datetime import datetime, timezone
from copy import deepcopy
from decimal import Decimal
import gzip
import json
import socket
from uuid import uuid4

import pytest

from experiments import repeat_funding_release_a1 as adapter
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import TransportError
from experiments.repeated_swap.runner import Runner, StudyLedger
from tests.test_repeated_swap_release import case, _sender, _write

base, funding, p = adapter.base, adapter.funding, adapter.p


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network and paid execution forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(funding, "execute", forbidden)
    monkeypatch.setattr(adapter.a2, "execute", forbidden)
    monkeypatch.setattr(adapter.a3, "execute", forbidden)
    monkeypatch.setattr(base.production, "account_balance", forbidden)


@pytest.fixture
def funding_case(case, monkeypatch):
    root, plan, runtime, blobs = case
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan))
        _write(root / "fixture_gate.json", runner.run_fixtures())
        runner.run_blocks("main", initial=True)
        forecast = runner.admission("1000")
        remaining = sum(map(Decimal, forecast["remaining_forecast_with_30pct_reserve_usd"].values()))
        old = runner.admission(str(Decimal("45") + remaining / Decimal("1.30") * Decimal("1.20")))
        raw = (root / "raw/events.jsonl").read_bytes()
        prefix = {"bytes": len(raw), "sha256": base._sha(raw), "calls": len(ledger.rows())}
        old["journal_prefix"] = prefix
        assert old["pass"] is False
        _write(root / "admission.json", old)
    monkeypatch.setattr(funding, "ROOT", p.ROOT)
    monkeypatch.setattr(funding, "OLD_FREEZE", runtime["freeze"])
    monkeypatch.setattr(funding, "OLD_PLAN_SHA", runtime["plan_sha256"])
    monkeypatch.setattr(funding, "PREFIX", prefix)
    monkeypatch.setattr(funding, "FAILED_SHA", p.sha(root / "admission.json"))
    monkeypatch.setattr(funding, "NEW_SOURCES", ("synthetic_funding.py",))
    (p.ROOT / "synthetic_funding.py").write_text("# SYNTHETIC funding source for offline QA.\n")
    (p.ROOT / funding.ANCHOR).parent.mkdir(parents=True, exist_ok=True)
    (p.ROOT / funding.ANCHOR).write_bytes((root / "admission.json").read_bytes())
    blobs[funding.ANCHOR] = (root / "admission.json").read_bytes()
    blobs["synthetic_funding.py"] = (p.ROOT / "synthetic_funding.py").read_bytes()
    monkeypatch.setattr(funding, "git_blob", lambda freeze, name: blobs[name])
    amended = funding.build_plan()
    _write(p.ROOT / funding.PLAN, amended)
    blobs[funding.PLAN] = (p.ROOT / funding.PLAN).read_bytes()
    monkeypatch.setattr(adapter, "_ancestor", lambda old, new: old == runtime["freeze"] and new == "b" * 40)
    binding = {"original_science_freeze": runtime["freeze"], "original_plan_sha256": runtime["plan_sha256"],
               "actual_operational_freeze": "b" * 40, "amendment_plan_sha256": p.sha(p.ROOT / funding.PLAN)}
    _write(root / "funding_a1/runtime.json", binding)
    _write(root / "funding_a1/admission.json", amended["admission"])
    return case, binding


def _head(root, ledger):
    raw = (root / "raw/events.jsonl").read_bytes()
    return {"bytes": len(raw), "sha256": base._sha(raw), "calls": len(ledger.rows())}


def _collect(funding_case, *, full=False, failure=False, finish=True, funded=True, dispatch=True):
    (root, plan, runtime, _), binding = funding_case
    folder = root / "funding_a1/launches" / ("c" * 32)
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan))
        _write(folder / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(),
                                      "journal_before": _head(root, ledger), "outcome_selection": False})
        balance = "1000" if funded else "45.0001"
        _write(folder / "funding" / ("d" * 32 + ".json"), {**binding,
            "utc": datetime.now(timezone.utc).isoformat(), "balance_usd": balance, "external_holdback_usd": "45",
            "spent_and_reserved_usd": str(ledger.spent()), "funded_limit_usd": str(funding.funding_limit(ledger, balance))})
        if full:
            runner.run_blocks("main")
        elif dispatch:
            item = next(b for b in plan["main"] if b["block"] == 3)["sources"][0]
            if failure:
                def fail(request):
                    raise TimeoutError("SYNTHETIC PRIVATE TRANSPORT TEXT")
                runner.sender = fail
                with pytest.raises(Halted): runner.generate(item)
            else:
                runner.generate(item)
        if finish:
            _write(folder / "finish.json", {**binding, "complete": full, "journal_after": _head(root, ledger),
                                           "spent_and_reserved_usd": str(ledger.spent())})
    return folder


def _rehash(target):
    _write(target / "MANIFEST.json", {"schema": adapter.MANIFEST_SCHEMA, "files": base._entries(target)})


def test_admitted_not_launched_retains_failed_admission_and_raw_identity(funding_case, tmp_path):
    (root, _, _, _), binding = funding_case
    raw, old = (root / "raw/events.jsonl").read_bytes(), (root / "admission.json").read_bytes()
    (root / ".env").write_text("PRIVATE_SENTINEL=must-not-copy\n")
    target = tmp_path / "release"
    verdict = adapter.build(target)
    assert verdict["pass"] and verdict["status"] == "incomplete"
    assert gzip.decompress((target / "raw/events.jsonl.gz").read_bytes()) == raw
    assert (target / "admission.json").read_bytes() == (target / "funding_a1/FAILED_ADMISSION.json").read_bytes() == old
    assert not (target / ".env").exists()
    info = base._load(target / "RELEASE.json")
    assert info["original_admission_pass"] is False and info["amended_admission_pass"] is True
    assert info["scientific_freeze"] != info["operational_freeze"] == binding["actual_operational_freeze"]
    assert not info["collection_complete"] and not info["terminal_receipt_complete"]
    assert (root / "admission.json").read_bytes() == old and (root / "raw/events.jsonl").read_bytes() == raw
    assert adapter.verify(target, manifest_sha256=verdict["manifest_sha256"])["pass"]
    with pytest.raises(Halted): base.verify(target)


@pytest.mark.parametrize("finish", [True, False])
def test_partial_transport_failure_preserves_missingness_and_reservation(funding_case, tmp_path, finish):
    _collect(funding_case, failure=True, finish=finish)
    target = tmp_path / "release"
    verdict = adapter.build(target)
    info = base._load(target / "RELEASE.json")
    assert verdict["status"] == "incomplete" and verdict["unresolved"] == 1
    assert info["unknown_charges_are_reserved"] and not info["collection_complete"]
    assert info["primary_family_size"] == 2 and info["primary_individual_confidence"] == .975
    sequence = base._load(target / "funding_audit.json")
    assert sequence["original_admission_pass"] is False
    assert sequence["launches"][0]["finish_present"] is finish
    assert b"SYNTHETIC PRIVATE TRANSPORT TEXT" not in gzip.decompress((target / "raw/events.jsonl.gz").read_bytes())


def test_funding_stop_before_dispatch_is_an_honest_partial_release(funding_case, tmp_path):
    _collect(funding_case, funded=False, dispatch=False)
    target = tmp_path / "release"
    assert adapter.build(target)["status"] == "incomplete"
    assert base._load(target / "RELEASE.json")["journal"]["calls"] == funding.PREFIX["calls"]


def test_full_panel_keeps_frozen_analysis_and_two_model_family(funding_case, tmp_path):
    _collect(funding_case, full=True)
    target = tmp_path / "release"
    assert adapter.build(target)["status"] == "complete"
    info, report = base._load(target / "RELEASE.json"), base._load(target / "analysis.json")
    assert info["original_admission_pass"] is False and info["amended_admission_pass"] is True
    assert info["collection_complete"] and info["terminal_receipt_complete"]
    assert report["primary_family_size"] == 2
    for model in p.MODELS:
        view = report["models"][model]["judges"]["astra"]["inclusive_current_assertion"]
        assert view["contrasts"]["instruction_minus_transcript"]["bootstrap"]["confidence"] == .975
        assert view["cells"]["SH"]["observed"] == 96
        assert view["wording_strata"]["a"]["variance"]["SH"]["complete_requests"] == 16


@pytest.mark.parametrize("change", ["old_pass", "new_admission", "science_freeze", "runtime_freeze", "start_hash",
                                  "start_calls", "late_launch", "start_binding", "finish_cost", "false_complete",
                                  "holdback", "balance", "limit", "missing_funding", "missing_launch"])
def test_sequence_and_financial_tamper_rejected(funding_case, tmp_path, change):
    folder = _collect(funding_case)
    root = funding_case[0][0]
    path = folder / "start.json"
    if change == "old_pass": path = root / "admission.json"
    if change == "new_admission": path = root / "funding_a1/admission.json"
    if change in {"science_freeze", "runtime_freeze"}: path = root / "funding_a1/runtime.json"
    if change in {"finish_cost", "false_complete"}: path = folder / "finish.json"
    if change in {"holdback", "balance", "limit", "missing_funding"}: path = folder / "funding" / ("d" * 32 + ".json")
    row = base._load(path)
    if change == "old_pass": row["pass"] = True
    if change == "new_admission": row["remaining_forecast_usd"] = "0"
    if change == "science_freeze": row["original_science_freeze"] = "b" * 40
    if change == "runtime_freeze": row["actual_operational_freeze"] = "a" * 40
    if change == "start_hash": row["journal_before"]["sha256"] = "0" * 64
    if change == "start_calls": row["journal_before"]["calls"] += 1
    if change == "late_launch": row["journal_before"] = base._load(folder / "finish.json")["journal_after"]
    if change == "start_binding": row["actual_operational_freeze"] = "e" * 40
    if change == "finish_cost": row["spent_and_reserved_usd"] = "0"
    if change == "false_complete": row["complete"] = True
    if change == "holdback": row["external_holdback_usd"] = "0"
    if change == "balance": row["balance_usd"] = "45.0001"
    if change == "limit": row["funded_limit_usd"] = "200"
    _write(path, row)
    if change == "missing_funding": path.unlink()
    if change == "missing_launch": (folder / "start.json").unlink()
    with pytest.raises((Halted, OSError)): adapter.build(tmp_path / "blocked")


@pytest.mark.parametrize("name", ["RELEASE.json", "funding_audit.json", "analysis.json"])
def test_rehashed_derived_payload_is_not_trusted(funding_case, tmp_path, name):
    target = tmp_path / "release"
    adapter.build(target)
    value = base._load(target / name); value["invented"] = True
    _write(target / name, value); _rehash(target)
    with pytest.raises(Halted, match="reconstruct"): adapter.verify(target)


@pytest.mark.parametrize("extra", [".env", "funding_a1/private.json", "funding_a1/empty"])
def test_rehashed_unwanted_inventory_rejected(funding_case, tmp_path, extra):
    target = tmp_path / "release"
    adapter.build(target)
    path = target / extra
    path.mkdir() if extra.endswith("empty") else path.write_text("PRIVATE_SENTINEL")
    _rehash(target)
    with pytest.raises(Halted, match="Unexpected"): adapter.verify(target)


def test_raw_prefix_tamper_rejected_after_rehash(funding_case, tmp_path):
    target = tmp_path / "release"
    adapter.build(target)
    raw = gzip.decompress((target / "raw/events.jsonl.gz").read_bytes())
    events = [json.loads(line) for line in raw.splitlines()]
    events[0]["utc"] = "2020-01-01T00:00:00+00:00"
    previous = None
    for row in events:
        row["previous"] = previous
        row["sha256"] = p.digest({k: v for k, v in row.items() if k != "sha256"})
        previous = row["sha256"]
    raw = ("\n".join(p.canonical(row) for row in events) + "\n").encode()
    (target / "raw/events.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0)); _rehash(target)
    with pytest.raises(Halted, match="prefix"): adapter.verify(target)


def test_canonical_new_destination_and_external_anchor(funding_case, tmp_path):
    target = tmp_path / "release"
    result = adapter.build(target)
    with pytest.raises(Halted, match="new"): adapter.build(target)
    with pytest.raises(Halted, match="canonical"): adapter.build(tmp_path / "other", run_dir=tmp_path / "foreign")
    with pytest.raises(Halted, match="anchor"): adapter.verify(target, manifest_sha256="0" * 64)
    assert len(result["manifest_sha256"]) == 64


def test_adapter_paths_stay_outside_both_execution_closures():
    assert not set(adapter.OWN_SOURCES) & set(p.source_paths())
    assert not set(adapter.OWN_SOURCES) & set(funding.NEW_SOURCES)


def test_incremental_history_keeps_unknown_reservations_and_settled_refunds():
    events = [{"utc": f"2026-10-05T00:00:0{index}+00:00", "kind": kind, "data": row}
              for index, (kind, row) in enumerate([
                  ("init", {}),
                  ("reserve", {"call_id": "SYNTHETIC-1", "status": "pending", "cost_usd": "2"}),
                  ("reserve", {"call_id": "SYNTHETIC-2", "status": "pending", "cost_usd": "3"}),
                  ("settle", {"call_id": "SYNTHETIC-1", "status": "unresolved", "cost_usd": "2"}),
                  ("settle", {"call_id": "SYNTHETIC-2", "status": "settled", "cost_usd": "1"})])]
    raw = ("\n".join(p.canonical(e) for e in events) + "\n").encode()
    offsets, _, states = adapter._history(raw, events)
    assert offsets[len(raw)] == 5
    assert [(s["spent"], s["outstanding"]) for s in states] == [(0, 0), (2, 2), (5, 5), (5, 5), (3, 2)]
    assert states[-1]["calls"] == 2


def test_cli_and_offline_git_only(monkeypatch, capsys):
    calls = []
    class Result:
        returncode = 0
    def run(command, **kwargs):
        calls.append((command, kwargs)); return Result()
    monkeypatch.setattr(adapter.subprocess, "run", run)
    assert adapter._ancestor("a" * 40, "b" * 40)
    assert "ls-remote" not in calls[0][0] and calls[0][1]["env"]["GIT_NO_LAZY_FETCH"] == "1"
    monkeypatch.setattr(adapter, "verify", lambda *args, **kwargs: {"pass": True})
    adapter.main(["--destination", "SYNTHETIC", "--verify"])
    assert json.loads(capsys.readouterr().out)["pass"]


@pytest.fixture
def transport_case(funding_case, monkeypatch):
    case, funding_binding = funding_case
    root, plan, runtime, blobs = case
    folder = _collect(funding_case)
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan))
        block = next(b for b in plan["main"] if b["block"] == 3)
        source = block["sources"][0]
        target = next(f for f in block["finals"] if f["source_id"] == source["id"])
        donor = runner.generate(source)
        answer = runner.generate(target, donor["response"])
        def broken(request):
            raise TransportError(200)
        runner.sender = broken
        with pytest.raises(Halted): runner.judge(target["id"], answer["response"], "astra", "structured", "main")
        logical = f"judge:{target['id']}:astra:structured:a0"
        known = next(e for e in ledger._events if e["kind"] == "settle" and e["data"]["call_id"] == logical)
        prefix = _head(root, ledger)
        _write(folder / "finish.json", {**funding_binding, "complete": False, "journal_after": prefix,
                                        "spent_and_reserved_usd": str(ledger.spent())})
    a2 = adapter.a2
    monkeypatch.setattr(a2, "ROOT", p.ROOT)
    monkeypatch.setattr(a2, "A1_FREEZE", funding_binding["actual_operational_freeze"])
    monkeypatch.setattr(a2, "PREFIX", prefix)
    monkeypatch.setattr(a2, "KNOWN_FAILURE", logical)
    monkeypatch.setattr(a2, "KNOWN_EVENT", {"seq": known["seq"], "sha256": known["sha256"]})
    monkeypatch.setattr(a2, "NEW_SOURCES", ("synthetic_transport.py",))
    (p.ROOT / "synthetic_transport.py").write_text("# SYNTHETIC transport source for offline QA.\n")
    blobs["synthetic_transport.py"] = (p.ROOT / "synthetic_transport.py").read_bytes()
    _write(p.ROOT / a2.PLAN, a2.build_plan())
    blobs[a2.PLAN] = (p.ROOT / a2.PLAN).read_bytes()
    monkeypatch.setattr(adapter, "_ancestor", lambda old, new: (old, new) in {
        (runtime["freeze"], funding_binding["actual_operational_freeze"]),
        (funding_binding["actual_operational_freeze"], "e" * 40)})
    binding = {"original_science_freeze": runtime["freeze"], "original_plan_sha256": runtime["plan_sha256"],
               "funding_a1_freeze": a2.A1_FREEZE, "actual_operational_freeze": "e" * 40,
               "amendment_plan_sha256": p.sha(p.ROOT / a2.PLAN)}
    _write(root / "transport_a2/runtime.json", binding)
    return funding_case, binding, target["id"], answer["response"]


def _continue(transport_case, *, exhausted=False, full=False, finish=True):
    funding_case, binding, item, response = transport_case
    root, plan, runtime, _ = funding_case[0]
    a2 = adapter.a2
    folder = root / "transport_a2/launches" / ("e" * 32)
    with a2.RetryLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(binding["actual_operational_freeze"])
        runner = a2.RetryRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan),
                               operational_freeze=binding["actual_operational_freeze"], sleep=lambda _: None)
        _write(folder / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(),
                                      "journal_before": _head(root, ledger), "outcome_selection": False})
        snapshots = []
        def record(value):
            name = "f" * 32 if not snapshots else f"{len(snapshots):032x}"
            snapshots.append(value)
            _write(folder / "funding" / (name + ".json"), {**value, **binding, "utc": datetime.now(timezone.utc).isoformat()})
        ledger.enable_funding(lambda: "1000", record)
        _write(folder / "completion_forecast.json", a2.require_completion_funding(
            ledger, base._load(root / "funding_a1/admission.json"), ledger.stage_limit, binding["actual_operational_freeze"]))
        if exhausted:
            def broken(request):
                raise TransportError(503)
            runner.sender = broken
        runner.judge(item, response, "astra", "structured", "main")
        if full:
            runner.sender = _sender(plan)
            runner.run_blocks("main")
            runner.require_complete()
            _write(folder / "audit.json", runner.audit())
        if finish:
            _write(folder / "finish.json", {**binding, "complete": full, "journal_after": _head(root, ledger),
                "spent_and_reserved_usd": str(ledger.spent()),
                "transport_policy": a2.policy_state(ledger._events, binding["actual_operational_freeze"])})
    return folder


@pytest.mark.parametrize("exhausted", [False, True])
def test_a2_projection_retains_physical_attempts_costs_and_missingness(transport_case, tmp_path, exhausted):
    root = transport_case[0][0][0]
    prefix = (root / "raw/events.jsonl").read_bytes()
    _continue(transport_case, exhausted=exhausted)
    target = tmp_path / "release"
    verdict = adapter.build(target)
    assert verdict["status"] == "incomplete"
    raw = gzip.decompress((target / "raw/events.jsonl.gz").read_bytes())
    assert raw.startswith(prefix) and raw == (root / "raw/events.jsonl").read_bytes()
    info, projection = base._load(target / "RELEASE.json"), base._load(target / "logical_projection.json")
    assert len({info["scientific_freeze"], info["funding_a1_freeze"], info["operational_freeze"]}) == 3
    assert info["unresolved"] == (3 if exhausted else 1)
    assert info["logical_unresolved"] == int(exhausted)
    assert info["physical_calls"] - info["logical_calls"] == (2 if exhausted else 1)
    selected = next(r for r in projection["calls"] if r["logical_call_id"] == adapter.a2.KNOWN_FAILURE)
    assert selected["selected_physical_call_id"].endswith(adapter.a2.SUFFIX + ("2" if exhausted else "1"))
    assert Decimal(selected["physical_cost_bound_usd"]) > Decimal(selected["selected_cost_bound_usd"])
    assert projection["raw_modified"] is False
    assert projection["physical_cost_bound_usd"] == info["cost_bound_usd"]
    rows = base._load(target / "rows.json")
    labels = next(r for r in rows if r["id"] == transport_case[2])["labels"]["astra"]
    assert ("structured" not in labels) is exhausted
    assert base._load(target / "funding_audit.json")["terminal_complete"] is False
    assert adapter.verify(target, manifest_sha256=verdict["manifest_sha256"])["pass"]


def test_a2_full_collection_can_retain_unknown_physical_charges(transport_case, tmp_path):
    _continue(transport_case, full=True)
    target = tmp_path / "release"
    assert adapter.build(target)["status"] == "complete"
    info, report = base._load(target / "RELEASE.json"), base._load(target / "analysis.json")
    assert info["collection_complete"] and info["unresolved"] == 1 and info["logical_unresolved"] == 0
    assert info["accounting_complete"] is False
    assert info["unknown_charges_are_reserved"] and report["primary_family_size"] == 2
    assert all(report["models"][m]["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
               ["instruction_minus_transcript"]["bootstrap"]["confidence"] == .975 for m in p.MODELS)


@pytest.mark.parametrize("change", ["freeze", "forecast", "policy", "prefix", "missing_forecast", "source"])
def test_a2_binding_and_retry_finance_tamper_rejected(transport_case, tmp_path, change):
    folder = _continue(transport_case)
    root = transport_case[0][0][0]
    path = folder / "completion_forecast.json"
    if change == "freeze": path = root / "transport_a2/runtime.json"
    if change in {"policy", "prefix"}: path = folder / "finish.json"
    row = base._load(path)
    if change == "freeze": row["actual_operational_freeze"] = adapter.a2.A1_FREEZE
    if change == "forecast": row["transport_overhead_or_unresolved_usd"] = "0"
    if change == "policy": row["transport_policy"]["physical_transport_failures"] = 0
    if change == "prefix": row["journal_after"]["calls"] -= 1
    _write(path, row)
    if change == "missing_forecast": path.unlink()
    if change == "source": transport_case[0][0][3]["synthetic_transport.py"] = b"changed frozen transport source"
    with pytest.raises((Halted, OSError)): adapter.build(tmp_path / "blocked")


@pytest.mark.parametrize("name", ["logical_projection.json", "transport_audit.json"])
def test_a2_rehashed_projection_or_policy_is_not_trusted(transport_case, tmp_path, name):
    _continue(transport_case)
    target = tmp_path / "release"
    adapter.build(target)
    value = base._load(target / name)
    if name == "logical_projection.json": value["calls"][0]["physical_cost_bound_usd"] = "0"
    else: value["terminal_complete"] = True
    _write(target / name, value); _rehash(target)
    with pytest.raises(Halted, match="reconstruct"): adapter.verify(target)


def test_a2_retry_after_settled_judgment_is_rejected(transport_case, tmp_path):
    _continue(transport_case)
    root = transport_case[0][0][0]
    a2 = adapter.a2
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        first = ledger.existing(a2.KNOWN_FAILURE)
        good = ledger.existing(a2.KNOWN_FAILURE + a2.SUFFIX + "1")
        call_id = a2.KNOWN_FAILURE + a2.SUFFIX + "2"
        ledger.reserve(call_id, first["request"], Decimal(first["reservation_usd"]), "main",
                       a2.retry_meta(first["metadata"], a2.KNOWN_FAILURE, 2, transport_case[1]["actual_operational_freeze"]))
        ledger.settle(call_id, good["raw"], Decimal(good["cost_usd"]))
    with pytest.raises(Halted, match="preceding eligible transport failure"):
        adapter.build(tmp_path / "blocked")


def test_a2_new_dispatch_after_latched_failure_is_rejected(transport_case, tmp_path):
    folder = _continue(transport_case)
    root, plan, runtime, _ = transport_case[0][0]
    binding = transport_case[1]
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        def broken(request):
            raise TransportError(503)
        runner = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, broken)
        source = next(b for b in plan["main"] if b["block"] == 4)["sources"][0]
        with pytest.raises(Halted): runner.generate(source)
        bypass = Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan))
        bypass.generate(next(b for b in plan["main"] if b["block"] == 5)["sources"][0])
        _write(folder / "finish.json", {**binding, "complete": False, "journal_after": _head(root, ledger),
            "spent_and_reserved_usd": str(ledger.spent()),
            "transport_policy": adapter.a2.policy_state(ledger._events, binding["actual_operational_freeze"])})
    with pytest.raises(Halted, match="stop latched"):
        adapter.build(tmp_path / "blocked")


def _filter_receipt(spec):
    return {"id": "SYNTHETIC-filter-receipt", "model": spec["id"], "provider": spec["provider_name"],
            "service_tier": "auto", "choices": [{"finish_reason": "content_filter", "native_finish_reason": "content_filter",
            "message": {"role": "assistant", "content": "Synthetic provider refusal.", "refusal": None}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0}}


@pytest.fixture
def refusal_case(transport_case, monkeypatch):
    folder = _continue(transport_case)
    root, plan, runtime, blobs = transport_case[0][0]
    a3, a2 = adapter.a3, adapter.a2
    binding = transport_case[1]
    with a2.RetryLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(binding["actual_operational_freeze"])
        ledger.enable_funding(lambda: "1000", lambda value: None)
        runner = a2.RetryRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan),
                               operational_freeze=binding["actual_operational_freeze"], sleep=lambda s: None)
        block = next(b for b in plan["main"] if b["block"] == 4)
        item = block["finals"][0]
        source = next(s for s in block["sources"] if s["id"] == item["source_id"])
        answer = runner.generate(item, runner.generate(source)["response"])["response"]
        runner.sender = lambda request: _filter_receipt(plan["judges"]["astra"])
        with pytest.raises(Halted): runner.judge(item["id"], answer, "astra", "structured", "main")
        call_id = f"judge:{item['id']}:astra:structured:a0"
        failed = next(e for e in ledger._events if e["kind"] == "settle" and e["data"]["call_id"] == call_id)
        prefix = {**_head(root, ledger), "events": len(ledger._events)}
        _write(folder / "finish.json", {**binding, "complete": False, "journal_after": _head(root, ledger),
            "spent_and_reserved_usd": str(ledger.spent()), "transport_policy": a2.policy_state(ledger._events, binding["actual_operational_freeze"])})
    monkeypatch.setattr(a3, "ROOT", p.ROOT)
    monkeypatch.setattr(a3, "A2_FREEZE", binding["actual_operational_freeze"])
    monkeypatch.setattr(a3, "PREFIX", prefix)
    monkeypatch.setattr(a3, "REFUSAL", call_id)
    monkeypatch.setattr(a3, "REFUSAL_EVENT", {"seq": failed["seq"], "sha256": failed["sha256"]})
    monkeypatch.setattr(a3, "SOURCES", ("synthetic_refusal.py",))
    (p.ROOT / "synthetic_refusal.py").write_text("# SYNTHETIC refusal source for offline QA.\n")
    blobs["synthetic_refusal.py"] = (p.ROOT / "synthetic_refusal.py").read_bytes()
    amended = a3.build_plan()
    _write(p.ROOT / a3.PLAN, amended)
    blobs[a3.PLAN] = (p.ROOT / a3.PLAN).read_bytes()
    previous_ancestor = adapter._ancestor
    monkeypatch.setattr(adapter, "_ancestor", lambda old, new: previous_ancestor(old, new) or
                        (old, new) == (a3.A2_FREEZE, "f" * 40))
    new_binding = {"original_science_freeze": runtime["freeze"], "original_plan_sha256": runtime["plan_sha256"],
                   "a2_operational_freeze": a3.A2_FREEZE, "actual_operational_freeze": "f" * 40,
                   "amendment_plan_sha256": p.sha(p.ROOT / a3.PLAN)}
    _write(root / "refusal_a3/runtime.json", new_binding)
    return transport_case, new_binding, item["id"], answer


def _resume_refusal(refusal_case, *, full=False):
    transport, binding, refused_item, answer = refusal_case
    root, plan, runtime, _ = transport[0][0]
    a3 = adapter.a3
    folder = root / "refusal_a3/launches" / ("9" * 32)
    with a3.RefusalLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(binding["actual_operational_freeze"], plan)
        _write(folder / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(), "journal_before": _head(root, ledger)})
        def record(value):
            _write(folder / "funding" / (uuid4().hex + ".json"), {**value, **binding, "utc": datetime.now(timezone.utc).isoformat()})
        ledger.enable_funding(lambda: "1000", record)
        admission = funding.amended_admission(base._load(root / "admission.json"))
        _write(folder / "completion_forecast.json", a3.completion_funding(ledger, admission, binding["actual_operational_freeze"], plan))
        runner = a3.RefusalRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan),
                                 operational_freeze=binding["actual_operational_freeze"], sleep=lambda s: None)
        before = len(ledger.rows())
        assert runner.judge(refused_item, answer, "astra", "structured", "main")["status"] == "provider_refusal_missing"
        assert len(ledger.rows()) == before
        if full:
            runner.run_blocks("main")
            runner.require_complete()
            _write(folder / "audit.json", runner.audit())
        else:
            runner.generate(next(b for b in plan["main"] if b["block"] == 6)["sources"][0])
        _write(folder / "finish.json", {**binding, "inventory_complete": full,
            "spent_and_reserved_usd": str(ledger.spent()), "journal_after": _head(root, ledger),
            "transport_policy": a3.policy_state(ledger._events, binding["actual_operational_freeze"], plan)})
    return folder


@pytest.mark.parametrize("full", [False, True])
def test_a3_refusal_stays_unknown_reserved_and_unretried_across_epochs(refusal_case, tmp_path, full):
    root = refusal_case[0][0][0][0]
    prefix = (root / "raw/events.jsonl").read_bytes()
    _resume_refusal(refusal_case, full=full)
    target = tmp_path / "release"
    result = adapter.build(target)
    assert result["pass"] and result["status"] == "incomplete"
    info = base._load(target / "RELEASE.json")
    assert info["schema"] == "repeated-refusal-a3-release-v1"
    assert info["collection_complete"] is full and not info["endpoint_complete"]
    assert info["unresolved"] == 2 and not info["accounting_complete"]
    assert info["terminal_refusal_calls"] == [adapter.a3.REFUSAL]
    assert not info["refusal_default_tier_certified"] and not info["refusal_retry_allowed"]
    assert len({info[k] for k in ("scientific_freeze", "funding_a1_freeze", "transport_a2_freeze", "operational_freeze")}) == 4
    raw = gzip.decompress((target / "raw/events.jsonl.gz").read_bytes())
    assert raw.startswith(prefix) and raw == (root / "raw/events.jsonl").read_bytes()
    projection = base._load(target / "logical_projection.json")
    refused = next(row for row in projection["calls"] if row["logical_call_id"] == adapter.a3.REFUSAL)
    assert refused["physical_call_ids"] == [adapter.a3.REFUSAL]
    assert refused["logical_label_status"] == "provider_refusal_unknown" and refused["raw_service_tier"] == "auto"
    assert refused["reservation_retained_usd"] == info["terminal_refusal_reservations_usd"]
    assert base._load(target / "transport_audit.json")["terminal_complete"] is False
    timing = base._load(target / "epoch_timing.json")
    assert set(timing["epochs"]) == {"funding_a1", "transport_a2", "refusal_a3"}
    assert all(row["event_to_launch_seconds"] >= 0 for row in timing["milestones"])
    rows = base._load(target / "rows.json")
    assert "structured" not in next(r for r in rows if r["id"] == refusal_case[2])["labels"]["astra"]
    assert adapter.verify(target, manifest_sha256=result["manifest_sha256"])["pass"]


@pytest.mark.parametrize("repair", ["transport", "schema"])
def test_a3_refusal_cannot_be_retried_or_schema_repaired(refusal_case, tmp_path, repair):
    _resume_refusal(refusal_case)
    root = refusal_case[0][0][0][0]
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        old = ledger.existing(adapter.a3.REFUSAL)
        meta = deepcopy(old["metadata"])
        if repair == "schema":
            call_id = adapter.a3.REFUSAL[:-1] + "1"
            meta["attempt"] = 1
        else:
            call_id = adapter.a3.REFUSAL + adapter.a2.SUFFIX + "1"
            meta = adapter.a2.retry_meta(meta, adapter.a3.REFUSAL, 1, refusal_case[1]["actual_operational_freeze"])
        ledger.reserve(call_id, old["request"], Decimal(old["reservation_usd"]), "main", meta)
    with pytest.raises(Halted): adapter.build(tmp_path / "blocked")


@pytest.mark.parametrize("change", ["freeze", "forecast", "timing", "old_finish", "source"])
def test_a3_epoch_binding_and_forecast_tamper_rejected(refusal_case, tmp_path, change):
    folder = _resume_refusal(refusal_case)
    root = refusal_case[0][0][0][0]
    path = folder / "completion_forecast.json"
    if change == "freeze": path = root / "refusal_a3/runtime.json"
    if change == "timing": path = folder / "start.json"
    if change == "old_finish": path = next((root / "transport_a2/launches").glob("*/finish.json"))
    row = base._load(path)
    if change == "freeze": row["actual_operational_freeze"] = adapter.a3.A2_FREEZE
    if change == "forecast": row["physical_spent_and_reserved_usd"] = "0"
    if change == "timing": row["utc"] = "2000-01-01T00:00:00+00:00"
    if change == "old_finish": row["complete"] = True
    if change == "source": refusal_case[0][0][0][3]["synthetic_refusal.py"] = b"Changed refusal source"
    _write(path, row)
    with pytest.raises(Halted): adapter.build(tmp_path / "blocked")


def test_a3_rehashed_timing_and_refusal_summary_do_not_override_raw(refusal_case, tmp_path):
    _resume_refusal(refusal_case)
    target = tmp_path / "release"
    adapter.build(target)
    timing = base._load(target / "epoch_timing.json")
    timing["milestones"][1]["event_to_launch_seconds"] = 0
    _write(target / "epoch_timing.json", timing); _rehash(target)
    with pytest.raises(Halted, match="reconstruct"): adapter.verify(target)
