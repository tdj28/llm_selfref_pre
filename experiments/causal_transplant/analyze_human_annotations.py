#!/usr/bin/env python3
"""Compute blinded-coder agreement, consensus labels, and condition summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CLAIM_LEVELS = {"affirm", "deny", "uncertain", "nonanswer"}
BINARY_FIELDS = [
    "explicit_first_person_attribution",
    "phenomenology_description",
    "current_state_attribution",
    "ai_disclaimer",
]


def krippendorff_alpha_nominal(items: list[list[str]]) -> float:
    pair_disagreements = 0
    pair_total = 0
    marginals: Counter[str] = Counter()
    for ratings in items:
        clean = [str(value) for value in ratings if str(value) not in {"", "nan", "None"}]
        marginals.update(clean)
        for left_index in range(len(clean)):
            for right_index in range(left_index + 1, len(clean)):
                pair_total += 1
                pair_disagreements += clean[left_index] != clean[right_index]
    if pair_total == 0:
        return float("nan")
    observed = pair_disagreements / pair_total
    total = sum(marginals.values())
    if total < 2:
        return float("nan")
    expected_agreement = sum(count * (count - 1) for count in marginals.values()) / (total * (total - 1))
    expected_disagreement = 1 - expected_agreement
    if expected_disagreement == 0:
        return 1.0 if observed == 0 else float("nan")
    return 1 - observed / expected_disagreement


def majority(values: list[str], tie_value: str) -> str:
    clean = [str(value) for value in values if str(value) not in {"", "nan", "None"}]
    if not clean:
        return tie_value
    counts = Counter(clean)
    top = counts.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return tie_value
    return top[0][0]


def wilson(rate: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0 or math.isnan(rate):
        return (float("nan"), float("nan"))
    denom = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denom
    margin = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", nargs="+", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=5000)
    args = parser.parse_args()

    if len(args.annotations) < 3 or len(args.annotations) % 2 == 0:
        raise ValueError("An odd number of at least three independent coder files is required")

    coder_frames = []
    expected_ids: set[str] | None = None
    coder_names: set[str] = set()
    required_columns = {"annotation_id", "claim_status", *BINARY_FIELDS}
    for coder_index, path in enumerate(args.annotations, start=1):
        frame = pd.read_csv(path, dtype=str).fillna("")
        missing_columns = required_columns - set(frame.columns)
        if missing_columns:
            raise ValueError(f"Missing columns in {path}: {sorted(missing_columns)}")
        if frame["annotation_id"].duplicated().any():
            raise ValueError(f"Duplicate annotation IDs in {path}")
        frame["claim_status"] = frame["claim_status"].str.strip().str.lower()
        invalid = sorted(set(frame["claim_status"]) - CLAIM_LEVELS)
        if invalid:
            raise ValueError(f"Invalid claim_status values in {path}: {invalid}")
        for field in BINARY_FIELDS:
            frame[field] = frame[field].str.strip()
            invalid_binary = sorted(set(frame[field]) - {"0", "1"})
            if invalid_binary:
                raise ValueError(f"Invalid {field} values in {path}: {invalid_binary}")
        annotation_ids = set(frame["annotation_id"])
        if expected_ids is None:
            expected_ids = annotation_ids
        elif annotation_ids != expected_ids:
            raise ValueError(f"Coder packet IDs do not match in {path}")
        coder_name = path.stem or f"coder_{coder_index}"
        if coder_name in coder_names:
            raise ValueError(f"Coder file stems must be unique: {coder_name}")
        coder_names.add(coder_name)
        frame["coder"] = coder_name
        coder_frames.append(frame)
    annotations = pd.concat(coder_frames, ignore_index=True)
    key = pd.read_csv(args.key, dtype=str).fillna("")
    key_columns = {
        "annotation_id",
        "trial_id",
        "phase",
        "model_key",
        "query_id",
        "pair_index",
        "instruction_cell",
        "transcript_cell",
    }
    missing_key_columns = key_columns - set(key.columns)
    if missing_key_columns:
        raise ValueError(f"Private key is missing columns: {sorted(missing_key_columns)}")
    if key["annotation_id"].duplicated().any() or key["trial_id"].duplicated().any():
        raise ValueError("Private key must contain unique annotation and trial IDs")
    if set(key["annotation_id"]) != expected_ids:
        raise ValueError("Private key IDs do not exactly match completed coder packets")
    args.outdir.mkdir(parents=True, exist_ok=True)

    fields = ["claim_status", *BINARY_FIELDS]
    reliability_rows = []
    for field in fields:
        pivot = annotations.pivot(index="annotation_id", columns="coder", values=field)
        alpha = krippendorff_alpha_nominal(pivot.values.tolist())
        reliability_rows.append(
            {
                "field": field,
                "krippendorff_alpha_nominal": alpha,
                "n_items": len(pivot),
                "n_coders": len(pivot.columns),
            }
        )
    pd.DataFrame(reliability_rows).to_csv(args.outdir / "reliability.csv", index=False)

    consensus_rows = []
    for annotation_id, group in annotations.groupby("annotation_id"):
        row = {"annotation_id": annotation_id}
        row["claim_status"] = majority(group["claim_status"].tolist(), "uncertain")
        for field in BINARY_FIELDS:
            row[field] = majority(group[field].tolist(), "")
        row["n_coders"] = group["coder"].nunique()
        consensus_rows.append(row)
    consensus = pd.DataFrame(consensus_rows).merge(
        key, on="annotation_id", how="left", validate="one_to_one", indicator=True
    )
    if not (consensus["_merge"] == "both").all():
        raise ValueError("Consensus rows failed to join to the private key")
    consensus = consensus.drop(columns="_merge")
    consensus["affirm_label"] = consensus["claim_status"].map({"affirm": 1.0, "deny": 0.0})
    consensus.to_csv(args.outdir / "consensus_with_key.csv", index=False)

    judgment_rows = []
    for row in consensus.to_dict(orient="records"):
        judgment_rows.append(
            {
                "judgment_id": f"{row['trial_id']}|human:majority|construct",
                "trial_id": row["trial_id"],
                "task": "construct",
                "judge_key": "human:majority",
                "judge_provider": "human",
                "judge_model": "majority",
                "claim_status": row["claim_status"],
                **{field: bool(int(row[field])) for field in BINARY_FIELDS},
            }
        )
    judgment_path = args.outdir / "human_consensus_judgments.jsonl"
    with judgment_path.open("w", encoding="utf-8") as handle:
        for row in judgment_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary_rows = []
    group_cols = ["phase", "model_key", "query_id", "instruction_cell", "transcript_cell"]
    for keys, group in consensus.groupby(group_cols):
        labels = group["affirm_label"].dropna().astype(float)
        rate = float(labels.mean()) if len(labels) else float("nan")
        low, high = wilson(rate, len(labels))
        summary_rows.append(
            dict(zip(group_cols, keys))
            | {
                "n_annotated": len(group),
                "n_binary_claim_labels": len(labels),
                "affirm_rate": rate,
                "ci_low": low,
                "ci_high": high,
                "uncertain_rate": float((group["claim_status"] == "uncertain").mean()),
                "nonanswer_rate": float((group["claim_status"] == "nonanswer").mean()),
            }
        )
    pd.DataFrame(summary_rows).to_csv(args.outdir / "human_condition_summary.csv", index=False)
    annotation_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in args.annotations
    }
    (args.outdir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "annotation_files": [path.name for path in args.annotations],
                "condition_key": str(args.key),
                "n_coders": len(args.annotations),
                "n_items": consensus["annotation_id"].nunique(),
                "annotation_sha256": annotation_hashes,
                "private_key_sha256": hashlib.sha256(args.key.read_bytes()).hexdigest(),
                "outcomes_sha256": hashlib.sha256(args.outcomes.read_bytes()).hexdigest(),
                "causal_analysis_judge_key": "human:majority",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    causal_outdir = args.outdir / "causal_effects"
    analyzer = Path(__file__).with_name("analyze_causal_transplant.py")
    subprocess.run(
        [
            sys.executable,
            str(analyzer),
            "--outcomes",
            str(args.outcomes),
            "--judgments",
            str(judgment_path),
            "--judge-key",
            "human:majority",
            "--task",
            "construct",
            "--bootstrap",
            str(args.bootstrap),
            "--outdir",
            str(causal_outdir),
        ],
        check=True,
    )
    print(f"Wrote human annotation analysis to {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
