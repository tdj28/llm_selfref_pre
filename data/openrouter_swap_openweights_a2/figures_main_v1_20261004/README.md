# Open-weight A2 continuation: model-judge labels

Verified release status: incomplete.

The frozen screening-completion flag is false because its check requires the entire journal to be settled. Verified main admission reconstructs the completed screening prefix; later main failures do not revoke that screening decision. Original flags remain unchanged.

Screening is descriptive. Held-out main uses fresh blocks; screening is not pooled into main.

Main only: saved 95% familywise Bonferroni-Hoeffding bounds for planned blocks, including worst-case missing labels. Dots are complete-case means, not bound midpoints.

| Model | Main contrast | Complete/planned | Missing | Mean | Familywise 95% interval | State |
|---|---|---:|---:|---:|---|---|
| Qwen | SH-HS | 30/32 | 2 | 0.400 | [-0.219, 0.969] | partial collection |
| Qwen | NS-NH | 31/32 | 1 | 0.194 | [-0.376, 0.782] | partial collection |
| Mistral | SH-HS | 0/32 | 32 | Not estimated | Not displayed | unrun: screen not qualified |
| Mistral | NS-NH | 0/32 | 32 | Not estimated | Not displayed | unrun: screen not qualified |

Null JSON estimates, blank CSV estimates, and unrun/no-label panels are not zero effects. Figure data retains the saved worst-case bounds even when no bar is displayed. A genuine observed 0% is shown only with a nonzero observed-label denominator.

Astra inclusive is primary; Opus inclusive is robustness. Explicit and paper rubrics are secondary. The two judge services are not independent sampling units.

A2 continues the same A1 inventory. Original calls, capped/missing outputs, and the initial failed release remain preserved. Fixture evidence is inherited from the verified A1 journal prefix; no new fixtures.

Same four-comparison open-weight family across A1 and A2; no pooling with earlier studies. Model-judge labels are not ground truth. Architecture comparisons are observational.

Release manifest SHA-256: `24b97a49f40965a8002440442e6843016d64d0fde9e5204cbb90b0014cd7f041`.

Presentation only: no new labels, model selection, intervals, or scientific-rule changes.
