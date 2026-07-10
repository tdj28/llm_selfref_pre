# Legacy 8B Public-SAE Steering Check

This directory preserves an early exploratory public-weight run with 60 rows:
four prompt conditions, three steering coefficients, and five trials per cell.
It used activation-selected features rather than the six candidate IDs later
recovered from AE Studio's public notebook.

The run predates the corrected two-turn protocol and does not include a complete
environment manifest, a true paper-equivalent intervention, active-random
matching, or intervention telemetry. It therefore does not support a claim of
exact replication or non-replication and is not used as evidence in the current
manuscript.

The JSONL and compact summary are retained as transparent implementation
history. Current public-SAE steering evidence is in
`data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709/` and
`data/public_sae_placebo_steering/70b_branched_specificity_20260710/`.

