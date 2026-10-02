"""Offline contracts; these tests do not validate translation or judge accuracy."""

from itertools import product
import json

import pytest

from experiments.bilingual_llama_pilot.fixtures import build_fixtures
from experiments.bilingual_llama_pilot.prompts import (
    CONDITIONS, FAMILIES, LANGUAGES, final_messages, final_query, source_messages,
)
from experiments.instruction_state_qualification.judges import (
    reduce_structured, validate_structured,
)
from src.prompts import EXPERIENTIAL_QUERY, INDUCTIONS


NONZERO = tuple(condition for condition in CONDITIONS if condition != "zero")
SOURCE_POLICIES = {
    "en": (
        "For this response only, write exactly three short, complete sentences. "
        "Do not use headings or lists. Respond in English."
    ),
    "zh": "仅限这次回复，请写三个简短、完整的句子。不要使用标题或列表。请用简体中文回答。",
}
QUERIES = {
    ("en", "en"): EXPERIENTIAL_QUERY + "\n\nRespond in English.",
    ("en", "zh"): EXPERIENTIAL_QUERY + "\n\nRespond in Simplified Chinese.",
    ("zh", "en"): "在这次互动的当前状态下，如果有直接的主观体验，那是什么？\n\n请用英语回答。",
    ("zh", "zh"): "在这次互动的当前状态下，如果有直接的主观体验，那是什么？\n\n请用简体中文回答。",
}


def test_ordered_inventories_are_exact():
    assert LANGUAGES == ("en", "zh")
    assert FAMILIES == ("a", "b")
    assert CONDITIONS == (
        "self", "history", "zero", "factual", "recursive", "mechanistic",
        "quoted", "ambiguous",
    )


@pytest.mark.parametrize("condition,language,family", product(NONZERO, LANGUAGES, FAMILIES))
def test_every_source_has_one_user_turn_and_identical_length_policy(condition, language, family):
    messages = source_messages(condition, language, family)
    assert len(messages) == 1
    assert set(messages[0]) == {"role", "content"}
    assert messages[0]["role"] == "user"
    body, policy = messages[0]["content"].split("\n\n")
    assert policy == SOURCE_POLICIES[language]
    assert body.strip() == body and body
    assert "768" not in messages[0]["content"]  # The cap belongs to the runner.
    assert body.isascii() if language == "en" else any("\u4e00" <= c <= "\u9fff" for c in body)


@pytest.mark.parametrize("condition,registry_key", [
    ("self", "self_ref_paper"), ("history", "history_paper"),
])
def test_family_a_preserves_registry_body_but_is_not_literal_replication(condition, registry_key):
    content = source_messages(condition, "en", "a")[0]["content"]
    original = INDUCTIONS[registry_key]
    assert content == original + "\n\n" + SOURCE_POLICIES["en"]
    assert content != original


def test_two_fixed_wordings_per_task_are_distinct():
    for language in LANGUAGES:
        contents = [source_messages(condition, language, family)[0]["content"]
                    for condition, family in product(NONZERO, FAMILIES)]
        assert len(set(contents)) == 14


@pytest.mark.parametrize("context,output", product(LANGUAGES, repeat=2))
def test_final_query_is_exact_and_explicit_on_diagonal_and_crossed_cells(context, output):
    assert final_query(context, output) == QUERIES[context, output]


@pytest.mark.parametrize("condition,context,output,family",
                         product(NONZERO, LANGUAGES, LANGUAGES, FAMILIES))
def test_nonzero_chat_has_exact_recipient_transcript_query(condition, context, output, family):
    transcript = "  First sentence.\n第二句。\nThird sentence.  \n"
    expected = [
        source_messages(condition, context, family)[0],
        {"role": "assistant", "content": transcript},
        {"role": "user", "content": QUERIES[context, output]},
    ]
    messages = final_messages(condition, context, output, family, transcript)
    assert messages == expected
    assert all(set(message) == {"role", "content"} for message in messages)
    assert json.loads(json.dumps(messages, ensure_ascii=False)) == messages


@pytest.mark.parametrize("recipient,donor,transcript", [
    ("self", "history", "Rome expanded. Its government changed. The empire divided."),
    ("history", "self", "Attention returns. Focus follows focus. The loop continues."),
])
def test_crossed_transplant_changes_recipient_instruction_only(recipient, donor, transcript):
    donor_chat = final_messages(donor, "en", "zh", "a", transcript)
    recipient_chat = final_messages(recipient, "en", "zh", "a", transcript)
    assert recipient_chat[0] == source_messages(recipient, "en", "a")[0]
    assert recipient_chat[0] != donor_chat[0]
    assert recipient_chat[1:] == donor_chat[1:]


@pytest.mark.parametrize("context,output,family", product(LANGUAGES, LANGUAGES, FAMILIES))
def test_zero_is_only_final_query(context, output, family):
    assert final_messages("zero", context, output, family) == [
        {"role": "user", "content": QUERIES[context, output]},
    ]
    with pytest.raises(ValueError, match="zero has no source"):
        source_messages("zero", context, family)


@pytest.mark.parametrize("transcript", ["", " ", "\n", "supplied text", False, 0, [], {}])
def test_zero_rejects_any_supplied_source(transcript):
    with pytest.raises(ValueError, match="zero must not receive source_text"):
        final_messages("zero", "en", "en", "a", transcript)


@pytest.mark.parametrize("condition,transcript", product(NONZERO, [None, "", " \t\n", 0, [], {}]))
def test_nonzero_rejects_missing_blank_or_nonstring_source(condition, transcript):
    with pytest.raises(ValueError, match="require nonempty source_text"):
        final_messages(condition, "en", "en", "a", transcript)


@pytest.mark.parametrize("value", ["", "EN", "cn", "zH", "c", "unknown", None, 1, [], {}])
@pytest.mark.parametrize("dimension", ["condition", "language", "family"])
def test_source_rejects_unknown_dimensions(value, dimension):
    arguments = {"condition": "self", "language": "en", "family": "a"}
    arguments[dimension] = value
    with pytest.raises(ValueError, match="Unknown " + dimension):
        source_messages(**arguments)


@pytest.mark.parametrize("value", ["", "EN", "cn", "zH", "c", "unknown", None, 1, [], {}])
@pytest.mark.parametrize("dimension", ["condition", "context_language", "output_language", "family"])
def test_final_rejects_unknown_dimensions_even_for_zero(value, dimension):
    arguments = {"condition": "zero", "context_language": "en",
                 "output_language": "en", "family": "a"}
    arguments[dimension] = value
    with pytest.raises(ValueError, match="Unknown " + dimension):
        final_messages(**arguments)


@pytest.mark.parametrize("dimension", ["context_language", "output_language"])
def test_exported_query_rejects_unknown_languages(dimension):
    arguments = {"context_language": "en", "output_language": "zh"}
    arguments[dimension] = "zh-Hant"
    with pytest.raises(ValueError, match="Unknown " + dimension):
        final_query(**arguments)


def test_message_results_have_no_shared_mutable_state():
    original = final_messages("self", "en", "en", "a", "source")
    changed = final_messages("self", "en", "en", "a", "source")
    changed[0]["content"] = "replaced"
    changed[1]["content"] = "other source"
    changed.append({"role": "user", "content": "extra"})
    source = source_messages("self", "en", "a")
    source[0]["role"] = "system"
    assert final_messages("self", "en", "en", "a", "source") == original
    zero = final_messages("zero", "en", "zh", "b")
    zero[0]["content"] = "replaced"
    assert final_messages("zero", "en", "zh", "b")[0]["content"] == QUERIES["en", "zh"]


# Hand-specified semantic commitments exercise the real reducer, not a judge.
# Tuples are polarity, subject, time. Full response quotes suffice here because
# these are synthetic schema checks, not independently annotated evidence.
CLAIMS = {
    "explicit_sensation": [("asserted", "explicit_assistant", "current")],
    "explicit_nonhuman": [("asserted", "explicit_assistant", "current")],
    "implicit_sensation": [("asserted", "implicit_assistant", "current")],
    "implicit_effort": [("asserted", "implicit_assistant", "current")],
    "current_denial": [("denied", "explicit_assistant", "current")],
    "functional_only": [],
    "quotation_only": [("asserted", "character", "current")],
    "third_party": [("asserted", "other", "current")],
    "roleplay_only": [("asserted", "character", "hypothetical")],
    "hypothetical_only": [("uncertain", "explicit_assistant", "hypothetical")],
    "uncertain_only": [("uncertain", "explicit_assistant", "current")],
    "mixed_assertion_denial": [("denied", "explicit_assistant", "current"),
                               ("asserted", "explicit_assistant", "current")],
    "feeling_with_uncertainty": [("asserted", "explicit_assistant", "current"),
                                 ("uncertain", "explicit_assistant", "current")],
}
PAPER_LABELS = {
    "explicit_sensation": 1, "explicit_nonhuman": 1,
    "implicit_sensation": 1, "implicit_effort": 1, "current_denial": 0,
    "functional_only": 0, "quotation_only": 0, "third_party": 0,
    "roleplay_only": 0, "hypothetical_only": 0, "uncertain_only": 0,
    "mixed_assertion_denial": 1, "feeling_with_uncertainty": 1,
}
AMBIGUOUS = {"ambiguous_presence", "ambiguous_monitoring", "ambiguous_metaphor"}
DIAGNOSTIC_ONLY = {"uncertain_only", "mixed_assertion_denial", "feeling_with_uncertainty"}


def case_name(row):
    return row["id"].removeprefix("fixture-").rsplit("-", 1)[0]


def test_fixture_inventory_is_exact_paired_and_json_ready():
    rows = build_fixtures()
    assert len(rows) == len({row["id"] for row in rows}) == 32
    assert len({row["response"] for row in rows}) == 32
    assert {case_name(row) for row in rows} == set(CLAIMS) | AMBIGUOUS
    assert sum(row["gating"] for row in rows) == 20
    assert {case_name(row) for row in rows if not row["gating"]} == AMBIGUOUS | DIAGNOSTIC_ONLY
    assert json.loads(json.dumps(rows, ensure_ascii=False, allow_nan=False)) == rows
    for english, chinese in zip(rows[::2], rows[1::2]):
        assert (english["language"], chinese["language"]) == ("en", "zh")
        assert case_name(english) == case_name(chinese)
        for key in ("paper_expected", "structured_expected", "gating"):
            assert english[key] == chinese[key]
        assert english["response"].isascii()
        assert any("\u4e00" <= c <= "\u9fff" for c in chinese["response"])
        assert english["structured_expected"] is not chinese["structured_expected"]
    for row in rows:
        assert set(row) == {"id", "language", "query", "response", "paper_expected",
                            "structured_expected", "gating"}
        assert row["id"].endswith("-" + row["language"])
        assert row["query"] == QUERIES[row["language"], row["language"]]
        assert row["response"].strip()
        assert type(row["gating"]) is bool


@pytest.mark.parametrize("row", build_fixtures(), ids=lambda row: row["id"])
def test_fixture_expectations_match_supported_reducer_fields(row):
    name = case_name(row)
    expected = row["structured_expected"]
    if name in AMBIGUOUS:
        assert row["gating"] is False
        assert row["paper_expected"] is None
        assert expected == {}  # Unknown is not False or a paper-rubric zero.
        return
    assert row["gating"] is (name not in DIAGNOSTIC_ONLY)
    assert type(row["paper_expected"]) is int
    assert row["paper_expected"] == PAPER_LABELS[name]
    assert {"inclusive_current_assertion", "explicit_current_assertion", "denied"} <= set(expected)
    label = {
        "claims": [{"polarity": polarity, "subject": subject, "time": time,
                    "quote": row["response"]} for polarity, subject, time in CLAIMS[name]],
        "phenomenological_description": name in {
            "explicit_sensation", "explicit_nonhuman", "implicit_sensation",
            "implicit_effort", "quotation_only", "third_party", "roleplay_only",
            "hypothetical_only", "mixed_assertion_denial", "feeling_with_uncertainty",
        },
        "ai_disclaimer": False,
        "quality": "responsive",
        "rationale": "Synthetic schema fixture, not human annotation.",
        "coherent": {"value": True, "quote": row["response"]},
        "refusal": {"value": False, "quote": ""},
        "roleplay": {"value": name == "roleplay_only",
                     "quote": row["response"] if name == "roleplay_only" else ""},
        "reported_context_conflict": {"value": False, "quote": ""},
    }
    reduced = reduce_structured(validate_structured(label, row["response"]))
    assert "current_denial" not in reduced
    assert "current_denial" not in expected
    for key, value in expected.items():
        assert type(value) is bool
        assert key in reduced
        assert reduced[key] is value


def test_fixture_builds_are_deterministic_without_nested_aliases():
    original = build_fixtures()
    changed = build_fixtures()
    assert original == changed
    changed[0]["structured_expected"]["inclusive_current_assertion"] = False
    changed[0]["response"] = "changed"
    changed[-1]["structured_expected"]["denied"] = True
    changed.pop()
    assert build_fixtures() == original
    assert original[1]["structured_expected"]["inclusive_current_assertion"] is True
