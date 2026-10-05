"""Bounded judge transport and terminal missing refusals on the A2 ledgers.

Physical HTTP bodies and charges are immutable. A disposable, explicitly
derived logical view is checked by the frozen request auditor. No controller,
root, worker binding, prompt, instrument, qualification or sample is replaced.
Validated Azure filter receipts stay physically unresolved and fully reserved;
only their derived label disposition is terminal missing, never negative.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from experiments.kolibri_bootstrap_a2 import adapter, production as a2
from experiments.kolibri_swap import production as prod, protocol, runtime as r
from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks
from experiments.openrouter_swap.providers import (
    ENDPOINT, _amount, _public_body, parse_result, receipt_cost, reservation,
)
from experiments.openrouter_swap.runner import write_once

PLAN = "data/kolibri_judge_transport/plan_v1_20261005/PLAN.json"
SOURCES = ("experiments/kolibri_judge_transport.py", "tests/test_kolibri_judge_transport.py")
SUFFIX = ":transport-r"
BACKOFF = (2, 5)


def split_id(call):
    if SUFFIX not in call:
        return call, 0
    logical, ordinal = call.rsplit(SUFFIX, 1)
    prod.check(logical.startswith("judge:") and SUFFIX not in logical and ordinal in ("1", "2"),
               "Invalid physical judge attempt ID")
    return logical, int(ordinal)


def retry_meta(metadata, logical, ordinal, freeze):
    return {**metadata, **({"transport_retry": {"logical_call_id": logical, "ordinal": ordinal,
                                               "operational_freeze": freeze}} if ordinal else {})}


def eligible(row, bill, receipts):
    """Only transient transport/outer-JSON failures with the full unknown holdback."""
    if (row["channel"] != "judge" or row["status"] != "unresolved"
            or row["metadata"].get("kind") != "judge" or bill is None
            or bill["status"] != "unresolved" or bill.get("cost_known") is not False
            or bill.get("reported_cost_usd") is not None or bill.get("over_reservation")
            or bill["cost_usd"] != bill["reservation_usd"]):
        return False
    status, error = row["http_status"], row["transport_error"]
    if error == "UnsafeReceipt" or status is not None and status != 200 and not (
            status in (408, 425, 429) or 500 <= status <= 599):
        return False
    try:
        raw = receipts.raw(row)
    except (ValueError, UnicodeError):
        raw = None
    # A delivered completion or accounting/identity-bearing object is not a
    # transport failure, even if a later read timed out or validation failed.
    if isinstance(raw, dict) and any(k in raw for k in ("choices", "usage", "model", "provider", "refusal")):
        return False
    if isinstance(raw, dict) and isinstance(raw.get("error"), dict):
        code = raw["error"].get("code")
        if code is not None and code not in (408, 425, 429) and not (type(code) is int and 500 <= code <= 599):
            return False
    if error is not None:
        return error in {"TotalDeadlineExceeded", "HTTPWorkerExited", "HTTPFailure", "TransportException"}
    if status in (408, 425, 429) or status is not None and 500 <= status <= 599:
        return True
    return status == 200 and row["error_type"] in {"JSONDecodeError", "UnicodeDecodeError"}


def refusal_missing(row, bill, receipts, plan):
    """Only the known Azure auto-tier, zero-usage content-filter shape.

    The HTTP/ledger failure and full unknown holdback stay unchanged. This
    returns a terminal missing-label interpretation, never a replacement raw
    receipt or a successful default-tier result.
    """
    try:
        meta = row["metadata"]
        spec = plan["judges"][meta["judge"]]
        raw = receipts.raw(row)
        if (row["channel"] != "judge" or meta["kind"] != "judge" or meta["judge"] != "astra"
                or row["status"] != "unresolved" or row["error_type"] != "ReceiptError"
                or row["http_status"] != 200 or row["transport_error"] is not None
                or bill["status"] != "unresolved" or bill["error_type"] != "ValueError"
                or bill["cost_known"] is not False or bill["over_reservation"]
                or bill["cost_usd"] != bill["reservation_usd"] or bill["reported_cost_usd"] != "0"
                or not isinstance(raw, dict) or raw.get("service_tier") != "auto" or raw.get("error") is not None
                or not isinstance(raw.get("id"), str) or not raw["id"].strip()
                or raw.get("model") not in [spec["id"], *spec.get("model_aliases", [])]
                or raw.get("provider") != spec["provider_name"]):
            return None
        choices, usage = raw["choices"], raw["usage"]
        if (not isinstance(choices, list) or len(choices) != 1
                or any(type(usage.get(k)) is not int or usage[k] != 0
                       for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                or _amount(usage.get("cost")) != 0 or receipt_cost(spec, raw) != 0):
            return None
        choice, message = choices[0], choices[0]["message"]
        if (choice.get("finish_reason") != "content_filter"
                or choice.get("native_finish_reason") not in (None, "content_filter", "refusal")
                or message.get("role") != "assistant" or not isinstance(message.get("content"), str)
                or not message["content"].strip()
                or message.get("refusal") is not None and not isinstance(message["refusal"], str)):
            return None
        return {"status": "provider_refusal_missing", "response": "", "missing": True,
                "refusal": True, "complete": False, "cap_hit": False,
                "stop_reason": "content_filter", "native_finish_reason": choice.get("native_finish_reason"),
                "model": raw["model"], "provider": raw["provider"], "service_tier": "auto",
                "service_tier_verified": False, "derived_terminal_missing": True}
    except (KeyError, TypeError, ValueError, AttributeError, Halted):
        return None


class LedgerView:
    """Read-only selected receipts; forecasting includes every physical charge."""
    def __init__(self, physical, rows, totals):
        self.cap, self.screen_cap = physical.cap, physical.screen_cap
        self._mutex, self._calls = threading.RLock(), deepcopy(rows)
        self.total, self.totals, self.forecast = physical.spent(), totals, False

    def existing(self, call):
        value = deepcopy(self._calls.get(call))
        if value is not None and self.forecast:
            value["cost_usd"] = str(self.totals[call])
        return value

    def rows(self):
        return [self.existing(call) for call in self._calls]

    def spent(self):
        return self.total


class ReceiptView:
    def __init__(self, physical, directory, records):
        self.root, self.binding = directory, physical.binding
        self.mutex, self._records = threading.RLock(), records
        self.events = deepcopy(physical.events)
        self.refusals, self.terminal_view = {}, False

    def _row(self, call):
        value = deepcopy(self._records.get(call))
        if value is not None and self.terminal_view and call in self.refusals:
            value.update(status="received", projection=deepcopy(self.refusals[call]),
                         source_receipt_status="unresolved", derived_terminal_missing=True)
        return value

    def records(self, verify=False):
        return {call: self._row(call) for call in self._records}

    def existing(self, call):
        return self._row(call)

    def unresolved(self, channel=None, phases=None):
        return any(row["status"] != "received" for row in self._records.values()
                   if (channel is None or row["channel"] == channel)
                   and (phases is None or row["phase"] in phases))

    def raw(self, row):
        return r.strict_json((self.root / row["body"]["path"]).read_bytes())

    def decision(self, name):
        return next((deepcopy(e["data"]["value"]) for e in self.events
                     if e["kind"] == "decision" and e["data"]["name"] == name), None)


class CheckedReader(r.Runner):
    """Frozen audit runs before allowing the forecast-only cost aggregation."""
    def audit(self):
        if not hasattr(self, "checked_report"):
            self.checked_report = super().audit()
        return deepcopy(self.checked_report)

    def require_resolved(self, channel=None, phases=None):
        # Frozen request/raw audit already ran on the unmodified logical view.
        # Only independently validated terminal refusals can remain missing.
        for row in self.ledger.rows():
            if channel != "local" and (phases is None or row["phase"] in phases):
                prod.check(not row.get("over_reservation") and
                           (row["status"] == "settled" or row["call_id"] in self.receipts.refusals),
                           "Nonterminal judge failure blocks analysis admission")
        for call, row in self.receipts._records.items():
            if (channel is None or row["channel"] == channel) and (phases is None or row["phase"] in phases):
                prod.check(row["status"] == "received" or call in self.receipts.refusals,
                           "Nonterminal HTTP failure blocks analysis admission")


class StopSignal(threading.Event):
    """Clear one inherited receipt-failure set only if no other stop changed."""
    def __init__(self):
        super().__init__()
        self._revision, self._revision_lock = 0, threading.Lock()

    def set(self):
        with self._revision_lock:
            self._revision += 1
            super().set()

    def clear(self):
        with self._revision_lock:
            self._revision += 1
            super().clear()

    def revision(self):
        with self._revision_lock:
            return self._revision

    def clear_failure(self, before):
        with self._revision_lock:
            if self._revision != before + 1 or not self.is_set():
                return False
            self._revision += 1
            super().clear()
            return True


class Runner(a2.Runner):
    def __init__(self, *args, transport_plan, operational_freeze, sleep=time.sleep, **kwargs):
        self.transport_plan, self.operational_freeze = deepcopy(transport_plan), operational_freeze
        self.transport_hash = protocol.sha(protocol.ROOT / PLAN)
        prod.check(prod.load(protocol.ROOT / PLAN) == transport_plan
                   and re.fullmatch(r"[0-9a-f]{40}", transport_plan["worker_freeze"])
                   and re.fullmatch(r"[0-9a-f]{40}", operational_freeze), "Transport binding differs")
        self.sleep, self._retry_current = sleep, None
        super().__init__(*args, **kwargs)
        stopped = self.stop.is_set()
        self.stop = StopSignal()
        if stopped:
            self.stop.set()
        prod.check(self.freeze == transport_plan["worker_freeze"], "Bound A2 worker freeze required")

    def check_sources(self):
        super().check_sources()
        prod.check(protocol.sha(protocol.ROOT / PLAN) == self.transport_hash
                   and protocol.digest(prod.load(protocol.ROOT / PLAN)) == protocol.digest(self.transport_plan)
                   and all(protocol.sha(protocol.ROOT / name) == digest
                           for name, digest in self.transport_plan["source_hashes"].items()),
                   "Judge transport source binding changed")

    def _judge_receipt(self, row, bill):
        spec = self.plan["judges"][row["metadata"]["judge"]]
        prod.check(bill is not None and all(bill[k] == row[k] for k in
                   ("request", "request_sha256", "metadata", "phase"))
                   and Decimal(bill["reservation_usd"]) == reservation(spec, row["request"]),
                   "Physical HTTP and judge reservation differ")
        if row["status"] == "pending":
            prod.check(bill["status"] == "pending", "Incomplete physical settlement")
            return
        raw, cost, projection, problem = None, None, None, None
        try:
            raw = self.receipts.raw(row)
            _public_body(raw)
            cost = receipt_cost(spec, raw)
            if row["transport_error"] is not None or row["http_status"] != 200:
                raise ValueError("Transport incomplete")
            if cost is None:
                raise ValueError("Accounting unavailable")
            projection = parse_result(spec, raw)
        except Exception as error:
            problem = type(error).__name__
        prod.check(row["error_type"] == problem and row["projection"] == projection
                   and row["status"] == ("unresolved" if problem else "received"),
                   "Physical response classification changed")
        settled = Ledger._settlement(bill, raw if isinstance(raw, dict) else None,
                                     cost, "ValueError" if problem else None)
        prod.check(all(bill[k] == value for k, value in settled.items()),
                   "Physical judge accounting does not reconstruct")

    @contextmanager
    def logical_reader(self, *, forecast=False, terminal_view=True):
        self.check_sources()
        with self.ledger._mutex, self.receipts.mutex:
            records = self.receipts.records(verify=True)
            paid = {x["call_id"]: x for x in self.ledger.rows()}
            expected = {"events.jsonl", ".lock"} | {x["body"]["path"] for x in records.values() if "body" in x}
            actual = set()
            for path in self.receipts.root.rglob("*"):
                _no_symlinks(path)
                if path.is_file():
                    actual.add(path.relative_to(self.receipts.root).as_posix())
            prod.check(actual == expected, "Extra or missing physical HTTP artifact")
            http_order, bill_order = {}, {}
            for event in self.receipts.events:
                if event["kind"] in {"dispatch", "response"}:
                    http_order[(event["data"]["call_id"], event["kind"])] = event["seq"]
            for event in self.ledger._events:
                if event["kind"] in {"reserve", "settle"}:
                    bill_order[(event["data"]["call_id"], event["kind"])] = event["seq"]
            selected, bills, mapping, totals, refusals = {}, {}, {}, {}, {}
            for call, row in records.items():
                logical, ordinal = split_id(call)
                if ordinal:
                    prod.check(logical in mapping and logical in records, "Retry lacks original request")
                    prior = records[mapping[logical][-1]]
                    base = records[logical]
                    prod.check(ordinal == len(mapping[logical]) and row["channel"] == "judge"
                               and eligible(prior, paid.get(prior["call_id"]), self.receipts)
                               and row["metadata"] == retry_meta(base["metadata"], logical, ordinal, self.operational_freeze)
                               and all(row[k] == base[k] for k in ("request", "request_sha256", "phase", "channel"))
                               and http_order[(prior["call_id"], "response")] < http_order[(call, "dispatch")]
                               and bill_order[(prior["call_id"], "settle")] < bill_order[(call, "reserve")],
                               "Retry is not an identical request after an eligible failure")
                else:
                    prod.check("transport_retry" not in row["metadata"], "Retry metadata on original request")
                mapping.setdefault(logical, []).append(call)
                copy = deepcopy(row)
                copy["call_id"] = logical
                copy["metadata"].pop("transport_retry", None)
                selected[logical] = copy
                if row["channel"] == "judge":
                    bill = paid.get(call)
                    self._judge_receipt(row, bill)
                    missing = refusal_missing(row, bill, self.receipts, self.plan)
                    if missing is not None:
                        refusals[logical] = missing
                    bills[logical] = {**deepcopy(bill), "call_id": logical, "metadata": copy["metadata"]}
                    totals[logical] = totals.get(logical, Decimal(0)) + Decimal(bill["cost_usd"])
            prod.check(set(paid) == {k for k, v in records.items() if v["channel"] == "judge"},
                       "Orphan physical reservation or missing HTTP dispatch")
            ledger = LedgerView(self.ledger, bills, totals)
            with tempfile.TemporaryDirectory(prefix="kolibri-logical-audit-") as temporary:
                directory = Path(temporary).resolve()
                for logical, row in selected.items():
                    if "body" not in row:
                        continue
                    body = (self.receipts.root / row["body"]["path"]).read_bytes()
                    name = "raw/" + r.sha(logical.encode()) + ".bin"
                    (directory / name).parent.mkdir(exist_ok=True)
                    (directory / name).write_bytes(body)
                    row["body"] = {**row["body"], "path": name}
                for name in ("events.jsonl", ".lock"):
                    (directory / name).touch()
                receipts = ReceiptView(self.receipts, directory, selected)
                reader = CheckedReader(self.plan, self.freeze, self.plan_hash, ledger, receipts)
                reader._existing_only = True
                reader.checked_report.update(derived_logical_view=True, physical_calls=len(records),
                    physical_unresolved=sum(x["status"] != "received" for x in records.values()),
                    logical_to_physical=mapping, physical_judge_cost_bound_usd=str(ledger.total))
                reader.checked_report.update(terminal_refusal_calls=sorted(refusals),
                    blocking_unresolved=reader.checked_report["unresolved"] - len(refusals),
                    terminal_refusal_holdback_usd=str(sum((totals[c] for c in refusals), Decimal(0))))
                receipts.refusals, receipts.terminal_view = refusals, terminal_view
                ledger.forecast = forecast
                yield reader

    def audit(self):
        with self.logical_reader() as reader:
            return reader.audit()

    def rows(self, *args, **kwargs):
        with self.logical_reader() as reader:
            return reader.rows(*args, **kwargs)

    def fixture_gate(self):
        with self.logical_reader() as reader:
            return reader.fixture_gate()

    def complete(self, *args, **kwargs):
        with self.logical_reader() as reader:
            return reader.complete(*args, **kwargs)

    def main_admission(self, **evidence):
        with self.logical_reader(forecast=True) as reader:
            return reader.main_admission(**evidence)

    def serialization_audit(self, directory):
        with self.logical_reader(terminal_view=False) as reader:
            return reader.serialization_audit(directory)

    def require_resolved(self, channel=None, phases=None):
        with self.ledger._mutex, self.receipts.mutex:
            latest = {}
            for call, row in self.receipts._cache.items():
                logical, ordinal = split_id(call)
                latest[logical] = (row, ordinal)
                if row["channel"] == "judge" and channel != "local":
                    bill = self.ledger._calls.get(call)
                    prod.check(bill is not None and not bill.get("over_reservation"), "Missing/overrun physical reservation")
            prod.check(set(self.ledger._calls) == {c for c, x in self.receipts._cache.items() if x["channel"] == "judge"},
                       "Orphan physical reservation")
            for logical, (row, ordinal) in latest.items():
                if channel is not None and row["channel"] != channel or phases is not None and row["phase"] not in phases:
                    continue
                if row["status"] == "received":
                    continue
                if refusal_missing(row, self.ledger._calls.get(row["call_id"]), self.receipts, self.plan) is not None:
                    continue
                prod.check(ordinal < 2 and eligible(row, self.ledger._calls.get(row["call_id"]), self.receipts)
                           and (self._retry_current is None or self._retry_current == logical),
                           "Pending, nontransport or exhausted request blocks dispatch")

    def _exchange(self, call_id, request, phase, metadata, channel, sender, spec):
        if channel != "judge":
            return super()._exchange(call_id, request, phase, metadata, channel, sender, spec)
        with self._channel_locks["judge"]:
            self._retry_current = call_id
            try:
                for ordinal in range(3):
                    physical = call_id if ordinal == 0 else call_id + SUFFIX + str(ordinal)
                    meta = retry_meta(metadata, call_id, ordinal, self.operational_freeze)
                    existing = self.receipts.existing(physical)
                    if existing is not None:
                        prod.check(existing["request"] == request and existing["phase"] == phase
                                   and existing["metadata"] == {**meta, "freeze": self.freeze, "plan_sha256": self.plan_hash},
                                   "Existing physical attempt changed")
                        if existing["status"] == "received":
                            prod.check(not self.ledger.existing(physical).get("over_reservation"),
                                       "Judge receipt exceeded its reservation")
                            return existing["projection"]
                        missing = refusal_missing(existing, self.ledger.existing(physical), self.receipts, self.plan)
                        if missing is not None:
                            return missing
                        prod.check(eligible(existing, self.ledger.existing(physical), self.receipts),
                                   "Prior request is not retryable")
                        continue
                    prod.check(not self.stop.is_set(), "External stop blocks judge dispatch")
                    if ordinal:
                        self.sleep(BACKOFF[ordinal - 1])
                    prod.check(not self.stop.is_set(), "External stop blocks judge dispatch")
                    self.require_resolved(channel="judge")
                    stop_revision = self.stop.revision()
                    try:
                        result = super()._exchange(physical, request, phase, meta, channel, sender, spec)
                        prod.check(not self.ledger.existing(physical).get("over_reservation"),
                                   "Judge receipt exceeded its reservation")
                        return result
                    except Halted:
                        row = self.receipts.existing(physical)
                        if row is not None:
                            missing = refusal_missing(row, self.ledger.existing(physical), self.receipts, self.plan)
                            if missing is not None:
                                self.stop.clear_failure(stop_revision)
                                return missing
                        if row is None or not eligible(row, self.ledger.existing(physical), self.receipts):
                            raise
                        # Frozen receipt handling calls set once. Any other
                        # set/clear since dispatch is external and stays binding.
                        if not self.stop.clear_failure(stop_revision):
                            raise
                self.stop.set()
                raise Halted("Three physical judge attempts exhausted; label remains missing")
            finally:
                self._retry_current = None


def build_plan(worker_freeze):
    prod.check(isinstance(worker_freeze, str) and re.fullmatch(r"[0-9a-f]{40}", worker_freeze)
               and worker_freeze not in (adapter.A1_FREEZE, adapter.a1.ORIGINAL_FREEZE),
               "Full A2 worker freeze required")
    prior = adapter.verify()
    return {"schema": "kolibri-judge-transport-v1", "worker_freeze": worker_freeze,
            "scientific_plan_sha256": adapter.a1.ORIGINAL_PLAN_SHA,
            "a2_amendment_sha256": protocol.sha(protocol.ROOT / adapter.AMENDMENT),
            "source_hashes": {name: protocol.sha(protocol.ROOT / name) for name in SOURCES},
            "input_hashes": {protocol.PLAN: adapter.a1.ORIGINAL_PLAN_SHA,
                             adapter.AMENDMENT: protocol.sha(protocol.ROOT / adapter.AMENDMENT)},
            "additional_attempts": 2, "backoff_seconds": list(BACKOFF), "deadline_seconds_per_attempt": 600,
            "phases": ["fixtures", "screen", "main"], "judges_only": True,
            "exhaustion": "halt; retain missing label and all charges", "generation_retries": 0,
            "unknown_charges_retained": True, "all_physical_costs_in_forecast": True,
            "terminal_refusal": "Azure auto-tier content_filter; exact identity; zero tokens/cost; preserve full reservation",
            "refusal_policy_basis": "Known sibling-study receipt shape; activate before first Kolibri judgment",
            "refusal_retry": False, "refusal_is_missing_not_negative": True,
            "original_worker_runtime_binding_retained": True, "new_budget_usd": "0",
            "prior_cheap_usd": prior["predecessor"]["cost_usd"]}


def verify(path, freeze=None):
    prod.check(Path(path).resolve() == (protocol.ROOT / PLAN).resolve(), "Canonical transport plan required")
    value = prod.load(path)
    prod.check(value == build_plan(value["worker_freeze"]), "Transport plan or source binding differs")
    if freeze is not None:
        adapter.verify(value["worker_freeze"])
        protocol.verify(protocol.ROOT / protocol.PLAN, freeze)
        for name, digest in {**value["source_hashes"], **value["input_hashes"], PLAN: protocol.sha(path)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(r.sha(body) == digest, "Transport source absent from pushed operational freeze")
    return value


def transport_binding(plan, freeze):
    return {"schema": "kolibri-judge-transport-v1", "operational_freeze": freeze,
            "worker_freeze": plan["worker_freeze"], "transport_plan_sha256": protocol.digest(plan)}


@contextmanager
def saved_runner(root, plan, plan_hash, amendment, transport, freeze):
    """Audit disposable copies, never create locks in the original evidence."""
    collection = root / "collection"
    worker_freeze = transport["worker_freeze"]
    prod.check(prod.load(collection / "runtime.json") == prod.binding(plan, worker_freeze, plan_hash)
               and protocol.sha(collection / "PLAN.json") == plan_hash
               and (collection / "AMENDMENT.json").read_bytes() == (protocol.ROOT / adapter.AMENDMENT).read_bytes()
               and prod.load(collection / "JUDGE_TRANSPORT.json") == transport,
               "Saved science/worker/transport binding differs")
    with tempfile.TemporaryDirectory(prefix="kolibri-transport-audit-") as temporary:
        destination = Path(temporary).resolve()
        for name in ("http", "judges"):
            for path in [collection / name, *(collection / name).rglob("*")]:
                _no_symlinks(path)
            shutil.copytree(collection / name, destination / name)
        with Ledger(destination / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                r.ReceiptJournal(destination / "http", worker_freeze, plan_hash) as receipts:
            prod.check(receipts.decision("judge_transport") == transport_binding(transport, freeze),
                       "Saved operational freeze differs")
            yield Runner(plan, worker_freeze, plan_hash, ledger, receipts, amendment=amendment,
                         transport_plan=transport, operational_freeze=freeze)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Print candidate only; never writes a plan")
    parser.add_argument("--freeze", help="Separate pushed judge operational freeze, not the A2 worker freeze")
    parser.add_argument("--worker-freeze", help="Required for --build: pushed A2 controller/worker freeze")
    parser.add_argument("--phase", choices=prod.PHASES, default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-dir", type=Path, help="Read-only audit only")
    parser.add_argument("--tokenizer-dir", type=Path, help="Read-only derived audit only")
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.build:
            prod.check(not args.execute and args.phase == "audit" and args.freeze is None,
                       "Candidate generation cannot execute")
            print(protocol.canonical(build_plan(args.worker_freeze)))
            return 0
        prod.check(args.execute == (args.phase != "audit"), "Non-audit phases require --execute")
        prod.check(args.tokenizer_dir is None or args.phase == "audit", "Tokenizer audit is offline only")
        prod.check(not args.abort or args.phase == "stop-server", "Abort is cleanup only")
        prod.check(not args.execute or args.run_dir is None, "Execution root cannot change")
        prod.check(isinstance(args.freeze, str) and re.fullmatch(r"[0-9a-f]{40}", args.freeze),
                   "Full judge operational freeze required")
        transport = verify(protocol.ROOT / PLAN, args.freeze if args.execute and args.phase != "stop-server" else None)
        worker_freeze = transport["worker_freeze"]
        prod.check(args.worker_freeze is None or args.worker_freeze == worker_freeze, "A2 worker freeze changed")
        amendment = adapter.verify()
        path = protocol.ROOT / protocol.PLAN
        plan, plan_hash = protocol.verify(path), protocol.sha(path)
        root = args.run_dir.absolute() if args.run_dir else adapter.root()
        _no_symlinks(root)
        if not args.execute:
            with saved_runner(root, plan, plan_hash, amendment, transport, args.freeze) as runner:
                result = runner.serialization_audit(args.tokenizer_dir) if args.tokenizer_dir else runner.audit()
        else:
            prod.check(plan["launch_authorized"] and not plan["metadata_blockers"], "Science plan not executable")
            prod.check(args.phase == "stop-server" or args.reconciliation is not None, "Live reconciliation required")
            record = None if args.phase == "stop-server" else prod.reconciliation(
                plan, prod.load(args.reconciliation), datetime.now(timezone.utc))
            collection = root / "collection"
            with Ledger(collection / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                    r.ReceiptJournal(collection / "http", worker_freeze, plan_hash) as receipts:
                binding = transport_binding(transport, args.freeze)
                if receipts.decision("judge_transport") is None:
                    prod.check(not ledger.rows(), "Transport activation must precede first paid judgment")
                    receipts.append("decision", {"name": "judge_transport", "value": binding})
                prod.check(receipts.decision("judge_transport") == binding, "Operational freeze changed")
                runner = Runner(plan, worker_freeze, plan_hash, ledger, receipts, amendment=amendment,
                                transport_plan=transport, operational_freeze=args.freeze, _freeze_verified=True)
                write_once(collection / "runtime.json", prod.binding(plan, worker_freeze, plan_hash))
                for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", adapter.AMENDMENT),
                                     ("JUDGE_TRANSPORT.json", PLAN)):
                    a2.save_bytes(collection / name, (protocol.ROOT / source).read_bytes())
                if args.phase != "stop-server":
                    runner.guard = adapter.StudyGuard(root, plan, worker_freeze, plan_hash, ledger, amendment=amendment)
                    runner.guard.state(running=args.phase in prod.GENERATION)
                    launch = {"phase": args.phase, "reconciliation": record, **binding,
                              "plan_sha256": plan_hash, "http_head": receipts.events[-1]["sha256"]}
                    write_once(collection / "admissions" / (protocol.digest(launch) + ".json"), launch)
                if args.phase in prod.GENERATION:
                    prod.check(type(args.port) is int and 1 <= args.port <= 65535, "Loopback tunnel port required")
                    runner.local_sender = r.http_sender(
                        f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
                if args.phase in prod.JUDGING:
                    runner.sender = r.http_sender(ENDPOINT, timeout_seconds=600, api_key=prod.local_key(args.env_file))
                result = prod.phase(runner, args.phase, root, abort=args.abort)
        print(protocol.canonical(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Kolibri judge transport halted; all evidence/costs retained. Parent owns cleanup.\n")


if __name__ == "__main__":
    raise SystemExit(main())
