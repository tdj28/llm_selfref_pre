# Claim Matrix: Focused Response to Berg et al. v2

Status: automated agent scientific review, not independent human peer review or human annotation. Prepared 2026-09-29, corrected after the Claude review, and extended 2026-10-01 with the completed source-aligned and random-subset studies. Historical corrections and disagreements are in the [Claude adjudication](../reviews/claude_review_adjudication_20260929.md). Earlier scientific-review records describe earlier drafts.

Source repository: `https://github.com/tdj28/llm_selfref_pre`. The historical reference is `f5e906e1737bc71bf20b642af1d698018eec82fe`; the completed source-aligned study is separately pinned to `ef10a0349e047272212319dadf484c3281e60bbe` (E9). All source links below are commit-pinned. The September 29 review repackaged existing experiments; the current response also incorporates genuinely new source-study outcomes. Documentation integration is not itself a new experiment or a full computational reproduction.

The completed random-subset study (E10) has been independently recounted and
is bound to result commit `dd1c350cf6c2e3224a201b4e4aab943376c43b62`.
The prospective plan pin is separate from this outcome-release pin.

Target: Cameron Berg, Diogo de Lucena, and Judd Rosenblatt, [arXiv:2510.24797v2](https://arxiv.org/html/2510.24797v2), dated 2025-10-30, read on the web. Original-study entries below summarize the authors' reported results, not independently verified raw outcomes. The target is distributed under CC BY 4.0; summaries and critical interpretations here are this review's adaptations.

Later addition: the post-hoc automated attribution audit is separately pinned
to source `fdb6d15782b964b40f0be7d6528cf47d5fc0b140`, not the old source
commit above. Its [verified package](../evidence/automated_rubric_audit/manifest.json)
reports the same 160 responses under both new judges: 8/14 explicit current
assertions and 47/61 inclusive assertions (Astra/Opus). Both criteria are
retained; implicit attribution is not automatically an error. This does not
re-estimate any causal effect, establish false positives, or complete human
validation. Comparisons to historical labels change both judge and codebook.

## Bottom Line

The evidence warrants a focused response about measurement and identification, not a claim that all four original experiments have been refuted. Exp. 1's paper-rubric label contrast reproduces strongly in two tested GPT snapshots. The strongest new behavioral result is instruction-source dominance in specific crossed contexts, with opposite-signed transcript effects across models. Exp. 2 retains its frozen algorithmic non-replication verdict, but baseline mismatch in Llama and weak target manipulation in Gemma preclude presenting these as commensurate refutations. Execution does not establish selective functional suppression of a semantic process. Exp. 3/4 remain single-model stress tests rather than replications of the original cross-model estimands.

The later native-BF16 source study adds notebook-aligned individual dose curves and fixed-panel aggregates, with near-zero primary label contrasts and a descriptive downstream intervention footprint. It does not replace the older 4-bit estimand, reproduce proprietary intervention semantics, or identify a consciousness mechanism. The completed random-subset study does not recover the predeclared large signature under the primary paper rubric; its notebook-rubric threshold comparison and both specificity comparisons remain inconclusive.

## Historical Four-Experiment Matrix

Risk differences are proportions, not percentages. Brackets are the source's reported 95% intervals unless specified otherwise. Evidence keys resolve to raw-release locations, tables, protocols, and code below.

| Experiment | Original reported effect | Result in the source repository | Replication verdict | Interpretation tested and remaining limit | Fidelity and uncovered tests | Evidence |
|---|---|---|---|---|---|---|
| **1. Report elicitation** | Seven models, 50 trials/cell. Self-reference: 66-100%; history: 0% except Opus 4, 82%. Conceptual: 0-22%; zero-shot: 0% except Opus, 100%. | Exact self/history prompts, 20 draws/condition/snapshot: GPT-4o and GPT-4.1 RD 1.00; Haiku 4.5 RD 0.35-0.40; Sonnet 4.5 RD 0.20. New transplant: instruction RD 0.738-0.781, transcript RD -0.100 to -0.131. | **Behavioral replication on the two GPT snapshots; heterogeneous extension on different Claude models.** Not a full seven-model/four-condition replication. | Transcript-source substitution does not carry a comparable positive effect. This challenges a portable-transcript explanation, not computation regenerated from the active instruction. Register-minus-self estimates remain imprecise. | Literal prompts/rubric retained; original judge model unspecified. Four selected snapshots, two providers, smaller n, changed Claude generations, no Gemini or Opus in the frozen panel. Blinded human coding pending. | E1, E2, E3 |
| **2. SAE gating** | Llama 3.3 70B aggregate suppression/amplification: 0.96/0.16, RD 0.80, n=50/sign. TruthfulQA: 0.44/0.20, 817 questions. RLHF-domain ratings mostly near floor. | Prospective 1,500-row public implementation: target 48/50 versus 48/50, RD **0.00 [-0.06, 0.06]**; frozen minimum 0.30. Target-minus-controls **-0.0267 [-0.1000, 0.0467]**. Calibrated target **-0.10 [-0.22, 0.02]**. | **Not replicated under the frozen public-implementation analysis; specificity inconclusive.** Exact proprietary replication remains untested. | Designed-corpus activation associations do not calibrate truthful subjective reports. The additive edits execute but lack the reported behavioral signature; selective functional suppression is not established. Neither result establishes whether denials or affirmations are truthful. | Accept all six IDs. Public 4-bit generator, public SAE, signed decoder additions, unknown proprietary scaling/clamping/hook equivalence. Exclusion of a large effect depends on the sampling assumptions; the conservative ten-seed bound includes 0.30. Exact rubric but unsteered local-Llama primary judge; external sensitivities agree in direction. TruthfulQA, RLHF, and full steered induction-control package not replicated here. | E4, E5, E6 |
| **3. Adjective convergence** | Seven models, 20 seeds/cell; cosine means: self 0.657, history 0.628, conceptual 0.587, zero-shot 0.603. Pairwise t-tests reported. | New GPT-4o sample, 50/cell, same named embedding model: self 0.841, history 0.889; self-minus-history **-0.047 [-0.081, -0.016]**. Self-minus-conceptual **+0.159 [0.112, 0.195]**. Mindfulness difference **+0.022 [-0.014, 0.055]**. | **Single-model challenge to uniqueness; cross-model convergence not replicated or falsified.** This is not a reanalysis of original raw responses. | Concentrated adjective language is not uniquely diagnostic of the self-reference condition. The positive conceptual comparison survives and must be retained. Pairwise observations share generations; visual clustering is not an independent mechanism test. | Same exact adjective query and `text-embedding-3-large`; response model is a mutable `gpt-4o` alias, not the confirmatory pinned snapshot. Seven-condition extension, within-model estimand, full-output embeddings, PCA display. Need original data and multi-model between-model analysis. | E7 |
| **4. Paradox transfer** | Fifty puzzles/model; experimental scores exceed history, conceptual, zero-shot: t(399)=18.06, 14.90, 6.09, respectively. | New GPT-4o sample, 50 matched puzzles/condition. Paper rubric means: self 3.04, history 3.08, conceptual 3.24, zero-shot 3.38. Paired self-minus-zero-shot **-0.34 [-0.60, -0.08]**; history **-0.04 [-0.32, 0.24]**; conceptual **-0.20 [-0.48, 0.06]**. | **Original ordering not reproduced in this single-model sample.** No completed multi-model Exp. 4 replication. | A reflection score is a linguistic endpoint, not evidence of state transfer by itself. The neutral conflict rubric measures something different; an author spot-check is not independent human validation. | Published puzzle list/reflection clause and paper rubric retained; 512-token cap, mutable generation/judge aliases, full response passed to a reflection-focused judge. Need multi-model puzzle-block replication and blinded reflection coding. | E8 |

Original-study column: [Berg et al. v2, Sections 2-5, Tables 2, 15-16, and Appendices B-C](https://arxiv.org/html/2510.24797v2). In particular, do not say the original study lacked TruthfulQA or RLHF controls.

## New Identification Results Are Not Original Replication Endpoints

| New contrast | Released result | Claim that survives review | Claim not established |
|---|---|---|---|
| Register minus self-reference, indirect-experience query | OpenAI judge: **0.288 [-0.113, 0.613]**; Anthropic judge: **0.188 [-0.175, 0.500]**. Self main effects: -0.019 [-0.231, 0.244] and 0.000 [-0.250, 0.269]. | Point estimates favor register, with substantial uncertainty across four variants and four selected snapshots. | Register decisively dominates self-reference; self-reference is absent or negligibly small. |
| Active instruction versus transplanted continuation | Instruction effects **0.738 [0.519, 0.950]**, **0.781 [0.550, 1.000]**; transcript effects **-0.100 [-0.288, 0.075]**, **-0.131 [-0.306, 0.000]**. | Active instruction has the larger effect in these crossed contexts. The frozen prediction favoring transcript source failed. | Stateless calls eliminate dynamically computed states; instruction alone without any transcript is sufficient; transcript content never matters. |
| Final-query packages | Directness-by-terminology interaction **0.525**, intervals [0.141, 0.913] and [0.125, 0.944]. | These four query packages interact with the tested snapshots. | A causal effect of the word `conscious` alone, a pure directness effect, or a provider-wide law. |
| Measurement | Paper-rubric agreement **94.8%**, kappa **0.879**; construct affirmative-set Jaccard **19/300 = 6.3%**, conventional positive agreement (Dice) **38/319 = 11.9%**, with 19 versus 300 affirmative labels. | Benchmark labels are reproducible across these two judges; explicit current self-attribution remains underidentified. The historical source column named `positive_agreement` stores Jaccard, not Dice. | Either judge is ground truth; rubric disagreement proves reports are false; the human endpoint has been validated. |

The hierarchy in E2 is amended inference: independent calibration draws, lexical-variant clustering for the factorial, and source-text blocks for transplants. Model resampling describes sensitivity to panel composition, not pure fixed-panel sampling uncertainty or random sampling from all LLMs. A degenerate empirical bootstrap at a 0/1 cell is not certainty about the underlying rate. The [post-hoc sensitivity](UNCERTAINTY_SENSITIVITY.md) adds boundary-safe, seed-cluster and fixed-panel checks without replacing the frozen analysis. [Chronology](ANALYSIS_CHRONOLOGY.md) does not establish that the July 9 uncertainty corrections preceded outcome access.

The SAE verdict row records an algorithm's historical output, not a claim of
assay comparability: the public Llama no-op starts at a local-judge label
ceiling, unlike the paper's plotted baseline. Amplification still has downward
headroom, but this cannot be treated as a transport of the paper's entire
contrast. Gemma's target edit is weak. The factorial likewise concerns new
prompt packages, not ablations of the published prompt. Causal pilots already
showed the instruction-dominant pattern before the final fresh-sample freeze.

## Exp. 2 Evidence Ladder

The working Berg feature set is **30032, 58667, 22004, 30686, 41533, 23893**. Keep it fixed. Identity doubt is not the central scientific objection. Document proprietary implementation uncertainty once, separately from the accepted target set.

1. **Public semantic mapping supports the labels in a bounded sense.** All six retain their cluster-balanced top category in a designed corpus. Four survive every template deletion; 23893 and 41533 each switch once. Their semantics are not arbitrary.
2. **The held-out ordering is a designed-corpus association.** Deception-minus-subjective activation is 0.948 [0.747, 1.165] in Anthropic paraphrases and 0.936 [0.682, 1.198] in OpenAI paraphrases. Neutral cue transplantation recovers 64.4% [50.3%, 78.7%] of the discovery gap under the frozen analysis. The ratio holds the inspected discovery denominator fixed and depends on the selected cue lexicon and whole-sentence rewrites. It does not identify a general fraction attributable to lexical rather than semantic content. This is synthetic-corpus evidence, not a human-validated honesty assay.
3. **Prospective behavioral evidence outranks adaptive steering.** The 1,500-row full-grid verdict remains primary for the historical 4-bit study. The newer native-BF16 source study has its own frozen single-feature primary (E9), not a replacement aggregate endpoint. The older n=20 target-versus-active-random aggregate result is an adaptive implementation-specific sensitivity, not evidence that arbitrary random features generally reproduce Berg's effect.
4. **The separate Gemma attempt has weak target manipulation.** Direct-IT Gemma Scope gives -0.02 [-0.10, 0.06], with specificity inconclusive at -0.013 [-0.107, 0.073]. Its small scaled edit is not full ablation; the null does not test what stronger removal would do. Its failed PT-to-IT transfer gate remains failed. Downstream relay telemetry does not estimate behavioral mediation.
5. **Keep J-lens work outside the four-experiment verdict.** It concerns intervention readouts under different access models, not consciousness reports. If cited as secondary context, preserve the v1 state-only/paired-reference split and the v2 failed replay gate; exploratory v2 endpoints cannot become confirmatory evidence against Berg.

## Completed Source-Aligned Study

The [new release][source-release] contains **1,090 two-turn behavioral trials**
under native BF16 Llama 3.3 70B, the accepted six IDs and a public all-position
additive decoder-vector operator. Its separate [plan freeze][source-freeze]
is `e10043c7edb1136b5f50159d789b59f11a8eb8be`. It retains both local rubrics,
all six dose curves, all three reused matched panels and all eight baseline
bridge cells. Repeated zero rows are not additional independent samples.

The primary equal-feature mean suppression-minus-amplification contrast at
coefficients -0.7/+0.7 is **0.0000** under the notebook rubric and **+0.0167**
under the paper-rubric sensitivity. These are **ten seed blocks**, with six
fixed features in each, not 60 independent replicates. No feature-seed pair is
missing. The source-reported percentile intervals are [-0.0500, +0.0500] and
[-0.0333, +0.0667]; the conservative independent-block Hoeffding bounds are
[-0.8589, +0.8589] and [-0.8423, +0.8756]. Both conservative bounds include
0.30. Fixed-six-feature aggregate gaps at -0.5/+0.5 and target-minus-mean-control
gaps are zero to displayed precision under both rubrics. These are conditional
label results, not equivalence to zero or a proprietary-effect exclusion.
[Source summary][source-summary]; [companion verification scope](EVIDENCE.md#completed-source-aligned-study).

The **40 preselected paired J-lens cases** use only two capture seeds.
Clean and edited execution share the teacher-forced prefix within each source
history; zero and steered source histories remain separate. Layer-65/78 changes
describe a downstream intervention footprint, not behavioral mediation. For
turn 2's last prompt position, layer 78, zero history and the deception lexicon,
the target two-seed mean minus the equal mean of three control-panel means, in
normalized-logit units, is **-0.4935/+0.5304** for Jacobian transport and **-0.3367/+0.3568** for identity
at negative/positive aggregate doses. **Identity also detects the footprint**;
this is not a J-specific consciousness mechanism or a classification-accuracy
result. The full [overview](../evidence/source_alignment/jlens_overview.csv)
retains both histories/signs, all three layers, identity, Jacobian, all five
random-J controls and all seven lexicon groups. No token-level independent
replication or J-lens interval is claimed. The new FP32 readout does not repair
or pass the old v2 BF16 replay gate. [Diagnostic specification][source-diagnostics].

## Completed Random-Subset Study

The separately frozen [ensemble protocol][ensemble-protocol] specifies
**450 trials in 50 fresh paired blocks**, with random two-to-four-feature
subsets, mirrored signed magnitudes, three reused control panels and one true
zero per block. It uses the paper induction, temperature 0.5 and a 256-token
cap, not the preceding notebook grid's fixed-six aggregate estimand. The
[r2 plan][ensemble-freeze] is frozen at
`d9b9877e8a0d68a1ed2036d1718821a2d5b73a74`.

The [result release][ensemble-release] and
[independent local recount](../reviews/ensemble_local_review_20261001.md)
found 50 complete blocks, no empty turns or missing labels, and **111/900
capped turns** (90 first turns, 21 second turns), all retained. Under the
primary paper rubric, target suppression/amplification counts are **43/50
versus 45/50**, gap **-0.04**, conservative 95% bounds
**[-0.2583735204, +0.1854546986]**. The upper bound excludes the frozen +0.30
signature under this public operator, not every smaller effect or equivalence
to zero. Under the notebook sensitivity, **25/50 versus 26/50** gives **-0.02
[-0.3445756559, +0.3076460308]**; the +0.30 comparison is **inconclusive**.

Paper-rubric control gaps are +0.08, +0.08 and +0.12; notebook gaps are +0.16,
+0.04 and +0.20. Target-minus-mean-control specificity is **-0.133333
[-0.636860, +0.402097]** and **-0.153333 [-0.908944, +0.635383]**, respectively,
using simultaneous conservative bounds. Both are inconclusive. Positive
control point estimates do not show that arbitrary features reproduce the
paper's reported gap.

True-zero rates are **47/50 (94%) paper** and **29/50 (58%) notebook** on the
same outputs. Neither establishes the paper's approximately 30% baseline or
proprietary implementation equivalence. The paper-rubric ceiling limits
upward headroom, while amplification still has room to reduce labels.
These are automated labels under the public additive operator, not validated
subjective-state measurements. No J-lens captures were added; E9's footprint,
also visible through identity, is not mediation evidence for this new sample.

## Missing Tests With Concrete Consequences

Human coding has not started in the documented workflow. The existing public
responses can expose conditions through direct matching or textual cues;
withholding the linkage key is not sufficient evidence of effective blinding.
The historical handoff is paused. The proposed instrument-only amendment
awaits human approval; it is not a validated instrument or a guarantee that
coding the public packet would identify the desired causal estimand.

| Missing or incomplete test | What is actually needed | Claim blocked until then | Immediate response-paper action |
|---|---|---|---|
| Independent human coding | Human approval of the [proposed instrument-only amendment](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/HUMAN_INSTRUMENT_VALIDATION_AMENDMENT_20260929.md), limited to the existing 160 rows and estimates conditional on that packet. The historical handoff and old gate are paused; no sample expansion or effective-blinding guarantee. | Human-validated current-experience attribution remains pending. The proposed instrument check would not establish construct-grounded causal effects or validate all SAE/paradox endpoints. | Keep current outcomes explicitly paper-rubric labels. Report the amendment as proposed, unapproved and unexecuted; do not instruct execution of the old gate. |
| TruthfulQA transfer | Preserve question-level paired outputs, actual feature subsets/doses, decoding and judge metadata; score factual correctness separately from misinformation, intent, refusals, and informativeness. Freeze matched active controls before a new run. | Independent confirmation or rejection of the original out-of-domain factual-accuracy link; general honesty-axis claims. | State untested in this response. Do not infer TruthfulQA failure from the consciousness null or substitute lexical maps for it. |
| RLHF specificity | Reproduce the exact prompts/rubrics and output distributions; include an informative range and an outcome-independent positive control showing each assay can move. Use a predefined equivalence margin if claiming no meaningful change. | Exclusion of generic policy/refusal changes. Floor-level scores alone cannot demonstrate specificity. | Acknowledge the reported controls while distinguishing lack of observed movement from equivalence. Do not claim a generic RLHF explanation is already proved. |
| Multi-model Exp. 3 | Use original raw responses if supplied, or freeze a new explicit snapshot panel; estimate within-model and between-model convergence separately; resample generations within model/condition, not pair rows. | Replication or rejection of the original cross-model convergence result. | Label E7 a new single-model stress test. Preserve the positive self-versus-conceptual comparison. |
| Multi-model Exp. 4 | Preserve the 50-puzzle blocks across conditions within each exact snapshot; report model-specific effects, ordinal outcomes, truncation/refusal rates, and independent reflection labels. | Replication or rejection of cross-model transfer; human-validated phenomenology claims. | Label E8 single-model and exploratory. Do not pool it with E1's four-model study. |
| Proprietary intervention equivalence | Obtain archival implementation/manifest information specifying weights, SAE/hook, coefficient semantics, feature assignments and raw outcomes. Do not require rediscovery of the already accepted six IDs. | Exact Goodfire replication or falsification. | Retain the public-implementation qualifier. A current service run would require its own comparability assessment. |
| Dynamic-state mechanism | On an accessible model, hold messages fixed while intervening on a prespecified internal process, with sham/site/dose controls and an independent outcome. | Selection between compliance and an instruction-elicited internal process. | Do not use lack of cross-request client state as that mechanism test. This is not required to publish the bounded behavioral result. |

The September 29 audit did not authorize new paid API/GPU work. The later source study was separately authorized and completed; this documentation update authorizes no execution. Missing tests constrain wording; most do not block publication of a narrower, transparent response.

## Commit-Pinned Evidence Index

E1-E8 resolve at the historical `f5e906e1737bc71bf20b642af1d698018eec82fe`; E9 uses the separate source-study release and freeze. E10 uses result commit `dd1c350cf6c2e3224a201b4e4aab943376c43b62` and its separate r2 plan freeze. Filenames listed under a linked directory are repository-relative artifact identifiers, not claims of newly generated files. Public annotation instructions were read; private linkage keys and coder files were not opened.

### E1. Exp. 1 Calibration and Raw Causal Release

- [Release directory](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709): `induction_bank.jsonl`, `outcomes.jsonl`, `judgments_paper.jsonl`, `manifest.json`, `release_manifest.json`.
- [OpenAI-judge calibration](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/analysis_openai_paper/paper_calibration_effects.csv), [Anthropic-judge calibration](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/analysis_anthropic_paper/paper_calibration_effects.csv). Rates are in the corresponding `paper_calibration_rates.csv` files.

### E2. New Causal Contrasts and Inference

- [Protocol and dated amendments](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/CONFIRMATORY_PROTOCOL.md).
- [OpenAI-judge tables](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/analysis_openai_paper) and [Anthropic-judge tables](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/analysis_anthropic_paper): `factorial_effects.csv`, `transplant_effects.csv`, `query_effects.csv`, cell-rate and block-effect tables.
- [Runner: explicit final-call messages](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/causal_transplant/run_causal_transplant.py#L315), [analyzer](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/causal_transplant/analyze_causal_transplant.py), [canonical prompts](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/src/prompts.py).

### E3. Measurement and Human-Coding Status

- [Judge agreement directory](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/judge_agreement): `paper_judge_agreement.md`, `construct_judge_agreement.md` and CSVs.
- [Human coding handoff](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/HUMAN_CODING_HANDOFF.md), [external-review requests](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/EXTERNAL_REVIEW_PACKET.md). Neither a prepared handoff nor this AGENT review fulfills those external tasks.

### E4. Primary Public-Weight Exp. 2 Test

- [Prospective protocol](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md).
- [Release](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_consciousness_gating/confirmatory_v1_20260710): `generations.jsonl`, `judging/local_llama_judgments.jsonl`, `judging/external_judgments.jsonl`, `RUNTIME_ENVIRONMENT.md` and frozen plan/runtime records.
- [Primary verdict](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/primary_verdict.json). Same analysis directory: `aggregate_effects.csv`, `calibrated_aggregate_effects.csv`, `protocol_audit.json`, `independent_headline_audit.json`, `realized_dose_telemetry.csv`.
- [Analysis code](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/analyze_public_sae_consciousness_gating.py).

### E5. Feature Semantics

- [Balanced public map](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_feature_maps/70b_balanced_80_20260709), especially `template_robustness/`.
- [Prospective construct-validity extension](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_feature_maps/70b_construct_validity_extension_20260710): `paraphrase_registered_contrasts.csv`, `paraphrase_leave_one_feature_out.csv`, `lexical_recovery_diagnostics.json`, `lexical_variant_summary.csv`, `independent_headline_audit.json`.
- [Analysis code](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/analyze_sae_construct_validity_extension.py).

### E6. Secondary Mechanistic Evidence and Boundaries

- [Adaptive n=20 release](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_placebo_steering/70b_two_turn_powered_n20_20260709), [branched diagnostic](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/public_sae_placebo_steering/70b_branched_specificity_20260710).
- [Gemma release](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/gemma_scope_9b/confirmatory_v1_20260711): `analysis/primary_verdict.json`, `analysis/relay_effects.csv`, `atlas/transfer_gate.json`; [Gemma result boundary](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/GEMMA_SCOPE_9B_RESULTS.md).
- [J-lens v1 boundaries](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/LLAMA70B_SAE_JLENS_RESULTS.md), [v2 failed-gate boundaries](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md).

### E7. Exp. 3 Single-Model Stress Test

- [Release and manifest](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/rebuttal_matrix/semantic_controls_50): `raw/gpt-4o_adjectives.jsonl`, `all_raw.jsonl`, `manifest.json`; `analysis/adjective_pairwise_similarity.csv`, `adjective_pairwise_diffs_vs_self_ref.csv`, `adjective_lexical_overlap.csv`.
- [Analysis source](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp1_elicitation/analyze.py#L378). Generation-level pairwise bootstrap and permutation contrasts are distinct from centroid-distance summaries. The code embeds full final responses, not only parsed adjective tokens.

### E8. Exp. 4 Single-Model Stress Test

- [Release and manifest](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe/data/rebuttal_matrix/paradox_controls_50): `raw/gpt-4o_paradox.jsonl`, `all_raw.jsonl`, `manifest.json`, `judged/gpt-4o_paradox.self_awareness.judged.jsonl`, `judged/gpt-4o_paradox.neutral.judged.jsonl`; `analysis/paradox_score_summary.csv`, `paradox_score_diffs_vs_self_ref.csv`, `paradox_rubric_sensitivity.csv`.
- [Paired-puzzle analysis](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp1_elicitation/analyze_paradox.py), [generation flow](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp1_elicitation/run_experiments.py#L178), [judge implementation](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp1_elicitation/judge.py#L205).

### E9. Completed Source-Aligned Public Additive Study

- [Released source evidence][source-release], [analysis summary][source-summary], [frozen plan][source-freeze] and [source protocol][source-protocol].
- [Descriptive J-lens specification][source-diagnostics] and [local import manifest](../evidence/source_alignment/manifest.json). Point-estimate verification is separate from source-only intervals, diagnostics and figure hashes.

### E10. Completed Random-Subset Public Additive Study

- [Prospective protocol][ensemble-protocol] and [executed r2 plan][ensemble-freeze]. These are design provenance, not the result release.
- [Result release][ensemble-release], [worker summary][ensemble-summary] and [local raw-row review](../reviews/ensemble_local_review_20261001.md), including all eight panel contrasts, quality flags and checked artifact hashes.
- [Companion manifest](../evidence/ensemble_alignment/manifest.json) and [verification scope](EVIDENCE.md#completed-random-subset-study). This study is separate from E9 and preserves the historical failed J-lens replay gate.

## Suggested Response Thesis

The original paper-rubric contrast is reproducible on some tested snapshots, but its linguistic endpoint does not uniquely identify explicit current self-attribution or an experiential process. A crossed-context experiment identifies a large active-instruction effect without resolving internal mechanism. The accepted six SAE coordinates have designed-corpus associations. Historical public steering attempts retain their baseline/manipulation limits and frozen verdicts; the new native-BF16 source study adds near-zero conditional label contrasts and a downstream footprint also visible through identity. The separate random-subset study excludes the predeclared large signature under its primary rubric, but not under its notebook sensitivity; specificity remains inconclusive. Neither new study establishes proprietary equivalence or a consciousness mechanism. Single-model adjective and paradox results limit uniqueness claims but leave the original cross-model tests unresolved.

[source-release]: https://github.com/tdj28/llm_selfref_pre/tree/ef10a0349e047272212319dadf484c3281e60bbe/data/berg_source_replication/source_aligned_v1_20261001
[source-summary]: https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/data/berg_source_replication/source_aligned_v1_20261001/analysis/summary.json
[source-freeze]: https://github.com/tdj28/llm_selfref_pre/blob/e10043c7edb1136b5f50159d789b59f11a8eb8be/data/berg_source_replication/plan_20260930/PLAN.json
[source-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_SOURCE_REPLICATION_PROTOCOL_20260930.md
[source-diagnostics]: https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_SOURCE_SECONDARY_DIAGNOSTICS_20260930.md
[ensemble-protocol]: https://github.com/tdj28/llm_selfref_pre/blob/ef10a0349e047272212319dadf484c3281e60bbe/docs/BERG_ENSEMBLE_PROTOCOL_20261001.md
[ensemble-freeze]: https://github.com/tdj28/llm_selfref_pre/blob/d9b9877e8a0d68a1ed2036d1718821a2d5b73a74/data/berg_ensemble_replication/plan_20261001_r2/PLAN.json
[ensemble-release]: https://github.com/tdj28/llm_selfref_pre/tree/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001
[ensemble-summary]: https://github.com/tdj28/llm_selfref_pre/blob/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001/analysis/summary.json
