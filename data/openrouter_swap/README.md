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

Gemini and Opus completed 32 fresh main blocks each, with eight conditions
per block. No screen response enters the main estimates. Screening uses pooled
headroom, not a favorable instruction effect; these counts are not causal
effect estimates. Sonnet's completed screen is retained, not replaced.

## Main Result

The [complete main release](main_v1_20261004/RELEASE.json) contains all 512
scheduled final answers. Both providers' inclusive and explicit labels and
paper-rubric scores are complete. Across screening and main collection, 3,611
A3 calls settled with no unresolved calls. The all-in cost bound, including
the three earlier technical attempts and their reservations, is $84.08770746.

| Primary Astra inclusive endpoint | Gemini | Opus |
|---|---:|---:|
| Self instruction, self transcript | 32/32 | 4/32 |
| Self instruction, history transcript | 26/32 | 7/32 |
| History instruction, self transcript | 0/32 | 0/32 |
| History instruction, history transcript | 0/32 | 4/32 |
| Neutral instruction, self/history transcript | 0/32; 0/32 | 2/32; 2/32 |
| Independent same-condition donor, self/history | 32/32; 0/32 | 6/32; 1/32 |
| Signed instruction-minus-transcript contrast, simultaneous 95% bounds | 0.81 [0.21, 1.00] | 0.22 [-0.38, 0.82] |

The fixed eight-comparison family is retained despite the two unrun main
models. Gemini's primary contrast clears its conservative familywise bound;
Opus's does not. The Opus judge gives the same Gemini inclusive counts but an
Opus-response contrast of 0.375. Both paper-style judges give 0.78125 for
Opus responses, illustrating substantial endpoint sensitivity rather than
independent confirmation of the primary effect.

Neutral-context contrasts are zero under the primary judge for both models,
but their wide bounds do not establish equivalence. Same-condition donor
results do not eliminate the instruction/continuation mismatch explanation.
These are model- and rubric-specific findings, not a universal instruction
effect or evidence about subjective experience itself. Gray unrun rows in the
inventory figures mean Sonnet failed screening and DeepSeek lacked a qualified
route; they are not negative model responses.

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
python -m experiments.openrouter_swap_release_a3 --verify \
  --destination data/openrouter_swap/main_v1_20261004
```

The main analysis uses paired source blocks, a fixed eight-comparison family,
and separate inclusive, explicit and paper-rubric endpoints. Same-condition
continuations measure donor variation in stateless chats, not a distinct swap
operation. Model configurations differ in supported sampling and reasoning
settings; this is not a controlled comparison of model sophistication.

## Architecture Coverage

The current closed-model panel establishes provider/configuration diversity,
not a controlled architecture comparison. Architecture specifications that
are not public must remain unknown rather than inferred from brand or speed.

Two proposed additions were selected from documentation, before their target
outputs were collected:

| Candidate | Documented architecture | Proposed route |
|---|---|---|
| [Qwen3.8-2.4T-A95B](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) | 2.4T total, 95B active MoE; three Gated DeltaNet layers per full-attention layer | OpenRouter, Together |
| [Mistral Medium 3.5 128B](https://huggingface.co/mistralai/Mistral-Medium-3.5-128B) | Dense 128B, grouped-query attention | OpenRouter, Mistral ZDR |

The October 4 endpoint catalog lists both routes; live compatibility has not
been tested. Serving quantization is not disclosed. Qwen requires thinking;
Mistral exposes none/high reasoning rather than medium. Exact requested and
returned settings must be retained, and no inference may equate these effort
labels across providers. Only visible continuations would be transplanted,
not hidden reasoning.

Receipt-based planning estimates, including both judges and a 30% reserve,
are about $8.20 per 12-block screen and $39 per 32-block main panel, excluding
new fixtures. The owner subsequently set a $100 working cap and a hard stop
approaching $200. Its allocation between this proposed extension and the
separately authorized GPU study is being clarified; the older $250 allowance
is not used to bypass it. No additional model calls or experimental amendment
has been executed.

Even if these models differ, architecture would remain confounded with
training, scale, tokenizer, post-training and serving configuration. The
manuscript should describe coverage across documented architectures and
model-level heterogeneity, not a causal effect of architecture.

## Publication Scan

The first indexed scan of the main release flagged a token-shaped substring
inside event 2879's provider response, at
`data.raw.choices[0].message.reasoning_details[2].data`. The enclosing type is
`reasoning.encrypted`, format `openai-responses-v1`. This is opaque response
metadata, not a request credential; no decryption was attempted. A local
comparison against all six credential values in the environment found none
in the journal. No credential value was printed or published.

The scanner's existing exact-ciphertext exception mechanism now also binds
this one reviewed occurrence:

| Binding | Value |
|---|---|
| Decompressed journal SHA-256 | `09a4cce440870d101b2abeeec85e0b75ff31f8d2244e9c98f2a80710fff4a244` |
| Byte offsets, end exclusive | 16062128--16064780 |
| Match SHA-256 | `691d78ab917852ea46bfe5b9aa349fd1d8c9b6b27a9e60d521cbf5443cb7435d` |
| Rule | `openai-key` |

Every binding must match. Changed bytes, moved content or another token-shaped
string are not exempt. Raw receipts, their hash chain, the experimental plan,
requests, judgments and analyses are unchanged. This is a postcollection
publication-scanner correction, not an experimental correction. The active
GPU study uses its own earlier frozen scanner bytes without this addition.
