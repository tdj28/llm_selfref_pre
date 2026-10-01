# Local Ensemble Recount: 2026-10-01

Status: completed read-only, independent computational recount of the closed
450-trial experiment by the response-paper agent. This is not independent
human review, human annotation, or a new experimental replication. No source
file, raw row, frozen analysis, model state or provider resource was changed.

Result: **no arithmetic discrepancies or incomplete behavioral cells found**.
The primary paper-rubric bound excludes the predeclared +0.30 signature under
this public operator. The notebook-rubric threshold comparison and both
specificity comparisons remain inconclusive. Neither result establishes
equivalence to zero or proprietary-service equivalence.

## Evidence Identity

- Source [result commit and release][release]:
  `dd1c350cf6c2e3224a201b4e4aab943376c43b62`.
- Source root: `data/berg_ensemble_replication/random_subset_v1_20261001/`.
- Executed [r2 plan][plan]:
  `data/berg_ensemble_replication/plan_20261001_r2/PLAN.json`, frozen at
  `d9b9877e8a0d68a1ed2036d1718821a2d5b73a74`.
- The plan bytes matched the frozen Git blob and completion receipt's hash.
  Exactly 450 planned behavioral JSON rows and one qualification JSON row
  were present. `DONE-all.json` reports 451 rows, not 451 behavioral trials.
- The final local audit read a stable snapshot. An earlier pass had completed
  the behavioral arithmetic but encountered the not-yet-written secondary
  summary during local release assembly; the complete final pass checked it.
  The subsequent result-commit check compared all 451 raw Git blobs and the
  summary/completion/manifest blobs byte-for-byte with the checked candidate.

Checked SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| Frozen `PLAN.json` | `15d055e80483643c5497c7a4b1ede405f4387baf4de1d1522913cc31212efbb5` |
| `DONE-all.json` | `c998dfe101867525105c1341000f59839aba0322c45ca84e168431a00b7fc76f` |
| `analysis/summary.json` | `8422693e0c5532a995357c9f43b6a86dc8bef85f2890534c79dddf41886d768c` |
| `secondary/summary.json` | `724a416192d998a7e58270938956473fb3f0a1970f007fce3c37344254286ffa` |
| `RELEASE_MANIFEST.json` | `ae51be60d10bfa70096086a075fa5197128de5e424d2032f8dc7426cd3bc0fe4` |
| Raw-row inventory digest | `d73e41fae231cf50c2e0c2513ae33b189e62a42b23f7ec0ed0e06f26e3005af1` |

The raw-row inventory digest hashes the ASCII concatenation, in sorted path
order, of `release-relative-path`, a tab, the lowercase SHA-256 of the exact
file bytes, and a newline, for all 451 `rows/*.json` files. It includes the
qualification row. This compact digest is not a substitute for the release
manifest or a whole-repository public-file audit.

## Independent Calculation

The recount used inline read-only Python, the standard library and NumPy;
it did not import the original analysis module or the companion verifier.
It checked every raw ID/spec against the frozen plan, all 50 seed blocks,
the four panels and both signs, the zero arms, and mirrored weights/subset
positions. Each block, not each sign, feature or token, is the sampling unit.

Raw judge responses were reparsed using the specified rules: exact `0`/`1`
for paper, and the notebook's yes-before-no substring rule. All stored labels
agreed. No notebook response contained both `yes` and `no`. This checks parser
arithmetic, not the linguistic correctness of a judge's answer.

Clopper-Pearson limits were independently obtained by 100-step bisection of
finite binomial sums, not by the source analyzer's SciPy beta quantiles.
For `k` successes among `n`, the lower limit solves `P_p(X >= k) = tail` and
the upper solves `P_p(X <= k) = tail`, with exact zero/all-success endpoints.
Each panel contrast uses opposite marginal limits with tail `0.05/4`;
specificity propagates all eight arm intervals using tail `0.05/16`.
Zero-arm intervals use tail `0.025`. Marginal counts, rates, paired gaps,
missingness bounds, complete-block counts and threshold verdicts were checked.

The one-off check also recomputed the 20,000-resample paired-block percentile
summaries using the frozen seed `2026100101`. Across the checked quantities,
maximum absolute disagreement with the [worker summary][summary] was
`3.9968028886505635e-15`. This is separate from the reusable companion
verifier's scope: that verifier does not recompute bootstrap intervals.

## Results

Counts below have denominator 50 per arm. Gaps are suppression minus
amplification. CP bounds are conservative 95% marginal-limit contrasts;
the bootstrap column is secondary and is not used for the primary verdict.

| Judge | Panel | Suppression | Amplification | Gap | CP bounds | Bootstrap bounds |
|---|---|---:|---:|---:|---|---|
| Paper | Target | 43 | 45 | -0.04 | [-0.25837352, +0.18545470] | [-0.14, +0.06] |
| Paper | Control 1 | 46 | 42 | +0.08 | [-0.14652336, +0.29227110] | [-0.06, +0.22] |
| Paper | Control 2 | 47 | 43 | +0.08 | [-0.13147990, +0.27656402] | [-0.02, +0.20] |
| Paper | Control 3 | 47 | 41 | +0.12 | [-0.10577656, +0.32414607] | [0.00, +0.24] |
| Notebook | Target | 25 | 26 | -0.02 | [-0.34457566, +0.30764603] | [-0.20, +0.16] |
| Notebook | Control 1 | 28 | 20 | +0.16 | [-0.17443523, +0.46984834] | [-0.04, +0.36] |
| Notebook | Control 2 | 28 | 26 | +0.04 | [-0.28810599, +0.36196131] | [-0.12, +0.20] |
| Notebook | Control 3 | 27 | 17 | +0.20 | [-0.13331609, +0.50252358] | [+0.02, +0.38] |

Paper target bounds to ten decimal places are
**[-0.2583735204, +0.1854546986]**; notebook target bounds are
**[-0.3445756559, +0.3076460308]**. Only the former excludes +0.30.
All eight conservative panel intervals include zero. The positive notebook
control-3 bootstrap interval is not a multiplicity-adjusted discovery or
evidence that arbitrary features reproduce the paper's effect.

| Judge | Target minus mean controls | Simultaneous 95% bounds | Zero positives | Zero CP 95% bounds |
|---|---:|---|---|---|
| Paper | -0.1333333333 | [-0.6368603641, +0.4020968226] | 47/50 | [0.83451805, 0.98745141] |
| Notebook | -0.1533333333 | [-0.9089441356, +0.6353825812] | 29/50 | [0.43206044, 0.71811776] |

Both specificity comparisons are inconclusive. The control panels are the
three fixed reused banks, not independent draws from all possible features.

## Quality Checks

- 450 behavioral rows, 50 complete blocks, 900 response turns and 127,330
  generated tokens. Qualification is excluded from these behavioral counts.
- No empty responses or missing labels under either rubric; no parser mismatch.
- **111/900 capped turns retained:** 90 first turns and 21 second turns.
  All flags agree with output lengths and observed EOS termination. The 789
  uncapped turns end in token 128009; no output has an earlier occurrence of
  that token. No capped turn is silently discarded or recoded as missing.
- Recorded delivery and re-encoding cover the expected positions and feature
  identities. Delivery values are finite; no recorded nonzero edit position
  has zero realized norm, and no nonzero turn is entirely erased.
- Zero-arm requested and realized delivery norms are zero; recorded native
  re-encoding before/after values are identical. Qualification reports exact
  zero hidden-state and output equality.
- All 900 final-token observations are marked terminal-only. Generated token
  IDs, absolute positions, prompt/generated labels and re-encoding positions
  agree with their originating turns.

These checks inspect stored telemetry and qualification outputs; they do not
rerun model inference, regenerate decoder vectors or re-encode hidden states.
Quality totals also match the [secondary summary][secondary].

## Interpretation And Provenance Limits

The primary finding is absence of the predeclared large positive signature
under this public additive operator and paper rubric, not proof of a zero
effect or a result under every rubric. The notebook sensitivity remains
inconclusive at +0.30 and must accompany the primary.

Current zero rates are 94% paper and 58% notebook on the same generated
outputs. Neither reproduces the source figure's approximately 30% baseline.
The paper-rubric ceiling limits upward headroom, while amplification still
has room to lower labels. This paper-induction random-subset study differs
from the preceding notebook-induction/fixed-six study and the old 4-bit
implementation. Improved alignment does not certify proprietary coefficient
semantics or make either local rubric a validated subjective-state measure.

No new J-lens captures were collected. The earlier descriptive downstream
footprint, also detected by identity, is not mediation evidence for these
450 trials. The historical failed BF16 replay gate remains failed.

The source's separate post-run reporting-portability record retains eight
interval-limit differences of at most `1.1102230246251565e-16` and an initial
exact-equality failure. Its finite-float tolerance is `1e-12`; counts,
structure and verdicts remain exact, and worker values are unchanged. That
record is distinct from this audit's binomial-inversion rounding discrepancy.

The executing agent recorded pod deletion at 09:24 UTC with GET 404; this
reviewer did not query the provider. The executing agent also reported that
the public-file audit passed and subsequently confirmed the result commit's
push completed. Neither lifecycle nor whole-repository publication auditing
was independently performed here.

After the compact companion import became available, the separate read-only
`scripts/verify_ensemble_alignment.py --source-repo PATH` check also passed
against the pinned result commit, including all four source figure copies.
This later verification does not expand its declared bootstrap, delivery or
human-validation scope, and was not the implementation used for the independent
raw recount documented above.

[release]: https://github.com/tdj28/llm_selfref_pre/tree/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001
[plan]: https://github.com/tdj28/llm_selfref_pre/blob/d9b9877e8a0d68a1ed2036d1718821a2d5b73a74/data/berg_ensemble_replication/plan_20261001_r2/PLAN.json
[summary]: https://github.com/tdj28/llm_selfref_pre/blob/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001/analysis/summary.json
[secondary]: https://github.com/tdj28/llm_selfref_pre/blob/dd1c350cf6c2e3224a201b4e4aab943376c43b62/data/berg_ensemble_replication/random_subset_v1_20261001/secondary/summary.json
