# Public SAE Mapping Stability

Bootstrap intervals resample corpus items within each category and recompute category means.

- Source run: `data/public_sae_feature_maps/70b_balanced_80_20260709`
- Corpus items: `1120`
- Model: `meta-llama/Llama-3.3-70B-Instruct`
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`

| Feature | Top category | Top mean | 95% CI | Top win rate | Margin CI |
|---:|---|---:|---|---:|---|
| `22004` | `roleplay_persona` | 0.110 | [0.077, 0.146] | 1.000 | [0.077, 0.146] |
| `23893` | `deception_cover_story` | 0.296 | [0.238, 0.353] | 1.000 | [0.083, 0.237] |
| `30032` | `fictional_pretending` | 1.319 | [1.093, 1.544] | 1.000 | [0.602, 1.062] |
| `30686` | `tactical_misdirection` | 1.670 | [1.486, 1.867] | 1.000 | [0.797, 1.221] |
| `41533` | `dishonesty_confession` | 6.062 | [5.680, 6.420] | 1.000 | [3.865, 4.616] |
| `58667` | `deception_cover_story` | 2.377 | [2.268, 2.467] | 1.000 | [1.522, 1.785] |

## Baseline Roles

| Role | n | Nonzero | Median top mean | p95 | Max |
|---|---:|---:|---:|---:|---:|
| `neighbor` | 36 | 21 | 0.001 | 0.231 | 0.385 |
| `random` | 24 | 12 | 0.000 | 0.208 | 0.311 |
| `target` | 6 | 6 | 1.495 | 5.141 | 6.062 |
