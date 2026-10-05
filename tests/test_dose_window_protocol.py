"""Result-free design parity, source binding and cumulative budget checks."""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

from experiments.berg_dose_ladder import protocol as old
from experiments.berg_dose_window import protocol as p


def test_only_declared_design_fields_change_and_seeds_are_fresh():
    before, after = old.design_fields(), p.design_fields()
    assert {k for k in before if before[k] != after[k]} == {"schema", "rows", "budget"}
    assert set(after)-set(before) == {"amendment"}
    assert Decimal(p.PRIOR_USD)+Decimal(p.NEW_CAP_USD) == Decimal(50)
    originals = {s["id"]: s for s in before["rows"]}
    seeds = set(p.CALIBRATION_SEEDS+p.MAIN_SEEDS)
    assert len(seeds) == 108 and max(seeds) < 2**63
    prior = set(old.CALIBRATION_SEEDS+old.MAIN_SEEDS)
    for path in (p.ROOT/"data").rglob("PLAN.json"):
        if "berg_dose_window" in path.parts:
            continue
        def visit(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "seed" and type(item) is int: prior.add(item)
                    if key.endswith("seeds") and isinstance(item, list):
                        prior.update(x for x in item if type(x) is int)
                    visit(item)
            elif isinstance(value, list):
                for item in value: visit(item)
        visit(json.loads(path.read_text()))
    assert seeds.isdisjoint(prior)
    assert all(s["family"] == "zero" and s["phase"] == "calibration" for s in after["rows"][:12])
    for row in after["rows"]:
        original = originals[row["id"].removeprefix("window-")]
        assert {k: v for k, v in row.items() if k not in {"id", "seed", "cap"}} == {
            k: v for k, v in original.items() if k not in {"id", "seed", "cap"}}
        assert row["cap"] == 512 and row["seed"] in seeds
    for dose in p.DOSES:
        rows = p.selected_rows(after, dose)
        assert len(rows) == 684 and sum(s["phase"] == "calibration" for s in rows) == 204
        assert [sum(s["phase"] == "main" and s["panel"] == panel for s in rows) for panel in (1, 2, 3)] == [160]*3


def test_new_plan_source_input_and_order_tampering_rejected(tmp_path, monkeypatch):
    predecessor = json.loads((p.ROOT/"data/berg_dose_ladder/plan_20261004/PLAN.json").read_text())
    monkeypatch.setattr(old, "build_plan", lambda _: deepcopy(predecessor))
    plan = p.build_plan("synthetic-unused-notebook")
    path = tmp_path/"PLAN.json"
    path.write_text(p.canonical(plan)+"\n")
    assert p.load_plan(path) == plan
    for mode in ("cap", "order", "seed", "carry", "source", "input"):
        changed = deepcopy(plan)
        if mode == "cap": changed["rows"][0]["cap"] = 256
        if mode == "order": changed["rows"][0], changed["rows"][12] = changed["rows"][12], changed["rows"][0]
        if mode == "seed": changed["rows"][0]["seed"] = old.CALIBRATION_SEEDS[0]
        if mode == "carry": changed["budget"]["prior_usd"] = "0"
        if mode == "source": changed["source_hashes"].pop("experiments/berg_dose_window/backend.py")
        if mode == "input": changed["input_hashes"][p.POWER] = "0"*64
        path.write_text(p.canonical(changed)+"\n")
        with pytest.raises(ValueError): p.load_plan(path)


def test_all_111_old_frozen_sources_remain_exact():
    plan = json.loads((p.ROOT/"data/berg_dose_ladder/plan_20261004/PLAN.json").read_text())
    assert len(plan["source_hashes"]) == 111
    assert all(p.sha(p.ROOT/name) == digest for name, digest in plan["source_hashes"].items())
