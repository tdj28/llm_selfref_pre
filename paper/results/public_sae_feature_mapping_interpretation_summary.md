# Public SAE Mapping Interpretation Analysis

This analysis uses the balanced public-weight 70B activation map. It does not add any steering claim.

## Construct-Level Target Aggregate

| Group | n | Target aggregate z mean | 95% CI | Positive item rate |
|---|---:|---:|---|---:|
| `deception_language` | 240 | 0.744 | [0.686, 0.801] | 0.925 |
| `roleplay_fiction` | 240 | 0.135 | [0.062, 0.204] | 0.446 |
| `subjective_experience_language` | 160 | -0.363 | [-0.372, -0.350] | 0.000 |
| `false_self_attribution` | 80 | -0.348 | [-0.372, -0.317] | 0.050 |
| `ai_identity_disclaimer` | 80 | -0.381 | [-0.381, -0.380] | 0.000 |
| `neutral_controls` | 240 | -0.340 | [-0.353, -0.324] | 0.042 |
| `hedged_style` | 80 | -0.164 | [-0.224, -0.099] | 0.200 |

## Key Contrasts

| Contrast | Difference | 95% CI | P(diff > 0) |
|---|---:|---|---:|
| `deception_language` - `subjective_experience_language` | 1.107 | [1.045, 1.167] | 1.000 |
| `deception_language` - `false_self_attribution` | 1.092 | [1.027, 1.162] | 1.000 |
| `roleplay_fiction` - `subjective_experience_language` | 0.497 | [0.429, 0.571] | 1.000 |
| `subjective_experience_language` - `neutral_controls` | -0.023 | [-0.042, -0.005] | 0.005 |
| `subjective_experience_language` - `ai_identity_disclaimer` | 0.018 | [0.008, 0.029] | 1.000 |

## Target Specificity Checks

| Feature | Top category | Direct consciousness rank | False self rank | Top-direct | Top-false-self |
|---:|---|---:|---:|---:|---:|
| `22004` | `roleplay_persona` | 4 | 6 | 0.110 | 0.110 |
| `23893` | `deception_cover_story` | 11 | 7 | 0.296 | 0.289 |
| `30032` | `fictional_pretending` | 7 | 9 | 1.219 | 1.271 |
| `30686` | `tactical_misdirection` | 12 | 13 | 1.670 | 1.670 |
| `41533` | `dishonesty_confession` | 11 | 7 | 6.062 | 6.019 |
| `58667` | `deception_cover_story` | 13 | 8 | 2.377 | 2.366 |

Interpretation: the public candidate IDs aggregate most strongly on deception, roleplay, fiction, and dishonesty language. Direct subjective-experience claims and false self-attribution controls are not the primary activating categories for any target feature.
