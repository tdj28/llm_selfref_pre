# Signed-dose audit-only recovery successor reproduction map

This map reproduces the C1 qualification incident and the C2→E2→F2 successor
without raw outcomes. Run from the repository root.

## C2: local closure and repair

Verify the incident artifacts with the independent implementation:

```bash
PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_signed_dose_scan.verify_qualification_incident \
  --incident-dir \
  docs/consciousness_sae_signed_dose_scan/audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up \
  --recovery-cycle-ledger \
  docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER_V2.json
```

Run the bounded recovery suite, including the deterministic regular-file
ancestor reproduction and the raw-containment, strict-existing, and symlink
negative controls:

```bash
python3 -m pytest -q \
  tests/consciousness_sae_signed_dose_scan/test_qualification_incident.py \
  tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py \
  tests/consciousness_sae_signed_dose_scan/test_recovery_host_qualification.py \
  tests/consciousness_sae_signed_dose_scan/test_audit_recovery.py
```

C2 must be pushed as a direct single-parent child of
`f1307fc56d9d8fbd0625bf30524e6eea16575326` with the exact status map in the
successor amendment. Do not include the untracked Pro templates or dirty blog
files in C2.

## E2: one replacement host qualification

Create one fresh B200 pod and fresh `audit_recovery_host_qualification_v2`
namespace. Use protocol v2, global qualification ordinal 2, successor attempt
1, no raw argument, 1,800 seconds / $3, and no retry. Reject both prior pod IDs.
The attempt must run the real pinned 0–78 J checkpoint, required 45–78 subset,
missing-layer negative, frozen-auditor CUDA startup, and one tiny raw BF16
matmul while model-forward and target-render counts remain zero.

Always terminate the exact qualification pod and freeze teardown before E2.
E2 is a direct child of C2 adding exactly the eight files enumerated in the
amendment. A failed qualification is terminal; do not create E2 or try again.

## F2: one cumulative review

After a passing E2, materialize the brief/context in
`audit_recovery_pro_review_v2/` with C2/E2 hashes and statuses. Disclose the
original review, original audit incident, consumed C1 qualification, capture
gaps, narrow ENOTDIR repair, V2 authority, and passing E2. Send only the compact
outcome-free packet to `gpt-5.6-sol`, once, capped at $1.25. F2 is a direct
child of E2 adding exactly the eight review artifacts. Any unresolved blocker
or verdict other than `READY TO FREEZE` stops.

## One recovery

Only after live-remote F2 validation may one fresh, distinct recovery pod use
the immutable remote raw run for the zero-forward audit. Never commit or copy
raw tensors/rows to the laptop. Publish only the fresh atomic three-file compact
directory. On success or failure, freeze evidence, terminate the exact owned
pod, and stop; there is no retry.
