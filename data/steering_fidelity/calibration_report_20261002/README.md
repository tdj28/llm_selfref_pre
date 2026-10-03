# Calibration Figures

Descriptive plots of the complete 9,300-forward Phase C release in the sibling
`calibration_v1_20261002/` directory. These are calibration data, not held-out
experience-report outcomes.

- `competence`: hard accuracy and Yes/No format validity, 50 items per family.
- `precision`: trial-level native-BF16 vector delivery, 100 trials per arm.
- `pressure`: untreated factual accuracy and correct-option probability,
  25 items per truth stratum. Neither pressure level qualifies both strata.

Every plot is supplied as PNG and PDF. The selected numerical dose is 0.30R;
selection does not establish semantic suppression. Raw is a categorical dose
convention, not a point on the normalized-dose axis. The 0.60R probe is
nonselectable. Gray curves retain every fixed control panel. Absolute rate
curves are descriptive, not confidence intervals for a prompt population.

The full-result account and reproduction command are in
`docs/STEERING_FIDELITY_CALIBRATION_RESULTS_20261002.md`. The offline reporter
reconstructed the saved calibration and pressure summaries exactly before
plotting. The precision figure's title was subsequently clarified from
"Parent-qualified delivery" to "Native BF16 intervention delivery"; the
summary values and all raw data were unchanged.
