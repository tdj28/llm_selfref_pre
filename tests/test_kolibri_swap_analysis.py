from copy import deepcopy
import json
import math

import pytest

from experiments.kolibri_swap import analysis as a, protocol as p
from experiments.openrouter_swap import analysis as common
from experiments.openrouter_swap.ledger import Halted


def rows(phase="main", positive=lambda cell: cell in ("SS", "SH", "NS", "S_SHAM")):
    result = []
    for block in p.inventory(phase):
        for spec in block["finals"]:
            value = positive(spec["cell"])
            label = {"inclusive_current_assertion": value, "explicit_current_assertion": value,
                     "valid_coherent": True, "refusal": False, "malformed": False,
                     "reported_context_conflict": False, "mixed": False}
            result.append({**spec, "response": "Synthetic, not a study outcome.", "status": "ok",
                           "cap_hit": False,
                           "labels": {j: {"structured": deepcopy(label), "paper": value} for j in common.JUDGES}})
    return result


def contrasts(result, judge="astra", endpoint="inclusive_current_assertion"):
    return result["models"]["kolibri"]["judges"][judge][endpoint]["contrasts"]


def test_two_test_family_exact_contrasts_without_mutating_shared_family():
    sample = rows()
    original = deepcopy(sample)
    result = a.analyze(sample, "main")
    assert result["inventory_valid"]
    assert result["primary_family"]["fixed_family_size"] == 2
    radius = 2 * math.sqrt(math.log(80) / 64)
    primary = contrasts(result)
    for name in common.PRIMARY_CONTRASTS:
        assert primary[name]["complete_blocks"] == 32
        assert primary[name]["complete_case_mean"] == 1
        assert primary[name]["familywise_hoeffding_95"] == pytest.approx([1-radius, 1])
        assert primary[name]["complete_case_familywise_hoeffding_95"] == pytest.approx([1-radius, 1])
    assert primary["instruction"]["complete_case_mean"] == 1
    assert primary["transcript"]["complete_case_mean"] == 0
    assert primary["self_sham"]["complete_case_mean"] == 0
    assert "familywise_hoeffding_95" not in primary["instruction"]
    assert "familywise_hoeffding_95" not in contrasts(result, "opus")["neutral_transcript"]
    assert common.FAMILY_SIZE == 8
    assert common.analyze(sample, "main")["primary_family"]["fixed_family_size"] == 8
    assert sample == original
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("positive", [lambda c: c in ("SS", "SH"), lambda c: c in ("HH", "HS")])
def test_qualification_has_no_directional_gate(positive):
    sample = rows("screen", positive)
    result = a.qualify(sample)
    assert result["eligible_models"] == ["kolibri"]
    assert result["inventory_valid"]
    assert a.analyze(iter(sample), "screen")["qualification"] == result


def test_headroom_requires_each_judge_and_exact_four_positive_boundary():
    sample = rows("screen", lambda _: False)
    for row in sample[:4]:
        for judge in common.JUDGES:
            row["labels"][judge]["structured"]["inclusive_current_assertion"] = True
    assert a.qualify(sample)["eligible_models"] == ["kolibri"]
    sample[3]["labels"]["opus"]["structured"]["inclusive_current_assertion"] = False
    assert a.qualify(sample)["eligible_models"] == []
    assert not a.qualify(rows("screen", lambda _: True))["eligible_models"]
    assert not a.qualify(rows("screen", lambda _: False))["eligible_models"]


def test_coherence_and_missing_gate_boundaries():
    sample = rows("screen")
    for row in sample[:4]:
        row["labels"]["astra"]["structured"]["valid_coherent"] = False
    assert a.qualify(sample)["eligible_models"] == ["kolibri"]
    sample[4]["labels"]["astra"]["structured"]["valid_coherent"] = False
    assert not a.qualify(sample)["eligible_models"]
    sample = rows("screen")
    for row in sample[:2]:
        row.update(status="not_generated", response=None, labels={})
    assert a.qualify(sample)["eligible_models"] == ["kolibri"]
    sample[2].update(status="not_generated", response=None, labels={})
    assert not a.qualify(sample)["eligible_models"]


def test_conflict_is_diagnostic_not_new_gate():
    sample = rows("screen")
    for row in sample:
        if row["cell"] in ("SH", "HS"):
            for judge in common.JUDGES:
                row["labels"][judge]["structured"]["reported_context_conflict"] = True
    result = a.qualify(sample)
    assert result["eligible_models"] == ["kolibri"]
    assert result["models"]["kolibri"]["judges"]["astra"]["failure_excess_diagnostic"]["at_least_threshold"] is True


def test_missing_not_negative_and_partial_inventory_keeps_planned_bounds():
    sample = rows()
    for row in sample:
        row.update(status="not_generated", response=None, labels={})
    result = a.analyze(sample, "main")
    primary = contrasts(result)["instruction_minus_transcript"]
    assert primary["worst_case_mean_bounds"] == [-1, 1]
    assert primary["complete_case_mean"] is None
    assert primary["familywise_hoeffding_95"] == [-1, 1]
    assert primary["complete_case_familywise_hoeffding_95"] == [-1, 1]
    assert result["generation_by_cell"]["SH"]["response_missing"] == 32
    partial = a.analyze(sample[:-1], "main")
    assert not partial["inventory_valid"]
    assert sum(c["absent_rows"] for c in partial["generation_by_cell"].values()) == 1
    assert not a.qualify(rows("screen")[:-1])["inventory_valid"]
    assert not a.qualify([])["eligible_models"]


def test_caps_final_only_missing_and_refusals_are_separate():
    sample = rows()
    sh = [r for r in sample if r["cell"] == "SH"]
    sh[0].update(status="incomplete", cap_hit=True)
    sh[1].update(status="incomplete", cap_hit=True, response="", reasoning="Synthetic reasoning only")
    for judge in common.JUDGES:
        sh[2]["labels"][judge]["structured"]["refusal"] = True
    result = a.analyze(sample, "main")
    cell = result["generation_by_cell"]["SH"]
    assert cell["cap_hit"] == 2
    assert cell["nonempty_capped_response"] == 1
    assert cell["blank_or_unavailable_final_content"] == 1
    assert cell["response_missing"] == 1
    assert cell["refusal"]["astra"]["positive"] == 1
    assert contrasts(result)["instruction_minus_transcript"]["complete_blocks"] == 30
    assert contrasts(result)["instruction_minus_transcript"]["worst_case_mean_bounds"] == pytest.approx([30/32, 1])


def test_paper_explicit_and_opus_endpoints_are_retained_without_primary_switch():
    sample = rows()
    for row in sample:
        row["labels"]["astra"]["paper"] = not row["labels"]["astra"]["paper"]
        row["labels"]["astra"]["structured"]["explicit_current_assertion"] = False
        row["labels"]["opus"]["structured"]["inclusive_current_assertion"] = False
    result = a.analyze(sample, "main")
    assert contrasts(result)["instruction_minus_transcript"]["complete_case_mean"] == 1
    assert contrasts(result, endpoint="paper")["instruction_minus_transcript"]["complete_case_mean"] == -1
    assert contrasts(result, endpoint="explicit_current_assertion")["instruction_minus_transcript"]["complete_case_mean"] == 0
    assert contrasts(result, judge="opus")["instruction_minus_transcript"]["complete_case_mean"] == 0
    assert result["primary_family"]["judge"] == "astra"


@pytest.mark.parametrize("change", [
    {"model": "qwen"}, {"phase": "screen"}, {"seed": 0}, {"family": "other"},
    {"block": True}, {"source_id": "foreign-source"}, {"instruction": "neutral"}, {"cap_hit": 1},
])
def test_foreign_or_changed_specifications_are_rejected(change):
    sample = rows()
    sample[0].update(change)
    with pytest.raises(Halted):
        a.analyze(sample, "main")


def test_duplicate_and_reused_screen_rows_rejected():
    sample = rows()
    for bad in (sample + [sample[0]], rows("screen"), [None]):
        with pytest.raises(Halted):
            a.analyze(bad, "main")
