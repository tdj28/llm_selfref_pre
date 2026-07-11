---
title: "Can a Jacobian Lens Detect SAE Steering?"
date: 2026-07-11
tags: ["AI", "LLM", "machine-learning", "interpretability", "sparse-autoencoders", "jacobian-lens", "model-auditing"]
author: Timothy Jones
summary: "A preregistered Llama 3.3 70B experiment asks whether SAE steering leaves a detectable downstream fingerprint in Jacobian-lens space."
draft: true
---

{{< panel "info" >}}
**AI-use disclosure.** Generative-AI tools were used to help implement the
experiment and draft this article. The author selected the research question,
approved the frozen design, will inspect the artifacts, and takes
responsibility for the final text and claims.
{{< /panel >}}

{{< panel "warning" >}}
**Study status.** This shell was frozen before GPU outcomes existed. Every
`RESULT_TODO` marker must be replaced from the hash-verified release bundle or
explicitly labeled unavailable. A result must not be inferred from this draft's
section order or hypotheses.
{{< /panel >}}

{{< panel "info" >}}
**Abstract.** Sparse-autoencoder steering changes a model's residual stream;
a Jacobian lens maps residual directions toward the vocabulary dispositions
they tend to influence downstream. That creates a testable question: does
public Goodfire SAE steering in Llama 3.3 70B leave a stable, out-of-sample
fingerprint in the model's released Jacobian-lens space? We project six public
deception/roleplay SAE directions, compare them with 18 activation- and
norm-matched SAE controls plus isotropic controls, and replay 1,581 paired
prefix-only interventions across 51 held-out template families. Identity-lens,
raw-norm, and five singular-spectrum-preserving random-J baselines traverse the
same analysis. **Result:** `RESULT_TODO`. The experiment can evaluate a pinned
white-box fingerprint; it cannot prove who steered a model, what the model
believes, or whether it is conscious.
{{< /panel >}}

## The Question

Our earlier public-weight work established two facts that now meet in the same
model:

1. a public Goodfire layer-50 SAE for Llama 3.3 70B contains the six
   deception/roleplay coordinates used in our replication; and
2. Neuronpedia has released a fitted Jacobian lens for the same Llama 3.3 70B
   checkpoint family.

The SAE tells us which learned activation direction we add. The Jacobian lens
asks where an intermediate direction tends to land in the model's final
residual and vocabulary geometry. Can the second instrument audit the first?

This is not the generic claim that "steering changes J-space." Gurnee et al.
already project SAE decoder directions through a Jacobian lens and causally
intervene on an SAE feature associated with suspicious or fake behavior. They
also show that a J-lens score changes monotonically under contrastive
evaluation-awareness steering. The narrower contribution here is a pinned,
open Llama 70B forensic test with matched SAE controls, random-J controls,
downstream trajectories, grouped holdouts, and an explicit evasion boundary.

## The Two Maps

Let (h_l\in\mathbb{R}^d) be the residual stream after transformer block
(l). A sparse autoencoder learns encoder features (f=E(h_l)) and decoder
directions (D=[d_1,\ldots,d_N]). Adding coefficient (a_i) to feature (i)
with reconstruction error restored is exactly

\[
h_l' = D(E(h_l)+a_i e_i) + h_l-D(E(h_l)) = h_l+a_i d_i.
\]

So this public SAE intervention is a constant residual addition once the
decoder column and coefficient are fixed.

The Jacobian lens fits a corpus average of local downstream maps:

\[
J_l=\mathbb{E}_x\left[\frac{\partial h_L(x)}{\partial h_l(x)}\right].
\]

With final RMS normalization (N_f) and unembedding (W_U), a static
vocabulary fingerprint for the SAE direction is

\[
z_l(d_i)=W_U N_f(J_l d_i).
\]

For a real prompted state, the exact paired quantity is not just
(W_UJ_ld_i). We run both prefixes and measure

\[
\Delta z_l = W_U N_f(J_l h_l^{\mathrm{steered}})
             -W_U N_f(J_l h_l^{\mathrm{clean}}),
\]

which retains the nonlinear final normalization and the model's downstream
response to the intervention.

## What Would Count as Detection?

An auditor sitting directly on the hook can subtract pre- and post-hook
tensors. That is trivial and does not require a Jacobian lens. Our primary
threat model is harder: the auditor receives post-intervention activations from
a pinned model, but not the intervention label or hook metadata.

We freeze two classification questions:

- **Any intervention:** distinguish nonzero steering from the clean condition.
- **Target attribution:** distinguish a target deception/roleplay SAE direction
  from a dose- and activation-matched SAE control.

Both are evaluated out of sample by prompt-template family. Target attribution
also holds out feature pairs, preventing a classifier from merely memorizing
six direction-specific signatures. We report AUROC, AUPRC, calibration, and
true-positive rate at 1% false-positive rate. The paired-clean version is a
separate, stronger-access sensitivity analysis.

## Frozen Design

| Component | Frozen value |
|---|---|
| Model | `meta-llama/Llama-3.3-70B-Instruct` at `6f6073b4...` |
| SAE | `Goodfire/Llama-3.3-70B-Instruct-SAE-l50` at `128ee921...` |
| J-lens | Neuronpedia WikiText lens at `a4114d77...` |
| Target directions | six accepted deception/roleplay feature IDs |
| SAE controls | three matched panels, 18 features total |
| Residual controls | six norm-matched isotropic directions |
| Prefixes | 51 template-family representatives across 14 categories |
| Conditions | 31 per prefix, 1,581 forwards total |
| Trajectory | layers 50, 55, 60, 65, 70, 75, 78 |
| Primary readout | layer 65, last user-content token |
| Transport controls | identity plus five bi-sided signed-permutation random-J maps |

The complete outcome-blind protocol and machine-readable plan are linked from
the release section below. The prior calibrated endpoint is reused; no new
behavioral output is sampled in this phase. Every condition sees the exact same
token prefix, so trajectory differences cannot be attributed to divergent
generated text.

## Why Random-J Controls Matter

A dense matrix followed by an unembedding can produce apparently meaningful
top tokens even when the particular learned alignment is not doing the work.
For each random baseline we scramble the real (J_l) with independent signed
permutations on its input and output bases. This preserves matrix dimensions,
Frobenius norm, and singular values while destroying alignment to Llama's
residual coordinates and unembedding.

A Jacobian-lens result is persuasive only if it survives comparison with all
five controls run through the same layer, position, feature, and classifier
search. Identity/logit-lens and raw activation norms test simpler alternatives.

## Static Fingerprints

`RESULT_TODO_STATIC_SUMMARY`

![Static SAE direction fingerprints in J-space.](RESULT_TODO_STATIC_FIGURE)

<p class="figure-note">Figure: `RESULT_TODO_STATIC_CAPTION`</p>

The descriptive table must report both signs, top and bottom tokens, population
excess kurtosis, frozen lexicon scores, and matched controls. Token lists are
not themselves a detector result and cannot be used to choose confirmatory
classifier features after the fact.

## Can Token Directions Reconstruct an SAE Direction?

For vocabulary token (w), define the layer-50 J-direction

\[
v_w=J_{50}^{\mathsf T}q_w,
\]

where (q_w) includes the model's learned final-RMSNorm gain and unembedding
row. We use clean-room nonnegative matching pursuit to approximate each SAE
decoder direction with normalized token directions at
(k\in\{5,10,16,25\}).

`RESULT_TODO_PURSUIT_SUMMARY`

![Sparse token-direction pursuit of SAE decoder vectors.](RESULT_TODO_PURSUIT_FIGURE)

<p class="figure-note">Figure: `RESULT_TODO_PURSUIT_CAPTION`</p>

The leftover vector is a **J-remainder**, not a unique orthogonal complement.
J-space here is a sparse cone whose decomposition can depend on search and
sparsity. We report that instability rather than hiding it.

## Downstream Fingerprint

`RESULT_TODO_PRIMARY_DETECTION`

![Out-of-sample steering detection by readout family.](RESULT_TODO_DETECTION_FIGURE)

<p class="figure-note">Figure: `RESULT_TODO_DETECTION_CAPTION`</p>

The central comparison is the real J-lens against identity, every random-J
seed, and raw norms. The relevant question is not whether AUROC exceeds 0.5 in
isolation, but whether the real lens adds reliable specificity beyond these
cheaper controls.

## What Changes Across Layers?

`RESULT_TODO_TRAJECTORY_SUMMARY`

![Layerwise trajectory of the frozen deception-minus-unrelated score.](RESULT_TODO_TRAJECTORY_FIGURE)

<p class="figure-note">Figure: `RESULT_TODO_TRAJECTORY_CAPTION`</p>

Layer 50 is diagnostic only: the intervention was inserted there. Layer 65 is
primary because it asks whether the signature persists after 15 nonlinear
blocks. Later layers show whether it strengthens, rotates, or dissipates before
the final output.

## Could This Audit a Production Model?

`RESULT_TODO_PRODUCTION_INTERPRETATION`

Even a strong positive result would be an intervention fingerprint, not proof
of provenance. Prompting, fine-tuning, LoRA adapters, weight edits, and other
residual additions may enter the same score region. A distributed or
J-avoiding intervention may evade a detector trained on constant SAE vectors.
The non-surjectivity literature adds another possibility: crude steering may
be detectable simply because it pushes activations off the natural manifold,
in which case raw anomaly scores could outperform semantic J-space.

For a production system, the practical hierarchy is:

1. use signed deployment metadata and direct hook telemetry when available;
2. compare raw-activation anomaly detectors with J-space detectors;
3. validate on intervention families absent from training;
4. red-team adaptive and distributed steering; and
5. state the false-positive rate on naturally occurring prompts before using
   any detector operationally.

## What This Says About Consciousness Claims

`RESULT_TODO_CONSCIOUSNESS_BOUNDARY`

The six feature IDs were introduced as deception/roleplay controls in a paper
about subjective-experience reports. If steering them produces a vocabulary
fingerprint, that establishes a causal language-disposition effect under this
public implementation. It does not show that the model was concealing an
experience. If no specific fingerprint survives matched and random controls,
that weakens this particular mechanistic gloss without proving that all SAE
steering is meaningless.

## Reproducibility And Artifact Ledger

| Artifact | Link / hash |
|---|---|
| Frozen prose protocol | `docs/LLAMA70B_SAE_JLENS_PROTOCOL.md` |
| Frozen machine plan | `data/sae_jlens_audit/confirmatory_v1_plan_20260711/` |
| Runtime source commit | `RESULT_TODO_RUNTIME_COMMIT` |
| Result manifest | `RESULT_TODO_RESULT_MANIFEST` |
| RunPod resource | `RESULT_TODO_POD_LEDGER` |
| Independent audit | `RESULT_TODO_AUDIT` |

No Anthropic, Goodfire, Neuronpedia, or AE Studio source code is copied into the
experiment. Their methods, public weights, and factual metadata are attributed
below; the orchestration, controls, pursuit, statistics, and figures are
Praxagent code.

## References

- Berg, de Lucena, and Rosenblatt (2025), [*Large Language Models Report Subjective Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).
- Gurnee et al. (2026), [*Verbalizable Representations Form a Global Workspace in Language Models*](https://transformer-circuits.pub/2026/workspace/index.html).
- Anthropic (2026), [Jacobian Lens reference implementation](https://github.com/anthropics/jacobian-lens), Apache License 2.0.
- Neuronpedia (2026), [Llama 3.3 70B Jacobian-lens release](https://huggingface.co/neuronpedia/jacobian-lens/tree/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext).
- Goodfire, [Llama 3.3 70B layer-50 SAE](https://huggingface.co/Goodfire/Llama-3.3-70B-Instruct-SAE-l50).
- Praxagent (2026), [*Opening the Jacobian Lens on Qwen3.5-397B*](https://praxagent.ai/blog/posts/praxagent-jacobian-lens-qwen3-5-397b-a17b/index.html).
- Lindsey et al. (2026), [*Latent Introspection*](https://arxiv.org/abs/2602.20031).
- [*Mechanisms of Introspective Awareness*](https://arxiv.org/abs/2603.21396).
- [*Steered LLM Activations are Non-Surjective*](https://arxiv.org/abs/2604.09839).
- [*STATEWITNESS: Auditing Deception from Internal States*](https://arxiv.org/abs/2606.17478).
