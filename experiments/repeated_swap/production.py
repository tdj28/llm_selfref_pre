"""Prospective local execution and offline audit; no inference on import."""

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.runner import write_once
from . import protocol
from .runner import Runner, StudyLedger
from .transport import live_sender


def account_balance(key):
    request = Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + key})
    with urlopen(request, timeout=30) as response:
        data = json.load(response)["data"]
    return Decimal(str(data["total_credits"])) - Decimal(str(data["total_usage"]))


def root_path():
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"],
                                         cwd=protocol.ROOT, text=True).strip())
    return (protocol.ROOT / common).resolve().parent / "out/repeated-swap-20261004"


def snapshot(runner, root):
    audit = runner.audit()
    folder = root / "snapshots" / f"{len(runner.ledger.rows()):06d}"
    write_once(folder / "audit.json", audit)
    write_once(folder / "rows.json", runner.rows("main"))
    return audit


def reconstruct_admission(root, plan, freeze, plan_hash):
    stored = json.loads((root / "admission.json").read_text())
    prefix = stored["journal_prefix"]
    raw = (root / "raw/events.jsonl").read_bytes()
    size = prefix["bytes"]
    if type(size) is not int or not 0 < size <= len(raw) or not raw[:size].endswith(b"\n"):
        raise Halted("Invalid admission prefix length")
    import hashlib
    if hashlib.sha256(raw[:size]).hexdigest() != prefix["sha256"]:
        raise Halted("Admission prefix changed")
    with TemporaryDirectory(prefix="repeated-admission-") as directory:
        path = Path(directory).resolve()
        (path / "events.jsonl").write_bytes(raw[:size])
        with StudyLedger(path, cap="130", screen_cap="15") as history:
            if len(history.rows()) != prefix["calls"]:
                raise Halted("Admission prefix call count changed")
            prior = Runner(plan, freeze, plan_hash, history)
            rebuilt = prior.admission(stored["credit_snapshot_usd"])
            rebuilt["journal_prefix"] = prefix
    if stored != rebuilt or not rebuilt["pass"]:
        raise Halted("Stored admission did not reconstruct")
    return rebuilt


def funded_limit(ledger, balance):
    """Only future spending may consume the current balance minus the holdback."""
    future = Decimal(str(balance)) - Decimal("45")
    if future <= 0:
        raise Halted("No funded allowance after the external reserve")
    return min(Decimal("130"), ledger.spent() + future)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--phase", choices=["fixtures", "initial", "main", "audit"], default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    plan_file = protocol.ROOT / protocol.PLAN
    plan = protocol.verify(plan_file, args.freeze)
    key, sender = None, None
    if args.execute:
        if args.env_file:
            from dotenv import load_dotenv
            load_dotenv(args.env_file, override=False)
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise Halted("OpenRouter credential unavailable")
        remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/repeated-swap-panel"],
                                         cwd=protocol.ROOT, text=True).split()
        if not remote or remote[0] != args.freeze:
            raise Halted("The complete prospective freeze must be pushed before dispatch")
        sender = live_sender(key)
    elif args.phase != "audit":
        raise Halted("Paid collection requires explicit execute")
    root = root_path()
    write_once(root / "runtime.json", {"freeze": args.freeze, "plan_sha256": protocol.sha(plan_file),
                                      "new_authorization_usd": "130", "external_api_reserve_usd": "45"})
    with StudyLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        runner = Runner(plan, args.freeze, protocol.sha(plan_file), ledger, sender)
        if args.execute:
            ledger.stage_limit = funded_limit(ledger, account_balance(key))
        if args.phase in {"fixtures", "initial"}:
            ledger.stage_limit = min(ledger.stage_limit, Decimal("15"))
        try:
            if args.phase == "fixtures":
                result = runner.run_fixtures()
                write_once(root / "fixture_gate.json", result)
                if not result["pass"]:
                    raise Halted("Fixture failure; no research dispatch")
            elif args.phase == "initial":
                runner.run_blocks("main", initial=True)
                runner.require_complete(initial=True)
            elif args.phase == "main":
                if not (root / "admission.json").exists():
                    admission = runner.admission(account_balance(key))
                    prefix = root / "raw/events.jsonl"
                    admission["journal_prefix"] = {"bytes": prefix.stat().st_size,
                                                    "sha256": protocol.sha(prefix),
                                                    "calls": len(ledger.rows())}
                    write_once(root / "admission.json", admission)
                    if not admission["pass"]:
                        raise Halted("Full-panel forecast exceeds available funds; no partial selection")
                admission = reconstruct_admission(root, plan, args.freeze, protocol.sha(plan_file))
                # Refresh even on resume; the earlier balance is not a spending permit.
                ledger.stage_limit = funded_limit(ledger, account_balance(key))
                original_remaining = sum(Decimal(v) for v in
                    admission["remaining_forecast_with_30pct_reserve_usd"].values())
                bulk_spent = ledger.spent() - Decimal(admission["observed_spend_usd"])
                if ledger.spent() + max(Decimal(0), original_remaining - bulk_spent) > ledger.stage_limit:
                    raise Halted("Fresh funding no longer covers the admitted completion forecast")
                runner.run_blocks("main")
                runner.require_complete()
            report = snapshot(runner, root)
            print(protocol.canonical(report), flush=True)
        except BaseException:
            snapshot(runner, root)
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Repeated-swap operation stopped; immutable receipts and reservations retained.") from None
