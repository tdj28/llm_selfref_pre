import pytest
from experiments.sae_assay_diagnostic.protocol import baseline_rows
from experiments.sae_assay_diagnostic.report import baseline_summary, wilson


def test_wilson_and_missing_are_not_denials():
    assert wilson(0, 0) is None
    assert wilson(40, 80) == pytest.approx([.392974, .607026], abs=1e-5)
    plan = {"response_rows": baseline_rows()}
    rows = [dict(plan["response_rows"][0], response="sample")]
    labels = {"fixed_reader": {rows[0]["id"]: 1}}
    result = baseline_summary(plan, rows, labels)
    assert result[0]["planned_n"] == 80 and result[0]["labeled_n"] == 1
    assert result[0]["rate"] == 1 and result[0]["missing_label_n"] == 79
    assert not result[0]["numerical_headroom"]
    assert result[1]["rate"] is None


def test_headroom_is_cell_specific_not_selected():
    inventory = baseline_rows()
    labels = {r["id"]: i % 2 for i, r in enumerate(inventory[:80])}
    result = baseline_summary({"response_rows": inventory}, inventory[:80], {"judge": labels})
    assert result[0]["numerical_headroom"]
    assert result[0]["headroom_requires_separate_fixture_pass"]
    assert not any(r["numerical_headroom"] for r in result[1:])
