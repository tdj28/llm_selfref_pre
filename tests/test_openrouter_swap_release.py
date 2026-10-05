"""Synthetic-only release checks; transport is fake and verification is offline."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import shutil
import sys

import pytest

from experiments.openrouter_swap import protocol, release, runner
from experiments.openrouter_swap.ledger import Ledger
from tests.test_openrouter_swap_runner import make_sender


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def inventory(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def synthetic_run(root, monkeypatch, *, failed=False, main=False):
    plan = protocol.build({})
    plan_path = root.parent / "synthetic_PLAN.json"
    write(plan_path, plan)
    monkeypatch.setattr(protocol, "PLAN", str(plan_path))
    frozen_bytes = plan_path.read_bytes()
    original_output = release.subprocess.check_output

    def frozen_plan(command, **kwargs):
        if command[0] != "git":
            return original_output(command, **kwargs)
        assert command == ["git", "show", "a" * 40 + ":" + str(plan_path)]
        assert kwargs["cwd"] == protocol.ROOT
        return frozen_bytes

    monkeypatch.setattr(release.subprocess, "check_output", frozen_plan)
    write(root / "runtime.json", {"freeze": "a" * 40, "plan_sha256": protocol.sha(plan_path)})
    sender, calls = make_sender()

    def send(request):
        result = sender(request)
        if failed and request["messages"][0]["content"].startswith("Analyze the following response"):
            result["choices"][0]["message"]["content"] = "invalid paper label"
        return result

    with Ledger(root / "raw") as ledger:
        r = runner.Runner(plan, "a" * 40, protocol.sha(plan_path), ledger, sender=send)
        gate = r.run_fixtures()
        write(root / "fixture_gate.json", gate)
        if not failed:
            phase = "main" if main else "screen"
            block = plan[phase][0]
            spec = block["finals"][0]
            source = next(s for s in block["sources"] if s["id"] == spec["source_id"])
            result = r.generate(spec, r.generate(source)["response"])
            for judge in plan["judges"]:
                for instrument in ("paper", "structured"):
                    r.judge(spec["id"], result["response"], judge, instrument, phase)
        write(root / "snapshots/000002/screen_rows.json", r.rows("screen"))
        write(root / "snapshots/000010/audit.json", r.audit())
        write(root / "snapshots/000010/screen_rows.json", r.rows("screen"))
        write(root / "snapshots/000010/extra.json", {"synthetic": True})
    (root / ".env").write_text("synthetic private marker, never publish\n")
    (root / "snapshots/000010/.ledger.lock").write_text("not public\n")
    return calls


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    root, destination = tmp_path / "run", tmp_path / "release"
    calls = synthetic_run(root, monkeypatch)
    before = inventory(root)
    result = release.build(root, destination)
    assert inventory(root) == before
    assert result["pass"] and result["status"] == "incomplete"
    return root, destination, calls


def test_build_explicit_inventory_plots_latest_snapshot_and_readonly_verification(bundle):
    root, destination, calls = bundle
    files = release._load(destination / "MANIFEST.json")["files"]
    assert set(files) == {
        "runtime.json", "fixture_gate.json", "raw/events.jsonl.gz", "PLAN.json", "RELEASE.json", "FIGURE_COUNTS.json",
        "snapshots/000010/audit.json", "snapshots/000010/screen_rows.json", "snapshots/000010/extra.json",
        "screen_astra_inclusive.png", "screen_astra_inclusive.pdf", "screen_opus_inclusive.png", "screen_opus_inclusive.pdf"}
    compressed = (destination / "raw/events.jsonl.gz").read_bytes()
    assert compressed[4:8] == b"\0\0\0\0"
    assert gzip.decompress(compressed) == (root / "raw/events.jsonl").read_bytes()
    assert (destination / "PLAN.json").read_bytes() == Path(protocol.PLAN).read_bytes()
    assert (destination / "screen_astra_inclusive.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (destination / "screen_opus_inclusive.pdf").read_bytes().startswith(b"%PDF-")
    before, n_calls = inventory(destination), len(calls)
    assert release.verify(destination)["pass"]
    assert inventory(destination) == before and len(calls) == n_calls
    assert str(destination) not in (destination / "RELEASE.json").read_text()
    assert str(root) not in (destination / "MANIFEST.json").read_text()
    assert "experiments/openrouter_swap/release.py" in protocol.source_paths()
    assert "tests/test_openrouter_swap_release.py" in protocol.source_paths()


@pytest.mark.parametrize("mutation", ["extra", "changed", "missing", "symlink", "directory_symlink"])
def test_verification_rejects_extra_missing_changed_and_symlinked_artifacts(bundle, mutation, tmp_path):
    _, destination, _ = bundle
    artifact = destination / "runtime.json"
    if mutation == "extra":
        (destination / ".env").write_text("extra")
    elif mutation == "changed":
        artifact.write_bytes(artifact.read_bytes() + b" ")
    elif mutation == "missing":
        artifact.unlink()
    elif mutation == "symlink":
        copied = tmp_path / "runtime-copy.json"
        shutil.copyfile(artifact, copied)
        artifact.unlink()
        artifact.symlink_to(copied)
    else:
        (destination / "extra-link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((ValueError, runner.Halted)):
        release.verify(destination)


def test_refuse_existing_destination_without_overwrite(bundle):
    root, destination, _ = bundle
    before = inventory(destination)
    with pytest.raises(FileExistsError):
        release.build(root, destination)
    assert inventory(destination) == before


def test_failed_fixture_bundle_keeps_all_failed_attempts(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    root, destination = tmp_path / "run", tmp_path / "failed-release"
    calls = synthetic_run(root, monkeypatch, failed=True)
    assert len(calls) == 40  # 12 invalid paper labels, each attempted twice.
    assert release.build(root, destination)["status"] == "incomplete"
    metadata = release._load(destination / "RELEASE.json")
    assert metadata["fixtures_pass"] is False
    assert metadata["audit"]["calls"] == 40
    raw = gzip.decompress((destination / "raw/events.jsonl.gz").read_bytes())
    assert raw == (root / "raw/events.jsonl").read_bytes()
    assert b"invalid paper label" in raw


def test_main_has_eight_cells_and_separate_judge_figures(tmp_path, monkeypatch):
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    root, destination = tmp_path / "run", tmp_path / "main-release"
    synthetic_run(root, monkeypatch, main=True)
    release.build(root, destination)
    counts = release._load(destination / "FIGURE_COUNTS.json")
    for judge in ("astra", "opus"):
        assert (destination / f"main_{judge}_inclusive.pdf").is_file()
        assert (destination / f"main_{judge}_inclusive.png").is_file()
        assert all(len(cells) == 8 for cells in counts[f"main_{judge}_inclusive"].values())


def test_rates_exclude_missing_and_preserve_judge_disagreement():
    rows = [{"model": "m", "cell": "SS", "response": "synthetic", "status": "ok",
             "labels": {"astra": {"structured": {"inclusive_current_assertion": True}},
                        "opus": {"structured": {"inclusive_current_assertion": False}}}},
            {"model": "m", "cell": "SS", "response": "unlabeled", "status": "ok", "labels": {}}]
    fake_missing = deepcopy(rows[0])
    fake_missing["response"] = None
    rows.append(fake_missing)
    astra = release.cell_counts(rows, ["m"], ["SS", "HH"], "astra")["m"]
    opus = release.cell_counts(rows, ["m"], ["SS"], "opus")["m"]
    assert astra["SS"] == {"positive": 1, "labeled": 1, "planned": 3, "missing": 2, "rate": 1.0}
    assert opus["SS"]["rate"] == 0.0 and opus["SS"]["missing"] == 2
    assert astra["HH"]["rate"] is None and astra["HH"]["planned"] == 0


@pytest.mark.parametrize("status,cap,refusal,expected", [
    ("ok", False, True, None), ("refusal", False, False, None),
    ("incomplete", False, False, None), ("incomplete", True, False, 0.0)])
def test_cell_counts_share_analysis_refusal_and_status_rules(status, cap, refusal, expected):
    row = {"model": "m", "cell": "SS", "response": "synthetic", "status": status, "cap_hit": cap,
           "labels": {"astra": {"structured": {"inclusive_current_assertion": False, "refusal": refusal}}}}
    assert release.cell_counts([row], ["m"], ["SS"], "astra")["m"]["SS"]["rate"] == expected


def test_frozen_plan_bytes_and_admission_reconstructed(tmp_path, monkeypatch):
    root = tmp_path / "run"
    synthetic_run(root, monkeypatch)
    shutil.copyfile(protocol.PLAN, root / "PLAN.json")
    with Ledger(root / "raw") as ledger:
        r = runner.Runner(release._load(root / "PLAN.json"), "a" * 40,
                          protocol.sha(root / "PLAN.json"), ledger)
        admission = r.main_admission()
    (root / "raw/events.jsonl.gz").write_bytes(gzip.compress((root / "raw/events.jsonl").read_bytes(), mtime=0))
    write(root / "main_admission.json", admission)
    assert release._replay(root)[0]["audit"]["pass"]
    write(root / "main_admission.json", {**admission, "remaining_unallocated_usd": "0"})
    with pytest.raises(ValueError, match="admission"):
        release._replay(root)
    write(root / "main_admission.json", admission)
    monkeypatch.setattr(release.subprocess, "check_output", lambda *args, **kwargs: b"wrong frozen bytes")
    with pytest.raises(ValueError, match="local freeze"):
        release._replay(root)


def test_runtime_binding_and_source_symlinks_fail_before_publication(tmp_path, monkeypatch):
    root, destination = tmp_path / "run", tmp_path / "release"
    synthetic_run(root, monkeypatch)
    runtime = release._load(root / "runtime.json")
    write(root / "runtime.json", {**runtime, "plan_sha256": "0" * 64})
    with pytest.raises(ValueError, match="binding"):
        release.build(root, destination)
    assert not destination.exists()
    write(root / "runtime.json", runtime)
    source = root / "snapshots/000010/audit.json"
    source.unlink()
    source.symlink_to(root / "runtime.json")
    with pytest.raises(runner.Halted, match="Symlink"):
        release.build(root, destination)


def test_cli_readonly_and_failure_output_contains_no_paths(bundle, monkeypatch, capsys):
    root, destination, _ = bundle
    monkeypatch.setattr(sys, "argv", ["release", "--destination", str(destination), "--verify"])
    release.main()
    assert json.loads(capsys.readouterr().out)["pass"]
    monkeypatch.setattr(sys, "argv", ["release", "--run-dir", str(root), "--destination", str(destination)])
    with pytest.raises(SystemExit) as error:
        release.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert str(root) not in output.err and str(destination) not in output.err
