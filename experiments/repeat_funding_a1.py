"""Separate, source-bound funding admission; original science and ledger unchanged."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import time
import uuid

from experiments.openrouter_swap.ledger import Halted, _no_symlinks
from experiments.openrouter_swap.runner import write_once
from experiments.repeated_swap import protocol as science, production
from experiments.repeated_swap.runner import Runner, StudyLedger
from experiments.repeated_swap.transport import live_sender

ROOT = Path(__file__).resolve().parents[1]
OLD_FREEZE = "b3ddbdcae9919937ffb67da565b26ec2d0c81f00"
OLD_PLAN_SHA = "aaeaca3ecd4e81e6f88a97c613077485a274f8c21d8825925079ece76f254fdc"
PREFIX = {"bytes": 3101711, "sha256": "6bb8363be09f31b3b71d42c152cc8788f484948352c35e8fb5f5767b85e2887c",
          "calls": 274}
FAILED_SHA = "b14dac9b79378838b9151b3be33c34959fca636363fc7137828508288cb7cd9e"
DIRECTORY = "data/repeated_swap/funding_a1_20261005"
PLAN = DIRECTORY + "/PLAN.json"
ANCHOR = DIRECTORY + "/FAILED_ADMISSION.json"
DOCUMENT = "docs/REPEATED_SWAP_FUNDING_A1_20261005.md"
NEW_SOURCES = ("experiments/repeat_funding_a1.py", "tests/test_repeat_funding_a1.py", DOCUMENT)
CAP, HOLDBACK, FACTOR = Decimal("130"), Decimal("45"), Decimal("1.10")
REFRESH_SECONDS = 60


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def amount(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise Halted("Invalid funding amount") from None
    if isinstance(value, bool) or not result.is_finite() or result < 0:
        raise Halted("Invalid funding amount")
    return result


def git_blob(freeze, name):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise Halted("Full freeze SHA required")
    return subprocess.check_output(["git", "--no-replace-objects", "show", f"{freeze}:{name}"],
                                   cwd=ROOT, env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})


def original_plan():
    path = ROOT / science.PLAN
    if digest(path.read_bytes()) != OLD_PLAN_SHA or git_blob(OLD_FREEZE, science.PLAN) != path.read_bytes():
        raise Halted("Original scientific plan changed")
    plan = science.verify(path)
    for name, expected in plan["source_hashes"].items():
        if digest(git_blob(OLD_FREEZE, name)) != expected:
            raise Halted("Original scientific source changed: " + name)
    return plan


def failed_admission(raw):
    if digest(raw) != FAILED_SHA:
        raise Halted("Failed admission anchor changed")
    value = json.loads(raw)
    if (value["pass"] is not False or value["outcome_selection"] is not False
            or value["journal_prefix"] != PREFIX or value["kolibri_reserve_usd"] != "45"):
        raise Halted("Wrong initial admission")
    return value


def amended_admission(old):
    forecasts = {model: amount(cost) / Decimal("1.30") * FACTOR
                 for model, cost in old["remaining_forecast_with_30pct_reserve_usd"].items()}
    remaining = sum(forecasts.values(), Decimal(0))
    spent, balance = amount(old["observed_spend_usd"]), amount(old["credit_snapshot_usd"])
    return {"schema": "repeated-funding-a1-admission-v1", "pass": remaining <= min(CAP-spent, balance-HOLDBACK),
            "outcome_selection": False, "models": old["models"], "journal_prefix": old["journal_prefix"],
            "observed_spend_usd": str(spent), "reserve_multiplier": str(FACTOR),
            "remaining_forecast_with_10pct_reserve_usd": {m: str(v) for m, v in forecasts.items()},
            "remaining_forecast_usd": str(remaining), "credit_snapshot_usd": str(balance),
            "cap_usd": str(CAP), "external_holdback_usd": str(HOLDBACK),
            "original_failed_admission_sha256": FAILED_SHA}


def build_plan():
    original = original_plan()
    admission = amended_admission(failed_admission((ROOT / ANCHOR).read_bytes()))
    if not admission["pass"]:
        raise Halted("Amended completion forecast still does not fit")
    return {"schema": "repeated-funding-a1-v1", "original_science_freeze": OLD_FREEZE,
            "original_plan": {"path": science.PLAN, "sha256": OLD_PLAN_SHA},
            "authorization": {"incremental_study_cap_usd": "130", "additional_funding_usd": "0",
                              "scope": "Owner-authorized accounting-only reserve reduction before bulk"},
            "change": {"old_multiplier": "1.30", "new_multiplier": "1.10",
                       "scientific_settings_changed": False, "outcome_selection": False},
            "atomic_cap_usd": "130", "external_holdback_usd": "45", "screen_cap_usd": "15",
            "balance_refresh_seconds": REFRESH_SECONDS, "admission": admission,
            "runtime_binding": "Original science freeze stays in request metadata; additional executed wrapper freeze is recorded separately before dispatch",
            "source_hashes": {**original["source_hashes"],
                              **{name: science.sha(ROOT / name) for name in NEW_SOURCES},
                              ANCHOR: FAILED_SHA},
            "input_hashes": {science.PLAN: OLD_PLAN_SHA}}


def verify(path, freeze=None, *, require_pushed=False):
    path = Path(path).resolve()
    if path != (ROOT / PLAN).resolve():
        raise Halted("Use the canonical funding amendment plan")
    plan = json.loads(path.read_bytes())
    if science.canonical(plan) != science.canonical(build_plan()):
        raise Halted("Funding plan or source closure changed")
    if freeze is not None:
        for name, expected in {**plan["source_hashes"], **plan["input_hashes"]}.items():
            if digest(git_blob(freeze, name)) != expected:
                raise Halted("Amendment source absent from operational freeze: " + name)
        if git_blob(freeze, PLAN) != path.read_bytes():
            raise Halted("Amendment plan absent from operational freeze")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if head != freeze or freeze == OLD_FREEZE:
            raise Halted("Checkout must equal the fresh operational freeze")
        if subprocess.run(["git", "merge-base", "--is-ancestor", OLD_FREEZE, freeze],
                          cwd=ROOT, check=False).returncode:
            raise Halted("Operational freeze does not descend from scientific freeze")
    if require_pushed:
        if freeze is None:
            raise Halted("Pushed operational freeze required")
        ref = "refs/heads/" + science.BRANCH
        remote = subprocess.check_output(["git", "ls-remote", "origin", ref], cwd=ROOT, text=True).split()
        if remote != [freeze, ref]:
            raise Halted("Operational freeze must be pushed before bulk dispatch")
    return plan


def verify_prefix(root, plan, *, initial_only=False):
    """Replay only the anchored prefix in a disposable ledger; never rewrite it."""
    root = Path(root)
    for name in ("runtime.json", "admission.json", "raw/events.jsonl"):
        _no_symlinks(root / name)
    runtime = json.loads((root / "runtime.json").read_bytes())
    expected = {"freeze": OLD_FREEZE, "plan_sha256": OLD_PLAN_SHA,
                "new_authorization_usd": "130", "external_api_reserve_usd": "45"}
    if runtime != expected:
        raise Halted("Original runtime record changed")
    old = failed_admission((root / "admission.json").read_bytes())
    raw = (root / "raw/events.jsonl").read_bytes()
    prefix = raw[:PREFIX["bytes"]]
    if (len(prefix) != PREFIX["bytes"] or not prefix.endswith(b"\n")
            or digest(prefix) != PREFIX["sha256"] or initial_only and len(raw) != len(prefix)):
        raise Halted("Initial prefix changed or unfrozen bulk already exists")
    with TemporaryDirectory(prefix="repeated-funding-a1-") as directory:
        path = Path(directory).resolve()
        (path / "events.jsonl").write_bytes(prefix)
        with StudyLedger(path, cap="130", screen_cap="15") as history:
            if len(history.rows()) != PREFIX["calls"]:
                raise Halted("Initial call count changed")
            runner = Runner(plan, OLD_FREEZE, OLD_PLAN_SHA, history)
            # The old constructor checks request integrity. Only costs decide
            # this amendment; no label, response or behavioral threshold is used.
            rebuilt = runner.admission(old["credit_snapshot_usd"])
            rebuilt["journal_prefix"] = PREFIX
    if rebuilt != old:
        raise Halted("Failed initial admission did not reconstruct")
    return amended_admission(rebuilt)


def funding_limit(ledger, balance):
    future = amount(balance) - HOLDBACK
    if future <= 0:
        raise Halted("No funded allowance after the $45 holdback")
    # Pending/unknown reservations may not yet appear in the provider balance.
    # Subtract them instead of counting them as already-paid spending.
    outstanding = sum((amount(r["cost_usd"]) for r in ledger.rows()
                       if r["status"] != "settled"), Decimal(0))
    return min(CAP, ledger.spent() + future - outstanding)


def require_completion_funding(ledger, admission, limit):
    extra = ledger.spent() - amount(admission["observed_spend_usd"])
    if extra < 0 or ledger.spent() + max(Decimal(0), amount(admission["remaining_forecast_usd"])-extra) > limit:
        raise Halted("Fresh balance does not cover the amended completion forecast")


class FundingLedger(StudyLedger):
    """Same immutable journal and atomic cap, with a separate live-funding guard."""
    def enable_funding(self, read_balance, record, clock=time.monotonic):
        self._funding_reader, self._funding_record, self._funding_clock = read_balance, record, clock
        self._funding_time = None
        self.refresh_funding(force=True)

    def refresh_funding(self, *, force=False):
        with self._mutex:
            now = self._funding_clock()
            if self._funding_time is not None and now < self._funding_time:
                raise Halted("Funding clock moved backward")
            if force or self._funding_time is None or now-self._funding_time >= REFRESH_SECONDS:
                balance = amount(self._funding_reader())
                limit = funding_limit(self, balance)
                self._funding_record({"balance_usd": str(balance), "external_holdback_usd": "45",
                                      "spent_and_reserved_usd": str(self.spent()),
                                      "funded_limit_usd": str(min(self.stage_limit, limit))})
                self.stage_limit = min(self.stage_limit, limit)
                self._funding_time = self._funding_clock()
            return self.stage_limit

    def reserve(self, *args, **kwargs):
        with self._mutex:
            if not hasattr(self, "_funding_reader"):
                raise Halted("Live funding guard not enabled")
            self.refresh_funding()
            return super().reserve(*args, **kwargs)


def execute(root, amendment, freeze, key):
    if amendment != verify(ROOT / PLAN, freeze, require_pushed=True):
        raise Halted("Execution amendment differs from its pushed freeze")
    root = Path(root)
    if root.resolve() != production.root_path().resolve():
        raise Halted("Cannot reset the study ledger in a different directory")
    scientific = original_plan()
    operational = root / "funding_a1"
    _no_symlinks(operational)
    with FundingLedger(root / "raw", cap="130", screen_cap="15") as ledger:
        fresh = not (operational / "runtime.json").exists()
        admission = verify_prefix(root, scientific, initial_only=fresh)
        if admission != amendment["admission"]:
            raise Halted("Amended admission differs from its freeze")
        binding = {"original_science_freeze": OLD_FREEZE, "original_plan_sha256": OLD_PLAN_SHA,
                   "actual_operational_freeze": freeze, "amendment_plan_sha256": science.sha(ROOT / PLAN)}
        write_once(operational / "runtime.json", binding)
        write_once(operational / "admission.json", admission)
        runner = Runner(scientific, OLD_FREEZE, OLD_PLAN_SHA, ledger)
        runner.require_resolved()
        runner.audit()
        launch = operational / "launches" / uuid.uuid4().hex
        before = (root / "raw/events.jsonl").read_bytes()
        write_once(launch / "start.json", {**binding, "utc": datetime.now(timezone.utc).isoformat(),
                   "journal_before": {"sha256": digest(before), "bytes": len(before), "calls": len(ledger.rows())},
                   "outcome_selection": False})
        def record(value):
            write_once(launch / "funding" / (uuid.uuid4().hex + ".json"),
                       {**value, "utc": datetime.now(timezone.utc).isoformat(), **binding})
        complete = False
        try:
            ledger.enable_funding(lambda: production.account_balance(key), record)
            require_completion_funding(ledger, admission, ledger.stage_limit)
            runner.sender = live_sender(key)
            runner.run_blocks("main")
            runner.require_complete()
            report = runner.audit()
            complete = True
            return report
        finally:
            after = (root / "raw/events.jsonl").read_bytes()
            write_once(launch / "finish.json", {**binding, "complete": complete,
                       "spent_and_reserved_usd": str(ledger.spent()),
                       "journal_after": {"sha256": digest(after), "bytes": len(after), "calls": len(ledger.rows())}})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args(argv)
    if args.build and args.execute:
        parser.error("Build and paid execution are separate operations")
    if args.execute and not args.freeze:
        parser.error("Execution requires the new operational freeze")
    root = production.root_path()
    if args.build:
        verify_prefix(root, original_plan(), initial_only=True)
        raw = (root / "admission.json").read_bytes()
        failed_admission(raw)
        path = ROOT / ANCHOR
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != raw:
                raise Halted("Existing failed admission anchor differs")
        else:
            with path.open("xb") as handle:
                handle.write(raw)
        write_once(ROOT / PLAN, build_plan())
    amendment = verify(ROOT / PLAN, args.freeze)
    if not args.execute:
        print(science.canonical({"plan_sha256": science.sha(ROOT / PLAN),
                                "source_files": len(amendment["source_hashes"]), "network_calls": 0}))
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
        raise SystemExit("Funding A1 stopped; original admission, receipts and reservations retained.") from None
