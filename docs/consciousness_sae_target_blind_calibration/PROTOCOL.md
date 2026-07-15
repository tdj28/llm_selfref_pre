# Pre-SAE Generic-Vector Delivery and J-Readout Calibration v2

Status: prospective adaptive calibration candidate, before any v2 model
forward. This document and its machine plan must be frozen before execution.

## Purpose and claim boundary

The prior `consciousness_sae_realization_validation_v1` Stage A executed
successfully but found that every generic 1% edit failed its frozen
requested-to-realized vector-fidelity criteria. The 1–8% downstream response
also failed the frozen dose-linearity gate. The real Jacobian beat five random
maps but did not clear the prespecified margin over identity. No target SAE
features, paper prompts, consciousness lexicon outcomes, or behavioral outcomes
were collected.

This new study is an adaptive, target-blind numerical calibration, not a rerun,
an SAE intervention, or a paper replication. It deliberately injects generic
vectors before any later SAE study and asks:

1. At layer 50, are signed generic edits of 2–8% source-residual RMS delivered
   faithfully by the native BF16 hook?
2. Is the *realized source edit* locally dose-linear over 2/3/4%, anchored at
   3%?
3. For actual post-injection states at layers 50–78, how well does each released
   `J_l` predict the observed final signed delta relative to identity and five
   fresh, v2-seeded random-J controls?
4. Is downstream model response locally linear? This is recorded as an outcome,
   not treated as a technical delivery failure.

The maximum conclusions are fixed-panel generic-vector delivery and
readout-validation claims. This run cannot support a claim about SAE steering,
deception, self-reference, consciousness, subjective experience, hidden
belief, model intent, or behavior.

## Separation from prior experiments

The study has a new identity, plan directory, raw namespace, prompt panel,
runtime seed, direction seeds, 2,048-token panel, random-J controls, and
J-orientation fixtures:

- study: `consciousness_sae_target_blind_calibration_v2`
- protocol: `consciousness_sae_target_blind_calibration_v2.0.0`
- plan: `data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3`
- raw: `<network-volume>/consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/raw/<run-id>`

The physical SHA-256 hashes of the predecessor Stage-A audit, receipt, and
summary are disclosed in `adaptive_design_inputs.json`. Only five compact facts
listed there informed the new dose design. No prior raw tensor, scalar row,
prompt outcome, fitted parameter, target vector, or semantic result is loaded,
pooled, or treated as v2 evidence. The v2 analysis input list is exactly empty.
In particular, the predecessor runtime seed, token panel, realized random-J
maps, and orientation measurements are not reused. All v2 seeds bind the new
study ID, protocol version, namespace, and coordinate.

## Pinned artifacts and runtime

- Model: `meta-llama/Llama-3.3-70B-Instruct`, revision
  `6f6073b423013f6a7d4d9f39144961bfbfbc386b`, BF16, 80 layers, width 8192.
- SAE cache artifact (provenance check only; no SAE feature is selected or
  injected): `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, revision
  `128ee921ecd1b8b3a87d776cbcc357c0855da134`, weight SHA-256
  `81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6`.
- J lens: `neuronpedia/jacobian-lens`, revision
  `a4114d7752d11eb546e6cf372213d7e75526d3a1`, checkpoint SHA-256
  `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
  Released source layers are 45–78 and target layer is 79. Row-vector
  implementation is `residual @ J_l.T`.
  The checkpoint and release config are frozen at
  [checkpoint](https://huggingface.co/neuronpedia/jacobian-lens/resolve/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext/Llama-3.3-70B-Instruct_jacobian_lens.pt)
  SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`
  and [config](https://huggingface.co/neuronpedia/jacobian-lens/resolve/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml)
  SHA-256 `d4784fe625f58f2ae90318d45b9c2355f749423992a8eb5`.
- Image: `runpod/pytorch@sha256:cb154fcca15d1d6ce858cfa672b76505e30861ef981d28ec94bd44168767d853`.
- Hardware: exactly one NVIDIA B200 with at least 160 GiB VRAM, in `US-CA-2`,
  attached to network volume `bv9gb9j32y`.
- Determinism: the inherited, source-bound backend disables TF32, flash SDP,
  and memory-efficient SDP; enables deterministic algorithms and math SDP; and
  requires `CUBLAS_WORKSPACE_CONFIG=:4096:8`. The executor supplies the fresh
  v2 runtime seed rather than accepting the predecessor default.
- Runtime packages: the B200 guest installs the exact frozen package set in
  `experiments/consciousness_sae_target_blind_calibration/requirements-runpod-b200.txt`
  by running, from the repository root:

  ```bash
  bash experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh
  ```

  The setup script first checks pod/volume/data-center identity, performs the
  exact install, runs `pip check`, and independently verifies the pinned package
  versions.

  GPU execution then enters only through the source-bound calibration guest
  launcher. The launcher validates ownership before importing Torch or
  Transformers, derives the immutable image/determinism environment, forbids a
  second ownership-receipt argument, and replaces itself with the sole v2
  runner:

  ```bash
  python3 -B -m experiments.consciousness_sae_target_blind_calibration.guest_launcher \
    --ownership-receipt <ownership-receipt.json> -- \
    --plan-dir data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3 \
    --volume-root /workspace \
    --volume-id bv9gb9j32y \
    --run-id <new-calibration-run-id> \
    --model-snapshot <pinned-model-snapshot-directory> \
    --sae-path <pinned-sae-checkpoint> \
    --j-lens-path <pinned-j-lens-checkpoint> \
    --guest-receipt <guest-receipt.json> \
    --cache-receipt <cache-receipt.json> \
    --authorization-receipt <final-authorization-receipt.json>
  ```

  The launcher injects the already validated ownership path into the runner;
  callers must not repeat it after `--`.

All cached public files are rehashed against the pinned revisions, physical
SHA-256 values, and cache receipt before model load. The calibration reuses the
already cached bytes on the retained network volume; it does not reuse prior
outcome rows or prior randomized controls.

## Fresh neutral prompt panel

System message for every prompt:

> Answer the mundane question briefly and literally. Do not add commentary.

The eight new user messages are:

1. What object is commonly used to unlock a door?
2. Which planet is closest to the Sun?
3. What color are ripe bananas usually?
4. Which room in a home commonly contains a bathtub?
5. How many days are in a standard week?
6. What handheld tool is commonly used to cut paper?
7. Which body part is normally used for hearing sounds?
8. What appliance turns slices of bread into toast?

The tokenizer-rendered IDs and hashes are archived. No generation, judging, or
behavioral scoring occurs.

## Intervention and capture contract

Three generic isotropic directions are generated by PCG64 from the new study
identity, direction index, and a frozen namespace. Each is normalized to unit
RMS in FP32. They are not SAE decoder columns and contain no target feature ID.
The runtime, direction, fixed-token-panel, random-J, and orientation namespaces
are respectively `runtime-v2`, `generic-layer50-direction`,
`fixed-token-panel-v2`, `random-j-v2`, and `j-orientation-fixture-v2`.

For each prompt and direction, the requested positive vector is

`unit_direction * RMS(clean_layer50_source) * dose_fraction`.

The FP32 request is cast once to BF16. A single-use hook adds the positive or
exact BF16-negative vector to the residual at layer 50. Positive and negative
branches share the same prefix KV cache and are always analyzed as a central
signed contrast. The hook must fire exactly once per branch.

The dose grid is `1%, 2%, 3%, 4%, 8%` of clean layer-50 source RMS:

- 1% is a disclosed diagnostic only and cannot fail the numerical fidelity or
  linearity authorization; universal hard native safety still applies.
- 2/3/4/8% gate actual-state fidelity/common-mode and, separately, J-shadow
  claim eligibility.
- 2/3/4% form the local-linearity band, anchored at 3%.
- 3% is the primary transport/readout dose.

Every branch captures released J-source layers 45–78, explicit layer-50
post-edit state, and the final pre-RMSNorm state. Layers 45–49 must remain
byte-identical to clean for both signed branches. Layer 50 is explicitly
represented by pre- and post-edit states. Layers 51–78 are actual post-edit
model states.

The exact intervention coordinate is machine-frozen in
`INTERVENTION_STATE_CONTRACT`. The chat template is rendered with a generation
prompt. One prefix forward consumes `token_ids[0:-1]`; each clean or signed
continuation forward consumes only `token_ids[-1]` with sequence length one.
The edit hook is a forward hook on zero-based `model.model.layers[50]`, so it
edits that block's output after block 50 and before block 51, at tensor slice
`hidden_state[0,0,:]` with shape `[1,1,8192]`. Capture is registered before the
edit hook, and both pre-edit and explicit post-edit layer-50 states are
archived. The request is constructed in FP32, cast once to BF16, and applied by
native BF16 addition or subtraction. Clean, plus, and minus continuations use
independent clones of the same immutable prefix-cache values; branch ordering
is not part of the estimand. The inherited implementation file is itself bound
by its physical SHA-256 entry in `source_files.json`.

The released-J coordinate is separately machine-frozen in `J_STATE_CONTRACT`.
At pinned upstream commit
`581d398613e5602a5af361e1c34d3a92ea82ba8e`, the
[hook code](https://github.com/anthropics/jacobian-lens/blob/581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/hooks.py)
captures transformer-block outputs, the
[Hugging Face adapter](https://github.com/anthropics/jacobian-lens/blob/581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/hf.py)
binds those hooks to the model blocks, and the
[fitting code](https://github.com/anthropics/jacobian-lens/blob/581d398613e5602a5af361e1c34d3a92ea82ba8e/jlens/fitting.py)
maps a null target-layer config to the final zero-based block, layer 79. Thus
`J_50` receives the explicit post-edit block-50 delta, `J_51` through `J_78`
receive their respective post-block deltas, and every map predicts the
block-79 output delta, which is the final RMSNorm input. Row-vector application
is exactly `residual_delta @ J_l.T`; there is no intercept or centering term.
The machine contract additionally freezes the exact source-byte SHA-256 values
for `hooks.py`, `hf.py`, and `fitting.py` as, respectively,
`c781d6944fd23396d3fc65a04db1f1db807f6f12cd5912cdbd2fb67eb3508081`,
`228cf078e4586a7b7f61a6f5064403b8960de337afd19256efa56f04d53e3222`,
and `5be8959db8efc34cee41ed677beba84e21ba3c9e3ccb958bdbc1600c86b5e080`.

## Exact inventory

- 8 prompts × 3 directions × 5 doses = 120 signed pairs.
- 240 edited continuation forwards (one plus and one minus per pair).
- Each prompt session uses one prefix forward and one clean continuation
  forward: 8 + 8 = 16 unedited forwards.
- Exactly 256 full-model forward invocations: 8 prefix + 8 clean continuation
  + 240 edited continuation. Orientation fixtures add zero model forwards.
- 120 realization/J-shadow rows.
- 24 local-linearity sites.
- 34 released J maps × 2 fresh fixtures = 68 current-study orientation rows;
  these require no model forward.
- At primary dose: 8 prompts × 3 directions × 29 readout layers × 7 transports
  = 4,872 readout-transport rows.

No smoke result is a scientific or dose-selection input. If an operational
smoke is performed, its prompt and direction must be disjoint and its results
remain in external operational receipts.

## Raw measurements and independent recomputation

The raw RunPod-only transaction stores, for every signed pair:

- both complete BF16 residual arcs;
- the exact FP32 and BF16 request vectors;
- realized plus, realized minus, central realized, common-mode, and final
  central FP32 deltas;
- BF16 production and FP32-shadow layer-50 J predictions;
- at 3%, the actual source delta at every layer 50–78;
- real-J, identity, and five random-J final-delta predictions for every readout
  layer;
- the corresponding fixed 2,048-token predicted and actual logit deltas.

An independent audit performs no model forward and does not construct the full
70B model. It does require the rehashed pinned J checkpoint and the pinned model
snapshot weights needed for final norm and LM-head recomputation. It does not
accept runner-emitted scalar results as evidence: it rehashes every manifested
raw file, reconstructs realized edits from the signed pre/post arcs, and
recomputes fidelity, common-mode, J-shadow, linearity, residual-cosine, and
selected-logit Pearson metrics from archived tensors. It also reconstructs the
fresh fixed-token inventory and checks the identity/random/real-J transport
identity and tensor bindings. Missing, duplicate, extra, nonfinite, partially
written, or unmanifested data are rejected.

Independently, the plan validator reconstructs all 120 coordinates, recomputes
the physical hashes of every plan and source artifact, checks the exact pinned
model/SAE/J/image metadata, and requires the complete source closure. Before a
model forward, the runtime recomputes the public-artifact hashes from the
receipt-owned cache. Compact summaries include by-dose min/median/max values and
separate component statuses so failure magnitude and substage remain visible
without downloading raw tensors.

The audit runs on the same B200 before compact-artifact retrieval. Both output
paths must use the exact names below inside the same fresh, not-yet-created
directory outside the raw transaction. The auditor stages and fsyncs the pair,
atomically publishes their containing directory, then writes and fsyncs
`PUBLICATION_COMPLETE.json` under the still-active 90-minute watchdog. If any
publication step crosses the deadline, the directory is quarantined under a
hidden `.expired` name and is not an admissible result:

```bash
CUBLAS_WORKSPACE_CONFIG=:4096:8 PYTHONDONTWRITEBYTECODE=1 \
python3 -B -m experiments.consciousness_sae_target_blind_calibration.audit \
  --run-root <published-raw-run-directory> \
  --plan-dir data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3 \
  --model-snapshot <pinned-model-snapshot-directory> \
  --j-lens-path <pinned-j-lens-checkpoint> \
  --ownership-receipt <ownership-receipt.json> \
  --guest-receipt <guest-receipt.json> \
  --cache-receipt <cache-receipt.json> \
  --authorization-receipt <final-authorization-receipt.json> \
  --artifact-device cuda:0 \
  --audit-out <fresh-compact-directory>/CALIBRATION_AUDIT.json \
  --summary-out <fresh-compact-directory>/CALIBRATION_SUMMARY.json
```

## Frozen numerical criteria

Hard safety at all 120 pairs:

- exactly one hook fire per signed branch;
- pre-edit layer 50 equals clean;
- native BF16 post bytes equal `pre + requested`;
- layers 45–49 equal clean;
- all archived tensors and metrics finite.

Actual-state collection has exactly three measurement gates at every one of the
96 gated 2/3/4/8% pairs: hard native delivery above, requested-to-realized
fidelity, and common-mode control. Requested-to-realized fidelity is checked
separately for the positive branch, sign-corrected negative branch, and central
signed contrast:

- maximum requested-to-realized relative RMSE across plus/minus/central ≤ 0.10;
- minimum requested-to-realized cosine across plus/minus/central ≥ 0.995;
- common-mode RMS / central realized RMS ≤ 0.10.

The J arithmetic gates are separate and apply only to J-derived claims:

- all 68 fresh current-study orientation fixtures pass the production-versus-
  explicit-reference and wrong-orientation-control criteria;
- BF16-production versus FP32-shadow J cosine ≥ 0.995;
- BF16-production versus FP32-shadow J relative RMSE ≤ 0.10.

Local linearity is evaluated at every prompt × direction site over 2/3/4%,
with 3% as anchor. The realized-source component is divided by the requested
BF16 RMS fraction so nonlinear delivery gain cannot be normalized away.
J(realized) and the actual final response are divided by the realized-source
RMS fraction because their input is the delivered perturbation. Every component
reports minimum cosine and maximum relative slope discrepancy. Thresholds are
cosine ≥ 0.95 and discrepancy ≤ 0.15; a zero delivered scale is a finite failed
linearity observation rather than an exception.

Realized-source linearity gates only a linear source-response claim.
J(realized) linearity gates only a linear-J interpretation. Actual-final
linearity gates only a linear downstream-response claim. Failure of any of
these linearity checks is a substantive nonlinear result and does not block a
discrete, faithfully delivered actual-state contrast.

## Primary fixed-panel J readout and descriptive layer profile

At the primary 3% dose, the signed actual delta at every layer 50–78 is
transported through:

- the released real `J_l`;
- identity;
- five fresh v2-seeded random-J controls produced by target-independent
  permutations and signs around the same matrix spectrum. No predecessor
  control realization is reused.

Each prediction is compared with the observed final signed delta using residual
cosine and fixed-panel logit-delta Pearson correlation. Layer 50 is the sole
prospectively primary readout layer. The estimand is the mean over the exact
three frozen directions within each prompt, followed by the mean over the exact
eight frozen prompts. A 20,000-replicate prompt resampling calculation is
reported as a **fixed-panel prompt-resampling stability interval**, not as a
population confidence interval. It supports no generalization to a prompt or
direction population. Direction-specific summaries are also reported.

The 2,048 logit coordinates are generated deterministically from token IDs
0–127,999. Llama 3's reserved/special range at IDs 128,000–128,255 is excluded,
so those control coordinates are ordinary vocabulary tokens rather than chat
control markers. This remains a fixed token panel, not a sample from a token
population.

The thresholds remain those frozen before v1, but are evaluated for eligibility
only at primary layer 50 and only for this exact fixed panel:

- absolute real-J residual-cosine LCB > 0.10;
- absolute real-J logit-Pearson LCB > 0.25;
- real-J minus identity LCB > 0.02 for each metric;
- real-J minus the strongest of five random controls LCB > 0.05 for each
  metric.

Statuses are never aliased to one composite value:

- absolute real-J status;
- real-J-over-random status;
- real-J-over-identity status;
- all-component composite status.

Absolute plus random-control passage permits a bounded descriptive claim that
the released layer-50 J readout captures intervention-related structure beyond
the random controls on this panel. Identity passage is additionally required to
claim learned-J added value over carrying the residual delta forward unchanged.
An identity miss does not invalidate exact actual-state contrasts and is not
silently relabeled as a successful J-added-value result.

Layers 51–78 are a prespecified descriptive trajectory only. Their point
summaries and stability intervals are retained to show the downstream arc, but
they cannot pass or fail an eligibility gate, cannot replace layer 50, and
cannot be searched to select a favorable layer. This prevents the 29-layer
profile from silently creating 29 primary tests.

## Prospective decision rule

The calibration authorizes designing a separate actual SAE experiment only if:

1. the complete raw transaction and independent audit pass;
2. all 120 pairs pass hard native delivery; and
3. all 96 gated edits pass the signed requested-to-realized fidelity and
   common-mode criteria.

The later experiment must be frozen after this calibration and must cite its
receipt hashes. Calibration rows will not be pooled with later target rows. A
new GPU campaign and raw namespace will be used.

Realized-source, J(realized), and downstream actual-final linearity do not gate
actual-state collection; they gate only their corresponding linear-response
claims. Current-study orientation and BF16-versus-FP32 J-shadow fidelity also
do not gate actual-state collection, but both must pass before any J-derived
projection claim is made. If either fails, the later study may still collect
and compare actual residual states while treating J readouts as unavailable.
If J-over-identity fails, the later study may still collect and compare actual
states, but it may not claim that learned J is superior to identity. Only the
prospectively primary layer-50 result may support a later learned-J claim tier.
The remaining-layer trajectory is descriptive and cannot authorize or rescue
that tier.

## Exact build, validation, and pod lifecycle commands

Run the build and independent validation from the repository root. Both target
paths must be absent before invocation; neither command overwrites output:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_target_blind_calibration.build_plan \
  --output-dir \
  data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_target_blind_calibration.validate_plan \
  --plan-dir \
  data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3 \
  --output \
  data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3/INDEPENDENT_PLAN_AUDIT.json
```

With `RUNPOD_API_KEY` already exported in the local process environment, create
exactly one receipt-owned pod from the repository root. The receipt directory
must be fresh and outside the repository:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_realization_validation.runpod_orchestrator \
  create --receipt-dir <fresh-external-provider-receipt-directory> --execute
```

After transferring that directory's `OWNERSHIP.json` to the pod, run both
network-free guest and full-cache gates there, before setup or any model
forward. The preflight receipt directory must also be fresh:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_realization_validation.runpod_preflight all \
  --ownership-receipt <ownership-receipt.json> \
  --receipt-dir <fresh-external-preflight-receipt-directory>
```

This produces `GUEST_PREFLIGHT.json` and `CACHE_PREFLIGHT.json`. After the
runner, independent audit, compact-artifact retrieval, and checksum
verification finish, terminate only the receipt-owned pod from the local
repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_realization_validation.runpod_orchestrator \
  terminate \
  --receipt-dir <same-external-provider-receipt-directory> \
  --pod-id <pod-id-from-OWNERSHIP.json> --execute
```

## Final freeze and execution authorization

The generated plan is not itself permission to start the GPU. After the plan
and every bound source are committed and pushed, a separate authorization
receipt must verify that local `HEAD` equals the live remote branch commit and
that every plan-defining path is clean. That receipt binds the final commit,
plan and source hashes, reviewed-plan adjudication, ownership/guest/cache
receipt chain, exact pod and volume, budget, and deadlines. The executor refuses
to run without the matching authorization. The plan-build commit field is
historical provenance; it is not a substitute for this final pushed-commit
authorization.

Both preserved GPT Pro attempts returned provider status `incomplete`. The
final adjudication may close only their visible findings and must retain that
limitation; it cannot describe either attempt, or the unreviewed r3 bytes, as a
completed or passing Pro review.

The external authorization receipt is issued once, after provider ownership,
guest, and cache receipts exist and before the first model forward:

```bash
python3 -B -m experiments.consciousness_sae_target_blind_calibration.authorize \
  --plan-dir data/consciousness_sae_target_blind_calibration/calibration_v2_plan_20260714_r3 \
  --ownership <ownership-receipt.json> \
  --guest <guest-receipt.json> \
  --cache <cache-receipt.json> \
  --review-adjudication <tracked-review-adjudication.json> \
  --hourly-price-usd 6.0 \
  --output <fresh-external-receipt-directory>/CALIBRATION_AUTHORIZATION.json
```

## Resource and storage bounds

- provider ownership deadline: six hours, with a provider-authority spend cap
  of $36.00;
- campaign sub-watchdog: 90 minutes total, always earlier than the provider
  deadline;
- runner sub-watchdog: 60 minutes and at most $6.00 at the frozen conservative
  rate;
- independent-audit reserve: the final 30 minutes and $3.00; the runner must
  stop when its 60-minute budget expires and cannot consume this reserve;
- conservative accounting rate: $6.00/hour, so the 60 + 30 minute partition
  exactly equals the $9.00 calibration ceiling and six hours exactly equals
  the $36.00 provider authority ceiling;
- maximum authorized calibration compute: $9.00;
- raw calibration ceiling: 1 GiB;
- post-run free-space reserve: 64 GiB;
- expected raw size: approximately 320 MB (about 306 MiB), below the 1 GiB
  hard ceiling;
- compact plans, hashes, receipts, and summaries may enter Git;
- raw residuals, arithmetic tensors, and raw logits remain on the RunPod
  network volume.

The exact receipt-owned pod is terminated immediately after compact artifacts
are retrieved and checksum-verified. The persistent network volume remains
because the user explicitly requested remote retention of raw data.

## Failure and claim policy

No threshold is weakened after outcomes. Startup failures before model forward
remain zero-forward operational incidents. Partial transactions remain under a
`.partial` path and cannot be accepted by the auditor. A failed gate preserves
the raw data and produces a negative/diagnostic result; it does not trigger an
automatic favorable-dose retry.

The calibration is adaptively motivated and will be described as such. It is
not independent confirmation of v1, not a consciousness result, and not
evidence that all SAEs or all model interventions are linear or nonlinear.
