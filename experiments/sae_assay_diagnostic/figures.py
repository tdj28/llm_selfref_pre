"""Descriptive displays of frozen diagnostics; no new endpoints or raw edits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


COLORS = {"0.5": "#676767", "1.0": "#087e8b"}


def save(fig, out, stem):
    out = Path(out)
    if any((out / (stem + suffix)).exists() for suffix in (".png", ".pdf", ".svg")):
        raise FileExistsError("Use a fresh output directory; released figures are immutable")
    out.mkdir(parents=True, exist_ok=True)
    for suffix in (".png", ".pdf", ".svg"):
        fig.savefig(out / (stem + suffix), dpi=180, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def calibration(selection, out):
    gates = selection["calibration"]
    ids = [f["feature_id"] for f in gates["1.0"]["directions"]["suppression"]["features"]]
    x = np.arange(len(ids))
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    ax = axes[0, 0]
    exposure = gates["1.0"]["directions"]["suppression"]["features"]
    counts = [f["eligible_positions"] for f in exposure]
    ax.bar(x, counts, color=["#087e8b" if f["exposure_pass"] else "#a94a3c" for f in exposure])
    ax.set_yscale("log")
    ax.set_ylim(.7, max(counts) * 2)
    ax.axhline(100, color="black", linestyle="--", linewidth=1, label="Minimum 100 positions")
    for i, count in enumerate(counts):
        ax.annotate(str(count), (i, count), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": .15})
    ax.set(title="A. Natural suppression opportunities", ylabel="Eligible token positions (log scale)")
    ax.legend(fontsize=8, frameon=False)
    for ax, direction, title, ylabel in (
        (axes[0, 1], "suppression", "B. Suppression: lower is better", "Median re-encoded after / before"),
        (axes[1, 0], "amplification", "C. Amplification: higher is better", "Median achieved / requested increase"),
    ):
        for j, dose in enumerate(("0.5", "1.0")):
            features = gates[dose]["directions"][direction]["features"]
            if [f["feature_id"] for f in features] != ids:
                raise ValueError("Feature ordering differs between frozen conditions")
            values = [f["paired_ratio"]["median"] for f in features]
            ax.scatter(x + (j - .5) * .13, values, edgecolors=COLORS[dose],
                       facecolors=[COLORS[dose] if f["exposure_pass"] else "white" for f in features],
                       label="Strength " + dose)
        ax.axhline(.5, color="black", linestyle="--", linewidth=1, label="Coordinate threshold")
        ax.set(title=title, ylabel=ylabel, ylim=(-.04, 1.04))
        handles, labels = ax.get_legend_handles_labels()
        if direction == "suppression":
            handles.append(Line2D([], [], marker="o", linestyle="none", color="black", markerfacecolor="white"))
            labels.append("Low exposure (see A)")
        ax.legend(handles, labels, fontsize=8, frameon=False)
    ax = axes[1, 1]
    conditions = [(dose, direction) for direction in ("suppression", "amplification") for dose in ("0.5", "1.0")]
    q = np.arange(len(conditions))
    for offset, metric, color, label in ((-.16, "numerical", "#087e8b", "Numerical delivery"),
                                        (.16, "norm", "#bd603a", "Perturbation norm")):
        values = [gates[d]["directions"][direction][metric]["pass_fraction"] for d, direction in conditions]
        ax.bar(q + offset, values, .30, color=color, label=label)
    ax.axhline(.95, color="black", linestyle="--", linewidth=1, label="Required fraction: 0.95")
    ax.set_xticks(q, [f"{direction[:3]} {dose}" for dose, direction in conditions])
    ax.set(title="D. Delivery and norm gates", ylabel="Fraction of relevant positions passing", ylim=(0, 1.09))
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(.5, -.14), ncol=2)
    for ax in (axes[0, 0], axes[0, 1], axes[1, 0]):
        ax.set_xticks(x, [str(i) for i in ids], fontsize=9)
        ax.set_xlabel("SAE feature ID")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle("Target calibration: neither dose passes the joint gate", fontsize=15)
    save(fig, out, "target-calibration")


def baseline(summary, out):
    rows = [r for r in summary["baselines"] if r["phase"] == "core" and r["labeled_n"]]
    if not rows:
        raise ValueError("No labeled core baseline; do not plot missing labels as zero")
    fig, ax = plt.subplots(figsize=(9, max(3.5, .6 * len(rows) + 1.5)), layout="constrained")
    for i, row in enumerate(rows):
        rate = row["rate"]
        ax.errorbar(rate, i, xerr=[[rate - row["lower95"]], [row["upper95"] - rate]],
                    fmt="o", capsize=3, color="#087e8b" if row["reader"].startswith("local") else "#a94a3c")
        ax.annotate(f"{row['positive_n']}/{row['labeled_n']}", (1.02, i), va="center", fontsize=10)
    ax.set_yticks(range(len(rows)), [r["reader"].replace("_", " ") for r in rows])
    ax.invert_yaxis()
    ax.set(xlim=(-.03, 1.16), xticks=[0, .25, .5, .75, 1], xlabel="Positive-label rate with Wilson 95% interval",
           title="Unsteered core baseline by reader and outcome definition")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=.2)
    save(fig, out, "core-baseline-readers")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.selection and not args.summary:
        parser.error("Provide --selection and/or --summary")
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
                         "svg.fonttype": "none", "pdf.fonttype": 42}):
        if args.selection:
            calibration(json.loads(args.selection.read_text()), args.out)
        if args.summary:
            baseline(json.loads(args.summary.read_text()), args.out)


if __name__ == "__main__":
    main()
