from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments import repeat_funding_a1 as a
from experiments.openrouter_swap.ledger import BudgetExceeded, Halted
from experiments.repeated_swap.runner import Runner, StudyLedger
from tests.test_repeated_swap_release import case, _collect


def test_actual_science_closure_unchanged_and_cost_arithmetic():
    plan = a.original_plan()
    assert len(plan["source_hashes"]) == 41
    assert "experiments/repeat_funding_a1.py" not in plan["source_hashes"]
    assert "tests/test_repeat_funding_a1.py" not in a.science.source_paths()
    old = {"remaining_forecast_with_30pct_reserve_usd": {"gemini": "49.69362839999999999999999999",
                                                        "opus": "84.17566170000000000000000000"},
           "observed_spend_usd": "7.23903055", "credit_snapshot_usd": "160.783095403",
           "journal_prefix": a.PREFIX, "models": ["gemini", "opus"]}
    result = a.amended_admission(old)
    assert result["pass"]
    assert Decimal(result["remaining_forecast_usd"]) == Decimal("113.2740147")
    assert Decimal(result["observed_spend_usd"]) + Decimal(result["remaining_forecast_usd"]) == Decimal("120.51304525")
    assert result["reserve_multiplier"] == "1.10" and result["external_holdback_usd"] == "45"


@pytest.fixture
def prepared(case, monkeypatch):
    root, scientific, runtime, _ = case
    _collect(case, initial=True)
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(scientific, runtime["freeze"], runtime["plan_sha256"], ledger)
        old = runner.admission("1000")
        point = sum(Decimal(v) for v in old["remaining_forecast_with_30pct_reserve_usd"].values()) / Decimal("1.30")
        old = runner.admission(str(Decimal("45") + point * Decimal("1.20")))
        raw = (root / "raw/events.jsonl").read_bytes()
        old["journal_prefix"] = {"bytes": len(raw), "sha256": a.digest(raw), "calls": len(ledger.rows())}
    assert old["pass"] is False
    failed = (json.dumps(old, indent=2) + "\n").encode()
    (root / "admission.json").write_bytes(failed)
    monkeypatch.setattr(a, "OLD_FREEZE", runtime["freeze"])
    monkeypatch.setattr(a, "OLD_PLAN_SHA", runtime["plan_sha256"])
    monkeypatch.setattr(a, "FAILED_SHA", a.digest(failed))
    monkeypatch.setattr(a, "PREFIX", old["journal_prefix"])
    monkeypatch.setattr(a, "ROOT", a.science.ROOT)
    monkeypatch.setattr(a, "original_plan", lambda: scientific)
    monkeypatch.setattr(a.production, "root_path", lambda: root)
    for name in a.NEW_SOURCES:
        path = a.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic bound wrapper input\n")
    path = a.ROOT / a.ANCHOR
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(failed)
    plan = a.build_plan()
    a.write_once(a.ROOT / a.PLAN, plan)
    return root, scientific, runtime, plan


def test_reconstructs_failed_prefix_without_rewriting_runtime_or_journal(prepared):
    root, scientific, _, plan = prepared
    before = {name: (root / name).read_bytes() for name in ("runtime.json", "admission.json", "raw/events.jsonl")}
    assert a.verify_prefix(root, scientific, initial_only=True) == plan["admission"]
    assert before == {name: (root / name).read_bytes() for name in before}
    assert plan["atomic_cap_usd"] == "130" and plan["external_holdback_usd"] == "45"
    assert set(plan["source_hashes"]) == set(scientific["source_hashes"]) | set(a.NEW_SOURCES) | {a.ANCHOR}


@pytest.mark.parametrize("name", ["runtime.json", "admission.json", "raw/events.jsonl"])
def test_prefix_identity_tamper_rejected(prepared, name):
    root, scientific, _, _ = prepared
    path = root / name
    before = path.read_bytes()
    changed = before.replace(b"false", b"true", 1) if name == "admission.json" else before.replace(b"130", b"131", 1)
    assert changed != before
    path.write_bytes(changed)
    with pytest.raises(Halted):
        a.verify_prefix(root, scientific)


def test_initial_bulk_cannot_precede_operational_binding(prepared):
    root, scientific, _, _ = prepared
    with (root / "raw/events.jsonl").open("ab") as stream:
        stream.write(b"unfrozen extra bytes\n")
    with pytest.raises(Halted, match="unfrozen bulk"):
        a.verify_prefix(root, scientific, initial_only=True)


def test_source_and_amendment_tamper_rejected(prepared):
    path = a.ROOT / a.PLAN
    assert a.verify(path)["change"]["new_multiplier"] == "1.10"
    (a.ROOT / a.NEW_SOURCES[0]).write_text("changed\n")
    with pytest.raises(Halted, match="closure changed"):
        a.verify(path)


def test_operational_and_public_freezes_are_separate(prepared, monkeypatch):
    _, _, _, plan = prepared
    freeze = "b" * 40
    monkeypatch.setattr(a, "git_blob", lambda revision, name: (a.ROOT / name).read_bytes())
    def command(args, **kwargs):
        if args[1] == "rev-parse":
            return freeze + "\n"
        if args[1] == "ls-remote":
            return freeze + "\trefs/heads/" + a.science.BRANCH + "\n"
        raise AssertionError(args)
    monkeypatch.setattr(a.subprocess, "check_output", command)
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert a.verify(a.ROOT / a.PLAN, freeze, require_pushed=True) == plan
    with pytest.raises(Halted, match="fresh operational freeze"):
        a.verify(a.ROOT / a.PLAN, a.OLD_FREEZE)
    monkeypatch.setattr(a.subprocess, "check_output", lambda args, **kwargs:
                        freeze + "\n" if args[1] == "rev-parse" else "")
    with pytest.raises(Halted, match="pushed"):
        a.verify(a.ROOT / a.PLAN, freeze, require_pushed=True)


def test_uncommitted_operational_source_is_rejected(prepared, monkeypatch):
    monkeypatch.setattr(a, "git_blob", lambda *args: b"wrong git blob")
    with pytest.raises(Halted, match="absent from operational freeze"):
        a.verify(a.ROOT / a.PLAN, "b" * 40)


@pytest.mark.parametrize("balance", [True, "NaN", "Infinity", "-1", "45", "44.99"])
def test_bad_or_empty_live_funding_stops_reservations(tmp_path, balance):
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        with pytest.raises(Halted):
            ledger.enable_funding(lambda: balance, lambda value: None)
        assert ledger.rows() == []


def test_balance_refresh_is_atomic_and_does_not_double_count_pending(tmp_path):
    clock = [0]
    balance = ["50"]
    records = []
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.enable_funding(lambda: balance[0], records.append, clock=lambda: clock[0])
        ledger.reserve("a", {"model": "synthetic"}, "4", "main", {})
        assert a.funding_limit(ledger, "50") == Decimal("5")
        clock[0] = 61
        with pytest.raises(BudgetExceeded):
            ledger.reserve("b", {"model": "synthetic"}, "2", "main", {})
        assert len(records) == 2 and len(ledger.rows()) == 1
        assert ledger.stage_limit == Decimal("5")


def test_account_read_failure_and_missing_guard_never_dispatch(tmp_path):
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        with pytest.raises(Halted, match="not enabled"):
            ledger.reserve("a", {}, "1", "main", {})
        with pytest.raises(TimeoutError):
            ledger.enable_funding(Mock(side_effect=TimeoutError()), lambda value: None)
        assert not ledger.rows()


def test_cap_is_unchanged_even_with_large_balance_and_concurrent_reservations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.enable_funding(lambda: "10000", lambda value: None)
        def reserve(index):
            try:
                ledger.reserve(str(index), {}, "10", "main", {})
                return True
            except BudgetExceeded:
                return False
        with ThreadPoolExecutor(max_workers=16) as pool:
            assert sum(pool.map(reserve, range(20))) == 13
        assert ledger.spent() == Decimal("130")


def test_completed_spend_never_resets_and_fresh_balance_must_cover_completion(tmp_path):
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.enable_funding(lambda: "200", lambda value: None)
        ledger.reserve("a", {}, "10", "main", {})
        ledger.settle("a", {"usage": {"prompt_tokens": 1, "completion_tokens": 1}}, "7")
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.enable_funding(lambda: "50", lambda value: None)
        assert ledger.spent() == Decimal("7") and ledger.stage_limit == Decimal("12")
        admission = {"observed_spend_usd": "7", "remaining_forecast_usd": "6"}
        with pytest.raises(Halted, match="completion forecast"):
            a.require_completion_funding(ledger, admission, ledger.stage_limit)


def test_execution_keeps_science_metadata_and_records_actual_wrapper_freeze(prepared, monkeypatch):
    root, scientific, runtime, amendment = prepared
    before = {name: (root / name).read_bytes() for name in ("runtime.json", "admission.json", "raw/events.jsonl")}
    monkeypatch.setattr(a, "verify", lambda path, freeze, require_pushed: amendment)
    monkeypatch.setattr(a.production, "account_balance", lambda key: "1000")
    monkeypatch.setattr(a, "live_sender", lambda key: Mock(side_effect=AssertionError("No network")))
    actual = []
    class StubRunner:
        def __init__(self, plan, freeze, plan_hash, ledger, sender=None):
            actual.append((plan, freeze, plan_hash))
            self.ledger = ledger
        def require_resolved(self): pass
        def audit(self): return {"pass": True}
        def run_blocks(self, phase):
            assert list((root / "funding_a1/launches").glob("*/start.json"))
            assert phase == "main"
        def require_complete(self): pass
    # Prefix reconstruction still uses the real frozen Runner.
    monkeypatch.setattr(a, "verify_prefix", lambda *args, **kwargs: amendment["admission"])
    monkeypatch.setattr(a, "Runner", StubRunner)
    assert a.execute(root, amendment, "b" * 40, "synthetic") == {"pass": True}
    assert actual == [(scientific, runtime["freeze"], runtime["plan_sha256"])]
    assert before == {name: (root / name).read_bytes() for name in before}
    binding = json.loads((root / "funding_a1/runtime.json").read_text())
    assert binding["actual_operational_freeze"] == "b" * 40
    assert binding["original_science_freeze"] == runtime["freeze"]
    finish = json.loads(next((root / "funding_a1/launches").glob("*/finish.json")).read_text())
    assert finish["complete"] and finish["journal_after"]["sha256"] == a.digest(before["raw/events.jsonl"])


def test_offline_build_does_not_call_balance_or_sender(prepared, monkeypatch, capsys):
    monkeypatch.setattr(a.production, "account_balance", Mock(side_effect=AssertionError("No balance API")))
    monkeypatch.setattr(a, "live_sender", Mock(side_effect=AssertionError("No inference")))
    a.main(["--build"])
    assert json.loads(capsys.readouterr().out)["network_calls"] == 0


def test_funding_drop_and_refresh_failure_block_new_calls(tmp_path):
    clock, balance = [0], ["100"]
    def read():
        if balance[0] is None:
            raise TimeoutError("Synthetic balance failure")
        return balance[0]
    with a.FundingLedger(tmp_path, cap="130", screen_cap="15") as ledger:
        ledger.enable_funding(read, lambda value: None, clock=lambda: clock[0])
        ledger.reserve("a", {}, "4", "main", {})
        clock[0], balance[0] = 61, "48"
        with pytest.raises(BudgetExceeded):
            ledger.reserve("b", {}, "1", "main", {})
        assert ledger.stage_limit == Decimal("3")
        clock[0], balance[0] = 122, None
        with pytest.raises(TimeoutError):
            ledger.reserve("c", {}, "1", "main", {})
        assert len(ledger.rows()) == 1
