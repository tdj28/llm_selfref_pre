"""Fail-closed regressions for the publication-only compatibility contexts."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.register_assert_rewrite("scripts.publication_test_compat")
from scripts import publication_test_compat as c
from scripts import verify_repeated_presentation_portable as repeated

pytest_plugins = ("scripts.publication_test_compat",)


def test_repeated_loader_uses_tracked_case_on_case_insensitive_hosts(monkeypatch):
    read = Path.read_bytes
    names = []
    def case_sensitive(path):
        if path.parent == repeated.ROOT / repeated.original.SOURCE:
            names.append(path.name)
            if path.name == "manifest.json":
                raise FileNotFoundError("Simulated case-sensitive filesystem")
        return read(path)
    monkeypatch.setattr(Path, "read_bytes", case_sensitive)
    with pytest.raises(FileNotFoundError):
        repeated.original.load()
    assert repeated.verify()["pass"]
    assert names.count("manifest.json") == 1 and "MANIFEST.json" in names


@pytest.mark.parametrize("name", ["MANIFEST.json", "figure_data.json", "binding.json"])
def test_repeated_loader_rejects_changed_source_bytes(monkeypatch, name):
    target = repeated.ROOT / repeated.original.SOURCE / name
    read = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda path: read(path) + b" " if path == target else read(path))
    with pytest.raises(ValueError, match="Original publication"):
        repeated.load()


def test_repeated_adapter_rejects_unknown_frozen_verifier(monkeypatch):
    monkeypatch.setattr(repeated, "SOURCE_SHA", "0" * 64)
    with pytest.raises(ValueError, match="Bound presentation verifier changed"):
        repeated.load()


def test_repeated_cli_cannot_write_release():
    with pytest.raises(SystemExit):
        repeated.main(["--write"])


def test_unlisted_test_gets_no_compatibility_context(monkeypatch):
    monkeypatch.setattr(c, "checked", Mock(side_effect=AssertionError("Unlisted context")))
    item = SimpleNamespace(nodeid="tests/unlisted.py::test_case")
    with c.test_context(item):
        pass


def test_scoped_context_restores_original_loader_even_on_failure():
    original = repeated.original.load
    with pytest.raises(RuntimeError):
        with repeated.portable_load():
            assert repeated.original.load is repeated.load
            raise RuntimeError("synthetic test failure")
    assert repeated.original.load is original


def test_editorial_adapter_changes_only_approved_assertions():
    from tests import test_completed_extensions as original
    cls = original.CompletedExtensionsTests
    old = getattr(cls, c.EDITORIAL_METHOD)
    new = c.editorial_method(old)
    # Scientific macros, ordering and numerical assertions are retained.
    old_strings = {x for x in old.__code__.co_consts if isinstance(x, str)}
    new_strings = {x for x in new.__code__.co_consts if isinstance(x, str)}
    assert old_strings - new_strings == {
        "We report a replication of Berg et al.",
        "scores answers primarily with the second rubric", "secondary paper rubric", "notebook",
    }
    assert new_strings - old_strings == {
        "We report a partial replication and extension of Berg et al.",
        r"primary scoring rule, the \emph{notebook classifier}",
        "paper rubric is secondary", r"\citep{aestudio2026deception}",
    }
    assert hashlib.sha256(Path(original.__file__).read_bytes()).hexdigest() == c.SPECIAL[
        "tests/test_completed_extensions.py"]


@pytest.mark.parametrize("missing", ["DoseMainSecondTargetLow", "RubricAuditAstraInclusive",
                                     r"\citep{aestudio2026deception}", "paper rubric is secondary"])
def test_editorial_adapter_keeps_scientific_and_provenance_guards(monkeypatch, missing):
    from tests import test_completed_extensions as original
    cls = original.CompletedExtensionsTests
    adapted = c.editorial_method(getattr(cls, c.EDITORIAL_METHOD))
    read = Path.read_text
    main = c.ROOT / "paper/main.tex"
    monkeypatch.setattr(Path, "read_text", lambda path, *a, **kw:
                        read(path, *a, **kw).replace(missing, "REMOVED")
                        if path == main else read(path, *a, **kw))
    with pytest.raises((AssertionError, ValueError)):
        adapted(cls(c.EDITORIAL_METHOD))


def test_bilingual_strict_failure_is_preserved_and_context_restored():
    from experiments.bilingual_llama_a1 import protocol as a1
    from experiments.bilingual_llama_pilot import protocol as p
    original = p.source_paths
    with pytest.raises(ValueError, match="A1 plan differs"):
        a1.load_plan(c.ROOT / a1.PLAN_PATH)
    with c.bilingual_source_view():
        assert a1.load_plan(c.ROOT / a1.PLAN_PATH)["amendment"]["prior_gate_remains_failed"]
    assert p.source_paths is original


def test_bilingual_unknown_extra_source_is_not_filtered(monkeypatch):
    from experiments.bilingual_llama_pilot import protocol as p
    original = p.source_paths
    monkeypatch.setattr(p, "source_paths", lambda: [*original(), "tests/test_bilingual_unknown.py"])
    with pytest.raises(ValueError, match="Unknown bilingual source inventory"):
        with c.bilingual_source_view():
            pytest.fail("Unknown source accepted")


@pytest.mark.parametrize("name", ["tests/test_bilingual_presentation.py",
                                 "experiments/bilingual_llama_pilot/protocol.py"])
def test_bilingual_extra_and_scientific_source_bytes_remain_bound(monkeypatch, name):
    read = Path.read_bytes
    target = c.ROOT / name
    monkeypatch.setattr(Path, "read_bytes", lambda path: read(path) + b"\n" if path == target else read(path))
    with pytest.raises(ValueError, match="Compatibility input changed"):
        with c.bilingual_source_view():
            pytest.fail("Changed source accepted")


def test_historical_scanner_hash_does_not_replace_content_scanner(tmp_path):
    from experiments.openrouter_swap import protocol as p
    from scripts import audit_public_release as live
    active = live.scan_bytes
    original = p.sha
    other = tmp_path / "science.py"
    other.write_bytes(b"unchanged scientific source\n")
    with c.scanner.source_hash_view():
        assert p.sha(c.ROOT / c.scanner.AUDITOR) == c.scanner.OLD_SHA
        assert p.sha(other) == hashlib.sha256(other.read_bytes()).hexdigest()
        assert live.scan_bytes is active
        assert active("synthetic.json", ("sk-" + "abcdef0123456789" * 3).encode())
    assert p.sha is original
    assert p.sha(c.ROOT / c.scanner.AUDITOR) == c.scanner.CURRENT_SHA


def test_unknown_current_scanner_is_rejected(monkeypatch):
    from experiments import dose_release_compat as d
    original = d.regular
    monkeypatch.setattr(d, "regular", lambda path: original(path) + b"\n"
                        if Path(path) == c.ROOT / c.scanner.AUDITOR else original(path))
    with pytest.raises(ValueError, match="Unapproved current public scanner"):
        c.scanner.checked_scanner()


def test_historical_scanner_change_during_replay_is_rejected(monkeypatch):
    from experiments import dose_release_compat as d
    with pytest.raises(ValueError, match="changed during replay"):
        with c.scanner.source_hash_view():
            original = d.regular
            monkeypatch.setattr(d, "regular", lambda path: original(path) + b"\n"
                                if Path(path) == c.ROOT / c.scanner.AUDITOR else original(path))


def test_saved_kolibri_fixture_cannot_authorize_runtime_and_is_copy_isolated():
    from experiments.kolibri_bootstrap_a1 import adapter as a1
    saved = c.amendment(a1, "b473908043ce0377f7dcae866e7c699a24b32da3583068472a54bc0398b35874")
    first = saved()
    first["predecessor"]["cost_usd"] = "0"
    assert saved()["predecessor"]["cost_usd"] != "0"
    with pytest.raises(ValueError, match="not a runtime"):
        saved("0" * 40)
    with pytest.raises(ValueError, match="Compatibility input changed"):
        c.amendment(a1, "0" * 64)
