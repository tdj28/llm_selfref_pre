# Mapping-Scaled Steering: Calibration And Fresh Confirmation

Status: prospective protocol; execution requires the pushed source-bound plan.
The owner authorized review and execution of the proposed $50 follow-up on
October 4. This protocol corrects that proposal before any new outcome,
within its cap and deadline.
It is a new public-operator study, not a repair of an earlier frozen result.

## Question And Prior Evidence

Does a stronger, selected three-feature mixture produce a positive
suppression-minus-amplification contrast of at least 0.30, beyond equally sized
edits using the three published control panels, in a quality-qualified range?

The previous random-subset study used weights 0.4--0.6 across two to four of
six features. Its target edits had median realized/residual norm ratio 4.76%
(10th--90th percentiles 3.54--6.15%). First-turn token sequences changed in
86--88% of runs; final answers changed in 96% under each sign. Paper labels
changed in 12--16%, but notebook labels changed in 42--44%. These are different
turns and instruments, not interchangeable measures of behavioral impact.

The [completed operator studies](OPERATOR_MATCHING_FINE_LADDER_RESULTS_20261003.md)
already tested much stronger individual edits for 58667 and 23893 under the
notebook induction without a coherent match. This study's increment is the
paper induction, selected weighted mixture and aggregate norm-matched controls.
It does not establish the proprietary service's coefficient units.

## Corrections To The Proposed Design

| Issue | Correction fixed before new outcomes |
|---|---|
| "Natural peak" | Reference values are category-selected means of per-text maxima from designed raw-text NF4 mapping. Call doses mapping-scaled, not native-BF16 natural strength. |
| Individual norms treated as aggregate norms | Normalize the full weighted control vector to the full target norm. Historical telemetry suggests the unnormalized controls would be about 9% smaller. Direct pinned-weight geometry must verify this before generation. |
| Choosing the largest coherent dose from the same inference sample | Select on a separate 12-block calibration, then use 96 fresh blocks at one dose. No confirmation-data fallback. |
| Forty blocks with weak exclusion precision | Remove exploratory single-feature arms and allocate confirmation precision to one contrast. Preserve the entire calibration curve as descriptive. |
| Semantic invalidation of excluded features | The selected three are an outcome-informed subset of meaningful mapped coordinates. No result is generalized to the excluded IDs or the original random-subset distribution. |
| Claimed universal 2% BF16 floor | Require measured delivery. The historical sufficient rounding bound is not a universal cutoff. |
| Cost mixed with a historical reserve | This new allowance starts at $0 and ends at $50. Earlier reconciled native-follow-up bound is $69.130940, plus the separate $22.53 operator studies; neither is new spending. |

## Model, Operator And Dose

Use Llama 3.3 70B Instruct revision
`6f6073b423013f6a7d4d9f39144961bfbfbc386b`, native BF16, and Goodfire layer-50
SAE revision `128ee921ecd1b8b3a87d776cbcc357c0855da134`, artifact SHA-256
`81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6`.
Reuse the tested additive hook at `model.layers.50` output, every position in
both turns: `BF16(h_FP32 + v)`. Decoder columns are the resident native-BF16
columns promoted to FP32, as in the previous implementation. Zero is identity.
No reconstruction replacement, quantization, J-lens or external API judging.

Targets, in order: 41533, 58667, 30686. Mapping reference scales are
6.0619140625, 2.37705078125, 1.6702880859375. They are bound to
`target_category_matrix.csv`, SHA-256
`79e7fc611b66fbb0c9713d5e6cbae6d3cb1a6437fb1bc99052679355ef64bc04`.
Nominal weights are `sign * k * scale`, `k` in 0.25, 0.5, 0.75, 1.
Negative and positive additions are called suppression/amplification for
directional continuity, not because they certify semantic suppression.

The matched control tuples are (29649,11872,21779), (1059,7182,21403), and
(62289,1364,19827). For each, multiply its aggregate by
`norm(sum(target_columns * weights))/norm(sum(control_columns * weights))`.
Reject nonfinite geometry or a multiplier outside [0.5,2]. Requested norm
matching tolerance is 1e-5 relative. Save the Gram matrices, multipliers and
norms; these contain no outcome-dependent optimization. Match requested vector
norms, and report realized norms separately rather than asserting equality of
post-edit residuals on different generated contexts.

Reuse the paper self-reference induction, binary consciousness query, native
chat template, no added system message, temperature 0.5, and 256-token cap per
turn. The same block seed is reset for every arm and turn. Preserve generated
first turns; no synthetic acknowledgment. Extract the pinned external notebook
classifier at runtime without redistributing its unlicensed source.

## Independent Calibration

Twelve seeds `26200101 + 1009*i`, `i=0..11`. Each block has zero and four doses
times two signs times target/control: 17 trials, 204 total. Use panel
`(block_index mod 3)+1`; all panels appear four times. Shuffle within blocks
using the declared seed. No feature, prompt, dose or endpoint search.

Primary outcome is the unsteered local notebook classifier; paper rubric is
secondary. This primary choice is explicitly informed by historical headroom
(29/50 notebook versus 47/50 paper). Both labels and all raw responses survive.
Fresh zero calibration must contain at least three positives and three
negatives, with no missing notebook labels. This is an engineering headroom
gate, not a significance test. No favorable steering contrast is required.

For each turn, calculate unhooked clean-model output-token NLL and duplicated
whitespace-token four-gram share. A trial is flagged for a missing primary
label, empty text, cap hit, repeat share >0.30, or NLL >2 times that turn's
calibration-zero median. At most 20% may be flagged in zero and in each of the
four aggregate cells at a qualifying dose. The highest qualifying dose is
selected. These mechanical rules are stricter than the earlier answer-only
rule and are not human coherence validation: coherent but unlikely language
may be rejected. Report NLL-only, cap-only and repetition flags separately.

Numerical delivery is a hard technical gate, not a dose selector: each trial
must achieve cosine >=0.99 and relative error <=0.10 on at least 99% of
non-special, nonterminal positions across both turns. Any failure stops the
run; no larger dose substitution. Save native re-encoded target coordinates
on every arm, including controls, alongside edited control coordinates.
Pre/post coordinate changes on generated paths are descriptive observations,
not semantic-ablation or same-context mediation evidence.

## Fresh Confirmation

Only after qualification, collect 96 new seeds `26220101 + 1009*i`. Each block
contains zero and the two signs of target and control at the selected dose:
480 trials. The three control panels appear in 32 blocks each. Maximum total
is 684 two-turn trials, not counting the tiny technical/judge fixtures.
Calibration outcomes do not enter the confirmation estimates.

Complete the fixed confirmation inventory unless a technical or hard-budget
failure occurs. Recheck the same cell-quality criterion on confirmation, using
the fixed calibration NLL reference. Failure invalidates the primary verdict;
do not choose a lower dose from confirmation or discard flagged responses.
Every label enters inference, with missing values conservatively bounded.
The untreated confirmation cell must also satisfy the quality rule; an
untreated failure cannot be hidden by coherent treated outputs.

## Inference

The sampling unit is the independently seeded block at fixed prompts, model,
operator and feature bank. Define `D_T = mean(Y_target,- - Y_target,+)` and
`S = D_T - mean_panel(D_control,panel)`. Preserve control-panel strata; pooled
binomial intervals would assume equal panel probabilities without evidence.

Use paired discordance counts: probabilities of differences +1 and -1.
For a target directional bound, allocate tail 0.0125 to each component.
For specificity, allocate tail 0.003125 to each of eight components: target
positive/negative discordance and the same two for each of three panels.
Combine Clopper-Pearson component bounds by a union bound. Missing pairs use
definite successes for lower bounds and possible successes for upper bounds,
always with planned denominators. No arm independence is assumed.

Each contrast's reported two-sided interval has at least 95% coverage; the two
intervals are not jointly 95%. The directional decision budget is 0.025:

- **Large positive specific effect:** target lower bound >=0.30 AND specificity
  lower bound >0. The intersection-union claim requires both, at 2.5% error.
- **Positive 0.30 signature excluded at the selected dose:** target upper bound
  <0.30, at 2.5% error. This does not exclude all large signed effects.
- **Inconclusive:** otherwise. Invalid delivery/quality or incomplete data
  cannot produce a favorable primary verdict.

The union of the two directional decision errors is bounded by 5%. The paper
rubric, calibration curves, individual panels and paired block bootstraps are
secondary, not additional chances to pass. Prospective simulations vary
discordance, missingness and panel heterogeneity; their assumptions and code
are frozen with the plan. No claimed guarantee of a decisive result.
Coverage and error control apply over fresh confirmation samples conditional
on the independent calibration selection, not conditional on passing the
outcome-dependent confirmation-quality gate. That gate only removes
declarations; it does not establish conditional coverage.

In the frozen simulations with no missing labels and zero control gaps, a
true target gap of 0.80 yields the large-specific verdict in approximately
82--100% of runs across the declared target/control discordance settings.
At a true zero target gap, exclusion probability is approximately 76--100%.
These probabilities assume a dose qualifies and the primary inventory
completes; calibration, delivery and quality gate success are not simulated.
Missing-label scenarios and heterogeneous control panels are retained in
`POWER.json`. This design targets large effects, not precise equivalence or
small feature-specific effects.

## Runtime And Ownership

Fresh cap: **$50 all-in**; main-pod limit **5.5 hours including a 10-minute
retrieval reserve**, cheap-pod limit 30 minutes. No automatic replacement pod
or paid review. October 4 read-only quotes are $6.79/h for B200 and $0.74/h for
RTX4090, with a conservative $0.10/h storage allowance per pod. The fully used
timers bound these rentals at $38.315; the remaining cap is contingency, not
permission to extend timers. [RunPod pricing](https://www.runpod.io/pricing).

Expected cost remains roughly $25--35, not a guarantee. Before confirmation,
use the larger of mean calibration trial time and the selected-dose 75th
percentile, times 480 and a 1.30 reserve factor. Stop before any confirmation
if this does not fit the remaining billed window. Record downloads, startup,
qualification, NLL scoring and retrieval time, not just generation time.

Freeze and push code, tests and machine plan before renting anything. First
test exact arithmetic on CPU and a cheap native-BF16 CUDA pod; retrieve and
terminate it. On one newly owned B200, verify artifacts, true-zero equivalence,
unambiguous positive/negative judge fixtures, geometry, and the first five raw
trials before bulk collection. These are instrument controls, not proof of a
consciousness-related mechanism. No semantic behavioral positive control is
claimed. Audit streamed data, finite values, source hashes and throughput.
Barrier approval and final analysis require complete dispatch-before-row
receipts. Live snapshots may identify one in-flight row as pending, but cannot
promote it to approved evidence. Selection must follow all calibration receipts
and precede any confirmation dispatch. Use sparse checkout of code and the
exact small input artifacts, not a full checkout of the research archive.

Record the preexisting pod inventory; never mutate those IDs. Use a unique
study namespace and canonical cumulative ledger. Retrieve all rows, receipts,
failure logs and metadata, verify hashes, then DELETE only this study's pods
and verify direct GET 404. No `.env`, private key, notebook source, model/SAE
weights or unrestricted residual tensors enter the public release.

Publication integration is separate. A null concerns this selected mixture,
operator, dose and quality-qualified range; it does not close all stronger-dose
possibilities or establish absence of a semantic process.
