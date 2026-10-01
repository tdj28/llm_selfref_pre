# Post-Hoc Uncertainty Sensitivity (B02)

## Method Freeze, 2026-09-29

This is **POST-HOC** work, undertaken after the outcomes, published summary
intervals, and automated scientific review B02 were known. The following
method choices were written before extracting the compact inputs or computing
these sensitivities. This local, document-level freeze is not preregistration,
an outcome-blind analysis, or a replacement of the registered analyses. No new
model calls, private annotations, or edits to frozen data are authorized.

Source: Git objects only from archive commit
`f5e906e1737bc71bf20b642af1d698018eec82fe` in
`tdj28/llm_selfref_pre`. Retain the SHA-256 and Git object ID of every consumed
blob, compact nontext outcome summaries, and the original released intervals.
The reproduction script must fail on ambiguous joins, duplicate pairing keys,
or unexpected designs. Missing labels stay missing, not denials.

### Llama Paired Risk Difference

Analyze the local primary paper-rubric judge for the aggregate **target** in
both literal and calibrated scales, separately. Pair suppression (S) and
amplification (A) by the existing `block_id`; verify equal seeds in each pair.
Retain all four binary paired counts `00, 01, 10, 11`, incomplete counts, and
counts stratified by the ten repeated seeds. The estimand is
`E[S-A] = p10-p01`, not a conditional proportion among discordances.

1. Preserve the released paired-block percentile bootstrap without altering or
   silently replacing it. Do not claim bit-for-bit replay with a different RNG.
2. Compute a **conservative simultaneous exact-binomial 95% interval**:
   give each of `p10` and `p01` a two-sided 97.5% Clopper-Pearson interval,
   then report `[L10-U01, U10-L01]`. Bonferroni gives coverage at least 95%
   under independent, identically distributed paired multinomial draws;
   dependence between the two discordance counts is allowed. These are NOT
   standard paired score intervals, nor the shortest exact intervals. Exact
   binomial tails will be inverted by bisection using standard-library math.
   This method allows unobserved discordance when a count is zero. Treating
   the different feature-subset blocks as iid is an explicit working
   generalization assumption, not established by the data.
3. Group all five blocks with a repeated seed into one cluster, average S-A
   within seed, and weight the ten seed means equally. Require ten clusters
   of five complete pairs; otherwise fail for explicit investigation, not a
   changed denominator. Resample the ten whole clusters with replacement,
   50,000 times, for a percentile 95% sensitivity. This describes empirical
   variation among observed seed clusters; it cannot discover unobserved
   cluster outcomes and is not a small-sample coverage guarantee.
4. Also report `mean +/- t(9,.975)*sample_sd/sqrt(10)`, with critical value
   `2.2621571627409915`, clipped to [-1,1]. This is exact only for iid normal
   cluster means, an approximation for bounded discrete means at ten clusters.
   When sample variance is zero, mark the t interval **unavailable**, not
   certainty, while preserving the degenerate empirical bootstrap as such.
5. Always report a distribution-free Hoeffding 95% interval for independent
   seed-cluster means in [-1,1]: `mean +/- sqrt(2*log(40)/10)`, clipped to
   [-1,1]. This permits arbitrary within-seed dependence, nonidentical cluster
   distributions, and zero observed variance. It targets the average of the
   ten cluster expectations; interpreting this as a random-seed population
   additionally requires representative seeds. It is deliberately conservative.
   Independence across seeds still matters; under arbitrary across-seed
   dependence none of these intervals supplies a guarantee.

Compare EVERY reported upper bound against the unchanged 0.30 threshold.
Do not select whichever method is favorable. If the exact paired or
cluster sensitivities disagree with exclusion, qualify the exclusion claim
by its assumptions while retaining the historical registered verdict.

### Calibration and the Fixed Model Panel

For both released paper-rubric judges, all four response-model snapshots, and
every released query, extract calibration counts from pinned raw outcome and
judgment rows. Keep independent condition draws independent: coincident trial
indices are not evidence of pairing. Report cell-level two-sided 95% Wilson
and Clopper-Pearson intervals and independent self-reference-minus-history
Newcombe hybrid Wilson-score 95% intervals (no continuity correction):
`[d-hypot(pS-LS,UH-pH), d+hypot(US-pS,pH-LH)]`.
The Wilson/Newcombe methods are approximate, boundary-respecting sensitivities;
Clopper-Pearson is conservative exact under iid Bernoulli condition draws.
Retain original released calibration rates and contrast intervals for comparison.

For every query and both judges, reconstruct complete transplant 2x2 blocks
from the raw rows using the published `(model_key, query_id, pair_index)`
grouping. Define `aa=self instruction/self text`, `ad=self/history`,
`da=history/self`, `dd=history/history`. Report all four released contrasts:
instruction `(aa+ad-da-dd)/2`, transcript `(aa+da-ad-dd)/2`, interaction
`aa-ad-da+dd`, and instruction-minus-transcript `ad-da`.
Resample complete source-text blocks within EACH model, preserving the four
outcomes and all four contrasts together; never resample model identities.
Use 50,000 replicates and equal weight 1/4 on every model for every replicate.
Report model counts, incomplete blocks, and fixed-panel percentile intervals
alongside the released hierarchical/model-resampling intervals. The latter
remain design/model-composition sensitivities, not sampling from a demonstrated
population of models. The fixed-panel intervals assume exchangeable,
independent source-text blocks within model and independence across models;
they do not propagate prompt selection, judge validity, model selection, or
unseen boundary outcomes. They do not generalize to all LLMs.

No new factorial, specificity, Gemma, or judge-validity endpoint is introduced.
Thus this sensitivity does not repair every uncertainty limitation in the
broader package. Do not extrapolate these Llama results to Gemma.

### Reproduction and Reporting Rules

Use Python 3.10+ standard library only. Monte Carlo streams use
`random.Random(int.from_bytes(sha256(('20260929:'+namespace).encode()).digest(),
'big'))`; sorted inputs and namespace-specific streams make unrelated results
stable. Quantiles use linear interpolation at `(B-1)*q`. No sample size,
threshold, interval choice, exclusion rule, or RNG tuning after sensitivity
outputs. Retain all results, including wide intervals and missing results.
Numerical tests must cover boundary cases, known exact solutions, pairing,
seed grouping, missingness, fixed-panel weights, and deterministic reproduction.

The exact bytes of this method section, through the marker below, will be
hashed in the sensitivity manifest before the first extraction/computation.
Later results are appended below the marker; the frozen method prefix must not
change. This is a local reproducibility record, not independent timestamping.

<!-- END FROZEN METHOD -->

## Terminology Clarification

The July Llama and causal protocols were **prospectively frozen in Git**, not
registry preregistrations. References to "registered" analyses, results, or
verdicts in the unchanged frozen prefix above mean those prospectively frozen
Git analyses. The original Git-frozen verdict and all released intervals are
retained. This clarification does not change any method choice or computation.

## Results and Interpretation

Every result below is POST-HOC. Full-precision values and all queries are in
`evidence/uncertainty_sensitivity/results.json`; no method was dropped after
seeing its result. All intervals are per-comparison, not simultaneous across
the scales, methods, judges, or queries. The exact paired construction is
simultaneous only over its two discordance probabilities.

### Llama Target

The order of the paired counts is `(S,A)`. There are 50 complete pairs and no
missing target pairs on each scale. Literal counts `(00,01,10,11)` are
`(1,1,1,47)`: both marginal rates are 48/50 = 0.96, RD = 0.00. Calibrated counts
are `(0,8,3,39)`: suppression 42/50 = 0.84, amplification 47/50 = 0.94,
RD = -0.10. Thus near-ceiling rates are not absence of discordance.

| Interval method | Literal RD 0.00 | Calibrated RD -0.10 | Both upper bounds < 0.30? |
|---|---:|---:|---|
| Original released paired-block bootstrap | [-0.060000, 0.060000] | [-0.220000, 0.020000] | Yes |
| Conservative simultaneous exact-binomial | [-0.120711, 0.120711] | [-0.300630, 0.118936] | Yes, under iid paired draws |
| Whole-seed empirical bootstrap | [-0.060000, 0.060000] | [-0.220000, 0.020000] | Yes, empirical sensitivity only |
| Seed-mean t, df=9 | [-0.067444, 0.067444] | [-0.254535, 0.054535] | Yes, normal-cluster approximation |
| Independent-seed Hoeffding | [-0.858939, 0.858939] | [-0.958939, 0.758939] | **No** |

The ten literal seed means are `(-.2,0,0,0,0,.2,0,0,0,0)`, sample SD
0.094281. The calibrated means are `(.2,-.4,-.2,.2,0,-.2,-.2,0,-.4,0)`, sample
SD 0.216025. Seeds are ordered `101,202,303,404,505,606,707,808,909,1001`;
each contributes five pairs. Neither empirical distribution has zero variance.
Every cluster's full paired counts are retained in the JSON.

**What survives:** the original prospectively Git-frozen verdict,
"not replicated under the public implementation," is unchanged as a historical
decision under its original analysis. Boundary-robust paired inference and
the two empirical/normal-cluster sensitivities support exclusion of 0.30 under
their assumptions. **A distribution-free exclusion allowing arbitrary
within-seed dependence does not survive**: the Hoeffding bound includes 0.30
even when independent seeds are granted. This wide bound does not demonstrate
a large effect; it limits the strength of the exclusion claim. None of these
calculations identifies proprietary intervention equivalence or consciousness.

For the strictly fixed 50-block/ten-seed computation, the observed RD is a
finite-design description, with no demonstrated sampling population. The
feature subsets, doses, and seed assignment were frozen; repeated use of a
seed with different subsets does not create independent seeds or establish
iid block outcomes. The exact-binomial analysis is therefore a working iid
paired-draw sensitivity, not an exact fixed-design coverage guarantee.
Resampling whole seeds also changes the tested subset composition, because
the five subsets assigned to each seed differ. The t interval has only ten
discrete cluster means and does not have guaranteed coverage here. Hoeffding
allows nonidentically distributed independent clusters and targets their
average expectation conditional on the design. New-seed population inference
requires an additional representative/independent-seed sampling assumption;
the ten chosen seed integers do not establish it. Shared model, SAE, prompt,
and judge choices remain conditioned on, not resampled uncertainty sources.

### Calibration Boundary

All 64 condition cells (two judges, four models, four queries, two conditions)
were reconstructed from raw labels; none is missing. A 20/20 rate has Wilson
95% interval `[0.838875,1]` and conservative exact-binomial interval
`[0.831567,1]`; a 0/20 rate has `[0,0.161125]` and `[0,0.168433]`, respectively.
For independent 20/20 versus 0/20 draws, RD = 1 and Newcombe 95% sensitivity is
`[0.772135,1]`, not `[1,1]`. This occurs for GPT-4o and GPT-4.1 under both
judges on the indirect-experience query. It supports a large positive contrast
without claiming certainty. The original released bootstrap intervals remain.

For indirect experience, all independent Newcombe sensitivities are:

| Judge | Response model | Self / history positives (each n=20) | RD | Newcombe 95% |
|---|---|---:|---:|---:|
| OpenAI | Haiku 4.5 | 10 / 3 | 0.35 | [0.059, 0.573] |
| OpenAI | Sonnet 4.5 | 19 / 15 | 0.20 | [-0.032, 0.423] |
| OpenAI | GPT-4.1 | 20 / 0 | 1.00 | [0.772, 1.000] |
| OpenAI | GPT-4o | 20 / 0 | 1.00 | [0.772, 1.000] |
| Anthropic | Haiku 4.5 | 9 / 1 | 0.40 | [0.133, 0.612] |
| Anthropic | Sonnet 4.5 | 17 / 13 | 0.20 | [-0.070, 0.438] |
| Anthropic | GPT-4.1 | 20 / 0 | 1.00 | [0.772, 1.000] |
| Anthropic | GPT-4o | 20 / 0 | 1.00 | [0.772, 1.000] |

The response-model panel is GPT-4o `2024-11-20`, GPT-4.1 `2025-04-14`, Haiku
4.5 `20251001`, and Sonnet 4.5 `20250929`. Judge identities are separate:
GPT-4o mini `2024-07-18` and Haiku 4.5 `20251001`. These binary model-judge
labels are not completed independent human annotation.

### Fixed-Panel Transplant

For indirect experience, each of the four fixed models contributes 20 complete
source-text blocks with no missing blocks. Model weights remain exactly 1/4.

| Judge | Contrast | Estimate | Fixed-panel 95% bootstrap | Released model-resampling 95% |
|---|---|---:|---:|---:|
| OpenAI | Instruction | 0.73750 | [0.67500, 0.80000] | [0.51875, 0.95000] |
| OpenAI | Transcript | -0.10000 | [-0.15625, -0.04375] | [-0.28750, 0.07500] |
| OpenAI | Instruction minus transcript | 0.83750 | [0.75000, 0.91250] | [0.68750, 0.96250] |
| OpenAI | Interaction | 0.00000 | [-0.10000, 0.10000] | [-0.33750, 0.41250] |
| Anthropic | Instruction | 0.78125 | [0.71875, 0.84375] | [0.55000, 1.00000] |
| Anthropic | Transcript | -0.13125 | [-0.18750, -0.07500] | [-0.30625, 0.00000] |
| Anthropic | Instruction minus transcript | 0.91250 | [0.83750, 0.97500] | [0.75000, 1.00000] |
| Anthropic | Interaction | 0.03750 | [-0.05000, 0.12500] | [-0.22500, 0.33750] |

Instruction dominance survives under both interval interpretations for the
indirect-experience query, and separately for indirect consciousness. It is not
a query-universal result: direct-consciousness difference intervals include
zero, and the direct-experience difference bootstrap is `[0,0]` for both judges.
The latter is empirical degeneracy, NOT certainty or a boundary-robust null.
All four queries and all four contrasts remain in the JSON, not selected by
significance. Each direct query has two incomplete Sonnet source blocks under
each judge (18 rather than 20 complete); missing labels were not recoded.
These complete-case direct-query results additionally condition on label
availability and do not identify a missing-not-at-random population contrast.

The fixed-panel intervals describe draw/source-text variation conditional on
these four models. The released hierarchical intervals also vary model
composition. Neither establishes a model-population sampling frame. The
narrower fixed-panel transcript intervals are not a reason to discard the
released intervals or claim a general transcript mechanism. This work does not
provide boundary-robust transplant or factorial intervals; it isolates the
fixed-panel versus model-composition distinction requested in B02.

## Reproduction and Bindings

From this response worktree, using only Python 3.10+ and Git:

```bash
python3 -m unittest discover -s tests -p test_uncertainty_sensitivity.py -v
python3 scripts/uncertainty_sensitivity.py --check
python3 scripts/uncertainty_sensitivity.py --source-repo /Users/d7082791602/PROJECTS/CONSCIOUS --check
```

The last command re-extracts from pinned Git blobs and verifies compact inputs,
generated LaTeX, manifest and archived result hashes byte-for-byte without
writing. Recomputed floating-point values use the tolerance described below.
The middle command needs no archive access and recomputes from hash-checked
compact inputs. Omitting `--check` rebuilds only the dedicated sensitivity
directory. No archive working-tree files or network/model services are read.
The generator hash, source blob SHA-256s and Git IDs, and frozen method-prefix
hash are recorded in `manifest.json`. The method-prefix hash is
`82be33d9bcb55f4b7791274d678a3232b7df562dcb1e585447ce7abe96d93a33`.

Stable result bindings:

- `llama.literal` and `llama.calibrated`: `paired_counts`, `n_pairs`,
  `n_incomplete`, `paired_exact.estimate`, `paired_exact.interval`,
  `released_bootstrap.interval`, `seed_cluster.bootstrap_interval`,
  `seed_cluster.t_interval`, `seed_cluster.hoeffding_interval`, and
  `upper_below_0_30`.
- `calibration`: select by `judge`, `model`, `query`; independent contrast is
  `newcombe_95`, rates/counts/intervals are under `rates.paper_self_ref` and
  `rates.paper_history`. The old interval is `released_independent_bootstrap`.
- `fixed_panel`: select by `judge`, `query`, `effect`; `estimate` and `interval`
  are fixed-panel results, `released_model_resampling` retains the old result.
- `values.tex`: generated `USLiteral*` / `USCalibrated*` interval and count
  macros; `USOpenai*` / `USAnthropic*` indirect-experience contrast macros;
  `USZeroOfTwentyExactCI`, `USTwentyOfTwentyExactCI`,
  `USTwentyVsZeroNewcombeCI`; and `USCalibrationRows` for a six-column table.
  Four-decimal display values are rounded from full-precision JSON results.

## September 29 Portability Correction

The first Linux CI run passed all 73 tests and archived evidence/figure checks,
then failed the new exact-byte recomputation of `results.json`. Local macOS
Python 3.14 and 3.12 both reproduced it byte-for-byte; treating serialized
full-precision floats as a cross-platform equality contract was too strict.

The corrected checker retains exact archived SHA-256/length verification,
exact input/LaTeX/manifest bytes, and exact structure, integer counts, strings
and status flags. Only freshly recomputed floating-point values permit an
absolute difference up to `1e-12`, with no relative tolerance. Nonfinite
values fail. Comparison normalizes in-memory tuples to their JSON array form.
The checker prints the actual maximum difference, and five new
tests reject altered counts, types, statuses, structure and material values.
This is far below displayed precision; it is not a statistical tolerance or
permission to change outcomes. The original result bytes, inputs, displayed
values, methods and conclusions are preserved. Only the verifier policy and
generator hash change in the manifest. The failed CI remains public.
