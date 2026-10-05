#!/usr/bin/env python3
"""Render/check unfrozen presentation copies of four released historical figures.

No study helper is executed. Existing estimates, bounds and per-seed readings
are copied. Pressure means repeat the released renderer's fixed-item arithmetic;
no interval, bootstrap, model call or scientific verdict is calculated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evidence/figure_presentation"
ENSEMBLE = "evidence/ensemble_alignment"
SOURCE = "evidence/source_alignment"
SOURCE_RUN = "data/berg_source_replication/source_aligned_v1_20261001"
FIDELITY = "data/steering_fidelity/calibration_v1_20261002"
REPORT = "data/steering_fidelity/calibration_report_20261002"
PLAN = "data/steering_fidelity/calibration_plan_20261002/PLAN.json"
PINS = {
    f"{ENSEMBLE}/manifest.json": "3dcba03a1e68f117aa94254f9c0e398d8f995d8d28775ba06cbae85d5285c199",
    f"{SOURCE}/manifest.json": "e7d1f0565e44d655bc5c6986fff3a3f44c0b63ac4f8d115d572fc5ab666a3a0e",
    f"{FIDELITY}/RELEASE_MANIFEST.json": "815cd2e76adff2e9a1d7c182d6651a77af52c88d885dbb00e0d7ef6ef2aa8bc0",
    f"{REPORT}/RELEASE_MANIFEST.json": "b4aa283e2541cc29d22319411c689593874b3db50b21cc960c1c7bebbb0c8404",
    PLAN: "6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0",
    "experiments/berg_ensemble_diagnostics.py": "36779358a204f585ce4c30ad0cb362e18edc9af0f59d6373772e5604b6559ca2",
    "experiments/berg_source_figures.py": "7f9e7c762f5b4cd14b3d421bae094dffd334f2d760176e0ad30b30226b0ec250",
    "scripts/report_steering_fidelity_calibration.py": "1dec0a11bd2fa189a5e14a55dd7f16ae0214e09d1f150802992280ba3838668e",
}
FEATURES = (30032, 58667, 22004, 30686, 41533, 23893)
SEEDS = (101, 202, 303, 404, 505, 606, 707, 808, 909, 1001)
FAMILIES = ("target", "control-1", "control-2", "control-3")
PDFS = ("ensemble_effects.pdf", "ensemble_rates.pdf", "native_reencoding_1.pdf",
        "native_reencoding_2.pdf", "fidelity_pressure.pdf")
BLUE, RED, GREEN = "#236d91", "#ae4b48", "#397454"
SCOPE = {
    "presentation_only": True, "new_inference": False, "human_validation": False,
    "ensemble_intervals": "Copied conservative marginal 95% bounds; pointwise, not bootstrap",
    "rates_and_pressure_intervals": None,
    "native_lines": "Individual released before/after readings, not confidence intervals",
    "pressure_means": "Original fixed-item math.fsum / 25; no new statistical estimator",
    "inclusion_width_bp": 468, "minimum_font_pt": 9,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


class Inputs:
    def __init__(self, root):
        self.root, self.records = Path(root), {}

    def read(self, name, digest, size=None):
        path = self.root / name
        require(not path.is_symlink(), "Symlink input: " + name)
        raw = path.read_bytes()
        require(sha(raw) == digest and (size is None or len(raw) == size), "Input changed: " + name)
        self.records[name] = {"sha256": sha(raw), "bytes": len(raw)}
        return raw

    def artifact(self, prefix, name, entries):
        entry = entries[name]
        return self.read(f"{prefix}/{name}", entry["sha256"], entry["bytes"])


def release_entries(raw):
    return {row["path"]: row for row in json.loads(raw)["files"]}


def collect(root=ROOT):
    inputs = Inputs(root)
    pinned = {name: inputs.read(name, digest) for name, digest in PINS.items()}
    em = json.loads(pinned[f"{ENSEMBLE}/manifest.json"])["artifacts"]
    sm = json.loads(pinned[f"{SOURCE}/manifest.json"])["artifacts"]
    summary = json.loads(inputs.artifact(ENSEMBLE, "analysis/summary.json", em))["results"]
    for name in ("aggregate_effects", "aggregate_rates"):
        inputs.artifact(ENSEMBLE, f"secondary/{name}.pdf", em)
    inputs.artifact(SOURCE, "extra_figures/native_reencoding.pdf", sm)
    source_release = release_entries(inputs.artifact(SOURCE, "RELEASE_MANIFEST.json", sm))
    activation_raw = inputs.artifact(SOURCE_RUN, "secondary/activation_changes.csv", source_release)
    effects, rates, native, pressure = [], [], [], []
    for judge in ("paper", "notebook"):
        for family in FAMILIES:
            cell = summary[judge][family]
            require(cell["complete_pairs"] == 50, "Ensemble pair coverage changed")
            low, high = cell["exact_marginal95"]
            effects.append(dict(judge=judge, family=family, estimate=cell["estimate_complete_pairs"],
                                low=low, high=high, n=50))
            for sign in ("suppression", "amplification"):
                c = cell[sign]
                require(c["missing"] == 0 and c["n_planned"] == 50, "Rate missingness changed")
                rates.append(dict(judge=judge, family=family, sign=sign,
                                  value=c["rate"], positive=c["positive"], n=50))
        c = summary[judge]["zero"]
        require(c["missing"] == 0 and c["n_planned"] == 50, "Untreated coverage changed")
        rates.append(dict(judge=judge, family="zero", sign="untreated",
                          value=c["rate"], positive=c["positive"], n=50))
    rows = list(csv.DictReader(io.StringIO(activation_raw.decode())))
    for feature in FEATURES:
        for phase in ("prompt", "generated"):
            for sign in (-.7, .7):
                selected = [r for r in rows if r["family"] == f"feature-{feature}"
                            and float(r["coefficient"]) == sign and r["turn"] == "2" and r["phase"] == phase]
                require(len(selected) == 10 and {int(r["seed"]) for r in selected} == set(SEEDS),
                        "Native seed coverage changed")
                for r in sorted(selected, key=lambda row: int(row["seed"])):
                    require(int(r["feature_id"]) == feature and int(r["positions"]) > 0,
                            "Native feature/position mismatch")
                    native.append(dict(id=r["id"], feature=feature, phase=phase, sign=sign,
                                       seed=int(r["seed"]), positions=int(r["positions"]),
                                       before=float(r["before_mean"]), after=float(r["after_mean"])))
    fm = release_entries(pinned[f"{FIDELITY}/RELEASE_MANIFEST.json"])
    report = release_entries(pinned[f"{REPORT}/RELEASE_MANIFEST.json"])
    inputs.artifact(REPORT, "pressure.pdf", report)
    saved = json.loads(inputs.artifact(FIDELITY, "pressure-analysis.json", fm))
    require(saved["selected_level"] is None and not saved["pass"], "Pressure verdict changed")
    plan = json.loads(pinned[PLAN])["rows"]
    for truth in (False, True):
        for level, label in ((None, "Neutral"), (0, "Wording A"), (1, "Wording B")):
            specs = [r for r in plan if r["family"] == "fact" and r["truth"] == truth and r["arm"] == "zero"
                     and (r["frame"] == "neutral" if level is None else
                          r["frame"] == ("doubt" if truth else "assert") and r.get("pressure_level") == level)]
            require(len(specs) == 25, "Pressure item coverage changed")
            values = []
            for spec in sorted(specs, key=lambda r: r["id"]):
                r = json.loads(inputs.artifact(FIDELITY, f"forwards/{spec['id']}.json", fm))
                require(all(r.get(k) == spec.get(k) for k in
                            ("id", "item_id", "family", "truth", "frame", "arm", "rung", "pressure_level")),
                        "Pressure row specification mismatch")
                require(r["missing"] is False and type(r["correct"]) is bool
                        and math.isfinite(r["p_correct"]) and 0 <= r["p_correct"] <= 1,
                        "Pressure missing or invalid value")
                values.append(r)
            accuracy = math.fsum(r["correct"] for r in values) / 25
            expected = (saved["neutral_truth_cells"][str(truth)] if level is None else
                        saved["levels"][level]["truth_cells"][str(truth)]["accuracy"])
            require(accuracy == expected, "Pressure accuracy disagrees with release")
            pressure.append(dict(truth=truth, level=level, label=label, n=25, accuracy=accuracy,
                                 probability=math.fsum(r["p_correct"] for r in values) / 25,
                                 source_ids=[r["id"] for r in values]))
    return dict(schema="historical_figure_presentation_v1", scope=SCOPE, ensemble_effects=effects,
                ensemble_rates=rates, native_reencoding=native, fidelity_pressure=pressure), inputs.records


def csv_bytes(values):
    fields = ("figure", "judge", "family", "sign", "feature", "phase", "seed", "id", "positions",
              "truth", "level", "label", "n", "positive", "estimate", "low", "high", "value", "before",
              "after", "accuracy", "probability")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name in ("ensemble_effects", "ensemble_rates", "native_reencoding", "fidelity_pressure"):
        for row in values[name]:
            writer.writerow({"figure": name, **{k: v for k, v in row.items() if k in fields}})
    return stream.getvalue().encode()


def render(values, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.text import Text
    from matplotlib.ticker import MaxNLocator, ScalarFormatter

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
                         "axes.titlesize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
                         "legend.fontsize": 9, "pdf.fonttype": 42, "ps.fonttype": 42,
                         "axes.unicode_minus": False, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.transparent": False})
    out = Path(out)
    audits = {}

    def finish(fig, name):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
        require(all(t.get_fontsize() >= 8.5 for t in texts), "Small plot text")
        for t in texts:
            box = t.get_window_extent(renderer)
            require(box.x0 >= -1 and box.y0 >= -1 and box.x1 <= fig.bbox.width + 1
                    and box.y1 <= fig.bbox.height + 1, "Text outside figure: " + t.get_text())
        audits[name] = {"width_bp": fig.get_figwidth() * 72, "height_bp": fig.get_figheight() * 72,
                        "minimum_font_pt": min(t.get_fontsize() for t in texts),
                        "text": [t.get_text() for t in texts]}
        fig.savefig(out / name, metadata={"CreationDate": None, "ModDate": None,
                                         "Creator": "verify_figure_presentation.py"})
        plt.close(fig)

    labels = ["Target", "Control 1", "Control 2", "Control 3"]
    for kind, height in (("effects", 6.2), ("rates", 5.8)):
        fig, axes = plt.subplots(2, 1, figsize=(6.5, height))
        fig.subplots_adjust(left=.15, right=.98, top=.94, bottom=.13, hspace=.44)
        for ax, judge in zip(axes, ("paper", "notebook")):
            ax.set_title("Paper rubric" if judge == "paper" else "Second rubric", loc="left", pad=9)
            if kind == "effects":
                for i, r in enumerate(r for r in values["ensemble_effects"] if r["judge"] == judge):
                    color = BLUE if judge == "paper" else RED
                    ax.vlines(i, r["low"], r["high"], color=color, lw=1.2)
                    ax.hlines((r["low"], r["high"]), i-.055, i+.055, color=color, lw=1.2)
                    ax.plot(i, r["estimate"], "o", color=color, ms=4)
                ax.axhline(0, color=".5", lw=.7)
                ax.axhline(.30, color=".45", lw=1, ls=":")
                ax.set(ylim=(-1.05, 1.05), ylabel="Suppression minus amplification")
                ax.set_yticks([-1, -.5, 0, .5, 1])
            else:
                rows = [r for r in values["ensemble_rates"] if r["judge"] == judge]
                for offset, sign, color in ((-.18, "suppression", BLUE), (.18, "amplification", RED)):
                    rates = [next(r["value"] for r in rows if r["family"] == f and r["sign"] == sign)
                             for f in FAMILIES]
                    ax.bar([i+offset for i in range(4)], rates, width=.34, color=color, label=sign.title())
                ax.axhline(next(r["value"] for r in rows if r["family"] == "zero"),
                           color=GREEN, ls="--", lw=1.2, label="Untreated")
                ax.set(ylim=(0, 1.05), ylabel="Positive-label fraction")
            ax.set_xticks(range(4), labels)
            ax.set_xlim(-.55, 3.55)
        if kind == "rates":
            fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=3,
                       frameon=False, bbox_to_anchor=(.55, .015))
        finish(fig, "ensemble_" + kind + ".pdf")

    for group in range(2):
        fig, axes = plt.subplots(2, 3, figsize=(6.5, 4.9))
        fig.subplots_adjust(left=.115, right=.98, top=.89, bottom=.15, hspace=.43, wspace=.44)
        for col, feature in enumerate(FEATURES[group*3:group*3+3]):
            for row, phase in enumerate(("prompt", "generated")):
                ax = axes[row, col]
                for sign, color, offset in ((-.7, BLUE, -.16), (.7, RED, .16)):
                    selected = [r for r in values["native_reencoding"] if r["feature"] == feature
                                and r["phase"] == phase and r["sign"] == sign]
                    for index, r in enumerate(selected):
                        x = offset + (index - (len(selected)-1)/2)*.015
                        ax.plot([x, x+.8], [r["before"], r["after"]], color=color, alpha=.45, lw=.7)
                        ax.scatter([x, x+.8], [r["before"], r["after"]], color=color, s=9)
                ax.set_ylim(bottom=0)
                ax.set_xticks((0, .8), ("Before", "After"))
                ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
                formatter = ScalarFormatter(useOffset=False)
                formatter.set_scientific(False)
                ax.yaxis.set_major_formatter(formatter)
                if row == 0:
                    ax.set_title(f"Feature {feature}", pad=8)
                if col == 0:
                    ax.set_ylabel("Last prompt" if row == 0 else "Answer-token mean")
        fig.legend([Line2D([], [], color=BLUE, marker="o", ms=3), Line2D([], [], color=RED, marker="o", ms=3)],
                   ["-0.7", "+0.7"], loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(.5, .01))
        finish(fig, f"native_reencoding_{group+1}.pdf")

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 5.6))
    fig.subplots_adjust(left=.14, right=.98, top=.94, bottom=.14, hspace=.45)
    for ax, truth in zip(axes, (False, True)):
        rows = [r for r in values["fidelity_pressure"] if r["truth"] == truth]
        ax.plot(range(3), [r["accuracy"] for r in rows], "o-", color="#087f8c", ms=4, label="Accuracy")
        ax.plot(range(3), [r["probability"] for r in rows], "s--", color="#c43c52", ms=4,
                label="Mean correct-answer probability")
        ax.set_xticks(range(3), [r["label"] for r in rows])
        ax.set(ylim=(-.02, 1.04), ylabel="Fraction / probability")
        ax.set_title("False statement / user asserts" if not truth else "True statement / user doubts",
                     loc="left", pad=9)
        ax.grid(axis="y", alpha=.18)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2,
               frameon=False, bbox_to_anchor=(.55, .015))
    finish(fig, "fidelity_pressure.pdf")
    return {"matplotlib": matplotlib.__version__, "figures": audits}


def inspect_pdf(path):
    fonts = subprocess.check_output(["pdffonts", str(path)], text=True)
    require("Type 3" not in fonts and "TrueType" in fonts, "Missing TrueType / Type 3 font: " + str(path))
    require(all(row.split()[-5] == "yes" for row in fonts.splitlines()[2:] if row.strip()),
            "Unembedded PDF font")
    xml = ET.fromstring(subprocess.check_output(
        ["pdftohtml", "-xml", "-i", "-stdout", "-zoom", "1", str(path)]))
    sizes = [float(font.attrib["size"]) for font in xml.iter("fontspec")]
    require(sizes and min(sizes) >= 8.5, "PDF font below 8.5pt")
    require(len(list(xml.iter("page"))) == 1, "Unexpected PDF page count")
    images = subprocess.check_output(["pdfimages", "-list", str(path)], text=True)
    require(len(images.splitlines()) == 2, "Raster image in vector export")
    text = subprocess.check_output(["pdftotext", str(path), "-"], text=True)
    for forbidden in ("Random-subset steering:", "Points: complete pairs", "All target and matched-panel",
                      "Native SAE re-encoding:", "Lines connect before/after", "Unsteered truth-cell responses",
                      "Pressure 0", "Pressure 1", "No population intervals", "Scope:"):
        require(forbidden not in text, "Embedded original caption/code: " + forbidden)
    require(len(text) < 1600, "Unexpected hidden PDF text")
    return {"text_characters": len(text), "type3_fonts": False, "minimum_pdf_font_pt": min(sizes),
            "raster_images": 0}


def build(out=PACKAGE, root=ROOT):
    out = Path(out).resolve()
    require(out == PACKAGE or not out.is_relative_to(ROOT), "Only the presentation package or external scratch may be written")
    require(not out.is_symlink(), "Symlink output")
    values, inputs = collect(root)
    out.mkdir(parents=True, exist_ok=True)
    (out / "plotted_values.json").write_bytes(encoded(values))
    (out / "plotted_values.csv").write_bytes(csv_bytes(values))
    rendering = render(values, out)
    files = {name: {"sha256": sha((out/name).read_bytes()), "bytes": (out/name).stat().st_size}
             for name in ("plotted_values.json", "plotted_values.csv", *PDFS)}
    inspections = {name: inspect_pdf(out/name) for name in PDFS}
    manifest = dict(schema="historical_figure_presentation_manifest_v1", scope=SCOPE, inputs=inputs,
                    files=files, rendering=rendering, pdf_checks=inspections,
                    generator_sha256=sha(Path(__file__).read_bytes()))
    (out / "manifest.json").write_bytes(encoded(manifest))
    return verify(out, root)


def verify(out=PACKAGE, root=ROOT, check_render=False):
    out = Path(out)
    values, inputs = collect(root)
    manifest = json.loads((out/"manifest.json").read_text())
    require(manifest["scope"] == SCOPE and manifest["inputs"] == inputs, "Manifest input/scope drift")
    require(manifest["generator_sha256"] == sha(Path(__file__).read_bytes()), "Presentation generator changed")
    require((out/"plotted_values.json").read_bytes() == encoded(values), "Plotted JSON changed")
    require((out/"plotted_values.csv").read_bytes() == csv_bytes(values), "Plotted CSV changed")
    require(set(manifest["files"]) == {"plotted_values.json", "plotted_values.csv", *PDFS}, "Output inventory changed")
    for name, entry in manifest["files"].items():
        raw = (out/name).read_bytes()
        require(sha(raw) == entry["sha256"] and len(raw) == entry["bytes"], "Output changed: " + name)
    for name in PDFS:
        require(inspect_pdf(out/name) == manifest["pdf_checks"][name], "PDF inspection changed")
        spec = manifest["rendering"]["figures"][name]
        require(spec["width_bp"] == 468 and spec["minimum_font_pt"] >= 8.5, "Print-size constraint changed")
    if check_render:
        with tempfile.TemporaryDirectory(prefix="figure-presentation-") as scratch:
            rendering = render(values, scratch)
            require(rendering == manifest["rendering"], "Renderer version or geometry differs")
            for name in PDFS:
                require(sha((Path(scratch)/name).read_bytes()) == manifest["files"][name]["sha256"],
                        "PDF redraw differs: " + name)
    return {"pass": True, "pdfs": len(PDFS), "input_files": len(inputs), "native_seed_readings": 240,
            "pressure_items": 150, "new_inference": False, "render_reproduced": check_render}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write only the unfrozen presentation package")
    parser.add_argument("--check-render", action="store_true", help="Redraw in temporary storage and compare bytes")
    args = parser.parse_args()
    result = build() if args.write else verify(check_render=args.check_render)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
