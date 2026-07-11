#!/usr/bin/env python3
"""Post-run paired-reference sensitivity for the SAE/J-lens audit.

This analysis was added after the confirmatory post-state outcomes were opened.
It uses the already frozen deception-minus-unrelated score and intervention
sign; it does not select tokens, features, layers, or positions from outcomes.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.analyze_sae_jlens_audit import (  # noqa: E402
    add_clean_deltas,
    flatten_paired,
    read_shards,
)
from experiments.exp2_sae.sae_jlens_protocol import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    PRIMARY_LAYER,
    PRIMARY_POSITION,
    PROTOCOL_VERSION,
    TARGET_FEATURE_IDS,
    TRANSPORT_RANDOM_SEEDS,
    sha256_file,
    write_json,
)


DEFAULT_RUN_DIR = REPO_ROOT / "out/sae_jlens_audit/confirmatory_v1_20260711"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def tpr_at_fpr(y_true: np.ndarray, score: np.ndarray, limit: float = 0.01) -> float:
    fpr, tpr, _ = roc_curve(y_true, score)
    eligible = tpr[fpr <= limit + 1e-12]
    return float(eligible.max()) if eligible.size else 0.0


def fixed_score_metrics(y_true: np.ndarray, score: np.ndarray) -> dict[str, float]:
    return {
        "auroc": float(roc_auc_score(y_true, score)),
        "auprc": float(average_precision_score(y_true, score)),
        "tpr_at_1pct_fpr": tpr_at_fpr(y_true, score),
    }


def cluster_bootstrap(
    rows: list[dict[str, Any]], replicates: int, seed: int
) -> dict[str, tuple[float, float]]:
    labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
    scores = np.asarray([row["score"] for row in rows], dtype=np.float64)
    groups = np.asarray([row["template_id"] for row in rows], dtype=object)
    unique_groups = np.asarray(sorted(set(groups.tolist())), dtype=object)
    group_indices = {
        group: np.flatnonzero(groups == group) for group in unique_groups
    }
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = defaultdict(list)
    for _ in range(replicates):
        sampled = rng.choice(unique_groups, size=len(unique_groups), replace=True)
        indices = np.concatenate([group_indices[group] for group in sampled])
        metrics = fixed_score_metrics(labels[indices], scores[indices])
        for name, value in metrics.items():
            draws[name].append(value)
    return {
        name: (float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975)))
        for name, values in draws.items()
    }


def score_rows(
    primary: list[dict[str, Any]], transport: str, score_mode: str
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in primary
        if row["transport"] == transport
        and row["condition_family"] in {"target_single", "matched_single"}
    ]
    scored: list[dict[str, Any]] = []
    for row in rows:
        delta = float(row["delta_semantic_score"])
        if score_mode == "known_sign":
            score = (1.0 if row["sign"] == "amplification" else -1.0) * delta
        elif score_mode == "unknown_sign_absolute":
            score = abs(delta)
        else:
            raise ValueError(score_mode)
        scored.append({
            "trial_id": row["trial_id"],
            "prompt_id": row["prompt_id"],
            "template_id": row["template_id"],
            "category": row["category"],
            "feature_id": int(row["matched_target_feature_id"]),
            "sign": row["sign"],
            "transport": transport,
            "score_mode": score_mode,
            "label": int(row["condition_family"] == "target_single"),
            "score": score,
        }
        )
    return scored


def summarize(
    rows: list[dict[str, Any]], replicates: int, seed: int
) -> dict[str, Any]:
    labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
    scores = np.asarray([row["score"] for row in rows], dtype=np.float64)
    point = fixed_score_metrics(labels, scores)
    intervals = cluster_bootstrap(rows, replicates, seed)
    result: dict[str, Any] = {
        "n": len(rows),
        "n_target": int(labels.sum()),
        "n_matched": int((1 - labels).sum()),
        "n_template_families": len({row["template_id"] for row in rows}),
        "target_mean_score": float(scores[labels == 1].mean()),
        "matched_mean_score": float(scores[labels == 0].mean()),
        "target_minus_matched_mean": float(
            scores[labels == 1].mean() - scores[labels == 0].mean()
        ),
    }
    for name, value in point.items():
        result[name] = value
        result[f"{name}_ci_low"] = intervals[name][0]
        result[f"{name}_ci_high"] = intervals[name][1]
    return result


def plot_overall(rows: list[dict[str, Any]], figures: Path) -> None:
    order = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    lookup = {(row["score_mode"], row["transport"]): row for row in rows}
    x = np.arange(len(order), dtype=float)
    width = 0.36
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    for offset, mode, color, label in (
        (-width / 2, "known_sign", "#1f6f8b", "known sign"),
        (width / 2, "unknown_sign_absolute", "#bd6b3d", "unknown sign: absolute delta"),
    ):
        values = [lookup[(mode, name)]["auroc"] for name in order]
        low = [
            max(0.0, lookup[(mode, name)]["auroc"] - lookup[(mode, name)]["auroc_ci_low"])
            for name in order
        ]
        high = [
            max(0.0, lookup[(mode, name)]["auroc_ci_high"] - lookup[(mode, name)]["auroc"])
            for name in order
        ]
        ax.bar(
            x + offset,
            values,
            width=width,
            color=color,
            yerr=[low, high],
            capsize=2,
            label=label,
        )
    ax.axhline(0.5, color="black", linewidth=1, linestyle="--")
    ax.set_ylim(0.2, 1.0)
    ax.set_ylabel("Fixed-score AUROC")
    ax.set_xticks(x, [name.replace("_", " ") for name in order], rotation=28, ha="right")
    ax.set_title("Target attribution with a paired clean reference")
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_paired_reference_auc.{suffix}", dpi=220)
    plt.close(fig)


def plot_features(rows: list[dict[str, Any]], figures: Path) -> None:
    rows = sorted(rows, key=lambda row: int(row["feature_id"]))
    values = [row["auroc"] for row in rows]
    low = [max(0.0, row["auroc"] - row["auroc_ci_low"]) for row in rows]
    high = [max(0.0, row["auroc_ci_high"] - row["auroc"]) for row in rows]
    colors = ["#1f6f8b" if value >= 0.5 else "#a23e48" for value in values]
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.bar(range(len(rows)), values, color=colors, yerr=[low, high], capsize=3)
    ax.axhline(0.5, color="black", linewidth=1, linestyle="--")
    ax.set_ylim(0.0, 1.05)
    ax.set_ylabel("Paired-reference J-score AUROC")
    ax.set_xticks(range(len(rows)), [str(row["feature_id"]) for row in rows])
    ax.set_xlabel("Target feature ID")
    ax.set_title("The aggregate fingerprint is not uniform across features")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(figures / f"sae_jlens_feature_heterogeneity.{suffix}", dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    analysis_dir = run_dir / "analysis"
    figures_dir = run_dir / "figures"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    paired = read_shards(run_dir / "paired_results")
    primary, _ = flatten_paired(paired)
    add_clean_deltas(primary)
    transports = ["jacobian", "identity"] + [
        f"random_j_{index}" for index in range(1, len(TRANSPORT_RANDOM_SEEDS) + 1)
    ]
    overall: list[dict[str, Any]] = []
    all_scores: dict[tuple[str, str], list[dict[str, Any]]] = {}
    score_modes = ("known_sign", "unknown_sign_absolute")
    for mode_index, score_mode in enumerate(score_modes):
        for transport_index, transport in enumerate(transports):
            rows = score_rows(primary, transport, score_mode)
            all_scores[(score_mode, transport)] = rows
            overall.append(
                {
                    "score_mode": score_mode,
                    "transport": transport,
                    **summarize(
                        rows,
                        args.bootstrap_replicates,
                        2026071400 + 100 * mode_index + transport_index,
                    ),
                }
            )
    feature_rows: list[dict[str, Any]] = []
    for index, feature_id in enumerate(TARGET_FEATURE_IDS):
        rows = [
            row
            for row in all_scores[("known_sign", "jacobian")]
            if row["feature_id"] == feature_id
        ]
        feature_rows.append(
            {
                "feature_id": feature_id,
                **summarize(rows, args.bootstrap_replicates, 2026071500 + index),
            }
        )

    write_csv(
        analysis_dir / "paired_reference_metrics.csv", overall, list(overall[0])
    )
    write_csv(
        analysis_dir / "paired_reference_feature_metrics.csv",
        feature_rows,
        list(feature_rows[0]),
    )
    plot_overall(overall, figures_dir)
    plot_features(feature_rows, figures_dir)
    manifest = {
        "status": "complete_posthoc_sensitivity",
        "created_at_utc": utc_now(),
        "protocol_version": PROTOCOL_VERSION,
        "bootstrap_replicates": args.bootstrap_replicates,
        "layer": PRIMARY_LAYER,
        "position": PRIMARY_POSITION,
        "scores": {
            "known_sign": "sign-adjusted paired change in deception-minus-unrelated logits",
            "unknown_sign_absolute": "absolute paired change in deception-minus-unrelated logits",
        },
        "timing": (
            "Added after confirmatory post-state outcomes were opened; uses the frozen "
            "lexicon score and is not a new confirmatory endpoint."
        ),
        "overall": overall,
        "features": feature_rows,
        "source_sha256": sha256_file(Path(__file__).resolve()),
    }
    write_json(analysis_dir / "paired_reference_sensitivity.json", manifest)
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
