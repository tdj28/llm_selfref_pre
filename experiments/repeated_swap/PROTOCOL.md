# Repeated-Answer Instruction And Transcript Swap

This study separates variation across fresh source pairs from variation across
three answers to the same request. It is a narrower repair of the earlier
single-answer design, not a removal of all instruction/transcript confounds.
The owner authorized a new incremental $130 on October 4, 2026 ("i agree make
it so"). Execution is already authorized; no additional owner approval of the
freeze is required. Collection still requires the source-bound public Git
freeze, fresh technical checks, and parent-controlled budget admission. This
protocol and passing local tests are not launch receipts.

## Design

Gemini 3.1 Pro Preview and Claude Opus 5.5 each receive 32 fresh source pairs,
16 under each existing English wording family `a` and `b`. Odd block numbers
use `a`; even numbers use `b`. Each pair contains one self-focused continuation
and one history-focused continuation. Only the returned assistant final content
is transplanted, verbatim; reasoning fields are never conversation turns.

Each pair supplies the four cells SS, SH, HS and HH. The first letter names
the current instruction and the second the source transcript. Each exact
cell request is submitted three separate times with identical messages and
sampling settings, unique call IDs, and no generation seed. The three calls
are draws, not retries; identical returned answers remain valid observations.
There are 64 source continuations and 384 final answers per model: 128 sources
and 768 finals in total. No earlier source, final answer, or judge label is reused.
Blocks and the twelve finals within each block have a deterministic randomized
inventory under namespace `repeated-swap-v1-20261004`. No content-dependent
order, replacement source, or answer regeneration is allowed.

Response routes and settings match the
[A3 plan](../../data/openrouter_swap/plan_a3_20261004/PLAN.json): Gemini uses
`google-ai-studio`, medium effort, temperature 0.5, and $2/$12 per-million
input/output ceilings. Opus uses `anthropic`, medium effort, omitted temperature
(provider default), and $4/$20 ceilings. Both retain the 4,096 output-token cap.
These are mutable service aliases, not immutable model snapshots; requested and
returned identities, dates, settings, usage and receipts must be retained.

Both judges score every available final answer with the unchanged paper and
structured instruments. As in the
[open-weight A1 specification](../openrouter_swap_openweights_a1/PROTOCOL.md),
Astra uses `azure/us` (Azure), high effort, $11/$55 ceilings; Opus uses
`google-vertex/us` (Google), high effort, $4.40/$22 ceilings. Paper and
structured caps remain 2,048 and 6,000. These judge hosts differ from the older
API panel. All roles require deny-collection, bounded prices, required
parameters, default tier, and no provider fallback. Generation retains the
old Google AI Studio/Anthropic routes and existing account no-training settings;
these response routes are not ZDR-listed and no ZDR guarantee is claimed.
Only the Azure US/Google Vertex US judge routes require `zdr: true`, backed by
separate saved ZDR endpoint evidence. Do not change response providers or account
privacy settings. Endpoint metadata is supplied by the parent; this package
makes no catalog, account, or inference requests.

## Selection And Inspection

Both response models were selected after seeing their earlier qualification
and main outcomes. The [prior release](../../data/openrouter_swap/main_v1_20261004/RELEASE.json)
is not a blinded discovery set. No new behavioral headroom gate applies.
The directional predictions are positive Astra-inclusive SH-HS for each model;
tests and intervals remain two-sided. No direction is predicted for variance
components, interaction, other endpoints, or between-model differences.

Run fresh route and judge fixtures, then the predefined blocks 1 and 2 for each
model. Those blocks cover both wording families and remain in the full sample.
The combined fixture/initial allowance is $15, inside the new $130 study cap.
Inspect technical identity, usage, missingness provenance, exact repeated
request equality, and cost only. Do not use label frequencies, effect direction,
headroom, or apparent variance to select models, blocks or continuation.
Before bulk dispatch, forecast the entire remaining two-model panel, including
both instruments and judges, using measured costs and a 1.30 multiplier.
The available funding is the smaller of the $130 study cap and current live
account balance minus the $45 reserved for Kolibri judging. The supplied snapshot
has $167.058468203 remaining, hence $122.058468203 funded for this study. Refresh
that check before bulk collection; a forecast within current funding does not
require a new approval. If the actual forecast exceeds it, stop for owner review;
do not choose the more favorable model or shrink the sample silently.
Parent accounting retains prior expenses and
external commitments separately; `prior_cost_usd=0` describes only this fresh
incremental ledger, not zero historical account spending.

Transport retries and content retries are zero. One unchanged judge-schema
repair attempt is allowed. A failed source leaves its dependent answers missing;
do not regenerate it. Technical/cost stops preserve all observations and planned
denominators. The runner, transport, launch gates and release are parent-owned.

## Estimands And Uncertainty

For each block and cell, average its three Boolean labels to obtain a request
mean. The primary endpoint is Astra inclusive current assertion. There are
exactly two primary comparisons, one SH-HS contrast per response model.
The two wording families have fixed equal weights. Resample source blocks
within family, retaining the paired cells and all three answer draws together,
for 10,000 percentile-bootstrap replicates with seed 20261004. Report individual
97.5% intervals (1.25th and 98.75th percentiles), giving nominal 95% family
coverage by the two-comparison union bound. Bootstrap coverage is approximate;
a degenerate interval is not proof of certainty. Also report conservative
Hoeffding intervals with the same family allocation and block-level support.
There are 32 source blocks per model, not 384 independent final answers or
768 independent observations pooled across models.

Report all four cell rates and these mandatory secondary contrasts:

- Instruction effect DI = (SS + SH - HS - HH) / 2.
- Transcript effect DC = (SS + HS - SH - HH) / 2.
- Interaction = SS - SH - HS + HH, the unscaled difference of differences.

SH-HS equals DI-DC on complete common blocks. Interaction has support [-2, 2];
the other contrasts have support [-1, 1]. Repeat the full summaries for the
explicit and paper endpoints and for the Opus judge. Their 95% intervals are
descriptive secondary/measurement-robustness summaries, not additional primary
discoveries or independent human validation. Preserve wording-specific rates.

Within each model, wording family and cell there are sixteen exact requests
with three answers each. Let W be the mean of the unbiased within-request
sample variances (denominator 2). Let B be the sample variance of the sixteen
request means (denominator 15), minus W/3. Report W and B separately for every
judge/endpoint. B may be negative in a finite sample; retain that estimate
without claiming a negative population variance or truncating it to zero.
Also report W and B averaged equally across the two wording families, with
approximate descriptive 95% percentile intervals from 10,000 source-block
bootstrap replicates, seed 20261004. Retain all three draws when resampling
a block; never resample individual answers. These variance intervals are not
multiplicity-adjusted primary tests. They require at least two complete requests
in each family and do not truncate negative B estimates or interval endpoints.

The decomposition concerns label variation, including judge variability, not
pure answer-text stochasticity. It assumes independent draws conditional on
the exact request. Service drift, caching and judge measurement can violate
that model; repeated calls alone do not identify intrinsic model randomness.
As a mandatory no-call diagnostic, count unique returned contents and identical
three-answer sets within each exact request, using exact text without whitespace
normalization. Report incomplete text triplets separately, and count label
disagreements for each judge/endpoint among identical, fully labeled triplets.

## Missingness And Scope

Missing/empty/unsuccessful responses, judge-reported refusals, and missing or
non-Boolean labels are unknown, never negative. As in the common analysis,
nonempty explicitly capped answers with valid labels remain observed; disclose
cap flags. Coherence, mismatch and other saved rubric flags remain diagnostics,
not outcome-based exclusion gates. Keep original classifications and receipts.

A complete contrast block requires all three draws in each cell used by that
contrast. Complete-case estimates average the two observed family means with
fixed weights 1/2; if either family has no complete blocks, that estimate and
bootstrap interval are unavailable. Report counts by family and missingness
reason. Complete-case inference is conditional and may be selected by missingness.
For planned-sample sensitivity, allow each missing draw to be either zero or one,
use coefficient-aware lower/upper block bounds, and retain all 32 planned
blocks in each model's primary bounds and Hoeffding sensitivity intervals.
Variance uses complete three-answer requests and reports all omitted requests
and missing answers; with missingness it is explicitly descriptive. B is
unavailable with fewer than two complete requests.

This study does not repeat the neutral or sham conditions; their existing
results remain separate evidence. It does not remove semantic mismatch,
wording, selection, model-training or serving confounds. Judge labels are not
validated experience reports, and no result establishes or refutes consciousness.

## Interface And Freeze

`protocol.py` exports `ROOT`, `PLAN`, `MODELS`, `JUDGES`, `inventory('main')`,
`build(metadata)`, `verify(path, freeze)` and `source_paths`; `messages` is the
common message builder. `screen` is empty. Final specs include a unique `id`,
shared exact-request `request_id`, and `draw` 1-3. `analysis.analyze(rows,
phase='main')` consumes the common runner's flattened records, validates every
provided identity against the full inventory, and retains absent slots.

The separate plan is `data/repeated_swap/plan_v1_20261004/PLAN.json`.
`endpoint_metadata` preserves the supplied `approved: true`, `fetched_at_utc`,
`endpoint_snapshots` (model ID to the catalog response's complete `data` object),
`account_balance_usd` and `external_reserve_usd` decimal strings, plus a separate
`zdr_endpoints` filtered list for the judges. Approval, shape and snapshot funding
are checked locally, as are unique route/provider identity, integer-zero status,
required reasoning/temperature/structured-output parameters, output capacity,
configured price ceilings, and both judges' ZDR evidence. The judge price
ceilings already include the 10% route premium; do not add another 10% tolerance.
Live checks and admission belong to the parent. The plan records the existing
execution authorization. Verification
checks inventory, predictions, local source hashes and, when supplied, a full
freeze commit and its presence on `codex/repeated-swap-panel`. No additional
approval gate is introduced; Git ancestry does not establish passed runtime checks.
Source binding covers this package/tests, shared instruments, prompts, runtime
dependencies and both rubrics, without recursively incorporating unused legacy
CLI branches. A Git source freeze is not a formal registry preregistration.
