"""Synthetic offline A2 release tests; no model services or study data are used."""

from copy import deepcopy
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

from experiments.openrouter_swap import protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1 import amendment as a1
from experiments.openrouter_swap_a2 import amendment, release
from tests.test_openrouter_recovery_release import inventory, write
from tests.test_openrouter_swap_runner import make_sender


def synthetic_run(tmp_path, monkeypatch, *, prior_target=False, resolved=False, failed=False):
    repository, original = tmp_path / "repo", tmp_path / "run"
    root = original / "a2"
    base = protocol.build({})
    source = b"synthetic frozen source\n"
    base["source_hashes"] = {"synthetic_source.py": hashlib.sha256(source).hexdigest()}
    frozen, bindings = {}, []
    sender, calls = make_sender()

    class RoutingFailure(Exception):
        status_code = 404

    for index, (label, subpath, plan_path, cost) in enumerate([
            ("original", ".", protocol.PLAN, "0.13347786"),
            ("a1", "a1", a1.PLAN, "0.12906260")]):
        plan = deepcopy(base)
        previous = Decimal(0) if index == 0 else Decimal(bindings[0]["cost_bound_usd"])
        plan.update(prior_cost_usd=str(previous), cap_usd=str(Decimal("250") - previous),
                    screen_cap_usd=str(Decimal("40") - previous))
        if index:
            plan["schema"] = "openrouter-swap-a1"
            plan["models"]["deepseek"].pop("temperature")
            plan["prior_attempt"] = deepcopy(bindings[0])
        path = repository / plan_path
        write(path, plan)
        freeze, plan_hash = ("a" if index == 0 else "b") * 40, protocol.sha(path)
        runtime = {"freeze": freeze, "plan_sha256": plan_hash}
        if index:
            runtime.update(prior_cost_bound_usd=str(previous),
                           prior_journal_sha256=bindings[0]["journal_sha256"])
        prior = original / subpath
        write(prior / "runtime.json", runtime)
        first_call = len(calls)

        def old_sender(request):
            if request["model"] == plan["models"]["deepseek"]["id"] and not resolved:
                raise RoutingFailure("Synthetic private transport detail")
            response = sender(request)
            if len(calls) == first_call + 1:
                response["usage"]["cost"] = "0.09640350" if index == 0 else "0.09201200"
            return response

        with Ledger(prior / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = Runner(plan, freeze, plan_hash, ledger, old_sender)
            for item in plan["fixtures"]:
                for instrument in ("paper", "structured"):
                    if len(calls) - first_call < 11:
                        runner.judge(item["id"], item["response"], "astra", instrument, "fixtures")
            if prior_target:
                block = next(b for b in plan["screen"] if b["model"] == "gemini")
                runner.generate(block["sources"][0])
            if resolved:
                runner.route_fixture("deepseek")
            else:
                with pytest.raises(Halted):
                    runner.route_fixture("deepseek")
            if not (prior_target or resolved):
                assert ledger.spent() == Decimal(cost)
        binding = {"label": label, "path": subpath, "freeze": freeze, "plan_path": plan_path,
                   "plan_sha256": plan_hash, "journal_sha256": protocol.sha(prior / "raw/events.jsonl"),
                   "cost_bound_usd": cost, "calls": 12, "target_calls": 0}
        bindings.append(binding)
        frozen[f"{freeze}:{plan_path}"] = path.read_bytes()
        frozen[f"{freeze}:synthetic_source.py"] = source

    plan = deepcopy(plan)
    plan.update(schema="openrouter-swap-a2", models={m: plan["models"][m] for m in amendment.ACTIVE_MODELS},
                prior_cost_usd="0.26254046", cap_usd="249.73745954", screen_cap_usd="39.73745954",
                prior_attempts=deepcopy(bindings))
    plan.pop("prior_attempt")
    path = repository / amendment.PLAN
    write(path, plan)
    plan_hash = protocol.sha(path)
    write(root / "runtime.json", {"freeze": "c" * 40, "plan_sha256": plan_hash,
                                  "prior_cost_bound_usd": plan["prior_cost_usd"],
                                  "prior_attempts": deepcopy(bindings)})

    def new_sender(request):
        response = sender(request)
        if failed and request["messages"][0]["content"].startswith("Analyze the following response"):
            response["choices"][0]["message"]["content"] = "invalid paper label"
        return response

    with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = amendment.IndependentRunner(plan, "c" * 40, plan_hash, ledger, new_sender)
        write(root / "fixture_gate.json", runner.run_fixtures())
        if not failed:
            block = next(b for b in plan["screen"] if b["model"] == "gemini")
            spec = block["finals"][0]
            donor = next(s for s in block["sources"] if s["id"] == spec["source_id"])
            result = runner.generate(spec, runner.generate(donor)["response"])
            for judge in plan["judges"]:
                for instrument in ("paper", "structured"):
                    runner.judge(spec["id"], result["response"], judge, instrument, "screen")
        write(root / "snapshots/000001/audit.json", {"older": True})
        write(root / "snapshots/000033/audit.json", runner.audit())
        write(root / "snapshots/000033/screen_rows.json", runner.rows("screen"))
    write(root / "snapshots/000033/private.json", {"headers": {"authorization": "synthetic private marker"}})
    (root / ".env").write_text("synthetic private marker\n")
    (original / ".env").write_text("synthetic prior private marker\n")
    frozen[f"{'c' * 40}:{amendment.PLAN}"] = path.read_bytes()
    frozen[f"{'c' * 40}:synthetic_source.py"] = source
    checked, verified = [], []
    real_output = release.subprocess.check_output

    def git_show(command, **kwargs):
        if command[0] != "git":
            return real_output(command, **kwargs)
        assert command[:2] == ["git", "show"]
        assert kwargs["cwd"] == repository
        checked.append(command[2])
        return frozen[command[2]]

    def verify_amendment(path, freeze=None):
        assert freeze is None
        verified.append(Path(path))
        assert release._load(path) == plan
        return deepcopy(plan)

    monkeypatch.setattr(protocol, "ROOT", repository)
    monkeypatch.setattr(amendment, "PRIORS", bindings)
    monkeypatch.setattr(amendment, "verify", verify_amendment)
    monkeypatch.setattr(release.subprocess, "check_output", git_show)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    return root, plan, calls, checked, frozen


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root, plan, calls, checked, frozen = synthetic_run(tmp_path, monkeypatch)
    destination = tmp_path / "release"
    before = inventory(root.parent)
    assert release.build(root, destination)["status"] == "incomplete"
    assert inventory(root.parent) == before
    return root, destination, plan, calls, checked, frozen


def refresh_manifest(destination):
    value = release._load(destination / "MANIFEST.json")
    write(destination / "MANIFEST.json", {**value, "files": release._inventory(destination)})


def test_three_journal_roundtrip_with_deferred_missingness(bundle):
    root, destination, plan, calls, checked, _ = bundle
    manifest = release._load(destination / "MANIFEST.json")["files"]
    assert not any("private" in name or ".env" in name or "000001" in name for name in manifest)
    for name, source in [("raw/events.jsonl.gz", root / "raw/events.jsonl"),
                         ("prior_attempts/original/events.jsonl.gz", root.parent / "raw/events.jsonl"),
                         ("prior_attempts/a1/events.jsonl.gz", root.parent / "a1/raw/events.jsonl")]:
        compressed = (destination / name).read_bytes()
        assert compressed[4:8] == b"\0\0\0\0"
        assert gzip.decompress(compressed) == source.read_bytes()
    for binding in plan["prior_attempts"]:
        prior = destination / "prior_attempts" / binding["label"]
        assert (prior / "PLAN.json").read_bytes() == (protocol.ROOT / binding["plan_path"]).read_bytes()
        assert f"{binding['freeze']}:{binding['plan_path']}" in checked
    assert f"{'c' * 40}:{amendment.PLAN}" in checked
    assert all(f"{freeze * 40}:synthetic_source.py" in checked for freeze in "abc")
    metadata = release._load(destination / "RELEASE.json")
    assert metadata["prior_cost_bound_usd"] == "0.26254046"
    assert Decimal(metadata["cumulative_cost_bound_usd"]) == Decimal("0.26254046") + Decimal(metadata["attempt_cost_bound_usd"])
    assert all(p["audit"]["calls"] == 12 and p["audit"]["unresolved"] == 1 and p["target_calls"] == 0
               for p in metadata["prior_attempts"])
    assert metadata["fixtures_pass"] is True and metadata["active_models"] == list(amendment.ACTIVE_MODELS)
    assert metadata["deferred_models"]["deepseek"]["status"] == "deferred_before_targets"
    counts = release._load(destination / "FIGURE_COUNTS.json")["screen_astra_inclusive"]
    assert set(counts) == {"gemini", "sonnet", "opus", "deepseek"}
    assert all(c == {"positive": 0, "labeled": 0, "planned": 12, "missing": 12, "rate": None}
               for c in counts["deepseek"].values())
    assert all(c["model"] != protocol.MODELS["deepseek"]["id"] for c in calls[22:])
    assert (destination / "screen_astra_inclusive.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (destination / "screen_opus_inclusive.pdf").read_bytes().startswith(b"%PDF-")
    before, source_before, count = inventory(destination), inventory(root.parent), len(calls)
    assert release.verify(destination)["pass"]
    assert inventory(destination) == before and inventory(root.parent) == source_before
    assert len(calls) == count


@pytest.mark.parametrize("label", ["original", "a1"])
@pytest.mark.parametrize("mutation", ["journal", "runtime", "plan"])
def test_prior_tampering_survives_manifest_rehash(bundle, label, mutation):
    _, destination, _, _, _, _ = bundle
    prior = destination / "prior_attempts" / label
    if mutation == "journal":
        path = prior / "events.jsonl.gz"
        path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()) + b"\n", mtime=0))
    else:
        path = prior / ("runtime.json" if mutation == "runtime" else "PLAN.json")
        value = release._load(path)
        value["freeze" if mutation == "runtime" else "cap_usd"] = "d" * 40 if mutation == "runtime" else "251"
        write(path, value)
    refresh_manifest(destination)
    with pytest.raises((ValueError, Halted, KeyError)):
        release.verify(destination)


@pytest.mark.parametrize("mutation", ["cap_usd", "screen_cap_usd", "prior_cost_usd", "cost_bound_usd", "order", "path"])
def test_plan_cannot_reset_budgets_or_rebind_prior_chain(bundle, mutation):
    _, _, plan, _, _, _ = bundle
    changed = deepcopy(plan)
    if mutation in {"cap_usd", "screen_cap_usd"}:
        changed[mutation] = str(Decimal(changed[mutation]) + Decimal("0.01"))
    elif mutation == "prior_cost_usd":
        changed[mutation] = "0"
    elif mutation == "order":
        changed["prior_attempts"].reverse()
    else:
        changed["prior_attempts"][1][mutation] = "0" if mutation == "cost_bound_usd" else "../elsewhere"
    with pytest.raises(ValueError, match="Prior chain|caps"):
        release._bindings(changed)


@pytest.mark.parametrize("name", [".env", "headers.json", "snapshots/000033/extra.json", "prior_attempts/a1/extra.json"])
def test_extra_payload_is_rejected_even_when_manifest_is_rehashed(bundle, name):
    _, destination, _, _, _, _ = bundle
    write(destination / name, {"extra": "synthetic private marker"})
    refresh_manifest(destination)
    with pytest.raises(ValueError, match="allowlist"):
        release.verify(destination)


def test_allowed_json_cannot_smuggle_headers(bundle, tmp_path):
    root, destination, _, _, _, _ = bundle
    value = release._load(root / "runtime.json")
    write(root / "runtime.json", {**value, "headers": {"authorization": "synthetic"}})
    with pytest.raises(ValueError, match="headers"):
        release.build(root, tmp_path / "private-release")
    write(destination / "snapshots/000033/audit.json", {"response_headers": {"cookie": "synthetic"}})
    refresh_manifest(destination)
    with pytest.raises(ValueError, match="headers"):
        release.verify(destination)


@pytest.mark.parametrize("mutation", ["cost", "chain", "report", "counts", "source"])
def test_runtime_reports_and_git_sources_are_bound(bundle, mutation):
    _, destination, _, _, _, frozen = bundle
    if mutation == "source":
        frozen[f"{'b' * 40}:synthetic_source.py"] = b"tampered source"
    else:
        name = {"cost": "runtime.json", "chain": "runtime.json", "report": "RELEASE.json", "counts": "FIGURE_COUNTS.json"}[mutation]
        value = release._load(destination / name)
        if mutation == "chain":
            value["prior_attempts"][0]["journal_sha256"] = "0" * 64
        else:
            key = {"cost": "prior_cost_bound_usd", "report": "cumulative_cost_bound_usd", "counts": "screen_astra_inclusive"}[mutation]
            value[key] = {} if mutation == "counts" else "0"
        write(destination / name, value)
        refresh_manifest(destination)
    with pytest.raises(ValueError):
        release.verify(destination)


@pytest.mark.parametrize("prior_target,resolved,match", [(True, False, "target calls"), (False, True, "accounting")])
def test_target_exposure_or_resolved_charge_forgiveness_is_rejected(tmp_path, monkeypatch, prior_target, resolved, match):
    root, _, _, _, _ = synthetic_run(tmp_path, monkeypatch, prior_target=prior_target, resolved=resolved)
    with pytest.raises(ValueError, match=match):
        release.build(root, tmp_path / "release")


def test_no_overwrite_or_source_and_release_symlinks(bundle, tmp_path):
    root, destination, _, _, _, _ = bundle
    before = inventory(destination)
    with pytest.raises(FileExistsError):
        release.build(root, destination)
    assert inventory(destination) == before
    path = root.parent / "a1/runtime.json"
    path.unlink()
    path.symlink_to(root / "runtime.json")
    with pytest.raises(Halted, match="Symlink"):
        release.build(root, tmp_path / "bad-release")
    path = destination / "prior_attempts/original/events.jsonl.gz"
    replacement = tmp_path / "prior.gz"
    shutil.copyfile(path, replacement)
    path.unlink()
    path.symlink_to(replacement)
    with pytest.raises(Halted, match="Symlink"):
        release.verify(destination)


def test_failed_fixtures_remain_incomplete_with_both_priors(tmp_path, monkeypatch):
    root, _, _, _, _ = synthetic_run(tmp_path, monkeypatch, failed=True)
    destination = tmp_path / "release"
    assert release.build(root, destination)["status"] == "incomplete"
    metadata = release._load(destination / "RELEASE.json")
    assert not metadata["fixtures_pass"] and len(metadata["prior_attempts"]) == 2
    assert metadata["audit"]["calls"] == 39


def test_completion_ignores_deferred_rows_but_requires_every_active_endpoint(bundle, monkeypatch):
    _, destination, _, _, _, _ = bundle
    metadata, _, _ = release._replay(destination)
    assert metadata["status"] == "incomplete"
    with monkeypatch.context() as patch:
        # Isolate the completion predicate from the synthetic partial data.
        patch.setattr(release.analysis, "_value", lambda row, judge, endpoint: None if row["model"] == "deepseek" else True)
        admission = {"admitted_models": []}
        patch.setattr(amendment.IndependentRunner, "main_admission", lambda self: admission)
        write(destination / "main_admission.json", admission)
        assert release._replay(destination)[0]["status"] == "complete"
        patch.setattr(release.analysis, "_value", lambda row, judge, endpoint: None if endpoint == release.analysis.ENDPOINTS[0] else True)
        assert release._replay(destination)[0]["status"] == "incomplete"


def test_cli_and_original_source_closure(bundle, monkeypatch, capsys):
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


def test_original_sources_remain_frozen():
    assert "tests/test_openrouter_isolation_release.py" not in protocol.source_paths()
    assert protocol.verify(protocol.ROOT / protocol.PLAN)["prior_cost_usd"] == "0"
    assert a1.verify(protocol.ROOT / a1.PLAN)["prior_cost_usd"] == "0.13347786"
