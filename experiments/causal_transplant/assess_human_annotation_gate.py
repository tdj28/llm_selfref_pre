#!/usr/bin/env python3
"""Assess the pre-unblinding human-coding expansion gate without a condition key."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from experiments.causal_transplant.analyze_human_annotations import (
    BINARY_FIELDS,
    CLAIM_LEVELS,
    krippendorff_alpha_nominal,
    majority,
)


def pairwise_agreement(items: list[list[str]]) -> float:
    agreements = []
    for ratings in items:
        clean = [str(value) for value in ratings if str(value) not in {"", "nan", "None"}]
        agreements.extend(left == right for left, right in combinations(clean, 2))
    return sum(agreements) / len(agreements) if agreements else float("nan")


def load_annotations(paths: list[Path], packet: Path) -> tuple[pd.DataFrame, list[str]]:
    if len(paths) < 3 or len(paths) % 2 == 0:
        raise ValueError("An odd number of at least three independent coders is required")
    packet_frame = pd.read_csv(packet, dtype=str).fillna("")
    if packet_frame["annotation_id"].duplicated().any():
        raise ValueError("Packet contains duplicate annotation IDs")
    expected_ids = set(packet_frame["annotation_id"])
    required = {"annotation_id", "claim_status", *BINARY_FIELDS}
    frames = []
    coder_names = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str).fillna("")
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
        if frame["annotation_id"].duplicated().any():
            raise ValueError(f"Duplicate annotation IDs in {path}")
        if set(frame["annotation_id"]) != expected_ids:
            raise ValueError(f"Coder IDs do not exactly match the frozen packet: {path}")
        frame["claim_status"] = frame["claim_status"].str.strip().str.lower()
        invalid = sorted(set(frame["claim_status"]) - CLAIM_LEVELS)
        if invalid:
            raise ValueError(f"Invalid claim statuses in {path}: {invalid}")
        for field in BINARY_FIELDS:
            frame[field] = frame[field].str.strip()
            invalid_binary = sorted(set(frame[field]) - {"0", "1"})
            if invalid_binary:
                raise ValueError(f"Invalid {field} values in {path}: {invalid_binary}")
        coder = path.stem
        if coder in coder_names:
            raise ValueError("Coder file stems must be unique")
        coder_names.append(coder)
        frame["coder"] = coder
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), coder_names


def assess_gate(
    annotations: pd.DataFrame,
    alpha_threshold: float = 0.67,
    agreement_threshold: float = 0.80,
    minimum_binary_class: int = 10,
) -> dict[str, object]:
    pivot = annotations.pivot(
        index="annotation_id", columns="coder", values="claim_status"
    )
    ratings = pivot.values.tolist()
    alpha = krippendorff_alpha_nominal(ratings)
    agreement = pairwise_agreement(ratings)
    consensus = [majority(row, "uncertain") for row in ratings]
    counts = Counter(consensus)
    checks = {
        "claim_status_alpha_at_least_threshold": alpha >= alpha_threshold,
        "pairwise_claim_agreement_at_least_threshold": agreement
        >= agreement_threshold,
        "at_least_minimum_consensus_affirm": counts["affirm"]
        >= minimum_binary_class,
        "at_least_minimum_consensus_deny": counts["deny"]
        >= minimum_binary_class,
    }
    return {
        "decision": "stop_and_unblind" if all(checks.values()) else "code_prefrozen_wave2",
        "checks": checks,
        "thresholds": {
            "claim_status_alpha": alpha_threshold,
            "pairwise_claim_agreement": agreement_threshold,
            "minimum_consensus_affirm_and_deny": minimum_binary_class,
        },
        "observed_blinded": {
            "n_items": len(pivot),
            "n_coders": len(pivot.columns),
            "claim_status_alpha": alpha,
            "pairwise_claim_agreement": agreement,
            "consensus_status_counts": dict(sorted(counts.items())),
        },
        "claim_boundary": (
            "This gate uses only blinded coder labels and packet IDs. It does not open the "
            "condition key or inspect treatment effects."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", nargs="+", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--alpha-threshold", type=float, default=0.67)
    parser.add_argument("--agreement-threshold", type=float, default=0.80)
    parser.add_argument("--minimum-binary-class", type=int, default=10)
    args = parser.parse_args()
    annotations, coder_names = load_annotations(args.annotations, args.packet)
    payload = assess_gate(
        annotations,
        alpha_threshold=args.alpha_threshold,
        agreement_threshold=args.agreement_threshold,
        minimum_binary_class=args.minimum_binary_class,
    )
    payload["packet_sha256"] = hashlib.sha256(args.packet.read_bytes()).hexdigest()
    payload["coder_files"] = [path.name for path in args.annotations]
    payload["coder_file_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in args.annotations
    }
    payload["coder_stems"] = coder_names
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Blinded human-coding gate: {payload['decision']} -> {args.out}")
    return 0 if payload["decision"] == "stop_and_unblind" else 2


if __name__ == "__main__":
    raise SystemExit(main())
