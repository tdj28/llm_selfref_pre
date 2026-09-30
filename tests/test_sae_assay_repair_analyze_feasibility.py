import json

import numpy as np
import pytest

from experiments.sae_assay_repair import analyze_feasibility as analysis


def test_relaxed_projection_does_not_force_ineligible_coordinates():
    p = np.array([[-2., 3.], [1., 1.]])
    z = np.maximum(p, 0)
    q = np.array([2., 2.])
    report = analysis.opportunity_projection(np.eye(2), p, z, q, .5)
    np.testing.assert_array_equal(report["eligible"], [[True, False], [True, True]])
    np.testing.assert_allclose(report["norm"], [2.5, np.sqrt(.125)])


def test_median_necessary_bound_grants_all_global_exceptions():
    # 21 of 100 local opportunities fit. Grant all 5/100 global exceptions.
    need = np.array([.01]*21 + [.2]*79)
    report = analysis.single_feature_bound(need, np.ones(100, bool), np.ones(100),
                                           np.ones(100, bool), 100)
    assert report["upper_bound_on_efficacious_positions"] == 26
    assert report["minimum_positions_needed_for_median"] == 50
    assert report["linear_surrogate_median_impossible"]
    # A shared denominator can be much larger than this feature's opportunities.
    generous = analysis.single_feature_bound(need, np.ones(100, bool), np.ones(100),
                                             np.ones(100, bool), 2000)
    assert not generous["linear_surrogate_median_impossible"]


def test_empty_and_even_median_bound_is_not_sufficiency():
    zero = analysis.single_feature_bound(np.array([0.]), np.array([False]), np.array([1.]),
                                         np.array([True]), 1)
    assert not zero["linear_surrogate_median_impossible"]
    even = analysis.single_feature_bound(np.array([.01, 1.]), np.ones(2, bool), np.ones(2),
                                         np.ones(2, bool), 2)
    assert not even["linear_surrogate_median_impossible"]
    assert even["minimum_positions_needed_for_median"] == 1


def test_analyzer_writes_separate_outputs_and_labels_surrogates(tmp_path, monkeypatch):
    root = tmp_path / "source"
    (root / "rows").mkdir(parents=True)
    (root / "RELEASE_MANIFEST.json").write_text('{}\n')
    clean = []
    for split in ("calibration", "validation"):
        row = {"id": "clean-" + split, "text_id": split, "split": split, "corpus": "fixture",
               "result": {"token_ids": [1, 2]}}
        p = np.array([[-1., -2.], [1., .5]])
        clean.append((row, p, np.maximum(p, 0), np.array([10., 10.]), np.array([False, True])))
        (root / "rows" / (row["id"] + ".json")).write_text(json.dumps(row))
    (root / "rows/qualification-live.json").write_text('{}\n')
    (root / "target-q90.json").write_text('{}\n')
    checks = []
    monkeypatch.setattr(analysis, "load_clean", lambda run: ({"freeze_commit": "a"*40},
                       [5, 6], np.eye(2), np.array([2., 2.]), clean))
    monkeypatch.setattr(analysis, "verify_manifest", lambda run: checks.append(run))
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    out = tmp_path / "result"
    result = analysis.analyze(root, out)
    assert not result["fresh_validation_available"]
    assert result["qualification_status"].startswith("NOT_TESTED")
    assert checks == [root]
    assert set(p.name for p in out.iterdir()) == {"INPUTS.json", "SUMMARY.json", "necessary_bounds.csv",
                                                "prototype_coordinates.csv", "prototype_positions.csv"}
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        analysis.analyze(root, out)
    with pytest.raises(ValueError):
        analysis.analyze(root, root / "illegal")
