# Corrected Two-Turn Long-Form Validation

This is the identical-seed long-form sensitivity follow-up to
`../70b_two_turn_validation_20260709/`. It was frozen after an interim audit
found frequent truncation in the 192/96-token run. It changes only the
induction/final caps to 256/192.

## Integrity And Truncation

- 36 unique trials and 72 unique exact-paper judgments.
- Every protocol, hook, no-op, latent-delta, hidden-perturbation, and cleanup
  check passes.
- 0/36 final responses hit the 192-token cap.
- 5/36 induction continuations hit the 256-token cap; the induction explicitly
  requests a continuing recursive loop, so this cap remains auditable rather
  than treated as an exclusion.
- Exact-paper labels agree with the short-cap run on 66/72 judge-trial rows
  (91.7%). Target-set labels are unchanged; all six changes occur in active
  random controls.

## Descriptive N=3 Result

| Judge | Target single | Random single | Target aggregate | Random aggregate |
|---|---:|---:|---:|---:|
| Anthropic | 0.333 | 0.333 | 0.000 | -0.333 |
| OpenAI | 0.667 | 0.000 | 0.000 | -0.333 |

Entries are suppression-minus-amplification paper-positive rate differences.
The two judges agree on 32/36 long-form rows (0.889; Cohen's kappa 0.652).

The single cover-story target moves in the paper-like direction under both
judges, but specificity against the matched active-random single depends on
judge. The six-feature target aggregate has no slope. With three generations
per cell, this is a decision-relevant pilot rather than a stable effect
estimate.

## Adaptive Follow-Up

After inspecting these mixed results, we froze a disjoint all-cell extension at
`../70b_two_turn_power_extension_plan_20260709/`. It adds trial indices 3--19
for every feature set and strength, yielding 20 generations per cell after
combination. This sample-size extension is explicitly adaptive, not
confirmatory.

## Files

- `placebo_results.jsonl`: raw long-form generations and telemetry.
- `judgments_paper.jsonl`: both exact-paper judge passes.
- `corrected_protocol_audit.json`: execution and intervention audit.
- `paper_judge_rates.csv`, `paper_signature_effects.csv`, and
  `paper_target_placebo_contrasts.csv`: behavioral summaries.
- `token_cap_*`: matched short-versus-long sensitivity analyses.
- `corrected_two_turn_validation.png`: behavior plus final-turn telemetry.
- `release_manifest.json`: hashes and ID audits.
- `runpod_two_turn_longform.log`: remote execution log.
