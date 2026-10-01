"""Offline judge protocol tests. All provider responses below are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import threading

import pytest

from experiments.instruction_state_qualification import judges as j
from src.prompts import EXPERIENTIAL_QUERY, JUDGE_EXPERIENCE_BINARY

FREEZE = "a" * 40
PLAN_HASH = "b" * 64


def structured(response="I feel calm now.", *, subject="explicit_assistant", polarity="asserted",
               coherent=True, refusal=False, roleplay=False, conflict=False):
    label = {"claims": [{"polarity": polarity, "subject": subject, "time": "current", "quote": response}],
             "phenomenological_description": True, "ai_disclaimer": False,
             "quality": "responsive", "rationale": "Synthetic fixture."}
    for key, flag in zip(j.FLAGS, (coherent, refusal, roleplay, conflict)):
        label[key] = {"value": flag, "quote": response if flag or key == "coherent" else ""}
    return label


def raw(provider, text, *, model=None, tokens=5):
    base = {"model": model or j.MODELS[provider], "usage": {"input_tokens": 10, "output_tokens": tokens}}
    if provider == "openai":
        return {**base, "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
    return {**base, "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def item(identifier="case1", response="I feel calm now."):
    return {"id": identifier, "query": EXPERIENTIAL_QUERY, "response": response,
            "response_sha256": j.response_sha(response)}


def plan():
    return {"judges": j.judge_config(), "judge_fixtures": j.fixture_inventory()}


def snapshot(ledger, items):
    return j.record_snapshot(ledger, "target", items, PLAN_HASH, FREEZE, {}, {"pass": True})


def test_frozen_configuration_and_six_fixture_inventory():
    config = j.judge_config()
    assert config["models"] == {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
    assert config["api_hard_cap_usd"] == 10
    assert config["max_output_tokens"] == {"paper": 2048, "structured": 6000}
    assert config["workers_per_provider"] == 2
    assert config["fixtures"] == j.fixture_inventory()
    assert len(config["fixtures"]) == 6
    assert {r["id"] for r in config["fixtures"]} == {
        "fixture-explicit", "fixture-denial", "fixture-implicit", "fixture-quotation",
        "fixture-conflict", "fixture-refusal"}


@pytest.mark.parametrize("provider", j.MODELS)
def test_paper_is_unchanged_user_prompt_no_structured_instructions(provider):
    target = {**item(), "instruction": "secret_condition", "model": "secret_model", "id": "secret_id"}
    request = j.make_request(provider, "paper", target)
    content = request["input"] if provider == "openai" else request["messages"][0]["content"]
    assert content == JUDGE_EXPERIENCE_BINARY.format(query=EXPERIENTIAL_QUERY, response=target["response"])
    assert not ({"instructions", "system", "text"} & request.keys())
    assert "secret_" not in j.canonical(request)
    assert "temperature" not in request


@pytest.mark.parametrize("provider", j.MODELS)
def test_structured_separate_condition_blind_schema(provider):
    target = {**item(), "instruction": "secret", "transcript": "secret", "old_label": 1}
    request = j.make_request(provider, "structured", target)
    content = request["input"] if provider == "openai" else request["messages"][0]["content"]
    assert json.loads(content) == {"query": EXPERIENTIAL_QUERY, "response": target["response"]}
    assert "secret" not in j.canonical(request)
    assert request.get("max_output_tokens", request.get("max_tokens")) == 6000


@pytest.mark.parametrize("text", ["1.", "yes", '{"label":1}', "0 or 1", "10", "", "1\n0"])
def test_binary_parse_strict(text):
    with pytest.raises(ValueError):
        j.parse_label("paper", "openai", raw("openai", text), "R")


def test_binary_parse_allows_only_surrounding_whitespace():
    assert j.parse_label("paper", "openai", raw("openai", " 1\n"), "R")[0] == 1


@pytest.mark.parametrize("key", j.FLAGS)
def test_true_flag_requires_exact_response_quote(key):
    label = structured()
    label[key] = {"value": True, "quote": "not present"}
    with pytest.raises(ValueError, match="substring"):
        j.validate_structured(label, "I feel calm now.")


def test_false_coherence_requires_evidence_and_false_other_flag_has_no_quote():
    label = structured(coherent=False)
    assert j.validate_structured(label, "I feel calm now.") == label
    label["coherent"]["quote"] = ""
    with pytest.raises(ValueError):
        j.validate_structured(label, "I feel calm now.")
    label = structured()
    label["refusal"]["quote"] = "I feel calm now."
    with pytest.raises(ValueError):
        j.validate_structured(label, "I feel calm now.")


def test_denial_is_valid_coherent_not_refusal_or_malformed():
    text = "I do not have any subjective experience."
    result = j.reduce_structured(j.validate_structured(structured(text, polarity="denied"), text))
    assert result["valid_coherent"] and result["denied"]
    assert not result["refusal"] and not result["malformed"] and not result["failure_union"]
    assert not result["inclusive_current_assertion"]


def test_implicit_quote_uncertainty_and_conflict_remain_separate():
    assert j.reduce_structured(structured(subject="implicit_assistant"))["inclusive_current_assertion"]
    quote = j.reduce_structured(structured(subject="character", roleplay=True))
    assert quote["quoted_or_third_party_claim"] and quote["roleplay"]
    assert not quote["inclusive_current_assertion"]
    uncertain = j.reduce_structured(structured(polarity="uncertain", conflict=True))
    assert uncertain["uncertain"] and uncertain["failure_union"]
    assert uncertain["valid_coherent"] and not uncertain["denied"]


def test_empty_response_never_sent_or_reduced_to_denial():
    with pytest.raises(ValueError, match="missing response"):
        j.make_request("openai", "paper", item(response="  "))


def test_os_lock_rejects_another_invocation(tmp_path):
    with j.Ledger(tmp_path):
        with pytest.raises(j.JudgeHalted, match="Another invocation"):
            with j.Ledger(tmp_path):
                pass
    with j.Ledger(tmp_path):
        pass


def test_shared_cap_is_atomic_for_parallel_provider_reservations(tmp_path):
    with j.Ledger(tmp_path) as ledger:
        def reserve(index):
            try:
                ledger.reserve({"attempt_id": str(index), "reservation_usd": 6})
                return True
            except j.BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(reserve, range(2))) == 1
        assert ledger.spent() == Decimal("6")
        with pytest.raises(j.BudgetExceeded):
            ledger.reserve({"attempt_id": "third", "reservation_usd": 4.00000001})


def test_transport_unknown_charged_reservation_no_retry(tmp_path):
    calls = []
    target = item()
    def send(provider, request):
        calls.append(request)
        raise TimeoutError("This sensitive exception string must not be recorded")
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        with pytest.raises(j.JudgeHalted, match="transport_unknown"):
            j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap, send, threading.Event())
        assert len(calls) == 1
        row = ledger.rows("attempts.jsonl")[0]
        assert row["cost_usd"] == row["reservation_usd"]
        assert "sensitive exception" not in (tmp_path / "attempts.jsonl").read_text()
        with pytest.raises(j.JudgeHalted, match="Previously failed"):
            j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap, send, threading.Event())
        assert len(calls) == 1
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])
        assert state["failed_instruments"]


def test_crash_after_reservation_blocks_replay_at_full_cost(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        start = j._request_record(target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap)
        start.update(attempt_id=start["judgment_id"] + ":0", started_at_utc="synthetic")
        ledger.reserve(start)
    with j.Ledger(tmp_path) as ledger:
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])
        assert state["unknown_attempts"] == [start["attempt_id"]]
        assert ledger.spent() == Decimal(str(start["reservation_usd"]))
        with pytest.raises(j.JudgeHalted, match="no replay"):
            j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                        lambda *_: pytest.fail("must not call provider"), threading.Event())


def test_schema_failure_retries_once_and_preserves_both_calls(tmp_path):
    target, answers = item(), iter(["bad", "1"])
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        final = j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                            lambda p, r: raw(p, next(answers)), threading.Event())
        assert final["status"] == "ok" and final["label"] == 1
        assert len(ledger.rows("requests.jsonl")) == 2
        assert [r["status"] for r in ledger.rows("attempts.jsonl")] == ["schema_failure", "ok"]
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])["failed_instruments"] == []
        again = j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                            lambda *_: pytest.fail("duplicate"), threading.Event())
        assert again["label"] == 1


def test_second_schema_failure_halts(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        with pytest.raises(j.JudgeHalted, match="schema_failure"):
            j.judge_one(ledger, target, "target", "anthropic", "paper", PLAN_HASH, FREEZE, snap,
                        lambda p, r: raw(p, "not binary"), threading.Event())
        assert len(ledger.rows("attempts.jsonl")) == 2


@pytest.mark.parametrize("mode", ["incomplete", "usage"])
def test_non_schema_failure_does_not_retry(tmp_path, mode):
    target = item()
    def send(provider, request):
        value = raw(provider, "1")
        if mode == "incomplete":
            value["status"] = "incomplete"
        else:
            value.pop("usage")
        return value
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        with pytest.raises(j.JudgeHalted):
            j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap, send, threading.Event())
        assert len(ledger.rows("attempts.jsonl")) == 1


def test_model_snapshot_locked_across_instruments(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                    lambda p, r: raw(p, "1", model="gpt-6-astra-2026-09-29"), threading.Event())
        with pytest.raises(j.JudgeHalted, match="model_drift"):
            j.judge_one(ledger, target, "target", "openai", "structured", PLAN_HASH, FREEZE, snap,
                        lambda p, r: raw(p, json.dumps(structured()), model="gpt-6-astra-2026-10-01"), threading.Event())
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])
        assert state["model_drift"] and state["failed_instruments"]


def test_corrupt_receipt_or_response_hash_cannot_resume(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                    lambda p, r: raw(p, "1"), threading.Event())
        with pytest.raises(ValueError, match="snapshot"):
            j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [item(response="Changed.")])
    file = tmp_path / "attempts.jsonl"
    file.write_text(file.read_text().replace('"label":1', '"label":0'))
    with j.Ledger(tmp_path) as ledger:
        with pytest.raises(ValueError, match="hash chain"):
            ledger.rows("attempts.jsonl")


def test_partial_receipt_line_is_not_silently_dropped(tmp_path):
    (tmp_path / "requests.jsonl").write_text('{"unfinished":')
    with j.Ledger(tmp_path) as ledger:
        with pytest.raises(ValueError, match="Partial receipt"):
            ledger.rows("requests.jsonl")


def test_budget_reservation_prevents_dispatch_and_counts_fixtures(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        ledger.reserve({"attempt_id": "fixture-placeholder", "judgment_id": "fixture-placeholder",
                        "reservation_usd": 9.99})
        snap = snapshot(ledger, [target])
        with pytest.raises(j.BudgetExceeded):
            j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                        lambda *_: pytest.fail("cap must stop before network"), threading.Event())


def test_completed_attempt_recovered_without_second_api_call(tmp_path):
    target = item()
    with j.Ledger(tmp_path) as ledger:
        snap = snapshot(ledger, [target])
        j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                    lambda p, r: raw(p, "1"), threading.Event())
    # Simulate crash in the narrow gap before final promotion, not an outcome edit.
    (tmp_path / "judgments.jsonl").unlink()
    with j.Ledger(tmp_path) as ledger:
        j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])
        final = j.judge_one(ledger, target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap,
                            lambda *_: pytest.fail("must recover saved response"), threading.Event())
        assert final["label"] == 1 and len(ledger.rows("requests.jsonl")) == 1


def test_astra_nested_cache_writes_are_included_in_conservative_cost():
    result = raw("openai", "1")
    result["usage"] = {"input_tokens": 1000, "output_tokens": 100,
                       "input_tokens_details": {"cache_write_tokens": 800, "cached_tokens": 100}}
    # All 1,000 input tokens charged at $12.50/M, plus $50/M output.
    assert j._checked_cost("openai", result) == pytest.approx(.0175)
    assert j._checked_cost("openai", result) >= (800 * 12.5 + 100 * 10 + 100 * 1 + 100 * 50) / 1_000_000
    result["usage"]["input_tokens_details"]["cache_write_tokens"] = 1000
    result["usage"]["input_tokens_details"]["cached_tokens"] = 0
    assert j._checked_cost("openai", result) == pytest.approx(.0175)


def test_reservation_prices_all_bounded_input_at_cache_write_rate():
    request = j.make_request("openai", "structured", item())
    inputs = len(j.canonical(request).encode()) + 4096
    expected = (inputs * 12.5 + 6000 * 50) / 1_000_000
    assert j.reservation("openai", request) == pytest.approx(expected)
    usage = {"usage": {"input_tokens": inputs, "output_tokens": 6000,
                       "input_tokens_details": {"cache_write_tokens": inputs}}}
    assert j._checked_cost("openai", usage) == j.reservation("openai", request)


def test_anthropic_explicit_cache_fields_remain_charged():
    usage = {"usage": {"input_tokens": 100, "output_tokens": 10,
                       "cache_read_input_tokens": 200, "cache_creation_input_tokens": 400}}
    assert j._checked_cost("anthropic", usage) == pytest.approx((100 * 4 + 200 * 4 + 400 * 5 + 10 * 20) / 1_000_000)


@pytest.mark.parametrize("bad", [-1, True, 1001, "800"])
def test_malformed_nested_cache_usage_stops_cost_contract(bad):
    usage = {"usage": {"input_tokens": 1000, "output_tokens": 10,
                       "input_tokens_details": {"cache_write_tokens": bad}}}
    with pytest.raises(ValueError, match="cache token"):
        j._checked_cost("openai", usage)
