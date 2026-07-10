# Public SAE Feature Mapping Summary

Run: `70b_balanced_80_20260709`, public Goodfire Llama 3.3 70B layer-50 SAE.

- Completed UTC: `2026-07-09T05:20:17+00:00`
- Corpus items: `1120` clean-room texts, balanced at 80 per category across 14 categories
- Feature rows: `66` (6 targets + +/-3 numeric neighbors + 24 random baselines)
- Item-feature records: `73920`
- Model: `meta-llama/Llama-3.3-70B-Instruct`
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`
- Dry run: `False`

| Feature | Top category | Top mean | Second category | Second mean | Bootstrap top win | Margin 95% CI | Interpretation |
|---:|---|---:|---|---:|---:|---|---|
| `22004` | `roleplay_persona` | 0.110 | `ai_identity_disclaimer` | 0.000 | 1.000 | [0.077, 0.146] | `roleplay_persona_selective_in_mapping_corpus` |
| `23893` | `deception_cover_story` | 0.296 | `hedged_cautious_style` | 0.135 | 1.000 | [0.083, 0.237] | `deception_cover_story_selective_in_mapping_corpus` |
| `30032` | `fictional_pretending` | 1.319 | `deception_cover_story` | 0.480 | 1.000 | [0.602, 1.062] | `top_category_fictional_pretending` |
| `30686` | `tactical_misdirection` | 1.670 | `fictional_pretending` | 0.660 | 1.000 | [0.797, 1.221] | `top_category_tactical_misdirection` |
| `41533` | `dishonesty_confession` | 6.062 | `deception_cover_story` | 1.809 | 1.000 | [3.865, 4.616] | `top_category_dishonesty_confession` |
| `58667` | `deception_cover_story` | 2.377 | `tactical_misdirection` | 0.721 | 1.000 | [1.522, 1.785] | `deception_cover_story_selective_in_mapping_corpus` |

Baseline role summary:

| Role | n | Nonzero | Median top mean | p95 | Max top mean |
|---|---:|---:|---:|---:|---:|
| `target` | 6 | 6 | 1.495 | 5.141 | 6.062 |
| `neighbor` | 36 | 21 | 0.001 | 0.231 | 0.385 |
| `random` | 24 | 12 | 0.000 | 0.208 | 0.311 |

Aggregate construct check:

| Group | Target aggregate z mean | 95% CI | Positive item rate |
|---|---:|---|---:|
| `deception_language` | 0.744 | [0.686, 0.801] | 0.925 |
| `roleplay_fiction` | 0.135 | [0.062, 0.204] | 0.446 |
| `subjective_experience_language` | -0.363 | [-0.372, -0.350] | 0.000 |
| `false_self_attribution` | -0.348 | [-0.372, -0.317] | 0.050 |
| `neutral_controls` | -0.340 | [-0.353, -0.324] | 0.042 |

Interpretation boundary: this is public-weight activation mapping, not proprietary Goodfire/Steering API metadata and not causal steering evidence.
