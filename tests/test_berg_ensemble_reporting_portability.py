import math

import pytest

from experiments.berg_ensemble_diagnostics import compare_reductions


def test_exact_and_recorded_roundoff():
    frozen = {"rate": .5, "n": 50, "verdict": "inconclusive", "bounds": [-.2, .3]}
    assert compare_reductions(frozen, frozen)["exact"]
    local = {**frozen, "bounds": [-.2, math.nextafter(.3, 1.)]}
    result = compare_reductions(frozen, local)
    assert not result["exact"]
    assert result["differences"][0]["path"] == "/bounds/1"
    assert 0 < result["maximum_absolute_error"] < 1e-15
    assert frozen["bounds"] == [-.2, .3]


@pytest.mark.parametrize("changed", [
    {"rate": .50000001, "n": 50, "verdict": "inconclusive", "bounds": [-.2, .3]},
    {"rate": .5, "n": 49, "verdict": "inconclusive", "bounds": [-.2, .3]},
    {"rate": .5, "n": 50., "verdict": "inconclusive", "bounds": [-.2, .3]},
    {"rate": .5, "n": 50, "verdict": "recovered", "bounds": [-.2, .3]},
    {"rate": .5, "n": 50, "verdict": "inconclusive", "bounds": [-.2]},
    {"rate": .5, "n": 50, "bounds": [-.2, .3]},
    {"rate": float("nan"), "n": 50, "verdict": "inconclusive", "bounds": [-.2, .3]},
])
def test_non_roundoff_drift_rejected(changed):
    frozen = {"rate": .5, "n": 50, "verdict": "inconclusive", "bounds": [-.2, .3]}
    with pytest.raises(ValueError):
        compare_reductions(frozen, changed)
