"""Offline, additive export of the fixed-main continuation and immutable calibration.

No collection, lifecycle actions, or edits to either frozen journal. Build into
a new directory from the final retrieval receipt; verify is read-only.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import nullcontext
from decimal import Decimal
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import tempfile

from experiments import mapping_exposure_release as prior
from experiments.berg_dose_exposure_continuation import analysis, protocol as p
from experiments.berg_dose_ladder import inference

base = prior.base
_require, _json, _files = prior._require, prior._json, prior._files
_write, _entries, _canonical = prior._write, prior._entries, prior._canonical_json
SCHEMA = "dose_main_release_v1"
FREEZE = "686efa2491a2334fcd2aff835627b24346d1dbb4"
JUDGES = {"notebook": "Second rubric", "paper": "Paper rubric"}
FIGURES = ("main_contrasts", "main_rates", "calibration_rates", "calibration_quality", "main_quality")
FIGURE_FILES = {f"figures/{name}.{ext}" for name in FIGURES for ext in ("png", "pdf")}
PORTABILITY_FILES = {"analysis/summary.json", "analysis/replay-summary.json", "analysis/portability.json"}
PORTABILITY_PATHS = (
    "$.results.notebook.target.bounds[1]",
    "$.results.notebook.target.event_probability_bounds.positive.upper",
    "$.results.notebook.target.upper",
    "$.results.paper.specificity.target.event_probability_bounds.positive.lower",
    "$.results.paper.target.bounds[0]",
    "$.results.paper.target.event_probability_bounds.negative.upper",
    "$.results.paper.target.event_probability_bounds.positive.lower",
    "$.results.paper.target.lower",
)
OBSERVED_WORKER_SHA = "53ec7ecb8d9cfa4f74098fd7bf6851043cd2ee869dedca6741306108ba331985"
OBSERVED_REPLAY_SHA = "86eff987cf9bc791b2b1f83bef3ef36dd65d0340adcc9f3c3b17cc2ec9b262c1"
ORIGINAL_REPORTER = "97c547d6f338fe085f0a1052ef7c8609f3c74ac9"
GENERATED = {"provenance/PLAN.json", "provenance/source.json", "provenance/controller.json",
             "REPORT.json", "FIGURE_DATA.json", "RESULTS.md", "values.tex"}
GROUPS = ("zero", "target", "control-1", "control-2", "control-3")
COLORS = {"zero": "#555555", "target": "#007C83", "control-1": "#B64B42",
          "control-2": "#5B6CAA", "control-3": "#967128"}
FIGURE_CAPTIONS = {
    "main_contrasts": "Fixed-dose paired contrasts. Dots are complete-pair estimates; lines are individual "
        "95% conservative paired-discordance CP bounds with worst-case missing labels. Target n=96 paired blocks; "
        "each fixed control panel n=32. The last row subtracts the equal mean of the three control gaps. "
        "Dashed +0.30 is the target threshold only. Control-panel comparisons are descriptive; intervals are not "
        "simultaneous across contrasts or rubrics. Quality status and frozen verdicts are reported separately.",
    "main_rates": "Fixed-dose label rates. Dots are positive/nonmissing labels; lines are missingness-aware "
        "marginal 95% CP limits. Negative (-) and positive (+) denote edit signs. The same 96 blocks supply "
        "the five arms, so cells are not independent samples; pairing enters the contrast analysis.",
    "calibration_rates": "Original calibration label rates. Dots are positive/nonmissing labels; whiskers are "
        "missingness-aware marginal 95% CP limits. These 204 original trials are separate from the 480 main trials. "
        "Target n=12 per dose/sign cell; each fixed control panel n=4. Dose 0.25 was quality-selected, not "
        "label-optimized. The original throughput FAIL is preserved unchanged.",
    "calibration_quality": "Original calibration quality diagnostics. Frozen heuristic flags are not human "
        "coherence validation; NLL pools both turns. Induction caps are exposure metadata; final caps remain "
        "quality failures. Fixed control panels remain separate. These are observed-sample summaries, not "
        "population estimates; no uncertainty calculation was frozen for these diagnostics.",
    "main_quality": "Fixed-dose main quality diagnostics, using only retrieved, scientifically auditable rows; "
        "the report states whether the main sample is complete. Frozen heuristic flags are not human coherence "
        "validation; NLL pools both turns. Induction caps are exposure metadata; final caps remain quality failures. "
        "Fixed control panels remain separate. These are observed-sample summaries, not population estimates; "
        "no uncertainty calculation was frozen for these diagnostics.",
}


def _verify_sources(plan_bytes, reference):
    _require(reference["freeze_commit"] == FREEZE and reference["plan_path"] == p.PLAN,
             "Wrong fixed-main freeze or plan")
    _require(prior._frozen_blob(FREEZE, p.PLAN) == plan_bytes
             and prior._digest(plan_bytes) == reference["plan_sha256"], "Plan differs from frozen blob")
    plan = json.loads(plan_bytes)
    _require(plan_bytes == (p.canonical(plan) + "\n").encode()
             and plan == p.build_plan(), "Continuation design/source/prefix drift")
    for section in ("source_hashes", "input_hashes"):
        _require(reference[section] == plan[section], "Source reference mismatch")
        for name, digest in plan[section].items():
            prior._relative(name)
            _require(prior._digest(prior._frozen_blob(FREEZE, name)) == digest,
                     "Frozen source/input mismatch: " + name)
    return plan


def _prefix_files():
    p.verify_prefix()
    root = p.ROOT / p.RELEASE
    files = _files(root)
    manifest = _canonical(files["MANIFEST.json"])
    _require(p.sha(files["MANIFEST.json"]) == p.MANIFEST_SHA
             and manifest["files"] == _entries({k: v for k, v in files.items() if k != "MANIFEST.json"}),
             "Immutable calibration manifest/inventory changed")
    return files


def _raw_inventory(root, plan):
    files = prior._raw_inventory(root, plan)
    _require("zero_screen.json" not in files, "No repeated calibration screen permitted")
    return files


def _controller(receipt_path, ledger_path, reference, artifacts):
    if receipt_path is None:
        _require(ledger_path is None, "Controller ledger requires retrieval receipt")
        return {"retrieval": {"status": "not_provided"},
                "lifecycle": {"status": "not_provided", "deletion_verified": False, "cost": None}}
    event = prior._receipt(Path(receipt_path), reference)
    _require(event["data"]["artifacts"] == artifacts, "Retrieval inventory/hash mismatch")
    no_worker = event["data"].get("no_worker_dispatched", False)
    _require(type(no_worker) is bool and (not no_worker or not artifacts), "Invalid empty retrieval")
    public = {"retrieval": {"status": "receipt_hash_verified", "event_sha256": event["sha256"],
        "receipt_sha256": p.sha(receipt_path), "artifacts": artifacts, "no_worker_dispatched": no_worker},
        "lifecycle": {"status": "unresolved", "deletion_verified": False, "cost": None}}
    if ledger_path is None:
        return public
    events = prior._read_ledger(Path(ledger_path), reference["plan_sha256"], FREEZE)
    _require(event in events and not any(e["id"].startswith("retrieval:") and e["seq"] > event["seq"]
                                       for e in events), "Not the final controller retrieval")
    by_id = {e["id"]: e for e in events}
    intent, created = by_id["create-intent"], by_id["created"]
    creation, pod = intent["data"], created["data"]
    _require(by_id["controller:config"]["data"] == {"kind": "main",
        "namespace": "dose-exposure-continuation-controller", "plan_path": p.PLAN,
        "budget": p.BUDGET, "hard_seconds": p.MAIN_SECONDS}, "Foreign controller config")
    _require(intent["seq"] < created["seq"] < event["seq"]
        and pod["id"] == event["data"]["pod_id"] and pod["id"] not in creation["blocked"]
        and re.fullmatch(r"codex-dose-exposure-continuation-20261005-main-[0-9a-f]{12}", pod["name"])
        and creation["payload"]["name"] == pod["name"]
        and creation["plan_sha256"] == reference["plan_sha256"] and creation["freeze_commit"] == FREEZE,
        "Foreign owned-pod binding")
    _require(not no_worker or "worker-intent" not in by_id, "Empty retrieval conflicts with dispatch")
    carry, cheap = prior._number(creation["prior_total_usd"]), prior._number(creation["prior_new_usd"])
    rate = prior._number(creation["quote"]["hourly_rate_usd"]) + Decimal("0.10")
    _require(carry == Decimal(p.PRIOR_USD) and cheap == 0, "Changed carry or double-counted cheap qualification")
    _require(rate * p.MAIN_SECONDS / 3600 <= Decimal(p.NEW_CAP_USD)
             and carry + rate * p.MAIN_SECONDS / 3600 <= Decimal(p.TOTAL), "Unfunded full timer")
    start = prior._utc(creation["created_utc"])
    _require((prior._utc(creation["hard_deadline_utc"]) - start).total_seconds() == p.MAIN_SECONDS
             and (prior._utc(creation["deadline_utc"]) - start).total_seconds()
             == p.MAIN_SECONDS - p.RESERVE_SECONDS, "Changed timer or cleanup reserve")
    public["retrieval"]["status"] = "externally_bound_controller_ledger"
    lifecycle = public["lifecycle"]
    lifecycle.update(ledger_sha256=p.sha(ledger_path), budget=p.BUDGET)
    if "closed" not in by_id:
        return public
    closed, delete = by_id["closed"], by_id["delete-intent"]
    data = closed["data"]
    _require(event["seq"] < delete["seq"] < closed["seq"]
             and data["pod_id"] == delete["data"]["pod_id"] == pod["id"], "Invalid deletion order/ownership")
    recovered = data["retrieval_verified"]
    _require(type(recovered) is bool and recovered == delete["data"]["retrieval_verified"]
             and data["artifacts_may_be_unrecovered"] is (not recovered), "Contradictory recovery status")
    elapsed = prior._number(data["elapsed_seconds"])
    cost, total = prior._number(data["compute_upper_bound_usd"]), prior._number(data["cumulative_upper_bound_usd"])
    current_rate = max(rate, prior._number(str(delete["data"]["pod"]["cost"])) + Decimal("0.10"))
    _require(cost >= elapsed * current_rate / 3600 and total == carry + cost,
             "Cost omits elapsed time, storage or immutable carry")
    within = elapsed <= p.MAIN_SECONDS and cost <= Decimal(p.NEW_CAP_USD) and total <= Decimal(p.TOTAL)
    _require(type(data["within_limits"]) is bool and data["within_limits"] == within
             and type(data["get_status"]) is int and isinstance(data["inventory_ids"], list)
             and all(isinstance(item, str) for item in data["inventory_ids"]), "Invalid closure status")
    deleted = data["get_status"] == 404 and pod["id"] not in data["inventory_ids"]
    lifecycle.update(status="closed" if deleted else "unresolved", deletion_verified=deleted,
        owned_pod_id=pod["id"],
        retrieval_verified=recovered, artifacts_may_be_unrecovered=not recovered,
        closed_event_sha256=closed["sha256"], direct_get_status=data["get_status"], closed_utc=data["utc"],
        cost={**{k: data[k] for k in ("elapsed_seconds", "compute_upper_bound_usd", "cumulative_upper_bound_usd", "within_limits")},
              "prior_study_usd": str(carry), "new_cheap_usd": "0"},
        cost_basis="controller_upper_bounds_not_provider_invoice")
    return public


def _audit(root, plan, reference, mode, controller):
    _require(mode in prior.MODES, "Explicit terminal mode required")
    for name in ("PLAN.json", "runtime.json"):
        if (root / name).exists():
            value = _json(root / name)
            if name == "PLAN.json":
                _require(p.sha(root / name) == reference["plan_sha256"], "Raw plan drift")
            else:
                _require(value["plan_sha256"] == reference["plan_sha256"]
                         and value["freeze_commit"] == FREEZE, "Raw runtime drift")
    rows = analysis.science.load_rows(root)
    seen = {r["id"] for r in rows}
    _require(len(rows) == len(seen), "Duplicate raw row")
    receipts = analysis.science.receipt_audit(root, plan, seen, settled=False)
    if receipts["state"] == "awaiting_runner":
        _require(not rows and not any((root / "rows").glob("*")), "Rows without runtime binding")
        if (root / "receipts.jsonl").exists():
            base._startup_ledger(root, plan, reference)
    done = root / "DONE-all.json"
    if mode == "completed":
        lifecycle = controller["lifecycle"]
        _require(lifecycle["status"] == "closed" and lifecycle["deletion_verified"] is True
                 and lifecycle.get("retrieval_verified") is True, "Complete export needs verified retrieval and owned deletion")
        result = analysis.audit(root, plan, partial=False, settled=True)
        _require(result["generations"] == 480 and len(rows) == 481, "Require 480 main rows plus qualification")
        _require(done.exists() and _json(done) == {"schema": "dose_exposure_continuation_completion_v1",
            "pass": True, "plan_sha256": reference["plan_sha256"], "freeze_commit": FREEZE,
            "generations": 480, "calibration_carried": 204, "selected_dose": .25,
            "original_throughput_pass": False}, "Invalid completion marker")
        _require(not (root / "failed.json").exists() and not list((root / "rows").glob("*.pending")),
                 "Completion conflicts with failure/pending evidence")
        scientific = {"status": "strict_completed", "audit": result}
    else:
        _require(not done.exists() and not (root / "analysis/summary.json").exists(),
                 "Partial export cannot contain completed inference")
        stopped = any((root / name).exists() for name in ("failed.json", "controller-stopped.json"))
        stopped |= (root / "controller-exit.json").exists() and _json(root / "controller-exit.json").get("exit_code") not in (None, 0)
        _require(stopped or controller["retrieval"].get("no_worker_dispatched") is True
                 or controller["lifecycle"].get("artifacts_may_be_unrecovered") is True,
                 "Partial export requires terminal stop/failure evidence")
        if (root / "failed.json").exists():
            _require(_json(root / "failed.json")["plan_sha256"] == reference["plan_sha256"], "Failure binding mismatch")
        try:
            result = analysis.audit(root, plan, partial=True, settled=True)
            scientific = {"status": "strict_partial_only", "audit": result}
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            scientific = {"status": "not_certified", "error_type": type(exc).__name__}
        if receipts["state"] == "awaiting_runner":
            scientific = {"status": "not_certified", "reason": "Runner initialization incomplete"}
    observed = len(seen - {"qualification-live"})
    return {"schema": SCHEMA, "mode": mode, "scientific": scientific, "receipts": receipts,
        "observed_rows": len(rows), "observed_main_rows": observed, "planned_main_rows": 480,
        "calibration_rows_carried": 204, "calibration_manifest_sha256": p.MANIFEST_SHA,
        "original_throughput_pass": False, "selected_dose": .25,
        "main_status": "completed" if mode == "completed" else "incomplete" if observed or receipts["pending_dispatches"] else "not_run",
        "missing_main_artifacts": 480 - observed,
        "claims": "Model-judge labels, not validated experience reports or consciousness evidence. "
                  "Calibration and main journals remain separate; unrun trials are not negative labels."}


def _summary_value(raw):
    value = json.loads(raw)
    _require(raw == (p.canonical(value) + "\n").encode(), "Summary serialization differs")
    return value


def _thresholds(summary):
    return {judge: {"target_lower_ge_0.30": result["target"]["bounds"][0] >= .30,
                   "target_upper_lt_0.30": result["target"]["bounds"][1] < .30,
                   "specificity_lower_gt_zero": result["specificity"]["bounds"][0] > 0}
            for judge, result in summary["results"].items()}


def _compare_summaries(saved_bytes, replay_bytes):
    """Eight observed CP-bound leaves only; no general numerical tolerance."""
    saved, replay = map(_summary_value, (saved_bytes, replay_bytes))
    differences = []

    def compare(a, b, path):
        _require(type(a) is type(b), "Summary type drift: " + path)
        if isinstance(a, dict):
            _require(a.keys() == b.keys(), "Summary keys drift: " + path)
            for key in sorted(a):
                compare(a[key], b[key], path + "." + key)
            if {"bounds", "lower", "upper"} <= a.keys():
                _require(a["bounds"] == [a["lower"], a["upper"]]
                         and b["bounds"] == [b["lower"], b["upper"]], "Summary bound aliases differ: " + path)
        elif isinstance(a, list):
            _require(len(a) == len(b), "Summary length drift: " + path)
            for index, (left, right) in enumerate(zip(a, b)):
                compare(left, right, f"{path}[{index}]")
        elif type(a) is float:
            _require(math.isfinite(a) and math.isfinite(b), "Nonfinite summary: " + path)
            if a.hex() == b.hex():
                return
            _require(path in PORTABILITY_PATHS and a != b, "Unallowed summary drift: " + path)
            adjacent = math.nextafter(a, b)
            ulps = 1 if adjacent == b else 2 if math.nextafter(adjacent, b) == b else None
            _require(ulps is not None, "Summary exceeds 2 ULP: " + path)
            differences.append({"path": path, "saved": a, "replayed": b,
                                "absolute_error": abs(a-b), "ulps": ulps})
        else:
            _require(a == b, "Unallowed summary drift: " + path)

    compare(saved, replay, "$")
    decisions = _thresholds(saved)
    _require(decisions == _thresholds(replay), "Summary threshold decision changed")
    return {"saved_summary_sha256": prior._digest(saved_bytes),
            "replay_summary_sha256": prior._digest(replay_bytes),
            "exact_replay": "PASS" if saved_bytes == replay_bytes else "FAIL",
            "differences": differences, "maximum_absolute_error": max(
                (d["absolute_error"] for d in differences), default=0.0),
            "maximum_ulps": max((d["ulps"] for d in differences), default=0),
            "threshold_decisions": decisions, "threshold_decisions_unchanged": True,
            "portability_check": "PASS"}


def _portability_record(saved_bytes, replay_bytes):
    check = _compare_summaries(saved_bytes, replay_bytes)
    observed = check["saved_summary_sha256"] == OBSERVED_WORKER_SHA
    if observed:
        _require(check["replay_summary_sha256"] == OBSERVED_REPLAY_SHA,
                 "Original failed local replay snapshot required; supply portability_replay")
    return {"schema": "dose_summary_portability_v1", "policy": {
        "allowed_paths": list(PORTABILITY_PATHS), "maximum_ulps": 2,
        "finite_floats_only": True, "all_other_bytes_values_and_types": "exact",
        "threshold_decision_changes": "reject"},
        "scope": "Post-outcome reporting portability only; frozen inference, science, raw bytes, "
                 "estimates, counts, missingness, quality and verdicts unchanged. "
                 "Canonical analysis is the exact saved worker summary, not a recomputed replacement.",
        "original_exact_replay": {"status": check["exact_replay"],
            "failure": "Saved analysis differs from frozen inference" if check["exact_replay"] == "FAIL" else None,
            "reporter_commit": ORIGINAL_REPORTER if observed else None,
            "observed_public_failure": observed},
        "archived_check": check,
        "verification": "Recheck this archived snapshot/diff record exactly; independently compare each "
                        "host's fresh replay to the saved worker under the same policy. "
                        "Fresh differences need not equal archived differences; zero differences are allowed."}


def _summary(root, mode):
    if mode != "completed":
        return None, None, None
    saved = root / "analysis/summary.json"
    _require(saved.is_file(), "Complete export requires saved worker summary")
    saved_bytes = saved.read_bytes()
    with tempfile.TemporaryDirectory(prefix="dose-main-analysis-") as tmp:
        analysis.analyze(root, Path(tmp))
        replay_bytes = (Path(tmp) / "summary.json").read_bytes()
    check = _compare_summaries(saved_bytes, replay_bytes)
    return _summary_value(saved_bytes), replay_bytes, check


def _group(spec):
    return "control-" + str(spec["block"] % 3 + 1) if spec["family"] == "control" else spec["family"]


def _figure_data(root, calibration, plan, report, summary):
    old_rows = [r for r in analysis.science.load_rows(calibration / "raw") if "spec" in r]
    certified = report["scientific"]["status"] != "not_certified"
    main_rows = [r for r in analysis.science.load_rows(root) if "spec" in r] if certified else []
    groups = defaultdict(list)
    for row in old_rows + main_rows:
        spec = row["spec"]
        groups[spec["phase"], _group(spec), spec["dose"], spec["coefficient"]].append(row)
    cells = []
    for (phase, group, dose, sign), rows in sorted(groups.items()):
        cell = {"phase": phase, "group": group, "dose": dose, "sign": sign, "n": len(rows),
            "induction_caps": sum(r["turns"][0]["cap_hit"] for r in rows),
            "final_caps": sum(r["turns"][1]["cap_hit"] for r in rows),
            "quality_flagged": sum(bool(analysis.science.flags(r, plan["continuation"]["selection"]["zero_nll_medians"])) for r in rows)}
        nll = [c["clean_nll"] for r in rows for c in r["coherence"] if c["clean_nll"] is not None]
        cell["mean_clean_nll"] = statistics.mean(nll) if nll else None
        cell["labels"] = {}
        for judge in JUDGES:
            labels = [r["judges"][judge]["label"] for r in rows]
            yes, missing, n = labels.count(1), labels.count(None), len(labels)
            cell["labels"][judge] = {"positive": yes, "missing": missing, "n": n,
                "observed_rate": yes / (n-missing) if n > missing else None,
                "identification_bounds": [yes/n, (yes+missing)/n],
                "marginal_cp_bounds": [inference.cp_limits(yes, n, .025)[0],
                                       inference.cp_limits(yes+missing, n, .025)[1]]}
        cells.append(cell)
    contrasts = {}
    if summary:
        lookup = {(r["spec"]["block"], r["spec"]["family"], r["spec"]["coefficient"]): r for r in main_rows}
        for judge, result in summary["results"].items():
            panels = {}
            for panel in (1, 2, 3):
                labs = lambda sign: [lookup[i, "control", sign]["judges"][judge]["label"]
                                     for i in range(96) if i % 3 == panel-1]
                panels[str(panel)] = inference.paired_bounds(labs(-1), labs(1))
            contrasts[judge] = {"target": result["target"], "specificity": result["specificity"],
                                "control_panels": panels, "bootstrap": result["bootstrap"],
                                "main_quality_pass": result["main_quality_pass"], "verdict": result["verdict"]}
    return {"schema": SCHEMA, "main_status": report["main_status"], "cells": cells, "contrasts": contrasts,
        "primary_judge": "notebook", "display_names": JUDGES, "selected_dose": .25,
        "figure_captions": FIGURE_CAPTIONS,
        "calibration_status": "completed_in_original_run", "original_throughput_pass": False,
        "quality_rule": {"induction_cap_is_quality_failure": False, "final_cap_is_quality_failure": True},
        "notes": {"main": "96 paired blocks; each fixed control panel has 32. Primary paired-discordance CP bounds; "
                   "secondary block bootstrap retained, not used for decisions. Individual two-sided 95% intervals, "
                   "not joint coverage across contrasts/rubrics; control-panel comparisons are descriptive.",
                  "rates": "Observed nonmissing rates; missingness-aware marginal CP limits use all planned labels in complete cells. "
                   "Partial rows are descriptive only and are never a complete main sample.",
                  "calibration": "204 original trials, separate from 480 main trials. Dose selected by frozen quality, "
                   "not nonzero label values; original throughput failure remains failed.",
                  "quality": "Frozen heuristic flags, not human coherence validation. Induction caps are exposure metadata."}}


def _plots(data, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    destination.mkdir()

    style = {"font.size": 10, "axes.labelsize": 10, "axes.titlesize": 11,
             "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 9.5,
             "axes.spines.top": False, "axes.spines.right": False,
             "axes.edgecolor": "0.65", "axes.linewidth": .6,
             "pdf.fonttype": 42, "ps.fonttype": 42}
    markers = dict(zip(GROUPS, ("o", "o", "s", "^", "D")))

    def finish(fig, name):
        for ext in ("pdf", "png"):
            metadata = {"Creator": SCHEMA}
            if ext == "pdf":
                metadata.update(CreationDate=None, ModDate=None)
            fig.savefig(destination / f"{name}.{ext}", dpi=160, metadata=metadata)
        plt.close(fig)

    def empty(ax):
        ax.text(.5, .5, "Main " + data["main_status"].replace("_", " ") + "\nNo complete-main inference",
                ha="center", va="center", transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])

    def horizontal(ax, bounds, y, point, color):
        ax.hlines(y, *bounds, color=color, linewidth=1.2)
        ax.plot(bounds, [y, y], linestyle="none", marker="|", markersize=6,
                markeredgewidth=1.1, color=color)
        if point is not None:
            ax.plot(point, y, "o", markersize=4, markerfacecolor="white",
                    markeredgewidth=1.1, color=color, zorder=3)

    def legend(fig, ax):
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="outside lower center", frameon=False,
                       ncol=3, columnspacing=1.6, handlelength=2.4)

    def curves(ax, cells, field, interval=None):
        for group in GROUPS:
            records = sorted((c for c in cells if c["group"] == group), key=lambda c: c["dose"]*c["sign"])
            if records:
                doses = [c["dose"]*c["sign"] for c in records]
                if interval:
                    bounds = [interval(c) for c in records]
                    ax.vlines(doses, [b[0] for b in bounds], [b[1] for b in bounds],
                              color=COLORS[group], alpha=.75, lw=1)
                    for side in (0, 1):
                        ax.plot(doses, [b[side] for b in bounds], linestyle="none", marker="_",
                                markersize=6, markeredgewidth=1, color=COLORS[group])
                ax.plot(doses,
                        [field(c) if field(c) is not None else float("nan") for c in records],
                        marker=markers[group], linestyle="-" if group == "target" else "--",
                        color=COLORS[group], label=group.replace("-", " ").capitalize(),
                        markersize=4, markerfacecolor="white", markeredgewidth=1, linewidth=1)
        ax.set_xlabel("Signed mapping-scaled dose"); ax.grid(alpha=.15)

    with plt.rc_context(style):
        fig, axes = plt.subplots(2, 1, figsize=(6.8, 6.4), sharex=True, layout="constrained")
        labels = ("Target", "Control 1", "Control 2", "Control 3", "Target - mean\ncontrols")
        for ax, judge in zip(axes, JUDGES):
            result = data["contrasts"].get(judge)
            ax.set_title(JUDGES[judge] + (" (primary)" if judge == "notebook" else " (secondary)"), loc="left")
            if not result:
                empty(ax); continue
            values = [result["target"], *result["control_panels"].values(), result["specificity"]]
            for i, value in enumerate(values):
                horizontal(ax, value["bounds"], i, value["estimate_complete_pairs"], COLORS["target"])
            ax.set_yticks(range(5), labels); ax.set_ylim(4.65, -.65)
            ax.axvline(0, color="gray", ls=":", linewidth=.8)
            ax.axvline(.30, color="#B64B42", ls="--", alpha=.5, linewidth=.9)
            ax.set_xlabel("Paired difference in label rate")
            ax.tick_params(labelbottom=True)
            ax.grid(axis="x", alpha=.15)
        finish(fig, "main_contrasts")

        fig, axes = plt.subplots(2, 1, figsize=(6.8, 7.4), layout="constrained")
        for ax, judge in zip(axes, JUDGES):
            ax.set_title(JUDGES[judge], loc="left", pad=16)
            if data["main_status"] != "completed":
                empty(ax); continue
            cells = sorted((c for c in data["cells"] if c["phase"] == "main"),
                           key=lambda c: (GROUPS.index(c["group"]), c["sign"]))
            for i, c in enumerate(cells):
                value = c["labels"][judge]
                horizontal(ax, value["marginal_cp_bounds"], i, value["observed_rate"], COLORS[c["group"]])
                ax.text(1.04, i, f"{value['positive']}/{c['n']-value['missing']} ({value['missing']})",
                        transform=ax.get_yaxis_transform(), fontsize=9.5, va="center", clip_on=False)
            ax.text(1.04, 1.015, "Positive / read\n(missing)", transform=ax.transAxes,
                    fontsize=9.5, va="bottom", clip_on=False)
            ax.set_yticks(range(len(cells)), [c["group"].replace("-", " ").capitalize() +
                          {-1: " -", 1: " +", 0: ""}[c["sign"]] for c in cells])
            ax.set_ylim(len(cells)-.35, -.65)
            ax.set_xlim(-.03, 1.03); ax.set_xticks([0, .5, 1])
            ax.set_xlabel("Positive-label rate"); ax.grid(axis="x", alpha=.15)
        finish(fig, "main_rates")

        calibration = [c for c in data["cells"] if c["phase"] == "calibration"]
        fig, axes = plt.subplots(2, 1, figsize=(6.8, 6.8), layout="constrained")
        for ax, judge in zip(axes, JUDGES):
            curves(ax, calibration, lambda c: c["labels"][judge]["observed_rate"],
                   lambda c: c["labels"][judge]["marginal_cp_bounds"])
            ax.set_title(JUDGES[judge], loc="left")
            ax.set(ylabel="Positive-label rate", ylim=(-.04, 1.04))
        legend(fig, axes[0])
        finish(fig, "calibration_rates")
        metrics = (("Frozen flags / trials", lambda c: c["quality_flagged"]/c["n"]),
                   ("Induction caps / trials", lambda c: c["induction_caps"]/c["n"]),
                   ("Final caps / trials", lambda c: c["final_caps"]/c["n"]),
                   ("Mean clean NLL", lambda c: c["mean_clean_nll"]))
        for phase in ("calibration", "main"):
            fig, axes = plt.subplots(2, 2, figsize=(6.8, 6.2), layout="constrained")
            cells = [c for c in data["cells"] if c["phase"] == phase]
            for ax, (title, field) in zip(axes.flat, metrics):
                ax.set_title(title, loc="left", fontsize=10.5)
                if cells:
                    curves(ax, cells, field)
                    ax.set_ylim(bottom=0) if title == "Mean clean NLL" else ax.set_ylim(-.04, 1.04)
                else:
                    empty(ax)
            legend(fig, axes[0, 0])
            finish(fig, phase + "_quality")


def _text_products(report, data, summary, controller):
    values = {"Complete": int(summary is not None), "Trials": report["observed_main_rows"],
              "CalibrationTrials": 204, "SelectedDose": .25}
    lines = ["# Fixed-Main Continuation", "", f"Main: **{report['main_status']}**; {report['observed_main_rows']}/480 main rows; "
             "204 separate, immutable calibration trials. Selected dose: 0.25.", "",
             "The original throughput FAIL remains preserved. The two journals are not pooled.", ""]
    if summary:
        lines += ["| Rubric | Contrast | Complete-pair estimate | Conservative 95% interval | Missing pairs |",
                  "|---|---|---:|---|---:|"]
        verdicts = []
        for judge, result in data["contrasts"].items():
            prefix = "Second" if judge == "notebook" else "Paper"
            values[prefix + "QualityPass"] = int(result["main_quality_pass"])
            for key, value in [("Target", result["target"]), *[("Control" + k, v) for k, v in result["control_panels"].items()],
                               ("Specificity", result["specificity"])]:
                point = value["estimate_complete_pairs"]
                display = "NA" if point is None else f"{point:.3f}"
                lo, hi = value["bounds"]
                missing = value.get("missing_pairs", "see component panels")
                lines.append(f"| {JUDGES[judge]} | {key} | {display} | [{lo:.3f}, {hi:.3f}] | {missing} |")
                values.update({prefix + key + "Estimate": display, prefix + key + "Low": f"{lo:.3f}",
                               prefix + key + "High": f"{hi:.3f}"})
            verdicts.append(JUDGES[judge] + " frozen verdict: `" + result["verdict"] + "`.")
        lines += ["", *verdicts, ""]
        for cell in data["cells"]:
            if cell["phase"] != "main":
                continue
            stem = cell["group"].title().replace("-", "") + {-1:"Negative", 0:"", 1:"Positive"}[cell["sign"]]
            values[stem + "N"] = cell["n"]
            values[stem + "QualityFlagged"] = cell["quality_flagged"]
            for judge, labels in cell["labels"].items():
                stem_j = ("Second" if judge == "notebook" else "Paper") + stem
                values[stem_j + "Yes"] = labels["positive"]
                values[stem_j + "Missing"] = labels["missing"]
    else:
        lines += ["No complete-main estimates, intervals, or scientific verdict. Missing artifacts are not negative labels.", ""]
    lifecycle = controller["lifecycle"]
    lines += ["Lifecycle: " + lifecycle["status"] + "."]
    if lifecycle.get("cost"):
        cost = lifecycle["cost"]
        lines += [f"New compute upper bound: ${cost['compute_upper_bound_usd']}; carried prior bound: ${cost['prior_study_usd']}; "
                  f"cumulative: ${cost['cumulative_upper_bound_usd']}. Controller upper bounds, not provider invoices."]
    lines += ["", "Second rubric is the frozen notebook-primary endpoint; Paper rubric is secondary. "
              "Primary intervals use paired blocks and worst-case missing labels. The three control panels are fixed, "
              "with 32 blocks each; their displayed intervals are descriptive, not simultaneous. "
              "Calibration quality and main quality are separate. Labels are not ground truth or consciousness evidence."]
    lines += ["", "## Figure Captions", ""]
    for name, caption in data["figure_captions"].items():
        lines += [f"**{name}.** {caption}", ""]
    tex = "% Generated by dose_main_release; descriptive reporting, not new inference.\n"
    for key, value in sorted(values.items()):
        for digit, word in (("1", "One"), ("2", "Two"), ("3", "Three")):
            key = key.replace(digit, word)
        tex += "\\newcommand{\\DoseMain" + key + "}{" + str(value) + "}\n"
    return ("\n".join(lines) + "\n").encode(), tex.encode()


def _reporting_hashes():
    names = ("experiments/dose_main_release.py", "tests/test_dose_main_release.py")
    return {name: p.sha(p.ROOT / name) for name in names}


def build(source, destination, *, freeze=FREEZE, plan_path=None, mode="completed", controller_ledger=None,
          portability_replay=None):
    source, destination = Path(source), Path(destination)
    _require(not destination.exists() and not destination.is_symlink(), "Destination must be new")
    plan_path = Path(plan_path) if plan_path else p.ROOT / p.PLAN
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    reference = {"freeze_commit": freeze, "plan_path": p.PLAN, "plan_sha256": prior._digest(plan_bytes),
                 "source_hashes": plan["source_hashes"], "input_hashes": plan["input_hashes"]}
    plan = _verify_sources(plan_bytes, reference)
    prefix = _prefix_files()
    receipt = None if source.is_dir() else source
    payload = prior._receipt(receipt, reference)["data"] if receipt else {}
    root = Path(payload["directory"]) if "directory" in payload else source if receipt is None else None
    _require(root is not None or payload.get("no_worker_dispatched") is True, "Receipt lacks retrieval directory")
    with (tempfile.TemporaryDirectory(prefix="dose-main-empty-") if root is None else nullcontext(root)) as raw:
        root = Path(raw)
        _require(not destination.resolve().is_relative_to(root.resolve()), "Destination cannot be inside retrieval")
        raw_files = _raw_inventory(root, plan)
        raw_hashes = {n: p.sha(f) for n, f in raw_files.items()}
        controller = _controller(receipt, controller_ledger, reference, raw_hashes)
        report = _audit(root, plan, reference, mode, controller)
        summary, replay_bytes, _ = _summary(root, mode)
        portability = None
        if summary:
            saved_bytes = (root / "analysis/summary.json").read_bytes()
            if portability_replay is not None:
                replay_bytes = Path(portability_replay).read_bytes()
            portability = _portability_record(saved_bytes, replay_bytes)
        else:
            _require(portability_replay is None, "Partial export cannot have a completed replay")
        data = _figure_data(root, p.ROOT / p.RELEASE, plan, report, summary)
        destination.mkdir(parents=True)
        for folder, files in (("main", raw_files), ("calibration", prefix)):
            (destination / folder).mkdir()
            for name, path in files.items():
                digest = p.sha(path)
                target = destination / folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                _require(p.sha(target) == digest, "Source changed during copy")
        _write(destination / "provenance/source.json", reference)
        (destination / "provenance/PLAN.json").write_bytes(plan_bytes)
        _write(destination / "provenance/controller.json", controller)
        _write(destination / "REPORT.json", report)
        _write(destination / "FIGURE_DATA.json", data)
        if summary:
            (destination / "analysis").mkdir()
            (destination / "analysis/summary.json").write_bytes(saved_bytes)
            (destination / "analysis/replay-summary.json").write_bytes(replay_bytes)
            _write(destination / "analysis/portability.json", portability)
        text, tex = _text_products(report, data, summary, controller)
        (destination / "RESULTS.md").write_bytes(text)
        (destination / "values.tex").write_bytes(tex)
        _plots(data, destination / "figures")
        files = _files(destination)
        _scan(files)
        _require(raw_hashes == {n: p.sha(f) for n, f in _raw_inventory(root, plan).items()},
                 "Retrieval hashes changed during reporting")
        _write(destination / "MANIFEST.json", {"schema": SCHEMA, "mode": mode, "freeze_commit": freeze,
            "plan_sha256": reference["plan_sha256"], "calibration_manifest_sha256": p.MANIFEST_SHA,
            "analysis_portability": portability,
            "reporting_source_hashes": _reporting_hashes(), "files": _entries(files)})
    return verify(destination, controller_receipt=receipt, controller_ledger=controller_ledger)


def _scan(files):
    for name, path in files.items():
        if name not in FIGURE_FILES and name not in {"calibration/" + n for n in prior.FIGURE_FILES}:
            prior._scan_text(name + ".json" if name.endswith(".pending") else name, path)


def verify(root, *, expected_manifest_sha256=None, controller_receipt=None, controller_ledger=None):
    root = Path(root)
    files = _files(root)
    manifest_path = files.pop("MANIFEST.json")
    digest = p.sha(manifest_path)
    manifest = _canonical(manifest_path)
    _require(expected_manifest_sha256 is None or digest == expected_manifest_sha256, "External manifest mismatch")
    _require(manifest["schema"] == SCHEMA and manifest["files"] == _entries(files)
             and manifest["reporting_source_hashes"] == _reporting_hashes(), "Manifest/reporting implementation drift")
    reference = _canonical(root / "provenance/source.json")
    _require(all(manifest[k] == reference[k] for k in ("freeze_commit", "plan_sha256"))
             and manifest["calibration_manifest_sha256"] == p.MANIFEST_SHA, "Manifest provenance mismatch")
    plan = _verify_sources((root / "provenance/PLAN.json").read_bytes(), reference)
    prefix, raw = _prefix_files(), _raw_inventory(root / "main", plan)
    for name, path in prefix.items():
        _require(p.sha(root / "calibration" / name) == p.sha(path), "Copied immutable calibration changed")
    expected = GENERATED | FIGURE_FILES | {"main/" + n for n in raw} | {"calibration/" + n for n in prefix}
    if manifest["mode"] == "completed":
        expected |= PORTABILITY_FILES
    _require(set(files) == expected, "Unexpected/missing public artifact")
    _scan(files)
    controller = _canonical(root / "provenance/controller.json")
    artifacts = {n: p.sha(f) for n, f in raw.items()}
    if controller["retrieval"]["status"] != "not_provided":
        _require(controller["retrieval"]["artifacts"] == artifacts, "Stored retrieval mismatch")
    external = controller_receipt is not None
    _require(controller_ledger is None or external, "External ledger needs receipt")
    if external:
        _require(controller == _controller(controller_receipt, controller_ledger, reference, artifacts), "External lifecycle mismatch")
    report = _audit(root / "main", plan, reference, manifest["mode"], controller)
    _require(_canonical(root / "REPORT.json") == report, "Report differs from raw audit")
    summary, _, local_check = _summary(root / "main", manifest["mode"])
    portability = None
    if summary:
        saved_bytes = (root / "main/analysis/summary.json").read_bytes()
        _require((root / "analysis/summary.json").read_bytes() == saved_bytes, "Saved worker summary bytes differ")
        portability = _portability_record(saved_bytes, (root / "analysis/replay-summary.json").read_bytes())
        _require((root / "analysis/portability.json").read_bytes() == (p.canonical(portability) + "\n").encode(),
                 "Archived portability record differs")
    _require(p.canonical(manifest["analysis_portability"]) == p.canonical(portability),
             "Manifest portability binding differs")
    data = _figure_data(root / "main", root / "calibration", plan, report, summary)
    _require(_canonical(root / "FIGURE_DATA.json") == data, "Figure data differs")
    text, tex = _text_products(report, data, summary, controller)
    _require((root / "RESULTS.md").read_bytes() == text and (root / "values.tex").read_bytes() == tex,
             "Summary/macros differ from evidence")
    with tempfile.TemporaryDirectory(prefix="dose-main-render-") as tmp:
        _plots(data, Path(tmp) / "figures")
        for name in FIGURE_FILES:
            _require((root / name).read_bytes() == (Path(tmp) / name).read_bytes(), "Figure rendering differs: " + name)
    _require(artifacts == {n: p.sha(f) for n, f in _raw_inventory(root / "main", plan).items()},
             "Retrieval hashes changed during verification")
    return {"pass": True, "mode": manifest["mode"], "main_status": report["main_status"], "manifest_sha256": digest,
        "external_manifest_bound": expected_manifest_sha256 is not None, "external_controller_bound": external,
        "lifecycle_verified_this_check": external and controller_ledger is not None,
        "retrieval_hashes_unchanged": True, "local_summary_replay": local_check}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument("--source", required=True, type=Path, help="Final retrieval receipt (raw directory only for incomplete drafts)")
    create.add_argument("--destination", required=True, type=Path)
    create.add_argument("--freeze", default=FREEZE)
    create.add_argument("--plan", type=Path)
    create.add_argument("--mode", required=True, choices=prior.MODES)
    create.add_argument("--controller-ledger", type=Path)
    create.add_argument("--portability-replay", type=Path,
                        help="Archived original local summary replay, required if this host cannot reproduce its bytes")
    check = commands.add_parser("verify")
    check.add_argument("--root", required=True, type=Path)
    check.add_argument("--manifest-sha256")
    check.add_argument("--controller-receipt", type=Path)
    check.add_argument("--controller-ledger", type=Path)
    args = parser.parse_args(argv)
    result = (build(args.source, args.destination, freeze=args.freeze, plan_path=args.plan,
                    mode=args.mode, controller_ledger=args.controller_ledger,
                    portability_replay=args.portability_replay) if args.command == "build" else
              verify(args.root, expected_manifest_sha256=args.manifest_sha256,
                     controller_receipt=args.controller_receipt, controller_ledger=args.controller_ledger))
    print(p.canonical(result))


if __name__ == "__main__":
    main()
