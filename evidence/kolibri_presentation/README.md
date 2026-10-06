# Kolibri Figure Presentation

This retained editorial export matches the Qwen figure: three scoring rules,
two readers, and descriptive paired-block bootstrap intervals for SH minus HS.
It adds the already released explicit-only estimates to the visual comparison;
it does not produce new labels, estimates or intervals.

`figure_data.json` copies all six estimates and intervals from the hash-pinned
`../kolibri_extension/results.json`. The original publication binding, numerical
package, renderer and plots remain unchanged. The condensed paper uses a
cross-model table instead of separate model plots. It keeps simultaneous
primary bounds and links the fuller two-comparison plot from its uncertainty
appendix. This export's narrower bars are descriptive, not a new primary
test or evidence that the primary null has been rejected.

From the repository root:

```sh
python scripts/verify_kolibri_presentation.py
python -m unittest tests.test_kolibri_presentation
```

`--write` rebuilds only this editorial package; `--rerender` verifies a fresh
render against the saved files. `make paper-verify` separately retains the
original raw-data replay and immutable publication check.
