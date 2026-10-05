"""Historical-node execution is mandatory; later seed reuse stays fail-closed."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.register_assert_rewrite("experiments.exposure_seed_history")
from experiments import exposure_seed_history as h

pytest_plugins = ("experiments.exposure_seed_history",)


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path.resolve()
    prior = {"data/prior/PLAN.json": h.encoded({"seed": 7})}
    allowed = {h.PLAN: h.encoded({"rows": [{"seed": 42}]}),
               "data/continuation/PLAN.json": h.encoded({"seed": 42})}
    for name, raw in {**prior, **allowed}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return root, prior, allowed, {42}


def test_live_guard_accepts_only_exact_known_reuse(corpus):
    result = h.live_guard(*corpus)
    assert result["plans"] == 3 and result["unknown_collisions"] == 0
    assert set(result["known_overlaps"]) == set(corpus[2])


@pytest.mark.parametrize("name", ["data/future/PLAN.json",
                                 "data/berg_dose_exposure/new/PLAN.json",
                                 "data/berg_dose_exposure_continuation/new/PLAN.json"])
@pytest.mark.parametrize("value", [{"seed": 42}, {"nested": {"decode_seeds": [42]}},
                                  {"copied": [{"seed": 42}]}])
def test_unknown_colliding_paths_fail_even_in_known_namespaces(corpus, name, value):
    path = corpus[0] / name
    path.parent.mkdir(parents=True)
    path.write_bytes(h.encoded(value))
    with pytest.raises(ValueError, match="Unknown colliding"):
        h.live_guard(*corpus)


def test_byte_identical_new_plan_copy_is_not_exempt(corpus):
    path = corpus[0] / "data/new-copy/PLAN.json"
    path.parent.mkdir()
    path.write_bytes(corpus[2][h.PLAN])
    with pytest.raises(ValueError, match="Unknown colliding"):
        h.live_guard(*corpus)


@pytest.mark.parametrize("name", [h.PLAN, "data/continuation/PLAN.json"])
@pytest.mark.parametrize("replacement", [b'{"seed":99}\n', b'{"seed":42,"added":true}\n'])
def test_known_plan_drift_fails_even_without_collision(corpus, name, replacement):
    (corpus[0] / name).write_bytes(replacement)
    with pytest.raises(ValueError, match="Known plan drift"):
        h.live_guard(*corpus)


@pytest.mark.parametrize("mode", ["missing", "changed"])
def test_prior_plan_cannot_be_removed_or_edited(corpus, mode):
    path = corpus[0] / next(iter(corpus[1]))
    if mode == "missing":
        path.unlink()
    else:
        path.write_bytes(b'{"seed":8}\n')
    with pytest.raises(ValueError, match="Historical plan"):
        h.live_guard(*corpus)


def test_noncolliding_future_plan_is_still_in_inventory(corpus):
    before = h.live_guard(*corpus)
    path = corpus[0] / "data/future/PLAN.json"
    path.parent.mkdir()
    path.write_bytes(b'{"seed":99}\n')
    after = h.live_guard(*corpus)
    assert after["plans"] == 4 and after["inventory_sha256"] != before["inventory_sha256"]


def test_duplicate_json_keys_cannot_hide_collision(corpus):
    path = corpus[0] / "data/future/PLAN.json"
    path.parent.mkdir()
    path.write_bytes(b'{"seed":42,"seed":99}\n')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        h.live_guard(*corpus)


def test_symlink_plan_and_directory_rejected(corpus):
    root = corpus[0]
    path = root / "data/link"
    path.symlink_to(root / "data/continuation", target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        h.live_guard(*corpus)
    path.unlink()
    plan = root / "data/continuation/PLAN.json"
    plan.unlink()
    plan.symlink_to(root / h.PLAN)
    with pytest.raises(ValueError, match="nonregular"):
        h.live_guard(*corpus)


@pytest.fixture
def historical(corpus, monkeypatch):
    root, prior, allowed, _ = corpus
    source = {h.TEST_FILE: b"def test_only_declared_design_fields_change_and_seeds_are_fresh():\n    assert True\n",
              "pytest.ini": b"[pytest]\naddopts = --import-mode=importlib\n"}
    plan = {"source_hashes": {n: h.sha(b) for n, b in source.items()},
            "rows": [{"seed": n} for n in range(1000, 1108)]}
    allowed[h.PLAN] = h.encoded(plan)
    frozen = {**source, h.PLAN: allowed[h.PLAN]}
    for name, raw in {**source, **allowed}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    class Git:
        def __init__(self, unused):
            pass
        def query(self, *args):
            return f"{h.FREEZE} {h.PRIOR}\n".encode()
        def tree(self, revision):
            return {h.PRIOR: prior, h.FREEZE: frozen, h.REVIEW: allowed}[revision]
        def read(self, tree, names):
            return {n: tree[n] for n in names}
    monkeypatch.setattr(h, "Git", Git)
    monkeypatch.setattr(h, "PRIOR_COUNT", 1)
    monkeypatch.setattr(h, "PRIOR_INVENTORY_SHA", h.sha(h.encoded(h.inventory(prior))))
    monkeypatch.setattr(h, "PLAN_SHA", h.sha(frozen[h.PLAN]))
    monkeypatch.setattr(h, "TEST_SHA", h.sha(source[h.TEST_FILE]))
    monkeypatch.setattr(h, "KNOWN", {n: h.sha(b) for n, b in allowed.items()})
    return root, prior, frozen


def test_historical_snapshot_has_only_pinned_prior_plans(historical):
    root, prior, _ = historical
    files, record, *_ = h.snapshot(root)
    assert {n for n in files if n.endswith("/PLAN.json")} == set(prior)
    assert record["prior_commit"] == h.PRIOR and record["prior_plan_count"] == 1


@pytest.mark.parametrize("mode", ["omitted", "extra", "changed"])
def test_historical_corpus_inventory_is_exact(historical, mode):
    root, prior, _ = historical
    if mode == "omitted":
        prior.clear()
    elif mode == "extra":
        prior["data/another/PLAN.json"] = b"{}\n"
    else:
        prior[next(iter(prior))] = b'{"seed":8}\n'
    with pytest.raises(ValueError, match="corpus inventory"):
        h.snapshot(root)


def test_actual_prior_collision_fails_even_with_valid_inventory(historical, monkeypatch):
    root, prior, _ = historical
    name = next(iter(prior))
    prior[name] = b'{"seed":1000}\n'
    (root / name).write_bytes(prior[name])
    monkeypatch.setattr(h, "PRIOR_INVENTORY_SHA", h.sha(h.encoded(h.inventory(prior))))
    with pytest.raises(ValueError, match="collide with historical"):
        h.snapshot(root)


def test_frozen_test_and_executed_sources_cannot_drift(historical):
    root, _, _ = historical
    (root / h.TEST_FILE).write_bytes(b"# edited test\n")
    with pytest.raises(ValueError, match="Executed source drift"):
        h.snapshot(root)


def test_synthetic_replay_executes_original_node_in_child(historical):
    result = h.replay(historical[0])
    assert result["execution"] == {"target": h.TARGET, "collected": 1, "passed": 1}


@pytest.mark.parametrize("statement", ["assert False", "pytest.skip('synthetic')", "pytest.xfail('synthetic')"])
def test_subprocess_failure_or_skip_cannot_produce_success(historical, monkeypatch, statement):
    root, _, frozen = historical
    raw = ("import pytest\ndef test_only_declared_design_fields_change_and_seeds_are_fresh():\n"
           "    " + statement + "\n").encode()
    frozen[h.TEST_FILE] = raw
    (root / h.TEST_FILE).write_bytes(raw)
    monkeypatch.setattr(h, "TEST_SHA", h.sha(raw))
    plan = json.loads(frozen[h.PLAN])
    plan["source_hashes"][h.TEST_FILE] = h.sha(raw)
    frozen[h.PLAN] = h.encoded(plan)
    (root / h.PLAN).write_bytes(frozen[h.PLAN])
    monkeypatch.setattr(h, "PLAN_SHA", h.sha(frozen[h.PLAN]))
    original_tree = h.Git.tree
    def tree(self, revision):
        data = original_tree(self, revision)
        if revision == h.REVIEW:
            data[h.PLAN] = frozen[h.PLAN]
        return data
    monkeypatch.setattr(h.Git, "tree", tree)
    monkeypatch.setitem(h.KNOWN, h.PLAN, h.PLAN_SHA)
    with pytest.raises(ValueError, match="Historical freshness replay failed"):
        h.replay(root)


@pytest.mark.parametrize("mode", ["failed", "skipped", "xfail", "deselected", "missing", "duplicate"])
def test_execution_receipt_never_accepts_bypassed_node(mode):
    audit = h.Execution()
    audit.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=h.TARGET)]))
    report = SimpleNamespace(nodeid=h.TARGET, when="call", passed=True, skipped=False, failed=False)
    audit.pytest_runtest_logreport(report)
    assert audit.result(0)["passed"] == 1
    if mode in ("failed", "skipped", "xfail"):
        setattr(report, "wasxfail" if mode == "xfail" else mode, True)
        report.when = "teardown"
        audit.pytest_runtest_logreport(report)
    elif mode == "deselected":
        audit.pytest_deselected([SimpleNamespace(nodeid=h.TARGET)])
    elif mode == "missing":
        audit.passed.clear()
    else:
        audit.passed.append(h.TARGET)
    with pytest.raises(ValueError, match="exactly once"):
        audit.result(0)


def good_receipt():
    return {"prior_plan_count": h.PRIOR_COUNT, "prior_commit": h.PRIOR,
            "source_freeze": h.FREEZE, "prior_inventory_sha256": h.PRIOR_INVENTORY_SHA,
            "test_sha256": h.TEST_SHA, "live_corpus": {"unknown_collisions": 0},
            "execution": {"target": h.TARGET, "collected": 1, "passed": 1}}


def test_delegation_requires_enforcer_and_only_moves_exact_node(monkeypatch):
    monkeypatch.delenv("EXPOSURE_HISTORY_CHILD", raising=False)
    nodes = [h.TARGET, h.ENFORCER, h.TEST_FILE + "::test_other"]
    hook = Mock()
    session = SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in nodes], testscollected=3,
                              config=SimpleNamespace(hook=hook), exitstatus=0)
    h.pytest_collection_finish(session)
    assert [i.nodeid for i in session.items] == nodes[1:]
    assert session.testscollected == 2
    hook.pytest_deselected.assert_called_once()
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1
    session.config._exposure_history_execution = good_receipt()
    session.exitstatus = 0
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    session.items = [SimpleNamespace(nodeid=h.TARGET)]
    h.pytest_collection_finish(session)
    assert len(session.items) == 1


def test_terminal_reports_execution_not_just_deselection():
    reporter = Mock()
    config = SimpleNamespace(_exposure_history_execution=good_receipt())
    h.pytest_terminal_summary(reporter, config)
    message = reporter.write_sep.call_args.args[1]
    assert "executed 1/1" in message and "29 pinned prior plans" in message and "live collision guard passed" in message


@pytest.mark.parametrize("stale_receipt", [False, True])
def test_collect_only_keeps_node_without_enforcement_or_execution_claim(stale_receipt):
    hook = Mock()
    config = SimpleNamespace(option=SimpleNamespace(collectonly=True), hook=hook)
    nodes = [h.TARGET, h.ENFORCER]
    session = SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in nodes],
                              testscollected=2, config=config, exitstatus=0)
    h.pytest_collection_finish(session)
    assert [i.nodeid for i in session.items] == nodes and session.testscollected == 2
    hook.pytest_deselected.assert_not_called()
    assert not hasattr(config, "_exposure_history_delegated")
    config._exposure_history_delegated = True
    if stale_receipt:
        config._exposure_history_execution = good_receipt()
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 0
    reporter = Mock()
    h.pytest_terminal_summary(reporter, config)
    reporter.write_sep.assert_not_called()


def test_collect_only_subprocess_exits_zero_without_execution_claim():
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         h.ENFORCER, h.TARGET], cwd=h.ROOT,
        env={**h.clean_env(), "PYTHONPATH": str(h.ROOT), "PYTHONDONTWRITEBYTECODE": "1",
             "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert h.TARGET in output and h.ENFORCER in output and "2 tests collected" in output
    assert "deselected" not in output and "Exposure freshness" not in output and h.MARKER not in output


@pytest.mark.parametrize("field", ["prior_plan_count", "prior_commit", "source_freeze",
                                  "prior_inventory_sha256", "test_sha256", "execution", "live_corpus"])
def test_delegation_fails_closed_for_incomplete_receipt(field):
    receipt = good_receipt()
    receipt.pop(field)
    config = SimpleNamespace(_exposure_history_delegated=True, _exposure_history_execution=receipt)
    session = SimpleNamespace(config=config, exitstatus=0)
    h.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1
    reporter = Mock()
    h.pytest_terminal_summary(reporter, config)
    assert "FAILED" in reporter.write_sep.call_args.args[1]


def test_wrapper_names_stay_outside_frozen_source_closure():
    from experiments.berg_dose_exposure_continuation import protocol
    paths = set(protocol.source_paths())
    assert "experiments/exposure_seed_history.py" not in paths
    assert "tests/test_exposure_seed_history.py" not in paths


def test_git_cannot_fetch_or_mutate():
    git = object.__new__(h.Git)
    for command in ("fetch", "checkout", "reset"):
        with pytest.raises(ValueError, match="Read-only"):
            git.query(command)


def test_child_environment_drops_credentials_and_test_overrides(monkeypatch):
    for key in ("OPENROUTER_API_KEY", "RUNPOD_API_KEY", "PYTHONPATH", "PYTEST_ADDOPTS", "GIT_CONFIG_COUNT"):
        monkeypatch.setenv(key, "synthetic-not-a-credential")
    assert not {"OPENROUTER_API_KEY", "RUNPOD_API_KEY", "PYTHONPATH", "PYTEST_ADDOPTS", "GIT_CONFIG_COUNT"} & h.clean_env().keys()


def test_historical_freshness_enforced(request):
    """Execute the unchanged historical assertion; do not waive or xfail it."""
    result = h.replay()
    assert result["prior_plan_count"] == 29 and result["prior_commit"] == h.PRIOR
    assert result["execution"] == {"target": h.TARGET, "collected": 1, "passed": 1}
    request.config._exposure_history_execution = result
