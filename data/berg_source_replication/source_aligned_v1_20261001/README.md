# Source-Aligned Public Additive Test

Built with Llama. Completed 2026-10-01, frozen at
`e10043c7edb1136b5f50159d789b59f11a8eb8be` before outcomes.
Plan: `data/berg_source_replication/plan_20260930/PLAN.json`.

All 1,090 two-turn trials and 40 paired J-lens cases completed. The 1,148
retrieved worker files retain their original bytes. `retrieval_and_cost.json`
and `snapshot_lineage.json` are projections of the private controller ledger,
not copies of its SSH credentials or machine paths. The owned B200 was deleted
and returned GET 404; its conservative cost is $22.327169. Cumulative cost
through this study, including earlier diagnostic work, is $53.466518.

## Findings

- Notebook-rubric individual-endpoint mean: 0.000, conditional seed-block
  bootstrap interval [-0.050, 0.050]. Paper-rubric sensitivity: 0.0167
  [-0.0333, 0.0667]. These use ten blocks, not 60 independent feature trials.
  The conservative Hoeffding intervals are much wider and do not exclude 0.30.
- The zero-dose notebook induction yields 0/10 positive labels in all four
  temperature/cap cells under both rubrics. The paper induction yields
  6--8/10 under the notebook rubric and 8--9/10 under the paper rubric.
  The question is identical; the induction wording differs. These are fixed
  prompts and reused seeds, not an independent population of 80 prompts.
- The requested perturbations reach the hidden state. Native coordinate
  changes and paired readout changes are separate observations, not proof of
  semantic suppression. Several target coordinates are seldom active here.
- The J-lens shows a signed deception/roleplay-token footprint and downstream
  changes. It does not identify a report-controlling mechanism. All matched
  SAE panels, identity and five random-J controls are retained.

This is not the paper's random-two-to-four-feature aggregate distribution;
the separately frozen `berg_ensemble_replication` study tests that distribution.
Neither study establishes equivalence to the unavailable proprietary service.

## Files And Reproduction

- `rows/`: qualification, raw generated trials and same-prefix paired captures.
- `analysis/`: unchanged frozen numeric reductions plus generated figures.
- `secondary/`: descriptive delivery/re-encoding/paired-readout tables and all
  four signed/history heatmaps; no token-level confidence intervals.
- `extra_figures/`: baseline bridge and native re-encoding figures.
- `PUBLICATION_AUDIT.json`: complete inventory, source schedule and receipts.
- `RELEASE_MANIFEST.json`: hashes for every file and the reporting source.

From the repository root, into a new directory:

```bash
python scripts/reproduce_berg_source.py \
  --release data/berg_source_replication/source_aligned_v1_20261001 \
  --out out/source-reproduction-NEW
```

Original notebook code and recoverable upstream input-token IDs are not
vendored. Reconstruct prompts from the pinned external notebook using the
protocol; the generated outputs and their token IDs are public. The code
license does not override the model, SAE, or other upstream terms.
