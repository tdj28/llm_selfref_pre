"""Synthetic offline A3 release checks; no service calls or study outcomes."""

from copy import deepcopy
from decimal import Decimal
import gzip
import hashlib
from pathlib import Path

import pytest

from experiments import openrouter_swap_release_a3 as release
from experiments.openrouter_swap import protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1 import amendment as a1
from experiments.openrouter_swap_a2 import amendment as a2
from experiments.openrouter_swap_a3 import amendment
from tests.test_openrouter_recovery_release import inventory, write
from tests.test_openrouter_swap_runner import make_sender


def synthetic_run(tmp_path, monkeypatch, *, refused=False):
    repository, original = tmp_path / "repo", tmp_path / "run"
    source = b"synthetic frozen source\n"
    plan = protocol.build({})
    plan["source_hashes"] = {"synthetic_source.py": hashlib.sha256(source).hexdigest()}
    sender, calls = make_sender()
    frozen, bindings, checked = {}, [], []

    class RoutingFailure(Exception):
        status_code = 404

    for index, (label, subpath, plan_path, cost) in enumerate([
            ("original", ".", protocol.PLAN, "0.13347786"),
            ("a1", "a1", a1.PLAN, "0.12906260"),
            ("a2", "a2", a2.PLAN, "0.357945")]):
        plan = deepcopy(plan)
        previous = sum((Decimal(p["cost_bound_usd"]) for p in bindings), Decimal(0))
        plan.update(prior_cost_usd=str(previous), cap_usd=str(Decimal("250") - previous),
                    screen_cap_usd=str(Decimal("40") - previous))
        if index == 1:
            plan["models"]["deepseek"].pop("temperature")
            plan["prior_attempt"] = deepcopy(bindings[0])
        elif index == 2:
            plan.pop("prior_attempt")
            plan.update(models={m: plan["models"][m] for m in a2.ACTIVE_MODELS},
                        prior_attempts=deepcopy(bindings),
                        deferred_models={"deepseek": {"status": "not_run_privacy_route_unavailable"}})
        path, root, freeze = repository / plan_path, original / subpath, "abc"[index] * 40
        write(path, plan)
        plan_hash = protocol.sha(path)
        runtime = {"freeze": freeze, "plan_sha256": plan_hash}
        if index == 1:
            runtime.update(prior_cost_bound_usd=str(previous),
                           prior_journal_sha256=bindings[0]["journal_sha256"])
        elif index == 2:
            runtime.update(prior_cost_bound_usd=str(previous), prior_attempts=deepcopy(bindings))
        write(root / "runtime.json", runtime)
        start = len(calls)

        def prior_sender(request):
            if index < 2 and request["model"] == protocol.MODELS["deepseek"]["id"]:
                raise RoutingFailure("Synthetic private transport detail")
            response = sender(request)
            if index < 2 and len(calls) == start + 1:
                response["usage"]["cost"] = ("0.09640350", "0.09201200")[index]
            elif index == 2:
                response["usage"]["cost"] = "0.097945" if len(calls) == start + 2 else "0.01"
                if request["model"] == protocol.MODELS["gemini"]["id"]:
                    response["choices"][0]["message"]["content"] = "OK."
            return response

        with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = Runner(plan, freeze, plan_hash, ledger, prior_sender)
            for item in plan["fixtures"]:
                for judge in (list(plan["judges"]) if index == 2 else ["astra"]):
                    for instrument in ("paper", "structured"):
                        if index == 2 or len(calls) - start < 11:
                            runner.judge(item["id"], item["response"], judge, instrument, "fixtures")
            if index == 2:
                for model in a2.ACTIVE_MODELS:
                    runner.route_fixture(model)
                gate = amendment.adjudicate_gate(runner.run_fixtures())
                assert gate["pass"] and not gate["original_gate"]["pass"]
            else:
                with pytest.raises(Halted):
                    runner.route_fixture("deepseek")
            assert ledger.spent() == Decimal(cost)
        binding = {"label": label, "path": subpath, "freeze": freeze, "plan_path": plan_path,
                   "plan_sha256": plan_hash, "journal_sha256": protocol.sha(root / "raw/events.jsonl"),
                   "cost_bound_usd": cost, "calls": 27 if index == 2 else 12, "target_calls": 0}
        if index == 2:
            binding["unresolved"] = 0
        bindings.append(binding)
        frozen[f"{freeze}:{plan_path}"] = path.read_bytes()
        frozen[f"{freeze}:synthetic_source.py"] = source

    plan.update(schema="openrouter-swap-a3", prior_attempts=deepcopy(bindings),
                prior_cost_usd="0.62048546", cap_usd="249.37951454", screen_cap_usd="39.37951454")
    path, root, freeze = repository / amendment.PLAN, original / "a3", "d" * 40
    write(path, plan)
    plan_hash = protocol.sha(path)
    write(root / "runtime.json", {"freeze": freeze, "plan_sha256": plan_hash,
                                  "prior_attempts": bindings, "prior_cost_bound_usd": plan["prior_cost_usd"]})
    write(root / "fixture_gate.json", gate)
    target_start = len(calls)

    def target_sender(request):
        response = sender(request)
        if refused and len(calls) == target_start + 2:
            response["choices"][0]["message"] = {"role": "assistant", "content": "", "refusal": "Synthetic refusal"}
        return response

    with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = amendment.A3Runner(plan, freeze, plan_hash, ledger, target_sender, fixture_gate=gate)
        block = next(b for b in plan["screen"] if b["model"] == "gemini")
        spec = block["finals"][0]
        donor = next(s for s in block["sources"] if s["id"] == spec["source_id"])
        response = runner.generate(spec, runner.generate(donor)["response"])["response"]
        if not refused:
            for judge in plan["judges"]:
                for instrument in ("paper", "structured"):
                    runner.judge(spec["id"], response, judge, instrument, "screen")
        write(root / "snapshots/000006/audit.json", runner.audit())
    write(root / "snapshots/000006/private.json", {"headers": {"authorization": "synthetic"}})
    frozen[f"{freeze}:{amendment.PLAN}"] = path.read_bytes()
    frozen[f"{freeze}:synthetic_source.py"] = source

    real_output = release.subprocess.check_output

    def git_show(command, **kwargs):
        if command[0] != "git":
            return real_output(command, **kwargs)
        assert command[:2] == ["git", "show"]
        assert kwargs["cwd"] == repository
        checked.append(command[2])
        return frozen[command[2]]

    def verify_plan(path, freeze=None):
        assert freeze is None
        if release._load(Path(path)) != plan:
            raise Halted("Synthetic frozen plan mismatch")
        return deepcopy(plan)

    monkeypatch.setattr(protocol, "ROOT", repository)
    monkeypatch.setattr(a2, "PRIORS", bindings[:2])
    monkeypatch.setattr(amendment, "PRIORS", bindings)
    monkeypatch.setattr(amendment, "verify", verify_plan)
    monkeypatch.setattr(release.subprocess, "check_output", git_show)
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "mpl"))
    return root, plan, calls, checked


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root, plan, calls, checked = synthetic_run(tmp_path, monkeypatch)
    destination = tmp_path / "release"
    before, count = inventory(root.parent), len(calls)
    assert release.build(root, destination)["status"] == "incomplete"
    assert inventory(root.parent) == before and len(calls) == count
    return root, destination, plan, calls, checked


def refresh_manifest(destination):
    manifest = release._load(destination / "MANIFEST.json")
    write(destination / "MANIFEST.json", {
        **manifest, "files": release._manifest_files(release._inventory(destination))})


def test_four_journal_offline_roundtrip_preserves_cost_failure_and_full_inventories(bundle):
    root, destination, plan, calls, checked = bundle
    manifest = release._load(destination / "MANIFEST.json")
    assert manifest["files"] == [
        {"path": name, "bytes": entry["size"], "sha256": entry["sha256"]}
        for name, entry in sorted(release._inventory(destination).items())]
    for invalid in (release._inventory(destination), manifest["files"][:-1],
                    manifest["files"] + [manifest["files"][0]],
                    [{**entry, "bytes": float(entry["bytes"])} for entry in manifest["files"]],
                    [{**entry, "sha256": "0" * 64} for entry in manifest["files"]],
                    [{**entry, "extra": True} for entry in manifest["files"]]):
        write(destination / "MANIFEST.json", {**manifest, "files": invalid})
        with pytest.raises(ValueError, match="inventory or hash mismatch"):
            release.verify(destination)
    write(destination / "MANIFEST.json", manifest)
    extra = destination / "private.json"
    write(extra, {"headers": {"authorization": "synthetic"}})
    with pytest.raises(ValueError, match="inventory or hash mismatch"):
        release.verify(destination)
    refresh_manifest(destination)
    with pytest.raises(ValueError, match="outside the publication allowlist"):
        release.verify(destination)
    extra.unlink()
    snapshot = destination / "snapshots/000006/audit.json"
    audit = release._load(snapshot)
    write(snapshot, {**audit, "headers": {"authorization": "synthetic"}})
    refresh_manifest(destination)
    with pytest.raises(ValueError):
        release.verify(destination)
    write(snapshot, audit)
    refresh_manifest(destination)
    for binding in plan["prior_attempts"]:
        prior = destination / "prior_attempts" / binding["label"]
        assert gzip.decompress((prior / "events.jsonl.gz").read_bytes()) == (
            root.parent / binding["path"] / "raw/events.jsonl").read_bytes()
        assert (prior / "PLAN.json").read_bytes() == (protocol.ROOT / binding["plan_path"]).read_bytes()
        assert f"{binding['freeze']}:{binding['plan_path']}" in checked
    raw = (destination / "raw/events.jsonl.gz").read_bytes()
    assert raw[4:8] == b"\0\0\0\0"
    assert gzip.decompress(raw) == (root / "raw/events.jsonl").read_bytes()
    assert all(f"{c * 40}:synthetic_source.py" in checked for c in "abcd")
    report = release._load(destination / "RELEASE.json")
    assert report["prior_cost_bound_usd"] == "0.62048546"
    assert Decimal(report["cumulative_cost_bound_usd"]) == Decimal("0.62048546") + Decimal(report["attempt_cost_bound_usd"])
    assert [p["audit"]["unresolved"] for p in report["prior_attempts"]] == [1, 1, 0]
    assert [p["audit"]["calls"] for p in report["prior_attempts"]] == [12, 12, 27]
    gate = report["fixture_gate"]
    assert gate == release._load(root / "fixture_gate.json") and gate["pass"]
    assert gate["original_gate"]["pass"] is False and gate["original_gate"]["judges"]["pass"] is True
    assert report["prior_attempts"][2]["fixture_gate"] == gate["original_gate"]
    assert report["phase_status"] == {"screen": "incomplete", "main": "pending_admission"}
    collected = report["collection_inventory"]
    assert collected["screen"]["gemini"]["finals"] == {"planned": 48, "requested": 1, "settled": 1}
    assert collected["screen"]["gemini"]["judgments"]["settled_calls"] == 4
    assert collected["screen"]["deepseek"]["scheduled"] is False
    assert collected["main"]["gemini"]["scheduled"] is None
    for name, panel in release._load(destination / "FIGURE_COUNTS.json").items():
        assert set(panel) == {"gemini", "sonnet", "opus", "deepseek"}
        count = 12 if name.startswith("screen") else 32
        assert all(c == {"positive": 0, "labeled": 0, "planned": count, "missing": count, "rate": None}
                   for c in panel["deepseek"].values())
    assert not any("private" in name for name in release._inventory(destination))
    assert (destination / "main_opus_inclusive.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    before, source_before, count = inventory(destination), inventory(root.parent), len(calls)
    assert release.verify(destination)["pass"]
    assert inventory(destination) == before and inventory(root.parent) == source_before and len(calls) == count


@pytest.mark.parametrize("label", ["original", "a1", "a2"])
@pytest.mark.parametrize("mutation", ["journal", "runtime", "plan"])
def test_each_prior_remains_bound_after_manifest_rehash(bundle, label, mutation):
    _, destination, _, _, _ = bundle
    prior = destination / "prior_attempts" / label
    if mutation == "journal":
        path = prior / "events.jsonl.gz"
        path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()) + b"\n", mtime=0))
    else:
        path = prior / ("runtime.json" if mutation == "runtime" else "PLAN.json")
        value = release._load(path)
        value["plan_sha256" if mutation == "runtime" else "cap_usd"] = "0" * 64 if mutation == "runtime" else "251"
        write(path, value)
    refresh_manifest(destination)
    with pytest.raises((ValueError, Halted)):
        release.verify(destination)


@pytest.mark.parametrize("mutation", ["original_failure", "route_text", "pass", "cost", "new_fixture"])
def test_failure_gate_cost_and_target_only_boundary_cannot_be_rewritten(bundle, mutation):
    root, destination, plan, _, _ = bundle
    if mutation == "new_fixture":
        runtime = release._load(root / "runtime.json")
        sender, _ = make_sender()
        with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            Runner(plan, runtime["freeze"], runtime["plan_sha256"], ledger, sender).route_fixture("gemini")
        (destination / "raw/events.jsonl.gz").write_bytes(gzip.compress((root / "raw/events.jsonl").read_bytes(), mtime=0))
    else:
        path = destination / ("runtime.json" if mutation == "cost" else "fixture_gate.json")
        value = release._load(path)
        if mutation == "original_failure":
            value["original_gate"]["pass"] = True
        elif mutation == "route_text":
            value["original_gate"]["routes"][0]["response"] = "OK"
        elif mutation == "pass":
            value["pass"] = False
        else:
            value["prior_cost_bound_usd"] = "0"
        write(path, value)
    refresh_manifest(destination)
    with pytest.raises(ValueError):
        release.verify(destination)


def test_completion_distinguishes_finished_screen_from_pending_or_unfinished_main(bundle, monkeypatch):
    _, destination, _, _, _ = bundle
    monkeypatch.setattr(release.analysis, "_value", lambda row, judge, endpoint: None if row["model"] == "deepseek" else True)
    report = release._replay(destination)[0]
    assert report["status"] == "incomplete"
    assert report["current_phase"] == "screen" and report["current_phase_status"] == "complete"
    admission = {"admitted_models": []}
    monkeypatch.setattr(amendment.A3Runner, "main_admission", lambda self: deepcopy(admission))
    write(destination / "main_admission.json", admission)
    assert release._replay(destination)[0]["status"] == "complete"
    admission["admitted_models"] = ["gemini"]
    write(destination / "main_admission.json", admission)
    monkeypatch.setattr(release.analysis, "_value", lambda row, judge, endpoint: None if row["phase"] == "main" else True)
    report, rows, _ = release._replay(destination)
    assert report["status"] == "incomplete" and report["current_phase_status"] == "incomplete"
    assert report["current_phase"] == "main" and len(rows["main"]) == 1024


def test_postcollection_adapter_is_not_a_frozen_input():
    plan = amendment.build()
    assert "experiments/openrouter_swap_release_a3.py" not in plan["source_hashes"]
    assert "tests/test_openrouter_punctuation_release.py" not in plan["source_hashes"]
    assert "tests/test_openrouter_punctuation.py" in plan["source_hashes"]


def test_settled_refusal_is_not_reported_as_an_unresolved_call(tmp_path, monkeypatch):
    root, _, _, _ = synthetic_run(tmp_path, monkeypatch, refused=True)
    destination = tmp_path / "release"
    assert release.build(root, destination)["status"] == "incomplete"
    report = release._load(destination / "RELEASE.json")
    counts = report["collection_inventory"]["screen"]["gemini"]
    assert counts["finals"] == {"planned": 48, "requested": 1, "settled": 1}
    assert counts["unresolved_calls"] == 0 and counts["judgments"]["requested_calls"] == 0
    assert counts["missing_final_responses"] == 48
    assert "not API collection completion" in report["status_definition"]
