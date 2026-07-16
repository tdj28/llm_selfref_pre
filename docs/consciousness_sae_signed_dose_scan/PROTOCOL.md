# Prospective protocol: signed residual-RMS dose scan v1

## Status and question

This document freezes an outcome-free exploratory design. It does not by
itself authorize a GPU run.

The experiment asks how a target-blind, generic layer-50 residual intervention
behaves across the full user-requested dose range, including where the response
ceases to resemble gentle steering. It estimates a signed curve from -30% to
+30% of each prompt's clean layer-50 residual RMS in 0.5 percentage-point
increments.

The entire curve is exploratory. There is no post-hoc winning-dose selection,
no deletion of inconvenient magnitudes, and no population-generalization claim.
The 3% point is only a storage-bounded reference for the full online J-lens
readout; it is not privileged as the best or primary curve endpoint.

## Frozen design

- Model: the public Llama 3.3 70B artifact pinned in `protocol.py`.
- Intervention boundary: zero-based block 50 output, post-block and before
  block 51, at the continuation position.
- Prompts: the eight mundane, target-blind prompts inherited from the completed
  calibration design.
- Directions: three fresh generic directions. Target SAE features and prompts
  from the consciousness paper are not used.
- Nonzero magnitudes: every integer basis-point value from 50 through 3,000 in
  steps of 50, corresponding to 0.5% through 30%.
- Branches: exact positive and negative BF16 branches for every prompt,
  direction, and nonzero magnitude.
- Zero: one shared clean continuation for each prompt. Zero is not duplicated
  across directions and is not represented as a signed intervention row.
- Full-curve outputs: positive, negative, central, and common-mode components,
  with requested and realized dose coordinates reported separately.
- Online J reference: 300 basis points (3%) across the frozen readout layers and
  transports, using the fresh fixed 2,048-token panel.

The machine grid therefore contains:

- 60 nonzero magnitudes;
- 8 prompts x 3 directions x 60 magnitudes = 1,440 signed pairs;
- 2,880 edited full-model forward invocations;
- 8 prefix and 8 shared-clean invocations; and
- 2,896 full-model forward invocations in total.

The reported curve has 121 signed coordinates when the single shared zero is
included: -3,000, -2,950, ..., 0, ..., 2,950, 3,000 basis points.

## Dose and estimand definitions

Dose membership is defined by integer basis points, not floating-point
accumulation. For magnitude `b`, the requested fraction is `b / 10_000` and
the requested edit norm is that fraction times the clean layer-50 source RMS.
The positive and negative branches use the same realized BF16 direction and
requested norm with opposite signs.

For a readout `y`, report the branches separately and derive:

- central signed response: `(y_plus - y_minus) / 2`;
- common-mode response: `(y_plus + y_minus) / 2 - y_clean`; and
- realized dose and direction fidelity from the archived pre/post residuals.

High doses are explicitly a stress regime. A dramatic effect at 20-30% must
not be described as evidence that the intervention is subtle, selective, or
mechanistically equivalent to natural activation.

## Delivery checks and interpretation

Requested-versus-realized fidelity and common-mode behavior are prespecified
measurement checks at 2%, 3%, 4%, and 8%. The 2%, 3%, and 4% points also retain
the predecessor's local-linearity diagnostic. Other grid points, including
0.5% and 1%, are retained and reported as diagnostics; a failed diagnostic
does not permit deleting a row.

The actual residual-state curve and the transported J-lens curve are different
objects. J-lens results are secondary and descriptive. J orientation and
BF16-versus-FP32 shadow checks gate J-projection claims only; they cannot rescue
or replace an invalid actual-state intervention curve. The learned J is not
assumed to outperform identity.

## Separation from the predecessor

The completed target-blind calibration influenced the design at the protocol
level only. Its compact result summary is hash-bound as design provenance.
No predecessor raw tensor, row, random direction, random-J control, token panel,
or runtime seed is loaded, pooled, or analyzed here.

Fresh namespaces are frozen for runtime state, generic directions, the fixed
token panel, random-J controls, and J-orientation fixtures. This successor also
uses a distinct raw-data namespace.

## Storage and reproducibility

Complete signed residual arcs remain on the RunPod network volume under:

`consciousness_sae_signed_dose_scan/consciousness_sae_signed_dose_scan_v1/raw`

The estimated raw payload is about 2.3 GB, with a hard 4 GiB run ceiling and a
required 64 GiB post-run free-space reserve. Raw residuals, logits, row-level
outputs, arithmetic tensors, archives, and runtime logs are never Git payloads.
Git may hold the prospective plan, source, documentation, hashes, and compact
audited receipts or summaries.

Archived residual arcs are the reproducibility substrate: they permit later
readout or vocabulary analysis without rerunning the 70B model. The independent
audit must rehash the plan and raw manifest, reject missing, duplicate,
non-finite, unmanifested, or partial data, reconstruct every signed realized
edit and the shared zero, and recompute the reference transport from the
archived tensors.

## Plan, smaller-model gate, and authorization boundary

The canonical prospectively frozen plan location is:

`data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716`

The builder is create-only and the validator independently reconstructs the
grid, counts, hashes, provenance, namespaces, and resource envelope without
importing the protocol module. The manifest is marked
`prospectively_frozen_exploratory_plan` and `execution_authorized: false`.

Before the 70B run, a pinned Gemma 2 9B IT model and a pinned public Gemma Scope
SAE execute one frozen neutral prompt, one frozen unlabeled decoder direction,
one shared zero, and all 60 signed magnitudes. The independent Gemma audit gates
only structural, numerical, hook, and artifact-replay mechanics. It does not
collect semantic outcomes, use the learned J, validate a scientific effect,
select a favorable dose, or tune any large-model threshold.

Execution authorization may be issued only after the runner, audit, plan,
review adjudication, tests, and passing Gemma promotion receipt are frozen; the
plan-defining paths are clean; and the local commit equals the live pushed
remote commit. The scientific campaign cap is $9 at a conservative $6/hour;
the provider watchdog is a separate $36 fail-safe. Together with the compact
review, all authorized work remains below the user's $50 ceiling.
