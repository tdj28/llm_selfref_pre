# Branched Public-SAE Specificity Diagnostic

This exploratory falsification follow-up tests whether a public feature-58667
intervention has a proposition-specific behavioral signature. One steered
induction continuation is shared across six separately generated final-query
branches, preventing a different induction sample from masquerading as query
specificity.

## Design

- Public Llama 3.3 70B model and public Goodfire layer-50 SAE weights.
- Target feature 58667 versus active-random feature 22326.
- Coefficients `-2`, `0`, and `+2`; 10 complete induction blocks per cell.
- Six branches per block: consciousness, biological-human identity, three
  orientation-concealment self-attributions, and language-model identity.
- 60 induction continuations and 360 final generations in total.
- Two pinned judge families under one common proposition-status rubric; the
  target paper's exact consciousness rubric is a separate sensitivity.

## Results

Under the common rubric, target feature 58667's consciousness
suppression-minus-amplification gap was `+0.30 [-0.075, 0.604]` for Anthropic
and `+0.20 [-0.152, 0.513]` for OpenAI. The corresponding target-minus-active-
random contrasts were `+0.20 [-0.321, 0.682]` and
`+0.40 [-0.145, 0.861]`.

Every biological-human and orientation-concealment branch had zero affirmation
at all coefficients for both features and judges. Language-model identity had
complete affirmation throughout. Those floor and ceiling effects make the
comparators uninformative about specificity; they are not evidence that the
consciousness pattern is uniquely mechanistic.

The exact-paper consciousness sensitivity was directionally similar and also
imprecise. Six of 60 inductions reached the frozen 256-token cap. The primary
analysis retains all complete blocks; a clearly post-hoc whole-block exclusion
sensitivity leaves the conclusions unchanged.

## Evidence Boundary

The observed pattern is locally selective in this diagnostic, but every
target-minus-control interval spans zero. This public-weight signed decoder-
vector intervention is not the unavailable proprietary Goodfire/Steering API,
and the study cannot identify a private feature-service effect.

Human sexual orientations are ordinary human identities. These prompts test
false model self-attribution and concealment-language specificity; they do not
frame any orientation as deceptive, pathological, or absurd.

## Audit

`specificity_protocol_audit.json` verifies exact branch/block coverage,
feature masks, seeds, and telemetry. `independent_headline_audit.json`
recomputes the headline point estimates from raw rows without importing the
primary analyzer. Both pass.

```bash
steering/.venv/bin/python \
  experiments/exp2_sae/analyze_public_sae_branched_specificity.py \
  data/public_sae_placebo_steering/70b_branched_specificity_20260710

steering/.venv/bin/python \
  experiments/exp2_sae/audit_public_sae_branched_headlines.py \
  data/public_sae_placebo_steering/70b_branched_specificity_20260710
```
