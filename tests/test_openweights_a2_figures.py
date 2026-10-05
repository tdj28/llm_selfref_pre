"""Synthetic presentation QA, not validation or publication of study results.

Rendering uses an explicitly substituted synthetic-manifest verifier. A separate
test invokes the real A2 verifier and requires rejection of fabricated input.
"""

import csv
import json
from pathlib import Path
import socket

from PIL import Image
import pytest

from experiments import openweights_a2_figures as figures
from experiments.openrouter_swap.ledger import Halted, _no_symlinks


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl-cache"))
    monkeypatch.setattr(figures, "TITLE", "SYNTHETIC TEST DATA - not study results")


def payload(state="complete"):
    admitted = ["qwen", "mistral"] if state in {"complete", "partial", "admitted-not-started"} else ["qwen"] if state == "single-model" else []
    metadata = {"schema": "openweights-a2-release-v1", "primary_family_size": 4,
                "status": "complete" if state == "complete" else "incomplete", "freeze": "a" * 40,
                "plan_sha256": "b" * 64, "fixtures_pass": True, "admitted_models": admitted,
                "collection_complete": {"screen": state != "startup", "main": state in {"complete", "single-model"}},
                "main_status": "not_run" if state in {"startup", "screen-failed", "admitted-not-started"}
                               else "incomplete" if state == "partial" else "completed",
                "failure_evidence": {"path": "synthetic-prefix", "release_sha256": "c" * 64},
                "fixture_evidence": {"epoch": "A1", "event_count": 53, "sha256": "d" * 64}}
    qualification = {"models": {m: {"qualified": state not in {"startup", "screen-failed"}
                                   and not (state == "single-model" and m == "mistral")} for m in figures.MODELS}}
    reports = {}
    for phase, cells, planned in (("screen", figures.schema.SCREEN_CELLS, 12), ("main", figures.schema.MAIN_CELLS, 32)):
        models = {}
        for model in figures.MODELS:
            unrun = state == "startup" or (phase == "main" and (model not in admitted or state == "admitted-not-started"))
            judges = {}
            for judge in figures.schema.JUDGES:
                judges[judge] = {}
                for endpoint in figures.schema.ENDPOINTS:
                    summaries = {}
                    for index, cell in enumerate(cells):
                        observed = 0 if unrun else planned - (2 if state == "partial" else 0)
                        positive = observed * (index % 5) // 4
                        summaries[cell] = {"planned": planned, "observed": observed, "positive": positive,
                                           "negative": observed - positive, "missing": planned - observed,
                                           "proportion": positive / observed if observed else None}
                    contrasts = {name: {"planned_blocks": planned, "complete_blocks": 0 if unrun else planned - 2,
                                        "missing_blocks": planned if unrun else 2,
                                        "complete_case_mean": None if unrun else .123456789,
                                        "familywise_hoeffding_95": [-1.0, 1.0] if unrun else [-.7312345, .8912345],
                                        "bootstrap_95": {"interval": [.11, .14]}}
                                 for name in figures.schema.PRIMARY_CONTRASTS}
                    judges[judge][endpoint] = {"cells": summaries, "contrasts": contrasts}
            models[model] = {"judges": judges, "classifications": [{"status": "not_generated" if unrun else "ok"}]}
        reports[phase] = {"phase": phase, "sampling_unit": "paired_block", "planned_blocks_per_model": planned,
                          "models": models, "primary_family": {"fixed_family_size": 4, "judge": "astra",
                              "endpoint": "inclusive_current_assertion", "contrasts": list(figures.schema.PRIMARY_CONTRASTS),
                              "study": "openweights_extension_only", "planned_models": list(figures.MODELS),
                              "familywise_confidence": .95, "method": figures.METHOD}}
    return metadata, reports, qualification


def fixture_release(root, state="complete"):
    metadata, reports, qualification = payload(state)
    root.mkdir()
    for name, value in {"RELEASE.json": metadata, "screen_analysis.json": reports["screen"],
                        "main_analysis.json": reports["main"], "qualification.json": qualification}.items():
        figures._write(root / name, value)
    entries = [{"path": path.name, "bytes": path.stat().st_size, "sha256": figures._sha(path)} for path in sorted(root.iterdir())]
    figures._write(root / "MANIFEST.json", {"synthetic_test_only": True, "files": entries})
    return root


def synthetic_verifier(root):
    manifest = figures._load(root / "MANIFEST.json")
    assert manifest["synthetic_test_only"] is True
    assert {p.name for p in root.iterdir()} == {"MANIFEST.json", *(r["path"] for r in manifest["files"])}
    for row in manifest["files"]:
        path = root / row["path"]
        _no_symlinks(path)
        assert path.stat().st_size == row["bytes"] and figures._sha(path) == row["sha256"]
    return {"pass": True}


def primary(reports, model="qwen"):
    return reports["main"]["models"][model]["judges"]["astra"]["inclusive_current_assertion"]


def test_saved_rates_and_four_main_bounds_are_copied_without_reanalysis():
    metadata, reports, qualification = payload("partial")
    view = figures._tables(metadata, reports, qualification)
    assert len(view["rates"]) == 144 and len(view["contrasts"]) == 4
    assert {r["phase"] for r in view["rates"]} == {"screen", "main"}
    assert {r["phase"] for r in view["contrasts"]} == {"main"}
    assert {r["judge"] for r in view["rates"]} == {"astra", "opus"}
    assert {r["endpoint"] for r in view["rates"]} == set(figures.schema.ENDPOINTS)
    for row in view["rates"]:
        saved = reports[row["phase"]]["models"][row["model"]]["judges"][row["judge"]][row["endpoint"]]["cells"][row["cell"]]
        assert all(row[k] == saved[k] for k in ("proportion", "positive", "negative", "observed", "missing", "planned"))
    for row in view["contrasts"]:
        assert row["complete_case_mean"] == .123456789
        assert [row["interval_low"], row["interval_high"]] == row["saved_familywise_hoeffding_95"] == [-.7312345, .8912345]
        assert row["family_size"] == 4 and row["judge"] == "astra" and row["interval_method"] == figures.METHOD


@pytest.mark.parametrize("state", ["startup", "screen-failed", "admitted-not-started"])
def test_unrun_or_missing_is_never_zero_effect(state):
    view = figures._tables(*payload(state))
    assert all(r["complete_case_mean"] is None and r["interval_low"] is None and r["interval_high"] is None
               and r["saved_familywise_hoeffding_95"] == [-1, 1] and r["state"].startswith("unrun") for r in view["contrasts"])
    assert all(r["proportion"] is None and r["missing"] == 32 for r in view["rates"] if r["phase"] == "main")
    if state != "startup":
        assert any(r["proportion"] == 0 and r["observed"] > 0 for r in view["rates"] if r["phase"] == "screen")
    else:
        assert all(r["proportion"] is None for r in view["rates"])


def test_model_selection_never_reduces_four_comparison_family():
    view = figures._tables(*payload("single-model"))
    assert len(view["contrasts"]) == 4 and all(r["family_size"] == 4 for r in view["contrasts"])
    assert all(r["interval_low"] is None and r["state"] == "unrun: screen not qualified"
               for r in view["contrasts"] if r["model"] == "mistral")
    assert all(r["interval_low"] == -.7312345 for r in view["contrasts"] if r["model"] == "qwen")


def test_later_unresolved_main_does_not_revoke_verified_screen_decision():
    metadata, reports, qualification = payload("single-model")
    metadata["collection_complete"] = {"screen": False, "main": False}
    metadata["main_status"] = "incomplete"
    view = figures._tables(metadata, reports, qualification)
    states = {(row["phase"], row["model"]): row["state"] for row in view["states"]}
    assert states["screen", "qwen"] == "screen completed before main"
    assert states["screen", "mistral"] == "screen not qualified"
    assert states["main", "qwen"] == "partial collection"
    assert states["main", "mistral"] == "unrun: screen not qualified"
    assert all(row["interval_low"] is None for row in view["contrasts"] if row["model"] == "mistral")


def test_no_primary_labels_hides_bar_but_preserves_saved_worst_case_bound():
    metadata, reports, qualification = payload()
    for row in primary(reports)["cells"].values():
        row.update(observed=0, positive=0, negative=0, missing=32, proportion=None)
    for row in primary(reports)["contrasts"].values():
        row.update(complete_blocks=0, missing_blocks=32, complete_case_mean=None, familywise_hoeffding_95=[-1, 1])
    rows = figures._tables(metadata, reports, qualification)["contrasts"]
    assert all(r["state"] == "no primary labels" and r["interval_low"] is None
               and r["saved_familywise_hoeffding_95"] == [-1, 1] for r in rows if r["model"] == "qwen")


def test_observed_unpaired_labels_keep_bound_without_fake_zero_dot():
    metadata, reports, qualification = payload("partial")
    row = primary(reports)["contrasts"]["instruction_minus_transcript"]
    row.update(complete_blocks=0, missing_blocks=32, complete_case_mean=None)
    contrast = figures._tables(metadata, reports, qualification)["contrasts"][0]
    assert contrast["complete_case_mean"] is None and contrast["interval_low"] == -.7312345


@pytest.mark.parametrize("change", ["a1_schema", "old_family", "method", "primary_judge", "model", "judge", "rubric", "counts",
                                  "boolean_count", "rate", "nonfinite", "interval", "fake_pairs", "unrun_labels"])
def test_foreign_schema_or_inconsistent_summary_is_rejected(change):
    metadata, reports, qualification = payload()
    if change == "a1_schema": metadata["schema"] = "openweights-a1-release-v1"
    if change == "old_family": reports["main"]["primary_family"]["fixed_family_size"] = 8
    if change == "method": reports["main"]["primary_family"]["method"] = "bootstrap"
    if change == "primary_judge": reports["main"]["primary_family"]["judge"] = "opus"
    if change == "model": reports["main"]["models"]["other"] = {}
    if change == "judge": reports["main"]["models"]["qwen"]["judges"].pop("opus")
    if change == "rubric": reports["main"]["models"]["qwen"]["judges"]["opus"].pop("paper")
    if change == "counts": primary(reports)["cells"]["SS"]["missing"] = 1
    if change == "boolean_count": primary(reports)["cells"]["SS"]["positive"] = False
    if change == "rate": primary(reports)["cells"]["SS"]["proportion"] = .5
    if change == "nonfinite": primary(reports)["cells"]["SS"]["proportion"] = float("nan")
    if change == "interval": primary(reports)["contrasts"]["instruction_minus_transcript"]["familywise_hoeffding_95"] = [1, -1]
    if change == "fake_pairs": primary(reports)["cells"]["SH"].update(observed=0, positive=0, negative=0, missing=32, proportion=None)
    if change == "unrun_labels": metadata["admitted_models"] = []
    with pytest.raises(Halted): figures._tables(metadata, reports, qualification)


def test_real_a2_verifier_rejects_fabricated_release_before_output(tmp_path):
    root = fixture_release(tmp_path / "synthetic-unverified")
    with pytest.raises(Halted): figures.build(root, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize("state", ["complete", "partial", "startup", "screen-failed", "single-model", "admitted-not-started"])
def test_render_synthetic_json_png_pdf_and_unchanged_source(tmp_path, monkeypatch, state):
    root = fixture_release(tmp_path / "release", state)
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    checked = []
    def verify(snapshot):
        assert snapshot != root and snapshot.name == "release"
        checked.append(True)
        return synthetic_verifier(snapshot)
    monkeypatch.setattr(figures.a2_release, "verify", verify)
    target = tmp_path / "figures"
    result = figures.build(root, target)
    assert checked == [True] and {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert result["release_manifest_sha256"] == figures._sha(root / "MANIFEST.json")
    assert result["release_sha256"] == figures._sha(root / "RELEASE.json")
    assert result["failure_evidence"] == payload(state)[0]["failure_evidence"]
    assert result["fixture_evidence"]["event_count"] == 53
    assert result["primary_family_size"] == 4 and "SYNTHETIC" in result["title"]
    assert len(result["files"]) == 8
    assert {path.name for path in target.iterdir()} == {"FIGURES.json", *(r["path"] for r in result["files"])}
    for row in result["files"]:
        assert (target / row["path"]).stat().st_size == row["bytes"]
        assert figures._sha(target / row["path"]) == row["sha256"]
    for name in ("cell_rates", "primary_contrasts"):
        assert (target / (name + ".pdf")).read_bytes().startswith(b"%PDF-")
        assert (target / (name + ".pdf")).stat().st_size > 10000
        with Image.open(target / (name + ".png")) as image:
            assert image.width >= 1800 and image.height >= 900
            pixels = image.convert("RGB").resize((300, 180))
            assert len(pixels.getcolors(pixels.width * pixels.height)) > 100
            channels = iter(pixels.tobytes())
            assert sum(max(rgb) < 180 for rgb in zip(channels, channels, channels)) > 150
    data = figures._load(target / "figure_data.json")
    assert {k: data[k] for k in ("rates", "contrasts", "states")} == figures._tables(*payload(state))
    with (target / "primary_contrasts.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    if state in {"startup", "screen-failed", "admitted-not-started"}:
        assert all(row["complete_case_mean"] == "" and row["interval_low"] == "" for row in rows)
        assert "Not estimated" in (target / "README.md").read_text()
    with pytest.raises(Halted): figures.build(root, target)
    with pytest.raises(Halted): figures.build(root, root / "forbidden")
    with pytest.raises(Halted): figures.build(root, root.parent)


@pytest.mark.parametrize("verdict", [None, {"pass": False}, {"pass": 1}])
def test_failed_verification_never_renders_or_writes(tmp_path, monkeypatch, verdict):
    root = fixture_release(tmp_path / "release")
    monkeypatch.setattr(figures.a2_release, "verify", lambda _: verdict)
    monkeypatch.setattr(figures, "_render", lambda *_: pytest.fail("Render before verification"))
    with pytest.raises(Halted): figures.build(root, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_snapshot_is_the_only_display_source_after_verification(tmp_path, monkeypatch):
    root = fixture_release(tmp_path / "release")
    def verify(snapshot):
        verdict = synthetic_verifier(snapshot)
        (root / "main_analysis.json").write_text("{}")
        return verdict
    monkeypatch.setattr(figures.a2_release, "verify", verify)
    assert figures.build(root, tmp_path / "figures")["release_verified"] is True


def test_symlink_cannot_be_laundered_into_snapshot(tmp_path):
    root = fixture_release(tmp_path / "release")
    (root / "private-link").symlink_to(tmp_path / "not-a-public-file")
    with pytest.raises((Halted, ValueError)): figures.build(root, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_cli_fails_closed_without_disclosing_exception_text(tmp_path, monkeypatch, capsys):
    def bad(*args): raise Halted("synthetic-sensitive-sentinel")
    monkeypatch.setattr(figures, "build", bad)
    with pytest.raises(SystemExit): figures.main(["--release", str(tmp_path), "--out", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert "failed closed" in captured.err and "sentinel" not in captured.err + captured.out


def test_sidecars_are_outside_115_source_frozen_inventory():
    root = Path(__file__).resolve().parents[1]
    plan = figures._load(root / "data/openrouter_swap_openweights_a2/plan_v1/PLAN.json")
    assert len(plan["source_hashes"]) == 115
    assert "experiments/openweights_a2_figures.py" not in plan["source_hashes"]
    assert "tests/test_openweights_a2_figures.py" not in plan["source_hashes"]
    assert all(figures._sha(root / name) == digest for name, digest in plan["source_hashes"].items())
