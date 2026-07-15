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

## Completed v2-v6 reviews; B14--B16 and the C10/v7 successor

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
exception. The v3 call is one historical paid call and cannot be relabeled as
approval.

The separately authorized v4 call completed as provider response
`resp_03da5e4ad00bb281016a575ff36b1881998a04bc71e3a8c066` and ended `NOT
READY TO FREEZE`. It used 1,129,614 input tokens and 27,987 output tokens,
including 8,904 reasoning tokens. Its immutable manifest reconstructed
`$6.48768` under short-context rates. Its 274,606-token exact preflight crossed
the 272K threshold; the retrospective long-context reconstruction is
`$12.555555`, still within the `$25.00` authorization. Neither value is an
account invoice. Its exact review, request artifacts,
provider response, manifest, and canonical `NOT READY TO EXECUTE` adjudication
are preserved under
`reviews/audit_recovery_landlock_gpt_pro_v4_completed_negative/`. No recovered
outcome was computed or inspected, and no model transaction, model forward,
target prompt render, or target feature extraction occurred.

V4 resolved B10 and B11. Its sole new blocker, B12, is an exact-byte evidence
closure defect: `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` was outside both
the provider-review packet and the source/test receipt closure, even though
later authorization and recovery metadata would bind its then-current bytes.
The supplied tests established generator agreement only when they ran; neither
the receipts nor the post-review packet Git-diff gate protected the omitted
machine JSON. The minimum repair is to add that existing generated JSON to the
packet and lineage gate, update the inclusion test, regenerate both affected
source/test receipts, and obtain a successor exact-byte review. It changes no
scientific calculation, confinement rule, or model-execution requirement.

The now-historical v5 packet included the exact machine JSON and the full v4
negative review, manifest, machine adjudication, and human-readable
adjudication. The immutable v4 bindings retain the archived request and
response hashes without recursively embedding the prior 1.2 MB request packet.
B12 retains its stable ID. Any new blocker begins at B13, and any new important
non-blocking finding begins at I09; prior findings may not disappear through
renumbering. Producer and verifier retain the exact `$25.00` review ceiling.
Its input/output envelope was 1,450,000 characters, 450,000
estimated input tokens, and 20,000 requested output tokens, with frozen 5.0
input and 2.2 output reserve multipliers. Both the static
3.5-characters-per-token estimate and an exact tokenizer preflight must pass
before submission. Expected spend is lower, and no silent retry is permitted.

V5 subsequently completed as response
`resp_0322d12a79eb8aa5016a576d65fc94819ba2ed3994c7f8cbf0` with terminal
verdict `READY TO FREEZE`. It used 1,379,762 input and 29,413 output tokens,
including 7,256 reasoning tokens. Its immutable manifest reconstructed
`$7.7812` under short-context rates. Its 336,765-token exact preflight crossed
the 272K threshold; the retrospective long-context reconstruction is
`$15.121205`, still within the `$25.00` authorization. Neither value is an
account invoice. The complete
review and structured `READY_TO_EXECUTE` adjudication are supplied to v6 as
bounded context. V5 is preserved as a valid review of its own exact bytes, not
as approval of the repaired successor packet.

The post-review authentic dry-run then exposed B14 before any new GPU was
provisioned: v5 had added `pytest==8.4.2` to two files that the immutable r3
plan binds byte-for-byte. The first real authorization statement rejected
`requirements-runpod-b200.txt`; the setup script had the same collision. The
canonical r3 files are restored exactly, while pytest moves to two separately
bound qualification-only files. An unmocked regression test now runs the real
plan/provenance gate and requires all 41 historical files and their exact
inventory hash.

That repair was pushed as C6 commit
`57c4a6577309a5f112eec199d406c271df554c3a`. Its local receipt passed, and
disposable B200 pod `0bc07njrv076ba` then passed the target-free Landlock/CUDA
preflight and exact C6 target tests on `bv9gb9j32y`, but only after two
preserved controller failures. The first qualification checkout used
`--depth=1` and could not prove the historical-review ancestry required by the
exact test suite. That depth-1 ancestry failure was controller-only. Retry2
fetched full history, but its longer fresh root made
the qualification socket pathname 114 bytes and failed before the expected
Landlock `EACCES`. Retry3 retained the full history and used the entirely fresh
short root `/root/q6-0bc07njrv076ba-57c4a65`, producing the successful 73-byte
qualification path. The two failed roots were not reused; their complete
status/log/partial-receipt/SHA256SUMS archives remain under the network
volume's `qualification_archives/` directory as
`v6-target-0bc07njrv076ba-57c4a65` and
`v6-target-retry2-0bc07njrv076ba-57c4a65`. These are controller failures,
separate from the later B15 production defect.

The pod was deleted and verified absent without mutating the unrelated L40S
pod or deleting the network volume. The successful five C6 receipts and
termination chain are pinned under the separate
`reviews/audit_recovery_landlock_c6_superseded_qualification/` directory, so
fresh C9 inputs cannot overwrite them. Those files, both failed archives, and
the successful archive remain historical qualification evidence; the probe
rendered no target and performed no model forward.

Only after that evidence was retrieved did a production-path audit expose
B15. C6's absolute `.landlock-deny-socket` pathname was 218 bytes in the
preflight canary and 217 bytes in the final canary, above Linux's 107-byte
pathname `AF_UNIX` maximum. The qualification path was only 73 bytes, so its
pass did not exercise the production length. The exact repair uses
`/workspace/csae` as the canonical attempt parent and `.s` as the socket leaf,
freezes a 16-byte margin below 107 bytes, and rejects any derived socket path
above 91 bytes. The resulting production preflight and final paths are exactly
91 and 90 bytes. Producer, launcher, verifier, and boundary tests must agree.
No relative bind, symlink alias, abstract socket, or scientific path changes.

Because B15 changes source/test bytes, C6 cannot authorize execution. C7's
first live successor qualification then failed closed before CUDA or tests:
direct regular-file stdout/stderr redirection was inherited and the unchanged
descriptor audit correctly rejected it. The verified failure archive remains
on the network volume. The retry uses pipe-backed standard streams so separate
`tee` processes own the regular logs; the controller is qualification-only and
never part of final recovery. The packet pins the exact controller/wrapper and
five selected C7 failure-archive artifacts. C8 disclosed this history and
produced a superseded local-only receipt, but never received target-host
qualification or paid review because a final packet audit caught stale lineage
in this context and the main plan.

C9 commit `b404491fe4bd28931e45bed16fb5d7d9a27382f5` then received fresh local
and disposable-B200 qualification. Receipt-owned pod `t915ydw4gqfb8a` passed
the target-free CUDA/Landlock preflight and all 216 target tests, recording
zero model forwards, Torch module calls, target renders, and target-feature
reads. E9 added the five fresh receipts to the cumulative packet. The exact
C9 qualification pod was deleted after evidence retrieval, without deleting
network volume `bv9gb9j32y`; it cannot be reused for the successor.

The cumulative v6 `gpt-5.6-sol` review then completed as response
`resp_096bfc4229fd22e6016a57992e0f648199913ca0849879a9a3` with terminal
verdict `READY TO FREEZE`. It reviewed the C9/E9 packet, preserved the complete
v5 context, explicitly accepted the B14 and B15 repairs, and identified no new
B16-or-later blocker or I10-or-later important finding. It used 2,029,613
input tokens and 31,829 output tokens and reconstructed to `$21.728435` under
the stored conservative schedule, below its `$75.00` authorization. These are
manifested usage and a conservative reconstruction, not an account invoice.

That positive v6 review is immutable historical evidence but cannot authorize
execution. Its checklist included the negated sentence `No B05 is invented`.
The v6/current-review gate extracted ID-shaped tokens throughout the response,
so it counted that prose mention as a recycled B05 finding and correctly
refused adjudication. This B16 incident is documented in
`AUDIT_RECOVERY_V7_POSTREVIEW_INCIDENT.md`. No recovery authorization,
recovery attempt, scientific calculation, target read, or model forward
followed the v6 review.

The smallest repair is v6/current-only ATX finding-heading extraction:
stable IDs are findings only when an ATX heading begins with `Bnn` or `Inn`;
negated prose and checklist mentions are not findings. Historical v2--v5
parsing remains unchanged. Because the parser and its regressions change
source/test bytes, C9 qualification and the v6 review cannot be relabeled as
evidence for the successor. C10 freezes the repair; fresh local and
disposable-B200 qualifications bind C10; E10 adds their receipts; the final
cumulative v7 call reviews exact E10 bytes and includes the complete v6 review
as context; and F10 adds only the v7 provider output and structured
adjudication. The current lineage is `C10 <= E10 <= F10`, with no source/test
drift from C10 to F10 and no reviewed-packet drift from E10 to F10. B14--B16
must all be explicitly dispositioned, and no silent retry is permitted.

The official GPT-5.6 Sol model page prices prompts above 272K input tokens at
2x input and 1.5x output for the full request. The final v7 successor packet is
conservatively above that threshold, so its prospective reserve uses `$10.00`
uncached input, `$12.50` cache write, and `$45.00` output per million tokens,
with the frozen 2.1-million-character/600,000-token ceilings, 5.0/2.2
aggregate-work multipliers, a `$69.48` worst-case reserve, and a `$75.00` hard
authorization. The
immutable v4/v5 cost fields remain their historical manifests' own
reconstructions; they are not reused as the v7 rate schedule or asserted to be
account invoices. The machine gate preserves both original fields and both
retrospective reconstructions. A fresh exact preflight must still prove that
the expanded v7 packet, including v6 review context, fits the frozen guard
before the separately authorized call is submitted.

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

For both production canaries, the launcher continues to bind an absolute
filesystem socket pathname. The attempt namespace is `/workspace/csae`, the
socket leaf is `.s`, and the independently enforced pathname budget is 91
bytes: Linux's 107-byte maximum less a frozen 16-byte reserve. The fixed
preflight and final candidates are 91 and 90 bytes respectively. An overlong
candidate is a pre-confinement stop, not evidence of Landlock denial.

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
