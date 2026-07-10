# Adaptive Public-SAE Precision Extension

This directory is the disjoint `n=17`-per-cell extension to
`../70b_two_turn_longform_validation_20260709/`. The long-form `n=3` base was
inspected before this extension was frozen, so neither this extension nor the
combined `n=20` result is confirmatory.

## Frozen Grid

- Model: `meta-llama/Llama-3.3-70B-Instruct`, loaded in 4-bit mode.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, layer 50.
- Protocol: `public_sae_two_turn_v2` with a real generated induction turn.
- Feature sets: target 58667, active-random 22326, six public targets, and six
  active-random features.
- Coefficients: `-2`, `0`, and `+2`.
- Trial indices: 3 through 19, giving 17 rows per cell and 204 rows total.
- Caps: 256 induction tokens and 192 final-answer tokens.
- Seeds: deterministic SHA-256 functions of the global seed and stable trial
  ID.

The live trial plan and feature catalog are byte-identical to the tracked
frozen plan. All 204 result IDs and seeds are unique and exactly cover that
plan.

## Pre-Judging Integrity

- Remote and local SHA-256 hashes matched for every retrieved file.
- 17/204 induction turns reached 256 tokens.
- 6/204 final turns reached 192 tokens (2.9%).
- The cap rule was frozen after a telemetry-only interim check: the primary
  analysis retains all rows, and a sensitivity excludes final-cap-hit rows.
  Because the final cap rate is below 5%, no selective regeneration is used.
- No extension behavioral rates or paper-judge labels were inspected before
  the full 204-row retrieval.

The generation-time `affirms` field uses a provisional heuristic and is not an
analysis endpoint. Behavioral reporting uses two later, condition-blind passes
of the exact paper rubric.

## Evidence Boundary

This is a clean-room signed decoder-vector intervention using public weights.
It is not an exact replication of the unavailable proprietary
Goodfire/Steering API implementation, coefficient scaling, or feature service.
The combined analysis remains conditional on this 4-bit model, public SAE,
candidate IDs, intervention, coefficient grid, and automated judges.

The source runtime is recorded in `RUNTIME_ENVIRONMENT.md`. Component and
combined analyses produce complete trial/judge audits, telemetry, cap
sensitivities, figures, and release manifests.
