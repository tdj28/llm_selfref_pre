# Audit-only recovery successor amendment — 2026-07-17

This amendment closes the consumed C1 host-qualification attempt and authorizes
one bounded successor cycle. It does not amend the signed-dose scientific
contract, inspect an outcome, authorize a model forward, or make the original
audit pass retroactively.

## What happened

C1 commit `f1307fc56d9d8fbd0625bf30524e6eea16575326` was pushed, and one
fresh US-CA-2 B200 pod (`69d9kxugxuf6up`) began the one-shot qualification.
The irreversible marker was written at `2026-07-17T03:22:06.571209Z`; the
qualification failed about one second later with the serialized error
`RecoveryHostQualificationError: opened path is missing`.

The attempt had no raw input argument, opened or recomputed no raw run, rendered
no target prompt, ran no model forward, and produced no compact result. Its
`raw_forbidden_attempt_count=2` is two false-positive guard increments, not
evidence of raw access. The exact triggering pathname, exact errno, and full
traceback were transient and were not preserved. The causal statement is
therefore limited to the deterministically reproducible bug class: the C1 path
guard treated an optional child probe below a regular-file component as a
missing/forbidden path.

The only guard repair tolerates an `ENOTDIR` result for `must_exist=false`
after the existing ancestors have been `lstat`-checked and no symlink was
encountered, then returns the lexical path for the raw-containment test.
Lexically raw-contained probes, `must_exist=true`, and symlink aliases still
fail. C2 also introduces the required fresh cycle/protocol identities,
ordinals, rejected-pod set, namespaces, and incident diagnostics; it does not
change the target-platform qualification gates or any scientific field.

All retained evidence is under
`audit_recovery_qualification_incident_f1307fc_69d9kxugxuf6up/`. The canonical
closure receipt is
`10a5838638ab3950981ea91532204c2ae28a67505e72fc3f5bf7bf534cdf79d1`;
its independent verification receipt is
`f8202d34728205e9e90f961c6ce28e830f287c392d4f27a2ad3b64645dd74dd6`.
The pod was deleted exactly, direct lookup returned 404, account inventory
returned to empty, and no unrelated pod changed. Its frozen conservative
compute estimate is `$1.075906519416666666666666667`.

## Frozen successor authority

`RECOVERY_CYCLE_LEDGER_V2.json` freezes receipt
`534531c3825a5d91521b417ba92482845ed663f86d66a18ddaa9f5a31fd9c787`.
The user's explicit successor authorization permits exactly:

1. one completed local incident-closure pass;
2. one C2 code/evidence freeze directly descended from C1;
3. one replacement B200 qualification (global ordinal 2, successor attempt 1);
4. one compact cumulative Pro review after passing E2; and
5. one zero-forward audit-only recovery after passing F2.

There are zero automatic, provider-capacity, qualification, review, or recovery
retries. Any failed gate consumes its attempt and stops. Pods
`wl8obvtuq0ax8t` and `69d9kxugxuf6up`, all old authority, and every old output
namespace are rejected. The recovery pod must be fresh and distinct from the
replacement-qualification pod.

The successor deadline is `2026-07-17T12:00:00Z`; the old `08:00:00Z` deadline
remains C1-only. Caps remain 1,800 seconds / $3 for qualification, $1.25 for
the single review, and 3,600 seconds / $6 for recovery, plus a $1.75
non-execution reserve. Conservative accounting uses the frozen predecessor
estimate of $19.60—not an invoice—plus the receipt-backed failed-pod estimate
of $1.075906519416666666666666667. The subtotal is
$20.675906519416666666666666667; the $12 successor envelope yields a
worst-case $32.675906519416666666666666667 under the user's $50 ceiling.

## Exact freeze chain

C1→C2 is a direct single-parent transition. The normative status map is:

- `M`: `audit_recovery.py`, `recovery_host_qualification.py`,
  `verify_recovery_host_qualification.py`, `recovery_equivalence.py`,
  `verify_recovery_equivalence.py`, and their three existing tests;
- `A`: `qualification_incident.py`, `verify_qualification_incident.py`,
  `test_qualification_incident.py`; this amendment, the V2 ledger and successor
  reproduction map; and all 18 files in the qualification-incident directory.

Paths above are relative to the experiment/test/docs study directories as
applicable. No other tracked path may differ from C1 in C2. User-authored dirty
blog files and the top-level review templates are excluded.

C2→E2 must add exactly these eight files under
`audit_recovery_host_qualification_v2/`: `RECOVERY_EQUIVALENCE_PACKET.json`,
`RECOVERY_EQUIVALENCE_VERIFICATION.json`, `ATTEMPT_STARTED.json`,
`TARGET_HOST_QUALIFICATION.json`, `TARGET_HOST_QUALIFICATION_VERIFICATION.json`,
`QUALIFICATION_TERMINATION_AUDIT.json`, `QUALIFICATION_FROZEN_TERMINATION.json`,
and `QUALIFICATION_POSTDELETE_INVENTORY.json`.

E2→F2 must add exactly eight files under `audit_recovery_pro_review_v2/`:
the brief, context, request Markdown, request payload, response JSON, rendered
review, manifest, and adjudication named by the runtime contract. The packet
must be cumulative over the original Pro disposition, the C1 qualification
failure, the C2 repair, and passing E2. It contains no raw data or outcome.

Only live-remote F2 with every gate green may authorize the one recovery. Any
red gate, review blocker, missed deadline, failed recovery, or lineage/status
deviation means preserve evidence, terminate the exact owned pod, and stop.
