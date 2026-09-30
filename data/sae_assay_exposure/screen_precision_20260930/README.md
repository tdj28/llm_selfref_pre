# Exposure Screen And Precision Pilot

Completed 2026-09-30: 224 clean Llama 3.3 70B texts and 48 separate
teacher-forced pilot forwards. No generated responses or judge calls.

Both signed pilot branches delivered all 290 nonzero nonspecial requests
within the frozen fidelity and norm limits. This does **not** qualify the
six-feature assay: feature 22004 lacks the required exposure, and the frozen
33-text discovery selection leaves feature 30032 at 99 rather than the
required 100 positive positions. No thresholds or selections were changed.
Precision-sham drift is also comparable to the edit-versus-sham drift.

See the [results](../../../docs/SAE_ASSAY_EXPOSURE_RESULTS_20260930.md) and
[portability amendment](../../../docs/SAE_ASSAY_EXPOSURE_PORTABILITY_20260930.md).
The mixed FP32-residual pilot is a different operator from native BF16; its
readout promotes native BF16 SAE weights to FP32. Neither earlier operator
failures nor the missing six-feature qualification are overwritten.

## Provenance

- Scientific plan SHA-256:
  `52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9`.
- Original public freeze: `1d7ec700ac1a91f133ac851d5e179aa8dcfa803e`.
- Execution freeze after lifecycle-only A1 repair:
  `4635849ff374d2c389f2b785e97b8c736cb02876`.
- All 566 remote artifacts were retrieved and hash-verified before deletion
  of task-owned pod `gc21eirao2x4wd`. Direct GET returned 404.
- This successful attempt cost at most $2.867573. With the preserved failed
  startup, the follow-up cost at most $3.354069; cumulative diagnostics cost
  at most $30.989138 of the authorized $200.

`retrieval_and_cost.json` is a public projection of closure and retrieval
evidence, not the private lifecycle ledger. No credentials, SSH material,
model weights or private lifecycle files are included. The captures contain
our experimental activations on the frozen researcher-authored texts.
Upstream model and SAE provenance remains in the plan and load record;
these are not the original paper authors' code or data.

## Contents

- `rows/` and `residuals/`: all clean-screen rows and bounded BF16 captures.
- `precision_pilot/`: all four branches, raw rows, tensors and receipts.
- Root qualification, tokenization, load, summary and completion records.
- `analysis/`: descriptive CSVs, two PNG/PDF figure pairs, and audit records.
- `RELEASE_MANIFEST.json`: every released file's size and SHA-256.

The exposure figure retains all six IDs and all three partitions. Pilot loss
figures weight the 12 texts equally; the results document's loss table pools
the 1,248 nonspecial tokens. Both weightings are in `paired_losses.csv`.
Neither is a population-level uncertainty estimate.

## Preserved Audit Failures

An intermediate snapshot caught a raw row between writing and receipt.
`interim-local-audit.json` preserves that failure; `interim-receipt-prefix.json`
contains the exact receipt prefix. Final reconciliation verifies the prefix
and all 277 earlier scientific files byte-for-byte, including that row.

The original exact pilot validator passed on the Linux worker but failed
CPU FP64 metric equality on the ARM Mac. `final-exact-audit.json` preserves
that failure. The separate post-outcome `portability-audit.json` permits only
metric comparison at `rtol=atol=1e-12`; hashes, raw identities, thresholds,
per-position classifications and denominators remain exact. All 48 rows
pass this explicit amended check. Independent NumPy arithmetic agrees.
This is automated verification, not independent human validation.

## Reproduce Without A GPU

From the repository root, in the documented Python environment, write only
to a fresh ignored directory. Do not overwrite this release. The explicit
adapter keeps the original exact failure visible and leaves frozen sources
unchanged:

```python
from pathlib import Path
from tempfile import mkdtemp
from scripts.report_sae_exposure import generate_report
from scripts.sae_exposure_portability import publication_adapter

run = Path("data/sae_assay_exposure/screen_precision_20260930")
plan = Path("data/sae_assay_exposure/plan_20260930/PLAN.json")
freeze = "4635849ff374d2c389f2b785e97b8c736cb02876"
Path("out").mkdir(exist_ok=True)
out = Path(mkdtemp(prefix="exposure-reanalysis-", dir="out"))
with publication_adapter(
    out / "portability",
    prior_exact_audit=run / "analysis/final-exact-audit.json",
):
    generate_report(run, plan, freeze, out / "report")
print(out)
```

The raw observations, original failures and post-outcome corrections are
separate artifacts. A successful reproduction of this pilot cannot establish
behavioral efficacy, semantic specificity or anything about consciousness.
