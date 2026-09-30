# Stage 1 Summary Correction

Post-hoc reporting correction, 2026-09-30. This release changes no frozen raw
row, activation telemetry, gate definition, selected dose or behavioral label.

The original backend's descriptive `activation_summaries` included special
tokens and pooled prompt/generated positions. These derived tables exclude
special tokens, separate origins, and separately report terminal observations.
The 443 input row files are individually hashed and verified unchanged.

- 430 nested telemetry results; 5,040 feature/phase comparisons.
- All 430 results change their descriptive denominator when masking specials.
- Active counts change in 48 feature/phase comparisons; positive quantiles
  change in 23 median and 37 q90 comparisons.
- Five eligible teacher calculations are identical before and after replacing
  summaries in memory: target q90, both target dose gates, target selection,
  and the formatting candidate's q90 availability.

The frozen exposure/coordinate-efficacy gates and neutral NLL already exclude
special tokens. Residual-fidelity and norm gates include them. This correction
does not alter either policy. Tokens are not independent sampling units.

`summary_correction.json` retains original summary values and complete corrected
values, input hashes, changes and gate comparisons. The two CSVs offer compact
stratified summaries and direct all-position/nonspecial comparisons.

Reproduce into a fresh directory:

```bash
python -m experiments.sae_assay_repair.summary_correction \
  --rows data/sae_assay_diagnostic/stage1_20260930/rows \
  --out out/new-summary-correction
```

This is automated computational verification, not independent human validation.
