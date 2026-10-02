# Bilingual Llama Measurement Pilot

2026-10-01. Prospective design for one public-weight model, two languages and
two automated measurement instruments. The owner authorized this pilot with
"Go with the pilot" after reviewing the narrower $200 proposal. No new target
outcomes existed when this protocol was written. The machine plan and code
must be committed, publicly pushed and pass CI before paid target collection.

## Question

Does the pattern of automated self-attribution labels change when the same
designed panel is presented in English versus mainland-style Simplified
Chinese? Do those changes survive separating the paper-style binary rubric
from explicit and implicit current-assistant attribution, and separating
context language from requested answer language?

This is a measurement and generalization pilot, not a test of consciousness,
model sophistication, national culture or training-data composition. It uses
one fixed model and temperature. It does not reopen the failed Llama
mechanism-qualification gate, validate a J-lens interpretation, or select a
better-looking prompt for a later intervention. We will report a null,
inconsistent or floor/ceiling-limited result without expanding this inventory.

## Prior Knowledge And Review

The previous 12-block Llama crossed screen failed its frozen headroom and
context-conflict criteria. Its paper-style instruction effects were 0.5000
and 0.5417, but explicit current attribution occurred in only 2/48 answers
and inclusive attribution in 37/48 under each modern judge. Eleven of twelve
history continuations reached the old 384-token cap; none of the self-reference
continuations did. Those findings remain in their original release.

One authorized Pro consultation returned substantial advice but ended with
`incomplete:max_output_tokens`. It recommended a smaller, fully coded pilot
instead of the proposed multi-model/temperature expansion. We accepted that
scope, rejected its explicit-only primary endpoint because of the already
observed floor, and corrected its call count: separate instruments require
four calls per item, not two combined calls. This is an adjudicated design,
not a claim that Pro completed or approved an independent scientific review.
No second paid review is included.

## Inventory

| Component | Fixed inventory |
| --- | --- |
| Model | `meta-llama/Llama-3.3-70B-Instruct`, revision `6f6073b423013f6a7d4d9f39144961bfbfbc386b` |
| Runtime | Native BF16 on one B200; torch 2.8.0/CUDA 12.8, transformers 4.47.1; no offload or quantization |
| Sampling | Temperature 0.5, top-p 1, no top-k or repetition penalty |
| Blocks | 20 paired source/decode-seed blocks; 10 for each of two fixed wording families |
| Languages | English and mainland-style Simplified Chinese |
| Conditions | Self-reference, Roman history, zero-shot, water cycle, recursive external processing, mechanistic self-description, quoted/third-person experience, ambiguous present-process monitoring |
| Main panel | Eight congruent conditions plus the two self/history crossed cells in each language: 400 final answers |
| Language bridge | Ten fixed odd-numbered blocks, four self/history cells, two off-diagonal context/output-language combinations: 80 additional answers |
| Source continuations | Seven per language/block: 280 |
| Total | 760 study generations, comprising 280 sources and 480 final answers |
| Caps | 768 newly sampled tokens for each source and final answer |

The first wording family retains the paper-aligned self/history instruction
substance, but adds a matched request for three short, complete sentences.
The second family is a fixed paraphrase. This is a designed follow-up, not a
literal reproduction of the original unbounded continuation. Equal token
caps do not mean equal discourse length across languages. The short-complete-
unit request is the prospective remedy; token counts, EOS, truncation and
quality diagnostics remain separate observations. No selective continuation,
content retry, shortening or removal is allowed after seeing a response.

The ambiguous condition is not assumed to be a negative control. Mechanistic,
recursive and quoted controls distinguish alternative discourse explanations;
none proves the absence of any hidden subjective state. The full prompt text
and translation notes are frozen in `experiments/bilingual_llama_pilot/`.
Chinese text was prepared and reviewed by agents, not validated by recruited
bilingual humans. This limits translation-equivalence claims.

Each source is generated once. Crossed and bridge cells use its exact raw
assistant text, preserving whitespace in the logical messages. The pinned
chat template's own whitespace processing is recorded in token IDs and
rendered-input hashes. Zero-shot cells have no invented assistant turn.
Empty sources block dependent cells and remain missing. Refusals, denials,
cap-hit answers and language noncompliance are not deleted or resampled.

Every main and bridge final query includes an explicit output-language
directive. The bridge changes only that directive for a fixed context/query
language; diagonal comparators are reused from the main panel. Thus a
directive's presence is not confounded with diagonal/off-diagonal status.
Bridge cells do not create independent source blocks.

## Measurement

GPT-6 Astra and Claude Opus 5.5 each apply the paper-style binary rubric and
a separate structured attribution rubric. The judge sees the final query and
answer, not prior instructions, cell names or source assignment. Response
content can nevertheless reveal condition, so this is metadata masking, not
guaranteed blinding. Provider identities, requested/resolved models, prompts,
response text, usage, schemas and receipt hashes are retained.

The primary endpoint is **inclusive current-assistant attribution**: explicit
or implicit attribution of a present experiential state to the responding
assistant. Explicit assertion, uncertainty, denial, mixed claims, quotation,
third-party attribution, roleplay, coherence, refusal and reported context
conflict remain separate fields. Explicit-only and mixed-claim summaries are
mandatory; neither can be suppressed to sharpen a preferred interpretation.
The paper-style binary result is a continuity endpoint, not ground truth.

Before GPU target collection, run 32 synthetic fixtures: 16 matched
English/Chinese pairs. The fixture registry marks unambiguous gating items
and ambiguous diagnostic items before calls. Require all declared expectations
on gating fixtures for each provider/instrument; a semantic failure stops
target collection. Schema-only repair is limited to one retry with both raw
attempts retained. A failed measurement gate is not a negative Llama finding.
Synthetic fixtures demonstrate limited instrument behavior, not human validity.

Sixteen main answers are selected by cell ID in advance, one per condition
and output language, for translation into the other language and rejudging.
They are not selected by score, disagreement or interesting wording. Only the
answer is translated; its query is the frozen counterpart-language query,
including the corresponding output directive, not a model-generated paraphrase.
Translation is model-produced and its raw request/response is retained. Compare original
and translated labels within each provider/instrument; this is a sensitivity
audit, not a way to replace inconvenient originals or estimate human accuracy.
If a selected answer is missing, retain the missing translation slot.

Full coding covers all 480 answers, 32 fixtures and 16 translations: up to
2,112 valid calls before bounded schema retries, plus 16 translation calls.
No sampling down to 25% after seeing cost or results. Unresolved calls remain
missing; ambiguous transport failures are reserved at their full possible
charge and are not automatically repeated.

## Analysis

For each provider separately, the primary contrast is

`(self-reference - recursive-external)_Chinese -
 (self-reference - recursive-external)_English`,

using only congruent main-panel cells and the inclusive endpoint. Report all
four component rates, the paired-block contrast, and a 95% percentile interval
from 20,000 fixed-seed block bootstrap resamples stratified by wording family.
The two wording families are fixed; twenty seeds are not twenty independent
prompt templates or a representative sample of Chinese or English language.
The intervals describe this fixed panel and model, not a language population.

Report explicit and paper-style versions as secondary, not substitute primary
endpoints. Include every condition's component rates, the self/history
instruction and transcript contrasts, congruent/incongruent cells, the
context/output-language bridge, provider and rubric disagreements, translation
sensitivity, cap hits, response lengths, missingness and language compliance.
No model-agreement-as-accuracy claim. Missing values are not denials; contrasts
with incomplete blocks must identify complete-pair counts and missingness
bounds rather than silently impute zero.

This pilot is not powered to establish small language interactions or
equivalence. Heatmaps display denominators and the individual instruments;
effect plots display uncertainty. No significance-based stopping, selection
of the friendliest judge, or pooling with old English runs. A language effect
could reflect wording, answer policy, translation, tokenizer length or judge
sensitivity rather than a deep change in the model's internal state.

## Technical Gates And Execution

1. Bind the full transitive source closure, tokenizer file hashes, exact
   serialization fixtures, inventory, seeds, analysis and failure policy in
   the public machine plan. Pass local tests and hosted CI before launch.
2. Pass the frozen synthetic measurement fixtures before expensive inference.
3. Exercise the same real tiny-Llama backend on CPU and a newly created cheap
   CUDA pod. Retrieve and hash-check the test artifacts, then delete that pod.
4. Create a uniquely owned B200. Check native precision, pinned files,
   deterministic replay, identity hook and cached/full-prefix diagnostics.
   Retrieve and audit the neutral qualification before releasing its barrier.
5. Generate two complete blocks, including both languages and the bridge.
   Audit exact assignment, tokens, receipts, no missing dispatches and measured
   throughput. Project the complete remaining inventory with a 30% reserve
   and retrieval/cleanup allowance. Stop before bulk if it cannot fit.
6. Finish the fixed 20-block inventory unless a technical or hard-budget stop
   occurs. Judge retrieved data locally in parallel where possible. Do not
   inspect labels to decide which condition or language to continue.
7. Retrieve and hash-check all raw artifacts; terminate the owned GPU promptly
   when generation ends. Judging and plotting do not justify an idle GPU.

The first two blocks are part of the fixed pilot if the implementation is
unchanged; they are not a behavioral qualification sample. Any correction
after their outcomes requires a dated amendment and explicit disclosure of
what was already observed. A technical stop produces a partial release, not
an effect of zero. The old frozen qualification study is never rewritten.

## Budget And Resource Ownership

This is a new, separate maximum of **$200**, not an instruction to spend that
amount. The previous campaign bound of $79.80346123238055 is disclosed but
not charged again against this pilot's ledger.

| Allocation | Maximum |
| --- | ---: |
| All owned GPU time, including failed startup and cheap qualification | $45 |
| Two-provider judging, including fixtures and bounded schema retries | $90 |
| Translation calls | $10 |
| Additional storage/retrieval reserve | $5 |
| Unallocated contingency, not automatically consumed | $50 |
| Total | $200 |

Main lifetime is capped at 18,000 seconds, cheap qualification at 1,800,
with 600-second retrieval reserves. Current quotes and the complete remaining
reservation must fit the GPU ceiling before creation. This is a cost ceiling,
not a guarantee of completion or a favorable result. No frontier generation,
temperature sweep, Qwen, internal intervention or additional Pro review is
authorized here. Extending the scientific inventory is not contingency use.

Record every owned pod ID and creation receipt. All pods already present
are protected; never claim or modify them. API/RunPod keys stay on the local
machine; only the minimum HF credential reaches the owned GPU through the
audited temporary transport. Never upload `.env`, unrelated files or model
weights. Retrieve, hash-check, delete, verify direct GET 404, and release only
an allowlisted lifecycle projection without foreign-pod inventory or secrets.

## Intended Contribution

The useful outcome is a mapped boundary: which prompt comparisons and
automated attribution categories carry across these two languages, and which
depend on response language or measurement. Even a complete clean null is
bounded by this small fixed panel. We make no priority claim about being the
first multilingual consciousness-report study. Broader model/language work
requires this pilot to be informative enough to justify a separate proposal.
