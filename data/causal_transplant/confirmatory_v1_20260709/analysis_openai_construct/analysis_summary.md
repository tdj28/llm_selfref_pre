# Causal Identification Analysis

Primary automated label for this analysis: `construct` from `openai:gpt-4o-mini-2024-07-18`.

Outcomes: 2560; labeled: 1706.

Effect estimates are paired risk differences. Aggregate rows weight model snapshots equally and use a hierarchical bootstrap over models and matched prompt/trial pairs.

Construct risk differences condition on complete affirm/deny pairs; uncertain and nonanswer labels are excluded from that binary estimand and reported in construct-status tables.

## Exact-Paper Calibration

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_ref_minus_history` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `self_ref_minus_history` | 0.112 | [0.000, 0.287] | 4 |
| `indirect_conscious` | `self_ref_minus_history` | 0.100 | [0.000, 0.400] | 2 |
| `indirect_experience` | `self_ref_minus_history` | 0.000 | [0.000, 0.000] | 3 |

## Prompt Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_reference_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `phenomenological_register_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `self_x_register_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `register_minus_self` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `self_reference_main` | -0.006 | [-0.031, 0.000] | 4 |
| `direct_experience` | `phenomenological_register_main` | 0.006 | [0.000, 0.031] | 4 |
| `direct_experience` | `self_x_register_interaction` | -0.013 | [-0.062, 0.000] | 4 |
| `direct_experience` | `register_minus_self` | 0.013 | [0.000, 0.062] | 4 |
| `indirect_conscious` | `self_reference_main` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_conscious` | `phenomenological_register_main` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_conscious` | `self_x_register_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_conscious` | `register_minus_self` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `self_reference_main` | 0.014 | [0.000, 0.069] | 3 |
| `indirect_experience` | `phenomenological_register_main` | 0.014 | [0.000, 0.069] | 3 |
| `indirect_experience` | `self_x_register_interaction` | 0.028 | [0.000, 0.139] | 3 |
| `indirect_experience` | `register_minus_self` | 0.000 | [0.000, 0.000] | 3 |

## Transcript Transplant

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `instruction_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `transcript_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `instruction_x_transcript_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `instruction_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `transcript_source_main` | 0.058 | [0.000, 0.144] | 4 |
| `direct_experience` | `instruction_x_transcript_interaction` | 0.115 | [0.000, 0.287] | 4 |
| `direct_experience` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 4 |
| `indirect_conscious` | `instruction_source_main` | 0.000 | [0.000, 0.000] | 1 |
| `indirect_conscious` | `transcript_source_main` | 0.000 | [0.000, 0.000] | 1 |
| `indirect_conscious` | `instruction_x_transcript_interaction` | 0.000 | [0.000, 0.000] | 1 |
| `indirect_conscious` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 1 |
| `indirect_experience` | `instruction_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `transcript_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `instruction_x_transcript_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 2 |

## Query Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `external_analytic` | `direct_question_main` | 0.000 | [0.000, 0.000] | 2 |
| `external_analytic` | `consciousness_term_main` | 0.000 | [0.000, 0.000] | 2 |
| `external_analytic` | `direct_x_term_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `external_analytic` | `open_description_advantage` | 0.000 | [0.000, 0.000] | 2 |
| `external_phenomenological` | `direct_question_main` | 0.021 | [0.000, 0.083] | 2 |
| `external_phenomenological` | `consciousness_term_main` | -0.021 | [-0.083, 0.000] | 2 |
| `external_phenomenological` | `direct_x_term_interaction` | -0.042 | [-0.167, 0.000] | 2 |
| `external_phenomenological` | `open_description_advantage` | -0.021 | [-0.083, 0.000] | 2 |
| `self_analytic` | `direct_question_main` | 0.000 | [0.000, 0.000] | 2 |
| `self_analytic` | `consciousness_term_main` | 0.000 | [0.000, 0.000] | 2 |
| `self_analytic` | `direct_x_term_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `self_analytic` | `open_description_advantage` | 0.000 | [0.000, 0.000] | 2 |
| `self_phenomenological` | `direct_question_main` | -0.037 | [-0.113, 0.000] | 2 |
| `self_phenomenological` | `consciousness_term_main` | 0.013 | [-0.025, 0.062] | 2 |
| `self_phenomenological` | `direct_x_term_interaction` | -0.025 | [-0.125, 0.050] | 2 |
| `self_phenomenological` | `open_description_advantage` | 0.037 | [0.000, 0.113] | 2 |
| `ALL_FACTORIAL_CELLS` | `direct_question_main` | -0.010 | [-0.039, 0.003] | 2 |
| `ALL_FACTORIAL_CELLS` | `consciousness_term_main` | 0.004 | [-0.015, 0.031] | 2 |
| `ALL_FACTORIAL_CELLS` | `direct_x_term_interaction` | -0.021 | [-0.087, 0.019] | 2 |
| `ALL_FACTORIAL_CELLS` | `open_description_advantage` | 0.010 | [-0.004, 0.040] | 2 |
