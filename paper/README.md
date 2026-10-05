# Canonical Manuscript

Edit `main.tex` and `references.bib` here. This public repository holds the
latest manuscript, evidence and tooling. No companion checkout is required.

**What Drives a Language Model's Report of Subjective Experience?
Instructions, Continuations, and the Labels That Count Them** studies causes
and measurement of report labels.
Berg et al. supplied the starting protocol; this is not limited to a response
to their paper. Broader framing does not broaden what any result establishes.
Keep instruction effects, automated labels, steering delivery and internal
readouts distinct from consciousness or validated introspective access.

From the repository root:

```sh
make paper-verify
make paper
```

The PDF is generated at `paper/main.pdf` and remains ignored. The verification
target checks the bounded evidence package; it does not validate every label,
interpretation or interval. The root public-release audit is required before
commits. Rebuild and inspect the PDF after manuscript changes.

The steering-fidelity appendix uses hash-bound release summaries and figures.
For full reconstruction of its two frozen decision summaries from all 9,300
forwards, run `python scripts/verify_fidelity_calibration.py --full` in the
research environment. The default manuscript check is hash/value verification,
not that reconstruction or independent scientific validation.

## arXiv Upload

From the repository root, run `make arxiv`. It runs the manuscript evidence
checks, builds the paper, and creates `build/arxiv.tar.gz`. Upload that source
archive, not `paper/main.pdf` and not the repository. The separate
`build/arxiv_abstract.txt` is for the submission form; the builder rejects
abstracts above arXiv's 1,920-character limit.
`build/arxiv_manifest.json` records the upload inventory, hashes and local
compiler version. `build/arxiv_preview.pdf` is the archive's rebuilt preview;
neither file belongs inside the source upload.

The bundle contains the manuscript's required TeX inputs, figures and compiled
`main.bbl`. Source comments are sanitized in the bundle only; the canonical
and frozen files are not rewritten. Local notes, history, data releases,
credentials, build logs and the compiled manuscript PDF do not belong in the
upload. Referenced evidence tables and figures are included individually;
the unused source bibliography database is omitted in favor of `main.bbl`.

Validation must rebuild the extracted archive outside the repository, with
shell escape disabled and no local TeX search-path overrides, then check
citations, references and rendered-text agreement with the manuscript.
Successful local validation does not certify arXiv's compiler or moderation.
Choose `main.tex` and `pdflatex` during submission and inspect arXiv's generated
PDF, especially tables, equations, cross-references and the bibliography.

Checked against arXiv's [TeX submission instructions](https://info.arxiv.org/help/submit_tex.html),
[source requirement](https://info.arxiv.org/help/faq/whytex.html),
[common mistakes](https://info.arxiv.org/help/faq/mistakes.html), and
[abstract metadata rules](https://info.arxiv.org/help/prep.html#abstract-required)
on 2026-10-05. Its [supported environments](https://info.arxiv.org/help/faq/texlive.html)
are TeX Live 2023 and 2025; this workstation has 2024, so exact server-version
compatibility is not established by the local build. The older author
checklists supplied for this review remain useful for source hygiene, but
their claims that arXiv cannot run BibTeX or that every directory must be
flattened are not current submission requirements. No submission, subject
classification or license selection is performed by `make arxiv`.

## Files

- `main.tex`, `references.bib`: current manuscript and its cited literature.
- `source_alignment.tex`, `ensemble_alignment.tex`, `factor_inventory.tex`,
  `uncertainty_sensitivity.tex`: included experimental and methods sections.
- `context_extensions.tex`, `operator_matching.tex`: completed bilingual,
  frontier-model and public-operator extensions, with separate study scopes.
- `openrouter_swap_extension.tex`: Gemini/Opus comparisons with neutral
  instructions and same-condition donor continuations.
- `qwen_extension.tex`: separate Qwen3.8 API panel. `paper-verify` runs
  `scripts/verify_qwen_extension.py` to check its pinned inputs, paired
  contrasts, primary bounds, and descriptive bootstrap intervals.
- `repeated_extension.tex`: randomized four-cell collections with three
  answers per request. `paper-verify` replays the raw response and judge
  receipts, paired analyses, variance summaries and figure bindings.
- `kolibri_extension.tex`: locally served Kolibri's eight-condition panel.
  Its check replays the released receipts and reconstructs counts, paired
  effects and both readers' figure inputs. Primary simultaneous bounds remain
  separate from pointwise and descriptive intervals.
- `main.tex` presents the mapping-scaled, quality-selected steering finding;
  the source-style subset and operator studies are supporting appendices.
  `dose_followup.tex` preserves the original hash-bound exposition, no longer
  compiled into the manuscript. The current narrative uses its same verified
  numerical macros and figure without changing the release or its binding.
  `paper-verify` checks those release hashes and bindings; use
  `python scripts/verify_dose_followup.py --full --require-pinned` for the
  historical-source inference replay as well.
- `figures/`: selected figure inputs with pinned source provenance.
- `../evidence/figure_presentation/`: readable vector exports of historical
  plots, bound to their original values. `paper-verify` checks the inputs,
  displayed values, embedded fonts and absence of embedded captions.
- `../evidence/`, `../scripts/verify_*.py`: compact evidence and its checks.
- `../reviews/`: dated automated reviews, adjudications and reference checks.
- `results/`: earlier research figures/tables, retained rather than discarded.
- `history/20261001/`: immutable migration snapshots and import hashes.

Earlier manuscripts remain historical, not alternate working drafts.
The owner separately reopened collection for the October 4 model-panel,
repeated-answer and steering-dose follow-ups. Their plans and releases remain distinct from the
earlier studies; this manuscript incorporates verified results, not pending
or unrun comparisons. Other work is verification, editorial review and
release preparation.
Human editorial approval is still required before publication or submission.
Do not edit the Praxagent website or the private former companion as part of
routine manuscript work.
