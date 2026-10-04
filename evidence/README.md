# Manuscript Evidence

This directory maps selected released measurements to manuscript tables,
figures and displayed values. It is a compact evidence package, not a second
raw-data archive. Start with the [paper](../paper/README.md), use the
[study data index](../data/README.md) for complete releases, and follow the
[research guide](../docs/README.md) for protocols and interpretation.

## Packages And Checks

| Material | Binding / provenance | Read-only check |
|---|---|---|
| Headline inputs and summaries | [Inputs](inputs/), [headlines](headlines.json), [provenance](provenance.json), [manuscript bindings](manuscript_bindings.json) | [verify_evidence.py](../scripts/verify_evidence.py) |
| Historical figure values | [Value inventory](figure_values.json), [audit description](../docs/FIGURE_VALUE_AUDIT.md) | [verify_figure_values.py](../scripts/verify_figure_values.py) |
| Automated rubric comparison | [Rubric package](automated_rubric_audit/) | [verify_rubric_audit.py](../scripts/verify_rubric_audit.py) |
| Native-BF16 source-aligned steering | [Source-alignment package](source_alignment/) | [verify_source_alignment.py](../scripts/verify_source_alignment.py) |
| Same-prefix J-lens comparison | [Table](source_jlens_table.tex), [diagnostic scope](../docs/BERG_SOURCE_SECONDARY_DIAGNOSTICS_20260930.md) | [verify_source_jlens_table.py](../scripts/verify_source_jlens_table.py) |
| Random-subset aggregate steering | [Ensemble package](ensemble_alignment/) | [verify_ensemble_alignment.py](../scripts/verify_ensemble_alignment.py) |
| Bilingual panels, crossed qualification and operator comparisons | [Completed extensions](completed_extensions/) | [verify_completed_extensions.py](../scripts/verify_completed_extensions.py); selected summary bindings, not raw-receipt or bootstrap reconstruction. |
| Uncertainty sensitivity | [Sensitivity package](uncertainty_sensitivity/), [methods](../docs/UNCERTAINTY_SENSITIVITY.md) | [uncertainty_sensitivity.py](../scripts/uncertainty_sensitivity.py) with `--check` |
| Conditional paired-binary reporting bound | [Display macro](reporting_checks/truthfulqa_bound.tex) | [verify_reporting_bound.py](../scripts/verify_reporting_bound.py); arithmetic under stated assumptions, not reconstruction of unobserved source scores. |

Steering-fidelity appendix checks read its
[calibration release](../data/steering_fidelity/README.md) directly through
[verify_fidelity_calibration.py](../scripts/verify_fidelity_calibration.py).
Full [bilingual](../data/bilingual_llama_b1/README.md),
[frontier](../data/frontier_bilingual_b1/README.md),
[operator-matching](../data/operator_matching/README.md), and
[fidelity-repair](../data/steering_fidelity_repair/README.md) records remain in
their study directories. Compact packages here do not replace those releases.

## Verify Or Regenerate?

From the repository root, `make paper-verify` runs the maintained checks
without replacing evidence. [Tests](../tests/README.md#publication-and-source-guards)
cover their failure behavior. These checks establish artifact/value agreement,
not the validity of every judgment or scientific interpretation.

The `build_*.py` files here generate packages or bindings and can overwrite
outputs. They are not verification commands. Changes to evidence require
review of the source measurements, generated values and manuscript bindings;
do not rebuild a package to hide a mismatch or move its inputs for tidiness.
