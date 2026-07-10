from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from dotenv import load_dotenv


@dataclass
class Completion:
    text: str
    raw: Any
    metadata: Dict[str, Any]


class AnthropicProvider:
    """Thin wrapper around the Anthropic Messages API."""

    def __init__(self, model: str, api_key: Optional[str] = None):
        load_dotenv()
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def complete(
        self,
        input_items: str | List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 512,
        instructions: Optional[str] = None,
        retries: int = 5,
    ) -> Completion:
        system_parts: list[str] = []
        messages: list[dict[str, str]] = []

        if instructions:
            system_parts.append(instructions)

        if isinstance(input_items, str):
            messages.append({"role": "user", "content": input_items})
        else:
            for item in input_items:
                role = item.get("role", "user")
                content = str(item.get("content", ""))
                if role in {"system", "developer"}:
                    system_parts.append(content)
                elif role == "assistant":
                    messages.append({"role": "assistant", "content": content})
                else:
                    messages.append({"role": "user", "content": content})

        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": max_output_tokens,
                    "messages": messages,
                    "temperature": temperature,
                }
                if system_parts:
                    kwargs["system"] = "\n\n".join(system_parts)
                resp = self.client.messages.create(**kwargs)
                text = "".join(
                    block.text
                    for block in resp.content
                    if getattr(block, "type", None) == "text"
                )
                usage = getattr(resp, "usage", None)
                if usage is None:
                    usage_dict: Dict[str, Any] = {}
                elif hasattr(usage, "model_dump"):
                    usage_dict = usage.model_dump(exclude_none=True)
                else:
                    usage_dict = {
                        key: getattr(usage, key)
                        for key in ("input_tokens", "output_tokens")
                        if getattr(usage, key, None) is not None
                    }
                metadata = {
                    "response_id": getattr(resp, "id", None),
                    "resolved_model": getattr(resp, "model", None),
                    "created_at": getattr(resp, "created_at", None),
                    "stop_reason": getattr(resp, "stop_reason", None),
                    "stop_sequence": getattr(resp, "stop_sequence", None),
                    "usage": usage_dict,
                }
                return Completion(text=text, raw=resp, metadata=metadata)
            except Exception as e:
                last_err = e
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"Anthropic request failed after {retries} retries: {last_err}")
