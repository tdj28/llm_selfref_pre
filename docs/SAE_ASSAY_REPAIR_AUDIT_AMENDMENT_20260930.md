# Repair Release Audit: Row Ordering

Date: 2026-09-30. Post-outcome audit correction. All 3,897 GPU rows had been
collected and both newly owned pods deleted before this correction. The frozen
runtime, plan, scientific analysis and original auditor remain unchanged.

## Failure Preserved

The complete frozen audit returned exactly three errors:

```text
literal reanalysis differs
decoder_span reanalysis differs
encoder_min_norm reanalysis differs
```

It reported 3,897 receipt-backed rows, no unresolved dispatch, no other error,
and no selected recipe. The full failed report is retained in the release as
`analysis/frozen_audit.json`. It must not be described as a passing frozen audit.

## Cause And Bounded Correction

The runtime first collected a seven-text check batch under each recipe. When
forming calibration reports, it reused those saved rows in the original
planned order: clean rows, then strength, direction and plan-text order.
The auditor instead collected edited rows in receipt order. Its exact report
comparison therefore compared differently ordered per-row diagnostic lists:
`encoder_activity_parity` and `mask_reports`.

The separate `experiments/sae_assay_repair/release_audit.py` reconstructs the
runtime's logical order from frozen IDs. It requires exact agreement with
every saved calibration report, including corpus sensitivities, and checks
that chronological reports agree after permuting **only** those two diagnostic
lists. Scientific feature order, all numbers, sample sizes, thresholds,
decisions and every other list remain order-sensitive. There is no numerical
tolerance or blanket report canonicalization. Missing/extra rows or any other
original audit error block the corrected release check.

This is an additive post-outcome comparator fix, not a new protocol, a new
experiment, a relaxed scientific gate or an excuse to delete a failed audit.
The public reproduction command emits both the unchanged failed audit and the
separately identified corrected reconstruction. An additional independent
NumPy check covers coordinate arithmetic; it is not human validation.

The observed result remains: no recipe qualifies, and no steered validation
or subjective-experience-report branch is run. Whether the report-ordering
diagnosis fully accounts for the failure is verified by the exact comparisons
in `analysis/audit.json`; a successful process exit alone is insufficient.

## Verified Outcome

The corrected reconstruction passes all exact comparisons for all three
operators. A separate agent reconstruction localized 27 diagnostic-list
permutations: nine per operator, including the authored-corpus sensitivity.
Aligning entries to raw row IDs reproduces the saved reports exactly, without
changing a number or decision. The originally failed audit has SHA-256
`5e72c29ffc3036dbb1e7b51652ba0641a9949e2db9d50eccc05c94d240b2f6fd`.

The existing minimum-norm encoder-path disagreement for feature 58667 at
half-strength suppression remains a scientific qualification failure. It is
not one of the report-order discrepancies. Neither this agent check nor the
NumPy arithmetic check is independent human review.
