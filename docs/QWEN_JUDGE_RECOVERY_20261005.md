# Qwen Missing-Judgment Recovery

This is an authorized, post-hoc scoring repair, not a new generation study or
a claim that the original collection completed. The published release at
`ad49e88f9cd4235670686ddcd5933ff9b98eb3be` remains unchanged and incomplete.
Its 256 Qwen answers and all completed judgments are retained verbatim.

Exactly three Astra structured judgments are eligible:

- `openweights-main-qwen-02-final-HS`: HTTP-200 transport failure.
- `openweights-main-qwen-02-final-NS`: HTTP-200 transport failure.
- `openweights-main-qwen-04-final-SH`: settled receipt with an incomplete
  response and `finish_reason="error"`, not a refusal.

Selection uses recorded technical failure and missing-label status, not the
model answer or a preferred label. The response texts and exact original
request bodies, including the rubric, model, provider, reasoning setting,
output limit and privacy settings, do not change. No generation calls,
additional fixtures, other judges or other missing items are authorized.

## Attempts And Budget

Each eligible logical judgment may receive at most two new physical attempts,
after 2 and 5 seconds. Each has a unique `:recovery-r1` or `:recovery-r2` ID
in a new locked sidecar ledger. A second attempt requires a transient
`TransportError` or another incomplete error-finish response. Transient status
codes are absent/0, 200, 408, 425, 429 and 5xx. The original sender discarded
the bodies of the two HTTP-200 failures, so their underlying causes remain
unknown. HTTP status 200 is not proof of a provider outage.

Completed labels are never redone. Refusals, capped responses, other incomplete
responses and completed but invalid-schema responses are retained as missing
without another call. Identity, accounting, authentication, pending-attempt
or budget failures stop dispatch. Restarting reuses receipts; it does not reset
attempt counts, replace completed judgments or erase charges.

All new attempts together have a hard $2 cap within the original $200 API
scope. The preceding cumulative bound is $125.75920446, including $0.965228
reserved for the original unresolved transports. Those reservations are not
known provider charges and remain in the original bound. The new ledger adds
its costs once. A path with repeated failures may hit $2 before all six
possible attempts; the cap is not a guarantee of recovery.

Before execution, the coordinating process supplies a confirmed funding
snapshot at most ten minutes old. It reserves the entire $2 sidecar, at least
$45 for Kolibri, the remaining repeated-study commitment, and any other
account obligations. The repeated-study holdback must include pending and
unresolved charges not known to have been debited. The snapshot also carries
the original-scope prior costs and other commitments; their sum plus $2 must
fit under $200. Concurrent controllers must retain these allocations. This
small sidecar consumes the confirmed allocation; it does not independently
discover other controllers' commitments or query their credentials.

Required preflight fields are `confirmed`, `as_of_utc`, `account_balance_usd`,
`scope_prior_bound_usd`, `scope_other_commitments_usd`, `kolibri_holdback_usd`,
`repeated_remaining_holdback_usd`, `other_account_holdback_usd`, and
`evidence_sha256`. The evidence hash identifies the coordinating process's
reconciliation. The preflight is saved with the launch. No private correspondence
or credentials belong in this file.

## Freeze And Reporting

The new protocol, tests, executable and source-bound plan must be committed and
pushed before calls. The plan inherits the unchanged original dependency
inventory and binds the exact release manifest, failed receipts and requests.
The release manifest SHA-256 is
`24b97a49f40965a8002440442e6843016d64d0fde9e5204cbb90b0014cd7f041`.

Build without network calls using `python -m experiments.qwen_judge_recovery
--build`. The plan is `data/qwen_judge_recovery/plan_v1_20261005/PLAN.json`.
After freezing and pushing, execution uses `--freeze FULL_SHA --execute
--preflight PATH`, optionally with `--env-file PATH`. The default only verifies
local evidence. Live artifacts go to the canonical ignored directory
`out/qwen-judge-recovery-20261005/`, not the published release.

An additive report links each logical judgment to every new physical attempt.
New rows fill only the three eligible missing structured-label slots. The old
analysis remains public; the recovered analysis uses the same four-comparison
family, planned panel, estimands and missing-label rules. Label recovery does
not retroactively reconcile the two old unknown charges or change any frozen
completion flag. Report this as post-hoc measurement repair, preserving both
the original incomplete results and the repaired sensitivity analysis.
