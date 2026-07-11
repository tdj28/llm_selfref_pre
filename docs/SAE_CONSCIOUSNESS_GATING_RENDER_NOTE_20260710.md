# Public-SAE Gating Render Note

Date: 2026-07-10

At confirmatory generation row count 10/1,500, before any response text was
opened or any outcome was classified, a full synthetic post-generation smoke
test found a figure-only edge case. Wilson bounds for synthetic cell rates of
exactly zero or one differed from the point by floating-point epsilon, causing
Matplotlib to reject a nominally negative error-bar length.

The figure code now clamps only rendered error-bar lengths at zero. It does not
change stored point estimates, confidence bounds, bootstrap draws, labels,
estimands, thresholds, verdicts, plans, or generation. The primary analyzer and
independently implemented raw-row headline audit both passed before this render
failure. Confirmatory generation continues at the previously frozen commit;
the plotting correction is applied only after complete blinded analysis.

The same outcome-blind hardening renders a judge sensitivity as `NA` when the
strict direct-answer parser has no complete paired blocks, rather than passing
nonfinite bounds to Matplotlib. Missing direct-parser estimates remain missing;
they are not imputed and do not affect the primary judge.

## Post-analysis visual QA

Date: 2026-07-11

After the frozen analysis and independent headline audit passed, visual QA of
the real-data figures found two presentation-only defects. The aggregate-panel
legend covered the paper's 0.16 amplification reference point, and the two
direct-parser `NA` markers sat too close to the lower axis. The legend was moved
to empty plot space, the missing markers were inset slightly, and the judge
panel received an explicit vertical margin. No data, label, interval, estimate,
threshold, verdict, or analysis file changed.
