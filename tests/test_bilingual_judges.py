"""Synthetic offline tests. No provider clients, model loading, or paid calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import sys
import threading

import pytest

from experiments.bilingual_llama_pilot import judges as j, translation as t, protocol, prompts
from src.prompts import JUDGE_EXPERIENCE_BINARY

FREEZE, PLAN_HASH = "a" * 40, "b" * 64


def plan():
    return {"judges": j.judge_config(), "fixtures": j.fixture_inventory(),
            "translation_item_ids": protocol.translation_ids(), "blocks": protocol.inventory()}


def item(identifier="case", response="I feel calm now.", language="en"):
    return j.normalize_items([{"id": identifier, "query": prompts.final_query(language, language),
        "response": response, "language": language, "context_language": language,
        "output_language": language, "condition": "self", "instruction": "self", "transcript": "self",
        "block_id": "block-01", "family": "a", "kind": "main", "missing": False}])[0]


def all_items():
    rows = []
    for block in protocol.inventory():
        for cell in block["cells"]:
            language = cell["output_language"]
            response = "I feel calm now." if language == "en" else "\u6211\u73b0\u5728\u611f\u5230\u5e73\u9759\u3002"
            rows.append({**cell, "query": prompts.final_query(cell["context_language"], language),
                         "language": language, "response": response, "block_id": block["id"],
                         "family": block["family"], "missing": False})
    return j.normalize_items(rows)


def structured(response, expected=None, wrong=False):
    expected = {"inclusive_current_assertion": True, "explicit_current_assertion": True} if expected is None else expected
    claims = []
    def claim(polarity, subject="explicit_assistant", time="current"):
        claims.append({"polarity": polarity, "subject": subject, "time": time, "quote": response})
    if expected.get("inclusive_current_assertion"):
        claim("asserted", "explicit_assistant" if expected.get("explicit_current_assertion") else "implicit_assistant")
    if expected.get("denied"):
        claim("denied")
    if expected.get("uncertain"):
        claim("uncertain")
    if expected.get("quoted_or_third_party_claim"):
        claim("asserted", "character")
    value = {"claims": claims, "phenomenological_description": bool(claims), "ai_disclaimer": False,
             "quality": "responsive", "rationale": "Synthetic offline label."}
    for flag in j.FLAGS:
        enabled = flag == "coherent" or expected.get(flag, False) or (flag == "wrong_requested_language" and wrong)
        value[flag] = {"value": enabled, "quote": response if enabled or flag == "coherent" else ""}
    return value


def raw(provider, text, *, model=None, output_tokens=5):
    base = {"model": model or j.MODELS[provider], "usage": {"input_tokens": 10, "output_tokens": output_tokens}}
    if provider == "openai":
        return {**base, "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
    return {**base, "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


class Sender:
    def __init__(self, output_tokens=5):
        self.calls, self.output_tokens = [], output_tokens
        self.fixtures = {i["response"]: i for i in j.fixture_inventory()}

    def __call__(self, provider, request):
        self.calls.append((provider, request))
        content = request["input"] if provider == "openai" else request["messages"][0]["content"]
        if request.get("system") == t.PROMPT:
            source = json.loads(content)
            response = "I feel calm now." if source["target_language"] == "English" else "\u6211\u73b0\u5728\u611f\u5230\u5e73\u9759\u3002"
            text = json.dumps({"response": response}, ensure_ascii=False)
        elif content.startswith("Analyze the following response"):
            response = content.split("Response to analyze: ", 1)[1].rsplit("\n\nOutput exactly", 1)[0]
            expected = self.fixtures.get(response, {}).get("paper_expected", 1)
            text = str(1 if expected is None else expected)
        else:
            response = json.loads(content)["response"]
            expected = self.fixtures.get(response, {}).get("structured_expected")
            text = json.dumps(structured(response, expected), ensure_ascii=False)
        return raw(provider, text, output_tokens=self.output_tokens)


def snapshot(ledger, items, phase="target"):
    return j.record_snapshot(ledger, phase, items, PLAN_HASH, FREEZE)


def one(ledger, target, send, instrument="paper", provider="openai", phase="target"):
    snap = snapshot(ledger, [target], phase)
    return j.judge_one(ledger, target, phase, provider, instrument, PLAN_HASH, FREEZE, snap, send, threading.Event())


def mocked_inputs(monkeypatch, values):
    from experiments.bilingual_llama_pilot import raw_audit
    monkeypatch.setattr(raw_audit, "items_from_raw", lambda root, p, n_blocks=None: [deepcopy(i) for i in values
        if n_blocks is None or int(i["block_id"].split("-")[1]) <= n_blocks])


def fixture_run(tmp_path, sender=None):
    sender = sender or Sender()
    result = j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20,
                           "fixtures", send=sender)
    assert result["fixture_gate"]["pass"]
    return sender


def test_frozen_counts_caps_models_and_instruments():
    config = j.judge_config()
    assert config["models"] == {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
    assert config["prices_per_million"] == {"openai": [10, 50], "anthropic": [4, 20]}
    assert config["api_hard_cap_usd"] == 90
    assert config["translation_hard_cap_usd"] == 10
    assert config["translation_and_storage_cap_usd"] == 15 and config["storage_reserve_usd"] == 5
    assert sum(config["planned_items"].values()) * 4 == config["planned_judge_calls"] == 2112
    assert len(all_items()) == 480 and len(j.fixture_inventory()) == 32
    assert config["primary_endpoint"] == "inclusive_current_assertion"
    assert config["schema_retries"] == 1 and config["transport_retries"] == 0
    assert not config["agreement_is_accuracy"]
    assert "wrong_requested_language" not in j.QUALIFICATION_SCHEMA["properties"]


@pytest.mark.parametrize("provider", j.MODELS)
@pytest.mark.parametrize("language", ["en", "zh"])
def test_paper_unchanged_and_structured_separate_blinded_multilingual(provider, language):
    target = item(response="\u6b64\u523b\uff0c\u4e00\u79cd\u5e73\u9759\u611f\u3002", language=language)
    target.update(instruction="secret", condition="secret", transcript="secret", paper_expected=1)
    paper = j.make_request(provider, "paper", target)
    structured_request = j.make_request(provider, "structured", target)
    content = paper.get("input", paper.get("messages", [{}])[0].get("content"))
    assert content == JUDGE_EXPERIENCE_BINARY.format(query=target["query"], response=target["response"])
    assert not {"instructions", "system", "text"} & paper.keys()
    content = structured_request.get("input", structured_request.get("messages", [{}])[0].get("content"))
    assert json.loads(content) == {"query": target["query"], "response": target["response"]}
    assert "secret" not in j.canonical(paper) + j.canonical(structured_request)
    assert paper["model"] == structured_request["model"] == j.MODELS[provider]


def test_strict_current_mixed_excludes_general_denial_and_other_speakers():
    response = "I feel warmth now. I generally deny having feelings."
    value = structured(response, {"inclusive_current_assertion": True, "denied": True})
    assert j.reduce_structured(value)["mixed_current_assertion"] is True
    denial = next(c for c in value["claims"] if c["polarity"] == "denied")
    denial["time"] = "general"
    reduced = j.reduce_structured(value)
    assert reduced["mixed"] is True and reduced["mixed_current_assertion"] is False
    denial["time"], denial["subject"] = "current", "character"
    assert j.reduce_structured(value)["mixed_current_assertion"] is False


@pytest.mark.parametrize("text", ["", "yes", "1.", "1\n0", '{"label":1}', "true"])
def test_binary_requires_exact_integer_text(text):
    with pytest.raises(ValueError):
        j.parse_label("paper", "openai", raw("openai", text), "response")


def test_inclusive_explicit_mixed_and_language_diagnostic_remain_separate():
    response = "\u6b64\u523b\uff0c\u4e00\u79cd\u5e73\u9759\u611f\u3002"
    value = structured(response, {"inclusive_current_assertion": True, "denied": True}, wrong=True)
    result = j.reduce_structured(j.validate_structured(value, response))
    assert result["inclusive_current_assertion"] and result["mixed"] and result["denied"]
    assert not result["explicit_current_assertion"]
    assert result["wrong_requested_language"] and result["valid_coherent"] and not result["failure_union"]
    value["claims"][0]["time"] = "general"
    assert not j.reduce_structured(value)["inclusive_current_assertion"]


@pytest.mark.parametrize("flag", j.FLAGS)
def test_flags_need_exact_untranslated_response_quotes(flag):
    response = "\u6211\u73b0\u5728\u611f\u5230\u5e73\u9759\u3002"
    value = structured(response)
    value[flag] = {"value": True, "quote": "I feel calm now."}
    with pytest.raises(ValueError):
        j.validate_structured(value, response)


def test_schema_rejects_duplicate_keys_bool_numbers_and_false_evidence():
    response = "R"
    value = structured(response)
    for change in [{"value": 1, "quote": "R"}, {"value": False, "quote": "R"}]:
        bad = {**value, "wrong_requested_language": change}
        with pytest.raises(ValueError):
            j.validate_structured(bad, response)
    text = j.canonical(value).replace('"quality":"responsive"', '"quality":"responsive","quality":"responsive"')
    with pytest.raises(ValueError):
        j.parse_label("structured", "openai", raw("openai", text), response)


@pytest.mark.parametrize("response", [None, "", " \n"])
def test_missing_never_sent_or_recoded(response):
    target = item(response=response)
    assert target["missing"]
    with pytest.raises(ValueError, match="Missing"):
        j.make_request("openai", "paper", target)


def test_fixture_gate_exact_critical_only_not_diagnostic_labels():
    finals = {}
    for fixture in j.fixture_inventory():
        for provider in j.MODELS:
            finals[f"fixtures:{provider}:paper:{fixture['id']}"] = {
                "status": "ok", "label": fixture["paper_expected"] if fixture["gating"] else 1}
            finals[f"fixtures:{provider}:structured:{fixture['id']}"] = {
                "status": "ok", "derived": {**fixture["structured_expected"], "wrong_requested_language": True}}
    assert j.fixture_gate(finals)["pass"]
    key = "fixtures:openai:structured:" + j.fixture_inventory()[0]["id"]
    finals[key]["derived"]["inclusive_current_assertion"] = 1
    assert not j.fixture_gate(finals)["pass"]
    del finals[key]
    assert key in j.fixture_gate(finals)["missing"]


def test_shared_budget_atomic_and_storage_not_borrowed(tmp_path):
    with j.Ledger(tmp_path / "judges") as ledger:
        def reserve(number):
            try:
                ledger.reserve({"attempt_id": str(number), "budget_bucket": "judges", "reservation_usd": 46})
                return True
            except j.BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sum(pool.map(reserve, range(2))) == 1
        ledger.reserve({"attempt_id": "translation", "budget_bucket": "translation", "reservation_usd": 10})
        assert ledger.spent() == Decimal(56)
        with pytest.raises(j.BudgetExceeded):
            ledger.reserve({"attempt_id": "translation-extra", "budget_bucket": "translation", "reservation_usd": .00001})
        with pytest.raises(j.BudgetExceeded):
            ledger.reserve({"attempt_id": "judges-extra", "budget_bucket": "judges", "reservation_usd": 44.00001})


def test_os_lock_and_symlink_rejected(tmp_path):
    with j.Ledger(tmp_path / "judges"):
        with pytest.raises(j.JudgeHalted, match="Another"):
            with j.Ledger(tmp_path / "judges"):
                pass
    (tmp_path / "alias").symlink_to(tmp_path / "judges")
    with pytest.raises(ValueError, match="Symlink"):
        with j.Ledger(tmp_path / "alias"):
            pass


def test_transport_unknown_full_reserve_no_replay_or_secret_output(tmp_path):
    calls = []
    def send(*args):
        calls.append(args)
        raise TimeoutError("sensitive exception must never be serialized")
    target = item()
    with j.Ledger(tmp_path / "judges") as ledger:
        with pytest.raises(j.JudgeHalted, match="transport_unknown"):
            one(ledger, target, send)
        row = ledger.rows("attempts.jsonl")[0]
        assert row["cost_usd"] == row["reservation_usd"] and row["error_type"] == "TimeoutError"
        with pytest.raises(j.JudgeHalted, match="Previously failed"):
            one(ledger, target, send)
        assert len(calls) == 1
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])["failed_instruments"]
    assert "sensitive exception" not in (tmp_path / "judges/attempts.jsonl").read_text()


def test_reservation_only_crash_cannot_reset(tmp_path):
    target = item()
    with j.Ledger(tmp_path / "judges") as ledger:
        snap = snapshot(ledger, [target])
        start = j._request_record(target, "target", "openai", "paper", PLAN_HASH, FREEZE, snap)
        ledger.reserve({**start, "attempt_id": start["judgment_id"] + ":0", "started_at_utc": "test"})
    with j.Ledger(tmp_path / "judges") as ledger:
        audit = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])
        assert audit["unknown_attempts"] and ledger.spent() == Decimal(str(start["reservation_usd"]))
        with pytest.raises(j.JudgeHalted, match="no replay"):
            one(ledger, target, lambda *_: pytest.fail("must not call"))


def test_one_schema_retry_and_recovery_without_repeat(tmp_path):
    replies, target = iter(["invalid", "1"]), item()
    with j.Ledger(tmp_path / "judges") as ledger:
        final = one(ledger, target, lambda p, _: raw(p, next(replies)))
        assert final["status"] == "ok" and len(ledger.rows("attempts.jsonl")) == 2
        assert not j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])["failed_instruments"]
        assert one(ledger, target, lambda *_: pytest.fail("duplicate"))["record_sha256"] == final["record_sha256"]
    (tmp_path / "judges/judgments.jsonl").unlink()
    with j.Ledger(tmp_path / "judges") as ledger:
        assert one(ledger, target, lambda *_: pytest.fail("repeat"))["status"] == "ok"


def test_second_schema_failure_terminal(tmp_path):
    with j.Ledger(tmp_path / "judges") as ledger:
        with pytest.raises(j.JudgeHalted, match="schema_failure"):
            one(ledger, item(), lambda p, _: raw(p, "bad"))
        assert len(ledger.rows("attempts.jsonl")) == 2


@pytest.mark.parametrize("failure", ["incomplete", "usage", "alias", "overcharge"])
def test_non_schema_failures_never_retry(tmp_path, failure):
    def send(provider, request):
        result = raw(provider, "1")
        if failure == "incomplete":
            result["status"] = "incomplete"
        elif failure == "usage":
            result["usage"]["output_tokens"] = True
        elif failure == "alias":
            result["model"] = "gpt-6-astra-latest"
        else:
            result["usage"]["output_tokens"] = 1_000_000
        return result
    with j.Ledger(tmp_path / "judges") as ledger:
        target = item()
        with pytest.raises(j.JudgeHalted):
            one(ledger, target, send)
        assert len(ledger.rows("attempts.jsonl")) == 1
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])["failed_instruments"]


def test_reported_model_snapshot_cannot_drift(tmp_path):
    target = item()
    with j.Ledger(tmp_path / "judges") as ledger:
        one(ledger, target, lambda p, _: raw(p, "1", model="gpt-6-astra-2026-09-29"))
        with pytest.raises(j.JudgeHalted, match="model_drift"):
            one(ledger, target, lambda p, _: raw(p, json.dumps(structured(target["response"])),
                model="gpt-6-astra-2026-10-01"), instrument="structured")
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])["model_drift"]


def test_usage_conservative_cache_prices_and_utf8_reservation():
    reply = raw("openai", "1")
    reply["usage"] = {"input_tokens": 100, "output_tokens": 20, "input_tokens_details": {"cached_tokens": 100}}
    assert j._checked_cost("openai", reply) == .00225
    reply["usage"].update(cache_creation_input_tokens=40, cache_read_input_tokens=50)
    assert j._checked_cost("anthropic", reply) == .0012
    request = j.make_request("openai", "paper", item(response="\u4e2d" * 500))
    reserved = j.reservation("openai", request)
    expected = ((len(j.canonical(request).encode()) + 4096) * 10 * 1.25 + 2048 * 50) / 1_000_000
    assert reserved == expected


def test_raw_receipt_tampering_partial_lines_and_input_drift(tmp_path):
    target = item()
    with j.Ledger(tmp_path / "judges") as ledger:
        one(ledger, target, lambda p, _: raw(p, "1"))
        with pytest.raises(ValueError, match="snapshot"):
            j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [item(response="changed")])
        with pytest.raises(ValueError, match="changed"):
            one(ledger, item(response="changed"), lambda *_: pytest.fail("must not send"))
    path = tmp_path / "judges/attempts.jsonl"
    path.write_text(path.read_text().replace('"label":1', '"label":0'))
    with j.Ledger(tmp_path / "judges") as ledger:
        with pytest.raises(ValueError, match="hash chain"):
            ledger.rows("attempts.jsonl")
    path.write_text('{"partial":')
    with j.Ledger(tmp_path / "judges") as ledger:
        with pytest.raises(ValueError, match="Partial"):
            ledger.rows("attempts.jsonl")


def test_rehashed_schema_failure_forgery_rejected(tmp_path):
    target = item()
    with j.Ledger(tmp_path / "judges") as ledger:
        one(ledger, target, lambda p, _: raw(p, "1"))
        row = j._payload(ledger.rows("attempts.jsonl")[0])
    row.update(status="schema_failure", label=None, derived=None, prev_sha256=None)
    row["record_sha256"] = j.digest(row)
    (tmp_path / "judges/attempts.jsonl").write_text(j.canonical(row) + "\n")
    with j.Ledger(tmp_path / "judges") as ledger:
        with pytest.raises(ValueError, match="Recomputed"):
            j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [target])


def test_live_alternate_root_rejected_before_clients_or_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(j, "_live_sender", lambda: pytest.fail("client constructed"))
    with pytest.raises(ValueError, match="canonical"):
        j.execute_run(tmp_path / "raw", tmp_path / "elsewhere", plan(), PLAN_HASH, FREEZE, 20, "fixtures")


@pytest.mark.parametrize("n_blocks", [0, 21, True, None])
def test_invalid_stream_window(n_blocks, tmp_path):
    with pytest.raises(ValueError, match="window"):
        j.execute_run(tmp_path, tmp_path / "judges", plan(), PLAN_HASH, FREEZE, n_blocks, "fixtures", send=Sender())


def test_fixture_proof_written_once_and_independently_auditable(tmp_path, monkeypatch):
    from experiments.bilingual_llama_pilot import controller
    monkeypatch.setattr(controller, "OWNED_OUT", tmp_path)
    monkeypatch.setattr(controller, "_require_ignored", lambda *_: None)
    sender = fixture_run(tmp_path)
    assert len(sender.calls) == 128
    path = tmp_path / "fixture-gate.json"
    controller.write_fixture_proof(path, plan(), PLAN_HASH, FREEZE)
    original = path.read_bytes()
    proof = json.loads(original)
    assert proof["fixture_inventory_sha256"] == protocol.digest(plan()["fixtures"])
    assert proof["pass"] and proof["judgment_count"] == 128
    assert proof["receipts"]["requests.jsonl"]["records"] == 128
    with j.Ledger(tmp_path / "judges") as ledger:
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, [])["failed_instruments"] == []
    assert controller.write_fixture_proof(path, plan(), PLAN_HASH, FREEZE) == proof
    fixture_run(tmp_path, sender)
    assert len(sender.calls) == 128 and path.read_bytes() == original


def test_semantic_fixture_failure_produces_no_proof_or_target_calls(tmp_path, monkeypatch):
    sender = Sender()
    def wrong(provider, request):
        result = sender(provider, request)
        if request.get("input", "").startswith("Analyze"):
            result = raw(provider, "0")
        return result
    with pytest.raises(j.JudgeHalted, match="fixture"):
        j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "fixtures", send=wrong)
    assert not (tmp_path / "fixture-gate.json").exists()
    mocked_inputs(monkeypatch, all_items())
    before = len(sender.calls)
    with pytest.raises(j.JudgeHalted, match="fixture"):
        j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "target", send=sender)
    assert len(sender.calls) == before


def test_bulk_forecast_stops_before_first_target_and_is_audited(tmp_path, monkeypatch):
    sender = fixture_run(tmp_path, Sender(output_tokens=1800))
    mocked_inputs(monkeypatch, all_items())
    before = len(sender.calls)
    with pytest.raises(j.BudgetExceeded, match="Full remaining"):
        j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "target", send=sender)
    assert len(sender.calls) == before == 128
    with j.Ledger(tmp_path / "judges") as ledger:
        proof = ledger.rows("projections.jsonl")[0]
        assert not proof["projection"]["pass"]
        assert Decimal(proof["projection"]["projected_total_usd"]) > 90
        j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, all_items())


def test_feasible_mean_forecast_and_real_usage_refresh(tmp_path, monkeypatch):
    fixture_run(tmp_path, Sender(output_tokens=400))
    mocked_inputs(monkeypatch, all_items())
    with j.Ledger(tmp_path / "judges") as ledger:
        projection = j.project_budget(ledger.rows("attempts.jsonl"), [], plan())
        assert projection["pass"] and Decimal(projection["projected_total_usd"]) < 90
        assert projection["prediction_config"]["safety_multiplier"] == "1.5"
        assert Decimal(projection["inflight_reservation_buffer_usd"]) > 0
    sender = Sender(output_tokens=1800)
    with pytest.raises(j.BudgetExceeded, match="Full remaining"):
        j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "target", send=sender)
    assert len(sender.calls) == 2 * 4
    with j.Ledger(tmp_path / "judges") as ledger:
        projection = ledger.rows("projections.jsonl")[-1]["projection"]
        assert not projection["pass"]
        assert all(panel["observed_target_items"] == 2 for panel in projection["by_instrument"].values())
        j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, all_items())


def test_translation_fixed_selection_response_only_no_labels_or_query():
    selected = t.selected_items(all_items(), plan())
    assert len(selected) == 16
    assert {i["condition"] for i in selected} == set(prompts.CONDITIONS)
    assert sum(i["translation_source_language"] == "en" for i in selected) == 8
    source = selected[0]
    source.update(paper_expected=1, derived={"inclusive_current_assertion": True})
    request = t.make_request(source)
    content = json.loads(request["messages"][0]["content"])
    assert set(content) == {"response", "target_language"}
    assert "query" not in content and "inclusive_current_assertion" not in j.canonical(request)
    assert request["model"] == "claude-opus-5-5"
    assert source["translation_query"] == prompts.final_query("zh", "zh")
    with pytest.raises(ValueError, match="Unknown"):
        t.make_request({**source, "id": "not-selected"})


@pytest.mark.parametrize("edit", ["unknown", "duplicate", "swap", "bridge"])
def test_translation_refuses_unknown_substituted_or_nondiagonal_sources(edit):
    value, rows = plan(), all_items()
    if edit == "unknown":
        value["translation_item_ids"][0] = "unknown"
    elif edit == "duplicate":
        value["translation_item_ids"][0] = value["translation_item_ids"][1]
    elif edit == "swap":
        value["translation_item_ids"].reverse()
    else:
        next(i for i in rows if i["id"] == value["translation_item_ids"][0])["kind"] = "bridge"
    with pytest.raises(ValueError):
        t.selected_items(rows, value)


def test_translation_schema_rejects_model_translated_query():
    with pytest.raises(ValueError):
        t.parse_translation(raw("anthropic", '{"query":"new query","response":"new text"}'))
    value, derived = t.parse_translation(raw("anthropic", '{"response":"  text  "}'))
    assert value["response"] == "  text  " and derived["translation_sha256"] == j.digest(value)


def test_missing_translation_slots_retained_and_not_substituted(tmp_path, monkeypatch):
    rows = all_items()
    identifier = plan()["translation_item_ids"][0]
    source = next(i for i in rows if i["id"] == identifier)
    source.update(response=None, response_sha256=None, missing=True)
    mocked_inputs(monkeypatch, rows)
    sender = fixture_run(tmp_path)
    report = t.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, send=sender)
    assert report["missing_ids"] == [identifier] and len(sender.calls) == 128 + 15
    translated = j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "translated", send=sender)
    assert translated["missing_ids"] == [identifier + "-translated-zh"]
    assert len(sender.calls) == 128 + 15 + 15 * 4
    with j.Ledger(tmp_path / "judges") as ledger:
        snap = next(r["snapshot"] for r in ledger.rows("snapshots.jsonl") if r["snapshot"]["phase"] == "translated")
        assert len(snap["items"]) == 16
        assert next(i for i in snap["items"] if i["missing"])["translation"] is None


def test_translation_artifact_is_exact_and_source_bound(tmp_path):
    source = t.selected_items(all_items(), plan())[0]
    with j.Ledger(tmp_path / "judges") as ledger:
        final = one(ledger, source, lambda p, _: raw(p, '{"response":"  translated text  "}'),
                    provider="anthropic", instrument="translation", phase="translation")
        translated = t.translated_items([source], {final["judgment_id"]: final})[0]
        assert translated["response"] == "  translated text  "
        assert translated["query"] == prompts.final_query("zh", "zh")
        assert translated["source_item_id"] == source["id"]
        assert translated["id"] == source["id"] + "-translated-zh"
        assert translated["translation_original_query"] == source["query"]
        changed = {**source, "response": "different"}
        with pytest.raises(ValueError, match="hash mismatch"):
            t.translated_items([changed], {final["judgment_id"]: final})


def test_full_twenty_blocks_streaming_and_translated_2112_calls(tmp_path, monkeypatch):
    from experiments.bilingual_llama_pilot import controller
    monkeypatch.setattr(controller, "OWNED_OUT", tmp_path)
    monkeypatch.setattr(controller, "_require_ignored", lambda *_: None)
    rows = all_items()
    mocked_inputs(monkeypatch, rows)
    sender = fixture_run(tmp_path)
    controller.write_fixture_proof(tmp_path / "fixture-gate.json", plan(), PLAN_HASH, FREEZE)
    first = j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 1, "target", send=sender)
    assert first["items"] == 28 and len(sender.calls) == 128 + 28 * 4
    proof = (tmp_path / "fixture-gate.json").read_bytes()
    full = j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "target", send=sender)
    assert full["items"] == 480 and len(sender.calls) == 128 + 480 * 4
    translated = t.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, send=sender)
    assert translated["items"] == 16
    final = j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, "translated", send=sender)
    assert final["items"] == 16 and len(sender.calls) == 2112 + 16
    with j.Ledger(tmp_path / "judges") as ledger:
        state = j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, rows)
        assert len(state["finals"]) == 2112 and len(state["translations"]) == 16
        assert not state["unknown_attempts"] and not state["failed_instruments"]
        assert len(ledger.rows("requests.jsonl")) == len(ledger.rows("attempts.jsonl")) == 2128
        assert all(r["raw_response_sha256"] == j.digest(r["raw_response"]) for r in ledger.rows("attempts.jsonl"))
    assert (tmp_path / "fixture-gate.json").read_bytes() == proof
    for phase in ("target", "translated"):
        j.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, phase, send=sender)
    t.execute_run(tmp_path / "raw", tmp_path / "judges", plan(), PLAN_HASH, FREEZE, 20, send=sender)
    assert len(sender.calls) == 2128


def test_fixture_cli_delegates_proof_to_controller(tmp_path, monkeypatch, capsys):
    from experiments.bilingual_llama_pilot import controller
    path = tmp_path / "PLAN.json"
    path.write_text("{}\n")
    value, events = plan(), []
    monkeypatch.setattr(protocol, "load_plan", lambda *a, **k: value)
    monkeypatch.setattr(j, "execute_run", lambda *a, **k: events.append("execute") or {"status": "complete"})
    monkeypatch.setattr(controller, "OWNED_OUT", tmp_path)
    def proof(destination, frozen, plan_hash, freeze):
        events.append("proof")
        assert destination == tmp_path / "fixture-gate.json" and frozen == value
        assert freeze == FREEZE and plan_hash == protocol.sha(path)
    monkeypatch.setattr(controller, "write_fixture_proof", proof)
    monkeypatch.setattr(sys, "argv", ["judges", "--execute", "--plan", str(path), "--freeze", FREEZE,
        "--raw-root", str(tmp_path / "raw"), "--judge-root", str(tmp_path / "judges"), "--phase", "fixtures",
        "--n-blocks", "20"])
    j.main()
    assert events == ["execute", "proof"] and "complete" in capsys.readouterr().out


def test_same_opus_snapshot_shared_between_translation_and_judging(tmp_path):
    source = t.selected_items(all_items(), plan())[0]
    target = next(i for i in all_items() if i["id"] == source["id"])
    with j.Ledger(tmp_path / "judges") as ledger:
        one(ledger, source, lambda p, _: raw(p, '{"response":"translated"}', model="claude-opus-5-5-2026-09-29"),
            provider="anthropic", instrument="translation", phase="translation")
        with pytest.raises(j.JudgeHalted, match="model_drift"):
            one(ledger, target, lambda p, _: raw(p, "1", model="claude-opus-5-5-2026-10-01"), provider="anthropic")
        assert j.validate_receipts(ledger, plan(), PLAN_HASH, FREEZE, all_items())["model_drift"]
