"""Renderer checks on synthetic rows; no real SAE outcomes or network."""
import pytest

from experiments.sae_assay_replay.analysis import summarize
from experiments.sae_assay_replay.report import figures, tables
from tests.test_sae_assay_replay_analysis import IDS, fixture


def test_table_preserves_exposure_failure_and_intended_denominator():
    rows = [fixture()[0], fixture("val-a", "validation")[0]]
    result = {"pass": True, "complete": True, "summary": summarize(rows, IDS)}
    features, delivery = tables(result, IDS, rows)
    assert len(features) == 8 and len(delivery) == 4
    assert not any(r["exposure_pass"] for r in features)
    assert all(r["native_pass"] for r in features)
    assert {r["native_median"] for r in features} == {.25, 1.0}
    assert not any(r["all_components_pass"] for r in delivery)
    for key in ("pass", "complete"):
        with pytest.raises(ValueError):
            tables({**result, key: False}, IDS, rows)


def test_render_complete_synthetic_tables(tmp_path):
    rows = [fixture()[0], fixture("val-a", "validation")[0]]
    features, delivery = tables({"pass": True, "complete": True,
                                "summary": summarize(rows, IDS)}, IDS, rows)
    figures(features, delivery, IDS, tmp_path)
    assert len(list(tmp_path.iterdir())) == 4
    assert all(p.stat().st_size > 1000 for p in tmp_path.iterdir())


def test_noop_only_summary_renders_unavailable_not_zero(tmp_path):
    rows = [fixture(before=[[0, 0], [0, 0]])[0],
            fixture("val-a", "validation", before=[[0, 0], [0, 0]])[0]]
    features, delivery = tables({"pass": True, "complete": True,
                                "summary": summarize(rows, IDS)}, IDS, rows)
    assert all(r["fidelity_fraction"] is None for r in delivery)
    assert all(r["native_median"] is None for r in features)
    figures(features, delivery, IDS, tmp_path)
    assert len(list(tmp_path.iterdir())) == 4
