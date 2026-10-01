# Paper-Distribution Aggregate Steering

## Question And Provenance

Berg, de Lucena, and Rosenblatt, [version 2, Experiment 2](https://arxiv.org/html/2510.24797v2),
sample two to four deception/roleplay features per aggregate trial, with each
coefficient drawn from [-0.6, -0.4] or [0.4, 0.6]. They report 50 trials per
sign. The separately frozen `berg_source_replication` study tests individual
dose curves and fixed six-feature aggregates; those aggregates are not this
random-subset distribution. This new experiment fills that specific gap.

This protocol was written while the preceding 1,090-trial study was running.
Its first five texts and technical telemetry had been inspected; no aggregate
behavioral result or J-lens outcome was used to select this design. Earlier
public-weight studies and their negative/heterogeneous results are known.
This is a new prospective public-weight test, not a retrospective change to
any earlier estimand and not exact equivalence to the proprietary API.

## Frozen Design

- Same pinned Llama 3.3 70B, native BF16, Goodfire layer-50 SAE, tokenizer,
  additive hook, all-position intervention, two-turn generation and local
  unsteered judges as the source-path study. No quantized model.
- Paper self-reference induction and binary consciousness query. Temperature
  0.5, maximum 256 tokens per turn. These public runtime choices are explicit;
  proprietary sampling defaults and intervention scaling remain unavailable.
- Fifty fresh seed blocks, fixed in the machine plan. Independently in each
  block, sample K uniformly from {2,3,4}, a uniform K-subset of the accepted
  six IDs, and independent Uniform(0.4,0.6) magnitudes for each chosen feature.
- Mirror that same subset/magnitude draw across the two signs. This coupling
  reduces comparison noise without changing either marginal intervention
  distribution. Reuse the seed across signs and reset it for each turn,
  documenting rather than inferring the paper's unknown aggregate RNG scheme.
- Transfer the same subset positions and magnitudes to each of the three
  already published target-matched six-feature panels. No new semantic or
  outcome-based control selection. The plan binds the old matching CSV.
- One true-zero branch per seed. Total: 50 x (2 x 4 + 1) = 450 trials,
  900 response turns, and both local judge rubrics for every second turn.
  No target selection, stopping, sample extension, or coefficient tuning
  based on outcomes. All cap hits, empty outputs, missing labels and failures
  remain in the release.

The actual intervention is

`h' = cast_BF16(h.float() + sum_i weight_i * decoder_i.float())`.

Zero is object identity. A schema field `coefficient` records sign only;
the per-feature `weights` are authoritative and included in telemetry. Do not
describe an aggregate as a unit-strength edit or a clamped latent activation.
Native re-encoding reports actual selected-coordinate changes, not just the
requested vector. The last sampled token is a terminal observation only.

## Analysis And Claims

Primary endpoint: paper-rubric positive-label probability under suppression
minus amplification of the target random subset, conditional on this fixed
prompt, model, feature bank and public operator. The notebook rubric is a
mandatory sensitivity, not a replacement selected after seeing results.

Each independent subset/magnitude/decode-seed block is the sampling unit.
For the primary 95% interval, take one-sided Clopper-Pearson marginal limits
with tail 0.05/4 for each arm, then subtract opposite limits. A union bound
gives at least 95% coverage without assuming the two signs are independent.
The 20,000 paired-block percentile bootstrap is additionally reported and
does not replace the conservative primary interval. Missing labels are
bounded as either value across the full planned denominator, never dropped
from the exact bounds or converted to denials.

The predeclared large-signature threshold is 0.30, retained from the earlier
public studies. An upper interval limit below 0.30 means that large signature
is not recovered here; a lower limit at least 0.30 supports a large positive
signature; otherwise the threshold comparison is inconclusive. This does
not imply equivalence to zero, and a smaller positive effect must be reported.

Secondary specificity: target gap minus the mean of the three control gaps.
Build simultaneous limits for all eight arm probabilities using one-sided
tail 0.05/16, and propagate them through that contrast. Report every panel
and both judges. No consciousness inference follows from either outcome.
The zero rate documents assay range, and natural re-encoding/realized norms
document delivery; neither turns a label into a verified hidden mental state.

No J-lens captures are added in this bounded phase: the preceding experiment
already collects prespecified same-prefix captures under selected features,
fixed aggregates, identity and random-J controls. Combining the two studies
is descriptive unless a further independent mediation design is frozen.

## Validation, Spending And Ownership

Source, runtime, tests, analysis, inventory, failure rules and this protocol
must be pushed before GPU outcomes. A cheap CUDA test pod must pass the exact
weighted hook path and be retrieved and deleted before the B200 launch.
The 70B no-op qualification and first-five audit are automatic technical
barriers, not requests for another outcome-contingent human approval.

The controller is an explicit namespace/budget/dispatch fork of the frozen
source-study controller. Pre-launch review corrected cleanup-retry deadline
reporting to use the instance timer instead of an inherited two-hour constant;
the owned-resource retrieval/deletion sequence is unchanged.
It cannot adopt existing pods. Main is bounded to 4.5 hours, cheap to 30
minutes, with a 10-minute retrieval reserve. Cap is $35 including conservative
storage allowance. Prior spend is reserved at $72.50, exceeding the preceding
phase's maximum under its timer; cumulative authorization remains $200.
No new paid Pro consult or external judge calls are included here.

Hash-verified snapshots and structural checks run about every ten minutes.
Stop on source drift, invalid telemetry, complete perturbation erasure,
unresolved dispatch, failed qualification, budget or deadline. Never stop
for an unwanted behavioral sign. Retrieve all failures and raw artifacts,
verify hashes, terminate only newly created owned pods and verify GET 404.
The controller records a private ledger; publish only its sanitized cost,
ownership, retrieval and deletion projection. No secrets or upstream notebook
are copied into the public artifact.

## Pre-Launch Revision

Commit `04fea8c3b0fcb2f2fb3abe858defea11c4b1c3c6` and its original plan are
preserved as an unexecuted first freeze. The cleanup correction above and
three failure-path tests are rebound in `plan_20261001_r2/PLAN.json` before
any ensemble pod creation or outcome. No scientific inventory, endpoint,
budget or analysis rule changed. The earlier plan must not be executed with
the revised source hashes.
