#!/usr/bin/env python3
"""Explicit literal headline bindings; not automatic acceptance of prose."""

import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify", ROOT / "scripts/verify_evidence.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def ref(claim, *path, scale=1):
    return {"claim": claim, "path": list(path), "scale": scale}


def raw(input_id, *path):
    return {"input": input_id, "path": list(path)}


def triple(claim, prefix=()):
    return [ref(claim, *prefix, key) for key in ("estimate", "ci_low", "ci_high")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    args = parser.parse_args()
    source = v.normalized_tex((ROOT / "paper/main.tex").read_text())
    bindings = []

    def bind(key, text, values, prefix=""):
        count = source.count(v.normalized_tex(prefix + text))
        v.require(count > 0, f"review required: binding passage absent: {key}")
        bindings.append({"id": key, "prefix": prefix, "text": text, "occurrences": count, "values": values})

    for judge, text in (("openai", "0.638 [0.262, 1.000]"), ("anthropic", "0.650 [0.275, 1.000]")):
        bind(f"calibration_{judge}", text, triple(f"causal_calibration_{judge}_indirect_experience"))
    transplant = [
        ("openai", "instruction_source_main", "0.738 [0.519, 0.950]"),
        ("anthropic", "instruction_source_main", "0.781 [0.550, 1.000]"),
        ("openai", "transcript_source_main", "$-0.100$ [$-0.288$, 0.075]"),
        ("anthropic", "transcript_source_main", "$-0.131$ [$-0.306$, 0.000]"),
        ("openai", "instruction_minus_transcript", "0.838 [0.688, 0.963]"),
        ("anthropic", "instruction_minus_transcript", "0.913 [0.750, 1.000]"),
    ]
    for judge, effect, text in transplant:
        bind(f"transplant_{judge}_{effect}", text, triple(f"causal_transplant_{judge}_indirect_experience", (effect,)))
    model_transcripts = (
        ("GPT-4o", "openai:gpt-4o-2024-11-20", "0.125 [0.049, 0.225] & 0.000 [0.000, 0.000]"),
        ("GPT-4.1", "openai:gpt-4.1-2025-04-14", "0.000 [0.000, 0.000] & 0.000 [0.000, 0.000]"),
        ("Haiku 4.5", "anthropic:claude-haiku-4-5-20251001", "$-0.175$ [$-0.350$, 0.000] & $-0.150$ [$-0.300$, 0.000]"),
        ("Sonnet 4.5", "anthropic:claude-sonnet-4-5-20250929", "$-0.350$ [$-0.475$, $-0.225$] & $-0.375$ [$-0.525$, $-0.225$]"),
    )
    for label, model, text in model_transcripts:
        expressions = []
        for judge in ("openai", "anthropic"):
            input_id = f"causal_{judge}_transplant"
            rows, _ = v.read_csv((ROOT / f"evidence/inputs/{input_id}.csv").read_bytes())
            indices = [i for i, row in enumerate(rows) if row["level"] == "model"
                       and row["model_key"] == model and row["query_id"] == "indirect_experience"
                       and row["effect"] == "transcript_source_main"]
            v.require(len(indices) == 1, "ambiguous model transcript binding")
            expressions.extend(raw(input_id, indices[0], field)
                               for field in ("estimate", "ci_low", "ci_high"))
        bind("transcript_table_" + model, text, expressions, label + " & ")
    factorial = [
        ("openai", "self_reference_main", "$-0.019$ [$-0.231$, 0.244]"),
        ("anthropic", "self_reference_main", "0.000 [$-0.250$, 0.269]"),
        ("openai", "phenomenological_register_main", "0.269 [0.000, 0.550]"),
        ("anthropic", "phenomenological_register_main", "0.188 [$-0.062$, 0.475]"),
        ("openai", "register_minus_self", "0.288 [$-0.113$, 0.613]"),
        ("anthropic", "register_minus_self", "0.188 [$-0.175$, 0.500]"),
    ]
    for judge, effect, text in factorial:
        bind(f"factorial_{judge}_{effect}", text, triple(f"causal_factorial_{judge}_indirect_experience", (effect,)))
    bind("query_interaction", "0.525 under both judges, with intervals [0.141, 0.913] and [0.125, 0.944]", [
        ref("causal_query_interaction_openai", "estimate"), ref("causal_query_interaction_openai", "ci_low"), ref("causal_query_interaction_openai", "ci_high"),
        ref("causal_query_interaction_anthropic", "ci_low"), ref("causal_query_interaction_anthropic", "ci_high")])
    for name, model, numeric in (
        ("GPT-4o", "openai:gpt-4o-2024-11-20", "0.00 / 0.00 & 1.00 / 1.00 & 1.00 / 1.00"),
        ("GPT-4.1", "openai:gpt-4.1-2025-04-14", "0.00 / 0.00 & 1.00 / 1.00 & 1.00 / 1.00"),
        ("Haiku 4.5", "anthropic:claude-haiku-4-5-20251001", "0.15 / 0.05 & 0.50 / 0.45 & 0.35 / 0.40"),
        ("Sonnet 4.5", "anthropic:claude-sonnet-4-5-20250929", "0.75 / 0.65 & 0.95 / 0.85 & 0.20 / 0.20"),
    ):
        cells = {judge: {cell: ref(f"causal_calibration_rates_{judge}", model+"/paper_"+cell, "positive_rate")
                        for cell in ("history", "self_ref")} for judge in ("openai", "anthropic")}
        values = [cells[j][c] for c in ("history", "self_ref") for j in ("openai", "anthropic")]
        values += [{"op": "subtract", "args": [cells[j]["self_ref"], cells[j]["history"]]} for j in ("openai", "anthropic")]
        bind("calibration_table_"+model, numeric, values, name + " & ")
    bind("paper_judge_agreement", r"2,423/2,556 responses (94.8\%; $\kappa=0.879$)", [
        {"op": "subtract", "args": [ref("judge_agreement_paper", "n_complete"), ref("judge_agreement_paper", "n_disagreements")]},
        ref("judge_agreement_paper", "n_complete"), ref("judge_agreement_paper", "agreement", scale=100), ref("judge_agreement_paper", "cohen_kappa")])
    # Preserve the historical field, whose definition is Jaccard rather than Dice.
    bind("construct_jaccard", r"6.3\% affirmative-set Jaccard index", [ref("judge_agreement_construct", "positive_agreement", scale=100)])
    def operation(name, left, right):
        return {"op": name, "args": [left, right]}

    jaccard = ref("judge_agreement_construct", "positive_agreement")
    total_positives = operation("add", *[
        operation("multiply", ref("judge_agreement_construct", "n_complete"),
                  ref("judge_agreement_construct", f"judge_{judge}_positive_rate"))
        for judge in ("a", "b")])
    union = operation("divide", total_positives, operation("add", {"constant": 1}, jaccard))
    intersection = operation("multiply", jaccard, union)
    twice_intersection = operation("multiply", {"constant": 2}, intersection)
    dice_percent = operation("multiply", {"constant": 100},
                             operation("divide", twice_intersection, total_positives))
    bind("construct_overlap_counts", "intersection is 19 and the union 300", [intersection, union])
    bind("construct_positive_agreement_dice", r"38/319=11.9\%", [twice_intersection, total_positives, dice_percent])
    bind("construct_affirmations", "19 versus 300 responses affirmative", [{"op": "multiply", "args": [ref("judge_agreement_construct", "n_complete"), ref("judge_agreement_construct", f"judge_{j}_positive_rate")]} for j in ("a", "b")])
    bind("construct_raw_agreement", r"84.1\% raw agreement", [ref("judge_agreement_construct", "agreement", scale=100)])
    for key, text in (("sae_primary_target", "0.00 [$-0.06$, 0.06]"), ("sae_primary_specificity", "$-0.0267$ [$-0.1000$, 0.0467]"),
                      ("sae_calibrated_target", "$-0.10$ [$-0.22$, 0.02]"), ("sae_calibrated_control_panel_1", "0.12 [0.04, 0.22]"),
                      ("gemma_primary_target", "$-0.02$ [$-0.10$, 0.06]"), ("gemma_primary_specificity", "$-0.013$ [$-0.107$, 0.073]")):
        bind(key, text, triple(key))
    for role, text in (("target", "0.00 & [$-0.06$, 0.06]"), ("control_panel_1", "0.06 & [$-0.04$, 0.16]"),
                       ("control_panel_2", "0.02 & [0.00, 0.06]"), ("control_panel_3", "0.00 & [$-0.06$, 0.06]")):
        label = "Target" if role == "target" else "Panel " + role[-1]
        bind("literal_table_"+role, text, triple("sae_literal_all_panels", (role,)), "Literal & " + label + " & ")
    bind("literal_table_specificity", "$-0.0267$ & [$-0.1000$, 0.0467]", triple("sae_primary_specificity"), "Literal & Target minus mean controls & ")
    for role, text in (("target", "$-0.10$ & [$-0.22$, 0.02]"), ("control_panel_1", "0.12 & [0.04, 0.22]")):
        bind("calibrated_table_"+role, text, triple("sae_calibrated_"+role), "Calibrated & " + ("Target" if role == "target" else "Panel 1") + " & ")
    bind("sae_rates", "48/50 positives under each sign: 0.96 versus 0.96", [ref("sae_literal_all_panels", "target", k) for k in ("suppression_positive", "suppression_n", "suppression_rate", "amplification_rate")])
    bind("sae_minimum", "frozen 0.30 minimum", [ref("sae_verdict", "minimum_effect")])
    bind("sae_external_gpt", "$-0.04$ [$-0.16$, 0.08]", [ref("sae_judge_sensitivity", "openai:gpt-4o-mini-2024-07-18", k) for k in ("target_effect", "target_ci_low", "target_ci_high")])
    bind("sae_external_claude_majority", "$-0.06$ [$-0.18$, 0.06]", [ref("sae_judge_sensitivity", "anthropic:claude-haiku-4-5-20251001", k) for k in ("target_effect", "target_ci_low", "target_ci_high")])
    bind("lexical_recovery", r"64.4\% [50.3\%, 78.7\%]", [ref("semantics_neutral_transplant", k, scale=100) for k in ("estimate", "ci_low", "ci_high")])
    bind("gemma_rates", "6/50 positive labels under suppression and 7/50 under amplification", [raw("gemma_verdict", "primary_target_effect", k) for k in ("left_positive", "left_n", "right_positive", "right_n")])
    bind("gemma_control_effects", "0.00, $-0.06$, and 0.04", [raw("gemma_verdict", "primary_role_effects", f"matched_control_{i}", "effect") for i in (1, 2, 3)])
    bind("gemma_baseline_local", "0.12 [0.04, 0.22] locally", [ref("gemma_baseline_all_judges", "gemma_local", k) for k in ("effect", "ci_low", "ci_high")])
    bind("gemma_baseline_gpt", "0.06 [0.00, 0.14]", [ref("gemma_baseline_all_judges", "openai", k) for k in ("effect", "ci_low", "ci_high")])
    bind("gemma_baseline_claude_majority", "0.020 [0.000, 0.061]", [ref("gemma_baseline_all_judges", "anthropic", k) for k in ("effect", "ci_low", "ci_high")])
    bind("gemma_hedging", "0.16 [0.04, 0.30] locally", [raw("gemma_verdict", "primary_role_effects", "hedging_refusal", k) for k in ("effect", "ci_low", "ci_high")])
    bind("gemma_hedging_holm", "$p=0.231$", [raw("gemma_verdict", "primary_role_effects", "hedging_refusal", "exact_discordant_holm_p_across_primary_roles")])
    bind("jlens_poststate", "AUROC 0.4998 [0.4978, 0.5016]", [ref("jlens_v1_poststate_attribution_all_controls", "jacobian", k) for k in ("auroc", "auroc_ci_low", "auroc_ci_high")])
    bind("jlens_failed_gate", "maximum error 0.25 against 0.02", [ref("jlens_v2_failed_replay_gate", k) for k in ("maximum_error", "tolerance")])
    bind("semantic_convergence", "0.841 [0.820, 0.870] for self-reference, versus 0.889 [0.874, 0.909]", [ref("exploratory_gpt4o_semantic_all_means", condition, k) for condition in ("self_ref_paper", "history_paper") for k in ("estimate", "ci_low", "ci_high")])
    bind("paradox_means", "3.04 for self-reference, 3.38 for zero-shot, and 3.24 for conceptual", [ref("exploratory_gpt4o_paradox_all_scores", "paradox_self_awareness/"+condition, "mean_score") for condition in ("self_ref_paper", "zero_shot", "conceptual_paper")])

    figures = []
    for name, source_path in (
        ("causal_decomposition.png", "paper/results/causal_decomposition.png"),
        ("causal_factorial_effects.png", "paper/results/causal_factorial_effects.png"),
        *((name, "data/public_sae_consciousness_gating/confirmatory_v1_20260710/figures/"+name)
          for name in ("aggregate_target_and_controls.pdf", "judge_sensitivity.pdf", "technical_dose_and_matching.pdf")),
    ):
        blob = v.git_blob(args.source_repo, source_path)
        figures.append({"path": "paper/figures/"+name, "source_path": source_path, "source_commit": v.PIN, "sha256": v.sha256(blob),
                        "source_url": f"{v.SOURCE_URL}/blob/{v.PIN}/{source_path}"})
    ledger = {"schema_version": 1, "source_commit": v.PIN, "document": "paper/main.tex", "binding_count": len(bindings),
              "scope": "Explicit headline excerpts only, not all manuscript numbers or all figure statistics. Whitespace changes allowed; numeric/context drift fails. Figure bytes checked, not independently replotted.",
              "numbers": bindings, "figures": figures}
    (ROOT / "evidence/manuscript_bindings.json").write_bytes(v.json_bytes(ledger))
    manifest_path = ROOT / "evidence/provenance.json"
    manifest = v.json_load(manifest_path.read_bytes())
    manifest["manuscript_bindings_sha256"] = v.sha256(v.json_bytes(ledger))
    manifest_path.write_bytes(v.json_bytes(manifest))
    print(v.verify(ROOT, args.source_repo))


if __name__ == "__main__":
    main()
