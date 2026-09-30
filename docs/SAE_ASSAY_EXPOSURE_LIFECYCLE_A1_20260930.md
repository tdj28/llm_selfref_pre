# Exposure Startup Amendment A1

This amendment changes process inspection and cost carry-forward, not the
scientific design. It follows a failed startup under public freeze
`1d7ec700ac1a91f133ac851d5e179aa8dcfa803e`. The original 53 source hashes and
plan `52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9`
remain unchanged. No exposure or precision-pilot outcome was generated.

## Observed Failure

The initial B200 pod, `6sr9s4hprynal1`, started at 21:21:06 UTC. Its first
snapshot attempt could not inspect an unrelated protected RunPod service's
`/proc` environment. The original global process scan raised `PermissionError`;
three monitoring retries were followed by cleanup retries with the same error.
The setup log and receipts contain no scientific row, residual capture,
pretrained-model load record or completed CUDA qualification.

The operator then verified the exact dispatch markers and process/session
identity of worker group 604, retained the existing late-dispatch fence,
stopped only that group, and established that the group was empty. All four
output artifacts were retrieved and hash-verified before deletion. DELETE
returned 204, direct GET returned 404, and the account inventory was empty at
21:25:19 UTC. The recovery did not claim to inspect protected foreign
environments. The original failed monitor and its receipts remain unchanged.

The raw failure bundle is
`data/sae_assay_exposure/startup_failure_20260930/`. A failure is not a zero
activation result or a failed scientific exposure gate.

## Narrow Repair

Use a separately source-bound lifecycle controller. For a known worker PID,
validate the leader's exact ownership markers, process group and session,
then use process-state/group information to establish pause or termination.
Do not require access to an unrelated service's private environment merely
to snapshot our own worker. Preserve missing-PID reconciliation, the shared
launch/cleanup lock and permanent late-launch fence. Never signal an
unverified or foreign process group. Failures of owned-leader verification
or owned-group quiescence still block a claimed safe snapshot.

Before replacement creation, test protected-foreign-process handling,
inaccessible or wrongly marked owned leaders, missing-PID recovery, late
dispatch fencing, lock-descriptor release, retrieval integrity and deletion.
The real Linux subprocess test and hosted public checks must pass. This is
engineering verification, not independent scientific review.

Run the original worker at the amendment's public execution commit with the
same original plan. Its loader must still verify all 53 original source
hashes. The separate A1 manifest binds the new lifecycle source, this
amendment and the original plan. No change to texts, IDs, selection, readout,
precision bridge, pilot inventory, thresholds or analysis is authorized.
Inspect CUDA qualification and the first five rows before bulk approval.

## Same Spending Ceiling

The failed startup cost is bounded by
`0.4864956272222222222222222222` USD. Prior cumulative diagnostic spending is
now bounded by `28.12156495135375832222222222` USD. The remaining portion of
the same $25 follow-up allowance is
`24.51350437277777777777777778` USD, not a second $25 authorization. The
overall diagnostic ceiling remains $200. A1 lifecycle accounting and the
final release must include the failed startup.

The unchanged worker's internal $25 guard is looser than the amended local
controller's remaining allowance; the latter controls provisioning, monitoring
and deletion and is authoritative for this replacement attempt. Its full
two-hour compute-plus-storage estimate must fit the remaining allowance
before creation. Only a newly created, uniquely named owned pod may be used.
Retrieve and verify every artifact before termination; no response generation,
judge calls, extra Pro review or automatic repeated experiment is added.
