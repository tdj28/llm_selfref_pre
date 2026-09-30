"""Synthetic lifecycle publication checks; no network or GPU."""
import json

import pytest

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_replay import release


def prepared(tmp_path, monkeypatch, *, closed=True, failed=False, extra=None):
    base, raw = tmp_path / "private", tmp_path / "retrieved"
    base.mkdir()
    raw.mkdir()
    plan = tmp_path / "PLAN.json"
    plan.write_text('{"inputs":[{}]}\n')
    monkeypatch.setattr(release, "load_plan", lambda _: {"inputs": [{"id": "synthetic"}]})
    freeze = "a" * 40
    monkeypatch.setattr(release, "audit", lambda *_: {"pass": True, "complete": True,
                        "freeze_commit": freeze, "plan_sha256": release.sha(plan)})
    (raw / "DONE-all.json").write_text(json.dumps({"rows": 1, "plan_sha256": release.sha(plan),
        "freeze_commit": freeze, "native_replay_complete": True, "behavioral_assay_qualified": False}))
    (raw / "controller-exit.json").write_text(json.dumps({"exit_code": int(failed)}))
    if extra:
        (raw / extra).write_text('{"private_metadata":"synthetic only"}')
    files = {p.name: release.sha(p) for p in raw.iterdir()}
    ledger = EventLedger(base / "events.jsonl", release.sha(plan), freeze, [])
    receipt = ledger.bind("retrieval:synthetic", {"pod_id": "synthetic-owned", "directory": str(raw), "artifacts": files})
    (base / "final-retrieval.json").write_text(json.dumps(receipt))
    if closed:
        ledger.bind("closed", {"pod_id": "synthetic-owned", "get_status": 404,
                    "utc": "2026-09-30T00:00:00+00:00", "elapsed_seconds": "10",
                    "compute_upper_bound_usd": "0.002", "cumulative_upper_bound_usd": "27.39",
                    "within_limits": True})
    return base, raw, plan, freeze


def test_copies_only_verified_raw_files_and_public_projection(tmp_path, monkeypatch):
    base, raw, plan, freeze = prepared(tmp_path, monkeypatch)
    dest = tmp_path / "release"
    result = release.copy_release(base, dest, plan, freeze)
    assert result["closure"]["get_status"] == 404
    assert not (dest / "events.jsonl").exists()
    assert str(tmp_path) not in (dest / "retrieval_and_cost.json").read_text()
    manifest = release.manifest(dest, plan, freeze)
    assert len(manifest["files"]) == 3
    for item in manifest["files"]:
        assert release.sha(dest / item["path"]) == item["sha256"]
    with pytest.raises(FileExistsError):
        release.copy_release(base, dest, plan, freeze)
    with pytest.raises(FileExistsError):
        release.manifest(dest, plan, freeze)


@pytest.mark.parametrize("problem", ["open", "failed", "changed", "extra"])
def test_invalid_release_refused_before_copy(tmp_path, monkeypatch, problem):
    base, raw, plan, freeze = prepared(tmp_path, monkeypatch, closed=problem != "open", failed=problem == "failed")
    if problem == "changed":
        (raw / "DONE-all.json").write_text("changed")
    if problem == "extra":
        (raw / ".env").write_text("placeholder")
    dest = tmp_path / "release"
    with pytest.raises(ValueError):
        release.copy_release(base, dest, plan, freeze)
    assert not dest.exists()


def test_terminal_marker_cannot_replace_raw_row_audit(tmp_path, monkeypatch):
    base, raw, plan, freeze = prepared(tmp_path, monkeypatch)
    monkeypatch.setattr(release, "audit", lambda *_: {"pass": False, "complete": False})
    with pytest.raises(ValueError, match="raw-row audit"):
        release.copy_release(base, tmp_path / "release", plan, freeze)


def test_public_allowlist_excludes_private_names():
    assert "credentials.json" not in release.PUBLIC_ROOT_FILES
    assert "events.jsonl" not in release.PUBLIC_ROOT_FILES


def test_receipted_private_json_refused(tmp_path, monkeypatch):
    base, raw, plan, freeze = prepared(tmp_path, monkeypatch, extra="credentials.json")
    with pytest.raises(ValueError, match="Unexpected"):
        release.copy_release(base, tmp_path / "release", plan, freeze)
    assert not (tmp_path / "release").exists()
