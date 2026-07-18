from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_realization_validation import guest_launcher
from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import runner
from experiments.consciousness_sae_realization_validation import runpod_preflight
from experiments.consciousness_sae_realization_validation import runtime


def _ownership_receipt() -> dict[str, object]:
    nonce = "a" * 32
    upstream_hash = "b" * 64
    core = {
        "schema_version": runpod_preflight.SCHEMA_VERSION,
        "status": "owned_running_isolated",
        "study_id": protocol.STUDY_ID,
        "protocol_version": protocol.PROTOCOL_VERSION,
        "pod_id": "abc123def456",
        "pod_name": runpod_preflight.POD_NAME_PREFIX + nonce,
        "ownership_nonce": nonce,
        "network_volume_id": runpod_preflight.EXPECTED_VOLUME_ID,
        "provider_volume_size_bytes": (
            runpod_preflight.EXPECTED_PROVIDER_VOLUME_BYTES
        ),
        "data_center_id": runpod_preflight.EXPECTED_DATA_CENTER_ID,
        "gpu_type": runpod_preflight.EXPECTED_GPU_TYPE,
        "gpu_count": 1,
        "volume_mount_path": runpod_preflight.VOLUME_MOUNT_PATH,
        "created_at": "2026-07-14T12:00:00Z",
        "terminate_after": "2026-07-14T18:00:00Z",
        "create_contract_sha256": "c" * 64,
        "upstream_lifecycle_receipt_sha256": upstream_hash,
        "provider_container_image_attestation": {
            "source": "validated_graphql_create_plus_final_rest_readback_v1",
            "immutable_reference": protocol.CONTAINER_IMAGE_SPEC[
                "immutable_reference"
            ],
            "graphql_create_snapshot_source": (
                "graphql_create_plus_rest_volume_proof"
            ),
            "create_request_sha256": "d" * 64,
            "final_rest_proof_source": (
                "rest_v1_pod_get_final_after_graphql_locked_state"
            ),
            "rest_image_fields": ["imageName"],
            "upstream_lifecycle_receipt_sha256": upstream_hash,
        },
        "desired_status": "RUNNING",
        "locked": False,
        "precreate_unrelated_pod_count": 0,
        "precreate_unrelated_inventory_sha256": protocol.canonical_sha256([]),
    }
    return runpod_preflight.with_self_hash(core)


class _ExecIntercept(RuntimeError):
    pass


class GuestLauncherTests(unittest.TestCase):
    def test_environment_is_derived_from_validated_provider_attestation(self) -> None:
        ownership = _ownership_receipt()
        observed = guest_launcher._set_attested_environment(
            ownership_receipt=ownership,
            environ={},
        )
        self.assertEqual(
            observed[protocol.CONTAINER_IMAGE_ENV],
            ownership["provider_container_image_attestation"][
                "immutable_reference"
            ],
        )
        self.assertEqual(
            observed[protocol.CUBLAS_WORKSPACE_CONFIG_ENV],
            protocol.CUBLAS_WORKSPACE_CONFIG_VALUE,
        )
        self.assertEqual(
            observed[protocol.GUEST_LAUNCH_OWNERSHIP_ENV],
            ownership["receipt_sha256"],
        )

    def test_smoke_and_both_stages_share_one_fail_closed_exec_path(self) -> None:
        ownership = _ownership_receipt()
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "OWNERSHIP.json"
            receipt_path.write_text(
                json.dumps(ownership, sort_keys=True) + "\n", encoding="utf-8"
            )
            for command, expected_module, expected_prefix in (
                (
                    "smoke",
                    "experiments.consciousness_sae_realization_validation.smoke_test",
                    (),
                ),
                (
                    "stage-a",
                    "experiments.consciousness_sae_realization_validation.runner",
                    ("stage-a",),
                ),
                (
                    "stage-b",
                    "experiments.consciousness_sae_realization_validation.runner",
                    ("stage-b",),
                ),
            ):
                captured: dict[str, object] = {}

                def intercept(path, argv, environment):
                    captured.update(path=path, argv=tuple(argv), env=dict(environment))
                    raise _ExecIntercept

                with self.subTest(command=command), self.assertRaises(_ExecIntercept):
                    guest_launcher.launch(
                        command=command,
                        ownership_receipt_path=receipt_path,
                        forwarded_args=("--", "--plan-dir", "/frozen/plan"),
                        environ={},
                        loaded_module_names=(),
                        executable="/usr/bin/python3",
                        execve=intercept,
                    )
                argv = captured["argv"]
                self.assertEqual(argv[:5], (
                    "/usr/bin/python3", "-B", "-u", "-m", expected_module
                ))
                self.assertEqual(argv[5 : 5 + len(expected_prefix)], expected_prefix)
                self.assertIn("--ownership-receipt", argv)
                self.assertEqual(
                    captured["env"][protocol.CUBLAS_WORKSPACE_CONFIG_ENV],
                    protocol.CUBLAS_WORKSPACE_CONFIG_VALUE,
                )

    def test_conflicting_environment_tampering_and_early_import_fail_closed(self) -> None:
        ownership = _ownership_receipt()
        for name, value in (
            (protocol.CONTAINER_IMAGE_ENV, "wrong-image"),
            (protocol.CUBLAS_WORKSPACE_CONFIG_ENV, ":16:8"),
            (protocol.GUEST_LAUNCH_OWNERSHIP_ENV, "0" * 64),
        ):
            with self.subTest(name=name), self.assertRaises(
                guest_launcher.GuestLaunchError
            ):
                guest_launcher._set_attested_environment(
                    ownership_receipt=ownership, environ={name: value}
                )

        tampered = dict(ownership)
        tampered_attestation = dict(
            tampered["provider_container_image_attestation"]
        )
        tampered_attestation["immutable_reference"] = "attacker/image@sha256:" + (
            "0" * 64
        )
        tampered["provider_container_image_attestation"] = tampered_attestation
        tampered.pop("receipt_sha256")
        tampered = runpod_preflight.with_self_hash(tampered)
        with self.assertRaises(guest_launcher.GuestLaunchError):
            guest_launcher._set_attested_environment(
                ownership_receipt=tampered, environ={}
            )
        with self.assertRaises(guest_launcher.GuestLaunchError):
            guest_launcher._require_pre_model_process(("torch",))
        with self.assertRaises(guest_launcher.GuestLaunchError):
            guest_launcher._forwarded_arguments(
                ("--ownership-receipt", "/different/receipt")
            )

    def test_runtime_rejects_missing_launcher_binding_before_tokenizer_or_torch(self) -> None:
        ownership_hash = _ownership_receipt()["receipt_sha256"]
        with mock.patch.dict(
            os.environ,
            {
                protocol.CONTAINER_IMAGE_ENV: protocol.CONTAINER_IMAGE_SPEC[
                    "immutable_reference"
                ],
                protocol.CUBLAS_WORKSPACE_CONFIG_ENV: (
                    protocol.CUBLAS_WORKSPACE_CONFIG_VALUE
                ),
            },
            clear=True,
        ), mock.patch.object(runtime, "verify_public_artifacts") as verify:
            with self.assertRaises(runtime.V2RuntimeError) as raised:
                runner._load_backend(
                    model_snapshot=Path("/never-read"),
                    sae_path=Path("/never-read"),
                    j_lens_path=Path("/never-read"),
                    ownership_receipt_sha256=ownership_hash,
                )
        self.assertEqual(raised.exception.code, "guest_launch_ownership")
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
