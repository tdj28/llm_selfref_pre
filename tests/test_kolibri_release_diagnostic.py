"""Synthetic offline diagnostics: exact differences, binding guards, no tolerance."""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kolibri_diagnostic_under_test",
                                            HERE / "scripts/diagnose_kolibri_release.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in diagnostic tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def case(tmp_path, monkeypatch):
    source = tmp_path / d.RELEASE
    source.mkdir(parents=True)
    code = tmp_path / d.REPORTER
    code.parent.mkdir(parents=True)
    code.write_bytes(b"# synthetic reporter\n")
    derived = {"main_analysis.json": {"interval": [0.25, 0.75], "count": 3},
               "screen_analysis.json": {"interval": [-0.25, 0.5], "complete": True}}
    exporter = {"schema": "kolibri-exporter-v1", "source_hashes": {d.REPORTER: d.sha(code.read_bytes())}}
    def receipts(values, images):
        return {"data_sha256": d.sha(d.canonical(values).encode()),
                "image_sha256": {k: d.sha(v) for k, v in images.items()}}
    images = {name: b"synthetic image bytes" for name in ("figures/cells.png", "figures/primary.png")}
    blobs = {**{name: d.canonical(value).encode() for name, value in derived.items()},
             "EXPORTER.json": d.canonical(exporter).encode(), "SUMMARY.md": b"Synthetic summary\n",
             "FIGURES.json": d.canonical(receipts(derived, images)).encode(), **images}
    for name, raw in blobs.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest = {"schema": "kolibri-release-manifest-v1", "files": [
        {"path": name, "bytes": len(raw), "sha256": d.sha(raw)} for name, raw in sorted(blobs.items())]}
    raw = d.canonical(manifest).encode()
    (source / "MANIFEST.json").write_bytes(raw)
    monkeypatch.setattr(d, "MANIFEST_SHA", d.sha(raw))
    snapshots = []
    def derive(path):
        assert path != source and path.is_dir()
        assert (path / "main_analysis.json").read_bytes() == blobs["main_analysis.json"]
        snapshots.append(path)
        return deepcopy(derived)
    reporter = SimpleNamespace(SOURCES=(d.REPORTER,), DEPENDENCIES=(), JSON_OUTPUTS=set(derived),
                               inventory=lambda path: {}, allowed=lambda *args: None,
                               derive=derive, figure_receipts=receipts, summary=lambda _: blobs["SUMMARY.md"])
    monkeypatch.setattr(d, "load_reporter", lambda root: reporter)
    return tmp_path, source, derived, reporter, snapshots


def test_complete_exact_diagnostic_is_readonly_and_removes_snapshot(case):
    root, source, _, _, snapshots = case
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = d.diagnose(root)
    assert result["exact_replay"] and result["frozen_derived_comparison_equal"]
    assert result["difference_count"] == 0 and len(result["files"]) == 3
    assert result["normal_dist_z"] == d.NormalDist().inv_cdf(0.975)
    assert result["normal_dist_z_hex"] == result["normal_dist_z"].hex()
    assert snapshots and all(not path.exists() for path in snapshots)
    assert str(root) not in d.canonical(result)
    assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}


def test_all_differing_json_paths_types_hex_and_whole_hashes_are_reported(case):
    root, _, derived, _, _ = case
    derived["main_analysis.json"]["interval"][0] = math.nextafter(0.25, math.inf)
    derived["screen_analysis.json"]["interval"][1] = math.nextafter(0.5, math.inf)
    result = d.diagnose(root)
    assert not result["exact_replay"] and not result["frozen_derived_comparison_equal"]
    floats = [row for row in result["differences"] if row["kind"] == "float"]
    assert len(floats) == 2 and {row["file"] for row in floats} == set(derived)
    for row in floats:
        assert row["saved_type"] == row["replay_type"] == "float" and row["ulp_distance"] == 1
        assert row["saved_hex"] != row["replay_hex"] and row["absolute_error"] > 0
        assert row["path"].startswith("/interval/")
    assert all(not row["exact_typed_replay"] for row in result["files"].values())


@pytest.mark.parametrize("saved,replay", [(1, True), (1, 1.0), (-0.0, 0.0), (3, 4), ([1], [1, 2]),
                                          ({"a/b~c": 1}, {"a/b~c": 2}), ({"missing": 1}, {})])
def test_exact_types_counts_keys_lengths_and_signed_zero(saved, replay):
    record, delta = d.compare("test.json", d.canonical(saved).encode(), replay)
    assert delta and not record["exact_typed_replay"]
    assert all("saved_type" in row and "replay_type" in row for row in delta)
    if isinstance(saved, dict) and "a/b~c" in saved:
        assert delta[0]["path"] == "/a~1b~0c"


def test_string_values_are_hash_only():
    secret = "private-response-content-not-for-logs"
    _, delta = d.compare("test.json", json.dumps({"response": secret}).encode(), {"response": secret + "x"})
    assert secret not in json.dumps(delta)
    assert delta[0]["saved"]["type"] == "str"


@pytest.mark.parametrize("name", ["MANIFEST.json", "main_analysis.json", "EXPORTER.json", "extra.json"])
def test_release_tamper_rejected_before_loading_reporter(case, monkeypatch, name):
    root, source, _, _, _ = case
    path = source / name
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b" ")
    monkeypatch.setattr(d, "load_reporter", lambda root: pytest.fail("Loaded unbound reporter"))
    with pytest.raises(ValueError):
        d.diagnose(root)


def test_reporter_source_tamper_rejected_before_import(case, monkeypatch):
    root, _, _, _, _ = case
    (root / d.REPORTER).write_bytes(b"# changed\n")
    monkeypatch.setattr(d, "load_reporter", lambda root: pytest.fail("Loaded changed reporter"))
    with pytest.raises(ValueError, match="Bound exporter source changed"):
        d.diagnose(root)


def test_mutation_during_replay_fails(case):
    root, source, _, reporter, _ = case
    original = reporter.derive
    def changed(path):
        (source / "main_analysis.json").write_bytes(b"{}")
        return original(path)
    reporter.derive = changed
    with pytest.raises(ValueError, match="Bound release artifact changed"):
        d.diagnose(root)


def test_replay_exception_removes_snapshot(case):
    root, _, _, reporter, snapshots = case
    def broken(path):
        snapshots.append(path)
        raise RuntimeError("failed replay")
    reporter.derive = broken
    with pytest.raises(RuntimeError):
        d.diagnose(root)
    assert snapshots and not snapshots[0].exists()


@pytest.mark.parametrize("exact,status", [(True, 0), (False, 1)])
def test_cli_keeps_exact_or_mismatch_status(monkeypatch, capsys, exact, status):
    hooks = []
    monkeypatch.setattr(d.sys, "addaudithook", hooks.append)
    monkeypatch.setattr(d, "diagnose", lambda root: {"exact_replay": exact})
    assert d.main([]) == status
    assert json.loads(capsys.readouterr().out)["exact_replay"] is exact
    with pytest.raises(RuntimeError, match="Network forbidden"):
        hooks[0]("socket.connect", ())


def test_cli_error_does_not_echo_exception_content(monkeypatch, capsys):
    monkeypatch.setattr(d.sys, "addaudithook", lambda hook: None)
    def broken(root):
        raise RuntimeError("private raw response /Users/private/file")
    monkeypatch.setattr(d, "diagnose", broken)
    assert d.main([]) == 2
    text = capsys.readouterr().out
    assert "private raw" not in text and "/Users/" not in text
