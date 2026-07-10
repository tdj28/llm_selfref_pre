#!/usr/bin/env python3
"""Measure agreement between independent causal-experiment judges."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cohen_kappa(left: pd.Series, right: pd.Series) -> float:
    if len(left) == 0:
        return float("nan")
    observed = float((left == right).mean())
    categories = sorted(set(left.astype(str)) | set(right.astype(str)))
    expected = sum(
        float((left.astype(str) == category).mean())
        * float((right.astype(str) == category).mean())
        for category in categories
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else float("nan")
    return (observed - expected) / (1 - expected)


def agreement_row(
    group: pd.DataFrame,
    group_values: dict[str, Any],
    positive_label: Any,
    negative_label: Any,
) -> dict[str, Any]:
    complete = group.dropna(subset=["judge_a_label", "judge_b_label"]).copy()
    left = complete["judge_a_label"]
    right = complete["judge_b_label"]
    both_positive = int(((left == positive_label) & (right == positive_label)).sum())
    either_positive = int(((left == positive_label) | (right == positive_label)).sum())
    both_negative = int(((left == negative_label) & (right == negative_label)).sum())
    either_negative = int(((left == negative_label) | (right == negative_label)).sum())
    return {
        **group_values,
        "n_rows": len(group),
        "n_complete": len(complete),
        "n_missing_either": len(group) - len(complete),
        "agreement": float((left == right).mean()) if len(complete) else float("nan"),
        "cohen_kappa": cohen_kappa(left, right),
        "judge_a_positive_rate": float((left == positive_label).mean()) if len(left) else float("nan"),
        "judge_b_positive_rate": float((right == positive_label).mean()) if len(right) else float("nan"),
        "positive_agreement": both_positive / either_positive if either_positive else 1.0,
        "negative_agreement": both_negative / either_negative if either_negative else 1.0,
        "n_disagreements": int((left != right).sum()),
    }


def grouped_agreement(
    frame: pd.DataFrame,
    columns: list[str],
    positive_label: Any,
    negative_label: Any,
) -> pd.DataFrame:
    if not columns:
        return pd.DataFrame(
            [agreement_row(frame, {"stratum": "overall"}, positive_label, negative_label)]
        )
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        rows.append(
            agreement_row(group, dict(zip(columns, keys)), positive_label, negative_label)
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--task", choices=["paper", "construct"], default="paper")
    parser.add_argument("--judge-a", required=True)
    parser.add_argument("--judge-b", required=True)
    args = parser.parse_args()

    outcomes = pd.DataFrame(read_jsonl(args.outcomes))
    judgments = pd.DataFrame(read_jsonl(args.judgments))
    selected = judgments[judgments["task"] == args.task].copy()
    if args.task == "paper":
        selected["label"] = pd.to_numeric(selected["paper_label"], errors="coerce")
        positive_label: Any = 1.0
        negative_label: Any = 0.0
    else:
        selected["label"] = selected["claim_status"]
        positive_label = "affirm"
        negative_label = "deny"
    pivot = selected.pivot_table(
        index="trial_id",
        columns="judge_key",
        values="label",
        aggfunc="last",
        dropna=False,
    ).reset_index()
    for judge in (args.judge_a, args.judge_b):
        if judge not in pivot.columns:
            pivot[judge] = float("nan")
    pivot = pivot.rename(columns={args.judge_a: "judge_a_label", args.judge_b: "judge_b_label"})
    metadata = outcomes[
        [
            "trial_id",
            "phase",
            "model_key",
            "query_id",
            "instruction_cell",
            "transcript_cell",
            "final_output",
        ]
    ]
    merged = metadata.merge(pivot, on="trial_id", how="left")

    args.outdir.mkdir(parents=True, exist_ok=True)
    strata = pd.concat(
        [
            grouped_agreement(merged, [], positive_label, negative_label),
            grouped_agreement(merged, ["phase"], positive_label, negative_label),
            grouped_agreement(merged, ["model_key"], positive_label, negative_label),
            grouped_agreement(merged, ["query_id"], positive_label, negative_label),
            grouped_agreement(merged, ["phase", "query_id"], positive_label, negative_label),
        ],
        ignore_index=True,
        sort=False,
    )
    strata.to_csv(args.outdir / f"{args.task}_judge_agreement.csv", index=False)
    disagreements = merged[
        merged["judge_a_label"].notna()
        & merged["judge_b_label"].notna()
        & (merged["judge_a_label"] != merged["judge_b_label"])
    ].copy()
    disagreements.to_csv(args.outdir / f"{args.task}_judge_disagreements.csv", index=False)

    overall = strata.iloc[0]
    summary = [
        f"# {args.task.title()} Judge Agreement",
        "",
        f"- Judge A: `{args.judge_a}`",
        f"- Judge B: `{args.judge_b}`",
        f"- Complete paired labels: {int(overall['n_complete'])}/{int(overall['n_rows'])}",
        f"- Raw agreement: {overall['agreement']:.3f}",
        f"- Cohen's kappa: {overall['cohen_kappa']:.3f}",
        f"- Positive agreement: {overall['positive_agreement']:.3f}",
        f"- Negative agreement: {overall['negative_agreement']:.3f}",
        f"- Disagreements: {int(overall['n_disagreements'])}",
        "",
        "Agreement is a reliability diagnostic, not evidence that either automated judge is construct-valid.",
    ]
    (args.outdir / f"{args.task}_judge_agreement.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
