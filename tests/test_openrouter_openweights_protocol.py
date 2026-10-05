"""Synthetic offline drafts, never production plans or collection approval."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import generation_request
from experiments.openrouter_swap_openweights import protocol as p
from experiments.openrouter_swap_openweights.runner import private_request


def budget(**changes):
    fields = dict(scope="synthetic API and GPU scope", working_cap_usd="100", hard_cap_usd="200",
                  prior_spend_usd="10", external_commitments_usd="20", screening_allowance_usd="15")
    return p.Budget(**{**fields, **changes})


def test_inventory_and_instruments_unchanged_and_disjoint():
    original = common.build({})
    plan = p.build_draft(budget=budget())
    assert plan["status"] == "offline_only_unfrozen" and not plan["launch_authorized"]
    assert plan["fixtures"] == original["fixtures"]
    for name, spec in plan["judges"].items():
        assert spec["id"] == original["judges"][name]["id"]
        assert spec["reasoning_effort"] == original["judges"][name]["reasoning_effort"]
    assert plan["judges"] == p.JUDGES
    inventories = {}
    for phase, counts in (("screen", (24, 48, 96)), ("main", (64, 256, 512))):
        blocks = plan[phase]
        assert (len(blocks), sum(len(b["sources"]) for b in blocks),
                sum(len(b["finals"]) for b in blocks)) == counts
        inventories[phase] = {s["id"] for b in blocks for s in b["sources"] + b["finals"]}
        assert not inventories[phase] & {s["id"] for b in original[phase] for s in b["sources"] + b["finals"]}
        for b in blocks:
            assert {s["source_id"] for s in b["finals"]} <= {s["id"] for s in b["sources"]}
            for spec in b["sources"] + b["finals"]:
                assert common.messages(spec, "visible continuation")
    assert inventories["screen"].isdisjoint(inventories["main"])
    assert common.build({}) == original


@pytest.mark.parametrize("model,effort,route", [("qwen", "low", "together"),
                                               ("mistral", "high", "mistral/zdr")])
def test_pinned_requests(model, effort, route):
    spec = p.MODELS[model]
    request = private_request(generation_request(spec, [{"role": "user", "content": "test"}]))
    assert request["model"] == spec["id"] and request["reasoning"] == {"effort": effort}
    assert request["temperature"] == .5 and request["max_tokens"] == 4096
    assert request["provider"] == {"only": [route], "allow_fallbacks": False, "require_parameters": True,
                                   "max_price": {"prompt": float(spec["input_price"]), "completion": float(spec["output_price"])},
                                   "data_collection": "deny", "zdr": True}
    assert request["service_tier"] == "default" and request["stream"] is False


def test_budget_has_no_defaults_and_never_borrows_hard_cap():
    with pytest.raises(TypeError):
        p.Budget()
    b = budget()
    assert b.limits() == (Decimal(70), Decimal(15))
    assert b.admission(spent_usd="15", remaining_usd="55")["fits"]
    denied = b.admission(spent_usd="15", remaining_usd="55.01")
    assert not denied["fits"] and Decimal(denied["scope_completion_usd"]) < Decimal(b.hard_cap_usd)
    assert not replace(b, external_commitments_usd="60").admission(spent_usd="10", remaining_usd="21")["fits"]
    with pytest.raises(Halted):
        replace(b, scope=None).limits()
    assert p.build_draft(budget=replace(b, scope=None))["budget"]["scope"] is None
    with pytest.raises(Halted):
        p.finalize_plan(p.build_draft(budget=b))


@pytest.mark.parametrize("judge,route,provider,prices", [
    ("astra", "azure/us", "Azure", (11., 55.)),
    ("opus", "amazon-bedrock/us-east-1", "Amazon Bedrock", (4.4, 22.)),
])
def test_judge_hosting_change_is_explicit_and_privacy_constrained(judge, route, provider, prices):
    spec = p.JUDGES[judge]
    request = private_request(generation_request(spec, [{"role": "user", "content": "test"}], 6000))
    assert spec["provider_name"] == provider
    assert request["provider"]["only"] == [route]
    assert request["provider"]["zdr"] is True
    assert request["provider"]["data_collection"] == "deny"
    assert request["provider"]["max_price"] == dict(zip(("prompt", "completion"), prices))
    assert request["reasoning"]["effort"] == "high"


@pytest.mark.parametrize("change", [{"prior_spend_usd": "NaN"}, {"external_commitments_usd": "-1"},
                                    {"working_cap_usd": "201"}, {"hard_cap_usd": True}, {"scope": ""}])
def test_bad_budget_rejected(change):
    with pytest.raises(ValueError):
        budget(**change)


def test_full_projection_includes_all_judge_slots_and_reserve():
    slots = {(j, i): "0.01" for j in common.JUDGES for i in judges.INSTRUMENTS}
    assert p.project("screen", source_usd=".02", final_usd=".03", judge_slots_usd=slots) == Decimal("4.992")
    assert p.project("main", source_usd=".02", final_usd=".03", judge_slots_usd=slots) == Decimal("26.624")
    slots.pop(("opus", "paper"))
    with pytest.raises(ValueError):
        p.project("main", source_usd=".02", final_usd=".03", judge_slots_usd=slots)


def test_draft_tampering_rejected():
    plan = p.build_draft(budget=budget())
    for key, value in (("primary_family_size", 8), ("routing_acknowledgments", ["OK", "Yes"]),
                       ("launch_authorized", True), ("main_cost_priority", ["mistral", "qwen"])):
        changed = deepcopy(plan)
        changed[key] = value
        with pytest.raises(Halted):
            p.verify_draft(changed)
