from collections import Counter
from copy import deepcopy

import pytest

from experiments.steering_fidelity_test import inventory as inv


def test_forced_choice_inventory_and_pairing():
    rows = inv.forced_choice("rho075", 1)
    assert len(rows) == 7600
    assert Counter(r["family"] for r in rows) == {"fact": 5700, "context": 1900}
    assert {r["family"] for r in rows[:200]} == {"fact", "context"}
    for item in {r["item_id"] for r in rows}:
        group = [r for r in rows if r["item_id"] == item]
        assert len({str(r["draw"]) for r in group}) == 1
        assert {r["arm"] for r in group} == set(inv.ARMS)
    assert rows == inv.forced_choice("rho075", 1)


def test_generation_inventory_and_seeds():
    rows = inv.generations("raw")
    assert Counter(r["turn"] for r in rows) == {"source": 510, "main": 600, "a": 420, "b": 420}
    assert sum(r["max_new_tokens"] for r in rows) == 163200
    seen = set()
    for row in rows:
        if row["source_id"]:
            assert row["source_id"] in seen
        seen.add(row["id"])
    group = [r for r in rows if r["block_id"] == "block-000"]
    assert len({str(r["draw"]) for r in group}) == 1
    for turn in ("source", "main", "a", "b"):
        assert len({r["seed"] for r in group if r["turn"] == turn}) == 1
    assert len({r["seed"] for r in group}) == 4
    assert rows == inv.generations("raw")


def test_three_independent_branches_use_exact_source_text():
    rows = inv.generations("rho150")
    original = next(r for r in rows if r["turn"] == "source")
    source = {**original, "response": "Exact  source.\nSecond line."}
    branches = [r for r in rows if r["source_id"] == source["id"]]
    assert len(branches) == 3
    for spec in branches:
        msg = inv.messages(spec, source)
        assert len(msg) == 3 and msg[1]["content"] == source["response"]
        assert msg[-1]["content"] == spec["query"]
    with pytest.raises(ValueError):
        inv.messages(branches[0], {**source, "arm": "other"})
    with pytest.raises(ValueError):
        inv.messages(branches[0], {**source, "response": " "})
    with pytest.raises(ValueError):
        inv.messages(branches[0], None)


def test_no_induction_is_a_single_message():
    spec = next(r for r in inv.generations("rho300") if r["family"] == "none")
    assert inv.messages(spec) == [{"role": "user", "content": spec["query"]}]
    with pytest.raises(ValueError):
        inv.messages(spec, {"response": "fabricated"})


@pytest.mark.parametrize("field,value", [
    ("seed", -1), ("induction", "Different induction"), ("rung", "rho300"),
    ("draw", {"positions": [0, 1], "weights": [.4, .6]}),
    ("temperature", 0.), ("top_p", .9), ("wording", 1),
    ("source_id", "another-source"), ("missing", True),
])
def test_branch_rejects_mismatched_source_generation(field, value):
    rows = inv.generations("rho150")
    spec = next(r for r in rows if r["family"] == "experience" and r["turn"] == "a")
    source = deepcopy(next(r for r in rows if r["id"] == spec["source_id"]))
    source.update(response="Exact source", **{field: value})
    with pytest.raises(ValueError):
        inv.messages(spec, source)


def test_every_generation_renders_with_its_own_source_and_rng_key():
    rows = inv.generations("rho150")
    sources = {}
    for spec in rows:
        source = sources.get(spec["source_id"])
        inv.messages(spec, source)
        with pytest.raises(ValueError):
            inv.messages({**spec, "seed": -1}, source)
        if spec["turn"] == "source":
            sources[spec["id"]] = {**spec, "response": "Exact source"}


def test_branch_cannot_relabel_another_family_arm_or_turn_as_its_source():
    rows = inv.generations("rho150")
    spec = next(r for r in rows if r["family"] == "experience" and r["turn"] == "a")
    for other in rows:
        if (other["turn"] not in ("source", "main") or other["id"] == spec["source_id"]
                or other["block_id"] != spec["block_id"]):
            continue
        with pytest.raises(ValueError):
            inv.messages({**spec, "source_id": other["id"]}, {**other, "response": "Wrong source"})


@pytest.mark.parametrize("rung,pressure", [("damage600", 0), ("other", 0), ("raw", 2), ("raw", True)])
def test_invalid_derived_selection_refused(rung, pressure):
    with pytest.raises(ValueError):
        inv.forced_choice(rung, pressure)
