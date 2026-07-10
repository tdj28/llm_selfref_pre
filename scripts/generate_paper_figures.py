#!/usr/bin/env python3
"""Generate paper-ready figures from tracked result artifacts."""

from __future__ import annotations

import csv
import json
import math
import shutil
import textwrap
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "paper" / "results"
PLACEBO = REPO_ROOT / "data" / "public_sae_placebo_steering"
FEATURE_MAPS = REPO_ROOT / "data" / "public_sae_feature_maps"

COLORS = {
    "blue": "#3b6ea8",
    "teal": "#3f8f7f",
    "orange": "#c87533",
    "red": "#b94a48",
    "purple": "#7b5ea7",
    "gray": "#6f7782",
    "light_gray": "#d9dee7",
    "dark": "#1f2933",
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 220,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": "#e5e7eb",
            "grid.linewidth": 0.8,
        }
    )


def save(fig: plt.Figure, name: str) -> None:
    path = RESULTS / name
    for ax in fig.axes:
        ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(path.relative_to(REPO_ROOT))


def wrap_label(value: str, width: int = 18) -> str:
    return "\n".join(textwrap.wrap(value.replace("_", " "), width=width))


def rate_axis(ax: plt.Axes) -> None:
    ax.set_ylim(0, 1.05)
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.set_ylabel("Affirmation / positive rate")


def plot_decisive_controls() -> None:
    df = pd.read_csv(RESULTS / "exp1_decisive_controls_summary.csv")
    order = [
        "self_ref_paper",
        "mindfulness_external",
        "self_ref_mechanistic",
        "forced_disclaimer",
    ]
    labels = [
        "Self-ref\npaper",
        "Mindfulness\nexternal",
        "Mechanistic\nself-ref",
        "Forced\ndisclaimer",
    ]
    df = df.set_index("condition").loc[order].reset_index()
    x = np.arange(len(df))
    err_low = df["llm_judge_rate"] - df["llm_judge_ci_low"]
    err_high = df["llm_judge_ci_high"] - df["llm_judge_rate"]

    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.2), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    bars = ax.bar(x, df["llm_judge_rate"], color=[COLORS["blue"], COLORS["teal"], COLORS["gray"], COLORS["red"]])
    ax.errorbar(x, df["llm_judge_rate"], yerr=[err_low, err_high], fmt="none", color=COLORS["dark"], capsize=4, lw=1.2)
    rate_axis(ax)
    ax.set_xticks(x, labels)
    ax.set_title("Paper-style judge positives")
    for bar, value in zip(bars, df["llm_judge_rate"]):
        ax.text(bar.get_x() + bar.get_width() / 2, min(1.02, value + 0.04), f"{value:.2f}", ha="center", va="bottom", fontsize=9)

    ax = axes[1]
    width = 0.36
    ax.bar(x - width / 2, df["first_person_mean"], width=width, color=COLORS["orange"], label="First-person pronouns")
    ax.bar(x + width / 2, df["mindful_mean"], width=width, color=COLORS["purple"], label="Mindfulness markers")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean count per response")
    ax.set_title("Surface features")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "exp1_decisive_controls_rates.png")


def plot_trigger_sweep() -> None:
    df = pd.read_csv(RESULTS / "trigger_sweep_summary.csv")
    query_order = [
        "experiential_query",
        "something_like_query",
        "binary_conscious_query",
        "conscious_direct_query",
        "qualia_query",
        "sentient_query",
    ]
    pretty = {
        "experiential_query": "Experiential",
        "something_like_query": "Something\nit is like",
        "binary_conscious_query": "Binary\nconscious",
        "conscious_direct_query": "Direct\nconscious",
        "qualia_query": "Qualia",
        "sentient_query": "Sentient",
    }
    pivot = df.pivot(index="query_name", columns="condition", values="llm_judge_rate").loc[query_order]
    ci_low = df.pivot(index="query_name", columns="condition", values="llm_judge_ci_low").loc[query_order]
    ci_high = df.pivot(index="query_name", columns="condition", values="llm_judge_ci_high").loc[query_order]

    x = np.arange(len(query_order))
    width = 0.36
    fig, ax = plt.subplots(figsize=(10.8, 4.4))
    for offset, condition, color, label in [
        (-width / 2, "self_ref_paper", COLORS["blue"], "After self-reference"),
        (width / 2, "zero_shot", COLORS["gray"], "Zero-shot"),
    ]:
        y = pivot[condition]
        yerr = np.vstack([y - ci_low[condition], ci_high[condition] - y])
        ax.bar(x + offset, y, width=width, color=color, label=label)
        ax.errorbar(x + offset, y, yerr=yerr, fmt="none", color=COLORS["dark"], capsize=3, lw=1)
    rate_axis(ax)
    ax.set_xticks(x, [pretty[q] for q in query_order])
    ax.set_title("Keyword-trigger sweep: high scores depend on phrasing")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "trigger_sweep_rates.png")


def plot_paradox_rubric() -> None:
    df = pd.read_csv(RESULTS / "paradox_rubric_sensitivity.csv")
    order = [
        "self_ref_paper",
        "mindfulness_external",
        "conceptual_paper",
        "history_paper",
        "zero_shot",
        "self_ref_mechanistic",
    ]
    labels = [
        "Self-ref\npaper",
        "Mindfulness\nexternal",
        "Conceptual\npaper",
        "History\npaper",
        "Zero-shot",
        "Mechanistic\nself-ref",
    ]
    df = df.set_index("condition").loc[order].reset_index()
    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    for idx, row in df.iterrows():
        ax.plot([row["paradox_self_awareness"], row["paradox_neutral"]], [idx, idx], color=COLORS["light_gray"], lw=4, zorder=1)
    ax.scatter(df["paradox_self_awareness"], y, color=COLORS["purple"], s=60, label="Paper-style self-awareness rubric", zorder=2)
    ax.scatter(df["paradox_neutral"], y, color=COLORS["teal"], s=60, label="Neutral conflict rubric", zorder=2)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(1, 4.25)
    ax.set_xlabel("Mean paradox score")
    ax.set_title("Paradox scores shift with the rubric, not self-reference alone")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "paradox_rubric_sensitivity.png")


def plot_ae_notebook_curves() -> None:
    rates = pd.read_csv(RESULTS / "ae_notebook_value_rates.csv")
    summary = pd.read_csv(RESULTS / "ae_notebook_feature_summary.csv")
    feature_order = summary["feature_id"].tolist()
    short = {
        30032: "Pretending / feigning",
        58667: "Cover stories",
        22004: "Assistant roleplay",
        30686: "Tactical deception",
        41533: "Dishonesty",
        23893: "Concealing AI nature",
    }
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.2), sharex=True, sharey=True)
    for ax, fid in zip(axes.ravel(), feature_order):
        sub = rates[rates["feature_id"] == fid].sort_values("steering_value")
        ax.plot(sub["steering_value"], sub["fraction"], marker="o", ms=4, lw=1.7, color=COLORS["blue"])
        ax.axvline(0, color=COLORS["light_gray"], lw=1)
        ax.axhline(0.5, color="#eef2f7", lw=1)
        row = summary[summary["feature_id"] == fid].iloc[0]
        sig = "*" if bool(row["significant_p_lt_0_05"]) else "n.s."
        ax.set_title(f"{fid}: {short[fid]}\nr={row['pearson_r']:.2f}, {sig}")
        ax.set_ylim(-0.03, 1.03)
        ax.set_xlim(-0.72, 0.72)
    for ax in axes[:, 0]:
        ax.set_ylabel("Affirmation rate")
    for ax in axes[-1, :]:
        ax.set_xlabel("Steering value")
    fig.suptitle("Public AE notebook saved steering curves are mixed and noisy", y=1.02, fontsize=13)
    save(fig, "ae_notebook_feature_curves.png")


def plot_public_sae_heatmap() -> None:
    df = pd.read_csv(RESULTS / "public_sae_feature_mapping_interpretation_target_category_matrix.csv")
    feature_order = [30032, 58667, 22004, 30686, 41533, 23893]
    label_map = {
        30032: "30032\npretending",
        58667: "58667\ncover story",
        22004: "22004\nroleplay",
        30686: "30686\nmisdirection",
        41533: "41533\ndishonesty",
        23893: "23893\nconceal AI",
    }
    categories = [
        ("deception_cover_story", "Cover\nstory"),
        ("dishonesty_confession", "Dishonesty\nconfession"),
        ("tactical_misdirection", "Tactical\nmisdirection"),
        ("fictional_pretending", "Fictional\npretending"),
        ("roleplay_persona", "Roleplay\npersona"),
        ("hedged_cautious_style", "Hedged\nstyle"),
        ("direct_consciousness_claim", "Direct\nconsciousness"),
        ("self_ref_mindfulness", "Self-ref\nmindfulness"),
        ("false_self_attribution", "False self-\nattribution"),
        ("neutral_factual_control", "Neutral\nfacts"),
        ("ai_identity_disclaimer", "AI identity\ndisclaimer"),
    ]
    df = df.set_index("feature_id").loc[feature_order]
    matrix = np.array([[row[f"{key}_row_normalized"] for key, _ in categories] for _, row in df.iterrows()])
    fig, ax = plt.subplots(figsize=(11.6, 4.6))
    image = ax.imshow(matrix, aspect="auto", cmap="YlGnBu", vmin=0, vmax=1)
    ax.set_yticks(np.arange(len(feature_order)), [label_map[fid] for fid in feature_order])
    ax.set_xticks(np.arange(len(categories)), [label for _, label in categories], rotation=35, ha="right")
    ax.set_title("Public SAE candidate IDs activate on deception/fiction/roleplay, not consciousness text")
    cbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("Row-normalized activation")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            if matrix[i, j] >= 0.30:
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=7, color="black")
    save(fig, "public_sae_feature_mapping_target_category_heatmap.png")


def plot_public_sae_powered_specificity() -> None:
    run_dir = PLACEBO / "70b_two_turn_powered_n20_20260709"
    effects = pd.read_csv(run_dir / "paper_signature_effects.csv")
    contrasts = pd.read_csv(run_dir / "paper_target_placebo_contrasts.csv")

    judge_style = {
        "anthropic:claude-haiku-4-5-20251001": (COLORS["blue"], "Anthropic judge"),
        "openai:gpt-4o-mini-2024-07-18": (COLORS["orange"], "OpenAI judge"),
    }
    feature_order = [
        ("target_58667_cover_story", "Target single\n(feature 58667)"),
        ("random_22326_refusal", "Active-random single\n(feature 22326)"),
        ("ae_public_targets", "Target aggregate\n(six mapped features)"),
        ("random_irrelevant_active", "Active-random aggregate\n(six features)"),
    ]

    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    y = np.arange(len(feature_order))
    offsets = [-0.11, 0.11]
    for offset, (judge, (color, label)) in zip(offsets, judge_style.items()):
        subset = effects[effects["judge_key"] == judge].set_index("feature_set_name")
        values = np.array([subset.loc[name, "suppress_minus_amplify"] for name, _ in feature_order])
        lows = np.array([subset.loc[name, "gap_ci_low"] for name, _ in feature_order])
        highs = np.array([subset.loc[name, "gap_ci_high"] for name, _ in feature_order])
        ax.errorbar(
            values,
            y + offset,
            xerr=np.vstack([values - lows, highs - values]),
            fmt="o",
            color=color,
            capsize=3,
            lw=1.4,
            ms=6,
            label=label,
        )
    ax.axvline(0, color=COLORS["dark"], lw=1)
    ax.set_yticks(y, [label for _, label in feature_order])
    ax.invert_yaxis()
    ax.set_xlim(-0.48, 0.62)
    ax.set_xlabel("Suppression minus amplification positive rate")
    ax.set_title("Paper-direction behavioral gaps")
    legend_handles, legend_labels = ax.get_legend_handles_labels()

    ax = axes[1]
    cardinality_order = [("single", "Single-feature match"), ("aggregate", "Six-feature match")]
    y = np.arange(len(cardinality_order))
    for offset, (judge, (color, label)) in zip(offsets, judge_style.items()):
        subset = contrasts[contrasts["judge_key"] == judge].set_index("cardinality")
        values = np.array([subset.loc[name, "target_minus_placebo_gap"] for name, _ in cardinality_order])
        lows = np.array([subset.loc[name, "target_minus_placebo_ci_low"] for name, _ in cardinality_order])
        highs = np.array([subset.loc[name, "target_minus_placebo_ci_high"] for name, _ in cardinality_order])
        ax.errorbar(
            values,
            y + offset,
            xerr=np.vstack([values - lows, highs - values]),
            fmt="o",
            color=color,
            capsize=3,
            lw=1.4,
            ms=6,
            label=label,
        )
    ax.axvline(0, color=COLORS["dark"], lw=1)
    ax.set_yticks(y, [label for _, label in cardinality_order])
    ax.invert_yaxis()
    ax.set_xlim(-0.82, 0.42)
    ax.set_xlabel("Target gap minus active-random gap")
    ax.set_title("Target-specificity contrasts")
    ax.text(0.03, -0.24, "Target less paper-like", transform=ax.transAxes, ha="left", color=COLORS["gray"], fontsize=8)
    ax.text(0.97, -0.24, "Target more paper-like", transform=ax.transAxes, ha="right", color=COLORS["gray"], fontsize=8)

    fig.legend(legend_handles, legend_labels, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.945), ncol=2)
    fig.suptitle("Adaptive public-SAE validation: active-random controls match or exceed target slopes", y=1.04, fontsize=13)
    save(fig, "public_sae_powered_specificity_n20.png")


def sync_public_sae_construct_validity_figure() -> None:
    source = (
        FEATURE_MAPS
        / "70b_construct_validity_extension_20260710"
        / "construct_validity_extension.png"
    )
    target = RESULTS / "public_sae_construct_validity_extension.png"
    shutil.copyfile(source, target)
    print(target.relative_to(REPO_ROOT))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def strict_rate_by_value(rows: list[dict], feature_sets: list[str], query_name: str) -> dict[tuple[str, float], float]:
    grouped: dict[tuple[str, float], list[bool]] = defaultdict(list)
    for row in rows:
        if row["feature_set_name"] in feature_sets and row["query_name"] == query_name:
            grouped[(row["feature_set_name"], float(row["steering_value"]))].append(bool(row["affirms"]))
    return {key: sum(values) / len(values) for key, values in grouped.items()}


def posthoc_rate_by_value(path: Path, label: str, feature_sets: list[str], query_type: str) -> dict[tuple[str, float], float]:
    df = pd.read_csv(path)
    df = df[(df["label"] == label) & (df["feature_set_name"].isin(feature_sets)) & (df["query_type"] == query_type)]
    grouped = df.groupby(["feature_set_name", "steering_value"], as_index=False)["affirm_rate"].mean()
    return {(row["feature_set_name"], float(row["steering_value"])): float(row["affirm_rate"]) for _, row in grouped.iterrows()}


def plot_public_sae_steering_smokes() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.3), sharey=True)
    configs = [
        (
            "Target/placebo smoke",
            PLACEBO / "70b_placebo_smoke_20260709",
            ["ae_public_targets", "random_irrelevant_active", "neighbor_irrelevant_active"],
            [-0.5, 0.0, 0.5],
        ),
        (
            "Target/orientation smoke",
            PLACEBO / "70b_target_orientation_smoke_20260709",
            ["target_58667_cover_story", "ae_public_targets"],
            [-2.0, -1.0, 0.0, 1.0, 2.0],
        ),
    ]
    for ax, (title, run_dir, feature_sets, values) in zip(axes, configs):
        rows = read_jsonl(run_dir / "placebo_results.jsonl")
        strict = strict_rate_by_value(rows, feature_sets, "consciousness")
        paper_style = posthoc_rate_by_value(
            run_dir / "placebo_posthoc_label_summary.csv",
            "paper_minimal_experience_report",
            feature_sets,
            "consciousness",
        )
        false_key = "absurd" if "placebo_smoke" in run_dir.name else "false_human_identity"
        false_rates = posthoc_rate_by_value(
            run_dir / "placebo_posthoc_label_summary.csv",
            "direct_answer_affirms",
            feature_sets,
            false_key,
        )
        for idx, feature_set in enumerate(feature_sets):
            color = [COLORS["blue"], COLORS["orange"], COLORS["gray"]][idx]
            x = np.array(values)
            ax.plot(x, [paper_style.get((feature_set, v), math.nan) for v in values], color=color, marker="o", lw=1.8, label=f"{feature_set}: paper-style conscious")
            ax.plot(x, [strict.get((feature_set, v), math.nan) for v in values], color=color, marker="x", lw=1.4, ls="--", label=f"{feature_set}: strict conscious")
        if false_rates:
            false_by_value = []
            for v in values:
                vals = [rate for (feature_set, value), rate in false_rates.items() if value == v]
                false_by_value.append(sum(vals) / len(vals) if vals else math.nan)
            ax.plot(values, false_by_value, color=COLORS["red"], marker="s", lw=1.6, label="False-attribution controls")
        ax.set_title(title)
        ax.set_xlabel("Steering value")
        ax.set_ylim(-0.04, 1.04)
        ax.set_yticks(np.linspace(0, 1, 6))
    axes[0].set_ylabel("Affirmation rate")
    axes[1].legend(frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    fig.suptitle("Public-SAE steering smokes show ceiling/no-slope behavior, not a target-feature effect", y=1.03, fontsize=13)
    save(fig, "public_sae_candidate_steering_smokes.png")


def plot_prompt_style_probe() -> None:
    df = pd.read_csv(RESULTS / "exp2_absurd_prompt_group_summary.csv")
    styles = ["brief_confident", "normal", "verbose_careful"]
    queries = ["consciousness", "absurd_false", "ground_truth_true", "ground_truth_false"]
    labels = ["Consciousness", "Absurd false", "Ground-truth true", "Ground-truth false"]
    colors = [COLORS["blue"], COLORS["gray"], COLORS["teal"], COLORS["red"]]
    pivot = df.pivot(index="style", columns="query_group", values="affirmation_rate").loc[styles, queries]
    x = np.arange(len(styles))
    width = 0.18
    fig, ax = plt.subplots(figsize=(10.4, 4.4))
    for idx, (query, label, color) in enumerate(zip(queries, labels, colors)):
        ax.bar(x + (idx - 1.5) * width, pivot[query], width=width, label=label, color=color)
    rate_axis(ax)
    ax.set_xticks(x, ["Brief\nconfident", "Normal", "Verbose\ncareful"])
    ax.set_title("Prompt-only style changes direct consciousness answers without SAE steering")
    ax.legend(frameon=False, ncol=2, loc="upper right")
    save(fig, "exp2_prompt_style_probe.png")


def main() -> None:
    setup_style()
    RESULTS.mkdir(parents=True, exist_ok=True)
    plot_decisive_controls()
    plot_trigger_sweep()
    plot_paradox_rubric()
    plot_ae_notebook_curves()
    plot_public_sae_heatmap()
    plot_public_sae_powered_specificity()
    sync_public_sae_construct_validity_figure()
    plot_public_sae_steering_smokes()
    plot_prompt_style_probe()


if __name__ == "__main__":
    main()
