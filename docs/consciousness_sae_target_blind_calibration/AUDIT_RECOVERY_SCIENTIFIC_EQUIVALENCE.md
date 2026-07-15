# Audit-recovery scientific-equivalence appendix

This appendix is outcome-blind. It binds the frozen r3 scientific auditor and
machine plan to the audit-only recovery, but it does **not** claim that the
recovery revalidates the substantive adequacy of the inherited design. No raw
run or compact result is an input to the extractor.

Packet SHA-256: `55ad1f80166a4998b9fe172f28be27fffc983ae2467617c0d4cfcb832fe1ed50`

## What is mechanically established

- The original plan manifest and frozen source bytes are hash-bound.
- The recovery invokes the same `audit.audit` scientific entry point exactly
  once. A separately extracted atomic publisher applies the fresh recovery
  clock without rewriting the original campaign fields.
- The only scientific compatibility change is the J-map inventory predicate:
  all required layers must exist; only those required maps are handed to the
  frozen auditor; unused extras are recorded in recovery-only provenance and
  ignored. The frozen J-artifact metadata shape retains the required-map count.
- Original and recovered outputs are compared through an affirmative frozen
  scientific-field projection. Recovery provenance fields are outside that
  projection and cannot substitute for a scientific field.

## Inherited design (no outcomes)

- Independent unit: `prompt_id`; 8
  exact frozen prompt units. This is a fixed-panel stability calculation, not
  a prompt-population confidence interval.
- The J-checkpoint field `n_prompts=125` describes prompts used to fit the
  public artifact; it is not this study's sample size or resampling unit.
- Repeated observations: 3 directions x
  5 doses per prompt, yielding
  120 signed pairs and 96
  prespecified gated pairs.
- Model inventory: 256
  original model forwards; the recovery adds zero.
- Primary J estimand: layer 50 at dose 0.03, mean directions within prompt and
  then mean prompts, for residual cosine and fixed-token logit Pearson.
  Layers 51-78 remain descriptive only.
- Missingness/exclusion: missing, duplicate, extra/unmanifested, nonfinite, or
  partial data reject the audit; there is no imputation or outcome-based
  exclusion.
- Bootstrap: 20000 prompt-resampling replicates over
  8 prompt units; interval label
  `fixed_panel_prompt_resampling_stability_interval`.
- Multiplicity: two metrics at sole primary layer 50, each with absolute, identity, and strongest-of-five-random gates; formal adjustment is
  `none_specified_in_frozen_protocol`. Eligibility is conjunctive and there
  is no across-layer selection.
- Stopping: complete fixed inventory, no optional scientific stopping. Partial
  or watchdog-stopped transactions are inadmissible.
- Claim gates and every numerical threshold are reproduced verbatim in the
  machine-readable packet.

## Scope boundary

This appendix answers the recovery-equivalence question. It does not add
independent units, increase power, turn fixed-panel intervals into population
intervals, repair any inherited multiplicity limitation, or authorize a new
model forward. Any such claim requires a separate prospective review.
