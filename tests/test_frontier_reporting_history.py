"""Historical provenance stays pinned while the current public auditor evolves."""
import hashlib
import json

import pytest

from scripts import release_frontier_b1 as r


def actual():
    raw = (r.protocol.ROOT / r.ARCHIVED_MANIFEST_PATH).read_bytes()
    current = {name: r.sha(r.protocol.ROOT / name) for name in r.REPORTING_SOURCES}
    return raw, current


def test_actual_history_is_verified_against_git():
    raw, current = actual()
    assert r._verified_reporting_sources(raw, current) == json.loads(raw)["reporting_source_hashes"]


def test_current_manifest_needs_no_archived_exception(monkeypatch):
    current = {name: "a" * 64 for name in r.REPORTING_SOURCES}
    monkeypatch.setattr(r, "_git", lambda *args: pytest.fail("Unneeded historical read"))
    raw = json.dumps({"reporting_source_hashes": current}).encode()
    assert r._verified_reporting_sources(raw, current) == current


@pytest.mark.parametrize("field", ["reporting_source_hashes", "interpretation", "receipt_audit"])
def test_historical_manifest_cannot_be_resealed(field):
    raw, current = actual()
    changed = json.loads(raw)
    changed[field] = {}
    with pytest.raises(ValueError, match="unknown reporting history"):
        r._verified_reporting_sources(json.dumps(changed).encode(), current)


def test_historical_source_must_match_snapshot(monkeypatch):
    raw, current = actual()
    original = r._git
    def altered(*args):
        if args == ("cat-file", "blob", f"{r.ARCHIVED_REPORTING_COMMIT}:scripts/audit_public_release.py"):
            return b"Different auditor"
        return original(*args)
    monkeypatch.setattr(r, "_git", altered)
    with pytest.raises(ValueError, match="source hash differs"):
        r._verified_reporting_sources(raw, current)


def test_historical_manifest_must_match_snapshot(monkeypatch):
    raw, current = actual()
    original = r._git
    def altered(*args):
        if args == ("cat-file", "blob", f"{r.ARCHIVED_REPORTING_COMMIT}:{r.ARCHIVED_MANIFEST_PATH}"):
            return raw + b"\n"
        return original(*args)
    monkeypatch.setattr(r, "_git", altered)
    with pytest.raises(ValueError, match="manifest differs"):
        r._verified_reporting_sources(raw, current)


def test_unknown_source_inventory_not_accepted_even_with_test_pin(monkeypatch):
    raw, current = actual()
    changed = json.loads(raw)
    changed["reporting_source_hashes"]["other.py"] = "b" * 64
    raw = json.dumps(changed).encode()
    monkeypatch.setattr(r, "ARCHIVED_MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(r, "_git", lambda *args: raw)
    with pytest.raises(ValueError, match="inventory differs"):
        r._verified_reporting_sources(raw, current)
