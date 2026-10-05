#!/usr/bin/env python3
"""Offline row-to-manuscript binding for the completed Gemini/Opus extension.

Default/--check is read-only and needs only the standard library. --write
regenerates this editorial package and its figure, never a scientific release.
The optional --source-release imports selected, byte-identical public inputs
after checking their local Git objects at SOURCE_COMMIT. No network is used.
The original release verifier separately reconstructs judgments from receipts;
this check recomputes counts and bounded intervals from its released row labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/openrouter_swap_extension"
SOURCE_COMMIT = "0438e6c12e6024da7e4284ec6c396e27c6c1738a"
FREEZE = "1177d0862fe5ea381fd0e75c39072469ec83cdfc"
RELEASE = "data/openrouter_swap/main_v1_20261004"
MANIFEST_SHA = "bf77334c21a94d356628475a1f9cb62d52e13f0293db95d4d710f3a0ffb09377"
INPUTS = {
    "plan": "PLAN.json", "release": "RELEASE.json",
    "main_rows": "snapshots/003611/main_rows.json",
    "screen_rows": "snapshots/003611/screen_rows.json",
    "analysis": "snapshots/003611/main_analysis.json",
    "qualification": "snapshots/003611/qualification.json",
}
INCLUSIVE = "inclusive_current_assertion"
EXPLICIT = "explicit_current_assertion"
ENDPOINTS = (INCLUSIVE, EXPLICIT, "paper")
JUDGES = ("astra", "opus")
MODELS = ("gemini", "opus")
SCREEN_MODELS = ("gemini", "opus", "sonnet")
CELLS = ("SS", "SH", "HS", "HH", "NS", "NH", "S_SHAM", "H_SHAM")
CONTRASTS = {
    "instruction_minus_transcript": {"SH": 1, "HS": -1},
    "neutral_transcript": {"NS": 1, "NH": -1},
    "instruction": {"SS": .5, "SH": .5, "HS": -.5, "HH": -.5},
    "transcript": {"SS": .5, "HS": .5, "SH": -.5, "HH": -.5},
    "self_sham": {"S_SHAM": 1, "SS": -1},
    "history_sham": {"H_SHAM": 1, "HH": -1},
}
PRIMARY = ("instruction_minus_transcript", "neutral_transcript")
FIGURE = "paper/figures/openrouter_swap_extension_measurement"
OWN = ("scripts/verify_openrouter_swap_extension.py",
       "tests/test_openrouter_swap_extension.py", "paper/openrouter_swap_extension.tex")
DERIVED = ("results.json", "values.tex", "figure_data.json")
SCOPE = {
    "editorial_binding_only": True, "authorizes_collection": False,
    "row_counts_and_block_contrasts_recomputed": True,
    "primary_bonferroni_hoeffding_intervals_recomputed": True,
    "original_analysis_selected_values_crosschecked": True,
    "raw_api_receipts_reaudited_by_this_command": False,
    "bootstrap_intervals_recomputed": False, "human_validation": False,
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "Duplicate JSON key")
            value[key] = item
        return value

    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def local(root, name):
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and ".." not in rel.parts and rel.as_posix() == name,
            "Unsafe relative path")
    target = Path(root)
    require(not target.is_symlink(), "Symlink root")
    for part in rel.parts:
        target /= part
        require(not target.is_symlink(), "Symlink path")
    return target


def source_entries(raw):
    require(sha(raw) == MANIFEST_SHA, "Release manifest pin changed")
    rows = decode(raw)["files"]
    result = {r["path"]: r for r in rows}
    require(len(result) == len(rows), "Duplicate release path")
    return result


def load_sources(root=ROOT):
    base = PACKAGE + "/inputs/"
    entries = source_entries(local(root, base + "source_inventory.json").read_bytes())
    values, provenance = {}, {}
    for key, name in INPUTS.items():
        raw = gzip.decompress(local(root, base + key + ".json.gz").read_bytes())
        entry = entries[name]
        require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"],
                "Source hash/size changed: " + key)
        values[key] = decode(raw)
        provenance[key] = {"release_path": name, "sha256": sha(raw), "bytes": len(raw)}
    require(values["release"]["freeze"] == FREEZE, "Scientific freeze changed")
    require(values["release"]["plan_sha256"] == provenance["plan"]["sha256"], "Plan pin changed")
    return values, provenance


def import_sources(source_release, root=ROOT):
    source_release = Path(source_release).resolve()
    repo = source_release.parents[2]
    require(source_release == repo / RELEASE, "Unexpected source release path")
    files = {"source_inventory.json": "MANIFEST.json",
             **{key + ".json.gz": name for key, name in INPUTS.items()}}
    imported = {}
    for dest, name in files.items():
        raw = local(source_release, name).read_bytes()
        pinned = subprocess.run(["git", "show", SOURCE_COMMIT + ":" + RELEASE + "/" + name],
                                cwd=repo, check=True, capture_output=True).stdout
        require(raw == pinned, "Source differs from pinned Git object: " + name)
        imported[dest] = raw
    entries = source_entries(imported["source_inventory.json"])
    for dest, name in files.items():
        if name != "MANIFEST.json":
            require(sha(imported[dest]) == entries[name]["sha256"], "Imported source hash changed")
    for dest, raw in imported.items():
        target = local(root, PACKAGE + "/inputs/" + dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.compress(raw, mtime=0) if dest.endswith(".gz") else raw)


def close(actual, expected):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12),
            "Released analysis disagrees with rows")


def observed(row, judge, endpoint):
    require(row["status"] == "ok" and isinstance(row["response"], str)
            and row["response"].strip(), "Missing/unsuccessful response; never recode as denial")
    payload = row["labels"][judge]
    require(payload["structured"]["refusal"] is False,
            "Refusal is missing, not a negative label")
    value = payload["paper"] if endpoint == "paper" else payload["structured"][endpoint]
    require(type(value) is bool, "Missing/nonboolean endpoint")
    return int(value)


def inventory(rows, plan, phase, models, n, cells):
    planned = {r["id"]: r for b in plan[phase] if b["model"] in models for r in b["finals"]}
    require(len(rows) == len(planned) == len(models) * n * len(cells), "Incomplete row inventory")
    require(len({r["id"] for r in rows}) == len(rows), "Duplicate row ID")
    grouped = {model: {} for model in models}
    for row in rows:
        require(row["id"] in planned, "Unplanned row")
        spec = planned[row["id"]]
        require(all(row.get(k) == v for k, v in spec.items()), "Row differs from planned block/cell/donor")
        require(row["phase"] == phase and row["cell"] in cells, "Wrong phase or cell")
        block = grouped[row["model"]].setdefault(row["block"], {})
        require(row["cell"] not in block, "Duplicate block/cell")
        block[row["cell"]] = row
        for judge in JUDGES:
            for endpoint in ENDPOINTS:
                observed(row, judge, endpoint)
    for blocks in grouped.values():
        require(set(blocks) == set(range(1, n + 1)), "Missing/unplanned block")
        require(all(set(b) == set(cells) for b in blocks.values()), "Missing cell")
        require(Counter(b[cells[0]]["family"] for b in blocks.values()) == {"a": n // 2, "b": n // 2},
                "Wording balance changed")
    return grouped


def bounded_interval(mean, n, family=8):
    radius = 2 * math.sqrt(math.log(2 * family / .05) / (2 * n))
    return [max(-1, mean - radius), min(1, mean + radius)]


def derive(saved):
    plan, release = saved["plan"], saved["release"]
    require(plan["analysis"]["primary_family_size"] == 8
            and plan["analysis"]["primary_judge"] == "astra"
            and plan["analysis"]["primary_endpoint"] == INCLUSIVE
            and plan["analysis"]["primary_contrasts"] == list(PRIMARY)
            and plan["analysis"]["missing_is_negative"] is False, "Primary analysis changed")
    require(plan["qualification"] == {"complete_blocks": 12, "min_coherent_fraction": .9,
            "max_missing_fraction": .05, "min_positive": 4, "min_negative": 4,
            "conflict_excess_is_exclusion": False}, "Screen rule changed")
    require(release["status"] == "complete" and release["admitted_models"] == list(MODELS),
            "Main admission/completion changed")
    require(release["deferred_models"]["deepseek"]["target_calls"] == 0
            and plan["deferred_models"]["deepseek"]["status"] == "not_run_privacy_route_unavailable",
            "DeepSeek was not a negative outcome")
    deferred = [r for r in saved["screen_rows"] if r["model"] == "deepseek"]
    planned_deferred = {r["id"]: r for b in plan["screen"] if b["model"] == "deepseek"
                        for r in b["finals"]}
    require(len(deferred) == len(planned_deferred) == 48
            and {r["id"] for r in deferred} == set(planned_deferred), "Deferred inventory changed")
    require(all(all(r.get(k) == value for k, value in planned_deferred[r["id"]].items())
                and r["status"] == "not_generated" and r["response"] is None
                and r["labels"] == {} for r in deferred), "Deferred slots contain outcomes")
    screen_rows = [r for r in saved["screen_rows"] if r["model"] != "deepseek"]
    screen = inventory(screen_rows, plan, "screen", SCREEN_MODELS, 12, CELLS[:4])
    main = inventory(saved["main_rows"], plan, "main", MODELS, 32, CELLS)
    require(not ({r["id"] for r in saved["main_rows"]} &
                 {r["id"] for r in saved["screen_rows"]}), "Screen/main overlap")
    result = {"source_commit": SOURCE_COMMIT, "freeze": FREEZE, "screen_blocks": 12,
              "main_blocks": 32, "main_answers": len(saved["main_rows"]),
              "screen_answers": len(screen_rows), "screen_unrun_slots": len(deferred),
              "primary_family_size": 8,
              "screen": {}, "main": {}, "model_settings": plan["models"],
              "judge_settings": plan["judges"], "output_cap": plan["generation_output_cap"],
              "deferred": plan["deferred_models"], "scope": SCOPE}
    for model, blocks in screen.items():
        readers = {}
        for judge in JUDGES:
            rows = [r for b in blocks.values() for r in b.values()]
            positive = sum(observed(r, judge, INCLUSIVE) for r in rows)
            coherent = sum(r["labels"][judge]["structured"]["valid_coherent"] is True for r in rows)
            # All required classifications are present in this complete release.
            require(all(type(r["labels"][judge]["structured"][flag]) is bool for r in rows
                        for flag in ("valid_coherent", "refusal", "malformed", "reported_context_conflict")),
                    "Screen quality missingness")
            passed = 4 <= positive <= 44 and coherent / 48 >= .9
            readers[judge] = {"positive": positive, "planned": 48, "missing": 0,
                              "coherent": coherent, "pass": passed}
            original = saved["qualification"]["models"][model]["judges"][judge]
            require(original["positive"] == positive and original["valid_coherent"] == coherent
                    and original["missing"] == 0, "Screen summary disagrees with rows")
        eligible = all(v["pass"] for v in readers.values())
        require(eligible == (model in MODELS), "Recomputed screening admission changed")
        result["screen"][model] = {"readers": readers, "eligible": eligible}
    for model, blocks in main.items():
        readers = {}
        for judge in JUDGES:
            readers[judge] = {}
            for endpoint in ENDPOINTS:
                original = saved["analysis"]["models"][model]["judges"][judge][endpoint]
                counts = {cell: sum(observed(b[cell], judge, endpoint) for b in blocks.values())
                          for cell in CELLS}
                for cell, positive in counts.items():
                    prior = original["cells"][cell]
                    require(prior["positive"] == positive and prior["observed"] == 32
                            and prior["missing"] == 0, "Main cell summary disagrees with rows")
                contrasts = {}
                for name, coefficients in CONTRASTS.items():
                    values = [sum(weight * observed(b[cell], judge, endpoint)
                                  for cell, weight in coefficients.items())
                              for _, b in sorted(blocks.items())]
                    mean = math.fsum(values) / 32
                    prior = original["contrasts"][name]
                    close(prior["complete_case_mean"], mean)
                    require(prior["coefficients"] == coefficients and prior["missing_blocks"] == 0,
                            "Contrast definition/missingness changed")
                    require([r["value"] for r in prior["per_block"]] == values,
                            "Released paired-block values disagree")
                    current = {"estimate": mean, "planned_blocks": 32, "missing_blocks": 0}
                    if judge == "astra" and endpoint == INCLUSIVE and name in PRIMARY:
                        current["simultaneous_ci95"] = bounded_interval(mean, 32)
                        for actual, expected in zip(prior["familywise_hoeffding_95"], current["simultaneous_ci95"]):
                            close(actual, expected)
                    contrasts[name] = current
                readers[judge][endpoint] = {"positive": counts, "n_per_cell": 32, "contrasts": contrasts}
        result["main"][model] = readers
    return result


def rd(value):
    rounded = Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, ".2f")


def render_values(result):
    values = {"MainAnswers": str(result["main_answers"]), "MainBlocks": "32",
              "ScreenBlocks": "12", "ScreenDenominator": "48", "FamilySize": "8"}
    for model in SCREEN_MODELS:
        for judge in JUDGES:
            values[model.title() + judge.title() + "Screen"] = str(result["screen"][model]["readers"][judge]["positive"])
    for model in MODELS:
        for judge in JUDGES:
            for endpoint, suffix in ((INCLUSIVE, "Inclusive"), (EXPLICIT, "Explicit"), ("paper", "Paper")):
                row = result["main"][model][judge][endpoint]
                prefix = model.title() + judge.title() + suffix
                values[prefix + "Effect"] = rd(row["contrasts"][PRIMARY[0]]["estimate"])
                if judge == "astra" and endpoint == INCLUSIVE:
                    lo, hi = row["contrasts"][PRIMARY[0]]["simultaneous_ci95"]
                    values[prefix + "CI"] = "[" + rd(lo) + ", " + rd(hi) + "]"
                    lo, hi = row["contrasts"][PRIMARY[1]]["simultaneous_ci95"]
                    values[prefix + "NeutralCI"] = "[" + rd(lo) + ", " + rd(hi) + "]"
                for cell in ("NS", "NH"):
                    values[prefix + cell] = str(row["positive"][cell])
    lines = ["% Generated from released response-level labels; see manifest.json."]
    lines += ["\\newcommand{\\ORS" + name + "}{" + value + "}" for name, value in sorted(values.items())]
    lines += ["\\newcommand{\\ORSArtifact}[2]{\\href{https://github.com/tdj28/llm_selfref_pre/blob/"
              + SOURCE_COMMIT + "/#1}{#2}}"]
    return ("\n".join(lines) + "\n").encode("ascii")


def figure_data(result):
    return {"contrast": "SH-HS", "sampling_unit": "paired_block", "blocks": 32,
            "interval_scope": "Astra inclusive only; 95% simultaneous over fixed eight-comparison family",
            "other_points": "descriptive, no confirmatory intervals",
            "rows": [{"model": model, "endpoint": endpoint, "judge": judge,
                      **result["main"][model][judge][endpoint]["contrasts"][PRIMARY[0]]}
                     for model in MODELS for endpoint in ENDPOINTS for judge in JUDGES]}


def render_figure(data, root=ROOT):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                         "pdf.fonttype": 42, "axes.spines.top": False,
                         "axes.spines.right": False}):
        fig, axes = plt.subplots(2, 1, figsize=(7, 5.2), sharex=True)
        for ax, model, title in zip(axes, MODELS, ("Gemini 3.1 Pro Preview", "Claude Opus 5.5")):
            ax.set_title(title, loc="left", fontsize=11, weight="bold", pad=8)
            for index, endpoint in enumerate(ENDPOINTS):
                for judge, offset, color, marker in (("astra", .10, "#17607c", "o"),
                                                     ("opus", -.10, "#a64438", "s")):
                    row = next(r for r in data["rows"] if r["model"] == model
                               and r["endpoint"] == endpoint and r["judge"] == judge)
                    y = 2 - index + offset
                    if "simultaneous_ci95" in row:
                        lo, hi = row["simultaneous_ci95"]
                        ax.hlines(y, lo, hi, color=color, linewidth=2)
                        ax.vlines([lo, hi], y - .05, y + .05, color=color, linewidth=1.3)
                    ax.plot(row["estimate"], y, marker=marker, color=color, markersize=6,
                            label=("Astra judge" if judge == "astra" else "Opus judge")
                            if model == "gemini" and index == 0 else None)
            ax.set_yticks([2, 1, 0], ["Inclusive claim (primary)", "Explicit claim only", "Paper rubric"])
            ax.set_ylim(-.4, 2.5)
            ax.axvline(0, color="#777777", linewidth=.8)
            ax.set_xlim(-1.04, 1.04)
            ax.xaxis.set_major_locator(MultipleLocator(.5))
            ax.grid(axis="x", color="#dddddd", linewidth=.6)
            ax.set_axisbelow(True)
            ax.tick_params(axis="y", length=0, pad=8)
        axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.28), ncol=2, frameon=False)
        axes[1].set_xlabel("Instruction-minus-continuation contrast (SH - HS)", labelpad=10)
        fig.subplots_adjust(left=.31, right=.97, top=.85, bottom=.13, hspace=.55)
        for extension in ("pdf", "png"):
            path = local(root, FIGURE + "." + extension)
            path.parent.mkdir(parents=True, exist_ok=True)
            metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {}
            fig.savefig(path, dpi=180, metadata=metadata)
        plt.close(fig)


def output_bytes(result):
    return {"results.json": encoded(result), "values.tex": render_values(result),
            "figure_data.json": encoded(figure_data(result))}


def manifest(root, provenance):
    paths = [PACKAGE + "/inputs/source_inventory.json",
             *(PACKAGE + "/inputs/" + k + ".json.gz" for k in INPUTS),
             *(PACKAGE + "/" + n for n in DERIVED), *OWN, FIGURE + ".pdf", FIGURE + ".png"]
    return {"schema": "openrouter-swap-editorial-binding-v1", "source_commit": SOURCE_COMMIT,
            "freeze": FREEZE, "release": RELEASE, "source_manifest_sha256": MANIFEST_SHA,
            "source_inputs": provenance, "scope": SCOPE,
            "files": {p: {"sha256": sha(local(root, p).read_bytes()),
                          "bytes": local(root, p).stat().st_size} for p in paths}}


def verify(root=ROOT):
    saved, provenance = load_sources(root)
    result = derive(saved)
    for name, content in output_bytes(result).items():
        require(local(root, PACKAGE + "/" + name).read_bytes() == content,
                "Derived output differs: " + name)
    expected = manifest(root, provenance)
    require(decode(local(root, PACKAGE + "/manifest.json").read_bytes()) == expected,
            "Editorial manifest/file hash changed")
    text = local(root, "paper/openrouter_swap_extension.tex").read_text()
    defined = set(re.findall(r"\\newcommand\{\\(ORS[A-Za-z]+)\}", render_values(result).decode()))
    require(set(re.findall(r"\\(ORS[A-Za-z]+)", text)) <= defined, "Undefined manuscript macro")
    return {"pass": True, "main_answers": result["main_answers"],
            "screen_answers": result["screen_answers"], "scope": SCOPE}


def write(root=ROOT):
    saved, provenance = load_sources(root)
    result = derive(saved)
    for name, raw in output_bytes(result).items():
        local(root, PACKAGE + "/" + name).write_bytes(raw)
    render_figure(figure_data(result), root)
    local(root, PACKAGE + "/manifest.json").write_bytes(encoded(manifest(root, provenance)))
    return verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only (the default)")
    parser.add_argument("--write", action="store_true", help="Rebuild editorial bindings and figure")
    parser.add_argument("--source-release", type=Path, help="Import pinned local release (requires --write)")
    args = parser.parse_args()
    require(not (args.check and args.write), "Choose check or write")
    require(not args.source_release or args.write, "Source import requires --write")
    if args.source_release:
        import_sources(args.source_release)
    print(json.dumps(write() if args.write else verify(), sort_keys=True))


if __name__ == "__main__":
    main()
