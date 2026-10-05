# Kolibri A3 Storage Qualification

This additive technical repair is prospective for a fresh cheap qualification,
not a retrospective pass for A2. No research/target outcomes were collected.
The original empty-report race, A1 Ninja PATH failure, and A2 storage-assertion
failure remain unchanged, with their retrievals, GET404 closures, and costs.

## Diagnosis

A2 used an RTX 4090, Torch 2.13.0/CUDA 13 and the pinned vLLM 0.29.0/plugin 1.0.0.
The saved log selected `MarlinFP8ScaledMMLinearKernel` for `Fp8LinearMethod` and
the Triton FP8 MoE backend. Execution reached the post-forward RPC inspector;
the original complete-token/finite-logprob validator precedes that RPC.
The overall saved verdict remains failed. No trained-model or H200 failure is
established by this tiny, random-checkpoint assertion.

The versioned official implementations are
[the Marlin kernel](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/model_executor/kernels/linear/scaled_mm/marlin.py),
[FP8 preparation](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/model_executor/layers/quantization/utils/marlin_utils_fp8.py),
and [the quantization method](https://github.com/vllm-project/vllm/blob/v0.29.0/vllm/model_executor/layers/quantization/fp8.py).
Marlin packs E4M3FN bytes into int32 storage and transforms scales for its
weight-only FP8 operator. The old inspector incorrectly required unrepacked
E4M3FN weights and FP32 scales after this preparation. Native FP8 storage and
Marlin weight-only execution are explicitly different runtime paths.

## Bounded Delta

Only the cheap worker's smoke entrypoint changes on the pod. A2 PATH/tool preflight,
hashlocked installations, pinned plugin, tiny checkpoint, prompts, forward
options, sample count, seeds, kernels, and 900-second deadline are reused.
The complete named-module type/method/kernel/dtype/shape inventory is logged
before storage validation and retained in the smoke receipt on validation
failure. The complete report is published atomically without overwriting.

Every dense/shared linear must use the exact official FP8 method with serialized
block128 weights. A3 reloads the synthetic checkpoint, reconstructs Q/K/V and
gate/up concatenation, and compares loaded tensors byte-exactly against that
checkpoint or its official Marlin preparation on an independent scratch layer.
Packed int32 alone is insufficient: the exact Marlin operator class, mode,
geometry, workspace, packed bytes and transformed scales must all agree.
No live layer or process-global function is patched. BF16 fallback, unrecognized
packing, wrong scales and tensor tampering fail. The original expert FP8,
router, norm, embedding/head, KV, finite-forward and parser checks remain.
Qualification does not establish native H200 operator equivalence or model
accuracy. Actual model FP8 requirements are not relaxed.

## Ownership And Carry

The new root is `out/kolibri-swap-20261004/bootstrap-a3`; all three failed pod
identities are excluded. The controller retains bounded status reads, exact
retrievals, deletion verification and cleanup reserves. No automatic replacement.
Prior exact receipt sum is `0.54409303377917539333333333333` USD. Preserving
earlier upward-rounded admission carry gives
`0.5440930337791753933333333367`; A3 rounds that upward to
`0.54409303377917539333333334`. Remaining cumulative cheap allowance is
`0.70590696622082460666666666` under the original 1.25 USD cap. GPU/study caps
remain 25/75 USD, with no budget reset.

The same prospective A3 amendment covers cheap/main controllers and the local
production bridge, so qualification needs no later source amendment to admit
main. H200 creation checks the A3 cheap controller source/carry binding, exact
retrieved hashes, direct GET404, successful parser and finite-forward receipt,
and all 24 named FP8 reconstruction checks. Failed/incomplete/foreign receipts
cannot admit main. For the same freeze/path/deadline arguments the main worker
script is byte-identical to A2; the trained checkpoint and serving options do
not change.

`production.Runner` inherits the frozen judge adapter's actual exchange,
retry/stop/refusal, accounting and logical-audit methods. Only its constructor
and source checks are rebound explicitly to the A3 amendment and root; no
process globals or old sources are patched. The original judge plan remains
unchanged and is saved exactly as `JUDGE_TRANSPORT.json`. A separate journal
bridge records the A3 worker/bridge freeze, original A2 worker binding,
judge-policy hash and judge operational freeze
`444a1a181f1056e24d18ebe89f93a941810dd2e4`. That freeze must be an ancestor of
the pushed A3 freeze, with byte-identical policy/source proofs. Retry metadata
continues to cite the original judge operational freeze. All raw attempts,
unresolved reservations and the three failed cheap costs count in admission.

The fixed fixtures, first-two-screen barrier, complete screen qualification,
30%-margin whole-main forecast, reconciliation and per-call guards are reused.
Main generation remains separate from judging. `stop-server` writes only the
owned local cleanup marker after all 384 main generations (or explicit abort);
`judge-main` requires exact main retrieval and direct GET404 before dispatch.
The parent owns review, freezing, execution, the tunnel and retrieval.

## Offline Commands

```sh
python -B -m pytest -q -p no:cacheprovider tests/test_kolibri_bootstrap_a3.py
python -B -m experiments.kolibri_bootstrap_a3.adapter --build-amendment
```

The builder prints an outcome-free candidate; it does not write, freeze or
execute a plan. Tests use synthetic CPU fixtures and mocked lifecycle calls,
not a CUDA pass. No real release is created by these commands.

After parent review and a pushed A3 freeze, controller entrypoints are
`python -m experiments.kolibri_bootstrap_a3.adapter --freeze FULL_A3_SHA
--kind cheap --action launch --execute` and the same command with `--kind main`.
The latter fails before inventory/creation unless the saved A3 cheap gate passes.

The local phase entrypoint is
`python -m experiments.kolibri_bootstrap_a3.production --freeze FULL_A3_SHA
--phase PHASE --execute --reconciliation LOCAL_JSON`. Phases are `fixtures`,
`generate-screen-initial`, `judge-screen-initial`, `generate-screen`,
`judge-screen`, `main-admission`, `generate-main`, `stop-server`, then
`judge-main` after controller retrieval/deletion. Add `--port LOCAL_TUNNEL_PORT`
for generation and `--env-file PRIVATE_LOCAL_ENV` for judging. `stop-server`
needs neither argument nor reconciliation. No command automatically advances
phases or launches a pod. Offline verification uses the same module with
`--phase audit --freeze FULL_A3_SHA`, without `--execute` or credentials.
