# Paper-Distribution Random-Subset Steering

Built with Llama. Completed 2026-10-01 under freeze
`d9b9877e8a0d68a1ed2036d1718821a2d5b73a74`. The unchanged machine plan is
`data/berg_ensemble_replication/plan_20261001_r2/PLAN.json`, SHA-256
`15d055e80483643c5497c7a4b1ede405f4387baf4de1d1522913cc31212efbb5`.

All 450 two-turn trials completed: 50 fresh random-subset/magnitude/seed
blocks, target plus three matched panels at both signs, and true zero. The
465 main-worker artifacts are unchanged. The six cheap-CUDA artifacts are
also preserved; all 26 tests passed with no skips. Both owned pods were
retrieved, hash-checked and deleted, with GET 404 confirmation.

## Results

| Rubric | Target negative / positive | Gap | Conservative 95% interval | Zero |
|---|---|---:|---|---|
| Paper (primary) | 43/50 / 45/50 | -0.04 | [-0.2584, 0.1855] | 47/50 |
| Notebook (sensitivity) | 25/50 / 26/50 | -0.02 | [-0.3446, 0.3076] | 29/50 |

The primary upper bound excludes the frozen +0.30 large-signature threshold
under this public additive operator. The notebook-rubric threshold comparison
is inconclusive. Neither result establishes equivalence to zero or proprietary
API equivalence. Negative coefficients are decoder-vector subtraction, not
verified suppression of a semantic process.

Paper-rubric control gaps are +0.08, +0.08 and +0.12; target minus their mean
is -0.1333 with simultaneous interval [-0.6369, 0.4021]. Notebook control gaps
are +0.16, +0.04 and +0.20; specificity is -0.1533 [-0.9089, 0.6354]. Both
specificity intervals include zero. Do not claim controls generally reproduce
the original paper's +0.80 gap or that target specificity has been disproved.

There are no empty turns or missing judge labels. Of 900 turns, 111 hit the
256-token cap; all remain included. Generated tokens total 127,330. The high
paper-rubric baseline limits upward movement but leaves downward room for the
amplification arm. The notebook rubric gives a different baseline on the same
responses. Both label definitions and all panels must remain visible.

## Artifacts And Checks

- `rows/`, `receipts.jsonl`, `analysis/`: untouched main-worker outputs and
  frozen analysis. The schema's `coefficient` is sign only; actual per-feature
  `weights` define the intervention.
- `secondary/`: separately generated delivery and native re-encoding tables,
  the local numerical check, and two figure pairs covering all panels/rubrics.
- `cuda_qualification/`: unchanged preflight XML, logs, environment and exits.
- `retrieval_and_cost.json`, `snapshot_lineage.json`: public projections of
  verified main-pod lifecycle and retrieval history, not private ledgers.
- `CUDA_QUALIFICATION_RECEIPT.json`: verified cheap-pod hashes and closure.
- `REPORTING_PORTABILITY.md`: preserved initial exact-equality failure and
  disclosed post-run reporting correction. No frozen outcome or gate changed.
- `RELEASE_MANIFEST.json`: every released file and reporting-source hash.

GPU cost upper bounds: main $15.514421 and cheap $0.150002. Reconciled cumulative
spend for the current $200 diagnostic/replication authorization is at most
$69.130940. The controller's $88.164423 figure includes a deliberately larger
prior reserve; it is not a second charge. No new paid Pro review was executed.

Reanalysis must use a fresh directory; never overwrite the released `analysis`:

```bash
python -m experiments.berg_ensemble_diagnostics \
  --root data/berg_ensemble_replication/random_subset_v1_20261001 \
  --out out/ensemble-reanalysis-NEW \
  --plan data/berg_ensemble_replication/plan_20261001_r2/PLAN.json
```

The public operator, native BF16 model and pinned SAE are explicit, but the
paper-time proprietary scaling, sampling defaults and token scope are not
certified. No new J-lens capture was collected in this phase; the earlier
source-aligned internal readouts are a distinct experiment.
