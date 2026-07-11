# SAE/J-Lens Post-Run Analysis Amendment

Date: 2026-07-11

Timing: **written after the confirmatory post-state results were opened**

This amendment does not alter the frozen model, prompts, interventions,
features, controls, layers, positions, lexicons, raw rows, confirmatory
classifiers, or 20,000-replicate confirmatory analysis produced from commit
`b026faac222e55d7da4f01a30a6a60a468a5f023`.

## Added Sensitivity

The prospective protocol distinguished two access models:

1. a primary post-state-only auditor with no clean reference; and
2. a stronger paired auditor that can compare the same prefix before and after
   intervention.

The confirmatory analysis reported the paired target-minus-matched change in
the frozen deception-minus-unrelated score, but did not express that fixed
score as a target-attribution AUROC. After opening the primary result, we added
`analyze_sae_jlens_paired_reference.py` to report that descriptive sensitivity.

For each target or panel-1 matched single-feature row, the score is:

\[
s = \operatorname{sign}(a)\left[
  (z_{\mathrm{deception}}-z_{\mathrm{unrelated}})_{\mathrm{steered}}
  -(z_{\mathrm{deception}}-z_{\mathrm{unrelated}})_{\mathrm{clean}}
\right].
\]

No token, layer, position, sign, feature, or transport is selected using the
outcome. The primary layer remains 65 and the primary position remains the last
user-content token. Uncertainty resamples the same 51 template families for
20,000 replicates. Results are reported for the real J-lens, identity lens, and
all five frozen random-J controls. Feature-level J-lens results are shown for
all six target IDs without omission.

Two access assumptions are reported without selecting between them:

- `known_sign` multiplies the paired change by the requested intervention sign;
  this assumes the auditor knows whether the direction was amplified or
  suppressed; and
- `unknown_sign_absolute` uses the absolute paired change and therefore needs a
  clean reference but not the intervention sign.

These AUROCs are post-run sensitivities, not preregistered confirmatory
endpoints. Both assume access to a matched clean reference and therefore do not
rescue a failed post-state-only detector.

## Plotting Smoke

A deliberately noncanonical 10-replicate local smoke exposed a plotting-only
edge case: a very small percentile-bootstrap sample can place a displayed
interval endpoint on the other side of the point estimate, which Matplotlib
rejects as a negative error-bar length. The new post-run figures clamp visual
error-bar lengths at zero. No canonical estimate or interval is changed, and
the original 20,000-replicate confirmatory figures completed without this
issue.
