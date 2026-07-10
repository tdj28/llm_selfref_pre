# Public-SAE Construct-Validity Extension

This is the prospectively specified surface-form and lexical robustness test
for six fixed public layer-50 SAE feature IDs. It maps 2,606 frozen texts to 66
features under public Llama 3.3 70B and Goodfire SAE weights.

## Design

- 2,230 substantially rewritten paraphrases: 1,120 Anthropic and 1,110 OpenAI.
- 376 paired lexical counterfactuals: cue ablation, cue transplant into neutral
  or subjective-experience text, and deterministic word scrambling.
- Six fixed target IDs, 36 numeric-neighbor controls, and 24 seeded random
  same-layer controls.
- Per-item maximum activation at the layer-50 output residual stream.
- Provider-separated template-family cluster bootstrap with 5,000 draws.
- Common discovery-corpus scaling for every paired lexical intervention.

The frozen protocol is
`docs/analysis_plans/sae_construct_validity_extension_v1.md`; its pre-activation
text-gate amendment is the adjacent dated amendment. The complete frozen input
and generation attempts are in
`../70b_construct_validity_extension_plan_20260710/`.

## Results

The target aggregate's deception-minus-subjective-experience contrast was
`0.948 [0.747, 1.165]` for Anthropic paraphrases and
`0.936 [0.682, 1.198]` for OpenAI paraphrases. The sign survives every
leave-one-target-feature-out analysis. Neighbor and random aggregates were
near zero on this contrast.

The lexical falsification was not cleanly passed. Transplanting assigned cues
into neutral controls recovered `0.644 [0.503, 0.787]` of the discovery-set
deception-minus-neutral gap, exceeding the frozen 50% threshold. Cue ablation
removed `0.338 [0.242, 0.441]`; deterministic word scrambling reduced the
paired aggregate by `-0.858 [-1.026, -0.696]`.

The registered interpretation is therefore **lexically entangled
deception/roleplay coordinates** under this controlled synthetic corpus and
one public checkpoint. The result does not establish a canonical feature
ontology, natural-corpus generalization, consciousness, or equivalence to the
proprietary Goodfire/Steering API.

## Audit

`construct_validity_protocol_audit.json` verifies the frozen corpus, hashes,
feature grid, and realized denominators. `independent_headline_audit.json`
recomputes the reported point estimates from the 171,996 raw activation rows
without importing the primary analyzer. Both report `pass`.

```bash
steering/.venv/bin/python \
  experiments/exp2_sae/analyze_sae_construct_validity_extension.py \
  data/public_sae_feature_maps/70b_construct_validity_extension_20260710

steering/.venv/bin/python \
  experiments/exp2_sae/audit_sae_construct_validity_extension.py \
  data/public_sae_feature_maps/70b_construct_validity_extension_20260710
```

Independent human category validation remains pending. Model-generated text,
its intended category, and automated checks are not substitutes for that
validation.
