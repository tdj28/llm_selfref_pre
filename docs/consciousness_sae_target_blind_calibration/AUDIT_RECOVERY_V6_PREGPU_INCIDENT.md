# V6 Pre-GPU Incidents and C8 Successor Review

Status: two outcome-blind stop-ships. B14 was caught before provider
provisioning. B15 was caught after one disposable C6 source/test qualification
on a B200, but before any final recovery pod was created, any recovery
authorization was issued, any attempt marker was claimed, or any scientific
output was computed or inspected. No paid v6 Pro review was submitted.

## Exact dry-run failure

After v5 was positively reviewed and adjudicated, the first non-provider line
of the intended issue path was exercised directly:

```python
from pathlib import Path
from experiments.consciousness_sae_target_blind_calibration import audit_recovery

audit_recovery.authorize._validate_plan(
    Path("data/consciousness_sae_target_blind_calibration/"
         "calibration_v2_plan_20260714_r3")
)
```

It failed closed with:

```text
AuthorizationError: bound source differs:
experiments/consciousness_sae_target_blind_calibration/requirements-runpod-b200.txt
```

The immutable r3 source inventory and v5 active tree differed in exactly two
historically bound files:

| Path | Immutable r3 bytes / SHA-256 | V5 bytes / SHA-256 | Difference |
|---|---|---|---|
| `requirements-runpod-b200.txt` | 204 / `4796c2817460bae757dcbae4c141bca460100fe80b13eb888776270d8df4b806` | 218 / `f4be59778bbe1c38ac65e4c0ae99c21d8d2ecf0c2352f48927c0840c423502a0` | added `pytest==8.4.2` |
| `setup_runpod_guest.sh` | 1,003 / `f420180faf5c229439e4bf626ec05f5e9a10902508e62dbcef36f48abc1ab8fa` | 1,026 / `71fdd22ee94898333918b8d5d2178d4e743f6415e5c2187c390701e9e03fe8b2` | added pytest version assertion |

The issue path could not legitimately pass from the v5 final commit. An older
worktree would lack the v5 Git/review chain; an edited worktree would fail the
committed-path checks; symlink substitution is forbidden. Runtime mutation is
not an acceptable substitute for exact-byte review.

## Minimum repair

This incident is tracked as B14.

1. Restore the two canonical runtime files exactly to the immutable r3 bytes.
2. Put only `pytest==8.4.2` in
   `requirements-runpod-b200-qualification.txt`.
3. Use `setup_runpod_qualification_guest.sh` only on disposable test hosts: it
   runs the canonical setup, installs the qualification-only requirement,
   checks dependencies, and asserts the pytest version.
4. Keep both qualification-only files in the source/test and provider-review
   closures, but never invoke the wrapper during final recovery.
5. Add a real pre-GPU test that validates the canonical r3 plan, derives the
   historical provenance closure, and hashes all 41 files. Its expected
   inventory SHA-256 is
   `ff02d92e681e662261b57dab00882a654eaf7b0d505dd2f210ab06f57ba8bd74`.

At issue time, the helper requires the canonical plan under the clean current
Git checkout. The authorization's already-frozen confined command separately
points execution at the exact 41-file nonimportable copy under the attempt's
`provenance_repo`; execute-time validation requires that second location and
rehashes its exact inventory. This makes the dual path roles explicit rather
than accepting an arbitrary issue-time plan path.

No canonical r3 plan, source inventory, scientific source, raw artifact,
metric, threshold, layer, prompt, dose, estimand, or claim gate changes.

## C6 qualification sequence and B15 socket-path stop-ship

The B14 repair was frozen and pushed as C6 commit
`57c4a6577309a5f112eec199d406c271df554c3a`. Its local receipt passed from
`2026-07-15T12:40:32Z` through `2026-07-15T12:40:35Z`. A distinct disposable
one-B200 qualification pod, `0bc07njrv076ba`, was created in `US-CA-2` on
network volume `bv9gb9j32y` at `2026-07-15T12:46:32Z`. Its target-free
Landlock/CUDA preflight completed at `2026-07-15T12:53:11Z`, and its exact C6
target test receipt completed at `2026-07-15T12:53:21Z` with status
`pass_exact_code_freeze_tests`. The preflight performed zero model forwards,
zero target renders, and zero target-feature reads.

That successful receipt was the third controller invocation on the same owned
qualification pod, and the preceding failures remain part of the operational
record. The first invocation used the fresh root
`/root/audit-recovery-v6-qualification-0bc07njrv076ba-57c4a6577309` but fetched
the branch with `--depth=1`. The exact source/test suite must prove that the
immutable historical review commits are ancestors of the current freeze; the
shallow checkout could not supply that history and failed closed. This
depth-1 ancestry failure was a qualification-controller failure, not a
source/test, confinement, or scientific finding.

Retry2 corrected the checkout to fetch full branch history but used the new
root
`/root/audit-recovery-v6-qualification-retry2-0bc07njrv076ba-57c4a6577309`.
That name made the qualification socket canary pathname 114 bytes, so the
pathname socket failed before it could establish the expected Landlock
`EACCES`. This was a separate qualification-root sizing failure. It did not
itself establish B15, which is the later finding that C6's distinct,
authorization-bound *production* paths were necessarily 218 and 217 bytes.

Retry3 applied both operational corrections without changing C6: it retained
the full-history checkout and used the entirely fresh short root
`/root/q6-0bc07njrv076ba-57c4a65`. That produced the successful 73-byte
qualification socket path and the five receipts below. Neither failed root was
reused or cleaned into a pass. Their complete failure archives, including
`QUALIFICATION_STATUS.json`, controller/log evidence, available partial
receipts, and verified `SHA256SUMS`, remain on the network volume at:

- `qualification_archives/v6-target-0bc07njrv076ba-57c4a65`;
- `qualification_archives/v6-target-retry2-0bc07njrv076ba-57c4a65`.

Their archive parent is
`/workspace/consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/qualification_archives`.
The successful archive
`v6-target-retry3-0bc07njrv076ba-57c4a65` is preserved alongside them. The
full-history/fresh-root correction is historical qualification-controller
evidence only; it neither repairs nor authorizes the later B15 production-path
defect.

The five C6 receipt files remain byte-for-byte historical qualification
evidence in the separate, immutable
`reviews/audit_recovery_landlock_c6_superseded_qualification/` directory; that
directory cannot be confused with or overwritten by the fresh C7 v6-input
directory. Their canonical receipt SHA-256 values are:

- local test: `cbe89a85ff57baf99b494298902b33cf75ed0aaf28b7ac349ded8767db824774`;
- target-host test: `95e97c63337d35a46d42fb32987265f986185c13c0929aabd5331d672dd7b4a0`;
- ownership: `3555d3aaa4253da2a2ef659130db727f5c18e7470b5f6e774e40c6ebcd4a557a`;
- Landlock enforcement: `a8b792cd1d80f5bd4dc3655e32374a3f5496d4919ce463b1682bcb1cee706056`;
- target-free CUDA preflight: `4781fac3a10b2ace8a518a8f0113124e08050b2bb7e27e59e39b7320272983cb`.

The exact qualification pod was deleted and direct lookup returned 404. Its
termination-audit receipt SHA-256 is
`d9bd122d39db3d4f6e47b22bd29f58021d9d05a92d3ac2103c7afb2650db9a04`;
the frozen termination and post-delete inventory receipt SHA-256 values are
`68a370fe145c4c051e7e185145fe4eb6c85f796ce294a76674e506ef9e9aba8e`
and `2da008042ab4ae624f241c099f6ffbdc8523477a3815296bf5046cca6199b1f3`.
The three corresponding termination files are pinned in the same superseded
C6 directory.
The unrelated pre-existing L40S pod was unchanged, and the network volume was
not deleted.

After those receipts were retrieved, a production-path audit exposed a second
stop-ship. Linux pathname `AF_UNIX` sockets have 108 bytes in
`sockaddr_un.sun_path`, of which at most 107 bytes are available to the
NUL-terminated pathname. C6 kept the descriptive 123-byte attempt parent and
used the 21-byte `.landlock-deny-socket` leaf. The resulting absolute socket
path was 218 bytes for `preflight/canary/output` and 217 bytes for
`landlock_canary/output`. The launcher therefore could not reach the expected
Landlock `EACCES` assertion on either production path; the kernel or Python
socket wrapper would reject the pathname first. The C6 qualification did not
detect this because its corresponding qualification socket pathname under
`/root/q6-0bc07njrv076ba-57c4a65` was only 73 bytes.

This is tracked as B15. It invalidates C6 as an execution-ready freeze but does
not invalidate its receipts as historical evidence of what that exact commit
and disposable host tested. No final recovery host, authorization, Landlock
receipt, attempt marker, compact output, model forward, or scientific result
was created before the stop.

The exact minimum repair keeps absolute pathname binding and changes only the
prospective recovery namespace and disposable socket leaf:

1. Set the on-volume attempt parent to `/workspace/csae`.
2. Set the Unix-socket canary leaf to `.s`.
3. Freeze the Linux pathname maximum at 107 bytes, require a 16-byte safety
   margin, and therefore reject any derived canary socket pathname above 91
   bytes before confinement.
4. With the fixed 48-byte attempt identifier, require the exact prospective
   production paths to measure 91 bytes for `preflight/canary/output/.s` and
   90 bytes for `landlock_canary/output/.s`.
5. Require the launcher, authorization producer, and independent offline
   verifier to enforce the same `107 - 16 = 91` byte contract, and require
   tests for producer/verifier equality and 91-byte-pass/92-byte-fail
   boundaries.

No relative socket bind, working-directory mutation, symlink alias, abstract
socket, mount, scientific input path, raw namespace, or historical evidence
path is substituted. The new attempt parent remains a clear, separate
on-volume namespace and is required to be canonical and symlink-free.

## C7 qualification-controller logging failure

The first disposable-B200 qualification of C7 commit
`4a7abd249d5bbc16e859bafb700f648de5245a50` was launched on owned pod
`t915ydw4gqfb8a` at `2026-07-15T13:53:16Z`. The full-history checkout, guest
identity preflight, qualification-only dependency setup, dependency staging,
and import-root manifest all completed. At `2026-07-15T13:57:27Z`, the
target-free Landlock/CUDA preflight failed closed before CUDA initialization or
the exact source/test suite because the SSH controller had redirected its
standard output and error directly to writable regular files. The launcher
correctly reported:

```text
landlock launcher failed: writable regular-file/directory descriptor was inherited
```

This is a qualification-controller invocation defect, not a relaxation of the
descriptor audit and not a scientific result. The regular-file standard
descriptors were deliberately rejected by an already-frozen source test. The
attempt made zero model forwards and did not render or read target prompts or
features. Its immutable failure archive remains on network volume
`bv9gb9j32y` at
`qualification_archives/v6-c7-target-t915ydw4gqfb8a-4a7abd2`. The archive's
`SHA256SUMS` verifies, and the relevant physical SHA-256 values are:

- `QUALIFICATION_STATUS.json`: `8a7b4f9750d9648d45b99f030d8f76800a26d4a1c3b6c819d58737ae392e36a2`;
- archived `remote.stdout`: `83a573b66f74ba07ee0df08b7484f5e60fd4298964b259b3e1db9c2a3142d5dc`;
- archived `remote.stderr`: `e126f6d1a54a5458002985aa70e7d4c5ed9ba8fe53f9fd41dd2b52ecb7232777`;
- controller: `49caca53952b9c00ab27536b78d2df928094dd986450074a4d66f77ae405315a`;
- `SHA256SUMS`: `2288175d16433f881a07b50bc33d0c6efef2fd7d49e0c1aaf79aa81a12dc8378`.

The minimum controller-only correction is to give the qualification child
pipe-backed standard streams and let separate `tee` processes own the regular
log files. The retry must use a wholly fresh root and archive name, retain the
failed archive, recompute the short socket pathname before setup, and run the
same unmodified fail-closed descriptor audit. Because this disclosure changes
the cumulative review packet, C7 cannot be the final reviewed freeze; fresh
local and B200 receipts must bind its C8 successor.

## Pre-review long-context reserve correction

Before the successor packet was frozen or submitted, the official GPT-5.6 Sol
model page was checked again. It states that prompts above 272K input tokens
are priced at 2x input and 1.5x output for the full request. This packet is
conservatively above that boundary. The prospective successor guard therefore
uses `$10.00` uncached input, `$12.50` cache write, and `$45.00` output per
million tokens. After the separately pinned C6 evidence was added to the
cumulative packet, the guard was frozen at 2.1 million characters, 600,000
tokens, and 5.0/2.2 Pro-work reserves. Its worst-case reserve is `$69.48`, so
the hard authorization rises from `$35.00` to `$75.00`. No paid
successor call had been made when this correction was applied.

The same check exposed two historical accounting fields that must remain
immutable but must not be repeated as corrected estimates. V4's exact preflight
was 274,606 tokens and its manifest recorded `$6.48768`; the retrospective
long-context reconstruction from stored usage is `$12.555555`. V5's exact
preflight was 336,765 tokens and its manifest recorded `$7.7812`; the
retrospective reconstruction is `$15.121205`. Both corrected reconstructions
remain below their respective `$25.00` authorizations. These are transparent
rate-schedule reconstructions, not provider invoices, and no historical file is
rewritten.

## Why the C8 cumulative review is required

V5 remains valid historical evidence for the exact packet it reviewed, but its
own exact-byte condition prevents it from authorizing either repaired
successor. C6 and its receipts remain historical B15 context and cannot be
reused as proof of the changed source/test bytes. The cumulative successor
review must receive the complete v5 review and adjudication, the exact B14 and
B15 incidents and repairs, the C6 qualification chronology, the disclosed C7
logging failure and pipe-backed retry, current
source/tests, canonical r3 source inventory, and fresh common-freeze local and
disposable-B200 receipts.

The successor gate must bind C8 code freeze, E8 reviewed packet, and F8
adjudication with `C8 <= E8 <= F8`, no source/test drift from C8 to F8, and no
reviewed-packet drift from E8 to F8. B14 and B15 must both be explicitly
dispositioned. Any genuinely new blocking finding begins at B16 and any
genuinely new important finding begins at I10. No silent retry is permitted.
