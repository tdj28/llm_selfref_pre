from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from experiments.consciousness_sae_realization_validation import protocol
from experiments.consciousness_sae_realization_validation import (
    runpod_lifecycle_adapter as adapter,
)
from experiments.consciousness_sae_realization_validation import (
    runpod_orchestrator as orchestrator,
)
from experiments.consciousness_sae_realization_validation import (
    runpod_preflight as preflight,
)
from tests.consciousness_readout_validation.test_runpod_lifecycle import (
    API_KEY,
    FakeGraphQLApi,
    FakeRestApi,
    _graphql_pod,
    _graphql_read_response,
    _graphql_response,
    _pod,
)


CREATED = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)
NONCE = "a" * 32
POD_NAME = preflight.POD_NAME_PREFIX + "20260714-" + NONCE
UNRELATED = {
    "id": "h200pod1",
    "name": "unrelated-8xh200",
    "desiredStatus": "RUNNING",
    "gpuCount": 8,
    "machine": {"gpuTypeId": "NVIDIA H200"},
}


def provider_fixture() -> tuple[FakeRestApi, FakeGraphQLApi]:
    provider_pod = _pod(
        name=POD_NAME,
        imageName=protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        containerDiskInGb=adapter.CONTAINER_DISK_GB,
    )
    graphql_pod = _graphql_pod(
        name=POD_NAME,
        imageName=protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        containerDiskInGb=adapter.CONTAINER_DISK_GB,
    )
    rest = FakeRestApi(
        pod=provider_pod,
        additional_pods=[dict(UNRELATED)],
        volume={
            "id": preflight.EXPECTED_VOLUME_ID,
            "name": "lens-campaign",
            "size": 500,
            "dataCenterId": preflight.EXPECTED_DATA_CENTER_ID,
        },
    )
    graphql = FakeGraphQLApi(
        response=_graphql_response(graphql_pod),
        read_responses=[_graphql_read_response(name=POD_NAME)],
    )
    return rest, graphql


class RunPodOrchestratorTests(unittest.TestCase):
    def _create(
        self, root: Path, *, rest: FakeRestApi, graphql: FakeGraphQLApi
    ) -> Path:
        with mock.patch.dict(
            "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
        ):
            return orchestrator.create_successor(
                receipt_dir=root / "receipts",
                execute=True,
                rest_api=rest,
                graphql_api=graphql,
                now=lambda: CREATED,
                nonce_factory=lambda: NONCE,
                sleeper=lambda _seconds: None,
                readiness_attempts=1,
            )

    def test_network_free_dry_run_calls_frozen_create_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = adapter.frozen.create_lifecycle
            with mock.patch.object(
                adapter.frozen, "create_lifecycle", wraps=original
            ) as create:
                output = orchestrator.create_successor(
                    receipt_dir=root / "receipts",
                    execute=False,
                    now=lambda: CREATED,
                    nonce_factory=lambda: NONCE,
                    sleeper=lambda _seconds: None,
                )
            self.assertEqual(create.call_count, 1)
            self.assertEqual(output.name, "ORCHESTRATION_DRY_RUN.json")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "dry_run_no_api_call")
            self.assertTrue(
                (
                    root
                    / "receipts"
                    / "frozen_lifecycle"
                    / "CREATE_DRY_RUN.json"
                ).is_file()
            )

    def test_execute_captures_full_inventory_bridges_and_polls_exact_pod(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = adapter.frozen.create_lifecycle
            with mock.patch.object(
                adapter.frozen, "create_lifecycle", wraps=original
            ) as create:
                ownership_path = self._create(root, rest=rest, graphql=graphql)
            self.assertEqual(create.call_count, 1)
            receipt_dir = ownership_path.parent
            ownership = json.loads(ownership_path.read_text(encoding="utf-8"))
            self.assertEqual(ownership["pod_id"], "abc123xyz")
            self.assertEqual(ownership["pod_name"], POD_NAME)
            self.assertEqual(ownership["network_volume_id"], "qf2lwehl89")
            self.assertEqual(ownership["data_center_id"], "US-NE-1")
            self.assertEqual(ownership["gpu_type"], "NVIDIA B200")
            self.assertTrue((receipt_dir / "READY.json").is_file())
            pre = json.loads(
                (receipt_dir / "PRECREATE_INVENTORY.json").read_text(encoding="utf-8")
            )
            post = json.loads(
                (receipt_dir / "POSTCREATE_INVENTORY.json").read_text(encoding="utf-8")
            )
            self.assertEqual(pre["all_account_pod_count"], 1)
            self.assertEqual(post["all_account_pod_count"], 2)
            self.assertEqual(pre["pods"][0]["pod_id"], UNRELATED["id"])
            self.assertFalse(
                any(
                    API_KEY in path.read_text(encoding="utf-8")
                    for path in receipt_dir.rglob("*.json")
                )
            )
            contract = json.loads(
                (receipt_dir / "CREATE_CONTRACT.json").read_text(encoding="utf-8")
            )
            upstream = json.loads(
                (
                    receipt_dir
                    / "frozen_lifecycle"
                    / "OWNERSHIP.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(contract["created_at"], upstream["created_at_utc"])
            self.assertEqual(contract["terminate_after"], upstream["hard_deadline_utc"])
            self.assertEqual(contract["max_total_spend_usd"], 36.0)
            self.assertEqual(contract["max_total_seconds"], 6 * 60 * 60)
            self.assertEqual(upstream["pod"]["container_disk_gb"], 20)
            create_inputs = [
                payload["variables"]["input"]
                for payload in graphql.calls
                if "mutation createPod" in str(payload.get("query"))
            ]
            self.assertEqual(len(create_inputs), 1)
            self.assertEqual(create_inputs[0]["containerDiskInGb"], 20)

    def test_wrong_status_id_is_rejected_before_provider_read(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ownership_path = self._create(root, rest=rest, graphql=graphql)
            calls_before = len(rest.calls)
            with (
                mock.patch.dict(
                    "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
                ),
                self.assertRaises(orchestrator.OrchestrationError),
            ):
                orchestrator.status_successor(
                    receipt_dir=ownership_path.parent,
                    pod_id=UNRELATED["id"],
                    rest_api=rest,
                    now=lambda: CREATED,
                )
            self.assertEqual(len(rest.calls), calls_before)

    def test_exact_termination_preserves_unrelated_inventory(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ownership_path = self._create(root, rest=rest, graphql=graphql)
            with mock.patch.dict(
                "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
            ):
                output = orchestrator.terminate_successor(
                    receipt_dir=ownership_path.parent,
                    pod_id="abc123xyz",
                    execute=True,
                    rest_api=rest,
                    now=lambda: CREATED,
                    sleeper=lambda _seconds: None,
                )
            self.assertTrue(rest.deleted)
            self.assertEqual(output.name, "TERMINATION_AUDIT.json")
            audit = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                audit["status"],
                "deleted_exact_owned_pod_unrelated_inventory_unchanged",
            )
            delete_calls = [
                path for method, path, _ in rest.calls if method == "DELETE"
            ]
            self.assertEqual(delete_calls, ["/pods/abc123xyz"])
            post = json.loads(
                (ownership_path.parent / "POSTDELETE_INVENTORY.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual([row["pod_id"] for row in post["pods"]], ["h200pod1"])

    def test_wrong_termination_id_never_calls_delete(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ownership_path = self._create(root, rest=rest, graphql=graphql)
            calls_before = len(rest.calls)
            with (
                mock.patch.dict(
                    "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
                ),
                self.assertRaises(orchestrator.OrchestrationError),
            ):
                orchestrator.terminate_successor(
                    receipt_dir=ownership_path.parent,
                    pod_id=UNRELATED["id"],
                    execute=True,
                    rest_api=rest,
                    now=lambda: CREATED,
                    sleeper=lambda _seconds: None,
                )
            self.assertEqual(len(rest.calls), calls_before)
            self.assertFalse(rest.deleted)

    def _assert_postcreate_failure_rolled_back(
        self,
        *,
        receipt_dir: Path,
        rest: FakeRestApi,
        graphql: FakeGraphQLApi,
        expected_stage: str,
    ) -> None:
        failure_path = receipt_dir / orchestrator.POSTCREATE_FAILURE_NAME
        self.assertTrue(failure_path.is_file())
        failure = json.loads(failure_path.read_text(encoding="utf-8"))
        self.assertEqual(failure["failure_stage"], expected_stage)
        self.assertEqual(
            failure["status"],
            "postcreate_failure_exact_rollback_verified",
        )
        self.assertTrue(failure["provider_absence_verified"])
        self.assertTrue(failure["unrelated_inventory_unchanged"])
        self.assertFalse(failure["manual_cleanup_required"])
        self.assertFalse(failure["create_retried"])
        self.assertTrue(rest.deleted)
        create_calls = [
            payload
            for payload in graphql.calls
            if "mutation createPod" in str(payload.get("query"))
        ]
        self.assertEqual(len(create_calls), 1)
        delete_calls = [
            path for method, path, _ in rest.calls if method == "DELETE"
        ]
        self.assertEqual(delete_calls, ["/pods/abc123xyz"])
        self.assertNotIn(API_KEY, failure_path.read_text(encoding="utf-8"))
        self.assertTrue(
            (receipt_dir / orchestrator.POSTROLLBACK_INVENTORY_NAME).is_file()
        )

    def test_postcreate_inventory_failure_rolls_back_without_create_retry(self) -> None:
        rest, graphql = provider_fixture()

        class FailThirdInventory:
            def __init__(self, delegate: FakeRestApi) -> None:
                self.delegate = delegate
                self.inventory_calls = 0

            def __call__(self, method: str, path: str, payload: object):
                if method == "GET" and path == orchestrator.ACCOUNT_INVENTORY_PATH:
                    self.inventory_calls += 1
                    if self.inventory_calls == 3:
                        return 503, None
                return self.delegate(method, path, payload)

        injected = FailThirdInventory(rest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.dict(
                    "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
                ),
                self.assertRaises(orchestrator.OrchestrationError),
            ):
                orchestrator.create_successor(
                    receipt_dir=root / "receipts",
                    execute=True,
                    rest_api=injected,
                    graphql_api=graphql,
                    now=lambda: CREATED,
                    nonce_factory=lambda: NONCE,
                    sleeper=lambda _seconds: None,
                    readiness_attempts=1,
                )
            self._assert_postcreate_failure_rolled_back(
                receipt_dir=root / "receipts",
                rest=rest,
                graphql=graphql,
                expected_stage="capture_postcreate_inventory",
            )

    def test_ownership_bridge_failure_rolls_back_without_create_retry(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.dict(
                    "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
                ),
                mock.patch.object(
                    adapter,
                    "publish_successor_ownership",
                    side_effect=preflight.PreflightError("injected bridge failure"),
                ),
                self.assertRaises(orchestrator.OrchestrationError),
            ):
                orchestrator.create_successor(
                    receipt_dir=root / "receipts",
                    execute=True,
                    rest_api=rest,
                    graphql_api=graphql,
                    now=lambda: CREATED,
                    nonce_factory=lambda: NONCE,
                    sleeper=lambda _seconds: None,
                    readiness_attempts=1,
                )
            self._assert_postcreate_failure_rolled_back(
                receipt_dir=root / "receipts",
                rest=rest,
                graphql=graphql,
                expected_stage="bridge_successor_ownership",
            )

    def test_readiness_failure_rolls_back_without_create_retry(self) -> None:
        rest, graphql = provider_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                mock.patch.dict(
                    "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
                ),
                mock.patch.object(
                    orchestrator,
                    "_poll_readiness",
                    side_effect=orchestrator.OrchestrationError(
                        "injected readiness timeout"
                    ),
                ),
                self.assertRaises(orchestrator.OrchestrationError),
            ):
                orchestrator.create_successor(
                    receipt_dir=root / "receipts",
                    execute=True,
                    rest_api=rest,
                    graphql_api=graphql,
                    now=lambda: CREATED,
                    nonce_factory=lambda: NONCE,
                    sleeper=lambda _seconds: None,
                    readiness_attempts=1,
                )
            self._assert_postcreate_failure_rolled_back(
                receipt_dir=root / "receipts",
                rest=rest,
                graphql=graphql,
                expected_stage="poll_exact_owned_readiness",
            )

    def test_cli_has_no_api_key_argument_or_secret_output_path(self) -> None:
        with mock.patch.dict(
            "os.environ", {orchestrator.API_KEY_ENV: API_KEY}, clear=False
        ):
            with self.assertRaises(orchestrator.OrchestrationError):
                orchestrator.main(
                    [
                        "create",
                        "--receipt-dir",
                        "/tmp/not-created",
                        "--api-key",
                        API_KEY,
                    ]
                )

    def test_receipts_inside_repository_are_rejected(self) -> None:
        forbidden = Path(__file__).resolve().parents[2] / "orchestrator-receipts"
        self.assertFalse(forbidden.exists())
        with self.assertRaises(orchestrator.OrchestrationError):
            orchestrator.create_successor(
                receipt_dir=forbidden,
                execute=False,
                now=lambda: CREATED,
                nonce_factory=lambda: NONCE,
            )
        self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
