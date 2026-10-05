"""Exact archived auditor provenance, never a generic frozen-source exemption."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("REPEAT_PORTABILITY_ROOT", HERE)).resolve()
spec = importlib.util.spec_from_file_location("repeat_reporting_history_under_test",
                                            HERE / "experiments/repeat_release_portability.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Historical reporting must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.syspath_prepend(str(ROOT))


def test_exact_source_failure_is_preserved_and_history_is_explicit():
    with pytest.raises(ValueError, match="Bound scientific/reporting source changed: " + c.AUDITOR):
        c.verify_inputs(ROOT, historical_reporting=False)
    c.verify_inputs(ROOT)
    raw, record = c.historical_auditor(ROOT)
    assert c.sha(raw) == c.HISTORICAL_AUDITOR_SHA
    assert record["current_auditor_sha256"] == c.REVIEWED_AUDITOR_SHA
    assert record["original_exact_source_check"] == "FAIL"
    assert str(ROOT) not in json.dumps(record)


@pytest.mark.parametrize("name", [c.AUDITOR, "experiments/repeated_swap/protocol.py",
                                  "experiments/repeated_swap/analysis.py", "experiments/repeat_funding_a1.py",
                                  "experiments/repeat_transport_a2.py", "experiments/repeat_refusal_a3.py",
                                  c.RELEASE + "/PLAN.json", c.RELEASE + "/MANIFEST.json"])
def test_unapproved_source_or_record_drift_fails(monkeypatch, name):
    original = c.regular
    def changed(path):
        raw = original(path)
        return raw + b" " if Path(path) == ROOT / name else raw
    monkeypatch.setattr(c, "regular", changed)
    with pytest.raises(ValueError, match="changed"):
        c.verify_inputs(ROOT)


@pytest.mark.parametrize("name", [c.AUDITOR, c.RELEASE + "/MANIFEST.json"])
def test_archived_git_blob_tamper_fails(monkeypatch, name):
    original = c._historical_blob
    monkeypatch.setattr(c, "_historical_blob",
                        lambda root, path: original(root, path) + (b" " if path == name else b""))
    with pytest.raises(ValueError, match="changed"):
        c.historical_auditor(ROOT)


@pytest.mark.parametrize("failure", [False, True])
def test_original_plan_reconstructs_current_scanner_stays_active_and_context_restores(failure):
    p = importlib.import_module("experiments.repeated_swap.protocol")
    scanner = importlib.import_module("scripts.audit_public_release")
    original, scan = p.sha, scanner.scan_blob
    common_sha = p.common.sha
    plan = json.loads((ROOT / c.RELEASE / "PLAN.json").read_bytes())
    assert original(ROOT / c.AUDITOR) == c.REVIEWED_AUDITOR_SHA
    try:
        with c.reporting_source_replay(ROOT) as record:
            assert p.sha(ROOT / c.AUDITOR) == c.HISTORICAL_AUDITOR_SHA
            assert p.sha(ROOT / "experiments/repeated_swap/protocol.py") == original(ROOT / "experiments/repeated_swap/protocol.py")
            assert p.verify(ROOT / c.RELEASE / "PLAN.json") == plan
            assert p.common.sha is common_sha and scanner.scan_blob is scan
            assert p.common.sha(ROOT / c.AUDITOR) == c.REVIEWED_AUDITOR_SHA
            assert record["historical_source_hash_reads"] > 0
            if failure:
                raise RuntimeError("caller failure")
    except RuntimeError as error:
        assert failure and str(error) == "caller failure"
    assert p.sha is original and scanner.scan_blob is scan
    assert p.sha(ROOT / c.AUDITOR) == c.REVIEWED_AUDITOR_SHA


def test_mid_replay_auditor_change_fails_and_restores(monkeypatch):
    p = importlib.import_module("experiments.repeated_swap.protocol")
    original, read = p.sha, c.regular
    with pytest.raises(ValueError, match="changed during replay"):
        with c.reporting_source_replay(ROOT):
            monkeypatch.setattr(c, "regular", lambda path: read(path) + (b" " if Path(path) == ROOT / c.AUDITOR else b""))
            p.sha(ROOT / c.AUDITOR)
    assert p.sha is original


def test_old_auditor_remains_exact_not_a_new_failure(monkeypatch):
    archived, _ = c.historical_auditor(ROOT)
    read = c.regular
    monkeypatch.setattr(c, "regular", lambda path: archived if Path(path) == ROOT / c.AUDITOR else read(path))
    c.verify_inputs(ROOT, historical_reporting=False)
    _, record = c.historical_auditor(ROOT)
    assert record["original_exact_source_check"] == "PASS"


def test_git_requests_are_local_read_only_and_ignore_ambient_overrides(monkeypatch):
    run = c.subprocess.run
    commands = []
    def capture(args, **kwargs):
        commands.append((args, kwargs))
        assert args[:4] == ["git", "--no-replace-objects", "cat-file", "blob"]
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        assert "GIT_DIR" not in kwargs["env"] and "GIT_WORK_TREE" not in kwargs["env"]
        return run(args, **kwargs)
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    monkeypatch.setenv("GIT_WORK_TREE", "/nonexistent")
    monkeypatch.setattr(c.subprocess, "run", capture)
    c.historical_auditor(ROOT)
    assert len(commands) == 2
