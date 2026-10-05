"""Register only five exact historical closure nodes; never skip their assertions."""
from contextlib import contextmanager
import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.register_assert_rewrite("experiments.repeat_closure_history")
from experiments import repeat_closure_history as h

pytest_plugins = ("experiments.repeat_closure_history",)
ROOT = Path(os.environ.get("REPEAT_PORTABILITY_ROOT", Path(__file__).resolve().parents[1])).resolve()


def item(nodeid):
    return SimpleNamespace(nodeid=nodeid, path=ROOT / nodeid.split("::", 1)[0],
                           config=SimpleNamespace(rootpath=ROOT), user_properties=[])


def finish(generator):
    with pytest.raises(StopIteration):
        next(generator)


def test_scope_is_exactly_the_five_original_closure_assertions():
    assert h.TARGETS == {
        "tests/test_repeat_funding_a1.py::test_actual_science_closure_unchanged_and_cost_arithmetic",
        "tests/test_repeat_transport_a2.py::test_old_frozen_source_closures_unchanged",
        "tests/test_repeat_refusal_a3.py::test_frozen_sources_unchanged_and_new_plan_is_additive",
        "tests/test_repeat_publication.py::test_presentation_sources_stay_outside_execution_closures",
        "tests/test_repeated_extension.py::test_binding_sources_remain_outside_all_execution_closures",
    }


@pytest.mark.parametrize("nodeid", sorted(h.TARGETS))
def test_context_rejects_unknown_scanner_before_assertions(monkeypatch, nodeid):
    read = h.history.regular
    monkeypatch.setattr(h.history, "regular", lambda path: read(path) + (
        b" " if Path(path) == ROOT / h.history.AUDITOR else b""))
    entered = False
    with pytest.raises(ValueError, match="Bound scientific/reporting source changed"):
        with h.historical_test_context(ROOT, nodeid):
            entered = True
    assert not entered


@pytest.mark.parametrize("name", ["experiments/repeated_swap/protocol.py",
                                  "experiments/repeated_swap/analysis.py",
                                  "tests/test_repeat_funding_a1.py", "tests/test_repeated_extension.py"])
def test_context_rejects_scientific_or_frozen_test_tamper(monkeypatch, name):
    read = h.history.regular
    monkeypatch.setattr(h.history, "regular", lambda path: read(path) + (b" " if Path(path) == ROOT / name else b""))
    with pytest.raises(ValueError, match="Bound scientific/reporting source changed"):
        with h.historical_test_context(ROOT, min(h.TARGETS)):
            pytest.fail("Tampered source reached test execution")


def test_other_tests_are_never_wrapped(monkeypatch):
    original = h.historical_test_context
    @contextmanager
    def forbidden(*args):
        pytest.fail("Unlisted test entered historical context")
        yield
    monkeypatch.setattr(h, "historical_test_context", forbidden)
    test = item(min(h.TARGETS) + "[unlisted]")
    hook = h.pytest_runtest_call(test)
    next(hook)
    finish(hook)
    assert not test.user_properties
    with pytest.raises(ValueError, match="Unlisted"):
        with original(ROOT, test.nodeid):
            pass


def test_assertions_are_not_suppressed_and_hash_function_restores():
    p = importlib.import_module("experiments.repeated_swap.protocol")
    original = p.sha
    test = item(min(h.TARGETS))
    hook = h.pytest_runtest_call(test)
    next(hook)
    assert p.sha is not original and test.user_properties
    with pytest.raises(AssertionError, match="actual assertion failure"):
        hook.throw(AssertionError("actual assertion failure"))
    assert p.sha is original


def test_normal_completion_restores_hash_function():
    p = importlib.import_module("experiments.repeated_swap.protocol")
    original = p.sha
    hook = h.pytest_runtest_call(item(min(h.TARGETS)))
    next(hook)
    finish(hook)
    assert p.sha is original


def test_same_node_from_another_checkout_is_rejected(tmp_path):
    test = item(min(h.TARGETS))
    test.path = tmp_path / "elsewhere.py"
    with pytest.raises(ValueError, match="another checkout"):
        next(h.pytest_runtest_call(test))
