"""Eight independent judgments with one physical journal/accounting owner.

Compose as Runner(JudgeWavesMixin, bridge.Runner). The generation amendment
must bind SOURCES and POLICY under ``judge_waves`` before use. Frozen judge(),
schema repair, receipt parsing, cost accounting, transport eligibility and
terminal-refusal rules are reused unchanged. Only the coordinator writes.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from queue import Empty, Queue
import threading
from types import SimpleNamespace

from experiments import kolibri_judge_transport as transport
from experiments.kolibri_swap import protocol, runtime as r, production as prod
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import _public_body, parse_result, receipt_cost, reservation


WIDTH = 8
SOURCES = ("experiments/kolibri_judge_waves.py", "tests/test_kolibri_judge_waves.py")
POLICY = {"schema": "kolibri-judge-waves-v1", "logical_width": WIDTH,
          "additional_transport_attempts": 2, "backoff_seconds": [2, 5],
          "schema_repair_changed": False, "refusal_policy_changed": False,
          "reservation": "full_worst_case_each_physical_attempt_before_send",
          "single_journal_owner": True, "stop_new_and_drain": True}
check = prod.check


def _send(runner, request):
    if runner.stop.is_set():
        return r.HTTPReceipt(None, b"", 0., "StoppedBeforeSend")
    try:
        value = runner.sender(deepcopy(request))
        check(isinstance(value, r.HTTPReceipt), "Exact HTTP receipt required")
        return value
    except BaseException:
        return r.HTTPReceipt(None, b"", 0., "TransportException")


class JudgeWavesMixin:
    def _judge_waves_binding(self):
        self.check_sources()
        check(self.wave_plan.get("judge_waves") == POLICY, "Judge wave policy unbound or changed")
        check(all(self.wave_plan["source_hashes"].get(name) == protocol.sha(protocol.ROOT / name)
                  for name in SOURCES), "Judge wave sources not bound")
        decision = self.receipts.decision("generation_waves")
        check(decision is not None and decision["operational_freeze"] == self.wave_freeze
              and decision["worker_freeze"] == self.freeze
              and decision["amendment_sha256"] == protocol.digest(self.wave_plan),
              "Judge wave operational authority absent")

    def _exchange(self, call_id, request, phase, metadata, channel, sender, spec):
        context = getattr(self, "_judge_wave_context", None)
        if context is None:
            return super()._exchange(call_id, request, phase, metadata, channel, sender, spec)
        check(channel == "judge" and getattr(context.worker, "job", None) is not None,
              "Only owned logical judges may use an active judge wave")
        job = context.worker.job
        for ordinal in range(3):
            check(not self.stop.is_set(), "External stop blocks judge dispatch")
            if ordinal:
                self.sleep(transport.BACKOFF[ordinal - 1])
            check(not self.stop.is_set(), "External stop blocks judge dispatch")
            with context.admission_lock:
                check(not self.stop.is_set(), "Stop before queuing judge request")
                reply = Future()
                context.requests.put((job, call_id, deepcopy(request), phase, deepcopy(metadata),
                                      spec, ordinal, reply))
            result, retry = reply.result()
            if not retry:
                return result
        self.stop.set()
        raise Halted("Three physical judge attempts exhausted; label remains missing")

    def _judge_wave_pending(self, context):
        """Never adopt inherited/foreign pending requests as concurrent work."""
        # The coordinator owns mutation, as in the frozen transport guard.
        # Avoid copying every prompt/response on each of 1,024 admissions.
        records = self.receipts._cache
        paid = self.ledger._calls
        check(set(paid) == {call for call, row in records.items() if row["channel"] == "judge"},
              "Orphan physical reservation or HTTP dispatch")
        pending = {call for call, row in records.items() if row["status"] == "pending"}
        check(pending == context.active, "Unowned or lost pending request blocks dispatch")
        latest = {}
        for call, row in records.items():
            if row["channel"] != "judge":
                continue
            logical, ordinal = transport.split_id(call)
            latest[logical] = (row, ordinal)
            check(not paid[call].get("over_reservation"), "Physical receipt exceeded reservation")
            if row["status"] == "pending":
                check(paid[call]["status"] == "pending", "Physical settlement incomplete")
        for logical, (row, ordinal) in latest.items():
            if row["status"] in {"received", "pending"}:
                continue
            if transport.refusal_missing(row, paid[row["call_id"]], self.receipts, self.plan) is not None:
                continue
            check(logical in context.retry_scope and ordinal < 2
                  and transport.eligible(row, paid[row["call_id"]], self.receipts),
                  "Unowned, nontransport or exhausted failure blocks dispatch")

    def _judge_wave_request(self, context, task):
        job, logical, request, phase, metadata, spec, ordinal, reply = task
        item_id, response, judge, instrument, expected_phase = job
        check(job in context.jobs and phase == expected_phase, "Unowned logical judge request")
        expected = judges.judge_request(self.plan["judges"][judge], instrument, response)
        expected["provider"].update(r.PRIVACY)
        attempt = metadata.get("attempt")
        check(type(attempt) is int and attempt in (0, 1), "Unknown schema attempt")
        check(logical == f"judge:{item_id}:{judge}:{instrument}:a{attempt}"
              and request == expected and spec == self.plan["judges"][judge]
              and metadata == {"kind": "judge", "item_id": item_id, "judge": judge,
                  "instrument": instrument, "attempt": attempt,
                  "response_sha256": protocol.digest(response)}, "Judge request/privacy/metadata changed")
        if attempt:
            prior = None
            for index in range(3):
                identity = f"judge:{item_id}:{judge}:{instrument}:a0" + (transport.SUFFIX + str(index) if index else "")
                row = self.receipts.existing(identity)
                if row is not None:
                    prior = row
            value = prior["projection"] if prior and prior["status"] == "received" else None
            check(value is not None and value["complete"] and not value["missing"],
                  "Schema repair lacks complete original judgment")
            try:
                judges.parse(instrument, response, value["response"])
            except (ValueError, KeyError, TypeError):
                pass
            else:
                raise Halted("Valid label cannot be rejudged")
        physical = logical + (transport.SUFFIX + str(ordinal) if ordinal else "")
        meta = transport.retry_meta(metadata, logical, ordinal, self.operational_freeze)
        dispatch = {"call_id": physical, "request": request, "request_sha256": protocol.digest(request),
                    "phase": phase, "channel": "judge",
                    "metadata": {**meta, "freeze": self.freeze, "plan_sha256": self.plan_hash}}
        return dispatch, spec, reply

    def _judge_wave_existing(self, dispatch):
        existing = self.receipts.existing(dispatch["call_id"])
        if existing is None:
            return None
        check(all(existing[k] == v for k, v in dispatch.items()), "Existing physical attempt changed")
        bill = self.ledger.existing(dispatch["call_id"])
        check(bill is not None and not bill.get("over_reservation"), "Physical accounting unresolved")
        if existing["status"] == "received":
            return existing["projection"], False
        missing = transport.refusal_missing(existing, bill, self.receipts, self.plan)
        if missing is not None:
            return missing, False
        check(transport.eligible(existing, bill, self.receipts), "Prior request is not retryable")
        return None, True

    def _judge_wave_settle(self, dispatch, spec, receipt):
        raw, cost, result, problem = None, None, None, None
        try:
            raw = r.strict_json(receipt.body)
            _public_body(raw)
            cost = receipt_cost(spec, raw)
            if receipt.error is not None or receipt.status != 200:
                raise ValueError("Ambiguous or unsuccessful HTTP request")
            if cost is None:
                raise ValueError("Judge accounting unavailable")
            result = parse_result(spec, raw)
        except Exception as error:
            problem = type(error).__name__
        with self.ledger._mutex, self.receipts.mutex:
            self.receipts.finish(dispatch["call_id"], receipt, result, problem)
            self.ledger.settle(dispatch["call_id"], raw if isinstance(raw, dict) else None, cost,
                               error=ValueError() if problem else None)
        return self._judge_wave_existing(dispatch)

    def _run_judge_wave(self, jobs, retry_scope=None):
        check(0 < len(jobs) <= WIDTH and len(set(jobs)) == len(jobs), "Invalid judge wave width/inventory")
        self._judge_waves_binding()
        for item_id, response, judge, instrument, phase in jobs:
            check(judge in self.plan["judges"] and instrument in judges.INSTRUMENTS,
                  "Unplanned judge or instrument")
            if phase == "fixtures":
                check(item_id in self.fixtures and response == self.fixtures[item_id]["response"],
                      "Fixture response differs")
            else:
                item = self.catalog.get(item_id)
                record = self.receipts.existing("gen:" + item_id)
                check(phase in {"screen", "main"} and item is not None and item["kind"] == "final"
                      and item["phase"] == phase and record is not None and record["status"] == "received"
                      and not record["projection"]["missing"] and response == record["projection"]["response"],
                      "Judge lacks exact planned saved response")
        check(not self.stop.is_set() and not self._existing_only and self.sender is not None
              and self.guard is not None, "Live judge guard/sender absent or stopped")
        with self._channel_locks["judge"]:
            check(getattr(self, "_judge_wave_context", None) is None, "Another judge wave owns the runner")
            context = SimpleNamespace(requests=Queue(), worker=threading.local(), jobs=tuple(jobs), active=set(),
                admission_lock=threading.Lock(),
                retry_scope=set(retry_scope or [f"judge:{j[0]}:{j[2]}:{j[3]}:a{a}" for j in jobs for a in (0, 1)]))
            self._judge_wave_pending(context)
            self._judge_wave_context = context
            failed, pending = False, {}

            def logical(job):
                context.worker.job = job
                try:
                    return self.judge(*job)
                finally:
                    del context.worker.job

            def halt(reply=None):
                nonlocal failed
                failed = True
                with context.admission_lock:
                    self.stop.set()
                if reply is not None and not reply.done():
                    reply.set_exception(Halted("Judge wave stopped; physical history retained"))

            try:
                with ThreadPoolExecutor(max_workers=WIDTH) as network, ThreadPoolExecutor(max_workers=WIDTH) as workers:
                    logical_futures = []
                    for job in jobs:
                        try:
                            logical_futures.append(workers.submit(logical, job))
                        except BaseException:
                            # Started workers may already await coordinator
                            # replies. Drain them before executor shutdown.
                            halt()
                            break
                    while pending or not all(f.done() for f in logical_futures) or not context.requests.empty():
                        # Persist replies before admitting new work, even after
                        # stop. No cancellation discards an in-flight receipt.
                        for future in tuple(pending):
                            if not future.done():
                                continue
                            dispatch, spec, reply = pending.pop(future)
                            try:
                                value = self._judge_wave_settle(dispatch, spec, future.result())
                                context.active.remove(dispatch["call_id"])
                                reply.set_result(value)
                            except BaseException:
                                halt(reply)
                        if any(f.done() and f.exception() is not None for f in logical_futures):
                            halt()
                        try:
                            task = context.requests.get(timeout=0.005)
                        except Empty:
                            continue
                        reply = task[-1]
                        if failed or self.stop.is_set():
                            halt(reply)
                            continue
                        try:
                            self._judge_waves_binding()
                            dispatch, spec, reply = self._judge_wave_request(context, task)
                            with self.ledger._mutex, self.receipts.mutex:
                                self._judge_wave_pending(context)
                                prior = self._judge_wave_existing(dispatch)
                                if prior is not None:
                                    reply.set_result(prior)
                                    continue
                                check(not self.stop.is_set(), "Stop before judge reservation")
                                self.guard.before_call("judge", dispatch["phase"], spec, dispatch["request"])
                                check(not self.stop.is_set(), "Stop during judge guard")
                                self.ledger.reserve(dispatch["call_id"], dispatch["request"],
                                    reservation(spec, dispatch["request"]), dispatch["phase"], dispatch["metadata"])
                                self.receipts.append("dispatch", dispatch)
                                context.active.add(dispatch["call_id"])
                            future = network.submit(_send, self, dispatch["request"])
                            pending[future] = (dispatch, spec, reply)
                        except BaseException:
                            halt(reply)
                    results = []
                    for future in logical_futures:
                        try:
                            results.append(future.result())
                        except BaseException:
                            halt()
            finally:
                self._judge_wave_context = None
            check(not failed and not self.stop.is_set(), "Judge wave halted after draining; no new calls")
            return results

    def judge_blocks(self, phase, initial=False):
        check(phase in {"screen", "main"} and (not initial or phase == "screen"), "Invalid judging stage")
        check(not initial, "Sequential initial qualification remains immutable")
        self._judge_waves_binding()
        self.require_resolved(channel="judge")
        self.audit()
        jobs = []
        for block in self.plan[phase]:
            for item in block["finals"]:
                record = self.receipts.existing("gen:" + item["id"])
                if record is None or record["status"] != "received" or record["projection"]["missing"]:
                    continue
                for judge in self.plan["judges"]:
                    for instrument in judges.INSTRUMENTS:
                        jobs.append((item["id"], record["projection"]["response"], judge, instrument, phase))
        scope = {f"judge:{j[0]}:{j[2]}:{j[3]}:a{a}" for j in jobs for a in (0, 1)}
        for offset in range(0, len(jobs), WIDTH):
            self._run_judge_wave(jobs[offset:offset + WIDTH], retry_scope=scope)
        self.audit()
        return self.rows(phase)

    def audit(self):
        report = super().audit()
        active, peak = set(), 0
        for event in self.receipts.events:
            if event["kind"] == "dispatch" and event["data"]["channel"] == "judge":
                active.add(event["data"]["call_id"])
                peak = max(peak, len(active))
                check(peak <= WIDTH, "Judge physical concurrency exceeded eight")
                logical = [transport.split_id(call)[0].rsplit(":a", 1)[0] for call in active]
                check(len(logical) == len(set(logical)), "Same logical judge dispatched concurrently")
            elif event["kind"] == "response":
                active.discard(event["data"]["call_id"])
        return {**report, "judge_waves": {"policy": POLICY, "peak_physical_pending": peak,
                                         "pending": len(active)}}
