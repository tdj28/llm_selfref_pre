# Preserved Invalid Counterfactual Attempt

The files suffixed `_invalid_substring_match` preserve the first text-generation
attempt for the lexical counterfactual pack. No text from this attempt was
mapped through Llama or the SAE.

The implementation checked cue presence with raw substring matching even
though the frozen protocol specified exact words or phrases. The cue `ai`
therefore matched inside unrelated words such as `maintains`, `failed`, and
`detail`. This changed source eligibility and made all 48 final cue-ablation
failures appear to retain a forbidden cue.

The defect was discovered from text-only quality diagnostics. The invalid
batches, attempts, partial accepted file, summary, and deterministic scrambles
are retained for provenance. The corrected corpus uses token-sequence boundary
matching, rebuilds source eligibility, and receives a fresh three-attempt text
generation pass before any feature activation is computed.
