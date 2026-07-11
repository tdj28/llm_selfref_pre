# SAE Steering Versus Jacobian-Lens Steering

Status: method comparison and next-experiment note, 2026-07-11

Primary sources:

- Gurnee et al. (2026), [Verbalizable Representations Form a Global Workspace
  in Language Models](https://transformer-circuits.pub/2026/workspace/index.html)
- Anthropic's Apache-2.0 [Jacobian Lens reference implementation](https://github.com/anthropics/jacobian-lens)

## Bottom Line

At the final hook, single-direction SAE steering and simple Jacobian-lens
steering can both reduce to adding a vector to the residual stream. Their
scientific meaning is different because the vectors are constructed for
different objectives.

- An SAE learns a sparse dictionary that reconstructs ordinary model
  activations. A feature is one learned coordinate in that dictionary.
- The Jacobian lens derives a token-indexed direction from the average
  first-order effect of an intermediate activation on current and future model
  outputs. A J-lens direction is therefore constructed around
  **verbalizability**, not activation reconstruction.

SAE steering asks what happens when a learned activation feature is edited.
J-lens steering asks what happens when a direction associated with being
disposed to verbalize a vocabulary token is written into or removed from the
residual stream.

## The Two Operations

For an SAE with encoder `E`, decoder `D`, latent vector `z = E(h)`, and retained
reconstruction residual `epsilon = h - D(z)`, a feature edit is:

```text
z' = z + alpha * e_i
h' = D(z') + epsilon
```

For a linear decoder and a one-feature additive edit, this simplifies to:

```text
h' = h + alpha * d_i
```

where `d_i` is feature `i`'s decoder direction. Variants can instead set,
clamp, or ablate the latent; those choices change the intervention semantics.

At layer `l`, the Jacobian lens fits a corpus-averaged map:

```text
J_l = E_prompt,t,t' [ partial h_final,t' / partial h_l,t ]
v_w = row_w(W_U J_l)^T
```

`v_w` is the residual-stream direction associated with future verbalization of
vocabulary token `w`. Its simplest write operation is:

```text
h' = h + alpha * v_w
```

Negative steering or projection removes a direction. The paper also swaps two
J-lens coordinates and dynamically projects out the strongest active J-space
directions across selected layers and positions.

## Key Differences

| Dimension | SAE steering | Jacobian-lens steering |
|---|---|---|
| Direction source | Dictionary learned from activation reconstruction plus sparsity | Corpus-averaged first-order map from intermediate residuals to final residuals/logits |
| Index | SAE-local feature ID | Model-tokenizer vocabulary token at a specific layer |
| Primary objective | Represent the activation distribution sparsely | Represent what an activation is disposed to make the model verbalize |
| Semantic interpretation | Post-hoc label from activating examples or automated interpretation | Token name is built into the construction, but a token is not a complete concept explanation |
| Representational coverage | Broad: semantic, syntactic, motor, and bookkeeping features | Selective verbalizable frame; most activation variance lies outside it |
| Context dependence | Feature activation is context dependent; decoder direction is fixed per SAE | Averaged lens direction is fixed per layer; active top-k J-space contents can be selected dynamically per context |
| Causal grounding | Learned correlational decomposition, followed by a causal intervention | Direction is derived from an averaged local output Jacobian, then tested by intervention |
| Typical write | Edit one or more latent coordinates, decode, and restore residual | Add/ablate a token direction, swap token coordinates, or remove dynamic top-k J-space projections |
| Main ambiguity | Feature splitting, absorption, polysemanticity, reconstruction error, and dictionary-local IDs | First-order approximation, corpus averaging, overcomplete/non-unique decomposition, arbitrary sparsity `k`, and single-token vocabulary limit |
| Compute profile | Expensive SAE training; cheap encoding and intervention after release | No SAE training, but fitting requires many backward passes and a full matrix per layer |
| Best use | Test a stable learned feature hypothesis and broad representational structure | Read and manipulate reportable intermediate content and localize its downstream disposition |

Calling the Jacobian lens "causal" requires care. Its directions derive from
an average derivative, but that derivative is local, linearized, and averaged
over contexts. It does not guarantee that the named concept is the operative
mechanism in a particular prompt. Intervention and matched controls remain
necessary.

## The Methods Overlap

The methods are complementary rather than mutually exclusive. Gurnee et al.
project SAE decoder directions through the J-lens and use lens-readout kurtosis
to estimate whether an SAE feature lies in the verbalizable J-space. They find
that only a minority of SAE features align strongly with it; low-alignment
features are often syntactic or bookkeeping features. They also report that
highly J-aligned SAE features can approximate workspace directions better than
single-token J-lens vectors.

This creates a useful two-axis description:

1. **SAE activation semantics:** what text or context activates the learned
   feature?
2. **J-space alignment:** is that decoder direction concentrated on a small set
   of future-verbalization directions?

A deception-labeled SAE feature can be semantically coherent but weakly
J-aligned. Conversely, a J-aligned SAE feature can be highly reportable without
being specific to deception, truth, selfhood, or subjective experience.

## Relevance To Experiential Reports

The Jacobian-lens paper's experiential-language intervention is not equivalent
to the Berg deception-feature intervention:

- Berg-style SAE steering edits a fixed set of six deception/roleplay
  coordinates at one layer.
- Gurnee et al. dynamically remove the ten strongest active J-lens directions
  at every position across a band of workspace layers.
- The former tests a feature-specific concealment interpretation. The latter
  broadly suppresses verbalizable intermediate content.

Gurnee et al. report that J-space ablation reduces experiential language not
only in model self-reports, but also when the model describes another person's
experience and when it writes third-person stories. The responses remain
largely coherent but become more mechanical. This is strong evidence that the
intervention changes a general experiential **reporting register**. It is not
self-specific evidence and does not identify phenomenal consciousness.

That result is directly relevant to this repository's identification argument:
an intervention can causally reduce experiential language because it removes a
verbalizable representational channel, without establishing that the channel
contains or reports subjective experience.

## Best Open Follow-Up

The strongest next experiment would combine both tools on one open model with a
frozen protocol:

1. Fit a Jacobian lens on an open instruction model using the released
   implementation, first with a bounded pilot and then a frozen corpus.
2. Measure J-lens kurtosis and sparse J-space decomposition for the already
   selected deception/roleplay, subjective-self-report, hedging/refusal, and
   matched-control SAE directions.
3. Cross intervention family: fixed SAE latent edit, fixed J-lens token-vector
   edit, dynamic top-k J-space ablation, J-stripped SAE controls, low-kurtosis
   SAE controls, isotropic random controls, and true zero.
4. Match realized perturbation norms and layer/position exposure rather than
   comparing nominal coefficients.
5. Cross target (`self` versus `other`) with register (`phenomenological`
   versus `analytic`) and include third-person experience and non-experiential
   story controls.
6. Judge explicit self-attribution, experiential register, coherence,
   hedging/refusal, and task performance separately with condition-blind
   evaluators.
7. Freeze selection rules, doses, exclusions, and the minimally relevant
   effect before opening behavioral outcomes.

Gemma 2 9B is attractive because this repository already has direct-IT Gemma
Scope feature sets, causal telemetry, and matched controls. The released J-lens
reference code demonstrates Qwen and says other Hugging Face decoder models can
be adapted, but Gemma compatibility and fitting cost require a local smoke test
before any GPU phase.

## Claim Boundary

Neither method reads a model's private ground truth.

- SAE labels are hypotheses about learned activation coordinates.
- J-lens tokens describe average output dispositions, not complete thoughts.
- Causal steering establishes that an edited direction affects measured model
  behavior under that intervention.
- A change in experiential language is not, by itself, evidence for or against
  phenomenal consciousness.
