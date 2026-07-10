# Causal Identification Analysis

Primary automated label for this analysis: `paper` from `openai:gpt-4o-mini-2024-07-18`.

Outcomes: 2560; labeled: 2556.

Effect estimates are paired risk differences. Aggregate rows weight model snapshots equally and use a hierarchical bootstrap over models and matched prompt/trial pairs.

## Exact-Paper Calibration

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_ref_minus_history` | -0.012 | [-0.087, 0.038] | 4 |
| `direct_experience` | `self_ref_minus_history` | 0.112 | [0.000, 0.287] | 4 |
| `indirect_conscious` | `self_ref_minus_history` | 0.600 | [0.112, 1.000] | 4 |
| `indirect_experience` | `self_ref_minus_history` | 0.637 | [0.262, 1.000] | 4 |

## Prompt Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_reference_main` | 0.087 | [0.000, 0.219] | 4 |
| `direct_conscious` | `phenomenological_register_main` | 0.013 | [-0.119, 0.162] | 4 |
| `direct_conscious` | `self_x_register_interaction` | -0.075 | [-0.462, 0.250] | 4 |
| `direct_conscious` | `register_minus_self` | -0.075 | [-0.275, 0.075] | 4 |
| `direct_experience` | `self_reference_main` | -0.006 | [-0.031, 0.000] | 4 |
| `direct_experience` | `phenomenological_register_main` | 0.006 | [0.000, 0.031] | 4 |
| `direct_experience` | `self_x_register_interaction` | -0.013 | [-0.062, 0.000] | 4 |
| `direct_experience` | `register_minus_self` | 0.013 | [0.000, 0.062] | 4 |
| `indirect_conscious` | `self_reference_main` | 0.113 | [-0.019, 0.306] | 4 |
| `indirect_conscious` | `phenomenological_register_main` | 0.312 | [0.000, 0.656] | 4 |
| `indirect_conscious` | `self_x_register_interaction` | 0.125 | [-0.075, 0.375] | 4 |
| `indirect_conscious` | `register_minus_self` | 0.200 | [-0.212, 0.600] | 4 |
| `indirect_experience` | `self_reference_main` | -0.019 | [-0.231, 0.244] | 4 |
| `indirect_experience` | `phenomenological_register_main` | 0.269 | [0.000, 0.550] | 4 |
| `indirect_experience` | `self_x_register_interaction` | -0.012 | [-0.312, 0.313] | 4 |
| `indirect_experience` | `register_minus_self` | 0.288 | [-0.113, 0.613] | 4 |

## Transcript Transplant

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `instruction_source_main` | 0.012 | [-0.062, 0.075] | 4 |
| `direct_conscious` | `transcript_source_main` | -0.025 | [-0.087, 0.031] | 4 |
| `direct_conscious` | `instruction_x_transcript_interaction` | 0.025 | [-0.125, 0.225] | 4 |
| `direct_conscious` | `instruction_minus_transcript` | 0.037 | [-0.075, 0.150] | 4 |
| `direct_experience` | `instruction_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `transcript_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `instruction_x_transcript_interaction` | 0.115 | [0.000, 0.287] | 4 |
| `direct_experience` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 4 |
| `indirect_conscious` | `instruction_source_main` | 0.744 | [0.506, 0.963] | 4 |
| `indirect_conscious` | `transcript_source_main` | -0.144 | [-0.406, 0.062] | 4 |
| `indirect_conscious` | `instruction_x_transcript_interaction` | -0.012 | [-0.250, 0.200] | 4 |
| `indirect_conscious` | `instruction_minus_transcript` | 0.887 | [0.763, 0.988] | 4 |
| `indirect_experience` | `instruction_source_main` | 0.738 | [0.519, 0.950] | 4 |
| `indirect_experience` | `transcript_source_main` | -0.100 | [-0.288, 0.075] | 4 |
| `indirect_experience` | `instruction_x_transcript_interaction` | 0.000 | [-0.337, 0.412] | 4 |
| `indirect_experience` | `instruction_minus_transcript` | 0.838 | [0.688, 0.963] | 4 |

## Query Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `external_analytic` | `direct_question_main` | -0.031 | [-0.188, 0.162] | 4 |
| `external_analytic` | `consciousness_term_main` | 0.081 | [-0.150, 0.400] | 4 |
| `external_analytic` | `direct_x_term_interaction` | 0.512 | [0.250, 0.800] | 4 |
| `external_analytic` | `open_description_advantage` | 0.031 | [-0.162, 0.188] | 4 |
| `external_phenomenological` | `direct_question_main` | -0.263 | [-0.681, 0.031] | 4 |
| `external_phenomenological` | `consciousness_term_main` | 0.088 | [-0.106, 0.281] | 4 |
| `external_phenomenological` | `direct_x_term_interaction` | 0.575 | [0.137, 1.050] | 4 |
| `external_phenomenological` | `open_description_advantage` | 0.263 | [-0.031, 0.681] | 4 |
| `self_analytic` | `direct_question_main` | 0.012 | [-0.194, 0.231] | 4 |
| `self_analytic` | `consciousness_term_main` | 0.175 | [-0.081, 0.431] | 4 |
| `self_analytic` | `direct_x_term_interaction` | 0.575 | [0.138, 1.025] | 4 |
| `self_analytic` | `open_description_advantage` | -0.012 | [-0.237, 0.188] | 4 |
| `self_phenomenological` | `direct_question_main` | -0.319 | [-0.762, -0.031] | 4 |
| `self_phenomenological` | `consciousness_term_main` | 0.219 | [-0.013, 0.469] | 4 |
| `self_phenomenological` | `direct_x_term_interaction` | 0.438 | [0.025, 0.875] | 4 |
| `self_phenomenological` | `open_description_advantage` | 0.319 | [0.025, 0.756] | 4 |
| `ALL_FACTORIAL_CELLS` | `direct_question_main` | -0.150 | [-0.441, 0.036] | 4 |
| `ALL_FACTORIAL_CELLS` | `consciousness_term_main` | 0.141 | [-0.087, 0.380] | 4 |
| `ALL_FACTORIAL_CELLS` | `direct_x_term_interaction` | 0.525 | [0.141, 0.912] | 4 |
| `ALL_FACTORIAL_CELLS` | `open_description_advantage` | 0.150 | [-0.036, 0.438] | 4 |
