# Verification And Release Tools

Use [REPRODUCTION.md](../docs/REPRODUCTION.md) for environment setup and complete
commands. This directory contains both read-only checks and tools that create
or overwrite outputs. Analysis and release-building work belongs in a fresh
directory, not an existing release. Collection controllers are not needed to
verify saved results.

## Repository And Paper Checks

| Task | Tool | Tests / scope |
|---|---|---|
| Public file, secret and release-manifest checks | [audit_public_release.py](audit_public_release.py), via `make public-audit` | [Tests](../tests/test_public_release_audit.py); canonical whole-repository scanner. |
| Compile tracked Python without importing it | [check_python_sources.py](check_python_sources.py), via `make compile` | Syntax check, not experiment execution. |
| Check selected local documentation links | [check_documentation_links.py](check_documentation_links.py) | Its `DOCUMENTS` list defines coverage; no network requests. |
| Verify paper tables and figures | [verify_evidence.py](verify_evidence.py), [verify_figure_values.py](verify_figure_values.py) | [Evidence tests](../tests/test_verify_evidence.py), [figure tests](../tests/test_figure_values.py). |
| Verify rubric, source and ensemble sections | [verify_rubric_audit.py](verify_rubric_audit.py), [verify_source_alignment.py](verify_source_alignment.py), [verify_source_jlens_table.py](verify_source_jlens_table.py), [verify_ensemble_alignment.py](verify_ensemble_alignment.py) | [Evidence index](../evidence/README.md) maps each package to its checks. |
| Verify fidelity appendix and uncertainty summaries | [verify_fidelity_calibration.py](verify_fidelity_calibration.py), [uncertainty_sensitivity.py](uncertainty_sensitivity.py) | [Fidelity bindings](../tests/test_fidelity_paper_binding.py), [uncertainty tests](../tests/test_uncertainty_sensitivity.py); uncertainty verification uses `--check`. |
| Verify completed follow-up summaries and the conditional reporting bound | [verify_completed_extensions.py](verify_completed_extensions.py), [verify_reporting_bound.py](verify_reporting_bound.py) | [Extension tests](../tests/test_completed_extensions.py), [bound tests](../tests/test_reporting_bound.py); default checks are read-only, `--write` regenerates their compact outputs. |
| Recompute selected historical summaries on copies | [check_frozen_audits.py](check_frozen_audits.py) | `make audit` runs its extended checks, separately from the bounded paper verification. |

`make paper-verify` is the maintained read-only paper check sequence.
[audit_public_files.py](audit_public_files.py) is an imported, narrower tool,
not a substitute for the root public-release audit.

## Core Causal And Measurement Studies

| Study | Tools | Tests |
|---|---|---|
| Causal prompt/transcript study | [Historical summary checks](check_frozen_audits.py); [figure generation](generate_causal_figures.py) writes outputs. | [Study tests](../tests/test_causal_transplant.py) |
| Bilingual Llama | [Reproduction](reproduce_bilingual_b1.py) writes to a fresh destination; [arithmetic check](check_bilingual_b1_arithmetic.py) reads the release. | [Release integration](../tests/test_bilingual_release_integration.py) |
| Frontier bilingual | [Release verifier and reproducer](release_frontier_b1.py); use the documented `--verify` or `--reproduce` mode. | [Release tests](../tests/test_frontier_release_b1.py) |
| Instruction-state qualification | [Reproduction](reproduce_instruction_qualification.py); figure output is optional. | [Release tests](../tests/test_instruction_qualification_release.py) |

## Public Steering And Internal Readouts

| Study | Tools | Tests |
|---|---|---|
| Source-aligned additive steering | [Reproduction](reproduce_berg_source.py); [release builder](release_berg_source.py). | [Reproduction](../tests/test_reproduce_berg_source.py), [release](../tests/test_release_berg_source.py) |
| Random-subset and same-prefix readouts | [Ensemble verifier](verify_ensemble_alignment.py); [J-lens table verifier](verify_source_jlens_table.py). Full analyses live in [experiment code](../experiments/README.md). | [Ensemble](../tests/test_ensemble_alignment.py), [J-lens table](../tests/test_source_jlens_table.py) |
| Steering-fidelity calibration | [Release builder](release_steering_fidelity_calibration.py), [report generator](report_steering_fidelity_calibration.py), [offline instrument audit](audit_steering_fidelity_instrument.py). | [Release](../tests/test_fidelity_calibration_release.py), [instrument audit](../tests/test_fidelity_instrument_repair.py) |
| Fresh steering-fidelity repair | [Release builder](release_fidelity_repair.py), including inspect-without-copying mode. | [Release tests](../tests/test_release_fidelity_repair.py) |
| Operator matching | Analysis and release tooling are in the [main](../experiments/operator_matching/) and [fine-ladder](../experiments/operator_matching_fine/) packages. | [Main](../tests/test_operator_matching.py), [fine](../tests/test_operator_matching_fine.py) |

## Historical Engineering

| Task | Route |
|---|---|
| Assay residual schema and release checks | [Residual audit](audit_sae_residual_release.py); [tests](../tests/test_sae_residual_release_audit.py). |
| Exposure release and arithmetic | [Release audit](audit_sae_exposure_release.py), [arithmetic](check_sae_exposure_arithmetic.py), [release builder](release_sae_exposure.py); [tests](../tests/test_sae_exposure_release.py). |
| Separate Qwen evidence review | [External-release auditor](audit_selfref_scaling_release.py); [review scope](../docs/SELFREF_SCALING_EVIDENCE_REVIEW_20261003.md). Not required for ordinary local reproduction. |
| Historical bootstrap and retrieval adapters | [Startup adapter](steering_fidelity_bootstrap_a1.py), [retrieval adapter](steering_fidelity_cleanup_a2.py); operational history, not reanalysis commands. |

For source inventories and historical Git requirements, see
[tests/frozen_sources.py](../tests/frozen_sources.py) and the
[test guide](../tests/README.md). Do not weaken a source check to accommodate
an edited runtime or relocated release.
