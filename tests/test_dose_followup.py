"""Offline paper binding; no model calls or frozen-record writes."""
import json
from pathlib import Path
import socket

import pytest

from scripts import verify_dose_followup as v


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Paper verification must be offline")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    result = {"target": {"estimate_complete_pairs": .10416666666666667,
                         "bounds": [-.09808587323340845, .2978063242719731]},
              "specificity": {"estimate_complete_pairs": .21875, "bounds": [-.44802543029152103, .8340426018411922]},
              "main_quality_pass": True}
    summary = {"selection": {"selected_dose": .25}, "results": {j: result for j in ("notebook", "paper")},
               "cap_counts_by_phase": {"main": {"induction": 47, "final": 6}}}
    files = {
        "analysis/summary.json": v.encoded(summary), "main/analysis/summary.json": v.encoded(summary),
        "analysis/portability.json": v.encoded({"original_exact_replay": {"status": "FAIL"}}),
        "REPORT.json": v.encoded({"main_status": "completed", "observed_main_rows": 480,
            "calibration_rows_carried": 204, "original_throughput_pass": False}),
        "provenance/PLAN.json": v.encoded({"amendment": {"output_cap_both_turns_all_arms": 512}}),
        "provenance/controller.json": v.encoded({"lifecycle": {"deletion_verified": True, "retrieval_verified": True}}),
        "FIGURE_DATA.json": v.encoded({"contrasts": {j: {**result, "control_panels": {str(i): {} for i in (1,2,3)}}
                                                      for j in ("notebook", "paper")}}),
        "values.tex": b"% Synthetic released macros\n", "figures/main_contrasts.pdf": b"%PDF-1.7\nsynthetic\n",
    }
    release = tmp_path / v.RELEASE
    for name, raw in files.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    for name in v.SOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((v.ROOT / name).read_bytes())
    monkeypatch.setattr(v, "WORKER_SUMMARY_SHA256", v.sha(files["analysis/summary.json"]))
    monkeypatch.setattr(v, "RELEASE_COMMIT", None)
    monkeypatch.setattr(v, "RELEASE_MANIFEST_SHA256", None)
    reseal(release)
    return tmp_path, release


def reseal(release):
    entries = [{"path": p.relative_to(release).as_posix(), "bytes": p.stat().st_size, "sha256": v.sha(p.read_bytes())}
               for p in sorted(release.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"]
    (release / "MANIFEST.json").write_bytes(v.encoded({"mode": "completed", "files": entries}))


def test_pending_pin_blocks_publication_but_draft_binds_saved_values(fixture):
    root, release = fixture
    with pytest.raises(ValueError, match="pending"):
        v.build(root, require_pinned=True)
    outputs = v.build(root)
    assert outputs["main_contrasts.pdf"] == (release / "figures/main_contrasts.pdf").read_bytes()
    assert outputs["values.tex"].startswith((release / "values.tex").read_bytes())
    assert b"\\DoseFollowupInductionCaps}{47}" in outputs["values.tex"]
    binding = json.loads(outputs["binding.json"])
    assert binding["release_commit_state"] == "pending"
    assert binding["release_manifest_sha256"] == v.sha((release / "MANIFEST.json").read_bytes())
    assert binding["worker_summary_sha256"] == v.WORKER_SUMMARY_SHA256
    assert str(root) not in outputs["binding.json"].decode()


@pytest.mark.parametrize("name", ["analysis/summary.json", "values.tex", "figures/main_contrasts.pdf"])
def test_tampered_bound_input_rejected(fixture, name):
    root, release = fixture
    path = release / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="input changed"):
        v.build(root)


def test_resealed_recomputed_summary_cannot_replace_worker(fixture):
    root, release = fixture
    path = release / "analysis/summary.json"
    summary = json.loads(path.read_bytes())
    summary["results"]["notebook"]["target"]["bounds"][1] = .29780632427197323
    path.write_bytes(v.encoded(summary))
    reseal(release)
    with pytest.raises(ValueError, match="exact saved worker"):
        v.build(root)


@pytest.mark.parametrize("field,value", [("main_status", "incomplete"), ("observed_main_rows", 479),
                                         ("original_throughput_pass", True)])
def test_resealed_incomplete_or_relabelled_report_rejected(fixture, field, value):
    root, release = fixture
    path = release / "REPORT.json"
    report = json.loads(path.read_bytes()); report[field] = value
    path.write_bytes(v.encoded(report)); reseal(release)
    with pytest.raises(ValueError, match="Incomplete or relabelled"):
        v.build(root)


def test_full_check_uses_historical_compatibility_and_does_not_modify_release(fixture, monkeypatch):
    root, release = fixture
    from experiments import dose_release_compat as compat
    calls = []
    def check(action, arguments, destination, repository):
        calls.append((action, arguments, destination, repository))
        return json.dumps({"pass": True, "main_status": "completed", "external_manifest_bound": True})
    monkeypatch.setattr(compat, "report", check)
    before = {p: p.read_bytes() for p in release.rglob("*") if p.is_file()}
    v.build(root, full=True)
    assert calls == [("verify", ["--root", str(release), "--manifest-sha256",
                                 v.sha((release / "MANIFEST.json").read_bytes())], release, root)]
    assert before == {p: p.read_bytes() for p in release.rglob("*") if p.is_file()}


def test_pin_requires_matching_manifest_and_local_git_blob(fixture, monkeypatch):
    root, release = fixture
    from experiments import dose_release_compat as compat
    raw = (release / "MANIFEST.json").read_bytes()
    monkeypatch.setattr(v, "RELEASE_COMMIT", "a" * 40)
    monkeypatch.setattr(v, "RELEASE_MANIFEST_SHA256", v.sha(raw))
    calls = []
    class Git:
        def __init__(self, path):
            assert path == root
        def query(self, *args):
            calls.append(args)
            return raw
    monkeypatch.setattr(compat, "GitBlobs", Git)
    binding = json.loads(v.build(root, require_pinned=True)["binding.json"])
    assert binding["release_commit_state"] == "bound"
    assert calls == [("cat-file", "blob", "a" * 40 + ":" + v.RELEASE + "/MANIFEST.json")]
    monkeypatch.setattr(Git, "query", lambda self, *args: b"foreign blob")
    with pytest.raises(ValueError, match="commit does not contain"):
        v.build(root, require_pinned=True)
    monkeypatch.setattr(v, "RELEASE_MANIFEST_SHA256", "b" * 64)
    with pytest.raises(ValueError, match="manifest hash"):
        v.build(root, require_pinned=True)


def test_pending_cli_requires_pin_and_refuses_public_write(monkeypatch):
    monkeypatch.setattr(v, "RELEASE_COMMIT", None)
    monkeypatch.setattr(v, "RELEASE_MANIFEST_SHA256", None)
    assert v.main(["--require-pinned"]) == 1
    assert v.main(["--write", "--full"]) == 1


def test_paper_keeps_both_rubrics_intervals_and_narrow_threshold_wording():
    text = (v.ROOT / v.PAPER).read_text()
    prose = " ".join(text.split())
    assert "Source release commit: " + v.RELEASE_COMMIT in text
    assert "Release manifest SHA-256: " + v.RELEASE_MANIFEST_SHA256 in text
    assert "only just below" in text and "not robust" in text
    assert "\\DoseMainPaperTargetLow{}" in text and "\\DoseMainSecondSpecificityLow{}" in text
    assert "first-turn truncation" in text and "final-turn truncation" in text
    assert text.count("\\includegraphics") == 1 and "\\caption{" in text
    assert "all three fixed control panels" in text
    assert "primary notebook classifier" in prose and "secondary paper rubric" in prose
    assert "features 41533, 58667, and 30686" in prose
    assert "largest category mean of per-text maxima" in prose and "designed NF4 mapping set" in prose
    assert "Each higher tested dose failed at least one target or control quality check" in prose
    assert "identifies the notebook classifier used in the earlier analyses" in prose
