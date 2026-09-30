# Native SAE Replay On Saved States

This is prospectively specified engineering after the original diagnostic and
offline geometry results. It is not fresh semantic validation, a proprietary
replication, or a consciousness-report experiment. Source release: `90765ea`;
offline development: `c1aa71b`. Neither historical release is modified.

## Question And Fixed Design

Does the 4%-norm-capped active-support intervention remain effective after its
FP32 request is added to a saved BF16 hidden state, rounded once to BF16, and
read through the pinned full-width native SAE? The prior geometry predictions
are not the answer to this question.

- Use all 544 saved clean residual captures, with original text IDs, token
  metadata and historical calibration/validation labels. No row selection.
- Load only the pinned Goodfire SAE, not Llama weights. The SAE revision and
  SHA-256 are inherited from the original diagnostic and checked before load.
- Run zero, suppression and amplification. The nonzero operator is the
  published active-support projection with change 0.75 and continuous norm
  cap 0.04. Do not use the coverage-losing 2-4% window as the intervention.
- Solve the saved six-row Gram geometry in float64, cast its coefficients to
  FP32, form the request using the selected encoder rows in FP32 with TF32
  disabled, add in FP32, then cast once to BF16. Record the continuous intent
  separately from the actual FP32 request and rounded delivered edit.
- Native encoding is `relu(F.linear(h, E, b))`, shape `[1,8192]` to
  `[1,65536]`, one position at a time. Select target columns afterward. The
  selected-width encoder is a diagnostic, never the canonical measurement.
- Zero returns the original state; all-inactive requests are unchanged. Do
  not pad small requests with unrelated noise or redefine realized as requested.

## Measurements And Decisions

For every position retain requested, realized and clean norms, cosine,
relative error, zero identity, active support, continuous scale, native and
selected-width before/after activations, FP32 preactivation references, full
SAE sparsity, reconstruction error, and non-target activation-change magnitude
and count. Save rows and hashes, not model/SAE weights.

Use the unchanged component limits as descriptive engineering gates: at least
95% of nonzero requests have cosine >=0.95 and relative error <=0.20; at least
95% of realized nonzero edits are <=5% of clean norm; each of six IDs has
>=100 active nonspecial positions in >=6 texts, and its median suppression
after/before is <=0.5 or amplification achieved/requested increment >=0.5.
Compute these separately by sign and historical split, with exact denominators.
Report selected-width/native decision disagreement without replacing native.
Even passing these components cannot qualify the behavioral assay: no fresh
states, downstream NLL, behavioral positive control or baseline headroom test
is included. No confidence interval treats tokens as independent observations.

The replay GPU may differ from the original B200. Measure exact equality,
maximum absolute difference, and active-support changes versus the recorded
native baseline on every state. Report both original and replayed exposure.
Any difference prevents a claim of exact historical replay, but is not itself
evidence of a broken implementation: this study explicitly measures native
delivery on the recorded new hardware. Full-model use still needs hardware-
matched validation. Input hashes, token IDs, selected promoted preactivation
and norm reconstruction must pass their technical checks; zero must be exact.
The preactivation check allows absolute error at most
`1e-4 * max(1, abs(original))` per coordinate; clean norm relative error must
be at most `1e-5`. These technical tolerances do not authorize replacing the
native outcome with the promoted-FP32 diagnostic.

## Execution And Failure Rules

The source-hashed plan, runtime, analysis and validators must be pushed before
any real SAE output. CPU tests use synthetic small dictionaries only. On a
newly created cheap CUDA pod, run and record those tests before loading the SAE.
Audit the first five complete state rows locally before releasing bulk work.
Estimate remaining runtime from that shard; stop rather than exceed the timer.
Nonfinite data, malformed inputs, hash drift, or incorrect zero stop execution
and retain the failure. Scientific efficacy/fidelity/exposure failures are
reported and do not trigger tuning, retries or omission of later states.

RunPod replay cap: $4 including provisioning, storage and retrieval, within the
existing $200 authorization. Carry $27.3845359753 prior spending forward. No
new paid reviewer, judge, full-model generation or borrowed pod. Keep a local
monitor, retrieve and hash-check artifacts before deleting the newly owned
pod, and verify deletion with direct GET 404. Partial completion is incomplete,
not a negative scientific result.

The fixed device is one secure RTX A6000, 48 GB, with compute price ceiling
$0.53/hour and a conservative $0.10/hour storage allowance. The hard timer is
two hours including ten minutes reserved for retrieval; availability and price
are checked again at dispatch. There is no automatic hardware substitution.

## Exposure Follow-Up

Separately prepare activation-enriched discovery and family-disjoint fresh
validation texts for all six IDs. Do not select validation examples by their
activations. The saved-state replay cannot manufacture new exposure. A later
full-model screening run needs its own executable freeze and cost guard; it
does not launch automatically from this replay plan.
