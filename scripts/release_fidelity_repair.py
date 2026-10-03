#!/usr/bin/env python3
"""Offline repair release candidate from a closed campaign, never launch authority.

--base is the directory containing budget.jsonl and cheap-NNN/main-NNN attempts.
Without --destination this only inspects. Incomplete evidence requires explicit
--allow-incomplete; invalid scientific rows remain byte-exact failed evidence.
Truthful cost/deadline overruns are incomplete evidence, not release blockers
or permission to extend execution. Malformed accounting remains a blocker.
Private lifecycle journals are verified locally, never copied or redacted into
public raw outputs. Unsafe raw content fails closed instead of being rewritten.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from experiments.sae_assay_diagnostic.budget import EventLedger, _canonical, _number, _utc
from experiments.steering_fidelity_repair import audit, controller as c
from scripts.audit_public_release import scan_blob
from scripts.release_sae_exposure import _files, _json, _relative, _require, _scan_text
from scripts.release_steering_fidelity_calibration import safe, scan, LOAD_FILES, REPORT_KEYS

FREEZE = "afea3ec607abdeb0b3a2f87aef4529b5238725a4"
PLAN_PATH = "data/steering_fidelity_repair/pilot_plan_20261003/PLAN.json"
PLAN_SHA256 = "d9d2c37e2187b3a53d7a97c35e4735d1dd8da5297599079d538800ac026d12ef"
NAMESPACE = "steering-fidelity-repair-20261003"
SCHEMA = "steering_fidelity_repair_release_v1"
TRANSPORT_FILES = set(("pip-freeze.txt controller.log controller-exit.json controller-stopped.json "
                       "controller-worker-reconciled.json STOP").split())
CHEAP_FILES = TRANSPORT_FILES | {"tests.xml", "DONE-all.json"}
MAIN_FILES = TRANSPORT_FILES | LOAD_FILES | set((
    "receipts.jsonl model.json qualification.json audit.json complete.json failed.json "
    "discovery-decision.json validation-decision.json singleton-decision.json liveness-decision.json "
    "WAITING-first-rows.json WAITING-throughput.json APPROVE-first-rows APPROVE-throughput").split())
sha = c.sha


def frozen_blob(name):
    _relative(name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")

    def git(*args):
        return subprocess.run(["git", "--no-replace-objects", "-C", str(ROOT), *args],
            env=env, check=True, capture_output=True, timeout=30).stdout

    entries = git("ls-tree", "-z", FREEZE, "--", name).split(b"\0")
    _require(len(entries) == 2 and entries[-1] == b"", "Missing frozen blob")
    header, actual = entries[0].split(b"\t")
    mode, kind, oid = header.split()
    _require(actual.decode() == name and mode in (b"100644", b"100755") and kind == b"blob",
             "Frozen path is not a regular blob")
    return git("cat-file", "blob", oid.decode())


def verify_sources():
    raw = frozen_blob(PLAN_PATH)
    _require(hashlib.sha256(raw).hexdigest() == PLAN_SHA256, "Wrong frozen plan hash")
    plan = json.loads(raw)
    bindings = {PLAN_PATH: PLAN_SHA256}
    for group in (plan["source_hashes"], plan["input_hashes"]):
        for name, digest in group.items():
            _require(name not in bindings, "Overlapping frozen bindings")
            _require(re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid frozen digest")
            bindings[name] = digest
    for name, digest in bindings.items():
        _require(hashlib.sha256(frozen_blob(name)).hexdigest() == digest
                 and sha(safe(ROOT / name)) == digest, "Frozen/local source mismatch: " + name)
    _require(_canonical(plan["budget"]) == _canonical(c.BUDGET), "Wrong frozen repair budget")
    return plan


def read_ledger(path):
    # Constructor/read() append; the frozen parser itself accepts a read-only fd.
    ledger = object.__new__(EventLedger)
    ledger.plan, ledger.freeze, ledger.ids, ledger.anchor = PLAN_SHA256, FREEZE, frozenset(), None
    with safe(path).open("rb") as stream:
        rows = ledger._read(stream.fileno())
    _require(bool(rows), "Missing lifecycle chain")
    return {row["id"]: row for row in rows}


def raw_audit(root, plan):
    if root is None:
        return {"status": "not_started", "pass": None, "complete": False,
                "reason": "no_worker_dispatched"}
    try:
        files = _files(safe(root))
        if not {"receipts.jsonl", "model.json"} & files.keys():
            _require(set(files) <= TRANSPORT_FILES | LOAD_FILES | {"failed.json"},
                     "Scientific artifacts without execution receipts or model metadata")
            if "failed.json" in files:
                failure = _json(files["failed.json"])
                _require(type(failure.get("completed_forwards")) is int
                         and failure["completed_forwards"] == 0
                         and failure.get("plan_sha256") == PLAN_SHA256
                         and failure.get("freeze_commit") == FREEZE,
                         "Startup failure does not attest zero scientific forwards")
            return {"status": "not_started", "pass": None, "complete": False,
                    "reason": "before_model_metadata_and_first_scientific_dispatch"}
        report = audit.audit_raw_window(root, plan, PLAN_SHA256, FREEZE, partial=True)
        return {"status": "audited", **{key: report[key] for key in REPORT_KEYS}}
    except Exception as exc:
        return {"status": "failed", "pass": False, "complete": False, "error_type": type(exc).__name__}


def inventory(root, expected, kind, plan, private):
    allowed = set(CHEAP_FILES if kind == "cheap" else MAIN_FILES)
    if kind == "main":
        for row in plan["rows"]:
            _require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", row["id"]), "Unsafe planned ID")
            allowed.add("forwards/" + row["id"] + ".json")
        allowed |= {name + ".pending" for name in allowed if name.endswith(".json")}
    files = _files(safe(root))
    _require(set(files) == set(expected) and set(files) <= allowed, "Unexpected or changed raw inventory")
    _require(sum(path.stat().st_size for path in files.values()) <= 256 * 1024**2,
             "Oversized public text inventory")
    _require(len(files.keys() & LOAD_FILES) <= 1, "Multiple model-load metadata files")
    for name, path in files.items():
        _require(sha(path) == expected[name], "Raw artifact hash mismatch")
        _require(name not in LOAD_FILES or path.stat().st_size <= 1024**2, "Oversized model-load metadata")
        scan(name, path)
        _scan_text(name.removesuffix(".pending"), path, private_paths=private)
    return files


def cheap_pass(files):
    required = {"DONE-all.json", "controller-exit.json", "tests.xml", "controller.log", "pip-freeze.txt"}
    if not required <= files.keys():
        return False
    if (_json(files["DONE-all.json"]) != {"pass": True, "scope": "tiny_cuda_exact_path"}
            or _json(files["controller-exit.json"]) != {"exit_code": 0}):
        return False
    suites = list(ET.parse(files["tests.xml"]).iter("testsuite"))
    return (bool(suites) and sum(int(s.get("tests", "0")) for s in suites) > 0
            and all(int(s.get(k, "0")) == 0 for s in suites for k in ("failures", "errors", "skipped")))


def lifecycle(base, reservation, plan, prior):
    events = read_ledger(base / "events.jsonl")
    config, intent, pod, closed = (events[key]["data"] for key in
        ("controller:config", "create-intent", "created", "closed"))
    kind, number = base.name.split("-")
    limit = 1800 if kind == "cheap" else 4800
    _require(list(events)[-1] == "closed", "Post-close lifecycle events")
    _require(config["kind"] == kind and type(config["attempt"]) is int and config["attempt"] == int(number)
             and config["namespace"] == NAMESPACE and config["plan_path"] == PLAN_PATH
             and _canonical(config["budget"]) == _canonical(plan["budget"])
             and config["hard_seconds"] == limit and config["retrieval_seconds"] == 600,
             "Wrong campaign or attempt")
    authority = events["creation-approval"]
    approval = c.approval_record(PLAN_SHA256, FREEZE, plan["budget"], authority["data"]["approval_ref"],
                                kind=kind, attempt=int(number))
    _require(set(authority["data"]) == set(approval) | {"approval_file_sha256"}
             and _canonical({k: authority["data"][k] for k in approval}) == _canonical(approval)
             and re.fullmatch(r"[0-9a-f]{64}", authority["data"].get("approval_file_sha256", ""))
             and intent["approval_sha256"] == reservation["data"]["approval_sha256"] == authority["sha256"]
             and intent["campaign_reservation_sha256"] == reservation["sha256"]
             and intent["plan_sha256"] == PLAN_SHA256 and intent["freeze_commit"] == FREEZE,
             "Authorization/reservation linkage failed")
    ci = intent["ci"]
    _require(set(ci) == {"pass", "freeze_commit", "run_id", "jobs"}
             and ci.get("pass") is True and ci.get("freeze_commit") == FREEZE
             and type(ci.get("run_id")) is int and ci["run_id"] > 0
             and type(ci.get("jobs")) is int and ci["jobs"] >= 7,
             "Missing exact-freeze CI receipt")
    started = _utc(intent["created_utc"])
    _require(_utc(intent["deadline_utc"]) == started + timedelta(seconds=limit - 600)
             and _utc(intent["hard_deadline_utc"]) == started + timedelta(seconds=limit), "Changed lifecycle deadlines")
    pid = pod["id"]
    blocked = events["pods:config"]["data"]["preexisting_ids"]
    _require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pid)
             and re.fullmatch("codex-" + NAMESPACE + "-" + kind + r"-[0-9a-f]{12}", pod["name"])
             and pod["name"] == intent["payload"]["name"]
             and blocked == intent["blocked"] and pid not in blocked
             and started - timedelta(seconds=60) <= _utc(pod["createdAt"]) <= _utc(closed["utc"]),
             "Pod is not newly owned")
    final = safe(base / "final-retrieval.json")
    receipt = _json(final)
    retrievals = [e for key, e in events.items() if key.startswith("retrieval:")]
    registered, permit, deletion = (events[k] for k in ("pod:created:" + pid, "pod:delete:" + pid, "delete-intent"))
    _require(receipt == retrievals[-1] and receipt["data"]["pod_id"] == pid
             and registered["data"]["creation_receipt_sha256"] == events["created"]["sha256"]
             and registered["data"]["required_artifacts"] == [str(final)]
             and permit["data"] == {"kind": "delete_authorized", "pod_id": pid, "artifacts": {str(final): sha(final)}}
             and deletion["data"]["permit_sha256"] == permit["sha256"]
             and deletion["data"]["pod_id"] == closed["pod_id"] == pid
             and all(deletion["data"]["pod"][k] == pod[k] for k in ("id", "name", "createdAt"))
             and type(closed["get_status"]) is int and closed["get_status"] == 404
             and pid not in closed["inventory_ids"], "Closure linkage failed")
    chain = [authority, events["create-intent"], events["created"], registered, receipt, permit, deletion, events["closed"]]
    _require(all(a["seq"] < b["seq"] for a, b in zip(chain, chain[1:])), "Closure order failed")
    if "delete-response" in events:
        _require(events["delete-response"]["data"] == {"status": 204, "pod_id": pid}, "Delete response mismatch")
    if "credential-intent" in events:
        removal = events["credential-removed"]
        _require(removal["data"].get("absent") is True
                 and removal["data"].get("path") == events["credential-intent"]["data"].get("path")
                 and receipt["seq"] < removal["seq"] < deletion["seq"], "Credential removal unverified")
    if "worker-intent" in events:
        worker = events["worker-intent"]
        _require(all(worker["data"].get(k) == v for k, v in
                     {"pod_id": pid, "plan_sha256": PLAN_SHA256, "freeze_commit": FREEZE}.items())
                 and re.fullmatch(r"[0-9a-f]{32}", worker["data"].get("worker_id", ""))
                 and registered["seq"] < worker["seq"] < receipt["seq"], "Worker ownership linkage failed")
    elapsed = _number(closed["elapsed_seconds"])
    quote = _number(intent["quote"]["hourly_rate_usd"])
    rate = max(quote, _number(deletion["data"]["pod"]["cost"]))
    _require(0 < quote <= c.base.HARDWARE[kind][1]
             and _number(intent["quote"]["storage_hourly_usd"]) == Decimal(".10")
             and elapsed + Decimal("1") >= _number((_utc(closed["utc"]) - started).total_seconds()),
             "Invalid elapsed/rate accounting")
    cost = elapsed * (rate + Decimal(".10")) / 3600
    cumulative = prior + cost
    within = c.budget_projection(cumulative)["pass"] and elapsed <= limit
    _require(_number(intent["prior_new_usd"]) == _number(reservation["data"]["prior_gpu_usd"]) == prior
             and _number(intent["prior_total_usd"]) == _number(closed["prior_total_usd"]) == Decimal("9.657774")
             and _number(closed["compute_upper_bound_usd"]) == cost
             and _number(closed["cumulative_gpu_upper_bound_usd"]) == cumulative
             and _number(closed["new_all_in_upper_bound_usd"]) == cumulative + 3
             and _number(closed["all_in_upper_bound_usd"]) == Decimal("9.657774") + cumulative + 3
             and closed["within_limits"] is within, "Cost projection mismatch")
    projection = reservation["data"]["projection"]
    _require(projection == c.budget_projection(projection["projected_gpu_usd"])
             and projection["pass"] is True, "Reservation projection mismatch")
    public = {key: closed[key] for key in ("pod_id", "get_status", "utc", "elapsed_seconds", "within_limits",
        "compute_upper_bound_usd", "cumulative_gpu_upper_bound_usd", "new_all_in_upper_bound_usd",
        "all_in_upper_bound_usd", "prior_total_usd")}
    public.update(attempt=base.name, pod_name=pod["name"], created_utc=pod["createdAt"], ci=ci,
        lifecycle_sha256=sha(base / "events.jsonl"), final_retrieval_sha256=sha(final),
        retrieval_event_sha256=receipt["sha256"], reservation_sha256=reservation["sha256"],
        approval_event_sha256=authority["sha256"], artifacts=receipt["data"]["artifacts"])
    return events, receipt, public, cumulative


def assess(root, files, plan):
    report = raw_audit(root, plan)
    marked = "complete.json" in files
    required = {"model.json", "qualification.json", "audit.json", "controller.log", "pip-freeze.txt", "controller-exit.json"}
    complete = (report.get("complete") is True and report.get("pass") is True and marked
                and required <= files.keys() and "failed.json" not in files
                and not any(n.endswith(".pending") for n in files)
                and _json(files["controller-exit.json"]) == {"exit_code": 0}
                and _json(files["qualification.json"]).get("pass") is True)
    if complete:
        saved = _json(files["audit.json"])
        rebuilt = audit.audit_raw_window(root, plan, PLAN_SHA256, FREEZE, partial=False)
        complete = _canonical(saved) == _canonical(rebuilt)
    return {"status": "complete" if complete else "incomplete", "raw_audit": report,
            "completion_meaning": "conditional_inventory_complete_not_scientific_gate",
            "worker_completion_marker_present": marked, "scientific_gate_evaluated": False,
            "stage_t_authorized": False, "e_only_fallback": False,
            "pending_temporary_files": sorted(n for n in files if n.endswith(".pending"))}


def _prepare(base, allow_incomplete):
    base = safe(base)
    plan = verify_sources()
    campaign = read_ledger(base / "budget.jsonl")
    _require(_canonical(campaign["budget"]["data"]) == _canonical(plan["budget"]), "Campaign budget mismatch")
    reservations = [row for key, row in campaign.items() if key.startswith("attempt:")]
    names = [row["id"].removeprefix("attempt:") for row in reservations]
    _require(reservations and set(campaign) == {"binding", "budget", *("attempt:" + n for n in names)}
             and all(re.fullmatch(r"(?:cheap|main)-[0-9]{3}", n) for n in names), "Invalid campaign reservations")
    actual = {path.name for path in base.iterdir() if re.fullmatch(r"(?:cheap|main)-[0-9]{3}", path.name)}
    _require(actual == set(names), "Unreserved or missing attempt directory")
    checks = {safe(base / "budget.jsonl"): sha(base / "budget.jsonl")}
    attempts, own_ids, foreign, prior, sequence = [], set(), set(), Decimal(0), {"cheap": 0, "main": 0}
    for name, reservation in zip(names, reservations):
        _require(not attempts or attempts[-1][3]["within_limits"], "Attempt follows an out-of-limit closure")
        kind, number = name.split("-")
        sequence[kind] += 1
        _require(int(number) == sequence[kind] and not (kind == "cheap" and sequence["main"]), "Invalid attempt order")
        directory = safe(base / name)
        events, receipt, public, prior = lifecycle(directory, reservation, plan, prior)
        _require(not attempts or _utc(attempts[-1][3]["utc"]) <= _utc(events["create-intent"]["data"]["created_utc"]),
                 "Attempt predates previous verified closure")
        _require(public["pod_id"] not in own_ids, "Reused owned pod")
        own_ids.add(public["pod_id"])
        foreign.update(events["create-intent"]["data"]["blocked"])
        foreign.update(events["closed"]["data"]["inventory_ids"])
        checks.update({directory / "events.jsonl": public["lifecycle_sha256"],
                       directory / "final-retrieval.json": public["final_retrieval_sha256"]})
        attempts.append((directory, events, receipt, public))
    private = sorted(foreign - own_ids) + [str(base)]
    sources, snapshots, public_attempts = {}, [], []
    latest_cheap, dispatched_main, main_result = None, False, None
    for directory, events, receipt, public in attempts:
        kind = directory.name.split("-")[0]
        if kind == "main":
            _require(latest_cheap is not None and latest_cheap["cheap_tests_pass"]
                     and latest_cheap["within_limits"] and not dispatched_main
                     and events["create-intent"]["data"]["cheap_receipt_sha256"] == latest_cheap["retrieval_event_sha256"],
                     "Main lacks the exact passing closed cheap receipt or repeats dispatched work")
            dispatched_main = "worker-intent" in events
        lineage, files, root = [], {}, None
        for event in events.values():
            if not event["id"].startswith("retrieval:"):
                continue
            data = event["data"]
            _require(data["pod_id"] == public["pod_id"], "Foreign retrieval")
            if data.get("no_worker_dispatched"):
                _require("worker-intent" not in events and data["artifacts"] == {}, "Dispatched evidence omitted")
                retrieval_root = directory / "retrievals"
                _require(not retrieval_root.exists() or not _files(safe(retrieval_root)), "Undispatched raw evidence omitted")
                snapshot, current = None, {}
            else:
                snapshot = safe(data["directory"])
                _require(snapshot.is_relative_to(directory / "retrievals"), "Snapshot outside owned attempt")
                current = inventory(snapshot, data["artifacts"], kind, plan, private)
                snapshots.append((snapshot, dict(data["artifacts"])))
            committed = {n: h for n, h in data["artifacts"].items() if n.startswith("forwards/") and n.endswith(".json")}
            _require(all(receipt["data"]["artifacts"].get(n) == h for n, h in committed.items()), "Earlier outcome bytes lost")
            record = {"retrieval_event_sha256": event["sha256"], "artifacts": data["artifacts"],
                      "committed_forward_payloads_preserved": len(committed)}
            if kind == "main":
                record["raw_audit"] = raw_audit(snapshot, plan)
            lineage.append(record)
            if event == receipt:
                files, root = current, snapshot
        if "worker-intent" in events:
            _require("controller.log" in files and bool(set(c.base.TERMINAL) & files.keys()), "Missing worker closure/log")
        if kind == "cheap":
            public["cheap_tests_pass"] = cheap_pass(files)
            latest_cheap = public
        else:
            main_result = assess(root, files, plan)
            if not public["within_limits"]:
                main_result["status"] = "incomplete"
            public["outcome"] = main_result
        public["snapshot_lineage"] = lineage
        for key in ("final-structural-audit",):
            if key in events:
                historical = events[key]["data"]
                _require(historical["retrieval_sha256"] == receipt["sha256"], "Historical audit linkage failed")
                public["recorded_final_audit"] = {k: historical[k] for k in ("status", "error_type") if k in historical}
                _require(historical.get("status") in {"audited", "failed"}
                         and ("error_type" not in historical or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,80}", historical["error_type"])),
                         "Unsafe historical audit status")
                public["recorded_final_audit"]["event_sha256"] = events[key]["sha256"]
        public_attempts.append(public)
        sources.update({directory.name + "/" + name: path for name, path in files.items()})
    result = main_result or {"status": "incomplete", "raw_audit": raw_audit(None, plan),
                            "completion_meaning": "conditional_inventory_complete_not_scientific_gate",
                            "scientific_gate_evaluated": False, "stage_t_authorized": False, "e_only_fallback": False}
    result["operational_limits_pass"] = all(row["within_limits"] for row in public_attempts)
    if not result["operational_limits_pass"]:
        result["status"] = "incomplete"
    _require(allow_incomplete or result["status"] == "complete", "Incomplete release requires --allow-incomplete")
    provenance = {"schema": SCHEMA, "freeze_commit": FREEZE, "plan_path": PLAN_PATH, "plan_sha256": PLAN_SHA256,
        **result, "attempts": public_attempts, "campaign_ledger_sha256": checks[base / "budget.jsonl"],
        "cost": c.budget_projection(prior), "cost_scope": "controller upper bounds, not a reconciled bill",
        "artifacts": {name: sha(path) for name, path in sources.items()}}
    encoded = _canonical(provenance)
    _require(not scan_blob("retrieval_and_cost.json", encoded)
             and not any(value in encoded.decode() for value in private), "Private lifecycle projection")
    return provenance, sources, checks, snapshots


def _unchanged(checks, snapshots):
    _require(all(sha(safe(path)) == digest for path, digest in checks.items()), "Lifecycle changed during release")
    for root, expected in snapshots:
        _require({name: sha(path) for name, path in _files(safe(root)).items()} == expected,
                 "Raw inventory changed during release")


def inspect_release(base, *, allow_incomplete=False):
    provenance, _, checks, snapshots = _prepare(base, allow_incomplete)
    _unchanged(checks, snapshots)
    return provenance


def copy_release(base, destination, *, allow_incomplete=False):
    base, destination = safe(base), safe(destination)
    _require(not destination.exists(), "Destination exists; overwrite forbidden")
    _require(not destination.is_relative_to(base) and not base.is_relative_to(destination), "Overlapping directories")
    provenance, sources, checks, snapshots = _prepare(base, allow_incomplete)
    _unchanged(checks, snapshots)
    destination.mkdir()
    for name, source in sources.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
        _require(sha(target) == provenance["artifacts"][name], "Copy changed bytes; candidate unsealed")
        scan(name.split("/", 1)[1], target)
    with (destination / "retrieval_and_cost.json").open("xb") as stream:
        stream.write(_canonical(provenance) + b"\n")
    scan("retrieval_and_cost.json", destination / "retrieval_and_cost.json")
    _unchanged(checks, snapshots)
    manifest = {"schema": SCHEMA, "status": provenance["status"], "freeze_commit": FREEZE,
        "plan_sha256": PLAN_SHA256, "builder_sha256": sha(Path(__file__)),
        "safety_sources": {name: sha(ROOT / name) for name in (
            "scripts/release_steering_fidelity_calibration.py", "scripts/release_sae_exposure.py",
            "scripts/audit_public_release.py")},
        "files": [{"path": name, "sha256": sha(path), "bytes": path.stat().st_size}
                  for name, path in _files(destination).items()]}
    with (destination / "RELEASE_MANIFEST.json").open("xb") as stream:
        stream.write(_canonical(manifest) + b"\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args(argv)
    result = (copy_release(args.base, args.destination, allow_incomplete=args.allow_incomplete)
              if args.destination else inspect_release(args.base, allow_incomplete=args.allow_incomplete))
    if args.destination:
        summary = {"status": result["status"], "files": len(result["files"]), "copied": True}
    else:
        summary = {"status": result["status"], "raw_audit": result["raw_audit"], "cost": result["cost"],
                   "operational_limits_pass": result["operational_limits_pass"],
                   "files": len(result["artifacts"]), "copied": False,
                   "attempts": [{k: row[k] for k in ("attempt", "pod_id", "get_status", "within_limits")}
                                for row in result["attempts"]]}
    print(_canonical(summary).decode())


if __name__ == "__main__":
    main()
