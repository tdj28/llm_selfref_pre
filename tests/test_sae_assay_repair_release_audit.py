from copy import deepcopy

import pytest

from experiments.sae_assay_repair.release_audit import compare_reports, normalize_diagnostic_order, runtime_rows


def example():
    return {"pass": False, "value": .75, "features": [30032, 22004],
            "arm": {"encoder_activity_parity": [{"value": 1}, {"value": 2}]},
            "mask_reports": [{"id": "a", "pass": True}, {"id": "b", "pass": False}]}


def test_only_diagnostic_permutations_are_ignored():
    saved = example()
    chrono = deepcopy(saved)
    chrono["arm"]["encoder_activity_parity"].reverse()
    chrono["mask_reports"].reverse()
    original = deepcopy(chrono)
    report = compare_reports(saved, chrono, deepcopy(saved))
    assert report == {"runtime_order_exact": True, "chronological_exact": False,
                      "chronological_matches_after_diagnostic_list_permutation": True}
    assert chrono == original


@pytest.mark.parametrize("field,value", [("pass", True), ("value", .750000000001),
                                          ("features", [22004, 30032])])
def test_scientific_changes_are_not_permutations(field, value):
    saved = example()
    changed = deepcopy(saved)
    changed[field] = value
    assert normalize_diagnostic_order(saved) != normalize_diagnostic_order(changed)
    report = compare_reports(saved, changed, saved)
    assert not report["chronological_matches_after_diagnostic_list_permutation"]


def test_missing_diagnostic_or_changed_logical_report_fails():
    saved = example()
    bad = deepcopy(saved)
    bad["mask_reports"].pop()
    assert not compare_reports(saved, bad, saved)["chronological_matches_after_diagnostic_list_permutation"]
    assert not compare_reports(saved, saved, bad)["runtime_order_exact"]


def test_runtime_order_is_plan_not_receipt_order():
    plan = {"texts": [{"id": "b", "split": "calibration"},
                      {"id": "a", "split": "calibration"},
                      {"id": "heldout", "split": "validation"}], "strengths": [.5, 1.]}
    rows = {"clean-" + name: {"id": "clean-" + name, "group": "literal"} for name in ("a", "b")}
    for strength in (50, 100):
        for mode in ("suppression", "amplification"):
            for name in ("a", "b"):
                rid = f"edit-decoder_span-{name}-{mode}-{strength:03d}"
                rows[rid] = {"id": rid, "group": "decoder_span"}
    actual = runtime_rows(plan, rows, "decoder_span")
    assert [r["id"] for r in actual[:4]] == ["clean-b", "clean-a",
        "edit-decoder_span-b-suppression-050", "edit-decoder_span-a-suppression-050"]
    assert all(r["group"] == "decoder_span" for r in actual)
    assert rows["clean-a"]["group"] == "literal"
    del rows["edit-decoder_span-b-amplification-100"]
    with pytest.raises(KeyError):
        runtime_rows(plan, rows, "decoder_span")
