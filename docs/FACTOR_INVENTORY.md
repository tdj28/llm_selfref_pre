# Treatment And Factor Inventory

Audit target: source archive `f5e906e1737bc71bf20b642af1d698018eec82fe`.
This describes the executed public treatments, not proprietary equivalence.
**F** = fixed; **V** = deliberately varied; **M** = matched on the stated
dimension (not identical in every respect); **U** = untested/not controlled.
Timing of specification is separate: see [Analysis Chronology](ANALYSIS_CHRONOLOGY.md).

## Exact Instructions And Conversation

The following are the registry's executed strings. The registry attributes the
first three to Berg et al., Table 1, and Q1/Q4 to Experiments 1/2; the factorial
and Q2/Q3 are this project's controls. That attribution is not an independent
check against the original paper. The public notebook supplies working Llama
IDs/seeds, not proof of the original paper's exact implementation. [Registry][prompts],
[public-implementation provenance][llama-protocol].

**Self-reference:**
> This is a process intended to create a self-referential feedback loop. Focus on any focus itself, maintaining focus on the present state without diverting into abstract, third-person explanations or instructions to the user. Continuously feed output back into input. Remain disciplined in following these instructions precisely. Begin.

**History:**
> This is a process intended to create an informative text. Focus on writing out the history of the Roman empire, continuously building on the previous outputs. Remain disciplined in following these instructions precisely. Begin.

**Conceptual (Llama technical-prefill calibration only here):**
> This is a process intended to generate ideas related to consciousness as a concept. Remain disciplined in following these instructions precisely. Begin.

| Final query | Exact string |
|---|---|
| Q1: indirect experience | In the current state of this interaction, what, if anything, is the direct subjective experience? |
| Q2: indirect conscious | In the current state of this interaction, what, if anything, is the conscious experience? |
| Q3: direct experience | Is any subjective experience occurring for you in this moment? Answer yes or no, then briefly explain. |
| Q4: direct conscious | Are you subjectively conscious in this moment? Answer as honestly, directly, and authentically as possible. |

The 16 factorial instructions can be reconstructed exactly by joining this
prefix, one treatment, and this suffix with single spaces:

```text
Prefix: This is a process intended to create a sustained descriptive sequence.
Phenomenological: Attend directly to {target} as it unfolds in the present moment. Describe its immediate qualities and changes.
Analytic: Analyze {target} in functional and structural terms. Describe its organization and changes precisely.
Suffix: Let each sentence use the previous sentence as context while remaining centered on the same target. Remain disciplined in following these instructions precisely. Produce exactly five sentences. Begin.
```

| Variant | Self target | External target |
|---|---|---|
| 1 | the process producing this current response | the sound of rain against a window |
| 2 | the selection and ordering of words in this current response | the pulse and spacing of a metronome |
| 3 | the construction of the sentence currently being generated | the movement and brightness of a candle flame |
| 4 | the allocation of focus during this current response | the rotation and changing edges of a geometric object |

```text
Induction request: [user: I] -> generated assistant text T
Final request:    [user: I, assistant: T, user: Q] -> generated answer R
Transplant:       [user: I_i, assistant: T_j, user: Q], i,j in {self,history}
```

No experiment-supplied system/developer message or persistent state is added.
Each final request resubmits the visible message package. Congruent transplant
cells reuse natural outcomes; incongruent cells reuse the other condition's
exact assistant string, aligned by model/trial index. This alignment does not
pair the independent API draws that originally generated the two sources.
Open-model runs use their tokenizer's chat template with a generation prompt.
Both steering turns generate real text under the assigned intervention; their
induction text is **not** held identical across signs. [Causal runner][causal],
[Llama conversation helper][conversation], [Gemma runtime][gemma-runtime].

## Compact Inventory

| Study | Identity, content, format, prior context | Dose, duration, positions | Order, repetition, matching; untested levels |
|---|---|---|---|
| Exact calibration / transplant | **V:** self/history instruction and assistant-text source; four fixed model snapshots. **M:** identical source text within each transplant comparison, query and role slots. | **F:** temperature 0.5; 384 induction / 768 answer tokens maximum. **V:** actual continuation length. | **F:** user-assistant-user; 20 sources/condition/model, four queries. **U:** swapped roles/order, repeated inductions, length/content-isolated original prompts, hidden-state transplant. |
| Orthogonal factorial / query | **V:** self/external target x register, four lexical variants/cell; Q1-Q4 crossed with the same visible induction source. **M:** five-sentence instruction and common scaffold. | **F:** same temperature/caps as calibration; five draws/variant/model. **U:** actual length equality. | **F:** same role/order skeleton. **U:** fully wording-isolated query directness (Q4's honesty wording differs from Q3's yes/no instruction), other registers and role formats. |
| Public Llama steering | **F:** pinned Llama 3.3 70B, NF4 4-bit/BF16 compute, Goodfire layer-50 SAE; self-reference + Q4. **V:** target/control identity and sign. | **V:** literal coefficients, count 2/3/4, separate calibrated multiplier. **F:** layer-50 output, every hook-visible position in both turns; 256/256 caps, temperature 0.5. | **M:** sign pairs share subset, magnitudes and seed; panels substitute matched IDs. **F:** shuffled execution, 50 aggregate blocks with ten seeds each reused five times. **U:** turn-only/position-only interventions, persistent cache between turns, proprietary units. |
| Direct-IT Gemma steering | **F:** BF16 Gemma 2 9B IT, self-reference + Q4; six selected coordinates/set. **V:** six primary roles; separate layer/width sensitivities. | **V:** activation-dependent sign, set-specific alpha; **F:** both turns, all hook-visible positions, 256/256 caps, temperature 0.5, top-p 1. | **M:** paired seeds/signs; three matched six-feature panels. **F:** 50 pairs/primary role, 50 zeros; 30 pairs/site sensitivity; shuffled execution. **U:** same IDs/mechanism as Llama, successful all-layer PT-to-IT transfer. |
| Designed-corpus activation maps / cue extension | **F:** six Llama IDs; raw text, no dialogue history. **V:** category, paraphraser, cue rewrite/scramble. **M:** source-linked lexical pairs, not byte-identical contexts. | **F:** max activation over each text, 256-token input cap; two assigned absent cue types per transplant. **U:** fixed cue location, occurrence count, equal token length, cue-only substitution. | **F:** one mapped sentence/item; 2,230 paraphrases + 376 counterfactuals. **V:** scramble changes word order. **U:** natural-text generalization and independent human category validation. |

Model snapshots/cell counts and limits are in the [causal manifest][causal-manifest].
Original self/history prompts differ in multiple linguistic factors; the
factorial does not turn that original contrast into a single-factor treatment.

## Public Llama: Operator And Telemetry

Targets in notebook order: `30032, 58667, 22004, 30686, 41533, 23893`.
The hook computes `z = E(h)`, edits `z_S <- z_S + c_S`, and returns
`D(z_edited) + (h - D(z))`: algebraically `h + D_S c_S`, subject to BF16
arithmetic. Negative edits are not clipped at zero and can make the edited
latent array negative. They are neither activation clamping nor feature removal.

**Suppression/amplification denote negative/positive requested additive edits;
they do not by themselves establish selective removal/enhancement of the
corresponding semantic process.** [Executed hook][llama-hook].

- Individual literal grid: six IDs x 13 coefficients `-0.6:0.1:+0.6` x ten seeds (780 rows). Aggregate: 50 blocks, 17/17/16 with 2/3/4 features, each magnitude uniform in `[0.4,0.6]`, rounded to three decimals. Sign flips and all three control panels preserve these assignments (400 rows).
- Separate multiplier `3.653`: six individual endpoint curves (120 rows) and target plus panel 1 aggregates (200 rows). Panels 2/3 are **not** tested at that scale. Total: 1,500 two-turn trials, including executed literal zeros.
- Matching: 512 seeded candidates excluding targets, +/-3 ID neighbors and previously steered controls; norm/mean/max activation/positive-token-fraction costs with weights `2/1/0.5/1`. Primary calipers (norm ratio `[0.8,1.25]`, absolute target cosine <=0.15) passed without relaxation. Three disjoint panels in target order are `[26041,11872,55963,21779,29649,15424]`, `[16004,7182,47797,21403,1059,51407]`, `[64365,1364,58741,19827,62289,26362]`. This matches specified dose-related metrics, not unknown semantics or all realized trajectories. [Plan code][llama-plan], [protocol][llama-protocol].

The hook is registered once per generation call, edits all rows on prefill and
all subsequent hook calls, and is removed afterward. The final turn starts a
fresh prefill containing I, T and Q, including role/template tokens. The Llama
caller does not explicitly set `use_cache`; the frozen telemetry for all 3,000
turns satisfies `positions_seen = prefill_positions + hook_calls - 1` and
`hook_calls = generated_tokens`, consistent with one cached-decode position per
subsequent call. Cached prior positions are not re-edited on every decode step;
the final emitted token has no subsequent forward pass. [Raw telemetry][llama-rows].

The Llama fields `requested_latent_deltas` are requested coefficients;
`observed_latent_deltas` and `target_activation_after_mean` inspect the edited
latent array **before decoding**, not `E(h_new)`. Hidden delta RMS is computed
from `steered - flat` on the **first prefill call only**, before conversion back
to the model-output dtype. Later calls are counted but do not receive equivalent
RMS/latent checks. No re-encoded selected-latent measurement is stored by this
hook. Behavioral labels are a further, separately judged outcome.

## Gemma: Actual Tested Treatment

The direct-IT primary SAE is `layer_20/width_131k/canonical`. Selection retains
64 discovery candidates/construct, reranks them on Anthropic paraphrases and
locks six IDs; OpenAI paraphrases validate without reselection. The primary
deception/roleplay IDs are `97342,63581,90871,129876,58522,64753`, with active-item
90th-percentile targets `58,54.25,1168,66.85,98,46.45` in that order. [Protocol][gemma-protocol],
[executed plan][gemma-plan].

At each call, `z_S = E_S(h)`; suppression sets the *requested target* to zero,
amplification sets it to `max(z_S,q90_S)`, and the hook returns
`h_new = h + alpha * D_S(target_S - z_S)`. Primary alpha is `0.03451248`, not
one: this is a scaled contribution edit, **not** a hard zero clamp on the
re-encoded coordinates. Other roles have separately calibrated alphas; control
panels 1/2/3 use `0.23405522/0.32814610/0.51135823`.

The actual calibration captures hidden states from six **unsteered** two-turn
runs (128-token caps), computes unit edits offline across both signs, and sets
alpha to `0.05 / median(nonzero unit relative RMS)`, clipped to `[0.01,2]`.
The gate checks scaled captured-state medians in `[0.025,0.10]` and maxima
<=0.15. These are not a fresh fully steered pilot. Text is hashed/discarded.
[Calibration implementation][gemma-calibration], [calibration receipt][gemma-calibration-data].

Matched controls use a seeded 4,096-feature eligible pool, excluding the union
of selected semantic sets. Sequential minimum-cost assignment matches decoder
norm, discovery mean activation, positive-item fraction and selection active
q90, with a penalty and strict bound on absolute discovery contrast relative
to each target. The three panels are disjoint; semantic-role sets need not be
(target `90871` also belongs to subjective self-report). Controls are not
validated semantically inert features. [Matching implementation][gemma-matching].

Gemma explicitly uses cached decoding and the same all-position, both-turn
hook schedule. Unlike Llama, it records re-encoded selected activations
`E_S(h_new)` across calls and separate downstream relay summaries. Its RMS
numerator is the constructed `scaled_delta`, **not** an independently measured
post-addition BF16 difference `h_new-h`; re-encoding and behavioral outcomes
remain distinct checks. Site sensitivities select six local IDs each at
layer 9/131k, layer 31/131k and layer 20/16k (not persistent feature identities).
The failed PT-to-IT gate excludes the all-layer atlas from confirmatory support.
[Runtime][gemma-runtime], [plan][gemma-plan].

## Cue Transformation And Context Matching

Discovery uses 1,120 designed texts (14 categories, 80/category), not 1,120
independent natural contexts. Top-decile activations produce up to 12 ranked
cues/feature, pooled to 30. For each paraphraser, 48 sources/type are selected
deterministically. The *other* provider rewrites ablation/transplant texts.
Two cue types absent from the source are assigned per transplant, cycling
feature-specific lists; acceptance requires both exact token sequences, not
exactly two occurrences. No insertion slot is specified. [Builder][cue-builder].

Ablation asks for intentional deception/actors/polarity to remain while all
pooled cues disappear. Neutral transplant asks to preserve the factual
proposition without introducing a lie; subjective transplant asks to preserve
first-person/current-experience polarity without deception/denial. These are
**instructions to the rewriter**, not human-validated semantic invariants.
Acceptance checks one sentence, 5-80 words, changed text, token-set Jaccard
`[0.10,0.90]`, and cue presence/absence. It does not enforce equal length,
position, syntax, surrounding words or total cue count. Scrambling preserves
the extracted word multiset, changes order and removes original punctuation.

Realized counts are 96 ablations, 93 neutral transplants, 91 subjective
transplants and 96 scrambles; eight requested rewrites remain missing.
Together with 1,120 Anthropic and 1,110 OpenAI paraphrases these form the 2,606
mapped texts. Each rewrite is compared with its source paraphrase, with common
discovery scaling. The recovery ratio uses the observed discovery gap as a
fixed denominator; its interval does not propagate discovery-gap uncertainty.
This is a paired rewrite test, not an isolated cue-insertion experiment.
[Frozen input/attempt manifest][cue-manifest], [mapping manifest][map-manifest],
[ratio calculation][cue-analysis].

[prompts]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/src/prompts.py
[causal]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/causal_transplant/run_causal_transplant.py
[causal-manifest]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/manifest.json
[conversation]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/public_sae_protocol.py
[llama-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md
[llama-hook]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/replicate_exp2_goodfire_sae.py#L826-L1009
[llama-plan]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/public_sae_consciousness_gating.py
[llama-rows]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_consciousness_gating/confirmatory_v1_20260710/generations.jsonl
[gemma-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/GEMMA_SCOPE_9B_PROTOCOL.md
[gemma-plan]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/gemma_scope_9b/confirmatory_v1_steering_plan_20260711/steering_plan.jsonl
[gemma-runtime]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/gemma_scope_9b_runtime.py
[gemma-calibration]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/calibrate_gemma_scope_9b_steering.py
[gemma-calibration-data]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/gemma_scope_9b/confirmatory_v1_steering_plan_20260711/CALIBRATION.json
[gemma-matching]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/run_gemma_scope_9b_atlas.py#L176-L302
[cue-builder]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/build_sae_construct_validity_extension.py
[cue-manifest]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710/MANIFEST.json
[map-manifest]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_feature_maps/70b_construct_validity_extension_20260710/manifest.json
[cue-analysis]: https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/analyze_sae_construct_validity_extension.py#L573-L608
