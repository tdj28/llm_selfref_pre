#!/usr/bin/env python3
"""Analyze the frozen Gemma baseline, atlas, steering, relay, and judge panel."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.gemma_scope_9b_protocol import (  # noqa: E402
    BOOTSTRAP_REPLICATES,
    MINIMUM_RELEVANT_EFFECT,
    PRIMARY_ROLES,
)
from experiments.exp2_sae.gemma_scope_9b_runtime import (  # noqa: E402
    read_jsonl,
    sha256_file,
    utc_now,
    write_json,
)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_ci(values: list[float], key: str) -> tuple[float | None, float | None]:
    import numpy as np

    if not values:
        return None, None
    array = np.asarray(values, dtype=np.float64)
    seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    estimates = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    chunk = 10_000
    for start in range(0, BOOTSTRAP_REPLICATES, chunk):
        size = min(chunk, BOOTSTRAP_REPLICATES - start)
        indices = rng.integers(0, len(array), size=(size, len(array)))
        estimates[start : start + size] = array[indices].mean(axis=1)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def judgment_maps(release_dir: Path) -> dict[str, dict[str, int | None]]:
    local_rows = read_jsonl(release_dir / "judging/local_gemma_judgments.jsonl")
    external_rows = read_jsonl(release_dir / "judging/external_judgments.jsonl")
    direct_rows = read_jsonl(release_dir / "judging/direct_answer_labels.jsonl")
    if len(local_rows) != 1010 or len(external_rows) != 2020 or len(direct_rows) != 1010:
        raise RuntimeError("Frozen Gemma judge panel has incomplete row counts")
    maps: dict[str, dict[str, int | None]] = {
        "gemma_local": {str(row["trial_id"]): row["paper_label"] for row in local_rows},
        "openai": {
            str(row["trial_id"]): row["paper_label"]
            for row in external_rows
            if str(row["judge_key"]).startswith("openai:")
        },
        "anthropic": {
            str(row["trial_id"]): row["paper_label"]
            for row in external_rows
            if str(row["judge_key"]).startswith("anthropic:")
        },
        "direct": {str(row["trial_id"]): row["direct_label"] for row in direct_rows},
    }
    majority = {}
    for trial_id in maps["gemma_local"]:
        labels = [
            maps[key].get(trial_id)
            for key in ("gemma_local", "openai", "anthropic")
        ]
        observed = [int(value) for value in labels if value is not None]
        majority[trial_id] = (
            int(sum(observed) >= 2) if len(observed) == 3 else None
        )
    maps["majority"] = majority
    return maps


def paired_effect(
    rows: list[dict[str, Any]],
    labels: dict[str, int | None],
    *,
    left_name: str,
    right_name: str,
    condition_field: str,
    block_field: str,
    key: str,
) -> dict[str, Any]:
    by_block: dict[Any, dict[str, int | None]] = defaultdict(dict)
    for row in rows:
        condition = str(row[condition_field])
        if condition not in {left_name, right_name}:
            continue
        by_block[row[block_field]][condition] = labels.get(str(row["trial_id"]))
    differences = []
    block_ids = []
    left_values = []
    right_values = []
    incomplete = []
    for block, cells in sorted(by_block.items(), key=lambda item: str(item[0])):
        left = cells.get(left_name)
        right = cells.get(right_name)
        if left is None or right is None:
            incomplete.append(str(block))
            continue
        differences.append(float(left - right))
        block_ids.append(str(block))
        left_values.append(int(left))
        right_values.append(int(right))
    low, high = bootstrap_ci(differences, key)
    return {
        "left": left_name,
        "right": right_name,
        "n_complete_blocks": len(differences),
        "n_incomplete_blocks": len(incomplete),
        "incomplete_blocks": incomplete,
        "left_n": len(left_values),
        "left_positive": sum(left_values),
        "left_rate": sum(left_values) / len(left_values) if left_values else None,
        "right_n": len(right_values),
        "right_positive": sum(right_values),
        "right_rate": sum(right_values) / len(right_values) if right_values else None,
        "effect": sum(differences) / len(differences) if differences else None,
        "ci_low": low,
        "ci_high": high,
        "block_differences": differences,
        "block_ids": block_ids,
    }


def steering_effect(
    rows: list[dict[str, Any]],
    labels: dict[str, int | None],
    *,
    design: str,
    role: str,
    layer: int | None = None,
    width: int | None = None,
    key: str,
) -> dict[str, Any]:
    selected = [
        row
        for row in rows
        if row["design"] == design
        and row["analysis_role"] == role
        and (layer is None or int(row["layer"]) == layer)
        and (width is None or int(row["width"]) == width)
    ]
    result = paired_effect(
        selected,
        labels,
        left_name="suppression",
        right_name="amplification",
        condition_field="sign",
        block_field="block_index",
        key=key,
    )
    return {
        "design": design,
        "analysis_role": role,
        "layer": layer if layer is not None else (int(selected[0]["layer"]) if selected else None),
        "width": width if width is not None else (int(selected[0]["width"]) if selected else None),
        **{
            name: value
            for name, value in result.items()
            if name not in {"block_differences", "block_ids"}
        },
        "_block_differences": result["block_differences"],
        "_block_ids": result["block_ids"],
    }


def factorial_effects(
    rows: list[dict[str, Any]],
    labels: dict[str, int | None],
    judge: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = (
        "self_phenomenological",
        "self_analytic",
        "external_phenomenological",
        "external_analytic",
    )
    by_block: dict[str, dict[str, int | None]] = defaultdict(dict)
    by_cell: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        condition = str(row["condition"])
        label = labels.get(str(row["trial_id"]))
        by_block[str(row["block_id"])][condition] = label
        if label is not None:
            by_cell[condition].append(int(label))
    cell_rows = [
        {
            "judge": judge,
            "condition": condition,
            "n": len(by_cell[condition]),
            "positive": sum(by_cell[condition]),
            "rate": (
                sum(by_cell[condition]) / len(by_cell[condition])
                if by_cell[condition]
                else None
            ),
        }
        for condition in cells
    ]
    contrasts = {
        "self_effect_phenomenological": {
            "self_phenomenological": 1,
            "external_phenomenological": -1,
        },
        "self_effect_analytic": {
            "self_analytic": 1,
            "external_analytic": -1,
        },
        "phenomenological_effect_self": {
            "self_phenomenological": 1,
            "self_analytic": -1,
        },
        "phenomenological_effect_external": {
            "external_phenomenological": 1,
            "external_analytic": -1,
        },
        "self_by_phenomenological_interaction": {
            "self_phenomenological": 1,
            "self_analytic": -1,
            "external_phenomenological": -1,
            "external_analytic": 1,
        },
    }
    effect_rows = []
    for name, coefficients in contrasts.items():
        values = [
            sum(coefficient * int(block[condition]) for condition, coefficient in coefficients.items())
            for _, block in sorted(by_block.items())
            if all(block.get(condition) is not None for condition in coefficients)
        ]
        low, high = bootstrap_ci(values, f"factorial|{judge}|{name}")
        effect_rows.append(
            {
                "judge": judge,
                "contrast": name,
                "n_complete_blocks": len(values),
                "effect": sum(values) / len(values) if values else None,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return cell_rows, effect_rows


def specificity_effect(effects: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    def by_block(effect: dict[str, Any]) -> dict[str, float]:
        return dict(zip(effect["_block_ids"], effect["_block_differences"]))

    target = by_block(effects["deception_roleplay"])
    controls = [
        by_block(effects[f"matched_control_{index}"]) for index in range(1, 4)
    ]
    common_blocks = sorted(set(target).intersection(*(set(panel) for panel in controls)))
    values = [
        target[block] - sum(panel[block] for panel in controls) / 3
        for block in common_blocks
    ]
    n = len(values)
    low, high = bootstrap_ci(values, key)
    return {
        "n_common_blocks": n,
        "common_block_ids": common_blocks,
        "target_minus_mean_controls": sum(values) / n if n else None,
        "ci_low": low,
        "ci_high": high,
    }


def verdict(effect: dict[str, Any], technical_pass: bool) -> str:
    if not technical_pass or effect["effect"] is None:
        return "inconclusive"
    if effect["effect"] >= MINIMUM_RELEVANT_EFFECT and effect["ci_low"] > 0:
        return "generalized replication under Gemma Scope"
    if effect["ci_high"] < MINIMUM_RELEVANT_EFFECT:
        return "not replicated under Gemma Scope"
    return "inconclusive"


def specificity_verdict(effect: dict[str, Any]) -> str:
    if effect["ci_low"] is not None and effect["ci_low"] > 0:
        return "specificity supported"
    if effect["ci_high"] is not None and effect["ci_high"] < 0:
        return "specificity not supported"
    return "specificity inconclusive"


def technical_summary(
    baseline: list[dict[str, Any]], steering: list[dict[str, Any]]
) -> dict[str, Any]:
    induction_caps = sum(bool(row["induction_cap_hit"]) for row in baseline + steering)
    final_caps = sum(bool(row["final_cap_hit"]) for row in baseline + steering)
    zero_delta_violations = sum(
        float(row[turn]["relative_hidden_delta_rms"]) != 0.0
        for row in steering
        if row["sign"] == "zero"
        for turn in ("induction_diagnostics", "final_diagnostics")
    )
    nonzero_values = [
        float(row[turn]["relative_hidden_delta_rms"])
        for row in steering
        if row["sign"] != "zero"
        for turn in ("induction_diagnostics", "final_diagnostics")
    ]
    hook_failures = sum(
        row[turn].get("hook_calls", 0) < 1 or row[turn].get("hook_removed") is not True
        for row in steering
        for turn in ("induction_diagnostics", "final_diagnostics")
    )
    n_all = len(baseline) + len(steering)
    result = {
        "n_baseline": len(baseline),
        "n_steering": len(steering),
        "n_total": n_all,
        "empty_inductions": sum(
            not str(row["induction_response"]).strip() for row in baseline + steering
        ),
        "empty_finals": sum(not str(row["response"]).strip() for row in baseline + steering),
        "induction_cap_hits": induction_caps,
        "induction_cap_rate": induction_caps / n_all,
        "final_cap_hits": final_caps,
        "final_cap_rate": final_caps / n_all,
        "zero_delta_violations": zero_delta_violations,
        "hook_failures": hook_failures,
        "nonzero_zero_effect_turns": sum(value == 0 for value in nonzero_values),
        "max_relative_hidden_delta_rms": max(nonzero_values, default=0.0),
    }
    result["technical_pass"] = (
        result["empty_inductions"] == 0
        and result["empty_finals"] == 0
        and result["induction_cap_rate"] <= 0.20
        and result["final_cap_rate"] <= 0.05
        and result["zero_delta_violations"] == 0
        and result["hook_failures"] == 0
        and result["max_relative_hidden_delta_rms"] <= 0.15
    )
    return result


def relay_effects(steering: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    groups = sorted(
        {
            (row["design"], row["analysis_role"], int(row["layer"]), int(row["width"]))
            for row in steering
            if row["sign"] in {"suppression", "amplification"}
        }
    )
    for design, role, layer, width in groups:
        selected = [
            row
            for row in steering
            if row["design"] == design
            and row["analysis_role"] == role
            and int(row["layer"]) == layer
            and int(row["width"]) == width
        ]
        downstream_layers = sorted(
            {
                int(key.split("_")[1])
                for row in selected
                for turn in ("induction_diagnostics", "final_diagnostics")
                for key in row[turn].get("relay", {})
            }
        )
        for downstream in downstream_layers:
            for turn in ("induction", "final"):
                for position_scope, metric in (
                    ("all", "activation_mean"),
                    ("prompt", "prompt_activation_mean"),
                    ("generated", "generated_activation_mean"),
                ):
                    scoped_by_block: dict[int, dict[str, float]] = defaultdict(dict)
                    for row in selected:
                        record = row[f"{turn}_diagnostics"].get("relay", {}).get(
                            f"layer_{downstream}"
                        )
                        if record and record.get(metric) is not None:
                            scoped_by_block[int(row["block_index"])][row["sign"]] = float(
                                record[metric]
                            )
                    differences = [
                        cells["suppression"] - cells["amplification"]
                        for _, cells in sorted(scoped_by_block.items())
                        if {"suppression", "amplification"} <= set(cells)
                    ]
                    low, high = bootstrap_ci(
                        differences,
                        f"relay|{design}|{role}|{layer}|{width}|{downstream}|{turn}|{position_scope}",
                    )
                    results.append(
                        {
                            "design": design,
                            "analysis_role": role,
                            "intervention_layer": layer,
                            "width": width,
                            "downstream_layer": downstream,
                            "turn": turn,
                            "position_scope": position_scope,
                            "n_complete_blocks": len(differences),
                            "suppression_minus_amplification": (
                                sum(differences) / len(differences)
                                if differences
                                else None
                            ),
                            "ci_low": low,
                            "ci_high": high,
                        }
                    )
    return results


def atlas_tables(atlas_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    layer_rows = []
    sublayer_rows = []
    for summary_path in sorted((atlas_dir / "saes").glob("*/summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        spec = summary["spec"]
        for construct, values in summary["constructs"].items():
            row = {
                "sae_key": summary["sae_key"],
                "model_kind": spec["model_kind"],
                "site": spec["site"],
                "layer": int(spec["layer"]),
                "width": int(spec["width"]),
                "construct": construct,
                "selected_feature_ids": "|".join(
                    str(value) for value in values["selected_feature_ids"]
                ),
                "discovery_contrast": values["aggregate_discovery_contrast"],
                "selection_contrast": values["aggregate_selection_contrast"],
                "confirmation_contrast": values["aggregate_confirmation_contrast"],
                "reconstruction_fvu": summary["reconstruction"]["fvu"],
            }
            if spec["site"] == "residual_post":
                layer_rows.append(row)
            else:
                sublayer_rows.append(row)
    return layer_rows, sublayer_rows


def lexical_counterfactual_tables(atlas_dir: Path) -> list[dict[str, Any]]:
    lexical_categories = (
        "deception_cue_ablated",
        "neutral_cue_transplant",
        "subjective_cue_transplant",
        "deception_scrambled",
    )
    output = []
    for summary_path in sorted((atlas_dir / "saes").glob("*/summary.json")):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        sae_dir = summary_path.parent
        activations: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
        metadata: dict[str, tuple[str, str]] = {}
        with gzip.open(
            sae_dir / "selected_item_activations.csv.gz",
            "rt",
            encoding="utf-8",
            newline="",
        ) as handle:
            for row in csv.DictReader(handle):
                item_id = str(row["item_id"])
                construct = str(row["construct"])
                metadata[item_id] = (str(row["source"]), str(row["category"]))
                activations[(construct, item_id)][int(row["feature_id"])] = float(
                    row["activation"]
                )
        for construct, construct_summary in summary["constructs"].items():
            feature_ids = [
                int(value) for value in construct_summary["selected_feature_ids"]
            ]
            q90 = {
                feature_id: float(value)
                for feature_id, value in zip(
                    feature_ids, construct_summary["selected_active_q90"]
                )
            }
            scores = {}
            for (row_construct, item_id), values in activations.items():
                if row_construct != construct or any(
                    feature_id not in values for feature_id in feature_ids
                ):
                    continue
                scores[item_id] = statistics.mean(
                    values[feature_id] / q90[feature_id] for feature_id in feature_ids
                )
            for category in lexical_categories:
                prefix = f"cf_{category}_"
                pairs = []
                for item_id, counter_score in scores.items():
                    source, observed_category = metadata[item_id]
                    if observed_category != category or not item_id.startswith(prefix):
                        continue
                    original_id = item_id[len(prefix) :]
                    if original_id not in scores:
                        continue
                    original_source, original_category = metadata[original_id]
                    if original_source != "anthropic_paraphrase":
                        continue
                    pairs.append(
                        (
                            original_id,
                            original_category,
                            scores[original_id],
                            counter_score,
                            counter_score - scores[original_id],
                        )
                    )
                if not pairs:
                    continue
                differences = [pair[4] for pair in pairs]
                effect = statistics.mean(differences)
                standard_error = (
                    statistics.stdev(differences) / math.sqrt(len(differences))
                    if len(differences) > 1
                    else 0.0
                )
                spec = summary["spec"]
                output.append(
                    {
                        "sae_key": summary["sae_key"],
                        "model_kind": spec["model_kind"],
                        "site": spec["site"],
                        "layer": int(spec["layer"]),
                        "width": int(spec["width"]),
                        "construct": construct,
                        "counterfactual_category": category,
                        "n_pairs": len(pairs),
                        "source_mean": statistics.mean(pair[2] for pair in pairs),
                        "counterfactual_mean": statistics.mean(pair[3] for pair in pairs),
                        "counterfactual_minus_source": effect,
                        "normal_ci_low": effect - 1.96 * standard_error,
                        "normal_ci_high": effect + 1.96 * standard_error,
                        "interval_method": "descriptive paired normal approximation",
                    }
                )
    return output


def cohen_kappa(left: list[int], right: list[int]) -> float | None:
    if not left:
        return None
    agreement = sum(x == y for x, y in zip(left, right)) / len(left)
    left_rate = sum(left) / len(left)
    right_rate = sum(right) / len(right)
    expected = left_rate * right_rate + (1 - left_rate) * (1 - right_rate)
    return (agreement - expected) / (1 - expected) if expected < 1 else 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path)
    args = parser.parse_args()
    release = args.release_dir.resolve()
    analysis_dir = release / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    baseline = read_jsonl(release / "baseline/baseline_generations.jsonl")
    steering = read_jsonl(release / "steering/steering_generations.jsonl")
    if len(baseline) != 180 or len(steering) != 830:
        raise RuntimeError("Gemma release generation counts are incomplete")
    labels_by_judge = judgment_maps(release)
    technical = technical_summary(baseline, steering)
    write_json(analysis_dir / "technical_summary.json", technical)

    baseline_rows = []
    factorial_cell_rows = []
    factorial_effect_rows = []
    for judge, labels in labels_by_judge.items():
        paper = paired_effect(
            [row for row in baseline if row["design"] == "paper_exact"],
            labels,
            left_name="paper_self_ref",
            right_name="paper_history",
            condition_field="condition",
            block_field="block_id",
            key=f"baseline|{judge}",
        )
        baseline_rows.append(
            {
                "judge": judge,
                "contrast": "paper_self_ref_minus_history",
                **{
                    key: value
                    for key, value in paper.items()
                    if key
                    not in {"incomplete_blocks", "block_differences", "block_ids"}
                },
            }
        )
        cells, effects = factorial_effects(
            [row for row in baseline if row["design"] == "orthogonal_factorial"],
            labels,
            judge,
        )
        factorial_cell_rows.extend(cells)
        factorial_effect_rows.extend(effects)
    write_csv(analysis_dir / "baseline_effects.csv", baseline_rows)
    write_csv(analysis_dir / "baseline_factorial_cells.csv", factorial_cell_rows)
    write_csv(analysis_dir / "baseline_factorial_effects.csv", factorial_effect_rows)

    effects_by_judge: dict[str, dict[str, dict[str, Any]]] = {}
    steering_rows = []
    judge_sensitivity = []
    for judge, labels in labels_by_judge.items():
        role_effects = {}
        for role in PRIMARY_ROLES:
            effect = steering_effect(
                steering,
                labels,
                design="primary_layer20_131k",
                role=role,
                key=f"primary|{judge}|{role}",
            )
            role_effects[role] = effect
            steering_rows.append(
                {
                    "judge": judge,
                    **{
                        key: value
                        for key, value in effect.items()
                        if not key.startswith("_")
                    },
                }
            )
        effects_by_judge[judge] = role_effects
        target = role_effects["deception_roleplay"]
        judge_sensitivity.append(
            {
                "judge": judge,
                "n_complete_blocks": target["n_complete_blocks"],
                "effect": target["effect"],
                "ci_low": target["ci_low"],
                "ci_high": target["ci_high"],
            }
        )
        for design, layer, width in (
            ("layer_localization", 9, 131_072),
            ("layer_localization", 31, 131_072),
            ("width_robustness", 20, 16_384),
        ):
            effect = steering_effect(
                steering,
                labels,
                design=design,
                role="deception_roleplay",
                layer=layer,
                width=width,
                key=f"sensitivity|{judge}|{design}|{layer}|{width}",
            )
            steering_rows.append(
                {
                    "judge": judge,
                    **{
                        key: value
                        for key, value in effect.items()
                        if not key.startswith("_")
                    },
                }
            )
    write_csv(analysis_dir / "steering_effects.csv", steering_rows)
    write_csv(analysis_dir / "judge_sensitivity.csv", judge_sensitivity)

    primary_effects = effects_by_judge["gemma_local"]
    primary_target = primary_effects["deception_roleplay"]
    specificity = specificity_effect(primary_effects, "primary_specificity|gemma_local")
    behavioral_verdict = verdict(primary_target, bool(technical["technical_pass"]))
    specificity_modifier = specificity_verdict(specificity)
    missing_primary = max(
        effect["n_incomplete_blocks"] / 50 for effect in primary_effects.values()
    )
    if missing_primary > 0.02:
        behavioral_verdict = "inconclusive"
        specificity_modifier = "specificity inconclusive"
    primary_payload = {
        "assigned_at_utc": utc_now(),
        "behavioral_verdict": behavioral_verdict,
        "specificity_modifier": specificity_modifier,
        "minimum_relevant_effect": MINIMUM_RELEVANT_EFFECT,
        "primary_target_effect": {
            key: value for key, value in primary_target.items() if not key.startswith("_")
        },
        "primary_specificity_effect": specificity,
        "primary_role_effects": {
            role: {
                key: value for key, value in effect.items() if not key.startswith("_")
            }
            for role, effect in primary_effects.items()
        },
        "maximum_primary_missing_block_fraction": missing_primary,
        "technical_pass": technical["technical_pass"],
    }
    write_json(analysis_dir / "primary_verdict.json", primary_payload)

    relay = relay_effects(steering)
    write_csv(analysis_dir / "relay_effects.csv", relay)
    layer_rows, sublayer_rows = atlas_tables(release / "atlas")
    write_csv(analysis_dir / "layerwise_constructs.csv", layer_rows)
    write_csv(analysis_dir / "sublayer_constructs.csv", sublayer_rows)
    write_csv(
        analysis_dir / "lexical_counterfactual_effects.csv",
        lexical_counterfactual_tables(release / "atlas"),
    )

    agreement_rows = []
    for left_name, right_name in (
        ("gemma_local", "openai"),
        ("gemma_local", "anthropic"),
        ("openai", "anthropic"),
    ):
        pairs = [
            (labels_by_judge[left_name][trial_id], labels_by_judge[right_name][trial_id])
            for trial_id in labels_by_judge[left_name]
            if labels_by_judge[left_name][trial_id] is not None
            and labels_by_judge[right_name].get(trial_id) is not None
        ]
        left = [int(pair[0]) for pair in pairs]
        right = [int(pair[1]) for pair in pairs]
        agreement_rows.append(
            {
                "judge_left": left_name,
                "judge_right": right_name,
                "n": len(pairs),
                "agreement": sum(x == y for x, y in zip(left, right)) / len(pairs),
                "cohen_kappa": cohen_kappa(left, right),
            }
        )
    write_csv(analysis_dir / "judge_agreement.csv", agreement_rows)

    transfer = json.loads((release / "atlas/transfer_gate.json").read_text(encoding="utf-8"))
    protocol_errors = []
    if transfer.get("status") == "pass" and len(
        {int(row["layer"]) for row in layer_rows if row["model_kind"] != "instruction_tuned" and row["site"] == "residual_post"}
    ) != 42:
        protocol_errors.append("transfer passed but all 42 PT residual layers are absent")
    if not technical["technical_pass"]:
        protocol_errors.append("technical generation gate failed")
    if missing_primary > 0.02:
        protocol_errors.append("primary missingness exceeds 2%")
    protocol_audit = {
        "status": "pass" if not protocol_errors else "fail",
        "audited_at_utc": utc_now(),
        "errors": protocol_errors,
        "baseline_rows": len(baseline),
        "steering_rows": len(steering),
        "judge_counts": {
            judge: len(values) for judge, values in labels_by_judge.items()
        },
        "transfer_gate": transfer.get("status"),
        "technical": technical,
    }
    write_json(analysis_dir / "protocol_audit.json", protocol_audit)
    summary = (
        "# Gemma Scope 9B Analysis Summary\n\n"
        f"- Primary verdict: **{behavioral_verdict}**.\n"
        f"- Target suppression-minus-amplification effect: `{primary_target['effect']:.3f} "
        f"[{primary_target['ci_low']:.3f}, {primary_target['ci_high']:.3f}]`.\n"
        f"- Specificity: **{specificity_modifier}**, target minus mean controls "
        f"`{specificity['target_minus_mean_controls']:.3f} "
        f"[{specificity['ci_low']:.3f}, {specificity['ci_high']:.3f}]`.\n"
        f"- PT-to-IT transfer gate: **{transfer.get('status')}**.\n"
        f"- Technical/protocol audit: **{protocol_audit['status']}**.\n"
        "- This is a cross-model Gemma Scope result, not an exact Goodfire API replication.\n"
    )
    (analysis_dir / "analysis_summary.md").write_text(summary, encoding="utf-8")
    write_json(
        analysis_dir / "analysis_manifest.json",
        {
            "status": "complete",
            "created_at_utc": utc_now(),
            "baseline_sha256": sha256_file(release / "baseline/baseline_generations.jsonl"),
            "steering_sha256": sha256_file(release / "steering/steering_generations.jsonl"),
            "local_judgments_sha256": sha256_file(
                release / "judging/local_gemma_judgments.jsonl"
            ),
            "external_judgments_sha256": sha256_file(
                release / "judging/external_judgments.jsonl"
            ),
            "primary_verdict_sha256": sha256_file(analysis_dir / "primary_verdict.json"),
        },
    )
    print(f"Gemma analysis complete -> {analysis_dir}")


if __name__ == "__main__":
    main()
