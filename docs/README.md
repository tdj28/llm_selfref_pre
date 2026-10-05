# Research Guide

Start with the [paper](../paper/README.md) for the argument and
[reproduction guide](REPRODUCTION.md) for commands. This index connects study
questions to their protocols and results; it does not replace those records.
The [data index](../data/README.md), [code index](../experiments/README.md), and
[test index](../tests/README.md) follow the same study groups.

## Core Causal And Measurement Studies

| Question | Status | Protocol and results | Data |
|---|---|---|---|
| Do instructions, transcript source, register, and query wording change reports? | Complete; automated judgments, human coding not conducted. | [Protocol](CONFIRMATORY_PROTOCOL.md); [results](../data/causal_transplant/confirmatory_v1_20260709/README.md) | [Causal study](../data/causal_transplant/README.md) |
| Do scoring rubrics distinguish assertions from attributed or hypothetical claims? | Completed automated rubric audit. | [Protocol](AUTOMATED_RUBRIC_AUDIT_PROTOCOL_20260929.md); [results](AUTOMATED_RUBRIC_AUDIT_RESULTS_20260929.md) | [Rubric audit](../data/automated_rubric_audit/README.md) |
| How do instruction and transcript contrasts vary across English and Chinese in Llama? | Completed bilingual pilot; earlier fixture failure and budget stop retained. | [Final protocol](BILINGUAL_LLAMA_B1_PROTOCOL_20261002.md); [results](BILINGUAL_LLAMA_B1_RESULTS_20261002.md) | [Llama bilingual](../data/bilingual_llama_b1/README.md) |
| How do the bilingual contrasts vary across API models? | Completed frontier mini; separate from the Llama panel. | [Protocol](FRONTIER_BILINGUAL_B1_PROTOCOL_20261002.md); [results](FRONTIER_BILINGUAL_RESULTS_20261002.md) | [Frontier bilingual](../data/frontier_bilingual_b1/README.md) |
| Does crossed Llama behavior qualify a later internal-state intervention? | Qualification failed; later intervention not run. | [Protocol](INSTRUCTION_STATE_QUALIFICATION_PROTOCOL_20261001.md); [results](INSTRUCTION_STATE_QUALIFICATION_RESULTS_20261001.md) | [Qualification](../data/instruction_state_qualification/README.md) |

The [human-instrument proposal](HUMAN_INSTRUMENT_VALIDATION_AMENDMENT_20260929.md)
is a proposal, not completed coding. The separate Qwen repository is covered
by a [local evidence review](SELFREF_SCALING_EVIDENCE_REVIEW_20261003.md), not a
second copy of its data here.

## Public Steering

| Question | Status | Protocol and results | Data |
|---|---|---|---|
| Which public SAE coordinates match the claimed feature descriptions? | Completed mapping and construct checks; invalid earlier extension retained. | [Mapping guide](../experiments/exp2_sae/PUBLIC_SAE_FEATURE_MAPPING.md); [extension plan](analysis_plans/sae_construct_validity_extension_v1.md) | [Feature maps](../data/public_sae_feature_maps/README.md) |
| Does public Llama steering change report labels relative to matched controls? | Completed earlier NF4 grid; delivery limitations remain part of its interpretation. | [Protocol](SAE_CONSCIOUSNESS_GATING_PROTOCOL.md); [analysis note](SAE_CONSCIOUSNESS_GATING_ANALYSIS_NOTE_20260710.md) | [Primary grid](../data/public_sae_consciousness_gating/README.md); [specificity and pilots](../data/public_sae_placebo_steering/README.md) |
| Does the intervention transfer to Gemma Scope? | Completed direct-IT study; PT-to-IT transfer failed, atlas exploratory. | [Protocol](GEMMA_SCOPE_9B_PROTOCOL.md); [results](GEMMA_SCOPE_9B_RESULTS.md) | [Gemma](../data/gemma_scope_9b/README.md) |
| Does native-BF16 additive steering reproduce source dose curves and fixed aggregates? | Completed source-aligned public implementation comparison. | [Protocol](BERG_SOURCE_REPLICATION_PROTOCOL_20260930.md); [results](../data/berg_source_replication/source_aligned_v1_20261001/README.md) | [Source alignment](../data/berg_source_replication/README.md) |
| Does the paper's random-subset aggregate signature appear under the public operator? | Completed random-subset study; distinct from fixed-six aggregates. | [Protocol](BERG_ENSEMBLE_PROTOCOL_20261001.md); [results](../data/berg_ensemble_replication/random_subset_v1_20261001/README.md) | [Random subsets](../data/berg_ensemble_replication/README.md) |
| Can tested public operator settings match saved notebook signatures? | Main grid and fine ladder complete; no qualifying match. | [Main protocol](OPERATOR_MATCHING_PROTOCOL_20261002.md), [results](OPERATOR_MATCHING_RESULTS_20261003.md); [fine protocol](OPERATOR_MATCHING_FINE_LADDER_20261003.md), [results](OPERATOR_MATCHING_FINE_LADDER_RESULTS_20261003.md) | [Operator comparisons](../data/operator_matching/README.md) |
| Does a calibrated edit support a fidelity experiment? | Calibration and fresh repair complete; qualification failed, held-out study not run. | [Calibration protocol](STEERING_FIDELITY_PROTOCOL_20261002.md), [results](STEERING_FIDELITY_CALIBRATION_RESULTS_20261002.md); [repair protocol](STEERING_FIDELITY_REPAIR_PROTOCOL_20261003.md), [results](STEERING_FIDELITY_REPAIR_RESULTS_20261003.md) | [Calibration](../data/steering_fidelity/README.md); [repair](../data/steering_fidelity_repair/README.md) |

## Internal Readouts

| Question | Status | Start here |
|---|---|---|
| What do SAE-to-logit readouts add beyond controls? | J-lens v1 complete; v2 failed its replay criterion, later endpoint analyses exploratory. | [v1 protocol](LLAMA70B_SAE_JLENS_PROTOCOL.md), [results](LLAMA70B_SAE_JLENS_RESULTS.md); [v2 protocol](LLAMA70B_SAE_JLENS_V2_PROTOCOL.md), [results](LLAMA70B_SAE_JLENS_V2_RESULTS.md); [data](../data/sae_jlens_audit/README.md) |
| How do delivered edits change same-prefix readouts? | Completed descriptive analysis, not a mediation test. | [Secondary diagnostics](BERG_SOURCE_SECONDARY_DIAGNOSTICS_20260930.md); [source release](../data/berg_source_replication/README.md) |
| Does the readout instrument satisfy its transport controls? | Completed pilot; overall qualification failed. | [Protocol](consciousness_readout_validation/PROTOCOL.md); [results and data](../data/consciousness_readout_validation/pilot_v1_result_20260714_r15/README.md) |

## Historical Engineering And Unrun Designs

| Work | Status and route |
|---|---|
| SAE assay, coordinate repair, native replay, exposure and precision | Completed diagnostics with failed overall qualification. Follow [assay](SAE_ASSAY_STAGE1_RESULTS_20260930.md), [repair](SAE_ASSAY_REPAIR_RESULTS_20260930.md), [replay](SAE_ASSAY_REPLAY_RESULTS_20260930.md), and [exposure](SAE_ASSAY_EXPOSURE_RESULTS_20260930.md) results for their separate protocols and releases. |
| Changepoint, realization, target-blind calibration and signed-dose studies | Failed controls or engineering-only outcomes. The [historical inventory](STUDY_INVENTORY.md) resolves stale execution wording and links recovery records. |
| Neutral-task causal report study | [Implemented draft](JLENS_CAUSAL_REPORT_PROTOCOL_20261001.md), superseded by the [query-blind proposal](QUERY_BLIND_INSTRUCTION_STATE_REVIEW_20261001.md); no completed causal-stage result. |
| Held-out steering-fidelity study | [Archived design notes](../provenance/planning/STEERING_FIDELITY_TEST_DESIGN_NOTES_20261002.md) and [code](../experiments/steering_fidelity_test/); not run after failed qualification. |
| SAE switch-arc | [Unexecuted design draft](consciousness_sae_switch_arc/README.md); no target outcomes. |

## Cross-Study References

- [Claim ledger](CLAIM_LEDGER.md): supported claims and their limits.
- [Factor inventory](FACTOR_INVENTORY.md): differences among experimental settings.
- [Analysis chronology](ANALYSIS_CHRONOLOGY.md): timing and post-outcome changes.
- [Figure-value audit](FIGURE_VALUE_AUDIT.md) and [uncertainty sensitivity](UNCERTAINTY_SENSITIVITY.md): manuscript checks.
- [Artifact inventory](../DATA_ARTIFACTS.md) and [NOTICE](../NOTICE.md): availability and rights scope.

Obsolete, unfrozen roadmaps, handoffs and process notes are separated in the
[planning archive and relocation map](../provenance/planning/README.md).
Historical snapshots retain their original references; the map resolves moved
paths without rewriting those records. Bound protocols, amendments and release
paths remain in place because plans, tests and manifests depend on them.
