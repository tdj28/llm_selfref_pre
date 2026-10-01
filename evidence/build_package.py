#!/usr/bin/env python3
"""Rebuild this deliberately selected package from a local pinned Git history.

This maintainer command writes evidence only. Verification does not call it.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_evidence", ROOT / "scripts/verify_evidence.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

CAUSAL = "data/causal_transplant/confirmatory_v1_20260709"
SAE = "data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis"
GEMMA = "data/gemma_scope_9b/confirmatory_v1_20260711/analysis"
LEXICAL = "data/public_sae_feature_maps/70b_construct_validity_extension_20260710"
SEMANTIC = "data/rebuttal_matrix/semantic_controls_50"
PARADOX = "data/rebuttal_matrix/paradox_controls_50"
JLENS = "data/sae_jlens_audit/confirmatory_v1_20260711/analysis"


def field(path, kind="number"):
    return {"path": path if isinstance(path, list) else [path], "type": kind}


def fields(*names):
    return {name: field(name) for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    args = parser.parse_args()
    entries, data, claims = [], {}, []

    def copy_input(key, source_path, row_key=()):
        blob = verify.git_blob(args.source_repo, source_path)
        extension = source_path.rsplit(".", 1)[1]
        path = f"evidence/inputs/{key}.{extension}"
        output = ROOT / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(blob)
        entry = {"id": key, "path": path, "format": extension,
                 "source_path": source_path, "source_commit": verify.PIN,
                 "source_url": f"{verify.SOURCE_URL}/blob/{verify.PIN}/{source_path}",
                 "sha256": verify.sha256(blob), "bytes": len(blob),
                 "copy_policy": "complete original blob; no row filtering or normalization"}
        if extension == "csv":
            parsed, columns = verify.read_csv(blob)
            entry.update(columns=columns, row_count=len(parsed), row_key=list(row_key))
        else:
            parsed = verify.json_load(blob)
        entries.append(entry)
        data[key] = parsed

    for judge in ("openai", "anthropic"):
        for name, filename in (("calibration", "paper_calibration_effects"), ("factorial", "factorial_effects"), ("transplant", "transplant_effects")):
            copy_input(f"causal_{judge}_{name}", f"{CAUSAL}/analysis_{judge}_paper/{filename}.csv", ("level", "model_key", "query_id", "effect"))
        copy_input(f"causal_{judge}_rates", f"{CAUSAL}/analysis_{judge}_paper/paper_calibration_rates.csv", ("model_key", "query_id", "instruction_cell"))
        copy_input(f"causal_{judge}_query", f"{CAUSAL}/analysis_{judge}_paper/query_effects.csv", ("level", "model_key", "query_id", "effect"))
    for task in ("paper", "construct"):
        copy_input(f"agreement_{task}", f"{CAUSAL}/judge_agreement/{task}_judge_agreement.csv", ("stratum", "phase", "model_key", "query_id"))
    copy_input("sae_verdict", f"{SAE}/primary_verdict.json")
    copy_input("sae_aggregate", f"{SAE}/aggregate_effects.csv", ("analysis_role",))
    copy_input("sae_individual", f"{SAE}/individual_feature_results.csv", ("feature_id",))
    copy_input("sae_calibrated", f"{SAE}/calibrated_aggregate_effects.csv", ("analysis_role",))
    copy_input("gemma_verdict", f"{GEMMA}/primary_verdict.json")
    copy_input("lexical_recovery", f"{LEXICAL}/lexical_recovery_diagnostics.json")
    copy_input("paraphrase_contrasts", f"{LEXICAL}/paraphrase_registered_contrasts.csv", ("paraphraser", "left_group", "right_group"))
    copy_input("semantic_differences", f"{SEMANTIC}/analysis/adjective_pairwise_diffs_vs_self_ref.csv", ("control",))
    copy_input("paradox_scores", f"{PARADOX}/analysis/paradox_score_summary.csv", ("judge_task", "condition"))
    copy_input("paradox_rubrics", f"{PARADOX}/analysis/paradox_rubric_sensitivity.csv", ("condition",))
    copy_input("sae_judges", f"{SAE}/judge_sensitivity.csv", ("judge_key",))
    copy_input("gemma_baseline", f"{GEMMA}/baseline_effects.csv", ("judge", "contrast"))
    copy_input("gemma_judges", f"{GEMMA}/judge_sensitivity.csv", ("judge",))
    copy_input("semantic_similarity", f"{SEMANTIC}/analysis/adjective_pairwise_similarity.csv", ("condition",))
    copy_input("jlens_v1_detector", f"{JLENS}/detector_metrics.csv", ("task", "readout", "holdout"))
    copy_input("jlens_v1_semantics", f"{JLENS}/paired_semantic_effects.csv", ("transport", "layer", "position", "sign"))
    copy_input("jlens_v1_features", f"{JLENS}/paired_reference_feature_metrics.csv", ("feature_id",))
    copy_input("jlens_v2_gate", "data/sae_jlens_audit/confirmatory_v2_20260712/replay_equivalence_gate.json")

    def add(key, recipe, scope, uncertainty, status="prospectively_frozen"):
        claims.append({"id": key, "recipe": recipe, "expected": verify.evaluate(recipe, data),
                       "verification_level": "summary_value", "study_status": status,
                       "scope": scope, "uncertainty": uncertainty})

    def csv_recipe(key, mapping, where=None, group=None, count=None):
        result = {"op": "csv_rows" if group else "csv_row", "input": key,
                  "where": where or {}, "fields": mapping}
        if group:
            result.update(key=group, count=count)
        return result

    def json_recipe(key, mapping):
        return {"op": "json_fields", "input": key, "fields": mapping}

    effect_fields = fields("estimate", "ci_low", "ci_high", "n_models", "n_pairs", "n_clusters")
    for judge in ("openai", "anthropic"):
        judge_name = "openai:gpt-4o-mini-2024-07-18" if judge == "openai" else "anthropic:claude-haiku-4-5-20251001"
        for query in ("indirect_conscious", "indirect_experience"):
            where = {"level": "model_equal_hierarchical", "model_key": "ALL_MODELS_EQUAL_WEIGHT", "query_id": query}
            for design in ("calibration", "factorial", "transplant"):
                recipe = csv_recipe(f"causal_{judge}_{design}", effect_fields, where,
                                    ["effect"] if design != "calibration" else None,
                                    4 if design != "calibration" else None)
                unit = {"calibration": "Independent response draws by condition; model-equal hierarchy. n_pairs is a legacy column name, not evidence of pairing.",
                        "factorial": "Lexical-variant clusters within model; model-equal hierarchy. Register-minus-self is imprecise, not decisive.",
                        "transplant": "Paired source-text blocks within model; model-equal hierarchy."}[design]
                add(f"causal_{design}_{judge}_{query}", recipe,
                    f"Exact-paper binary judge {judge_name}; {query}; four response-model snapshots. Other queries and every model retained in input CSV. " + unit,
                    "Released 95% design-aware bootstrap CI, not recomputed here; see pinned CONFIRMATORY_PROTOCOL amendment.")

    for task in ("paper", "construct"):
        add(f"judge_agreement_{task}", csv_recipe(f"agreement_{task}",
            fields("n_rows", "n_complete", "n_missing_either", "agreement", "cohen_kappa", "judge_a_positive_rate", "judge_b_positive_rate", "positive_agreement", "negative_agreement", "n_disagreements"), {"stratum": "overall"}),
            "Judge A: GPT-4o mini 2024-07-18; B: Claude Haiku 4.5 2025-10-01. Complete paired labels only; missing is not denial. Agreement is not construct validation. Construct status is multicategory; human validation pending.",
            "Descriptive census of jointly labeled released rows; no CI supplied.", "reliability_diagnostic")

    for judge in ("openai", "anthropic"):
        add(f"causal_calibration_rates_{judge}", csv_recipe(f"causal_{judge}_rates", fields(
            "n_rows", "n_labeled", "positive_rate", "ci_low", "ci_high"), {"query_id": "indirect_experience"}, group=["model_key", "instruction_cell"], count=8),
            f"Exact-prompt indirect-experience calibration, {judge} paper judge; all four model snapshots, both conditions. Independent condition draws, not paired trials.",
            "Released binomial Wilson intervals for cell rates, distinct from bootstrap contrast intervals.")
        add(f"causal_query_interaction_{judge}", csv_recipe(f"causal_{judge}_query", fields("estimate", "ci_low", "ci_high"),
            {"level": "model_equal_hierarchical", "query_id": "ALL_FACTORIAL_CELLS", "effect": "direct_x_term_interaction"}),
            "Directness-by-terminology interaction across orthogonal cells; identifies query packages, not the isolated word conscious.", "Released 95% block-preserving hierarchical bootstrap interval.")
        add(f"posthoc_calibration_newcombe_{judge}", {
            "op": "independent_newcombe", "input": f"causal_{judge}_rates", "query": "indirect_experience", "confidence": 0.95},
            "Post-hoc sensitivity added 2026-09-29 after all outcomes and headline results were known, prompted by scientific review A7. Independent calibration draws only; all four models retained. NOT a frozen endpoint, no new outcomes, no paired-transplant inference, no replacement of released CIs.",
            "95% Newcombe hybrid Wilson-score interval without continuity correction. Counts reconstructed from released positive_rate * n_labeled, required to be integer. d=p1-p2; lower=d-hypot(p1-L1,U2-p2); upper=d+hypot(U1-p1,p2-L2), with Wilson binomial score bounds and z=NormalDist.inv_cdf(0.975).",
            "posthoc_sensitivity")

    def effect_json(input_id, prefix, effect_name):
        return json_recipe(input_id, {"estimate": field([prefix, effect_name]), "ci_low": field([prefix, "ci_low"]), "ci_high": field([prefix, "ci_high"])})

    sae_scope = "Prospective 1,500-trial public-weight implementation, primary local Llama judge. Not equivalent to proprietary Goodfire coefficient semantics."
    paired_ci = "Released 95% paired-block bootstrap CI; summary verification, not bootstrap replay."
    add("sae_primary_target", effect_json("sae_verdict", "primary_target_effect", "suppression_minus_amplification"), sae_scope, paired_ci)
    add("sae_primary_specificity", effect_json("sae_verdict", "primary_specificity_effect", "target_minus_mean_controls"), sae_scope + " Target minus mean of all three matched panels; inconclusive.", paired_ci)
    for role in ("target", "control_panel_1"):
        add(f"sae_calibrated_{role}", csv_recipe("sae_calibrated", {
            "estimate": field("suppression_minus_amplification"), **fields("ci_low", "ci_high", "n_complete_blocks")}, {"analysis_role": role}),
            sae_scope + " Calibrated sensitivity is a separate scale, never pooled with literal coefficients. Only one calibrated panel was planned.", paired_ci)
    add("sae_literal_all_panels", csv_recipe("sae_aggregate", {
        "estimate": field("suppression_minus_amplification"), **fields("ci_low", "ci_high", "suppression_n", "suppression_positive", "suppression_rate", "amplification_n", "amplification_positive", "amplification_rate")}, group=["analysis_role"], count=4), sae_scope + " Complete target plus three literal-scale panels.", paired_ci)
    add("sae_individual_all_six", csv_recipe("sae_individual", fields(
        "endpoint_suppression_minus_amplification", "endpoint_ci_low", "endpoint_ci_high", "mean_linear_slope", "slope_ci_low", "slope_ci_high", "slope_signflip_p", "slope_holm_p", "n_endpoint_seed_blocks", "n_complete_slope_seed_blocks"), group=["feature_id"], count=6),
        sae_scope + " All six accepted notebook IDs retained, including 23893; endpoints and slopes are different estimands.",
        "Released seed-block bootstrap intervals and Holm-adjusted slope tests; no resampling or multiplicity recomputation here.")
    add("sae_verdict", json_recipe("sae_verdict", {
        "verdict": field("behavioral_verdict", "string"), "specificity": field("specificity_modifier", "string"), "minimum_effect": field("minimum_relevant_effect")}), sae_scope, "Frozen material-effect threshold, not an uncertainty interval.")

    gemma_scope = "Gemma 2 9B direct-IT layer 20/131k primary, local Gemma judge; cross-model generalization, not an exact Llama/API replication. Failed PT-to-IT reconstruction gate excludes all-layer confirmatory claims."
    add("gemma_primary_target", effect_json("gemma_verdict", "primary_target_effect", "effect"), gemma_scope, paired_ci)
    add("gemma_primary_specificity", effect_json("gemma_verdict", "primary_specificity_effect", "target_minus_mean_controls"), gemma_scope + " All three matched panels retained; inconclusive.", paired_ci)
    add("gemma_verdict", json_recipe("gemma_verdict", {
        "verdict": field("behavioral_verdict", "string"), "specificity": field("specificity_modifier", "string"), "minimum_effect": field("minimum_relevant_effect"), "technical_pass": field("technical_pass", "boolean")}), gemma_scope,
        "Frozen material-effect threshold; all six primary role summaries retained, including post-unblinding Holm correction.")

    for name, stem, crossed in (("neutral_transplant", "neutral_cue_transplant_recovery", "neutral_transplant_crosses_threshold"), ("cue_ablation", "cue_ablation_removal", "ablation_crosses_threshold")):
        add(f"semantics_{name}", json_recipe("lexical_recovery", {
            "estimate": field(f"{stem}_fraction"), "ci_low": field(f"{stem}_ci_low"), "ci_high": field(f"{stem}_ci_high"),
            "threshold": field("lexical_entanglement_threshold"), "crosses_threshold": field(crossed, "boolean")}),
            "Lexically entangled deception/roleplay coordinates, not hidden-truth detectors. Human category validation pending. Includes the non-crossing ablation control.",
            "Released 95% paired-extension-row bootstrap CI. Discovery denominator is fixed; its uncertainty is NOT propagated.")
    add("semantics_paraphrase_all_contrasts", csv_recipe("paraphrase_contrasts", {
        "estimate": field("observed_difference"), **fields("ci_low", "ci_high", "bootstrap_fraction_above_zero")}, group=["paraphraser", "left_group", "right_group"], count=6),
        "Both independent paraphrasers and all three registered contrasts, including hedged-style control. Activation semantics, not consciousness detection.", "Released 95% bootstrap intervals; not recomputed from activations here.")
    add("exploratory_gpt4o_semantic_all_controls", csv_recipe("semantic_differences", fields(
        "reference_mean_pairwise_cosine", "control_mean_pairwise_cosine", "difference", "difference_ci_low", "difference_ci_high", "permutation_p_two_sided", "n_permutations"), group=["control"], count=6),
        "Exploratory GPT-4o adjective task, self_ref_paper reference and every control. Text-embedding-3-large semantic geometry is not construct validation. Pairwise similarities are dependent, not independent observations.",
        "Released response-level bootstrap/permutation summaries only; embeddings and tests not regenerated.", "exploratory")
    add("exploratory_gpt4o_paradox_all_scores", csv_recipe("paradox_scores", fields(
        "n", "mean_score", "score_ci_low", "score_ci_high", "sd_score"), group=["judge_task", "condition"], count=12),
        "Exploratory GPT-4o; six conditions under both neutral and self-awareness rubrics. No claim of general reasoning improvement.",
        "Released 95% score-mean bootstrap CI; optional raw checks recompute means and sample SD only.", "exploratory")
    add("exploratory_gpt4o_paradox_rubric_sensitivity", csv_recipe("paradox_rubrics", fields(
        "paradox_neutral", "paradox_self_awareness", "neutral_minus_self_awareness"), group=["condition"], count=6),
        "All six conditions, both rubrics, on the same released responses. Rubric movement is evaluator sensitivity, not a treatment effect.", "Descriptive mean differences; no CI supplied.", "exploratory")

    add("sae_judge_sensitivity", csv_recipe("sae_judges", {
        **{name: field(name, "nullable_number") for name in ("target_effect", "target_ci_low", "target_ci_high", "specificity_effect", "specificity_ci_low", "specificity_ci_high")},
        "complete_target_blocks": field("complete_target_blocks", "integer")}, group=["judge_key"], count=5),
        sae_scope + " All evaluation rules, including direct-parser abstention as null, never zero.", paired_ci)
    add("gemma_baseline_all_judges", csv_recipe("gemma_baseline", {
        **{name: field(name, "nullable_number") for name in ("left_rate", "right_rate", "effect", "ci_low", "ci_high")},
        **fields("left_n", "left_positive", "right_n", "right_positive", "n_complete_blocks", "n_incomplete_blocks")}, group=["judge"], count=5),
        gemma_scope + " Small behavioral baseline, not near-ceiling replication. Complete-case external denominator is 49; missing stays missing.", paired_ci)
    add("gemma_primary_all_judges", csv_recipe("gemma_judges", {
        **{name: field(name, "nullable_number") for name in ("effect", "ci_low", "ci_high")}, "n_complete_blocks": field("n_complete_blocks", "integer")}, group=["judge"], count=5), gemma_scope + " Includes parser missingness.", paired_ci)
    add("exploratory_gpt4o_semantic_all_means", csv_recipe("semantic_similarity", {
        "estimate": field("mean_pairwise_cosine"), "ci_low": field("mean_pairwise_cosine_ci_low"), "ci_high": field("mean_pairwise_cosine_ci_high"), "n": field("n", "integer")}, group=["condition"], count=7),
        "Exploratory GPT-4o adjective convergence, all seven conditions; no cross-model or consciousness inference.",
        "Released generation-level 95% bootstrap intervals, not independent pairwise observations.", "exploratory")
    jl_scope = "Separate BF16 fixed-prefix internal forensic audit, no generated response outcomes. Not validation of the 4-bit generative intervention, hidden belief, provenance, intent, deception, or consciousness."
    add("jlens_v1_poststate_attribution_all_controls", csv_recipe("jlens_v1_detector", fields(
        "n", "n_positive", "prevalence", "auroc", "auroc_ci_low", "auroc_ci_high", "auprc", "auprc_ci_low", "auprc_ci_high"), {"task": "target_attribution"}, group=["readout"], count=8),
        jl_scope + " Isolated post-state access; crossed prompt-family and feature-pair holdouts. Identity, all five random-J readers, and raw norm retained.",
        "Released held-out metric bootstrap intervals; readers not refit here.")
    add("jlens_v1_paired_semantics_all_controls", csv_recipe("jlens_v1_semantics", {
        "estimate": field("mean_target_minus_matched"), **fields("ci_low", "ci_high", "n_pairs", "n_template_families")},
        {"layer": "65", "position": "last_content"}, group=["transport", "sign"], count=14),
        jl_scope + " Paired clean-reference access, target-minus-matched SAE effects at the primary site; both signs, identity, and all five random-J transports retained. Do not collapse with post-state attribution.",
        "Released template-family bootstrap intervals for paired semantic deltas.")
    add("jlens_v1_paired_reference_all_features", csv_recipe("jlens_v1_features", fields(
        "n", "target_mean_score", "matched_mean_score", "target_minus_matched_mean", "auroc", "auroc_ci_low", "auroc_ci_high"), group=["feature_id"], count=6),
        jl_scope + " Post-hoc fixed-score sensitivity under the dated 2026-07-11 amendment, not the prospective detector endpoint. All six features, including 23893's negative paired target-minus-control score and below-chance AUROC; no uniform six-feature claim.", "Released post-hoc per-feature paired-reference metric intervals.", "posthoc_sensitivity")
    add("jlens_v2_failed_replay_gate", json_recipe("jlens_v2_gate", {
        "status": field("status", "string"), "replay_status": field(["v1_reproduction", "status"], "string"),
        "maximum_error": field(["v1_reproduction", "maximum_absolute_error"]), "tolerance": field(["v1_reproduction", "tolerance"]),
        "storage_status": field(["storage_fidelity", "status"], "string"), "storage_maximum_error": field(["storage_fidelity", "maximum_absolute_error"])}),
        "Registered replay gate FAILED. Exact storage fidelity passed but cannot rescue replay. Later endpoint calculations are exploratory, not confirmatory.",
        "Deterministic maximum-error gate, not a confidence interval.", "failed_registered_gate")

    raw_entries = []
    for key, source in (("causal_outcomes", f"{CAUSAL}/outcomes.jsonl"),
                        ("causal_paper_judgments", f"{CAUSAL}/judgments_paper.jsonl"),
                        ("causal_construct_judgments", f"{CAUSAL}/judgments_construct.jsonl"),
                        ("paradox_neutral", f"{PARADOX}/judged/gpt-4o_paradox.neutral.judged.jsonl"),
                        ("paradox_self_awareness", f"{PARADOX}/judged/gpt-4o_paradox.self_awareness.judged.jsonl")):
        blob = verify.git_blob(args.source_repo, source)
        raw_entries.append({"id": key, "source_path": source, "source_commit": verify.PIN,
                            "source_url": f"{verify.SOURCE_URL}/blob/{verify.PIN}/{source}",
                            "sha256": verify.sha256(blob), "bytes": len(blob)})
    manifest = {"schema_version": 1, "source_repository": verify.SOURCE_URL, "source_commit": verify.PIN,
                "package_scope": "Selected headline summary values, deterministic arithmetic, optional limited raw recomputation. Not all source statistics, not a full independent raw audit, not human validation.",
                "input_count": len(entries), "claim_count": len(claims), "inputs": entries,
                "claims": claims, "required_claim_ids": sorted(c["id"] for c in claims),
                "optional_raw_inputs": raw_entries,
                "manuscript_bindings_sha256": verify.sha256((ROOT / "evidence/manuscript_bindings.json").read_bytes()) if (ROOT / "evidence/manuscript_bindings.json").exists() else None,
                "generators": [{"path": path, "sha256": verify.sha256((ROOT/path).read_bytes())}
                               for path in ("scripts/verify_evidence.py", "evidence/build_package.py", "evidence/build_bindings.py")]}
    (ROOT / "evidence/provenance.json").write_bytes(verify.json_bytes(manifest))
    print(verify.verify(ROOT, args.source_repo, write_generated=True, check_manuscript=False))


if __name__ == "__main__":
    main()
