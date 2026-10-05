# Open-Weight Technical Fixture Repair A1

Status: technical repair within the owner's October 4 separate-provider
authorization. Execution requires a pushed source-bound plan and successful
fresh fixtures; this document alone is not a passed gate. The predecessor freeze was
`29ecac9ba3cd2dd59c98938203e0ba1b981e7b96`. Its technical fixture results were
seen, including route acknowledgments and synthetic judge outputs; no research
or target outcomes were generated, and no target prompts were dispatched.
Preserve its failed
[release](../../data/openrouter_swap_openweights/fixture_failure_v1_20261004/RELEASE.json),
all original receipts, and three unresolved reservations. This amendment does
not reinterpret those failed calls as successful or automatically retry them.

## Unchanged Design

Reuse the frozen [extension](../openrouter_swap_openweights/PROTOCOL.md): both
models, prompts, 12-block screens, fresh 32-block conditional mains, two judges,
instruments, parsing, thresholds, missingness, generation caps, temperature,
effort and fixed Qwen-then-Mistral main order. The family remains four primary
comparisons, separate from the completed eight-comparison family. No effect
selection, sample expansion, threshold change, or early endpoint stopping.
Architecture, training, effort, hosting and serving remain confounded.

Run all 26 technical checks anew in the A1 ledger, including both model routes
and all 24 judge/instrument fixtures. No old fixture receipt qualifies A1.
Require the unchanged complete/nonmissing OK or OK. acknowledgments, then
the journal-bound two-block-per-model technical screen audit before screen
completion. Complete both screens before qualification and whole-main budget
admission. Retain the unchanged 1.30 projection multiplier and concurrent
atomic reservations with the later model's full forecast held back.

## Exact Repairs

Opus retains its model ID, high effort and $4.40/$22 per-million ceilings but
uses only `google-vertex/us`, expected receipt provider `Google`.
The predecessor Bedrock route advertised response_format but lacked
structured_outputs and returned HTTP404. Saved public evidence must demonstrate
both capabilities for BOTH judges, plus exact endpoint and ZDR-list route
identity, integer status 0, generation limits, reasoning parameters, temperature where requested,
and prices within the frozen ceilings. A response_format-only declaration does
not qualify. Astra stays Azure US; response routes stay Together and Mistral
ZDR. Every request still requires deny-collection, ZDR, no fallbacks, required
parameters, default tier and bounded prices. No catalog is fetched by A1 code.

Only the exact frozen Mistral configuration uses the accounting adapter.
Prompt, completion, reasoning and total counts must all be present nonnegative
integers. Missing/unknown/negative/nonfinite usage fails closed. If reasoning
exceeds completion, or total differs from prompt plus completion, declare a
discrepancy and bound output by max(completion + reasoning, total - prompt).
This intentionally overcounts when the provider's fields overlap. Otherwise
use completion as before. Charge the larger of reported billing and the token
price bound; never discount cached input. The observed 20/57/59/77 receipt with
reported $0.0004575 therefore has a conservative $0.000900 bound. No such
exception is allowed for other providers or model/route/price identities.

The raw response is never modified. The unchanged ledger stores its exact
decoded JSON and canonical digest. An explicit detached audit projection
validates the original identity, usage and cost first, then changes only its
in-memory completion/total accounting fields for the common auditor. Audit
output discloses original counts, original digest, discrepancy and computed
bound for each Mistral receipt. The projection is never saved as a raw receipt.
For exact Mistral only, reserve the common input/output bound plus another
max_tokens times output price: one full output cap for each reported component.
At 4,096 tokens the added padding is $0.03072. This is a prospective reserve,
not a reported bill or an added settled charge. Atomic ledger caps and later
model holdbacks use this actual padded reserve. Audit validates the original
reserve and privacy fields first, then projects only the detached reservation
to the common auditor's unpadded request formula. It discloses the padding
separately, including for unresolved calls. Raw receipts remain unchanged.
All other providers keep the common reservation. Missing usage, identity
failure and transport error retain the full actual reservation; genuinely
unexpected over-reservation still blocks subsequent dispatch. There is no
exception to privacy or secret rejection.

## Carry And Evidence

The prior API panel cost bound is $84.08770746; failed fixtures add $0.5550459,
including all three unresolved reservations. Cumulative prior cost is at least
$84.64275336. Reconciliation must include public ID
`openweights-v1-through-failure`, that whole cost or a larger bound, and failure
RELEASE SHA256
`76b68ccfb92c779c39d10df0523311434f65ec2fb68cede2d557b064a119777e`.
Do not also include the same earlier costs in another row. All other external
completion commitments remain explicit, including an explicit empty list.
Working/hard caps must be supplied and may not exceed the $200 OpenRouter
ceiling. The failed fixture cost remains inside the original $25 fixture/screen
allowance, so A1's allowance is at most $24.4449541. Do not borrow RunPod funds.

Endpoint evidence has the old spec/privacy/timestamp fields plus a `catalog`
record matching the saved ENDPOINTS format: checked_at_utc, url, endpoint,
zdr_catalog_url, zdr_endpoint. Its catalog_sha256 is the SHA256 of canonical
JSON for that record. Both endpoint records must pass capability validation.
Public snapshots and approval/reconciliation IDs are attestations, not
independently authenticated provider promises. Parent supplies refreshed
snapshots; this preparation makes no network or account calls.

## Entrypoints And Release

`experiments.openrouter_swap_openweights_a1.production` retains the explicit
finalize/launch/approval/reconciliation/source-hash/pushed-Git gates. The new
plan location is `data/openrouter_swap_openweights_a1/plan_v1/PLAN.json`; the
single canonical ledger is `out/openrouter-openweights-a1-v1` under the shared
Git root. The old ledger is never reopened, reset, migrated or settled by A1.
All original frozen source hashes and the predecessor release hash are checked.
No credential is loaded until launch gates pass. Decoded response keys/values
are recursively checked against the actual credential before receipt storage.

The A1 production/release entrypoints are narrow namespace copies where frozen
module-level plan/runner bindings prevent reuse. Shared ledger, provider,
instruments, qualification, inference and execution methods remain unmodified;
there is no process-global monkeypatch. Original frozen CLIs should be run in
their original clean freeze checkout because their broad source glob also sees
new extension tests in this checkout.

`experiments.openrouter_swap_openweights_a1.release` keeps the strict sorted
list manifest, explicit inventory, root public scanner, decoded JSON scans,
immutable raw gzip bytes, offline reconstruction and rehashed-tamper rejection.
It reports conservative costs and unresolved reserves, the bound failure
release, fixed family, qualification and admission. Parent owns publication
of the predecessor failure and any future A1 freeze/launch.

Offline check: `python -B -m pytest -q -p no:cacheprovider tests/test_openrouter_openweights_a1*.py`.
Synthetic tests establish implementation behavior only, not live technical
qualification or permission to collect research outcomes.
