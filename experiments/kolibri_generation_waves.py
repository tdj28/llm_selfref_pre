"""Source-bound 2-source/4-final waves on the unchanged, already owned A5 server."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import shutil

from experiments import kolibri_judge_transport as transport
from experiments import kolibri_judge_waves as judge_waves
from experiments.kolibri_bootstrap_a5 import adapter as a5, production as bridge
from experiments.kolibri_swap import production as prod, protocol, runtime
from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Ledger, _no_symlinks, read_events
from experiments.openrouter_swap.providers import ENDPOINT
from experiments.openrouter_swap.runner import write_once
from experiments.sae_assay_diagnostic.budget import _utc

PLAN = "data/kolibri_generation_waves/plan_v1_20261005/AMENDMENT.json"
SOURCES = ("experiments/kolibri_generation_waves.py", "tests/test_kolibri_generation_waves.py",
           "experiments/kolibri_judge_waves.py", "tests/test_kolibri_judge_waves.py",
           "docs/KOLIBRI_GENERATION_WAVES_20261005.md")
WORKER_FREEZE = "13f3ed1277a86e6aca2fcf111547a32e677988f3"
WIDTHS = {"source": 2, "final": 4}
JUDGE_CONCURRENCY = 8
check = prod.check


def prefix(collection):
    names = ["http/events.jsonl", "judges/events.jsonl"]
    result = {"journals": {}, "raw": {}}
    for name in names:
        path = collection / name
        _no_symlinks(path)
        body = path.read_bytes()
        check(body.endswith(b"\n"), "Incomplete prefix journal")
        read_events(path)
        result["journals"][name] = {"bytes": len(body), "sha256": runtime.sha(body)}
    for path in sorted((collection / "http/raw").glob("*.bin")):
        result["raw"][path.relative_to(collection).as_posix()] = protocol.sha(path)
    return result


def check_prefix(collection, expected):
    for name, spec in expected["journals"].items():
        check(name in {"http/events.jsonl", "judges/events.jsonl"}, "Unknown prefix journal")
        path = collection / name
        _no_symlinks(path)
        body = path.read_bytes()
        check(type(spec["bytes"]) is int and 0 < spec["bytes"] <= len(body)
              and runtime.sha(body[:spec["bytes"]]) == spec["sha256"], "Original sequential prefix changed")
    for name, digest in expected["raw"].items():
        check(Path(name).parts[:2] == ("http", "raw") and len(Path(name).parts) == 3,
              "Unsafe original receipt name")
        _no_symlinks(collection / name)
        check(protocol.sha(collection / name) == digest, "Original raw receipt changed")


def source_hashes():
    return {name: protocol.sha(protocol.ROOT / name) for name in SOURCES}


def build():
    amendment = a5.verify()
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    policy = transport.verify(protocol.ROOT / transport.PLAN)
    root = a5.root()
    with bridge.saved_runner(root, plan, a5.a4.a1.ORIGINAL_PLAN_SHA, amendment, policy, WORKER_FREEZE) as runner:
        check(runner.initial_audit() == runner.receipts.decision("screen_initial"), "Initial audit not passed")
        runner.require_resolved()
        records = runner.receipts.records(verify=True)
        check(not any(r["phase"] == "main" or r["phase"] == "screen" and
                      runner.catalog[r["metadata"]["item_id"]]["block"] > 2 for r in records.values()),
              "Wave freeze must precede all remaining screen/main calls")
        initial = runner.receipts.decision("screen_initial")
    _, events = prod.controller_events(root, "main", a5.a4.a1.ORIGINAL_PLAN_SHA, WORKER_FREEZE)
    check("closed" not in events and "server-ready" in events, "Existing A5 server required")
    return {"schema": "kolibri-generation-waves-v1", "worker_freeze": WORKER_FREEZE,
        "scientific_plan_sha256": a5.a4.a1.ORIGINAL_PLAN_SHA,
        "a5_amendment_sha256": protocol.sha(protocol.ROOT / a5.AMENDMENT),
        "judge_policy_freeze": a5.JUDGE_FREEZE, "wave_widths": WIDTHS,
        "judge_concurrency": JUDGE_CONCURRENCY,
        "judge_waves": deepcopy(judge_waves.POLICY),
        "source_hashes": source_hashes(), "dependency_source_hashes": {
            **amendment["source_hashes"], **amendment["dependency_source_hashes"]},
        "prefix": prefix(root / "collection"), "initial_audit": initial,
        "owned_pod_id": events["created"]["data"]["id"],
        "create_intent_sha256": events["create-intent"]["sha256"],
        "server_ready_sha256": events["server-ready"]["sha256"],
        "deadline_utc": events["create-intent"]["data"]["deadline_utc"],
        "known_outcomes": "Sequential first two screen blocks and their labels are observed; no main outcomes. Timing motivated this operational amendment, not label direction.",
        "forecast": {"source_waves": 64, "final_waves": 64, "margin": "1.30", "cleanup_seconds": "600",
                     "basis": "all post-amendment screen waves, including every slow wave"},
        "same_pod_no_restart": True, "generation_retries": 0, "sampling_changed": False,
        "budget_changed": False, "sequential_prefix_retained": True,
        "batching_numerical_equivalence_claimed": False}


def verify(freeze=None, collection=None):
    value = prod.load(protocol.ROOT / PLAN)
    check(value["schema"] == "kolibri-generation-waves-v1" and value["worker_freeze"] == WORKER_FREEZE
          and value["scientific_plan_sha256"] == a5.a4.a1.ORIGINAL_PLAN_SHA
          and value["a5_amendment_sha256"] == protocol.sha(protocol.ROOT / a5.AMENDMENT)
          and value["judge_policy_freeze"] == a5.JUDGE_FREEZE and value["wave_widths"] == WIDTHS
          and value["judge_concurrency"] == JUDGE_CONCURRENCY
          and value["judge_waves"] == judge_waves.POLICY and judge_waves.WIDTH == JUDGE_CONCURRENCY
          and value["source_hashes"] == source_hashes()
          and value["forecast"] == {"source_waves": 64, "final_waves": 64, "margin": "1.30", "cleanup_seconds": "600",
                                  "basis": "all post-amendment screen waves, including every slow wave"}
          and value["same_pod_no_restart"] is True and value["generation_retries"] == 0
          and value["sampling_changed"] is False and value["budget_changed"] is False
          and value["sequential_prefix_retained"] is True and value["batching_numerical_equivalence_claimed"] is False,
          "Wave policy differs")
    prior = prod.load(protocol.ROOT / a5.AMENDMENT)
    check(value["dependency_source_hashes"] == {**prior["source_hashes"], **prior["dependency_source_hashes"]}
          and all(protocol.sha(protocol.ROOT / n) == d for n, d in value["dependency_source_hashes"].items()),
          "Frozen worker/science/judge source changed")
    if collection is not None:
        check_prefix(collection, value["prefix"])
    if freeze is not None:
        a5.verify(WORKER_FREEZE)
        protocol.verify(protocol.ROOT / protocol.PLAN, freeze)
        subprocess.run(["git", "merge-base", "--is-ancestor", WORKER_FREEZE, freeze], cwd=protocol.ROOT, check=True)
        for name, digest in {**value["source_hashes"], PLAN: protocol.sha(protocol.ROOT / PLAN)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            check(runtime.sha(body) == digest, "Wave source absent from pushed operational freeze")
    return value


def binding(freeze, value):
    return {"operational_freeze": freeze, "worker_freeze": value["worker_freeze"],
            "amendment_sha256": protocol.digest(value), "wave_widths": WIDTHS,
            "judge_concurrency": JUDGE_CONCURRENCY}


def schedule(plan, phase):
    result = []
    for block in plan[phase]:
        if phase == "screen" and block["block"] <= 2:
            continue
        for role, name in (("source", "sources"), ("final", "finals")):
            size = WIDTHS[role]
            for offset in range(0, len(block[name]), size):
                result.append({"id": f"wave:{phase}:{block['block']}:{role}:{offset // size}",
                    "phase": phase, "block": block["block"], "role": role,
                    "item_ids": [item["id"] for item in block[name][offset:offset + size]]})
    return result


class Runner(judge_waves.JudgeWavesMixin, bridge.Runner):
    def __init__(self, *args, wave_plan, wave_freeze, monotonic=time.monotonic, **kwargs):
        self.wave_plan, self.wave_freeze, self.monotonic = deepcopy(wave_plan), wave_freeze, monotonic
        super().__init__(*args, **kwargs)

    def check_sources(self):
        super().check_sources()
        check(self.freeze == self.wave_plan["worker_freeze"], "Wave policy refers to another worker freeze")
        check(self.wave_plan == prod.load(protocol.ROOT / PLAN)
              and all(protocol.sha(protocol.ROOT / n) == d for n, d in self.wave_plan["source_hashes"].items()),
              "Wave source binding changed")

    def wave_audit(self):
        events = self.receipts.events
        decisions = {e["data"]["name"]: e for e in events if e["kind"] == "decision"}
        policy = decisions.get("generation_waves")
        check(policy is not None and policy["data"]["value"] == binding(self.wave_freeze, self.wave_plan),
              "Wave operational binding absent")
        initial = self.receipts.decision("screen_initial")
        check(initial == self.wave_plan["initial_audit"], "Original initial audit differs")
        prefix_bytes = b"".join((common.canonical(e) + "\n").encode() for e in events[:policy["seq"] - 1])
        check({"bytes": len(prefix_bytes), "sha256": runtime.sha(prefix_bytes)}
              == self.wave_plan["prefix"]["journals"]["http/events.jsonl"],
              "Operational policy must immediately follow the frozen prefix")
        records = self.receipts.records(verify=True)
        order = {(e["data"]["call_id"], e["kind"]): e["seq"] for e in events if e["kind"] in {"dispatch", "response"}}
        declared = schedule(self.plan, "screen") + schedule(self.plan, "main")
        allowed = {w["id"] + suffix for w in declared for suffix in (":open", ":closed")}
        check(all(not name.startswith("wave:") or name in allowed for name in decisions), "Unknown wave decision")
        seen, completed, blocked, previous = set(), [], False, policy["seq"]
        for wave in declared:
            opened, closed = decisions.get(wave["id"] + ":open"), decisions.get(wave["id"] + ":closed")
            if opened is None:
                check(closed is None, "Wave closure lacks dispatch authority")
                blocked = True
                continue
            check(not blocked and opened["seq"] > previous, "Wave order or barrier changed")
            value = opened["data"]["value"]
            started = _utc(value["started_utc"])
            check(_utc(events[previous - 1]["utc"]) <= started <= _utc(opened["utc"]),
                  "Wave preflight clock is outside its ordered interval")
            expected, skipped = [], []
            for item_id in wave["item_ids"]:
                item = self.catalog[item_id]
                if item["kind"] == "final":
                    donor = records.get("gen:" + item["source_id"])
                    check(donor is not None and donor["status"] == "received"
                          and order[(donor["call_id"], "response")] < opened["seq"], "Wave lacks settled donor")
                    if donor["projection"]["missing"]:
                        skipped.append(item_id)
                        continue
                expected.append("gen:" + item_id)
            check(value == {**wave, "call_ids": expected, "skipped_missing_donor": skipped,
                            "started_utc": value["started_utc"]}, "Wave inventory differs")
            observed = [call for call in expected if call in records]
            check(all(opened["seq"] < order[(call, "dispatch")] for call in observed), "Wave dispatch precedes admission")
            seen.update(observed)
            if closed is None:
                blocked = True
                continue
            check(observed == expected, "Closed wave has missing dispatches")
            result = closed["data"]["value"]
            check(set(result) == {"id", "call_ids", "elapsed_seconds", "responses_sha256", "pass"}
                  and result["id"] == wave["id"] and result["call_ids"] == expected
                  and type(result["pass"]) is bool and isinstance(result["elapsed_seconds"], str)
                  and Decimal(result["elapsed_seconds"]).is_finite()
                  and Decimal(result["elapsed_seconds"]) >= 0, "Invalid wave closure")
            check(all((call, "response") in order and order[(call, "response")] < closed["seq"] for call in expected),
                  "Wave closed before draining responses")
            check(result["responses_sha256"] == protocol.digest({call: records[call]["body"] for call in expected})
                  and (not result["pass"] or all(records[call]["status"] == "received" for call in expected)),
                  "Wave response proof differs")
            seconds = Decimal(result["elapsed_seconds"])
            clock_seconds = Decimal(str((_utc(closed["utc"]) - started).total_seconds()))
            check(abs(seconds - clock_seconds) <= 2 and all(seconds + 1 >= Decimal(str(records[c]["elapsed_seconds"])) for c in expected),
                  "Wave elapsed time inconsistent with saved request/UTC clocks")
            if expected:
                check(max(order[(c, "dispatch")] for c in expected) < min(order[(c, "response")] for c in expected),
                      "Wave was not admitted before responses")
            completed.append({**wave, **result})
            blocked, previous = not result["pass"], closed["seq"]
        subsequent = {call for call, row in records.items() if row["channel"] == "local"
                      and order[(call, "dispatch")] > policy["seq"]}
        check(seen == subsequent, "Local dispatch outside declared waves")
        return completed

    def audit(self):
        report = super().audit()
        check_prefix(self.receipts.root.parent, self.wave_plan["prefix"])
        waves = self.wave_audit()
        return {**report, "wave_policy": binding(self.wave_freeze, self.wave_plan),
                "completed_waves": len(waves), "failed_waves": sum(not w["pass"] for w in waves)}

    def run_wave(self, wave):
        start = self.monotonic()
        started_utc = datetime.now(timezone.utc).isoformat()
        check(wave in schedule(self.plan, wave["phase"]), "Unplanned wave")
        existing = self.receipts.decision(wave["id"] + ":closed")
        if existing is not None:
            self.wave_audit()
            check(existing["pass"], "Prior failed wave blocks dispatch")
            return existing
        check(not self.stop.is_set() and self.receipts.decision(wave["id"] + ":open") is None,
              "Stopped or incomplete wave; never resend")
        completed = self.wave_audit()
        declared = schedule(self.plan, "screen") + schedule(self.plan, "main")
        check(all(item["pass"] for item in completed) and len(completed) < len(declared)
              and wave == declared[len(completed)], "Wave must be next in frozen order")
        if wave["phase"] == "main":
            check(self.receipts.decision("main_admission") is not None, "Main admission absent")
            if wave == schedule(self.plan, "main")[0]:
                self._stage("main")
        self.check_sources()
        self.require_resolved(channel="local")
        requests, skipped = [], []
        for item_id in wave["item_ids"]:
            item, donor = self.catalog[item_id], None
            spec = self.plan["models"][item["model"]]
            if item["kind"] == "final":
                parsed = self.parsed_call("gen:" + item["source_id"], spec)
                check(parsed is not None, "Wave donor absent")
                if parsed["missing"]:
                    skipped.append(item_id); continue
                donor = parsed["response"]
            request = runtime.local_request(spec, item_id, common.messages(item, donor), item["seed"])
            check(self.receipts.existing("gen:" + item_id) is None, "Unexpected existing wave request")
            check(self.guard is not None and self.local_sender is not None, "Live wave guard/sender absent")
            self.guard.before_call("local", wave["phase"], spec, request)
            requests.append((item, spec, request))
        check(not self.stop.is_set(), "External stop before wave admission")
        calls = ["gen:" + item["id"] for item, _, _ in requests]
        self.receipts.append("decision", {"name": wave["id"] + ":open", "value": {
            **wave, "call_ids": calls, "skipped_missing_donor": skipped, "started_utc": started_utc}})
        for item, _, request in requests:
            self.receipts.append("dispatch", {"call_id": "gen:" + item["id"], "request": request,
                "request_sha256": protocol.digest(request), "phase": wave["phase"], "channel": "local",
                "metadata": {"kind": "generation", "item_id": item["id"], "role": item["kind"],
                    "model": item["model"], "block": item["block"], "freeze": self.freeze, "plan_sha256": self.plan_hash}})
        def send(request):
            if self.stop.is_set():
                return runtime.HTTPReceipt(None, b"", 0., "StoppedBeforeSend")
            try:
                value = self.local_sender(deepcopy(request))
                check(isinstance(value, runtime.HTTPReceipt), "Exact HTTP receipt required")
                return value
            except Exception:
                return runtime.HTTPReceipt(None, b"", 0., "TransportException")
        with ThreadPoolExecutor(max_workers=WIDTHS[wave["role"]]) as pool:
            futures = {}
            for item, spec, request in requests:
                try:
                    futures[pool.submit(send, request)] = (item, spec)
                except Exception:
                    self.stop.set()
                    self.receipts.finish("gen:" + item["id"],
                        runtime.HTTPReceipt(None, b"", 0., "WorkerSubmissionFailure"), None, "WorkerSubmissionFailure")
            for future in as_completed(futures):
                item, spec = futures[future]
                try:
                    receipt = future.result()
                except BaseException:
                    receipt = runtime.HTTPReceipt(None, b"", 0., "TransportException")
                result, problem = None, None
                try:
                    raw = runtime.strict_json(receipt.body)
                    runtime.public_response(receipt.body)
                    if receipt.error is not None or receipt.status != 200:
                        raise ValueError("Incomplete local HTTP receipt")
                    result = runtime.local_result(spec, raw)
                except Exception as error:
                    problem = type(error).__name__
                self.receipts.finish("gen:" + item["id"], receipt, result, problem)
                if problem:
                    self.stop.set()
        self.audit()
        records = self.receipts.records()
        result = {"id": wave["id"], "call_ids": calls, "elapsed_seconds": str(self.monotonic() - start),
            "responses_sha256": protocol.digest({call: records[call]["body"] for call in calls}),
            "pass": not self.stop.is_set() and all(records[call]["status"] == "received" for call in calls)}
        self.receipts.append("decision", {"name": wave["id"] + ":closed", "value": result})
        self.wave_audit()
        check(result["pass"], "Wave failed or stopped; all in-flight receipts retained")
        return result

    def generate_blocks(self, phase, initial=False):
        check(not initial, "Sequential initial barrier is immutable")
        self._stage(phase, initial=False)
        for wave in schedule(self.plan, phase):
            self.run_wave(wave)
        return self.complete_generation(phase)

    def main_admission(self, **evidence):
        original = super().main_admission(**evidence)
        waves = self.wave_audit()
        screen = [w for w in waves if w["phase"] == "screen"]
        check(len(screen) == 20 and all(w["pass"] for w in screen), "Complete fixed batched screen timing required")
        means = {role: sum((Decimal(w["elapsed_seconds"]) for w in screen if w["role"] == role), Decimal(0)) / 10
                 for role in WIDTHS}
        check(evidence["remaining_overhead_seconds"] == "600", "Cleanup reserve changed")
        seconds = Decimal("1.30") * (64 * means["source"] + 64 * means["final"]) + 600
        gpu = Decimal(evidence["gpu_spent_usd"]) + seconds * Decimal(evidence["gpu_hourly_rate_usd"]) / 3600
        api = Decimal(original["judge_completion_usd"])
        total = gpu + api + Decimal(evidence["storage_bound_usd"])
        fits = (original["qualified"] and gpu <= 25 and api <= 45 and total <= 75
                and Decimal(evidence["storage_bound_usd"]) <= 5
                and seconds <= Decimal(evidence["gpu_remaining_seconds"]))
        return {**original, "fits": fits, "main_seconds_with_margin": str(seconds), "gpu_completion_usd": str(gpu),
            "combined_completion_usd": str(total), "wave_timing_means": {k: str(v) for k, v in means.items()},
            "wave_forecast": self.wave_plan["forecast"], "sequential_forecast_preserved": original}


@contextmanager
def saved_runner(root, plan, amendment, policy, wave_plan, wave_freeze):
    collection = root / "collection"
    check(prod.load(collection / "runtime.json") == prod.binding(plan, WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA)
          and protocol.sha(collection / "PLAN.json") == a5.a4.a1.ORIGINAL_PLAN_SHA
          and prod.load(collection / "JUDGE_TRANSPORT.json") == policy
          and (collection / "AMENDMENT.json").read_bytes() == (protocol.ROOT / a5.AMENDMENT).read_bytes()
          and (collection / "WAVES.json").read_bytes() == (protocol.ROOT / PLAN).read_bytes(), "Saved wave binding differs")
    with tempfile.TemporaryDirectory(prefix="kolibri-waves-audit-") as tmp:
        destination = Path(tmp).resolve()
        for name in ("http", "judges"):
            for path in [collection / name, *(collection / name).rglob("*")]:
                _no_symlinks(path)
            shutil.copytree(collection / name, destination / name)
        with Ledger(destination / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                runtime.ReceiptJournal(destination / "http", WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA) as receipts:
            check(receipts.decision("judge_transport") == bridge.bridge_binding(WORKER_FREEZE, amendment, policy),
                  "Saved original judge/worker binding differs")
            yield Runner(plan, WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA, ledger, receipts, amendment=amendment,
                         transport_plan=policy, wave_plan=wave_plan, wave_freeze=wave_freeze)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=prod.PHASES, default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    if args.build:
        check(not args.execute and args.freeze is None, "Build is offline only")
        path = protocol.ROOT / PLAN
        write_once(path, build())
        print(protocol.canonical({"path": PLAN, "sha256": protocol.sha(path)})); return
    root = args.run_dir.absolute() if args.run_dir else a5.root()
    check(args.execute == (args.phase != "audit") and (not args.execute or args.run_dir is None), "Invalid wave execution scope")
    check(args.phase not in {"fixtures", "generate-screen-initial", "judge-screen-initial"}, "Original prefix cannot rerun")
    check(args.freeze is not None and (not args.abort or args.phase == "stop-server"), "Operational freeze required")
    wave_plan = verify(args.freeze if args.execute and args.phase != "stop-server" else None, root / "collection")
    amendment, plan = a5.verify(), protocol.verify(protocol.ROOT / protocol.PLAN)
    policy = transport.verify(protocol.ROOT / transport.PLAN)
    if not args.execute:
        with saved_runner(root, plan, amendment, policy, wave_plan, args.freeze) as runner:
            result = runner.audit()
    else:
        _, events = prod.controller_events(root, "main", a5.a4.a1.ORIGINAL_PLAN_SHA, WORKER_FREEZE)
        check(events["created"]["data"]["id"] == wave_plan["owned_pod_id"]
              and events["create-intent"]["sha256"] == wave_plan["create_intent_sha256"]
              and events["server-ready"]["sha256"] == wave_plan["server_ready_sha256"], "Owned A5 lifecycle differs")
        check(args.phase == "stop-server" or args.reconciliation is not None, "Fresh reconciliation required")
        record = None if args.phase == "stop-server" else prod.reconciliation(plan, prod.load(args.reconciliation), datetime.now(timezone.utc))
        collection = root / "collection"
        with Ledger(collection / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                runtime.ReceiptJournal(collection / "http", WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA) as receipts:
            if receipts.decision("generation_waves") is None:
                check(prefix(collection) == wave_plan["prefix"], "Prefix advanced before operational binding")
                receipts.append("decision", {"name": "generation_waves", "value": binding(args.freeze, wave_plan)})
            bridge.save_bytes(collection / "WAVES.json", (protocol.ROOT / PLAN).read_bytes())
            runner = Runner(plan, WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA, ledger, receipts,
                amendment=amendment, transport_plan=policy, wave_plan=wave_plan, wave_freeze=args.freeze,
                _freeze_verified=True)
            runner.guard = a5.StudyGuard(root, plan, WORKER_FREEZE, a5.a4.a1.ORIGINAL_PLAN_SHA, ledger, amendment=amendment)
            if args.phase != "stop-server":
                runner.guard.state(running=args.phase in prod.GENERATION)
                admission = {"phase": args.phase, "reconciliation": record, "plan_sha256": runner.plan_hash,
                    "http_head": receipts.events[-1]["sha256"], **bridge.bridge_binding(WORKER_FREEZE, amendment, policy),
                    "generation_waves": binding(args.freeze, wave_plan)}
                write_once(collection / "admissions" / (protocol.digest(admission) + ".json"), admission)
            if args.phase in prod.GENERATION:
                check(type(args.port) is int and 1 <= args.port <= 65535, "Loopback port required")
                runner.local_sender = runtime.http_sender(f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
            if args.phase in prod.JUDGING:
                runner.sender = runtime.http_sender(ENDPOINT, timeout_seconds=600, api_key=prod.local_key(args.env_file))
            previous = {sig: signal.signal(sig, lambda *_: runner.stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                result = prod.phase(runner, args.phase, root, abort=args.abort)
            finally:
                for sig, handler in previous.items(): signal.signal(sig, handler)
    print(protocol.canonical(result))


if __name__ == "__main__":
    main()
