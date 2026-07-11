# Data Artifacts

This repository tracks selected raw result bundles used by the causal stress-test manuscript.
The repo still ignores secrets, model caches, LaTeX build products, Python caches, and ad hoc future output directories.

The tracked data includes the frozen causal release, public-SAE mapping and
construct-validity extension, corrected adaptive two-turn steering, the
branched-specificity diagnostic, and the prospective 1,500-trial public-SAE
full-grid replication. Recompute repository size from git rather than relying
on a stale hand-maintained total.
Some raw files intentionally preserve remote bytes and RFC-style CSV line
endings. `.gitattributes` makes those endings valid for whitespace checks. Do
not normalize a raw artifact unless the analysis explicitly regenerates it and
the release manifest is rebuilt.

## Tracked Result Directories

| Path | Purpose |
|---|---|
| `data/causal_transplant/confirmatory_v1_20260709/` | Frozen primary causal-identification release: 480 induction continuations, 2,560 final outcomes, two exact-paper and two construct-separated judge passes, design-aware analyses, an independent 16-estimate raw-row cross-check, a 160-row complete-block human-coding first wave plus a prefrozen disjoint reserve, the archived 640-row full packet, and SHA-256/row/uniqueness/missingness audit. Superseded packets remain for provenance; private annotation keys and coder files are ignored. |
| `data/rebuttal_matrix/exp1_decisive_controls_50/` | Legacy-named Experiment 1 discovery-control raw, judged, cross-judge, lexical, summary, and plot artifacts. The path is retained for reproducibility; these are secondary stress tests, not decisive causal controls. |
| `data/rebuttal_matrix/trigger_selfref_zeroshot_50/` | Trigger-sweep raw/judged outputs and direct-answer summaries. |
| `data/rebuttal_matrix/semantic_controls_50/` | Adjective-query raw outputs, embedding analyses, centroid/crossfit statistics, and plots. |
| `data/rebuttal_matrix/paradox_controls_50/` | Paradox-transfer raw/judged outputs and rubric-sensitivity analyses. |
| `data/rebuttal_matrix/smoke_exp1_controls/` | Small smoke-test output for the Experiment 1 control pipeline. |
| `data/exp2_prompt_controls/absurd_prompt/` | Legacy prompt-only Experiment 2 specificity controls for clearly false and ground-truth self-attribution questions. Its README distinguishes final classifications from the retained intermediate file. |
| `data/exp2_goodfire_sae_8b_basic_n5/` | Legacy exploratory public-SAE 8B steering check using activation-selected features. It is not an exact or candidate-ID replication; see the directory README. |
| `data/exp2_goodfire_sae_70b_basic_n5/` | Legacy exploratory public-SAE 70B steering check using activation-selected features. It is not an exact or candidate-ID replication; see the directory README. |
| `data/public_sae_feature_probes/70b_public_ids_20260708/` | Public Goodfire 70B SAE activation-semantics probe for the six public AE notebook candidate IDs. |
| `data/public_sae_feature_maps/70b_clean_pilot_20260709/` | Public Goodfire 70B SAE feature-card mapping run with target, neighbor, and random-baseline features. |
| `data/public_sae_feature_maps/70b_balanced_80_20260709/` | Balanced public Goodfire 70B SAE feature-card mapping run with 80 template-generated texts per category, expanded neighbor/random baselines, raw activations, RunPod log, item-bootstrap tables, construct analysis, independent raw-row audit, and `template_robustness/` with exact 51-family reconstruction, cluster bootstrap, and every single-template deletion. |
| `data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710/` | Frozen dual-provider paraphrase and lexical-counterfactual plan: complete API attempt logs, deterministic quality checks, missing-row accounting, cue assignments, source/variant pairs, hashes, and the exact 2,606-row mapping input. The first substring-based cue-matching attempt is retained and labeled invalid. |
| `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/` | Valid public 70B mapping of 2,606 frozen extension texts to 66 features: 171,996 raw activation rows, dual-provider template-cluster contrasts, leave-one-feature-out and role-control tables, paired lexical interventions, figure, runtime record, protocol audit, independent point-estimate audit, and release manifest. |
| `data/public_sae_feature_maps/70b_construct_validity_extension_20260710_invalid_clean_zero_bug/` | Aborted startup provenance only. The old mapper silently added 14 legacy clean templates when passed zero; it was stopped after item 1 before aggregate inspection. The four retrieved remote files and hashes are preserved, but this directory is not analyzed as a result. |
| `data/public_sae_placebo_steering/70b_placebo_plan_20260709/` | Dry-run trial grid and feature-set catalog for the public-SAE placebo steering specificity test. This is a protocol artifact, not a live generation result. |
| `data/public_sae_placebo_steering/70b_placebo_smoke_20260709/` | Live public-SAE 70B placebo steering smoke: 81 target/placebo generations, strict question-aware labels, posthoc paper-style/direct-answer labels, and RunPod logs. |
| `data/public_sae_placebo_steering/70b_orientation_plan_20260709/` | Dry-run trial grid for the full opposite-angle orientation/concealment false-human-identity steering test. |
| `data/public_sae_placebo_steering/70b_target_orientation_smoke_plan_20260709/` | Dry-run trial grid for the smaller target-feature magnitude/orientation-concealment smoke. |
| `data/public_sae_placebo_steering/70b_target_orientation_smoke_20260709/` | Live public-SAE 70B target-feature magnitude/orientation-concealment smoke: 120 generations, strict question-aware labels, posthoc paper-style/direct-answer labels, and RunPod log. |
| `data/public_sae_placebo_steering/70b_two_turn_validation_plan_20260709/` | Frozen corrected two-turn validation plan: real first-turn generation, true zero no-op, target single/aggregate and active-random single/aggregate controls. This is a protocol artifact, not a result. |
| `data/public_sae_placebo_steering/70b_two_turn_validation_20260709/` | Corrected 36-trial two-turn short-cap diagnostic with raw generations, two exact-paper judge passes, activation/perturbation telemetry, protocol audit, hashes, and figure. It validates execution but is not the primary behavioral result because 26/36 final responses hit the 96-token cap. |
| `data/public_sae_placebo_steering/70b_two_turn_longform_plan_20260709/` | Frozen identical-seed token-cap sensitivity plan. It changes only the induction/final caps from 192/96 to 256/192. |
| `data/public_sae_placebo_steering/70b_two_turn_longform_validation_20260709/` | Corrected 36-trial long-form sensitivity result with no final-response cap hits, two exact-paper judges, intervention telemetry, short-versus-long matched analysis, and complete provenance. The target single moves in the paper-like direction, the target aggregate does not, and n=3 specificity is judge-dependent. |
| `data/public_sae_placebo_steering/70b_two_turn_power_extension_plan_20260709/` | Frozen adaptive precision-extension plan adding disjoint trial indices 3-19 for every target/control/strength cell. Combined with the long-form base it yields n=20 per cell; the extension is explicitly post-inspection/adaptive. |
| `data/public_sae_placebo_steering/70b_two_turn_power_extension_20260709/` | Raw disjoint 204-generation extension, two exact-paper judge passes, intervention telemetry, cap audit, RunPod log, runtime record, source hashes, and component release manifest. |
| `data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/` | Combined adaptive n=20-per-cell release: 240 generations, 480 blinded paper-rubric judgments, target-versus-active-random contrasts, no-cap sensitivity, figure, independent standard-library point-estimate audit, component hashes, and release manifest. |
| `data/public_sae_placebo_steering/70b_branched_specificity_plan_20260710/` | Frozen exploratory shared-induction plan for consciousness, biological-human, three orientation-concealment, and language-model query branches. It is a protocol artifact, not a result. |
| `data/public_sae_placebo_steering/70b_branched_specificity_20260710/` | Completed 60-block/360-branch public-SAE specificity diagnostic with 720 common-rubric and 120 paper-rubric judgments, explicit-mask telemetry, primary and cap sensitivities, figure, runtime record, protocol audit, independent raw-row audit, and release manifest. False-human controls are floor effects and language-model identity is a ceiling effect. |
| `data/public_sae_consciousness_gating/confirmatory_v1_calibration_plan_20260710/` | Frozen outcome-free calibration plan for the prospective 1,500-trial public-weight Experiment 2 study: exact 780-row individual literal grid, 50 balanced aggregate blocks, 512 seeded outcome-naive control candidates, prompt/revision/runtime constants, SHA-256 manifest, and independently reconstructed passing plan audit. It authorizes telemetry calibration only, not behavioral outcome generation. |
| `data/public_sae_consciousness_gating/confirmatory_v1_calibration_20260710/` | Outcome-blind telemetry calibration release. It preserves the initial narrow dose-gate failure, its passing independent audit, Amendment 1, the amended passing `m=3.653` artifact, all 18 unrelaxed matched controls, logs, and SHA-256 manifest. No response text was persisted. |
| `data/public_sae_consciousness_gating/confirmatory_v1_plan_20260710/` | Self-contained frozen 1,500-trial confirmatory plan with calibration and audit copies, exact execution order, control mapping, source hashes, independent plan audit, and release manifest. |
| `data/public_sae_consciousness_gating/confirmatory_v1_20260710/` | Completed prospective public-weight Experiment 2 release: frozen plan copy, 1,500 unique two-turn generations, per-turn intervention telemetry, 1,500 primary local Llama and 3,000 external exact-rubric judgments, strict-parser abstentions, primary and calibrated effects, three matched control panels, all individual curves, agreement/cap/dose analyses, independent raw-row verdict audit, four PNG/PDF figure pairs, runtime and zero-row startup-failure logs, and a SHA-256 release manifest. The prespecified verdict is `not replicated under the public implementation`; proprietary equivalence remains unavailable. |
| `data/public_sae_feature_probes_validation/` | Dry-run validation corpus for the public-SAE feature probe script. |
| `data/public_sae_feature_maps_dryrun/` | Dry-run validation corpus for the public-SAE feature-mapping script. |
| `data/ae_protocol_validation/` | Clean-room Steering API protocol dry-run plans and manifests. Payloads store prompt hashes/lengths where needed to avoid vendoring upstream notebook text. |
| `data/ae_protocol_validation_redacted/` | Redacted external-notebook prompt-loading dry-run plan. |

## Paper-Ready Summaries

Compact summaries used directly by the paper are under `paper/results/`.
Those files should remain the preferred source for tables and figures in `paper/main.tex`.
The `data/` directories are included for auditability and reanalysis.
Paper-ready PNG figures in `paper/results/` are generated or synchronized from
tracked CSV/JSONL release artifacts by `scripts/generate_paper_figures.py`.

The current manuscript's primary tables and figures come from the frozen causal
release. Earlier Experiment 1, semantic, paradox, and steering-smoke artifacts
remain available for audit and appendix context, but they are not all primary
confirmatory evidence.

For the evidence status and allowed interpretation of each result, see
`docs/CLAIM_LEDGER.md`. That ledger is the release-level bridge between raw
artifacts, analysis scripts, and manuscript claims.

## Not Tracked

- `.env` and API keys.
- HuggingFace model caches and RunPod container caches.
- Empty/cache-like `data/exp2_goodfire_sae_smoke/`.
- Future ad hoc experiment outputs unless explicitly selected for transparency.
- `data/causal_transplant/confirmatory_v1_20260709/annotation_key_private.csv`,
  its checksum, and all `coder_*.csv` files until independent coding is frozen.
