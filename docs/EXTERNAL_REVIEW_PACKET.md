# External Methods Review Packet

This packet is for independent review before submission. It asks reviewers to
audit causal and mechanistic identification, not to opine on whether language
models are conscious. Please report concrete errors, unsupported claims, and
missing sensitivity analyses with file/table references.

## Target And Scope

- Target artifact: Berg, de Lucena, and Rosenblatt, arXiv:2510.24797v2
  (2025-10-30).
- Manuscript: `paper/main.tex`.
- Frozen causal protocol: `docs/CONFIRMATORY_PROTOCOL.md`.
- Claim boundaries: `docs/CLAIM_LEDGER.md`.
- Primary release: `data/causal_transplant/confirmatory_v1_20260709/`.
- Public-SAE protocol: `experiments/exp2_sae/PUBLIC_SAE_PLACEBO_STEERING.md`.
- Powered public-SAE release:
  `data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/`.
- Branched specificity protocol:
  `experiments/exp2_sae/BRANCHED_SPECIFICITY_PROTOCOL.md`.

The central claim is deliberately limited: the published report endpoint is
causally sensitive to active instruction and the tested query packages. Effect
magnitudes also vary across the tested response-model snapshots and evaluator
criteria. Together, these dependencies mean the benchmark does not by itself
identify a self-reference-specific phenomenal state. Exact proprietary
Goodfire API replication is not claimed. In the adaptive best-public steering
analysis, the active-random aggregate has a larger paper-direction slope than
the mapped target aggregate under both judges; this is a public-implementation
specificity result, not a proprietary non-replication.

## Statistics And Causal Inference Review

Please audit:

1. Whether the calibration, orthogonal factorial, transcript transplant, and
   query-factorial estimands match the stated identification questions.
2. Whether independent calibration draws, lexical-variant clusters, and paired
   source-text blocks are the correct resampling units.
3. Whether equal-model summaries and hierarchical intervals are described
   appropriately given four non-randomly selected model snapshots.
4. Whether empty refusals are consistently retained as missing rather than
   recoded as denials.
5. Whether the transcript-source and instruction-source effects are calculated
   from complete crossed blocks without pseudoreplication.
6. Whether the directional-but-imprecise register result and query interaction
   are worded at the strength supported by their intervals.
7. Whether multiplicity, adaptive analysis, and automated-judge uncertainty
   are disclosed sufficiently.
8. Whether any numerical claim fails to resolve to a tracked table. The
   independent raw-row check is
   `independent_point_estimate_audit.json`; it validates point estimates, not
   interval code.

## Mechanistic Interpretability Review

Please audit:

1. Whether layer 50 and the hook location match the public SAE's intended
   activation site.
2. Whether encoding, signed latent addition, decoding, and reconstruction-error
   restoration implement the stated decoder-vector intervention.
3. The consequences of moving ReLU-encoded latents below zero during negative
   steering.
4. The comparability limits introduced by 4-bit quantization and unknown
   proprietary API normalization/clamping/scaling.
5. Whether target and active-random controls are adequately matched by feature
   count and effective hidden-state perturbation; identify any need for
   decoder-norm matching.
6. Whether hook-call, no-op, latent-delta, perturbation, cleanup, and token-cap
   telemetry are sufficient technical positive controls.
7. Whether the adaptive `n=20` behavioral analysis and Jeffreys-Beta contrast
   intervals are interpreted descriptively rather than as an exact Goodfire
   non-replication.
8. Whether the activation map supports the stated semantic interpretations
   without treating feature labels as ground truth or claiming
   consciousness-specificity.
9. Whether the aggregate target-minus-active-random contrasts, their no-cap
   sensitivity, and realized hidden-state RMS telemetry justify the manuscript's
   bounded non-specificity wording; the independent point-estimate audit is
   `independent_headline_audit.json` in the powered release.
10. Whether the template-aware feature-map analysis correctly treats the 51
    researcher-authored template families as clusters, reports the two
    leave-one-template label switches, and avoids implying natural-corpus
    generalization.

## Requested Review Format

Return findings ordered by severity, each with:

- the affected file/table/figure;
- the failure mode or unsupported inference;
- the smallest defensible correction;
- whether the issue blocks public release, submission, or only a stronger
  interpretation.

Please list residual risks even if no blocking error is found. Human annotation
and proprietary API access are known external limitations and should not be
treated as completed evidence.
