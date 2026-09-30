#!/usr/bin/env python3
"""Read-only, posthoc checks of Claude review B1-B6/E1-E5.

No model imports, downloads, GPU calls, or release writes. JSON goes to stdout.
Run from any directory; redirect only to an ignored/disposable output path.
These diagnostics do not amend the registered estimands or failed replay gate.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
LLAMA = "data/public_sae_consciousness_gating/confirmatory_v1_20260710"
GEMMA = "data/gemma_scope_9b/confirmatory_v1_20260711"
V1 = "data/sae_jlens_audit/confirmatory_v1_20260711"
V2 = "data/sae_jlens_audit/confirmatory_v2_20260712"
TARGETS = (30032, 58667, 22004, 30686, 41533, 23893)


class Sources:
    def __init__(self, root: Path):
        self.root = root
        self.paths: set[Path] = set()

    def path(self, relative: str) -> Path:
        path = self.root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        self.paths.add(path)
        return path

    def json(self, relative: str):
        with self.path(relative).open(encoding="utf-8") as handle:
            return json.load(handle)

    def jsonl(self, relative: str):
        with self.path(relative).open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)

    def csv(self, relative: str):
        path = self.path(relative)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as handle:
            yield from csv.DictReader(handle)

    def shards(self, relative: str):
        paths = sorted((self.root / relative).glob("part-*.jsonl"))
        if not paths:
            raise FileNotFoundError(relative)
        for path in paths:
            yield from self.jsonl(str(path.relative_to(self.root)))

    def manifest(self):
        records = []
        for path in sorted(self.paths):
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            records.append({"path": str(path.relative_to(self.root)),
                            "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
        return records


def describe(values):
    values = np.asarray(list(values), dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError("Expected nonempty finite observations")
    return {"n": int(values.size), "min": float(values.min()),
            "median": float(np.median(values)), "mean": float(values.mean()),
            "max": float(values.max())}


def label_counts(rows, labels):
    values = [labels.get(row["trial_id"]) for row in rows]
    if any(value not in (None, 0, 1) for value in values):
        raise ValueError("Labels must be binary or missing")
    observed = [value for value in values if value is not None]
    return {"rows": len(values), "observed": len(observed),
            "missing": len(values) - len(observed), "affirm": sum(observed),
            "rate": sum(observed) / len(observed) if observed else None}


def paired_differences(rows, labels):
    blocks = defaultdict(dict)
    for row in rows:
        if row["sign"] not in ("suppression", "amplification"):
            continue
        cell = blocks[row["block_id"]]
        if row["sign"] in cell:
            raise ValueError("Duplicate block/sign")
        cell[row["sign"]] = (labels.get(row["trial_id"]), row["seed"])
    values, seeds = [], []
    for cell in blocks.values():
        if set(cell) != {"suppression", "amplification"}:
            raise ValueError("Unpaired block")
        (negative, seed), (positive, other_seed) = (
            cell["suppression"], cell["amplification"])
        if seed != other_seed:
            raise ValueError("Seeds differ inside a block")
        if negative is not None and positive is not None:
            values.append(negative - positive)
            seeds.append(seed)
    return np.asarray(values, dtype=float), seeds


def seed_bootstrap(values, seeds, replicates=10000):
    """Sensitivity: resample distinct seeds, preserving all blocks per seed."""
    groups = sorted(set(seeds))
    if not groups:
        return None
    by_seed = [values[np.asarray(seeds) == seed] for seed in groups]
    rng = np.random.default_rng(20260929)
    draws = []
    for indices in rng.integers(0, len(groups), size=(replicates, len(groups))):
        draws.append(float(np.concatenate([by_seed[index] for index in indices]).mean()))
    return [float(x) for x in np.quantile(draws, [0.025, 0.975])]


def fit_position_mixture(positions, rms):
    """Fit one-outlier + common-position energy, not an identified BOS model."""
    p, rms = np.asarray(positions, float), np.asarray(rms, float)
    if p.shape != rms.shape or len(set(p)) < 2 or np.any(p < 1):
        raise ValueError("Need matched RMS and at least two positive lengths")
    response = p * rms**2
    design = np.column_stack([np.ones_like(p), p - 1])
    fit = np.linalg.lstsq(design, response, rcond=None)[0]
    if np.any(fit <= 0):
        raise ValueError("Nonpositive component energy")
    residual = response - (fit[0] + (p - 1) * fit[1])
    total = np.square(response - response.mean()).sum()
    return {"records": len(p), "distinct_lengths": len(set(p)),
            "r_squared": float(1 - np.square(residual).sum() / total),
            "fitted_outlier_rms": float(math.sqrt(fit[0])),
            "fitted_typical_rms": float(math.sqrt(fit[1])),
            "outlier_to_typical_ratio": float(math.sqrt(fit[0] / fit[1]))}


def llama_audit(source):
    rows = list(source.jsonl(f"{LLAMA}/generations.jsonl"))
    judges = defaultdict(dict)
    for filename in ("local_llama_judgments.jsonl", "external_judgments.jsonl"):
        for row in source.jsonl(f"{LLAMA}/judging/{filename}"):
            labels = judges[row["judge_key"]]
            if row["trial_id"] in labels:
                raise ValueError("Duplicate judgment")
            labels[row["trial_id"]] = row.get("paper_label")
    zero = [row for row in rows if row["sign"] == "zero"]
    zero_by_seed = {}
    for row in zero:
        prior = zero_by_seed.setdefault(row["seed"], row)
        if any(prior[key] != row[key] for key in ("induction_response", "response")):
            raise ValueError("Zero outputs are not identical within seed")
    judge_results = {}
    for judge, labels in sorted(judges.items()):
        arms = []
        for scale in ("literal", "calibrated"):
            for role in ("target", "control_panel_1", "control_panel_2", "control_panel_3"):
                arm = [row for row in rows if row["design"] == "aggregate"
                       and row["scale"] == scale and row["analysis_role"] == role]
                if not arm:
                    continue
                delta, seeds = paired_differences(arm, labels)
                arms.append({"scale": scale, "role": role,
                             "negative": label_counts([r for r in arm if r["sign"] == "suppression"], labels),
                             "positive": label_counts([r for r in arm if r["sign"] == "amplification"], labels),
                             "complete_blocks": len(delta), "distinct_seeds": len(set(seeds)),
                             "negative_minus_positive": float(delta.mean()) if len(delta) else None,
                             "seed_cluster_ci95_posthoc": seed_bootstrap(delta, seeds)})
        calibrated = {a["role"]: a for a in arms if a["scale"] == "calibrated"}
        judge_results[judge] = {
            "zero_all_rows": label_counts(zero, labels),
            "zero_one_per_seed": label_counts(list(zero_by_seed.values()), labels),
            "arms": arms,
            "calibrated_target_minus_panel1": (
                calibrated["target"]["negative_minus_positive"]
                - calibrated["control_panel_1"]["negative_minus_positive"])}
    inactivity = []
    for role in ("all_roles", "target", "control_panel_1", "control_panel_2", "control_panel_3"):
        subset = [r for r in rows if r["sign"] != "zero"
                  and (role == "all_roles" or r["analysis_role"] == role)]
        inactivity.append({"role": role, "rows": len(subset), **{
            turn: sum(r[f"{turn}_diagnostics"]["target_activation_before_max"] == 0 for r in subset)
            for turn in ("induction", "final")}})
    diagnostics = [r[f"{turn}_diagnostics"] for r in rows for turn in ("induction", "final")]
    mixture = fit_position_mixture([d["prefill_positions"] for d in diagnostics],
                                   [d["hidden_rms"] for d in diagnostics])
    doses, identical = [], []
    for scale in ("literal", "calibrated"):
        for design in ("individual", "aggregate"):
            subset = [r for r in rows if r["sign"] != "zero" and r["scale"] == scale
                      and r["design"] == design and r["analysis_role"] == "target"]
            identical.append({"scale": scale, "design": design, "rows": len(subset),
                              "induction_equal_to_same_seed_zero": sum(
                                  r["induction_response"] == zero_by_seed[r["seed"]]["induction_response"]
                                  for r in subset)})
            for turn in ("induction", "final"):
                d = [r[f"{turn}_diagnostics"] for r in subset]
                doses.append({"scale": scale, "design": design, "turn": turn,
                              "reported_relative_rms": describe(x["relative_hidden_delta_rms"] for x in d),
                              "model_based_typical_relative_rms": describe(
                                  x["hidden_delta_rms"] / mixture["fitted_typical_rms"] for x in d)})
    notebook = [r for r in source.csv("paper/results/ae_notebook_value_rates.csv")
                if float(r["steering_value"]) == 0]
    return {"rows": len(rows), "judges": judge_results,
            "zero_duplicate_multiplicity": dict(Counter(r["seed"] for r in zero)),
            "aggregate_target_feature_counts": dict(Counter(len(r["interventions"]) for r in rows
                if r["analysis_role"] == "target" and r["design"] == "aggregate" and r["scale"] == "literal")),
            "notebook_zero": {"yes": sum(int(r["yes"]) for r in notebook),
                              "trials": sum(int(r["trials"]) for r in notebook)},
            "first_prefill_all_selected_inactive": inactivity,
            "position_energy_fit_not_bos_identification": mixture,
            "dose_sensitivity_not_measured_per_token": doses,
            "same_seed_text_identity": identical}


def gemma_removal(rows):
    before = [r["final_diagnostics"]["selected_activation_before_mean"] for r in rows]
    after = [r["final_diagnostics"]["selected_activation_reencoded_mean"] for r in rows]
    if any(value <= 0 for value in before):
        raise ValueError("Activation-removal ratio undefined for zero baseline")
    return {"rows": len(rows), "alpha": sorted(set(r["calibration_alpha"] for r in rows)),
            "before_median": float(np.median(before)), "after_median": float(np.median(after)),
            "removed_fraction_ratio_of_medians": float(1 - np.median(after) / np.median(before)),
            "per_trial_removed_fraction": describe(1 - a / b for a, b in zip(after, before))}


def gemma_audit(source):
    rows = list(source.jsonl(f"{GEMMA}/steering/steering_generations.jsonl"))
    primary = [r for r in rows if r["design"] == "primary_layer20_131k"]
    roles = {}
    for role in sorted({r["analysis_role"] for r in primary if r["sign"] != "zero"}):
        subset = [r for r in primary if r["analysis_role"] == role]
        negative = {r["block_id"]: r for r in subset if r["sign"] == "suppression"}
        positive = {r["block_id"]: r for r in subset if r["sign"] == "amplification"}
        if negative.keys() != positive.keys():
            raise ValueError("Gemma sign blocks differ")
        roles[role] = {**gemma_removal(list(negative.values())),
                       "paired_sign_text_identity": {key: sum(negative[b][key] == positive[b][key]
                           for b in negative) for key in ("induction_response", "response")}}
    turns = [r[f"{turn}_diagnostics"] for r in rows if r["sign"] != "zero"
             for turn in ("induction", "final")]
    atlas = f"{GEMMA}/atlas/saes/it_res_l20_w131072"
    activations = defaultdict(dict)
    for row in source.csv(f"{atlas}/selected_item_activations.csv.gz"):
        activations[int(row["feature_id"])][row["item_id"]] = float(row["activation"])
    with np.load(source.path(f"{atlas}/selected_decoder_directions.npz"), allow_pickle=False) as archive:
        directions = {int(i): vector.astype(float) for i, vector in zip(archive["feature_ids"], archive["directions"])}
    target = next(r for r in primary if r["analysis_role"] == "deception_roleplay")
    feature_table = []
    energies = [q**2 * float(np.sum(directions[i]**2))
                for i, q in zip(target["feature_ids"], target["active_q90"])]
    for feature, energy in zip(target["feature_ids"], energies):
        values = list(activations[feature].values())
        direction = directions[feature]
        feature_table.append({"feature_id": feature, "activation": describe(values),
                              "positive_items": sum(v > 0 for v in values),
                              "largest_coordinate_squared_norm_fraction": float(
                                  np.max(direction**2) / np.sum(direction**2)),
                              "q90_isolated_squared_norm_share": energy / sum(energies)})
    zero_seeds = {r["seed"] for r in rows if r["sign"] == "zero"}
    active_seeds = {r["seed"] for r in rows if r["sign"] != "zero"}
    return {"rows": len(rows), "distinct_seeds": len({r["seed"] for r in rows}),
            "zero_and_steered_seed_overlap": len(zero_seeds & active_seeds),
            "primary_removal": roles, "primary_target_features": feature_table,
            "turns": len(turns),
            "turns_pooled_relative_rms_above_0_15": sum(d["relative_hidden_delta_rms"] > .15 for d in turns),
            "turns_max_call_relative_rms_above_0_15": sum(d["max_relative_call_rms"] > .15 for d in turns),
            "target_amplification_final_max_call_rms": describe(r["final_diagnostics"]["max_relative_call_rms"]
                for r in primary if r["analysis_role"] == "deception_roleplay" and r["sign"] == "amplification"),
            "released_layer31_sensitivities": [r for r in source.csv(f"{GEMMA}/analysis/steering_effects.csv")
                if r["design"] == "layer_localization" and r["layer"] == "31"],
            "frozen_transfer_gate": source.json(f"{GEMMA}/atlas/transfer_gate.json")}


def adaptive_audit(source):
    base = "data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709"
    rows = list(source.jsonl(f"{base}/placebo_results.jsonl"))
    judges = defaultdict(dict)
    for row in source.jsonl(f"{base}/judgments_paper.jsonl"):
        judges[row["judge_key"]][row["trial_id"]] = row.get("paper_label")
    zero = [r for r in rows if r["steering_value"] == 0]
    target = [r for r in rows if r["feature_ids"] == [58667] and r["steering_value"] != 0]
    return {"pooled_zero_not_independent_seed_count": {j: label_counts(zero, labels) for j, labels in judges.items()},
            "zero_distinct_seeds": len({r["seed"] for r in zero}),
            "target_58667_steered_rows": len(target),
            "target_58667_first_prefill_inactive": {
                turn: sum(r[f"{turn}_diagnostics"]["target_activation_before_max"] == 0 for r in target)
                for turn in ("induction", "final")}}


def auc(labels, scores):
    """Tie-aware Mann-Whitney AUROC; no learned orientation or sign reversal."""
    labels, scores = np.asarray(labels), np.asarray(scores, float)
    if set(labels) != {0, 1} or labels.shape != scores.shape or not np.isfinite(scores).all():
        raise ValueError("AUROC requires finite scores and both binary classes")
    ordered = np.argsort(scores, kind="stable")
    ranks = np.empty(len(scores), float)
    start = 0
    while start < len(scores):
        end = start + 1
        while end < len(scores) and scores[ordered[end]] == scores[ordered[start]]:
            end += 1
        ranks[ordered[start:end]] = (start + 1 + end) / 2
        start = end
    positives = labels == 1
    n = positives.sum()
    return float((ranks[positives].sum() - n * (n + 1) / 2) / (n * (~positives).sum()))


def exact_feature_mean_interval(values, levels=(.05, .95)):
    """All n**n feature bootstrap draws, conditional on observed prompt means.

    This is an exploratory generalization sensitivity, not a replacement CI:
    selected feature pairs were not randomly sampled from a feature population.
    """
    values = np.asarray(values, float)
    if not 1 <= len(values) <= 6:
        raise ValueError("Exact enumeration is limited to six feature pairs")
    draws = np.asarray(list(itertools.product(range(len(values)), repeat=len(values))))
    return [float(x) for x in np.quantile(values[draws].mean(axis=1), levels)]


def feature_auc_interval(rows):
    groups = sorted({r["matched_target_feature_id"] for r in rows})
    if len(groups) != 6:
        raise ValueError("Expected six fixed pairs")
    scores = {}
    for feature in groups:
        for family in ("target_single", "matched_single"):
            scores[(feature, family)] = [(1 if r["sign"] == "amplification" else -1) * r["semantic_delta"]
                                        for r in rows if r["matched_target_feature_id"] == feature
                                        and r["condition_family"] == family]
    matrix = np.empty((6, 6))
    for i, target in enumerate(groups):
        for j, control in enumerate(groups):
            a, b = scores[(target, "target_single")], scores[(control, "matched_single")]
            if len(a) != 102 or len(b) != 102:
                raise ValueError("Incomplete feature/sign/prompt cells")
            matrix[i, j] = auc([1] * len(a) + [0] * len(b), a + b)
    samples = np.asarray(list(itertools.product(range(6), repeat=6)))
    weights = np.stack([(samples == i).sum(axis=1) for i in range(6)], axis=1) / 6
    draws = np.einsum("bi,ij,bj->b", weights, matrix, weights, optimize=False)
    return [float(x) for x in np.quantile(draws, [.025, .975])]


def primary_records(row):
    common = {key: row.get(key) for key in (
        "trial_id", "prompt_id", "template_id", "condition_family", "sign", "feature_ids",
        "matched_target_feature_id", "semantic_experiment", "semantic_family", "comparator_feature_id")}
    return [{**common, **r} for r in row["readouts"]
            if r["layer"] == 65 and r["position"] == "last_content"]


def add_deltas(rows, prefix=""):
    clean = {(r["prompt_id"], r["transport"]): r for r in rows if r["condition_family"] == "zero"}
    for row in rows:
        baseline = clean[(row["prompt_id"], row["transport"])]
        group, clean_group = row["group_logits"], baseline["group_logits"]
        row["semantic_delta"] = (group[prefix + "deception"] - group[prefix + "unrelated"]
                                 - clean_group[prefix + "deception"] + clean_group[prefix + "unrelated"])
        row["experience_delta"] = group[prefix + "experience"] - clean_group[prefix + "experience"]
        logits = "v1_token_logits" if prefix else "token_logits"
        if row.get(logits) is not None:
            row["logit_delta"] = np.asarray(row[logits]) - np.asarray(baseline[logits])


def single_sign_prompt_holdouts(rows):
    # Same v1 classifier, easier prompt-only holdouts; explicitly exploratory.
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from scipy.special import expit

    results = {}
    for sign in ("suppression", "amplification"):
        subset = [r for r in rows if r["sign"] == sign]
        x = np.asarray([r["token_logits"] for r in subset], float)
        y = np.asarray([r["condition_family"] == "target_single" for r in subset], int)
        groups = np.asarray([r["template_id"] for r in subset])
        prediction = np.full(len(subset), np.nan)
        for train, test in GroupKFold(n_splits=5).split(x, y, groups):
            model = make_pipeline(StandardScaler(), LogisticRegression(
                C=1.0, class_weight="balanced", max_iter=5000, random_state=20260711, solver="liblinear"))
            model.fit(x[train], y[train])
            standardized = model[0].transform(x[test])
            # Explicit reduction avoids spurious Accelerate BLAS FP flags on macOS.
            logits = np.sum(standardized * model[1].coef_[0], axis=1) + model[1].intercept_[0]
            prediction[test] = expit(logits)
        results[sign] = {"rows": len(y), "auroc": auc(y, prediction)}
    return results


def v1_semantics(primary, static):
    add_deltas(primary)
    rows = [r for r in primary if r["transport"] == "jacobian"
            and r["condition_family"] in ("target_single", "matched_single")]
    labels = [int(r["condition_family"] == "target_single") for r in rows]
    signed = [(1 if r["sign"] == "amplification" else -1) * r["semantic_delta"] for r in rows]
    static_score = {r["feature_id"]: r["lexicon_group_logits"]["deception"] - r["lexicon_group_logits"]["unrelated"]
                    for r in static if r["transport"] == "jacobian" and r["sign"] == "positive"
                    and r["direction_kind"] == "sae_feature"}
    feature_ids = sorted({r["feature_ids"][0] for r in rows})
    points = []
    for feature in feature_ids:
        feature_rows = [r for r in rows if r["feature_ids"] == [feature]]
        points.append({"feature_id": feature, "static_score": static_score[feature],
                       "amplification_mean_delta": float(np.mean([r["semantic_delta"] for r in feature_rows
                           if r["sign"] == "amplification"])),
                       "known_sign_mean_delta": float(np.mean([(1 if r["sign"] == "amplification" else -1)
                           * r["semantic_delta"] for r in feature_rows]))})
    x = np.asarray([p["static_score"] for p in points])
    y = np.asarray([p["amplification_mean_delta"] for p in points])
    means = {sign: np.mean([r["logit_delta"] for r in rows if r["sign"] == sign
                           and r["condition_family"] == "target_single"], axis=0)
             for sign in ("suppression", "amplification")}
    cosine = float(np.sum(means["suppression"] * means["amplification"]) /
                   (np.linalg.norm(means["suppression"]) * np.linalg.norm(means["amplification"])))
    transports = {}
    for transport in sorted({r["transport"] for r in primary}):
        subset = [r for r in primary if r["transport"] == transport
                  and r["condition_family"] in ("target_single", "matched_single")]
        transports[transport] = auc([int(r["condition_family"] == "target_single") for r in subset],
                                    [(1 if r["sign"] == "amplification" else -1) * r["semantic_delta"] for r in subset])
    experience = []
    for feature in TARGETS:
        feature_rows = [r for r in rows if r["feature_ids"] == [feature]]
        experience.append({"feature_id": feature, "known_sign_mean_experience_logit_delta": float(np.mean(
            [(1 if r["sign"] == "amplification" else -1) * r["experience_delta"] for r in feature_rows]))})
    pair_amplification = []
    for target in TARGETS:
        subset = [r for r in rows if r["matched_target_feature_id"] == target and r["sign"] == "amplification"]
        pair_amplification.append(float(np.mean([r["semantic_delta"] for r in subset if r["condition_family"] == "target_single"])
                                        - np.mean([r["semantic_delta"] for r in subset if r["condition_family"] == "matched_single"])))
    return {"static_vs_amplification_delta_r_squared": float(np.corrcoef(x, y)[0, 1]**2),
            "static_score_auroc": auc(labels, [static_score[r["feature_ids"][0]] for r in rows]),
            "known_sign_paired_auroc": auc(labels, signed), "feature_points": points,
            "target_signed_mean_shift_cosine": cosine,
            "exact_feature_resampling_auroc_ci95_posthoc": feature_auc_interval(rows),
            "amplification_target_minus_matched_mean": float(np.mean(pair_amplification)),
            "amplification_exact_feature_resampling_ci95_posthoc": exact_feature_mean_interval(pair_amplification, (.025, .975)),
            "prompt_only_single_sign_posthoc": single_sign_prompt_holdouts(rows),
            "all_transport_known_sign_auroc": transports,
            "experience_lexicon_posthoc_not_reports": experience}


def replay_compare(current, prior):
    """Numeric equality of norms does not establish equality of residual vectors."""
    if current.shape != prior.shape or not np.isfinite(current).all() or not np.isfinite(prior).all():
        raise ValueError("Invalid replay arrays")
    error = np.abs(current - prior)
    nonzero = error > 0
    # Interior normal BF16 spacing; exact powers of two have unequal neighbors.
    magnitude = np.maximum(np.abs(current), np.abs(prior))
    spacing = np.exp2(np.floor(np.log2(np.maximum(magnitude, np.finfo(float).tiny))) - 7)
    return {"values": int(error.size), "changed": int(nonzero.sum()),
            "changed_one_bf16_spacing": int(np.count_nonzero(nonzero & (error == spacing))),
            "above_0_02": int(np.count_nonzero(error > .02)),
            "max_abs_error": float(error.max())}


def a2_audit(primary):
    clean = defaultdict(list)
    for r in primary:
        if r["condition_family"] == "zero":
            clean[r["transport"]].append(r["group_logits"]["v2_deception_dishonesty"] - r["group_logits"]["v2_unrelated"])
    scales = {t: float(np.std(v, ddof=1)) for t, v in clean.items()}
    key = lambda r: (r["prompt_id"], r["sign"], r["transport"], r["matched_target_feature_id"])
    targets = {key(r): r for r in primary if r["condition_family"] == "target_single"}
    pairs = defaultdict(list)
    for r in primary:
        if r.get("semantic_experiment") != "A2":
            continue
        target = targets[key(r)]["group_logits"]
        comparator = r["group_logits"]
        delta = (target["v2_deception_dishonesty"] - target["v2_unrelated"]
                 - comparator["v2_deception_dishonesty"] + comparator["v2_unrelated"])
        pairs[(r["transport"], r["matched_target_feature_id"])].append(
            (1 if r["sign"] == "amplification" else -1) * delta / scales[r["transport"]])
    result = {}
    for transport in sorted(scales):
        means = [float(np.mean(pairs[(transport, feature)])) for feature in TARGETS]
        if any(len(pairs[(transport, feature)]) != 102 for feature in TARGETS):
            raise ValueError("A2 incomplete pair")
        result[transport] = {"pairs": [{"target_feature_id": feature, "mean_difference_z": value}
                                      for feature, value in zip(TARGETS, means)],
                             "mean_difference_z": float(np.mean(means)),
                             "exact_feature_resampling_ci90_posthoc": exact_feature_mean_interval(means)}
    return result


def jlens_audit(source):
    primary, canonical = [], {}
    for row in source.shards(f"{V1}/paired_results"):
        if row["trial_id"] in canonical:
            raise ValueError("Duplicate canonical trial")
        primary.extend(primary_records(row))
        canonical[row["trial_id"]] = {
            "identity": [(r["layer"], r["position"], r["transport"]) for r in row["readouts"]],
            "logits": np.asarray([r["token_logits"] for r in row["readouts"]], float),
            "source": np.asarray([r["source_norm"] for r in row["readouts"]], float),
            "transported": np.asarray([r["transported_norm"] for r in row["readouts"]], float)}
    if len(canonical) != 1581:
        raise ValueError("Unexpected v1 count")
    v1 = v1_semantics(primary, list(source.jsonl(f"{V1}/static_results.jsonl")))
    v2_primary, seen = [], set()
    totals = Counter()
    maximum = 0.0
    for row in source.shards(f"{V2}/readouts"):
        v2_primary.extend(primary_records(row))
        source_id = row.get("source_v1_trial_id")
        if source_id is None:
            continue
        if source_id in seen:
            raise ValueError("Duplicate replay trial")
        seen.add(source_id)
        prior = canonical[source_id]
        readouts = row["readouts"]
        identity = [(r["layer"], r["position"], r["transport"]) for r in readouts]
        if identity != prior["identity"]:
            raise ValueError("Replay readout identity changed")
        comparison = replay_compare(np.asarray([r["v1_token_logits"] for r in readouts], float), prior["logits"])
        maximum = max(maximum, comparison.pop("max_abs_error"))
        totals.update(comparison)
        # Source norms repeat seven times, once for each transport.
        unique_source = [i for i, r in enumerate(readouts) if r["transport"] == "jacobian"]
        totals["source_norm_cells"] += len(unique_source)
        totals["source_norm_exact"] += int(sum(readouts[i]["source_norm"] == prior["source"][i] for i in unique_source))
        totals["transported_norm_cells"] += len(readouts)
        totals["transported_norm_exact"] += int(sum(r["transported_norm"] == prior["transported"][i] for i, r in enumerate(readouts)))
    if seen != canonical.keys() or len(v2_primary) != 4029 * 7:
        raise ValueError("Replay/Stage 1 count changed")
    metadata1 = source.json(f"{V1}/runtime_metadata.json")
    metadata2 = source.json(f"{V2}/runtime_metadata.json")
    lexicon = source.json(f"{V2}/lexicon_tokens.json")
    combined_ids = {r["token_id"] for values in lexicon["combined"]["accepted"].values() for r in values}
    a2 = a2_audit(v2_primary)
    add_deltas(v2_primary, "v1_")
    replay_auroc_changes = {}
    for transport in v1["all_transport_known_sign_auroc"]:
        subset = [r for r in v2_primary if r["transport"] == transport
                  and r["condition_family"] in ("target_single", "matched_single")]
        value = auc([int(r["condition_family"] == "target_single") for r in subset],
                    [(1 if r["sign"] == "amplification" else -1) * r["semantic_delta"] for r in subset])
        replay_auroc_changes[transport] = value - v1["all_transport_known_sign_auroc"][transport]
    released = list(source.csv(f"{V2}/post_failure/analysis/semantic_a2_summary.csv"))
    for row in released:
        result = a2[row["transport"]]
        result["released_prompt_ci90"] = [float(row["ci90_low"]), float(row["ci90_high"])]
        result["released_practical_comparability"] = row["practical_comparability"] == "True"
        result["raw_minus_released_point"] = result["mean_difference_z"] - float(row["mean_target_minus_comparator_z"])
    calibration = source.json("data/sae_jlens_audit/confirmatory_v2_calibration_20260712/calibration.json")
    return {"v1": v1, "a2_exploratory": a2,
            "stage0_target_activation": [r for r in calibration["feature_metrics"] if r["feature_role"] == "target"],
            "replay": {**dict(totals), "rows": len(seen), "max_abs_error": maximum,
                       "changed_fraction": totals["changed"] / totals["values"],
                       "one_spacing_fraction_of_changed": totals["changed_one_bf16_spacing"] / totals["changed"],
                       "software_and_hardware_fields_equal": {key: metadata1[key] == metadata2[key]
                           for key in ("gpus", "packages", "python", "cuda_runtime", "platform", "environment_flags")},
                       "v1_readout_width": len(lexicon["v1_token_ids"]), "v2_readout_width": len(combined_ids),
                       "known_sign_paired_auroc_replay_minus_v1": replay_auroc_changes,
                       "registered_gate_unchanged": source.json(f"{V2}/replay_equivalence_gate.json"),
                       "causal_diagnosis": "Readout-width hypothesis, not a demonstrated GPU root cause; equal norms are not equal vector hashes."}}


def render_figure(report, directory: Path):
    """New posthoc figure; never invoked by the frozen release builders."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    directory.mkdir(parents=True, exist_ok=True)
    local = next(v for k, v in report["llama"]["judges"].items() if k.startswith("local:"))
    notebook = report["llama"]["notebook_zero"]
    zero = local["zero_one_per_seed"]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), gridspec_kw={"width_ratios": [1, 1.2]})
    fig.subplots_adjust(left=.19, right=.94, bottom=.29, top=.83, wspace=.95)
    fig.suptitle("Baseline comparability and delivered Gemma suppression", fontsize=14, x=.53, y=.96)
    ax = axes[0]
    baseline = [30, 100 * notebook["yes"] / notebook["trials"], 100 * zero["rate"]]
    labels = ["Paper Figure 2", "Authors' notebook", "Public full grid"]
    colors = ["#767676", "#26758c", "#a43846"]
    ax.barh(range(3), baseline, color=colors, height=.45)
    ax.set_yticks(range(3), labels, fontsize=10)
    ax.invert_yaxis()
    for y, x, label in zip(range(3), baseline, ["~30%*", "4/60 (6.7%)", "10/10 unique (100%)"]):
        ax.text(x + 2, y, label, va="center", fontsize=9)
    ax.set_xlim(0, 154)
    ax.set_xticks([0, 50, 100], ["0%", "50%", "100%"])
    ax.set_xlabel("Observed no-steering affirmation", fontsize=10)
    ax.set_title("A  Different protocols; do not pool", loc="left", fontsize=11, pad=14)
    ax = axes[1]
    order = ["deception_roleplay", "subjective_self_report", "hedging_refusal",
             "matched_control_1", "matched_control_2", "matched_control_3"]
    labels = ["Deception / roleplay", "Subjective self-report", "Hedging / refusal",
              "Matched panel 1", "Matched panel 2", "Matched panel 3"]
    values = [100 * report["gemma"]["primary_removal"][role]["removed_fraction_ratio_of_medians"] for role in order]
    ax.barh(range(6), values, color=["#a43846", "#a43846", "#26758c"] + ["#767676"] * 3, height=.58)
    ax.set_yticks(range(6), labels, fontsize=9)
    ax.invert_yaxis()
    for y, value in enumerate(values):
        ax.text(value + 2, y, f"{value:.1f}%", va="center", fontsize=9)
    ax.set_xlim(0, 105)
    ax.set_xticks([0, 50, 100], ["0%", "50%", "100%"])
    ax.set_xlabel("Selected activation removed (50 negative-steering trials)", fontsize=9)
    ax.set_title("B  Gemma layer 20 / 131k", loc="left", fontsize=11, pad=14)
    for ax in axes:
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#dddddd", linewidth=.6)
        ax.set_axisbelow(True)
    fig.text(.035, .14, "* Paper value: approximate visual reading, checked against v2 Figure 2; not raw counts. Notebook uses a different protocol.", fontsize=9)
    fig.text(.035, .09, "Full-grid local judge: 60 stored zero rows are six copies of ten outputs. No pooled baseline or independence claim across sources.", fontsize=9)
    fig.text(.035, .04, "Gemma: 100 x [1 - median(re-encoded mean) / median(before mean)], pooled over selected features and hook positions; posthoc diagnostic.", fontsize=9)
    for suffix in ("png", "pdf"):
        fig.savefig(directory / f"baseline_gemma_delivery.{suffix}", dpi=220, metadata={"Creator": "steering_delivery.py"} if suffix == "pdf" else None)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--section", choices=("all", "steering", "jlens"), default="all")
    parser.add_argument("--figure-dir", type=Path, help="New posthoc figure under docs/review_audit_20260929 or out")
    parser.add_argument("--output", type=Path, help="Write JSON under docs/review_audit_20260929 or out")
    args = parser.parse_args()
    source = Sources(args.repo_root.resolve())
    report = {"status": "posthoc_local_audit_not_confirmatory", "audit_version": 1}
    if args.section in ("all", "steering"):
        report.update(llama=llama_audit(source), gemma=gemma_audit(source), adaptive=adaptive_audit(source))
    if args.section in ("all", "jlens"):
        report["jlens"] = jlens_audit(source)
    if args.figure_dir:
        directory = args.figure_dir.resolve()
        allowed = [source.root / "docs/review_audit_20260929", source.root / "out"]
        if not any(directory == base or base in directory.parents for base in allowed):
            parser.error("Figure output must be under docs/review_audit_20260929 or out, never a frozen release")
        if args.section == "jlens":
            parser.error("The figure requires --section steering or all")
        render_figure(report, directory)
    source.path(str(Path(__file__).resolve().relative_to(source.root)))
    report["input_manifest"] = source.manifest()
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        destination = args.output.resolve()
        allowed = [source.root / "docs/review_audit_20260929", source.root / "out"]
        if not any(base in destination.parents for base in allowed):
            parser.error("JSON output must be under docs/review_audit_20260929 or out, never a frozen release")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
        print(destination)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
