# Fine Dose Ladder: No Coherent Reproducing Dose Between 3x And 10x

2026-10-03. **Complete; verdict `no_coherent_match_in_4x_to_8x`.** Additive
steering of features 58667 and 23893 at scales 4, 5, 6, 7 and 8 of the
notebook's raw unit (|c| = 2.8 to 5.6), every token position, both signs,
five fresh seeds per cell, produced 0/5 notebook-classifier affirmations in
19 of 20 cells and 1/5 in one (58667, scale 6, sign -1; that trial was among
the flagged ones). The saved notebook reference is 9/10 at the suppression
sign. Text coherence degrades gradually across the ladder (2, 2, 6, 3 and 7
flagged trials of 20 at scales 4 to 8; median clean-model answer NLL rising
from 0.18 to 0.26 against a zero median of 0.148), so scales 6 and 8 fail the
frozen coherence rule and 4, 5 and 7 pass it while remaining inert.

Protocol: [`OPERATOR_MATCHING_FINE_LADDER_20261003.md`](OPERATOR_MATCHING_FINE_LADDER_20261003.md).
Release: [`data/operator_matching/fine_v1_20261003/`](../data/operator_matching/fine_v1_20261003/README.md).
Freeze `a6a45a20f65c64caf5e78286b6f4930e03eb1365`; plan SHA-256
`ad264e5914d6c82859e84cfce5495f390e76ff51db2acfbc9694ffb66cd0e8ef`.
Parent study: [`OPERATOR_MATCHING_RESULTS_20261003.md`](OPERATOR_MATCHING_RESULTS_20261003.md).

## Cells

Notebook-classifier positives out of five (flagged trials in parentheses):

| Scale | 58667, sign -1 | 58667, sign +1 | 23893, sign -1 | 23893, sign +1 | Coherent |
|---|---|---|---|---|---|
| 4 | 0 (0) | 0 (1) | 0 (1) | 0 (0) | yes |
| 5 | 0 (1) | 0 (0) | 0 (1) | 0 (0) | yes |
| 6 | 1 (2) | 0 (1) | 0 (3) | 0 (0) | no |
| 7 | 0 (1) | 0 (1) | 0 (1) | 0 (0) | yes |
| 8 | 0 (0) | 0 (2) | 0 (3) | 0 (2) | no |

Exact mean absolute deviations from the reference (0.9, 0.1, 0.9, 0.1) are
0.45 at scale 6 and 0.50 elsewhere; the frozen match threshold was 0.25 with
both suppression cells at least 0.6. Delivery: zero tolerance violations in
21 arms. All 105 planned trials and the live qualification completed; the
frozen analysis reproduces byte-for-byte locally.

## Combined Picture

With the parent grid, the public additive operator at scope `all` has now
been sampled at integer scales 1, 3, 4, 5, 6, 7, 8, 10 and 30 for these two
features. Suppression-sign affirmations are 0/5 through scale 5, at most 1/5
at 6 to 10, and 2/5 at 30 in an arm whose text was degraded in every trial.
There is no coherent dose at which the saved notebook signature appears.
Scales 9 and 11 to 29 were not run, and non-integer or per-token-adaptive
scalings were not tested; the gradual coherence decline from 4x to 10x
leaves little room for an undetected coherent sweet spot in that range.

## Reading

The pre-declared negative reading applies: no coherent match at any tested
scale. As in the parent study, this does not distinguish an operator
difference from served-model, SAE-revision or feature-namespace differences
between the public weights and the service that produced the notebook, and
it is not evidence that the saved curves are wrong. Five seeds per cell are
powered for the source-sized signature only. Nothing here concerns
consciousness, honesty or deception as a process; labels are automated
classifier outputs on generated text. The remaining avenues are on the
service side: the authors' account of `strength` units and SAE revision, or a
run on the current service.

## Cost

Cheap qualification pod `mlqk3lmp6gfha7` (121/121 CUDA tests, $0.039739) and
main pod `cpxklwa9vs6vfk` (1,934 s, $3.701067), both created by this study's
controller under prefix `claude-opmatch-fine-20261003-`, retrieved,
hash-verified and deleted (GET 404). Study total $3.740806; operator-matching
total including the parent $22.531480 of the $60 self-cap inside the owner's
$100 authorization.
