"""Offline inventory, funding, request identity and source-freeze controls."""

from collections import Counter
from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.providers import generation_request
from experiments.repeated_swap import protocol as p


def metadata():
    snapshots = {}
    zdr = []
    for role, specs in (("generation", p.MODELS), ("judges", p.JUDGES)):
        for spec in specs.values():
            endpoint = {"model_id": spec["id"], "tag": spec["provider_slug"],
                        "provider_name": spec["provider_name"], "status": 0,
                        "max_completion_tokens": 6000,
                        "supported_parameters": ["max_tokens", "reasoning", "reasoning_effort",
                                                 "temperature", "response_format", "structured_outputs"],
                        "pricing": {"prompt": str(Decimal(spec["input_price"]) / 1_000_000),
                                    "completion": str(Decimal(spec["output_price"]) / 1_000_000)}}
            snapshots.setdefault(spec["id"], {"id": spec["id"], "endpoints": []})["endpoints"].append(endpoint)
            if role == "judges":
                zdr.append(deepcopy(endpoint))
    return {"approved": True, "fetched_at_utc": "2026-10-05T06:30:00+00:00",
            "endpoint_snapshots": snapshots, "zdr_endpoints": zdr,
            "account_balance_usd": "167.058468203", "external_reserve_usd": "45"}


def test_inventory_counts_balance_unique_draws_and_fresh_namespace():
    blocks = p.inventory("main")
    assert blocks == p.inventory("main") and len(blocks) == 64
    assert sum(len(b["sources"]) for b in blocks) == 128
    assert sum(len(b["finals"]) for b in blocks) == 768
    assert Counter((b["model"], b["family"]) for b in blocks) == {
        (model, family): 16 for model in p.MODELS for family in ("a", "b")}
    all_ids = [s["id"] for b in blocks for kind in ("sources", "finals") for s in b[kind]]
    assert len(set(all_ids)) == 896
    old_ids = {s["id"] for b in common.inventory("main") for kind in ("sources", "finals") for s in b[kind]}
    assert not old_ids.intersection(all_ids)
    assert all(identifier.startswith(p.NAMESPACE) for identifier in all_ids)
    assert p.inventory("screen") == []
    with pytest.raises(ValueError):
        p.inventory("initial")
    for block in blocks:
        source_ids = {s["id"] for s in block["sources"]}
        assert {s["transcript"] for s in block["sources"]} == {"self", "history"}
        assert Counter(s["cell"] for s in block["finals"]) == dict.fromkeys(p.CELLS, 3)
        for cell in p.CELLS:
            draws = [s for s in block["finals"] if s["cell"] == cell]
            assert {s["draw"] for s in draws} == {1, 2, 3}
            assert len({s["request_id"] for s in draws}) == 1
            assert len({s["source_id"] for s in draws}) == 1
            assert all(s["source_id"] in source_ids for s in draws)
        by_cell = {s["cell"]: s["source_id"] for s in block["finals"]}
        assert by_cell["SS"] == by_cell["HS"]
        assert by_cell["SH"] == by_cell["HH"] != by_cell["SS"]


def test_randomization_initial_barrier_and_no_shared_mutable_inventory():
    blocks = p.inventory("main")
    assert [(b["model"], b["block"]) for b in blocks] != sorted((b["model"], b["block"]) for b in blocks)
    for model in p.MODELS:
        initial = [b for b in blocks if b["model"] == model and b["block"] <= 2]
        assert {b["family"] for b in initial} == {"a", "b"}
    assert any([s["draw"] for s in b["finals"]] != sorted(s["draw"] for s in b["finals"]) for b in blocks)
    blocks[0]["finals"].pop()
    assert len(p.inventory("main")[0]["finals"]) == 12


def test_exact_body_repeats_without_generation_seed_or_reasoning_transplant():
    source = "  Synthetic final content only.\r\nUnchanged whitespace.  "
    assert p.messages is common.messages
    for block in p.inventory("main"):
        for cell in p.CELLS:
            draws = [s for s in block["finals"] if s["cell"] == cell]
            requests = [generation_request(p.MODELS[block["model"]], p.messages(s, source)) for s in draws]
            assert len({p.digest(r) for r in requests}) == 1
            assert len({s["id"] for s in draws}) == 3
            assert all("seed" not in r and "seed" not in s for r, s in zip(requests, draws))
            assert requests[0]["messages"][1] == {"role": "assistant", "content": source}
            assert requests[0]["max_tokens"] == 4096
            assert requests[0]["reasoning"] == {"effort": "medium"}
    with pytest.raises(ValueError):
        p.messages(draws[0], {"content": source, "reasoning": "never transplant"})


def test_routes_settings_and_role_specific_privacy():
    prior = json.loads((p.ROOT / "data/openrouter_swap/plan_a3_20261004/PLAN.json").read_text())
    assert p.MODELS == {model: prior["models"][model] for model in ("gemini", "opus")}
    assert p.JUDGES["astra"]["provider_slug"] == "azure/us"
    assert p.JUDGES["astra"]["input_price"] == "11"
    assert p.JUDGES["opus"]["provider_slug"] == "google-vertex/us"
    assert p.JUDGES["opus"]["output_price"] == "22"
    assert p.PRIVACY == {"generation": {"data_collection": "deny"},
                         "judges": {"data_collection": "deny", "zdr": True}}
    assert "temperature" not in p.MODELS["opus"]


@pytest.fixture
def local_binding(tmp_path, monkeypatch):
    (tmp_path / "bound.txt").write_text("synthetic bound source\n")
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(p, "source_paths", lambda: ["bound.txt"])
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(p.build(metadata())))
    return path


def test_fixed_plan_predictions_budget_and_no_metadata_mutation(local_binding):
    external = metadata()
    original = deepcopy(external)
    plan = p.build(external)
    assert external == original
    assert p.verify(local_binding) == plan
    assert plan["cap_usd"] == "130" and plan["screen_cap_usd"] == "15"
    assert plan["funded_allowance_usd_at_snapshot"] == "122.058468203"
    assert not plan["qualification"]["new_behavioral_gate"]
    assert plan["qualification"]["past_qualification_and_main_outcomes_seen"]
    assert plan["initial_inspection"]["included_in_main"]
    assert not plan["initial_inspection"]["outcome_selection"]
    assert plan["analysis"]["primary_family_size"] == 2
    assert plan["analysis"]["individual_confidence"] == 0.975
    assert plan["analysis"]["bootstrap_replicates"] == 10000
    assert plan["projection"]["multiplier"] == 1.3
    assert plan["launch_authorized"]
    assert not plan["authorization"]["requires_owner_approval_of_freeze"]
    plan["models"]["opus"]["id"] = "tampered"
    assert p.MODELS["opus"]["id"] != "tampered"


@pytest.mark.parametrize("balance,expected", [("165", "120"), ("167.058468203", "122.058468203"),
                                               ("999", "130"), ("44", "0")])
def test_snapshot_funding_not_new_authorization(balance, expected):
    value = metadata()
    value["account_balance_usd"] = balance
    assert p.metadata_funding(value) == Decimal(expected)


@pytest.mark.parametrize("key,value", [("approved", False), ("approved", 1),
    ("fetched_at_utc", "2026-10-04"), ("account_balance_usd", "NaN"),
    ("account_balance_usd", "-1"), ("account_balance_usd", 165),
    ("external_reserve_usd", "44"), ("endpoint_snapshots", {}), ("zdr_endpoints", [])])
def test_metadata_rejections(key, value):
    data = metadata()
    data[key] = value
    with pytest.raises((ValueError, TypeError)):
        p.build(data)


@pytest.mark.parametrize("mutation", ["draw", "cell", "prediction", "budget", "privacy", "bootstrap", "source"])
def test_plan_tampering_rejected(local_binding, mutation):
    plan = json.loads(local_binding.read_text())
    if mutation in {"draw", "cell"}:
        plan["main"][0]["finals"][0][mutation] = 99
    elif mutation == "prediction":
        plan["predictions"]["gemini"]["direction"] = "negative"
    elif mutation == "budget":
        plan["cap_usd"] = "131"
    elif mutation == "privacy":
        plan["privacy"]["generation"]["zdr"] = True
    elif mutation == "bootstrap":
        plan["analysis"]["individual_confidence"] = 0.95
    else:
        (p.ROOT / "bound.txt").write_text("changed bound source")
    local_binding.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="differs"):
        p.verify(local_binding)


def test_freeze_checks_bytes_and_branch_without_real_git_or_network(local_binding, monkeypatch):
    freeze = "a" * 40
    source = (p.ROOT / "bound.txt").read_bytes()
    plan_bytes = local_binding.read_bytes()

    def git(command, **kwargs):
        if command[1] == "show":
            return source if command[2].endswith(":bound.txt") else plan_bytes
        assert command == ["git", "ls-remote", "origin", "refs/heads/" + p.BRANCH]
        return freeze + "\trefs/heads/" + p.BRANCH + "\n"

    monkeypatch.setattr(p.subprocess, "check_output", git)
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    p.verify(local_binding, freeze)
    with pytest.raises(ValueError, match="Full freeze"):
        p.verify(local_binding, "")
    source = b"different frozen source"
    with pytest.raises(ValueError, match="absent from freeze"):
        p.verify(local_binding, freeze)


def test_source_closure_has_active_dependencies_without_historical_cli_expansion():
    paths = p.source_paths()
    required = {"experiments/repeated_swap/protocol.py", "experiments/repeated_swap/analysis.py",
                "experiments/repeated_swap/PROTOCOL.md", "tests/test_repeated_swap_protocol.py",
                "tests/test_repeated_swap_analysis.py", "experiments/openrouter_swap/protocol.py",
                "experiments/openrouter_swap/providers.py", "experiments/openrouter_swap/ledger.py",
                "experiments/openrouter_swap/judges.py", "experiments/instruction_state_qualification/judges.py",
                "experiments/automated_rubric_audit/common.py", "experiments/automated_rubric_audit/run.py",
                "experiments/bilingual_llama_pilot/prompts.py", "src/prompts.py"}
    assert required <= set(paths)
    assert paths == sorted(set(paths))
    assert not any("sae_assay" in path or "berg_ensemble" in path or
                   "openrouter_swap_a3/amendment" in path for path in paths)
    assert all((p.ROOT / name).is_file() for name in paths)


@pytest.mark.parametrize("mutation", ["route", "status", "provider", "capacity", "temperature",
                                      "structured_outputs", "zdr", "price", "duplicate"])
def test_saved_endpoint_validator_fails_closed(mutation):
    data = metadata()
    generation = data["endpoint_snapshots"][p.MODELS["gemini"]["id"]]["endpoints"][0]
    judge = data["endpoint_snapshots"][p.JUDGES["astra"]["id"]]["endpoints"][0]
    if mutation == "route":
        generation["tag"] = "other-host"
    elif mutation == "status":
        generation["status"] = False
    elif mutation == "provider":
        generation["provider_name"] = "other-provider"
    elif mutation == "capacity":
        judge["max_completion_tokens"] = 5999
    elif mutation == "temperature":
        generation["supported_parameters"].remove("temperature")
    elif mutation == "structured_outputs":
        judge["supported_parameters"].remove("structured_outputs")
    elif mutation == "zdr":
        data["zdr_endpoints"][0]["tag"] = "other-route"
    elif mutation == "price":
        # Judge ceiling already includes its 10% route premium, no second uplift.
        judge["pricing"]["prompt"] = "0.00001101"
    else:
        data["endpoint_snapshots"][p.MODELS["gemini"]["id"]]["endpoints"].append(deepcopy(generation))
    with pytest.raises(ValueError):
        p.metadata_funding(data)
