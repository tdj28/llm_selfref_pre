# Historical Figure Presentation

Seven caption-free vector exports replace six historical plots without
changing the released measurements. This is an unfrozen presentation package,
not a replacement evidence release. The original PDFs, PNGs, helpers and data
remain unchanged. All seven exports are integrated in the canonical manuscript.

| Export | Plotted values |
|---|---|
| `ensemble_effects.pdf` | Eight released paired estimates and conservative pointwise 95% bounds; +0.30 reference line |
| `ensemble_rates.pdf` | Sixteen observed rates and two untreated rates; no invented intervals |
| `native_reencoding_1.pdf` | Features 30032, 58667, 22004; ten seeds per sign and phase |
| `native_reencoding_2.pdf` | Features 30686, 41533, 23893; ten seeds per sign and phase |
| `fidelity_pressure.pdf` | Six fixed-item accuracy and correct-answer probability means; no intervals |
| `causal_decomposition.pdf` | All 24 released model/judge estimates and within-model bootstrap intervals, including ten zero-width intervals |
| `causal_factorial_effects.pdf` | All 12 released equal-model estimates and hierarchical bootstrap intervals; main question above open/conscious question |

The native panels retain every before/after reading, including overlapping
zeros, in the original feature and seed order. Their lines are individual
readings, not uncertainty intervals. The pressure labels map `Pressure 0` to
Wording A and `Pressure 1` to Wording B; neutral is unchanged. Correct-answer
probabilities repeat the original renderer's `math.fsum / 25` reduction of the
same 150 released forward records, not a new analysis or model execution.

The two causal exports copy all estimates and interval endpoints from the
reviewed `evidence/figure_values.json` receipt, bound to source commit
`f5e906e1737bc71bf20b642af1d698018eec82fe`, and check them exactly against the
six copied CSV inputs. The receipt, original PNGs, original plotting and
analysis helpers, and both analysis manifests are hash-checked. No bootstrap
or other estimator runs. Calibration intervals resample independent conditions
within model; transplant intervals resample paired source-text blocks within
model. The factorial uses the existing 5,000-draw model/wording/trial
hierarchical intervals, not independent-wording or pooled-response intervals.
Denominators and source paths remain in the value inventory. A collapsed
interval remains a point, not an invented visible whisker. The factorial's
third row remains the direct register-minus-self contrast, not an interaction.

`plotted_values.json` preserves full numeric precision, source row identifiers
and semantics; `plotted_values.csv` is the flat display inventory. Missing
interval columns are empty, not zero. `manifest.json` records exact hashes for
all inputs, including the original figures and helpers, plus output hashes
and font checks. Source values are checked against the original release
manifests or reviewed causal receipt; frozen helpers are read, never executed.

## Verification

Requires Python 3.10+, Matplotlib 3.10.8 for byte-identical rendering, and Poppler
(`pdffonts`, `pdftotext`, `pdftohtml`, `pdfimages`). No network access is used.

```sh
python scripts/verify_figure_presentation.py
python scripts/verify_figure_presentation.py --check-render
python -m pytest tests/test_figure_presentation.py
```

`--write` regenerates only this presentation package. Default verification is
read-only; `--check-render` redraws in temporary storage and compares PDF bytes.
The existing manuscript verifiers continue to check the original evidence.
These presentation checks do not independently validate the underlying labels,
activations, confidence intervals or study conclusions.

## Manuscript Integration

Each PDF is exactly 468 bp wide (6.5 inches), matching the manuscript's text
width. Use `width=\linewidth`, with no trim, clipping, masks or additional
scaling. Text is 9 pt or larger at that size. Do not shrink below 94.5% width
if the minimum must remain at least 8.5 pt. Captions remain in the manuscript.

The exports are included in `paper/ensemble_alignment.tex`,
`paper/source_alignment.tex` and `paper/fidelity_calibration.tex`. Figure order,
captions and labels are retained; the native re-encoding caption now gives
the per-panel seed counts that previously appeared inside the artwork.

In `paper/main.tex`, the causal decomposition keeps the continuation-swap
diagram, external `B. Label contrasts` heading and existing caption. The plot
is included without the former bitmap masks or overlaid labels:

```tex
\includegraphics[width=\linewidth]{../evidence/figure_presentation/causal_decomposition.pdf}
```

The factorial is a single two-panel vector figure with its existing caption:

```tex
\includegraphics[width=\linewidth]{../evidence/figure_presentation/causal_factorial_effects.pdf}
```

Each new export includes only panel/axis/category labels and the judge legend,
not the figure caption or a findings headline. Their dimensions are 6.5 by
2.8 inches and 6.5 by 4.6 inches respectively. Captions and the existing
left/middle/right and top/bottom references need no numerical or wording change.
