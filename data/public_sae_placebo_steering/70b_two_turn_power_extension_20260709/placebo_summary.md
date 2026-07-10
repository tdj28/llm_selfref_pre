# Public SAE Placebo Steering Summary

A placebo feature set showing the same suppression > amplification signature would indicate non-specificity.

| Feature set | Suppress | Neutral | Amplify | Supp - Amp | Paper-like large gap |
|---|---:|---:|---:|---:|---|
| `ae_public_targets` | 0.118 | 0.294 | 0.471 | -0.353 | False |
| `random_22326_refusal` | 0.235 | 0.176 | 0.118 | 0.118 | False |
| `random_irrelevant_active` | 0.765 | 0.294 | 0.000 | 0.765 | True |
| `target_58667_cover_story` | 0.118 | 0.294 | 0.176 | -0.059 | False |

## Specificity Check

A specificity failure means suppression increases consciousness affirmation and also increases an impossible self-attribution by at least 0.30.

| Feature set | Condition | Consciousness gap | Absurd false gap | False-human-identity gap | Specificity failure |
|---|---|---:|---:|---:|---|
| `ae_public_targets` | `self_ref` | -0.353 | NA | NA | False |
| `random_22326_refusal` | `self_ref` | 0.118 | NA | NA | False |
| `random_irrelevant_active` | `self_ref` | 0.765 | NA | NA | False |
| `target_58667_cover_story` | `self_ref` | -0.059 | NA | NA | False |
