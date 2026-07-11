#!/usr/bin/env python3
"""Build descriptive adjacent-layer feature links for the Gemma residual atlas."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from pathlib import Path
from typing import Any


def rankdata(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2 + 1
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    return numerator / math.sqrt(left_ss * right_ss) if left_ss and right_ss else 0.0


def load_feature_items(sae_dir: Path) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}
    with gzip.open(sae_dir / "selected_item_activations.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["source"] != "openai_paraphrase" or row["construct"] != "deception_roleplay":
                continue
            result.setdefault(int(row["feature_id"]), {})[row["item_id"]] = float(
                row["activation"]
            )
    return result


def load_directions(sae_dir: Path) -> dict[int, Any]:
    import numpy as np

    payload = np.load(sae_dir / "selected_decoder_directions.npz")
    return {
        int(feature_id): direction.astype(np.float64)
        for feature_id, direction in zip(payload["feature_ids"], payload["directions"])
    }


def cosine(left: Any, right: Any) -> float:
    import numpy as np

    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


def top_overlap(left: dict[str, float], right: dict[str, float], count: int = 20) -> float:
    left_top = {
        item for item, _ in sorted(left.items(), key=lambda item: (-item[1], item[0]))[:count]
    }
    right_top = {
        item for item, _ in sorted(right.items(), key=lambda item: (-item[1], item[0]))[:count]
    }
    union = left_top | right_top
    return len(left_top & right_top) / len(union) if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    atlas = args.atlas_dir.resolve()
    output = args.out.resolve() if args.out else atlas / "cross_layer_feature_edges.csv"
    rows = []
    for layer in range(41):
        left_dir = atlas / "saes" / f"pt_res_l{layer}_w16384"
        right_dir = atlas / "saes" / f"pt_res_l{layer + 1}_w16384"
        if not left_dir.is_dir() or not right_dir.is_dir():
            continue
        left_items = load_feature_items(left_dir)
        right_items = load_feature_items(right_dir)
        left_directions = load_directions(left_dir)
        right_directions = load_directions(right_dir)
        for left_id, left_values_by_item in sorted(left_items.items()):
            for right_id, right_values_by_item in sorted(right_items.items()):
                common = sorted(set(left_values_by_item) & set(right_values_by_item))
                activation_spearman = pearson(
                    rankdata([left_values_by_item[item] for item in common]),
                    rankdata([right_values_by_item[item] for item in common]),
                )
                direction_cosine = cosine(
                    left_directions[left_id], right_directions[right_id]
                )
                overlap = top_overlap(left_values_by_item, right_values_by_item)
                selected_edge = (
                    activation_spearman >= 0.25
                    and (direction_cosine >= 0.05 or overlap >= 0.15)
                )
                rows.append(
                    {
                        "from_layer": layer,
                        "to_layer": layer + 1,
                        "from_feature_id": left_id,
                        "to_feature_id": right_id,
                        "n_common_items": len(common),
                        "activation_spearman": activation_spearman,
                        "decoder_cosine": direction_cosine,
                        "top20_item_jaccard": overlap,
                        "selected_descriptive_edge": int(selected_edge),
                    }
                )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(rows[0]) if rows else [
            "from_layer",
            "to_layer",
            "from_feature_id",
            "to_feature_id",
            "n_common_items",
            "activation_spearman",
            "decoder_cosine",
            "top20_item_jaccard",
            "selected_descriptive_edge",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "status": "complete",
        "n_tested_adjacent_feature_pairs": len(rows),
        "n_selected_descriptive_edges": sum(
            int(row["selected_descriptive_edge"]) for row in rows
        ),
        "layers_covered": sorted(
            {int(row["from_layer"]) for row in rows}
            | {int(row["to_layer"]) for row in rows}
        ),
        "selection_rule": (
            "activation Spearman >= 0.25 and either decoder cosine >= 0.05 "
            "or top-20 item Jaccard >= 0.15"
        ),
        "claim_boundary": "descriptive cross-layer links; IDs are not persistent identities",
    }
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Gemma cross-layer links: {len(rows)} tested pairs -> {output}")


if __name__ == "__main__":
    main()
