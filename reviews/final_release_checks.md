# Final Draft Checks

2026-09-29. These are local executing-agent checks, not human review.

- `make verify`: 78 tests pass, indexed public-file scan passes, 44 claim
  groups and 321 arithmetic identities pass, 52 passages bind 176 numerical
  occurrences, all five figure hashes pass, and the 19-file reproducibility
  receipt verifies.
- `verify_evidence.py --source-repo`: pinned-blob checks and 416 bounded raw
  field checks pass. This is not complete independent reanalysis.
- `verify_figure_values.py --source-repo`: all five plotting receipts
  reconstruct from pinned source code/summaries, with no mismatch.
- `uncertainty_sensitivity.py --source-repo ... --check`: archived hashes,
  compact inputs, manifest and LaTeX are exact; recomputed floats allow at most
  `1e-12` absolute platform roundoff. See the dated portability correction in
  `docs/UNCERTAINTY_SENSITIVITY.md`; original result bytes remain unchanged.
- Both Pro bundles pass the canonical helper's read-only authenticity
  validation. Their source packets, provider responses and original verdicts
  are unchanged. The final manuscript incorporates local adjudications;
  it has not received another paid review.
- Final `latexmk` build: 20 pages, no warnings, undefined references, overfull
  or underfull boxes. All 20 pages rendered and visually inspected for clipped
  text, equations, tables, figures, page flow and bibliography legibility.
- Final local PDF SHA-256:
  `cec689165e0e78f6d4544157b8d5866c275776b4b67b5e6018177f6c17dad29b`.
  Rebuilding may change PDF timestamps/bytes; this identifies the handed-off
  local artifact, not a requirement for byte-identical TeX builds.

No new experiment outcomes, GPU work, source release edits or website edits.
Human editorial approval and the separately planned human coding remain
pending. No consciousness verdict follows from these checks or results.
