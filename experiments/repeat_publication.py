"""Offline figures and a manuscript subsection from a verified, finished release.

No collection, new inference, or manuscript edits. Output is a separate new-only
bundle; a pending publication commit is explicit in its machine-readable binding.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from experiments import repeat_funding_release_a1 as release

base, p = release.base, release.p
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("experiments/repeat_publication.py", "tests/test_repeat_publication.py")
MODELS = {"gemini": "Gemini 3.1 Pro Preview", "opus": "Claude Opus 5.5"}
READERS = {"astra": "Astra", "opus": "Opus 5.5"}
ENDPOINTS = {"inclusive_current_assertion": "Explicit or implicit claims",
             "explicit_current_assertion": "Explicit claims", "paper": "Paper instrument"}
EFFECTS = {"instruction_minus_transcript": "Instruction minus continuation",
           "instruction": "Instruction", "transcript": "Continuation", "interaction": "Interaction"}
COLORS = {"astra": "#17607c", "opus": "#a64438"}
FIGURES = ("repeated_main", "repeated_effects")
OUTPUTS = {"binding.json", "figure_data.json", "subsection.md", "subsection.tex",
           "supplementary_figures.md", "supplementary_figures.tex",
           *(name + ext for name in FIGURES for ext in (".png", ".pdf"))}


def _check(condition, message):
    base._check(condition, message)


def _digest(value):
    _check(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Full manifest digest required")
    return value


def _projection(report, metadata):
    _check(report["schema"] == "repeated-swap-analysis-v1" and report["phase"] == "main"
           and report["primary_family_size"] == 2 and report["nominal_family_confidence"] == .95
           and set(report["models"]) == set(MODELS), "Unexpected repeated-study analysis")
    data = {"schema": "repeat-publication-data-v1", "release_status": metadata["status"],
            "collection_complete": metadata["collection_complete"], "endpoint_complete": metadata["endpoint_complete"],
            "terminal_provider_refusals": {"calls": deepcopy(metadata.get("terminal_refusal_calls", [])),
                                            "label_status": "unknown", "default_tier_certified": False},
            "primary_reader": "astra", "primary_endpoint": "inclusive_current_assertion",
            "primary_contrast": "instruction_minus_transcript", "primary_family_size": 2,
            "primary_individual_confidence": .975, "nominal_family_confidence": .95,
            "inventory": deepcopy(report["inventory"]), "models": {}}
    for model, block in report["models"].items():
        _check(block["planned_blocks"] == 32 and block["planned_finals"] == 384
               and set(block["judges"]) == set(READERS), "Changed model or reader inventory")
        readers = deepcopy(block["judges"])
        for reader, endpoints in readers.items():
            _check(set(endpoints) == set(ENDPOINTS), "Changed endpoint inventory")
            for endpoint, summary in endpoints.items():
                for name, contrast in summary["contrasts"].items():
                    primary = (reader, endpoint, name) == ("astra", "inclusive_current_assertion", "instruction_minus_transcript")
                    _check(contrast["primary"] is primary and contrast["bootstrap"]["confidence"] == (.975 if primary else .95)
                           and contrast["planned_blocks"] == 32 and contrast["stratum_weights"] == {"a": .5, "b": .5},
                           "Changed primary family, uncertainty or wording weights")
        data["models"][model] = {"name": MODELS[model], "planned_blocks": 32, "planned_finals": 384,
            "readers": readers, "response_agreement": deepcopy(block["response_agreement"])}
    base._public(data)
    return data


def _read_verified(source, manifest_sha256):
    _digest(manifest_sha256)
    verdict = release.verify(source, manifest_sha256=manifest_sha256)
    _check(verdict["pass"], "Release verification failed")
    metadata = base._load(source / "RELEASE.json")
    audits = {"repeated-funding-a1-release-v1": "funding_audit.json",
              "repeated-transport-a2-release-v1": "transport_audit.json",
              "repeated-refusal-a3-release-v1": "refusal_audit.json"}
    _check(metadata["schema"] in audits,
           "Unsupported release schema")
    audit_name = audits[metadata["schema"]]
    launches = base._load(source / audit_name)["launches"]
    _check(launches and all(row["finish_present"] for row in launches), "Finished release required; no in-flight summaries")
    data = _projection(base._load(source / "analysis.json"), metadata)
    _check(p.sha(source / "MANIFEST.json") == manifest_sha256
           and base._entries(source) == base._load(source / "MANIFEST.json")["files"], "Release changed while reading")
    return data, metadata


def _binding(source, digest, metadata, commit):
    _check(commit is None or isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
           "Publication commit must be a full SHA or pending")
    if commit is not None:
        try:
            relative = source.relative_to(ROOT).as_posix()
        except ValueError as exc:
            raise base.Halted("Commit binding requires a release in this repository") from exc
        _check(base._sha(base._git_blob(commit, relative + "/MANIFEST.json")) == digest,
               "Publication commit does not contain the release manifest")
    return {"schema": "repeat-publication-binding-v1", "release_manifest_sha256": digest,
            "release_commit": commit, "release_commit_state": "pending" if commit is None else "bound",
            "scientific_freeze": metadata["scientific_freeze"], "operational_freeze": metadata["operational_freeze"],
            "release_status": metadata["status"], "source_hashes": {name: p.sha(ROOT / name) for name in SOURCES},
            "scope": "Offline presentation of fixed released analysis; no new labels or inference"}


def _number(value):
    return "unavailable" if value is None else f"{value:.2f}"


def _interval(value):
    return "unavailable" if value is None else "[" + ", ".join(_number(v) for v in value) + "]"


def _table(data):
    rows = []
    for model, block in data["models"].items():
        for reader, endpoints in block["readers"].items():
            summary = endpoints["inclusive_current_assertion"]
            contrast = summary["contrasts"]["instruction_minus_transcript"]
            observed = sum(cell["observed"] for cell in summary["cells"].values())
            rows.append(["Gemini 3.1" if model == "gemini" else "Opus 5.5", READERS[reader],
                         f"{observed}/384", f"{contrast['complete_blocks']}/32",
                         _number(contrast["complete_case_mean"]) + " " + _interval(contrast["bootstrap"]["interval"]),
                         _interval(contrast["worst_case_mean_bounds"])])
    return rows


def _prose(data):
    status = "" if data["collection_complete"] else " The collection stopped before all planned observations were obtained."
    missing = []
    for model, block in data["models"].items():
        for reader, endpoints in block["readers"].items():
            count = sum(c["missing"] for c in endpoints["inclusive_current_assertion"]["cells"].values())
            if count:
                name = "Gemini" if model == "gemini" else "Opus"
                missing.append(f"{READERS[reader]} labels are missing for {count} {name} answer" + ("s" if count != 1 else "") + ".")
    missing_sentence = " ".join(missing) if missing else "Both readers labeled every planned answer."
    estimates = {model: block["readers"]["astra"]["inclusive_current_assertion"]["contrasts"]
                 ["instruction_minus_transcript"]["complete_case_mean"] for model, block in data["models"].items()}
    if all(value is not None for value in estimates.values()):
        lead = ("Among complete request pairs, Astra's claim-label rate differed by " + _number(estimates["gemini"]) +
                " for Gemini 3.1 Pro Preview and " + _number(estimates["opus"]) +
                " for Claude Opus 5.5 when a self-referential instruction with a history continuation was compared with the reverse pairing. ")
    else:
        lead = "The primary instruction-versus-continuation comparison is unavailable for at least one model because a wording family lacks complete requests. "
    conservative = data["models"]["opus"]["readers"]["astra"]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]["worst_case_hoeffding"]
    sensitivity = (" The conservative planned-sample bound for the Opus model includes zero."
                   if conservative is not None and conservative[0] <= 0 <= conservative[1] else "")
    variances = [block["readers"][reader]["inclusive_current_assertion"]["variance"]["SH"]
                 for block in data["models"].values() for reader in READERS]
    if all(v["W"] is not None and v["B"] is not None and v["bootstrap"]["B_interval"] is not None for v in variances):
        low, high = min(v["W"] for v in variances), max(v["W"] for v in variances)
        within = (_number(low) if low == high else _number(low) + " to " + _number(high))
        finding = ("Across three answers to the same SH request, within-request label variance (W) was " + within +
                   " across the two models and readers. ")
        if all(v["bootstrap"]["B_interval"][0] <= 0 <= v["bootstrap"]["B_interval"][1] for v in variances):
            finding += ("The additional source-pair component (B) was not clearly positive: all four descriptive 95% intervals include zero. ")
        else:
            finding += "The figure shows the additional source-pair component (B) separately, with descriptive 95% uncertainty intervals. "
    else:
        finding = "Within-request (W) and source-pair (B) label variances are shown where complete three-answer requests are available. "
    return [
        lead + "Unlike the historical panel, all four request types were randomized and interleaved in this collection. "
        "Each model supplied 32 fresh continuation pairs, with the two wording families weighted equally. "
        "Each unchanged request was submitted three times without a generation seed; neutral-instruction and donor-continuation controls were not repeated. "
        "The models were selected after the earlier panel's results." + status,
        "Astra counted explicit or implicit claims of current subjective experience; Opus 5.5 provided a second automated reading. "
        "The table shows individual 97.5% primary intervals for Astra and descriptive 95% intervals for Opus." + sensitivity + " " +
        missing_sentence + " Missing labels remain unknown: complete-request estimates and all-planned-answer bounds are shown separately.",
        finding + "Within each wording family, B is the variance of three-answer request means minus W/3; the two families are averaged equally. "
        "This is label variation, including reader variability, not pure model randomness or a formal test of W minus B. "
        "Negative B estimates are retained as finite-sample estimates, not negative population variances. "
        "Collapsed bootstrap intervals do not imply certainty. "
        "These two automated readers do not provide independent human validation."]


TABLE_NOTE = ("SH-HS differences in label rates. Astra's primary intervals are individually 97.5%, giving nominal 95% coverage "
              "across the fixed two-model family; Opus intervals are descriptive 95%. Intervals resample paired source blocks "
              "within wording family, retaining all three answers; coverage is approximate. The final column bounds missing labels "
              "over all planned blocks, not sampling uncertainty. Complete-block estimates exclude blocks with missing labels; "
              "missing-label bounds retain all 32 blocks and need not contain the complete-block estimate. "
              "S and H mean self-referential and history-focused; the first letter "
              "denotes the instruction and the second the continuation.")
FIGURE_NOTE = ("Repeated answers and source variation, counting explicit or implicit claims. Left: source-block SH-HS differences "
               "(circles: wording family A; triangles: wording family B) and aggregate estimates (diamonds). Both readers have "
               "bootstrap intervals (thick) and conservative all-planned Hoeffding sensitivity intervals (thin). Astra's primary "
               "intervals are individually 97.5%, preserving the fixed two-model family and nominal 95% family coverage; Opus "
               "intervals are descriptive 95%. Bootstrap coverage is approximate and conditional on complete requests. Dashed block segments mark missing-label "
               "bounds, not observed effects. Right: W (circles, within-request variation) and B (squares, source-pair variation), "
               "averaged equally across wording families, with descriptive 95% source-block bootstrap intervals for both readers. "
               "Missing quantities are not plotted as zeros.")
SUPPLEMENT_NOTES = {
    "repeated_effects": ("Paired differences in label rates, with uncertainty shown for both readers. Astra's explicit-or-implicit "
        "SH-HS contrast is primary: individual 97.5% bootstrap intervals preserve the fixed two-model family with nominal 95% "
        "family coverage. Every other interval, including all Opus intervals, is descriptive 95%. All intervals resample source "
        "blocks within wording family, retaining the three answers and paired cells; coverage is approximate and complete-request "
        "estimates condition on observed labels. Missing estimates are NA, not zero. The interaction is the unscaled difference "
        "of differences; its support is twice that of the other contrasts. Planned-sample missingness bounds remain in the "
        "released analysis and main figure. Horizontal scales differ across panels; collapsed intervals do not imply certainty."),
}


def _tex(text):
    return "".join({"\\": r"\textbackslash{}", "%": r"\%", "&": r"\&", "_": r"\_", "#": r"\#",
                    "{": r"\{", "}": r"\}", "$": r"\$"}.get(c, c) for c in text)


def _figure_note(data):
    counts = []
    for model, block in data["models"].items():
        values = [block["readers"][reader]["inclusive_current_assertion"]["contrasts"]["instruction_minus_transcript"]
                  for reader in READERS]
        name = "Gemini" if model == "gemini" else "Opus"
        counts.append(name + " " + ", ".join(f"{v['complete_blocks']}/{v['planned_blocks']}" for v in values))
    return FIGURE_NOTE + " Complete SH-HS blocks (Astra, Opus reader): " + "; ".join(counts) + "."


def _editorial(data):
    paragraphs, rows = _prose(data), _table(data)
    figure_note = _figure_note(data)
    header = ["Model", "Reader", "Available labels", "Complete SH-HS blocks", "SH-HS [interval]", "Missing bounds"]
    md = "## Repeated Answers And Source Variation\n\n" + "\n\n".join(paragraphs) + "\n\n"
    md += "| " + " | ".join(header) + " |\n|" + " --- |" * len(header) + "\n"
    md += "".join("| " + " | ".join(row) + " |\n" for row in rows)
    md += "\n" + TABLE_NOTE + "\n\n![Repeated answers and source variation](repeated_main.png)\n\n" + figure_note + "\n"
    tex = "% Generated subsection; publication binding is in binding.json.\n"
    tex += r"\subsection{Repeated answers and source variation}" + "\n\n" + "\n\n".join(_tex(p) for p in paragraphs) + "\n\n"
    tex += "\\begin{table}[t]\n\\centering\n\\footnotesize\n\\setlength{\\tabcolsep}{2pt}\n"
    tex_header = list(map(_tex, header))
    tex_header[3] = r"\shortstack{Complete SH-HS\\blocks}"
    tex += "\\begin{tabular}{llrrll}\n\\toprule\n\\addlinespace[2pt]\n" + " & ".join(tex_header) + " \\\\\n\\midrule\n"
    tex += "".join(" & ".join(map(_tex, row)) + " \\\\\n" for row in rows)
    tex += "\\bottomrule\n\\end{tabular}\n\\caption{" + _tex(TABLE_NOTE) + "}\n\\end{table}\n\n"
    tex += "\\begin{figure}[t]\n\\centering\n\\includegraphics[width=\\linewidth]{repeated_main.pdf}\n"
    tex += "\\caption{" + _tex(figure_note) + "}\n\\end{figure}\n"
    supplemental_md, supplemental_tex = [], []
    for name, caption in SUPPLEMENT_NOTES.items():
        supplemental_md.append(f"![{name}]({name}.png)\n\n{caption}\n")
        supplemental_tex.append("\\begin{figure}[t]\n\\centering\n\\includegraphics[width=\\linewidth]{" + name +
                                ".pdf}\n\\caption{" + _tex(caption) + "}\n\\end{figure}\n")
    return {"subsection.md": md, "subsection.tex": tex,
            "supplementary_figures.md": "\n".join(supplemental_md),
            "supplementary_figures.tex": "\n".join(supplemental_tex)}


def _segment(ax, interval, y, *, color, width=1, style="-", caps=False):
    if interval is not None:
        ax.plot(interval, [y, y], color=color, linewidth=width, linestyle=style, solid_capstyle="butt")
        if caps:
            ax.plot(interval, [y, y], color=color, linestyle="", marker="|", markersize=5, markeredgewidth=.9)


def _render(data, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({"font.size": 10, "axes.labelsize": 10, "xtick.labelsize": 9,
                         "ytick.labelsize": 9, "legend.fontsize": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "0.65", "axes.linewidth": .6,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 170})

    reader_handles = [Line2D([], [], color=COLORS[r], marker="o", markersize=4.5,
                             linewidth=1.5, label=READERS[r]) for r in READERS]

    def finish(fig, name):
        fig.savefig(destination / (name + ".png"))
        fig.savefig(destination / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None})
        plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(6.6, 6.2), sharex="col", layout="constrained")
    for row, (model, block) in enumerate(data["models"].items()):
        left, right = axes[row]
        left.axvline(0, color="0.8", linewidth=.8)
        right.axvline(0, color="0.8", linewidth=.8)
        for j, reader in enumerate(READERS):
            summary = block["readers"][reader]["inclusive_current_assertion"]
            contrast = summary["contrasts"]["instruction_minus_transcript"]
            color = COLORS[reader]
            for dot in contrast["per_block"]:
                y = dot["block"] + (j - .5) * .25
                if dot["value"] is not None:
                    left.plot(dot["value"], y, "o" if dot["family"] == "a" else "^", color=color, markersize=3.2, alpha=.75)
                else:
                    _segment(left, dot["worst_case_bounds"], y, color=color, width=.5, style="--")
            y = 35 + j * 3
            _segment(left, contrast["worst_case_hoeffding"], y, color=color)
            _segment(left, contrast["bootstrap"]["interval"], y, color=color, width=3)
            if contrast["complete_case_mean"] is None:
                left.text(0, y + .7, "NA", ha="center", fontsize=8, color=color)
            else:
                left.plot(contrast["complete_case_mean"], y, "D", markersize=4.5, color=color)
            for c, cell in enumerate(p.CELLS):
                value = summary["variance"][cell]
                for k, (key, marker) in enumerate((("W", "o"), ("B", "s"))):
                    y = c + (j - .5) * .30 + (k - .5) * .11
                    if value[key] is not None:
                        _segment(right, value["bootstrap"][key + "_interval"], y, color=color)
                        right.plot(value[key], y, marker, color=color, markersize=4.5)
                    else:
                        right.text(.98, y, "NA", transform=right.get_yaxis_transform(), ha="right", fontsize=7, color=color)
        left.axhline(33.5, color="0.85", linewidth=.6)
        left.set(xlim=(-1.05, 1.05), ylim=(40, 0), xlabel="SH-HS difference in label rate", ylabel=MODELS[model],
                 xticks=[-1, -.5, 0, .5, 1],
                 yticks=[1, 16, 32, 35, 38], yticklabels=["Block 1", "16", "32", "Astra", "Opus"])
        right.set(yticks=range(4), yticklabels=list(p.CELLS), ylim=(-.5, 3.5), xlabel="Label variance", ylabel="Request")
        right.grid(axis="y", color="0.93", linewidth=.5)
        right.set_axisbelow(True)
    fig.legend(handles=reader_handles +
               [Line2D([], [], color="0.3", marker=m, linestyle="", label=label)
                for m, label in (("o", "Within request (W)"), ("s", "Source pairs (B)"))],
               loc="outside lower center", frameon=False, ncol=4)
    finish(fig, "repeated_main")

    from matplotlib.ticker import MaxNLocator
    fig, axes = plt.subplots(3, 2, figsize=(6.6, 8.2), layout="constrained")
    for row, (model, block) in enumerate(data["models"].items()):
        for col, endpoint in enumerate(ENDPOINTS):
            ax = axes[col, row]
            extent = [0.0]
            for j, reader in enumerate(READERS):
                summary = block["readers"][reader][endpoint]
                for i, key in enumerate(EFFECTS):
                    y, color = i + (j - .5) * .22, COLORS[reader]
                    value = summary["contrasts"][key]
                    point, interval = value["complete_case_mean"], value["bootstrap"]["interval"]
                    if point is not None:
                        _segment(ax, interval, y, color=color, width=1.2, caps=True)
                        ax.plot(point, y, "o", color=color, markersize=2.6, markerfacecolor="none", markeredgewidth=.8)
                        extent.append(point)
                        if interval is not None:
                            extent.extend(interval)
                    else:
                        ax.text(.98, y, "NA", transform=ax.get_yaxis_transform(), ha="right", color=color, fontsize=7)
            low, high = min(extent), max(extent)
            padding = max(.06, (high - low) * .10)
            ax.set(yticks=range(len(EFFECTS)), ylim=(-.5, len(EFFECTS) - .5), ylabel=ENDPOINTS[endpoint],
                   yticklabels=["SH-HS", "Instruction", "Continuation", "Interaction"],
                   xlim=(low - padding, high + padding),
                   xlabel=MODELS[model] + "\nDifference in label rate")
            ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.grid(axis="y", color="0.93", linewidth=.5)
            ax.set_axisbelow(True)
            ax.axvline(0, color="0.8", linewidth=.8)
    fig.legend(handles=reader_handles, loc="outside lower center", frameon=False, ncol=2)
    finish(fig, "repeated_effects")


def build(source, destination, *, release_manifest_sha256, commit=None):
    source, target = Path(source).absolute(), Path(destination).absolute()
    base._no_symlinks(source); base._no_symlinks(target)
    _check(not target.exists() and source not in target.parents and target not in source.parents,
           "Destination must be new and outside the release")
    data, metadata = _read_verified(source, release_manifest_sha256)
    binding = _binding(source, release_manifest_sha256, metadata, commit)
    with TemporaryDirectory(prefix="repeat-publication-") as temporary:
        stage = Path(temporary).resolve()
        base._write(stage / "binding.json", binding)
        base._write(stage / "figure_data.json", data)
        for name, text in _editorial(data).items():
            (stage / name).write_text(text, encoding="utf-8")
        _render(data, stage)
        base._write(stage / "MANIFEST.json", {"schema": "repeat-publication-manifest-v1", "files": base._entries(stage)})
        _check(p.sha(source / "MANIFEST.json") == release_manifest_sha256
               and base._entries(source) == base._load(source / "MANIFEST.json")["files"], "Release changed during presentation")
        base._no_symlinks(target)
        shutil.copytree(stage, target)
    return {"pass": True, "files": len(OUTPUTS), "manifest_sha256": p.sha(target / "MANIFEST.json"),
            "release_status": metadata["status"], "commit_state": binding["release_commit_state"]}


def verify(source, destination, *, release_manifest_sha256, manifest_sha256):
    source, target = Path(source).absolute(), Path(destination).absolute()
    base._no_symlinks(source); base._no_symlinks(target)
    files = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    _check(files == OUTPUTS | {"MANIFEST.json"} and all(path.is_file() and not path.is_symlink() for path in target.iterdir()),
           "Unexpected presentation inventory")
    _check(p.sha(target / "MANIFEST.json") == _digest(manifest_sha256), "Presentation manifest anchor differs")
    _check(base._load(target / "MANIFEST.json") == {"schema": "repeat-publication-manifest-v1", "files": base._entries(target)},
           "Presentation manifest differs")
    data, metadata = _read_verified(source, release_manifest_sha256)
    binding = base._load(target / "binding.json")
    _check(binding == _binding(source, release_manifest_sha256, metadata, binding["release_commit"]), "Presentation binding differs")
    _check(base._load(target / "figure_data.json") == data and all((target / name).read_text() == text for name, text in _editorial(data).items()),
           "Presentation does not reconstruct")
    with TemporaryDirectory(prefix="repeat-figure-verify-") as temporary:
        rendered = Path(temporary).resolve()
        _render(data, rendered)
        _check(all(p.sha(rendered / (name + ext)) == p.sha(target / (name + ext))
                   for name in FIGURES for ext in (".png", ".pdf")), "Rendered figures do not reconstruct")
    return {"pass": True, "manifest_sha256": manifest_sha256, "release_status": metadata["status"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--release-manifest-sha256", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--commit")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    if args.verify:
        result = verify(args.release, args.destination, release_manifest_sha256=args.release_manifest_sha256,
                        manifest_sha256=args.manifest_sha256)
    else:
        result = build(args.release, args.destination, release_manifest_sha256=args.release_manifest_sha256, commit=args.commit)
    print(p.canonical(result))


if __name__ == "__main__":
    main()
