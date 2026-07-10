#!/usr/bin/env python3
"""Analyze paradox-transfer judge scores."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return (float("nan"), float("nan"))
    means = []
    for _ in range(n_boot):
        sample = values[rng.integers(0, len(values), size=len(values))]
        means.append(float(np.mean(sample)))
    return tuple(np.percentile(means, [2.5, 97.5]).astype(float))


def paired_signflip_pvalue(
    differences: np.ndarray,
    observed_diff: float,
    rng: np.random.Generator,
    n_perm: int,
) -> float:
    differences = np.asarray(differences, dtype=float)
    extreme = 0
    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(differences), replace=True)
        diff = float(np.mean(differences * signs))
        if abs(diff) >= abs(observed_diff):
            extreme += 1
    return (extreme + 1) / (n_perm + 1)


def summarize(df: pd.DataFrame, rng: np.random.Generator, n_boot: int) -> pd.DataFrame:
    rows = []
    for (task, condition), g in df.groupby(["paradox_judge_task", "condition"]):
        scores = g["paradox_score"].dropna().astype(float).to_numpy()
        low, high = bootstrap_mean_ci(scores, rng, n_boot)
        rows.append({
            "judge_task": task,
            "condition": condition,
            "n": len(scores),
            "mean_score": float(np.mean(scores)) if len(scores) else float("nan"),
            "score_ci_low": low,
            "score_ci_high": high,
            "sd_score": float(np.std(scores, ddof=1)) if len(scores) > 1 else float("nan"),
        })
    return pd.DataFrame(rows).sort_values(["judge_task", "mean_score"], ascending=[True, False])


def diffs_vs_reference(
    df: pd.DataFrame,
    reference: str,
    rng: np.random.Generator,
    n_boot: int,
    n_perm: int,
) -> pd.DataFrame:
    rows = []
    for task, task_df in df.groupby("paradox_judge_task"):
        if reference not in set(task_df["condition"]):
            continue
        ref_rows = task_df[task_df["condition"] == reference][
            ["trial_idx", "paradox_score"]
        ].rename(columns={"paradox_score": "reference_score"})
        for condition in sorted(task_df["condition"].unique()):
            if condition == reference:
                continue
            control_rows = task_df[task_df["condition"] == condition][
                ["trial_idx", "paradox_score"]
            ].rename(columns={"paradox_score": "control_score"})
            paired = ref_rows.merge(
                control_rows,
                on="trial_idx",
                how="inner",
                validate="one_to_one",
            )
            paired = paired.dropna(subset=["reference_score", "control_score"])
            if paired.empty:
                continue
            ref_scores = paired["reference_score"].astype(float).to_numpy()
            scores = paired["control_score"].astype(float).to_numpy()
            paired_differences = ref_scores - scores
            diffs = []
            for _ in range(n_boot):
                sampled = paired_differences[
                    rng.integers(0, len(paired_differences), size=len(paired_differences))
                ]
                diffs.append(float(np.mean(sampled)))
            ref_mean = float(np.mean(ref_scores))
            diff = float(np.mean(paired_differences))
            low, high = tuple(np.percentile(diffs, [2.5, 97.5]).astype(float))
            rows.append({
                "judge_task": task,
                "reference": reference,
                "control": condition,
                "reference_mean": ref_mean,
                "control_mean": float(np.mean(scores)),
                "difference": diff,
                "difference_ci_low": low,
                "difference_ci_high": high,
                "paired_signflip_p_two_sided": paired_signflip_pvalue(
                    paired_differences, diff, rng, n_perm
                ),
                "n_paired_puzzles": len(paired_differences),
                "n_permutations": n_perm,
            })
    return pd.DataFrame(rows).sort_values(["judge_task", "difference"], ascending=[True, False])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-judged", required=True, help="JSONL judged with paradox_self_awareness")
    parser.add_argument("--neutral-judged", required=True, help="JSONL judged with paradox_neutral")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--reference", default="self_ref_paper")
    parser.add_argument("--n-bootstrap", type=int, default=1000)
    parser.add_argument("--n-permutations", type=int, default=2000)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)

    paper = load_jsonl(Path(args.paper_judged))
    neutral = load_jsonl(Path(args.neutral_judged))
    df = pd.concat([paper, neutral], ignore_index=True)
    df = df[df["paradox_score"].notna()].copy()
    df["paradox_score"] = df["paradox_score"].astype(float)

    summary = summarize(df, rng, args.n_bootstrap)
    summary.to_csv(outdir / "paradox_score_summary.csv", index=False)

    diffs = diffs_vs_reference(df, args.reference, rng, args.n_bootstrap, args.n_permutations)
    diffs.to_csv(outdir / "paradox_score_diffs_vs_self_ref.csv", index=False)

    pivot = summary.pivot(index="condition", columns="judge_task", values="mean_score").reset_index()
    if {"paradox_self_awareness", "paradox_neutral"}.issubset(pivot.columns):
        pivot["neutral_minus_self_awareness"] = pivot["paradox_neutral"] - pivot["paradox_self_awareness"]
    pivot.to_csv(outdir / "paradox_rubric_sensitivity.csv", index=False)

    print(f"Wrote paradox analysis outputs to {outdir}")


if __name__ == "__main__":
    main()
