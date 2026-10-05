"""Keep verified provider refusals missing without aborting unrelated judging."""
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
import uuid

from experiments import repeat_transport_a2 as a2
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.providers import parse_result, receipt_cost
from experiments.openrouter_swap.runner import write_once
from experiments.repeated_swap.runner import Runner as OriginalRunner, privacy

funding, science, production = a2.funding, a2.science, a2.production
ROOT = Path(__file__).resolve().parents[1]
A2_FREEZE = "a08e271caf2a633426882cbd9705f95bfe653e3b"
PLAN = "data/repeated_swap/refusal_a3_20261005/PLAN.json"
SOURCES = ("experiments/repeat_refusal_a3.py", "tests/test_repeat_refusal_a3.py",
           "docs/REPEATED_SWAP_REFUSAL_A3_20261005.md")
PREFIX = {"bytes": 14537377, "events": 2521, "calls": 1260,
          "sha256": "eaac1ee5b6798077c4fe18052697f989b9d832798af704f0f5a628640bf8a0c9"}
REFUSAL = "judge:repeated-swap-v1-20261004-main-gemini-07-final-SH-draw-3:astra:structured:a0"
REFUSAL_EVENT = {"seq": 2500, "sha256": "ee4f2b6930054db827a679f7b1eaa74f1c71c43ed75d909c5249e19a8e410f07"}


def terminal_refusal(row, plan):
    """Recognize a missing filter receipt, never a valid default-tier answer."""
    try:
        meta, raw = row["metadata"], row["raw"]
        spec = plan["judges"][meta["judge"]]
        if (meta["kind"] != "judge" or row["phase"] != "main" or row["status"] != "unresolved"
                or row["error_type"] != "ReceiptError" or row["cost_known"] is not False
                or row["over_reservation"] or row["cost_usd"] != row["reservation_usd"]
                or row["reported_cost_usd"] != "0" or not isinstance(raw, dict)
                or raw.get("service_tier") != "auto" or raw.get("error") is not None
                or not isinstance(raw.get("id"), str) or not raw["id"].strip()
                or raw.get("model") not in [spec["id"], *spec.get("model_aliases", [])]
                or raw.get("provider") != spec["provider_name"]):
            return False
        choices, usage = raw["choices"], raw["usage"]
        if (not isinstance(choices, list) or len(choices) != 1
                or any(type(usage.get(k)) is not int or usage[k] != 0
                       for k in ("prompt_tokens", "completion_tokens", "total_tokens"))
                or funding.amount(usage.get("cost")) != 0 or receipt_cost(spec, raw) != 0):
            return False
        choice = choices[0]
        message = choice["message"]
        return (choice.get("finish_reason") in ("content_filter", "refusal")
                and choice.get("native_finish_reason") in (None, "content_filter", "refusal")
                and message.get("role") == "assistant"
                and isinstance(message.get("content"), str) and bool(message["content"].strip())
                and (message.get("refusal") is None or isinstance(message["refusal"], str)))
    except (KeyError, TypeError, ValueError, AttributeError, Halted):
        return False


def policy_state(events, freeze, plan):
    calls = {}
    for event in events:
        if event["kind"] != "binding":
            row = event["data"]
            calls[row["call_id"]] = {**calls.get(row["call_id"], {}), **row}
    refused = {c for c, row in calls.items() if terminal_refusal(row, plan)}
    projected = []
    for event in events:
        row = event["data"]
        if row.get("call_id") in refused:
            continue
        if event["kind"] == "reserve" and "transport_retry" in row["metadata"]:
            actual = row["metadata"]["transport_retry"]["operational_freeze"]
            expected = A2_FREEZE if event["seq"] <= PREFIX["events"] else freeze
            if actual != expected:
                raise Halted("Transport retry operational epoch differs")
            # Only the legacy policy view normalizes the epoch; raw receipts do not.
            event = deepcopy(event)
            event["data"]["metadata"]["transport_retry"]["operational_freeze"] = A2_FREEZE
        projected.append(event)
    state = a2.policy_state(projected, A2_FREEZE)
    return {**state, "terminal_refusal_calls": sorted(refused),
            "terminal_refusal_reservations_usd": str(sum((Decimal(calls[c]["cost_usd"]) for c in refused), Decimal(0)))}


class MissingProviderRefusal(Halted):
    pass


class RefusalLedger(a2.RetryLedger):
    def enable_policy(self, freeze, plan):
        self.refusal_freeze, self.refusal_plan = freeze, plan
        self.check_policy()

    def check_policy(self):
        with self._mutex:
            if not hasattr(self, "refusal_plan"):
                raise Halted("A3 policy not enabled")
            state = policy_state(self._events, self.refusal_freeze, self.refusal_plan)
            if state["stop_reason"]:
                raise Halted("Transport stop: " + state["stop_reason"])
            return state

    def settle(self, *args, **kwargs):
        row = super().settle(*args, **kwargs)
        if terminal_refusal(row, self.refusal_plan):
            self.check_policy()
            # Raised after the durable failure settlement, before A2 sets stop.
            raise MissingProviderRefusal("Provider refusal retained as missing; never retry")
        return row


class LogicalView(a2.LogicalView):
    def __init__(self, ledger, freeze, plan):
        self.ledger, self.mapping, self.records = ledger, {}, {}
        with ledger._mutex:
            self.policy = policy_state(ledger._events, freeze, plan)
            rows = ledger.rows()
        for row in rows:
            logical, _ = a2.split_id(row["call_id"])
            self.mapping.setdefault(logical, []).append(row["call_id"])
            row["call_id"] = logical
            row["metadata"].pop("transport_retry", None)
            self.records[logical] = row


class RefusalRunner(a2.RetryRunner):
    def logical_runner(self):
        return OriginalRunner(self.plan, self.freeze, self.plan_hash,
                              LogicalView(self.ledger, self.operational_freeze, self.plan))

    def require_resolved(self):
        self.ledger.check_policy()
        for row in self.ledger.rows():
            if row.get("over_reservation") or (row["status"] != "settled"
                    and not a2.eligible(row) and not terminal_refusal(row, self.plan)):
                raise Halted("Unknown pending, identity or accounting failure")

    def judge(self, item_id, response, judge, instrument, phase):
        try:
            return super().judge(item_id, response, judge, instrument, phase)
        except MissingProviderRefusal:
            return {"item_id": item_id, "judge": judge, "instrument": instrument,
                    "status": "provider_refusal_missing", "raw_text": None}

    def call(self, call_id, spec, request, phase, metadata):
        if metadata["kind"] == "judge" and phase == "main":
            expected_request = deepcopy(request)
            expected_request["provider"].update(privacy("judge"))
            base_meta = {**metadata, "freeze": self.freeze, "plan_sha256": self.plan_hash}
            for ordinal in range(3):
                physical = call_id if not ordinal else call_id + a2.SUFFIX + str(ordinal)
                row = self.ledger.existing(physical)
                if row is None:
                    break
                epoch = row["metadata"].get("transport_retry", {}).get("operational_freeze", self.operational_freeze)
                if (epoch not in (A2_FREEZE, self.operational_freeze) or row["request"] != expected_request
                        or row["phase"] != phase or row["metadata"] != a2.retry_meta(base_meta, call_id, ordinal, epoch)):
                    raise Halted("Cached judge request or epoch changed")
                if terminal_refusal(row, self.plan):
                    raise MissingProviderRefusal("Retained provider refusal is never retried")
                if row["status"] == "settled" and not row.get("over_reservation"):
                    return parse_result(spec, row["raw"])
        return super().call(call_id, spec, request, phase, metadata)


def build_plan():
    previous = a2.verify(ROOT / a2.PLAN)
    for name, expected in {**previous["source_hashes"], **previous["input_hashes"]}.items():
        if funding.digest(funding.git_blob(A2_FREEZE, name)) != expected:
            raise Halted("Frozen A2 input changed")
    if funding.git_blob(A2_FREEZE, a2.PLAN) != (ROOT / a2.PLAN).read_bytes():
        raise Halted("Frozen A2 plan changed")
    return {"schema": "repeated-refusal-a3-v1", "a2_freeze": A2_FREEZE,
            "original_science_freeze": funding.OLD_FREEZE, "prior_prefix": PREFIX,
            "known_refusal": {"call_id": REFUSAL, **REFUSAL_EVENT},
            "authorization": {"approved": True, "scope": "Preserve provider refusals as missing; continue unrelated planned requests"},
            "refusal_retry": False, "science_changed": False,
            "atomic_cap_usd": "130", "external_holdback_usd": "45",
            "source_hashes": {**previous["source_hashes"], **{n: science.sha(ROOT / n) for n in SOURCES}},
            "input_hashes": {**previous["input_hashes"], a2.PLAN: science.sha(ROOT / a2.PLAN)}}


def verify(path, freeze=None, *, pushed=False):
    path = Path(path)
    if path.resolve() != (ROOT / PLAN).resolve():
        raise Halted("Use the canonical A3 plan")
    plan = json.loads(path.read_bytes())
    if science.canonical(plan) != science.canonical(build_plan()):
        raise Halted("A3 source or plan changed")
    if freeze is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", freeze) or freeze == A2_FREEZE:
            raise Halted("Fresh full A3 freeze required")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise Halted("Checkout must equal A3 freeze")
        subprocess.check_call(["git", "merge-base", "--is-ancestor", A2_FREEZE, freeze], cwd=ROOT)
        for name, digest in {**plan["source_hashes"], **plan["input_hashes"]}.items():
            if funding.digest(funding.git_blob(freeze, name)) != digest:
                raise Halted("A3 input absent from freeze")
        if funding.git_blob(freeze, PLAN) != path.read_bytes():
            raise Halted("A3 plan absent from freeze")
    if pushed:
        ref = "refs/heads/" + science.BRANCH
        if freeze is None or subprocess.check_output(["git", "ls-remote", "origin", ref], cwd=ROOT, text=True).split() != [freeze, ref]:
            raise Halted("A3 freeze must be pushed before dispatch")
    return plan


def verify_prefix(root, *, initial_only=False):
    root = Path(root)
    _no_symlinks(root / "raw/events.jsonl")
    raw = (root / "raw/events.jsonl").read_bytes()
    if funding.digest(raw[:PREFIX["bytes"]]) != PREFIX["sha256"] or initial_only and len(raw) != PREFIX["bytes"]:
        raise Halted("A2 refusal prefix changed or A3 began before binding")
    events = read_events(root / "raw/events.jsonl")
    e = events[REFUSAL_EVENT["seq"] - 1]
    if e["sha256"] != REFUSAL_EVENT["sha256"] or e["data"]["call_id"] != REFUSAL:
        raise Halted("Known refusal anchor changed")
    return a2.verify_prefix(root)


def completion_funding(ledger, admission, freeze, plan):
    completed = sum((Decimal(r["cost_usd"]) for r in LogicalView(ledger, freeze, plan).rows()
                     if r["status"] == "settled"), Decimal(0))
    initial = funding.amount(admission["observed_spend_usd"])
    remaining = max(Decimal(0), funding.amount(admission["remaining_forecast_usd"]) - (completed - initial))
    total = ledger.spent() + remaining
    if completed < initial or total > ledger.stage_limit:
        raise Halted("Completion plus retained failure overhead exceeds funded allowance")
    return {"completed_logical_spend_usd": str(completed), "physical_spent_and_reserved_usd": str(ledger.spent()),
            "remaining_forecast_usd": str(remaining), "forecast_total_usd": str(total),
            "funded_limit_usd": str(ledger.stage_limit), "pass": True}


def execute(amendment, freeze, key):
    if amendment != verify(ROOT / PLAN, freeze, pushed=True):
        raise Halted("Execution plan differs from pushed A3 freeze")
    root, plan = production.root_path(), funding.original_plan()
    operational = root / "refusal_a3"
    _no_symlinks(operational)
    with RefusalLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        admission = verify_prefix(root, initial_only=not (operational / "runtime.json").exists())
        ledger.enable_policy(freeze, plan)
        runner = RefusalRunner(plan, funding.OLD_FREEZE, funding.OLD_PLAN_SHA, ledger, operational_freeze=freeze)
        runner.require_resolved(); runner.audit()
        binding = {"original_science_freeze": funding.OLD_FREEZE, "original_plan_sha256": funding.OLD_PLAN_SHA,
                   "a2_operational_freeze": A2_FREEZE, "actual_operational_freeze": freeze,
                   "amendment_plan_sha256": science.sha(ROOT / PLAN)}
        write_once(operational / "runtime.json", binding)
        launch = operational / "launches" / uuid.uuid4().hex
        def journal():
            raw = (root / "raw/events.jsonl").read_bytes()
            return {"bytes": len(raw), "sha256": funding.digest(raw), "calls": len(ledger.rows())}
        write_once(launch / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(), "journal_before": journal()})
        def record(value):
            write_once(launch / "funding" / (uuid.uuid4().hex + ".json"), {**value, **binding, "utc": datetime.now(timezone.utc).isoformat()})
        complete = False
        try:
            ledger.enable_funding(lambda: production.account_balance(key), record)
            write_once(launch / "completion_forecast.json", completion_funding(ledger, admission, freeze, plan))
            runner.sender = a2.live_sender(key)
            runner.run_blocks("main")
            runner.require_complete()
            report = runner.audit()
            write_once(launch / "audit.json", report)
            complete = True
            return report
        finally:
            write_once(launch / "finish.json", {**binding, "inventory_complete": complete,
                       "spent_and_reserved_usd": str(ledger.spent()), "journal_after": journal(),
                       "transport_policy": policy_state(ledger._events, freeze, plan)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args(argv)
    if args.build and args.execute or args.execute and not args.freeze:
        parser.error("Build, freeze and execution are separate steps")
    if args.build:
        verify_prefix(production.root_path(), initial_only=True)
        write_once(ROOT / PLAN, build_plan())
    amendment = verify(ROOT / PLAN, args.freeze)
    if not args.execute:
        print(science.canonical({"plan_sha256": science.sha(ROOT / PLAN), "network_calls": 0}))
        return
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise Halted("OpenRouter credential unavailable")
    print(science.canonical(execute(amendment, args.freeze, key)), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("A3 stopped; refusals, raw receipts and reservations remain preserved.") from None
