"""Offline publication candidates for the frozen mapping-scaled dose study.

Build into a new directory only. Raw evidence is copied byte-for-byte; frozen
analysis supplies completed inference. Checksums detect changes, not authorship:
retain the manifest digest and private controller receipts outside the release.
This sidecar neither authorizes publication nor contacts a provider.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import nullcontext
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import shutil
import statistics
import tempfile
import textwrap

from experiments.berg_dose_ladder import analysis, protocol
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc
from scripts.release_berg_source import _frozen_blob, _git
from scripts.release_sae_exposure import _files, _json, _relative, _require, _scan_text


SCHEMA = "mapping_scaled_release_v1"
PLAN_PATH = "data/berg_dose_ladder/plan_20261004/PLAN.json"
MODES = ("completed", "partial_technical_failure")
FIGURES = ("calibration", "quality", "main_contrasts", "delivery_coordinates")
ROOT_FILES = frozenset({
    "PLAN.json", "runtime.json", "receipts.jsonl", "pip-freeze.txt", "controller.log",
    "controller-exit.json", "controller-stopped.json", "controller-worker-reconciled.json",
    "WAITING-qualification.json", "WAITING-first-five.json", "APPROVE-qualification",
    "APPROVE-first-five", "DONE-all.json", "failed.json", "selection.json",
    "throughput.json", "audit.json", "analysis/summary.json",
})
GENERATED = frozenset({"provenance/PLAN.json", "provenance/source.json",
                       "provenance/controller.json", "REPORT.json", "FIGURE_DATA.json"})
FIGURE_FILES = frozenset(f"figures/{name}.{ext}" for name in FIGURES for ext in ("png", "pdf"))
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write((protocol.canonical(value) + "\n").encode())


def _canonical_json(path):
    value = _json(path)
    _require(path.read_bytes() == (protocol.canonical(value) + "\n").encode(),
             "Noncanonical JSON: " + path.name)
    return value


def _verify_sources(plan_bytes, reference):
    """Verify local immutable Git blobs and the code actually doing the audit."""
    freeze, name = reference["freeze_commit"], reference["plan_path"]
    _relative(name)
    _require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "Full freeze commit required")
    _require(_git("cat-file", "-t", freeze).strip() == b"commit", "Freeze is not a commit")
    _require(_frozen_blob(freeze, name) == plan_bytes, "Plan differs from frozen Git blob")
    _require(reference["plan_sha256"] == _digest(plan_bytes), "Plan reference hash mismatch")
    import json
    plan = json.loads(plan_bytes)
    _require(plan_bytes == (protocol.canonical(plan) + "\n").encode(), "Noncanonical source plan")
    _require(plan.get("schema") == "mapping_scaled_dose_v1" and
             set(plan["source_hashes"]) == set(protocol.source_paths()), "Wrong study/source closure")
    for section in ("source_hashes", "input_hashes"):
        _require(isinstance(plan.get(section), dict) and plan[section], "Missing frozen closure")
        _require(reference[section] == plan[section], "Source reference differs from plan")
        for path, digest in plan[section].items():
            _relative(path)
            _require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "Invalid source digest")
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
    _require(sum(p.stat().st_size for p in files.values()) <= MAX_TOTAL_BYTES, "Oversized release")
    for name, path in files.items():
        _require(name in allowed or re.fullmatch(r"model-bf16-load-[0-9]{5}\.json", name),
                 "Unapproved raw artifact: " + name)
        _scan_text(name, path)
        if name.endswith(".pending"):
            _scan_text(name + ".json", path)
        if name.startswith("rows/") and name.endswith(".json"):
            _require(_json(path)["id"] == path.stem, "Row filename differs from its ID")
    return files


def _read_ledger(path, plan_hash, freeze, *, row_ids=()):
    _require(path.is_file() and not path.is_symlink(), "Missing regular event ledger")
    ledger = object.__new__(EventLedger)
    ledger.plan, ledger.freeze, ledger.ids, ledger.anchor = plan_hash, freeze, frozenset(row_ids), None
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        return ledger._read(fd)
    finally:
        os.close(fd)


def _startup_ledger(root, plan, reference):
    """Allow only the frozen runner's pre-initialization ledger prefix."""
    _require(not (root / "runtime.json").exists(), "Startup ledger exception requires absent runtime.json")
    ids = ["qualification-live"] + [row["id"] for row in plan["rows"]]
    events = _read_ledger(root / "receipts.jsonl", reference["plan_sha256"],
                          reference["freeze_commit"], row_ids=ids)
    # _read validates the canonical chain and exact first binding/row inventory.
    _require(len(events) in (1, 2), "Startup ledger must contain only binding and optional runtime event")
    if len(events) == 2:
        event, data = events[1], events[1]["data"]
        _require(event["id"] == "runtime" and set(data) == {"kind", "schema", "deadline_utc"} and
                 data["kind"] == "runtime" and data["schema"] == plan["schema"] and
                 isinstance(data["deadline_utc"], str), "Invalid pre-initialization runtime event")
        _utc(data["deadline_utc"])


def _receipt(path, reference):
    _require(path.is_file() and not path.is_symlink(), "Invalid final retrieval receipt")
    event = _canonical_json(path)
    _require(set(event) == {"id", "seq", "data", "plan_sha256", "freeze_commit",
                            "previous_sha256", "sha256"}, "Malformed retrieval receipt")
    body = {k: v for k, v in event.items() if k != "sha256"}
    _require(event["sha256"] == _digest(protocol.canonical(body).encode()), "Receipt hash mismatch")
    _require(event["plan_sha256"] == reference["plan_sha256"] and
             event["freeze_commit"] == reference["freeze_commit"] and
             event["id"].startswith("retrieval:") and type(event["seq"]) is int,
             "Retrieval plan/freeze/event mismatch")
    return event


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
                            "receipt_sha256": protocol.sha(receipt_path), "artifacts": artifacts,
                            "no_worker_dispatched": no_worker}
    if ledger_path is None:
        return public
    events = _read_ledger(Path(ledger_path), reference["plan_sha256"], reference["freeze_commit"])
    _require(event in events, "Final receipt is not bound to controller ledger")
    by_id = {e["id"]: e for e in events}
    _require(not no_worker or "worker-intent" not in by_id, "No-worker receipt conflicts with dispatch intent")
    created = by_id.get("created")
    config = by_id.get("controller:config", {}).get("data", {})
    _require(created is not None and created["seq"] < event["seq"] and
             created["data"].get("id") == event["data"].get("pod_id") and
             created["data"].get("name", "").startswith("codex-dose-ladder-20261004-") and
             config.get("namespace") == "dose-ladder-controller" and config.get("kind") == "main",
             "Foreign or non-main controller retrieval")
    public["retrieval"]["status"] = "externally_bound_controller_ledger"
    closed = next((e for e in events if e["id"] == "closed"), None)
    lifecycle = {"status": "unresolved", "cost": None, "deletion_verified": False,
                 "ledger_sha256": protocol.sha(ledger_path)}
    if closed is not None:
        data = closed["data"]
        _require(closed["seq"] > event["seq"] and data["pod_id"] == event["data"]["pod_id"],
                 "Deletion does not follow matching retrieval")
        intent = by_id.get("delete-intent")
        _require(intent is not None and event["seq"] < intent["seq"] < closed["seq"] and
                 intent["data"].get("pod_id") == data["pod_id"], "Missing matching delete intent")
        response = by_id.get("delete-response")
        if response is not None:
            _require(intent["seq"] < response["seq"] < closed["seq"] and
                     response["data"].get("pod_id") == data["pod_id"] and
                     type(response["data"].get("status")) is int, "Foreign deletion response")
        for key in ("elapsed_seconds", "compute_upper_bound_usd", "cumulative_upper_bound_usd"):
            _require(isinstance(data[key], str) and Decimal(data[key]).is_finite() and
                     Decimal(data[key]) >= 0, "Invalid exact controller cost/time")
        _require(type(data["get_status"]) is int and isinstance(data["inventory_ids"], list) and
                 type(data["within_limits"]) is bool, "Malformed closure status")
        deleted = data["get_status"] == 404 and data["pod_id"] not in data["inventory_ids"]
        lifecycle.update(status="closed" if deleted else "unresolved", deletion_verified=deleted,
                         closed_event_sha256=closed["sha256"],
                         cost={k: data[k] for k in ("elapsed_seconds", "compute_upper_bound_usd",
                               "cumulative_upper_bound_usd", "within_limits")},
                         cost_basis="controller_upper_bounds_not_provider_invoice",
                         delete_response_status=response["data"]["status"] if response else None,
                         direct_get_status=data["get_status"],
                         full_inventory_sha256=_digest(protocol.canonical(data["inventory_ids"]).encode()))
    public["lifecycle"] = lifecycle
    return public


def _audit(root, plan, reference, mode, *, no_worker=False):
    _require(mode in MODES, "Explicit completed or partial_technical_failure mode required")
    _require(not no_worker or mode == "partial_technical_failure" and not _files(root),
             "No-worker release must be empty and incomplete")
    if (root / "PLAN.json").exists():
        _require(protocol.sha(root / "PLAN.json") == reference["plan_sha256"], "Raw plan hash mismatch")
    if (root / "runtime.json").exists():
        runtime = _json(root / "runtime.json")
        _require(runtime["plan_sha256"] == reference["plan_sha256"] and
                 runtime["freeze_commit"] == reference["freeze_commit"], "Runtime freeze mismatch")
    rows = analysis.load_rows(root)
    seen = {r["id"] for r in rows}
    _require(len(seen) == len(rows), "Duplicate scientific rows")
    receipts = analysis.receipt_audit(root, plan, seen, settled=False)
    if receipts["state"] == "awaiting_runner":
        _require(not any((root / p).exists() for p in ("selection.json", "audit.json", "throughput.json",
                     "WAITING-qualification.json", "WAITING-first-five.json")) and not rows and
                 not any((root / "rows").glob("*")),
                 "Incomplete scientific bindings are not an empty startup")
        if (root / "receipts.jsonl").exists():
            _require(mode == "partial_technical_failure", "Startup ledger is not completed collection")
            _startup_ledger(root, plan, reference)
    done = _json(root / "DONE-all.json") if (root / "DONE-all.json").exists() else None
    if mode == "completed":
        result = analysis.audit(root, plan, partial=False, settled=True)
        _require(done is not None and done.get("pass") is True and
                 done.get("plan_sha256") == reference["plan_sha256"] and
                 done.get("freeze_commit") == reference["freeze_commit"] and
                 done.get("generations") == result["generations"] and
                 done.get("selected_dose") == result["selected_dose"] and
                 done.get("main_run") is (result["selected_dose"] is not None), "Invalid completion marker")
        _require(not (root / "failed.json").exists() and not list((root / "rows").glob("*.pending")),
                 "Completed release contains failure/pending evidence")
        scientific = {"status": "strict_completed", "audit": result}
    else:
        _require(done is None, "Completion marker conflicts with technical-failure mode")
        _require(no_worker or (root / "failed.json").exists() or (root / "controller-stopped.json").exists() or
                 ((root / "controller-exit.json").exists() and
                  _json(root / "controller-exit.json").get("exit_code") not in (None, 0)),
                 "Partial release requires terminal failure/stop evidence")
        _require(not (root / "analysis/summary.json").exists(), "Partial release has completed inference")
        if (root / "failed.json").exists():
            _require(_json(root / "failed.json").get("plan_sha256") == reference["plan_sha256"],
                     "Failure plan binding mismatch")
        if receipts["state"] == "awaiting_runner":
            scientific = {"status": "not_certified", "reason": "Runner initialization incomplete; "
                          "startup ledger bindings do not certify scientific results"}
        else:
            try:
                result = analysis.audit(root, plan, partial=True, settled=True)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                scientific = {"status": "not_certified", "error_type": type(exc).__name__,
                              "reason": str(exc)}
            else:
                scientific = {"status": "strict_partial_only", "audit": result}
    main_rows = sum(r.get("spec", {}).get("phase") == "main" for r in rows)
    selected = scientific.get("audit", {}).get("selected_dose")
    return {"schema": SCHEMA, "mode": mode, "scientific": scientific, "receipts": receipts,
            "no_worker_dispatched": no_worker,
            "main_status": ("completed" if mode == "completed" and selected is not None else
                            "incomplete" if main_rows else "not_run"),
            "observed_main_rows": main_rows, "observed_rows": len(rows),
            "pending_files": sorted(p.name for p in (root / "rows").glob("*.pending")),
            "claims": "Model-judge labels, not validated experience reports. Native-coordinate and "
                      "delivery diagnostics are descriptive, not semantic suppression or consciousness evidence."}


def _summary(root, mode):
    if mode != "completed":
        return None
    # Never invoke the frozen writer in the retrieved directory.
    with tempfile.TemporaryDirectory(prefix="mapping-scaled-analysis-") as temporary:
        summary = analysis.analyze(root, Path(temporary))
        original = root / "analysis/summary.json"
        if original.exists():
            _require(original.read_bytes() == (Path(temporary) / "summary.json").read_bytes(),
                     "Saved summary differs from frozen analysis")
        return summary


def _figure_data(root, report, summary):
    certified = report["scientific"]["status"] in {"strict_completed", "strict_partial_only"}
    rows = [r for r in analysis.load_rows(root) if "spec" in r] if certified else []
    groups = defaultdict(list)
    for row in rows:
        spec = row["spec"]
        if spec["phase"] == "calibration":
            groups[spec["dose"], spec["family"], spec["coefficient"]].append(row)
    calibration, quality, delivery = [], [], []
    for (dose, family, sign), group in sorted(groups.items()):
        base = {"dose": dose, "family": family, "sign": sign, "n": len(group)}
        for judge in ("notebook", "paper"):
            labels = [r["judges"][judge]["label"] for r in group]
            calibration.append({**base, "judge": judge, "positive": labels.count(1),
                                "missing": labels.count(None)})
        turns = [t for r in group for t in r["turns"]]
        nll = [c["clean_nll"] for r in group for c in r["coherence"] if c["clean_nll"] is not None]
        quality.append({**base, "turns": len(turns), "cap_hits": sum(t["cap_hit"] for t in turns),
                        "clean_nll_n": len(nll), "clean_nll_mean": statistics.mean(nll) if nll else None,
                        "flagged": (sum(bool(analysis.flags(r, summary["selection"]["zero_nll_medians"]))
                                        for r in group) if summary else None)})
    for row in rows:
        requested, realized, changes = [], [], []
        for turn in row["turns"]:
            t = turn["telemetry"]
            for i, position in enumerate(t["position_metadata"]):
                if not position["special"] and not position["terminal_observation_only"]:
                    requested.append(t["delivery"]["requested_norm"][i])
                    realized.append(t["delivery"]["realized_norm"][i])
            target_indices = [t["readout_feature_ids"].index(fid) for fid in protocol.TARGET_IDS]
            for record in t["reencoding"]:
                changes.extend(record["after"][i] - record["before"][i] for i in target_indices)
        delivery.append({"id": row["id"], "phase": row["spec"]["phase"],
                         "family": row["spec"]["family"],
                         "signed_dose": row["spec"]["dose"] * row["spec"]["coefficient"],
                         "requested_norm": statistics.mean(requested) if requested else None,
                         "realized_norm": statistics.mean(realized) if realized else None,
                         "target_coordinate_delta": statistics.mean(changes) if changes else None})
    return {"calibration": calibration, "quality": quality, "delivery": delivery,
            "main_status": report["main_status"], "contrasts": summary["results"] if summary else {},
            "descriptive_rows_certified": certified,
            "notes": {"calibration": "Positive fraction among observed nonmissing labels; both rubrics. "
                      "Control panels pooled descriptively. Missing and unrun cells are not zero effects.",
                      "quality": "Calibration only; both turns pooled. Cap rate and mean clean NLL; "
                      "frozen quality flags are heuristics, not human coherence validation.",
                      "main": "Frozen missingness-aware primary bounds, not bootstrap intervals. "
                      "No held-out inference for incomplete runs.",
                      "delivery": "Per-trial means; norms exclude special and terminal-only positions. "
                      "Native readouts average the three target coordinates across recorded observations. "
                      "Descriptive only; not semantic suppression."}}


def _plots(data, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"target": "#007C83", "control": "#B64B42", "zero": "#505050"}

    def empty(ax, text="No certified observations"):
        ax.text(.5, .5, textwrap.fill(text, 38), ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])

    def finish(fig, name, note):
        fig.text(.02, .015, note, fontsize=8, va="bottom")
        fig.tight_layout(rect=(0, .12, 1, .96))
        for ext in ("png", "pdf"):
            fig.savefig(destination / f"{name}.{ext}", dpi=160,
                        metadata={"Creator": "mapping_scaled_release"})
        plt.close(fig)

    def curve(ax, cells, field):
        for family in ("target", "control"):
            selected = sorted((c for c in cells if c["family"] == family),
                              key=lambda c: c["sign"] * c["dose"])
            if not selected:
                continue
            by_x = {c["sign"] * c["dose"]: c for c in selected}
            xs = sorted(s * d for s in (-1, 1) for d in protocol.DOSES)
            ys = [field(by_x[x]) if x in by_x else float("nan") for x in xs]
            ax.plot(xs, ys, "o-" if family == "target" else "x--",
                    color=colors[family], label=family, markersize=4)
        zero = next((c for c in cells if c["family"] == "zero"), None)
        if zero is not None:
            ax.scatter([0], [field(zero)], color=colors["zero"], marker="s", label="true zero", s=30, zorder=5)
        if cells:
            ax.legend(fontsize=8)
            ax.set_xlabel("Signed mapping-scaled dose")
            ax.grid(alpha=.18)
        else:
            empty(ax)

    destination.mkdir()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    for ax, judge in zip(axes, ("notebook", "paper")):
        cells = [c for c in data["calibration"] if c["judge"] == judge]
        curve(ax, cells, lambda c: c["positive"] / (c["n"] - c["missing"])
              if c["n"] > c["missing"] else float("nan"))
        ax.set_title(f"{judge} rubric: calibration")
        ax.set_ylabel("Positive / nonmissing labels")
        ax.set_ylim(-.04, 1.04)
        if cells:
            ax.text(.02, .98, f"Observed n={sum(c['n'] for c in cells)}; missing={sum(c['missing'] for c in cells)}",
                    va="top", transform=ax.transAxes, fontsize=8)
    finish(fig, "calibration", "Observed labels only; pooled controls; no selected-label dose optimization.\n"
           "Absent dose cells are gaps, not zero effects. Cell counts are in FIGURE_DATA.json.")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6))
    for ax, title, metric in zip(axes, ("Cap hits / turns", "Mean clean NLL", "Frozen quality flags / trials"),
                                 (lambda c: c["cap_hits"] / c["turns"],
                                  lambda c: c["clean_nll_mean"] if c["clean_nll_mean"] is not None else float("nan"),
                                  lambda c: c["flagged"] / c["n"] if c["flagged"] is not None else float("nan"))):
        if title.startswith("Frozen") and not any(c["flagged"] is not None for c in data["quality"]):
            empty(ax, "Not available: no completed calibration analysis")
        else:
            curve(ax, data["quality"], metric)
        ax.set_title(title)
    finish(fig, "quality", "Calibration observations; both turns pooled. NLL missingness is retained in FIGURE_DATA.json.\n"
           "Quality flags follow frozen analysis; they are not validated human coherence judgments.")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    for ax, contrast in zip(axes, ("target", "specificity")):
        if data["main_status"] != "completed":
            empty(ax, "Main " + data["main_status"].replace("_", " ") + ": no held-out inference")
        else:
            for i, judge in enumerate(("notebook", "paper")):
                value = data["contrasts"][judge][contrast]
                lo, hi = value["bounds"]
                ax.plot([lo, hi], [i, i], color=colors["target"], linewidth=3)
                estimate = value.get("estimate_complete_pairs")
                if estimate is not None:
                    ax.scatter([estimate], [i], color=colors["control"], s=25)
            ax.set_yticks([0, 1], ["notebook", "paper"])
            ax.set_ylim(-.5, 1.5)
            ax.axvline(0, color="gray", linestyle=":")
            ax.set_xlabel("Frozen contrast bounds")
        ax.set_title(contrast.capitalize())
    finish(fig, "main_contrasts", "Primary missingness-aware bounds from frozen analysis, not bootstrap intervals.\n"
           "Dots, where available, are complete-pair estimates; missing branches are never zero effects.")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    for family, color in colors.items():
        records = [r for r in data["delivery"] if r["family"] == family]
        norms = [r for r in records if r["requested_norm"] is not None and r["realized_norm"] is not None]
        coords = [r for r in records if r["target_coordinate_delta"] is not None]
        if norms:
            axes[0].scatter([r["requested_norm"] for r in norms], [r["realized_norm"] for r in norms],
                            color=color, label=family, alpha=.5, s=12)
        if coords:
            axes[1].scatter([r["signed_dose"] for r in coords], [r["target_coordinate_delta"] for r in coords],
                            color=color, label=family, alpha=.4, s=12)
    for ax in axes:
        if ax.collections:
            ax.legend(fontsize=8)
            ax.grid(alpha=.18)
        else:
            empty(ax)
    axes[0].set(title="Delivered additive norm", xlabel="Requested norm (trial mean)", ylabel="Realized norm (trial mean)")
    axes[1].set(title="Native target coordinates", xlabel="Signed dose", ylabel="After - before (trial mean)")
    finish(fig, "delivery_coordinates", "All certified observed phases; per-trial means, pooled control panels.\n"
           "Delivery and coordinate readouts are descriptive only, not evidence of semantic suppression.")


def _entries(files):
    return [{"path": name, "bytes": path.stat().st_size, "sha256": protocol.sha(path)}
            for name, path in sorted(files.items())]


def build(source, destination, *, freeze, plan_path=None, mode="completed", controller_ledger=None):
    """Copy a terminal retrieval; a receipt input also checks its exact inventory."""
    source, destination = Path(source), Path(destination)
    _require(not destination.exists() and not destination.is_symlink(), "Destination must be new")
    plan_path = Path(plan_path) if plan_path else protocol.ROOT / PLAN_PATH
    _require(plan_path.is_file() and not plan_path.is_symlink(), "Invalid source plan")
    plan = _canonical_json(plan_path)
    reference = {"freeze_commit": freeze, "plan_path": plan_path.resolve().relative_to(protocol.ROOT.resolve()).as_posix(),
                 "plan_sha256": protocol.sha(plan_path),
                 "source_hashes": plan["source_hashes"], "input_hashes": plan["input_hashes"]}
    _verify_sources(plan_path.read_bytes(), reference)
    receipt_path = None if source.is_dir() else source
    if receipt_path is None:
        root = source
    else:
        payload = _receipt(receipt_path, reference)["data"]
        _require("directory" in payload or payload.get("no_worker_dispatched") is True,
                 "Retrieval receipt lacks directory or explicit no-worker evidence")
        root = Path(payload["directory"]) if "directory" in payload else None
    with (tempfile.TemporaryDirectory(prefix="mapping-scaled-empty-") if root is None else nullcontext(root)) as raw:
        return _build_from_root(Path(raw), destination, plan, plan_path.read_bytes(), reference,
                                mode, receipt_path, controller_ledger)


def _build_from_root(root, destination, plan, plan_bytes, reference, mode, receipt_path, controller_ledger):
    _require(not destination.resolve().is_relative_to(root.resolve()), "Destination must be outside retrieval")
    files = _raw_inventory(root, plan)
    artifacts = {name: protocol.sha(path) for name, path in files.items()}
    controller = _controller(receipt_path, controller_ledger, reference, artifacts)
    report = _audit(root, plan, reference, mode,
                    no_worker=controller["retrieval"].get("no_worker_dispatched", False))
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
    _write(destination / "MANIFEST.json", {"schema": SCHEMA, "mode": mode,
            "plan_sha256": reference["plan_sha256"], "freeze_commit": reference["freeze_commit"],
            "files": _entries(inventory)})
    return verify(destination, controller_receipt=receipt_path, controller_ledger=controller_ledger)


def verify(root, *, expected_manifest_sha256=None, controller_receipt=None, controller_ledger=None):
    """Read-only verification; optional external anchors authenticate provenance."""
    root = Path(root)
    files = _files(root)
    _require("MANIFEST.json" in files, "Missing manifest")
    manifest_path = files.pop("MANIFEST.json")
    digest = protocol.sha(manifest_path)
    if expected_manifest_sha256 is not None:
        _require(digest == expected_manifest_sha256, "External manifest digest mismatch")
    manifest = _canonical_json(manifest_path)
    _require(set(manifest) == {"schema", "mode", "plan_sha256", "freeze_commit", "files"} and
             manifest["schema"] == SCHEMA and manifest["mode"] in MODES, "Manifest schema mismatch")
    entries = manifest["files"]
    _require(isinstance(entries, list), "Manifest inventory must be a list")
    for entry in entries:
        _require(isinstance(entry, dict) and set(entry) == {"path", "bytes", "sha256"}, "Invalid manifest entry")
        _relative(entry["path"])
        _require(type(entry["bytes"]) is int and entry["bytes"] >= 0 and
                 isinstance(entry["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]),
                 "Invalid manifest byte count/digest")
    _require(entries == _entries(files), "Manifest inventory/bytes/hash mismatch")
    reference = _canonical_json(root / "provenance/source.json")
    _require(set(reference) == {"freeze_commit", "plan_path", "plan_sha256", "source_hashes", "input_hashes"},
             "Invalid source reference")
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
    _require(_canonical_json(root / "FIGURE_DATA.json") == _figure_data(root / "raw", report, summary),
             "Figure data differs from raw evidence")
    artifacts = {name: protocol.sha(path) for name, path in raw.items()}
    if controller["retrieval"]["status"] != "not_provided":
        _require(controller["retrieval"]["artifacts"] == artifacts, "Public retrieval inventory mismatch")
    externally_bound = controller_receipt is not None
    _require(controller_ledger is None or externally_bound, "External ledger needs final receipt")
    if externally_bound:
        _require(controller == _controller(controller_receipt, controller_ledger, reference, artifacts),
                 "Public lifecycle differs from external controller evidence")
    return {"pass": True, "mode": manifest["mode"], "main_status": report["main_status"],
            "manifest_sha256": digest, "external_manifest_bound": expected_manifest_sha256 is not None,
            "external_controller_bound": externally_bound,
            "lifecycle_verified_this_check": externally_bound and controller_ledger is not None}


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
