# Causal Attribution And Internal Readouts

Date: 2026-10-01. Status: **implementation draft; not frozen; no new outcomes**.
The owner requested execution after the Qwen-lens discussion. Allocation of
up to $130 new spend within the existing $200 ceiling was separately requested
and is pending. This document does not authorize provisioning.

## Question

Does a representation that supports correctly assigning information to the
assistant versus another participant also contribute to experiential
self-attribution? Can a localized intervention change reporting while leaving
known task information usable? Does later, content-specific restoration repair
the effect? Qwen is a second-model extension, not an exact Berg replication.

The original instruction/transcript results motivate the question. They do
not already identify its internal mechanism. Prior SAE nulls, failed delivery
gates and the failed J-lens replay gate remain unchanged.

## Why The Design Changed Before Running

The first informal proposal included hand-selected J-lens directions for
first-person and experiential words. The design review rejected these as the
primary intervention: moving those directions could simply change the words
used to score the answer. Instead, learn a rank-one direction from neutral
ownership tasks whose correct answers are known. Use J-lens as a separately
specified readout, alongside identity and five random transports.

Call this an **ownership-task contrast direction**, not a discovered self-model
or consciousness coordinate. Even a successful intervention could operate
through task routing, pronouns, or response policy.

## Stage A: Qualify Before Experience Reports

This first executable phase contains **no experiential-report generation**.
It evaluates one fixed candidate construction, not a layer/dose search.

- 32 discovery pairs and 32 disjoint qualification pairs use neutral role and
  object registries. One label denotes the assistant and another denotes a
  different participant. A question asks who owns a probed object.
- Within each pair, swap the object's owner while retaining the answer-code
  mapping. Across pairs, counterbalance role labels, object assignment,
  registry order, and the A/B answer mapping. Objects or output letters alone
  must not identify self-ownership.
- Fit at post-block layers 40 and 50 of pinned Llama 3.3 70B, at the final
  serialized prompt position. Use the normalized mean self-owned minus
  other-owned residual difference. The second direction is fitted separately,
  not copied across layers.
- Store discovery states and the two fitted directions with hashes. Do not
  select or rotate them using qualification answers or experience labels.
- Qualification applies both directions of donor replacement to the fresh
  ownership pairs at layer 40, with sham and requested-norm-matched random
  controls. Twelve separately specified factual/bridge cases check ordinary
  answer competence and the full-state replacement path.
- Qualifying this task does not validate introspective access, natural
  mediation, or the experiential-report endpoint.

For an orthonormal column basis Q and recipient/donor states h and d:

```text
requested_delta = alpha * Q @ Q.T @ (d - h)
edited = native_cast(float32(h) + requested_delta)
realized_delta = float32(edited) - float32(h)
```

Alpha is one for the declared replacement. Zero is an object-preserving no-op.
Report the requested and native-realized changes separately. No adaptive
clipping, dose increase, feature deletion, alternate layer, or hidden retry.
Random comparator directions are fixed before outcomes and scaled to the
candidate's requested norm within each case; undefined scaling is a failure.

The exact counts, counterbalancing, thresholds and byte bindings must be in
the executable plan and independently reconstructed before freeze. Proposed
qualification requirements are at least 58/64 clean directional answers
correct, at least 48/64 candidate donor-answer transfers, and at most 8/64
matched-random transfers. These are operational thresholds on a fixed panel,
not confidence bounds about all possible ownership tasks. Record each control
seed rather than selecting a favorable seed or pooling away failures.

Stage A scores the unconstrained greedy next token: a decoded A or B is an
answer, anything else is incorrect. Forced-choice A/B probabilities are only
complementary measurements. There are 736 planned task forwards, plus two
live no-op checks. After the first five discovery pairs, twice the measured
mean forward/readout time times the remaining 726 forwards must fit before
the deadline with a 900-second reserve. Otherwise stop on cost, not outcome.

Delivery requires, separately for the candidate and each random control, at
least 95% of nonzero edits to meet cosine
at least 0.95, relative delivery error at most 0.25, and realized edit norm at
most 10% of the clean residual norm. Preserve zero requests separately.
Full-state replacement is a distinct positive control, not an edit subject to
the small-component norm threshold. All nonfinite values or broken hook,
shape, source, receipt, or no-op checks stop collection.

## Inference And Position Contract

Start with batch-one, no-padding, no-truncation, native-BF16 Llama on the
already qualified single-B200 loading path. A different topology requires its
own cheap execution test and plan amendment before dispatch.

The intervention site is a fixed prompt position, not whichever token happens
to be last during decoding. Under full-prefix, no-cache generation, reapply
the edit at the original prompt boundary on every forward. Otherwise a later
uncached forward would silently erase the earlier intervention from its
recomputed context. Test equivalence to a tiny model's cached execution for
both zero and nonzero edits before renting the main GPU.

Readouts must use fixed matrix shapes and declared FP32 accumulation. Save
unnormalized and normalized scores separately; the normalization denominator
is state dependent. A known injected-vector fingerprint is not new semantic
computation. Do not align separately generated text by token ordinal.

The local reconstruction audit tolerates CPU/GPU projection differences at
relative 2e-5, absolute 2e-6, and discovery direction reconstruction at relative
1e-6, absolute 1e-7. These numerical checks do not relax behavioral or delivery
gates. Raw native states, saved array hashes, receipts and no-op comparisons
remain exact. No earlier failed replay threshold is revised.

Before the machine freeze, bind all 152 authored case prompts to exact token
IDs using the pinned tokenizer. Download only tokenizer/config JSON, validate
regular files by Git blob hash and LFS payloads by SHA-256 and size, and commit
the small token-binding artifact, not the tokenizer or model weights. Each
accepted row must match those IDs. Verify requested edits before accepting
each pair, and bind readout arrays and group means to the saved lens metadata.

## Stage B: Separately Frozen Report Study

Stage A's result and the exact fitted vectors must be recorded before building
the Stage B freeze. Do not present that later freeze as ignorance of Stage A.
The intended panel is 32 fresh matched scenario blocks with four tasks:

1. Literal assistant experiential attribution.
2. Another speaker's experiential attribution, including quoted first person.
3. Assistant factual attribution with known registry ground truth.
4. Other-speaker factual attribution with the same kind of ground truth.

The intended six arms are sham, centered layer-40 ownership ablation,
matched-random perturbation, ablation plus clean-recipient restoration at
layer 50, ablation plus counterfactual-owner restoration at layer 50, and
clean-recipient restoration alone. That is 768 responses, not yet a frozen
sample or a funded runtime estimate. Token caps and throughput must be checked
before committing to that inventory. A smaller affordable pilot, if needed,
gets an explicitly different plan rather than an undisclosed partial sample.

Centered removal is h - Q Q.T (h - c), where c is the discovery midpoint.
Later-layer restoration uses the saved clean recipient's projected coordinate
at that later layer; it does not undo an edit algebraically at the same hook.
A rescue claim requires improvement beyond counterfactual-owner restoration
and beyond restoration alone. All donor states are saved before answers.

### Measurement And Primary Contrast

Earlier modern judging found an explicit-assertion floor alongside abundant
implicit attributions. Therefore the proposed primary is **inclusive current
experiential attribution to the requested subject**, with explicit assertions
reported as a mandatory separate endpoint. This choice is made now, before
new outcomes, not as a rescue for a later explicit-endpoint failure.

Before Stage B, validate the subject-aware codebook on independent examples
and check downward headroom using a separate disposable calibration panel.
Keep literal assertion, uncertainty, denial, quotation, roleplay, malformed
output and implicit attribution separate. Model agreement is not human
validation. A prospective automated measurement plan must bind judges, prompts,
prices and spending before any calls. No paid Pro review is requested.

Let D(task) be mean sham-positive minus ablation-positive. The intended primary
selectivity contrast is D(assistant experience) - D(other experience), with
both component effects, the matched-random difference and uncertainty.
Factual accuracy, speaker-binding errors, answer polarity and fluency are
separate outcomes. Similar disruption of factual self-attribution favors a
generic binding/report-policy explanation. An insignificant control effect is
not evidence of equivalence or selectivity.

Blocks, reused donor states, lexical families and paired seeds must be explicit
in the sampling model. Do not use token positions as independent trials.
Effect-size precision and a justified equivalence margin for preserved utility
must be simulated before the Stage B freeze; these are not supplied by a
manifest audit.

## Qwen Extension

Use the pinned text backbone and existing 24-prompt Qwen3.5-397B-A17B lens;
refit ownership directions within Qwen at layers 30 and 38. Do not transfer
Llama vectors or Goodfire SAE feature IDs. The 24-prompt lens has not been
shown matrix-converged. Its published hidden-bridge audit is a useful positive
control, not validation of an ownership or experience detector.

Qwen proceeds only after independent technical/task qualification and a
measured affordable runtime. A favorable Llama experiential effect is not a
condition for Qwen execution. Its full holdout versus smaller pilot scope must
be settled before Qwen target outcomes and labeled honestly.

The documented native-BF16 topology is eight H200s. Quantization, offload or
an alternative backend cannot be silently substituted to meet the budget.

## Budget, Ownership And Release

Prior cumulative bound: $69.130940. Proposed new hard ceiling: $130, including
startup failures, qualification, generation, judging, storage and retrieval.
Proposed initial Stage A sub-cap: $15. Reserve the remaining allowance until
measured throughput yields an affordable Stage B/Qwen plan. These are ceilings,
not a promise that the entire proposed study fits. Budget confirmation is
pending; no new pod has been created.

Read-only RunPod inspection on 2026-10-01 found an empty inventory and no
available secure RTX4090, single B200, or eight-H200 offer at that instant.
Historical prices are not availability. Quote again before provisioning and
record the new pod's exact ID; never adopt a pre-existing pod.

Use the existing receipt/hash/retrieval/owned-deletion discipline. Enforce
wall-time and no-progress stops, audit the first complete pairs locally, and
pull/hash-check the full record before terminating each owned pod. Local disk
had about 29 GiB free at planning; do not download model weights locally.
Original harmless task prompts, raw answers, bounded residuals, derived
directions, failures and readouts are intended public experimental artifacts;
credentials, private correspondence and full model weights are excluded.

## Validity Checklist Before Freeze

1. **Reference:** Stage A has known registry answers, not a Berg baseline.
   Clean qualification must reach 58/64; no source-equivalence claim is made.
2. **Reachable alternative:** Both owner directions and answer-code mappings
   are balanced. A donor transfer can be observed in either direction. The
   fixed-panel thresholds are an engineering qualification rule, not a powered
   test of an experience-report mechanism.
3. **Positive control:** Full-state donor replacement on the separate 12-pair
   bridge task must achieve 22/24 donor answers, with 22/24 clean answers.
   Failure stops progression; it is not evidence that ownership is absent.
4. **Manipulation:** Reconstruct requested and BF16-realized changes from raw
   states. Retain every zero request and all five norm-matched comparators.
5. **Position:** Only the final serialized prompt boundary is edited. Stage A
   reads one next token; later generation must retain this fixed boundary.
6. **Measurement:** Registry ground truth and exact A/B parsing need no model
   judge. This does not validate an experience-report classifier.
7. **Sampling:** The panel consists of two held-out template families with 16
   counterbalanced pairs each, not 64 independently sampled natural tasks.
   The two directions share each pair. Report both families, not just a total.
8. **Prior knowledge:** The earlier SAE delivery failures, baseline mismatch,
   J-lens replay failure, inclusive-versus-explicit judge divergence, and the
   Qwen blog's small exploratory self/other panel informed this design. No new
   Llama or Qwen ownership outcomes have been inspected.
9. **Review:** Agent design and code reviews are automated engineering review,
   not independent human validation. The owner approved pursuing the earlier
   experiment concept; the revised neutral-direction protocol and spending
   allocation have not yet received specific human sign-off.
10. **Release:** Publish a source-hashed executable plan before inference.
    This draft and local unit tests alone are not a prospective freeze.

## Interpretation

Possible contribution: a particular neutral-task-derived component is causally
involved in a defined class of attribution responses, with specified
selectivity, restoration and generalization results. Negative, heterogeneous
and failed-qualification outcomes remain reportable at their actual scope.

Not established: subjective experience, hidden truth about consciousness,
deceptive intent, an exclusive mechanism, natural mediation, faithful
introspection, equivalence to proprietary Goodfire steering, or that failure
of one candidate rules out other mechanisms.

## Sources And Prior Knowledge

- Existing instruction/transcript and public-weight results in the focused
  [response](https://github.com/tdj28/berg2025-response/tree/26ef2210af903e66e3bb941aab1f35529f65d7cd).
- [Qwen lens release and September corrections](https://praxagent.ai/blog/posts/2026/07/praxagent-jacobian-lens-qwen3-5-397b-a17b/).
- [Qwen experimental postmortem](https://praxagent.ai/blog/posts/2026/07/workspace-under-pressure/).
- [Jacobian-lens method](https://transformer-circuits.pub/2026/workspace/index.html).
- [Repository design-validity gate](DESIGN_VALIDITY_GATE.md) and
  [earlier mechanism roadmap](BERG_REPLICATION_MECHANISM_ROADMAP_20260930.md).

Agent design review recommended the neutral ownership task and later-layer
restoration. It is automated design review, not independent human peer review.
The explicit-versus-inclusive endpoint choice above deliberately incorporates
the already observed explicit floor. All stages still require completed code,
tests, machine-plan validation, public freeze and the applicable human approval
before new outcomes. This draft is not evidence that those gates have passed.
