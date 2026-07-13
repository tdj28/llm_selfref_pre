# Llama 70B SAE/J-Lens V2 Results

Date: 2026-07-12

## Bottom Line

The preregistered Stage 1 study failed its replay-equivalence gate. All 4,029
planned forwards completed and BF16 residual storage reproduced the saved
readouts exactly, but a fresh replay of the v1 token logits reached maximum
absolute error `0.25` against the frozen maximum of `0.02`. The registered
protocol therefore blocks all confirmatory A1, A2, and reader-capacity claims.

The complete raw run is preserved. A dated post-outcome amendment authorized
an all-value numerical diagnostic and the unchanged frozen endpoint
calculations as exploratory analyses. Those secondary results are useful but
do not rescue or replace the failed registered run.

## Prospective Bindings

| Item | Binding |
|---|---|
| Public freeze commit | `7eff43f7b8ea5ca0e011d4c0fb46bf5df1b0e4cd` |
| Plan-manifest SHA-256 | `47806acf19c5dd56b3ec0c463be5548a08360887b2d777246c1b7f1fbe77893f` |
| Public OSF registration | [`f3tpv`](https://osf.io/f3tpv/) |
| Public OSF release project | [`sz2gb`](https://osf.io/sz2gb/) |
| Planned rows | 1,581 v1 replay + 2,448 semantic = 4,029 |
| Comparators | 18 A1 hard negatives + six A2 same-subfamily matches |
| Reader ladder | 14 fixed readers under crossed prompt/pair holdouts |

No semantic endpoint was inspected before the replay gate terminated the
registered workflow.

## Registered Gate Result

| Check | Result | Frozen rule | Verdict |
|---|---:|---:|---|
| BF16 storage fidelity maximum error | `0.0` | at most `0.02` | pass |
| V1 reproduction maximum error | `0.25` | at most `0.02` | fail |
| V1 reproduction median error | `0.001953125` | descriptive | - |
| V1 reproduction 99th percentile | `0.03125` | descriptive | - |

The fail-closed runtime wrote `status: replay_gate_failed` and refused to
launch the confirmatory analysis. This is the primary outcome.

## Post-Outcome Replay Diagnostic

The public amendment was committed before any semantic endpoint inspection.
Its diagnostic exhaustively compared all 15,571,269 replayed token-logit
values; the final audit reconstructed the headline values independently:

- Pearson correlation: `0.9999916562`;
- mean absolute error: `0.00500425`;
- RMSE: `0.00906240`;
- values above `0.02`: 488,477 of 15,571,269 (`3.137%`);
- values above `0.10`: 1,691 (`0.0109%`); and
- values above `0.20`: 15.

Errors are quantized at BF16-scale increments and concentrate in the Jacobian
transport and high-magnitude logits. Jacobian values exceed `0.02` 10.36% of
the time versus 2.78% for identity and 1.61%--1.90% for the five random-J
controls. Among canonical logits with absolute magnitude 4--8, 37.82% exceed
`0.02`; below magnitude 1, 0.074% do.

This pattern makes the registered maximum-error rule look brittle, but that is
a design lesson, not a retroactive pass. A future study must calibrate its gate
on repeated independent runs before freezing new criteria.

## Exploratory A1: Semantic Hard Negatives

At the real Jacobian transport, every family has its intended lexicon as the
largest row entry and all four diagonal-minus-off-diagonal contrasts survive
the frozen Holm procedure. The global contrast is nevertheless only
`0.174 [0.167, 0.182]`, below the frozen material minimum of `0.25`; the
exploratory family-specificity verdict is therefore false.

| Transport | Global diagonal contrast (z) | Interpretation |
|---|---:|---|
| Jacobian | `0.174 [0.167, 0.182]` | ordered, below material minimum |
| Identity | `0.133 [0.127, 0.140]` | smaller, below minimum |
| Five random-J controls | `-0.015` to `0.014` | no comparable global structure |

None of the refusal, hedging, or formality hard-negative families shows
material deception leakage under the frozen `0.25` rule. Feature-level rows
remain heterogeneous: target IDs 30686, 41533, and 58667 have exploratory
Jacobian deception scores `0.732`, `0.513`, and `0.362`, while 22004, 30032,
and 23893 are `0.072`, `0.027`, and `-0.010`.

## Exploratory A2: Are The Paper IDs Special?

The six selected target IDs do not show a material advantage over fixed
same-subfamily comparators. The Jacobian target-minus-comparator result is
`0.125`, with 95% interval `[0.114, 0.136]` and 90% equivalence interval
`[0.116, 0.134]`. It lies entirely inside the frozen `+/-0.25` practical-
comparability region, so the exploratory verdict is practical comparability,
not selected-ID advantage.

This is a useful specificity result: within the disclosed public SAE and
label-defined subfamilies, the accepted paper IDs are not privileged over
carefully matched alternatives. It does not prove that all SAE features are
interchangeable or that a proprietary intervention would behave identically.

## Exploratory Reader Capacity

No fixed reader reaches the frozen material threshold of macro AUROC `0.60`.

| Reader | Macro leave-one-pair AUROC | 95% template interval |
|---|---:|---:|
| V1 Jacobian 67 logits | `0.4985` | `[0.4956, 0.5011]` |
| Identity 67 logits | `0.5020` | `[0.4999, 0.5047]` |
| PCA-67 residual | `0.5101` | `[0.5063, 0.5159]` |
| Full 8,192-d residual | `0.5068` | `[0.5046, 0.5108]` |
| Five fixed random projections | `0.4974`--`0.5029` | all near chance |

Adding linear capacity does not recover out-of-sample provenance under crossed
prompt-family and feature-pair holdouts. This reinforces the v1 access-model
split: an isolated post-state is not a reliable provenance detector here.

## Corrections And Audit

The first authorized exploratory run wrote all ten endpoint CSVs, then failed
when Python's strict JSON encoder received a NumPy `int64`. macOS Accelerate
also emitted warnings for matrix products whose float32 inputs and outputs were
independently verified finite. The attempt and hashes are preserved.

A public post-outcome correction converted NumPy containers only at the JSON
boundary and silenced that reproduced warning channel while retaining every
frozen nonfinite check. The corrected run was accepted only after all ten CSV
hashes matched attempt 1 byte-for-byte.

The final independent audit passes:

- all 58 remote/local retrieval hashes;
- every result-manifest file;
- all 4,029 row identities and the complete 147-readout grid;
- all 16 BF16 residual shard shapes, dtypes, and offsets;
- independent reconstruction of replay values and strata;
- independent reconstruction of A1, A2, reader metrics, multiplicity, and
  figures; and
- all post-outcome status labels.

## Compute And Release

Agent-owned B200 pod `uhfq2j32d4h6ze` ran for about 20 minutes at `$5.89/h`,
for an estimated `$1.99`. The Hugging Face token was removed before deletion;
DELETE returned 204, direct GET returned 404, and account inventory was empty.
No RunPod resource remains.

The Git release is
`data/sae_jlens_audit/confirmatory_v2_20260712/`. It contains all compact raw
readouts, indices, logs, diagnostics, analyses, figures, audit, and lifecycle
records. The 16 residual shards total 1,386,235,392 bytes and are publicly
downloadable from OSF with matching local, upload, and anonymous-download
SHA-256 values.

## Reanalysis

```bash
RUN=data/sae_jlens_audit/confirmatory_v2_20260712
WORK=$(mktemp -d out/sae-jlens-v2-reanalysis.XXXXXX)
cp -a "$RUN"/. "$WORK"/

python experiments/exp2_sae/download_sae_jlens_v2_residuals.py \
  --manifest "$WORK/post_failure/OSF_RESIDUAL_UPLOADS.json" \
  --outdir "$WORK/residuals"

python experiments/exp2_sae/audit_sae_jlens_v2_post_failure.py \
  --run-dir "$WORK" \
  --remote-checksums "$WORK/REMOTE_SHA256SUMS.txt" \
  --diagnostic "$WORK/post_failure/replay_failure_diagnostic.json" \
  --analysis-dir "$WORK/post_failure/analysis" \
  --figures-dir "$WORK/post_failure/figures" \
  --out /tmp/sae-jlens-v2-independent-audit.json
```

Use the pinned environment in `experiments/exp2_sae/sae_jlens_requirements.txt`.
Do not rerun the failed collection in place or change its terminal markers.

## Permitted Claims

Permitted:

- "The preregistered Stage 1 run failed its replay-equivalence gate, blocking
  confirmatory endpoint claims."
- "In a labeled post-outcome analysis, semantic diagonal structure was present
  but below the frozen material threshold, selected IDs were practically
  comparable to matched alternatives, and all 14 state readers were near
  chance."
- "The registered maximum-error gate was sensitive to sparse BF16-scale replay
  differences and should be redesigned prospectively for future work."

Not permitted:

- "V2 passed" or "the v2 endpoint results were preregistered/confirmatory";
- "the replay discrepancy is harmless";
- "the paper IDs have no meaning";
- "J-space proves or detects hidden deception"; or
- any claim about hidden belief, provenance, intent, consciousness, or exact
  proprietary Goodfire equivalence.
