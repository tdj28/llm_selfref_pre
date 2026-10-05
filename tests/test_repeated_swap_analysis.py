"""Synthetic truths and missing-data controls, never collected target outputs."""

from copy import deepcopy
import itertools
import json
import math
import random
from statistics import fmean

import pytest

from experiments.repeated_swap import analysis as a, protocol as p


def rows(value=None):
    value = value or (lambda spec: spec["cell"] in ("SS", "SH"))
    result = []
    for block in p.inventory("main"):
        for spec in block["finals"]:
            label = bool(value(spec))
            structured = {"inclusive_current_assertion": label, "explicit_current_assertion": label,
                          "refusal": False, "malformed": False, "valid_coherent": True,
                          "reported_context_conflict": False}
            result.append({**deepcopy(spec), "response": "Synthetic offline response.",
                           "status": "ok", "cap_hit": False,
                           "labels": {j: {"paper": label, "structured": deepcopy(structured)} for j in a.JUDGES}})
    return result


def endpoint(result, model="gemini", judge="astra", name="inclusive_current_assertion"):
    return result["models"][model]["judges"][judge][name]


def contrast(result, name="instruction_minus_transcript", **kwargs):
    return endpoint(result, **kwargs)["contrasts"][name]


@pytest.fixture(scope="module")
def truth():
    return a.analyze(rows())


def test_primary_truth_all_four_rates_and_mandatory_measurements(truth):
    assert truth["inventory"]["observed_records"] == 768
    assert truth["primary_family_size"] == 2
    for model in p.MODELS:
        for judge in a.JUDGES:
            assert set(truth["models"][model]["judges"][judge]) == set(a.ENDPOINTS)
            for name in a.ENDPOINTS:
                summary = endpoint(truth, model, judge, name)
                for cell in p.CELLS:
                    assert summary["cells"][cell]["proportion"] == int(cell in ("SS", "SH"))
                    assert summary["cells"][cell]["planned"] == summary["cells"][cell]["observed"] == 96
                for key, expected in {"instruction": 1, "transcript": 0,
                                      "instruction_minus_transcript": 1, "interaction": 0}.items():
                    assert summary["contrasts"][key]["complete_case_mean"] == pytest.approx(expected)
                for family in ("a", "b"):
                    for variance in summary["wording_strata"][family]["variance"].values():
                        assert variance["complete_requests"] == 16
                        assert variance["planned_answers"] == 48
                        assert variance["W"] == variance["B"] == 0


def test_intervals_use_32_blocks_and_two_primary_comparisons(truth):
    primary = contrast(truth)
    radius = 2 * math.sqrt(math.log(80) / (2 * 32))
    assert primary["complete_blocks"] == primary["planned_blocks"] == 32
    assert primary["bootstrap"]["confidence"] == 0.975
    assert primary["bootstrap"]["resamples"] == 10000
    assert primary["bootstrap"]["seed"] == 20261004
    assert primary["complete_case_hoeffding"] == pytest.approx([1 - radius, 1])
    assert primary["worst_case_hoeffding"] == primary["complete_case_hoeffding"]
    assert primary["bootstrap"]["degenerate"]
    assert contrast(truth, judge="opus")["bootstrap"]["confidence"] == 0.95
    assert not contrast(truth, name="interaction")["primary"]


def test_factorial_binary_truths_and_interaction_support():
    patterns = list(itertools.product((False, True), repeat=4))
    sample = rows(lambda s: patterns[(s["block"] - 1) % 16][list(p.CELLS).index(s["cell"])])
    result = a.analyze(sample)
    for index in range(32):
        ss, sh, hs, hh = map(int, patterns[index % 16])
        for name, expected in {"instruction": (ss + sh - hs - hh) / 2,
                               "transcript": (ss + hs - sh - hh) / 2,
                               "instruction_minus_transcript": sh - hs,
                               "interaction": ss - sh - hs + hh}.items():
            assert contrast(result, name)["per_block"][index]["value"] == pytest.approx(expected)
    assert contrast(result, "interaction")["support"] == [-2, 2]


def test_shared_source_pairing_is_not_independent_cell_bootstrap():
    result = a.analyze(rows(lambda s: s["block"] % 4 in (0, 1)))
    primary = contrast(result)
    assert primary["bootstrap"]["interval"] == [0, 0]
    assert primary["complete_case_mean"] == 0
    assert endpoint(result)["cells"]["SH"]["proportion"] == 0.5


def test_stratified_not_unstratified_bootstrap_with_fixed_family_weights():
    result = a.analyze(rows(lambda s: (s["cell"] == "SH") if s["family"] == "a" else s["cell"] == "HS"))
    primary = contrast(result)
    assert primary["complete_case_mean"] == 0
    assert primary["bootstrap"]["interval"] == [0, 0]
    assert primary["complete_blocks_by_family"] == {"a": 16, "b": 16}


def test_bootstrap_matches_fixed_seed_and_97_5_percentiles():
    groups = (tuple(float(i % 3 - 1) for i in range(16)), tuple(i / 15 for i in range(16)))
    rng = random.Random(20261004)
    reference = sorted(fmean(fmean(rng.choices(g, k=len(g))) for g in groups) for _ in range(10000))
    expected = (a._quantile(reference, 0.0125), a._quantile(reference, 0.9875))
    assert a._bootstrap(groups, 0.025) == expected
    assert a._bootstrap(groups, 0.025) != a._bootstrap(groups, 0.05)


def test_negative_between_estimates_are_preserved_not_population_claims():
    result = a.analyze(rows(lambda s: s["draw"] == 1))
    variance = endpoint(result)["wording_strata"]["a"]["variance"]["SH"]
    assert variance["W"] == pytest.approx(1 / 3)
    assert variance["request_means_sample_variance"] == 0
    assert variance["B"] == pytest.approx(-1 / 9)
    assert variance["negative_B_is_population_negative_variance"] is False
    assert endpoint(result)["cells"]["SH"]["proportion"] == pytest.approx(1 / 3)
    pooled = endpoint(result)["variance"]["SH"]
    assert pooled["W"] == pytest.approx(1 / 3)
    assert pooled["B"] == pytest.approx(-1 / 9)
    assert pooled["bootstrap"]["B_interval"] == pytest.approx([-1 / 9, -1 / 9])
    assert pooled["bootstrap"]["W_interval"] == pytest.approx([1 / 3, 1 / 3])


def test_between_source_variance_uses_unbiased_request_denominator():
    requests = [[False] * 3] * 8 + [[True] * 3] * 8
    value = a.variance_components(requests)
    assert value["W"] == 0
    assert value["B"] == pytest.approx(4 / 15)


def test_variance_missing_requests_and_small_n_are_descriptive():
    requests = [[True, False, False]] * 15 + [[True, None, False]]
    value = a.variance_components(requests)
    assert value["complete_requests"] == 15 and value["incomplete_requests"] == 1
    assert value["missing_answers"] == 1
    assert value["B"] == pytest.approx(-1 / 9)
    assert "missingness" in value["scope"]
    assert a.variance_components([[True, False, False]])["B"] is None
    assert a.variance_components([[None] * 3] * 16)["W"] is None
    for bad in ([[True, False]], [[1, False, False]]):
        with pytest.raises(ValueError):
            a.variance_components(bad)


def test_one_missing_draw_retains_planned_denominator_and_paired_complete_cases():
    sample = rows()
    removed = next(r for r in sample if r["model"] == "gemini" and r["block"] == 1 and r["cell"] == "SH")
    sample.remove(removed)
    result = a.analyze(sample)
    primary = contrast(result)
    assert result["inventory"]["missing_records"] == 1
    assert primary["complete_blocks"] == 31
    assert primary["complete_blocks_by_family"] == {"a": 15, "b": 16}
    assert primary["complete_case_mean"] == pytest.approx(1)
    assert primary["worst_case_mean_bounds"] == pytest.approx([95 / 96, 1])
    cell = endpoint(result)["cells"]["SH"]
    assert (cell["planned"], cell["observed"], cell["missing"]) == (96, 95, 1)
    assert cell["negative"] == 0


def test_missingness_does_not_reweight_wording_families():
    sample = rows(lambda s: s["family"] == "a" and s["cell"] == "SH")
    sample = [r for r in sample if not (r["model"] == "gemini" and r["family"] == "a" and r["block"] <= 16)]
    primary = contrast(a.analyze(sample))
    assert primary["complete_blocks_by_family"] == {"a": 8, "b": 16}
    assert primary["complete_case_mean"] == pytest.approx(0.5)
    assert primary["complete_case_mean"] != pytest.approx(8 / 24)
    assert primary["worst_case_mean_bounds"] == pytest.approx([0, 0.5])


def test_pooled_variance_equal_families_preserves_whole_request_draws():
    result = a.analyze(rows(lambda s: s["family"] == "a" and s["draw"] == 1))
    pooled = endpoint(result)["variance"]["SH"]
    assert pooled["W"] == pytest.approx(1 / 6)
    assert pooled["B"] == pytest.approx(-1 / 18)
    assert pooled["bootstrap"]["W_interval"] == pytest.approx([1 / 6, 1 / 6])
    assert pooled["bootstrap"]["B_interval"] == pytest.approx([-1 / 18, -1 / 18])
    assert pooled["bootstrap"]["sampling_unit"] == "source_block_with_all_three_draws"


def test_missing_family_and_empty_study_never_become_zero_effect():
    partial = [r for r in rows() if r["family"] == "a"]
    result = a.analyze(partial)
    assert contrast(result)["complete_case_mean"] is None
    assert contrast(result)["bootstrap"]["interval"] is None
    empty = a.analyze([])
    assert set(empty["models"]) == {"gemini", "opus"}
    assert empty["inventory"]["missing_records"] == 768
    for model in p.MODELS:
        assert contrast(empty, model=model)["worst_case_mean_bounds"] == pytest.approx([-1, 1])
        assert contrast(empty, model=model)["complete_case_mean"] is None
        assert endpoint(empty, model)["cells"]["SS"]["missing"] == 96


@pytest.mark.parametrize("failure", ["empty", "status", "refusal", "nonboolean", "no_judge"])
def test_missing_or_invalid_measurements_are_not_negative(failure):
    sample = rows()
    for row in sample:
        if failure == "empty":
            row["response"] = " "
        elif failure == "status":
            row["status"] = "failed"
        elif failure == "refusal":
            row["labels"]["astra"]["structured"]["refusal"] = True
        elif failure == "nonboolean":
            row["labels"]["astra"]["structured"]["inclusive_current_assertion"] = 0
        else:
            row["labels"].pop("astra")
    result = a.analyze(sample)
    cell = endpoint(result)["cells"]["SH"]
    assert cell["positive"] == cell["negative"] == 0
    assert cell["missing"] == 96
    assert contrast(result)["worst_case_mean_bounds"] == pytest.approx([-1, 1])
    if failure not in {"empty", "status"}:
        assert contrast(result, judge="opus")["complete_blocks"] == 32


def test_capped_nonempty_and_conflict_labels_stay_observed_without_selection():
    sample = rows()
    for row in sample:
        row.update(status="incomplete", cap_hit=True)
        row["labels"]["astra"]["structured"]["reported_context_conflict"] = True
    result = a.analyze(sample)
    assert contrast(result)["complete_blocks"] == 32
    assert all(r["cap_hit"] for r in result["models"]["gemini"]["classifications"])


@pytest.mark.parametrize("field,value", [("model", "foreign"), ("family", "b"), ("draw", 9),
    ("draw", True), ("request_id", "other-request"), ("source_id", "old-source"),
    ("block", 99), ("cell", "NS"), ("phase", "screen"), ("instruction", "neutral")])
def test_identity_tampering_rejected(field, value):
    sample = rows()
    index = next(i for i, r in enumerate(sample) if r["family"] == "a")
    sample[index][field] = value
    with pytest.raises(ValueError, match="specification"):
        a.analyze(sample)


def test_duplicate_foreign_and_nonfinite_records_rejected():
    sample = rows()
    with pytest.raises(ValueError, match="Duplicate"):
        a.analyze([*sample, sample[0]])
    sample[0]["id"] = "foreign"
    with pytest.raises(ValueError, match="foreign"):
        a.analyze(sample)
    sample = rows()
    sample[0]["untrusted_metric"] = float("nan")
    with pytest.raises(ValueError):
        a.analyze(sample)
    with pytest.raises(ValueError, match="main"):
        a.analyze([], "screen")


def test_order_invariance_no_mutation_and_json_output():
    sample = rows(lambda s: (s["block"] + s["draw"]) % 3 == 0)
    original = deepcopy(sample)
    first = a.analyze(sample)
    assert sample == original
    random.Random(91).shuffle(sample)
    assert a.analyze(sample) == first
    assert json.loads(json.dumps(first, allow_nan=False)) == first


def test_exact_text_triplets_disambiguate_judge_variation_without_calls():
    sample = rows(lambda s: s["draw"] == 1)
    for row in sample:
        if row["model"] == "gemini" and row["block"] == 1 and row["cell"] == "SS":
            row["response"] += " " * row["draw"]
        if row["model"] == "gemini" and row["block"] == 1 and row["cell"] == "SH" and row["draw"] == 1:
            row["response"] = None
    result = a.analyze(sample)
    diagnostic = result["models"]["gemini"]["response_agreement"]
    assert diagnostic["planned_requests"] == 128
    assert diagnostic["complete_text_requests"] == 127
    assert diagnostic["identical_triplets"] == 126
    assert diagnostic["unique_content_counts_complete_requests"] == {"1": 126, "3": 1}
    for judge in a.JUDGES:
        for endpoint_name in a.ENDPOINTS:
            labels = diagnostic["identical_text_label_disagreement"][judge][endpoint_name]
            assert labels == {"eligible_requests": 126, "disagreeing_requests": 126}
    missing = next(r for r in diagnostic["requests"] if r["block"] == 1 and r["cell"] == "SH")
    assert missing["identical_three"] is None and missing["unique_content_count"] == 1
