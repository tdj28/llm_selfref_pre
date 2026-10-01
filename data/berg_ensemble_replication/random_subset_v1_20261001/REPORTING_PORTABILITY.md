# Post-Run Reporting Portability Correction

2026-10-01, after all 450 outcomes and pod deletion. The first local secondary
reporter required exact Python equality with the unchanged GPU-worker summary.
It stopped after writing local `behavior/summary.json` and `behavior/rates.csv`.
That attempt is preserved locally under the ignored
`out/berg-ensemble-secondary-exact-failure-20261001/`; its same local numerical
values are retained in this release's `secondary/behavior/`.

There were eight unequal floats, all in notebook-rubric marginal or propagated
interval limits. Maximum absolute difference was 1.1102230246251565e-16.
All counts, estimates, bootstrap intervals and verdicts matched. The complete
primary paper-rubric target result matched exactly. The remote environment
pins NumPy 2.2.6 and SciPy 1.15.3; local reporting ran on macOS rather than the
Linux GPU worker. This is consistent with numerical-library/platform rounding,
not a demonstrated isolated cause.

The unfrozen reporting helper now requires identical structures, types,
integer counts and nonnumeric values; finite floats may differ by at most
1e-12. It records every differing value and the maximum error in
`secondary/summary.json`. Figures use the unchanged worker summary, not the
locally rounded copy. Eight focused tests cover accepted rounding and rejected
count, type, verdict, shape, nonfinite and material numerical changes.

This is a disclosed post-run reporting amendment, not a change to the frozen
analysis, sample, failure rules or decision threshold. In particular, it does
not relax or rescue the historical v2 J-lens replay gate. The original worker
artifacts and their remote hashes remain unchanged.

Before the first public commit, visual review moved the rate-figure legend
outside the plotting axes because it overlapped control-panel bars. The first
unpublished candidate, including its manifest, is preserved locally under
`out/berg-ensemble-prepublication-layout-20261001/`. The final manifest binds
the reviewed figures and updated reporting source; no plotted value changed.
