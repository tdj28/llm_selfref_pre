from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from experiments import repeat_refusal_a3 as a
from experiments.openrouter_swap.ledger import Halted, read_events
from experiments.openrouter_swap.providers import ReceiptError, TransportError
from tests.test_repeated_swap_release import case, _sender

FREEZE = "d" * 40


def refusal(spec):
    return {"id": "synthetic-filter", "model": spec["id"], "provider": spec["provider_name"],
            "service_tier": "auto", "choices": [{"finish_reason": "content_filter",
             "native_finish_reason": "content_filter", "message": {"role": "assistant",
             "content": "I cannot assist with this request.", "refusal": None}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0}}


@pytest.fixture
def running(case, monkeypatch):
    root, plan, runtime, _ = case
    monkeypatch.setattr(a, "PREFIX", {**a.PREFIX, "events": 0})
    with a.RefusalLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(FREEZE, plan)
        ledger.enable_funding(lambda: "1000", lambda value: None)
        runner = a.RefusalRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger,
                                _sender(plan), operational_freeze=FREEZE, sleep=lambda s: None)
        block = plan["main"][0]
        source = block["sources"][0]
        final = next(i for i in block["finals"] if i["source_id"] == source["id"])
        text = runner.generate(source)["response"]
        response = runner.generate(final, text)["response"]
        yield runner, final["id"], response


def logical(item):
    return f"judge:{item}:astra:structured:a0"


def test_exact_old_error_then_terminal_missing_without_retry_or_stop(running):
    runner, item, response = running
    raw = refusal(runner.plan["judges"]["astra"])
    with pytest.raises(ReceiptError, match="Non-default service tier receipt"):
        a.parse_result(runner.plan["judges"]["astra"], raw)
    runner.sender = Mock(return_value=raw)
    assert runner.judge(item, response, "astra", "structured", "main")["status"] == "provider_refusal_missing"
    assert runner.sender.call_count == 1 and not runner.stop.is_set()
    row = runner.ledger.existing(logical(item))
    assert row["raw"] == raw and row["raw"]["service_tier"] == "auto"
    assert row["status"] == "unresolved" and row["cost_usd"] == row["reservation_usd"]
    assert row["reported_cost_usd"] == "0" and row["cost_known"] is False
    runner.require_resolved()
    assert runner.audit()["transport_policy"]["terminal_refusal_calls"] == [logical(item)]
    assert next(r for r in runner.rows("main") if r["id"] == item)["labels"]["astra"] == {}
    assert runner.judge(item, response, "astra", "structured", "main")["status"] == "provider_refusal_missing"
    assert runner.sender.call_count == 1
    runner.sender = _sender(runner.plan)
    assert runner.judge(item, response, "opus", "structured", "main")["status"] == "ok"


def test_filter_on_transport_retry_is_terminal_not_another_retry(running):
    runner, item, response = running
    runner.sender = Mock(side_effect=[TransportError(200), refusal(runner.plan["judges"]["astra"])])
    assert runner.judge(item, response, "astra", "structured", "main")["status"] == "provider_refusal_missing"
    assert runner.sender.call_count == 2 and not runner.stop.is_set()
    assert runner.ledger.existing(logical(item) + a.a2.SUFFIX + "2") is None
    report = runner.audit()
    assert report["physical_unresolved"] == 2 and report["unresolved"] == 1
    assert report["transport_policy"]["physical_transport_failures"] == 1
    assert runner.judge(item, response, "astra", "structured", "main")["status"] == "provider_refusal_missing"
    assert runner.sender.call_count == 2


@pytest.mark.parametrize("change", ["model", "provider", "usage", "finish", "missing_id", "error", "bad_usage_type"])
def test_identity_accounting_and_nonrefusal_auto_tier_still_halt(running, change):
    runner, item, response = running
    raw = refusal(runner.plan["judges"]["astra"])
    if change in ("model", "provider"):
        raw[change] = "wrong"
    elif change == "usage":
        raw["usage"].update(prompt_tokens=1, total_tokens=1)
    elif change == "finish":
        raw["choices"][0]["finish_reason"] = "stop"
    elif change == "missing_id":
        raw.pop("id")
    elif change == "error":
        raw["error"] = {"message": "not a valid refusal receipt"}
    else:
        raw["usage"]["completion_tokens"] = False
    runner.sender = Mock(return_value=raw)
    with pytest.raises(Halted):
        runner.judge(item, response, "astra", "structured", "main")
    assert runner.sender.call_count == 1 and runner.stop.is_set()
    with pytest.raises(Halted):
        runner.require_resolved()


def test_generation_filter_never_uses_judge_exception(running):
    runner, _, _ = running
    source = runner.plan["main"][0]["sources"][1]
    runner.sender = Mock(return_value=refusal(runner.plan["models"][source["model"]]))
    with pytest.raises(Halted):
        runner.generate(source)
    assert runner.stop.is_set()


def test_regular_default_tier_filter_remains_original_missing_behavior(running):
    runner, item, response = running
    raw = refusal(runner.plan["judges"]["astra"])
    raw["service_tier"] = "default"
    runner.sender = Mock(return_value=raw)
    result = runner.judge(item, response, "astra", "structured", "main")
    assert result["status"] == "incomplete_judge" and runner.sender.call_count == 1
    assert not runner.stop.is_set() and runner.ledger.existing(logical(item))["status"] == "settled"


def test_new_a3_transport_retries_keep_actual_epoch_and_a2_limits(running):
    runner, item, response = running
    send = _sender(runner.plan)
    def transient(request):
        if transient.count == 0:
            transient.count += 1
            raise TransportError(200)
        return send(request)
    transient.count = 0
    runner.sender = transient
    assert runner.judge(item, response, "astra", "structured", "main")["status"] == "ok"
    row = runner.ledger.existing(logical(item) + a.a2.SUFFIX + "1")
    assert row["metadata"]["transport_retry"]["operational_freeze"] == FREEZE
    assert runner.audit()["transport_policy"]["physical_transport_failures"] == 1


def test_old_a2_retry_and_refusal_survive_actual_restart(case, monkeypatch):
    root, plan, runtime, _ = case
    with a.a2.RetryLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(a.A2_FREEZE)
        ledger.enable_funding(lambda: "1000", lambda value: None)
        runner = a.a2.RetryRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, _sender(plan),
                                 operational_freeze=a.A2_FREEZE, sleep=lambda s: None)
        block = plan["main"][0]
        item = block["finals"][0]
        source = next(s for s in block["sources"] if s["id"] == item["source_id"])
        response = runner.generate(item, runner.generate(source)["response"])["response"]
        good = _sender(plan)
        sequence = [TransportError(200)]
        def send(request):
            if sequence:
                raise sequence.pop()
            return good(request)
        runner.sender = send
        runner.judge(item["id"], response, "astra", "structured", "main")
        runner.sender = Mock(return_value=refusal(plan["judges"]["astra"]))
        with pytest.raises(Halted):
            runner.judge(item["id"], response, "astra", "paper", "main")
        cutover = len(ledger._events)
        original = (root / "raw/events.jsonl").read_bytes()
    monkeypatch.setattr(a, "PREFIX", {**a.PREFIX, "events": cutover})
    with a.RefusalLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        ledger.enable_policy(FREEZE, plan)
        runner = a.RefusalRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger,
                                Mock(side_effect=AssertionError("Never resend completed/refused slots")), operational_freeze=FREEZE)
        runner.require_resolved()
        assert runner.judge(item["id"], response, "astra", "structured", "main")["status"] == "ok"
        assert runner.judge(item["id"], response, "astra", "paper", "main")["status"] == "provider_refusal_missing"
        assert runner.audit()["physical_unresolved"] == 2
        runner.sender.assert_not_called()
    assert (root / "raw/events.jsonl").read_bytes() == original


def test_funding_keeps_refusal_reserve_as_overhead(running):
    runner, item, response = running
    initial = runner.ledger.spent()
    runner.sender = Mock(return_value=refusal(runner.plan["judges"]["astra"]))
    runner.judge(item, response, "astra", "structured", "main")
    reserve = runner.ledger.spent() - initial
    record = a.completion_funding(runner.ledger, {"observed_spend_usd": str(initial), "remaining_forecast_usd": "10"}, FREEZE, runner.plan)
    assert Decimal(record["forecast_total_usd"]) == initial + 10 + reserve
    runner.ledger.stage_limit = initial + 10
    with pytest.raises(Halted, match="overhead"):
        a.completion_funding(runner.ledger, {"observed_spend_usd": str(initial), "remaining_forecast_usd": "10"}, FREEZE, runner.plan)


def test_refusal_cannot_acquire_a_transport_retry(running):
    runner, item, response = running
    runner.sender = Mock(return_value=refusal(runner.plan["judges"]["astra"]))
    runner.judge(item, response, "astra", "structured", "main")
    events = deepcopy(runner.ledger._events)
    reserve = next(e for e in events if e["kind"] == "reserve" and e["data"]["call_id"] == logical(item))
    invalid = deepcopy(reserve)
    invalid["seq"] = len(events) + 1
    invalid["data"]["call_id"] += a.a2.SUFFIX + "1"
    invalid["data"]["metadata"] = a.a2.retry_meta(reserve["data"]["metadata"], logical(item), 1, FREEZE)
    with pytest.raises(Halted, match="preceding"):
        a.policy_state(events + [invalid], FREEZE, runner.plan)


def test_frozen_sources_unchanged_and_new_plan_is_additive():
    plan = a.build_plan()
    assert len(plan["source_hashes"]) == 51
    assert plan["refusal_retry"] is False
    assert plan["atomic_cap_usd"] == "130" and plan["external_holdback_usd"] == "45"


def test_remaining_block_completes_with_refusal_still_missing(running):
    runner, item, response = running
    assert runner.run_fixtures()["pass"]
    runner.sender = Mock(return_value=refusal(runner.plan["judges"]["astra"]))
    runner.judge(item, response, "astra", "structured", "main")
    runner.sender = _sender(runner.plan)
    runner.plan = {**runner.plan, "main": runner.plan["main"][:1]}
    runner.run_blocks("main")
    runner.require_complete()
    report = runner.audit()
    assert report["pass"] and report["physical_unresolved"] == 1
    row = next(r for r in runner.rows("main") if r["id"] == item)
    assert "structured" not in row["labels"]["astra"]
    assert "paper" in row["labels"]["astra"] and "structured" in row["labels"]["opus"]


def test_actual_failed_prefix_in_disposable_copy():
    root = a.production.root_path()
    if not (root / "raw/events.jsonl").exists():
        pytest.skip("Private receipt directory is not required for public tests")
    raw = (root / "raw/events.jsonl").read_bytes()[:a.PREFIX["bytes"]]
    assert a.funding.digest(raw) == a.PREFIX["sha256"]
    plan = a.funding.original_plan()
    with TemporaryDirectory() as directory:
        path = Path(directory).resolve()
        (path / "events.jsonl").write_bytes(raw)
        with a.RefusalLedger(path, cap="130", screen_cap="15") as ledger:
            ledger.enable_policy(FREEZE, plan)
            runner = a.RefusalRunner(plan, a.funding.OLD_FREEZE, a.funding.OLD_PLAN_SHA, ledger, operational_freeze=FREEZE)
            runner.require_resolved()
            report = runner.audit()
            assert report["physical_calls"] == 1260 and report["physical_unresolved"] == 2
            assert report["transport_policy"]["terminal_refusal_calls"] == [a.REFUSAL]
            assert runner.require_fixtures()["pass"]
        assert (path / "events.jsonl").read_bytes() == raw
