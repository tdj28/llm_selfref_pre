from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from experiments.consciousness_readout_validation import guest_attestation, paths, protocol


class GuestAttestationTests(unittest.TestCase):
    POD_ID = "owned-pod-123"
    BOOT_ID = "12345678-1234-4abc-8def-1234567890ab"
    NOW = datetime(2026, 7, 13, 20, 0, 0, tzinfo=timezone.utc)

    def _environment(self) -> dict[str, str]:
        return {
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def _pid1_environment(self, **updates: str) -> bytes:
        values = {
            "RUNPOD_POD_ID": self.POD_ID,
            "RUNPOD_VOLUME_ID": guest_attestation.EXPECTED_VOLUME_ID,
            "RUNPOD_DC_ID": guest_attestation.EXPECTED_DATA_CENTER_ID,
            "RUNPOD_API_KEY": "unit-secret-that-must-never-be-retained",
            "UNRELATED_PROVIDER_VALUE": "opaque",
        }
        values.update(updates)
        return b"\0".join(
            f"{name}={value}".encode("utf-8") for name, value in values.items()
        ) + b"\0"

    @staticmethod
    def _cmdline(module: str) -> bytes:
        return b"python3\0-B\0-m\0" + module.encode("ascii") + b"\0"

    def _mountinfo(
        self,
        workspace: Path,
        *,
        device: str = "0:42",
        mount_root: str = "/",
        mount_source: str = "server:/volume",
        mount_point: str | None = None,
    ) -> str:
        return (
            f"101 99 {device} {mount_root} "
            f"{mount_point or workspace.resolve()} rw,relatime "
            f"- nfs4 {mount_source} rw\n"
        )

    def _attest(self, workspace: Path, receipt_dir: Path, **overrides):
        arguments = {
            "owned_pod_id": self.POD_ID,
            "volume_id": guest_attestation.EXPECTED_VOLUME_ID,
            "data_center_id": guest_attestation.EXPECTED_DATA_CENTER_ID,
            "receipt_dir": receipt_dir,
            "environ": self._environment(),
            "workspace": workspace,
            "nvidia_smi": lambda: "0, NVIDIA B200, 183359\n",
            "read_mountinfo": lambda: self._mountinfo(workspace),
            "is_mount": lambda candidate: candidate == str(workspace.resolve()),
            "access": lambda _candidate, _mode: True,
            "disk_usage": lambda _candidate: SimpleNamespace(
                free=(
                    guest_attestation.FROZEN_PUBLIC_ARTIFACT_BYTES
                    + guest_attestation.MIN_STAGE_HEADROOM_BYTES
                    + 12345
                )
            ),
            "read_pid1_environ": self._pid1_environment,
            "read_boot_id": lambda: self.BOOT_ID,
            "read_process_cmdline": lambda: self._cmdline(
                guest_attestation.GUEST_ATTESTATION_MODULE
            ),
            "runtime_dont_write_bytecode": True,
            "now": self.NOW,
        }
        arguments.update(overrides)
        with mock.patch.object(
            guest_attestation, "WORKSPACE_ROOT", workspace.resolve()
        ):
            return guest_attestation.attest_guest(**arguments)

    def _validate(self, workspace: Path, receipt: Path, **overrides):
        arguments = {
            "expected_owned_pod_id": self.POD_ID,
            "expected_volume_id": guest_attestation.EXPECTED_VOLUME_ID,
            "expected_data_center_id": guest_attestation.EXPECTED_DATA_CENTER_ID,
            "expected_artifact_root": workspace,
            "environ": self._environment(),
            "workspace": workspace,
            "nvidia_smi": lambda: "0, NVIDIA B200, 183359\n",
            "read_mountinfo": lambda: self._mountinfo(workspace),
            "is_mount": lambda candidate: candidate == str(workspace.resolve()),
            "access": lambda _candidate, _mode: True,
            "disk_usage": lambda _candidate: SimpleNamespace(
                free=(
                    guest_attestation.FROZEN_PUBLIC_ARTIFACT_BYTES
                    + guest_attestation.MIN_STAGE_HEADROOM_BYTES
                    + 12345
                )
            ),
            "read_pid1_environ": self._pid1_environment,
            "read_boot_id": lambda: self.BOOT_ID,
            "read_process_cmdline": lambda: self._cmdline(
                guest_attestation.STAGE_PUBLIC_ARTIFACTS_MODULE
            ),
            "runtime_dont_write_bytecode": True,
            "now": self.NOW,
        }
        arguments.update(overrides)
        with mock.patch.object(
            guest_attestation, "WORKSPACE_ROOT", workspace.resolve()
        ):
            return guest_attestation.validate_guest_attestation_receipt(
                receipt, **arguments
            )

    def test_pass_receipt_is_external_self_hashed_and_does_not_create_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            receipt_path = self._attest(workspace, external / "attestation")

            self.assertFalse((workspace / paths.VOLUME_SENTINEL).exists())
            self.assertEqual(
                stat.S_IMODE(receipt_path.stat().st_mode),
                0o600,
            )
            receipt = json.loads(receipt_path.read_bytes())
            sealed = dict(receipt)
            embedded = sealed.pop("receipt_sha256")
            self.assertEqual(protocol.canonical_sha256(sealed), embedded)
            self.assertEqual("pass", receipt["status"])
            self.assertEqual(
                "provider_pid1_environment",
                receipt["identity_binding"]["provenance"],
            )
            self.assertEqual(
                {
                    "RUNPOD_POD_ID": self.POD_ID,
                    "RUNPOD_VOLUME_ID": guest_attestation.EXPECTED_VOLUME_ID,
                    "RUNPOD_DC_ID": guest_attestation.EXPECTED_DATA_CENTER_ID,
                },
                receipt["identity_binding"]["allowlisted_values"],
            )
            self.assertNotIn(
                b"unit-secret-that-must-never-be-retained",
                receipt_path.read_bytes(),
            )
            self.assertNotIn(b"RUNPOD_API_KEY", receipt_path.read_bytes())
            self.assertNotIn(b"UNRELATED_PROVIDER_VALUE", receipt_path.read_bytes())
            self.assertNotIn(b"opaque", receipt_path.read_bytes())
            self.assertEqual(
                guest_attestation.FROZEN_PUBLIC_ARTIFACT_BYTES,
                receipt["disk"]["frozen_public_artifact_bytes"],
            )
            self.assertEqual(
                "absent_safe_for_stager_initialization",
                receipt["volume_sentinel"]["state"],
            )
            self.assertEqual("0:42", receipt["mount"]["device_major_minor"])
            self.assertEqual(
                hashlib.sha256(b"/").hexdigest(),
                receipt["mount"]["mount_root_raw_field_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(b"server:/volume").hexdigest(),
                receipt["mount"]["mount_source_raw_field_sha256"],
            )
            self.assertEqual(
                "sha256_utf8_of_exact_raw_mountinfo_field_without_unescaping",
                receipt["mount"]["raw_field_hash_semantics"],
            )
            self.assertNotIn("mount_root", receipt["mount"])
            self.assertNotIn("mount_source", receipt["mount"])
            self.assertEqual(
                guest_attestation.expected_python_launch_contract(
                    guest_attestation.GUEST_ATTESTATION_MODULE
                ),
                receipt["python_launch_contract"],
            )
            self.assertTrue(receipt["repository_source"]["outside_workspace"])
            self.assertEqual(
                hashlib.sha256(str(paths.REPO_ROOT.resolve()).encode("utf-8")).hexdigest(),
                receipt["repository_source"]["resolved_path_sha256"],
            )
            validated = self._validate(workspace, receipt_path)
            self.assertEqual(embedded, validated["receipt_sha256"])

    def test_launch_contract_and_external_repository_root_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()

            wrong_environment = self._environment()
            wrong_environment["PYTHONDONTWRITEBYTECODE"] = "0"
            cases = {
                "environment": {"environ": wrong_environment},
                "runtime": {"runtime_dont_write_bytecode": False},
                "minus_b": {
                    "read_process_cmdline": lambda: (
                        b"python3\0-m\0"
                        + guest_attestation.GUEST_ATTESTATION_MODULE.encode("ascii")
                        + b"\0"
                    )
                },
            }
            for name, overrides in cases.items():
                destination = external / name
                with self.subTest(name=name), self.assertRaises(
                    guest_attestation.GuestAttestationError
                ):
                    self._attest(workspace, destination, **overrides)
                self.assertFalse(destination.exists())

            repository_inside_workspace = workspace / "repo"
            repository_inside_workspace.mkdir()
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError,
                "source root must be outside /workspace",
            ):
                self._attest(
                    workspace,
                    external / "inside-repository",
                    repository_root=repository_inside_workspace,
                )
            self.assertEqual([repository_inside_workspace], list(workspace.iterdir()))

    def test_stager_revalidates_launch_and_exact_repository_source_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            other_repository = root / "other-repository"
            workspace.mkdir()
            external.mkdir()
            other_repository.mkdir()
            receipt = self._attest(workspace, external / "attestation")

            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError,
                "source-root binding differs",
            ):
                self._validate(
                    workspace,
                    receipt,
                    repository_root=other_repository,
                )
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError,
                "exact -B",
            ):
                self._validate(
                    workspace,
                    receipt,
                    read_process_cmdline=lambda: self._cmdline(
                        guest_attestation.GUEST_ATTESTATION_MODULE
                    ),
                )

    def test_validation_rejects_same_fstype_mount_identity_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            receipt = self._attest(workspace, external / "attestation")

            changed_mounts = {
                "device": self._mountinfo(workspace, device="0:43"),
                "root": self._mountinfo(workspace, mount_root="/another-volume-root"),
                "source": self._mountinfo(workspace, mount_source="server:/another-volume"),
            }
            for field, mountinfo in changed_mounts.items():
                with self.subTest(field=field), self.assertRaisesRegex(
                    guest_attestation.GuestAttestationError,
                    "current /workspace mount differs",
                ):
                    self._validate(
                        workspace,
                        receipt,
                        read_mountinfo=lambda mountinfo=mountinfo: mountinfo,
                    )

    def test_mountinfo_parser_is_bounded_and_mount_point_decode_is_strict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()

            cases = {
                "oversized": "x" * (guest_attestation.MAX_MOUNTINFO_BYTES + 1),
                "unknown-mount-point-escape": self._mountinfo(
                    workspace,
                    mount_point=f"{workspace.resolve()}" + r"\043",
                ),
            }
            for name, mountinfo in cases.items():
                destination = external / name
                with self.subTest(name=name), self.assertRaises(
                    guest_attestation.GuestAttestationError
                ):
                    self._attest(
                        workspace,
                        destination,
                        read_mountinfo=lambda mountinfo=mountinfo: mountinfo,
                    )
                self.assertFalse(destination.exists())

    def test_fuse_source_notation_is_hashed_as_exact_raw_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            raw_source = r"runpod-volume\043snapshot"
            receipt_path = self._attest(
                workspace,
                external / "attestation",
                read_mountinfo=lambda: self._mountinfo(
                    workspace, mount_source=raw_source
                ),
            )
            receipt = json.loads(receipt_path.read_bytes())
            self.assertEqual(
                hashlib.sha256(raw_source.encode("utf-8")).hexdigest(),
                receipt["mount"]["mount_source_raw_field_sha256"],
            )
            self._validate(
                workspace,
                receipt_path,
                read_mountinfo=lambda: self._mountinfo(
                    workspace, mount_source=raw_source
                ),
            )
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError,
                "current /workspace mount differs",
            ):
                self._validate(
                    workspace,
                    receipt_path,
                    read_mountinfo=lambda: self._mountinfo(
                        workspace, mount_source="runpod-volume#snapshot"
                    ),
                )

    def test_provider_pid1_identity_mismatch_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "identity variables"
            ):
                self._attest(
                    workspace,
                    external / "attestation",
                    read_pid1_environ=lambda: self._pid1_environment(
                        RUNPOD_VOLUME_ID="another-volume"
                    ),
                )
            self.assertFalse((external / "attestation").exists())
            self.assertFalse((workspace / paths.VOLUME_SENTINEL).exists())

    def test_provider_pid1_parser_is_bounded_unique_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            cases = {
                "missing": b"UNRELATED=value\0",
                "duplicate": (
                    self._pid1_environment()
                    + f"RUNPOD_POD_ID={self.POD_ID}".encode("ascii")
                    + b"\0"
                ),
                "unterminated": self._pid1_environment()[:-1],
                "oversized": b"X=" + b"x" * guest_attestation.MAX_PID1_ENVIRON_BYTES,
            }
            for label, payload in cases.items():
                destination = external / label
                with self.subTest(label=label), self.assertRaises(
                    guest_attestation.GuestAttestationError
                ):
                    self._attest(
                        workspace,
                        destination,
                        read_pid1_environ=lambda payload=payload: payload,
                    )
                self.assertFalse(destination.exists())

    def test_ssh_child_identity_spoof_is_ignored_in_favor_of_pid1(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            child_environment = self._environment()
            child_environment.update(
                {
                    "RUNPOD_POD_ID": "spoofed-child-pod",
                    "RUNPOD_VOLUME_ID": "spoofed-child-volume",
                    "RUNPOD_DC_ID": "spoofed-child-dc",
                }
            )
            receipt_path = self._attest(
                workspace,
                external / "attestation",
                environ=child_environment,
            )
            receipt = json.loads(receipt_path.read_bytes())
            self.assertEqual(
                self.POD_ID,
                receipt["identity_binding"]["allowlisted_values"]["RUNPOD_POD_ID"],
            )
            self.assertNotIn(b"spoofed-child", receipt_path.read_bytes())

    def test_stager_rejects_changed_provider_pid1_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            receipt = self._attest(workspace, external / "attestation")
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "identity variables differ"
            ):
                self._validate(
                    workspace,
                    receipt,
                    read_pid1_environ=lambda: self._pid1_environment(
                        RUNPOD_POD_ID="another-provider-pod"
                    ),
                )

    def test_requires_exactly_one_large_b200(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            for output in (
                "0, NVIDIA H100 80GB HBM3, 81559\n",
                "0, NVIDIA B200, 183359\n1, NVIDIA B200, 183359\n",
                "0, NVIDIA B200, 100000\n",
            ):
                with self.subTest(output=output):
                    destination = external / f"attestation-{abs(hash(output))}"
                    with self.assertRaises(guest_attestation.GuestAttestationError):
                        self._attest(
                            workspace,
                            destination,
                            nvidia_smi=lambda output=output: output,
                        )
                    self.assertFalse(destination.exists())

    def test_mount_and_frozen_disk_budget_fail_before_receipt_or_sentinel(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "mount point"
            ):
                self._attest(
                    workspace,
                    external / "mount-fail",
                    is_mount=lambda _candidate: False,
                )
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "insufficient free bytes"
            ):
                self._attest(
                    workspace,
                    external / "disk-fail",
                    disk_usage=lambda _candidate: SimpleNamespace(free=1),
                )
            self.assertFalse((workspace / paths.VOLUME_SENTINEL).exists())

    def test_existing_sentinel_must_match_exactly_but_is_never_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            expected = {
                "schema_version": 1,
                "study_slug": protocol.STUDY_SLUG,
                "study_id": protocol.STUDY_ID,
                "volume_id": guest_attestation.EXPECTED_VOLUME_ID,
            }
            sentinel = workspace / paths.VOLUME_SENTINEL
            sentinel.write_bytes(protocol.canonical_json_bytes(expected) + b"\n")
            receipt = self._attest(workspace, external / "attestation")
            payload = json.loads(receipt.read_bytes())
            self.assertEqual("exact_existing_match", payload["volume_sentinel"]["state"])
            self.assertEqual(
                protocol.canonical_json_bytes(expected) + b"\n", sentinel.read_bytes()
            )

            sentinel.write_text('{"volume_id":"wrong"}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "sentinel differs"
            ):
                self._attest(workspace, external / "second-attestation")

    def test_receipt_must_be_fresh_same_boot_and_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "outside repository and /workspace"
            ):
                self._attest(workspace, workspace / "inside-attestation")

            receipt = self._attest(workspace, external / "attestation")
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "stale"
            ):
                self._validate(
                    workspace,
                    receipt,
                    now=self.NOW
                    + timedelta(seconds=guest_attestation.MAX_RECEIPT_AGE_SECONDS + 1),
                )
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "another guest boot"
            ):
                self._validate(
                    workspace,
                    receipt,
                    read_boot_id=lambda: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                )

    def test_receipt_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            external = root / "external"
            workspace.mkdir()
            external.mkdir()
            receipt_path = self._attest(workspace, external / "attestation")
            receipt = json.loads(receipt_path.read_bytes())
            receipt["gpu"]["name"] = "NVIDIA H100"
            receipt_path.write_bytes(protocol.canonical_json_bytes(receipt) + b"\n")
            with self.assertRaisesRegex(
                guest_attestation.GuestAttestationError, "self-hash"
            ):
                self._validate(workspace, receipt_path)


if __name__ == "__main__":
    unittest.main()
