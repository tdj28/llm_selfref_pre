# Reproducing the consciousness SAE changepoint study

Status: prospective target-blind reproduction contract. The target launch and
analysis commands cannot be frozen until the remaining gates in `PROTOCOL.md`
pass. This file must be updated with exact immutable plan/run IDs before OSF
registration; placeholders are intentionally not executable target authority.

## Repository and external-data separation

Run commands from the repository root. Source, tests, protocol, compact
receipts, and aggregate results live in Git. Raw data live only under a
dedicated persistent RunPod network-volume root:

```text
experiments/consciousness_sae_changepoint/        source
tests/consciousness_sae_changepoint/              tests
docs/consciousness_sae_changepoint/               protocol and reports
data/consciousness_sae_changepoint/               compact frozen plans/receipts
$CONSCIOUSNESS_SAE_ARTIFACT_ROOT/                 raw external archive
```

Do not copy raw text, token IDs, residual/logit shards, judgments, vocabulary
indexes, telemetry, or row-level analysis to the laptop or repository. Do not
point the artifact root inside the checkout, `/tmp`, or container-local storage.

## External-volume preflight

The external study root must contain `.consciousness_sae_volume.json` with the
study slug, stable private volume ID, and purchased logical size. Set:

```bash
export CONSCIOUSNESS_SAE_ARTIFACT_ROOT=/workspace/consciousness_sae_changepoint/v1
export CONSCIOUSNESS_SAE_VOLUME_ID=<registered-volume-id>
```

The path guard verifies the sentinel, expected volume ID, write/read behavior,
logical purchased quota, and free-space ceiling. Shared-NFS `df` output is not
evidence that the individual volume has enough quota. At provisional `N=560`,
the current planning estimate is about 714 GiB including cache and reserve, so
the existing 500 GB volume is not authorized for the full target run. The final
measured benchmark and approved ceiling are pending.

## Pinned environment

The machine plan must record:

- the exact Git commit and hashes of every bound source, test, and governing
  document;
- container image name and immutable digest;
- Python, PyTorch, CUDA, Transformers, Safetensors, and Hugging Face versions;
- GPU model/count and network-volume identity;
- model, tokenizer/chat-template, SAE, J-lens, final RMSNorm, and LM-head hashes;
- all plan, gate, registration, and spend-authorization receipt hashes; and
- exact command lines and environment variables with secrets redacted.

Install only from the pinned requirement file:

```bash
python -m pip install -r experiments/consciousness_sae_changepoint/requirements-runpod-b200.txt
```

Credentials are supplied through the runtime secret environment. Never store
tokens, `.env` contents, signed URLs, or absolute private mount paths in Git
receipts.

## Validate source without target data

Run the complete study tests before building a machine plan:

```bash
python -m unittest discover -s tests/consciousness_sae_changepoint -p 'test_*.py'
```

Build/validate the result-free machine plan only after the parent gate receipts
exist. The final command must bind explicit input paths and a fresh output ID;
the exact registered invocation will replace this descriptive form:

```text
python -m experiments.consciousness_sae_changepoint.build_plan <all frozen inputs>
python -m experiments.consciousness_sae_changepoint.validate_plan <frozen plan>
```

Never use files under `data/public_sae_consciousness_gating/` or
`data/sae_jlens_audit/` as inputs. The validator must fail if a prohibited prior
namespace, unstated file, unbound validator, or source-hash mismatch appears.

## Completed target-blind parent receipts

Verify the complete external transaction, not just the JSON payload, for:

- artifact audit `artifact-audit-20260714T0145Z-final`, receipt
  `869deee31e5331f99684bd0ff32de34cbf3706b613d76e6d030ed34d85e4f2c6`,
  manifest
  `866b4689351161f7dcfc3fb4924d3454cb7ecb7762c20ae1aa8472724a661cab`;
- calibration `neutral-calibration-20260714T0200Z-final`, receipt
  `04f6751134be6a1bc2f7dd387a01e4a34990d5271bf0e385d767460260493247`,
  manifest
  `ecffedec405fcbab6365bb3d66f26939435e45b09049c25abe135d35e00e9b70`;
  and
- semantic selection `semantic-label-snapshot-20260714T0215Z-final`, receipt
  `ab43a18c5f9db30451015c705cbab19cdbb78b5ad0a132f92f040ab734203179`,
  selection
  `85427e45c7bfa8e21805e0603ab7cfda907e1f5cb2aba348c9823c8704c457ee`.

For each transaction, independently enumerate the manifest, verify relative
paths/bytes/SHA-256 values, verify the completion marker was written last, and
recompute the embedded receipt hash. Standalone copied JSON is not a gate.

The failed broad selector `semantic-label-snapshot-20260714T0130Z` and receipt
`b294e736d31c9b2e5013354e1e5ee146f5243b555ccdad0cee65d2ad727ace49`
remain archived as provenance but are forbidden inputs.

## Remaining target-blind commands

The semantic positive-control runner is:

```text
python -m experiments.consciousness_sae_changepoint.semantic_control_run \
  --cache-dir <external-cache> \
  --artifact-receipt <completed-artifact-run>/artifact_receipt.json \
  --calibration-receipt <completed-calibration-run>/calibration_receipt.json \
  --selection-receipt <completed-selection-run>/semantic_control_selection_receipt.json \
  --artifact-root "$CONSCIOUSNESS_SAE_ARTIFACT_ROOT" \
  --volume-id "$CONSCIOUSNESS_SAE_VOLUME_ID" \
  --run-id <fresh-semantic-control-run-id>
```

Its result and hash are pending. The representative B200 benchmark and power
suite must also write fresh, non-overwriting receipts. The power receipt must
use the final candidate sample size, at least 2,000 outer simulations and 999
inner bootstraps, and must include material, zero, and all signed boundary
scenarios. A pass explicitly does not authorize freeze.

## Target execution barrier

Do not run the target executor unless all of the following are bound to one
machine-plan manifest:

1. passing artifact/calibration/semantic-control/benchmark/power/runtime gates;
2. reviewed protocol, claim boundary, reproduction instructions, source, and
   tests;
3. final sample size, complete-block rule, storage ceiling, GPU-hours, retry
   reserve, and maximum spend;
4. adjudicated renewed GPT-5.6 Sol Pro review;
5. explicit human signoff on the exact immutable OSF registration; and
6. explicit human approval of the measured spend ceiling.

The final registered target command must require all of those receipt hashes on
the command line or through a hash-bound gate manifest. A generic “go” is not a
substitute. The exact target command is therefore intentionally **pending**.

## Sealing, audit, human coding, and unsealing

Every execution starts at `<run_id>.partial`. Each block is content-addressed,
read back, manifested, and completed independently. After the structural audit,
the run is atomically renamed and `COMPLETE.json` is written last. Interrupted
or failed `.partial` directories cannot be analyzed or cited.

Target outcomes remain sealed while a nonsemantic audit verifies plan identity,
common eligible blocks, gate receipts, schemas, branch completeness, hashes,
and shard integrity. Two independent human coders then label the prospectively
selected reliability packet; disagreements are adjudicated under the frozen
rubric. The unseal command must require the structural-audit receipt and the
human reliability/adjudication receipt. Analysis refuses to read semantic
outcomes without a valid unseal receipt.

The final release must include two exact reproduction paths:

- rerun the full model into a fresh external directory; and
- reanalyze the immutable external release in place without regenerating model
  outputs.

Both exact commands, expected manifest hashes, environment receipt, and compact
Git metadata-export command remain pending until the protocol is registered and
the first immutable release exists.
