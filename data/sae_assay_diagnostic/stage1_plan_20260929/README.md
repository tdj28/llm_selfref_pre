# Stage 1 Assay Plan

This is an outcome-free execution plan, not a result bundle. The owner approved
overnight execution on 2026-09-29 after correction of the paid Pro findings,
within $200 including that review. The executable freeze was prepared on
2026-09-30. No new GPU or experimental API calls preceded this freeze.

`PLAN.json` SHA-256:
`2c7d5d53cfca49757db5a4304c83f8234b34ea3cb405ef621d0b2f1e0544d970`.

The plan binds 19 source files, 96 teacher texts, 12 judge fixtures, 80 core
baseline responses, 210 conditional baseline responses, and an eligible
20-task/four-arm formatting diagnostic. Its full branch inventory contains
3,009 possible row IDs; this is not a promise or requirement to execute every
conditional row. In particular, validation and optional panels remain gated.

Protocol: `docs/SAE_ASSAY_STAGE1_PROTOCOL_20260929.md`.
Prior review: `reviews/sae_assay_pre_spend_20260929/`.
Prior review cost upper bound: $0.86461. Stage 2 is not authorized.

The preflight receipt records CPU tests only. CUDA and actual 70B gates must
still pass in order. These are automated implementation checks, not independent
human scientific validation or evidence that any semantic intervention works.
