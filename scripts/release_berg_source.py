#!/usr/bin/env python3
"""Publish a verified closed Berg run, excluding the private pod ledger.

No network, GPU or API calls. Destination must be new. Raw bytes are copied,
never rewritten; analysis belongs in separate directories afterwards.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.berg_source_replication import analysis, protocol
from experiments.berg_source_diagnostics import validate_capture_schedule
from scripts.release_sae_exposure import (
    MAX_TEXT_BYTES, PRIVATE_TEXT, _files, _json, _ledger, _relative, _require, _scan_text,
)
from scripts.audit_public_release import path_findings, scan_blob


ROOT_FILES = {
    "receipts.jsonl", "pip-freeze.txt", "controller.log", "controller-exit.json",
    "controller-stopped.json", "controller-worker-reconciled.json",
    "WAITING-qualification.json", "WAITING-first-five.json",
    "APPROVE-qualification", "APPROVE-first-five", "DONE-all.json", "failed.json",
    "lens-metadata.json", "lens-replay-check.json", "static-directions.json",
    "audit.json", "analysis/summary.json", "analysis/curves.csv",
    "rows/qualification-live.json", "model-bf16-load-00002.json",
}

PAIRED_CSV = "secondary/paired_positions.csv"
PAIRED_CSV_MAX_BYTES = 64 * 1024**2
PAIRED_CSV_MAX_ROWS = 40 * 2 * 2 * 3 * 5 * 7 * 7
PAIRED_CSV_HEADER = (
    "source_id", "family", "seed", "coefficient", "history", "turn", "layer", "position",
    "relative_position", "phase", "transport", "group", "originating_row_id",
    "source_output_tokens", "terminal_observation_only", "normalized_logit_delta",
    "linear_logit_delta", "static_linear_prediction", "all_lexicon_static_cosine",
    "residual_delta_norm", "clean_residual_norm", "clean_transport_norm", "edited_transport_norm",
)


def reporting_sources(ensemble=False):
    common = ("scripts/release_berg_source.py", "scripts/reproduce_berg_source.py",
              "scripts/release_sae_exposure.py", "scripts/audit_public_release.py",
              "experiments/berg_source_diagnostics.py", "experiments/berg_source_figures.py")
    return common + (("experiments/berg_ensemble_diagnostics.py",) if ensemble else
                     ("docs/BERG_SOURCE_SECONDARY_DIAGNOSTICS_20260930.md",))


def _repo_path(name):
    _relative(name)
    root = protocol.ROOT.resolve()
    path = root/name
    _require(not path.is_symlink() and path.resolve().is_relative_to(root), "Unsafe repository path")
    return path


def _git(*args):
    # Never fetch missing promisor objects or honor replacement objects during verification.
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(protocol.ROOT), *args],
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
                            capture_output=True, check=False)
    _require(result.returncode == 0, "Cannot verify local frozen Git object")
    return result.stdout


def _frozen_blob(freeze, name):
    _relative(name)
    entries = _git("ls-tree", "-z", freeze, "--", name).split(b"\0")
    entries = [entry for entry in entries if entry]
    _require(len(entries) == 1, "Missing or ambiguous frozen blob: "+name)
    header, actual = entries[0].split(b"\t", 1)
    mode, kind, oid = header.split()
    _require(actual.decode() == name and mode in (b"100644", b"100755") and kind == b"blob",
             "Frozen artifact is not a regular Git blob: "+name)
    return _git("cat-file", "blob", oid.decode("ascii"))


def verify_freeze(plan_path, freeze):
    """Bind exact plan/source/input Git blobs without depending on current HEAD."""
    _require(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze),
             "Full freeze commit required")
    _require(_git("cat-file", "-t", freeze).strip() == b"commit", "Freeze must be a commit")
    plan_path = Path(plan_path)
    _require(not plan_path.is_symlink(), "Plan symlink")
    name = plan_path.resolve().relative_to(protocol.ROOT.resolve()).as_posix()
    _require(_frozen_blob(freeze, name) == plan_path.read_bytes(), "Plan differs from frozen Git blob")
    plan = _json(plan_path)
    for section in ("source_hashes", "input_hashes"):
        bindings = plan[section]
        _require(isinstance(bindings, dict) and bindings, "Missing frozen "+section)
        for path, digest in bindings.items():
            _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                     "Invalid frozen blob digest")
            _require(hashlib.sha256(_frozen_blob(freeze, path)).hexdigest() == digest,
                     "Frozen Git blob hash mismatch: "+path)
    return plan


def verify_reporting_sources(manifest):
    ensemble = manifest["schema"] == "berg_ensemble_release_v1"
    _require(manifest["schema"] in ("berg_source_release_v1", "berg_ensemble_release_v1"),
             "Unknown release schema")
    hashes = manifest["reporting_source_hashes"]
    _require(set(hashes) == set(reporting_sources(ensemble)), "Incomplete reporting-source binding")
    for name, digest in hashes.items():
        _require(protocol.sha(_repo_path(name)) == digest, "Reporting source changed: "+name)


def verify_receipts(root, plan, freeze):
    """Require the frozen serial dispatch/return trace and its exact raw bytes."""
    root = Path(root)
    ids = ["qualification-live"]+[r["id"] for r in plan["rows"]]
    ids += ["capture-"+r["id"] for r in plan["rows"] if r["capture"]]
    plan_hash = hashlib.sha256((protocol.canonical(plan)+"\n").encode()).hexdigest()
    events = _ledger(root/"receipts.jsonl", plan_hash, freeze, ids)
    scientific = [e for e in events if e["data"].get("kind") in ("dispatch", "row")]
    expected = [(kind, rid) for rid in ids for kind in ("dispatch", "row")]
    _require([(e["data"]["kind"], e["data"]["row_id"]) for e in scientific] == expected,
             "Dispatch/return chronology differs from frozen serial inventory")
    for event in scientific:
        data = event["data"]
        _require(event["id"] == data["kind"]+":"+data["row_id"], "Wrong dispatch/return event ID")
        if data["kind"] == "row":
            _require(data["payload"]["path"] == "rows/"+data["row_id"]+".json"
                     and protocol.sha(root/data["payload"]["path"]) == data["payload"]["sha256"],
                     "Raw receipt mismatch")


def verify_publication(root, plan, plan_hash, freeze):
    root = Path(root)
    receipt = _json(root/"retrieval_and_cost.json")
    _require(receipt["freeze_commit"] == freeze and receipt["plan_sha256"] == plan_hash,
             "Publication binding differs from verified retrieval")
    files = _files(root)
    for name, digest in receipt["artifacts"].items():
        _require(name in files and protocol.sha(files[name]) == digest,
                 "Original retrieved bytes changed before sealing: "+name)
    audit = _json(root/"PUBLICATION_AUDIT.json")
    _require(audit.get("pass") is True and audit.get("partial") is False
             and audit.get("generations") == audit.get("expected") == len(plan["rows"])
             and audit.get("freeze_commit") == freeze and audit.get("plan_sha256") == plan_hash
             and audit.get("receipts_verified") is True, "Missing or failed bound publication audit")
    _require(_json(root/"DONE-all.json") == {
        "pass": True, "plan_sha256": plan_hash, "freeze_commit": freeze,
        "rows": 1+len(plan["rows"])+sum(r["capture"] for r in plan["rows"])},
        "Completion does not match frozen inventory")
    verify_receipts(root, plan, freeze)
    return audit


def _scan_paired_csv(path, plan):
    """Stream the one bounded derived table; no raw outcome reads or cap changes."""
    _require(plan is not None and plan.get("schema") == "berg_source_public_v1",
             "Paired CSV requires the source-study plan")
    families = [f"feature-{f}" for f in protocol.TARGET_IDS] + [
        "aggregate-target", "aggregate-control-1", "aggregate-control-2", "aggregate-control-3"]
    expected = {}
    for family in families:
        dose = .7 if family.startswith("feature-") else .5
        for seed in (101, 202):
            for coefficient in (-dose, dose):
                identifier = f"{family}-{seed}-{coefficient:+.1f}-notebook-0.6-128"
                expected[identifier] = (family, seed, coefficient)
    captures = {s["id"]: s for s in plan["rows"] if s["capture"]}
    _require(set(captures) == set(expected), "Paired CSV capture inventory differs from known schema")
    for identifier, (family, seed, coefficient) in expected.items():
        spec = captures[identifier]
        _require((spec["family"], spec["seed"], spec["coefficient"], spec["prompt"],
                  spec["temperature"], spec["cap"]) == (family, seed, coefficient, "notebook", .6, 128),
                 "Paired CSV source specification mismatch")
    layers = (50, 65, 78)
    transports = ("identity", "jacobian") + tuple(f"random_j_{i}" for i in range(1, 6))
    groups = ("deception", "roleplay", "honesty", "hedging", "experience", "intervention", "unrelated")
    integer = re.compile(r"(?:0|[1-9][0-9]*)")
    number = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
    cases, count, total = {}, 0, 0

    def numeric(row, key):
        text = row[key]
        _require(bool(number.fullmatch(text)) and len(text) <= 64, "Invalid paired CSV numeric field: "+key)
        value = float(text)
        _require(math.isfinite(value), "Nonfinite paired CSV field: "+key)
        return value

    with path.open("rb") as stream:
        while raw := stream.readline(2049):
            total += len(raw)
            _require(total <= PAIRED_CSV_MAX_BYTES and len(raw) <= 2048,
                     "Paired CSV byte/record bound exceeded")
            _require(not scan_blob(PAIRED_CSV, raw), "Paired CSV public content scan failed")
            text = raw.decode("ascii")
            _require(not PRIVATE_TEXT.search(text), "Private paired CSV content")
            try:
                fields = next(csv.reader([text], strict=True))
            except csv.Error as exc:
                raise ValueError("Invalid paired CSV record") from exc
            decoded = "\n".join(fields)
            _require(not scan_blob(PAIRED_CSV, decoded.encode()) and not PRIVATE_TEXT.search(decoded),
                     "Decoded paired CSV public content scan failed")
            if total == len(raw):
                _require(tuple(fields) == PAIRED_CSV_HEADER, "Invalid paired CSV header")
                continue
            count += 1
            _require(count <= PAIRED_CSV_MAX_ROWS, "Paired CSV row bound exceeded")
            _require(len(fields) == len(PAIRED_CSV_HEADER) and all(len(v) <= 128 for v in fields),
                     "Invalid paired CSV field count/length")
            row = dict(zip(PAIRED_CSV_HEADER, fields))
            _require(row["source_id"] in expected, "Unknown paired CSV source ID")
            family, seed, coefficient = expected[row["source_id"]]
            ints = {}
            for key in ("seed", "turn", "layer", "position", "relative_position", "source_output_tokens"):
                _require(bool(integer.fullmatch(row[key])), "Invalid paired CSV integer: "+key)
                ints[key] = int(row[key])
            _require(row["family"] == family and ints["seed"] == seed
                     and numeric(row, "coefficient") == coefficient, "Paired CSV source fields mismatch")
            _require(row["history"] in ("zero", "steered") and ints["turn"] in (1, 2)
                     and ints["layer"] in layers and row["transport"] in transports and row["group"] in groups,
                     "Invalid paired CSV enum")
            relative, position, length = ints["relative_position"], ints["position"], ints["source_output_tokens"]
            _require(1 <= length <= 128 and 0 <= relative <= min(4, length)
                     and relative <= position < 131072, "Invalid paired CSV position/output length")
            _require(row["phase"] == ("last_prompt" if relative == 0 else "generated")
                     and row["terminal_observation_only"] == str(relative > 0 and relative == length),
                     "Invalid paired CSV phase/terminal annotation")
            origin = (f"feature-30032-{seed}-+0.0-notebook-0.6-128" if row["history"] == "zero"
                      else row["source_id"])
            _require(row["originating_row_id"] == origin, "Invalid paired CSV originating row ID")
            for key in ("normalized_logit_delta", "linear_logit_delta"):
                numeric(row, key)
            for key in ("residual_delta_norm", "clean_residual_norm", "clean_transport_norm", "edited_transport_norm"):
                _require(numeric(row, key) >= 0, "Negative paired CSV norm")
            if ints["layer"] == 50:
                numeric(row, "static_linear_prediction")
                if row["all_lexicon_static_cosine"]:
                    _require(abs(numeric(row, "all_lexicon_static_cosine")) <= 1.000001,
                             "Invalid paired CSV cosine")
            else:
                _require(row["static_linear_prediction"] == row["all_lexicon_static_cosine"] == "",
                         "Unexpected later-layer static paired CSV prediction")
            key = (row["source_id"], row["history"], ints["turn"])
            first, output_length, mask = cases.get(key, (position-relative, length, 0))
            _require((first, output_length) == (position-relative, length), "Inconsistent paired CSV case metadata")
            # One bit per position/layer/transport/group bounds memory independently of file size.
            bit = 1 << (((relative*3+layers.index(ints["layer"]))*7+transports.index(row["transport"]))*7
                        + groups.index(row["group"]))
            _require(not mask & bit, "Duplicate paired CSV observation")
            cases[key] = (first, length, mask | bit)
    _require(len(cases) == 40*2*2 and all(mask == (1 << ((1+min(4, length))*3*7*7))-1
                                        for _, length, mask in cases.values()), "Incomplete paired CSV grid")


def _scan_public_file(name, path, plan=None):
    _require(not path_findings([name]), "Private or restricted publication path: "+name)
    if name == PAIRED_CSV:
        _require(path.stat().st_size <= PAIRED_CSV_MAX_BYTES, "Paired CSV exceeds 64 MiB size bound")
        _scan_paired_csv(path, plan)
        return
    _require(path.stat().st_size <= MAX_TEXT_BYTES, "Publication artifact exceeds size bound")
    if path.suffix.lower() in (".png", ".pdf"):
        raw = path.read_bytes()
        magic = b"\x89PNG\r\n\x1a\n" if path.suffix.lower() == ".png" else b"%PDF-"
        _require(raw.startswith(magic), "Invalid figure format: "+name)
        _require(not scan_blob(name, raw), "Figure public content scan failed: "+name)
        _require(not PRIVATE_TEXT.search(raw.decode("latin1")), "Private figure metadata: "+name)
    else:
        _scan_text(name, path)


def allowed(plan):
    result = set(ROOT_FILES)
    if plan.get("schema") == "berg_random_subset_public_v1":
        result.difference_update({"lens-metadata.json", "lens-replay-check.json", "static-directions.json",
                                  "analysis/curves.csv"})
        result.add("analysis/rates.csv")
    for row in plan["rows"]:
        _require(re.fullmatch(r"[A-Za-z0-9_.+-]+", row["id"]), "Unsafe row ID")
        result.add("rows/"+row["id"]+".json")
        if row["capture"]:
            result.add("rows/capture-"+row["id"]+".json")
    return result


def lifecycle(base, plan_hash, freeze, *, ensemble=False):
    base = Path(base)
    events = _ledger(base/"events.jsonl", plan_hash, freeze, [])
    by_id = {e["id"]: e for e in events}
    for key in ("created", "closed", "delete-response"):
        _require(key in by_id, "Missing verified lifecycle event: "+key)
    closed = by_id["closed"]["data"]
    _require(closed["get_status"] == 404 and closed["within_limits"], "Pod not verifiably closed within budget")
    _require(closed["pod_id"] == by_id["created"]["data"]["id"], "Wrong pod closure")
    prefix = "codex-berg-ensemble-20261001-" if ensemble else "codex-berg-source-20260930-"
    _require(by_id["created"]["data"]["name"].startswith(prefix), "Unowned pod namespace")
    receipt = _json(base/"final-retrieval.json")
    _require(any(e == receipt for e in events), "Final retrieval is not ledger-bound")
    _require(receipt["data"]["pod_id"] == closed["pod_id"], "Foreign retrieval")
    directory = Path(receipt["data"]["directory"])
    _require(directory.resolve().parent == (base/"retrievals").resolve(), "Unexpected retrieval location")
    files = _files(directory)
    expected = receipt["data"]["artifacts"]
    _require(set(files) == set(expected), "Changed retrieval inventory")
    for name, path in files.items():
        _require(protocol.sha(path) == expected[name], "Changed retrieved artifact: "+name)
    return directory, files, closed, receipt["data"]


def snapshot_lineage(base, final_hashes, plan_hash, freeze):
    events = _ledger(Path(base)/"events.jsonl", plan_hash, freeze, [])
    result = []
    for event in events:
        if not event["id"].startswith("retrieval:"):
            continue
        data = event["data"]
        raw = {n: h for n, h in data["artifacts"].items()
               if n.startswith("rows/") and n.endswith(".json")}
        inflight = {n: h for n, h in data["artifacts"].items()
                    if n.startswith("rows/") and n.endswith(".pending")}
        _require(all(final_hashes.get(n) == h for n, h in raw.items()),
                 "Previously retrieved raw scientific data changed or disappeared")
        result.append({"utc": data.get("utc"), "raw_rows": len(raw), "artifacts": raw,
                       "unpublished_inflight_files": inflight})
    return {"schema": "berg_source_snapshot_lineage_v1",
            "scope": "Projection of verified private retrieval ledger; raw rows match final bytes",
            "snapshots": result}


def build(base, plan_path, freeze, destination):
    plan_path, destination = Path(plan_path), Path(destination)
    _require(not destination.exists(), "Refuse to overwrite a release")
    _require(re.fullmatch(r"[0-9a-f]{40}", freeze), "Full freeze commit required")
    frozen = verify_freeze(plan_path, freeze)
    ensemble = frozen.get("schema") == "berg_random_subset_public_v1"
    study_protocol, study_analysis = protocol, analysis
    if ensemble:
        from experiments.berg_ensemble_replication import protocol as study_protocol, analysis as study_analysis
    plan = study_protocol.load_plan(plan_path)
    plan_hash = protocol.sha(plan_path)
    root, files, closure, receipt = lifecycle(base, plan_hash, freeze, ensemble=ensemble)
    lineage = snapshot_lineage(base, receipt["artifacts"], plan_hash, freeze)
    _require(set(files) <= allowed(plan), "Unexpected raw artifact; audit before allowlisting")
    _require(sum(p.stat().st_size for p in files.values()) <= 2*1024**3, "Raw release exceeds 2 GiB bound")
    for name, path in files.items():
        _scan_text(name, path, (Path(base).resolve(),))
    model = _json(root/"model-bf16-load-00002.json")
    _require(model["model_id"] == plan["model"]["id"]
             and model["model_revision"] == plan["model"]["revision"]
             and model["precision"] == plan["model"]["precision"] == "bf16"
             and model["sae_id"] == plan["sae"]["id"]
             and model["sae_revision"] == plan["sae"]["revision"]
             and model["sae_sha256"] == plan["sae"]["sha256"],
             "Loaded model/SAE does not match plan")
    done = _json(root/"DONE-all.json")
    _require(done == {"pass": True, "plan_sha256": plan_hash, "freeze_commit": freeze,
                     "rows": 1+len(plan["rows"])+sum(r["capture"] for r in plan["rows"])},
             "Completion does not match frozen inventory")
    report = study_analysis.audit(root, plan, partial=False)
    if not ensemble:
        report["capture_schedule"] = validate_capture_schedule(root,plan)
    verify_receipts(root, plan, freeze)
    report.update(plan_sha256=plan_hash, freeze_commit=freeze, receipts_verified=True)
    for name, path in files.items():
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        _require(protocol.sha(target) == receipt["artifacts"][name], "Copy mismatch")
    public_receipt = {"schema": "berg_ensemble_retrieval_v1" if ensemble else "berg_source_retrieval_v1", "freeze_commit": freeze,
                      "plan_sha256": plan_hash, "closure": closure, "artifacts": receipt["artifacts"],
                      "scope": "Projection of private verified lifecycle; paths and SSH material omitted"}
    (destination/"retrieval_and_cost.json").write_text(protocol.canonical(public_receipt)+"\n")
    (destination/"snapshot_lineage.json").write_text(protocol.canonical(lineage)+"\n")
    (destination/"PUBLICATION_AUDIT.json").write_text(protocol.canonical(report)+"\n")
    return report


def manifest(destination, plan_path, freeze):
    """Seal only after adding separately reviewed analysis and documentation."""
    destination, plan_path = Path(destination).resolve(), Path(plan_path).resolve()
    _require(not (destination/"RELEASE_MANIFEST.json").exists(), "Release already sealed")
    files = _files(destination)
    plan = verify_freeze(plan_path, freeze)
    verify_publication(destination, plan, protocol.sha(plan_path), freeze)
    _require(sum(p.stat().st_size for p in files.values()) <= 2*1024**3, "Release exceeds 2 GiB bound")
    for name, path in files.items():
        _scan_public_file(name, path, plan=plan)
    ensemble = plan.get("schema") == "berg_random_subset_public_v1"
    value = {"schema": "berg_ensemble_release_v1" if ensemble else "berg_source_release_v1", "freeze_commit": freeze,
             "plan_path": plan_path.relative_to(protocol.ROOT).as_posix(),
             "plan_sha256": protocol.sha(plan_path),
             "reporting_source_hashes": {p: protocol.sha(_repo_path(p)) for p in reporting_sources(ensemble)},
             "files": [{"path": name, "sha256": protocol.sha(path), "bytes": path.stat().st_size}
                       for name, path in files.items()]}
    encoded = protocol.canonical(value)+"\n"
    _require(not scan_blob("RELEASE_MANIFEST.json", encoded.encode()) and not PRIVATE_TEXT.search(encoded),
             "Manifest public content scan failed")
    with (destination/"RELEASE_MANIFEST.json").open("x") as handle:
        handle.write(encoded)
    return {"files": len(files), "bytes": sum(f["bytes"] for f in value["files"])}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--freeze", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(build(args.base, args.plan, args.freeze, args.out)))
