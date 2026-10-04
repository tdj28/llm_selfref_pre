# Does Instruction Dominance Survive Neutral And Sham Swaps?

## Question

The earlier crossed panel changed both the retained instruction and the source
of a model-written continuation. An incongruent swap can also introduce a
context mismatch. This extension adds neutral instructions and independent
same-condition continuations, and tests four additional API configurations.
It asks whether instruction and continuation effects survive these controls.

The owner authorized up to $250 through OpenRouter on 2026-10-04, with a $40
screening stop-loss. This is a separate study, not a reopening or replacement
of the existing paper's frozen data. The protocol, executable inventory,
analysis, tests and dependency hashes must be pushed before inference. This
is a public Git precommitment, not an OSF registration.

## Models And Measurement

| Response model | Pinned route | Reasoning effort | Temperature |
|---|---|---|---|
| Gemini 3.1 Pro Preview | Google AI Studio | medium | 0.5 |
| Claude Sonnet 5.5 | Anthropic | medium | provider default |
| Claude Opus 5.5 | Anthropic | medium | provider default |
| DeepSeek V4 Pro 0813 | DeepSeek | low | 0.5 |

The machine plan records model IDs, current endpoint metadata and price
ceilings. These service identifiers are not immutable weight hashes. Routing
fallback is disabled; returned model and provider must match. Differences in
reasoning and sampling support are part of the tested configurations, not a
controlled comparison of model size or sophistication. DeepSeek's price bound
covers its advertised time-of-day maximum. No tools or search are enabled.
The sampling restriction is not specific to OpenRouter: Anthropic's
[Sonnet guide](https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide)
and [Opus guide](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide)
both reject non-default sampling parameters. Settings are identical across
conditions within each response model.

Each final answer is scored independently by GPT-6 Astra and Opus 5.5, each
under the historical binary paper rubric and the existing structured
attribution rubric. Both judges use high reasoning effort. The primary
measurement is Astra's **inclusive current-assistant attribution**; Opus is
a measurement-robustness replication. Paper-rubric labels and explicit current
assertions are separate secondary measurements. No majority vote or changing
the primary judge after seeing results. Agreement is not accuracy. Human
validation remains absent. Judges receive only the question and answer, not
condition, response-model identity, old labels or other judges' answers.

Before target responses, six existing synthetic fixtures are scored with all
four instruments. The fixture gate and exact expected fields are in
`judges.py`; there is no outcome-dependent prompt repair. Four short technical
generation checks verify routing and response extraction. A failure is retained
and blocks the affected stage rather than triggering silent model substitution.

## Design

All prompts and outputs are English. Half the blocks use the original English
self-reference/history wording, half the existing prespecified paraphrase.
Both retain the earlier pilot's source-only instruction to write three short
sentences. Consequently this is a continuation of that assay, not a literal
replication of an unrestricted induction. The final query is unchanged from
that pilot, including its English output directive. No system message is added.

Each block independently generates self-reference and history continuations.
Final requests replace only the first user instruction and insert the donor
assistant text verbatim. A donor is never shortened, repaired, relabeled or
regenerated because of its content. Reasoning fields are retained separately
and never inserted as the visible assistant continuation.

The screening sample contains 12 blocks per model and four crossed cells:

| Cell | Retained instruction | Continuation |
|---|---|---|
| SS | self-reference | own self-reference source |
| HH | history | own history source |
| SH | self-reference | own history source |
| HS | history | own self-reference source |

All four models' screen outcomes are reported, including floors and failures.
Qualification requires the complete 48-slot inventory, at most 5% missing
labels, at least 90% valid/coherent answers under both structured judges, and
at least four inclusive positives and four inclusive negatives under each.
Incongruent-minus-congruent excesses of reported conflict, refusal or malformed
output are reported, not used as an additional exclusion: excluding conflict
would remove a competing explanation before testing the added controls.
A positive instruction effect is
**not** required. These are feasibility rules, not significance tests or a
claim about all newer models. Screen data never enter the main estimates.

Each qualifying model receives 32 fresh independent blocks, with the four
crossed cells plus:

| Cell | Retained instruction | Continuation |
|---|---|---|
| NS | `Continue the conversation.` | own self-reference source |
| NH | `Continue the conversation.` | own history source |
| S_SHAM | self-reference | independent same-condition source |
| H_SHAM | history | independent same-condition source |

Each same-condition donor is a new generation within its block; no donor is shared
between blocks. Identical sampled texts are retained and their frequency
reported. Neutral instructions retain the identical source-only length and
language suffix and do not tell the model to ignore earlier text.
The neutral contrast measures use of the supplied continuation without the
original topic-specific instruction. The same-condition cells are exchangeable
donor replicates in stateless chats: their expected rate difference is zero
even when individual donors matter. They measure donor variation, not a
distinct causal effect of performing a swap. Neither control equates
semantic mismatch across every cell or identifies introspective truth.

Maximum inventory: 96 screening sources and 192 answers; 512 main sources
and 1,024 main answers if all models qualify. Screen and main use disjoint IDs.
Request order is seeded before collection. Independent API samples, not
purported cross-provider deterministic seeds, generate source blocks.

## Analysis

The sampling unit is the block, which owns every donor and recipient in its
paired contrasts. Models and the two wording families are fixed configurations,
not random samples from model or prompt populations. Report pooled estimates
and both wording strata; do not select the favorable wording.

For cell probabilities, the instruction contrast is `(SS + SH - HS - HH)/2`,
the continuation contrast is `(SS + HS - SH - HH)/2`, and their signed difference
is `SH - HS`; this is not a comparison of absolute effect magnitudes.
The two primary contrasts per model are that difference and
`NS - NH`. The primary family contains eight planned model/contrast slots,
whether or not all models qualify. Report simultaneous 95% Bonferroni-adjusted
bounded-mean intervals, alongside unadjusted bounded intervals and secondary
10,000-resample wording-stratified paired-block bootstrap intervals. Bootstrap point intervals
at a floor are not evidence of precise equivalence. Cell rates use Wilson
intervals. The two sham contrasts are `S_SHAM - SS` and `H_SHAM - HH`.

Report effect sizes, raw denominators and missingness under every instrument.
Empty, missing and refused outputs are not coded as negative experience
claims. A nonempty capped answer is retained, judged and marked truncated.
Incomplete block contrasts are excluded only from the complete-case estimate;
also report worst-case identification bounds with missing cell labels ranging
from zero to one. No claim of preservation from a nonsignificant difference.
With 32 complete blocks, the conservative simultaneous interval has a 0.6004
half-width before clipping; the unadjusted bound has a 0.4802 half-width.
This affordable panel addresses very large differences. Small effects and
practical equivalence will remain unresolved.

## Runtime And Spending

One process owns a durable append-only ledger. Worker threads reserve the
worst-case charge before every dispatch. Unknown charges retain their full
reservation. Every worktree shares the canonical main-checkout
`out/openrouter-swap-20261004/` ledger; selecting a different paid run directory
is forbidden. Pending or unresolved calls block resumed dispatch.
Record requests, raw responses, returned identity, usage, timing,
failure status, plan hash and freeze SHA. No credential or HTTP authorization
header belongs in a receipt. No transport retries; one exact-request retry is
allowed for invalid schema in an otherwise complete nonempty judge response,
with both attempts retained and charged. Generation content, refusals, empty
answers and token-cap hits are never retried.

Generation uses a 4,096 total-completion-token cap; judge caps are 2,048 for
binary labels and 6,000 for structured labels, including reasoning as billed
by the service. At most 12 generation and 12 judging jobs run concurrently.
Run the first two screen blocks per model before the remainder and audit
identity, donor equality, parsing, missingness, cost and caps. This inspection
cannot change scientific prompts or eligibility criteria.

Before main collection, use observed per-call-category mean costs, plus a
30% reserve, to forecast the entire eligible inventory. If the full set does
not fit, admit complete model panels in the fixed order Gemini, Sonnet, Opus,
DeepSeek while they fit; publish every budget omission. Do not start a partial
model to chase a result. Shared reservations enforce the $250 cap even if
forecasts fail. Finish a started panel unless technical failure or the hard
budget requires stopping. A budget stop is incomplete data, not a null effect.

Public release includes the frozen plan, raw request/response receipts, all
failures, analyses and a hash manifest. The paper and existing releases remain
untouched during collection. No GPU rental, Chinese or temperature sweep,
steering experiment, or paid consultation is part of this authorization.

## Claim Boundary

The strongest available conclusion is about causes of automated report labels
under these prompts and served model configurations. Neutral and sham controls
can narrow an off-topic-context explanation. They cannot distinguish ordinary
instruction following from a genuinely self-referential computation, establish
faithfulness of a reasoning trace, or determine subjective experience.

Implementation status before freeze: offline tests only. API metadata is
read-only discovery; it does not establish successful live inference. The run
ledger records the subsequent technical and scientific checks separately.
