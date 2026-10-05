"""Synthetic offline receipts only; no providers, credentials, SSH or GPUs."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json
import threading
from unittest.mock import Mock

import pytest

from experiments import kolibri_judge_transport as t
from experiments.kolibri_bootstrap_a2 import adapter
from experiments.kolibri_swap import protocol, runtime as r, production as prod
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Halted, Ledger, read_events
from experiments.openrouter_swap.providers import reservation
from tests.test_kolibri_swap_runtime import senders, receipt
from tests.test_kolibri_swap_production import write, tree_hashes

WORKER_FREEZE = "a" * 40  # Synthetic prospective A2 freeze.
OPERATIONAL = "d" * 40
TIMEOUT = r.HTTPReceipt(None, b"partial synthetic response\r\n", 600., "TotalDeadlineExceeded")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    original = protocol.ROOT
    plan = protocol.verify(original / protocol.PLAN)
    repo, root = tmp_path / "repo", tmp_path / "run"
    for name in (*t.SOURCES, protocol.PLAN):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes((original / name).read_bytes())
    (repo / "repair.py").write_text("# Synthetic A2 source binding\n")
    amendment = {"source_hashes": {"repair.py": protocol.sha(repo / "repair.py")},
                 "dependency_source_hashes": {},
                 "predecessor": {"cost_usd": "0.20653345641250872666666667"}}
    write(repo / adapter.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(adapter, "verify", lambda *args: deepcopy(amendment))
    transport = t.build_plan(WORKER_FREEZE)
    write(repo / t.PLAN, transport)
    return plan, root, amendment, transport


@contextmanager
def opened(setup, judge=None, local=None, screen_cap="10"):
    plan, root, amendment, transport = setup
    for sender in (judge, local):
        if isinstance(sender, Mock):
            sender._kolibri_live = False
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    with Ledger(root / "collection/judges", cap="45", screen_cap=screen_cap) as ledger, \
            r.ReceiptJournal(root / "collection/http", WORKER_FREEZE, digest) as receipts:
        runner = t.Runner(plan, WORKER_FREEZE, digest, ledger, receipts, local, judge,
                          amendment=amendment, transport_plan=transport,
                          operational_freeze=OPERATIONAL, sleep=Mock())
        runner.guard = Mock()
        yield runner


def judge_one(runner):
    item = runner.plan["fixtures"][0]
    return runner.judge(item["id"], item["response"], "astra", "paper", "fixtures")


def flaky(good, failures):
    requests = []
    def sender(request):
        requests.append(deepcopy(request))
        return failures[len(requests)-1] if len(requests) <= len(failures) else good(request)
    return sender, requests


def filtered(request, good):
    raw = r.strict_json(good(request).body)
    raw["service_tier"] = "auto"
    raw["usage"] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0}
    raw["choices"][0].update(finish_reason="content_filter", native_finish_reason="content_filter")
    raw["choices"][0]["message"]["content"] = "Synthetic provider refusal, not an instrument label."
    return raw


def rehash(path, events):
    for index, event in enumerate(events):
        event["seq"] = index + 1
        event["previous"] = events[index-1]["sha256"] if index else None
        event.pop("sha256", None)
        event["sha256"] = protocol.digest(event)
    path.write_text("".join(protocol.canonical(event)+"\n" for event in events))


@pytest.mark.parametrize("failures", [1, 2])
def test_identical_attempts_keep_bytes_holdbacks_and_a2_binding(setup, failures):
    _, good, _, _ = senders()
    sender, seen = flaky(good, [TIMEOUT] * failures)
    with opened(setup, sender) as runner:
        assert judge_one(runner)["status"] == "ok"
        assert len(seen) == failures + 1 and all(q == seen[0] for q in seen)
        assert runner.sleep.call_args_list == [((x,),) for x in t.BACKOFF[:failures]]
        assert runner.guard.before_call.call_count == failures + 1
        records, bills = runner.receipts.records(), runner.ledger.rows()
        assert [b["status"] for b in bills] == ["unresolved"] * failures + ["settled"]
        assert runner.ledger.spent() == sum((Decimal(b["cost_usd"]) for b in bills), Decimal(0))
        for call, row in records.items():
            assert row["metadata"]["freeze"] == WORKER_FREEZE
            if row["status"] == "unresolved":
                assert (runner.receipts.root / row["body"]["path"]).read_bytes() == TIMEOUT.body
                bill = runner.ledger.existing(call)
                assert not bill["cost_known"] and bill["cost_usd"] == bill["reservation_usd"]
        report = runner.audit()
        assert report["pass"] and report["calls"] == 1 and report["physical_calls"] == failures + 1
        assert report["unresolved"] == 0 and report["physical_unresolved"] == failures
        before = tree_hashes(setup[1])
        assert judge_one(runner)["status"] == "ok" and len(seen) == failures + 1
        assert before == tree_hashes(setup[1])
    with opened(setup, Mock(side_effect=AssertionError("must not resend"))) as runner:
        assert judge_one(runner)["status"] == "ok" and runner.audit()["physical_calls"] == failures + 1


@pytest.mark.parametrize("failed", [TIMEOUT,
    r.HTTPReceipt(None, b"", 2., "HTTPWorkerExited"),
    r.HTTPReceipt(None, b"", 2., "TransportException"),
    r.HTTPReceipt(200, b"{bad JSON\r\n", 2.),
    r.HTTPReceipt(200, b"\xff", 2.),
    receipt({"error": {"code": 429, "message": "synthetic throttle"}}, 429),
    receipt({"error": "synthetic unavailable"}, 503)])
def test_narrow_transport_failures_can_retry(setup, failed):
    _, good, _, _ = senders()
    sender, seen = flaky(good, [failed])
    with opened(setup, sender) as runner:
        assert judge_one(runner)["status"] == "ok" and len(seen) == 2
        assert runner.audit()["pass"]


@pytest.mark.parametrize("mode", ["valid", "cap", "refusal", "identity", "model", "missing_usage",
    "negative_usage", "overrun", "unsafe", "401", "403", "404", "error_refusal", "valid_json_wrong_schema"])
def test_nontransport_never_gets_transport_retry(setup, mode):
    _, good, _, _ = senders()
    seen = []
    def sender(request):
        seen.append(request)
        raw = r.strict_json(good(request).body)
        if mode == "cap":
            raw["choices"][0]["finish_reason"] = "length"
        elif mode == "refusal":
            raw["choices"][0]["message"]["content"] = ""
            raw["choices"][0]["finish_reason"] = "refusal"
        elif mode == "identity":
            raw["provider"] = "unexpected synthetic host"
        elif mode == "model":
            raw["model"] = "unexpected synthetic model"
        elif mode == "missing_usage":
            del raw["usage"]
        elif mode == "negative_usage":
            raw["usage"]["completion_tokens"] = -1
        elif mode == "overrun":
            raw["usage"]["cost"] = 46
        elif mode == "unsafe":
            return r.HTTPReceipt(200, b"", 1., "UnsafeReceipt")
        elif mode.isdigit():
            return receipt({"error": "synthetic failure"}, int(mode))
        elif mode == "error_refusal":
            return receipt({"error": {"code": "content_filter"}}, 503)
        elif mode == "valid_json_wrong_schema":
            return receipt({"unrecognized": "synthetic"})
        return receipt(raw)
    with opened(setup, sender) as runner:
        if mode in ("valid", "cap", "refusal"):
            judge_one(runner)
        else:
            with pytest.raises(Halted):
                judge_one(runner)
        assert len(seen) == 1
        assert not runner.sleep.called and len(runner.ledger.rows()) == 1
        assert runner.audit()["pass"]


def test_exhaustion_halts_without_fourth_attempt_or_reset_on_resume(setup):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        with pytest.raises(Halted, match="exhausted"):
            judge_one(runner)
        assert sender.call_count == 3 and runner.stop.is_set()
        assert runner.audit()["unresolved"] == 1
        before = tree_hashes(setup[1])
    with opened(setup, sender) as runner:
        with pytest.raises(Halted):
            judge_one(runner)
        assert sender.call_count == 3 and before == tree_hashes(setup[1])
        with pytest.raises(Halted):
            runner.require_resolved(channel="judge")


def test_budget_and_guard_checked_on_each_physical_attempt(setup):
    plan = setup[0]
    req = judges.judge_request(plan["judges"]["astra"], "paper", plan["fixtures"][0]["response"])
    req["provider"].update(r.PRIVACY)
    cap = str(reservation(plan["judges"]["astra"], req) * Decimal("1.5"))
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender, screen_cap=cap) as runner:
        with pytest.raises(Halted):
            judge_one(runner)
        assert sender.call_count == 1 and runner.guard.before_call.call_count == 2
        assert len(runner.ledger.rows()) == 1
        assert runner.ledger.spent() == Decimal(runner.ledger.rows()[0]["reservation_usd"])


@pytest.mark.parametrize("cause", ["guard", "external_stop"])
def test_guard_or_external_stop_during_backoff_prevents_dispatch(setup, cause):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        if cause == "guard":
            runner.guard.before_call.side_effect = [None, Halted("synthetic budget stop")]
        else:
            runner.sleep.side_effect = lambda seconds: runner.stop.set()
        with pytest.raises(Halted):
            judge_one(runner)
        assert sender.call_count == 1 and len(runner.ledger.rows()) == 1


@pytest.mark.parametrize("attempt", [1, 2])
@pytest.mark.parametrize("outcome", ["transport", "refusal"])
def test_external_stop_during_http_is_not_cleared_by_receipt_failure(setup, attempt, outcome):
    _, good, _, _ = senders()
    seen = []
    with opened(setup) as runner:
        def sender(request):
            seen.append(deepcopy(request))
            if len(seen) == attempt:
                runner.stop.set()
                return TIMEOUT if outcome == "transport" else receipt(filtered(request, good))
            return TIMEOUT if len(seen) < attempt else good(request)
        runner.sender = sender
        if outcome == "refusal":
            assert judge_one(runner)["status"] == "incomplete_judge"
        else:
            with pytest.raises(Halted):
                judge_one(runner)
        assert len(seen) == attempt and runner.stop.is_set()
        assert runner.sleep.call_count == attempt - 1
        assert runner.guard.before_call.call_count == attempt
        assert len(runner.ledger.rows()) == attempt
        assert all(row["cost_usd"] == row["reservation_usd"] for row in runner.ledger.rows())
        before = tree_hashes(setup[1])
        item = runner.plan["fixtures"][1]
        with pytest.raises(Halted):
            runner.judge(item["id"], item["response"], "astra", "paper", "fixtures")
        assert len(seen) == attempt and runner.stop.is_set() and before == tree_hashes(setup[1])
        assert runner.audit()["pass"]


def test_external_thread_stop_while_http_is_in_flight_remains_binding(setup):
    entered, release = threading.Event(), threading.Event()
    seen = []
    with opened(setup) as runner:
        def sender(request):
            seen.append(request)
            entered.set()
            assert release.wait(5)
            return TIMEOUT
        runner.sender = sender
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(judge_one, runner)
            try:
                assert entered.wait(5)
                runner.stop.set()
            finally:
                release.set()
            with pytest.raises(Halted):
                future.result(timeout=5)
        assert runner.stop.is_set() and len(seen) == 1 and not runner.sleep.called
        assert runner.ledger.rows()[0]["cost_usd"] == runner.ledger.rows()[0]["reservation_usd"]


@pytest.mark.parametrize("point", ["before_wait", "during_wait", "retry_guard"])
def test_external_stop_at_retry_boundaries_prevents_new_reservation(setup, monkeypatch, point):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        if point == "before_wait":
            clear_failure = runner.stop.clear_failure
            def clear_then_stop(before):
                cleared = clear_failure(before)
                runner.stop.set()
                return cleared
            monkeypatch.setattr(runner.stop, "clear_failure", clear_then_stop)
        elif point == "during_wait":
            runner.sleep.side_effect = lambda seconds: runner.stop.set()
        else:
            def guard(*args):
                if runner.guard.before_call.call_count == 2:
                    runner.stop.set()
            runner.guard.before_call.side_effect = guard
        with pytest.raises(Halted):
            judge_one(runner)
        assert sender.call_count == 1 and runner.stop.is_set()
        assert len(runner.ledger.rows()) == 1 and len(runner.receipts.records()) == 1
        assert runner.sleep.call_count == (0 if point == "before_wait" else 1)


def test_failure_stop_clear_is_single_use_and_preserves_other_changes():
    stop = t.StopSignal()
    before = stop.revision()
    stop.set()
    assert stop.clear_failure(before) and not stop.is_set()
    assert not stop.clear_failure(before)
    before = stop.revision()
    stop.set()
    stop.set()
    assert not stop.clear_failure(before) and stop.is_set()
    stop.clear()
    assert not stop.clear_failure(before)


def test_generation_errors_never_retry(setup):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, local=sender) as runner:
        with pytest.raises(Halted):
            runner.route_fixture("kolibri")
        assert sender.call_count == 1 and not runner.sleep.called and not runner.ledger.rows()


def test_filtered_fixture_stays_missing_gate_fails_but_other_fixtures_run(setup):
    local, good, generated, judged = senders()
    seen = []
    def sender(request):
        seen.append(deepcopy(request))
        return receipt(filtered(request, good)) if len(seen) == 1 else good(request)
    with opened(setup, sender, local) as runner:
        result = runner.run_fixtures()
        assert not result["pass"] and len(seen) == 24 and len(generated) == 1
        assert not runner.sleep.called and not runner.stop.is_set()
        assert not runner.fixture_gate()["pass"]
        first = runner.ledger.rows()[0]
        assert first["status"] == "unresolved" and first["reported_cost_usd"] == "0"
        assert first["cost_usd"] == first["reservation_usd"] and not first["cost_known"]
        audit = runner.audit()
        assert audit["terminal_refusal_calls"] == [first["call_id"]]
        assert audit["unresolved"] == 1 and audit["blocking_unresolved"] == 0
        before = tree_hashes(setup[1])
        result = judge_one(runner)
        assert result["status"] == "incomplete_judge" and result["raw_text"] == ""
        assert before == tree_hashes(setup[1]) and len(seen) == 24
        with pytest.raises(Halted, match="Fixture gate"):
            runner.generate_blocks("screen", initial=True)


def test_filtered_screen_label_is_missing_not_negative_and_no_retry(setup):
    local, good, _, _ = senders()
    with opened(setup, good, local) as runner:
        runner.run_fixtures()
        runner.generate_blocks("screen", initial=True)
        seen = []
        def sender(request):
            seen.append(request)
            return receipt(filtered(request, good)) if len(seen) == 1 else good(request)
        runner.sender = sender
        rows = runner.judge_blocks("screen", initial=True)
        assert len(seen) == 32 and not runner.sleep.called
        call = runner.audit()["terminal_refusal_calls"][0]
        physical = runner.receipts.existing(call)
        target = next(row for row in rows if row["id"] == physical["metadata"]["item_id"])
        assert "paper" not in target["labels"]["astra"]
        assert "structured" in target["labels"]["astra"]
        runner.complete("screen", initial=True)
        runner.approve_initial(runner.initial_audit())
        runner.require_resolved(channel="judge")
        assert physical["status"] == "unresolved" and physical["projection"] is None
        assert physical["error_type"] == "ReceiptError"
        assert runner.receipts.raw(physical)["service_tier"] == "auto"
        assert runner.ledger.existing(call)["raw"] == runner.receipts.raw(physical)
        assert not any(t.SUFFIX in c for c in runner.receipts.records())


def test_filter_after_transport_failures_is_terminal_and_preserves_all_holds(setup):
    _, good, _, _ = senders()
    sender, seen = flaky(lambda request: receipt(filtered(request, good)), [TIMEOUT, TIMEOUT])
    with opened(setup, sender) as runner:
        assert judge_one(runner)["status"] == "incomplete_judge"
        assert len(seen) == 3 and not runner.stop.is_set()
        report = runner.audit()
        assert report["physical_unresolved"] == 3 and report["blocking_unresolved"] == 0
        assert Decimal(report["terminal_refusal_holdback_usd"]) == runner.ledger.spent()
        before = tree_hashes(setup[1])
    with opened(setup, Mock(side_effect=AssertionError("No retry of a filter receipt"))) as runner:
        assert judge_one(runner)["status"] == "incomplete_judge"
        assert not runner.sleep.called and before == tree_hashes(setup[1])


@pytest.mark.parametrize("mutation", ["model", "provider", "tier", "nonzero", "negative", "bool",
    "missing_cost", "charged", "finish", "native_finish", "message_role", "empty_message", "error", "multiple"])
def test_refusal_exception_does_not_hide_invalid_receipts(setup, mutation):
    _, good, _, _ = senders()
    seen = []
    def sender(request):
        seen.append(request)
        raw = filtered(request, good)
        if mutation in ("model", "provider"):
            raw[mutation] = "synthetic wrong identity"
        elif mutation == "tier":
            raw["service_tier"] = "priority"
        elif mutation in ("nonzero", "negative", "bool"):
            raw["usage"]["prompt_tokens"] = {"nonzero": 1, "negative": -1, "bool": False}[mutation]
        elif mutation == "missing_cost":
            del raw["usage"]["cost"]
        elif mutation == "charged":
            raw["usage"]["cost"] = "0.01"
        elif mutation == "finish":
            raw["choices"][0]["finish_reason"] = "stop"
        elif mutation == "native_finish":
            raw["choices"][0]["native_finish_reason"] = "length"
        elif mutation == "message_role":
            raw["choices"][0]["message"]["role"] = "user"
        elif mutation == "empty_message":
            raw["choices"][0]["message"]["content"] = ""
        elif mutation == "error":
            raw["error"] = {"code": 500}
        else:
            raw["choices"].append(deepcopy(raw["choices"][0]))
        return receipt(raw)
    with opened(setup, sender) as runner:
        with pytest.raises(Halted):
            judge_one(runner)
        assert len(seen) == 1 and not runner.sleep.called
        assert runner.audit()["terminal_refusal_calls"] == []
        with pytest.raises(Halted):
            runner.require_resolved(channel="judge")


def test_full_screen_barriers_forecast_and_generation_independence(setup):
    local, good, generated, judged = senders()
    sender, seen = flaky(good, [TIMEOUT])
    with opened(setup, sender, local) as runner:
        assert runner.run_fixtures()["pass"] and runner.fixture_gate()["pass"]
        runner.generate_blocks("screen", initial=True)
        # One failed physical attempt during the measured screen too.
        runner.sender, _ = flaky(good, [TIMEOUT])
        runner.judge_blocks("screen", initial=True)
        runner.approve_initial(runner.initial_audit())
        count = len(judged)
        runner.generate_blocks("screen")
        assert len(judged) == count and len(generated) == 73
        runner.judge_blocks("screen")
        assert runner.qualification()["eligible_models"] == ["kolibri"]
        evidence = dict(gpu_spent_usd="2", gpu_hourly_rate_usd="4.59", gpu_remaining_seconds="10000",
                        storage_bound_usd="1", remaining_overhead_seconds="600")
        admission = runner.main_admission(**evidence)
        screen_cost = sum((Decimal(b["cost_usd"]) for b in runner.ledger.rows() if b["phase"] == "screen"), Decimal(0))
        assert Decimal(admission["judge_main_with_margin_usd"]) == Decimal("1.30") * 256 * (screen_cost / 48)
        assert Decimal(admission["judge_completion_usd"]) == runner.ledger.spent() + Decimal(admission["judge_main_with_margin_usd"])
        assert admission["fits"] and runner.audit()["physical_unresolved"] == 2
        runner.approve_main(admission)
        runner.sender = None
        count = len(judged)
        assert runner.generate_blocks("main")["generation_calls"] == 384
        assert len(judged) == count


@pytest.mark.parametrize("mode", ["raw", "extra", "missing", "projection", "request", "retry_freeze", "accounting"])
def test_physical_tamper_rejected_even_with_rehashed_derived_data(setup, mode):
    _, good, _, _ = senders()
    sender, _ = flaky(good, [TIMEOUT])
    with opened(setup, sender) as runner:
        judge_one(runner)
        call, row = next(iter(runner.receipts.records().items()))
    directory = setup[1] / "collection/http"
    http_path, bill_path = directory / "events.jsonl", setup[1] / "collection/judges/events.jsonl"
    if mode == "raw":
        (directory / row["body"]["path"]).write_bytes(b"changed")
    elif mode == "extra":
        (directory / "extra.json").write_bytes(b"{}")
    elif mode == "missing":
        (directory / row["body"]["path"]).unlink()
    else:
        events, bills = read_events(http_path), read_events(bill_path)
        retry = next(e["data"] for e in events if e["kind"] == "dispatch" and t.SUFFIX in e["data"]["call_id"])
        if mode == "projection":
            events[-1]["data"]["projection"]["response"] = "fabricated label"
        elif mode == "request":
            retry["request"]["provider"]["allow_fallbacks"] = True
            retry["request_sha256"] = protocol.digest(retry["request"])
            for event in bills:
                if event["data"].get("call_id") == retry["call_id"]:
                    event["data"]["request_sha256"] = retry["request_sha256"]
                    if event["kind"] == "reserve":
                        event["data"]["request"] = deepcopy(retry["request"])
        elif mode == "retry_freeze":
            retry["metadata"]["transport_retry"]["operational_freeze"] = "f"*40
        else:
            next(e["data"] for e in bills if e["kind"] == "settle")["cost_usd"] = "0"
        rehash(http_path, events)
        rehash(bill_path, bills)
    with pytest.raises((Halted, ValueError, OSError)):
        with opened(setup) as runner:
            runner.audit()


@pytest.mark.parametrize("file", ["repair.py", t.SOURCES[0], t.PLAN])
def test_all_additive_source_bindings_checked_before_dispatch(setup, file):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        path = protocol.ROOT / file
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(Halted):
            judge_one(runner)
        assert not sender.called


def test_candidate_is_exact_a2_binding_and_does_not_write(setup):
    before = tree_hashes(protocol.ROOT)
    result = t.build_plan(WORKER_FREEZE)
    assert result["worker_freeze"] == WORKER_FREEZE and result["new_budget_usd"] == "0"
    assert result["additional_attempts"] == 2 and result["backoff_seconds"] == [2, 5]
    assert not set(result["source_hashes"]) & set(setup[0]["source_hashes"])
    assert before == tree_hashes(protocol.ROOT)
    with pytest.raises(Halted):
        t.build_plan("not-a-freeze")


def test_pending_attempt_is_never_resent(setup):
    sender = Mock(return_value=TIMEOUT)
    with opened(setup, sender) as runner:
        runner.guard.before_call.side_effect = [None, Halted("synthetic interrupted retry")]
        with pytest.raises(Halted):
            judge_one(runner)
        row = next(iter(runner.receipts.records().values()))
        call = row["call_id"] + t.SUFFIX + "1"
        metadata = t.retry_meta(row["metadata"], row["call_id"], 1, OPERATIONAL)
        runner.ledger.reserve(call, row["request"], runner.ledger.rows()[0]["reservation_usd"], "fixtures", metadata)
        runner.receipts.append("dispatch", {k: row[k] for k in ("request", "request_sha256", "phase", "channel")} |
                               {"call_id": call, "metadata": metadata})
    with opened(setup, sender) as runner:
        assert runner.audit()["unresolved"] == 1
        with pytest.raises(Halted):
            judge_one(runner)
        assert sender.call_count == 1 and len(runner.ledger.rows()) == 2


def test_mocked_cli_uses_same_a2_root_guard_deadlines_and_readonly_audit(setup, monkeypatch, capsys):
    from tests import test_kolibri_swap_production as helpers
    plan, root, amendment, transport = setup
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    monkeypatch.setattr(helpers, "FREEZE", WORKER_FREEZE)
    for kind in ("cheap", "main"):
        controller = helpers.saved_controller(root, kind, closed=kind == "cheap", plan_hash=digest)
        controller.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / adapter.AMENDMENT)})
    local, good, generated, judged = senders()
    judge, physical = flaky(good, [TIMEOUT])
    factory_calls = []
    def factory(endpoint, timeout_seconds, api_key=None):
        factory_calls.append((endpoint, timeout_seconds, api_key))
        return judge if api_key else local
    real_guard = adapter.StudyGuard
    guards = []
    def guard(*args, **kwargs):
        value = real_guard(*args, clock=lambda: helpers.NOW, **kwargs)
        value.before_call = Mock(wraps=value.before_call)
        guards.append(value)
        return value
    monkeypatch.setattr(adapter, "StudyGuard", guard)
    monkeypatch.setattr(t, "verify", Mock(return_value=transport))
    monkeypatch.setattr(protocol, "verify", lambda path: deepcopy(plan))
    monkeypatch.setattr(adapter, "root", lambda: root)
    monkeypatch.setattr(r, "http_sender", factory)
    key = Mock(return_value="synthetic-no-real-credential")
    monkeypatch.setattr(prod, "local_key", key)
    monkeypatch.setattr(t, "datetime", type("Clock", (), {"now": staticmethod(lambda tz: helpers.NOW)}))
    evidence_path = protocol.ROOT / "out/synthetic-reconciliation-basis.json"
    write(evidence_path, {"synthetic": True})
    reconciliation = root / "synthetic-reconciliation.json"
    write(reconciliation, {"as_of": helpers.NOW.isoformat(), "openrouter_prior_and_reserved_usd": "0",
        "runpod_prior_and_reserved_usd": "0", "source_hashes": {
            "out/synthetic-reconciliation-basis.json": protocol.sha(evidence_path)}})
    assert t.main(["--freeze", OPERATIONAL, "--execute", "--phase", "fixtures", "--port", "12345",
                   "--reconciliation", str(reconciliation)]) == 0
    assert len(generated) == 1 and len(judged) == 24 and len(physical) == 25
    assert guards[0].before_call.call_count == 26
    assert factory_calls == [("http://127.0.0.1:12345/v1/chat/completions", 300, None),
                             (t.ENDPOINT, 600, "synthetic-no-real-credential")]
    assert prod.load(root / "collection/runtime.json")["freeze"] == WORKER_FREEZE
    assert key.call_count == 1
    before = tree_hashes(root)
    assert t.main(["--freeze", OPERATIONAL, "--phase", "audit", "--run-dir", str(root)]) == 0
    assert key.call_count == 1 and len(factory_calls) == 2 and before == tree_hashes(root)
    assert "synthetic-no-real-credential" not in capsys.readouterr().out
    for path in (root / "collection").rglob("*"):
        if path.is_file():
            assert b"synthetic-no-real-credential" not in path.read_bytes()
    # Removing the activation event cannot re-admit an already judged prefix.
    path = root / "collection/http/events.jsonl"
    events = [e for e in read_events(path) if not (e["kind"] == "decision" and e["data"]["name"] == "judge_transport")]
    rehash(path, events)
    with pytest.raises(SystemExit):
        t.main(["--freeze", OPERATIONAL, "--execute", "--phase", "fixtures", "--port", "12345",
                "--reconciliation", str(reconciliation)])
    assert key.call_count == 1 and len(physical) == 25


@pytest.mark.parametrize("args", [["--phase", "fixtures"], ["--phase", "audit", "--execute"],
    ["--phase", "fixtures", "--execute", "--run-dir", "/tmp/other"], ["--build", "--execute"]])
def test_cli_permission_and_root_guards_precede_credentials(args, monkeypatch):
    verify = Mock(side_effect=AssertionError("must not reach provider proof"))
    monkeypatch.setattr(t, "verify", verify)
    key = Mock(side_effect=AssertionError("must not read credentials"))
    monkeypatch.setattr(prod, "local_key", key)
    with pytest.raises(SystemExit) as error:
        t.main(["--freeze", OPERATIONAL, *args])
    assert error.value.code == 1 and not verify.called and not key.called
