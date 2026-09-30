import json
from collections import Counter

import pytest

from experiments.sae_assay_exposure import protocol as p


def test_fixed_panel_and_separate_pilot():
    plan = p.build_plan()
    assert len(plan["texts"]) == 224
    assert Counter(x["split"] for x in plan["texts"]) == {
        "discovery": 96, "validation": 96, "representative": 32}
    assert plan["first_five"] == [x["id"] for x in plan["texts"][:5]]
    assert sum(len(x["token_ids"]) for x in plan["certificate"]["items"]) == 23489
    pilot = plan["precision_pilot"]
    assert len(pilot["texts"]) == len({r["family"] for r in pilot["texts"]}) == 12
    assert all(r["split"] == "discovery" and r["id"].endswith("-01") for r in pilot["texts"])
    assert pilot["modes"] == ["native_zero", "precision_sham", "suppression", "amplification"]
    assert pilot["fidelity"]["minimum_fraction"] == .95
    assert pilot["norm"]["maximum_clean_ratio"] == .05
    assert plan["budget"] == {"prior_total_usd": "27.6350693241315361", "total_usd": 200,
                             "exposure_max_usd": 25, "new_paid_judge_calls": 0, "new_pro_calls": 0}
    assert plan["hardware"]["hard_seconds"] == 7200
    assert set(plan["target_feature_ids"]) == {30032, 58667, 22004, 30686, 41533, 23893}


def test_canonical_roundtrip_and_tamper(tmp_path):
    plan = p.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(p.canonical(plan) + "\n")
    assert p.load_plan(path) == plan
    plan["precision_pilot"]["fidelity"]["minimum_fraction"] = .6
    path.write_text(p.canonical(plan) + "\n")
    with pytest.raises(ValueError, match="drift"):
        p.load_plan(path)


def test_noncanonical_and_wrong_freeze(tmp_path):
    plan = p.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan, indent=2))
    with pytest.raises(ValueError):
        p.load_plan(path)
    path.write_text(p.canonical(plan) + "\n")
    with pytest.raises(ValueError, match="freeze"):
        p.load_plan(path, "0" * 40)


def test_historical_sources_unchanged_and_all_new_runtime_bound():
    plan = p.build_plan()
    prior = json.loads((p.ROOT / "data/sae_assay_replay/plan_20260930a/PLAN.json").read_text())
    for name, checksum in prior["source_hashes"].items():
        assert plan["source_hashes"][name] == checksum
    for package in ("sae_assay_exposure", "sae_assay_precision"):
        for path in (p.ROOT / "experiments" / package).glob("*.py"):
            assert path.relative_to(p.ROOT).as_posix() in plan["source_hashes"]
