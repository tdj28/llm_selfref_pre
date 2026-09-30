# Verdict

**Stage 1 addresses the right immediate question: can this public assay deliver and measure a meaningful intervention? It cannot yet be frozen.** The proposed diagnostic could support a bounded assay-feasibility conclusion—not a refutation of Berg, a demonstration of truthful introspection, or equivalence to the proprietary intervention.

The strongest elements are the separation of requested from realized edits, literal zero control, locked validation texts, fixed target identities, explicit claim limits, and refusal to rescue failed gates with outcome-selected substitutions. Preserve them.

The smallest useful repair is to make failures distinguishable, replace the ambiguous behavioral-control gate with a precisely specified diagnostic, and schedule spending so that intervention qualification precedes the large baseline inventory. Stage 2 remains unauthorized and should not be implemented as an automatic continuation.

I treat the historical results and test receipts as disclosed evidence. The supplied excerpts do not establish real-model efficacy, final integration correctness, or affordability at measured throughput.

NOT READY TO FREEZE

# Blocking findings

## B01 — The candidate behavioral control cannot carry the proposed positive-control interpretation

- **Severity:** Blocking; definite interpretation defect and missing contrast specification.
- **Location:** “Behavioral positive control”; Artifact 2, feature `7688`, “JSON format with no extra text.”
- **Why it matters:** An activation-derived label is not evidence that steering this coordinate causes JSON output. Failure could mean an inaccurate causal label, ineffective coordinate manipulation, an unsuitable task, or insufficient dose—not necessarily a broken intervention pipeline. Moreover, “zero, suppression, and two amplification doses” leaves the gate’s exact contrast unspecified. Selecting whichever amplification dose produces the favorable effect would invalidate the gate.
- **Minimum fix:**
  1. Call `7688` a **candidate causal control**, not a known-working SAE positive control.
  2. Within the existing 80-generation allocation, replace one amplification arm with an **unsteered explicit-JSON-instruction arm**. Use the same 20 underlying tasks across zero, instruction, suppression, and one amplification arm.
  3. Freeze the amplification strength in advance, or use a deterministic selection rule based only on independent teacher-forced telemetry. Specify exactly which dose is used for suppression.
  4. Make amplification-minus-zero the sole candidate behavioral gate; keep suppression descriptive. Freeze the paired interval method, treatment of ties and invalid responses, and the proposed effect threshold before generation.
  5. Treat instruction-minus-zero as a task/endpoint responsiveness check, not validation of SAE steering. If zero is already at ceiling, report inadequate endpoint headroom.
  6. Candidate failure may conservatively block expansion, but must not block publication or completion of an already budgeted target-delivery diagnostic. No fallback feature.
- **Claim affected:** Whether a behavioral-control failure diagnoses pipeline failure, and whether a pass demonstrates anything beyond controllability of this particular formatting endpoint.

No supplied artifact establishes a known-working SAE direction. The revision should acknowledge that limitation rather than manufacture one.

## B02 — The gate definitions do not yet separate availability, delivery, coordinate geometry, and downstream damage

- **Severity:** Blocking; missing operational definitions.
- **Location:** “Proposed validation gates”; “select the lowest common lambda”; Artifact 2, open risks 2–4.
- **Why it matters:** These are different failure modes with different conclusions:
  - insufficient natural activation or amplification opportunities;
  - BF16 loss of a requested residual edit;
  - a faithfully delivered decoder edit that does not produce the intended encoder-coordinate change;
  - effective coordinate changes requiring excessive perturbation;
  - acceptable perturbations that damage language modeling.

  A single pass/fail summary would obscure those distinctions. Likewise, 100 active tokens concentrated in one text provide very different evidence from broad exposure across validation texts. The draft also leaves aggregation, quantile edge cases, and some dose-comparison rules unresolved.
- **Minimum fix:** Freeze a compact gate specification containing:
  - Exact active/nonzero definitions, positive-activation quantile calculation, and behavior when calibration has no positive activations.
  - The aggregation unit and denominator for every gate, separately for suppression and amplification and for targets versus each panel. Do not pool directions to achieve a pass.
  - A fixed minimum number of distinct validation texts contributing opportunities for each coordinate, alongside the 100-token feasibility criterion. Treat texts—not tokens—as the independent units for any uncertainty summaries.
  - A fixed common-dose policy. The simplest is to select the lowest target lambda that passes calibration, lock it, and require panels to qualify at that same lambda. If independently calibrated panel strengths are intended instead, describe the later contrast as an **achieved-dose-matched operator comparison**, not an identical-lambda comparison.
  - Separate requested-versus-delivered residual metrics from delivered-versus-achieved coordinate metrics. On a small fixed diagnostic subset, compare re-encoding of the ideal FP32 requested state with re-encoding of the actual BF16 state. This is a diagnostic reference, not a replacement production operator.
  - Mutually identifiable failure codes for availability, numerical delivery, coordinate efficacy, bounded norm, language preservation, and comparator availability. Multiple codes may apply.
- **Claim affected:** “Substantially changed the accepted coordinates,” successful suppression/amplification, and any later target-versus-panel comparison.

The thresholds can remain engineering choices. They need not be empirically optimized to become operationally exact.

## B03 — The intervention arithmetic and selected/full encoder policy are not frozen

- **Severity:** Blocking; definite documentation mismatch and missing numerical policy.
- **Location:** Stage 0, “native BF16 intervention”; Artifacts 2–3, FP32 decoder product/addition and proposed `0.02` selected/full tolerance.
- **Why it matters:** The supplied implementation describes an FP32 decoder product and residual addition followed by one BF16 cast, with native-BF16 re-encoding. That is more specific than—and not necessarily numerically equivalent to—the brief’s shorthand. Selected versus full encoder matrix shapes can also alter BF16 rounding. An absolute discrepancy tolerance has no defensible meaning without relating it to activity, quantiles, dose selection, and pass/fail decisions.
- **Minimum fix:**
  - Freeze the exact arithmetic, hook location/index convention, encoding convention, and diagnostic precision in one authoritative operator specification.
  - Designate which encoder path governs quantiles, matching, activation availability, and coordinate-efficacy gates.
  - Check selected/full agreement on a fixed real-model qualification shard using the final GPU environment. Require agreement in consequential decisions, not merely average numerical proximity.
  - If discrepancies change activity classification, selected lambda, panel eligibility, or gate status, halt and resolve them before collection; do not average the paths or select the more favorable one.
  - Freeze any clipping behavior explicitly. It must not silently change the stated equations.
- **Claim affected:** Reproducibility, actual delivered dose, and historical implementation comparability.

The reported 95 passing local tests are useful evidence of prototype behavior. They do not close this real-model numerical question.

## B04 — The spending sequence does not guarantee that the most informative diagnostic happens first

- **Severity:** Blocking for launch; missing scheduling policy, with a proportionality judgment.
- **Location:** 290 baseline trials, 80 behavioral-control generations, three comparator panels, and modern judging of all 370 responses.
- **Why it matters:** The primary mechanical uncertainty can invalidate the proposed follow-up before most of this inventory is useful. Running the eight-cell baseline grid or judging mundane formatting outputs first risks spending the cap without establishing whether the target intervention is deliverable. Conversely, a ceiling baseline or failed modern judge should not automatically erase the value of teacher-forced intervention diagnostics.
- **Minimum fix:**
  - Define a mandatory core and a fixed-priority optional remainder.
  - Put real-model numerical qualification and target teacher-forced calibration/validation before bulk baseline generation.
  - Retain the designated 80-trial primary baseline as the core behavioral measurement. Defer the other seven 30-trial cells unless the explicit objective includes diagnosing those historical protocol differences and the measured budget permits the complete prefrozen remainder.
  - Remove modern experience-rubric judging of formatting-control generations; it does not serve their endpoint.
  - Defer fresh comparator-panel qualification until target delivery has passed. Panel failure blocks specificity readiness, not the target-delivery conclusion.
  - Make gate failures branch-specific: measurement failure stops that measurement path; baseline headroom failure blocks the proposed symmetric follow-up; delivery failure blocks mechanistic expansion.
  - Reserve enough money and time for retrieval, validation, and a minimal diagnostic release before authorizing each batch.
- **Claim affected:** Whether Stage 1 is the smallest useful diagnostic within $200, and whether a failed run leaves an interpretable result rather than an unfinished inventory.

# Important non-blocking findings

## I01 — Coordinate efficacy remains distinct from semantic selectivity

- **Severity:** Important, non-blocking.
- **Location:** “When we substantially change the accepted deception/roleplay coordinates”; non-target activation telemetry and matched panels.
- **Why it matters:** Successful re-encoded suppression establishes a coordinate-level manipulation under this SAE. It does not establish selective removal of deception or roleplay as a psychological or computational capability. Norm-matched panels and non-target telemetry help characterize specificity but cannot supply that semantic ground truth.
- **Minimum fix:** Use “accepted deception/roleplay-associated SAE coordinates” in conclusions. Report off-target changes alongside coordinate efficacy. Do not add a broad semantic benchmark campaign.
- **Claim affected:** Semantic ablation and feature-specific mechanistic explanations.

## I02 — The eventual both-turn contrast is a total conversational effect

- **Severity:** Important, non-blocking.
- **Location:** Stage 2, “Regenerate each arm’s induction” and steering both turns.
- **Why it matters:** An altered induction can change the answer through ordinary transcript conditioning. The planned contrast legitimately includes that pathway, but cannot isolate direct changes to reporting from changes mediated by the model’s preceding text.
- **Minimum fix:** Name the estimand a **total two-turn report-label effect**. Do not add a mediation study now. If direct answer-stage reporting becomes the claim later, it requires a separately designed intervention.
- **Claim affected:** Direct introspective/reporting mechanisms versus total conversational effects.

## I03 — Stage 2’s power statements should remain conditional planning, especially for specificity

- **Severity:** Important, non-blocking for Stage 1.
- **Location:** “Precision And Power”; specificity margin `0.15`.
- **Why it matters:** The primary contrast’s planning approximation does not establish power for excluded advantage or equivalence against three fixed panels. Common-random-number pairing may help, but its actual covariance is not guaranteed.
- **Minimum fix:** Preserve the requirement for exact-method simulations before any separately authorized Stage 2 freeze. Include unfavorable covariance, missingness, and invalid-delivery scenarios. If specificity is weakly powered, narrow its evidential role rather than automatically increasing the study.
- **Claim affected:** Exclusion of a material target advantage and practical comparability.

# What should remain unchanged

- **Fixed six target identities and predicted sign.** Do not reopen feature identification to explain a null.
- **Literal zero no-op**, rather than reconstruction masquerading as zero.
- **Requested-versus-realized edit telemetry**, with rounded-away requests counted as failures.
- **Calibration/locked-validation separation**, with no report-label selection of doses, features, or panels.
- **Residual-preserving algebra acknowledgment:** equivalent additive formulations are not independent mechanisms.
- **Controls required to achieve coordinate changes**, not merely match residual norms.
- **Separate rubric-specific reporting**, fixture gates, condition-blinded judging, and explicit rejection of automated judges as human ground truth.
- **Stage 1’s permanent diagnostic status**, public failure reporting, and separate authorization for Stage 2.
- **Historical failed gates and results preserved unchanged.**
- **Hard spending limits, unresolved-request stops, and explicit retrieval/deletion requirements.**

# Minimal revised design

1. **Freeze the diagnostic decision tree locally.**  
   Resolve B01–B04; complete integration, scoring, gate-analysis, and lifecycle tests. Publish a compact machine-plan summary and executable freeze. Keep independent source/schema checks local.

2. **Qualify the numerical path cheaply, then on a tiny fixed 70B shard.**  
   Verify zero identity, hook timing, cached/prefill consistency, selected/full encoder decisions, arithmetic, memory, and measured cost. Stop on invalid bookkeeping or unresolved numerical discrepancies before bulk execution.

3. **Run target teacher-forced qualification first.**  
   Preserve the 48 calibration/48 locked validation split and candidate lambdas. Select by telemetry alone, validate once, and publish the failure decomposition. If calibration finds no eligible dose, do not generate a behavioral study to compensate.

4. **Run the core measurement branch.**  
   Gate each rubric before its bulk judgments. Run the designated 80-trial primary baseline without switching cells. A headroom failure blocks the proposed symmetric follow-up, not the already valid intervention characterization.

5. **Run the bounded formatting diagnostic, if technically eligible.**  
   Use 20 paired tasks and the four arms specified in B01: zero, explicit instruction, suppression, and one amplification dose. Score mechanically. Report instruction responsiveness and candidate-coordinate efficacy separately.

6. **Only then spend on handoff refinements.**  
   Qualify the three comparator panels and, if explicitly retained and affordable, the remaining baseline cells in a frozen order. Neither is a reason to exceed the cap or change the core protocol.

7. **Release and stop.**  
   The minimum useful release is: operator/source provenance, qualification status, target availability and delivery summaries, gate-specific failure reasons, completed measurement summaries, and actual spending. Budget truncation is **incomplete**, not scientific failure. Nothing automatically launches Stage 2.

Interpret outcomes narrowly:

| Result | Interpretation |
|---|---|
| Requested residual edit is not delivered | Numerical/operator failure |
| Residual edit is delivered but coordinate change is insufficient | SAE/operator geometry or coordinate-efficacy failure |
| Too few eligible positions/texts | Exposure failure in these fixtures |
| Coordinate gate passes but norm/loss gate fails | Intervention outside the prespecified acceptable envelope |
| Instruction check passes, candidate steering fails despite verified delivery | Candidate causal-control failure, not general pipeline failure |
| Baseline headroom fails | Proposed symmetric report assay unsuitable; mechanical findings remain usable |
| All core gates pass | Readiness evidence for seeking a separately frozen follow-up—not a target behavioral result |

# Freeze checklist

- [ ] **B01:** Candidate and instruction-control interpretations, exact arms/doses, primary contrast, paired interval, scorer, and invalid-response policy frozen.
- [ ] **B02:** Gate denominators, text coverage, quantile edge cases, dose/panel policy, and failure codes fixed.
- [ ] **B03:** Exact arithmetic and authoritative encoder path documented; decision-relevant selected/full discrepancy policy fixed.
- [ ] **B04:** Mandatory/optional schedule, branch-specific stopping rules, and retrieval reserve fixed.
- [ ] Exact model, tokenizer, SAE revisions, layer convention, serialization, and classifier prompts verified locally against their cited sources.
- [ ] Final integration and independent plan/code checks completed; prototype test receipts not represented as final-system validation.
- [ ] Outcome-free qualification protocol and first-batch audit requirements frozen before paid execution.
- [ ] Real-model memory, throughput, numerical parity, and projected completion cost checked before bulk dispatch.
- [ ] Fixed inventories, missingness/cap handling, seed rules, judge masking, and no-retry/resume policies bound to the executable freeze.
- [ ] Compact qualification and audit attestations retained for review; raw rows and source-level verification remain in the local audit workflow.
- [ ] Diagnostic-only claims and minimum partial-release requirements approved.
- [ ] Stage 2 and registry submission remain disabled pending separate explicit authorization.
