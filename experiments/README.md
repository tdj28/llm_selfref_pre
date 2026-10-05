# Experiment Code

Find a study's implementation here; read its protocol before interpreting an
entry point. A runner or passing test is not evidence that collection ran.
Use the [research guide](../docs/README.md) for protocols and results, the
[data index](../data/README.md) for releases, and the
[reproduction guide](../docs/REPRODUCTION.md) for saved-data commands.
Collection and lifecycle commands are not required for reproduction.

## Core Causal And Measurement Studies

| Question / status | Implementation | Representative tests |
|---|---|---|
| Instruction, transcript, register and query effects; complete | [Causal transplant](causal_transplant/README.md) | [Design and analysis](../tests/test_causal_transplant.py) |
| Automated rubric behavior; complete | [Rubric audit](automated_rubric_audit/) | [Analysis](../tests/test_automated_rubric_analysis.py), [runtime](../tests/test_automated_rubric_runtime.py) |
| Bilingual Llama contrasts; complete | [Final panel](bilingual_llama_b1/); [base runtime](bilingual_llama_pilot/); [instrument amendment](bilingual_llama_a1/); [technical retry](bilingual_pod_retry_b1/) | [Analysis](../tests/test_bilingual_analysis.py), [release integration](../tests/test_bilingual_release_integration.py) |
| Frontier bilingual contrasts; complete | [Final panel](frontier_bilingual_b1/); [base runtime](frontier_bilingual_mini/) | [Inventory](../tests/test_frontier_mini.py), [release](../tests/test_frontier_release_b1.py) |
| Crossed Llama qualification; failed, causal follow-up not run | [Qualification](instruction_state_qualification/); [startup adapter](instruction_qualification_bootstrap_a1/) | [Protocol](../tests/test_instruction_state_protocol.py), [release](../tests/test_instruction_qualification_release.py) |
| Kolibri instruction/continuation panel; complete | [Study protocol and runtime](kolibri_swap/README.md); [saved-data exporter](kolibri_release.py) | [Analysis](../tests/test_kolibri_swap_analysis.py), [release](../tests/test_kolibri_release.py), [paper binding](../tests/test_kolibri_extension.py) |

## Public Steering

| Question / status | Implementation | Representative tests |
|---|---|---|
| Feature maps, earlier NF4 Llama grid, specificity and Gemma; completed with distinct limitations | [Experiment 2 guide](exp2_sae/README.md) | [Llama grid](../tests/test_public_sae_consciousness_gating.py), [Gemma](../tests/test_gemma_scope_9b.py), [mapping templates](../tests/test_public_sae_mapping_template_robustness.py) |
| Native-BF16 source-aligned dose curves and fixed aggregates; complete | [Source replication](berg_source_replication/) | [Runtime](../tests/test_berg_source_replication.py), [reproduction](../tests/test_reproduce_berg_source.py) |
| Paper-distribution random subsets; complete | [Ensemble replication](berg_ensemble_replication/) | [Design](../tests/test_berg_ensemble_replication.py), [reporting portability](../tests/test_berg_ensemble_reporting_portability.py) |
| Public operator comparison; main grid and fine ladder complete, no qualifying match | [Main grid](operator_matching/); [fine ladder](operator_matching_fine/) | [Main](../tests/test_operator_matching.py), [fine](../tests/test_operator_matching_fine.py) |
| Steering-fidelity qualification; calibration and repair complete, qualification failed | [Calibration](steering_fidelity/); [fresh repair](steering_fidelity_repair/) | [Calibration analysis](../tests/test_steering_fidelity_analysis.py), [repair audit](../tests/test_fidelity_repair_audit.py), [position observer](../tests/test_fidelity_position_probe.py) |
| Held-out fidelity and opposing claims; not run | [Held-out implementation](steering_fidelity_test/) | [Inventory](../tests/test_fidelity_heldout_inventory.py), [analysis](../tests/test_fidelity_heldout_analysis.py) |

## Internal Readouts

| Work / status | Implementation | Representative tests |
|---|---|---|
| J-lens v1 and v2; v2 replay failed, later endpoints exploratory | [Readout analysis](exp2_sae/analyze_sae_jlens_audit.py), [v2 results](../docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md) | [v1](../tests/test_sae_jlens_audit.py), [v2](../tests/test_sae_jlens_v2.py) |
| Instrument transport; completed failed pilot | [Readout validation](consciousness_readout_validation/) | [Readout tests](../tests/consciousness_readout_validation/) |
| Neutral-task causal intervention; superseded implemented draft, not a completed experiment | [Causal report draft](jlens_causal_report/), [design](../docs/JLENS_CAUSAL_REPORT_PROTOCOL_20261001.md) | [Protocol](../tests/test_jlens_causal_protocol.py), [operators](../tests/test_jlens_causal_operators.py) |

## Historical Engineering

| Work | Implementation and tests |
|---|---|
| Assay diagnosis, coordinate repair, native replay, exposure and precision | [Diagnostic](sae_assay_diagnostic/), [repair](sae_assay_repair/), [replay](sae_assay_replay/), [exposure](sae_assay_exposure/), [precision](sae_assay_precision/); [repair tests](../tests/test_sae_assay_repair_protocol.py), [replay tests](../tests/test_sae_assay_replay_protocol.py), [exposure tests](../tests/test_sae_assay_exposure_protocol.py). |
| Changepoint and realization controls | [Changepoint](consciousness_sae_changepoint/), [realization](consciousness_sae_realization_validation/); [changepoint tests](../tests/consciousness_sae_changepoint/), [realization tests](../tests/consciousness_sae_realization_validation/). |
| Generic-direction calibration and dose scans | [Target-blind calibration](consciousness_sae_target_blind_calibration/), [signed-dose scan](consciousness_sae_signed_dose_scan/); [calibration tests](../tests/consciousness_sae_target_blind_calibration/), [scan tests](../tests/consciousness_sae_signed_dose_scan/). |

Consult the [historical inventory](../docs/STUDY_INVENTORY.md) for execution
status, failed controls and raw-data availability in the older engineering
families. Earlier prototypes in [elicitation](exp1_elicitation/) and
[Experiment 2](exp2_sae/README.md) remain distinct from the completed studies.
Source-bound modules and historical paths must stay unchanged during
navigation work; corrections belong outside the original runtime.
