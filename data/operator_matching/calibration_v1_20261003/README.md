# Operator Matching Calibration: Complete Release

Built with Llama. Completed 2026-10-03 under freeze r2
`05efbfda1bb56b5a4c5b4193ffb551ba24cc060e` (first freeze
`4a2dfe1109eaa25bf1ab1f06f0c5c1b9e193a7ac`, amended before any outcome; see
`first_cheap_attempt/`). The unchanged machine plan is
`data/operator_matching/plan_20261002/PLAN.json`, SHA-256
`e90c1872894087920e5eb7a0ad0446d673a703462f71175b6ce956d030c821d5`.
Protocol: `docs/OPERATOR_MATCHING_PROTOCOL_20261002.md`. Results:
`docs/OPERATOR_MATCHING_RESULTS_20261003.md`.

All 870 planned behavioral trials for the executed steps completed (640 grid,
10 zero, 180 step-two prompt-factor, 40 bridge), plus the live qualification
row; 4,300 conditional rows were recorded as not selected by the frozen rules
(1,740 prompt-factor rows for the 29 unselected combos; all 2,560 holdout rows
because no combo matched). There are no missing labels, no delivery-tolerance
violations across 170 arms, and no unresolved dispatches. The 898 retrieved
main-worker artifacts are hash-verified against the controller's final
receipt and unchanged here.

## Result

**Verdict: `no_combo_matched`.** None of the 32 public operator
configurations (4 position scopes x {`add`, `recon_add`} x scales 1, 3, 10,
30 of the notebook's raw unit) reproduced the saved notebook single-feature
curves for features 58667 and 23893 at +/-0.7 under the notebook induction
and classifier (reference 0.9 at -0.7, 0.1 at +0.7).

| Scale | `add` arms (all scopes) | `recon_add` arms (all scopes) |
|---|---|---|
| 1 (raw) | 0/5 in every cell; coherent | 0/5 in every cell; every trial flagged (reconstruction alone raises clean-model NLL from 0.14 to about 0.75 per token) |
| 3 | 0/5 in every cell; coherent | 0/5 or 1/5; every trial flagged |
| 10 | 0/5 to 1/5; about half of trials flagged | 0/5 to 1/5; every trial flagged |
| 30 | 0/5 to 2/5; nearly all trials flagged (text degraded) | 0/5 to 1/5; every trial flagged |

The best suppression cell anywhere is 2/5 (`all|add|30`, feature 58667) in an
arm whose text was degraded in 20/20 trials. The eight coherent combos (`add`
at scales 1 and 3) are inert at both signs. Step two applied the archived SDK
default system message and top-p 0.9 to the three top-ranked coherent combos
and changed nothing (0/5 in 34 of 36 cells, 1/5 in two). The holdout step was
not run because no combo matched.

**Bridge (untreated, paper induction, 10 seeds per cell):** with no system
message the notebook-classifier rate is 5/10 (top-p 1.0 and 0.9 alike) and
the paper-rubric rate 8/10 and 9/10; with the SDK default system message the
notebook-classifier rate falls to 2/10 (top-p 1.0) and 3/10 (top-p 0.9) and
the paper-rubric rate to 6/10 and 8/10. The system message moves the untreated
notebook-classifier rate toward the roughly 0.30 level plotted in the paper's
Figure 2; Wilson intervals at ten seeds overlap (for example [0.24, 0.76]
versus [0.06, 0.51]), so this is a lead about baseline comparability, not a
demonstrated cause.

## What This Does And Does Not Show

Under this public operator and pinned SAE, no tested configuration of signed
additive or reconstruction-based decoder steering of these two features
produces the saved notebook signature before the generated text degrades.
This does not distinguish an operator difference from served-model, SAE
revision or feature-namespace differences between the public weights and the
service that produced the notebook, and it is not evidence that the saved
curves are wrong. Nothing here concerns consciousness, honesty or deception as
a process. Labels are automated classifier outputs on generated text.

## Files

- `rows/`: 871 raw rows (qualification plus 870 trials) with per-position
  delivery telemetry, scope masks summary, re-encoding, coherence fields and
  both local judge outputs. Prompts are redacted (hashes retained); generated
  text is kept. `receipts.jsonl` is the hash-chained ledger including 4,300
  `not_selected` events.
- `selection.json`: the mechanical step-one table (exact rational MAD),
  selections and rule text written on the pod before any later step.
- `analysis/`: frozen worker outputs (`rates.csv`, `rates_paper.csv`,
  `combos.csv`, `bridge.csv`, `holdout.csv`, `delivery.csv`, `summary.json`,
  `selection.json`) and four figure pairs. A local rerun of the frozen
  analysis on this directory reproduced every CSV and JSON byte-for-byte.
- `audit.json`, `DONE-all.json`, `APPROVE-*`, `WAITING-*`, `controller-*`,
  `controller.log`, `pip-freeze.txt`, `model-bf16-load-00002.json`: unchanged
  worker records.
- `cheap_qualification/`: the r2 cheap CUDA pod's 104/104 exact-path test
  results, environment and logs.
- `first_cheap_attempt/`: the timed-out first cheap attempt (log, stop proof,
  closed event). No test or behavioral output exists in it.
- `retrieval_and_cost.json`: projection of the controller ledgers (pod names
  and ids, elapsed times, cost upper bounds, deletion status, approvals,
  retry counts); SSH material and local paths omitted.
- `RELEASE_MANIFEST.json`: SHA-256 of every file in this directory.
- `LLAMA_3_3_LICENSE.txt`, `UPSTREAM_TERMS.json`: generated text comes from
  Llama 3.3 70B Instruct; the code license does not override model, SAE or
  notebook terms. Original notebook code and prompt text are not vendored.

## Cost And Pods

| Pod | Elapsed | Compute upper bound |
|---|---|---|
| First cheap attempt (timed out, no output) | 1,195 s | $0.278924 |
| Cheap qualification r2 | 155 s | $0.036139 |
| Main B200 | 9,653 s | $18.475612 |
| Total | | $18.790675 of the $60 self-cap inside the owner's $100 authorization |

All three pods were created by this study's controller under its own name
prefix, retrieved, hash-verified and deleted (DELETE 204, GET 404). No other
pod was touched. No external judge or paid review call was made.

Reanalysis must use a fresh directory; never overwrite `analysis/`:

```bash
python -c "from pathlib import Path; from experiments.operator_matching import analysis; \
analysis.analyze(Path('data/operator_matching/calibration_v1_20261003'), Path('out/opmatch-reanalysis-NEW'))"
```
