"""Offline A1 release checks, outside the original frozen test-file glob."""

from copy import deepcopy
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil
import sys

import pytest

from experiments.openrouter_swap import protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1 import amendment, release
from tests.test_openrouter_swap_runner import make_sender


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def inventory(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def synthetic_run(tmp_path, monkeypatch, *, failed=False, main=False, prior_target=False):
    base = protocol.build({})
    repository, prior = tmp_path / "repo", tmp_path / "run"
    root = prior / "a1"
    old_path, new_path = repository / protocol.PLAN, repository / amendment.PLAN
    write(old_path, base)
    old_hash = protocol.sha(old_path)
    write(prior / "runtime.json", {"freeze": "a" * 40, "plan_sha256": old_hash})
    sender, calls = make_sender()

    class RoutingFailure(Exception):
        status_code = 404

    def old_sender(request):
        if request["model"] == base["models"]["deepseek"]["id"]:
            raise RoutingFailure("Synthetic private exception text")
        result = sender(request)
        if len(calls) == 1:
            result["usage"]["cost"] = "0.09640350"
        return result

    with Ledger(prior / "raw") as ledger:
        old = Runner(base, "a" * 40, old_hash, ledger, old_sender)
        for item in base["fixtures"]:
            for instrument in ("paper", "structured"):
                if len(calls) < 11:
                    old.judge(item["id"], item["response"], "astra", instrument, "fixtures")
        if prior_target:
            block = next(block for block in base["screen"] if block["model"] == "gemini")
            old.generate(block["sources"][0])
        with pytest.raises(Halted):
            old.route_fixture("deepseek")
        prior_cost = ledger.spent()
        prior_calls = len(ledger.rows())
    if not prior_target:
        assert prior_cost == Decimal("0.13347786")

    plan = deepcopy(base)
    plan["schema"] = "openrouter-swap-a1"
    plan["models"]["deepseek"].pop("temperature")
    plan["prior_cost_usd"] = str(prior_cost)
    plan["cap_usd"] = str(Decimal("250") - prior_cost)
    plan["screen_cap_usd"] = str(Decimal("40") - prior_cost)
    plan["prior_attempt"] = {"freeze": "a" * 40, "plan_sha256": old_hash,
                             "journal_sha256": protocol.sha(prior / "raw/events.jsonl"),
                             "cost_bound_usd": str(prior_cost), "calls": prior_calls,
                             "target_calls": 0}
    write(new_path, plan)
    new_hash = protocol.sha(new_path)
    write(root / "runtime.json", {"freeze": "b" * 40, "plan_sha256": new_hash,
                                  "prior_cost_bound_usd": str(prior_cost),
                                  "prior_journal_sha256": plan["prior_attempt"]["journal_sha256"]})

    def new_sender(request):
        result = sender(request)
        if failed and request["messages"][0]["content"].startswith("Analyze the following response"):
            result["choices"][0]["message"]["content"] = "invalid paper label"
        return result

    with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        current = Runner(plan, "b" * 40, new_hash, ledger, new_sender)
        write(root / "fixture_gate.json", current.run_fixtures())
        if not failed:
            phase = "main" if main else "screen"
            block = plan[phase][0]
            spec = block["finals"][0]
            source = next(s for s in block["sources"] if s["id"] == spec["source_id"])
            result = current.generate(spec, current.generate(source)["response"])
            for judge in plan["judges"]:
                for instrument in ("paper", "structured"):
                    current.judge(spec["id"], result["response"], judge, instrument, phase)
        write(root / "snapshots/000002/audit.json", {"older": True})
        write(root / "snapshots/000040/audit.json", current.audit())
        write(root / "snapshots/000040/screen_rows.json", current.rows("screen"))
    (root / ".env").write_text("synthetic private marker\n")
    (prior / ".env").write_text("synthetic old private marker\n")
    (root / "snapshots/000040/.ledger.lock").write_text("not public\n")

    checked = []
    frozen = {protocol.PLAN: old_path.read_bytes(), amendment.PLAN: new_path.read_bytes()}
    real_output = release.subprocess.check_output

    def git_show(command, **kwargs):
        if command[0] != "git":
            return real_output(command, **kwargs)
        assert command[:2] == ["git", "show"]  # No network or inference during release.
        assert kwargs["cwd"] == repository
        freeze, path = command[2].split(":", 1)
        checked.append((freeze, path))
        return frozen[path]

    verified = []

    def verify_amendment(path, freeze=None):
        assert freeze is None  # Published-branch checks are not offline replay.
        verified.append(Path(path))
        assert release._load(path) == plan
        return deepcopy(plan)

    def forbidden_original_verify(*args, **kwargs):
        raise AssertionError("Release replay must use amendment.verify")

    monkeypatch.setattr(protocol, "ROOT", repository)
    monkeypatch.setattr(protocol, "verify", forbidden_original_verify)
    monkeypatch.setattr(amendment, "verify", verify_amendment)
    monkeypatch.setattr(release.subprocess, "check_output", git_show)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    return root, plan, calls, checked, verified


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root, plan, calls, checked, verified = synthetic_run(tmp_path, monkeypatch)
    destination = tmp_path / "release"
    before = inventory(root.parent)
    assert release.build(root, destination) == {"pass": True, "status": "incomplete", "files": 15}
    assert inventory(root.parent) == before
    return root, destination, plan, calls, checked, verified


def refresh_manifest(destination):
    manifest = release._load(destination / "MANIFEST.json")
    manifest["files"] = release._inventory(destination)
    write(destination / "MANIFEST.json", manifest)


def test_release_preserves_both_journals_costs_and_frozen_paths(bundle):
    root, destination, plan, calls, checked, verified = bundle
    files = release._load(destination / "MANIFEST.json")["files"]
    assert set(files) == {"PLAN.json", "runtime.json", "fixture_gate.json", "raw/events.jsonl.gz",
                          "prior_attempt/PLAN.json", "prior_attempt/runtime.json", "prior_attempt/events.jsonl.gz",
                          "RELEASE.json", "FIGURE_COUNTS.json", "snapshots/000040/audit.json",
                          "snapshots/000040/screen_rows.json", "screen_astra_inclusive.png",
                          "screen_astra_inclusive.pdf", "screen_opus_inclusive.png", "screen_opus_inclusive.pdf"}
    for name, source in (("raw/events.jsonl.gz", root / "raw/events.jsonl"),
                         ("prior_attempt/events.jsonl.gz", root.parent / "raw/events.jsonl")):
        compressed = (destination / name).read_bytes()
        assert compressed[4:8] == b"\0\0\0\0"
        assert gzip.decompress(compressed) == source.read_bytes()
    assert b'"transport_status_code":404' in gzip.decompress((destination / "prior_attempt/events.jsonl.gz").read_bytes())
    assert (destination / "PLAN.json").read_bytes() == (protocol.ROOT / amendment.PLAN).read_bytes()
    assert (destination / "prior_attempt/PLAN.json").read_bytes() == (protocol.ROOT / protocol.PLAN).read_bytes()
    metadata = release._load(destination / "RELEASE.json")
    assert metadata["prior_cost_bound_usd"] == "0.13347786"
    assert metadata["attempt_cost_bound_usd"] == metadata["audit"]["cost_bound_usd"]
    assert Decimal(metadata["cumulative_cost_bound_usd"]) == Decimal("0.13347786") + Decimal(metadata["attempt_cost_bound_usd"])
    assert metadata["prior_attempt"]["audit"]["calls"] == 12
    assert metadata["prior_attempt"]["audit"]["unresolved"] == 1
    assert metadata["prior_attempt"]["target_calls"] == 0
    assert metadata["fixtures_pass"] is True
    assert set(checked) == {("a" * 40, protocol.PLAN), ("b" * 40, amendment.PLAN)}
    assert verified
    assert "temperature" not in plan["models"]["deepseek"]
    deepseek = next(c for c in calls if c["model"] == plan["models"]["deepseek"]["id"])
    assert "temperature" not in deepseek and deepseek["service_tier"] == "default"
    assert (destination / "screen_astra_inclusive.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (destination / "screen_opus_inclusive.pdf").read_bytes().startswith(b"%PDF-")


def test_verification_is_readonly_with_no_new_calls(bundle):
    root, destination, _, calls, _, _ = bundle
    before, source_before, count = inventory(destination), inventory(root.parent), len(calls)
    assert release.verify(destination)["pass"]
    assert inventory(destination) == before and inventory(root.parent) == source_before
    assert len(calls) == count


@pytest.mark.parametrize("mutation", ["extra", "missing_prior", "changed", "symlink"])
def test_exact_inventory_covers_prior_and_new_artifacts(bundle, mutation, tmp_path):
    _, destination, _, _, _, _ = bundle
    path = destination / "prior_attempt/events.jsonl.gz"
    if mutation == "extra":
        (destination / ".env").write_text("extra")
    elif mutation == "missing_prior":
        path.unlink()
    elif mutation == "changed":
        path.write_bytes(path.read_bytes() + b" ")
    else:
        replacement = tmp_path / "journal.gz"
        shutil.copyfile(path, replacement)
        path.unlink()
        path.symlink_to(replacement)
    with pytest.raises((ValueError, Halted)):
        release.verify(destination)


@pytest.mark.parametrize("mutation,match", [("journal", "Prior journal hash"),
                                          ("runtime", "Prior runtime binding"),
                                          ("cost", "prior-attempt binding"),
                                          ("report", "audit does not reconstruct"),
                                          ("counts", "counts do not reconstruct")])
def test_rehashed_manifest_cannot_hide_binding_or_report_changes(bundle, mutation, match):
    _, destination, _, _, _, _ = bundle
    if mutation == "journal":
        path = destination / "prior_attempt/events.jsonl.gz"
        path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()) + b"\n", mtime=0))
    else:
        name, key, replacement = {"runtime": ("prior_attempt/runtime.json", "freeze", "c" * 40),
                                  "cost": ("runtime.json", "prior_cost_bound_usd", "0"),
                                  "report": ("RELEASE.json", "cumulative_cost_bound_usd", "0"),
                                  "counts": ("FIGURE_COUNTS.json", "screen_astra_inclusive", {})}[mutation]
        path = destination / name
        value = release._load(path)
        write(path, {**value, key: replacement})
    refresh_manifest(destination)
    with pytest.raises(ValueError, match=match):
        release.verify(destination)


def test_new_freeze_uses_amendment_git_path(bundle, monkeypatch):
    _, destination, _, _, _, _ = bundle
    original = release.subprocess.check_output

    def wrong_plan(command, **kwargs):
        if command[-1] == "b" * 40 + ":" + amendment.PLAN:
            return b"original plan is not the amendment"
        return original(command, **kwargs)

    monkeypatch.setattr(release.subprocess, "check_output", wrong_plan)
    with pytest.raises(ValueError, match="local freeze"):
        release.verify(destination)


def test_replay_uses_reduced_budget_binding_and_process_lock(bundle, tmp_path):
    _, destination, plan, _, _, _ = bundle
    raw = tmp_path / "new-raw"
    raw.mkdir()
    (raw / "events.jsonl").write_bytes(gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes()))
    assert plan["cap_usd"] == "249.86652214" and plan["screen_cap_usd"] == "39.86652214"
    with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]):
        with pytest.raises(Halted, match="Another process"):
            with Ledger(raw, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]):
                pass
    with pytest.raises(Halted, match="budget binding"):
        with Ledger(raw):
            pass
    path = destination / "raw/events.jsonl.gz"
    path.write_bytes((destination / "prior_attempt/events.jsonl.gz").read_bytes())
    refresh_manifest(destination)
    with pytest.raises(Halted, match="budget binding"):
        release.verify(destination)


def test_no_overwrite_and_source_symlinks_fail_before_publication(bundle, tmp_path):
    root, destination, _, _, _, _ = bundle
    before = inventory(destination)
    with pytest.raises(FileExistsError):
        release.build(root, destination)
    assert inventory(destination) == before
    old_runtime = root.parent / "runtime.json"
    old_runtime.unlink()
    old_runtime.symlink_to(root / "runtime.json")
    target = tmp_path / "bad-release"
    with pytest.raises(Halted, match="Symlink"):
        release.build(root, target)
    assert not target.exists()


def test_failed_new_fixtures_retain_every_attempt(tmp_path, monkeypatch):
    root, _, _, _, _ = synthetic_run(tmp_path, monkeypatch, failed=True)
    destination = tmp_path / "failed-release"
    assert release.build(root, destination)["status"] == "incomplete"
    metadata = release._load(destination / "RELEASE.json")
    assert metadata["fixtures_pass"] is False and metadata["audit"]["calls"] == 40
    assert metadata["prior_attempt"]["audit"]["unresolved"] == 1
    raw = gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes())
    assert raw == (root / "raw/events.jsonl").read_bytes() and b"invalid paper label" in raw


def test_prior_target_exposure_is_rejected(tmp_path, monkeypatch):
    root, _, _, _, _ = synthetic_run(tmp_path, monkeypatch, prior_target=True)
    with pytest.raises(ValueError, match="target calls"):
        release.build(root, tmp_path / "release")


def test_main_figures_and_admission_replay(tmp_path, monkeypatch):
    root, plan, _, _, _ = synthetic_run(tmp_path, monkeypatch, main=True)
    with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        current = Runner(plan, "b" * 40, protocol.sha(protocol.ROOT / amendment.PLAN), ledger)
        admission = current.main_admission()
    # This synthetic partial main run has no eligible models. The receipt-only
    # release still retains its main panel when no admission record was written.
    destination = tmp_path / "release"
    release.build(root, destination)
    counts = release._load(destination / "FIGURE_COUNTS.json")
    for judge in ("astra", "opus"):
        assert (destination / f"main_{judge}_inclusive.pdf").is_file()
        assert all(len(cells) == 8 for cells in counts[f"main_{judge}_inclusive"].values())
    write(destination / "main_admission.json", {**admission, "remaining_unallocated_usd": "0"})
    refresh_manifest(destination)
    with pytest.raises(ValueError, match="admission"):
        release.verify(destination)


def test_cli_verification_and_private_failure_output(bundle, monkeypatch, capsys):
    root, destination, _, _, _, _ = bundle
    monkeypatch.setattr(sys, "argv", ["release", "--destination", str(destination), "--verify"])
    release.main()
    assert json.loads(capsys.readouterr().out)["pass"]
    monkeypatch.setattr(sys, "argv", ["release", "--run-dir", str(root), "--destination", str(destination)])
    with pytest.raises(SystemExit) as error:
        release.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert str(root) not in output.err and str(destination) not in output.err


def test_original_source_closure_and_plan_remain_valid():
    paths = protocol.source_paths()
    assert "tests/test_openrouter_recovery_release.py" not in paths
    assert not any(path.startswith("experiments/openrouter_swap_a1/") for path in paths)
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    assert plan["prior_cost_usd"] == "0" and plan["models"]["deepseek"]["temperature"] == 0.5
