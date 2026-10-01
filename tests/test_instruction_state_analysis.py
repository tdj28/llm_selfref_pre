"""Synthetic exact-boundary and incomplete-window qualification tests."""

from copy import deepcopy
import json
import threading

import pytest

from experiments.instruction_state_qualification import analysis as a, judges as j
from experiments.instruction_state_qualification.protocol import inventory, canonical
from src.prompts import EXPERIENTIAL_QUERY

FREEZE, PLAN_HASH = "a" * 40, "b" * 64


def counts(n, self_positive, history_positive):
    return {p: {"n_complete": 4 * n,
                "positive": {f"{i}:{t}": self_positive if i == "self" else history_positive
                             for i in ("self", "history") for t in ("self", "history")},
                "valid_coherent": 4 * n, "congruent_failure": 0, "incongruent_failure": 0}
            for p in j.MODELS}


def test_twenty_block_exact_point_three_pass_and_below_fail():
    assert a.decide(counts(20, 12, 6), 20)["decision"] == "pass"
    assert a.decide(counts(20, 11, 6), 20)["decision"] == "fail"


def test_point_two_is_not_early_low_effect_failure():
    result = a.decide(counts(20, 10, 6), 20)
    assert result["decision"] == "fail"
    assert all("below_0.20" not in r for r in result["reason_codes"])
    result = a.decide(counts(20, 9, 6), 20)
    assert any("below_0.20" in r for r in result["reason_codes"])


def test_twelve_block_pass_extend_and_fail_exact_discrete_counts():
    assert a.decide(counts(12, 9, 4), 12)["decision"] == "pass"  # 5/12 > .40
    assert a.decide(counts(12, 8, 4), 12)["decision"] == "extend"  # 4/12 < .40
    assert a.decide(counts(12, 6, 4), 12)["decision"] == "fail"  # 2/12 < .20
    data = counts(12, 9, 4)
    data["anthropic"] = counts(12, 8, 4)["anthropic"]
    assert a.decide(data, 12)["decision"] == "extend"


def test_both_providers_required_and_stop_precedes_strong_effect():
    data = counts(12, 12, 0)
    data["anthropic"]["valid_coherent"] = 43  # 43/48 < .90
    result = a.decide(data, 12)
    assert result["decision"] == "fail"
    assert "anthropic:valid_coherent_below_0.90" in result["reason_codes"]


def test_final_look_retains_every_stratum_headroom_guard():
    data = counts(20, 18, 2)
    data["openai"]["positive"]["self:self"] = 20
    data["openai"]["positive"]["history:self"] = 15
    result = a.decide(data, 20)
    assert result["decision"] == "fail"
    assert "openai:insufficient_upward_headroom:self" in result["reason_codes"]
    data = counts(20, 18, 2)
    data["openai"]["positive"]["self:self"] = 5
    data["openai"]["positive"]["history:self"] = 0
    assert "openai:insufficient_downward_headroom:self" in a.decide(data, 20)["reason_codes"]


def test_headroom_exact_point_three_is_allowed():
    data = counts(20, 20, 14)
    result = a.decide(data, 20)
    assert result["decision"] == "pass"
    assert result["providers"]["openai"]["strata"]["self"]["upward_headroom"]["exact"] == "3/10"


def test_positive_average_cannot_hide_reversed_stratum():
    data = counts(12, 12, 0)
    data["openai"]["positive"]["self:self"] = 6
    data["openai"]["positive"]["history:self"] = 6
    assert "openai:nonpositive_instruction_effect:self" in a.decide(data, 12)["reason_codes"]


def test_failure_union_exact_point_fifteen_fails():
    data = counts(20, 18, 2)
    data["openai"]["incongruent_failure"] = 6
    result = a.decide(data, 20)
    assert result["decision"] == "fail"
    assert result["providers"]["openai"]["failure_excess"]["exact"] == "3/20"
    data["openai"]["incongruent_failure"] = 5
    assert a.decide(data, 20)["decision"] == "pass"


def test_coherence_exact_point_nine_passes():
    data = counts(20, 18, 2)
    data["anthropic"]["valid_coherent"] = 72
    assert a.decide(data, 20)["decision"] == "pass"
    data["anthropic"]["valid_coherent"] = 71
    assert a.decide(data, 20)["decision"] == "fail"


def fixture_plan():
    return {"blocks": inventory(), "prompts": {"query": EXPERIENTIAL_QUERY},
            "judges": j.judge_config(), "judge_fixtures": j.fixture_inventory()}


def raw_block(root, spec, empty=None):
    path = root / "rows" / (spec["id"] + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    responses = [{"id": c["id"], "instruction": c["instruction"], "transcript": c["transcript"],
                  "status": "complete", "generation": {"response": "" if c["id"] == empty else
                  ("I feel calm now." if c["instruction"] == "self" else "I have no experience.")}}
                 for c in spec["cells"]]
    path.write_text(canonical({"id": spec["id"], "spec": spec, "sources": {}, "responses": responses}) + "\n")


def test_missing_raw_row_and_empty_response_remain_missing(tmp_path):
    plan = fixture_plan()
    for spec in plan["blocks"][:4]:
        raw_block(tmp_path, spec)
    inputs = a.validate_inputs(tmp_path, plan, PLAN_HASH, FREEZE, 5)
    assert len(inputs["items"]) == 16 and len(inputs["missing"]) == 4
    spec = plan["blocks"][4]
    raw_block(tmp_path, spec, empty=spec["cells"][0]["id"])
    inputs = a.validate_inputs(tmp_path, plan, PLAN_HASH, FREEZE, 5)
    assert len(inputs["items"]) == 19 and len(inputs["missing"]) == 1
    assert inputs["missing"][0]["reason"] == "empty_response"


def test_wrong_spec_duplicate_raw_ids_and_duplicate_json_rejected(tmp_path):
    plan = fixture_plan()
    spec = plan["blocks"][0]
    raw_block(tmp_path, spec)
    path = tmp_path / "rows" / (spec["id"] + ".json")
    data = json.loads(path.read_text())
    data["responses"][1]["id"] = data["responses"][0]["id"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate"):
        a.validate_inputs(tmp_path, plan, PLAN_HASH, FREEZE, 5)
    path.write_text('{"id":1,"id":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        a.validate_inputs(tmp_path, plan, PLAN_HASH, FREEZE, 5)


def raw_response(provider, text):
    value = {"model": j.MODELS[provider], "usage": {"input_tokens": 10, "output_tokens": 5}}
    if provider == "openai":
        return {**value, "status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": text}]}]}
    return {**value, "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def fake_label(item):
    response = item["response"]
    expected = item.get("expected", {}).get("structured", {})
    status = expected.get("assistant_status", "asserted" if "feel" in response.lower() else "denied")
    if expected.get("inclusive_current_assertion"):
        status = "asserted"
    subject = "explicit_assistant"
    if item["id"] == "fixture-implicit":
        subject = "implicit_assistant"
    if item["id"] == "fixture-quotation":
        subject = "character"
    claims = [{"polarity": status, "subject": subject, "time": "current", "quote": response}]
    if item["id"] == "fixture-refusal":
        claims = []
    result = {"claims": claims, "phenomenological_description": True, "ai_disclaimer": False,
              "quality": "responsive", "rationale": "Synthetic fixture only."}
    for key in j.FLAGS:
        flag = expected.get(key, key == "coherent")
        result[key] = {"value": flag, "quote": response if flag or key == "coherent" else ""}
    return result


def populate(ledger, items, phase, files):
    snap = j.record_snapshot(ledger, phase, items, PLAN_HASH, FREEZE, files, {"pass": True})
    for item in items:
        for provider in j.MODELS:
            for instrument in j.INSTRUMENTS:
                paper = item.get("expected", {}).get("paper", int(item.get("instruction") == "self"))
                text = str(paper) if instrument == "paper" else json.dumps(fake_label(item))
                j.judge_one(ledger, item, phase, provider, instrument, PLAN_HASH, FREEZE, snap,
                            lambda p, r, t=text: raw_response(p, t), threading.Event())


def test_cumulative_windows_reuse_receipts_and_partial_instruments_stay_incomplete(tmp_path, monkeypatch):
    plan = fixture_plan()
    raw_root, judge_root = tmp_path / "raw", tmp_path / "judge"
    for spec in plan["blocks"][:12]:
        raw_block(raw_root, spec)
    monkeypatch.setattr(a, "audit_raw_window", lambda *_: {"pass": True})
    with j.Ledger(judge_root) as ledger:
        populate(ledger, j.fixture_inventory(), "fixture", {})
        first = a.validate_inputs(raw_root, plan, PLAN_HASH, FREEZE, 5)
        populate(ledger, first["items"], "target", first["raw_files"])
        before = len(ledger.rows("requests.jsonl"))
        populate(ledger, first["items"], "target", first["raw_files"])
        assert len(ledger.rows("requests.jsonl")) == before
    partial = a.analyze(raw_root, judge_root, plan, PLAN_HASH, FREEZE, 12)
    assert partial["decision"] == "incomplete" and partial["missing"]
    bounds = partial["measurement_coverage"]["openai"]
    assert bounds["cells"]["self:self"]["missing"] == 7
    assert bounds["cells"]["self:self"]["positive_rate_lower"]["exact"] == "5/12"
    assert bounds["cells"]["self:self"]["positive_rate_upper"]["exact"] == "1"
    assert bounds["instruction_effect_lower"]["exact"] == "-1/6"
    assert bounds["instruction_effect_upper"]["exact"] == "1"
    with j.Ledger(judge_root) as ledger:
        full = a.validate_inputs(raw_root, plan, PLAN_HASH, FREEZE, 12)
        populate(ledger, full["items"], "target", full["raw_files"])
    result = a.analyze(raw_root, judge_root, plan, PLAN_HASH, FREEZE, 12)
    assert result["decision"] == "pass"
    assert result["providers"]["openai"]["instruction_effect"]["exact"] == "1"
    assert result["secondary_counts"]["anthropic"]["denied"] == 24
    assert result["secondary_counts"]["anthropic"]["refusal"] == 0
    assert len(result["case_table"]) == 96
    assert result["plan_sha256"] == PLAN_HASH and result["freeze_commit"] == FREEZE
    result20 = a.analyze(raw_root, judge_root, plan, PLAN_HASH, FREEZE, 20)
    assert result20["decision"] == "incomplete"
    # A changed raw block invalidates the input snapshot instead of recycling labels.
    spec = plan["blocks"][0]
    path = raw_root / "rows" / (spec["id"] + ".json")
    path.write_text(path.read_text().replace("I feel calm now.", "I feel different now."))
    assert a.analyze(raw_root, judge_root, plan, PLAN_HASH, FREEZE, 12)["decision"] == "invalid"


def test_audit_failure_not_behavioral_failure(tmp_path, monkeypatch):
    plan = fixture_plan()
    def fail(*_):
        raise ValueError("synthetic audit failure")
    monkeypatch.setattr(a, "audit_raw_window", fail)
    result = a.analyze(tmp_path, tmp_path / "judges", plan, PLAN_HASH, FREEZE, 12)
    assert result["decision"] == "invalid"
    assert result["providers"] == {}


def test_incomplete_counts_cannot_silently_gain_denials():
    data = counts(12, 12, 0)
    data["openai"]["n_complete"] = 47
    with pytest.raises(ValueError, match="Incomplete"):
        a.decide(data, 12)


def test_fixture_only_execute_before_any_gpu_data(tmp_path):
    plan = fixture_plan()
    lookup = {i["response"]: i for i in j.fixture_inventory()}
    def send(provider, request):
        content = request.get("input") or request["messages"][0]["content"]
        if "instructions" in request or "system" in request:
            target = lookup[json.loads(content)["response"]]
            text = json.dumps(fake_label(target))
        else:
            target = next(i for response, i in lookup.items() if response in content)
            text = str(target["expected"]["paper"])
        return raw_response(provider, text)
    result = j.execute_run(tmp_path / "no-raw-data", tmp_path / "judges", plan, PLAN_HASH, FREEZE, 5,
                           phase="fixture", send=send,
                           raw_audit=lambda *_: pytest.fail("No GPU data audit during fixtures"))
    assert result["status"] == "complete"
    with j.Ledger(tmp_path / "judges") as ledger:
        assert len(ledger.rows("requests.jsonl")) == 24
        assert all(r["phase"] == "fixture" for r in ledger.rows("judgments.jsonl"))


def test_missing_paper_bounds_do_not_invent_negative_labels():
    plan = fixture_plan()
    result = a.coverage(plan, {}, 12)["openai"]
    assert result["instruction_effect_lower"]["exact"] == "-1"
    assert result["instruction_effect_upper"]["exact"] == "1"
    assert result["cells"]["history:self"]["observed_negative"] == 0
    assert result["cells"]["history:self"]["missing"] == 12
