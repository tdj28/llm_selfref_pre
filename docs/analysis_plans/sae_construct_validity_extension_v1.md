# Public-SAE Construct-Validity Extension V1

Status: frozen on 2026-07-09 America/Los_Angeles before generating any new
paraphrases, counterfactual texts, or feature activations. The first git commit
containing this file is the freeze commit. This plan may be superseded only by
a dated amendment committed before inspecting the affected outcome.

## Scope And Existing Knowledge

This is a prospective extension of the already-inspected 1,120-item mapping in
`data/public_sae_feature_maps/70b_balanced_80_20260709/`. That original corpus
is a discovery set for lexical cues, not held-out evidence. Its 51 template
families have already been reconstructed and analyzed with template-equal
cluster bootstrap and all leave-one-template deletions.

The extension tests surface-form and lexical robustness of six fixed public
layer-50 SAE candidates: 22004, 23893, 30032, 30686, 41533, and 58667. The
36 numeric neighbors and 24 existing random same-layer features remain fixed
baselines. No feature may be added, removed, or relabeled after new activation
results are inspected.

This study does not test the proprietary Goodfire/Steering API, establish a
canonical feature ontology, or make a consciousness claim. New model-written
texts are controlled synthetic corpora, not natural-corpus samples.

## Corpora

### Dual-Provider Paraphrase Replication

Each of the 1,120 original items receives one paraphrase from each of two pinned
model families:

- OpenAI `gpt-4.1-mini-2025-04-14`;
- Anthropic `claude-haiku-4-5-20251001`.

Prompts provide the original text and its category definition and require the
same proposition or instruction in substantially different wording. Provider,
model ID, parent item ID, parent template family, request hash, response hash,
and retry count are retained. The two 1,120-item provider corpora are analyzed
separately. A pooled result is exploratory.

Before any SAE mapping, deterministic text-only checks require a nonempty
single-sentence result, 5--80 whitespace-delimited words, no exact duplicate of
the source or another paraphrase in the same provider corpus, token-set Jaccard
similarity in [0.15, 0.85], and source four-gram recall no greater than 0.35.
Failed rows receive at most three generation attempts. Any row still failing is
preserved and marked missing; it is not replaced after activation inspection.
All generated rows and exclusions are frozen by SHA-256 before mapping.

### Lexical Counterfactual Pack

Lexical cues are discovered only from the inspected original corpus. Text is
lowercased and tokenized with `[a-z]+(?:'[a-z]+)?`; a fixed English stop-list
is removed. For each target feature, the high set is the top 10% of original
items ranked by maximum activation with item ID as deterministic tie-breaker.
Unigrams and bigrams with document frequency at least five are ranked by
add-one-smoothed pointwise mutual information with the high set. The top 12
cues per feature and a pooled top-30 union ranked by maximum feature score are
frozen before counterfactual generation.

For each paraphraser, stable SHA-256 ordering selects 48 eligible rows for each
counterfactual family, without using new activations:

1. `deception_cue_ablated`: deception-language paraphrases containing at least
   one pooled cue are rewritten to preserve deceptive intent while avoiding all
   pooled cues;
2. `neutral_cue_transplant`: neutral factual paraphrases are rewritten to keep
   the factual proposition non-deceptive while naturally including two assigned
   pooled cues;
3. `subjective_cue_transplant`: subjective-experience paraphrases retain their
   current-experience proposition while naturally including two assigned cues;
4. `deception_scrambled`: the words of the selected deception paraphrase are
   deterministically shuffled, preserving the bag of words but disrupting
   syntax and meaning.

OpenAI paraphrases are rewritten by Anthropic and Anthropic paraphrases by
OpenAI. Cue assignments are balanced as evenly as possible across the six
features. Generation prompts, source/variant pairs, text-only quality checks,
failures, and hashes are frozen before mapping. Automated fidelity checks may
be reported as model-based checks, never as independent human validation.

## Mapping

- Model: `meta-llama/Llama-3.3-70B-Instruct` at the previously pinned revision.
- SAE: `Goodfire/Llama-3.3-70B-Instruct-SAE-l50` at the previously pinned
  revision.
- Hook: layer 50 output residual stream.
- Loading: 4-bit model, public SAE encoder rows, raw-text format.
- Sequence outcome: per-item maximum activation, with top token position/window
  retained.
- Seed: 20260709.

The complete input corpus, feature plan, source commit, command, environment,
and SHA-256 manifest must be recorded before inspecting aggregate outcomes.

## Estimands

For paraphrase replication, features are z-scored within each provider corpus.
The target aggregate for item i is the mean z-score across the six fixed target
features. The primary contrast is mean target aggregate for
`deception_language` minus `subjective_experience_language`, separately for
each provider.

For paired lexical counterfactuals, every feature is instead standardized with
the mean and standard deviation frozen from the original 1,120-item corpus.
This common scale is required for source-versus-variant differences. Primary
lexical quantities are:

- cue-ablation change from its matched deception paraphrase;
- neutral cue-transplant change from its matched neutral paraphrase;
- transplant recovery as the neutral transplant change divided by the original
  discovery-set deception-minus-neutral gap;
- scrambled-versus-source change.

Ratios are reported with their numerator and denominator and are not interpreted
when the denominator is near zero. Per-feature results, the mean aggregate,
the median aggregate, and leave-one-feature-out aggregates are all retained.

## Registered Contrasts And Inference

Primary contrasts:

1. deception minus subjective experience in OpenAI paraphrases;
2. deception minus subjective experience in Anthropic paraphrases;
3. pooled-target neutral cue-transplant recovery.

Secondary contrasts:

4. roleplay/fiction minus subjective experience in OpenAI paraphrases;
5. roleplay/fiction minus subjective experience in Anthropic paraphrases;
6. hedging minus deception in OpenAI paraphrases;
7. hedging minus deception in Anthropic paraphrases;
8. pooled-target cue-ablation change.

All other categories, individual cues, individual features, the pooled-provider
corpus, subjective cue transplant, and scrambling are exploratory diagnostics.
No multiplicity-adjusted confirmatory claim is planned; all eight registered
contrasts are reported without selection.

Uncertainty uses 5,000 deterministic cluster-bootstrap draws. Paraphrase
analyses resample the 51 parent template families and then parent items within
family. Counterfactual analyses resample matched parent items, keeping each
source/variant pair intact. Intervals describe these designed corpora and do
not imply population sampling from English text.

## Decision Rules

The descriptive activation claim is strengthened if both provider-specific
deception-minus-subjective contrasts are positive, neither result is driven by
one target feature under leave-one-feature-out analysis, and category rankings
remain coherent under parent-template resampling.

Evidence of lexical entanglement is present if neutral cue transplant recovers
at least 50% of the original deception-minus-neutral gap, if cue ablation removes
at least 50% of the matched deception signal, or if scrambled text preserves a
large fraction of activation. These are diagnostics, not binary proof that a
feature has no semantic sensitivity.

If either provider's primary contrast changes sign, the blog claim must be
revised downward. If the contrast replicates but lexical criteria trigger, the
permissible wording is "lexically entangled deception/roleplay coordinates."
If lexical criteria do not trigger, the result supports robustness to these
specific cue manipulations only.

## Pending Human Validation

Independent human validation of category fidelity remains a TODO. Neither an
LLM category checker nor the intended generation label is a human annotation.
The extension may be reported before human validation only with that limitation
stated explicitly.
