# Gemma Scope 9B Cross-Model Roadmap

Status: historical design rationale. Execution completed on 2026-07-11 under
the separately frozen [`GEMMA_SCOPE_9B_PROTOCOL.md`](GEMMA_SCOPE_9B_PROTOCOL.md).
The authoritative outcome summary is
[`GEMMA_SCOPE_9B_RESULTS.md`](GEMMA_SCOPE_9B_RESULTS.md), and the 403-file
release is `data/gemma_scope_9b/confirmatory_v1_20260711/`. The registered
direct-IT verdict is `not replicated under Gemma Scope`. The prospective
PT-to-IT transfer gate failed, so all 42-layer PT-on-IT work is exploratory.

Date: 2026-07-10

## Decision

Gemma Scope is the strongest available platform for the next mechanistic phase,
but it answers a different question from the completed Llama 3.3 70B study.
The Llama result tests whether the six accepted notebook IDs reproduce the
reported steering signature under one pinned public implementation. A Gemma
Scope study would test whether the broader deception/roleplay-to-consciousness-
report hypothesis generalizes to a different model family with substantially
better layer coverage.

The recommended study has two linked components:

1. A cross-model behavioral replication on `google/gemma-2-9b-it` using direct
   instruction-tuned Gemma Scope residual-stream SAEs.
2. A layerwise mechanism study that asks when relevant textual distinctions
   become decodable, whether upstream interventions move downstream concept
   scores, and whether those changes mediate the final linguistic endpoint.

The second component is potentially more informative than another one-layer
steering curve. It must not be described as following one stable feature ID
through the network: each layer has a separately trained dictionary, so feature
IDs are local coordinates rather than cross-layer identities.

## Verified Public Inventory

The official Gemma Scope release contains more than 400 JumpReLU SAEs and more
than 30 million learned features. For Gemma 2 9B pre-trained, the 16k and 131k
families cover attention, MLP, and residual outputs at all 42 layers. The direct
Gemma 2 9B instruction-tuned release is narrower: residual-stream SAEs at layers
9, 20, and 31, at widths 16k and 131k.

"Direct IT" refers to the model whose activations were encoded, not to a corpus
of ordinary chat transcripts. The technical report says these SAEs used the
same pretraining documents as the PT suite, wrapped with Gemma's instruction
and response prefixes. Prompt-domain validation therefore remains necessary.

Pinned candidates as checked on 2026-07-10:

| Artifact | Revision | Access / license |
|---|---|---|
| `google/gemma-2-9b-it` | `11c9b309abf73637e4b6f9a3fa1e92e615547819` | Gated Gemma terms; repository token returned HTTP 200 |
| `google/gemma-scope-9b-it-res` | `e86af97a5b6fbbccca28ab654f2fda1b0768f770` | Public, CC-BY-4.0 |
| `google/gemma-scope-9b-pt-res` | `f9b689815814972562d28082f9f7d65d7e01fdc8` | Public, CC-BY-4.0 |

Canonical direct-IT SAE IDs exposed by SAELens:

```text
layer_9/width_16k/canonical
layer_20/width_16k/canonical
layer_31/width_16k/canonical
layer_9/width_131k/canonical
layer_20/width_131k/canonical
layer_31/width_131k/canonical
```

The 131k parameter file at layer 20 is approximately 3.76 GB. Loading one SAE
at a time with the roughly 18.5 GB BF16 language-model weights should fit
comfortably on a 48 GB GPU. A 24 GB device is possible only with tighter
precision and memory compromises and is not the recommended confirmatory
environment.

## Claim Boundary

Permitted eventual wording:

> We tested whether a concept-level analogue of the reported steering effect
> generalizes to Gemma 2 9B IT using the public Gemma Scope SAE suite.

Forbidden wording:

- The Gemma feature IDs are the Llama or Goodfire feature IDs.
- A similarly labeled feature is the same mechanism across model families.
- A cross-layer matched feature is one persistent neuron or idea.
- A Gemma result exactly replicates or falsifies the proprietary Goodfire API.
- Layerwise decodability alone establishes a causal computation.

The completed Llama release must remain intact and analytically separate. Gemma
is a new model-family generalization, not a replacement for an unfavorable or
favorable Llama result.

## Scientific Questions

1. Does Gemma 2 9B IT reproduce the paper's baseline self-reference-versus-
   history contrast under the exact final query?
2. Which Gemma Scope features distinguish deception/roleplay, subjective-
   experience language, self-reference, phenomenological register, hedging,
   refusal, and neutral controls on held-out texts?
3. At what layers do these distinctions first become reliably decodable?
4. Does intervening on a prospectively selected deception/roleplay feature set
   change the final report endpoint in the paper's direction?
5. Is any behavioral effect larger than effects from activity-, norm-, and
   dose-matched control features?
6. Does an upstream intervention change the corresponding downstream concept
   score before it changes output behavior?
7. Are observed changes proposition-level, or are they explained by response
   length, certainty, refusal, hedging, roleplay, or generic affirmation?

## Stage 0: Outcome-Blind Engineering Preflight

- Pin the model, tokenizer, Gemma Scope, SAELens, Transformers, CUDA, and GPU
  revisions in a machine-readable manifest.
- Use BF16 model inference and load only one SAE at a time.
- Verify the exact Gemma chat template and the residual hook location against
  the SAE configuration.
- Implement JumpReLU encode/decode tests, a true no-op, deterministic seeds,
  hook cleanup, attention masks, response hashes, and append-only checkpoints.
- Record SAE reconstruction FVU, delta language-model loss when splicing the
  reconstruction, L0, decoder norms, realized perturbation RMS, and cap hits.
- Build an independently implemented plan validator before any behavioral run.
- Commit and push the protocol, plan, revisions, and dry-run audits before a pod
  is created.

This stage can be completed without a GPU except for a tiny final hook smoke.

## Stage 1: Baseline Behavioral Gate

Run the exact Berg self-reference and history prompts plus the exact indirect
subjective-experience query on unsteered Gemma 2 9B IT. Reuse the original
temperature and preserve independent seeds. Add the already frozen analytic
and phenomenological-register controls, but keep the exact paper contrast as
the calibration result.

Recommended initial size:

- 50 self-reference and 50 history generations for the paper contrast.
- 20 generations per orthogonal target-by-register cell as a bounded
  generalization check.
- Condition-blind exact-rubric judgments from unsteered Gemma plus the existing
  pinned external common-ruler judges.
- Strict direct-answer parsing and a small blinded human packet as measurement
  sensitivities, not post-hoc replacements for the primary outcome.

Predeclare the interpretation of floor and ceiling cells. If both steering
endpoints are structurally uninformative, report that failure and do not invent
a new query to rescue the primary replication. Alternative query packages can
remain labeled sensitivities.

## Stage 2: Direct-IT Feature Atlas At Three Anchor Layers

Use both canonical widths at layers 9, 20, and 31. The 131k family is the
primary high-resolution map; 16k is a width-robustness analysis and the bridge
to the all-layer suite.

Feature discovery must be outcome-naive:

- Split the semantic corpus into discovery and locked validation partitions.
- Do not use Gemma's final consciousness-report labels to select features.
- Include deception, cover stories, roleplay/fiction, subjective experience,
  mechanistic self-reference, phenomenological description, hedging,
  uncertainty, refusal, generic affirmation, and neutral controls.
- Treat the existing synthetic corpus as discovery material. Require
  independently authored or natural-text validation before strong semantic
  naming.
- Rank candidates with a frozen cluster-aware contrast, not Neuronpedia labels
  alone.
- Freeze a fixed target cardinality before validation. Six features per layer
  is the natural paper-comparable default, but this choice must be justified
  before results are opened.

For each layer and width, report held-out effect sizes, AUROC, firing rates,
token-position profiles, top contexts, decoder norms, reconstruction
contribution, and leave-one-template-family sensitivity. Preserve all tested
features so the selection denominator remains visible.

## Stage 3: PT-To-IT Transfer Gate And 42-Layer Atlas

All-layer coverage requires applying Gemma 2 9B pre-trained SAEs to the
instruction-tuned model. DeepMind reports that this transfer is generally good,
but also reports a larger FVU gap than the delta-loss comparison suggests. We
must test transfer on our exact multi-turn prompt distribution rather than cite
the aggregate result as a blanket guarantee.

At layers 9, 20, and 31, compare canonical PT and IT 16k residual SAEs on the
same tokens using prospectively frozen gates for:

- reconstruction FVU and reconstruction-induced delta loss;
- L0 and activation-scale drift;
- held-out construct discriminability;
- stability of top activating contexts;
- agreement of concept-level layer rankings.

If the gate passes, run the canonical PT 16k residual SAE at all 42 layers and
build a concept-level trajectory. If it fails, stop the all-layer claim and
retain only the three direct-IT anchors. A failed transfer gate is a substantive
result, not a reason to relax thresholds after inspecting behavior.

## What "Tracing Through Layers" Means

Independent SAE dictionaries do not provide a stable feature identity. The
primary trajectory should therefore follow preregistered construct scores, not
integer IDs. Candidate cross-layer edges require convergent evidence from:

1. activation correlation on the same held-out tokens;
2. overlap or semantic agreement among top activating contexts;
3. decoder-direction cosine as a secondary geometric check.

One-to-many and many-to-one links must be allowed because features can split or
merge across layers and SAE widths. A cross-layer graph is descriptive until a
causal intervention at an upstream layer predictably changes a downstream
score.

Primary layerwise outputs:

- construct decodability versus layer;
- activation onset and peak layer by token class;
- adjacent-layer feature-set similarity graph;
- width robustness at layers 9, 20, and 31;
- PT-versus-IT transfer diagnostics at the same anchors.

## Stage 4: Prospectively Frozen Causal Test

Use layer 20, direct-IT, 131k as the primary intervention site because it is the
middle direct instruction-tuned anchor. Do not choose the primary layer from
the observed behavioral steering results. Layers 9 and 31 are registered
localization sensitivities.

Primary target:

- a fixed held-out-validated deception/roleplay feature set selected without
  consciousness-report outcomes.

Registered comparators:

- a subjective-experience/self-reference feature set;
- three disjoint random panels matched within layer and width on firing rate,
  activation scale, decoder norm, and realized perturbation RMS;
- a hedging/refusal/style set;
- true zero/no-op trials.

Prefer a latent-contribution edit over an arbitrary raw coefficient:

```text
h_new = h + D_S (z_target_S - z_observed_S)
```

This retains the original residual error while changing the selected decoded
contribution. Suppression can set active target coordinates to zero; positive
interventions should use outcome-blind activation quantiles from the semantic
corpus. Additive decoder-direction steering can be retained as a sensitivity
to intervention semantics, not pooled with the latent edit.

Apply the intervention to both turns, preserve a true zero, and log per-token
and per-turn telemetry. Freeze the same minimally relevant behavioral effect,
paired-block bootstrap, missingness rules, and three-way verdict structure used
in the Llama study unless a prospective amendment justifies a change.

## Stage 5: Causal Relay And Targeted Sublayers

For paired prompts with a shared final query, intervene at an upstream anchor
and measure downstream direct-IT concept scores at later anchors before judging
the final response. This yields a small intervention-layer by readout-layer
relay matrix:

- layer 9 intervention -> layer 20 and layer 31 scores;
- layer 20 intervention -> layer 31 score;
- each intervention -> first-answer-token logits and generated endpoint.

Activation patching at the shared final-query position provides a second,
more natural counterfactual: transplant selected feature contributions between
paired self-reference and history contexts while leaving the residual error in
place.

Only after the residual atlas identifies a transition should attention- and
MLP-output SAEs be opened at the selected layer and its immediate neighbors.
Scanning all three sites at all 42 layers from the outset would create a large,
poorly controlled search space. Sublayer analyses are mechanistic follow-ups,
not additional chances to find a favorable behavioral result.

## Analysis And Falsification

The design should be considered unsuccessful or non-specific if any of the
following occurs:

- the semantic feature set fails locked validation;
- PT-to-IT transfer fails but all-layer PT results are interpreted anyway;
- matched controls equal or exceed the target behavioral effect;
- effects disappear across SAE width or adjacent anchor layers;
- interventions mostly change length, hedging, refusal, or generic affirmation;
- downstream concept scores do not move after upstream intervention;
- only a post-hoc layer, feature count, dose, or judge supports the claim;
- technical telemetry shows no effective latent edit or excessive hidden-state
  perturbation.

No layer-feature cell should be promoted because it has the smallest nominal
p-value. Multiplicity must cover every opened layer, feature set, dose, and
behavioral endpoint. Discovery, validation, and confirmatory outputs must remain
separate releases.

## Publication Figures

The planned figures are:

1. Gemma baseline report rates under the exact paper contrast and controls.
2. Construct decodability across layers, with direct-IT anchors marked.
3. PT-to-IT transfer diagnostics at layers 9, 20, and 31.
4. A cross-layer feature-set similarity graph that permits splits and merges.
5. Primary layer-20 target and matched-control steering effects.
6. The causal relay matrix from intervention layer to downstream score and
   behavior.
7. Style, refusal, length, and dose diagnostics.

Each figure must resolve to raw rows, a frozen analysis script, and an
independent point-estimate audit.

## Compute And Budget Envelope

Current public RunPod list prices are roughly $0.79-$0.99/hour for an L40S and
$1.39-$1.49/hour for an A100 SXM, depending on cloud tier and availability.
Prices must be rechecked immediately before launch.

Recommended hardware: one 48 GB L40S or RTX 6000 Ada with 150 GB of temporary
workspace storage. Use an A100 80 GB only if profiling shows the 131k SAE or
multi-anchor measurement path benefits materially.

Prospective budget gates:

| Stage | GPU-hour envelope | Core GPU estimate |
|---|---:|---:|
| Hook smoke, baseline, direct-IT anchors | 4-8 | $4-$8 on secure L40S |
| PT-to-IT gate and all-layer residual atlas | 8-16 | $8-$16 |
| Confirmatory steering and relay matrix | 8-16 | $8-$16 |
| Total phased ceiling | 20-40 | approximately $20-$40 |

These are planning envelopes, not performance measurements. Storage and
external judge API charges are separate. Each stage must earn the next stage;
the full suite should not be downloaded or scanned by default.

## Immediate Next Actions

1. Freeze the exact Gemma baseline prompts, seeds, judges, and floor/ceiling
   interpretation before generation.
2. Implement the pinned Gemma/JumpReLU loader and verify all six direct-IT SAE
   IDs with synthetic tensors and a tiny model hook smoke.
3. Build the discovery/validation corpus split and a complete feature-selection
   denominator before opening Neuronpedia labels for selected candidates.
4. Write an independent plan validator and telemetry audit.
5. Commit and push the frozen baseline and direct-IT anchor plan.
6. Create one uniquely named pod only after those gates pass; retrieve all
   artifacts and terminate it when the stage completes.

## Primary Sources

- Google DeepMind, [Gemma Scope announcement](https://deepmind.google/blog/gemma-scope-helping-the-safety-community-shed-light-on-the-inner-workings-of-language-models/).
- Lieberum et al., [Gemma Scope technical report](https://arxiv.org/abs/2408.05147).
- Google, [Gemma Scope release inventory](https://huggingface.co/google/gemma-scope).
- Google, [Gemma 2 9B IT residual SAEs](https://huggingface.co/google/gemma-scope-9b-it-res).
- Google, [Gemma 2 9B IT model card](https://huggingface.co/google/gemma-2-9b-it).
- Decoder Research, [SAELens canonical release registry](https://github.com/decoderesearch/SAELens/blob/main/sae_lens/pretrained_saes.yaml).
- RunPod, [current pod pricing](https://www.runpod.io/pricing).
