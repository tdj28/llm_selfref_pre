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

Use the Python environment and system dependencies in the
[reproduction guide](../docs/REPRODUCTION.md#setup-and-checks). From the
repository root, run `make arxiv`. It runs the manuscript evidence
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

## Manuscript Structure

- `main.tex`, `references.bib`: current text and bibliography. The main paper
  presents the original swaps, scoring audit, model comparison and
  quality-selected steering result.
- `model_comparison.tex`: integrated cross-model/language and repeated-answer
  results. It retains primary versus secondary endpoints, judge identity,
  missingness and conservative primary bounds. Its overview heatmap compares
  the same English swap contrast across 11 response models, without pooling
  studies or treating point estimates as significance tests.
- `internal_diagnostics_summary.tex`: compact source-alignment, readout and
  failed-fidelity account; complete diagnostics are linked to pinned releases.
- `uncertainty_sensitivity.tex`: post-hoc checks, including reused-seed and
  fixed-panel uncertainty. Exact prompts, complete examples and other
  detailed estimates are in the appendices in `main.tex`.
- `../evidence/` and `../scripts/verify_*.py`: bound numerical packages and
  checks. Condensation changes presentation, not frozen data or intervals.
  The readable figure exports preserve source values and embedded fonts.
- `history/20261005-pre-condensation/`: master-source snapshot before the
  approved length reduction, with its hash. `history/20261001/` preserves
  the earlier immutable migration snapshots.
- Earlier detailed section files (`context_extensions.tex`,
  `openrouter_swap_extension.tex`, `qwen_extension.tex`,
  `kolibri_extension.tex`, `repeated_extension*.tex`, `source_alignment.tex`,
  `ensemble_alignment.tex`, `operator_matching.tex`,
  `fidelity_calibration.tex`, `factor_inventory.tex`, `dose_followup.tex`)
  remain as source/provenance records, not alternate manuscripts.
  Hash-bound files are unchanged even when no longer compiled. Their
  figures and complete releases remain available in the archive.

The Chinese examples preserve the generated Chinese and recorded translation
receipts. The displayed English translation corrects only "an attention" to
"attention"; the caption and presentation data disclose the correction.
On 2026-10-05, the author reported that a Chinese speaker had checked Figure
B.3's displayed translations. The manuscript discloses this figure-specific
check, not human validation of the full dataset or the automated labels.

Earlier manuscripts remain historical, not alternate working drafts.
The owner separately reopened collection for the October 4 model-panel,
repeated-answer and steering-dose follow-ups. Their plans and releases remain distinct from the
earlier studies; this manuscript incorporates verified results, not pending
or unrun comparisons. Other work is verification, editorial review and
release preparation.
Human editorial approval is still required before publication or submission.
Do not edit the Praxagent website or the private former companion as part of
routine manuscript work.
