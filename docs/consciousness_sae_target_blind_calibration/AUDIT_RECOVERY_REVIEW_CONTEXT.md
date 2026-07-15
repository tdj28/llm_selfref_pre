# Bounded Context for the Calibration r3 Audit Recovery Review

This packet contains no scientific result values. The raw tensors and JSONL
rows remain only on the RunPod network volume and are not reviewer inputs.

## Observed lifecycle

- Original freeze commit: `1a165725cad3484c646de8420846545a6a8beb8b`.
- Owned execution pod: `597yeluoak40i7`, one NVIDIA B200, `US-CA-2`, network
  volume `bv9gb9j32y`.
- Model transaction: one invocation, exit zero, 256 model forwards, atomically
  finalized, 35 manifested files and 323,365,550 manifested bytes.
- Target prompt renders: zero. Target feature vectors: zero. Analysis outcome
  inputs: empty.
- First audit: one invocation, no compact output published, stopped at the
  pinned J-checkpoint inventory predicate.
- Original pod: receipt-owned termination completed; post-delete account pod
  inventory was empty. The network volume and raw transaction were retained.

## Exact failure

The failure log ended with:

```text
File ".../audit.py", line 1119, in _load_j_checkpoint
    raise CalibrationAuditError("J-lens map inventory differs")
CalibrationAuditError: J-lens map inventory differs
```

Physical failure-log SHA-256:
`a5936d0fda01b96f193a1ab40c9d7c52dc751ecdf3686896e26d2d3951cdd86f`.

## First recovery-host infrastructure block

The first fresh audit-only recovery host was staged from commit `e0dd9a6`, but
the audit entry point was never invoked. Before the exclusive attempt marker
was created, the host proved that its root user lacked `CAP_SYS_ADMIN` in both
the effective and bounding sets. The exact raw-tree `mount --bind` operation
failed with return code 32, and both `unshare -m` and `unshare -Urnm` failed
with return code 1. The host ran Linux `6.8.0-111-generic`; its Landlock ABI
query returned 4. No marker, failure receipt, or compact directory existed.

The preserved external pre-execution receipt has canonical SHA-256
`bf8ddbb31b3ddab99c2126d1100691f8d0878c1a0d1d4a091776e5d3f2bc207d`.
The exact pod was then deleted, direct lookup returned 404, and the account
pod inventory returned to empty. This is an infrastructure block, not a
scientific attempt, and its expired authorization will not be reused.

## Incomplete Landlock review and accepted redesign

The exact first Landlock packet received one synchronous `gpt-5.6-sol` Pro
review. Response `resp_076355ae1eba8bf5016a570d939bcc819ba1a5412f83532777`
ended `incomplete/max_output_tokens` and `NOT READY TO FREEZE`. It returned four
visible blockers: missing compact scientific-equivalence evidence; a post-
Landlock child restart that allowed `site` before guards; overwriting original
campaign-field semantics with recovery timing; and an exact `0..78` whitelist
that contradicted literal required-subset prose. All four are accepted in the
prospective redesign. Aggregate usage reconstructed to $2.44009 against a
$1.80 estimate; the budget incident and prohibition on a silent replacement
call are preserved. This context is not itself authority for another paid
review.

The outcome-blind scientific-equivalence appendix extracts and hash-binds the
transitively called 49-function frozen scientific closure, protocol/orientation
semantics, exact recovery adapter surface, and an affirmative output-field
projection. Its synthetic tests require old/recovery map selection and
projected scientific fields to remain identical. Its inherited-design manifest
records eight fixed `prompt_id` units, three directions by five repeated doses,
prompt-level bootstrap, frozen estimands/gates/missingness/stopping, and no
prompt-population generalization. The J artifact's `n_prompts=125` is fitting
metadata, not the study sample size.

## Completed v2 and v3 reviews and bounded final repair

After the scientific metadata correction and full source/test packet were
frozen, one explicitly authorized synchronous `gpt-5.6-sol` Pro review
completed as response
`resp_08bf88c21348bec0016a5722977908819a8f86ea3d61725704`. It ended `NOT READY
TO FREEZE`, used 823,115 input and 30,179 output tokens, and reconstructed to
$5.020945 within its $17 authorization. Its exact review and structured
`NOT_READY_TO_EXECUTE` adjudication are retained as context for the replacement
review authorized by the user.

For the now-historical v3 packet, including this negative review and the exact
local/target qualification receipts, the user explicitly authorized a bounded
increase: producer and verifier used one $25 preflight ceiling with a
1.2-million-character/400,000-estimated-token input guard and the same
20,000-output-token request cap. Expected spend is lower, and there is no
silent retry.

That review found four concrete blockers. B06 identified Torch-dependent loader
tests that skipped on macOS and still expected recovery inventory fields in the
downstream J metadata record. B07 identified a fail-open substring check under
which `NOT READY TO FREEZE` contained `READY TO FREEZE`. B08 identified that the
plan required exact local and target-host test receipts but the authorization
and verifier could not bind them. B09 identified a $17 producer versus $10
offline-verifier completed-review cost ceiling. The bounded repair keeps the
loader unchanged, makes verdict parsing exact, adds two canonical
authorization-bound code-freeze test receipts, and aligns the cost boundary.
No scientific outcome was opened and no GPU scientific audit was launched.

The separately authorized v3 call then completed as response
`resp_0c08617bb82fc5ce016a5748c627d881989e5fffdd49f658cf` and ended `NOT
READY TO FREEZE`. It used 1,051,523 aggregate input tokens and 28,895 output
tokens (10,935 reasoning), reconstructing to $6.124465 within the $25
authorization. Its exact provider files and canonical adjudication are retained
under `reviews/audit_recovery_landlock_gpt_pro_v3_completed_negative/` as
immutable historical evidence. B10 found that the supplied qualification timing
missed the then-frozen one-hour recovery envelope; B11 found that one paragraph
labeled “The precise claim” omitted the otherwise disclosed `/proc/self/task`
exception. The replacement v4 review must disposition both findings against the
exact repaired bytes. The v3 call is one historical paid call; it is not the
future v4 approval call and cannot be relabeled as such.

## Prospective Landlock replacement

The material redesign must be reviewed before authorization. The exact plan,
launcher, direct bootstrap, verifier, and focused tests in this packet define
the full contract. In brief: a single-threaded absolute-path launcher starts as
`python -B -E -s -S`, rejects inherited writable/protected descriptors and
unsafe mappings, installs the ABI-4 `0x7ff2` Landlock policy before project or
ML imports, and same-PID execs a no-site bootstrap. Two exact output
directories get only `0x1b2`; one exact `/proc/self/task` rule gets only
`WRITE_FILE|TRUNCATE` (`0x4002`) on all procfs descendants beneath that task
root, required for CUDA thread-name `comm` writes; each
identity-bound NVIDIA character device gets only `WRITE_FILE`; no broader
`/proc` or device-directory rule exists. An external manifest binds and
rehashes every approved import-root byte and ordered `sys.path` entry. The
launcher requires and the preflight receipt records `LANG=C` and `LC_ALL=C`,
avoiding locale-dependent inherited shared gconv mappings.

Both the pre-authorization probe and real launcher exercise independent
protected/output canaries. The confined probe imports pinned dependencies and
performs raw BF16 CUDA arithmetic and synchronization while model loaders and
`torch.nn.Module` calls are guarded; it renders no prompt and performs zero
model forwards. The raw and historical-provenance inventories are rehashed at
both endpoints before compact success publication.

The claim is deliberately narrow. ABI 4 does not mediate metadata-only
operations, already-open descriptors, sibling processes, other NFS clients,
or NVIDIA driver `ioctl`. The evidence supports process-tree confinement of
handled filesystem content/topology writes with both disclosed exception
classes: exact `/proc/self/task` `WRITE_FILE|TRUNCATE` access and exact
inode/`rdev`-bound NVIDIA character-device `WRITE_FILE` access. It also supports
equality of frozen byte/path inventories at the pre/post endpoints—not a
read-only mount or continuous external immutability claim. Upstream caveats:
<https://docs.kernel.org/6.8/userspace-api/landlock.html>.

## Frozen runtime predicate

The model runtime loaded the same hash-pinned checkpoint and required the
study maps as a subset:

```python
raw_maps = _validate_j_lens_checkpoint_metadata(checkpoint)
available = {int(layer) for layer in raw_maps}
if not set(protocol.J_LAYERS) <= available:
    raise V2RuntimeError("jlens_layers", "a required J map is missing")
```

It then iterated only over `protocol.J_LAYERS`.

## Frozen audit predicate

The failed auditor used an exact-equality predicate:

```python
maps = checkpoint["J"]
available = {int(layer) for layer in maps}
if available != set(protocol.J_LAYERS):
    raise CalibrationAuditError("J-lens map inventory differs")
```

`protocol.J_LAYERS` is 45 through 78. The pinned release checkpoint contains
maps 0 through 78. Its frozen physical SHA-256 is
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`;
metadata are `n_prompts=125` and `d_model=8192`. The extra 0-through-44 maps
are never selected by the study.

## Review boundary

The proposed correction must be rejected if it changes anything beyond
checkpoint-inventory compatibility, audit-host provenance, recovery timing,
or transparent disclosure. In particular, it may not change or select based
on prompts, directions, doses, raw rows, layers used by calculations,
thresholds, metrics, bootstrap logic, claim gates, or observed values.

The reviewer should assess:

1. whether required-subset semantics are the correct narrow correction for a
   physically hash-pinned superset checkpoint;
2. whether original execution provenance and fresh audit-compute provenance
   are independently and adequately bound;
3. whether the recovery code can alter any scientific calculation beyond the
   loader predicate;
4. whether the failed attempt and post-run recovery remain unambiguously
   disclosed in the final receipts;
5. whether a fresh model run is necessary despite the target-independent,
   pre-publication audit bug; and
6. any concrete stop-ship flaw that must be fixed before audit execution;
7. whether the ABI-4 Landlock launcher, `0x7ff2` handled mask, two exact
   `0x1b2` output rules, the exact `/proc/self/task` path-beneath `0x4002`
   exception required for CUDA thread naming, independent pre-authorization and real-launch
   two-canary tests, exact inode/`rdev`-bound NVIDIA device exceptions,
   confined dependency imports and BF16 CUDA check, inherited-FD checks, and
   pre/post rehashes support the narrower stated process-tree
   filesystem-write-confinement claim;
8. whether the unhandled device-`ioctl` boundary and zero-model-forward status
   are stated and evidenced precisely enough; and
9. whether any remaining gap requires a fresh model transaction rather than
   stopping only the audit-only recovery.
