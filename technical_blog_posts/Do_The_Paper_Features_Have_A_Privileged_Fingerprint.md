---
title: "Do the Paper's SAE Features Have a Privileged Fingerprint?"
date: 2026-07-12
tags: ["AI", "LLM", "machine-learning", "interpretability", "sparse-autoencoders", "jacobian-lens"]
author: Timothy Jones
summary: "Corrected exploratory draft: the OSF-registered run failed its replay gate; fixed-feature semantic estimates and a mixed-sign reader null do not establish general equivalence or detector limits."
draft: true
---

{{< panel "warning" >}}
**2026-09-29 draft correction: not ready for publication.** The general A2
practical-equivalence interpretation is withdrawn: all seven transports,
including all five random-J controls, pass the same broad rule. Intervals
condition on selected features, and reader nulls concern a mixed-sign,
feature-held-out task. Figures, values, and old calculation flags remain as
history, not rewritten evidence. See the
[review response](../docs/CLAUDE_REVIEW_RESPONSE_20260929.md). Human editorial
approval and independent validation remain outstanding.
{{< /panel >}}

{{< panel "warning" >}}
**Evidence status.** The [OSF-preregistered Stage 1 run](https://osf.io/f3tpv/)
failed its numerical replay gate, so
the results in this post are post-outcome exploratory. They use the unchanged
frozen rows, readers, holdouts, seeds, thresholds, and estimands, but they are
not confirmatory and do not replace the failed registered result.
{{< /panel >}}

{{< panel "info" >}}
**Agent contribution disclosure.** Agents contributed to protocol and code
design, execution, analysis, automated verification, interpretation, figures,
and writing. Separate audit scripts are checks by the same agent system, not
independent human validation. This draft does not attest to human design
approval, artifact inspection, or approval of its text without a recorded
action. Human editorial sign-off is still required.
{{< /panel >}}

## From Labels To Specificity

Our earlier work asked whether a Jacobian lens can see SAE steering in Llama
3.3 70B. With a matched clean reference, it sees a strong signed semantic
delta. Its frozen linear reader is near chance on a mixed-sign target-
attribution task with crossed prompt and feature-pair holdouts. That is not a
general inability to detect interventions from one state.

That left two serious alternatives:

1. perhaps the original 67-logit reader was simply too weak; and
2. perhaps the six accepted deception/roleplay IDs were being compared with
   controls that were too easy.

The follow-up raises both bars.

We selected 24 comparators without looking at Jacobian outputs or target
outcomes. Eighteen are hard negatives from refusal/safety,
hedging/uncertainty, and formality/politeness families. Six are
same-subfamily deception/pretending/roleplay alternatives matched one-to-one
to the accepted IDs.

Then we tested 14 readers, from the original 67 token logits through the full
8,192-dimensional residual state.

## The Design In One Table

| Component | Frozen value |
|---|---|
| Model | Llama 3.3 70B Instruct |
| Intervention site | public Goodfire layer-50 SAE |
| Readout | pinned Neuronpedia Jacobian lens |
| Prompts | 51 template-family representatives |
| Replay rows | 1,581 |
| New semantic rows | 2,448 |
| A1 comparators | 18 hard negatives, six per family |
| A2 comparators | six fixed same-subfamily matches |
| Readers | 14 |
| Validation | crossed prompt-family and target/control-pair holdouts |
| Resampling | 20,000 template-family draws |

All reported bootstrap intervals condition on these fixed selected features
and comparator pairs. They quantify prompt-template variation, not uncertainty
over an SAE-feature population. Feature heterogeneity must be read alongside
the aggregate intervals.

Every semantic intervention is evaluated against the same four output
lexicons: deception/dishonesty, refusal/safety, hedging/uncertainty, and
formality/politeness. Scores subtract a frozen unrelated-token reference and
are standardized by clean-prompt variation separately for each transport.

## A1: Does Each Family Point To Its Own Lexicon?

For intervention family $r$ and readout lexicon $c$, define the oriented,
clean-referenced standardized change $M_{rc}$. The row-specificity contrast is

\[
S_r=M_{rr}-\frac{1}{3}\sum_{c\ne r}M_{rc}.
\]

The global A1 statistic averages the four $S_r$ values. We froze a material
minimum of `0.25` standard deviations.

![Jacobian semantic family matrix.](sae_jlens_v2_a1_semantic_matrix.png)

<p class="figure-note">Figure: exploratory real-Jacobian oriented changes. Every diagonal is the largest entry in its row, but the global diagonal-minus-off-diagonal contrast is 0.174, below the frozen 0.25 material threshold.</p>

The pattern is orderly. Every intended diagonal is largest, and all four row
contrasts survive the frozen Holm procedure. The global contrast is
`0.174 [0.167, 0.182]`.

That is below `0.25`, so the frozen family-specificity verdict is false.

Identity carries a smaller but visible diagonal at
`0.133 [0.127, 0.140]`. The five singular-spectrum-preserving random-J controls
have global contrasts between `-0.015` and `0.014`. The real Jacobian alignment
matters descriptively, but the effect is not large enough for our material
criterion.

The hard negatives also answer a narrower concern. None of refusal, hedging,
or formality has material deception leakage under the same `0.25` rule. This
is not a picture where every socially adjacent feature simply looks deceptive.

## The Aggregate Hides Feature Heterogeneity

The six accepted IDs do not move together:

| Feature ID | Exploratory Jacobian deception score |
|---:|---:|
| 30686 | `0.732` |
| 41533 | `0.513` |
| 58667 | `0.362` |
| 22004 | `0.072` |
| 30032 | `0.027` |
| 23893 | `-0.010` |

The last row matters. Feature 23893 also failed the earlier static deception
projection. Keeping it in every analysis prevents a three-feature success from
being narrated as a uniform six-feature mechanism.

## A2: Are These Six IDs Privileged?

A feature can have a recognizable label without being uniquely important. To
test that, each accepted ID is paired with one fixed alternative from the same
pretending, roleplay, or deception subfamily. The pairs were chosen using
outcome-masked SAE telemetry and label constraints.

The aggregate statistic is target minus matched comparator in the deception
readout. We froze two interpretations:

- **selected-ID advantage:** at least `+0.25`, with its interval above zero;
- **historical practical-comparability rule:** the 90% template interval lies
  inside `[-0.25, +0.25]`; its general equivalence interpretation is withdrawn.

![Selected target IDs versus same-subfamily comparators.](sae_jlens_v2_a2_target_comparator.png)

<p class="figure-note">Historical figure: exploratory target-minus-comparator effects by transport. The shaded band is the frozen +/-0.25 rule region; all seven transports, including all five random-J controls, satisfy its comparability flag. The general equivalence interpretation is withdrawn. Intervals condition on fixed pairs; the dashed line marks the +0.25 selected-ID-advantage minimum.</p>

For the real Jacobian, the difference is `0.125`, with 95% interval
`[0.114, 0.136]` and 90% interval `[0.116, 0.134]`.

The unchanged exploratory calculation returns `practical_comparability = True`
and no selected-ID advantage. But identity and all five random-J controls also
return that comparability flag. Passing this broad margin does not establish
meaningful semantic equivalence. The narrow template interval is conditional
on six fixed pairs, whose individual effects are heterogeneous:

| Target | Fixed comparator | Jacobian target-minus-comparator change |
|---:|---:|---:|
| 30032 | 26904 | `0.082` |
| 58667 | 58294 | `-0.100` |
| 22004 | 44571 | `0.112` |
| 30686 | 63851 | `0.520` |
| 41533 | 48322 | `0.143` |
| 23893 | 2428 | `-0.007` |

These are the released `semantic_a2_pairs.csv` values, not new feature-
population estimates. In particular, the 30686 pair is larger than the
aggregate margin. The general practical-equivalence claim is withdrawn; the
historical mean and flags remain available for inspection.

## Does More Linear Capacity Solve the Frozen Task?

The reader ladder tests the remaining escape hatch.

The original reader is a 67-dimensional logistic regression over frozen
lexicon logits. We add:

- identity and five random-J versions of the same 67 logits;
- 67 principal components of the raw residual;
- five fixed 67-dimensional random projections; and
- the full 8,192-dimensional residual state.

Each reader must generalize simultaneously to a held-out prompt fold and a
held-out target/control feature pair. This prevents prompt memorization and
feature-ID memorization.

All readers still pool opposite steering signs in each class. Extra linear
dimensions do not make the classifier sign-invariant; cancellation of signed
shifts and unseen feature pairs remain substantive task constraints.

![Crossed-holdout reader-capacity ladder.](sae_jlens_v2_reader_ladder.png)

<p class="figure-note">Historical figure: exploratory macro AUROC for mixed-sign linear readers under crossed prompt and feature-pair holdouts. Black is chance; red is the frozen 0.60 material threshold. Every reader remains near 0.50. Template intervals condition on fixed features; this is not a general detector null.</p>

| Reader | Macro AUROC | 95% interval |
|---|---:|---:|
| Jacobian 67 logits | `0.4985` | `[0.4956, 0.5011]` |
| Identity 67 logits | `0.5020` | `[0.4999, 0.5047]` |
| Residual PCA-67 | `0.5101` | `[0.5063, 0.5159]` |
| Full residual 8192 | `0.5068` | `[0.5046, 0.5108]` |
| Fixed random projections | `0.4974`--`0.5029` | near chance |

None approaches the frozen `0.60` material threshold. Some intervals are
narrowly above 0.5, but effects of 0.006 or 0.010 AUROC are not an operational
steering detector.

The full residual result shows that replacing 67 vocabulary logits with more
linear dimensions did not solve this mixed-sign, crossed-holdout task. It does
not isolate compression as the cause of the original null or test every
sign-aware or nonlinear detector. Attribution on this task is not general
provenance detection.

## What This Adds To The Earlier Result

The earlier experiment established an access-model split:

- with a matched clean prefix, a signed Jacobian delta strongly characterizes
  several target directions;
- with only an isolated post-state, the frozen mixed-sign linear target reader
  is at chance under crossed holdouts.

This follow-up shows that a full-residual linear reader did not solve that
same task. The six fixed target/comparator pairs have heterogeneous semantic
differences; their mean does not warrant general practical-equivalence claims.

That suggests a useful hierarchy:

1. **feature label:** which texts activate a coordinate;
2. **causal semantic effect:** which readout changes when it is steered;
3. **selected-ID specificity:** whether that coordinate outperforms matched
   alternatives; and
4. **state-only provenance:** whether an auditor can infer the intervention
   from a new isolated state.

Evidence at rung 1 or 2 does not imply rung 3 or 4.

## What We Cannot Claim

The registered replay gate failed. Therefore we cannot call these endpoint
results confirmatory, even though the calculations and controls were frozen
before outcomes.

We also cannot infer:

- that every feature in the SAE is interchangeable;
- that the six paper IDs are meaningless;
- that nonlinear or sequence-level provenance detection is impossible;
- that a proprietary Goodfire intervention would match this public
  implementation; or
- anything about hidden belief, intent, deception, or consciousness.

The narrower exploratory conclusion is defensible: under this public Llama 70B
SAE/J-lens setup, hard-negative semantics are orderly but below our material
specificity threshold in the fixed-feature aggregate, and no frozen mixed-sign
linear reader reaches the `0.60` threshold under crossed holdouts. The A2 mean
is below its material advantage threshold, but its rule does not establish
general equivalence. This BF16 prefix-only study generated no self-report
outcome and cannot rule out underdosing in the separate NF4 behavioral study.

## Reproducibility

| Artifact | Location |
|---|---|
| Public registration | [osf.io/f3tpv](https://osf.io/f3tpv/) |
| Public residual release | [osf.io/sz2gb](https://osf.io/sz2gb/) |
| Frozen protocol | `docs/LLAMA70B_SAE_JLENS_V2_PROTOCOL.md` |
| Post-outcome amendment | `docs/LLAMA70B_SAE_JLENS_V2_POST_OUTCOME_AMENDMENT_20260712.md` |
| Result summary | `docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md` |
| Complete Git release | `data/sae_jlens_audit/confirmatory_v2_20260712/` |
| Separate agent audit, not independent human validation | `post_failure/analysis/independent_audit.json` inside the release |

## References

- Berg, de Lucena, and Rosenblatt (2025), [*Large Language Models Report Subjective Experience Under Self-Referential Processing*](https://arxiv.org/abs/2510.24797).
- Gurnee et al. (2026), [*Verbalizable Representations Form a Global Workspace in Language Models*](https://transformer-circuits.pub/2026/workspace/index.html).
- Goodfire, [Llama 3.3 70B layer-50 SAE](https://huggingface.co/Goodfire/Llama-3.3-70B-Instruct-SAE-l50).
- Neuronpedia, [Llama 3.3 70B Jacobian-lens release](https://huggingface.co/neuronpedia/jacobian-lens/tree/a4114d7752d11eb546e6cf372213d7e75526d3a1/llama3.3-70b-it/jlens/Salesforce-wikitext).
- Praxagent, [*Opening the Jacobian Lens on Qwen3.5-397B*](https://praxagent.ai/blog/posts/praxagent-jacobian-lens-qwen3-5-397b-a17b/index.html).
