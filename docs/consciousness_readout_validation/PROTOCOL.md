# Protocol: `consciousness_readout_validation_v1`

Version: `consciousness_readout_validation_v1.0.0`  
Authority: investigative pilot only; no OSF confirmatory authority  
Execution state: pre-execution; immutable public-artifact and tokenizer receipts
must pass before the first model forward

## Question and permitted interpretation

The pilot asks whether the pinned J-lens arithmetic and transport are correctly
implemented, whether a prospectively authored clean semantic instrument has the
registered sensitivity and specificity, whether factual polarity is read at the
right token position, and whether the complete SAE-vector inventory is safe to
materialize in BF16 before any edit.

It does **not** test consciousness, subjective experience, a target intervention
effect, a causal mechanism, or reproduction/falsification of the target paper.
The six public feature IDs are opaque working intervention candidates in `G4`;
their inclusion is not semantic validation.

## Frozen J-lens algebra

The absolute-readout and perturbation uses are distinct and both follow the
pinned upstream implementation. Anthropic's reference code at commit
`581d398613e5602a5af361e1c34d3a92ea82ba8e` defines the lens as
`unembed(J_l @ h_l)` and implements its row-vector equivalent as
`residual @ J_l.T` before applying the model's own final normalization and
unembedding. It supplies no intercept, affine offset, prompt-specific
reference state, or centering term. Accordingly, `G3` and `G3P` transport the
captured absolute residual state. `G2` instead transports a central-difference
residual perturbation, which is the corresponding first-order tangent
prediction. The Neuronpedia release supplies the fitted matrices; its pinned
configuration records `target_layer: null`, which the upstream fitter resolves
to the final block output (layer 79 for this 80-layer model), and 125 completed
WikiText prompts of maximum length 128.

Primary provenance:

- Anthropic reference
  [`README.md`](https://github.com/anthropics/jacobian-lens/blob/581d398613e5602a5af361e1c34d3a92ea82ba8e/README.md)
  and
  [`jlens/lens.py`](https://github.com/anthropics/jacobian-lens/blob/581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/lens.py#L135-L143);
- Neuronpedia's pinned Llama 3.3 70B
  [`config.yaml`](https://huggingface.co/neuronpedia/jacobian-lens/blob/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml).

## Exact tensor, hook, and token contract

All layer numbers in this study are zero-based transformer-block indices. A
source state at layer `L` is the hidden-state tensor returned by
`LlamaForCausalLM.model.layers[L]` after that decoder block's residual update
and before the next block. In the bound Transformers object the executable path
is `model.model.layers[L]`. The tensor is unnormalized BF16 residual-stream data
with last dimension `8192`.

For cached one-token pilot forwards, the rendered prefix is tokenized once,
tokens `x_1...x_(T-1)` are cached cleanly, and `x_T` is processed in the measured
forward. Therefore every captured `[1, 1, 8192]` source state is at position
`T`; its resulting logits predict `x_(T+1)`. The visible prefix bytes and token
IDs are identical across clean and edited forwards. `actual_final` is the exact
block-79 output captured at the input of `model.model.norm`; the production
comparison then applies that pinned RMSNorm and LM head.

At block 50 the capture hook is registered before the edit hook. `h50_pre` is
the untouched block-50 output; `h50_post` is the BF16 tensor returned after one
elementwise addition of the signed BF16 vector at the measured final position.
The edit hook must fire exactly once. The independently retained pre/post tensor
bundle must reconstruct `h50_post` byte-for-byte as BF16 `h50_pre + vector`.

The SAE consumes this same unnormalized post-block-50 residual convention. The
pinned Goodfire model card says the checkpoint was trained specifically on layer
50; the release history names the source module `model.layers.50`; and
Goodfire's linked reference notebook defines an `l19` checkpoint as
`model.layers.19` and reads `module.output`. The checkpoint itself supplies
`encoder_linear` and `decoder_linear`; production encoding is exactly
`ReLU(h @ encoder_linear.weight.T + encoder_linear.bias)`, with no centering or
normalization. The public release does not prove equivalence to any proprietary
Goodfire or Steering API intervention.

The J-lens source convention is the same post-block state at each zero-based
layer 45--78. Its target is post-block layer 79, after which the model's final
RMSNorm and LM head are applied. Runtime metadata, the machine plan, the
execution binding, and the independent audit must all agree with this contract.

## Frozen acceptance and consequence table

All listed conditions are conjunctive. A missing row, wrong grid, non-finite
value, binding mismatch, partial transaction, or failed independent audit is a
technical invalidity, not a scientific pass or fail. A technically invalid run
may be repeated only from a fresh output transaction with identical frozen
source and plan, before any valid gate result is used; the invalid receipt and
reason remain disclosed. A numeric gate failure is terminal for that gate under
`consciousness_readout_validation_v1`: there is no threshold, prompt, layer,
token, dose, matching, or vector substitution under this study ID.

| Gate | Unit and frozen pass rule | Multiplicity treatment | Consequence of numeric failure |
|---|---|---|---|
| `G1` | Every one of 34 maps x 4 fixtures must have production-versus-independent-reference relative RMSE `< 0.01` and sign agreement `>= 1.00`; the wrong-orientation control must remain distinct as specified. | Complete deterministic grid; no selection. | Blocks every J-lens endpoint and layerwise J interpretation. |
| `G2` | In each of four layer bands, the prompt-cluster 95% LCB must exceed `0.10` for residual cosine and `0.25` for fixed-token logit Pearson; each real-J-minus-best-of-five-random LCB must exceed `0.05`. Every 1%/2% anchor must have cosine `> 0.95` and slope discrepancy `< 0.15`. Across layers 45--69, real-J-minus-identity LCB must exceed `0.02` for both metrics. | Each family is an intersection-union gate: all predeclared components must pass. The strongest random control is selected inside every bootstrap draw. | Blocks causal/differential J transport claims, including intervention-change J endpoints; descriptive actual-final results cannot rescue it. |
| `G3` | For actual-final / real-J depth AUC, respectively, 95% LCBs must exceed: macro AUROC `0.80 / 0.70`, top-family accuracy `0.55 / 0.40`, and explicit-versus-adjacent AUROC `0.75 / 0.65`. Each real-J-minus-best-random LCB must exceed `0.05`. Each leave-one-explicit-token-out actual/J LCB must exceed `0.60 / 0.55`; each render mode's actual and J explicit-versus-adjacent AUROC must be `>= 0.65`. | One reused 50,000-draw family-stratified prompt-cluster bootstrap; nonlinear metrics, depth integration, and best random control are recomputed inside each draw. All components must pass. Permutation results are diagnostics, not alternate gates. | Blocks transfer of the frozen semantic panel to any successor consciousness/awareness J endpoint. A new instrument requires a new protocol and untouched validation fixtures. |
| `G3P` | Actual-final must classify `24/24`; real-J depth AUC must classify at least `22/24`; real J must exceed each of five random-J controls by at least two questions. | Exact complete question inventory; all three conditions pass together. | Blocks binary-report polarity J endpoints and any claim that this answer boundary is validated. |
| `G4` | All 300 vectors must be finite BF16, have clean-prompt vector/residual RMS ratio `<= 0.10`, and controls must have post-cast norm error `<= 0.01`. For all 1,200 sentinel edits, post-edit bytes must exactly equal the independent BF16 reconstruction, requested-vector relative RMSE must be `<= 0.10`, cosine `>= 0.995`, and hook count exactly one; no attenuation or retry. | Complete vector x sign x sentinel grid; no selection or rescue. | Blocks this public-weight intervention implementation. A successor remains obliged to build and preflight its own fresh inventory even if this pilot passes. |

Overall pilot passage requires all five gates and the independent structural
audit. Partial passage authorizes only the explicitly mapped descriptive
component; it never authorizes target execution by itself.

Both release files are execution-bound: the checkpoint SHA-256 is
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`
and the config SHA-256 is
`d4784fe625f58f2ae90318d45b9c2355f749c334a97936a04f749423992a8eb5`.
The loaded checkpoint must independently report `n_prompts=125` and
`d_model=8192`; a byte-valid checkpoint with different embedded metadata is
rejected.

The Goodfire SAE checkpoint is accompanied by two revision-pinned provenance
sidecars that are hashed as execution artifacts before loading: `README.md`
SHA-256
`dcadf1602fc337dcd538803c0e551cc93e6811b90e6fa0bb75cb8de8e0b219db`
and `config.yaml` SHA-256
`ac0a793c34ce988d2524346d3ada7f2bf2e6d63bd584b3bb80943827a3112fc4`.
The checkpoint itself must expose exactly the four frozen encoder/decoder
weight and bias tensors with the shapes in `HOOK_CONTRACT`; decoder bias is
validated for provenance but is not added to an intervention direction.

## Frozen GPU environment and launch topology

The GPU image is the immutable manifest
`runpod/pytorch@sha256:cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853`.
The human-readable tag is provenance only. Both the launch wrapper and adapter
require the immutable reference, and every phase receipts the exact container,
hardware, package, and deterministic-kernel inventory.

The only authorized pod creator includes RunPod's `terminateAfter` in the exact
GraphQL `PodFindAndDeployOnDemandInput`. It derives that RFC3339 UTC timestamp
before preflight from the prospectively authorized maximum hours, requires the
duration to be exactly representable in whole seconds, and floors any fractional
clock reading so the provider cutoff cannot exceed the authorization. The
canonical create-request hash and ownership receipt bind the same timestamp as
the local hard deadline. Active status metering and ID-plus-nonce verified
deletion remain mandatory; provider termination is only the failure backstop.

The r6 operational amendment follows the current GraphQL nullability and enum
semantics without weakening the frozen resource identity. A create mutation may
report `CREATED` or `RUNNING`, but the independently fetched REST record must
reach `RUNNING` before ownership is published. GPU authority remains exact
`gpuTypeId == NVIDIA B200` plus `gpuCount == 1`; `gpuDisplayName` is only a
bounded diagnostic. `machine.id` may be null, neither `machineId` nor
`machine.id` is an authority or equality constraint, and both are recorded only
as SHA-256 hashes. Container identity accepts only harmless absent/`docker.io`/
`index.docker.io` default-registry spelling differences while requiring the
exact `runpod/pytorch` repository and frozen SHA-256 manifest digest. Tags,
another repository, or another digest fail closed and trigger verified rollback.
Identity-failure receipts contain at most three fixed-allowlist mismatch field
names with safe bounded observations or identifier hashes, never a raw response.
Ownership and preflight receipts likewise omit raw host IDs, machine locations,
volume names, provider lifecycle timestamps, runtime IPs, and public-port
mappings. They retain only hashes or non-identifying presence/count booleans;
SSH endpoint discovery is ephemeral operational state outside the evidence
receipt.

The r7 provider-nullability amendment permits creation-time GraphQL `locked` to
be only `null` or `false`; it canonicalizes the requested state to false and
still requires the independent REST record to prove exact `locked=false` before
ownership. Any other GraphQL value or any non-false REST value fails closed.

The r8 observability amendment allows a persistent REST-hydration failure to
record only the fixed names of missing reliable top-level fields. No provider
values, endpoints, or raw response are included, and the rollback requirement
is unchanged.

The r9 lifecycle amendment requires the creation response to report exact
`podType=RESERVED`. Per-pod REST may omit `locked` and `interruptible`, and its
compact receipt records each as `absent`, `observed_null`, or `observed_false`
according to whether the key is absent, present with null, or present with the
exact boolean false. Any other concrete value is contradictory and fails
closed. All other reliable top-level requirements are unchanged. After REST reaches
`RUNNING`, a fixed read-only GraphQL `pod(input: PodFilter)` query must return
the exact mutation ID and nonce name plus `locked=false`, `podType=RESERVED`,
and `desiredStatus=RUNNING`. A temporarily absent pod, null lock, null pod type,
or null/`CREATED` desired state is bounded-polled. Wrong identity, an explicit
non-`RESERVED` type, another explicit state, any non-null lock other than exact
false, a malformed response, or transport failure fails immediately. One final
expanded REST read is adjacent to the successful GraphQL proof and must
reconfirm exact ID/name, every available configuration field, `RUNNING`, and
the unchanged creation price; optional null or absent lock/interruptibility is
recorded, while any concrete contradiction or read failure triggers verified
rollback. Ownership seals this final REST corroboration plus only the GraphQL
request hash, safe selected values, and attempt count. Pod update/reset is
outside the REST allowlist and is never used.

Before the public-artifact stager may initialize or validate the persistent
volume sentinel, a separate read-only in-guest attestation must pass. The
caller's ownership-proven pod ID and the fixed `qf2lwehl89` / `US-NE-1`
identities must exactly match `RUNPOD_POD_ID`, `RUNPOD_VOLUME_ID`, and
`RUNPOD_DC_ID` in the provider-initialized PID 1 environment. Their omission from an
SSH child environment is not treated as absence from the provider guest and no
controller-injected value is described as provider-observed. The gate reads
`/proc/1/environ` with fixed byte, entry-count, and entry-size bounds and decodes
only those three allowlisted variables. All non-allowlisted values remain opaque
bytes and are not decoded, emitted, logged, sourced into the child environment,
or persisted as evidence. Missing, duplicate, malformed, or mismatching allowlisted
values fail before publication. `nvidia-smi` must enumerate exactly one B200 with at
least 160 GiB; `/workspace` must resolve directly to a writable mount with one
exact, bounded-parsed `/proc/self/mountinfo` entry. The receipt seals the exact
device major/minor. The mount-point field alone is decoded with the fixed set of
kernel-required mountinfo escapes so it can be compared to exact `/workspace`.
The mount-root and mount-source fields are instead treated as bounded opaque
UTF-8 with no control codepoints and no backslash interpretation; the receipt
stores SHA-256 of each exact raw field's UTF-8 bytes and an explicit
`sha256_utf8_of_exact_raw_mountinfo_field_without_unescaping` semantic marker.
Thus provider/FUSE notation such as literal `\043` is accepted without colliding
with a decoded `#`, while a same-filesystem-type remount still cannot replay.
The current free space must cover
the 156,023,372,845-byte frozen selection plus 40 GiB while predicting at least
32 GiB free after staging. An existing study sentinel must exactly match; an
absent sentinel remains absent during attestation.

Both attestation and staging must be launched through the bound
`run_guest_preflight.sh` from the physical `/root/pilot_repo` source copy. The
wrapper rejects any source root at or beneath `/workspace` before Python starts,
exports exact `PYTHONDONTWRITEBYTECODE=1`, and uses exact `python3 -B -m` module
launches. The guest independently verifies the bounded Linux process command
line and active runtime flag. Its receipt seals those facts and a SHA-256 of the
resolved repository root; the stager rechecks the same physical source binding
and its own exact no-bytecode launch before any volume mutation.

Only after all checks pass may the gate publish a canonical self-hashed receipt
in a fresh directory outside the repository and `/workspace`. The receipt
stores no credential, raw provider response, GPU UUID, raw repository path, or
raw mount root/source. It is bound to a hash of the current guest boot ID and
expires after 15 minutes. The receipt explicitly records
`provider_pid1_environment` provenance and the three allowlisted values. The
stager makes this receipt mandatory and rechecks its hash, the current bounded
PID 1 identity observation, boot,
age, current B200/mount/disk state, and unchanged sentinel state before its
first volume write. The staging receipt retains the guest-attestation hash and
owned pod/volume/data-center identities.

One all-phase process performs artifact validation and tokenizer audit once,
writes all five phase lineage receipts durably, then loads the model, SAE, and
J-lens once. Gates run in frozen order `G1`, `G2`, `G3`, `G3P`, `G4`. Each gate
has a fresh run ID, separate sealed file manifest, and its own model-forward
counter/timestamps; consequently `G1` still records exactly zero forwards.
Before the 70B model is loaded, the wrapper and adapter require
`CUBLAS_WORKSPACE_CONFIG=:4096:8` and execute a tiny deterministic CUDA matrix
multiplication. The exact environment value is included in each phase runtime
receipt and independently checked by the structural auditor.

## Frozen gates

`G1` covers every J map from layers 45 through 78. At each layer, four synthetic
residual fixtures are evaluated by production arithmetic, an independently
written component-level reference, and a deliberately wrong-orientation negative
control. A deterministic tokenizer-aware rejection sampler selects 32 vocabulary
IDs from a SHA-256 stream bound to the study ID and protocol version. It rejects
special IDs, duplicates, non-roundtripping pieces, anything that does not exactly
match ASCII ` [A-Za-z]{3,16}`, and a prospectively enumerated endpoint/target lexicon
(including `alert` and `secret`). The plan contains no executable panel until a
receipt records the complete accepted and rejected sequence; failure permits no
substitution.

`G2` uses 24 exact neutral factual prompts. Its primary grid is all 34 layers,
two study/version-bound hash-seeded PCG64 Gaussian directions, both signs, and a 2% residual-RMS
dose. The 1% linearity anchor is limited to prompts 01–08, direction 0, both
signs, and layers 45, 50, 55, 60, 65, 70, 75, and 78. Identity and five
hash-seeded random-J controls use the same statistic.

`G3` contains exactly 72 clean clozes: nine semantic families with eight items
each. Both formats are unfinished assistant prefills ending at the stem with no
trailing space. Items 1–4 use `minimal_prefill`: system instruction, user
`Complete this sentence:`, and assistant stem. Items 5–8 use `framed_prefill`:
system instruction, user `Give the one-word completion for this sentence.`, and
assistant `The sentence reads: {stem}`. Both use
`continue_final_message=True`. Every one of the 72 rendered prefixes must extend
by exactly one token for every one of the 28 leading-space semantic candidates
(2,016 audited continuations). No first-subtoken scoring, replacement, or empty
assistant boundary is allowed. The wakefulness panel uses `vigilant`, not the multi-token
`wakefulness` piece. `G3` contains no intervention and establishes only diagnostic readout
behavior on these fixtures.

`G3P` contains 24 balanced, paired factual questions with exact `Yes`/`No`
labels. At the actual chat boundary, the correct unspaced token IDs are
`Yes=9642` and `No=2822`. For both answers at all 24 contexts, the full rendered
assistant message must equal the exact prefix plus `[answer_id, 128009]`, where
`128009` is the EOT token. The gate validates polarity parsing and position only.

G3 confidence bounds use 50,000 direct family-stratified prompt-cluster
bootstrap draws. A single SplitMix64-derived count matrix is reused across
conditions; NumPy recomputes the nonlinear accuracy and AUROC statistics on
every draw. Depth integration is performed within each draw, and the maximum
of the five random-J controls is selected within that same draw before the
real-J advantage is formed. No jackknife or pseudo-value approximation is used.

`G4` enumerates all 50 combinations of two, three, or four of the six public
feature IDs. Target coordinates have literal absolute coefficient `0.5`;
fresh matched-SAE directions begin at the same base coefficient and, like the
isotropic directions, receive one deterministic BF16 norm match to the target
aggregate with at most `0.01` relative error. Matched IDs are selected
one-to-one using only fresh 32-neutral-prompt layer-50 statistics under the
frozen metric in `protocol.py`. All 300 signed vectors
must pass the 10% relative-RMS preflight on every clean prompt before any edit.
There is no attenuation, replacement, or retry under this study ID.

This preflight certifies only the 300 vectors materialized inside this pilot
and the frozen construction/checking implementation. It does not pre-certify a
successor experiment that recomputes matched controls or uses successor-bound
isotropic seeds. Such a successor must independently repeat target-blind
matching, vector materialization, and the complete preflight before any target
prompt. Pilot mappings, vectors, measurements, and receipts are not successor
inputs; only the public target IDs and frozen source-level procedure may be
carried forward.

The matching table is exact, not an implementation choice. At every valid
token, layer-50 residuals, encoder weights, and encoder bias are cast to BF16
before `ReLU(linear(...))`; sums are accumulated in float64, counts as
integers, and maxima in float32. Each feature uses log-one-plus float32 L2 norm
of the decoder column after its exact BF16 cast,
log-one-plus conditional mean over strictly positive activations (zero if
inactive), log-one-plus strictly positive maximum (zero if inactive), and the
strictly-positive fraction over all valid tokens. Eligible candidates are
scaled by the coordinatewise float64 median and unscaled MAD, with divisor
`1.0` exactly when MAD is zero. Matching minimizes the float64 sum of squared
standardized-coordinate differences, without a square root or rounding, using
the frozen target order and smaller feature ID for an exact tie.

Vector construction is likewise CPU-only and ordered. Each selected decoder
column is first cast to BF16, then added in listed feature-ID order to a
float32 CPU accumulator; the accumulator is multiplied by literal float32
`0.5` and cast once to BF16. Control and target norms are computed from those
BF16 vectors after float32 cast. The target/raw norm ratio is cast once to a
BF16 scalar and multiplied once into the raw BF16 control, with no iterative
correction. Isotropic vectors come from the assignment-bound NumPy PCG64
float32 stream, receive one L2 normalization and BF16 cast, and then use that
same norm-match path. Negative branches are exact elementwise BF16 negations.

Hook correctness and requested-vector fidelity are separate. For every sentinel
edit, the observed BF16 post-edit tensor must be byte-identical to an
independently reconstructed BF16 `pre_edit + signed_vector` tensor. Ordered
pre/post BF16 tensors are retained only on the external volume so the
structural auditor can repeat this check. Because BF16 addition necessarily
rounds at the scale of the pre-edit residual, the realized float32
`post_edit - pre_edit` is separately required to have relative RMSE at most
`0.10` and cosine at least `0.995` against the requested signed BF16 vector.
The earlier `0.001` draft tolerance was removed before any pilot outcome after
a model-free arithmetic check showed it was below unavoidable BF16 rounding.

## Data and path isolation

Tracked plan metadata lives only under `data/consciousness_readout_validation/`.
Large or outcome-bearing artifacts, if execution is separately authorized, must
live below a sentinel-bound external root named by
`CONSCIOUSNESS_READOUT_VALIDATION_ARTIFACT_ROOT` and
`CONSCIOUSNESS_READOUT_VALIDATION_VOLUME_ID`. Paths from prior outcome studies
are rejected. The positive input allowlist contains only the pinned public model,
SAE, J-lens, and the two embedded fixture/protocol source files.

The authorized analysis command is held to the same boundary: every phase
directory and audit receipt must be a non-symlink descendant of the
sentinel-bound external study namespace, and `ANALYSIS_RESULT.json` is written
only in a fresh direct child of its external `analysis/` directory. No
outcome-bearing analysis result is written into the repository.

The scaffold writes no target prompt, target outcome, activation, residual,
generation, judgment, or effect estimate. `artifact_bindings.json` and
`token_metadata.json` deliberately remain unresolved and therefore execution
prohibited until independently validated binding receipts exist.

## Hash semantics

The plan distinguishes three hashes:

- `content_sha256`: exact bytes of one plan or source file;
- `canonical_payload_sha256`: canonical JSON over the ordered plan file records;
- `plan_manifest_sha256`: canonical JSON over the manifest excluding only that
  field.

The validator also reports `manifest_file_sha256`, the hash of the exact encoded
manifest file. These values are not interchangeable.

Every stable row ID and deterministic seed domain—including synthetic fixtures,
finite-difference directions, random-J controls, isotropic vectors, bootstrap,
and permutation streams—is prefixed by the exact study ID and protocol version.
