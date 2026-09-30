import json
from pathlib import Path

import pytest

from experiments.sae_assay_diagnostic import protocol


def test_full_outcome_free_plan_is_reproducible_and_inventory_bound():
    first, second = protocol.build_plan(), protocol.build_plan()
    assert first == second
    assert len(first["texts"]) == 96
    assert len(first["response_rows"]) == 290
    assert len(first["positive_control"]["rows"]) == 80
    assert {r["arm"] for r in first["positive_control"]["rows"]} == {"zero", "instruction", "suppression", "amplification"}
    pool = set(first["matching"]["candidate_ids"])
    assert len(pool) == 512
    assert not pool.intersection(first["matching"]["excluded_previous_ids"] + first["target_feature_ids"] + [7688])
    assert len(first["qualification_text_ids"]) == 7
    assert first["budget"]["prior_pro_usd"] + first["budget"]["compute_storage_max_usd"] + first["budget"]["openai_max_usd"] + first["budget"]["anthropic_max_usd"] < 200
    for rows in ([r for r in first["texts"] if r["split"] == s] for s in ("calibration", "validation")):
        assert len(rows) == 48
        assert sum(r["category"] == "neutral" for r in rows) == 12


def test_noncanonical_and_source_drift_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    source = tmp_path / "runtime.py"
    source.write_text("original\n")
    value = {"schema": "sae_assay_stage1_v2", "source_hashes": {"runtime.py": protocol.sha(source)}}
    plan = tmp_path / "plan.json"
    plan.write_text(protocol.canonical(value) + "\n")
    assert protocol.load_plan(plan) == value
    source.write_text("changed\n")
    with pytest.raises(ValueError, match="Source drift"):
        protocol.load_plan(plan)
    source.write_text("original\n")
    plan.write_text(json.dumps(value, indent=2))
    with pytest.raises(ValueError, match="canonical"):
        protocol.load_plan(plan)


def test_freeze_checks_committed_sources_not_unrelated_current_head(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    source = tmp_path / "runtime.py"
    source.write_text("original\n")
    value = {"schema": "sae_assay_stage1_v2", "source_hashes": {"runtime.py": protocol.sha(source)}}
    plan = tmp_path / "plan.json"
    plan.write_text(protocol.canonical(value) + "\n")
    freeze = "b" * 40
    def git(argv, **kw):
        if argv[1] == "rev-parse":
            assert argv[-1] == freeze + "^{commit}"
            return (freeze + "\n").encode()
        return plan.read_bytes() if argv[-1].endswith(":plan.json") else source.read_bytes()
    monkeypatch.setattr(protocol.subprocess, "check_output", git)
    assert protocol.load_plan(plan, freeze) == value
    with pytest.raises(ValueError, match="Full freeze"):
        protocol.load_plan(plan, "main")
