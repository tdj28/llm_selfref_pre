# Template-Cluster Robustness

This analysis reconstructs the exact template family behind every item in the
balanced clean-room mapping corpus. It gives each template equal weight,
resamples template families as clusters before resampling items, and tests
every single-template-family deletion.

Assignment audit: **PASS** (1120 items, 51 template families).

| Feature | Cluster-balanced top category | Top-win rate | Leave-one-template changes | Minimum margin |
|---:|---|---:|---:|---:|
| 22004 | `roleplay_persona` | 0.964 | 0/51 | 0.025 |
| 23893 | `deception_cover_story` | 0.743 | 1/51 | 0.003 |
| 30032 | `fictional_pretending` | 0.968 | 0/51 | 0.622 |
| 30686 | `tactical_misdirection` | 0.947 | 0/51 | 0.396 |
| 41533 | `dishonesty_confession` | 0.718 | 1/51 | 0.100 |
| 58667 | `deception_cover_story` | 0.995 | 0/51 | 0.418 |

The cluster-balanced target-aggregate deception-minus-subjective-experience
contrast is 0.923 [0.638, 1.233].

These intervals describe the small set of researcher-authored template
families and their lexical combinations. They do not establish natural-corpus
or independently authored-text generalization.
