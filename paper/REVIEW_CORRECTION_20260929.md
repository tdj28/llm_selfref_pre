# Historical Manuscript Correction: 2026-09-29

This dated correction responds to the owner-supplied Claude AI review of
2026-09-29. It is an agent-produced source-manuscript correction, not independent
human peer review. The active paper-specific response is maintained in the
[companion repository](https://github.com/tdj28/berg2025-response).

## Scope

This manuscript correction changes `paper/main.tex`, `paper/references.bib`,
and this note. No frozen data, computed result table, analysis code, figure asset,
release manifest, or decision rule was changed. Historical verdict strings and
release names remain in the record. No new model calls, paid API use, GPU work,
human annotation, or author contact was performed.

## Corrections

- **Measurement (A1/C3):** The abstract, discussion, and conclusion distinguish
  paper-rubric positives from validated explicit consciousness assertions.
  Among 735 responses positive under both paper-rubric judges, 19 are `affirm`
  under both construct judges, and 437 are uncertain under at least one.
  The construct judges mark 19 and 300 positives,
  with intersection 19 and union 300. Thus 6.3% is intersection-over-union
  overlap, not positive agreement; positive agreement is `38/319 = 11.9%`.
  Exact-calibration construct counts are 0/80 versus 0/80 for the OpenAI judge
  and 53/80 versus 2/80 for the Anthropic judge.
- **Llama (B1):** The 60 zero-steering rows contain only ten unique seed/output
  cases, all paper-rubric positive. The paper's Figure 2 has an approximately
  0.30 zero-steering rate. This is a behavioral comparability failure and leaves
  no observed headroom for a suppression-driven increase. Amplification could
  lower the rate, but the observed rates remain 48/50 at the literal scale and
  47/50 at the calibrated scale. The computed non-replication verdict is
  preserved as a historical rule output, not promoted as a precise refutation.
- **Gemma (B2):** Primary target `alpha = 0.03451248`; medians of final-turn
  per-trial selected-activation means are 10.5181395 before intervention and
  10.1527975 after re-encoding. Each mean pools selected features and **all
  final-turn hook positions**, not prefill alone. The reduction is approximately
  3.5%, not full ablation. Gemma uses BF16 without quantization, not NF4. The
  original effect and verdict are retained with that limitation.
  Local-judge positives are not assumed to be assertions, and local nonpositive
  layer/width sensitivities are not described as evaluator-universal.
- **Telemetry boundary:** Llama stores first-prefill activation/norm summaries,
  not generated-position telemetry. Its target-only inactivity counts are
  799/1,040 final-turn and 804/1,040 induction-turn prefills; 970/1,440 final
  prefills includes controls. No whole-turn inactivity claim follows. These
  distinctions follow the verified `docs/CLAUDE_REVIEW_STEERING.md` audit.
- **Causal interpretation (C):** The sixteen new factorial prompts are not a
  decomposition of the original recursive induction. The manuscript reports
  opposite-signed transcript effects, including Sonnet -0.350 and GPT-4o
  +0.125 under the OpenAI paper-rubric judge, with their released intervals.
  It names instruction/transcript mismatch, length, truncation, and missing
  arms as limitations. Historical model-resampling intervals are not presented
  as validated fixed-panel or model-population intervals. Public response
  matching and text cues limit the proposed human packet's blinding.
- **Verified review corrections:** Only Sonnet and GPT-4o transcript intervals
  strictly exclude zero; Haiku's reaches zero. The post-hoc deletion check
  gives 9/33 active baselines (27.3%), not the review's 64%, versus 4/6 targets.
  The final causal freeze at 21:08:21 UTC preceded runtime start at 21:08:35;
  the first final response completed at 21:12:55. Fourteen seconds describes
  the first gap, not time to a completed final response. Both analyzed pilots
  preceded the final freeze and informed intervening design revisions.
- **Cue interpretation (D3):** The archived 64.4% recovery ratio and its
  fixed-denominator interval are not recomputed or overwritten. Zero-activation
  items in sparse-feature high sets, alphabetical ties, cue/feature assignment
  mismatches (47/184 accepted transplant rows), and meaning-changing insertions
  are disclosed. The ratio is not
  a pure lexical test or validation of an honesty-related construct.
- **Attribution and comparison (H):** Substantive agent conduct is disclosed;
  separate automated implementations are not called independent human audits.
  The prior claim that a named human performed the 60-response inspection is
  removed as unverified. No completed independent human validation is claimed,
  nor is a claim made about private author contact. The target paper's original
  controls, sample sizes, prompt variants, and high Opus control rates are
  acknowledged. Its bibliography URL now pins
  [arXiv version 2](https://arxiv.org/abs/2510.24797v2).

All **15 old figure captions** were qualified or corrected. Embedded plot
labels remain historical, and all **12 tabular environments** and **15 figure
asset references** are byte-identical to the pre-correction manuscript.

## Evidence and Checks

Read-only standard-library checks used the released causal-study judgments and
`analysis_openai_paper/transplant_effects.csv`, the full-grid Llama generations
and local judgments, and Gemma's `steering/steering_generations.jsonl`. They
reproduced the counts, overlap formula, per-model effects, and activation
summaries above without running an analyzer or rewriting a release. The
cue-selection implementation was inspected without modification. The original
paper's version-2 methods, Table 2, and Appendix C.1 were checked directly.
The finalized `docs/CLAUDE_REVIEW_MEASUREMENT.md` supplied the separately
checked uncertainty, deletion-survival, assignment, and chronology details;
these remain explicitly post-hoc, not replacements for frozen analyses.

The PDF skill was read and its edit-operation marker completed successfully
once before the final forced rebuild. The LaTeX/BibTeX build succeeds locally:

```sh
cd paper
latexmk -g -pdf -interaction=nonstopmode -halt-on-error \
  -outdir=../out/review-correction-20260929 main.tex
```

The resulting 33-page PDF and auxiliary outputs are ignored. The final build
log has no LaTeX warnings, undefined references/citations, or overfull/underfull
boxes. The final opening page and two conclusion pages were rendered and
visually checked; this was not an all-page visual audit. Scoped whitespace and
preservation checks pass. This is manuscript verification, not a rerun of the
full repository test suite or independent scientific validation.
