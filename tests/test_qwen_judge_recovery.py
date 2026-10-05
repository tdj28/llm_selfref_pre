from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from unittest.mock import Mock

import pytest

from experiments import qwen_judge_recovery as q
from experiments.openrouter_swap.ledger import BudgetExceeded, Halted, Ledger
from experiments.openrouter_swap.providers import TransportError

FREEZE, PLAN_HASH = "a" * 40, "b" * 64


@pytest.fixture(scope="module")
def data():
    return q.source()


@pytest.fixture
def funded():
    return {"confirmed": True, "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "account_balance_usd": "200", "scope_prior_bound_usd": str(q.PRIOR),
            "scope_other_commitments_usd": "45", "kolibri_holdback_usd": "45",
            "repeated_remaining_holdback_usd": "100", "other_account_holdback_usd": "0",
            "evidence_sha256": "c" * 64}


def sender(data, *, finish="stop", content=None):
    def send(request):
        response = next(t["response"] for t in data["targets"].values() if t["original"]["request"] == request)
        structured = {"claims": [], "phenomenological_description": False, "ai_disclaimer": False,
                      "quality": "responsive", "rationale": "Synthetic test only.",
                      "coherent": {"value": True, "quote": response[:100]},
                      "refusal": {"value": False, "quote": ""},
                      "roleplay": {"value": False, "quote": ""},
                      "reported_context_conflict": {"value": False, "quote": ""}}
        return {"id": "synthetic-recovery", "model": data["spec"]["id"], "provider": data["spec"]["provider_name"],
                "choices": [{"finish_reason": finish, "message": {"role": "assistant",
                             "content": json.dumps(structured) if content is None else content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
    return send


def test_exact_three_technical_slots_and_bound_source_closure(data):
    assert tuple(data["targets"]) == q.TARGETS
    assert [t["status"] for t in data["targets"].values()] == ["transport_failure", "transport_failure", "incomplete_error"]
    plan = q.build_plan(data)
    assert plan["cap_usd"] == "2" and plan["new_generations"] == 0
    assert plan["authorization"]["posthoc_scoring_calls"]
    assert set(plan["source_hashes"]) == set(data["plan"]["source_hashes"]) | set(q.SOURCES)
    assert not set(q.SOURCES) & set(data["plan"]["source_hashes"])


def test_recovery_only_fills_three_slots_and_preserves_original_requests(tmp_path, data, funded):
    original = deepcopy(data)
    send = Mock(side_effect=sender(data))
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        report = q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert len(report["recovered"]) == 3 and not report["remaining_missing"]
        assert send.call_count == 3
        for row, target in zip(ledger.rows(), data["targets"].values()):
            assert row["request"] == target["original"]["request"]
        rows = q.project(data, report)
        changed = [r["id"] for r, old in zip(rows, data["rows"]) if r != old]
        assert set(changed) == {cid.split(":")[1] for cid in q.TARGETS}
        assert report["original_release_status"] == "incomplete"
        assert report["original_unknown_charges_retained_usd"] == "0.96522800"
    assert data == original


def test_restart_never_redoes_completed_labels(tmp_path, data, funded):
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        first = q.recover(ledger, data, FREEZE, PLAN_HASH, sender(data), funded, sleep=lambda s: None)
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        send = Mock(side_effect=AssertionError("No cached label can be dispatched"))
        assert q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None) == first
        send.assert_not_called()


@pytest.mark.parametrize("failure", ["transport", "error_finish"])
def test_one_eligible_failure_gets_identical_second_attempt(tmp_path, data, funded, failure):
    normal = sender(data)
    calls = []
    def send(request):
        calls.append(deepcopy(request))
        if len(calls) == 1:
            if failure == "transport":
                raise TransportError(200)
            return sender(data, finish="error")(request)
        return normal(request)
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        report = q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert len(calls) == 4 and calls[0] == calls[1]
        assert len(report["recovered"]) == 3
        assert ledger.rows()[0]["status"] == ("unresolved" if failure == "transport" else "settled")


def test_two_failed_attempts_remain_missing_and_resume_does_not_add_third(tmp_path, data, funded):
    calls = []
    def send(request):
        calls.append(request)
        if len(calls) <= 2:
            raise TransportError(503)
        return sender(data)(request)
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        report = q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert report["remaining_missing"] == [q.TARGETS[0]] and len(calls) == 4
        cost = ledger.spent()
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        send = Mock(side_effect=AssertionError("No third attempt"))
        assert q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None) == report
        assert ledger.spent() == cost
        send.assert_not_called()


@pytest.mark.parametrize("finish,content", [("length", "partial"), ("content_filter", ""), ("stop", "bad schema")])
def test_other_incomplete_or_schema_response_not_retried(tmp_path, data, funded, finish, content):
    send = Mock(side_effect=sender(data, finish=finish, content=content))
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        report = q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert send.call_count == 3 and report["remaining_missing"] == list(q.TARGETS)


@pytest.mark.parametrize("failure", ["identity", "usage", "authentication"])
def test_integrity_errors_stop_without_retry(tmp_path, data, funded, failure):
    def broken(request):
        if failure == "authentication":
            raise TransportError(401)
        raw = sender(data)(request)
        if failure == "identity":
            raw["model"] = "wrong"
        else:
            raw.pop("usage")
        return raw
    send = Mock(side_effect=broken)
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        with pytest.raises(Halted):
            q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert send.call_count == 1 and ledger.rows()[0]["status"] == "unresolved"


def test_two_dollar_cap_counts_every_failed_attempt(tmp_path, data, funded):
    send = Mock(side_effect=TransportError(200))
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        with pytest.raises(BudgetExceeded):
            q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        assert send.call_count == 4
        assert Decimal("1.9") < ledger.spent() <= 2
        assert all(r["status"] == "unresolved" for r in ledger.rows())


@pytest.mark.parametrize("field,value", [("confirmed", False), ("account_balance_usd", "146.99"),
                                       ("kolibri_holdback_usd", "44"), ("scope_prior_bound_usd", "125"),
                                       ("scope_other_commitments_usd", "73"), ("account_balance_usd", "NaN")])
def test_funding_guards_prior_costs_and_other_commitments(funded, field, value):
    q.check_funding(funded)
    funded[field] = value
    with pytest.raises((Halted, ValueError)):
        q.check_funding(funded)


def test_stale_funding_prevents_dispatch(tmp_path, data, funded):
    funded["as_of_utc"] = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    send = Mock()
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        with pytest.raises(Halted, match="stale"):
            q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        send.assert_not_called()
        assert not ledger.rows()


def test_pending_call_never_automatically_resent(tmp_path, data, funded):
    call_id = q.TARGETS[0]
    request = data["targets"][call_id]["original"]["request"]
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        ledger.reserve(q.attempt_id(call_id, 1), request, q.reservation(data["spec"], request), "main",
                       q.attempt_metadata(call_id, 1, FREEZE, PLAN_HASH))
        send = Mock()
        with pytest.raises(Halted, match="Pending"):
            q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        send.assert_not_called()


def test_recovery_plan_tamper_and_generation_call_rejected(tmp_path, data, funded, monkeypatch):
    plan = q.build_plan(data)
    path = tmp_path / q.PLAN
    q.write_once(path, plan)
    monkeypatch.setattr(q, "ROOT", tmp_path)
    monkeypatch.setattr(q, "build_plan", lambda data=None: plan)
    assert q.verify(path, data=data) == plan
    wrong = {**plan, "cap_usd": "3"}
    path.write_text(json.dumps(wrong))
    with pytest.raises(Halted, match="binding"):
        q.verify(path, data=data)
    with Ledger(tmp_path / "ledger", cap="2", screen_cap="2") as ledger:
        ledger.reserve("gen:forbidden", {}, "1", "main", {})
        with pytest.raises(Halted, match="generations"):
            q.audit(ledger, data, FREEZE, PLAN_HASH)


def test_no_relabeling_outside_three_or_overwriting_valid_labels(data):
    with pytest.raises(Halted, match="Unexpected"):
        q.project(data, {"recovered": {"judge:other": {}}})
    changed = deepcopy(data)
    item = next(r for r in changed["rows"] if r["id"] == q.TARGETS[0].split(":")[1])
    item["labels"]["astra"]["structured"] = {"inclusive_current_assertion": True}
    with pytest.raises(Halted, match="completed"):
        q.project(changed, {"recovered": {q.TARGETS[0]: {}}})


def test_cli_never_executes_without_freeze_and_preflight():
    with pytest.raises(SystemExit):
        q.main(["--execute"])


def test_broader_ledger_cannot_replace_two_dollar_sidecar(tmp_path, data, funded):
    with Ledger(tmp_path, cap="200", screen_cap="25") as ledger:
        send = Mock()
        with pytest.raises(Halted, match="own \\$2 ledger"):
            q.recover(ledger, data, FREEZE, PLAN_HASH, send, funded, sleep=lambda s: None)
        send.assert_not_called()


def test_second_attempt_after_valid_label_is_rejected(tmp_path, data, funded):
    with Ledger(tmp_path, cap="2", screen_cap="2") as ledger:
        q.recover(ledger, data, FREEZE, PLAN_HASH, sender(data), funded, sleep=lambda s: None)
        call_id = q.TARGETS[0]
        request = data["targets"][call_id]["original"]["request"]
        ledger.reserve(q.attempt_id(call_id, 2), request, q.reservation(data["spec"], request), "main",
                       q.attempt_metadata(call_id, 2, FREEZE, PLAN_HASH))
        raw = sender(data)(request)
        ledger.settle(q.attempt_id(call_id, 2), raw, q.receipt_cost(data["spec"], raw))
        with pytest.raises(Halted, match="Completed"):
            q.audit(ledger, data, FREEZE, PLAN_HASH)


def test_pushed_freeze_must_bind_plan_and_sources(tmp_path, monkeypatch):
    plan = {"source_hashes": {"source.py": q.sha(b"bound\n")}}
    path = tmp_path / q.PLAN
    q.write_once(path, plan)
    monkeypatch.setattr(q, "ROOT", tmp_path)
    monkeypatch.setattr(q, "build_plan", lambda data=None: plan)
    def git(*args):
        if args[0] == "rev-parse":
            return FREEZE.encode()
        if args[0] == "merge-base":
            return b""
        if args[0] == "ls-remote":
            return (FREEZE + "\t" + q.production.BRANCH).encode()
        if args == ("show", f"{FREEZE}:{q.PLAN}"):
            return path.read_bytes()
        if args == ("show", f"{FREEZE}:source.py"):
            return b"bound\n"
        raise AssertionError(args)
    monkeypatch.setattr(q.production, "git", git)
    assert q.verify(path, FREEZE, pushed=True, data={}) == plan
    monkeypatch.setattr(q.production, "git", lambda *args: b"" if args[0] == "ls-remote" else git(*args))
    with pytest.raises(Halted, match="pushed"):
        q.verify(path, FREEZE, pushed=True, data={})
    with pytest.raises(Halted, match="Fresh"):
        q.verify(path, q.RELEASE_COMMIT, data={})
