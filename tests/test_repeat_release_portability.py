"""No test delegation: original suites remain collected; real release replay is mandatory."""
from copy import deepcopy
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import socket

import pytest

HERE = Path(__file__).resolve().parents[1]
# Allows testing these additive files against the parent's checkout without copying or editing it.
ROOT = Path(os.environ.get("REPEAT_PORTABILITY_ROOT", HERE)).resolve()
spec = importlib.util.spec_from_file_location("repeat_portability_under_test", HERE / "experiments/repeat_release_portability.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Portability verification must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture(scope="module")
def saved():
    return json.loads((ROOT / c.RELEASE / "analysis.json").read_bytes())


@pytest.fixture
def linux(saved):
    result = deepcopy(saved)
    c._interval(result)[0] = float.fromhex(c.LINUX_HEX)
    return result


def test_both_observed_platform_reports_and_original_failure_are_bound():
    evidence, files = c.observations()
    assert evidence["original_strict_failure"] == "Derived funding release does not reconstruct"
    assert evidence["diagnostic_commit"] == "4a4c613a024e8900dd30f300b0bd084ddf5826cb"
    assert [o["job_id"] for o in evidence["observations"]] == [111736011735, 111736011780]
    for observation in evidence["observations"]:
        report = observation["diagnostic"]
        assert observation["conclusion"] == "failure" and report["exact_replay"] is False
        assert report["manifest_sha256"] == c.MANIFEST_SHA
        assert report["difference_count"] == 1 and report["differences"][0]["ulp_distance"] == 1
        assert report["differences"][0]["saved_hex"] == c.SAVED_HEX
        assert report["differences"][0]["replay_hex"] == c.LINUX_HEX
    assert len(files) == 9 and sum(row["exact"] for row in files.values()) == 8


def test_exact_and_measured_entire_analysis_outputs_only(saved, linux):
    assert c.value_sha(saved) == c.SAVED_SHA and c.value_sha(linux) == c.LINUX_SHA
    for original, exact in ((saved, True), (linux, False)):
        before = c.canonical(original)
        result, record = c.normalize_analysis(original)
        assert c.canonical(result) == c.canonical(saved)
        assert record["exact_replay"] is exact and record["accepted_known_float_pair"] is not exact
        assert c.canonical(original) == before
        assert str(ROOT) not in c.canonical(record)


@pytest.mark.parametrize("change", ["two_ulp", "opposite_ulp", "type", "other_path", "count", "zero_cross", "order"])
def test_any_unmeasured_drift_is_rejected(saved, change):
    value = deepcopy(saved)
    interval = c._interval(value)
    if change == "two_ulp":
        interval[0] = math.nextafter(float.fromhex(c.LINUX_HEX), math.inf)
    elif change == "opposite_ulp":
        interval[0] = math.nextafter(interval[0], -math.inf)
    elif change == "type":
        interval[0] = str(interval[0])
    elif change == "other_path":
        interval[1] = math.nextafter(interval[1], math.inf)
    elif change == "count":
        value["inventory"]["observed_records"] -= 1
    elif change == "zero_cross":
        interval[0] = abs(interval[0])
    else:
        interval.reverse()
    with pytest.raises(ValueError, match="Unmeasured"):
        c.normalize_analysis(value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_values_fail(saved, value):
    changed = deepcopy(saved)
    c._interval(changed)[0] = value
    with pytest.raises(ValueError):
        c.normalize_analysis(changed)


@pytest.mark.parametrize("name", [c.RELEASE + "/MANIFEST.json", c.RELEASE + "/raw/events.jsonl.gz",
                                  "experiments/repeated_swap/analysis.py",
                                  "experiments/repeat_funding_release_a1.py",
                                  "experiments/repeat_publication.py", "scripts/verify_repeated_extension.py",
                                  c.BINDING, c.PACKAGE + "/repeated_main.pdf"])
def test_manifest_raw_source_binding_and_figure_tamper_rejected(monkeypatch, name):
    original = c.regular
    def read(path):
        raw = original(path)
        return raw + b" " if Path(path) == ROOT / name else raw
    monkeypatch.setattr(c, "regular", read)
    with pytest.raises(ValueError, match="changed"):
        c.verify_inputs(ROOT)


def test_archived_diagnostics_cannot_be_replaced(tmp_path):
    path = tmp_path / "changed.json"
    path.write_bytes(c.EVIDENCE.read_bytes() + b" ")
    with pytest.raises(ValueError, match="sidecar changed"):
        c.observations(path)


@pytest.mark.parametrize("flag", ["--write", "--wr", "--w"])
def test_entrypoint_never_allows_publication_writes(flag):
    with pytest.raises(ValueError, match="verification-only"):
        c.main([flag])


def test_original_completed_paper_verifier_runs_without_mutating_release(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    analysis = importlib.import_module("experiments.repeated_swap.analysis")
    binder = importlib.import_module("scripts.verify_repeated_extension")
    original = analysis.analyze
    with c.portable_replay(ROOT) as report:
        verdict = binder.check_binding(ROOT / c.RELEASE, ROOT / c.PACKAGE, ROOT / c.BINDING,
            release_manifest_sha256=c.MANIFEST_SHA, publication_manifest_sha256=c.PACKAGE_SHA,
            paper=True, require_pinned=True)
    assert verdict["pass"] and len(report["local_replays"]) == 2
    assert analysis.analyze is original
    assert all(row["observed_analysis_sha256"] in (c.SAVED_SHA, c.LINUX_SHA) for row in report["local_replays"])


def test_original_strict_still_fails_for_measured_linux_output_and_restores(monkeypatch, linux):
    monkeypatch.syspath_prepend(str(ROOT))
    reporter = importlib.import_module("experiments.repeat_funding_release_a1")
    analysis = reporter.base.analysis
    original = analysis.analyze
    def measured(rows, phase="main"):
        if phase == "main" and c.value_sha(rows) == c.ROWS_SHA:
            return deepcopy(linux)
        return original(rows, phase)
    monkeypatch.setattr(analysis, "analyze", measured)
    with pytest.raises(reporter.base.Halted, match="Derived funding release does not reconstruct"):
        reporter.verify(ROOT / c.RELEASE, manifest_sha256=c.MANIFEST_SHA)
    with c.portable_replay(ROOT) as report:
        assert reporter.verify(ROOT / c.RELEASE, manifest_sha256=c.MANIFEST_SHA)["pass"]
    assert report["local_replays"][0]["accepted_known_float_pair"]
    assert analysis.analyze is measured
    with pytest.raises(RuntimeError, match="caller failure"):
        with c.portable_replay(ROOT):
            raise RuntimeError("caller failure")
    assert analysis.analyze is measured


def test_foreign_manifest_cannot_use_known_pair(monkeypatch, tmp_path, linux):
    monkeypatch.syspath_prepend(str(ROOT))
    reporter = importlib.import_module("experiments.repeat_funding_release_a1")
    analysis = reporter.base.analysis
    rows = json.loads((ROOT / c.RELEASE / "rows.json").read_bytes())
    monkeypatch.setattr(analysis, "analyze", lambda rows, phase="main": deepcopy(linux))
    def strict(destination, *, manifest_sha256=None):
        return analysis.analyze(rows)
    monkeypatch.setattr(reporter, "verify", strict)
    (tmp_path / "MANIFEST.json").write_text("{}\n")
    with c.portable_replay(ROOT) as report:
        assert c.value_sha(reporter.verify(tmp_path)) == c.LINUX_SHA
        assert c.value_sha(reporter.verify(ROOT / c.RELEASE, manifest_sha256="0" * 64)) == c.LINUX_SHA
        assert not report["local_replays"]
        assert c.value_sha(reporter.verify(ROOT / c.RELEASE, manifest_sha256=c.MANIFEST_SHA)) == c.SAVED_SHA
    assert reporter.verify is strict


@pytest.mark.parametrize("name", ["RELEASE.json", "rows.json", "audit.json", "funding_audit.json",
                                  "transport_audit.json", "refusal_audit.json", "epoch_timing.json",
                                  "logical_projection.json"])
def test_every_other_derived_file_keeps_original_exact_comparison(monkeypatch, name):
    monkeypatch.syspath_prepend(str(ROOT))
    reporter = importlib.import_module("experiments.repeat_funding_release_a1")
    _, files = c.observations()
    derived = {n: json.loads((ROOT / c.RELEASE / n).read_bytes()) for n in files}
    if isinstance(derived[name], list):
        derived[name].pop()
    else:
        derived[name]["unapproved_change"] = True
    monkeypatch.setattr(reporter, "_derive", lambda snapshot: derived)
    with c.portable_replay(ROOT):
        with pytest.raises(reporter.base.Halted, match="Derived funding release does not reconstruct"):
            reporter.verify(ROOT / c.RELEASE, manifest_sha256=c.MANIFEST_SHA)
