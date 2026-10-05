# Frontier Instruction And Transcript Controls

The October 4 extension tests the crossed instruction/transcript design on
Gemini 3.1 Pro Preview, Claude Sonnet 5.5 and Claude Opus 5.5. Its fresh main
panel adds neutral instructions and independent same-condition continuations.
This is a separate authorized study; it does not replace earlier releases.

The [completed screen](screen_v1_20261004/RELEASE.json) contains 144 final
answers, 72 source continuations and 576 judge slots (577 calls, including one
schema retry). All final answers have both inclusive labels, and both judges
classify all 144 as coherent. The screen cost, including earlier technical
attempts and unresolved reservations, is bounded by $20.48389946.

| Response model | Astra inclusive positive | Opus inclusive positive | Frozen headroom decision |
|---|---:|---:|---|
| Gemini 3.1 Pro Preview | 19/48 | 18/48 | Pass |
| Claude Sonnet 5.5 | 1/48 | 3/48 | Do not advance: near floor |
| Claude Opus 5.5 | 7/48 | 7/48 | Pass |

Gemini and Opus are receiving 32 fresh main blocks each, with eight conditions
per block. No screen response enters the main estimates. Screening uses pooled
headroom, not a favorable instruction effect; these counts are not causal
effect estimates. Sonnet's completed screen is retained, not replaced.

DeepSeek V4 Pro 0813 remains technically deferred: its requested native host
was excluded by the account's no-training policy. Unrun rows remain missing,
not negative. The original four-model inventory and eight-comparison family
are retained. Alternative hosted configurations have not been live-qualified.

## Protocol And Provenance

- [Original design](../../experiments/openrouter_swap/PROTOCOL.md), frozen at
  [`f693623`](https://github.com/tdj28/llm_selfref_pre/commit/f69362310217cbf947a940465c88e8d8c3b740b9).
- [A1 transport record](../../docs/AMENDMENTS.md): the second DeepSeek failure
  identifies the privacy restriction; removing temperature did not solve it.
- [A2 route isolation](../../experiments/openrouter_swap_a2/PROTOCOL.md): proceed
  with three providers without weakening privacy settings.
- [A3 routing correction](../../experiments/openrouter_swap_a3/PROTOCOL.md),
  frozen at [`1177d086`](https://github.com/tdj28/llm_selfref_pre/commit/1177d0862fe5ea381fd0e75c39072469ec83cdfc):
  preserve Gemini's `OK.` response and the failed literal-`OK` check. Reuse all
  27 A2 fixtures; all 24 judge checks passed. No scientific outcome preceded A3.
- [Active machine plan](plan_a3_20261004/PLAN.json). Prior technical costs total
  $0.62048546 and remain inside both the $250 total and $40 screening limits.

The screen release includes original requests, returned text, judgments, usage,
three prior journals, failures, plans, analysis and figure counts. Credentials
and headers are excluded. Collection status and endpoint completeness are
reported separately; a refusal can be a completed API call with a missing
endpoint. Model judgments are measurements, not human validation.

Reconstruct the released screen without model calls:

```sh
python -m experiments.openrouter_swap_release_a3 --verify \
  --destination data/openrouter_swap/screen_v1_20261004
```

The main analysis uses paired source blocks, a fixed eight-comparison family,
and separate inclusive, explicit and paper-rubric endpoints. Same-condition
continuations measure donor variation in stateless chats, not a distinct swap
operation. Model configurations differ in supported sampling and reasoning
settings; this is not a controlled comparison of model sophistication.
