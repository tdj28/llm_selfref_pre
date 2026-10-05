"""Unchanged A1 science with a separately bound continuation authority."""
from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap_openweights_a1 import protocol as a1

Budget, MODELS, JUDGES, PRIVACY = a1.Budget, a1.MODELS, a1.JUDGES, a1.PRIVACY
PLAN = "data/openrouter_swap_openweights_a2/plan_v1/PLAN.json"
A1_PLAN = "data/openrouter_swap_openweights_a1/plan_v1/PLAN.json"
FAILURE = "data/openrouter_swap_openweights_a1/initial_failure_v1_20261004"
FAILURE_SHA = "08b863d58f469e8001bba66f61b242bc34f54e998cd9668391049e247965b167"
PREFIX_COST = Decimal("1.84767560")
PRIOR = Decimal("86.49042896")
SCREEN = Decimal("22.59727850")
PREFIX = {
    "freeze": "9407bae95d759de4f64b4f34d03281164f4ecae9",
    "plan_sha256": "caa54bbe9aae1fa7ff43427cbb74f2d669c5c48b9e299033980f4187ff33b667",
    "journal_sha256": "ee84f0d4e6387c261ad35ce7b35be1c6a05f3e11a011c33e40ba2e65930e6ef6",
    "journal_bytes": 1000434, "events": 185, "calls": 92,
    "head": "ecc017b5e18318a521a0bdba3fe9191917eb4e99dc444e719146bfa19613dc4a",
    "fixture_events": 53,
    "fixture_prefix_sha256": "27578cb69129f0486b78565a3d8c29e2e241768148457fcab37cb04b767a4443",
    "cost_bound_usd": str(PREFIX_COST),
}
EXCEPTION = {
    "call_id": "gen:openweights-screen-mistral-02-final-SH",
    "reserve_event_sha256": "b0d597b5e188d85d74bab7714c2a70d5cc05f79888a3556a87db7d81bf4addbb",
    "settle_event_sha256": "62bc478043543a104911be4efda797f0534a8be730f17e5b0825d31c9606b66d",
    "request_sha256": "aaa595663ec4d1730f81a1c865f554fcc113f5cba3c8a8a732e6b4dfbd66f06d",
    "raw_sha256": "e647993597939677700cffdc554eba23e755a4b8510b53940448fa1e304cd611",
    "reservation_usd": "0.06927", "cost_usd": "0.0741945",
    "prompt_tokens": 163, "completion_tokens": 4096, "reasoning_tokens": 5764, "total_tokens": 4259,
    "reported_charge_usd": "0.0309645",
}
AMENDMENT = {
    "research_outcomes_seen": True, "technical_continuation_only": True,
    "prefix": PREFIX, "acknowledged_historical_overreservation": EXCEPTION,
    "reuse_all_92_calls": True, "new_fixture_calls": False,
    "mistral_reservation": "four-output-caps-v1", "generation_output_cap": 4096,
    "scientific_design_changed": False, "missing_or_capped_generation_retry": False,
    "prefix_cost_already_in_prior": str(PREFIX_COST),
}


def check_budget(budget):
    cap, screen = budget.limits()
    if (Decimal(budget.prior_spend_usd) != PRIOR or Decimal(budget.hard_cap_usd) > 200
            or Decimal(budget.screening_allowance_usd) > SCREEN or cap > Decimal("113.50957104")):
        raise Halted("A2 cannot reset prior spending or provider/screen allowances")
    return cap, screen


def build_draft(*, budget):
    check_budget(budget)
    plan = a1.build_draft(budget=budget)
    plan.update(schema="openweights-a2-draft-v1", amendment=deepcopy(AMENDMENT))
    return plan


def verify_draft(plan):
    budget = Budget(**plan["budget"])
    if common.canonical(plan) != common.canonical(build_draft(budget=budget)):
        raise Halted("Changed A2 science, inventory, privacy, or continuation binding")
    return budget


class ForecastBudget(Budget):
    """Old forecasting sees all observations; A1 was already charged in prior."""

    def admission(self, *, spent_usd, remaining_usd):
        observed = Decimal(spent_usd)
        if observed < PREFIX_COST:
            raise Halted("Forecast lost the immutable observed prefix")
        result = super().admission(spent_usd=observed - PREFIX_COST, remaining_usd=remaining_usd)
        return {**result, "observed_prefix_and_delta_usd": str(observed),
                "prefix_already_in_prior_usd": str(PREFIX_COST)}
