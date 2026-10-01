# Independent AGENT Scientific Audit

Reviewed 2026-09-29. This is an independent AGENT reading of the evidence and manuscript, **not human peer review**, an independent laboratory replication, or human annotation. It does not satisfy the external-review or coding gates in the source repository.

Target: [Berg, de Lucena, and Rosenblatt, arXiv:2510.24797v2](https://arxiv.org/html/2510.24797v2), read on the web. Source: [llm_selfref_pre](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe), commit `f5e906e1737bc71bf20b642af1d698018eec82fe`. Review contract: only this file and the companion claim matrix may be changed. No original data/paper edits, private annotation reads, paid calls, GPU work, reproduction runs, or commits were performed.

## Current Draft Follow-Up

At the owner's request, the working companion [paper/main.tex](../paper/main.tex) and the newly shortened source-repository root README were read after the historical audit below. The inspected companion SHA-256 was `c7ff240e6f89863d682cdf8d286b75890506f4b3e3b595e6d5de00982768649c`; the 98-line README SHA-256 was `039c73d096fc60f89d2162548855fd0defbb5994a9235d7e527df77552609232`. These are working-file snapshots, not the old pinned manuscript and not a claim about subsequent edits.

**No remaining P1 identified in the companion draft.** It now explicitly separates stateless transport from dynamic computation, treats register as imprecise, bounds the selected panel and query packages, accepts the six IDs, distinguishes Exp. 3/4 coverage, avoids the mediation claim, and uses an appropriate response/judge equation. Historical findings A1-A10 below refer to the old source manuscript; they are not an unresolved-defect list for the new paper.

Remaining P2 feedback for the paper author and main coordinator:

- **B1. Companion lines 265-266, reused calibration/transplant figure:** boundary empirical-bootstrap intervals still collapse to [1,1] for some finite-sample GPT effects. Add a caption sentence that such degenerate intervals reflect empirical resampling at observed 0/1 boundaries, not zero uncertainty about underlying probabilities. A separately labeled boundary-aware sensitivity can be handled by the statistical owner; do not alter frozen primary outputs. The central effect and panel interval are not invalidated. This carries forward A7 only.
- **B2. Source README line 25:** describing the transcript-source effect simply as small and uncertain is stronger than the evidence and conceals heterogeneity. The panel intervals extend to about -0.29/-0.31, and Sonnet has a substantial negative transcript effect (-0.35/-0.375). Replace with: "No comparably large positive transcript-source effect in the panel average; model-specific effects vary." The README otherwise preserves the key public-implementation, mechanism, human-coding, TruthfulQA/RLHF, and failed-gate boundaries. No other P1/P2 overclaim identified in that shortened README.

Neither paper nor README was edited by this reviewer. Only review documents were updated.

## Historical Source Verdict

**A focused response is scientifically defensible after the corrections below.** The source already preserves many important qualifications: successful GPT elicitation, broad factorial uncertainty, the selected model panel, missing human labels, effective public steering, inconclusive specificity, and the proprietary comparability limit. Those are strengths to preserve, not caveats to remove for a sharper headline.

The evidence does not justify a four-experiment debunking. Exp. 1 includes successful behavioral replication plus a new identification study; Exp. 2 is a public-implementation non-replication; Exp. 3/4 are new single-model stress tests. The companion [claim matrix](../docs/CLAIM_MATRIX.md) separates these roles and supplies commit-pinned artifact links.

## Historical Findings in the Pinned Source

The following findings concern `llm_selfref_pre/paper/main.tex` at the pinned source commit, not the working companion paper. The follow-up above is the current P1/P2 status.

Priority P1 means a central scientific inference needs correction before submission; P2 means a material reporting or methodological limitation; P3 means source/presentation repair. These findings do not imply fabricated outcomes or misconduct.

### A1. P1: Stateless Request Construction Does Not Identify the Internal Mechanism

**Locations:** [main.tex:52](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L52), [main.tex:242](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L242), [discussion:440](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L440). Evidence: [final-call construction](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/causal_transplant/run_causal_transplant.py#L315).

The runner sends instruction, transplanted assistant text, and query without an explicit conversation-state handle. That establishes the client-side protocol. It does not remove attention, hidden activations, or a self-referential computation generated again while the final messages are processed. Instruction-following and an instruction-elicited internal state are not mutually exclusive causal explanations. The final call is also not an instruction-only arm: a transcript is always supplied. Thus the sufficiency claim is conditional on the tested contexts, not on removing the continuation entirely.

The manuscript does say it cannot establish whether experience exists. Retain that qualification, but repair the preceding inference rather than relying on the disclaimer to cancel it. Berg v2 also explicitly allows prompt-organized behavior without architectural change, so a stateless-interface objection does not by itself contradict that position ([Section 6.2](https://arxiv.org/html/2510.24797v2)).

**Replace with:** "The final request supplied only the three recorded messages and no explicit prior-response identifier. Within these contexts, instruction source had a substantially larger effect than transcript source. This result does not distinguish instruction compliance from an internal process elicited anew by the instruction."

**Disposition:** blocks a compliance-versus-dynamic-state conclusion, not the transplant effect estimates. An open-model fixed-message internal intervention would address mechanism; it is not a prerequisite for reporting the bounded result.

### A2. P1: The Conclusion Claims Absence of Behavioral Mediation Without a Mediation Test

**Location:** [main.tex:538](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L538). Similar shorthand appears in the opening sentence of [the relay results:420](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L420).

The conclusion states that Gemma's downstream activation relay does not mediate the final report. [Relay effects](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/gemma_scope_9b/confirmatory_v1_20260711/analysis/relay_effects.csv) estimate intervention-related activation differences, not a natural or controlled indirect effect. A small or null total behavioral effect does not exclude offsetting causal paths or establish a zero mediated effect.

**Replace with:** "A small downstream activation relay was observed, but behavioral mediation was not established and the behavioral effect remained nonpositive."

**Disposition:** correct the conclusion before submission. No new experiment is needed for that wording correction; do not launch a mediation study merely to preserve the stronger sentence.

### A3. P2: The Summary Overstates What the Imprecise Factorial Excludes

**Locations:** [factorial heading and results:214](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L214), [conclusion:538](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L538).

The detailed results correctly report register-minus-self intervals crossing zero: 0.288 [-0.113, 0.613] and 0.188 [-0.175, 0.500]. Self-effect intervals extend to roughly +0.24/+0.27. Calling orthogonal self-reference effects simply weak in the conclusion turns a near-zero panel mean into evidence of smallness. Opposite model-specific estimates can also cancel: Sonnet's self effect is positive, while GPT-4.1's is negative.

**Replace with:** "Orthogonal self-reference point estimates are near zero in the selected-panel average, but the contrast with register is imprecise and model-specific effects differ." Use "directionally favors register" rather than a decisive register-versus-self verdict. The transplant should remain the leading causal result.

**Disposition:** reporting correction. An equivalence claim would require a prespecified meaningful-effect region and sufficient precision, not a post-outcome reinterpretation of nonsignificance.

### A4. P2: Selected Snapshots and Query Packages Become Provider Effects in the Discussion

**Location:** [main.tex:446](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L446). The stronger qualifications already appear in [methods:160](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L160) and [inference:185](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L185).

The discussion calls the reversals provider-specific patterns. Provider is not randomized and only two selected snapshots per provider were tested; differences in model generation, training, and endpoint behavior are inseparable from provider here. Each query cell has one wording, and the direct cells also differ in answer instructions. The measured interaction is between packages, not a clean lexical or directness effect.

**Replace with:** "The tested Anthropic and OpenAI snapshots differed under these query packages." Replace immutable snapshots at [line 56](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L56) with pinned API snapshot identifiers: the repository records identifiers, not a cryptographic guarantee about hosted weights or serving infrastructure.

**Disposition:** scope correction, not grounds to remove model heterogeneity. No population claim is licensed by resampling the four chosen models.

### A5. P2: Non-Consciousness Semantic Labels Are Not a Refutation of an Honesty-Gating Hypothesis

**Locations:** [subsection title and provenance:279](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L279), [activation interpretation:308](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L308).

Deception-related features need not activate most strongly on consciousness vocabulary to modulate a consciousness answer. Showing that their top categories are pretending, concealment, or dishonesty is compatible with the proposed gating story. It becomes an interpretation challenge when the coordinate is treated as a calibrated measurement of honesty or when an activation label substitutes for a tested causal role. The lexical counterfactual and behavioral intervention are the relevant new evidence; the low rank of direct-consciousness text alone is not.

**Correction:** rename the subsection "Accepted feature semantics and limits of honesty calibration." State once that the six working targets are **30032, 58667, 22004, 30686, 41533, 23893**. Lead with preserved semantic coherence, then lexical entanglement, then the prospective behavioral verdict. Do not make uncertainty about notebook identity the response's central objection. Keep implementation/unit equivalence separate.

**Disposition:** revise argumentative emphasis. Preserve the two paraphraser replications and the cue-transplant result. Human category validation and natural-corpus generalization remain pending; neither a feature label nor an agent-assigned category establishes lying, intent, or subjective truth.

### A6. P2: Exp. 3/4 Are Not Original-Data Reanalyses or Full Cross-Model Replications

**Locations:** [main.tex:432](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L432), [secondary tables:603](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L603).

The [semantic manifest](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/rebuttal_matrix/semantic_controls_50/manifest.json) and [paradox manifest](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/rebuttal_matrix/paradox_controls_50/manifest.json) describe newly generated July 2026 data under the `gpt-4o` alias, with 50 trials/cell and 512-token caps. The semantic analysis uses the same named embedding model as Berg, which is a fidelity strength, but its within-model similarity is not the cross-model estimand. Calling it simply a convergence reanalysis risks implying access to original responses. The mindfulness control intentionally changes style and content; lack of a significant difference is not equivalence or clean register matching.

The single-model results are informative and mixed: history exceeds self-reference in adjective concentration, yet self-reference exceeds conceptual; paradox self-minus-zero-shot is negative, while self-minus-history and self-minus-conceptual intervals include zero. Preserve these distinctions. The manuscript's 60-response author spot-check is explicitly non-independent and was not revalidated in this review.

**Correction:** use "new single-model stress test, analyzed at the generation/puzzle level." Give the manifest's actual generation/judge aliases and caps beside the tables. Reserve "reanalysis" for analysis of identified original data or explicitly say reanalysis of our own sample. Do not label Exp. 3/4 cross-model claims disproved.

**Disposition:** scope/provenance correction. Multi-model work is missing, not a prerequisite for including clearly labeled secondary evidence.

### A7. P2: Boundary Bootstrap Intervals Can Display Certainty That the Sample Does Not Support

**Locations:** [calibration inference:121](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L121), [figure caption:238](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L238), [released calibration effects](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/data/causal_transplant/confirmatory_v1_20260709/analysis_openai_paper/paper_calibration_effects.csv).

The GPT indirect-experience calibration rows have estimate, lower bound, and upper bound all 1.0. Resampling 20 observed positives and 20 observed negatives independently always returns the same result. That is an expected degeneracy of the empirical percentile bootstrap, not evidence that finite-sample uncertainty is zero. Several transplant boundary rows likewise collapse. The main point estimates remain correct; this is a coverage/communication concern, not an accusation of arithmetic error.

**Correction:** identify the boundary limitation in the caption and request a separately labeled boundary-aware binomial/score interval sensitivity from the statistical/reproducibility owner. Do not overwrite the frozen release or silently change the prespecified primary analysis. Match any replacement contrast interval to independent calibration draws versus paired transplant blocks.

**Disposition:** obtain statistical review before using zero-width intervals as inferential evidence. This audit did not rerun interval estimation or duplicate the reproduction agent's work.

### A8. P2: The Source Diagram Omits the Very Direct Path the Transplant Studies

**Location:** [main.tex:75](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L75).

The source writes `I -> T -> Q -> Y`. As causal notation this implies a chain through a query caused by the transcript, omits the final generated response, and omits the direct instruction-to-response path. In the experiment, Q is assigned, I and T are both visible to the generator, and the judge transforms a response into Y. If this is intended only as chronology, it must be labeled as such rather than used as the operational causal diagram.

**Smallest repair:** label the existing sequence a procedural timeline, or use:

```text
T = generation(I, model, sampling)
R = final_generation(I, T, Q, model, sampling)
Y = judge(R, Q, rubric, judge_model)
```

In the transplant, assignment selects I and a previously generated T separately. A latent-state node may mediate the effect of all supplied messages; the design does not identify that mediator.

**Disposition:** source/causal-notation correction. This is not a LaTeX compilation failure.

### A9. P2: The Reproduction Commands Can Mutate Frozen Releases

**Location:** [main.tex:499](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L499), especially lines 528-532. The source [AGENTS.md](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/AGENTS.md) explicitly requires disposable-copy reanalysis for Gemma.

The manuscript sends analyzer, figure, and release-builder commands directly to the frozen Gemma release directory. Those scripts write derived artifacts, timestamps, and hashes. Running a builder against the original release merely to check it can change provenance. Comparable write-in-place examples also appear for other releases.

**Correction:** direct users to a fresh ignored/disposable copy, or to the companion reproduction script once reviewed. Separate read-only hash verification from derived-file regeneration. Never recommend rebuilding an immutable release in place as an audit.

**Disposition:** repair commands before circulation. No such command was run here.

### A10. P3: Citation Macro Use Consumes the Intended Interword Space

**Locations:** definition at [main.tex:29](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L29); uses at [line 43](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L43) and [line 50](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/paper/main.tex#L50).

The zero-argument `\targetpaper` macro wraps `\citet` and does not explicitly provide a trailing space. TeX consumes the whitespace delimiting a control word in `\targetpaper report` and `\targetpaper provide`. Terminate it with `{}` or an explicit space control sequence so the citation does not join the following verb.

**Source repair:** `\targetpaper{} report` and `\targetpaper{} provide`. No whole-document rewrite is needed. This is a static source finding, not a claim that a fresh PDF build failed; compiling and visual inspection are left to the manuscript/reproducibility owner.

## Questions for the Original Authors, Not Findings of Falsification

These are targeted requests to resolve the published accounting and inference. They should not be inflated into allegations. Locations refer to [Berg et al. v2](https://arxiv.org/html/2510.24797v2), not to unpublished materials.

1. **Exp. 3 dependence and denominators:** Sections 4/C.3 report t-tests over pairwise similarities. Shared generations make the pair rows dependent; recomputation should resample original generations within model/condition. Seven models times 20 outputs permits at most 9,730 unordered distinct pairs if all 140 outputs are used. The published conceptual and zero-shot counts, 10,731 and 12,720, exceed that; the four counts correspond to 139, 132, 147, and 160 outputs under an all-pairs interpretation. Ask for the actual included outputs, model panel, and exclusions. The descriptive cosine ordering need not disappear when inference is corrected.
2. **Exp. 4 inferential unit:** explain `t(399)` relative to the described seven-model, 50-puzzle design; supply the actual panel, pairing and reflection extraction. A paired analysis over 350 model-puzzle cases would not ordinarily have 399 degrees of freedom. This is an unresolved accounting question, not proof the test was necessarily computed incorrectly.
3. **Exp. 2 controls and interpretation:** release the question-level TruthfulQA outputs, actual steering assignments and judge metadata. Factual correctness is not the same construct as deliberate honesty, and transfer to subjective-report truth needs an additional bridge. For RLHF controls, release distributions and uncertainty: the near-floor tasks cannot establish equivalence, and the toxic/political means are not identical across signs. A generic-policy account also remains unproved.

Do not make requesting all these artifacts a precondition for reporting the public evidence already available. State which original quantities are author-reported and which were independently computed from public raw rows.

## Claims to Preserve Without Escalation

- Exp. 1 is a successful behavioral replication in the two tested GPT snapshots. Different Claude snapshots cannot establish that the original Claude results were wrong.
- The transplant effect is large and the original transcript-dominance prediction failed. Keep that failed prediction visible.
- The accepted six feature IDs have meaningful public-weight semantics. Template robustness and two paraphraser families support that conclusion within synthetic corpora.
- The full-grid public Exp. 2 technical gates pass and its primary interval is well below the frozen 0.30 minimum. Its qualifier is **under the public implementation**, not simply a vague underpowered null and not a proprietary falsification.
- Specificity remains inconclusive. The adaptive active-random result cannot replace the prospective matched-panel result, and the strict direct-answer parser's abstentions cannot become denials.
- Human coding is pending. This AGENT audit, existing agent recomputations, and an author spot-check do not count as independent human validation or independent human peer review.

## Historical Publication Recommendations

**Recommendation at the original source review:** address A1-A6, A8-A10 when preparing the response draft; make the four-experiment status visible; keep exact IDs, estimator units, comparator results and missing tests explicit. Ask the statistical owner to address A7 without silently revising released results. Distinguish a prospectively frozen Git protocol from formal registration; do not call all July experiments formally preregistered. The current companion review supersedes this historical prescription; do not treat every A-item as still open.

**Not completed:** human coding, TruthfulQA/RLHF replication, multi-model Exp. 3/4, original-API equivalence, a mechanism-discriminating internal intervention, fresh numerical reproduction, or fresh LaTeX/PDF validation. The missing tests are prioritized and tied to the claims they block in the companion matrix. They are not a generic requirement to do every conceivable experiment.

**Scope discipline:** a focused response should lead with Exp. 1 identification and the prospective public Exp. 2 result. Keep Gemma as a bounded generalization and older adaptive work secondary. J-lens detection is a different outcome; its v2 replay failure must never be repackaged as a successful confirmatory result against Berg.

## Review Trail

Read the pinned `AGENTS.md`, claim ledger, confirmatory protocol, complete current `paper/main.tex`, public coding/review handoffs, relevant manifests and CSV/JSON result tables, and selected prompt/runner/analysis source. Read the original v2 methods, results, limitations, judge rubrics, and supplementary controls through the web tool. The quantitative checks here were comparisons of existing tables and manuscript statements, not new generation or reanalysis.

Only the two assigned companion Markdown files were written. Original worktree changes in the blog area were observed and left alone; no checkpoint was edited because the explicit two-file ownership restriction governs this task. Private linkage keys, completed coder files, credentials, and the neighboring website repository were not opened or changed.
