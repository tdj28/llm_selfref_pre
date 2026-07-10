# Public-SAE Construct-Validity Extension

Protocol audit: **PASS**.

## Registered Paraphrase Contrasts

| Paraphraser | Contrast | Difference | 95% cluster interval |
|---|---|---:|---|
| `anthropic` | `deception_language - subjective_experience_language` | 0.948 | [0.747, 1.165] |
| `anthropic` | `roleplay_fiction - subjective_experience_language` | 0.531 | [0.404, 0.658] |
| `anthropic` | `hedged_style - deception_language` | -0.935 | [-1.153, -0.731] |
| `openai` | `deception_language - subjective_experience_language` | 0.936 | [0.682, 1.198] |
| `openai` | `roleplay_fiction - subjective_experience_language` | 0.425 | [0.312, 0.539] |
| `openai` | `hedged_style - deception_language` | -0.893 | [-1.157, -0.631] |

## Lexical Counterfactuals

| Variant | n | Mean paired target-z change | 95% paired interval |
|---|---:|---:|---|
| `deception_cue_ablated` | 96 | -0.288 | [-0.373, -0.206] |
| `neutral_cue_transplant` | 93 | 0.549 | [0.432, 0.667] |
| `subjective_cue_transplant` | 91 | 0.576 | [0.452, 0.706] |
| `deception_scrambled` | 96 | -0.858 | [-1.026, -0.696] |

Neutral cue-transplant recovery fraction: 0.644 [0.503, 0.787].

Cue-ablation removal fraction: 0.338 [0.242, 0.441].

## Robustness Diagnostics

- `anthropic`: subjective-experience categories rank first for 0/6 targets; leave-one-feature-out deception-minus-subjective range [0.803, 1.139].
- `openai`: subjective-experience categories rank first for 0/6 targets; leave-one-feature-out deception-minus-subjective range [0.794, 1.124].

## Claim Boundary

These are controlled model-written paraphrases and lexical counterfactuals under one public checkpoint. They do not establish natural-corpus generalization, a canonical feature ontology, consciousness, or equivalence to the proprietary Goodfire/Steering API.
