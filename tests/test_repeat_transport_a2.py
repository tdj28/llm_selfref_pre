from copy import deepcopy
from decimal import Decimal
import json
from unittest.mock import Mock

import pytest

from experiments import repeat_transport_a2 as a
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import BudgetExceeded, Halted
from experiments.openrouter_swap.providers import TransportError, reservation
from experiments.repeated_swap.runner import Runner, privacy
from tests.test_repeated_swap_release import case, _sender

FREEZE = "b" * 40


@pytest.fixture
def running(case):
    root, plan, runtime, _ = case
    with a.RetryLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(FREEZE)
        ledger.enable_funding(lambda: "1000", lambda value: None)
        runner = a.RetryRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger,
                              _sender(plan), operational_freeze=FREEZE, sleep=Mock())
        block = plan["main"][0]
        source = block["sources"][0]
        final = next(f for f in block["finals"] if f["source_id"] == source["id"])
        transcript = runner.generate(source)
        answer = runner.generate(final, transcript["response"])
        yield runner, final["id"], answer["response"]


def logical(item, judge="astra", instrument="paper"):
    return f"judge:{item}:{judge}:{instrument}:a0"


def test_existing_failed_call_retried_identically_and_original_preserved(running):
    runner, item, response = running
    old = Runner(runner.plan, runner.freeze, runner.plan_hash, runner.ledger,
                 Mock(side_effect=TransportError(200)))
    with pytest.raises(Halted):
        old.judge(item, response, "astra", "paper", "main")
    original = runner.ledger.existing(logical(item))
    assert original["raw"] == {"transport_status_code": 200}
    result = runner.judge(item, response, "astra", "paper", "main")
    assert result["status"] == "ok"
    assert runner.ledger.existing(logical(item)) == original
    retry = runner.ledger.existing(logical(item) + a.SUFFIX + "1")
    assert retry["request"] == original["request"]
    assert retry["metadata"]["freeze"] == runner.freeze
    assert retry["metadata"]["transport_retry"]["operational_freeze"] == FREEZE
    assert runner.ledger.spent() >= Decimal(original["reservation_usd"]) + Decimal(retry["cost_usd"])
    report = runner.audit()
    assert report["physical_unresolved"] == 1 and report["unresolved"] == 0
    assert report["physical_calls"] == report["logical_calls"] + 1
    assert report["logical_to_physical"][logical(item)] == [logical(item), logical(item) + a.SUFFIX + "1"]
    row = next(r for r in runner.rows("main") if r["id"] == item)
    assert row["labels"]["astra"]["paper"] == 1
    runner.sender = Mock(side_effect=AssertionError("cached success must not dispatch"))
    assert runner.judge(item, response, "astra", "paper", "main")["status"] == "ok"


def test_three_attempts_then_missing_and_no_fourth_on_resume(running):
    runner, item, response = running
    runner.sender = Mock(side_effect=TransportError(503))
    assert runner.judge(item, response, "astra", "paper", "main")["status"] == "transport_failed_missing"
    assert runner.sender.call_count == 3
    assert [c.args[0] for c in runner.sleep.call_args_list] == [2, 5]
    runner.require_resolved()
    before = runner.ledger.spent()
    assert runner.judge(item, response, "astra", "paper", "main")["status"] == "transport_failed_missing"
    assert runner.sender.call_count == 3 and runner.ledger.spent() == before
    assert runner.audit()["transport_policy"]["exhausted_logical_calls"] == [logical(item)]
    assert next(r for r in runner.rows("main") if r["id"] == item)["labels"]["astra"] == {}


@pytest.mark.parametrize("content,finish", [("0", "stop"), ("1", "stop"), ("", "length"), (None, "content_filter")])
def test_completed_label_or_cap_or_refusal_never_transport_retried(running, content, finish):
    runner, item, response = running
    send = _sender(runner.plan)
    def answer(request):
        raw = send(request)
        raw["choices"][0]["message"]["content"] = content
        raw["choices"][0]["finish_reason"] = finish
        return raw
    runner.sender = Mock(side_effect=answer)
    runner.judge(item, response, "astra", "paper", "main")
    assert runner.sender.call_count == 1
    assert not any(a.SUFFIX in r["call_id"] for r in runner.ledger.rows())


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_nontransient_status_halts_without_retry(running, status):
    runner, item, response = running
    runner.sender = Mock(side_effect=TransportError(status))
    with pytest.raises(Halted):
        runner.judge(item, response, "astra", "paper", "main")
    assert runner.sender.call_count == 1
    with pytest.raises(Halted):
        runner.require_resolved()


@pytest.mark.parametrize("change", ["model", "provider", "usage"])
def test_identity_and_accounting_errors_never_retried(running, change):
    runner, item, response = running
    send = _sender(runner.plan)
    def broken(request):
        raw = send(request)
        if change == "usage":
            raw.pop("usage")
        else:
            raw[change] = "wrong"
        return raw
    runner.sender = Mock(side_effect=broken)
    with pytest.raises(Halted):
        runner.judge(item, response, "astra", "paper", "main")
    assert runner.sender.call_count == 1 and runner.stop.is_set()


def test_generation_transport_never_retried(running):
    runner, _, _ = running
    runner.sender = Mock(side_effect=TransportError(503))
    with pytest.raises(Halted):
        runner.generate(runner.plan["main"][0]["sources"][1])
    assert runner.sender.call_count == 1
    with pytest.raises(Halted):
        runner.ledger.check_policy()


def test_budget_keeps_failed_reservation_and_stops_retry(running):
    runner, item, response = running
    spec = runner.plan["judges"]["astra"]
    request = judges.judge_request(spec, "paper", response)
    request["provider"].update(privacy("judge"))
    runner.ledger.stage_limit = runner.ledger.spent() + reservation(spec, request)
    runner.sender = Mock(side_effect=TransportError(200))
    with pytest.raises(BudgetExceeded):
        runner.judge(item, response, "astra", "paper", "main")
    assert runner.sender.call_count == 1
    assert runner.ledger.existing(logical(item))["status"] == "unresolved"
    assert runner.ledger.spent() == runner.ledger.stage_limit


@pytest.mark.parametrize("mutation", ["request", "metadata", "predecessor", "ordinal"])
def test_physical_retry_tampering_rejected(running, mutation):
    runner, item, response = running
    send = _sender(runner.plan)
    runner.sender = Mock(side_effect=[TransportError(200), send(judges.judge_request(runner.plan["judges"]["astra"], "paper", response))])
    runner.judge(item, response, "astra", "paper", "main")
    events = deepcopy(runner.ledger._events)
    retry = next(e for e in events if e["kind"] == "reserve" and a.SUFFIX in e["data"]["call_id"])
    if mutation == "request":
        retry["data"]["request"]["model"] = "different"
    elif mutation == "metadata":
        retry["data"]["metadata"]["transport_retry"]["operational_freeze"] = "c" * 40
    elif mutation == "predecessor":
        events = [e for e in events if not (e["kind"] == "settle" and e["data"]["call_id"] == logical(item))]
    else:
        retry["data"]["call_id"] = logical(item) + a.SUFFIX + "3"
    with pytest.raises(Halted):
        a.policy_state(events, FREEZE)


def synthetic_events(outcomes):
    events = []
    for item, ordinal, success, endpoint in outcomes:
        logical_id = f"judge:{item}:astra:paper:a0"
        call_id = logical_id + (a.SUFFIX + str(ordinal) if ordinal else "")
        meta = a.retry_meta({"kind": "judge"}, logical_id, ordinal, FREEZE)
        request = {"model": endpoint, "provider": {"only": [endpoint]}}
        row = {"call_id": call_id, "metadata": meta, "request": request, "request_sha256": "x",
               "phase": "main", "reservation_usd": "1", "status": "pending", "cost_usd": "1"}
        events.append({"kind": "reserve", "data": row})
        events.append({"kind": "settle", "data": {"call_id": call_id, "status": "settled" if success else "unresolved",
                      "error_type": None if success else "TransportError", "raw": {} if success else {"transport_status_code": 200},
                      "cost_known": success, "reported_cost_usd": "1" if success else None,
                      "over_reservation": False, "cost_usd": "1"}})
    return events


def test_systematic_stops_count_exhausted_logical_requests_not_attempts_and_latch():
    failures = [(i, r, False, "astra") for i in range(3) for r in range(3)]
    assert a.policy_state(synthetic_events(failures[:3]), FREEZE)["stop_reason"] is None
    state = a.policy_state(synthetic_events(failures + [(4, 0, True, "astra")]), FREEZE)
    assert state["physical_transport_failures"] == 9
    assert state["stop_reason"] == "three_consecutive_exhausted_judge_requests"
    assert list(state["endpoint_exhaustion_streaks"].values()) == [0]


def test_seventeenth_physical_failure_latches_and_endpoint_success_resets_streak():
    failures = [(i, 0, False, "astra") for i in range(17)]
    assert a.policy_state(synthetic_events(failures[:16]), FREEZE)["stop_reason"] is None
    assert a.policy_state(synthetic_events(failures), FREEZE)["stop_reason"] == "seventeenth_physical_transport_failure"
    outcomes = [(0, r, False, "astra") for r in range(3)] + [(1, 0, True, "astra")]
    outcomes += [(2, r, False, "astra") for r in range(3)]
    assert list(a.policy_state(synthetic_events(outcomes), FREEZE)["endpoint_exhaustion_streaks"].values()) == [1]


def test_pending_attempt_not_eligible_for_automatic_resend(running):
    runner, item, response = running
    spec = runner.plan["judges"]["astra"]
    request = judges.judge_request(spec, "paper", response)
    request["provider"].update(privacy("judge"))
    meta = {"kind": "judge", "item_id": item, "judge": "astra", "instrument": "paper", "attempt": 0,
            "response_sha256": a.science.digest(response), "freeze": runner.freeze, "plan_sha256": runner.plan_hash}
    runner.ledger.reserve(logical(item), request, reservation(spec, request), "main", meta)
    with pytest.raises(Halted):
        runner.require_resolved()
    runner.sender = Mock()
    with pytest.raises(Halted):
        runner.judge(item, response, "astra", "paper", "main")
    runner.sender.assert_not_called()


def test_old_frozen_source_closures_unchanged():
    prior = a.prior_plan()
    assert len(prior["source_hashes"]) == 45
    assert not set(a.NEW_SOURCES) & set(prior["source_hashes"])
    assert "tests/test_repeat_transport_a2.py" not in a.science.source_paths()
    plan = a.build_plan()
    assert len(plan["source_hashes"]) == 48
    assert plan["atomic_cap_usd"] == "130" and plan["external_holdback_usd"] == "45"


def test_actual_failed_prefix_offline_readonly():
    root = a.production.root_path()
    if not (root / "raw/events.jsonl").exists():
        pytest.skip("Private live receipt directory is not required for public tests")
    names = ("runtime.json", "admission.json", "raw/events.jsonl")
    before = {n: (root / n).read_bytes() for n in names}
    assert a.verify_prefix(root)["pass"]
    assert before == {n: (root / n).read_bytes() for n in names}


def test_run_blocks_continues_after_exhausted_judge_and_keeps_other_judges(running):
    runner, item, response = running
    assert runner.run_fixtures()["pass"]
    runner.sender = Mock(side_effect=TransportError(200))
    assert runner.judge(item, response, "astra", "paper", "main")["status"] == "transport_failed_missing"
    assert runner.sender.call_count == 3
    runner.sender = _sender(runner.plan)
    # A bounded synthetic inventory exercises the production thread-pool path.
    runner.plan = {**runner.plan, "main": runner.plan["main"][:1]}
    runner.run_blocks("main")
    runner.require_complete()
    report = runner.audit()
    assert report["pass"] and report["physical_unresolved"] == 3
    assert len(runner.rows("main")) == 12
    assert all(row["labels"]["opus"] for row in runner.rows("main"))


def test_stop_latch_reconstructs_after_restart(tmp_path):
    path = tmp_path / "ledger"
    with a.RetryLedger(path, cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(FREEZE)
        ledger.enable_funding(lambda: "1000", lambda v: None)
        for i in range(17):
            request = {"model": "astra", "provider": {"only": ["azure"]}}
            ledger.reserve(f"judge:{i}:astra:paper:a0", request, "1", "main", {"kind": "judge"})
            ledger.settle(f"judge:{i}:astra:paper:a0", {"transport_status_code": 200}, None, error=TransportError(200))
        with pytest.raises(Halted, match="seventeenth"):
            ledger.reserve("gen:next", {}, "1", "main", {})
        assert ledger.spent() == Decimal("17")
    with a.RetryLedger(path, cap="130", screen_cap="15") as ledger:
        with pytest.raises(Halted, match="seventeenth"):
            ledger.enable_policy(FREEZE)
        assert ledger.spent() == Decimal("17")


def test_source_plan_tamper_and_pushed_freeze_binding(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(a, "ROOT", root)
    prior = {"source_hashes": {}, "input_hashes": {}}
    monkeypatch.setattr(a, "prior_plan", lambda: prior)
    for name in (*a.NEW_SOURCES, a.funding.PLAN):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic bound source\n")
    a.write_once(root / a.PLAN, a.build_plan())
    assert a.verify(root / a.PLAN)["additional_attempts"] == 2
    monkeypatch.setattr(a.funding, "git_blob", lambda freeze, name: (root / name).read_bytes())
    def command(args, **kwargs):
        if args[1] == "rev-parse":
            return FREEZE + "\n"
        if args[1] == "ls-remote":
            return FREEZE + "\trefs/heads/" + a.science.BRANCH + "\n"
        raise AssertionError(args)
    monkeypatch.setattr(a.subprocess, "check_output", command)
    from types import SimpleNamespace
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kw: SimpleNamespace(returncode=0))
    assert a.verify(root / a.PLAN, FREEZE, require_pushed=True)
    with pytest.raises(Halted, match="Fresh"):
        a.verify(root / a.PLAN, a.A1_FREEZE)
    monkeypatch.setattr(a.subprocess, "check_output", lambda args, **kw: FREEZE + "\n" if args[1] == "rev-parse" else "")
    with pytest.raises(Halted, match="pushed"):
        a.verify(root / a.PLAN, FREEZE, require_pushed=True)
    (root / a.NEW_SOURCES[0]).write_text("changed\n")
    with pytest.raises(Halted, match="closure"):
        a.verify(root / a.PLAN)


def test_paid_execute_requires_fresh_freeze_without_dispatch():
    with pytest.raises(SystemExit):
        a.main(["--execute"])


def test_completion_forecast_does_not_treat_failed_attempt_as_completed_work(running):
    runner, item, response = running
    initial = runner.ledger.spent()
    admission = {"observed_spend_usd": str(initial), "remaining_forecast_usd": "10"}
    old = Runner(runner.plan, runner.freeze, runner.plan_hash, runner.ledger,
                 Mock(side_effect=TransportError(200)))
    with pytest.raises(Halted):
        old.judge(item, response, "astra", "paper", "main")
    overhead = runner.ledger.spent() - initial
    limit = initial + Decimal("10") + overhead / 2
    # A1's old arithmetic admits this by subtracting the failed cost as work.
    a.funding.require_completion_funding(runner.ledger, admission, limit)
    with pytest.raises(Halted, match="transport overhead"):
        a.require_completion_funding(runner.ledger, admission, limit, FREEZE)
    runner.judge(item, response, "astra", "paper", "main")
    result = a.require_completion_funding(runner.ledger, admission, Decimal("130"), FREEZE)
    assert Decimal(result["transport_overhead_or_unresolved_usd"]) == overhead
    assert Decimal(result["forecast_total_usd"]) == initial + Decimal("10") + overhead
