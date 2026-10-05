"""Offline interval, missingness, stratification and prospective-power checks."""
import itertools
import hashlib
import json

import numpy as np
import pytest
from scipy.stats import beta

from experiments.berg_dose_ladder import inference as inf
from experiments.berg_dose_ladder import power


def labels_from_differences(differences):
    pairs = {-1: (0, 1), 0: (0, 0), 1: (1, 0)}
    return tuple(map(list, zip(*(pairs[d] for d in differences))))


def controls(differences):
    pairs = [labels_from_differences(ds) for ds in differences]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def test_directional_alpha_and_complete_agreement():
    result = inf.paired_bounds([1]*96, [1]*96)
    assert result["alpha"] == .025
    assert result["component_tail"] == .0125
    assert result["two_sided_confidence"] == .95
    assert result["joint_D_S_coverage"] is False
    assert result["bounds"] == pytest.approx([-(1-.0125**(1/96)), 1-.0125**(1/96)])
    assert result["identification_bounds"] == [0., 0.]
    assert result["complete_pairs"] == 96
    assert result["counts"]["complete_agreements"] == 96
    assert result["upper"] > 0


def test_opposite_effects_and_cp_formula():
    result = inf.paired_bounds([1]*96, [0]*96)
    expected = beta.ppf(.0125, 96, 1)-beta.ppf(1-.0125, 1, 96)
    assert result["lower"] == pytest.approx(expected)
    assert result["upper"] == 1.
    assert result["estimate_complete_pairs"] == 1.
    opposite = inf.paired_bounds([0]*96, [1]*96)
    assert opposite["bounds"] == pytest.approx([-result["upper"], -result["lower"]])
    assert opposite["estimate_complete_pairs"] == -1.


def test_all_missing_keeps_planned_denominator():
    result = inf.paired_bounds([None]*96, [None]*96)
    assert result["n_planned"] == result["missing_pairs"] == 96
    assert result["complete_pairs"] == 0
    assert result["estimate_complete_pairs"] is None
    assert result["bounds"] == result["identification_bounds"] == [-1., 1.]
    assert result["counts"]["positive_possible"] == result["counts"]["negative_possible"] == 96


def test_partial_pairs_have_distinct_definite_and_possible_events():
    result = inf.paired_bounds([1, 0, None, None, 1], [None, None, 0, 1, 0])
    c = result["counts"]
    assert (c["positive_definite"], c["positive_possible"]) == (1, 3)
    assert (c["negative_definite"], c["negative_possible"]) == (0, 2)
    assert result["identification_bounds"] == [-.2, .6]
    assert result["n_planned"] == 5


def test_missingness_never_narrows_exhaustive_two_pair_masks():
    for values in itertools.product((0, 1), repeat=4):
        a, b = list(values[:2]), list(values[2:])
        original = inf.paired_bounds(a, b)
        for mask in itertools.product((False, True), repeat=4):
            missing = [None if hide else value for hide, value in zip(mask, values)]
            result = inf.paired_bounds(missing[:2], missing[2:])
            assert result["lower"] <= original["lower"]+1e-14
            assert result["upper"] >= original["upper"]-1e-14


@pytest.mark.parametrize("alpha", [0, .5, -1, float("nan"), float("inf"), True, "0.025"])
def test_bad_alpha_rejected(alpha):
    with pytest.raises(ValueError, match="alpha"):
        inf.paired_bounds([1], [0], alpha)


@pytest.mark.parametrize("a,b", [([], []), ([1], []), ([1, 0], [0]),
    ([True], [0]), ([1.], [0]), ([2], [0]), ([float("nan")], [0]), ([[1]], [0])])
def test_invalid_labels_and_lengths_rejected(a, b):
    with pytest.raises(ValueError):
        inf.paired_bounds(a, b)


def test_specificity_sign_equal_fixed_weights_and_component_tails():
    minus, plus = controls([[0]*32]*3)
    result = inf.specificity_bounds([1]*96, [0]*96, minus, plus)
    assert result["component_tail"] == .003125
    assert result["two_sided_confidence"] == .95
    tail = .003125
    assert result["bounds"] == pytest.approx(
        [2*tail**(1/96)+tail**(1/32)-2, 2-tail**(1/32)])
    assert result["estimate_complete_pairs"] == 1.
    assert result["identification_bounds"] == [1., 1.]
    assert list(result["panel_weights"].values()) == [1/3]*3
    reverse = inf.specificity_bounds([0]*96, [1]*96, plus, minus)
    assert reverse["bounds"] == pytest.approx([-result["upper"], -result["lower"]])


def test_control_strata_are_not_pooled():
    target = labels_from_differences([0]*18)
    concentrated = controls([[1]*6, [0]*6, [-1]*6])
    mixed = controls([[1, 1, 0, 0, -1, -1]]*3)
    first = inf.specificity_bounds(*target, *concentrated)
    second = inf.specificity_bounds(*target, *mixed)
    assert first["estimate_complete_pairs"] == second["estimate_complete_pairs"] == 0
    assert first["bounds"] != second["bounds"]
    for key in ("lower", "upper"):
        opposite = "upper" if key == "lower" else "lower"
        assert first[key] == pytest.approx(first["target"][key]
            -sum(p[opposite] for p in first["panels"].values())/3)
    assert all(p["n_planned"] == 6 for p in first["panels"].values())


def test_panel_key_order_is_irrelevant_and_json_native():
    minus, plus = controls([[1]*32, [0]*32, [-1]*32])
    a, b = np.ones(96, dtype=int), np.zeros(96, dtype=int)
    first = inf.specificity_bounds(a, b, {3: minus[2], 1: minus[0], 2: minus[1]},
                                  {2: plus[1], 3: plus[2], 1: plus[0]})
    assert first == inf.specificity_bounds(a, b, minus, plus)
    assert json.loads(json.dumps(first, allow_nan=False)) == first
    assert json.loads(json.dumps(inf.paired_bounds(a, b))) == inf.paired_bounds(a, b)


def test_specificity_all_missing_and_monotonicity():
    complete = inf.specificity_bounds([1]*96, [0]*96, [[0]*32]*3, [[0]*32]*3)
    missing = inf.specificity_bounds([None]+[1]*95, [0]*96,
                                    [[None]+[0]*31, [0]*32, [0]*32], [[0]*32]*3)
    assert missing["lower"] <= complete["lower"]
    assert missing["upper"] >= complete["upper"]
    empty = inf.specificity_bounds([None]*96, [None]*96, [[None]*32]*3, [[None]*32]*3)
    assert empty["bounds"] == empty["identification_bounds"] == [-2., 2.]
    assert empty["estimate_complete_pairs"] is None


@pytest.mark.parametrize("minus,plus", [([[0]*32]*2, [[0]*32]*2),
    ({1: [0]*32, 2: [0]*32, 3: [0]*32}, {1: [0]*32, 2: [0]*32, 4: [0]*32}),
    ([[0]*31, [0]*32, [0]*33], [[0]*31, [0]*32, [0]*33]),
    ([[0]*31]*3, [[0]*31]*3),
    ({1: [0], "1": [0], 2: [0]}, {1: [0], "1": [0], 2: [0]})])
def test_bad_strata_rejected(minus, plus):
    with pytest.raises(ValueError):
        inf.specificity_bounds([0]*96, [0]*96, minus, plus)


def test_vectorized_power_bounds_match_public_inference_for_observed_pairs():
    rng = np.random.default_rng(81)
    tables = power.cp_tables()
    for n, alpha in ((96, .025), (96, .025/4), (32, .025/4)):
        counts = np.vstack([np.eye(9, dtype=int)*n, rng.multinomial(n, [1/9]*9, size=25)])
        lower, upper = power.vectorized_bounds(counts, tables[(n, alpha/2)])
        for i, row in enumerate(counts):
            labels = [pair for pair, count in zip(power.OBSERVED_PAIRS, row) for _ in range(count)]
            a, b = zip(*labels)
            direct = inf.paired_bounds(a, b, alpha)
            assert [lower[i], upper[i]] == pytest.approx(direct["bounds"])


def test_observed_pair_law_preserves_declared_mean_and_discordance():
    p = power.observed_pair_probabilities(.3, .5, 0.)
    assert sum(p) == pytest.approx(1.)
    mean = sum(prob*(a-b) for prob, (a, b) in zip(p, power.OBSERVED_PAIRS)
               if a is not None and b is not None)
    q = sum(prob for prob, (a, b) in zip(p, power.OBSERVED_PAIRS)
            if a is not None and b is not None and a != b)
    assert mean == pytest.approx(.3) and q == pytest.approx(.5)
    missing = power.observed_pair_probabilities(.3, .5, .05)
    assert sum(prob for prob, (a, _) in zip(missing, power.OBSERVED_PAIRS) if a is None) == pytest.approx(.05)
    with pytest.raises(ValueError, match="Infeasible"):
        power.observed_pair_probabilities(.8, .2, 0.)


def test_inventory_covers_requested_scenarios_without_hiding_infeasibility():
    rows = power.scenario_inventory()
    assert len({r["id"] for r in rows}) == len(rows)
    assert {r["target_mean"] for r in rows} == {0., .3, .8}
    assert {.2, .5, 1.} <= {r["target_discordance"] for r in rows}
    assert {r["missing_probability_per_label"] for r in rows} == {0., .05}
    assert any(len(set(r["control_means"])) > 1 for r in rows)
    assert any(r["target_mean"] > r["target_discordance"] for r in rows)


def test_simulation_deterministic_json_native_and_no_false_certainty():
    scenario = power.scenario_inventory()[0]
    first = power.simulate_scenario(scenario, seed=12)
    assert first == power.simulate_scenario(scenario, seed=12)
    assert json.loads(json.dumps(first, allow_nan=False)) == first
    decisions = first["decisions"]
    assert sum(decisions[k]["count"] for k in ("large_specific", "exclude_target_gap_0.30", "inconclusive")) == 20000
    assert first["target_bounds"]["median_width"] > 0
    assert decisions["either_directional_error"]["rate"] < .05
    assert decisions["large_specific"]["monte_carlo_95"][1] > 0
    with pytest.raises(ValueError, match="20000"):
        power.simulate_scenario(scenario, repetitions=19999)


def test_cli_requires_explicit_new_output_and_does_not_overwrite(tmp_path, monkeypatch):
    fake = {"report_sha256": "test-only", "experiment_results": False}
    monkeypatch.setattr(power, "build_report", lambda *args: fake)
    path = tmp_path / "plan" / "POWER.json"
    assert power.main(["--out", str(path)]) == 0
    assert json.loads(path.read_text()) == fake
    with pytest.raises(FileExistsError):
        power.main(["--out", str(path)])
    with pytest.raises(SystemExit):
        power.main([])
    with pytest.raises(ValueError, match="20000"):
        power.main(["--out", str(tmp_path / "bad.json"), "--reps", "10"])
    assert not (tmp_path / "bad.json").exists()


def test_report_is_deterministic_source_bound_and_marks_infeasible(monkeypatch):
    inventory = power.scenario_inventory()
    valid = inventory[0]
    invalid = next(s for s in inventory if s["target_mean"] > s["target_discordance"])
    monkeypatch.setattr(power, "scenario_inventory", lambda: [valid, invalid])
    report = power.build_report(seed=82)
    assert report == power.build_report(seed=82)
    assert report["scenarios"][1]["status"] == "infeasible_not_simulated"
    assert "decisions" not in report["scenarios"][1]
    assert report["experiment_results"] is report["execution_authorization"] is False
    assert report["eligibility_gates_simulated"] is False
    assert report["experimental_rows_read"] == []
    assert report["directional_alpha"] == .025
    assert report["target_component_tail"] == .0125
    assert report["specificity_component_tail"] == .003125
    assert report["family_error_bound"] == .05
    assert set(report["source_sha256"]) == {"inference.py", "power.py"}
    digest = report.pop("report_sha256")
    assert hashlib.sha256(power._canonical(report).encode()).hexdigest() == digest


def test_nondefault_alpha_and_cached_bool_count_validation():
    result = inf.paired_bounds([1, 0], [0, 1], alpha=.05)
    assert result["component_tail"] == .025
    inf.cp_limits(1, 2, .025)
    with pytest.raises(ValueError):
        inf.cp_limits(True, 2, .025)
