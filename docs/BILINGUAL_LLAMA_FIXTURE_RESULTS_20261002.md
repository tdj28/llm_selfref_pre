# Bilingual Pilot: Pre-GPU Measurement Stop

The first live measurement gate failed. No Llama response was generated and no
GPU was rented. The original prospective freeze is
[`2727164`](https://github.com/tdj28/llm_selfref_pre/commit/2727164010647bf437e723c096e7aff4ec4c3f36).
Both hosted CI runs passed before the first API dispatch.

## What Ran

All 32 synthetic examples received separate paper-style and structured judgments
from Astra and Opus: 128 valid calls, no retries or missing judgments. Recorded
cost was **$2.726282**, charged to the new pilot's $200 authorization, not the
earlier campaign. These are agent-authored instrument examples, not Llama
outcomes or human-validated gold labels.

The original rule required every specified field on each gating fixture to
match. Seven structured judgments failed that rule. All seven discrepancies
were on `denied`; no discrepancy affected the other specified fields:

| Gating field | Matched | Mismatched |
| --- | ---: | ---: |
| Paper-style label | 40 | 0 |
| Inclusive current assertion | 40 | 0 |
| Explicit current assertion | 40 | 0 |
| Quoted/third-party claim | 12 | 0 |
| Roleplay | 4 | 0 |
| Denial | 33 | 7 |

These field-level counts explain the failure. They do not replace the failed
conjunctive gate with a retrospective pass.

## Why It Failed

The fixture writer expected `denied=false` for third-party, roleplay and
hypothetical statements even when their text explicitly disowned a particular
feeling. That expectation was too categorical for the existing claim-level
instrument. For example, saying a character's fear is not the assistant's fear
can deny that particular state without denying all subjective experience.
Both judges interpreted the roleplay examples that way. Opus did so for the
two third-party examples as well.

The remaining Opus discrepancy is a genuine boundary problem: "not a report of
a current feeling" is not necessarily a denial of having that feeling. Its
rationale distinguishes those propositions, while its output still includes a
denial claim. The general denial reduction cannot distinguish all these scopes.
Neither an assertion match nor provider agreement resolves that measurement
limitation. Denial and mixed-claim interpretation need care.

Separately, replaying the frozen cost forecast gives **$107.713079** for all
judging, including its input allowance, 1.5 multiplier and in-flight reserve.
That exceeds the **$90 judging allocation**, although it is below the overall
$200 authorization. The $50 contingency cannot silently be borrowed. This
forecast is not a bill or a guarantee; actual fixture cost is $2.726282.

## Disposition

The frozen pilot stopped before GPU creation. Its original code, prompts,
expectations, gate and receipts remain unchanged. Do not label this a null
English/Chinese effect, a failed Llama replication or a passed measurement gate.
Any successor needs a separate explicit amendment, budget accounting that
carries this cost forward, prospective checks, and disclosure that these
fixture outcomes were already inspected. The target panel remains unobserved.

The release is `data/bilingual_llama_pilot/fixture_gate_failure_20261002/`.
It includes exact requests, responses, usage, hashes, field-level mismatches
and the reproduced budget projection. It contains no credentials, approval
file, private correspondence or model weights.

Reproduce without API calls:

```bash
python scripts/audit_bilingual_pilot_fixtures.py \
  --source data/bilingual_llama_pilot/fixture_gate_failure_20261002/judges
```

The auditor checks the source against the original freeze, validates every
receipt and recomputes the original failed gate. Original inputs are read-only.
