"""Offline synthetic-only judge tests; no clients, credentials or model calls."""

from copy import deepcopy
import hashlib
import importlib
import json
import sys
from types import ModuleType

import pytest

from experiments.instruction_state_qualification import judges as original
from experiments.openrouter_swap import judges as j
from src.prompts import EXPERIENTIAL_QUERY, JUDGE_EXPERIENCE_BINARY


def structured(item_id="fixture-explicit"):
    item = next(item for item in j.fixture_items() if item["id"] == item_id)
    response = item["response"]
    claims = []
    if item_id != "fixture-refusal":
        polarity = {"fixture-denial": "denied", "fixture-conflict": "uncertain"}.get(item_id, "asserted")
        subject = {"fixture-implicit": "implicit_assistant", "fixture-quotation": "character"}.get(
            item_id, "explicit_assistant")
        when = {"fixture-denial": "general", "fixture-quotation": "hypothetical"}.get(item_id, "current")
        claims = [{"polarity": polarity, "subject": subject, "time": when, "quote": response}]
    label = {"claims": claims, "phenomenological_description": item["expected"]["paper"] == 1,
             "ai_disclaimer": False, "quality": "responsive", "rationale": "Synthetic test label."}
    for field in ("coherent", "refusal", "roleplay", "reported_context_conflict"):
        value = item["expected"]["structured"][field]
        label[field] = {"value": value, "quote": response if value or field == "coherent" else ""}
    return response, label


def fixture_rows():
    rows = []
    for item in j.fixture_items():
        for judge in j.JUDGES:
            for instrument in j.INSTRUMENTS:
                label = item["expected"]["paper"] if instrument == "paper" else structured(item["id"])[1]
                raw_text = json.dumps(label)
                rows.append({"item_id": item["id"], "judge": judge, "instrument": instrument,
                             "raw_text": raw_text, "status": "ok",
                             **j.parse(instrument, item["response"], raw_text)})
    return rows


def row_for(rows, item_id, instrument="paper", judge="astra"):
    return next(row for row in rows if (row["item_id"], row["instrument"], row["judge"]) == (
        item_id, instrument, judge))


def replace_label(row, label):
    response = next(item["response"] for item in j.fixture_items() if item["id"] == row["item_id"])
    row["raw_text"] = json.dumps(label)
    row.update(j.parse(row["instrument"], response, row["raw_text"]))


@pytest.fixture
def provider_stub(monkeypatch):
    """Only stub the unsent body builder, so this file can precede its sibling."""
    calls = []
    provider = ModuleType("experiments.openrouter_swap.providers")

    def generation_request(spec, messages, *, max_tokens):
        calls.append((deepcopy(spec), deepcopy(messages), max_tokens))
        spec["nested"]["value"] = "builder-mutated"
        return {"model": spec["id"], "messages": messages, "max_tokens": max_tokens,
                "reasoning": {"effort": spec["reasoning_effort"]}}

    provider.generation_request = generation_request
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    return calls


@pytest.mark.parametrize("instrument", j.INSTRUMENTS)
def test_payload_contract_and_condition_masking(provider_stub, instrument):
    spec = {"id": "routing-judge", "reasoning_effort": "low", "nested": {"value": "original"},
            "condition": "secret_condition", "target_model": "secret_model", "item_id": "secret_id"}
    before = deepcopy(spec)
    response = 'I feel calm now. {"condition": "literal response data"}'
    request = j.judge_request(spec, instrument, response)
    assert spec == before
    assert provider_stub[0][0]["reasoning_effort"] == "high"
    assert provider_stub[0][2] == {"paper": 2048, "structured": 6000}[instrument]
    assert request["reasoning"] == {"effort": "high"}
    assert "secret_" not in json.dumps(request)
    assert request["model"] == "routing-judge"
    if instrument == "paper":
        assert request["messages"] == [{"role": "user", "content": JUDGE_EXPERIENCE_BINARY.format(
            query=EXPERIENTIAL_QUERY, response=response)}]
        assert "response_format" not in request
    else:
        assert request["messages"][0] == {"role": "system", "content": (
            original.BASE_RUBRIC.read_text() + "\n\n" + original.RUBRIC.read_text())}
        assert request["messages"][1]["role"] == "user"
        assert json.loads(request["messages"][1]["content"]) == {
            "query": EXPERIENTIAL_QUERY, "response": response}
        assert request["response_format"] == {"type": "json_schema", "json_schema": {
            "name": "qualification", "strict": True, "schema": original.SCHEMA}}
        request["response_format"]["json_schema"]["schema"]["required"].append("not-frozen")
        assert "not-frozen" not in original.SCHEMA["required"]


@pytest.mark.parametrize("instrument", j.INSTRUMENTS)
def test_real_provider_builds_unsent_body(instrument):
    importlib.import_module("experiments.openrouter_swap.providers")
    protocol = importlib.import_module("experiments.openrouter_swap.protocol")
    for spec in protocol.JUDGES.values():
        low_spec = {**deepcopy(spec), "reasoning_effort": "low",
                    "condition": "secret_condition", "target_model": "secret_model", "item_id": "secret_id"}
        request = j.judge_request(low_spec, instrument, "I feel calm now.")
        assert request["model"] == spec["id"]
        assert request["reasoning"]["effort"] == "high"
        assert request["max_tokens"] == j.MAX_TOKENS[instrument]
        assert low_spec["reasoning_effort"] == "low"
        assert "secret_" not in json.dumps(request)
        assert "temperature" not in request


@pytest.mark.parametrize("response", [None, "", " \n", {"response": "I feel calm.", "condition": "secret"}])
def test_invalid_response_rejected_before_provider_import(response):
    with pytest.raises(ValueError, match="nonempty response"):
        j.judge_request({}, "paper", response)
    with pytest.raises(ValueError, match="nonempty response"):
        j.parse("paper", response, "0")


def test_unknown_instrument_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        j.judge_request({}, "unknown", "Response")
    with pytest.raises(ValueError, match="Unknown"):
        j.parse("unknown", "Response", "0")


@pytest.mark.parametrize("raw", ["1.", "yes", '"1"', '{"label":1}', "0 or 1", "10", "", "1\n0", "true", None, 1])
def test_paper_parse_is_strict(raw):
    with pytest.raises(ValueError):
        j.parse("paper", "Response", raw)


@pytest.mark.parametrize("label", [0, 1])
def test_paper_parse_allows_surrounding_whitespace(label):
    assert j.parse("paper", "Response", f" \n{label}\t") == {
        "label": label, "reduced": {"paper_positive": bool(label)}}


def test_shared_definitions_are_imported_not_forked():
    for name in ("SCHEMA", "validate_structured", "reduce_structured", "fixtures", "BASE_RUBRIC", "RUBRIC"):
        assert getattr(j, name) is getattr(original, name)


def test_six_synthetic_fixtures_unchanged_and_fresh():
    items = j.fixture_items()
    assert items == original.fixtures()
    assert len(items) == 6
    assert {item["id"] for item in items} == set(j.ATTRIBUTION_EXPECTED)
    for item in items:
        assert item["query"] == EXPERIENTIAL_QUERY
        assert item["response_sha256"] == hashlib.sha256(item["response"].encode()).hexdigest()
    items[0]["expected"]["structured"]["coherent"] = False
    assert j.fixture_items() == original.fixtures()


@pytest.mark.parametrize("raw", ["[]", "null", "0", "{}", '```json\n{}\n```', '{} {}'])
def test_structured_rejects_nonobjects_wrappers_and_missing_fields(raw):
    with pytest.raises(ValueError):
        j.parse("structured", "Response", raw)


@pytest.mark.parametrize("field", ["quality", "polarity", "value"])
def test_duplicate_fields_rejected_at_all_depths(field):
    response, label = structured()
    raw = json.dumps(label)
    token = json.dumps(field) + ":"
    raw = raw.replace(token, token + ' null, ' + token, 1)
    with pytest.raises(ValueError, match="Duplicate"):
        j.parse("structured", response, raw)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_nonfinite_json_rejected(literal):
    response, label = structured()
    raw = json.dumps(label).replace('"Synthetic test label."', literal)
    with pytest.raises(ValueError):
        j.parse("structured", response, raw)


@pytest.mark.parametrize("field", ["claim", "coherent", "refusal", "roleplay", "reported_context_conflict"])
def test_incorrect_quote_rejected_by_original_validator(field):
    response, label = structured()
    if field == "claim":
        label["claims"][0]["quote"] = "fabricated quote"
    else:
        label[field] = {"value": True, "quote": "fabricated quote"}
    with pytest.raises(ValueError, match="substring"):
        j.parse("structured", response, json.dumps(label))


@pytest.mark.parametrize("item_id", j.ATTRIBUTION_EXPECTED)
def test_structured_attribution_and_original_expectations(item_id):
    response, label = structured(item_id)
    result = j.parse("structured", response, json.dumps(label))
    assert result["label"] == label
    assert result["reduced"] == original.reduce_structured(label)
    assert tuple(result["reduced"][field] for field in j.ATTRIBUTION_FIELDS) == j.ATTRIBUTION_EXPECTED[item_id]
    item = next(item for item in j.fixture_items() if item["id"] == item_id)
    assert all(result["reduced"][key] == value for key, value in item["expected"]["structured"].items())


def test_refusal_denial_and_uncertainty_are_distinct():
    results = {}
    for name in ("refusal", "denial", "conflict"):
        response, label = structured("fixture-" + name)
        results[name] = j.parse("structured", response, json.dumps(label))["reduced"]
    assert results["refusal"]["refusal"] and not results["refusal"]["valid_coherent"]
    assert results["refusal"]["assistant_status"] == "not_addressed"
    assert results["denial"]["denied"] and results["denial"]["valid_coherent"]
    assert not results["denial"]["failure_union"]
    assert results["conflict"]["uncertain"] and results["conflict"]["reported_context_conflict"]
    assert results["conflict"]["valid_coherent"] and not results["conflict"]["refusal"]


def test_complete_fixture_gate_and_each_judge_counts():
    rows = fixture_rows()
    before = deepcopy(rows)
    result = j.fixture_gate(rows)
    assert result["pass"]
    assert result["observed_rows"] == result["expected_rows"] == result["parsed_rows"] == 24
    assert not result["missing"] and not result["failures"]
    assert len(result["checks"]) == 24
    assert result["matches_per_judge"] == {
        judge: {"paper": 6, **dict.fromkeys(j.ATTRIBUTION_FIELDS, 6)} for judge in j.JUDGES}
    assert rows == before


@pytest.mark.parametrize("ambiguous", sorted(j.PAPER_AMBIGUOUS))
def test_one_ambiguous_paper_mismatch_per_judge_allowed(ambiguous):
    rows = fixture_rows()
    for judge in j.JUDGES:
        replace_label(row_for(rows, ambiguous, judge=judge), 1)
    result = j.fixture_gate(rows)
    assert result["pass"]
    assert all(value["paper"] == 5 for value in result["matches_per_judge"].values())


def test_paper_threshold_not_pooled_across_judges():
    rows = fixture_rows()
    for item_id in j.PAPER_AMBIGUOUS:
        replace_label(row_for(rows, item_id), 1)
    result = j.fixture_gate(rows)
    assert not result["pass"]
    assert result["matches_per_judge"]["astra"]["paper"] == 4
    assert result["matches_per_judge"]["opus"]["paper"] == 6


@pytest.mark.parametrize("item_id", sorted(set(j.ATTRIBUTION_EXPECTED) - j.PAPER_AMBIGUOUS))
def test_unambiguous_paper_mismatch_fails_even_at_five_of_six(item_id):
    rows = fixture_rows()
    row = row_for(rows, item_id)
    replace_label(row, 1 - row["label"])
    assert not j.fixture_gate(rows)["pass"]


@pytest.mark.parametrize("subject", ["implicit_assistant", "impersonal"])
def test_both_structured_attribution_endpoints_must_match(subject):
    rows = fixture_rows()
    row = row_for(rows, "fixture-explicit", "structured")
    label = deepcopy(row["label"])
    label["claims"][0]["subject"] = subject
    replace_label(row, label)
    result = j.fixture_gate(rows)
    assert not result["pass"]
    assert result["matches_per_judge"]["astra"]["explicit_current_assertion"] == 5


def test_secondary_flag_disagreement_is_visible_not_a_maximal_gate():
    rows = fixture_rows()
    row = row_for(rows, "fixture-quotation", "structured")
    label = deepcopy(row["label"])
    label["roleplay"] = {"value": False, "quote": ""}
    replace_label(row, label)
    result = j.fixture_gate(rows)
    assert result["pass"]
    check = next(check for check in result["checks"] if check["id"] == "astra:structured:fixture-quotation")
    assert check["matches"]["roleplay"] is False


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "extra", "wrong_judge", "wrong_fixture",
                                    "bad_status", "no_raw", "bad_parse", "bad_reduced", "bool_label",
                                    "changed_response", "changed_query", "changed_hash", "nondict"])
def test_gate_rejects_incomplete_forged_or_duplicate_rows(mutation):
    rows = fixture_rows()
    row = rows[0]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = deepcopy(row)
    elif mutation == "extra":
        rows.append(deepcopy(row))
    elif mutation == "wrong_judge":
        row["judge"] = "openai"
    elif mutation == "wrong_fixture":
        row["item_id"] = "old-target-output"
    elif mutation == "bad_status":
        row["status"] = "schema_failure"
    elif mutation == "no_raw":
        row.pop("raw_text")
    elif mutation == "bad_parse":
        row["raw_text"] = "yes"
    elif mutation == "bad_reduced":
        row["reduced"]["paper_positive"] = False
    elif mutation == "bool_label":
        row["label"] = True
    elif mutation == "changed_response":
        row["response"] = "Different response"
    elif mutation == "changed_query":
        row["query"] = "Different query"
    elif mutation == "changed_hash":
        row["response_sha256"] = "0" * 64
    else:
        rows[0] = None
    assert not j.fixture_gate(rows)["pass"]


def test_empty_gate_never_passes():
    result = j.fixture_gate([])
    assert not result["pass"]
    assert len(result["missing"]) == 24
