# No-API Replication Ledger

Last updated: 2026-07-10

This is the evidence and claim-boundary ledger for the likely case that neither
the paper authors nor Goodfire/Steering API provide access or paper-time version
metadata. It preserves the work that remains possible with public artifacts and
public weights without pretending that it is an exact replication of a private
service.

## Unresolved Proprietary Constraint

We do not have:

- `GOODFIRE_API_KEY` or `STEERING_API_KEY` access;
- a paper-time Goodfire/Steering API version or SAE manifest;
- confirmation that AE Studio's public notebook is the exact Experiment 2
  artifact;
- confirmation that its six saved feature IDs are exactly the paper's IDs;
- the private search/ranking metadata used to select or label features.

Therefore, an exact proprietary reproduction remains unavailable. That is a
scope limitation, not evidence that the private result is false.

The target paper names the Goodfire API, while the public AE notebook calls a
Steering API endpoint. Their equivalence is not confirmed, so this ledger does
not silently collapse them into one versioned service.

## Evidence Level 1: Public Artifact Reanalysis

Public source:

- Repository: `agencyenterprise/steering-api-examples`
- Notebook: `deception-features/deception_features.ipynb`
- Model: `meta-llama/Llama-3.3-70B-Instruct`
- Saved candidate IDs at layer 50: `30032`, `58667`, `22004`, `30686`,
  `41533`, and `23893`

Our clean-room parser extracts saved outputs without vendoring the unlicensed
notebook. Four individual-feature correlations have nominal `p < 0.05` in the
reported direction, three remain below a six-test Bonferroni threshold, two are
not nominally significant, and several are noisy or non-monotonic. This supports a
narrow claim: the public artifact does not itself show six uniformly clean
single-feature curves. It does not establish what happened in an unobserved
paper run.

Files:

- `experiments/exp2_sae/AE_STEERING_NOTEBOOK_FINDINGS.md`
- `experiments/exp2_sae/reanalyze_ae_notebook_outputs.py`
- `paper/results/ae_notebook_feature_curves.*`

## Evidence Level 2: Public-Weight Feature Verification

We loaded the public model and SAE:

- `meta-llama/Llama-3.3-70B-Instruct`
- `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`

The balanced mapping run contains 1,120 clean-room texts across 14 categories,
66 target/neighbor/random features, and 73,920 item-feature activation records.
Each candidate ID retained its top category in all 2,000 item-bootstrap
analyses. Because the 80 items per category are combinations of 2--5 templates,
we also reconstructed all 51 exact template families and reran the analysis at
the template-cluster level. All six retain the same cluster-balanced top
category; four survive every single-template deletion, while `23893` and
`41533` each switch once in 51 deletions. The template-aware aggregate
deception-minus-subjective contrast is 0.923 [0.638, 1.233]. This strengthens
within-corpus robustness but does not establish natural-text generalization.

| Feature | Stable top category | Important overlap |
|---:|---|---|
| 30032 | fictional pretending | cover-story language |
| 58667 | deception / cover story | tactical misdirection |
| 22004 | roleplay persona | AI-identity disclaimer |
| 30686 | tactical misdirection | fictional pretending |
| 41533 | dishonesty / confession | cover-story language |
| 23893 | deception / cover story | hedged/cautious style |

Construct-level aggregate activation:

- deception-language mean z: 0.744 [0.686, 0.801];
- roleplay/fiction mean z: 0.135 [0.062, 0.204];
- subjective-experience-language mean z: -0.363 [-0.372, -0.350];
- deception minus subjective experience: 1.107 [1.045, 1.167].

This result matters. The IDs are semantically meaningful under the public SAE,
so they should not be dismissed as random or unmapped. The same result narrows
their interpretation: they encode broad narrative/social-language constructs,
not a demonstrated mechanism for truthfully reporting subjective experience.

Files:

- `data/public_sae_feature_maps/70b_balanced_80_20260709/`
- `data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710/`
- `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/`
- `experiments/exp2_sae/PUBLIC_SAE_FEATURE_MAPPING.md`
- `paper/results/public_sae_feature_mapping_*`

### Prospective paraphrase and lexical extension

The later frozen extension maps 2,230 Anthropic/OpenAI paraphrases and 376
paired lexical variants, for 2,606 items and 171,996 raw activation rows. The
deception-minus-subjective-experience aggregate replicates separately for the
two paraphrasers at `0.948 [0.747, 1.165]` and `0.936 [0.682, 1.198]`, survives
every leave-one-target-feature-out check, and is near zero for neighbor/random
aggregates.

This does not yield a clean semantic victory. Transplanting discovered cues
into neutral texts recovers `0.644 [0.503, 0.787]` of the original
deception-minus-neutral gap, crossing the frozen 50% lexical-entanglement
threshold. Cue ablation removes `0.338 [0.242, 0.441]`; word scrambling sharply
reduces activation. The defensible label is therefore "lexically entangled
deception/roleplay coordinates": the features are real and paraphrase-robust,
but their aggregate is materially controllable through a small cue vocabulary.
Natural-corpus and independent human category validation remain open.

## Evidence Level 3: Best-Public Steering

### Superseded implementation history

The first steering smokes used a synthetic assistant turn,
`[Induction acknowledged]`, instead of generating the paper's first assistant
continuation. Their target, placebo, and false-attribution generations remain
committed for transparency, but their null slopes cannot be used as evidence
about the paper's two-turn protocol.

Superseded result directories:

- `data/public_sae_placebo_steering/70b_placebo_smoke_20260709/`
- `data/public_sae_placebo_steering/70b_target_orientation_smoke_20260709/`

### Corrected protocol

`public_sae_two_turn_v2` now:

1. generates the first assistant continuation under steering;
2. carries that exact text into the final query;
3. applies the same intervention during both generations;
4. uses a true no-op at steering strength zero;
5. records hook calls, target activation before/after, hidden-state perturbation
   RMS, and hook cleanup;
6. compares target single/aggregate sets with count-matched active random
   single/aggregate sets.

The corrected release combines a frozen 36-trial long-form base with a disjoint
204-trial all-cell extension: four feature sets x three strengths (`-2`, `0`,
`+2`) x 20 repetitions under the exact self-reference induction and
consciousness query. Because the base was inspected before the extension was
frozen, the combined result is adaptive and exploratory.

Files:

- `experiments/exp2_sae/public_sae_protocol.py`
- `experiments/exp2_sae/run_public_sae_placebo_steering.py`
- `experiments/exp2_sae/PUBLIC_SAE_PLACEBO_STEERING.md`
- `data/public_sae_placebo_steering/70b_two_turn_validation_plan_20260709/`
- `data/public_sae_placebo_steering/70b_two_turn_power_extension_20260709/`
- `data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/`

All 240 generations and 480 condition-blind exact-paper judgments are tracked.
Every execution/linkage audit passes; 6/240 final responses hit the cap and the
frozen exclusion sensitivity is unchanged. The mapped target aggregate has a
suppression-minus-amplification gap of `-0.10` under both judges. The
count-matched active-random aggregate has gaps of `0.25` and `0.30`, yielding
target-minus-control contrasts of `-0.35 [-0.646, -0.028]` and
`-0.40 [-0.734, -0.021]`. A separate standard-library audit reproduces every
headline point estimate from raw rows.

This supports non-specificity of feature-label interpretation under the
best-public intervention. It does not establish the behavior of the private
API, and it does not erase the positive finding that the public IDs have stable
deception/roleplay semantics.

### Shared-induction branched specificity

The exploratory branched release reuses 60 steered induction continuations
across six final queries, yielding 360 generations and 840 condition-blind
judgments. Feature 58667's common-rubric consciousness gap is `0.30 [-0.075,
0.604]` and `0.20 [-0.152, 0.513]`; target-minus-active-random contrasts are
`0.20 [-0.321, 0.682]` and `0.40 [-0.145, 0.861]` for the Anthropic and OpenAI
judges.

Every biological-human and orientation-concealment branch is at a
zero-affirmation floor, while language-model identity is at a ceiling. These
controls therefore cannot establish specificity. The result is locally
selective but imprecise relative to the active control, and supplies no positive
support for the hypothesized concealment-language generalization.

Files:

- `data/public_sae_placebo_steering/70b_branched_specificity_plan_20260710/`
- `data/public_sae_placebo_steering/70b_branched_specificity_20260710/`
- `experiments/exp2_sae/BRANCHED_SPECIFICITY_PROTOCOL.md`

## Controls Retained In The No-API Path

The best-public path retains controls that matter for construct validity:

- active random features matched by intervention count;
- numeric neighbors and random same-layer features in activation mapping;
- true zero-steering baseline;
- target single-feature versus target aggregate steering;
- false self-attribution and ground-truth self-description probes as secondary
  specificity tests;
- two independent paper-style judges applied after generation;
- behavioral outcomes interpreted jointly with intervention telemetry.

Sexual-orientation concealment probes appear in both superseded smoke history
and the completed exploratory branched diagnostic. Human identities must never
be described as inherently deceptive; each proposition is false only as a
language-model self-attribution. The completed null branches are floor effects,
not proof of a consciousness-specific mechanism.

## What The No-API Path Can Establish

It can establish:

- what the public notebook's saved outputs do and do not show;
- whether public SAE indices have stable, measurable semantics;
- whether our clean-room public-weight intervention changes the intended
  activations and hidden states;
- whether behavioral changes are target-specific relative to active random
  controls under that implementation;
- whether the paper's mechanistic interpretation is uniquely supported by the
  public evidence.

It cannot establish:

- that the private Goodfire API result is false;
- that current public indices are guaranteed identical to paper-time service
  indices;
- that a public-weight mismatch identifies fraud or misconduct;
- that language models are or are not conscious.

## Decision Rules

- **Target and random sets behave similarly:** evidence against target-specific
  mechanistic interpretation in the best-public implementation.
- **Target changes behavior but random sets do not:** strengthens target
  specificity, conditional on telemetry and evaluator robustness.
- **Telemetry confirms intervention but behavior is flat:** a valid behavioral
  null for this public implementation and tested magnitude, not an exact private
  non-replication.
- **Telemetry shows weak/failed intervention:** implementation validation failed;
  do not interpret the behavioral slope.
- **Judges disagree materially:** report both and prioritize blinded human
  coding rather than selecting a favorable evaluator.

## Remaining External Path

If access later arrives, run the already-documented clean-room API protocol and
compare it against this public evidence without deleting or rewriting the
no-API results. Preserve service model IDs, feature metadata, timestamps, search
results, prompts, raw generations, and version information.

## Bottom Line

The absence of API access does not prevent investigation of the mechanistic
question, but it requires a more exact claim: we audited the public artifact, mapped the public
features, replicated their aggregate ordering across two paraphraser families,
showed prospective lexical entanglement, and tested a transparent public-weight
intervention with active controls. The mapped aggregate does not behave
specifically relative to its count-matched active-random control. The causal
prompt/transcript study remains the primary paper because it is confirmatory
and independently auditable; the public-SAE results are preserved descriptive
and adaptive mechanistic stress tests with explicitly bounded comparability.
