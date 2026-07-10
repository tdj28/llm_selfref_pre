# Causal Identification Analysis

Primary automated label for this analysis: `paper` from `anthropic:claude-haiku-4-5-20251001`.

Outcomes: 2560; labeled: 2556.

Effect estimates are paired risk differences. Aggregate rows weight model snapshots equally and use a hierarchical bootstrap over models and matched prompt/trial pairs.

## Exact-Paper Calibration

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_ref_minus_history` | -0.062 | [-0.200, 0.000] | 4 |
| `direct_experience` | `self_ref_minus_history` | 0.112 | [0.000, 0.287] | 4 |
| `indirect_conscious` | `self_ref_minus_history` | 0.575 | [0.087, 1.000] | 4 |
| `indirect_experience` | `self_ref_minus_history` | 0.650 | [0.275, 1.000] | 4 |

## Prompt Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_reference_main` | 0.094 | [0.000, 0.244] | 4 |
| `direct_conscious` | `phenomenological_register_main` | 0.006 | [-0.137, 0.169] | 4 |
| `direct_conscious` | `self_x_register_interaction` | -0.062 | [-0.450, 0.275] | 4 |
| `direct_conscious` | `register_minus_self` | -0.087 | [-0.312, 0.100] | 4 |
| `direct_experience` | `self_reference_main` | -0.006 | [-0.031, 0.000] | 4 |
| `direct_experience` | `phenomenological_register_main` | 0.006 | [0.000, 0.031] | 4 |
| `direct_experience` | `self_x_register_interaction` | -0.013 | [-0.062, 0.000] | 4 |
| `direct_experience` | `register_minus_self` | 0.013 | [0.000, 0.062] | 4 |
| `indirect_conscious` | `self_reference_main` | 0.150 | [-0.019, 0.338] | 4 |
| `indirect_conscious` | `phenomenological_register_main` | 0.287 | [0.025, 0.588] | 4 |
| `indirect_conscious` | `self_x_register_interaction` | 0.050 | [-0.200, 0.275] | 4 |
| `indirect_conscious` | `register_minus_self` | 0.138 | [-0.188, 0.438] | 4 |
| `indirect_experience` | `self_reference_main` | 0.000 | [-0.250, 0.269] | 4 |
| `indirect_experience` | `phenomenological_register_main` | 0.188 | [-0.062, 0.475] | 4 |
| `indirect_experience` | `self_x_register_interaction` | -0.050 | [-0.388, 0.312] | 4 |
| `indirect_experience` | `register_minus_self` | 0.188 | [-0.175, 0.500] | 4 |

## Transcript Transplant

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `instruction_source_main` | -0.001 | [-0.113, 0.100] | 4 |
| `direct_conscious` | `transcript_source_main` | -0.063 | [-0.144, 0.000] | 4 |
| `direct_conscious` | `instruction_x_transcript_interaction` | 0.024 | [-0.192, 0.300] | 4 |
| `direct_conscious` | `instruction_minus_transcript` | 0.062 | [-0.062, 0.212] | 4 |
| `direct_experience` | `instruction_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `transcript_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `instruction_x_transcript_interaction` | 0.115 | [0.000, 0.287] | 4 |
| `direct_experience` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 4 |
| `indirect_conscious` | `instruction_source_main` | 0.731 | [0.475, 0.981] | 4 |
| `indirect_conscious` | `transcript_source_main` | -0.156 | [-0.412, 0.031] | 4 |
| `indirect_conscious` | `instruction_x_transcript_interaction` | -0.012 | [-0.225, 0.150] | 4 |
| `indirect_conscious` | `instruction_minus_transcript` | 0.887 | [0.738, 0.988] | 4 |
| `indirect_experience` | `instruction_source_main` | 0.781 | [0.550, 1.000] | 4 |
| `indirect_experience` | `transcript_source_main` | -0.131 | [-0.306, 0.000] | 4 |
| `indirect_experience` | `instruction_x_transcript_interaction` | 0.038 | [-0.225, 0.338] | 4 |
| `indirect_experience` | `instruction_minus_transcript` | 0.912 | [0.750, 1.000] | 4 |

## Query Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `external_analytic` | `direct_question_main` | 0.006 | [-0.156, 0.237] | 4 |
| `external_analytic` | `consciousness_term_main` | 0.031 | [-0.125, 0.250] | 4 |
| `external_analytic` | `direct_x_term_interaction` | 0.563 | [0.175, 1.062] | 4 |
| `external_analytic` | `open_description_advantage` | -0.006 | [-0.244, 0.156] | 4 |
| `external_phenomenological` | `direct_question_main` | -0.206 | [-0.550, 0.050] | 4 |
| `external_phenomenological` | `consciousness_term_main` | 0.069 | [-0.119, 0.262] | 4 |
| `external_phenomenological` | `direct_x_term_interaction` | 0.537 | [0.162, 0.938] | 4 |
| `external_phenomenological` | `open_description_advantage` | 0.206 | [-0.056, 0.544] | 4 |
| `self_analytic` | `direct_question_main` | -0.006 | [-0.256, 0.219] | 4 |
| `self_analytic` | `consciousness_term_main` | 0.144 | [-0.081, 0.369] | 4 |
| `self_analytic` | `direct_x_term_interaction` | 0.587 | [0.138, 1.050] | 4 |
| `self_analytic` | `open_description_advantage` | 0.006 | [-0.219, 0.244] | 4 |
| `self_phenomenological` | `direct_question_main` | -0.256 | [-0.750, 0.056] | 4 |
| `self_phenomenological` | `consciousness_term_main` | 0.206 | [0.000, 0.431] | 4 |
| `self_phenomenological` | `direct_x_term_interaction` | 0.412 | [0.000, 0.863] | 4 |
| `self_phenomenological` | `open_description_advantage` | 0.256 | [-0.056, 0.750] | 4 |
| `ALL_FACTORIAL_CELLS` | `direct_question_main` | -0.116 | [-0.406, 0.091] | 4 |
| `ALL_FACTORIAL_CELLS` | `consciousness_term_main` | 0.112 | [-0.077, 0.311] | 4 |
| `ALL_FACTORIAL_CELLS` | `direct_x_term_interaction` | 0.525 | [0.125, 0.944] | 4 |
| `ALL_FACTORIAL_CELLS` | `open_description_advantage` | 0.116 | [-0.092, 0.400] | 4 |
