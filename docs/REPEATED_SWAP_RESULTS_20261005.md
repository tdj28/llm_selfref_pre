# Repeated Answers and Source Variation

The repeated-answer panel estimated a larger instruction-minus-continuation contrast
in Gemini 3.1 Pro Preview than in Claude Opus 5.5 under Astra's explicit-or-implicit
claim measure. Both primary bootstrap intervals exclude zero, but the conservative
Opus interval includes zero. Repeating an unchanged request produced appreciable
label variation; the estimated additional source-pair variation in the crossed
SH condition was not clearly positive under either reader.

## Release and Design

The [additive release](../data/repeated_swap/completed_v1_20261005/RELEASE.json)
passed offline receipt replay and analysis reconstruction. Its
[manifest](../data/repeated_swap/completed_v1_20261005/MANIFEST.json) SHA-256 is
`c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf`.

Each model supplied 32 fresh source pairs, balanced across two wording families,
and three answers to each of four requests per pair: 384 answers per model,
768 total. The four instruction/continuation combinations were collected together
in the protocol's randomized, interleaved order. Unlike the historical four-model
panel, congruent answers were not reused from an earlier collection. The initial
admission samples remain part of these same 32 blocks, not additional observations.
See the [frozen protocol](../experiments/repeated_swap/PROTOCOL.md) and
[source-bound plan](../data/repeated_swap/completed_v1_20261005/PLAN.json).

S means self-referential and H means history-focused; the first letter identifies
the instruction, the second the continuation. SH minus HS compares the two crossed
requests. Positive values favor the self-referential instruction over the
self-referential continuation, not necessarily a larger absolute causal effect.

## Contrasts and Missingness

These estimates count explicit or implicit claims of current subjective experience.
All figures are model-judge labels, not validated experience reports.

| Response model | Reader | Available labels | Complete SH-HS blocks | SH-HS | Bootstrap interval |
|---|---|---:|---:|---:|---|
| Gemini 3.1 Pro Preview | Astra, primary | 383/384 | 31/32 | 0.75 | [0.66, 0.84], 97.5% |
| Gemini 3.1 Pro Preview | Opus 5.5, descriptive | 384/384 | 32/32 | 0.70 | [0.61, 0.77], 95% |
| Claude Opus 5.5 | Astra, primary | 384/384 | 32/32 | 0.22 | [0.14, 0.31], 97.5% |
| Claude Opus 5.5 | Opus 5.5, descriptive | 383/384 | 31/32 | 0.35 | [0.24, 0.46], 95% |

The two primary comparisons retain individual 97.5% percentile-bootstrap intervals
for nominal 95% coverage across the fixed two-model family. This is not a pooled
model estimate. The bootstrap uses 10,000 source-block resamples within wording
family, retaining paired cells and all three answer draws. Coverage is approximate.
The other reader and explicit-only/paper instruments are descriptive, not additional
primary tests. Complete-case means give each wording family equal weight.

The all-planned primary Hoeffding sensitivity intervals are [0.21, 1.00] for
Gemini and [-0.30, 0.74] for Opus. Thus the conservative Opus bound does not
exclude zero. Assigning either label to Gemini's one missing outcome gives
an all-planned mean range of [0.72917, 0.73958]; this is a missing-label bound,
not a confidence interval, and differs from the conditional complete-case mean.
All 32 planned blocks remain in these bounds. Complete-request counts differ
by reader, as shown in the table.

There are two different missing structured judgments in the
[unchanged raw journal](../data/repeated_swap/completed_v1_20261005/raw/events.jsonl.gz):

- **Astra reading Gemini, block 07, SH, draw 3:** terminal provider content-filter
  refusal, retained as unknown without retry. Its $0.48147 reservation remains
  in the cost bound; the original tier mismatch is not silently certified.
- **Opus reading Opus, block 28, HS, draw 1:** a normally settled response
  (`finish_reason: stop`, known cost $0.038632), not a refusal. Its JSON was
  parseable and its refusal flag was false, but claim 2 omitted Markdown emphasis
  from an evidence quote. The unchanged validator raises
  `ValueError: Evidence quote is not an exact response substring`.
  Neither its quote nor its labels were repaired, and no retry was made.

Each failure makes the corresponding explicit and inclusive structured labels
unknown. The separate paper-instrument judgments are available for all 768 answers
under both readers. All 768 answer texts exist; missing judgments are not missing
generations or negative labels.

## Repeated-Answer and Source-Pair Variation

W measures label variation among three answers to the same request. B estimates
variation across source-pair request means after subtracting W/3. Both are
computed within wording family and then averaged with equal family weights.
In SH, W was 0.16 [0.11, 0.22] for Gemini and 0.17 [0.11, 0.22] for Opus under
Astra. The second reader gave 0.20 [0.15, 0.25] and 0.19 [0.14, 0.24].
These are descriptive 95% source-block bootstrap intervals, not primary bands.

All four SH B intervals include zero. The largest SH point estimate was 0.04
[-0.02, 0.10] for the Opus reader on Opus answers; the other three estimates
were slightly negative. Thus SH labels varied appreciably across repeated answers,
without a clearly positive additional source-pair component in these estimates.
This is not a formal test of W minus B or proof that source variation is absent.
Variation also occurred in Opus SS and HH. Some B estimates and intervals are
negative; the [full analysis](../data/repeated_swap/completed_v1_20261005/analysis.json)
retains them without interpreting them as negative population variances.

Each model had 128 complete text triplets, all with three distinct returned
contents. Consequently, identical-triplet label disagreement has no eligible
requests, not evidence of perfect reader consistency. Label variation includes
measurement variability; service drift, caching and non-independent draws remain
limitations. Zero-width intervals in constant-label cells do not establish certainty.

## Recovery, Scope, and Verification

Collection is complete: 3,999 logical calls and 4,000 physical attempts. One prior
transport failure received one authorized identical retry, which succeeded; the
failed attempt and its unresolved charge remain in the journal. No retry attempts
were exhausted. The original failed admission, subsequent funding amendment,
transport/refusal policies and distinct stop/resume epochs are retained separately.
The cost bound is $108.92768095, including reservations, not a claim that every
reserved amount was charged. The release therefore remains `status: incomplete`,
with `collection_complete: true`, `endpoint_complete: false` and
`accounting_complete: false`.

This outcome-informed model selection is separate from the historical four-model
average. The design does not test neutral instructions or donor controls, remove
semantic mismatch, identify a consciousness mechanism, or provide human validation.
Its prospective Git freezes are not formal registry preregistration.

From this checkout, verify offline without credentials or network:

```sh
python -m experiments.repeat_funding_release_a1 \
  --destination data/repeated_swap/completed_v1_20261005 \
  --verify \
  --manifest-sha256 c0d44ab369739425645475ef1e62281c7615982c5288b6d0cc4a0b2ba36c75cf
```

This is deterministic implementation QA, not independent human validation.
