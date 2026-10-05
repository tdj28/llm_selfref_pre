# Repeated-Answer Transport Amendment A2

The owner explicitly authorized up to two additional identical requests after
a transient judge transport failure, including the existing failed Astra call.
This supersedes the earlier no-retry instruction. It does not change the
scientific panel, prompts, settings, endpoints, judges, codebooks or analysis.
The $130 cumulative study cap, A1 funding guard and $45 external holdback remain.

A1 stopped with 443 physical calls: 442 settled and one unresolved. The cost
including its full reservation was $11.40252755. The journal was 4,775,467 bytes,
SHA-256 `2f09ba9b8a7ac4176897550194ab127a0523eca4ad898f5a96cb359adc01be88`.
The failed call was Astra's structured judgment of Gemini block 3, SH, draw 2.
Its only retained transport information was HTTP status 200. The frozen sender
discarded the response body, so the underlying cause cannot be recovered or
called a proven transient provider outage.

## Retry Rule

Only main-panel judge `TransportError` receipts with unknown charges qualify.
Eligible status codes are absent/0, 200, 408, 425, 429 and 5xx. Authentication,
request, identity, usage, accounting, budget and observed integrity failures
stop execution. Generation calls are never retried. The old sender can wrap
body-decoding or body-validation failures as `TransportError(200)`; A2 cannot
distinguish those hidden causes. This limitation is disclosed, not repaired by
guessing what the missing body contained.

The original request gets at most two further physical attempts, after 2 and
5 seconds. Their request bodies are identical, and their IDs end in
`:transport-a2-r1` and `:transport-a2-r2`. Each reserves its full upper-bound
charge before dispatch. Earlier failures and their unknown charges remain in
the journal permanently. A completed answer, valid label, refusal or capped
output is not retried by this rule. The original, separately specified single
judge schema retry remains unchanged; transport and schema attempts have
different IDs and are reported separately.

After three transport failures for one logical request, its label stays
missing and collection proceeds. The 17th physical judge transport failure
(including the original failure) stops new dispatches. Three consecutive
exhausted logical judge requests on one model/provider endpoint also stop new
dispatches. Endpoint streaks follow durable settlement order: a completed
judge transport resets the streak; intermediate failed attempts do not end a
logical request. Both instruments share the endpoint counter. A stop latches
even if another in-flight success later arrives. Already dispatched calls
settle and remain charged; concurrency can therefore add failures after the
stop threshold. Restarting does not reset counters. A pending attempt without
a settlement requires reconciliation, not an automatic retry.

## Accounting And Evidence

The original scientific freeze is `b3ddbdcae9919937ffb67da565b26ec2d0c81f00`;
the A1 operational freeze is `ce07d52a1fed2ec530b6e31c8670c8f3fb8597bb`.
Those files, the original failed admission and both journal prefixes stay
unchanged. A2 inherits A1's full source inventory and adds only this document,
its wrapper and tests. Its fresh plan is frozen and pushed before dispatch.
`transport_a2/runtime.json` and launch records identify the actual new
operational freeze separately from the original scientific request metadata.

For analysis, a read-only logical view selects the completed retry receipt or
leaves the exhausted request missing. It never edits raw data. The audit
includes every logical-to-physical mapping, the physical failure count and the
full physical spending total. Existing planned-denominator missingness bounds
remain unchanged. The startup completion forecast subtracts only settled
logical work from remaining work. Failed attempts and additional physical
charges consume funds without making that forecast shrink; each launch saves
this distinction in `completion_forecast.json`. The release adapter must use `LogicalView`,
`RetryRunner.rows`, `RetryRunner.audit` and `policy_state`, retaining both the
physical journal and this projection. The old release builder alone does not
understand physical retry IDs.

Build offline with `python -m experiments.repeat_transport_a2 --build`.
The plan is `data/repeated_swap/transport_a2_20261005/PLAN.json`. After the
parent commits and pushes, `--freeze FULL_SHA` verifies locally; parent-only
execution adds `--execute` and optionally `--env-file`. Default/build commands
make no provider calls. No outcomes select this operational repair.
