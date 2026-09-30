#!/usr/bin/env python3
"""Copy a closed, hash-verified exposure run without its private lifecycle.

This creates a publication candidate, not permission to commit safetensors.
The separate bounded-capture public auditor and its reviewed registry still
have to approve this release. No model, pod, API, or network calls are made.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.sae_assay_diagnostic.budget import EventLedger, _number, _utc
from experiments.sae_assay_diagnostic.protocol import canonical, sha
from experiments.sae_assay_exposure import analysis
from experiments.sae_assay_exposure.protocol import load_plan
from scripts.audit_public_release import scan_blob


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESTINATION = ROOT / "data/sae_assay_exposure/screen_precision_20260930"
PLAN_SHA256 = "52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9"
PLAN_PATH = "data/sae_assay_exposure/plan_20260930/PLAN.json"
REPORTING_SOURCES = ("scripts/release_sae_exposure.py", "scripts/report_sae_exposure.py")
PUBLIC_ROOT_FILES = frozenset({
    "cheap-qualification.json", "tokenizer-verification.json",
    "model-bf16-load-00003.json", "first-five-audit.json", "summary.json",
    "precision-pilot-summary.json", "DONE-all.json", "ARTIFACTS.json",
    "WAITING-qualification.json", "WAITING-first-five.json",
    "APPROVE-qualification", "APPROVE-first-five", "receipts.jsonl",
    "pip-freeze.txt", "controller.log", "controller-exit.json",
    "controller-stopped.json", "controller-worker-reconciled.json", "failure.json",
})
PILOT_FILES = frozenset("precision_pilot/" + name for name in (
    "binding.json", "qualification.json", "receipts.jsonl", "summary.json", "failure.json"))
MODES = ("native_zero", "precision_sham", "suppression", "amplification")
MAX_TEXT_BYTES = 32 * 1024 * 1024
MAX_CLEAN_BYTES = 256 * (8192 * 2 + 8) + 8192
MAX_PILOT_BYTES = 256 * (8192 * 10 + 6 * 4 * 7 + 13) + 16384
MAX_TOTAL_BYTES = 1600 * 1024 * 1024
PRIVATE_TEXT = re.compile(
    r"(?:/Users/|/home/|/private/(?:tmp|var)/|[A-Za-z]:\\Users\\|"
    r"(?:root|ubuntu)@\d{1,3}(?:\.\d{1,3}){3}|\.ssh/|known_hosts|"
    r"credential-intent|credential-removed)")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=lambda _: _require(False, "Nonfinite JSON"))


def _relative(name):
    _require(isinstance(name, str) and bool(name), "Invalid artifact path")
    path = PurePosixPath(name)
    _require(not path.is_absolute() and path.as_posix() == name and name != "."
             and "\\" not in name and all(not part.startswith(".") for part in path.parts)
             and all(32 <= ord(c) < 127 for c in name), "Invalid artifact path")
    return path


def _files(root):
    root = Path(root)
    _require(root.is_dir() and not root.is_symlink(), "Invalid artifact directory")
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        _require(not stat.S_ISLNK(mode), "Artifact symlink")
        if stat.S_ISDIR(mode):
            continue
        _require(stat.S_ISREG(mode), "Nonregular artifact")
        name = path.relative_to(root).as_posix()
        _relative(name)
        result[name] = path
    return result


def _ledger(path, plan_hash, freeze, ids):
    # EventLedger binds on construction. Never let a missing source create a
    # fresh apparently valid ledger during publication.
    path = Path(path)
    _require(path.is_file() and not path.is_symlink(), "Missing regular ledger")
    before = sha(path)
    events = EventLedger(path, plan_hash, freeze, ids).read()
    _require(sha(path) == before, "Publication changed a source ledger")
    return events


def _scan_text(name, path, private_paths=()):
    raw = path.read_bytes()
    _require(len(raw) <= MAX_TEXT_BYTES, "Text artifact exceeds publication bound")
    _require(not scan_blob(name, raw), "Public content scan failed: " + name)
    text = raw.decode("utf-8")
    # Decode escaping too: a serialized slash or token is still private data.
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)
    if name.endswith(".json"):
        text += "\n" + "\n".join(strings(_json(path)))
    elif name.endswith(".jsonl"):
        text += "\n" + "\n".join(s for line in raw.splitlines()
                                  for s in strings(json.loads(line)))
    _require(not scan_blob(name, text.encode()), "Decoded public content scan failed: " + name)
    _require(not PRIVATE_TEXT.search(text), "Private lifecycle content: " + name)
    _require(not any(str(p) in text for p in private_paths), "Private local path: " + name)


def _allowlist(plan):
    names = set(PUBLIC_ROOT_FILES | PILOT_FILES)
    names.add("rows/qualification-live.json")
    for item in plan["texts"]:
        _require(re.fullmatch(r"[A-Za-z0-9_-]+", item["id"]) is not None, "Unsafe plan text ID")
        names.update(("rows/clean-" + item["id"] + ".json",
                      "residuals/" + item["id"] + ".safetensors"))
    for ordinal in range(48):
        names.update((f"precision_pilot/rows/{ordinal:03d}.json",
                      f"precision_pilot/tensors/{ordinal:03d}.safetensors"))
    return names


def _check_inventory(root, expected, allowed, private_paths=()):
    actual = _files(root)
    _require(set(actual) == set(expected), "Retrieved inventory differs from final receipt")
    _require(set(actual) <= allowed, "Unexpected retrieved artifact")
    _require(sum(p.stat().st_size for p in actual.values()) <= MAX_TOTAL_BYTES,
             "Release exceeds bounded activation inventory")
    for name, path in actual.items():
        digest = expected[name]
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                 and sha(path) == digest, "Retrieved artifact hash mismatch: " + name)
        if name.endswith(".safetensors"):
            limit = MAX_CLEAN_BYTES if name.startswith("residuals/") else MAX_PILOT_BYTES
            _require(8 < path.stat().st_size <= limit, "Capture exceeds bounded state schema")
        else:
            _scan_text(name, path, private_paths)
    return actual


def _worker_inventory(root, files, plan_hash, freeze, *, required):
    path = root / "ARTIFACTS.json"
    if not path.exists():
        _require(not required, "Missing terminal worker artifact inventory")
        return None
    value = _json(path)
    _require(value.get("schema") == "sae_exposure_artifacts_v1"
             and value.get("plan_sha256") == plan_hash and value.get("freeze_commit") == freeze,
             "Worker artifact inventory binding mismatch")
    entries = value["files"]
    names = [entry["path"] for entry in entries]
    _require(len(names) == len(set(names)) and set(names) <= set(files)
             and "ARTIFACTS.json" not in names, "Worker artifact inventory mismatch")
    log_matches = None
    for entry in entries:
        _require(set(entry) == {"path", "sha256", "bytes"}, "Worker artifact entry schema")
        source = root / entry["path"]
        matches = entry["sha256"] == sha(source) and entry["bytes"] == source.stat().st_size
        if entry["path"] == "controller.log":
            # Exception tracebacks can follow the worker's finally snapshot.
            log_matches = matches
        else:
            _require(matches, "Terminal worker artifact changed")
    scientific = {name for name in files if name.startswith(("rows/", "residuals/", "precision_pilot/"))}
    _require(scientific <= set(names), "Worker snapshot omits scientific artifacts")
    return log_matches


def _partial_pilot(root, plan, plan_hash, freeze):
    from experiments.sae_assay_precision import pilot

    directory = root / "precision_pilot"
    if not directory.exists():
        return {"status": "not_started", "validated_rows": 0, "completed": False}
    ids = ["precision-pilot:" + item["id"] + ":" + mode
           for item in plan["precision_pilot"]["texts"] for mode in MODES]
    events = _ledger(directory / "receipts.jsonl", plan_hash, freeze, ids)
    _require(not any(e["data"].get("kind") == "complete" for e in events),
             "Incomplete release contains a completed pilot ledger")
    binding = _json(directory / "binding.json")
    _require(binding == {"schema": pilot.SCHEMA, "plan_sha256": plan_hash,
                         "freeze_commit": freeze,
                         "text_ids": [item["id"] for item in plan["precision_pilot"]["texts"]]},
             "Partial pilot binding mismatch")
    dispatches = [e for e in events if e["data"].get("kind") == "dispatch"]
    receipts = [e for e in events if e["data"].get("kind") == "row"]
    _require([e["data"]["row_id"] for e in dispatches] == ids[:len(dispatches)]
             and [e["data"]["row_id"] for e in receipts] == ids[:len(receipts)]
             and len(receipts) <= len(dispatches) <= min(48, len(receipts) + 1),
             "Partial pilot is not a single unretried prefix")
    for ordinal, event in enumerate(dispatches):
        _require(event["id"] == "dispatch:" + ids[ordinal]
                 and event["data"] == {"kind": "dispatch", "row_id": ids[ordinal],
                    "ordinal": ordinal, "full_model_forwards": 1},
                 "Partial pilot dispatch differs from fixed forward inventory")
    rows, captures = set(), set()
    for ordinal, event in enumerate(receipts):
        payload = event["data"]["payload"]
        name = f"rows/{ordinal:03d}.json"
        _require(payload["path"] == name and sha(directory / name) == payload["sha256"]
                 and dispatches[ordinal]["seq"] < event["seq"], "Partial pilot receipt mismatch")
        row = _json(directory / name)
        _require(row["row_id"] == ids[ordinal] and row["freeze_commit"] == freeze
                 and row.get("test_only") is False
                 and row["capture"]["sha256"] == payload["capture_sha256"],
                 "Partial pilot row binding mismatch")
        pilot.validate_row(row, plan, directory)
        rows.add(name)
        captures.add(row["capture"]["path"])
    actual = _files(directory)
    _require({n for n in actual if n.startswith("rows/")} == rows
             and {n for n in actual if n.startswith("tensors/")} == captures,
             "Unreceipted partial pilot artifacts require a separate failure amendment")
    for event in events:
        if event["id"] in {"qualification", "failure"}:
            _require(event["data"]["sha256"] == sha(directory / (event["id"] + ".json")),
                     "Partial pilot diagnostic hash mismatch")
    _require(not (directory / "summary.json").exists(), "Incomplete pilot has a success summary")
    return {"status": "incomplete", "validated_rows": len(receipts), "completed": False}


def _audit(root, plan, plan_hash, freeze, *, allow_incomplete):
    from experiments.sae_assay_precision import pilot

    done_path = root / "DONE-all.json"
    done = _json(done_path) if done_path.exists() else None
    complete = done is not None and done.get("status") == "complete"
    _require(complete or allow_incomplete, "Incomplete run requires explicit --allow-incomplete")
    if done is not None:
        _require(done.get("plan_sha256") == plan_hash and done.get("freeze_commit") == freeze
                 and done.get("behavioral_assay_qualified") is False,
                 "Terminal plan/freeze/claim mismatch")
    if not complete:
        _require((done is not None and done.get("status") in {
            "technical_failure", "incomplete_budget_deadline", "failed_or_incomplete"})
            or (root / "controller-stopped.json").exists()
            or ((root / "controller-exit.json").exists()
                and _json(root / "controller-exit.json").get("exit_code") not in (None, 0)),
            "Incomplete run lacks a terminal failure/stop record")
    has_rows = (root / "receipts.jsonl").exists()
    _require(has_rows or not complete, "Missing clean ledger")
    rows = analysis.audit_run(root, plan, plan_hash, freeze, complete=complete) if has_rows else []
    _require(has_rows or not any(n.startswith(("rows/", "residuals/", "precision_pilot/"))
                                for n in _files(root)), "Scientific artifacts without a clean ledger")
    if done is not None:
        _require(done.get("exposure_rows") == len(rows), "Terminal clean count mismatch")
        ids = ["qualification-live", *("clean-" + item["id"] for item in plan["texts"])]
        events = _ledger(root / "receipts.jsonl", plan_hash, freeze, ids) if has_rows else []
        _require(done.get("rows") == sum(e["data"].get("kind") == "row" for e in events),
                 "Terminal receipt count mismatch")
    if len(rows) == len(plan["texts"]):
        summary = analysis.summarize(rows, plan, plan_sha256=plan_hash, freeze_commit=freeze)
        _require((root / "summary.json").exists() and _json(root / "summary.json") == summary,
                 "Clean summary reconstruction mismatch")
    else:
        _require(not (root / "summary.json").exists(), "Partial clean panel has a success summary")
    _require(not (root / "precision_pilot").exists() or len(rows) == len(plan["texts"]),
             "Precision pilot started before clean screening completed")
    if complete:
        _require(_json(root / "controller-exit.json").get("exit_code") == 0,
                 "Complete run has no successful process exit")
        checked = pilot.validate_run(root, plan, plan_hash, freeze)
        _require(checked.get("structural_pass") is True and checked.get("row_count") == 48,
                 "Full precision pilot audit required")
        summary = _json(root / "precision_pilot/summary.json")
        _require(summary.get("completed") is True and summary.get("full_model_forwards") == 48
                 and summary.get("test_only") is False and summary.get("overall_assay_qualified") is False
                 and summary == _json(root / "precision-pilot-summary.json"),
                 "Precision terminal summary mismatch")
        inventory = [{"path": "precision_pilot/" + name, "bytes": path.stat().st_size,
                      "sha256": sha(path)} for name, path in _files(root / "precision_pilot").items()]
        _require(done["precision_pilot"] == {"status": "complete",
                 "summary_path": "precision-pilot-summary.json",
                 "summary_sha256": sha(root / "precision-pilot-summary.json"), "artifacts": inventory},
                 "DONE precision summary/inventory mismatch")
        _require(not any((root / n).exists() for n in ("failure.json", "precision_pilot/failure.json")),
                 "Complete release contains failure records")
        pilot_audit = {"status": "complete", "validated_rows": 48, "completed": True}
    else:
        _require(done is None or done.get("precision_pilot") == {"status": "not_completed"},
                 "Incomplete terminal falsely claims a full pilot")
        _require(not (root / "precision-pilot-summary.json").exists(), "Incomplete run has pilot success summary")
        pilot_audit = _partial_pilot(root, plan, plan_hash, freeze)
    return {"status": "complete" if complete else "incomplete",
            "clean_validated_rows": len(rows), "expected_clean_rows": len(plan["texts"]),
            "precision_pilot": pilot_audit, "behavioral_assay_qualified": False,
            "raw_safetensors_public_approval": "separate_bounded_capture_audit_required"}


def _public_closure(closure):
    _require(isinstance(closure.get("pod_id"), str)
             and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", closure["pod_id"]), "Invalid closure pod ID")
    _require(type(closure.get("within_limits")) is bool and closure.get("get_status") == 404,
             "Invalid closure status")
    _utc(closure["utc"])
    _number(closure["elapsed_seconds"])
    for name in ("compute_upper_bound_usd", "cumulative_upper_bound_usd"):
        value = closure[name]
        if value is None:
            _require(not closure["within_limits"], "Unknown closure cost cannot claim within limits")
        else:
            _number(value)
    keys = ("pod_id", "get_status", "utc", "elapsed_seconds", "compute_upper_bound_usd",
            "cumulative_upper_bound_usd", "within_limits")
    return {key: closure[key] for key in keys}


def copy_release(base, destination, plan_path, freeze, *, allow_incomplete=False):
    base, destination, plan_path = Path(base), Path(destination), Path(plan_path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    _require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "Invalid freeze commit")
    _require(sha(plan_path) == PLAN_SHA256, "Unexpected exposure plan hash")
    # Post-run reporting commits intentionally need not equal the runtime freeze.
    plan = load_plan(plan_path)
    events = _ledger(base / "events.jsonl", PLAN_SHA256, freeze, [])
    closed = [event for event in events if event["id"] == "closed"]
    _require(len(closed) == 1 and closed[0]["data"].get("get_status") == 404,
             "Verified pod deletion required")
    receipt = _json(base / "final-retrieval.json")
    _require(receipt in events and receipt["id"].startswith("retrieval:")
             and receipt["seq"] < closed[0]["seq"], "Final retrieval is not in the verified lifecycle chain")
    _require(receipt == [event for event in events if event["id"].startswith("retrieval:")][-1],
             "Final retrieval points to a superseded snapshot")
    data, closure = receipt["data"], closed[0]["data"]
    _require(data["pod_id"] == closure["pod_id"], "Retrieval/deletion mismatch")
    _require(closure["pod_id"] not in closure.get("inventory_ids", []), "Closed pod remains in inventory")
    root, hashes = Path(data["directory"]), data["artifacts"]
    files = _check_inventory(root, hashes, _allowlist(plan), (base.resolve(), root.resolve()))
    audit = _audit(root, plan, PLAN_SHA256, freeze, allow_incomplete=allow_incomplete)
    audit["worker_snapshot_log_matches_final"] = _worker_inventory(
        root, files, PLAN_SHA256, freeze, required=audit["status"] == "complete")
    projection = {"schema": "sae_exposure_retrieval_v1", "freeze_commit": freeze,
                  "plan_sha256": PLAN_SHA256, "status": audit["status"],
                  "scope": "Projection of verified private receipts; local paths and SSH coordinates omitted",
                  "closure": _public_closure(closure), "artifacts": hashes}
    destination.mkdir(parents=True, exist_ok=False)
    for name, source in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        _require(sha(target) == hashes[name], "Copied artifact hash mismatch")
    for name, value in (("retrieval_and_cost.json", projection), ("PUBLICATION_AUDIT.json", audit)):
        with (destination / name).open("x") as handle:
            handle.write(canonical(value) + "\n")
        _scan_text(name, destination / name, (base.resolve(), root.resolve()))
    return projection


def manifest(directory, plan_path, freeze, *, additional_files=()):
    """Bind explicitly named reports; never register or approve raw captures."""
    directory, plan_path = Path(directory), Path(plan_path)
    output = directory / "RELEASE_MANIFEST.json"
    if output.exists():
        raise FileExistsError(output)
    _require(sha(plan_path) == PLAN_SHA256, "Unexpected exposure plan hash")
    plan = load_plan(plan_path)
    projection, audit = (_json(directory / name) for name in (
        "retrieval_and_cost.json", "PUBLICATION_AUDIT.json"))
    _require(projection["freeze_commit"] == freeze and projection["plan_sha256"] == PLAN_SHA256
             and projection["status"] == audit["status"] and projection["closure"]["get_status"] == 404,
             "Publication projection binding mismatch")
    actual = _files(directory)
    raw = projection["artifacts"]
    _require(set(raw) <= _allowlist(plan) and all(name in actual and sha(actual[name]) == digest
             for name, digest in raw.items()), "Published raw artifacts changed")
    extra = set(additional_files)
    for name in extra:
        path = _relative(name)
        _require(path.suffix in {".json", ".csv", ".md", ".svg", ".png", ".pdf"}
                 and (path.parts[0] in {"analysis", "figures", "tables"}
                      or name in {"README.md", "ATTRIBUTION.md", "NOTICE.md", "REPORT.json", "REPORT.md"})
                 and not any(part in {"events.json", "events.jsonl", "credentials.json",
                     "final-retrieval.json", "checkpoint.md", "worker-closing.json"} for part in path.parts)
                 and name not in raw and name not in {"PUBLICATION_AUDIT.json", "retrieval_and_cost.json"},
                 "Invalid explicitly named publication artifact")
    _require(set(actual) == set(raw) | extra | {"PUBLICATION_AUDIT.json", "retrieval_and_cost.json"},
             "Unlisted publication artifact")
    verified = _audit(directory, plan, PLAN_SHA256, freeze, allow_incomplete=audit["status"] == "incomplete")
    verified["worker_snapshot_log_matches_final"] = _worker_inventory(
        directory, raw, PLAN_SHA256, freeze, required=audit["status"] == "complete")
    _require(verified == audit, "Publication audit changed")
    records = []
    for name, path in actual.items():
        _require(path.stat().st_size <= (MAX_PILOT_BYTES if name.endswith(".safetensors") else MAX_TEXT_BYTES),
                 "Publication artifact exceeds size bound")
        if not name.endswith((".safetensors", ".png", ".pdf")):
            _scan_text(name, path)
        elif not name.endswith(".safetensors"):
            _require(not scan_blob(name, path.read_bytes()), "Figure public content scan failed")
        records.append({"path": name, "bytes": path.stat().st_size, "sha256": sha(path)})
    result = {"schema": "sae_assay_exposure_release_v1", "freeze_commit": freeze,
              "plan_path": PLAN_PATH, "plan_sha256": PLAN_SHA256,
              "status": audit["status"], "files": records,
              "reporting_source_hashes": {name: sha(ROOT / name) for name in REPORTING_SOURCES},
              "raw_safetensors_public_approval": "separate_bounded_capture_audit_required",
              "scope": "Authored clean exposure screen and separate transport pilot; no behavioral assay qualification"}
    with output.open("x") as handle:
        handle.write(canonical(result) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--additional-file", action="append", default=[])
    args = parser.parse_args()
    if args.manifest_only:
        result = manifest(args.destination, args.plan, args.freeze, additional_files=args.additional_file)
        print(canonical({"files": len(result["files"]), "status": result["status"]}))
    else:
        if args.base is None or args.additional_file:
            parser.error("--base required for copy; --additional-file applies to --manifest-only")
        result = copy_release(args.base, args.destination, args.plan, args.freeze,
                              allow_incomplete=args.allow_incomplete)
        print(canonical({"files": len(result["artifacts"]), "status": result["status"]}))


if __name__ == "__main__":
    main()
