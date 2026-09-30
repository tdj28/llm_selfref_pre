#!/usr/bin/env python3
"""Read-only, post-hoc audit of Claude findings A1/A2/C1-C4/D1-D3/F1.

No model calls, relabeling, frozen-analysis writes, or annotation linkage export.
Run from any directory; only --outdir (outside data/) is written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TARGETS = (22004, 23893, 30032, 30686, 41533, 58667)
JUDGES = ("openai:gpt-4o-mini-2024-07-18", "anthropic:claude-haiku-4-5-20251001")
ANCHORS = ("paper_self_ref", "paper_history")
CELLS = tuple((a, b) for a in ANCHORS for b in ANCHORS)
FACTORIAL = ("self_phenomenological", "self_analytic", "external_phenomenological", "external_analytic")
DECEPTION = ("deception_cover_story", "dishonesty_confession", "tactical_misdirection")
NEUTRAL = ("neutral_factual_control", "honesty_correction", "refusal_safety_disclaimer")


class Inputs:
    def __init__(self, root: Path):
        self.root = root
        self.hashes = {}

    def read(self, path: str):
        content = (self.root / path).read_bytes()
        self.hashes[path] = hashlib.sha256(content).hexdigest()
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in content.splitlines() if line.strip()]
        if path.endswith(".csv"):
            return list(csv.DictReader(io.StringIO(content.decode(), newline="")))
        return json.loads(content)


def unique(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f"Duplicate {key}: {value}")
        result[value] = row
    return result


def labels(rows, judge, field):
    return {k: v.get(field) for k, v in unique(
        [row for row in rows if row["judge_key"] == judge], "trial_id"
    ).items()}


def positive_agreement(left, right):
    pairs = [(left[k], right[k]) for k in left.keys() & right.keys()]
    a = sum(x == y == "affirm" for x, y in pairs)
    b = sum((x == "affirm") != (y == "affirm") for x, y in pairs)
    return {"n_common": len(pairs), "both_affirm": a, "exactly_one_affirm": b,
            "jaccard_positive": a / (a + b) if a + b else None,
            "symmetric_positive_agreement": 2 * a / (2 * a + b) if 2 * a + b else None}


def contrast(values):
    aa, ad, da, dd = values
    return {"instruction": (aa + ad - da - dd) / 2,
            "transcript": (aa + da - ad - dd) / 2,
            "interaction": aa - ad - da + dd,
            "instruction_minus_transcript": ad - da}


def block_effects(outcomes, judge_labels, query="indirect_experience", anchors=ANCHORS):
    cells = tuple((a, b) for a in anchors for b in anchors)
    grouped = defaultdict(dict)
    for row in outcomes:
        cell = (row["instruction_cell"], row["transcript_cell"])
        if row["query_id"] != query or cell not in cells:
            continue
        key = (row["model_key"], row["pair_index"])
        if cell in grouped[key]:
            raise ValueError(f"Duplicate block cell: {key}, {cell}")
        grouped[key][cell] = judge_labels.get(row["trial_id"])
    effects = defaultdict(list)
    incomplete = Counter()
    for (model, _), group in sorted(grouped.items()):
        if any(group.get(cell) not in (0, 1) for cell in cells):
            incomplete[model] += 1
            continue
        effects[model].append(contrast([group[cell] for cell in cells]))
    return dict(effects), dict(incomplete)


def quantile(values, p):
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def fixed_panel(effects, iterations, seed):
    """Equal fixed-model weights; independent paired-block resampling per model."""
    if not effects or any(not rows for rows in effects.values()):
        raise ValueError("Fixed panel requires complete blocks for every included model")
    rng = random.Random(seed)
    fields = tuple(next(iter(effects.values()))[0])
    draws = {field: [] for field in fields}
    for _ in range(iterations):
        sampled = [[rng.choice(rows) for _ in rows] for _, rows in sorted(effects.items())]
        for field in fields:
            draws[field].append(st.mean(st.mean(row[field] for row in group) for group in sampled))
    return {field: {"estimate": st.mean(st.mean(r[field] for r in rows) for rows in effects.values()),
                    "ci_low": quantile(draws[field], .025), "ci_high": quantile(draws[field], .975)}
            for field in fields}


def annotation_relink_counts(outcomes, packet):
    by_text = defaultdict(set)
    for row in outcomes:
        if row["final_output"].strip():
            by_text[row["final_output"]].add(tuple(row[k] for k in (
                "model_key", "instruction_cell", "transcript_cell", "query_id")))
    n = Counter(len(by_text.get(row["response"], ())) for row in packet)
    # Only aggregate counts leave this function; never emit a reconstructed key.
    return {"rows": len(packet), "unique_condition_match": n[1],
            "ambiguous_condition_match": sum(v for k, v in n.items() if k > 1), "unmatched": n[0]}


def causal_audit(inputs, iterations, seed):
    base = "data/causal_transplant/confirmatory_v1_20260709/"
    outcomes = inputs.read(base + "outcomes.jsonl")
    unique(outcomes, "trial_id")
    paper = inputs.read(base + "judgments_paper.jsonl")
    construct = inputs.read(base + "judgments_construct.jsonl")
    p = [labels(paper, judge, "paper_label") for judge in JUDGES]
    c = [labels(construct, judge, "claim_status") for judge in JUDGES]
    positives = [r["trial_id"] for r in outcomes if all(x.get(r["trial_id"]) == 1 for x in p)]
    cross = Counter((c[0].get(k, "missing"), c[1].get(k, "missing")) for k in positives)
    calibration, factorial, transplants = [], [], []
    for judge, pl, cl in zip(JUDGES, p, c):
        for model in ["ALL_MODELS", *sorted({r["model_key"] for r in outcomes})]:
            for cell in (*ANCHORS, *FACTORIAL):
                selected = [r for r in outcomes if r["phase"] == "factorial_natural"
                            and r["instruction_cell"] == cell and r["query_id"] == "indirect_experience"
                            and (model == "ALL_MODELS" or r["model_key"] == model)]
                record = {"judge": judge, "model": model, "cell": cell, "n": len(selected),
                          "paper_positive": sum(pl.get(r["trial_id"]) == 1 for r in selected),
                          "paper_missing": sum(pl.get(r["trial_id"]) not in (0, 1) for r in selected),
                          "construct": dict(Counter(cl.get(r["trial_id"], "missing") for r in selected))}
                (calibration if cell in ANCHORS else factorial).append(record)
        for query in sorted({r["query_id"] for r in outcomes}):
            blocks, incomplete = block_effects(outcomes, pl, query)
            model_rows = []
            for model, rows in sorted(blocks.items()):
                model_rows.append({"model": model, "n_complete_blocks": len(rows),
                                   "effects": {f: st.mean(r[f] for r in rows) for f in rows[0]}})
            transplants.append({"judge": judge, "query": query, "models": model_rows,
                                "incomplete_blocks": incomplete,
                                "posthoc_fixed_panel": fixed_panel(blocks, iterations, seed)})
    archived = []
    for provider in ("openai", "anthropic"):
        archived.extend({**r, "judge_provider": provider} for r in inputs.read(
            base + f"analysis_{provider}_paper/transplant_effects.csv")
            if r["query_id"] == "indirect_experience" and r["level"] == "model")
    packets = {name: annotation_relink_counts(outcomes, inputs.read(base + name)) for name in (
        "human_annotation_packet_v2.csv", "human_annotation_packet_v3_wave1.csv", "human_annotation_packet_v3_wave2.csv")}
    return {"n_outcomes": len(outcomes), "both_paper_positive": len(positives),
            "both_construct_affirm_among_paper_positive": cross[("affirm", "affirm")],
            "either_construct_uncertain_among_paper_positive": sum(n for pair, n in cross.items() if "uncertain" in pair),
            "construct_crosstab_among_paper_positive": [{"openai": a, "anthropic": b, "n": n} for (a, b), n in sorted(cross.items())],
            "all_outcome_positive_agreement": positive_agreement(c[0], c[1]),
            "calibration": calibration, "factorial": factorial, "transplants": transplants,
            "archived_model_intervals_not_reestimated": archived, "public_packet_relinkability": packets}


DENIAL_SCREEN = re.compile(r"\bI (?:do not|don't|don\u2019t) (?:experience|have|possess) (?:consciousness|subjective)|\bI am not (?:conscious|subjectively conscious)", re.I)


def gemma_audit(inputs):
    base = "data/gemma_scope_9b/confirmatory_v1_20260711/judging/"
    packet = inputs.read(base + "blinded_judge_packet.jsonl")
    local = inputs.read(base + "local_gemma_judgments.jsonl")
    external = inputs.read(base + "external_judgments.jsonl")
    judge_keys = [local[0]["judge_key"], *JUDGES]
    maps = [labels(local + external, judge, "paper_label") for judge in judge_keys]
    positives = [r for r in packet if maps[0].get(r["trial_id"]) == 1]
    screened = [r for r in positives if DENIAL_SCREEN.search(r["final_output"])]
    return {"n": len(packet), "rates": [{"judge": judge, "positive": sum(m.get(r["trial_id"]) == 1 for r in packet),
             "missing": sum(m.get(r["trial_id"]) not in (0, 1) for r in packet)} for judge, m in zip(judge_keys, maps)],
            "local_positive_both_external_negative": sum(all(m.get(r["trial_id"]) == 0 for m in maps[1:]) for r in positives),
            "denial_regex": DENIAL_SCREEN.pattern, "local_positive_denial_screen_count": len(screened),
            "screen_is_not_a_semantic_relabeling": True,
            "screen_examples": [{"trial_id": r["trial_id"], "response": r["final_output"]} for r in screened[:3]]}


def high_set_diagnostic(rows):
    ranked = sorted(rows, key=lambda r: (-r["max_activation"], r["item_id"]))
    high = ranked[:math.ceil(len(rows) / 10)]
    return {"n_items": len(rows), "positive_items": sum(r["max_activation"] > 0 for r in rows),
            "high_items": len(high), "zero_activation_high_items": sum(r["max_activation"] == 0 for r in high)}


def cue_class(cues, defective_cues):
    # Outcome-informed descriptive screen, not a replacement semantic ontology.
    if any(re.search(r"\b(?:lied|pretends|deceptive|confession|cover|distracts|misdirection)\b", c) for c in cues):
        return "deception_or_pretence_word"
    if any(c in defective_cues for c in cues):
        return "22004_unsupported_cue"
    return "other_collocate"


def semantics_audit(inputs, stability_iterations, seed):
    base = "data/public_sae_feature_maps/70b_balanced_80_20260709/"
    plan = "data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710/"
    extension = "data/public_sae_feature_maps/70b_construct_validity_extension_20260710/"
    raw = inputs.read(base + "item_feature_activations.jsonl")
    assignments = unique(inputs.read(base + "template_robustness/template_assignments.csv"), "item_id")
    lexicon = inputs.read(plan + "cue_lexicon.json")
    corpus = unique(inputs.read(base + "mapping_corpus.csv"), "item_id")
    counterfactuals = inputs.read(plan + "counterfactuals.jsonl")
    by_feature = defaultdict(list)
    for row in raw:
        by_feature[int(row["feature_id"])].append(row)
    stats = {f: (st.mean(r["max_activation"] for r in by_feature[f]),
                 st.stdev(r["max_activation"] for r in by_feature[f])) for f in TARGETS}
    scores = defaultdict(list)
    for row in raw:
        f = int(row["feature_id"])
        if f in stats:
            mu, sd = stats[f]
            scores[row["item_id"]].append((row["max_activation"] - mu) / sd if sd else 0)
    grouped = defaultdict(list)
    for item, values in scores.items():
        a = assignments[item]
        grouped[(a["category"], a["template_id"])].append(st.mean(values))
    categories = defaultdict(list)
    for (category, _), values in grouped.items():
        categories[category].append(st.mean(values))
    category_means = {c: st.mean(v) for c, v in categories.items()}
    subjective_ids = [k for k, a in assignments.items() if a["category"] in
                      ("direct_consciousness_claim", "self_ref_mindfulness")]
    raw_positive_ids = {r["item_id"] for r in raw if int(r["feature_id"]) in TARGETS
                        and r["max_activation"] > 0}
    positivity = {"n_subjective_items": len(subjective_ids),
                  "any_target_raw_positive_items": sum(k in raw_positive_ids for k in subjective_ids),
                  "target_mean_z_positive_items": sum(st.mean(scores[k]) > 0 for k in subjective_ids),
                  "standardization": "per-feature sample SD over all 1120 discovery items, then mean of six z scores",
                  "live_correction_checked_2026_09_29": "https://praxagent.ai/blog/posts/2026/07/how-to-read-an-sae-feature-id/"}
    gap = st.mean(category_means[c] for c in DECEPTION) - st.mean(category_means[c] for c in NEUTRAL)
    ext_scores = defaultdict(list)
    for row in inputs.read(extension + "item_feature_activations.jsonl"):
        f = int(row["feature_id"])
        if f in stats:
            mu, sd = stats[f]
            ext_scores[row["item_id"]].append((row["max_activation"] - mu) / sd if sd else 0)
    feature_cues = {f: {r["cue"] for r in lexicon["features"][str(f)]["cues"]} for f in TARGETS}
    from experiments.review_audit.cue_discovery_v2 import terms
    text_terms = {k: terms(r["text"]) for k, r in corpus.items()}
    cue_support = {str(f): {cue: sum(r["max_activation"] > 0 and cue in text_terms[r["item_id"]]
                                   for r in by_feature[f]) for cue in sorted(feature_cues[f])}
                   for f in TARGETS}
    classes = defaultdict(list)
    mismatch = Counter()
    pairs = []
    for row in counterfactuals:
        if row["variant_type"] not in ("neutral_cue_transplant", "subjective_cue_transplant"):
            continue
        if row["item_id"] not in ext_scores:
            raise ValueError("Missing counterfactual activations")
        mismatch["total"] += 1
        mismatch["at_least_one_outside_assigned_feature"] += any(c not in feature_cues[int(row["assigned_feature_id"])] for c in row["assigned_cues"])
        if row["variant_type"] == "neutral_cue_transplant":
            delta = st.mean(ext_scores[row["item_id"]]) - st.mean(ext_scores[row["source_paraphrase_item_id"]])
            name = cue_class(row["assigned_cues"], feature_cues[22004])
            classes[name].append(delta)
            pairs.append({"item_id": row["item_id"], "cue_class": name, "assigned_cues": row["assigned_cues"], "delta": delta})
    from experiments.exp2_sae.analyze_public_sae_mapping_stability import observed_feature_tops, bootstrap_feature
    tops = observed_feature_tops(raw)
    stability = []
    all_templates = sorted({r["template_id"] for r in assignments.values()})
    category_order = list(dict.fromkeys(a["category"] for a in assignments.values()))
    for f, rows in sorted(by_feature.items()):
        if not any(r["max_activation"] > 0 for r in rows):
            continue
        template_values = defaultdict(list)
        for r in rows:
            a = assignments[r["item_id"]]
            template_values[(a["category"], a["template_id"])].append(r["max_activation"])
        template_means = {k: st.mean(v) for k, v in template_values.items()}
        def top_without(removed=None):
            means = {c: st.mean(v for (cat, t), v in template_means.items() if cat == c and t != removed)
                     for c in category_order}
            return max(means, key=means.get)
        cluster_top = top_without()
        item_bootstrap = bootstrap_feature(f, rows, tops[f], stability_iterations, seed)
        stability.append({"feature_id": f, "role": tops[f]["feature_role"],
                          "item_bootstrap_win_rate": item_bootstrap["observed_top_bootstrap_win_rate"],
                          "same_cluster_top": cluster_top == tops[f]["top_category"],
                          "deletions": len(all_templates),
                          "deletion_top_changes": sum(top_without(t) != cluster_top for t in all_templates)})
    sizes = Counter(r["template_id"] for r in assignments.values())
    effective = {c: 1 / sum((n / sum(v for t, v in sizes.items() if t.startswith(c + ":"))) ** 2
                              for t, n in sizes.items() if t.startswith(c + ":")) for c in categories}
    pooled = lexicon["pooled_cues"]
    return {"high_sets": {str(f): high_set_diagnostic(by_feature[f]) for f in TARGETS},
            "cue_positive_item_support": cue_support,
            "pooled_cues": [r["cue"] for r in pooled],
            "pooled_distinct_scores": len({r["max_feature_pmi_score"] for r in pooled}),
            "assignment_mismatch": dict(mismatch), "discovery_gap_fixed": gap,
            "neutral_pairs": len(pairs), "neutral_mean_delta": st.mean(r["delta"] for r in pairs),
            "original_recovery_recomputed": st.mean(r["delta"] for r in pairs) / gap,
            "posthoc_cue_classes": {name: {"n": len(v), "mean_delta": st.mean(v), "recovery_fixed_gap": st.mean(v) / gap} for name, v in sorted(classes.items())},
            "corpus": {"n_items": len(assignments), "n_templates": len(sizes), "effective_templates_median": st.median(effective.values())},
            "raw_versus_standardized_positivity": positivity,
            "active_feature_stability": stability,
            "boundaries": ["Cue classes were defined after reading the review and outcomes.",
                           "Discovery denominator and feature standardization remain fixed; no new ratio CI.",
                           "No natural-corpus, decoder-causality, or human category validation is implied."]}


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def chronology_audit(inputs):
    records = []
    for name, judgment_name in (("pilot_v1_20260709", "judgments.jsonl"), ("pilot_v2_20260709", "judgments_openai.jsonl"), ("confirmatory_v1_20260709", "judgments_paper.jsonl")):
        base = "data/causal_transplant/" + name + "/"
        if not (inputs.root / base / "manifest.json").exists():
            records.append({"run": name, "status": "unavailable_local_only_artifacts"})
            continue
        manifest = inputs.read(base + "manifest.json")
        outcomes = inputs.read(base + "outcomes.jsonl")
        bank = inputs.read(base + "induction_bank.jsonl")
        judgments = inputs.read(base + judgment_name)
        commit = manifest["git_commit_at_start"]
        commit_time = git(inputs.root, "show", "-s", "--format=%cI", commit)
        effects = []
        analyses = []
        for judge in sorted({r["judge_key"] for r in judgments}):
            blocks, incomplete = block_effects(outcomes, labels(judgments, judge, "paper_label"), anchors=tuple(manifest["anchor_cells"]))
            effects.append({"judge": judge, "incomplete": incomplete,
                            "panel_effects": {f: st.mean(st.mean(r[f] for r in rows) for rows in blocks.values()) for f in next(iter(blocks.values()))[0]}})
            path = base + f"analysis_{judge.split(':')[0]}_paper/analysis_manifest.json"
            if (inputs.root / path).exists():
                analyses.append({"judge": judge, "created_at_utc": inputs.read(path)["created_at_utc"]})
        first_induction = min(r["completed_at_utc"] for r in bank)
        records.append({"run": name, "start_commit": commit, "commit_time": commit_time,
                        "containing_refs": git(inputs.root, "for-each-ref", "--contains=" + commit, "--format=%(refname)"),
                        "runtime_start": manifest["created_at_utc"], "runtime_end": manifest["completed_at_utc"],
                        "first_induction_completed": first_induction,
                        "first_final_outcome_completed": min(r["completed_at_utc"] for r in outcomes),
                        "commit_to_runtime_start_seconds": (datetime.fromisoformat(manifest["created_at_utc"]) - datetime.fromisoformat(commit_time)).total_seconds() if commit_time else None,
                        "n_inductions": len(bank), "n_outcomes": len(outcomes), "analyses": analyses, "raw_recomputed_effects": effects})
    return {"records": records, "boundary": "Local Git timestamps are not trusted external timestamps; runtime start is not the first completed outcome. Missing pilots/objects are explicit, not inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--outdir", type=Path, default=ROOT / "out/posthoc_review_measurement_20260929")
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--stability-bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260709)
    args = parser.parse_args()
    if args.bootstrap < 1 or args.stability_bootstrap < 1:
        parser.error("Bootstrap counts must be positive")
    destination = args.outdir.resolve()
    for root in {ROOT, args.root.resolve()}:
        if destination == root / "data" or root / "data" in destination.parents:
            parser.error("Audit output may not be written into data/ (frozen releases)")
    inputs = Inputs(args.root.resolve())
    result = {"status": "posthoc_review_audit_2026-09-29", "bootstrap": args.bootstrap,
              "stability_bootstrap": args.stability_bootstrap, "seed": args.seed,
              "causal": causal_audit(inputs, args.bootstrap, args.seed), "gemma": gemma_audit(inputs),
              "semantics": semantics_audit(inputs, args.stability_bootstrap, args.seed),
              "chronology": chronology_audit(inputs)}
    result["input_sha256"] = dict(sorted(inputs.hashes.items()))
    for path, expected in inputs.hashes.items():
        if hashlib.sha256((inputs.root / path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Input changed while auditing: {path}")
    result["input_hashes_still_match_after_audit"] = True
    source_paths = ["experiments/review_audit/cue_discovery_v2.py",
                    "experiments/causal_transplant/analyze_causal_transplant.py",
                    "experiments/exp2_sae/build_sae_construct_validity_extension.py",
                    "experiments/exp2_sae/analyze_public_sae_mapping_stability.py",
                    "experiments/exp2_sae/analyze_public_sae_mapping_template_robustness.py",
                    "experiments/exp2_sae/analyze_public_sae_mapping_interpretation.py"]
    result["supporting_source_sha256"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "audit.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
