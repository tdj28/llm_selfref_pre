"""Synthetic CPU-only concurrency/replay tests; never contact an endpoint."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import threading
import time
from unittest.mock import Mock

import pytest

from experiments import kolibri_generation_waves as w
from experiments.kolibri_swap import production as prod, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_bootstrap_a5 import bridge as a5_setup, opened as a5_opened
from tests.test_kolibri_swap_production import FREEZE, write, tree_hashes
from tests.test_kolibri_swap_runtime import senders, receipt, local_raw

OP_FREEZE = "b" * 40


@pytest.fixture
def setup(a5_setup):
    plan, root, amendment, policy = a5_setup
    local, judge, _, _ = senders()
    with a5_opened(a5_setup, local, judge) as runner:
        runner.guard = Mock()
        assert prod.phase(runner, "fixtures", root)["pass"]
        assert prod.phase(runner, "generate-screen-initial", root)["generation_calls"] == 12
        assert prod.phase(runner, "judge-screen-initial", root)["pass"]
    source = protocol.ROOT / "synthetic-waves.py"
    source.write_text("# Synthetic operational test binding, not a research record\n")
    for name in w.judge_waves.SOURCES:
        target = protocol.ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((Path(w.__file__).resolve().parents[1] / name).read_bytes())
    value = {"worker_freeze": FREEZE, "source_hashes": {source.name: protocol.sha(source),
                 **{name: protocol.sha(protocol.ROOT / name) for name in w.judge_waves.SOURCES}},
             "judge_waves": deepcopy(w.judge_waves.POLICY),
             "initial_audit": runner.receipts.decision("screen_initial"),
             "prefix": w.prefix(root / "collection"), "forecast": {"source_waves": 64, "final_waves": 64,
                 "margin": "1.30", "cleanup_seconds": "600"}}
    write(protocol.ROOT / w.PLAN, value)
    return a5_setup, value


@contextmanager
def opened(setup, local=None, judge=None):
    (plan, root, amendment, policy), value = setup
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", FREEZE, digest) as receipts:
        if receipts.decision("generation_waves") is None:
            receipts.append("decision", {"name": "generation_waves", "value": w.binding(OP_FREEZE, value)})
        runner = w.Runner(plan, FREEZE, digest, ledger, receipts, local, judge,
            amendment=amendment, transport_plan=policy, wave_plan=value, wave_freeze=OP_FREEZE, sleep=Mock())
        runner.guard = Mock()
        yield runner


def test_exact_fixed_within_block_schedule():
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    screen, main = w.schedule(plan, "screen"), w.schedule(plan, "main")
    assert len(screen) == 20 and len(main) == 128
    assert all(len(wave["item_ids"]) == w.WIDTHS[wave["role"]] for wave in screen + main)
    assert [x["block"] for x in screen[::2]] == [b["block"] for b in plan["screen"] if b["block"] > 2]
    assert [x["block"] for x in main[::4]] == [b["block"] for b in plan["main"]]
    assert [x["role"] for x in main[:4]] == ["source", "source", "final", "final"]


def test_real_overlap_one_journal_owner_exact_requests_and_replay(setup):
    active, maximum, seen, lock = 0, 0, [], threading.Lock()
    owner = threading.get_ident()
    def sender(request):
        nonlocal active, maximum
        with lock:
            active += 1; maximum = max(maximum, active); seen.append(deepcopy(request))
        time.sleep(.035)
        with lock: active -= 1
        return receipt(local_raw(request), elapsed=.03)
    with opened(setup, sender) as runner:
        finish = runner.receipts.finish
        def owned_finish(*args):
            assert threading.get_ident() == owner
            return finish(*args)
        runner.receipts.finish = owned_finish
        waves = w.schedule(runner.plan, "screen")[:2]
        for wave in waves: assert runner.run_wave(wave)["pass"]
        assert maximum == 4 and len(seen) == 6
        assert runner.audit()["completed_waves"] == 2
        before = tree_hashes(runner.receipts.root)
        for wave in waves: runner.run_wave(wave)
        assert len(seen) == 6 and before == tree_hashes(runner.receipts.root)
        for request in seen:
            assert request["max_tokens"] == 4096 and request["temperature"] == .5
            assert request["reasoning_effort"] == "medium" and "provider" not in request
            assert "Synthetic reasoning never transplanted" not in json.dumps(request)
        assert runner.guard.before_call.call_count == 6


@pytest.mark.parametrize("mode", ["timeout", "parse", "identity", "exception", "external_stop"])
def test_failure_drains_wave_and_never_resends_or_opens_next(setup, mode):
    ready = threading.Barrier(2)
    holder, seen = {}, []
    def sender(request):
        seen.append(request)
        ready.wait(timeout=2)
        if request["seed"] == holder["seed"]:
            if mode == "timeout": return runtime.HTTPReceipt(None, b"partial original bytes", .02, "TotalDeadlineExceeded")
            if mode == "parse": return runtime.HTTPReceipt(200, b"malformed original bytes", .02)
            if mode == "exception": raise RuntimeError("Synthetic transport failure")
            if mode == "external_stop": holder["runner"].stop.set()
            if mode == "identity":
                raw = local_raw(request); raw["model"] = "synthetic-wrong-model"
                return receipt(raw, elapsed=.02)
        time.sleep(.025)
        return receipt(local_raw(request), elapsed=.02)
    with opened(setup, sender) as runner:
        first, second = w.schedule(runner.plan, "screen")[:2]
        holder.update(runner=runner, seed=runner.catalog[first["item_ids"][0]]["seed"])
        with pytest.raises(Halted): runner.run_wave(first)
        assert len(seen) == 2 and runner.stop.is_set()
        records = runner.receipts.records()
        assert all(records["gen:" + item]["status"] != "pending" for item in first["item_ids"])
        assert runner.audit()["failed_waves"] == 1
        with pytest.raises(Halted): runner.run_wave(second)
        with pytest.raises(Halted): runner.run_wave(first)
        assert len(seen) == 2


def test_external_stop_before_wave_keeps_prefix_and_sends_nothing(setup):
    sender = Mock(_kolibri_live=False)
    with opened(setup, sender) as runner:
        before = tree_hashes(runner.receipts.root)
        runner.stop.set()
        with pytest.raises(Halted): runner.run_wave(w.schedule(runner.plan, "screen")[0])
        assert before == tree_hashes(runner.receipts.root)
        sender.assert_not_called()


def test_guard_rejection_before_wave_admission_has_no_partial_dispatch(setup):
    sender = Mock(_kolibri_live=False)
    with opened(setup, sender) as runner:
        runner.guard.before_call.side_effect = [None, Halted("Synthetic cumulative cap")]
        before = tree_hashes(runner.receipts.root)
        with pytest.raises(Halted): runner.run_wave(w.schedule(runner.plan, "screen")[0])
        assert before == tree_hashes(runner.receipts.root)
        sender.assert_not_called()


def test_out_of_order_wave_rejected_before_guard_or_dispatch(setup):
    sender = Mock(_kolibri_live=False)
    with opened(setup, sender) as runner:
        before = tree_hashes(runner.receipts.root)
        with pytest.raises(Halted): runner.run_wave(w.schedule(runner.plan, "screen")[1])
        assert before == tree_hashes(runner.receipts.root)
        sender.assert_not_called()
        runner.guard.before_call.assert_not_called()


def test_missing_source_stays_missing_no_reasoning_transplant_or_generation_retry(setup):
    count = 0
    def sender(request):
        nonlocal count
        count += 1
        raw = local_raw(request)
        if count == 1:
            raw["choices"][0]["message"]["content"] = None
            raw["choices"][0]["finish_reason"] = "length"
        return receipt(raw, elapsed=0)
    with opened(setup, sender) as runner:
        waves = w.schedule(runner.plan, "screen")[:2]
        for wave in waves: runner.run_wave(wave)
        final = runner.receipts.decision(waves[1]["id"] + ":open")
        assert len(final["call_ids"]) == 2 and len(final["skipped_missing_donor"]) == 2
        source = runner.receipts.existing("gen:" + waves[0]["item_ids"][0])
        assert source["projection"]["cap_hit"] and source["projection"]["missing"]
        assert count == 4 and runner.audit()["completed_waves"] == 2


def test_complete_screen_and_forecast_replay_preserve_original_judges(setup):
    local, judge, _, judged = senders()
    with opened(setup, local, judge) as runner:
        assert runner.generate_blocks("screen")["generation_calls"] == 72
        runner.judge_blocks("screen"); runner.complete("screen")
        assert len(judged) == 160
        evidence = dict(gpu_spent_usd="3", gpu_hourly_rate_usd="4.59", gpu_remaining_seconds="10000",
                        storage_bound_usd="5", remaining_overhead_seconds="600")
        admission = runner.main_admission(**evidence)
        means = admission["wave_timing_means"]
        expected = Decimal("1.30") * 64 * (Decimal(means["source"]) + Decimal(means["final"])) + 600
        assert Decimal(admission["main_seconds_with_margin"]) == expected
        assert admission["qualified"] and admission["fits"]
        runner.approve_main(admission)
        assert runner.receipts.decision("main_admission") == runner.main_admission(**evidence)
        assert not runner.main_admission(**{**evidence, "gpu_remaining_seconds": "1"})["fits"]
        assert not runner.main_admission(**{**evidence, "storage_bound_usd": "6"})["fits"]
        with pytest.raises(Halted): runner.main_admission(**{**evidence, "remaining_overhead_seconds": "0"})


@pytest.mark.parametrize("mutation", ["elapsed", "order", "hash", "inventory", "extra", "prefix"])
def test_rehashed_wave_tampering_fails_closed(setup, mutation):
    local, _, _, _ = senders()
    with opened(setup, local) as runner:
        wave = w.schedule(runner.plan, "screen")[0]
        runner.run_wave(wave)
        if mutation == "prefix":
            path = runner.receipts.root.parent / next(iter(runner.wave_plan["prefix"]["raw"]))
            path.write_bytes(path.read_bytes() + b" ")
            with pytest.raises(Halted): runner.audit()
            return
        events = deepcopy(runner.receipts.events)
        opened_event = next(e for e in events if e["kind"] == "decision" and e["data"]["name"] == wave["id"] + ":open")
        closed_event = next(e for e in events if e["kind"] == "decision" and e["data"]["name"] == wave["id"] + ":closed")
        if mutation == "elapsed": closed_event["data"]["value"]["elapsed_seconds"] = "3000"
        elif mutation == "order": opened_event["seq"] = closed_event["seq"] + 1
        elif mutation == "hash": closed_event["data"]["value"]["responses_sha256"] = "0" * 64
        elif mutation == "inventory": opened_event["data"]["value"]["call_ids"].pop()
        else: closed_event["data"]["name"] = "wave:unplanned:closed"
        original = runner.receipts.events
        runner.receipts.events = events
        try:
            with pytest.raises(Halted): runner.wave_audit()
        finally:
            runner.receipts.events = original


def test_incomplete_open_wave_is_retained_not_retried(setup):
    with opened(setup, Mock(_kolibri_live=False)) as runner:
        wave = w.schedule(runner.plan, "screen")[0]
        runner.receipts.append("decision", {"name": wave["id"] + ":open", "value": {
            **wave, "call_ids": ["gen:" + item for item in wave["item_ids"]], "skipped_missing_donor": [],
            "started_utc": datetime.now(timezone.utc).isoformat()}})
        assert runner.wave_audit() == []
        with pytest.raises(Halted): runner.run_wave(wave)
        runner.local_sender.assert_not_called()


def test_wave_timer_includes_preflight_guards_and_receipt_audit(setup):
    local, _, _, _ = senders()
    with opened(setup, local) as runner:
        runner.guard.before_call.side_effect = lambda *args: time.sleep(.02)
        result = runner.run_wave(w.schedule(runner.plan, "screen")[0])
        assert Decimal(result["elapsed_seconds"]) >= Decimal(".04")
        assert runner.audit()["completed_waves"] == 1


def test_new_files_outside_existing_frozen_closures():
    old = prod.load(protocol.ROOT / w.a5.AMENDMENT)
    hashes = {**old["source_hashes"], **old["dependency_source_hashes"]}
    assert not set(w.SOURCES) & set(hashes)
    assert all(protocol.sha(protocol.ROOT / n) == d for n, d in hashes.items())
