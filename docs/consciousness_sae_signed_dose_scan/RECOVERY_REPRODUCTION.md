# Signed-dose audit-only recovery reproduction map

The first complete 70B transaction finalized its raw tree, but its independent
auditor stopped before compact publication because the pinned J-lens contains
the canonical layer superset 0–78 while this study requires 45–78. The terminal
attempt record and the only permitted mechanical repair are frozen in
`AUDIT_ONLY_RECOVERY_AMENDMENT_20260717.md`. The original raw directory is
immutable and remains remote-only.

Recovery artifacts are deliberately separated by role:

- C commits recovery code, tests, and the outcome-blind incident closure.
- E adds one directory named `audit_recovery_qualification_<id>/` containing
  exactly the eight qualification/equivalence/teardown receipts.
- F adds only the cumulative Pro review and its adjudication.
- Remote recovery attempts use
  `consciousness_sae_signed_dose_scan/consciousness_sae_signed_dose_scan_v1/audit_recovery/`,
  never the original `raw/` or `compact/` namespace.

`recovery_equivalence.py` and `verify_recovery_equivalence.py` construct the
outcome-blind C-bound packet. `recovery_host_qualification.py` and its
independent verifier perform the one-shot, zero-forward B200 gate. Only after
the pushed C→E→F ancestry and all receipts validate may `audit_recovery.py`
issue and execute one fresh authorization. The recovery rehashes every raw
file before and after the audit, rejects model construction/loading/forward
paths, and atomically publishes only the three compact audit files. A failure
is retained and consumes the attempt; there is no automatic retry.
