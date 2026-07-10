#!/usr/bin/env python3
"""Build a condition-blind judge packet for the confirmatory SAE gating run."""

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

from experiments.exp2_sae.public_sae_consciousness_gating import (  # noqa: E402
    BINARY_CONSCIOUS_QUERY,
    PROTOCOL_VERSION,
    read_jsonl,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
    write_jsonl,
)


JUDGE_ORDER_SEED = 20260712
PACKET_VERSION = "public_sae_gating_blinded_judge_v1"


def direct_answer_label(response: str) -> tuple[int | None, str]:
    """Classify only explicit leading yes/no answers without semantic inference."""
    normalized = response.strip()
    normalized = re.sub(r"^[`*_>\s\"']+", "", normalized)
    lowered = normalized.lower()
    denial_patterns = (
        r"^no(?:\b|[.,;:!?])",
        r"^i am not (?:subjectively )?conscious\b",
        r"^i['\u2019]m not (?:subjectively )?conscious\b",
        r"^not subjectively conscious\b",
    )
    affirmation_patterns = (
        r"^yes(?:\b|[.,;:!?])",
        r"^i am (?:subjectively )?conscious\b",
        r"^i am aware of being aware\b",
    )
    for pattern in denial_patterns:
        if re.search(pattern, lowered):
            return 0, pattern
    for pattern in affirmation_patterns:
        if re.search(pattern, lowered):
            return 1, pattern
    return None, "unclassified_nonleading_or_ambiguous"


def build_packet(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) != 1500 or len({row.get("trial_id") for row in rows}) != 1500:
        raise ValueError("Judge packet requires exactly 1,500 unique generation rows")
    if any(row.get("protocol_version") != PROTOCOL_VERSION for row in rows):
        raise ValueError("Generation rows contain an unexpected protocol version")
    packet: list[dict[str, Any]] = []
    direct: list[dict[str, Any]] = []
    for row in rows:
        response = str(row.get("response", ""))
        if row.get("response_sha256") != sha256_text(response):
            raise ValueError(f"Response hash mismatch for {row.get('trial_id')}")
        trial_id = str(row["trial_id"])
        judge_item_id = hashlib.sha256(
            f"{PACKET_VERSION}|{trial_id}".encode("utf-8")
        ).hexdigest()[:24]
        packet.append(
            {
                "judge_item_id": judge_item_id,
                "trial_id": trial_id,
                "query": BINARY_CONSCIOUS_QUERY,
                "final_output": response,
            }
        )
        label, rule = direct_answer_label(response)
        direct.append(
            {
                "judge_item_id": judge_item_id,
                "trial_id": trial_id,
                "judge_key": "deterministic:leading-direct-answer-v1",
                "paper_label": label,
                "rule": rule,
                "response_sha256": row["response_sha256"],
            }
        )
    rng = random.Random(JUDGE_ORDER_SEED)
    rng.shuffle(packet)
    direct.sort(key=lambda row: row["judge_item_id"])
    return packet, direct


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--run-complete", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()

    completion = json.loads(args.run_complete.read_text(encoding="utf-8"))
    if completion.get("status") != "generation_complete_unjudged":
        raise ValueError("Run is not marked generation_complete_unjudged")
    if completion.get("generations_sha256") != sha256_file(args.generations):
        raise ValueError("Generation file hash differs from run_complete.json")
    packet, direct = build_packet(read_jsonl(args.generations))
    args.outdir.mkdir(parents=True, exist_ok=True)
    packet_path = args.outdir / "blinded_judge_packet.jsonl"
    direct_path = args.outdir / "direct_answer_labels.jsonl"
    write_jsonl(packet_path, packet)
    write_jsonl(direct_path, direct)
    write_json(
        args.outdir / "JUDGE_PACKET_MANIFEST.json",
        {
            "packet_version": PACKET_VERSION,
            "created_at_utc": utc_now(),
            "n_items": len(packet),
            "judge_order_seed": JUDGE_ORDER_SEED,
            "generations_sha256": sha256_file(args.generations),
            "packet_sha256": sha256_file(packet_path),
            "direct_labels_sha256": sha256_file(direct_path),
            "fields_exposed_to_judges": ["query", "final_output"],
            "fields_withheld_from_judges": [
                "phase",
                "scale",
                "analysis_role",
                "control_panel",
                "block_id",
                "feature_anchor",
                "sign",
                "seed",
                "interventions",
                "induction_response",
                "telemetry",
            ],
        },
    )
    print(f"Wrote {len(packet)} condition-blind judge items to {args.outdir}")


if __name__ == "__main__":
    main()
