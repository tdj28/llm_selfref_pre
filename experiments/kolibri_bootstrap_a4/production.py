"""Explicit A4 root/worker bridge; frozen judge policy and scientific phases reused."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from experiments import kolibri_judge_transport as transport
from experiments.kolibri_bootstrap_a2.production import save_bytes
from experiments.kolibri_swap import production as prod, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks
from experiments.openrouter_swap.providers import ENDPOINT
from experiments.openrouter_swap.runner import write_once
from . import adapter


def bridge_binding(freeze, amendment, policy):
    prod.check(prod.load(protocol.ROOT / adapter.AMENDMENT) == amendment
               and prod.load(protocol.ROOT / transport.PLAN) == policy, "Bridge input bytes differ")
    return {"schema": "kolibri-a4-runtime-bridge-v1", "worker_freeze": freeze,
            "bridge_freeze": freeze, "amendment_sha256": protocol.sha(protocol.ROOT / adapter.AMENDMENT),
            "judge_operational_freeze": adapter.JUDGE_FREEZE,
            "judge_policy_sha256": protocol.sha(protocol.ROOT / transport.PLAN),
            "judge_policy_original_worker_freeze": policy["worker_freeze"],
            "policy_changed": False}


class Runner(transport.Runner):
    """Replace only frozen A2 constructor/source bindings, not transport behavior."""
    def __init__(self, *args, amendment, transport_plan, sleep=time.sleep, **kwargs):
        self.amendment, self.transport_plan = deepcopy(amendment), deepcopy(transport_plan)
        self.amendment_hash = protocol.sha(protocol.ROOT / adapter.AMENDMENT)
        self.transport_hash = protocol.sha(protocol.ROOT / transport.PLAN)
        self.operational_freeze = adapter.JUDGE_FREEZE
        self.sleep, self._retry_current = sleep, None
        prod.check(self.transport_plan["worker_freeze"] == adapter.A2_FREEZE
                   and self.amendment["judge_policy"] == {
                       "freeze": adapter.JUDGE_FREEZE, "path": transport.PLAN,
                       "sha256": self.transport_hash, "original_worker_freeze": adapter.A2_FREEZE,
                       "policy_changed": False}, "Original judge policy bridge differs")
        # Explicit ancestor constructor bypasses only A2's hardcoded plan/root binding.
        # The inherited exchange/audit/stop/retry/refusal implementations remain exact.
        prod.ProductionRunner.__init__(self, *args, **kwargs)
        stopped = self.stop.is_set()
        self.stop = transport.StopSignal()
        if stopped:
            self.stop.set()

    def check_sources(self):
        runtime.Runner.check_sources(self)
        prod.check(protocol.sha(protocol.ROOT / adapter.AMENDMENT) == self.amendment_hash
                   and prod.load(protocol.ROOT / adapter.AMENDMENT) == self.amendment
                   and all(protocol.sha(protocol.ROOT / name) == digest for name, digest in
                           {**self.amendment["source_hashes"], **self.amendment["dependency_source_hashes"]}.items()),
                   "A4 bridge source binding changed")
        prod.check(protocol.sha(protocol.ROOT / transport.PLAN) == self.transport_hash
                   and prod.load(protocol.ROOT / transport.PLAN) == self.transport_plan
                   and all(protocol.sha(protocol.ROOT / name) == digest
                           for name, digest in self.transport_plan["source_hashes"].items()),
                   "Frozen judge policy binding changed")


@contextmanager
def saved_runner(root, plan, plan_hash, amendment, policy, freeze):
    """Audit disposable copies; preserve both physical ledgers and exact raw bytes."""
    collection = root / "collection"
    prod.check(prod.load(collection / "runtime.json") == prod.binding(plan, freeze, plan_hash)
               and protocol.sha(collection / "PLAN.json") == plan_hash
               and (collection / "AMENDMENT.json").read_bytes() == (protocol.ROOT / adapter.AMENDMENT).read_bytes()
               and prod.load(collection / "JUDGE_TRANSPORT.json") == policy,
               "Saved A4 science/worker/judge policy binding differs")
    with tempfile.TemporaryDirectory(prefix="kolibri-a4-audit-") as temporary:
        destination = Path(temporary).resolve()
        for name in ("http", "judges"):
            for path in [collection / name, *(collection / name).rglob("*")]:
                _no_symlinks(path)
            shutil.copytree(collection / name, destination / name)
        with Ledger(destination / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                runtime.ReceiptJournal(destination / "http", freeze, plan_hash) as receipts:
            prod.check(receipts.decision("judge_transport") == bridge_binding(freeze, amendment, policy),
                       "Saved A4 operational bridge differs")
            yield Runner(plan, freeze, plan_hash, ledger, receipts, amendment=amendment, transport_plan=policy)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True, help="Pushed A4 worker/controller/bridge freeze")
    parser.add_argument("--phase", choices=prod.PHASES, default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-dir", type=Path, help="Offline audit only")
    parser.add_argument("--tokenizer-dir", type=Path, help="Offline derived audit only")
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    try:
        prod.check(args.execute == (args.phase != "audit"), "Non-audit phases require --execute")
        prod.check(args.tokenizer_dir is None or args.phase == "audit", "Tokenizer audit is offline only")
        prod.check(not args.abort or args.phase == "stop-server", "Abort is cleanup only")
        prod.check(not args.execute or args.run_dir is None, "Execution root cannot change")
        prod.check(re.fullmatch(r"[0-9a-f]{40}", args.freeze), "Full A4 freeze required")
        amendment = adapter.verify(args.freeze if args.execute and args.phase != "stop-server" else None)
        policy = transport.verify(protocol.ROOT / transport.PLAN)
        path = protocol.ROOT / protocol.PLAN
        plan, plan_hash = protocol.verify(path), protocol.sha(path)
        root = args.run_dir.absolute() if args.run_dir else adapter.root()
        _no_symlinks(root)
        if not args.execute:
            with saved_runner(root, plan, plan_hash, amendment, policy, args.freeze) as runner:
                result = runner.serialization_audit(args.tokenizer_dir) if args.tokenizer_dir else runner.audit()
        else:
            prod.check(plan["launch_authorized"] and not plan["metadata_blockers"], "Science plan not executable")
            prod.check(args.phase == "stop-server" or args.reconciliation is not None, "Live reconciliation required")
            record = None if args.phase == "stop-server" else prod.reconciliation(
                plan, prod.load(args.reconciliation), datetime.now(timezone.utc))
            collection = root / "collection"
            with Ledger(collection / "judges", cap="45", screen_cap=prod.SCREEN_CAP) as ledger, \
                    runtime.ReceiptJournal(collection / "http", args.freeze, plan_hash) as receipts:
                binding = bridge_binding(args.freeze, amendment, policy)
                if receipts.decision("judge_transport") is None:
                    prod.check(not receipts.records() and not ledger.rows(), "A4 bridge must precede all calls")
                    receipts.append("decision", {"name": "judge_transport", "value": binding})
                prod.check(receipts.decision("judge_transport") == binding, "A4 operational bridge changed")
                runner = Runner(plan, args.freeze, plan_hash, ledger, receipts, amendment=amendment,
                                transport_plan=policy, _freeze_verified=True)
                write_once(collection / "runtime.json", prod.binding(plan, args.freeze, plan_hash))
                for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", adapter.AMENDMENT),
                                     ("JUDGE_TRANSPORT.json", transport.PLAN)):
                    save_bytes(collection / name, (protocol.ROOT / source).read_bytes())
                if args.phase != "stop-server":
                    runner.guard = adapter.StudyGuard(root, plan, args.freeze, plan_hash, ledger, amendment=amendment)
                    runner.guard.state(running=args.phase in prod.GENERATION)
                    launch = {"phase": args.phase, "reconciliation": record, **binding,
                              "plan_sha256": plan_hash, "http_head": receipts.events[-1]["sha256"]}
                    write_once(collection / "admissions" / (protocol.digest(launch) + ".json"), launch)
                if args.phase in prod.GENERATION:
                    prod.check(type(args.port) is int and 1 <= args.port <= 65535, "Loopback tunnel port required")
                    runner.local_sender = runtime.http_sender(
                        f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
                if args.phase in prod.JUDGING:
                    runner.sender = runtime.http_sender(ENDPOINT, timeout_seconds=600, api_key=prod.local_key(args.env_file))
                result = prod.phase(runner, args.phase, root, abort=args.abort)
        print(protocol.canonical(result))
        return 0
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Kolibri A4 halted; raw evidence and costs retained. Controller owns cleanup.\n")


if __name__ == "__main__":
    raise SystemExit(main())
