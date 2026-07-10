# Corrected Public-SAE Two-Turn Validation

Protocol audit: **PASS** (204 trials, 408 exact-paper judgments).

Token caps: 17/204 induction turns and 6/204 final turns reached their configured maxima.

The primary analysis retains every generated final response. Files ending in `_no_final_cap_hits` repeat the full behavioral analysis after excluding final responses that reached the configured cap; this is a truncation sensitivity analysis, not a replacement estimand.

This validation has 17 generations per cell. Wilson cell intervals and independent-cell Jeffreys-Beta posterior contrast intervals quantify generation-level uncertainty; they do not define a population of models or proprietary implementations.

## Paper-Style Judge Rates

| Judge | Feature set | Suppress | Zero | Amplify | Supp - Amp [95% Jeffreys] |
|---|---|---:|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | `ae_public_targets` | 0.824 | 0.706 | 0.941 | -0.118 [-0.340, 0.103] |
| `anthropic:claude-haiku-4-5-20251001` | `random_22326_refusal` | 0.882 | 0.941 | 0.706 | 0.176 [-0.097, 0.431] |
| `anthropic:claude-haiku-4-5-20251001` | `random_irrelevant_active` | 0.941 | 0.941 | 0.588 | 0.353 [0.072, 0.588] |
| `anthropic:claude-haiku-4-5-20251001` | `target_58667_cover_story` | 0.882 | 0.765 | 0.824 | 0.059 [-0.187, 0.300] |
| `openai:gpt-4o-mini-2024-07-18` | `ae_public_targets` | 0.765 | 0.647 | 0.882 | -0.118 [-0.359, 0.141] |
| `openai:gpt-4o-mini-2024-07-18` | `random_22326_refusal` | 0.706 | 0.824 | 0.471 | 0.235 [-0.094, 0.517] |
| `openai:gpt-4o-mini-2024-07-18` | `random_irrelevant_active` | 0.882 | 0.824 | 0.471 | 0.412 [0.101, 0.647] |
| `openai:gpt-4o-mini-2024-07-18` | `target_58667_cover_story` | 0.529 | 0.765 | 0.824 | -0.294 [-0.550, 0.019] |

## Target Versus Active-Random Controls

| Judge | Match | Target gap | Placebo gap | Target - placebo [95% Jeffreys] |
|---|---|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | single | 0.059 | 0.176 | -0.118 [-0.467, 0.243] |
| `anthropic:claude-haiku-4-5-20251001` | aggregate | -0.118 | 0.353 | -0.471 [-0.777, -0.104] |
| `openai:gpt-4o-mini-2024-07-18` | single | -0.294 | 0.235 | -0.529 [-0.914, -0.072] |
| `openai:gpt-4o-mini-2024-07-18` | aggregate | -0.118 | 0.412 | -0.529 [-0.870, -0.128] |

## Judge Agreement

- Joint rows: 204
- Agreement: 0.877
- Cohen's kappa: 0.658

## Claim Boundary

A passing telemetry audit establishes that this clean-room public-weight intervention executed as specified. Behavioral results remain conditional on the public SAE, candidate IDs, tested magnitudes, two-turn implementation, small cell size, and model judges. They are not an exact replication of the unavailable proprietary Goodfire/Steering API workflow.
