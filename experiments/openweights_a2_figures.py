"""Offline, additive figures from a verified A2 release; no scientific reanalysis."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import analysis as schema
from experiments.openrouter_swap.ledger import Halted, _no_symlinks
from experiments.openrouter_swap.release import _load
from experiments.openrouter_swap_openweights_a2 import release as a2_release

TITLE = "Open-weight A2 continuation: model-judge labels"
MODELS = ("qwen", "mistral")
MODEL_NAMES = {"qwen": "Qwen", "mistral": "Mistral"}
ENDPOINT_NAMES = {"inclusive_current_assertion": "inclusive", "explicit_current_assertion": "explicit", "paper": "paper"}
CONTRAST_NAMES = {"instruction_minus_transcript": "SH-HS", "neutral_transcript": "NS-NH"}
METHOD = "Bonferroni bounded Hoeffding"
SCOPE = ("Same four-comparison open-weight family across A1 and A2; no pooling with earlier studies. "
         "Model-judge labels are not ground truth. Architecture comparisons are observational.")
INTERVAL_NOTE = ("Main only: saved 95% familywise Bonferroni-Hoeffding bounds for planned blocks, "
                 "including worst-case missing labels. Dots are complete-case means, not bound midpoints.")


def _check(condition, message):
    if not condition:
        raise Halted(message)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _state(metadata, qualification, model, phase, result):
    # Verified admission reconstructs a completed screen prefix even when a
    # later main failure makes the frozen whole-journal completion flag false.
    screen_decided = metadata["collection_complete"]["screen"] or bool(metadata["admitted_models"])
    if phase == "main" and model not in metadata["admitted_models"]:
        if not screen_decided:
            return "unrun: screening incomplete"
        if not qualification["models"][model]["qualified"]:
            return "unrun: screen not qualified"
        return "unrun: not admitted"
    if not any(r["status"] != "not_generated" for r in result["classifications"]):
        if phase == "main" and metadata["main_status"] == "not_run":
            return "unrun: admitted, not started"
        return "no observed finals"
    if phase == "screen" and screen_decided and not qualification["models"][model]["qualified"]:
        return "screen not qualified"
    if phase == "screen" and screen_decided and not metadata["collection_complete"]["screen"]:
        return "screen completed before main"
    return "complete collection" if metadata["collection_complete"][phase] else "partial collection"


def _tables(metadata, reports, qualification):
    _check(metadata["schema"] == "openweights-a2-release-v1"
           and type(metadata["primary_family_size"]) is int and metadata["primary_family_size"] == 4
           and metadata["status"] in {"complete", "incomplete"} and metadata["fixtures_pass"] is True,
           "Only a verified four-comparison A2 release is supported")
    _check(set(metadata["collection_complete"]) == {"screen", "main"}
           and all(type(v) is bool for v in metadata["collection_complete"].values())
           and metadata["main_status"] in {"not_run", "incomplete", "completed"}
           and isinstance(metadata["admitted_models"], list)
           and len(set(metadata["admitted_models"])) == len(metadata["admitted_models"])
           and set(metadata["admitted_models"]) <= set(MODELS)
           and set(qualification["models"]) == set(MODELS)
           and all(type(q["qualified"]) is bool for q in qualification["models"].values()),
           "Collection or qualification state differs")
    rates, contrasts, states = [], [], []
    for phase, cells, planned in (("screen", schema.SCREEN_CELLS, 12), ("main", schema.MAIN_CELLS, 32)):
        report, family = reports[phase], reports[phase]["primary_family"]
        _check(report["phase"] == phase and report["planned_blocks_per_model"] == planned
               and report["sampling_unit"] == "paired_block" and set(report["models"]) == set(MODELS)
               and type(family["fixed_family_size"]) is int and family["fixed_family_size"] == 4
               and family["judge"] == "astra" and family["endpoint"] == "inclusive_current_assertion"
               and family["contrasts"] == list(schema.PRIMARY_CONTRASTS)
               and family["study"] == "openweights_extension_only"
               and family["planned_models"] == list(MODELS)
               and family["familywise_confidence"] == .95 and family["method"] == METHOD,
               "Analysis identity or fixed family differs")
        for model in MODELS:
            result = report["models"][model]
            state = _state(metadata, qualification, model, phase, result)
            states.append({"phase": phase, "model": model, "state": state})
            _check(set(result["judges"]) == set(schema.JUDGES), "Judge inventory differs")
            for judge in schema.JUDGES:
                _check(set(result["judges"][judge]) == set(schema.ENDPOINTS), "Rubric inventory differs")
                for endpoint in schema.ENDPOINTS:
                    summaries = result["judges"][judge][endpoint]["cells"]
                    _check(set(summaries) == set(cells), "Cell inventory differs")
                    for cell in cells:
                        s = summaries[cell]
                        _check(all(type(s[k]) is int and s[k] >= 0 for k in ("planned", "observed", "positive", "negative", "missing"))
                               and s["planned"] == planned and s["observed"] + s["missing"] == planned
                               and s["positive"] + s["negative"] == s["observed"]
                               and ((s["observed"] == 0 and s["proportion"] is None)
                                    or (s["observed"] > 0 and _finite(s["proportion"], 0, 1)
                                        and math.isclose(s["proportion"], s["positive"] / s["observed"], abs_tol=1e-12))),
                               "Saved cell counts or rate are inconsistent")
                        _check(not state.startswith("unrun") or s["observed"] == 0, "Unrun main cannot supply labels")
                        rates.append({"phase": phase, "model": model, "judge": judge, "endpoint": endpoint,
                                      "cell": cell, "state": state, **{k: s[k] for k in (
                                          "planned", "observed", "positive", "negative", "missing", "proportion")}})
            if phase != "main":
                continue
            primary = result["judges"]["astra"]["inclusive_current_assertion"]
            for name in schema.PRIMARY_CONTRASTS:
                c = primary["contrasts"][name]
                n, missing, mean = c["complete_blocks"], c["missing_blocks"], c["complete_case_mean"]
                interval = c["familywise_hoeffding_95"]
                _check(type(n) is int and type(missing) is int and min(n, missing) >= 0
                       and type(c["planned_blocks"]) is int and c["planned_blocks"] == 32 and n + missing == 32
                       and ((n == 0 and mean is None) or (n > 0 and _finite(mean, -1, 1)))
                       and isinstance(interval, list) and len(interval) == 2
                       and all(_finite(v, -1, 1) for v in interval) and interval[0] <= interval[1],
                       "Saved primary interval or denominator is inconsistent")
                counts = [primary["cells"][cell]["observed"] for cell in schema.CONTRASTS[name]]
                _check(n <= min(counts), "Complete pairs exceed observed labels")
                visible = any(counts) and not state.startswith("unrun")
                contrasts.append({"phase": "main", "model": model, "judge": "astra",
                    "endpoint": "inclusive_current_assertion", "contrast": CONTRAST_NAMES[name],
                    "state": state if visible or state.startswith("unrun") else "no primary labels",
                    "planned_blocks": 32, "complete_blocks": n, "missing_blocks": missing,
                    "complete_case_mean": mean if visible else None,
                    "saved_familywise_hoeffding_95": list(interval),
                    "interval_low": interval[0] if visible else None, "interval_high": interval[1] if visible else None,
                    "interval_method": METHOD, "family_size": 4})
    return {"rates": rates, "contrasts": contrasts, "states": states}


def _write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _markdown(data):
    lines = ["# " + TITLE, "", "Verified release status: " + data["release_status"] + ".", "",
             data["completion_flag_note"], "",
             "Screening is descriptive. Held-out main uses fresh blocks; screening is not pooled into main.", "",
             INTERVAL_NOTE, "", "| Model | Main contrast | Complete/planned | Missing | Mean | Familywise 95% interval | State |",
             "|---|---|---:|---:|---:|---|---|"]
    for row in data["contrasts"]:
        mean = "Not estimated" if row["complete_case_mean"] is None else f"{row['complete_case_mean']:.3f}"
        bound = "Not displayed" if row["interval_low"] is None else f"[{row['interval_low']:.3f}, {row['interval_high']:.3f}]"
        lines.append(f"| {MODEL_NAMES[row['model']]} | {row['contrast']} | {row['complete_blocks']}/32 | "
                     f"{row['missing_blocks']} | {mean} | {bound} | {row['state']} |")
    lines.extend(["", "Null JSON estimates, blank CSV estimates, and unrun/no-label panels are not zero effects. "
                  "Figure data retains the saved worst-case bounds even when no bar is displayed. "
                  "A genuine observed 0% is shown only with a nonzero observed-label denominator.", "",
                  "Astra inclusive is primary; Opus inclusive is robustness. Explicit and paper rubrics are secondary. "
                  "The two judge services are not independent sampling units.", "",
                  "A2 continues the same A1 inventory. Original calls, capped/missing outputs, and the initial failed release "
                  "remain preserved. Fixture evidence is inherited from the verified A1 journal prefix; no new fixtures.", "",
                  SCOPE, "", "Release manifest SHA-256: `" + data["release_manifest_sha256"] + "`.", "",
                  "Presentation only: no new labels, model selection, intervals, or scientific-rule changes.", ""])
    return "\n".join(lines)


def _render(data, out):
    import matplotlib as mpl
    import numpy as np
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    row_keys = [(m, j, e) for m in MODELS for j in schema.JUDGES for e in schema.ENDPOINTS]
    row_names = [f"{MODEL_NAMES[m]} | {j.title()} {ENDPOINT_NAMES[e]}" for m, j, e in row_keys]
    states = {(r["phase"], r["model"]): r["state"] for r in data["states"]}
    styles = {"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
              "axes.spines.right": False, "savefig.facecolor": "white"}

    def save(fig, name):
        for suffix in ("png", "pdf"):
            fig.savefig(out / (name + "." + suffix))

    with mpl.rc_context(styles):
        fig = Figure(figsize=(15.8, 9.2), dpi=180); FigureCanvasAgg(fig)
        axes = fig.subplots(1, 2, gridspec_kw={"width_ratios": [4, 8]})
        fig.subplots_adjust(left=.17, right=.97, bottom=.23, top=.85, wspace=.13)
        cmap = mpl.colormaps["cividis"].copy(); cmap.set_bad("#eeeeee")
        image = None
        for ax, phase, cells, planned in zip(axes, ("screen", "main"), (schema.SCREEN_CELLS, schema.MAIN_CELLS), (12, 32)):
            records = {(r["model"], r["judge"], r["endpoint"], r["cell"]): r for r in data["rates"] if r["phase"] == phase}
            ax.set_title(("Screening (descriptive)" if phase == "screen" else "Held-out main")
                         + f": {planned} paired blocks/model", loc="left", fontsize=11, pad=16)
            if not any(r["observed"] for r in records.values()):
                ax.set_axis_off()
                ax.text(.5, .55, "No observed final labels", ha="center", va="center", transform=ax.transAxes,
                        fontsize=13, weight="bold", color="#353535")
                message = "\n".join(f"{MODEL_NAMES[m]}: {states[phase, m]}" for m in MODELS)
                ax.text(.5, .40, message + "\nNo rates estimated.", ha="center", va="center",
                        transform=ax.transAxes, fontsize=9, linespacing=1.7)
                continue
            values = np.array([[records[key + (cell,)]["proportion"] if records[key + (cell,)]["proportion"] is not None
                                else np.nan for cell in cells] for key in row_keys])
            image = ax.imshow(np.ma.masked_invalid(values), vmin=0, vmax=1, cmap=cmap, aspect="auto")
            ax.set(xticks=range(len(cells)), xticklabels=cells, yticks=range(len(row_keys)),
                   yticklabels=row_names if phase == "screen" or not axes[0].axison else [])
            ax.tick_params(axis="both", length=0, pad=7, labelsize=8.5)
            ax.axhline(5.5, color="white", linewidth=3)
            for y, key in enumerate(row_keys):
                for x, cell in enumerate(cells):
                    row, color = records[key + (cell,)], "#555555"
                    rate = row["proportion"]
                    if rate is None:
                        label = "UNRUN" if row["state"].startswith("unrun") else "NO LABEL"
                        text = f"{label}\nobs 0/{planned}\nmissing {row['missing']}"
                    else:
                        text = f"{rate:.0%}\n{row['positive']}/{row['observed']}\nmissing {row['missing']}"
                        red, green, blue, _ = cmap(rate)
                        color = "white" if .2126*red + .7152*green + .0722*blue < .48 else "#151515"
                    ax.text(x, y, text, ha="center", va="center", fontsize=7.3, color=color, linespacing=1.25)
        fig.suptitle(data["title"] + " | cell rates", x=.17, ha="left", y=.975, fontsize=14, weight="bold")
        fig.text(.17, .923, f"Release: {data['release_status']}. Inclusive/explicit: structured instrument. Paper: paper rubric.\n"
                 "Cells show observed-label rate, positive/observed labels, and missing labels. Judges are not independent replicates.",
                 fontsize=9, linespacing=1.6)
        if image is not None:
            bar = fig.colorbar(image, cax=fig.add_axes((.78, .157, .19, .017)), orientation="horizontal")
            bar.set_label("Observed-label proportion", fontsize=8, labelpad=3); bar.ax.tick_params(labelsize=8)
        phase_states = "\n".join(phase.title() + ": " + "; ".join(f"{MODEL_NAMES[m]} {states[phase, m]}" for m in MODELS)
                                 for phase in ("screen", "main"))
        fig.text(.17, .165, "Planned denominator per cell: screen 12; main 32.\n"
                 "Technical fixtures: verified A1 prefix; none repeated in A2.\n" + phase_states,
                 va="top", fontsize=8, linespacing=1.6)
        fig.text(.17, .055, "Astra inclusive: primary. Opus inclusive: robustness. Explicit and paper: secondary.", fontsize=8)
        fig.text(.17, .025, SCOPE, fontsize=8)
        save(fig, "cell_rates")

        fig = Figure(figsize=(12.2, 5.7), dpi=180); FigureCanvasAgg(fig)
        ax = fig.subplots(); fig.subplots_adjust(left=.18, right=.72, top=.76, bottom=.29)
        ax.axvline(0, color="#999999", linestyle="--", linewidth=.8)
        colors = {"qwen": "#166c80", "mistral": "#a04440"}
        for y, row in enumerate(data["contrasts"]):
            if row["interval_low"] is not None:
                bounds = [row["interval_low"], row["interval_high"]]
                ax.plot(bounds, [y, y], color=colors[row["model"]], linewidth=2)
                ax.plot(bounds, [y, y], "|", color=colors[row["model"]], markersize=9)
                if row["complete_case_mean"] is not None:
                    ax.plot(row["complete_case_mean"], y, "o", color=colors[row["model"]], markersize=5)
                label = f"{row['complete_blocks']}/32 complete; {row['missing_blocks']} missing"
            else:
                label = row["state"] + f"\n0/32 complete; {row['missing_blocks']} missing"
            ax.text(1.035, y, label, transform=ax.get_yaxis_transform(), va="center", fontsize=8.5)
        ax.set(xlim=(-1.05, 1.05), ylim=(3.6, -.6), yticks=range(4),
               yticklabels=[f"{MODEL_NAMES[r['model']]}  {r['contrast']}" for r in data["contrasts"]],
               xlabel="Difference in label probability", xticks=(-1, -.5, 0, .5, 1))
        ax.tick_params(axis="y", length=0, pad=10)
        fig.suptitle(data["title"] + " | primary main contrasts", x=.18, ha="left", y=.96, fontsize=12, weight="bold")
        fig.text(.18, .84, "Astra inclusive current attribution | fixed family of four | held-out main only\n"
                 f"Release: {data['release_status']}. Screening is not main evidence.", fontsize=9, linespacing=1.6)
        fig.text(.18, .13, "Bars: saved 95% familywise Bonferroni-Hoeffding bounds with worst-case missing labels.\n"
                 "Dots: complete-case means. No bar or dot for unrun/no-label outcomes; no dot without complete pairs.",
                 fontsize=8, linespacing=1.6)
        fig.text(.02, .03, SCOPE, fontsize=8)
        save(fig, "primary_contrasts")


def build(release_dir, destination):
    """Verify a detached snapshot using the unchanged A2 verifier before display."""
    source, target = Path(release_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source); _no_symlinks(target)
    _check(not target.exists() and source != target and source not in target.parents and target not in source.parents,
           "Output must be a new directory outside the release")
    _check((source / "MANIFEST.json").is_file() and (source / "RELEASE.json").is_file(), "A public A2 release is required")
    with TemporaryDirectory(prefix="openweights-a2-figures-") as temporary:
        work = Path(temporary).resolve(); snapshot = work / "release"
        # Preserve links so verification rejects them, rather than copying private targets.
        shutil.copytree(source, snapshot, symlinks=True)
        verified = a2_release.verify(snapshot)
        _check(isinstance(verified, dict) and verified.get("pass") is True, "Public A2 release verification did not pass")
        metadata = _load(snapshot / "RELEASE.json")
        reports = {phase: _load(snapshot / (phase + "_analysis.json")) for phase in ("screen", "main")}
        view = _tables(metadata, reports, _load(snapshot / "qualification.json"))
        data = {"schema": "openweights-a2-figure-data-v1", "title": TITLE,
                "release_manifest_sha256": _sha(snapshot / "MANIFEST.json"), "release_sha256": _sha(snapshot / "RELEASE.json"),
                "freeze": metadata["freeze"], "plan_sha256": metadata["plan_sha256"], "release_status": metadata["status"],
                "collection_complete": metadata["collection_complete"], "main_status": metadata["main_status"],
                "completion_flag_note": ("The frozen screening-completion flag is false because its check requires "
                    "the entire journal to be settled. Verified main admission reconstructs the completed screening "
                    "prefix; later main failures do not revoke that screening decision. Original flags remain unchanged."
                    if not metadata["collection_complete"]["screen"] and metadata["admitted_models"] else ""),
                "failure_evidence": metadata["failure_evidence"], "fixture_evidence": metadata["fixture_evidence"],
                "release_verified": True, "source_sha256": _sha(Path(__file__)), "primary_family_size": 4,
                "interval_note": INTERVAL_NOTE, "scope": SCOPE, **view}
        out = work / "figures"; out.mkdir()
        _write(out / "figure_data.json", data)
        _csv(out / "cell_rates.csv", data["rates"]); _csv(out / "primary_contrasts.csv", data["contrasts"])
        (out / "README.md").write_text(_markdown(data), encoding="utf-8")
        _render(data, out)
        result = {k: v for k, v in data.items() if k not in {"rates", "contrasts", "states"}}
        result.update(schema="openweights-a2-figures-v1", files=[
            {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)} for path in sorted(out.iterdir())])
        _write(out / "FIGURES.json", result)
        _no_symlinks(target)
        shutil.copytree(out, target)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True); parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = build(args.release, args.out)
    except (Halted, ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
        parser.exit(1, "A2 figure adapter failed closed; release retained unchanged.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
