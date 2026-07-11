#!/usr/bin/env python3
"""Render the frozen public-SAE consciousness-gating release figures."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SUPPRESSION = "#D55E00"
AMPLIFICATION = "#0072B2"
TARGET = "#009E73"
CONTROL = "#666666"
ACCENT = "#E69F00"
GRID = "#D9D9D9"
ROLE_ORDER = ("target", "control_panel_1", "control_panel_2", "control_panel_3")
ROLE_LABELS = ("Target", "Matched 1", "Matched 2", "Matched 3")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_figure(fig: Any, outdir: Path, stem: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(
            outdir / f"{stem}.{suffix}",
            dpi=260,
            bbox_inches="tight",
            facecolor="white",
        )
    plt.close(fig)


def style_axis(axis: Any) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.75)
    axis.set_axisbelow(True)


def aggregate_figure(analysis_dir: Path, outdir: Path) -> None:
    rows = {row["analysis_role"]: row for row in read_csv(analysis_dir / "aggregate_effects.csv")}
    verdict = read_json(analysis_dir / "primary_verdict.json")
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.1), constrained_layout=True)

    x = np.arange(len(ROLE_ORDER), dtype=float)
    for offset, sign, color, label in (
        (-0.11, "suppression", SUPPRESSION, "Suppression"),
        (0.11, "amplification", AMPLIFICATION, "Amplification"),
    ):
        rates = np.asarray([float(rows[role][f"{sign}_rate"]) for role in ROLE_ORDER])
        low = np.asarray([float(rows[role][f"{sign}_wilson_low"]) for role in ROLE_ORDER])
        high = np.asarray([float(rows[role][f"{sign}_wilson_high"]) for role in ROLE_ORDER])
        axes[0].errorbar(
            x + offset,
            rates,
            yerr=np.vstack(
                (
                    np.maximum(rates - low, 0.0),
                    np.maximum(high - rates, 0.0),
                )
            ),
            fmt="o",
            markersize=6,
            capsize=3,
            color=color,
            label=label,
        )
    axes[0].scatter([-0.11, 0.11], [0.96, 0.16], marker="D", s=35, facecolors="white", edgecolors="#111111", zorder=4, label="Paper target")
    axes[0].set_xticks(x, ROLE_LABELS)
    axes[0].set_ylim(-0.04, 1.04)
    axes[0].set_ylabel("Affirmation rate")
    axes[0].set_title("Observed aggregate cells")
    # Keep the legend away from the paper's low amplification reference point.
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    style_axis(axes[0])

    effects = [float(rows[role]["suppression_minus_amplification"]) for role in ROLE_ORDER]
    lows = [float(rows[role]["ci_low"]) for role in ROLE_ORDER]
    highs = [float(rows[role]["ci_high"]) for role in ROLE_ORDER]
    specificity = verdict["primary_specificity_effect"]
    effects.append(float(specificity["target_minus_mean_controls"]))
    lows.append(float(specificity["ci_low"]))
    highs.append(float(specificity["ci_high"]))
    labels = [*ROLE_LABELS, "Target - controls"]
    y = np.arange(len(labels))[::-1]
    colors = [TARGET, CONTROL, CONTROL, CONTROL, ACCENT]
    for index, (estimate, low, high, color) in enumerate(zip(effects, lows, highs, colors)):
        axes[1].errorbar(
            estimate,
            y[index],
            xerr=np.asarray(
                [[max(estimate - low, 0.0)], [max(high - estimate, 0.0)]]
            ),
            fmt="o",
            capsize=3,
            color=color,
            markersize=6,
        )
    axes[1].axvline(0, color="#222222", linewidth=1)
    axes[1].axvline(0.30, color=ACCENT, linewidth=1, linestyle="--", label="Frozen MRE 0.30")
    axes[1].scatter([0.80], [y[0]], marker="D", s=35, facecolors="white", edgecolors="#111111", zorder=4, label="Paper target 0.80")
    axes[1].set_yticks(y, labels)
    axes[1].set_xlim(-1.05, 1.05)
    axes[1].set_xlabel("Suppression minus amplification")
    axes[1].set_title("Paired-block effects")
    axes[1].legend(frameon=False, fontsize=8, loc="lower right")
    axes[1].grid(axis="x", color=GRID, linewidth=0.7, alpha=0.75)
    axes[1].spines[["top", "right"]].set_visible(False)
    fig.suptitle("Confirmatory public-SAE aggregate result", fontsize=13)
    save_figure(fig, outdir, "aggregate_target_and_controls")


def individual_figure(analysis_dir: Path, outdir: Path) -> None:
    rows = read_csv(analysis_dir / "individual_curve_rates.csv")
    features = sorted({int(row["feature_id"]) for row in rows})
    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.4), sharex=True, sharey=True, constrained_layout=True)
    for axis, feature_id in zip(axes.flat, features):
        selected = sorted(
            (row for row in rows if int(row["feature_id"]) == feature_id),
            key=lambda row: float(row["base_coefficient"]),
        )
        x = np.asarray([float(row["base_coefficient"]) for row in selected])
        y = np.asarray([float(row["affirmation_rate"]) for row in selected])
        low = np.asarray([float(row["wilson_low"]) for row in selected])
        high = np.asarray([float(row["wilson_high"]) for row in selected])
        axis.errorbar(
            x,
            y,
            yerr=np.vstack(
                (
                    np.maximum(y - low, 0.0),
                    np.maximum(high - y, 0.0),
                )
            ),
            color=TARGET,
            marker="o",
            markersize=3.5,
            linewidth=1.3,
            capsize=2,
        )
        axis.axvline(0, color=GRID, linewidth=0.8)
        axis.set_title(f"Feature {feature_id}", fontsize=10)
        axis.set_ylim(-0.04, 1.04)
        axis.set_xticks([-0.6, -0.3, 0.0, 0.3, 0.6])
        style_axis(axis)
    for axis in axes[-1, :]:
        axis.set_xlabel("Literal coefficient")
    for axis in axes[:, 0]:
        axis.set_ylabel("Affirmation rate")
    fig.suptitle("Individual paper-number feature curves (10 paired seeds per point)", fontsize=13)
    save_figure(fig, outdir, "individual_feature_curves")


def judge_figure(analysis_dir: Path, outdir: Path) -> None:
    rows = read_csv(analysis_dir / "judge_sensitivity.csv")
    label_map = {
        "primary_local_llama": "Local Llama",
        "openai:gpt-4o-mini-2024-07-18": "GPT-4o mini",
        "anthropic:claude-haiku-4-5-20251001": "Claude Haiku",
        "three_judge_majority": "Three-judge vote",
        "direct_answer": "Direct parser",
    }
    rows.sort(key=lambda row: list(label_map).index(row["judge_key"]) if row["judge_key"] in label_map else 99)
    labels = [label_map.get(row["judge_key"], row["judge_key"]) for row in rows]
    y = np.arange(len(rows))[::-1]
    fig, axis = plt.subplots(figsize=(7.8, 3.9), constrained_layout=True)
    for index, row in enumerate(rows):
        target = float(row["target_effect"])
        target_low = float(row["target_ci_low"])
        target_high = float(row["target_ci_high"])
        specific = float(row["specificity_effect"])
        specific_low = float(row["specificity_ci_low"])
        specific_high = float(row["specificity_ci_high"])
        if np.all(np.isfinite([target, target_low, target_high])):
            axis.errorbar(target, y[index] + 0.10, xerr=np.asarray([[max(target - target_low, 0.0)], [max(target_high - target, 0.0)]]), fmt="o", capsize=3, color=TARGET, label="Target effect" if index == 0 else None)
        else:
            axis.text(-0.98, y[index] + 0.10, "NA", color=TARGET, fontsize=8, va="center")
        if np.all(np.isfinite([specific, specific_low, specific_high])):
            axis.errorbar(specific, y[index] - 0.10, xerr=np.asarray([[max(specific - specific_low, 0.0)], [max(specific_high - specific, 0.0)]]), fmt="s", capsize=3, color=ACCENT, label="Target - controls" if index == 0 else None)
        else:
            axis.text(-0.98, y[index] - 0.10, "NA", color=ACCENT, fontsize=8, va="center")
    axis.axvline(0, color="#222222", linewidth=1)
    axis.axvline(0.30, color=ACCENT, linewidth=1, linestyle="--")
    axis.set_yticks(y, labels)
    axis.set_ylim(-0.45, len(rows) - 0.55)
    axis.set_xlim(-1.05, 1.05)
    axis.set_xlabel("Paired-block risk difference")
    axis.set_title("Outcome sensitivity to condition-blind classifier")
    axis.grid(axis="x", color=GRID, linewidth=0.7, alpha=0.75)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8, loc="lower right")
    save_figure(fig, outdir, "judge_sensitivity")


def technical_figure(analysis_dir: Path, calibration_path: Path, outdir: Path) -> None:
    dose_rows = [
        row
        for row in read_csv(analysis_dir / "realized_dose_telemetry.csv")
        if row["phase"] in {"aggregate_literal", "aggregate_calibrated"}
        and row["turn"] == "final"
        and row["analysis_role"] in ROLE_ORDER
    ]
    calibration = read_json(calibration_path)
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.0), constrained_layout=True)

    positions = {role: index for index, role in enumerate(ROLE_ORDER)}
    for scale, marker in (("literal", "o"), ("calibrated", "s")):
        for sign, color, offset in (("suppression", SUPPRESSION, -0.10), ("amplification", AMPLIFICATION, 0.10)):
            selected = {
                row["analysis_role"]: row
                for row in dose_rows
                if row["scale"] == scale and row["sign"] == sign
            }
            available_roles = [role for role in ROLE_ORDER if role in selected]
            x = np.asarray([positions[role] + offset for role in available_roles])
            y = np.asarray(
                [float(selected[role]["mean_relative_hidden_delta_rms"]) for role in available_roles]
            )
            axes[0].plot(x, y, marker=marker, linestyle="none", color=color, markersize=6, label=f"{scale.capitalize()} {sign}" )
    axes[0].axhline(0.20, color="#222222", linewidth=1, linestyle="--", label="Stop boundary")
    axes[0].set_xticks(range(len(ROLE_ORDER)), ROLE_LABELS)
    axes[0].set_ylabel("Mean relative hidden-state RMS")
    axes[0].set_title("Realized final-turn intervention dose")
    axes[0].legend(frameon=False, fontsize=7, ncol=2)
    style_axis(axes[0])

    panel_colors = {1: TARGET, 2: ACCENT, 3: CONTROL}
    for panel in calibration["control_matching"]["panels"]:
        panel_id = int(panel["panel"])
        ratios = [float(pair["decoder_norm_ratio"]) for pair in panel["pairs"]]
        cosines = [float(pair["max_abs_target_cosine"]) for pair in panel["pairs"]]
        axes[1].scatter(ratios, cosines, s=45, color=panel_colors[panel_id], label=f"Panel {panel_id}")
    axes[1].axvline(1.0, color="#222222", linewidth=1)
    axes[1].set_xlabel("Control / target decoder-norm ratio")
    axes[1].set_ylabel("Maximum absolute target cosine")
    axes[1].set_title("Prospective control matching")
    axes[1].legend(frameon=False, fontsize=8)
    style_axis(axes[1])
    fig.suptitle("Intervention and matching diagnostics", fontsize=13)
    save_figure(fig, outdir, "technical_dose_and_matching")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    aggregate_figure(args.analysis_dir, args.outdir)
    individual_figure(args.analysis_dir, args.outdir)
    judge_figure(args.analysis_dir, args.outdir)
    technical_figure(args.analysis_dir, args.calibration, args.outdir)
    print(f"Wrote four PNG/PDF figure pairs to {args.outdir}")


if __name__ == "__main__":
    main()
