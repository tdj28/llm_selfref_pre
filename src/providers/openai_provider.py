from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI


@dataclass
class Completion:
    text: str
    raw: Any
    metadata: Dict[str, Any]


class OpenAIProvider:
    """
    Thin wrapper around the OpenAI Python SDK using the Responses API.

    Docs:
      - Responses API reference: https://platform.openai.com/docs/api-reference/responses
      - Python quickstart:      https://platform.openai.com/docs/overview?lang=python
    """

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
        load_dotenv()
        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
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
        """
        input_items:
          - string prompt, OR
          - list of {"role": "...", "content": "..."} dicts (developer/user/assistant)
        """
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                resp = self.client.responses.create(
                    model=self.model,
                    input=input_items,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    instructions=instructions,
                )
                # The SDK exposes convenience property output_text.
                usage = getattr(resp, "usage", None)
                if usage is None:
                    usage_dict: Dict[str, Any] = {}
                elif hasattr(usage, "model_dump"):
                    usage_dict = usage.model_dump(exclude_none=True)
                else:
                    usage_dict = {
                        key: getattr(usage, key)
                        for key in ("input_tokens", "output_tokens", "total_tokens")
                        if getattr(usage, key, None) is not None
                    }
                metadata = {
                    "response_id": getattr(resp, "id", None),
                    "resolved_model": getattr(resp, "model", None),
                    "created_at": getattr(resp, "created_at", None),
                    "status": getattr(resp, "status", None),
                    "incomplete_details": (
                        resp.incomplete_details.model_dump(exclude_none=True)
                        if getattr(resp, "incomplete_details", None) is not None
                        and hasattr(resp.incomplete_details, "model_dump")
                        else None
                    ),
                    "system_fingerprint": getattr(resp, "system_fingerprint", None),
                    "usage": usage_dict,
                }
                return Completion(text=resp.output_text, raw=resp, metadata=metadata)
            except Exception as e:
                last_err = e
                # basic exponential backoff
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"OpenAI request failed after {retries} retries: {last_err}")
