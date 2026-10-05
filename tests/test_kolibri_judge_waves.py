"""Offline synthetic receipts; no hosted calls, environment keys or pods."""
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import threading
from unittest.mock import Mock

import pytest

from experiments import kolibri_judge_transport as transport, kolibri_judge_waves as waves
from experiments.kolibri_swap import protocol, runtime as r
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Halted, read_events
from experiments.openrouter_swap.providers import reservation
from tests.test_kolibri_judge_transport import (
    setup as original_setup, opened as original_opened, TIMEOUT, filtered, rehash,
)
from tests.test_kolibri_swap_runtime import senders, receipt
from tests.test_kolibri_swap_production import tree_hashes


class Runner(waves.JudgeWavesMixin, transport.Runner):
    pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    value = original_setup.__wrapped__(tmp_path, monkeypatch)
    source_root = Path(__file__).resolve().parents[1]
    for name in waves.SOURCES:
        target = protocol.ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / name).read_bytes())
    return value


@contextmanager
def opened(setup, judge=None, screen_cap="10"):
    with original_opened(setup, judge=judge, screen_cap=screen_cap) as runner:
        runner.__class__ = Runner
        runner.wave_plan = {"worker_freeze": runner.freeze, "judge_waves": deepcopy(waves.POLICY),
                            "source_hashes": {n: protocol.sha(protocol.ROOT / n) for n in waves.SOURCES}}
        runner.wave_freeze = "e" * 40
        if runner.receipts.decision("generation_waves") is None:
            runner.receipts.append("decision", {"name": "generation_waves", "value": {
                "operational_freeze": runner.wave_freeze, "worker_freeze": runner.freeze,
                "amendment_sha256": protocol.digest(runner.wave_plan)}})
        yield runner


def jobs(runner, count=8):
    return [(item["id"], item["response"], judge, instrument, "fixtures")
            for item in runner.plan["fixtures"] for judge in runner.plan["judges"]
            for instrument in judges.INSTRUMENTS][:count]


def request_for(runner, job):
    req = judges.judge_request(runner.plan["judges"][job[2]], job[3], job[1])
    req["provider"].update(r.PRIVACY)
    return req


def test_eight_physical_senders_one_journal_owner_and_unchanged_requests(setup, monkeypatch):
    _, good, _, seen = senders()
    barrier = threading.Barrier(8)
    workers = set()
    mutex = threading.Lock()
    def sender(request):
        with mutex:
            workers.add(threading.get_ident())
        barrier.wait(10)
        return good(request)
    with opened(setup, sender) as runner:
        owner = threading.get_ident()
        for obj, method in ((runner.receipts, "append"), (runner.receipts, "finish"),
                            (runner.ledger, "reserve"), (runner.ledger, "settle")):
            original = getattr(obj, method)
            def checked(*args, original=original, **kwargs):
                assert threading.get_ident() == owner
                return original(*args, **kwargs)
            monkeypatch.setattr(obj, method, checked)
        selected = jobs(runner)
        expected = [request_for(runner, job) for job in selected]
        assert len(runner._run_judge_wave(selected)) == 8
        assert len(workers) == 8 and owner not in workers
        assert sorted(map(protocol.canonical, seen)) == sorted(map(protocol.canonical, expected))
        report = runner.audit()
        assert report["pass"] and report["judge_waves"]["peak_physical_pending"] == 8
        assert report["judge_waves"]["pending"] == 0
        assert runner.guard.before_call.call_count == 8
        assert read_events(runner.receipts.root / "events.jsonl") == runner.receipts.events
        assert len(read_events(runner.ledger.root / "events.jsonl")) == 17


def test_out_of_order_completion_and_read_only_terminal_replay(setup, monkeypatch):
    _, good, _, seen = senders()
    second_settled = threading.Event()
    with opened(setup) as runner:
        selected = jobs(runner, 2)
        first = request_for(runner, selected[0])
        def sender(request):
            if request == first:
                assert second_settled.wait(10)
            return good(request)
        runner.sender = sender
        original = runner.receipts.finish
        def finish(call, *args, **kwargs):
            value = original(call, *args, **kwargs)
            if ":structured:" in call:
                second_settled.set()
            return value
        monkeypatch.setattr(runner.receipts, "finish", finish)
        runner._run_judge_wave(selected)
        replies = [e["data"]["call_id"] for e in runner.receipts.events if e["kind"] == "response"]
        assert ":structured:" in replies[0] and ":paper:" in replies[1]
        before = tree_hashes(setup[1])
        assert len(runner._run_judge_wave(selected)) == 2
        assert len(seen) == 2 and tree_hashes(setup[1]) == before
        assert runner.audit()["pass"]


@pytest.mark.parametrize("failures", [1, 2])
def test_independent_identical_transport_retries_and_original_backoffs(setup, failures):
    _, good, _, seen = senders()
    counts, lock = {}, threading.Lock()
    def sender(request):
        key = protocol.digest(request)
        with lock:
            counts[key] = counts.get(key, 0) + 1
            ordinal = counts[key]
        return TIMEOUT if ordinal <= failures else good(request)
    with opened(setup, sender) as runner:
        selected = jobs(runner, 2)
        assert len(runner._run_judge_wave(selected)) == 2
        assert sorted(counts.values()) == [failures + 1] * 2
        assert sorted(c.args[0] for c in runner.sleep.call_args_list) == sorted(list(transport.BACKOFF[:failures]) * 2)
        records = runner.receipts.records()
        for row in records.values():
            if row["status"] == "unresolved":
                bill = runner.ledger.existing(row["call_id"])
                assert bill["cost_usd"] == bill["reservation_usd"] and not bill["cost_known"]
                assert (runner.receipts.root / row["body"]["path"]).read_bytes() == TIMEOUT.body
            if transport.SUFFIX in row["call_id"]:
                assert row["metadata"]["transport_retry"]["operational_freeze"] == runner.operational_freeze
        for logical in [k for k in records if transport.SUFFIX not in k]:
            assert all(records[k]["request"] == records[logical]["request"] for k in records if k.startswith(logical))
        report = runner.audit()
        assert report["pass"] and report["physical_calls"] == 2 * (failures + 1)
        assert report["unresolved"] == 0 and report["physical_unresolved"] == 2 * failures


def test_known_refusal_stays_missing_raw_unresolved_full_reserve_no_retry(setup):
    _, good, _, _ = senders()
    seen = []
    def sender(request):
        seen.append(deepcopy(request))
        return receipt(filtered(request, good))
    with opened(setup, sender) as runner:
        value = runner._run_judge_wave(jobs(runner, 2))
        assert all(row["status"] == "incomplete_judge" for row in value)
        assert len(seen) == 2 and not runner.sleep.called
        assert all(row["status"] == "unresolved" for row in runner.receipts.records().values())
        assert all(b["cost_usd"] == b["reservation_usd"] for b in runner.ledger.rows())
        report = runner.audit()
        assert report["pass"] and len(report["terminal_refusal_calls"]) == 2
        assert report["blocking_unresolved"] == 0


def test_frozen_schema_repair_not_transport_retry_and_valid_not_rejudged(setup):
    _, good, _, _ = senders()
    seen = []
    def sender(request):
        seen.append(deepcopy(request))
        raw = r.strict_json(good(request).body)
        if len(seen) == 1:
            raw["choices"][0]["message"]["content"] = "synthetic invalid instrument output"
        return receipt(raw)
    with opened(setup, sender) as runner:
        result = runner._run_judge_wave(jobs(runner, 1))
        assert result[0]["status"] == "ok" and len(seen) == 2
        assert seen[0] == seen[1]
        ids = list(runner.receipts.records())
        assert ids[0].endswith(":a0") and ids[1].endswith(":a1")
        assert all(transport.SUFFIX not in x for x in ids) and not runner.sleep.called
        before = tree_hashes(setup[1])
        runner._run_judge_wave(jobs(runner, 1))
        assert len(seen) == 2 and tree_hashes(setup[1]) == before and runner.audit()["pass"]


def test_exhaustion_halts_drains_other_judges_and_never_resets_retry_budget(setup):
    _, good, _, _ = senders()
    with opened(setup) as runner:
        selected = jobs(runner, 2)
        failed_request = request_for(runner, selected[0])
        seen = []
        def sender(request):
            seen.append(deepcopy(request))
            return TIMEOUT if request == failed_request else good(request)
        runner.sender = sender
        with pytest.raises(Halted):
            runner._run_judge_wave(selected)
        assert len([q for q in seen if q == failed_request]) == 3
        assert runner.stop.is_set()
        assert not any(x["status"] == "pending" for x in runner.receipts.records().values())
        before = tree_hashes(setup[1])
        with pytest.raises(Halted):
            runner._run_judge_wave(selected)
        assert tree_hashes(setup[1]) == before
        assert runner.audit()["physical_unresolved"] == 3


@pytest.mark.parametrize("mode", ["model", "overrun", "unsafe", "401"])
def test_nontransport_failure_drains_all_eight_without_retry(setup, mode):
    _, good, _, _ = senders()
    barrier = threading.Barrier(8)
    with opened(setup) as runner:
        selected = jobs(runner)
        fail_request = request_for(runner, selected[0])
        seen = []
        def sender(request):
            seen.append(deepcopy(request))
            barrier.wait(10)
            raw = r.strict_json(good(request).body)
            if request == fail_request:
                if mode == "model": raw["model"] = "synthetic-wrong-model"
                if mode == "overrun": raw["usage"]["cost"] = 46
                if mode == "unsafe": return r.HTTPReceipt(200, b"", 1., "UnsafeReceipt")
                if mode == "401": return receipt({"error": "synthetic unauthorized"}, 401)
            return receipt(raw)
        runner.sender = sender
        with pytest.raises(Halted):
            runner._run_judge_wave(selected)
        assert len(seen) == 8 and not runner.sleep.called
        assert not any(row["status"] == "pending" for row in runner.receipts.records().values())
        assert len(runner.ledger.rows()) == 8


def test_atomic_pending_reservations_enforce_shared_screen_cap(setup):
    _, good, _, _ = senders()
    with opened(setup) as runner:
        selected = jobs(runner, 2)
        amounts = [reservation(runner.plan["judges"][j[2]], request_for(runner, j)) for j in selected]
        cap = str(min(amounts) / 2)
    # Fresh root so the bound cap is never changed in an existing journal.
    fresh = (setup[0], setup[1] / "budget", setup[2], setup[3])
    sender = Mock(side_effect=good)
    with opened(fresh, sender, screen_cap=cap) as runner:
        with pytest.raises(Halted):
            runner._run_judge_wave(jobs(runner, 2))
        assert sender.call_count == 0 and not runner.ledger.rows()


def test_pending_first_call_blocks_second_over_cap_and_drains_first(setup, monkeypatch):
    _, good, _, _ = senders()
    with opened(setup) as runner:
        selected = jobs(runner, 2)
        amounts = [reservation(runner.plan["judges"][j[2]], request_for(runner, j)) for j in selected]
    fresh = (setup[0], setup[1] / "concurrent-budget", setup[2], setup[3])
    first_started, release = threading.Event(), threading.Event()
    cap = str(max(amounts) + min(amounts) / 2)
    def sender(request):
        first_started.set()
        assert release.wait(10)
        return good(request)
    with opened(fresh, sender, screen_cap=cap) as runner:
        original = runner.ledger.reserve
        def reserve(*args, **kwargs):
            if runner.ledger.rows():
                assert first_started.wait(10)
            try:
                return original(*args, **kwargs)
            except Exception:
                release.set()
                raise
        monkeypatch.setattr(runner.ledger, "reserve", reserve)
        with pytest.raises(Halted):
            runner._run_judge_wave(jobs(runner, 2))
        assert len(runner.ledger.rows()) == 1
        assert len(runner.receipts.records()) == 1
        assert runner.ledger.rows()[0]["status"] == "settled"
        assert not any(row["status"] == "pending" for row in runner.receipts.records().values())


@pytest.mark.parametrize("field", ["item", "response", "judge", "instrument", "phase"])
def test_unplanned_logical_work_rejected_before_dispatch(setup, field):
    sender = Mock()
    with opened(setup, sender) as runner:
        job = list(jobs(runner, 1)[0])
        job[["item", "response", "judge", "instrument", "phase"].index(field)] = "synthetic-unplanned"
        with pytest.raises(Halted): runner._run_judge_wave([tuple(job)])
        assert not sender.called and not runner.ledger.rows()


def test_mutated_privacy_request_rejected_before_reservation(setup, monkeypatch):
    sender = Mock()
    with opened(setup, sender) as runner:
        original = runner._exchange
        def exchange(call_id, request, *args):
            request = deepcopy(request)
            request["provider"]["allow_fallbacks"] = True
            return original(call_id, request, *args)
        monkeypatch.setattr(runner, "_exchange", exchange)
        with pytest.raises(Halted): runner._run_judge_wave(jobs(runner, 1))
        assert not sender.called and not runner.ledger.rows()


def test_fake_clock_horizon_checked_after_backoff_before_retry(setup):
    now = [0]
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        def guard(*args):
            if now[0] + 600 > 601:
                raise Halted("synthetic absolute deadline")
        runner.guard.before_call.side_effect = guard
        runner.sleep.side_effect = lambda seconds: now.__setitem__(0, now[0] + seconds)
        with pytest.raises(Halted):
            runner._run_judge_wave(jobs(runner, 1))
        assert now[0] == 2 and sender.call_count == 1
        assert runner.guard.before_call.call_count == 2
        bill = runner.ledger.rows()[0]
        assert bill["cost_usd"] == bill["reservation_usd"]


def test_external_stop_during_transport_never_cleared(setup):
    with opened(setup) as runner:
        def sender(request):
            runner.stop.set()
            return TIMEOUT
        runner.sender = Mock(side_effect=sender)
        with pytest.raises(Halted):
            runner._run_judge_wave(jobs(runner, 1))
        assert runner.sender.call_count == 1 and runner.stop.is_set()
        assert len(runner.ledger.rows()) == 1
        assert runner.receipts.records()[runner.ledger.rows()[0]["call_id"]]["status"] == "unresolved"


@pytest.mark.parametrize("change", ["policy", "source", "binding"])
def test_changed_amendment_or_source_blocks_before_dispatch(setup, change):
    sender = Mock()
    with opened(setup, sender) as runner:
        if change == "policy": runner.wave_plan["judge_waves"]["logical_width"] = 9
        if change == "source": (protocol.ROOT / waves.SOURCES[0]).write_text("# synthetic tamper\n")
        if change == "binding": runner.wave_freeze = "f" * 40
        with pytest.raises(Halted):
            runner._run_judge_wave(jobs(runner, 1))
        assert sender.call_count == 0 and not runner.ledger.rows()


def test_inherited_pending_never_adopted_or_resent(setup):
    _, good, _, _ = senders()
    with opened(setup, good) as runner:
        job = jobs(runner, 1)[0]
        request = request_for(runner, job)
        identity = f"judge:{job[0]}:{job[2]}:{job[3]}:a0"
        meta = {"kind": "judge", "item_id": job[0], "judge": job[2], "instrument": job[3],
                "attempt": 0, "response_sha256": protocol.digest(job[1]),
                "freeze": runner.freeze, "plan_sha256": runner.plan_hash}
        runner.ledger.reserve(identity, request, reservation(runner.plan["judges"][job[2]], request), "fixtures", meta)
        runner.receipts.append("dispatch", {"call_id": identity, "request": request,
            "request_sha256": protocol.digest(request), "phase": "fixtures", "channel": "judge", "metadata": meta})
        runner.sender = Mock(side_effect=AssertionError("must not send"))
        before = tree_hashes(setup[1])
        with pytest.raises(Halted): runner._run_judge_wave([job])
        assert not runner.sender.called and tree_hashes(setup[1]) == before


def test_original_prefix_raw_and_costs_remain_byte_identical(setup):
    _, good, _, _ = senders()
    with opened(setup, good) as runner:
        selected = jobs(runner, 2)
        runner.judge(*selected[0])  # Frozen serial path before enabling waves.
        http_before = (runner.receipts.root / "events.jsonl").read_bytes()
        ledger_before = (runner.ledger.root / "events.jsonl").read_bytes()
        raw_before = {p.name: p.read_bytes() for p in (runner.receipts.root / "raw").glob("*.bin")}
        spent = runner.ledger.spent()
        runner._run_judge_wave(selected)
        assert (runner.receipts.root / "events.jsonl").read_bytes().startswith(http_before)
        assert (runner.ledger.root / "events.jsonl").read_bytes().startswith(ledger_before)
        assert all((runner.receipts.root / "raw" / n).read_bytes() == body for n, body in raw_before.items())
        assert runner.ledger.spent() > spent and len(runner.ledger.rows()) == 2
        assert runner.audit()["pass"]


def test_initial_barrier_cannot_be_replayed_as_parallel_initial_collection(setup):
    with opened(setup, Mock()) as runner:
        with pytest.raises(Halted): runner.judge_blocks("screen", initial=True)
        assert not runner.sender.called


def test_rehashed_request_tamper_still_fails_frozen_audit(setup):
    _, good, _, _ = senders()
    with opened(setup, good) as runner:
        runner._run_judge_wave(jobs(runner, 1))
        path = runner.receipts.root / "events.jsonl"
    events = read_events(path)
    event = next(e for e in events if e["kind"] == "dispatch")
    event["data"]["request"]["provider"]["allow_fallbacks"] = True
    event["data"]["request_sha256"] = protocol.digest(event["data"]["request"])
    rehash(path, events)
    with pytest.raises(Halted):
        with opened(setup, good) as runner:
            runner.audit()


@pytest.mark.parametrize("fail_at", [2, 4])
@pytest.mark.parametrize("after_enqueue", [False, True])
def test_logical_submission_failure_drains_waiting_workers_without_dispatch(
        setup, monkeypatch, fail_at, after_enqueue):
    original_executor, original_future = waves.ThreadPoolExecutor, waves.Future
    waiting, timed_out = threading.Event(), threading.Event()
    replies, pools = [], []

    class BoundedReply(original_future):
        def __init__(self):
            super().__init__()
            replies.append(self)

        def result(self, timeout=None):
            waiting.set()
            try:
                # A broken coordinator fails within five seconds rather than
                # deadlocking pytest itself inside executor shutdown.
                return super().result(timeout=5)
            except TimeoutError:
                timed_out.set()
                raise

    class FailingExecutor(original_executor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.attempts, self.submitted = 0, []

        def submit(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == fail_at:
                assert waiting.wait(5), "First logical worker never waited for its reply"
                if after_enqueue:
                    self.submitted.append(super().submit(*args, **kwargs))
                raise RuntimeError("Synthetic partial logical-executor startup failure")
            value = super().submit(*args, **kwargs)
            self.submitted.append(value)
            return value

    def executor(*args, **kwargs):
        pool = (FailingExecutor if pools else original_executor)(*args, **kwargs)
        pools.append(pool)
        return pool

    monkeypatch.setattr(waves, "Future", BoundedReply)
    monkeypatch.setattr(waves, "ThreadPoolExecutor", executor)
    sender = Mock(side_effect=AssertionError("No HTTP before successful logical admission"))
    with opened(setup, sender) as runner:
        before = tree_hashes(setup[1])
        with pytest.raises(Halted, match="after draining"):
            runner._run_judge_wave(jobs(runner))
        assert waiting.is_set() and not timed_out.is_set()
        assert pools[1].attempts == fail_at
        assert all(f.done() for f in pools[1].submitted)
        assert replies and all(f.done() for f in replies)
        assert runner.stop.is_set() and runner._judge_wave_context is None
        assert not sender.called and not runner.guard.before_call.called
        assert not runner.ledger.rows() and tree_hashes(setup[1]) == before
