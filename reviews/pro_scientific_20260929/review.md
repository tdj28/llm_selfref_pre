# Verdict

The main findings are potentially publishable and substantially well bounded: the instruction/transcript comparison concerns visible message packages, and the steering result concerns a specified public implementation—not consciousness or the validity of an unavailable proprietary result.

However, the central non-replication claim needs stronger uncertainty support, the intervention description needs clearer fidelity boundaries, and the response must identify precisely which proposition in Berg et al. it challenges. The internal-fingerprint sidebar currently exceeds the evidence described.

This is automated editorial review of the supplied manuscript and bibliography only. No linked artifacts, original-paper full text, figure pixels, or numerical receipts were supplied or verified. The responsible human remains the publication gate.

NOT READY FOR READER REVIEW

# Accuracy and claim findings

**B01 — Identify the original claim before adjudicating it.**  
**Affected:** Introduction, coverage table, transplant interpretation, steering comparison, discussion.  
**Status:** Required source check, not an established misquotation.

The manuscript fairly acknowledges that Berg et al. do not claim direct evidence of consciousness. But it does not document whether their explanation assigns causal importance specifically to the *earlier visible continuation*, rather than to self-referential processing induced anew by the retained instruction. The transplant distinguishes the former account, not the latter. Likewise, the reported 0.96-versus-0.16 steering contrast needs its original denominator, aggregation rule, endpoint, and intervention context.

**Minimum fix:** Add a short claim-to-test table containing:
- the relevant v2 quotation or tightly faithful paraphrase with page/section locator;
- the original measured endpoint and comparison;
- what this study manipulates;
- what remains observationally compatible.

Use this sentence unless source checking supports something stronger:

> “The transplant constrains a transcript-mediated explanation; it does not discriminate the original account insofar as that account allows self-referential processing to be induced by the retained instruction.”

Verify the v2 date, exact prompts, rubric attribution, six-feature provenance, and reported steering rates against the identified sources. No full-paper upload is necessary.

**Claim affected:** Whether this is explanatory disconfirmation of Berg et al., rather than a useful component intervention and implementation-specific non-replication.

**B03 — Complete intervention fidelity and factor-level disclosure.**  
**Affected:** Behavioral methods, semantic mapping, steering methods, Gemma section, implementation appendix.  
**Status:** Missing methodological information.

Important factors are already disclosed: model identities, token caps, query packages, feature IDs, subset counts, coefficients, matching variables, and separate scales. However:
- The exact induction instructions and final message-role/order construction are only linked or paraphrased.
- Hook application across prefill, generated positions, and cached decoding is unspecified.
- Signed additive latent edits are called “suppression” and “amplification” without explicitly distinguishing them from activation clamping, feature removal, or demonstrated downstream functional suppression.
- Gemma lacks the feature-set size, dose definition, timing, and matching details needed to interpret its supporting result.
- The lexical-cue extension does not compactly specify the cue transformation, insertion position/amount, and context matching.

**Minimum fix:** Add one compact factor inventory marking identity, dose, duration/positions, order, repetition, format/content, transformation, and prior context as **matched, varied, fixed, or untested** for each experiment. Include the short exact induction strings and message skeleton. State:

> “Suppression/amplification denote negative/positive requested additive edits; they do not by themselves establish selective removal/enhancement of the corresponding semantic process.”

Separate requested latent change, realized hidden-state perturbation, any re-encoded latent change, and subsequent behavioral outcome. Bind Gemma and semantic-mapping claims to their actual tested levels.

**Claims affected:** Instruction identification, matched-control adequacy, steering fidelity, and cross-model support.

**B04 — Remove or substantiate the internal-fingerprint sidebar.**  
**Affected:** Discussion, “An internal fingerprint is a different result.”  
**Status:** Missing evidence and insufficient readout definition.

“Large signed internal fingerprint … beyond matched SAE, identity, and five random-J controls” supplies neither its statistic nor the exact control-by-readout comparisons. The isolated-state AUROC is a different task and cannot substantiate that claim. Nor is it clear which quantity is a requested edit, realized edit, fixed-Jacobian projection, or actual downstream state.

**Minimum fix:** Prefer deleting this nonessential paragraph. If retained, provide a compact readout table defining those quantities, giving the fingerprint statistic for each invoked control, explaining the AUROC interval’s resampling unit, and separating the failed replay-gate analysis from confirmatory evidence. Do not call a projected quantity an observed downstream state.

**Claim affected:** Independent internal corroboration of intervention effects.

**S01 — Narrow semantic-validation language.**  
**Affected:** Abstract (“Feature semantics are verified”), feature section, discussion (“reproducible semantics”).  
**Status:** Definite overstatement relative to the described validation.

Designed-corpus category preferences, paraphrase robustness, and cue-transfer results support reproducible activation associations. They do not establish context-general semantic identity or exclusive mechanisms—especially given the substantial lexical recovery and pending independent validation.

**Minimum fix:** Replace “Feature semantics are verified but lexically entangled” with:

> “Designed-corpus activation associations reproduce across the tested paraphrases and are substantially lexically entangled.”

Retain “lexically entangled deception/roleplay coordinates” only with that operational definition. Identify the recovery-ratio interval as conditional on the observed discovery denominator wherever it is interpreted.

**Claim affected:** SAE construct validity, not the behavioral null.

# Statistical and scope findings

**B02 — Boundary resampling and the estimand require an uncertainty sensitivity.**  
**Affected:** Calibration, transplant/factorial intervals, primary steering verdict, Gemma support.  
**Status:** Methodological limitation with missing sensitivity evidence.

The caption correctly admits that bootstrap \([1,1]\) intervals are not certainty. Nevertheless, empirical resampling cannot represent unobserved outcomes in 20/20 and 0/20 cells. The primary steering endpoint is also near a boundary. Its bootstrap upper bound is central to the assertion that the study excludes the frozen 0.30 signature.

Additionally, the Llama analysis resamples 50 blocks although ten seeds recur five times. Reuse does not automatically invalidate the analysis, but the independence/generalization assumption needs justification or sensitivity analysis. Resampling four purposively selected models also introduces model-composition variation into an estimand described as the observed equal-model panel.

**Minimum fix:**
1. Give boundary-respecting binomial uncertainty for calibration rates and an appropriate risk-difference sensitivity.
2. Supply compact paired outcome counts for the primary aggregate comparison and a paired-proportion score/exact or other justified boundary-robust interval.
3. Report a seed-cluster sensitivity, or justify the block exchangeability assumption and restrict the estimand accordingly.
4. Distinguish fixed-panel sampling uncertainty from model-resampling/design sensitivity.

If the robust upper bound remains below 0.30, retain the non-replication conclusion unchanged. Otherwise qualify the exclusion claim. This does not require raw trial records.

**Claims affected:** Exclusion of a large steering signature and the interpretation of reported “95%” intervals.

**S02 — Clarify chronology without upgrading the freeze.**  
**Affected:** Behavioral analysis amendments, dose calibration, conclusion/provenance.  
**Status:** Missing chronology detail.

“Before final reporting” does not establish that the July uncertainty amendments preceded access to outcomes. The draft commendably avoids claiming that every analysis detail was initially frozen, but readers still need to distinguish pre-collection hypotheses, outcome-masked technical decisions, and post-outcome analysis corrections.

**Minimum fix:** Add a compact chronology giving each consequential decision’s date and whether behavioral outcomes were accessible. Retain the corrected analyses; do not imply they were all prospectively specified. The failed transcript prediction is appropriately attributed to the authors’ own frozen expectation, not to an invented audience prior. The 0.30 threshold should remain a decision threshold, not evidence of surprise.

**Claim affected:** Confirmatory status, not the point estimates.

# Reference audit

**R01 — Source attribution needs targeted checking, not bibliography expansion.**  
**Status:** Required live-source checks.

Every supplied entry has a body citation and a potentially necessary role; none is clearly orphaned or prestige decoration. The following is the complete inventory. Quoted warrants are manuscript claims, not independently verified source contents.

| Entry | Exact manuscript claim or sentence it is intended to warrant | Disposition |
|---|---|---|
| **Berg et al. (2025), arXiv:2510.24797v2** | “present four linked experiments”; “explicitly stops short of direct evidence of consciousness”; the reported 0.80 aggregate difference, target prompts/rubric, and unreplicated controls | **Retain; essential.** Verify each attribution with v2 locators, especially the proposed mechanism and rate denominators. Check revision date and notebook-versus-paper provenance. |
| **Sclar et al. (2024)** | “Prompt-format sensitivity … [is an] established methodological concern” | **Retain narrowly.** It supports format sensitivity, not consciousness-report validity or the particular transplant mechanism. Check bibliographic metadata/publication venue. |
| **Zheng et al. (2023)** | “limitations of model-based evaluation are established methodological concerns” | **Retain narrowly.** Name the relevant limitation rather than implying validation of this rubric. Verify title, complete author list, and publication status; the supplied entry is an arXiv record. |
| **Goodfire (2024)** | “Goodfire’s public SAE release is a concrete resource” | **Retain as resource provenance.** Verify page title/date and linkage to the actual Llama-3.3 layer-50 release. A vendor research page does not establish proprietary equivalence or semantic validity. |
| **Lieberum et al. (2024)** | “uses Gemma 2 9B IT with direct-IT Gemma Scope SAEs” | **Retain.** Check that the cited report/resource supports the specific direct-IT sites and widths used; identify the exact resource revision separately if needed. Treat it as the supplied technical/preprint report, not authority for causal validity. |
| **Jones (2026)** | “The source repository … is pinned to commit …; it contains protocols, raw outcomes, judgments, telemetry, amendments, analyses, and release hashes” | **Retain as evidence provenance.** It is not independent validation. Check snapshot accessibility and whether it contains the cited releases; do not imply this review inspected it. |

The principal missing citation support is precise original-source support for B01, not a larger consciousness bibliography. If broad SAE semantic-validity assertions remain, a directly relevant limitation/validation source would have a role; narrowing those assertions to this study’s measured associations avoids unnecessary expansion. No source should be added merely for prominence or balance.

# Figure-to-text consistency

**F01 — Numerical and visual binding remains unverified.**  
**Affected:** All five figures, especially judge sensitivity and technical dose.

Five figure inclusions agree with the appendix’s count of five copied plots. The supplied prose/table arithmetic is internally consistent:
- Calibration averages are approximately 0.638 and 0.650.
- Instruction plus transcript effects recover those calibration contrasts at reported precision.
- Instruction-minus-transcript effects are 0.838 and approximately 0.913.
- The control-mean specificity calculations agree with the tabulated effects.

But captions are not figure receipts. In particular, the judge figure promises target-minus-controls effects for every evaluation rule, whereas the text supplies only external-judge target effects. Dose/matching plots likewise cannot be checked from the manuscript.

**Minimum fix:** Provide a compact figure-value receipt containing plotted estimates, intervals, denominators, and NA cells, or have the responsible human document that comparison. Include external-judge control/specificity cells rather than inferring them from primary-judge results. Check reference diamonds, interval types, scale separation, and parser NA against the plots. No pixels or alt text were supplied for this review; neither was verified.

# What should remain unchanged

- The strong positive exact-prompt label replication, with provider-specific differences.
- The substantial instruction-versus-transcript contrast, restricted to the tested message packages.
- The imprecise register result and retained failed predictions.
- The public Llama non-replication finding, subject to B02—not softened for marketability.
- The distinction between inconclusive specificity and established equivalence.
- Separate literal/calibrated scales and disclosure of missing calibrated panels.
- Parser abstention as missing evidence, not a null effect.
- Pending human coding, failed transfer/replay gates, exploratory secondary probes, and non-equivalence to the proprietary implementation.
- The explicit refusal to infer either consciousness or its absence.

# Required revisions

1. **B01:** Establish the exact original propositions and delimit what the transplant challenges.
2. **B02:** Add compact boundary-robust and dependence-sensitive uncertainty checks.
3. **B03:** Complete the factor inventory and distinguish additive edits from functional suppression.
4. **B04:** Remove the internal-fingerprint sidebar or supply its exact readout/control evidence.
5. **S01–S02, R01, F01:** Narrow semantic language, clarify chronology, complete source checks, and bind figures to compact numerical receipts.

# Publication checklist

- [ ] Original v2 claims, dates, rates, and protocol attributions checked.
- [ ] Primary exclusion conclusion survives justified uncertainty sensitivities.
- [ ] Treatment factors and untested levels explicitly inventoried.
- [ ] Requested edits, realized perturbations, projections, and downstream outcomes remain distinct.
- [ ] Every invoked control contains the claimed readout/statistic; missing cells remain visible.
- [ ] All five figures checked against compact values, including external-judge specificity.
- [ ] Bibliography metadata and precise resource provenance checked.
- [ ] No human-validation, peer-review, or source-verification claim exceeds what occurred.
- [ ] Responsible human approves the bounded claims and final publication version.
