"""Offline reference replay, bound to both original hosted failure observations."""
from copy import deepcopy
import importlib
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
from statistics import NormalDist

import pytest

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("KOLIBRI_PORTABILITY_ROOT", HERE)).resolve()
spec = importlib.util.spec_from_file_location("kolibri_wilson_portability_under_test",
                                            HERE / "experiments/kolibri_wilson_portability.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    def forbidden(*args, **kwargs):
        raise AssertionError("Portability tests must remain offline")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


@pytest.fixture
def modules():
    common = importlib.import_module("experiments.openrouter_swap.analysis")
    analysis = importlib.import_module("experiments.kolibri_swap.analysis")
    return common, analysis


def native(monkeypatch, common, value):
    class ObservedNormal:
        def inv_cdf(self, probability):
            assert probability == 0.975
            return value
    monkeypatch.setattr(common, "NormalDist", ObservedNormal)


def test_public_entrypoint_requires_archived_hosted_evidence(monkeypatch):
    monkeypatch.setattr(c, "HOSTED_EVIDENCE_SHA256", "not-an-activation")
    with pytest.raises(ValueError, match="Hosted observation provenance changed"):
        c.verify(ROOT)


def test_reference_reuses_frozen_formula_without_mutating_global_normal(modules, monkeypatch):
    common, _ = modules
    original = common._wilson
    native(monkeypatch, common, float.fromhex(c.REFERENCE_Z_HEX))
    reference = c.reference_wilson(original)
    assert reference.__code__ is original.__code__ and reference.__globals__ is not original.__globals__
    for n in range(97):
        for positive in range(n + 1):
            assert reference(positive, n) == original(positive, n)
    assert NormalDist().inv_cdf(.975).hex() in (c.REFERENCE_Z_HEX, c.LINUX_Z_HEX)


@pytest.mark.parametrize("value", [math.nan, math.inf, "1.9599639845400534", 2,
                                  float.fromhex("0x1.f5c0331eeff80p+0"),
                                  float.fromhex("0x1.f5c0331eeff83p+0")])
def test_unknown_native_quantiles_rejected_before_patching(modules, monkeypatch, value):
    common, analysis = modules
    before = common._wilson, analysis.analyze, analysis.qualify
    native(monkeypatch, common, value)
    with pytest.raises(ValueError, match="Unmeasured native Wilson quantile"):
        with c.reference_replay(ROOT):
            pytest.fail("Unknown quantile entered reference replay")
    assert before == (common._wilson, analysis.analyze, analysis.qualify)


@pytest.mark.parametrize("name", [c.RELEASE + "/MANIFEST.json", c.RELEASE + "/main_rows.json",
                                  c.PACKAGE + "/BINDING.json", c.PACKAGE + "/figure_data.json",
                                  "experiments/openrouter_swap/analysis.py",
                                  "experiments/kolibri_swap/analysis.py", "experiments/kolibri_release.py",
                                  "scripts/verify_kolibri_extension.py"])
def test_unknown_bundle_or_source_rejected(monkeypatch, name):
    original = c.regular
    monkeypatch.setattr(c, "regular", lambda path: original(path) + (b" " if Path(path) == ROOT / name else b""))
    with pytest.raises(ValueError, match="changed"):
        c.verify_inputs(ROOT)


def test_unbound_rows_are_rejected_and_unrelated_wilson_calls_remain_native(modules, monkeypatch):
    common, analysis = modules
    native(monkeypatch, common, float.fromhex(c.LINUX_Z_HEX))
    original = common._wilson
    rows = json.loads((ROOT / c.RELEASE / "main_rows.json").read_bytes())
    rows[0]["cap_hit"] = not rows[0]["cap_hit"]
    with c.reference_replay(ROOT):
        assert common._wilson(3, 32) == original(3, 32)
        with pytest.raises(ValueError, match="Unbound Kolibri analysis rows"):
            analysis.analyze(rows, "main")
        with pytest.raises(ValueError, match="Unbound Kolibri qualification rows"):
            analysis.qualify(rows)


def test_unknown_analysis_field_rejected_even_when_python_equality_could_pass(modules, monkeypatch):
    _, analysis = modules
    rows = json.loads((ROOT / c.RELEASE / "main_rows.json").read_bytes())
    saved = json.loads((ROOT / c.RELEASE / "main_analysis.json").read_bytes())
    saved["inventory_valid"] = 1
    monkeypatch.setattr(analysis, "analyze", lambda rows, phase: deepcopy(saved))
    with c.reference_replay(ROOT):
        with pytest.raises(ValueError, match="Unknown whole-analysis replay variation"):
            analysis.analyze(rows, "main")


def test_context_restores_after_caller_error(modules):
    common, analysis = modules
    before = common._wilson, analysis.analyze, analysis.qualify, common.NormalDist
    imports = sys.path[:]
    with pytest.raises(RuntimeError, match="caller failed"):
        with c.reference_replay(ROOT):
            raise RuntimeError("caller failed")
    assert before == (common._wilson, analysis.analyze, analysis.qualify, common.NormalDist)
    assert sys.path == imports


def test_simulated_linux_fails_strict_then_replays_original_reporter_binder_and_tables(modules, monkeypatch):
    common, analysis = modules
    native(monkeypatch, common, float.fromhex(c.LINUX_Z_HEX))
    rows = json.loads((ROOT / c.RELEASE / "screen_rows.json").read_bytes())
    saved = json.loads((ROOT / c.RELEASE / "screen_analysis.json").read_bytes())
    strict = analysis.analyze(rows, "screen")
    assert c.value_sha(strict) != c.value_sha(saved)
    before = common._wilson, analysis.analyze, analysis.qualify, common.NormalDist
    result = c.verify(ROOT)
    report = result["kolibri_wilson_portability"]
    assert result["paper_verification"]["pass"]
    assert report["original_hosted_exact_replay"] == "FAIL"
    assert report["hosted_evidence_sha256"] == c.HOSTED_EVIDENCE_SHA256
    assert report["analysis_replays"] == ["screen", "main", "screen", "main"]
    assert report["qualification_replays"] > 0
    assert str(ROOT) not in json.dumps(report)
    assert before == (common._wilson, analysis.analyze, analysis.qualify, common.NormalDist)
    assert c.value_sha(analysis.analyze(rows, "screen")) != c.value_sha(saved)


def test_complete_observations_include_zero_boundary_changes(modules):
    evidence, report = c.observations()
    c.validate_observed_outputs(ROOT, report, modules[0])
    assert len(evidence["observations"]) == 2
    assert sum(d["kind"] == "float" for d in report["differences"]) == 622
    assert sum(d["kind"] == "str" for d in report["differences"]) == 1
    assert sum(d["kind"] == "float" and d["saved"] == 0 and d["replay"] != 0
               for d in report["differences"]) == 8


@pytest.mark.parametrize("name", ["OBSERVATIONS.json", "py310.json", "py312.json"])
def test_archived_evidence_byte_tamper_rejected(monkeypatch, name):
    regular = c.regular
    target = c.EVIDENCE.parent / name
    monkeypatch.setattr(c, "regular", lambda path: regular(path) + (b" " if Path(path) == target else b""))
    with pytest.raises(ValueError, match="Hosted .* changed"):
        c.observations()


@pytest.mark.parametrize("change", ["path", "type", "value", "inventory", "whole_hash"])
def test_unknown_observed_changes_rejected(modules, change):
    _, report = c.observations()
    row = next(d for d in report["differences"] if d["kind"] == "float")
    if change == "path":
        row["path"] = "/counts/positive"
    elif change == "type":
        row["replay_type"] = "int"
    elif change == "value":
        row["replay"] = math.nextafter(row["replay"], math.inf)
        row["replay_hex"] = row["replay"].hex()
    elif change == "inventory":
        report["differences"].pop()
    else:
        report["files"]["main_analysis.json"]["replay_canonical_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        c.validate_observed_outputs(ROOT, report, modules[0])


def test_cli_is_readonly_and_installs_network_denial(monkeypatch, capsys):
    hooks = []
    monkeypatch.setattr(c.sys, "addaudithook", hooks.append)
    monkeypatch.setattr(c, "verify", lambda root: {"offline": True})
    assert c.main(["--root", str(ROOT)]) == 0
    assert json.loads(capsys.readouterr().out) == {"offline": True}
    for event in ("socket.connect", "socket.getaddrinfo", "socket.bind"):
        with pytest.raises(RuntimeError, match="Network forbidden"):
            hooks[0](event, ())
    with pytest.raises(SystemExit):
        c.main(["--write"])


@pytest.mark.parametrize("entry", ["module", "script"])
def test_both_cli_entrypoints_reject_invalid_root(tmp_path, entry):
    target = (["-m", "experiments.kolibri_wilson_portability"] if entry == "module" else
              [str(HERE / "scripts/verify_kolibri_portable.py")])
    result = subprocess.run([sys.executable, "-B", *target, "--root", str(tmp_path / "absent")],
                            cwd=HERE, capture_output=True, text=True,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30)
    assert result.returncode != 0 and "Missing/nonregular" in result.stderr
    assert not result.stdout
