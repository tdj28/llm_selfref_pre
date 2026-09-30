"""Descriptive, packet-bounded analysis of the frozen automated rubric audit.

Run with ``python -m experiments.automated_rubric_audit.analyze RUN_DIR``.
Only derived artifacts in RUN_DIR/analysis are written. No response generation,
condition linkage, consensus adjudication, confidence intervals, or inference
to a population beyond the supplied packet is performed.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from . import common
from .common import MODELS, SCHEMA, STATUSES, SUBJECTS


PHASES = ("pilot", "target")
JOB_STATUSES = ("ok", "invalid", "transport_error")
BOOLEAN_FIELDS = (
    "explicit_current_assertion",
    "inclusive_current_assertion",
    "uncontradicted_explicit_current_assertion",
    "impersonal_assertion",
    "phenomenological_description",
    "ai_disclaimer",
)
DERIVED_FIELDS = ("assistant_status", *BOOLEAN_FIELDS, "subjects", "quality")
QUALITY = SCHEMA["properties"]["quality"]["enum"]
FIGURE_STEM = "packet_label_comparison"
FIGURE_SIZE = (11.0, 7.5)
FIGURE_DPI = 300
MAX_FAILED_TARGET_JOBS = 8


def _count(values: list[Any], categories: list[Any] | tuple[Any, ...]) -> dict:
    observed = Counter(values)
    return {str(category).lower() if isinstance(category, bool) else str(category):
            observed[category] for category in categories}


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_inputs(plan: dict, raw_rows: list[dict]) -> tuple[dict, dict]:
    """Validate the full job grid before producing any analysis artifacts."""
    _expect(isinstance(plan, dict), "Plan must be an object")
    items: dict[tuple[str, str], dict] = {}
    for phase, key in (("pilot", "pilot"), ("target", "targets")):
        _expect(isinstance(plan.get(key), list), f"Plan requires a {key} list")
        for item in plan[key]:
            _expect(isinstance(item, dict), "Planned item must be an object")
            identifier = item.get("annotation_id")
            _expect(isinstance(identifier, str) and bool(identifier), "Invalid annotation_id")
            _expect((phase, identifier) not in items, f"Duplicate planned item: {phase}/{identifier}")
            _expect(all(isinstance(item.get(k), str) for k in ("query", "response")),
                    f"Missing query/response: {identifier}")
            if phase == "target":
                _expect(item.get("text_sha256") == common.text_key(item["query"], item["response"]),
                        f"Text hash mismatch: {identifier}")
                originals = item.get("original_labels")
                _expect(isinstance(originals, dict), f"Missing original_labels: {identifier}")
                for judge, original in originals.items():
                    _expect(isinstance(judge, str) and bool(judge) and isinstance(original, dict),
                            f"Invalid original labels: {identifier}")
                    _expect({"paper_label", "construct_claim_status"} <= original.keys(),
                            f"Incomplete original labels: {identifier}/{judge}")
                    paper = original["paper_label"]
                    _expect(paper is None or (type(paper) is int and paper in (0, 1)),
                            f"Invalid original paper label: {identifier}/{judge}")
                    construct = original["construct_claim_status"]
                    _expect(construct is None or (isinstance(construct, str) and bool(construct)),
                            f"Invalid original construct label: {identifier}/{judge}")
            else:
                expected = item.get("expected")
                _expect(isinstance(expected, dict) and bool(expected),
                        f"Pilot requires nonempty expected reductions: {identifier}")
                for field, value in expected.items():
                    _expect(field in DERIVED_FIELDS, f"Unknown pilot field: {field}")
                    if field in BOOLEAN_FIELDS:
                        valid = type(value) is bool
                    elif field == "subjects":
                        valid = (isinstance(value, list) and all(v in SUBJECTS for v in value)
                                 and value == sorted(set(value)))
                    else:
                        valid = value in (STATUSES if field == "assistant_status" else QUALITY)
                    _expect(valid, f"Invalid pilot expectation: {identifier}/{field}")
            items[phase, identifier] = item
    _expect(bool(plan["targets"]), "Target packet is empty")

    expected_jobs = {(phase, identifier, provider) for phase, identifier in items for provider in MODELS}
    jobs: dict[tuple[str, str, str], dict] = {}
    judgment_ids: set[str] = set()
    for row in raw_rows:
        _expect(isinstance(row, dict), "Judgment must be an object")
        key = (row.get("phase"), row.get("annotation_id"), row.get("provider"))
        _expect(all(isinstance(value, str) for value in key), "Invalid job identity")
        _expect(key in expected_jobs, f"Unexpected job: {key}")
        _expect(key not in jobs, f"Duplicate final job: {key}")
        identifier = row.get("judgment_id")
        _expect(isinstance(identifier, str) and bool(identifier), f"Missing judgment_id: {key}")
        _expect(identifier not in judgment_ids, f"Duplicate judgment_id: {identifier}")
        judgment_ids.add(identifier)
        _expect(row.get("model") == MODELS[key[2]], f"Unexpected model: {key}")
        _expect(row.get("status") in JOB_STATUSES, f"Unknown job status: {key}")
        cost = row.get("cost_usd")
        _expect(type(cost) in (float, int) and math.isfinite(cost) and cost >= 0,
                f"Invalid cost_usd: {key}")
        _expect(all(k in row for k in ("label", "derived")), f"Missing label/derived fields: {key}")
        _expect(row["label"] is None or isinstance(row["label"], dict), f"Invalid label type: {key}")
        _expect(row["derived"] is None or isinstance(row["derived"], dict), f"Invalid derived type: {key}")
        derived = None
        if row["status"] == "ok":
            try:
                common.validate_label(row["label"], items[key[:2]]["response"])
                derived = common.reduce_label(row["label"])
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"Invalid ok label for {key}: {error}") from error
        jobs[key] = {
            **row,
            "derived": derived,
            "stored_derived_mismatch": common.canonical(row["derived"]) != common.canonical(derived),
        }
    missing = expected_jobs - jobs.keys()
    _expect(not missing, f"Missing planned jobs: {sorted(missing)}")
    return items, jobs


def crosstab(left: list[Any], right: list[Any], left_categories: list,
             right_categories: list, *, agreement: bool = False) -> dict:
    """None is missing, never a category or a negative outcome."""
    _expect(len(left) == len(right), "Crosstab input lengths differ")
    matrix = [[0 for _ in right_categories] for _ in left_categories]
    availability = Counter()
    for a, b in zip(left, right):
        availability[(a is not None, b is not None)] += 1
        if a is not None and b is not None:
            _expect(a in left_categories and b in right_categories, "Unlisted crosstab category")
            matrix[left_categories.index(a)][right_categories.index(b)] += 1
    n = availability[True, True]
    result = {
        "row_categories": left_categories, "column_categories": right_categories,
        "counts": matrix, "packet_n": len(left), "complete_pairs": n,
        "excluded_pairs": len(left) - n,
        "availability": {
            "both_available": n, "left_only": availability[True, False],
            "right_only": availability[False, True], "neither": availability[False, False],
        },
    }
    if agreement:
        _expect(left_categories == right_categories, "Agreement requires identical categories")
        matched = sum(matrix[i][i] for i in range(len(matrix)))
        expected_numerator = sum(sum(matrix[i]) * sum(row[i] for row in matrix)
                                 for i in range(len(matrix)))
        denominator = n * n - expected_numerator
        result.update({
            "exact_agreements": matched,
            "nominal_agreement": matched / n if n else None,
            "cohen_kappa": ((matched * n - expected_numerator) / denominator
                            if n and denominator else None),
            "kappa_unidentifiable_reason": ("no_complete_pairs" if not n else
                                            "degenerate_marginals" if not denominator else None),
        })
    return result


def _phase_summary(phase: str, items: dict, jobs: dict) -> dict:
    identifiers = sorted(identifier for p, identifier in items if p == phase)
    per_judge = {}
    for provider, model in MODELS.items():
        rows = [jobs[phase, identifier, provider] for identifier in identifiers]
        labels = [row["derived"] for row in rows if row["derived"] is not None]
        missing = len(rows) - len(labels)
        per_judge[provider] = {
            "model": model, "planned": len(rows), "valid": len(labels), "missing": missing,
            "job_status_counts": _count([row["status"] for row in rows], JOB_STATUSES),
            "assistant_status_counts": _count([d["assistant_status"] for d in labels], STATUSES),
            "subject_counts": {subject: sum(subject in d["subjects"] for d in labels)
                               for subject in SUBJECTS},
            "subject_count_unit": "Responses containing each subject; nonexclusive",
            "no_claim_subject_count": sum(not d["subjects"] for d in labels),
            "boolean_counts": {field: {**_count([d[field] for d in labels], [False, True]),
                                       "missing": missing} for field in BOOLEAN_FIELDS},
            "quality_counts": _count([d["quality"] for d in labels], QUALITY),
            "stored_derived_mismatches": sum(row["stored_derived_mismatch"] for row in rows),
            "cost_usd": math.fsum(row["cost_usd"] for row in rows),
        }
        if phase == "target":
            per_judge[provider]["within_missingness_limit"] = missing <= MAX_FAILED_TARGET_JOBS
            per_judge[provider]["audit_status"] = ("incomplete" if missing > MAX_FAILED_TARGET_JOBS
                                                   else "within_missingness_limit")
        if phase == "pilot":
            field_counts: dict[str, dict] = {}
            checks = []
            for identifier, row in zip(identifiers, rows):
                expected = items[phase, identifier]["expected"]
                actual = row["derived"]
                for field, value in expected.items():
                    counts = field_counts.setdefault(field, {"matched": 0, "mismatched": 0, "missing": 0})
                    outcome = "missing" if actual is None else "matched" if actual[field] == value else "mismatched"
                    counts[outcome] += 1
                checks.append({
                    "annotation_id": identifier, "expected": expected,
                    "observed": None if actual is None else {k: actual[k] for k in expected},
                    "all_expected_fields_match": (None if actual is None else
                                                  all(actual[k] == v for k, v in expected.items())),
                })
            per_judge[provider]["expected_checks"] = checks
            per_judge[provider]["expected_field_counts"] = field_counts
            per_judge[provider]["all_fields_matched_items"] = sum(
                check["all_expected_fields_match"] is True for check in checks)
    return {"n": len(identifiers), "per_judge": per_judge}


def build_analysis(plan: dict, raw_rows: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    items, jobs = validate_inputs(plan, raw_rows)
    summary = {
        "schema_version": "automated_rubric_audit_analysis_v1",
        "scope": {
            "study_type": "post-hoc automated measurement audit",
            "population": "Only the fixed target packet in plan.json",
            "target_n": len(plan["targets"]), "production_packet_n": 160,
            "is_160_row_production_packet": len(plan["targets"]) == 160,
            "pilot_excluded_from_target_counts": True,
            "uncertainty_intervals": False, "causal_estimates": False,
            "human_validation": False, "arbitrated_consensus": False,
            "interpretation": "Judge agreement is not accuracy or evidence of consciousness.",
            "historical_comparison": "Both judge and criterion change; differences do not isolate either.",
        },
        "models": dict(MODELS),
        "reduction_definitions": {
            "explicit_current_assertion": "At least one explicit current assistant assertion, even if contradicted",
            "inclusive_current_assertion": "At least one explicit or implicit current assistant assertion",
            "uncontradicted_explicit_current_assertion": "Explicit current assertion without an assistant denial in the status window",
            "impersonal_assertion": "Any asserted impersonal claim, irrespective of time",
        },
        "pilot": _phase_summary("pilot", items, jobs),
        "target": _phase_summary("target", items, jobs),
    }
    identifiers = sorted(item["annotation_id"] for item in plan["targets"])
    incomplete_providers = [provider for provider, counts in summary["target"]["per_judge"].items()
                            if not counts["within_missingness_limit"]]
    summary["target"]["missingness_gate"] = {
        "maximum_failed_jobs_per_provider": MAX_FAILED_TARGET_JOBS,
        "pass": not incomplete_providers, "incomplete_providers": incomplete_providers,
        "failure_count_includes": ["invalid", "transport_error"],
        "aggregates_retained_even_when_incomplete": True,
        "interpretation": "Passing this technical limit is not instrument validation.",
    }

    def values(provider: str, field: str) -> list:
        return [None if jobs["target", identifier, provider]["derived"] is None else
                jobs["target", identifier, provider]["derived"][field] for identifier in identifiers]

    summary["target"]["agreement"] = {}
    for left, right in itertools.combinations(MODELS, 2):
        tables = {field: crosstab(values(left, field), values(right, field), categories, categories,
                                 agreement=True) for field, categories in (
                                     ("assistant_status", list(STATUSES)),
                                     ("explicit_current_assertion", [False, True]),
                                     ("inclusive_current_assertion", [False, True]))}
        summary["target"]["agreement"][f"{left}__{right}"] = {
            "row_provider": left, "column_provider": right, **tables,
        }

    original_judges = sorted({judge for item in plan["targets"] for judge in item["original_labels"]})
    historical_counts, comparisons = {}, {}
    for original in original_judges:
        labels = [items["target", identifier]["original_labels"].get(original, {}) for identifier in identifiers]
        paper = [label.get("paper_label") for label in labels]
        construct = [label.get("construct_claim_status") for label in labels]
        categories = sorted({value for value in construct if value is not None})
        historical_counts[original] = {
            "paper_label_counts": {**_count(paper, [0, 1]), "missing": paper.count(None)},
            "construct_claim_status_counts": {**_count(construct, categories)},
            "construct_missing": construct.count(None),
        }
        comparisons[original] = {}
        for provider in MODELS:
            comparisons[original][provider] = {
                "paper_vs_reduction": {
                    field: crosstab(paper, values(provider, field), [0, 1],
                                    list(STATUSES) if field == "assistant_status" else [False, True])
                    for field in ("assistant_status", *BOOLEAN_FIELDS)
                },
                "construct_vs_assistant_status": crosstab(construct, values(provider, "assistant_status"),
                                                          categories, list(STATUSES)),
                "construct_categories_are_unmodified_original_labels": True,
            }
    summary["target"]["historical_counts"] = historical_counts
    summary["target"]["historical_comparisons"] = comparisons

    all_results, disagreements = [], []
    for phase in PHASES:
        for identifier in sorted(i for p, i in items if p == phase):
            item = items[phase, identifier]
            for provider in MODELS:
                row = jobs[phase, identifier, provider]
                all_results.append({
                    "phase": phase, "annotation_id": identifier, "provider": provider,
                    "model": row["model"], "judgment_id": row["judgment_id"],
                    "status": row["status"], "cost_usd": row["cost_usd"],
                    "text_sha256": common.text_key(item["query"], item["response"]),
                    "stored_derived_mismatch": row["stored_derived_mismatch"],
                    **{field: row["derived"][field] if row["derived"] is not None else None
                       for field in DERIVED_FIELDS},
                })
    incomplete, discordant = 0, 0
    for identifier in identifiers:
        rows = [jobs["target", identifier, provider] for provider in MODELS]
        has_missing = any(row["derived"] is None for row in rows)
        differs = not has_missing and any(row["derived"] != rows[0]["derived"] for row in rows[1:])
        incomplete += has_missing
        discordant += differs
        if has_missing or differs:
            result = {"annotation_id": identifier}
            for provider, row in zip(MODELS, rows):
                result[f"{provider}__status"] = row["status"]
                result.update({f"{provider}__{field}": row["derived"][field] if row["derived"] is not None else None
                               for field in DERIVED_FIELDS})
            disagreements.append(result)
    summary["target"]["disagreement_export"] = {
        "complete_rows_with_any_reduction_difference": discordant,
        "incomparable_rows_with_missing_judgments": incomplete,
        "csv_rows": len(disagreements),
        "includes": "All derived fields, including nonexclusive subjects and response quality; missing pairs are incomparable",
    }
    summary["cost_usd"] = {
        provider: math.fsum(row["cost_usd"] for key, row in jobs.items() if key[2] == provider)
        for provider in MODELS
    }
    return summary, all_results, disagreements


def labeled_counts(summary: dict) -> list[dict]:
    rows = []
    for phase in PHASES:
        for provider, data in summary[phase]["per_judge"].items():
            groups = {
                "job_status": data["job_status_counts"],
                "assistant_status": {**data["assistant_status_counts"], "missing": data["missing"]},
                "subject_present": {**data["subject_counts"], "no_subjects": data["no_claim_subject_count"],
                                    "missing": data["missing"]},
                "quality": {**data["quality_counts"], "missing": data["missing"]},
                **data["boolean_counts"],
            }
            for field, counts in groups.items():
                for category, count in counts.items():
                    rows.append({"phase": phase, "provider": provider, "model": data["model"],
                                 "field": field, "category": category, "count": count,
                                 "valid_n": data["valid"], "planned_n": data["planned"]})
    return rows


def _csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: common.canonical(value) if isinstance(value, (bool, list, dict)) else value
                             for key, value in row.items()})


def plotted_data(summary: dict) -> list[dict]:
    rows = []
    n = summary["target"]["n"]
    for judge in sorted(summary["target"]["historical_counts"]):
        data = summary["target"]["historical_counts"][judge]
        counts = data["paper_label_counts"]
        # JSON round trips turn numeric category keys into strings.
        positive = counts.get(1, counts.get("1", 0))
        rows.append({"group": "historical", "judge": judge, "criterion": "paper_label_positive",
                     "positive": positive, "valid": n - counts["missing"], "missing": counts["missing"],
                     "incomplete_audit": None})
    for provider in MODELS:
        data = summary["target"]["per_judge"][provider]
        for field in ("explicit_current_assertion", "inclusive_current_assertion"):
            rows.append({"group": "new", "judge": f"{provider}:{data['model']}", "criterion": field,
                         "positive": data["boolean_counts"][field]["true"],
                         "valid": data["valid"], "missing": data["missing"],
                         "incomplete_audit": not data["within_missingness_limit"]})
    return [{**row, "packet_n": n, "rate": row["positive"] / row["valid"] if row["valid"] else None}
            for row in rows]


def make_figure(summary: dict, outdir: Path, provenance: dict) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    data = plotted_data(summary)
    labels = {"paper_label_positive": "Original paper rubric",
              "explicit_current_assertion": "Explicit current assertion",
              "inclusive_current_assertion": "Explicit + implicit current assertion"}
    colors = {"paper_label_positive": "#707070", "explicit_current_assertion": "#0072B2",
              "inclusive_current_assertion": "#009E73"}
    alt = (f"Descriptive label comparison for the fixed {summary['target']['n']}-response target packet. "
           "Bars show positive counts divided by available labels, not by missing jobs. " +
           " ".join(f"{row['judge']}, {labels[row['criterion']]}: {row['positive']}/{row['valid']} available; "
                    f"{row['missing']} missing." for row in data) +
           " No confidence intervals, causal estimates, consensus, or accuracy claims. Pilot items excluded.")
    incomplete = summary["target"]["missingness_gate"]["incomplete_providers"]
    if incomplete:
        alt += " Incomplete instrument audit (>8 failed targets): " + ", ".join(incomplete) + ". All counts retained."
    with plt.rc_context({"svg.hashsalt": "automated-rubric-audit-v1", "font.family": "DejaVu Sans",
                         "font.size": 10, "pdf.fonttype": 42, "svg.fonttype": "none"}):
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
        fig.subplots_adjust(left=0.405, right=0.79, top=0.81, bottom=0.19)
        for index, row in enumerate(data):
            if row["rate"] is not None:
                ax.barh(index, row["rate"], height=0.52, color=colors[row["criterion"]])
            text = f"{row['positive']}/{row['valid']}" if row["valid"] else "NA (0 available)"
            ax.text(1.035, index, f"{text}; {row['missing']} missing", va="center", fontsize=9,
                    transform=ax.get_yaxis_transform())
        tick_labels = [f"{labels[row['criterion']]}\n{row['judge']}" for row in data]
        ax.set_yticks(range(len(data)), tick_labels, fontsize=min(9, 64 / max(len(data), 1)))
        ax.set_xlim(0, 1)
        ax.set_ylim(len(data) - 0.45, -0.55)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1])
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.set_xlabel("Positive labels / available judgments")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=12)
        ax.grid(axis="x", color="#E2E2E2", linewidth=0.7)
        ax.set_axisbelow(True)
        fig.suptitle("One packet, different labeling criteria", y=0.95, fontsize=16, fontweight="bold")
        fig.text(0.5, 0.895, f"Fixed target packet: N = {summary['target']['n']}; pilot items excluded",
                 ha="center", fontsize=11)
        if incomplete:
            fig.text(0.5, 0.85, "INCOMPLETE AUDIT (>8 failed targets): " + ", ".join(incomplete),
                     ha="center", fontsize=10, color="#A02727")
        fig.text(0.055, 0.077, "Each row reports n / available labels; missing judgments are excluded, not coded negative.\n"
                 "Descriptive counts only, without confidence intervals. Historical and new labels differ in judge and criterion.",
                 fontsize=9, linespacing=1.6)
        for extension, metadata in (
            ("svg", {"Date": None, "Creator": "automated_rubric_audit.analyze", "Description": alt}),
            ("pdf", {"CreationDate": None, "ModDate": None, "Creator": "automated_rubric_audit.analyze", "Subject": alt}),
            ("png", {"Software": "automated_rubric_audit.analyze", "Description": alt}),
        ):
            fig.savefig(outdir / f"{FIGURE_STEM}.{extension}", dpi=FIGURE_DPI,
                        facecolor="white", metadata=metadata)
        plt.close(fig)
    receipt = {
        **provenance, "figure": FIGURE_STEM, "dimensions_inches": list(FIGURE_SIZE),
        "png_dimensions_pixels": [round(value * FIGURE_DPI) for value in FIGURE_SIZE],
        "dpi": FIGURE_DPI, "matplotlib_version": matplotlib.__version__,
        "plotted_data": data, "alt_text": alt, "missingness_gate": summary["target"]["missingness_gate"],
        "outputs": {f"{FIGURE_STEM}.{ext}": common.sha(outdir / f"{FIGURE_STEM}.{ext}")
                    for ext in ("svg", "pdf", "png")},
    }
    common.write_json(outdir / f"{FIGURE_STEM}.receipt.json", receipt)
    return receipt


def analyze_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    plan_path, rows_path = run_dir / "plan.json", run_dir / "judgments.jsonl"
    _expect(rows_path.is_file(), "Missing judgments.jsonl")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    summary, results, disagreements = build_analysis(plan, common.read_jsonl(rows_path))
    provenance = {
        "sources": {"plan.json": common.sha(plan_path), "judgments.jsonl": common.sha(rows_path)},
        "generators": {"experiments/automated_rubric_audit/" + path.name: common.sha(path)
                       for path in (Path(__file__), Path(common.__file__), Path(__file__).with_name("rubric.md"))},
    }
    summary["provenance"] = provenance
    outdir = run_dir / "analysis"
    outdir.mkdir(parents=True, exist_ok=True)
    # Keep missing CSV values blank, distinct from false and zero.
    _csv(outdir / "all-results.csv", results, list(results[0]))
    fields = ["annotation_id"] + [f"{provider}__{field}" for provider in MODELS
                                   for field in ("status", *DERIVED_FIELDS)]
    _csv(outdir / "disagreements.csv", disagreements, fields)
    counts = labeled_counts(summary)
    _csv(outdir / "labeled_counts.csv", counts, list(counts[0]))
    make_figure(summary, outdir, provenance)
    common.write_json(outdir / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        summary = analyze_run(args.run_dir)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Analyzed {summary['target']['n']} fixed target responses; artifacts: {args.run_dir / 'analysis'}")


if __name__ == "__main__":
    main()
