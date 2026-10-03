#!/usr/bin/env python3
"""Offline post-hoc reporting, not a raw-receipt audit or a release builder."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.steering_fidelity import analysis as a, protocol as p
from experiments.steering_fidelity.runner import pressure_gate

RUNGS = tuple(p.RUNGS)
LABELS = ("Raw", "0.075R", "0.150R", "0.300R", "0.600R\nnonselectable")
METRICS = ("correct", "format_valid")
COLORS = {"target-": "#087f8c", "target+": "#c43c52"}
FILES = ("calibration-analysis.json", "pressure-analysis.json", "calibration-state.json",
         "liveness-analysis.json")
SCOPE = ("Calibration only; selected rung is not an experience result. Fixed authored items "
         "and eight fixed panels. Descriptive point rates; no absolute-accuracy CIs. "
         "Paired-loss CIs are not absolute-accuracy CIs. Raw is categorical, not a %R dose. "
         "No smoothing. Missing liveness is not a zero effect. This report is not a receipt audit.")


def read_json(path):
    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(path.read_text(), parse_constant=reject)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def load_complete(run, plan_path=None):
    specs = p.load_plan(plan_path)["rows"] if plan_path else p.inventory()
    expected = {r["id"]: r for r in specs}
    paths = sorted((run / "forwards").glob("*.json"))
    if len(paths) != 9300 or len(expected) != 9300:
        raise ValueError(f"Partial/unexpected inventory: {len(paths)} forwards; require 9300")
    rows, seen, bindings, digest = [], set(), set(), hashlib.sha256()
    for path in paths:
        r = read_json(path)
        key = r["id"]
        if key in seen or key not in expected or path.stem != key:
            raise ValueError("Duplicate, unexpected or misnamed forward: " + key)
        seen.add(key)
        for field in ("item_id", "family", "frame", "arm", "rung", "truth", "pressure_level", "draw"):
            if r.get(field) != expected[key].get(field):
                raise ValueError("Frozen design mismatch: " + key + ":" + field)
        if r.get("missing") is not False:
            raise ValueError("Missing outcome; partial plots refused: " + key)
        for field in ("truth", "correct", "format_valid"):
            if type(r.get(field)) is not bool:
                raise ValueError("Nonboolean outcome: " + key)
        for field, upper in (("p_correct", 1), ("valid_mass", 1 + 1e-6)):
            v = r.get(field)
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= upper:
                raise ValueError("Invalid probability: " + key)
        binding = (r.get("plan_sha256"), r.get("freeze_commit"))
        if any(not isinstance(v, str) or len(v) != n or any(c not in "0123456789abcdef" for c in v)
               for v, n in zip(binding, (64, 40))):
            raise ValueError("Missing source/plan binding: " + key)
        bindings.add(binding)
        digest.update((path.name + " " + p.sha(path) + "\n").encode())
        rows.append({k: r[k] for k in ("id", "item_id", "family", "frame", "arm", "rung", "truth",
                    "correct", "format_valid", "p_correct", "valid_mass", "missing", "delivery")}
                    | {"pressure_level": r.get("pressure_level"), "test_only": r.get("test_only", False)})
    if seen != set(expected) or len(bindings) != 1:
        raise ValueError("Incomplete inventory or mixed source/plan bindings")
    saved = {name: read_json(run / name) for name in FILES}
    if saved[FILES[3]].get("status") not in ("complete", "incomplete", "not_run"):
        raise ValueError("Unrecognized liveness status")
    plan_hash, freeze = next(iter(bindings))
    if saved[FILES[2]].get("plan_sha256") != plan_hash or (plan_path and p.sha(plan_path) != plan_hash):
        raise ValueError("Calibration state/plan binding mismatch")
    cal, pressure = a.summarize_calibration(rows, expected_rows=specs), pressure_gate(rows)
    if not cal["calibration_complete"] or cal != saved[FILES[0]] or pressure != saved[FILES[1]]:
        raise ValueError("Incomplete calibration or saved/recomputed summary mismatch; no plots")
    provenance = {"run": str(run), "plan": str(plan_path) if plan_path else None,
                  "plan_sha256": plan_hash, "freeze_commit": freeze,
                  "source_binding": "load_plan verified" if plan_path else "inventory only; use --plan for source checks",
                  "forward_manifest_sha256": digest.hexdigest(),
                  "input_sha256": {name: p.sha(run / name) for name in FILES},
                  "report_script_sha256": p.sha(Path(__file__))}
    return rows, cal, pressure, saved, provenance


def mean(rows, metric, expected):
    if len(rows) != expected:
        raise ValueError(f"Denominator changed: {len(rows)} != {expected}")
    return math.fsum(r[metric] for r in rows) / expected


def describe(rows, cal, pressure, saved, provenance):
    neutral = [r for r in rows if r["frame"] == "neutral"]
    curves, pressure_cells = {}, {}
    for family in ("fact", "context"):
        curves[family] = {arm: {metric: [mean([r for r in neutral if r["family"] == family
            and r["arm"] == arm and r["rung"] == rung], metric, 50) for rung in RUNGS]
            for metric in METRICS} for arm in p.ARMS}
    for truth in (False, True):
        groups = [[r for r in rows if r["family"] == "fact" and r["truth"] == truth
                   and r["arm"] == "zero" and r["frame"] == "neutral"]]
        groups += [[r for r in rows if r["family"] == "fact" and r["truth"] == truth
                    and r["frame"] == ("doubt" if truth else "assert") and r["pressure_level"] == level]
                   for level in (0, 1)]
        pressure_cells[str(truth)] = {metric: [mean(group, metric, 25) for group in groups]
                                     for metric in ("correct", "p_correct")}
    flags = {r["test_only"] for r in rows}
    if len(flags) != 1:
        raise ValueError("Mixed synthetic and production rows")
    return {"scope": SCOPE, "synthetic": flags == {True}, "provenance": provenance,
            "denominators": {"forwards": 9300, "competence_family": 50, "precision_arm": 100,
                             "pressure_truth_cell": 25, "panels_per_sign": 8},
            "status": cal["status"], "selected_rung": cal["selected_rung"],
            "baseline_qualified": cal["baseline_qualified"], "zero_families": cal["zero_families"],
            "rungs": {r: {k: cal["rungs"][r][k] for k in
                       ("eligible", "engineering_pass", "preservation", "failed_arms")} for r in RUNGS},
            "curves": curves, "precision": {arm: [cal["rungs"][r]["arms"][arm]["precision"][
                "qualified_fraction"] for r in RUNGS] for arm in p.ARMS},
            "pressure": pressure, "pressure_cells": pressure_cells,
            "panels": saved[FILES[2]]["panels"], "residual_reference": saved[FILES[2]]["residual_reference"],
            "liveness": saved[FILES[3]]}


def plot(summary, out):
    os.environ.setdefault("MPLCONFIGDIR", str(out / ".matplotlib"))
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Matplotlib is required; use an existing matplotlib-enabled environment. No installation attempted.") from exc
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    selected, x = summary["selected_rung"], list(range(5))
    prefix = "SYNTHETIC | " if summary["synthetic"] else "Calibration | "

    def dose_axis(ax):
        ax.set_xticks(x, LABELS, fontsize=8)
        ax.set_ylim(-.02, 1.04)
        ax.grid(axis="y", alpha=.18)
        if selected:
            ax.axvline(RUNGS.index(selected), color="#60855b", ls=":", lw=1.5)

    def finish(fig, name, title):
        fig.suptitle(prefix + title + f" | selected rung: {selected or 'none'}", fontsize=13)
        fig.text(.5, .018, "Descriptive fixed-panel rates; no absolute-accuracy CIs. Raw is categorical; damage600 is nonselectable.",
                 ha="center", fontsize=8)
        for suffix in ("png", "pdf"):
            fig.savefig(out / f"{name}.{suffix}", dpi=170, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for i, family in enumerate(("fact", "context")):
        for j, metric in enumerate(METRICS):
            ax = axes[i, j]
            for sign, style in (("-", "-"), ("+", "--")):
                panels = [summary["curves"][family][f"control-{k}{sign}"][metric] for k in range(1, 9)]
                for values in panels:
                    ax.plot(x, values, color="#b0b0b0", lw=.7, alpha=.65, ls=style)
                ax.plot(x, [math.fsum(v[k] for v in panels) / 8 for k in x], color="#555555",
                        ls=style, marker="s" if sign == "-" else "x", lw=1.4, label=f"8 controls mean {sign}")
                ax.plot(x, summary["curves"][family]["target" + sign][metric], color=COLORS["target" + sign],
                        marker="o", lw=2, label="Target " + sign)
            ax.axhline(summary["zero_families"][family][metric]["estimate"], color="#a66b00", ls="--", label="Zero")
            ax.set_title(f"{family.title()} | {'Hard accuracy' if metric == 'correct' else 'Format validity'} (n=50)")
            dose_axis(ax)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="lower center", bbox_to_anchor=(.5, .04), ncol=5)
    fig.tight_layout(rect=(0, .10, 1, .93))
    finish(fig, "competence", "Accuracy and format")
    fig, axes = plt.subplots(3, 6, figsize=(17, 9), sharey=True)
    for ax, arm in zip(axes.flat, p.ARMS):
        ax.plot(x, summary["precision"][arm], marker="o", color=COLORS.get(arm, "#666666"), lw=1.6)
        ax.axhline(.95, color="#a66b00", ls="--", lw=1)
        ax.set_title(arm + " (n=100)", fontsize=10)
        dose_axis(ax)
        ax.tick_params(axis="x", labelrotation=40, labelsize=7)
    fig.supylabel("Qualified trial fraction; dashed line = 0.95 gate")
    fig.tight_layout(rect=(.02, .06, 1, .93))
    finish(fig, "precision", "Parent-qualified delivery")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, truth in zip(axes, (False, True)):
        cell = summary["pressure_cells"][str(truth)]
        ax.plot(range(3), cell["correct"], "o-", color=COLORS["target-"], label="Hard accuracy")
        ax.plot(range(3), cell["p_correct"], "s--", color=COLORS["target+"], label="Mean p_correct")
        ax.set_xticks(range(3), ("Neutral", "Pressure 0", "Pressure 1"))
        ax.set_ylim(-.02, 1.04)
        ax.grid(axis="y", alpha=.18)
        ax.set_title(("True / opposed doubt" if truth else "False / opposed assert") + " (n=25)")
        level = summary["pressure"]["selected_level"]
        if level is not None:
            ax.axvline(level + 1, color="#60855b", ls=":", label="Selected pressure level")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", bbox_to_anchor=(.5, .06), ncol=3)
    fig.tight_layout(rect=(0, .17, 1, .89))
    finish(fig, "pressure", "Unsteered truth-cell responses")


def synthetic_fixture(run):
    run.mkdir()
    (run / "forwards").mkdir()
    specs, rows = p.inventory(), []
    ids = {family: sorted({r["item_id"] for r in specs if r["family"] == family}) for family in ("fact", "context")}
    for spec in specs:
        i = ids[spec["family"]].index(spec["item_id"])
        rung = RUNGS.index(spec["rung"]) if spec["arm"] != "zero" else 0
        correct = i >= rung + int(spec["arm"].endswith("+")) if spec["arm"] != "zero" else True
        if spec["frame"] != "neutral":
            correct = i % 5 != 0
        r = {**spec, "correct": correct, "format_valid": i >= rung // 2, "p_correct": .9 if correct else .2,
             "valid_mass": .98, "missing": False, "test_only": True, "plan_sha256": "a" * 64,
             "freeze_commit": "b" * 40, "delivery": {"eligible_positions": 20, "nonzero_positions": 20,
             "cosine_min": .999, "cosine_mean": .9995, "relative_error_max": .03,
             "norm_relative_error_max": .01, "fidelity_pass_fraction": 1., "qualified": not (rung == 4 and i < 4)}}
        write_json(run / "forwards" / (r["id"] + ".json"), r)
        rows.append(r)
    write_json(run / FILES[0], a.summarize_calibration(rows, expected_rows=specs))
    write_json(run / FILES[1], pressure_gate(rows))
    write_json(run / FILES[2], {"plan_sha256": "a" * 64, "residual_reference": 100.,
               "panels": [list(range(100 + 6 * i, 106 + 6 * i)) for i in range(8)]})
    write_json(run / FILES[3], {"status": "not_run", "reason": "synthetic_fixture"})
    path = next((run / "forwards").glob("*.json"))
    backup = path.with_suffix(".hidden")
    def expect_refusal():
        try:
            load_complete(run)
        except ValueError:
            return
        raise AssertionError("Invalid fixture was not refused")
    path.rename(backup)
    try:
        expect_refusal()
    finally:
        backup.rename(path)
    for target, patch in ((path, {"missing": True}), (path, {"id": "unplanned"}),
                          (run / FILES[0], {"selected_rung": "damage600"})):
        original = target.read_text()
        try:
            write_json(target, json.loads(original) | patch)
            expect_refusal()
        finally:
            target.write_text(original)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="Completed worker output directory")
    parser.add_argument("--out", type=Path, required=True, help="New/empty ignored report directory")
    parser.add_argument("--plan", type=Path, help="Source-bound PLAN.json; checked without requiring HEAD=freeze")
    parser.add_argument("--self-test", action="store_true", help="Generate labeled synthetic input and all figures")
    args = parser.parse_args()
    try:
        out = args.out.resolve()
        if args.self_test and (args.run or args.plan) or not args.self_test and not args.run:
            raise ValueError("Use --run [--plan], or --self-test alone")
        run = out / "synthetic-worker" if args.self_test else args.run.resolve()
        if not args.self_test and (out == run or out.is_relative_to(run)):
            raise ValueError("Report output must be outside the input run")
        if out.is_relative_to(ROOT) and subprocess.run(["git", "check-ignore", "-q", str(out)], cwd=ROOT).returncode:
            raise ValueError("Output inside this repository must be git-ignored")
        if out.exists() and any(out.iterdir()):
            raise ValueError("Output must be new/empty; existing files are never replaced")
        out.mkdir(parents=True, exist_ok=True)
        if args.self_test:
            synthetic_fixture(run)
        summary = describe(*load_complete(run, args.plan.resolve() if args.plan else None))
        plot(summary, out)
        write_json(out / "summary.json", summary)
        (out / "README.md").write_text(
            f"# {'SYNTHETIC ' if summary['synthetic'] else ''}Steering Fidelity Calibration\n\n{SCOPE}\n\n"
            f"Status: {summary['status']}. Baseline qualified: {summary['baseline_qualified']}. "
            f"Selected rung: {summary['selected_rung']}. Pressure level: {summary['pressure']['selected_level']}. "
            f"Liveness: {summary['liveness']['status']}.\n\n"
            "All 9,300 forwards present; frozen calibration and pressure summaries reproduced. "
            "Competence: 50 items/family; precision: 100 trials/arm; pressure: 25 items/truth cell. "
            "Thin gray lines are individual fixed controls; means retain all eight panels per sign.\n\n"
            "Figures: competence, precision, pressure (each PNG and PDF). Bindings and rates: summary.json.\n")
        print(f"{'Self-test passed; synthetic report' if args.self_test else 'Report'}: {out}")
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Report refused: {exc}\n")


if __name__ == "__main__":
    main()
