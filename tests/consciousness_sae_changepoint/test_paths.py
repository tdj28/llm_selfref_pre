from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_changepoint import paths


class OutputPathPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_out_root = paths.OUT_ROOT
        self.original_data_root = paths.DATA_ROOT
        paths.OUT_ROOT = self.root / "out" / paths.STUDY_SLUG
        paths.DATA_ROOT = self.root / "data" / paths.STUDY_SLUG
        self.external_root = self.root / "network-volume" / paths.STUDY_SLUG
        self.external_root.mkdir(parents=True)
        (self.external_root / paths.ARTIFACT_VOLUME_SENTINEL).write_text(
            json.dumps(
                {
                    "study_slug": paths.STUDY_SLUG,
                    "volume_id": "test-network-volume",
                    "volume_size_gb": 500,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        paths.OUT_ROOT = self.original_out_root
        paths.DATA_ROOT = self.original_data_root
        self.tempdir.cleanup()

    def test_accepts_fresh_local_fixture_child(self) -> None:
        destination = paths.OUT_ROOT / "confirmatory" / "run-001"

        self.assertEqual(
            paths.require_new_output_path(destination), destination.resolve()
        )

    def test_accepts_fresh_direct_metadata_release_child(self) -> None:
        destination = paths.DATA_ROOT / "confirmatory_v1_20990101"

        self.assertEqual(
            paths.require_new_output_path(destination, release=True),
            destination.resolve(),
        )

    def test_rejects_prior_experiment_namespaces(self) -> None:
        for upstream_root in paths.READ_ONLY_UPSTREAM_ROOTS:
            with self.subTest(upstream_root=upstream_root):
                with self.assertRaisesRegex(
                    paths.UnsafeOutputPath, "read-only upstream"
                ):
                    paths.require_new_output_path(upstream_root / "new-results")

    def test_rejects_existing_destination(self) -> None:
        destination = paths.OUT_ROOT / "dryrun" / "existing"
        destination.mkdir(parents=True)

        with self.assertRaisesRegex(
            paths.UnsafeOutputPath, "must not already exist"
        ):
            paths.require_new_output_path(destination)

    def test_rejects_nested_release_destination(self) -> None:
        with self.assertRaisesRegex(paths.UnsafeOutputPath, "direct child"):
            paths.require_new_output_path(
                paths.DATA_ROOT / "confirmatory_v1_20990101" / "nested",
                release=True,
            )

    def test_requires_explicit_external_root_without_local_fallback(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                paths.UnsafeOutputPath, "no local fallback"
            ):
                paths.require_external_artifact_root(minimum_free_bytes=0)

    def test_accepts_verified_external_artifact_child(self) -> None:
        destination = self.external_root / "confirmatory" / "run-001.partial"

        self.assertEqual(
            paths.require_new_external_artifact_path(
                destination,
                artifact_root=self.external_root,
                minimum_free_bytes=0,
                expected_volume_id="test-network-volume",
            ),
            destination.resolve(),
        )

    def test_external_root_write_read_probe(self) -> None:
        self.assertEqual(
            paths.require_external_artifact_root(
                self.external_root,
                minimum_free_bytes=0,
                expected_volume_id="test-network-volume",
                write_read_probe=True,
            ),
            self.external_root.resolve(),
        )
        self.assertEqual(
            list(self.external_root.glob(".csae-write-read-probe-*")), []
        )

    def test_rejects_wrong_external_volume(self) -> None:
        with self.assertRaisesRegex(paths.UnsafeOutputPath, "volume_id mismatch"):
            paths.require_external_artifact_root(
                self.external_root,
                minimum_free_bytes=0,
                expected_volume_id="different-volume",
            )

    def test_rejects_unproven_volume_size(self) -> None:
        sentinel = self.external_root / paths.ARTIFACT_VOLUME_SENTINEL
        payload = json.loads(sentinel.read_text())
        payload["volume_size_gb"] = 499
        sentinel.write_text(json.dumps(payload))
        with self.assertRaisesRegex(paths.UnsafeOutputPath, "volume-size floor"):
            paths.require_external_artifact_root(
                self.external_root,
                minimum_free_bytes=0,
            )

    def test_rejects_existing_external_destination(self) -> None:
        destination = self.external_root / "confirmatory" / "existing.partial"
        destination.mkdir(parents=True)

        with self.assertRaisesRegex(
            paths.UnsafeOutputPath, "must not already exist"
        ):
            paths.require_new_external_artifact_path(
                destination,
                artifact_root=self.external_root,
                minimum_free_bytes=0,
            )

    def test_rejects_external_root_inside_repository(self) -> None:
        with self.assertRaisesRegex(paths.UnsafeOutputPath, "outside the Git"):
            paths.require_external_artifact_root(
                paths.REPO_ROOT,
                minimum_free_bytes=0,
            )


if __name__ == "__main__":
    unittest.main()
