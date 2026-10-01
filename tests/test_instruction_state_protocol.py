"""Outcome-free inventory, tokenizer provenance and freeze binding checks."""
import copy
from decimal import Decimal
import json

import pytest

from experiments.instruction_state_qualification import protocol as p


def test_inventory_counts_and_pairs():
    blocks = p.inventory()
    assert len(blocks) == 20
    assert blocks == p.inventory()
    assert [b["index"] for b in blocks] == list(range(1, 21))
    ids = [cell["id"] for block in blocks for cell in block["cells"]]
    assert len(ids) == len(set(ids)) == 80
    source_seeds = []
    response_seeds = []
    for block in blocks:
        assert {(r["instruction"], r["transcript"]) for r in block["cells"]} == {
            ("self", "self"), ("self", "history"), ("history", "self"), ("history", "history")}
        assert len({r["seed"] for r in block["cells"]}) == 1
        response_seeds.append(block["cells"][0]["seed"])
        source_seeds.extend(block["source_seeds"].values())
    assert len(set(source_seeds + response_seeds)) == 60
    assert all(type(s) is int and 0 <= s < 2**63 for s in source_seeds + response_seeds)


def test_caps_match_completed_crossed_study():
    old = json.loads((p.ROOT / "data/causal_transplant/confirmatory_v1_20260709/manifest.json").read_text())
    for key in ("temperature", "induction_max_tokens", "final_max_tokens"):
        assert p.GENERATION[key] == old[key]
    assert p.CHAT_TEMPLATE["date_string"] == "26 Jul 2024"


def test_full_hardware_timer_fits_reserved_partition():
    cost = (Decimal("0.84") * p.CHEAP_SECONDS + Decimal("6.89") * p.MAIN_SECONDS) / 3600
    assert cost < Decimal(p.GPU_CAP_USD)
    assert Decimal(p.GPU_CAP_USD) + Decimal(p.API_CAP_USD) + 1 == Decimal(p.NEW_CAP_USD)
    assert Decimal(p.PRIOR_USD) + Decimal(p.NEW_CAP_USD) < 200
    assert p.RESERVE_SECONDS < p.CHEAP_SECONDS < p.MAIN_SECONDS


def test_source_binding_contains_inherited_lifecycle_and_relative_imports():
    paths = p.source_paths()
    assert paths == sorted(set(paths))
    assert "experiments/sae_assay_replay/controller.py" in paths
    assert "experiments/sae_assay_diagnostic/budget.py" in paths
    assert "experiments/instruction_state_qualification/analysis.py" in paths
    assert "experiments/automated_rubric_audit/common.py" in paths


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'])
def test_noncanonical_numbers_and_duplicates_rejected(raw):
    with pytest.raises(ValueError):
        p.strict_json(raw)


@pytest.fixture
def isolated_plan(tmp_path, monkeypatch):
    original = p.ROOT
    prior = (original / p.PRIOR_BINDING_PATH).read_bytes()
    bindings = json.loads((original / p.TOKEN_BINDINGS_PATH).read_bytes())
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(p, "source_paths", lambda: ["source.py"])
    for relative, raw in ((p.PRIOR_BINDING_PATH, prior),
                          (p.TOKEN_BINDINGS_PATH, (p.canonical(bindings) + "\n").encode()),
                          ("source.py", b"# isolated source\n")):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    plan = p.build_plan()
    path = tmp_path / "PLAN.json"
    path.write_text(p.canonical(plan) + "\n")
    return path, plan, bindings


def test_plan_reconstructs(isolated_plan):
    path, plan, _ = isolated_plan
    assert p.load_plan(path) == plan
    assert plan["status"] == "qualification_only_no_internal_intervention"
    assert plan["looks"]["unresolved_labels"] == "incomplete_no_extension"


@pytest.mark.parametrize("section,key,value", [
    ("budget", "new_cap_usd", "26"),
    ("generation", "final_max_tokens", 256),
    ("looks", "early_pass_min", "0.30"),
    ("model", "precision", "nf4"),
    ("chat_template", "date_string", "01 Oct 2026"),
])
def test_plan_scientific_drift_rejected(isolated_plan, section, key, value):
    path, plan, _ = isolated_plan
    plan[section][key] = value
    path.write_text(p.canonical(plan) + "\n")
    with pytest.raises(ValueError):
        p.load_plan(path)


def test_source_drift_rejected(isolated_plan):
    path, _, _ = isolated_plan
    (path.parent / "source.py").write_text("# changed\n")
    with pytest.raises(ValueError):
        p.load_plan(path)


def test_binding_provenance_rejected(isolated_plan):
    _, _, bindings = isolated_plan
    bad = copy.deepcopy(bindings)
    bad["prior_binding_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        p.validate_token_bindings(bad)
    bad = copy.deepcopy(bindings)
    bad["cases"]["source-self"]["input_token_ids"][0] = True
    with pytest.raises(ValueError):
        p.validate_token_bindings(bad)
    bad = copy.deepcopy(bindings)
    bad["cases"]["source-self"]["messages"][0]["content"] = "A different prompt."
    with pytest.raises(ValueError):
        p.validate_token_bindings(bad)


def test_binding_fixture_is_not_an_outcome():
    messages = p.binding_messages()
    assert len(messages) == 4
    assert messages["source-self"][0]["content"] == p.PROMPTS["self"]
    assert messages["synthetic-final-self"][1]["content"].startswith("Serialization fixture:")


def test_freeze_requires_exact_checkout_and_blobs(isolated_plan, monkeypatch):
    path, plan, _ = isolated_plan
    freeze = "a" * 40
    def git_output(args, **kwargs):
        if args[1] == "rev-parse":
            return freeze + "\n"
        return (path.parent / args[2].split(":", 1)[1]).read_bytes()
    monkeypatch.setattr(p.subprocess, "check_output", git_output)
    assert p.load_plan(path, freeze) == plan
    with pytest.raises(ValueError):
        p.load_plan(path, "a" * 39)
    with pytest.raises(ValueError):
        p.load_plan(path, "b" * 40)
    def wrong_blob(args, **kwargs):
        return freeze + "\n" if args[1] == "rev-parse" else b"corrupt"
    monkeypatch.setattr(p.subprocess, "check_output", wrong_blob)
    with pytest.raises(ValueError):
        p.load_plan(path, freeze)
