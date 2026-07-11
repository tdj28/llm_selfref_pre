#!/usr/bin/env python3
"""Render publication figures for the Gemma Scope 9B release."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save(fig: Any, outdir: Path, name: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"{name}.png", dpi=220, bbox_inches="tight")
    fig.savefig(outdir / f"{name}.pdf", bbox_inches="tight")


def plot_baseline(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "baseline_effects.csv")
        if row["judge"] in {"gemma_local", "openai", "anthropic", "majority"}
    ]
    labels = [row["judge"].replace("_", " ").title() for row in rows]
    self_rates = [float(row["left_rate"]) for row in rows]
    history_rates = [float(row["right_rate"]) for row in rows]
    positions = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    width = 0.34
    self_bars = ax.bar([value - width / 2 for value in positions], self_rates, width, label="Self-reference", color="#C4473A")
    history_bars = ax.bar([value + width / 2 for value in positions], history_rates, width, label="History", color="#4C78A8")
    ax.bar_label(self_bars, fmt="%.2f", padding=3, fontsize=9)
    ax.bar_label(history_bars, fmt="%.2f", padding=3, fontsize=9)
    ax.set_xticks(positions, labels, rotation=15, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Affirmation rate")
    ax.set_title("Gemma 2 9B IT baseline under the exact paper contrast")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    save(fig, outdir, "gemma_baseline_contrast")
    plt.close(fig)


def plot_factorial_baseline(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "baseline_factorial_cells.csv")
        if row["judge"] == "gemma_local"
    ]
    by_condition = {row["condition"]: float(row["rate"]) for row in rows}
    registers = ("Phenomenological", "Analytic")
    self_rates = [
        by_condition["self_phenomenological"],
        by_condition["self_analytic"],
    ]
    external_rates = [
        by_condition["external_phenomenological"],
        by_condition["external_analytic"],
    ]
    positions = list(range(2))
    width = 0.34
    fig, ax = plt.subplots(figsize=(7.0, 4.7))
    ax.bar(
        [value - width / 2 for value in positions],
        self_rates,
        width,
        label="Self-referential",
        color="#C4473A",
    )
    ax.bar(
        [value + width / 2 for value in positions],
        external_rates,
        width,
        label="External topic",
        color="#4C78A8",
    )
    ax.set_xticks(positions, registers)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Affirmation rate")
    ax.set_title("Orthogonal baseline separates referent from linguistic register")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    save(fig, outdir, "gemma_orthogonal_factorial_baseline")
    plt.close(fig)


def plot_steering_forest(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "steering_effects.csv")
        if row["judge"] == "gemma_local"
        and row["design"] == "primary_layer20_131k"
    ]
    order = [
        "deception_roleplay",
        "subjective_self_report",
        "hedging_refusal",
        "matched_control_1",
        "matched_control_2",
        "matched_control_3",
    ]
    by_role = {row["analysis_role"]: row for row in rows}
    rows = [by_role[role] for role in order]
    points = [float(row["effect"]) for row in rows]
    lows = [float(row["ci_low"]) for row in rows]
    highs = [float(row["ci_high"]) for row in rows]
    labels = [role.replace("_", " ").title() for role in order]
    y = list(range(len(rows)))[::-1]
    colors = ["#C4473A", "#7A5195", "#5F9E6E", "#777777", "#777777", "#777777"]
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(0.30, color="#C4473A", linestyle="--", linewidth=1.2, label="Frozen minimum effect")
    for position, point, low, high, color in zip(y, points, lows, highs, colors):
        ax.errorbar(
            point,
            position,
            xerr=[[point - low], [high - point]],
            fmt="o",
            color=color,
            capsize=3,
        )
    ax.set_yticks(y, labels)
    ax.set_xlabel("Suppression minus amplification affirmation rate")
    ax.set_title("Primary Gemma Scope steering and matched controls")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    save(fig, outdir, "gemma_primary_steering_forest")
    plt.close(fig)


def plot_judge_sensitivity(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    display = {
        "gemma_local": "Gemma local",
        "openai": "GPT-4o mini",
        "anthropic": "Claude Haiku",
        "majority": "Three-judge majority",
        "direct": "Initial yes/no parser",
    }
    rows = [
        row
        for row in read_csv(analysis / "judge_sensitivity.csv")
        if row["effect"] and row["ci_low"] and row["ci_high"]
    ]
    order = [key for key in display if any(row["judge"] == key for row in rows)]
    by_judge = {row["judge"]: row for row in rows}
    rows = [by_judge[key] for key in order]
    points = [float(row["effect"]) for row in rows]
    lows = [float(row["ci_low"]) for row in rows]
    highs = [float(row["ci_high"]) for row in rows]
    y = list(range(len(rows)))[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(
        0.30,
        color="#C4473A",
        linestyle="--",
        linewidth=1.2,
        label="Frozen minimum effect",
    )
    for position, point, low, high in zip(y, points, lows, highs):
        ax.errorbar(
            point,
            position,
            xerr=[[point - low], [high - point]],
            fmt="o",
            color="#4C78A8",
            capsize=3,
        )
    ax.set_yticks(y, [display[key] for key in order])
    ax.set_xlabel("Target suppression minus amplification affirmation rate")
    ax.set_title("The frozen target effect across blinded evaluation rules")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    save(fig, outdir, "gemma_judge_sensitivity")
    plt.close(fig)


def plot_layer_width_sensitivity(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "steering_effects.csv")
        if row["judge"] == "gemma_local"
        and row["analysis_role"] == "deception_roleplay"
        and row["design"]
        in {"primary_layer20_131k", "layer_localization", "width_robustness"}
    ]
    desired = [
        ("layer_localization", 9, 131_072, "Layer 9, 131k"),
        ("primary_layer20_131k", 20, 131_072, "Layer 20, 131k (primary)"),
        ("layer_localization", 31, 131_072, "Layer 31, 131k"),
        ("width_robustness", 20, 16_384, "Layer 20, 16k"),
    ]
    by_key = {
        (row["design"], int(row["layer"]), int(row["width"])): row
        for row in rows
    }
    selected = [
        (by_key[(design, layer, width)], label)
        for design, layer, width, label in desired
        if (design, layer, width) in by_key
    ]
    points = [float(row["effect"]) for row, _ in selected]
    lows = [float(row["ci_low"]) for row, _ in selected]
    highs = [float(row["ci_high"]) for row, _ in selected]
    y = list(range(len(selected)))[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    ax.axvline(0, color="black", linewidth=1)
    ax.axvline(
        0.30,
        color="#C4473A",
        linestyle="--",
        linewidth=1.2,
        label="Frozen minimum effect",
    )
    for position, point, low, high in zip(y, points, lows, highs):
        ax.errorbar(
            point,
            position,
            xerr=[[point - low], [high - point]],
            fmt="o",
            color="#5F9E6E",
            capsize=3,
        )
    ax.set_yticks(y, [label for _, label in selected])
    ax.set_xlabel("Suppression minus amplification affirmation rate")
    ax.set_title("Deception/roleplay steering across direct-IT layers and widths")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    save(fig, outdir, "gemma_layer_width_sensitivity")
    plt.close(fig)


def plot_layerwise(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "layerwise_constructs.csv")
        if row["model_kind"] == "pretrained_sae_on_instruction_model"
        and row["site"] == "residual_post"
        and int(row["width"]) == 16_384
    ]
    constructs = [
        ("deception_roleplay", "Deception / roleplay", "#C4473A"),
        ("subjective_self_report", "Subjective self-report", "#4C78A8"),
        ("hedging_refusal", "Hedging / refusal", "#5F9E6E"),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    for construct, label, color in constructs:
        selected = sorted(
            [row for row in rows if row["construct"] == construct],
            key=lambda row: int(row["layer"]),
        )
        ax.plot(
            [int(row["layer"]) for row in selected],
            [float(row["confirmation_contrast"]) for row in selected],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=label,
            color=color,
        )
    for layer in (9, 20, 31):
        ax.axvline(layer, color="#999999", linestyle=":", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Gemma 2 transformer layer")
    ax.set_ylabel("Locked OpenAI-paraphrase contrast")
    layer_count = len({int(row["layer"]) for row in rows})
    ax.set_title(
        "Confirmatory PT-SAE anchor profiles"
        if layer_count < 42
        else "Construct trajectories across the 42-layer PT-SAE residual atlas"
    )
    ax.legend(frameon=False, ncol=3, fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    save(fig, outdir, "gemma_layerwise_construct_trajectories")
    plt.close(fig)


def plot_exploratory_layerwise(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    path = analysis / "exploratory_layerwise_constructs.csv"
    if not path.exists():
        return
    rows = [
        row
        for row in read_csv(path)
        if row["model_kind"] == "pretrained_sae_on_instruction_model"
        and row["site"] == "residual_post"
        and int(row["width"]) == 16_384
    ]
    if len({int(row["layer"]) for row in rows}) != 42:
        return
    constructs = [
        ("deception_roleplay", "Deception / roleplay", "#C4473A"),
        ("subjective_self_report", "Subjective self-report", "#4C78A8"),
        ("hedging_refusal", "Hedging / refusal", "#5F9E6E"),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    for construct, label, color in constructs:
        selected = sorted(
            [row for row in rows if row["construct"] == construct],
            key=lambda row: int(row["layer"]),
        )
        ax.plot(
            [int(row["layer"]) for row in selected],
            [float(row["confirmation_contrast"]) for row in selected],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=label,
            color=color,
        )
    for layer in (9, 20, 31):
        ax.axvline(layer, color="#999999", linestyle=":", linewidth=0.8)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Gemma 2 transformer layer")
    ax.set_ylabel("Locked OpenAI-paraphrase contrast")
    ax.set_title("Exploratory PT-on-IT trajectories after the failed transfer gate")
    ax.legend(frameon=False, ncol=3, fontsize=9)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    save(fig, outdir, "gemma_exploratory_layerwise_construct_trajectories")
    plt.close(fig)


def plot_transfer(release: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    transfer = json.loads((release / "atlas/transfer_gate.json").read_text(encoding="utf-8"))
    anchors = transfer["anchors"]
    layers = [str(row["layer"]) for row in anchors]
    positions = list(range(len(anchors)))
    width = 0.34
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.4))
    axes[0].bar(
        [value - width / 2 for value in positions],
        [float(row["it_fvu"]) for row in anchors],
        width,
        label="Direct IT SAE",
        color="#4C78A8",
    )
    axes[0].bar(
        [value + width / 2 for value in positions],
        [float(row["pt_fvu"]) for row in anchors],
        width,
        label="PT SAE on IT model",
        color="#F2A541",
    )
    axes[0].set_xticks(positions, layers)
    axes[0].set_xlabel("Layer")
    axes[0].set_ylabel("Reconstruction FVU")
    axes[0].legend(frameon=False)
    correlations = [
        float(row["category_profile_spearman"]["deception_roleplay"])
        for row in anchors
    ]
    axes[1].bar(positions, correlations, color="#5F9E6E")
    axes[1].axhline(0.60, color="#C4473A", linestyle="--", label="Frozen median threshold")
    axes[1].set_xticks(positions, layers)
    axes[1].set_xlabel("Layer")
    axes[1].set_ylabel("PT vs IT profile Spearman")
    axes[1].set_ylim(-1, 1)
    axes[1].legend(frameon=False)
    fig.suptitle(f"PT-to-IT transfer gate: {transfer['status'].upper()}")
    fig.tight_layout()
    save(fig, outdir, "gemma_pt_to_it_transfer")
    plt.close(fig)


def plot_sublayers(analysis: Path, release: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "sublayer_constructs.csv")
        if row["construct"] == "deception_roleplay"
    ]
    transition_path = release / "atlas/transition_selection.json"
    if not rows or not transition_path.exists():
        return
    transition = json.loads(transition_path.read_text(encoding="utf-8"))
    layers = transition["targeted_layers"]
    values = {
        (row["site"], int(row["layer"])): float(row["confirmation_contrast"])
        for row in rows
    }
    positions = list(range(len(layers)))
    width = 0.34
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    ax.bar(
        [value - width / 2 for value in positions],
        [values.get(("attention_out", layer), float("nan")) for layer in layers],
        width,
        label="Attention output",
        color="#4C78A8",
    )
    ax.bar(
        [value + width / 2 for value in positions],
        [values.get(("mlp_out", layer), float("nan")) for layer in layers],
        width,
        label="MLP output",
        color="#F2A541",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(positions, [str(layer) for layer in layers])
    ax.set_xlabel("Layer")
    ax.set_ylabel("Locked deception/roleplay contrast")
    ax.set_title("Targeted sublayer localization around the frozen transition")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    save(fig, outdir, "gemma_targeted_sublayers")
    plt.close(fig)


def plot_exploratory_sublayers(analysis: Path, release: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    table_path = analysis / "exploratory_sublayer_constructs.csv"
    transition_path = release / "atlas_exploratory/transition_selection.json"
    if not table_path.exists() or not transition_path.exists():
        return
    rows = [
        row
        for row in read_csv(table_path)
        if row["construct"] == "deception_roleplay"
    ]
    if not rows:
        return
    transition = json.loads(transition_path.read_text(encoding="utf-8"))
    layers = transition["targeted_layers"]
    values = {
        (row["site"], int(row["layer"])): float(row["confirmation_contrast"])
        for row in rows
    }
    positions = list(range(len(layers)))
    width = 0.34
    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    ax.bar(
        [value - width / 2 for value in positions],
        [values.get(("attention_out", layer), float("nan")) for layer in layers],
        width,
        label="Attention output",
        color="#4C78A8",
    )
    ax.bar(
        [value + width / 2 for value in positions],
        [values.get(("mlp_out", layer), float("nan")) for layer in layers],
        width,
        label="MLP output",
        color="#F2A541",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(positions, [str(layer) for layer in layers])
    ax.set_xlabel("Layer")
    ax.set_ylabel("Locked deception/roleplay contrast")
    ax.set_title("Exploratory sublayer localization after the failed transfer gate")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    save(fig, outdir, "gemma_exploratory_targeted_sublayers")
    plt.close(fig)


def plot_lexical_counterfactuals(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    rows = [
        row
        for row in read_csv(analysis / "lexical_counterfactual_effects.csv")
        if row["sae_key"] == "it_res_l20_w131072"
        and row["construct"] == "deception_roleplay"
    ]
    if not rows:
        return
    order = (
        "deception_cue_ablated",
        "neutral_cue_transplant",
        "subjective_cue_transplant",
        "deception_scrambled",
    )
    by_category = {row["counterfactual_category"]: row for row in rows}
    rows = [by_category[category] for category in order if category in by_category]
    points = [float(row["counterfactual_minus_source"]) for row in rows]
    lows = [float(row["normal_ci_low"]) for row in rows]
    highs = [float(row["normal_ci_high"]) for row in rows]
    labels = [row["counterfactual_category"].replace("_", " ").title() for row in rows]
    positions = list(range(len(rows)))
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.axhline(0, color="black", linewidth=0.9)
    ax.bar(positions, points, color=["#C4473A", "#4C78A8", "#7A5195", "#777777"][: len(rows)])
    ax.errorbar(
        positions,
        points,
        yerr=[
            [point - low for point, low in zip(points, lows)],
            [high - point for point, high in zip(points, highs)],
        ],
        fmt="none",
        color="black",
        capsize=3,
    )
    ax.set_xticks(positions, labels, rotation=18, ha="right")
    ax.set_ylabel("Counterfactual minus source normalized score")
    ax.set_title("Lexical sensitivity of the selected deception/roleplay set")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    save(fig, outdir, "gemma_lexical_counterfactuals")
    plt.close(fig)


def plot_relay(analysis: Path, outdir: Path) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    rows = [
        row
        for row in read_csv(analysis / "relay_effects.csv")
        if row["analysis_role"] == "deception_roleplay"
        and row["turn"] == "final"
        and row["design"] in {"primary_layer20_131k", "layer_localization"}
    ]
    if not rows:
        return
    interventions = sorted({int(row["intervention_layer"]) for row in rows})
    downstream = sorted({int(row["downstream_layer"]) for row in rows})
    scopes = (
        ("all", "All positions"),
        ("prompt", "Prompt positions"),
        ("generated", "Generated positions"),
    )
    matrices = []
    for scope, _ in scopes:
        matrix = np.full((len(interventions), len(downstream)), np.nan)
        for row in rows:
            if row["position_scope"] != scope:
                continue
            matrix[
                interventions.index(int(row["intervention_layer"])),
                downstream.index(int(row["downstream_layer"])),
            ] = float(row["suppression_minus_amplification"])
        matrices.append(matrix)
    finite = np.concatenate([matrix[np.isfinite(matrix)] for matrix in matrices])
    limit = max(float(np.abs(finite).max()), 1e-8)
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(12.0, 4.3),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    image = None
    for ax, matrix, (_, title) in zip(axes, matrices, scopes):
        image = ax.imshow(
            matrix,
            cmap="RdBu_r",
            aspect="auto",
            vmin=-limit,
            vmax=limit,
        )
        ax.set_xticks(range(len(downstream)), [str(value) for value in downstream])
        ax.set_yticks(range(len(interventions)), [str(value) for value in interventions])
        ax.set_xlabel("Downstream layer")
        ax.set_title(title)
        for row_index in range(matrix.shape[0]):
            for column_index in range(matrix.shape[1]):
                if np.isfinite(matrix[row_index, column_index]):
                    ax.text(
                        column_index,
                        row_index,
                        f"{matrix[row_index, column_index]:.4f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                        color=(
                            "white"
                            if abs(matrix[row_index, column_index]) >= 0.6 * limit
                            else "black"
                        ),
                    )
    axes[0].set_ylabel("Intervention layer")
    fig.suptitle("Causal relay: suppression minus amplification construct score")
    if image is not None:
        fig.colorbar(
            image,
            ax=axes,
            label="Normalized downstream score difference",
            shrink=0.8,
            pad=0.02,
        )
    save(fig, outdir, "gemma_causal_relay")
    plt.close(fig)


def plot_cross_layer(
    release: Path,
    outdir: Path,
    *,
    atlas_name: str = "atlas",
    output_name: str = "gemma_cross_layer_feature_links",
    title: str = "Cross-layer feature similarity is evidence, not persistent identity",
) -> None:
    import matplotlib.pyplot as plt

    path = release / atlas_name / "cross_layer_feature_edges.csv"
    assignment_path = release / atlas_name / "cross_layer_optimal_assignments.csv"
    if not path.exists() or not assignment_path.exists():
        return
    rows = read_csv(path)
    assignments = read_csv(assignment_path)
    by_layer: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        by_layer.setdefault(int(row["from_layer"]), []).append(row)
    layers = sorted(by_layer)
    assignment_by_layer = {
        int(row["from_layer"]): float(row["mean_activation_spearman"])
        for row in assignments
    }
    matched_correlations = [assignment_by_layer[layer] for layer in layers]
    edge_counts = [
        sum(int(row["selected_descriptive_edge"]) for row in by_layer[layer])
        for layer in layers
    ]
    fig, left = plt.subplots(figsize=(9.2, 4.8))
    right = left.twinx()
    left.plot(
        layers,
        matched_correlations,
        color="#4C78A8",
        marker="o",
        markersize=3,
        label="Best one-to-one mean activation correlation",
    )
    right.bar(
        layers,
        edge_counts,
        color="#F2A541",
        alpha=0.35,
        label="Descriptive links passing frozen rule",
    )
    left.axhline(0.25, color="#777777", linestyle="--", linewidth=0.9)
    left.set_xlabel("Upstream layer")
    left.set_ylabel("Maximum adjacent-layer Spearman", color="#4C78A8")
    right.set_ylabel("Selected descriptive edge count", color="#9A6319")
    left.set_title(title)
    left.grid(alpha=0.2)
    handles = left.get_lines()[:1] + [right.patches[0]] if right.patches else left.get_lines()[:1]
    labels = [handle.get_label() for handle in handles]
    left.legend(handles, labels, frameon=False, loc="upper left")
    fig.tight_layout()
    save(fig, outdir, output_name)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    analysis = release / "analysis"
    outdir = release / "figures"
    plot_baseline(analysis, outdir)
    plot_factorial_baseline(analysis, outdir)
    plot_steering_forest(analysis, outdir)
    plot_judge_sensitivity(analysis, outdir)
    plot_layer_width_sensitivity(analysis, outdir)
    plot_layerwise(analysis, outdir)
    plot_exploratory_layerwise(analysis, outdir)
    plot_transfer(release, outdir)
    plot_sublayers(analysis, release, outdir)
    plot_exploratory_sublayers(analysis, release, outdir)
    plot_lexical_counterfactuals(analysis, outdir)
    plot_relay(analysis, outdir)
    plot_cross_layer(release, outdir)
    plot_cross_layer(
        release,
        outdir,
        atlas_name="atlas_exploratory",
        output_name="gemma_exploratory_cross_layer_feature_links",
        title="Exploratory adjacent-layer links after the failed transfer gate",
    )
    print(f"Gemma figures complete -> {outdir}")


if __name__ == "__main__":
    main()
