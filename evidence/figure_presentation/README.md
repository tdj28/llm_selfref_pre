# Historical Figure Presentation

Five caption-free vector exports replace four historical plot PDFs without
changing the released measurements. This is an unfrozen presentation package,
not a replacement evidence release. The original PDFs, helpers and data remain
unchanged. The canonical manuscript uses these exports.

| Export | Plotted values |
|---|---|
| `ensemble_effects.pdf` | Eight released paired estimates and conservative pointwise 95% bounds; +0.30 reference line |
| `ensemble_rates.pdf` | Sixteen observed rates and two untreated rates; no invented intervals |
| `native_reencoding_1.pdf` | Features 30032, 58667, 22004; ten seeds per sign and phase |
| `native_reencoding_2.pdf` | Features 30686, 41533, 23893; ten seeds per sign and phase |
| `fidelity_pressure.pdf` | Six fixed-item accuracy and correct-answer probability means; no intervals |

The native panels retain every before/after reading, including overlapping
zeros, in the original feature and seed order. Their lines are individual
readings, not uncertainty intervals. The pressure labels map `Pressure 0` to
Wording A and `Pressure 1` to Wording B; neutral is unchanged. Correct-answer
probabilities repeat the original renderer's `math.fsum / 25` reduction of the
same 150 released forward records, not a new analysis or model execution.

`plotted_values.json` preserves full numeric precision, source row identifiers
and semantics; `plotted_values.csv` is the flat display inventory. Missing
interval columns are empty, not zero. `manifest.json` records exact hashes for
all inputs, including the four original PDFs and the three original plotting
helpers, plus output hashes and font checks. Source values are checked against
the original release manifests; frozen helpers are read, never executed.

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
