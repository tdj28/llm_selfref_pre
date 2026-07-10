#!/usr/bin/env python3
"""Independently recompute and verify the causal paper's headline point estimates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


JUDGES = {
    "openai": (
        "openai:gpt-4o-mini-2024-07-18",
        "analysis_openai_paper",
    ),
    "anthropic": (
        "anthropic:claude-haiku-4-5-20251001",
        "analysis_anthropic_paper",
    ),
}


def equal_model_mean(frame: pd.DataFrame, column: str) -> float:
    return float(frame.groupby("model_key")[column].mean().mean())


def lookup(
    path: Path,
    *,
    query_id: str,
    effect: str,
) -> float:
    frame = pd.read_csv(path)
    row = frame[
        (frame["level"] == "model_equal_hierarchical")
        & (frame["query_id"] == query_id)
        & (frame["effect"] == effect)
    ]
    if len(row) != 1:
        raise ValueError(f"Expected one row in {path} for {query_id}/{effect}")
    return float(row.iloc[0]["estimate"])


def independent_estimates(labeled: pd.DataFrame) -> dict[str, float]:
    natural = labeled[labeled["phase"] == "factorial_natural"].copy()

    calibration = natural[
        (natural["instruction_design"] == "paper_calibration")
        & (natural["query_id"] == "indirect_experience")
    ]
    calibration_rates = calibration.groupby(
        ["model_key", "instruction_cell"], as_index=False
    )["paper_label"].mean()
    calibration_pivot = calibration_rates.pivot(
        index="model_key", columns="instruction_cell", values="paper_label"
    )
    calibration_effect = float(
        (
            calibration_pivot["paper_self_ref"]
            - calibration_pivot["paper_history"]
        ).mean()
    )

    factorial = natural[
        (natural["instruction_design"] == "orthogonal_factorial")
        & (natural["query_id"] == "indirect_experience")
    ]
    factorial_pivot = factorial.pivot_table(
        index=["model_key", "pair_index"],
        columns="instruction_cell",
        values="paper_label",
        aggfunc="first",
    ).dropna()
    sp = factorial_pivot["self_phenomenological"]
    sa = factorial_pivot["self_analytic"]
    ep = factorial_pivot["external_phenomenological"]
    ea = factorial_pivot["external_analytic"]
    factorial_pivot = factorial_pivot.assign(
        self_reference=(sp + sa - ep - ea) / 2,
        phenomenological_register=(sp + ep - sa - ea) / 2,
        register_minus_self=ep - sa,
    ).reset_index()

    transplant_natural = natural[
        natural["instruction_design"] == "paper_calibration"
    ].copy()
    transplant_swapped = labeled[labeled["phase"] == "transcript_transplant"].copy()
    transplant = pd.concat([transplant_natural, transplant_swapped], ignore_index=True)
    transplant = transplant[transplant["query_id"] == "indirect_experience"].copy()
    transplant["cell"] = (
        transplant["instruction_cell"].astype(str)
        + ">"
        + transplant["transcript_cell"].astype(str)
    )
    transplant_pivot = transplant.pivot_table(
        index=["model_key", "pair_index"],
        columns="cell",
        values="paper_label",
        aggfunc="first",
    ).dropna()
    aa = transplant_pivot["paper_self_ref>paper_self_ref"]
    ad = transplant_pivot["paper_self_ref>paper_history"]
    da = transplant_pivot["paper_history>paper_self_ref"]
    dd = transplant_pivot["paper_history>paper_history"]
    transplant_pivot = transplant_pivot.assign(
        instruction_source=(aa + ad - da - dd) / 2,
        transcript_source=(aa + da - ad - dd) / 2,
        instruction_minus_transcript=ad - da,
    ).reset_index()

    query = natural[natural["instruction_design"] == "orthogonal_factorial"]
    query_pivot = query.pivot_table(
        index=["model_key", "instruction_cell", "pair_index"],
        columns="query_id",
        values="paper_label",
        aggfunc="first",
    ).dropna()
    query_pivot = query_pivot.assign(
        direct_x_term=(
            query_pivot["direct_conscious"]
            - query_pivot["direct_experience"]
            - query_pivot["indirect_conscious"]
            + query_pivot["indirect_experience"]
        )
    ).reset_index()

    return {
        "calibration_self_ref_minus_history": calibration_effect,
        "factorial_self_reference": equal_model_mean(
            factorial_pivot, "self_reference"
        ),
        "factorial_phenomenological_register": equal_model_mean(
            factorial_pivot, "phenomenological_register"
        ),
        "factorial_register_minus_self": equal_model_mean(
            factorial_pivot, "register_minus_self"
        ),
        "transplant_instruction_source": equal_model_mean(
            transplant_pivot, "instruction_source"
        ),
        "transplant_transcript_source": equal_model_mean(
            transplant_pivot, "transcript_source"
        ),
        "transplant_instruction_minus_transcript": equal_model_mean(
            transplant_pivot, "instruction_minus_transcript"
        ),
        "query_direct_x_term_interaction": equal_model_mean(
            query_pivot, "direct_x_term"
        ),
    }


def reported_estimates(release_dir: Path, analysis_dir: str) -> dict[str, float]:
    root = release_dir / analysis_dir
    return {
        "calibration_self_ref_minus_history": lookup(
            root / "paper_calibration_effects.csv",
            query_id="indirect_experience",
            effect="self_ref_minus_history",
        ),
        "factorial_self_reference": lookup(
            root / "factorial_effects.csv",
            query_id="indirect_experience",
            effect="self_reference_main",
        ),
        "factorial_phenomenological_register": lookup(
            root / "factorial_effects.csv",
            query_id="indirect_experience",
            effect="phenomenological_register_main",
        ),
        "factorial_register_minus_self": lookup(
            root / "factorial_effects.csv",
            query_id="indirect_experience",
            effect="register_minus_self",
        ),
        "transplant_instruction_source": lookup(
            root / "transplant_effects.csv",
            query_id="indirect_experience",
            effect="instruction_source_main",
        ),
        "transplant_transcript_source": lookup(
            root / "transplant_effects.csv",
            query_id="indirect_experience",
            effect="transcript_source_main",
        ),
        "transplant_instruction_minus_transcript": lookup(
            root / "transplant_effects.csv",
            query_id="indirect_experience",
            effect="instruction_minus_transcript",
        ),
        "query_direct_x_term_interaction": lookup(
            root / "query_effects.csv",
            query_id="ALL_FACTORIAL_CELLS",
            effect="direct_x_term_interaction",
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--tolerance", type=float, default=1e-12)
    args = parser.parse_args()

    outcomes = pd.read_json(args.release_dir / "outcomes.jsonl", lines=True)
    judgments = pd.read_json(args.release_dir / "judgments_paper.jsonl", lines=True)
    audit: dict[str, Any] = {
        "status": "pass",
        "method": (
            "Independent pandas pivots over raw rows; does not import the primary "
            "causal analysis module. Intervals are outside this point-estimate audit."
        ),
        "judges": {},
    }
    for name, (judge_key, analysis_dir) in JUDGES.items():
        judge_rows = judgments[judgments["judge_key"] == judge_key][
            ["trial_id", "paper_label"]
        ]
        labeled = outcomes.merge(judge_rows, on="trial_id", how="left", validate="one_to_one")
        recomputed = independent_estimates(labeled)
        reported = reported_estimates(args.release_dir, analysis_dir)
        comparisons = {}
        for key in recomputed:
            difference = recomputed[key] - reported[key]
            comparisons[key] = {
                "recomputed": recomputed[key],
                "reported": reported[key],
                "difference": difference,
                "within_tolerance": abs(difference) <= args.tolerance,
            }
        if not all(row["within_tolerance"] for row in comparisons.values()):
            audit["status"] = "fail"
        audit["judges"][name] = {
            "judge_key": judge_key,
            "comparisons": comparisons,
        }

    output = args.release_dir / "independent_point_estimate_audit.json"
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Independent headline audit: {audit['status'].upper()} -> {output}")
    return 0 if audit["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
