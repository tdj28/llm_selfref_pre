import json
import tempfile
import unittest
from pathlib import Path

from experiments.consciousness_sae_changepoint import seal_semantic_amendment_failure as failure


class SealSemanticAmendmentFailureTests(unittest.TestCase):
    def test_partial_snapshot_preserves_empty_partial_block_and_started_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            partial = root / "calibration" / "execution.partial"
            block = partial / "blocks" / "first-block.partial"
            block.mkdir(parents=True)
            started = {"run_id": "execution", "metadata": {"plan_hash": "a" * 64}}
            (partial / "RUN_STARTED.json").write_text(
                json.dumps(started), encoding="utf-8"
            )
            snapshot = failure.snapshot_partial(partial, root=root)
            validated = failure.validate_partial_snapshot(snapshot)
        self.assertIn("blocks/first-block.partial", snapshot["directories"])
        self.assertEqual(validated["file_count"], 1)
        self.assertEqual(validated["directory_count"], 2)

    def test_partial_snapshot_rejects_completion_marker(self):
        snapshot = {
            "schema_version": 1,
            "consumed_partial_relative_path": "calibration/execution.partial",
            "directories": [],
            "files": [
                {
                    "relative_path": "RUN_STARTED.json",
                    "bytes": 2,
                    "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
                    "payload_base64": "e30=",
                },
                {
                    "relative_path": "COMPLETE.json",
                    "bytes": 2,
                    "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
                    "payload_base64": "e30=",
                },
            ],
        }
        snapshot["snapshot_sha256"] = failure.sha256_json(snapshot)
        with self.assertRaises(failure.AmendmentFailureSealError):
            failure.validate_partial_snapshot(snapshot)

    def test_traceback_requires_exact_frozen_safety_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "traceback.txt"
            path.write_text(
                "Traceback (most recent call last):\n"
                "SemanticControlAmendmentError: "
                "vector exceeds 10% of a clean injection-state RMS\n",
                encoding="utf-8",
            )
            evidence = failure.traceback_evidence(path)
            validated = failure.validate_traceback_evidence(evidence)
            self.assertEqual(validated["traceback_sha256"], evidence["sha256"])
            path.write_text(
                "SemanticControlAmendmentError: unrelated technical error\n",
                encoding="utf-8",
            )
            with self.assertRaises(failure.AmendmentFailureSealError):
                failure.traceback_evidence(path)

    def test_terminal_contract_can_never_pass_or_retry(self):
        self.assertEqual(failure.REASON_CODE, "vector_rms_safety_gate")
        args = failure.parse_args(
            [
                "--amendment-freeze-receipt", "freeze.json",
                "--traceback-file", "traceback.txt",
                "--volume-id", "volume",
                "--failure-run-id", "terminal-failure",
            ]
        )
        self.assertEqual(args.failure_run_id, "terminal-failure")


if __name__ == "__main__":
    unittest.main()
