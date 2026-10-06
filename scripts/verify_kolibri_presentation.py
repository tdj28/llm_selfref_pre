#!/usr/bin/env python3
"""Qwen-style Kolibri presentation of unchanged, hash-pinned estimates.

Default verification is read-only. --write updates only the editorial package;
the original release, publication binding and fuller uncertainty plot stay fixed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "evidence/kolibri_extension"
PACKAGE = "evidence/kolibri_presentation"
BINDING_SHA = "5f9e3d6eb923c02cb73d2a853ed778783c5988e0d05437f796b4fe65fb94adb8"
ENDPOINTS = ("inclusive_current_assertion", "explicit_current_assertion", "paper")
LABELS = ("Inclusive claim", "Explicit claim only", "Paper rubric")
STYLES = (("astra", .13, "#17607c", "o"), ("opus", -.13, "#a64438", "s"))
OWN = ("scripts/verify_kolibri_presentation.py", "tests/test_kolibri_presentation.py",
       "paper/kolibri_extension.tex", "paper/model_comparison.tex")
OUTPUTS = ("figure_data.json", "measurement.pdf", "measurement.png")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load(root=ROOT):
    raw = (root / SOURCE / "BINDING.json").read_bytes()
    require(sha(raw) == BINDING_SHA, "Original publication binding changed")
    binding = json.loads(raw)
    for entry in binding["outputs"]:
        body = (root / SOURCE / entry["path"]).read_bytes()
        require(len(body) == entry["bytes"] and sha(body) == entry["sha256"],
                "Original publication output changed: " + entry["path"])
    return (json.loads((root / SOURCE / "results.json").read_bytes()),
            json.loads((root / SOURCE / "figure_data.json").read_bytes()), binding)


def derive(result, original, binding):
    require(result["status"] == "main_complete" and original["phase"] == "main",
            "Requires the completed main panel")
    rows = []
    for endpoint in ENDPOINTS:
        for reader, *_ in STYLES:
            value = result["phases"]["main"]["judges"][reader][endpoint]["contrasts"]["instruction_minus_transcript"]
            require(value["complete_blocks"] == value["planned_blocks"] == 32
                    and value["missing_blocks"] == 0, "Block inventory changed")
            lo, hi = value["descriptive_95"]
            require(-1 <= lo <= value["estimate"] <= hi <= 1, "Invalid estimate or interval")
            rows.append({"reader": reader, "endpoint": endpoint, "estimate": value["estimate"],
                         "descriptive_ci95": value["descriptive_95"],
                         "pointwise_hoeffding95": value["worst_case_hoeffding_95"]})
    return {"schema": "kolibri-editorial-presentation-v1", "model": result["model"],
            "source_commit": binding["source_commit"], "blocks": 32, "contrast": "SH-HS",
            "rows": rows, "bootstrap_seed": original["seed"], "bootstrap_resamples": original["resamples"],
            "plotted_intervals": "Pointwise descriptive 95% paired-block bootstrap within wording families",
            "primary_inference": result["primary"],
            "fuller_plot": SOURCE + "/kolibri.pdf",
            "scope": {"new_outcomes": False, "new_inference": False, "human_validation": False,
                      "raw_receipts_replayed_by_this_script": False,
                      "note": "Original replay remains part of make paper-verify; this check binds the presentation."}}


def make_plot(data):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    import matplotlib

    # Match the adjacent Qwen figure's dimensions, rows, markers and typography.
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}):
        fig = Figure(figsize=(6.4, 2.8), dpi=180)
        FigureCanvasAgg(fig)
        ax = fig.add_axes((.28, .22, .69, .62))
        for index, endpoint in enumerate(ENDPOINTS):
            for reader, offset, color, marker in STYLES:
                row = next(r for r in data["rows"] if r["reader"] == reader and r["endpoint"] == endpoint)
                y = 2 - index + offset
                lo, hi = row["descriptive_ci95"]
                tag = reader + ":" + endpoint
                ax.hlines(y, lo, hi, color=color, linewidth=1.5, gid="interval:" + tag)
                ax.vlines([lo, hi], y-.05, y+.05, color=color, linewidth=1)
                ax.plot(row["estimate"], y, marker=marker, color=color, markersize=5,
                        label=reader.title() if index == 0 else None, gid="estimate:" + tag)
        ax.set(yticks=[2, 1, 0], yticklabels=LABELS, ylim=(-.4, 2.4),
               xlim=(-.2, 1.0), xticks=[-.2, 0, .2, .4, .6, .8, 1.0],
               xlabel="Label-rate difference (SH - HS)")
        ax.axvline(0, color="#777777", linewidth=.8)
        ax.grid(axis="x", color="#dddddd", linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=8)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, frameon=False)
    return fig, ax


def render(data, out):
    import matplotlib
    from matplotlib.text import Text

    fig, _ = make_plot(data)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in fig.findobj(Text):
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        require(text.get_fontsize() >= 9, "Small figure text")
        require(box.x0 >= 0 and box.y0 >= 0 and box.x1 <= fig.bbox.width
                and box.y1 <= fig.bbox.height, "Clipped figure text: " + text.get_text())
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        for extension in ("pdf", "png"):
            metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {}
            fig.savefig(out / ("measurement." + extension), metadata=metadata)
    fig.clear()


def manifest(root, out, binding):
    return {"schema": "kolibri-presentation-manifest-v1", "source_binding_sha256": BINDING_SHA,
            "source_commit": binding["source_commit"],
            "source_release_manifest_sha256": binding["release_manifest_sha256"],
            "sources": {path: sha((root / path).read_bytes()) for path in OWN},
            "outputs": {name: {"sha256": sha((out / name).read_bytes()),
                               "bytes": (out / name).stat().st_size} for name in OUTPUTS}}


def write(root=ROOT):
    result, original, binding = load(root)
    data = derive(result, original, binding)
    out = root / PACKAGE
    out.mkdir(parents=True, exist_ok=True)
    (out / "figure_data.json").write_bytes(encoded(data))
    render(data, out)
    (out / "manifest.json").write_bytes(encoded(manifest(root, out, binding)))


def verify(root=ROOT, *, rerender=False):
    result, original, binding = load(root)
    data = derive(result, original, binding)
    out = root / PACKAGE
    require((out / "figure_data.json").read_bytes() == encoded(data), "Figure data differs")
    require((out / "manifest.json").read_bytes() == encoded(manifest(root, out, binding)),
            "Editorial source or output hash differs")
    tex = (root / "paper/kolibri_extension.tex").read_text()
    require("../" + PACKAGE + "/measurement.pdf" in tex, "Main figure not linked")
    require(r"\KEXPrimaryAstraInclusiveSHHSBounds{}" in tex
            and r"\KEXPrimaryAstraInclusiveNSNHBounds{}" in tex, "Primary bounds omitted")
    appendix = (root / "paper/main.tex").read_text().split(r"\appendix", 1)[1]
    require("3f9857bf47894b334e18ed370e257f458d0316c7/" + SOURCE + "/kolibri.pdf" in appendix
            and r"\label{app:kolibri-uncertainty}" in appendix, "Fuller uncertainty plot link omitted")
    comparison = (root / "paper/model_comparison.tex").read_text()
    require(r"\KEXPrimaryAstraInclusiveSHHSBounds{}" in comparison,
            "Primary Kolibri bound absent from compiled comparison")
    if rerender:
        with tempfile.TemporaryDirectory() as temp:
            render(data, Path(temp))
            for name in ("measurement.pdf", "measurement.png"):
                require((Path(temp) / name).read_bytes() == (out / name).read_bytes(),
                        "Rerender differs: " + name)
    return {"pass": True, "points": len(data["rows"]), "new_inference": False, "rerendered": rerender}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--rerender", action="store_true")
    args = parser.parse_args()
    if args.write:
        write()
    print(json.dumps(verify(rerender=args.rerender), sort_keys=True))


if __name__ == "__main__":
    sys.exit(main())
