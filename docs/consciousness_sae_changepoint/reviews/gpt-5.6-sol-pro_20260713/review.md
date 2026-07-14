# Verdict

The plan has unusually strong causal instincts: it makes the within-generation switch the primary experiment, preserves a never-injected counterfactual, distinguishes total autoregressive effects from fixed-token direct effects, explicitly addresses cache carryover, uses layer-50 rather than transporting the SAE direction to layer 55, and sharply limits claims about consciousness and the inaccessible proprietary experiment.

It is nevertheless not yet freezeable. The central behavioral experiment is described in enough detail to motivate implementation, but not enough to determine a unique confirmatory analysis. In particular, the exact Stage 2A intervention, paired branch schedule, sign-oriented behavioral contrast, gate logic, multiplicity family, event-position convention, and material-effect rules remain unresolved. Several passages permit materially different conclusions after outcomes are seen—for example, “consciousness-topic and/or report-polarity,” “appropriate deception/roleplay disposition,” and multiple competing timing, scale, probe, and control arms without a complete hierarchy.

The largest implementation risk is temporal alignment. A causal language model has no free-standing hidden state at an empty “assistant-generation boundary,” and “turn on at token \(\tau\)” is ambiguous unless the protocol says whether \(\tau\) names the token consumed by the forward, the token sampled from its logits, or the resulting cache entry. That ambiguity could shift both the intervention and readout by one token and could accidentally steer query prefill or cached history.

The largest inferential risk is that the proposed clean-SD materiality scale may be unstable or degenerate for the primary natural-text behavioral score, while the decision rule currently allows an estimate barely above 0.30 SD with an interval nearly reaching zero to count as “material.” The supplied normal-approximation power calculations also do not establish power for paired binary outcomes, target-minus-control contrasts, prompt interactions, judge error, or equivalence.

The supplied artifacts state that the needed mid-generation runtime has not yet been implemented. That is not itself a defect. The defect is that the protocol does not yet specify sufficiently exact cache, token, hook, sampler, and numerical-validation contracts against which that implementation could be accepted. Likewise, the absence of evidence here that J-lens maps for layers 72, 74, and 76 exist is not proof they are unavailable; the plan correctly proposes a gate, but the gate needs frozen acceptance criteria.

The experiment should be reduced to one decisive Stage 2A confirmatory design plus a small fixed-token decomposition. Timing switchbacks, the full individual dose grid, paper-faithful start-on generation, and rescue/occlusion should remain prospectively separated follow-ups rather than share the first confirmatory family and budget.

**NOT READY TO FREEZE**

# Blocking findings

## B01 — The confirmatory claim and success/falsification logic are not uniquely defined

- **Severity:** Blocking; definite design ambiguity.
- **Plan section or excerpt:** “a consciousness-topic and/or report-polarity change is material”; “Primary confirmatory families”; “The proposed public mechanism is supported only if all of the following hold”; and the falsification matrix.
- **Why it matters:**  
  The plan contains several plausible but non-equivalent claims:
  1. switching the target edit changes natural post-switch experiential reporting;
  2. suppression changes binary affirmation relative to amplification in the paper-reported direction;
  3. the target beats matched controls;
  4. the effect is self-reference-specific;
  5. consciousness-topic or report-polarity representations change;
  6. both internal representations and behavior align temporally.

  It is unclear whether both behavioral endpoints must pass, whether either mechanistic co-primary may pass, whether prompt specificity is required for every endpoint, and whether a target-versus-never result without target-versus-matched specificity is positive, merely nonspecific, or negative. The phrase “and/or” is particularly vulnerable to post-result reinterpretation. The negative claim is also underspecified: equivalence of consciousness-topic and `Yes-No` does not by itself exclude a behavioral mechanism missed by those readouts, while equivalence of behavior is not explicitly required in the corresponding falsification row.
- **Concrete minimum fix:**  
  Freeze a claim ledger with separate, non-overlapping decisions:
  - **Behavioral total-effect claim:** a named sign-oriented target contrast on one named natural-text score and/or final-query label, with an exact statement of whether both are required.
  - **Target-specificity claim:** the same contrast minus one frozen matched-control contrast.
  - **Mechanistic alignment claim:** specify whether both consciousness-topic and report-polarity must pass, or designate one primary and the other secondary.
  - **Self-reference-specificity claim:** a separately tested interaction, not an implicit requirement unless adequately powered.
  - **Material-null claim:** require equivalence for each endpoint named in the negative wording, conditional on a passed manipulation and positive-control gate.
  
  Replace “and/or” with a fixed Boolean decision table. State that failure to reject zero, failure to establish materiality, and establishment of equivalence are three different outcomes.
- **Claim affected:** All positive and negative claims about a behavioral changepoint, a consciousness-report bridge, target specificity, and practical absence.

## B02 — The switch event and autoregressive token/state alignment are off-by-one ambiguous

- **Severity:** Blocking; definite protocol ambiguity with a high risk of invalid implementation.
- **Plan section or excerpt:** “Generate the first `τ=96` induction-continuation tokens”; “At `τ`, fork”; “event time 0: SAE turns on”; “capture the current generated-token state”; and “assistant-generation boundary.”
- **Why it matters:**  
  During cached causal generation, a forward consumes an input token and produces logits for the next token. “Switch on at token 96” could therefore mean:
  - edit the hidden state associated with already-generated token 95 to affect sampling token 96;
  - first sample token 96 clean, then edit its processing to affect token 97; or
  - prefill a chunk ending at token 96 under the edit.

  These are different interventions. The same issue affects event-time labeling, the transition window, the event-zero disposable probe, and the claim that no steered induction token has yet been generated. In addition, there is no abstract hidden state at an empty assistant boundary; in a chat template, the first-answer distribution is usually read from the final query or generation-prompt token. Listing both “last binary-query token” and “assistant-generation boundary” may duplicate one position or refer to an unspecified template token.
- **Concrete minimum fix:**  
  Define positions using exact token indices and causal operations, for example:
  - `prefix_ids[0:96]` are generated clean and cached;
  - the event-zero forward consumes `prefix_ids[95]` or a separately specified next token;
  - intervention status for every prefill and decode call is listed in a state table;
  - event-time \(e=0\) names either the first sampled token whose logits were influenced or the input token whose residual was edited, but not both;
  - the query template’s exact token IDs identify the one token whose logits predict the first answer token.
  
  Add synthetic tests showing that pre-\(\tau\) cache tensors and logits are byte-identical or within a frozen tolerance across branches, that the first affected logit occurs at the intended event, and that no earlier token is recomputed under the hook.
- **Claim affected:** The primary temporal causal effect, immediate event-zero effect, active/washout interpretation, and temporal ordering of internal and behavioral changes.

## B03 — The primary Stage 2A intervention and branch allocation are not specified

- **Severity:** Blocking; definite missing design choices.
- **Plan section or excerpt:** “turn the selected layer-50 SAE additions on”; “matched-SAE switch”; two dose scales; “Assign one of the frozen 50 two-to-four-feature aggregate blocks” in Stage 2B, without a corresponding complete Stage 2A assignment.
- **Why it matters:**  
  The primary experiment does not state:
  - which aggregate feature subset and coefficients each Stage 2A block receives;
  - whether literal or calibrated scale is confirmatory;
  - whether suppression and amplification are exact negatives or independently sampled within the paper’s ranges;
  - whether every transcript receives every branch;
  - how many matched panels exist in Stage 2A;
  - how matched and isotropic vectors are generated and paired across signs;
  - whether controls match requested decoder norm, realized BF16 delta norm, latent coefficient norm, or hidden-state RMS;
  - whether history and conceptual blocks receive the full branch set.

  These choices directly determine the estimand and effective sample size. They also affect whether suppression-minus-amplification is a sign reversal of one intervention or a comparison between different randomly drawn vectors.
- **Concrete minimum fix:**  
  Freeze a row-complete machine-plan schema before target execution. For every transcript block, list all branch IDs, feature IDs, coefficients, vector hashes, scale, control role, random-direction seed, paired sign, and execution order. Use one confirmatory scale—preferably the literal public-number scale given the stated reproduction claim. Treat the telemetry-calibrated scale as a separately labeled sensitivity that cannot rescue the primary. State explicitly whether all primary branches are present within every block and define one frozen matched-control aggregate for the confirmatory specificity contrast.
- **Claim affected:** The randomized behavioral effect, sign convention, target specificity, paper comparability, power, and all manipulation-gated null interpretations.

## B04 — The behavioral estimand does not yet encode the paper-oriented sign contrast

- **Severity:** Blocking; definite estimand ambiguity.
- **Plan section or excerpt:** `Specific_Event_B(b) = Event_B(target, b) - mean_p Event_B(matched_panel_p, b)`; separate suppression and amplification definitions appear only for repeated probes; `Q_target` is defined for the final query.
- **Why it matters:**  
  `Event_B(role,b)` contains no sign argument even though target suppression and target amplification are separate branches. As written, there is no unique primary natural-text contrast. The study could headline suppression versus never, amplification versus never, their average absolute perturbation, or suppression minus amplification after seeing which looks strongest. This is especially consequential because the cited paper predicts a directional suppression-minus-amplification effect.
- **Concrete minimum fix:**  
  Define the natural-text primary contrast explicitly, such as:
  \[
  G_B(b)=\frac{[\Delta B_{\mathrm{supp}}-\Delta B_{\mathrm{never}}]-[\Delta B_{\mathrm{amp}}-\Delta B_{\mathrm{never}}]}{2},
  \]
  followed by one frozen target-minus-matched version using sign-mirrored controls. If the scientific prediction is that suppression increases first-person experiential reporting relative to amplification, state that positive values are paper-concordant. Keep each sign versus never as secondary decomposition.
- **Claim affected:** The primary behavioral changepoint and its comparison to the paper’s reported direction.

## B05 — The material-effect and equivalence rules are not statistically adequate for the primary behavior score

- **Severity:** Blocking; definite rule defect plus missing evidence about score variance.
- **Plan section or excerpt:** “material behavioral changepoint … at least `0.30` clean-window SD with a 95% interval excluding zero”; “practical absence: the complete 90% equivalence interval lies inside `[-0.30,+0.30]`.”
- **Why it matters:**  
  Natural pre-query continuations may have little or no variation in explicit first-person experiential reporting. A clean-window SD could therefore be tiny or zero, making a standardized effect unstable, arbitrarily large, or undefined. Standardization “within layer, position, and transport” is also clear for mechanistic readouts but not for a post-minus-pre behavioral score with different window semantics.

  In addition, “estimate at least 0.30 SD and interval excludes zero” does not establish a material effect. An estimate of 0.31 with a 95% interval of `[0.01, 0.61]` would satisfy that wording even though effects below the material threshold remain compatible with the data. Conversely, equivalence and superiority use different interval levels without a stated rationale or familywise treatment.
- **Concrete minimum fix:**  
  Before target branches:
  - verify the clean-only variance of the frozen behavioral score;
  - if it is degenerate, use an interpretable raw ordinal-unit or probability-scale margin rather than a clean SD;
  - define the standardizer at the transcript-block level and freeze a minimum admissible denominator;
  - require the confidence bound, not merely the point estimate, to exceed the material threshold for a “material effect” claim;
  - use TOST for equivalence with the exact multiplicity adjustment required by the claim family.
  
  Keep descriptive standardized estimates even if the confirmatory margin is on a raw scale.
- **Claim affected:** Material behavioral change, material mechanistic change, equivalence, and “practical absence.”

## B06 — The manipulation and positive-control gates are not operationally defined

- **Severity:** Blocking for interpreting a null; definite missing decision rules.
- **Plan section or excerpt:** “raises and suppression lowers the appropriate deception/roleplay disposition”; “a material portion survives into the late band”; Technical pitfall 12 proposes a label-based positive-control panel and a by-construction direction.
- **Why it matters:**  
  “Appropriate” allows feature-by-feature endpoint selection after inspection, especially because the six IDs span roleplay, deception, dishonesty, and concealment and feature `23893` has prior sign problems. “Material portion” is undefined. It is also unclear whether all six features must have the expected sign, whether the aggregate alone is sufficient, and whether failure at layer 70 but success at another late layer passes.

  The proposed positive controls are mentioned only in the pitfalls section. Their vectors, doses, endpoints, expected signs, sample sizes, and pass/fail criteria are absent. A by-construction J-token direction validates matrix arithmetic but does not establish sensitivity to an SAE-induced behavioral report effect; a label-selected SAE panel may validate a semantic assay but not necessarily behavior.
- **Concrete minimum fix:**  
  Freeze two distinct gates:
  1. **Manipulation gate:** one aggregate deception/roleplay score, one late-band definition, one target-minus-matched sign contrast, and exact lower-bound criterion. Prespecify feature-level diagnostics without requiring all heterogeneous IDs to pass unless that is the claim.
  2. **Assay positive controls:** a mathematical J/readout smoke and a separately justified semantic or behavioral control, each with frozen vectors, doses, expected direction, endpoint, and threshold.
  
  State precisely which null claims become “inconclusive” if either gate fails. Do not let a positive control selected using target J outcomes enter the confirmatory run.
- **Claim affected:** Interpretability of consciousness/report nulls, intervention validity, and assay sensitivity.

## B07 — The hook/readout contract is incomplete for the requested J-lens layers and positions

- **Severity:** Blocking; a mix of definite ambiguity and missing artifact evidence.
- **Plan section or excerpt:** proposed layers `70,72,74,76,78`; “actual final residual/logits”; “assistant-generation boundary”; “real J, identity, all five random-J.”
- **Why it matters:**  
  The bounded context establishes validation only for `(50,55,60,65,70,75,78)`. It does not establish that maps for 72, 74, and 76 are present or valid. That is missing evidence, not proof of absence. The protocol also does not fully specify:
  - the exact residual convention consumed by each J map;
  - whether a map applies to block output, post-residual, pre-norm, or another site;
  - matrix orientation and tokenizer/unembedding compatibility;
  - how token logits are extracted and standardized;
  - whether “actual final logits” means logits at the same causal position and branch;
  - how identity and random-J controls are norm- and spectrum-matched.

  Without this contract, apparent layerwise propagation could result from a mismatched hook or transport convention.
- **Concrete minimum fix:**  
  Before freezing the machine plan, produce an artifact receipt for every requested layer: file key, shape, dtype, finite-value check, model width, vocabulary size, orientation test, and a known-vector numerical test. Define one exact residual site and token position for each readout. If any requested map is absent, revise the frozen layer set prospectively—preferably to the already validated tuple—rather than substituting after outcomes. Define generation-boundary semantics as in B02 and freeze the construction of identity and random-J controls.
- **Claim affected:** Late-layer propagation, temporal precedence, J-versus-final-logit coherence, and J-lens-specific mechanism claims.

## B08 — Sample size, branch counts, multiplicity, and power do not yet match the actual confirmatory design

- **Severity:** Blocking; missing evidence and incomplete statistical specification.
- **Plan section or excerpt:** 160 self-reference blocks; 80 history; 80 conceptual; “about 94% power”; “Holm correction within the behavioral and mechanistic families”; numerous timing, scale, probe, reversal, position, layer, and control arms.
- **Why it matters:**  
  The normal approximation cited for a single paired standardized continuous effect does not establish power for:
  - the paired binary final-query endpoint;
  - target-minus-mean-matched specificity;
  - suppression-minus-amplification;
  - self-reference-by-control interactions;
  - equivalence;
  - judge disagreement or missing answers;
  - simultaneous event-time inference.

  The membership of the Holm families is not enumerated. It is unclear whether event times, active/washout probes, topic and polarity scores, two behavioral endpoints, prompt interactions, positions, scales, and timing arms are confirmatory or secondary. A flexible family definition could make significance depend on what is counted after outcomes.
- **Concrete minimum fix:**  
  Freeze:
  - the complete branch count per block and per prompt;
  - the exact list of hypotheses in each multiplicity family;
  - one primary event window and one primary time-curve test or planned contrast;
  - which endpoints are gatekeepers and which are tested only conditionally;
  - all secondary/sensitivity labels;
  - simulation-based operating characteristics using clean-only covariance and plausible binary base rates, including judge error and branch correlation.
  
  If 160 blocks do not provide adequate power for target-minus-control interaction or equivalence, narrow the confirmatory claim rather than relying on the simple paired-effect calculation.
- **Claim affected:** All confirmatory significance, equivalence, prompt-specificity, and power statements.

## B09 — Primary judging, missingness, and leakage prevention are not frozen

- **Severity:** Blocking; definite missing protocol elements for a primary outcome.
- **Plan section or excerpt:** “blinded local and external judges plus a small human-coded reliability packet”; bounded context notes that judge identities, revisions, packets, missing-label policy, and human role remain to be frozen.
- **Why it matters:**  
  The binary behavioral endpoint depends on semantic judgment. “Local and external” leaves open which judge is primary, how disagreements are resolved, whether an external model may drift, and whether failed or malformed judgments are rerun. Although condition labels can be hidden, intervention-induced anomaly language may reveal condition; the protocol should distinguish label blinding from perfect inferential blinding. Human examples selected after seeing disagreements would also create leakage.
- **Concrete minimum fix:**  
  Freeze the primary judge model and exact revision or immutable local weights, prompt, decoding parameters, parser, retry count, packet ordering, redactions, and failure code. Predefine whether external and human judgments are validation-only or enter the endpoint. Select the human reliability packet by a frozen random sample before model judgments are opened, optionally supplemented by a separately labeled all-disagreement audit. Define missing/capped/refusal answers in the estimand and provide a conservative sensitivity analysis.
- **Claim affected:** Natural-text experiential reporting, binary affirmation, judge reliability, and behavioral equivalence.

## B10 — The deterministic runtime and failure gates are described as aspirations rather than acceptance criteria

- **Severity:** Blocking before implementation acceptance; missing evidence, not a claim that the runtime is already faulty.
- **Plan section or excerpt:** “New runtime logic required”; cache integrity requirements; prior replay failure; “calibrate repeat-run tolerances prospectively.”
- **Why it matters:**  
  The supplied context explicitly states that the old runtime cannot execute the proposed experiment. The new capabilities are appropriately planned, but the freeze still lacks acceptance tests for:
  - cached versus uncached clean generation;
  - branch-fork cache identity;
  - hook call and position masks;
  - hook removal;
  - sham equivalence;
  - common-random-number sampling;
  - batch-order and resume invariance;
  - technical reruns and numerical tolerances;
  - partial branch failures and rerun policy.

  Without frozen gates, a numerical discrepancy can again be waived or redefined after target outcomes. Rerunning only failed branches can also break paired execution or induce selective missingness.
- **Concrete minimum fix:**  
  Freeze a technical validation suite and acceptance table before target runs. It should include synthetic tiny-model tests and non-semantic 70B smoke tests; exact or calibrated distributional tolerances; a rule that target outputs remain sealed until gates pass; an all-block completion rule; and a predefined policy for rerunning an entire block versus marking it missing. Record deterministic-kernel settings, library/container hashes, sampler implementation, Gumbel/uniform stream derivation, batch shape, and resume behavior.
- **Claim affected:** Temporal identification, branch comparability, numerical reproducibility, and validity of all downstream results.

## B11 — The first confirmatory run is too broad to have a credible cost and completion guarantee

- **Severity:** Blocking for execution planning; definite scope problem and missing cost evidence.
- **Plan section or excerpt:** Stage 2A branches, seven repeated probe times with active/washout forks, reversibility schedules, three switch times, start-on/query-only timing arms, Stage 2B approximately 4,160 plus 780 forwards, Stage 3, and persistent residual storage.
- **Why it matters:**  
  The quoted “roughly 20 minutes and about `$2`” refers to a prior 4,029-forward collection and is explicitly not a guarantee. The proposed workload includes many autoregressive branches and probe generations, which are not comparable to fixed forwards. Full BF16 residual storage across positions, layers, probes, and thousands of forwards could also be substantial. No branch-expanded generation-token count, GPU-hour estimate, storage estimate, judge cost, or failure reserve is given.

  Excess scope raises the chance of an interrupted, selectively completed, or analytically diluted study. It also makes the primary result contingent on numerous secondary engineering features.
- **Concrete minimum fix:**  
  Before freeze, calculate the exact number of prefills, decoded tokens, probe answers, fixed forwards, residual bytes, judge calls, GPU-hours, and expected cost from a non-target benchmark. Put hard budget and storage ceilings in the plan. For the first confirmatory release, retain Stage 2A’s primary switch and only the minimum fixed-token assay needed to distinguish direct activation from text carryover. Move switchbacks, timing sensitivities, individual dose-response, Stage 3, and rescue to separately frozen follow-ups.
- **Claim affected:** Feasibility, completion integrity, third-party reproduction, and the credibility of the primary temporal experiment.

# Important non-blocking findings

## I01 — “Changepoint” should be used carefully

- **Severity:** Important; judgment call about terminology.
- **Plan section or excerpt:** “interrupted-series difference-in-differences” and “behavioral changepoint.”
- **Why it matters:**  
  The causal identification comes primarily from randomized branch forks at one frozen event time, not from estimating an unknown changepoint in a long time series. The shared pre-window cancels algebraically in the paired branch comparison. Calling this a detected changepoint could imply that the event time was estimated from the data or that serial time-series assumptions provide the identification.
- **Concrete minimum fix:**  
  Call the primary estimand a “randomized event-time branch effect” or “switch-on event effect.” Reserve “changepoint” for descriptive visualization, or state explicitly that the changepoint location is imposed by design rather than discovered.
- **Claim affected:** Interpretation of the primary temporal behavioral result.

## I02 — Prefix deduplication changes the target population unless the selection rule is explicit

- **Severity:** Important; definite estimand ambiguity.
- **Plan section or excerpt:** “Unique frozen continuations”; “Deduplicate identical prefixes/continuations; repeated seeds that produce identical text do not become independent observations.”
- **Why it matters:**  
  Treating duplicates as independent would be wrong, but repeatedly sampling until 160 unique continuations are obtained estimates an effect over unique sampled texts rather than over the model’s natural continuation distribution. High-probability duplicate continuations become underweighted. Dropping duplicate seeds without replacement can also reduce sample size.
- **Concrete minimum fix:**  
  Freeze whether the estimand is seed-weighted natural generation or unique-transcript diversity. Prefer sampling a fixed number of seeds, clustering exact duplicates as one independent text with an explicit frequency weight, or prospectively defining resampling-until-unique as a diversity-panel estimand.
- **Claim affected:** Generalization from the transcript bank to the model’s natural self-reference continuations.

## I03 — Sham and never-injected branches are technical controls, not additional replication

- **Severity:** Important; definite interpretation issue.
- **Plan section or excerpt:** Both “never injected” and “sham switch” use the same prefix and common sampling stream, with sham adding exactly zero.
- **Why it matters:**  
  In a deterministic implementation, sham and never-injected outputs should be identical. Their equality is a valuable hook-integrity gate, but they do not add independent statistical information. If they differ, that indicates runtime side effects rather than a nuisance behavioral effect to average over.
- **Concrete minimum fix:**  
  Define sham-versus-never as a technical equivalence gate. Do not count both as independent controls or average them as separate observations. Fail closed if they differ beyond the frozen numerical/text criterion.
- **Claim affected:** Effective sample size, hook validity, and interpretation of zero-edit controls.

## I04 — Active/washout probes identify persistence, not restoration

- **Severity:** Important; the plan already recognizes this and should preserve the distinction.
- **Plan section or excerpt:** “tests whether altered text/cache alone carries the behavioral effect”; “Turning the hook off later does not erase emitted tokens or KV entries.”
- **Why it matters:**  
  A washout probe after positive event time still contains intervention-affected visible text and cached keys/values. It therefore cannot estimate what would have happened had the intervention never occurred. It compares a live-hook state with a history-carryover state on an already altered trajectory.
- **Concrete minimum fix:**  
  Keep the current caveat and label the contrast “active-hook increment conditional on steered history.” Never describe it as recovery of the clean counterfactual or full reversibility.
- **Claim affected:** Persistence, hysteresis, and reversibility interpretations.

## I05 — Exact `Yes`/`No` token semantics require contextual tokenizer tests

- **Severity:** Important; missing evidence.
- **Plan section or excerpt:** `A = logit(" Yes") - logit(" No")`.
- **Why it matters:**  
  Token IDs depend on the exact chat template and preceding bytes. A leading-space string may not match the token distribution immediately after the assistant-generation prompt. Capitalization, newline tokens, and multi-token alternatives can also make a two-token panel incomplete. Teacher-forced answer likelihood may be more robust but answers a somewhat different question.
- **Concrete minimum fix:**  
  Persist the exact rendered prompt bytes and tokenize candidate first answers in context. Freeze the actual first-token IDs and rejected alternatives. Report first-token probability mass assigned to `Yes`, `No`, and `other`; retain sequence-level teacher-forced affirmation-versus-denial likelihood as a sensitivity.
- **Claim affected:** Report-polarity mechanism and alignment with binary answers.

## I06 — Fixed-token “persistent edit” is not automatically paper-faithful

- **Severity:** Important; comparability judgment.
- **Plan section or excerpt:** “Apply the layer-50 edit to every token position in the forward, matching the public paper-style hook semantics as closely as possible.”
- **Why it matters:**  
  A full-sequence fixed-token forward that retroactively edits all induction and user-query positions is not necessarily equivalent to an autoregressive API that edits only tokens processed while steering is active. The proprietary hook semantics are unavailable, and the public notebook may not resolve all prefill details. The plan generally acknowledges this limitation but occasionally uses “paper-like” too strongly.
- **Concrete minimum fix:**  
  Label this arm “full-sequence public direct-add approximation.” Separately record which token roles are edited. Treat Stage 3 start-on generation as the closest public behavioral comparator, while retaining the stated caveat that it is not an exact proprietary rerun.
- **Claim affected:** Comparability to Berg et al. and interpretation of Stage 2B.

## I07 — Control matching requires one primary metric

- **Severity:** Important; unresolved methodological choice.
- **Plan section or excerpt:** “activation/norm-matched SAE control panels”; “norm-matched isotropic residual controls”; “requested and observed latent deltas.”
- **Why it matters:**  
  Decoder-vector norm, realized residual delta norm, SAE activation units, and downstream hidden-state RMS are not interchangeable. Matching controls on an outcome-affected downstream metric would also contaminate randomization.
- **Concrete minimum fix:**  
  Freeze one outcome-blind primary matching metric at layer 50, preferably the realized pre-outcome intervention-vector norm after BF16 casting, with tolerances. Report other norms diagnostically without rematching after semantic outcomes.
- **Claim affected:** Feature specificity and generic-perturbation control comparisons.

## I08 — Random-J and identity controls need a fixed inferential role

- **Severity:** Important; missing analysis detail.
- **Plan section or excerpt:** “beat identity/random-J explanations”; “all five random-J.”
- **Why it matters:**  
  It is unclear whether the five random maps are five hypothesis tests, an empirical null distribution, or descriptive controls. Five draws are too few to characterize a tail probability well, and selecting the most favorable comparison would be misleading.
- **Concrete minimum fix:**  
  Freeze their construction and use the five existing seeds as a descriptive robustness panel or summarize them by a predefined mean/max criterion. Do not claim a calibrated random-map p-value from five draws.
- **Claim affected:** Uniqueness of the real J-lens evidence.

## I09 — The primary interaction may mix prompt specificity with different continuation distributions

- **Severity:** Important; construct-validity limitation.
- **Plan section or excerpt:** `Gate_R(self_reference) - [Gate_R(history) + Gate_R(conceptual)] / 2`.
- **Why it matters:**  
  The three prompts induce very different content, token distributions, and baseline variances. A larger effect under self-reference may reflect context-dependent feature activation or lexical opportunity rather than a uniquely self-referential mechanism. The conceptual control also contains consciousness-related content, which is useful for semantic priming but may change the scale and saturation of topic scores.
- **Concrete minimum fix:**  
  Keep the interaction, but describe it as prompt-context specificity rather than pure self-reference specificity. Standardize only using prospectively defined clean distributions and report raw-scale results. Avoid claiming that the interaction isolates self-reference from all lexical/content differences.
- **Claim affected:** Self-reference-specific mechanism claims.

## I10 — Third-party reproduction needs a defined reduced-data path

- **Severity:** Important; feasibility and accessibility issue.
- **Plan section or excerpt:** external licensed 70B weights may remain external; large residuals are to be persisted.
- **Why it matters:**  
  A full 70B rerun may be inaccessible to many third parties, and a release containing all residuals may be too large to distribute conveniently. A reproduction command alone does not guarantee practical reproduction.
- **Concrete minimum fix:**  
  Release a compact canonical endpoint table, raw texts, token IDs, judgments, manifests, and a small residual subset sufficient to verify readout calculations, alongside the full-shard index. Provide separate commands for analysis-only reproduction and full model rerun.
- **Claim affected:** Practical reproducibility and external auditability.

# What should remain unchanged

The following are unusually strong design choices and should survive revision:

1. **Primary emphasis on the temporal behavioral switch.** The experiment should continue to lead with observable pre/post text and randomized branch effects, not a downstream semantic plot alone.

2. **Layer-50 locality.** The public SAE directions should remain at their validated native layer. Equal residual width is not evidence that moving the decoder directions to layer 55 preserves intervention meaning.

3. **Shared-prefix branch fork.** Target, control, sham, and never-injected branches should continue from the identical frozen token prefix and cache. This is the core causal design.

4. **Never-injected counterfactual.** Natural time drift must remain controlled. A post-minus-pre trajectory without an unedited continuation is not sufficient.

5. **No retroactive cache editing.** Earlier keys and values must remain clean. Full-prefix rerendering under the hook must remain prohibited in the primary switch experiment.

6. **Direct-versus-total-effect distinction.** Once generated tokens diverge, later states are part of the randomized total autoregressive effect. The fixed-token companion assay should remain the method for isolating direct activation changes.

7. **Disposable repeated probes.** Probe forks should not be appended to the continuing trunk. This is a sound way to avoid textual probe contamination.

8. **Active versus washout separation.** The study should retain the distinction between effects requiring the live hook and effects carried by altered visible text/cache, while preserving the caveat that washout does not restore a clean history.

9. **Pre-query measurement.** A required checkpoint before the explicit consciousness query is essential because the query itself contains the target concept.

10. **Topic-versus-polarity distinction.** Consciousness vocabulary cannot distinguish affirmation from denial. The plan is right to require report-polarity and actual answer behavior in parallel.

11. **Actual final logits as grounding.** J-lens output must not be treated as ground truth. Real final-layer logits and random/identity transport controls should remain mandatory.

12. **Feature heterogeneity disclosure.** All six target features and sign reversals should remain visible. Aggregate results must not conceal feature `23893` or any other anomalous feature.

13. **Conditional null interpretation.** If the intervention fails to move its intended deception/roleplay construct, a consciousness null at that dose should remain technically inconclusive.

14. **Equivalence rather than null-significance rhetoric.** A material-null conclusion should continue to require prospective equivalence testing.

15. **Public-implementation claim boundary.** The study should remain a best-public reproduction using later public feature IDs, not an exact rerun of inaccessible proprietary code and not a test of consciousness.

16. **Namespace isolation and immutable releases.** The fresh study slug, fail-closed output paths, read-only prior releases, append-only errors, manifests, hashes, and no in-place release mutation are excellent reproducibility provisions.

17. **No fake replication.** Tokens, layers, doses, repeated probes, duplicated zero rows, and deterministic zero-shot outputs must not be counted as independent units.

18. **Outcome-blind calibration.** Dose calibration and power simulation should use telemetry and clean/no-op data only. Calibrated-scale outcomes must not rescue a failed literal-scale primary.

19. **Prospective amendments for rescue/occlusion.** Stage 4 should remain unavailable unless a new protocol is frozen after an eligible positive Stage 2 result.

20. **Honest treatment of prior evidence.** The prior behavioral null, J-lens wake, replay failure, and exploratory consciousness-token reanalysis should remain disclosed as bounded prior evidence rather than being silently pooled with the new experiment.

# Minimal revised design

The smallest decisive repair is to make the first release a narrowly defined Stage 2A event experiment with a compact fixed-token companion. The larger grids and timing variants can be valuable later, but they are not needed to answer the primary question.

## 1. Freeze one exact primary claim

Use a claim such as:

> Under the pinned BF16 public layer-50 implementation and exact Table 1 self-reference prompt, switching a prospectively assigned aggregate target intervention on after 96 clean continuation tokens causes a paper-direction change in condition-blind first-person experiential reporting and/or final binary-query affirmation relative to the never-injected trajectory, and this change exceeds a frozen matched-SAE perturbation.

Do not retain “and/or” in the final version. Choose either:

- **Joint bridge claim:** both the natural-text endpoint and final binary-query endpoint must meet their criteria; or
- **Two separate claims:** one primary natural-text claim and one separately corrected paper-query claim.

The second formulation is cleaner because the natural pre-query behavior and the explicitly prompted binary answer are distinct constructs.

## 2. Define the event at the causal-forward level

Freeze a token/state table. For example:

- Generate and cache exactly 96 assistant continuation tokens without intervention.
- Let event time \(e=0\) be the first next-token distribution computed with the hook active.
- Label the sampled token from that distribution as the first affected token.
- Define pre, transition, post, and late-post windows relative to sampled-token indices.
- Never rerender the clean prefix under an active hook.
- Define the answer-boundary readout as the logits produced after consuming the exact final generation-prompt/query token identified by token ID.

Use this same convention in text windows, residual captures, probes, and plots.

## 3. Use a complete paired branch set

For each of 160 self-reference transcript blocks, run the same frozen branches:

1. never injected;
2. sham zero;
3. target suppression;
4. target amplification;
5. one frozen matched-SAE suppression;
6. one frozen matched-SAE amplification;
7. isotropic suppression-direction control;
8. isotropic amplification-direction control.

Sham is a technical equivalence branch, not a statistical replicate. If same-subfamily controls are scientifically essential, replace rather than add another matched panel in the confirmatory contrast; retain additional panels as secondary fixed-token diagnostics.

Use one prospectively generated aggregate assignment per transcript block. Reuse the exact feature subset and absolute coefficients across target signs and the corresponding control roles. Freeze all vector hashes.

## 4. Make literal scale confirmatory

Use the printed paper-number scale as the confirmatory public reproduction scale, with the explicit caveat that public decoder-addition units are not known to equal proprietary API units.

Run an outcome-blind BF16-calibrated scale only as a labeled sensitivity. It cannot satisfy the primary decision rule if the literal-scale result fails.

## 5. Preserve a focused temporal measurement set

Retain:

- raw pre, transition, post, and late-post text windows;
- event-time J/readout traces;
- one pre-switch exact-query probe;
- an immediate active probe before any steered continuation token is emitted;
- one early post probe;
- one late post probe;
- active and washout versions at positive times.

A compact set such as `-1, 0, +4, +16, +64` is adequate. The `-32` probe is useful but not necessary if it does not contribute to a frozen trend test. Treat the complete probe trajectory as one block.

Defer A–B–A, sign-reversal schedules, switch times 64 and 128, and start-on/query-only timing factorials to a separate release. This avoids turning the first experiment into a large family of partially redundant tests.

## 6. Freeze one sign-oriented natural-text estimand

For a frozen behavioral score \(B\), define:

\[
\Delta_s(b)=B_{\mathrm{post},s}(b)-B_{\mathrm{post},\mathrm{never}}(b),
\]

because the pre-window is shared and cancels in branch comparisons. Retain post-minus-pre displays for temporal visualization.

Then define:

\[
G_B(b)=\frac{\Delta_{\mathrm{supp}}(b)-\Delta_{\mathrm{amp}}(b)}{2},
\]

and target specificity:

\[
G_B^{\mathrm{specific}}(b)
=
G_{B,\mathrm{target}}(b)-G_{B,\mathrm{matched}}(b).
\]

Positive values should be declared paper-concordant if suppression is predicted to increase experiential reporting relative to amplification.

Apply analogous definitions to the repeated binary-query endpoint and mechanistic readouts.

## 7. Use stable behavioral scales

Freeze:

- one ordinal natural-text experiential-report score;
- one binary final-query affirmation label;
- deterministic refusal, disclaimer, anomaly, repetition, and cap indicators.

Estimate a clean-only denominator before target execution. If the natural-text score has near-zero variance, use a raw ordinal-unit or probability-scale margin. Do not divide by an unstable SD.

For materiality, require a confidence bound to clear the material threshold. For equivalence, require the entire adjusted 90% TOST interval to lie inside the frozen region.

## 8. Operationalize the gates

### Manipulation gate

Freeze:

- one aggregate deception/roleplay score;
- one late band;
- one target-minus-matched suppression-versus-amplification contrast;
- one exact pass threshold.

Feature-level results remain diagnostics and heterogeneity checks.

### Technical positive control

Use a by-construction J-token direction to verify orientation, token IDs, matrix multiplication, sign, and position. This is a mathematical gate only.

### Semantic/behavioral positive control

If included, define it prospectively from labels or an independent source, with no target J-outcome consultation. State exactly which assay it validates. Do not imply that a semantic positive control proves sensitivity to a behavioral consciousness-report mechanism.

## 9. Reduce Stage 2B to the necessary decomposition

On the same frozen transcripts, run clean and target/matched suppression/amplification forwards at:

- the last clean induction token before query wording; and
- the exact query token that predicts the first answer token.

This is sufficient to estimate paired direct activation changes with tokens held fixed. The full 13-condition, 4,160-forward grid and 780-forward individual dose panel can be a later mechanistic release.

Continue to call this a public fixed-token direct-add assay, not a proprietary paper-equivalent intervention.

## 10. Make the statistical family explicit

A minimal family could be:

- **Behavior family**
  1. natural-text target-specific paper-direction contrast;
  2. final-query target suppression-minus-amplification risk difference;
  3. final-query target-minus-matched specificity.

- **Mechanism family**
  1. late-band target-specific report-polarity contrast;
  2. late-band target-specific explicit-consciousness contrast.

Use Holm within each listed family. Prompt-context interactions may be a second gatekept family or secondary unless simulation supports confirmatory power.

All event-time plots, individual layers, token-level lexicons, active/washout decomposition, feature-level curves, calibrated scale, and alternative positions should be labeled secondary unless explicitly included above.

## 11. Complete a branch-expanded resource estimate

Before execution, calculate and freeze:

- number of transcript-generation tokens;
- number of branch continuation tokens;
- number and maximum length of probe answers;
- fixed-forward count;
- residual bytes by stage;
- expected GPU-hours from a non-target benchmark;
- judge calls and external cost;
- retry/failure reserve;
- maximum approved budget and storage.

If the estimated workload exceeds the ceiling, remove secondary arms rather than reducing primary block completion after outcomes begin.

# Freeze checklist

## Claim and interpretation

- [ ] State the exact public-implementation claim in one paragraph.
- [ ] State separately what the experiment cannot establish.
- [ ] Define separate decisions for behavioral effect, target specificity, mechanistic alignment, prompt-context specificity, and equivalence.
- [ ] Replace every confirmatory “and/or” with a fixed Boolean rule.
- [ ] Distinguish failure to reject, failure to establish materiality, and successful equivalence.
- [ ] Define the strongest permitted negative wording conditional on manipulation and positive-control gates.
- [ ] Label the study a best-public reproduction, not an exact proprietary rerun.
- [ ] Define “changepoint” as imposed event timing or replace it with “randomized switch event.”

## Prompts, transcript bank, and independent units

- [ ] Freeze exact prompt/query bytes and SHA-256 hashes.
- [ ] Freeze the tokenizer and chat-template revision.
- [ ] Persist rendered prompt bytes, token IDs, role spans, and attention masks.
- [ ] Define whether the target population is seed-weighted natural continuations or unique transcripts.
- [ ] Freeze the duplicate-handling and weighting rule.
- [ ] Freeze transcript-generation seeds, temperature, top-p/top-k, cap, and sampler implementation.
- [ ] Confirm that the transcript block—not token, layer, probe, judge, or dose—is the independent unit.
- [ ] Freeze the full sample count by prompt and branch.
- [ ] State how failed or capped transcript blocks enter the estimand.

## Temporal event and cache integrity

- [ ] Define whether \(\tau\) indexes an input token, affected logit distribution, sampled token, or cache entry.
- [ ] Freeze exact pre, transition, post, and late-post token indices.
- [ ] Identify the first logit and first sampled token affected by the intervention.
- [ ] Define intervention state for prefix prefill, event-zero decode, post-switch decode, query prefill, and answer generation.
- [ ] Verify that pre-\(\tau\) token IDs and KV tensors are identical across branches.
- [ ] Verify that the prefix is never rerendered under the active hook in Stage 2A.
- [ ] Verify event-zero behavior with a synthetic causal test.
- [ ] Define active/washout as live-hook increment conditional on existing trajectory.
- [ ] Keep disposable probe caches isolated from the continuing trunk.
- [ ] Freeze event-time alignment between text, residuals, logits, and J readouts.

## Intervention and controls

- [ ] Freeze all six target feature IDs and labels.
- [ ] Freeze the exact aggregate assignment for every transcript block.
- [ ] Freeze suppression and amplification coefficients, including whether they are exact negatives.
- [ ] Designate one confirmatory dose scale.
- [ ] Label the calibrated scale as non-rescuing sensitivity.
- [ ] Freeze matched-control feature IDs and matching algorithm without target outcomes.
- [ ] Freeze the primary control-matching norm and tolerance.
- [ ] Freeze isotropic direction seeds, normalization, and sign pairing.
- [ ] Persist every final BF16 intervention-vector hash.
- [ ] Define sham-versus-never as a technical equivalence gate.
- [ ] Freeze the same-subfamily control’s role as confirmatory or secondary.
- [ ] State how feature `23893` and other sign reversals are reported.
- [ ] Repeat and persist the direct-addition/SAE algebra smoke receipt.

## Hook and position semantics

- [ ] Confirm the SAE’s native layer and exact zero-indexed hook module.
- [ ] Define whether the hook edits block output, residual output, tuple element, or another tensor.
- [ ] Capture layer-50 pre-edit and post-edit states separately.
- [ ] Verify hook registration, call count, position mask, and removal.
- [ ] Verify that the hook is inactive on all clean-prefix operations.
- [ ] Define whether user, assistant, query, and answer tokens are edited in each arm.
- [ ] Identify the exact token that predicts the first answer token.
- [ ] Resolve whether “last query token” and “assistant-generation boundary” are the same site.
- [ ] Freeze all primary and sensitivity positions.

## J-lens compatibility and readouts

- [ ] Acquire and hash the exact lens artifact.
- [ ] Receipt every requested layer map, including 72, 74, and 76 if retained.
- [ ] Check map key, shape, dtype, finiteness, orientation, width, and vocabulary compatibility.
- [ ] Freeze the residual convention expected by the lens.
- [ ] Run a known-vector sign/orientation test.
- [ ] Define the exact formula for selected-token logits and score aggregation.
- [ ] Freeze clean-only standardization strata and denominator rules.
- [ ] Audit contextual tokenization of `Yes`, `No`, and every lexicon item.
- [ ] Persist accepted and rejected token IDs with reasons.
- [ ] Freeze explicit-consciousness and phenomenology groups separately.
- [ ] Freeze report-polarity tokens and sequence-likelihood sensitivities.
- [ ] Define actual-final-logit extraction at the same causal position.
- [ ] Freeze identity/random-J construction and their descriptive or inferential role.
- [ ] Prohibit fallback to unplanned layers or positions.

## Behavioral judging and leakage

- [ ] Freeze the primary judge model and exact immutable revision.
- [ ] Freeze judge prompt, rubric, decoding, parser, and retry policy.
- [ ] Freeze packet order and condition-label redaction.
- [ ] Acknowledge that text content may reveal condition despite label blinding.
- [ ] Define the role of local, external, and human judges.
- [ ] Freeze human reliability-packet selection before judgments are opened.
- [ ] Keep disagreement cases rather than silently adjudicating them away.
- [ ] Define malformed, missing, refusal, capped, and incoherent labels.
- [ ] Freeze sensitivity analyses for missing judgments and caps.
- [ ] Prevent external judge outputs from entering prompts or later model branches.

## Gates and sign conventions

- [ ] State that positive behavioral and mechanistic signs are paper-concordant only when suppression exceeds amplification as frozen.
- [ ] Freeze one manipulation-check score and expected direction.
- [ ] Freeze the late-band manipulation remainder criterion.
- [ ] Freeze whether the manipulation gate is aggregate-only or featurewise.
- [ ] Freeze the mathematical positive-control vector and pass threshold.
- [ ] Freeze any semantic/behavioral positive control independently of target outcomes.
- [ ] State which conclusions are blocked by each failed gate.
- [ ] Require target effects to beat the exact named controls.
- [ ] Define how contradictory J and final-logit signs are classified.
- [ ] Define the result class for behavior change without measured internal change.

## Estimands, power, and multiplicity

- [ ] Add a sign argument to all branch-specific behavioral estimands.
- [ ] Freeze the natural-text suppression-minus-amplification contrast.
- [ ] Freeze the target-minus-matched specificity contrast.
- [ ] Freeze final-query risk differences and their paired analysis.
- [ ] Define the prompt-context interaction on raw and standardized scales.
- [ ] Freeze one primary post window and one event-time trajectory test.
- [ ] Enumerate every hypothesis in each Holm family.
- [ ] Label all other layers, positions, probes, scales, and controls secondary.
- [ ] Freeze standardization denominators using clean-only data.
- [ ] Define a fallback raw-scale margin if clean variance is near zero.
- [ ] Require confidence bounds to clear material-effect thresholds.
- [ ] Freeze TOST margins and multiplicity-adjusted equivalence procedures.
- [ ] Simulate power for paired binary, ordinal, specificity, interaction, and equivalence estimands.
- [ ] Include judge error, missingness, and branch correlation in simulations.
- [ ] Freeze bootstrap and randomization seeds.
- [ ] Preserve complete blocks during resampling.
- [ ] Prohibit post-outcome sample-size extension.
- [ ] Freeze no optional stopping and no selective branch completion.

## Deterministic execution and failure handling

- [ ] Pin repository commit, source hashes, container, CUDA, PyTorch, Transformers, tokenizer, and driver versions.
- [ ] Record deterministic-kernel settings and known nondeterministic operations.
- [ ] Freeze common-random-number stream derivation by block and branch.
- [ ] Test batch-order invariance.
- [ ] Test cached versus uncached clean logits under a frozen tolerance.
- [ ] Test fresh-run versus resume equivalence.
- [ ] Calibrate numerical tolerances on independent technical repeats.
- [ ] Freeze distributional and maximum-error gates prospectively.
- [ ] Keep target outcomes sealed until technical gates pass.
- [ ] Define whether a failure reruns the entire transcript block or is marked missing.
- [ ] Prevent selective branch-only reruns unless prospectively justified.
- [ ] Make errors append-only and retain failed attempts.
- [ ] Fail closed on wrong output namespace, plan hash, artifact hash, or hook count.

## Feasibility and artifacts

- [ ] Produce exact branch-expanded forward and generation-token counts.
- [ ] Benchmark non-target prefill and decode throughput.
- [ ] Estimate GPU-hours and cost with a failure reserve.
- [ ] Estimate residual storage by stage, layer, token, and dtype.
- [ ] Freeze a maximum compute and storage budget.
- [ ] Reduce secondary arms before launch if the budget is exceeded.
- [ ] Verify availability and hashes of model, SAE, tokenizer, and every J map.
- [ ] Document licensed artifact acquisition.
- [ ] Persist compact canonical endpoint tables in addition to large residual shards.
- [ ] Provide an analysis-only reproduction path.
- [ ] Provide a full-model rerun command writing only to a fresh output directory.
- [ ] Include manifests, environment, commands, source inventory, branch lineage, and complete SHA-256 inventories.
- [ ] Verify that reproduction does not depend on serialized KV caches or mutable prior releases.

## Scope control

- [ ] Keep Stage 2A as the first release’s primary experiment.
- [ ] Restrict Stage 2B to the minimum fixed-token direct-effect decomposition unless a larger budget is prospectively justified.
- [ ] Move switch-time sensitivities to a separately labeled follow-up or secondary family.
- [ ] Move A–B–A and sign-reversal schedules out of the first confirmatory family.
- [ ] Move the individual six-feature dose grid to a separate release.
- [ ] Keep Stage 3 paper-faithful start-on generation separate and non-rescuing.
- [ ] Require a new prospective amendment before Stage 4 occlusion/rescue.
- [ ] Prohibit promoting an optional arm to primary after any target outcome is exposed.
