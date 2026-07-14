# Reproducing SAE realization validation v1

Status: **prospective execution contract; no completed run exists**.

Run commands from the repository root. The examples below show the required
order, not authority to substitute paths, hashes, prices, pod IDs, or receipts.
The frozen machine plan and one verified GPT Pro advisory-evidence receipt
must exist before paid execution. For this freeze, that receipt records an
incomplete attempt with no reviewer feedback; it is not an adjudication.

## Repository/external-data split

```text
experiments/consciousness_sae_realization_validation/   source
tests/consciousness_sae_realization_validation/         local contracts
docs/consciousness_sae_realization_validation/          protocol/reports
data/consciousness_sae_realization_validation/          compact plans/receipts
/workspace/consciousness_sae_realization_validation/    raw network-volume runs
```

Do not copy raw residuals, arithmetic tensors, full vocabulary tables,
top-2,000 arrays, JSONL telemetry, or logs into Git or onto the laptop.

## 1. Test and build the result-free plan

```bash
python -m unittest discover \
  -s tests/consciousness_sae_realization_validation -p 'test_*.py'

python -m experiments.consciousness_sae_realization_validation.build_plan \
  --outdir out/consciousness_sae_realization_validation/review_candidate_20260714
```

The builder refuses an existing destination and writes exact Stage-A and
Stage-B JSONL grids, a protocol snapshot, a complete source-file inventory,
and a self-hashed plan manifest. The paid-review packet is exact and ordered:
`PROTOCOL.md` is the plan; `PRO_REVIEW_CONTEXT_20260714.md`, `SMOKE_TEST.md`,
`REPRODUCING.md`, the candidate manifest, all five candidate machine-plan
files, and the full text of every source named by the candidate inventory are
the only allowed artifacts. The adjudicator rejects missing, reordered,
substituted, or extra context—including this blog draft or any prior outcome
artifact. It reconstructs the complete input with no `--question` emphasis,
cross-checks every supplied byte, and cleanly regenerates the machine plan from
the embedded candidate source before accepting it.

This expanded packet is about 1.33 million characters before the final paid
submission is frozen. Use the reviewed profile explicitly:

```text
--max-input-chars 1500000
--max-input-tokens 500000
--max-output-tokens 12000
--pro-output-reserve-multiplier 2
--chars-per-token 3
--input-rate-usd-per-million 10
--cache-write-rate-usd-per-million 12.5
--output-rate-usd-per-million 45
--budget-authorization-usd 12
```

Omit `--question`. Closure rejects lower/default limits and any noncanonical
researcher-emphasis block.

Under the trusted procedural rule, that packet was submitted once through the
canonical experiment-plan review script. Do not rerun it for this freeze. The
provider returned `status=incomplete` with reason `max_output_tokens`, 327,771
input tokens, 154,922 output tokens (23,394 reasoning tokens), and zero
`output_text`. Therefore no reviewer verdict, finding, or recommendation was
received, and no feedback may be inferred or adjudicated. The estimated cost
at the prospectively frozen rates is `$10.2492`.

The committed
`docs/consciousness_sae_realization_validation/reviews/gpt-5.6-sol-pro_20260714/attempt_receipt.json`
reconstructs the canonical question-free packet and binds the exact request,
response, failed manifest, and failure record. Its status is
`attempted_incomplete`, with `review_feedback_received=false` and
`adjudication_completed=false`. Use that file as `REVIEW_ADJUDICATION`; the
legacy environment variable and CLI option keep their old name for
compatibility. This receipt is advisory provenance only, not evidence that the
final execution plan was reviewed.

If a different freeze has a completed response, resolve or rebut every finding
with file-backed evidence and build an `adjudicated_pass` receipt. That
optional path binds the completed response to the final plan. In either path,
build the final plan into
`data/consciousness_sae_realization_validation/validation_v1_plan_20260714`
and never edit a built plan. The one-call condition remains an explicit
operator rule, not a machine-attested global guarantee.

For the optional completed-response path, the schema-v2 decisions file also contains an exact ordered
`candidate_to_final_changes` list. Each row has `path`, `change_kind`,
`candidate_sha256`, `final_sha256`, and `finding_ids`. Use `null` for the hash
on the absent side of an addition or removal. The adjudicator independently
reconstructs the diff; hand-written mappings cannot add unknown paths, omit a
change, reorder rows, or substitute hashes. Every mapped finding must be
`accept`/`fixed`, and every such finding must explain at least one changed
byte set. `accepted_without_change` and rejected findings are never change
authority. If Pro returned `READY TO FREEZE` with no findings, this list must
be empty and the final reviewed bytes must be identical to the candidate.

An `adjudicated_pass` closure receipt binds both protocol/source inventories, both plan
inventories, the decisions mapping, the authorized diff, their canonical
hashes, and the candidate and final plan identities. Receipt validation
reconstructs all of them from the frozen review payload and final disk files.

Commit and push the exact bound source, selected review-evidence receipt, and final plan before
the smoke or Stage A. The pre-execution producer rechecks every bound hash,
scoped worktree cleanliness, `HEAD`, the local `origin/...` tracking ref, and
the exact live `refs/heads/...` SHA returned by non-mutating `git ls-remote`.
All three SHAs must be identical. Unrelated files may remain uncommitted
only when they are outside the bound execution surface.

Do not deploy the full repository: it contains committed predecessor plans and
compact outcomes that are prohibited even if runtime code never opens them.
Build an allowlisted archive containing only the final plan, selected
review-evidence paths, and plan-bound source files:

```bash
python - <<'PY'
import json, os, subprocess
from pathlib import Path
from experiments.consciousness_sae_realization_validation import preexecution

root = Path(os.environ["REPO_ROOT"]).resolve()
plan = Path(os.environ["PLAN_DIR"]).resolve()
review = json.loads(
    Path(os.environ["REVIEW_ADJUDICATION"]).read_text(encoding="utf-8")
)
paths = preexecution.deployment_allowlist(
    repo_root=root, plan_dir=plan, review_receipt=review
)
subprocess.run(
    ["git", "archive", "--format=tar", "--output",
     os.environ["MINIMAL_SOURCE_ARCHIVE"], "HEAD", "--", *paths],
    cwd=root, check=True,
)
PY
```

Extract that tar into a fresh guest source directory. Keep ownership,
preflight, authorization, smoke, and other operational receipts outside it.
The eventual authorization seals the allowlist file count and path-set hash;
gitless smoke and Stage A scan the tree and reject `.git`, symlinks, missing
paths, or any extra prior plan, result, blog, or other file. Generated `.pyc`
files are not exempt; run every guest command with `python -B` so imports do
not contaminate the allowlisted source tree.

The bound source inventory intentionally contains no predecessor protocol,
runtime, GPU runner, semantic fixtures, tokenizer audit, or changepoint
readouts. Successor runtime primitives are local. Exactly one target-free
audited predecessor file remains: `runpod_lifecycle.py`, loaded by the
successor lifecycle adapter through a private successor-only protocol/path
shim. Before deployment, the isolated-import contract test must extract the
exact source allowlist into a fresh directory and successfully run `--help` for
every registered guest CLI under `python -I -B`, with only that fresh directory
added to the interpreter path and with `PYTHONPATH`/`PYTHONHOME` removed.

## 2. Dry-run, create, and attest one pod

Keep orchestration receipts in a fresh directory outside the repository. The
credential is environment-only.

```bash
# RUNPOD_API_KEY must already be set in the process environment.

python -m experiments.consciousness_sae_realization_validation.runpod_orchestrator \
  create --receipt-dir "$EXTERNAL_ORCHESTRATION_DIR"

python -m experiments.consciousness_sae_realization_validation.runpod_orchestrator \
  create --receipt-dir "$FRESH_EXTERNAL_ORCHESTRATION_DIR" --execute
```

Before the executing command, independently recheck live B200 stock and price.
The create contract fixes `NVIDIA B200`, `US-NE-1`, volume `qf2lwehl89`, a
six-hour provider kill, and a `$36` ceiling. The executing path performs
exactly one create call. Use the returned ownership receipt and exact pod ID;
never target another account pod by name or convenience.

From that fresh minimal guest tree, build both the provider/mount and full
public-cache rehash receipts:

```bash
python -B -m experiments.consciousness_sae_realization_validation.runpod_preflight \
  all --ownership-receipt "$OWNERSHIP" --receipt-dir "$FRESH_PREFLIGHT_DIR"
```

This verifies PID-1 provider identity, the network mount and 500 GB provider
quota, then independently rehashes every one of the 45 pinned public-artifact
files without copying them into the new study namespace.

The successor `OWNERSHIP.json` also binds the immutable image observed in the
validated GraphQL create snapshot and corroborated by the final REST pod
readback. Smoke, Stage A, and Stage B must all run through `guest_launcher`.
That launcher derives the image environment from this attestation (never from
an operator-entered digest), refuses conflicting pre-existing values, sets
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, and `execve`s a fresh allowlisted module.
The runtime checks the image, CUDA setting, and exact ownership self-hash
before importing Transformers or Torch. Direct `smoke_test` or `runner`
execution is therefore invalid for a campaign run.

## 3. Benchmark storage and seal its budget

Initialize the study sentinel only at the intended volume root, run the
production 2 GiB dense interruption/resume benchmark, and derive the measured
budget receipt:

```bash
python -B -m experiments.consciousness_sae_realization_validation.runner \
  init-volume --volume-root /workspace --volume-id qf2lwehl89

python -B -m experiments.consciousness_sae_realization_validation.storage_benchmark \
  --plan-dir "$PLAN_DIR" --volume-root /workspace --volume-id qf2lwehl89 \
  --run-id "$FRESH_BENCHMARK_ID" --output "$FRESH_BENCHMARK_RECEIPT"

python -B -m experiments.consciousness_sae_realization_validation.gate_receipts \
  storage-budget --plan-manifest "$PLAN_MANIFEST" \
  --benchmark-receipt "$FRESH_BENCHMARK_RECEIPT" \
  --ownership-receipt "$OWNERSHIP" --guest-receipt "$GUEST_PREFLIGHT" \
  --cache-receipt "$CACHE_PREFLIGHT" --volume-root /workspace \
  --volume-id qf2lwehl89 --output "$FRESH_STORAGE_BUDGET"
```

The production benchmark has no reduced-size CLI switch. The storage budget
must leave both the 32 GiB raw ceiling and 64 GiB final reserve available under
conservative volume accounting. Its receipt is explicitly stamped
`execution_authorization_status=not_evaluated_storage_only` and
`model_execution_authorized=false`: a storage pass never authorizes a model
load, prompt render, smoke, or Stage A.

## 4. Issue the one pre-execution authorization

After copying the machine-produced ownership, guest, and cache receipts back
to the clean local Git checkout, issue the authorization there (where `.git`
and live `origin` are available):

```bash
python -m experiments.consciousness_sae_realization_validation.preexecution \
  --repo-root "$REPO_ROOT" --plan-dir "$PLAN_DIR" \
  --review-adjudication "$REVIEW_ADJUDICATION" \
  --ownership-receipt "$OWNERSHIP" \
  --guest-receipt "$GUEST_PREFLIGHT" \
  --cache-receipt "$CACHE_PREFLIGHT" \
  --remote-ref "$REMOTE_REF" --output "$FRESH_PREEXECUTION_AUTHORIZATION"
```

This is the only artifact that authorizes paid model execution. It binds the
exact final plan/source inventory, verified advisory receipt, clean pushed
commit, provider/preflight chain, pod and volume identity, and six-hour
campaign. It records zero model forwards and zero prompt/outcome access. Copy
the canonical receipt beside the other external operational receipts. The
allowlisted `git archive` deployment has no `.git`; smoke and Stage A therefore
rehash every sealed
plan/source/review/provider binding while retaining, rather than re-querying,
the producer's live-remote proof.
The receipt's `review_status` is either `adjudicated_pass` or
`attempted_incomplete`; for the present freeze it must be
`attempted_incomplete`. The latter does not claim feedback was received and
does not waive any later scientific gate.
`REMOTE_REF` must name the exact pushed execution branch (for this campaign,
`origin/feat/sae-changepoint`), not an assumed default branch.

## 5. Smoke, Stage A, structural audit, and analysis

Before Stage A, run the source-bound four-forward B200 smoke described in
`SMOKE_TEST.md` with the exact plan, ownership, guest, cache, artifact, and
resource bindings and `--preexecution-authorization`. Its receipt is
operational only: it cannot enter a
scientific gate, select a dose, or contribute a target outcome. A failed smoke
blocks Stage A for infrastructure diagnosis; it does not authorize changing
the frozen grid. Preserve the fresh external receipt and record its hash in the
execution log.

Run the launcher's `stage-a` command with the exact pinned model/SAE/J paths, live hourly price,
campaign start/deadline, ownership/preflight receipts, storage-budget receipt,
the same authorization, and the exact external smoke receipt path:

```bash
python -B -m experiments.consciousness_sae_realization_validation.guest_launcher \
  --ownership-receipt "$OWNERSHIP" stage-a -- \
  --plan-dir "$PLAN_DIR" --volume-root /workspace --volume-id qf2lwehl89 \
  --run-id "$FRESH_STAGE_A_RUN_ID" --model-snapshot "$MODEL_SNAPSHOT" \
  --sae-path "$SAE_PATH" --j-lens-path "$J_LENS_PATH" \
  --hourly-price-usd "$HOURLY_PRICE_USD" \
  --campaign-started-at-unix "$CAMPAIGN_STARTED_AT_UNIX" \
  --provider-terminate-at-unix "$PROVIDER_TERMINATE_AT_UNIX" \
  --guest-receipt "$GUEST_PREFLIGHT" \
  --cache-receipt "$CACHE_PREFLIGHT" --storage-budget "$STORAGE_BUDGET" \
  --preexecution-authorization "$PREEXECUTION_AUTHORIZATION" \
  --smoke-receipt "$EXACT_EXTERNAL_SMOKE_RECEIPT"
```

The J arithmetic/orientation fixtures execute and are sealed before the first
Stage-A prompt render; failure aborts the transaction before any Stage-A
prompt. The raw output must use a fresh run ID. Then run, in order:

```bash
python -B -m experiments.consciousness_sae_realization_validation.audit \
  --run-root "$STAGE_A_RUN_ROOT" --plan-dir "$PLAN_DIR" --out "$STAGE_A_AUDIT" \
  --storage-budget "$STORAGE_BUDGET" \
  --preexecution-authorization "$PREEXECUTION_AUTHORIZATION" \
  --smoke-receipt "$EXACT_EXTERNAL_SMOKE_RECEIPT"

python -B -m experiments.consciousness_sae_realization_validation.analysis stage-a \
  --run-root "$STAGE_A_RUN_ROOT" --plan-dir "$PLAN_DIR" \
  --audit "$STAGE_A_AUDIT" --storage-budget "$STORAGE_BUDGET" \
  --preexecution-authorization "$PREEXECUTION_AUTHORIZATION" \
  --smoke-receipt "$EXACT_EXTERNAL_SMOKE_RECEIPT" \
  --receipt-out "$STAGE_A_RECEIPT" --summary-out "$STAGE_A_SUMMARY"

python -B -m experiments.consciousness_sae_realization_validation.gate_receipts target-blind ...
```

The execution binding, audit receipt, and analysis receipt all bind the
authorization hash, smoke self-hash, smoke physical-file hash, campaign
identity, and external smoke-relative path. The audit independently rehashes
the complete run, rejects extra files, checks the exact grids and schemas,
validates the 68-row orientation artifact and its receipt, and binds the
storage receipt. It also joins every Stage-A branch and arithmetic-index row to
the archived clean/signed residuals, requests, realized/common/final deltas,
BF16/FP32 J predictions, seven transport predictions, and actual/predicted
2,048-token logit deltas. It recomputes realization fidelity, J-shadow,
transport correlation, and dose-linearity scalars before sealing a compact
numeric-classification hash; JSON telemetry cannot supply those classifications
without matching the raw tensors. Analysis may emit a
passing full Stage-A receipt or a failing receipt that still proves collection
safety. Collection safety includes realized-edit fidelity, common-mode control,
the exact layer-50 envelope inventory, and a passing independent 34-map
J-arithmetic/orientation receipt. The target-blind receipt keeps those gates
distinct from incremental real-J transport, dose-linearity, and the dedicated
global and layer-50 BF16-versus-FP32 J-shadow statuses. The Stage-A receipt
binds one ordered status/failure-count row per tested edit layer and a canonical
inventory hash. A global failure prevents a full passing Stage-A scientific
verdict but does not block neutral collection. The layer-50 subset alone gates
Stage-B layer-50 J eligibility: a layer-50 failure makes every such summary
ineligible, while a failure confined to another edit layer remains explicitly
failed without impersonating edit realization, J orientation, or layer-50
eligibility. Stage B must present the exact Stage-A audit whose numeric
classification hash is named by the Stage-A receipt.

Do not change the Stage-B plan after seeing Stage A. If collection safety or J
arithmetic/orientation fails, stop and terminate. If only incremental real-J
transport, dose-linearity, or the layer-50 J shadow fails, Stage B neutral
diagnostic collection may proceed, but the corresponding J-derived
interpretations remain blocked.

## 6. Permit, execute, and audit Stage B

Build the Stage-B permit from the exact plan, Stage-A safety receipt,
target-blind receipt, storage budget, selected advisory receipt, source inventory,
pushed remote ref, measured spend, and remaining wall-time ceilings:

```text
python -B -m experiments.consciousness_sae_realization_validation.gate_receipts stage-b-permit ...
python -B -m experiments.consciousness_sae_realization_validation.guest_launcher \
  --ownership-receipt "$OWNERSHIP" stage-b -- \
  ... --preexecution-authorization "$PREEXECUTION_AUTHORIZATION"
python -B -m experiments.consciousness_sae_realization_validation.audit \
  ... --preexecution-authorization "$PREEXECUTION_AUTHORIZATION"
python -B -m experiments.consciousness_sae_realization_validation.analysis stage-b \
  ... --plan-dir "$PLAN_DIR" \
  --preexecution-authorization "$PREEXECUTION_AUTHORIZATION"
```

Stage B uses its own fresh run ID but the same authorization and campaign as
Stage A. It reloads the authorization against the current ownership/guest/cache
receipts and exact campaign timestamps; a replacement pod, volume, receipt
chain, or deadline is not interchangeable. The Stage-B execution binding,
audit, and analysis all preserve the authorization and campaign hashes.
The review-evidence union changes no scientific predicate: the permit still
validates the Stage-A safety receipt, target-blind scientific-status/hash
inventory, storage receipt, plan binding, target-access zeros, and resource
ceilings before accepting either advisory status. A verified incomplete attempt
cannot turn a failed scientific status into a pass or authorize a claim that
the existing scientific contract blocks.
The Stage-B audit independently joins each signed branch to its archived
`requested_fp32`, `requested_bfloat16`, `realized_fp32`, `50_pre`, and
`50_post` tensors. It recomputes the three vector hashes and all eight
requested/native/realized scalar metrics, then applies the frozen `RMSE <=
0.10` and `cosine >= 0.995` thresholds. A requested-fidelity miss is reported,
not erased: it blocks requested direction/class/dose, paired-contrast, and J
attribution for affected members/groups while preserving separately labelled
actual-realized row characterization if hard/native integrity passed.
Preserve the
raw immutable release on the network volume. Export only compact self-hashed
receipts and aggregate summaries after checking that they contain no raw data,
credentials, signed URLs, or private absolute host paths.

The current analyzer truthfully reports replay as
`not_run_replay_capable_only`. Do not describe the release as replay-verified
unless a separate replay producer executes and a receipt passes the frozen
replay validator.

## 7. Terminate exact ownership and verify absence

Termination is mandatory on success, failure, timeout, or abandoned staging:

```bash
python -m experiments.consciousness_sae_realization_validation.runpod_orchestrator \
  terminate --receipt-dir "$FRESH_EXTERNAL_ORCHESTRATION_DIR" \
  --pod-id "$EXACT_OWNED_POD_ID" --execute
```

The termination audit must prove deletion of that exact ID, direct provider
absence, and an unchanged unrelated-pod inventory. Do not mutate or stop any
other account pod.
