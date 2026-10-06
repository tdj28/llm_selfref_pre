#!/usr/bin/env python3
"""Render/check the original-pair rate plot and appendix table from pinned CSVs.

Default is read-only. --write updates only evidence/calibration_rates;
--rerender also checks a fresh PDF against the saved one. All rate intervals
are copied from the released analysis (Wilson, z=1.96), not newly estimated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/calibration_rates"
RELEASE = "data/causal_transplant/confirmatory_v1_20260709"
PIN = "f5e906e1737bc71bf20b642af1d698018eec82fe"
INPUTS = {
    "openai": "986a5a786e2b9aac458288db4d865362d7ebca58537666f8328b0b9ae8e3dedc",
    "anthropic": "92b1295e43634ea0eac88850faf3eba615b990c1a0c5885b4636d0b9347f7dfb",
}
METHOD = "experiments/causal_transplant/analyze_causal_transplant.py"
METHOD_SHA = "a704f0420de15d9eb07d49bac4048169f8c3272d7055d82b522c94cc2598a87b"
MODELS = (
    ("openai:gpt-4o-2024-11-20", "GPT-4o"),
    ("openai:gpt-4.1-2025-04-14", "GPT-4.1"),
    ("anthropic:claude-haiku-4-5-20251001", "Haiku 4.5"),
    ("anthropic:claude-sonnet-4-5-20250929", "Sonnet 4.5"),
)
JUDGES = (("openai", "OpenAI judge"), ("anthropic", "Anthropic judge"))
CONDITIONS = ("paper_history", "paper_self_ref")
QUERY = "indirect_experience"
PDF = "calibration_rates.pdf"
SCOPE = {
    "query": QUERY,
    "interval": "Released pointwise 95% Wilson rate intervals, z=1.96",
    "sampling": "Independent condition draws; lines connect rates, not paired responses",
    "new_inference": False,
    "new_outcomes": False,
    "human_validation": False,
    "verification": "Hash-pinned summary CSVs, complete cells, integer counts, plotted artists and output hashes",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_path(judge):
    return f"{RELEASE}/analysis_{judge}_paper/paper_calibration_rates.csv"


def load(root=ROOT):
    require(sha((root / METHOD).read_bytes()) == METHOD_SHA, "Analysis method changed")
    tables = {}
    for judge, digest in INPUTS.items():
        raw = (root / source_path(judge)).read_bytes()
        require(sha(raw) == digest, "Input hash mismatch: " + judge)
        tables[judge] = list(csv.DictReader(io.StringIO(raw.decode())))
    return tables


def derive(tables):
    rows = []
    for judge, _ in JUDGES:
        selected = [r for r in tables[judge] if r["query_id"] == QUERY]
        expected = {(model, condition) for model, _ in MODELS for condition in CONDITIONS}
        keys = [(r["model_key"], r["instruction_cell"]) for r in selected]
        require(len(keys) == len(expected) and set(keys) == expected,
                "Missing, duplicate or unexpected calibration cells")
        lookup = dict(zip(keys, selected))
        for model, label in MODELS:
            for condition in CONDITIONS:
                row = lookup[model, condition]
                require(row["n_rows"] == row["n_labeled"] == "20", "Calibration count/missingness changed")
                rate, low, high = (float(row[k]) for k in ("positive_rate", "ci_low", "ci_high"))
                require(all(math.isfinite(v) for v in (rate, low, high))
                        and 0 <= low <= rate <= high <= 1, "Invalid rate or interval")
                positive = round(20 * rate)
                require(abs(positive / 20 - rate) < 1e-12, "Noninteger positive count")
                rows.append(dict(judge=judge, model_key=model, model_label=label,
                                 condition=condition, positive=positive, n=20,
                                 rate=rate, ci_low=low, ci_high=high))
    return rows


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def table_bytes(rows):
    rates = {(r["judge"], r["model_key"], r["condition"]): r["rate"] for r in rows}
    lines = [r"\begin{tabular}{@{}lccc@{}}", r"\toprule",
             r"& History $(H,H)$ & Self-referential $(S,S)$ & Difference\\",
             r"Response model & {\footnotesize OpenAI / Anthropic} & {\footnotesize OpenAI / Anthropic} & {\footnotesize OpenAI / Anthropic}\\",
             r"\midrule"]
    for model, label in MODELS:
        values = [[rates[j, model, c] for j, _ in JUDGES] for c in CONDITIONS]
        values.append([s - h for h, s in zip(*values)])
        cells = [" / ".join(f"{v:.2f}" for v in pair) for pair in values]
        lines.append(label + " & " + " & ".join(cells) + r"\\")
    return ("\n".join(lines + [r"\bottomrule", r"\end{tabular}"]) + "\n").encode()


def make_plot(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.spines.left": False}):
        fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.6), sharey=True)
        fig.subplots_adjust(left=.16, right=.985, bottom=.17, top=.80, wspace=.16)
        styles = (("paper_history", "#236d91", "o", .11),
                  ("paper_self_ref", "#ae4b48", "D", -.11))
        lookup = {(r["judge"], r["model_key"], r["condition"]): r for r in rows}
        for ax, (judge, title) in zip(axes, JUDGES):
            for index, (model, _) in enumerate(MODELS):
                y = len(MODELS) - 1 - index
                points = [lookup[judge, model, c]["rate"] for c in CONDITIONS]
                ax.plot(points, [y + .11, y - .11], color=".65", lw=1,
                        zorder=1, gid=f"connector:{judge}:{model}")
                for condition, color, marker, offset in styles:
                    r = lookup[judge, model, condition]
                    tag = f"{judge}:{model}:{condition}"
                    ax.hlines(y + offset, r["ci_low"], r["ci_high"], color=color,
                              lw=1.2, zorder=2, gid="interval:" + tag)
                    ax.vlines([r["ci_low"], r["ci_high"]], y + offset - .04,
                              y + offset + .04, color=color, lw=1.2)
                    ax.plot(r["rate"], y + offset, marker=marker, ls="none", ms=4.5,
                            color=color, mfc="white" if offset > 0 else color,
                            zorder=3, gid="rate:" + tag)
                    ax.annotate(f"{r['rate']:.0%}", (r["rate"], y + offset),
                                xytext=(0, 8 if offset > 0 else -14),
                                textcoords="offset points", ha="center", va="center",
                                color=color, fontsize=9, gid="label:" + tag)
            ax.set(xlim=(-.08, 1.08), ylim=(-.6, 3.6))
            ax.set_xticks([0, .25, .5, .75, 1], ["0%", "25%", "50%", "75%", "100%"])
            ax.set_yticks(range(4), [label for _, label in reversed(MODELS)])
            ax.tick_params(axis="y", length=0, pad=7)
            ax.spines["bottom"].set_bounds(0, 1)
            ax.spines["bottom"].set_color(".6")
            ax.grid(axis="x", color=".9", lw=.6)
            ax.set_axisbelow(True)
            ax.set_title(title, pad=14, fontsize=11)
        fig.legend([Line2D([], [], color=color, marker=marker, ls="none", ms=5,
                           mfc="white" if offset > 0 else color)
                    for _, color, marker, offset in styles],
                   ["History (H,H)", "Self-reference (S,S)"],
                   loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(.55, 1.0))
        fig.supxlabel("Answers labeled positive", x=.57, y=.035, fontsize=10)
        return fig, axes


def render(rows, path):
    import matplotlib.pyplot as plt
    from matplotlib.text import Text

    fig, _ = make_plot(rows)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for text in fig.findobj(Text):
            if not text.get_visible() or not text.get_text():
                continue
            box = text.get_window_extent(renderer)
            require(text.get_fontsize() >= 9, "Small plot text")
            require(box.x0 >= 0 and box.y0 >= 0 and box.x1 <= fig.bbox.width
                    and box.y1 <= fig.bbox.height, "Plot text clipped: " + text.get_text())
        with plt.rc_context({"pdf.fonttype": 42}):
            fig.savefig(path, metadata={"CreationDate": None, "ModDate": None,
                                       "Creator": "verify_calibration_rates.py"})
    finally:
        plt.close(fig)


def manifest(files, root=ROOT):
    return {"schema": "calibration_rate_presentation_v1", "source_commit": PIN,
            "scope": SCOPE, "inputs": {source_path(j): h for j, h in INPUTS.items()},
            "analysis_source": {"path": METHOD, "sha256": METHOD_SHA},
            "generator_sha256": sha((root / "scripts/verify_calibration_rates.py").read_bytes()),
            "files": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in files.items()}}


def build(out, root=ROOT):
    rows = derive(load(root))
    out.mkdir(parents=True, exist_ok=True)
    render(rows, out / PDF)
    files = {"rates.csv": csv_bytes(rows), "table.tex": table_bytes(rows), PDF: (out / PDF).read_bytes()}
    for name, raw in files.items():
        (out / name).write_bytes(raw)
    (out / "manifest.json").write_text(json.dumps(manifest(files, root), indent=2, sort_keys=True) + "\n")


def verify(out, root=ROOT, *, rerender=False):
    rows = derive(load(root))
    # Keep the literal table where the existing manuscript bindings can check it.
    appendix = (root / "paper/main.tex").read_text().split(r"\appendix", 1)[1]
    require(table_bytes(rows).decode().strip() in appendix, "Appendix table differs from released rates")
    files = {"rates.csv": csv_bytes(rows), "table.tex": table_bytes(rows), PDF: (out / PDF).read_bytes()}
    for name, raw in files.items():
        require((out / name).read_bytes() == raw, "Generated evidence differs: " + name)
    require(json.loads((out / "manifest.json").read_bytes()) == manifest(files, root),
            "Figure manifest/hash mismatch")
    if rerender:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / PDF
            render(rows, target)
            require(target.read_bytes() == files[PDF], "Re-rendered PDF differs")
    return {"pass": True, "rates": len(rows), "answers_per_rate": 20, "rerendered": rerender}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--rerender", action="store_true")
    args = parser.parse_args()
    try:
        out = ROOT / PACKAGE
        if args.write:
            build(out)
        print(json.dumps(verify(out, rerender=args.rerender), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print("Calibration rate verification failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
