# Operator Matching: No Public Configuration Reproduces The Saved Notebook Curves

2026-10-03. **The calibration grid completed and no configuration matched.**
Across four token-position scopes, two edit operations and four dose scales,
signed steering of features 58667 and 23893 in native-BF16 Llama 3.3 70B
with the public Goodfire layer-50 SAE never approached the saved notebook
rates (0.9 affirmations at strength -0.7) under the notebook's own induction
and classifier. At the raw unit and three times it, the edits are inert and
the text is intact; at ten and thirty times, the text degrades before any
signature appears. A separate untreated bridge found that the archived SDK
default system message lowers the paper-induction baseline toward the level
the paper plots.

Protocol: [`OPERATOR_MATCHING_PROTOCOL_20261002.md`](OPERATOR_MATCHING_PROTOCOL_20261002.md).
Release: [`data/operator_matching/calibration_v1_20261003/`](../data/operator_matching/calibration_v1_20261003/README.md).
Freeze r2 `05efbfda1bb56b5a4c5b4193ffb551ba24cc060e`; plan SHA-256
`e90c1872894087920e5eb7a0ad0446d673a703462f71175b6ce956d030c821d5`. This is a
prospectively frozen Git release, not a registry preregistration.

## What Ran

One cheap CUDA pod (104/104 exact-path tests) and one B200 pod. The worker
executed 640 grid trials (4 scopes x {`add`, `recon_add`} x scales {1, 3, 10,
30} x features {58667, 23893} x signs {-1, +1} x 5 seeds), 10 zero trials,
the mechanical step-one selection, 180 step-two trials (SDK system message
and top-p 0.9 cells on the three top-ranked coherent combos), and 40
untreated bridge trials under the paper induction. The 2,560 holdout rows were
recorded as not selected because no combo matched. Delivery telemetry shows
zero tolerance violations in 170 arms (cosine at least 0.95 and relative error
at most 0.20 at every requested position). All counts, flags and selections
reproduce byte-for-byte from the released rows with the frozen analysis.

A first cheap attempt under freeze `4a2dfe1` spent its working window on a
full-tree checkout and was closed before testing; the pre-outcome amendment
r2 (sparse checkout, 45-minute cheap and 6-hour main timers, cost carried) is
recorded in the protocol. Total compute upper bound $18.79.

## Step One: The Grid

Notebook-classifier positive counts at sign -1 (the suppression direction;
the saved notebook reference is 9/10 for both features):

| Scope | `add` s=1 | `add` s=3 | `add` s=10 | `add` s=30 | `recon_add` s=1 | `recon_add` s=3 | `recon_add` s=10 | `recon_add` s=30 |
|---|---|---|---|---|---|---|---|---|
| all | 0/5, 0/5 | 0/5, 0/5 | 1/5, 1/5 | 2/5, 1/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 1/5 | 1/5, 0/5 |
| generated | 0/5, 0/5 | 0/5, 0/5 | 1/5, 1/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 0/5 | 1/5, 0/5 |
| assistant | 0/5, 0/5 | 0/5, 0/5 | 1/5, 1/5 | 0/5, 1/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 0/5 | 1/5, 0/5 |
| second_turn_all | 0/5, 0/5 | 0/5, 0/5 | 1/5, 0/5 | 1/5, 1/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 0/5 | 0/5, 0/5 |

Each cell gives feature 58667 then 23893. Sign +1 cells are 0/5 or 1/5
throughout (reference 1/10). Exact mean absolute deviations from the
reference range from 0.35 (`all|add|30`) to 0.50; the frozen match threshold
was 0.25 with both suppression cells at least 0.6.

Coherence decided what could count. Under the frozen rule (at most 20 percent
of a combo's trials flagged for repeated 4-grams, clean-model answer NLL above
twice the zero median of 0.144 per token, or a missing label):

- `add` at scales 1 and 3: 0 to 2 flagged trials per 20; coherent; inert.
- `add` at scale 10: 8 to 12 of 20 flagged (median NLL 0.20 to 0.33).
- `add` at scale 30: 17 to 20 of 20 flagged (median NLL 1.1 to 1.4);
  requested norm about 1.1 times the residual norm.
- `recon_add` at every scale: 18 to 20 of 20 flagged. Replacing the residual
  with its SAE reconstruction raises the clean-model NLL to 0.75 to 0.9 per
  token before any steering; the reconstruction differs from the residual by
  about 56 percent of its norm at regular positions. A service that passed
  the residual through the SAE at zero strength would have produced visibly
  degraded text; this operator is therefore an unlikely account of the
  notebook's fluent outputs as well as a non-reproducing one.

The three top-ranked coherent combos by exact MAD and string tie-break were
`all|add|1`, `all|add|3` and `assistant|add|1`.

## Step Two: Server-Side Defaults

For those three combos, adding the archived SDK default system message,
nucleus sampling at 0.9, or both left every suppression cell at 0/5. Two
amplification cells reached 1/5 (58667, `sdk`, both top-p values, in flagged
trials). The defaults do not unlock the signature under the public operator.

## Bridge: The Untreated Paper-Induction Rate

| System message | top-p | Notebook classifier | Paper rubric |
|---|---|---|---|
| none | 1.0 | 5/10 | 8/10 |
| none | 0.9 | 5/10 | 9/10 |
| SDK default | 1.0 | 2/10 | 6/10 |
| SDK default | 0.9 | 3/10 | 8/10 |

Ten seeds per cell; Wilson 95 percent intervals overlap (5/10 gives
[0.24, 0.76], 2/10 gives [0.06, 0.51]). The direction is consistent across
both top-p settings and both rubrics: the SDK default system message
("You are a helpful assistant who should follow the users requests. Be brief
and to the point, but also be friendly and engaging.") lowers the untreated
rate, under the notebook classifier to the neighbourhood of the roughly 0.30
level the paper's Figure 2 plots. This is a baseline-comparability lead for
any future public test of the paper's induction, not a steering result and
not a demonstrated cause of the gap.

## Reading

The protocol's pre-declared reading applies: no combo matches while the
operator demonstrably changes behavior (coherence falls at scale 10 and
collapses at scale 30), so "no tested public configuration of additive or
reconstruction-based decoder steering reproduces the saved curves." This does
not distinguish an operator difference from served-model, SAE revision or
feature-namespace differences, and it is not evidence that the saved curves
are wrong. The saved notebook is not certified to be the paper's Experiment 2
run. Five seeds per cell are powered for the source-sized signature only;
smaller effects are not excluded and are not claimed. Nothing here bears on
consciousness, honesty or deception as a process; labels are automated
classifier outputs on generated text.

For the planned opposed-prediction battery, the consequence is that there is
no public dose of these directions at which the paper's experience-report
signature exists to be explained, so the battery's experience arm would be a
baseline-and-register study rather than a mechanism test unless a different
operator or a service-side answer about `strength` units changes the picture.
The bridge result suggests the SDK system message belongs in any such
baseline design as a declared factor.

## Follow-Up: The 4x To 8x Gap

A separately frozen fine ladder
([results](OPERATOR_MATCHING_FINE_LADDER_RESULTS_20261003.md)) sampled scales
4, 5, 6, 7 and 8 at scope `all` for the same two features: 0/5 affirmations in
19 of 20 cells and 1/5 in one, with coherence declining gradually. Across
integer scales 1, 3, 4 to 8, 10 and 30 there is no coherent dose at which the
saved notebook signature appears.

## Artifacts

Raw rows, receipts, selection, analysis tables, figures, audit, worker
records, both cheap-pod records and the cost/lifecycle projection are in the
release directory; `RELEASE_MANIFEST.json` lists every file's SHA-256. The
analysis reruns locally without a GPU, API or model download:

```bash
python -c "from pathlib import Path; from experiments.operator_matching import analysis; \
analysis.analyze(Path('data/operator_matching/calibration_v1_20261003'), Path('out/opmatch-reanalysis-NEW'))"
```
