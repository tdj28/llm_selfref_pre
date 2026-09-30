import hashlib
import json

import pytest

from experiments.sae_assay_repair import reproduce_feasibility as reproduction


def test_bundle_hashes_code_and_outputs_without_modifying_inputs(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "raw").write_text("unchanged")
    out = tmp_path / "result"
    calls = []

    def analyze(run, destination):
        assert run == source
        destination.mkdir(exist_ok=False)
        (destination / "SUMMARY.json").write_text('{}\n')
        return {"source_release_manifest_sha256": "c"*64, "qualification_status": "NOT_TESTED"}

    def render(summary, destination):
        assert summary == out / "SUMMARY.json"
        destination.mkdir(exist_ok=False)
        (destination / "figure.svg").write_text("synthetic fixture")

    monkeypatch.setattr(reproduction, "analyze", analyze)
    monkeypatch.setattr(reproduction, "report", lambda run: {"counts": {"raw_rows": 4}})
    monkeypatch.setattr(reproduction, "render", render)
    monkeypatch.setattr(reproduction, "verify_manifest", lambda run: calls.append(run))
    result = reproduction.build(source, out)
    assert result["new_spending_usd"] == 0 and result["qualification_status"] == "NOT_TESTED"
    assert calls == [source]
    assert (source / "raw").read_text() == "unchanged"
    manifest = json.loads((out / "RELEASE_MANIFEST.json").read_text())
    assert manifest["timing"] == "post_outcome_exploratory"
    assert len(manifest["files"]) == result["files"] - 1
    for item in manifest["files"]:
        raw = (out / item["path"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(raw).hexdigest()
        assert item["bytes"] == len(raw)
    with pytest.raises(FileExistsError):
        reproduction.build(source, out)


def test_plot_declares_conditional_scope_and_shows_missing_feature(tmp_path):
    from experiments.sae_assay_repair.figure_feasibility import render
    root = tmp_path / "SUMMARY.json"
    features = [{"predicted_median_ratio": .25, "window_all_active_median": 1.,
                 "window_dispatched_median": None, "active_nonspecial_positions": 16,
                 "window_dispatched_active_positions": 0} for _ in range(6)]
    bounds = [{"eligible_nonspecial_positions": 20, "upper_bound_on_efficacious_positions": 8} for _ in range(6)]
    split = {"old_amplification_relaxed_inequalities": {str(d): {"per_feature_necessary_bounds": bounds} for d in (.5, 1.)},
             "active_support_075_cap004": {m: {"feature_surrogates": features} for m in ("suppression", "amplification")}}
    root.write_text(json.dumps({"feature_ids": [30032,58667,22004,30686,41533,23893],
                               "splits": {s: split for s in ("calibration", "validation")}}))
    destination = tmp_path / "figures"
    render(root, destination)
    assert len(list(destination.iterdir())) == 6
    text = (destination / "prototype-coverage-tradeoff.svg").read_text()
    assert "not model forwards" in text and "zero window-dispatched" in text
