"""Enforce original mapping-release tests without changing their frozen inputs."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.register_assert_rewrite("experiments.mapping_release_history")
from experiments import mapping_release_history as h

pytest_plugins = ("experiments.mapping_release_history",)


@pytest.fixture
def receipt(monkeypatch):
    nodes = [h.MODULE + "::test_first", h.MODULE + "::test_second"]
    monkeypatch.setattr(h, "NODE_COUNT", 2)
    monkeypatch.setattr(h, "NODES_SHA", h.compat.digest(h.compat.encoded(nodes)))
    return {"requested": [h.MODULE], "collected": 2, "passed": 2, "node_ids": nodes,
            "module_sha256": h.MODULE_SHA, "current_public_auditor_sha256": h.compat.NEW_AUDITOR}


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_node", "failed", "scanner", "module", "requested"])
def test_receipt_rejects_incomplete_or_rebound_execution(receipt, change):
    assert h.valid_receipt(receipt)
    if change == "missing":
        receipt["node_ids"].pop()
    elif change == "duplicate":
        receipt["node_ids"][1] = receipt["node_ids"][0]
    elif change == "wrong_node":
        receipt["node_ids"][1] = h.MODULE + "::test_replacement"
    elif change == "failed":
        receipt["passed"] = 1
    elif change == "scanner":
        receipt["current_public_auditor_sha256"] = h.compat.OLD_AUDITOR
    elif change == "module":
        receipt["module_sha256"] = "0" * 64
    else:
        receipt["requested"] = []
    assert not h.valid_receipt(receipt)


@pytest.mark.parametrize("failure", ["failed", "skipped", "xfail", "xpass", "deselected", "absent_call"])
def test_original_node_failure_cannot_be_hidden(receipt, monkeypatch, failure):
    monkeypatch.setattr(h.compat, "SUITES", (h.MODULE,))
    monkeypatch.setattr(h, "scanner_binding", lambda: h.compat.NEW_AUDITOR)
    audit = h.MappingTests()
    audit.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in receipt["node_ids"]]))
    for n in receipt["node_ids"]:
        audit.pytest_runtest_logreport(SimpleNamespace(nodeid=n, when="call", passed=True, skipped=False, failed=False))
    assert h.valid_receipt(audit.result(0))
    if failure == "deselected":
        audit.pytest_deselected([SimpleNamespace(nodeid="omitted")])
    elif failure == "absent_call":
        audit.passed.pop()
    else:
        report = SimpleNamespace(nodeid=receipt["node_ids"][0], when="teardown", passed=False,
                                 skipped=failure in ("skipped", "xfail"), failed=failure == "failed")
        if failure in ("xfail", "xpass"):
            report.wasxfail = "synthetic"
        audit.pytest_runtest_logreport(report)
    with pytest.raises(ValueError, match="Incomplete historical"):
        audit.result(0)


def test_collection_requires_exact_original_inventory(receipt):
    audit = h.MappingTests()
    with pytest.raises(ValueError, match="node inventory"):
        audit.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=receipt["node_ids"][0])]))


@pytest.fixture
def view(tmp_path, monkeypatch):
    root, temporary = tmp_path / "repo", tmp_path / "view"
    root.mkdir(); temporary.mkdir()
    old, new = b"# old scanner\n", b"# current scanner\n"
    monkeypatch.setattr(h.compat, "OLD_AUDITOR", h.compat.digest(old))
    monkeypatch.setattr(h.compat, "NEW_AUDITOR", h.compat.digest(new))
    for base in (root, temporary):
        path = base / h.MODULE
        path.parent.mkdir(parents=True)
        path.write_bytes(b"# exact test module\n")
    monkeypatch.setattr(h, "MODULE_SHA", h.compat.digest((root / h.MODULE).read_bytes()))
    scanner = root / h.compat.AUDITOR
    scanner.parent.mkdir(parents=True)
    scanner.write_bytes(old)
    monkeypatch.setattr(h, "check_adapter", lambda: None)
    git = Mock()
    git.query.return_value = new
    monkeypatch.setattr(h.compat, "GitBlobs", lambda _: git)
    record = {"current_public_auditor_sha256": h.compat.NEW_AUDITOR}
    @contextmanager
    def historical_view(path):
        assert path == root.resolve()
        assert h.compat.regular(scanner) == new and scanner.read_bytes() == old
        yield temporary, {}, record
    monkeypatch.setattr(h.compat, "historical_view", historical_view)
    monkeypatch.setattr(h.compat, "snapshot", lambda _: (None, None, None, record))
    return root, temporary, scanner, git, record


def test_reuses_verified_view_and_never_rewrites_live_scanner(view):
    root, temporary, scanner, git, record = view
    before = scanner.read_bytes()
    with h.verified_view(root) as (actual, env, metadata):
        assert actual == temporary and metadata == record
    assert scanner.read_bytes() == before and h.compat.regular(scanner) == before
    git.query.assert_called_once_with("cat-file", "blob", h.SCANNER_COMMIT + ":" + h.compat.AUDITOR)


@pytest.mark.parametrize("mutation", ["live_scanner", "reviewed_scanner", "module", "view_module", "view_scanner"])
def test_tampering_fails_before_original_tests_run(view, mutation):
    root, temporary, scanner, git, record = view
    if mutation == "live_scanner":
        scanner.write_bytes(b"# unapproved\n")
    elif mutation == "reviewed_scanner":
        git.query.return_value = b"# unapproved\n"
    elif mutation in ("module", "view_module"):
        ((root if mutation == "module" else temporary) / h.MODULE).write_bytes(b"# changed\n")
    else:
        record["current_public_auditor_sha256"] = h.compat.OLD_AUDITOR
    with pytest.raises(ValueError):
        with h.verified_view(root):
            pytest.fail("Tampered view was accepted")


def test_historical_input_drift_during_replay_is_rejected(view, monkeypatch):
    monkeypatch.setattr(h.compat, "snapshot", lambda _: (None, None, None, {"changed": True}))
    with pytest.raises(ValueError, match="Historical inputs changed"):
        with h.verified_view(view[0]):
            pass


def test_bound_compatibility_adapter_cannot_be_edited(monkeypatch):
    monkeypatch.setattr(h, "COMPAT_SHA", "0" * 64)
    with pytest.raises(ValueError, match="Bound reporting adapter"):
        h.check_adapter()


def test_current_scanner_must_be_the_function_used_by_release(tmp_path, monkeypatch):
    monkeypatch.setattr(h.compat, "ROOT", tmp_path)
    path = tmp_path / "_compat/current_auditor.py"
    path.parent.mkdir()
    path.write_bytes(b"# exact reviewed scanner\n")
    monkeypatch.setattr(h.compat, "NEW_AUDITOR", h.compat.digest(path.read_bytes()))
    scanner = SimpleNamespace(__file__=str(path), scan_blob=lambda *args: [])
    release = SimpleNamespace(scan_blob=scanner.scan_blob)
    monkeypatch.setitem(h.sys.modules, "scripts.audit_public_release", scanner)
    monkeypatch.setitem(h.sys.modules, "scripts.release_sae_exposure", release)
    assert h.scanner_binding() == h.compat.NEW_AUDITOR
    release.scan_blob = lambda *args: []
    with pytest.raises(ValueError, match="did not use"):
        h.scanner_binding()


@pytest.mark.parametrize("legacy_selected", [False, True])
def test_delegation_preserves_legacy_ownership_and_requires_receipt(receipt, monkeypatch, legacy_selected):
    monkeypatch.delenv("DOSE_COMPAT_CHILD", raising=False)
    legacy_node = h.MODULE + "::test_sidecar_does_not_change_frozen_source_closure"
    nodes = [h.ENFORCER, *receipt["node_ids"], legacy_node, "tests/test_other.py::test_other"]
    if legacy_selected:
        nodes.append(h.compat.ENFORCER)
    config = SimpleNamespace(hook=Mock())
    session = SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in nodes], config=config,
                              testscollected=len(nodes), exitstatus=0)
    h.pytest_collection_finish(session)
    remaining = [i.nodeid for i in session.items]
    assert (legacy_node in remaining) == legacy_selected
    assert not set(receipt["node_ids"]) & set(remaining)
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1
    config._mapping_history_execution = receipt
    session.exitstatus = 0
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    reporter = Mock()
    h.pytest_terminal_summary(reporter, config)
    assert "original nodes executed and passed" in reporter.write_sep.call_args.args[1]


def test_no_enforcer_means_no_delegation(monkeypatch):
    monkeypatch.delenv("DOSE_COMPAT_CHILD", raising=False)
    items = [SimpleNamespace(nodeid=h.MODULE + "::test_original")]
    session = SimpleNamespace(items=list(items), config=SimpleNamespace(hook=Mock()))
    h.pytest_collection_finish(session)
    assert session.items == items


def test_collect_only_keeps_all_nodes_and_makes_no_execution_claim(receipt):
    config = SimpleNamespace(option=SimpleNamespace(collectonly=True), hook=Mock(),
                             _mapping_history_delegated=True, _mapping_history_execution=receipt)
    nodes = [h.ENFORCER, *receipt["node_ids"]]
    session = SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in nodes], config=config, exitstatus=0)
    h.pytest_collection_finish(session)
    assert [i.nodeid for i in session.items] == nodes
    config.hook.pytest_deselected.assert_not_called()
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    reporter = Mock()
    h.pytest_terminal_summary(reporter, config)
    reporter.write_sep.assert_not_called()


def test_new_adapter_is_outside_frozen_closure():
    from experiments.berg_dose_exposure_continuation import protocol
    paths = set(protocol.source_paths())
    assert h.ADAPTER not in paths
    assert "tests/test_mapping_release_history.py" not in paths


def test_mapping_release_module_enforced(request):
    result = h.replay()
    assert h.valid_receipt(result["execution"])
    assert result["historical_view"]["current_public_auditor_sha256"] == h.compat.NEW_AUDITOR
    request.config._mapping_history_execution = result["execution"]
