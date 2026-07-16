# V9 director-level brief: target-blind J-lens calibration audit recovery

Status: prospective recovery review before any successor audit is authorized.
This brief synthesizes the decision-relevant design. It intentionally excludes
source code, tests, raw rows, model outputs, full receipts, and logs. Those are
validated by separate exact-byte and execution gates and are not within the
provider review claim.

## Decision requested

Decide whether one fresh, audit-only attempt may finish the already completed
target-blind calibration transaction after a late mechanical launch failure.
The review should answer two big-picture questions:

1. Does the inherited calibration design still support its narrow claim?
2. Given the disclosed failed attempts, would a new audit be a legitimate,
   non-adaptive recovery rather than an outcome-informed rerun?

The desired review is not a line-by-line implementation certification. A
favorable verdict authorizes movement to the mechanical launch gates; it does
not replace those gates.

## Scientific question and strict claim boundary

The underlying study is a generic-vector calibration for a later SAE/J-lens
experiment on Llama 3.3 70B. It asks whether signed, generic residual edits are
delivered faithfully at layer 50 and whether released Jacobian-lens maps
predict their downstream effects. It does not inject an SAE feature, use a
deception or consciousness prompt, generate behavioral answers, or test a
claim about consciousness.

The maximum valid conclusions are limited to this fixed panel and runtime:

- whether native BF16 hooks deliver generic 2%, 3%, 4%, and 8% layer-50 edits
  with prespecified vector-fidelity and common-mode tolerances;
- whether realized source edits are locally dose-linear over 2%, 3%, and 4%;
- whether each released real J map predicts the observed final signed delta
  better than identity and five fresh random-J controls; and
- a descriptive account of downstream response linearity, which is an outcome
  rather than a technical delivery gate.

The study cannot establish SAE-steering validity, semantic wake, deception,
self-reference, consciousness, subjective experience, introspective accuracy,
hidden belief, intent, or behavioral change. It also cannot generalize from the
eight fixed prompts to a prompt population. The independent unit is the prompt,
and the prompt count is not confused with the 125-prompt fitting metadata in
the released J artifact.

## Smallest decisive inherited design

The model, J-lens checkpoint, model/SAE revisions, runtime, hardware class,
numeric settings, prompt strings, seeds, directions, token panel, intervention
coordinate, layers, transports, estimands, thresholds, and claim rules were
frozen before the calibration transaction.

The panel contains eight mundane prompts and three independently seeded
isotropic directions. These directions are not SAE decoder columns and carry
no target feature identity. At layer 50, the runtime forms signed central
contrasts at 1%, 2%, 3%, 4%, and 8% of clean source-residual RMS. The 1% dose is
diagnostic only. The 2/3/4% band tests local linearity, 3% is the primary
transport/readout dose, and 8% checks the wider delivery range. Plus and minus
branches share the same clean prefix cache and differ only in the signed edit.

The hook is applied exactly once after transformer block 50 and before block
51. Layers 45--49 must remain byte-identical to clean, layer 50 records both
pre-edit and explicit post-edit states, and layers 51--78 record actual
post-edit states. Each released J map predicts the final block-79 residual
delta. Real J, identity, and five freshly seeded random-J transports are
compared on the same frozen 2,048-token panel.

The design has 120 signed pairs, 24 local-linearity sites, and eight prompt
clusters for inferential resampling. The primary summaries use prompt-cluster
bootstrap intervals and frozen paired contrasts. No generation or external
judge is involved. Missing or duplicate rows, nonfinite values, hook-count
errors, pre-layer changes, severe degeneration, or provenance mismatches are
fail-closed events rather than analyst exclusions.

Interpretation is gated in stages. Native delivery and common-mode safety must
pass before J-shadow claims are eligible. Local realized-source linearity is
separate from downstream model linearity. The real-J comparison is evaluated
against identity and the random-J family rather than against a zero-only
baseline. Positive, null, mixed, and invalid outcomes therefore have distinct
prespecified readings:

- delivery failure invalidates transport conclusions;
- successful delivery with weak realized-source linearity narrows the usable
  dose range;
- successful delivery but weak real-J advantage is evidence against useful
  released-J readout on this panel;
- a real-J advantage without downstream linearity supports readout utility but
  not a linear causal model of the network; and
- all successful calibration gates permit, but do not predetermine, a later
  separately frozen SAE experiment.

## What has already happened

The expensive model-forward transaction completed atomically on the retained
network disk. It wrote a completion receipt and a closed raw-file ledger. The
raw transaction is immutable; a successor may only rehash it and independently
recompute the previously frozen compact audit. It may not invoke the model,
render a target prompt, construct a target feature vector, add rows, replace a
row, change a dose, or modify an estimand or threshold.

The first audit stopped without compact publication because its loader required
the available J-map inventory to equal the required study inventory. The
authentic pinned checkpoint contains maps for layers 0--78, while this study
requires only 45--78. The already frozen runtime correctly accepts the required
set as a subset. The recovery adapter therefore rehashes the same checkpoint,
requires every study layer, records unused extras, exposes only the required
maps to the unchanged scientific calculations, and fails if a required map is
missing. A synthetic scientific-equivalence test projects the old and recovery
paths onto every scientific output field and requires byte identity.

A subsequent prospective host attempt ended before the audit entry point when
the container lacked privileges for a planned read-only bind mount. No attempt
marker or compact output was created. The design switched to same-process
Landlock confinement: source, tests, inputs, dependencies, and historical
evidence are protected, while only a new empty output directory is writable.
That operational change was reviewed and qualified separately.

Another attempt was stopped by review/adjudication bookkeeping, and later
attempts repaired the issue bridge, repository-free active execution,
hash-and-exec handoff, independent verifier, and complete launch-wrapper
inventory. The prior V8 adjudication records B17--B21 as fixed and I10--I13 as
fixed, while rejecting I14 as unnecessary scope expansion. It concluded that
the then-reviewed design was ready to execute. Those prior reviews are
historical evidence, not authority to reuse a consumed attempt.

## B22: why the last attempt failed

The F12 recovery created its one-shot authorization, entered Landlock, and
claimed its exclusive attempt marker. It then stopped before compact
publication because the final `env -i` launch omitted the already frozen
`CUBLAS_WORKSPACE_CONFIG=:4096:8` precondition. The auditor checked this late,
at artifact-device setup. This was an absent environment assignment, not an
observation of numerical nondeterminism.

Raw rows had been opened, and row-level quantities may have been recomputed
before the late guard. No compact metric, summary, or publication receipt was
written or emitted in the retrieved logs. The exact pod was deleted, the
attempt namespace was closed, and its authority is permanently consumed.
Nothing learned from row-level values was used to alter the plan. This access
is nevertheless disclosed because it is the strongest concern about whether a
retry could be adaptive.

The proposed B22 repair is intentionally mechanical:

- carry exactly `CUBLAS_WORKSPACE_CONFIG=:4096:8` through every sanitized
  environment that can reach artifact-device setup;
- make the independent offline verifier require the same value;
- execute the real artifact-device guard on a disposable B200 under missing,
  wrong, and correct values, requiring rejection, rejection, and acceptance;
- rerun the complete focused suite on the exact frozen source/test inventory;
  and
- issue an entirely new pod, authorization, attempt ID, output namespace,
  deadline, and spend envelope only after review and all mechanical gates pass.

The repair does not change any raw input, plan row, scientific calculation,
threshold, aggregation, bootstrap seed, outcome interpretation, or claim.

## Why a retry is argued to be non-adaptive

The case for a single successor rests on precommitted separation between
scientific and operational information:

1. The model transaction is complete and immutable. There is no new sampling,
   model forward, prompt, direction, or intervention.
2. The compatibility correction concerns checkpoint inventory shape, and the
   CUBLAS repair concerns a frozen launch precondition. Neither depends on an
   observed scientific value.
3. The recovered audit calls the inherited scientific functions and applies
   the inherited estimands and decision thresholds. Scientific-equivalence is
   checked over the full projected output, not a handpicked headline metric.
4. Each failed attempt has a unique consumed authority and closed namespace.
   Failed outputs cannot be merged with a successor.
5. No compact result existed after any failed audit. For B22, possible internal
   recomputation is disclosed and treated as contamination risk even though
   the values were not published or used.
6. The successor is one-shot and fail-closed. Another scientific or
   post-publication failure does not silently authorize a loop.

The strongest objection is that opening raw rows and recomputing quantities
could create unrecorded human knowledge. The mitigation is not to pretend that
access did not occur. It is to preserve the exact scientific design, forbid any
scientific change, show that the failure arose from a deterministic mechanical
precondition, keep the review packet outcome-free, and require a fresh external
judgment before the next authorization. If those facts are insufficient, the
review should say that no retry is defensible.

## Leakage, provenance, and exact-byte controls

The provider receives only the six high-level artifacts listed in the review
manifest. Full receipts remain in the repository/retained evidence and are
mechanically validated before authorization. The compact evidence summary is
derived field-for-field from those receipts; it is not a substitute for them
and does not ask the reviewer to rederive their claims.

Before any final launch:

- a C14 commit freezes all executable and test bytes;
- local and disposable-B200 test receipts must name C14 and the same complete
  source/test inventory;
- the disposable host must demonstrate same-process Landlock enforcement,
  target-free CUDA compatibility, zero model forwards, zero target prompt
  renders, zero target vectors, and the B22 three-way guard regression;
- E14 freezes the exact compact provider packet after those evidence files and
  their derived summary are present;
- the paid response and local adjudication are the only permitted additions in
  F14;
- Git ancestry must be C14 <= E14 <= F14;
- source/test bytes must not change from C14 through F14, and packet bytes must
  not change from E14 through F14; and
- the final controller, hash-exec gate, local supervisor, retrieved-receipt
  validator, and repository-free offline verifier independently repeat the
  relevant identities before compact publication is accepted.

The exact source and tests are deliberately not in this director packet. A
provider verdict cannot be cited as evidence that the implementation is
correct. It can only judge whether this architecture and recovery rationale are
sound enough to proceed if the mechanical checks succeed.

## Feasibility and proportionality

No new model-forward collection is proposed. The retained raw data stay on the
network disk and are not committed or downloaded to the laptop. The audit uses
one B200 for a bounded window because exact comparison is tied to the original
hardware/runtime numerical path. Qualification uses a disposable B200 and no
target computation. Each pod has a provider-creation-bound deadline, watchdog,
spend ceiling, exact ownership receipt, and deletion audit. A failed gate stops
before a final scientific pod is claimed where possible.

The review itself is also intentionally proportional: one director-level Pro
call, a request below 60,000 characters and 20,000 counted input tokens, no
tools, no raw data, and a small fixed budget. A favorable review is followed by
local adjudication; it does not directly trigger paid GPU execution.

## Decision table for this review

- **READY TO FREEZE:** the inherited narrow claim remains supported by the
  design, and one new audit-only attempt is defensible subject to every
  mechanical gate above.
- **READY AFTER SPECIFIED FIXES:** only compact top-level prose, claim, or
  decision-rule changes are needed; any packet change requires a new freeze and
  review rather than silent editing.
- **NOT READY TO FREEZE:** retry legitimacy, construct validity, controls,
  falsifiers, decision rules, leakage protection, or feasibility has a
  substantive unresolved flaw.

Please preserve strong elements explicitly, especially the target-blind scope,
signed paired design, staged eligibility gates, identity/random-J controls,
prompt-cluster inference, immutable raw transaction, scientific-equivalence
projection, one-shot authority, and honest boundary between provider judgment
and local exact-byte verification.
