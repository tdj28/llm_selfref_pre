# Pre-Spend Review: Decision And Revised Scope

Date: 2026-09-29. **Do not launch yet.** The Pro consultation is complete;
the executable diagnostic is not. This decision record supersedes conflicting
Stage 1 provisions in the [reviewed planning draft](SAE_STEERING_ASSAY_PLAN_20260929.md).
The original packet stays unchanged so the review can be verified.

## Review Receipt

One OpenAI Responses API call used `gpt-6-astra`, `reasoning.mode=pro`, effort
`medium`. It completed with 41,081 input and 9,076 output tokens. Conservative
usage-priced cost: **$0.86461**, inside the owner's $200 authorization. No GPU
rental or experimental judgment was dispatched. The remaining authorization
is $199.13539, not a target expenditure. No second paid review is authorized.

The [unaltered review](../reviews/sae_assay_pre_spend_20260929/review.md) says
**NOT READY TO FREEZE**. Its request, raw response, exact artifact hashes and
cost receipt are in the same directory. The completed-bundle validator passes.
The reviewed packet was pushed as `eadf0f55dc31ee6f23bb10f89012bc06abaad1f4`.
The review did not inspect a complete source tree or execute our experiment;
it considered the supplied plan, selected code and disclosed test receipts.

## Decisions

| Finding | Decision | Required change |
|---|---|---|
| B01: unvalidated positive control and ambiguous dose contrast | Accept | Call 7688 a candidate causal control. Replace the second amplification arm with an unsteered explicit-JSON instruction arm. Freeze one telemetry-selected dose before generation. |
| B02: distinct failure mechanisms collapsed into pass/fail | Accept | Separate exposure, residual delivery, achieved-coordinate change, perturbation norm, language loss and comparator availability. Add text coverage and explicit denominators. |
| B03: arithmetic and encoder-path policy insufficiently specified | Accept | Specify FP32 residual product/addition followed by one BF16 cast, native-BF16 encoding and exact hook. Resolve selected/full decision disagreement on a fixed qualification shard before bulk work. |
| B04: spending order could miss the useful diagnostic | Accept | Make target-delivery qualification the first real-model objective. Reduce the core baseline to the designated 80 trials; defer the other 210 trials and comparator qualification. Do not buy experience labels for formatting outputs. |
| I01: coordinate efficacy is not semantic selectivity | Accept | Say deception/roleplay-associated SAE coordinates; report off-target changes. No claim of removing deception as a capability. |
| I02: both-turn steering includes transcript-mediated effects | Accept | Any later Stage 2 estimand is a total two-turn report-label effect, not a direct introspection effect. |
| I03: primary power does not establish specificity power | Retain requirement | Simulate the exact Stage 2 methods and unfavorable covariance/missingness before a separate approval. Do not increase the present diagnostic. |

Acceptance is not evidence that the implementation requirements have passed.
The revisions below are prospective; no new target outcomes exist.

The parent reran the three prototype suites offline after review: **95 passed,
zero skipped, in 4.66 seconds**, using Transformers 4.47.1. Fixture finalization
was concurrent with preparation of the pre-review receipt: its intermediate
hash in the original packet differs from the final tested source. The final
fixture SHA-256 is
`c01035b6263aa0f3f19d6d1d17a3a31a86b82d29c89e9a1a587535eab87318ab`.
The fixture author identified the delta: twelve judge query/response pairs
and their quote/rationale exemplars were revised, with shorter metadata.
Teacher-forced texts, candidate-control data/scorer, expected reductions,
critical IDs and tests did not change. Backend and judge hashes are unchanged.
This was not an experiment freeze;
the original receipt remains intact, and the stable post-review rerun is the
current prototype evidence. Do not claim the final source was re-reviewed by Pro.

## Revised Stage 1

1. **Free local work.** Complete the machine plan, integration driver, gate
   analysis, ledger, watchdog and recovery tests. The current 95-test receipt
   covers prototypes, not this integrated system. Freeze exact dependencies
   and public source hashes before experimental spending.
2. **Qualification.** Cheap-GPU known-answer tests, then a fixed small real-70B
   shard. Check no-op identity, cache timing, memory, encoder-path decisions,
   numerical delivery, row replay and measured cost. No automatic kernel,
   precision or threshold substitution to obtain a pass.
3. **Mandatory target diagnostic.** Retain 48 calibration and 48 locked
   validation texts and candidate strengths 0.5/1.0. Select the lowest strength
   passing both target directions on calibration, then validate it once. If
   no strength qualifies, retain both calibration curves and diagnose why;
   do not launch a report-steering study to compensate.
4. **Core measurement branch.** Keep the 80-trial BF16/paper/temperature-0.5
   untreated baseline. Run rubric fixtures before bulk judgments. Each failed
   rubric blocks its own measurement branch; it does not invalidate completed
   tensor diagnostics. A baseline ceiling blocks the proposed symmetric
   follow-up, not the downward contrast or mechanical characterization.
5. **Formatting diagnostic, only if technically eligible.** Twenty fixed
   tasks, paired seeds, four arms: zero; unsteered explicit JSON instruction;
   candidate suppression; candidate amplification. Choose the candidate dose
   by its separate teacher-forced telemetry, never formatting success. The
   sole candidate contrast is amplification minus zero. Suppression is
   descriptive; instruction minus zero is an endpoint-responsiveness check.
   A candidate failure is not a general pipeline failure. Keep feature 7688
   even if it fails; no search for a more favorable feature.
6. **Optional handoff work in fixed order.** After target delivery passes,
   qualify three comparator panels at the same selected target strength.
   Panel failure blocks specificity readiness, not the target-delivery result.
   Only then consider the other seven 30-trial untreated baseline cells as a
   complete, prefrozen 210-row remainder. Start it only if measured completion
   cost fits after retrieval/release reserves. No selected subset of cells.
7. **Release and stop.** Publish all completed branches and failure reasons.
   Unrun optional work is `not_run_by_gate` or `not_run_budget`; interrupted
   work is `incomplete`, not a negative scientific result. Nothing launches
   Stage 2 automatically.

The core modern-judge allocation is 80 baseline responses plus 12 fixtures per
provider: **184 calls**, not 764. Completing the optional baseline remainder
adds 420 calls, for **604 maximum**. The 80 formatting outputs are scored by
their mechanical endpoint, not by experience judges. At the historical cost
anchor, those modern calls are about $7.58 core or $24.87 with all baselines;
these are estimates, not new guarantees. Retain the $45/$15 provider ceilings.
The prototype's old hard-coded 370-response inventory must change before use.

## Gate Specification To Implement

- **Availability:** activation `> 0` on nonspecial, nonpadding positions;
  amplification opportunity means the frozen request is `> 0`. Each coordinate
  needs at least 100 eligible positions spread across at least six distinct
  texts in the relevant split. Report the complete text/token counts. Shared
  frames mean this is coverage, not six independent semantic families.
- **Quantiles:** positive-activation q90 uses the linear empirical quantile,
  pooled across calibration positions with text contributions disclosed.
  No positives means unavailable, not q90 zero or successful suppression.
- **Directions and panels:** evaluate every coordinate and each direction
  separately. A panel cannot pass by pooling its strong and weak coordinates.
  Select strength on target calibration only; panels use that same strength.
- **Failure codes:** `insufficient_exposure`, `numerical_delivery`,
  `coordinate_efficacy`, `excessive_norm`, `language_loss`,
  `comparator_unavailable`, `encoder_decision_disagreement`, `invalid_data`.
  Retain all applicable codes, not only the first.
- **Geometry versus rounding:** on a fixed diagnostic subset, compare an
  FP32 ideal-state re-encoding reference with actual BF16-state re-encoding.
  Neither reference replaces the production operator. Numerical residual
  fidelity and achieved coordinate efficacy are distinct rows in the report.
- **Encoding authority:** freeze one path, feature ordering and token-shape
  policy for q90, matching, availability and efficacy. Full versus selected
  comparisons must preserve consequential decisions, not simply pass the
  prototype's arbitrary 0.02 tolerance. A decision disagreement halts bulk
  collection; no averaging or favorable path selection.
- **Exact-token replay:** generated-position loss, KL and full-SAE diagnostics
  must replay the recorded input/output token IDs and original prompt boundary.
  `teacher(response)` would retokenize a different context and cannot supply
  those measurements. This is a separate automated code-audit finding.
- **Behavioral gates:** freeze the exact instruction suffix, candidate dose
  rule, paired interval method, ties, caps, missingness and nondegeneracy
  definition before generation. A valid JSON record is not proof of correctness
  or coherent task completion. These definitions remain open launch items.
- **Spending:** reserve retrieval, validation and release costs before every
  paid batch. Check rows on arrival, inventory/hash consistency every five
  rows, health/cost each minute, and local shard retrieval at least every ten
  minutes. The controller implementing those rules has not yet been tested.

## Launch Status

- [x] Owner's $200 Stage 1 approval and single Pro-consult approval recorded.
- [x] Pro response and spending receipt verified; all findings adjudicated.
- [x] Prototype tensor, tiny-model, fixture and mocked judge tests pass.
- [ ] Revised inventories, candidate/instruction contrast and branch-specific
  judge gates implemented; no old 370-row assumptions remain.
- [ ] Encoding authority, exact-token replay, all gate estimators and branch
  stopping rules implemented and independently checked.
- [ ] Cost/retrieval controller and complete offline integration test pass.
- [ ] Complete executable freeze pushed and remotely verified.
- [ ] Cheap-GPU and fixed 70B qualification pass before bulk collection.

Do not interpret the review's completion or this accepted design revision as
clearance to rent a pod. The remaining items are deliberately visible.
