import json
from pathlib import Path

import pytest

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_repair.protocol import canonical, sha
from experiments.sae_assay_repair.release import copy_release, manifest, verified_run
from experiments.sae_assay_repair.reproduce import verify_manifest

FREEZE = "a" * 40


def run_fixture(root, kind, plan_hash):
    base = root / kind
    raw = base / "retrieved"
    raw.mkdir(parents=True)
    files = {"controller-exit.json": {"exit_code": 0},
             "cheap-qualification.json": {"pass": True, "device": "cuda", "checks": {"known": True}}}
    if kind == "main":
        files = {"controller-exit.json": {"exit_code": 0}, "DONE-all.json": {"status": "complete"}}
    for name, content in files.items():
        (raw / name).write_text(canonical(content) + "\n")
    ledger = EventLedger(base / "events.jsonl", plan_hash, FREEZE, [])
    receipt = ledger.bind("retrieval:1", {"pod_id": "fixture-" + kind,
        "directory": str(raw), "artifacts": {name: sha(raw / name) for name in files}})
    (base / "final-retrieval.json").write_text(canonical(receipt) + "\n")
    ledger.bind("closed", {"pod_id": "fixture-" + kind, "get_status": 404,
        "utc": "2026-09-30T00:00:00+00:00", "elapsed_seconds": "1",
        "compute_upper_bound_usd": "0.001", "repair_upper_bound_usd": "0.002",
        "cumulative_upper_bound_usd": "13.08", "within_limits": True,
        "private_field": "must not be projected"})
    return base, raw


def test_release_copies_raw_and_projects_private_lifecycle(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text("{}\n")
    root = tmp_path / "private"
    for kind in ("cheap", "main"):
        run_fixture(root, kind, sha(plan))
    out = tmp_path / "public"
    result = copy_release(root, out, plan, FREEZE)
    assert all("private_field" not in p for p in result["pods"].values())
    assert "directory" not in canonical(result)
    assert not list(out.rglob("events.jsonl"))
    assert json.loads((out / "DONE-all.json").read_text())["status"] == "complete"
    data = manifest(out, FREEZE, plan)
    assert len(data["files"]) == 5
    assert all(sha(out / r["path"]) == r["sha256"] for r in data["files"])
    assert verify_manifest(out) == data
    with pytest.raises(FileExistsError):
        manifest(out, FREEZE, plan)
    with pytest.raises(FileExistsError):
        copy_release(root, out, plan, FREEZE)
    (out / "unmanifested.txt").write_text("unexpected")
    with pytest.raises(ValueError, match="unmanifested"):
        verify_manifest(out)


def test_tampered_retrieval_rejected(tmp_path):
    base, raw = run_fixture(tmp_path, "cheap", "b" * 64)
    (raw / "controller-exit.json").write_text('{"exit_code": 1}')
    with pytest.raises(ValueError, match="hash/type"):
        verified_run(base, "b" * 64, FREEZE)


def test_missing_ledger_is_read_only(tmp_path):
    with pytest.raises(ValueError, match="Existing lifecycle"):
        verified_run(tmp_path / "absent", "b" * 64, FREEZE)
    assert not (tmp_path / "absent").exists()


def test_receipt_outside_ledger_rejected(tmp_path):
    base, _ = run_fixture(tmp_path, "cheap", "b" * 64)
    path = base / "final-retrieval.json"
    value = json.loads(path.read_text())
    value["data"]["directory"] = str(tmp_path)
    path.write_text(canonical(value))
    with pytest.raises(ValueError, match="not in the chained"):
        verified_run(base, "b" * 64, FREEZE)


@pytest.mark.parametrize("arithmetic_pass", [True, False])
def test_reproduction_checks_separate_arithmetic(tmp_path, monkeypatch, arithmetic_pass):
    from experiments.sae_assay_repair import release_audit, corpus_report, figures, geometry_audit
    from experiments.sae_assay_repair.reproduce import reproduce

    run = tmp_path / "release"
    run.mkdir()
    plan = tmp_path / "plan.json"
    plan.write_text("{}\n")
    original = manifest(run, FREEZE, plan)
    calls = []
    monkeypatch.setattr(release_audit, "audit", lambda *a, **kw: {
        "pass": True, "rows": 0, "errors": [], "frozen_audit": {"pass": False, "errors": ["fixture"]}})
    monkeypatch.setattr(geometry_audit, "audit", lambda *a: {"pass": arithmetic_pass})
    monkeypatch.setattr(figures, "render", lambda *a: calls.append("figures"))
    monkeypatch.setattr(figures, "mundane_controls", lambda *a: calls.append("controls"))
    monkeypatch.setattr(corpus_report, "report_corpus", lambda *a: calls.append("corpus"))
    out = tmp_path / "reproduced"
    if arithmetic_pass:
        assert reproduce(run, plan, out)["pass"]
        assert calls == ["figures", "controls", "corpus"]
    else:
        with pytest.raises(ValueError, match="coordinate arithmetic"):
            reproduce(run, plan, out)
        assert calls == []
    assert json.loads((out / "geometry_audit.json").read_text())["pass"] == arithmetic_pass
    assert verify_manifest(run) == original
