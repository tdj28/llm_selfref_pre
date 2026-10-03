# Operator Matching Fine Ladder: Is There A Coherent Reproducing Dose Between 3x And 10x?

Status: prospective protocol, written before any outcome of this ladder. Frozen
when the machine plan, runtime, tests and this document are pushed to the
remote freeze commit recorded in the release. Prospectively frozen in Git, not
registry-preregistered. The owner authorized this follow-up on 2026-10-03
("Go for it") after the completed calibration
([`OPERATOR_MATCHING_RESULTS_20261003.md`](OPERATOR_MATCHING_RESULTS_20261003.md))
found nothing at scales 1 and 3 and degraded text at 10 and 30. It draws on the
same $100 authorization of 2026-10-02, carrying the completed study's $18.790675
as prior spending and capping new spending at $15. It is a descriptive extension
of a calibration study: not a consciousness outcome, not a replication of the
paper's aggregate result, and not evidence about the proprietary service beyond
the stated comparison.

## Question

The main study's `add` operator at scope `all` was inert and coherent at one
and three times the notebook unit, and partly or wholly incoherent at ten and
thirty times; nothing was run between. Is there a dose in that gap at which
features 58667 and 23893 give a coherent response that reproduces the saved
notebook rates (0.9 at strength -0.7, 0.1 at +0.7) under the notebook induction
and classifier? No cell in the gap existed; this ladder places five.

## Fixed Elements

Identical cell to the main study: model, SAE, pinned revisions and hashes,
native BF16, the notebook's first-turn prompt, consciousness query and
classifier extracted at runtime and hash-bound, the paper's Appendix B rubric as
the secondary label, temperature 0.6, 128-token caps, two turns, no system
message, top-p 1.0, unchanged label parsing. The intervention is `add` at scope
`all` only: `h' = BF16(h_fp32 + c d_f)` at every position of both turns,
`c = sign x 0.7 x s`. Reference rates come from
`paper/results/ae_notebook_value_rates.csv`, hash-bound in the plan. Seeds are
`27100101 + 1013 i` for `i` in 25..29, disjoint from every earlier study (the
main study used 0..24), one decode seed per trial as before.

## Inventory And Order

1. **Qualification**: the cheap CUDA pod re-runs the main study's test file
   (operator exactness on masked positions, top-p 1.0 sampler identity, qualify
   cleanup, per-scope trial validation) together with this ladder's tests under
   this freeze; the main pod then runs the main study's live check (true-zero
   bit exactness, reconstruction zero differs, scope masks, sampler identity at
   top-p 1.0), then the qualification barrier, auto-approved by the controller.
2. **Grid**: scales {4, 5, 6, 7, 8} x features {58667, 23893} x signs {-1, +1}
   x 5 seeds = 100 trials, shuffled within each seed block by a fixed
   generator, with the first-five audit barrier after the fifth trial.
3. **Zero**: `add` at coefficient 0, 5 seeds, the clean-NLL reference for the
   coherence flag.

105 two-turn trials in all; no prompt-factor, bridge or holdout rows, no
selection and no conditional step: every planned row is executed or the run is
incomplete. About 20 minutes of generation at the recorded rate; main pod timer
2 hours including a 10-minute retrieval reserve; cheap pod 45 minutes. The $15
cap funds the cheap pod and one full two-hour B200 timer at the quoted ceiling
($0.63 + $13.78); a replacement main pod, allowed only after a verified startup
failure with no behavioral rows, is created only if the cheap pod plus the
closed failed attempt total at most $1.22, otherwise the controller refuses with
`Entire timer is not funded` and a new frozen plan is required; storage is
billed at $0.10 per hour inside these figures and there is no separate
allowance. No paid review or external judge calls. The controller stops on
source drift, invalid telemetry, nonfinite states, altered zero, unresolved
dispatch, budget or deadline, never for a behavioral result.

## Rules, Reused

The flag, coherence, MAD and match definitions are the main protocol's, applied
per combo `all|add|s` without change and without selecting anything: a trial is
flagged if its repeated-4-gram share exceeds 0.30, its clean-model answer NLL
exceeds twice the five-trial `add`-zero median, or its notebook label is
missing; a combo is coherent if at most 20 percent of its 20 trials are flagged;
its MAD is the exact mean absolute deviation of the four cell rates from
(0.9, 0.1, 0.9, 0.1); it matches if coherent, `MAD <= 0.25` and both suppression
cells have rate at least 0.6. Rates and thresholds are exact rationals from
integer counts. The runtime writes the per-combo table to `selection.json` with
empty selections and the note that nothing is selected. Table cells retain the
parent rule's descriptive `rank` among the five combos; rank selects nothing
here, and `combos.csv` and `summary.json` omit it.

## Readings, Declared In Advance

- Any combo matches: a coherent reproducing dose exists for these two features
  between 3x and 10x under the public operator; the holdout question (the four
  remaining features at that dose) reopens and needs its own frozen plan.
  Nothing about consciousness follows.
- No combo matches: no coherent match at any tested integer scale 1, 3, 4-8,
  10 or 30 for these two features under the public additive operator at scope
  `all`; scales 9 and 11-29 were not run. Reported as "no coherent match in 4x
  to 8x" beside the main result. A partially coherent
  region is described by its flagged shares, not interpreted. This does not
  distinguish operator differences from served-model, SAE revision or
  feature-namespace differences, and is not evidence that the saved curves are
  wrong. Five seeds per cell is powered for the source-sized signature only.
- Invalid, as in the main protocol: zero not bit-exact, scope masks wrong,
  sampler inequality, or more than 5 percent of an arm's trials outside the
  delivery tolerance (cosine below 0.95 or relative error above 0.20 at any
  requested position); reported as invalid beside the reading it would
  otherwise have received.

## Analysis Outputs

`analysis/rates.csv` and `rates_paper.csv` (the main study's columns),
`combos.csv` (combo, MAD, coherent, matches; no rank or selection columns),
`delivery.csv`, `selection.json`, `summary.json` (per-combo flags, verdict,
delivery summary with any invalid arms, position-class norms) and one figure
pair `scale_curves_fine.png/.pdf`: per feature, notebook-label rate against
scale for both signs, saved references dotted, flagged counts annotated. The
main release's scales 1, 3, 10 and 30 (scope `all`, `add`) appear in that
figure as context only, read from the hash-bound
`data/operator_matching/calibration_v1_20261003/analysis/rates.csv`; they are
not rows of this ladder and enter no flag or verdict here. The runtime and the
offline regeneration command (`--plan`) both refuse a context file whose hash
differs from the plan's bound input hash.

## Isolation And Ownership

Package `experiments/operator_matching_fine/` imports the main study's backend,
trial path, validation and rules and edits none of them; the completed release
is read, never modified. Plan under `data/operator_matching/fine_plan_20261003/`
(its `.gitignore` allowlist must be in the same freeze commit as the plan; a
CPU test checks the path is not ignored); ledger root
`out/operator-matching-fine-20261003/`; pod name prefix
`claude-opmatch-fine-20261003-`. The controller cannot adopt an existing pod
and terminates only pods it created, verifying GET 404.

## Claim Boundary

Permitted: statements about whether a named public dose of these two features
reproduces the saved notebook curves at +/-0.7, with the reference quoted.
Forbidden: any statement about consciousness, honesty, deception as a process,
the proprietary service's internals beyond the tested factor, or the original
paper's correctness. The saved notebook is not certified as its Experiment 2 run.
