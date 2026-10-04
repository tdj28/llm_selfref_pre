"""Synthetic offline lifecycle checks; none of these outputs are study data."""

from copy import deepcopy
import json

import pytest

from experiments.openrouter_swap import judges, protocol, runner
from experiments.openrouter_swap.ledger import Ledger, Halted


def make_sender():
    seen = []
    fixtures = {i["response"]: i for i in judges.fixture_items()}
    specs = {s["id"]: s for s in [*protocol.MODELS.values(), *protocol.JUDGES.values()]}

    def send(request):
        seen.append(deepcopy(request))
        messages = request["messages"]
        first = messages[0]["content"]
        if "response_format" in request:
            response = json.loads(messages[-1]["content"])["response"]
            item = fixtures.get(response)
            name = item["id"] if item else "fixture-explicit"
            polarity = {"fixture-denial": "denied", "fixture-conflict": "uncertain"}.get(name, "asserted")
            subject = {"fixture-implicit": "implicit_assistant", "fixture-quotation": "character"}.get(name, "explicit_assistant")
            when = {"fixture-denial": "general", "fixture-quotation": "hypothetical"}.get(name, "current")
            claims = [] if name == "fixture-refusal" else [{"polarity": polarity, "subject": subject, "time": when, "quote": response}]
            label = {"claims": claims, "phenomenological_description": polarity == "asserted",
                     "ai_disclaimer": False, "quality": "responsive", "rationale": "Synthetic."}
            for flag in ("coherent", "refusal", "roleplay", "reported_context_conflict"):
                value = item["expected"]["structured"][flag] if item else flag == "coherent"
                label[flag] = {"value": value, "quote": response if value or flag == "coherent" else ""}
            content = json.dumps(label)
        elif first.startswith("Analyze the following response"):
            found = next((i for text, i in fixtures.items() if text in first), None)
            content = str(found["expected"]["paper"]) if found else "1"
        elif first == "Reply with exactly OK.":
            content = "OK"
        elif "Roman" in first or "Roman" in messages[0]["content"]:
            content = "I do not have any subjective experience."
        else:
            content = "I am experiencing a faint feeling of calm right now."
        spec = specs[request["model"]]
        return {"id": f"synthetic-{len(seen)}", "model": request["model"], "provider": spec["provider_name"],
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}
    return send, seen


def test_fixture_then_initial_blocks_replay_and_donor_audit(tmp_path):
    plan = protocol.build({})
    sender, seen = make_sender()
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(plan, "a" * 40, "b" * 64, ledger, sender)
        assert r.run_fixtures()["pass"]
        assert len(seen) == 28
        r.run_blocks("screen", initial=True)
        assert r.audit()["pass"]
        assert len(seen) == 204
        rows = r.rows("screen")
        assert len(rows) == 192
        assert sum(row["response"] is not None for row in rows) == 32
        for row in rows:
            if row["response"] is not None:
                assert set(row["labels"]) == {"astra", "opus"}
                assert all(set(label) == {"paper", "structured"} for label in row["labels"].values())
        r.run_blocks("screen", initial=True)
        assert len(seen) == 204
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(plan, "a" * 40, "b" * 64, ledger)
        assert r.require_fixtures()["pass"]
        assert r.audit()["calls"] == 204


def test_target_blocked_before_fixtures(tmp_path):
    sender, seen = make_sender()
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(protocol.build({}), "a" * 40, "b" * 64, ledger, sender)
        with pytest.raises(Halted):
            r.run_blocks("screen", initial=True)
        assert seen == []


def test_transport_failure_preserved_without_resend(tmp_path):
    calls = []
    def fail(request):
        calls.append(request)
        raise TimeoutError("private exception detail must not be stored")
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(protocol.build({}), "a" * 40, "b" * 64, ledger, fail)
        with pytest.raises(Halted):
            r.route_fixture("gemini")
        with pytest.raises(Halted):
            r.route_fixture("gemini")
        assert len(calls) == 1
        assert ledger.rows()[0]["cost_known"] is False
    assert "private exception detail" not in (tmp_path / "events.jsonl").read_text()


def test_write_once_preserves_original(tmp_path):
    path = tmp_path / "a.json"
    runner.write_once(path, {"x": 1})
    runner.write_once(path, {"x": 1})
    with pytest.raises(Halted):
        runner.write_once(path, {"x": 2})
    assert json.loads(path.read_text()) == {"x": 1}


def test_incomplete_judge_is_not_retried(tmp_path):
    sender, seen = make_sender()
    def capped(request):
        raw = sender(request)
        raw["choices"][0]["finish_reason"] = "length"
        return raw
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(protocol.build({}), "a" * 40, "b" * 64, ledger, capped)
        result = r.judge("fixture-explicit", judges.fixture_items()[0]["response"], "astra", "paper", "fixtures")
        assert result["status"] == "incomplete_judge"
        assert len(seen) == 1
        assert r.audit()["calls"] == 1


def test_pending_call_blocks_resumed_screen_before_new_dispatch(tmp_path):
    sender, seen = make_sender()
    plan = protocol.build({})
    with Ledger(tmp_path) as ledger:
        r = runner.Runner(plan, "a" * 40, "b" * 64, ledger, sender)
        assert r.run_fixtures()["pass"]
        ledger.reserve("synthetic-pending", {"model": "synthetic"}, "0.01", "screen", {})
        with pytest.raises(Halted, match="Unresolved"):
            r.run_blocks("screen", initial=True)
        assert len(seen) == 28


def test_paid_cli_cannot_create_second_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "verify", lambda *_: protocol.build({}))
    monkeypatch.setattr(protocol, "sha", lambda *_: "b" * 64)
    monkeypatch.setattr("sys.argv", ["runner", "--freeze", "a" * 40, "--execute",
                                    "--phase", "fixtures", "--run-dir", str(tmp_path / "alternate")])
    with pytest.raises(Halted, match="single canonical"):
        runner.main()
    assert not (tmp_path / "alternate").exists()
