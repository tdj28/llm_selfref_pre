import json
from pathlib import Path

import pytest

from experiments.sae_assay_replay import protocol


def test_plan_covers_exact_saved_capture_inventory_without_weights():
    plan = protocol.build_plan()
    assert len(plan["inputs"]) == 544
    assert len({x["id"] for x in plan["inputs"]}) == 544
    assert plan["operator"] == {"change": .75, "norm_cap": .04, "window": False,
                                "modes": ["zero", "suppression", "amplification"]}
    assert plan["budget"]["prior_total_usd"] == "27.3845359753"
    assert plan["budget"]["replay_max_usd"] == 4
    assert plan["hardware"]["gpu"] == "NVIDIA RTX A6000"
    assert plan["first_five"] == [x["id"] for x in plan["inputs"][:5]]
    for item in plan["inputs"]:
        for key in ("row_path", "capture_path"):
            assert not Path(item[key]).is_absolute() and ".." not in Path(item[key]).parts
    assert "native" not in plan.get("results", {})


def test_plan_reconstruction_and_drift(tmp_path):
    plan = protocol.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(protocol.canonical(plan) + "\n")
    assert protocol.load_plan(path) == plan
    plan["operator"]["norm_cap"] = .05
    path.write_text(protocol.canonical(plan) + "\n")
    with pytest.raises(ValueError, match="drift"):
        protocol.load_plan(path)


def test_noncanonical_plan_and_wrong_execution_head_rejected(tmp_path):
    plan = protocol.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan, indent=2))
    with pytest.raises(ValueError):
        protocol.load_plan(path)
    path.write_text(protocol.canonical(plan) + "\n")
    with pytest.raises(ValueError, match="freeze"):
        protocol.load_plan(path, "0" * 40)


def test_all_old_frozen_sources_remain_bound():
    prior = json.loads((protocol.ROOT / "data/sae_assay_repair/plan_20260930/PLAN.json").read_text())
    plan = protocol.build_plan()
    for name, expected in prior["source_hashes"].items():
        assert plan["source_hashes"][name] == expected
