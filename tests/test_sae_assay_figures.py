import json
from pathlib import Path

import pytest

from experiments.sae_assay_diagnostic.figures import baseline, calibration


def test_calibration_display_preserves_frozen_input(tmp_path):
    source = Path("data/sae_assay_diagnostic/stage1_20260930/target-selection.json")
    raw = source.read_bytes()
    calibration(json.loads(raw), tmp_path)
    assert source.read_bytes() == raw
    assert all((tmp_path / ("target-calibration" + suffix)).stat().st_size > 1000
               for suffix in (".png", ".svg", ".pdf"))
    with pytest.raises(FileExistsError):
        calibration(json.loads(raw), tmp_path)


def test_baseline_does_not_impute_unlabeled_rows(tmp_path):
    with pytest.raises(ValueError, match="No labeled core"):
        baseline({"baselines": [{"phase": "core", "labeled_n": 0}]}, tmp_path)


def test_baseline_displays_intervals_and_counts(tmp_path):
    baseline({"baselines": [{"phase": "core", "labeled_n": 80, "positive_n": 40,
                            "reader": "local_paper", "rate": .5, "lower95": .39,
                            "upper95": .61}]}, tmp_path)
    assert (tmp_path / "core-baseline-readers.png").is_file()
