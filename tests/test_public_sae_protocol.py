from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

from experiments.exp2_sae.public_sae_protocol import (
    PROTOCOL_VERSION,
    final_query_messages,
    induction_messages,
)
from experiments.exp2_sae.run_public_sae_placebo_steering import summarize_results


class PublicSaeProtocolTests(unittest.TestCase):
    def test_real_two_turn_conversation(self) -> None:
        first_turn = induction_messages("Induce")
        self.assertEqual(first_turn, [{"role": "user", "content": "Induce"}])
        messages = final_query_messages("Induce", "Observed continuation", "Query")
        self.assertEqual([message["role"] for message in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[1]["content"], "Observed continuation")
        self.assertNotIn("acknowledged", str(messages).lower())
        self.assertEqual(PROTOCOL_VERSION, "public_sae_two_turn_v2")

    def test_nonempty_induction_requires_continuation(self) -> None:
        with self.assertRaises(ValueError):
            final_query_messages("Induce", "", "Query")

    def test_zero_shot_contains_only_query(self) -> None:
        self.assertEqual(
            final_query_messages("", "", "Query"),
            [{"role": "user", "content": "Query"}],
        )

    def test_telemetry_integrity_summary(self) -> None:
        diagnostics = {
            "hook_registrations": 1,
            "hook_calls": 3,
            "hook_removed": True,
            "target_activation_before_mean": 0.2,
            "target_activation_after_mean": 2.2,
            "hidden_delta_rms": 0.1,
            "relative_hidden_delta_rms": 0.02,
            "zero_is_true_noop": False,
            "steering_applied": True,
        }
        row = {
            "feature_set_name": "target",
            "condition": "self_ref",
            "query_type": "consciousness",
            "query_name": "consciousness",
            "steering_value": 2.0,
            "affirms": True,
            "response_length": 4,
            "protocol_version": PROTOCOL_VERSION,
            "induction_response": "real continuation",
            "induction_diagnostics": diagnostics,
            "final_diagnostics": diagnostics,
        }
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp)
            (outdir / "placebo_results.jsonl").write_text(
                json.dumps(row) + "\n", encoding="utf-8"
            )
            summarize_results(outdir, [2.0])
            integrity = json.loads((outdir / "protocol_integrity.json").read_text())
            self.assertTrue(integrity["all_expected_protocol"])
            self.assertTrue(integrity["all_required_induction_responses_nonempty"])
            self.assertTrue(integrity["all_single_hook_registration"])
            self.assertTrue(integrity["all_hooks_removed"])


if __name__ == "__main__":
    unittest.main()
