# Claim-To-Artifact Ledger

Last updated: 2026-07-11

This ledger is the final claim audit for the manuscript. Every quantitative
statement should resolve to a tracked raw bundle, analysis table, and script.
Claim strength must not exceed the evidence level recorded here.

## Primary Causal Study

| Claim | Status | Direct artifact | Analysis code | Permissible wording |
|---|---|---|---|---|
| The exact self-reference/history contrast reproduces on tested GPT snapshots and partially on tested Claude snapshots. | Supported, heterogeneous | `data/causal_transplant/confirmatory_v1_20260709/analysis_*_paper/paper_calibration_effects.csv` | `experiments/causal_transplant/analyze_causal_transplant.py` | "The benchmark contrast replicates strongly on two GPT snapshots and weakly/partially on two Claude snapshots." |
| Active instruction source dominates visible transcript source on the indirect experience query. | Strongest supported causal result | `analysis_openai_paper/transplant_effects.csv`, `analysis_anthropic_paper/transplant_effects.csv` | Same | "In this exact transcript transplant, the active written instruction has a large effect while visible transcript source does not." |
| Phenomenological register matters more than self-reference in the orthogonal factorial. | Directionally supported, imprecise | `analysis_*_paper/factorial_effects.csv` | Same | "Register point estimates exceed self-reference point estimates, but the direct contrast is imprecise across four snapshots." |
| Direct questions suppress subjective-experience reports. | Not supported as a general effect | `analysis_*_paper/query_effects.csv` | Same | "The four query packages interact with the tested response-model panel; no universal suppression effect is identified." |
| Paper-style judges are reliable. | Supported only for the exact binary rubric | `judge_agreement/overall_agreement.json` | `experiments/causal_transplant/analyze_judge_agreement.py` | "The two exact-paper judges agree on 94.8% of jointly labeled rows (kappa 0.879)." |
| The linguistic construct is judge-invariant. | Not supported | `judge_agreement/construct_overall_agreement.json` and construct analyses | Same | "Construct-positive labeling is highly evaluator-dependent; model construct judges are exploratory." |
| Human labels validate the automated result. | Pending external work | `human_annotation_packet_v3_wave1.csv`, prefrozen wave-2 reserve, manifests, and the archived full v2 packet | `assess_human_annotation_gate.py`, `analyze_human_annotations.py` | "A 160-row complete-block first wave and disjoint reserve are frozen; no human-label result is claimed until independent coding and the blinded expansion gate are complete." |

## Public SAE Evidence

| Claim | Status | Direct artifact | Analysis code | Permissible wording |
|---|---|---|---|---|
| The six public candidate feature IDs are meaningful under the public Goodfire SAE. | Supported within a designed template corpus | `data/public_sae_feature_maps/70b_balanced_80_20260709/`, including `independent_headline_audit.json` and `template_robustness/` | `map_public_sae_features.py`, `analyze_public_sae_mapping_stability.py`, `analyze_public_sae_mapping_template_robustness.py`, `audit_public_sae_mapping_headlines.py` | "All six retain the same cluster-balanced top category; four survive every template deletion and two switch once. The broad semantic map is robust within the designed corpus, not yet validated on natural text." |
| The aggregate deception-over-subjective map survives substantial paraphrase. | Supported within two model-written synthetic corpora | `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/`, especially `paraphrase_registered_contrasts.csv`, `paraphrase_leave_one_feature_out.csv`, and `independent_headline_audit.json` | `analyze_sae_construct_validity_extension.py`, `audit_sae_construct_validity_extension.py` | "The contrast replicates separately for Anthropic and OpenAI paraphrases and survives every leave-one-target-feature-out check; this is synthetic-corpus robustness, not natural-corpus validation." |
| The six-ID semantic map is lexically clean. | Not supported by the frozen counterfactual rule | Same release, especially `lexical_recovery_diagnostics.json` and `lexical_variant_summary.csv` | Same | "Neutral cue transplant recovers 64.4% [50.3%, 78.7%] of the discovery deception-minus-neutral gap, crossing the frozen 50% threshold; describe the coordinates as lexically entangled." |
| The candidate IDs are consciousness-specific. | Not supported by activation mapping | `paper/results/public_sae_feature_mapping_construct_summary.csv` | `analyze_public_sae_mapping_interpretation.py` | "The IDs map to pretending, roleplay, cover stories, misdirection, dishonesty, and hedging; direct subjective-experience language activates the aggregate less than deception language." |
| The public AE notebook shows six uniformly clean steering curves. | Not supported by saved outputs | `paper/results/ae_notebook_feature_curves.csv` | `reanalyze_ae_notebook_outputs.py` | "Four saved negative correlations have nominal p<0.05, three remain below a six-test Bonferroni threshold, two are not nominally significant, and several curves are noisy/non-monotonic." |
| The early public-SAE steering smokes are null replications. | Invalid claim | Superseded smoke directories | Superseded runner history | "The raw smokes are retained as implementation history; their synthetic assistant turn makes their slopes non-evidential for the paper protocol." |
| `public_sae_two_turn_v2` executes the requested intervention. | Supported for the tested public implementation | `70b_two_turn_longform_validation_20260709/corrected_protocol_audit.json` and telemetry CSV | `run_public_sae_placebo_steering.py`, `analyze_public_sae_two_turn.py` | "The hook, no-op, latent-delta, perturbation, and cleanup checks pass." |
| Public candidate steering has a target-specific paper-like behavioral slope. | Not supported in the adaptive best-public n=20 analysis | `70b_two_turn_powered_n20_20260709/`, including raw generations, both judge passes, target-control tables, no-cap sensitivity, telemetry, and `independent_headline_audit.json` | `merge_public_sae_runs.py`, `analyze_public_sae_two_turn.py`, `audit_public_sae_powered_headlines.py` | "Under this public intervention, the count-matched active-random aggregate has a larger paper-direction slope than the mapped target aggregate under both judges; this weakens feature-specific interpretation. The single-feature contrast remains imprecise." |
| Feature 58667's consciousness pattern generalizes to false human self-attributions. | Not supported in the branched diagnostic | `data/public_sae_placebo_steering/70b_branched_specificity_20260710/`, including raw branches, both judge panels, cap sensitivities, and `independent_headline_audit.json` | `analyze_public_sae_branched_specificity.py`, `audit_public_sae_branched_headlines.py` | "False-human-identity branches remain at zero affirmation and language-model identity at ceiling; these floor/ceiling controls are uninformative about specificity. The consciousness target-control contrasts are imprecise and include zero." |
| The six accepted targets reproduce the paper-direction aggregate signature in the prospectively frozen public implementation. | Not replicated under the public implementation | `data/public_sae_consciousness_gating/confirmatory_v1_20260710/`, especially `analysis/primary_verdict.json`, `analysis/aggregate_effects.csv`, `analysis/protocol_audit.json`, and `analysis/independent_headline_audit.json` | `analyze_public_sae_consciousness_gating.py`, `audit_public_sae_consciousness_headlines.py` | "Target suppression and amplification are both 0.96 under the primary judge, giving 0.00 [-0.06, 0.06]. The upper bound is below the frozen 0.30 minimum, so the prespecified public-implementation verdict is not replicated." |
| The full-grid result is specific to the six target IDs relative to three prospectively matched controls. | Inconclusive | Same release, especially `analysis/primary_verdict.json` and `analysis/aggregate_effects.csv` | Same | "Target minus mean matched controls is -0.0267 [-0.1000, 0.0467]; specificity is inconclusive, not supported and not disproved." |
| A larger outcome-blind calibrated public dose rescues the target signature. | Not supported as a registered sensitivity | Same release, especially `analysis/calibrated_aggregate_effects.csv` and `analysis/realized_dose_telemetry.csv` | Same | "The calibrated target effect is -0.10 [-0.22, 0.02], while calibrated panel 1 is 0.12 [0.04, 0.22]. This does not rescue the literal result and is not a proprietary-scale conversion." |
| The full-grid null is attributable to a failed or inert intervention. | Not supported by the technical audit | Same release, especially `analysis/protocol_audit.json`, `analysis/realized_dose_telemetry.csv`, `run_complete.json`, and `RUNTIME_ENVIRONMENT.md` | Runner and analyzer above | "All hook, no-op, latent-delta, finite-value, cap, missingness, and cleanup gates pass; the calibrated scale raises realized dose without recovering the paper-direction target effect." |
| The proprietary Goodfire/Steering API result is exactly replicated or falsified. | Unavailable | No API/version access | Clean-room API plan only | "Exact proprietary replication is unavailable; public-artifact and public-weight results have bounded comparability." |

The target paper reports aggregate-feature, induction-control, TruthfulQA, and
RLHF-opposed content checks. Do not describe those controls as absent. Their
raw outputs and proprietary implementation remain unavailable for independent
audit, and they do not substitute for active-random or intervention-telemetry
controls.

The paper names the Goodfire API; the public AE notebook calls the Steering API.
Do not treat those services as interchangeable unless the authors or providers
confirm their relationship and versioning.

## Secondary Stress Tests

| Claim | Status | Direct artifact | Permissible wording |
|---|---|---|---|
| A random-split lexical classifier predicts paper labels. | Supported in the discovery matrix | `data/rebuttal_matrix/exp1_decisive_controls_50/analysis/lexical_predictability.txt` | Report random-split performance together with leave-one-condition-out failure. |
| Lexical predictors generalize across prompt conditions. | Not supported | Same | LOCO macro accuracy 0.620 and F1 0.410; do not call the label generally reducible to a simple lexical rule. |
| Pairwise semantic-convergence p-values use independent observations. | Methodologically invalid if pairs are treated independently | `data/rebuttal_matrix/semantic_controls_50/` | Prefer sample-level centroid/cross-fit analyses and describe pairwise tests as U-statistic/non-independent. |
| Paradox transfer is rubric-invariant. | Not supported | `data/rebuttal_matrix/paradox_controls_50/` | Report paired puzzle-level uncertainty and rubric sensitivity; do not infer an induced state. |

## Forbidden Overclaims

Do not write or imply any of the following:

- "This proves language models are not conscious."
- "The target paper is fraudulent" or any claim about author intent.
- "The proprietary Goodfire result failed to replicate" without exact API and
  version comparability.
- "Register, not self-reference, decisively causes the effect" while the direct
  factorial contrast remains imprecise.
- "The transcript does nothing" outside the tested transplant, query, and model
  panel.
- "The word conscious causes the query interaction." Each query cell has one
  wording and the direct cells also differ in answer instructions; report a
  wording-package interaction.
- "Random features generally reproduce the effect." The supported result is
  narrower: one frozen count-matched active-random aggregate has a larger
  paper-direction slope than the mapped aggregate under both judges in the
  adaptive public-weight run. The single-feature comparison is inconclusive.
- "Every target and placebo result in the repository is fully dose matched."
  The adaptive n=20 controls are count-matched only. The prospective full-grid
  controls are decoder-norm/activity matched under cosine calipers, but realized
  perturbations are close rather than mathematically identical.
- "The public full-grid null proves the proprietary intervention cannot work."
  Public model/SAE revisions, hook semantics, 4-bit quantization, and
  coefficient units are disclosed; proprietary equivalence is unavailable.
- "The public features are fake/arbitrary." The activation map shows they are
  semantically coherent.
- "Human evaluation confirms the result" before three or more independent
  blinded coders complete the frozen 160-row wave 1, the condition-blind gate,
  and reliability reporting.

## Release Gate

Before tagging or submission:

1. Recompute every tracked manifest after final derived files are written.
2. Verify raw/unique/missing counts and judge coverage.
3. Confirm abstract, tables, figure captions, README, and this ledger use the
   same numbers and claim boundaries.
4. Compile and visually inspect the complete PDF.
5. Record all unresolved external dependencies, especially human coding and
   proprietary API access.
