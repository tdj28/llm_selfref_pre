"""Explicit historical provenance context for five unchanged closure assertions."""
from contextlib import contextmanager
from pathlib import Path

import pytest

from experiments import repeat_release_portability as history

TARGETS = frozenset({
    "tests/test_repeat_funding_a1.py::test_actual_science_closure_unchanged_and_cost_arithmetic",
    "tests/test_repeat_transport_a2.py::test_old_frozen_source_closures_unchanged",
    "tests/test_repeat_refusal_a3.py::test_frozen_sources_unchanged_and_new_plan_is_additive",
    "tests/test_repeat_publication.py::test_presentation_sources_stay_outside_execution_closures",
    "tests/test_repeated_extension.py::test_binding_sources_remain_outside_all_execution_closures",
})


@contextmanager
def historical_test_context(root, nodeid):
    history.require(nodeid in TARGETS, "Unlisted historical closure test")
    # The release-bound source inventory verifies these original test bytes too.
    with history.reporting_source_replay(root) as record:
        yield record


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    if item.nodeid not in TARGETS:
        yield
        return
    root = Path(item.config.rootpath).resolve()
    history.require(Path(item.path).resolve() == root / item.nodeid.split("::", 1)[0],
                    "Historical closure test collected from another checkout")
    with historical_test_context(root, item.nodeid) as record:
        item.user_properties.append(("repeated_historical_source_context", {
            "historical_auditor_sha256": record["historical_auditor_sha256"],
            "current_auditor_sha256": record["current_auditor_sha256"],
            "original_exact_source_check": record["original_exact_source_check"],
        }))
        # No collection filtering or outcome replacement: pytest runs the test.
        yield
