"""Offline A3 checks; synthetic fixtures are not scientific outcomes."""

from collections import Counter
from copy import deepcopy
from decimal import Decimal
import inspect
import json

import pytest

from experiments.openrouter_swap import analysis, judges, protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.providers import parse_result
from experiments.openrouter_swap.runner import Runner, canonical_run_root
from experiments.openrouter_swap_a2 import amendment as a2
from experiments.openrouter_swap_a3 import amendment
from tests.test_openrouter_swap_judges import fixture_rows


def original_gate(response="OK.", *, finish_reason="stop", refusal=None):
    rows = fixture_rows()
    routes = []
    for name in ("gemini", "sonnet", "opus"):
        spec = protocol.MODELS[name]
        message = {"role": "assistant", "content": response if name == "gemini" else "OK"}
        if name == "gemini" and refusal is not None:
            message["refusal"] = refusal
        raw = {
            "id": "synthetic-route-" + name,
            "model": spec["id"],
            "provider": spec["provider_name"],
            "choices": [{"finish_reason": finish_reason if name == "gemini" else "stop",
                         "message": message}],
        }
        parsed = parse_result(spec, raw)
        routes.append({"pass": parsed["complete"] and parsed["response"].strip() == "OK", **parsed})
    judge_gate = judges.fixture_gate(rows)
    return {"pass": judge_gate["pass"] and all(route["pass"] for route in routes),
            "judges": judge_gate, "routes": routes, "rows": rows}


@pytest.mark.parametrize("response", ["OK", "OK.", " \tOK.\r\n"])
def test_adjudication_accepts_only_declared_punctuation_without_rewriting_history(response):
    old = original_gate(response)
    before = deepcopy(old)
    result = amendment.adjudicate_gate(old)
    assert result["pass"] is True
    assert result["original_gate"] == before
    assert len(result["original_gate"]["routes"]) == 3
    assert len(result["original_gate"]["rows"]) == 24
    assert old == before
    if response.strip() == "OK.":
        assert result["original_gate"]["pass"] is False
        assert result["original_gate"]["routes"][0]["pass"] is False
    old["routes"][0]["response"] = "Changed after adjudication"
    old["rows"][0]["raw_text"] = "Changed after adjudication"
    assert result["original_gate"] == before


@pytest.mark.parametrize("response", ["", "ok", "OK!", "OK..", "OK. More text"])
def test_adjudication_rejects_other_route_text(response):
    old = original_gate(response)
    before = deepcopy(old)
    result = amendment.adjudicate_gate(old)
    assert result["pass"] is False
    assert result["original_gate"]["pass"] is False
    assert result["original_gate"] == before
    assert old == before


@pytest.mark.parametrize("failure", ["refusal", "capped"])
def test_adjudication_rejects_incomplete_routes_even_with_ok_period(failure):
    old = original_gate("OK.", **({"refusal": "Synthetic refusal"} if failure == "refusal"
                                  else {"finish_reason": "length"}))
    route = old["routes"][0]
    assert route["response"] == "OK."
    assert route["complete"] is False
    assert route["refusal" if failure == "refusal" else "cap_hit"] is True
    result = amendment.adjudicate_gate(old)
    assert result["pass"] is False
    assert result["original_gate"] == old


def test_punctuation_cannot_override_a_failed_judge_gate():
    old = original_gate()
    old["rows"][0]["status"] = "incomplete_judge"
    old["judges"] = judges.fixture_gate(old["rows"])
    assert old["judges"]["pass"] is False
    result = amendment.adjudicate_gate(old)
    assert result["pass"] is False
    assert result["original_gate"] == old


def test_scientific_design_keeps_three_routes_four_inventory_slots_and_eight_comparisons():
    previous = a2.verify(protocol.ROOT / a2.PLAN)
    plan = amendment.build()
    assert amendment.ACTIVE_MODELS == a2.ACTIVE_MODELS == ("gemini", "sonnet", "opus")
    for key in (
        "models", "active_models", "deferred_models", "screen", "main", "judges",
        "fixtures", "qualification", "analysis", "projection", "retries",
        "neutral_instruction", "experiential_query", "endpoint_metadata",
        "generation_output_cap", "generation_workers", "judge_workers", "publication",
    ):
        assert plan[key] == previous[key], key
    assert plan["analysis"]["primary_family_size"] == analysis.FAMILY_SIZE == 8
    for phase, blocks in (("screen", 12), ("main", 32)):
        assert Counter(block["model"] for block in plan[phase]) == {
            "gemini": blocks, "sonnet": blocks, "opus": blocks, "deepseek": blocks,
        }


def test_prior_costs_reduce_both_caps_exactly_without_reset():
    plan = amendment.build()
    assert amendment.PRIOR_COST == Decimal("0.62048546")
    assert sum((Decimal(prior["cost_bound_usd"]) for prior in amendment.PRIORS),
               Decimal(0)) == amendment.PRIOR_COST
    assert Decimal(plan["prior_cost_usd"]) == amendment.PRIOR_COST
    assert Decimal(plan["cap_usd"]) == Decimal("249.37951454")
    assert Decimal(plan["screen_cap_usd"]) == Decimal("39.37951454")
    assert plan["prior_attempts"] == amendment.PRIORS


def test_third_prior_binds_the_completed_a2_fixture_attempt():
    assert len(amendment.PRIORS) == 3
    assert amendment.PRIORS[:2] == a2.PRIORS
    prior = amendment.PRIORS[2]
    assert prior["label"] == prior["path"] == "a2"
    assert prior["freeze"] == "bae7b50d6e2eb2213ea7a4518904ef268c600042"
    assert prior["plan_path"] == a2.PLAN
    assert prior["plan_sha256"] == "7205ff349219b71bfbc8f83656e547acecd58767e60d07024a061793eb87a56e"
    assert protocol.sha(protocol.ROOT / a2.PLAN) == prior["plan_sha256"]
    assert Decimal(prior["cost_bound_usd"]) == Decimal("0.357945")
    assert prior["calls"] == 27
    assert prior["target_calls"] == prior["unresolved"] == 0


def test_a3_uses_a_new_sibling_root():
    assert amendment.canonical_run_root() == canonical_run_root() / "a3"
    assert amendment.canonical_run_root() != a2.canonical_run_root()


def test_runner_reuses_gate_without_new_calls_or_charges(tmp_path):
    plan = amendment.build()
    gate = amendment.adjudicate_gate(original_gate())
    before = deepcopy(gate)

    def forbidden_sender(request):
        pytest.fail("Reusing A2 fixtures must not dispatch any request")

    with Ledger(tmp_path, cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
        runner = amendment.A3Runner(plan, "a" * 40, "b" * 64, ledger,
                                    forbidden_sender, fixture_gate=gate)
        assert isinstance(runner, a2.IndependentRunner)
        assert type(runner).audit is Runner.audit
        for _ in range(2):
            assert runner.run_fixtures() == before
            assert runner.require_fixtures() == before
        audit = runner.audit()
        assert audit["pass"] is True
        assert audit["calls"] == audit["unresolved"] == 0
        assert Decimal(audit["cost_bound_usd"]) == ledger.spent() == Decimal(0)
        assert ledger.rows() == []
    assert gate == before


def test_runner_requires_explicit_verified_gate_keyword():
    parameter = inspect.signature(amendment.A3Runner).parameters["fixture_gate"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_failed_gate_cannot_qualify_targets(tmp_path):
    plan = amendment.build()
    gate = amendment.adjudicate_gate(original_gate("not OK"))
    with Ledger(tmp_path) as ledger:
        with pytest.raises(Halted):
            runner = amendment.A3Runner(plan, "a" * 40, "b" * 64, ledger, fixture_gate=gate)
            runner.require_fixtures()
        assert ledger.rows() == []


@pytest.mark.parametrize("tampered", [False, True])
def test_verify_rebuilds_plan_offline_and_rejects_accounting_change(tmp_path, tampered):
    plan = amendment.build()
    if tampered:
        plan["cap_usd"] = "250"
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    if tampered:
        with pytest.raises(Halted):
            amendment.verify(path)
    else:
        assert amendment.verify(path) == plan
