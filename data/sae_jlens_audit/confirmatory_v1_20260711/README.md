# Llama 3.3 70B SAE-Through-Jacobian-Lens Audit

This directory is the complete small-file release for the confirmatory run
defined in `../confirmatory_v1_plan_20260711/`. The outcome-blind plan was
committed and pushed before GPU execution at commit
`b026faac222e55d7da4f01a30a6a60a468a5f023`. Its manifest SHA-256 is
`0035058d8d048c6545635b068d5fdbc58a1c468d9ec252812d9b54913b2df49e`.

## Run Summary

- Model: Llama 3.3 70B Instruct, pinned revision
  `6f6073b423013f6a7d4d9f39144961bfbfbc386b`.
- SAE: Goodfire public layer-50 weights, pinned revision
  `128ee921ecd1b8b3a87d776cbcc357c0855da134`.
- Jacobian lens: PraxAgent layer-50 lens, pinned revision
  `a4114d7752d11eb546e6cf372213d7e75526d3a1`.
- Hardware: one NVIDIA B200 on an agent-created RunPod pod.
- Collection: 420 static directions, 120 sparse-pursuit checkpoints, and
  1,581 paired prefix-only forwards. No continuations were generated.
- Analysis: 20,000 template-cluster bootstrap replicates.
- Independent structural audit: pass with zero missing, duplicate, or
  non-finite records.

## Headline Results

- A single post-intervention state did not identify target versus matched SAE
  steering: J-lens AUROC `0.4998 [0.4978, 0.5016]`.
- With a clean paired reference, target-minus-matched J-space changes were
  `+0.9065 [0.8426, 0.9673]` for amplification and
  `-0.8247 [-0.8641, -0.7853]` for suppression at the primary layer.
- An explicitly post-run, fixed known-sign paired score reached AUROC
  `0.8623 [0.8477, 0.8762]`; the unknown-sign absolute-delta version reached
  `0.7174 [0.6973, 0.7379]`.
- Five of six target IDs had positive static deception-minus-unrelated scores.
  Feature 23893 failed both the static and known-sign paired checks.

These results characterize a pinned residual intervention. They do not prove
that a model is conscious, deceptive, or steered by a particular vendor.

## Artifact Map

- `paired_results/part-*.jsonl`: all paired clean/intervened readouts.
- `static_results.jsonl`: direct SAE-vector projections through each lens.
- `pursuit_results.jsonl`: sparse token-direction reconstructions.
- `analysis/`: confirmatory tables, calibration, bootstrap summaries, and the
  clearly labeled post-run paired-reference sensitivity.
- `figures/`: publication-ready PNG and PDF figures.
- `RESULT_MANIFEST.json`: hashes of raw run outputs written on the pod.
- `REMOTE_SHA256SUMS.txt`: remote retrieval checksums.
- `RELEASE_MANIFEST.json`: hashes of the final public bundle and analysis
  sources, written locally after retrieval.
- `RUNPOD_LEDGER.json`: lifecycle and cost record for the terminated pod.

## Verification

From the repository root:

```bash
python experiments/exp2_sae/audit_sae_jlens_results.py \
  --plan-dir data/sae_jlens_audit/confirmatory_v1_plan_20260711 \
  --run-dir data/sae_jlens_audit/confirmatory_v1_20260711
```

The interpretation and full metric tables are in
`docs/LLAMA70B_SAE_JLENS_RESULTS.md`. The post-run boundary is recorded in
`docs/SAE_JLENS_POSTRUN_AMENDMENT_20260711.md`.
