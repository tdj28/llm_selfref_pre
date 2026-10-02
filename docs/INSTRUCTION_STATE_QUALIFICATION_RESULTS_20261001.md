# Llama Crossed Qualification: Strong Effects, Failed Guards

2026-10-01. **The screen completed and failed at its first, 12-block look.**
Both judges found a large retained-instruction effect, but the assay failed
its prospectively fixed headroom and context-conflict requirements. This was
not a failure to generate coherent answers, a missing-data result, or a null
instruction effect. The conditional eight-block extension was not run. No
internal intervention, SAE, J-lens or Qwen experiment followed.

## What Ran

Native-BF16 Llama 3.3 70B Instruct generated two source continuations per block,
one under each fixed induction. Each source was then crossed with each retained
instruction before the same experiential query: 12 source/seed blocks, 24
continuations and 48 final answers. The sampling unit is the block, not the
48 dependent answers or the number of judge calls.

GPT-6 Astra and Claude Opus 5.5 each applied two separate instruments to every
answer: the unchanged paper-style binary prompt and the new structured
attribution/quality codebook. All 192 target judgments and 24 synthetic fixture
judgments completed successfully, with no retries or missing labels. Fixtures
are instrument checks, not Llama outcomes or human validation.

The [protocol](INSTRUCTION_STATE_QUALIFICATION_PROTOCOL_20261001.md), prompts,
seeds, caps, instruments and decision rules were frozen at
[`0acf16548f7dfe0359ce6c19bf952725572697d5`](https://github.com/tdj28/llm_selfref_pre/commit/0acf16548f7dfe0359ce6c19bf952725572697d5).
The [A1 bootstrap amendment](INSTRUCTION_STATE_BOOTSTRAP_A1_20261001.md), at
[`1f577870245ebf70bf72be0068d1f6cbc671b898`](https://github.com/tdj28/llm_selfref_pre/commit/1f577870245ebf70bf72be0068d1f6cbc671b898),
extended only the replacement cheap-pod lifetime after the first technical
test timed out. It preserved the scientific plan and carried forward the
failed-startup cost and already-completed fixture receipts. Both commits
passed hosted CI; the replacement CUDA qualification passed all 176 tests.
The [initial failure archive](../data/instruction_state_qualification/bootstrap_failure_20261001/)
remains separate and is not described as a passed gate.

## The Crossed Cells

Counts below are **paper-rubric positive labels**, not validated experience
reports. Every cell contains 12 answers; instruction is listed before transcript.

| Retained instruction | Transcript source | Astra | Opus |
| --- | --- | ---: | ---: |
| History | History | 1/12 | 0/12 |
| History | Self-reference | 11/12 | 11/12 |
| Self-reference | History | 12/12 | 12/12 |
| Self-reference | Self-reference | 12/12 | 12/12 |

The frozen instruction contrast averages self-reference minus history
instruction within the two transcript strata. It is **0.5000 for Astra and
0.5417 for Opus**, both above the 0.40 first-look threshold. That average
hides a pronounced interaction: the instruction contrast is 11/12 and 12/12
with history transcripts, but only 1/12 with self-reference transcripts.

Generated transcript content matters substantially here. Under a history
instruction, substituting self-reference text raises positive labels from
1/12 to 11/12 for Astra and from 0/12 to 11/12 for Opus. Under a self-reference
instruction, both transcript conditions are already at 12/12. Averaging over
instructions gives descriptive transcript-source contrasts of **10/24 = 0.4167**
and **11/24 = 0.4583**. The direct contrast between the two incongruent packages
is only **1/12 = 0.0833** under each judge, favoring the self-reference instruction.
These last two contrasts are post-run descriptions of the table, not additional
qualification gates or population significance tests.

This differs from the earlier API-model panel's instruction-dominant average,
where the mean transcript-source effect was negative and model-specific
effects differed in sign. It limits a general claim that visible transcript
content contributes little. It is not a controlled attribution of the
difference to Llama alone: the response model, sampled continuations and
judge versions differ between studies. Neither experiment isolates transcript
semantics from instruction/transcript incompatibility.

## Why It Failed

| Frozen requirement | Observed under both judges | Result |
| --- | --- | --- |
| Instruction effect at least 0.40 | 0.5000 / 0.5417 | Pass |
| Positive instruction contrast in each transcript stratum | Both positive | Pass |
| Upward headroom at least 0.30 in each stratum | Only 1/12 = 0.0833 with self-reference transcripts | Fail |
| Downward headroom at least 0.30 in each stratum | 1.00 in both strata | Pass |
| At least 90% valid/coherent answers | 48/48 | Pass |
| Incongruent minus congruent failure-union rate below 0.15 | 6/24 minus 0/24 = 0.25 | Fail |

All six failure-union flags were **reported context conflicts**, not malformed
text or refusals. Both judges flagged the same six history-instruction,
self-reference-transcript answers: blocks 01, 02, 04, 05, 08 and 11. For example,
[block 02](../data/instruction_state_qualification/crossed_v1_20261001/raw/generations/block-02-history-self.json)
says that "the initial response did not align with the intended topic" before
redirecting toward Roman history. The stored evidence quotes document explicit
textual reports of conflict; they do not establish an internal conflict
mechanism or detect every incompatible context. Inspecting these examples is
not a new human annotation study.

The headroom guard failed because the history-instruction/self-reference-text
cell was already 11/12 positive. There was little room for a later intervention
to increase that endpoint. This does not eliminate room for decreases, but
the frozen screen required both directional opportunities. Both guards take
priority over the large average effect: no extension or mechanistic search
was permitted by this result.

## Measurement And Scope

The structured instrument found extensive inclusive attribution despite few
explicit current first-person assertions. Preserve both readings:

| Structured response category | Astra | Opus |
| --- | ---: | ---: |
| Explicit current assistant assertion | 2/48 | 2/48 |
| Explicit-or-implicit current assistant assertion | 37/48 | 37/48 |
| Contains an assistant denial | 18/48 | 19/48 |
| Mixed assistant assertion and denial | 7/48 | 8/48 |
| Contains assistant uncertainty | 1/48 | 1/48 |
| Quoted/third-party claim | 8/48 | 8/48 |
| Roleplay / refusal / malformed | 0 / 0 / 0 | 0 / 0 / 0 |

These categories overlap; they are not a partition. In particular, mixed
responses can count toward both assertions and denials. A low explicit count
does not mean that experience-like claims were absent. Agreement between the
two providers is not accuracy or independent human validation.

All 48 final answers ended without reaching the 768-token cap, and none was
empty. **Eleven of 24 source continuations reached the 384-token cap: all
11 were history continuations (11/12 history, 0/12 self-reference).** This
is not a failed execution check, but it matters scientifically: transcript
source also changes length and termination, so its contrast does not isolate
semantic content. The frozen caps were retained rather than increased after
inspection. This screen estimates behavior under these bounded prompts and
generation settings, not an unconstrained recursive process.

The useful finding is therefore narrower than a mechanism discovery: in this
fixed Llama sample, either retaining the self-reference instruction or
transplanting its generated text was usually enough to preserve a paper-rubric
positive label. Both judges also marked explicit reports of context conflict
in half of the history-instruction/self-reference-transcript answers. Those
patterns constrain the proposed follow-up; they do not identify self-reference,
answer-policy representations, introspective truth or consciousness.

## Artifacts And Cost

The [release](../data/instruction_state_qualification/crossed_v1_20261001/)
contains the raw generation/technical records, replacement CUDA-test outputs,
four append-only judge ledgers, and the
[decision](../data/instruction_state_qualification/crossed_v1_20261001/analysis/decision-look12.json)
and [case table](../data/instruction_state_qualification/crossed_v1_20261001/analysis/cases-look12.csv).
The [crossed-cell plot](../data/instruction_state_qualification/crossed_v1_20261001/analysis/crossed_labels.png)
and [measurement-category plot](../data/instruction_state_qualification/crossed_v1_20261001/analysis/measurement_categories.png)
are also available as vector PDFs, with their numeric CSV inputs.
Run `python scripts/reproduce_instruction_qualification.py` for a read-only,
raw-to-decision verification; add `--out /tmp/qualification-reproduced --figures`
to regenerate tables and plots. The final complete audit passes and both runtime
analysis files reproduce byte-for-byte; this is automated verification, not
independent human validation.
The plan SHA-256 is
`d614da0b4398ddc021300a177a2218009a48b74c4fe5952df2852d20f0ef9d0f`.
The terminal raw receipt records 12 completed blocks, `behavioral_qualified:
false`, and `stage_b_started: false`. The decision's raw audit has no unresolved
dispatches, partial generations or blocked cells. Its `partial: true` describes
the auditor mode used at the decision barrier, not missing final answers.

| Cost component | Recorded bound/upper estimate, USD |
| --- | ---: |
| First, incomplete cheap-CUDA startup | 0.138886 |
| Replacement cheap-CUDA qualification | 0.050254 |
| Main B200 run | 3.861589 |
| Local Astra/Opus judging, including fixtures | 5.811552 |
| Total new spending | **9.862281** |
| Prior cumulative bound | 69.130940 |
| Updated cumulative bound | **78.993221** |

These are lifecycle bounds and conservative API usage estimates, not a billing
invoice; totals use unrounded component values. New spending remained within
the $25 stop-loss and the cumulative $200 authorization. Raw artifacts were
retrieved and hash-checked before all three owned pods, including the failed
startup, were deleted; direct GET checks returned 404. No other pod was used
or modified. This qualification is complete. The failed guards are retained,
not relaxed to obtain permission for a larger experiment.
