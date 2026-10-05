"""Offline release for repeated-study funding A1, retries A2 and refusals A3.

The original failed admission and scientific request metadata remain unchanged.
This adapter is deliberately outside all execution source closures.
"""

import argparse
from bisect import bisect_right
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import gzip
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import RLock

from experiments import repeat_funding_a1 as funding
from experiments import repeat_transport_a2 as a2
from experiments import repeat_refusal_a3 as a3
from experiments.repeated_swap import release as base

p = base.p
ROOT = Path(__file__).resolve().parents[1]
FOLDER = "funding_a1"
DERIVED = base.DERIVED | {"funding_audit.json"}
A2_DERIVED = {"transport_audit.json", "logical_projection.json"}
A2_INPUTS = {"transport_a2/PLAN.json", "transport_a2/runtime.json"}
A3_DERIVED = {"refusal_audit.json", "epoch_timing.json"}
A3_INPUTS = {"refusal_a3/PLAN.json", "refusal_a3/runtime.json"}
FUNDING_INPUTS = {f"{FOLDER}/{name}" for name in (
    "PLAN.json", "FAILED_ADMISSION.json", "runtime.json", "admission.json")}
REQUIRED = base.REQUIRED | {"fixture_gate.json", "admission.json", "funding_audit.json"} | FUNDING_INPUTS
MANIFEST_SCHEMA = "repeated-funding-a1-manifest-v1"
OWN_SOURCES = ("experiments/repeat_funding_release_a1.py", "tests/test_repeat_funding_release_a1.py")


def _time(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    base._check(stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0,
                "UTC receipt timestamp required")
    return stamp


def _ancestor(old, new):
    result = subprocess.run(["git", "--no-replace-objects", "merge-base", "--is-ancestor", old, new],
        cwd=p.ROOT, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=30, check=False)
    return result.returncode == 0


def _launch_path(name):
    return re.fullmatch(r"funding_a1/launches/[0-9a-f]{32}/(?:start|finish)\.json|"
                        r"(?:transport_a2|refusal_a3)/launches/[0-9a-f]{32}/(?:start|finish|completion_forecast|audit)\.json|"
                        r"(?:funding_a1|transport_a2|refusal_a3)/launches/[0-9a-f]{32}/funding/[0-9a-f]{32}\.json", name) is not None


def _inventory(root, *, derived):
    inventory = base._inventory(root)
    required = REQUIRED if derived else REQUIRED - DERIVED
    if (root / "transport_a2").exists():
        required = required | A2_INPUTS | (A2_DERIVED if derived else set())
    if (root / "refusal_a3").exists():
        base._check((root / "transport_a2").is_dir(), "A3 lacks its A2 history")
        required = required | A3_INPUTS | (A3_DERIVED if derived else set())
    base._check(required <= set(inventory)
                and all(n in required or _launch_path(n) for n in inventory), "Unexpected funding release inventory")
    directories = {parent.as_posix() for name in inventory for parent in Path(name).parents}
    base._check(all(not path.is_dir() or path.relative_to(root).as_posix() in directories
                    for path in root.rglob("*")), "Unexpected funding release directory")
    return inventory


def _plans(root):
    scientific, runtime = base._plan(root)
    base._check(runtime["freeze"] == funding.OLD_FREEZE and runtime["plan_sha256"] == funding.OLD_PLAN_SHA,
                "Original scientific freeze changed")
    amended = funding.verify(funding.ROOT / funding.PLAN)
    local_plan = root / FOLDER / "PLAN.json"
    base._check(local_plan.read_bytes() == (funding.ROOT / funding.PLAN).read_bytes(), "Funding plan bytes differ")
    actual = base._load(root / FOLDER / "runtime.json")
    freeze = actual.get("actual_operational_freeze")
    base._check(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze)
                and freeze != runtime["freeze"], "Separate operational freeze required")
    binding = {"original_science_freeze": runtime["freeze"], "original_plan_sha256": runtime["plan_sha256"],
               "actual_operational_freeze": freeze, "amendment_plan_sha256": p.sha(local_plan)}
    base._check(actual == binding and _ancestor(runtime["freeze"], freeze), "Funding runtime or ancestry differs")
    base._check(base._git_blob(freeze, funding.PLAN) == local_plan.read_bytes(), "Frozen funding plan differs")
    for name, expected in {**amended["source_hashes"], **amended["input_hashes"]}.items():
        base._check(base._sha(base._git_blob(freeze, name)) == expected, "Frozen funding source differs")
    old_bytes = (root / "admission.json").read_bytes()
    base._check(old_bytes == (root / FOLDER / "FAILED_ADMISSION.json").read_bytes()
                == base._git_blob(freeze, funding.ANCHOR), "Original failed admission bytes differ")
    old = funding.failed_admission(old_bytes)
    admission = funding.amended_admission(old)
    base._check(admission["pass"] is True and admission == amended["admission"]
                == base._load(root / FOLDER / "admission.json"), "Amended admission differs or did not pass")
    base._check(not set(OWN_SOURCES) & set(amended["source_hashes"]), "Release adapter entered execution closure")
    return scientific, runtime, amended, binding, admission


def _transport_plan(root, funding_binding):
    plan = a2.verify(a2.ROOT / a2.PLAN)
    path = root / "transport_a2/PLAN.json"
    base._check(path.read_bytes() == (a2.ROOT / a2.PLAN).read_bytes(), "Transport plan bytes differ")
    actual = base._load(root / "transport_a2/runtime.json")
    freeze = actual.get("actual_operational_freeze")
    base._check(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze)
                and freeze not in (funding.OLD_FREEZE, a2.A1_FREEZE)
                and funding_binding["actual_operational_freeze"] == a2.A1_FREEZE,
                "Distinct A2 freeze or A1 ancestry binding differs")
    binding = {"original_science_freeze": funding.OLD_FREEZE, "original_plan_sha256": funding.OLD_PLAN_SHA,
               "funding_a1_freeze": a2.A1_FREEZE, "actual_operational_freeze": freeze,
               "amendment_plan_sha256": p.sha(path)}
    base._check(actual == binding and _ancestor(a2.A1_FREEZE, freeze), "Transport runtime or ancestry differs")
    base._check(base._git_blob(freeze, a2.PLAN) == path.read_bytes(), "Frozen transport plan differs")
    for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
        base._check(base._sha(base._git_blob(freeze, name)) == expected, "Frozen transport source differs")
    base._check(not set(OWN_SOURCES) & set(plan["source_hashes"]), "Release adapter entered A2 execution closure")
    return binding


def _refusal_plan(root, transport_binding):
    plan = a3.verify(a3.ROOT / a3.PLAN)
    path = root / "refusal_a3/PLAN.json"
    base._check(path.read_bytes() == (a3.ROOT / a3.PLAN).read_bytes(), "Refusal plan bytes differ")
    actual = base._load(root / "refusal_a3/runtime.json")
    freeze = actual.get("actual_operational_freeze")
    base._check(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze)
                and freeze not in (funding.OLD_FREEZE, a2.A1_FREEZE, a3.A2_FREEZE)
                and transport_binding["actual_operational_freeze"] == a3.A2_FREEZE,
                "Distinct A3 freeze or A2 binding differs")
    binding = {"original_science_freeze": funding.OLD_FREEZE, "original_plan_sha256": funding.OLD_PLAN_SHA,
               "a2_operational_freeze": a3.A2_FREEZE, "actual_operational_freeze": freeze,
               "amendment_plan_sha256": p.sha(path)}
    base._check(actual == binding and _ancestor(a3.A2_FREEZE, freeze), "Refusal runtime or ancestry differs")
    base._check(base._git_blob(freeze, a3.PLAN) == path.read_bytes(), "Frozen refusal plan differs")
    for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
        base._check(base._sha(base._git_blob(freeze, name)) == expected, "Frozen refusal source differs")
    base._check(not set(OWN_SOURCES) & set(plan["source_hashes"]), "Release adapter entered A3 execution closure")
    return binding


class _PhysicalSnapshot:
    """Read-only prefix interface for the frozen LogicalView and cost forecast."""
    def __init__(self, events, freeze, plan=None):
        self._mutex, self._events = RLock(), events
        if plan is None:
            policy = a2.Policy(freeze)
            self.policy = policy.advance(events)
            self.records = policy.calls
        else:
            self.policy = a3.policy_state(events, freeze, plan)
            self.records = {}
            for event in events:
                if event["kind"] != "binding":
                    row = event["data"]
                    key = row["call_id"]
                    self.records[key] = {**self.records.get(key, {}), **row}

    def rows(self):
        return deepcopy(list(self.records.values()))

    def existing(self, call_id):
        return deepcopy(self.records.get(call_id))

    def spent(self):
        return sum((Decimal(r["cost_usd"]) for r in self.records.values()), Decimal(0))


def _retry_runner(plan, runtime, ledger, freeze, *, refusal=False):
    cls = a3.RefusalRunner if refusal else a2.RetryRunner
    return cls(plan, runtime["freeze"], runtime["plan_sha256"], ledger,
                          operational_freeze=freeze)


def _projection(ledger, freeze, plan=None):
    view = a2.LogicalView(ledger, freeze) if plan is None else a3.LogicalView(ledger, freeze, plan)
    physical = {r["call_id"]: r for r in ledger.rows()}
    rows = []
    for logical, ids in view.mapping.items():
        selected = view.existing(logical)
        settled = [cid for cid in ids if physical[cid]["status"] == "settled"]
        base._check(not settled or settled == [ids[-1]], "A completed physical result was retried or replaced")
        rows.append({"logical_call_id": logical, "physical_call_ids": ids,
                     "selected_physical_call_id": ids[-1], "selected_status": selected["status"],
                     "physical_cost_bound_usd": str(sum((Decimal(physical[cid]["cost_usd"]) for cid in ids), Decimal(0))),
                     "selected_cost_bound_usd": selected["cost_usd"]})
        if plan is not None and a3.terminal_refusal(selected, plan):
            base._check(ids[-1] == selected["call_id"] or a2.split_id(ids[-1])[0] == logical,
                        "Refusal projection identity differs")
            rows[-1].update(logical_label_status="provider_refusal_unknown", default_tier_certified=False,
                            raw_service_tier=selected["raw"]["service_tier"], error_type=selected["error_type"],
                            reservation_retained_usd=selected["reservation_usd"], refusal_retry_allowed=False)
    base._check(sum((Decimal(r["physical_cost_bound_usd"]) for r in rows), Decimal(0)) == ledger.spent(),
                "Physical attempt costs were omitted or counted twice")
    completed = sum((Decimal(r["cost_usd"]) for r in view.rows() if r["status"] == "settled"), Decimal(0))
    return {"schema": "repeated-transport-a2-logical-projection-v1", "raw_modified": False,
            "rule": "Frozen LogicalView selects the last attempt; a later attempt requires an eligible transport failure, never a settled result",
            "physical_calls": len(physical), "logical_calls": len(rows), "calls": rows,
            "physical_cost_bound_usd": str(ledger.spent()), "completed_logical_spend_usd": str(completed),
            "transport_overhead_or_unresolved_usd": str(ledger.spent() - completed),
            "physical_unresolved": sum(r["status"] != "settled" for r in physical.values()),
            "logical_unresolved": sum(r["status"] != "settled" for r in view.rows()),
            "unknown_charges_are_reserved": True, "transport_policy": view.policy}


def _history(raw, events):
    offsets, times, states = {}, [], []
    size, records, spent, outstanding = 0, {}, Decimal(0), Decimal(0)
    for index, (line, event) in enumerate(zip(raw.splitlines(keepends=True), events)):
        size += len(line)
        times.append(_time(event["utc"]))
        if index:
            row = records.setdefault(event["data"]["call_id"], {})
            before = Decimal(row.get("cost_usd", "0"))
            spent -= before
            outstanding -= before if row.get("status") != "settled" else Decimal(0)
            row.update(event["data"])
            after = Decimal(row["cost_usd"])
            spent += after
            outstanding += after if row["status"] != "settled" else Decimal(0)
        state = {"calls": len(records), "spent": spent, "outstanding": outstanding}
        states.append(state); offsets[size] = index + 1
    base._check(times == sorted(times), "Journal clock moved backward")
    return offsets, times, states


def _prefix(raw, receipt, offsets, states):
    base._check(set(receipt) == {"bytes", "sha256", "calls"} and type(receipt["bytes"]) is int
                and type(receipt["calls"]) is int and receipt["bytes"] in offsets,
                "Malformed or torn launch prefix")
    cutoff = offsets[receipt["bytes"]]
    base._check(base._sha(raw[:receipt["bytes"]]) == receipt["sha256"]
                and states[cutoff - 1]["calls"] == receipt["calls"], "Launch prefix hash or calls differ")
    return cutoff


def _refusal_dispatch_guard(events, freeze, plan):
    """Replay stop decisions chronologically; no repair call can replace a refusal."""
    policy, projected, records, refused = a2.Policy(a3.A2_FREEZE), [], {}, set()
    for event in events:
        if event["kind"] == "binding":
            projected.append(event); policy.advance(projected)
            continue
        row = event["data"]
        key = row["call_id"]
        if event["kind"] == "reserve":
            meta = row["metadata"]
            signature = (meta.get("item_id"), meta.get("judge"), meta.get("instrument"))
            base._check(signature not in refused, "Provider refusal was retried or schema-repaired")
            if event["seq"] > a3.PREFIX["events"]:
                base._check(policy.stop_reason is None, "Dispatch occurred after the A3 stop latched")
            if "transport_retry" in meta:
                expected = a3.A2_FREEZE if event["seq"] <= a3.PREFIX["events"] else freeze
                base._check(meta["transport_retry"]["operational_freeze"] == expected, "Retry epoch differs")
                event = deepcopy(event)
                event["data"]["metadata"]["transport_retry"]["operational_freeze"] = a3.A2_FREEZE
        records[key] = {**records.get(key, {}), **row}
        if event["kind"] == "settle" and a3.terminal_refusal(records[key], plan):
            meta = records[key]["metadata"]
            refused.add((meta["item_id"], meta["judge"], meta["instrument"]))
            continue
        projected.append(event); policy.advance(projected)
    frozen = a3.policy_state(events, freeze, plan)
    base._check(all(frozen[k] == v for k, v in policy.summary().items()), "A3 chronological policy differs")


def _sequence(root, raw, plan, runtime, binding, admission, runner, events, *, retry=False, refusal=False):
    anchor = {k: a3.PREFIX[k] for k in ("bytes", "sha256", "calls")} if refusal else a2.PREFIX if retry else funding.PREFIX
    prefix = raw[:anchor["bytes"]]
    base._check(len(prefix) == anchor["bytes"] and base._sha(prefix) == anchor["sha256"],
                "Immutable initial journal prefix differs")
    offsets, times, states = _history(raw, events)
    if refusal:
        initial_count = _prefix(raw, anchor, offsets, states)
        base._check(initial_count == a3.PREFIX["events"], "A3 prior event count differs")
        known = events[a3.REFUSAL_EVENT["seq"] - 1]
        base._check(known["sha256"] == a3.REFUSAL_EVENT["sha256"] and known["kind"] == "settle"
                    and known["data"]["call_id"] == a3.REFUSAL, "Known A2 refusal anchor differs")
        before = _PhysicalSnapshot(events[:initial_count], binding["actual_operational_freeze"], plan)
        base._check(a3.terminal_refusal(before.existing(a3.REFUSAL), plan), "Known A2 refusal shape differs")
        _refusal_dispatch_guard(events, binding["actual_operational_freeze"], plan)
        fixtures = True
    elif retry:
        initial_count = _prefix(raw, anchor, offsets, states)
        known = events[a2.KNOWN_EVENT["seq"] - 1]
        base._check(known["sha256"] == a2.KNOWN_EVENT["sha256"] and known["kind"] == "settle"
                    and known["data"]["call_id"] == a2.KNOWN_FAILURE, "Known A1 transport failure anchor differs")
        policy = a2.Policy(binding["actual_operational_freeze"])
        policy.advance(events[:initial_count])
        base._check(a2.eligible(policy.calls[a2.KNOWN_FAILURE]), "Known failure is not retry-eligible")
        for index in range(initial_count, len(events)):
            base._check(events[index]["kind"] != "reserve" or policy.stop_reason is None,
                        "Dispatch occurred after the transport stop latched")
            policy.advance(events[:index + 1])
        fixtures = True
    else:
        with base._replay(prefix, plan, runtime) as (prior, history):
            base._check(len(prior.ledger.rows()) == funding.PREFIX["calls"], "Initial call count differs")
            fixtures, old = base._sequence(root, prefix, plan, runtime, prior, history)
            base._check(fixtures and old is not None and old["pass"] is False
                        and old["journal_prefix"] == funding.PREFIX, "Original failed admission did not reconstruct")
            initial_count = len(history)
    launches = []
    launch_root = root / ("refusal_a3" if refusal else "transport_a2" if retry else FOLDER) / "launches"
    complete_key = "inventory_complete" if refusal else "complete"
    for folder in sorted(launch_root.iterdir()) if launch_root.exists() else []:
        start = base._load(folder / "start.json")
        base._check(set(start) == set(binding) | {"utc", "journal_before"} | (set() if refusal else {"outcome_selection"})
                    and all(start[k] == v for k, v in binding.items()) and (refusal or start["outcome_selection"] is False),
                    "Launch binding differs")
        cutoff = _prefix(raw, start["journal_before"], offsets, states)
        stamp = _time(start["utc"])
        base._check(cutoff >= initial_count and (retry or states[cutoff - 1]["outstanding"] == 0)
                    and stamp >= times[cutoff - 1], "Launch preceded resolved initial history")
        if retry:
            before = _PhysicalSnapshot(events[:cutoff], binding["actual_operational_freeze"], plan if refusal else None)
            base._check(before.policy["stop_reason"] is None
                        and all(r["status"] == "settled" or a2.eligible(r) or refusal and a3.terminal_refusal(r, plan) for r in before.rows()),
                        "A2 launch preceded a pending or nonretryable failure")
        finish = base._load(folder / "finish.json") if (folder / "finish.json").exists() else None
        end = None
        if finish is not None:
            base._check(set(finish) == set(binding) | {complete_key, "spent_and_reserved_usd", "journal_after"}
                        | ({"transport_policy"} if retry else set())
                        and all(finish[k] == v for k, v in binding.items()) and type(finish[complete_key]) is bool,
                        "Finish binding differs")
            end = _prefix(raw, finish["journal_after"], offsets, states)
            base._check(end >= cutoff and funding.amount(finish["spent_and_reserved_usd"]) == states[end - 1]["spent"],
                        "Finish spend or history differs")
            if retry:
                expected_policy = (a3.policy_state(events[:end], binding["actual_operational_freeze"], plan) if refusal else
                                   a2.policy_state(events[:end], binding["actual_operational_freeze"]))
                base._check(finish["transport_policy"] == expected_policy,
                            "Finish transport policy differs")
        observations = []
        for path in sorted((folder / "funding").glob("*.json")):
            row = base._load(path)
            base._check(set(row) == set(binding) | {"utc", "balance_usd", "external_holdback_usd",
                        "spent_and_reserved_usd", "funded_limit_usd"}
                        and all(row[k] == v for k, v in binding.items()) and row["external_holdback_usd"] == "45",
                        "Funding observation binding or holdback differs")
            observations.append((_time(row["utc"]), row))
        launches.append({"id": folder.name, "start": cutoff, "utc": stamp, "end": end, "finish": finish,
                         "folder": folder,
                         "observations": sorted(observations, key=lambda item: item[0])})
    launches.sort(key=lambda launch: (launch["start"], launch["utc"]))
    covered, summaries = set(), []
    for number, launch in enumerate(launches):
        next_start = launches[number + 1]["start"] if number + 1 < len(launches) else len(events)
        end = launch["end"] if launch["end"] is not None else next_start
        base._check(launch["start"] <= end <= next_start, "Launch histories overlap")
        limit, observations = Decimal("130"), []
        for stamp, row in launch["observations"]:
            index = bisect_right(times, stamp) - 1
            base._check(stamp >= launch["utc"] and launch["start"] - 1 <= index < max(end, launch["start"]),
                        "Funding observation is outside launch history")
            state = states[index]
            balance = funding.amount(row["balance_usd"])
            base._check(balance > Decimal("45") and funding.amount(row["spent_and_reserved_usd"]) == state["spent"],
                        "Funding observation spend or balance differs")
            limit = min(limit, Decimal("130"), state["spent"] + balance - Decimal("45") - state["outstanding"])
            base._check(funding.amount(row["funded_limit_usd"]) == limit, "Funded limit does not reconstruct")
            if not retry and not observations and end > launch["start"]:
                extra = state["spent"] - funding.amount(admission["observed_spend_usd"])
                base._check(extra >= 0 and state["spent"] + max(Decimal(0),
                            funding.amount(admission["remaining_forecast_usd"]) - extra) <= limit,
                            "Launch lacked completion funding")
            observations.append((stamp, limit))
        if retry:
            forecast_path = launch["folder"] / "completion_forecast.json"
            base._check(end == launch["start"] or forecast_path.exists(), "A2 dispatch lacks completion forecast")
            if forecast_path.exists():
                base._check(observations and bisect_right(times, observations[0][0]) == launch["start"],
                            "First funding receipt did not precede A2 dispatch")
                prior = _PhysicalSnapshot(events[:launch["start"]], binding["actual_operational_freeze"], plan if refusal else None)
                prior.stage_limit = observations[0][1]
                expected = (a3.completion_funding(prior, admission, binding["actual_operational_freeze"], plan) if refusal else
                            a2.require_completion_funding(prior, admission, observations[0][1], binding["actual_operational_freeze"]))
                base._check(base._load(forecast_path) == expected, "A2 completion forecast omits retry overhead or differs")
            audit_path = launch["folder"] / "audit.json"
            base._check(not launch["finish"] or not launch["finish"][complete_key] or audit_path.exists(),
                        "Complete A2 finish lacks its saved audit")
            if audit_path.exists():
                prior = _PhysicalSnapshot(events[:end], binding["actual_operational_freeze"], plan if refusal else None)
                expected = _retry_runner(plan, runtime, prior, binding["actual_operational_freeze"], refusal=refusal).audit()
                base._check(base._load(audit_path) == expected, "A2 saved launch audit differs")
        for index in range(launch["start"], end):
            base._check(index not in covered and times[index] >= launch["utc"], "Event preceded its launch")
            covered.add(index)
            if events[index]["kind"] != "reserve":
                continue
            row = events[index]["data"]
            base._check(row["phase"] == "main" and (runner.catalog[row["metadata"]["item_id"]]["block"] > 2
                        or retry and a2.split_id(row["call_id"])[1] > 0),
                        "Funding amendment restarted fixtures or initial samples")
            available = [value for stamp, value in observations if stamp <= times[index]]
            base._check(available and states[index]["spent"] <= available[-1], "Dispatch lacks sufficient prior funding")
        summaries.append({"id": launch["id"], "start_events": launch["start"], "end_events": end,
                          "finish_present": launch["finish"] is not None,
                          "reported_complete": launch["finish"][complete_key] if launch["finish"] else None,
                          "start_utc": launch["utc"].isoformat(),
                          "journal_before_utc": times[launch["start"] - 1].isoformat(),
                          "last_journal_utc": times[end - 1].isoformat(),
                          "balance_observations": len(observations)})
    base._check(covered == set(range(initial_count, len(events))), "Post-prefix events lack launch coverage")
    terminal_complete = bool(launches and launches[-1]["finish"] and launches[-1]["finish"][complete_key]
                             and launches[-1]["end"] == len(events))
    return {"pass": True, "original_admission_pass": False, "amended_admission_pass": True,
            "original_prefix": dict(anchor), "original_failed_admission_sha256": funding.FAILED_SHA,
            "scientific_freeze": runtime["freeze"], "operational_freeze": binding["actual_operational_freeze"],
            "fixtures_pass": fixtures, "launches": summaries, "terminal_complete": terminal_complete,
            "scientific_settings_changed": False, "outcome_selection": False,
            "atomic_cap_usd": "130", "external_holdback_usd": "45", "reserve_multiplier": "1.10"}


def _derive(root):
    plan, runtime, amended, binding, admission = _plans(root)
    retry = (root / "transport_a2").exists()
    retry_binding = _transport_plan(root, binding) if retry else None
    refusal = (root / "refusal_a3").exists()
    refusal_binding = _refusal_plan(root, retry_binding) if refusal else None
    for name in _inventory(root, derived=False):
        if name.endswith(".json"):
            base._public(base._load(root / name))
    with gzip.open(root / "raw/events.jsonl.gz", "rb") as stream:
        raw = stream.read(base.MAX_RAW_BYTES + 1)
    additions = {}
    if retry:
        with base._replay(raw[:a2.PREFIX["bytes"]], plan, runtime) as (prior, history):
            prior.audit()
            funding_sequence = _sequence(root, raw[:a2.PREFIX["bytes"]], plan, runtime,
                                         binding, admission, prior, history)
    if refusal:
        with base._replay(raw[:a3.PREFIX["bytes"]], plan, runtime) as (prior, history):
            original_a2 = _retry_runner(plan, runtime, prior.ledger, retry_binding["actual_operational_freeze"])
            original_a2.audit()
            transport_sequence = _sequence(root, raw[:a3.PREFIX["bytes"]], plan, runtime,
                                           retry_binding, admission, original_a2, history, retry=True)
            base._check(transport_sequence["launches"] and all(x["finish_present"] for x in transport_sequence["launches"])
                        and not transport_sequence["terminal_complete"], "A3 lacks the finished, failed A2 epoch")
    with base._replay(raw, plan, runtime) as (runner, events):
        physical = runner.ledger
        active = refusal_binding if refusal else retry_binding if retry else binding
        if retry:
            runner = _retry_runner(plan, runtime, physical, active["actual_operational_freeze"], refusal=refusal)
        audit = runner.audit()
        sequence = _sequence(root, raw, plan, runtime, active,
                             admission, runner, events, retry=retry, refusal=refusal)
        if retry:
            additions = {"transport_audit.json": transport_sequence if refusal else sequence,
                         "logical_projection.json": _projection(physical, active["actual_operational_freeze"], plan if refusal else None)}
        if refusal:
            milestones = []
            for name, anchor, following in (("a1_transport_failure", a2.KNOWN_EVENT, transport_sequence),
                                             ("a2_provider_refusal", a3.REFUSAL_EVENT, sequence)):
                event = events[anchor["seq"] - 1]
                resumed = following["launches"][0]["start_utc"] if following["launches"] else None
                milestones.append({"kind": name, "event_seq": event["seq"], "event_sha256": event["sha256"],
                                   "event_utc": event["utc"], "next_epoch_launch_utc": resumed,
                                   "event_to_launch_seconds": (_time(resumed) - _time(event["utc"])).total_seconds() if resumed else None})
            additions.update({"refusal_audit.json": sequence, "epoch_timing.json": {
                "schema": "repeated-execution-epochs-v1", "epochs": {"funding_a1": funding_sequence["launches"],
                "transport_a2": transport_sequence["launches"], "refusal_a3": sequence["launches"]}, "milestones": milestones,
                "scope": "Recorded failure events and launch receipts; in-flight settlements retained; not exact process downtime"}})
        rows = runner.rows("main")
        try:
            if retry:
                view = (a3.LogicalView(physical, active["actual_operational_freeze"], plan) if refusal else
                        a2.LogicalView(physical, active["actual_operational_freeze"]))
                base._check(view.policy["stop_reason"] is None and all(r["status"] == "settled" or a2.eligible(r)
                            or refusal and a3.terminal_refusal(r, plan)
                            for r in physical.rows()), "A2 retains pending or nonretryable failures")
                base._check(all(r["status"] == "settled" or a2.split_id(view.mapping[r["call_id"]][-1])[1] == 2
                            or refusal and a3.terminal_refusal(r, plan)
                            for r in view.rows()), "Logical missingness is not exhausted under the frozen retry rule")
            else:
                runner.require_resolved()
            runner.require_complete()
            complete = sequence["terminal_complete"]
        except base.Halted:
            complete = False
        base._check(not sequence["terminal_complete"] or complete, "Complete finish lacks complete scientific inventory")
        endpoints = all(base.labels._value(row, judge, endpoint) is not None
                        for row in rows for judge in plan["judges"] for endpoint in base.analysis.ENDPOINTS)
        metadata = {"schema": "repeated-funding-a1-release-v1", "status": "complete" if complete and endpoints else "incomplete",
            "freeze": runtime["freeze"], "scientific_freeze": runtime["freeze"],
            "operational_freeze": binding["actual_operational_freeze"], "plan_sha256": runtime["plan_sha256"],
            "amendment_plan_sha256": binding["amendment_plan_sha256"],
            "collection_complete": complete, "endpoint_complete": endpoints, "fixtures_pass": sequence["fixtures_pass"],
            "original_admission_pass": False, "amended_admission_pass": True,
            "main_status": "completed" if complete else "incomplete", "terminal_receipt_complete": sequence["terminal_complete"],
            "journal": {"bytes": len(raw), "sha256": base._sha(raw), "events": len(events), "calls": len(runner.ledger.rows())},
            "initial_prefix": dict(funding.PREFIX), "cost_bound_usd": str(runner.ledger.spent()),
            "unknown_charges_are_reserved": True, "unresolved": sum(r["status"] != "settled" for r in physical.rows()),
            "primary_judge": "astra", "primary_family_size": 2, "primary_individual_confidence": .975,
            "nominal_family_confidence": .95, "scientific_settings_changed": False,
            "publication_scope": "Original observations and financial amendment; no new calls, labels or scientific rules",
            "source_hashes": {name: p.sha(ROOT / name) for name in OWN_SOURCES}}
        if retry:
            metadata.update(schema="repeated-transport-a2-release-v1", funding_a1_freeze=binding["actual_operational_freeze"],
                            operational_freeze=retry_binding["actual_operational_freeze"],
                            funding_plan_sha256=binding["amendment_plan_sha256"],
                            amendment_plan_sha256=retry_binding["amendment_plan_sha256"],
                            transport_prefix=dict(a2.PREFIX), physical_calls=audit["physical_calls"],
                            logical_calls=audit["logical_calls"], logical_unresolved=audit["unresolved"],
                            accounting_complete=audit["physical_unresolved"] == 0,
                            projection_disclosure="LogicalView is a detached projection; all physical attempts, failures and costs remain in raw receipts",
                            unknown_200_cause="The frozen sender lost the body; status 200 does not identify the failure cause",
                            publication_scope="Original science plus separately frozen funding and identical-transport-retry amendments; no publication-time dispatch")
        if refusal:
            metadata.update(schema="repeated-refusal-a3-release-v1", transport_a2_freeze=retry_binding["actual_operational_freeze"],
                            transport_plan_sha256=retry_binding["amendment_plan_sha256"],
                            operational_freeze=active["actual_operational_freeze"], amendment_plan_sha256=active["amendment_plan_sha256"],
                            refusal_prefix=dict(a3.PREFIX), terminal_refusal_calls=audit["transport_policy"]["terminal_refusal_calls"],
                            terminal_refusal_reservations_usd=audit["transport_policy"]["terminal_refusal_reservations_usd"],
                            refusal_default_tier_certified=False, refusal_retry_allowed=False,
                            publication_scope="Original science and separately frozen A1/A2/A3 operational amendments; refusals remain unknown and reserved")
    return {"RELEASE.json": metadata, "rows.json": rows, "analysis.json": base.analysis.analyze(rows),
            "audit.json": audit, "funding_audit.json": funding_sequence if retry else sequence, **additions}


def verify(destination, *, manifest_sha256=None):
    root = Path(destination).absolute()
    inventory = _inventory(root, derived=True)
    manifest = base._load(root / "MANIFEST.json")
    base._check(manifest == {"schema": MANIFEST_SCHEMA, "files": base._entries(root)}
                and (root / "MANIFEST.json").read_bytes() == (p.canonical(manifest) + "\n").encode(),
                "Manifest inventory, hashes or encoding differ")
    if manifest_sha256 is not None:
        base._check(p.sha(root / "MANIFEST.json") == manifest_sha256, "External manifest anchor differs")
    with TemporaryDirectory(prefix="repeat-funding-verify-") as temporary:
        snapshot = Path(temporary).resolve()
        for name in set(inventory) - DERIVED - A2_DERIVED - A3_DERIVED:
            target = snapshot / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / name).read_bytes())
        expected = _derive(snapshot)
    base._check(all(p.canonical(base._load(root / name)) == p.canonical(value) for name, value in expected.items()),
                "Derived funding release does not reconstruct")
    return {"pass": True, "status": expected["RELEASE.json"]["status"], "files": len(inventory),
            "manifest_sha256": p.sha(root / "MANIFEST.json"), "unresolved": expected["RELEASE.json"]["unresolved"]}


def build(destination, *, run_dir=None):
    source = Path(base.production.root_path()).absolute()
    if run_dir is not None:
        base._check(Path(run_dir).absolute() == source, "Export requires the canonical operational root")
    target = Path(destination).absolute()
    base._no_symlinks(source); base._no_symlinks(target)
    base._check(not target.exists() and source not in target.parents and target not in source.parents,
                "Destination must be new and outside the run")
    paths = {"PLAN.json": p.ROOT / p.PLAN, f"{FOLDER}/PLAN.json": funding.ROOT / funding.PLAN,
             f"{FOLDER}/FAILED_ADMISSION.json": funding.ROOT / funding.ANCHOR}
    paths.update({name: source / name for name in REQUIRED - DERIVED - set(paths) - {"raw/events.jsonl.gz"}})
    paths["raw/events.jsonl"] = source / "raw/events.jsonl"
    epochs = [FOLDER]
    if (source / "transport_a2").exists():
        paths["transport_a2/PLAN.json"] = a2.ROOT / a2.PLAN
        paths["transport_a2/runtime.json"] = source / "transport_a2/runtime.json"
        epochs.append("transport_a2")
    if (source / "refusal_a3").exists():
        paths["refusal_a3/PLAN.json"] = a3.ROOT / a3.PLAN
        paths["refusal_a3/runtime.json"] = source / "refusal_a3/runtime.json"
        epochs.append("refusal_a3")
    for epoch in epochs:
        for path in (source / epoch / "launches").rglob("*"):
            base._no_symlinks(path)
            if not path.is_dir():
                name = path.relative_to(source).as_posix()
                base._check(_launch_path(name), "Unexpected operational launch artifact")
                paths[name] = path
    for path in paths.values():
        base._no_symlinks(path)
    originals = {name: path.read_bytes() for name, path in paths.items()}
    with TemporaryDirectory(prefix="repeat-funding-release-") as temporary:
        snapshot = Path(temporary).resolve() / "bundle"; snapshot.mkdir()
        for name, data in originals.items():
            if name == "raw/events.jsonl":
                name, data = name + ".gz", gzip.compress(data, mtime=0)
            path = snapshot / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        for name, value in _derive(snapshot).items():
            base._write(snapshot / name, value)
        base._write(snapshot / "MANIFEST.json", {"schema": MANIFEST_SCHEMA, "files": base._entries(snapshot)})
        result = verify(snapshot)
        base._check(all(path.read_bytes() == originals[name] for name, path in paths.items()), "Operational inputs changed during export")
        launch_paths = {q.relative_to(source).as_posix() for epoch in epochs
                        for q in (source / epoch / "launches").rglob("*") if q.is_file()}
        base._check(launch_paths == {name for name in paths if _launch_path(name)}, "Launch inventory changed during export")
        base._no_symlinks(target); shutil.copytree(snapshot, target)
    base._check(base._entries(target) == base._load(target / "MANIFEST.json")["files"]
                and p.sha(target / "MANIFEST.json") == result["manifest_sha256"], "Copied release differs")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--run-dir")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    try:
        result = verify(args.destination, manifest_sha256=args.manifest_sha256) if args.verify else build(args.destination, run_dir=args.run_dir)
    except (base.Halted, ValueError, TypeError, KeyError, ArithmeticError, OSError, EOFError, subprocess.SubprocessError):
        parser.exit(1, "Funding release failed closed; scientific and financial records retained.\n")
    print(p.canonical(result))


if __name__ == "__main__":
    main()
