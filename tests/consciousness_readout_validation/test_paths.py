from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.consciousness_readout_validation import paths


class PathIsolationTests(unittest.TestCase):
    def test_metadata_output_must_be_fresh_direct_child(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(paths, "DATA_ROOT", root):
                allowed = root / "fresh_plan"
                self.assertEqual(paths.require_new_metadata_output(allowed), allowed.resolve())
                with self.assertRaises(paths.UnsafePilotPath):
                    paths.require_new_metadata_output(root / "nested" / "plan")
                allowed.mkdir()
                with self.assertRaises(paths.UnsafePilotPath):
                    paths.require_new_metadata_output(allowed)

    def test_prior_study_roots_are_rejected(self) -> None:
        forbidden = paths.REPO_ROOT / "data" / "consciousness_sae_changepoint" / "anything"
        with self.assertRaises(paths.UnsafePilotPath):
            paths.assert_not_forbidden_input(forbidden)

    def test_repository_source_input_is_exactly_allowlisted(self) -> None:
        accepted = paths.REPO_ROOT / "experiments" / paths.STUDY_SLUG / "protocol.py"
        self.assertEqual(paths.require_repository_source_input(accepted), accepted.resolve())
        with self.assertRaises(paths.UnsafePilotPath):
            paths.require_repository_source_input(paths.REPO_ROOT / "consciousness_sae.md")

    def test_external_root_requires_matching_study_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / paths.VOLUME_SENTINEL
            sentinel.write_text(
                json.dumps(
                    {
                        "study_slug": paths.STUDY_SLUG,
                        "study_id": paths.STUDY_ID,
                        "volume_id": "volume-test",
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                paths.require_external_artifact_root(root, expected_volume_id="volume-test"),
                root.resolve(),
            )
            phase = paths.require_new_external_phase_dir(
                "g1_transport_arithmetic",
                root=root,
                expected_volume_id="volume-test",
            )
            self.assertEqual(
                phase,
                root.resolve()
                / paths.STUDY_SLUG
                / paths.STUDY_ID
                / "g1_transport_arithmetic",
            )
            self.assertIn("analysis", paths.PILOT_EXTERNAL_PHASES)
            self.assertIn("audit", paths.PILOT_EXTERNAL_PHASES)
            self.assertEqual(
                paths.require_new_external_phase_dir(
                    "analysis", root=root, expected_volume_id="volume-test"
                ),
                root.resolve() / paths.STUDY_SLUG / paths.STUDY_ID / "analysis",
            )
            with self.assertRaises(paths.UnsafePilotPath):
                paths.require_new_external_phase_dir(
                    "target_execution",
                    root=root,
                    expected_volume_id="volume-test",
                )

    def test_external_root_rejects_wrong_sentinel_or_missing_env(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / paths.VOLUME_SENTINEL).write_text(
                json.dumps(
                    {
                        "study_slug": paths.STUDY_SLUG,
                        "study_id": paths.STUDY_ID,
                        "volume_id": "wrong",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(paths.UnsafePilotPath):
                paths.require_external_artifact_root(root, expected_volume_id="expected")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(paths.UnsafePilotPath):
                paths.require_external_artifact_root()


if __name__ == "__main__":
    unittest.main()
