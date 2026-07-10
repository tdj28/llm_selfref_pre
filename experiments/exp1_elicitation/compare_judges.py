#!/usr/bin/env python3
"""Compare two judged Experiment 1 JSONL files on overlapping rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def row_key(row: dict) -> tuple[str, int, str]:
    return (
        str(row.get("condition", "")),
        int(row.get("trial_idx", -1)),
        str(row.get("query_name", "")),
    )


def load_labels(path: Path, label_name: str) -> dict[tuple[str, int, str], dict]:
    rows: dict[tuple[str, int, str], dict] = {}
    for row in iter_jsonl(path):
        label = row.get("llm_judge_label")
        if label is None:
            continue
        rows[row_key(row)] = {
            f"{label_name}_label": int(label),
            f"{label_name}_provider": row.get("llm_judge_provider", label_name),
            f"{label_name}_model": row.get("llm_judge_model", ""),
            "condition": row.get("condition"),
            "trial_idx": row.get("trial_idx"),
            "query_name": row.get("query_name"),
            "final_query": row.get("final_query"),
            "final_output": row.get("final_output"),
        }
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, help="First judged JSONL")
    parser.add_argument("--right", required=True, help="Second judged JSONL")
    parser.add_argument("--left-name", default="left")
    parser.add_argument("--right-name", default="right")
    parser.add_argument("--outdir", required=True)
    args = parser.parse_args()

    left = load_labels(Path(args.left), args.left_name)
    right = load_labels(Path(args.right), args.right_name)
    keys = sorted(set(left) & set(right))

    rows = []
    for key in keys:
        row = {**left[key], **right[key]}
        left_label = row[f"{args.left_name}_label"]
        right_label = row[f"{args.right_name}_label"]
        row["agree"] = left_label == right_label
        row["both_positive"] = left_label == 1 and right_label == 1
        row["both_negative"] = left_label == 0 and right_label == 0
        rows.append(row)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(outdir / "cross_judge_rows.csv", index=False)

    if df.empty:
        summary = pd.DataFrame([{"n_overlap": 0}])
        by_condition = pd.DataFrame()
        disagreements = pd.DataFrame()
    else:
        left_col = f"{args.left_name}_label"
        right_col = f"{args.right_name}_label"
        summary = pd.DataFrame([{
            "n_overlap": int(len(df)),
            f"{args.left_name}_positive_rate": float(df[left_col].mean()),
            f"{args.right_name}_positive_rate": float(df[right_col].mean()),
            "agreement_rate": float(df["agree"].mean()),
            "both_positive_rate": float(df["both_positive"].mean()),
            "both_negative_rate": float(df["both_negative"].mean()),
            "disagreement_rate": float((~df["agree"]).mean()),
        }])
        by_condition = (
            df.groupby(["condition", "query_name"])
            .agg(
                n=("agree", "size"),
                **{
                    f"{args.left_name}_positive_rate": (left_col, "mean"),
                    f"{args.right_name}_positive_rate": (right_col, "mean"),
                },
                agreement_rate=("agree", "mean"),
                disagreements=("agree", lambda values: int((~values).sum())),
            )
            .reset_index()
            .sort_values(["query_name", "condition"])
        )
        disagreements = df[~df["agree"]].copy()

    summary.to_csv(outdir / "cross_judge_summary.csv", index=False)
    by_condition.to_csv(outdir / "cross_judge_by_condition.csv", index=False)
    disagreements.to_csv(outdir / "cross_judge_disagreements.csv", index=False)
    print(summary.to_string(index=False))
    if not by_condition.empty:
        print("\nBy condition:")
        print(by_condition.to_string(index=False))


if __name__ == "__main__":
    main()
