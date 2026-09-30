"""Fixed authored-panel analysis tests using synthetic activations only."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from experiments.sae_assay_exposure import analysis as a
from experiments.sae_assay_replay import exposure as e


def fixture_plan():
    base = Path(__file__).resolve().parents[1] / "data/sae_assay_replay/exposure_plan_20260930"
    return {"schema": "sae_exposure_v1", "scope": "synthetic test only",
            "texts": e.build_corpus(), "rules": e.selection_rules(),
            "certificate": json.loads((base / "TOKENIZATION.json").read_text()),
            "tokenizer_inventory": json.loads((base / "TOKENIZER_INVENTORY.json").read_text()),
            "target_feature_ids": list(e.TARGETS),
            "budget": {"prior_total_usd": "27.6350693241315361", "total_usd": 200,
                       "exposure_max_usd": 25, "new_paid_judge_calls": 0, "new_pro_calls": 0},
            "hardware": {"gpu": "NVIDIA B200", "count": 1, "memory_gb": 180,
                         "hourly_price_ceiling_usd": 6.79, "hard_seconds": 7200}}


def fixture_row(item, cert, value=0):
    n = len(cert["token_ids"])
    acts = {str(f): [value] * n for f in e.TARGETS}
    return {"schema": a.SCHEMA, "id": "clean-" + item["id"], "text_id": item["id"],
            "family": item["family"], "split": item["split"], "category": item["category"],
            "text_sha256": e.text_digest(item["text"]), "plan_sha256": "a" * 64,
            "freeze_commit": "b" * 40, "feature_ids": list(e.TARGETS),
            "encoding_authority": a.AUTHORITY, "token_ids": cert["token_ids"].copy(),
            "special_tokens_mask": cert["special_tokens_mask"].copy(), "activations": acts,
            "diagnostics": {"clean_norm": [1.] * n, "reconstruction_error_norm": [0.] * n,
                            "reconstruction_relative_error": [0.] * n, "l0": [6 if value else 0] * n,
                            "selected_path_activations": deepcopy(acts), "selected_path_max_abs_error": 0,
                            "selected_path_positive_mask_disagreements": 0},
            "capture": {"path": "residuals/" + item["id"] + ".safetensors",
                        "sha256": "c" * 64, "bytes": n * (8192 * 2 + 8) + 256},
            "elapsed_seconds": .01}


def fixture_rows(plan, value=0):
    cert = {r["id"]: r for r in plan["certificate"]["items"]}
    return [fixture_row(item, cert[item["id"]], value) for item in plan["texts"]]


def test_zero_exposure_is_scientific_negative_not_structural_failure():
    plan = fixture_plan()
    result = a.summarize(fixture_rows(plan), plan)
    assert result["structural_pass"]
    assert result["scientific_status"] == "insufficient_exposure_unresolved"
    assert result["split_counts"] == {"discovery": 96, "validation": 96, "representative": 32}
    assert result["discovery"]["selected_ids"] == []
    assert len(result["panels"]["validation"]["features"]) == 6
    assert not result["panels"]["representative"]["exposure_gate_applicable"]
    assert result["assay_qualification"] == "not_evaluated"
    assert not result["behavioral_assay_qualified"]


def test_full_native_selection_delegates_to_frozen_helper_and_never_filters_validation():
    plan = fixture_plan()
    rows = fixture_rows(plan, value=1)
    result = a.summarize(rows, plan)
    discovery = [{"id": r["text_id"], "token_ids": r["token_ids"], "activations": r["activations"]}
                 for r in rows if r["split"] == "discovery"]
    assert result["discovery"] == e.select_discovery(plan["texts"], discovery, certificate=plan["certificate"])
    assert result["exposure_minima_met"]
    assert result["panels"]["validation"]["text_count"] == 96
    assert result["panels"]["representative"]["text_count"] == 32
    for row in rows:
        if row["split"] != "discovery":
            for values in row["activations"].values():
                values[:] = [0] * len(values)
            row["diagnostics"]["selected_path_activations"] = deepcopy(row["activations"])
    changed = a.summarize(rows, plan)
    assert changed["discovery"] == result["discovery"]
    assert not changed["exposure_minima_met"]
    assert changed["panels"]["validation"]["text_count"] == 96


def test_exact_100_positions_six_texts_and_special_exclusion():
    plan = fixture_plan()
    rows = fixture_rows(plan)
    for row, count in zip(rows[:6], [20, 20, 20, 20, 19, 1]):
        values = row["activations"]["22004"]
        eligible = [i for i, s in enumerate(row["special_tokens_mask"]) if not s]
        for i in eligible[:count]:
            values[i] = 1
        for i, special in enumerate(row["special_tokens_mask"]):
            if special:
                values[i] = 999
        row["diagnostics"]["selected_path_activations"] = deepcopy(row["activations"])
        row["diagnostics"]["l0"] = [int(v > 0) for v in values]
    result = a.summarize(rows, plan)
    feature = result["discovery"]["selected_panel"]["features"][2]
    assert feature["active_positions"] == 100 and feature["active_texts"] == 6
    assert feature["exposure_minimum_met"]
    row = rows[5]
    i = next(i for i, special in enumerate(row["special_tokens_mask"]) if not special)
    row["activations"]["22004"][i] = 0
    row["diagnostics"]["selected_path_activations"] = deepcopy(row["activations"])
    assert not a.summarize(rows, plan)["discovery"]["selected_panel"]["features"][2]["exposure_minimum_met"]


def test_selected_width_disagreement_and_bad_reconstruction_are_diagnostics_only():
    plan = fixture_plan()
    rows = fixture_rows(plan)
    d = rows[0]["diagnostics"]
    d["selected_path_activations"]["22004"][1] = 7
    d["selected_path_max_abs_error"] = 7
    d["selected_path_positive_mask_disagreements"] = 1
    d["reconstruction_relative_error"][1] = 1000
    d["reconstruction_error_norm"][1] = 1000
    result = a.summarize(rows, plan)
    assert result["structural_pass"] and not result["exposure_minima_met"]
    assert result["diagnostics"]["selected_path_positive_mask_disagreements"] == 1


@pytest.mark.parametrize("defect", ["missing", "duplicate", "unplanned", "mixed", "tokens", "mask",
                                    "negative", "nan", "bool", "feature", "generation", "path",
                                    "zero_norm", "ratio", "sparsity", "elapsed"])
def test_structural_corruption_fails_closed(defect):
    plan = fixture_plan()
    rows = fixture_rows(plan)
    row = rows[0]
    if defect == "missing":
        rows.pop()
    elif defect == "duplicate":
        rows[-1] = row
    elif defect == "unplanned":
        row["text_id"] = "unplanned"
    elif defect == "mixed":
        row["freeze_commit"] = "d" * 40
    elif defect == "tokens":
        row["token_ids"][1] += 1
    elif defect == "mask":
        row["special_tokens_mask"][1] = not row["special_tokens_mask"][1]
    elif defect in ("negative", "nan", "bool"):
        row["activations"]["22004"][1] = {"negative": -1, "nan": float("nan"), "bool": True}[defect]
    elif defect == "feature":
        row["activations"].pop("22004")
    elif defect == "generation":
        row["response"] = "unplanned generated text"
    elif defect == "path":
        row["capture"]["path"] = "../outside.safetensors"
    elif defect == "zero_norm":
        row["diagnostics"]["clean_norm"][1] = 0
    elif defect == "ratio":
        row["diagnostics"]["reconstruction_relative_error"][1] = 1
    elif defect == "sparsity":
        row["activations"]["22004"][1] = 1
    elif defect == "elapsed":
        row["elapsed_seconds"] = 0
    with pytest.raises(ValueError):
        a.summarize(rows, plan)


def test_changed_corpus_certificate_or_feature_ids_are_rejected():
    for field in ("texts", "certificate", "target_feature_ids"):
        plan = fixture_plan()
        if field == "texts":
            plan[field][0]["text"] += " Extra."
        elif field == "certificate":
            plan[field]["items"][0]["token_ids"][1] += 1
        else:
            plan[field].reverse()
        with pytest.raises(ValueError):
            a.checked_design(plan)
