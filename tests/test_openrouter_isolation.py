"""Offline A2 isolation checks; synthetic receipts are not study outcomes."""

from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from experiments.openrouter_swap import analysis, protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.runner import Runner
from experiments.openrouter_swap_a1 import amendment as a1
from experiments.openrouter_swap_a2 import amendment
from tests.test_openrouter_swap_runner import make_sender


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Isolation tests must not make network requests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def test_original_and_a1_source_bound_plans_remain_valid():
    paths = [protocol.ROOT / protocol.PLAN, protocol.ROOT / a1.PLAN]
    before = {path: path.read_bytes() for path in paths}
    assert protocol.verify(paths[0])["schema"] == "openrouter-swap-v1"
    assert a1.verify(paths[1])["schema"] == "openrouter-swap-a1"
    amendment.build()
    assert {path: path.read_bytes() for path in paths} == before


def test_only_active_roster_and_declared_accounting_change():
    old = a1.verify(protocol.ROOT / a1.PLAN)
    original = deepcopy(old)
    plan = amendment.build()
    assert amendment.ACTIVE_MODELS == ("gemini", "sonnet", "opus")
    assert plan["models"] == {name: old["models"][name] for name in amendment.ACTIVE_MODELS}
    assert plan["active_models"] == list(amendment.ACTIVE_MODELS)
    assert set(plan["deferred_models"]) == {"deepseek"}
    assert plan["deferred_models"]["deepseek"]["status"] == "not_run_privacy_route_unavailable"
    for key in (
        "screen", "main", "judges", "fixtures", "qualification", "analysis",
        "projection", "retries", "neutral_instruction", "experiential_query",
        "endpoint_metadata", "generation_output_cap", "generation_workers",
        "judge_workers", "publication",
    ):
        assert plan[key] == old[key], key
    assert plan["analysis"]["primary_family_size"] == analysis.FAMILY_SIZE == 8
    for phase in ("screen", "main"):
        assert {block["model"] for block in plan[phase]} == set(protocol.MODELS)
    assert old == original
    plan["models"]["gemini"]["id"] = "synthetic-mutation"
    plan["screen"][0]["sources"].clear()
    rebuilt = amendment.build()
    assert rebuilt["models"]["gemini"] == original["models"]["gemini"]
    assert rebuilt["screen"] == original["screen"]


def test_cumulative_cost_and_remaining_caps():
    plan = amendment.build()
    assert amendment.PRIOR_COST == Decimal("0.26254046")
    assert Decimal(plan["prior_cost_usd"]) == amendment.PRIOR_COST
    assert Decimal(plan["cap_usd"]) == Decimal("249.73745954")
    assert Decimal(plan["screen_cap_usd"]) == Decimal("39.73745954")
    assert len(amendment.PRIORS) == 2
    assert sum((Decimal(binding["cost_bound_usd"]) for binding in amendment.PRIORS), Decimal(0)) == amendment.PRIOR_COST
    assert plan["prior_attempts"] == amendment.PRIORS
    assert {binding["path"] for binding in amendment.PRIORS} == {".", "a1"}
    assert all(binding["calls"] == 12 and binding["target_calls"] == 0 for binding in amendment.PRIORS)


def test_a2_root_is_a_fixed_sibling_of_a1(tmp_path, monkeypatch):
    monkeypatch.setattr(amendment, "original_root", lambda: tmp_path)
    assert amendment.canonical_run_root() == tmp_path / "a2"


def test_paid_cli_reuses_a1_safe_sender_without_dispatch(monkeypatch):
    plan = amendment.build()
    sender, seen = make_sender()
    keys = []

    def sender_for(key):
        keys.append(key)
        return sender

    def stop_before_ledger():
        raise Halted("Synthetic stop before opening a ledger")

    monkeypatch.setattr(amendment, "verify", lambda *_: plan)
    monkeypatch.setattr(a1, "sender_for", sender_for)
    monkeypatch.setattr(amendment, "canonical_run_root", stop_before_ledger)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-offline-only")
    monkeypatch.setattr("sys.argv", ["amendment", "--freeze", "a" * 40, "--execute", "--phase", "audit"])
    with pytest.raises(Halted, match="Synthetic stop"):
        amendment.main()
    assert keys == ["synthetic-offline-only"]
    assert seen == []


@pytest.mark.parametrize("phase,cost", [("main", "250"), ("screen", "40"), ("fixtures", "40")])
def test_prior_cost_cannot_be_reset(tmp_path, phase, cost):
    plan = amendment.build()
    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        with pytest.raises(Halted):
            ledger.reserve("synthetic-over-budget", {}, cost, phase, {})
        assert ledger.rows() == []


def test_three_routes_all_judges_and_initial_blocks_preserve_missingness(tmp_path):
    plan = amendment.build()
    sender, seen = make_sender()
    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = amendment.IndependentRunner(plan, "a" * 40, "b" * 64, ledger, sender)
        gate = runner.run_fixtures()
        assert gate["pass"]
        assert {route["model"] for route in gate["routes"]} == {
            plan["models"][name]["id"] for name in amendment.ACTIVE_MODELS
        }
        assert len(gate["rows"]) == 24
        assert len(seen) == 27
        assert {
            (row["item_id"], row["judge"], row["instrument"]) for row in gate["rows"]
        } == {
            (item["id"], judge, instrument)
            for item in plan["fixtures"] for judge in plan["judges"]
            for instrument in ("paper", "structured")
        }

        runner.run_blocks("screen", initial=True)
        paid = ledger.rows()
        generations = [row for row in paid if row["metadata"]["kind"] == "generation"]
        assert Counter(row["metadata"]["role"] for row in generations) == {"source": 12, "final": 24}
        assert Counter(row["metadata"]["model"] for row in generations) == dict.fromkeys(amendment.ACTIVE_MODELS, 12)
        assert {row["metadata"]["block"] for row in generations} == {1, 2}
        assert len(seen) == 159  # 27 fixtures, 12 sources, 24 finals, 96 judgments.
        assert all(request["model"] != protocol.MODELS["deepseek"]["id"] for request in seen)
        assert runner.audit()["pass"]

        rows = runner.rows("screen")
        assert len(rows) == 192
        assert sum(row["response"] is not None for row in rows) == 24
        missing = [row for row in rows if row["model"] == "deepseek"]
        assert len(missing) == 48
        assert all(row["response"] is None and row["status"] == "not_generated" and row["labels"] == {}
                   for row in missing)
        qualification = analysis.qualify(rows)
        assert qualification["inventory_valid"]
        deferred = qualification["models"]["deepseek"]
        assert not deferred["qualified"]
        for judge in deferred["judges"].values():
            assert judge["missing"] == judge["inclusive_missing"] == 48
            assert judge["positive"] == judge["negative"] == 0
        admission = runner.main_admission()
        assert "deepseek" not in admission["eligible_models"]
        assert "deepseek" not in admission["admitted_models"]
        assert admission["projections"]["deepseek"]["status"] == "not_run_privacy_route_unavailable"
        reported = amendment.qualification(rows, plan)["models"]["deepseek"]
        assert reported["decision"] == "not_run"
        assert reported["unrun_inventory_diagnostics"]["decision"] == "fail"
        assert reported["reason_codes"] == ["not_run_privacy_route_unavailable"]

        before = ledger.spent()
        runner.run_blocks("screen", initial=True)
        assert len(seen) == 159
        assert ledger.spent() == before

    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        replay = amendment.IndependentRunner(plan, "a" * 40, "b" * 64, ledger)
        assert replay.require_fixtures()["pass"]
        assert replay.audit()["calls"] == 159
        assert replay.rows("screen") == rows


@pytest.mark.parametrize("phase", ["screen", "main"])
@pytest.mark.parametrize("models", [("deepseek",), ("gemini", "deepseek"), ("unknown",)])
def test_explicit_inactive_models_never_dispatch(tmp_path, phase, models):
    sender, seen = make_sender()
    with Ledger(tmp_path) as ledger:
        runner = amendment.IndependentRunner(amendment.build(), "a" * 40, "b" * 64, ledger, sender)
        assert runner.run_fixtures()["pass"]
        before = ledger.rows()
        with pytest.raises(Halted):
            runner.run_blocks(phase, models=models, initial=True)
        assert ledger.rows() == before
        assert len(seen) == 27


def test_inactive_route_and_generation_have_no_paid_bypass(tmp_path):
    plan = amendment.build()
    sender, seen = make_sender()
    source = next(block["sources"][0] for block in plan["screen"] if block["model"] == "deepseek")
    with Ledger(tmp_path) as ledger:
        runner = amendment.IndependentRunner(plan, "a" * 40, "b" * 64, ledger, sender)
        for action in (lambda: runner.route_fixture("deepseek"), lambda: runner.generate(source)):
            with pytest.raises((Halted, KeyError)):
                action()
        assert seen == []
        assert ledger.rows() == []


@pytest.mark.parametrize("phase", ["screen", "main"])
@pytest.mark.parametrize("models", [None, (), ("sonnet",)])
def test_dispatch_filter_preserves_explicit_active_subset(tmp_path, monkeypatch, phase, models):
    selected = []

    def record(self, phase, models=None, initial=False):
        selected.append((phase, tuple(models), initial))

    monkeypatch.setattr(Runner, "run_blocks", record)
    with Ledger(tmp_path) as ledger:
        runner = amendment.IndependentRunner(amendment.build(), "a" * 40, "b" * 64, ledger)
        runner.run_blocks(phase, models=models, initial=True)
    assert selected == [(phase, amendment.ACTIVE_MODELS if models is None else models, True)]


def test_initial_targets_require_fixtures(tmp_path):
    sender, seen = make_sender()
    with Ledger(tmp_path) as ledger:
        runner = amendment.IndependentRunner(amendment.build(), "a" * 40, "b" * 64, ledger, sender)
        with pytest.raises(Halted):
            runner.run_blocks("screen", initial=True)
        assert seen == []
        assert ledger.rows() == []


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("changed", [None, "journal", "freeze", "plan_sha256", "plan"])
def test_prior_hash_and_runtime_bindings(tmp_path, monkeypatch, index, changed):
    binding = deepcopy(amendment.PRIORS[index])
    (tmp_path / "raw").mkdir()
    journal = tmp_path / "raw/events.jsonl"
    journal.write_text("synthetic prior journal\n")
    binding["journal_sha256"] = protocol.sha(journal)
    runtime = {key: binding[key] for key in ("freeze", "plan_sha256")}
    if changed in runtime:
        runtime[changed] = "0" * len(runtime[changed])
    (tmp_path / "runtime.json").write_text(json.dumps(runtime))
    if changed == "journal":
        journal.write_text("changed synthetic prior journal\n")
    if changed == "plan":
        real_sha = protocol.sha
        bound_path = protocol.ROOT / binding["plan_path"]
        monkeypatch.setattr(protocol, "sha", lambda path: "0" * 64 if Path(path) == bound_path else real_sha(path))
    if changed is None:
        assert amendment.verify_prior(tmp_path, binding) == json.loads(
            (protocol.ROOT / binding["plan_path"]).read_text()
        )
    else:
        with pytest.raises(Halted):
            amendment.verify_prior(tmp_path, binding)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("changed", [None, "count", "unresolved", "cost", "target", "request"])
def test_prior_audit_rebuilds_calls_and_preserves_failed_charge(tmp_path, monkeypatch, index, changed):
    binding = deepcopy(amendment.PRIORS[index])
    plan = json.loads((protocol.ROOT / binding["plan_path"]).read_text())
    sender, seen = make_sender()

    def prior_sender(request):
        if request["model"] == plan["models"]["deepseek"]["id"] and changed != "unresolved":
            raise TimeoutError("Synthetic unavailable prior route")
        return sender(request)

    with Ledger(tmp_path / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = Runner(plan, binding["freeze"], binding["plan_sha256"], ledger, prior_sender)
        fixtures = [(item, instrument) for item in plan["fixtures"] for instrument in ("paper", "structured")]
        count = 10 if changed in {"count", "target"} else 11
        for item, instrument in fixtures[:count]:
            runner.judge(item["id"], item["response"], "astra", instrument, "fixtures")
        if changed == "target":
            source = next(block["sources"][0] for block in plan["screen"] if block["model"] == "gemini")
            runner.generate(source)
        if changed == "unresolved":
            runner.route_fixture("deepseek")
        else:
            with pytest.raises(Halted):
                runner.route_fixture("deepseek")
        failed = ledger.existing("route:deepseek")
        if changed != "unresolved":
            assert failed["cost_known"] is False
            assert Decimal(failed["cost_usd"]) == Decimal(failed["reservation_usd"])

        binding["cost_bound_usd"] = str(ledger.spent() + (Decimal("0.01") if changed == "cost" else 0))
        binding["journal_sha256"] = protocol.sha(tmp_path / "raw/events.jsonl")
        (tmp_path / "runtime.json").write_text(json.dumps({
            key: binding[key] for key in ("freeze", "plan_sha256")
        }))
        if changed == "request":
            rows = ledger.rows()
            rows[0]["request"]["max_tokens"] += 1
            monkeypatch.setattr(ledger, "rows", lambda: deepcopy(rows))
        before = (tmp_path / "raw/events.jsonl").read_bytes()
        calls = len(seen)
        if changed is None:
            audit = amendment.audit_prior(tmp_path, binding, ledger)
            assert audit["pass"]
            assert audit["calls"] == 12
            assert audit["unresolved"] == 1
            assert Decimal(audit["cost_bound_usd"]) == ledger.spent()
        else:
            with pytest.raises(Halted):
                amendment.audit_prior(tmp_path, binding, ledger)
        assert (tmp_path / "raw/events.jsonl").read_bytes() == before
        assert len(seen) == calls


@pytest.mark.parametrize("old_plan", [protocol.PLAN, a1.PLAN])
def test_build_rejects_changed_prior_plan_hash(monkeypatch, old_plan):
    real_sha = protocol.sha
    monkeypatch.setattr(protocol, "sha", lambda path: "0" * 64 if Path(path) == protocol.ROOT / old_plan else real_sha(path))
    with pytest.raises((Halted, ValueError)):
        amendment.build()


@pytest.mark.parametrize("freeze", ["", "a" * 39, "g" * 40])
def test_invalid_freeze_rejected_offline(tmp_path, freeze):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(amendment.build()))
    with pytest.raises(Halted):
        amendment.verify(path, freeze)


@pytest.mark.parametrize("changed", [None, "source", "plan", "ancestry"])
def test_verify_reconstructs_published_source_freeze_offline(tmp_path, monkeypatch, changed):
    plan = amendment.build()
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    freeze = "c" * 40
    source = next(iter(plan["source_hashes"]))
    checked = []

    def check_output(command, **kwargs):
        if command[:2] == ["git", "show"]:
            revision, name = command[2].split(":", 1)
            assert revision == freeze
            checked.append(name)
            if changed == "source" and name == source or changed == "plan" and name == amendment.PLAN:
                return b"synthetic tamper"
            return path.read_bytes() if name == amendment.PLAN else (protocol.ROOT / name).read_bytes()
        assert command == ["git", "ls-remote", "origin", "refs/heads/codex/openrouter-swap-panel"]
        return freeze + "\trefs/heads/codex/openrouter-swap-panel\n"

    def run(command, **kwargs):
        assert command == ["git", "merge-base", "--is-ancestor", freeze, freeze]
        return SimpleNamespace(returncode=int(changed == "ancestry"))

    monkeypatch.setattr(amendment.subprocess, "check_output", check_output)
    monkeypatch.setattr(amendment.subprocess, "run", run)
    if changed is None:
        assert amendment.verify(path, freeze) == plan
        assert set(checked) == set(plan["source_hashes"]) | {amendment.PLAN}
    else:
        with pytest.raises(Halted):
            amendment.verify(path, freeze)
