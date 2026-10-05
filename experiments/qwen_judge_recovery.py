"""Additive, post-hoc recovery of three technically missing Qwen judgments."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import time
import uuid

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Ledger, Halted, _no_symlinks
from experiments.openrouter_swap.providers import TransportError, _amount, parse_result, receipt_cost, reservation
from experiments.openrouter_swap.runner import write_once
from experiments.openrouter_swap.release import _inventory
from experiments.openrouter_swap_openweights import analysis
from experiments.openrouter_swap_openweights_a2 import production, release
from experiments.openrouter_swap_openweights_a2.prefix import merged, events_from_bytes, read_raw, sha, check

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = "data/openrouter_swap_openweights_a2/main_v1_20261004"
RELEASE_COMMIT = "ad49e88f9cd4235670686ddcd5933ff9b98eb3be"
MANIFEST_SHA = "24b97a49f40965a8002440442e6843016d64d0fde9e5204cbb90b0014cd7f041"
PLAN = "data/qwen_judge_recovery/plan_v1_20261005/PLAN.json"
SOURCES = ("experiments/qwen_judge_recovery.py", "tests/test_qwen_judge_recovery.py",
           "docs/QWEN_JUDGE_RECOVERY_20261005.md")
TARGETS = (
    "judge:openweights-main-qwen-02-final-HS:astra:structured:a0",
    "judge:openweights-main-qwen-02-final-NS:astra:structured:a0",
    "judge:openweights-main-qwen-04-final-SH:astra:structured:a0",
)
CAP, PRIOR = Decimal("2"), Decimal("125.75920446")
BACKOFF = (2, 5)


def transport_failure(row):
    raw = row.get("raw")
    status = None if raw is None else raw.get("transport_status_code") if isinstance(raw, dict) else -1
    return (row["status"] == "unresolved" and row.get("error_type") == "TransportError"
            and not row.get("over_reservation") and row.get("cost_known") is False
            and row.get("reported_cost_usd") is None and row["cost_usd"] == row["reservation_usd"]
            and (raw is None or set(raw) == {"transport_status_code"})
            and (status is None or type(status) is int and (status in (0, 200, 408, 425, 429) or 500 <= status <= 599)))


def classify(row, spec, response):
    if transport_failure(row):
        return "transport_failure", None
    check(row["status"] == "settled" and not row.get("over_reservation"), "Pending or nontransport failure requires reconciliation")
    result = parse_result(spec, row["raw"])
    check(receipt_cost(spec, row["raw"]) == Decimal(row["cost_usd"]), "Judgment accounting differs")
    if result["stop_reason"] == "error" and not result["refusal"] and not result["cap_hit"]:
        return "incomplete_error", None
    if not result["complete"] or result["missing"]:
        return "incomplete_other", None
    try:
        return "completed_label", judges.parse("structured", response, result["response"])["reduced"]
    except (ValueError, TypeError, KeyError):
        return "invalid_schema", None


def source():
    root = ROOT / ORIGINAL
    manifest_raw = (root / "MANIFEST.json").read_bytes()
    check(sha(manifest_raw) == MANIFEST_SHA
          and production.git("show", f"{RELEASE_COMMIT}:{ORIGINAL}/MANIFEST.json") == manifest_raw,
          "Published incomplete release manifest changed")
    manifest = json.loads(manifest_raw)
    check(manifest["files"] == release._entries(_inventory(root)), "Published release file inventory changed")
    old = json.loads((root / "PLAN.json").read_bytes())
    metadata = json.loads((root / "RELEASE.json").read_bytes())
    check(metadata["status"] == "incomplete" and metadata["costs"]["scope_cost_plus_commitments_usd"] == str(PRIOR),
          "Original incomplete status or cumulative cost changed")
    calls = {r["call_id"]: r for r in merged(events_from_bytes(read_raw(root)))}
    rows = json.loads((root / "main_rows.json").read_bytes())
    missing = {r["id"] for r in rows if r["model"] == "qwen" and r["labels"]["astra"].get("structured") is None}
    check(missing == {c.split(":")[1] for c in TARGETS}, "Technical missing-label inventory changed")
    spec, targets = old["judges"]["astra"], {}
    for call_id in TARGETS:
        row = calls[call_id]
        item_id = call_id.split(":")[1]
        response_row = next(r for r in rows if r["id"] == item_id)
        response = response_row["response"]
        generated = parse_result(old["models"]["qwen"], calls["gen:" + item_id]["raw"])
        check(generated["response"] == response and generated["complete"] and not generated["missing"],
              "Recovery cannot change the original model answer")
        request = judges.judge_request(spec, "structured", response)
        request["provider"].update(old["privacy"] if "privacy" in old else production.p.PRIVACY)
        check(row["request"] == request and row["request_sha256"] == common.digest(request)
              and Decimal(row["reservation_usd"]) == reservation(spec, request), "Original judge request does not reconstruct")
        status, _ = classify(row, spec, response)
        expected = "incomplete_error" if call_id == TARGETS[2] else "transport_failure"
        check(status == expected and not any(c.startswith(call_id.rsplit(":", 1)[0] + ":") and c != call_id for c in calls),
              "Target is no longer an un-retried technical failure")
        targets[call_id] = {"original": row, "response": response, "status": status}
    return {"plan": old, "spec": spec, "targets": targets, "rows": rows}


def build_plan(data=None):
    data = source() if data is None else data
    old_hashes = data["plan"]["source_hashes"]
    check(all(common.sha(ROOT / n) == h for n, h in old_hashes.items()), "Frozen predecessor source changed")
    return {"schema": "qwen-judgment-recovery-v1", "original_release": ORIGINAL,
            "release_commit": RELEASE_COMMIT, "manifest_sha256": MANIFEST_SHA,
            "authorization": {"approved": True, "posthoc_scoring_calls": True,
                              "selection": "Exactly three missing labels selected by technical failure status, never by label value"},
            "cap_usd": "2", "original_api_scope_cap_usd": "200", "prior_scope_cost_bound_usd": str(PRIOR),
            "kolibri_holdback_usd": "45", "maximum_new_attempts_per_logical_call": 2,
            "backoff_seconds": list(BACKOFF), "new_generations": 0,
            "completed_label_redo": False, "schema_retries": False,
            "original_release_remains_incomplete": True,
            "targets": [{"call_id": c, "request_sha256": d["original"]["request_sha256"],
                         "raw_sha256": d["original"]["raw_sha256"], "response_sha256": common.digest(d["response"]),
                         "reason": d["status"], "reservation_usd": d["original"]["reservation_usd"]}
                        for c, d in data["targets"].items()],
            "judge": data["spec"],
            "source_hashes": {**old_hashes, **{n: common.sha(ROOT / n) for n in SOURCES}}}


def verify(path, freeze=None, *, pushed=False, data=None):
    path = Path(path)
    check(path.resolve() == (ROOT / PLAN).resolve(), "Use the canonical recovery plan")
    value = json.loads(path.read_bytes())
    check(common.canonical(value) == common.canonical(build_plan(data)), "Recovery plan or source binding changed")
    if freeze is not None:
        check(re.fullmatch(r"[0-9a-f]{40}", freeze) and freeze != RELEASE_COMMIT, "Fresh full freeze required")
        check(production.git("rev-parse", "HEAD").decode().strip() == freeze, "Checkout must equal recovery freeze")
        production.git("merge-base", "--is-ancestor", RELEASE_COMMIT, freeze)
        check(production.git("show", f"{freeze}:{PLAN}") == path.read_bytes(), "Recovery plan absent from freeze")
        for name, digest in value["source_hashes"].items():
            check(sha(production.git("show", f"{freeze}:{name}")) == digest, "Recovery source absent from freeze")
    if pushed:
        check(freeze is not None, "Pushed freeze required")
        remote = production.git("ls-remote", "origin", production.BRANCH).decode().split()
        check(remote == [freeze, production.BRANCH], "Recovery freeze must be pushed before calls")
    return value


def check_funding(record, spent=Decimal(0), now=None):
    check(set(record) == {"confirmed", "as_of_utc", "account_balance_usd", "scope_prior_bound_usd",
                          "scope_other_commitments_usd", "kolibri_holdback_usd", "repeated_remaining_holdback_usd",
                          "other_account_holdback_usd", "evidence_sha256"}
          and record["confirmed"] is True and re.fullmatch(r"[0-9a-f]{64}", record["evidence_sha256"]),
          "Explicit funded parent preflight required")
    stamp = production.a1._date(record["as_of_utc"])
    now = now or datetime.now(timezone.utc)
    check(timedelta(0) <= now - stamp <= timedelta(minutes=10), "Recovery funding preflight is stale")
    values = {k: _amount(v) for k, v in record.items() if k.endswith("_usd")}
    check(values["scope_prior_bound_usd"] >= PRIOR and values["kolibri_holdback_usd"] >= 45
          and values["scope_other_commitments_usd"] >= values["kolibri_holdback_usd"], "Prior costs or holdbacks were reduced")
    check(values["scope_prior_bound_usd"] + values["scope_other_commitments_usd"] + CAP <= 200,
          "Recovery exceeds original $200 API scope")
    hold = values["kolibri_holdback_usd"] + values["repeated_remaining_holdback_usd"] + values["other_account_holdback_usd"]
    check(values["account_balance_usd"] >= hold + CAP and Decimal(0) <= spent <= CAP,
          "Account funds do not protect other work and the full $2 sidecar")


def attempt_metadata(call_id, ordinal, freeze, plan_hash):
    return {"kind": "judge_recovery", "logical_call_id": call_id, "attempt": ordinal,
            "freeze": freeze, "plan_sha256": plan_hash, "original_release_commit": RELEASE_COMMIT}


def attempt_id(call_id, ordinal):
    return call_id + ":recovery-r" + str(ordinal)


def audit(ledger, data, freeze, plan_hash):
    check(ledger.cap == CAP and ledger.screen_cap == CAP, "Recovery requires its own $2 ledger")
    allowed = {attempt_id(c, n): (c, n) for c in TARGETS for n in (1, 2)}
    recovered, attempts = {}, []
    for row in ledger.rows():
        check(row["call_id"] in allowed, "Unexpected recovery call; generations are forbidden")
        call_id, ordinal = allowed[row["call_id"]]
        target = data["targets"][call_id]
        check(row["request"] == target["original"]["request"] and row["phase"] == "main"
              and row["metadata"] == attempt_metadata(call_id, ordinal, freeze, plan_hash)
              and Decimal(row["reservation_usd"]) == reservation(data["spec"], row["request"]), "Recovery request or identity changed")
        if ordinal == 2:
            previous = ledger.existing(attempt_id(call_id, 1))
            check(previous is not None and classify(previous, data["spec"], target["response"])[0]
                  in ("transport_failure", "incomplete_error"), "Completed or ineligible output was retried")
        status, label = classify(row, data["spec"], target["response"])
        attempts.append({"call_id": row["call_id"], "logical_call_id": call_id, "status": status,
                         "cost_bound_usd": row["cost_usd"], "raw_sha256": row["raw_sha256"]})
        if label is not None:
            recovered[call_id] = label
    return {"pass": True, "posthoc_scoring_repair": True, "original_release_status": "incomplete",
            "attempts": attempts, "recovered": recovered, "remaining_missing": [c for c in TARGETS if c not in recovered],
            "new_cost_bound_usd": str(ledger.spent()), "scope_prior_plus_recovery_usd": str(PRIOR + ledger.spent()),
            "original_unknown_charges_retained_usd": "0.96522800"}


def recover(ledger, data, freeze, plan_hash, sender, preflight, *, sleep=time.sleep):
    audit(ledger, data, freeze, plan_hash)
    for call_id in TARGETS:
        target = data["targets"][call_id]
        for ordinal in (1, 2):
            physical = attempt_id(call_id, ordinal)
            row = ledger.existing(physical)
            if row is None:
                sleep(BACKOFF[ordinal - 1])
                check_funding(preflight, ledger.spent())
                check(sender is not None, "No dispatch permission")
                request = deepcopy(target["original"]["request"])
                ledger.reserve(physical, request, reservation(data["spec"], request), "main",
                               attempt_metadata(call_id, ordinal, freeze, plan_hash))
                raw, cost = None, None
                try:
                    raw = sender(request)
                    cost = receipt_cost(data["spec"], raw)
                    check(cost is not None, "Usage unavailable")
                    parse_result(data["spec"], raw)
                except Exception as error:
                    if raw is None and getattr(error, "status_code", None) is not None:
                        raw = {"transport_status_code": error.status_code}
                    row = ledger.settle(physical, raw, cost, error=error)
                    check(isinstance(error, TransportError) and transport_failure(row), "Nonretryable recovery failure")
                else:
                    row = ledger.settle(physical, raw, cost)
            status, _ = classify(row, data["spec"], target["response"])
            if status not in ("transport_failure", "incomplete_error"):
                break
    return audit(ledger, data, freeze, plan_hash)


def project(data, report):
    check(set(report["recovered"]) <= set(TARGETS), "Unexpected recovered judgment")
    rows = deepcopy(data["rows"])
    for row in rows:
        call_id = f"judge:{row['id']}:astra:structured:a0"
        if call_id in report["recovered"]:
            check(row["labels"]["astra"].get("structured") is None, "Cannot replace a completed label")
            row["labels"]["astra"]["structured"] = deepcopy(report["recovered"][call_id])
    return rows


def run_root():
    return production.canonical_root().parent / "qwen-judge-recovery-20261005"


def execute(plan, freeze, preflight, key):
    data = source()
    check(plan == verify(ROOT / PLAN, freeze, pushed=True, data=data), "Recovery plan differs from pushed freeze")
    check_funding(preflight)
    root = run_root()
    _no_symlinks(root)
    binding = {"freeze": freeze, "plan_sha256": common.sha(ROOT / PLAN),
               "original_manifest_sha256": MANIFEST_SHA, "original_release_commit": RELEASE_COMMIT}
    with Ledger(root / "raw", cap="2", screen_cap="2") as ledger:
        write_once(root / "runtime.json", binding)
        launch = root / "launches" / uuid.uuid4().hex
        write_once(launch / "start.json", {**binding, "preflight": preflight,
                   "utc": datetime.now(timezone.utc).isoformat(), "calls_before": len(ledger.rows()),
                   "journal_before_sha256": common.sha(root / "raw/events.jsonl")})
        complete = False
        try:
            report = recover(ledger, data, freeze, binding["plan_sha256"], production.guarded_sender(key), preflight)
            rows = project(data, report)
            write_once(launch / "recovery_report.json", report)
            write_once(launch / "recovery_main_rows.json", rows)
            write_once(launch / "recovery_main_analysis.json", analysis.analyze(rows, "main"))
            complete = not report["remaining_missing"]
            return report
        finally:
            write_once(launch / "finish.json", {**binding, "all_three_labels_recovered": complete,
                       "new_cost_bound_usd": str(ledger.spent()), "calls_after": len(ledger.rows()),
                       "journal_after_sha256": common.sha(root / "raw/events.jsonl")})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--preflight")
    parser.add_argument("--env-file")
    args = parser.parse_args(argv)
    if args.build and args.execute or args.execute and (not args.freeze or not args.preflight):
        parser.error("Build then freeze; execution requires both freeze and funded preflight")
    data = source()
    if args.build:
        write_once(ROOT / PLAN, build_plan(data))
    plan = verify(ROOT / PLAN, args.freeze, data=data)
    if not args.execute:
        print(common.canonical({"plan_sha256": common.sha(ROOT / PLAN), "targets": len(TARGETS), "network_calls": 0}))
        return
    preflight = json.loads(Path(args.preflight).read_bytes())
    print(common.canonical(execute(plan, args.freeze, preflight, production.load_key(args.env_file))))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Qwen recovery stopped; all original and new attempts remain preserved.") from None
