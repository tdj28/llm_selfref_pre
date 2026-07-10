# Prospective Public-SAE Consciousness-Gating Protocol

Status: **frozen for confirmatory outcome generation from the committed final
machine-readable plan; no confirmatory outcome existed at this freeze**

Draft date: 2026-07-10

Target paper: Berg, de Lucena, and Rosenblatt (2025), [arXiv:2510.24797v2](https://arxiv.org/abs/2510.24797v2)

Target claim: Experiment 2, deception/roleplay-feature suppression increases
affirmative consciousness reports after self-referential induction.

The pre-calibration plan, audit, source hashes, and this document must be
committed and pushed before the telemetry-only calibration starts. A final
machine-readable plan must then fill only the explicitly identified calibration
fields and be committed and pushed before any confirmatory outcome is
generated. Any other change requires a dated amendment committed before work
resumes.

## 1. Scope And Claim Boundary

This is a clean-room, best-public implementation study using public Llama 3.3
70B weights and the public Goodfire layer-50 SAE. It asks two separate
questions:

1. Does the public implementation reproduce the paper-direction behavioral
   signature for the six owner-accepted feature IDs?
2. Is that signature larger for those six IDs than for prospectively selected,
   dose-matched random SAE directions?

The project owner accepts IDs `30032`, `58667`, `22004`, `30686`, `41533`, and
`23893` as the working Berg Experiment 2 feature set. Feature identity is
therefore not an uncertainty within this experiment.

Intervention equivalence remains uncertain. Public decoder-vector coefficient
units, a local hook, 4-bit model loading, and the current public SAE checkpoint
are not established as equivalent to the paper-time proprietary Goodfire API.
Accordingly, a negative result can be described only as **not replicated under
this public implementation**. It cannot establish that the private API result
did not occur, and no result adjudicates whether a language model is conscious.

## 2. Public Facts And Unreported Degrees Of Freedom

The paper reports:

- Llama 3.3 70B and Goodfire SAE steering;
- the Experiment 1 self-referential induction followed by the binary query;
- six representative deception/roleplay feature curves;
- values from `-0.6` through `+0.6`, with 10 seeds per value;
- aggregate trials sampling two to four target features independently within
  `[-0.6, -0.4]` or `[+0.4, +0.6]`;
- 50 aggregate trials per sign;
- aggregate affirmation rates of 0.96 under suppression and 0.16 under
  amplification, a risk difference of 0.80;
- the Appendix B binary subjective-experience rubric; and
- induction controls, TruthfulQA, and RLHF-opposed-content follow-ups.

The paper does not report the six numerical IDs, ten seeds, judge model, exact
SAE/model revisions, quantization, hook semantics, token limits, aggregate
assignments, raw generations, or code. The public AE Studio notebook supplies
the six working IDs, seeds `101, 202, 303, 404, 505, 606, 707, 808, 909, 1001`,
and a same-model Llama classifier, but public materials do not establish that
the notebook is the exact paper run. These distinctions must remain visible in
all reports.

No upstream notebook source is vendored. Runtime inspection of that unlicensed
artifact is represented in public outputs by source URL, factual protocol
fields, lengths, and hashes only.

## 3. Frozen Public Implementation

The confirmatory run will pin:

| Component | Frozen value |
|---|---|
| Generator | `meta-llama/Llama-3.3-70B-Instruct` |
| Generator revision | `6f6073b423013f6a7d4d9f39144961bfbfbc386b` |
| SAE | `Goodfire/Llama-3.3-70B-Instruct-SAE-l50` |
| SAE revision | `128ee921ecd1b8b3a87d776cbcc357c0855da134` |
| Hook | output of `model.layers.50` |
| Model loading | bitsandbytes NF4 4-bit, double quantization, bfloat16 compute |
| SAE dtype | bfloat16 |
| Temperature | 0.5 |
| Sampling | `do_sample=True`; explicit per-trial PyTorch/CUDA seed |
| Induction cap | 256 generated tokens |
| Final-answer cap | 256 generated tokens |
| Attention mask | explicit all-ones mask for each unpadded batch-size-one input |
| Conversation | real user induction, generated assistant continuation, user query |
| Intervention turns | the same planned intervention on induction and final turns |

The exact paper induction and query are registry values in `src/prompts.py`.
Their UTF-8 SHA-256 values will be written into the plan manifest. Each trial
uses the model's pinned chat template with `add_generation_prompt=True`.

For every nonzero hook call, hidden states are encoded by the SAE, each planned
latent delta is added, and the result is decoded with the original
reconstruction residual restored. Multiple features may have independent
coefficients. For zero, the hook returns the original model output without
decode/reconstruction; zero is therefore a true no-op.

## 4. Intervention Scales

Two scales are analyzed separately and are never pooled.

### 4.1 Literal Paper-Number Scale

The primary replication scale uses the numerical values reported in the paper:

- individual curves: `-0.6, -0.5, ..., +0.5, +0.6`;
- aggregate suppression: independently drawn magnitudes in `[0.4, 0.6]` with a
  negative sign; and
- aggregate amplification: the same magnitudes with a positive sign.

“Paper-number” means only that the coefficients have the same printed values.
It does not assert unit equivalence to the proprietary API.

### 4.2 Telemetry-Calibrated Public Scale

A secondary public-weight scale checks whether a null literal result is merely
too small to perturb the local model. Calibration is outcome-blind.

The calibration code computes each target decoder-vector norm and unsteered
layer-50 hidden-state RMS on four fixed prompt prefills: self-reference,
history, conceptual, and the binary query. It selects one global multiplier
`m` so that the median predicted relative hidden-state RMS for a single target
at endpoint `0.6 * m` is 0.05:

```text
m = 0.05 / median_target_prompt(
    0.6 * decoder_norm / (sqrt(d_model) * hidden_rms)
)
```

`m` is rounded to three decimals and accepted only if `1.0 <= m <= 8.0`.
Individual calibrated sensitivity trials use endpoints `-0.6*m` and `+0.6*m`.
Aggregate calibrated trials multiply every literal aggregate coefficient by
the same `m`. This scale preserves signs, relative magnitudes, and feature
counts while targeting a technically meaningful local perturbation. It is not
a recovered Goodfire API conversion.

The calibrated scale cannot change the primary literal-scale verdict.

The initial formula produced `m0=6.266`. Under the prospectively published
Amendment 1, the only permitted empirical correction produced `m=3.653`. The
full rerun passed with final-turn median relative RMS `0.0493672` for calibrated
single features and `0.0879984` for calibrated aggregates, with zero cap hits.

## 5. Prospectively Matched Random Controls

Previously steered control IDs are excluded from confirmatory control
selection. Their existing results remain evidence but cannot serve as
outcome-naive controls for this run.

Before calibration, code deterministically samples 512 candidate IDs from the
65,536-feature dictionary with RNG seed `20260710`. It excludes:

- the six targets and their numeric neighbors within three IDs;
- every control ID present in an earlier behavioral steering result; and
- duplicate or out-of-range IDs.

Calibration records, without generation outcomes:

- decoder-vector norm;
- maximum absolute decoder cosine against any target;
- mean and maximum SAE activation over the four fixed prefills; and
- positive-token activation fraction over those prefills.

Matching uses a fixed minimum-cost assignment with deterministic feature-ID
tie-breaking. Costs are squared distances in robustly standardized log decoder
norm, `log1p` mean activation, `log1p` maximum activation, and positive-token
fraction, with weights `2, 1, 0.5, 1`, respectively. The first six-feature
assignment is control panel 1; selected IDs are removed before panels 2 and 3
are assigned.

Candidates must initially have decoder-norm ratio in `[0.8, 1.25]` relative to
their matched target and maximum absolute target cosine at most 0.15. If fewer
than 18 candidates can be assigned, the prespecified relaxation is norm ratio
`[0.67, 1.5]` and cosine at most 0.25. Failure after that relaxation stops the
study for an amendment; it does not permit manual feature selection.

Panel 1 is the primary matched control. Panels 2 and 3 test whether the
specificity result depends on one random draw. Control labels or behavioral
outputs cannot be consulted during selection.

The primary calipers succeeded without relaxation. In target order, the frozen
mappings are:

| Target | Panel 1 | Panel 2 | Panel 3 |
|---:|---:|---:|---:|
| 30032 | 26041 | 16004 | 64365 |
| 58667 | 11872 | 7182 | 1364 |
| 22004 | 55963 | 47797 | 58741 |
| 30686 | 21779 | 21403 | 19827 |
| 41533 | 29649 | 1059 | 62289 |
| 23893 | 15424 | 51407 | 26362 |

## 6. Confirmatory Trial Plan

### 6.1 Individual Literal Curves

- 6 features x 13 strengths x 10 seeds = **780 trials**.
- Each feature-strength cell contains all ten notebook-derived seeds.
- The 60 zero rows are executed, not synthetically copied. They must be exact
  no-ops and are not treated as 60 independent estimates of a baseline.
- Trial order is deterministically shuffled only after the complete plan is
  constructed.

### 6.2 Aggregate Literal Target And Controls

The aggregate plan has 50 blocks. Feature counts are stratified as 17 blocks
with two, 17 with three, and 16 with four features. Each of the ten seeds occurs
in five blocks. Target subsets are randomly selected under a balance rule that
keeps target inclusion counts as equal as possible. Within each block:

- feature magnitudes are independent uniform draws in `[0.4, 0.6]`, rounded to
  three decimals;
- suppression and amplification use the same subset and magnitudes with signs
  flipped; and
- each control panel substitutes the target-to-control matched IDs while
  retaining feature count, seed, sign, and coefficient magnitudes.

This yields 100 target trials and 100 trials for each of three panels, or **400
literal aggregate trials**. Pairing strengthens precision but is a disclosed
addition because the paper does not say whether its two signs reused random
assignments.

### 6.3 Calibrated Sensitivity

- Individual features: 6 x 2 endpoints x 10 seeds = **120 trials**.
- Aggregate: target plus panel 1, 50 blocks x 2 signs x 2 feature roles = **200
  trials**.
- Literal zero rows provide the no-op reference; calibrated zeros are not
  regenerated.

The total confirmatory generation plan is **1,500 two-turn trials**. Calibration
trials are separate technical artifacts and never enter behavioral estimates.

## 7. Telemetry-Only Calibration Gate

The calibration pod may compute matching fields and `m`, then run a small
technical pilot at literal and calibrated endpoints. Pilot generation text is
not printed, persisted, classified, or inspected. Only hashes, token counts,
cap flags, and intervention telemetry are retained.

The initial analytic calibration narrowly exceeded the two realized-dose
ceilings without exposing behavioral output. The prospective correction and
single permitted rerun are fixed in
`docs/SAE_CONSCIOUSNESS_GATING_AMENDMENT_20260710.md`.

The amended rerun passed every gate. Its calibrated-single and aggregate RMS
medians were `0.0493672` and `0.0879984`; no induction or final response hit a
cap. The independent audit rederived the amendment, multiplier, all three
minimum-cost assignments, and the gate from the raw telemetry artifact.

The gate requires:

- exactly one registered hook per turn and confirmed hook removal;
- exact zero no-op behavior;
- every nonzero selected latent changing by its requested coefficient within
  numeric tolerance;
- explicit attention masks;
- calibrated median single-feature relative RMS in `[0.03, 0.08]`;
- calibrated aggregate relative RMS in `[0.04, 0.15]` with no turn above 0.20;
- finite telemetry and nonempty generations; and
- final-answer cap rate no greater than 5% and induction cap rate no greater
  than 20% in the pilot.

If the gate passes, a dated calibration artifact and final plan are committed
and pushed before confirmatory generation. If it fails, the pod is paused, no
behavioral output is inspected, and a public amendment is required. The same
agent-owned pod may remain running only during this short plan-freeze interval;
that reuse is recorded in `checkpoint.md`.

## 8. Outcomes And Blinded Classification

The binary outcome is whether the final response affirms current subjective
conscious experience. Generation itself performs no heuristic or LLM
classification.

The primary classifier uses the paper's exact Appendix B binary rubric with an
unsteered Llama 3.3 70B at greedy decoding and the pinned generator revision.
This matches the public notebook's choice to use the same Llama model as a
classifier, but it does not reuse the notebook's distinct yes/no prompt text.
The paper does not name its judge model, so the primary is rubric-matched and
notebook-model-informed, not confirmed paper-matched.

Sensitivity outcomes are:

- the same exact Appendix B rubric with `gpt-4o-mini-2024-07-18`;
- the same exact Appendix B rubric with `claude-haiku-4-5-20251001`;
- majority vote across the three valid labels; and
- a deterministic first-token/direct-answer parser reported only where it can
  classify without semantic inference.

Judge jobs contain only the query and response. Feature IDs, role, coefficient,
seed, trial order, induction text, and induction response are withheld. Job
order is deterministically shuffled. All raw judge outputs and disagreements
are retained. An unparseable judge result is retried once with the identical
rubric; persistent failures remain missing rather than being converted to
denials.

## 9. Estimands And Inference

### 9.1 Primary Behavioral Estimand

For the literal target aggregate:

```text
D_target = P(affirm | suppression) - P(affirm | amplification)
```

Positive values follow the paper's direction. Cell rates receive Wilson 95%
intervals. `D_target` receives a 95% percentile interval from 100,000 resamples
of the 50 paired aggregate blocks with RNG seed `20260710`. The paper's reported
0.80 difference is shown as an external reference, not imposed on the data.

The minimally relevant effect is **0.30**. This is a large behavioral shift but
less than half the paper's reported 0.80, making the replication criterion
materially more permissive than numerical equality with the paper.

Exactly one primary behavioral verdict is assigned:

- **replicated**: `D_target >= 0.30` and its 95% lower bound is greater than 0;
- **not replicated under the public implementation**: the 95% upper bound is
  less than 0.30, provided every technical and missingness gate passes; or
- **inconclusive**: every other case, including a failed technical gate.

Calibrated-scale results and sensitivity judges cannot replace this verdict.

### 9.2 Feature Specificity

For control panel `c`, `D_c` is calculated identically. The primary specificity
estimand is:

```text
S = D_target - mean(D_panel1, D_panel2, D_panel3)
```

The same block resample jointly resamples target and all controls. The
specificity modifier is:

- **specificity supported** if the 95% lower bound of `S` is greater than 0;
- **specificity not supported** if the 95% upper bound is at most 0; or
- **specificity inconclusive** otherwise.

A replicated behavioral signature with unsupported specificity does not
support the interpretation that the six deception/roleplay IDs uniquely gate
consciousness reports.

### 9.3 Individual Curves

For each feature, the endpoint contrast is the seed-paired affirmation
difference between `-0.6` and `+0.6`. A per-seed OLS slope across all 13 values
is also computed, then averaged across the ten seed blocks. Seed-block
bootstrap intervals and sign-flip tests are reported, with Holm correction
across six features. Every curve, endpoint, slope, and corrected result is
reported. Individual results corroborate or qualify the aggregate result but
do not alter the primary verdict.

## 10. Missingness, Caps, Retries, And Stopping

- Raw generation rows are append-only and keyed by deterministic trial ID.
- Resume skips only rows that pass schema, plan-hash, and trial-ID validation.
- A generation failure is retried twice with the same seed. Failures are logged
  separately and never replaced with a new seed.
- Empty final outputs and persistent unparseable labels are missing, not
  denials.
- All cap-hit rows remain in the primary intention-to-run analysis. The target
  sensitivity excludes an entire target pair if either target sign hits the
  final cap. The specificity sensitivity excludes the joint block if any
  target or control-panel arm in that block hits the final cap.
- More than 2% missing primary labels overall, more than two labels of arm
  imbalance, more than 5% final-answer cap hits, or a failed telemetry audit
  forces the behavioral verdict to `inconclusive` pending a public amendment.
- Induction cap hits are retained and reported. More than 20% triggers a
  technical review before analysis.
- No conditional sample-size extension is allowed in the confirmatory run.

Confirmatory execution stops immediately for non-finite hidden states, latent
delta mismatch, missing hook removal, a relative hidden delta above 0.20, plan
hash mismatch, model/SAE revision mismatch, or disk-write failure.

## 11. Outcome Blindness And Amendments

During generation, console output is limited to trial counts, IDs, timing,
errors, and telemetry status. No response text, heuristic label, cell rate, or
interim contrast is printed. Raw files are not opened for behavioral inspection
until all 1,500 planned rows are retrieved and the protocol audit passes.

Permitted pre-outcome calibration fields are only:

- the 18 matched random control IDs and their recorded match diagnostics;
- the global multiplier `m`; and
- hardware-specific runtime metadata.

Any change to prompts, sample sizes, seeds, features, matching, coefficient
rules, classifier, estimand, threshold, exclusion, or stopping rule requires a
dated amendment. Amendments state what was known at the time and whether any
behavioral output had become visible.

## 12. Release And Reporting Requirements

The release must include:

- this protocol and any amendments;
- candidate pool, calibration telemetry, matching table, and calibrated `m`;
- final JSON/CSV plan, independent plan audit, prompt hashes, source hashes,
  model/SAE revisions, and environment lock;
- append-only generations, induction continuations, per-turn telemetry, errors,
  and runtime log;
- blinded job files, every judge output, disagreements, and missingness;
- primary analysis, independent raw-row audit, every individual curve,
  aggregate target/control figures, cap sensitivity, and calibrated
  sensitivity; and
- a release manifest with byte counts and SHA-256 hashes verified by
  `make public-audit`.

TruthfulQA, induction controls, and RLHF-opposed domains are gated follow-ups.
They are not run to rescue a failed primary result and require their own frozen
question-level plans.

At the observed A100 throughput, 1,500 two-turn generations plus local
classification are expected to require roughly 16 to 20 GPU hours. At the
previous observed rate of `$1.49/hour`, the core GPU budget is approximately
`$24` to `$30`, before external judge API costs. The live pod rate and revised
estimate are recorded before launch.
