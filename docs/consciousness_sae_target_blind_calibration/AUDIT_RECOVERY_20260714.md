# Calibration v2 r3 Audit-Only Recovery

Status: prospective technical-recovery plan, frozen before any recovered audit
output is computed or inspected. This is not a new model run and cannot change
the r3 estimand, prompt panel, directions, doses, layers, thresholds, or claim
policy.

## Why recovery is necessary

The r3 model transaction completed atomically as
`calv2-r3-1a16572-20260715T002344Z`. Its `RUN_COMPLETE.json` has canonical
receipt SHA-256
`bab48b452c7e7c5b9db5d09ecc34c7e530813e2f5093aff1b8a8152017e4695d`
and physical SHA-256
`d60e25d13d1b9e30a52114aa954a6c1306ef8e15a8dddd53af1de58c4dcb9fee`.
The 35 manifested raw files total 323,365,550 bytes; with the completion
receipt, the remote ledger contains exactly 36 files. The external raw-ledger
file has physical SHA-256
`7bffb6306b67814d2f4618b6aaf4f243ab2992d7b6b92ebb955a370654e0a20c`.
No target prompt or target feature was used, and no prior outcome row was an
analysis input.

The first independent audit stopped before publication with
`CalibrationAuditError: J-lens map inventory differs`. The failure log has
physical SHA-256
`a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f`.
No compact audit or summary was published.

The cause is a target-independent compatibility predicate. The authentic,
hash-pinned checkpoint contains maps for source layers 0 through 78. The study
requires and uses only layers 45 through 78. The frozen runtime correctly
accepts the checkpoint when the required set is a subset of the available set;
the frozen auditor incorrectly requires the two sets to be equal. The pinned
checkpoint SHA-256 remains
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.

## Exact correction

The immutable r3 plan and its bound `audit.py` remain unchanged. A separate
recovery entry point makes exactly one scientific-compatibility correction:
the J-checkpoint inventory predicate specified below. Its other adaptations
are operational only: fresh audit-host watchdog/publication authority, an
isolated historical-source validator, and a byte-equivalent audit-only tensor
hasher needed to keep the old model runtime out of the executable package.
None may weaken original run-timing checks or touch a scientific calculation.
The corrected loader must:

1. rehash the checkpoint against the frozen SHA-256;
2. verify `n_prompts == 125` and `d_model == 8192`;
3. require every study layer 45 through 78;
4. record the complete available layer inventory and the unused extras;
5. reject a missing required layer;
6. expose only the same maps to the unchanged downstream audit calculations.

The authentic available inventory is 0 through 78. Extra maps are ignored by
the frozen orientation and transport loops. No metric, threshold, aggregation,
bootstrap, layer role, row inclusion rule, or claim gate may change.

## Dual provenance and authorization

The recovered audit must validate two independent chains:

- The original ownership, guest, cache, authorization, execution binding,
  raw manifest, and completion receipt establish provenance of the r3 model
  transaction.
- A fresh receipt-owned one-B200 guest in `US-CA-2` on network volume
  `bv9gb9j32y`, plus fresh guest/cache receipts, establishes provenance of the
  audit-only computation.

Before execution, an audit-recovery authorization must bind:

- this plan's physical hash;
- the committed recovery source and tests;
- the clean local, tracking, and live remote Git commit;
- the bounded Pro review evidence and its adjudication;
- the original run ID, raw namespace, completion receipt hashes, 36-file
  ledger hash, failed-audit-log hash, and original receipt chain;
- the fresh audit host's ownership, guest, and cache receipt hashes;
- a short audit-only deadline and conservative spend ceiling; and
- an exact 30-minute, $3.00 audit-only ceiling at the frozen conservative
  $6.00/hour rate, starting from the fresh audit host's provider creation
  time; and
- zero model forwards, zero target renders, zero target feature vectors, and
  an empty *external-or-prior* outcome-input list for the fresh audit host.

The old execution authorization is historical provenance, not authority for
the fresh pod. The new authorization cannot permit a model forward. The
recovery must begin and publish inside its new audit-only budget. The expired
or superseded r3 operational clock remains historical execution provenance and
is never presented as authority for the fresh host. The recovery entry point
may replace the original operational watchdog with the new receipt-bound
watchdog, but may not alter the original run-timing validation or any
scientific calculation. A missed recovery window stops recovery rather than
changing a clock or deadline.

Zero-forward status is enforced at four levels: the fresh guest receipt must
begin at zero; the recovery entry point must install a process-local guard that
raises on any `torch.nn.Module` call and on the base Transformers model-loader
families; forbidden runner/runtime modules are denied by an import guard; and
the exact executable package must contain no 70B model construction or runner
entry point. The original source bytes required to validate the historical
authorization are present only in a separately inventoried, kernel-read-only,
non-importable provenance tree. They are never on `PYTHONPATH`. The only audit
dependency formerly imported from the model runtime is `tensor_sha256`; it is
supplied by a small audit-only shim whose outputs are mechanically compared to
the frozen implementation across dtypes and non-contiguous tensors. The
recovery receipt records that all guards fired zero times. Tokenizer loading,
safetensor reads, direct tensor arithmetic, and loading only
final-normalization/LM-head weights remain allowed.

The authorization binds one commit-scoped attempt ID, the exact provenance
root, model/J paths, compact output names, attempt marker, failure receipt, and
a canonical command hash. Execution atomically creates the attempt marker with
`O_EXCL`; its continued existence makes the authorization non-reusable. No
second output directory or retry can be selected inside the same authority.

## Execution and stopping rules

The recovery audit is read-only with respect to the raw transaction and the
historical source provenance. Before metric computation both trees are
bind-mounted over their canonical paths as read-only mounts. Mountinfo must
prove their mount IDs, parents, filesystem devices, sources, roots, and exact
volume-subtree provenance; failure to establish either kernel-enforced state is
a stop condition. It then rehashes the complete raw tree against both
`RUN_COMPLETE.json` and the externally preserved 36-file ledger and runs
the unchanged r3 prompt, tensor, arithmetic, orientation, final-norm/LM-head,
transport, bootstrap, gate, and summary logic. It does not construct the 70B
model and performs no model forward.

After all metrics are computed but before any success publication, the full raw
tree and historical provenance tree are rehashed again against their frozen
inventories. Only then may compact output be atomically published to the one
authorization-bound fresh recovery directory. The
audit and summary must disclose the correction identity, old failure-log hash,
old and new receipt chains, recovery source/plan/review hashes, full available
J inventory, required inventory, and unused extras. The raw tree is rehashed
again after audit and must be unchanged.

Stop without retry or *success* publication if:

- any raw byte or manifest entry differs;
- any required J map is missing;
- the pinned J artifact or metadata differs;
- the proposed correction reaches beyond the inventory predicate;
- either receipt chain fails;
- any target/outcome input or model forward is introduced;
- the source/review/Git closure differs; or
- either audit deadline or spend ceiling is crossed.

The fresh receipt-owned pod is terminated after compact evidence is retrieved
or after any failure. The 900 GB network volume is never deleted.
Every catchable failure after the one-shot marker is claimed writes an
exclusive canonical operational failure receipt containing the attempt,
authorization, command, source, error, and compact-publication state. The
external stderr log, pod receipt chain, and termination proof are also
preserved; failure cannot create or relabel a compact scientific success
bundle. An uncatchable process or host loss still leaves the exclusive marker
and external provider/log evidence and cannot be retried under that authority.

The r3 raw outputs are the primary subject of this audit and therefore are not
misdescribed as forbidden "outcome inputs." The forbidden set is external or
prior scientific outcomes used to adapt, select, pool, or judge this recovery;
that set remains exactly empty.

## Review disclosure

One budget-authorized latest-model Pro review was requested for this bounded
plan and structural context. The provider returned
`status=incomplete`/`max_output_tokens`; it did not review the later executable
source or tests and must not be described as having approved the recovery.
Its visible response agreed that required-subset semantics are technically
justified and that a fresh model execution is not required solely for this
target-independent predicate bug, but returned `NOT READY TO FREEZE` on the
plan-only packet. Its visible blockers are handled by the minimal executable
closure plus non-importable provenance compartment, zero-forward/import guards,
kernel read-only raw and provenance mounts, final prepublication rehashes,
exact ownership-bound 30-minute/$3 ceiling, one-shot attempt marker, external
failure receipt, and corrected external/prior-outcome wording above. The
executable source and focused tests receive local mechanical and independent
review before authorization. No second paid provider call is implied or
claimed.

## Claim boundary

A successful result is an explicitly disclosed post-run technical recovery of
the prospectively frozen r3 raw collection. It is not described as the
original same-pod r3 audit. Scientific claims remain unavailable until the
corrected audit publishes and its compact receipts pass independent validation.
If recovery fails for any data-, metric-, or required-map reason, a separately
frozen fresh model execution is required.
