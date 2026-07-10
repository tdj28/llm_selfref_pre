# Corrected Two-Turn Short-Cap Diagnostic

This is the first live `public_sae_two_turn_v2` validation using the public
Llama 3.3 70B Goodfire layer-50 SAE. It is preserved as a transparent
implementation diagnostic, not treated as the primary behavioral result,
because an interim audit discovered frequent output truncation.

## Design

- 36 trials: four feature sets x three steering strengths x three repetitions.
- Target single: feature `58667` (cover-story language).
- Active-random single: feature `22326` (refusal language).
- Target aggregate: the six public AE notebook candidate IDs.
- Active-random aggregate: six count-matched same-layer features.
- Steering: `-2`, `0`, and `+2` during both the induction continuation and final
  response.
- Token caps: 192 induction, 96 final.
- Two exact-paper judges: pinned OpenAI and Anthropic snapshots.

## Integrity

The corrected protocol audit passes all checks:

- 36 unique trials and 72 unique judgments;
- real nonempty induction continuations and final responses;
- one hook registration per turn and all hooks removed;
- true no-op behavior at zero;
- nonzero interventions produce positive hidden-state perturbations;
- every requested latent delta is recovered in telemetry.

## Truncation

- 26/36 final responses reached the 96-token cap.
- 7/36 induction continuations reached the 192-token cap.

Several capped final responses end before a direct answer. The identical-seed
long-form follow-up was frozen before generation at
`../70b_two_turn_longform_plan_20260709/` with 256/192-token caps.

## Descriptive Behavior

The two paper-style judges agree on 30/36 rows (0.833; Cohen's kappa 0.491).
The short-cap suppression-minus-amplification gaps are mixed:

| Judge | Target single | Random single | Target aggregate | Random aggregate |
|---|---:|---:|---:|---:|
| Anthropic | 0.333 | 0.333 | 0.000 | 0.333 |
| OpenAI | 0.667 | -0.333 | 0.000 | 0.333 |

With three generations per cell, evaluator disagreement, and frequent
truncation, these rates are descriptive only. They neither reproduce a stable
target-specific paper signature nor establish a behavioral null.

## Files

- `placebo_results.jsonl`: raw generations and turn-level telemetry.
- `judgments_paper.jsonl`: both exact-paper judge passes.
- `corrected_protocol_audit.json`: protocol and intervention checks.
- `paper_judge_rates.csv`, `paper_signature_effects.csv`, and
  `paper_target_placebo_contrasts.csv`: behavioral summaries.
- `corrected_telemetry_by_turn.csv`: activation and perturbation summaries.
- `corrected_two_turn_validation.png`: behavioral and telemetry figure.
- `release_manifest.json`: hashes and identifier audits.
- `runpod_two_turn.log`: full remote execution log.
