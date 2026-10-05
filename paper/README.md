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

## Files

- `main.tex`, `references.bib`: current manuscript and its cited literature.
- `source_alignment.tex`, `ensemble_alignment.tex`, `factor_inventory.tex`,
  `uncertainty_sensitivity.tex`: included experimental and methods sections.
- `context_extensions.tex`, `operator_matching.tex`: completed bilingual,
  frontier-model and public-operator extensions, with separate study scopes.
- `openrouter_swap_extension.tex`: Gemini/Opus comparisons with neutral
  instructions and same-condition donor continuations.
- `figures/`: selected figure inputs with pinned source provenance.
- `../evidence/`, `../scripts/verify_*.py`: compact evidence and its checks.
- `../reviews/`: dated automated reviews, adjudications and reference checks.
- `results/`: earlier research figures/tables, retained rather than discarded.
- `history/20261001/`: immutable migration snapshots and import hashes.

Earlier manuscripts remain historical, not alternate working drafts.
The owner separately reopened collection for the October 4 model-panel and
steering-dose follow-ups. Their plans and releases remain distinct from the
earlier studies; this manuscript incorporates verified results, not pending
or unrun comparisons. Other work is verification, editorial review and
release preparation.
Human editorial approval is still required before publication or submission.
Do not edit the Praxagent website or the private former companion as part of
routine manuscript work.
