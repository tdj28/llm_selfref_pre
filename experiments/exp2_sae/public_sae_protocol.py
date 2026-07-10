"""Pure conversation helpers for the public-SAE two-turn protocol."""

from __future__ import annotations


PROTOCOL_VERSION = "public_sae_two_turn_v2"


def induction_messages(induction: str) -> list[dict[str, str]]:
    if not induction.strip():
        return []
    return [{"role": "user", "content": induction}]


def final_query_messages(
    induction: str,
    induction_response: str,
    query: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if induction.strip():
        if not induction_response.strip():
            raise ValueError("A non-empty induction requires a real assistant continuation")
        messages.extend(
            [
                {"role": "user", "content": induction},
                {"role": "assistant", "content": induction_response},
            ]
        )
    messages.append({"role": "user", "content": query})
    return messages
