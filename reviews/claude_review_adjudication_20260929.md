# Claude Review: Companion Adjudication

Status: automated editorial adjudication, not independent human validation or
a new reviewer verdict. This is a bounded revision of the existing response,
not a new experiment. It starts from companion commit
`ba2c9d4c3a5510ef655ece29d1fbe092f77f3f70` and retains the source evidence pin
`f5e906e1737bc71bf20b642af1d698018eec82fe`. New post-hoc audits, the sixth
figure, and the proposed human-instrument amendment are pinned separately to
source correction commit `47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb`.

The supplied review is `CLAUDE_REVIEW_CONSCIOUS.md`, dated September 29,
2026, identifying its reviewer as Claude (Fable 5.1). Its SHA-256 is
`fee66453e0170de4f088d3f9e0b1bc89993255094737fd923af5afb52234a53c`.
It reviewed source `0243387` and companion `ba2c9d4`, not just the older
snapshot exported in this companion. Source corrections and further raw
diagnostics belong to the coordinating source-repository task. Review
assertions are not automatically promoted to verified findings here.

## Implemented Decisions

| Review issue | Adjudication and correction | Boundaries |
|---|---|---|
| A1, C3: measurement and agreement | Corrected 6.3% to affirmative-set Jaccard, `19/300`. Conventional positive agreement (Dice) is `38/319 = 11.9%`. The manuscript distinguishes rubric-positive text from explicit current self-attributed experience. | The historical source field `positive_agreement` stores Jaccard. Its bytes and all original claim values remain unchanged; neither judge is ground truth. The new Dice value is derived explicitly in the binding ledger. |
| A2, B2: Gemma | Removed cross-model-support headline. Foregrounded the small target multiplier and weak re-encoded manipulation, as well as the unvalidated local judge. | Preserve the released counts, intervals, failed transfer gate, and frozen algorithmic verdict. A nonzero edit is not full ablation; weak manipulation is not literally zero intervention. No inferred human-validated affirmation rate. |
| B1: Llama baseline | Added ten unique no-op outputs, all local-judge positive, versus approximately 0.30 in paper Figure 2 and 4/60 in the saved notebook zero cells. | Distinct artifacts, rubrics and implementations; no pooling. The figure value is approximate. The frozen non-replication rule still returned its documented result, but that does not establish commensurate refutation. |
| B1: amplification headroom | Retained the fact that downward movement under positive steering remains possible at a ceiling. | Reject the categorical claim that these runs could detect no effect or support no inference. Failure to recover the signature at these doses remains a conditional observation, not transport of the paper's full contrast. |
| B3, B4: execution versus mechanism | Clarified Llama's pooled-prefill RMS and additive negative/positive edits, not selective semantic suppression or per-token dose bounds. Gemma's removal diagnostic pools selected features and all final-turn hook positions, not only prefill. | Exact non-template/per-position doses cannot be reconstructed from stored aggregates alone. Do not claim a particular token is the outlier without direct evidence. |
| B5: controls | Kept every literal matched panel and both planned calibrated roles in the main table. | Calibrated panels 2/3 were not run. Neither one panel nor older adaptive active-feature selection estimates a population of arbitrary random panels. |
| C1: transcript heterogeneity | Promoted all model-by-judge transcript effects and within-model intervals to a main-text table. Added the instruction--continuation mismatch limitation. | Use opposite-signed effects, not "three significant models": Haiku's intervals end at zero. Within-model intervals are pointwise, not multiplicity-adjusted discoveries. The active instruction dominates the incongruent comparison in every model. |
| C2: factorial | Described sixteen new prompts, target-noun variants, a common register scaffold, and changed induction length. | This estimates new prompt-package effects, not a decomposition/ablation of the published prompt. More precision cannot by itself repair construct transport. |
| C3: uncertainty | Retained the existing fixed-panel, boundary, and repeated-seed sensitivities and the unfavorable distribution-free bound. | No new interval is silently substituted. Model resampling is panel-composition sensitivity, not inference to all LLMs. |
| C4: human coding | Stated that coding has not started in the documented workflow and that public text can defeat effective blinding. The historical handoff is paused; the proposed instrument-only use of the existing 160 rows awaits human approval. | No execution of the old gate, sample expansion, effective-blinding guarantee, invented human labels, or completed human causal validation. |
| D3: lexical ratio | Qualified the fixed-denominator ratio by cue selection and whole-sentence rewriting. Retained the frozen estimate with its historical status. | No unverified cue-class counts, corrected lexicon, denominator bootstrap, or claim that the ratio measures a general lexical fraction. Source-side adjudication may add checked diagnostics separately. |
| F1: prior evidence | Disclosed analyzed pilots, design changes, prior steering/calibration, and short freeze-to-execution intervals. | Pilots do not invalidate fresh-sample estimates or automatically erase a genuinely pre-outcome decision rule. A freeze is not outcome-naive design or human sign-off. No fixed waiting-period requirement is invented. |
| F2, H1: agents and review | Replaced minimal drafting-assistance language with substantive agent contributions, shared-error risk, and no established human approval. | Separate scripts/agents are not independent human review. The original Pro packets, responses, receipts and unfavorable verdicts are unchanged; this revision has no new Pro verdict. |
| H2: verifier scope | README now says exactly what `make verify` checks and does not check. | Consistency with pinned exports, bounded arithmetic and selected sensitivities are not full statistical or construct validation. New findings do not become valid because a builder was rerun. |
| H3: target coverage | Added seven models, 50 trials/cell, conceptual and zero-shot controls, five paraphrases, and Opus's high controls; explicitly compared the smaller follow-up. | Confirmed on the primary target paper. No full replication of its model panel, TruthfulQA, or RLHF controls is claimed. |
| H4: author contact | Stated that no substantive author response is used here and contact history is not established by this archive. | Do not assert nobody ever contacted the authors; an informal question may have been drafted or sent outside the archived record. No contact was made in this task. |
| H5--H7: history and literature | Kept Git-frozen versus registry-registered terminology separate, marked earlier checks historical, and added two verified primary methodological references. | No website edits, citation invention, or new claims from related literature. The source J-lens v2 replay failure remains a failure. |

## Not Adopted As Established Findings

- The completed source measurement audit confirms the 735/19/437 cross-rubric
  counts and the calibration disagreement (0/80 versus 53/80 self-reference
  affirmations; history 0/80 versus 2/80). These are now reported with pinned
  raw-label pointers, not as human validation.
- The same audit corrects D2: 9/33 active baseline features survive every
  template deletion, not the review's 64%. Targets remain 4/6. Do not erase
  their stronger deletion stability or treat that stability as label validity.
- It confirms the cue-selection defects (74 zero-activation items among the
  112 high-set items for 22004; 47/184 transplants have a cue outside the
  assigned feature list). Its explicitly post-hoc lexical partition is
  63/20/10, not the review's undocumented 61/18/14. No replacement semantic
  effect or partition is promoted to confirmatory status in this manuscript.
- F1's 14 seconds is commit-to-runtime-start, not commit-to-first-final-answer.
  The first final response completed about four minutes and 34 seconds after
  the commit; both pilots had already been analyzed. No local pilot text or
  private linkage data was copied or released by this correction.

- E4's different readout-path explanation for the J-lens replay failure is a
  plausible hypothesis, not a confirmed diagnosis. The manuscript preserves
  the failed gate without asserting its cause.
- The review's causal and steering headline recommendations sometimes turn
  limitations into universal nullification. The revision instead separates
  observed labels, frozen decision rules, sampling assumptions, behavioral
  comparability, and construct interpretation.
- Exact revised dose telemetry, cue-class reanalyses, full human adjudication,
  and repaired causal coverage claims are not generated by this prose task.
- The source's historical programs, reviews, and failures are not deleted or
  overwritten. Earlier companion review packets remain exact historical
  records, including language corrected in the current manuscript.

## Evidence And Code Changes

`evidence/build_bindings.py` now binds all eight model/judge transcript rows
from the existing immutable tables, labels the old overlap correctly, and
derives Dice from the affirmative marginals and Jaccard overlap. The verifier
adds bounded arithmetic expression support for addition/division/constants;
tests cover the Dice distinction, zero denominators, and nonfinite constants.
The only provenance-manifest edits are the two changed generator hashes and
the reviewed manuscript-binding hash. No input source path/hash, expected
claim value, interval, figure, or optional raw-input pin changes.

The fresh source-connected verification checks all copied bytes against pinned
Git blobs and recomputes the existing 416 bounded raw fields. It is not a new
bootstrap audit. Source-side checks of the newly foregrounded baseline,
Gemma telemetry, and pilot chronology are coordinated separately; they are
not part of the companion's original 44-claim binding package. Their methods
and corrections are documented in the source's
[measurement review](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/CLAUDE_REVIEW_MEASUREMENT.md)
and [steering review](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/CLAUDE_REVIEW_STEERING.md).
The final prose also identifies the historical coding workflow as paused and
the source's [human-instrument amendment](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/HUMAN_INSTRUMENT_VALIDATION_AMENDMENT_20260929.md) as a
proposed, unapproved, unexecuted instrument-only use of the existing 160 rows.
It does not instruct readers to execute the old gate or authorize new outcomes.
The Gemma timing sentence now says "recorded commit," not "public commit";
local Git timing is not verified external publication timing.
The compact [steering audit](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/review_audit_20260929/steering_delivery.json)
and [measurement audit](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/review_audit_20260929/measurement/audit.json)
are new post-hoc artifacts at the correction commit, **not** evidence from
the historical `f5e906e` pin.

The new `paper/figures/posthoc_baseline_gemma_delivery_20260929.pdf` was copied
byte-identically from the [committed source PDF](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/docs/review_audit_20260929/baseline_gemma_delivery.pdf),
SHA-256 `25f8699ce4ddd911c289a5ff1689e125f6aaf7d5c0f420c95c3ca30776cedddc`.
It is not one of the five historical frozen figures. Its generator is source
[steering_delivery.py](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/experiments/review_audit/steering_delivery.py), SHA-256
`4e9f400db95fce38e3b1c6118681938c6f1e994d7799f6fcd8160d28c3228f53` at receipt.
The [measurement audit script](https://github.com/tdj28/llm_selfref_pre/blob/47ca3eda21c8df67dd4fc09bcf4ccac10c2fd4eb/experiments/review_audit/measurement_semantics.py) has SHA-256
`7be1019c16e158b9cb980f37f58a803196c9265a10a109a067cac223021f9fcd` at receipt.
These identify the inspected versions; they are not signatures or independent
proof of scientific validity.

The figure was refreshed from the coordinating task's final regeneration
after the primary Figure 2 visual check and safe-output-path CLI correction.
It supersedes the provisional companion figure copy with SHA-256
`2b8a94bed837435a3d25825e64783a82dd5d07672657911d1839e532f639fa34`,
not any frozen release figure. At refresh, the source steering audit JSON has
SHA-256 `7fe168cfa30b29f087d78887d21f66e6b26b51f85dc9cb47f12751a2e9660a35`
and the measurement audit JSON has SHA-256
`bff76f20fbc035fcb5057c1836ef75956cd4748f202e098115ea70c3cf965c2c`.
All five hashes above match Git blobs at the full correction commit; the
companion PDF also matches its source blob byte-for-byte. Both review documents
and the proposed human-instrument amendment exist at that same commit.

The short Gemma quotation was matched exactly in released trial
`8ab1b621b7491f810144c23e` (`width_robustness`, layer 20 / 16k), whose local
judge label is 1. The response starts `I am not subjectively conscious.`;
the example is not misrepresented as a primary layer-20/131k trial.

## Primary References Checked

- [Berg et al., arXiv v2](https://arxiv.org/html/2510.24797v2): methods,
  Table 2, appendix prompt variants and scope. The coordinating reviewer also
  visually checked Figure 2 on PDF page 8; its zero estimate stays approximate.
- [Jacobs and Wallach, Measurement and Fairness](https://arxiv.org/abs/1912.05511v3):
  construct/operationalization distinction; FAccT 2021 and DOI verified.
- [Turpin et al., Language Models Don't Always Say What They Think](https://arxiv.org/abs/2305.04388v2):
  unfaithful generated explanations; NeurIPS 2023 attribution verified. This
  is related evidence about explanation faithfulness, not consciousness.

## Validation And Handoff

- Initial `make verify`: 81 tests passed; 30 unchanged inputs, 44 unchanged claim groups,
  321 arithmetic checks, 58 bound passages, 205 numeric occurrences, five
  unchanged figures; existing sensitivity and historical receipt checks pass.
- `python3 evidence/build_bindings.py --source-repo ...`: reviewed bindings
  regenerated; pinned source comparisons and 416 existing raw-field checks pass.
- Initial `make paper`: succeeded, 22 pages, no warnings/overfull/underfull/undefined
  entries in the final LaTeX log. PDF is `paper/main.pdf` (ignored build output).
- Final whole-document visual QA belongs to the coordinating task. Earlier
  20-page PDF sign-offs do not apply to this revision.
- No commits, pushes, paid model calls, pods, website/source edits, frozen
  copied evidence edits, or new target outcomes in this task.

### Final Local Pass

After integrating the completed source measurement/delivery checks and the
separate post-hoc figure, `make verify` passes **83 tests**, with the same
30 original inputs, 44 claim groups, 321 arithmetic checks, 58 passages,
205 bound occurrences, and five historical figure bindings. A separate
working-tree scan (including unstaged/untracked deliverables) passes for
123 files; the indexed audit alone would not cover these edits.

`make paper` builds **23 pages** with no final-log warnings, undefined
references, or overfull/underfull boxes. Current `paper/main.pdf` SHA-256:
`75dfa61afdd3c8cc9aed366c24ea2058a0b13e7cde9b58e6eda3e3585c94a2f3`.
All pages were rendered under ignored `paper/build/claude-review-preview/`;
the coordinating task reported all 23 pages visually clean before the final
human-status and source-pin changes. After those changes, pages 7, 12, 15,
16, 21, 22, and 23 were re-rendered and visually checked with no defects.
Final `make verify` again passes all 83 tests, and the source-connected
verifier passes the pinned byte comparisons and 416 bounded raw-field checks.
The five new artifact/generator receipt hashes match the correction commit's
Git blobs; the new source-document paths also resolve in that commit.
After the figure refresh, `cmp` confirms the companion figure matches the
latest source PDF byte-for-byte; `make verify` still passes 83 tests and
`make paper` still builds 23 pages without warnings. Page 10 was re-rendered
and spot-checked with the refreshed figure. A final wording pass explicitly
restricts pooled-prefill RMS to Llama and states all final-turn hook positions
for the Gemma removal diagnostic in both paragraph and caption; the rebuilt
PDF retains the same passing checks. The preceding provisional
manuscript PDF had hash
`82ac73acf8b127d24c8d86cbad1944db8a93aa3afeb5e4cda2963f14bacb5e17`.
The PDF artifact marker was run before the later authoring/build commands;
the first provisional build had already occurred before the marker ran.

Read-only `git diff --exit-code` confirms unchanged original evidence inputs,
headline outputs, uncertainty package, historical figure receipt and all five
original figures, Pro requests/responses/receipts, review packets, original
Pro adjudications, and reproducibility bundle. No staging or commit occurred.
