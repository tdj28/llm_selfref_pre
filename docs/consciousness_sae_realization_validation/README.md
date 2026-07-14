# SAE realization-validation documents

Study ID: `consciousness_sae_realization_validation_v1`

Protocol version: `consciousness_sae_realization_validation_v1.0.0`

Status: **prospective draft; not executed; no results**

This directory documents a neutral, fixed-token validation of layer-50 SAE
edits and the Llama 3.3 70B Jacobian lens. It is a calibration study, not the
paper-prompt experiment, a behavioral replication, or a test of whether a
model is conscious.

The documents are:

- `PROTOCOL.md` — frozen-design intent, exact grids, gates, data contract, and
  claim boundaries;
- `REPRODUCING.md` — ordered execution and audit contract;
- `SMOKE_TEST.md` — the source-bound, target-free four-forward B200 operational
  smoke that runs before Stage A; and
- `PRO_REVIEW_CONTEXT_20260714.md` — bounded context and open risks for the
  prospective GPT Pro review.

The implementation is under
`experiments/consciousness_sae_realization_validation/`; local contract tests
are under `tests/consciousness_sae_realization_validation/`; compact plans and
receipts belong under `data/consciousness_sae_realization_validation/`.

Raw residuals, exact arithmetic tensors, vocabulary indexes, row-level
telemetry, and runtime logs remain on the RunPod network volume. They must not
be committed to Git or copied to the laptop. Git may contain source, tests,
prospective documents, the frozen machine plan, checksums, audit receipts, and
compact summaries.

The prior r15 result is disclosed as motivation but is not a computational
input. No prior result row, vector match, effect size, dose choice, or raw
artifact may enter this study. Pinned public model, SAE, and J-lens files may be
reused in place only after a complete independent rehash.

After execution, add a dated `RESULTS.md` only from the independently audited
release. Outcome-motivated changes require a new study ID or a prospective,
dated amendment; they must not rewrite this protocol in place.
