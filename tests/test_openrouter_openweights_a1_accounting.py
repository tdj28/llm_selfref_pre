"""Synthetic contradictory receipts; no model, provider or credential access."""

from copy import deepcopy
from decimal import Decimal

import pytest

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.providers import generation_request, receipt_cost, reservation as common_reservation
from experiments.openrouter_swap_openweights import protocol as old
from experiments.openrouter_swap_openweights_a1 import protocol as p
from experiments.openrouter_swap_openweights_a1.accounting import accounting, reservation
from tests.test_openrouter_openweights_runner import receipts as original_receipts


def budget(**overrides):
    values = dict(scope="OpenRouter cumulative only", working_cap_usd="200", hard_cap_usd="200",
                  prior_spend_usd="84.64275336", external_commitments_usd="10",
                  screening_allowance_usd="24.4449541")
    return p.Budget(**{**values, **overrides})


def usage():
    return {"prompt_tokens": 20, "completion_tokens": 57, "total_tokens": 77,
            "completion_tokens_details": {"reasoning_tokens": 59}, "cost": 0.0004575}


def receipts(plan, *, main=False):
    result = original_receipts(plan, main=main)
    for item in result.values():
        if item["raw"]["model"] == p.MODELS["mistral"]["id"]:
            item["raw"]["usage"] = usage()
    return result


def raw():
    return {"id": "synthetic-fixture", "model": p.MODELS["mistral"]["id"], "provider": "Mistral",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "OK."}}],
            "usage": usage()}


def test_exact_observed_accounting_pattern_is_overbounded_without_raw_mutation():
    original = raw(); saved = deepcopy(original)
    with pytest.raises(ValueError): receipt_cost(p.MODELS["mistral"], original)
    cost, report, projected = accounting(p.MODELS["mistral"], original)
    assert cost == Decimal(".000900")
    assert report["discrepancy"] is True
    assert report["conservative_output_tokens"] == 116
    assert report["raw_sha256"] == common.digest(saved)
    assert report["reported_charge_usd"] == "0.0004575"
    assert projected["usage"]["completion_tokens"] == 116
    assert projected["usage"]["total_tokens"] == 136
    assert receipt_cost(p.MODELS["mistral"], projected) == cost
    assert original == saved and projected is not original
    projected.pop("usage")
    assert original == saved


@pytest.mark.parametrize("spec", [p.MODELS["qwen"], p.MODELS["mistral"], *p.JUDGES.values(),
                                 {**p.MODELS["mistral"], "provider_slug": "mistral"}])
def test_reservation_padding_is_only_exact_mistral_and_not_a_bill(spec):
    request = generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}])
    original = deepcopy(request)
    delta = reservation(spec, request) - common_reservation(spec, request)
    assert delta == (Decimal(".03072") if spec == p.MODELS["mistral"] else 0)
    assert request == original


@pytest.mark.parametrize("total,reasoning,outputs,discrepancy", [
    (77, 30, 57, False), (70, 30, 87, True), (1000, 30, 980, True), (77, 59, 116, True),
])
def test_conservative_accounting_cases(total, reasoning, outputs, discrepancy):
    value = raw(); value["usage"]["total_tokens"] = total
    value["usage"]["completion_tokens_details"]["reasoning_tokens"] = reasoning
    value["usage"]["cost"] = "1"
    cost, report, _ = accounting(p.MODELS["mistral"], value)
    assert cost == 1 and report["discrepancy"] is discrepancy
    assert report["conservative_output_tokens"] == outputs


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"])
@pytest.mark.parametrize("bad", [None, -1, True, "59", 1.5])
def test_missing_negative_or_unknown_counts_never_relaxed(field, bad):
    value = raw()
    target = value["usage"]["completion_tokens_details"] if field == "reasoning_tokens" else value["usage"]
    target[field] = bad
    with pytest.raises(ValueError): accounting(p.MODELS["mistral"], value)


@pytest.mark.parametrize("bad", ["-1", "NaN", "Infinity", True])
def test_malformed_reported_charge_rejected(bad):
    value = raw(); value["usage"]["cost"] = bad
    with pytest.raises(ValueError): accounting(p.MODELS["mistral"], value)


@pytest.mark.parametrize("field,value", [("id", "other/model"), ("provider_slug", "mistral"),
                                        ("input_price", "1"), ("reasoning_effort", "low")])
def test_exception_is_exact_spec_only(field, value):
    spec = {**p.MODELS["mistral"], field: value}
    with pytest.raises(ValueError): accounting(spec, raw())


@pytest.mark.parametrize("spec", [p.MODELS["qwen"], *p.JUDGES.values()])
def test_other_providers_still_reject_reasoning_over_completion(spec):
    value = raw(); value.update(model=spec["id"], provider=spec["provider_name"])
    with pytest.raises(ValueError): accounting(spec, value)


@pytest.mark.parametrize("field,value", [("model", "wrong/model"), ("provider", "other"),
                                        ("service_tier", "priority")])
def test_mistral_identity_checks_unchanged(field, value):
    receipt = raw(); receipt[field] = value
    with pytest.raises(ValueError): accounting(p.MODELS["mistral"], receipt)


def test_only_declared_route_and_amendment_differ_from_scientific_design():
    b = budget(); current, previous = p.build_draft(budget=b), old.build_draft(budget=b)
    assert current.pop("amendment") == p.AMENDMENT
    current["schema"] = previous["schema"]
    current["judges"]["opus"] = previous["judges"]["opus"]
    assert current == previous
    assert p.inventory("screen") == old.inventory("screen")
    assert p.inventory("main") == old.inventory("main")
    assert p.FAMILY_SIZE == 4
