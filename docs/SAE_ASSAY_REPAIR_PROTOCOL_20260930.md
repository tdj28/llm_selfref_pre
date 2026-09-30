# SAE Assay Repair: Coordinate Delivery

Date: 2026-09-30. Status: engineering follow-up after inspecting Stage 1.
Public Git freeze is required before new GPU outcomes. This is not a new
consciousness experiment, a proprietary replication, or a retrospective repair
of the earlier verdict. Original artifacts and thresholds remain unchanged.

## What We Already Know

Stage 1 at `2ca10e1756a6cffe77b8194367f5026abadc7f0f` failed its
target-delivery, candidate-control and baseline-headroom gates. Native BF16
rounding damages many small suppression edits. Amplification has a different
problem: three target coordinates have median-zero efficacy even in the saved
ideal FP32 edited-state diagnostic. That reference promotes already-BF16 SAE
weights; it is not an original-weight FP32 experiment.

An inactive ReLU coordinate can have a substantially negative preactivation.
Adding its positive activation target times its decoder vector need not cross
that threshold. The encoder/decoder response matrix need not be identity,
either. This is a limitation of the specified intervention, not evidence of a
wrong layer or incorrect feature IDs.

Candidate 7688 was selected from a third-party JSON-format label. Bare JSON
objects are not necessarily the instruction/assistant context represented by
that coordinate. Its zero activation on twelve objects remains a real result.
The old descriptive `activation_summaries` also included special tokens and
pooled origins, contrary to the protocol. The frozen exposure and coordinate
efficacy gates exclude special tokens; residual-fidelity and norm gates include
them. A separate derived correction will preserve raw
summaries and repair reporting without changing those gates.

## Questions

1. Do explicit preactivation corrections improve delivered coordinate edits?
2. Does the answer survive the original norm, fidelity and language gates?
3. Does a larger fixed, previously published text panel provide adequate
   exposure for the six accepted coordinates?
4. Is 7688's activity context-dependent, and does the mundane JSON endpoint
   respond to an ordinary instruction independently of SAE success?

No generated subjective-experience response is collected or judged here.
Stage 1's 71/80 historical-rubric and 78/80 inclusive modern-reader baselines
remain unchanged. Selecting the strict 0/80 endpoint is not a headroom fix.

## Fixed Inputs

Same pinned Llama 3.3 70B, native BF16, Goodfire layer-50 SAE, artifact hash,
full-dictionary token-one encoder and actual block-output hook as Stage 1.
The six coordinates remain 30032, 58667, 22004, 30686, 41533 and 23893.

The machine plan contains 544 teacher texts: the original 48+48 authored
texts, plus 64 texts per each of seven fixed categories from the published
2,606-text construct-validity corpus. Selection sorts item IDs by a fixed
salted SHA-256, takes 64 per category, and assigns the first 32 to calibration.
No activation ranking is used. The result is 272 calibration and 272
validation texts. Prior semantic-map outcomes were public, so these are not
new independent semantic-validation texts or natural documents. Corpus-specific
results are reported alongside pooled diagnostics; lexical variants are not
treated as independent natural observations.

Clean layer-50 states and exact token IDs are persisted as BF16 safetensors,
with per-file hashes. This avoids renting the full model again merely to
inspect coordinate geometry. No SAE or model weights are redistributed.

## Three Operators

Let `E` be the six selected encoder rows, `D` the selected decoder columns,
`p = E h + b` the promoted-BF16 FP32 preactivation, and `z` the authoritative
full-width native BF16 activation. Strengths remain 0.5 and 1.0.

- **Literal:** the unchanged Stage 1 decoder-delta operator.
- **Decoder-span correction:** `r = D solve(E D, u)`.
- **Encoder minimum-norm correction:** `r = E.T solve(E E.T, u)`.

For suppression, active coordinates target `(1-lambda) z`; inactive
preactivations are left unchanged. For amplification, eligible coordinates
target `z + lambda max(q90-z, 0)`. The requested preactivation shift `u` is
the target minus `p`, explicitly crossing negative thresholds where necessary.
Ineligible coordinates have zero preactivation shift. Positive q90 comes only
from pooled clean calibration activations. It is never recomputed on validation.

Both alternatives apply `BF16(FP32(h) + r)` once. No clipping, iterative
rounding compensation, regularization search or hidden fallback is allowed.
A singular/nonfinite solve matrix or condition number above 1e6 makes that
operator unavailable; it does not silently substitute another operator.
Zero remains bitwise identity. All nonpadding positions, including special
tokens, receive interventions. As in the frozen analysis, exposure, coordinate
efficacy and neutral NLL exclude special tokens; residual-fidelity and norm
gates include them. Report both scopes explicitly. Do not silently change an
old gate to remove the special positions that account for all 48 dose-1
amplification norm passes in Stage 1.

The encoder-minimum-norm alternative is not confined to the decoder span and
has a different semantic interpretation. A coordinate-delivery success would
not show successful removal of deception, natural mediation, or equivalence to
the paper's proprietary service. Both alternatives are explicitly new
engineering interventions, not bug-fixed copies of the historical operator.

## Gates And Selection

Reuse Stage 1's exact exposure, residual fidelity, re-encoded coordinate
efficacy, perturbation-norm and neutral-language-loss thresholds. No failure
threshold is relaxed. Full-native encoding remains authoritative. Report
selected-width and historical separate-matmul/bias diagnostics; selected-width
decision disagreement blocks qualification as before.
The historical-arithmetic diagnostic still uses this run's six-coordinate
panel and BF16 model states; it is not an exact replay of earlier NF4 mapping.

Run every calibration recipe, regardless of favorable interim results.
Choose the first qualifying operator in the fixed order literal,
decoder-span, encoder-minimum-norm; each chooses its lowest passing strength.
Persist that selection before validation. Collect all clean validation states;
run one paired validation only for the selected recipe. Failure cannot trigger
another operator's validation or new prompts. No qualifying recipe means
clean-exposure evidence only, not a behavioral null.

Publish all operator failures, corpus sensitivities and delivered magnitudes.
Token counts are descriptive denominators, not independent sample sizes.
Record preactivations, threshold deficits, solve coefficients/residuals,
historical matmul-plus-bias activations, non-target coordinate movement, native
re-encoding, residual norms/fidelity, paired NLL and reconstruction diagnostics.

## Mundane Controls

Inspect the same twelve 7688 JSON texts in four fixed contexts: bare JSON,
plain instruction plus JSON, an instruction/assistant chat, and a user chat.
No new feature is selected. Contextual activation is observational; it does
not qualify SAE steering or retroactively rescue the original candidate.

Independently generate the existing twenty mundane tasks in two unsteered
arms, zero and explicit JSON instruction, with paired task seeds, temperature
0.5 and a 128-token cap. This branch runs even if 7688 remains inactive.
Report whole-object strict JSON scores, nondegeneracy, caps, missingness,
per-task pairs and the fixed-panel mean difference. It establishes only
instruction/endpoint responsiveness, not a successful SAE positive control.
No paid experience judges are used.

## Execution And Cost

The owner's instruction to keep fixing authorizes this bounded engineering
follow-up within the original cumulative $200 cap. Prior spending upper bound
is $13.07885980328333333333333333, including Pro, all GPU attempts and judges.
This repair is capped at $40 new spending: $2 cheap qualification and $38 main,
not an additional $200. No paid Pro or judge calls. Expected new cost is about
$8-18 from measured Stage 1 throughput, with uncertainty for increased logging.

CPU algebra tests and a tiny real BF16 Llama must pass; repeat the exact path
on a newly owned cheap CUDA pod before B200. The main run needs parent audits
at live-model zero qualification, the first five clean rows, and the fixed
seven-category nonzero shard (both signed doses, every available operator,
84 rows if all are available) before bulk interventions. The shard is retained
inside calibration, never regenerated. Verify exact canonical/full-diagnostic
reencoding equality. Solve residuals
must be at most `0.001 * max(1, abs(requested preactivation shift))` per
coordinate as a numerical implementation check, distinct from efficacy gates.
Check progress
and cost every minute, retrieve hash-checked snapshots at least every ten
minutes, and stop on invalid data or stalled/budget-limited work. Remote timers
reserve ten minutes for retrieval; the parent monitor must remain active.

Create uniquely named pods only; inventory existing pods into a do-not-touch
set. Transfer only the scoped Hugging Face credential and public SSH key, never
`.env`, provider keys or the RunPod key. Retrieve and hash-check every artifact,
then delete the owned pod and verify GET 404 and inventory absence. Preserve
incomplete attempts. A failed engineering repair can be reported honestly; it
does not authorize threshold changes or a report-steering Stage 2.
