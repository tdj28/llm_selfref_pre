#!/usr/bin/env python3
"""Present the released bilingual contrasts and preselected translation cases.

Default: read-only hash/data verification. --write rebuilds only the compact
presentation package. It never changes or reanalyzes a frozen release.
--cjk-font is needed only to rebuild the embedded-font Chinese example PDF.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify_completed_extensions as completed

PACKAGE = "evidence/bilingual_presentation"
RELEASE = completed.PINS["bilingual"][0]
MANIFEST_SHA = "0a2e78ef585106ac72c6ed3991394a892efc072957ce9c4f8491b27c855848af"
ENDPOINTS = (
    ("inclusive_current_assertion", "Explicit or implicit\ncurrent claim (primary)"),
    ("explicit_current_assertion", "Explicit current claim\n(secondary)"),
    ("paper_positive", "Paper rubric\n(secondary)"),
)
READERS = (("openai", "Astra", "#21698d", "o"),
           ("anthropic", "Opus 5.5", "#aa4646", "s"))
CASES = ((1, "self", "Self-reference"), (9, "recursive", "External feedback control"))
PDFS = ("language_contrasts.pdf", "bilingual_examples.pdf")
TRANSLATION_DISPLAY_EDITS = {
    "block-01-main-zh-self-self": [{
        "original": "an attention", "replacement": "attention",
        "source_chinese": "关注",
        "reason": "Remove an unnatural English article; retain 'thoughts' and all other wording.",
    }],
}
SCOPE = {
    "new_outcomes": False, "new_inference": False, "human_validation": False,
    "intervals": "Released within-wording paired-block bootstrap intervals; secondary intervals unadjusted",
    "selection": "The protocol-selected translation pairs for the two primary conditions; not representative sampling",
    "translations": "Recorded Claude Opus 5.5 translations retained unchanged; block 01 display alone changes 'an attention' to 'attention'. No new translation or human validation",
    "figures": "Plot uses released estimates, not pooled readers; original-language excerpts are verbatim; display translation edits are recorded per example; labels score complete original answers without rescoring",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def load(root=ROOT):
    base = root / RELEASE
    raw = (base / "MANIFEST.json").read_bytes()
    require(sha(raw) == MANIFEST_SHA, "Bilingual release manifest changed")
    entries = {r["path"]: r for r in json.loads(raw)["files"]}
    inputs = {f"{RELEASE}/MANIFEST.json": MANIFEST_SHA}

    def read(name):
        raw = (base / name).read_bytes()
        require(sha(raw) == entries[name]["sha256"] and len(raw) == entries[name]["bytes"],
                "Release input hash mismatch: " + name)
        inputs[f"{RELEASE}/{name}"] = sha(raw)
        return raw

    analysis = json.loads(read("analysis/analysis.json"))
    selected = completed.bilingual_result({"analysis/analysis.json": analysis,
                                         "raw/DONE-all.json": json.loads(read("raw/DONE-all.json"))})
    plan = json.loads(read("raw/PLAN.json"))
    translations = [json.loads(line) for line in read("judges/translations.jsonl").splitlines()]
    table = list(csv.DictReader(io.StringIO(read("analysis/case_table.csv").decode())))
    effects = [dict(provider=p, endpoint=e, **selected["readers"][p][e]["zh_minus_en"])
               for e, _ in ENDPOINTS for p, *_ in READERS]
    cases = []
    for block, condition, title in CASES:
        case = {"block": block, "condition": condition, "title": title}
        for language in ("en", "zh"):
            identity = f"block-{block:02d}-main-{language}-{condition}-{condition}"
            require(identity in plan["translation_item_ids"], "Example not prospectively selected for translation")
            row = json.loads(read(f"raw/generations/{identity}.json"))
            require(row["status"] == "complete" and not row["cap_hit"], "Incomplete example")
            require(sha(row["response"].encode()) == row["response_sha256"], "Response hash mismatch")
            labels = {}
            for provider, *_ in READERS:
                label = completed.one(table, id=identity, provider=provider)
                labels[provider] = {e: int(label[e]) for e, _ in ENDPOINTS}
            case[language] = {"id": identity, "response": row["response"],
                              "excerpt": row["response"].split("。" if language == "zh" else ".", 1)[0]
                              + ("。" if language == "zh" else "."),
                              "query": row["messages"][-1]["content"],
                              "instruction": row["messages"][0]["content"], "labels": labels}
            if language == "zh":
                translation = completed.one(translations, item_id=identity, status="ok")
                require(translation["response_sha256"] == row["response_sha256"], "Translation source mismatch")
                translated = translation["label"]["response"]
                artifact = json.dumps(translation["label"], ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":")).encode()
                require(sha(artifact) == translation["derived"]["translation_sha256"],
                        "Translation hash mismatch")
                case["translation"] = translated
                case["translation_excerpt"] = translated.split(".", 1)[0] + "."
                case["translation_model"] = translation["model"]
                # Keep the receipt text separate from the editorial display.
                display = case["translation_excerpt"]
                edits = [dict(edit) for edit in TRANSLATION_DISPLAY_EDITS.get(identity, [])]
                for edit in edits:
                    require(edit["source_chinese"] in case["zh"]["excerpt"],
                            "Display correction Chinese source mismatch")
                    require(display.count(edit["original"]) == 1,
                            "Display correction must match exactly once")
                    display = display.replace(edit["original"], edit["replacement"], 1)
                case["translation_display_excerpt"] = display
                case["translation_display_edits"] = edits
        cases.append(case)
    return {"effects": effects, "examples": cases, "scope": SCOPE}, inputs


def make_contrast_plot(data):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.7, 3.55))
    fig.subplots_adjust(left=.34, right=.97, top=.86, bottom=.24)
    ax.axhspan(1.55, 2.45, color="#eef4f2", zorder=0)
    ax.axvline(0, color="#777777", lw=.85, linestyle="--")
    for index, (endpoint, _) in enumerate(ENDPOINTS):
        for offset, (provider, title, color, marker) in zip((.13, -.13), READERS):
            row = completed.one(data["effects"], endpoint=endpoint, provider=provider)
            point, low, high = (100 * row["estimate"], *[100 * v for v in row["ci95"]])
            artist = ax.errorbar(point, 2 - index + offset,
                                xerr=[[point - low], [high - point]],
                                fmt=marker, color=color, markersize=5.5,
                                capsize=3, elinewidth=1.4,
                                label=title if index == 0 else None)
            artist.lines[0].set_gid(f"{provider}:{endpoint}")
    ax.set_yticks([2, 1, 0], [label for _, label in ENDPOINTS])
    ax.set_ylim(-.45, 2.5)
    ax.set_xlim(-85, 115)
    ax.set_xticks([-75, -50, -25, 0, 25, 50, 75, 100])
    ax.set_xlabel("Chinese minus English in the self-reference/control gap\n(percentage points)", labelpad=10)
    ax.tick_params(axis="y", length=0, pad=10)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", color="#eeeeee", linewidth=.6)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(-.01, 1.02), ncol=2, frameon=False)
    return fig


def make_examples(data, cjk_font):
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.ft2font import FT2Font
    from matplotlib.lines import Line2D

    width, height = 6.7, 7.1
    fig = plt.figure(figsize=(width, height))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    english = FontProperties(family="DejaVu Sans", size=10)
    chinese = FontProperties(fname=str(cjk_font), size=10)
    chars = set("".join(c["zh"]["response"] + c["zh"]["query"] for c in data["examples"]))
    charmap = FT2Font(str(cjk_font)).get_charmap()
    require(all(ord(c) in charmap for c in chars if not c.isspace()),
            "CJK font lacks a required glyph")

    # Wrap by measured glyph widths, not character counts; never rewrite quotes.
    def wrapped(text, font, fraction, cjk=False):
        lines = []
        for paragraph in text.split("\n"):
            tokens = list(paragraph) if cjk else paragraph.split(" ")
            line = ""
            for token in tokens:
                candidate = line + ("" if cjk or not line else " ") + token
                pixels = renderer.get_text_width_height_descent(candidate, font, False)[0]
                if pixels > fig.bbox.width * fraction and line:
                    lines.append(line)
                    line = token
                else:
                    line = candidate
            lines.append(line)
        return "\n".join(lines)

    def text(x, y, value, *, font=english, fraction=.294, cjk=False, color="#202020"):
        item = fig.text(x, y, wrapped(value, font, fraction, cjk), va="top",
                        fontproperties=font, color=color, linespacing=1.3)
        fig.canvas.draw()
        return item.get_window_extent(renderer).y0 / fig.bbox.height - .018

    def heading(x, y, value, color="#202020"):
        font = FontProperties(family="DejaVu Sans", weight="bold", size=10)
        return text(x, y, value, font=font, fraction=.96, color=color)

    y = heading(.02, .98, "Question asked after the continuation")
    query = data["examples"][0]
    y = text(.02, y, query["en"]["query"].split("\n\n")[0], fraction=.96)
    y = text(.02, y, query["zh"]["query"].split("\n\n")[0],
             font=chinese, fraction=.96, cjk=True) - .005
    for case in data["examples"]:
        fig.add_artist(Line2D([.02, .98], [y, y], transform=fig.transFigure,
                              color="#bcbcbc", linewidth=.8))
        y = heading(.02, y - .015, f"{case['title']}  |  block {case['block']:02d}")
        left = heading(.02, y, "English answer", "#21698d")
        middle = heading(.353, y, "Chinese answer", "#21698d")
        right = heading(.686, y, "English translation", "#21698d")
        left = text(.02, left, case["en"]["excerpt"])
        middle = text(.353, middle, case["zh"]["excerpt"], font=chinese, cjk=True)
        right = text(.686, right, case["translation_display_excerpt"])
        # Keep the score rows aligned even when the translated column is taller.
        bottom = min(left, middle, right)
        for x, language in ((.02, "en"), (.353, "zh")):
            labels = case[language]["labels"]
            require(labels["openai"] == labels["anthropic"], "Readers disagree; do not merge example scores")
            r = labels["openai"]
            text(x, bottom, "Both readers: inclusive {} | explicit {} | paper {}".format(
                r["inclusive_current_assertion"], r["explicit_current_assertion"], r["paper_positive"]),
                font=FontProperties(family="DejaVu Sans", size=8.5))
        y = bottom - .085
    require(y > 0, f"Example page overflow: {y}")
    return fig


def save_figure(fig, path):
    import matplotlib.pyplot as plt
    from matplotlib.text import Text

    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for item in fig.findobj(Text):
            if not item.get_visible() or not item.get_text():
                continue
            box = item.get_window_extent(renderer)
            require(box.x0 >= 0 and box.y0 >= 0 and box.x1 <= fig.bbox.width
                    and box.y1 <= fig.bbox.height, "Clipped text: " + item.get_text())
        fig.savefig(path, metadata={"CreationDate": None, "ModDate": None,
                                   "Creator": "verify_bilingual_presentation.py"})
    finally:
        plt.close(fig)


def build(out, cjk_font, root=ROOT):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data, inputs = load(root)
    out.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "axes.unicode_minus": True}):
        save_figure(make_contrast_plot(data), out / PDFS[0])
        save_figure(make_examples(data, cjk_font), out / PDFS[1])
    (out / "data.json").write_bytes(json_bytes(data))
    manifest = {"schema": "bilingual_presentation_v1", "source_commit": completed.SOURCE_COMMIT,
                "scope": SCOPE, "inputs": inputs,
                "generator_sha256": sha((root / "scripts/verify_bilingual_presentation.py").read_bytes()),
                "cjk_font": {"name": cjk_font.name, "sha256": sha(cjk_font.read_bytes())},
                "files": {name: sha((out / name).read_bytes()) for name in (*PDFS, "data.json")}}
    (out / "manifest.json").write_bytes(json_bytes(manifest))


def verify(out, root=ROOT):
    data, inputs = load(root)
    manifest = json.loads((out / "manifest.json").read_bytes())
    require(manifest["inputs"] == inputs and manifest["scope"] == SCOPE, "Presentation input/scope changed")
    require(manifest["generator_sha256"] == sha((root / "scripts/verify_bilingual_presentation.py").read_bytes()),
            "Presentation generator changed")
    require(set(manifest["files"]) == {*PDFS, "data.json"}, "Unexpected presentation inventory")
    require((out / "data.json").read_bytes() == json_bytes(data), "Presentation data changed")
    for name, digest in manifest["files"].items():
        require(sha((out / name).read_bytes()) == digest, "Presentation asset changed: " + name)
    prose = ((root / "paper/main.tex").read_text()
             + (root / "paper/model_comparison.tex").read_text())
    for name in PDFS:
        require(f"{{../{PACKAGE}/{name}}}" in prose, "Figure absent from manuscript: " + name)
    require("display-only correction" in prose and "``an attention''" in prose
            and "``attention''" in prose, "Translation correction disclosure omitted")
    return {"pass": True, "contrast_points": len(data["effects"]), "example_pairs": len(data["examples"]),
            "translation_display_edits": sum(len(c["translation_display_edits"]) for c in data["examples"]),
            "new_outcomes": False, "human_translation_validation": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--cjk-font", type=Path)
    args = parser.parse_args()
    out = ROOT / PACKAGE
    if args.write:
        require(args.cjk_font is not None and args.cjk_font.is_file(), "Supply --cjk-font to rebuild")
        build(out, args.cjk_font)
    print(json.dumps(verify(out), sort_keys=True))


if __name__ == "__main__":
    main()
