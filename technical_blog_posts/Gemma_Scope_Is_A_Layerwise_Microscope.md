---
title: "Gemma Scope Is a Layerwise Microscope, Not a Mind Reader"
date: 2026-07-11
tags: ["AI", "LLM", "machine-learning", "interpretability", "sparse-autoencoders", "Gemma", "reproducibility", "tutorials"]
author: Timothy Jones
summary: "A practical guide to using Gemma Scope for layerwise sparse-autoencoder research, including the crucial distinction between direct instruction-tuned SAEs and exploratory transfer from pretrained-model SAEs."
---

{{< panel "info" >}}
**AI-use disclosure.** Generative-AI tools were used during drafting and
editorial revision. The author designed the study, selected the analyses,
inspected the outputs, and takes responsibility for the final text and claims.
{{< /panel >}}

{{< panel "info" >}}
**Abstract.** Gemma Scope is unusually useful for open mechanistic
interpretability because it supplies sparse autoencoders (SAEs) across many
layers and internal sites of Gemma 2. That breadth makes layerwise questions
possible, but it does not make every SAE interchangeable. In particular, the
public Gemma 2 9B instruction-tuned residual SAEs directly cover layers 9, 20,
and 31, while the all-42-layer suite was trained on the pretrained model. This
post explains the inventory, the JumpReLU SAE, why feature IDs do not persist
across dictionaries, and how we prospectively tested whether pretrained SAEs
could be applied to the instruction-tuned model. Our frozen transfer gate
failed on chat-centered reconstruction even though semantic profiles aligned
strongly. We therefore preserve the direct instruction-tuned experiment as the
confirmatory study and label the all-layer map as exploratory. That failure is
not an inconvenience to hide. It is exactly what a gate is for.
{{< /panel >}}

### Learning objectives

By the end of this post you should be able to:

1. explain why Gemma Scope is different from a one-model, one-layer SAE release;
2. distinguish a model layer, an activation site, an SAE width, and a feature ID;
3. explain why a feature ID at layer 9 is not the same object as that integer at layer 20;
4. distinguish a direct instruction-tuned SAE analysis from PT-SAE-on-IT transfer; and
5. understand why a failed transfer gate narrows a claim instead of invalidating an experiment.

---

## What Gemma Scope Actually Released

Sparse autoencoders are expensive to train at serious scale. A typical public
release gives researchers one SAE at one layer. That is enough to inspect a
local dictionary, but not enough to ask how a construct changes as information
moves through a model.

[Google DeepMind's Gemma Scope release](https://deepmind.google/blog/gemma-scope-helping-the-safety-community-shed-light-on-the-inner-workings-of-language-models/)
changed that tradeoff. The original release contains more than 400 SAEs and
more than 30 million learned features across Gemma 2 models. DeepMind reports
that producing the suite used about 15 percent of the compute used to train
Gemma 2 9B and involved saving about 20 pebibytes of activations. The
[technical report](https://arxiv.org/abs/2408.05147) describes JumpReLU SAEs at
all layers and sublayers of the pretrained Gemma 2 2B and 9B models, selected
sites in 27B, and a smaller comparison release for instruction-tuned 9B.

That inventory is what makes Gemma Scope a layerwise microscope. It lets us
ask whether a measured construct appears early, late, gradually, abruptly, in
attention output, or in multilayer-perceptron output. It does **not** let us
read a model's private thoughts. An SAE is a learned approximation to model
activations, and an English feature label is an interpretation of observed
activation patterns.

{{< mermaid >}}
flowchart LR
  H0["Dense residual activation<br/>at layer l"] --> E["JumpReLU encoder"]
  E --> F["Sparse feature activations<br/>for SAE at layer l"]
  F --> D["Decoder directions"]
  D --> R["Approximate reconstruction<br/>of the original activation"]
  F -. "activation evidence" .-> L["Human-readable feature gloss"]
  L -. "not an identity claim" .-> M["Mechanistic interpretation"]
{{< /mermaid >}}

<p class="figure-note">An SAE decomposes one site's dense activation into a
sparse set of learned coordinates. The label is downstream of the numerical
object, not part of the object itself.</p>

## Four Coordinates You Must Keep Separate

It is easy to compress an SAE result into a phrase such as "feature 12345."
That phrase omits most of the address. A complete coordinate includes at least:

| Coordinate | Example in this study | Why it matters |
|---|---|---|
| Base model | `google/gemma-2-9b-it` | Activations depend on the exact model weights |
| Model layer | 9, 20, or 31 | Different layers represent different stages of computation |
| Activation site | residual post, attention output, or MLP output | Different sites contain different tensors |
| SAE checkpoint | repository, revision, width, and sparsity variant | Each SAE learns its own dictionary |
| Feature ID | an integer index into that checkpoint | The integer is meaningful only inside the exact dictionary |

The same integer in two SAEs is usually no more meaningful than row 317 in two
unrelated spreadsheets. Even when two features respond to similar text, they
remain separately learned directions. Cross-layer similarity can support a
descriptive link; it does not turn the two coordinates into a persistent
identity.

## A Compact JumpReLU SAE

Let \(h \in \mathbb{R}^{d_{model}}\) be one model activation and let the SAE
have \(N\) learned features. In simplified notation, Gemma Scope's JumpReLU
encoder computes:

\[
z = h W_{enc} + b_{enc}
\]

\[
f_i = z_i \cdot \mathbb{1}[z_i > \theta_i]
\]

where \(\theta_i\) is a learned threshold. The decoder reconstructs the dense
activation:

\[
\hat{h} = f W_{dec} + b_{dec}.
\]

Most entries of \(f\) are zero for a given token. Researchers inspect which
texts produce large values for one coordinate, then assign a tentative gloss
such as "roleplay," "quotation," or "uncertainty." The gloss is useful
metadata. It is not a proof that the feature is a pure, exclusive, or causally
necessary representation of that concept.

## The Gemma 2 9B Inventory Has an Important Asymmetry

The [official Gemma Scope inventory](https://huggingface.co/google/gemma-scope/blob/3fd475be527e3db5185dbffbd5f9ecdf62117064/README.md)
lists broad coverage for the pretrained 9B model and narrower coverage for the
instruction-tuned 9B model:

| Model/SAE pairing | Residual coverage used here | Widths used here | Status in our study |
|---|---:|---:|---|
| Gemma 2 9B IT with direct IT SAEs | layers 9, 20, 31 | 16,384 and 131,072 | Confirmatory semantic anchors |
| Gemma 2 9B IT with direct IT SAEs | layer 20 primary; layers 9 and 31 sensitivity | 131,072 primary; 16,384 width check | Confirmatory causal steering |
| Gemma 2 9B IT with pretrained-model SAEs | all 42 residual layers | 16,384 | Transfer-gated; exploratory after gate failure |
| Gemma 2 9B IT with pretrained-model sublayer SAEs | selected transition neighborhoods | 16,384 | Exploratory localization only |

Why not simply apply the pretrained SAEs to the instruction-tuned model and
call the result an all-layer map? Because instruction tuning changes the model.
The tensors have compatible shapes, but shape compatibility is not evidence
that a dictionary still reconstructs the new activation distribution well.

## We Froze a Transfer Gate Before Mapping All 42 Layers

Before examining any final consciousness-report outcome, we registered a gate
at layers 9, 20, and 31. At each anchor we compared the direct IT SAE against
the corresponding pretrained-model SAE applied to the IT model. The gate asked
two different questions:

1. **Reconstruction transfer:** does the PT SAE reconstruct instruction-tuned
   chat activations with acceptably low fraction of variance unexplained (FVU)?
2. **Semantic-profile transfer:** do PT and IT dictionaries produce similar
   category-level profiles for our deception/roleplay contrast corpus?

The thresholds were frozen in advance:

| Gate component | Frozen requirement |
|---|---:|
| Median PT-on-IT chat-centered FVU | at most 0.35 |
| Median PT minus direct-IT FVU | at most 0.10 |
| Median PT-versus-IT category-profile Spearman correlation | at least 0.60 |
| PT deception/roleplay confirmation contrast | positive at all three anchors |

The gate required every component. This prevents us from deciding after seeing
the measurements which quality criterion should count.

## The Gate Failed, Informatively

The semantic checks passed. Median category-profile correlation was `0.952`,
and the locked deception/roleplay contrast was positive at all three anchor
layers. But the chat-centered reconstruction checks failed badly:

| Measurement | Observed | Frozen maximum | Result |
|---|---:|---:|---|
| Median PT-on-IT chat-centered FVU | 6.260 | 0.35 | Fail |
| Median PT minus direct-IT FVU | 1.775 | 0.10 | Fail |
| Median category-profile Spearman | 0.952 | minimum 0.60 | Pass |
| Positive deception contrast at every anchor | yes | required | Pass |

FVU above 1 means reconstruction error exceeded the centered variance in this
small, repetitive chat probe. A supplementary raw-text reconstruction check
was much more ordinary: direct-IT anchor FVU ranged from about `0.121` to
`0.325`, while PT-on-IT anchor FVU ranged from about `0.146` to `0.329`.
That discrepancy suggests the frozen chat-centering diagnostic is unusually
sensitive to this prompt set. It does not make the failed registered gate pass.

This distinction matters:

- The PT dictionaries retain useful category structure on the designed corpus.
- They did not satisfy our prospective reconstruction-transfer standard on the
  exact chat distribution.
- Therefore the all-layer PT-on-IT map can be reported as descriptive,
  post-gate exploration, but not as confirmatory evidence that the same SAE
  representation transfers cleanly.

{{< panel "warning" >}}
**A failed gate is part of the result.** Replacing the registered diagnostic
with a more favorable one after seeing both would convert a prospective test
into a post-hoc choice. We report the raw-text diagnostic as context and keep
the original verdict unchanged.
{{< /panel >}}

## Confirmatory and Exploratory Branches

The study now has two deliberately separate branches:

{{< mermaid >}}
flowchart TD
  P["Outcome-free semantic corpus"] --> I["Direct IT SAEs<br/>layers 9, 20, 31"]
  I --> C["Confirmatory feature selection<br/>and calibrated causal steering"]
  I --> G["Frozen PT-to-IT transfer gate"]
  G -->|"reconstruction checks failed"| X["Exploratory PT-on-IT atlas<br/>all 42 residual layers"]
  X --> S["Exploratory attention/MLP<br/>transition neighborhoods"]
  X --> E["Descriptive adjacent-layer<br/>feature links"]
  X -. "cannot alter" .-> C
{{< /mermaid >}}

The causal experiment uses direct instruction-tuned SAEs only. The exploratory
atlas cannot change feature selection, steering strength, the primary layer,
the minimum relevant effect, the judge panel, or the behavioral verdict. Its
job is narrower: show where similar construct-level profiles appear and where
their trajectories change enough to motivate future work.

## What We Mean by "Tracing" a Construct

We do not search for one magic feature ID and follow that integer from layer 0
to layer 41. Instead, at every SAE we independently select a small feature set
using the same frozen construct definition and held-out corpora. We then track:

1. the set's held-out category contrast at each layer;
2. the similarity of item-level activation profiles across adjacent layers;
3. decoder-direction cosine similarity, where dimensions are compatible;
4. overlap among the highest-activating held-out items; and
5. attention-output versus MLP-output localization near selected transitions.

An adjacent-layer link is descriptive. It says that two separately learned
features respond similarly under disclosed criteria. It does not establish a
causal circuit, a persistent feature identity, or an internal experience.

## What the Microscope Can and Cannot Tell Us

| Supported question | Unsupported shortcut |
|---|---|
| Which learned directions activate on a frozen contrast corpus? | What the model is secretly thinking |
| Where does a construct score become stronger or weaker? | That one feature literally travels between layers |
| Does a calibrated intervention change later activations or outputs? | That the English label names the sole causal mechanism |
| Does the effect beat matched controls and a frozen relevance threshold? | That any output change establishes consciousness or deception |
| Does a public implementation reproduce a registered signature? | That it is byte-identical to a proprietary hosted API |

The language of "microscopes" is helpful only if we retain the limitations of
real microscopes: sample preparation matters, calibration matters, lenses have
aberrations, and seeing a structure is not the same as understanding its role.

## Reproduce the Outcome-Free Parts

The protocol, source, machine plans, exact revisions, validation logs, and
small release artifacts are public in the project repository. The central
commands are:

```bash
python experiments/exp2_sae/build_gemma_scope_9b_plan.py \
  data/gemma_scope_9b/confirmatory_v1_plan_20260711

python experiments/exp2_sae/validate_gemma_scope_9b_plan.py \
  data/gemma_scope_9b/confirmatory_v1_plan_20260711

python experiments/exp2_sae/run_gemma_scope_9b_atlas.py \
  --plan-dir data/gemma_scope_9b/confirmatory_v1_plan_20260711 \
  --outdir data/gemma_scope_9b/confirmatory_v1_20260711/atlas
```

The GPU path pins the Gemma model, both SAE repositories, Transformers, SAE
Lens, PyTorch, CUDA-visible runtime metadata, and every generated artifact
hash. A custom JumpReLU implementation was checked against SAE Lens on the
same tensors; selected activations and reconstructions matched exactly in the
runtime smoke test.

## Bottom Line

Gemma Scope gives open researchers something unusually valuable: enough SAE
coverage to ask layerwise questions on a modern language model. The breadth of
the release does not remove the need for provenance, held-out validation,
transfer tests, controls, or causal experiments. It makes those tests possible.

Our first lesson from using it was methodological rather than dramatic. A
pretrained-model SAE can preserve striking semantic profile similarity on an
instruction-tuned model while failing a prospectively frozen reconstruction
gate on the target chat distribution. Both facts belong in the record. The
direct-IT causal experiment and the exploratory all-layer map therefore answer
different questions, and the next posts keep them separate.

## Primary sources

- Lieberum et al., [*Gemma Scope: Open Sparse Autoencoders Everywhere All At Once on Gemma 2*](https://arxiv.org/abs/2408.05147).
- Google DeepMind, [*Gemma Scope: helping the safety community shed light on the inner workings of language models*](https://deepmind.google/blog/gemma-scope-helping-the-safety-community-shed-light-on-the-inner-workings-of-language-models/).
- Google, [Gemma Scope release inventory](https://huggingface.co/google/gemma-scope/blob/3fd475be527e3db5185dbffbd5f9ecdf62117064/README.md).
- Google, [Gemma 2 9B instruction-tuned residual SAEs](https://huggingface.co/google/gemma-scope-9b-it-res).
- Berg, de Lucena, and Rosenblatt, [*Large Language Models Report Subjective Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).

---

*This is the second post in a planned interpretability series. The first,
[*Feature IDs Are Not Explanations*](https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html),
introduces SAE coordinates and feature labels using the public Llama 3.3 70B
feature map. Subsequent posts will present the Gemma layer atlas, the blinded
causal steering result, and the difference between feature similarity and a
causal relay.*
