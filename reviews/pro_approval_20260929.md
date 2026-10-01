# Pro Review Authorization

On 2026-09-29 the owner replied, "i approve get it done", to the explicit
request for two GPT-6 Astra Pro-mode reviews at up to $3 per call, $6 total,
with no automatic retries. This note records that conversational approval;
it is an operator attestation, not an independent signature.

The publication milestone is the focused response to Berg et al. The first
call reviews the complete manuscript and bibliography at companion commit
`ad54256c3e7c997d24e46442b2364c69f610ae3e` for scientific integrity, inference
and references. The second reviews the scientifically corrected draft for
zero-context expert readability. The calls are separately authorized within
that two-call scope. No retry, continuation or substitute provider is covered.

Both use `gpt-6-astra`, `reasoning.mode=pro`, medium effort, with 6,000 requested
output tokens and the helper's default aggregate-usage reserves. Before the
first call, its complete-packet conservative estimate was about $2.51. These
are preflight spending guards, not provider-enforced billing caps. Record the
exact counted estimates and returned usage in each actual review manifest.

The [official latest-model guide](https://developers.openai.com/api/docs/guides/latest-model)
and [pricing](https://developers.openai.com/api/docs/pricing) were rechecked on
2026-09-29. Standard short-context input/cache-write/output rates are
$10/$12.50/$50 per million tokens. Both packets are far below the 272K-input
long-context boundary. No background storage or tools are requested.

New paid-review spend at authorization was $0. Partial historical review
receipts sum to $116.747125; that is not the full project or account total.
See `pro_review_status.md` for the unreconciled-cost limitation and updates.

The manuscript and references are public. Only those contents and review
instructions are submitted. Keys are loaded privately by the shared helper;
an environment-file path in an invocation does not submit its contents.
