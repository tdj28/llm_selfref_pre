"""Support unchanged public artifacts without weakening unknown-path checks."""
import hashlib
import json
import subprocess

import pytest

from scripts import audit_public_release as a


PATH = next(iter(a.HASH_MAP_MANIFESTS))
BASE = PATH.rsplit("/", 1)[0]


def manifest(**updates):
    return {"schema": a.HASH_MAP_MANIFESTS[PATH], "release": BASE,
            "file_count": 1, "files": {"example.txt": hashlib.sha256(b"ok").hexdigest()}, **updates}


def check(value, records=None, path=PATH):
    return a.release_manifest_findings({path: json.dumps(value).encode()}, records or {})


def test_known_hash_map_verifies_actual_bytes():
    findings, n = check(manifest(), {BASE + "/example.txt": (2, hashlib.sha256(b"ok").hexdigest())})
    assert not findings and n == 1


def test_hash_map_rejects_drift_and_untracked():
    findings, n = check(manifest(), {BASE + "/example.txt": (2, hashlib.sha256(b"no").hexdigest())})
    assert n == 0 and findings[0].rule == "release-hash-mismatch"
    findings, n = check(manifest())
    assert n == 0 and findings[0].rule == "untracked-release-file"


@pytest.mark.parametrize("updates", [{"schema": "other"}, {"file_count": 2},
    {"file_count": True}, {"release": "elsewhere"}, {"files": {}}, {"files": []}])
def test_invalid_hash_map_rejected(updates):
    findings, n = check(manifest(**updates))
    assert n == 0 and findings[0].rule == "invalid-release-manifest"


@pytest.mark.parametrize("path", sorted(a.HASH_MAP_MANIFESTS))
def test_each_known_map_needs_its_own_schema(path):
    base = path.rsplit("/", 1)[0]
    value = {"schema": a.HASH_MAP_MANIFESTS[path], "release": base, "file_count": 1,
             "files": {"example.txt": hashlib.sha256(b"ok").hexdigest()}}
    findings, n = check(value, {base + "/example.txt": (2, hashlib.sha256(b"ok").hexdigest())}, path)
    assert not findings and n == 1
    for schema in set(a.HASH_MAP_MANIFESTS.values()) - {value["schema"]}:
        findings, n = check({**value, "schema": schema}, path=path)
        assert n == 0 and findings[0].rule == "invalid-release-manifest"


def test_unknown_manifest_not_allowed_to_switch_format():
    findings, n = check(manifest(), path="data/other/RELEASE_MANIFEST.json")
    assert n == 0 and findings[0].rule == "invalid-release-manifest"


@pytest.mark.parametrize("name,rule", [("../escape", "unsafe-release-path"),
                                       ("/absolute", "unsafe-release-path")])
def test_unsafe_map_path_rejected(name, rule):
    findings, n = check(manifest(files={name: hashlib.sha256(b"ok").hexdigest()}))
    assert n == 0 and findings[0].rule == rule


def test_invalid_map_hash_rejected():
    findings, n = check(manifest(files={"example.txt": "invalid"}))
    assert n == 0 and findings[0].rule == "invalid-release-entry"


@pytest.mark.parametrize("value", [[], None, "invalid"])
def test_nondictionary_known_manifest_rejected(value):
    findings, n = check(value)
    assert n == 0 and findings[0].rule == "invalid-release-manifest"


def test_license_exemption_requires_exact_bytes(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "license.txt"
    raw = b"Unmodified upstream text.  \n"
    monkeypatch.setattr(a, "PRESERVED_SOURCE_BYTES", {"license.txt": hashlib.sha256(raw).hexdigest()})
    path.write_bytes(raw)
    subprocess.run(["git", "-C", str(tmp_path), "add", "license.txt"], check=True)
    assert a.whitespace_findings(tmp_path) == []
    path.write_bytes(raw + b"Changed content.  \n")
    assert {f.rule for f in a.whitespace_findings(tmp_path)} == {"working-tree-whitespace"}
    subprocess.run(["git", "-C", str(tmp_path), "add", "license.txt"], check=True)
    assert {f.rule for f in a.whitespace_findings(tmp_path)} == {"index-whitespace"}


def test_unknown_whitespace_still_fails(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "unknown.txt").write_text("unknown  \n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "unknown.txt"], check=True)
    assert a.whitespace_findings(tmp_path)
