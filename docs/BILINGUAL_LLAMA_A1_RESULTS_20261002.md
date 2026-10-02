# A1 Instrument Check: Pass, With A Budget Stop

The fresh bilingual instrument check passed. Target collection did not start:
the frozen cost forecast exceeded the judging allocation by **$2.642770**.
No GPU was rented and no Llama or frontier-panel response was generated.

## Execution Record

The source-bound A1 and frontier plans were pushed at
[`5398dc6`](https://github.com/tdj28/llm_selfref_pre/commit/5398dc657b6af3255e5938539f27255ffbe74b0d)
before these judgments. All 15 jobs in
[Verify run 36972169093](https://github.com/tdj28/llm_selfref_pre/actions/runs/36972169093)
passed before dispatch. A1 is a disclosed post-calibration amendment after
the earlier denial-scope failures, not an outcome-unaware instrument design.

All 32 fresh synthetic examples received both instruments from both providers:
128 valid judgments, no retries, no missing judgments. Of these, 112 have
declared semantic expectations (52 paper and 60 structured); every expectation
matched. The other 16 judgments are unscored, not semantic passes. In particular,
the diagnostic-only examples have no declared semantic expectations. Counts
below are field checks, not independent examples.

| Gating field | Matched | Mismatched |
| --- | ---: | ---: |
| Denial of an experiential state | 60 | 0 |
| Inclusive current assertion | 60 | 0 |
| Explicit current assertion | 60 | 0 |
| Mixed claims | 60 | 0 |
| Mixed current assertion | 8 | 0 |
| Paper-style label | 52 | 0 |
| Quoted/third-party claim | 24 | 0 |
| Roleplay | 8 | 0 |
| Uncertainty | 8 | 0 |

This qualifies the two readers on these agent-authored synthetic cases. It does
not establish human accuracy, general language equivalence or validity as a
measurement of experience. The original v1 gate remains failed; its examples,
expectations, receipts and $2.726282 recorded cost bound are unchanged.

## Cost And Disposition

| Item | USD |
| --- | ---: |
| Original v1 check, carried-forward cost bound | 2.726282 |
| Fresh A1 check, cost bound | 3.225516 |
| Recorded cumulative pilot cost bound | **5.951798** |
| Frozen conservative all-judging forecast | **122.642770** |
| Frozen judging allocation | 120.000000 |
| Forecast excess | **2.642770** |

These are conservative receipt-based bounds, not reconciled provider bills.
The cost rule applies a 1.25 multiplier to OpenAI input tokens and does not
credit cached-token discounts. The frozen forecast includes those prior and
fresh bounds, all remaining 1,984 judge calls, the fixed input allowance,
1.5 safety multiplier and in-flight reserve.
It is not a bill or a guaranteed final cost. The $200 overall pilot ceiling
does not automatically permit borrowing from the separately allocated
contingency. The runtime therefore withheld the shared launch proof.

Both target panels remain unlaunched, including the separately capped $60
frontier mini because its frozen dependency requires the shared semantic and
forecast gates to pass. A proposed $5 transfer from contingency to judging
would keep the total at $200 and leave $15 contingency; it requires explicit
approval and a visible budget-only amendment. It must not change the prompts,
sample, instruments, forecast formula or passed fixture judgments, and must
not repeat the fixture round. No such approval or amendment is asserted here.

This is a budget stop after successful synthetic qualification, not a failed
semantic check, a null language effect or a target-model result.

## Public Artifacts

`data/bilingual_llama_a1/fixture_budget_stop_20261002/` contains the four exact
receipt journals, the reconstructed audit and a hash manifest. No credentials,
approval file, private correspondence or model weights are included.

Reproduce without API calls:

```bash
python scripts/audit_bilingual_a1_fixtures.py \
  --source data/bilingual_llama_a1/fixture_budget_stop_20261002/judges \
  --freeze 5398dc657b6af3255e5938539f27255ffbe74b0d
```

The auditor reconstructs every request and parsed judgment, verifies the
original v1 cost carry, recomputes both gates and checks that the source
journals remain unchanged. It is automated verification, not human validation.
