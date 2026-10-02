# B1 Provisioning Retry

This is an operational amendment, not a new scientific design or a result.
The owner authorized another provisioning attempt on October 2 after the first
RunPod POST returned HTTP 500. Account balance was not established as the cause.

The first exact name was
`codex-bilingual-llama-b1-20261002-cheap-e08cbdeb733f`, requested at
2026-10-02 18:41:20.202067 UTC. Its immutable creation-intent receipt is
`78d564cdc7c772619e2c40807570a2e6690275c285038b7aad9745993d18111e`.
Repeated paginated inventory checks, including after its 19:11 UTC deadline,
found no exact match. No pod ID, worker dispatch, GPU test or Llama target
outcome was obtained. Absence from inventory is not a verified deletion or
proof of zero billing. The original ledger and failed request are preserved.

## Unchanged Experiment

- Scientific runtime remains at
  `c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb`; plan SHA-256 remains
  `1f06e45c703b11f6d7c02535529fa69112bcfa640886a230550c689e1b1b3886`.
- Same 20 blocks, 760 generation calls, Llama checkpoint, native precision,
  prompts, seeds, temperatures, translation checks, judges and endpoints.
- The inherited 128 fixture judgments remain unchanged. No repeat calibration,
  new paid review, local judge ledger reset or outcome-dependent selection.
- Same cheap CUDA worker, source-bound main worker, first-row and first-two-block
  audits, measured-throughput gate, local judge halt and retrieval/deletion rules.

## Retry and Accounting

The separate controller uses namespace `bilingual-pod-retry-b1` inside the
existing ignored output root. It permits one new cheap POST. A main POST is
allowed only after that cheap pod passes, all evidence is retrieved and hashed,
and deletion is verified by GET 404. An ambiguous retry POST is reconciled by
exact name, never followed by another automatic POST.

The $200 pilot ceiling and its $45 GPU / $125 judging / $15 translation and
storage / $15 contingency allocation do not increase. Reserve **$8 of the GPU
allowance** for the original ambiguous attempt. This is a conservative planning
reservation, not an asserted charge. At its quoted $0.84/hour including storage,
the reservation covers 9.52 hours from the original request. Before each rental,
the original elapsed time plus the entire future GPU lifetimes and an extra
retrieval reserve must fit that window. The live controller checks it again
before worker dispatch, barrier approval and during monitoring. If original
cleanup is later verified, use its recorded cost for that horizon test but
retain the full $8 reservation in the retry budget.

At the original quotes the full reservation is
`8 + 0.84 * 0.5 + 6.89 * 5 = $42.87`, below $45. Actual current quotes must pass
the same complete-lifetime calculation before POST. Main accounting carries
$8 plus the cheap pod's own verified cost exactly once. No reserve is borrowed
from judging or contingency.

Each inventory observation filters only the original exact name. If it appears,
new work stops and any retry pod is retrieved and deleted. Only the original
persisted intent, fresh-name/time checks and blocked-ID registry can authorize
reconciliation and cleanup of the old pod. It is never reused for inference.
Other pods are not inspected by SSH or mutated. A second unresolved creation,
unverifiable ownership, failing tests, or insufficient remaining budget stops
progress with evidence preserved.

This policy limits a possible delayed charge but cannot guarantee a cloud bill
when the provider has not supplied a pod ID. Persistent invisible provisioning
would require provider/account reconciliation; no local script can certify its
absence. Cleanup retries can exceed a nominal deadline and must be reported.

## Execution Binding

Run the separately committed controller using `runpy.run_path` from the unchanged
scientific checkout. Both its own source hashes/public CI and the old scientific
plan/public CI must verify before rental. The approval receipt binds
`owner-20261002-runpod-retry`, the original $200 allocation, plan and science
freeze; the creation ledger also binds the full operational amendment.
Lifecycle receipts remain ignored because they contain account inventory and
SSH provisioning material. Publish a sanitized status and verified artifacts,
not the private controller ledger. Keep the original HTTP 500 in the record.
