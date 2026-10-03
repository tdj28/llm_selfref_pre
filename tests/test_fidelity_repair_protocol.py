"""Fresh pilot inventory and binding tests; no providers or model downloads."""
from copy import deepcopy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.steering_fidelity_repair import protocol as p
from tests.test_steering_fidelity_protocol import literal_backend_pins


def test_complete_conditional_inventory_and_fixed_dose():
    with literal_backend_pins():
        plan = p.build_plan()
    assert len(plan["rows"]) == len({s["id"] for s in plan["rows"]}) == 600
    assert len(plan["discovery_rows"]) == 200
    assert len(plan["validation_neutral_rows"]) == 40
    assert {k: len(v) for k, v in plan["validation_rows"].items()} == {"P0": 80, "P1": 80}
    assert len(plan["singleton_rows"]) == 80
    assert len(plan["teacher_rows"]) == 48
    assert len(plan["generation_rows"]) == 72
    assert plan["counts"]["calibration_forwards"] == 520
    assert plan["branches"]["stage_t_authorized"] is False
    assert plan["branches"]["e_only_fallback"] is False
    assert all(s["split"] != "test" for s in plan["rows"] if s["task"] == "choice")
    for s in plan["singleton_rows"]:
        assert p.intervention(s) == {"feature_ids": [s["feature_id"]], "weights": [.5],
                                     "sign": 1, "requested_norm": .30 * 18.246721267700195}
    assert all(p.intervention(s) is None for s in plan["discovery_rows"])


def test_budget_and_source_closure_bound_without_old_heldout_outcomes():
    with literal_backend_pins():
        plan = p.build_plan()
    assert plan["budget"]["new_cap_usd"] == "15"
    assert plan["budget"]["prior_usd"] == "9.657774"
    assert plan["budget"]["api_cap_usd"] == "0"
    assert plan["budget"]["total_usd"] == "170"
    paths = set(plan["source_hashes"])
    for name in ("protocol", "runner", "audit", "controller", "liveness", "analysis", "activation_probe"):
        assert f"experiments/steering_fidelity_repair/{name}.py" in paths
    assert "experiments/steering_fidelity/item_bank.json" in paths
    assert "tests/test_fidelity_position_probe.py" in paths
    assert all(not name.startswith(("out/", ".env")) for name in paths)
    assert set(plan["input_hashes"]) == {p.REFERENCE, p.OLD_ANALYSIS, p.PAYLOAD_FIXTURE}
    from experiments.steering_fidelity_repair.controller import sparse_paths
    assert p.PAYLOAD_FIXTURE in sparse_paths(plan)


def test_canonical_plan_reconstruction_and_tampering(tmp_path):
    with literal_backend_pins():
        plan = p.build_plan()
        path = tmp_path / "PLAN.json"
        path.write_text(p.canonical(plan) + "\n")
        assert p.load_plan(path) == plan
        path.write_text(json.dumps(plan))
        with pytest.raises(ValueError, match="source-bound"):
            p.load_plan(path)
        for section, key, value in (("budget", "new_cap_usd", "16"),
                                    ("fixed_dose", "rho", .60),
                                    ("branches", "stage_t_authorized", True)):
            changed = deepcopy(plan)
            changed[section][key] = value
            path.write_text(p.canonical(changed) + "\n")
            with pytest.raises(ValueError, match="source-bound"):
                p.load_plan(path)


def test_runtime_requires_exact_freeze(tmp_path):
    with literal_backend_pins():
        path = tmp_path / "PLAN.json"
        path.write_text(p.canonical(p.build_plan()) + "\n")
        with patch.object(p.subprocess, "check_output", return_value="b" * 40):
            with pytest.raises(ValueError, match="exact freeze"):
                p.load_plan(path, "a" * 40)


def test_no_unlisted_feature_or_random_seed_mutation():
    with pytest.raises(ValueError, match="two fixed"):
        p.intervention({"feature_id": 30032})
    assert p.seed("case-a") == p.seed("case-a")
    assert p.seed("case-a") != p.seed("case-b")
