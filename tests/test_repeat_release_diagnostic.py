import math
import json
from types import SimpleNamespace

import pytest

from scripts import diagnose_repeat_release as diagnostic


def test_exact_values_and_mapping_order():
    assert diagnostic.differences({"x": [1, 0.5, True], "y": None},
                                  {"y": None, "x": [1, 0.5, True]}) == []


@pytest.mark.parametrize("saved,replay", [(1, True), (1, 1.0), (False, 0)])
def test_types_are_not_coerced(saved, replay):
    assert diagnostic.differences(saved, replay)[0]["kind"] == "type"


@pytest.mark.parametrize("value,direction", [(1.0, math.inf), (1.0, -math.inf), (-1.0, -math.inf),
                                            (0.0, math.inf), (-0.0, -math.inf)])
def test_single_ulp_and_power_of_two_boundaries(value, direction):
    replay = math.nextafter(value, direction)
    result = diagnostic.differences(value, replay)[0]
    assert result["ulp_distance"] == 1
    assert float.fromhex(result["saved_hex"]) == value
    assert float.fromhex(result["replay_hex"]) == replay
    assert result["absolute_error"] == abs(value - replay)


def test_signed_zero_is_not_silently_equal():
    assert diagnostic.differences(-0.0, 0.0)[0]["ulp_distance"] == 1


def test_paths_are_exact_and_structural_changes_are_visible():
    diffs = diagnostic.differences({"a/b": [1, 2], "gone": True}, {"a/b": [1], "new": True}, "file.json")
    assert [(d["path"], d["kind"]) for d in diffs] == [
        ("file.json/a~1b", "length"), ("file.json/gone", "key"), ("file.json/new", "key")]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_values_are_rejected(value):
    with pytest.raises(ValueError):
        diagnostic.differences(value, value)


def test_no_drift_is_accepted_as_a_tolerance():
    result = diagnostic.differences(1.0, 1.5)[0]
    assert result["absolute_error"] == 0.5 and result["ulp_distance"] > 1


@pytest.mark.parametrize("exact,code", [(True, 0), (False, 1)])
def test_cli_preserves_mismatch_failure(monkeypatch, capsys, exact, code):
    monkeypatch.setattr(diagnostic, "diagnose", lambda root: {"exact_replay": exact})
    assert diagnostic.main([]) == code
    assert '"exact_replay"' in capsys.readouterr().out


def test_failed_replay_is_not_a_pass(monkeypatch, capsys):
    def fail(root):
        raise ValueError("bound input changed")
    monkeypatch.setattr(diagnostic, "diagnose", fail)
    assert diagnostic.main([]) == 2
    assert "bound input changed" in capsys.readouterr().out


@pytest.fixture
def fixture_release(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    source = root / diagnostic.RELEASE
    source.mkdir(parents=True)
    name = "experiments/repeat_funding_release_a1.py"
    reporter_path = root / name
    reporter_path.parent.mkdir()
    reporter_path.write_bytes(b"bound reporter fixture\n")
    metadata = {"source_hashes": {name: diagnostic.sha(reporter_path.read_bytes())}}
    def write(path, value):
        path.write_text(diagnostic.canonical(value) + "\n")
    write(source / "RELEASE.json", metadata)
    write(source / "input.json", {"estimate": 0.5})
    write(source / "analysis.json", {"estimate": 0.5})
    def entries(directory):
        return [{"path": path.name, "bytes": len(path.read_bytes()), "sha256": diagnostic.sha(path.read_bytes())}
                for path in sorted(directory.iterdir()) if path.name != "MANIFEST.json"]
    write(source / "MANIFEST.json", {"schema": "fixture", "files": entries(source)})
    monkeypatch.setattr(diagnostic, "MANIFEST_SHA", diagnostic.sha((source / "MANIFEST.json").read_bytes()))
    calls = []
    def derive(snapshot):
        calls.append(snapshot)
        assert snapshot != source and source not in snapshot.parents
        assert not (snapshot / "analysis.json").exists()
        return {"RELEASE.json": metadata, "analysis.json": json.loads((snapshot / "input.json").read_text())}
    reporter = SimpleNamespace(__file__=str(reporter_path), OWN_SOURCES=(name,),
        MANIFEST_SCHEMA="fixture", DERIVED={"RELEASE.json", "analysis.json"}, A2_DERIVED=set(), A3_DERIVED=set(),
        _inventory=lambda directory, **kwargs: [p.name for p in directory.iterdir()], _derive=derive,
        p=SimpleNamespace(canonical=diagnostic.canonical),
        base=SimpleNamespace(_no_symlinks=lambda path: None, _entries=entries,
                             _load=lambda path: json.loads(path.read_text())))
    monkeypatch.setattr(diagnostic.importlib, "import_module", lambda name: reporter)
    return root, source, reporter, calls


def test_diagnostic_replays_copy_and_preserves_input_bytes(fixture_release):
    root, source, reporter, calls = fixture_release
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    report = diagnostic.diagnose(root)
    assert report["exact_replay"] and report["difference_count"] == 0 and len(calls) == 1
    assert str(root) not in diagnostic.canonical(report)
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}
    assert not calls[0].exists()


@pytest.mark.parametrize("filename", ["MANIFEST.json", "input.json", "reporter"])
def test_changed_manifest_input_or_source_fails_before_replay(fixture_release, filename):
    root, source, reporter, calls = fixture_release
    path = root / reporter.OWN_SOURCES[0] if filename == "reporter" else source / filename
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="differs|differ"):
        diagnostic.diagnose(root)
    assert not calls


def test_diagnostic_exposes_small_numeric_drift_without_accepting_it(fixture_release):
    root, source, reporter, calls = fixture_release
    original = reporter._derive
    def derive(snapshot):
        result = original(snapshot)
        result["analysis.json"]["estimate"] = math.nextafter(0.5, math.inf)
        return result
    reporter._derive = derive
    report = diagnostic.diagnose(root)
    assert not report["exact_replay"] and report["difference_count"] == 1
    assert report["differences"][0]["path"] == "analysis.json/estimate"
    assert report["differences"][0]["ulp_distance"] == 1
