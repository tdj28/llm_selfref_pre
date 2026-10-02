import pytest

from experiments.bilingual_llama_pilot.release import phase_labels


def test_phase_separation_with_identical_item_ids():
    rows = {phase: {"phase": phase, "status": "ok", "item_id": "same-id",
            "provider": "openai", "instrument": "paper", "label": value}
            for phase, value in (("fixtures", 1), ("target", 0), ("translated", 1))}
    assert phase_labels(rows, phase="target") == {("same-id", "openai", "paper"): 0}
    assert phase_labels(rows, phase="translated") == {("translated:same-id", "openai", "paper"): 1}


def test_invalid_status_is_missing_not_negative():
    rows = {"one": {"phase": "target", "status": "schema_failure"}}
    assert phase_labels(rows, phase="target") == {}


def test_duplicate_or_incorrect_instrument_results_fail():
    row = {"phase": "target", "status": "ok", "item_id": "a", "provider": "openai",
           "instrument": "structured", "derived": {"inclusive_current_assertion": True}}
    with pytest.raises(ValueError, match="Duplicate"):
        phase_labels({"a": row, "b": row}, phase="target")
