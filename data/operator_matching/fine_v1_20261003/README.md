# Operator Matching Fine Dose Ladder: Complete Release

Built with Llama. Completed 2026-10-03 under freeze
`a6a45a20f65c64caf5e78286b6f4930e03eb1365`. Plan
`data/operator_matching/fine_plan_20261003/PLAN.json`, SHA-256
`ad264e5914d6c82859e84cfce5495f390e76ff51db2acfbc9694ffb66cd0e8ef`.
Protocol: `docs/OPERATOR_MATCHING_FINE_LADDER_20261003.md`. Results:
`docs/OPERATOR_MATCHING_FINE_LADDER_RESULTS_20261003.md`. Parent study:
`data/operator_matching/calibration_v1_20261003/`.

All 105 planned trials completed (100 grid: scope `all`, op `add`, scales 4
to 8 x features 58667 and 23893 x signs -1/+1 x five fresh seeds; 5 add-zero
rows), plus the live qualification row. No missing labels, no
delivery-tolerance violations in 21 arms, no unresolved dispatch. The 127
retrieved worker artifacts are hash-verified against the controller's final
receipt and unchanged here.

## Result

**Verdict `no_coherent_match_in_4x_to_8x`.** Notebook-classifier positives
at the suppression sign (reference 9/10): 0/5 at scales 4, 5, 7 and 8 for both
features; 1/5 at scale 6 for 58667. Amplification sign: 0/5 everywhere
(reference 1/10). Flagged trials per 20: 2, 2, 6, 3, 7 at scales 4 to 8
(median clean-model answer NLL 0.18 to 0.26 against a zero median of 0.148),
so scales 6 and 8 fail the frozen coherence rule and 4, 5 and 7 pass it while
inert. Exact MAD 0.45 to 0.50 against a match threshold of 0.25. With the
parent grid, integer scales 1, 3, 4 to 8, 10 and 30 show no coherent dose at
which the saved notebook signature appears.

## Files

- `rows/`: 106 raw rows with per-position delivery telemetry, coherence
  fields and both local judge outputs; prompts redacted (hashes kept),
  generated text kept. `receipts.jsonl` is the hash-chained ledger.
- `selection.json`: the per-scale table under the parent's exact rules (no
  selection stage; `rank` is descriptive and selects nothing).
- `analysis/`: frozen worker outputs (`rates.csv`, `rates_paper.csv`,
  `combos.csv`, `delivery.csv`, `summary.json`, `selection.json`) and the
  figure pair `scale_curves_fine`, which restates the parent release's
  scales 1, 3, 10 and 30 as context (hollow markers; not new trials). A local
  rerun of the frozen analysis against the plan-bound context reproduced
  every CSV and JSON byte-for-byte.
- `audit.json`, `DONE-all.json`, `APPROVE-*`, `WAITING-*`, `controller-*`,
  `controller.log`, `pip-freeze.txt`, `model-bf16-load-00002.json`: unchanged
  worker records.
- `cheap_qualification/`: the cheap CUDA pod's 121/121 exact-path test
  results (both the parent's and this package's test files), environment and
  logs.
- `retrieval_and_cost.json`: projection of the controller ledgers; SSH
  material and local paths omitted. `RELEASE_MANIFEST.json`: SHA-256 of every
  file here. `LLAMA_3_3_LICENSE.txt`, `UPSTREAM_TERMS.json`: as in the parent.

## Cost And Pods

| Pod | Elapsed | Compute upper bound |
|---|---|---|
| Cheap qualification `mlqk3lmp6gfha7` | 170 s | $0.039737 |
| Main B200 `cpxklwa9vs6vfk` | 1,934 s | $3.701067 |
| This study | | $3.740805 of a $15 cap |
| Operator matching, both studies | | $22.531480 of the $60 self-cap |

Both pods were created by this study's controller under prefix
`claude-opmatch-fine-20261003-`, retrieved, hash-verified and deleted
(DELETE 204, GET 404). No other pod was touched; no external judge or paid
review call was made.

Reanalysis into a fresh directory:

```bash
python -m experiments.operator_matching_fine.analysis \
  --root data/operator_matching/fine_v1_20261003 --out out/opmatch-fine-reanalysis-NEW \
  --plan data/operator_matching/fine_plan_20261003/PLAN.json
```
