"""Fresh, deterministic tokenizer audit for the target-blind pilot.

This module is intentionally model-free: importing it or calling
``audit_tokenizer`` cannot instantiate model weights or perform a model
forward.  Its receipt records every accepted and rejected G1 candidate and
hard-fails any unresolved semantic or polarity endpoint.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from . import protocol


HEX64 = re.compile(r"[0-9a-f]{64}")
HASH_SELECTED_LEXICAL_PIECE = re.compile(r" [A-Za-z]{3,16}")
MAX_ATTEMPTS_PER_SLOT = 1_000_000
POLARITY_TOKEN_IDS = dict(protocol.G3P_ANSWER_TOKEN_IDS)


class TokenizerAuditError(RuntimeError):
    """A pinned tokenizer differs from the frozen prospective contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_json_bytes(value: Any) -> bytes:
    return protocol.canonical_json_bytes(value)


def canonical_sha256(value: Any) -> str:
    return protocol.canonical_sha256(value)


def token_ids_sha256(ids: Sequence[int]) -> str:
    return canonical_sha256([int(value) for value in ids])


def _encode(tokenizer: Any, piece: str) -> list[int]:
    return [int(value) for value in tokenizer.encode(piece, add_special_tokens=False)]


def _decode(tokenizer: Any, ids: Sequence[int]) -> str:
    return str(
        tokenizer.decode(
            [int(value) for value in ids],
            skip_special_tokens=False,
            clean_up_tokenization_spaces=False,
        )
    )


def _one_token_round_trip(tokenizer: Any, piece: str) -> int:
    ids = _encode(tokenizer, piece)
    if len(ids) != 1 or _decode(tokenizer, ids) != piece:
        raise TokenizerAuditError(
            "endpoint_multitoken",
            f"{piece!r} is not an exact one-token round trip",
        )
    return ids[0]


def _special_token_ids(tokenizer: Any) -> tuple[int, ...]:
    values = getattr(tokenizer, "all_special_ids", None)
    if not isinstance(values, (list, tuple, set)):
        raise TokenizerAuditError("special_ids", "tokenizer lacks all_special_ids")
    result = tuple(sorted({int(value) for value in values}))
    if not result:
        raise TokenizerAuditError("special_ids", "special-token inventory is empty")
    return result


def _experimental_lexicon_token_ids(tokenizer: Any) -> dict[str, list[int]]:
    return {
        word: _encode(tokenizer, f" {word}")
        for word in protocol.G1_TOKEN_REJECTION_LEXICON
    }


def _candidate_decision(
    tokenizer: Any,
    token_id: int,
    *,
    accepted_ids: set[int],
    special_ids: set[int],
) -> tuple[str, str, str]:
    """Return ``(decision, reason, exact_piece)`` for one frozen candidate."""

    if token_id in accepted_ids:
        return "reject", "duplicate_id", ""
    if token_id in special_ids:
        return "reject", "special_token_id", ""
    piece = _decode(tokenizer, [token_id])
    if _encode(tokenizer, piece) != [token_id] or _decode(tokenizer, [token_id]) != piece:
        return "reject", "token_does_not_exactly_round_trip", piece
    if HASH_SELECTED_LEXICAL_PIECE.fullmatch(piece) is None:
        return (
            "reject",
            "decoded_piece_does_not_fullmatch_ASCII_space_word_[A-Za-z]{3,16}",
            piece,
        )
    word = piece[1:]
    if word.casefold() in {item.casefold() for item in protocol.G1_TOKEN_REJECTION_LEXICON}:
        return "reject", "casefolded_word_is_in_G1_TOKEN_REJECTION_LEXICON", piece
    return "accept", "accepted", piece


def resolve_g1_panel(tokenizer: Any) -> dict[str, Any]:
    """Resolve 32 tokens from the frozen candidate stream and record all draws."""

    special_ids = _special_token_ids(tokenizer)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    sequence: list[dict[str, Any]] = []
    accepted_ids: set[int] = set()
    for index in range(protocol.G1_TOKEN_PANEL_SIZE):
        resolved = False
        for attempt in range(MAX_ATTEMPTS_PER_SLOT):
            token_id = protocol.g1_token_candidate_id(index, attempt)
            decision, reason, piece = _candidate_decision(
                tokenizer,
                token_id,
                accepted_ids=accepted_ids,
                special_ids=set(special_ids),
            )
            row = {
                "sequence_index": len(sequence),
                "panel_index": index,
                "attempt": attempt,
                "token_id": token_id,
                "exact_piece": piece,
                "decision": decision,
                "reason": reason,
            }
            sequence.append(row)
            if decision == "accept":
                accepted_ids.add(token_id)
                accepted.append(row)
                resolved = True
                break
            rejected.append(row)
        if not resolved:
            raise TokenizerAuditError(
                "g1_panel_unresolved",
                f"slot {index} did not resolve within the operational hard ceiling",
            )
    token_ids = [int(row["token_id"]) for row in accepted]
    pieces = [str(row["exact_piece"]) for row in accepted]
    if len(token_ids) != 32 or len(set(token_ids)) != 32:
        raise TokenizerAuditError("g1_panel_count", "G1 panel is not 32 unique IDs")
    core = {
        "candidate_sequence": sequence,
        "accepted_token_ids": token_ids,
        "accepted_exact_token_pieces": pieces,
        "rejected_token_ids_and_reasons": [
            {
                "sequence_index": int(row["sequence_index"]),
                "panel_index": int(row["panel_index"]),
                "attempt": int(row["attempt"]),
                "token_id": int(row["token_id"]),
                "exact_piece": str(row["exact_piece"]),
                "reason": str(row["reason"]),
            }
            for row in rejected
        ],
        "special_token_ids": list(special_ids),
        "experimental_lexicon_token_ids": _experimental_lexicon_token_ids(tokenizer),
        "selection_rule_sha256": canonical_sha256(protocol.G1_TOKEN_SELECTION_RULE),
    }
    return {**core, "token_panel_canonical_sha256": canonical_sha256(core)}


def audit_semantic_endpoints(
    tokenizer: Any,
    contextual_boundaries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    union: list[int] = []
    for family in protocol.G3_FAMILIES:
        rows: list[dict[str, Any]] = []
        for token in protocol.G3_TOKEN_GROUPS[family]:
            piece = f" {token}"
            token_id = _one_token_round_trip(tokenizer, piece)
            if token_id in union:
                raise TokenizerAuditError(
                    "semantic_duplicate_id", f"semantic endpoint ID {token_id} is duplicated"
                )
            union.append(token_id)
            rows.append({"token": token, "piece": piece, "token_id": token_id})
        groups[family] = rows
    token_id_by_label = {
        str(row["token"]): int(row["token_id"])
        for rows in groups.values()
        for row in rows
    }
    contexts: list[dict[str, Any]] = []
    for boundary in contextual_boundaries:
        fixture_id = boundary.get("fixture_id")
        raw_ids = boundary.get("context_ids")
        full_by_token = boundary.get("full_ids_by_token")
        if (
            not isinstance(fixture_id, str)
            or not isinstance(raw_ids, Sequence)
            or not isinstance(full_by_token, Mapping)
            or set(full_by_token) != set(token_id_by_label)
        ):
            raise TokenizerAuditError("semantic_context", "semantic boundary is malformed")
        ids = [int(value) for value in raw_ids]
        continuation_hashes: dict[str, str] = {}
        for label, token_id in token_id_by_label.items():
            full_ids = [int(value) for value in full_by_token[label]]
            if full_ids[: len(ids)] != ids or full_ids[len(ids) :] != [token_id]:
                raise TokenizerAuditError(
                    "semantic_context_multitoken",
                    f"leading-space endpoint {label!r} is not exact at {fixture_id}",
                )
            continuation_hashes[label] = token_ids_sha256(full_ids)
        contexts.append(
            {
                "fixture_id": fixture_id,
                "context_token_ids_sha256": token_ids_sha256(ids),
                "context_token_count": len(ids),
                "continuation_full_token_ids_sha256": continuation_hashes,
            }
        )
    if len(contexts) != len(protocol.g3_fixture_rows()):
        raise TokenizerAuditError("semantic_context_count", "not all 72 contexts were audited")
    return {
        "groups": groups,
        "ordered_union_token_ids": union,
        "contextual_boundaries": contexts,
    }


def audit_polarity_endpoints(
    tokenizer: Any,
    contextual_boundaries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observed = {piece: _one_token_round_trip(tokenizer, piece) for piece in POLARITY_TOKEN_IDS}
    if observed != POLARITY_TOKEN_IDS:
        raise TokenizerAuditError(
            "polarity_id_mismatch",
            f"pinned IDs differ: expected={POLARITY_TOKEN_IDS}, observed={observed}",
        )
    contextual: list[dict[str, Any]] = []
    for boundary in contextual_boundaries:
        prompt_id = boundary.get("prompt_id")
        raw_ids = boundary.get("context_ids")
        full_by_answer = boundary.get("full_ids_by_answer")
        if (
            not isinstance(prompt_id, str)
            or not isinstance(raw_ids, Sequence)
            or not isinstance(full_by_answer, Mapping)
            or set(full_by_answer) != set(POLARITY_TOKEN_IDS)
        ):
            raise TokenizerAuditError("polarity_context", "context boundary is malformed")
        ids = [int(value) for value in raw_ids]
        continuations: dict[str, dict[str, Any]] = {}
        for piece, token_id in observed.items():
            full_ids = [int(value) for value in full_by_answer[piece]]
            if full_ids[: len(ids)] != ids or full_ids[len(ids) :] != [
                token_id,
                protocol.G3P_EOT_TOKEN_ID,
            ]:
                raise TokenizerAuditError(
                    "polarity_context_multitoken",
                    f"full assistant rendering for {piece!r} is not exact at {prompt_id}",
                )
            continuations[piece] = {
                "token_id": token_id,
                "eot_token_id": protocol.G3P_EOT_TOKEN_ID,
                "full_token_ids_sha256": token_ids_sha256(full_ids),
                "exact_suffix": True,
            }
        contextual.append(
            {
                "prompt_id": prompt_id,
                "context_token_ids_sha256": token_ids_sha256(ids),
                "context_token_count": len(ids),
                "continuations": continuations,
            }
        )
    if len(contextual) != protocol.G3P_PROMPT_COUNT:
        raise TokenizerAuditError("polarity_context_count", "not all 24 contexts were audited")
    return {"isolated_token_ids": observed, "contextual_boundaries": contextual}


def audit_tokenizer(
    tokenizer: Any,
    *,
    tokenizer_repository: str,
    tokenizer_revision: str,
    plan_manifest_sha256: str,
    contextual_boundaries: Sequence[Mapping[str, Any]],
    semantic_contextual_boundaries: Sequence[Mapping[str, Any]],
    tokenizer_inventory_sha256: str,
) -> dict[str, Any]:
    """Return a self-hashed exact audit receipt; never substitute endpoints."""

    if tokenizer_repository != protocol.MODEL_SPEC["repository"]:
        raise TokenizerAuditError("tokenizer_repository", "tokenizer repository differs")
    if tokenizer_revision != protocol.MODEL_SPEC["revision"]:
        raise TokenizerAuditError("tokenizer_revision", "tokenizer revision differs")
    if not HEX64.fullmatch(plan_manifest_sha256):
        raise TokenizerAuditError("plan_hash", "plan manifest hash is malformed")
    if not HEX64.fullmatch(tokenizer_inventory_sha256):
        raise TokenizerAuditError("inventory_hash", "tokenizer inventory hash is malformed")
    if len(tokenizer) != protocol.MODEL_SPEC["tokenizer_vocabulary_size"]:
        raise TokenizerAuditError("vocabulary_size", "tokenizer vocabulary size differs")

    g1 = resolve_g1_panel(tokenizer)
    semantic = audit_semantic_endpoints(tokenizer, semantic_contextual_boundaries)
    polarity = audit_polarity_endpoints(tokenizer, contextual_boundaries)
    core = {
        "schema_version": 1,
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "status": "pass",
        "model_weights_loaded": False,
        "model_forward_count": 0,
        "plan_manifest_sha256": plan_manifest_sha256,
        "tokenizer_repository": tokenizer_repository,
        "tokenizer_revision": tokenizer_revision,
        "tokenizer_inventory_sha256": tokenizer_inventory_sha256,
        "g1": g1,
        "semantic": semantic,
        "polarity": polarity,
    }
    return {**core, "receipt_sha256": canonical_sha256(core)}

