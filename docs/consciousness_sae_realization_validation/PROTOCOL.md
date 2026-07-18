# SAE realization and J-lens validation: prospective protocol

Study ID: `consciousness_sae_realization_validation_v1`

Protocol version: `consciousness_sae_realization_validation_v1.0.0`

Prepared: 2026-07-14 (America/Los_Angeles)

Status: **prospective draft; not executed; no results**

## Question and scope

This study asks three ordered questions on new mundane prompts:

1. Does the requested FP32 edit survive conversion and BF16 addition as the
   intended native and realized edit?
2. After conditioning on that realized edit, how linear is the fixed-token
   downstream response for generic residual directions across dose and depth,
   and does the real Jacobian outperform identity and random-J controls?
3. Do public SAE decoder directions show a different neutral-prompt dose arc
   from freshly matched SAE and norm-matched isotropic directions?

Both stages run the final rendered prompt token from a shared prefix cache.
They do not generate a continuation. “Actual final” means the actual final
pre-RMSNorm residual and logits for that same fixed-token forward, not a model
response or behavioral outcome.

This study cannot establish consciousness, deception, subjective experience,
or paper replication. Its strongest possible result is a technical statement
about edit realization, fixed-token propagation, and J-lens behavior in the
pinned model/SAE/prompt setting. A later paper-prompt study remains separate
and blocked.

## Isolation from prior outcomes

The machine plan, runtime, receipts, and analyses require
`prior_outcome_inputs=[]`. They may not read or pool any result, raw row,
matched coordinate, effect estimate, selected layer, threshold adaptation, or
dose decision from `consciousness_readout_validation_v1`, r15, the changepoint
study, or any paper-prompt run.

The earlier r15 findings may be described in prose as motivation. Outcome-free
source implementations may be reused only as hash-bound code. Public weights
may be reused read-only from the existing cache only after all 45 files
(`156,023,372,845` bytes) are independently rehashed against the pinned
manifest. That cache reuse is public-artifact reuse, not prior-outcome reuse;
no old plan, match, or result file is admitted.

## Advisory review and candidate-to-final closure

The GPT Pro request embeds the exact prospective protocol/reproduction
documents, candidate plan manifest, every candidate machine-plan byte
(`protocol_snapshot`, Stage-A grid, aggregate assignments, Stage-B grid, and
source inventory), and every candidate source byte. Closure reconstructs the
canonical question-free input, cleanly regenerates the candidate machine plan
from the embedded candidate builder/source in an isolated process, and requires
byte identity. The ignored candidate directory is therefore disposable after
submission.

The review is advisory, not scientific evidence or an execution permit. The
operator follows a trusted procedural rule to make one paid review call. The
stored request, response ID, exact provider-echoed metadata, usage, and hashes
identify the response actually returned, but neither the provider response
nor local verification can prove that no other call was made elsewhere. No
such global uniqueness claim is made.

That call returned `status=incomplete` with
`incomplete_details.reason=max_output_tokens`, 327,771 input tokens, 154,922
output tokens (23,394 reasoning tokens), and no `output_text`. No reviewer
verdict, finding, or recommendation was received, so no adjudication or
review-driven plan change exists and the call must not be rerun for this
freeze. The self-hashed `attempted_incomplete` receipt reconstructs the
canonical question-free packet and binds the exact `request_payload.json`,
`response.json`, `review_manifest.json`, and `failure.json`. It records
`review_feedback_received=false` and `adjudication_completed=false`.

If a completed advisory response is available, final closure recomputes separate candidate and final protocol/source and
plan inventories, then emits one canonical candidate-to-final change
inventory. Every modified, added, or removed path must appear in the
schema-v2 decisions file with its change kind, exact candidate/final SHA-256
(using `null` on the absent side), and one or more stable review finding IDs.
Only an `accept`/`fixed` finding authorizes changed bytes. Rejected findings
and `accepted_without_change` findings cannot authorize changes; unknown,
unmapped, reordered, or hash-mismatched entries fail closed. Every
`accept`/`fixed` finding must account for at least one actual byte change. A
no-finding `READY TO FREEZE` verdict requires candidate and final byte
identity. Under the trusted one-call procedure, adjudication traces repairs to
the stored advisory review rather than selecting a more convenient response.
This optional completed-adjudication path is not invoked for the present
no-feedback attempt.

## Pre-execution stop-ship authorization

No model forward or smoke prompt render may begin from a plan, review, Git
state, or provider receipt considered separately. One machine-produced
authorization must bind the exact final plan and source inventory, one
verified advisory receipt (`adjudicated_pass` or `attempted_incomplete`), every bound path's scoped cleanliness and
presence in `HEAD`, the local `origin/...` tracking SHA, the SHA advertised by
a read-only `git ls-remote --exit-code origin refs/heads/...` query, the
ownership/guest/cache receipt chain, and the one pod/volume/campaign deadline.
`HEAD`, the local tracking ref, and the one exact 40-hex live branch SHA must
all match. The producer records zero model forwards and zero prompt/outcome
access.

The authorization is produced in the clean local checkout. A Git-less guest
archive is constructed from an exact allowlist containing only the final plan,
review-evidence paths, and plan-bound sources—never a full-repo
archive carrying predecessor plans, compact outcomes, or blogs. The
authorization seals the permitted path count/set and states that prior-result
files are forbidden. Guest validation rejects `.git`, symlinks, missing paths,
and any non-allowlisted file before backend creation, while independently
rehashing all sealed plan, source, review, and provider bindings. It does not
pretend to re-run the unavailable Git proof. Both the
operational smoke, Stage A, and Stage B require the same authorization and
campaign. Stage B reloads it against the current ownership/guest/cache chain
and joins its authorization/campaign hashes to the Stage-A receipt, preventing
a permit or Stage-A receipt from being replayed on a replacement pod.
Stage A also requires the exact external single-link smoke path and records the
smoke self-hash and physical file SHA-256. Those authorization/smoke/campaign
bindings are reproduced in the raw execution bindings, independent audits, and
both analysis receipts.

The legacy machine fields and CLI option retain the word `adjudication` for
compatibility, but their bound receipt is a tagged union. An
`attempted_incomplete` receipt satisfies only the advisory/provenance slot: it
cannot satisfy or override storage, collection-safety, J orientation, J-shadow,
transport, dose-linearity, target-blind, spend, wall-time, or Stage-B permit
checks. Those scientific and operational gates are evaluated exactly as
specified below.

The deployed successor runtime is self-contained: it does not import the
predecessor runtime, GPU runner, protocol, semantic fixtures, tokenizer audit,
or changepoint readouts. The sole predecessor source in the bound allowlist is
the target-free audited RunPod lifecycle implementation. Its successor adapter
loads that one file inside a private synthetic package that exposes only the
successor identity/hash contract and repository-root path; the predecessor
package initializer and its fixture closure are neither deployed nor imported.
The source allowlist is tested by copying it into a fresh tree and running all
guest CLIs with isolated Python, bytecode disabled, and no ambient repository
or `PYTHONPATH`.

Smoke, Stage A, and Stage B have one frozen guest entry point. The launcher
validates the successor ownership receipt, takes the immutable image from its
provider-observation attestation, sets `CUBLAS_WORKSPACE_CONFIG=:4096:8`, and
binds the ownership self-hash before replacing itself with the smoke or runner
module. It refuses conflicting pre-existing values and any process that has
already imported Torch or Transformers. The runtime repeats the image, CUDA,
and ownership-hash checks before tokenizer/model initialization; direct module
execution fails closed.

The dense storage benchmark is not execution authority. Its machine receipt
must state `not_evaluated_storage_only` and
`model_execution_authorized=false`; only the pre-execution authorization can
permit the backend load and smoke/Stage-A forwards.

## Pinned artifacts

| Artifact | Frozen identity |
|---|---|
| Model | `meta-llama/Llama-3.3-70B-Instruct` at `6f6073b423013f6a7d4d9f39144961bfbfbc386b`, BF16, 80 layers, width 8192 |
| SAE | `Goodfire/Llama-3.3-70B-Instruct-SAE-l50` at `128ee921ecd1b8b3a87d776cbcc357c0855da134`, layer 50, 65,536 features, file SHA-256 `81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6` |
| J lens | `neuronpedia/jacobian-lens` at `a4114d7752d11eb546e6cf372213d7e75526d3a1`, source maps 45–78 to layer 79, file SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`, release-config SHA-256 `d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5` |
| J reference semantics | `anthropics/jacobian-lens` at `581d398613e5602a5af361e1c34d3a92ea82ba8e`; column definition `J_l @ h_l`, row implementation `residual @ J_l.T`, no intercept or centering reference |
| Container | `runpod/pytorch@sha256:cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853` |
| Vocabulary | 128,256 tokenizer IDs, with a canonical ID/piece/decoded-text table |

The J orientation is frozen from that public upstream contract, not asserted
only by this repository. Before any Stage-A prompt render, a new target-free
producer exercises two SHAKE256-derived fixtures on every one of the 34 maps.
The production backend computes row `residual @ J.T`; a separately coded
component loop computes `y_i = sum_j J[i,j] x_j`; and row `residual @ J` is an
explicit wrong-orientation control. Exact rows and a self-hashed receipt bind
the plan, checkpoint, release config, upstream revision, algorithms, fixtures,
outputs, and metrics. This gate performs zero model forwards and uses no prompt
or predecessor result. Stage A also loads FP32 shadows of the eight tested J
maps and compares them with production transport.

## Stage A: generic realization and transport

Stage A uses eight new mundane prompts, disjoint from Stage B. The exact grid
is:

| Factor | Frozen values |
|---|---|
| Edit layer | `45, 50, 55, 60, 65, 70, 75, 78` |
| Direction | Three hash-seeded PCG64 Gaussian directions, each normalized to unit RMS |
| Requested dose | `0.25%, 0.5%, 1%, 2%, 4%, 8%` of the clean source-residual RMS |
| Sign | `-1, +1` |
| Edited forwards | `8 × 8 × 3 × 6 × 2 = 2,304` |

For every signed pair the archive retains the FP32 request, native BF16
request, clean pre-hook tensor, exact post-hook tensor, realized plus and minus
deltas, signed central delta, common-mode component, complete residual arc,
and actual final residual. The hook must fire exactly once. The post-hook BF16
bytes must equal the native BF16 addition, and the pre-hook bytes must equal
the clean source state.

Each edited trace has 36 states: all 34 released J-source layers `45:78`, an
explicit immediate `edit_post` state, and the actual final residual. At the
edited layer, the ordinary layer capture is pre-edit because the capture hook
precedes the single-use edit hook. Earlier layers are upstream of the edit and
are expected to match clean; later layers record the realized downstream
trajectory.

The two lowest doses are diagnostic probes of the BF16 floor. The prospective
linearity gate uses only `1%, 2%, 4%, 8%`, anchored at `2%`, and separately
checks the realized source delta, `J(realized delta)`, and actual final delta.
For every prompt/layer/direction/dose, the realized central edit is transported
with the real J map, identity, and five independently seeded random-J controls.

Stage A archives the raw quantities needed for a CPU-only numeric audit: clean
and signed pre/post/final BF16 states; FP32 and native-BF16 requests and
realizations; BF16 and FP32 J predictions; every transport prediction; and the
actual and predicted fixed-panel logit deltas. The audit joins those tensors to
the branch/arithmetic indexes, reconstructs all realization, J-shadow,
transport, and dose-linearity scalars, and rejects any contradictory JSON row.
Its independently derived status inventory is self-hashed into the audit and
that hash is bound into the Stage-A analysis receipt and Stage-B permit chain.

### Stage-A thresholds

| Check | Frozen requirement |
|---|---:|
| Requested-to-realized central cosine | at least `0.995` |
| Requested-to-realized relative RMSE | at most `0.10` |
| Common-mode RMS / central RMS | at most `0.10` on the 1–8% gate band |
| 34-map production vs independent-component orientation cosine | at least `0.995` on all 68 fixtures |
| 34-map production vs independent-component orientation relative RMSE | at most `0.05` on all 68 fixtures |
| Wrong-minus-correct orientation relative-RMSE margin | at least `0.10` on all 68 fixtures |
| Correct-minus-wrong orientation cosine gap | at least `0.10` on all 68 fixtures |
| Production-BF16 J vs FP32-shadow cosine | at least `0.995` |
| Production-BF16 J vs FP32-shadow relative RMSE | at most `0.10` |
| Dose-normalized direction cosine | at least `0.95` |
| Dose-normalized slope discrepancy | at most `0.15` |
| Real-J residual-cosine 95% prompt-cluster LCB | greater than `0.10` |
| Real-J minus identity residual-cosine LCB | greater than `0.02` |
| Real-J minus best-of-five-random residual-cosine LCB | greater than `0.05` |
| Real-J fixed-token logit-Pearson LCB | greater than `0.25` |
| Real-J minus identity logit-Pearson LCB | greater than `0.02` |
| Real-J minus best-of-five-random logit-Pearson LCB | greater than `0.05` |

Intervals use 20,000 deterministic prompt-cluster bootstrap draws over the
eight prompts. The layer-50 primary transport status requires both transport
metrics to pass in every one of the three direction strata; averaging across a
failed direction cannot rescue it. The `0.02` real-J-over-identity margin is
the earlier frozen design threshold retained without weakening; it is not
selected from successor outcomes.

The production-BF16-versus-FP32 J comparison has a global all-tested-layer
scientific status and a distinct **layer-50 J-shadow status**. The receipt
binds the ordered per-edit-layer pass/fail and failure-count inventory plus its
canonical hash. Both statuses use the frozen `RMSE <= 0.10` and `cosine >=
0.995` requirements on every gated row. A full passing Stage-A scientific
verdict requires the global status to pass. The layer-50 status is the narrower
gate used for Stage-B layer-50 J eligibility; a failure confined to another
tested edit layer remains a disclosed global Stage-A failure but does not
impersonate a layer-50 failure. Neither status is edit realization,
J arithmetic/orientation, or collection safety, so a miss may still permit the
neutral raw collection while the affected J interpretation remains blocked.

## Stage B: SAE-family neutral characterization

Stage B uses eight different mundane prompts. It constructs all 15 unordered
two-feature pairs from public layer-50 candidate IDs `30032`, `58667`, `22004`,
`30686`, `41533`, and `23893`. The pinned source is the AE Studio
`deception-features/deception_features.ipynb` notebook at commit
`d50dc4ba125dde98666a60e3115a6a476dabea10`, file SHA-256
`a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8`.
These are later-public working intervention coordinates, not validated
concepts and not verified as the private paper's exact features.

Each pair has three vector classes:

- `target`: the ordered BF16 aggregate of the two public decoder columns, with
  frozen coefficient `0.5`;
- `matched`: fresh, unique, disjoint SAE controls selected from new neutral
  all-token layer-50 residuals and norm-matched to the target pair; and
- `isotropic`: a hash-seeded Gaussian residual direction norm-matched to that
  target pair.

Fresh SAE matching uses four coordinates from the eight Stage-A prompts:
decoder-column norm, mean positive activation, maximum positive activation,
and positive-activation fraction. Coordinates are median/MAD standardized,
then assigned greedily one-to-one in the frozen target-ID order with smaller
feature ID as the exact-tie break. “Matched SAE” means matched on these four
numerical coordinates; it does not mean semantically unrelated or causally
inert.

No predecessor match table is accepted. The exact Stage-B grid is:

| Factor | Frozen values |
|---|---|
| Prompt | 8 new Stage-B mundane prompts |
| Pair | all 15 unordered target-feature pairs |
| Vector class | target, matched SAE, isotropic |
| Multiplier | `0.25×, 0.5×, 1.0×` |
| Sign | `-1, +1` |
| Edited forwards | `8 × 15 × 3 × 3 × 2 = 2,160` |

Every edit is preflighted at no more than 10% of source-residual RMS. The requested FP32,
native BF16, and realized FP32 vectors are archived, with exact hook counts,
pre/post byte checks, upstream equality, cosine, relative RMSE, and realized
RMS fraction. Every Stage-B row must separately pass the prospectively frozen
requested-edit fidelity thresholds (`relative RMSE <= 0.10`, `cosine >=
0.995`) for all three recorded comparisons: native request versus realization,
FP32 request versus native request, and FP32 request versus realization. The
structural audit recomputes all eight scalar telemetry values and all three
vector hashes from the archived `requested_fp32`, `requested_bfloat16`,
`realized_fp32`, and residual tensors; it does not trust the JSON values alone.

Each branch retains these 36 states:

```text
45, 46, 47, 48, 49, 50_pre, 50_post, 51, ..., 78, final
```

Raw BF16 residuals are authoritative. At every state the archive also stores
stable top/bottom-2,000 token IDs and FP32 scores for branch-versus-clean and
signed-pair central changes, plus the absolute top 2,000. Intermediate states
use the released J map for that source layer; `final` uses actual final logits.
These arrays are browse indexes, not a confirmatory lexicon or substitute for
the raw residuals.

Stage B directly evaluates the signed-pair central layer-50 vector edit with
real J, identity, and five random-J transports. Authorization is only at the
vector-class-by-multiplier group level, clustering on the eight prompts after
averaging the 15 overlapping assignments. Per-assignment J claims are never
authorized. A group-level layer-50 J summary additionally requires:

- passing Stage-B hard/native actual-realized integrity;
- passing requested-edit fidelity for both signed members of every included pair;
- a passing Stage-A layer-50 BF16-versus-FP32 J-shadow gate;
- a passing Stage-A layer-50 transport gate;
- realized dose within the Stage-A layer-50 envelope; and
- a passing Stage-B direct transport gate for that vector class and multiplier.

The current analysis deliberately marks J-derived claims at other propagated
layers invalid/inconclusive. Actual residual and actual-final characterization
does not inherit that J restriction when edit integrity passes.

## Collection gates versus interpretation gates

Stage B may be collected after an independent Stage-A structural audit and a
passing **collection-safety** receipt: exact single hook, clean pre-state,
exact native post bytes, finite edits, passing realized-edit fidelity and
common-mode gates, the exact 96-row layer-50 realized-dose envelope, a passing
current-study 34-map J arithmetic/orientation gate, valid storage/provenance,
and live resource budget. Stage A need not show successful incremental real-J
transport or downstream dose-linearity for this neutral diagnostic collection
to proceed.

This separation prevents an instrument failure from suppressing the data
needed to diagnose it. It does not convert a failed scientific gate into a
pass. If Stage A incremental real-J transport or dose-linearity fails, the
corresponding J-derived interpretation remains invalid/inconclusive. A failed
J arithmetic/orientation gate blocks Stage B entirely. A failed layer-50
J-shadow gate does not impersonate an orientation failure or an edit failure;
it specifically blocks Stage-B layer-50 J interpretation. A global J-shadow
failure at another tested edit layer makes the full Stage-A scientific verdict
fail and remains visible in the per-layer receipt, while the narrower
layer-50 status continues to control Stage-B layer-50 eligibility. If Stage-B hard/native
actual-realized integrity fails, that Stage-B characterization is invalid. If
hard/native integrity passes but requested-edit fidelity fails, the archived
actual-realized vectors remain available for explicitly labelled row-level
characterization, while requested direction, vector-class, multiplier/dose,
paired-contrast, and J attribution are invalid/inconclusive for the affected
members and groups. Receipts preserve all of these statuses and counts
separately from collection authorization.

## Data, storage, and replay boundary

All raw data are written to a fresh study-owned namespace on RunPod network
volume `bv9gb9j32y`; nothing may spill to container-local disk, Git, or the
laptop. Transactions begin in a fresh partial directory, hash every artifact,
enforce no-extra-file and no-symlink rules, and become complete only through
atomic publication and a final completion receipt.

The fail-closed limits are:

- 32 GiB maximum new raw-run allocation;
- 64 GiB minimum post-run volume reserve;
- 2 GiB maximum atomic shard and a mandatory dense 2 GiB
  interruption/resume/checksum storage benchmark, explicitly non-authorizing;
  and
- conservative logical-or-allocated usage accounting against the provider's
  500,000,000,000-byte volume capacity.

The archived BF16 states, pinned J maps, final norm, LM head, tokenizer, and
vocabulary table are intended to permit arbitrary future vocabulary replay.
That is a representation capability, not a validated result. The v1 analysis
must report `not_run_replay_capable_only` and
`replay_verified_claims=false` unless a separate hash-bound replay-equivalence
run actually passes. Top-2,000 retention alone does not verify full-vocabulary
replay.

## RunPod ownership and resource contract

Execution is restricted to one newly created `NVIDIA B200` pod in `US-CA-2`,
with volume `bv9gb9j32y` (`consciousness-sae-realization-v1-us-ca-2`) mounted
at `/workspace` and the immutable container
digest above. The successor create request and ownership validation bind a
`20 GB` container disk; all retained study data still belongs on the mounted
network volume. The adapter restores the audited predecessor lifecycle's
in-memory default after each scoped call. This smaller container disk is an
operational availability repair after the frozen `50 GB` request found no
eligible instance, not a scientific or raw-storage change. Live price/stock is
checked at creation; the hourly price is
accepted only if six hours cannot exceed the hard `$36` ceiling.

The orchestration layer records sanitized full account inventories before and
after creation, binds the exact new pod ID/name to an ownership receipt, and
must leave every unrelated pod unchanged. Post-create orchestration failure
triggers exact-ID rollback and an absence receipt.

The ownership receipt's container-image attestation is copied from the fully
validated GraphQL create snapshot and names the image field independently
observed by the final REST readback, along with the upstream lifecycle and
create-request hashes. The guest launcher never manufactures that value from
the protocol constant or an operator export.

The runtime has one cumulative clock spanning staging, Stage A, audits, and
Stage B: six hours total, `$36`
maximum estimated spend, and a 20-minute no-progress watchdog. The provider
kill deadline is exactly six hours after creation.

Final cleanup deletes only the receipt-owned pod ID, verifies direct `404`
absence and the post-delete account inventory, and proves unrelated inventory
unchanged. API credentials are accepted only from `RUNPOD_API_KEY` in the
process environment and never enter arguments or receipts.

## Reporting boundary

Report every gate, including failures. Report Stage B by prompt-clustered
vector-class/multiplier groups and label all top-token inspection exploratory.
Do not call overlapping assignments independent samples. Do not call a smooth
or curved fixed-token arc a behavioral effect. Do not infer that “SAEs are
nonlinear”: the edit is algebraically additive, BF16 realization may differ
from the request, and the downstream transformer response may be nonlinear.
