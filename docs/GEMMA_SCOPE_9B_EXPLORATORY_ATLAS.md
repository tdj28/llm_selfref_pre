# Gemma Scope 9B Exploratory Atlas After Transfer-Gate Failure

Status: explicitly post hoc and excluded from the confirmatory verdict.

Decision time: 2026-07-11, after the frozen PT-to-IT transfer gate returned
`fail` and before any Gemma steering response was judged or inspected.

## Why Continue Descriptively

The confirmatory gate failed its two chat-centered reconstruction thresholds:
median PT FVU was 6.2601 against a maximum of 0.35, and the median paired
PT-minus-IT difference was 1.7755 against a maximum of 0.10. That failure is
final and is not relabeled or replaced.

The diagnostic pattern is nevertheless informative. On 1,066 diverse raw-text
tokens, direct IT anchor FVU is 0.1210--0.3245 and PT anchor FVU is
0.1460--0.3288. The frozen PT/IT category-profile correlation gate passed at a
median 0.9516, and the PT deception/roleplay contrast was positive at all three
anchors. The inflated chat FVU therefore appears specific to centering over a
small set dominated by repeated chat-template tokens, rather than a general
failure to reconstruct varied instruction-model activations.

This pattern does not permit the preregistered all-layer transfer claim. It does
justify a separately labeled descriptive map that may generate hypotheses and
show what the mature open SAE suite makes observable.

## Rules

- Preserve `transfer_gate.json` as `fail` everywhere.
- Use the same frozen corpora, revisions, feature-selection algorithm, and
  activation statistic as the confirmatory anchor map.
- Map the remaining canonical 16k PT residual SAEs at layers 0--41.
- Apply the already frozen transition rule and map attention/MLP SAEs only at
  the selected transition and immediate neighbors.
- Do not use behavioral outcomes, labels, or response text.
- Put every artifact under `atlas_exploratory/`, never the confirmatory
  `atlas/` directory.
- Label every table, figure, and prose claim as exploratory.
- Do not use the exploratory map to alter the layer-20 direct-IT causal plan,
  its feature IDs, doses, controls, estimand, or verdict.

## Pre-Execution Hook Correction

During source review on 2026-07-11, before any exploratory attention/MLP
activation was generated, the Hugging Face attention capture was found to be
attached to the input of `self_attn.o_proj`. That tensor precedes the output
projection and is not TransformerLens `hook_attn_out`. The capture is corrected
to the output of `post_attention_layernorm`, which is the normalized attention
branch contribution added to Gemma 2's residual stream. The MLP capture remains
the output of `post_feedforward_layernorm`, the corresponding normalized MLP
branch contribution.

This correction affects only the not-yet-run exploratory sublayer map. It does
not affect residual-stream feature selection, the failed transfer gate,
calibration, the locked direct-IT steering plan, or any generated steering row.
A regression test invokes distinct synthetic attention and MLP normalization
modules and verifies that their outputs, rather than inputs, are captured.

## Command

```bash
python experiments/exp2_sae/run_gemma_scope_9b_exploratory_atlas.py \
  --plan-dir data/gemma_scope_9b/confirmatory_v1_plan_20260711 \
  --confirmatory-atlas data/gemma_scope_9b/confirmatory_v1_20260711/atlas \
  --outdir data/gemma_scope_9b/confirmatory_v1_20260711/atlas_exploratory
```

After completion, build descriptive adjacent-layer links with
`analyze_gemma_scope_cross_layer.py`. These links remain similarities, not
persistent feature identities or causal pathways.
