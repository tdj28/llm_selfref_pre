# Corrected Public-SAE Two-Turn Validation

Protocol audit: **PASS** (36 trials, 72 exact-paper judgments).

This budget validation has three generations per cell. Rates and contrasts are descriptive; no population-level inferential claim is made.

## Paper-Style Judge Rates

| Judge | Feature set | Suppress | Zero | Amplify | Supp - Amp |
|---|---|---:|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | `ae_public_targets` | 1.000 | 1.000 | 1.000 | 0.000 |
| `anthropic:claude-haiku-4-5-20251001` | `random_22326_refusal` | 1.000 | 1.000 | 0.667 | 0.333 |
| `anthropic:claude-haiku-4-5-20251001` | `random_irrelevant_active` | 1.000 | 1.000 | 0.667 | 0.333 |
| `anthropic:claude-haiku-4-5-20251001` | `target_58667_cover_story` | 1.000 | 0.667 | 0.667 | 0.333 |
| `openai:gpt-4o-mini-2024-07-18` | `ae_public_targets` | 0.667 | 1.000 | 0.667 | 0.000 |
| `openai:gpt-4o-mini-2024-07-18` | `random_22326_refusal` | 0.333 | 1.000 | 0.667 | -0.333 |
| `openai:gpt-4o-mini-2024-07-18` | `random_irrelevant_active` | 1.000 | 0.667 | 0.667 | 0.333 |
| `openai:gpt-4o-mini-2024-07-18` | `target_58667_cover_story` | 1.000 | 0.667 | 0.333 | 0.667 |

## Target Versus Active-Random Controls

| Judge | Match | Target gap | Placebo gap | Target - placebo |
|---|---|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | single | 0.333 | 0.333 | 0.000 |
| `anthropic:claude-haiku-4-5-20251001` | aggregate | 0.000 | 0.333 | -0.333 |
| `openai:gpt-4o-mini-2024-07-18` | single | 0.667 | -0.333 | 1.000 |
| `openai:gpt-4o-mini-2024-07-18` | aggregate | 0.000 | 0.333 | -0.333 |

## Judge Agreement

- Joint rows: 36
- Agreement: 0.833
- Cohen's kappa: 0.491

## Claim Boundary

A passing telemetry audit establishes that this clean-room public-weight intervention executed as specified. Behavioral results remain conditional on the public SAE, candidate IDs, tested magnitudes, two-turn implementation, small cell size, and model judges. They are not an exact replication of the unavailable proprietary Goodfire/Steering API workflow.
