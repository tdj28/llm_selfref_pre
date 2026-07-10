#!/usr/bin/env python3
"""Reanalyze saved outputs from AE Studio's public steering notebook.

This is clean-room analysis code for an external public notebook whose
repository had no explicit license when accessed.
It does not copy or execute AE's notebook code. It parses saved output text from
the notebook JSON and writes derived summary tables/figures for reproducibility.

Input may be a local `.ipynb` path or an HTTP(S) URL. Do not commit the upstream
notebook unless a suitable license is provided; commit only derived facts and
our own analysis outputs.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_NOTEBOOK_URL = (
    "https://raw.githubusercontent.com/agencyenterprise/"
    "steering-api-examples/main/deception-features/deception_features.ipynb"
)


@dataclass
class FeatureRun:
    search_string: str
    label: str | None = None
    feature_id: int | None = None
    layer: int | None = None
    similarity: str | None = None
    pearson_r: float | None = None
    p_value: float | None = None
    rates: list[dict[str, float | int]] = field(default_factory=list)


def load_notebook(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    with Path(source).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_output_text(notebook: dict) -> Iterable[str]:
    for cell in notebook.get("cells", []):
        for output in cell.get("outputs", []) or []:
            if "text" in output:
                text = output["text"]
                yield "".join(text) if isinstance(text, list) else str(text)
            data = output.get("data") or {}
            plain = data.get("text/plain")
            if plain:
                yield "".join(plain) if isinstance(plain, list) else str(plain)


def parse_runs(output_chunks: Iterable[str]) -> list[FeatureRun]:
    experiment_re = re.compile(r"^EXPERIMENT:\s*(.+?)\s*$")
    label_re = re.compile(r"^\s*Label:\s*(.+?)\s*$")
    index_re = re.compile(
        r"^\s*Index:\s*(\d+)\s*\|\s*Layer:\s*(\d+)\s*\|\s*Similarity:\s*(.+?)\s*$"
    )
    corr_re = re.compile(r"^Correlation:\s*r=([+-]?(?:\d+(?:\.\d+)?|nan)),\s*p=([0-9.]+)")
    row_re = re.compile(
        r"^\s*([+-]?\d+\.\d+)\s*\|\s*([0-9.]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*$"
    )

    runs: list[FeatureRun] = []
    current: FeatureRun | None = None

    for chunk in output_chunks:
        for line in chunk.splitlines():
            experiment_match = experiment_re.match(line)
            if experiment_match:
                current = FeatureRun(search_string=experiment_match.group(1).strip())
                runs.append(current)
                continue

            if current is None:
                continue

            if (label_match := label_re.match(line)):
                current.label = label_match.group(1).strip()
                continue

            if (index_match := index_re.match(line)):
                current.feature_id = int(index_match.group(1))
                current.layer = int(index_match.group(2))
                current.similarity = index_match.group(3).strip()
                continue

            if (corr_match := corr_re.match(line)):
                current.pearson_r = float(corr_match.group(1))
                current.p_value = float(corr_match.group(2))
                continue

            if (row_match := row_re.match(line)):
                current.rates.append(
                    {
                        "steering_value": float(row_match.group(1)),
                        "fraction": float(row_match.group(2)),
                        "trials": int(row_match.group(3)),
                        "yes": int(row_match.group(4)),
                        "no": int(row_match.group(5)),
                    }
                )

    return [run for run in runs if run.feature_id is not None and run.rates]


def mean_for_values(run: FeatureRun, values: set[float]) -> float | None:
    matches = [
        float(row["fraction"])
        for row in run.rates
        if round(float(row["steering_value"]), 1) in values
    ]
    if not matches:
        return None
    return sum(matches) / len(matches)


def value_at(run: FeatureRun, value: float) -> float | None:
    rounded = round(value, 1)
    for row in run.rates:
        if round(float(row["steering_value"]), 1) == rounded:
            return float(row["fraction"])
    return None


def upward_steps(run: FeatureRun) -> int:
    rows = sorted(run.rates, key=lambda row: float(row["steering_value"]))
    count = 0
    for prev, cur in zip(rows, rows[1:]):
        if float(cur["fraction"]) > float(prev["fraction"]):
            count += 1
    return count


def fmt_float(value: float | None, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return f"{value:.{digits}f}"


def write_value_rates(path: Path, runs: list[FeatureRun], source: str) -> None:
    fieldnames = [
        "source_artifact",
        "source_note",
        "search_string",
        "feature_label",
        "feature_id",
        "layer",
        "similarity",
        "steering_value",
        "fraction",
        "trials",
        "yes",
        "no",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            for row in sorted(run.rates, key=lambda item: float(item["steering_value"])):
                writer.writerow(
                    {
                        "source_artifact": source,
                        "source_note": "Derived from saved notebook outputs; upstream notebook not vendored.",
                        "search_string": run.search_string,
                        "feature_label": run.label or "",
                        "feature_id": run.feature_id,
                        "layer": run.layer,
                        "similarity": run.similarity or "",
                        **row,
                    }
                )


def write_summary(path: Path, runs: list[FeatureRun], source: str) -> None:
    fieldnames = [
        "source_artifact",
        "source_note",
        "search_string",
        "feature_label",
        "feature_id",
        "layer",
        "similarity",
        "pearson_r",
        "p_value",
        "significant_p_lt_0_05",
        "rate_at_minus_0_6",
        "rate_at_0_0",
        "rate_at_plus_0_6",
        "paper_suppression_mean_minus_0_6_to_minus_0_4",
        "paper_amplification_mean_plus_0_4_to_plus_0_6",
        "paper_range_difference_suppression_minus_amplification",
        "upward_steps_against_expected_negative_trend",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            suppression = mean_for_values(run, {-0.6, -0.5, -0.4})
            amplification = mean_for_values(run, {0.4, 0.5, 0.6})
            writer.writerow(
                {
                    "source_artifact": source,
                    "source_note": "Derived from saved notebook outputs; upstream notebook not vendored.",
                    "search_string": run.search_string,
                    "feature_label": run.label or "",
                    "feature_id": run.feature_id,
                    "layer": run.layer,
                    "similarity": run.similarity or "",
                    "pearson_r": fmt_float(run.pearson_r),
                    "p_value": fmt_float(run.p_value),
                    "significant_p_lt_0_05": (
                        "" if run.p_value is None else str(run.p_value < 0.05).lower()
                    ),
                    "rate_at_minus_0_6": fmt_float(value_at(run, -0.6), 2),
                    "rate_at_0_0": fmt_float(value_at(run, 0.0), 2),
                    "rate_at_plus_0_6": fmt_float(value_at(run, 0.6), 2),
                    "paper_suppression_mean_minus_0_6_to_minus_0_4": fmt_float(suppression, 4),
                    "paper_amplification_mean_plus_0_4_to_plus_0_6": fmt_float(amplification, 4),
                    "paper_range_difference_suppression_minus_amplification": fmt_float(
                        None if suppression is None or amplification is None else suppression - amplification,
                        4,
                    ),
                    "upward_steps_against_expected_negative_trend": upward_steps(run),
                }
            )


def write_manifest(
    path: Path,
    source: str,
    input_location: str,
    runs: list[FeatureRun],
    outputs: list[Path],
) -> None:
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_artifact": source,
        "input_location_used_for_this_run": input_location,
        "source_license_status": "No license observed in upstream repo at time of review.",
        "copyright_handling": (
            "This repo does not vendor the upstream notebook or copy its code. "
            "Outputs are derived from saved notebook output text and include factual "
            "measurements, labels, and source attribution."
        ),
        "analysis_code": "experiments/exp2_sae/reanalyze_ae_notebook_outputs.py",
        "num_feature_runs": len(runs),
        "feature_ids": [run.feature_id for run in runs],
        "outputs": [str(path) for path in outputs],
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def write_plot(path: Path, runs: list[FeatureRun]) -> None:
    """Write a dependency-free SVG line plot for the six feature curves."""

    width = 1200
    height = 760
    margin_x = 70
    margin_y = 85
    gap_x = 55
    gap_y = 80
    panel_w = (width - 2 * margin_x - 2 * gap_x) / 3
    panel_h = (height - 2 * margin_y - gap_y) / 2

    def sx(panel_left: float, value: float) -> float:
        return panel_left + ((value + 0.7) / 1.4) * panel_w

    def sy(panel_top: float, frac: float) -> float:
        return panel_top + (1.0 - frac) * panel_h

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#222}.title{font-size:20px;font-weight:700}.panel-title{font-size:14px;font-weight:700}.small{font-size:11px}.axis{stroke:#333;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}.zero{stroke:#999;stroke-width:1;stroke-dasharray:4 3}.line{fill:none;stroke:#1f77b4;stroke-width:2}.point{fill:#1f77b4;stroke:white;stroke-width:1}</style>',
        '<text class="title" x="600" y="34" text-anchor="middle">AE public notebook saved outputs: candidate feature steering curves</text>',
        '<text class="small" x="600" y="58" text-anchor="middle">Derived from saved output text; upstream notebook not vendored.</text>',
    ]

    for idx, run in enumerate(runs):
        col = idx % 3
        row = idx // 3
        left = margin_x + col * (panel_w + gap_x)
        top = margin_y + row * (panel_h + gap_y)
        bottom = top + panel_h
        right = left + panel_w

        parts.extend(
            [
                f'<rect x="{left:.1f}" y="{top:.1f}" width="{panel_w:.1f}" height="{panel_h:.1f}" fill="#fafafa" stroke="#ccc"/>',
                f'<text class="panel-title" x="{left:.1f}" y="{top - 18:.1f}">ID {run.feature_id}</text>',
                f'<text class="small" x="{right:.1f}" y="{top - 18:.1f}" text-anchor="end">r={fmt_float(run.pearson_r, 2)} p={fmt_float(run.p_value, 3)}</text>',
            ]
        )

        for frac in (0.0, 0.5, 1.0):
            y = sy(top, frac)
            parts.append(f'<line class="grid" x1="{left:.1f}" y1="{y:.1f}" x2="{right:.1f}" y2="{y:.1f}"/>')
            parts.append(f'<text class="small" x="{left - 8:.1f}" y="{y + 4:.1f}" text-anchor="end">{frac:.1f}</text>')

        for value in (-0.6, 0.0, 0.6):
            x = sx(left, value)
            klass = "zero" if value == 0.0 else "grid"
            parts.append(f'<line class="{klass}" x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{bottom:.1f}"/>')
            parts.append(f'<text class="small" x="{x:.1f}" y="{bottom + 18:.1f}" text-anchor="middle">{value:+.1f}</text>')

        parts.append(f'<line class="axis" x1="{left:.1f}" y1="{bottom:.1f}" x2="{right:.1f}" y2="{bottom:.1f}"/>')
        parts.append(f'<line class="axis" x1="{left:.1f}" y1="{top:.1f}" x2="{left:.1f}" y2="{bottom:.1f}"/>')

        rows = sorted(run.rates, key=lambda item: float(item["steering_value"]))
        points = [
            (sx(left, float(item["steering_value"])), sy(top, float(item["fraction"])))
            for item in rows
        ]
        point_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline class="line" points="{point_attr}"/>')
        for x, y in points:
            parts.append(f'<circle class="point" cx="{x:.1f}" cy="{y:.1f}" r="3.5"/>')

        label = html.escape(run.label or run.search_string)
        parts.append(f'<text class="small" x="{left:.1f}" y="{bottom + 38:.1f}">{label[:58]}</text>')

    parts.extend(
        [
            '<text class="small" x="600" y="742" text-anchor="middle">Steering value</text>',
            '<text class="small" transform="translate(18 390) rotate(-90)" text-anchor="middle">Affirmation fraction</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=DEFAULT_NOTEBOOK_URL,
        help="Local .ipynb path or raw notebook URL.",
    )
    parser.add_argument(
        "--outdir",
        default="paper/results",
        help="Directory for derived tables, figure, and manifest.",
    )
    parser.add_argument(
        "--source-artifact",
        default=None,
        help="Canonical source URL/path to record in derived outputs. Defaults to --input.",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    source_artifact = args.source_artifact or args.input

    notebook = load_notebook(args.input)
    runs = parse_runs(iter_output_text(notebook))
    if not runs:
        print("No feature runs found in saved notebook outputs.", file=sys.stderr)
        return 1

    summary_path = outdir / "ae_notebook_feature_summary.csv"
    rates_path = outdir / "ae_notebook_value_rates.csv"
    plot_path = outdir / "ae_notebook_feature_curves.svg"
    manifest_path = outdir / "ae_notebook_reanalysis_manifest.json"

    write_summary(summary_path, runs, source_artifact)
    write_value_rates(rates_path, runs, source_artifact)
    write_plot(plot_path, runs)
    write_manifest(
        manifest_path,
        source_artifact,
        args.input,
        runs,
        [summary_path, rates_path, plot_path],
    )

    print(f"Parsed {len(runs)} feature runs")
    for path in (summary_path, rates_path, plot_path, manifest_path):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
