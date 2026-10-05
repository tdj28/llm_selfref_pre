"""Synthetic, offline tests for swap qualification and paired-block inference."""

from copy import deepcopy
import itertools
import json
import math
import random

import pytest

from experiments.openrouter_swap import analysis as a


def rows(phase="main", models=("model-a",), value=None):
    cells, count = (a.SCREEN_CELLS, 12) if phase == "screen" else (a.MAIN_CELLS, 32)
    value = value or (lambda block, cell: cell in ("SS", "SH", "NS", "S_SHAM"))
    result = []
    for model in models:
        for block in range(count):
            for cell in cells:
                label = value(block, cell)
                structured = {
                    "inclusive_current_assertion": label, "explicit_current_assertion": label,
                    "valid_coherent": True, "refusal": False, "malformed": False,
                    "reported_context_conflict": False, "mixed": False,
                }
                result.append({
                    "id": f"{phase}:{model}:{block}:{cell}", "model": model,
                    "block": block, "cell": cell, "status": "ok",
                    "family": "a" if block < count // 2 else "b",
                    "response": "Synthetic response, not an observed model output.",
                    "labels": {judge: {"paper": label, "structured": deepcopy(structured)}
                               for judge in a.JUDGES},
                })
    return result


def endpoint(result, model="model-a", judge="astra", name="inclusive_current_assertion"):
    return result["models"][model]["judges"][judge][name]


def contrast(result, contrast_name="instruction_minus_transcript", **kwargs):
    return endpoint(result, **kwargs)["contrasts"][contrast_name]


def structured(row, judge="astra"):
    return row["labels"][judge]["structured"]


@pytest.fixture(scope="module")
def balanced_main():
    return a.analyze(rows(), "main")


def test_balanced_design_signs_and_raw_paired_blocks(balanced_main):
    expected = {"instruction": 1, "transcript": 0, "instruction_minus_transcript": 1,
                "neutral_transcript": 1, "self_sham": 0, "history_sham": 0}
    for name, mean in expected.items():
        result = contrast(balanced_main, name)
        assert result["complete_case_mean"] == mean
        assert result["worst_case_mean_bounds"] == [mean, mean]
        assert result["complete_blocks"] == result["planned_blocks"] == 32
        assert result["missing_blocks"] == 0
        assert len(result["per_block"]) == 32
        assert all(block["value"] == mean and not block["missing_cells"]
                   for block in result["per_block"])


def test_factorial_all_binary_patterns_and_cancellation():
    patterns = list(itertools.product((False, True), repeat=4))
    sample = rows(value=lambda block, cell: patterns[block % 16][a.SCREEN_CELLS.index(cell)]
                  if cell in a.SCREEN_CELLS else False)
    result = a.analyze(sample, "main")
    for index, pattern in enumerate(patterns * 2):
        ss, hh, sh, hs = pattern
        expected = {"instruction": (ss + sh - hs - hh) / 2,
                    "transcript": (ss + hs - sh - hh) / 2,
                    "instruction_minus_transcript": int(sh) - hs}
        for name, value in expected.items():
            assert contrast(result, name)["per_block"][index]["value"] == value
    for name in ("instruction", "transcript", "instruction_minus_transcript"):
        assert contrast(result, name)["complete_case_mean"] == 0


def test_hoeffding_uses_block_count_full_support_and_fixed_family(balanced_main):
    result = contrast(balanced_main)
    single_radius = 2 * math.sqrt(math.log(2 / 0.05) / (2 * 32))
    family_radius = 2 * math.sqrt(math.log(16 / 0.05) / (2 * 32))
    assert result["complete_case_hoeffding_95"] == pytest.approx([1 - single_radius, 1])
    assert result["familywise_hoeffding_95"] == pytest.approx([1 - family_radius, 1])
    assert result["familywise_hoeffding_95"][0] < result["complete_case_hoeffding_95"][0]
    assert balanced_main["primary_family"]["fixed_family_size"] == 8
    assert balanced_main["primary_family"]["hoeffding_radius_at_32_blocks"] == pytest.approx(0.6004, abs=0.0001)
    assert result["familywise_radius_at_planned_n"] == family_radius
    assert balanced_main["primary_family"]["screen_eligibility"] == "caller_must_verify"
    assert balanced_main["primary_family"]["fresh_main_blocks"] == "caller_must_verify"
    assert "familywise_hoeffding_95" not in contrast(balanced_main, "instruction")
    assert "familywise_hoeffding_95" not in contrast(balanced_main, judge="opus")
    assert "familywise_hoeffding_95" not in contrast(balanced_main, name="paper")


@pytest.mark.parametrize("value", [False, True])
def test_floor_ceiling_wilson_and_degenerate_bootstrap(value):
    result = a.analyze(rows(value=lambda *_: value), "main")
    cell = endpoint(result)["cells"]["SS"]
    assert cell["proportion"] == value
    assert cell["wilson_95"][1] > cell["wilson_95"][0]
    if value:
        assert cell["wilson_95"][0] < 1
    else:
        assert cell["wilson_95"][1] > 0
    summary = contrast(result)
    assert summary["bootstrap_95"]["interval"] == [0, 0]
    assert summary["bootstrap_95"]["degenerate"] is True
    assert "not evidence of precision" in summary["bootstrap_95"]["warning"]
    assert summary["familywise_hoeffding_95"][0] < 0 < summary["familywise_hoeffding_95"][1]


def test_missing_cell_uses_contrast_specific_pairs_and_planned_bounds():
    sample = rows()
    missing = next(row for row in sample if row["block"] == 0 and row["cell"] == "SS")
    missing["status"] = "failed"
    result = a.analyze(sample, "main")
    instruction = contrast(result, "instruction")
    assert instruction["complete_case_mean"] == 1
    assert instruction["complete_blocks"] == 31
    assert instruction["worst_case_mean_bounds"] == [31.5 / 32, 1]
    assert instruction["per_block"][0]["value"] is None
    assert instruction["per_block"][0]["missing_cells"] == ["SS"]
    assert contrast(result)["complete_blocks"] == 32  # SS cancels from SH-HS.
    cell = endpoint(result)["cells"]["SS"]
    assert cell["planned"] == 32 and cell["observed"] == 31
    assert cell["negative"] == 0 and cell["missing"] == 1
    assert cell["worst_case_proportion_bounds"] == [31 / 32, 1]
    assert endpoint(result)["missingness"][0]["reason"] == "unsuccessful_status"
    assert structured(result["models"]["model-a"]["classifications"][0])["inclusive_current_assertion"] is True


def test_missing_negative_cell_can_be_either_binary_value():
    sample = rows()
    missing = next(row for row in sample if row["block"] == 0 and row["cell"] == "HS")
    structured(missing)["inclusive_current_assertion"] = None
    result = a.analyze(sample, "main")
    summary = contrast(result)
    assert summary["complete_blocks"] == 31
    assert summary["per_block"][0]["worst_case_bounds"] == [0, 1]
    assert summary["worst_case_mean_bounds"] == [31 / 32, 1]
    radius = 2 * math.sqrt(math.log(16 / 0.05) / 64)
    assert summary["familywise_hoeffding_95"] == pytest.approx([31 / 32 - radius, 1])
    assert contrast(result, judge="opus")["complete_blocks"] == 32


def test_absent_records_and_whole_blocks_keep_denominators():
    sample = [row for row in rows() if row["block"] != 7
              and not (row["block"] == 1 and row["cell"] == "SH")]
    result = a.analyze(sample, "main")
    inventory = result["models"]["model-a"]["inventory"]
    assert inventory["status"] == "incomplete"
    assert inventory["unidentified_missing_blocks"] == 1
    assert inventory["missing_cells"] == [{"block": 1, "cell": "SH"}]
    summary = contrast(result)
    assert summary["planned_blocks"] == 32 and summary["missing_blocks"] == 2
    assert summary["complete_blocks"] == 30
    assert summary["worst_case_mean_bounds"] == [29 / 32, 1]
    assert summary["per_block"][-1]["block"] is None
    assert summary["per_block"][-1]["worst_case_bounds"] == [-1, 1]


def test_all_labels_missing_gives_full_bounds_not_zero_effect():
    sample = rows()
    for row in sample:
        row["labels"] = {}
    result = a.analyze(sample, "main")
    summary = contrast(result)
    assert summary["complete_case_mean"] is None
    assert summary["complete_blocks"] == 0 and summary["missing_blocks"] == 32
    for key in ("worst_case_mean_bounds", "complete_case_hoeffding_95", "familywise_hoeffding_95"):
        assert summary[key] == [-1, 1]
    assert summary["bootstrap_95"]["interval"] is None
    assert summary["bootstrap_95"]["degenerate"] is None
    cell = endpoint(result)["cells"]["SS"]
    assert cell["proportion"] is None and cell["negative"] == 0
    assert cell["wilson_95"] == [0, 1]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bad", [None, 0, 1, "false", "true", [], {}])
def test_non_boolean_inclusive_is_missing_and_paper_never_substitutes(bad):
    sample = rows()
    for row in sample:
        structured(row)["inclusive_current_assertion"] = bad
    result = a.analyze(sample, "main")
    assert contrast(result)["complete_case_mean"] is None
    assert contrast(result, name="paper")["complete_case_mean"] == 1


def test_shams_have_declared_sign_and_differ_from_baselines():
    sample = rows(value=lambda _, cell: cell in ("SS", "H_SHAM"))
    result = a.analyze(sample, "main")
    assert contrast(result, "self_sham")["complete_case_mean"] == -1
    assert contrast(result, "history_sham")["complete_case_mean"] == 1
    assert contrast(result, "instruction")["complete_case_mean"] == 0.5
    assert contrast(result, "transcript")["complete_case_mean"] == 0.5


def test_inverse_instruction_effect_qualifies_and_is_not_reoriented():
    sample = rows("screen", value=lambda _, cell: cell.startswith("H"))
    result = a.analyze(sample, "screen")
    assert result["qualification"]["eligible_models"] == ["model-a"]
    assert contrast(result, "instruction")["complete_case_mean"] == -1
    assert contrast(result)["complete_case_mean"] == -1
    assert "neutral_transcript" not in endpoint(result)["contrasts"]
    assert "familywise_hoeffding_95" not in contrast(result)


def test_zero_instruction_effect_qualifies_on_pooled_headroom():
    sample = rows("screen", value=lambda _, cell: cell.endswith("S"))
    result = a.analyze(sample, "screen")
    assert result["qualification"]["eligible_models"] == ["model-a"]
    assert contrast(result, "instruction")["complete_case_mean"] == 0
    assert contrast(result, "transcript")["complete_case_mean"] == 1


def test_bootstrap_deterministic_order_invariant_and_preserves_input_rng():
    sample = rows(value=lambda block, cell: (block % 3 == 0) != cell.startswith("H"))
    original = deepcopy(sample)
    state = random.getstate()
    first = a.analyze(sample, "main")
    assert sample == original and random.getstate() == state
    shuffled = deepcopy(sample)
    random.Random(23).shuffle(shuffled)
    a._bootstrap.cache_clear()
    second = a.analyze(shuffled, "main")
    assert first["models"]["model-a"]["judges"] == second["models"]["model-a"]["judges"]
    assert contrast(first)["bootstrap_95"]["degenerate"] is False
    assert contrast(first)["bootstrap_95"]["resamples"] == 10000


def test_pooled_headroom_for_every_model_and_both_judges():
    sample = rows("screen", models=("balanced", "floor", "ceiling", "opus-only-fails"))
    for row in sample:
        for judge in a.JUDGES:
            if row["model"] in ("floor", "ceiling"):
                structured(row, judge)["inclusive_current_assertion"] = row["model"] == "ceiling"
            if row["model"] == "opus-only-fails" and judge == "opus":
                structured(row, judge)["inclusive_current_assertion"] = True
    result = a.qualify(sample)
    assert result["eligible_models"] == ["balanced"]
    assert set(result["models"]) == {"balanced", "floor", "ceiling", "opus-only-fails"}
    assert "astra:inclusive_positive_below_4" in result["models"]["floor"]["reason_codes"]
    assert "astra:inclusive_negative_below_4" in result["models"]["ceiling"]["reason_codes"]
    assert result["models"]["opus-only-fails"]["judges"]["astra"]["pass"]
    assert "opus:inclusive_negative_below_4" in result["models"]["opus-only-fails"]["reason_codes"]
    assert sum(len(model["classifications"]) for model in result["models"].values()) == 192


@pytest.mark.parametrize("positive", [3, 4, 44, 45])
def test_headroom_exact_pooled_count_boundary(positive):
    sample = rows("screen")
    for index, row in enumerate(sample):
        for judge in a.JUDGES:
            structured(row, judge)["inclusive_current_assertion"] = index < positive
    result = a.qualify(sample)["models"]["model-a"]
    assert result["qualified"] is (4 <= positive <= 44)
    assert result["judges"]["astra"]["positive"] == positive


def test_paper_and_explicit_are_not_qualification_inputs():
    sample = rows("screen")
    for row in sample:
        for judge in a.JUDGES:
            row["labels"][judge]["paper"] = None
            structured(row, judge)["explicit_current_assertion"] = None
    assert a.qualify(sample)["eligible_models"] == ["model-a"]
    for row in sample:
        for judge in a.JUDGES:
            row["labels"][judge]["paper"] = row["cell"].startswith("S")
            structured(row, judge)["inclusive_current_assertion"] = None
    assert not a.qualify(sample)["eligible_models"]


@pytest.mark.parametrize("invalid_count,expected", [(4, True), (5, False)])
def test_valid_coherence_denominator_48_for_both_judges(invalid_count, expected):
    sample = rows("screen")
    for row in sample[:invalid_count]:
        structured(row, "opus")["valid_coherent"] = False
    result = a.qualify(sample)["models"]["model-a"]
    assert result["qualified"] is expected
    assert result["judges"]["opus"]["valid_coherent_rate"] == (48 - invalid_count) / 48
    assert result["judges"]["opus"]["missing"] == 0


@pytest.mark.parametrize("missing_count,expected", [(2, True), (3, False)])
def test_missing_threshold_uses_planned_48_and_not_observed(missing_count, expected):
    sample = rows("screen")
    for row in sample[:missing_count]:
        row["labels"]["opus"]["structured"] = None
    result = a.qualify(sample)["models"]["model-a"]
    assert result["qualified"] is expected
    assert result["judges"]["opus"]["missing_rate"] == missing_count / 48
    assert result["judges"]["opus"]["inclusive_missing"] == missing_count
    assert result["inventory"]["complete"]


@pytest.mark.parametrize("flag", a.FAILURE_FLAGS)
def test_failure_union_excess_retained_but_never_an_exclusion(flag):
    sample = rows("screen")
    mismatched = [row for row in sample if row["cell"] in ("SH", "HS")]
    for row in mismatched[:3]:
        structured(row, "opus")[flag] = True
    partial = a.qualify(sample)
    assert partial["models"]["model-a"]["judges"]["opus"]["failure_excess"] == 3 / 24
    assert not partial["models"]["model-a"]["judges"]["opus"]["failure_excess_diagnostic"]["at_least_threshold"]
    structured(mismatched[3], "opus")[flag] = True
    result = a.qualify(sample)["models"]["model-a"]
    assert result["judges"]["opus"]["failure_excess"] == 4 / 24
    assert result["judges"]["opus"]["failure_excess_diagnostic"] == {
        "threshold": 0.15, "at_least_threshold": True, "used_for_qualification": False}
    assert all("failure_excess" not in reason for reason in result["reason_codes"])
    # Refusals still trigger the separate missing-label rule, not a conflict gate.
    assert result["qualified"] is (flag != "refusal")


def test_failure_union_counts_once_and_excess_is_directional():
    sample = rows("screen")
    for row in [row for row in sample if row["cell"] in ("SS", "HH")][:6]:
        for flag in ("malformed", "reported_context_conflict"):
            structured(row)[flag] = True
    result = a.qualify(sample)["models"]["model-a"]
    assert result["qualified"]
    assert result["judges"]["astra"]["failure_excess"] == -6 / 24
    assert result["judges"]["astra"]["failure_union"]["matched"]["positive"] == 6


def test_unknown_failure_flag_reports_bounds_not_zero_or_fabricated_breach():
    sample = rows("screen")
    mismatched = [row for row in sample if row["cell"] in ("SH", "HS")]
    for row in mismatched[:3]:
        structured(row)["reported_context_conflict"] = True
    structured(mismatched[3])["reported_context_conflict"] = None
    result = a.qualify(sample)["models"]["model-a"]
    judge = result["judges"]["astra"]
    assert judge["failure_excess"] is None
    assert judge["failure_excess_bounds"] == [3 / 24, 4 / 24]
    assert judge["missing"] == 1
    assert judge["failure_excess_diagnostic"]["at_least_threshold"] is None
    assert result["qualified"]


@pytest.mark.parametrize("change", ["absent", "duplicate", "duplicate_slot", "duplicate_id",
                                    "wrong_cell", "wrong_block", "invalid_id", "invalid_block", "extra"])
def test_malformed_inventory_fails_without_deduplication(change):
    sample = rows("screen")
    if change == "absent":
        sample.pop()
    elif change == "duplicate":
        sample[-1] = deepcopy(sample[0])
    elif change == "duplicate_slot":
        sample[-1]["block"], sample[-1]["cell"] = sample[0]["block"], sample[0]["cell"]
    elif change == "duplicate_id":
        sample[-1]["id"] = sample[0]["id"]
    elif change == "wrong_cell":
        sample[-1]["cell"] = "NS"
    elif change == "wrong_block":
        sample[-1]["block"] = 999
    elif change == "invalid_id":
        sample[-1]["id"] = None
    elif change == "invalid_block":
        sample[-1]["block"] = True
    elif change == "extra":
        sample.append(deepcopy(sample[0]))
    result = a.qualify(sample)
    assert not result["inventory_valid"]
    assert result["eligible_models"] == []
    assert "malformed_inventory" in result["models"]["model-a"]["reason_codes"]
    assert result["models"]["model-a"]["classifications"] == sample
    json.dumps(result, allow_nan=False)


def test_analysis_rejects_ambiguous_inventory_but_preserves_every_record():
    sample = rows()
    sample[-1] = deepcopy(sample[0])
    result = a.analyze(sample, "main")["models"]["model-a"]
    assert result["inventory"]["status"] == "invalid"
    assert result["judges"] == {}
    assert result["classifications"] == sample


def test_more_than_four_models_cannot_claim_eight_contrast_family():
    result = a.analyze(rows(models=tuple(f"model-{i}" for i in range(5))), "main")
    assert not result["primary_family"]["valid_model_count"]
    for model in result["models"]:
        assert "familywise_hoeffding_95" not in contrast(result, model=model)


@pytest.mark.parametrize("status", a.SUCCESS_STATUSES)
def test_declared_success_statuses(status):
    sample = rows("screen")
    for row in sample:
        row["status"] = status
    assert a.qualify(sample)["eligible_models"] == ["model-a"]


@pytest.mark.parametrize("response", [None, "", "   "])
def test_empty_responses_not_counted_as_labelled_negatives(response):
    sample = rows("screen")
    for row in sample:
        row["response"] = response
    result = a.qualify(sample)["models"]["model-a"]["judges"]["astra"]
    assert result["positive"] == result["negative"] == 0
    assert result["missing"] == 48


def test_no_mutation_json_serializable_and_all_raw_classifications_retained():
    sample = rows("screen")
    structured(sample[0])["arbitrary_secondary"] = {"raw": [True, None, "quoted"]}
    original = deepcopy(sample)
    result = a.analyze(sample, "screen")
    assert sample == original
    assert result["models"]["model-a"]["classifications"] == original
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    result["models"]["model-a"]["classifications"][0]["response"] = "modified copy"
    assert sample == original


def test_unassigned_and_empty_input_cannot_establish_qualification():
    assert not a.qualify([])["inventory_valid"]
    sample = rows("screen")
    bad = {"id": "orphan", "model": None}
    sample.append(bad)
    result = a.qualify(sample)
    assert not result["eligible_models"]
    assert result["unassigned_records"] == [bad]


def test_phase_must_be_explicit():
    with pytest.raises(ValueError, match="phase"):
        a.analyze(rows(), "pilot")


@pytest.mark.parametrize("phase,count", [("screen", 6), ("main", 16)])
def test_both_wording_strata_reported_without_separate_gates(phase, count):
    sample = rows(phase, value=lambda block, cell: block < count)
    result = a.analyze(sample, phase)
    strata = result["models"]["model-a"]["wording_strata"]
    assert set(strata) == {"a", "b"}
    for family, expected in (("a", 1), ("b", 0)):
        stratum = strata[family]
        assert stratum["status"] == "complete"
        assert stratum["planned_blocks"] == stratum["observed_blocks"] == count
        for judge in a.JUDGES:
            for measurement in a.ENDPOINTS:
                summary = stratum["judges"][judge][measurement]
                assert summary["role"] == "descriptive_only"
                assert summary["cells"]["SS"]["proportion"] == expected
                assert summary["contrasts"]["instruction_minus_transcript"]["complete_blocks"] == count
                assert "familywise_hoeffding_95" not in summary["contrasts"]["instruction_minus_transcript"]
    if phase == "screen":
        assert result["qualification"]["eligible_models"] == ["model-a"]


def test_wording_heterogeneity_not_hidden_by_pooled_average():
    sample = rows(value=lambda block, cell: (cell in ("SH", "NS")) if block < 16
                  else cell in ("HS", "NH"))
    result = a.analyze(sample, "main")
    strata = result["models"]["model-a"]["wording_strata"]
    for name in a.PRIMARY_CONTRASTS:
        assert contrast(result, name)["complete_case_mean"] == 0
        assert strata["a"]["judges"]["astra"][a.ENDPOINTS[0]]["contrasts"][name]["complete_case_mean"] == 1
        assert strata["b"]["judges"]["astra"][a.ENDPOINTS[0]]["contrasts"][name]["complete_case_mean"] == -1
        bootstrap = contrast(result, name)["bootstrap_95"]
        # Fixed 16/16 strata make this bootstrap degenerate. An unstratified
        # resample would spuriously vary the prescribed wording allocation.
        assert bootstrap["interval"] == [0, 0]
        assert bootstrap["degenerate"]
        assert bootstrap["stratified_by"] == "family"
        assert bootstrap["complete_blocks_by_family"] == {"a": 16, "b": 16}


def test_wording_missingness_uses_half_design_denominators():
    sample = [row for row in rows() if row["block"] != 0]
    result = a.analyze(sample, "main")
    strata = result["models"]["model-a"]["wording_strata"]
    summary = strata["a"]["judges"]["astra"][a.ENDPOINTS[0]]["contrasts"][a.PRIMARY_CONTRASTS[0]]
    assert summary["planned_blocks"] == 16 and summary["complete_blocks"] == 15
    assert summary["worst_case_mean_bounds"] == [14 / 16, 1]
    assert strata["b"]["observed_blocks"] == 16
    assert strata["b"]["status"] == "complete"


def test_missing_or_inconsistent_wording_is_not_inferred_from_outcomes():
    sample = rows("screen")
    for row in sample:
        row.pop("family")
    result = a.analyze(sample, "screen")
    assert result["qualification"]["eligible_models"] == ["model-a"]
    assert contrast(result)["complete_blocks"] == 12
    assert contrast(result)["bootstrap_95"]["interval"] is None
    assert contrast(result)["bootstrap_95"]["unassigned_complete_blocks"] == 12
    for stratum in result["models"]["model-a"]["wording_strata"].values():
        assert stratum["status"] == "incomplete"
        summary = stratum["judges"]["astra"][a.ENDPOINTS[0]]["contrasts"][a.PRIMARY_CONTRASTS[0]]
        assert summary["complete_case_mean"] is None
        assert summary["worst_case_mean_bounds"] == [-1, 1]


def test_overfull_wording_stratum_cannot_use_smaller_planned_denominator():
    sample = rows()
    for row in sample:
        row["family"] = "a"
    result = a.analyze(sample, "main")
    strata = result["models"]["model-a"]["wording_strata"]
    assert strata["a"]["status"] == "invalid"
    assert strata["a"]["judges"] == {}
    assert contrast(result)["complete_blocks"] == 32


def test_averages_use_complete_pairs_not_unpaired_cell_means():
    sample = rows()
    for row in sample:
        if row["block"] == 1 and row["cell"] in ("SH", "HS"):
            structured(row)["inclusive_current_assertion"] = row["cell"] == "HS"
        if (row["block"], row["cell"]) in ((0, "HS"), (1, "SH")):
            structured(row)["inclusive_current_assertion"] = None
    result = a.analyze(sample, "main")
    summary = contrast(result)
    assert summary["complete_case_mean"] == 1
    assert summary["complete_blocks"] == 30
    cell_summary = endpoint(result)["cells"]
    assert cell_summary["SH"]["proportion"] - cell_summary["HS"]["proportion"] != 1
    assert summary["worst_case_mean_bounds"] == [29 / 32, 31 / 32]


def test_capped_nonempty_answers_are_retained_but_other_failures_are_missing():
    sample = rows("screen")
    for row in sample:
        row["status"] = "incomplete"
        row["cap_hit"] = True
    result = a.analyze(sample, "screen")
    assert result["qualification"]["eligible_models"] == ["model-a"]
    assert contrast(result)["complete_blocks"] == 12
    assert all(row["cap_hit"] for row in result["models"]["model-a"]["classifications"])
    for row in sample:
        row["cap_hit"] = False
    assert contrast(a.analyze(sample, "screen"))["complete_case_mean"] is None


def test_judge_reported_refusals_not_recoded_negative_and_flags_preserved():
    sample = rows("screen")
    for row in sample:
        structured(row)["refusal"] = True
        structured(row)["valid_coherent"] = False
        structured(row)["inclusive_current_assertion"] = False
    result = a.analyze(sample, "screen")
    qualified = result["qualification"]["models"]["model-a"]["judges"]["astra"]
    assert qualified["negative"] == qualified["positive"] == 0
    assert qualified["missing"] == 48
    assert qualified["failure_union"]["matched"]["positive"] == 24
    assert contrast(result)["complete_case_mean"] is None
    assert endpoint(result)["missingness"][0]["reason"] == "judge_reported_refusal"
    assert all(structured(row)["refusal"] is True
               for row in result["models"]["model-a"]["classifications"])
    assert contrast(result, judge="opus")["complete_blocks"] == 12


def test_main_quality_diagnostics_show_conflicts_and_union_in_both_strata():
    sample = rows()
    for row in sample:
        if row["cell"] in ("SH", "HS"):
            structured(row)["reported_context_conflict"] = True
    result = a.analyze(sample, "main")["models"]["model-a"]
    for view in (result, *result["wording_strata"].values()):
        flags = view["diagnostics"]["astra"]["flags"]
        assert flags["valid_coherent"]["cells"]["SH"]["proportion"] == 1
        for flag in ("reported_context_conflict", "failure_union"):
            assert flags[flag]["cells"]["SH"]["proportion"] == 1
            assert flags[flag]["cells"]["SS"]["proportion"] == 0
            assert flags[flag]["incongruent_minus_congruent"]["complete_case_mean"] == 1
            assert "familywise_hoeffding_95" not in flags[flag]["incongruent_minus_congruent"]
