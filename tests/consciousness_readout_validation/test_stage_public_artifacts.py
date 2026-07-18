from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from experiments.consciousness_readout_validation import guest_attestation, paths, protocol
from experiments.consciousness_readout_validation.stage_public_artifacts import (
    STAGING_RECEIPT_FILENAME,
    StagingError,
    initialize_or_validate_volume,
    stage_public_artifacts,
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_blob(payload: bytes) -> str:
    return hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()


class StagePublicArtifactsTests(unittest.TestCase):
    @staticmethod
    def _attestation_kwargs():
        return {
            "owned_pod_id": "unit-owned-pod",
            "data_center_id": "US-NE-1",
            "guest_attestation_receipt": Path(
                "/tmp/unit-guest-attestation/GUEST_ATTESTATION_RECEIPT.json"
            ),
            "attestation_validator": lambda _path, **_expected: {
                "receipt_sha256": "a" * 64,
                "repository_source_root_sha256": "b" * 64,
                "stage_python_launch_contract": (
                    guest_attestation.expected_python_launch_contract(
                        guest_attestation.STAGE_PUBLIC_ARTIFACTS_MODULE
                    )
                ),
            },
        }

    def _fixture(self):
        index = json.dumps(
            {"weight_map": {"model.embed_tokens.weight": "model-00001-of-00001.safetensors"}},
            sort_keys=True,
        ).encode("utf-8")
        model_payloads = {
            ".gitattributes": b"attrs",
            "config.json": b"{}",
            "generation_config.json": b"{}",
            "model.safetensors.index.json": index,
            "model-00001-of-00001.safetensors": b"weights",
            "tokenizer.json": b"{}",
            "tokenizer_config.json": b"{}",
            "original/consolidated.00.pth": b"excluded-original",
        }
        sae_payloads = {str(protocol.SAE_SPEC["filename"]): b"sae"}
        for row in protocol.SAE_SPEC["sidecars"].values():
            sae_payloads[str(row["filename"])] = f"sidecar:{row['filename']}".encode()
        j_payloads = {
            str(protocol.J_LENS_SPEC["filename"]): b"jlens",
            str(protocol.J_LENS_SPEC["release_config"]["filename"]): b"jlens-config",
        }
        infos = {
            protocol.MODEL_SPEC["repository"]: {
                "revision": protocol.MODEL_SPEC["revision"],
                "files": [
                    {
                        "path": path,
                        "size": len(payload),
                        **(
                            {"blob_id": _git_blob(payload)}
                            if path == ".gitattributes"
                            else {"sha256": _sha(payload)}
                        ),
                    }
                    for path, payload in model_payloads.items()
                ],
            },
            protocol.SAE_SPEC["repository"]: {
                "revision": protocol.SAE_SPEC["revision"],
                "files": [
                    {"path": path, "size": len(payload), "sha256": _sha(payload)}
                    for path, payload in sae_payloads.items()
                ],
            },
            protocol.J_LENS_SPEC["repository"]: {
                "revision": protocol.J_LENS_SPEC["revision"],
                "files": [
                    {"path": path, "size": len(payload), "sha256": _sha(payload)}
                    for path, payload in j_payloads.items()
                ],
            },
        }

        def resolve(repository, revision, token):
            self.assertEqual(token, "test-token")
            self.assertEqual(infos[repository]["revision"], revision)
            return copy.deepcopy(infos[repository])

        def snapshot_download(**kwargs):
            root = Path(kwargs["local_dir"])
            root.mkdir(parents=True, exist_ok=True)
            for path in kwargs["allow_patterns"]:
                destination = root / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(model_payloads[path])
            metadata = root / ".cache" / "huggingface"
            metadata.mkdir(parents=True)
            (metadata / "transport.json").write_text("{}", encoding="utf-8")
            return str(root)

        def hub_download(**kwargs):
            repository = kwargs["repo_id"]
            payloads = sae_payloads if repository == protocol.SAE_SPEC["repository"] else j_payloads
            destination = Path(kwargs["local_dir"]) / kwargs["filename"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payloads[kwargs["filename"]])
            metadata = Path(kwargs["local_dir"]) / ".cache" / "huggingface"
            metadata.mkdir(parents=True, exist_ok=True)
            return str(destination)

        sae_spec = copy.deepcopy(protocol.SAE_SPEC)
        sae_spec["sha256"] = _sha(sae_payloads[str(sae_spec["filename"])])
        for row in sae_spec["sidecars"].values():
            row["sha256"] = _sha(sae_payloads[str(row["filename"])])
        j_spec = copy.deepcopy(protocol.J_LENS_SPEC)
        j_spec["sha256"] = _sha(j_payloads[str(j_spec["filename"])])
        j_spec["release_config"]["sha256"] = _sha(
            j_payloads[str(j_spec["release_config"]["filename"])]
        )
        return resolve, snapshot_download, hub_download, sae_spec, j_spec

    def test_fresh_stage_is_regular_hashed_and_atomic(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
            ):
                output = stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )
            self.assertTrue(output.is_dir())
            self.assertFalse((output.parent / "public_artifacts.partial").exists())
            self.assertFalse((output / "model_snapshot" / "original").exists())
            self.assertFalse(any(path.name == ".cache" for path in output.rglob("*")))
            self.assertTrue((output / "sae" / "README.md").is_file())
            self.assertTrue((output / "sae" / "config.yaml").is_file())
            receipt = json.loads((output / STAGING_RECEIPT_FILENAME).read_text())
            sealed = dict(receipt)
            receipt_hash = sealed.pop("receipt_sha256")
            self.assertEqual(protocol.canonical_sha256(sealed), receipt_hash)
            self.assertEqual("pass", receipt["status"])
            self.assertEqual("unit-owned-pod", receipt["owned_pod_id"])
            self.assertEqual("US-NE-1", receipt["data_center_id"])
            self.assertEqual("a" * 64, receipt["guest_attestation_receipt_sha256"])
            self.assertEqual("b" * 64, receipt["repository_source_root_sha256"])
            self.assertEqual(
                guest_attestation.expected_python_launch_contract(
                    guest_attestation.STAGE_PUBLIC_ARTIFACTS_MODULE
                ),
                receipt["stage_python_launch_contract"],
            )
            self.assertEqual([], receipt["prior_outcome_inputs"])
            self.assertEqual(
                receipt["expected_download_bytes"], receipt["retained_bytes"]
            )
            self.assertEqual(
                {"model", "sae", "j_lens"},
                set(receipt["selected_remote_inventories"]),
            )
            with self.assertRaises(StagingError):
                stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )

    def test_guest_attestation_failure_precedes_any_volume_write_or_remote_call(self):
        remote_called = False

        def forbidden_remote(*_args):
            nonlocal remote_called
            remote_called = True
            raise AssertionError("remote resolution must not start")

        def reject_attestation(_path, **_expected):
            raise guest_attestation.GuestAttestationError("unit rejection")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arguments = self._attestation_kwargs()
            arguments["attestation_validator"] = reject_attestation
            with self.assertRaisesRegex(StagingError, "guest attestation failed"):
                stage_public_artifacts(
                    artifact_root=root,
                    **arguments,
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=forbidden_remote,
                    snapshot_download=lambda **_kwargs: "",
                    hub_download=lambda **_kwargs: "",
                )
            self.assertFalse(remote_called)
            self.assertFalse((root / paths.VOLUME_SENTINEL).exists())
            self.assertEqual([], list(root.iterdir()))

    def test_insufficient_remote_byte_budget_fails_before_download(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()
        called = False

        def forbidden_snapshot(**_kwargs):
            nonlocal called
            called = True
            raise AssertionError("download must not begin")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
                self.assertRaises(StagingError),
            ):
                stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=forbidden_snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=1),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )
            self.assertFalse(called)
            self.assertFalse(
                (
                    root
                    / protocol.STUDY_SLUG
                    / protocol.STUDY_ID
                    / "public_artifacts.partial"
                ).exists()
            )

    def test_remote_byte_identity_mismatch_blocks_publication(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()

        def corrupt_snapshot(**kwargs):
            root = Path(snapshot(**kwargs))
            (root / "config.json").write_bytes(b"[]")
            return str(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
                self.assertRaisesRegex(StagingError, "SHA-256"),
            ):
                stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=corrupt_snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )
            self.assertFalse(
                (root / protocol.STUDY_SLUG / protocol.STUDY_ID / "public_artifacts").exists()
            )

    def test_resume_rejects_unplanned_stale_file(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_or_validate_volume(root, volume_id="unit-volume")
            partial = (
                root
                / protocol.STUDY_SLUG
                / protocol.STUDY_ID
                / "public_artifacts.partial"
            )
            partial.mkdir(parents=True)
            (partial / "stale-secret.txt").write_text("not allowed", encoding="utf-8")
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
                self.assertRaisesRegex(StagingError, "unplanned files"),
            ):
                stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=snapshot,
                    hub_download=download,
                    resume_partial=True,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )

    def test_token_bytes_in_valid_remote_file_block_publication(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()

        def secret_resolve(repository, revision, token):
            info = resolve(repository, revision, token)
            if repository == protocol.MODEL_SPEC["repository"]:
                record = next(row for row in info["files"] if row["path"] == ".gitattributes")
                record.clear()
                record.update(
                    path=".gitattributes",
                    size=len(b"test-token"),
                    sha256=_sha(b"test-token"),
                )
            return info

        def secret_snapshot(**kwargs):
            root = Path(snapshot(**kwargs))
            (root / ".gitattributes").write_bytes(b"test-token")
            return str(root)

        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
                self.assertRaisesRegex(StagingError, "credential bytes"),
            ):
                stage_public_artifacts(
                    artifact_root=Path(temporary),
                    **self._attestation_kwargs(),
                    volume_id="unit-volume",
                    token="test-token",
                    resolve_remote=secret_resolve,
                    snapshot_download=secret_snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )

    def test_volume_sentinel_rejects_identity_change_and_symlink_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "volume"
            root.mkdir()
            initialize_or_validate_volume(root, volume_id="volume-a")
            with self.assertRaises(StagingError):
                initialize_or_validate_volume(root, volume_id="volume-b")
            link = Path(temporary) / "link"
            link.symlink_to(root, target_is_directory=True)
            with self.assertRaises(StagingError):
                initialize_or_validate_volume(link, volume_id="volume-a")

    def test_symlinked_study_parent_cannot_escape_volume(self):
        resolve, snapshot, download, sae_spec, j_spec = self._fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "volume"
            outside = Path(temporary) / "outside"
            root.mkdir()
            outside.mkdir()
            initialize_or_validate_volume(root, volume_id="volume-a")
            (root / protocol.STUDY_SLUG).symlink_to(outside, target_is_directory=True)
            with (
                mock.patch.dict(protocol.SAE_SPEC, sae_spec, clear=True),
                mock.patch.dict(protocol.J_LENS_SPEC, j_spec, clear=True),
                self.assertRaisesRegex(StagingError, "unsafe entry"),
            ):
                stage_public_artifacts(
                    artifact_root=root,
                    **self._attestation_kwargs(),
                    volume_id="volume-a",
                    token="test-token",
                    resolve_remote=resolve,
                    snapshot_download=snapshot,
                    hub_download=download,
                    disk_usage=lambda _path: SimpleNamespace(free=10**15),
                    min_stage_headroom_bytes=0,
                    min_final_free_bytes=0,
                )


if __name__ == "__main__":
    unittest.main()
