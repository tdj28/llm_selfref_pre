# Public-SAE Consciousness-Gating Amendment 1

Date: 2026-07-10

Status: **prospective relative to every confirmatory behavioral outcome**

Initial calibration SHA-256:
`5ee29141d9f0928e3720e2ff945ee27cd270bf2f42bc011918f598e5a4654d10`

## What Was Known

The telemetry-only calibration completed all 11 technical pilot trials. The
runner discarded response text and retained only output hashes, token counts,
cap flags, and intervention diagnostics. No confirmatory generation had begun,
and no calibration response was persisted, classified, printed, or inspected.

The initial analytic multiplier was `m0 = 6.266`. Every hook, true-zero no-op,
attention-mask, latent-delta, nonfinite-value, and token-cap check passed. There
were no induction or final cap hits. The gate failed only because the realized
final-turn relative hidden-state RMS was slightly above both prespecified upper
bounds:

- calibrated single median: `0.0857685573`, versus allowed `[0.03, 0.08]`;
- calibrated aggregate median: `0.1556249690`, versus allowed `[0.04, 0.15]`.

The literal scale remained small: final-turn RMS was approximately `0.0137` for
single-feature endpoints and `0.0271` for target aggregates. The three matched
control panels were selected under the primary, unrelaxed calipers. No feature
selection or matching decision used behavioral output.

## Amendment

The analytic decoder-norm approximation is retained as `m0` for provenance,
but the one permitted correction uses the observed calibrated-single telemetry
to target the protocol's original `0.05` relative-RMS center:

```text
m1 = round(m0 * 0.05 / observed_single_median, 3)
   = round(6.266 * 0.05 / 0.0857685573, 3)
   = 3.653
```

The runner must derive `m1` from the hashed failed calibration; it does not
accept a manually entered multiplier. It must also reproduce the same 18
control IDs. The complete 11-trial technical pilot is rerun at `m1`, and every
original gate remains in force. No second automatic rescaling is allowed. A
second failure stops the study pending another public amendment.

This amendment changes only the telemetry-calibrated sensitivity scale. The
literal paper-number scale remains the primary replication scale, and all
trial counts, prompts, features, controls, seeds, judges, estimands, missingness
rules, thresholds, and verdict rules remain unchanged.
