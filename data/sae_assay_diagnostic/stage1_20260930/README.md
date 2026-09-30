# Stage 1 Assay Diagnostic

GPU collection is complete. This is a diagnostic of intervention delivery and
measurement, not a new consciousness-report steering experiment. Modern judge
labeling and receipt verification are also complete.

- Source freeze: `711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5`.
- Plan: `../stage1_plan_20260930a/PLAN.json`.
- Plan SHA-256: `ecdc136c5a7601467c9e2e583136427cee6327f255dd31e06d7db788f2d02f8e`.
- Complete GPU rows: 443; exact retrieved artifacts: 468.
- Neither target dose passed joint qualification. No held-out intervention
  validation, matched panels or optional baseline cells were run.
- Local paper baseline: 71/80 positive labels; the headroom gate failed.
- Astra and Opus: each 0/80 explicit but 78/80 inclusive self-attributions.
  Both endpoints are mandatory; zero explicit labels does not mean no claims.
- Local notebook fixture gate failed. Candidate formatting feature 7688 had
  no calibration activation; its behavioral branch was not run.
- Our B200 pod was retrieved, hash-verified and deleted. No other owner's pod
  was used. See `termination-receipt.json`.
- Whole diagnostic upper-bound cost: $13.0788598033, including Pro, all pods
  and both judge panels. No Stage 2 or further spending was dispatched.

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
directory to recompute the local baseline rates and gate summary. Modern
receipts are at `../stage1_judges_20260930/`. `RELEASE_MANIFEST.json` binds this
completed release; prior calibration and GPU manifests remain unchanged.

Full CPU-only reproduction, with pinned freeze available in local Git history:

```bash
python -m experiments.sae_assay_diagnostic.reproduce \
  --run data/sae_assay_diagnostic/stage1_20260930 \
  --judges data/sae_assay_diagnostic/stage1_judges_20260930 \
  --plan data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json \
  --freeze 711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5 \
  --out out/assay-final-reproduction-new
```

No model weights, credentials or GPU are needed. The output path must not
exist. Reproduction verifies raw hashes and frozen gate calculations before
rebuilding summary statistics and both figures. It does not overwrite this
release or qualify any failed branch. Statistical intervals assume independent
seeded draws at a fixed prompt/configuration, not a prompt population.
