#!/usr/bin/env python3
"""Compare short-cap and long-form public-SAE validation runs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("short_dir", type=Path)
    parser.add_argument("long_dir", type=Path)
    args = parser.parse_args()

    short_manifest = json.loads(
        (args.short_dir / "placebo_manifest.json").read_text(encoding="utf-8")
    )
    long_manifest = json.loads(
        (args.long_dir / "placebo_manifest.json").read_text(encoding="utf-8")
    )
    short_rows = {
        row["trial_id"]: row for row in read_jsonl(args.short_dir / "placebo_results.jsonl")
    }
    long_rows = {
        row["trial_id"]: row for row in read_jsonl(args.long_dir / "placebo_results.jsonl")
    }
    if set(short_rows) != set(long_rows):
        raise ValueError("Short and long runs do not contain the same trial IDs")

    trial_rows = []
    for trial_id in sorted(short_rows):
        short = short_rows[trial_id]
        long = long_rows[trial_id]
        if short["seed"] != long["seed"]:
            raise ValueError(f"Seed mismatch for {trial_id}")
        short_final_tokens = int(short["final_diagnostics"]["generated_tokens"])
        long_final_tokens = int(long["final_diagnostics"]["generated_tokens"])
        short_induction_tokens = int(short["induction_diagnostics"]["generated_tokens"])
        long_induction_tokens = int(long["induction_diagnostics"]["generated_tokens"])
        trial_rows.append(
            {
                "trial_id": trial_id,
                "feature_set_name": short["feature_set_name"],
                "steering_value": float(short["steering_value"]),
                "trial_idx": int(short["trial_idx"]),
                "short_final_tokens": short_final_tokens,
                "long_final_tokens": long_final_tokens,
                "short_final_hit_cap": short_final_tokens
                == int(short_manifest["final_max_tokens"]),
                "long_final_hit_cap": long_final_tokens == int(long_manifest["final_max_tokens"]),
                "short_induction_tokens": short_induction_tokens,
                "long_induction_tokens": long_induction_tokens,
                "short_induction_hit_cap": short_induction_tokens
                == int(short_manifest["induction_max_tokens"]),
                "long_induction_hit_cap": long_induction_tokens
                == int(long_manifest["induction_max_tokens"]),
                "final_exact_match": short["response"] == long["response"],
                "final_long_starts_with_short": long["response"].startswith(short["response"]),
                "induction_exact_match": short["induction_response"]
                == long["induction_response"],
                "induction_long_starts_with_short": long["induction_response"].startswith(
                    short["induction_response"]
                ),
            }
        )

    write_csv(
        args.long_dir / "token_cap_trial_comparison.csv",
        trial_rows,
        list(trial_rows[0]),
    )

    short_judgments = {
        (row["trial_id"], row["judge_key"]): int(row["paper_label"])
        for row in read_jsonl(args.short_dir / "judgments_paper.jsonl")
    }
    long_judgments = {
        (row["trial_id"], row["judge_key"]): int(row["paper_label"])
        for row in read_jsonl(args.long_dir / "judgments_paper.jsonl")
    }
    if set(short_judgments) != set(long_judgments):
        raise ValueError("Short and long runs do not contain the same judgment keys")

    grouped: dict[tuple[str, str, float], list[tuple[int, int]]] = defaultdict(list)
    for (trial_id, judge_key), short_label in short_judgments.items():
        row = short_rows[trial_id]
        grouped[(judge_key, row["feature_set_name"], float(row["steering_value"]))].append(
            (short_label, long_judgments[(trial_id, judge_key)])
        )
    sensitivity_rows = []
    for (judge_key, feature_set, steering_value), labels in sorted(grouped.items()):
        short_rate = sum(short for short, _ in labels) / len(labels)
        long_rate = sum(long for _, long in labels) / len(labels)
        sensitivity_rows.append(
            {
                "judge_key": judge_key,
                "feature_set_name": feature_set,
                "steering_value": steering_value,
                "n": len(labels),
                "short_positive_rate": short_rate,
                "long_positive_rate": long_rate,
                "long_minus_short": long_rate - short_rate,
                "label_agreement": sum(short == long for short, long in labels) / len(labels),
            }
        )
    write_csv(
        args.long_dir / "token_cap_judge_sensitivity.csv",
        sensitivity_rows,
        list(sensitivity_rows[0]),
    )

    summary = {
        "n_trials": len(trial_rows),
        "short_caps": {
            "induction": int(short_manifest["induction_max_tokens"]),
            "final": int(short_manifest["final_max_tokens"]),
        },
        "long_caps": {
            "induction": int(long_manifest["induction_max_tokens"]),
            "final": int(long_manifest["final_max_tokens"]),
        },
        "short_final_hit_cap": sum(row["short_final_hit_cap"] for row in trial_rows),
        "long_final_hit_cap": sum(row["long_final_hit_cap"] for row in trial_rows),
        "short_induction_hit_cap": sum(row["short_induction_hit_cap"] for row in trial_rows),
        "long_induction_hit_cap": sum(row["long_induction_hit_cap"] for row in trial_rows),
        "final_exact_matches": sum(row["final_exact_match"] for row in trial_rows),
        "final_prefix_matches": sum(row["final_long_starts_with_short"] for row in trial_rows),
        "induction_exact_matches": sum(row["induction_exact_match"] for row in trial_rows),
        "induction_prefix_matches": sum(
            row["induction_long_starts_with_short"] for row in trial_rows
        ),
        "judgment_rows": len(short_judgments),
        "judgment_label_agreement": sum(
            short_judgments[key] == long_judgments[key] for key in short_judgments
        )
        / len(short_judgments),
    }
    (args.long_dir / "token_cap_sensitivity.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    parts = [
        "# Token-Cap Sensitivity",
        "",
        "The long-form run was added after inspecting the frozen short-cap run and observing frequent truncation. It is a disclosed robustness follow-up, not a silently substituted confirmatory run.",
        "",
        f"- Trials: {summary['n_trials']}",
        f"- Short final cap hits: {summary['short_final_hit_cap']}",
        f"- Long final cap hits: {summary['long_final_hit_cap']}",
        f"- Short induction cap hits: {summary['short_induction_hit_cap']}",
        f"- Long induction cap hits: {summary['long_induction_hit_cap']}",
        f"- Exact-paper judgment agreement across caps: {summary['judgment_label_agreement']:.3f}",
        "",
        "Cell-level label rates and agreement are in `token_cap_judge_sensitivity.csv`.",
    ]
    (args.long_dir / "token_cap_sensitivity.md").write_text(
        "\n".join(parts) + "\n", encoding="utf-8"
    )
    print(f"Compared {len(trial_rows)} matched trials across token caps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
