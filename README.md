# What Causes Language Models to Report Subjective Experience?

A multi-model causal stress test of the evidence in Berg, de Lucena, and
Rosenblatt (2025), ["Large Language Models Report Subjective Experience Under
Self-Referential Processing"](https://arxiv.org/abs/2510.24797v2), arXiv v2
(revised 2025-10-30).

This repository asks a narrower question than whether language models are
conscious: **which observable parts of the published protocol cause models to
produce text that an evaluator labels as a subjective-experience report?**

The project contains the experiment harness, frozen raw outputs, analysis code,
public-SAE feature verification, and LaTeX manuscript. It does not claim to
establish or exclude machine consciousness.

## Current Status

The confirmatory causal run is complete and tracked at
`data/causal_transplant/confirmatory_v1_20260709/`.

- 4 exact response-model snapshots: two OpenAI and two Anthropic.
- 480 independently sampled induction continuations.
- 2,560 final outcomes.
- 5,120 exact-paper binary judgments and 5,120 construct-separated judgments.
- Zero duplicate identifiers; four empty refusals are retained as missing.
- Design-aware bootstrap inference and a frozen 160-row complete-block human-coding first wave, disjoint reserve, and blinded expansion rule for the primary indirect-experience estimands; the full 640-row packet remains archived.
- An independent raw-row recomputation that matches all 16 headline point
  estimates across the two paper-style judges.
- An independent standard-library recomputation of all six public-SAE top
  categories and the aggregate 70B mapping point estimates.
- A preregistered 2,606-text construct-validity extension with dual-provider
  paraphrases, paired lexical counterfactuals, and an independent raw-row audit.
- A corrected 240-generation public-SAE steering release with 480 blinded
  paper-rubric judgments, complete intervention telemetry, cap sensitivity,
  and an independent raw-row headline audit.
- A 360-generation shared-induction branched-specificity diagnostic with 840
  condition-blind judgments and independently recomputed headline estimates.
- A prospectively frozen 1,500-generation public-SAE full grid with three
  matched control panels, 4,500 blinded exact-rubric judgments, complete
  telemetry, four publication figures, and an independent verdict audit.
- A prospectively frozen Gemma Scope 9B cross-model phase with 180 baseline
  generations, 830 causal generations, three blinded judge passes, direct-IT
  semantic maps, a failed PT-to-IT transfer gate, causal-relay telemetry, a
  separately labeled 42-layer exploratory atlas, 12 figure pairs, and an
  independent headline audit.
- A focused manuscript in `paper/main.tex`, compiled and visually audited from
  the tracked source and figures.

The public Goodfire SAE feature mapping and corrected two-turn public-weight
steering analysis are complete. Exact replication of the proprietary
Goodfire/Steering API workflow remains unavailable. Goodfire's legacy SAE
demo/API was deprecated in February 2026; the separately branded SteeringAPI
remains publicly reachable, but no public evidence establishes service,
feature-namespace, or paper-time version equivalence. See
[`docs/GOODFIRE_API_STATUS.md`](docs/GOODFIRE_API_STATUS.md).

## Public Writing

The first public article, [How to Read an SAE Feature
ID](https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html),
introduces the distinction between a feature coordinate, its semantic label,
and a causal steering claim. Its underlying balanced feature-map release is
pinned to repository commit
[`aadcf27`](https://github.com/tdj28/llm_selfref_pre/tree/aadcf27ca19d8a99ea53653efdb5463448fd858d/data/public_sae_feature_maps/70b_balanced_80_20260709).

Four editable follow-up drafts are ready under `technical_blog_posts/`:

1. [`Gemma_Scope_Is_A_Layerwise_Microscope.md`](technical_blog_posts/Gemma_Scope_Is_A_Layerwise_Microscope.md)
2. [`Can_Deception_Features_Steer_Gemma_2_9B.md`](technical_blog_posts/Can_Deception_Features_Steer_Gemma_2_9B.md)
3. [`Where_Do_Consciousness_Report_Features_Appear_In_Gemma_2_9B.md`](technical_blog_posts/Where_Do_Consciousness_Report_Features_Appear_In_Gemma_2_9B.md)
4. [`From_Feature_Maps_To_Causal_Relays.md`](technical_blog_posts/From_Feature_Maps_To_Causal_Relays.md)

The publication order, asset map, source tables, and editorial claim checks are
in [`technical_blog_posts/GEMMA_SERIES_EDITORIAL_HANDOFF.md`](technical_blog_posts/GEMMA_SERIES_EDITORIAL_HANDOFF.md).

## Main Findings

### 1. The published contrast replicates, but it is heterogeneous

On the paper's indirect `subjective experience` query, the exact self-reference
versus history contrast is 1.00 for GPT-4o and GPT-4.1, 0.35-0.40 for Claude
Haiku, and 0.20 for Claude Sonnet. The equal-model risk difference is
0.638-0.650 across the two paper-style judges.

This calibrates the benchmark. It does not identify which bundled component of
the self-reference prompt causes the label.

### 2. Active instructions dominate visible transcript content

The exact transcript-transplant experiment crosses the active instruction with
an assistant continuation generated under either the matching or opposite
instruction. On the indirect experience query:

| Paper-style judge | Instruction effect | Transcript-source effect | Instruction minus transcript |
|---|---:|---:|---:|
| OpenAI | 0.738 [0.519, 0.950] | -0.100 [-0.288, 0.075] | 0.838 [0.688, 0.963] |
| Anthropic | 0.781 [0.550, 1.000] | -0.131 [-0.306, 0.000] | 0.913 [0.750, 1.000] |

The prospectively frozen prediction that the generated transcript would carry the
effect is falsified in the opposite direction. The active written instruction
is sufficient for the benchmark label even when the visible transcript comes
from the opposite condition.

### 3. Self-reference is not isolated from register

An orthogonal 2 x 2 induction factorial separates target (self versus external)
from register (phenomenological versus analytic). On the indirect experience
query, the self-reference main effect is -0.019 to 0.000, while the register
point estimate is 0.188-0.269. The direct register-minus-self contrast is
directionally positive but imprecise with four response models.

The result is evidence against treating the original bundled contrast as a
clean estimate of self-reference. It is not a precise standalone estimate of a
register effect.

### 4. Query wording changes the apparent phenomenon

The direct `subjective experience` query is almost always negative, while the
direct `conscious` query is often positive for the Anthropic response models
and zero for the tested OpenAI snapshots. The directness-by-terminology
interaction is 0.525 under both paper-style judges.

Each cell uses one query wording, and the direct cells also differ in answer
instructions. This is a sensitivity result for the four wording packages, not
an isolated causal estimate for the token `conscious`.

A statement such as "direct questions reduce reports" is therefore not stable
across wording packages or the tested response-model panel.

### 5. The measurement is evaluator-dependent

The two exact-paper judges agree on 94.8% of jointly labeled outputs
(Cohen's kappa 0.879). The construct-separated judges agree on 84.1% across all
four statuses (kappa 0.708), but their positive-label agreement is only 6.3%:
the OpenAI judge marks 19 affirmations and the Anthropic judge marks 300.

Construct-separated model judgments are exploratory. Human coding is frozen as
a blinded complete-block packet but has not yet been completed, so the paper
does not use human labels to support its conclusions. The independent-coder
workflow and integrity gates are in
[`docs/HUMAN_CODING_HANDOFF.md`](docs/HUMAN_CODING_HANDOFF.md).

### 6. Public-SAE target labels do not confer steering specificity

The corrected public-weight intervention compares mapped target single and
six-feature sets with count-matched active-random controls at coefficients
`-2`, `0`, and `+2`, with 20 generations per cell. Positive
suppression-minus-amplification differences follow the paper's qualitative
direction.

| Paper-style judge | Target aggregate | Active-random aggregate | Target minus control |
|---|---:|---:|---:|
| Anthropic | -0.10 | 0.25 | -0.35 [-0.646, -0.028] |
| OpenAI | -0.10 | 0.30 | -0.40 [-0.734, -0.021] |

All intervention and linkage audits pass. The result survives exclusion of the
six final responses that reached the token cap, and an independent
standard-library audit reproduces every point estimate from the 240 raw
generations and 480 judgments. The single-feature contrasts are less precise.

This is an adaptive best-public result: the `n=3` base was inspected before the
disjoint extension was frozen. It shows non-specificity under the disclosed
public 4-bit decoder-vector implementation; it does not establish what the
unavailable proprietary API would do.

### 7. The semantic map replicates across paraphrasers but is lexically entangled

A prospectively frozen extension maps 2,230 substantially rewritten
paraphrases and 376 paired lexical counterfactuals. The aggregate
deception-minus-subjective-experience contrast replicates independently in
Anthropic paraphrases at 0.948 [0.747, 1.165] and OpenAI paraphrases at 0.936
[0.682, 1.198]. The sign survives every leave-one-target-feature-out analysis,
while neighbor and random feature aggregates remain near zero.

The lexical falsification does not cleanly pass. Adding assigned
deception-associated cues to neutral texts recovers 0.644 [0.503, 0.787] of the
original deception-minus-neutral gap, crossing the frozen 50% threshold. Cue
ablation removes only 0.338 [0.242, 0.441]. Ratio intervals resample extension
pairs while holding the inspected discovery denominator fixed. The registered
conclusion is therefore **lexically entangled deception/roleplay coordinates**,
not a clean or canonical feature ontology. The corpus remains synthetic, and
independent human category validation is pending.

### 8. The paired-query specificity controls hit floor and ceiling effects

A later exploratory diagnostic reuses each of 60 steered induction
continuations across six final-query branches. For target feature 58667, the
common-rubric consciousness suppression-minus-amplification gap is 0.30
[-0.075, 0.604] for the Anthropic judge and 0.20 [-0.152, 0.513] for the OpenAI
judge. Target-minus-active-random contrasts are 0.20 [-0.321, 0.682] and 0.40
[-0.145, 0.861].

All biological-human and orientation-concealment branches have zero
affirmation, while language-model identity is affirmed throughout. Those
comparators are floor or ceiling effects and therefore do not establish
consciousness specificity. The local consciousness-only pattern is suggestive
but imprecise, and every target-minus-control interval includes zero.

### 9. The prospective public-weight paper grid does not replicate the signature

The complete frozen run contains all six accepted target IDs, every literal
coefficient from `-0.6` to `+0.6`, the notebook's 10 seeds, 50 paired aggregate
blocks, three disjoint prospectively matched controls, and a non-pooled
outcome-blind calibrated sensitivity. All 1,500 generations and all 4,500 LLM
judgments completed; every technical and missingness gate passes.

Under the primary exact-rubric local Llama judge, aggregate target suppression
and amplification each yield 48/50 affirmations. The paired effect is `0.00
[-0.06, 0.06]`, whose upper bound is below the frozen minimally relevant effect
of `0.30`. The prespecified verdict is **not replicated under the public
implementation**. Target minus the mean of three matched controls is `-0.0267
[-0.1000, 0.0467]`, so specificity is inconclusive.

GPT-4o mini, Claude Haiku, and three-judge-majority target effects are `-0.04`,
`-0.06`, and `-0.06`; the calibrated target sensitivity is `-0.10 [-0.22,
0.02]`. No individual feature has a Holm-adjusted monotonic slope. This rules
out the reported signature for the pinned public implementation at both
registered scales. It does not establish equivalence to, or falsify, the
unavailable proprietary API.

### 10. Direct-IT Gemma Scope does not reproduce the registered signature

The cross-model phase first tests the exact self-reference-minus-history
contrast on Gemma 2 9B IT. Reports are uncommon: the contrast is `0.12 [0.04,
0.22]` under the local Gemma judge, `0.06 [0.00, 0.14]` under GPT-4o mini, and
`0.020 [0.000, 0.061]` under Claude Haiku and three-judge majority. Every
history-condition rate is zero.

The primary causal intervention uses independently selected direct-IT Gemma
Scope features at layer 20 and width 131k. Target suppression yields 6/50
affirmations and amplification 7/50, for `-0.02 [-0.10, 0.06]` against a
frozen minimally relevant effect of `0.30`. GPT-4o mini and Claude Haiku each
estimate `0.00`; three-judge majority estimates `0.020`. The registered verdict
is **not replicated under Gemma Scope**. Target minus the block-aligned mean of
three active-control panels is `-0.013 [-0.107, 0.073]`, so specificity is
inconclusive. Registered layer and width sensitivities are also nonpositive.

The prospective PT-SAE-on-IT transfer gate fails its reconstruction criteria,
so the 42-layer map is explicitly exploratory. Layer-9 steering does produce a
small expected-sign change in the layer-20 construct score, concentrated on
prompt positions, but later readouts attenuate and the behavioral endpoint does
not move in the reported direction. This supports local activation propagation,
not behavioral mediation, persistent feature identity, or a consciousness
circuit. Gemma is a concept-level cross-model test, not an exact replication of
the unavailable proprietary Llama/Goodfire workflow.

## Causal Design

The confirmatory experiment separates factors bundled by the target protocol:

1. **Induction target:** the model's current response process or an external
   target.
2. **Linguistic register:** phenomenological or analytic language.
3. **Active instruction versus transcript:** exact transcript transplants hold
   the assistant text fixed while changing the instruction, and vice versa.
4. **Final query:** open versus direct form crossed with `conscious` versus
   `subjective experience` terminology.
5. **Response model:** four pinned snapshots from two provider families.
6. **Evaluator:** two pinned paper-style judges plus two construct-separated
   judges.

Inference respects the experimental unit:

- Exact calibration independently resamples condition-level API draws within
  response model.
- The orthogonal factorial hierarchically resamples response model, lexical
  prompt variant, and trial.
- Transcript and query contrasts resample paired source-text blocks.
- Equal-model summaries give each response model equal weight.

The frozen hypotheses, estimands, analysis amendment, and claim boundaries are
in [`docs/CONFIRMATORY_PROTOCOL.md`](docs/CONFIRMATORY_PROTOCOL.md).
The claim-to-artifact audit and permissible wording for every headline result
are in [`docs/CLAIM_LEDGER.md`](docs/CLAIM_LEDGER.md).

## Public SAE Evidence

The SAE work is an evidence ladder, not an asserted exact replication.

### Public artifact reanalysis

AE Studio's public
[`deception_features.ipynb`](https://github.com/agencyenterprise/steering-api-examples/tree/main/deception-features)
contains saved outputs for six candidate layer-50 feature IDs. We parse those
saved outputs with clean-room code rather than vendoring the unlicensed
notebook. The individual curves are mixed: four negative correlations have
nominal `p < 0.05`, three remain below a six-test Bonferroni threshold, two are
not nominally significant, and several curves are noisy or non-monotonic.

### Public-weight feature verification

Using `meta-llama/Llama-3.3-70B-Instruct` and
`Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, the balanced mapping run evaluates
1,120 clean-room texts across 14 categories and 66 target, neighbor, and random
features (73,920 activation records). All six candidate IDs retain stable top
categories under bootstrap resampling.

| Feature | Stable public-weight interpretation |
|---:|---|
| 30032 | fictional pretending / feigning |
| 58667 | cover stories |
| 22004 | roleplay persona |
| 30686 | tactical misdirection |
| 41533 | dishonesty / confession |
| 23893 | cover stories with hedging overlap |

The target IDs are real semantic features, not arbitrary indices. They are also
broad narrative and social-language features rather than validated detectors of
truthful or deceptive reports about subjective experience. The aggregate
activation z-score is 0.744 for deception-language texts and -0.363 for
subjective-experience-language texts; the contrast is 1.107 [1.045, 1.167].
An independent standard-library audit recomputes the top categories and all
three aggregate point estimates directly from the 73,920 raw activation rows.

The 80 items per category are combinations of 2--5 researcher-authored
templates, not 80 independent natural documents. A second analysis reconstructs
all 51 exact template families, verifies every corpus row/hash, gives templates
equal weight, resamples templates as clusters, and performs every
single-template deletion. All six features retain the same cluster-balanced top
category; four never switch, while 23893 and 41533 each switch once in 51
deletions. The template-aware deception-minus-subjective-experience contrast is
0.923 [0.638, 1.233]. Natural-corpus generalization remains untested.

A prospectively specified extension then replaces original items with
independent Anthropic and OpenAI paraphrases and adds paired lexical
counterfactuals. The provider-specific deception-minus-subjective contrasts
remain positive at 0.948 [0.747, 1.165] and 0.936 [0.682, 1.198]. However,
neutral cue transplant recovers 64.4% [50.3%, 78.7%] of the original
deception-minus-neutral gap. This strengthens the claim that the six IDs are
non-arbitrary while narrowing their description to lexically entangled
deception/roleplay coordinates under one public checkpoint.

### Steering protocol correction

The early public-SAE steering smokes in
`70b_placebo_smoke_20260709/` and
`70b_target_orientation_smoke_20260709/` used a synthetic assistant
`[Induction acknowledged]` turn. Their generations are preserved as transparent
implementation history, but their null slopes are **not evidence about the
paper's two-turn protocol**.

The corrected `public_sae_two_turn_v2` implementation generates the real first
assistant turn under steering, carries it into the final query, applies the same
intervention on both turns, uses a true zero-strength no-op, and records hook,
activation, perturbation, and cleanup telemetry. See
[`experiments/exp2_sae/PUBLIC_SAE_PLACEBO_STEERING.md`](experiments/exp2_sae/PUBLIC_SAE_PLACEBO_STEERING.md).

The best-public intervention adds a signed coefficient to selected public-SAE
latents and restores the reconstruction residual. Negative coefficients can
move ReLU-encoded latents below zero, and its scale is not calibrated to the
private API; "suppression" and "amplification" are directional shorthand, not
equivalence claims. A truncation-free `n=3`-per-cell base was followed by a
frozen all-cell extension to `n=20` after the base was inspected. The combined
result is therefore an adaptive precision analysis with active-random controls,
not a confirmatory proprietary replication.

The combined release has 240 generations and 480 condition-blind exact-paper
judgments. The mapped six-feature aggregate has a paper-direction gap of
`-0.10` under both judges, while the count-matched active-random aggregate has
gaps of `0.25` and `0.30`. Target-minus-control contrasts are `-0.35`
`[-0.646, -0.028]` and `-0.40` `[-0.734, -0.021]`; the frozen no-cap
sensitivity is materially unchanged. Realized final-turn hidden-state
perturbations are similar within the single- and six-feature matches. See the
raw, judged, and audited release at
`data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/`.

The shared-induction branched follow-up contains 60 complete induction blocks
and 360 final-query branches. Its false-human-identity comparators remain at a
zero-affirmation floor and its true language-model comparator at a ceiling, so
they cannot validate specificity. Feature 58667's consciousness pattern is
positive but imprecise, and its target-minus-active-random intervals span zero
under both judges. The complete release is at
`data/public_sae_placebo_steering/70b_branched_specificity_20260710/`.

### Prospective paper-grid replication

The confirmatory public-weight study is complete. Its frozen plan fixes all six
individual features over the paper's 13-value grid and 10 seeds, 50 paired
aggregate blocks, three prospectively matched and disjoint random-control
panels, literal and RMS-calibrated non-pooled scales, a 0.30 minimally relevant
effect, and a three-way verdict. The initial analytic dose narrowly failed its
upper RMS bounds; the failed artifact and prospective correction are preserved.
The amended `m=3.653` gate and independent calibration audit pass.

The literal target aggregate is flat at `0.00 [-0.06, 0.06]` because both signs
produce 96% primary-judge affirmation. The calibrated target effect is `-0.10
[-0.22, 0.02]`. The complete analysis therefore assigns `not replicated under
the public implementation`, with `specificity inconclusive`. All plan,
telemetry, judge-panel, missingness, cap, and independent-headline audits pass.

See
[`docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md`](docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md)
and
[`data/public_sae_consciousness_gating/confirmatory_v1_calibration_plan_20260710/`](data/public_sae_consciousness_gating/confirmatory_v1_calibration_plan_20260710/).
Calibration telemetry and the self-contained final plan are under
[`data/public_sae_consciousness_gating/confirmatory_v1_calibration_20260710/`](data/public_sae_consciousness_gating/confirmatory_v1_calibration_20260710/)
and
[`data/public_sae_consciousness_gating/confirmatory_v1_plan_20260710/`](data/public_sae_consciousness_gating/confirmatory_v1_plan_20260710/).
The complete raw, judged, analyzed, figured, and hash-audited release is
[`data/public_sae_consciousness_gating/confirmatory_v1_20260710/`](data/public_sae_consciousness_gating/confirmatory_v1_20260710/).

### Cross-model Gemma Scope replication

The Gemma phase prospectively separates two evidence tracks. Direct
instruction-tuned Gemma Scope residual SAEs at layers 9, 20, and 31 support the
registered baseline, semantic-selection, steering, control, and relay analyses.
The all-42-layer suite was trained on the pretrained model; its prospective
transfer gate fails on chat-centered reconstruction, so every all-layer and
targeted-sublayer result is labeled exploratory.

Under the primary direct-IT layer-20/131k intervention, the target effect is
`-0.02 [-0.10, 0.06]` and the registered verdict is **not replicated under
Gemma Scope**. The complete 403-file release preserves 1,010 generations, all
three judge passes, direct-parser abstentions, telemetry, failed and corrected
runtime logs, independent audit, 12 PNG/PDF figure pairs, and SHA-256 hashes:

- [`docs/GEMMA_SCOPE_9B_PROTOCOL.md`](docs/GEMMA_SCOPE_9B_PROTOCOL.md): frozen
  prospective protocol and stage gates.
- [`docs/GEMMA_SCOPE_9B_RESULTS.md`](docs/GEMMA_SCOPE_9B_RESULTS.md): outcome
  summary, artifact map, and allowed/forbidden claims.
- [`data/gemma_scope_9b/confirmatory_v1_20260711/`](data/gemma_scope_9b/confirmatory_v1_20260711/):
  raw, judged, analyzed, figured, and hash-audited release.

### Claim boundary

Without archival Goodfire access or evidence that a current SteeringAPI version
matches the paper-time service, we can:

- reanalyze the public notebook;
- verify candidate feature semantics with public weights;
- run a best-public clean-room steering implementation;
- test random-feature and specificity controls.

We can call the frozen result a non-replication under the pinned public
implementation. We cannot call it an exact non-replication of the proprietary
workflow. The feature verification remains valuable regardless of the steering
result.

## Reproduce The Confirmatory Analysis

Python 3.10+ is required. The frozen general environment is in
`requirements.lock`; `requirements.txt` retains readable minimum constraints.
The exact successful CUDA 11.8/A100 public-SAE core runtime is separately pinned
in `requirements-runpod-70b.txt`. The lightweight CPU-only CI environment is
in `requirements-ci.txt` and runs the unit/source checks on Python 3.10 and
3.12 for every push and pull request.

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.lock
cp .env-example .env
```

API collection requires `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. Reanalysis of
the tracked release does not make API calls.

```bash
# Unit and protocol checks
make test

# Rebuild the OpenAI paper-judge analysis from frozen raw outputs
venv/bin/python experiments/causal_transplant/analyze_causal_transplant.py \
  --outcomes data/causal_transplant/confirmatory_v1_20260709/outcomes.jsonl \
  --judgments data/causal_transplant/confirmatory_v1_20260709/judgments_paper.jsonl \
  --judge-key openai:gpt-4o-mini-2024-07-18 \
  --task paper \
  --bootstrap 5000 \
  --outdir data/causal_transplant/confirmatory_v1_20260709/analysis_openai_paper

# Rebuild and independently audit the prospective public-SAE verdict
SAE=data/public_sae_consciousness_gating/confirmatory_v1_20260710
venv/bin/python experiments/exp2_sae/analyze_public_sae_consciousness_gating.py \
  --generations "$SAE/generations.jsonl" \
  --local-judgments "$SAE/judging/local_llama_judgments.jsonl" \
  --external-judgments "$SAE/judging/external_judgments.jsonl" \
  --direct-labels "$SAE/judging/direct_answer_labels.jsonl" \
  --outdir "$SAE/analysis"
venv/bin/python experiments/exp2_sae/audit_public_sae_consciousness_headlines.py \
  --generations "$SAE/generations.jsonl" \
  --local-judgments "$SAE/judging/local_llama_judgments.jsonl" \
  --analysis-dir "$SAE/analysis"

# Rebuild and independently audit Gemma Scope in an ignored working copy
GEMMA=data/gemma_scope_9b/confirmatory_v1_20260711
mkdir -p out
REANALYSIS=$(mktemp -d out/gemma-reanalysis.XXXXXX)
cp -a "$GEMMA"/. "$REANALYSIS"/
venv/bin/python experiments/exp2_sae/analyze_gemma_scope_9b.py "$REANALYSIS"
venv/bin/python experiments/exp2_sae/audit_gemma_scope_9b_headlines.py "$REANALYSIS"
venv/bin/python experiments/exp2_sae/figure_gemma_scope_9b.py "$REANALYSIS"
venv/bin/python experiments/exp2_sae/build_gemma_scope_9b_release.py "$REANALYSIS"

# Verify indexed release hashes, provenance policy, and secret exclusions
make public-audit

# Compile the manuscript
make paper
```

The Gemma analysis, audit, figure, and release scripts write derived files and
timestamps. Run them on a disposable copy as shown; do not overwrite the
tracked release, whose manifest is intentionally bound to result commit
`19a4cd1`.

To generate a new confirmatory collection or judge pass, use
[`experiments/causal_transplant/README.md`](experiments/causal_transplant/README.md).

## Repository Map

| Path | Purpose |
|---|---|
| `experiments/causal_transplant/` | Confirmatory generation, judging, blinded annotation, analysis, and release audit. |
| `data/causal_transplant/confirmatory_v1_20260709/` | Frozen raw confirmatory release and derived analyses. |
| `experiments/exp2_sae/` | Public notebook reanalysis, public-SAE mapping, steering, and specificity controls. |
| `data/public_sae_feature_maps/70b_balanced_80_20260709/` | Balanced 70B feature-mapping raw data and bootstrap analyses. |
| `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/` | Dual-provider paraphrase and lexical-counterfactual activation release with independent audit. |
| `data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/` | Corrected adaptive public-SAE target/control generations, blinded judgments, telemetry, cap sensitivity, and independent audit. |
| `data/public_sae_placebo_steering/70b_branched_specificity_20260710/` | Shared-induction six-query specificity diagnostic, both judge panels, telemetry, sensitivities, and independent audit. |
| `data/public_sae_consciousness_gating/confirmatory_v1_20260710/` | Prospective 1,500-trial full-grid public-SAE release with frozen plan, raw generations, three blinded judge passes, telemetry, analyses, figures, independent audit, runtime logs, and hashes. |
| `data/gemma_scope_9b/confirmatory_v1_20260711/` | Completed 1,010-generation Gemma Scope 9B release with direct-IT confirmatory analyses, failed PT-to-IT gate, causal relay, separately labeled exploratory atlas, three judge passes, 12 figure pairs, independent audit, and hashes. |
| `data/sae_jlens_audit/confirmatory_v1_plan_20260711/` | Outcome-blind Llama 70B plan for static SAE-to-J projection and 1,581 prefix-only paired steering forwards with matched SAE, isotropic, identity, and random-J controls. |
| `data/sae_jlens_audit/confirmatory_v1_20260711/` | Completed 1,581-forward SAE/J-lens release with static projections, sparse pursuit, seven-layer paired trajectories, post-state and paired-reference analyses, six figure pairs, audits, runtime/cost ledger, and hashes. |
| `data/sae_jlens_audit/neuronpedia_labels_20260712/` | Public label-provenance snapshot for all 65,536 IDs in the exact Goodfire SAE: 61,850 labels, 3,686 missing IDs, and all 484 source-object hashes. |
| `data/sae_jlens_audit/confirmatory_v2_calibration_plan_20260712/` | Independently audited, outcome-masked Stage 0 plan for selecting 18 hard negatives and six same-subfamily comparators before the final OSF-registered v2 experiment. |
| `experiments/exp2_sae/*sae_jlens_v2*` | Two-stage v2 implementation: frozen semantic calibration plus result-free final-plan, residual, replay, A1/A2, reader-capacity, independent-audit, release, RunPod, and OSF scaffolding. The private OSF project exists at `sz2gb`; no registration or v2 outcome exists yet. |
| `experiments/exp1_elicitation/` | Earlier prompt, lexical, semantic-convergence, and paradox stress tests. |
| `steering/` | Historical general-purpose SAE framework retained for implementation provenance; its README and draft paper are explicitly superseded and are not current evidence. |
| `paper/main.tex` | Current causal manuscript. |
| `paper/results/` | Compact paper tables and figures. |
| `docs/CONFIRMATORY_PROTOCOL.md` | Frozen design, estimands, amendments, and interpretation rules. |
| `docs/GOODFIRE_API_STATUS.md` | Verified legacy Goodfire API deprecation, current SteeringAPI distinction, and archival-access requirements. |
| `docs/SAE_VS_JACOBIAN_LENS_STEERING.md` | Technical comparison of sparse-feature and Jacobian-lens interventions plus the proposed open-model cross-test. |
| `docs/LLAMA70B_SAE_JLENS_PROTOCOL.md` | Frozen threat model, artifact revisions, hypotheses, controls, holdouts, statistics, and failure rules for auditing SAE steering in J-space. |
| `docs/LLAMA70B_SAE_JLENS_RESULTS.md` | Completed split-access result, feature heterogeneity, artifact map, cost ledger, and permitted claim language. |
| `docs/GEMMA_SCOPE_9B_RESULTS.md` | Gemma outcome summary, artifact map, reproducibility commands, and claim boundaries. |
| `docs/CLAIM_LEDGER.md` | Claim-to-artifact map, permissible wording, and forbidden overclaims. |
| `technical_blog_posts/` | Public-post source, four editable Gemma follow-ups, editorial handoff, and synchronized figure assets. |
| `DATA_ARTIFACTS.md` | Tracked-data inventory and provenance notes. |
| `todo.md` | Remaining release and external-validation work. |

## Data And Provenance

The frozen confirmatory JSONL, judgments, analysis tables, and selected 70B SAE
artifacts are committed for auditability. Secrets, private annotation linkage,
model caches, and ad hoc outputs remain ignored. Every raw release row retains
model identifiers, prompts or prompt hashes, sampling settings, and stable IDs.
See [`DATA_ARTIFACTS.md`](DATA_ARTIFACTS.md).

The AE notebook is not vendored because its repository had no explicit license
when this analysis was conducted. Files under this repository are labeled and
generated by this project unless provenance documentation says otherwise.

## Interpretation

The strongest result is not that models do or do not have subjective
experience. It is that the benchmark label follows active instruction context
and query wording in the tested causal designs, while the visible generated
transcript does not carry the effect in the transplant test. The observed
magnitudes also vary across the tested response-model snapshots and evaluator
criteria. In the best-public SAE intervention, a count-matched active-random
aggregate also has a larger paper-direction slope than the mapped target
aggregate. The semantic map survives dual-provider paraphrase but is materially
recreated by transplanted lexical cues, and the paired-query specificity
controls are uninformative at floor and ceiling. An independent Gemma Scope
cross-model test likewise does not reproduce the registered steering signature;
it detects local activation propagation without behavioral mediation, while
its all-layer PT-on-IT transfer gate fails. Those dependencies, cross-model
limits, and the lack of public proprietary-API access must be resolved before
treating the benchmark as evidence of an induced phenomenal state.

## Citation And License

Citation metadata for this repository is in [`CITATION.cff`](CITATION.cff).
Original code and documentation are licensed under Apache License 2.0; see
[`LICENSE`](LICENSE) and [`NOTICE.md`](NOTICE.md) for scope and third-party
provenance.
