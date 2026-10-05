#!/usr/bin/env python3
"""Offline, additive row/figure binding for a verified final Kolibri release.

No pending source pin or default release path is supplied. Materialization
requires a reviewed manifest and a local Git commit containing the exact
inputs. The exporter retains responsibility for raw receipt/source replay;
this binder also reconstructs row inventories, missingness and paired effects.
Verification requires an external binding digest, not a plot rerender. Optional
strict rerender diagnoses byte differences without accepting changed assets.
Neither command authorizes collection or writes to the release/manuscript.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import inspect
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
SOURCES = ("scripts/verify_kolibri_extension.py", "tests/test_kolibri_extension.py")
INPUTS = {"plan": "provenance/PLAN.json", "release": "RELEASE.json",
          "qualification": "qualification.json", "model": "MODEL_PROVENANCE.json",
          **{p + suffix: p + suffix + ".json" for p in ("screen", "main")
             for suffix in ("_rows", "_analysis")}}
JUDGES = ("astra", "opus")
ENDPOINTS = ("inclusive_current_assertion", "explicit_current_assertion", "paper")
CONTRASTS = {"instruction_minus_transcript": {"SH": 1, "HS": -1},
             "neutral_transcript": {"NS": 1, "NH": -1}}
COLORS = {"astra": "#17607c", "opus": "#a64438"}
VECTORS = ("kolibri.pdf", "kolibri.svg")
TEXT_OUTPUTS = ("results.json", "values.tex")
OUTPUTS = (*TEXT_OUTPUTS, "figure_data.json", *VECTORS)


def require(value, message):
    if not value:
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
    def invalid(_):
        raise ValueError("Nonfinite JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def local(root, name):
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.parts and ".." not in relative.parts
            and relative.as_posix() == name and "\\" not in name, "Unsafe artifact path")
    path = Path(root).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink artifact root")
    for part in relative.parts:
        path /= part
        require(not path.is_symlink(), "Symlink artifact")
    return path


def _replay_release(root, pin):
    from experiments import kolibri_release
    require("rerender" in inspect.signature(kolibri_release.verify).parameters,
            "Exporter explicit rerender=False verification interface is not available yet")
    return kolibri_release.verify(root, expected_manifest_sha256=pin, rerender=False)


def read_sources(root, pin):
    require(isinstance(pin, str) and re.fullmatch(r"[0-9a-f]{64}", pin), "Reviewed manifest SHA required")
    raw = local(root, "MANIFEST.json").read_bytes()
    require(sha(raw) == pin, "Release manifest pin differs")
    manifest = decode(raw)
    require(manifest["schema"] == "kolibri-release-manifest-v1", "Unsupported release inventory")
    entries = {entry["path"]: entry for entry in manifest["files"]}
    require(len(entries) == len(manifest["files"]), "Duplicate release artifact")
    report = _replay_release(Path(root), pin)
    require(report.get("pass") is True and report.get("manifest_sha256") == pin
            and report.get("reviewed_manifest_pinned") is True and report.get("figures_rerendered") is False,
            "Release replay did not certify the pinned bundle in explicit non-rerender mode")
    values, bindings = {}, {}
    for key, name in INPUTS.items():
        body = local(root, name).read_bytes()
        entry = {"path": name, "bytes": len(body), "sha256": sha(body)}
        require(entries.get(name) == entry, "Release input hash/size differs")
        values[key], bindings[key] = decode(body), entry
    require(sha(local(root, "MANIFEST.json").read_bytes()) == pin, "Release changed during verification")
    require(values["release"]["status"] == report["status"]
            and values["release"]["plan_sha256"] == bindings["plan"]["sha256"], "Release status/plan binding differs")
    return values, bindings


def derive(values):
    from experiments.kolibri_swap import analysis, protocol
    from experiments.openrouter_swap import analysis as common

    release, plan = values["release"], values["plan"]
    require(release["schema"] == "kolibri-release-v1"
            and release["status"] in {"screen_stopped", "main_complete", "technical_incomplete"},
            "Unsupported release status")
    require(set(plan["models"]) == {"kolibri"} and plan["models"]["kolibri"]["id"] == protocol.MODEL["id"]
            and set(plan["judges"]) == set(JUDGES) and release["primary_family_size"] == 2
            and release["unrun_is_zero"] is False and release["independent_human_validation"] is False,
            "Model, readers or scientific scope differs")
    require(release["completion"]["screen"] is True and release["qualification_evaluable"] is True
            and release["fixture_gate"]["pass"] is True and release["audit"]["pass"] is True,
            "Verified completed screen and fixture/receipt gates required")
    require(values["qualification"] == analysis.qualify(values["screen_rows"]), "Qualification differs from rows")
    main = release["status"] == "main_complete"
    technical = release["status"] == "technical_incomplete"
    require(release["completion"]["main"] is main, "Completion state differs")
    require(values["qualification"]["inventory_valid"] is True
            and values["qualification"]["eligible_models"] == (["kolibri"] if main or technical else []),
            "Conditional main/stop disagrees with qualification")
    qualification = values["qualification"]["models"]["kolibri"]
    result = {"schema": "kolibri-extension-results-v1", "status": release["status"],
              "model": plan["models"]["kolibri"]["id"], "conditional_on_screen": True,
              "phases": {}, "primary": None, "human_validation": False,
              "publication_kind": "status_only" if technical else "figure",
              "qualification": {"source": "qualification.json", "qualified": qualification["qualified"],
                  "reason_codes": deepcopy(qualification["reason_codes"]),
                  "reader_reason_codes": {j: deepcopy(qualification["judges"][j]["reason_codes"]) for j in JUDGES}},
              "bootstrap_source_sha256": plan["source_hashes"]["experiments/openrouter_swap/analysis.py"]}
    if technical:
        result["technical_stop"] = {"state": "qualified_screen_main_not_run",
            "evidence": {"RELEASE.json": ["status", "completion", "counts.main"],
                         "qualification.json": ["inventory_valid", "eligible_models"]},
            "cause": None, "cause_status": "not_recorded_in_bound_summary",
            "behavioral_failure": False}
    for phase in ("screen", "main"):
        rows, saved = values[phase + "_rows"], values[phase + "_analysis"]
        planned = {item["id"]: item for block in plan[phase] for item in block["finals"]}
        require(plan[phase] == protocol.inventory(phase) and len(planned) == len(rows)
                and len({row["id"] for row in rows}) == len(rows), "Planned final inventory differs")
        require(all(row["id"] in planned and all(type(row.get(k)) is type(v) and row[k] == v
                    for k, v in planned[row["id"]].items()) for row in rows), "Row differs from frozen plan")
        require(saved == analysis.analyze(rows, phase), "Saved analysis does not replay")
        counts = release["counts"][phase]
        require(counts["planned_finals"] == len(rows)
                and counts["planned_sources"] == sum(len(b["sources"]) for b in plan[phase])
                and counts["missing_final_content"] == sum(not r["response"] for r in rows)
                and counts["cap_hit"] == sum(r["cap_hit"] for r in rows), "Release counts differ from rows")
        if phase == "main" and not main:
            require(counts["source_dispatches"] == counts["final_dispatches"] == 0
                    and all(r["status"] == "not_generated" and r["response"] is None
                            and r["labels"] == {} and r["cap_hit"] is False for r in rows),
                    "Unrun main contains dispatches or observations")
            result["phases"][phase] = {"state": "not_run", "counts": deepcopy(counts), "judges": None}
            continue
        n = 12 if phase == "screen" else 32
        blocks = {b: {r["cell"]: r for r in rows if r["block"] == b} for b in range(1, n + 1)}
        require(Counter(next(iter(b.values()))["family"] for b in blocks.values()) == {"a": n // 2, "b": n // 2},
                "Wording strata differ")
        model = saved["models"]["kolibri"]
        require(set(model["judges"]) == set(JUDGES), "Missing reader analysis")
        phase_result = {"state": "collected", "counts": deepcopy(counts), "judges": {}}
        names = [] if technical else list(CONTRASTS) if phase == "main" else ["instruction_minus_transcript"]
        for judge in JUDGES:
            phase_result["judges"][judge] = {}
            require(set(model["judges"][judge]) == set(ENDPOINTS), "Missing instrument/endpoint analysis")
            for endpoint in ENDPOINTS:
                source = model["judges"][judge][endpoint]
                contrasts = {}
                for name in names:
                    paired, bounds, groups = [], [0., 0.], {"a": [], "b": []}
                    for cells in blocks.values():
                        terms = [(weight, common._value(cells[cell], judge, endpoint))
                                 for cell, weight in CONTRASTS[name].items()]
                        for weight, value in terms:
                            bounds[0] += min(0, weight) if value is None else weight * value
                            bounds[1] += max(0, weight) if value is None else weight * value
                        if all(value is not None for _, value in terms):
                            value = sum(weight * label for weight, label in terms)
                            paired.append(value)
                            groups[next(iter(cells.values()))["family"]].append(value)
                    interval, collapsed = common._bootstrap(tuple(tuple(groups[f]) for f in ("a", "b")))
                    mean = sum(paired) / len(paired) if paired else None
                    previous = source["contrasts"][name]
                    worst = [x / n for x in bounds]
                    radius = 2 * math.sqrt(math.log(2 / .05) / (2 * n))
                    pointwise = [max(-1, worst[0] - radius), min(1, worst[1] + radius)]
                    require(previous["worst_case_hoeffding_95"] == pointwise,
                            "Pointwise Hoeffding bound disagrees with planned blocks/missingness")
                    require(previous["complete_case_mean"] == mean and previous["complete_blocks"] == len(paired)
                            and previous["worst_case_mean_bounds"] == worst
                            and previous["bootstrap_95"]["interval"] == (list(interval) if interval else None),
                            "Paired contrast disagrees with rows")
                    contrasts[name] = {"estimate": mean, "complete_blocks": len(paired), "planned_blocks": n,
                        "missing_blocks": n - len(paired), "missing_label_bounds": worst,
                        "worst_case_hoeffding_95": deepcopy(previous["worst_case_hoeffding_95"]),
                        "descriptive_95": list(interval) if interval else None, "collapsed": collapsed}
                totals = {key: sum(cell[key] for cell in source["cells"].values())
                          for key in ("planned", "observed", "positive", "negative", "missing")}
                phase_result["judges"][judge][endpoint] = {
                    "counts": totals, "cells": deepcopy(source["cells"]), "contrasts": contrasts}
        result["phases"][phase] = phase_result
    if main:
        family = values["main_analysis"]["primary_family"]
        require(family["fixed_family_size"] == 2 and family["planned_models"] == ["kolibri"]
                and family["judge"] == "astra" and family["endpoint"] == ENDPOINTS[0]
                and family["contrasts"] == list(CONTRASTS) and family["familywise_confidence"] == .95
                and family["method"] == "Bonferroni bounded Hoeffding", "Primary family changed")
        primary = {"judge": "astra", "endpoint": ENDPOINTS[0], "family_size": 2,
                   "familywise_confidence": .95, "individual_confidence": .975,
                   "method": family["method"], "includes_planned_missingness": True, "contrasts": {}}
        radius = 2 * math.sqrt(math.log(4 / .05) / (2 * 32))
        for name in CONTRASTS:
            bounds = result["phases"]["main"]["judges"]["astra"][ENDPOINTS[0]]["contrasts"][name]["missing_label_bounds"]
            interval = [max(-1, bounds[0] - radius), min(1, bounds[1] + radius)]
            saved = values["main_analysis"]["models"]["kolibri"]["judges"]["astra"][ENDPOINTS[0]]["contrasts"][name]
            require(saved["familywise_hoeffding_95"] == interval, "Primary bound differs")
            primary["contrasts"][name] = {"interval": interval}
        result["primary"] = primary
    return result


def rd(value):
    if value is None:
        return "unavailable"
    number = Decimal(str(value))
    require(number.is_finite(), "Nonfinite TeX value")
    rounded = number.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return format(abs(rounded) if rounded == 0 else rounded, ".2f")


def _tex_interval(value):
    return "unavailable" if value is None else "[" + ", ".join(rd(v) for v in value) + "]"


def render_values(result):
    """KEX{Phase}{Reader}{Endpoint}{Cell/Contrast}{Field}; counts are integers."""
    endpoints = dict(zip(ENDPOINTS, ("Inclusive", "Explicit", "Paper")))
    cells = {"SS": "SS", "HH": "HH", "SH": "SH", "HS": "HS", "NS": "NS", "NH": "NH",
             "S_SHAM": "SSham", "H_SHAM": "HSham"}
    contrasts = dict(zip(CONTRASTS, ("SHHS", "NSNH")))
    status = {"main_complete": "main complete", "screen_stopped": "screen stopped",
              "technical_incomplete": "technical incomplete"}
    values = {"Status": status[result["status"]],
              "Qualification": "passed" if result["qualification"]["qualified"] else "failed",
              "PrimaryFamilySize": "2"}
    for phase, summary in result["phases"].items():
        ran = summary["state"] == "collected"
        values[phase.title() + "State"] = "collected" if ran else "not run"
        values[phase.title() + "PlannedFinals"] = str(summary["counts"]["planned_finals"])
        values[phase.title() + "MissingFinalContent"] = str(summary["counts"]["missing_final_content"]) if ran else "not run"
        for judge in JUDGES:
            for endpoint, label in endpoints.items():
                prefix = phase.title() + judge.title() + label
                row = summary["judges"][judge][endpoint] if ran else None
                for key in ("planned", "observed", "positive", "negative", "missing"):
                    values[prefix + key.title()] = str(row["counts"][key]) if ran else "not run"
                for cell, alias in cells.items():
                    planned = phase == "main" or cell in ("SS", "HH", "SH", "HS")
                    for key in ("planned", "observed", "positive", "negative", "missing"):
                        values[prefix + alias + key.title()] = ("not planned" if not planned else
                            str(row["cells"][cell][key]) if ran else "not run")
                for name, alias in contrasts.items():
                    contrast = row["contrasts"].get(name) if ran else None
                    absent = ("not run" if not ran else "not planned" if phase == "screen" and name == "neutral_transcript"
                              else "not reported")
                    fields = ({"CompleteEstimate": rd(contrast["estimate"]),
                        "DescriptiveCI": _tex_interval(contrast["descriptive_95"]),
                        "MissingLabelBounds": _tex_interval(contrast["missing_label_bounds"]),
                        "CompleteBlocks": str(contrast["complete_blocks"]),
                        "PlannedBlocks": str(contrast["planned_blocks"]),
                        "MissingBlocks": str(contrast["missing_blocks"])} if contrast is not None else
                        {key: absent for key in ("CompleteEstimate", "DescriptiveCI", "MissingLabelBounds",
                                                "CompleteBlocks", "PlannedBlocks", "MissingBlocks")})
                    values.update({prefix + alias + key: value for key, value in fields.items()})
    primary = result["primary"]
    for key, field in (("FamilywiseConfidence", "familywise_confidence"), ("IndividualConfidence", "individual_confidence")):
        values["Primary" + key] = rd(100 * primary[field]) + r"\%" if primary is not None else "not run"
    values["PrimaryMethod"] = primary["method"] if primary is not None else "not run"
    for name, alias in contrasts.items():
        prefix = "PrimaryAstraInclusive" + alias
        values[prefix + "Bounds"] = _tex_interval(primary["contrasts"][name]["interval"]) if primary is not None else "not run"
        for field in ("CompleteBlocks", "PlannedBlocks", "MissingBlocks"):
            values[prefix + field] = values["MainAstraInclusive" + alias + field]
    lines = ["% Generated from pinned Kolibri results; full precision remains in results.json.",
             "% DescriptiveCI: pointwise 95% paired-block bootstrap, not the primary family bounds.",
             "% Primary bounds: Astra inclusive, two-comparison family 95%, individual 97.5%.",
             "% not run / not planned / not reported / unavailable are not numerical zeros."]
    lines += ["\\newcommand{\\KEX" + key + "}{" + value + "}" for key, value in sorted(values.items())]
    return ("\n".join(lines) + "\n").encode("ascii")


def figure_data(result):
    require(result["publication_kind"] == "figure", "Technical stop supports status-only evidence, not figures")
    phase = "main" if result["status"] == "main_complete" else "screen"
    panels = []
    for endpoint, title in ((ENDPOINTS[0], "Explicit or implicit claims"), ("paper", "Paper rubric")):
        points = []
        for judge in JUDGES:
            for name, value in result["phases"][phase]["judges"][judge][endpoint]["contrasts"].items():
                points.append({"judge": judge, "contrast": name, **deepcopy(value)})
        panels.append({"endpoint": endpoint, "label": title, "points": points})
    caption = ("Conditional held-out main after qualification. " if phase == "main" else
               "Qualification screen only; held-out main was not run. ")
    caption += ("Open circles show Astra; open triangles show Opus. Thin bars are conservative pointwise 95% "
                "Hoeffding bounds over planned blocks, including worst-case missing labels. Thick bars are "
                "descriptive 95% bootstrap intervals, resampling complete paired source blocks within wording "
                "families. Neither set of plotted bars is simultaneous across comparisons. The first letter identifies "
                "the instruction and the second the supplied continuation's source: S is self-referential; "
                "H is Roman history. SS and HH match instruction and continuation source; SH combines a "
                "self-referential instruction with a history continuation, and HS a history instruction with "
                "a self-referential continuation. SH-HS compares these two crossed cells. ")
    if phase == "main":
        caption += ("NS-NH holds the neutral instruction fixed and compares self-referential versus history "
                    "continuation sources. ")
    caption += ("Complete-block estimates exclude "
                "missing labels; planned-sample missing-label bounds need not contain those estimates. "
                "Collapsed bootstrap intervals do not establish certainty or equivalence.")
    if phase == "main":
        caption += (" The separate primary Astra inclusive bounds cover the two planned comparisons jointly at 95%; "
                    "they are not the plotted bars. Opus and paper-rubric results are secondary.")
    return {"schema": "kolibri-extension-figure-v1", "phase": phase, "panels": panels,
            "interval": "pointwise_descriptive_paired_block_bootstrap_95", "resamples": 10000,
            "conservative_interval": {"field": "worst_case_hoeffding_95", "confidence": .95,
                "scope": "pointwise_planned_blocks_including_worst_case_missing_labels",
                "familywise": False, "primary": False},
            "seed": 20261004, "width_inches": 6.5, "minimum_font_pt": 9, "caption": caption}


def render(data):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D
    names = list(CONTRASTS) if data["phase"] == "main" else ["instruction_minus_transcript"]
    labels = {"instruction_minus_transcript": "SH - HS", "neutral_transcript": "NS - NH"}
    with plt.rc_context({"font.size": 10, "axes.labelsize": 10, "axes.titlesize": 10,
                         "xtick.labelsize": 9, "ytick.labelsize": 10, "legend.fontsize": 9,
                         "pdf.fonttype": 42, "svg.fonttype": "none", "svg.hashsalt": sha(encoded(data))}):
        fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.2), sharex=True)
        fig.subplots_adjust(left=.14, right=.97, bottom=.14, top=.82, hspace=.7)
        for ax, panel in zip(axes, data["panels"]):
            ax.axvline(0, color="#999999", linewidth=.7, zorder=0)
            ax.set_title(panel["label"], loc="left")
            for point in panel["points"]:
                judge = point["judge"]
                y = names.index(point["contrast"]) + (-.12 if judge == "astra" else .12)
                low, high = point["worst_case_hoeffding_95"]
                ax.hlines(y, low, high, color=COLORS[judge], linewidth=.8, zorder=1)
                ax.vlines([low, high], y - .075, y + .075, color=COLORS[judge], linewidth=.8, zorder=1)
                if point["estimate"] is None:
                    ax.text(.02, y, judge.title() + ": unavailable", transform=ax.get_yaxis_transform(),
                            fontsize=9, color=COLORS[judge], va="center", backgroundcolor="white", zorder=3)
                    continue
                low, high = point["descriptive_95"]
                ax.hlines(y, low, high, color=COLORS[judge], linewidth=2.4, zorder=2)
                ax.vlines([low, high], y - .04, y + .04, color=COLORS[judge], linewidth=1.2, zorder=2)
                ax.plot(point["estimate"], y, "o" if judge == "astra" else "^", markersize=4,
                        markerfacecolor="white", markeredgecolor=COLORS[judge], markeredgewidth=1.1, zorder=3)
            ax.set_yticks(range(len(names)), [labels[n] for n in names])
            ax.set_ylim(len(names) - .5, -.5)
            ax.set_xlim(-1.05, 1.05)
            ax.spines[["top", "right", "left"]].set_visible(False)
            ax.tick_params(axis="y", length=0)
        axes[-1].set_xlabel("Difference in positive-label rate")
        readers = [Line2D([], [], color=COLORS[j], marker=m, markersize=4, linestyle="none",
                   markerfacecolor="white", label=j.title()) for j, m in zip(JUDGES, ("o", "^"))]
        fig.legend(handles=[readers[0], Line2D([], [], color="#555555", linewidth=.8, label="Pointwise 95% bound"),
                            readers[1], Line2D([], [], color="#555555", linewidth=2.4, label="Descriptive 95% bootstrap")],
                   loc="upper center", bbox_to_anchor=(.55, .98), ncol=2, frameon=False)
        images = {}
        try:
            for extension in ("pdf", "svg"):
                buffer = io.BytesIO()
                metadata = {"CreationDate": None, "ModDate": None} if extension == "pdf" else {"Date": None}
                fig.savefig(buffer, format=extension, metadata=metadata)
                images["kolibri." + extension] = buffer.getvalue()
        finally:
            plt.close(fig)
    return images


def _git_pin(repo, release, commit, names):
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "Final source commit required")
    relative = Path(release).absolute().relative_to(Path(repo).absolute()).as_posix()
    for name in names:
        body = subprocess.run(["git", "show", commit + ":" + relative + "/" + name], cwd=repo,
                              check=True, capture_output=True).stdout
        require(body == local(release, name).read_bytes(), "Release input differs from source commit")
    return relative


def _reconstruct(release, pin, commit, repo):
    values, inputs = read_sources(release, pin)
    relative = _git_pin(repo, release, commit, ["MANIFEST.json", *INPUTS.values()])
    results = derive(values)
    data = figure_data(results) if results["publication_kind"] == "figure" else None
    outputs = {"results.json": encoded(results), "values.tex": render_values(results)}
    if data is not None:
        outputs["figure_data.json"] = encoded(data)
    binding = {"schema": "kolibri-extension-binding-v2", "source_commit": commit,
               "release_path": relative, "release_manifest_sha256": pin, "inputs": inputs,
               "publication_kind": results["publication_kind"],
               "verification": "externally_pinned_assets_and_exact_data_replay",
               "source_hashes": {name: sha(local(ROOT, name).read_bytes()) for name in SOURCES}}
    return outputs, binding, data


def _entries(outputs):
    return [{"path": name, "bytes": len(body), "sha256": sha(body)} for name, body in outputs.items()]


def package_bytes(release, pin, commit, repo=ROOT):
    outputs, binding, data = _reconstruct(release, pin, commit, repo)
    if data is not None:
        outputs.update(render(data))
        require(tuple(outputs) == OUTPUTS, "Renderer output inventory differs")
    binding["outputs"] = _entries(outputs)
    return {**outputs, "BINDING.json": encoded(binding)}


def materialize(destination, release, pin, commit, repo=ROOT):
    destination = Path(destination).absolute()
    require(not destination.exists() and not destination.is_symlink(), "New-only package destination required")
    local(destination, "BINDING.json")
    require(not destination.resolve().is_relative_to(Path(release).resolve()), "Cannot write inside immutable release")
    expected = package_bytes(release, pin, commit, repo)
    destination.mkdir(parents=True, exist_ok=False)
    for name, body in expected.items():
        with local(destination, name).open("xb") as handle:
            handle.write(body)
    return decode(expected["BINDING.json"])


def verify_package(destination, release, pin, commit, repo=ROOT, *, expected_binding_sha256=None,
                   strict_rerender=False):
    require(isinstance(expected_binding_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", expected_binding_sha256), "External publication binding SHA required")
    raw = local(destination, "BINDING.json").read_bytes()
    require(sha(raw) == expected_binding_sha256, "Publication binding pin differs")
    saved = decode(raw)
    expected, binding, data = _reconstruct(release, pin, commit, repo)
    names = OUTPUTS if data is not None else TEXT_OUTPUTS
    require({p.relative_to(destination).as_posix() for p in Path(destination).rglob("*")}
            == {*names, "BINDING.json"}, "Publication package inventory differs")
    originals = {name: local(destination, name).read_bytes() for name in names}
    binding["outputs"] = _entries(originals)
    require(saved == binding and raw == encoded(binding), "Bound metadata or artifact hash/size differs")
    for name, body in expected.items():
        require(originals[name] == body, "Publication numeric/text artifact does not reconstruct")
    diagnostic = {"requested": strict_rerender, "state": "not_requested"}
    if strict_rerender:
        if data is None:
            diagnostic["state"] = "not_applicable_status_only"
        else:
            candidates = render(data)
            require(set(candidates) == set(VECTORS), "Renderer output inventory differs")
            same = all(candidates[name] == originals[name] for name in VECTORS)
            diagnostic.update(state="byte_identical" if same else "rendering_bytes_differ", byte_exact=same,
                artifacts={name: {"original_sha256": sha(originals[name]),
                                  "rerendered_sha256": sha(candidates[name]),
                                  "byte_exact": originals[name] == candidates[name]} for name in VECTORS})
    require(local(destination, "BINDING.json").read_bytes() == raw, "Publication binding changed during verification")
    return {"pass": True, "verification": binding["verification"], "publication_kind": binding["publication_kind"],
            "release_manifest_sha256": pin, "binding_sha256": expected_binding_sha256, "rerender": diagnostic}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--binding-sha256", help="External reviewed BINDING.json digest; required for package verification")
    parser.add_argument("--strict-rerender", action="store_true", help="Also diagnose exact rendering-byte differences")
    args = parser.parse_args(argv)
    require(not args.write or args.package is not None, "--write requires a new package path")
    require(not (args.binding_sha256 or args.strict_rerender) or args.package is not None and not args.write,
            "Binding pin and rerender diagnostic apply only to package verification")
    if args.package is not None:
        if args.write:
            result = materialize(args.package, args.release, args.manifest_sha256, args.source_commit)
        else:
            result = verify_package(args.package, args.release, args.manifest_sha256, args.source_commit,
                                    expected_binding_sha256=args.binding_sha256, strict_rerender=args.strict_rerender)
    else:
        result = derive(read_sources(args.release, args.manifest_sha256)[0])
    print(encoded(result).decode(), end="")


if __name__ == "__main__":
    main()
