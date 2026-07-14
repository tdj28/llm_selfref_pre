from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import runpod_preflight as gate
from experiments.consciousness_sae_realization_validation import runpod_lifecycle_adapter


class RunPodPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.created = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
        self.contract = gate.build_create_contract(
            created_at=self.created,
            nonce="a" * 32,
            provider_pods=[],
        )
        ownership_core = {
            "schema_version": gate.SCHEMA_VERSION,
            "status": "owned_running_isolated",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "pod_id": "abc123def456",
            "pod_name": self.contract["pod_name"],
            "ownership_nonce": self.contract["ownership_nonce"],
            "network_volume_id": gate.EXPECTED_VOLUME_ID,
            "provider_volume_size_bytes": gate.EXPECTED_PROVIDER_VOLUME_BYTES,
            "data_center_id": gate.EXPECTED_DATA_CENTER_ID,
            "gpu_type": gate.EXPECTED_GPU_TYPE,
            "gpu_count": 1,
            "volume_mount_path": gate.VOLUME_MOUNT_PATH,
            "created_at": self.contract["created_at"],
            "terminate_after": self.contract["terminate_after"],
            "create_contract_sha256": self.contract["create_contract_sha256"],
            "upstream_lifecycle_receipt_sha256": "0" * 64,
            "provider_container_image_attestation": {
                "source": "validated_graphql_create_plus_final_rest_readback_v1",
                "immutable_reference": protocol.CONTAINER_IMAGE_SPEC[
                    "immutable_reference"
                ],
                "graphql_create_snapshot_source": (
                    "graphql_create_plus_rest_volume_proof"
                ),
                "create_request_sha256": "3" * 64,
                "final_rest_proof_source": (
                    "rest_v1_pod_get_final_after_graphql_locked_state"
                ),
                "rest_image_fields": ["imageName"],
                "upstream_lifecycle_receipt_sha256": "0" * 64,
            },
            "desired_status": "RUNNING",
            "locked": False,
            "precreate_unrelated_pod_count": self.contract[
                "precreate_unrelated_pod_count"
            ],
            "precreate_unrelated_inventory_sha256": self.contract[
                "precreate_unrelated_inventory_sha256"
            ],
        }
        self.ownership = gate.with_self_hash(ownership_core)
        guest_core = {
            "schema_version": gate.SCHEMA_VERSION,
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "ownership_receipt_sha256": self.ownership["receipt_sha256"],
            "attested_at_utc": "2026-07-14T12:01:00Z",
            "identity_source": "provider_pid1_environment",
            "provider_identity_sha256": "1" * 64,
            "observed_pod_id": self.ownership["pod_id"],
            "observed_volume_id": gate.EXPECTED_VOLUME_ID,
            "observed_data_center_id": gate.EXPECTED_DATA_CENTER_ID,
            "mount_path": gate.VOLUME_MOUNT_PATH,
            "mount_is_network_volume": True,
            "filesystem_id": "runpod-network-volume-qf2lwehl89",
            "mount_evidence_sha256": "2" * 64,
            "provider_volume_size_bytes": gate.EXPECTED_PROVIDER_VOLUME_BYTES,
            "logical_bytes_on_volume": (
                gate.EXPECTED_PROVIDER_VOLUME_BYTES
                - gate.MIN_MOUNTED_FREE_BYTES
            ),
            "allocated_bytes_on_volume": (
                gate.EXPECTED_PROVIDER_VOLUME_BYTES
                - gate.MIN_MOUNTED_FREE_BYTES
            ),
            "accounted_usage_bytes": (
                gate.EXPECTED_PROVIDER_VOLUME_BYTES
                - gate.MIN_MOUNTED_FREE_BYTES
            ),
            "quota_remaining_bytes": gate.MIN_MOUNTED_FREE_BYTES,
            "statvfs_free_bytes_diagnostic": 234_502_372_655_104,
            "minimum_required_free_bytes": gate.MIN_MOUNTED_FREE_BYTES,
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "prior_outcome_inputs": [],
        }
        self.guest = gate.with_self_hash(guest_core)

    @staticmethod
    def _rehash(value: dict) -> dict:
        core = dict(value)
        core.pop("receipt_sha256", None)
        return gate.with_self_hash(core)

    def test_create_contract_has_exact_provider_kill_and_identity(self) -> None:
        self.assertEqual(self.contract["network_volume_id"], "qf2lwehl89")
        self.assertEqual(self.contract["gpu_type"], "NVIDIA B200")
        self.assertEqual(
            self.contract["terminate_after"], "2026-07-14T18:00:00Z"
        )
        self.assertTrue(
            self.contract["pod_name"].startswith(
                "consciousness-sae-realization-validation-v1-"
            )
        )

    def test_unrelated_active_pod_is_frozen_not_blocked(self) -> None:
        unrelated = {
            "pod_id": "h200pod1",
            "pod_name": "unrelated-8xh200",
            "desired_status": "RUNNING",
            "gpu_type": "NVIDIA H200",
            "gpu_count": 8,
        }
        contract = gate.build_create_contract(
            created_at=self.created,
            nonce="b" * 32,
            provider_pods=[unrelated],
        )
        self.assertEqual(contract["precreate_unrelated_pod_count"], 1)
        collision = {**unrelated, "pod_name": gate.POD_NAME_PREFIX + "collision"}
        with self.assertRaises(gate.PreflightError):
            gate.build_create_contract(
                created_at=self.created,
                nonce="c" * 32,
                provider_pods=[collision],
            )

    def test_ownership_and_exact_guest_capacity_boundary_pass(self) -> None:
        gate.validate_ownership_receipt(self.ownership)
        observed = gate.validate_guest_receipt(
            self.guest, ownership_receipt=self.ownership
        )
        self.assertEqual(observed["quota_remaining_bytes"], 96 * 1024**3)

    def test_one_byte_below_mounted_free_gate_fails(self) -> None:
        bad = copy.deepcopy(self.guest)
        bad["logical_bytes_on_volume"] += 1
        bad["allocated_bytes_on_volume"] += 1
        bad["accounted_usage_bytes"] += 1
        bad["quota_remaining_bytes"] -= 1
        bad = self._rehash(bad)
        with self.assertRaises(gate.PreflightError):
            gate.validate_guest_receipt(bad, ownership_receipt=self.ownership)

    def test_guest_must_match_exact_owned_pod_and_volume(self) -> None:
        for field, value in (
            ("observed_pod_id", "other999"),
            ("observed_volume_id", "another-volume"),
        ):
            with self.subTest(field=field):
                bad = copy.deepcopy(self.guest)
                bad[field] = value
                bad = self._rehash(bad)
                with self.assertRaises(gate.PreflightError):
                    gate.validate_guest_receipt(
                        bad, ownership_receipt=self.ownership
                    )

    def test_guest_builder_uses_pid1_mount_tree_and_statvfs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "volume"
            root.mkdir()
            (root / "existing-public-input.bin").write_bytes(b"fixture")
            identity = (
                b"RUNPOD_POD_ID=abc123def456\0"
                b"UNRELATED_SECRET=never-persist-this\0"
                b"RUNPOD_VOLUME_ID=qf2lwehl89\0"
                b"RUNPOD_DC_ID=US-NE-1\0"
            )
            mountinfo = (
                f"36 25 0:32 / {root} rw,relatime - nfs4 server:/volume rw\n"
            )
            receipt = gate.build_guest_receipt(
                ownership_receipt=self.ownership,
                volume_root=root,
                read_pid1_environ=lambda: identity,
                read_mountinfo=lambda: mountinfo,
                is_mount=lambda _path: True,
                statvfs=os.statvfs,
                now=self.created + timedelta(minutes=1),
                require_exact_mount_path=False,
            )
            self.assertEqual(receipt["observed_pod_id"], self.ownership["pod_id"])
            self.assertEqual(receipt["identity_source"], "provider_pid1_environment")
            self.assertNotIn("never-persist-this", gate.canonical_json_bytes(receipt).decode())
            gate.validate_guest_receipt(receipt, ownership_receipt=self.ownership)
            with self.assertRaises(gate.PreflightError):
                gate.build_guest_receipt(
                    ownership_receipt=self.ownership,
                    volume_root=root,
                    read_pid1_environ=lambda: identity.replace(
                        b"abc123def456", b"wrongpod999"
                    ),
                    read_mountinfo=lambda: mountinfo,
                    is_mount=lambda _path: True,
                    statvfs=os.statvfs,
                    now=self.created + timedelta(minutes=1),
                    require_exact_mount_path=False,
                )

    def test_unrelated_inventory_must_survive_create_and_delete_unchanged(self) -> None:
        unrelated = {
            "pod_id": "h200pod1",
            "pod_name": "unrelated-8xh200",
            "desired_status": "RUNNING",
            "gpu_type": "NVIDIA H200",
            "gpu_count": 8,
        }
        contract = gate.build_create_contract(
            created_at=self.created,
            nonce="d" * 32,
            provider_pods=[unrelated],
        )
        core = dict(self.ownership)
        core.pop("receipt_sha256")
        core.update(
            {
                "pod_name": contract["pod_name"],
                "ownership_nonce": contract["ownership_nonce"],
                "create_contract_sha256": contract["create_contract_sha256"],
                "precreate_unrelated_pod_count": 1,
                "precreate_unrelated_inventory_sha256": contract[
                    "precreate_unrelated_inventory_sha256"
                ],
            }
        )
        ownership = gate.with_self_hash(core)
        owned_row = {
            "pod_id": ownership["pod_id"],
            "pod_name": ownership["pod_name"],
        }
        gate.validate_inventory_after_create(
            precreate_pods=[unrelated],
            postcreate_pods=[unrelated, owned_row],
            ownership_receipt=ownership,
        )
        gate.validate_inventory_after_delete(
            precreate_pods=[unrelated],
            postdelete_pods=[unrelated],
            ownership_receipt=ownership,
        )
        mutated = {**unrelated, "desired_status": "STOPPED"}
        with self.assertRaises(gate.PreflightError):
            gate.validate_inventory_after_delete(
                precreate_pods=[unrelated],
                postdelete_pods=[mutated],
                ownership_receipt=ownership,
            )
        self.assertEqual(
            gate.require_exact_owned_pod_id(
                ownership["pod_id"], ownership_receipt=ownership
            ),
            ownership["pod_id"],
        )
        with self.assertRaises(gate.PreflightError):
            gate.require_exact_owned_pod_id(
                unrelated["pod_id"], ownership_receipt=ownership
            )

    def test_legacy_public_cache_is_read_only_rehashed_input(self) -> None:
        cache_core = {
            "schema_version": gate.SCHEMA_VERSION,
            "status": "pass",
            "study_id": protocol.STUDY_ID,
            "protocol_version": protocol.PROTOCOL_VERSION,
            "guest_receipt_sha256": self.guest["receipt_sha256"],
            "cache_root": gate.LEGACY_PUBLIC_ARTIFACT_ROOT,
            "cache_role": "immutable_public_artifacts_only",
            "read_only": True,
            "independently_rehashed": True,
            "full_file_count": gate.LEGACY_PUBLIC_ARTIFACT_FILE_COUNT,
            "full_retained_bytes": gate.LEGACY_PUBLIC_ARTIFACT_BYTES,
            "full_file_inventory_sha256": (
                gate.LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
            ),
            "components": [
                {
                    "component": "model",
                    "revision": protocol.MODEL_SPEC["revision"],
                    "relative_path": "model_snapshot",
                    "byte_count": 1,
                    "sha256": gate.LEGACY_MODEL_FILE_INVENTORY_SHA256,
                    "verified": True,
                },
                {
                    "component": "sae",
                    "revision": protocol.SAE_SPEC["revision"],
                    "relative_path": "sae/Llama-3.3-70B-Instruct-SAE-l50.pt",
                    "byte_count": 1,
                    "sha256": protocol.SAE_SPEC["sha256"],
                    "verified": True,
                },
                {
                    "component": "j_lens",
                    "revision": protocol.J_LENS_SPEC["revision"],
                    "relative_path": (
                        "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt"
                    ),
                    "byte_count": 1,
                    "sha256": protocol.J_LENS_SPEC["sha256"],
                    "verified": True,
                },
            ],
            "model_forward_count": 0,
            "target_prompt_render_count": 0,
            "prior_outcome_inputs": [],
        }
        receipt = gate.with_self_hash(cache_core)
        gate.validate_cache_receipt(
            receipt,
            guest_receipt=self.guest,
            ownership_receipt=self.ownership,
        )
        bad = copy.deepcopy(receipt)
        bad["cache_root"] = (
            "/workspace/consciousness_sae_realization_validation/"
            "consciousness_sae_realization_validation_v1/public_artifacts"
        )
        bad = self._rehash(bad)
        with self.assertRaises(gate.PreflightError):
            gate.validate_cache_receipt(
                bad,
                guest_receipt=self.guest,
                ownership_receipt=self.ownership,
            )

    def test_pinned_legacy_manifest_covers_all_45_public_files(self) -> None:
        manifest = gate.load_legacy_public_artifact_manifest()
        self.assertEqual(manifest["cache_root"], gate.LEGACY_PUBLIC_ARTIFACT_ROOT)
        self.assertEqual(len(manifest["files"]), 45)
        self.assertEqual(
            gate.canonical_sha256(manifest["files"]),
            gate.LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256,
        )

    def test_independent_tree_rehash_rejects_tamper_extra_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cache"
            root.mkdir()
            payload = b"public-weight-fixture"
            target = root / "model.bin"
            target.write_bytes(payload)
            expected = [
                {
                    "bytes": len(payload),
                    "path": "model.bin",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ]
            self.assertEqual(
                gate.rehash_artifact_tree(root, expected_files=expected),
                tuple(expected),
            )
            target.write_bytes(payload + b"tamper")
            with self.assertRaises(gate.PreflightError):
                gate.rehash_artifact_tree(root, expected_files=expected)
            target.write_bytes(payload)
            (root / "extra").write_bytes(b"extra")
            with self.assertRaises(gate.PreflightError):
                gate.rehash_artifact_tree(root, expected_files=expected)
            (root / "extra").unlink()
            target.unlink()
            os.symlink(Path(directory) / "outside", target)
            with self.assertRaises(gate.PreflightError):
                gate.rehash_artifact_tree(root, expected_files=expected)

    def test_all_cli_builds_guest_then_cache_without_hand_authored_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ownership_path = root / "ownership.json"
            ownership_path.write_text(
                gate.canonical_json_bytes(self.ownership).decode("utf-8") + "\n",
                encoding="utf-8",
            )
            cache = gate.with_self_hash(
                {
                    "kind": "test-cache-builder-output",
                    "guest_receipt_sha256": self.guest["receipt_sha256"],
                }
            )
            with (
                mock.patch.object(
                    gate, "build_guest_receipt", return_value=self.guest
                ) as guest_builder,
                mock.patch.object(
                    gate, "build_cache_receipt", return_value=cache
                ) as cache_builder,
            ):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = gate.main(
                        [
                            "all",
                            "--ownership-receipt",
                            str(ownership_path),
                            "--receipt-dir",
                            str(root / "receipts"),
                        ]
                    )
            self.assertEqual(status, 0)
            guest_builder.assert_called_once_with(ownership_receipt=self.ownership)
            cache_builder.assert_called_once_with(
                guest_receipt=self.guest,
                ownership_receipt=self.ownership,
            )
            self.assertTrue((root / "receipts" / gate.GUEST_RECEIPT_FILENAME).is_file())
            self.assertTrue((root / "receipts" / gate.CACHE_RECEIPT_FILENAME).is_file())

    def test_cumulative_meter_spans_both_stages(self) -> None:
        meter = gate.CumulativeMeter(
            provider_created_at=self.created,
            provider_terminate_after=self.created + timedelta(hours=6),
            hourly_price_usd=5.0,
            prior_elapsed_seconds=2 * 3600,
            prior_spend_usd=10.0,
        )
        observed = meter.check(
            observed_at=self.created + timedelta(hours=5),
            current_process_elapsed_seconds=3 * 3600 - 1,
            seconds_since_progress=1,
        )
        self.assertLess(observed["cumulative_estimated_spend_usd"], 36)
        with self.assertRaises(gate.PreflightError):
            meter.check(
                observed_at=self.created + timedelta(hours=6),
                current_process_elapsed_seconds=4 * 3600,
                seconds_since_progress=1,
            )

    def test_no_progress_and_worst_case_price_fail_closed(self) -> None:
        meter = gate.CumulativeMeter(
            provider_created_at=self.created,
            provider_terminate_after=self.created + timedelta(hours=6),
            hourly_price_usd=5.0,
        )
        with self.assertRaises(gate.PreflightError):
            meter.check(
                observed_at=self.created + timedelta(minutes=20),
                current_process_elapsed_seconds=20 * 60,
                seconds_since_progress=gate.MAX_NO_PROGRESS_SECONDS,
            )
        with self.assertRaises(gate.PreflightError):
            gate.CumulativeMeter(
                provider_created_at=self.created,
                provider_terminate_after=self.created + timedelta(hours=6),
                hourly_price_usd=6.01,
            )

    def test_volume_scan_does_not_follow_symlink_and_charges_sparse_logical_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "volume"
            root.mkdir()
            sparse = root / "sparse.bin"
            with sparse.open("wb") as handle:
                handle.seek(8 * 1024**2 - 1)
                handle.write(b"\0")
            usage = gate.measure_volume_usage(root)
            self.assertGreaterEqual(
                usage["accounted_usage_bytes"], usage["logical_bytes_on_volume"]
            )
            self.assertGreater(
                usage["logical_bytes_on_volume"], usage["allocated_bytes_on_volume"]
            )
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "must-not-be-counted.bin").write_bytes(b"x" * 1024**2)
            before = usage["logical_bytes_on_volume"]
            link = root / "non-followed-link"
            os.symlink(outside, link)
            after = gate.measure_volume_usage(root)["logical_bytes_on_volume"]
            self.assertLess(after - before, 1024**2)
            with self.assertRaises(gate.PreflightError):
                gate.validate_study_owned_output_tree(root)

    def test_lifecycle_adapter_rebinds_and_restores_frozen_client(self) -> None:
        frozen = runpod_lifecycle_adapter.frozen
        prior_protocol = frozen.protocol
        prior_prefix = frozen.POD_NAME_PREFIX
        with runpod_lifecycle_adapter.configured_frozen_lifecycle() as lifecycle:
            self.assertEqual(lifecycle.protocol.STUDY_ID, protocol.STUDY_ID)
            self.assertEqual(lifecycle.POD_NAME_PREFIX, gate.POD_NAME_PREFIX)
            self.assertEqual(
                lifecycle.protocol.CONTAINER_IMAGE_SPEC["manifest_digest"],
                protocol.CONTAINER_IMAGE_SPEC["immutable_reference"].rsplit("@", 1)[1],
            )
            self.assertIsNot(lifecycle.protocol, prior_protocol)
        self.assertIs(frozen.protocol, prior_protocol)
        self.assertEqual(frozen.POD_NAME_PREFIX, prior_prefix)

    def test_lifecycle_adapter_actual_cli_path_has_network_free_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            receipt_dir = Path(directory) / "receipts"
            pod_name = gate.POD_NAME_PREFIX + "20260714-" + "e" * 32
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = runpod_lifecycle_adapter.main(
                    [
                        "create",
                        "--receipt-dir",
                        str(receipt_dir),
                        "--pod-name",
                        pod_name,
                        "--network-volume-id",
                        gate.EXPECTED_VOLUME_ID,
                        "--data-center-id",
                        gate.EXPECTED_DATA_CENTER_ID,
                        "--max-usd",
                        "36",
                        "--max-hours",
                        "6",
                    ]
                )
            self.assertEqual(status, 0)
            self.assertTrue((receipt_dir / "CREATE_DRY_RUN.json").is_file())
            payload = (receipt_dir / "CREATE_DRY_RUN.json").read_text(encoding="utf-8")
            self.assertIn(protocol.STUDY_ID, payload)
            self.assertIn(pod_name, payload)
            with self.assertRaises(runpod_lifecycle_adapter.frozen.LifecycleError):
                runpod_lifecycle_adapter.main(
                    [
                        "create",
                        "--receipt-dir",
                        str(Path(directory) / "bad"),
                        "--pod-name",
                        pod_name,
                        "--network-volume-id",
                        "wrongvolume",
                        "--data-center-id",
                        gate.EXPECTED_DATA_CENTER_ID,
                        "--max-usd",
                        "36",
                        "--max-hours",
                        "6",
                    ]
                )

    def test_frozen_ownership_conversion_reaches_guest_cache_and_runner(self) -> None:
        from tests.consciousness_readout_validation.test_runpod_lifecycle import (
            API_KEY,
            FakeGraphQLApi,
            FakeRestApi,
            _graphql_pod,
            _graphql_read_response,
            _graphql_response,
            _pod,
        )
        from experiments.consciousness_sae_realization_validation import runner

        unrelated_raw = {
            "id": "h200pod1",
            "name": "unrelated-8xh200",
            "desiredStatus": "RUNNING",
            "gpuCount": 8,
            "machine": {"gpuTypeId": "NVIDIA H200"},
        }
        precreate = runpod_lifecycle_adapter.compact_provider_inventory(
            [unrelated_raw]
        )
        nonce = "f" * 32
        contract = gate.build_create_contract(
            created_at=self.created,
            nonce=nonce,
            provider_pods=precreate,
        )
        pod_name = contract["pod_name"]
        provider_pod = _pod(
            name=pod_name,
            imageName=protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        )
        graphql_pod = _graphql_pod(
            name=pod_name,
            imageName=protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        )
        rest_api = FakeRestApi(
            pod=provider_pod,
            additional_pods=[unrelated_raw],
            volume={
                "id": gate.EXPECTED_VOLUME_ID,
                "name": "lens-campaign",
                "size": 500,
                "dataCenterId": gate.EXPECTED_DATA_CENTER_ID,
            },
        )
        graphql_api = FakeGraphQLApi(
            response=_graphql_response(graphql_pod),
            read_responses=[_graphql_read_response(name=pod_name)],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with runpod_lifecycle_adapter.configured_frozen_lifecycle() as lifecycle:
                upstream_path = lifecycle.create_lifecycle(
                    receipt_dir=root / "upstream",
                    pod_name=pod_name,
                    volume_id=gate.EXPECTED_VOLUME_ID,
                    data_center_id=gate.EXPECTED_DATA_CENTER_ID,
                    max_usd_text="36",
                    max_hours_text="6",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: self.created,
                    sleeper=lambda _seconds: None,
                )
            status, postcreate_raw = rest_api(
                "GET", "/pods?includeMachine=true&includeNetworkVolume=true", None
            )
            self.assertEqual(status, 200)
            ownership = runpod_lifecycle_adapter.load_and_build_successor_ownership(
                upstream_ownership_path=upstream_path,
                create_contract=contract,
                precreate_inventory=[unrelated_raw],
                postcreate_inventory=postcreate_raw,
                api_key=API_KEY,
            )
            gate.validate_ownership_receipt(ownership)
            self.assertEqual(
                ownership["provider_container_image_attestation"],
                {
                    "source": (
                        "validated_graphql_create_plus_final_rest_readback_v1"
                    ),
                    "immutable_reference": protocol.CONTAINER_IMAGE_SPEC[
                        "immutable_reference"
                    ],
                    "graphql_create_snapshot_source": (
                        "graphql_create_plus_rest_volume_proof"
                    ),
                    "create_request_sha256": ownership[
                        "provider_container_image_attestation"
                    ]["create_request_sha256"],
                    "final_rest_proof_source": (
                        "rest_v1_pod_get_final_after_graphql_locked_state"
                    ),
                    "rest_image_fields": ["imageName"],
                    "upstream_lifecycle_receipt_sha256": ownership[
                        "upstream_lifecycle_receipt_sha256"
                    ],
                },
            )

            volume = root / "volume-fixture"
            volume.mkdir()
            (volume / "existing.bin").write_bytes(b"public")
            pid1 = (
                f"RUNPOD_POD_ID={ownership['pod_id']}\0"
                f"RUNPOD_VOLUME_ID={gate.EXPECTED_VOLUME_ID}\0"
                f"RUNPOD_DC_ID={gate.EXPECTED_DATA_CENTER_ID}\0"
            ).encode()
            mountinfo = (
                f"36 25 0:32 / {volume} rw - nfs4 server:/volume rw\n"
            )
            guest = gate.build_guest_receipt(
                ownership_receipt=ownership,
                volume_root=volume,
                read_pid1_environ=lambda: pid1,
                read_mountinfo=lambda: mountinfo,
                is_mount=lambda _path: True,
                statvfs=os.statvfs,
                now=self.created + timedelta(minutes=1),
                require_exact_mount_path=False,
            )

            cache_root = root / "legacy-public-artifacts"
            model = cache_root / "model_snapshot"
            sae = cache_root / "sae" / "Llama-3.3-70B-Instruct-SAE-l50.pt"
            jlens = (
                cache_root
                / "jlens"
                / "Llama-3.3-70B-Instruct_jacobian_lens.pt"
            )
            model.mkdir(parents=True)
            sae.parent.mkdir(parents=True)
            jlens.parent.mkdir(parents=True)
            sae.write_bytes(b"fixture")
            jlens.write_bytes(b"fixture")
            rehash = {
                "cache_root": str(cache_root),
                "full_file_count": gate.LEGACY_PUBLIC_ARTIFACT_FILE_COUNT,
                "full_retained_bytes": gate.LEGACY_PUBLIC_ARTIFACT_BYTES,
                "full_file_inventory_sha256": (
                    gate.LEGACY_PUBLIC_ARTIFACT_INVENTORY_SHA256
                ),
                "components": [
                    {
                        "component": "model",
                        "revision": protocol.MODEL_SPEC["revision"],
                        "relative_path": "model_snapshot",
                        "byte_count": 1,
                        "sha256": gate.LEGACY_MODEL_FILE_INVENTORY_SHA256,
                        "verified": True,
                    },
                    {
                        "component": "sae",
                        "revision": protocol.SAE_SPEC["revision"],
                        "relative_path": "sae/Llama-3.3-70B-Instruct-SAE-l50.pt",
                        "byte_count": 1,
                        "sha256": protocol.SAE_SPEC["sha256"],
                        "verified": True,
                    },
                    {
                        "component": "j_lens",
                        "revision": protocol.J_LENS_SPEC["revision"],
                        "relative_path": "jlens/Llama-3.3-70B-Instruct_jacobian_lens.pt",
                        "byte_count": 1,
                        "sha256": protocol.J_LENS_SPEC["sha256"],
                        "verified": True,
                    },
                ],
            }
            with (
                mock.patch.object(
                    gate, "LEGACY_PUBLIC_ARTIFACT_ROOT", str(cache_root)
                ),
                mock.patch.object(
                    gate,
                    "rehash_legacy_public_artifact_cache",
                    return_value=rehash,
                ),
            ):
                cache = gate.build_cache_receipt(
                    guest_receipt=guest,
                    ownership_receipt=ownership,
                )
                receipt_paths = {}
                for name, value in (
                    ("ownership", ownership),
                    ("guest", guest),
                    ("cache", cache),
                ):
                    path = root / f"{name}.json"
                    path.write_text(
                        gate.canonical_json_bytes(value).decode() + "\n",
                        encoding="utf-8",
                    )
                    receipt_paths[name] = path
                with mock.patch.dict(
                    os.environ, {"RUNPOD_POD_ID": ownership["pod_id"]}
                ):
                    observed = runner._validate_guest_chain(
                        ownership_receipt_path=receipt_paths["ownership"],
                        guest_receipt_path=receipt_paths["guest"],
                        cache_receipt_path=receipt_paths["cache"],
                        volume_id=gate.EXPECTED_VOLUME_ID,
                        model_snapshot=model,
                        sae_path=sae,
                        j_lens_path=jlens,
                        campaign_started_at_unix=self.created.timestamp(),
                        provider_terminate_at_unix=(
                            self.created + timedelta(hours=6)
                        ).timestamp(),
                    )
            self.assertEqual(observed[0]["pod_id"], ownership["pod_id"])


if __name__ == "__main__":
    unittest.main()
