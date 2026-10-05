"""Plan-supplied OpenRouter requests, receipt checks, and one-shot transport.

Prices are USD per million tokens. Optional spec fields are
``model_aliases`` (an explicit list), ``temperature=0.5`` (only when verified
by the plan), or ``supports_temperature=True``. Importing does no I/O.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import math

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 6000


class ReceiptError(ValueError):
    """The receipt does not satisfy the selected model/provider contract."""


class TransportError(RuntimeError):
    """Sanitized transport failure; no response body, headers, or client."""

    def __init__(self, status_code=None):
        self.status_code = status_code if type(status_code) is int else None
        super().__init__("OpenRouter request failed; outcome may be billable; no retry")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _amount(value):
    if type(value) not in (str, int, float, Decimal):
        raise ValueError("Invalid nonnegative USD amount")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid nonnegative USD amount") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid nonnegative USD amount")
    return result


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid nonnegative token count")
    return value


def _public_body(value):
    """Reject transport envelopes instead of quietly altering audit records."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            normalized = key.lower().replace("-", "_")
            if normalized in {"headers", "request_headers", "response_headers",
                              "authorization", "proxy_authorization", "api_key",
                              "apikey", "x_api_key", "cookie", "set_cookie"}:
                raise ValueError("Credentials and headers are not public records")
            _public_body(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _public_body(item)


def _spec(spec):
    if not isinstance(spec, dict):
        raise ValueError("Model spec must be a dictionary")
    for key in ("id", "provider_slug", "provider_name", "reasoning_effort"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError("Model spec is missing a required string")
    if spec["provider_slug"].rsplit("/", 1)[-1].lower() in {
            "flex", "fast", "priority", "ultrafast"}:
        raise ValueError("Non-default provider tiers are forbidden")
    aliases = spec.get("model_aliases", [])
    if not isinstance(aliases, list) or any(not isinstance(a, str) or not a for a in aliases):
        raise ValueError("Model aliases must be an explicit list of strings")
    if type(spec.get("supports_temperature", False)) is not bool:
        raise ValueError("Temperature support must be a boolean")
    if "temperature" in spec and (type(spec["temperature"]) not in (int, float)
                                  or spec["temperature"] != 0.5):
        raise ValueError("The verified temperature must be 0.5")
    if "temperature" in spec and spec.get("supports_temperature") is False:
        raise ValueError("Conflicting temperature support declaration")
    return _amount(spec.get("input_price")), _amount(spec.get("output_price"))


def generation_request(spec, messages, max_tokens=4096):
    """Return one Chat Completions body; no fallback models or transforms."""
    input_price, output_price = _spec(spec)
    if not 1 <= _integer(max_tokens) <= MAX_TOKENS:
        raise ValueError("Completion cap must be between 1 and 6000")
    if not isinstance(messages, list):
        raise ValueError("Messages must be a list")
    for message in messages:
        if (not isinstance(message, dict) or message.get("role") not in
                {"system", "user", "assistant"} or not isinstance(message.get("content"), str)):
            raise ValueError("Only text chat messages are supported")
    prices = [float(input_price), float(output_price)]
    if not all(math.isfinite(p) for p in prices):
        raise ValueError("Price ceiling is not representable")
    request = {"model": spec["id"], "messages": deepcopy(messages),
               "max_tokens": max_tokens, "reasoning": {"effort": spec["reasoning_effort"]},
               "provider": {"only": [spec["provider_slug"]], "allow_fallbacks": False,
                            "require_parameters": True,
                            "max_price": {"prompt": prices[0], "completion": prices[1]}},
               "service_tier": "default", "stream": False}
    if "temperature" in spec or spec.get("supports_temperature") is True:
        request["temperature"] = 0.5
    _public_body(request)
    _canonical(request)
    return request


def parse_result(spec, raw):
    """Extract assistant content only, retaining capped, missing and refused text.

    Identity/tier failures raise ReceiptError. Persist the unmodified raw body
    even when this check fails. A null/absent service tier is not verification.
    """
    _spec(spec)
    if not isinstance(raw, dict):
        raise ReceiptError("Receipt must be a dictionary")
    if not isinstance(raw.get("id"), str) or not raw["id"].strip():
        raise ReceiptError("Completion receipt ID missing")
    if raw.get("model") not in [spec["id"], *spec.get("model_aliases", [])]:
        raise ReceiptError("Model receipt mismatch")
    if raw.get("provider") != spec["provider_name"]:
        raise ReceiptError("Provider receipt missing or mismatched")
    tier = raw.get("service_tier")
    if tier is not None and tier != "default":
        raise ReceiptError("Non-default service tier receipt")
    if raw.get("error") is not None:
        raise ReceiptError("Provider returned an error receipt")
    choices = raw.get("choices", [])
    if not isinstance(choices, list) or len(choices) > 1:
        raise ReceiptError("Expected at most one completion")
    choice = choices[0] if choices else {}
    if not isinstance(choice, dict):
        raise ReceiptError("Invalid completion choice")
    message = choice.get("message") or {}
    if not isinstance(message, dict) or (message and message.get("role") != "assistant"):
        raise ReceiptError("Expected an assistant message")
    content = message.get("content")
    refused = bool(message.get("refusal"))
    if content is None:
        text = ""
    elif isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                raise ReceiptError("Invalid assistant content block")
            if part.get("type") == "text":
                if not isinstance(part.get("text"), str):
                    raise ReceiptError("Non-text assistant content")
                parts.append(part["text"])
            elif part.get("type") == "refusal":
                refused = True
        text = "".join(parts)
    else:
        raise ReceiptError("Non-text assistant content")
    stop = choice.get("finish_reason")
    native_stop = choice.get("native_finish_reason")
    if any(v is not None and not isinstance(v, str) for v in (stop, native_stop)):
        raise ReceiptError("Invalid finish reason")
    refused = refused or stop in {"content_filter", "refusal"} or native_stop == "refusal"
    cap_hit = stop == "length" or native_stop in {"max_tokens", "max_output_tokens", "length"}
    complete = stop == "stop" and not refused and not cap_hit
    missing = refused or not text.strip()
    status = "refusal" if refused else "incomplete" if not complete else "empty" if missing else "ok"
    return {"status": status, "response": text, "missing": missing, "refusal": refused,
            "stop_reason": stop, "native_finish_reason": native_stop,
            "complete": complete, "cap_hit": cap_hit, "model": raw["model"],
            "provider": raw["provider"], "service_tier": tier,
            "service_tier_verified": tier == "default"}


def receipt_cost(spec, raw):
    """Return Decimal max(reported charge, token bound), or None if incomplete.

    OpenRouter completion_tokens includes reasoning_tokens; adding the latter
    again would double count. No cached-input discount is credited. Malformed
    or contradictory accounting raises ValueError and must keep the reserve.
    See https://openrouter.ai/docs/cookbook/administration/usage-accounting
    and https://openrouter.ai/docs/guides/best-practices/reasoning-tokens .
    """
    input_price, output_price = _spec(spec)
    usage = raw.get("usage") if isinstance(raw, dict) else None
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise ValueError("Invalid usage receipt")
    if any(usage.get(k) is None for k in ("prompt_tokens", "completion_tokens")):
        return None
    inputs = _integer(usage["prompt_tokens"])
    outputs = _integer(usage["completion_tokens"])
    details = usage.get("completion_tokens_details")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise ValueError("Invalid completion token details")
    reasoning = details.get("reasoning_tokens")
    if reasoning is not None and _integer(reasoning) > outputs:
        raise ValueError("Reasoning exceeds total completion tokens")
    total = usage.get("total_tokens")
    if total is not None:
        if _integer(total) < inputs + outputs:
            raise ValueError("Total tokens undercount prompt and completion")
        outputs = max(outputs, total - inputs)
    bound = (Decimal(inputs) * input_price + Decimal(outputs) * output_price) / 1_000_000
    cost = usage.get("cost")
    return bound if cost is None else max(bound, _amount(cost))


def reservation(spec, request):
    """Reserve UTF-8 request bytes + 4096 input tokens and the full output cap."""
    input_price, output_price = _spec(spec)
    if not isinstance(request, dict) or request.get("model") != spec["id"]:
        raise ValueError("Request does not match model spec")
    outputs = _integer(request.get("max_tokens"))
    if not 1 <= outputs <= MAX_TOKENS:
        raise ValueError("Invalid completion cap")
    _public_body(request)
    inputs = len(_canonical(request).encode("utf-8")) + 4096
    return (Decimal(inputs) * input_price + Decimal(outputs) * output_price) / 1_000_000


def live_sender(api_key):
    """Return send(request) -> raw dict: one POST, no redirects or retry.

    Construct only after the caller's plan and budget gates. HTTP error bodies
    and exception messages are deliberately not exposed to the caller/logs.
    """
    if not isinstance(api_key, str) or not api_key or any(c.isspace() for c in api_key):
        raise ValueError("A nonempty API key without whitespace is required")

    def send(request):
        from urllib import error, request as http

        class NoRedirect(http.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        status, raw, failed = None, None, False
        try:
            _public_body(request)
            body = _canonical(request).encode("utf-8")
            if api_key in body.decode("utf-8"):
                raise ValueError("Credential in body")
            req = http.Request(ENDPOINT, data=body, method="POST", headers={
                "Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
            opener = http.build_opener(NoRedirect())
            with opener.open(req, timeout=180) as response:
                status = response.status
                if status != 200:
                    raise ValueError("Non-success HTTP status")
                payload = response.read().decode("utf-8")
                if api_key in payload:
                    raise ValueError("Credential in response")
                raw = json.loads(payload)
                if not isinstance(raw, dict) or raw.get("error") is not None:
                    raise ValueError("Invalid completion response")
                _public_body(raw)
                _canonical(raw)
        except error.HTTPError as exc:
            status, failed = exc.code, True
            exc.close()
        except Exception:
            failed = True
        # Raise outside the handler: even __context__ must not retain secrets.
        if failed:
            raise TransportError(status)
        return raw

    return send
