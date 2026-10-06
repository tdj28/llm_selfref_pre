#!/usr/bin/env python3
"""Build/check a descriptive cross-model swap overview from released summaries.

No new labels, uncertainty estimates, pooling or model ranking. The optional
companion import reads pinned local Git objects; verification needs no checkout.
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

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/model_overview"
COMPANION = "7cb5c984eb41968b6f3d2f9b322f4de125a1d1ca"
COMPANION_CSV = "data/release_20261003/analysis/q1.csv"
COMPANION_LICENSE_SHA = "09b5ba921b65ea3a6cb87f3a11ac29afd45f060b29ca797c3169cfe1f5c8b315"
INPUTS = {
    "evidence/inputs/causal_openai_transplant.csv": "ef65a0579816d0a0bc41810a742c2cbfce1c981ff9873bb0dbd68089426db17a",
    "evidence/inputs/causal_anthropic_transplant.csv": "3273016373b3b0068f03cbfed3898ecb6301065d12af4273f2df434ed6cb6c46",
    "data/bilingual_llama_b1/completed_20261002/analysis/analysis.json": "075bbe1c90875c739dc04c64ce730526b6a91790a140d03c596749ec245c724d",
    "data/frontier_bilingual_b1/completed_20261002/analysis/analysis.json": "5132645e0a352fd937732d00c80585bf69c717a4ece8857099ea4e400a44cd4b",
    "evidence/openrouter_swap_extension/figure_data.json": "161264a50aca40db822a8713098b825050af2dd5fd847d4390784c7f8670b7d3",
    "evidence/qwen_extension/figure_data.json": "71faec3fdeb28de09976de19bb6cdd823e8bd64e5d0445f1e0c28f13f18e049f",
    "evidence/kolibri_presentation/figure_data.json": "3ceffef0722c177a234f38204dfda85c16ec81bfa60e5434c31b16bf472361b6",
    PACKAGE + "/inputs/companion_q1.csv": "0694ea6b4f86e1d1d3b14618ac438ac3655995a200c94ca6be1b0d67010652aa",
}
MAIN_MODELS = (
    ("openai:gpt-4o-2024-11-20", "GPT-4o"),
    ("openai:gpt-4.1-2025-04-14", "GPT-4.1"),
    ("anthropic:claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("anthropic:claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
)
ENDPOINTS = ("paper", "inclusive_current_assertion")
PROVIDERS = ("openai", "anthropic")
MODERN_READERS = {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
ORIGINAL_READERS = {"openai": "gpt-4o-mini-2024-07-18", "anthropic": "claude-haiku-4-5-20251001"}
OUTPUTS = ("figure_data.json", "plotted_values.csv", "overview.pdf", "overview.png")
OWN = ("scripts/verify_model_overview.py", "tests/test_model_overview.py", "paper/model_comparison.tex")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def one(rows, **selector):
    found = [r for r in rows if all(r.get(k) == v for k, v in selector.items())]
    require(len(found) == 1, "Missing or duplicate selection: " + repr(selector))
    return found[0]


def load(root=ROOT):
    data = {}
    for path, digest in INPUTS.items():
        raw = (root / path).read_bytes()
        require(sha(raw) == digest, "Input hash changed: " + path)
        data[path] = (list(csv.DictReader(io.StringIO(raw.decode())))
                      if path.endswith(".csv") else json.loads(raw))
    require(sha((root / PACKAGE / "inputs/companion_LICENSE").read_bytes()) == COMPANION_LICENSE_SHA,
            "Companion license changed")
    return data


def complete_rate(row, n, rate_key):
    require(row["planned"] == row["observed"] == n and row["missing"] == 0,
            "Incomplete cell cannot enter this overview")
    require(type(row["positive"]) is int and 0 <= row["positive"] <= n, "Invalid count")
    require(abs(row[rate_key] - row["positive"] / n) < 1e-12, "Rate/count mismatch")
    return row["positive"] / n


def derive(data):
    rows = []

    def add(group, model, label, n, endpoint, provider, estimate, source, selector, primary=False):
        require(math.isfinite(estimate) and -1 <= estimate <= 1, "Invalid contrast")
        readers = ORIGINAL_READERS if group == "original" else MODERN_READERS
        rows.append(dict(group=group, model=model, label=label, blocks=n, endpoint=endpoint,
                         provider=provider, reader=readers[provider], estimate=estimate,
                         primary_endpoint=primary, source=source, selector=selector))

    for model, label in MAIN_MODELS:
        for provider in PROVIDERS:
            source = f"evidence/inputs/causal_{provider}_transplant.csv"
            selector = dict(level="model", model_key=model, query_id="indirect_experience",
                            effect="instruction_minus_transcript")
            row = one(data[source], **selector)
            require(row["n_pairs"] == row["n_clusters"] == "20", "Original inventory changed")
            add("original", model, label, 20, "paper", provider, float(row["estimate"]),
                source, selector, primary=True)

    source = "data/frontier_bilingual_b1/completed_20261002/analysis/analysis.json"
    for model, label in (("gpt41", "GPT-4.1"), ("opus", "Claude Opus 5.5"), ("astra", "GPT-6 Astra")):
        for endpoint in ENDPOINTS:
            for provider in PROVIDERS:
                selector = dict(model=model, judge=provider, language="en",
                                endpoint="paper_positive" if endpoint == "paper" else endpoint)
                cells = {i+t: complete_rate(one(data[source]["cells"], **selector,
                         instruction=i, transcript=t), 6, "rate")
                         for i in ("self", "history") for t in ("self", "history")}
                estimate = cells["selfhistory"] - cells["historyself"]
                effects = data[source]["contrasts"]
                check = (one(effects, **selector, contrast="instruction_effect")["estimate"]
                         - one(effects, **selector, contrast="transcript_effect")["estimate"])
                require(abs(estimate-check) < 1e-12, "Frontier contrast identity failed")
                add("frontier", model, label, 6, endpoint, provider, estimate, source, selector,
                    primary=endpoint != "paper")

    source = "data/bilingual_llama_b1/completed_20261002/analysis/analysis.json"
    for endpoint in ENDPOINTS:
        for provider in PROVIDERS:
            selector = dict(kind="main", context_language="en", output_language="en", provider=provider,
                            endpoint="paper_positive" if endpoint == "paper" else endpoint)
            sh = complete_rate(one(data[source]["rates"], **selector,
                               instruction="self", transcript="history"), 20, "rate_observed")
            hs = complete_rate(one(data[source]["rates"], **selector,
                               instruction="history", transcript="self"), 20, "rate_observed")
            effects = {component: one(data[source]["effects"], panel="anchor", provider=provider,
                       endpoint=selector["endpoint"], contrast=component+"_average:en")["estimate"]
                       for component in ("instruction", "transcript")}
            require(abs(sh-hs-effects["instruction"]+effects["transcript"]) < 1e-12,
                    "Llama contrast identity failed")
            add("local", "llama", "Llama 3.3 70B", 20, endpoint, provider, sh-hs, source, selector,
                primary=endpoint != "paper")

    source = PACKAGE + "/inputs/companion_q1.csv"
    for endpoint in ENDPOINTS:
        for provider in PROVIDERS:
            selector = dict(question="q1", model="qwen", reader=provider, kind="cell",
                            endpoint="paper_positive" if endpoint == "paper" else endpoint)
            cells = [one(data[source], **selector, name=name) for name in ("SH", "HS")]
            for row in cells:
                require(row["planned"] == row["ok"] == "20"
                        and all(row[k] == "0" for k in ("not_ok", "absent", "missing_response")),
                        "Companion cell missingness changed")
                require(abs(float(row["estimate"])-int(row["positive"])/20) < 1e-12,
                        "Companion count/rate mismatch")
            add("local", "qwen35", "Qwen3.5-397B-A17B", 20, endpoint, provider,
                (int(cells[0]["positive"])-int(cells[1]["positive"]))/20, source, selector,
                primary=endpoint != "paper")

    for model, label, package in (
        ("gemini", "Gemini 3.1 Pro Preview", "openrouter_swap_extension"),
        ("opus", "Claude Opus 5.5", "openrouter_swap_extension"),
        ("qwen38", "Qwen3.8-2.4T-A95B", "qwen_extension"),
        ("kolibri", "Kolibri-1", "kolibri_presentation"),
    ):
        source = f"evidence/{package}/figure_data.json"
        require(data[source]["blocks"] == 32, "Larger panel inventory changed")
        for endpoint in ENDPOINTS:
            for provider, judge in zip(PROVIDERS, ("astra", "opus")):
                selector = dict(endpoint=endpoint)
                selector["reader" if model == "kolibri" else "judge"] = judge
                if package == "openrouter_swap_extension":
                    selector["model"] = model
                row = one(data[source]["rows"], **selector)
                add("extended", model, label, 32, endpoint, provider, row["estimate"], source,
                    selector, primary=endpoint != "paper")

    require(len(rows) == 44, "Overview inventory changed")
    require(len({(r["group"], r["model"], r["endpoint"], r["provider"]) for r in rows}) == 44,
            "Duplicate plotted measurements")
    return dict(schema="cross-model-overview-v1", contrast="SH-HS", language="en", rows=rows,
                scope=dict(point_estimates_only=True, pooled=False, model_ranking=False,
                           new_outcomes=False, new_inference=False, human_validation=False,
                           note="Original single-answer panels; screen-only models and qualification repeats excluded. "
                                "Missing rubric cells are not scored, not zero. Primary intervals remain in the paper."))


def csv_bytes(data):
    out = io.StringIO(newline="")
    fields = ("group", "model", "label", "blocks", "endpoint", "provider", "reader",
              "estimate", "primary_endpoint", "source")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(data["rows"])
    return out.getvalue().encode()


def make_plot(data):
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle

    groups = (
        ("original", "Original panel", "GPT-4o mini / Claude Haiku 4.5", [m for m, _ in MAIN_MODELS]),
        ("frontier", "Frontier pilot", "GPT-6 Astra / Claude Opus 5.5", ["gpt41", "opus", "astra"]),
        ("local", "Local-weight panels", "GPT-6 Astra / Claude Opus 5.5", ["llama", "qwen35"]),
        ("extended", "Larger panels", "GPT-6 Astra / Claude Opus 5.5", ["gemini", "opus", "qwen38", "kolibri"]),
    )
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}):
        fig = Figure(figsize=(6.5, 6.0), dpi=200)
        FigureCanvasAgg(fig)
        ax = fig.add_axes((.01, .16, .98, .78))
        ax.set(xlim=(0, 10), ylim=(18.2, -1.5))
        ax.set_axis_off()
        cmap = LinearSegmentedColormap.from_list("contrast", ["#a64438", "#fafafa", "#17607c"])
        norm = Normalize(-1, 1)
        centers = (5.0, 6.34, 7.95, 9.29)
        for x, title in ((5.67, "Paper rubric"), (8.62, "Inclusive claims")):
            ax.text(x, -1.15, title, ha="center", va="center", weight="bold", fontsize=10.5)
        for x, label in zip(centers, ("OpenAI", "Anthropic", "OpenAI", "Anthropic")):
            ax.text(x, -.5, label, ha="center", va="center", fontsize=9.5)
        ax.text(.04, -.5, "Response model", va="center", fontsize=9.5, color="#444444")
        ax.text(3.92, -.5, "Blocks", ha="center", va="center", fontsize=9.5, color="#444444")
        y = .7
        for group, title, readers, models in groups:
            ax.text(.04, y, title, weight="bold", va="center", fontsize=10)
            ax.text(9.88, y, readers, ha="right", va="center", fontsize=9.2, color="#555555")
            ax.hlines(y+.39, 0, 9.94, color="#cacaca", linewidth=.7)
            y += 1.05
            for model in models:
                values = [r for r in data["rows"] if r["group"] == group and r["model"] == model]
                ax.text(.04, y, values[0]["label"], va="center", fontsize=10)
                ax.text(3.92, y, str(values[0]["blocks"]), ha="center", va="center", fontsize=10)
                for j, (endpoint, provider) in enumerate((e, p) for e in ENDPOINTS for p in PROVIDERS):
                    found = [r for r in values if r["endpoint"] == endpoint and r["provider"] == provider]
                    tag = group + ":" + model + ":" + endpoint + ":" + provider
                    x = centers[j]
                    value = found[0]["estimate"] if found else None
                    color = "#eeeeee" if value is None else cmap(norm(value))
                    ax.add_patch(Rectangle((x-.60, y-.37), 1.20, .74, facecolor=color, edgecolor="white",
                                           linewidth=.6, gid="cell:" + tag))
                    text = "n/a" if value is None else ("0.0" if abs(value) < 1e-12 else f"{value*100:+.1f}")
                    ink = "#777777" if value is None else ("white" if abs(value) >= .65 else "#222222")
                    ax.text(x, y, text, ha="center", va="center", color=ink, fontsize=10,
                            gid="value:" + tag)
                y += 1
            y += .35
        ax.set_ylim(y-.6, -1.5)
        cax = fig.add_axes((.40, .088, .57, .023))
        from matplotlib.colorbar import ColorbarBase
        cb = ColorbarBase(cax, cmap=cmap, norm=Normalize(-100, 100), orientation="horizontal",
                          ticks=[-100, -50, 0, 50, 100])
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=9, length=2)
        cb.set_label("SH - HS (percentage points)", fontsize=10, labelpad=4)
        fig.text(.025, .091, "n/a = not scored", fontsize=9.5, color="#555555")
    return fig


def render(data, out):
    import matplotlib
    from matplotlib.text import Text
    fig = make_plot(data)
    fig.canvas.draw()
    for text in fig.findobj(Text):
        if text.get_visible() and text.get_text():
            box = text.get_window_extent(fig.canvas.get_renderer())
            require(text.get_fontsize() >= 9, "Small figure text")
            require(box.x0 >= 0 and box.y0 >= 0 and box.x1 <= fig.bbox.width and box.y1 <= fig.bbox.height,
                    "Clipped text: " + text.get_text())
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        for suffix in ("pdf", "png"):
            metadata = {"CreationDate": None, "ModDate": None} if suffix == "pdf" else {}
            fig.savefig(out / ("overview." + suffix), metadata=metadata)
    fig.clear()


def manifest(root, out):
    return dict(schema="cross-model-overview-manifest-v1", inputs=INPUTS,
                companion_commit=COMPANION, companion_source=COMPANION_CSV,
                companion_license_sha256=COMPANION_LICENSE_SHA,
                sources={p: sha((root / p).read_bytes()) for p in OWN},
                outputs={p: sha((out / p).read_bytes()) for p in OUTPUTS})


def import_companion(repo, root=ROOT):
    out = root / PACKAGE / "inputs"
    out.mkdir(parents=True, exist_ok=True)
    for path, name in ((COMPANION_CSV, "companion_q1.csv"), ("LICENSE", "companion_LICENSE")):
        raw = subprocess.run(["git", "--no-lazy-fetch", "-C", str(repo), "show", COMPANION+":"+path],
                             check=True, capture_output=True).stdout
        if name.endswith(".csv"):
            require(sha(raw) == INPUTS[PACKAGE + "/inputs/companion_q1.csv"], "Companion source changed")
        else:
            require(sha(raw) == COMPANION_LICENSE_SHA, "Companion license changed")
        (out / name).write_bytes(raw)


def write(root=ROOT):
    data = derive(load(root))
    out = root / PACKAGE
    out.mkdir(parents=True, exist_ok=True)
    (out / "figure_data.json").write_bytes(encoded(data))
    (out / "plotted_values.csv").write_bytes(csv_bytes(data))
    render(data, out)
    (out / "manifest.json").write_bytes(encoded(manifest(root, out)))


def verify(root=ROOT, rerender=False):
    data = derive(load(root))
    out = root / PACKAGE
    require((out / "figure_data.json").read_bytes() == encoded(data), "Figure data differs")
    require((out / "plotted_values.csv").read_bytes() == csv_bytes(data), "CSV differs")
    require((out / "manifest.json").read_bytes() == encoded(manifest(root, out)), "Manifest differs")
    tex = (root / "paper/model_comparison.tex").read_text()
    require("../" + PACKAGE + "/overview.pdf" in tex, "Overview not included")
    require("point estimates, not confidence intervals" in " ".join(tex.split()), "Scope disclosure missing")
    require(r"\ORSGeminiAstraInclusiveCI{}" in tex and r"\KEXPrimaryAstraInclusiveSHHSBounds{}" in tex,
            "Primary interval table removed")
    if rerender:
        with tempfile.TemporaryDirectory() as temp:
            render(data, Path(temp))
            for name in ("overview.pdf", "overview.png"):
                require((Path(temp) / name).read_bytes() == (out / name).read_bytes(), "Rerender differs: " + name)
    return dict(pass_check=True, plotted_estimates=len(data["rows"]), model_rows=13, unique_models=11,
                new_outcomes=False, new_inference=False, rerendered=rerender)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rerender", action="store_true")
    parser.add_argument("--import-companion", type=Path)
    args = parser.parse_args()
    if args.import_companion:
        import_companion(args.import_companion)
    if args.write:
        write()
    print(json.dumps(verify(rerender=args.rerender), sort_keys=True))


if __name__ == "__main__":
    main()
