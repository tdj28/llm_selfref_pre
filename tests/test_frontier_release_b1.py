"""Offline synthetic run only. Never open the live frontier output directory."""
import fcntl
import json
from pathlib import Path
import runpy
import shutil
from types import SimpleNamespace

import pytest

from scripts import release_frontier_b1 as release
from experiments.automated_rubric_audit.common import canonical, digest, sha
from experiments.frontier_bilingual_b1 import protocol, runner

FREEZE = "c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb"
SNAPSHOT = {"test_only": True, "source": "synthetic qualification placeholder"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No API/network allowed in release tests")
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr(runner, "live_sender", forbidden)


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    root = tmp_path_factory.mktemp("frontier-release-synthetic")
    plan_path = protocol.ROOT / protocol.PLAN_PATH
    plan = json.loads(plan_path.read_text())
    # Reuse the frozen offline fake sender, not any model output or API client.
    helpers = runpy.run_path(str(protocol.ROOT / "tests/test_frontier_mini.py"))
    first = runner.execute(plan, sha(plan_path), FREEZE, root, digest(SNAPSHOT), helpers["Sender"](), through_block=1)
    assert first["paid_calls"] == 132 and not first["complete"]
    result = runner.execute(plan, sha(plan_path), FREEZE, root, digest(SNAPSHOT), helpers["Sender"]())
    assert result["complete"] and result["paid_calls"] == 792
    (root / "qualification.json").write_text(canonical(SNAPSHOT) + "\n")
    (root / "environment.json").write_text(canonical({"python": "synthetic", "platform": "test",
                                                     "packages": {"numpy": "synthetic"}}) + "\n")
    for name in ("approval.json", ".env", "foreign-pods.json"):
        (root / name).write_text("private synthetic sentinel: never imported\n")
    return SimpleNamespace(root=root, plan_path=plan_path, plan=plan)


@pytest.fixture
def case(tmp_path, completed, monkeypatch):
    root = tmp_path / "closed-run"
    shutil.copytree(completed.root, root)

    def binding(path, freeze):
        assert freeze == FREEZE
        assert Path(path).read_bytes() == completed.plan_path.read_bytes()
        return completed.plan

    def qualification(snapshot, plan, freeze):
        assert snapshot == SNAPSHOT and plan == completed.plan and freeze == FREEZE
        return {"pass": True, "snapshot_sha256": digest(snapshot), "new_fixture_calls": 0,
                "cost_charged_to_mini_usd": "0"}

    # Real ledger replay and unchanged scientific analysis; only synthetic
    # qualification and Git binding are substituted in these packaging cases.
    monkeypatch.setattr(release, "bind_sources", binding)
    monkeypatch.setattr(release.qualification, "verify_snapshot", qualification)
    return SimpleNamespace(root=root, plan_path=completed.plan_path, plan=completed.plan,
                           out=tmp_path / "release", tmp=tmp_path)


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def seal(case):
    return release.build(case.root, case.plan_path, FREEZE, case.out)


def test_real_frozen_source_closure_and_helper_outside_globs():
    path = protocol.ROOT / protocol.PLAN_PATH
    value = release.bind_sources(path, FREEZE)
    assert sha(path) == "8f71b25cc05bf8cd5f658cce9c4b5b1ee21d1546b1b2f718adca6ff87f42a118"
    assert "scripts/release_frontier_b1.py" not in value["sources"]
    assert "tests/test_frontier_release_b1.py" not in protocol.source_paths(protocol.B1_PLAN_PATH)


def test_build_verify_reproduce_read_only_exact_tables_and_exclusions(case):
    before = tree(case.root)
    events = [json.loads(line) for line in before["events.jsonl"].splitlines()]
    assert [e["data"]["after_block"] for e in events if e["kind"] == "projection"] == [1, 1, 2, 3, 4, 5, 6]
    result = seal(case)
    assert result["pass"] and result["receipt_audit"]["complete"]
    original = tree(case.out)
    assert set(original) == release.RELEASE_FILES | {"MANIFEST.json"}
    assert all((case.out / "raw" / n).read_bytes() == before[n] for n in release.RAW_FILES)
    assert (case.out / "PLAN.json").read_bytes() == case.plan_path.read_bytes()
    assert not any(Path(n).name in {"approval.json", ".mini.lock", ".env", "foreign-pods.json"} for n in original)
    manifest = json.loads(original["MANIFEST.json"])
    assert manifest["fixture_cost_charged_to_frontier_usd"] == "0"
    assert len(manifest["files"]) == len(release.RELEASE_FILES)
    assert release.verify(case.out, FREEZE)["tables_reproduced_exactly"] == list(release.TABLES)
    rebuilt = case.tmp / "reproduced"
    assert release.verify(case.out, FREEZE, rebuilt)["pass"]
    for name in release.TABLES:
        assert (rebuilt / name).read_bytes() == (case.out / "analysis" / name).read_bytes()
    assert all((rebuilt / name).stat().st_size > 1000 for name in release.FIGURES)
    assert tree(case.root) == before and tree(case.out) == original


@pytest.mark.parametrize("fault", ["partial", "false_completion", "unresolved", "wrong_binding", "bad_receipt"])
def test_rejects_incomplete_failed_or_rebound_journal_before_release(case, fault):
    path = case.root / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if fault == "partial":
        events = events[:200]
    elif fault == "false_completion":
        events[-1]["data"]["complete"] = False
    elif fault == "unresolved":
        last_request = max(i for i, row in enumerate(events) if row["kind"] == "request")
        events = events[:last_request + 1]
    elif fault == "wrong_binding":
        events[0]["data"]["freeze_commit"] = "a" * 40
    else:
        row = next(e for e in events if e["kind"] == "result")
        row["data"]["cost_usd"] = "0"
    previous = None
    for event in events:
        event["previous"] = previous
        event["sha256"] = digest({k: v for k, v in event.items() if k != "sha256"})
        previous = event["sha256"]
    path.write_text("".join(canonical(e) + "\n" for e in events))
    before = tree(case.root)
    with pytest.raises((ValueError, release.runner.Halted)):
        seal(case)
    assert not case.out.exists() and tree(case.root) == before


def test_active_writer_rejected_without_reading_outcomes(case, monkeypatch):
    def no_render(*args, **kwargs):
        raise AssertionError("Active source must not reach analysis")
    monkeypatch.setattr(release, "_render", no_render)
    with (case.root / ".mini.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            seal(case)
    assert not case.out.exists()


def test_source_change_during_analysis_rejected(case, monkeypatch):
    render = release._render
    def changed(*args, **kwargs):
        result = render(*args, **kwargs)
        (case.root / "environment.json").write_text('{"changed_during_snapshot":true}\n')
        return result
    monkeypatch.setattr(release, "_render", changed)
    with pytest.raises(ValueError, match="Source snapshot changed"):
        seal(case)
    assert not case.out.exists()


@pytest.mark.parametrize("fault", ["existing", "nested", "symlink"])
def test_fresh_separate_destination_required(case, fault):
    destination = case.out
    if fault == "existing":
        destination.mkdir()
    elif fault == "nested":
        destination = case.root / "release"
    else:
        destination.symlink_to(case.root, target_is_directory=True)
    with pytest.raises(ValueError):
        release.build(case.root, case.plan_path, FREEZE, destination)


def test_source_symlink_rejected(case):
    path = case.root / "environment.json"
    path.unlink()
    path.symlink_to(case.plan_path)
    with pytest.raises(ValueError, match="Symlink"):
        seal(case)


@pytest.mark.parametrize("fault", ["extra", "missing", "symlink", "hash", "table_resealed", "freeze", "reporter"])
def test_verify_rejects_tampering_even_with_rehashed_table(case, fault):
    seal(case)
    path = case.out / "MANIFEST.json"
    manifest = json.loads(path.read_text())
    if fault == "extra":
        (case.out / "approval.json").write_text("unapproved extra file")
    elif fault == "missing":
        (case.out / "analysis" / release.FIGURES[0]).unlink()
    elif fault == "symlink":
        target = case.out / "raw/environment.json"
        target.unlink()
        target.symlink_to(case.root / "environment.json")
    elif fault in {"hash", "table_resealed"}:
        target = case.out / "analysis/rates.csv"
        target.write_bytes(target.read_bytes() + b"unapproved table edit\n")
        if fault == "table_resealed":
            entry = next(e for e in manifest["files"] if e["path"] == "analysis/rates.csv")
            entry.update(bytes=target.stat().st_size, sha256=sha(target))
    elif fault == "freeze":
        manifest["freeze_commit"] = "a" * 40
    else:
        manifest["reporting_source_hashes"]["scripts/release_frontier_b1.py"] = "a" * 64
    path.write_text(canonical(manifest) + "\n")
    before = tree(case.out)
    with pytest.raises(ValueError):
        release.verify(case.out, FREEZE)
    assert tree(case.out) == before


def test_missing_plan_and_foreign_frozen_source_fail_closed(tmp_path, monkeypatch):
    plan_path = tmp_path / protocol.PLAN_PATH
    plan_path.parent.mkdir(parents=True)
    plan_path.write_bytes(b"{}\n")
    source = tmp_path / "science.py"
    source.write_bytes(b"original\n")
    value = {"sources": {"science.py": sha(source)}}
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    monkeypatch.setattr(protocol, "load_plan", lambda path: value)
    monkeypatch.setattr(protocol, "assert_scientific_equivalence", lambda plan: True)
    blobs = {protocol.PLAN_PATH: plan_path.read_bytes(), "science.py": source.read_bytes()}
    calls = []
    def git(*args):
        calls.append(args)
        if args == ("cat-file", "-t", FREEZE):
            return b"commit\n"
        if args == ("merge-base", "--is-ancestor", FREEZE, "HEAD"):
            return b""
        return blobs[args[2].split(":", 1)[1]]
    monkeypatch.setattr(release, "_git", git)
    assert release.bind_sources(plan_path, FREEZE) == value
    assert ("merge-base", "--is-ancestor", FREEZE, "HEAD") in calls
    assert not any("rev-parse" in args for args in calls)
    source.write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="Current frozen source"):
        release.bind_sources(plan_path, FREEZE)
    source.write_bytes(blobs["science.py"])
    blobs["science.py"] = b"foreign frozen blob\n"
    with pytest.raises(ValueError, match="Freeze source mismatch"):
        release.bind_sources(plan_path, FREEZE)
    other = tmp_path / "PLAN-copy.json"
    other.write_bytes(b'{"wrong":true}\n')
    with pytest.raises(ValueError, match="plan differs"):
        release.bind_sources(other, FREEZE)


def test_local_git_disables_network_fetch_and_replacements(monkeypatch):
    def run(command, **kwargs):
        assert "--no-replace-objects" in command
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        return SimpleNamespace(returncode=1, stdout=b"")
    monkeypatch.setattr(release.subprocess, "run", run)
    with pytest.raises(ValueError, match="local frozen Git object"):
        release._git("cat-file", "-t", FREEZE)


def test_non_descendant_checkout_rejected_before_plan_reads(monkeypatch):
    def git(*args):
        if args == ("cat-file", "-t", FREEZE):
            return b"commit\n"
        assert args == ("merge-base", "--is-ancestor", FREEZE, "HEAD")
        raise ValueError("Cannot verify local frozen Git object")
    monkeypatch.setattr(release, "_git", git)
    with pytest.raises(ValueError, match="local frozen Git object"):
        release.bind_sources(Path("must-not-read.json"), FREEZE)


def rewrite_events(path, events):
    previous = None
    for index, event in enumerate(events, 1):
        event.update(seq=index, previous=previous)
        event["sha256"] = digest({k: v for k, v in event.items() if k != "sha256"})
        previous = event["sha256"]
    path.write_text("".join(canonical(event) + "\n" for event in events))


@pytest.mark.parametrize("fault", ["missing", "all_failed", "technical_failed", "late_first",
                                    "wrong_order", "future_forecast", "extra_gate"])
def test_rehashed_block_gates_must_match_contemporaneous_prefix(case, fault):
    path = case.root / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    gates = [e for e in events if e["kind"] == "projection"]
    if fault == "missing":
        events = [e for e in events if e["kind"] != "projection"]
    elif fault == "all_failed":
        for event in gates:
            event["data"]["projection"]["pass"] = False
            event["data"]["technical_gate"]["pass"] = False
    elif fault == "technical_failed":
        gates[0]["data"]["technical_gate"]["pass"] = False
    elif fault == "late_first":
        first = [e for e in gates if e["data"]["after_block"] == 1]
        events = [e for e in events if e not in first]
        events[-1:-1] = first
    elif fault == "wrong_order":
        gates[2]["data"]["after_block"] = 3
    elif fault == "future_forecast":
        gates[0]["data"]["projection"] = gates[-1]["data"]["projection"]
    else:
        events.insert(-1, json.loads(json.dumps(gates[-1])))
    rewrite_events(path, events)
    before = tree(case.root)
    with pytest.raises(ValueError, match="gate|Block"):
        seal(case)
    assert not case.out.exists() and tree(case.root) == before


@pytest.mark.parametrize("name", ["raw/environment.json", "analysis/rates_openai.pdf", "MANIFEST.json"])
@pytest.mark.parametrize("reproduce", [False, True])
def test_verify_and_reproduce_scan_all_files_even_after_resealing(case, name, reproduce):
    seal(case)
    target = case.out / name
    manifest_path = case.out / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    fake = "sk-" + "abcdef0123456789" * 3
    if name == "MANIFEST.json":
        manifest["fake_test_credential"] = fake
    else:
        raw = (canonical({"fake_test_credential": fake}) + "\n").encode()
        if target.suffix == ".pdf":
            raw = target.read_bytes() + raw
        target.write_bytes(raw)
        entry = next(e for e in manifest["files"] if e["path"] == name)
        entry.update(bytes=len(raw), sha256=sha(target))
    manifest_path.write_text(canonical(manifest) + "\n")
    assert release.scan_blob(name, target.read_bytes())
    before = tree(case.out)
    out = case.tmp / "reproduced" if reproduce else None
    with pytest.raises(ValueError, match="Public content check failed"):
        release.verify(case.out, FREEZE, out)
    assert tree(case.out) == before
    if out is not None:
        assert not out.exists()


@pytest.mark.parametrize("reproduce", [False, True])
def test_traversal_alias_destination_rejected_before_source_reads(case, reproduce):
    alias = case.tmp / "alias"
    alias.mkdir()
    source = case.out if reproduce else case.root
    out = alias / ".." / source.name / "nested-output"
    with pytest.raises(ValueError, match="traversal"):
        if reproduce:
            release.verify(source, FREEZE, out)
        else:
            release.build(source, case.plan_path, FREEZE, out)
    assert not (source / "nested-output").exists()


def test_symlink_guard_runs_before_path_normalization(case):
    alias = case.tmp / "alias"
    alias.symlink_to(case.root, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        release._new_destination(alias / ".." / "otherwise-safe", case.root)


def test_actual_completed_frontier_release_reproduces_exactly():
    import csv
    from decimal import Decimal

    root = protocol.ROOT / "data/frontier_bilingual_b1/completed_20261002"
    if not root.exists():
        pytest.skip("Completed frontier B1 release has not been created yet")
    # This is deliberately the real verifier with no qualification/Git stubs.
    # Run under both supported interpreters; byte drift is a portability failure,
    # not permission to loosen comparisons or alter frozen analysis.
    before = tree(root)
    result = release.verify(root, FREEZE)
    audit = result["receipt_audit"]
    assert result["pass"] and audit["complete"]
    assert audit["paid_calls"] == audit["planned_slots"] == audit["recorded_slots"] == 792
    assert audit["missing_slots"] == audit["uncollected_slots"] == 0
    assert Decimal(audit["cost_usd_upper_bound"]) == Decimal("20.9621255")
    with (root / "analysis/answers.csv").open(newline="", encoding="utf-8") as handle:
        assert sum(1 for _ in csv.DictReader(handle)) == 144
    assert tree(root) == before
