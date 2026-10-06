# Cross-Model Swap Overview

The figure shows how the instruction advantage changes across response models
and scoring rules. It uses one contrast throughout: the positive-label rate
for a self-reference instruction with a history continuation (SH), minus the
rate for the reverse pairing (HS). Values are percentage points.

The 13 rows cover 11 models in the completed English, single-answer swap
panels. GPT-4.1 and Opus appear in two separate studies; no rows are pooled or
selected by effect size. Llama uses the bilingual study's history anchor,
not its self-reference/recursive-feedback language contrast. The earlier
qualification repeats and screen-only models are excluded; the separate
repeated-answer experiment keeps its own figure. Chinese comparisons also
keep their dedicated figure.

Gray cells mean that the whole panel was not scored under that rubric. They
are not zero outcomes. A zero contrast can reflect two floor or ceiling
conditions, not evidence that neither input matters. The matrix shows point
estimates only; it does not encode significance. The paper retains the larger
panels' primary simultaneous bounds in its adjacent table. The original
panel's readers were GPT-4o mini and Haiku 4.5; later readers were GPT-6 Astra
and Opus 5.5. Different study settings preclude a capability ranking.

`figure_data.json` records each exact selector and source; `plotted_values.csv`
provides the same measurements for reuse. Every source is hash-checked before
the figure is generated. The frozen study data and existing figures are not
modified. The Qwen3.5 row uses an unchanged copy of `analysis/q1.csv` from
the [companion release](https://github.com/tdj28/selfref_scaling/blob/7cb5c984eb41968b6f3d2f9b322f4de125a1d1ca/data/release_20261003/analysis/q1.csv);
its Apache 2.0 license accompanies that copy. No external checkout is needed
to verify this figure.

```sh
python scripts/verify_model_overview.py
python scripts/verify_model_overview.py --rerender
```

`--write` rebuilds only this editorial package. No new model calls, labels,
confidence intervals or cross-study hypothesis tests are produced.
