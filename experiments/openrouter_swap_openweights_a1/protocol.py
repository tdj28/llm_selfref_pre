"""Same four-comparison design, separately bound route/accounting amendment."""

from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap_openweights import protocol as old

Budget, MODELS, PRIVACY = old.Budget, old.MODELS, old.PRIVACY
inventory, project, FAMILY_SIZE = old.inventory, old.project, old.FAMILY_SIZE
JUDGES = deepcopy(old.JUDGES)
JUDGES["opus"].update(provider_slug="google-vertex/us", provider_name="Google")
OLD_PLAN = "data/openrouter_swap_openweights/plan_v1/PLAN.json"
PREDECESSOR_RELEASE = "data/openrouter_swap_openweights/fixture_failure_v1_20261004/RELEASE.json"
PRIOR_PANEL = Decimal("84.08770746")
FAILED_COST = Decimal("0.5550459")
PREDECESSOR = {
    "freeze": "29ecac9ba3cd2dd59c98938203e0ba1b981e7b96",
    "journal_sha256": "65de501ae0107a505ad3a8d29730bbf1ce3f37eaf4cb5027d34f88d7d089a975",
    "release_sha256": "76b68ccfb92c779c39d10df0523311434f65ec2fb68cede2d557b064a119777e",
    "calls": 12, "settled": 9, "unresolved": 3,
    "cost_bound_usd": str(FAILED_COST), "research_calls": 0,
}
AMENDMENT = {
    "technical_fixture_outcomes_seen": True, "research_outcomes_seen": False,
    "prior_route_acknowledgments_seen": True, "prior_synthetic_judge_outputs_seen": True,
    "predecessor": PREDECESSOR, "reuse_predecessor_receipts": False,
    "mistral_accounting": "contradictory-output-sum-upper-bound-v1",
    "mistral_reservation": "full-output-cap-for-each-reported-component-v1",
    "judge_capability": "response_format-and-structured_outputs",
    "endpoint_status": 0,
}


def build_draft(*, budget):
    plan = old.build_draft(budget=budget)
    plan.update(schema="openrouter-openweights-a1-offline-draft-v1",
                judges=deepcopy(JUDGES), amendment=deepcopy(AMENDMENT))
    return plan


def verify_draft(plan):
    budget = Budget(**plan["budget"])
    if common.canonical(plan) != common.canonical(build_draft(budget=budget)):
        raise Halted("Draft differs from the fixed A1 repair")
    return budget


def finalize_plan(draft, **inputs):
    from .production import finalize
    return finalize(draft, **inputs)
