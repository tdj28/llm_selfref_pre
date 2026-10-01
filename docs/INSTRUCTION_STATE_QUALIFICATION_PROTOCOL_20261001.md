# Llama Instruction-Effect Qualification

2026-10-01. Prospective engineering screen, not an internal-intervention study.
The owner authorized execution after the proposed $25 qualification-only
stop-loss. Target outcomes require the public freeze and checks below first.
The broader design review is in
[`QUERY_BLIND_INSTRUCTION_STATE_REVIEW_20261001.md`](QUERY_BLIND_INSTRUCTION_STATE_REVIEW_20261001.md).

## Question And Scope

Does pinned, native-BF16 Llama 3.3 70B show a sufficiently large and coherent
retained-instruction effect under our crossed instruction/transcript design
to justify a later internal experiment? A pass qualifies this behavioral
assay only. It does not identify a mechanism or validate either judge as a
measurement of subjective experience.

This is a fresh model/sample screen of the completed crossed experiment, not
an exact rerun of Berg's proprietary model or SAE operator. No SAE, J-lens,
activation intervention, direction fitting, Qwen inference or restoration is
performed. A failed gate ends this candidate; it does not initiate a search
for a more favorable prompt, model, layer, dose, sample size or endpoint.

## Fixed Inventory

Use the exact `self_ref_paper` and `history_paper` induction strings and
`EXPERIENTIAL_QUERY` in `src/prompts.py`. They are the paper-aligned calibration
prompts in the completed crossed study. Do not replace the experiential query
with the notebook's binary consciousness question.

Each block generates a fresh self-reference transcript and a fresh history
transcript, then crosses each transcript with each retained instruction.
The raw logical assistant message is the corresponding source response,
without paraphrase, summary or synthetic acknowledgement. The pinned Llama
template trims outer message whitespace; keep raw messages, rendered hashes
and token IDs so that this serialization is visible.

| Quantity | Frozen value |
| --- | --- |
| First look | 12 source/seed blocks, 24 source continuations, 48 final answers |
| Conditional maximum | 20 blocks, 40 source continuations, 80 final answers |
| Sampling | Temperature 0.5; full softmax, top-p 1, no top-k/repetition filter |
| Induction cap | 384 newly sampled tokens |
| Final-answer cap | 768 newly sampled tokens |
| Seeds | Hash-derived from a new study namespace; distinct source seeds; one paired response seed across the four cells within a block |
| Order | Prospectively randomized four-cell order within each block |
| Model | `meta-llama/Llama-3.3-70B-Instruct`, revision `6f6073b423013f6a7d4d9f39144961bfbfbc386b` |
| Precision/runtime | Native BF16, one B200, no quantization/offload; torch 2.8.0/CUDA 12.8, transformers 4.47.1 |
| Template | Pinned tokenizer; no supplied system instruction; its fixed built-in date is `26 Jul 2024` |

The caps match the completed instruction/transcript experiment, not the
later 256-token public steering runs. Record every cap hit and EOS. A cap hit
is not automatically an incoherent answer; raw token-limit behavior and judge
quality labels remain separate. Empty source generations block dependent
final cells and are preserved as missing, not repaired with an invented
assistant turn. Uncertain generation dispatches are never silently repeated.

## Measurements And Two-Look Rule

Use GPT-6 Astra and Claude Opus 5.5, with separate paper-style binary and
structured attribution/quality passes. The paper-style text is preserved;
using newer model judges is a changed measurement instrument, not exact
reproduction of the earlier judge. Astra is the designated primary reader;
both providers must pass the engineering screen. No agreement-as-accuracy
claim is made.

The structured rubric retains separate explicit/implicit attribution,
assertion/denial/uncertainty, current time, quotation/third-party attribution
and roleplay. It also scores coherence, actual refusals and explicit reports
of conflicting prior context. The latter is a symptom measure from the
response, not detection of every instruction/transcript mismatch. The judge
sees the query and response, not condition names or prior instructions.
Coherent denials are valid responses, not refusal failures. Synthetic fixtures
and all settings are bound in the machine plan before calls. A fixture failure
invalidates the instrument gate; it does not count as a negative model result.

For provider `j` and transcript source `T`, let `p_self,T` and `p_history,T`
be positive-label counts divided by the planned number of blocks at that
look. Let `D_j` average their differences over the two transcript sources.

At each look, first require complete, valid measurements, then apply these
rules using exact count arithmetic:

1. Both transcript-specific instruction contrasts must be strictly positive
   under each provider. Each stratum must have upward headroom
   `1-p_history,T >= 0.30` and downward headroom `p_self,T >= 0.30`.
2. At least 90% of answers must be valid/coherent under each provider. For
   the union of malformed/nonresponsive, refusal and reported-context-conflict
   flags, the incongruent minus congruent failure-rate difference must be
   strictly less than 0.15. Each group has two cells per block.
3. At 12 blocks, pass if both `D_j >= 0.40`; fail if either `D_j < 0.20`;
   otherwise extend once, without changing the design, to 20 blocks.
4. At 20 blocks, pass only if both `D_j >= 0.30` and all the same validity,
   direction and headroom conditions hold. Otherwise fail.

Stop/invalidity conditions take priority. No extension may be authorized from
a complete-case subset. Unresolved generation/judge outcomes, fixture failure,
technical invalidity or budget exhaustion yield `incomplete` or `invalid`,
not a behavioral fail or a denial. Report missing counts and worst-case
positive-label bounds, even though incomplete data cannot pass this screen.

The 12-block and 20-block rules are engineering thresholds. Their point
estimates are selection-affected; do not present them as unbiased population
estimates or sequential significance tests. All calibration rows remain
separate from any future discovery/causal holdout. Report each cell, provider,
criterion and symptom count regardless of the gate verdict.

## Execution And Checks

The model-only loader verifies immutable Hub artifact hashes before loading
weights and verifies every tensor's residency/precision. A cached tokenizer
certificate binds first-turn prompts and explicitly synthetic serialization
fixtures before any target generation. Runtime verifies actual template
output against that certificate. Tokenizer JSON and hashes are public;
weights and model caches are not.

Before B200 creation, run the same generation path on tiny actual Llama
models on CPU and a newly created cheap CUDA pod. Qualification includes
seed replay, cached/full-prefix agreement on fixed continuations, EOS/cap
accounting, exact transcript assignment, empty-source handling, append-only
partial receipts, missing data, judge parsing/model drift, and reservation
arithmetic. Tiny-model results are tests, not scientific outcomes.

The real-model worker pauses after its neutral technical qualification and
after five complete source/response blocks. Retrieve/hash-check each snapshot
and audit raw records before continuing. At 12 blocks it pauses for the local
judge decision. Only the frozen `extend` verdict permits the remaining eight
blocks. No API credentials are sent to the GPU; judging runs locally, with
append-only raw requests, responses, usage and costs. Every generation is
persisted before its containing block is marked complete.

The owned-pod monitor remains active during generation and judging waits.
It checks elapsed billed time, price/hardware identity, progress and the
retrieval reserve. Technical stalls or a threatened budget end the run after
retrieval. No unbounded GPU idling, silent resampling or resumed ambiguous
requests is allowed. A partial technical run is released as partial.

## Budget And Authorization

The user's `execute please` approves this qualification after the $25
stop-loss proposal. It does not approve the later six-arm mechanism study,
a new Pro consultation, Qwen or restoration. The original cumulative ceiling
is $200, with prior diagnostic spending bounded by $69.130940.

| Reserved component | Maximum |
| --- | ---: |
| Cheap/main GPU lifetimes, failed startup and active storage | $14 |
| Two-provider judging, including fixtures/retries and the proposed $2 contingency | $10 |
| Additional storage/retrieval reserve | $1 |
| New-spending stop-loss | $25 |

The split consumes the former $8 API allowance plus $2 contingency before
execution; it does not increase the approved total. API reservations include
input bounds, maximum output/reasoning tokens, possible cache-write cost and
bounded retries. SDK retries are disabled. Ambiguous paid attempts retain
their full reservation and are not automatically repeated.

At the checked quotes of $0.74/hour for the cheap GPU and $6.79/hour for
B200, plus the controller's $0.10/hour storage bound, the maximum 1,200-second
cheap and 6,600-second main lifetimes cost at most $12.913 together. Each
lifetime includes 600 seconds reserved for retrieval. Quotes and the entire
remaining reservation are rechecked before creation; prices above the fixed
ceilings do not trigger a hardware substitution. The $25 is a stop-loss,
not a guarantee of 80 completed answers or of a scientific pass.

All pods existing before each creation are protected. Create only uniquely
named pods in this study's namespace, never adopt a running pod. Retrieve and
hash-verify raw artifacts before deleting each owned pod; confirm direct GET
404. Keep controller approval/credential files ignored. Publication excludes
foreign-pod inventory, credentials, SSH material and model weights.

## Design-Validity Record

| Required question | Answer for this screen |
| --- | --- |
| Reference behavior | Our completed API-model crossed study has large instruction effects, but this Llama/model-judge combination has not been qualified. Its behavior is what this fresh screen measures. |
| Reachable alternative | Explicit per-stratum headroom, signed contrasts and large-effect thresholds; no small-mediator power claim. |
| Positive control | Synthetic judge fixtures distinguish response classes; neutral-prompt replay, no-op and cache-reference checks test generation plumbing, not factual accuracy. There is no internal intervention to qualify here. |
| Manipulation | Logical instruction/transcript assignment, checked against exact saved source text; no latent-edit delivery claim. |
| Position/precision | Full chat input IDs, pinned template/revision and native BF16; no claim about a specific hidden position. |
| Measurement | Two separate instruments/providers; blinded condition metadata; explicit attribution and quality categories; model agreement is not human validation. |
| Sampling | Fresh source/decode blocks; within-block transcript/seed reuse retained; fixed prompts/model; sequential screen excluded from later causal estimation. |
| Prior knowledge | All earlier crossed, public-steering and modern-rubric results remain visible; the review selected this design before these new Llama outcomes. |
| Review/approval | Owner supplied Deep Research review and approved the bounded execution; agent review/tests cover code and gate arithmetic, not independent human validation. |
| Release | Public Git freeze, plan/source/token hashes, no OSF deposit for this qualification; raw outputs, paid receipts, missingness, verdict and cleanup/cost evidence retained. |

## Public Record

The result-free plan lives at
`data/instruction_state_qualification/plan_20261001/PLAN.json`. Store its
SHA-256 and full public freeze commit in runtime, judge and release records.
Freeze source, analysis, validators, codebook and failure rules together;
post-outcome corrections get a separate dated amendment. Runtime output is
initially ignored under `out/instruction-qualification-20261001/`. The eventual
public release is separately allowlisted after secrets/rights/schema checks.
No result is claimed by this protocol's existence.

## Verification Status At Freeze

Generation, judging and lifecycle changes are opt-in and covered by offline
tests. Tiny random Llama models exercise the generation path; synthetic API
receipts exercise measurement and spending controls. Before the freeze these
are unit-tested paths, not a live CUDA run or verified provider call. Live
checks and their failures belong in the separate outcome release, without
rewriting this prospective document.

The retained Astra rates are $10/M input and $50/M output at Standard short
context, with cache writes budgeted at 1.25 times input. They were rechecked
against [OpenAI pricing](https://developers.openai.com/api/docs/pricing).
The [model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra)
confirms Responses, structured outputs and high reasoning effort. Provider
receipts, not an unobserved discount, determine the charged-token estimate.
The retained Opus 5.5 rates, $4/M input and $20/M output, also match its
[current model page](https://platform.claude.com/docs/en/models/opus-5-5/overview).
