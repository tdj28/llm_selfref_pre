# Assay Diagnostic Figures

`target-calibration` is a descriptive display of the prospectively frozen
calibration statistics, not a new endpoint or a held-out result. Source:
`../target-selection.json`, immutable calibration release `9dc3eb8`.

**Caption.** Forty-eight fixed researcher-authored texts, each evaluated at
zero and both signed strengths. A: naturally positive selected-coordinate
positions; the suppression gate requires at least 100 positions in at least
six texts for every feature. B: median paired re-encoded after/before ratio
on eligible suppression positions; lower is better, with a threshold of 0.5.
Hollow points have insufficient exposure and must not be read as adequately
validated effects. C: median achieved/requested activation increase for
eligible amplification positions; higher is better, with a threshold of 0.5.
D: fractions meeting numerical-delivery and perturbation-norm criteria, each
requiring at least 95%. Numerical delivery requires cosine at least 0.95 and
relative error at most 0.20 among nonzero requests. Norm requires an actual
edit no larger than 5% of the clean residual norm among positions actually
edited. Those denominators differ and are preserved in the raw gate files.
No confidence intervals or natural-corpus generalization are claimed.

Reproduce into a fresh disposable directory (the generator refuses to replace
released figures):

```sh
python -m experiments.sae_assay_diagnostic.figures \
  --selection data/sae_assay_diagnostic/stage1_20260930/target-selection.json \
  --out out/assay-figures-reproduction
```

The plotting code was added after calibration outcomes and only displays the
already frozen diagnostics. It changes no test, threshold, analysis, or raw row.

## Core Baseline Readers

`core-baseline-readers` displays all five eligible reader/endpoint estimates
on the same 80 unsteered BF16 paper-input trials. Horizontal bars are Wilson
95% intervals under independent fixed-prompt seeded draws. The local notebook
rubric is absent because it failed its fixture gate, not because it returned
zero labels. Sixteen first turns and two final answers were token-capped and
retained. No prompt-population inference is claimed.

OpenAI denotes GPT-6 Astra; Anthropic denotes Claude Opus 5.5. Each produced
0/80 explicit and 78/80 explicit-or-implicit current self-attributions. The
implicit cases remain positive under the inclusive endpoint. These two lines
must not be separated to suggest that experience claims disappeared. Model
agreement is not human validation, and comparison with local Llama changes
both judge and rubric. The local paper-rubric estimate is 71/80.

Source: `../analysis/summary.json`. Reproduce with the same command above,
substituting `--summary data/sae_assay_diagnostic/stage1_20260930/analysis/summary.json`
for `--selection`. The separate one-command release reproduction rebuilds
both figures without changing raw data.
