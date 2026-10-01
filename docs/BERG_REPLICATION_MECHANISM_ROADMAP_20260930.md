# Replicate The Effect, Then Identify Its Mechanism

Date: 2026-09-30. Status: design draft, informed by completed outcomes.
This is not a frozen executable protocol or a new result. No additional paid
run is authorized by this document. Existing releases and failed gates stand.

## Question And Order Of Work

First test whether the reported suppression-minus-amplification report contrast
is reproducible under source-aligned public execution. Then test what computation
accounts for any reproduced effect. Keep both a language/framing explanation
and a functional internal-access explanation open to evidence.

The next milestone is a notebook-aligned behavioral comparison with delivered
edit telemetry and bounded paired J-lens capture. Further exposure-corpus
expansion for the separate active-support operator is not its prerequisite.
An additive intervention can be delivered when the native SAE coordinate is
zero; that does not make it an ablation of naturally occurring activity.

## What We Already Know

- The 1,500-trial public NF4 study already used additive steering and did not
  recover the specified contrast. It used the paper induction, temperature
  0.5 and 256-token turns. Do not attribute its result to later repair operators.
- The source notebook requests additive steering on both turns, temperature
  0.6, 128-token turns, and the same seed on both calls. Its induction differs
  from the paper. Its backend scaling, precision and token scope are unknown.
- The latest mixed-precision repair instead implements capped,
  activation-dependent edits. Its engineering successes and exposure failures
  answer a different question from notebook-style additive steering.
- Our BF16 J-lens study found large signed paired readout changes but generated
  no answers. Its post-state-only target-attribution reader was at chance
  (AUROC 0.4998). Neither result establishes the mechanism of the separate NF4
  behavioral study. Feature 23893 did not share the other features' fingerprint.
- The J-lens v2 replay gate failed. Its later analyses remain exploratory.

## A. Source-Aligned Behavioral Replication

1. Keep notebook and paper tracks separate. Produce a machine-checked table of
   prompt hashes, chat serialization, caps, decoding settings, seeds, scoring,
   intervention sites and token scope. Extract notebook prompts at runtime
   from its pinned upstream source; do not vendor unlicensed notebook code.
2. Retain all six accepted IDs. Start from notebook seed/dose settings for the
   source comparison; reserve disjoint seeds for a later held-out extension.
   A matching seed number does not equate RNG streams across API backends.
3. Specify public additive units and delivered vector norms. Preserve zero as
   a true no-op. Any calibrated scale is a separately declared sensitivity,
   not an attempt to tune coefficients until the source result appears.
4. Compare baseline, signed target interventions and frozen matched controls.
   Measure per-position delivery, re-encoding, saturation and output quality.
   A weak natural-coordinate suppression claim must not be substituted for
   successful vector addition, or vice versa.
5. Retain the source judge as a replication endpoint, alongside the separate
   explicit/inclusive codebook. Store raw judge responses. Failed calls are
   missing, not denials; disclose any source-parser sensitivity separately.
6. Audit the baseline difference before interpreting the steering difference.
   Predefine a bounded bridge across prompt, cap, temperature and precision;
   do not change them adaptively to obtain a preferred baseline. A high
   baseline limits increases but still permits amplification-driven decreases.

Freeze sample sizes, pairing, dose grid, control panels, primary contrasts,
multiple-comparison treatment and cost stops before new outcomes. Preserve
uncertainty appropriate to the actual sampling design, including reused
induction text and seeds. Previously observed outcomes are design information,
not fresh confirmation. No symmetric headroom gate may be silently changed;
any directional successor must explicitly supersede its scope.

## B. Read Internals In The Same Experiment

Reuse the pinned Llama 3.3 70B lens in the existing J-lens protocol; do not fit
a new lens before trying the one we have. Save a bounded, preselected panel of
layer/token states from the behavioral run, with raw generations and hashes.

Free-running continuations answer the behavioral question. Fixed-prefix replay
answers a different question: what does the intervention change internally
when the text is identical? Replay both arms on both clean and steered source
prefixes using a frozen alignment/weighting rule. Keep these estimates separate;
otherwise changed words can masquerade as an internal steering mechanism.

For the pinned readout R at layer l, inspect
`delta_r_l = R_l(h_steered) - R_l(h_clean)` under matched prefixes. Compare this
with the static fingerprint of the injected vector, identity readouts, the
five fixed random-J controls, and matched SAE interventions. A persistent
fingerprint alone is not evidence of an additional computation.

Candidate readouts: roleplay/fiction framing, experiential language,
self/other reference, and uncertainty/refusal. Select lexicons and any candidate
directions on discovery material, not the held-out report outcomes. Keep the
behavioral judge independent of readout-token selection. Validate exact tensor
shapes and dtypes on the executed replay path before freezing; do not repeat
the v2 mistake of treating high correlation as passing an absolute-error gate.

## C. Turn Candidate Explanations Into Causal Tests

| Candidate explanation | Discriminating follow-up |
|---|---|
| Instruction-driven experiential register | Cross self/other target with experiential/functional register; ablate components of the actual induction. |
| Fiction/persona framing | Compare literal assistant, quotation and fictional-speaker contexts; patch the candidate framing component while retaining the instruction. |
| Hedging/refusal or affirmation policy | Measure uncertainty, negation, refusal and unrelated proposition judgments alongside experience reports. |
| General experiential-language computation | Test first-person reports, third-person experience and fiction; check whether the same intervention affects all three. |
| Functional access to internal state | Test whether reports track randomized internal perturbations not disclosed in the prompt, with sham and perturbation controls and independent task endpoints. This is a separate extension, not a synonym for changed experience reports. |

The first causal follow-up should patch a small candidate component, not erase
the full residual stream. For an orthogonal projector P learned/fixed before
held-out testing, compare the steered state with
`h_patch = h_steered + P (h_clean - h_steered)` at a fixed layer/token window.
Test the converse transfer into a clean state and a restoration control.
Compare rank/norm-matched random patches and sham hooks; measure fluency and
unrelated task performance. Declare source/recipient alignment before execution.

The J-lens vocabulary directions form an overcomplete frame, not automatically
a unique low-rank subspace. Specify candidate vectors, rank selection and
orthogonalization explicitly. Do not label projection onto every vocabulary
direction as selective "J-space ablation."

A held-out effect abolished by removal and restored by replacement supports a
causal role for that component under these interventions. It does not by itself
establish exclusive or natural mediation. If behavioral replication fails,
report the implementation-dependent outcome and internal fingerprints without
claiming to explain a behavioral effect that was not observed.

## Execution Milestones

- [ ] Build the source-to-public configuration table and dry-run payload checks.
- [ ] Validate additive delivery plus bounded J-lens capture on synthetic and
      existing saved fixtures; no target generation needed for this step.
- [ ] Freeze the executable behavioral plan, budget and exact-path checks.
- [ ] Execute and release replication, paired internal readouts and all failures.
- [ ] Freeze a separate held-out ablation/patching study after discovery.

Stay on Llama 70B first. Reuse existing weights, lens, controls and capture
infrastructure. Do not expand to another family or a large feature sweep before
the source-aligned question is answered. Preserve every technical failure;
stop for broken delivery or corrupted data, not for an unfavorable effect.

## Sources And Existing Evidence

- [Berg et al., version 2](https://arxiv.org/html/2510.24797v2).
- [Pinned AE notebook](https://github.com/agencyenterprise/steering-api-examples/blob/d50dc4ba125dde98666a60e3115a6a476dabea10/deception-features/deception_features.ipynb).
- [Gurnee et al., Jacobian lens](https://transformer-circuits.pub/2026/workspace/index.html).
- [Existing J-lens protocol](LLAMA70B_SAE_JLENS_PROTOCOL.md),
  [v1 results](LLAMA70B_SAE_JLENS_RESULTS.md), and
  [v2 failed-gate results](LLAMA70B_SAE_JLENS_V2_RESULTS.md).
- [Stage 1 baseline/measurement results](SAE_ASSAY_STAGE1_RESULTS_20260930.md)
  and [separate precision/exposure results](SAE_ASSAY_EXPOSURE_RESULTS_20260930.md).
