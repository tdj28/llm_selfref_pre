#!/usr/bin/env python3
"""Verify the F01 figure receipt; stdlib only, read-only unless --write-receipt.

Portable mode checks the reviewed receipt digest, copied figures and local
summary inputs. --source-repo additionally reconstructs values from Git blobs
at PIN. Neither mode runs plotting code, bootstraps, APIs or model inference.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys

PIN = "f5e906e1737bc71bf20b642af1d698018eec82fe"
URL = "https://github.com/tdj28/llm_selfref_pre"
ROOT = Path(__file__).resolve().parents[1]
RECEIPT = "evidence/figure_values.json"
REVIEWED_SHA256 = "f1d52ea52eafdfc9cc659d80ae38b779d1e9dface1179672d75682a396f75b5d"
CAUSAL = "data/causal_transplant/confirmatory_v1_20260709/"
SAE = "data/public_sae_consciousness_gating/confirmatory_v1_20260710/"
ROLES = ["target", "control_panel_1", "control_panel_2", "control_panel_3"]
MODELS = ["anthropic:claude-haiku-4-5-20251001", "anthropic:claude-sonnet-4-5-20250929",
          "openai:gpt-4.1-2025-04-14", "openai:gpt-4o-2024-11-20"]
JUDGES = ["primary_local_llama", "openai:gpt-4o-mini-2024-07-18",
          "anthropic:claude-haiku-4-5-20251001", "three_judge_majority", "direct_answer"]
FACTORIAL = ["self_reference_main", "phenomenological_register_main", "register_minus_self"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def number(value):
    result = float(value)
    return result if math.isfinite(result) else None


def close(a, b, message):
    require((a is None and b is None) or (a is not None and b is not None
            and math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12)), message)


def one(rows, **where):
    matches = [r for r in rows if all(r[k] == v for k, v in where.items())]
    require(len(matches) == 1, f"Expected unique row: {where}")
    return matches[0]


def triplet(row, estimate="estimate", low="ci_low", high="ci_high"):
    return [number(row[k]) for k in (estimate, low, high)]


class Archive:
    def __init__(self, repo):
        self.repo, self.sources, self.cache = Path(repo), {}, {}

    def read(self, path, local_path=None):
        if path not in self.cache:
            data = subprocess.check_output(["git", "-C", str(self.repo), "show", f"{PIN}:{path}"])
            self.cache[path] = data
            self.sources[path] = {"sha256": sha(data), "bytes": len(data)}
        if local_path:
            self.sources[path]["local_path"] = local_path
        return self.cache[path]

    def csv(self, path, local_path=None):
        return list(csv.DictReader(io.StringIO(self.read(path, local_path).decode())))

    def json(self, path, local_path=None):
        return json.loads(self.read(path, local_path))

    def jsonl(self, path):
        return [json.loads(line) for line in self.read(path).splitlines() if line.strip()]


def code_receipt(archive, path, functions):
    tree = ast.parse(archive.read(path).decode())
    result = {}
    for name, required_literals in functions.items():
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        literals = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant)]
        require(all(v in literals for v in required_literals), f"Plot binding drift: {name}")
        result[name] = {"lines": [node.lineno, node.end_lineno], "checked_literals": required_literals}
    return {"source_path": path, "functions": result}


def tally_labels(archive):
    plan = archive.jsonl(SAE + "plan/confirmatory_plan.jsonl")
    generations = archive.jsonl(SAE + "generations.jsonl")
    require(len(plan) == len(generations) == 1500, "Expected 1500 planned/generated trials")
    plans = {r["trial_id"]: r for r in plan}
    require(len(plans) == 1500 and len({r["trial_id"] for r in generations}) == 1500,
            "Duplicate trial ID")
    for phase, roles in (("aggregate_literal", ROLES), ("aggregate_calibrated", ROLES[:2])):
        counts = Counter((r["analysis_role"], r["sign"]) for r in plan if r["phase"] == phase)
        require(counts == {(role, sign): 50 for role in roles for sign in ("suppression", "amplification")},
                f"Planned scale/role/sign coverage: {phase}")
    for row in generations:
        expected = plans[row["trial_id"]]
        for key in ("phase", "scale", "analysis_role", "sign", "block_id", "seed"):
            require(row[key] == expected[key], f"Plan/runtime mismatch: {key}")
    maps = {key: {} for key in JUDGES if key != "three_judge_majority"}
    for filename, fixed_key in [("local_llama_judgments.jsonl", JUDGES[0]),
                                ("external_judgments.jsonl", None),
                                ("direct_answer_labels.jsonl", "direct_answer")]:
        for row in archive.jsonl(SAE + "judging/" + filename):
            key = fixed_key or row["judge_key"]
            require(row["trial_id"] not in maps[key], "Duplicate label")
            require(row.get("paper_label") in (0, 1, None), "Invalid label")
            maps[key][row["trial_id"]] = row.get("paper_label")
    for key, labels in maps.items():
        require(set(labels) == set(plans), f"Label coverage: {key}")
    maps["three_judge_majority"] = {}
    for trial in plans:
        values = [maps[key][trial] for key in JUDGES[:3]]
        maps["three_judge_majority"][trial] = int(sum(values) >= 2) if None not in values else None
    output = []
    for judge in JUDGES:
        roles, differences = [], {}
        for role in ROLES:
            blocks = defaultdict(dict)
            for row in plan:
                if row["phase"] == "aggregate_literal" and row["analysis_role"] == role:
                    require(row["sign"] not in blocks[row["block_id"]], "Duplicate block sign")
                    blocks[row["block_id"]][row["sign"]] = maps[judge][row["trial_id"]]
            complete = {b: v for b, v in blocks.items() if len(v) == 2 and None not in v.values()}
            pairs = Counter(f"{v['suppression']}{v['amplification']}" for v in complete.values())
            diffs = {b: v["suppression"] - v["amplification"] for b, v in complete.items()}
            differences[role] = diffs
            roles.append({"role": role, "planned_blocks": len(blocks), "complete_blocks": len(complete),
                          "paired_counts_SA": {k: pairs[k] for k in ("00", "01", "10", "11")},
                          "valid_labels_by_sign": {s: sum(v.get(s) is not None for v in blocks.values())
                                                   for s in ("suppression", "amplification")},
                          "effect": sum(diffs.values()) / len(diffs) if diffs else None})
        common = set.intersection(*(set(differences[r]) for r in ROLES))
        specific = [differences["target"][b] - sum(differences[r][b] for r in ROLES[1:]) / 3
                    for b in sorted(common)]
        output.append({"judge": judge, "roles": roles, "common_blocks": len(common),
                       "specificity": sum(specific) / len(specific) if specific else None})
    return output


def build(repo):
    archive = Archive(repo)
    causal_code = code_receipt(archive, "scripts/generate_causal_figures.py", {
        "load_effects": ["level", "model", "query_id", "effect"],
        "causal_decomposition": ["indirect_experience", "self_ref_minus_history",
                                 "instruction_source_main", "transcript_source_main", "estimate", "ci_low", "ci_high"],
        "orthogonal_factorial": ["model_equal_hierarchical", "indirect_experience", "indirect_conscious", *FACTORIAL]})
    sae_code = code_receipt(archive, "experiments/exp2_sae/figure_public_sae_consciousness_gating.py", {
        "aggregate_figure": ["aggregate_effects.csv", "primary_specificity_effect", "target_minus_mean_controls", 0.96, 0.16, 0.80, 0.30, "D"],
        "judge_figure": ["target_effect", "specificity_effect", "NA", "o", "s", 0.30],
        "technical_figure": ["aggregate_literal", "aggregate_calibrated", "final", "mean_relative_hidden_delta_rms",
                             "decoder_norm_ratio", "max_abs_target_cosine", 0.20, 1.0]})
    # Analysis source is inspected for denominator/interval semantics, not executed.
    archive.read("experiments/causal_transplant/analyze_causal_transplant.py")
    archive.read("experiments/exp2_sae/analyze_public_sae_consciousness_gating.py")
    causal_manifests = [archive.json(CAUSAL + f"analysis_{judge}_paper/analysis_manifest.json")
                        for judge in ("openai", "anthropic")]
    require(all(m["bootstrap_iterations"] == 5000 for m in causal_manifests), "Causal bootstrap draws")
    sae_manifest = archive.json(SAE + "analysis/analysis_manifest.json")
    require(sae_manifest["bootstrap_draws"] == 100000, "SAE bootstrap draws")
    decomposition, factorial = [], []
    for judge in ("openai", "anthropic"):
        for kind, filename, effects in [
            ("calibration", "paper_calibration_effects.csv", ["self_ref_minus_history"]),
            ("transplant", "transplant_effects.csv", ["instruction_source_main", "transcript_source_main"]),
            ("factorial", "factorial_effects.csv", FACTORIAL)]:
            path = CAUSAL + f"analysis_{judge}_paper/{filename}"
            rows = archive.csv(path, f"evidence/inputs/causal_{judge}_{kind}.csv")
            models = ["ALL_MODELS_EQUAL_WEIGHT"] if kind == "factorial" else MODELS
            queries = ["indirect_experience", "indirect_conscious"] if kind == "factorial" else ["indirect_experience"]
            for query in queries:
                for effect in effects:
                    for model in models:
                        level = "model_equal_hierarchical" if kind == "factorial" else "model"
                        row = one(rows, level=level, query_id=query, effect=effect, model_key=model)
                        cell = {"judge": judge, "query": query, "effect": effect, "model": model,
                                "estimate_ci95": triplet(row),
                                "denominators": {k: int(row[k]) for k in ("n_models", "n_pairs", "n_clusters")},
                                "source_path": path}
                        (factorial if kind == "factorial" else decomposition).append(cell)
    aggregate = archive.csv(SAE + "analysis/aggregate_effects.csv", "evidence/inputs/sae_aggregate.csv")
    verdict = archive.json(SAE + "analysis/primary_verdict.json", "evidence/inputs/sae_verdict.json")
    aggregate_cells = []
    for role in ROLES:
        row = one(aggregate, analysis_role=role)
        aggregate_cells.append({"role": role, "planned_blocks": int(row["n_blocks_planned"]),
            "complete_blocks": int(row["n_complete_blocks"]),
            "effect_ci95": triplet(row, "suppression_minus_amplification"),
            "rates": {sign: {"positive": int(row[f"{sign}_positive"]), "n": int(row[f"{sign}_n"]),
                      "rate_wilson95": triplet(row, f"{sign}_rate", f"{sign}_wilson_low", f"{sign}_wilson_high")}
                      for sign in ("suppression", "amplification")}})
    sensitivity = archive.csv(SAE + "analysis/judge_sensitivity.csv", "evidence/inputs/sae_judges.csv")
    judge_cells = [{"judge": j, "target_ci95": triplet(one(sensitivity, judge_key=j), "target_effect", "target_ci_low", "target_ci_high"),
                    "specificity_ci95": triplet(one(sensitivity, judge_key=j), "specificity_effect", "specificity_ci_low", "specificity_ci_high"),
                    "complete_target_blocks": int(one(sensitivity, judge_key=j)["complete_target_blocks"])} for j in JUDGES]
    telemetry = archive.csv(SAE + "analysis/realized_dose_telemetry.csv")
    dose = []
    for scale in ("literal", "calibrated"):
        for role in ROLES:
            for sign in ("suppression", "amplification"):
                selected = [r for r in telemetry if r["phase"] == f"aggregate_{scale}" and r["turn"] == "final"
                            and r["scale"] == scale and r["analysis_role"] == role and r["sign"] == sign]
                require(len(selected) <= 1, "Duplicate dose row")
                dose.append({"scale": scale, "role": role, "sign": sign, "plotted": bool(selected),
                             "values": {k: number(v) for k, v in selected[0].items()
                                        if k not in ("phase", "scale", "analysis_role", "sign", "turn")} if selected else None,
                             "missing_reason": None if selected else "not included in calibrated design; no point, not zero"})
    calibration = archive.json(SAE + "plan/calibration.json")
    matching = [{"panel": panel["panel"], **{k: pair[k] for k in
                 ("target_feature_id", "control_feature_id", "decoder_norm_ratio", "max_abs_target_cosine")}}
                for panel in calibration["control_matching"]["panels"] for pair in panel["pairs"]]
    feature_metrics = {r["feature_id"]: r for r in calibration["feature_metrics"]}
    for pair in matching:
        control = feature_metrics[pair["control_feature_id"]]
        target = feature_metrics[pair["target_feature_id"]]
        close(control["decoder_norm"] / target["decoder_norm"], pair["decoder_norm_ratio"], "Matching ratio arithmetic")
        close(control["max_abs_target_cosine"], pair["max_abs_target_cosine"], "Matching cosine source")
    calibrated = archive.csv(SAE + "analysis/calibrated_aggregate_effects.csv", "evidence/inputs/sae_calibrated.csv")
    calibrated_cells = []
    for role in ROLES:
        rows = [r for r in calibrated if r["analysis_role"] == role]
        calibrated_cells.append({"role": role, "effect_ci95": triplet(rows[0], "suppression_minus_amplification") if rows else [None]*3,
                                 "complete_blocks": int(rows[0]["n_complete_blocks"]) if rows else 0,
                                 "status": "unplotted scale sensitivity" if rows else "not in calibrated design"})
    labels = tally_labels(archive)
    for key, path in [("generations", "generations.jsonl"), ("local_judgments", "judging/local_llama_judgments.jsonl"),
                      ("external_judgments", "judging/external_judgments.jsonl"), ("direct_labels", "judging/direct_answer_labels.jsonl")]:
        require(archive.sources[SAE + path]["sha256"] == sae_manifest["input_hashes"][key], "Released analysis input hash")
    for row, counts in zip(aggregate_cells, labels[0]["roles"]):
        close(row["effect_ci95"][0], counts["effect"], "Local control tally mismatch")
        for sign, bit in (("suppression", "10"), ("amplification", "01")):
            require(row["rates"][sign]["positive"] == counts["paired_counts_SA"][bit] + counts["paired_counts_SA"]["11"], "Local rate tally mismatch")
    for cell, counts in zip(judge_cells, labels):
        close(cell["target_ci95"][0], counts["roles"][0]["effect"], "Judge target tally mismatch")
        close(cell["specificity_ci95"][0], counts["specificity"], "Judge specificity tally mismatch")
        require(cell["complete_target_blocks"] == counts["roles"][0]["complete_blocks"], "Judge denominator mismatch")
    specific = verdict["primary_specificity_effect"]
    figures = {
        "causal_decomposition": {"source_path": "paper/results/causal_decomposition.png", "plot_function": "causal_decomposition", "cells": decomposition},
        "causal_factorial_effects": {"source_path": "paper/results/causal_factorial_effects.png", "plot_function": "orthogonal_factorial", "cells": factorial},
        "aggregate_target_and_controls": {"source_path": SAE + "figures/aggregate_target_and_controls.pdf", "plot_function": "aggregate_figure",
            "scale": "literal", "cells": aggregate_cells, "specificity_ci95": triplet(specific, "target_minus_mean_controls"),
            "specificity_common_blocks": specific["n_common_blocks"], "minimum_relevant_effect_line": 0.30,
            "paper_diamonds": {"suppression": 0.96, "amplification": 0.16, "difference": 0.80, "intervals": None,
                               "denominators": None, "provenance": "hard-coded plotting references; original-paper attribution is B01, not verified here"}},
        "judge_sensitivity": {"source_path": SAE + "figures/judge_sensitivity.pdf", "plot_function": "judge_figure",
            "scale": "literal", "cells": judge_cells, "minimum_relevant_effect_line": 0.30, "na_rendering": "two NA text labels at x=-0.98; no parser points or intervals"},
        "technical_dose_and_matching": {"source_path": SAE + "figures/technical_dose_and_matching.pdf", "plot_function": "technical_figure",
            "dose": dose, "matching": matching, "dose_stop_boundary_line": 0.20, "matching_norm_reference_line": 1.0,
            "intervals": None, "matching_pairs_per_panel": 6}}
    for name, figure in figures.items():
        extension = Path(figure["source_path"]).suffix
        figure["path"] = f"paper/figures/{name}{extension}"
        figure["sha256"] = sha(archive.read(figure["source_path"], figure["path"]))
    return {"schema_version": 1, "finding": "F01", "audit_date": "2026-09-29", "source_repository": URL, "source_commit": PIN,
            "verification_level": "source-code/summary check plus bounded paired-label tallies; not independent raw reanalysis",
            "bootstrap_intervals": "copied from released summaries, not recomputed",
            "interval_types": {"causal_decomposition": "95% percentile bootstrap, 5000 draws; independent conditions for calibration, paired source-text blocks for transplant; within model",
                               "causal_factorial_effects": "95% percentile bootstrap, 5000 draws; models, lexical variants, then trials; equal-model point estimate",
                               "aggregate_rates": "95% Wilson, z=1.959963984540054",
                               "aggregate_effects_and_judges": "95% percentile paired-block bootstrap, 100000 draws; seed 20260710",
                               "technical_dose_and_matching": "none: descriptive point summaries and fixed reference lines"},
            "visual_check": "all five copied figures inspected; three PDFs rendered with pdftoppm; no numerical mismatch observed",
            "plot_code": [causal_code, sae_code], "sources": archive.sources, "figures": figures,
            "supplemental": {"literal_judge_control_tallies": labels, "calibrated_effects_not_in_behavioral_figures": calibrated_cells,
                             "control_intervals": "Individual external-control CIs are not plotted or released in judge_sensitivity.csv; null here is not a zero-width CI."}}


def verify_semantics(receipt):
    require(receipt["source_commit"] == PIN, "Source pin changed")
    figs = receipt["figures"]
    require(set(figs) == {"causal_decomposition", "causal_factorial_effects", "aggregate_target_and_controls",
                          "judge_sensitivity", "technical_dose_and_matching"}, "Five-figure coverage")
    require(len(figs["causal_decomposition"]["cells"]) == 24, "Decomposition coverage")
    require(len(figs["causal_factorial_effects"]["cells"]) == 12, "Factorial coverage")
    aggregate = figs["aggregate_target_and_controls"]
    require(aggregate["scale"] == figs["judge_sensitivity"]["scale"] == "literal", "Scale pooling/drift")
    require([r["role"] for r in aggregate["cells"]] == ROLES, "Literal panel coverage")
    for row in aggregate["cells"]:
        for rate in row["rates"].values():
            close(rate["positive"] / rate["n"], rate["rate_wilson95"][0], "Rate denominator mismatch")
        close(row["rates"]["suppression"]["rate_wilson95"][0] - row["rates"]["amplification"]["rate_wilson95"][0],
              row["effect_ci95"][0], "Aggregate effect arithmetic")
    close(aggregate["cells"][0]["effect_ci95"][0] - sum(r["effect_ci95"][0] for r in aggregate["cells"][1:])/3,
          aggregate["specificity_ci95"][0], "Control-mean specificity")
    judges = figs["judge_sensitivity"]["cells"]
    require([r["judge"] for r in judges] == JUDGES, "Judge coverage/order")
    require(judges[-1]["target_ci95"] == judges[-1]["specificity_ci95"] == [None]*3
            and judges[-1]["complete_target_blocks"] == 0, "Parser NA recoded")
    dose = figs["technical_dose_and_matching"]["dose"]
    require(len(dose) == 16 and sum(r["plotted"] for r in dose) == 12, "Dose coverage")
    require(all(r["plotted"] == (r["scale"] == "literal" or r["role"] in ROLES[:2]) for r in dose), "Calibrated missing panels")
    require(len(figs["technical_dose_and_matching"]["matching"]) == 18, "Matching coverage")
    for judge, counts in zip(judges, receipt["supplemental"]["literal_judge_control_tallies"]):
        require(judge["judge"] == counts["judge"] and [r["role"] for r in counts["roles"]] == ROLES, "Tally coverage")
        for row in counts["roles"]:
            pairs = row["paired_counts_SA"]
            require(sum(pairs.values()) == row["complete_blocks"], "Paired-count denominator")
            close((pairs["10"]-pairs["01"])/row["complete_blocks"] if row["complete_blocks"] else None,
                  row["effect"], "Paired-count effect")
        close(judge["target_ci95"][0], counts["roles"][0]["effect"], "Judge target mismatch")
        close(judge["specificity_ci95"][0], counts["specificity"], "Judge specificity mismatch")


def verify(root=ROOT, source_repo=None):
    receipt = json.loads((Path(root) / RECEIPT).read_bytes())
    verify_semantics(receipt)
    require(sha(encoded(receipt)) == REVIEWED_SHA256, "Reviewed receipt changed; re-audit required")
    local_checks = 0
    for path, source in receipt["sources"].items():
        if "local_path" in source:
            data = (Path(root) / source["local_path"]).read_bytes()
            require(sha(data) == source["sha256"], f"Copied input/figure hash mismatch: {path}")
            local_checks += 1
    if source_repo:
        expected = build(source_repo)
        require(encoded(expected) == encoded(receipt), "Pinned source/summary reconstruction differs")
    return {"figures": 5, "local_hash_checks": local_checks, "pinned_reconstruction": bool(source_repo),
            "independent_raw_reanalysis": False, "bootstrap_recomputation": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-repo", type=Path)
    parser.add_argument("--write-receipt", action="store_true", help="Maintainer-only: write this new receipt, no other artifacts")
    args = parser.parse_args()
    try:
        if args.write_receipt:
            require(args.source_repo is not None, "Writing requires pinned source repo")
            receipt = build(args.source_repo)
            verify_semantics(receipt)
            data = encoded(receipt)
            (args.root / RECEIPT).write_bytes(data)
            print(f"Receipt SHA256: {sha(data)}")
        else:
            print("PASS: " + json.dumps(verify(args.root, args.source_repo), sort_keys=True))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
