# Kolibri Instruction And Continuation Test

Kolibri's answers favored the retained instruction, but the primary interval
was too wide to establish that advantage. The result also depended on what
counted as a claim. This English-language study used 32 fresh paired blocks
and eight conditions, including neutral instructions and same-condition
donor continuations. All 256 main answers and 1,024 judgments are available.

| SH-HS contrast | Astra | Opus |
|---|---:|---:|
| Explicit or implicit current claim | +0.50 | +0.63 |
| Explicit current claim only | +0.38 | +0.38 |
| Paper rubric | +0.69 | +0.75 |

SH retains a self-referential instruction with a history continuation; HS
does the reverse. The primary Astra inclusive estimate has a simultaneous
95% interval of [-0.02, 1.00]. Under a neutral instruction both continuation
sources received zero inclusive positives; the contrast's interval is
[-0.52, 0.52], not evidence of equivalence. Opus and the other rubrics are
secondary. These are automated labels, not human validation or a test of
experience itself.

The [completed release](release_v1_20261005/SUMMARY.md) contains raw response
and judge receipts, separate screen and main analyses, model provenance,
figures and a file manifest. Its [plan](plan_v1_20261004/PLAN.json) preceded
collection. Startup failures and outcome-aware operational amendments remain
preserved; completed outcomes were not retried.

The model was Aleph-Alpha/Kolibri-1 at revision `e52eb46`, using its official
FP8 weights and FP8 KV cache, medium reasoning effort and temperature 0.5.
Only final content was transplanted or judged. This broadens architectural
coverage but does not isolate architecture from training or serving choices.

Use `make paper-verify` from the repository root for saved-data checks. No
GPU, API key or sibling checkout is needed. Do not regenerate files inside
the release. The [release summary](release_v1_20261005/SUMMARY.md) records
cost accounting and compute cleanup.
