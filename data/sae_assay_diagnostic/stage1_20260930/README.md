# Stage 1 Assay Diagnostic

GPU collection is complete. This is a diagnostic of intervention delivery and
measurement, not a new consciousness-report steering experiment. Modern judge
labeling is still in progress at this release checkpoint.

- Source freeze: `711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5`.
- Plan: `../stage1_plan_20260930a/PLAN.json`.
- Plan SHA-256: `ecdc136c5a7601467c9e2e583136427cee6327f255dd31e06d7db788f2d02f8e`.
- Complete GPU rows: 443; exact retrieved artifacts: 468.
- Neither target dose passed joint qualification. No held-out intervention
  validation, matched panels or optional baseline cells were run.
- Local paper baseline: 71/80 positive labels; the headroom gate failed.
- Local notebook fixture gate failed. Candidate formatting feature 7688 had
  no calibration activation; its behavioral branch was not run.
- Our B200 pod was retrieved, hash-verified and deleted. No other owner's pod
  was used. See `termination-receipt.json`.

`CALIBRATION_MANIFEST.json`, `CALIBRATION_README.md` and the calibration receipt
prefix are historical snapshots, retained unchanged. `GPU_MANIFEST.json` binds
all 468 byte-exact final remote artifacts. Raw rows must never be overwritten.
The detailed explanation is in `docs/SAE_ASSAY_STAGE1_RESULTS_20260930.md` at
the repository root. The labels are linguistic measurements, not observations
of subjective experience.

Read-only structural verification (no GPU or API required):

```bash
python -c 'from experiments.sae_assay_diagnostic.validate import validate_run_directory; r=validate_run_directory("data/sae_assay_diagnostic/stage1_20260930"); print(r["status"], r["errors"]); assert r["pass"]'
```

Raw receipt validation checks structural integrity, not semantic validity.
Run frozen `experiments.sae_assay_diagnostic.report` into a fresh ignored output
directory to recompute the local baseline rates and gate summary. The final
release will also bind the separately stored modern-judge receipts.
