# Source-Alignment Local Review

Automated separate-agent review, 2026-10-01. Not human peer review. It covers
the completed native-BF16 source study and the outcome-blind methods text for
the random-subset extension, not that extension's still-pending results.

## Finding And Correction

The opening source section described "code and analysis" as pinned before
outcomes. That was too broad: the runtime and primary behavioral analysis
were frozen, whereas secondary diagnostic reductions and displays were added
separately. The manuscript now names the narrower frozen scope and explicitly
labels the internal-readout reductions descriptive. The capture schedule
itself remains bound to the original prospective plan.

## Checks

- The J-lens equations match the executed FP32 transport, final RMSNorm gains,
  denominator and selected unembedding rows. Gain-free linear differences and
  normalized readout differences are distinct. Requested-vector predictions
  are approximate because delivered BF16 edits are rounded.
- The honesty/deception observation is restricted to the two-seed,
  zero-source-history, layer-78, target-minus-matched-panel summary. It is not
  a statement about individual seeds, all transports, or calibrated honesty.
- The new table retains seven groups, both signs and all five random
  transports in its extrema. The range is not a confidence interval.
- The ensemble methods match the frozen subset/magnitude coupling, 450 rows,
  block unit, Clopper-Pearson marginal construction and threshold rule.

The separate table check verifies 14 displayed rows from all 588 overview
contrasts and 4,704 source-reduced seed/panel rows, with optional pinned-Git
cross-checking. It does not reconstruct raw states or validate token scores
as mental-state measurements. The source release is pinned at
`ef10a0349e047272212319dadf484c3281e60bbe`.

No live ensemble outcome was inspected for this review. There was no new paid
review call. Earlier Pro verdicts continue to refer to their original packets.
