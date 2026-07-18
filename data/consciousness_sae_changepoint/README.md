# Consciousness SAE changepoint Git metadata

This is the dedicated Git-tracked namespace for result-free machine plans and
compact audited release receipts for the temporal before/after SAE experiment.
It is **not** the raw-data location and currently contains no outcomes.

Use these immutable directory classes:

```text
confirmatory_v1_calibration_plan_<YYYYMMDD>/
confirmatory_v1_plan_<YYYYMMDD>/
confirmatory_v1_<YYYYMMDD>_metadata/
```

Do not write mutable or outcome-bearing jobs here. Calibration, confirmatory,
judging, vocabulary expansion, raw analysis, reanalysis, and complete immutable
releases belong under the explicitly configured
`$CONSCIOUSNESS_SAE_ARTIFACT_ROOT/` on the persistent RunPod network volume. A
metadata exporter may create a new dated metadata directory here only after the
external raw rows, analysis, audit, manifest, and completion receipt agree; an
existing directory is never updated in place.

The repository ignore policy tracks only this namespace README today. Add
narrow file-by-file exceptions for an exact result-free plan or audited compact
metadata receipt; never unignore this entire tree, an external release mirror,
or a dated directory wholesale.

Every tracked plan or metadata receipt must be self-describing and may include,
as applicable:

- `manifest.json`/`GIT_MANIFEST.json` for the tracked files;
- `REMOTE_RECEIPT.json` containing the external manifest/completion hashes,
  logical volume label and relative prefix, byte/file counts, but no credential,
  signed URL, or host-absolute path;
- `upstream_inputs.json` recording source path, commit/release, byte hash, role, and transformation;
- `environment.json` with pinned external artifacts and dependencies;
- `commands.txt` with repository-relative build, validation, analysis, audit, and reproduction commands;
- all result-free plans, seeds, prompt/token hashes, assignments, and control mappings;
- schemas, aggregate endpoint summaries, allowlisted figures, and derived result
  prose; and
- a complete inventory of external shard hashes, shapes/schemas, row/file
  counts, and roles, or its hash plus a compact summary when the manifest itself
  exceeds the Git payload ceiling.

Never track row-level observations, generated prefix/transcript text or token
rows, judgments, errors/telemetry rows, logs, residuals, logits, vocabulary
indexes, KV caches, model tensors, Parquet/Arrow, JSONL, or compressed archives.
This remains true when a raw file is small. The metadata exporter must reject
symlinks, forbidden formats, files over 5 MiB, and a total tracked release
payload over 25 MiB.

The canonical scientific archive lives externally and stores portable prefixes
as text, exact token IDs, masks, seeds, tokenizer revisions, and hashes. It is
written as a fresh `.partial` run, every shard is read back and hashed, and it
becomes citable only after an immutable remote manifest and matching
`COMPLETE.json` exist.

Once an audited external release and its metadata receipt are added, register
the receipt in `DATA_ARTIFACTS.md` and the root README artifact map. The RunPod
network volume is a private, single-copy location unless separately backed up;
this Git receipt does not make raw data publicly available. Until then, this
README is only a namespace reservation and must not be cited as evidence.
