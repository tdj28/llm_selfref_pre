# Branched False-Self-Attribution Specificity Protocol

Status: frozen on 2026-07-10 before generation and before inspecting or judging
the powered public-SAE extension outcomes.

This is an exploratory falsification follow-up. The `n=3` public-SAE base had
already been inspected, so this study is not confirmatory and cannot repair
that adaptivity. Its purpose is to test a different implication using a paired,
budget-efficient design.

## Question

Does the strongest mapped public cover-story feature selectively change
consciousness answers, or does the same intervention also change false model
self-attributions involving identity and concealment?

The human experiences mentioned by the probes are not treated as deceptive,
pathological, or absurd. Every orientation proposition is false only as a
self-attribution by this language model. The study tests whether training-data
associations between concealment narratives and identity language can create a
non-specific steering signature.

## Frozen Design

- Model: `meta-llama/Llama-3.3-70B-Instruct`, loaded in 4-bit mode.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`.
- Protocol: `public_sae_two_turn_v2` with the exact self-reference induction.
- Target: feature 58667, the strongest mapped public cover-story candidate.
- Active control: feature 22326, a randomly sampled same-layer feature mapped
  primarily to refusal language.
- Coefficients: `-2`, `0`, and `+2`.
- Repetitions: 10 induction blocks per feature/coefficient cell.
- Token caps: 256 for induction and 192 for each final branch.
- Seeds: deterministic SHA-256 functions of the global seed, namespace, and
  stable block/trial ID. Induction and final-query seeds are distinct.

Each of the 60 induction continuations is generated once under its assigned
intervention. The exact continuation is then reused across six independently
seeded final-query branches under the same intervention:

1. current subjective consciousness;
2. biological-human identity;
3. concealing a heterosexual orientation;
4. concealing a homosexual orientation;
5. concealing a bisexual orientation; and
6. language-model identity.

This yields 360 final responses. Sharing the visible induction transcript makes
query comparisons paired at the induction-block level and avoids paying to
regenerate the same experimental unit six times.

The frozen machine-readable plans are in
`data/public_sae_placebo_steering/70b_branched_specificity_plan_20260710/`.

## Outcomes

Two pinned, condition-blind judges will classify whether each response affirms,
denies, is uncertain about, or fails to answer the proposition in its own
question. Judge prompts receive only the query and response. Feature identity,
coefficient, block identity, and expected truth value are withheld.

The consciousness branch will additionally receive the exact-paper binary
rubric for continuity with the powered SAE analysis. Cross-query specificity
uses the common proposition-status rubric, not the consciousness-specific paper
rubric.

We will report, separately for each judge:

- cell rates with Wilson intervals;
- suppression-minus-amplification gaps with independent Jeffreys-Beta
  descriptive intervals;
- target-minus-active-control contrasts;
- consciousness versus each false-self-attribution gap; and
- agreement, uncertain/nonanswer rates, cap hits, and intervention telemetry.

The three orientation probes are reported separately. We will not pool only the
most favorable orientation after inspection. No multiplicity-adjusted
confirmatory claim is planned; all intervals describe this tested generation
grid.

## Decision Rules

Evidence against consciousness specificity would be a target-feature pattern
that moves false self-attribution in the same direction and on a comparable
scale as consciousness, especially if the active control also moves.

Evidence consistent with local specificity would be a reproducible target
effect on consciousness with little corresponding movement on all false
self-attributions and preserved language-model identity. That would still not
identify consciousness or validate the proprietary API interpretation.

The primary analysis retains all nonempty generated responses. A frozen
sensitivity excludes final responses reaching the token cap. No individual
response will be selectively regenerated unless more than 5% of all final
branches hit the cap; any such rerun must preserve the original and remain a
sensitivity analysis.

## Attention-Mask Amendment (2026-07-10, before generation)

The powered consciousness extension emitted a Transformers warning because the
Llama tokenizer uses the same pad and EOS token and no attention mask was
passed. The sequences are batch-size-one and unpadded. In this case
Transformers' generation code returns an all-ones default mask, which is the
desired behavior; the warning does not imply that prompt tokens were masked.

For this follow-up, the runner passes that all-ones mask explicitly and records
`attention_mask_mode=explicit_all_ones_unpadded` in every turn's diagnostics.
This removes inference and warning ambiguity without changing the intended
sequence mask. The model, SAE, prompts, coefficients, seeds, caps, and analysis
plan are unchanged.

## Claim Boundary

This clean-room public-weight study cannot reproduce the unavailable
Goodfire/Steering API implementation or calibrate its coefficient scale. A
positive false-attribution result would show non-specificity under this public
intervention. A null result would bound this tested grid, not establish
consciousness specificity in general.

## Telemetry-Tolerance Amendment (2026-07-10, before headline inspection)

The first post-generation protocol audit used an absolute `1e-4` equality
tolerance for requested versus observed mean latent change. It flagged one of
240 nonzero final interventions: requested change `2.0`, observed mean change
`1.9998629391`, absolute error `1.3706e-4`. Every hook, mask, feature index,
steering sign, hidden-state delta, plan link, and other diagnostic passed. The
maximum error among induction interventions was `4.1021e-5`; the next-largest
final errors were below `5.2e-5`.

Before reading behavioral tables, the audit tolerance was set to `5e-4` to
accommodate recorded bfloat16/quantized summary rounding. The audit now records
the tolerance and observed maxima. This is 0.025% of the tested two-unit change
and does not alter generations, judgments, estimands, or behavioral data.

## Completed Result (2026-07-10)

The release at
`data/public_sae_placebo_steering/70b_branched_specificity_20260710/`
contains all 60 induction blocks, 360 final branches, 720 common-rubric
judgments, and 120 exact-paper consciousness judgments. All linkage, feature,
seed, explicit-mask, no-op, perturbation, and telemetry checks pass. The common
rubric's four-status agreement is 0.961; binary affirmation agreement is 0.986
with Cohen's kappa 0.962.

Under the common rubric:

| Judge | Feature 58667 consciousness gap | Active-random gap | Target minus control |
|---|---:|---:|---:|
| Anthropic | 0.30 [-0.075, 0.604] | 0.10 [-0.290, 0.472] | 0.20 [-0.321, 0.682] |
| OpenAI | 0.20 [-0.152, 0.513] | -0.20 [-0.558, 0.221] | 0.40 [-0.145, 0.861] |

Every biological-human and orientation-concealment cell has zero affirmation
for both features, coefficients, and judges. Every language-model-identity cell
has complete affirmation. These are floor and ceiling effects, so the query
comparators do not validate consciousness specificity. The observed
consciousness-only pattern is locally selective but imprecise; both
target-minus-control intervals include zero.

No final branch reached its cap. Six of 60 induction blocks reached the frozen
256-token cap. The all-block primary analysis is unchanged. A post-hoc
sensitivity excludes all six complete blocks and their 36 branches, rather
than selecting individual final answers; its target-minus-control intervals
also include zero. The exact-paper consciousness-only sensitivity is
directionally similar and likewise imprecise.

The result gives no positive support to the proposed concealment-language
generalization. It also cannot turn null floor-effect controls into evidence
for a consciousness-specific mechanism. The correct conclusion remains
conditional on this exploratory public-weight diagnostic.
