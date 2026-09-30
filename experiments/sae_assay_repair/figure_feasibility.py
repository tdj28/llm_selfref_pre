"""Display saved-data surrogate limits and coverage, never native outcomes."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render(summary_path, out):
    data = json.loads(Path(summary_path).read_text())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    labels = [str(f) for f in data["feature_ids"]]
    x = np.arange(len(labels))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "svg.hashsalt": "sae-offline-feasibility-20260930"})

    def save(fig, name):
        for suffix in ("png", "svg", "pdf"):
            fig.savefig(out / (name + "." + suffix), dpi=170, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.3), sharey=True)
    for ax, dose in zip(axes, ("0.5", "1.0")):
        for offset, split, color, label in ((-.17, "calibration", "#147d79", "Historical calibration"),
                                           (.17, "validation", "#b06036", "Historical validation")):
            records = data["splits"][split]["old_amplification_relaxed_inequalities"][dose]["per_feature_necessary_bounds"]
            values = [r["upper_bound_on_efficacious_positions"] / r["eligible_nonspecial_positions"] for r in records]
            ax.bar(x + offset, values, width=.32, color=color, label=label)
        ax.axhline(.5, color="#333333", linestyle="--", linewidth=1)
        ax.set(title="Original dose " + dose, xticks=x, xticklabels=labels, ylim=(0, 1.07))
        ax.set_xlabel("Feature ID")
        ax.grid(axis="y", alpha=.15)
    axes[0].set_ylabel("Upper bound on efficacious-position fraction")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(.5, .92), ncol=2, fontsize=8)
    fig.suptitle("Old amplification: necessary median bounds in the linear surrogate", fontsize=13)
    fig.text(.5, -.03, "Every feature is granted all global norm exceptions. Below 0.5 excludes its median only in this surrogate.\n"
             "At dose 0.5 no feature is excluded. Native BF16 behavior is not computed.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .85))
    save(fig, "linear-feasibility-bounds")

    fig, axes = plt.subplots(2, 2, figsize=(12, 7.4))
    cal = data["splits"]["calibration"]["active_support_075_cap004"]
    for column, mode in enumerate(("suppression", "amplification")):
        rows = cal[mode]["feature_surrogates"]
        top, bottom = axes[0, column], axes[1, column]
        for offset, key, color, label in ((-.25, "predicted_median_ratio", "#147d79", "4% cap, all active"),
                                         (0, "window_all_active_median", "#777777", "2-4% window, all active"),
                                         (.25, "window_dispatched_median", "#b06036", "Window, dispatched only")):
            values = [r[key] if r[key] is not None else np.nan for r in rows]
            top.bar(x + offset, values, width=.23, color=color, label=label)
        top.axhline(.5, color="#333333", linestyle="--", linewidth=1)
        top.set(title=mode.capitalize(), xticks=x, xticklabels=labels, ylim=(0, 1.15))
        top.set_ylabel("After/before" if mode == "suppression" else "Achieved/requested increment")
        available = [r["active_nonspecial_positions"] for r in rows]
        dispatched = [r["window_dispatched_active_positions"] for r in rows]
        bottom.bar(x-.17, available, width=.32, color="#777777", label="All active positions")
        bottom.bar(x+.17, dispatched, width=.32, color="#b06036", label="Window-dispatched")
        for i, n in enumerate(dispatched):
            bottom.text(i+.17, n+15, str(n), ha="center", fontsize=8)
        bottom.set(xticks=x, xticklabels=labels, ylabel="Calibration positions", xlabel="Feature ID", ylim=(0, 1400))
        if column == 0:
            bottom.legend(fontsize=8)
        for ax in (top, bottom):
            ax.grid(axis="y", alpha=.15)
    fig.suptitle("Active-support prototype: geometric efficacy is not assay qualification", fontsize=13)
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(.5, .94), ncol=3, fontsize=8)
    fig.text(.5, -.015, "Continuous predictions, not model forwards. Skipped states remain in all-active medians.\n"
             "Feature 22004 has zero window-dispatched calibration positions; conditional success cannot conceal this.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .045, 1, .89))
    save(fig, "prototype-coverage-tradeoff")
