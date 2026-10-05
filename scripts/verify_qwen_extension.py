#!/usr/bin/env python3
"""Offline row-to-manuscript binding for Qwen3.8, separate from its releases.

Default verification uses only the standard library. --write regenerates only
the editorial package and measurement figure. Receipt replay belongs to the
separate recovery-release verifier; this script independently recomputes counts,
paired contrasts, primary bounds and descriptive bootstrap intervals from
its hash-pinned response rows.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import random
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/qwen_extension"
SOURCE_COMMIT = "0eb2e039ae0807dca9c9df262db18e2d863d428d"
ORIGINAL_COMMIT = "ad49e88f9cd4235670686ddcd5933ff9b98eb3be"
FREEZE = "a366b664855dfed12590803134a7841844360175"
RELEASE = "data/qwen_judge_recovery/release_v1_20261005"
ORIGINAL = "data/openrouter_swap_openweights_a2/main_v1_20261004"
MANIFESTS = {"recovery": "08529400e650095d693a60551f11cdf97b157f467c19feef2c15df3c6d4103e1",
             "original": "24b97a49f40965a8002440442e6843016d64d0fde9e5204cbb90b0014cd7f041"}
INPUTS = {"rows": ("recovery", "recovery_main_rows.json"),
          "analysis": ("recovery", "recovery_main_analysis.json"),
          "release": ("recovery", "RELEASE.json"), "report": ("recovery", "recovery_report.json"),
          "recovery_plan": ("recovery", "PLAN.json"),
          "plan": ("original", "PLAN.json"), "original_rows": ("original", "main_rows.json")}
MODEL = "qwen/qwen3.8-2.4t-a95b"
INCLUSIVE, EXPLICIT = "inclusive_current_assertion", "explicit_current_assertion"
ENDPOINTS, JUDGES = (INCLUSIVE, EXPLICIT, "paper"), ("astra", "opus")
CELLS = ("SS", "SH", "HS", "HH", "NS", "NH", "S_SHAM", "H_SHAM")
CONTRASTS = {"swap": {"SH": 1, "HS": -1}, "neutral": {"NS": 1, "NH": -1}}
SAVED_NAMES = {"swap": "instruction_minus_transcript", "neutral": "neutral_transcript"}
BOOTSTRAP_SEED, BOOTSTRAP_RESAMPLES = 20261004, 10000
BOOTSTRAP_SOURCE_SHA = "ce3f420ad33f561c17279fd624f41cf721ffbb93336448d86e375a234c7dd879"
TARGETS = ("openweights-main-qwen-02-final-HS", "openweights-main-qwen-02-final-NS",
           "openweights-main-qwen-04-final-SH")
OWN = ("scripts/verify_qwen_extension.py", "tests/test_qwen_extension.py", "paper/qwen_extension.tex",
       PACKAGE + "/README.md")
DERIVED = ("results.json", "values.tex", "figure_data.json", "measurement.pdf", "measurement.png")
SCOPE = {"row_counts_and_paired_contrasts_recomputed": True,
         "primary_four_comparison_bounds_recomputed": True,
         "secondary_bootstrap_intervals_recomputed": True,
         "raw_receipts_reaudited_by_this_command": False, "posthoc_scoring_repair": True,
         "new_responses": False, "human_validation": False, "authorizes_collection": False}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def local(root, name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and ".." not in relative.parts and relative.as_posix() == name,
            "Unsafe relative path")
    path = Path(root)
    require(not path.is_symlink(), "Symlink root")
    for part in relative.parts:
        path /= part
        require(not path.is_symlink(), "Symlink input")
    return path


def source_entries(raw, kind):
    require(sha(raw) == MANIFESTS[kind], "Source manifest pin changed")
    entries = decode(raw)["files"]
    result = {row["path"]: row for row in entries}
    require(len(result) == len(entries), "Duplicate source path")
    return result


def load_sources(root=ROOT):
    base = PACKAGE + "/inputs/"
    manifests = {kind: source_entries(local(root, base + kind + "_inventory.json").read_bytes(), kind)
                 for kind in MANIFESTS}
    values, provenance = {}, {}
    for key, (kind, name) in INPUTS.items():
        raw = gzip.decompress(local(root, base + key + ".json.gz").read_bytes())
        entry = manifests[kind][name]
        require(sha(raw) == entry["sha256"] and len(raw) == entry["bytes"], "Source hash/size changed: " + key)
        values[key] = decode(raw)
        provenance[key] = {"archive": kind, "release_path": name, "sha256": sha(raw), "bytes": len(raw)}
    return values, provenance


def import_sources(repo=ROOT, root=ROOT):
    paths = {"recovery": RELEASE, "original": ORIGINAL}
    imported = {}
    for kind, release in paths.items():
        raw = local(repo, release + "/MANIFEST.json").read_bytes()
        source_entries(raw, kind)
        imported[kind + "_inventory.json"] = (kind, "MANIFEST.json", raw)
    for key, (kind, name) in INPUTS.items():
        raw = local(repo, paths[kind] + "/" + name).read_bytes()
        entry = source_entries(imported[kind + "_inventory.json"][2], kind)[name]
        require(sha(raw) == entry["sha256"] and len(raw) == entry["bytes"], "Import differs from release")
        imported[key + ".json.gz"] = (kind, name, raw)
    for dest, (kind, name, raw) in imported.items():
        commit = SOURCE_COMMIT if kind == "recovery" else ORIGINAL_COMMIT
        if commit is not None:
            require(re.fullmatch(r"[0-9a-f]{40}", commit), "Full source commit required")
            pinned = subprocess.run(["git", "show", commit + ":" + paths[kind] + "/" + name],
                                    cwd=repo, check=True, capture_output=True).stdout
            require(pinned == raw, "Source differs from pinned local Git object")
        target = local(root, PACKAGE + "/inputs/" + dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gzip.compress(raw, mtime=0) if dest.endswith(".gz") else raw)


def close(actual, expected):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12), "Saved analysis disagrees with rows")


def observed(row, judge, endpoint):
    require(row["status"] == "ok" and row["cap_hit"] is False
            and isinstance(row["response"], str) and row["response"].strip(), "Missing or capped response")
    labels = row["labels"][judge]
    require(labels["structured"]["refusal"] is False, "Refusal is not a negative label")
    value = labels["paper"] if endpoint == "paper" else labels["structured"][endpoint]
    require(type(value) is bool, "Missing or nonboolean endpoint")
    return int(value)


def bounded_interval(mean, n=32, family=4):
    radius = 2 * math.sqrt(math.log(2 * family / .05) / (2 * n))
    return [max(-1, mean - radius), min(1, mean + radius)]


@lru_cache(maxsize=128)
def paired_bootstrap(groups):
    """Frozen algorithm: seeded block resampling within ordered wording strata."""
    values = tuple(value for group in groups for value in group)
    require(values and all(groups), "Bootstrap requires complete paired strata")
    if all(len(set(group)) <= 1 for group in groups):
        mean = sum(values) / len(values)
        return (mean, mean), True
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(sum(sum(rng.choices(group, k=len(group))) for group in groups) / len(values)
                   for _ in range(BOOTSTRAP_RESAMPLES))
    def quantile(p):
        position = (len(means) - 1) * p
        lower = math.floor(position)
        weight = position - lower
        return means[lower] * (1 - weight) + means[math.ceil(position)] * weight
    interval = (quantile(.025), quantile(.975))
    return interval, interval[0] == interval[1]


def derive(saved):
    release, plan, report = saved["release"], saved["plan"], saved["report"]
    require(release["runtime"]["freeze"] == FREEZE and release["response_model"] == MODEL
            and plan["models"]["qwen"]["id"] == MODEL, "Wrong model or recovery freeze")
    require(release["status"] == "recovered" and release["original_release_status"] == "incomplete"
            and release["posthoc_scoring_repair"] is True and release["new_response_generations"] == 0,
            "Recovery status or timing changed")
    logical = {"judge:" + row + ":astra:structured:a0" for row in TARGETS}
    require(set(report["recovered"]) == logical and report["remaining_missing"] == []
            and {row["call_id"] for row in saved["recovery_plan"]["targets"]} == logical,
            "Repair target inventory changed")
    projected = deepcopy(saved["original_rows"])
    for row in projected:
        call_id = "judge:" + row["id"] + ":astra:structured:a0"
        if call_id in logical:
            require(row["labels"]["astra"].get("structured") is None, "Completed judgment replaced")
            row["labels"]["astra"]["structured"] = report["recovered"][call_id]
    require(projected == saved["rows"], "Repair changed more than three missing structured labels")
    family = saved["analysis"]["primary_family"]
    require(plan["primary_family_size"] == family["fixed_family_size"] == 4
            and family["planned_models"] == ["qwen", "mistral"] and family["judge"] == "astra"
            and family["endpoint"] == INCLUSIVE and family["contrasts"] == list(SAVED_NAMES.values())
            and family["method"] == "Bonferroni bounded Hoeffding" and family["familywise_confidence"] == .95,
            "Primary family changed")
    planned = {row["id"]: row for block in plan["main"] for row in block["finals"]}
    require(len(planned) == len(saved["rows"]) == 512
            and len({row["id"] for row in saved["rows"]}) == 512, "Missing or duplicate planned rows")
    blocks = {}
    for row in saved["rows"]:
        require(row["id"] in planned and all(row.get(k) == v for k, v in planned[row["id"]].items()),
                "Row differs from planned block/cell/donor")
        if row["model"] == "mistral":
            require(row["status"] == "not_generated" and row["response"] is None and row["labels"] == {},
                    "Unrun Mistral acquired outcomes")
            continue
        require(row["model"] == "qwen", "Foreign model")
        block = blocks.setdefault(row["block"], {})
        require(row["cell"] not in block, "Duplicate cell")
        block[row["cell"]] = row
    require(set(blocks) == set(range(1, 33)) and all(set(b) == set(CELLS) for b in blocks.values()),
            "Qwen block/cell inventory changed")
    require(Counter(b["SS"]["family"] for b in blocks.values()) == {"a": 16, "b": 16}, "Wording balance changed")
    require(plan["source_hashes"]["experiments/openrouter_swap/analysis.py"] == BOOTSTRAP_SOURCE_SHA,
            "Frozen bootstrap implementation changed")
    families = [b["SS"]["family"] for _, b in sorted(blocks.items())]
    results = {"response_model": MODEL, "blocks": 32, "answers": 256, "family_size": 4,
               "recovered_labels": 3, "source_commit": SOURCE_COMMIT, "recovery_freeze": FREEZE,
               "bootstrap_source_sha256": BOOTSTRAP_SOURCE_SHA,
               "judges": {}, "model_settings": plan["models"]["qwen"], "scope": SCOPE}
    for judge in JUDGES:
        results["judges"][judge] = {}
        for endpoint in ENDPOINTS:
            prior = saved["analysis"]["models"]["qwen"]["judges"][judge][endpoint]
            counts = {cell: sum(observed(b[cell], judge, endpoint) for b in blocks.values()) for cell in CELLS}
            for cell, count in counts.items():
                s = prior["cells"][cell]
                require(s["positive"] == count and s["observed"] == s["planned"] == 32 and s["missing"] == 0,
                        "Cell count disagrees with rows")
            contrasts = {}
            for name, coefficients in CONTRASTS.items():
                paired = [sum(weight * observed(b[cell], judge, endpoint) for cell, weight in coefficients.items())
                          for _, b in sorted(blocks.items())]
                estimate = math.fsum(paired) / 32
                s = prior["contrasts"][SAVED_NAMES[name]]
                require(s["coefficients"] == coefficients and s["complete_blocks"] == s["planned_blocks"] == 32
                        and s["missing_blocks"] == 0 and [x["value"] for x in s["per_block"]] == paired,
                        "Paired contrast definition or block values changed")
                close(s["complete_case_mean"], estimate)
                groups = tuple(tuple(value for value, f in zip(paired, families) if f == family)
                               for family in ("a", "b"))
                interval, degenerate = paired_bootstrap(groups)
                bootstrap = {"interval": list(interval), "degenerate": degenerate,
                             "resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED,
                             "sampling_unit": "paired_complete_block_within_wording_family",
                             "stratified_by": "family", "complete_blocks_by_family": {"a": 16, "b": 16},
                             "unassigned_complete_blocks": 0,
                             "scope": "secondary_conditional_on_observed_complete_blocks",
                             "warning": "Degeneracy is not evidence of precision; use bounded intervals."}
                require(s["bootstrap_95"] == bootstrap, "Saved bootstrap settings or bounds disagree with paired rows")
                contrast = {"estimate": estimate, "paired_values": paired, "bootstrap_95": bootstrap}
                if judge == "astra" and endpoint == INCLUSIVE:
                    contrast["simultaneous_ci95"] = bounded_interval(estimate)
                    for actual, expected in zip(s["familywise_hoeffding_95"], contrast["simultaneous_ci95"]):
                        close(actual, expected)
                contrasts[name] = contrast
            results["judges"][judge][endpoint] = {"positive": counts, "contrasts": contrasts}
    return results


def rd(value):
    rounded = Decimal(str(value)).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, ".2f")


def render_values(result):
    values = {"Blocks": "32", "Answers": "256", "FamilySize": "4", "Recovered": "3",
              "BootstrapResamples": "10{,}000"}
    for judge in JUDGES:
        for endpoint, suffix in ((INCLUSIVE, "Inclusive"), (EXPLICIT, "Explicit"), ("paper", "Paper")):
            row = result["judges"][judge][endpoint]
            prefix = judge.title() + suffix
            values.update({prefix + cell: str(row["positive"][cell]) for cell in CELLS if "_" not in cell})
            for name, contrast in row["contrasts"].items():
                values[prefix + name.title()] = rd(contrast["estimate"])
                if "simultaneous_ci95" in contrast:
                    values[prefix + name.title() + "CI"] = "[" + ", ".join(rd(v) for v in contrast["simultaneous_ci95"]) + "]"
    lines = ["% Generated from pinned Qwen3.8 response labels, not the Qwen3.5 companion."]
    lines += ["\\newcommand{\\QEX" + key + "}{" + value + "}" for key, value in sorted(values.items())]
    lines += (["\\newcommand{\\QEXArtifact}[2]{\\href{https://github.com/tdj28/llm_selfref_pre/blob/" + SOURCE_COMMIT + "/#1}{#2}}"]
              if SOURCE_COMMIT else ["% Pending public release commit; numerical source is manifest-pinned.", "\\newcommand{\\QEXArtifact}[2]{#2}"])
    return ("\n".join(lines) + "\n").encode("ascii")


def figure_data(result):
    return {"model": MODEL, "contrast": "SH-HS", "blocks": 32, "sampling_unit": "paired_block",
            "interval_scope": "Pointwise 95% descriptive paired-block bootstrap within wording families; not primary confirmatory bounds",
            "primary_inference": "Separate four-comparison simultaneous Hoeffding bounds remain in the prose",
            "bootstrap_seed": BOOTSTRAP_SEED, "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "rows": [{"judge": j, "endpoint": e,
                      "estimate": result["judges"][j][e]["contrasts"]["swap"]["estimate"],
                      "descriptive_ci95": result["judges"][j][e]["contrasts"]["swap"]["bootstrap_95"]["interval"]}
                     for e in ENDPOINTS for j in JUDGES]}


def render_figure(data, root=ROOT):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    import matplotlib
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}):
        fig = Figure(figsize=(6.4, 2.8), dpi=180)
        FigureCanvasAgg(fig)
        ax = fig.add_axes((.28, .22, .69, .62))
        for index, endpoint in enumerate(ENDPOINTS):
            for judge, offset, color, marker in (("astra", .13, "#17607c", "o"), ("opus", -.13, "#a64438", "s")):
                row = next(r for r in data["rows"] if r["judge"] == judge and r["endpoint"] == endpoint)
                y = 2 - index + offset
                lo, hi = row["descriptive_ci95"]
                ax.hlines(y, lo, hi, color=color, linewidth=1.5)
                ax.vlines([lo, hi], y-.05, y+.05, color=color, linewidth=1)
                ax.plot(row["estimate"], y, marker=marker, color=color, markersize=5,
                        label=judge.title() if index == 0 else None)
        ax.set(yticks=[2, 1, 0], yticklabels=["Inclusive claim", "Explicit claim only", "Paper rubric"],
               ylim=(-.4, 2.4), xlim=(-.2, .7), xticks=[-.2, 0, .2, .4, .6],
               xlabel="Label-rate difference (SH - HS)")
        ax.axvline(0, color="#777777", linewidth=.8)
        ax.grid(axis="x", color="#dddddd", linewidth=.6)
        ax.set_axisbelow(True)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=8)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, frameon=False)
        for extension in ("pdf", "png"):
            target = local(root, PACKAGE + "/measurement." + extension)
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {}
            fig.savefig(target, metadata=metadata)
    return fig


def output_bytes(result):
    return {"results.json": encoded(result), "values.tex": render_values(result),
            "figure_data.json": encoded(figure_data(result))}


def manifest(root, provenance):
    paths = [*(PACKAGE + "/inputs/" + k + "_inventory.json" for k in MANIFESTS),
             *(PACKAGE + "/inputs/" + k + ".json.gz" for k in INPUTS),
             *(PACKAGE + "/" + name for name in DERIVED), *OWN]
    return {"schema": "qwen-extension-editorial-v1", "source_commit": SOURCE_COMMIT,
            "original_commit": ORIGINAL_COMMIT, "recovery_freeze": FREEZE, "source_manifest_sha256": MANIFESTS,
            "source_inputs": provenance, "scope": SCOPE,
            "files": {name: {"sha256": sha(local(root, name).read_bytes()), "bytes": local(root, name).stat().st_size}
                      for name in paths}}


def verify(root=ROOT, *, require_pinned=False):
    require(not require_pinned or SOURCE_COMMIT is not None, "Public source commit still pending")
    if SOURCE_COMMIT is not None:
        require(re.fullmatch(r"[0-9a-f]{40}", SOURCE_COMMIT), "Invalid source commit")
    saved, provenance = load_sources(root)
    result = derive(saved)
    for name, raw in output_bytes(result).items():
        require(local(root, PACKAGE + "/" + name).read_bytes() == raw, "Derived editorial output differs: " + name)
    require(decode(local(root, PACKAGE + "/manifest.json").read_bytes()) == manifest(root, provenance),
            "Editorial source or figure hash changed")
    tex = local(root, "paper/qwen_extension.tex").read_text()
    defined = set(re.findall(r"\\newcommand\{\\(QEX[A-Za-z]+)\}", render_values(result).decode()))
    require(set(re.findall(r"\\(QEX[A-Za-z]+)", tex)) <= defined, "Undefined Qwen manuscript macro")
    return {"pass": True, "source_commit_pinned": SOURCE_COMMIT is not None, "answers": 256,
            "paired_blocks": 32, "family_size": 4, "scope": SCOPE}


def write(root=ROOT):
    saved, provenance = load_sources(root)
    result = derive(saved)
    for name, raw in output_bytes(result).items():
        local(root, PACKAGE + "/" + name).write_bytes(raw)
    render_figure(figure_data(result), root)
    local(root, PACKAGE + "/manifest.json").write_bytes(encoded(manifest(root, provenance)))
    return verify(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--require-pinned", action="store_true")
    args = parser.parse_args(argv)
    require(not (args.write and args.check), "Choose write or check")
    require(not args.source_root or args.write, "Import requires write")
    if args.source_root:
        import_sources(args.source_root)
    if args.write:
        write()
    print(json.dumps(verify(require_pinned=args.require_pinned), sort_keys=True))


if __name__ == "__main__":
    main()
