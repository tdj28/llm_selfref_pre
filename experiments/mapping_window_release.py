"""Offline publication adapter for the frozen 512-token dose-window study.

Build a new destination from a terminal retrieval, preserving every raw byte.
Completed stopping branches are not positive findings. External controller
receipts authenticate lifecycle claims; checksums alone do not establish origin.
This unfrozen packaging sidecar never authorizes collection or publication.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import shutil
import tempfile

from experiments import mapping_scaled_release as base
from experiments.berg_dose_window import analysis, protocol
from experiments.sae_assay_diagnostic.budget import _utc
from scripts.release_berg_source import _frozen_blob, _git
from scripts.release_sae_exposure import _files, _json, _relative, _require, _scan_text


SCHEMA = "mapping_window_release_v1"
PLAN_PATH = protocol.PLAN
MODES, FIGURES, FIGURE_FILES = base.MODES, base.FIGURES, base.FIGURE_FILES
GENERATED = base.GENERATED
ROOT_FILES = base.ROOT_FILES | {"zero_screen.json"}
_digest, _write, _canonical_json, _entries = base._digest, base._write, base._canonical_json, base._entries
_read_ledger, _receipt, _plots = base._read_ledger, base._receipt, base._plots


def _verify_sources(plan_bytes, reference):
    freeze, name = reference["freeze_commit"], reference["plan_path"]
    _require(name == PLAN_PATH, "Wrong source plan path")
    _require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "Full freeze commit required")
    _require(_git("cat-file", "-t", freeze).strip() == b"commit", "Freeze is not a commit")
    _require(_frozen_blob(freeze, name) == plan_bytes, "Plan differs from frozen Git blob")
    _require(reference["plan_sha256"] == _digest(plan_bytes), "Plan reference hash mismatch")
    plan = json.loads(plan_bytes)
    _require(plan_bytes == (protocol.canonical(plan) + "\n").encode(), "Noncanonical source plan")
    _require(all(protocol.canonical(plan.get(k)) == protocol.canonical(v)
                 for k, v in protocol.design_fields().items()), "Changed frozen window design")
    source = protocol.source
    _require(plan["model"] == {"id": source.MODEL_ID, "revision": source.MODEL_REVISION, "precision": "bf16"}
             and plan["sae"] == {"id": source.SAE_ID, "revision": source.SAE_REVISION, "sha256": source.SAE_FILE_SHA256}
             and plan["notebook"]["url"] == source.NOTEBOOK_URL
             and plan["notebook"]["sha256"] == source.NOTEBOOK_SHA
             and set(plan["source_hashes"]) == set(protocol.source_paths())
             and set(plan["input_hashes"]) == {source.MATCHING, protocol.MAPPING, protocol.POWER, protocol.PREDECESSOR},
             "Changed model, notebook, or source/input closure")
    for section in ("source_hashes", "input_hashes"):
        _require(reference[section] == plan[section], "Source reference differs from plan")
        for path, digest in plan[section].items():
            _relative(path)
            _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid source digest")
            _require(_digest(_frozen_blob(freeze, path)) == digest, "Frozen blob mismatch: " + path)
            if section == "source_hashes":
                local = protocol.ROOT / path
                _require(local.is_file() and not local.is_symlink() and protocol.sha(local) == digest,
                         "Audit implementation differs from frozen source: " + path)
    return plan


def _raw_inventory(root, plan):
    files = _files(root)
    ids = {r["id"] for r in plan["rows"]} | {"qualification-live"}
    _require(all(re.fullmatch(r"[A-Za-z0-9_+-]+", rid) for rid in ids), "Unsafe planned ID")
    allowed = ROOT_FILES | {f"rows/{rid}.{ext}" for rid in ids for ext in ("json", "pending")}
    _require(sum(p.stat().st_size for p in files.values()) <= base.MAX_TOTAL_BYTES, "Oversized release")
    for name, path in files.items():
        _require(name in allowed or re.fullmatch(r"model-bf16-load-[0-9]{5}\.json", name),
                 "Unapproved raw artifact: " + name)
        _scan_text(name + ".json" if name.endswith(".pending") else name, path)
        if name.startswith("rows/") and name.endswith(".json"):
            _require(_json(path)["id"] == path.stem, "Row filename differs from its ID")
    return files


def _number(value):
    _require(isinstance(value, str), "Exact decimal string required")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid controller decimal") from exc
    _require(number.is_finite() and number >= 0, "Invalid controller cost/time")
    return number


def _controller(receipt_path, ledger_path, reference, artifacts):
    public = {"retrieval": {"status": "not_provided"},
              "lifecycle": {"status": "not_provided", "cost": None, "deletion_verified": None}}
    if receipt_path is None:
        _require(ledger_path is None, "Controller ledger requires its external final receipt")
        return public
    event = _receipt(Path(receipt_path), reference)
    _require(event["data"]["artifacts"] == artifacts, "Final retrieval inventory/hash mismatch")
    no_worker = event["data"].get("no_worker_dispatched", False)
    _require(type(no_worker) is bool and (not no_worker or not artifacts), "Invalid no-worker receipt")
    public["retrieval"] = {"status": "receipt_hash_verified", "event_sha256": event["sha256"],
        "receipt_sha256": protocol.sha(receipt_path), "artifacts": artifacts, "no_worker_dispatched": no_worker}
    if ledger_path is None:
        return public
    events = _read_ledger(Path(ledger_path), reference["plan_sha256"], reference["freeze_commit"])
    _require(event in events, "Final receipt is not bound to controller ledger")
    _require(not any(e["id"].startswith("retrieval:") and e["seq"] > event["seq"] for e in events),
             "Provided receipt is not the final controller retrieval")
    by_id = {e["id"]: e for e in events}
    _require(not no_worker or "worker-intent" not in by_id, "No-worker receipt conflicts with dispatch intent")
    created, intent = by_id.get("created"), by_id.get("create-intent")
    config = by_id.get("controller:config", {}).get("data", {})
    _require(created is not None and intent is not None
             and intent["seq"] < created["seq"] < event["seq"]
             and config == {"kind": "main", "namespace": "dose-window-controller", "plan_path": PLAN_PATH,
                            "budget": protocol.BUDGET, "hard_seconds": protocol.MAIN_SECONDS},
             "Foreign or non-main controller retrieval")
    creation, pod = intent["data"], created["data"]
    _require(pod.get("id") == event["data"].get("pod_id")
             and re.fullmatch(r"codex-dose-window-20261004-main-[0-9a-f]{12}", pod.get("name", ""))
             and creation["payload"]["name"] == pod["name"] and pod["id"] not in creation["blocked"]
             and creation["plan_sha256"] == reference["plan_sha256"]
             and creation["freeze_commit"] == reference["freeze_commit"], "Foreign owned-pod binding")
    prior, cheap = _number(creation["prior_total_usd"]), _number(creation["prior_new_usd"])
    rate = _number(creation["quote"]["hourly_rate_usd"]) + Decimal("0.10")
    _require(prior == Decimal(protocol.PRIOR_USD), "Prior study cost carry mismatch")
    full_cost = cheap + rate * protocol.MAIN_SECONDS / 3600
    _require(full_cost <= Decimal(protocol.NEW_CAP_USD) and prior + full_cost <= Decimal(protocol.BUDGET["total_usd"]),
             "Controller all-in admission exceeds frozen study budget")
    start = _utc(creation["created_utc"])
    _require((_utc(creation["hard_deadline_utc"]) - start).total_seconds() == protocol.MAIN_SECONDS
             and (_utc(creation["deadline_utc"]) - start).total_seconds()
             == protocol.MAIN_SECONDS - protocol.RESERVE_SECONDS, "Controller timer/reserve mismatch")
    public["retrieval"]["status"] = "externally_bound_controller_ledger"
    lifecycle = {"status": "unresolved", "cost": None, "deletion_verified": False,
                 "ledger_sha256": protocol.sha(ledger_path), "budget": protocol.BUDGET}
    closed = by_id.get("closed")
    if closed is not None:
        data, delete = closed["data"], by_id.get("delete-intent")
        _require(delete is not None and event["seq"] < delete["seq"] < closed["seq"]
                 and data["pod_id"] == pod["id"] == delete["data"].get("pod_id"),
                 "Deletion does not follow matching retrieval")
        response = by_id.get("delete-response")
        if response is not None:
            _require(delete["seq"] < response["seq"] < closed["seq"]
                     and response["data"].get("pod_id") == pod["id"]
                     and type(response["data"].get("status")) is int, "Foreign deletion response")
        elapsed = _number(data["elapsed_seconds"])
        cost, total = _number(data["compute_upper_bound_usd"]), _number(data["cumulative_upper_bound_usd"])
        _require(cost >= elapsed * rate / 3600 and total == prior + (cheap + cost),
                 "Controller cumulative cost does not preserve carry/storage")
        within = (elapsed <= protocol.MAIN_SECONDS and total <= Decimal(protocol.BUDGET["total_usd"])
                  and cheap + cost <= Decimal(protocol.NEW_CAP_USD))
        _require(type(data["within_limits"]) is bool and data["within_limits"] == within
                 and type(data["get_status"]) is int and isinstance(data["inventory_ids"], list)
                 and all(isinstance(i, str) for i in data["inventory_ids"]), "Malformed closure status")
        deleted = data["get_status"] == 404 and pod["id"] not in data["inventory_ids"]
        lifecycle.update(status="closed" if deleted else "unresolved", deletion_verified=deleted,
            closed_event_sha256=closed["sha256"],
            cost={**{k: data[k] for k in ("elapsed_seconds", "compute_upper_bound_usd",
                    "cumulative_upper_bound_usd", "within_limits")},
                  "prior_study_usd": creation["prior_total_usd"], "current_cheap_usd": creation["prior_new_usd"],
                  "new_spend_upper_bound_usd": str(cheap + cost)},
            cost_basis="controller_upper_bounds_not_provider_invoice",
            direct_get_status=data["get_status"],
            delete_response_status=response["data"]["status"] if response else None,
            full_inventory_sha256=_digest(protocol.canonical(data["inventory_ids"]).encode()))
    public["lifecycle"] = lifecycle
    return public


def _audit(root, plan, reference, mode, *, no_worker=False):
    _require(mode in MODES, "Explicit terminal release mode required")
    _require(not no_worker or mode == "partial_technical_failure" and not _files(root),
             "No-worker release must be empty and incomplete")
    if (root / "PLAN.json").exists():
        _require(protocol.sha(root / "PLAN.json") == reference["plan_sha256"], "Raw plan hash mismatch")
    if (root / "runtime.json").exists():
        runtime = _json(root / "runtime.json")
        _require(runtime["plan_sha256"] == reference["plan_sha256"]
                 and runtime["freeze_commit"] == reference["freeze_commit"], "Runtime freeze mismatch")
    rows = analysis.load_rows(root)
    seen = {r["id"] for r in rows}
    _require(len(seen) == len(rows), "Duplicate scientific rows")
    receipts = analysis.old.receipt_audit(root, plan, seen, settled=False)
    if receipts["state"] == "awaiting_runner":
        _require(not rows and not any((root / "rows").glob("*")) and not any((root / p).exists() for p in
                 ("zero_screen.json", "selection.json", "audit.json", "throughput.json",
                  "WAITING-qualification.json", "WAITING-first-five.json", "APPROVE-qualification", "APPROVE-first-five")),
                 "Incomplete scientific bindings are not an empty startup")
        if (root / "receipts.jsonl").exists():
            _require(mode == "partial_technical_failure", "Startup ledger is not completed collection")
            base._startup_ledger(root, plan, reference)
    done = _json(root / "DONE-all.json") if (root / "DONE-all.json").exists() else None
    branch = "technical_failure"
    if mode == "completed":
        result = analysis.audit(root, plan, partial=False, settled=True)
        zero_pass, selected = result["zero_screen_pass"], result["selected_dose"]
        expected = 12 if zero_pass is False else 204 if selected is None else 684
        _require(type(result["generations"]) is int and result["generations"] == expected
                 and done is not None and done.get("pass") is True
                 and done.get("schema") == "dose_window_completion_v1"
                 and done.get("plan_sha256") == reference["plan_sha256"]
                 and done.get("freeze_commit") == reference["freeze_commit"]
                 and type(done.get("generations")) is int and done["generations"] == expected
                 and done.get("selected_dose") == selected and done.get("zero_screen_pass") is zero_pass
                 and done.get("main_run") is (selected is not None)
                 and done.get("stop_reason") == result["stop_reason"], "Invalid window completion marker")
        _require(not (root / "failed.json").exists() and not list((root / "rows").glob("*.pending")),
                 "Completed release contains failure/pending evidence")
        scientific = {"status": "strict_completed", "audit": result}
        branch = "zero_screen_failed" if not zero_pass else "calibration_failed" if selected is None else "main_completed"
    else:
        _require(done is None, "Completion marker conflicts with technical-failure mode")
        _require(no_worker or (root / "failed.json").exists() or (root / "controller-stopped.json").exists()
                 or ((root / "controller-exit.json").exists()
                     and _json(root / "controller-exit.json").get("exit_code") not in (None, 0)),
                 "Partial release requires terminal failure/stop evidence")
        _require(not (root / "analysis/summary.json").exists(), "Partial release has completed inference")
        if (root / "failed.json").exists():
            _require(_json(root / "failed.json").get("plan_sha256") == reference["plan_sha256"], "Failure plan binding mismatch")
        if receipts["state"] == "awaiting_runner":
            scientific = {"status": "not_certified", "reason": "Runner initialization incomplete; awaiting_runner"}
        else:
            try:
                result = analysis.audit(root, plan, partial=True, settled=True)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                scientific = {"status": "not_certified", "error_type": type(exc).__name__,
                              "reason": "Frozen strict partial audit failed; no scientific results certified"}
            else:
                scientific = {"status": "strict_partial_only", "audit": result}
    specs = {s["id"]: s for s in plan["rows"]}
    observed = [specs[rid] for rid in seen if rid in specs]
    pending = sorted(p.name for p in (root / "rows").glob("*.pending"))
    attempted = seen | set(receipts["pending_dispatches"]) | {Path(p).stem for p in pending}
    main_rows = sum(s["phase"] == "main" for s in observed)
    main_attempted = any(specs.get(rid, {}).get("phase") == "main" for rid in attempted)
    calibration_rows = sum(s["phase"] == "calibration" for s in observed)
    return {"schema": SCHEMA, "mode": mode, "branch": branch, "scientific": scientific, "receipts": receipts,
        "no_worker_dispatched": no_worker, "observed_rows": len(rows), "observed_calibration_rows": calibration_rows,
        "observed_main_rows": main_rows, "pending_files": pending,
        "main_status": "completed" if branch == "main_completed" else "incomplete" if main_attempted else "not_run",
        "treated_calibration_status": ("not_run" if branch == "zero_screen_failed" else
            "completed" if mode == "completed" else "incomplete" if any(
                specs.get(rid, {}).get("phase") == "calibration" and specs[rid]["family"] != "zero"
                for rid in attempted if rid in specs) else "not_run"),
        "unrun_trials": ({"treated_calibration": 192 if branch == "zero_screen_failed" else 0,
                          "main": 0 if branch == "main_completed" else 480} if mode == "completed" else None),
        "claims": "Model-judge labels, not validated experience reports. Unrun branches are not zero effects. "
                  "Delivery and native-coordinate diagnostics are descriptive, not semantic suppression or consciousness evidence."}


def _summary(root, mode):
    if mode != "completed":
        return None
    with tempfile.TemporaryDirectory(prefix="mapping-window-analysis-") as temporary:
        summary = analysis.analyze(root, Path(temporary))
        original = root / "analysis/summary.json"
        if original.exists():
            _require(original.read_bytes() == (Path(temporary) / "summary.json").read_bytes(),
                     "Saved summary differs from frozen analysis")
        return summary


def _figure_data(root, report, summary):
    # The failed zero screen has medians but deliberately has no dose selection.
    plot_summary = summary
    if summary is not None and summary["selection"] is None:
        plot_summary = {"selection": {"zero_nll_medians": summary["zero_screen"]["zero_nll_medians"]}, "results": {}}
    data = base._figure_data(root, report, plot_summary)
    data.update(branch=report["branch"], treated_calibration_status=report["treated_calibration_status"],
                unrun_trials=report["unrun_trials"])
    _require(report["main_status"] == "completed" or not data["contrasts"], "Unrun main cannot have contrasts")
    return data


def build(source, destination, *, freeze, plan_path=None, mode="completed", controller_ledger=None):
    source, destination = Path(source), Path(destination)
    _require(not destination.exists() and not destination.is_symlink(), "Destination must be new")
    plan_path = Path(plan_path) if plan_path else protocol.ROOT / PLAN_PATH
    _require(plan_path.is_file() and not plan_path.is_symlink(), "Invalid source plan")
    plan = _canonical_json(plan_path)
    reference = {"freeze_commit": freeze, "plan_path": plan_path.resolve().relative_to(protocol.ROOT.resolve()).as_posix(),
                 "plan_sha256": protocol.sha(plan_path), "source_hashes": plan["source_hashes"], "input_hashes": plan["input_hashes"]}
    plan_bytes = plan_path.read_bytes()
    _verify_sources(plan_bytes, reference)
    receipt_path = None if source.is_dir() else source
    root = source
    if receipt_path is not None:
        payload = _receipt(receipt_path, reference)["data"]
        _require("directory" in payload or payload.get("no_worker_dispatched") is True, "Retrieval receipt lacks directory")
        root = Path(payload["directory"]) if "directory" in payload else None
    with (tempfile.TemporaryDirectory(prefix="mapping-window-empty-") if root is None else nullcontext(root)) as raw:
        root = Path(raw)
        _require(not destination.resolve().is_relative_to(root.resolve()), "Destination must be outside retrieval")
        files = _raw_inventory(root, plan)
        artifacts = {n: protocol.sha(p) for n, p in files.items()}
        controller = _controller(receipt_path, controller_ledger, reference, artifacts)
        report = _audit(root, plan, reference, mode, no_worker=controller["retrieval"].get("no_worker_dispatched", False))
        summary = _summary(root, mode)
        data = _figure_data(root, report, summary)
        destination.mkdir(parents=True, exist_ok=False)
        for name, path in files.items():
            target = destination / "raw" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            _require(protocol.sha(target) == artifacts[name], "Source changed during release copy")
        (destination / "raw").mkdir(exist_ok=True)
        _write(destination / "provenance/source.json", reference)
        (destination / "provenance/PLAN.json").write_bytes(plan_bytes)
        _write(destination / "provenance/controller.json", controller)
        _write(destination / "REPORT.json", report)
        _write(destination / "FIGURE_DATA.json", data)
        if summary is not None:
            _write(destination / "analysis/summary.json", summary)
        _plots(data, destination / "figures")
        inventory = _files(destination)
        for name, path in inventory.items():
            if name not in FIGURE_FILES:
                _scan_text(name, path)
        _write(destination / "MANIFEST.json", {"schema": SCHEMA, "mode": mode, "plan_sha256": reference["plan_sha256"],
                "freeze_commit": freeze, "files": _entries(inventory)})
    return verify(destination, controller_receipt=receipt_path, controller_ledger=controller_ledger)


def verify(root, *, expected_manifest_sha256=None, controller_receipt=None, controller_ledger=None):
    """Verify without rewriting; external anchors are optional and reported."""
    root = Path(root)
    files = _files(root)
    _require("MANIFEST.json" in files, "Missing manifest")
    manifest_path = files.pop("MANIFEST.json")
    digest = protocol.sha(manifest_path)
    _require(expected_manifest_sha256 is None or digest == expected_manifest_sha256, "External manifest digest mismatch")
    manifest = _canonical_json(manifest_path)
    _require(set(manifest) == {"schema", "mode", "plan_sha256", "freeze_commit", "files"}
             and manifest["schema"] == SCHEMA and manifest["mode"] in MODES, "Manifest schema mismatch")
    _require(isinstance(manifest["files"], list), "Manifest inventory must be a list")
    for entry in manifest["files"]:
        _require(isinstance(entry, dict) and set(entry) == {"path", "bytes", "sha256"}, "Invalid manifest entry")
        _relative(entry["path"])
        _require(type(entry["bytes"]) is int and entry["bytes"] >= 0 and isinstance(entry["sha256"], str)
                 and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), "Invalid manifest byte count/digest")
    _require(manifest["files"] == _entries(files), "Manifest inventory/bytes/hash mismatch")
    reference = _canonical_json(root / "provenance/source.json")
    _require(set(reference) == {"freeze_commit", "plan_path", "plan_sha256", "source_hashes", "input_hashes"}, "Invalid source reference")
    _require(all(reference[k] == manifest[k] for k in ("freeze_commit", "plan_sha256")), "Manifest binding mismatch")
    plan = _verify_sources((root / "provenance/PLAN.json").read_bytes(), reference)
    raw = _raw_inventory(root / "raw", plan)
    expected = GENERATED | FIGURE_FILES | {"raw/" + n for n in raw}
    if manifest["mode"] == "completed":
        expected |= {"analysis/summary.json"}
    _require(set(files) == expected, "Unexpected or missing release artifact")
    for name, path in files.items():
        if name not in FIGURE_FILES:
            _scan_text(name, path)
    controller = _canonical_json(root / "provenance/controller.json")
    report = _audit(root / "raw", plan, reference, manifest["mode"],
                    no_worker=controller["retrieval"].get("no_worker_dispatched", False))
    _require(_canonical_json(root / "REPORT.json") == report, "Report differs from raw audit")
    summary = _summary(root / "raw", manifest["mode"])
    if summary is not None:
        _require(_canonical_json(root / "analysis/summary.json") == summary, "Frozen summary mismatch")
    _require(_canonical_json(root / "FIGURE_DATA.json") == _figure_data(root / "raw", report, summary), "Figure data differs from raw evidence")
    artifacts = {name: protocol.sha(path) for name, path in raw.items()}
    if controller["retrieval"]["status"] != "not_provided":
        _require(controller["retrieval"]["artifacts"] == artifacts, "Public retrieval inventory mismatch")
    external = controller_receipt is not None
    _require(controller_ledger is None or external, "External ledger needs final receipt")
    if external:
        _require(controller == _controller(controller_receipt, controller_ledger, reference, artifacts),
                 "Public lifecycle differs from external controller evidence")
    return {"pass": True, "mode": manifest["mode"], "branch": report["branch"], "main_status": report["main_status"],
            "manifest_sha256": digest, "external_manifest_bound": expected_manifest_sha256 is not None,
            "external_controller_bound": external, "lifecycle_verified_this_check": external and controller_ledger is not None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument("--source", required=True, type=Path)
    create.add_argument("--destination", required=True, type=Path)
    create.add_argument("--freeze", required=True)
    create.add_argument("--plan", type=Path)
    create.add_argument("--mode", choices=MODES, required=True)
    create.add_argument("--controller-ledger", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("--root", required=True, type=Path)
    check.add_argument("--manifest-sha256")
    check.add_argument("--controller-receipt", type=Path)
    check.add_argument("--controller-ledger", type=Path)
    args = parser.parse_args(argv)
    if args.command == "build":
        result = build(args.source, args.destination, freeze=args.freeze, plan_path=args.plan,
                       mode=args.mode, controller_ledger=args.controller_ledger)
    else:
        result = verify(args.root, expected_manifest_sha256=args.manifest_sha256,
                        controller_receipt=args.controller_receipt, controller_ledger=args.controller_ledger)
    print(protocol.canonical(result))


if __name__ == "__main__":
    main()
