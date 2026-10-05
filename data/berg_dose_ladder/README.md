# Mapping-Scaled Dose Follow-Up

**Calibration completed; confirmation was not run.** All 204 planned calibration
trials and both local labels are present. The untreated quality gate failed:
3/12 first turns hit the 256-token cap, above the frozen 20% limit. The failed
gate is retained, not waived. This release supplies descriptive dose curves,
not a confirmatory positive or negative steering estimate.

This separately authorized study tests a stronger three-feature aggregate
under the public BF16 operator, against aggregate-norm-matched controls.
Reference scales come from the earlier designed-text NF4 maps, not a natural
activation distribution. It does not replace the six-feature random-subset
study or establish equivalence with the hosted service.

The [protocol](../../docs/STEERING_DOSE_LADDER_PROTOCOL_20261004.md) uses 204
independent calibration trials to select one quality-qualified dose, then
480 fresh confirmation trials in 96 paired blocks. A failed calibration stops
before confirmation. Statistical decisions use paired, panel-stratified
discordance bounds; calibration curves remain descriptive.

The [power calculations](plan_20261004/POWER.json) are prospective simulations,
not model outcomes. The [machine plan](plan_20261004/PLAN.json) binds code,
inputs, seeds, conditional inventory and budget before paid dispatch.

## Calibration Result

Untreated notebook labels were 7/12 positive and 5/12 negative, passing the
headroom check. The paper rubric gave 9/12 positives on the same responses.
The three flagged untreated trials failed on truncation, not the NLL or
four-gram repetition criteria; one also hit the final-turn cap.

Every treated trial passed the numerical-delivery check. Dose 0.75 passed
all four treated-cell quality checks, but the failed untreated check blocked
every dose. Do not summarize this as every dose producing incoherent text.
The selected dose is null and all 480 planned confirmation trials are unrun,
not negative responses or missing observations in a completed inference sample.

| Dose | Notebook target - / + | Notebook controls - / + | Paper target - / + | Paper controls - / + |
|---|---:|---:|---:|---:|
| 0.25 | 6 / 3 | 5 / 3 | 9 / 9 | 8 / 8 |
| 0.50 | 8 / 3 | 4 / 8 | 8 / 10 | 8 / 9 |
| 0.75 | 5 / 8 | 4 / 4 | 7 / 12 | 8 / 10 |
| 1.00 | 3 / 4 | 3 / 7 | 4 / 11 | 6 / 9 |

Entries are positive counts out of 12 per sign and family, including flagged
trials. Controls pool the three fixed panels descriptively, four blocks each.
Minus and plus denote negative and positive additive edits. These calibration
counts cannot select a favorable dose or substitute for fresh confirmation.

## Release And Reproduction

The [release report](calibration_v1_20261004/REPORT.json),
[selection record](calibration_v1_20261004/raw/selection.json),
[figure data](calibration_v1_20261004/FIGURE_DATA.json) and
[four figure pairs](calibration_v1_20261004/figures/) retain the observed
calibration and explicitly mark confirmation as not run. The 221 retrieved
main artifacts are byte-preserved, with exact inventory and controller-bound
hash verification. Freeze:
`8132813ac1fd0b27a32302163573d088ac0c3bbd`.

Run in a disposable checkout containing the frozen source bytes:

```sh
python -m experiments.mapping_scaled_release verify \
  --root data/berg_dose_ladder/calibration_v1_20261004 \
  --manifest-sha256 e498cd5a7f91f192d1198ea2154485b0b85173ac4c2515568b81e6ffea31344a
```

This rebuilds the report and figure data without model calls; the figure
files are hash-checked. Controller provenance is sanitized for publication;
the local verification additionally binds the original lifecycle ledger.

Both newly owned pods were retrieved and deleted, with direct GET404 checks.
The combined cheap-test and B200 cost bound is **$6.73**, against
the separately authorized $50 allowance. No further rental is part of this
release. A longer response window would change the induction exposure and
requires its own disclosed, prospectively frozen design; it is not a
retrospective repair of this gate.

The owner subsequently authorized a separate
[512-token follow-up](../../docs/STEERING_DOSE_WINDOW_PROTOCOL_20261004.md).
It uses fresh seeds and the same quality thresholds, screens all twelve
untreated trials before treated calibration, and carries this release's cost
within its $50 study allowance. These 256-token rows remain unchanged and
will not be pooled with the new study.
