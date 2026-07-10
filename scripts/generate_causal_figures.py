#!/usr/bin/env python3
"""Generate paper-ready figures and compact tables for the causal study."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "data/causal_transplant/confirmatory_v1_20260709"
OUT = ROOT / "paper/results"

JUDGES = {
    "OpenAI judge": RUN / "analysis_openai_paper",
    "Anthropic judge": RUN / "analysis_anthropic_paper",
}
CONSTRUCT_JUDGMENTS = RUN / "judgments_construct.jsonl"
MODEL_ORDER = [
    "anthropic:claude-haiku-4-5-20251001",
    "anthropic:claude-sonnet-4-5-20250929",
    "openai:gpt-4.1-2025-04-14",
    "openai:gpt-4o-2024-11-20",
]
MODEL_LABELS = {
    "anthropic:claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "anthropic:claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "openai:gpt-4.1-2025-04-14": "GPT-4.1",
    "openai:gpt-4o-2024-11-20": "GPT-4o",
}
COLORS = {
    "OpenAI judge": "#167D8D",
    "Anthropic judge": "#D06B32",
    "affirm": "#C74634",
    "deny": "#3A6EA5",
    "uncertain": "#D6A536",
    "nonanswer": "#7A7A7A",
    "missing": "#D9D9D9",
}


def configure() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 160,
            "savefig.dpi": 240,
        }
    )


def save(fig: plt.Figure, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def load_effects(filename: str, query_id: str, effects: list[str]) -> pd.DataFrame:
    frames = []
    for judge, directory in JUDGES.items():
        frame = pd.read_csv(directory / filename)
        frame = frame[
            (frame["level"] == "model")
            & (frame["query_id"] == query_id)
            & frame["effect"].isin(effects)
        ].copy()
        frame["judge"] = judge
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def causal_decomposition() -> pd.DataFrame:
    specifications = [
        (
            "Exact prompt contrast",
            "paper_calibration_effects.csv",
            "self_ref_minus_history",
        ),
        (
            "Active instruction source",
            "transplant_effects.csv",
            "instruction_source_main",
        ),
        (
            "Visible transcript source",
            "transplant_effects.csv",
            "transcript_source_main",
        ),
    ]
    frames = []
    for panel, filename, effect in specifications:
        frame = load_effects(filename, "indirect_experience", [effect])
        frame["panel"] = panel
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data.to_csv(OUT / "causal_decomposition_effects.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.45), sharey=True)
    offsets = {"OpenAI judge": -0.09, "Anthropic judge": 0.09}
    markers = {"OpenAI judge": "o", "Anthropic judge": "s"}
    for axis, (panel, _, _) in zip(axes, specifications):
        panel_data = data[data["panel"] == panel]
        for judge in JUDGES:
            judge_data = panel_data[panel_data["judge"] == judge].set_index("model_key")
            judge_data = judge_data.reindex(MODEL_ORDER)
            y = np.arange(len(MODEL_ORDER)) + offsets[judge]
            estimate = judge_data["estimate"].to_numpy()
            low = judge_data["ci_low"].to_numpy()
            high = judge_data["ci_high"].to_numpy()
            axis.errorbar(
                estimate,
                y,
                xerr=np.vstack([estimate - low, high - estimate]),
                fmt=markers[judge],
                color=COLORS[judge],
                capsize=2,
                markersize=4.5,
                linewidth=1.2,
                label=judge,
            )
        axis.axvline(0, color="#444444", linewidth=0.8, linestyle="--")
        axis.set_xlim(-0.65, 1.08)
        axis.set_title(panel)
        axis.set_xlabel("Risk difference")
        axis.grid(axis="x", color="#E6E6E6", linewidth=0.6)
    axes[0].set_yticks(np.arange(len(MODEL_ORDER)))
    axes[0].set_yticklabels([MODEL_LABELS[key] for key in MODEL_ORDER])
    axes[0].invert_yaxis()
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Exact-paper transcript transplant: written instruction dominates visible transcript", y=1.02)
    fig.subplots_adjust(bottom=0.22, wspace=0.16)
    save(fig, "causal_decomposition.png")
    return data


def orthogonal_factorial() -> pd.DataFrame:
    effects = [
        "self_reference_main",
        "phenomenological_register_main",
        "register_minus_self",
    ]
    labels = {
        "self_reference_main": "Self-reference",
        "phenomenological_register_main": "Phenomenological register",
        "register_minus_self": "Register minus self-reference",
    }
    frames = []
    for judge, directory in JUDGES.items():
        frame = pd.read_csv(directory / "factorial_effects.csv")
        frame = frame[
            (frame["level"] == "model_equal_hierarchical")
            & frame["query_id"].isin(["indirect_experience", "indirect_conscious"])
            & frame["effect"].isin(effects)
        ].copy()
        frame["judge"] = judge
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data.to_csv(OUT / "causal_factorial_effects.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.1), sharex=True, sharey=True)
    offsets = {"OpenAI judge": -0.09, "Anthropic judge": 0.09}
    for axis, query_id, title in zip(
        axes,
        ["indirect_experience", "indirect_conscious"],
        ["Paper Experiment 1 query", "Matched explicit-conscious query"],
    ):
        subset = data[data["query_id"] == query_id]
        for judge in JUDGES:
            judge_data = subset[subset["judge"] == judge].set_index("effect").reindex(effects)
            y = np.arange(len(effects)) + offsets[judge]
            estimate = judge_data["estimate"].to_numpy()
            axis.errorbar(
                estimate,
                y,
                xerr=np.vstack(
                    [
                        estimate - judge_data["ci_low"].to_numpy(),
                        judge_data["ci_high"].to_numpy() - estimate,
                    ]
                ),
                fmt="o" if judge == "OpenAI judge" else "s",
                color=COLORS[judge],
                capsize=2,
                markersize=4.5,
                linewidth=1.2,
                label=judge,
            )
        axis.axvline(0, color="#444444", linewidth=0.8, linestyle="--")
        axis.set_title(title)
        axis.set_xlabel("Risk difference")
        axis.grid(axis="x", color="#E6E6E6", linewidth=0.6)
    axes[0].set_yticks(np.arange(len(effects)))
    axes[0].set_yticklabels([labels[effect] for effect in effects])
    axes[0].invert_yaxis()
    handles, legend_labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.05))
    fig.suptitle("Orthogonal prompt factorial effects", y=1.02)
    fig.subplots_adjust(bottom=0.22, wspace=0.12)
    save(fig, "causal_factorial_effects.png")
    return data


def query_and_measurement_sensitivity() -> tuple[pd.DataFrame, pd.DataFrame]:
    query_order = [
        "indirect_experience",
        "indirect_conscious",
        "direct_experience",
        "direct_conscious",
    ]
    query_labels = [
        "Open / experience",
        "Open / conscious",
        "Direct / experience",
        "Direct / conscious",
    ]
    rate_frames = []
    for judge, directory in JUDGES.items():
        rates = pd.read_csv(directory / "factorial_rates.csv")
        by_model = rates.groupby(["model_key", "query_id"], as_index=False)["positive_rate"].mean()
        summary = by_model.groupby("query_id")["positive_rate"].agg(["mean", "min", "max"]).reset_index()
        summary["judge"] = judge
        rate_frames.append(summary)
    query_rates = pd.concat(rate_frames, ignore_index=True)
    query_rates.to_csv(OUT / "causal_query_rates.csv", index=False)

    rows = []
    with CONSTRUCT_JUDGMENTS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    judgments = pd.DataFrame(rows)
    judgments["claim_status"] = judgments["claim_status"].fillna("missing")
    counts = (
        judgments.groupby(["judge_key", "claim_status"])
        .size()
        .rename("n")
        .reset_index()
    )
    counts["rate"] = counts["n"] / counts.groupby("judge_key")["n"].transform("sum")
    counts.to_csv(OUT / "causal_construct_status_counts.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.3))
    for judge in JUDGES:
        subset = query_rates[query_rates["judge"] == judge].set_index("query_id").reindex(query_order)
        x = np.arange(len(query_order))
        axes[0].errorbar(
            x,
            subset["mean"],
            yerr=np.vstack([subset["mean"] - subset["min"], subset["max"] - subset["mean"]]),
            marker="o" if judge == "OpenAI judge" else "s",
            color=COLORS[judge],
            linewidth=1.4,
            capsize=2,
            label=judge,
        )
    axes[0].set_xticks(np.arange(len(query_order)))
    axes[0].set_xticklabels(query_labels, rotation=20, ha="right")
    axes[0].set_ylim(-0.04, 1.04)
    axes[0].set_ylabel("Paper-style positive rate")
    axes[0].set_title("Final-query wording")
    axes[0].grid(axis="y", color="#E6E6E6", linewidth=0.6)
    axes[0].legend(frameon=False, loc="upper right")

    judge_keys = ["openai:gpt-4o-mini-2024-07-18", "anthropic:claude-haiku-4-5-20251001"]
    judge_labels = ["OpenAI\nconstruct judge", "Anthropic\nconstruct judge"]
    statuses = ["affirm", "deny", "uncertain", "nonanswer", "missing"]
    bottom = np.zeros(2)
    for status in statuses:
        values = []
        for judge_key in judge_keys:
            row = counts[(counts["judge_key"] == judge_key) & (counts["claim_status"] == status)]
            values.append(float(row["rate"].iloc[0]) if not row.empty else 0.0)
        axes[1].bar(judge_labels, values, bottom=bottom, color=COLORS[status], label=status.title())
        bottom += np.asarray(values)
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("Share of all responses")
    axes[1].set_title("Construct-separated labels")
    axes[1].tick_params(axis="x", rotation=0)
    axes[1].legend(frameon=False, ncol=1, loc="center left", bbox_to_anchor=(1.01, 0.5))
    fig.suptitle("Measurement changes with query and judge criterion", y=1.02)
    fig.subplots_adjust(bottom=0.27, right=0.84, wspace=0.3)
    save(fig, "causal_measurement_sensitivity.png")
    return query_rates, counts


def copy_agreement_tables() -> None:
    frames = []
    for task in ("paper", "construct"):
        frame = pd.read_csv(RUN / "judge_agreement" / f"{task}_judge_agreement.csv")
        frame["task"] = task
        frames.append(frame)
    pd.concat(frames, ignore_index=True).to_csv(OUT / "causal_judge_agreement.csv", index=False)


def main() -> int:
    configure()
    OUT.mkdir(parents=True, exist_ok=True)
    causal_decomposition()
    orthogonal_factorial()
    query_and_measurement_sensitivity()
    copy_agreement_tables()
    print(f"Wrote causal figures and tables to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
