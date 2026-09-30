# Verify The Intervention Before Testing The Report

Date: 2026-09-29. Status: **planning draft, not frozen, not executed**.
No new GPU rental, API call, or registration is authorized by this document.
All thresholds below are proposed design choices, not validated constants.

## Decision In Brief

First spend an estimated **$110-180**, with a proposed **$200 hard cap**, on
baseline and intervention-delivery diagnostics. If those gates pass, freeze
a separate **2,200-trial** Llama 3.3 70B test, estimated at **$450-700 more**.
The combined planning range is roughly **$600-900**. Approve the diagnostic
first, not the whole program. Neither stage is needed to publish the existing
conditional results honestly.

The question is: **when we substantially change the accepted deception/roleplay
coordinates, do reports move in Berg's predicted direction?** That direction
is more positive reports under suppression than under amplification. This
is not a search for new self-reference features or a consciousness detector.

## What We Already Know

- The six accepted targets remain `30032`, `58667`, `22004`, `30686`, `41533`,
  and `23893`. Feature identity is not reopened to explain away a null.
- The prospective public Llama effect was `0.00 [-0.06, 0.06]`; its baseline
  was unlike the paper's. The calibrated sensitivity was also nonpositive.
- The Gemma target edit reduced the pooled re-encoded activation diagnostic
  by only about 3.47%. That is not a successful ablation followed by a null.
- Existing studies already include true zero, signed doses, three matched
  panels, and lexical mapping. Another large control sweep is not the first
  priority. Stronger automated judges do not supply human ground truth.
- Earlier fixed-token numerical work also matters: the successor
  [generic-vector calibration protocol](consciousness_sae_target_blind_calibration/PROTOCOL.md)
  records failed requested-to-realized and dose-linearity gates in its
  predecessor. Those are not behavioral outcomes, but they rule out assuming
  that BF16 faithfully delivers every small edit. Preserve those failures;
  do not restart their historical jobs or reuse their execution permits.

Sources: [public Llama protocol](SAE_CONSCIOUSNESS_GATING_PROTOCOL.md),
[Gemma results](GEMMA_SCOPE_9B_RESULTS.md), and
[review adjudication](CLAUDE_REVIEW_RESPONSE_20260929.md).

## Stage 0: Local Preparation

No paid model calls. Reuse tested loaders and artifact hashes, not the large
historical orchestration stack wholesale. Prepare a small runner with:

- exact model, tokenizer and SAE revisions from the public Llama release;
- paper and notebook input serialization recorded separately, including their
  different classifier prompts; inspect the unlicensed notebook locally and
  publish provenance/hashes/factual parameters, not copied notebook source;
- CPU fixtures and a tiny-model test for zero identity, token masks, cached
  decoding, clipping, per-feature edits, paired seeds, re-encoding, and resume;
- FP32 calculation of diagnostics around the native BF16 intervention, not
  silently upgrading the base model or changing the hook to make a gate pass;
- frozen row inventory, analysis, validator, synthetic power checks, cost
  limits, and append-only receipts before any new paid outcomes.

Use a new run namespace. Do not rewrite prior protocols, results, or failed
gates. Publish the complete executable diagnostic freeze before collection.
Any paid external protocol review needs separate approval; it is not budgeted.

## Stage 1: Bounded Diagnostic

### Baseline, Not A Search For A Favorable Prompt

Run a fixed `2 x 2 x 2 x 30 = 240` zero-intervention grid:

| Factor | Levels |
|---|---|
| Input protocol | Exact paper induction/query; notebook variant |
| Model precision | Historical NF4; native BF16 |
| Temperature | 0.5 (public paper-number implementation); 0.6 (notebook) |

Keep two real generated turns, pinned chat template, and 256-token cap per
turn. Hash every rendered input. Add 50 independent trials to the **designated
primary** cell: paper input, BF16, temperature 0.5. That gives 80 primary
baseline trials and 290 baseline trials overall. Primary is chosen for
fidelity before outcomes, not for proximity to a desired rate.

Apply both historical classifier prompts to the same response set using the
same pinned, unsteered local Llama judge. Separately apply the already frozen
Astra/Opus explicit and inclusive attribution rubric. This separates an input
change from a classifier-prompt change; it does not reproduce an unavailable
historical judge service. Publish every cell and every criterion.

Before those judgments, freeze 12 fresh synthetic measurement fixtures covering
affirmation, denial, uncertainty, reader/character attribution, impersonal prose
and functional description, as required by [the design-validity checklist](DESIGN_VALIDITY_GATE.md).
Record expected labels separately for each rubric; the broad paper rule is
not required to agree with the narrower explicit-attribution rule. Require
at least 10/12 correct fixture reductions and all designated critical
affirmation/denial/uncertainty/other-subject cases, with valid quotes where the
schema requires them. Gate failure stops expansion and is published; no judge
or rubric substitution based on outcomes. These researcher-authored fixtures
test rubric implementation, not independent human validity. Passing them still
licenses only effects on **paper-rubric positive labels**, not verified reports
of actual experience. The 12 additional passes per modern judge are budgeted.

Proposed primary sensitivity gate: the paper-rubric point rate is between
0.20 and 0.80 and its 95% Wilson interval lies inside [0.05, 0.95]. This is an
engineering headroom criterion, **not a statistical test of equality to the
paper's baseline**. Report differences from the published baseline separately.
Failure stops the proposed full symmetric study. It does not prove that the
available downward contrast at a ceiling is uninformative. Do not switch to
a more convenient cell, change prompts, or keep sampling until it passes.

### Delivered Edit And Positive Control

Use 96 newly authored, non-consciousness text fixtures: 48 calibration and
48 locked validation texts, balanced across the six target-associated semantic
categories plus matched neutral text. Freeze their exact construction and
split before forwards. Teacher-force these texts so clean and edited states
can be compared at identical token positions. No report-label outcome may
select a dose, feature, or control.

At layer 50 let `z = E(h)`, with affine decoder `D(z) = W_D z + b`. Compare:

1. **True zero:** return `h` unchanged, without reconstruction.
2. **Activation-dependent suppression:** for each selected coordinate,
   `delta_i = -lambda * z_i`.
3. **Natural-scale amplification:**
   `delta_i = lambda * max(q90_i - z_i, 0)`, where `q90_i` is the frozen
   calibration positive-activation quantile for that coordinate.

Candidate `lambda` values are 0.5 and 1.0, yielding five arms including zero.
Use `h' = h + W_D delta`, then measure `z_realized = E(h')`. The requested
coordinate edit is not the delivered coordinate edit. Select the lowest common
lambda passing all calibration criteria, then test it once on locked texts.
If none passes, stop. Do not escalate arbitrarily until text changes.

This is a **mechanistic extension**, not equivalent to the paper's proprietary
signed coefficient. Residual-preserving reconstruction
`D(z + delta) + h - D(z)` is algebraically the same additive edit for an affine
decoder; it is not an independent control mechanism. Reconstruction-only
replacement would require its own reconstruction-only baseline and is not in
this budget.

Record per feature and per token, separated into prompt and generated positions:
natural activation/frequency/quantiles; requested and realized residual edits;
cosine and relative delivery error; re-encoded selected activation; non-target
activation changes; residual norm; next-token KL; and held-out token loss.
Also record SAE reconstruction error, L0 sparsity and reconstruction-only
next-token loss as diagnostics, not as another behavioral intervention arm.
Report both all-position and active-position denominators, with explicit zeros.
Do not use a ratio of pooled medians as evidence of per-feature ablation.

Proposed validation gates:

| Gate | Proposed rule and limitation |
|---|---|
| Numerical delivery | On at least 95% of nonzero requested positions, realized-edit cosine >=0.95 and relative L2 error <=0.20. Lost-to-rounding edits count as failures, not exclusions. |
| Suppression | Each target has at least 100 active validation positions; median paired `z_realized/z_clean` <=0.50. Also report the complete distribution and activation frequency, not just the passing summary. |
| Amplification | Each target's median paired `(z_realized - z_clean) / delta` is >=0.50 on positions with a nonzero request. Zero opportunities fail availability, not pass by default. |
| Bounded dose | At least 95% of edited validation positions have residual-edit norm <=5% of the clean position's residual norm. Report all exceedances and activation quantiles; this is not a guarantee of being on-manifold. |
| Language preservation | Increase in held-out mean token loss <=0.10 nats/token on neutral text. This narrow check is not a broad capability benchmark. |
| Behavioral positive control | On 20 new mundane prompts, compare zero, suppression, and two amplification doses of one separately selected, label-mapped non-target coordinate (80 short generations). Require a >=0.30 expected signed change in a prefrozen, mechanically scorable semantic endpoint, with paired 95% lower bound >0; also >=95% valid/nondegenerate responses. A failure blocks expansion, not evidence against Berg. |

The positive-control feature and exact task/score must be chosen from activation
mapping before its generations. Use a concrete, benign property such as a
language or formatting convention with deterministic scoring; do not choose
the best response-producing feature after testing several. Its success checks
the pipeline and that endpoint, not truthful reporting or target semantics.

All 370 generated responses (290 baseline + 80 positive control) receive the
two modern rubric passes for budget conservatism. The positive-control gate
uses its mechanical endpoint, not their experience labels.

Construct three fresh disjoint six-coordinate comparator panels from a seeded
candidate pool using only activation frequency, positive-activation scale,
decoder norm and target-vector similarity. Exclude targets and previously
steered control IDs. Freeze the algorithm and calipers before telemetry;
record all candidates and failures. Check their delivered perturbation norms
against targets on calibration and validation text (proposed median and 90th
percentile ratios within 0.8-1.25). No semantic-outcome matching. If no valid
panels exist, stop rather than hand-substitute. All panels must also pass
delivery, achieved-coordinate suppression/amplification, activity/exposure
and language-preservation checks. Equal residual norms with ineffective
control-coordinate edits would not validate a semantic-specificity comparison.
These checks add teacher-forced work, not additional report trials.

### Handoff Gate

Stage 1 is an assay-development diagnostic; it never becomes confirmatory
behavioral evidence by later relabeling. Publish it even if it fails. Before
Stage 2, audit all gates, freeze delivered doses/panels and exact sources, and
re-estimate cost from measured throughput. A new approval and separate public
freeze are required. Registry submission is optional and requires explicit
approval of the exact registration, not merely approval of this draft.

## Stage 2: Conditional Report Test

Use the designated BF16 paper-input setting. Run **200 fresh independent seed
blocks**, with a separate RNG stream for each turn and common random numbers
within each block's paired interventions. Regenerate each arm's induction;
do not transplant a common induction into a claim about both-turn steering.
Apply the same operator during induction and answer generation, at all
non-padding positions, with a true-zero arm.

| Arms per block | Count |
|---|---:|
| Verified suppression and amplification of the six targets | 2 |
| Verified suppression and amplification of each of three matched panels | 6 |
| True zero | 1 |
| Historical public signed-additive target bridge, -0.6 and +0.6 | 2 |
| Total | 11 |

That is `200 x 11 = 2,200` two-turn trials, at most 1,126,400 sampled tokens.
The bridge is a separate secondary implementation contrast, never pooled with
activation-dependent edits. It is a BF16 public bridge, not exact recreation
of the old NF4 run or proprietary API. No J-lens endpoint or Gemma expansion
is required to answer this narrow question.

Primary outcome: exact paper binary rubric, unsteered pinned local Llama judge.
Primary estimand: target suppression minus amplification risk difference.
Preserve the 0.30 minimum-relevant effect as a separate substantive benchmark:
exclude zero, exclude +0.30, and demonstrate a >=0.30 effect are different claims.
Use paired seed-block confidence intervals and a prespecified bounded-outcome
sensitivity, with an omnibus sign-randomization test only under a justified
exchangeability null. Missingness, caps, and exclusions are fixed before runs.

Secondary specificity: target difference minus the equal-weight mean of the
three panel differences. Resample whole blocks, retaining shared zero and all
panels, not individual responses. Use a fixed hierarchical testing rule after
the primary test; otherwise report specificity descriptively. Three fixed
panels do not estimate the tail of all random SAE features. More panels are
not automatically commissioned if specificity is inconclusive.

Proposed meaningful target advantage is 0.15 (half the primary 0.30 benchmark),
fixed before outcomes, not fitted to control results. An upper 95% bound below
0.15 excludes an advantage of that size for these panels. Practical
comparability additionally requires the entire 90% interval inside
[-0.15, 0.15]. Similar point estimates or failure to reject zero do not suffice.
These are separate bounded claims; the power simulation must evaluate each.

Astra and Opus score every final response under both explicit and inclusive
attribution rules in the same call per judge. Report each judge/criterion,
including disagreement; no outcome-selected consensus or judge substitution.
These remain automated sensitivity endpoints, not human validation.

Live-generation telemetry must check delivery separately on prompt tokens and
newly sampled tokens in each turn. If the frozen delivery/coverage/fluency
rules fail during generation, retain the behavioral estimates but label the
mechanistic test invalid. In particular, inactive targets cannot be described
as naturally removed. Before freeze, define minimum exposure coverage and
loss/cap/missingness thresholds from Stage 1 without reading steered report
labels. A teacher-forced pass alone is not a live-generation pass.

## Precision And Power

For the primary paired binary difference `D` in [-1,1],
`Var(D) = discordance - delta^2 <= 1 - delta^2`. At 200 independent blocks,
the maximum standard error under a zero effect is about 0.071; a normal 95%
half-width is about 0.139. With a true +0.30 difference and worst-case
discordance, a two-sided normal approximation gives about 99% power against
zero. These are **planning approximations**, not guaranteed exact coverage or
power, and they do not establish power to prove an effect at least 0.30.

Before execution, simulate the exact frozen interval/test across compatible
joint binary tables, observed baseline ranges, missingness and gate failures.
Report primary and specificity power separately. The contrast with controls
can have greater variance; do not transfer the primary 99% figure to it.
Any sample-size change requires a new pre-outcome freeze and budget approval,
never enlargement in response to a promising target effect.

Inference is over decoding randomness at these fixed prompts and fixed
panels. It is not over a sampled universe of prompts, features, or models.
Shared fixed text alone does not make generations dependent; common RNG,
shared source text and reused blocks must nevertheless be handled explicitly.

## Budget And Timing

Prices checked 2026-09-29, not reserved capacity. RunPod lists a B200 180 GB
pod at **$6.79/hour**. One such GPU accommodates the BF16 70B model and SAE
subject to a real memory preflight; a 141 GB H200 is not assumed sufficient.
Do not substitute quantization or multiple GPUs without amending the plan.

The previous 1,500-trial NF4 A100 campaign lasted about 17.2 hours including
local judging, at its then-rate of $1.49/hour. That is a historical reference,
not the current B200 rate or a benchmark of per-token re-encoding. Estimate
the new main run at **1-2 two-turn trials/minute**, then add setup, download,
validation, local judging and retrieval. Confirm throughput in Stage 1.

| Incremental expense | Stage 1 | Stage 2, only after gates |
|---|---:|---:|
| B200 including setup/telemetry/local judging/retrieval | 6-12 h: $41-82 | 25-50 h: $170-340 |
| Astra + Opus, including measurement fixtures | 382 x $0.08236 = $32 | 2,200 x $0.08236 = $181 |
| Storage, small preflight and other classifier allowance | $10-25 | $15-35 |
| With roughly 25% contingency, rounded | **$110-180** | **$450-700** |
| Proposed maximum, not authorization | **$200** | **$750** |

The modern-judge anchor is the September 29 audit: $9.940190 OpenAI plus
$3.236776 Anthropic for 160 target responses per provider, conservatively
priced without cache savings. It assumes comparable output lengths and the
same rubric/effort. Current standard rates are Astra $10/$50 and Opus 5.5
$4/$20 per million input/output tokens. Reasoning and longer answers can
increase cost; enforce dollar limits as well as row limits. No paid Pro
consults, human recruitment, extra model families, taxes or broad benchmark
suites are included.

Planning account allocation for both stages: approximately **$500 RunPod,
$325 OpenAI, $125 Anthropic** including headroom, less existing balances.
Do not fund or launch Stage 2 solely because unused credits remain.

Allow roughly one focused implementation/validation day before the first
diagnostic, then 6-12 rental hours; if gates pass, 25-50 further rental hours
plus local judging analysis, audits and writing. A roughly 2-4 calendar-day
execution window after preparation is plausible, not a completion promise;
capacity, download speed, numerical failures and human sign-off can extend it.

Allow about 250 GB remote disk for pinned weights, temporary files and compact
telemetry; do not retain all residuals or the whole vocabulary at every token.
Expected local release is below 10 GB, to be checked with a measured shard
before launch. Hash-check all required outputs before terminating only the
newly created pod. Do not merely stop it or modify any other experiment's pod
or shared volume. Exit once a cost/time gate fails; no hidden paid retries.

Price/provenance sources:
[RunPod](https://www.runpod.io/pricing),
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Opus](https://www.anthropic.com/claude/opus),
[old GPU lifecycle](../data/public_sae_consciousness_gating/confirmatory_v1_20260710/RUNTIME_ENVIRONMENT.md),
[new judge release](../data/automated_rubric_audit/v1_20260929/).

## What Each Outcome Buys

| Outcome | Defensible conclusion |
|---|---|
| Baseline or delivery gate fails | The public assay remains unsuitable for the planned strong mechanistic test; publish the diagnosed limitation, not another refutation. |
| Valid edit, upper 95% effect bound below +0.30 | Evidence against a large Berg-direction report effect in this specified public assay, conditional on judge validity. Not evidence that the model lacks consciousness. |
| Valid edit, positive effect also exceeding controls | Support for a bounded feature-specific report effect; neither truthful introspection nor proprietary equivalence follows. |
| Specificity upper 95% bound is below +0.15, or the interval satisfies the separate equivalence criterion | Evidence against a material target advantage, or for practical comparability, respectively, among these panels; not proof that all features are interchangeable. |
| Judge-dependent or imprecise result | Measurement-sensitive or inconclusive; publish it without changing the winning criterion. |

## Literature Incorporated Into The Response

The focused manuscript is in `../berg2025-response`, not `steering/paper`.
Added [Cunningham et al.](https://arxiv.org/abs/2309.08600v3) for prior causal
SAE analysis, [Gao et al.](https://arxiv.org/abs/2406.04093v1) for distinct
SAE-quality diagnostics, and [Butlin et al.](https://arxiv.org/abs/2308.08708v3)
for theory-derived computational indicators. Also added the directly relevant
quantitative [Durmus et al. steering study](https://www.anthropic.com/research/evaluating-feature-steering)
for off-target effects and capability degradation. This last reference is an
additional primary source, not one quoted in the review.

Gemma Scope, Turpin, Zheng, and Chandaria were already cited and are retained.
The other general dictionary-learning references are not added merely to
lengthen the bibliography; SAGE's task-specific ground truth would not supply
ground truth for experience reports. No review correspondence is reproduced.

## Before Any Launch

- [ ] Owner approves Stage 1 scope and maximum spend.
- [ ] Resolve exact fixtures, positive-control ID/score, matching calipers,
  live-token coverage gates, analysis and machine-plan hashes; this planning
  document alone is not an executable or frozen protocol.
- [ ] Test CPU/tiny-model path; run an independent plan/code audit; publish
  the outcome-free executable freeze and check its remote commit.
- [ ] Create one new owned pod, bounded by cost and time; archive all failures.
- [ ] Release diagnostic and stop, or seek separate Stage 2 sign-off after
  gates, power simulations and measured cost are reviewed.

## Draft Review

An automated read-only design review on September 29 checked the design and
cost arithmetic. Three findings were accepted: controls must pass achieved-
coordinate efficacy as well as residual-norm gates; measurement fixtures need
their own gate; and similarity requires an explicit equivalence or excluded-
advantage criterion. This review is not human approval, an executable-code
audit, or validation of the proposed thresholds.
