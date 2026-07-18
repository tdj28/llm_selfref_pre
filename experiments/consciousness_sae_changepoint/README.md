# Consciousness SAE changepoint experiment

This directory is the isolated implementation namespace for the prospective experiment that switches a layer-50 SAE intervention during generation and measures behavior and downstream J-lens trajectories before and after that switch.

The target-blind runtime and validation stack is under implementation. Target
outcomes remain blocked until the exact protocol, renewed independent review,
machine-plan freeze, registration, and human reliability commitments pass; this
namespace must never become an implicit extension of either prior SAE experiment.

## Path contract

All files use the study slug `consciousness_sae_changepoint`:

| Kind | Path |
|---|---|
| Code | `experiments/consciousness_sae_changepoint/` |
| Protocol and results documents | `docs/consciousness_sae_changepoint/` |
| Frozen plans and compact release receipts | `data/consciousness_sae_changepoint/` |
| Outcome-bearing runs and complete releases | `$CONSCIOUSNESS_SAE_ARTIFACT_ROOT/` on the persistent RunPod network volume |
| Local disposable development fixtures only | `out/consciousness_sae_changepoint/` |
| Tests | `tests/consciousness_sae_changepoint/` |

The following prior namespaces are read-only inputs:

- `experiments/exp2_sae/`
- `data/public_sae_consciousness_gating/`
- `data/sae_jlens_audit/`

New runners and release builders must reject output paths inside those prior namespaces. Existing code may be imported, but the new frozen plan must pin the source commit and hash every reused input or source file that can affect the result.

Outcome-bearing entry points must require an explicit
`CONSCIOUSNESS_SAE_ARTIFACT_ROOT`, verify that it resolves outside the Git
checkout to the expected persistent-volume identity with sufficient free
space and logical purchased-volume quota, and call the external path guard
before creating a destination. Shared-NFS `df` capacity is not proof of the
individual RunPod volume quota. There is
no fallback to repository `out/`, `/tmp`, container-local storage, or a laptop
path. `require_new_output_path` remains only for small local dry-run/test output
and compact Git metadata construction. Every raw row carries
`study_id=consciousness_sae_changepoint_v1`, its plan-manifest hash, run ID, and
block/branch identity.

Provision the study-specific directory on the mounted volume once and place a
`.consciousness_sae_volume.json` sentinel at its root:

```json
{
  "study_slug": "consciousness_sae_changepoint",
  "volume_id": "<stable-private-volume-label>",
  "volume_size_gb": 500
}
```

Set `CONSCIOUSNESS_SAE_VOLUME_ID` to the same frozen label for runtime
cross-checking. Neither the absolute mount path nor the label grants access;
do not put credentials or signed URLs in the sentinel or tracked receipt.

## Required lifecycle

1. Write and review the human protocol under `docs/consciousness_sae_changepoint/`.
2. Build and validate a result-free machine plan under `data/consciousness_sae_changepoint/confirmatory_v1_plan_<date>/` through a narrow Git allowlist.
3. Freeze the protocol, source, plan manifest, and analysis before opening target outcomes.
4. Write mutable execution into a fresh `$CONSCIOUSNESS_SAE_ARTIFACT_ROOT/<phase>/<run_id>.partial/` directory on the RunPod network volume.
5. Analyze and audit the run without modifying the frozen plan.
6. Hash/read back every shard, write the external manifest, rename to `<run_id>`, and write `COMPLETE.json` last.
7. Build an immutable external release plus a compact Git metadata receipt; never overwrite either half.
8. Update `DATA_ARTIFACTS.md` and the root artifact map only when the external release and tracked receipt agree.

## Reproduction contract

Before execution, this namespace must provide builders, validators, the runtime,
analysis, audit, release, metadata-export, and reproduction entry points. The
canonical external release must include:

- exact commands that run from the repository root;
- pinned model, SAE, J-lens, tokenizer, package, and source revisions;
- copied result-free plans and `upstream_inputs.json` with SHA-256 provenance;
- raw rows/text/token IDs, error rows, judge packets, telemetry, residual and
  vocabulary shards, and branch lineage;
- environment and runtime metadata;
- analysis outputs and figures generated from the released raw inputs;
- `REMOTE_MANIFEST.json` with relative paths, roles, bytes, SHA-256, and
  schema/dtype/shape where applicable; and
- reproduction and reanalysis commands whose data outputs go only to fresh
  directories under the external artifact root.

The Git metadata receipt may contain the frozen plan, schemas, environment and
command receipts, aggregate endpoint summaries/figures, `GIT_MANIFEST.json`,
and `REMOTE_RECEIPT.json`. The latter binds the release/plan hashes to the
external manifest hash, logical volume label, relative run prefix, byte/file
counts, and completion hash. It must contain no credentials, signed URLs, or
host-absolute RunPod paths.

Generated prefixes, transcripts, token rows, judgments, telemetry, logs,
packed vocabulary indexes, logits, residuals, model artifacts, and complete
analysis tables remain external even if an individual file happens to be
small. The metadata exporter is allowlist-based, refuses symlinks and forbidden
raw formats, and enforces a 5 MiB per-file and 25 MiB aggregate Git ceiling.
Serialized KV caches remain external and are rebuilt from the frozen external
token IDs rather than treated as portable scientific inputs.

Secrets never belong in either release half. Interrupted `.partial` runs cannot
be cited. The RunPod volume is the primary private raw archive, not a public
download or a backup; losing its only copy requires a rerun.
