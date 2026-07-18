from __future__ import annotations

import string
import unittest

from experiments.consciousness_readout_validation import protocol
from experiments.consciousness_readout_validation import tokenizer_audit


def _letters(value: int) -> str:
    alphabet = string.ascii_lowercase
    result = ""
    number = value + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = alphabet[remainder] + result
    return result


class FakePinnedTokenizer:
    def __init__(self) -> None:
        self.all_special_ids = [0, 1]
        self.by_id: dict[int, str] = {
            0: "<bos>",
            1: "<eos>",
            9642: "Yes",
            2822: "No",
            128009: "<|eot_id|>",
        }
        self.by_piece = {piece: token_id for token_id, piece in self.by_id.items()}

    def __len__(self) -> int:
        return 128256

    def _piece(self, token_id: int) -> str:
        if token_id not in self.by_id:
            piece = " q" + _letters(token_id)
            self.by_id[token_id] = piece
            self.by_piece[piece] = token_id
        return self.by_id[token_id]

    def encode(self, piece: str, add_special_tokens: bool = False) -> list[int]:
        del add_special_tokens
        if piece in self.by_piece:
            return [self.by_piece[piece]]
        digest = protocol.identity_bound_seed64("fake-tokenizer", piece)
        token_id = 10_000 + digest % 100_000
        while token_id in self.by_id and self.by_id[token_id] != piece:
            token_id += 1
        self.by_id[token_id] = piece
        self.by_piece[piece] = token_id
        return [token_id]

    def decode(
        self,
        ids: list[int],
        *,
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = False,
    ) -> str:
        del skip_special_tokens, clean_up_tokenization_spaces
        return "".join(self._piece(int(token_id)) for token_id in ids)


class TokenizerAuditTests(unittest.TestCase):
    def test_g1_receipt_records_exact_candidate_stream(self) -> None:
        receipt = tokenizer_audit.resolve_g1_panel(FakePinnedTokenizer())
        self.assertEqual(len(receipt["accepted_token_ids"]), 32)
        self.assertEqual(len(set(receipt["accepted_token_ids"])), 32)
        self.assertGreaterEqual(len(receipt["candidate_sequence"]), 32)
        self.assertEqual(
            [row["sequence_index"] for row in receipt["candidate_sequence"]],
            list(range(len(receipt["candidate_sequence"]))),
        )
        self.assertEqual(
            receipt["token_panel_canonical_sha256"],
            tokenizer_audit.canonical_sha256(
                {
                    key: value
                    for key, value in receipt.items()
                    if key != "token_panel_canonical_sha256"
                }
            ),
        )

    def test_polarity_ids_are_independently_frozen(self) -> None:
        tokenizer = FakePinnedTokenizer()
        boundaries = [
            {
                "prompt_id": f"factual_yes_no_{index:02d}",
                "context_ids": [90_000 + index],
                "full_ids_by_answer": {
                    "Yes": [90_000 + index, 9642, 128009],
                    "No": [90_000 + index, 2822, 128009],
                },
            }
            for index in range(1, 25)
        ]
        result = tokenizer_audit.audit_polarity_endpoints(tokenizer, boundaries)
        self.assertEqual(result["isolated_token_ids"], {"Yes": 9642, "No": 2822})
        self.assertEqual(len(result["contextual_boundaries"]), 24)

    def test_all_semantic_contexts_require_exact_single_token_suffixes(self) -> None:
        tokenizer = FakePinnedTokenizer()
        labels = tuple(
            token
            for family in protocol.G3_FAMILIES
            for token in protocol.G3_TOKEN_GROUPS[family]
        )
        token_ids = {
            label: tokenizer.encode(f" {label}", add_special_tokens=False)[0]
            for label in labels
        }
        boundaries = []
        for index, row in enumerate(protocol.g3_fixture_rows(), start=1):
            context = [80_000 + index]
            boundaries.append(
                {
                    "fixture_id": row["fixture_id"],
                    "context_ids": context,
                    "full_ids_by_token": {
                        label: [*context, token_ids[label]] for label in labels
                    },
                }
            )
        result = tokenizer_audit.audit_semantic_endpoints(tokenizer, boundaries)
        self.assertEqual(len(result["contextual_boundaries"]), 72)
        self.assertEqual(len(result["ordered_union_token_ids"]), 28)

    def test_multitoken_polarity_endpoint_hard_fails(self) -> None:
        class Broken(FakePinnedTokenizer):
            def encode(self, piece: str, add_special_tokens: bool = False) -> list[int]:
                if piece == "Yes":
                    return [7, 8]
                return super().encode(piece, add_special_tokens=add_special_tokens)

        with self.assertRaises(tokenizer_audit.TokenizerAuditError) as caught:
            tokenizer_audit.audit_polarity_endpoints(Broken(), [])
        self.assertEqual(caught.exception.code, "endpoint_multitoken")


if __name__ == "__main__":
    unittest.main()
