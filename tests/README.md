# Test Guide

The suite checks code, artifact contracts and failure handling. Passing it
does not establish a scientific qualification result. Use the
[research guide](../docs/README.md) for study status and
[reproduction guide](../docs/REPRODUCTION.md) for Python and CPU dependencies.

From the repository root, `make test` collects the full suite. For a focused
check, pass explicit files, for example:

```sh
python -m pytest tests/test_causal_transplant.py tests/test_rubric_audit.py
```

CPU tests require no model download or API credentials. CUDA-only fixtures
have separate device requirements; CPU success is not a CUDA qualification.

## Core Causal And Measurement Studies

| Study | Start with |
|---|---|
| Causal instruction/transcript study | [Design and analysis](test_causal_transplant.py) |
| Automated rubrics | [Runtime](test_automated_rubric_runtime.py), [analysis](test_automated_rubric_analysis.py), [paper binding](test_rubric_audit.py) |
| Bilingual Llama | [Protocol](test_bilingual_protocol.py), [raw audit](test_bilingual_raw_audit.py), [analysis](test_bilingual_analysis.py), [release integration](test_bilingual_release_integration.py) |
| Frontier bilingual | [Inventory](test_frontier_mini.py), [budget](test_frontier_budget_b1.py), [release](test_frontier_release_b1.py) |
| Instruction-state qualification | [Protocol](test_instruction_state_protocol.py), [runner](test_instruction_state_runner.py), [analysis](test_instruction_state_analysis.py), [release](test_instruction_qualification_release.py) |

## Public Steering

| Study | Start with |
|---|---|
| Earlier Llama grid and mapping | [Protocol](test_public_sae_protocol.py), [grid](test_public_sae_consciousness_gating.py), [two-turn analysis](test_public_sae_two_turn_analysis.py), [mapping templates](test_public_sae_mapping_template_robustness.py) |
| Gemma Scope | [Gemma tests](test_gemma_scope_9b.py) |
| Source-aligned native-BF16 steering | [Runtime](test_berg_source_replication.py), [diagnostics](test_berg_source_diagnostics.py), [reproduction](test_reproduce_berg_source.py) |
| Random-subset steering | [Design](test_berg_ensemble_replication.py), [figures](test_berg_ensemble_figures.py), [portability](test_berg_ensemble_reporting_portability.py) |
| Operator matching | [Main grid](test_operator_matching.py), [fine ladder](test_operator_matching_fine.py) |
| Steering-fidelity calibration | [Protocol](test_steering_fidelity_protocol.py), [backend](test_steering_fidelity_backend.py), [analysis](test_steering_fidelity_analysis.py), [release](test_fidelity_calibration_release.py) |
| Fresh fidelity repair | [Protocol](test_fidelity_repair_protocol.py), [pressure decision](test_fidelity_repair_pressure_gate.py), [audit](test_fidelity_repair_audit.py), [liveness](test_fidelity_repair_liveness.py), [position observer](test_fidelity_position_probe.py), [release](test_release_fidelity_repair.py) |
| Unrun held-out fidelity design | [Inventory](test_fidelity_heldout_inventory.py), [fixtures](test_fidelity_heldout_fixtures.py), [analysis](test_fidelity_heldout_analysis.py) |

## Internal Readouts And Historical Engineering

| Work | Start with |
|---|---|
| SAE J-lens | [v1](test_sae_jlens_audit.py), [v2](test_sae_jlens_v2.py), [source-aligned lens mathematics](test_berg_source_lens_math.py) |
| Readout validation | [Instrument tests](consciousness_readout_validation/) |
| Superseded causal-report implementation | [Protocol](test_jlens_causal_protocol.py), [operators](test_jlens_causal_operators.py); tests do not imply collection occurred. |
| Assay diagnosis and repair | [Assay protocol](test_sae_assay_protocol.py), [repair protocol](test_sae_assay_repair_protocol.py), [release](test_sae_assay_repair_release.py) |
| Native replay and exposure | [Replay](test_sae_assay_replay_protocol.py), [exposure](test_sae_assay_exposure_protocol.py), [precision](test_sae_assay_precision_pilot.py) |
| Earlier engineering families | [Changepoint](consciousness_sae_changepoint/), [realization](consciousness_sae_realization_validation/), [target-blind calibration](consciousness_sae_target_blind_calibration/), [signed-dose scan](consciousness_sae_signed_dose_scan/) |

## Publication And Source Guards

- [Public-release tests](test_public_release_audit.py) check exclusions, inventory and hashes.
- [Evidence](test_verify_evidence.py), [figures](test_figure_values.py), [source alignment](test_source_alignment.py), [ensemble](test_ensemble_alignment.py), [fidelity](test_fidelity_paper_binding.py) and [uncertainty](test_uncertainty_sensitivity.py) cover paper bindings.
- [Completed extensions](test_completed_extensions.py) and [reporting bound](test_reporting_bound.py) check follow-up summary bindings and conditional arithmetic without collecting outcomes.
- [Historical source helper](frozen_sources.py) requires regular files at their recorded paths and rejects scientific-source drift. Its two named historical infrastructure exceptions do not relax runtime gates.
- [CI](../.github/workflows/verify.yml) uses full Git history for historical fixtures. A shallow checkout or source ZIP can lack required historical blobs.

Keep historical failures and their regression fixtures. Do not regenerate a
plan, change expected scientific decisions, or relocate inputs merely to make
a test pass.
