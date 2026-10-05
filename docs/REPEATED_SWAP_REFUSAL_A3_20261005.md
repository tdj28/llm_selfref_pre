# Repeated-Answer Refusal Handling A3

A2 stopped when an Astra structured judgment returned a provider filter
refusal. The request specified `service_tier="default"`; the receipt instead
said `service_tier="auto"`. The frozen parser checks the service tier before
the finish reason, so it raised `ReceiptError("Non-default service tier
receipt")` before handling `content_filter` as a missing judgment.

The affected slot is
`judge:repeated-swap-v1-20261004-main-gemini-07-final-SH-draw-3:astra:structured:a0`.
Its model and provider match Astra/Azure, its finish and native finish reasons
are `content_filter`, and all top-level usage counts and reported cost are zero.
The ledger nevertheless retains the full $0.48147 reservation because the
receipt failed validation. This amendment neither settles that reservation
nor treats the response as a valid default-tier result.

The owner authorizes continuing the remaining planned inventory without
retrying this refusal or bypassing the filter. Models, routes, requests,
endpoints, labels, missingness analysis, the $130 cap and the $45 external
holdback do not change.

## Narrow Rule

A3 recognizes a main-panel judge receipt as terminal missing only when it has
the expected model/provider, a nonempty receipt ID, assistant text, an explicit
`content_filter` or `refusal` finish reason, `auto` service tier, zero integer
usage counts, zero reported charge and no other receipt/accounting error.
Its stored state must be an unresolved `ReceiptError` retaining exactly its
original reservation. Nonzero usage, identity mismatch, a successful answer
with `auto` tier, malformed accounting, pending calls and other errors still
halt. Ordinary valid refusals under the original parser remain missing as
before.

The rule applies prospectively to the same narrowly defined refusal receipts.
Such a receipt is never retried, including when it arrives on an A2 transport
retry. The refusal is not an answer label or a negative experience label.
Unrelated planned judgments continue. Refusals are excluded from transient
transport-failure counters and do not reset exhaustion streaks. All existing
A2 transport retry limits and systematic-stop rules remain in force.

## Evidence And Freeze

The preserved A2 freeze is `a08e271caf2a633426882cbd9705f95bfe653e3b`.
The stopped journal contains 1,260 physical calls and 2,521 events in
14,537,377 bytes, SHA-256
`eaac1ee5b6798077c4fe18052697f989b9d832798af704f0f5a628640bf8a0c9`.
Every byte remains unchanged. The original transport failure and its successful
A2 retry also remain; the successful label is reused, not requested again.

The new plan inherits A2's source inventory and adds only this document,
the adapter and its tests. Commit and push it before any additional call.
Raw retry metadata keeps its actual A2 or A3 operational freeze. A detached
policy view checks those epochs against the frozen prefix before using the
unchanged A2 counter logic. It never normalizes raw service tiers, converts
refusals into settled calls, or changes recorded charges.

The full physical journal remains the accounting record. The logical view
retains refused slots as missing and reports their IDs and reserved amounts.
The completion forecast does not count failure reservations as completed work.
`refusal_a3/runtime.json` and per-launch records bind the actual adapter freeze,
funding snapshots and journal boundaries. Finishing the planned inventory
does not mean all labels are present or all charges are reconciled.

Build locally with `python -m experiments.repeat_refusal_a3 --build`.
The plan is `data/repeated_swap/refusal_a3_20261005/PLAN.json`. After commit
and push, execution adds `--freeze FULL_SHA --execute`, with `--env-file` only
if needed. Default/build commands make no provider calls. The release adapter
uses `RefusalRunner`, `LogicalView` and `policy_state` from this module while
retaining the previous A1/A2 records and physical journal.
