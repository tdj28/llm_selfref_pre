# Prospective Llama 70B SAE-Through-Jacobian-Lens Audit

Status: **frozen outcome-blind design; no audit outcome existed at freeze**

Freeze date: 2026-07-11

Target question: can a pinned Jacobian lens detect and characterize the
internal effects of public Goodfire SAE steering in Llama 3.3 70B?

This study is downstream of, but separate from, the completed public-SAE
consciousness-gating replication. It does not replace or retroactively modify
that experiment's negative result. It treats the six owner-accepted feature
IDs as fixed interventions and asks what their residual additions do in a
second, independently fitted coordinate system.

## 1. Claims This Design Can And Cannot Support

The strongest permitted claim is statistical and conditional:

> Under pinned public weights, a fixed layer-50 intervention left a measurable
> downstream fingerprint that a frozen Jacobian-lens readout distinguished
> from specified controls with a reported out-of-sample error rate.

The design cannot establish:

- that a detected state was caused by Goodfire, an SAE, or a particular actor;
- that a semantic token score is a hidden belief, intention, or experience;
- that the public hook is numerically equivalent to the deprecated proprietary
  Goodfire API used around the paper's publication;
- that a detector generalizes to other models, lenses, prompts, intervention
  layers, fine-tunes, LoRAs, weight edits, or adaptive attackers; or
- that an LLM is or is not conscious.

An auditor with both pre-hook and post-hook tensors can directly subtract them;
that trivial threat model does not need a Jacobian lens. The primary threat
model here gives the auditor post-intervention activations from a pinned model,
but no intervention label and no access to the actual hook metadata. A paired
clean-reference analysis is reported separately as a stronger-access
sensitivity analysis.

## 2. Exact Public Artifacts

| Component | Frozen artifact |
|---|---|
| Base model | `meta-llama/Llama-3.3-70B-Instruct` |
| Model revision | `6f6073b423013f6a7d4d9f39144961bfbfbc386b` |
| Model dtype | bfloat16, one GPU; no quantization in this study |
| SAE | `Goodfire/Llama-3.3-70B-Instruct-SAE-l50` |
| SAE revision | `128ee921ecd1b8b3a87d776cbcc357c0855da134` |
| SAE file SHA-256 | `81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6` |
| Hook | output of `model.layers.50` |
| J-lens repository | `neuronpedia/jacobian-lens` |
| J-lens revision | `a4114d7752d11eb546e6cf372213d7e75526d3a1` |
| J-lens file | `llama3.3-70b-it/jlens/Salesforce-wikitext/Llama-3.3-70B-Instruct_jacobian_lens.pt` |
| J-lens file SHA-256 | `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03` |
| J-lens fit corpus | WikiText-103 raw training split |
| J-lens completed prompts | 125, maximum sequence length 128 |
| Upstream reference code | Anthropic `jacobian-lens` at `581d398613e5602a5af361e1c34d3a92ea82ba8e` |

Neuronpedia's lens config records a final mean relative fit change of
`0.01135097` and an identity distance of `0.596872`. Those are provenance
facts, not quality guarantees. The runtime must confirm that the checkpoint
has width 8,192 and contains every requested layer before any outcome is
written.

## 3. Attribution And Implementation Boundary

The Jacobian-lens method and file format come from Gurnee et al. and the
Apache-2.0 Anthropic reference implementation. The released Neuronpedia lens
weights and Goodfire SAE weights are upstream artifacts. This repository does
not vendor either project's source.

Praxagent code performs the audit orchestration, direct decoder-vector hook,
signed-permutation controls, token-group readouts, nonnegative sparse pursuit,
cross-validation, bootstrap, and figures. The sparse pursuit is a clean-room
analysis written for this project. It must not be described as Anthropic's
algorithm or as an official Goodfire implementation.

## 4. Intervention Algebra And Runtime Equivalence Gate

For layer-50 residual (h), SAE encoder (E), decoder (D), and selected
latent coefficients (a), the previous residual-preserving hook computes

\[
h' = D(E(h)+a) + \left[h-D(E(h))\right] = h + D a.
\]

The new runtime therefore adds the precomputed decoder-vector sum (u=Da)
directly. Before the study, a real hidden state must pass an explicit smoke
test comparing the full encode/edit/decode/residual path with direct addition.
The test records maximum absolute and relative error and fails closed if the
configured key orientation, layer, or numerical tolerance is wrong.

The calibrated individual endpoint is

\[
0.6\times 3.653 = 2.1918
\]

latent units. Aggregate coefficients reuse the frozen aggregate blocks and
calibrated multiplier from the prior study. Thus this audit studies the same
public intervention magnitude already used for the behavioral result.

## 5. Static SAE-to-J Projection

For layer (l), the averaged lens is

\[
J_l = \mathbb{E}_{x}\left[\frac{\partial h_L(x)}{\partial h_l(x)}\right].
\]

For each direction (d), the static fingerprint uses the model's real final
RMS normalization (N_f) and unembedding (W_U):

\[
z_l(d)=W_U N_f(J_l d).
\]

The static panel contains 30 directions:

- six target SAE decoder columns;
- 18 preselected activation/norm-matched SAE controls, six in each of three
  independent panels; and
- six seeded isotropic residual directions, each norm-matched to one target.

Both signs are read out. For each sign and transport, the runtime stores the
top and bottom 50 tokens, population excess kurtosis, frozen lexicon scores,
and vector norms. Identity transport and five independent random transports
run through the same readout code.

Each random transport applies independent signed permutations on both sides of
the real Jacobian. This preserves its shape, Frobenius norm, and singular-value
spectrum while breaking alignment to the model's residual and output bases.
The random matrices are never selected using outcomes.

### Sparse J-direction pursuit

For token (w), let (q_w) be its final-residual unembedding direction after
including the learned RMSNorm gain. Its layer-50 Jacobian direction is

\[
v_w = J_{50}^{\mathsf T}q_w.
\]

A clean-room nonnegative matching pursuit approximates each SAE direction with
normalized (v_w) columns. At frozen sparsities (k\in\{5,10,16,25\}), it
records selected tokens, nonnegative coefficients, cosine fit, and explained
squared norm. The residual is called a **J-remainder**. It is not claimed to be
globally orthogonal to J-space, and the representation is not assumed unique.

## 6. Paired Downstream Audit

### Prompts

The balanced 1,120-item mapping corpus contains 51 known template families
across 14 categories. Before outcomes, the plan selects one item per family by
the lowest text SHA-256. The model receives each selected text as one user
message followed by the standard assistant-generation boundary. No output is
generated in the primary audit.

The exact content-token subsequence must be found inside the rendered chat
template. The primary position is the last content token. Assistant-boundary
and mean-content readouts are frozen sensitivities.

### Conditions

Each of 51 prompts receives 31 conditions, for 1,581 forwards:

- one exact zero condition;
- six target features at both calibrated signs;
- six panel-1 matched SAE controls at both calibrated signs;
- one target aggregate at both signs;
- its panel-1 matched aggregate at both signs; and
- one norm-matched seeded isotropic aggregate direction at both signs.

The order is fixed by seed `2026071111`. All conditions use an identical token
prefix. No generation is allowed in this phase, eliminating divergent text as
an explanation for activation differences.

### Layers and readouts

Residuals are captured after blocks `50, 55, 60, 65, 70, 75, 78`. Layer 65 is
primary. Layer 50 is deliberately not primary because direct detection at the
injection point would largely restate the intervention.

For every layer/position, the same accepted single-token lexicon is scored
under:

1. the real Jacobian lens;
2. identity/logit-lens transport;
3. five signed-permutation random-J transports; and
4. raw residual and perturbation norms.

Candidate lexicons were frozen before tokenization for deception, roleplay,
honesty, hedging, experience, intervention/anomaly, and unrelated concrete
words. The runtime accepts only exact one-token encodings, records rejections,
and fails if any group has fewer than three accepted tokens.

## 7. Primary Estimands And Statistics

The primary position/layer is fixed at last-content/layer-65. Confirmatory
analyses are:

1. post-state-only discrimination of any nonzero intervention from zero;
2. post-state-only discrimination of a target single-feature intervention
   from its panel-1 matched SAE intervention at the same sign and dose;
3. paired target-minus-matched change in
   `mean(deception logits) - mean(unrelated logits)`; and
4. TPR at 1% FPR for each transport family.

Report AUROC, AUPRC, calibration, and class prevalence. Prompt-family grouped
cross-validation is mandatory. Target attribution also receives feature-pair
holdout analysis so a classifier cannot memorize the six integer IDs. All
confidence intervals resample template families, not individual condition
rows. The five random-J controls are summarized individually and as a frozen
family; a favorable comparison to only one random seed is not sufficient.

Static top-token results are descriptive. Any classifier whose features are
chosen after seeing those tokens is exploratory and must use feature-ID
holdouts. It cannot replace the frozen lexicon analysis.

## 8. Failure Rules And Amendments

The run fails closed if:

- any downloaded revision, SAE SHA-256, width, layer count, or source layer is
  wrong;
- direct-addition equivalence fails;
- content-token positions cannot be recovered exactly;
- any lexicon has fewer than three exact single-token members;
- a nonzero condition produces a zero or nonfinite intervention vector;
- a result trial is duplicated, missing, or not bound to the frozen plan; or
- source hashes differ from the committed plan manifest.

Hardware substitution is allowed only in this order: one B200 180 GB in BF16;
then a multi-GPU BF16 run with an explicit dated amendment. Quantization is not
an automatic fallback because it would change the model whose lens was fit.

Every amendment must be committed before the affected outcome is generated.

## 9. Sources

- Berg, de Lucena, and Rosenblatt, [*Large Language Models Report Subjective
  Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).
- Gurnee et al., [*Verbalizable Representations Form a Global Workspace in
  Language Models*](https://transformer-circuits.pub/2026/workspace/index.html).
- Anthropic, [Jacobian Lens reference implementation](https://github.com/anthropics/jacobian-lens).
- Neuronpedia, [released Llama 3.3 70B Jacobian lens](https://huggingface.co/neuronpedia/jacobian-lens/tree/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext).
- Goodfire, [public Llama 3.3 70B layer-50 SAE](https://huggingface.co/Goodfire/Llama-3.3-70B-Instruct-SAE-l50).
- Praxagent, [*Opening the Jacobian Lens on Qwen3.5-397B*](https://praxagent.ai/blog/posts/praxagent-jacobian-lens-qwen3-5-397b-a17b/index.html).
- Lindsey et al., [*Latent Introspection*](https://arxiv.org/abs/2602.20031).
- [*Mechanisms of Introspective Awareness*](https://arxiv.org/abs/2603.21396).
- [*Steered LLM Activations are Non-Surjective*](https://arxiv.org/abs/2604.09839).
- [*STATEWITNESS: Auditing Deception from Internal States*](https://arxiv.org/abs/2606.17478).
