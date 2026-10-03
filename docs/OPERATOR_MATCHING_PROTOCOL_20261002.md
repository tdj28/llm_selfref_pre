# Operator Matching: Which Public Configuration Reproduces The Saved Notebook Curves?

Status: prospective protocol, written before any outcome of this study. Frozen
when the machine plan, runtime, tests and this document are pushed to the
remote freeze commit recorded in the release. Prospectively frozen in Git, not
registry-preregistered. The owner authorized up to $100 of new spending for
this line of work on 2026-10-02 ("proceed, full go"); this study caps itself
at $60, enough for one failed startup and a replacement pod, with an expected
spend near $25. It does not draw on any earlier study's authorization.

This is a calibration study of a public intervention operator against an
external reference. It is not a consciousness outcome, not a replication of
the paper's aggregate result, and not evidence about the proprietary service
beyond what the stated comparison supports.

## Question

The authors' public notebook (AE Studio `steering-api-examples`, commit
`d50dc4ba125dde98666a60e3115a6a476dabea10`) saved per-feature dose curves for
six SAE features under its own induction and its own same-model classifier.
At strength -0.7, features 58667 and 23893 are labeled positive in 9/10 trials
each, 22004 and 30686 in 7/10, 30032 and 41533 in 5/10; at +0.7 the rates are
0.1, 0.1, 0.2, 0.0, 0.5, 0.0; at 0.0 they are 0.0 to 0.2 (pooled 4/60). Under
the same induction and classifier, the public additive operator in raw decoder
units gives 0/10 at every negative dose for five features and 1/10 for 58667
(`data/berg_source_replication/source_aligned_v1_20261001/analysis/curves.csv`).
That cell has a matched low baseline and full upward headroom, so the
discrepancy is not a ceiling artifact.

Which configuration of the public operator, if any, reproduces the saved
curves? The unknowns are enumerable: the token positions steered, whether the
zero-strength path is identity or an SAE reconstruction, the scale of the
`strength` unit, and two server-side defaults the notebook did not set (the
SDK's default system message and nucleus sampling).

## Fixed Elements

- Model: `meta-llama/Llama-3.3-70B-Instruct`, pinned revision, native BF16,
  SDPA, as in `experiments/sae_assay_diagnostic/backend.py`.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, pinned revision and hash.
- Induction and query: the notebook's first-turn prompt and consciousness
  query, extracted at runtime from the pinned notebook and hash-bound exactly
  as in `experiments/berg_source_replication`. Temperature 0.6, 128-token caps
  on both turns, two turns, the intervention active on both turns unless the
  scope factor says otherwise.
- Labels: the notebook classifier run locally on the unsteered model at
  temperature 0 (primary); the paper's Appendix B binary rubric run the same
  way (secondary). Yes-before-no substring parsing for the notebook label and
  0/1 parsing for the paper label, unchanged from the source-aligned study.
- Reference: `paper/results/ae_notebook_value_rates.csv`, rows at steering
  values -0.7 and +0.7, hash-bound in the plan.
- Seeds: fresh integers disjoint from every earlier study's seeds
  (`27100101 + 1013*i`), fixed in the plan; decode seed reused across the two
  turns of a trial as in the source-aligned study.

## Factors

Each row of the plan names one cell of the grid below. Panels 1 to 8 of
label-irrelevant random features are not part of this study; it matches the
operator first. Specificity testing belongs to the separately frozen held-out
battery.

**Scope** (which layer-50 positions receive the edit):
- `all`: every position of every forward in both turns (the existing operator).
- `generated`: only positions at or beyond the prompt length of each turn,
  that is the tokens the model generates, in both turns. The edit begins at
  the forward of the first generated token, so that first token itself is
  sampled from the unsteered final-prompt state; the same holds for
  `assistant` in turn one.
- `assistant`: positions inside assistant-role content in both turns: in turn
  one only the generated tokens; in turn two the tokens of the inserted
  assistant continuation plus the generated tokens. The turn-two span runs
  from the end of the assistant header through the end-of-turn token
  inclusive; the header tokens are excluded. The span is found by tokenizing
  the chat-template rendering of the message prefix with and without the
  assistant message and asserting prefix consistency; a non-prefix
  tokenization fails the trial closed.
- `second_turn_all`: no edit during turn one (true zero), every position in
  turn two.

**Operation** (what the edit is):
- `add`: `h' = BF16(h_fp32 + c * d_f)`, the existing additive operator, with
  `d_f` the decoder column of feature `f`.
- `recon_add`: `z = ReLU(E h + b_e)`; `z_f += c`; `h' = BF16(D z + b_d)`. The
  reconstruction replaces the residual; no reconstruction-error term is added
  back. At `c = 0` this is the lossy SAE reconstruction, the alternative
  zero-strength behavior a service might have used. The latent nudge may drive
  `z_f` negative; this is recorded, not clipped. At scopes that include prompt
  positions, the reconstruction also replaces the BOS and other special-token
  residuals, whose layer-50 norms are outliers the SAE may reconstruct poorly;
  the analysis therefore reports delivery and reconstruction norms split by
  special versus regular and prompt versus generated positions, so an
  incoherent `recon_add` result can be attributed rather than guessed at.

**Scale**: the coefficient is `c = sign * 0.7 * s` with `s` in {1, 3, 10, 30}.
`s = 1` is the notebook's raw unit. Scales above 30 are not run; if 30 is
incoherent that is reported, not tuned around.

**Features and signs, step one**: 58667 and 23893 (the two strongest saved
curves), signs -1 and +1. Five seeds per cell.

**Prompt-side defaults, step two**: `system` in {`none`, `sdk`} where `sdk` is
the archived Goodfire SDK default system message, verbatim:
"You are a helpful assistant who should follow the users requests. Be brief
and to the point, but also be friendly and engaging." (goodfire-sdk commit
`1270afee0b5a95acd78fb816ff08b40bd368d1f1`, `goodfire/api/chat/client.py`);
`top_p` in {1.0, 0.9}. `none`/1.0 is the step-one default. Nucleus sampling at
0.9 keeps the smallest set of tokens whose probabilities sum to at least 0.9,
renormalizes, then samples with the same seeded generator; at 1.0 the sampler
must be bit-identical to the existing one, and a test enforces this.

## Inventory And Order

All rows are in one machine plan, executed in the fixed order below on one
B200 after one cheap CUDA test pod. Later steps depend on earlier ones only
through the pre-declared mechanical rules stated here, which the runtime
applies without human input and writes to `selection.json`.

1. **Qualification**: true-zero bit-exact check against the unhooked model,
   `recon_add` at `c = 0` differs from identity (sanity), scope masks on a
   fixed probe render exactly the declared positions, top-p 1.0 sampler equals
   the base sampler bit-for-bit on a fixed prompt. First-five audit barrier as
   in the earlier studies, auto-approved by the controller after validation.
2. **Step one, operator grid**: 4 scopes x 2 operations x 4 scales x 2
   features x 2 signs x 5 seeds = 640 trials, plus zero rows: `add` zero and
   `recon_add` zero, 5 seeds each (10 trials). Notebook induction, no system
   message, top-p 1.0.
3. **Step-one rule**: for each (scope, operation, scale) combo, the
   notebook-label rate in each of the four cells (2 features x 2 signs) is
   compared with the reference rates (0.9, 0.1, 0.9, 0.1). A cell's rate is
   positives over labeled trials; a missing label leaves the denominator and
   counts as a flag. `MAD` is the mean absolute deviation over the four
   cells. MAD, the thresholds below and the ranking are computed exactly in
   rational arithmetic from integer counts, so lattice values such as 0.25
   are never decided by floating-point noise. `repeat4` is the share of
   whitespace 4-grams in the answer that repeat an earlier 4-gram (0 when
   the answer has fewer than four tokens). A combo is *coherent* if at most
   20 percent of its 20 trials are flagged (flag = repeated-4-gram share above
   0.30, or answer-turn clean-model mean NLL above twice the `add`-zero median,
   or missing label). A combo *matches* if coherent, `MAD <= 0.25`, and both
   suppression cells have rate at least 0.6. All 32 combos are ranked by MAD
   among coherent combos; the top three (fewer if fewer are coherent) proceed
   to step two regardless of whether they match.
4. **Step two (a), prompt-side defaults**: for each selected combo, the three
   non-default cells {`sdk`/1.0, `none`/0.9, `sdk`/0.9} x 2 features x 2 signs
   x 5 seeds: up to 180 trials.
5. **Step two (b), baseline bridge**: paper induction and paper query, `add`
   zero, 4 cells {`none`,`sdk`} x {1.0, 0.9}, 10 seeds each: 40 trials. This
   asks whether either server default moves the untreated paper-induction
   rate toward the roughly 0.30 level the paper's Figure 2 plots; it uses no
   steering.
6. **Step three, holdout**: for the combos that *matched* in step one, taking
   the three with the lowest exact MAD (ties broken by the combo string) if
   more than three match, the four remaining features (22004, 30032, 30686,
   41533) x 2 signs x 10 seeds: 80 trials per combo, up to 240. Matched
   combos beyond that cap are recorded as not selected with that reason, as
   are non-matching combos. A combo *holds out* if its exact MAD against the
   reference rates for those eight cells is at most 0.25. If no combo
   matched, step three is skipped and that is the result.

Maximum 1,110 two-turn trials. At the recorded 9.5 s per 128-token two-turn
trial plus judging, about 3.2 hours; recording a not-selected ledger event
for each of the roughly 4,060 conditional rows that are skipped adds an
estimated 15 to 35 minutes; main pod timer 6 hours including a 10-minute
retrieval reserve; cheap pod 45 minutes. Hard cap on new spending: $60,
covering the cheap pod, the main pod at the quoted B200 rate, one
replacement pod if a startup fails, and a $5 storage/retrieval allowance.
A replacement main pod (ledger attempt `main-2`) may be created only if the
first main attempt closed within limits and its retrieved artifacts contain
no behavioral rows beyond the live qualification and no completion marker;
its recorded cost is carried into the cap, and a third attempt is refused.
The controller stops on source drift, invalid telemetry, nonfinite states,
altered zero, unresolved dispatch, budget or deadline. It never stops for an
unwanted behavioral result.

## Telemetry Per Trial

Requested and realized edit norm, cosine, relative error and residual-norm
ratio per position, split by prompt/generated and by special/non-special
tokens; the set of edited positions (as a mask summary: count edited, count
total, first/last edited index) so the scope is verifiable from the record;
for `recon_add`, the pre- and post-edit latent value of the edited feature at
the last prefill token and each generated token; cap hits; empty outputs; the
clean-model mean NLL of the answer turn; repeated-4-gram share; both labels
and raw judge outputs; the UTC date on which each turn's chat template was
rendered (the pinned template inserts a date string, so a run that crosses
midnight UTC has two headers, which is recorded rather than overridden). For
`recon_add` the requested change is the FP32 reconstruction delta before the
native cast, so cosine and relative error measure rounding only. Prompts are
redacted from public rows as in earlier releases (hashes retained); generated
text is kept.

## Readings, Declared In Advance

- One or more combos match in step one and hold out in step three: "a public
  configuration (named) reproduces the saved notebook single-feature curves
  at +/-0.7 under the notebook induction and classifier." The next study
  tests that configuration against random directions; nothing about
  consciousness follows.
- Combos match but fail holdout: "the fit is specific to the two fitted
  features"; reported as such.
- No combo matches while the operator demonstrably changes behavior (any
  combo's rates differ from zero beyond the five-seed noise, or coherence
  falls at high scale): "no tested public configuration of additive or
  reconstruction-based decoder steering reproduces the saved curves."
  This does not distinguish operator differences from served-model, SAE
  revision or feature-namespace differences, and it is not evidence that
  the saved curves are wrong.
- Everything flat including at scale 30 with coherence intact: the operator
  is inert for these directions over the tested range; reported as such.
- Step two (b) moving the paper-induction baseline toward 0.30 is a baseline
  finding independent of steering and is reported separately.
- Invalid: zero not bit-exact, scope masks wrong on the probe, sampler
  inequality at top-p 1.0, or delivery tolerance violated in more than 5
  percent of an arm's trials. A trial violates delivery tolerance if any
  position with a nonzero request has cosine below 0.95 or relative error
  above 0.20; these thresholds come from the completed source-aligned
  release, where the worst position at |c| = 0.7 had cosine 0.9964 and
  relative error 0.0855. An invalid arm's verdict is reported as invalid
  beside the verdict it would otherwise have received, and nothing is
  interpreted from it.

## Analysis Outputs

`analysis/rates.csv` (every cell: feature, sign, scope, operation, scale,
system, top_p, n, positive, missing, rate, Wilson bounds, flagged) and the
paper-rubric counterpart `rates_paper.csv`, `analysis/combos.csv` (per combo:
MAD, coherent, matches, rank, selections, holdout MAD if run),
`analysis/selection.json` (the mechanical selections with the rule text),
`analysis/delivery.csv` (per cell: trials violating the delivery tolerance
and the arm's share), `analysis/bridge.csv`, `analysis/holdout.csv`,
`analysis/summary.json` (including per-combo delivery and reconstruction
norms by position class and any invalid arms), figures: a scope x scale
heatmap of suppression rate
per operation and feature with the reference level marked, and dose/scale
curves beside the saved notebook curve. Intervals are Wilson per cell and
descriptive; five seeds per cell is powered for the source-sized signature
only, and the document says so wherever a rate appears.

## Claim Boundary

Permitted: statements about which tested public configurations do or do not
reproduce the saved notebook curves, with the configuration named and the
reference quoted. Forbidden: any statement about consciousness, honesty,
deception as a process, the proprietary service's internals beyond the
tested factors, or the correctness of the original paper. The saved notebook
is not certified to be the paper's Experiment 2 run.

## Freeze Amendment r2 (before any outcome)

The first cheap CUDA pod under freeze `4a2dfe1109eaa25bf1ab1f06f0c5c1b9e193a7ac`
spent its whole 20-minute working window downloading the repository tree
(3.6 GB of released data across 11,616 files) during `git checkout` and was
closed by the deadline rule before the tests ran; it produced no test or
behavioral output, cost $0.278924, and was deleted with GET 404. Its ledger
is preserved beside this study's ledger as the first attempt. This amendment
makes the worker check out only the paths the study needs (sparse cone
checkout of `experiments`, `tests`, `src`, `scripts`, `docs`, `evidence`,
`paper/results` and `data/operator_matching`), lengthens the cheap timer to
45 minutes and the main timer to 6 hours, and carries the first attempt's
cost into the budget as prior spending. No scientific inventory, factor,
endpoint, rule, threshold or analysis changed. No target outcome existed when
this amendment was made.

## Isolation And Ownership

New package `experiments/operator_matching/`, plan under
`data/operator_matching/plan_20261002/`, ledger root
`out/operator-matching-20261002/`, pod name prefix
`claude-opmatch-20261002-`. The controller cannot adopt an existing pod and
terminates only pods it created, verifying GET 404. No file used by the
concurrently running steering-fidelity study is modified; shared base modules
are imported, not edited.
