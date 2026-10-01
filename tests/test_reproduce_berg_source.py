import json
from pathlib import Path

import pytest

from scripts import reproduce_berg_source as r
from tests.test_release_berg_source import candidate


def fixture(tmp_path):
    raw = tmp_path/"raw.json"; raw.write_text('{}\n')
    manifest = {"schema": "berg_source_release_v1",
        "reporting_source_hashes": {p: r.protocol.sha(r.protocol.ROOT/p)
                                    for p in r.publication.reporting_sources()}, "files":[{
        "path":"raw.json","bytes":raw.stat().st_size,"sha256":r.protocol.sha(raw)}]}
    (tmp_path/"RELEASE_MANIFEST.json").write_text(json.dumps(manifest))
    return raw


def test_manifest_exact_inventory_and_hash(tmp_path):
    raw = fixture(tmp_path)
    assert r.verify_manifest(tmp_path)["files"][0]["path"] == "raw.json"
    raw.write_text('{"changed":true}\n')
    with pytest.raises(ValueError,match="verification"): r.verify_manifest(tmp_path)


def test_unmanifested_extra_file_rejected(tmp_path):
    fixture(tmp_path)
    (tmp_path/"extra.json").write_text('{}\n')
    with pytest.raises(ValueError,match="inventory"): r.verify_manifest(tmp_path)


def test_no_output_into_release_or_existing_directory(tmp_path):
    fixture(tmp_path)
    for out in (tmp_path,tmp_path/"derived"):
        with pytest.raises(ValueError,match="outside"): r.reproduce(tmp_path,out)


def test_actual_clean_capture_replay_check(tmp_path):
    rows = tmp_path/"rows"; rows.mkdir()
    state = {"layer":50,"position":5,"residual":[1.,2.],"readout":{"test":[3.]}}
    for name in ("a","b"):
        row = {"id":"capture-"+name,"pairs":[{"source":"zero","turn":1,
            "clean":{"input_sha256":"a"*64,"output_prefix_ids":[4],"captures":[state]}}]}
        (rows/("capture-"+name+".json")).write_text(json.dumps(row))
    result = r.replay_consistency(tmp_path)
    assert result["all_repeats_exact"] and result["repeated_states"] == 1
    row["pairs"][0]["clean"]["captures"][0]["residual"][0] = 1.5
    (rows/"capture-b.json").write_text(json.dumps(row))
    result = r.replay_consistency(tmp_path)
    assert not result["all_repeats_exact"] and result["exact_mismatches"] == 1


@pytest.mark.parametrize("source", ["experiments/berg_source_diagnostics.py",
                                    "experiments/berg_source_figures.py",
                                    "scripts/reproduce_berg_source.py"])
def test_reporting_source_drift_rejected_before_reanalysis(candidate, tmp_path, source):
    c = candidate
    r.publication.manifest(c.out, c.path, c.freeze)
    (c.repo/source).write_text("changed reporting implementation\n")
    with pytest.raises(ValueError, match="Reporting source changed"):
        r.reproduce(c.out, tmp_path/"reanalysis")
    assert not (tmp_path/"reanalysis").exists()


@pytest.mark.parametrize("ensemble", [False, True])
def test_missing_shared_helper_hash_rejected(candidate, ensemble):
    c = candidate
    manifest = {"schema": "berg_ensemble_release_v1" if ensemble else "berg_source_release_v1",
                "reporting_source_hashes": {p: r.protocol.sha(c.repo/p)
                                            for p in r.publication.reporting_sources(ensemble)}}
    r.publication.verify_reporting_sources(manifest)
    del manifest["reporting_source_hashes"]["experiments/berg_source_diagnostics.py"]
    with pytest.raises(ValueError, match="Incomplete reporting"):
        r.publication.verify_reporting_sources(manifest)


def test_manifest_freeze_tampering_fails_before_output(candidate, tmp_path):
    c = candidate
    r.publication.manifest(c.out, c.path, c.freeze)
    path = c.out/"RELEASE_MANIFEST.json"
    manifest = json.loads(path.read_text())
    manifest["freeze_commit"] = "b"*40
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="frozen Git object"):
        r.reproduce(c.out, tmp_path/"reanalysis")
    assert not (tmp_path/"reanalysis").exists()


def test_reproduction_integrates_verified_plan_and_extra_figures(candidate, tmp_path, monkeypatch):
    c = candidate
    r.publication.manifest(c.out, c.path, c.freeze)
    monkeypatch.setattr(r.protocol, "load_plan", lambda path: c.plan)
    monkeypatch.setattr(r.analysis, "audit", lambda *args, **kwargs: {"pass": True})
    monkeypatch.setattr(r.diagnostics, "validate_capture_schedule", lambda *args: {"complete": True})
    calls = []

    def analyze(root, out):
        calls.append(("analyze", root, out))
        out.mkdir(parents=True)
        return {}

    def summarize(root, out, plan):
        assert plan is c.plan
        calls.append(("secondary", root, out))
        out.mkdir()
        return {"synthetic": True}

    monkeypatch.setattr(r.analysis, "analyze", analyze)
    monkeypatch.setattr(r.analysis, "figures", lambda *args: calls.append(("primary_figures", *args)))
    monkeypatch.setattr(r.diagnostics, "summarize", summarize)
    monkeypatch.setattr(r.diagnostics, "figures", lambda *args: calls.append(("secondary_figures", *args)))
    monkeypatch.setattr(r.berg_source_figures, "figures", lambda *args: calls.append(("extra_figures", *args)))
    out = tmp_path/"reanalysis"
    result = r.reproduce(c.out, out)
    assert result["raw_manifest_verified"] and result["primary_reproduced_exactly"]
    assert calls[-1] == ("extra_figures", c.out, out/"secondary", out/"extra_figures")
    assert (out/"REPRODUCTION_AUDIT.json").is_file()


def test_reproduction_rechecks_publication_binding(candidate, tmp_path, monkeypatch):
    c = candidate
    c.audit["freeze_commit"] = "b"*40
    (c.out/"PUBLICATION_AUDIT.json").write_text(json.dumps(c.audit))
    # A self-consistent file manifest cannot substitute for the publication binding.
    files = r.publication._files(c.out)
    manifest = {"schema": "berg_source_release_v1", "freeze_commit": c.freeze,
                "plan_path": "PLAN.json", "plan_sha256": r.protocol.sha(c.path),
                "reporting_source_hashes": {p: r.protocol.sha(c.repo/p) for p in r.publication.reporting_sources()},
                "files": [{"path": name, "bytes": path.stat().st_size, "sha256": r.protocol.sha(path)}
                          for name, path in files.items()]}
    (c.out/"RELEASE_MANIFEST.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(r.protocol, "load_plan", lambda path: c.plan)
    with pytest.raises(ValueError, match="publication audit"):
        r.reproduce(c.out, tmp_path/"reanalysis")
    assert not (tmp_path/"reanalysis").exists()
