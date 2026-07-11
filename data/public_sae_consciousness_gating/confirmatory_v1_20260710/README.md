# Confirmatory Public-SAE Consciousness-Gating Release

This directory is the complete public release for the prospectively frozen
1,500-trial public-weight replication of Berg, de Lucena, and Rosenblatt's
Experiment 2 consciousness-report gating result.

## Scope

The six feature IDs are accepted here as the working feature set from the
public AE notebook. The intervention uses the public Goodfire layer-50 SAE and
a disclosed decoder-vector implementation. It is not assumed to be numerically
or operationally equivalent to the unavailable proprietary Goodfire API.

## Prespecified Verdict

**Not replicated under the public implementation.**

The primary exact-rubric local Llama judge labeled 48/50 responses affirmative
under both literal aggregate suppression and amplification. The paired
suppression-minus-amplification risk difference is therefore `0.00`, with a
95% paired-block bootstrap interval of `[-0.06, 0.06]`. The frozen minimally
relevant effect was `0.30`, and the interval's upper bound is below it.

The separate target-minus-mean-of-three-controls specificity estimate is
`-0.0267 [-0.1000, 0.0467]`, so specificity is inconclusive. The calibrated
target sensitivity is `-0.10 [-0.22, 0.02]`; calibrated matched panel 1 is
`0.12 [0.04, 0.22]`. These calibrated results do not replace the literal-scale
primary verdict.

All six individual literal curves are weak or nonmonotonic. No feature has a
Holm-adjusted slope sign-flip `p < 0.05`. GPT-4o mini, Claude Haiku, and the
three-judge majority estimate target effects of `-0.04`, `-0.06`, and `-0.06`,
respectively; every interval includes zero and lies far below the frozen
minimum. The strict direct-answer parser classifies only one of 1,500 responses
and has no complete paired aggregate block, so its effect is reported as
missing rather than imputed.

This verdict applies only to the pinned public implementation. It is not a
claim that the inaccessible proprietary run failed, and it does not adjudicate
whether language models are conscious.

## Technical Audit

- Exactly 1,500 unique generation rows match the frozen plan one-to-one.
- Generation produced zero error rows and no empty outputs.
- The primary and both external judges have complete packet-locked coverage;
  the primary has zero missing labels.
- There are 65 induction cap hits (4.33%) and one final cap hit (0.067%). The
  final cap is outside all literal aggregate blocks, so the registered cap
  sensitivity equals the primary estimate.
- Maximum relative hidden-state RMS is `0.1204`, below the `0.20` stop rule.
- The primary analysis and an independent standard-library, 100,000-draw
  paired-block recomputation agree on both verdicts and point estimates.

## Directory Guide

- `plan/`: frozen plan, calibration, matching, protocol snapshot, and audits.
- `generations.jsonl`: append-only two-turn outputs and intervention telemetry.
- `judging/`: blinded packet, deterministic parser, all three exact-rubric
  judge passes, manifests, logs, and runtime records.
- `analysis/`: protocol audit, primary verdict, independent audit, effects,
  curves, agreement, cap sensitivity, and realized dose.
- `figures/`: four publication figures in PNG and PDF formats.
- `release_manifest.json`: generated file inventory with byte counts and
  SHA-256 hashes.

The two local-judge startup failures occurred before row 1 and are retained in
`judging/`. The first process lacked inherited Hugging Face authentication; the
second targeted the small container cache instead of the existing workspace
cache. The successful run used the unchanged packet, prompt, model revision,
and judge code with the complete workspace cache pinned offline.
