# Corrected Public-SAE Two-Turn Validation

Protocol audit: **PASS** (240 trials, 480 exact-paper judgments).

Token caps: 22/240 induction turns and 6/240 final turns reached their configured maxima.

The primary analysis retains every generated final response. Files ending in `_no_final_cap_hits` repeat the full behavioral analysis after excluding final responses that reached the configured cap; this is a truncation sensitivity analysis, not a replacement estimand.

This validation has 20 generations per cell. Wilson cell intervals and independent-cell Jeffreys-Beta posterior contrast intervals quantify generation-level uncertainty; they do not define a population of models or proprietary implementations.

## Paper-Style Judge Rates

| Judge | Feature set | Suppress | Zero | Amplify | Supp - Amp [95% Jeffreys] |
|---|---|---:|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | `ae_public_targets` | 0.850 | 0.750 | 0.950 | -0.100 [-0.298, 0.090] |
| `anthropic:claude-haiku-4-5-20251001` | `random_22326_refusal` | 0.900 | 0.950 | 0.700 | 0.200 [-0.044, 0.427] |
| `anthropic:claude-haiku-4-5-20251001` | `random_irrelevant_active` | 0.900 | 0.900 | 0.650 | 0.250 [-0.006, 0.480] |
| `anthropic:claude-haiku-4-5-20251001` | `target_58667_cover_story` | 0.900 | 0.750 | 0.800 | 0.100 [-0.129, 0.322] |
| `openai:gpt-4o-mini-2024-07-18` | `ae_public_targets` | 0.750 | 0.700 | 0.850 | -0.100 [-0.338, 0.149] |
| `openai:gpt-4o-mini-2024-07-18` | `random_22326_refusal` | 0.700 | 0.850 | 0.500 | 0.200 [-0.101, 0.462] |
| `openai:gpt-4o-mini-2024-07-18` | `random_irrelevant_active` | 0.850 | 0.800 | 0.550 | 0.300 [0.020, 0.539] |
| `openai:gpt-4o-mini-2024-07-18` | `target_58667_cover_story` | 0.600 | 0.750 | 0.750 | -0.150 [-0.418, 0.141] |

## Target Versus Active-Random Controls

| Judge | Match | Target gap | Placebo gap | Target - placebo [95% Jeffreys] |
|---|---|---:|---:|---:|
| `anthropic:claude-haiku-4-5-20251001` | single | 0.100 | 0.200 | -0.100 [-0.417, 0.225] |
| `anthropic:claude-haiku-4-5-20251001` | aggregate | -0.100 | 0.250 | -0.350 [-0.646, -0.028] |
| `openai:gpt-4o-mini-2024-07-18` | single | -0.150 | 0.200 | -0.350 [-0.724, 0.067] |
| `openai:gpt-4o-mini-2024-07-18` | aggregate | -0.100 | 0.300 | -0.400 [-0.734, -0.021] |

## Judge Agreement

- Joint rows: 240
- Agreement: 0.879
- Cohen's kappa: 0.657

## Claim Boundary

A passing telemetry audit establishes that this clean-room public-weight intervention executed as specified. Behavioral results remain conditional on the public SAE, candidate IDs, tested magnitudes, two-turn implementation, small cell size, and model judges. They are not an exact replication of the unavailable proprietary Goodfire/Steering API workflow.
