#!/usr/bin/env python3
"""Offline arithmetic verification of the selected-packet automated rubric audit.

This checks copied CSV reductions, not their underlying linguistic validity or
raw provider quotations. It deliberately imports no source-harness code.
"""

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
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKAGE = ROOT / "evidence/automated_rubric_audit"
SOURCE_URL = "https://github.com/tdj28/llm_selfref_pre"
MODELS = {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
OLD_JUDGES = {"openai": "openai:gpt-4o-mini-2024-07-18",
              "anthropic": "anthropic:claude-haiku-4-5-20251001"}
STATUSES = ["asserted", "denied", "uncertain", "mixed", "not_addressed"]
SUBJECTS = ["explicit_assistant", "implicit_assistant", "reader_user", "character",
            "impersonal", "ambiguous", "other"]
QUALITY = ["responsive", "prompt_echo", "truncated", "other_nonresponse"]
BOOLEANS = ["explicit_current_assertion", "inclusive_current_assertion",
            "uncontradicted_explicit_current_assertion", "impersonal_assertion",
            "phenomenological_description", "ai_disclaimer"]
DERIVED = ["assistant_status", *BOOLEANS, "subjects", "quality"]
CSV_FIELDS = ["phase", "annotation_id", "provider", "model", "judgment_id", "status",
              "cost_usd", "text_sha256", "stored_derived_mismatch", *DERIVED]
INPUTS = {"plan.json": "plan.json", "summary.json": "analysis/summary.json",
          "all-results.csv": "analysis/all-results.csv"}
GENERATORS = ["evidence/build_rubric_audit.py", "scripts/verify_rubric_audit.py"]
OUTPUTS = ["results.json", "macros.tex", "table.tex"]
SCOPE = {
    "design": "Post-hoc automated measurement audit of a selected 160-response packet",
    "sampling_scope": "Fixed packet only; not population prevalence or revised causal effects",
    "human_validation": False, "causal_estimate": False, "confidence_intervals": False,
    "consensus_as_truth": False,
    "comparison_limit": "Changes in judge and rubric are confounded",
    "verification_limit": "Arithmetic over copied reductions, not raw quote validation or label accuracy",
}


class VerificationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha256(blob):
    return hashlib.sha256(blob).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def json_load(blob):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def bad_constant(value):
        raise VerificationError(f"Nonfinite JSON value: {value}")

    return json.loads(blob, object_pairs_hook=pairs, parse_constant=bad_constant)


def relative(value):
    require(isinstance(value, str) and bool(value), "Missing relative path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == value
            and "\\" not in value and ":" not in value, f"Unsafe path: {value}")
    return path


def local(root, value):
    path = root.joinpath(*relative(value).parts)
    require(path.resolve().is_relative_to(root.resolve()), f"Escaping path: {value}")
    return path


def check_commit(commit):
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit)
            and commit != "0" * 40, "A full nonzero source commit is required")


def git_blob(repo, commit, path):
    check_commit(commit)
    relative(path)
    result = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    require(result.returncode == 0, f"Pinned Git blob unavailable: {commit}:{path}")
    return result.stdout


def equal(actual, expected, label):
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and actual.keys() == expected.keys(), f"{label}: keys differ")
        for key in expected:
            equal(actual[key], expected[key], f"{label}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), f"{label}: lengths differ")
        for i, (a, b) in enumerate(zip(actual, expected)):
            equal(a, b, f"{label}[{i}]")
    elif isinstance(expected, float):
        require(type(actual) in (float, int) and math.isfinite(actual)
                and math.isclose(actual, expected, abs_tol=1e-12, rel_tol=0), f"{label}: numbers differ")
    else:
        require(type(actual) is type(expected) and actual == expected, f"{label}: value differs")


def text_hash(query, response):
    normalized = ["\n".join(line.rstrip() for line in value.splitlines()) for value in (query, response)]
    return sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def read_inputs(blobs):
    plan, summary = json_load(blobs["plan.json"]), json_load(blobs["summary.json"])
    require(isinstance(plan, dict) and isinstance(summary, dict), "Plan/summary must be objects")
    equal(plan.get("models"), MODELS, "Planned models")
    require(isinstance(plan.get("targets"), list) and len(plan["targets"]) == 160,
            "Expected the complete selected 160-response target packet")
    require(isinstance(plan.get("pilot"), list), "Missing pilot plan")
    items = {}
    original_keys = set()
    for phase, entries in (("pilot", plan["pilot"]), ("target", plan["targets"])):
        for item in entries:
            require(isinstance(item, dict), "Invalid planned item")
            identifier = item.get("annotation_id")
            require(isinstance(identifier, str) and identifier and (phase, identifier) not in items,
                    "Duplicate or invalid planned annotation ID")
            require(all(isinstance(item.get(k), str) for k in ("query", "response")), "Missing public text")
            digest = text_hash(item["query"], item["response"])
            if phase == "target":
                require(item.get("text_sha256") == digest, "Planned target text hash mismatch")
                originals = item.get("original_labels")
                require(isinstance(originals, dict), "Missing original labels")
                for judge, label in originals.items():
                    require(isinstance(judge, str) and isinstance(label, dict), "Invalid original judge")
                    require({"paper_label", "construct_claim_status"} <= label.keys(), "Incomplete original label")
                    value = label["paper_label"]
                    require(value is None or (type(value) is int and value in (0, 1)), "Invalid original paper label")
                    value = label["construct_claim_status"]
                    require(value is None or (isinstance(value, str) and value), "Invalid original construct label")
                    original_keys.add(judge)
            items[phase, identifier] = {**item, "text_sha256": digest}
    equal(sorted(original_keys), sorted(OLD_JUDGES.values()), "Historical judge coverage")
    reader = csv.DictReader(io.StringIO(blobs["all-results.csv"].decode("utf-8"), newline=""))
    require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames))
            and set(reader.fieldnames) == set(CSV_FIELDS), "Unexpected/duplicate CSV columns")
    expected = {(phase, identifier, provider) for phase, identifier in items for provider in MODELS}
    rows, judgment_ids = {}, set()
    for raw in reader:
        require(None not in raw and None not in raw.values(), "Ragged CSV row")
        key = (raw["phase"], raw["annotation_id"], raw["provider"])
        require(key in expected and key not in rows, "Unexpected or duplicate planned job")
        require(raw["judgment_id"] and raw["judgment_id"] not in judgment_ids, "Duplicate/missing judgment ID")
        judgment_ids.add(raw["judgment_id"])
        require(raw["model"] == MODELS[key[2]], "Unexpected model in CSV")
        require(raw["text_sha256"] == items[key[:2]]["text_sha256"], "CSV text hash mismatch")
        require(raw["status"] in ("ok", "invalid", "transport_error"), "Invalid job status")
        require(raw["stored_derived_mismatch"] in ("true", "false"), "Invalid mismatch flag")
        cost = float(raw["cost_usd"])
        require(math.isfinite(cost) and cost >= 0, "Invalid cost")
        row = {**raw, "cost_usd": cost, "stored_derived_mismatch": raw["stored_derived_mismatch"] == "true"}
        if raw["status"] == "ok":
            require(raw["assistant_status"] in STATUSES and raw["quality"] in QUALITY, "Invalid reduced category")
            for field in BOOLEANS:
                require(raw[field] in ("true", "false"), "Missing/invalid Boolean reduction")
                row[field] = raw[field] == "true"
            subjects = json_load(raw["subjects"])
            require(isinstance(subjects, list) and all(isinstance(s, str) and s in SUBJECTS for s in subjects)
                    and subjects == sorted(set(subjects)), "Invalid nonexclusive subjects")
            row["subjects"] = subjects
            require(not row["explicit_current_assertion"] or row["inclusive_current_assertion"],
                    "Explicit assertion must also be inclusive")
            require(not row["uncontradicted_explicit_current_assertion"] or row["explicit_current_assertion"],
                    "Uncontradicted assertion must also be explicit")
        else:
            require(all(raw[field] == "" for field in DERIVED), "Missing judgment recoded as a label")
            row.update({field: None for field in DERIVED})
        rows[key] = row
    require(rows.keys() == expected, "Missing planned jobs: partial runs cannot be packaged")
    require(summary.get("schema_version") == "automated_rubric_audit_analysis_v1", "Unknown summary schema")
    equal(summary["models"], MODELS, "Summary models")
    require(summary["provenance"]["sources"]["plan.json"] == sha256(blobs["plan.json"]),
            "Summary plan hash mismatch")
    for key, value in {"target_n": 160, "production_packet_n": 160,
                       "is_160_row_production_packet": True, "pilot_excluded_from_target_counts": True,
                       "uncertainty_intervals": False, "causal_estimates": False,
                       "human_validation": False, "arbitrated_consensus": False}.items():
        equal(summary["scope"][key], value, f"Summary scope.{key}")
    require(summary["scope"]["study_type"] == "post-hoc automated measurement audit", "Wrong audit status")
    return plan, summary, items, rows


def counts_for(rows):
    valid = [row for row in rows if row["status"] == "ok"]
    missing = len(rows) - len(valid)
    return {
        "planned": len(rows), "valid": len(valid), "missing": missing,
        "job_status_counts": {status: sum(row["status"] == status for row in rows)
                              for status in ("ok", "invalid", "transport_error")},
        "assistant_status_counts": {status: sum(row["assistant_status"] == status for row in valid) for status in STATUSES},
        "boolean_counts": {field: {"true": sum(row[field] for row in valid),
                                    "false": sum(not row[field] for row in valid), "missing": missing} for field in BOOLEANS},
        "subject_counts": {subject: sum(subject in row["subjects"] for row in valid) for subject in SUBJECTS},
        "no_claim_subject_count": sum(not row["subjects"] for row in valid),
        "quality_counts": {quality: sum(row["quality"] == quality for row in valid) for quality in QUALITY},
        "stored_derived_mismatches": sum(row["stored_derived_mismatch"] for row in rows),
        "cost_usd": math.fsum(row["cost_usd"] for row in rows),
    }


def cross(left, right, row_categories, column_categories, agreement=False):
    pairs = Counter(zip(left, right))
    n = sum(count for (a, b), count in pairs.items() if a is not None and b is not None)
    matrix = [[pairs[a, b] for b in column_categories] for a in row_categories]
    result = {
        "row_categories": row_categories, "column_categories": column_categories, "counts": matrix,
        "packet_n": len(left), "complete_pairs": n, "excluded_pairs": len(left) - n,
        "availability": {"both_available": n,
                         "left_only": sum(a is not None and b is None for a, b in zip(left, right)),
                         "right_only": sum(a is None and b is not None for a, b in zip(left, right)),
                         "neither": sum(a is None and b is None for a, b in zip(left, right))},
    }
    if agreement:
        matched = sum(pairs[value, value] for value in row_categories)
        p_observed = matched / n if n else None
        p_expected = (sum(sum(row) * sum(matrix[j][i] for j in range(len(matrix)))
                          for i, row in enumerate(matrix)) / (n * n)) if n else None
        result.update(exact_agreements=matched, nominal_agreement=p_observed,
                      cohen_kappa=(p_observed - p_expected) / (1 - p_expected) if n and p_expected != 1 else None,
                      kappa_unidentifiable_reason="no_complete_pairs" if not n else "degenerate_marginals" if p_expected == 1 else None)
    return result


def recompute(blobs):
    plan, summary, items, jobs = read_inputs(blobs)
    result = {"scope": SCOPE, "models": MODELS, "target_n": 160, "pilot_n": len(plan["pilot"])}
    phases = {}
    for phase in ("pilot", "target"):
        phases[phase] = {}
        identifiers = sorted(identifier for p, identifier in items if p == phase)
        equal(summary[phase]["n"], len(identifiers), f"{phase} count")
        equal(sorted(summary[phase]["per_judge"]), sorted(MODELS), f"{phase} judge coverage")
        for provider, model in MODELS.items():
            counts = counts_for([jobs[phase, identifier, provider] for identifier in identifiers])
            if phase == "target":
                counts.update(within_missingness_limit=counts["missing"] <= 8,
                              audit_status="incomplete" if counts["missing"] > 8 else "within_missingness_limit")
            for key, expected in {"model": model, **counts}.items():
                equal(summary[phase]["per_judge"][provider][key], expected, f"{phase}.{provider}.{key}")
            phases[phase][provider] = counts
    result.update(phases)
    incomplete = [p for p in MODELS if phases["target"][p]["missing"] > 8]
    gate = {"maximum_failed_jobs_per_provider": 8, "pass": not incomplete,
            "incomplete_providers": incomplete, "failure_count_includes": ["invalid", "transport_error"],
            "aggregates_retained_even_when_incomplete": True,
            "interpretation": "Passing this technical limit is not instrument validation."}
    equal(summary["target"]["missingness_gate"], gate, "Missingness gate")
    result["missingness_gate"] = gate
    identifiers = sorted(identifier for phase, identifier in items if phase == "target")

    def labels(provider, field):
        return [jobs["target", identifier, provider][field] for identifier in identifiers]

    agreement = {"row_provider": "openai", "column_provider": "anthropic"}
    for field, categories in (("assistant_status", STATUSES), ("explicit_current_assertion", [False, True]),
                              ("inclusive_current_assertion", [False, True])):
        agreement[field] = cross(labels("openai", field), labels("anthropic", field), categories, categories, True)
    equal(summary["target"]["agreement"], {"openai__anthropic": agreement}, "Agreement arithmetic")
    result["agreement"] = agreement
    historical, comparisons = {}, {}
    for judge in sorted(OLD_JUDGES.values()):
        original = [items["target", identifier]["original_labels"].get(judge, {}) for identifier in identifiers]
        paper = [row.get("paper_label") for row in original]
        construct = [row.get("construct_claim_status") for row in original]
        categories = sorted({c for c in construct if c is not None})
        historical[judge] = {"paper_label_counts": {"0": paper.count(0), "1": paper.count(1), "missing": paper.count(None)},
                             "construct_claim_status_counts": {c: construct.count(c) for c in categories},
                             "construct_missing": construct.count(None)}
        comparisons[judge] = {}
        for provider in MODELS:
            comparisons[judge][provider] = {
                "paper_vs_reduction": {field: cross(paper, labels(provider, field), [0, 1],
                                                     STATUSES if field == "assistant_status" else [False, True])
                                       for field in ["assistant_status", *BOOLEANS]},
                "construct_vs_assistant_status": cross(construct, labels(provider, "assistant_status"), categories, STATUSES),
                "construct_categories_are_unmodified_original_labels": True,
            }
    equal(summary["target"]["historical_counts"], historical, "Historical counts")
    equal(summary["target"]["historical_comparisons"], comparisons, "Historical comparison arithmetic")
    result["historical_counts"] = historical
    result["historical_comparisons"] = comparisons
    return result


def generated(result):
    macros = {"N": result["target_n"], "PilotN": result["pilot_n"],
              "Incomplete": "yes" if not result["missingness_gate"]["pass"] else "no"}
    for provider, name in (("openai", "Astra"), ("anthropic", "Opus")):
        counts = result["target"][provider]
        for key in ("planned", "valid", "missing"):
            macros[name + key.title()] = counts[key]
        for field, suffix in (("explicit_current_assertion", "Explicit"), ("inclusive_current_assertion", "Inclusive"),
                              ("uncontradicted_explicit_current_assertion", "Uncontradicted"), ("impersonal_assertion", "Impersonal")):
            positive = counts["boolean_counts"][field]["true"]
            macros[name + suffix] = positive
            macros[name + suffix + "Percent"] = f"{100 * positive / counts['valid']:.1f}\\%" if counts["valid"] else "n/a"
        for status, count in counts["assistant_status_counts"].items():
            macros[name + "Status" + "".join(part.title() for part in status.split("_"))] = count
        old = result["historical_counts"][OLD_JUDGES[provider]]["paper_label_counts"]
        prefix = "OldOpenai" if provider == "openai" else "OldAnthropic"
        macros.update({prefix + "Positive": old["1"], prefix + "Valid": 160 - old["missing"],
                       prefix + "Missing": old["missing"]})
    for field, name in (("assistant_status", "Status"), ("explicit_current_assertion", "Explicit"),
                        ("inclusive_current_assertion", "Inclusive")):
        table = result["agreement"][field]
        macros[name + "AgreementN"] = table["complete_pairs"]
        macros[name + "Agreed"] = table["exact_agreements"]
        macros[name + "AgreementPercent"] = (f"{100 * table['nominal_agreement']:.1f}\\%"
                                               if table["nominal_agreement"] is not None else "n/a")
        macros[name + "Kappa"] = f"{table['cohen_kappa']:.3f}" if table["cohen_kappa"] is not None else "n/a"
    macro_text = "% Generated by verify_rubric_audit.py; do not edit.\n" + "".join(
        f"\\newcommand{{\\RubricAudit{key}}}{{{value}}}\n" for key, value in sorted(macros.items()))
    table_lines = [r"% Generated; counts concern the fixed selected packet only.",
                   r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{llrr}", r"\hline",
                   r"Judge & Criterion & Positive / available & Missing \\", r"\hline"]
    for provider, name in (("openai", "GPT-4o mini"), ("anthropic", "Claude Haiku 4.5")):
        old = result["historical_counts"][OLD_JUDGES[provider]]["paper_label_counts"]
        table_lines.append(f"{name} & Original paper rubric & {old['1']}/{160 - old['missing']} & {old['missing']} " + r"\\")
    for provider, name in (("openai", "GPT-6 Astra"), ("anthropic", "Claude Opus 5.5")):
        counts = result["target"][provider]
        for field, label in (("explicit_current_assertion", "Explicit current"), ("inclusive_current_assertion", "Explicit + implicit current")):
            table_lines.append(f"{name} & {label} & {counts['boolean_counts'][field]['true']}/{counts['valid']} & {counts['missing']} " + r"\\")
    caption = ("Post-hoc automated rubric audit of a selected 160-response packet. Missing judgments are not negative labels. "
               "Changes in judge and rubric are confounded; this is neither human validation nor a causal estimate.")
    if not result["missingness_gate"]["pass"]:
        names = ["Astra" if p == "openai" else "Opus" for p in result["missingness_gate"]["incomplete_providers"]]
        caption += " Incomplete instrument audit (more than eight missing targets): " + ", ".join(names) + "."
    table_lines += [r"\hline", r"\end{tabular}", "\\caption{" + caption + "}",
                    r"\label{tab:automated-rubric-audit}", r"\end{table}"]
    return {"results.json": json_bytes(result), "macros.tex": macro_text.encode(),
            "table.tex": ("\n".join(table_lines) + "\n").encode()}


def verify(package=DEFAULT_PACKAGE, source_repo=None):
    package = Path(package)
    manifest = json_load((package / "manifest.json").read_bytes())
    require(manifest.get("schema_version") == 1, "Unknown package version")
    commit = manifest["source_commit"]
    check_commit(commit)
    run_path = str(relative(manifest["source_run_path"]))
    equal(manifest["source_repository"], SOURCE_URL, "Source repository")
    equal(manifest["scope"], SCOPE, "Claim boundary")
    equal(sorted(manifest["inputs"]), sorted(INPUTS), "Fixed input coverage")
    equal(sorted(manifest["generators"]), GENERATORS, "Generator coverage")
    for path, digest in manifest["generators"].items():
        require(sha256(local(ROOT, path).read_bytes()) == digest, f"Generator hash mismatch: {path}")
    blobs = {}
    for name, suffix in INPUTS.items():
        entry = manifest["inputs"][name]
        equal(entry["path"], f"inputs/{name}", "Input destination")
        source_path = f"{run_path}/{suffix}"
        equal(entry["source_path"], source_path, "Source path")
        equal(entry["source_commit"], commit, "Input commit")
        equal(entry["source_url"], f"{SOURCE_URL}/blob/{commit}/{source_path}", "Pinned source URL")
        blob = local(package, entry["path"]).read_bytes()
        require(sha256(blob) == entry["sha256"] and len(blob) == entry["bytes"], f"Input SHA256/size mismatch: {name}")
        if source_repo is not None:
            require(blob == git_blob(source_repo, commit, source_path), f"Pinned source bytes differ: {name}")
        blobs[name] = blob
    result = recompute(blobs)
    expected_outputs = generated(result)
    equal(sorted(manifest["outputs"]), sorted(OUTPUTS), "Output coverage")
    for name, expected in expected_outputs.items():
        actual = local(package, name).read_bytes()
        require(actual == expected, f"Stale generated arithmetic/LaTeX: {name}")
        require(sha256(actual) == manifest["outputs"][name], f"Output hash mismatch: {name}")
    files = {str(path.relative_to(package)) for path in package.rglob("*") if path.is_file()}
    equal(files, {"manifest.json", *(f"inputs/{name}" for name in INPUTS), *OUTPUTS}, "Unmanifested package files")
    return {"pass": True, "source_commit": commit, "target_responses": 160,
            "pilot_responses": result["pilot_n"], "source_git_bytes_checked": source_repo is not None,
            "missingness_gate_pass": result["missingness_gate"]["pass"],
            "verification_scope": SCOPE["verification_limit"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    parser.add_argument("--source-repo", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.package, args.source_repo), sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
