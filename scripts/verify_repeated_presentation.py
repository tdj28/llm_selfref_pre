#!/usr/bin/env python3
"""Four-point summary of the immutable repeated-answer publication.

Default verification is read-only. --write updates only the editorial package.
No responses, judgments, estimates or uncertainty intervals are recomputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "evidence/repeated_extension"
PACKAGE = "evidence/repeated_presentation"
SOURCE_SHA = "b2cd569022042097cf574f2dd7038cad20489a6b43992eeb01f631357ff5e242"
MODELS = (("gemini", "Gemini 3.1\nPro Preview"), ("opus", "Claude Opus 5.5"))
STYLES = (("astra", .13, "#17607c", "o"), ("opus", -.13, "#a64438", "s"))
OWN = ("scripts/verify_repeated_presentation.py", "tests/test_repeated_presentation.py",
       "tests/test_repeated_editorial.py", "paper/repeated_extension_editorial.tex",
       "paper/model_comparison.tex")
OUTPUTS = ("figure_data.json", "summary.pdf", "summary.png")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load(root=ROOT):
    raw = (root / SOURCE / "manifest.json").read_bytes()
    require(sha(raw) == SOURCE_SHA, "Original publication manifest changed")
    for entry in json.loads(raw)["files"]:
        body = (root / SOURCE / entry["path"]).read_bytes()
        require(len(body) == entry["bytes"] and sha(body) == entry["sha256"],
                "Original publication output changed: " + entry["path"])
    return (json.loads((root / SOURCE / "figure_data.json").read_bytes()),
            json.loads((root / SOURCE / "binding.json").read_bytes()))


def derive(original, binding):
    require(original["primary_reader"] == "astra" and original["primary_family_size"] == 2,
            "Primary reader or comparison family changed")
    rows = []
    for model, label in MODELS:
        for reader, *_ in STYLES:
            contrast = original["models"][model]["readers"][reader]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]
            bootstrap = contrast["bootstrap"]
            require(bootstrap["confidence"] == (.975 if reader == "astra" else .95),
                    "Interval confidence differs from the frozen analysis")
            require(contrast["planned_blocks"] == 32 and contrast["coefficients"] == {"HS": -1, "SH": 1},
                    "Sampling inventory or contrast changed")
            rows.append({"model": model, "model_label": label.replace("\n", " "), "reader": reader,
                         "estimate": contrast["complete_case_mean"], "bootstrap": bootstrap,
                         "complete_blocks": contrast["complete_blocks"], "planned_blocks": contrast["planned_blocks"],
                         "missing_blocks": contrast["missing_blocks"],
                         "missing_label_bounds": contrast["worst_case_mean_bounds"],
                         "conservative_all_planned_bounds": contrast["worst_case_hoeffding"]})
    return {"schema": "repeated-summary-presentation-v1", "source_commit": binding["release_commit"],
            "endpoint": original["primary_endpoint"], "contrast": "SH-HS", "rows": rows,
            "nominal_family_confidence": original["nominal_family_confidence"],
            "primary_family_size": original["primary_family_size"], "primary_reader": original["primary_reader"],
            "fuller_plot": SOURCE + "/repeated_main.pdf",
            "scope": {"new_outcomes": False, "new_inference": False, "human_validation": False,
                      "raw_receipts_replayed_by_this_script": False,
                      "note": "Original replay remains in make paper-verify; this check binds the presentation."}}


def make_plot(data):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    import matplotlib

    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}):
        fig = Figure(figsize=(6.4, 2.8), dpi=180)
        FigureCanvasAgg(fig)
        ax = fig.add_axes((.28, .22, .69, .62))
        for index, (model, _) in enumerate(MODELS):
            for reader, offset, color, marker in STYLES:
                row = next(r for r in data["rows"] if r["reader"] == reader and r["model"] == model)
                y = 1 - index + offset
                lo, hi = row["bootstrap"]["interval"]
                tag = model + ":" + reader
                ax.hlines(y, lo, hi, color=color, linewidth=1.5, gid="interval:" + tag)
                ax.vlines([lo, hi], y-.05, y+.05, color=color, linewidth=1)
                ax.plot(row["estimate"], y, marker=marker, color=color, markersize=5,
                        label=reader.title() if index == 0 else None, gid="estimate:" + tag)
        ax.set(yticks=[1, 0], yticklabels=[label for _, label in MODELS], ylim=(-.4, 1.4),
               xlim=(-.1, 1), xticks=[0, .2, .4, .6, .8, 1],
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
            fig.savefig(out / ("summary." + extension), metadata=metadata)
    fig.clear()


def manifest(root, out, binding):
    return {"schema": "repeated-presentation-manifest-v1", "source_manifest_sha256": SOURCE_SHA,
            "source_commit": binding["release_commit"],
            "source_release_manifest_sha256": binding["release_manifest_sha256"],
            "sources": {path: sha((root / path).read_bytes()) for path in OWN},
            "outputs": {name: {"sha256": sha((out / name).read_bytes()),
                               "bytes": (out / name).stat().st_size} for name in OUTPUTS}}


def write(root=ROOT):
    original, binding = load(root)
    data = derive(original, binding)
    out = root / PACKAGE
    out.mkdir(parents=True, exist_ok=True)
    (out / "figure_data.json").write_bytes(encoded(data))
    render(data, out)
    (out / "manifest.json").write_bytes(encoded(manifest(root, out, binding)))


def verify(root=ROOT, *, rerender=False):
    original, binding = load(root)
    data = derive(original, binding)
    out = root / PACKAGE
    require((out / "figure_data.json").read_bytes() == encoded(data), "Figure data differs")
    require((out / "manifest.json").read_bytes() == encoded(manifest(root, out, binding)),
            "Editorial source or output hash differs")
    tex = (root / "paper/model_comparison.tex").read_text()
    require("../" + PACKAGE + "/summary.pdf" in tex, "Summary figure not linked")
    require("97.5\\%" in tex and "95\\%" in tex
            and "all-planned bound for Opus includes zero" in " ".join(tex.split()),
            "Interval distinction or conservative sensitivity caveat omitted")
    appendix = (root / "paper/main.tex").read_text().split(r"\appendix", 1)[1]
    require("c09b19445c24e63f5160953883e71d76850fa9df/" + SOURCE + "/repeated_main.pdf" in appendix
            and r"\label{app:repeated-bounds}" in appendix, "Detailed plot link or bounds omitted")
    for row in data["rows"]:
        low, high = row["conservative_all_planned_bounds"]
        require(f"$[{low:.2f},{high:.2f}]$" in appendix,
                "Conservative bound differs from the frozen repeated-answer result")
    if rerender:
        with tempfile.TemporaryDirectory() as temporary:
            render(data, Path(temporary))
            for name in ("summary.pdf", "summary.png"):
                require((Path(temporary) / name).read_bytes() == (out / name).read_bytes(),
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
