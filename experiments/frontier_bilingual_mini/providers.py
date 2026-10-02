"""Frozen native API configurations and conservative receipt accounting."""

from __future__ import annotations

from decimal import Decimal
import re

from experiments.automated_rubric_audit.common import canonical

MODELS = {
    "astra": {"provider": "openai", "id": "gpt-6-astra", "input_price": "10", "output_price": "50"},
    "opus": {"provider": "anthropic", "id": "claude-opus-5-5", "input_price": "4", "output_price": "20"},
    "gpt41": {"provider": "openai", "id": "gpt-4.1-2025-04-14", "input_price": "2", "output_price": "8"},
}
JUDGES = {"openai": "astra", "anthropic": "opus"}
OUTPUT_CAPS = {"astra": 4096, "opus": 4096, "gpt41": 768}


def generation_request(model, messages):
    """No system text, synthetic turn, unsupported temperature, or SDK retry."""
    spec = MODELS[model]
    if spec["provider"] == "openai":
        request = {"model": spec["id"], "input": messages, "store": False,
                   "service_tier": "default", "max_output_tokens": OUTPUT_CAPS[model]}
        if model == "astra":
            request["reasoning"] = {"effort": "medium"}
        else:
            request.update(temperature=0.5, top_p=1.0)
        return request
    return {"model": spec["id"], "messages": messages, "max_tokens": OUTPUT_CAPS[model],
            "extra_body": {"output_config": {"effort": "medium"}}}


def model_matches(key, value):
    expected = MODELS[key]["id"]
    return isinstance(value, str) and (value == expected or (
        key != "gpt41" and re.fullmatch(re.escape(expected) + r"-20\d{2}-\d{2}-\d{2}", value) is not None))


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {name}")
    return value


def receipt_cost(model, raw):
    """Upper bound: include reasoning, never credit cached-input discounts."""
    spec = MODELS[model]
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Usage unavailable")
    inp = Decimal(_integer(usage.get("input_tokens"), "input_tokens"))
    out = Decimal(_integer(usage.get("output_tokens"), "output_tokens"))
    if spec["provider"] == "openai":
        inp *= Decimal("1.25")
    else:
        inp += _integer(usage.get("cache_read_input_tokens", 0), "cache_read_input_tokens")
        inp += Decimal("1.25") * _integer(usage.get("cache_creation_input_tokens", 0), "cache_creation_input_tokens")
    return (inp * Decimal(spec["input_price"]) + out * Decimal(spec["output_price"])) / 1_000_000


def reservation(model, request):
    # UTF-8 bytes, not bytes/4: conservative for Chinese and schema-heavy inputs.
    inputs = len(canonical(request).encode("utf-8")) + 4096
    outputs = request.get("max_output_tokens", request.get("max_tokens"))
    _integer(outputs, "output cap")
    spec = MODELS[model]
    return (Decimal(inputs) * Decimal(spec["input_price"]) * Decimal("1.25")
            + Decimal(outputs) * Decimal(spec["output_price"])) / 1_000_000


def generation_result(model, raw):
    """Keep/judge nonempty capped text exactly as the Llama pilot does."""
    provider = MODELS[model]["provider"]
    if provider == "openai":
        content = [c for o in raw.get("output", []) if o.get("type") == "message"
                   for c in o.get("content", [])]
        text = "".join(c.get("text", "") for c in content if c.get("type") == "output_text")
        refused = any(c.get("type") == "refusal" for c in content)
        complete = raw.get("status") == "completed"
        stop = raw.get("status")
        cap_hit = (raw.get("incomplete_details") or {}).get("reason") == "max_output_tokens"
    else:
        text = "".join(c.get("text", "") for c in raw.get("content", []) if c.get("type") == "text")
        stop = raw.get("stop_reason")
        refused = stop == "refusal"
        complete = stop == "end_turn"
        cap_hit = stop == "max_tokens"
    if not isinstance(text, str):
        raise ValueError("Non-text response")
    status = "refusal" if refused else "incomplete" if not complete else "empty" if not text.strip() else "ok"
    return {"status": status, "response": text, "missing": refused or not text.strip(),
            "stop_reason": stop, "complete": complete and not refused, "cap_hit": cap_hit}


def live_sender():
    """Construct clients only after freeze, fixture and budget gates pass."""
    from anthropic import Anthropic
    from openai import OpenAI

    clients = {}

    def send(provider, request):
        if provider not in clients:
            clients[provider] = (OpenAI(max_retries=0, timeout=180, base_url="https://api.openai.com/v1")
                                 if provider == "openai" else
                                 Anthropic(max_retries=0, timeout=180, base_url="https://api.anthropic.com"))
        client = clients[provider]
        result = (client.responses.create(**request) if provider == "openai"
                  else client.messages.create(**request))
        return result.model_dump(mode="json", exclude_none=True)
    return send
