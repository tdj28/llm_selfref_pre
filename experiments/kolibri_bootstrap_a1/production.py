"""Original fixed scientific phases, bound to the A1 controller and cost carry."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess

from experiments.kolibri_swap import production as old, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger, _no_symlinks, _sync_directory
from experiments.openrouter_swap.providers import ENDPOINT
from experiments.openrouter_swap.runner import write_once
from . import adapter


class Runner(old.ProductionRunner):
    def __init__(self, *args, amendment, **kwargs):
        self.amendment = deepcopy(amendment)
        self.amendment_hash = protocol.sha(protocol.ROOT / adapter.AMENDMENT)
        super().__init__(*args, **kwargs)

    def check_sources(self):
        super().check_sources()
        old.check(protocol.sha(protocol.ROOT / adapter.AMENDMENT) == self.amendment_hash
                  and all(protocol.sha(protocol.ROOT / name) == digest
                          for name, digest in self.amendment["source_hashes"].items()),
                  "Technical repair changed after phase admission")


def save_bytes(path, body):
    _no_symlinks(path)
    if path.exists():
        old.check(path.read_bytes() == body, "Saved binding bytes differ")
    else:
        with path.open("xb") as handle:
            handle.write(body); handle.flush(); os.fsync(handle.fileno())
        _sync_directory(path.parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=old.PHASES, default="audit")
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reconciliation", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--run-dir", type=Path, help="Read-only audit only")
    parser.add_argument("--tokenizer-dir", type=Path, help="Read-only derived audit only")
    parser.add_argument("--abort", action="store_true")
    args = parser.parse_args(argv)
    try:
        old.check(args.execute == (args.phase != "audit"), "Paid phases require explicit --execute")
        old.check(args.tokenizer_dir is None or args.phase == "audit", "Tokenizer audit is offline only")
        old.check(not args.abort or args.phase == "stop-server", "Abort is cleanup only")
        old.check(not args.execute or args.run_dir is None, "Execution root cannot be overridden")
        old.check(re.fullmatch(r"[0-9a-f]{40}", args.freeze), "Full technical freeze required")
        amendment = adapter.verify(args.freeze if args.execute and args.phase != "stop-server" else None)
        amendment_bytes = (protocol.ROOT / adapter.AMENDMENT).read_bytes()
        path = protocol.ROOT / protocol.PLAN
        plan, plan_hash = protocol.verify(path), protocol.sha(path)
        root = args.run_dir.absolute() if args.run_dir else adapter.root()
        _no_symlinks(root)
        collection = root / "collection"
        if not args.execute:
            old.check((collection / "AMENDMENT.json").read_bytes() == amendment_bytes,
                      "Saved technical amendment differs")
            with old.saved_runner(root, plan, args.freeze, plan_hash) as runner:
                result = runner.serialization_audit(args.tokenizer_dir) if args.tokenizer_dir else runner.audit()
        else:
            old.check(plan["launch_authorized"] and not plan["metadata_blockers"], "Science freeze not executable")
            old.check(args.phase == "stop-server" or args.reconciliation is not None, "Live reconciliation required")
            record = None if args.phase == "stop-server" else old.reconciliation(
                plan, old.load(args.reconciliation), datetime.now(timezone.utc))
            for child in (collection, collection / "runtime.json", collection / "PLAN.json",
                          collection / "AMENDMENT.json", collection / "admissions"):
                _no_symlinks(child)
            with Ledger(collection / "judges", cap="45", screen_cap=old.SCREEN_CAP) as ledger, \
                    runtime.ReceiptJournal(collection / "http", args.freeze, plan_hash) as receipts:
                runner = Runner(plan, args.freeze, plan_hash, ledger, receipts,
                                amendment=amendment, _freeze_verified=True)
                write_once(collection / "runtime.json", old.binding(plan, args.freeze, plan_hash))
                save_bytes(collection / "PLAN.json", path.read_bytes())
                save_bytes(collection / "AMENDMENT.json", amendment_bytes)
                if args.phase != "stop-server":
                    runner.guard = adapter.StudyGuard(root, plan, args.freeze, plan_hash, ledger, amendment=amendment)
                    runner.guard.state(running=args.phase in old.GENERATION)
                    launch = {"phase": args.phase, "reconciliation": record, "freeze": args.freeze,
                              "plan_sha256": plan_hash, "amendment_sha256": runner.amendment_hash,
                              "http_head": receipts.events[-1]["sha256"]}
                    write_once(collection / "admissions" / (protocol.digest(launch) + ".json"), launch)
                if args.phase in old.GENERATION:
                    old.check(type(args.port) is int and 1 <= args.port <= 65535, "Loopback tunnel port required")
                    runner.local_sender = runtime.http_sender(
                        f"http://127.0.0.1:{args.port}/v1/chat/completions", timeout_seconds=300)
                if args.phase in old.JUDGING:
                    runner.sender = runtime.http_sender(ENDPOINT, timeout_seconds=600,
                                                        api_key=old.local_key(args.env_file))
                result = old.phase(runner, args.phase, root, abort=args.abort)
        print(protocol.canonical({"result": result, "amendment_sha256": runtime.sha(amendment_bytes),
                                  "predecessor_cheap_usd": amendment["predecessor"]["cost_usd"]}))
        return 0
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Kolibri A1 phase failed closed; evidence retained. Controller owns cleanup.\n")


if __name__ == "__main__":
    raise SystemExit(main())
