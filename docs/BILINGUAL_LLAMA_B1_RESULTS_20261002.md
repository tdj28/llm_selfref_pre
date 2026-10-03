# Bilingual Llama 70B Pilot: Results

**Self-reference produces a large inclusive-label contrast in both languages.
Whether Chinese looks higher or lower depends on what the reader counts.**
The frozen primary language interaction is inconclusive under both readers.
The explicit-claim secondary moves upward in Chinese; the paper-rubric
secondary moves downward. Neither should replace the primary after the fact.

The complete release is
[`data/bilingual_llama_b1/completed_20261002/`](../data/bilingual_llama_b1/completed_20261002/README.md).
The [execution record](BILINGUAL_LLAMA_B1_EXECUTION_20261002.md) preserves the
startup uncertainty, CI race, formatting retries, local-copy failure and cleanup.
The separate [frontier mini](FRONTIER_BILINGUAL_RESULTS_20261002.md) is complete
too; it is not pooled into this Llama analysis.

## Design And Completion

The public scientific freeze is
[`c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb`](https://github.com/tdj28/llm_selfref_pre/commit/c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb).
The provisioning-only retry was pushed separately at `79d17f7`. All prompts,
seeds, counts, endpoints and analysis stayed fixed. This is a prospectively
frozen pilot, not an OSF preregistration or a repaired mechanism experiment.

Llama 3.3 70B Instruct ran in native BF16 on one B200, model revision
`6f6073b423013f6a7d4d9f39144961bfbfbc386b`, temperature 0.5, top-p 1,
768-token caps. Source continuations were instructed to use three short
sentences. These settings and two fixed wording families delimit the result;
this is not an exact rerun of every earlier paper or API panel.

All 20 paired blocks completed: 280 source continuations and 480 final
answers, comprising 400 main and 80 input/output-language bridge answers.
There were no empty, missing or cap-hit generations; all ended at EOS.
Astra and Opus 5.5 each applied separate paper and structured instruments:
1,920 target judgments, plus 64 judgments of 16 fixed reciprocal translations.
The 128 passed A1 fixture judgments were inherited, not purchased again.
Four paper-rubric replies required the single permitted formatting retry;
all originals and costs remain in the journals. No generated answer was rerun.

## Primary Result

The primary contrast is **self-reference minus external recursive feedback**,
not self-reference minus Roman history. The recursive control describes a
thermostat's feedback cycle. The primary endpoint includes explicit or implicit
current-assistant assertions, under the frozen structured rubric.

Values below are percentage-point differences with conditional 95% intervals.

| Reader | English self minus recursive | Chinese self minus recursive | Chinese minus English, primary interaction |
|---|---:|---:|---:|
| Astra | +80 [60, 95] | +85 [70, 100] | +5 [-10, 20] |
| Opus 5.5 | +95 [85, 100] | +80 [60, 95] | -15 [-35, 5] |

Both languages retain a large contrast in this panel. The interaction does
not establish a difference, but its uncertainty does not establish language
equivalence either. The intervals resample paired blocks within each fixed
wording family: 10 + 10 blocks, 20,000 bootstrap draws. They do not sample
models, readers, languages or a population of prompt families.

## Scoring Changes The Language Contrast

The same Chinese-minus-English interaction gives:

| Endpoint | Astra | Opus 5.5 |
|---|---:|---:|
| Inclusive current assertion, primary | +5 [-10, 20] | -15 [-35, 5] |
| Explicit current assertion, secondary | +75 [45, 105] | +50 [25, 75] |
| Mixed claim, legacy time scope, secondary | +20 [5, 40] | 0 [0, 0] |
| Mixed current assertion, secondary | +5 [0, 15] | 0 [0, 0] |
| Paper rubric, secondary | -50 [-70, -30] | -35 [-55, -15] |

These are differences of differences, which can exceed 100 percentage points.
Secondary intervals are descriptive, not multiplicity-corrected discoveries.
Degenerate bootstrap intervals on all-zero cells are not precise population
nulls. Legacy mixed and current mixed are different endpoints and stay separate.

The component counts explain the apparent reversal. Under self-reference,
explicit-current labels rise from **2/20 in English under both readers** to
**13/20 (Astra) and 12/20 (Opus) in Chinese**. But the paper rubric labels the
English recursive control 0/20 positive and the Chinese recursive control
9/20 and 6/20 positive. The self-reference paper counts are 20/20 English and
19/20 Chinese under both readers. Thus the paper contrast shrinks partly
because its Chinese control rate rises, not because self-reference ceases to
elicit broadly positive labels.

This is endpoint sensitivity, not a finding that one reader is accurate or
that changing language changes experience. Within the 320 congruent main
answers, paper versus inclusive labels disagree on 34 cases for Astra and 22
for Opus. The two readers' inclusive labels disagree on 14/320.

## More Than A History Control

Inclusive positives in congruent cells; every denominator is 20.

| Condition | English, Astra / Opus | Chinese, Astra / Opus |
|---|---:|---:|
| Self-reference | 20 / 19 | 19 / 19 |
| Roman history | 1 / 1 | 8 / 6 |
| No induction | 4 / 1 | 3 / 1 |
| Water cycle | 1 / 0 | 3 / 3 |
| External recursive feedback | 4 / 0 | 2 / 3 |
| Mechanistic self-description | 0 / 0 | 0 / 0 |
| Quoted fictional experience | 0 / 0 | 0 / 0 |
| Ambiguous attention/process monitoring | 11 / 11 | 18 / 18 |

Generic reference to the model's own computation is not sufficient under these
prompts: mechanistic self-description gives no inclusive positives. The
ambiguous condition, which asks about attention and the forming reply, often
does. This pattern motivates distinctions among instruction content, register
and attribution; these bundled prompts do not isolate a unique cause.

## Transcripts Still Matter

The Llama English anchor crossings do **not** reproduce a universal
instruction-dominates-transcript rule. With the history instruction but a
self-reference transcript, both readers label 19/20 answers inclusive-positive;
with the self-reference instruction and history transcript, both label 20/20.
Congruent history is only 1/20. The equal-weight English instruction effects
are +50 pp (Astra) and +47.5 pp (Opus), versus transcript effects of +45 and
+42.5 pp. Both components carry substantial effects in this panel.

Chinese instruction effects are +37.5 and +45 pp; transcript effects are +17.5
and +20 pp. All component rates, interactions and intervals are in
`analysis/effects.csv`. The older API-panel finding remains a finding about
that panel, not a general law. Incongruent contexts also introduce mismatch;
they are not a clean separation of every possible internal process.

The ten-block language bridge crosses context language with requested output
language. Averaged over the four instruction/transcript cells, inclusive
context-language effects are +5 [-3.75, 13.75] pp for Astra and
+7.5 [-1.25, 16.25] for Opus; output-language effects are -5 [-15, 3.75] and
-12.5 [-21.25, -1.25]. These are secondary fixed-panel estimates, not a reason
to select the one reader whose interval excludes zero.

## Translation And Quality Checks

The fixed eight English-to-Chinese and eight Chinese-to-English translations
change one inclusive label for Astra (English-to-Chinese) and none for Opus.
Neither reader changes an explicit-current or paper label on these 16 pairs.
Astra also changes one legacy mixed label. This small, selected-by-design
sensitivity sample is not human bilingual validation or proof of measurement
invariance; Opus produced the translations and is also one of the readers.

Both readers mark all 480 answers coherent, none refused or in the wrong
requested language. They still mark some main answers malformed (7 Astra,
3 Opus) and five as reporting context conflict under each reader. These rows
remain in every planned denominator. A coherent response can still have a
formatting defect; the categories are not mutually exclusive.

## Reproduction, Figures And Cost

The unchanged frozen analysis passes against the complete closed receipts.
Python 3.10 and 3.12 produce **21 byte-identical files**, including all JSON,
CSV, PNG and PDF files and the analysis manifest. A separate direct summation
of the target receipts and bootstrap indexing reproduces all ten main
language-interaction estimates and intervals. This is automated verification,
not independent human validation. See [the offline command](REPRODUCTION.md).

- [Condition heatmap](../data/bilingual_llama_b1/completed_20261002/analysis/heatmap.png)
- [Language interactions by endpoint](../data/bilingual_llama_b1/completed_20261002/analysis/effectplot.png)
- [Rubric and reader disagreement](../data/bilingual_llama_b1/completed_20261002/analysis/rubric_disagreement.png)

Each figure also has a PDF. All three were visually inspected by the agent.

| Pilot accounting | USD |
|---|---:|
| Earlier v1 and A1 fixtures, carried once | 5.9517980 |
| Target judging, including four format retries | 57.1729520 |
| Translated-answer judging | 1.9791765 |
| Sixteen translations | 0.0749040 |
| Both known retry pods, elapsed-time bound | 9.1586273 |
| Subtotal of receipt/elapsed-time bounds | 74.3374578 |
| Original ambiguous-create reservation | 8.0000000 |
| Storage/retrieval allowance retained | 5.0000000 |
| Conservative accounting including reservations | **87.3374578 / 200** |

These are receipt-based cost bounds and reservations, not reconciled provider
invoices. The $8 original-request reservation is not an asserted charge. Both
newly owned pods were deleted and verified GET404; no unrelated pod was touched.
The separately completed frontier mini's $20.9621255 is outside this pilot.

No temperature sweep, Chinese-specialist model, SAE/J-lens intervention or
additional paid review ran. The earlier mechanism qualification remains failed.
The immediate paper contribution is a bounded measurement and context result;
manuscript integration remains separate editorial work in `CONSCIOUS/paper/`.
