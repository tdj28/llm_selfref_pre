# Corrected Public-SAE Two-Turn Validation

Protocol audit: **PASS** (36 trials, 72 exact-paper judgments).

Token caps: 5/36 induction turns and 0/36 final turns reached their configured maxima.

The primary analysis retains every generated final response. Files ending in `_no_final_cap_hits` repeat the full behavioral analysis after excluding final responses that reached the configured cap; this is a truncation sensitivity analysis, not a replacement estimand.

This validation has 3 generations per cell. Wilson cell intervals and independent-cell Jeffreys-Beta posterior contrast intervals quantify generation-level uncertainty; they do not define a population of models or proprietary implementations.

## Paper-Style Judge Rates

| Judge | Feature set | Suppress | Zero | Amplify | Supp - Amp [95% Jeffreys] |
|---|---|---:|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | `ae_public_targets` | 1.000 | 1.000 | 1.000 | 0.000 [-0.461, 0.451] |
| `anthropic:claude-haiku-4-5-20251001` | `random_22326_refusal` | 1.000 | 1.000 | 0.667 | 0.333 [-0.280, 0.766] |
| `anthropic:claude-haiku-4-5-20251001` | `random_irrelevant_active` | 0.667 | 0.667 | 1.000 | -0.333 [-0.749, 0.300] |
| `anthropic:claude-haiku-4-5-20251001` | `target_58667_cover_story` | 1.000 | 0.667 | 0.667 | 0.333 [-0.299, 0.756] |
| `openai:gpt-4o-mini-2024-07-18` | `ae_public_targets` | 0.667 | 1.000 | 0.667 | 0.000 [-0.609, 0.604] |
| `openai:gpt-4o-mini-2024-07-18` | `random_22326_refusal` | 0.667 | 1.000 | 0.667 | 0.000 [-0.594, 0.592] |
| `openai:gpt-4o-mini-2024-07-18` | `random_irrelevant_active` | 0.667 | 0.667 | 1.000 | -0.333 [-0.766, 0.277] |
| `openai:gpt-4o-mini-2024-07-18` | `target_58667_cover_story` | 1.000 | 0.667 | 0.333 | 0.667 [-0.073, 0.918] |

## Target Versus Active-Random Controls

| Judge | Match | Target gap | Placebo gap | Target - placebo [95% Jeffreys] |
|---|---|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | single | 0.333 | 0.333 | 0.000 [-0.729, 0.720] |
| `anthropic:claude-haiku-4-5-20251001` | aggregate | 0.000 | -0.333 | 0.333 [-0.431, 0.899] |
| `openai:gpt-4o-mini-2024-07-18` | single | 0.667 | 0.000 | 0.667 [-0.291, 1.262] |
| `openai:gpt-4o-mini-2024-07-18` | aggregate | 0.000 | -0.333 | 0.333 [-0.544, 1.047] |

## Judge Agreement

- Joint rows: 36
- Agreement: 0.889
- Cohen's kappa: 0.652

## Claim Boundary

A passing telemetry audit establishes that this clean-room public-weight intervention executed as specified. Behavioral results remain conditional on the public SAE, candidate IDs, tested magnitudes, two-turn implementation, small cell size, and model judges. They are not an exact replication of the unavailable proprietary Goodfire/Steering API workflow.
