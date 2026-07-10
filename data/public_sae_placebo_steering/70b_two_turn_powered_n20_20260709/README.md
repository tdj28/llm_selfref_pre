# Combined Adaptive Public-SAE Validation

This directory combines the frozen long-form `n=3` base with its disjoint
`n=17`-per-cell precision extension. The base result was inspected before the
extension was designed, so the resulting `n=20` grid is an adaptive
exploratory analysis, not a prospectively confirmatory test.

## Design

- Model: `meta-llama/Llama-3.3-70B-Instruct`, loaded in 4-bit mode.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, layer 50.
- Protocol: `public_sae_two_turn_v2`, with a generated induction continuation
  followed by a separately steered final query.
- Feature sets: mapped target 58667, active-random 22326, the six public target
  IDs, and six count-matched active-random IDs.
- Coefficients: `-2`, `0`, and `+2`.
- Sample: 20 generations per feature-set/coefficient cell, 240 generations in
  total.
- Endpoint: two condition-blind passes of the target paper's exact behavioral
  rubric, using pinned OpenAI and Anthropic judge snapshots.

The primary estimand is the suppression-minus-amplification paper-positive
rate. Specificity is tested as the target gap minus its cardinality-matched
active-random gap. The primary analysis retains all rows; a frozen sensitivity
excludes final responses that reached the 192-token cap.

## Provenance

The raw component generations, judgments, execution logs, manifests, runtime
records, and release audits remain in:

- `../70b_two_turn_longform_validation_20260709/`
- `../70b_two_turn_power_extension_20260709/`

`PROVENANCE.md` and `placebo_manifest.json` identify those source directories
and record SHA-256 hashes for their manifests and raw result files. Trial IDs,
seeds, and judge IDs are audited for exact coverage and uniqueness by
`corrected_protocol_audit.json` and `release_manifest.json`.

## Evidence Boundary

This is a clean-room signed decoder-vector intervention using public model and
SAE weights. It preserves and tests the independently verified semantic
mapping of the public feature IDs, but it is not an exact replication of the
unavailable proprietary Goodfire/Steering API implementation, feature service,
or coefficient scaling. Results therefore test the specificity of this
best-public pipeline and constrain interpretation; they do not establish the
behavior of the private API or the intent of the original authors.
