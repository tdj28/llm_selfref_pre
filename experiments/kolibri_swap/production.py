"""Explicit local phases; the separate controller owns SSH and pod deletion.

No plan generation or automatic phase advancement. ``audit`` copies saved
ledgers to a disposable directory and makes no network or credential access.
Execution uses protocol.PLAN and the shared controller's canonical run root.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks, _sync_directory
from experiments.openrouter_swap.providers import ENDPOINT, _amount, reservation
from experiments.openrouter_swap.runner import write_once
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc
from . import controller, gpu_smoke, protocol, runtime

PHASES = ("fixtures", "generate-screen-initial", "judge-screen-initial", "generate-screen",
          "judge-screen", "main-admission", "generate-main", "stop-server", "judge-main", "audit")
GENERATION = {"fixtures", "generate-screen-initial", "generate-screen", "generate-main"}
JUDGING = {"fixtures", "judge-screen-initial", "judge-screen", "judge-main"}
SCREEN_CAP = "10"


def check(condition, message):
    if not condition:
        raise Halted(message)


def load(path):
    path = Path(path)
    _no_symlinks(path)
    return runtime.strict_json(path.read_bytes())


def local_key(env_file=None):
    """Same private-file convention as the existing API production adapters."""
    if env_file is None:
        value = os.environ.get("OPENROUTER_API_KEY")
    else:
        from dotenv import dotenv_values
        path = Path(env_file).absolute()
        _no_symlinks(path)
        check(path.is_file() and not path.stat().st_mode & 0o077, "Credential file is not private")
        value = dotenv_values(path, interpolate=False).get("OPENROUTER_API_KEY")
    check(isinstance(value, str) and value and not any(c.isspace() for c in value),
          "Local judge credential unavailable")
    return value


def reconciliation(plan, record, now):
    check(isinstance(record, dict) and set(record) == {
        "as_of", "openrouter_prior_and_reserved_usd", "runpod_prior_and_reserved_usd", "source_hashes"},
        "Exact live cumulative reconciliation required")
    age = (now - _utc(record["as_of"])).total_seconds()
    check(0 <= age <= 900, "Reconciliation must be current at phase admission")
    budget = plan["budget"]
    for account, allowance in (("openrouter", "judges_usd"), ("runpod", "gpu_usd")):
        prior = max(_amount(record[account + "_prior_and_reserved_usd"]),
                    _amount(budget[account + "_reserved_prior_usd"]))
        check(prior + _amount(budget[allowance]) + _amount(budget[account + "_external_commitments_usd"])
              <= _amount(budget[account + "_account_cap_usd"]), "Cumulative account allowance exceeded")
    evidence = record["source_hashes"]
    check(isinstance(evidence, dict) and evidence, "Reconciliation evidence absent")
    for name, digest in evidence.items():
        path = Path(name)
        frozen = (plan.get("metadata", {}).get("spend_reconciliation", {}).get("source_hashes", {}).get(name)
                  == digest == plan.get("source_hashes", {}).get(name))
        check(path.parts and path.as_posix() == name and not path.is_absolute() and ".." not in path.parts
              and (path.parts[0] in {"data", "out", "provenance"} or frozen)
              and path.suffix in {".json", ".jsonl"} and re.fullmatch(r"[0-9a-f]{64}", str(digest)),
              "Unsafe reconciliation evidence path")
        target = protocol.ROOT / path
        _no_symlinks(target)
        check(protocol.sha(target) == digest, "Reconciliation evidence changed")
    return record


def controller_events(root, kind, plan_hash, freeze):
    """Reuse the controller's canonical validator without its creating constructor."""
    path = root / "controller" / kind / "events.jsonl"
    _no_symlinks(path)
    reader = object.__new__(EventLedger)
    reader.path, reader.plan, reader.freeze = path, plan_hash, freeze
    reader.ids, reader.anchor = frozenset(), None
    with path.open("rb") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        rows = reader._read(handle.fileno())
    check(rows, "Controller ledger absent")
    events = {r["id"]: r for r in rows}
    intent, created = events["create-intent"]["data"], events["created"]["data"]
    check(intent["plan_sha256"] == plan_hash and intent["freeze_commit"] == freeze
          and re.fullmatch(re.escape(controller.PREFIX) + kind + r"-[0-9a-f]{12}", created["name"])
          and created["name"] == intent["payload"]["name"] and created["id"] not in intent["blocked"],
          "Controller ownership or source binding differs")
    return rows, events


def closed_receipt(root, kind, plan_hash, freeze, *, smoke=False):
    rows, events = controller_events(root, kind, plan_hash, freeze)
    closed = events["closed"]["data"]
    check(closed["get_status"] == 404 and closed["pod_id"] == events["created"]["data"]["id"],
          "Direct owned-pod deletion receipt required")
    base = root / "controller" / kind
    receipt = load(base / "final-retrieval.json")
    check(events.get(receipt["id"]) == receipt and receipt["data"]["pod_id"] == closed["pod_id"]
          and receipt["data"].get("retrieval_verified") is True
          and receipt["data"].get("recovery_failed") is not True,
          "Final retrieval is not in the controller ledger")
    directory = Path(receipt["data"]["directory"])
    _no_symlinks(directory)
    check(directory.is_absolute() and directory.parent == base / "retrievals", "Foreign retrieval path")
    artifacts = receipt["data"]["artifacts"]
    check(isinstance(artifacts, dict) and artifacts, "Retrieved artifact inventory absent")
    controller.check_manifest(artifacts)
    actual = set()
    for path in directory.rglob("*"):
        _no_symlinks(path)
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    check(actual == set(artifacts), "Extra or missing retrieved artifact")
    for name, digest in artifacts.items():
        check(not Path(name).is_absolute() and ".." not in Path(name).parts
              and protocol.sha(directory / name) == digest, "Retrieved artifact hash mismatch")
    cost = _amount(closed["compute_upper_bound_usd"])
    check(cost <= controller.CAPS[kind], "Controller cost exceeded its allowance")
    if smoke:
        result = load(directory / "gpu-smoke.json")
        check(result.get("schema") == "kolibri-tiny-qualification-v1" and result.get("status") == "passed"
              and result.get("mode") == "gpu" and result.get("scientific_generation") is False
              and result.get("expected_versions") == gpu_smoke.VERSIONS
              and result.get("upstream") == {"revision": gpu_smoke.UPSTREAM_SHA, "source_sha256": gpu_smoke.SOURCE_HASHES}
              and result.get("gpu", {}).get("official_routing_cpu_cuda") is True
              and load(directory / "exit.json")["exit_code"] == 0,
              "Saved CUDA qualification did not pass")
        gpu_smoke.verify_versions(result["versions"])
    return {"cost_usd": str(cost), "ledger_sha256": rows[-1]["sha256"],
            "retrieval_sha256": receipt["sha256"], "closed_sha256": events["closed"]["sha256"]}


class StudyGuard:
    """Local saved evidence only; full call horizons and unresolved API reserves count."""
    def __init__(self, root, plan, freeze, plan_hash, ledger, clock=None):
        self.root, self.plan, self.freeze, self.plan_hash, self.ledger = root, plan, freeze, plan_hash, ledger
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cheap = closed_receipt(root, "cheap", plan_hash, freeze, smoke=True)

    def state(self, horizon=0, *, running=False, permit_stop=False):
        rows, events = controller_events(self.root, "main", self.plan_hash, self.freeze)
        intent = events["create-intent"]["data"]
        now = _utc(self.clock())
        rate = _amount(intent["quote"]["hourly_rate_usd"])
        storage = _amount(intent["quote"]["storage_hourly_usd"])
        check(0 < rate <= _amount(self.plan["budget"]["gpu_hourly_usd"])
              and storage <= controller.STORAGE, "Unexpected rental rates")
        if "closed" in events:
            check(not running, "Generation server has been deleted")
            saved = closed_receipt(self.root, "main", self.plan_hash, self.freeze)
            main, remaining, active = _amount(saved["cost_usd"]), Decimal(0), False
        else:
            check("worker-started" in events and events["worker-started"]["data"]["pod_id"] == events["created"]["data"]["id"],
                  "Owned worker start receipt missing")
            check(permit_stop or not (self.root / "controller/main/STOP_SERVER").exists(), "Server cleanup was requested")
            health = [r["data"] for r in rows if r["id"].startswith("health:")]
            check(permit_stop or health and health[-1]["worker"].get("ready") is True
                  and "exit.json" not in health[-1]["worker"], "Saved server readiness absent")
            elapsed = max(Decimal(str((now - _utc(intent["created_utc"])).total_seconds())),
                          max((_amount(r["data"]["elapsed_seconds"]) for r in rows
                               if "elapsed_seconds" in r["data"]), default=Decimal(0)))
            check(elapsed >= 0, "Clock precedes server creation")
            main = (elapsed + Decimal(horizon)) * (rate + storage) / 3600
            main = max(main, max((_amount(r["data"]["upper_bound_usd"]) for r in rows
                                 if r["id"].startswith("accounting:")), default=Decimal(0)))
            remaining = Decimal(str((_utc(intent["cleanup_deadline_utc"]) - now).total_seconds()))
            check(permit_stop or now.timestamp() + horizon <= _utc(intent["deadline_utc"]).timestamp(),
                  "Worker deadline cannot fit the full HTTP horizon")
            active = True
        gpu = main + _amount(self.cheap["cost_usd"])
        check(permit_stop or main <= controller.CAPS["main"] and gpu <= Decimal("25"), "GPU allowance exhausted")
        return {"gpu_usd": gpu, "main_usd": main, "remaining_seconds": remaining, "active": active,
                "controller_sha256": rows[-1]["sha256"]}

    def before_call(self, channel, phase, spec, request):
        seconds = 300 if channel == "local" else 600
        state = self.state(seconds, running=channel == "local")
        api = self.ledger.spent() + (reservation(spec, request) if channel == "judge" else 0)
        budget = self.plan["budget"]
        storage = _amount(budget["storage_recovery_usd"])
        check(api <= _amount(budget["judges_usd"]) and state["gpu_usd"] + api + storage <= Decimal("75"),
              "Whole-study reservation exceeds allowance")
        if phase in {"fixtures", "screen"}:
            check(state["gpu_usd"] + api + storage <= Decimal("20"), "Combined pilot stop-loss reached")

    def admission(self, runner):
        state = self.state(running=True)
        result = runner.main_admission(gpu_spent_usd=str(state["gpu_usd"]),
            gpu_hourly_rate_usd=self.plan["budget"]["gpu_hourly_usd"],
            gpu_remaining_seconds=str(max(0, state["remaining_seconds"])),
            storage_bound_usd=self.plan["budget"]["storage_recovery_usd"], remaining_overhead_seconds="600")
        # The controller's main allowance includes storage and retrieval time too.
        duration = _amount(result["main_seconds_with_margin"])
        check(state["main_usd"] + duration * (_amount(self.plan["budget"]["gpu_hourly_usd"])
              + controller.STORAGE) / 3600 <= controller.CAPS["main"], "Whole main cannot fit controller allowance")
        return result


class ProductionRunner(runtime.Runner):
    guard = None

    def _exchange(self, call_id, request, phase, metadata, channel, sender, spec):
        with self._channel_locks[channel]:
            if sender is not None and self.receipts.existing(call_id) is None:
                check(self.guard is not None, "Live study guard absent")
                self.guard.before_call(channel, phase, spec, request)
            return super()._exchange(call_id, request, phase, metadata, channel, sender, spec)


def checkpoint(runner, name, value):
    name = "production:" + name
    prior = runner.receipts.decision(name)
    check(prior is None or prior == value, "Saved phase checkpoint differs")
    if prior is None:
        runner.receipts.append("decision", {"name": name, "value": value})
    return value


def phase(runner, name, root, *, abort=False):
    check(name in PHASES, "Unknown phase")
    if name == "fixtures":
        result = runner.run_fixtures()
    elif name in {"generate-screen-initial", "generate-screen", "generate-main"}:
        target = "main" if name == "generate-main" else "screen"
        if target == "main":
            check(runner.guard.admission(runner)["fits"], "Current whole-main admission failed")
        result = runner.generate_blocks(target, initial=name.endswith("initial"))
    elif name in {"judge-screen-initial", "judge-screen", "judge-main"}:
        target, initial = ("main" if name == "judge-main" else "screen"), name.endswith("initial")
        runner.complete_generation(target, initial)
        if target == "main":
            closed_receipt(root, "main", runner.plan_hash, runner.freeze)
        runner.judge_blocks(target, initial)
        runner.complete(target, initial)
        if initial:
            result = runner.initial_audit()
            runner.approve_initial(result)
        elif target == "screen":
            result = runner.qualification()
        else:
            result = {"complete": True, "rows": len(runner.rows("main")), "audit": runner.audit()}
    elif name == "main-admission":
        check(not any(r["phase"] == "main" for r in runner.receipts.records().values()), "Admission must precede main calls")
        result = runner.guard.admission(runner)
        check(result["fits"], "Main qualification or whole-completion forecast failed")
        prior = runner.receipts.decision("main_admission")
        if prior is not None:
            check(prior == runner.main_admission(**prior["evidence"]), "Saved main admission differs")
            result = prior
        else:
            runner.approve_main(result)
    elif name == "stop-server":
        result = {"operational_abort": bool(abort), "deletion_verified": False}
        if not abort:
            result["generation"] = runner.complete_generation("main")
        runner.audit()
        # This local marker requests the existing owned controller's cleanup.
        # It is never represented as a deletion receipt or scientific completion.
        controller_events(root, "main", runner.plan_hash, runner.freeze)
        write_once(root / "controller/main/STOP_SERVER", {"freeze": runner.freeze,
            "plan_sha256": runner.plan_hash, **result})
    else:
        return runner.audit()
    if name not in {"generate-screen-initial", "generate-screen", "generate-main"}:
        return checkpoint(runner, name, result)
    return result


def binding(plan, freeze, plan_hash):
    return {"schema": "kolibri-production-v1", "plan_path": protocol.PLAN, "freeze": freeze,
            "plan_sha256": plan_hash, "judge_cap_usd": "45", "judge_screen_cap_usd": SCREEN_CAP,
            "generation_cost_channel": "controller", "judge_cost_channel": "judges"}


@contextmanager
def saved_runner(root, plan, freeze, plan_hash):
    """Verification must not create even lock files in the original evidence."""
    check(load(root / "collection/runtime.json") == binding(plan, freeze, plan_hash), "Runtime binding differs")
    check(protocol.sha(root / "collection/PLAN.json") == plan_hash, "Saved plan differs")
    source = root / "collection"
    with tempfile.TemporaryDirectory(prefix="kolibri-audit-") as tmp:
        temporary = Path(tmp).resolve()
        for name in ("http", "judges"):
            for path in [source / name, *(source / name).rglob("*")]:
                _no_symlinks(path)
            shutil.copytree(source / name, temporary / name)
        with Ledger(temporary / "judges", cap="45", screen_cap=SCREEN_CAP) as ledger, \
                runtime.ReceiptJournal(temporary / "http", freeze, plan_hash) as receipts:
            yield runtime.Runner(plan, freeze, plan_hash, ledger, receipts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, default="audit")
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-dir", type=Path, help="Read-only audit only")
    parser.add_argument("--tokenizer-dir", type=Path,
                        help="Audit only: local frozen config/tokenizer files for derived full contexts")
    parser.add_argument("--abort", action="store_true", help="Stop-server only; preserves incomplete collection")
    args = parser.parse_args(argv)
    try:
        check(args.execute == (args.phase != "audit"), "Non-audit phases require explicit --execute")
        check(args.tokenizer_dir is None or args.phase == "audit", "Tokenizer reconstruction is offline audit only")
        check(not args.abort or args.phase == "stop-server", "Abort is cleanup only")
        check(not args.execute or args.run_dir is None, "Execution must use the canonical run root")
        check(re.fullmatch(r"[0-9a-f]{40}", args.freeze), "Full source freeze required")
        path = protocol.ROOT / protocol.PLAN
        # Cleanup cannot wait on a network proof; its owned local intent is bound
        # below. Only phases that can collect/judge require a fresh pushed proof.
        plan = protocol.verify(path, args.freeze if args.execute and args.phase != "stop-server" else None)
        plan_hash = protocol.sha(path)
        root = (args.run_dir.absolute() if args.run_dir else controller.canonical_root())
        _no_symlinks(root)
        if not args.execute:
            with saved_runner(root, plan, args.freeze, plan_hash) as runner:
                result = (runner.serialization_audit(args.tokenizer_dir) if args.tokenizer_dir is not None
                          else runner.audit())
        else:
            check(plan["launch_authorized"] and not plan["metadata_blockers"], "Source freeze is not executable")
            check(args.phase == "stop-server" or args.reconciliation is not None, "Live reconciliation required")
            record = None if args.phase == "stop-server" else reconciliation(plan, load(args.reconciliation), datetime.now(timezone.utc))
            collection = root / "collection"
            for child in (collection, collection / "runtime.json", collection / "PLAN.json", collection / "admissions"):
                _no_symlinks(child)
            # No credential is loaded until local qualification/budget admission succeeds.
            with Ledger(collection / "judges", cap="45", screen_cap=SCREEN_CAP) as ledger, \
                    runtime.ReceiptJournal(collection / "http", args.freeze, plan_hash) as receipts:
                runner = ProductionRunner(plan, args.freeze, plan_hash, ledger, receipts, _freeze_verified=True)
                write_once(collection / "runtime.json", binding(plan, args.freeze, plan_hash))
                original = path.read_bytes()
                saved = collection / "PLAN.json"
                if saved.exists():
                    check(saved.read_bytes() == original, "Saved plan bytes differ")
                else:
                    with saved.open("xb") as handle:
                        handle.write(original); handle.flush(); os.fsync(handle.fileno())
                    _sync_directory(collection)
                if args.phase != "stop-server":
                    runner.guard = StudyGuard(root, plan, args.freeze, plan_hash, ledger)
                    runner.guard.state(running=args.phase in GENERATION)
                    launch = {"phase": args.phase, "reconciliation": record, "freeze": args.freeze,
                              "plan_sha256": plan_hash, "http_head": receipts.events[-1]["sha256"]}
                    write_once(collection / "admissions" / (protocol.digest(launch) + ".json"), launch)
                if args.phase in GENERATION:
                    check(type(args.port) is int and 1 <= args.port <= 65535, "Explicit loopback tunnel port required")
                    runner.local_sender = runtime.http_sender(f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
                if args.phase in JUDGING:
                    runner.sender = runtime.http_sender(ENDPOINT, timeout_seconds=600, api_key=local_key(args.env_file))
                result = phase(runner, args.phase, root, abort=args.abort)
        print(protocol.canonical(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Kolibri phase failed closed; saved evidence retained. Controller owns cleanup.\n")


if __name__ == "__main__":
    raise SystemExit(main())
