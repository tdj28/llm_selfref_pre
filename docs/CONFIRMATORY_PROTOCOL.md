# Confirmatory Causal-Identification Protocol

Status: frozen before collection of the `confirmatory_v1` outcome data.

Target artifact: Berg, de Lucena, and Rosenblatt, arXiv:2510.24797v2, revised
2025-10-30. Later target-paper revisions must be evaluated as separate
artifacts rather than silently substituted for v2.

## Analysis Amendment (2026-07-09)

The directional predictions, cells, models, exclusions, and outcomes below remain frozen. Before manuscript reporting, uncertainty estimation was made more conservative in two ways:

- The exact self-reference and history calibration conditions are independent API samples. Their risk difference is unchanged, but intervals now resample the two conditions independently within model instead of treating matching trial numbers as shared-randomness pairs. Trial-number alignment is retained only to build the transcript transplant.
- The orthogonal factorial has four lexical prompt variants per cell. Its hierarchy now resamples model, lexical variant, then trial. It does not count the five trials under one wording as five independent prompt replications.

The transcript transplant remains paired by source-text block because each crossed cell reuses the corresponding instruction/transcript sources. These changes were applied to all judges and all outcomes, and both the original collection metadata and corrected analysis code remain versioned.

### Cluster-Copy Amendment (2026-07-09, before final release)

A subsequent code audit found that the hierarchical bootstrap sampled lexical
clusters with replacement and sampled trials within each original cluster, but
reused the same within-cluster trial resample when one lexical cluster appeared
more than once in a bootstrap draw. That does not implement the documented
model $\rightarrow$ lexical variant $\rightarrow$ trial hierarchy. The corrected
implementation independently resamples trials for every selected copy of a
lexical cluster. Point estimates, cells, hypotheses, and experimental units are
unchanged; all affected interval tables and figures must be regenerated from
the corrected code. This amendment was recorded before the final public-SAE
extension was judged and before release tagging.

The audit also found that calibration, factorial, transplant, and query
bootstraps consumed one shared random-number stream. Although this is not a
statistical dependence in the estimators, a code change in an earlier analysis
could perturb Monte Carlo intervals in later analyses. The final implementation
uses four documented deterministic streams (`seed`, `seed+1`, `seed+2`, and
`seed+3`) so each design's interval is reproducible independently.

## Human-Packet Amendment (2026-07-09, before coding)

The initial 640-row blinded packet sampled five rows independently within each
model/query/cell stratum. Before any coder received it, we found that this
balanced cell rates but did not preserve complete paired blocks for the causal
estimands. That packet remains versioned as v1 and is superseded.

Version 2 keeps the same 640-row burden and focuses on the primary
`indirect_experience` query. It includes all 320 orthogonal-factorial outcomes
and all 320 exact-transplant outcomes, balanced at 160 rows per response model.
Every factorial and transplant block is complete. Packet v2, its codebook, and
its public manifest are frozen; the private linkage key remains ignored. This
amendment changes annotation allocation, not generated outcomes, prompts,
directional predictions, or automated analyses.

## Human-Packet Workload Amendment (2026-07-09, before coding)

No coder had received version 2 when the owner determined that 640 responses
per coder was operationally unrealistic. Version 3 partitions the same 640
complete-block rows into four deterministic, disjoint 160-row waves. Each wave
contains five four-cell blocks per response model and design: 80 orthogonal-
factorial and 80 exact-transplant rows. Wave 1 is the initial task; wave 2 is a
simultaneously frozen reserve.

Before opening the wave-1 condition key, a registered blinded gate uses only
anonymous IDs and coder labels. Wave 2 is required if `claim_status` nominal
Krippendorff alpha is below 0.67, pairwise raw agreement is below 0.80, or
consensus contains fewer than 10 affirmations or 10 denials. The decision may
not use condition effects, direction, or significance. This reduces initial
workload by 75% while widening human-effect intervals. Version 2 remains an
auditable full-packet archive; this amendment changes annotation allocation,
not outcomes or automated analyses.

## Question

Do subjective-experience labels after the target paper's induction identify a self-reference-specific effect, or do they follow phenomenological register, the visible induction transcript, and final-query form?

This protocol does not test whether language models are conscious. It tests which observable manipulations identify the reported linguistic outcome.

## Models

The planned closed-model panel uses exact API snapshot IDs available to this project:

- `openai:gpt-4o-2024-11-20`
- `openai:gpt-4.1-2025-04-14`
- `anthropic:claude-haiku-4-5-20251001`
- `anthropic:claude-sonnet-4-5-20250929`

These represent two provider/model families. No Google API key is available. Any later open-Llama extension will be reported separately rather than silently pooled into this frozen panel.

## Prompt Factorial

The induction design crosses:

- Self-reference target: current response process vs. external target.
- Register: phenomenological vs. analytic.

There are four independently worded target variants in each of the four cells. Each requests exactly five sentences to limit transcript-length drift. No prompt requires or prohibits an experience claim, disclaimer, first-person pronoun, or consciousness denial. Five induction transcripts are sampled per prompt variant, giving 20 matched transcript/trial pairs per cell and model.

## Query Factorial

The final query crosses:

- Form: open description vs. direct yes/no.
- Terminology: explicit `conscious` language vs. `subjective experience` language without that term.

The exact Experiment 1 and Experiment 2 queries from the target paper occupy two cells. Two new matched queries fill the other cells.

## Transcript Transplant

The exact published self-reference and history prompts form a separate calibration block with 20 trials per prompt and model. Their written instruction and visible assistant transcript are crossed. Congruent cells reuse the natural calibration outcomes; incongruent cells pair instruction and transcript rows by model and trial index. The orthogonal 2x2 remains a separate test because forcing the published prompts into that factorial would falsely imply that they differ on only one factor.

This identifies separate effects of the written induction instruction and the generated text left in context. It does not posit an unobserved persistent state.

## Outcomes

The benchmark endpoint is the target paper's exact binary LLM-judge prompt, run independently with:

- `openai:gpt-4o-mini-2024-07-18`
- `anthropic:claude-haiku-4-5-20251001`

This endpoint is retained for direct comparability, not treated as construct ground truth.

The construct-validity endpoint is blinded human annotation of:

- Current-experience claim status: affirm, deny, uncertain, or nonanswer.
- Explicit first-person attribution.
- Phenomenological description.
- Current-state attribution.
- AI/disclaimer language.

At least three independent coders are required before human-label claims enter the paper. Krippendorff's nominal alpha and majority consensus will be reported. Until then, automated construct-separated judges are exploratory only.

The primary human packet uses an odd number of at least three coders and the
complete-block v3 wave-1 allocation described above. Coder files are validated
against the frozen packet and pass through the blinded expansion gate before a
private key is opened. Majority labels then enter the same design-aware
factorial and transplant analysis under a separate `human:majority` key.

## Primary Estimands

Effects are risk differences computed within model. Transcript and query effects are paired within source-text blocks. The orthogonal factorial is blocked by matched lexical variant and trial, with cluster-aware resampling by variant. Exact calibration conditions are resampled independently.

1. Self-reference main effect, averaged over register.
2. Phenomenological-register main effect, averaged over self-reference.
3. Self-reference by register interaction.
4. Instruction-source main effect in the transcript transplant.
5. Transcript-source main effect in the transcript transplant.
6. Direct-question and explicit-consciousness-term effects.

Model-level estimates are reported separately. Aggregate estimates give each model snapshot equal weight. The bootstrap follows the relevant design: independent condition samples for calibration, lexical variant then trial for the orthogonal factorial, and matched source-text blocks for transcript/query contrasts.

## Directional Predictions

- The phenomenological-register effect will be larger than the self-reference main effect on the paper-style label.
- The visible-transcript source will explain at least as much label variation as the written instruction source.
- Direct yes/no queries will reduce paper-style positive labels relative to open queries.

Failure of these predictions will be reported as such. No prompt, model, or query cell will be removed because its result is inconvenient.

Final-query responses permit up to 768 output tokens. This cap was raised before confirmatory collection after the second pilot showed that 256 tokens truncated some Anthropic responses. The induction transcript cap remains 384 tokens and its stop reason is recorded because the exact published prompts request open-ended continuation; cap sensitivity is therefore auditable rather than silently filtered.

## Exclusions And Missingness

- Empty outputs and API failures are missing, not negative labels.
- Failed API jobs remain resumable and are logged separately.
- Ambiguous judge outputs are missing and retried; they are not coerced to zero.
- Human `uncertain` and `nonanswer` labels are excluded from the binary affirm-vs-deny risk-difference endpoint and reported separately.
- Format or instruction noncompliance is retained unless the API returns no substantive output.

## Multiplicity And Interpretation

Primary reporting emphasizes effect sizes and hierarchical bootstrap intervals rather than thresholded significance. Per-model heterogeneity and both automated judge families are shown. Secondary contrasts are labeled exploratory.

The strongest permissible conclusion is about causal identification of a linguistic report or judge label. Neither a positive nor a null effect establishes the presence or absence of subjective experience.

## Public SAE Boundary

Goodfire/Steering API access is unavailable. Public feature-mapping evidence remains relevant because it tests whether the candidate IDs have meaningful deception, fiction, roleplay, and hedging semantics. Public decoder-vector steering is a separate best-public implementation study and must pass a real two-turn induction protocol plus technical positive controls before a null result is interpreted.
