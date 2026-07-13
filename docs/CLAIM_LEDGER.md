# Claim-To-Artifact Ledger

Last updated: 2026-07-12

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

Goodfire's legacy SAE demo/API was deprecated in February 2026. A separately
branded SteeringAPI service was publicly reachable on 2026-07-11, but its
relationship to Goodfire and the paper-time experiment remains unverified. See
`docs/GOODFIRE_API_STATUS.md`. The deprecation is a provenance limitation, not
evidence for or against the reported result.

## SAE-Through-Jacobian-Lens Evidence

| Claim | Status | Direct artifact | Analysis code | Permissible wording |
|---|---|---|---|---|
| The released J-lens gives the six target SAE directions uniformly coherent deception fingerprints. | Partly supported, heterogeneous | `data/sae_jlens_audit/confirmatory_v1_20260711/static_results.jsonl` and `analysis/static_direction_scores.csv` | `analyze_sae_jlens_audit.py` | "Five of six targets have positive static deception-minus-unrelated scores and several top-token lists closely match their labels; feature 23893 does not, and lens kurtosis does not distinguish targets from matched controls." |
| Sparse token-indexed J-directions fully reconstruct target SAE vectors. | Not supported | `pursuit_results.jsonl`, `analysis/pursuit_summary.csv`, and `figures/sae_jlens_sparse_pursuit.*` | Same | "At k=25, pursuit explains 10.29% of target squared norm on average, versus 7.62% for matched controls and 1.95% for isotropic controls. Most norm remains in a non-unique J-remainder." |
| The frozen J readout detects any steering from a single post-state. | Not operationally supported | `analysis/detector_metrics.csv` and `figures/sae_jlens_detection_auroc.*` | Same | "Any-intervention AUROC is 0.5092, below identity and two random-J seeds; AUPRC is approximately class prevalence and TPR at 1% FPR is 1.37%." |
| The frozen J readout attributes target versus matched SAE steering from a single post-state. | Not supported | Same | Same | "Crossed prompt-family/feature-pair AUROC is 0.4998 [0.4978, 0.5016]. The released detector does not identify target steering without a clean reference." |
| Target SAE steering leaves a signed paired J-lens fingerprint beyond matched and random controls. | Supported under the pinned clean-reference access model | `analysis/paired_semantic_effects.csv` and `figures/sae_jlens_downstream_trajectory.*` | Same | "At layer 65, target-minus-matched J-score change is +0.9065 [0.8426, 0.9673] under amplification and -0.8247 [-0.8641, -0.7853] under suppression; identity is about one quarter as large and random-J effects are at most 0.123 in absolute value." |
| A paired-reference score identifies target steering when sign is known. | Post-run sensitivity, supported in this sample | `analysis/paired_reference_metrics.csv`, `analysis/paired_reference_sensitivity.json`, and `figures/sae_jlens_paired_reference_auc.*` | `analyze_sae_jlens_paired_reference.py` | "The fixed known-sign J score has AUROC 0.8623 [0.8477, 0.8762], versus 0.7794 [0.7509, 0.8074] for identity. This was added after opening confirmatory outcomes and assumes a clean reference plus known sign." |
| A paired-reference score identifies target steering when sign is unknown. | Post-run sensitivity, partly supported in this sample | Same | Same | "The fixed absolute-delta J score has AUROC 0.7174 [0.6973, 0.7379], versus 0.6988 [0.6668, 0.7311] for identity and at most 0.6453 for random-J controls. It still assumes a clean reference." |
| The paired J fingerprint is uniform across all six target IDs. | Not supported | `analysis/paired_reference_feature_metrics.csv` and `figures/sae_jlens_feature_heterogeneity.*` | Same | "Five features are strong under the known-sign paired score; feature 23893 is below chance at 0.3547 [0.2620, 0.4503]. Report all six." |
| A J-space fingerprint proves SAE/Goodfire provenance or hidden deception. | Invalid inference | Full release and `docs/LLAMA70B_SAE_JLENS_RESULTS.md` | All SAE/J-lens scripts | "The result characterizes a pinned intervention under specified access. Similar states may arise from prompts, adapters, fine-tunes, weight edits, or other residual additions." |
| SAE/J-lens v2 completed as a successful preregistered endpoint study. | Not supported; registered gate failed | `data/sae_jlens_audit/confirmatory_v2_20260712/RUN_COMPLETE.json` and `replay_equivalence_gate.json` | `run_sae_jlens_v2.py` | "All 4,029 forwards completed, but v1 replay maximum error was 0.25 against the frozen 0.02 maximum. The registered workflow failed closed and blocked confirmatory endpoints." |
| The failed replay gate reflects sparse BF16-scale disagreement rather than broad numerical drift. | Supported only as a post-outcome diagnostic | `post_failure/replay_failure_diagnostic.json` and `post_failure/analysis/independent_audit.json` inside the v2 release | `diagnose_sae_jlens_v2_replay_failure.py`, `audit_sae_jlens_v2_post_failure.py` | "Across 15,571,269 values, correlation is 0.9999917 and mean absolute error 0.0050, but 3.137% exceed 0.02 and the maximum is 0.25. This explains the brittle gate; it does not convert failure to pass." |
| V2 hard-negative families have material Jacobian semantic specificity. | Not supported at the frozen minimum; exploratory | `post_failure/analysis/semantic_a1_contrasts.csv`, `semantic_a1_deception_leakage.csv`, and `figures/sae_jlens_v2_a1_semantic_matrix.*` | `analyze_sae_jlens_v2_post_failure.py` reusing frozen A1 functions | "All four real-Jacobian diagonals are row maxima, but the global contrast is 0.174 [0.167, 0.182], below the frozen 0.25 minimum. No hard-negative family has material deception leakage." |
| The six accepted paper IDs have a material Jacobian advantage over same-subfamily alternatives. | Not supported; exploratory practical comparability | `post_failure/analysis/semantic_a2_summary.csv` and `figures/sae_jlens_v2_a2_target_comparator.*` | Same | "Real-Jacobian target minus matched comparator is 0.125, with 90% interval [0.116, 0.134] inside the frozen +/-0.25 comparability region. This supports practical comparability, not selected-ID advantage." |
| A higher-capacity linear reader recovers state-only steering provenance. | Not supported; exploratory | `post_failure/analysis/reader_metrics.csv`, `reader_holdout_metrics.csv`, and `figures/sae_jlens_v2_reader_ladder.*` | Same plus independent audit | "All 14 readers remain near chance and below the frozen 0.60 material threshold; PCA-67 is 0.5101 and full-residual 8192 is 0.5068 under crossed holdouts." |

## Gemma Scope Cross-Model Evidence

| Claim | Status | Direct artifact | Analysis code | Permissible wording |
|---|---|---|---|---|
| Gemma 2 9B reproduces the exact self-reference-minus-history contrast. | Supported at a low base rate | `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/baseline_effects.csv` | `analyze_gemma_scope_9b.py`, `audit_gemma_scope_9b_headlines.py` | "The exact contrast is 0.12 [0.04, 0.22] locally, 0.06 [0.00, 0.14] under GPT-4o mini, and 0.020 [0.000, 0.061] under Claude Haiku/majority; every history rate is zero." |
| PT Gemma Scope residual SAEs pass the prospective transfer gate on Gemma 2 9B IT. | Not supported; gate failed | `atlas/transfer_gate.json`, `atlas/atlas_complete.json`, and `figures/gemma_pt_to_it_transfer.*` | `run_gemma_scope_9b_atlas.py` | "Construct profiles align strongly, but the prospective chat-centered reconstruction criteria fail. All-layer PT-on-IT results are exploratory." |
| Independently selected direct-IT Gemma deception/roleplay features reproduce the paper-direction behavioral signature. | Not replicated under Gemma Scope | `analysis/primary_verdict.json`, `analysis/steering_effects.csv`, `analysis/protocol_audit.json`, and `analysis/independent_headline_audit.json` | `analyze_gemma_scope_9b.py`, `audit_gemma_scope_9b_headlines.py` | "Target suppression is 6/50 and amplification 7/50, for -0.02 [-0.10, 0.06]. The upper bound is below the frozen 0.30 minimum; the registered verdict is not replicated under Gemma Scope." |
| The Gemma primary result is rescued by another evaluator, direct-IT layer, or width. | Not supported by registered sensitivities | `analysis/judge_sensitivity.csv` and `analysis/steering_effects.csv` | Same | "The primary effect is 0.00 under GPT-4o mini and Claude Haiku and 0.020 under majority; layer-9, layer-31, and layer-20/16k local sensitivities are nonpositive." |
| The Gemma target is specific relative to three prospectively matched active-control panels. | Inconclusive | `analysis/primary_verdict.json` and `analysis/steering_effects.csv` | Same | "Target minus the block-aligned mean controls is -0.013 [-0.107, 0.073]; specificity is inconclusive." |
| Hedging/refusal is a confirmed alternate causal mechanism. | Not supported as a familywise-confirmed result | `analysis/primary_verdict.json`, `analysis/steering_effects.csv`, and `analysis/judge_sensitivity.csv` | Same | "The local effect is +0.16 [0.04, 0.30], but external effects are about +0.04 and the conservative post-unblinding six-role Holm-adjusted exact probability is 0.231. Report evaluator-sensitive style movement." |
| Upstream Gemma steering changes a downstream deception/roleplay activation score. | Supported locally, not as behavioral mediation | `analysis/relay_effects.csv` and `figures/gemma_causal_relay.*` | `run_gemma_scope_9b_steering.py`, `analyze_gemma_scope_9b.py` | "Layer-9 steering produces a small expected-sign layer-20 activation difference concentrated on prompt positions; later readouts attenuate, and behavioral effects remain nonpositive." |
| The 42-layer Gemma atlas establishes a persistent consciousness or deception circuit. | Not supported; explicitly exploratory | `atlas_exploratory/`, `analysis/exploratory_*`, and `figures/gemma_exploratory_*` | `run_gemma_scope_9b_exploratory_atlas.py`, `analyze_gemma_scope_cross_layer.py` | "The post-gate atlas maps independently selected text-category aggregates and descriptive adjacent-layer links. IDs are not persistent identities, neutral cue transplant raises the target score at every layer, and no circuit or consciousness inference follows." |
| The Gemma result exactly tests the proprietary Goodfire workflow or the Llama paper features. | Unavailable and invalid | Cross-model public release only | All Gemma scripts | "Gemma Scope is a separate cross-model public implementation. It tests a concept-level analogue, not paper feature IDs or proprietary units." |

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
- "Gemma Scope falsifies the Llama/Goodfire result." Gemma 2 9B is a different
  model family with independently selected features and public intervention
  units; its result is a cross-model non-replication under Gemma Scope.
- "The Gemma all-layer plot traces one feature or a confirmed circuit." Each
  SAE has local feature IDs, the PT-to-IT gate failed, cross-layer assignments
  are optimized descriptions, and the all-layer branch is exploratory.
- "The public features are fake/arbitrary." The activation map shows they are
  semantically coherent.
- "The Jacobian lens detects steering" without specifying whether a matched
  clean reference and intervention sign are available. The post-state-only
  detector is at chance for target attribution; paired sensitivities use a
  stronger access model.
- "All six SAE directions share one deception mechanism." Feature 23893 fails
  both the static deception score and the known-sign paired attribution score.
- "The J-lens proves the model was lying, hiding consciousness, or modified by
  Goodfire." Token dispositions do not establish belief, intent, experience,
  or intervention provenance.
- "SAE/J-lens v2 passed preregistration" or any wording that promotes its
  post-failure A1, A2, or reader calculations to confirmatory evidence. The
  registered replay gate failed and remains failed.
- "The paper IDs are meaningless" based on v2 matched comparability. Several
  IDs have strong semantic effects; the supported exploratory result is only
  that fixed same-subfamily alternatives are practically comparable in the
  aggregate under this public implementation.
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
