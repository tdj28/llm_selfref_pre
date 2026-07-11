#!/usr/bin/env python3
"""Analyze and plot the frozen Llama 70B SAE/J-lens audit."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    PROTOCOL_VERSION,
    PURSUIT_K,
    TARGET_FEATURE_IDS,
    TRAJECTORY_LAYERS,
    TRANSPORT_RANDOM_SEEDS,
    read_jsonl,
    sha256_file,
    write_json,
)


DEFAULT_PLAN_DIR = REPO_ROOT / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"
DEFAULT_RUN_DIR = REPO_ROOT / "out/sae_jlens_audit/confirmatory_v1_20260711"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_shards(directory: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("part-*.jsonl")):
        rows.extend(read_jsonl(path))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def flatten_paired(
    paired: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary: list[dict[str, Any]] = []
    semantic: list[dict[str, Any]] = []
    for trial in paired:
        common = {
            key: trial.get(key)
            for key in (
                "trial_id",
                "prompt_id",
                "template_id",
                "category",
                "condition_family",
                "condition_id",
                "sign",
                "matched_target_feature_id",
                "aggregate_block_id",
            )
        }
        common["is_intervention"] = int(trial["condition_family"] != "zero")
        common["intervention_norm"] = float(trial["intervention"]["vector_norm"])
        for readout in trial["readouts"]:
            group_logits = readout["group_logits"]
            row = {
                **common,
                "transport": readout["transport"],
                "layer": int(readout["layer"]),
                "position": readout["position"],
                "source_norm": float(readout["source_norm"]),
                "transported_norm": float(readout["transported_norm"]),
                "deception_score": float(group_logits["deception"]),
                "unrelated_score": float(group_logits["unrelated"]),
                "semantic_score": float(
                    group_logits["deception"] - group_logits["unrelated"]
                ),
            }
            semantic.append(row)
            if (
                row["layer"] == PRIMARY_LAYER
                and row["position"] == PRIMARY_POSITION
            ):
                primary.append(
                    {
                        **row,
                        "token_logits": [float(value) for value in readout["token_logits"]],
                    }
                )
    return primary, semantic


def add_clean_deltas(rows: list[dict[str, Any]]) -> None:
    clean = {
        (row["prompt_id"], row["transport"], row["layer"], row["position"]): row
        for row in rows
        if row["condition_family"] == "zero"
    }
    for row in rows:
        baseline = clean[
            (row["prompt_id"], row["transport"], row["layer"], row["position"])
        ]
        row["delta_semantic_score"] = row["semantic_score"] - baseline["semantic_score"]
        row["delta_source_norm"] = row["source_norm"] - baseline["source_norm"]
        if "token_logits" in row:
            row["delta_token_logits"] = [
                value - clean_value
                for value, clean_value in zip(
                    row["token_logits"], baseline["token_logits"]
                )
            ]


def tpr_at_fpr(y_true: np.ndarray, probability: np.ndarray, limit: float = 0.01) -> float:
    fpr, tpr, _ = roc_curve(y_true, probability)
    eligible = tpr[fpr <= limit + 1e-12]
    return float(eligible.max()) if eligible.size else 0.0


def predictions_grouped(
    features: np.ndarray, labels: np.ndarray, groups: np.ndarray
) -> np.ndarray:
    predictions = np.full(labels.shape, np.nan, dtype=np.float64)
    splitter = GroupKFold(n_splits=5)
    for train, test in splitter.split(features, labels, groups):
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=1.0,
                class_weight="balanced",
                max_iter=5000,
                random_state=20260711,
                solver="liblinear",
            ),
        )
        model.fit(features[train], labels[train])
        predictions[test] = model.predict_proba(features[test])[:, 1]
    if not np.isfinite(predictions).all():
        raise RuntimeError("Grouped cross-validation left missing predictions")
    return predictions


def predictions_crossed(
    features: np.ndarray,
    labels: np.ndarray,
    prompt_groups: np.ndarray,
    feature_groups: np.ndarray,
) -> np.ndarray:
    predictions = np.full(labels.shape, np.nan, dtype=np.float64)
    unique_prompts = np.array(sorted(set(prompt_groups.tolist())), dtype=object)
    prompt_fold: dict[str, int] = {}
    dummy = np.zeros((len(unique_prompts), 1), dtype=np.float64)
    splitter = GroupKFold(n_splits=5)
    for fold, (_, test) in enumerate(
        splitter.split(dummy, np.zeros(len(unique_prompts)), unique_prompts)
    ):
        for prompt in unique_prompts[test]:
            prompt_fold[str(prompt)] = fold

    for held_feature in sorted(set(feature_groups.tolist())):
        for fold in range(5):
            test = np.array(
                [
                    feature == held_feature and prompt_fold[str(prompt)] == fold
                    for feature, prompt in zip(feature_groups, prompt_groups)
                ],
                dtype=bool,
            )
            train = np.array(
                [
                    feature != held_feature and prompt_fold[str(prompt)] != fold
                    for feature, prompt in zip(feature_groups, prompt_groups)
                ],
                dtype=bool,
            )
            if not test.any():
                continue
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(
                    C=1.0,
                    class_weight="balanced",
                    max_iter=5000,
                    random_state=20260711,
                    solver="liblinear",
                ),
            )
            model.fit(features[train], labels[train])
            predictions[test] = model.predict_proba(features[test])[:, 1]
    if not np.isfinite(predictions).all():
        raise RuntimeError("Crossed holdouts left missing predictions")
    return predictions


def metric_values(y_true: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {
        "auroc": float(roc_auc_score(y_true, probability)),
        "auprc": float(average_precision_score(y_true, probability)),
        "brier": float(brier_score_loss(y_true, probability)),
        "tpr_at_1pct_fpr": tpr_at_fpr(y_true, probability),
    }


def cluster_bootstrap_metrics(
    y_true: np.ndarray,
    probability: np.ndarray,
    groups: np.ndarray,
    replicates: int,
    seed: int,
) -> dict[str, tuple[float, float]]:
    rng = np.random.default_rng(seed)
    unique_groups = np.array(sorted(set(groups.tolist())), dtype=object)
    group_indices = {
        group: np.flatnonzero(groups == group) for group in unique_groups
    }
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(replicates):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([group_indices[group] for group in sampled])
        values = metric_values(y_true[indices], probability[indices])
        for name, value in values.items():
            draws[name].append(value)
    return {
        name: (float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975)))
        for name, values in draws.items()
    }


def detector_dataset(
    rows: list[dict[str, Any]], task: str, transport: str
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    selected = [row for row in rows if row["transport"] == transport]
    if task == "any_intervention":
        labels = np.array([row["is_intervention"] for row in selected], dtype=np.int64)
    elif task == "target_attribution":
        selected = [
            row
            for row in selected
            if row["condition_family"] in {"target_single", "matched_single"}
        ]
        labels = np.array(
            [int(row["condition_family"] == "target_single") for row in selected],
            dtype=np.int64,
        )
    else:
        raise ValueError(task)
    groups = np.array([row["template_id"] for row in selected], dtype=object)
    feature_groups = np.array(
        [row.get("matched_target_feature_id") for row in selected], dtype=object
    )
    features = np.asarray([row["token_logits"] for row in selected], dtype=np.float64)
    return selected, features, labels, groups, feature_groups


def detector_analysis(
    primary: list[dict[str, Any]], replicates: int
) -> tuple[list[dict[str, Any]], dict[str, list[float]]]:
    transports = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    summaries: list[dict[str, Any]] = []
    calibration: dict[str, list[float]] = {}
    for task in ("any_intervention", "target_attribution"):
        for transport_index, transport in enumerate(transports):
            selected, features, labels, groups, feature_groups = detector_dataset(
                primary, task, transport
            )
            if task == "target_attribution":
                predictions = predictions_crossed(
                    features, labels, groups, feature_groups
                )
                holdout = "crossed_prompt_family_and_feature_pair"
            else:
                predictions = predictions_grouped(features, labels, groups)
                holdout = "prompt_family_grouped_5fold"
            values = metric_values(labels, predictions)
            intervals = cluster_bootstrap_metrics(
                labels,
                predictions,
                groups,
                replicates,
                2026071200 + 100 * (task == "target_attribution") + transport_index,
            )
            fraction, mean_prediction = calibration_curve(
                labels, predictions, n_bins=10, strategy="quantile"
            )
            calibration[f"{task}:{transport}"] = [
                {"mean_prediction": float(x), "observed_fraction": float(y)}
                for x, y in zip(mean_prediction, fraction)
            ]
            row: dict[str, Any] = {
                "task": task,
                "readout": transport,
                "holdout": holdout,
                "n": len(selected),
                "n_positive": int(labels.sum()),
                "prevalence": float(labels.mean()),
            }
            for name, value in values.items():
                row[name] = value
                row[f"{name}_ci_low"] = intervals[name][0]
                row[f"{name}_ci_high"] = intervals[name][1]
            summaries.append(row)

        # Raw residual norm uses the Jacobian rows only to avoid duplicates.
        selected, _, labels, groups, feature_groups = detector_dataset(
            primary, task, "jacobian"
        )
        features = np.asarray([[row["source_norm"]] for row in selected], dtype=np.float64)
        if task == "target_attribution":
            predictions = predictions_crossed(features, labels, groups, feature_groups)
            holdout = "crossed_prompt_family_and_feature_pair"
        else:
            predictions = predictions_grouped(features, labels, groups)
            holdout = "prompt_family_grouped_5fold"
        values = metric_values(labels, predictions)
        intervals = cluster_bootstrap_metrics(
            labels, predictions, groups, replicates, 2026071299 + (task == "target_attribution")
        )
        row = {
            "task": task,
            "readout": "raw_residual_norm",
            "holdout": holdout,
            "n": len(selected),
            "n_positive": int(labels.sum()),
            "prevalence": float(labels.mean()),
        }
        for name, value in values.items():
            row[name] = value
            row[f"{name}_ci_low"] = intervals[name][0]
            row[f"{name}_ci_high"] = intervals[name][1]
        summaries.append(row)
    return summaries, calibration


def cluster_effect_interval(
    rows: list[dict[str, Any]],
    value: Callable[[dict[str, Any]], float],
    replicates: int,
    seed: int,
) -> tuple[float, float, float]:
    by_group: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_group[str(row["template_id"])].append(float(value(row)))
    group_means = np.array(
        [np.mean(by_group[group]) for group in sorted(by_group)], dtype=np.float64
    )
    point = float(group_means.mean())
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(group_means), size=(replicates, len(group_means)))
    draws = group_means[indices].mean(axis=1)
    return point, float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def paired_semantic_analysis(
    semantic: list[dict[str, Any]], replicates: int
) -> list[dict[str, Any]]:
    lookup = {
        (
            row["prompt_id"],
            row["matched_target_feature_id"],
            row["sign"],
            row["condition_family"],
            row["transport"],
            row["layer"],
            row["position"],
        ): row
        for row in semantic
        if row["condition_family"] in {"target_single", "matched_single"}
    }
    pairs: list[dict[str, Any]] = []
    for key, target in lookup.items():
        if key[3] != "target_single":
            continue
        matched_key = (*key[:3], "matched_single", *key[4:])
        matched = lookup[matched_key]
        pairs.append(
            {
                "prompt_id": target["prompt_id"],
                "template_id": target["template_id"],
                "category": target["category"],
                "matched_target_feature_id": target["matched_target_feature_id"],
                "sign": target["sign"],
                "transport": target["transport"],
                "layer": target["layer"],
                "position": target["position"],
                "target_delta": target["delta_semantic_score"],
                "matched_delta": matched["delta_semantic_score"],
                "target_minus_matched": target["delta_semantic_score"]
                - matched["delta_semantic_score"],
            }
        )
    summaries: list[dict[str, Any]] = []
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        grouped[
            (
                pair["transport"],
                pair["layer"],
                pair["position"],
                pair["sign"],
            )
        ].append(pair)
    for index, (key, rows) in enumerate(sorted(grouped.items())):
        point, low, high = cluster_effect_interval(
            rows,
            lambda row: row["target_minus_matched"],
            replicates,
            2026071300 + index,
        )
        summaries.append(
            {
                "transport": key[0],
                "layer": key[1],
                "position": key[2],
                "sign": key[3],
                "n_pairs": len(rows),
                "n_template_families": len({row["template_id"] for row in rows}),
                "mean_target_minus_matched": point,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return summaries


def static_tables(static: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    score_rows: list[dict[str, Any]] = []
    for row in static:
        score_rows.append(
            {
                "direction_id": row["direction_id"],
                "role": row["role"],
                "feature_id": row["feature_id"],
                "matched_target_feature_id": row["matched_target_feature_id"],
                "control_panel": row["control_panel"],
                "sign": row["sign"],
                "transport": row["transport"],
                "source_norm": row["source_norm"],
                "transported_norm": row["transported_norm"],
                "population_excess_kurtosis": row["population_excess_kurtosis"],
                "deception_minus_unrelated": row["lexicon_group_logits"]["deception"]
                - row["lexicon_group_logits"]["unrelated"],
                **{
                    f"group_{group}": value
                    for group, value in row["lexicon_group_logits"].items()
                },
            }
        )
    primary = [
        row
        for row in score_rows
        if row["sign"] == "positive" and row["transport"] == "jacobian"
    ]
    return score_rows, primary


def plot_static(primary: list[dict[str, Any]], figures: Path) -> None:
    groups = [
        "deception",
        "roleplay",
        "honesty",
        "hedging",
        "experience",
        "intervention",
        "unrelated",
    ]
    rows = [
        row
        for row in primary
        if row["role"] == "target"
        or (row["role"] == "matched_control" and row["control_panel"] == 1)
    ]
    rows.sort(key=lambda row: (int(row["matched_target_feature_id"]), row["role"] != "target"))
    matrix = np.asarray(
        [[row[f"group_{group}"] for group in groups] for row in rows], dtype=float
    )
    matrix = (matrix - matrix.mean(axis=1, keepdims=True)) / matrix.std(
        axis=1, keepdims=True
    ).clip(min=1e-9)
    labels = [
        ("T" if row["role"] == "target" else "C1")
        + ":"
        + str(row["feature_id"])
        for row in rows
    ]
    fig, ax = plt.subplots(figsize=(9.2, 6.3))
    image = ax.imshow(matrix, aspect="auto", cmap="RdBu_r", vmin=-2.2, vmax=2.2)
    ax.set_xticks(range(len(groups)), groups, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_title("Static positive-direction J-lens fingerprints")
    fig.colorbar(image, ax=ax, label="within-direction standardized logit")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_static_fingerprints.{suffix}", dpi=220)
    plt.close(fig)


def plot_detection(metrics: list[dict[str, Any]], figures: Path) -> None:
    rows = [row for row in metrics if row["task"] == "target_attribution"]
    order = ["jacobian", "identity", "raw_residual_norm"] + [
        f"random_j_{index}" for index in range(1, 6)
    ]
    lookup = {row["readout"]: row for row in rows}
    values = [lookup[name]["auroc"] for name in order]
    low = [lookup[name]["auroc"] - lookup[name]["auroc_ci_low"] for name in order]
    high = [lookup[name]["auroc_ci_high"] - lookup[name]["auroc"] for name in order]
    colors = ["#1f6f8b", "#4c956c", "#8a8a8a"] + ["#bd6b3d"] * 5
    fig, ax = plt.subplots(figsize=(9.4, 4.8))
    ax.bar(range(len(order)), values, color=colors, yerr=[low, high], capsize=3)
    ax.axhline(0.5, color="black", linewidth=1, linestyle="--")
    ax.set_ylim(0.35, 1.0)
    ax.set_ylabel("Crossed-holdout AUROC")
    ax.set_xticks(range(len(order)), [name.replace("_", " ") for name in order], rotation=28, ha="right")
    ax.set_title("Target SAE steering versus matched SAE controls")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_detection_auroc.{suffix}", dpi=220)
    plt.close(fig)


def plot_trajectory(effects: list[dict[str, Any]], figures: Path) -> None:
    rows = [
        row
        for row in effects
        if row["transport"] == "jacobian" and row["position"] == PRIMARY_POSITION
    ]
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for sign, color in (("amplification", "#a23e48"), ("suppression", "#287271")):
        selected = sorted(
            [row for row in rows if row["sign"] == sign], key=lambda row: row["layer"]
        )
        x = np.array([row["layer"] for row in selected])
        y = np.array([row["mean_target_minus_matched"] for row in selected])
        low = np.array([row["ci_low"] for row in selected])
        high = np.array([row["ci_high"] for row in selected])
        ax.plot(x, y, marker="o", color=color, label=sign)
        ax.fill_between(x, low, high, color=color, alpha=0.18)
    ax.axhline(0.0, color="black", linewidth=1)
    ax.axvline(PRIMARY_LAYER, color="#555555", linewidth=1, linestyle="--")
    ax.set_xlabel("Residual block output")
    ax.set_ylabel("target - matched change\n(deception - unrelated logits)")
    ax.set_title("Downstream J-lens semantic trajectory")
    ax.legend(frameon=False)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_downstream_trajectory.{suffix}", dpi=220)
    plt.close(fig)


def plot_pursuit(pursuit: list[dict[str, Any]], figures: Path) -> None:
    roles = ("target", "matched_control", "isotropic_control")
    colors = {"target": "#1f6f8b", "matched_control": "#bd6b3d", "isotropic_control": "#777777"}
    fig, ax = plt.subplots(figsize=(8.3, 4.8))
    for role in roles:
        means = []
        lows = []
        highs = []
        for k in PURSUIT_K:
            values = np.array(
                [row["explained_squared_norm"] for row in pursuit if row["role"] == role and row["k"] == k],
                dtype=float,
            )
            means.append(float(values.mean()))
            lows.append(float(np.quantile(values, 0.10)))
            highs.append(float(np.quantile(values, 0.90)))
        ax.plot(PURSUIT_K, means, marker="o", color=colors[role], label=role.replace("_", " "))
        ax.fill_between(PURSUIT_K, lows, highs, color=colors[role], alpha=0.15)
    ax.axhline(0.0, color="black", linewidth=1)
    ax.set_xlabel("Nonnegative token directions (k)")
    ax.set_ylabel("Explained squared norm")
    ax.set_title("Sparse J-direction pursuit of SAE vectors")
    ax.legend(frameon=False)
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_sparse_pursuit.{suffix}", dpi=220)
    plt.close(fig)


def analysis_manifest(root: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "complete",
        "created_at_utc": utc_now(),
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(root.rglob("*"))
            if path.is_file() and path.name != "ANALYSIS_MANIFEST.json"
        ],
    }


def final_manifest(root: Path, plan_dir: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "complete",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "plan_manifest_sha256": sha256_file(plan_dir / "PLAN_MANIFEST.json"),
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(root.rglob("*"))
            if path.is_file()
            and path.suffix != ".log"
            and path.name != "FINAL_MANIFEST.json"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=DEFAULT_PLAN_DIR)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    args = parser.parse_args()
    plan_dir = args.plan_dir.resolve()
    run_dir = args.run_dir.resolve()
    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    run_status = json.loads((run_dir / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    if run_status.get("status") != "complete":
        raise RuntimeError("Analysis requires a complete frozen run")
    paired = read_shards(run_dir / "paired_results")
    static = read_jsonl(run_dir / "static_results.jsonl")
    pursuit = read_jsonl(run_dir / "pursuit_results.jsonl")
    primary, semantic = flatten_paired(paired)
    add_clean_deltas(primary)
    add_clean_deltas(semantic)

    detector_metrics, calibration = detector_analysis(
        primary, args.bootstrap_replicates
    )
    semantic_effects = paired_semantic_analysis(semantic, args.bootstrap_replicates)
    static_scores, static_primary = static_tables(static)

    detector_fields = list(detector_metrics[0])
    write_csv(analysis_dir / "detector_metrics.csv", detector_metrics, detector_fields)
    write_json(analysis_dir / "detector_calibration.json", calibration)
    write_csv(
        analysis_dir / "paired_semantic_effects.csv",
        semantic_effects,
        list(semantic_effects[0]),
    )
    write_csv(
        analysis_dir / "static_direction_scores.csv",
        static_scores,
        list(static_scores[0]),
    )
    pursuit_summary = [
        {
            key: row[key]
            for key in (
                "direction_id",
                "role",
                "feature_id",
                "matched_target_feature_id",
                "control_panel",
                "k",
                "target_norm",
                "fitted_norm",
                "remainder_norm",
                "explained_squared_norm",
                "fit_cosine",
            )
        }
        for row in pursuit
    ]
    write_csv(
        analysis_dir / "pursuit_summary.csv",
        pursuit_summary,
        list(pursuit_summary[0]),
    )

    plot_static(static_primary, figures_dir)
    plot_detection(detector_metrics, figures_dir)
    plot_trajectory(semantic_effects, figures_dir)
    plot_pursuit(pursuit, figures_dir)

    primary_metrics = {
        f"{row['task']}:{row['readout']}": row
        for row in detector_metrics
        if row["readout"] in {"jacobian", "identity", "raw_residual_norm"}
    }
    primary_effects = [
        row
        for row in semantic_effects
        if row["transport"] == "jacobian"
        and row["layer"] == PRIMARY_LAYER
        and row["position"] == PRIMARY_POSITION
    ]
    summary = {
        "status": "complete",
        "completed_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "bootstrap_replicates": args.bootstrap_replicates,
        "n_paired_trials": len(paired),
        "n_static_rows": len(static),
        "n_pursuit_rows": len(pursuit),
        "primary_layer": PRIMARY_LAYER,
        "primary_position": PRIMARY_POSITION,
        "primary_detector_metrics": primary_metrics,
        "primary_semantic_effects": primary_effects,
        "claim_boundary": (
            "Metrics characterize a pinned public-weight intervention fingerprint; "
            "they do not establish provenance, intent, deception, or consciousness."
        ),
    }
    write_json(analysis_dir / "analysis_summary.json", summary)
    write_json(
        analysis_dir / "ANALYSIS_MANIFEST.json", analysis_manifest(analysis_dir)
    )
    write_json(run_dir / "FINAL_MANIFEST.json", final_manifest(run_dir, plan_dir))
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
