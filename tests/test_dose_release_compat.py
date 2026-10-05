"""Enforce historical dose suites without weakening their frozen source checks."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.register_assert_rewrite("experiments.dose_release_compat")
from experiments import dose_release_compat as c

pytest_plugins = ("experiments.dose_release_compat",)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    root = tmp_path.resolve() / "repo"
    old, new = b"# historical scanner\n", b"# reviewed scanner\n"
    prefix = "data/calibration"
    scientific = "experiments/science.py"
    files = {c.AUDITOR: old, scientific: b"VALUE = 1\n",
             prefix + "/raw/receipt.json": b'{"unchanged":true}\n'}
    manifest = {"files": [{"path": "raw/receipt.json", "sha256": c.digest(files[prefix + "/raw/receipt.json"])}]}
    files[prefix + "/MANIFEST.json"] = c.encoded(manifest)
    plan = {"source_hashes": {n: c.digest(files[n]) for n in (c.AUDITOR, scientific)},
            "input_hashes": {prefix + "/MANIFEST.json": c.digest(files[prefix + "/MANIFEST.json"])},
            "continuation": {"release": prefix, "manifest_sha256": c.digest(files[prefix + "/MANIFEST.json"])}}
    files[c.PLAN] = c.encoded(plan)
    for name, raw in {**files, **{n: b"# additive reporting code\n" for n in c.REPORTERS}}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    class Frozen:
        def __init__(self, unused):
            self.tree = {n: ("100644", "blob", "a" * 40) for n in files}
            self.env = {"GIT_DIR": "/synthetic/read-only.git", "GIT_WORK_TREE": str(root)}
        def read(self, names):
            return {n: files[n] for n in names}
        def source_paths(self):
            return list(plan["source_hashes"])
    monkeypatch.setattr(c, "GitBlobs", Frozen)
    monkeypatch.setattr(c, "OLD_AUDITOR", c.digest(old))
    monkeypatch.setattr(c, "NEW_AUDITOR", c.digest(new))
    monkeypatch.setattr(c, "PLAN_SHA", c.digest(files[c.PLAN]))
    monkeypatch.setattr(c, "ANCESTOR_PLANS", ())
    return root, files, new


def test_only_exact_reviewed_auditor_can_differ(repository):
    root, files, new = repository
    baseline = c.snapshot(root)[3]
    (root / c.AUDITOR).write_bytes(new)
    _, historic, scanner, record = c.snapshot(root)
    assert historic[c.AUDITOR] == files[c.AUDITOR] and scanner == new
    assert record["current_public_auditor_sha256"] == c.digest(new)
    assert record["historical_public_auditor_sha256"] == c.digest(files[c.AUDITOR])
    assert record["historical_view_sha256"] == baseline["historical_view_sha256"]
    (root / c.AUDITOR).write_bytes(new + b"# arbitrary edit\n")
    with pytest.raises(ValueError, match="Unapproved"):
        c.snapshot(root)


def test_scanner_copy_uses_verified_bytes(repository, monkeypatch):
    root, _, new = repository
    original = c.regular
    reads = []
    def changing(path):
        if path == root / c.AUDITOR:
            reads.append(path)
            return new if len(reads) == 1 else b"# unapproved later bytes\n"
        return original(path)
    monkeypatch.setattr(c, "regular", changing)
    _, _, scanner, record = c.snapshot(root)
    assert len(reads) == 1 and scanner == new
    assert record["current_public_auditor_sha256"] == c.digest(new)


@pytest.mark.parametrize("name", ["experiments/science.py", "data/calibration/raw/receipt.json",
                                  "data/calibration/MANIFEST.json", c.PLAN])
def test_science_plan_and_prefix_drift_rejected(repository, name):
    root, _, _ = repository
    (root / name).write_bytes((root / name).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="drift"):
        c.snapshot(root)


def test_frozen_blob_corruption_and_extra_prefix_rejected(repository):
    root, files, _ = repository
    files["experiments/science.py"] += b"# corrupt object\n"
    with pytest.raises(ValueError, match="Frozen blob"):
        c.snapshot(root)
    files["experiments/science.py"] = b"VALUE = 1\n"
    (root / "data/calibration/unlisted.json").write_text("{}")
    with pytest.raises(ValueError, match="inventory"):
        c.snapshot(root)


def test_new_scientific_source_inventory_is_rejected(repository, monkeypatch):
    root, _, _ = repository
    monkeypatch.setattr(c.GitBlobs, "source_paths", lambda self: [c.AUDITOR, "experiments/science.py", "new.py"])
    with pytest.raises(ValueError, match="source inventory"):
        c.snapshot(root)


def test_ancestor_test_inputs_are_exact_git_blobs(repository, monkeypatch):
    root, files, _ = repository
    name = "data/ancestor/PLAN.json"
    files[name] = b'{"frozen":true}\n'
    (root / name).parent.mkdir(parents=True)
    (root / name).write_bytes(files[name])
    monkeypatch.setattr(c, "ANCESTOR_PLANS", (name,))
    assert c.snapshot(root)[1][name] == files[name]
    (root / name).write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="drift"):
        c.snapshot(root)


def test_nonregular_prefix_artifact_is_rejected(repository, monkeypatch):
    root, _, _ = repository
    path = root / "data/calibration/special"
    path.write_bytes(b"")
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: False if p == path else original(p))
    with pytest.raises(ValueError, match="Nonregular"):
        c.snapshot(root)


def test_disposable_view_is_separate_and_contains_no_credentials(repository, monkeypatch):
    root, files, new = repository
    (root / c.AUDITOR).write_bytes(new)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-test-key-not-a-credential")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("PYTHONPATH", "/synthetic/untrusted")
    assert not {"OPENROUTER_API_KEY", "GIT_CONFIG_COUNT", "PYTHONPATH"} & c.clean_env().keys()
    with c.historical_view(root) as (view, env, record):
        assert view != root and (view / c.AUDITOR).read_bytes() == files[c.AUDITOR]
        assert (view / "_compat/current_auditor.py").read_bytes() == new
        assert env["GIT_WORK_TREE"] == str(view) and env["GIT_DIR"].endswith("read-only.git")
        assert env["PYTHONPATH"] == str(view)
        assert "OPENROUTER_API_KEY" not in env and "GIT_CONFIG_COUNT" not in env
        assert str(view) not in c.encoded(record).decode() and str(root) not in c.encoded(record).decode()
    assert not view.exists() and (root / c.AUDITOR).read_bytes() == new


@pytest.mark.parametrize("name", ["../secret", "/home/user/file", r"C:\Users\person\file",
                                  "C:/Users/person/file", "a//b", "a/./b", "a\\b", ""])
def test_cross_platform_source_paths_reject_unsafe_names(name):
    with pytest.raises(ValueError):
        c.relative(name)


def test_relative_import_closure_is_bounded_to_local_modules():
    available = {"experiments/x/__init__.py", "experiments/x/protocol.py", "experiments/common.py",
                 "experiments/__init__.py", "unrelated.py"}
    raw = b"from . import protocol\nfrom ..common import helper\nimport torch\n"
    assert c.imports("experiments/x/analysis.py", raw, available) == available - {"unrelated.py"}


def test_git_interface_rejects_mutating_commands():
    git = object.__new__(c.GitBlobs)
    with pytest.raises(ValueError, match="Read-only"):
        git.query("checkout", "HEAD")


def test_source_symlinks_are_rejected(repository):
    root, _, _ = repository
    path = root / "experiments/science.py"
    target = root / "preserved.py"
    path.rename(target)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="Symlink"):
        c.snapshot(root)


def test_sidecar_binds_current_scanner_without_paths(repository, monkeypatch):
    root, _, new = repository
    (root / c.AUDITOR).write_bytes(new)
    dest = root / "release"
    def exported(view, env, action, arguments):
        if action == "build":
            dest.mkdir()
            (dest / "MANIFEST.json").write_bytes(b'{"synthetic":true}\n')
        return "verified\n"
    monkeypatch.setattr(c, "run_child", exported)
    assert c.report("build", [], dest, root) == "verified\n"
    path = root / "release.compat.json"
    record = json.loads(path.read_bytes())
    assert record["release_manifest_sha256"] == c.digest((dest / "MANIFEST.json").read_bytes())
    assert record["current_public_auditor_sha256"] == c.digest(new)
    assert str(root) not in path.read_text() and "\\Users\\" not in path.read_text()
    assert c.report("verify", [], dest, root) == "verified\n"
    record["current_public_auditor_sha256"] = "0" * 64
    path.write_bytes(c.encoded(record))
    with pytest.raises(ValueError, match="Compatibility receipt"):
        c.report("verify", [], dest, root)


def test_failed_export_never_gets_compatibility_receipt(repository, monkeypatch):
    root, _, _ = repository
    monkeypatch.setattr(c, "run_child", Mock(side_effect=ValueError("failed")))
    with pytest.raises(ValueError, match="failed"):
        c.report("build", [], root / "release", root)
    assert not (root / "release.compat.json").exists()


def test_ci_routing_never_drops_suites_without_selected_enforcer(monkeypatch):
    monkeypatch.delenv("DOSE_COMPAT_CHILD", raising=False)
    items = [SimpleNamespace(nodeid=n) for n in (c.ENFORCER, c.SUITES[0] + "::test_frozen",
        "tests/test_other.py::test_other", c.SUITES[2],
        c.SUITES[2].split("::", 1)[0] + "::test_other")]
    hook = Mock()
    session = SimpleNamespace(items=list(items), testscollected=len(items), config=SimpleNamespace(hook=hook))
    c.pytest_collection_finish(session)
    assert session.items == [items[0], items[2], items[4]] and session.testscollected == 3
    hook.pytest_deselected.assert_called_once_with(items=[items[1], items[3]])
    session.items = items[1:]
    c.pytest_collection_finish(session)
    assert session.items == items[1:]


@pytest.mark.parametrize("failure", ["skipped", "deselected", "missing_call", "missing_target"])
def test_historical_execution_cannot_silently_drop_checks(failure):
    audit = c.HistoricalTests()
    nodes = [target if "::" in target else target + "::test_example" for target in c.SUITES]
    audit.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=n) for n in nodes]))
    for node in nodes:
        audit.pytest_runtest_logreport(SimpleNamespace(nodeid=node, when="call", passed=True,
                                                      skipped=False, failed=False))
    assert audit.result(0) == {"requested": list(c.SUITES), "collected": len(nodes), "passed": len(nodes)}
    if failure == "skipped":
        audit.pytest_runtest_logreport(SimpleNamespace(nodeid=nodes[0], when="teardown", passed=False,
                                                      skipped=True, failed=False))
    elif failure == "deselected":
        audit.pytest_deselected([SimpleNamespace(nodeid="omitted")])
    elif failure == "missing_call":
        audit.passed.pop()
    else:
        audit.collected.pop(); audit.passed.pop()
    with pytest.raises(ValueError, match="historical|Historical"):
        audit.result(0)


def test_ci_reports_actual_delegated_execution():
    reporter = Mock()
    config = SimpleNamespace(_dose_delegation_selected=True,
                             _dose_historical_execution={"passed": 71, "collected": 71})
    c.pytest_terminal_summary(reporter, config)
    assert "71/71 tests executed" in reporter.write_sep.call_args.args[1]


def test_historical_suites_enforced(monkeypatch, request):
    """Root CI runs every displaced frozen/exporter test, including real prefix checks."""
    git = c.GitBlobs(c.ROOT)
    # Exercise the merged scanner before merge, without editing this checkout.
    import subprocess
    reviewed = subprocess.check_output(["git", "--no-replace-objects", "show",
        "a366b664855dfed12590803134a7841844360175:" + c.AUDITOR], cwd=c.ROOT, env=git.env)
    assert c.digest(reviewed) == c.NEW_AUDITOR
    original = c.regular
    def merged(path):
        return reviewed if Path(path).absolute() == c.ROOT / c.AUDITOR else original(path)
    monkeypatch.setattr(c, "regular", merged)
    output = c.test_frozen(c.ROOT)
    assert "passed" in output and "failed" not in output and "ERROR" not in output
    record = json.loads(next(line.removeprefix("DOSE_HISTORICAL_TESTS ") for line in output.splitlines()
                             if line.startswith("DOSE_HISTORICAL_TESTS ")))
    assert record["requested"] == list(c.SUITES) and record["passed"] == record["collected"] > 0
    request.config._dose_historical_execution = record


def test_real_partial_export_cli_and_readonly_verify(tmp_path):
    source, destination = tmp_path.resolve() / "stopped", tmp_path.resolve() / "release"
    source.mkdir()
    (source / "failed.json").write_bytes(c.encoded({"plan_sha256": c.PLAN_SHA,
        "error_type": "SyntheticFailure", "completed": 0}))
    before = (source / "failed.json").read_bytes()
    assert c.main(["build", "--source", str(source), "--destination", str(destination),
                   "--mode", "partial_technical_failure"]) == 0
    saved = {p.relative_to(destination).as_posix(): c.digest(p.read_bytes())
             for p in destination.rglob("*") if p.is_file()}
    sidecar = destination.with_name(destination.name + ".compat.json")
    record = sidecar.read_bytes()
    assert c.main(["verify", "--root", str(destination)]) == 0
    assert saved == {p.relative_to(destination).as_posix(): c.digest(p.read_bytes())
                     for p in destination.rglob("*") if p.is_file()}
    assert sidecar.read_bytes() == record and str(tmp_path).encode() not in record
    assert (source / "failed.json").read_bytes() == before
    assert json.loads((destination / "REPORT.json").read_bytes())["main_status"] == "not_run"
