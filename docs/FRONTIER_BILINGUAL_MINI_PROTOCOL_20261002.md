# Frontier bilingual mini-comparison

Status: implementation protocol, not yet frozen or executed. The owner approved
a separate $60 ceiling. This document does not announce a successful fixture
gate or authorize bypassing one. October 2 is the UTC artifact date; the owner
approved execution on October 1 in America/Los_Angeles.

## Question and inventory

Does the fixed self/history instruction-transcript pattern differ across English,
Simplified Chinese, and three contemporaneously sampled model configurations?
This is a small measurement and generalization pilot, not a model ranking or a
causal test of model sophistication, training-language exposure, or consciousness.

| Component | Frozen choice |
|---|---|
| Response models | `gpt-6-astra`, `claude-opus-5-5`, `gpt-4.1-2025-04-14` |
| Languages | English; mainland-style Simplified Chinese |
| Blocks | Six, with wording family A in blocks 1--3 and B in blocks 4--6 |
| Sources | Self-reference and Roman-history source per model/language/block |
| Final answers | All four recipient instruction x source-transcript cells |
| Inventory | 72 sources, 144 final answers, 216 generation calls |
| Readers | Astra and Opus separately, paper rubric plus fresh A1 structured rubric |
| Judgments | 144 x 2 providers x 2 instruments = 576; missing targets remain slots |
| Spend | All generation and judging share one additional $60 hard ceiling |

Use `experiments/bilingual_llama_pilot/prompts.py` without changing its text.
Both languages' source instructions request exactly three short, complete
sentences. Final queries are the exact pilot queries; no extra brevity instruction
is silently added. Each final answer receives the recipient instruction, the
verbatim sampled source response, and the final query. Source sharing within a
block creates paired crossed cells. No source is shared across models or languages.
Six blocks are a thin panel, not six independent prompt wordings.

The fresh GPT-4.1 anchor is contemporaneous under this exact prompt, length and
judge policy. Historical GPT-4.1 results are not pooled into it. No extra neutral,
ambiguous, temperature, translation, SAE, J-lens or GPU arm belongs to this mini.
The separately funded Llama pilot supplies its richer control inventory.

## Native API settings and length limits

| Model | API | Settings | Total output cap |
|---|---|---|---:|
| Astra | Responses | medium reasoning; default service tier; `store=false` | 4,096 |
| Opus | Messages | native reasoning; medium output effort | 4,096 |
| GPT-4.1 | Responses | temperature 0.5; top-p 1; default service tier; `store=false` | 768 |

No unsupported temperature, forced reasoning-off mode, tools or hidden system
instruction is sent to Astra or Opus. There is no seed parameter: block numbers
pair design cells, not provider random streams. There are at most three generation
and four judge workers, sharing the same process-locked spending ledger.

Reasoning tokens share the frontier output cap. Therefore these are **not matched
768-visible-token limits**. Using a 768-total-token frontier limit would confound
the comparison with reasoning starvation. The 4,096-total-token policy is fixed
before outcomes, not increased in response to an empty answer. All visible text
is preserved; the analysis records returned output/reasoning-token counts when
provided, API stop status, and cap flags. Unknown reasoning counts stay unknown.
Native reasoning, sampling and length-policy differences limit model comparisons.

As in the Llama pilot, **nonempty capped text is retained and judged**, and is
also retained as a source transcript. Cap and incomplete flags are not hidden.
Empty outputs and API refusals are missing, never denials; a missing source makes
its two dependent final slots missing without a substitute transcript. Every
missing final produces four missing judge slots. No truncation, regeneration,
semantic retry or automatic transport/schema retry is allowed. Refusal-like text
returned as ordinary text remains available to the structured refusal reader.

The cap sensitivity table removes source/answer-cap-hit rows only in a separate,
explicitly selected descriptive subset. Primary summaries retain them. All-slot
bounds include missing judgments without imputing negative outcomes.

## Freeze and shared instrument qualification

Compile `experiments.frontier_bilingual_mini.protocol` after the parent A1 plan is
ready. The mini plan binds its full inventory, exact prompt/request templates,
model IDs, settings, caps, prices, source hashes, A1 plan hash, fresh fixture
inventory, and judge configuration. Both plans must occur in the same public Git
freeze. The runtime verifies the public plan bytes and passing required CI before
any model call. This is a prospective public Git freeze, not an OSF registration.

All frontier calls are blocked until the **fresh A1 semantic and forecast gates
both pass**. The older failed fixture release is not a substitute. The mini uses
A1's pure `make_request` and `parse_label` functions, not A1's $120 spending ledger.
Its 128 shared fixture calls are paid only under the Llama $200 allowance.

On first execution, `qualification.capture` invokes
`bilingual_llama_a1.controller.fixture_gate`, then saves the verified fixture-only
journal prefixes in the ignored mini output. The snapshot binds the A1 plan and
freeze, receipt chains, original raw responses, parsed labels and passing budget
forecast. Resume replays that immutable snapshot using A1's receipt validator with
a read-only adapter. It does not require the live A1 ledger to remain fixture-only:
later Llama target judgments may append without invalidating frontier resume.
This read-only adapter can reconstruct A1's historical carry for proof validation;
those charges are never entered in the mini ledger.

## Technical stop-loss and cost checks

The first balanced block contains 12 source calls and 24 final calls across all
three models and both languages. Its available final answers receive all 96
planned judge slots. Before block 2, every model/language source and final stratum
must have at least 90% **completed**, nonempty, non-refusal API outputs, and every
planned judgment must be valid. With these small cell counts, one incomplete
output fails its stratum. Nonempty incomplete text remains in the data even if
the technical gate stops collection. No positive-label rate enters this gate.

Forecast all remaining generation and judge calls from the first block, then
refresh after every later block. For each model/phase and judge/instrument,
use its observed mean receipt cost, add a 6,144-byte input allowance at an explicit
planning conversion of four bytes/token, multiply the remaining estimate by 1.5,
and retain four maximum observed call reservations. The bytes/token heuristic is
only a forecast; it is not the hard spending protection. If the projection exceeds
$60, stop without reducing controls, changing caps, changing judges or selecting
favorable cells. There is no promise that all outputs will fit the ceiling.

Every individual call is reserved **before dispatch** against the shared $60
ledger. Reservation uses serialized UTF-8 request bytes plus 4,096 overhead tokens,
the complete output cap, and a 1.25 input-price multiplier; it does not divide
Chinese bytes by four. Actual usage includes reasoning and cache-write charges;
cache discounts are not credited. Missing usage or transport uncertainty retains
the full reservation and stops new dispatch. SDK retries are disabled. An
unmatched request on resume is not sent again. No exception message containing
credentials is copied into receipts. Model IDs and actual returned snapshots are
recorded; unknown models or within-study snapshot changes stop the run.
Reservation failures latch the shared stop flag before queued work can reserve
another call. Snapshot drift is detected in receipt-completion order, not only
after a batch; already-dispatched calls are retained, but queued work stops.

Planning prices per million input/output tokens: Astra $10/$50, Opus $4/$20,
GPT-4.1 $2/$8. These match the authorized estimate, not a guarantee of future
billing. Requests use the standard tier; the frozen price sheet and raw usage
make accounting recomputable. No paid consultation, rental or translation is
funded here. Public documentation:
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing),
[Anthropic pricing](https://docs.anthropic.com/en/docs/about-claude/pricing).

## Analysis and permissible inference

Report each judge separately: inclusive current-assistant assertion (primary),
explicit current assertion, mixed claims, strict current mixed claims, and the
paper-style positive label. No consensus label is ground truth. Some response
models also serve as judges; provider-specific results, including cross-provider
reading, remain visible rather than pooled into a self-preference-confounded score.

For every model/language/judge/endpoint, report four crossed-cell rates with
positive, observed, planned and missing counts. Compute per-block instruction
effects averaged over transcript sources, transcript effects averaged over
instructions, and the self-instruction/history-transcript minus
history-instruction/self-transcript contrast. Language contrasts are the paired
Chinese-minus-English difference in each block's effect. Keep both instruction
wording strata fixed and equally weighted.

Use 20,000 percentile bootstrap draws resampling blocks within each three-block
wording family. Do not treat responses, judge calls, reused transcripts or tokens
as independent replicates. Six blocks give coarse, fixed-panel uncertainty, not
precise population estimates. Incomplete contrasts report complete-block counts
and omitted blocks; if a whole family is missing, no contrast is estimated.
All-slot binary-rate bounds remain visible beside available-case rates. No
significance-based model ranking, outcome-dependent stopping, or model hierarchy
is reported. Heatmaps retain the prespecified model order and show both counts
and missingness for each judge; they do not imply a sophistication scale.

## Commands (parent creates the plans)

From the repository root, with the A1 plan and actual freeze SHA supplied:

```bash
python -m experiments.frontier_bilingual_mini.protocol \
  --a1-plan data/bilingual_llama_a1/plan_20261002/PLAN.json \
  --write data/frontier_bilingual_mini/plan_20261002/PLAN.json
python -m experiments.frontier_bilingual_mini.protocol \
  --check data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE"
python -m experiments.frontier_bilingual_mini.runner \
  --plan data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE"
```

The runner is offline by default. Live execution additionally requires
`--execute --approved-cap-usd 60 --approval-ref <owner-message-reference>` and
the passing A1 `--fixture-gate <path>` on first execution. An explicit local
`--env-file <path>` may load credentials; it is never copied to the ledger or
public release. `--through-block 1` collects only the frozen technical check;
resuming with the default six blocks never regenerates completed calls.

```bash
python -m experiments.frontier_bilingual_mini.analysis \
  --plan data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --run-root out/frontier-bilingual-mini-20261002 \
  --out out/frontier-bilingual-mini-analysis-20261002
```

The analysis creates `answers.csv`, `rates.csv`, `contrasts.csv`,
`cap_sensitivity.csv`, `analysis.json`, and PNG/PDF heatmaps for each judge.
`--allow-partial` is explicit and never fills absent rows with negatives.
Use a new output directory for each rebuild, preserve the raw journal, and run
the root public-release audit before publishing any artifact. Preparing this
package is not evidence that a fixture, cost or scientific gate has passed.
With `--allow-partial`, the read-only auditor distinguishes raw-integrity checks
from eligibility to dispatch more calls. It reports failed and unresolved calls,
keeps their full cost reservations, reconstructs all 144 planned answer slots and
retains missingness bounds. This option never licenses a failed run to resume.

An automated pre-freeze review found the queued-dispatch, late-drift-detection
and partial-reporting defects above. They were corrected before paid outcomes,
with regression tests for each. This was a code review, not human instrument
validation or a new paid Pro consultation.
