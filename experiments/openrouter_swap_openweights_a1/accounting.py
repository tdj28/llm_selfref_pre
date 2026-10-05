"""Explicit read-only Mistral usage projection, never a rewritten receipt."""

from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.providers import (
    _amount, _integer, parse_result, receipt_cost, reservation as common_reservation,
)
from .protocol import MODELS


def reservation(spec, request):
    """Pad only exact Mistral for two independently reported output components."""
    base = common_reservation(spec, request)
    padding = (Decimal(request["max_tokens"]) * _amount(spec["output_price"]) / 1_000_000
               if spec == MODELS["mistral"] else Decimal(0))
    return base + padding


def accounting(spec, raw):
    """Return cost bound, audit disclosure and a detached common-auditor view.

    Only this exact Mistral configuration permits contradictory finite counts.
    Unknown or malformed usage still fails closed. Other providers retain the
    unchanged common accounting contract, including contradiction rejection.
    """
    if spec != MODELS["mistral"]:
        return receipt_cost(spec, raw), None, deepcopy(raw)
    parse_result(spec, raw)
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Mistral usage required")
    inputs = _integer(usage.get("prompt_tokens"))
    completion = _integer(usage.get("completion_tokens"))
    total = _integer(usage.get("total_tokens"))
    details = usage.get("completion_tokens_details")
    if not isinstance(details, dict):
        raise ValueError("Mistral reasoning usage required")
    reasoning = _integer(details.get("reasoning_tokens"))
    reported = usage.get("cost")
    if reported is not None:
        reported = _amount(reported)
    contradictory = reasoning > completion or total != inputs + completion
    outputs = max(completion + reasoning, total - inputs) if contradictory else completion
    bound = (Decimal(inputs) * Decimal(spec["input_price"])
             + Decimal(outputs) * Decimal(spec["output_price"])) / 1_000_000
    cost = max(bound, reported or Decimal(0))
    projection = deepcopy(raw)
    projection["usage"]["completion_tokens"] = outputs
    projection["usage"]["total_tokens"] = inputs + outputs
    if receipt_cost(spec, projection) != cost:
        raise ValueError("Accounting projection does not reconstruct")
    disclosure = {"schema": "mistral-accounting-a1-v1", "raw_sha256": common.digest(raw),
                  "discrepancy": contradictory, "prompt_tokens": inputs,
                  "completion_tokens": completion, "reasoning_tokens": reasoning,
                  "total_tokens": total, "conservative_output_tokens": outputs,
                  "reported_charge_usd": None if reported is None else str(reported),
                  "cost_bound_usd": str(cost)}
    return cost, disclosure, projection
