#!/usr/bin/env python3
"""Offline Phase C publication candidate; no scientific gate or release approval."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from experiments.sae_assay_diagnostic.budget import EventLedger, _number, _utc
from experiments.steering_fidelity import audit, protocol as p
from scripts.audit_public_release import scan_blob
from scripts.release_sae_exposure import _files, _json, _relative, _require, _scan_text

FREEZE = "2d9c94f1de59f0f59dd89636c20afece1f6d1daf"
PLAN_PATH = "data/steering_fidelity/calibration_plan_20261002/PLAN.json"
PLAN_SHA256 = "6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0"
NAMESPACE = "steering-fidelity-20261002"
ROOT_FILES = set(("receipts.jsonl model.json qualification.json calibration-state.json "
    "calibration-analysis.json pressure-analysis.json liveness-analysis.json complete.json failed.json "
    "pip-freeze.txt controller.log controller-exit.json controller-stopped.json "
    "controller-worker-reconciled.json WAITING-first-rows.json WAITING-throughput.json "
    "APPROVE-first-rows APPROVE-throughput STOP").split())
# Inherited diagnostic runner metadata uses a five-digit ledger counter; never weights.
LOAD_FILES = {f"model-bf16-load-{i:05d}.json" for i in range(1, 10)}
REPORT_KEYS = ("pass", "forwards", "unresolved_forward_ids", "expected_forwards", "complete", "receipt_events")


def safe(path):
    path = Path(path).absolute()
    _require(".." not in path.parts and not any(x.is_symlink() for x in (path, *path.parents)),
             "Symlink or traversal path")
    return path


def frozen_blob(name):
    _relative(name)
    def git(*args):
        return subprocess.run(["git", "--no-replace-objects", "-C", str(ROOT), *args],
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"}, check=True, capture_output=True,
            timeout=30).stdout
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
    bindings = {PLAN_PATH: PLAN_SHA256, **plan["source_hashes"], **plan["input_hashes"]}
    for name, digest in bindings.items():
        _require(hashlib.sha256(frozen_blob(name)).hexdigest() == digest
                 and p.sha(safe(ROOT / name)) == digest, "Frozen/local source mismatch: " + name)
    return plan


def scan(name, path):
    name = name.removesuffix(".pending")  # Final pending payloads must still be safely parseable text.
    _scan_text(name, path)
    text = path.read_text(encoding="utf-8")
    if name.endswith(".json"):
        text += json.dumps(_json(path), ensure_ascii=False)
    elif name.endswith(".jsonl"):
        text += "".join(json.dumps(json.loads(line), ensure_ascii=False) for line in text.splitlines())
    _require(not scan_blob(name, text.encode()), "Decoded secret content")
    _require(not any(ord(c) < 32 and c not in "\n\r\t" for c in text)
             and not re.search(r'\\u00(?:0[0-9a-f]|1[0-9a-f])', text, re.I)
             and not re.search(r"\bssh(?:\b|-)", text, re.I), "Binary or private transport content")
    for candidate in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|[0-9a-fA-F]*:[0-9a-fA-F:]+", text):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            continue
        raise ValueError("Private IP address in public artifact")


def lifecycle(base, plan):
    path = safe(base / "events.jsonl")
    # Constructor/read() open for append. Reuse the frozen parser with a read-only fd instead.
    ledger = object.__new__(EventLedger)
    ledger.plan, ledger.freeze, ledger.ids, ledger.anchor = PLAN_SHA256, FREEZE, frozenset(), None
    with path.open("rb") as stream:
        events = ledger._read(stream.fileno())
    e = {row["id"]: row for row in events}
    config, intent, pod, closed = (e[k]["data"] for k in
        ("controller:config", "create-intent", "created", "closed"))
    _require(events[-1]["id"] == "closed", "Post-close lifecycle events")
    _require(config["kind"] == "main" and config["namespace"] == NAMESPACE
             and config["plan_path"] == PLAN_PATH and config["budget"] == plan["budget"], "Wrong campaign")
    pid = pod["id"]
    _require(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pid)
             and re.fullmatch("codex-" + NAMESPACE + r"-main-[0-9a-f]{12}", pod["name"])
             and pod["name"] == intent["payload"]["name"]
             and pid not in intent["blocked"] and pid not in e["pods:config"]["data"]["preexisting_ids"],
             "Pod is not newly owned")
    final = safe(base / "final-retrieval.json")
    receipt = _json(final)
    retrievals = [row for row in events if row["id"].startswith("retrieval:")]
    registered, permit, deletion = (e[k] for k in ("pod:created:" + pid, "pod:delete:" + pid, "delete-intent"))
    _require(receipt == retrievals[-1] and receipt["data"]["pod_id"] == pid
             and registered["data"]["creation_receipt_sha256"] == e["created"]["sha256"]
             and registered["data"]["required_artifacts"] == [str(final)]
             and permit["data"] == {"kind": "delete_authorized", "pod_id": pid,
                                    "artifacts": {str(final): p.sha(final)}}
             and deletion["data"]["permit_sha256"] == permit["sha256"]
             and deletion["data"]["pod_id"] == closed["pod_id"] == pid
             and all(deletion["data"]["pod"][k] == pod[k] for k in ("id", "name", "createdAt"))
             and closed["get_status"] == 404 and pid not in closed["inventory_ids"], "Closure linkage failed")
    chain = [e["create-intent"], e["created"], registered, receipt, permit, deletion, e["closed"]]
    _require(all(a["seq"] < b["seq"] for a, b in zip(chain, chain[1:])), "Closure order failed")
    _utc(closed["utc"])
    elapsed = _number(closed["elapsed_seconds"])
    costs = [closed[k] for k in ("compute_upper_bound_usd", "cumulative_gpu_upper_bound_usd", "all_in_upper_bound_usd")]
    _require(type(closed["within_limits"]) is bool, "Invalid cost status")
    if all(v is not None for v in costs):
        cost, cumulative, total = map(_number, costs)
        _require(cumulative == _number(intent["prior_new_usd"]) + cost and total == cumulative + 3
                 and (not closed["within_limits"] or (cumulative <= 22 and total <= 25 and elapsed <= 9000)),
                 "Cost projection mismatch")
    else:
        _require(all(v is None for v in costs) and not closed["within_limits"], "Unknown cost claims success")
    public = {k: closed[k] for k in ("pod_id", "get_status", "utc", "elapsed_seconds", "within_limits",
              "compute_upper_bound_usd", "cumulative_gpu_upper_bound_usd", "all_in_upper_bound_usd")}
    return e, receipt, public


def inventory(root, expected, plan):
    allowed = ROOT_FILES | LOAD_FILES | {"forwards/" + r["id"] + suffix for r in plan["rows"]
                                       for suffix in (".json", ".json.pending")}
    ids = [f"positive-activation-{i:02d}" for i in range(20)] + [
        f"liveness-{f}-{i:02d}-{arm}" for f in p.POSITIVE_IDS for i in range(20) for arm in ("zero", "positive")]
    allowed |= {"liveness/" + key + suffix for key in ids for suffix in (".json", ".dispatch.json")}
    files = _files(root)
    _require(set(files) == set(expected) and set(files) <= allowed, "Unexpected or changed raw inventory")
    _require(len(files.keys() & LOAD_FILES) <= 1, "Multiple model-load metadata files")
    for name, path in files.items():
        _require(name not in LOAD_FILES or path.stat().st_size <= 1024**2, "Oversized model-load metadata")
        _require(p.sha(path) == expected[name], "Raw artifact hash mismatch")
        scan(name, path)
    return files


def partial_audit(root, plan):
    result = {"status": "not_started", "pass": None, "complete": False}
    if root is not None:
        try:
            report = audit.audit_raw_window(root, plan, PLAN_SHA256, FREEZE, partial=True)
            result = {"status": "audited", **{k: report[k] for k in REPORT_KEYS}}
        except Exception as exc:
            result = {"status": "failed", "pass": False, "complete": False, "error_type": type(exc).__name__}
    return result


def assess(root, files, plan):
    result = partial_audit(root, plan)
    live = _json(files["liveness-analysis.json"]) if "liveness-analysis.json" in files else {}
    expected = set()
    if live.get("selected_rung") is not None:
        expected |= {f"positive-activation-{i:02d}" for i in range(20)}
    eligible = live.get("eligible_ids", [])
    valid_live = (live.get("status") in ("complete", "not_run") and len(eligible) == len(set(eligible))
                  and set(eligible) <= set(p.POSITIVE_IDS))
    if live.get("status") == "complete":
        valid_live &= bool(eligible) and live.get("selected_rung") in p.RUNGS
        expected |= {f"liveness-{f}-{i:02d}-{arm}" for f in eligible for i in range(20) for arm in ("zero", "positive")}
    else:
        valid_live &= not eligible and ((live.get("selected_rung") is None and live.get("reason") == "no_selected_dose")
            or (live.get("selected_rung") in p.RUNGS and live.get("reason") == "neither_predeclared_positive_feature_active_on_JSON_probes"))
    actual = {n for n in files if n.startswith("liveness/")}
    valid_live &= actual == {"liveness/" + key + suffix for key in expected for suffix in (".json", ".dispatch.json")}
    for name in actual:
        row = _json(files[name])
        valid_live &= row.get("plan_sha256") == PLAN_SHA256 and row.get("id") == name.split("/")[1].split(".")[0]
        valid_live &= name.endswith(".dispatch.json") or row.get("freeze_commit") == FREEZE
    done = _json(files["complete.json"]) if "complete.json" in files else {}
    marked = (done.get("pass") is True and done.get("meaning") == "inventory_complete_not_scientific_gate"
              and done.get("forwards") == len(plan["rows"]) and done.get("plan_sha256") == PLAN_SHA256
              and done.get("freeze_commit") == FREEZE)
    complete = (result["complete"] and result["pass"] is True and marked and valid_live
                and {"calibration-state.json", "calibration-analysis.json", "pressure-analysis.json"} <= files.keys()
                and not any(n.endswith(".pending") for n in files) and "failed.json" not in files and "controller-exit.json" in files
                and _json(files["controller-exit.json"]).get("exit_code") == 0)
    return {"status": "complete" if complete else "incomplete", "raw_audit": result,
            "completion_meaning": "inventory_complete_not_scientific_gate", "worker_completion_marker": marked,
            "liveness_inventory_complete": bool(valid_live), "scientific_gate_evaluated": False,
            "absent_forward_files": len(plan["rows"]) - sum(n.startswith("forwards/") and n.endswith(".json") for n in files),
            "pending_temporary_files": sorted(n for n in files if n.endswith(".pending")),
            "unresolved_liveness_dispatches": sorted(n for n in actual if n.endswith(".dispatch.json")
                                                       and n.replace(".dispatch.json", ".json") not in actual)}


def copy_release(base, destination, *, allow_incomplete=False):
    base, destination = safe(base), safe(destination)
    _require(not destination.exists(), "Destination exists; overwrite forbidden")
    _require(not destination.is_relative_to(base) and not base.is_relative_to(destination), "Overlapping directories")
    plan = verify_sources()
    ledger_hash = p.sha(safe(base / "events.jsonl"))
    events, receipt, closure = lifecycle(base, plan)
    data = receipt["data"]
    lineage = []
    for event in events.values():
        if not event["id"].startswith("retrieval:") or event == receipt:
            continue
        prior = event["data"]
        _require(prior["pod_id"] == closure["pod_id"], "Foreign snapshot in lineage")
        forward_map = {n: h for n, h in prior["artifacts"].items() if n.startswith("forwards/") and n.endswith(".json")}
        _require(all(data["artifacts"].get(n) == h for n, h in forward_map.items()), "Earlier forward bytes lost")
        earlier = None if prior.get("no_worker_dispatched") else safe(prior["directory"])
        if earlier is not None:
            _require(earlier.is_relative_to(base / "retrievals")
                     and {n: p.sha(f) for n, f in _files(earlier).items()} == prior["artifacts"], "Prior snapshot changed")
        pending = [{"path": n, "sha256": h, "final_path": n.removesuffix(".pending"),
                    "status": "byte_exact_final_json" if data["artifacts"].get(n.removesuffix(".pending")) == h
                    else "not_a_committed_outcome"} for n, h in prior["artifacts"].items()
                   if n.startswith("forwards/") and n.endswith(".json.pending")]
        lineage.append({"retrieval_event_sha256": event["sha256"], "raw_audit": partial_audit(earlier, plan),
                        "committed_forward_payloads_preserved": len(forward_map), "all_committed_forward_bytes_preserved": True,
                        "pending_reconciliation": pending, "recorded_audits": [
                            {k: v for k, v in row["data"].get("report", {}).items() if k in REPORT_KEYS}
                            for row in events.values() if row["data"].get("retrieval_sha256") == event["sha256"]
                            and "report" in row["data"]]})
    root = None if data.get("no_worker_dispatched") else safe(data["directory"])
    if root is None:
        _require("worker-intent" not in events and data["artifacts"] == {}, "Dispatched evidence omitted")
        files = {}
    else:
        _require(root.is_relative_to(base / "retrievals"), "Snapshot outside attempt retrievals")
        files = inventory(root, data["artifacts"], plan)
        _require(bool({"controller-exit.json", "controller-stopped.json"} & files.keys()), "Missing worker closure")
    result = assess(root, files, plan)
    historical = events.get("final-structural-audit", {}).get("data")
    if historical is not None:
        _require(historical["retrieval_sha256"] == receipt["sha256"], "Historical audit linkage failed")
        result["lifecycle_audit"] = {k: historical[k] for k in ("status", "error_type") if k in historical}
        result["lifecycle_audit"]["report"] = {k: v for k, v in historical.get("report", {}).items() if k in REPORT_KEYS}
    _require(allow_incomplete or result["status"] == "complete", "Incomplete release requires --allow-incomplete")
    provenance = {"schema": "steering_fidelity_calibration_release_v1", "freeze_commit": FREEZE,
        "plan_path": PLAN_PATH, "plan_sha256": PLAN_SHA256, **result, "closure": closure,
        "cost_scope": "controller upper bounds including prior attempts and storage reserve; not a reconciled bill",
        "lifecycle_sha256": ledger_hash, "final_retrieval_sha256": p.sha(base / "final-retrieval.json"),
        "retrieval_event_sha256": receipt["sha256"], "artifacts": data["artifacts"], "snapshot_lineage": lineage}
    destination.mkdir()
    for name, source in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
        _require(p.sha(target) == data["artifacts"][name], "Copy changed bytes; candidate unsealed")
    with (destination / "retrieval_and_cost.json").open("x") as stream:
        stream.write(p.canonical(provenance) + "\n")
    for name, path in _files(destination).items():
        scan(name, path)
    _require(p.sha(safe(base / "events.jsonl")) == ledger_hash
             and p.sha(safe(base / "final-retrieval.json")) == provenance["final_retrieval_sha256"]
             and (root is None or {n: p.sha(f) for n, f in _files(root).items()} == data["artifacts"]),
             "Post-close source mutation; candidate unsealed")
    manifest = {"schema": provenance["schema"], "status": result["status"], "freeze_commit": FREEZE,
        "plan_sha256": PLAN_SHA256, "files": [{"path": n, "sha256": p.sha(f), "bytes": f.stat().st_size}
            for n, f in _files(destination).items()], "builder_sha256": p.sha(Path(__file__))}
    with (destination / "RELEASE_MANIFEST.json").open("x") as stream:
        stream.write(p.canonical(manifest) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    result = copy_release(args.base, args.destination, allow_incomplete=args.allow_incomplete)
    print(p.canonical({"status": result["status"], "files": len(result["files"])}))
