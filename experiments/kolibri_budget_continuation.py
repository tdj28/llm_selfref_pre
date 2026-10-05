"""Additive budget continuation: finish saved screening; one conditional main server."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import signal
import subprocess
import time

from experiments import kolibri_generation_waves as waves, kolibri_judge_transport as transport
from experiments.kolibri_bootstrap_a5 import adapter as a5
from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol, runtime
from experiments.openrouter_swap import judges
from experiments.openrouter_swap.ledger import Ledger, _no_symlinks, read_events
from experiments.openrouter_swap.providers import ENDPOINT, reservation
from experiments.openrouter_swap.runner import write_once
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc

PLAN = "data/kolibri_budget_continuation/plan_v1_20261005/AMENDMENT.json"
SOURCES = ("experiments/kolibri_budget_continuation.py", "tests/test_kolibri_budget_continuation.py",
           "docs/KOLIBRI_BUDGET_CONTINUATION_20261005.md")
WAVE_FREEZE = "1c41ab1957a5ac95bd1d94fe707604158b52e1aa"
CAPS = {"gpu": "30", "judges": "40", "recovery": "5", "pilot": "30", "total": "75"}
AUTHORITY = {"direct_owner_total_usd": "75", "additional_total_authorized_usd": "0",
    "allocation_origin": "parent_agent_implementation_judgment_under_owner_best_judgment_instruction",
    "subsequent_human_approval": "Approved, continue",
    "approval_recorded_utc": "2026-10-05T12:39:16+00:00",
    "approval_evidence": "Parent relayed a new direct human message; not a quotation of the earlier allocation proposal",
    "scope": "Finish undispatched fixed screen; if unchanged qualification and full budget forecast pass, one fresh main-only H200; no completed-call retries or new science"}
check = prod.check


def root():
    return old.canonical_root() / "bootstrap-a6"


def sources():
    return {name: protocol.sha(protocol.ROOT / name) for name in SOURCES}


def inputs():
    return (protocol.verify(protocol.ROOT / protocol.PLAN), a5.verify(),
            transport.verify(protocol.ROOT / transport.PLAN), waves.verify(collection=a5.root() / "collection"))


def unfinished(runner):
    result = []
    for block in runner.plan["screen"]:
        for item in block["finals"]:
            raw = runner.receipts.existing("gen:" + item["id"])
            if raw["projection"]["missing"]:
                continue
            for judge in runner.plan["judges"]:
                for instrument in judges.INSTRUMENTS:
                    identity = f"judge:{item['id']}:{judge}:{instrument}"
                    if runner.receipts.existing(identity + ":a0") is None:
                        result.append(identity)
    return result


def predecessor():
    prior = a5.verify()["predecessor"]["cost_usd"]
    receipt = prod.closed_receipt(a5.root(), "main", a5.a4.a1.ORIGINAL_PLAN_SHA, waves.WORKER_FREEZE)
    _, events = prod.controller_events(a5.root(), "main", a5.a4.a1.ORIGINAL_PLAN_SHA, waves.WORKER_FREEZE)
    with localcontext() as context:
        context.prec = 60
        carry = Decimal(prior) + Decimal(receipt["cost_usd"])
    return {**receipt, "pod_id": events["created"]["data"]["id"],
            "prior_six_attempts_usd": prior, "gpu_carry_usd": str(carry),
            "startup_seconds": events["server-ready"]["data"]["elapsed_seconds"],
            "old_work_deadline": events["create-intent"]["data"]["deadline_utc"]}


def build():
    plan, amendment, policy, wave_plan = inputs()
    with waves.saved_runner(a5.root(), plan, amendment, policy, wave_plan, WAVE_FREEZE) as runner:
        audit = runner.audit()
        runner.require_resolved()
        check(runner.complete_generation("screen")["generation_calls"] == 72, "Screen generations incomplete")
        records = runner.receipts.records()
        check(not any(r["phase"] == "main" for r in records.values()), "Continuation must precede main")
        pending = unfinished(runner)
        check(pending, "No undispatched screen judgments remain")
        old_stop = guard_stop(runner, pending[0])
        completed = runner.wave_audit()
        means = {role: sum(Decimal(w["elapsed_seconds"]) for w in completed if w["role"] == role) / 10
                 for role in ("source", "final")}
        old_seconds = Decimal("1.30") * 64 * sum(means.values()) + 600
    old_run = predecessor()
    with localcontext() as context:
        context.prec = 60
        remaining = Decimal(CAPS["gpu"]) - Decimal(old_run["gpu_carry_usd"])
    check(remaining > 0, "GPU allowance exhausted")
    return {"schema": "kolibri-budget-continuation-v1", "wave_freeze": WAVE_FREEZE,
        "authorization_provenance": AUTHORITY,
        "worker_source_basis": waves.WORKER_FREEZE, "scientific_plan_sha256": a5.a4.a1.ORIGINAL_PLAN_SHA,
        "wave_plan_sha256": protocol.sha(protocol.ROOT / waves.PLAN), "caps_usd": CAPS,
        "source_hashes": sources(), "dependency_source_hashes": {
            **wave_plan["dependency_source_hashes"], **wave_plan["source_hashes"]},
        "prefix": waves.prefix(a5.root() / "collection"), "prefix_audit": audit,
        "undispatched_screen_judgments": pending, "predecessor": old_run,
        "new_main_cap_usd": str(remaining), "maximum_new_main_pods": 1,
        "startup_margin": "1.30", "main_margin": "1.30", "cleanup_seconds": "600",
        "qualified_a4_cheap_reused": amendment["qualification"], "new_cheap_pod": False,
        "watchdog_handoff": False, "old_watchdog_preserved": True,
        "new_server_requires_old_retrieval_and_GET404": True,
        "science_changed": False, "completed_calls_repeated": False,
        "known_outcomes": "All 72 screen generations and 127 target judgments are observed; one capped/missing final is retained. The 20-dollar pilot reservation guard stopped 61 undispatched judgments. Full scientific qualification is not yet available; no main outcomes exist.",
        "preserved_guard_stop": old_stop,
        "preserved_time_forecast": {"main_seconds_with_margin": str(old_seconds),
            "wave_mean_seconds": {k: str(v) for k, v in means.items()}, "cleanup_seconds": "600",
            "original_work_deadline": old_run["old_work_deadline"], "old_remaining_horizon_insufficient": True},
        "new_main_policy": "Only after unchanged complete screen qualification and measured whole-inventory admission; one fresh owned H200 with unchanged A5 worker sources and fixed waves. No extra samples or adaptive concurrency."}


def guard_stop(runner, blocked):
    """Reconstruct the reservation bound, not a provider bill or unsaved exception."""
    events = read_events(runner.ledger.root / "events.jsonl")
    last = next(e for e in reversed(events) if e["kind"] == "reserve")
    calls = {}
    for event in events:
        if event["seq"] > last["seq"]: break
        data = event["data"]
        if event["kind"] in {"reserve", "settle"}:
            calls[data["call_id"]] = {**calls.get(data["call_id"], {}), **data}
    _, controller = prod.controller_events(a5.root(), "main", runner.plan_hash, waves.WORKER_FREEZE)
    intent = controller["create-intent"]["data"]
    rate = Decimal(intent["quote"]["hourly_rate_usd"]) + Decimal(intent["quote"]["storage_hourly_usd"])
    elapsed = Decimal(str((_utc(last["utc"]) - _utc(intent["created_utc"])).total_seconds()))
    carry = Decimal(runner.amendment["predecessor"]["cost_usd"])
    paid = sum(Decimal(r["cost_usd"]) for r in calls.values() if r["status"] != "pending")
    held = sum(Decimal(r["cost_usd"]) for r in calls.values() if r["status"] == "pending")
    identity, judge, instrument = blocked.rsplit(":", 2)
    response = runner.receipts.existing("gen:" + identity[len("judge:"):])["projection"]["response"]
    spec = runner.plan["judges"][judge]
    request = judges.judge_request(spec, instrument, response)
    request["provider"].update(runtime.PRIVACY)
    reserve = reservation(spec, request)
    before = carry + (elapsed + 600) * rate / 3600 + paid + held + 5
    check(before <= 20 < before + reserve, "Stopped reservation no longer reconstructs")
    return {"pilot_usd": "20", "last_reservation_utc": last["utc"], "last_reservation_sha256": last["sha256"],
        "clock_basis": "Reconstructed at saved reservation timestamp; actual pre-reserve guard clock was not recorded",
        "prior_gpu_usd": str(carry), "current_gpu_at_timestamp_usd": str(elapsed * rate / 3600),
        "gpu_600_second_horizon_usd": str(600 * rate / 3600), "settled_judges_at_timestamp_usd": str(paid),
        "pending_full_reservations_usd": str(held), "recovery_reserve_usd": "5",
        "reconstructed_before_usd": str(before), "blocked_judgment": blocked,
        "blocked_full_request_reservation_usd": str(reserve), "reconstructed_after_usd": str(before + reserve),
        "all_admitted_calls_drained": True}


def verify(freeze=None):
    value = prod.load(protocol.ROOT / PLAN)
    check(value["schema"] == "kolibri-budget-continuation-v1" and value["caps_usd"] == CAPS
          and value["authorization_provenance"] == AUTHORITY
          and value["wave_freeze"] == WAVE_FREEZE and value["worker_source_basis"] == waves.WORKER_FREEZE
          and value["scientific_plan_sha256"] == a5.a4.a1.ORIGINAL_PLAN_SHA
          and value["source_hashes"] == sources() and value["predecessor"] == predecessor()
          and value["wave_plan_sha256"] == protocol.sha(protocol.ROOT / waves.PLAN)
          and value["maximum_new_main_pods"] == 1 and value["new_cheap_pod"] is False
          and value["watchdog_handoff"] is False and value["old_watchdog_preserved"] is True
          and value["new_server_requires_old_retrieval_and_GET404"] is True
          and value["science_changed"] is False and value["completed_calls_repeated"] is False
          and value["startup_margin"] == value["main_margin"] == "1.30" and value["cleanup_seconds"] == "600",
          "Continuation policy differs")
    prior = waves.verify(collection=a5.root() / "collection")
    check(value["dependency_source_hashes"] == {**prior["dependency_source_hashes"], **prior["source_hashes"]}
          and all(protocol.sha(protocol.ROOT / name) == digest for name, digest in value["dependency_source_hashes"].items()),
          "Frozen dependency changed")
    with localcontext() as context:
        context.prec = 60
        check(Decimal(value["new_main_cap_usd"]) + Decimal(value["predecessor"]["gpu_carry_usd"]) == 30,
              "GPU cost carry differs")
    waves.check_prefix(a5.root() / "collection", value["prefix"])
    if freeze is not None:
        waves.verify(WAVE_FREEZE, a5.root() / "collection")
        protocol.verify(protocol.ROOT / protocol.PLAN, freeze)
        subprocess.run(["git", "merge-base", "--is-ancestor", WAVE_FREEZE, freeze], cwd=protocol.ROOT, check=True)
        for name, digest in {**value["source_hashes"], PLAN: protocol.sha(protocol.ROOT / PLAN)}.items():
            check(runtime.sha(subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)) == digest,
                  "Continuation source absent from pushed freeze")
    return value


def binding(freeze, value):
    return {"schema": value["schema"], "freeze": freeze, "amendment_sha256": protocol.digest(value),
            "caps_usd": CAPS, "predecessor_closed_sha256": value["predecessor"]["closed_sha256"]}


def budget_projection(plan):
    result = deepcopy(plan)
    result["budget"].update(gpu_usd=CAPS["gpu"], judges_usd=CAPS["judges"],
                            combined_screen_stoploss_usd=CAPS["pilot"])
    return result


class Runner(waves.Runner):
    def __init__(self, *args, continuation, continuation_freeze, **kwargs):
        self.continuation, self.continuation_freeze = deepcopy(continuation), continuation_freeze
        super().__init__(*args, **kwargs)

    def check_sources(self):
        super().check_sources()
        check(self.continuation == prod.load(protocol.ROOT / PLAN)
              and self.continuation["source_hashes"] == sources(), "Continuation source binding changed")

    def audit(self):
        result = super().audit()
        events = self.receipts.events
        decision = next((e for e in events if e["kind"] == "decision" and e["data"]["name"] == "budget_continuation"), None)
        check(decision is not None and decision["data"]["value"] == binding(self.continuation_freeze, self.continuation),
              "Continuation authority absent")
        prefix = b"".join((protocol.canonical(e) + "\n").encode() for e in events[:decision["seq"] - 1])
        check({"bytes": len(prefix), "sha256": runtime.sha(prefix)} == self.continuation["prefix"]["journals"]["http/events.jsonl"],
              "Continuation did not preserve exact stopped prefix")
        for event in events[decision["seq"]:]:
            if event["kind"] != "dispatch":
                continue
            data = event["data"]
            if data["phase"] == "screen":
                logical, _ = transport.split_id(data["call_id"])
                check(data["channel"] == "judge" and logical.rsplit(":a", 1)[0]
                      in self.continuation["undispatched_screen_judgments"], "Completed or unplanned screen call repeated")
            else:
                check(data["phase"] == "main", "Extra fixture or generation scope")
        return {**result, "budget_continuation": binding(self.continuation_freeze, self.continuation)}

    def main_admission(self, **evidence):
        old_result = super().main_admission(**evidence)
        fits = (old_result["qualified"] and Decimal(old_result["gpu_completion_usd"]) <= 30
                and Decimal(old_result["judge_completion_usd"]) <= 40
                and Decimal(old_result["combined_completion_usd"]) <= 75
                and Decimal(evidence["storage_bound_usd"]) <= 5
                and Decimal(old_result["main_seconds_with_margin"]) <= Decimal(evidence["gpu_remaining_seconds"]))
        return {**old_result, "fits": fits, "prior_category_forecast_preserved": old_result,
                "budget_continuation": binding(self.continuation_freeze, self.continuation)}


def make_runner(plan, ledger, receipts, value, freeze, **kwargs):
    return Runner(plan, waves.WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA, ledger, receipts,
        amendment=a5.verify(), transport_plan=transport.verify(protocol.ROOT / transport.PLAN),
        wave_plan=waves.verify(collection=a5.root() / "collection"), wave_freeze=WAVE_FREEZE,
        continuation=value, continuation_freeze=freeze, **kwargs)


@contextmanager
def saved_runner(value, freeze):
    check((a5.root() / "collection/CONTINUATION.json").read_bytes() == (protocol.ROOT / PLAN).read_bytes(),
          "Saved continuation bytes differ")
    plan, amendment, policy, wave_plan = inputs()
    with waves.saved_runner(a5.root(), plan, amendment, policy, wave_plan, WAVE_FREEZE) as old_runner:
        yield make_runner(plan, old_runner.ledger, old_runner.receipts, value, freeze)


class StudyGuard(prod.StudyGuard):
    def __init__(self, plan, ledger, value, freeze, clock=None):
        self.root, self.plan, self.freeze, self.plan_hash = root(), plan, freeze, a5.a4.a1.ORIGINAL_PLAN_SHA
        self.ledger, self.continuation = ledger, value
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cheap = {"cost_usd": "0"}  # The complete A4 qualification cost is already in the carried total.

    def state(self, horizon=0, *, running=False, permit_stop=False):
        carry = Decimal(self.continuation["predecessor"]["gpu_carry_usd"])
        if not (self.root / "controller/main/events.jsonl").exists():
            check(not running, "Conditional main server has not been launched")
            return {"gpu_usd": carry, "main_usd": Decimal(0), "remaining_seconds": Decimal(0),
                    "active": False, "controller_sha256": self.continuation["predecessor"]["closed_sha256"]}
        _, events = prod.controller_events(self.root, "main", self.plan_hash, self.freeze)
        check(events["controller:config"]["data"]["continuation"] == binding(self.freeze, self.continuation),
              "Replacement controller binding differs")
        result = super().state(horizon, running=running, permit_stop=permit_stop)
        result["gpu_usd"] += carry
        check(permit_stop or result["gpu_usd"] <= 30
              and result["main_usd"] <= Decimal(self.continuation["new_main_cap_usd"]), "Cumulative GPU allowance exhausted")
        return result

    def before_call(self, channel, phase, spec, request):
        state = self.state(300 if channel == "local" else 600, running=channel == "local")
        api = self.ledger.spent() + (reservation(spec, request) if channel == "judge" else 0)
        total = state["gpu_usd"] + api + 5
        check(api <= 40 and total <= 75, "Whole-study reservation exceeds continuation allowance")
        check(phase != "fixtures", "No fixture repetition authorized")
        check(phase != "screen" or channel == "judge" and total <= 30, "Screen continuation reservation exceeded")

    def admission(self, runner):
        rate = Decimal(runner.plan["budget"]["gpu_hourly_usd"])
        if not (root() / "controller/main/events.jsonl").exists():
            startup = Decimal(self.continuation["predecessor"]["startup_seconds"]) * Decimal("1.30")
            duration = min(Decimal(old.SECONDS["main"]), Decimal(self.continuation["new_main_cap_usd"]) / (rate + old.STORAGE) * 3600)
            gpu = Decimal(self.continuation["predecessor"]["gpu_carry_usd"]) + startup * (rate + old.STORAGE) / 3600
            remaining, used = duration - startup, startup * (rate + old.STORAGE) / 3600
        else:
            state = self.state(running=True)
            gpu, remaining, used = state["gpu_usd"], state["remaining_seconds"], state["main_usd"]
        result = runner.main_admission(gpu_spent_usd=str(gpu), gpu_hourly_rate_usd=str(rate),
            gpu_remaining_seconds=str(remaining), storage_bound_usd="5", remaining_overhead_seconds="600")
        check(used + Decimal(result["main_seconds_with_margin"]) * (rate + old.STORAGE) / 3600
              <= Decimal(self.continuation["new_main_cap_usd"]), "Whole main plus startup/storage cannot fit new GPU allowance")
        return result


class Controller(a5.Controller):
    def __init__(self, freeze, api, *, run=subprocess.run, clock=old.base.now, sleep=time.sleep):
        self.continuation = verify(freeze)
        self.amendment = {"main_cap_usd": self.continuation["new_main_cap_usd"],
                          "qualification": self.continuation["qualified_a4_cheap_reused"]}
        self.plan_path, self.freeze, self.kind = protocol.ROOT / protocol.PLAN, freeze, "main"
        self.plan = protocol.verify(self.plan_path)
        self.plan_hash, self.relative = a5.a4.a1.ORIGINAL_PLAN_SHA, protocol.PLAN
        self.out, self.base = root(), root() / "controller/main"
        _no_symlinks(self.base); self.base.mkdir(parents=True, exist_ok=True)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": "main", "plan": self.relative, "image": bootstrap.IMAGE,
            "cap_usd": self.continuation["new_main_cap_usd"], "continuation": binding(freeze, self.continuation),
            "prior_gpu_usd": self.continuation["predecessor"]["gpu_carry_usd"],
            "qualification": self.continuation["qualified_a4_cheap_reused"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()
        self.api = a5.a4.ReadRetryAPI(api, self.read_guard, self.record, self.sleep)

    def cheap_pass(self):
        receipt = a5.qualification(a5.a4.verify())
        check(self.continuation["qualified_a4_cheap_reused"] == {"freeze": a5.A4_FREEZE,
            "pod_id": a5.QUALIFIED_POD, **receipt}, "Qualified cheap receipt changed")
        with saved_runner(self.continuation, self.freeze) as runner:
            runner.complete("screen")
            check(runner.qualification()["eligible_models"] == ["kolibri"], "Scientific screen did not qualify")
            saved = runner.receipts.decision("main_admission")
            check(saved is not None and saved == runner.main_admission(**saved["evidence"]) and saved["fits"],
                  "Whole-main admission absent or changed")
        return receipt

    def _new_pod(self, pod, intent):
        return pod.get("id") != self.continuation["predecessor"]["pod_id"] and super()._new_pod(pod, intent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=("judge-screen", "main-admission", "generate-main", "stop-server", "judge-main", "audit"), default="audit")
    parser.add_argument("--action", choices=("launch", "monitor", "terminate"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    if args.build:
        check(not args.execute and args.freeze is None and args.action is None, "Build is offline")
        write_once(protocol.ROOT / PLAN, build())
        print(protocol.canonical({"path": PLAN, "sha256": protocol.sha(protocol.ROOT / PLAN)})); return
    check(args.freeze is not None and args.execute == (args.action is not None or args.phase != "audit"), "Invalid execution scope")
    check(not args.abort or args.action is None and args.phase == "stop-server", "Abort is cleanup only")
    value = verify(args.freeze if args.execute and args.action not in {"monitor", "terminate"} and args.phase != "stop-server" else None)
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    record = None
    if args.execute and args.action not in {"monitor", "terminate"} and args.phase != "stop-server":
        check(args.reconciliation is not None, "Fresh account reconciliation required")
        record = prod.reconciliation(budget_projection(plan), prod.load(args.reconciliation), datetime.now(timezone.utc))
    if args.action:
        from dotenv import dotenv_values
        path = args.env_file
        check(path is not None, "Local private credential file required")
        _no_symlinks(path)
        check(not path.stat().st_mode & 0o077, "Credential file is not private")
        api = old.base.RunPodV2(dotenv_values(path, interpolate=False).get("RUNPOD_API_KEY"), writable=True)
        ctl = Controller(args.freeze, api)
        def interrupted(signum, _frame):
            raise SystemExit(128 + signum)
        previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
        try:
            if args.action == "launch":
                ctl.ledger.bind("funds-admission", {"reconciliation": record, "continuation": binding(args.freeze, value)})
                ctl.launch(); result = ctl.monitor()
            else:
                result = getattr(ctl, args.action)()
        finally:
            for sig, handler in previous.items(): signal.signal(sig, handler)
    elif not args.execute:
        with saved_runner(value, args.freeze) as runner:
            result = runner.audit()
    else:
        collection = a5.root() / "collection"
        with Ledger(collection / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                runtime.ReceiptJournal(collection / "http", waves.WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA) as receipts:
            if receipts.decision("budget_continuation") is None:
                check(waves.prefix(collection) == value["prefix"], "Stopped prefix advanced before continuation")
                receipts.append("decision", {"name": "budget_continuation", "value": binding(args.freeze, value)})
            waves.bridge.save_bytes(collection / "CONTINUATION.json", (protocol.ROOT / PLAN).read_bytes())
            runner = make_runner(plan, ledger, receipts, value, args.freeze, _freeze_verified=True)
            runner.guard = StudyGuard(plan, ledger, value, args.freeze)
            if args.phase != "stop-server":
                state = runner.guard.state(running=args.phase == "generate-main")
                admission = {"phase": args.phase, "reconciliation": record, "http_head": receipts.events[-1]["sha256"],
                    "plan_sha256": runner.plan_hash, **waves.bridge.bridge_binding(waves.WORKER_FREEZE, runner.amendment, runner.transport_plan),
                    "generation_waves": waves.binding(WAVE_FREEZE, runner.wave_plan),
                    "budget_continuation": binding(args.freeze, value),
                    "lifecycle": {k: str(v) if isinstance(v, Decimal) else v for k, v in state.items()}}
                write_once(collection / "admissions" / (protocol.digest(admission) + ".json"), admission)
            if args.phase == "generate-main":
                check(type(args.port) is int and 1 <= args.port <= 65535, "Loopback port required")
                runner.local_sender = runtime.http_sender(f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
            if args.phase in {"judge-screen", "judge-main"}:
                runner.sender = runtime.http_sender(ENDPOINT, timeout_seconds=600, api_key=prod.local_key(args.env_file))
            previous = {sig: signal.signal(sig, lambda *_: runner.stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                if args.phase == "stop-server":
                    result = {"operational_abort": bool(args.abort), "deletion_verified": False}
                    if not args.abort:
                        result["generation"] = runner.complete_generation("main")
                    runner.audit()
                    prod.controller_events(root(), "main", runner.plan_hash, args.freeze)
                    write_once(root() / "controller/main/STOP_SERVER", {"freeze": args.freeze, **result})
                else:
                    if args.phase == "judge-main":
                        prod.closed_receipt(root(), "main", runner.plan_hash, args.freeze)
                    # The original root remains authoritative for all saved calls.
                    result = prod.phase(runner, args.phase, a5.root())
            finally:
                for sig, handler in previous.items(): signal.signal(sig, handler)
    print(protocol.canonical(result))


if __name__ == "__main__":
    main()
