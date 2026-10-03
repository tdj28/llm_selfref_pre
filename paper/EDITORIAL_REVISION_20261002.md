# Editorial Revision: 2 October 2026

This pass implements the owner's requested writing review, informed by
[Neel Nanda's ML-paper advice](https://www.lesswrong.com/posts/eJGptPbbFPZGLpjsp/highly-opinionated-advice-on-how-to-write-ml-papers).
It edits the canonical manuscript, not the experimental archive. Existing
uncommitted introduction and methods edits were the starting point.

## Changes

- The abstract quantifies the instruction and transcript effects and retains
  the random-subset result with its alternative-rubric and specificity limits.
- The introduction states three contributions: input-component effects,
  report measurement, and bounded public-weight intervention evidence.
- Figure 1 combines the crossed-request diagram with the unchanged causal
  decomposition plot. The existing post-hoc boundary intervals appear beside
  the plot, explicitly separate from its frozen bootstrap intervals.
- Full trial and transplant texts move to Appendix A. Their selection as
  the first GPT-4o block, rather than an outcome-selected example, is retained.
- Measurement becomes a separate main section. Its new figure separates
  full-panel agreement from attribution counts on the fixed 160-response
  packet. All readers and both attribution thresholds remain visible; changing
  judge and rubric is not interpreted as a rubric-only causal effect.
- The native-BF16 450-trial random-subset study leads the steering results.
  A study inventory summarizes the earlier Llama, native source-alignment and
  Gemma studies; their full results, matching panels, scales, failed gates,
  and limitations remain in appendices rather than being discarded.
- J-lens has a short main-text account of propagation with identity and
  random-transport comparators. Full equations, lexicon tables, source-history
  distinctions and descriptive-analysis status remain in Appendix F.
- The discussion groups measurement, intervention and generalization limits.
  Reporting-column history and floating-point portability move to appendices.
- Wording no longer implies that report effects are categorically irrelevant
  to consciousness. They do not, by themselves, establish it. The API panel
  is described as pinned configurations, not current frontier models.

## Evidence Boundaries

No raw data, frozen protocol, result, threshold, numerical binding, source
figure, evidence package, or analysis implementation is changed. The new
attribution bars use the existing verified audit macros. The boundary table
uses the existing post-hoc uncertainty macros. Earlier failures remain
failures; moving material does not change its evidential status.

This pass launches no experiment, GPU rental, model-judge call, or paid
review. It does not edit the website or the private former companion repo.
Automated checks and visual inspection are not independent scientific review
or human editorial approval.

## Verification

- `make paper-verify`: passed after restructuring, including all 58 original
  numerical passages and 201 numerical occurrences.
- `make paper`: rebuilt the manuscript; layout review includes the lead
  diagram, measurement figure, main steering figures and appendix tables.
- `make public-audit`: passed for 10,501 indexed files (3,628,658,732 bytes).
  This audit reads the index, not unstaged changes. A separate run of its
  secret scanner over the four edited/new manuscript files found no issues.
- `git diff --check`: passed. No files were staged or committed in this
  editorial pass; unrelated work was left unchanged.
