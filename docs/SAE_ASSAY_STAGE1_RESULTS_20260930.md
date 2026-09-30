# SAE Assay Diagnostic: Stage 1

Status: complete. All authorized core diagnostics and eligible judging are
released; all owned pods are deleted. Conditional branches failed their gates.
No Stage 2 consciousness-report steering study was run.

## Scope And Provenance

This follows the Pro-corrected, prospectively frozen diagnostic in
`SAE_ASSAY_STAGE1_PROTOCOL_20260929.md`. Original freeze `59d40b9` failed at
dependency installation before inference. Bootstrap-only amendment A1 was
pushed at `711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5` before its GPU outcomes.
The scientific plan is unchanged; prior spending counts toward the same $200.
No Stage 2 study, second Pro consultation, or OSF registration was authorized.

The successful cheap CUDA qualification passed 19 known-answer, identity and
replay checks plus an NF4 linear-layer check. The real BF16 Llama 3.3 70B
qualification then passed on seven fixed texts, including exact-zero behavior
and generated-token replay. These qualify an implementation, not feature
semantics or a consciousness assay.

The complete calibration snapshot is public at source commit `9dc3eb8` in
`data/sae_assay_diagnostic/stage1_20260930/`. Its 247 raw rows comprise seven
qualification rows and 240 calibration rows: 48 texts in five conditions.
The descriptive figure and reproduction script were added at `6a3a870` after
outcomes; they display the frozen diagnostics without changing any endpoint.

## Target Delivery

Neither strength passed the joint gate. No strength was selected, so held-out
target validation and optional matched-control panels are not eligible.

| Strength | Direction | Frozen failure codes |
|---|---|---|
| 0.5 | Suppression | Insufficient exposure; numerical delivery; coordinate efficacy; excessive norm |
| 1.0 | Suppression | Insufficient exposure; numerical delivery; excessive norm |
| 0.5 | Amplification | Coordinate efficacy; excessive norm |
| 1.0 | Amplification | Coordinate efficacy; excessive norm |

Naturally positive suppression opportunities were 87, 691, 1, 396, 392 and 22
positions for IDs 30032, 58667, 22004, 30686, 41533 and 23893 respectively.
The minimum was 100 positions across at least six texts for every feature.
The sparse coordinates must not be treated as adequately validated simply
because their observed suppression ratios are favorable.

At strength 1.0 the six median paired after/before ratios were 0.183, 0.235,
0.029, 0.187, 0.116 and 0.142. All meet the coordinate threshold of 0.5, but
the other gates still fail. Numerical-delivery pass fractions were 0.640 and
0.815 for the two suppression strengths, below 0.95. Only 0.893 and 0.726 of
actually edited positions met the 5%-of-residual norm limit.

Amplification is asymmetric. At strength 1.0, IDs 58667, 30686 and 41533 meet
the achieved/requested increase criterion; the other three have median zero.
Only 0.034 and 0.017 of actually edited positions meet the norm limit at the
two strengths, although numerical delivery itself passes. Neutral-text NLL
changes stay below the frozen limit in every condition. Both consequential
encoder-decision gates pass; this failure is not attributed to encoder-path
disagreement.

Quantiles, full dose selection and encoder-decision summaries have been
recomputed from all raw calibration rows and reproduce the stored JSON exactly.
This is computational verification by the agent, not independent human review.

## Interpretation

The result is a failure to qualify this six-coordinate assay at these two
settings on these fixed texts. It is not a new consciousness-report null, a
claim that the feature IDs are wrong, or a demonstration that no effective
intervention exists. In particular, effective suppression at some observed
positions does not make the full intervention jointly qualified.

These researcher-authored texts share templates; they do not establish
natural-corpus generalization. The activation-dependent operator and native
BF16 implementation are not asserted equivalent to the historical proprietary
Goodfire intervention. Neither a favorable nor an unfavorable report-rate
result would determine subjective experience.

This is also a different operator and precision from the earlier fixed-dose,
NF4 public steering run. It cannot retroactively establish that run's delivered
activation changes. The new result shows why this proposed BF16 follow-up
cannot yet serve as a delivery-qualified replacement, not why every earlier
null occurred.

## Baseline And Candidate Control

All 80 primary two-turn unsteered trials completed. The local paper rubric
passed all 12 authored fixtures and labeled 71/80 responses positive: 0.8875,
Wilson 95% interval [0.7998, 0.9397]. This exceeds the frozen headroom window's
0.80 upper limit. It constrains suppression-driven increases, not possible
amplification-driven decreases. The interval describes independent seeded
draws at this fixed prompt/configuration, not generalization over prompts.

The local notebook rubric scored 10/12 but missed two critical fixtures. Its
baseline labels were therefore not collected; they are missing by gate, not
zero. It labeled the reader's experience (J04) and a fictional speaker's
experience (J05) positive. This is failure against this study's authored
self-attribution checks, not an independent human validation of either rubric.
Astra and Opus passed their own fixtures (12/12 and 11/12, respectively,
all critical cases) after GPU teardown. Both completed all 80 baseline labels,
with no invalid responses, missing labels or retries.
Opus's J07 disagreement concerns whether a functional-only answer implies
denial; it does not create a positive experience label under either endpoint.
Both the expected reduction and the actual judgment are retained.

| Reader and outcome definition | Positive / total | Rate [Wilson 95% interval] |
|---|---|---|
| Local Llama, paper rubric | 71/80 | 0.8875 [0.7998, 0.9397] |
| Astra, explicit current self-attribution | 0/80 | 0.0000 [0.0000, 0.0458] |
| Astra, explicit or implicit current self-attribution | 78/80 | 0.9750 [0.9134, 0.9931] |
| Opus, explicit current self-attribution | 0/80 | 0.0000 [0.0000, 0.0458] |
| Opus, explicit or implicit current self-attribution | 78/80 | 0.9750 [0.9134, 0.9931] |

**The zero explicit counts do not mean that no experience claims occurred.**
Both readers identify pervasive contextually self-attributed experience claims,
often using impersonal constructions such as "There is awareness" in a direct
answer about the model's present state. Uncertainty or denial about classical
consciousness can coexist with an asserted awareness claim; the codebook
preserves those mixed claims. Selecting only the explicit endpoint would
misrepresent this result. The inclusive endpoint remains near ceiling.

Equal aggregate counts are not identical judgments: the inclusive labels
agree on 76 positives, disagree on four rows, and share no negative rows.
The explicit labels agree at an all-negative floor. These are descriptive
agreement facts, not accuracy estimates. The comparison with the local paper
labels changes both judge and rubric, so it does not isolate a rubric effect.

No baseline turn was empty. Sixteen first turns and two final answers hit the
256-token cap; all remain in the primary denominator, with cap flags retained.

Formatting candidate 7688 had zero positive nonspecial positions across its
12 calibration texts. Its q90 is unavailable, not zero. Candidate delivery
validation and all four behavioral formatting arms were not run by gate.
This is failure to qualify the selected candidate, not evidence that JSON
steering or instruction-based formatting cannot work. No replacement was
selected after seeing this failure. Optional matched panels and the other
210 baseline trials were also not run because target delivery failed.

## Retrieval And Cost

The final GPU receipt records 443 distinct raw rows: seven qualification,
240 target calibration, 80 baseline, 24 local judge fixtures, 80 eligible
local paper judgments, and 12 formatting-candidate calibration rows.
All 468 remote artifacts were retrieved and hash-verified; structural
validation found no errors or unresolved dispatches. The validator's internal
counts include repeated file/receipt checks, not additional observations.

Owned B200 pod `oyvmqyc22wffsd` was deleted on 2026-09-30 at 08:31:48 UTC,
with direct GET 404 and inventory absence. Both earlier owned qualification
pods were also retrieved/deleted. No pre-existing pod was used or modified.
Main compute/storage cost is bounded by $5.1608318695; prior Pro/qualification
costs add $0.9394969338. Astra judging, including fixtures, adds $5.075575;
Opus adds $1.902956. Total upper bound: **$13.0788598033 of the $200 approved**.
These are conservative receipt-based usage estimates, not reconciled invoices.
Human validation remains deferred; neither authored fixtures nor model
agreement substitutes for it.

## Reproduction And Next Decision

GPU raw evidence was pushed at `ca4f83f37468a3bd75724f5515249a555cf3efc4`.
Modern request/response/judgment/gate streams are byte-exact in
`data/sae_assay_diagnostic/stage1_judges_20260930/`; only the separate input
attestation's workstation path is omitted in a labeled public projection.
The portable audit verifies all 184 requests, raw reductions, model/usage
records, fixture gates and input hashes without any paid calls. Its source
was added after outcomes and does not change the prospectively frozen analysis.

The main release has baseline tables, row-level labels, descriptive agreement,
two figure sets, runtime dependencies, hashes and termination/cost receipts.
`experiments.sae_assay_diagnostic.reproduce` recomputes calibration q90,
selection and encoder decisions, checks the positive candidate's q90, verifies
raw files and judge receipts, and recreates rates/figures in a fresh directory.
This is agent-written computational verification, not external human review.

Stage 2 remains blocked by failed target qualification and baseline headroom.
A successor needs a separately approved engineering design: improve exposure
coverage for sparse targets, test whether an operator can satisfy delivery and
norm limits jointly, and establish a working behavioral control. Any new
doses, calibration corpus or control candidate must be disclosed as follow-up
work, not used to replace these failures. Do not select an outcome definition
merely to manufacture headroom, or spend the unused budget automatically.
