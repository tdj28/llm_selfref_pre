"""Display-only checks using historical gates, never synthetic GPU outcomes."""
import csv
import json
from pathlib import Path

import pytest

from experiments.sae_assay_repair.figures import geometry, mundane_controls, render, tables


def fixture_run(tmp_path):
    old = Path("data/sae_assay_diagnostic/stage1_20260930/target-selection.json")
    selection = json.loads(old.read_text())
    run = tmp_path / "input"
    run.mkdir()
    payload = {"calibration": {
        "literal": {"selection": selection},
        "decoder_span": {"unavailable": "TEST_FIXTURE_NOT_RUN"},
        "encoder_min_norm": {"unavailable": "TEST_FIXTURE_NOT_RUN"},
    }}
    (run / "target-final.json").write_text(json.dumps(payload))
    return run, old


def test_tables_preserve_missing_operators(tmp_path):
    run, _ = fixture_run(tmp_path)
    gates, coordinates = tables(run)
    assert len(gates) == 6
    assert len(coordinates) == 24
    assert {r["operator"] for r in coordinates} == {"literal"}
    assert all(r["status"] == "TEST_FIXTURE_NOT_RUN"
               for r in gates if r["operator"] != "literal")
    assert {r["direction"] for r in coordinates} == {"suppression", "amplification"}


def test_render_preserves_inputs_and_refuses_overwrite(tmp_path):
    run, old = fixture_run(tmp_path)
    before = {p: p.read_bytes() for p in (old, run / "target-final.json")}
    out = tmp_path / "display"
    render(run, out)
    for name in ("coordinate-delivery", "delivery-constraints"):
        for suffix in ("png", "svg", "pdf"):
            assert (out / f"{name}.{suffix}").stat().st_size > 1000
    assert len(list(csv.DictReader((out / "coordinates.csv").open()))) == 24
    assert all(p.read_bytes() == raw for p, raw in before.items())
    with pytest.raises(FileExistsError):
        render(run, out)


def test_geometry_has_separate_display_and_rejects_wrong_shape(tmp_path):
    value = {"feature_ids": [1, 2], "encoder_decoder_response": [[.8, .1], [.1, .9]],
             "encoder_gram": [[1., .1], [.1, 1.2]]}
    geometry(value, tmp_path)
    assert (tmp_path / "coordinate-geometry.svg").stat().st_size > 1000
    value["encoder_gram"] = [[1.]]
    with pytest.raises(ValueError, match="Invalid geometry"):
        geometry(value, tmp_path)


def test_mundane_control_plot_is_separate(tmp_path):
    report = {"context_activity": {name: {"positions": 10, "positive": i, "texts": 1}
              for i, name in enumerate(("raw", "instruction_raw", "assistant_chat", "user_chat"))},
              "formatting": {"zero": {"n": 20, "strict_json": 0},
                             "instruction": {"n": 20, "strict_json": 20}}}
    mundane_controls(report, tmp_path)
    assert (tmp_path / "mundane-controls.svg").stat().st_size > 1000
