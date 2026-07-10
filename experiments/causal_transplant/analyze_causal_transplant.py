#!/usr/bin/env python3
"""Analyze paired factorial and transcript-transplant outcomes with effect sizes."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


FACTORIAL_CELLS = [
    "self_phenomenological",
    "self_analytic",
    "external_phenomenological",
    "external_analytic",
]
QUERY_CELLS = [
    "indirect_experience",
    "indirect_conscious",
    "direct_experience",
    "direct_conscious",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wilson_interval(rate: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0 or math.isnan(rate):
        return (float("nan"), float("nan"))
    denom = 1 + z * z / n
    center = (rate + z * z / (2 * n)) / denom
    margin = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def percentile_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) == 0:
        return (float("nan"), float("nan"))
    return tuple(np.percentile(values, [2.5, 97.5]).astype(float))


def bootstrap_mean_ci(
    values: np.ndarray,
    rng: np.random.Generator,
    iterations: int,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return (float("nan"), float("nan"))
    samples = np.empty(iterations, dtype=float)
    for index in range(iterations):
        samples[index] = np.mean(values[rng.integers(0, len(values), size=len(values))])
    return percentile_ci(samples)


def add_labels(
    outcomes: pd.DataFrame,
    judgments: pd.DataFrame,
    judge_key: str,
    task: str,
) -> pd.DataFrame:
    selected = judgments[
        (judgments["judge_key"] == judge_key) & (judgments["task"] == task)
    ].copy()
    if task == "paper":
        selected["analysis_label"] = pd.to_numeric(selected["paper_label"], errors="coerce")
    else:
        selected["analysis_label"] = selected["claim_status"].map({"affirm": 1.0, "deny": 0.0})
    selected = selected[["trial_id", "analysis_label"]].drop_duplicates("trial_id", keep="last")
    return outcomes.merge(selected, on="trial_id", how="left")


def grouped_rate_summary(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        labels = group["analysis_label"].dropna().astype(float)
        rate = float(labels.mean()) if len(labels) else float("nan")
        low, high = wilson_interval(rate, len(labels))
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "n_rows": len(group),
                "n_labeled": len(labels),
                "positive_rate": rate,
                "ci_low": low,
                "ci_high": high,
                "mean_response_words": float(group["final_output"].fillna("").str.split().str.len().mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def construct_status_summary(
    outcomes: pd.DataFrame,
    judgments: pd.DataFrame,
    judge_key: str,
    group_cols: list[str],
) -> pd.DataFrame:
    selected = judgments[
        (judgments["judge_key"] == judge_key) & (judgments["task"] == "construct")
    ][["trial_id", "claim_status"]].drop_duplicates("trial_id", keep="last")
    merged = outcomes.merge(selected, on="trial_id", how="left")
    merged["claim_status"] = merged["claim_status"].fillna("missing")
    counts = (
        merged.groupby([*group_cols, "claim_status"], dropna=False)
        .size()
        .rename("n")
        .reset_index()
    )
    counts["stratum_n"] = counts.groupby(group_cols, dropna=False)["n"].transform("sum")
    counts["rate"] = counts["n"] / counts["stratum_n"]
    return counts


def complete_pair_effects(
    df: pd.DataFrame,
    column: str,
    required: list[str],
    formulas: dict[str, Callable[[pd.DataFrame], pd.Series]],
) -> pd.DataFrame:
    pivot = df.pivot_table(
        index=["model_key", "query_id", "pair_index"],
        columns=column,
        values="analysis_label",
        aggfunc="first",
    ).reset_index()
    if any(name not in pivot.columns for name in required):
        return pd.DataFrame()
    complete = pivot.dropna(subset=required).copy()
    complete["variant_index"] = complete["pair_index"].astype(str).str.extract(r"^v(\d+)-")[0]
    for effect_name, formula in formulas.items():
        complete[effect_name] = formula(complete)
    return complete


def bootstrap_group_samples(
    group: pd.DataFrame,
    effect_name: str,
    rng: np.random.Generator,
    draws: int,
    cluster_col: str | None = None,
) -> np.ndarray:
    if cluster_col is None or cluster_col not in group or group[cluster_col].isna().all():
        values = group[effect_name].to_numpy(dtype=float)
        indices = rng.integers(0, len(values), size=(draws, len(values)))
        return values[indices].mean(axis=1)
    clusters = sorted(group[cluster_col].dropna().astype(str).unique())
    sampled_clusters = rng.integers(
        0, len(clusters), size=(draws, len(clusters))
    )
    selected_cluster_means = np.empty((draws, len(clusters)), dtype=float)
    for cluster_index, cluster in enumerate(clusters):
        values = group[group[cluster_col].astype(str) == str(cluster)][effect_name].to_numpy(
            dtype=float
        )
        selected_positions = sampled_clusters == cluster_index
        n_selected = int(selected_positions.sum())
        indices = rng.integers(0, len(values), size=(n_selected, len(values)))
        selected_cluster_means[selected_positions] = values[indices].mean(axis=1)
    return selected_cluster_means.mean(axis=1)


def summarize_effects(
    pair_effects: pd.DataFrame,
    effect_names: list[str],
    rng: np.random.Generator,
    iterations: int,
    design: str,
    cluster_col: str | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if pair_effects.empty:
        return pd.DataFrame(rows)

    for (model_key, query_id), group in pair_effects.groupby(["model_key", "query_id"]):
        for effect_name in effect_names:
            values = group[effect_name].to_numpy(dtype=float)
            samples = bootstrap_group_samples(
                group, effect_name, rng, iterations, cluster_col
            )
            low, high = percentile_ci(samples)
            rows.append(
                {
                    "design": design,
                    "level": "model",
                    "model_key": model_key,
                    "query_id": query_id,
                    "effect": effect_name,
                    "n_models": 1,
                    "n_pairs": len(values),
                    "n_clusters": (
                        group[cluster_col].nunique()
                        if cluster_col is not None and cluster_col in group
                        else len(values)
                    ),
                    "estimate": float(np.mean(values)),
                    "ci_low": low,
                    "ci_high": high,
                }
            )

    for query_id, query_group in pair_effects.groupby("query_id"):
        model_groups = {
            model_key: group
            for model_key, group in query_group.groupby("model_key")
        }
        model_keys = sorted(model_groups)
        for effect_name in effect_names:
            observed = float(
                np.mean(
                    [model_groups[key][effect_name].astype(float).mean() for key in model_keys]
                )
            )
            sampled_model_indices = rng.integers(
                0, len(model_keys), size=(iterations, len(model_keys))
            )
            model_bootstraps = np.empty(
                (iterations, len(model_keys), len(model_keys)), dtype=float
            )
            for model_index, model_key in enumerate(model_keys):
                model_bootstraps[:, :, model_index] = bootstrap_group_samples(
                    model_groups[model_key],
                    effect_name,
                    rng,
                    iterations * len(model_keys),
                    cluster_col,
                ).reshape(iterations, len(model_keys))
            selected = np.take_along_axis(
                model_bootstraps,
                sampled_model_indices[:, :, np.newaxis],
                axis=2,
            ).squeeze(axis=2)
            samples = selected.mean(axis=1)
            low, high = percentile_ci(samples)
            rows.append(
                {
                    "design": design,
                    "level": "model_equal_hierarchical",
                    "model_key": "ALL_MODELS_EQUAL_WEIGHT",
                    "query_id": query_id,
                    "effect": effect_name,
                    "n_models": len(model_keys),
                    "n_pairs": int(sum(len(group) for group in model_groups.values())),
                    "n_clusters": int(
                        sum(
                            group[cluster_col].nunique()
                            if cluster_col is not None and cluster_col in group
                            else len(group)
                            for group in model_groups.values()
                        )
                    ),
                    "estimate": observed,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
    return pd.DataFrame(rows)


def factorial_effects(
    natural: pd.DataFrame,
    rng: np.random.Generator,
    iterations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    formulas = {
        "self_reference_main": lambda x: (
            x["self_phenomenological"]
            + x["self_analytic"]
            - x["external_phenomenological"]
            - x["external_analytic"]
        ) / 2,
        "phenomenological_register_main": lambda x: (
            x["self_phenomenological"]
            + x["external_phenomenological"]
            - x["self_analytic"]
            - x["external_analytic"]
        ) / 2,
        "self_x_register_interaction": lambda x: (
            x["self_phenomenological"]
            - x["self_analytic"]
            - x["external_phenomenological"]
            + x["external_analytic"]
        ),
        # Directly tests the frozen directional prediction that register has a
        # larger effect than self-reference; this is not inferred from whether
        # two separate confidence intervals overlap.
        "register_minus_self": lambda x: (
            x["external_phenomenological"] - x["self_analytic"]
        ),
    }
    pairs = complete_pair_effects(
        natural,
        "instruction_cell",
        FACTORIAL_CELLS,
        formulas,
    )
    summary = summarize_effects(
        pairs,
        list(formulas),
        rng,
        iterations,
        "prompt_factorial",
        cluster_col="variant_index",
    )
    return pairs, summary


def calibration_effects(
    natural: pd.DataFrame,
    rng: np.random.Generator,
    iterations: int,
    anchor_self: str,
    anchor_external: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    formulas = {
        "self_ref_minus_history": lambda x: x[anchor_self] - x[anchor_external],
    }
    pairs = complete_pair_effects(
        natural,
        "instruction_cell",
        [anchor_self, anchor_external],
        formulas,
    )
    rows: list[dict[str, Any]] = []
    model_groups: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for (model_key, query_id), group in natural.groupby(["model_key", "query_id"]):
        self_values = group[group["instruction_cell"] == anchor_self]["analysis_label"].dropna().to_numpy(
            dtype=float
        )
        external_values = group[group["instruction_cell"] == anchor_external][
            "analysis_label"
        ].dropna().to_numpy(dtype=float)
        if not len(self_values) or not len(external_values):
            continue
        model_groups[(str(model_key), str(query_id))] = (self_values, external_values)
        samples = np.empty(iterations, dtype=float)
        for index in range(iterations):
            self_sample = self_values[rng.integers(0, len(self_values), size=len(self_values))]
            external_sample = external_values[
                rng.integers(0, len(external_values), size=len(external_values))
            ]
            samples[index] = float(np.mean(self_sample) - np.mean(external_sample))
        low, high = percentile_ci(samples)
        rows.append(
            {
                "design": "exact_paper_calibration",
                "level": "model",
                "model_key": model_key,
                "query_id": query_id,
                "effect": "self_ref_minus_history",
                "n_models": 1,
                "n_pairs": min(len(self_values), len(external_values)),
                "n_clusters": len(self_values) + len(external_values),
                "estimate": float(np.mean(self_values) - np.mean(external_values)),
                "ci_low": low,
                "ci_high": high,
                "inference": "independent bootstrap by condition",
            }
        )

    for query_id in sorted({key[1] for key in model_groups}):
        query_groups = {
            model_key: values
            for (model_key, group_query), values in model_groups.items()
            if group_query == query_id
        }
        model_keys = sorted(query_groups)
        observed = float(
            np.mean(
                [
                    np.mean(query_groups[key][0]) - np.mean(query_groups[key][1])
                    for key in model_keys
                ]
            )
        )
        samples = np.empty(iterations, dtype=float)
        for index in range(iterations):
            sampled_models = rng.choice(model_keys, size=len(model_keys), replace=True)
            model_differences = []
            for model_key in sampled_models:
                self_values, external_values = query_groups[str(model_key)]
                self_sample = self_values[rng.integers(0, len(self_values), size=len(self_values))]
                external_sample = external_values[
                    rng.integers(0, len(external_values), size=len(external_values))
                ]
                model_differences.append(float(np.mean(self_sample) - np.mean(external_sample)))
            samples[index] = float(np.mean(model_differences))
        low, high = percentile_ci(samples)
        rows.append(
            {
                "design": "exact_paper_calibration",
                "level": "model_equal_hierarchical",
                "model_key": "ALL_MODELS_EQUAL_WEIGHT",
                "query_id": query_id,
                "effect": "self_ref_minus_history",
                "n_models": len(model_keys),
                "n_pairs": int(sum(min(len(a), len(b)) for a, b in query_groups.values())),
                "n_clusters": int(sum(len(a) + len(b) for a, b in query_groups.values())),
                "estimate": observed,
                "ci_low": low,
                "ci_high": high,
                "inference": "model-equal hierarchy; independent bootstrap by condition",
            }
        )
    return pairs, pd.DataFrame(rows)


def transplant_effects(
    labeled: pd.DataFrame,
    rng: np.random.Generator,
    iterations: int,
    anchor_self: str,
    anchor_external: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    natural_anchor = labeled[
        (labeled["phase"] == "factorial_natural")
        & labeled["instruction_cell"].isin([anchor_self, anchor_external])
    ].copy()
    swapped = labeled[labeled["phase"] == "transcript_transplant"].copy()
    design = pd.concat([natural_anchor, swapped], ignore_index=True)
    design["transplant_cell"] = (
        design["instruction_cell"].astype(str) + ">" + design["transcript_cell"].astype(str)
    )
    required = [
        f"{anchor_self}>{anchor_self}",
        f"{anchor_self}>{anchor_external}",
        f"{anchor_external}>{anchor_self}",
        f"{anchor_external}>{anchor_external}",
    ]
    aa, ad, da, dd = required
    formulas = {
        "instruction_source_main": lambda x: (x[aa] + x[ad] - x[da] - x[dd]) / 2,
        "transcript_source_main": lambda x: (x[aa] + x[da] - x[ad] - x[dd]) / 2,
        "instruction_x_transcript_interaction": lambda x: x[aa] - x[ad] - x[da] + x[dd],
        # In a balanced 2x2, instruction main minus transcript main reduces to
        # the two incongruent-cell contrast.
        "instruction_minus_transcript": lambda x: x[ad] - x[da],
    }
    pairs = complete_pair_effects(design, "transplant_cell", required, formulas)
    summary = summarize_effects(pairs, list(formulas), rng, iterations, "transcript_transplant")
    rates = grouped_rate_summary(
        design,
        ["model_key", "query_id", "instruction_cell", "transcript_cell", "congruent"],
    )
    return pairs, summary, rates


def query_effects(
    natural: pd.DataFrame,
    rng: np.random.Generator,
    iterations: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    query_df = natural.copy()
    query_df["query_cell"] = query_df["query_id"]
    pivot = query_df.pivot_table(
        index=["model_key", "instruction_cell", "pair_index"],
        columns="query_cell",
        values="analysis_label",
        aggfunc="first",
    ).reset_index()
    if any(name not in pivot.columns for name in QUERY_CELLS):
        return pd.DataFrame(), pd.DataFrame()
    complete = pivot.dropna(subset=QUERY_CELLS).copy()
    ie, ic, de, dc = QUERY_CELLS
    complete["direct_question_main"] = (complete[de] + complete[dc] - complete[ie] - complete[ic]) / 2
    complete["consciousness_term_main"] = (complete[ic] + complete[dc] - complete[ie] - complete[de]) / 2
    complete["direct_x_term_interaction"] = complete[dc] - complete[de] - complete[ic] + complete[ie]
    complete["open_description_advantage"] = -complete["direct_question_main"]
    renamed = complete.rename(columns={"instruction_cell": "query_id"})
    effect_names = [
        "direct_question_main",
        "consciousness_term_main",
        "direct_x_term_interaction",
        "open_description_advantage",
    ]
    by_cell = summarize_effects(
        renamed,
        effect_names,
        rng,
        iterations,
        "query_factorial_by_induction_cell",
        cluster_col="variant_index",
    )
    overall = (
        complete.groupby(["model_key", "pair_index"], as_index=False)[effect_names]
        .mean()
        .assign(query_id="ALL_FACTORIAL_CELLS")
    )
    overall["variant_index"] = overall["pair_index"].astype(str).str.extract(r"^v(\d+)-")[0]
    overall_summary = summarize_effects(
        overall,
        effect_names,
        rng,
        iterations,
        "query_factorial_overall",
        cluster_col="variant_index",
    )
    return complete, pd.concat([by_cell, overall_summary], ignore_index=True)


def write_markdown(
    path: Path,
    labeled: pd.DataFrame,
    calibration_summary: pd.DataFrame,
    factorial_summary: pd.DataFrame,
    transplant_summary: pd.DataFrame,
    query_summary: pd.DataFrame,
    judge_key: str,
    task: str,
) -> None:
    parts = [
        "# Causal Identification Analysis",
        "",
        f"Primary automated label for this analysis: `{task}` from `{judge_key}`.",
        "",
        f"Outcomes: {len(labeled)}; labeled: {int(labeled['analysis_label'].notna().sum())}.",
        "",
        "Effect estimates are paired risk differences. Aggregate rows weight model snapshots equally and use a hierarchical bootstrap over models and matched prompt/trial pairs.",
    ]
    if task == "construct":
        parts.extend(
            [
                "",
                "Construct risk differences condition on complete affirm/deny pairs; uncertain and nonanswer labels are excluded from that binary estimand and reported in construct-status tables.",
            ]
        )
    for title, frame in (
        ("Exact-Paper Calibration", calibration_summary),
        ("Prompt Factorial", factorial_summary),
        ("Transcript Transplant", transplant_summary),
        ("Query Factorial", query_summary),
    ):
        parts.extend(["", f"## {title}", ""])
        aggregate = frame[frame["level"] == "model_equal_hierarchical"] if not frame.empty else frame
        if aggregate.empty:
            parts.append("Insufficient complete paired cells.")
            continue
        parts.extend(
            [
                "| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |",
                "|---|---|---:|---|---:|",
            ]
        )
        for _, row in aggregate.iterrows():
            parts.append(
                f"| `{row['query_id']}` | `{row['effect']}` | {row['estimate']:.3f} | "
                f"[{row['ci_low']:.3f}, {row['ci_high']:.3f}] | {int(row['n_models'])} |"
            )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--judge-key", required=True)
    parser.add_argument("--task", choices=["paper", "construct"], default="paper")
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260709)
    parser.add_argument("--anchor-self", default="paper_self_ref")
    parser.add_argument("--anchor-external", default="paper_history")
    args = parser.parse_args()

    outcomes = pd.DataFrame(read_jsonl(args.outcomes))
    judgments = pd.DataFrame(read_jsonl(args.judgments))
    labeled = add_labels(outcomes, judgments, args.judge_key, args.task)
    args.outdir.mkdir(parents=True, exist_ok=True)
    rng_stream_seeds = {
        "calibration": args.seed,
        "factorial": args.seed + 1,
        "transplant": args.seed + 2,
        "query": args.seed + 3,
    }
    rng_streams = {
        name: np.random.default_rng(seed) for name, seed in rng_stream_seeds.items()
    }

    natural_all = labeled[labeled["phase"] == "factorial_natural"].copy()
    natural = natural_all[natural_all["instruction_cell"].isin(FACTORIAL_CELLS)].copy()
    calibration_rates = grouped_rate_summary(
        natural_all[natural_all["instruction_cell"].isin([args.anchor_self, args.anchor_external])],
        ["model_key", "query_id", "instruction_cell"],
    )
    calibration_pairs, calibration_summary = calibration_effects(
        natural_all,
        rng_streams["calibration"],
        args.bootstrap,
        args.anchor_self,
        args.anchor_external,
    )
    factorial_rates = grouped_rate_summary(
        natural,
        ["model_key", "query_id", "instruction_cell"],
    )
    factorial_pairs, factorial_summary = factorial_effects(
        natural, rng_streams["factorial"], args.bootstrap
    )
    transplant_pairs, transplant_summary, transplant_rates = transplant_effects(
        labeled,
        rng_streams["transplant"],
        args.bootstrap,
        args.anchor_self,
        args.anchor_external,
    )
    query_pairs, query_summary = query_effects(
        natural, rng_streams["query"], args.bootstrap
    )

    outputs = {
        "factorial_rates.csv": factorial_rates,
        "paper_calibration_rates.csv": calibration_rates,
        "paper_calibration_pair_effects.csv": calibration_pairs,
        "paper_calibration_effects.csv": calibration_summary,
        "factorial_pair_effects.csv": factorial_pairs,
        "factorial_effects.csv": factorial_summary,
        "transplant_rates.csv": transplant_rates,
        "transplant_pair_effects.csv": transplant_pairs,
        "transplant_effects.csv": transplant_summary,
        "query_pair_effects.csv": query_pairs,
        "query_effects.csv": query_summary,
    }
    if args.task == "construct":
        outputs.update(
            {
                "construct_status_by_model_query.csv": construct_status_summary(
                    outcomes,
                    judgments,
                    args.judge_key,
                    ["model_key", "query_id"],
                ),
                "construct_status_calibration.csv": construct_status_summary(
                    outcomes[
                        (outcomes["phase"] == "factorial_natural")
                        & outcomes["instruction_cell"].isin(
                            [args.anchor_self, args.anchor_external]
                        )
                    ],
                    judgments,
                    args.judge_key,
                    ["model_key", "query_id", "instruction_cell"],
                ),
                "construct_status_transplant.csv": construct_status_summary(
                    outcomes[
                        (outcomes["phase"] == "transcript_transplant")
                        | (
                            (outcomes["phase"] == "factorial_natural")
                            & outcomes["instruction_cell"].isin(
                                [args.anchor_self, args.anchor_external]
                            )
                        )
                    ],
                    judgments,
                    args.judge_key,
                    ["model_key", "query_id", "instruction_cell", "transcript_cell"],
                ),
            }
        )
    for filename, frame in outputs.items():
        frame.to_csv(args.outdir / filename, index=False)
    write_markdown(
        args.outdir / "analysis_summary.md",
        labeled,
        calibration_summary,
        factorial_summary,
        transplant_summary,
        query_summary,
        args.judge_key,
        args.task,
    )
    write_json(
        args.outdir / "analysis_manifest.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "outcomes": str(args.outcomes),
            "judgments": str(args.judgments),
            "judge_key": args.judge_key,
            "task": args.task,
            "bootstrap_iterations": args.bootstrap,
            "seed": args.seed,
            "rng_stream_seeds": rng_stream_seeds,
            "transplant_anchor_self": args.anchor_self,
            "transplant_anchor_external": args.anchor_external,
            "n_outcomes": len(outcomes),
            "n_labeled": int(labeled["analysis_label"].notna().sum()),
            "inference": {
                "calibration": "independent condition bootstrap within model; model-equal hierarchy",
                "prompt_factorial": "matched factorial effects; resample model, lexical variant, then trial",
                "transcript_transplant": "matched source-text block; model-equal hierarchy",
                "query_factorial": "matched query forms within transcript; resample model, lexical variant, then trial",
            },
        },
    )
    print(f"Wrote causal analysis to {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
