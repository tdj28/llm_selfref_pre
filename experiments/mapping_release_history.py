"""Execute unchanged mapping-release tests through the verified reporting view."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from experiments import dose_release_compat as compat

ROOT = Path(__file__).resolve().parents[1]
MODULE = "tests/test_mapping_scaled_release.py"
MODULE_SHA = "3e095b5a149ccaa12e805ce2437dcb3670942faa725f79c85ceee6c6e9cdf84d"
NODE_COUNT = 62
NODES_SHA = "7fb31a3cd9cc952f2332544bc16a4d9576cb2e9001e2af69ea9f9dfeb80a8fd2"
COMPAT_SHA = "fe26aabbbfbd63937ddf1e6fdcaeaf1227465b1419668441d3c54fbd142d7ee4"
SCANNER_COMMIT = "a366b664855dfed12590803134a7841844360175"
ADAPTER = "experiments/mapping_release_history.py"
ENFORCER = "tests/test_mapping_release_history.py::test_mapping_release_module_enforced"
MARKER = "DOSE_HISTORICAL_TESTS "


def check_adapter():
    compat.require(compat.digest(compat.regular(compat.__file__)) == COMPAT_SHA,
                   "Bound reporting adapter changed")


def check_module(root):
    compat.require(compat.digest(compat.regular(Path(root) / MODULE)) == MODULE_SHA,
                   "Original mapping-release test module changed")


@contextmanager
def verified_view(root):
    """Use the existing exact scanner exception, including in pre-merge worktrees."""
    root = Path(root).resolve()
    check_adapter()
    check_module(root)
    original = compat.regular
    scanner_path = root / compat.AUDITOR
    before = original(scanner_path)
    compat.require(compat.digest(before) in (compat.OLD_AUDITOR, compat.NEW_AUDITOR),
                   "Unapproved live public scanner")
    git = compat.GitBlobs(root)
    reviewed = git.query("cat-file", "blob", SCANNER_COMMIT + ":" + compat.AUDITOR)
    compat.require(compat.digest(reviewed) == compat.NEW_AUDITOR, "Reviewed public scanner drift")
    # Identical to the bound adapter's enforcing test: only the disposable view
    # imports this reviewed scanner; the hash-bound historical file stays exact.
    def current_scanner(path):
        return reviewed if Path(path).absolute() == scanner_path else original(path)
    with patch.object(compat, "regular", current_scanner):
        with compat.historical_view(root) as (view, env, record):
            check_module(view)
            compat.require(record["current_public_auditor_sha256"] == compat.NEW_AUDITOR,
                           "Current scanner required in historical view")
            yield view, env, record
            compat.require(compat.snapshot(root)[3] == record, "Historical inputs changed during replay")
    compat.require(original(scanner_path) == before, "Live scanner changed during replay")


def scanner_binding():
    scanner = sys.modules.get("scripts.audit_public_release")
    release = sys.modules.get("scripts.release_sae_exposure")
    expected = compat.ROOT / "_compat/current_auditor.py"
    compat.require(scanner is not None and Path(scanner.__file__).resolve() == expected.resolve()
                   and compat.digest(compat.regular(expected)) == compat.NEW_AUDITOR
                   and release is not None and release.scan_blob is scanner.scan_blob,
                   "Release tests did not use the reviewed current public scanner")
    return compat.NEW_AUDITOR


class MappingTests(compat.HistoricalTests):
    def pytest_collection_finish(self, session):
        super().pytest_collection_finish(session)
        nodes = sorted(self.collected)
        compat.require(len(nodes) == len(set(nodes)) == NODE_COUNT
                       and compat.digest(compat.encoded(nodes)) == NODES_SHA,
                       "Original mapping-release node inventory changed or filtered")

    def pytest_runtest_logreport(self, report):
        super().pytest_runtest_logreport(report)
        self.incomplete |= hasattr(report, "wasxfail")

    def result(self, status):
        result = super().result(status)
        return {**result, "node_ids": sorted(self.collected), "module_sha256": MODULE_SHA,
                "current_public_auditor_sha256": scanner_binding()}


def valid_receipt(value):
    if not isinstance(value, dict):
        return False
    nodes = value.get("node_ids")
    return (isinstance(nodes, list) and all(isinstance(n, str) for n in nodes)
            and len(nodes) == len(set(nodes)) == NODE_COUNT
            and compat.digest(compat.encoded(sorted(nodes))) == NODES_SHA
            and value.get("requested") == [MODULE]
            and value.get("collected") == value.get("passed") == NODE_COUNT
            and value.get("module_sha256") == MODULE_SHA
            and value.get("current_public_auditor_sha256") == compat.NEW_AUDITOR)


def child():
    compat.require(os.environ.get("MAPPING_HISTORY_CHILD") == "1", "Disposable mapping-test child required")
    check_adapter()
    check_module(ROOT)
    record = json.loads(compat.regular(ROOT / "_compat/record.json"))
    compat.require(record["current_public_auditor_sha256"] == compat.NEW_AUDITOR,
                   "Current public scanner required")
    # This isolated invocation adds one exact test module. It does not alter
    # the legacy suite, its source bytes, or its separate root-CI enforcer.
    compat.SUITES = (MODULE,)
    compat.HistoricalTests = MappingTests
    return compat.child("test-frozen", [])


def replay(root=ROOT):
    with verified_view(root) as (view, env, record):
        adapter = view / ADAPTER
        compat.require(not adapter.exists(), "Test adapter entered historical inventory")
        with adapter.open("xb") as stream:
            stream.write(compat.regular(__file__))
        result = subprocess.run([sys.executable, "-B", "-m", "experiments.mapping_release_history", "_child"],
                                cwd=view, env={**env, "MAPPING_HISTORY_CHILD": "1"},
                                capture_output=True, text=True, timeout=1800)
        compat.require(result.returncode == 0, "Mapping historical tests failed:\n"
                       + result.stdout[-6000:] + result.stderr[-6000:])
        lines = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
        compat.require(len(lines) == 1, "Missing/duplicate mapping execution receipt")
        receipt = json.loads(lines[0])
        compat.require(valid_receipt(receipt), "Incomplete mapping execution receipt")
        return {"execution": receipt, "historical_view": record}


def collection_only(config):
    return getattr(getattr(config, "option", None), "collectonly", False)


def pytest_collection_finish(session):
    if collection_only(session.config) or os.environ.get("DOSE_COMPAT_CHILD"):
        return
    if not any(i.nodeid == ENFORCER for i in session.items):
        return
    legacy_selected = any(i.nodeid == compat.ENFORCER for i in session.items)
    moved = [i for i in session.items if i.nodeid.startswith(MODULE + "::")
             and not (legacy_selected and i.nodeid in compat.SUITES)]
    if moved:
        session.config._mapping_history_delegated = True
        session.items[:] = [i for i in session.items if i not in moved]
        session.testscollected = len(session.items)
        session.config.hook.pytest_deselected(items=moved)


def pytest_sessionfinish(session, exitstatus):
    if not collection_only(session.config) and getattr(session.config, "_mapping_history_delegated", False):
        if not valid_receipt(getattr(session.config, "_mapping_history_execution", None)):
            session.exitstatus = 1


def pytest_terminal_summary(terminalreporter, config):
    if collection_only(config):
        return
    if valid_receipt(getattr(config, "_mapping_history_execution", None)):
        terminalreporter.write_sep("-", "Mapping release delegation: all 62 original nodes executed and passed; "
                                  "exact historical inputs, reviewed current public scanner")
    elif getattr(config, "_mapping_history_delegated", False):
        terminalreporter.write_sep("-", "Mapping release delegation FAILED: missing/invalid execution receipt")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["_child"]:
        return child()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    print("MAPPING_RELEASE_HISTORY " + compat.encoded(replay(args.root)).decode().strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
