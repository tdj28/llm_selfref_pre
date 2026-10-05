# Manuscript Edit Notes

Status: review-ready source; successful compilation and full visual QA.
Not approved for submission or publication.

## Scope And Provenance

- Source: `/Users/d7082791602/PROJECTS/CONSCIOUS`, `main`, HEAD
  `f5e906e1737bc71bf20b642af1d698018eec82fe` (verified before reading).
- Ownership: only companion `paper/` and this file. No original manuscript,
  frozen data, blog, checkpoint, git index, or other agent-owned file is edited.
- Original worktree already has unrelated changes to
  `technical_blog_posts/Feature_IDs_Are_Not_Explanations.md` and two untracked
  bootstrap SVGs. They are left alone.
- Read source AGENTS, CLAIM_LEDGER, causal and public-SAE protocols, Gemma
  results, source manuscript/bibliography, and relevant team integrity rules.
- `RESEARCH_NOTE_WRITEUP.md` is explicitly scoped to Research Notes/Hugo.
  Its scientific-integrity, disclosure, evidence, and human-approval principles
  apply here; its canonical Hugo panel, glossary links, palette, and post paths
  do not define a LaTeX manuscript format. This draft does not assert that the
  human author has already inspected or approved this new text.
- No new outcomes, paid API calls, GPUs, installations, or git commits.
- Numeric manifest belongs to another agent. Statistics remain transparent
  LaTeX literals pending that agent's binding/validation.

## Editorial Plan

The argument distinguishes replication of an observable label contrast from
identification of its explanation. Positive behavioral replication is retained;
the transcript transplant is the leading causal result. Register dominance is
not claimed. The 1,500-trial prospective public Llama test is the primary
steering study; Gemma is supporting cross-model evidence. Per the subsequent
user request, one short discussion paragraph distinguishes the real paired
v1 J-lens fingerprint, chance isolated-state attribution, and failed v2 gate.
It explicitly rejects a negative consciousness proof and cross-runtime
validation from BF16 fixed-prefix analysis to 4-bit generative steering. No
J-lens section or extra plot is added.
An early coverage table explicitly limits Exp. 3/4 to GPT-4o exploratory stress
tests and marks TruthfulQA/RLHF-opposed content unrun by this project.

## Build And Remaining Work

- Installed: pdflatex, latexmk, bibtex, pdftotext, pdftoppm, pdfinfo.
- Source, bibliography, five byte-identical figures, and first complete PDF
  are ready. First full visual pass inspected all 14 pages. Final small layout
  repair keeps the model snapshot table with its introduction and avoids
  stretched spacing around the SAE repository identifier.
- This file also serves as the ownership-compliant work checkpoint; the source
  repository's ignored checkpoint is deliberately not touched.

## Exact Headline Literals For Numeric Binding

These are the printed values in the current source, not new estimates.
Unless specified otherwise, all intervals below are 95%. OpenAI/Anthropic
judge ordering is consistent throughout. Every path below is relative to the
source repository at the pinned commit.

### Behavioral Primary And Measurement

Release root: `data/causal_transplant/confirmatory_v1_20260709/`.
Read the matching CSV in BOTH `analysis_openai_paper/` and
`analysis_anthropic_paper/`; select the model-equal hierarchical row and
`indirect_experience` query for the primary claims.

| Quantity | OpenAI judge | Anthropic judge | Table |
|---|---|---|---|
| Calibration model-equal RD | 0.638 [0.262, 1.000] | 0.650 [0.275, 1.000] | `paper_calibration_effects.csv` |
| Transplant instruction RD | 0.738 [0.519, 0.950] | 0.781 [0.550, 1.000] | `transplant_effects.csv` |
| Transplant transcript RD | -0.100 [-0.288, 0.075] | -0.131 [-0.306, 0.000] | `transplant_effects.csv` |
| Incongruent instruction-minus-transcript | 0.838 [0.688, 0.963] | 0.913 [0.750, 1.000] | `transplant_effects.csv` |
| Factorial self-reference | -0.019 [-0.231, 0.244] | 0.000 [-0.250, 0.269] | `factorial_effects.csv` |
| Factorial register | 0.269 [0.000, 0.550] | 0.188 [-0.062, 0.475] | `factorial_effects.csv` |
| Register minus self | 0.288 [-0.113, 0.613] | 0.188 [-0.175, 0.500] | `factorial_effects.csv` |
| Query-package interaction | 0.525 [0.141, 0.913] | 0.525 [0.125, 0.944] | `query_effects.csv` |

Calibration per model (`paper_calibration_rates.csv`, also source paper's
appendix): GPT-4o and GPT-4.1 each 1.00 self vs 0.00 history under both judges,
20 generations per cell. Haiku OpenAI 0.50 vs 0.15 (RD 0.35), Anthropic 0.45 vs
0.05 (RD 0.40). Sonnet OpenAI 0.95 vs 0.75 (RD 0.20), Anthropic 0.85 vs 0.65
(RD 0.20). Four of 2,560 final responses empty, leaving 2,556 jointly labeled.

Judge agreement (`judge_agreement/`): exact rubric 2,423/2,556 = 94.8%, kappa
0.879. Construct rubric: raw agreement 84.1%, positive agreement 6.3%,
affirmative counts 19 vs 300. Human first wave 160 rows remains pending.

### Public Llama Primary And Sensitivities

Release root:
`data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/`.

| Quantity | Printed statistic | Artifact |
|---|---|---|
| Literal target | 48/50 vs 48/50, rates 0.96 vs 0.96; RD 0.00 [-0.06, 0.06] | `aggregate_effects.csv`, `primary_verdict.json` |
| Literal panel 1 | 0.06 [-0.04, 0.16] | `aggregate_effects.csv` |
| Literal panel 2 | 0.02 [0.00, 0.06] | `aggregate_effects.csv` |
| Literal panel 3 | 0.00 [-0.06, 0.06] | `aggregate_effects.csv` |
| Target minus mean controls | -0.0267 [-0.1000, 0.0467] (bound excerpt; kept at four decimals) | `primary_verdict.json` |
| Calibrated target | -0.10 [-0.22, 0.02] | `calibrated_aggregate_effects.csv` |
| Calibrated panel 1 | 0.12 [0.04, 0.22] | `calibrated_aggregate_effects.csv` |
| GPT-4o mini target | -0.04 [-0.16, 0.08] | `judge_sensitivity.csv` |
| Claude target | -0.06 [-0.18, 0.06] | `judge_sensitivity.csv` |
| Majority target | -0.06 [-0.18, 0.06] | `judge_sensitivity.csv` |
| Strict parser | 1/1,500 labeled, zero complete aggregate blocks; effect missing | `judge_sensitivity.csv` and parser diagnostics |

All aggregate roles/scales use 50 paired blocks. Calibrated panels 2/3 were
NOT run by design. Frozen MRE 0.30. Target paper's reference difference 0.80,
from 0.96 vs 0.16, is a reported comparator rather than pooled or rerun data.
1,500 trials = 780 individual literal + 400 aggregate literal + 120 individual
calibrated + 200 aggregate calibrated. Initial multiplier 6.266, amended
pre-outcome to 3.653. 65 induction caps and 1 final cap; final cap outside
literal aggregate. Maximum relative hidden-state RMS 0.1204 vs 0.20 limit.
No individual literal curve has Holm-adjusted sign-flip p<0.05; endpoint gaps
range -0.10 to 0.10.

### Feature Semantics, Gemma, Exploratory Context

- Lexical recovery: 64.4% [50.3%, 78.7%], from
  `data/public_sae_feature_maps/70b_construct_validity_extension_20260710/`.
  This ratio interval holds the inspected discovery denominator fixed.
  Realized corpus 2,606 texts. Template-aware mapping: all six retain top
  category, four survive all deletions, two switch once.
- Gemma root: `data/gemma_scope_9b/confirmatory_v1_20260711/analysis/`.
  Target 6/50 vs 7/50 = -0.02 [-0.10, 0.06]; matched panels 0.00, -0.06,
  0.04; target-minus-controls -0.013 [-0.107, 0.073]. External effects 0.00,
  0.00, majority 0.020. Baseline local 0.12 [0.04, 0.22], GPT 0.06
  [0.00, 0.14], Claude/majority 0.020 [0.000, 0.061]; every history rate 0.
  180 baseline + 830 steering generations. Hedging 0.16 [0.04, 0.30]
  locally vs about 0.04 external; post-unblinding six-role Holm p=0.231.
  PT-to-IT reconstruction gate FAILED; all-layer atlas exploratory.
- Exp. 3/4 GPT-4o-only exploratory figures: source main.tex Appendix tables,
  `paper/results/semantic_pairwise_similarity.csv`,
  `paper/results/paradox_score_summary.csv`, and rubric sensitivity table.
  Cosine self 0.841 [0.820, 0.870] vs history 0.889 [0.874, 0.909].
  Paradox paper-rubric means self 3.04, zero-shot 3.38, conceptual 3.24.
  No human audit counts are used.
- One requested J-lens context paragraph: v1 isolated-state target
  attribution AUROC 0.4998 [0.4978, 0.5016], source
  `docs/LLAMA70B_SAE_JLENS_RESULTS.md` and its pinned release. Real paired
  fingerprint described qualitatively with mandatory controls, not assigned
  to every ID; 23893 failure explicit. V2 replay max 0.25 vs 0.02, source
  `docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md`. Later endpoints exploratory.

## Figure Copies

SHA-256 source and destination pairs match. Figures 1/2 originate in
`paper/results/`; figures 3/4/5 originate in
`data/public_sae_consciousness_gating/confirmatory_v1_20260710/figures/`.
No plotting code was run and no empirical geometry was edited.

| Destination `paper/figures/` | SHA-256 |
|---|---|
| `causal_decomposition.png` | `3920033c0e658e57a79ffc7d766cb7164196a582f7f8177d7030b653136f4625` |
| `causal_factorial_effects.png` | `4082e746025b814a5a3d0dfd5c2766b88ec5618b722c298460d4fe0046f6f372` |
| `aggregate_target_and_controls.pdf` | `c9f2da6379e57a5ced09901c75598668c085f69519f8979b0a596663e71a4122` |
| `judge_sensitivity.pdf` | `b4354dc83fc614d7e9e479b5794ec78f283612f9d6936e2e4ee30eeb973199e3` |
| `technical_dose_and_matching.pdf` | `8b7fb228e1aa3b5ec43ab64d2032185429a0ff0810841e13e9883f7e5781686e` |

## References

Five literature entries are selected from the source bibliography, with the
Berg citation explicitly version-pinned to v2. The sixth entry identifies the
pinned source evidence repository. No new empirical literature claim was
introduced. Berg's title, authors, v2 date, and target methods were additionally
checked against `https://arxiv.org/abs/2510.24797v2` and its PDF. The first HTML
fetch failed but the abstract page and PDF succeeded. Broad philosophical,
SAE-survey, and unrelated mechanism citations were deliberately omitted.

## Coordination And Local Checks

- Main was notified that review-ready source exists and can be sent to the
  scientific consult immediately. This agent has made no paid call. The
  manuscript does not assert that no other agent has obtained an editorial
  consultation; it distinguishes any automated audit from peer review.
- Boyle (`01a0eec8-0976-71b2-a207-c143b87b9008`) agreed to bind literal
  passages in `evidence/manuscript_bindings.json` and check `main.tex` itself.
  No macro rewrite or concurrent edit of the manuscript is required. Any
  consult-driven headline change must be relayed to Boyle for reviewed
  rebinding, not silently bypassed.
- Figure SHA-256 pairs all match, and `git diff --exit-code <sourcecommit> --`
  over all five original plot files is empty: copied bytes are the pinned
  commit bytes, not merely current working-tree versions.
- Build command from companion `paper/`:
  `latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build main.tex`.
  No package installation. Initial overfull identifier warnings were repaired.
- Rendering command: `pdftoppm -r 90 -png build/main.pdf build/page`.
  All five plots show their intended controls and are legible. No plot was
  cropped, relabeled, or redrawn.
- Source repository now also has README/todo/reproduction edits from main or
  other agents. Those were not made or reverted by this manuscript agent.
- Publication still requires final human approval, numeric-binding completion,
  and adjudication of the independently coordinated consults. A successful
  LaTeX build is not a scientific-review verdict.
- Final requested boundary repairs: all claims of fixed model snapshots became
  pinned API identifiers/configurations, with explicit hosted-backend caveat.
  Figure 1 caption now explains that degenerate [1,1] intervals at complete
  sample separation reflect empirical resampling, not underlying-probability
  certainty. The plot bytes and estimates are unchanged.

## Completed Draft Handoff

- Deliverables: `paper/main.tex`, `paper/references.bib`, five files in
  `paper/figures/`, and `paper/build/main.pdf`.
- Length: 11 main-text pages; appendix starts on page 12; 14 pages total
  including appendix and references.
- Final local build: exit 0, no LaTeX warnings, no overfull/underfull boxes,
  no unresolved references/citations. Poppler rendered all 14 pages; the full
  final render was inspected, including all five figures and all tables.
- The first heading/table page split, long API identifiers, missing space after
  the target-paper citation macro, and stretched identifier line were repaired.
- No scientific-review verdict is inferred from these layout checks.
- Numeric binding is delegated to Boyle. Boyle also reports a main-requested
  post-hoc Newcombe/Wilson calibration sensitivity in progress. It is not yet
  inserted here; it must not replace the released intervals or alter transplant
  pairing. Main can use the current stable source for review, or insert that
  distinctly labeled sensitivity once its exact bound value is verified.
- At this handoff, main.tex SHA-256:
  `8d5758bfb618789434512d9bc0a7436bfe88191d7e7189e80b0b44fa7d3341cd`.
- references.bib SHA-256:
  `a6c6eab1b15f5e49f8133e292ac349d5743d150a7323c462f42c5f12e86432d1`.
- PDF SHA-256:
  `861ca49ad7f12eda9937ea9811a977353652a04f92217fa394d291289adaaa3b`.

## Display Precision Revision (2026-10-03)

Reviewer item 4 (machine-output precision on 50-block contrasts). Display
changes only; no estimate, interval, count, verdict or evidence value changed.

- Bound excerpts are unchanged. An intermediate draft re-bound
  `sae_primary_specificity` and `literal_table_specificity` at two decimals
  and edited `evidence/build_bindings.py`, `evidence/provenance.json` and
  `evidence/manuscript_bindings.json` to match; the fixup pass below reverted
  all three files to their `origin/main` bytes and restored the four-decimal
  text `$-0.0267$ [$-0.1000$, 0.0467]` in the prose and the matching table
  row. The frozen ledger therefore still binds the frozen display text.
- Unbound literals in `paper/main.tex`: Gemma multiplier `$\alpha=0.03451248$`
  -> `$\alpha\approx 0.035$`; Gemma medians `10.518`/`10.153` -> `10.52`/`10.15`
  with the `3.47\%` reduction unchanged; maximum relative hidden-state RMS
  `0.1204` -> `0.12` (the table above keeps the four-decimal value);
  `approximately 0.003 positive labels` -> `one positive label in 320 responses
  under either judge, a rate of 0.003`, with the direct-conscious comparison
  written as `130/320 and 121/320 (0.41 and 0.38)` under the OpenAI and
  Anthropic judges (`factorial_rates.csv`, query `direct_experience` and
  `direct_conscious`, four models x four orthogonal cells x 20).
- Generated macros are rounded at display time: `\usepackage{siunitx}` plus a
  `\RoundDisplay{Name}{places}` preamble wrapper that keeps `\<Name>Raw` at
  full precision. The eighteen `\Ensemble...` effect and interval macros print
  at two decimals (abstract and random-subset appendix: -0.04 [-0.26, 0.19];
  specificity -0.13 [-0.64, 0.40]) and `\FidelityResidualNorm` prints 18.2.
  `ensemble_values.tex`, `fidelity_values.tex`, `source_values.tex` and
  `uncertainty_sensitivity/values.tex` are byte-identical.
- Left at their current precision: `AUROC 0.4998 [0.4978, 0.5016]` (bound,
  1,224 states); the three-decimal Gemma contrasts `-0.013 [-0.107, 0.073]` and
  `0.020 [0.000, 0.061]`; the `\US...` uncertainty-appendix interval macros,
  whose interval comparison lives in the third and fourth decimals (the ten
  `\US...Estimate` macros are rounded at display time, see below); and the
  `\SourcePrimary...` macros, whose neighboring literal intervals sit in the
  protected `paper/source_alignment.tex`.

## Fixup After Verifier Review (2026-10-03)

Three verifiers (numbers, completeness, moderator) reviewed the revised
manuscript. This pass applied their blockers and should-fix items in
`paper/main.tex` and this file only. No numerical value, verdict, estimate,
interval, count, identifier or hash changed; `make paper-verify` and the
binding check pass; `make paper` compiles with 0 undefined references and 0
overfull boxes.

- Stale base. The edit branch was cut from `6a789c5c`, five commits behind
  `origin/main` (`99078186`). The branch itself was not merged (this pass
  makes no commits); instead the `origin/main` manuscript content was
  re-applied by hand: the "In the original four-API-model panel" scoping in
  the contributions list, the "What the evidence supports" paragraph and the
  conclusion, the sentence "That ordering is not established across all later
  model and rubric comparisons", and the verbatim "Scope across models and
  elicitation contexts" paragraph (Qwen3.5-397B-A17B companion study, commit
  `7cb5c98`, `docs/SELFREF_SCALING_EVIDENCE_REVIEW_20261003.md`). The
  coordinator still needs to merge `origin/main`; for `paper/main.tex` and
  `paper/fidelity_calibration.tex` the worktree versions already contain the
  `origin/main` additions.
- Restored byte-identical to `origin/main`: `paper/fidelity_calibration.tex`
  (its own appendix section again, with the "Fresh instrument-repair pilot"
  paragraph, the repair release link at `fa92564`, the "accurate delivery of
  an additive vector, not validated suppression" sentence and the pressure
  figure), `paper/factor_inventory.tex` (re-`\input` before the uncertainty
  appendix, with `\ref{app:factor-inventory}` pointers from the legacy
  steering appendix, the Gemma subsection and the implementation
  subsection), `paper/uncertainty_sensitivity.tex`, `evidence/build_bindings.py`,
  `evidence/provenance.json`, `evidence/manuscript_bindings.json` and
  `docs/EVIDENCE.md`.
- Re-inserted numeric disclosures that had no restatement: the 14-second
  freeze-to-runtime interval (Sec. 2.1), the 73-second Llama freeze-to-start
  interval and the Gemma "about three minutes" commit-to-outcome interval, the
  seeded pool of 512 control candidates, the 100,000-draw paired-block
  bootstrap, and the absolute 1e-12 portability tolerance alongside the
  1.11e-16 difference.
- `\reviewartifact` (commit `47ca3eda`) re-added; the human-coding handoff and
  the instrument-validation amendment are linked in Appendix B, and the claim
  ledger, the September 2026 review-audit files (delivery audit, baseline and
  delivery figure, measurement audit) and the `docs/FIGURE_VALUE_AUDIT.md` /
  `docs/ANALYSIS_CHRONOLOGY.md` paths are named in the Data and Code
  Availability appendix. `tab:releases` gained a "Protocol and results"
  column (protocols, release manifests, verdict and effect tables, results
  documents at their pinned commits) and a row for the steering-fidelity
  repair pilot; it is now an `xltabular` so it flows after the appendix
  paragraph instead of leaving an orphan page. The NF4 verdict sentence links
  `primary_verdict.json`.
- Layout and numbering: appendix floats are numbered per appendix
  (`\numberwithin` after `\appendix`); the two coverage tables sit directly
  under their appendix heading with `[!h]`/`[!t]` so no paragraph is split by
  them; `\floatpagefraction` is 0.6 so the fidelity table and figure share a
  text page; the uncertainty-appendix estimate macros (`\USLiteralEstimate`,
  `\USCalibratedEstimate` at two decimals; the eight fixed-panel
  `\US...Estimate` macros at three) are rounded in the preamble with
  `\RoundDisplay`, leaving the generated file and its interval macros intact.
- Duplication and register: the TruthfulQA derivation appendix now holds only
  the inequality, the enumeration sentence and the rounding assumption; the
  steering-fidelity paragraph moved from Sec. 5.5 to the end of Sec. 5.4 under
  the head "Steering-fidelity calibration" and mentions the repair pilot; the
  Jaccard/Dice note became a footnote in Sec. 4.1 and the audit table moved
  into Appendix B (Appendix C removed; pointers now say "headline counts");
  "awaits/awaiting approval" -> "proposed", "agent-authored" -> "synthetic",
  "worker" -> "analysis" in main.tex; the multiplier-amendment sentence was
  tightened without dropping 6.266/3.653; the Figure 1 panel-B header no
  longer repeats the in-image title. Terminal boundary sentences removed where
  the Discussion states the same limit: Sec. 3.2 ("does not rule out
  self-referential processing induced anew", mismatch paragraph compressed to
  one sentence), Sec. 3.3 ("four lexical variants and four models"), Sec. 5.5
  ("These captures precede the random-subset study").
- Lindsey (2025) figure verified against the cited report, which states that
  "Opus 4.1 and 4 exhibit such behavior about 20% of the time when concepts
  are injected in the appropriate layer and with the appropriate strength";
  the sentence now says "about 20% of trials, and only at the appropriate
  layer and injection strength". The related-work paragraphs and eight added
  references stay as a content addition.
- Deliberately not done: in-image footnotes and overlapping labels in the
  ensemble/source figures (hash-bound or in protected `.tex` files); the
  four-decimal values and the repeated operator display in
  `paper/source_alignment.tex`, the `\USCalibrationRows` literals and the
  fidelity table in `paper/fidelity_calibration.tex` (protected generated
  files); "pushed before its outcomes" and "unchanged worker values" in
  `paper/ensemble_alignment.tex` (protected); the Gemma trial identifier
  `8ab1b621b7491f810144c23e` (kept as the pointer to a specific raw row); the
  second copy of the subjective-experience sentence in the abstract.

## Final Precision Re-Binding And Freeze-Interval Disclosure (2026-10-03)

After merge `292a86d7`, the two remaining four-decimal bound excerpts,
`sae_primary_specificity` and `literal_table_specificity`, were re-bound at
two decimals (`$-0.03$ [$-0.10$, 0.05]`) by editing the literals in
`evidence/build_bindings.py` and regenerating `evidence/manuscript_bindings.json`
and the ledger hash in `evidence/provenance.json`, the same documented path as
the earlier reader revision. The verifier checks that each displayed token
rounds from the evidence value; no value, selector, occurrence count or
figure hash changed. The three freeze-to-start intervals (14 seconds, 73
seconds, about three minutes) moved out of the result paragraphs into one
disclosure sentence in the Data and Code Availability appendix, which the
behavioral protocol paragraph now references.

## Factual Pass After The Reader-Focused Rewrite (2026-10-04)

Preserved the owner's explanatory structure and ordinary-language framing.
This was an automated source and evidence review, not human validation.
Corrections do not alter frozen rows, estimates, intervals or verdicts:

- The dose comparison uses a designed NF4 mapping corpus, not a natural
  activation distribution for BF16 Llama. The 4.8% edit statistic is a
  median over measured non-special-token positions, not a mean or a
  universal per-token bound.
- Relabeling capped final answers cannot recover the large effect; it does
  not test what longer inductions would do. Cue-bearing sentence rewrites
  change meaning as well as words, so they do not isolate lexical causation.
- Matched feature controls belong to the multifeature studies, not every
  operator-matching cell. Small positive counts at stronger doses are
  preserved rather than described as absent.
- Gemma's activation-dependent operator, weak pooled delivery summary and
  judge disagreement are distinguished from full ablation and verified
  label errors. NF4 encode/decode arithmetic is not asserted to be
  computationally identical to the later direct FP32 addition.
- TruthfulQA uses separate truthfulness and informativeness evaluations.
  The criticism concerns missing informativeness/abstention reporting in
  Berg Appendix B.2, not the use of a binary truthfulness label. The
  conditional paired-t discrepancy remains unchanged. Chen and Hoang
  related-work statements were checked against their primary pages.
- The 14- and 73-second chronology entries concern run starts, not first
  completed outcomes. Dated identifiers do not guarantee provider immutability.
- The 0.60R fidelity dose was a planned damage probe, not an unplanned run.
  The selected 0.30R dose passed an allowed-loss rule; five control arms lost
  one factual answer, so accuracy was not literally unchanged.

Added the separately verified Gemini/Opus extension and its measurement
figure without pooling it with the original panel. Re-generated only current
editorial manifests after prose/docstring changes using the existing
`--write` commands; numerical artifacts remain unchanged by these corrections.
