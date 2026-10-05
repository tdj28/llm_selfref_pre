#!/usr/bin/env python3
"""Bind the completed context/operator extensions to pinned released summaries.

Default/--check is read-only. --write refreshes the editorial binding by
regenerating only the four compact files in evidence/completed_extensions;
it never rewrites a historical release or authorizes execution.
No Git/network/model access or third-party
packages are needed. Counts and selected contrast arithmetic are checked;
bootstrap intervals are copied from frozen summaries, not recomputed. This is
not a raw-generation, judge-receipt, scientific-gate or human-validation audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import ROUND_HALF_UP, Decimal
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence/completed_extensions"
SOURCE_COMMIT = "3adc17809bf453b87e84187438470eff9661b102"
READERS = {"openai": "Astra", "anthropic": "Opus"}
INCLUSIVE = "inclusive_current_assertion"
PINS = {
    "bilingual": ("data/bilingual_llama_b1/completed_20261002", "MANIFEST.json",
        "0a2e78ef585106ac72c6ed3991394a892efc072957ce9c4f8491b27c855848af",
        "c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb", "raw/PLAN.json",
        ("analysis/analysis.json", "raw/DONE-all.json")),
    "frontier": ("data/frontier_bilingual_b1/completed_20261002", "MANIFEST.json",
        "da7468314f3334b93043af854a7890d528d93d8ddd93f0c5d2af76f9560f825b",
        "c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb", "PLAN.json",
        ("analysis/analysis.json",)),
    "qualification": ("data/instruction_state_qualification/crossed_v1_20261001", "MANIFEST.json",
        "967dc1bb65f0b1aca921009b7b012373cd77425c19d9d91b408b9333fee00bd7",
        "0acf16548f7dfe0359ce6c19bf952725572697d5", "raw/PLAN.json",
        ("analysis/decision-look12.json", "raw/DONE-all.json")),
    "operator": ("data/operator_matching/calibration_v1_20261003", "RELEASE_MANIFEST.json",
        "b8cf8300b67fdcce4d7cee8b401fd3a16ffb7377a23c823d4bc0c74964115bf9",
        "05efbfda1bb56b5a4c5b4193ffb551ba24cc060e", None,
        ("analysis/summary.json", "analysis/rates.csv", "DONE-all.json")),
    "fine": ("data/operator_matching/fine_v1_20261003", "RELEASE_MANIFEST.json",
        "ba3c49fa87a44c65c15e3aa40e8c4a53a597a3ef709131dd2bd060e553b3249a",
        "a6a45a20f65c64caf5e78286b6f4930e03eb1365", None,
        ("analysis/summary.json", "analysis/rates.csv", "DONE-all.json")),
}
OUTPUTS = ("results.json", "values.tex", "table.tex", "manifest.json")
OWN_SOURCES = ("scripts/verify_completed_extensions.py", "tests/test_completed_extensions.py",
               "paper/context_extensions.tex", "paper/operator_matching.tex")
SCOPE = {
    "source_commit": SOURCE_COMMIT,
    "editorial_binding_only": True,
    "authorizes_experiments": False,
    "source_manifest_and_selected_input_hashes_checked": True,
    "counts_and_selected_contrast_arithmetic_recomputed": True,
    "bootstrap_intervals_recomputed": False,
    "raw_generations_or_judge_receipts_reaudited": False,
    "all_release_artifact_bytes_checked": False,
    "human_validation": False,
    "description": "Selected frozen summaries, not pooled studies or a new scientific analysis",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("ascii")


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def local(root, name):
    path = PurePosixPath(name)
    require(name and not path.is_absolute() and ".." not in path.parts
            and path.as_posix() == name, "Unsafe relative path: " + name)
    target = Path(root)
    require(not target.is_symlink(), "Symlink root")
    for part in path.parts:
        target /= part
        require(not target.is_symlink(), "Symlink path: " + name)
    return target


def manifest_entries(manifest):
    files = manifest["files"]
    rows = ([{"path": name, "sha256": digest} for name, digest in files.items()]
            if isinstance(files, dict) else files)
    result = {}
    for row in rows:
        name = row["path"]
        path = PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts and name == path.as_posix()
                and name not in result and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
                "Unsafe/duplicate release entry")
        result[name] = row
    return result


def load_sources(root=ROOT):
    sources, provenance = {}, {}
    for key, (directory, filename, digest, freeze, plan_name, names) in PINS.items():
        manifest_path = directory + "/" + filename
        raw = local(root, manifest_path).read_bytes()
        require(sha(raw) == digest, "Release manifest pin changed: " + key)
        manifest = decode(raw)
        require(manifest.get("freeze_commit", manifest.get("science_freeze")) == freeze,
                "Scientific freeze changed: " + key)
        entries = manifest_entries(manifest)
        saved, inputs = {}, {}
        plan_path = directory + "/" + plan_name if plan_name else manifest["plan_path"]
        for name in (*names, "__plan__"):
            path = plan_path if name == "__plan__" else directory + "/" + name
            content = local(root, path).read_bytes()
            expected = manifest["plan_sha256"] if name == "__plan__" else entries[name]["sha256"]
            require(sha(content) == expected, "Source hash changed: " + path)
            if name != "__plan__" and "bytes" in entries[name]:
                require(len(content) == entries[name]["bytes"], "Source size changed: " + path)
            saved[name] = (list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
                           if name.endswith(".csv") else decode(content))
            inputs[path] = {"sha256": expected, "bytes": len(content)}
        sources[key] = saved
        provenance[key] = {"manifest_path": manifest_path, "manifest_sha256": digest,
                           "freeze_commit": freeze, "plan_path": plan_path,
                           "plan_sha256": manifest["plan_sha256"], "inputs": inputs}
    return sources, provenance


def one(rows, **selector):
    matches = [r for r in rows if all(r.get(k) == v for k, v in selector.items())]
    require(len(matches) == 1, "Missing/duplicate selected cell: " + repr(selector))
    return matches[0]


def close(actual, expected):
    require(type(actual) in (float, int) and math.isfinite(actual)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12), "Arithmetic differs")


def effect(row, blocks):
    interval = row["ci95"]
    require(isinstance(interval, list) and len(interval) == 2
            and all(type(x) in (int, float) and math.isfinite(x) for x in interval)
            and interval[0] <= interval[1], "Invalid frozen interval")
    require(row["planned_blocks"] == blocks, "Wrong planned block count")
    if "blocks" in row:
        require(row["status"] == "complete" and row["complete_blocks"] == blocks,
                "Incomplete bilingual contrast")
        values = row["blocks"]
        require(len(values) == len({r["block_id"] for r in values}) == blocks
                and Counter(r["family"] for r in values) == {"a": blocks // 2, "b": blocks // 2}
                and not any(r["missing_item_ids"] for r in values), "Incomplete/duplicate paired blocks")
        mean = math.fsum(r["value"] for r in values) / blocks
    else:
        require(row["observed_blocks"] == blocks and not row["incomplete_blocks"]
                and set(row["block_values"]) == {str(i) for i in range(1, blocks + 1)},
                "Incomplete frontier contrast")
        mean = math.fsum(row["block_values"].values()) / blocks
    close(row["estimate"], mean)
    return {"estimate": row["estimate"], "ci95": interval, "blocks": blocks}


def complete_cell(row, n, rate_key):
    require(row["planned"] == row["observed"] == n and row["missing"] == 0
            and type(row["positive"]) is int and 0 <= row["positive"] <= n, "Incomplete rate cell")
    close(row[rate_key], row["positive"] / n)
    return row["positive"]


def bilingual_result(saved):
    data, done = saved["analysis/analysis.json"], saved["raw/DONE-all.json"]
    inventory = data["inventory"]
    require(inventory["total_answers"] == 480 and inventory["main_answers"] == 400
            and inventory["bridge_answers"] == 80 and inventory["blocks"] == 20
            and inventory["family_blocks"] == {"a": 10, "b": 10}, "Bilingual inventory changed")
    require(done["complete"] and not done["stage_b_started"]
            and data["validation"]["raw_audit"]["generations"] == 760, "Bilingual completion changed")
    result = {"answers": inventory["total_answers"], "blocks": inventory["blocks"], "readers": {}}
    endpoints = (INCLUSIVE, "explicit_current_assertion", "paper_positive")
    for provider in READERS:
        selected = {}
        for endpoint in endpoints:
            contrasts = {}
            for language in ("en", "zh", "zh_minus_en"):
                row = one(data["effects"], provider=provider, endpoint=endpoint,
                          panel="main", contrast="self_minus_recursive:" + language)
                contrasts[language] = effect(row, 20)
            close(contrasts["zh_minus_en"]["estimate"],
                  contrasts["zh"]["estimate"] - contrasts["en"]["estimate"])
            for language in ("en", "zh"):
                counts = [complete_cell(one(data["rates"], provider=provider, endpoint=endpoint,
                          kind="main", context_language=language, output_language=language,
                          instruction=condition, transcript=condition, condition=condition), 20, "rate_observed")
                          for condition in ("self", "recursive")]
                close(contrasts[language]["estimate"], (counts[0] - counts[1]) / 20)
            selected[endpoint] = contrasts
        primary = one(data["primary"], provider=provider, endpoint=INCLUSIVE,
                      contrast="self_minus_recursive:zh_minus_en")
        require(effect(primary, 20) == selected[INCLUSIVE]["zh_minus_en"], "Primary endpoint changed")
        for component in ("instruction", "transcript"):
            selected[component] = effect(one(data["effects"], provider=provider, endpoint=INCLUSIVE,
                panel="anchor", contrast=component + "_average:en"), 20)
        result["readers"][provider] = selected
    return result


def frontier_result(saved):
    data = saved["analysis/analysis.json"]
    require(data["rows"] == 144 and data["receipt_audit"]["complete"]
            and data["receipt_audit"]["missing_slots"] == 0, "Frontier completion changed")
    result = {"answers": data["rows"], "blocks": 6, "readers": {}}
    for provider in READERS:
        models = {}
        for model in ("astra", "gpt41", "opus"):
            cells = {}
            for language in ("en", "zh"):
                cell = {}
                for endpoint in (INCLUSIVE, "explicit_current_assertion", "paper_positive"):
                    cell[endpoint] = sum(complete_cell(one(data["cells"], judge=provider, model=model,
                        language=language, endpoint=endpoint, instruction=i, transcript=t), 6, "rate")
                        for i in ("self", "history") for t in ("self", "history"))
                cell["instruction"] = effect(one(data["contrasts"], judge=provider, model=model,
                    language=language, endpoint=INCLUSIVE, contrast="instruction_effect"), 6)
                paper = {i + ":" + t: complete_cell(one(data["cells"], judge=provider, model=model,
                         language=language, endpoint="paper_positive", instruction=i, transcript=t), 6, "rate")
                         for i in ("self", "history") for t in ("self", "history")}
                for key, contrast, positives in (
                        ("paper_instruction", "instruction_effect", paper["self:self"] + paper["self:history"]
                         - paper["history:self"] - paper["history:history"]),
                        ("paper_transcript", "transcript_effect", paper["self:self"] + paper["history:self"]
                         - paper["self:history"] - paper["history:history"])):
                    cell[key] = effect(one(data["contrasts"], judge=provider, model=model,
                        language=language, endpoint="paper_positive", contrast=contrast), 6)
                    close(cell[key]["estimate"], positives / 12)
                cells[language] = cell
            models[model] = cells
        result["readers"][provider] = models
    return result


def qualification_result(saved):
    data, done = saved["analysis/decision-look12.json"], saved["raw/DONE-all.json"]
    require(data["decision"] == done["gate_decision"] == "fail" and data["n_blocks"] == 12
            and done["complete"] and not done["behavioral_qualified"] and not done["stage_b_started"],
            "Qualification failure changed")
    require(set(data["providers"]) == set(READERS), "Qualification reader inventory changed")
    result = {"answers": 4 * data["n_blocks"], "blocks": data["n_blocks"], "decision": "fail", "readers": {}}
    for provider, row in data["providers"].items():
        counts = row["counts"]["positive"]
        require(set(counts) == {i + ":" + t for i in ("history", "self") for t in ("history", "self")}
                and row["counts"]["n_complete"] == row["planned_responses"] == result["answers"],
                "Qualification cells incomplete")
        close(row["instruction_effect"]["value"],
              (counts["self:self"] + counts["self:history"] - counts["history:self"] - counts["history:history"]) / 24)
        require(set(row["reason_codes"]) == {"insufficient_upward_headroom:self", "failure_excess_at_least_0.15"},
                "Qualification failed guards changed")
        result["readers"][provider] = {"instruction_effect": row["instruction_effect"]["value"],
            "continuation_effect": (counts["self:self"] + counts["history:self"]
                                    - counts["self:history"] - counts["history:history"]) / 24,
            "upward_headroom": row["strata"]["self"]["upward_headroom"]["value"],
            "conflict_excess": row["failure_excess"]["value"], "paper_positive": counts}
    return result


def operator_result(saved, fine=False):
    data, plan = saved["analysis/summary.json"], saved["__plan__"]
    expected_steps = {"grid": 100, "zero": 5} if fine else {"grid": 640, "zero": 10, "prompt": 180, "bridge": 40}
    expected_combos = ({f"all|add|{s}" for s in range(4, 9)} if fine else
        {f"{scope}|{op}|{s}" for scope in ("all", "generated", "assistant", "second_turn_all")
         for op in ("add", "recon_add") for s in (1, 3, 10, 30)})
    require(set(data["combos"]) == expected_combos, "Operator scope/grid changed")
    rates = saved["analysis/rates.csv"]
    seen, steps = set(), Counter()
    for row in rates:
        key = tuple(row[k] for k in ("step", "combo", "feature", "sign", "system", "top_p"))
        require(key not in seen, "Duplicate operator rate cell")
        seen.add(key)
        n, positive, missing = (int(row[k]) for k in ("n", "positive", "missing"))
        require(n > 0 and missing == 0 and 0 <= positive <= n, "Incomplete operator rate cell")
        close(float(row["rate"]), positive / n)
        steps[row["step"]] += n
    require(dict(steps) == expected_steps and sum(steps.values()) == data["rows"], "Operator trial inventory changed")
    done = saved["DONE-all.json"]
    require(done["pass"] and done["rows"] == data["rows"] + 1, "Operator completion changed")
    require(len(plan["rows"]) - data["rows"] == done["not_selected"], "Conditional inventory changed")
    expected_verdict = "no_coherent_match_in_4x_to_8x" if fine else "no_combo_matched"
    require(data["verdict"] == expected_verdict, "Operator verdict changed")
    require(data["delivery"]["valid"] and not data["delivery"]["invalid_arms"], "Operator delivery invalid")
    for name, combo in data["combos"].items():
        cells = [r for r in rates if r["step"] == "grid" and r["combo"] == name]
        require(len(cells) == 4 and {r["feature"] for r in cells} == {"23893", "58667"}
                and all(int(r["n"]) == 5 for r in cells), "Incomplete operator tested cells")
        for r in cells:
            close(combo["rates"][f"{r['feature']}:{int(r['sign']):+d}"], float(r["rate"]))
        flagged = sum(int(r["flagged"]) for r in cells)
        mad = math.fsum(abs(float(r["rate"]) - data["reference"][f"{r['feature']}:{int(r['sign']):+d}"])
                        for r in cells) / 4
        close(combo["mad"], mad)
        require(combo["flagged"] == flagged and combo["trials"] == 20
                and combo["coherent"] == (flagged / 20 <= data["rules"]["flag_share_max"]), "Coherence differs")
        matches = (combo["coherent"] and mad <= data["rules"]["mad_max"]
                   and all(float(r["rate"]) >= data["rules"]["suppression_min"] for r in cells if r["sign"] == "-1"))
        require(combo["matches"] == matches and not matches, "Operator match status differs")
    holdout_rows = [r for r in plan["rows"] if r["step"] == "holdout"]
    holdout_inventory = None
    if not fine:
        require(data["held_out"] == [] and data["selected_holdout"] == [], "Holdout status changed")
        per_combo = Counter(r["combo"] for r in holdout_rows)
        require(set(per_combo) == expected_combos and set(per_combo.values()) == {80}
                and all(r["conditional"] for r in holdout_rows)
                and plan["rules"]["top_k"] == data["rules"]["top_k"] == 3,
                "Holdout conditional inventory/selection changed")
        holdout_inventory = {"slots": len(holdout_rows), "possible_combos": len(per_combo),
                             "trials_per_combo": 80, "top_k": plan["rules"]["top_k"],
                             "maximum_selected_trials": 80 * plan["rules"]["top_k"]}
        require(set(data["bridge"]) == {"none/0.9", "none/1.0", "sdk/0.9", "sdk/1.0"}, "Bridge inventory changed")
        for group in data["bridge"].values():
            for cell in group.values():
                require(cell["n"] == 10 and cell["missing"] == 0, "Incomplete bridge cell")
                close(cell["rate"], cell["positive"] / cell["n"])
    else:
        require(not holdout_rows, "Unexpected fine-ladder holdout inventory")
    return {"trials": data["rows"], "steps": dict(steps), "verdict": data["verdict"],
            "holdout_run": False, "conditional_holdout_inventory": holdout_inventory,
            "combos": data["combos"], "bridge": data.get("bridge", []), "rates": rates}


def derive(sources):
    return {"bilingual": bilingual_result(sources["bilingual"]),
            "frontier": frontier_result(sources["frontier"]),
            "qualification": qualification_result(sources["qualification"]),
            "operator": operator_result(sources["operator"]),
            "fine": operator_result(sources["fine"], fine=True)}


def pp(value):
    value = round(value * 100, 1)
    return "0" if value == 0 else f"{value:+g}"


def estimate_cells(value):
    return ["$" + pp(value["estimate"]) + "$", "$[" + ",".join(pp(v) for v in value["ci95"]) + "]$"]


def rd2(value):
    text = str(Decimal(repr(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return "0.00" if text == "-0.00" else text


def render_values(results):
    values = {"CELlamaAnswers": results["bilingual"]["answers"], "CELlamaBlocks": results["bilingual"]["blocks"],
              "CEFrontierAnswers": results["frontier"]["answers"], "CEFrontierBlocks": results["frontier"]["blocks"],
              "CEQualificationAnswers": results["qualification"]["answers"],
              "CEQualificationBlocks": results["qualification"]["blocks"],
              "CEOperatorTrials": results["operator"]["trials"], "CEFineTrials": results["fine"]["trials"],
              "CEFrontierModelAnswers": results["frontier"]["answers"] // 3,
              "CEFrontierLanguageAnswers": results["frontier"]["answers"] // 6}
    for step, name in (("grid", "Grid"), ("zero", "Zero"), ("prompt", "Defaults"), ("bridge", "Bridge")):
        values["CEOperator" + name] = results["operator"]["steps"][step]
    values["CEFineGrid"] = results["fine"]["steps"]["grid"]
    values["CEFineZero"] = results["fine"]["steps"]["zero"]
    fine_cells = [r for r in results["fine"]["rates"] if r["step"] == "grid"]
    values["CEFineZeroCells"] = sum(int(r["positive"]) == 0 for r in fine_cells)
    values["CEFineCells"] = len(fine_cells)
    positive_cells = [r for r in fine_cells if int(r["positive"]) > 0]
    require(len(positive_cells) == 1 and positive_cells[0]["scale"] == "6"
            and not results["fine"]["combos"][positive_cells[0]["combo"]]["coherent"],
            "Fine-ladder positive/coherence description changed")
    values["CEFineRemainingPositive"] = f"{positive_cells[0]['positive']}/{positive_cells[0]['n']}"
    for key, name in (("none/1.0", "NoSystem"), ("sdk/1.0", "SDKFull"), ("sdk/0.9", "SDKNucleus")):
        cell = results["operator"]["bridge"][key]["notebook"]
        values["CEBridge" + name] = f"{cell['positive']}/{cell['n']}"
    for provider, label in READERS.items():
        b = results["bilingual"]["readers"][provider]
        for component in ("instruction", "transcript"):
            values["CELlama" + label + component.title()] = pp(b[component]["estimate"])
        f = results["frontier"]["readers"][provider]
        values["CEFrontierAstra" + label + "Positive"] = sum(f["astra"][l][INCLUSIVE] for l in ("en", "zh"))
        for endpoint, name in ((INCLUSIVE, "Inclusive"), ("paper_positive", "Paper")):
            values["CEFrontierOpusChinese" + label + name] = f["opus"]["zh"][endpoint]
        q = results["qualification"]["readers"][provider]
        values["CEQualification" + label + "Instruction"] = f"{q['instruction_effect']:.3f}"
        values["CEQualification" + label + "Headroom"] = f"{q['upward_headroom']:.3f}"
        values["CEQualification" + label + "Conflict"] = f"{q['conflict_excess']:.2f}"
        values["CESwapLlama" + label + "Instruction"] = rd2(b["instruction"]["estimate"])
        values["CESwapLlama" + label + "Continuation"] = rd2(b["transcript"]["estimate"])
        values["CESwapQualification" + label + "Instruction"] = rd2(q["instruction_effect"])
        values["CESwapQualification" + label + "Continuation"] = rd2(q["continuation_effect"])
        for model, name in (("gpt41", "Gpt"), ("opus", "Opus"), ("astra", "Astra")):
            values["CESwapFrontier" + name + label + "Instruction"] = rd2(f[model]["en"]["paper_instruction"]["estimate"])
            values["CESwapFrontier" + name + label + "Continuation"] = rd2(f[model]["en"]["paper_transcript"]["estimate"])
    lines = ["% Generated by scripts/verify_completed_extensions.py --write; do not edit."]
    lines += ["\\newcommand{\\" + name + "}{" + str(value) + "}" for name, value in values.items()]
    lines += [r"\newcommand{\CEArtifact}[2]{\href{https://github.com/tdj28/llm_selfref_pre/blob/"
              + SOURCE_COMMIT + r"/#1}{#2}}"]
    return ("\n".join(lines) + "\n").encode("ascii")


def render_table(results):
    lines = ["% Generated from the two separate readers; units are percentage points.",
             r"\begin{tabular}{@{}lr@{\,}lr@{\,}l@{}}", r"\toprule",
             r"What is counted & \multicolumn{2}{c}{Astra} & \multicolumn{2}{c}{Opus 5.5}\\", r"\midrule"]
    for endpoint, label in ((INCLUSIVE, "Explicit or implicit claim (main)"),
                            ("explicit_current_assertion", "Explicit claim only (secondary)"),
                            ("paper_positive", "Paper rubric (secondary)")):
        cells = [c for p in READERS for c in estimate_cells(results["bilingual"]["readers"][p][endpoint]["zh_minus_en"])]
        lines.append(label + " & " + " & ".join(cells) + r"\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return ("\n".join(lines) + "\n").encode("ascii")


def expected_outputs(root=ROOT):
    sources, provenance = load_sources(root)
    results = derive(sources)
    outputs = {"results.json": json_bytes(results), "values.tex": render_values(results), "table.tex": render_table(results)}
    manifest = {"schema": "completed-extensions-evidence-v1", "scope": SCOPE, "sources": provenance,
                "generators_and_prose": {p: sha(local(root, p).read_bytes()) for p in OWN_SOURCES},
                "artifacts": {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in outputs.items()}}
    outputs["manifest.json"] = json_bytes(manifest)
    return outputs


def verify(root=ROOT, write=False):
    outputs = expected_outputs(root)
    directory = local(root, PACKAGE)
    if directory.exists():
        require({p.name for p in directory.iterdir()} <= set(OUTPUTS), "Unlisted compact evidence artifact")
    if write:
        directory.mkdir(parents=True, exist_ok=True)
        for name, raw in outputs.items():
            local(root, PACKAGE + "/" + name).write_bytes(raw)
    for name, raw in outputs.items():
        require(local(root, PACKAGE + "/" + name).read_bytes() == raw, "Generated evidence differs: " + name)
    return {"pass": True, "source_commit": SOURCE_COMMIT, "release_manifests": len(PINS),
            "bilingual_answers": 480, "frontier_answers": 144, "qualification_answers_reused_later": 48,
            "operator_trials": 870, "fine_trials": 105, "scope": SCOPE}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Read-only check (default)")
    group.add_argument("--write", action="store_true", help="Regenerate compact evidence only")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(write=args.write), sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
