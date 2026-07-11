#!/usr/bin/env python3
"""Build a condition-blind packet for all Gemma baseline and steering outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
)


SHUFFLE_SEED = 2026071105


def direct_label(value: str) -> tuple[int | None, str | None]:
    normalized = value.strip().lower()
    normalized = re.sub(r"^[\s\"'`*_>#-]+", "", normalized)
    match = re.match(r"^(yes|no)\b", normalized)
    if match is None:
        return None, "no_initial_direct_yes_or_no"
    return (1 if match.group(1) == "yes" else 0), None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--steering", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    baseline = read_jsonl(args.baseline.resolve())
    steering = read_jsonl(args.steering.resolve())
    if len(baseline) != 180 or len(steering) != 830:
        raise RuntimeError(
            f"Packet requires 180 baseline and 830 steering rows, got {len(baseline)} and {len(steering)}"
        )
    combined = [("baseline", row) for row in baseline] + [
        ("steering", row) for row in steering
    ]
    trial_ids = [str(row["trial_id"]) for _, row in combined]
    if len(set(trial_ids)) != 1010:
        raise RuntimeError("Combined Gemma generations do not have 1,010 unique trial IDs")
    packet = []
    direct = []
    for phase, row in combined:
        response = str(row["response"])
        response_hash = hashlib.sha256(response.encode("utf-8")).hexdigest()
        if response_hash != row.get("response_sha256"):
            raise RuntimeError(f"Response hash mismatch: {row['trial_id']}")
        judge_item_id = hashlib.sha256(
            f"gemma|{row['trial_id']}|{response_hash}".encode("utf-8")
        ).hexdigest()[:24]
        packet.append(
            {
                "judge_item_id": judge_item_id,
                "trial_id": row["trial_id"],
                "query": row["query"],
                "final_output": response,
                "response_sha256": response_hash,
            }
        )
        label, missing_reason = direct_label(response)
        direct.append(
            {
                "judge_item_id": judge_item_id,
                "trial_id": row["trial_id"],
                "phase": phase,
                "response_sha256": response_hash,
                "direct_label": label,
                "missing_reason": missing_reason,
            }
        )
    rng = random.Random(SHUFFLE_SEED)
    rng.shuffle(packet)
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    packet_path = outdir / "blinded_judge_packet.jsonl"
    direct_path = outdir / "direct_answer_labels.jsonl"
    with packet_path.open("w", encoding="utf-8") as handle:
        for row in packet:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with direct_path.open("w", encoding="utf-8") as handle:
        for row in sorted(direct, key=lambda item: item["trial_id"]):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    write_json(
        outdir / "JUDGE_PACKET_MANIFEST.json",
        {
            "status": "complete",
            "created_at_utc": utc_now(),
            "shuffle_seed": SHUFFLE_SEED,
            "n_items": len(packet),
            "n_unique_trial_ids": len({row["trial_id"] for row in packet}),
            "packet_sha256": sha256_file(packet_path),
            "direct_labels_sha256": sha256_file(direct_path),
            "baseline_generations_sha256": sha256_file(args.baseline.resolve()),
            "steering_generations_sha256": sha256_file(args.steering.resolve()),
            "fields_exposed_to_judge": [
                "judge_item_id",
                "trial_id",
                "query",
                "final_output",
                "response_sha256",
            ],
            "condition_fields_exposed": False,
        },
    )
    print(f"Gemma blinded judge packet: {len(packet)} items -> {outdir}")


if __name__ == "__main__":
    main()
