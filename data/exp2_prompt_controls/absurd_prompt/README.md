# Legacy Prompt-Only Specificity Controls

This directory contains an early prompt-only test of clearly false and
ground-truth model self-attributions. It is a behavioral specificity check, not
an SAE intervention and not a replication of the target paper's Experiment 2.

`absurd_prompt_results.json` is the final result file for this run. The retained
`absurd_prompt_results.partial.json` is an intermediate checkpoint from before
the rule-based labels were corrected. It contains known contradictory fields,
including rows marked both affirmative and denying. It is preserved only as
implementation provenance and must not be analyzed or cited as a result.

The canonical summaries for this legacy run are
`absurd_prompt_group_summary.csv` and `absurd_prompt_summary.csv`. Current SAE
specificity evidence is documented in
`experiments/exp2_sae/PUBLIC_SAE_PLACEBO_STEERING.md`.

