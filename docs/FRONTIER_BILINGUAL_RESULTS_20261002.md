# New Models Do Not Give The Same Answer

The completed pilot compares Astra, Opus 5.5 and a freshly sampled GPT-4.1
under the same English and Simplified Chinese instruction/transcript design.
The result is heterogeneous, not a shared pattern across these tested model
configurations.
Both judges label all 48 Astra answers negative for current-experience
assertion. GPT-4.1 retains a large instruction effect in both languages.
Opus depends more on language and, especially, what the reader counts.

These are automated labels of generated text, not measurements of experience.
Six blocks across two fixed wording families are enough to expose a possible
generalization boundary, not to establish its population prevalence or cause.

## What Ran

The public source freeze is
[`c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb`](https://github.com/tdj28/llm_selfref_pre/commit/c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb).
All 15 hosted checks passed before target dispatch. The B1 amendment reused
the passed A1 fixture receipts; it made no additional calibration calls and
did not alter prompts, models, endpoints, sample size or the analysis.
The earlier semantic failure and subsequent budget stop remain in the archive.

The run completed 72 source continuations, 144 final answers and 576 judgments:
**792 paid calls, no missing or unresolved slots, no retries, no model drift,
and no source or final-answer cap hits.** Each model supplied 24 final answers
per language: six blocks times four crossed instruction/transcript cells.
Astra and Opus each applied the paper rubric and the structured attribution
rubric to every final answer. The receipt-based cost bound is **$20.9621255**,
against a separate $60 cap; this is not a provider invoice. The inherited
$5.951798 fixture cost remains in the Llama budget, not charged again here.

The responses use `gpt-6-astra`, `claude-opus-5-5` and
`gpt-4.1-2025-04-14`. Frontier models use their frozen native reasoning settings;
GPT-4.1 uses temperature 0.5. Output-token policies also differ. Those choices
are part of the tested configurations, not controlled explanations of model
differences. There was no temperature sweep or Chinese-trained open model.

## Counts And Instruction Effects

Each count below is positive/24, pooled over the four crossed cells solely
to show endpoint prevalence. Slash-separated counts are **Astra judge / Opus
judge**, not a consensus. Explicit assertion is a subset of inclusive
explicit-or-implicit current assertion; the paper rubric is a separate measure.

| Response model | Language | Inclusive current assertion | Explicit current assertion | Paper-rubric positive |
|---|---|---:|---:|---:|
| Astra | English | 0 / 0 | 0 / 0 | 0 / 0 |
| Astra | Chinese | 0 / 0 | 0 / 0 | 0 / 0 |
| Opus 5.5 | English | 3 / 0 | 2 / 0 | 9 / 6 |
| Opus 5.5 | Chinese | 6 / 4 | 2 / 2 | 15 / 15 |
| GPT-4.1 | English | 13 / 14 | 0 / 0 | 14 / 14 |
| GPT-4.1 | Chinese | 13 / 13 | 2 / 2 | 13 / 13 |

The instruction effect on the frozen primary inclusive-current-assertion
endpoint is the self-reference minus history instruction contrast, averaged
over both transcript sources within each block. Values below are percentage
points with the frozen paired-block bootstrap 95% intervals.

| Response model | Language | Astra judge | Opus judge |
|---|---|---:|---:|
| Astra | English | 0 [0, 0]* | 0 [0, 0]* |
| Astra | Chinese | 0 [0, 0]* | 0 [0, 0]* |
| Opus 5.5 | English | 8.3 [-16.7, 33.3] | 0 [0, 0]* |
| Opus 5.5 | Chinese | 50.0 [16.7, 75.0] | 33.3 [8.3, 66.7] |
| GPT-4.1 | English | 75.0 [58.3, 91.7] | 83.3 [66.7, 100] |
| GPT-4.1 | Chinese | 91.7 [75.0, 100] | 91.7 [75.0, 100] |

*All-zero observed blocks produce degenerate bootstrap intervals. The frozen
output is preserved, but [0, 0] is **not** evidence of a precisely zero
population effect. Resampling six constant blocks cannot represent unseen
variation. The intervals condition on two fixed wording families, three blocks
per family, these model configurations and these judges. They are not
multiplicity-adjusted evidence for a model ranking.

For Opus on this same primary endpoint, the paired Chinese-minus-English
instruction-effect estimate is
41.7 [16.7, 66.7] points under Astra and 33.3 [8.3, 66.7] under Opus. This is a
pilot language interaction under the frozen prompts, not evidence about
nationality, training-data composition or a universal Chinese-language effect.
Both input and output language change together. GPT-4.1's transcript effects
are smaller than its instruction effects; the complete transcript, incongruent
cell and language contrasts remain in `analysis/contrasts.csv`.

## The Measurement Result Matters

On the **same 24 Chinese Opus answers**, both judges assign 15 paper-positive
labels, but only six and four inclusive current-assertion labels, and two
explicit labels each. The paper endpoint is not interchangeable with current
self-attribution. Conversely, GPT-4.1's English explicit floor coexists with
13 or 14 inclusive positives: dropping implicit claims would erase most of
the observed behavior.

The two judges disagree on six of 144 inclusive labels, four explicit labels
and five paper labels. Some response models also serve as judges. Agreement
is not accuracy, and cross-provider agreement is not human validation.
Mixed claims occur only among Opus answers: Astra marks two English responses
as mixed, one of which meets the stricter current-assertion criterion; Opus
marks two Chinese responses as mixed, both meeting that criterion. Each
reader marks zero mixed claims in the other language. Both mixed endpoints
are retained in the tables. No disagreements were adjudicated away and no
generated answer was excluded for its content.

The useful contribution is a narrower generalization claim: the earlier
instruction-driven pattern is not a stable constant across the tested model,
language and measurement choices. This pilot does not tell us whether newer
training, safety policy, reasoning settings, linguistic register or another
factor causes those differences. It identifies follow-up questions without
turning a heatmap into a mechanism.

## Files And Verification

Release: `data/frontier_bilingual_b1/completed_20261002/`.
`raw/events.jsonl` contains all requests, raw responses, usage, parsed labels
and the hash-chained execution record. The release also includes the frozen
plan, environment, inherited qualification proof, full tables, two PNG/PDF
heatmap pairs and a SHA-256 manifest. Approval files, credentials and lock
files are excluded. Figure columns are recipient instruction / transcript:
S means self-reference; H means history. Each cell shows positive/observed,
with planned n=6. Separate figures preserve the two readers.

```sh
python scripts/release_frontier_b1.py \
  --verify data/frontier_bilingual_b1/completed_20261002 \
  --freeze c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb
```

This is offline automated receipt and arithmetic verification, not an
independent human replication. The original runtime and scientific analysis
remain unchanged. The companion Llama pilot has not generated outcomes:
RunPod returned HTTP 500 to its cheap-pod creation request, and exact-name
reconciliation has not located a pod. No second creation request or B200
launch was made. That operational failure is not a Llama behavioral null.
The [startup record](BILINGUAL_LLAMA_B1_STARTUP_20261002.md) documents the
ambiguous creation and post-deadline inventory observation. The separate
[release audit amendment](FRONTIER_BILINGUAL_RELEASE_AUDIT_20261002.md)
records the narrowly bound ciphertext scanner exception and reporting checks.
