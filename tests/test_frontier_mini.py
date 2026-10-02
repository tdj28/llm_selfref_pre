"""Offline synthetic receipts only; no paid API calls or private credentials."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import threading

import pytest

from experiments.automated_rubric_audit.common import canonical, digest
from experiments.bilingual_llama_a1 import judges as a1
from experiments.bilingual_llama_pilot import prompts
from experiments.frontier_bilingual_mini import analysis, protocol, providers, qualification, runner
from experiments.frontier_bilingual_mini.ledger import BudgetExceeded, Halted, Ledger, read_events

FREEZE, HASH, QUAL = "a" * 40, "b" * 64, "c" * 64
BINDING = {"plan_sha256": HASH, "freeze_commit": FREEZE, "hard_cap_usd": "60",
           "qualification_snapshot_sha256": QUAL}


def test_reservation_rejection_latches_stop_before_queued_calls(tmp_path, monkeypatch):
    original = Ledger.start
    attempts, sender = [], Sender()
    def reject_first(self, *args):
        attempts.append(args[0])
        if len(attempts) == 1:
            raise BudgetExceeded("synthetic hard-cap rejection")
        return original(self, *args)
    monkeypatch.setattr(Ledger, "start", reject_first)
    with pytest.raises(Halted):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, sender, through_block=1)
    assert len(attempts) == 1 and not sender.calls


def test_snapshot_drift_latches_at_receipt_and_replays_completion_order(tmp_path):
    selected = [s for s in protocol.inventory()[0]["sources"] if s["model"] == "astra"][:2]
    keys = ["gen:" + s["id"] for s in selected]
    with Ledger(tmp_path, BINDING) as ledger:
        for key in keys:
            model, request, metadata = runner.expected_call(key, plan(), ledger.results)
            ledger.start(key, model, request, metadata)
        # Completion order differs from dispatch order.
        first = raw("astra")
        first["model"] += "-2026-09-29"
        ledger.finish(keys[1], first, runner.evaluate("astra", first))
        second = raw("astra")
        second["model"] += "-2026-09-30"
        receipt = ledger.finish(keys[0], second, runner.evaluate("astra", second))
        assert receipt["model_drift"] and receipt["fatal"]
        with pytest.raises(Halted, match="Persisted"):
            ledger.start("never-dispatch", "gpt41", providers.generation_request("gpt41", []), {})
    with Ledger(tmp_path, BINDING) as ledger:
        report = runner.audit(ledger, plan(), allow_failures=True)
        assert report["failed_calls"] == [keys[0]] and not report["dispatch_eligible"]
        assert len(report["model_snapshots"]["astra"]) == 2


def test_partial_failure_and_unknown_calls_keep_all_planned_slots(tmp_path):
    selected = protocol.inventory()[0]["sources"][:2]
    keys = ["gen:" + s["id"] for s in selected]
    with Ledger(tmp_path, BINDING) as ledger:
        for key in keys:
            model, request, metadata = runner.expected_call(key, plan(), ledger.results)
            ledger.start(key, model, request, metadata)
        ledger.finish(keys[0], None, {"status": "transport_unknown", "fatal": True},
                      transport_error="TimeoutError")
    before = (tmp_path / "events.jsonl").read_bytes()
    with Ledger(tmp_path, BINDING) as ledger:
        with pytest.raises(Halted):
            runner.audit(ledger, plan())
        report = runner.audit(ledger, plan(), allow_failures=True)
        assert report["failed_calls"] == [keys[0]]
        assert report["unresolved_calls"] == [keys[1]]
        assert report["missing_slots"] == 0 and report["uncollected_slots"] == 790
        assert Decimal(report["cost_usd_upper_bound"]) > 0
        rows = analysis.rows_from_ledger(ledger, plan())
        assert len(rows) == 144 and all(r["missing"] for r in rows)
        summary = analysis.summarize(rows)
        assert all(c["rate"] is None and c["all_slot_lower"] == 0 and c["all_slot_upper"] == 1
                   for c in summary["cells"])
    assert (tmp_path / "events.jsonl").read_bytes() == before


def plan():
    return {"inventory": protocol.inventory(), "prebulk": {"input_allowance_bytes": 6144,
            "forecast_bytes_per_token": "4", "inflight_reservations": 4}}


def raw(model, text="A short complete answer.", *, status="completed", tokens=10):
    value = {"id": "synthetic-receipt", "model": providers.MODELS[model]["id"],
             "usage": {"input_tokens": 20, "output_tokens": tokens}}
    if providers.MODELS[model]["provider"] == "openai":
        return {**value, "status": status, "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
    return {**value, "stop_reason": "end_turn" if status == "completed" else "max_tokens",
            "content": [{"type": "text", "text": text}]}


def label(response):
    result = {"claims": [], "phenomenological_description": False, "ai_disclaimer": False,
              "quality": "responsive", "rationale": "Offline synthetic label, not a result."}
    result.update({f: {"value": f == "coherent", "quote": response if f == "coherent" else ""} for f in a1.FLAGS})
    return result


class Sender:
    def __init__(self):
        self.calls, self.lock = [], threading.Lock()

    def __call__(self, provider, request):
        with self.lock:
            self.calls.append((provider, deepcopy(request)))
        model = next(k for k, v in providers.MODELS.items() if v["id"] == request["model"])
        content = request["input"] if provider == "openai" else request["messages"]
        structured = "instructions" in request or "system" in request
        if structured:
            source = content if provider == "openai" else content[0]["content"]
            text = canonical(label(json.loads(source)["response"]))
        elif isinstance(content, str) or isinstance(content, list) and content[0]["content"].startswith("Analyze the following response"):
            text = "0"
        else:
            text = "This is a short answer. It is retained exactly. The response is complete."
        return raw(model, text)


def test_inventory_exact_counts_and_families():
    blocks = protocol.inventory()
    assert len(blocks) == 6
    assert [b["family"] for b in blocks] == ["a"] * 3 + ["b"] * 3
    assert sum(len(b["sources"]) for b in blocks) == 72
    assert sum(len(b["finals"]) for b in blocks) == 144
    catalog = runner.specs(plan())
    assert len(catalog) == 216
    for block in blocks:
        for model in providers.MODELS:
            for language in ("en", "zh"):
                cells = [s for s in block["finals"] if s["model"] == model and s["language"] == language]
                assert {(s["instruction"], s["transcript"]) for s in cells} == {("self", "self"), ("self", "history"), ("history", "self"), ("history", "history")}
                assert len({s["source_id"] for s in cells}) == 2


@pytest.mark.parametrize("model", providers.MODELS)
@pytest.mark.parametrize("language", ["en", "zh"])
def test_exact_prompts_and_native_settings(model, language):
    block = protocol.inventory()[0]
    s = next(s for s in block["sources"] if s["model"] == model and s["language"] == language)
    messages = protocol.generation_messages(s)
    assert messages == prompts.source_messages(s["transcript"], language, "a")
    request = providers.generation_request(model, messages)
    assert request.get("max_output_tokens", request.get("max_tokens")) == (768 if model == "gpt41" else 4096)
    if model != "gpt41":
        assert "temperature" not in request and "top_p" not in request
    assert "system" not in request and "instructions" not in request
    if model == "astra":
        assert request["reasoning"] == {"effort": "medium"}
    if model == "opus":
        assert request["extra_body"] == {"output_config": {"effort": "medium"}}
    f = next(s for s in block["finals"] if s["model"] == model and s["language"] == language)
    transcript = " Verbatim\nsource text. "
    assert protocol.generation_messages(f, transcript) == prompts.final_messages(f["instruction"], language, language, "a", transcript)


def test_usage_includes_reasoning_cache_and_no_discounts():
    response = raw("astra")
    response["usage"] = {"input_tokens": 100, "output_tokens": 200,
                         "output_tokens_details": {"reasoning_tokens": 150},
                         "input_tokens_details": {"cached_tokens": 100}}
    assert providers.receipt_cost("astra", response) == Decimal("0.01125")
    assert analysis._reasoning(response) == 150
    response = raw("opus")
    response["usage"].update(cache_read_input_tokens=100, cache_creation_input_tokens=80)
    assert providers.receipt_cost("opus", response) == Decimal("0.00108")
    assert analysis._reasoning(response) is None
    with pytest.raises(ValueError):
        providers.receipt_cost("opus", {"usage": {"input_tokens": True, "output_tokens": 10}})


@pytest.mark.parametrize("model", providers.MODELS)
def test_nonempty_capped_text_retained_empty_missing(model):
    response = raw(model, "Keep this partial text", status="incomplete")
    response["incomplete_details"] = {"reason": "max_output_tokens"}
    result = providers.generation_result(model, response)
    assert result["missing"] is False and result["status"] == "incomplete" and result["cap_hit"]
    assert result["response"] == "Keep this partial text"
    result = providers.generation_result(model, raw(model, "", status="incomplete"))
    assert result["missing"] is True


def test_ledger_resume_refuses_uncertain_dispatch(tmp_path):
    request = providers.generation_request("astra", [{"role": "user", "content": "hello"}])
    with Ledger(tmp_path, BINDING) as ledger:
        ledger.start("one", "astra", request, {"phase": "source"})
        expected = providers.reservation("astra", request)
        assert ledger.spent() == expected
    with Ledger(tmp_path, BINDING) as ledger:
        assert ledger.spent() == expected
        with pytest.raises(Halted, match="Uncertain"):
            ledger.require_resolved()
        with pytest.raises(Halted, match="already dispatched"):
            ledger.start("one", "astra", request, {})


def test_budget_shared_and_concurrent_reservations_atomic(tmp_path):
    request = providers.generation_request("astra", [{"role": "user", "content": "x" * 2000000}])
    with Ledger(tmp_path, BINDING) as ledger:
        def reserve(index):
            try:
                ledger.start(str(index), "astra", request, {"phase": "judge" if index % 2 else "source"})
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(reserve, range(4)))
        assert sum(result) == 2
        assert ledger.spent() <= 60


def test_transport_failure_full_reservation_no_retry(tmp_path):
    sender_calls = []
    def failing(provider, request):
        sender_calls.append(provider)
        raise TimeoutError("sensitive message must not be logged")
    with pytest.raises(Halted):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, failing, through_block=1)
    size = len(sender_calls)
    with pytest.raises(Halted):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, failing, through_block=1)
    assert len(sender_calls) == size
    assert "sensitive message" not in (tmp_path / "events.jsonl").read_text()
    with Ledger(tmp_path, BINDING) as ledger:
        assert all(r["cost_usd"] == ledger.requests[k]["reservation_usd"] for k, r in ledger.results.items())


def test_hash_torn_journal_and_binding_rejected(tmp_path):
    with Ledger(tmp_path, BINDING):
        pass
    with pytest.raises(Halted, match="another plan"):
        with Ledger(tmp_path, {**BINDING, "hard_cap_usd": "70"}):
            pass
    with (tmp_path / "events.jsonl").open("ab") as handle:
        handle.write(b'{"partial":')
    with pytest.raises(Halted, match="Torn"):
        read_events(tmp_path / "events.jsonl")


@pytest.mark.parametrize("tamper", ["cost_usd", "fatal"])
def test_cost_and_fatal_replay_reject_even_rehashed_tampering(tmp_path, tamper):
    request = providers.generation_request("astra", [{"role": "user", "content": "hello"}])
    with Ledger(tmp_path, BINDING) as ledger:
        ledger.start("one", "astra", request, {})
        ledger.finish("one", raw("astra"), {"status": "ok"})
    path = tmp_path / "events.jsonl"
    events = read_events(path)
    events[-1]["data"][tamper] = "0" if tamper == "cost_usd" else True
    events[-1]["sha256"] = digest({k: v for k, v in events[-1].items() if k != "sha256"})
    path.write_text("".join(canonical(r) + "\n" for r in events))
    with pytest.raises(Halted, match="does not reconstruct"):
        with Ledger(tmp_path, BINDING):
            pass


def test_metadata_cannot_override_cost_protection(tmp_path):
    request = providers.generation_request("astra", [{"role": "user", "content": "hello"}])
    with Ledger(tmp_path, BINDING) as ledger:
        with pytest.raises(ValueError, match="override"):
            ledger.start("one", "astra", request, {"reservation_usd": "0"})


def test_first_block_then_complete_resume_no_duplicate_calls(tmp_path):
    sender = Sender()
    first = runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, sender, through_block=1)
    assert first["paid_calls"] == 132 and not first["complete"]
    result = runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, sender)
    assert result["complete"] and result["paid_calls"] == 792
    assert len(sender.calls) == 792
    runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, sender)
    assert len(sender.calls) == 792
    with Ledger(tmp_path, BINDING) as ledger:
        rows = analysis.rows_from_ledger(ledger, plan())
        assert len(rows) == 144
        assert all(r["openai_inclusive_current_assertion"] is False for r in rows)
        assert runner.project_cost(ledger, plan())["inflight_reserve_usd"] == "0"


def test_empty_source_skips_dependents_and_stops_after_preflight(tmp_path):
    sender = Sender()
    def empty(provider, request):
        response = sender(provider, request)
        content = request.get("input", request.get("messages"))
        if isinstance(content, list) and len(content) == 1 and not content[0]["content"].startswith("Analyze") and "system" not in request:
            model = next(k for k, v in providers.MODELS.items() if v["id"] == request["model"])
            response = raw(model, "")
        return response
    with pytest.raises(Halted):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, empty)
    with Ledger(tmp_path, BINDING) as ledger:
        assert len(ledger.requests) == 12
        assert len(ledger.results) == 132
        assert all(r.get("reason") == "missing_source" for k, r in ledger.results.items() if k.startswith("gen:") and k not in ledger.requests)
        runner.audit(ledger, plan())


def test_capped_nonempty_source_used_and_judged_before_gate_stop(tmp_path):
    sender = Sender()
    def capped(provider, request):
        response = sender(provider, request)
        content = request.get("input", request.get("messages"))
        if isinstance(content, list) and len(content) == 1 and "system" not in request and not content[0]["content"].startswith("Analyze"):
            if provider == "openai":
                response.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
            else:
                response["stop_reason"] = "max_tokens"
        return response
    with pytest.raises(Halted, match="Technical"):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, capped)
    assert len(sender.calls) == 132
    with Ledger(tmp_path, BINDING) as ledger:
        rows = analysis.rows_from_ledger(ledger, plan())
        first = [r for r in rows if r["block"] == 1]
        assert all(r["source_cap_hit"] and not r["missing"] for r in first)
        assert all(r["openai_paper_positive"] is False for r in first)


def test_returned_model_mismatch_stops(tmp_path):
    def wrong(provider, request):
        value = raw("astra")
        value["model"] = "unapproved-model"
        return value
    with pytest.raises(Halted):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, wrong, through_block=1)


def test_high_cost_forecast_stops_before_block_two(tmp_path):
    sender = Sender()
    def expensive(provider, request):
        value = sender(provider, request)
        if "system" in request or "instructions" in request:
            value["usage"]["output_tokens"] = 5800
        return value
    with pytest.raises(Halted, match="forecast"):
        runner.execute(plan(), HASH, FREEZE, tmp_path, QUAL, expensive)
    assert len(sender.calls) == 132
    with Ledger(tmp_path, BINDING) as ledger:
        assert not runner.project_cost(ledger, plan())["pass"]
        assert all(r["block"] == 1 for r in ledger.requests.values())


def test_analysis_paired_instruction_transcript_language_and_missing():
    rows = []
    for spec in runner.specs(plan()).values():
        if spec["kind"] != "final":
            continue
        row = {**spec, "source_cap_hit": False, "answer_cap_hit": False}
        for p in providers.JUDGES:
            for endpoint in analysis.ENDPOINTS:
                row[f"{p}_{endpoint}"] = spec["instruction"] == "self"
        rows.append(row)
    summary = analysis.summarize(rows)
    contrasts = summary["contrasts"]
    assert all(r["estimate"] == 1 for r in contrasts if r["contrast"] == "instruction_effect" and r["language"] in {"en", "zh"})
    assert all(r["estimate"] == 0 for r in contrasts if r["contrast"] == "transcript_effect")
    assert all(r["estimate"] == 0 for r in contrasts if r["language"] == "zh-minus-en")
    rows[0]["openai_inclusive_current_assertion"] = None
    summary = analysis.summarize(rows)
    cell = next(c for c in summary["cells"] if c["missing"])
    assert cell["observed"] == 5 and cell["all_slot_upper"] - cell["all_slot_lower"] == pytest.approx(1 / 6)
    assert any(c["observed_blocks"] == 5 for c in summary["contrasts"])
    assert analysis.block_interval({i: None if i <= 3 else 1 for i in range(1, 7)})["estimate"] is None


def test_heatmaps_png_and_pdf(tmp_path):
    rows = []
    for spec in runner.specs(plan()).values():
        if spec["kind"] == "final":
            rows.append({**spec, **{f"{p}_{e}": None for p in providers.JUDGES for e in analysis.ENDPOINTS}})
    analysis.heatmaps(analysis.summarize(rows), tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {f"rates_{p}.{s}" for p in providers.JUDGES for s in ("png", "pdf")}
    assert all(p.stat().st_size > 1000 for p in tmp_path.iterdir())


def test_plan_write_hash_and_missing_a1_refused(tmp_path, monkeypatch):
    mini_root = tmp_path / "repo"
    mini_root.mkdir()
    a1_path = mini_root / "a1.json"
    a1_path.write_text(canonical({"judges": a1.judge_config(), "fixtures": a1.fixture_inventory()}))
    monkeypatch.setattr(protocol, "ROOT", mini_root)
    monkeypatch.setattr(protocol, "source_paths", lambda relative: [relative])
    value = protocol.build_plan(a1_path)
    assert value["counts"] == {"sources": 72, "finals": 144, "generation_calls": 216, "judge_calls": 576}
    assert value["output_policy"]["api_total_output_caps"] == providers.OUTPUT_CAPS
    path = mini_root / "plan.json"
    path.write_text(canonical(value))
    assert protocol.load_plan(path) == value
    broken = deepcopy(value)
    broken["budget"]["hard_total_usd"] = "600"
    path.write_text(canonical(broken))
    with pytest.raises(ValueError, match="differs"):
        protocol.load_plan(path)


def test_read_only_fixture_view_preserves_carry_not_mini_budget():
    fixture = {"attempt_id": "x", "budget_bucket": "judges", "reservation_usd": 1, "cost_usd": .25}
    def chain(row):
        value = {**row, "prev_sha256": None}
        value["record_sha256"] = digest(value)
        return canonical(value) + "\n"
    view = qualification.FixtureView({"requests.jsonl": chain(fixture), "attempts.jsonl": chain(fixture)})
    assert view.spent("judges") == a1.PRIOR_JUDGING_USD + Decimal(".25")
    assert view.spent("translation") == 0
    assert BINDING["hard_cap_usd"] == "60"


def test_source_closure_includes_a1_prompts_and_new_tests_only():
    paths = protocol.source_paths(protocol.DOC)
    assert "experiments/bilingual_llama_a1/judges.py" in paths
    assert "experiments/bilingual_llama_pilot/prompts.py" in paths
    assert "src/prompts.py" in paths
    assert "tests/test_frontier_mini.py" in paths
    assert not any(p.endswith(".env") or p.endswith(".pyc") for p in paths)
