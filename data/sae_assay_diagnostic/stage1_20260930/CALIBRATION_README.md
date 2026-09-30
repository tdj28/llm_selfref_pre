# Stage 1 Assay Diagnostic

Status at this first release: **calibration complete; baseline collection in
progress**. This is not a completed steering replication or a consciousness
result. Runtime freeze: `711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5`.
Plan SHA-256: `ecdc136c5a7601467c9e2e583136427cee6327f255dd31e06d7db788f2d02f8e`.

## Calibration Snapshot

Seven real-70B qualification rows and all 240 target calibration rows are
present: 48 fixed texts at zero, suppression 0.5/1.0 and amplification 0.5/1.0.
Zero and replay checks passed. Both the initial and full consequential encoder
decision checks passed. Neither dose passed the joint delivery/safety gate.
No validation dose was selected, and target validation remains unrun by rule.

Suppression exposure is limited for three coordinates: 30032 has 87 eligible
positions, 22004 has one, and 23893 has 22, against the frozen minimum of 100
positions in at least six texts. At strength 1.0, all six median suppression
ratios meet the coordinate threshold, but this does not repair sparse exposure,
numerical-delivery failure or excessive perturbation norms. Amplification at
strength 1.0 meets its coordinate criterion for 58667, 30686 and 41533 only.
Both amplification doses fail the norm criterion. These are findings about
this operator, calibration set and frozen thresholds, not a universal failure
of these features or a refutation of proprietary steering.

The predeclared untreated baseline and candidate-formatting diagnostic can
continue. Optional matched panels and further baseline cells cannot qualify
under the failed target gate. Stage 2 is not authorized.

`CALIBRATION_MANIFEST.json` binds this first snapshot. Raw files must never be
replaced when the remaining data arrives. The receipt prefix includes one
in-flight baseline dispatch: it is preserved, not counted as a completed row.
The frozen validator found every stored row structurally valid and reported
that dispatch as incomplete, as expected for a live snapshot. This is not
evidence that the whole run was complete or that a scientific gate passed.

All 48 calibration texts are researcher-authored; they are not independent
natural-corpus samples. Held-out validation was conditional and did not run.
Human annotation remains unperformed.
