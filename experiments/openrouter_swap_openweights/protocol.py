"""Declared design and explicit budget inputs; importing performs no I/O."""

from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal
import random

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import _amount

MODELS = {
    "qwen": {"id": "qwen/qwen3.8-2.4t-a95b", "provider_slug": "together",
             "provider_name": "Together", "input_price": "2", "output_price": "6",
             "reasoning_effort": "low", "temperature": 0.5},
    "mistral": {"id": "mistralai/mistral-medium-3-5", "provider_slug": "mistral/zdr",
                "provider_name": "Mistral", "input_price": "1.5", "output_price": "7.5",
                "reasoning_effort": "high", "temperature": 0.5},
}
PRIVACY = {"data_collection": "deny", "zdr": True}
JUDGES = {
    "astra": {**common.JUDGES["astra"], "provider_slug": "azure/us",
              "provider_name": "Azure", "input_price": "11", "output_price": "55"},
    "opus": {**common.JUDGES["opus"], "provider_slug": "amazon-bedrock/us-east-1",
             "provider_name": "Amazon Bedrock", "input_price": "4.4", "output_price": "22"},
}
FAMILY_SIZE = 4
RESERVE = Decimal("1.30")


@dataclass(frozen=True, kw_only=True)
class Budget:
    """All amounts required; prior spend excludes the new extension ledger.

    External commitments cover full remaining authorized completion, including
    unresolved reservations, not merely currently running calls. A confirmed
    scope names all included studies; None explicitly means unresolved.
    """

    scope: str | None
    working_cap_usd: str
    hard_cap_usd: str
    prior_spend_usd: str
    external_commitments_usd: str
    screening_allowance_usd: str

    def __post_init__(self):
        if self.scope is not None and (not isinstance(self.scope, str) or not self.scope.strip()):
            raise ValueError("Scope must be explicit or unresolved")
        for name, value in asdict(self).items():
            if name != "scope":
                object.__setattr__(self, name, str(_amount(value)))
        if not 0 < _amount(self.working_cap_usd) <= _amount(self.hard_cap_usd):
            raise ValueError("Positive working cap must not exceed hard cap")

    def limits(self):
        if self.scope is None:
            raise Halted("Budget scope unresolved; no launch or plan finalization")
        available = (_amount(self.working_cap_usd) - _amount(self.prior_spend_usd)
                     - _amount(self.external_commitments_usd))
        if available <= 0 or _amount(self.screening_allowance_usd) <= 0:
            raise Halted("No funded extension allowance")
        return available, min(available, _amount(self.screening_allowance_usd))

    def admission(self, *, spent_usd, remaining_usd):
        cap, _ = self.limits()
        spent, remaining = _amount(spent_usd), _amount(remaining_usd)
        total = spent + remaining
        return {"fits": total <= cap, "extension_completion_usd": str(total),
                "scope_completion_usd": str(total + _amount(self.prior_spend_usd)
                                            + _amount(self.external_commitments_usd)),
                "remaining_unallocated_usd": str(cap - total)}


def project(phase, *, source_usd, final_usd, judge_slots_usd):
    """Retry-inclusive per-item means; four distinct judge/instrument slots."""
    expected = {(j, i) for j in common.JUDGES for i in judges.INSTRUMENTS}
    if set(judge_slots_usd) != expected or phase not in {"screen", "main"}:
        raise ValueError("Exact phase and four judge cost bases required")
    sources, finals = (24, 48) if phase == "screen" else (128, 256)
    judging = sum((_amount(v) for v in judge_slots_usd.values()), Decimal(0))
    return RESERVE * (sources * _amount(source_usd) + finals * (_amount(final_usd) + judging))


def inventory(phase):
    blocks = []
    for template in common.inventory(phase):
        if template["model"] != "gemini":
            continue
        for model in MODELS:
            block = deepcopy(template)
            block["model"] = model
            for item in block["sources"] + block["finals"]:
                item["model"] = model
                for key in ("id", "source_id"):
                    if key in item:
                        item[key] = "openweights-" + item[key].replace("-gemini-", f"-{model}-", 1)
            blocks.append(block)
    random.Random(20261004 + (phase == "main")).shuffle(blocks)
    return blocks


def build_draft(*, budget):
    if type(budget) is not Budget:
        raise TypeError("Explicit Budget required")
    return {"schema": "openrouter-openweights-offline-draft-v1", "launch_authorized": False,
            "budget": asdict(budget), "models": deepcopy(MODELS),
            "judges": deepcopy(JUDGES), "privacy": deepcopy(PRIVACY),
            "screen": inventory("screen"), "main": inventory("main"),
            "fixtures": judges.fixture_items(), "routing_acknowledgments": ["OK", "OK."],
            "generation_output_cap": 4096, "primary_family_size": FAMILY_SIZE,
            "main_cost_priority": list(MODELS), "projection_multiplier": str(RESERVE),
            "status": "offline_only_unfrozen"}


def verify_draft(plan):
    budget = Budget(**plan["budget"])
    if common.canonical(plan) != common.canonical(build_draft(budget=budget)):
        raise Halted("Draft differs from the declared extension design")
    return budget


def finalize_plan(draft, **inputs):
    from .production import finalize
    return finalize(draft, **inputs)
