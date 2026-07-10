# Public-SAE Gating Analysis Alignment Note

Date: 2026-07-10

At confirmatory generation row count 70/1,500, before any response text was
opened or any outcome was classified, an outcome-blind code audit found that
the analyzer implemented a stricter missing-output gate than the frozen
protocol. The protocol treats empty final outputs as missing and makes the
verdict inconclusive only above 2% missing primary labels. The code also
required every final output to be nonempty, so one empty output would have
overridden the documented 2% rule.

The redundant all-nonempty final-output check is removed. Empty outputs remain
explicitly counted, receive missing local labels, and contribute to the frozen
2% missingness and aggregate arm-imbalance gates. Empty induction continuations
remain a technical failure. No threshold, estimand, observed value, or verdict
rule changed; the implementation now follows the already-public protocol.

The same review made Holm correction robust to a missing secondary
individual-feature p-value: correction is applied across finite tests, and a
missing test remains missing. This does not affect the primary aggregate
verdict or specificity modifier.
