#!/usr/bin/env python3
"""Verify the bounded evidence ledger, not every statistic in the source study."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import sys

PIN = "f5e906e1737bc71bf20b642af1d698018eec82fe"
SOURCE_URL = "https://github.com/tdj28/llm_selfref_pre"
ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-12


def wilson_interval(successes, n, confidence=0.95):
    require(isinstance(successes, int) and isinstance(n, int) and n > 0 and 0 <= successes <= n,
            "invalid binomial counts")
    require(0 < confidence < 1, "invalid confidence level")
    z = statistics.NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / n
    denominator = 1 + z*z/n
    center = (p + z*z/(2*n)) / denominator
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return max(0.0, center-radius), min(1.0, center+radius)


def newcombe_independent(left_positive, left_n, right_positive, right_n, confidence=0.95):
    """Post-hoc unpaired Wilson-score hybrid CI; no continuity correction."""
    left_low, left_high = wilson_interval(left_positive, left_n, confidence)
    right_low, right_high = wilson_interval(right_positive, right_n, confidence)
    left, right = left_positive/left_n, right_positive/right_n
    difference = left-right
    return {"estimate": difference,
            "ci_low": round(max(-1.0, difference-math.hypot(left-left_low, right_high-right)), 12),
            "ci_high": round(min(1.0, difference+math.hypot(left_high-left, right-right_low)), 12),
            "self_positive": left_positive, "self_n": left_n,
            "history_positive": right_positive, "history_n": right_n}
REQUIRED_INPUTS = {
    *(f"causal_{judge}_{design}" for judge in ("openai", "anthropic") for design in ("calibration", "factorial", "transplant")),
    "agreement_paper", "agreement_construct", "sae_verdict", "sae_aggregate", "sae_individual",
    "sae_calibrated", "gemma_verdict", "lexical_recovery", "paraphrase_contrasts",
    "semantic_differences", "paradox_scores", "paradox_rubrics",
    "causal_openai_rates", "causal_anthropic_rates", "causal_openai_query", "causal_anthropic_query",
    "sae_judges", "gemma_baseline", "gemma_judges", "semantic_similarity",
    "jlens_v1_detector", "jlens_v1_semantics", "jlens_v1_features", "jlens_v2_gate",
}
REQUIRED_CLAIMS = {
    *(f"causal_{design}_{judge}_{query}" for design in ("calibration", "factorial", "transplant")
      for judge in ("openai", "anthropic") for query in ("indirect_conscious", "indirect_experience")),
    "judge_agreement_paper", "judge_agreement_construct", "sae_primary_target", "sae_primary_specificity",
    "sae_calibrated_target", "sae_calibrated_control_panel_1", "sae_literal_all_panels",
    "sae_individual_all_six", "sae_verdict", "gemma_primary_target", "gemma_primary_specificity",
    "gemma_verdict", "semantics_neutral_transplant", "semantics_cue_ablation",
    "semantics_paraphrase_all_contrasts", "exploratory_gpt4o_semantic_all_controls",
    "exploratory_gpt4o_paradox_all_scores", "exploratory_gpt4o_paradox_rubric_sensitivity",
    "causal_calibration_rates_openai", "causal_calibration_rates_anthropic",
    "causal_query_interaction_openai", "causal_query_interaction_anthropic",
    "sae_judge_sensitivity", "gemma_baseline_all_judges", "gemma_primary_all_judges",
    "exploratory_gpt4o_semantic_all_means", "jlens_v1_poststate_attribution_all_controls",
    "jlens_v1_paired_semantics_all_controls", "jlens_v1_paired_reference_all_features", "jlens_v2_failed_replay_gate",
    "posthoc_calibration_newcombe_openai", "posthoc_calibration_newcombe_anthropic",
}


class VerificationError(ValueError):
    """Evidence is absent, ambiguous, inconsistent, or different from its pin."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def relative_path(value):
    require(isinstance(value, str) and value, "empty/non-string path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and
            str(path) == value and "\\" not in value, f"unsafe path: {value}")
    return path


def local_path(root, value):
    path = root.joinpath(*relative_path(value).parts)
    require(path.resolve().is_relative_to(root.resolve()), f"escaping path: {value}")
    return path


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise VerificationError(f"nonfinite JSON number: {value}")


def json_load(data):
    return json.loads(data, object_pairs_hook=no_duplicate_keys,
                      parse_constant=reject_constant)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def read_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
    require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames),
            "missing/duplicate CSV header")
    rows = list(reader)
    require(all(None not in row and None not in row.values() for row in rows),
            "ragged CSV row")
    return rows, reader.fieldnames


def equal(actual, expected, label, *, approximate=False):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(),
                f"{label}: key mismatch")
        for key in expected:
            equal(actual[key], expected[key], f"{label}.{key}", approximate=approximate)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected),
                f"{label}: length mismatch")
        for i, (left, right) in enumerate(zip(actual, expected)):
            equal(left, right, f"{label}[{i}]", approximate=approximate)
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        require(isinstance(actual, (int, float)) and not isinstance(actual, bool)
                and math.isfinite(actual) and math.isfinite(expected),
                f"{label}: nonnumeric/nonfinite value")
        matched = math.isclose(actual, expected, rel_tol=0, abs_tol=TOLERANCE) if approximate else actual == expected
        require(matched, f"{label}: {actual!r} != {expected!r}")
    else:
        require(type(actual) is type(expected) and actual == expected,
                f"{label}: {actual!r} != {expected!r}")


def number(value):
    result = float(value)
    require(math.isfinite(result), f"nonfinite number: {value}")
    return result


def extract(record, fields):
    result = {}
    for name, spec in fields.items():
        value = record
        for key in spec["path"]:
            value = value[key]
        kind = spec.get("type", "number")
        if kind == "number":
            value = number(value)
        elif kind == "nullable_number":
            value = None if value in ("", "nan") else number(value)
        elif kind == "integer":
            numeric = number(value)
            require(numeric.is_integer(), f"{name}: non-integer")
            value = int(numeric)
        elif kind == "string":
            require(isinstance(value, str), f"{name}: not a string")
        elif kind == "boolean":
            require(isinstance(value, bool), f"{name}: not a boolean")
        else:
            raise VerificationError(f"unknown field type: {kind}")
        result[name] = value
    return result


def evaluate(recipe, inputs):
    data = inputs[recipe["input"]]
    if recipe["op"] == "independent_newcombe":
        require(recipe["query"] == "indirect_experience" and recipe["confidence"] == 0.95,
                "unexpected boundary-sensitivity endpoint")
        selected = [r for r in data if r["query_id"] == recipe["query"]]
        grouped = {}
        for row in selected:
            key = (row["model_key"], row["instruction_cell"])
            require(key not in grouped, "duplicate calibration cell")
            n = int(row["n_labeled"])
            positive = number(row["positive_rate"]) * n
            require(abs(positive - round(positive)) < TOLERANCE, "rate does not recover integer count")
            grouped[key] = (round(positive), n)
        require(len(grouped) == 8, "boundary sensitivity requires all eight calibration cells")
        return {model: newcombe_independent(*grouped[model, "paper_self_ref"],
                                           *grouped[model, "paper_history"], recipe["confidence"])
                for model in sorted({r["model_key"] for r in selected})}
    if recipe["op"] == "json_fields":
        return extract(data, recipe["fields"])
    require(recipe["op"] in {"csv_row", "csv_rows"}, "unknown recipe operation")
    selected = [row for row in data if all(row[k] == v for k, v in recipe.get("where", {}).items())]
    if recipe["op"] == "csv_row":
        require(len(selected) == 1, f"{recipe['input']}: selector matched {len(selected)} rows, expected one")
        return extract(selected[0], recipe["fields"])
    require(len(selected) == recipe["count"], f"{recipe['input']}: incomplete selected rows")
    keys = recipe["key"]
    result = {}
    for row in selected:
        key = "/".join(row[k] for k in keys)
        require(key not in result, f"{recipe['input']}: duplicate selection key {key}")
        result[key] = extract(row, recipe["fields"])
    return dict(sorted(result.items()))


def git_blob(repo, path):
    relative_path(path)
    process = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{PIN}:{path}"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    require(process.returncode == 0, f"pinned Git blob unavailable: {PIN}:{path}")
    return process.stdout


def arithmetic_checks(inputs):
    """Recompute only identified deterministic relations, never resample a CI."""
    checks = 0

    def check(left, right, label):
        nonlocal checks
        equal(left, right, label, approximate=True)
        checks += 1

    for judge in ("openai", "anthropic"):
        for design in ("calibration", "factorial", "transplant"):
            rows = inputs[f"causal_{judge}_{design}"]
            for row in rows:
                if row["level"] == "model_equal_hierarchical":
                    group = [r for r in rows if r["level"] == "model" and
                             r["query_id"] == row["query_id"] and r["effect"] == row["effect"]]
                    require(len(group) == 4, "causal aggregate must retain four models")
                    check(statistics.mean(number(r["estimate"]) for r in group),
                          number(row["estimate"]), f"{judge}/{design}: model-equal mean")
            if design != "calibration":
                terms = ("phenomenological_register_main", "self_reference_main", "register_minus_self") if design == "factorial" else (
                    "instruction_source_main", "transcript_source_main", "instruction_minus_transcript")
                lookup = {(r["model_key"], r["query_id"], r["effect"]): number(r["estimate"]) for r in rows}
                for model, query in {(r["model_key"], r["query_id"]) for r in rows}:
                    check(lookup[model, query, terms[0]] - lookup[model, query, terms[1]],
                          lookup[model, query, terms[2]], f"{judge}/{design}: contrast identity")

    for task in ("paper", "construct"):
        for row in inputs[f"agreement_{task}"]:
            n = number(row["n_complete"])
            check(n + number(row["n_missing_either"]), number(row["n_rows"]), "agreement missingness")
            check(1 - number(row["n_disagreements"]) / n, number(row["agreement"]), "agreement from counts")
            # Construct kappa is multicategory: positive marginals alone are insufficient.
            if task == "paper":
                a, b = number(row["judge_a_positive_rate"]), number(row["judge_b_positive_rate"])
                chance = a * b + (1-a) * (1-b)
                kappa = (number(row["agreement"]) - chance) / (1-chance) if chance < 1 else 1.0
                check(kappa, number(row["cohen_kappa"]), "binary kappa")

    sae = inputs["sae_verdict"]
    effects = {}
    for row in inputs["sae_aggregate"]:
        for side in ("suppression", "amplification"):
            check(number(row[f"{side}_positive"]) / number(row[f"{side}_n"]),
                  number(row[f"{side}_rate"]), "SAE rate from counts")
        effect = number(row["suppression_rate"]) - number(row["amplification_rate"])
        check(effect, number(row["suppression_minus_amplification"]), "SAE endpoint subtraction")
        effects[row["analysis_role"]] = effect
    check(effects["target"], sae["primary_target_effect"]["suppression_minus_amplification"], "SAE target across files")
    check(effects["target"] - statistics.mean(effects[f"control_panel_{i}"] for i in (1, 2, 3)),
          sae["primary_specificity_effect"]["target_minus_mean_controls"], "SAE all-panel specificity")
    for row, released in zip(inputs["sae_calibrated"], sae["calibrated_sensitivity"]):
        for key in ("ci_low", "ci_high", "suppression_minus_amplification", "n_complete_blocks"):
            check(number(row[key]), released[key], "SAE calibrated cross-file consistency")
        equal(row["analysis_role"], released["analysis_role"], "SAE calibrated role")

    gemma = inputs["gemma_verdict"]
    roles = gemma["primary_role_effects"]
    require(set(roles) == {"deception_roleplay", "hedging_refusal", "subjective_self_report",
                           "matched_control_1", "matched_control_2", "matched_control_3"}, "missing Gemma role")
    for role, row in roles.items():
        for side in ("left", "right"):
            check(row[f"{side}_positive"] / row[f"{side}_n"], row[f"{side}_rate"], f"Gemma {role} rate")
        check(row["left_rate"] - row["right_rate"], row["effect"], f"Gemma {role} effect")
        check((row["discordant_positive"] - row["discordant_negative"]) / row["n_complete_blocks"],
              row["effect"], f"Gemma {role} discordant effect")
    check(gemma["primary_target_effect"], roles["deception_roleplay"], "Gemma target role identity")
    check(roles["deception_roleplay"]["effect"] - statistics.mean(roles[f"matched_control_{i}"]["effect"] for i in (1, 2, 3)),
          gemma["primary_specificity_effect"]["target_minus_mean_controls"], "Gemma all-panel specificity")
    for name, verdict in (("SAE", sae), ("Gemma", gemma)):
        require(verdict["primary_target_effect"]["ci_high"] < verdict["minimum_relevant_effect"],
                f"{name}: released nonreplication bound no longer holds")

    lexical = inputs["lexical_recovery"]
    check(lexical["neutral_cue_transplant_recovery_ci_low"] > lexical["lexical_entanglement_threshold"],
          lexical["neutral_transplant_crosses_threshold"], "lexical transplant threshold")
    check(lexical["cue_ablation_removal_ci_low"] > lexical["lexical_entanglement_threshold"],
          lexical["ablation_crosses_threshold"], "lexical ablation threshold")
    for row in inputs["semantic_differences"]:
        check(number(row["reference_mean_pairwise_cosine"]) - number(row["control_mean_pairwise_cosine"]),
              number(row["difference"]), "semantic mean subtraction")
    scores = {(r["judge_task"], r["condition"]): number(r["mean_score"]) for r in inputs["paradox_scores"]}
    for row in inputs["paradox_rubrics"]:
        for task in ("paradox_neutral", "paradox_self_awareness"):
            check(scores[task, row["condition"]], number(row[task]), "paradox rubric cross-file mean")
        check(number(row["paradox_neutral"]) - number(row["paradox_self_awareness"]),
              number(row["neutral_minus_self_awareness"]), "paradox rubric subtraction")
    return checks


def limited_raw_checks(raw, inputs):
    """Recompute agreement and paradox means/SDs; not a full independent audit."""
    def rows(name):
        return [json_load(line) for line in raw[name].splitlines() if line.strip()]

    checks = 0
    outcomes = rows("causal_outcomes")
    require(len({r["trial_id"] for r in outcomes}) == len(outcomes), "duplicate raw trial")
    judges = ("openai:gpt-4o-mini-2024-07-18", "anthropic:claude-haiku-4-5-20251001")
    for task in ("paper", "construct"):
        labels = {}
        for row in rows(f"causal_{task}_judgments"):
            if row["task"] == task and row["judge_key"] in judges:
                key = (row["trial_id"], row["judge_key"])
                # The release analysis explicitly uses the last available label.
                value = row.get("paper_label" if task == "paper" else "claim_status")
                if value is not None:
                    labels[key] = value
        for released in inputs[f"agreement_{task}"]:
            selected = [r for r in outcomes if all(not released[k] or r[k] == released[k]
                        for k in ("phase", "model_key", "query_id"))]
            paired = [(labels.get((r["trial_id"], judges[0])), labels.get((r["trial_id"], judges[1]))) for r in selected]
            complete = [(a, b) for a, b in paired if a is not None and b is not None]
            n = len(complete)
            require(n > 0, "empty raw agreement stratum")
            left, right = Counter(a for a, _ in complete), Counter(b for _, b in complete)
            agreement = sum(a == b for a, b in complete) / n
            chance = sum(left[k] * right[k] for k in left.keys() | right.keys()) / n**2
            positive, negative = (1, 0) if task == "paper" else ("affirm", "deny")

            def jaccard(label):
                union = sum(a == label or b == label for a, b in complete)
                return sum(a == label and b == label for a, b in complete) / union if union else 1.0

            computed = {"n_rows": len(selected), "n_complete": n, "n_missing_either": len(selected)-n,
                        "n_disagreements": sum(a != b for a, b in complete), "agreement": agreement,
                        "cohen_kappa": (agreement-chance)/(1-chance) if chance < 1 else 1.0,
                        "judge_a_positive_rate": left[positive]/n, "judge_b_positive_rate": right[positive]/n,
                        "positive_agreement": jaccard(positive), "negative_agreement": jaccard(negative)}
            for key, value in computed.items():
                equal(value, number(released[key]), f"raw {task} {key}", approximate=True)
                checks += 1
    for task in ("neutral", "self_awareness"):
        judged = rows(f"paradox_{task}")
        for released in inputs["paradox_scores"]:
            if released["judge_task"] != f"paradox_{task}":
                continue
            values = [number(r["paradox_score"]) for r in judged if r["condition"] == released["condition"]
                      and r.get("paradox_score") is not None and r["paradox_judge_task"] == released["judge_task"]]
            for key, value in {"n": len(values), "mean_score": statistics.mean(values), "sd_score": statistics.stdev(values)}.items():
                equal(value, number(released[key]), f"raw paradox {key}", approximate=True)
                checks += 1
    return checks


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, value


def tex_escape(value):
    mapping = {"\\": r"\textbackslash{}", "_": r"\_", "%": r"\%", "&": r"\&",
               "#": r"\#", "$": r"\$", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(mapping.get(c, c) for c in str(value))


def display(value):
    if value is None:
        return "NA"
    if isinstance(value, float):
        result = f"{value:.4f}".rstrip("0").rstrip(".")
        return "0" if result == "-0" else result
    return str(value).lower() if isinstance(value, bool) else str(value)


def generated_outputs(manifest, values):
    macros = ["% Generated by scripts/verify_evidence.py --write-generated; do not edit.",
              "% Display floats rounded to four decimal places; exact values in headlines.json.",
              r"\providecommand{\EvidenceValue}[2]{\csname Evidence@#1.#2\endcsname}"]
    table = ["% Generated, selected scalar headline rows only; intervals are released 95% CIs.",
             "% Claim IDs printed with spaces to allow line wrapping; macro keys retain underscores.",
             r"\begin{tabular}{p{0.58\linewidth}rrr}", r"Claim & Estimate & CI low & CI high \\", r"\hline"]
    for claim in manifest["claims"]:
        key, value = claim["id"], values[claim["id"]]
        for field, scalar in flatten(value):
            require(re.fullmatch(r"[A-Za-z0-9_:./-]+", key + "." + field) is not None, "unsafe TeX macro key")
            macros.append(r"\expandafter\def\csname Evidence@" + key + "." + field + r"\endcsname{" + tex_escape(display(scalar)) + "}")
        if all(k in value for k in ("estimate", "ci_low", "ci_high")):
            table.append(tex_escape(key.replace("_", " ")) + " & " + " & ".join(display(value[k]) for k in ("estimate", "ci_low", "ci_high")) + r" \\")
    table.append(r"\end{tabular}")
    return {"evidence/headlines.json": json_bytes({"source_commit": PIN, "verification_level": "summary_values_with_bounded_arithmetic", "claims": values}),
            "evidence/headline_macros.tex": ("\n".join(macros)+"\n").encode(),
            "evidence/headline_table.tex": ("\n".join(table)+"\n").encode()}


NUMBER_TOKEN = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def normalized_tex(text):
    return " ".join(re.sub(r"(?<!\\)%[^\n]*", "", text).split())


def binding_value(expression, values, inputs):
    if "constant" in expression:
        return number(expression["constant"])
    if "claim" in expression:
        value = values[expression["claim"]]
    elif "input" in expression:
        value = inputs[expression["input"]]
    else:
        arguments = [binding_value(a, values, inputs) for a in expression["args"]]
        op = expression["op"]
        require(op in {"add", "subtract", "multiply", "divide"} and len(arguments) == 2,
                "unknown binding operation")
        left, right = arguments
        if op == "divide":
            require(right != 0, "zero binding denominator")
            return left / right
        if op == "add":
            return left + right
        return left - right if op == "subtract" else left * right
    for key in expression["path"]:
        value = value[key]
    return number(value) * expression.get("scale", 1)


def check_manuscript_bindings(root, values, inputs, source_repo=None):
    ledger = json_load((root / "evidence/manuscript_bindings.json").read_bytes())
    equal(ledger["schema_version"], 1, "manuscript binding schema")
    equal(ledger["source_commit"], PIN, "manuscript source pin")
    equal(ledger["document"], "paper/main.tex", "bound manuscript")
    text = normalized_tex(local_path(root, ledger["document"]).read_text(encoding="utf-8"))
    checked = 0
    ids = set()
    for entry in ledger["numbers"]:
        require(entry["id"] not in ids, "duplicate manuscript binding ID")
        ids.add(entry["id"])
        excerpt = normalized_tex(entry.get("prefix", "") + entry["text"])
        require(entry["occurrences"] > 0 and text.count(excerpt) == entry["occurrences"],
                f"manuscript drift or missing passage: {entry['id']}")
        tokens = NUMBER_TOKEN.findall(entry["text"])
        require(len(tokens) == len(entry["values"]), f"{entry['id']}: unbound numeric token")
        for token, expression in zip(tokens, entry["values"]):
            actual = number(token.replace(",", ""))
            expected = binding_value(expression, values, inputs)
            places = len(token.split(".")[1]) if "." in token else None
            tolerance = 0.5 * 10**(-places) + TOLERANCE if places is not None else TOLERANCE
            require(abs(actual-expected) <= tolerance,
                    f"{entry['id']}: manuscript {token} does not round from evidence {expected}")
            checked += entry["occurrences"]
    require(len(ids) == ledger["binding_count"], "manuscript binding count")
    for entry in ledger["figures"]:
        equal(entry["source_commit"], PIN, "figure pin")
        equal(entry["source_url"], f"{SOURCE_URL}/blob/{PIN}/{entry['source_path']}", "figure URL")
        data = local_path(root, entry["path"]).read_bytes()
        equal(sha256(data), entry["sha256"], f"figure hash {entry['path']}")
        if source_repo is not None:
            equal(git_blob(source_repo, entry["source_path"]), data, "pinned figure bytes")
    return {"passages": len(ids), "numeric_occurrences": checked, "pinned_figures": len(ledger["figures"])}


def verify(root=ROOT, source_repo=None, write_generated=False, check_manuscript=True):
    root = Path(root).resolve()
    manifest = json_load((root / "evidence/provenance.json").read_bytes())
    equal(manifest["schema_version"], 1, "manifest schema")
    equal(manifest["source_commit"], PIN, "full source commit")
    equal(manifest["source_repository"], SOURCE_URL, "source repository")
    equal(sorted(g["path"] for g in manifest["generators"]),
          ["evidence/build_bindings.py", "evidence/build_package.py", "scripts/verify_evidence.py"], "required generators")
    for generator in manifest["generators"]:
        equal(sha256(local_path(root, generator["path"]).read_bytes()), generator["sha256"], "generator hash")
    require(len(manifest["inputs"]) == manifest["input_count"], "input count mismatch")
    inputs, input_ids, paths = {}, set(), set()
    for entry in manifest["inputs"]:
        key = entry["id"]
        require(key not in input_ids and entry["path"] not in paths, "duplicate input ID/path")
        input_ids.add(key)
        paths.add(entry["path"])
        equal(entry["source_commit"], PIN, "input commit")
        relative_path(entry["source_path"])
        require(entry["path"].startswith("evidence/inputs/"), "input outside evidence/inputs")
        equal(entry["source_url"], f"{SOURCE_URL}/blob/{PIN}/{entry['source_path']}", "source URL")
        data = local_path(root, entry["path"]).read_bytes()
        equal(len(data), entry["bytes"], f"{key} size")
        equal(sha256(data), entry["sha256"], f"{key} SHA256")
        if source_repo is not None:
            equal(git_blob(source_repo, entry["source_path"]), data, f"{key} pinned blob bytes")
        if entry["format"] == "csv":
            rows, columns = read_csv(data)
            equal(columns, entry["columns"], f"{key} columns")
            equal(len(rows), entry["row_count"], f"{key} row count")
            if entry.get("row_key"):
                keys = [tuple(r[k] for k in entry["row_key"]) for r in rows]
                require(len(set(keys)) == len(keys), f"{key} duplicate row key")
            inputs[key] = rows
        else:
            require(entry["format"] == "json", "unknown input format")
            inputs[key] = json_load(data)
    actual_paths = {p.relative_to(root).as_posix() for p in (root / "evidence/inputs").rglob("*") if p.is_file()}
    equal(sorted(actual_paths), sorted(paths), "unmanifested or missing input file")
    equal(sorted(inputs), sorted(REQUIRED_INPUTS), "required input coverage")
    values = {}
    for claim in manifest["claims"]:
        key = claim["id"]
        require(key not in values, f"duplicate claim ID: {key}")
        require(claim["verification_level"] == "summary_value", f"{key}: unsupported verification scope")
        expected_status = "failed_registered_gate" if key == "jlens_v2_failed_replay_gate" else (
            "exploratory" if key.startswith("exploratory_") else (
            "reliability_diagnostic" if key.startswith("judge_agreement_") else "prospectively_frozen"))
        if key.startswith("posthoc_") or key == "jlens_v1_paired_reference_all_features":
            expected_status = "posthoc_sensitivity"
        equal(claim["study_status"], expected_status, f"{key} study status")
        require(claim["scope"] and claim["uncertainty"], f"{key}: missing interpretation boundary")
        value = evaluate(claim["recipe"], inputs)
        equal(value, claim["expected"], key)
        values[key] = value
    equal(sorted(values), manifest["required_claim_ids"], "required claim coverage")
    equal(sorted(values), sorted(REQUIRED_CLAIMS), "fixed claim coverage")
    equal(len(values), manifest["claim_count"], "claim count")
    arithmetic = arithmetic_checks(inputs)
    raw_count = 0
    if source_repo is not None:
        raw = {}
        for entry in manifest["optional_raw_inputs"]:
            equal(entry["source_commit"], PIN, "raw source commit")
            equal(entry["source_url"], f"{SOURCE_URL}/blob/{PIN}/{entry['source_path']}", "raw source URL")
            data = git_blob(source_repo, entry["source_path"])
            equal(len(data), entry["bytes"], "raw size")
            equal(sha256(data), entry["sha256"], "raw SHA256")
            require(entry["id"] not in raw, "duplicate raw ID")
            raw[entry["id"]] = data
        raw_count = limited_raw_checks(raw, inputs)
    if check_manuscript:
        equal(sha256((root / "evidence/manuscript_bindings.json").read_bytes()),
              manifest["manuscript_bindings_sha256"], "manuscript binding ledger hash")
        manuscript = check_manuscript_bindings(root, values, inputs, source_repo)
    else:
        manuscript = "not checked by maintainer build"
    for path, data in generated_outputs(manifest, values).items():
        output = local_path(root, path)
        if write_generated:
            output.write_bytes(data)
        else:
            require(output.exists() and output.read_bytes() == data, f"stale generated output: {path}")
    return {"inputs": len(inputs), "claims": len(values), "arithmetic_checks": arithmetic,
            "pinned_blob_check": source_repo is not None, "limited_raw_field_checks": raw_count,
            "independent_raw_audit": "not performed", "bootstrap_intervals": "released-summary verification only",
            "manuscript_headline_bindings": manuscript}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="companion checkout root")
    parser.add_argument("--source-repo", type=Path, help="optional local source Git repo containing the pinned commit")
    parser.add_argument("--write-generated", action="store_true", help="regenerate only evidence/headline outputs after checks pass")
    parser.add_argument("--verify", action="store_true", help="explicit spelling of the default read-only mode")
    args = parser.parse_args(argv)
    if args.verify and args.write_generated:
        parser.error("--verify and --write-generated are mutually exclusive")
    try:
        result = verify(args.root, args.source_repo, args.write_generated)
    except (VerificationError, OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
