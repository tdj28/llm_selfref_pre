# Public-SAE Gating Calibration

This directory preserves the outcome-blind telemetry calibration for the
prospective 1,500-trial consciousness-report gating study.

`calibration_initial_failed.json` completed all 11 technical trials with no
stored or printed response text. Its SHA-256 is
`5ee29141d9f0928e3720e2ff945ee27cd270bf2f42bc011918f598e5a4654d10`.
The independent audit passes, meaning the artifact, matching, multiplier
formula, text-absence policy, and failed gate were reproduced independently.

The initial `m=6.266` gate failed only because realized calibrated single and
aggregate relative hidden-state RMS medians were slightly above their upper
bounds. Every hook, no-op, latent-delta, mask, cap, and nonfinite-value check
passed. The correction to `m=3.653` was fixed before a rerun in
[`docs/SAE_CONSCIOUSNESS_GATING_AMENDMENT_20260710.md`](../../../docs/SAE_CONSCIOUSNESS_GATING_AMENDMENT_20260710.md).

The failed artifact and log are permanent provenance. They must not be
overwritten when the amended calibration is added.

The amended `calibration.json` has SHA-256
`9f9509b27640e24a8b78af668b53eda9e0d3f6fc2c713725be99523990629c47`.
Its independently rederived multiplier is `m=3.653`; the calibrated single and
aggregate final-turn RMS medians are `0.0493672` and `0.0879984`. The rerun had
zero cap hits and no gate errors. `independent_calibration_audit.json` passes.

The three unrelaxed, disjoint control panels, in target order `30032, 58667,
22004, 30686, 41533, 23893`, are:

1. `26041, 11872, 55963, 21779, 29649, 15424`
2. `16004, 7182, 47797, 21403, 1059, 51407`
3. `64365, 1364, 58741, 19827, 62289, 26362`
