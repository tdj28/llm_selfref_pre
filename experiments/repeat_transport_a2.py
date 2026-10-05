"""Bounded identical judge transport retries; immutable physical accounting."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from experiments import repeat_funding_a1 as funding
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.providers import TransportError, parse_result, receipt_cost, reservation
from experiments.openrouter_swap.runner import write_once
from experiments.repeated_swap import protocol as science, production
from experiments.repeated_swap.runner import Runner as OriginalRunner, privacy
from experiments.repeated_swap.transport import live_sender

ROOT = Path(__file__).resolve().parents[1]
A1_FREEZE = "ce07d52a1fed2ec530b6e31c8670c8f3fb8597bb"
DIRECTORY = "data/repeated_swap/transport_a2_20261005"
PLAN = DIRECTORY + "/PLAN.json"
NEW_SOURCES = ("experiments/repeat_transport_a2.py", "tests/test_repeat_transport_a2.py",
               "docs/REPEATED_SWAP_TRANSPORT_A2_20261005.md")
PREFIX = {"bytes": 4775467, "sha256": "2f09ba9b8a7ac4176897550194ab127a0523eca4ad898f5a96cb359adc01be88", "calls": 443}
KNOWN_FAILURE = "judge:repeated-swap-v1-20261004-main-gemini-03-final-SH-draw-2:astra:structured:a0"
KNOWN_EVENT = {"seq": 864, "sha256": "e0bf7168f8d8e511dead165cb43239197ed3c5c4f2c4745faccfb5a4a072af03"}
BACKOFF = (2, 5)
SUFFIX = ":transport-a2-r"


def split_id(call_id):
    if SUFFIX not in call_id:
        return call_id, 0
    logical, ordinal = call_id.rsplit(SUFFIX, 1)
    if not logical.startswith("judge:") or ordinal not in ("1", "2"):
        raise Halted("Invalid physical transport retry ID")
    return logical, int(ordinal)


def eligible(row):
    raw = row.get("raw")
    if raw is not None and (not isinstance(raw, dict) or set(raw) != {"transport_status_code"}):
        return False
    status = None if raw is None else raw["transport_status_code"]
    transient = status is None or type(status) is int and (status in (0, 200, 408, 425, 429) or 500 <= status <= 599)
    return (transient and row["metadata"].get("kind") == "judge" and row["phase"] == "main"
            and row["status"] == "unresolved" and row.get("error_type") == "TransportError"
            and row.get("cost_known") is False and row.get("reported_cost_usd") is None
            and not row.get("over_reservation") and row["cost_usd"] == row["reservation_usd"])


def retry_meta(metadata, logical, ordinal, freeze):
    return {**metadata, **({"transport_retry": {"logical_call_id": logical, "ordinal": ordinal,
                                               "operational_freeze": freeze}} if ordinal else {})}


class Policy:
    """Incremental replay in durable settlement order; stop decisions latch."""
    def __init__(self, freeze):
        self.freeze, self.cursor = freeze, 0
        self.calls, self.streaks = {}, {}
        self.failures, self.exhausted, self.stop_reason = 0, [], None

    def advance(self, events):
        for event in events[self.cursor:]:
            self.cursor += 1
            row = event["data"]
            if event["kind"] == "binding":
                continue
            call_id = row["call_id"]
            logical, ordinal = split_id(call_id)
            if event["kind"] == "reserve":
                if ordinal:
                    base = self.calls.get(logical)
                    previous = self.calls.get(logical if ordinal == 1 else logical + SUFFIX + "1")
                    if base is None or previous is None or not eligible(previous):
                        raise Halted("Retry lacks a preceding eligible transport failure")
                    if (row["metadata"] != retry_meta(base["metadata"], logical, ordinal, self.freeze)
                            or any(row[k] != base[k] for k in ("request", "request_sha256", "reservation_usd", "phase"))):
                        raise Halted("Physical retry differs from the identical logical request")
                elif "transport_retry" in row["metadata"]:
                    raise Halted("Retry metadata on an original call")
                self.calls[call_id] = row
                continue
            if event["kind"] != "settle" or call_id not in self.calls:
                raise Halted("Unexpected transport-policy journal event")
            row = {**self.calls[call_id], **row}
            self.calls[call_id] = row
            if row.get("over_reservation") or row["status"] != "settled" and not eligible(row):
                self.stop_reason = self.stop_reason or "nontransport_or_accounting_failure"
                continue
            if row["metadata"].get("kind") != "judge":
                continue
            endpoint = science.canonical({"model": row["request"]["model"], "provider": row["request"]["provider"]["only"]})
            if eligible(row):
                self.failures += 1
                if self.failures > 16:
                    self.stop_reason = self.stop_reason or "seventeenth_physical_transport_failure"
                if ordinal == 2:
                    self.exhausted.append(logical)
                    self.streaks[endpoint] = self.streaks.get(endpoint, 0) + 1
                    if self.streaks[endpoint] >= 3:
                        self.stop_reason = self.stop_reason or "three_consecutive_exhausted_judge_requests"
            else:
                self.streaks[endpoint] = 0
        return self.summary()

    def summary(self):
        return {"physical_transport_failures": self.failures, "exhausted_logical_calls": list(self.exhausted),
                "endpoint_exhaustion_streaks": dict(self.streaks), "stop_reason": self.stop_reason}


def policy_state(events, operational_freeze):
    return Policy(operational_freeze).advance(events)


class LogicalView:
    """Read-only selected receipts, with physical charges and mapping retained."""
    def __init__(self, ledger, operational_freeze):
        self.ledger, self.mapping, self.records = ledger, {}, {}
        with ledger._mutex:
            self.policy = policy_state(ledger._events, operational_freeze)
            rows = ledger.rows()
        for row in rows:
            logical, ordinal = split_id(row["call_id"])
            self.mapping.setdefault(logical, []).append(row["call_id"])
            projected = deepcopy(row)
            projected["call_id"] = logical
            projected["metadata"].pop("transport_retry", None)
            self.records[logical] = projected

    def existing(self, call_id):
        return deepcopy(self.records.get(call_id))

    def rows(self):
        return deepcopy(list(self.records.values()))

    def spent(self):
        return self.ledger.spent()


class RetryLedger(funding.FundingLedger):
    def enable_policy(self, operational_freeze):
        with self._mutex:
            self.transport_policy = Policy(operational_freeze)
            self.check_policy()

    def check_policy(self):
        with self._mutex:
            if not hasattr(self, "transport_policy"):
                raise Halted("Transport policy not enabled")
            state = self.transport_policy.advance(self._events)
            if state["stop_reason"]:
                raise Halted("Transport stop: " + state["stop_reason"])
            return state

    def reserve(self, *args, **kwargs):
        with self._mutex:
            self.check_policy()
            return super().reserve(*args, **kwargs)


class MissingTransportJudge(Halted):
    pass


class RetryRunner(OriginalRunner):
    def __init__(self, *args, operational_freeze, sleep=time.sleep, **kwargs):
        super().__init__(*args, **kwargs)
        self.operational_freeze, self.sleep = operational_freeze, sleep

    def logical_runner(self):
        return OriginalRunner(self.plan, self.freeze, self.plan_hash,
                              LogicalView(self.ledger, self.operational_freeze))

    def require_resolved(self):
        self.ledger.check_policy()
        for row in self.ledger.rows():
            if row.get("over_reservation") or row["status"] != "settled" and not eligible(row):
                raise Halted("Unknown pending, nontransport or accounting failure")

    def audit(self):
        runner = self.logical_runner()
        view = runner.ledger
        report = runner.audit()
        return {**report, "logical_calls": report["calls"], "physical_calls": len(self.ledger.rows()),
                "physical_unresolved": sum(r["status"] != "settled" for r in self.ledger.rows()),
                "transport_policy": view.policy, "logical_to_physical": view.mapping}

    def rows(self, phase, models=None):
        return self.logical_runner().rows(phase, models)

    def judge(self, item_id, response, judge, instrument, phase):
        try:
            return super().judge(item_id, response, judge, instrument, phase)
        except MissingTransportJudge:
            return {"item_id": item_id, "judge": judge, "instrument": instrument,
                    "status": "transport_failed_missing", "raw_text": None}

    def call(self, call_id, spec, request, phase, metadata):
        if metadata["kind"] != "judge" or phase != "main":
            return super().call(call_id, spec, request, phase, metadata)
        request = deepcopy(request)
        request["provider"].update(privacy("judge"))
        metadata = {**metadata, "freeze": self.freeze, "plan_sha256": self.plan_hash}
        for ordinal in range(3):
            physical_id = call_id if not ordinal else call_id + SUFFIX + str(ordinal)
            physical_meta = retry_meta(metadata, call_id, ordinal, self.operational_freeze)
            row = self.ledger.existing(physical_id)
            if row is not None:
                if row["request"] != request or row["metadata"] != physical_meta or row["phase"] != phase:
                    raise Halted("Cached physical attempt identity changed")
                if row["status"] == "settled" and not row.get("over_reservation"):
                    return parse_result(spec, row["raw"])
                if not eligible(row):
                    raise Halted("Prior failure is not an eligible judge transport failure")
                continue
            if self.sender is None or self.stop.is_set():
                raise Halted("No dispatch permission")
            if ordinal:
                self.sleep(BACKOFF[ordinal - 1])
            if self.stop.is_set():
                raise Halted("Dispatch stopped during backoff")
            self.ledger.reserve(physical_id, request, reservation(spec, request), phase, physical_meta)
            raw, cost = None, None
            try:
                raw = self.sender(request)
                cost = receipt_cost(spec, raw)
                if cost is None:
                    raise Halted("Usage unavailable")
                result = parse_result(spec, raw)
            except Exception as error:
                if raw is None and getattr(error, "status_code", None) is not None:
                    raw = {"transport_status_code": error.status_code}
                row = self.ledger.settle(physical_id, raw, cost, error=error)
                if not isinstance(error, TransportError) or not eligible(row):
                    self.stop.set()
                    raise Halted("Nonretryable judge transport, identity or accounting failure") from None
                self.ledger.check_policy()
                continue
            row = self.ledger.settle(physical_id, raw, cost)
            if row["status"] != "settled" or row.get("over_reservation"):
                self.stop.set()
                raise Halted("Judge accounting failure")
            self.ledger.check_policy()
            return result
        self.ledger.check_policy()
        raise MissingTransportJudge("All three physical transport attempts failed; label remains missing")


def prior_plan():
    plan = funding.verify(ROOT / funding.PLAN)
    for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
        if funding.digest(funding.git_blob(A1_FREEZE, name)) != expected:
            raise Halted("Frozen A1 source changed")
    if funding.git_blob(A1_FREEZE, funding.PLAN) != (ROOT / funding.PLAN).read_bytes():
        raise Halted("Frozen A1 plan changed")
    return plan


def build_plan():
    prior = prior_plan()
    return {"schema": "repeated-transport-a2-v1", "original_science_freeze": funding.OLD_FREEZE,
            "funding_a1_freeze": A1_FREEZE, "prior_journal_prefix": PREFIX,
            "known_failure": {"call_id": KNOWN_FAILURE, **KNOWN_EVENT},
            "authorization": {"approved": True, "additional_budget_usd": "0",
                              "scope": "Owner explicitly authorizes identical judge transport retries, including the existing failed Astra call"},
            "atomic_cap_usd": "130", "external_holdback_usd": "45",
            "additional_attempts": 2, "backoff_seconds": list(BACKOFF),
            "stop": {"physical_transport_failure_number": 17, "consecutive_exhausted_logical_requests_per_endpoint": 3,
                     "order": "durable settlement order; successful judge transport resets endpoint streak; stops latch"},
            "science_changed": False, "failed_attempts_and_reservations_retained": True,
            "completed_outputs_retried": False, "existing_schema_retry_rule": "unchanged",
            "unknown_200_cause": "Frozen sender discarded the body; status 200 alone cannot identify why transport failed",
            "source_hashes": {**prior["source_hashes"], **{name: science.sha(ROOT / name) for name in NEW_SOURCES}},
            "input_hashes": {**prior["input_hashes"], funding.PLAN: science.sha(ROOT / funding.PLAN)}}


def verify(path, freeze=None, *, require_pushed=False):
    path = Path(path).resolve()
    if path != (ROOT / PLAN).resolve():
        raise Halted("Use the canonical A2 plan")
    plan = json.loads(path.read_bytes())
    if science.canonical(plan) != science.canonical(build_plan()):
        raise Halted("A2 plan or source closure changed")
    if freeze is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", freeze) or freeze in (A1_FREEZE, funding.OLD_FREEZE):
            raise Halted("Fresh full operational freeze required")
        for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
            if funding.digest(funding.git_blob(freeze, name)) != expected:
                raise Halted("A2 source absent from operational freeze: " + name)
        if funding.git_blob(freeze, PLAN) != path.read_bytes():
            raise Halted("A2 plan absent from operational freeze")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise Halted("Checkout must equal operational freeze")
        if subprocess.run(["git", "merge-base", "--is-ancestor", A1_FREEZE, freeze], cwd=ROOT, check=False).returncode:
            raise Halted("A2 must descend from A1")
    if require_pushed:
        ref = "refs/heads/" + science.BRANCH
        if freeze is None or subprocess.check_output(["git", "ls-remote", "origin", ref], cwd=ROOT, text=True).split() != [freeze, ref]:
            raise Halted("A2 freeze must be pushed before dispatch")
    return plan


def verify_prefix(root, *, initial_only=False):
    root = Path(root)
    _no_symlinks(root / "raw/events.jsonl")
    raw = (root / "raw/events.jsonl").read_bytes()
    prefix = raw[:PREFIX["bytes"]]
    if funding.digest(prefix) != PREFIX["sha256"] or initial_only and len(raw) != len(prefix):
        raise Halted("A1 failure prefix changed or A2 dispatched before binding")
    events = read_events(root / "raw/events.jsonl")
    anchored = events[:887]
    if sum(e["kind"] == "reserve" for e in anchored) != PREFIX["calls"]:
        raise Halted("A1 failure call count changed")
    event = events[KNOWN_EVENT["seq"] - 1]
    if event["sha256"] != KNOWN_EVENT["sha256"] or event["data"]["call_id"] != KNOWN_FAILURE:
        raise Halted("Known failure anchor changed")
    return funding.verify_prefix(root, funding.original_plan())


def require_completion_funding(ledger, admission, limit, operational_freeze):
    # A failed physical attempt consumes money but completes no logical work.
    view = LogicalView(ledger, operational_freeze)
    completed = sum((funding.amount(r["cost_usd"]) for r in view.rows()
                     if r["status"] == "settled"), Decimal(0))
    initial = funding.amount(admission["observed_spend_usd"])
    if completed < initial:
        raise Halted("Completed logical spending is below the initial cost anchor")
    remaining = max(Decimal(0), funding.amount(admission["remaining_forecast_usd"]) - (completed - initial))
    required = ledger.spent() + remaining
    if required > limit:
        raise Halted("Fresh balance does not cover completion plus transport overhead")
    return {"physical_spent_and_reserved_usd": str(ledger.spent()),
            "completed_logical_spend_usd": str(completed),
            "transport_overhead_or_unresolved_usd": str(ledger.spent() - completed),
            "remaining_forecast_usd": str(remaining), "forecast_total_usd": str(required),
            "funded_limit_usd": str(limit), "pass": True}


def execute(root, amendment, freeze, key):
    if amendment != verify(ROOT / PLAN, freeze, require_pushed=True):
        raise Halted("Execution amendment differs from its pushed freeze")
    root = Path(root)
    if root.resolve() != production.root_path().resolve():
        raise Halted("A2 must use the original shared ledger")
    operational = root / "transport_a2"
    _no_symlinks(operational)
    with RetryLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        admission = verify_prefix(root, initial_only=not (operational / "runtime.json").exists())
        ledger.enable_policy(freeze)
        runner = RetryRunner(funding.original_plan(), funding.OLD_FREEZE, funding.OLD_PLAN_SHA,
                             ledger, operational_freeze=freeze)
        runner.require_resolved()
        runner.audit()
        binding = {"original_science_freeze": funding.OLD_FREEZE, "original_plan_sha256": funding.OLD_PLAN_SHA,
                   "funding_a1_freeze": A1_FREEZE, "actual_operational_freeze": freeze,
                   "amendment_plan_sha256": science.sha(ROOT / PLAN)}
        write_once(operational / "runtime.json", binding)
        launch = operational / "launches" / uuid.uuid4().hex
        def journal():
            raw = (root / "raw/events.jsonl").read_bytes()
            return {"sha256": funding.digest(raw), "bytes": len(raw), "calls": len(ledger.rows())}
        write_once(launch / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(),
                                          "journal_before": journal(), "outcome_selection": False})
        def record(value):
            write_once(launch / "funding" / (uuid.uuid4().hex + ".json"),
                       {**value, **binding, "utc": datetime.now(timezone.utc).isoformat()})
        complete = False
        try:
            ledger.enable_funding(lambda: production.account_balance(key), record)
            write_once(launch / "completion_forecast.json",
                       require_completion_funding(ledger, admission, ledger.stage_limit, freeze))
            runner.sender = live_sender(key)
            runner.run_blocks("main")
            runner.require_complete()
            report = runner.audit()
            write_once(launch / "audit.json", report)
            complete = True
            return report
        finally:
            write_once(launch / "finish.json", {**binding, "complete": complete,
                       "spent_and_reserved_usd": str(ledger.spent()), "journal_after": journal(),
                       "transport_policy": policy_state(ledger._events, freeze)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args(argv)
    if args.build and args.execute or args.execute and not args.freeze:
        parser.error("Build, pushed freeze and execution are separate steps")
    root = production.root_path()
    if args.build:
        verify_prefix(root, initial_only=True)
        write_once(ROOT / PLAN, build_plan())
    amendment = verify(ROOT / PLAN, args.freeze)
    if not args.execute:
        print(science.canonical({"plan_sha256": science.sha(ROOT / PLAN), "source_files": len(amendment["source_hashes"]), "network_calls": 0}))
        return
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise Halted("OpenRouter credential unavailable")
    print(science.canonical(execute(root, amendment, args.freeze, key)), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("A2 stopped; all physical attempts and reservations retained.") from None
