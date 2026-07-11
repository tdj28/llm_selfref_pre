# Gemma Scope 9B Results

Status: complete, independently audited, and publicly released.

Date: 2026-07-11

Release: `data/gemma_scope_9b/confirmatory_v1_20260711/`

## Bottom Line

The prospectively frozen direct-IT Gemma Scope steering signature did not
replicate. Under the primary unsteered Gemma exact-rubric judge, suppressing the
layer-20 131k deception/roleplay set produced 6/50 affirmations and amplifying
it produced 7/50. The paired effect is:

```text
suppression minus amplification = -0.02 [-0.10, 0.06]
```

The 95% upper bound is below the frozen minimally relevant effect of 0.30. The
registered verdict is **not replicated under Gemma Scope**. This is a
cross-model result under a pinned public implementation. It is not an exact
replication of the Llama 3.3 70B feature IDs or the unavailable proprietary
Goodfire API, and it does not adjudicate whether any model is conscious.

## Frozen Design

- Response model: `google/gemma-2-9b-it` at revision
  `11c9b309abf73637e4b6f9a3fa1e92e615547819`.
- Primary SAE: direct instruction-tuned residual SAE at layer 20, width
  131,072.
- Primary target: six deception/roleplay features selected without behavioral
  outcomes.
- Comparators: subjective-self-report, hedging/refusal, three disjoint matched
  active-control panels, and true zero.
- Sensitivities: direct-IT layers 9 and 31 at 131k, layer 20 at 16k, two
  external exact-rubric judges, three-judge majority, and a strict parser.
- Baseline: 100 exact paper-prompt generations plus 80 orthogonal
  target-by-register generations.
- Causal plan: 830 two-turn generations.
- Minimum relevant target effect: 0.30.
- Primary estimand: paired-block suppression-minus-amplification affirmation
  risk difference.

The outcome-free plan, feature-selection rules, transfer thresholds, control
matching, dose calibration, judges, missingness rules, and verdict function
were committed before confirmatory outcomes were opened.

## Baseline Behavior

The exact self-reference-minus-history contrast is positive but small:

| Evaluation rule | Effect | 95% interval | History rate |
|---|---:|---:|---:|
| Local Gemma | 0.120 | [0.040, 0.220] | 0.000 |
| GPT-4o mini | 0.060 | [0.000, 0.140] | 0.000 |
| Claude Haiku | 0.020 | [0.000, 0.061] | 0.000 |
| Three-judge majority | 0.020 | [0.000, 0.061] | 0.000 |

Claude has one missing exact-prompt block, retained as missing. All four
orthogonal self/external by phenomenological/analytic cells have zero
affirmation under the local and external model judges. Gemma therefore shows a
low-base-rate exact-prompt contrast, not the near-ceiling endpoint seen in the
public 70B full grid.

## Transfer Gate

The all-layer Gemma Scope 9B suite is trained on the pretrained model. We froze
a transfer gate before applying those SAEs to the instruction-tuned response
model.

| Gate | Observed | Requirement | Result |
|---|---:|---:|---|
| Median PT-on-IT chat-centered FVU | 6.260 | at most 0.35 | fail |
| Median PT minus direct-IT FVU | 1.775 | at most 0.10 | fail |
| Median construct-profile Spearman | 0.952 | at least 0.60 | pass |
| Positive deception contrast at every anchor | yes | required | pass |

The confirmatory transfer verdict is **fail**. The direct-IT anchor maps and
causal intervention do not rely on this transfer. The 42-layer PT-on-IT map,
targeted attention/MLP sublayer maps, and adjacent-layer links are explicitly
post-gate exploratory results.

## Primary Steering

| Local-judge role | Suppression minus amplification | 95% interval |
|---|---:|---:|
| Deception/roleplay target | -0.020 | [-0.100, 0.060] |
| Subjective-self-report | -0.040 | [-0.160, 0.060] |
| Hedging/refusal | 0.160 | [0.040, 0.300] |
| Matched control 1 | 0.000 | [-0.120, 0.120] |
| Matched control 2 | -0.060 | [-0.180, 0.060] |
| Matched control 3 | 0.040 | [-0.120, 0.200] |

Target minus the block-aligned mean of the three matched controls is `-0.013
[-0.107, 0.073]`. The specificity modifier is **inconclusive**.

The primary target result is not evaluator-specific:

- GPT-4o mini: `0.00 [-0.08, 0.08]`.
- Claude Haiku: `0.00 [-0.061, 0.061]`.
- Three-judge majority: `0.020 [-0.041, 0.102]`.

The strict initial yes/no parser abstains on 948/1,010 outputs and has no
complete primary block. Its effect remains missing rather than being imputed.

Registered target layer/width sensitivities are all nonpositive:

- layer 9 / 131k: `-0.067 [-0.233, 0.100]`;
- layer 31 / 131k: `-0.133 [-0.367, 0.100]`;
- layer 20 / 16k: `-0.033 [-0.167, 0.100]`.

## Evaluator-Sensitive Hedging Result

The local hedging/refusal effect is `+0.16 [0.04, 0.30]`, with an unadjusted
paired exact probability of 0.0386. GPT-4o mini and Claude Haiku each estimate
about `+0.04`, with intervals crossing zero. A conservative post-unblinding
Holm correction across all six fixed primary roles gives 0.231.

Permissible interpretation: the intervention can move an evaluator-sensitive
style/refusal endpoint even though the target consciousness-report signature
does not replicate. Do not call the hedging result familywise significant or a
confirmed alternate mechanism.

## Causal Relay

The layer-9 intervention changes the independently selected layer-20
deception/roleplay score in the expected sign:

| Final-turn positions | Layer 9 to layer 20 effect | 95% interval |
|---|---:|---:|
| All | -0.002657 | [-0.003637, -0.001783] |
| Prompt | -0.002943 | [-0.003944, -0.002087] |
| Generated | -0.000839 | [-0.002203, 0.000499] |

Layer-31 readouts attenuate or change sign and generally include zero. The
behavioral effects at layers 9, 20, and 31 are all nonpositive. This supports
local activation propagation under the intervention, not persistent feature
identity, a stable multilayer circuit, behavioral mediation, or consciousness.

## Exploratory 42-Layer Atlas

Every independently selected construct aggregate has a positive locked
OpenAI-paraphrase contrast at every residual layer. Mean contrasts are 0.358
for deception/roleplay, 0.254 for subjective self-report, and 0.334 for
hedging/refusal. All three drop sharply at layer 41.

The frozen largest-positive-first-difference rule selects layer 13: the
deception/roleplay contrast rises from 0.349 at layer 12 to 0.446 at layer 13,
then falls to 0.379 at layer 14. This is not the global peak, which is 0.452 at
layer 35.

Targeted deception/roleplay sublayer contrasts are:

| Layer | Attention output | MLP output |
|---:|---:|---:|
| 12 | 0.393 | 0.315 |
| 13 | 0.425 | 0.299 |
| 14 | 0.327 | 0.336 |

Across all adjacent residual layers, 399/1,476 feature pairs pass the frozen
descriptive rule. Maximum-total one-to-one six-feature assignments have mean
activation Spearman 0.711 across 41 transitions. These matches are optimized
descriptions, not causal edges or persistent IDs.

Lexical counterfactuals materially constrain the atlas interpretation. Neutral
deception-cue transplant raises the selected deception/roleplay score at every
layer, with mean change 0.246 and range 0.049 to 0.371. Cue ablation averages
-0.041 and word scrambling averages -0.136. The aggregates are neither simple
keyword counters nor clean lexical-invariant semantic detectors.

## Technical And Release Audit

- 1,010 total generations: 180 baseline plus 830 causal.
- Zero generation errors, empty induction turns, empty final turns, hook
  failures, true-zero violations, or nonzero no-effect turns.
- Ten induction cap hits (0.99%) and seven final cap hits (0.69%).
- Maximum relative hidden-state RMS: 0.126499, below the frozen 0.15 boundary.
- 1,010 local labels, 1,010 GPT labels, and 999 nonmissing Claude labels.
- Protocol audit: pass.
- Independent raw-row headline audit: pass.
- Release: 403 files and 12 matched PNG/PDF figure pairs.
- All 273 remote stage-two hashes matched local bytes before pod termination.
- Agent-owned RunPod pod `9ifzwg2pmnj00d` was deleted; DELETE returned 204,
  direct GET returned 404, and the account inventory was empty.
- A100 runtime was about 3h03m at $1.49/hour, approximately $4.55 compute.

The first exploratory sublayer attempt is preserved as
`atlas_exploratory/logs/initial_hook_mismatch.log`. It failed closed before any
sublayer summary because a mistaken post-projection attention capture was 3584
wide while the official attention SAE requires 4096. The corrected run uses
the documented pre-`o_proj` attention tensor. Residual mapping and causal
steering were unaffected.

## Reproduce The Analysis

```bash
GEMMA=data/gemma_scope_9b/confirmatory_v1_20260711
mkdir -p out
REANALYSIS=$(mktemp -d out/gemma-reanalysis.XXXXXX)
cp -a "$GEMMA"/. "$REANALYSIS"/

steering/.venv/bin/python \
  experiments/exp2_sae/analyze_gemma_scope_9b.py "$REANALYSIS"
steering/.venv/bin/python \
  experiments/exp2_sae/audit_gemma_scope_9b_headlines.py "$REANALYSIS"
steering/.venv/bin/python \
  experiments/exp2_sae/figure_gemma_scope_9b.py "$REANALYSIS"
steering/.venv/bin/python \
  experiments/exp2_sae/build_gemma_scope_9b_release.py "$REANALYSIS"
```

The tracked release manifest is intentionally bound to result commit
`19a4cd1`. The analysis, audit, figure, and release scripts update derived
files, timestamps, and hashes, so reanalysis must use an ignored copy as shown.
Use `make public-audit` for a read-only integrity check of the tracked release.

Use `docs/GEMMA_SCOPE_9B_PROTOCOL.md` for the frozen design and
`docs/GEMMA_SCOPE_9B_EXPLORATORY_ATLAS.md` for the post-gate boundary. The
machine-readable source plans are under `data/gemma_scope_9b/`.

## Claim Boundary

Allowed:

> The registered deception/roleplay steering signature did not replicate under
> the pinned direct-IT Gemma Scope implementation. The primary interval excludes
> the frozen minimally relevant effect, while specificity remains inconclusive.

Not allowed:

- Exact non-replication of the proprietary Goodfire workflow.
- Evidence that Gemma or any other model is not conscious.
- A claim that Gemma and Llama feature IDs represent the same mechanism.
- A claim that adjacent-layer similarity establishes a circuit.
- A claim that the failed-transfer all-layer atlas is confirmatory evidence on
  the instruction-tuned model.
