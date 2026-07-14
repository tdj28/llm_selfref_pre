from __future__ import annotations

import copy
import hashlib
import unittest

from experiments.consciousness_sae_changepoint import calibrate, protocol


def metric_rows(
    candidate_ids: list[int],
    *,
    fallback: bool = False,
    impossible: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, target_id in enumerate(protocol.TARGET_FEATURE_IDS):
        norm = 1.0 + 0.05 * index
        rows.append(
            {
                "feature_id": target_id,
                "feature_role": "target",
                "decoder_norm": norm,
                "mean_activation": 0.01 * (index + 1),
                "max_activation": 0.1 * (index + 1),
                "positive_token_fraction": 0.02 * (index + 1),
                "max_abs_target_cosine": 1.0,
                "n_prompt_positions": 100,
            }
        )
    for index, candidate_id in enumerate(candidate_ids):
        target_index = index % len(protocol.TARGET_FEATURE_IDS)
        target_norm = 1.0 + 0.05 * target_index
        if impossible:
            norm, cosine = target_norm * 2.0, 0.5
        elif fallback:
            norm, cosine = target_norm * 1.4, 0.2
        else:
            norm, cosine = target_norm, 0.0
        rows.append(
            {
                "feature_id": candidate_id,
                "feature_role": "candidate",
                "decoder_norm": norm,
                "mean_activation": 0.01 * (target_index + 1),
                "max_activation": 0.1 * (target_index + 1),
                "positive_token_fraction": 0.02 * (target_index + 1),
                "max_abs_target_cosine": cosine,
                "n_prompt_positions": 100,
            }
        )
    return rows


def hidden_rms(value: float = 2.0) -> dict[str, float]:
    return {
        str(prompt["prompt_id"]): value
        for prompt in calibrate.NEUTRAL_CALIBRATION_PROMPTS
    }


class CalibrationPureTests(unittest.TestCase):
    def test_candidate_pool_is_fixed_unique_and_excludes_targets(self) -> None:
        first = calibrate.build_candidate_pool()
        second = calibrate.build_candidate_pool()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 512)
        self.assertEqual(len(set(first)), 512)
        self.assertTrue(set(first).isdisjoint(protocol.TARGET_FEATURE_IDS))
        self.assertEqual(
            first[:10],
            [18627, 64153, 6824, 35185, 57440, 49759, 46374, 35667, 42167, 6268],
        )
        self.assertEqual(
            calibrate.candidate_pool_sha256(first),
            "802031a96c470b00ee574a9f47d43aada5492ab36813bdd72570c210e0c72ae7",
        )

    def test_dead_hash_ranked_feature_is_receipted_and_replaced(self) -> None:
        ranking = calibrate.build_candidate_ranking()
        candidates = ranking[1 : calibrate.CANDIDATE_POOL_SIZE + 1]
        screening = [
            {
                "feature_id": ranking[0],
                "eligible": False,
                "reason": "zero_decoder_norm",
                "decoder_norm": 0.0,
            },
            *[
                {
                    "feature_id": feature_id,
                    "eligible": True,
                    "reason": "selected",
                    "decoder_norm": 1.0,
                }
                for feature_id in candidates
            ],
        ]
        validated = calibrate.validate_candidate_screening(screening, candidates)
        self.assertEqual(len(validated), 513)
        self.assertEqual(validated[0]["reason"], "zero_decoder_norm")

    def test_primary_matching_is_one_to_one_and_deterministic(self) -> None:
        candidates = [101, 102, 103, 104, 105, 106]
        rows = metric_rows(candidates)
        first = calibrate.match_features(rows, candidates)
        second = calibrate.match_features(reversed(rows), list(reversed(candidates)))
        self.assertEqual(first, second)
        self.assertEqual(first["matching_path"], "primary")
        self.assertFalse(first["fallback_was_used"])
        self.assertEqual(
            calibrate.matched_feature_map(first),
            dict(zip(protocol.TARGET_FEATURE_IDS, candidates)),
        )

    def test_lexicographic_tie_break_is_frozen(self) -> None:
        candidates = [106, 103, 105, 101, 104, 102]
        rows = []
        for feature_id in (*protocol.TARGET_FEATURE_IDS, *candidates):
            rows.append(
                {
                    "feature_id": feature_id,
                    "feature_role": (
                        "target"
                        if feature_id in protocol.TARGET_FEATURE_IDS
                        else "candidate"
                    ),
                    "decoder_norm": 1.0,
                    "mean_activation": 0.0,
                    "max_activation": 0.0,
                    "positive_token_fraction": 0.0,
                    "max_abs_target_cosine": (
                        1.0 if feature_id in protocol.TARGET_FEATURE_IDS else 0.0
                    ),
                    "n_prompt_positions": 50,
                }
            )
        matching = calibrate.match_features(rows, candidates)
        self.assertEqual(
            tuple(calibrate.matched_feature_map(matching).values()),
            tuple(sorted(candidates)),
        )

    def test_only_prespecified_fallback_is_used(self) -> None:
        candidates = [201, 202, 203, 204, 205, 206]
        matching = calibrate.match_features(
            metric_rows(candidates, fallback=True), candidates
        )
        self.assertEqual(matching["matching_path"], "prespecified_fallback")
        self.assertTrue(matching["fallback_was_used"])
        self.assertEqual([row["path"] for row in matching["failed_prior_paths"]], ["primary"])

    def test_matching_fails_closed_after_fallback(self) -> None:
        candidates = [301, 302, 303, 304, 305, 306]
        with self.assertRaisesRegex(calibrate.CalibrationProtocolError, "primary and sole"):
            calibrate.match_features(
                metric_rows(candidates, impossible=True), candidates
            )

    def test_multiplier_targets_rms_and_honors_hard_cap(self) -> None:
        result = calibrate.compute_bf16_multiplier(
            hidden_rms_by_prompt=hidden_rms(2.0),
            target_vector_rms=[0.01] * 50,
            matched_vector_rms=[0.01] * 50,
        )
        self.assertEqual(result["calibrated_multiplier"], 8.0)
        self.assertIn("hard_multiplier", result["limiting_caps"])
        self.assertEqual(result["outcome_inputs"], [])

    def test_multiplier_is_conservatively_stability_capped(self) -> None:
        result = calibrate.compute_bf16_multiplier(
            hidden_rms_by_prompt=hidden_rms(2.0),
            target_vector_rms=[0.05] * 50,
            matched_vector_rms=[0.15] * 50,
        )
        self.assertEqual(result["calibrated_multiplier"], 1.333)
        self.assertLessEqual(result["maximum_calibrated_relative_rms"], 0.10)
        self.assertIn("stability_relative_rms", result["limiting_caps"])

    def test_unsafe_literal_vectors_fail_instead_of_being_attenuated(self) -> None:
        with self.assertRaisesRegex(
            calibrate.CalibrationProtocolError, "literal aggregate scale"
        ):
            calibrate.compute_bf16_multiplier(
                hidden_rms_by_prompt=hidden_rms(1.0),
                target_vector_rms=[0.10] * 50,
                matched_vector_rms=[0.11] * 50,
            )


class CalibrationReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = calibrate.build_candidate_pool()
        rows = metric_rows(cls.candidates)
        # Only the first six candidates are eligible; the rest remain in the
        # measured pool but are outside both caliper paths.
        for row in rows[len(protocol.TARGET_FEATURE_IDS) + 6 :]:
            row["decoder_norm"] = 5.0
            row["max_abs_target_cosine"] = 0.5
        cls.metrics = rows
        cls.matching = calibrate.match_features(rows, cls.candidates)
        cls.hidden = hidden_rms(2.0)
        cls.prompt_receipts = [
            {
                "prompt_id": str(prompt["prompt_id"]),
                "prompt_utf8_sha256": hashlib.sha256(
                    str(prompt["text"]).encode("utf-8")
                ).hexdigest(),
                "rendered_token_count": 12,
                "rendered_token_ids_sha256": hashlib.sha256(
                    str(prompt["prompt_id"]).encode("utf-8")
                ).hexdigest(),
                "hidden_rms": 2.0,
                "sampled_output": False,
            }
            for prompt in calibrate.NEUTRAL_CALIBRATION_PROMPTS
        ]
        mapping = calibrate.matched_feature_map(cls.matching)
        cls.vectors = []
        for block in protocol.aggregate_blocks():
            targets = [int(value) for value in block["target_feature_ids"]]
            cls.vectors.append(
                {
                    "block_id": block["block_id"],
                    "target_feature_ids": targets,
                    "matched_feature_ids": [mapping[target] for target in targets],
                    "magnitudes": [float(value) for value in block["magnitudes"]],
                    "target_vector_bf16_sha256": hashlib.sha256(
                        f"target:{block['block_id']}".encode()
                    ).hexdigest(),
                    "matched_vector_bf16_sha256": hashlib.sha256(
                        f"matched:{block['block_id']}".encode()
                    ).hexdigest(),
                    "target_vector_rms": 0.02,
                    "matched_vector_rms": 0.02,
                }
            )
        cls.multiplier = calibrate.compute_bf16_multiplier(
            hidden_rms_by_prompt=cls.hidden,
            target_vector_rms=[0.02] * 50,
            matched_vector_rms=[0.02] * 50,
        )
        cls.artifact = {
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "outcome_blind": True,
            "prior_outcome_inputs": [],
            "expected_volume_id": "test-volume-001",
            "model": {
                "id": protocol.MODEL_ID,
                "revision": protocol.MODEL_REVISION,
                "files": [
                    {
                        "path": "config.json",
                        "bytes": 10,
                        "sha256": "a" * 64,
                    }
                ],
            },
            "sae": {"file_sha256": protocol.SAE_FILE_SHA256},
            "tokenizer": {"len": protocol.TOKENIZER_SIZE},
        }
        cls.artifact["receipt_sha256"] = calibrate.sha256_json(cls.artifact)

    def build(self) -> dict[str, object]:
        return calibrate.build_receipt(
            artifact_receipt=self.artifact,
            artifact_receipt_file_sha256="b" * 64,
            expected_volume_id="test-volume-001",
            candidate_ids=self.candidates,
            feature_metrics=self.metrics,
            hidden_rms_by_prompt=self.hidden,
            prompt_receipts=self.prompt_receipts,
            matching=self.matching,
            aggregate_vectors=self.vectors,
            multiplier_calibration=self.multiplier,
            runtime={"gpu": "synthetic"},
            created_at_utc="2026-07-13T00:00:00+00:00",
        )

    def test_receipt_asserts_blinding_and_revalidates(self) -> None:
        receipt = self.build()
        self.assertTrue(receipt["outcome_blind"])
        self.assertFalse(receipt["target_outcomes_opened"])
        self.assertEqual(receipt["prior_outcome_inputs"], [])
        self.assertEqual(receipt["calibrated_multiplier"], 5.0)
        result = calibrate.validate_calibration_receipt(receipt)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["matching_path"], "primary")

    def test_receipt_hash_tamper_fails_closed(self) -> None:
        receipt = self.build()
        tampered = copy.deepcopy(receipt)
        tampered["prior_outcome_inputs"] = ["old-results.jsonl"]
        with self.assertRaises(calibrate.CalibrationProtocolError):
            calibrate.validate_calibration_receipt(tampered)

    def test_rehashed_matching_tamper_still_fails_reconstruction(self) -> None:
        receipt = self.build()
        tampered = copy.deepcopy(receipt)
        tampered["matching"]["matching_path"] = "prespecified_fallback"
        without_hash = dict(tampered)
        without_hash.pop("receipt_sha256")
        tampered["receipt_sha256"] = calibrate.sha256_json(without_hash)
        with self.assertRaisesRegex(
            calibrate.CalibrationProtocolError, "matching reconstruction"
        ):
            calibrate.validate_calibration_receipt(tampered)


if __name__ == "__main__":
    unittest.main()
