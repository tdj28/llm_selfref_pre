# V6 Pre-GPU Authorization-Gate Incident

Status: outcome-blind stop-ship caught before provider provisioning. No new
B200 was created, no recovery authorization was issued, no attempt marker was
claimed, and no scientific output was computed or inspected.

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

## Pre-review long-context reserve correction

Before the v6 packet was frozen or submitted, the official GPT-5.6 Sol model
page was checked again. It states that prompts above 272K input tokens are
priced at 2x input and 1.5x output for the full request. This packet is
conservatively above that boundary. The prospective v6 guard therefore uses
`$10.00` uncached input, `$12.50` cache write, and `$45.00` output per million
tokens and raises the hard authorization from `$35.00` to `$65.00`. At the
frozen 1.9-million-character/550,000-token ceilings and 5.0/2.2 Pro-work
reserves, the maximum estimated reserve remains below `$65.00`. No paid v6
call had been made when this correction was applied.

The same check exposed two historical accounting fields that must remain
immutable but must not be repeated as corrected estimates. V4's exact preflight
was 274,606 tokens and its manifest recorded `$6.48768`; the retrospective
long-context reconstruction from stored usage is `$12.555555`. V5's exact
preflight was 336,765 tokens and its manifest recorded `$7.7812`; the
retrospective reconstruction is `$15.121205`. Both corrected reconstructions
remain below their respective `$25.00` authorizations. These are transparent
rate-schedule reconstructions, not provider invoices, and no historical file is
rewritten.

## Why v6 review is required

V5 remains valid historical evidence for the exact packet it reviewed, but its
own exact-byte condition prevents it from authorizing these repaired bytes.
V6 must receive the complete v5 review and adjudication as context, the exact
B14 failure and repair, current source/tests, canonical r3 source inventory,
and fresh common-freeze local and disposable-B200 receipts. The successor gate
must bind C6 code freeze, E6 reviewed packet, and F6 adjudication with no
source/test drift from C6 to F6 and no packet drift from E6 to F6.
