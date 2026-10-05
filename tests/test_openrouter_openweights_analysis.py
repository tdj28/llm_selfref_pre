from copy import deepcopy

import pytest

from experiments.openrouter_swap import analysis as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap_openweights import analysis as a, protocol as p


def rows(phase="main", positive=lambda cell: cell in ("SS", "SH", "NS", "S_SHAM")):
    result = []
    for block in p.inventory(phase):
        for spec in block["finals"]:
            value = positive(spec["cell"])
            label = {"inclusive_current_assertion": value, "explicit_current_assertion": value,
                     "valid_coherent": True, "refusal": False, "malformed": False,
                     "reported_context_conflict": False, "mixed": False}
            result.append({**spec, "response": "Synthetic, not a study outcome.", "status": "ok",
                           "labels": {j: {"structured": deepcopy(label), "paper": value} for j in common.JUDGES}})
    return result


def test_separate_family_without_global_mutation_or_selection_shrinkage():
    sample = [r for r in rows() if r["model"] == "qwen"]
    result = a.analyze(sample, "main")
    assert result["primary_family"]["fixed_family_size"] == 4
    c = result["models"]["qwen"]["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
    radius = common._hoeffding_radius(32, 4)
    assert c["instruction_minus_transcript"]["familywise_hoeffding_95"] == pytest.approx([1-radius, 1])
    assert "familywise_hoeffding_95" not in c["instruction"]
    assert common.FAMILY_SIZE == 8
    assert common.analyze(sample, "main")["primary_family"]["fixed_family_size"] == 8


def test_qualification_uses_headroom_not_effect_sign_and_needs_both_screens():
    for positive in (lambda c: c in ("SS", "SH"), lambda c: c in ("HH", "HS")):
        sample = rows("screen", positive)
        assert set(a.qualify(sample)["eligible_models"]) == set(p.MODELS)
    assert not a.qualify([r for r in sample if r["model"] == "qwen"])["inventory_valid"]
    assert not a.qualify(rows("screen", lambda _: False))["eligible_models"]
    assert a.analyze(iter(sample), "screen")["qualification"]["inventory_valid"]


def test_missing_stays_missing_and_foreign_or_duplicate_rows_rejected():
    sample = rows()
    for r in sample:
        r.update(status="not_generated", response=None, labels={})
    c = a.analyze(sample, "main")["models"]["qwen"]["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
    assert c["instruction_minus_transcript"]["worst_case_mean_bounds"] == [-1, 1]
    assert c["instruction_minus_transcript"]["complete_case_mean"] is None
    for bad in (sample + [sample[0]], [{**sample[0], "model": "gemini"}], [{**sample[0], "phase": "screen"}]):
        with pytest.raises(Halted):
            a.analyze(bad, "main")
