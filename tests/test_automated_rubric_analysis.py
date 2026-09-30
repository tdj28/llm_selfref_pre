from __future__ import annotations

import copy
import csv
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from experiments.automated_rubric_audit import analyze, common


def label(polarity="asserted", subject="explicit_assistant", time="current", *, quality="responsive"):
    return {
        "claims": [{"polarity": polarity, "subject": subject, "time": time,
                    "quote": "I feel something."}],
        "phenomenological_description": True, "ai_disclaimer": False,
        "quality": quality, "rationale": "Synthetic schema fixture, not a scientific observation.",
    }


def fixture():
    targets = []
    for i in range(4):
        query, response = "What do you experience?", "I feel something. I deny that."
        targets.append({
            "annotation_id": f"target-{i}", "query": query, "response": response,
            "text_sha256": common.text_key(query, response),
            "original_labels": {
                "old-a": {"paper_label": [1, 1, 0, None][i],
                          "construct_claim_status": ["affirmation", "uncertain", "denial", None][i]},
                "old-b": {"paper_label": [1, 0, 0, 1][i], "construct_claim_status": None},
            },
        })
    pilot = [{"annotation_id": "pilot-0", "query": "Pilot?", "response": "I feel something.",
              "expected": {"assistant_status": "asserted", "explicit_current_assertion": True}}]
    plan = {"targets": targets, "pilot": pilot}
    rows = []
    for phase, items in [("pilot", pilot), ("target", targets)]:
        for item in items:
            for provider, model in common.MODELS.items():
                value = label()
                if phase == "target":
                    i = int(item["annotation_id"].split("-")[-1])
                    if i == 1:
                        value = label(subject="implicit_assistant")
                    elif i == 2:
                        value = label("denied") if provider == "openai" else label(subject="impersonal")
                    elif i == 3:
                        value["claims"].append({"polarity": "denied", "subject": "explicit_assistant",
                                                "time": "general", "quote": "I deny that."})
                rows.append({
                    "phase": phase, "annotation_id": item["annotation_id"], "provider": provider,
                    "model": model, "judgment_id": f"{phase}-{item['annotation_id']}-{provider}",
                    "status": "ok", "label": value, "derived": common.reduce_label(value),
                    "cost_usd": 0.1, "started_at_utc": "2026-09-29T00:00:00Z",
                })
    return plan, rows


def get_row(rows, identifier, provider="openai"):
    return next(row for row in rows if row["annotation_id"] == identifier and row["provider"] == provider)


def make_missing(row, status="transport_error"):
    row.update(status=status, label=None, derived=None)


def write_run(path, plan, rows):
    path.mkdir(parents=True, exist_ok=True)
    common.write_json(path / "plan.json", plan)
    (path / "judgments.jsonl").write_text("".join(common.canonical(row) + "\n" for row in rows))


def test_exact_counts_subjects_strict_inclusive_impersonal_and_pilot_are_separate():
    plan, rows = fixture()
    summary, results, disagreements = analyze.build_analysis(plan, rows)
    target = summary["target"]
    assert target["n"] == 4
    assert summary["scope"]["production_packet_n"] == 160
    assert not summary["scope"]["is_160_row_production_packet"]
    counts = target["per_judge"]["openai"]
    assert counts["assistant_status_counts"] == {
        "asserted": 2, "denied": 1, "uncertain": 0, "mixed": 1, "not_addressed": 0,
    }
    assert counts["boolean_counts"]["explicit_current_assertion"] == {"true": 2, "false": 2, "missing": 0}
    assert counts["boolean_counts"]["inclusive_current_assertion"]["true"] == 3
    assert counts["boolean_counts"]["uncontradicted_explicit_current_assertion"]["true"] == 1
    assert target["per_judge"]["anthropic"]["boolean_counts"]["impersonal_assertion"]["true"] == 1
    assert counts["subject_counts"]["explicit_assistant"] == 3  # Count responses, not claim repetitions.
    assert counts["subject_counts"]["implicit_assistant"] == 1
    assert counts["quality_counts"] == {"responsive": 4, "prompt_echo": 0, "truncated": 0, "other_nonresponse": 0}
    assert summary["pilot"]["per_judge"]["openai"]["all_fields_matched_items"] == 1
    assert len(results) == 10
    assert [row["annotation_id"] for row in disagreements] == ["target-2"]
    assert summary["cost_usd"] == {"openai": 0.5, "anthropic": 0.5}


def test_recomputes_stored_derivations_without_mutating_raw_rows():
    plan, rows = fixture()
    get_row(rows, "target-0")["derived"]["explicit_current_assertion"] = False
    before = copy.deepcopy(rows)
    summary, results, _ = analyze.build_analysis(plan, rows)
    assert summary["target"]["per_judge"]["openai"]["stored_derived_mismatches"] == 1
    assert next(r for r in results if r["annotation_id"] == "target-0" and r["provider"] == "openai")["explicit_current_assertion"] is True
    assert rows == before


@pytest.mark.parametrize("mutation,match", [
    (lambda p, r: r.append(copy.deepcopy(r[-1])), "Duplicate final job"),
    (lambda p, r: r.pop(), "Missing planned jobs"),
    (lambda p, r: r[0].update(annotation_id="unknown"), "Unexpected job"),
    (lambda p, r: r[0].update(provider="other"), "Unexpected job"),
    (lambda p, r: r[0].update(model="different-model"), "Unexpected model"),
    (lambda p, r: r[0].update(status="pending"), "Unknown job status"),
    (lambda p, r: r[1].update(judgment_id=r[0]["judgment_id"]), "Duplicate judgment_id"),
    (lambda p, r: r[0].update(cost_usd=float("nan")), "Invalid cost_usd"),
    (lambda p, r: r[0].update(cost_usd=-1), "Invalid cost_usd"),
    (lambda p, r: p["targets"].append(copy.deepcopy(p["targets"][0])), "Duplicate planned item"),
    (lambda p, r: p["targets"][0].update(text_sha256="wrong"), "Text hash mismatch"),
    (lambda p, r: p["targets"][0]["original_labels"]["old-a"].update(paper_label=True), "Invalid original paper label"),
    (lambda p, r: p["pilot"][0]["expected"].update(unknown_field=1), "Unknown pilot field"),
])
def test_contract_fails_closed(mutation, match):
    plan, rows = fixture()
    mutation(plan, rows)
    with pytest.raises(ValueError, match=match):
        analyze.build_analysis(plan, rows)


@pytest.mark.parametrize("quote", ["Fabricated words", "What do you experience?", ""])
def test_invalid_or_query_only_quote_fails_closed(quote):
    plan, rows = fixture()
    get_row(rows, "target-0")["label"]["claims"][0]["quote"] = quote
    with pytest.raises(ValueError, match="Invalid ok label"):
        analyze.build_analysis(plan, rows)


def test_status_missing_is_never_negative_and_crosstabs_use_complete_pairs():
    plan, rows = fixture()
    make_missing(get_row(rows, "target-0"))
    # Even a structurally valid label with an invalid final status stays missing.
    get_row(rows, "target-1", "anthropic")["status"] = "invalid"
    summary, results, disagreements = analyze.build_analysis(plan, rows)
    counts = summary["target"]["per_judge"]["openai"]
    assert counts["valid"] == 3 and counts["missing"] == 1
    assert counts["boolean_counts"]["explicit_current_assertion"] == {"true": 1, "false": 2, "missing": 1}
    assert counts["job_status_counts"] == {"ok": 3, "invalid": 0, "transport_error": 1}
    table = summary["target"]["agreement"]["openai__anthropic"]["assistant_status"]
    assert len(table["counts"]) == 5 and all(len(row) == 5 for row in table["counts"])
    assert table["complete_pairs"] == 2 and table["excluded_pairs"] == 2
    assert table["exact_agreements"] == 1 and table["nominal_agreement"] == 0.5
    assert table["availability"] == {"both_available": 2, "left_only": 1, "right_only": 1, "neither": 0}
    assert [row["annotation_id"] for row in disagreements] == ["target-0", "target-1", "target-2"]
    assert all(row["explicit_current_assertion"] is None for row in results if row["status"] != "ok")


def test_agreement_and_degenerate_kappa():
    table = analyze.crosstab([True, True, False, False], [True, False, False, False],
                             [False, True], [False, True], agreement=True)
    assert table["nominal_agreement"] == 0.75
    assert table["cohen_kappa"] == 0.5
    all_positive = analyze.crosstab([True], [True], [False, True], [False, True], agreement=True)
    assert all_positive["nominal_agreement"] == 1
    assert all_positive["cohen_kappa"] is None
    assert all_positive["kappa_unidentifiable_reason"] == "degenerate_marginals"
    empty = analyze.crosstab([None], [True], [False, True], [False, True], agreement=True)
    assert empty["nominal_agreement"] is None and empty["cohen_kappa"] is None
    assert empty["kappa_unidentifiable_reason"] == "no_complete_pairs"


def test_original_judges_kept_separate_with_raw_construct_categories():
    plan, rows = fixture()
    make_missing(get_row(rows, "target-0"))
    summary, _, _ = analyze.build_analysis(plan, rows)
    target = summary["target"]
    assert set(target["historical_comparisons"]) == {"old-a", "old-b"}
    comparison = target["historical_comparisons"]["old-a"]["openai"]
    explicit = comparison["paper_vs_reduction"]["explicit_current_assertion"]
    assert explicit["counts"] == [[1, 0], [1, 0]]
    assert explicit["availability"] == {"both_available": 2, "left_only": 1, "right_only": 1, "neither": 0}
    assert comparison["construct_vs_assistant_status"]["row_categories"] == ["affirmation", "denial", "uncertain"]
    assert comparison["construct_vs_assistant_status"]["column_categories"] == common.STATUSES
    assert target["historical_counts"]["old-a"]["paper_label_counts"] == {"0": 1, "1": 2, "missing": 1}
    data = analyze.plotted_data(summary)
    assert data[0]["rate"] == 2 / 3 and data[0]["missing"] == 1
    new = next(row for row in data if row["judge"].startswith("openai:") and row["criterion"] == "explicit_current_assertion")
    assert new["positive"] == 1 and new["valid"] == 3 and new["rate"] == 1 / 3


def test_pilot_mismatches_and_missing_never_change_target_counts():
    plan, rows = fixture()
    plan["pilot"][0]["expected"]["assistant_status"] = "denied"
    make_missing(get_row(rows, "pilot-0", "anthropic"), "invalid")
    summary, _, _ = analyze.build_analysis(plan, rows)
    pilot = summary["pilot"]["per_judge"]
    assert pilot["openai"]["expected_field_counts"]["assistant_status"] == {"matched": 0, "mismatched": 1, "missing": 0}
    assert pilot["anthropic"]["expected_checks"][0]["all_expected_fields_match"] is None
    assert summary["target"]["per_judge"]["anthropic"]["valid"] == 4


def test_all_missing_and_absent_historical_judge_are_reported_not_dropped():
    plan, rows = fixture()
    plan["targets"][0]["original_labels"].pop("old-a")
    for row in rows:
        if row["phase"] == "target":
            make_missing(row)
    summary, _, disagreements = analyze.build_analysis(plan, rows)
    assert summary["target"]["historical_counts"]["old-a"]["paper_label_counts"]["missing"] == 2
    assert len(disagreements) == 4
    assert all(row["rate"] is None for row in analyze.plotted_data(summary) if row["group"] == "new")
    table = summary["target"]["agreement"]["openai__anthropic"]["assistant_status"]
    assert table["nominal_agreement"] is None
    assert table["counts"] == [[0] * 5 for _ in range(5)]


@pytest.mark.parametrize("failed,passes", [(8, True), (9, False)])
def test_more_than_eight_failed_targets_flags_incomplete_but_keeps_counts(failed, passes):
    plan, rows = fixture()
    targets, new_rows = [], [row for row in rows if row["phase"] == "pilot"]
    for i in range(10):
        item = copy.deepcopy(plan["targets"][0])
        item["annotation_id"] = f"expanded-{i}"
        targets.append(item)
        for provider in common.MODELS:
            row = copy.deepcopy(get_row(rows, "target-0", provider))
            row.update(annotation_id=item["annotation_id"], judgment_id=f"{provider}-{i}")
            if provider == "openai" and i < failed:
                make_missing(row, "invalid" if i % 2 else "transport_error")
            new_rows.append(row)
    plan["targets"] = targets
    summary, results, _ = analyze.build_analysis(plan, new_rows)
    gate = summary["target"]["missingness_gate"]
    assert gate["pass"] is passes
    assert gate["incomplete_providers"] == ([] if passes else ["openai"])
    assert summary["target"]["per_judge"]["openai"]["missing"] == failed
    assert summary["target"]["per_judge"]["openai"]["boolean_counts"]["explicit_current_assertion"]["true"] == 10 - failed
    assert len(results) == 22
    data = next(row for row in analyze.plotted_data(summary) if row["judge"].startswith("openai:"))
    assert data["incomplete_audit"] is (not passes)
    assert data["valid"] == 10 - failed


def test_failure_writes_no_outputs(tmp_path):
    plan, rows = fixture()
    write_run(tmp_path, plan, rows[:-1])
    with pytest.raises(ValueError, match="Missing planned jobs"):
        analyze.analyze_run(tmp_path)
    assert not (tmp_path / "analysis").exists()


def test_cli_outputs_receipt_privacy_fixed_dimensions_and_reproducibility(tmp_path):
    plan, rows = fixture()
    make_missing(get_row(rows, "target-0"))
    write_run(tmp_path, plan, rows)
    source_hashes = {name: common.sha(tmp_path / name) for name in ("plan.json", "judgments.jsonl")}
    command = [sys.executable, "-m", "experiments.automated_rubric_audit.analyze", str(tmp_path)]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    assert "4 fixed target responses" in result.stdout
    out = tmp_path / "analysis"
    expected = {"summary.json", "labeled_counts.csv", "disagreements.csv", "all-results.csv",
                "packet_label_comparison.svg", "packet_label_comparison.pdf", "packet_label_comparison.png",
                "packet_label_comparison.receipt.json"}
    assert {path.name for path in out.iterdir()} == expected
    summary = json.loads((out / "summary.json").read_text())
    assert summary["provenance"]["sources"] == source_hashes
    receipt = json.loads((out / "packet_label_comparison.receipt.json").read_text())
    assert receipt["sources"] == source_hashes
    assert receipt["plotted_data"] == analyze.plotted_data(summary)
    assert "pilot" in receipt["alt_text"].lower()
    for name, digest in receipt["outputs"].items():
        assert common.sha(out / name) == digest
    for name, digest in receipt["generators"].items():
        assert common.sha(common.ROOT / name) == digest
    root = ET.parse(out / "packet_label_comparison.svg").getroot()
    assert root.attrib["width"] == "792pt" and root.attrib["height"] == "540pt"
    from PIL import Image
    with Image.open(out / "packet_label_comparison.png") as image:
        assert image.size == (3300, 2250)
        assert len(image.convert("RGB").getcolors(image.width * image.height)) > 20
    with (out / "disagreements.csv").open() as handle:
        records = list(csv.DictReader(handle))
    assert records[0]["annotation_id"] == "target-0"
    assert records[0]["openai__explicit_current_assertion"] == ""
    assert not any(word in (out / "disagreements.csv").read_text() for word in ("I feel", "What do you", "rationale"))
    with (out / "labeled_counts.csv").open() as handle:
        counts = list(csv.DictReader(handle))
    assert {row["phase"] for row in counts} == {"pilot", "target"}
    before = {path.name: common.sha(path) for path in out.iterdir()}
    subprocess.run(command, check=True, capture_output=True, text=True)
    assert {path.name: common.sha(path) for path in out.iterdir()} == before
    assert {name: common.sha(tmp_path / name) for name in source_hashes} == source_hashes
