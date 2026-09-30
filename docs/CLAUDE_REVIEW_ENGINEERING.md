# Engineering Review Decisions

Date: 2026-09-29. Baseline: `39c21e0b52d3b176f1ebfc6af6d40b26fff6ab86`.
Scope: G1-G4 and Appendix B of the supplied review. This is an engineering
response, not independent human scientific review. No paid calls, GPU pods,
commits, history publication, GitHub settings changes, license changes, or
frozen artifact writes were performed. Concurrent parent-owned edits are
outside this change set.

## G1: Test Collection And CI

The principal local claims reproduce. With the missing dependencies installed,
the original full pytest suite on Python 3.12.12 collected 1,024 tests:
97 failed, 921 passed, six skipped. Ninety-six failures reached historical
source drift before their intended assertions; one was a Darwin device-number
fixture bug. The existing unittest command omitted function-style tests and
two directories. The documented Experiment 1 analyzer had an indentation
error. The workflow placed all later audits after that failing test step.
The review's exact historical GitHub success/failure counts were not independently
queried in this pass; they are not needed to establish the local defects.

Changes:

- Added pytest, scikit-learn and scipy to the CPU verification requirements,
  plus a separate pinned CPU-capable PyTorch requirement. CI installs CPU
  wheels on Linux. Unlike Appendix B, no Gemma module-wide skip was added.
- `make test` now runs pytest, with importlib collection and both missing
  package markers. Removed the default fallback to `steering/.venv`, avoiding
  its editable-install namespace collision without renaming frozen code.
- Separated tests, source compilation, public-release scanning and each of the
  four headline audits into independent CI jobs. A failure cannot suppress
  unrelated checks. CI fetches reachable history for historical fixtures.
- `make compile` now checks every tracked Python file without imports or
  bytecode output. Fixed the analyzer's incorrectly indented conditional prose.
- `make audit` retains the legacy checks but executes them on disposable
  copies. The four CI headline outputs are compared to the frozen originals;
  extended analysis/audit/manifest commands retain their exit-status checks.
  They do not silently refresh original timestamps, commits or hashes.
- Mapping JSON comparison on Python 3.12 allows absolute float error at most
  `1e-12`, with zero relative tolerance. Types, integers/counts, keys, list
  structure and labels remain exact; nonfinite values fail. Other comparisons
  remain byte-exact. Tests reject material changes, nonfinite values, schema
  drift, missing outputs and unexpected output files.

### Frozen Source Bindings

No old hash was deleted and no live execution validator was relaxed. Historical
test fixtures first require all current scientific/source files to match their
recorded size and SHA-256. Only two explicit infrastructure/provenance paths
may be recovered from the full source commit recorded in the plan manifest:
`.gitignore` and `data/consciousness_sae_target_blind_calibration/README.md`.
Recovered bytes must still match both original fields exactly. The two source
commits are reachable ancestors, not newly published history.

Signed-dose packet fixtures now read original frozen bindings from the
recorded Git commit instead of pretending current working-tree files belong
to that commit. Current recovery code and live-closure tampering checks remain
current. Regression tests prove that scientific-source drift is not replaced
by historical code and that live validators still reject both infrastructure
and scientific edits. Frozen plans, runtime/auditor files and result hashes are
unchanged. A current-worktree execution gate can still legitimately fail on
historical `.gitignore` drift; passing a historical test is not permission to
execute a new run.

### Dependency Boundary

The older general/GPU `requirements.lock` contains Python-3.10-incompatible
pins and is not a faithful lock of every released runtime. It was not broadly
regenerated or represented as repaired. The supported no-GPU test/reanalysis
route is now explicit in [REPRODUCTION.md](REPRODUCTION.md), using the verified
CPU requirements. A future general/GPU lock rebuild needs its own compatibility
validation; it is not necessary for these checks. No experimental GPU runtime
pins were changed.

## G2: Later Studies

[STUDY_INVENTORY.md](STUDY_INVENTORY.md) indexes the five code families plus
the switch-arc draft, their recorded statuses, public summaries, raw-data
availability limits and claim boundaries. The review's blanket description
"undocumented" is too broad: family-local protocols and summaries exist, but
top-level discovery and status consistency were poor. The index exposes that
drift without editing frozen/local historical documents.

The original strict-equality J-map inventory bug already has separately
disclosed recovery adapters and missing-layer regression tests. The original
auditors were preserved. Archiving/removing studies and a precision-control
experiment were not authorized here; the inventory warns against treating the
disputed downstream-nonlinearity interpretation as settled.

## G3: Public Boundary

The index audit now recognizes uppercase `RELEASE_MANIFEST.json`, scans bounded
gzip payloads, does not let a NUL byte bypass raw-byte scanning, and recognizes
`OSF_TOKEN` and inline JSON credential assignments. Bad, oversized or nested
gzip content fails closed; values are never printed. This remains a heuristic
index scan, not a full-history or arbitrary-archive security guarantee.
Lowercase runtime `manifest.json` is not confused with a release hash manifest.

Private annotation/coder filename variants are rejected by the audit and
excluded by the causal release builder. A regression test checks the parent's
ignore rules for the review's three examples and annotation-key hash sidecars.
No private file or frozen release manifest was regenerated. Privacy/history,
infrastructure disclosure, branch protection, licensing and external archival
publication remain owner decisions. The parent owns NOTICE and ignore edits.

## G4: Documentation

Updated the reproduction environment and read-only audit instructions, and
added the study index. CI now checks local Markdown links and unambiguous
repository-root artifact references in the claim ledger, reproduction guide
and inventory. It handles globs but does not guess the meaning of abbreviated
table paths or check external websites. The parent's four corrected ledger
references resolve; no ledger edit was made here.

## Validation

- Python 3.10.15: full suite 1,064 passed, six skipped; the subsequently added
  ignore regression and all engineering checks passed in a 24-test focused run.
- Python 3.12.12: final full suite 1,065 passed, six skipped, including the
  parent's latest agreement, measurement and steering-delivery tests.
- `pip check`: passed in both isolated CPU environments.
- All 313 tracked Python sources compiled on both versions; five existing
  shell syntax checks passed. New helper modules are also imported by tests
  or exercised directly. No import-only compile test runs model code.
- All four frozen CI output checks passed on both versions. The full extended
  `make audit` equivalent passed on 3.10 using disposable copies, including
  construct validity, branched specificity, J-lens v1 and the causal builder.
- Public index audit: passed, 2,170 files / 1,324,844,362 bytes scanned; 17 release
  manifests / 911 file entries verified. This does not include unstaged new
  files; the parent must rerun after staging the combined change set.
- Documentation reference checks and `git diff --check`: passed.
- Additional direct scans of the engineering worktree files and current
  private-ignore checks found no findings. The frozen `data/` tree has no diff.

The six skips require CUDA, the designated GPU host, Linux Landlock, or optional
RunPod/transformers dependencies. No Linux or remote GitHub Actions execution
was performed locally; CI must establish that platform result after the parent
pushes. These are validation boundaries, not evidence of scientific validation
or a need to access private raw tensors for this engineering work.

## Changed Paths

Engineering-owned paths only; do not infer ownership of other concurrent edits.

```text
.github/workflows/verify.yml
Makefile
pytest.ini
requirements-ci.txt
requirements-ci-torch.txt
docs/CLAUDE_REVIEW_ENGINEERING.md
docs/STUDY_INVENTORY.md
docs/REPRODUCTION.md
experiments/causal_transplant/build_release_manifest.py
experiments/exp1_elicitation/analyze.py
scripts/audit_public_release.py
scripts/check_documentation_links.py
scripts/check_frozen_audits.py
scripts/check_python_sources.py
tests/__init__.py
tests/frozen_sources.py
tests/test_engineering_checks.py
tests/test_public_release_audit.py
tests/consciousness_sae_changepoint/__init__.py
tests/consciousness_sae_signed_dose_scan/test_recovery_equivalence.py
tests/consciousness_sae_target_blind_calibration/__init__.py
tests/consciousness_sae_target_blind_calibration/test_audit_recovery.py
tests/consciousness_sae_target_blind_calibration/test_landlock_launcher.py
tests/consciousness_sae_target_blind_calibration/test_recovery_bundle_verifier.py
```
