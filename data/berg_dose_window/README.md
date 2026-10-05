# Longer-Window Dose Screen

**The longer window did not pass the frozen untreated quality gate.** Three
of twelve fresh inductions reached the 512-token cap; the allowed maximum was
two. Notebook-label headroom passed at 5 positive and 7 negative labels. The
paper rubric labeled 9/12 positive. No labels were missing.

All three quality flags were first-turn cap hits. This is a mechanical stopping
rule, not a validated human judgment that those texts are incoherent. No
treated calibration trials or main trials were run, and no dose was selected.
The result does not exclude a steering effect at any nonzero dose.

The [protocol](../../docs/STEERING_DOSE_WINDOW_PROTOCOL_20261004.md) and
[plan](plan_20261004/PLAN.json) were frozen at
[`be48474c`](https://github.com/tdj28/llm_selfref_pre/commit/be48474c7f48d524e38970bea301dd6a623cca7b).
This fresh-sample amendment followed the observed
[256-token calibration](../berg_dose_ladder/README.md); the two samples are not
pooled. The protocol's preparation-time status is preserved with its frozen
bytes. This release records what actually ran.

## Evidence

- [Release report](zero_screen_v1_20261004/REPORT.json),
  [analysis](zero_screen_v1_20261004/analysis/summary.json), and
  [raw rows](zero_screen_v1_20261004/raw/rows/).
- [Fixture and no-op checks](zero_screen_v1_20261004/raw/rows/qualification-live.json):
  true zero preserved hidden state and output exactly; requested target/control
  aggregate norms matched. These do not validate nonzero delivered edits.
- [Figure data](zero_screen_v1_20261004/FIGURE_DATA.json) and
  [figures](zero_screen_v1_20261004/figures/): baseline observations only;
  main panels explicitly show that confirmation was not run.
- [Manifest](zero_screen_v1_20261004/MANIFEST.json) SHA256:
  `7f601f61bae97e9f39325cebed1c06e7c9aad737c47e2f78acc9f6f8d40a41e1`.

The new cheap CUDA check passed 44 tests. Cheap pod `pkhm0622b2pqo8` and main
pod `60u8duw2om0c08` were retrieved, hash-verified, and deleted, each with direct
GET404 verification. This attempt cost at most $2.110993030627623, bringing the
cumulative dose-study bound to $8.837266296602623, below its $50 cap.

## Verify

```sh
python -m experiments.mapping_window_release verify \
  --root data/berg_dose_window/zero_screen_v1_20261004 \
  --manifest-sha256 7f601f61bae97e9f39325cebed1c06e7c9aad737c47e2f78acc9f6f8d40a41e1
```

Verification reconstructs the analysis from preserved rows and rejects altered
derived artifacts. The release also binds the controller's deletion/cost record;
its original local receipt and ledger were checked before publication. Do not
overwrite the release or rerun collection under this completed plan.
