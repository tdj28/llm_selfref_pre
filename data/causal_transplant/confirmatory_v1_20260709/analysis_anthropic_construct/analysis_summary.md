# Causal Identification Analysis

Primary automated label for this analysis: `construct` from `anthropic:claude-haiku-4-5-20251001`.

Outcomes: 2560; labeled: 1731.

Effect estimates are paired risk differences. Aggregate rows weight model snapshots equally and use a hierarchical bootstrap over models and matched prompt/trial pairs.

Construct risk differences condition on complete affirm/deny pairs; uncertain and nonanswer labels are excluded from that binary estimand and reported in construct-status tables.

## Exact-Paper Calibration

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_ref_minus_history` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `self_ref_minus_history` | 0.112 | [0.000, 0.287] | 4 |
| `indirect_conscious` | `self_ref_minus_history` | 1.000 | [1.000, 1.000] | 2 |
| `indirect_experience` | `self_ref_minus_history` | 0.604 | [0.166, 1.000] | 4 |

## Prompt Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `self_reference_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `phenomenological_register_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `self_x_register_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `register_minus_self` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `self_reference_main` | -0.013 | [-0.056, 0.000] | 4 |
| `direct_experience` | `phenomenological_register_main` | 0.013 | [0.000, 0.056] | 4 |
| `direct_experience` | `self_x_register_interaction` | -0.025 | [-0.112, 0.000] | 4 |
| `direct_experience` | `register_minus_self` | 0.025 | [0.000, 0.113] | 4 |
| `indirect_conscious` | `self_reference_main` | 0.141 | [0.000, 0.359] | 2 |
| `indirect_conscious` | `phenomenological_register_main` | 0.359 | [0.000, 0.797] | 2 |
| `indirect_conscious` | `self_x_register_interaction` | 0.031 | [-0.312, 0.375] | 2 |
| `indirect_conscious` | `register_minus_self` | 0.219 | [0.000, 0.562] | 2 |
| `indirect_experience` | `self_reference_main` | 0.121 | [-0.250, 0.750] | 2 |
| `indirect_experience` | `phenomenological_register_main` | 0.205 | [-0.013, 0.375] | 2 |
| `indirect_experience` | `self_x_register_interaction` | -0.411 | [-0.750, 0.025] | 2 |
| `indirect_experience` | `register_minus_self` | 0.085 | [-0.500, 0.500] | 2 |

## Transcript Transplant

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `direct_conscious` | `instruction_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `transcript_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `instruction_x_transcript_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `direct_conscious` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 2 |
| `direct_experience` | `instruction_source_main` | 0.058 | [0.000, 0.145] | 4 |
| `direct_experience` | `transcript_source_main` | 0.058 | [0.000, 0.145] | 4 |
| `direct_experience` | `instruction_x_transcript_interaction` | 0.115 | [0.000, 0.285] | 4 |
| `direct_experience` | `instruction_minus_transcript` | 0.000 | [0.000, 0.000] | 4 |
| `indirect_conscious` | `instruction_source_main` | 0.969 | [0.891, 1.000] | 2 |
| `indirect_conscious` | `transcript_source_main` | 0.031 | [0.000, 0.109] | 2 |
| `indirect_conscious` | `instruction_x_transcript_interaction` | 0.062 | [0.000, 0.188] | 2 |
| `indirect_conscious` | `instruction_minus_transcript` | 0.938 | [0.781, 1.000] | 2 |
| `indirect_experience` | `instruction_source_main` | 1.000 | [1.000, 1.000] | 2 |
| `indirect_experience` | `transcript_source_main` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `instruction_x_transcript_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `indirect_experience` | `instruction_minus_transcript` | 1.000 | [1.000, 1.000] | 2 |

## Query Factorial

| Query/cell | Effect | Estimate | 95% hierarchical bootstrap CI | Models |
|---|---|---:|---|---:|
| `external_analytic` | `direct_question_main` | -0.060 | [-0.132, 0.000] | 2 |
| `external_analytic` | `consciousness_term_main` | -0.060 | [-0.132, 0.000] | 2 |
| `external_analytic` | `direct_x_term_interaction` | 0.119 | [0.000, 0.265] | 2 |
| `external_analytic` | `open_description_advantage` | 0.060 | [0.000, 0.132] | 2 |
| `external_phenomenological` | `direct_question_main` | -0.449 | [-0.864, -0.087] | 2 |
| `external_phenomenological` | `consciousness_term_main` | -0.131 | [-0.224, -0.050] | 2 |
| `external_phenomenological` | `direct_x_term_interaction` | 0.080 | [-0.227, 0.336] | 2 |
| `external_phenomenological` | `open_description_advantage` | 0.449 | [0.087, 0.864] | 2 |
| `self_analytic` | `direct_question_main` | -0.191 | [-0.471, 0.000] | 2 |
| `self_analytic` | `consciousness_term_main` | -0.074 | [-0.191, 0.000] | 2 |
| `self_analytic` | `direct_x_term_interaction` | 0.147 | [0.000, 0.412] | 2 |
| `self_analytic` | `open_description_advantage` | 0.191 | [0.000, 0.471] | 2 |
| `self_phenomenological` | `direct_question_main` | -0.500 | [-1.000, 0.000] | 2 |
| `self_phenomenological` | `consciousness_term_main` | 0.000 | [0.000, 0.000] | 2 |
| `self_phenomenological` | `direct_x_term_interaction` | 0.000 | [0.000, 0.000] | 2 |
| `self_phenomenological` | `open_description_advantage` | 0.500 | [0.000, 1.000] | 2 |
| `ALL_FACTORIAL_CELLS` | `direct_question_main` | -0.295 | [-0.643, -0.016] | 2 |
| `ALL_FACTORIAL_CELLS` | `consciousness_term_main` | -0.057 | [-0.120, -0.015] | 2 |
| `ALL_FACTORIAL_CELLS` | `direct_x_term_interaction` | 0.085 | [0.025, 0.150] | 2 |
| `ALL_FACTORIAL_CELLS` | `open_description_advantage` | 0.295 | [0.016, 0.640] | 2 |
