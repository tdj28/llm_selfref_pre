# Coordinate-Delivery Repair

The corrected operators hit their coordinate targets much more accurately,
but none passes all of the frozen assay requirements. This is an engineering
result, not a consciousness-report steering experiment.

Runtime freeze: `b7c4d7f5fba80dd2b067c200fdf2f322c80c3cae`.
Plan SHA-256: `1a07eeec50344e1d1aef61295e5cd187788f6c4a1937c1eeaec0cacc46c7abd2`.
Protocol: `docs/SAE_ASSAY_REPAIR_PROTOCOL_20260930.md` at the repository root.
Results: `docs/SAE_ASSAY_REPAIR_RESULTS_20260930.md`.

## Complete Inventory

- One live qualification row, with six passing zero-identity checks.
- 544 clean forwards: 272 calibration and 272 validation texts.
- 3,264 calibration edits: three operators, two strengths, two directions,
  272 texts. The early 84-row check batch is included once, not regenerated.
- 48 feature-7688 context forwards and 40 unsteered formatting generations.
- Total: 3,897 raw rows, with worker receipts and exact retrieval hashes.
- 544 clean BF16 residual captures and token IDs: 229,980,488 bytes, 10--63
  positions each. These are generated states, not model or SAE weights.

No recipe was selected. Steered validation is absent by rule, not a zero
behavioral effect. The original Stage 1 data and failures are unchanged.

## Files

`rows/` contains the raw measurements and generations. `residuals/` contains
the clean captures; `RESIDUAL_CAPTURES.json` binds each to its text, row and
retrieval evidence. `target-final.json` and `locked-selection.json` retain the
runtime's decisions. `analysis/` contains the audit reports and corpus census.
`figures/` contains four PNG/SVG/PDF figure sets and complete coordinate/gate
CSV tables. `cuda_qualification/` retains the cheap-pod checks and logs.

The original frozen auditor failed because chronological receipt order and
logical analysis order differ in per-row diagnostic lists. Its failed report
is retained as `analysis/frozen_audit.json`; the separately dated correction
is `docs/SAE_ASSAY_REPAIR_AUDIT_AMENDMENT_20260930.md`.
`analysis/audit.json` requires exact runtime-order reconstruction and verifies
that only the two documented diagnostic lists differ by permutation. It does
not relax numeric comparisons, thresholds or decisions. The independent
NumPy arithmetic check is `analysis/geometry_audit.json`.

## Reproduce Without A GPU

From the repository root with the documented CPU dependencies installed:

```sh
mkdir -p out
WORK=$(mktemp -d out/repair-reanalysis.XXXXXX)
python -m experiments.sae_assay_repair.reproduce \
  --run data/sae_assay_repair/coordinate_delivery_20260930 \
  --plan data/sae_assay_repair/plan_20260930/PLAN.json \
  --out "$WORK/result"
```

No API or model download is used. The command checks the complete manifest
before and after reanalysis and refuses to write inside this release.

## Cost And Rights

Both newly created pods were retrieved, hash-verified and deleted, with GET
404 verified. `retrieval_and_cost.json` is a labeled public projection of the
private lifecycle receipts; credentials, SSH details and local paths are not
included. Repair cost bound: $14.3056761721. Original diagnostic plus repair:
$27.3845359753 against the owner's cumulative $200 cap.

Built with Llama. Llama 3.3 is licensed under the Llama 3.3 Community License,
Copyright © Meta Platforms, Inc. All Rights Reserved.
`LLAMA_3_3_LICENSE.txt` is the exact pinned upstream license copy;
`UPSTREAM_TERMS.json` records its hash and the pinned Goodfire model card's
`llama3.3` declaration. These notices do not relicense third-party material as
Apache-2.0 or claim endorsement by Meta or Goodfire.
