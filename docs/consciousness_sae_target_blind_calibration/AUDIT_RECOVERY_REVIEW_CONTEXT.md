# Bounded Context for the Calibration r3 Audit Recovery Review

This packet contains no scientific result values. The raw tensors and JSONL
rows remain only on the RunPod network volume and are not reviewer inputs.

## Observed lifecycle

- Original freeze commit: `1a165725cad3484c646de8420846545a6a8beb8b`.
- Owned execution pod: `597yeluoak40i7`, one NVIDIA B200, `US-CA-2`, network
  volume `bv9gb9j32y`.
- Model transaction: one invocation, exit zero, 256 model forwards, atomically
  finalized, 35 manifested files and 323,365,550 manifested bytes.
- Target prompt renders: zero. Target feature vectors: zero. Analysis outcome
  inputs: empty.
- First audit: one invocation, no compact output published, stopped at the
  pinned J-checkpoint inventory predicate.
- Original pod: receipt-owned termination completed; post-delete account pod
  inventory was empty. The network volume and raw transaction were retained.

## Exact failure

The failure log ended with:

```text
File ".../audit.py", line 1119, in _load_j_checkpoint
    raise CalibrationAuditError("J-lens map inventory differs")
CalibrationAuditError: J-lens map inventory differs
```

Physical failure-log SHA-256:
`a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f`.

## Frozen runtime predicate

The model runtime loaded the same hash-pinned checkpoint and required the
study maps as a subset:

```python
raw_maps = _validate_j_lens_checkpoint_metadata(checkpoint)
available = {int(layer) for layer in raw_maps}
if not set(protocol.J_LAYERS) <= available:
    raise V2RuntimeError("jlens_layers", "a required J map is missing")
```

It then iterated only over `protocol.J_LAYERS`.

## Frozen audit predicate

The failed auditor used an exact-equality predicate:

```python
maps = checkpoint["J"]
available = {int(layer) for layer in maps}
if available != set(protocol.J_LAYERS):
    raise CalibrationAuditError("J-lens map inventory differs")
```

`protocol.J_LAYERS` is 45 through 78. The pinned release checkpoint contains
maps 0 through 78. Its frozen physical SHA-256 is
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`;
metadata are `n_prompts=125` and `d_model=8192`. The extra 0-through-44 maps
are never selected by the study.

## Review boundary

The proposed correction must be rejected if it changes anything beyond
checkpoint-inventory compatibility, audit-host provenance, recovery timing,
or transparent disclosure. In particular, it may not change or select based
on prompts, directions, doses, raw rows, layers used by calculations,
thresholds, metrics, bootstrap logic, claim gates, or observed values.

The reviewer should assess:

1. whether required-subset semantics are the correct narrow correction for a
   physically hash-pinned superset checkpoint;
2. whether original execution provenance and fresh audit-compute provenance
   are independently and adequately bound;
3. whether the recovery code can alter any scientific calculation beyond the
   loader predicate;
4. whether the failed attempt and post-run recovery remain unambiguously
   disclosed in the final receipts;
5. whether a fresh model run is necessary despite the target-independent,
   pre-publication audit bug; and
6. any concrete stop-ship flaw that must be fixed before audit execution.
