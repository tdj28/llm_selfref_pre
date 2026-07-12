#!/usr/bin/env python3
"""Render the frozen SAE/J-lens v2 semantic and reader-capacity figures."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


FAMILIES = (
    "deception_dishonesty",
    "refusal_safety",
    "hedging_uncertainty",
    "formality_politeness",
)
FAMILY_LABELS = {
    "deception_dishonesty": "Deception /\ndishonesty",
    "refusal_safety": "Refusal /\nsafety",
    "hedging_uncertainty": "Hedging /\nuncertainty",
    "formality_politeness": "Formality /\npoliteness",
}
TRANSPORT_LABELS = {
    "jacobian": "Jacobian",
    "identity": "Identity",
    "random_j_1": "Random J1",
    "random_j_2": "Random J2",
    "random_j_3": "Random J3",
    "random_j_4": "Random J4",
    "random_j_5": "Random J5",
}
COLORS = {
    "jacobian": "#15616d",
    "identity": "#d17b0f",
    "random": "#6c757d",
    "threshold": "#9b2226",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save_pair(fig: Any, outdir: Path, stem: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"{stem}.png", dpi=220, bbox_inches="tight")
    fig.savefig(outdir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def semantic_matrix(analysis_dir: Path, outdir: Path) -> None:
    rows = [
        row
        for row in read_csv(analysis_dir / "semantic_a1_matrix.csv")
        if row["transport"] == "jacobian"
    ]
    lookup = {
        (row["intervention_family"], row["lexicon"]): float(row["mean_oriented_z"])
        for row in rows
    }
    matrix = np.asarray(
        [[lookup[(family, lexicon)] for lexicon in FAMILIES] for family in FAMILIES]
    )
    bound = max(0.25, float(np.max(np.abs(matrix))))
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    image = ax.imshow(matrix, cmap="RdBu_r", vmin=-bound, vmax=bound, aspect="auto")
    for row_index in range(4):
        for column_index in range(4):
            value = matrix[row_index, column_index]
            color = "white" if abs(value) > 0.55 * bound else "#111111"
            ax.text(
                column_index,
                row_index,
                f"{value:.2f}",
                ha="center",
                va="center",
                color=color,
                fontsize=10,
            )
    ax.set_xticks(range(4), [FAMILY_LABELS[value] for value in FAMILIES])
    ax.set_yticks(range(4), [FAMILY_LABELS[value] for value in FAMILIES])
    ax.set_xlabel("Readout lexicon")
    ax.set_ylabel("Intervention family")
    ax.set_title("Jacobian readout family matrix")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.85)
    colorbar.set_label("Mean oriented change (clean-score SD)")
    fig.tight_layout()
    save_pair(fig, outdir, "sae_jlens_v2_a1_semantic_matrix")


def target_comparator(analysis_dir: Path, outdir: Path) -> None:
    rows = read_csv(analysis_dir / "semantic_a2_summary.csv")
    order = list(TRANSPORT_LABELS)
    lookup = {row["transport"]: row for row in rows}
    points = np.asarray([float(lookup[key]["mean_target_minus_comparator_z"]) for key in order])
    low = np.asarray([float(lookup[key]["ci95_low"]) for key in order])
    high = np.asarray([float(lookup[key]["ci95_high"]) for key in order])
    x = np.arange(len(order))
    colors = [
        COLORS["jacobian"] if key == "jacobian" else COLORS["identity"] if key == "identity" else COLORS["random"]
        for key in order
    ]
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.errorbar(
        x,
        points,
        yerr=np.vstack((points - low, high - points)),
        fmt="none",
        ecolor="#4a4a4a",
        capsize=4,
        linewidth=1.5,
    )
    ax.scatter(x, points, c=colors, s=52, zorder=3)
    ax.axhline(0, color="#222222", linewidth=1)
    ax.axhline(0.25, color=COLORS["threshold"], linestyle="--", linewidth=1.2)
    ax.axhspan(-0.25, 0.25, color="#e9ecef", alpha=0.55, zorder=0)
    ax.set_xticks(x, [TRANSPORT_LABELS[key] for key in order], rotation=25, ha="right")
    ax.set_ylabel("Target minus comparator (clean-score SD)")
    ax.set_title("Selected target IDs versus same-subfamily comparators")
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.7)
    fig.tight_layout()
    save_pair(fig, outdir, "sae_jlens_v2_a2_target_comparator")


def reader_ladder(analysis_dir: Path, outdir: Path) -> None:
    rows = read_csv(analysis_dir / "reader_metrics.csv")
    labels = [row["reader_id"].replace("_", " ") for row in rows]
    points = np.asarray([float(row["macro_leave_one_pair_auroc"]) for row in rows])
    low = np.asarray([float(row["macro_bootstrap_ci_low"]) for row in rows])
    high = np.asarray([float(row["macro_bootstrap_ci_high"]) for row in rows])
    y = np.arange(len(rows))[::-1]
    colors = [
        COLORS["jacobian"]
        if row["reader_id"] == "v1_jacobian_67"
        else COLORS["identity"]
        if row["reader_id"] == "v1_identity_67"
        else COLORS["random"]
        for row in rows
    ]
    fig, ax = plt.subplots(figsize=(9.4, 7.2))
    ax.errorbar(
        points,
        y,
        xerr=np.vstack((points - low, high - points)),
        fmt="none",
        ecolor="#4a4a4a",
        capsize=3,
        linewidth=1.4,
    )
    ax.scatter(points, y, c=colors, s=46, zorder=3)
    ax.axvline(0.5, color="#222222", linewidth=1)
    ax.axvline(0.6, color=COLORS["threshold"], linestyle="--", linewidth=1.2)
    ax.set_yticks(y, labels)
    ax.set_xlim(0.35, 1.0)
    ax.set_xlabel("Macro leave-one-feature-pair AUROC")
    ax.set_title("Crossed-holdout reader-capacity ladder")
    ax.grid(axis="x", color="#d9d9d9", linewidth=0.7)
    fig.tight_layout()
    save_pair(fig, outdir, "sae_jlens_v2_reader_ladder")


def reader_pair_heatmap(analysis_dir: Path, outdir: Path) -> None:
    rows = read_csv(analysis_dir / "reader_pair_metrics.csv")
    reader_ids = list(dict.fromkeys(row["reader_id"] for row in rows))
    pair_ids = sorted({int(row["feature_pair"]) for row in rows})
    lookup = {
        (row["reader_id"], int(row["feature_pair"])): float(row["auroc"])
        for row in rows
    }
    matrix = np.asarray(
        [[lookup[(reader_id, pair_id)] for pair_id in pair_ids] for reader_id in reader_ids]
    )
    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    image = ax.imshow(matrix, cmap="viridis", vmin=0.0, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(pair_ids)), [str(value) for value in pair_ids], rotation=25, ha="right")
    ax.set_yticks(range(len(reader_ids)), [value.replace("_", " ") for value in reader_ids])
    ax.set_xlabel("Held target/control feature pair")
    ax.set_ylabel("Reader")
    ax.set_title("Reader heterogeneity across fixed feature pairs")
    colorbar = fig.colorbar(image, ax=ax, shrink=0.85)
    colorbar.set_label("AUROC")
    fig.tight_layout()
    save_pair(fig, outdir, "sae_jlens_v2_reader_pair_heatmap")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    analysis_dir = args.analysis_dir.resolve()
    outdir = args.outdir.resolve()
    semantic_matrix(analysis_dir, outdir)
    target_comparator(analysis_dir, outdir)
    reader_ladder(analysis_dir, outdir)
    reader_pair_heatmap(analysis_dir, outdir)


if __name__ == "__main__":
    main()
