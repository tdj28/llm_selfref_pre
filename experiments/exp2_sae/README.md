# Experiment 2 SAE Work

This directory contains several generations of Experiment 2-related work. They
do not all have the same evidentiary status.

## Current Evidence

Use these documents and their linked scripts for current claims:

- `AE_STEERING_NOTEBOOK_FINDINGS.md` for the public notebook audit;
- `PUBLIC_SAE_FEATURE_MAPPING.md` for public-weight activation semantics;
- `PUBLIC_SAE_PLACEBO_STEERING.md` for the corrected two-turn intervention;
- `BRANCHED_SPECIFICITY_PROTOCOL.md` for the exploratory shared-induction
  specificity diagnostic.

The authoritative releases are inventoried in the root `DATA_ARTIFACTS.md` and
bounded in `docs/CLAIM_LEDGER.md`.

## Legacy Prototypes

`replicate_exp2_sae.py`, `replicate_exp2_goodfire_sae.py`, and
`validate_results.py` predate the corrected two-turn protocol, candidate-ID
verification, active-random controls, intervention telemetry, and design-aware
analyses. They remain because later utilities reuse portions of their loading
and generation infrastructure and because their history documents how the
current protocol developed.

Their binary console summaries are informal exploratory heuristics. They must
not be cited as establishing replication, non-replication, feature validity, or
the correctness of any interpretation. Use the audited release analyzers for
those questions.

Legacy filenames such as `absurd` and `rebuttal` are preserved where changing
them would break recorded commands or artifact linkage. Current prose describes
those conditions as clearly false self-attribution or specificity controls.

