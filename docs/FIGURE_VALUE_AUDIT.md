# F01 Figure-Value Audit

Audit date: 2026-09-29. Source archive pinned to
`f5e906e1737bc71bf20b642af1d698018eec82fe`.

**Result: no numerical mismatch found between the five copied figures, the
pinned summary inputs, and the inspected plotting-code selections.** All five
copied files are byte-identical to that pin. Both PNGs were inspected directly;
the three PDFs were rendered with `pdftoppm` and inspected. This is an automated
source-code/summary check with bounded existing-label tallies, **not independent
raw reanalysis, human validation, or a new uncertainty analysis**. Bootstrap
intervals were not recomputed. B02 addresses their statistical adequacy.

**Remaining attribution boundary:** the original-paper diamonds are hard-coded
plotting references, not estimates computed from this release. Their original
denominators, aggregation and endpoint attribution are a separate B01 source
check. This audit verifies where the diamonds are plotted, not their provenance
in Berg et al. No denominator is inferred from a decimal rate.

## Receipt and Verification

[`evidence/figure_values.json`](../evidence/figure_values.json) is a compact,
portable receipt. It records exact floating-point values, denominators, explicit
nulls, all source paths/SHA-256 hashes, figure hashes, function line locators,
and checked plotting literals. `estimate_ci95`, `effect_ci95`, `target_ci95`,
`specificity_ci95`, and `rate_wilson95` are `[estimate, lower, upper]` triples.
Null means unavailable/not plotted as specified, never a zero estimate.

The stdlib verifier has two deliberately different modes:

```bash
python3 scripts/verify_figure_values.py
python3 scripts/verify_figure_values.py --source-repo /Users/d7082791602/PROJECTS/CONSCIOUS
python3 -B -m unittest discover -s tests -p 'test_figure_values.py' -v
```

Portable mode checks the reviewed receipt digest, numerical identities,
coverage/NA rules, and copied summary/figure hashes. It cannot authenticate
uncopied source data without the source archive. Source mode reads `git show
<pin>:<path>`, never the archive's current working files, reconstructs the
receipt, checks plotting-function literals/locations, and compares it exactly.
The digest is a tamper guard, not scientific validation. Source-code inspection
and the mappings below provide the substantive value binding; literal checks
alone are not a general proof of arbitrary plotting-program semantics.

No plots were regenerated or redrawn. No original figures, evidence manifests,
or source-archive files were changed. The verifier's optional maintainer
`--write-receipt` writes only this new JSON; ordinary verification is read-only.

## Plotting Bindings

Pinned code inspected:

- [Causal figure generator](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/scripts/generate_causal_figures.py),
  `load_effects` lines 68-79, `causal_decomposition` lines 82-144, and
  `orthogonal_factorial` lines 147-211. These select particular model/query/effect
  rows and plot `estimate` with `ci_low`/`ci_high`, not pooled substitutes.
- [SAE figure generator](https://github.com/tdj28/llm_selfref_pre/blob/f5e906e1737bc71bf20b642af1d698018eec82fe/experiments/exp2_sae/figure_public_sae_consciousness_gating.py),
  `aggregate_figure`, `judge_figure`, and `technical_figure`; exact function
  locators are in the receipt. The inspected analysis code is also hash-bound
  there to establish interval and denominator semantics.

All paths below are relative to the pinned archive. Causal inputs are under
`data/causal_transplant/confirmatory_v1_20260709/analysis_{openai,anthropic}_paper/`.
SAE inputs are under
`data/public_sae_consciousness_gating/confirmatory_v1_20260710/`.

## 1. Causal Decomposition

`paper/figures/causal_decomposition.png`: 24 estimate/interval markers, three
panels, four response models, two judges. All use `indirect_experience` and
`level=model`. The selected inputs are `paper_calibration_effects.csv`
(`self_ref_minus_history`) and `transplant_effects.csv`
(`instruction_source_main`, `transcript_source_main`). The zero line is at 0.

Values below are estimate [95% interval], rounded for reading; JSON is exact.
O = OpenAI paper-style judge; A = Anthropic paper-style judge.

| Response model | Judge | Exact prompt contrast | Instruction source | Transcript source |
|---|---|---|---|---|
| Claude Haiku 4.5 | O | .350 [.100, .600] | .525 [.350, .700] | -.175 [-.350, .000] |
| Claude Haiku 4.5 | A | .400 [.150, .650] | .550 [.350, .725] | -.150 [-.300, .000] |
| Claude Sonnet 4.5 | O | .200 [.000, .400] | .550 [.425, .675] | -.350 [-.475, -.225] |
| Claude Sonnet 4.5 | A | .200 [-.050, .450] | .575 [.425, .725] | -.375 [-.525, -.225] |
| GPT-4.1 | O | 1 [1, 1] | 1 [1, 1] | 0 [0, 0] |
| GPT-4.1 | A | 1 [1, 1] | 1 [1, 1] | 0 [0, 0] |
| GPT-4o | O | 1 [1, 1] | .875 [.775, .950] | .125 [.049375, .225] |
| GPT-4o | A | 1 [1, 1] | 1 [1, 1] | 0 [0, 0] |

Calibration uses 20 independent draws per condition/model; `n_pairs=20` is a
legacy column name, not pairing evidence, and `n_clusters=40` counts both
conditions. Transplant effects use 20 complete source-text blocks per model
(`n_pairs=n_clusters=20`), with four instruction/transcript cells per block.
Each displayed cell has `n_models=1`. Intervals are released 5,000-draw
percentile bootstrap intervals, not Wilson intervals. Degenerate [1,1] or
[0,0] intervals are retained and do not establish population certainty.
No selected cell is NA. Equal-model text summaries are not the displayed
model-level markers.

## 2. Orthogonal Factorial

`paper/figures/causal_factorial_effects.png`: 12 estimate/interval markers from
`factorial_effects.csv`, `level=model_equal_hierarchical`. Left is
`indirect_experience`; right is `indirect_conscious`. The third effect is
`register_minus_self`, not the interaction. Both judges remain present.

| Query | Judge | Self-reference | Phenomenological register | Register minus self |
|---|---|---|---|---|
| Experience | O | -.01875 [-.23125, .24375] | .26875 [.00000, .55015625] | .28750 [-.11250, .61250] |
| Experience | A | .00000 [-.25000, .26875] | .18750 [-.06250, .47500] | .18750 [-.17500, .50000] |
| Conscious | O | .11250 [-.01875, .30625] | .31250 [.00000, .65625] | .20000 [-.21250, .60000] |
| Conscious | A | .15000 [-.01875, .33750] | .28750 [.02500, .58750] | .13750 [-.18750, .43750] |

Each selected row records four models, 80 complete factorial trial units, and
16 model-by-lexical-variant clusters (four variants per model). Four condition
cells contribute to each factorial unit. Intervals use the released 5,000-draw
model/lexical-variant/trial hierarchical percentile bootstrap. These are not
80 independently sampled lexical variants. No NA cells or omitted query/judge
combinations were found.

## 3. Aggregate Target and Controls

`paper/figures/aggregate_target_and_controls.pdf` uses **literal scale only**.
Left: `aggregate_effects.csv` sign-specific rate and Wilson fields. Right:
the same file's suppression-minus-amplification and bootstrap bounds, plus
`primary_verdict.json:primary_specificity_effect` for target minus the mean of
all three controls. Each role has 50 planned and complete paired blocks;
each sign-specific denominator is 50. Specificity has 50 common blocks.

| Role | Suppression count; rate [Wilson 95%] | Amplification count; rate [Wilson 95%] | Effect [bootstrap 95%] |
|---|---|---|---|
| Target | 48/50; .96 [.865399, .988961] | 48/50; .96 [.865399, .988961] | .00 [-.06, .06] |
| Matched 1 | 48/50; .96 [.865399, .988961] | 45/50; .90 [.786398, .956524] | .06 [-.04, .16] |
| Matched 2 | 50/50; 1.00 [.928652, 1.000000] | 49/50; .98 [.895046, .996461] | .02 [.00, .06] |
| Matched 3 | 49/50; .98 [.895046, .996461] | 49/50; .98 [.895046, .996461] | .00 [-.06, .06] |
| Target minus mean controls | Not a rate | Not a rate | -.026667 [-.100000, .046667] |

Wilson uses `z=1.959963984540054`; effect intervals are the released
100,000-draw percentile paired-block bootstrap, seed 20260710. The right-panel
reference lines are 0 and the frozen minimum relevant effect .30.

Original-paper references are open diamonds: suppression .96 and amplification
.16 in the left target column (x offsets -.11 and +.11), and their .80
difference in the right target row. There are **no reference error bars**.
The plot code supplies no original-paper denominator; the receipt records null.
These diamonds are not extra observations or estimates from the local judge.

## 4. Judge Sensitivity

`paper/figures/judge_sensitivity.pdf` plots literal-scale `judge_sensitivity.csv`
target effects (circles) and target-minus-mean-controls effects (squares).
Every interval below is actually plotted, except the explicitly NA parser.
Reference lines are 0 and .30. The parser has two visible `NA` strings at
x=-.98, not two negative estimates.

| Judge | Target [95%] | Matched 1 effect | Matched 2 effect | Matched 3 effect | Mean control effect | Specificity [95%] | Complete/common blocks |
|---|---|---|---|---|---|---|---|
| Local Llama | .00 [-.06, .06] | .06 | .02 | .00 | .026667 | -.026667 [-.100000, .046667] | 50 / 50 |
| GPT-4o mini | -.04 [-.16, .08] | .10 | .04 | -.06 | .026667 | -.066667 [-.206667, .066667] | 50 / 50 |
| Claude Haiku | -.06 [-.18, .06] | .10 | -.02 | .06 | .046667 | -.106667 [-.226667, .006667] | 50 / 50 |
| Three-judge majority | -.06 [-.18, .06] | .10 | -.02 | .06 | .046667 | -.106667 [-.226667, .006667] | 50 / 50 |
| Direct parser | NA | NA | NA | NA | NA | NA | 0 / 0 |

The individual external-control effects are explanatory support cells, **not
separate markers in this figure**. Their CIs are not supplied in the released
judge-sensitivity summary and are not invented here. The plotted target and
specificity CIs are retained exactly. All three controls are tallied separately
for each evaluator; none is borrowed from the primary judge.

For a compact denominator cross-check, entries below are suppression-positive /
amplification-positive counts, each over 50 complete pairs:

| Judge | Target | Matched 1 | Matched 2 | Matched 3 |
|---|---|---|---|---|
| Local Llama | 48 / 48 | 48 / 45 | 50 / 49 | 49 / 49 |
| GPT-4o mini | 41 / 43 | 45 / 40 | 44 / 42 | 41 / 44 |
| Claude Haiku | 43 / 46 | 47 / 42 | 45 / 46 | 48 / 45 |
| Three-judge majority | 43 / 46 | 47 / 42 | 45 / 46 | 48 / 45 |

The receipt includes all four paired outcome counts (`00`, `01`, `10`, `11`,
ordered suppression/amplification) for every judge/role, not just marginal
rates. Tallies join released labels to the frozen plan and verify that runtime
phase/scale/role/sign/block/seed metadata agrees with the plan. Generation and
label-file hashes also match the pinned analysis manifest. Majority requires
three valid labels. All 400 literal aggregate parser labels are missing,
with 50 planned but zero complete pairs in every role; they are not denials.
This bounded tally does not reassess response text, judge correctness, or
bootstrap coverage.

## 5. Dose and Matching

`paper/figures/technical_dose_and_matching.pdf`, left: only final-turn rows
from `analysis/realized_dose_telemetry.csv`, phases `aggregate_literal` and
`aggregate_calibrated`, roles target and matched 1-3. The y value is
`mean_relative_hidden_delta_rms`, not absolute RMS, a requested coefficient,
or a behavioral effect. Each present point summarizes 50 trials with 50
nonmissing dose measurements. No error bars are plotted.

| Scale | Role | Suppression mean | Amplification mean |
|---|---|---|---|
| Literal | Target | .0218309084 | .0219951906 |
| Literal | Matched 1 | .0210456828 | .0207898463 |
| Literal | Matched 2 | .0209509469 | .0204614173 |
| Literal | Matched 3 | .0204960125 | .0203309655 |
| Calibrated | Target | .0823730441 | .0803899999 |
| Calibrated | Matched 1 | .0744867011 | .0764165232 |
| Calibrated | Matched 2 | Not in design | Not in design |
| Calibrated | Matched 3 | Not in design | Not in design |

Literal circles and calibrated squares are separate series; suppression is
orange and amplification blue. There are 12 present points and four absent
calibrated cells, not four zeros or parser NAs. The horizontal .20 line is a
technical stop boundary, not a confidence bound. The receipt additionally
retains each selected row's absolute RMS, maximum relative RMS, coefficient,
feature-count and token summaries to disambiguate the plotted field. Means
below .20 alone would not verify every trial's stopping rule.

Right: all 18 target/control pairs in `plan/calibration.json:control_matching`
are plotted, six per panel, with decoder-norm ratio on x and maximum absolute
cosine to any target on y. These are feature-pair diagnostics, not 18 trials
or intervals. The vertical reference is x=1. The ratio arithmetic is also
checked against `feature_metrics`; the cosine matches the control metric.

| Panel | Target -> control | Norm ratio | Max abs target cosine |
|---|---|---|---|
| 1 | 30032 -> 26041 | 1.00019975 | .02227939 |
| 1 | 58667 -> 11872 | 1.00002711 | .01301106 |
| 1 | 22004 -> 55963 | 1.00013600 | .03505123 |
| 1 | 30686 -> 21779 | .99819416 | .01578118 |
| 1 | 41533 -> 29649 | 1.00003418 | .03086739 |
| 1 | 23893 -> 15424 | .97005514 | .02674018 |
| 2 | 30032 -> 16004 | 1.00038271 | .01655294 |
| 2 | 58667 -> 7182 | 1.00044293 | .02968727 |
| 2 | 22004 -> 47797 | 1.00166768 | .01275562 |
| 2 | 30686 -> 21403 | .99766545 | .04804569 |
| 2 | 41533 -> 1059 | 1.00029885 | .03126350 |
| 2 | 23893 -> 51407 | .95189637 | .02438506 |
| 3 | 30032 -> 64365 | 1.00041042 | .00843750 |
| 3 | 58667 -> 1364 | .99914020 | .05850180 |
| 3 | 22004 -> 58741 | 1.00167274 | .01262445 |
| 3 | 30686 -> 19827 | .99511217 | .02414930 |
| 3 | 41533 -> 62289 | 1.00034855 | .02319174 |
| 3 | 23893 -> 26362 | .83162785 | .02370915 |

### Scale Separation

The behavioral aggregate and judge figures do not contain calibrated effects.
For completeness, the separate `calibrated_aggregate_effects.csv` records target
-.10 [-.22, .02] and matched 1 +.12 [.04, .22], each on 50 complete blocks.
Matched 2 and 3 were not in that design. Their absence cannot establish a
three-panel calibrated specificity result, and the scales are not pooled.

## Validation Scope

The new receipt and verifier preserve the figures' original uncertainty;
neither changes a scientific endpoint nor upgrades inference. Focused tests
cover altered estimates/intervals, figure bytes, source-summary bytes, wrong
pins, removed controls, wrong evaluator controls, NA-to-zero conversion,
denominator drift, fabricated calibrated panels, and diagnostic/reference
coordinates. Tests establish resistance to these edits, not empirical truth.
The only files added for F01 are this document, the JSON receipt, the verifier,
and its test module. No commits, API calls, GPU work, or source-archive writes
were performed.
