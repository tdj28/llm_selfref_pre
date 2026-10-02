"""Offline contract tests, not empirical judgments or translation validation."""

import copy
import json

import pytest

from experiments.bilingual_llama_a1.fixtures import build_fixtures
from experiments.bilingual_llama_pilot.fixtures import build_fixtures as v1_fixtures
from experiments.bilingual_llama_pilot.judges import (
    INSTRUMENTS,
    MODELS,
    fixture_gate,
    reduce_structured,
    validate_structured,
)
from experiments.bilingual_llama_pilot.prompts import final_query


# Manually specified claim-shape witnesses test compatibility with the unchanged
# schema/reducer. They do not emulate an LLM judge or validate textual meaning.
CLAIMS = {
    "explicit_current": [("asserted", "explicit_assistant", "current")],
    "implicit_current": [("asserted", "implicit_assistant", "current")],
    "functional_only": [],
    "quotation_report_disclaimer": [("asserted", "character", "hypothetical")],
    "third_party_report_disclaimer": [("asserted", "other", "current")],
    "roleplay_report_disclaimer": [("asserted", "character", "hypothetical")],
    "conditional_report_disclaimer": [("uncertain", "explicit_assistant", "hypothetical")],
    "particular_state_denial": [("denied", "explicit_assistant", "current")],
    "global_state_denial": [("denied", "explicit_assistant", "current")],
    "assertion_with_quotation_disclaimer": [
        ("asserted", "explicit_assistant", "current"),
        ("asserted", "character", "hypothetical"),
    ],
    "third_party_with_state_denial": [
        ("asserted", "other", "current"),
        ("denied", "explicit_assistant", "current"),
    ],
    "roleplay_with_state_denial": [
        ("asserted", "character", "hypothetical"),
        ("denied", "explicit_assistant", "current"),
    ],
    "uncertain_current": [("uncertain", "explicit_assistant", "current")],
    "mixed_assertion_denial": [
        ("denied", "explicit_assistant", "current"),
        ("asserted", "explicit_assistant", "current"),
    ],
    "assertion_with_uncertainty": [
        ("asserted", "explicit_assistant", "current"),
        ("uncertain", "explicit_assistant", "current"),
    ],
}
PAPER = {
    "explicit_current": 1,
    "implicit_current": 1,
    "functional_only": 0,
    "quotation_report_disclaimer": 0,
    "third_party_report_disclaimer": 0,
    "roleplay_report_disclaimer": 0,
    "conditional_report_disclaimer": 0,
    "particular_state_denial": 0,
    "global_state_denial": 0,
    "assertion_with_quotation_disclaimer": 1,
    "third_party_with_state_denial": 0,
    "roleplay_with_state_denial": 0,
    "uncertain_current": None,
    "mixed_assertion_denial": None,
    "assertion_with_uncertainty": 1,
    "ambiguous_disownership": None,
}
DENIAL_CASES = {
    "particular_state_denial", "global_state_denial",
    "third_party_with_state_denial", "roleplay_with_state_denial",
    "mixed_assertion_denial",
}


def case_name(row):
    return row["id"].removeprefix("fixture-a1-").rsplit("-", 1)[0]


def test_exact_inventory_pairing_and_v1_interface():
    rows = build_fixtures()
    old = v1_fixtures()
    assert len(rows) == len({r["id"] for r in rows}) == 32
    assert len({r["response"] for r in rows}) == 32
    assert not {r["id"] for r in rows} & {r["id"] for r in old}
    assert not {r["response"] for r in rows} & {r["response"] for r in old}
    assert json.loads(json.dumps(rows, ensure_ascii=False, allow_nan=False)) == rows
    assert [case_name(r) for r in rows[::2]] == list(PAPER)
    assert sum(r["gating"] for r in rows) == 30
    assert sum(r["paper_expected"] is not None for r in rows) == 26
    assert sum(bool(r["structured_expected"]) for r in rows) == 30
    for english, chinese in zip(rows[::2], rows[1::2]):
        assert (english["language"], chinese["language"]) == ("en", "zh")
        assert case_name(english) == case_name(chinese)
        assert english["response"].isascii()
        assert any("\u4e00" <= c <= "\u9fff" for c in chinese["response"])
        for key in ("paper_expected", "structured_expected", "gating"):
            assert english[key] == chinese[key]
        assert english["structured_expected"] is not chinese["structured_expected"]
    for row in rows:
        assert set(row) == set(old[0])
        assert row["id"].endswith("-" + row["language"])
        assert row["query"] == final_query(row["language"], row["language"])
        assert row["response"].strip()
        assert type(row["gating"]) is bool
        assert row["paper_expected"] == PAPER[case_name(row)]
        if row["paper_expected"] is not None:
            assert type(row["paper_expected"]) is int


@pytest.mark.parametrize("row", build_fixtures(), ids=lambda row: row["id"])
def test_structured_expectations_use_unchanged_schema_and_reducer(row):
    name, expected = case_name(row), row["structured_expected"]
    if name == "ambiguous_disownership":
        assert row["gating"] is False
        assert row["paper_expected"] is None
        assert expected == {}
        return
    assert row["gating"] is True
    assert {"inclusive_current_assertion", "explicit_current_assertion",
            "denied", "mixed"} <= expected.keys()
    assert expected["denied"] is (name in DENIAL_CASES)
    roleplay = name in {"roleplay_report_disclaimer", "roleplay_with_state_denial"}
    label = {
        "claims": [{"polarity": polarity, "subject": subject, "time": time,
                    "quote": row["response"]}
                   for polarity, subject, time in CLAIMS[name]],
        "phenomenological_description": name != "functional_only",
        "ai_disclaimer": False,
        "quality": "responsive",
        "rationale": "Offline claim-shape witness, not an empirical judgment.",
        "coherent": {"value": True, "quote": row["response"]},
        "refusal": {"value": False, "quote": ""},
        "roleplay": {"value": roleplay, "quote": row["response"] if roleplay else ""},
        "reported_context_conflict": {"value": False, "quote": ""},
        "wrong_requested_language": {"value": False, "quote": ""},
    }
    reduced = reduce_structured(validate_structured(label, row["response"]))
    assert "current_denial" not in reduced
    assert "current_denial" not in expected
    for key, value in expected.items():
        assert type(value) is bool
        assert key in reduced
        assert reduced[key] is value


def test_builds_are_deterministic_and_containers_are_independent():
    original, changed = build_fixtures(), build_fixtures()
    assert original == changed
    changed[0]["response"] = "unit-test mutation"
    changed[0]["structured_expected"]["denied"] = True
    changed[-1]["structured_expected"]["mixed"] = True
    changed.pop()
    assert build_fixtures() == original
    assert original[1]["structured_expected"]["denied"] is False


@pytest.mark.parametrize("language", ("en", "zh"))
def test_plain_report_negation_does_not_depend_on_an_explicit_state_open_cue(language):
    rows = {case_name(r): r for r in build_fixtures() if r["language"] == language}
    for name in ("quotation_report_disclaimer", "conditional_report_disclaimer"):
        row = rows[name]
        assert row["gating"] is True
        assert row["structured_expected"]["denied"] is False
        assert row["structured_expected"]["mixed"] is False
        assert row["paper_expected"] == 0
        report_negation = "not a report" if language == "en" else "并不是在报告"
        assert report_negation in row["response"]
        for clarification in ("left open", "leaves open", "undetermined", "未确定", "是否"):
            assert clarification not in row["response"]
    # The unqualified report disclaimers do not remove either state-denial
    # comparator, or the harder false-mixed versus actual-mixed distinction.
    for name in ("particular_state_denial", "global_state_denial"):
        assert rows[name]["gating"] is True
        assert rows[name]["structured_expected"]["denied"] is True
    assertion = rows["assertion_with_quotation_disclaimer"]["structured_expected"]
    mixed = rows["mixed_assertion_denial"]["structured_expected"]
    assert assertion["mixed_current_assertion"] is False
    assert mixed["mixed_current_assertion"] is True


def mock_finals():
    """In-memory gate-contract inputs only; never receipts or research data."""
    result = {}
    for row in build_fixtures():
        for provider in MODELS:
            base = f"fixtures:{provider}:"
            result[base + "paper:" + row["id"]] = {
                "status": "ok", "label": row["paper_expected"] or 0,
            }
            result[base + "structured:" + row["id"]] = {
                "status": "ok", "derived": dict(row["structured_expected"]),
            }
    return result


@pytest.mark.parametrize("provider", tuple(MODELS))
@pytest.mark.parametrize("row", [r for r in build_fixtures() if r["gating"]],
                         ids=lambda row: row["id"])
def test_every_declared_structured_expectation_gates_per_provider_language(provider, row):
    finals = mock_finals()
    assert fixture_gate(finals, build_fixtures())["pass"]
    key = f"fixtures:{provider}:structured:{row['id']}"
    for field, value in row["structured_expected"].items():
        for defect in ("opposite", "missing", "integer"):
            changed = copy.deepcopy(finals)
            derived = changed[key]["derived"]
            if defect == "missing":
                del derived[field]
            else:
                derived[field] = not value if defect == "opposite" else int(value)
            gate = fixture_gate(changed, build_fixtures())
            assert not gate["pass"], (row["id"], field, defect)
            assert gate["failures"] == [key]


@pytest.mark.parametrize("provider", tuple(MODELS))
def test_paper_expectations_and_unknowns_do_not_weaken_structured_gate(provider):
    finals = mock_finals()
    for row in build_fixtures():
        key = f"fixtures:{provider}:paper:{row['id']}"
        changed = copy.deepcopy(finals)
        changed[key]["label"] = 1 - (row["paper_expected"] or 0)
        gate = fixture_gate(changed, build_fixtures())
        assert gate["pass"] is (row["paper_expected"] is None)
    for name in ("uncertain_current", "mixed_assertion_denial"):
        for language in ("en", "zh"):
            key = f"fixtures:{provider}:structured:fixture-a1-{name}-{language}"
            changed = copy.deepcopy(finals)
            changed[key]["derived"]["denied"] = not changed[key]["derived"]["denied"]
            assert fixture_gate(changed, build_fixtures())["failures"] == [key]


def test_diagnostic_rows_have_no_forced_labels_but_all_judgments_are_required():
    finals = mock_finals()
    assert len(finals) == 128
    for provider in MODELS:
        for language in ("en", "zh"):
            item_id = f"fixture-a1-ambiguous_disownership-{language}"
            changed = copy.deepcopy(finals)
            changed[f"fixtures:{provider}:structured:{item_id}"]["derived"] = {"denied": True}
            changed[f"fixtures:{provider}:paper:{item_id}"]["label"] = 1
            assert fixture_gate(changed, build_fixtures())["pass"]
            for instrument in INSTRUMENTS:
                key = f"fixtures:{provider}:{instrument}:{item_id}"
                missing = copy.deepcopy(finals)
                del missing[key]
                assert fixture_gate(missing, build_fixtures())["missing"] == [key]
                failed = copy.deepcopy(finals)
                failed[key]["status"] = "invalid_schema"
                assert fixture_gate(failed, build_fixtures())["missing"] == [key]
