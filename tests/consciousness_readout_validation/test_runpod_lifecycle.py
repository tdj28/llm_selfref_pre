from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from experiments.consciousness_readout_validation import protocol, runpod_lifecycle
from experiments.consciousness_readout_validation.runpod_lifecycle import (
    GRAPHQL_CREATE_QUERY,
    GRAPHQL_POD_READ_QUERY,
    LifecycleError,
    RunPodGraphQLClient,
    RunPodRestClient,
    create_lifecycle,
    reject_secret_argv,
    status_lifecycle,
    terminate_lifecycle,
)


POD_NAME = (
    "consciousness-readout-validation-v1-20260713-"
    "0123456789abcdef0123456789abcdef"
)
VOLUME_ID = "qf2lwehl89"
DATA_CENTER = "US-NE-1"
API_KEY = "unit-secret-runpod-credential-123456"
NOW = datetime(2026, 7, 13, 22, 0, tzinfo=timezone.utc)


def _pod(**updates):
    value = {
        "id": "abc123xyz",
        "name": POD_NAME,
        "desiredStatus": "RUNNING",
        "imageName": protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        "interruptible": False,
        "locked": False,
        "podType": "RESERVED",
        "containerDiskInGb": 50,
        "volumeInGb": 0,
        "volumeMountPath": "/workspace",
        "gpuCount": 1,
        "memoryInGb": 180,
        "vcpuCount": 16,
        "networkVolumeId": VOLUME_ID,
        "gpu": {"displayName": "B200", "count": 1},
        "machine": {
            "id": "machineabc123",
            "dataCenterId": DATA_CENTER,
            "secureCloud": True,
            "gpuTypeId": "NVIDIA B200",
            "gpuDisplayName": "B200",
            "location": "Nebraska, USA",
            "podHostId": "hostabc123",
        },
        "networkVolume": {"id": VOLUME_ID, "dataCenterId": DATA_CENTER},
        "ports": ["22/tcp"],
        "costPerHr": "5.98",
        "lastStatusChange": "2026-07-13T22:00:00.000Z",
        "lastStartedAt": "2026-07-13T22:00:00.000Z",
    }
    value.update(updates)
    return value


def _graphql_pod(**updates):
    value = {
        "id": "abc123xyz",
        "name": POD_NAME,
        "imageName": protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
        "desiredStatus": "RUNNING",
        "costPerHr": "5.98",
        "containerDiskInGb": 50,
        "volumeInGb": 0,
        "volumeMountPath": "/workspace",
        "gpuCount": 1,
        "memoryInGb": 180,
        "vcpuCount": 16,
        "ports": "22/tcp",
        "lastStatusChange": "2026-07-13T22:00:00.000Z",
        "lastStartedAt": "2026-07-13T22:00:00.000Z",
        "machineId": "machineabc123",
        "networkVolumeId": VOLUME_ID,
        "locked": False,
        "podType": "RESERVED",
        "machine": {
            "id": "machineabc123",
            "dataCenterId": DATA_CENTER,
            "secureCloud": True,
            "gpuTypeId": "NVIDIA B200",
            "gpuDisplayName": "B200",
            "location": "Nebraska, USA",
            "podHostId": "hostabc123",
        },
        "runtime": {
            "ports": [
                {
                    "ip": "192.0.2.10",
                    "isIpPublic": True,
                    "privatePort": 22,
                    "publicPort": 32022,
                    "type": "tcp",
                }
            ]
        },
    }
    value.update(updates)
    return value


def _graphql_response(pod=None):
    return {"data": {"podFindAndDeployOnDemand": pod or _graphql_pod()}}


def _graphql_read_response(**updates):
    pod = {
        "id": "abc123xyz",
        "name": POD_NAME,
        "locked": False,
        "podType": "RESERVED",
        "desiredStatus": "RUNNING",
    }
    pod.update(updates)
    return {"data": {"pod": pod}}


class FakeRestApi:
    def __init__(
        self,
        pod=None,
        *,
        initial_not_found=0,
        exists=False,
        additional_pods=None,
        inventory_visibility_lag=0,
        deletion_inventory_lag=0,
        incomplete_metadata_gets=0,
        readiness_lag=0,
        volume=None,
        volume_status=200,
        events=None,
    ):
        self.pod = _pod() if pod is None else pod
        self.calls = []
        self.deleted = False
        self.exists = exists
        self.additional_pods = list(additional_pods or [])
        self.initial_not_found = initial_not_found
        self.inventory_visibility_lag = inventory_visibility_lag
        self.deletion_inventory_lag = deletion_inventory_lag
        self.incomplete_metadata_gets = incomplete_metadata_gets
        self.readiness_lag = readiness_lag
        self.volume = volume or {
            "id": VOLUME_ID,
            "name": "lens-campaign",
            "size": 900,
            "dataCenterId": DATA_CENTER,
        }
        self.volume_status = volume_status
        self.events = events

    def __call__(self, method, path, payload):
        self.calls.append((method, path, payload))
        if self.events is not None:
            self.events.append(("rest", method, path))
        if method == "GET" and path == f"/networkvolumes/{VOLUME_ID}":
            return self.volume_status, self.volume
        pod_id = str(self.pod["id"])
        if method == "DELETE" and path == f"/pods/{pod_id}":
            self.deleted = True
            return 204, None
        if method == "GET" and path.startswith(f"/pods/{pod_id}"):
            if self.deleted:
                return 404, None
            if self.initial_not_found:
                self.initial_not_found -= 1
                return 404, None
            self.exists = True
            if self.incomplete_metadata_gets:
                self.incomplete_metadata_gets -= 1
                incomplete = dict(self.pod)
                incomplete["gpu"] = None
                incomplete["costPerHr"] = None
                return 200, incomplete
            if self.readiness_lag:
                self.readiness_lag -= 1
                not_ready = dict(self.pod)
                not_ready["desiredStatus"] = "CREATED"
                return 200, not_ready
            return 200, self.pod
        if method == "GET" and path.startswith("/pods?"):
            if self.deleted and self.deletion_inventory_lag:
                self.deletion_inventory_lag -= 1
                return 200, [self.pod] + self.additional_pods
            if self.exists and self.inventory_visibility_lag:
                self.inventory_visibility_lag -= 1
                return 200, []
            rows = [] if self.deleted or not self.exists else [self.pod]
            return 200, rows + self.additional_pods
        raise AssertionError((method, path, payload))


class FakeGraphQLApi:
    def __init__(
        self,
        *,
        status=200,
        response=None,
        error=None,
        on_call=None,
        read_status=200,
        read_responses=None,
        read_error=None,
        read_on_call=None,
        events=None,
    ):
        self.status = status
        self.response = (
            _graphql_response()
            if response is None
            else response
        )
        self.error = error
        self.on_call = on_call
        self.read_status = read_status
        self.read_responses = list(read_responses or [_graphql_read_response()])
        self.read_error = read_error
        self.read_on_call = read_on_call
        self.events = events
        self.read_calls = 0
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        if payload.get("query") == GRAPHQL_POD_READ_QUERY:
            if self.events is not None:
                self.events.append(("graphql", "pod_read"))
            index = min(self.read_calls, len(self.read_responses) - 1)
            self.read_calls += 1
            if self.read_on_call is not None:
                self.read_on_call()
            if self.read_error is not None:
                raise self.read_error
            return self.read_status, self.read_responses[index]
        if self.events is not None:
            self.events.append(("graphql", "create"))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        return self.status, self.response


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class RunPodLifecycleTests(unittest.TestCase):
    def _create_owned(
        self,
        root: Path,
        rest_api: FakeRestApi | None = None,
        graphql_api: FakeGraphQLApi | None = None,
    ) -> tuple[Path, FakeRestApi, FakeGraphQLApi]:
        selected_rest = rest_api or FakeRestApi()
        selected_graphql = graphql_api or FakeGraphQLApi()
        path = create_lifecycle(
            receipt_dir=root / "lifecycle",
            pod_name=POD_NAME,
            volume_id=VOLUME_ID,
            data_center_id=DATA_CENTER,
            max_usd_text="6.00",
            max_hours_text="1.0",
            execute=True,
            graphql_api=selected_graphql,
            rest_api=selected_rest,
            api_key=API_KEY,
            now=lambda: NOW,
            sleeper=lambda _seconds: None,
        )
        return path, selected_rest, selected_graphql

    def test_create_defaults_to_no_api_dry_run_and_binds_exact_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = create_lifecycle(
                receipt_dir=Path(temporary) / "dry",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="12.50",
                max_hours_text="2",
                execute=False,
                graphql_api=None,
                rest_api=None,
                api_key=API_KEY,
                now=lambda: NOW,
            )
            receipt = _load(output)
            self.assertEqual("dry_run_no_api_call", receipt["status"])
            self.assertEqual(GRAPHQL_CREATE_QUERY, receipt["request"]["query"])
            graphql_input = receipt["request"]["variables"]["input"]
            self.assertEqual(
                {
                    "cloudType",
                    "containerDiskInGb",
                    "dataCenterId",
                    "gpuCount",
                    "gpuTypeId",
                    "imageName",
                    "name",
                    "networkVolumeId",
                    "ports",
                    "startSsh",
                    "terminateAfter",
                    "volumeMountPath",
                },
                set(graphql_input),
            )
            self.assertEqual("SECURE", graphql_input["cloudType"])
            self.assertEqual("NVIDIA B200", graphql_input["gpuTypeId"])
            self.assertEqual(DATA_CENTER, graphql_input["dataCenterId"])
            self.assertEqual(VOLUME_ID, graphql_input["networkVolumeId"])
            self.assertEqual("22/tcp", graphql_input["ports"])
            self.assertIs(graphql_input["startSsh"], True)
            self.assertEqual(
                "2026-07-14T00:00:00Z", graphql_input["terminateAfter"]
            )
            self.assertEqual(
                protocol.CONTAINER_IMAGE_SPEC["immutable_reference"],
                graphql_input["imageName"],
            )
            for selection in (
                "networkVolumeId",
                "gpuTypeId",
                "gpuDisplayName",
                "dataCenterId",
                "secureCloud",
                "lastStartedAt",
                "podHostId",
                "runtime",
            ):
                self.assertIn(selection, GRAPHQL_CREATE_QUERY)
            self.assertNotIn(API_KEY.encode(), output.read_bytes())
            sealed = dict(receipt)
            digest = sealed.pop("receipt_sha256")
            self.assertEqual(protocol.canonical_sha256(sealed), digest)

    def test_create_writes_ownership_and_never_serializes_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, rest_api, graphql_api = self._create_owned(Path(temporary))
            receipt = _load(ownership)
            self.assertEqual("created", receipt["status"])
            self.assertTrue(receipt["agent_owned"])
            self.assertEqual("abc123xyz", receipt["pod"]["id"])
            self.assertEqual("5.98", receipt["pod"]["cost_per_hour_usd"])
            self.assertEqual(VOLUME_ID, receipt["pod"]["network_volume_id"])
            self.assertEqual(DATA_CENTER, receipt["pod"]["data_center_id"])
            self.assertEqual("NVIDIA B200", receipt["pod"]["gpu_type_id"])
            self.assertEqual("B200", receipt["pod"]["gpu_display_name"])
            self.assertEqual(
                {"interruptible": "observed_false", "locked": "observed_false"},
                receipt["rest_corroboration"]["optional_false_field_status"],
            )
            self.assertEqual(
                "rest_v1_pod_get_final_after_graphql_locked_state",
                receipt["rest_corroboration"]["proof_source"],
            )
            self.assertEqual(
                {
                    "desired_status": "RUNNING",
                    "http_status": 200,
                    "id": "abc123xyz",
                    "locked": False,
                    "name": POD_NAME,
                    "pod_type": "RESERVED",
                    "poll_attempts": 1,
                    "proof_source": "graphql_pod_filter_locked_state",
                    "request_sha256": protocol.canonical_sha256(
                        {
                            "query": GRAPHQL_POD_READ_QUERY,
                            "variables": {"input": {"podId": "abc123xyz"}},
                        }
                    ),
                },
                receipt["graphql_locked_state_proof"],
            )
            self.assertEqual("2026-07-13T22:00:00Z", receipt["created_at_utc"])
            self.assertEqual("2026-07-13T23:00:00Z", receipt["hard_deadline_utc"])
            self.assertEqual(
                receipt["hard_deadline_utc"],
                receipt["provider_terminate_after_utc"],
            )
            create_request = _load(ownership.parent / "CREATE_REQUEST.json")
            self.assertEqual(
                receipt["hard_deadline_utc"],
                create_request["request"]["variables"]["input"]["terminateAfter"],
            )
            self.assertEqual(
                protocol.canonical_sha256(create_request["request"]),
                receipt["request_sha256"],
            )
            self.assertEqual(2, len(graphql_api.calls))
            self.assertFalse(any(call[0] == "POST" for call in rest_api.calls))
            self.assertTrue(
                any(
                    call[0] == "GET" and "includeMachine=true" in call[1]
                    for call in rest_api.calls
                )
            )
            self.assertIn(
                ("GET", f"/networkvolumes/{VOLUME_ID}", None), rest_api.calls
            )
            for candidate in ownership.parent.iterdir():
                self.assertNotIn(API_KEY.encode(), candidate.read_bytes())

    def test_provider_deadline_floors_fractional_start_and_never_exceeds_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            observed = NOW + timedelta(microseconds=999_999)
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "fractional-clock",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=FakeGraphQLApi(),
                rest_api=FakeRestApi(),
                api_key=API_KEY,
                now=lambda: observed,
                sleeper=lambda _seconds: None,
            )
            receipt = _load(ownership)
            self.assertEqual("2026-07-13T22:00:00Z", receipt["created_at_utc"])
            self.assertEqual("2026-07-13T23:00:00Z", receipt["hard_deadline_utc"])
            deadline = datetime.fromisoformat(
                receipt["provider_terminate_after_utc"].replace("Z", "+00:00")
            )
            self.assertLessEqual(deadline, observed + timedelta(hours=1))

    def test_provider_deadline_rejects_subsecond_authorization_before_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt_dir = Path(temporary) / "subsecond-authorization"
            with self.assertRaisesRegex(
                LifecycleError, "not exactly representable.*RFC3339-second precision"
            ):
                create_lifecycle(
                    receipt_dir=receipt_dir,
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="0.000001",
                    execute=False,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertFalse(receipt_dir.exists())

    def test_provider_deadline_rejects_naive_lifecycle_clock_before_side_effects(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt_dir = Path(temporary) / "naive-clock"
            with self.assertRaisesRegex(LifecycleError, "timezone-aware"):
                create_lifecycle(
                    receipt_dir=receipt_dir,
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=False,
                    api_key=API_KEY,
                    now=lambda: NOW.replace(tzinfo=None),
                )
            self.assertFalse(receipt_dir.exists())

    def test_over_budget_create_is_immediately_rolled_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            graphql_api = FakeGraphQLApi()
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "budget",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="5.00",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertTrue(rest_api.deleted)
            self.assertFalse((Path(temporary) / "budget" / "OWNERSHIP.json").exists())

    def test_identity_mismatch_is_immediately_rolled_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            mismatched = _pod(
                networkVolume={"id": "wrongvol1", "dataCenterId": DATA_CENTER}
            )
            rest_api = FakeRestApi(mismatched)
            graphql_api = FakeGraphQLApi()
            sleeps = []
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "identity",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                )
            self.assertTrue(rest_api.deleted)
            self.assertEqual([], sleeps)

    def test_graphql_must_directly_bind_exact_network_volume_and_gpu_type(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            bad_machine = dict(_graphql_pod()["machine"])
            bad_machine["gpuTypeId"] = "NVIDIA H200"
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(
                    _graphql_pod(networkVolumeId="wrongvol1", machine=bad_machine)
                )
            )
            with self.assertRaisesRegex(
                LifecycleError, "GraphQL identity validation failed.*rollback_verified=True"
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "graphql-direct-binding",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertTrue(rest_api.deleted)
            failure_path = (
                Path(temporary)
                / "graphql-direct-binding"
                / "CREATE_FAILURE.json"
            )
            failure = _load(failure_path)
            self.assertIn('gpu_type_id="NVIDIA H200"', failure["sanitized_summary"])
            self.assertIn("network_volume_id=sha256:", failure["sanitized_summary"])
            self.assertNotIn(b"wrongvol1", failure_path.read_bytes())

    def test_graphql_machine_ids_are_hashed_diagnostics_and_record_id_may_be_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            machine = dict(_graphql_pod()["machine"])
            machine["id"] = None
            machine["gpuDisplayName"] = "B200 SXM"
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(
                    _graphql_pod(machineId="differentmachine", machine=machine)
                )
            )
            rest_api = FakeRestApi()
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "machine-id-diagnostics",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=graphql_api,
                rest_api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW,
            )
            pod = _load(ownership)["pod"]
            self.assertEqual(
                protocol.sha256_bytes(b"differentmachine"),
                pod["machine_id_sha256"],
            )
            self.assertIsNone(pod["machine_record_id_sha256"])
            self.assertEqual("B200 SXM", pod["gpu_display_name"])
            self.assertFalse(rest_api.deleted)

    def test_receipts_omit_raw_infrastructure_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            machine = dict(_graphql_pod()["machine"])
            machine["location"] = "Secret Lab 9382"
            machine["podHostId"] = "hostprivate999"
            runtime = {
                "ports": [
                    {
                        "ip": "198.51.100.77",
                        "isIpPublic": True,
                        "privatePort": 22,
                        "publicPort": 45678,
                        "type": "tcp",
                    }
                ]
            }
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(
                    _graphql_pod(
                        machine=machine,
                        runtime=runtime,
                        lastStatusChange="opaque-status-marker",
                        lastStartedAt="opaque-start-marker",
                    )
                )
            )
            rest_api = FakeRestApi(
                volume={
                    "id": VOLUME_ID,
                    "name": "private-volume-name",
                    "size": 900,
                    "dataCenterId": DATA_CENTER,
                }
            )
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "private-diagnostics",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=graphql_api,
                rest_api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW,
            )
            receipt = _load(ownership)
            self.assertEqual(
                {"row_count": 1, "public_ssh_endpoint_present": True},
                receipt["pod"]["runtime_port_summary"],
            )
            raw_receipts = b"".join(
                path.read_bytes() for path in ownership.parent.glob("*.json")
            )
            for forbidden in (
                b"Secret Lab 9382",
                b"hostprivate999",
                b"198.51.100.77",
                b'"public_port":45678',
                b"private-volume-name",
                b"opaque-status-marker",
                b"opaque-start-marker",
            ):
                self.assertNotIn(forbidden, raw_receipts)

    def test_graphql_created_state_waits_for_rest_running_before_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(readiness_lag=2)
            sleeps = []
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "created-to-running",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=FakeGraphQLApi(
                    response=_graphql_response(
                        _graphql_pod(desiredStatus="CREATED", locked=None)
                    )
                ),
                rest_api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW,
                sleeper=sleeps.append,
                rest_fetch_attempts=3,
            )
            receipt = _load(ownership)
            self.assertEqual("CREATED", receipt["pod"]["desired_status"])
            self.assertEqual(
                "RUNNING", receipt["rest_corroboration"]["desired_status"]
            )
            self.assertEqual([1.0, 1.0], sleeps)

    def test_rest_must_reach_running_or_creation_rolls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(readiness_lag=99)
            with self.assertRaisesRegex(
                LifecycleError, "not reached RUNNING readiness.*rollback_verified=True"
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "never-running",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=FakeGraphQLApi(
                        response=_graphql_response(
                            _graphql_pod(desiredStatus="CREATED")
                        )
                    ),
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=lambda _seconds: None,
                    rest_fetch_attempts=3,
                )
            self.assertTrue(rest_api.deleted)

    def test_graphql_locked_state_null_is_bounded_polled_after_rest_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            graphql_api = FakeGraphQLApi(
                read_responses=[
                    _graphql_read_response(locked=None),
                    _graphql_read_response(locked=None),
                    _graphql_read_response(locked=False),
                ]
            )
            sleeps = []
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "locked-read-poll",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=graphql_api,
                rest_api=FakeRestApi(),
                api_key=API_KEY,
                now=lambda: NOW,
                sleeper=sleeps.append,
                rest_fetch_attempts=3,
            )
            proof = _load(ownership)["graphql_locked_state_proof"]
            self.assertEqual(3, proof["poll_attempts"])
            self.assertEqual(3, graphql_api.read_calls)
            self.assertEqual([1.0, 1.0], sleeps)

    def test_graphql_plausible_transients_are_bounded_polled(self):
        cases = {
            "absent": {"data": {"pod": None}},
            "locked-null": _graphql_read_response(locked=None),
            "type-null": _graphql_read_response(podType=None),
            "state-null": _graphql_read_response(desiredStatus=None),
            "created": _graphql_read_response(desiredStatus="CREATED"),
        }
        for label, transient_response in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                graphql_api = FakeGraphQLApi(
                    read_responses=[transient_response, _graphql_read_response()]
                )
                sleeps = []
                ownership = create_lifecycle(
                    receipt_dir=Path(temporary) / label,
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=FakeRestApi(),
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                    rest_fetch_attempts=3,
                )
                self.assertEqual(
                    2, _load(ownership)["graphql_locked_state_proof"]["poll_attempts"]
                )
                self.assertEqual(2, graphql_api.read_calls)
                self.assertEqual([1.0], sleeps)

    def test_graphql_transient_exhaustion_rolls_back(self):
        cases = {
            "absent": {"data": {"pod": None}},
            "locked-null": _graphql_read_response(locked=None),
            "type-null": _graphql_read_response(podType=None),
            "state-null": _graphql_read_response(desiredStatus=None),
            "created": _graphql_read_response(desiredStatus="CREATED"),
        }
        for label, transient_response in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                graphql_api = FakeGraphQLApi(read_responses=[transient_response])
                rest_api = FakeRestApi()
                with self.assertRaisesRegex(
                    LifecycleError, "remained transient.*rollback_verified=True"
                ):
                    create_lifecycle(
                        receipt_dir=Path(temporary) / label,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=graphql_api,
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                        sleeper=lambda _seconds: None,
                        rest_fetch_attempts=3,
                    )
                failure = _load(Path(temporary) / label / "CREATE_FAILURE.json")
                self.assertEqual(
                    "graphql_locked_state_readback", failure["failure_stage"]
                )
                self.assertEqual(3, graphql_api.read_calls)
                self.assertTrue(rest_api.deleted)

    def test_graphql_locked_state_contradictions_or_malformed_reads_never_retry(self):
        cases = {
            "locked-true": _graphql_read_response(locked=True),
            "locked-zero": _graphql_read_response(locked=0),
            "locked-string": _graphql_read_response(locked="false"),
            "wrong-type": _graphql_read_response(podType="INTERRUPTABLE"),
            "terminal-state": _graphql_read_response(desiredStatus="EXITED"),
            "wrong-id": _graphql_read_response(id="wrong123"),
            "wrong-name": _graphql_read_response(name=f"wrong-{API_KEY}"),
            "malformed": {"data": {"pod": {"id": "abc123xyz"}}},
        }
        for label, read_response in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                graphql_api = FakeGraphQLApi(read_responses=[read_response])
                rest_api = FakeRestApi()
                with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                    create_lifecycle(
                        receipt_dir=Path(temporary) / label,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=graphql_api,
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                    )
                failure_path = Path(temporary) / label / "CREATE_FAILURE.json"
                self.assertEqual(
                    "graphql_locked_state_readback",
                    _load(failure_path)["failure_stage"],
                )
                self.assertEqual(1, graphql_api.read_calls)
                self.assertNotIn(API_KEY.encode(), failure_path.read_bytes())
                self.assertTrue(rest_api.deleted)

    def test_graphql_locked_state_transport_failure_rolls_back_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            graphql_api = FakeGraphQLApi(
                read_error=TimeoutError(f"provider detail {API_KEY}")
            )
            rest_api = FakeRestApi()
            with self.assertRaisesRegex(
                LifecycleError, "pod-read transport failed.*rollback_verified=True"
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "locked-read-transport",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            failure_path = (
                Path(temporary)
                / "locked-read-transport"
                / "CREATE_FAILURE.json"
            )
            self.assertEqual(1, graphql_api.read_calls)
            self.assertNotIn(API_KEY.encode(), failure_path.read_bytes())
            self.assertTrue(rest_api.deleted)

    def test_final_rest_confirmation_is_adjacent_to_graphql_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            events = []
            rest_api = FakeRestApi(events=events)
            graphql_api = FakeGraphQLApi(events=events)
            ownership, _, _ = self._create_owned(
                Path(temporary), rest_api=rest_api, graphql_api=graphql_api
            )
            expanded_read = (
                "rest",
                "GET",
                "/pods/abc123xyz?includeMachine=true&includeNetworkVolume=true",
            )
            self.assertEqual(
                [expanded_read, ("graphql", "pod_read"), expanded_read],
                events[-3:],
            )
            self.assertEqual(
                "rest_v1_pod_get_final_after_graphql_locked_state",
                _load(ownership)["rest_corroboration"]["proof_source"],
            )

    def test_final_rest_race_mismatch_rolls_back_without_sealing_ownership(self):
        cases = {
            "config": ("gpuCount", 2),
            "state": ("desiredStatus", "CREATED"),
            "cost": ("costPerHr", "5.99"),
            "locked": ("locked", True),
        }
        for label, (field, value) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                rest_api = FakeRestApi()

                def mutate_final_read(
                    selected_field=field, selected_value=value
                ):
                    rest_api.pod[selected_field] = selected_value

                graphql_api = FakeGraphQLApi(read_on_call=mutate_final_read)
                receipt_dir = Path(temporary) / label
                with self.assertRaisesRegex(
                    LifecycleError, "rollback_verified=True"
                ):
                    create_lifecycle(
                        receipt_dir=receipt_dir,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=graphql_api,
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                        sleeper=lambda _seconds: None,
                    )
                failure_path = receipt_dir / "CREATE_FAILURE.json"
                failure = _load(failure_path)
                self.assertEqual("final_rest_confirmation", failure["failure_stage"])
                self.assertTrue(failure["rollback_verified"])
                self.assertTrue(rest_api.deleted)
                self.assertFalse((receipt_dir / "OWNERSHIP.json").exists())
                self.assertEqual(1, graphql_api.read_calls)
                expanded_gets = [
                    call
                    for call in rest_api.calls
                    if call[0] == "GET"
                    and call[1].startswith("/pods/abc123xyz?")
                ]
                self.assertEqual(2, len(expanded_gets))
                self.assertNotIn(API_KEY.encode(), failure_path.read_bytes())

    def test_malformed_graphql_desired_status_rolls_back_known_pod(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            receipt_dir = Path(temporary) / "malformed-created-state"
            with self.assertRaisesRegex(
                LifecycleError,
                "GraphQL identity validation failed.*rollback_verified=True",
            ):
                create_lifecycle(
                    receipt_dir=receipt_dir,
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=FakeGraphQLApi(
                        response=_graphql_response(_graphql_pod(desiredStatus=[]))
                    ),
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertTrue(rest_api.deleted)
            failure = _load(receipt_dir / "CREATE_FAILURE.json")
            self.assertEqual("graphql_identity_or_budget", failure["failure_stage"])
            self.assertIn("desired_status=sha256:", failure["sanitized_summary"])
            self.assertTrue(failure["rollback_verified"])

    def test_ownership_sealing_failure_rolls_back_known_pod(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            receipt_dir = Path(temporary) / "ownership-sealing-failure"
            original_sealed = runpod_lifecycle._sealed

            def fail_only_ownership(kind, body, *, api_key):
                if kind == "runpod_pod_ownership_v1":
                    raise LifecycleError("synthetic ownership sealing failure")
                return original_sealed(kind, body, api_key=api_key)

            with mock.patch.object(
                runpod_lifecycle, "_sealed", side_effect=fail_only_ownership
            ):
                with self.assertRaisesRegex(
                    LifecycleError,
                    "ownership receipt publication failed; rollback_verified=True",
                ):
                    create_lifecycle(
                        receipt_dir=receipt_dir,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=FakeGraphQLApi(),
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                    )
            self.assertTrue(rest_api.deleted)
            self.assertFalse((receipt_dir / "OWNERSHIP.json").exists())

    def test_default_registry_image_spelling_is_canonicalized_by_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            canonical = protocol.CONTAINER_IMAGE_SPEC["immutable_reference"]
            provider_spelling = f"docker.io/{canonical}"
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(_graphql_pod(imageName=provider_spelling))
            )
            rest_api = FakeRestApi(_pod(imageName=provider_spelling))
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "default-registry-image",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=graphql_api,
                rest_api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW,
            )
            self.assertEqual(canonical, _load(ownership)["pod"]["image"])

    def test_tag_or_different_image_digest_is_hashed_and_rolled_back(self):
        for suffix, unsafe_value in (
            ("tag", "runpod/pytorch:latest"),
            ("digest", f"runpod/pytorch@sha256:{'0' * 64}"),
        ):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                rest_api = FakeRestApi()
                with self.assertRaisesRegex(
                    LifecycleError,
                    "GraphQL identity validation failed.*rollback_verified=True",
                ):
                    create_lifecycle(
                        receipt_dir=Path(temporary) / suffix,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=FakeGraphQLApi(
                            response=_graphql_response(
                                _graphql_pod(imageName=unsafe_value)
                            )
                        ),
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                    )
                failure_path = Path(temporary) / suffix / "CREATE_FAILURE.json"
                self.assertIn("image=sha256:", _load(failure_path)["sanitized_summary"])
                self.assertNotIn(unsafe_value.encode(), failure_path.read_bytes())
                self.assertTrue(rest_api.deleted)

    def test_mismatch_summary_is_bounded_allowlisted_and_never_echoes_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            unsafe_image = f"private.example/{API_KEY}@sha256:{'1' * 64}"
            rest_api = FakeRestApi()
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "safe-diagnostic",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=FakeGraphQLApi(
                        response=_graphql_response(
                            _graphql_pod(
                                desiredStatus="PAUSED",
                                imageName=unsafe_image,
                                locked=True,
                                networkVolumeId="wrong-private-volume",
                            )
                        )
                    ),
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            failure_path = (
                Path(temporary) / "safe-diagnostic" / "CREATE_FAILURE.json"
            )
            receipt = _load(failure_path)
            self.assertEqual(
                'GraphQL identity mismatch: desired_status="PAUSED"; '
                "image=sha256:"
                + protocol.canonical_sha256(unsafe_image)[:16]
                + "; locked=true; additional_mismatch_count=1",
                receipt["sanitized_summary"],
            )
            raw = failure_path.read_bytes()
            self.assertNotIn(API_KEY.encode(), raw)
            self.assertNotIn(b"wrong-private-volume", raw)
            self.assertLessEqual(len(receipt["sanitized_summary"]), 240)
            self.assertTrue(rest_api.deleted)

    def test_graphql_pod_type_must_be_exact_reserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(
                    _graphql_pod(podType="FUTURE_ON_DEMAND_CLASS")
                )
            )
            rest_api = FakeRestApi(_pod(podType="FUTURE_ON_DEMAND_CLASS"))
            with self.assertRaisesRegex(
                LifecycleError, 'rollback_verified=True.*pod_type="FUTURE_ON_DEMAND_CLASS"'
            ):
                self._create_owned(
                    Path(temporary), rest_api=rest_api, graphql_api=graphql_api
                )
            failure = _load(
                Path(temporary) / "lifecycle" / "CREATE_FAILURE.json"
            )
            self.assertEqual("graphql_identity_or_budget", failure["failure_stage"])
            self.assertTrue(failure["rollback_verified"])
            self.assertTrue(rest_api.deleted)

    def test_rest_interruptible_requires_exact_boolean_false(self):
        for label, interruptible in (
            ("integer-zero", 0),
            ("true", True),
            ("string-false", "false"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                rest_api = FakeRestApi(_pod(interruptible=interruptible))
                with self.assertRaisesRegex(
                    LifecycleError,
                    "REST corroboration is interruptible.*rollback_verified=True",
                ):
                    create_lifecycle(
                        receipt_dir=Path(temporary) / label,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=FakeGraphQLApi(),
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                    )
                self.assertTrue(rest_api.deleted)

    def test_rest_locked_requires_exact_boolean_false(self):
        for label, locked in (
            ("integer-zero", 0),
            ("float-zero", 0.0),
            ("true", True),
            ("string-false", "false"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                rest_api = FakeRestApi(_pod(locked=locked))
                with self.assertRaisesRegex(
                    LifecycleError,
                    "REST corroboration locked state differs.*rollback_verified=True",
                ):
                    create_lifecycle(
                        receipt_dir=Path(temporary) / label,
                        pod_name=POD_NAME,
                        volume_id=VOLUME_ID,
                        data_center_id=DATA_CENTER,
                        max_usd_text="6",
                        max_hours_text="1",
                        execute=True,
                        graphql_api=FakeGraphQLApi(
                            response=_graphql_response(_graphql_pod(locked=None))
                        ),
                        rest_api=rest_api,
                        api_key=API_KEY,
                        now=lambda: NOW,
                    )
                self.assertTrue(rest_api.deleted)

    def test_rest_locked_and_interruptible_may_be_absent_but_are_recorded_truthfully(self):
        with tempfile.TemporaryDirectory() as temporary:
            pod = _pod()
            pod.pop("locked")
            pod.pop("interruptible")
            ownership, rest_api, _ = self._create_owned(
                Path(temporary), rest_api=FakeRestApi(pod)
            )
            corroboration = _load(ownership)["rest_corroboration"]
            self.assertEqual(
                {"interruptible": "absent", "locked": "absent"},
                corroboration["optional_false_field_status"],
            )
            self.assertNotIn("interruptible", corroboration["observed_config_fields"])
            self.assertNotIn("locked", corroboration["observed_config_fields"])
            status_path, exhausted = status_lifecycle(
                ownership_path=ownership,
                api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW + timedelta(minutes=5),
            )
            self.assertFalse(exhausted)
            self.assertEqual(
                {"interruptible": "absent", "locked": "absent"},
                _load(status_path)["pod"]["optional_false_field_status"],
            )

    def test_rest_present_null_optional_fields_are_recorded_truthfully(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, rest_api, _ = self._create_owned(
                Path(temporary),
                rest_api=FakeRestApi(_pod(interruptible=None, locked=None)),
            )
            corroboration = _load(ownership)["rest_corroboration"]
            self.assertEqual(
                {"interruptible": "observed_null", "locked": "observed_null"},
                corroboration["optional_false_field_status"],
            )
            self.assertIn("interruptible", corroboration["observed_config_fields"])
            self.assertIn("locked", corroboration["observed_config_fields"])
            self.assertFalse(rest_api.deleted)

    def test_network_volume_identity_is_proved_before_graphql(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(
                volume={
                    "id": VOLUME_ID,
                    "name": "lens-campaign",
                    "size": 900,
                    "dataCenterId": "US-KS-1",
                }
            )
            graphql_api = FakeGraphQLApi()
            with self.assertRaisesRegex(LifecycleError, "blocked before GraphQL"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "wrong-volume-dc",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertEqual([], graphql_api.calls)
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))

    def test_rest_nested_hydration_may_be_absent_when_top_level_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(_pod(machine=None, networkVolume=None, gpu=None))
            ownership, selected_rest, _ = self._create_owned(
                Path(temporary), rest_api=rest_api
            )
            self.assertTrue(ownership.is_file())
            self.assertFalse(selected_rest.deleted)

    def test_rest_creation_cost_must_match_graphql_cost(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(_pod(costPerHr="5.99"))
            with self.assertRaisesRegex(
                LifecycleError, "hourly cost differs.*rollback_verified=True"
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "cost-disagreement",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=FakeGraphQLApi(),
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertTrue(rest_api.deleted)

    def test_graphql_error_is_sanitized_and_partial_pod_is_rolled_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(deletion_inventory_lag=1)
            sleeps = []
            graphql_api = FakeGraphQLApi(
                response={
                    "data": {
                        "podFindAndDeployOnDemand": {
                            "id": "abc123xyz",
                            "name": POD_NAME,
                        }
                    },
                    "errors": [
                        {"message": f"capacity failed {API_KEY} Bearer abcdefghijklmnop"}
                    ],
                }
            )
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "graphql-error",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                )
            failure = Path(temporary) / "graphql-error" / "CREATE_FAILURE.json"
            raw = failure.read_bytes()
            self.assertNotIn(API_KEY.encode(), raw)
            self.assertNotIn(b"abcdefghijklmnop", raw)
            self.assertEqual("graphql_create", _load(failure)["failure_stage"])
            self.assertTrue(rest_api.deleted)
            self.assertEqual([1.0], sleeps)

    def test_preexisting_exact_name_blocks_before_graphql_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(exists=True)
            graphql_api = FakeGraphQLApi()
            with self.assertRaisesRegex(LifecycleError, "blocked before GraphQL"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "preexisting",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertEqual([], graphql_api.calls)
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))
            failure = _load(
                Path(temporary) / "preexisting" / "CREATE_FAILURE.json"
            )
            self.assertEqual("precreate_name_inventory", failure["failure_stage"])
            self.assertEqual(
                "exact_name_already_present_no_create_attempted",
                failure["name_reconciliation"]["outcome"],
            )
            self.assertEqual(
                1, failure["name_reconciliation"]["exact_name_match_count"]
            )

    def test_pod_name_requires_a_128_bit_hex_nonce(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(LifecycleError, "unique pilot name"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "weak-name",
                    pod_name="consciousness-readout-validation-v1-20260713-unit",
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=False,
                    api_key=API_KEY,
                )

    def test_malformed_account_inventory_fails_closed_before_graphql(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(additional_pods=[None])
            graphql_api = FakeGraphQLApi()
            with self.assertRaisesRegex(LifecycleError, "blocked before GraphQL"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "malformed-inventory",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertEqual([], graphql_api.calls)
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))

    def test_graphql_id_without_exact_nonce_name_never_authorizes_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            graphql_api = FakeGraphQLApi(
                response=_graphql_response(_graphql_pod(name="provider-wrong-name"))
            )
            with self.assertRaisesRegex(LifecycleError, "manual_cleanup_required"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "wrong-graphql-name",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=lambda _seconds: None,
                    rest_fetch_attempts=2,
                )
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))

    def test_graphql_transport_ambiguity_reconciles_unique_name_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            graphql_api = FakeGraphQLApi(
                error=TimeoutError("provider may have accepted create"),
                on_call=lambda: setattr(rest_api, "exists", True),
            )
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "transport-unique",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            failure_path = (
                Path(temporary) / "transport-unique" / "CREATE_FAILURE.json"
            )
            failure = _load(failure_path)
            self.assertTrue(rest_api.deleted)
            self.assertEqual("graphql_transport", failure["failure_stage"])
            self.assertEqual("abc123xyz", failure["candidate_pod_id"])
            self.assertTrue(failure["rollback_verified"])
            self.assertEqual(
                "unique_exact_name_match_rollback_verified",
                failure["name_reconciliation"]["outcome"],
            )
            self.assertFalse(failure["manual_cleanup_required"])
            self.assertTrue(failure["retry_allowed"])
            self.assertNotIn(API_KEY.encode(), failure_path.read_bytes())

    def test_graphql_transport_poll_finds_list_lagged_name_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()

            def appear_after_one_inventory_poll():
                rest_api.exists = True
                rest_api.inventory_visibility_lag = 1

            graphql_api = FakeGraphQLApi(
                error=TimeoutError("provider may have accepted create"),
                on_call=appear_after_one_inventory_poll,
            )
            sleeps = []
            with self.assertRaisesRegex(LifecycleError, "rollback_verified=True"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "transport-list-lag",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                    rest_fetch_attempts=3,
                )
            failure = _load(
                Path(temporary) / "transport-list-lag" / "CREATE_FAILURE.json"
            )
            self.assertTrue(rest_api.deleted)
            self.assertEqual(
                2, failure["name_reconciliation"]["inventory_poll_attempts"]
            )
            self.assertEqual(
                "resolved_rollback_verified",
                failure["name_reconciliation"]["resolution_status"],
            )
            self.assertEqual([1.0], sleeps)

    def test_graphql_transport_ambiguity_never_deletes_multiple_name_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()

            def appear_ambiguously():
                rest_api.exists = True
                rest_api.additional_pods = [_pod(id="def456uvw")]

            graphql_api = FakeGraphQLApi(
                error=TimeoutError("ambiguous create"), on_call=appear_ambiguously
            )
            with self.assertRaisesRegex(
                LifecycleError, "ambiguous_exact_name_matches_no_mutation"
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "transport-ambiguous",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                )
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))
            failure = _load(
                Path(temporary) / "transport-ambiguous" / "CREATE_FAILURE.json"
            )
            self.assertEqual(
                2, failure["name_reconciliation"]["exact_name_match_count"]
            )
            self.assertIsNone(failure["candidate_pod_id"])
            self.assertIsNone(failure["rollback_verified"])
            self.assertTrue(failure["manual_cleanup_required"])
            self.assertFalse(failure["retry_allowed"])

    def test_persistent_zero_name_match_requires_manual_cleanup_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi()
            graphql_api = FakeGraphQLApi(response={"data": {}})
            sleeps = []
            with self.assertRaisesRegex(LifecycleError, "manual_cleanup_required"):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "invalid-no-id",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                    rest_fetch_attempts=3,
                )
            failure = _load(
                Path(temporary) / "invalid-no-id" / "CREATE_FAILURE.json"
            )
            self.assertEqual("graphql_create", failure["failure_stage"])
            self.assertEqual(
                "exact_name_absent_so_far_manual_cleanup_required",
                failure["name_reconciliation"]["outcome"],
            )
            self.assertEqual(
                "unresolved_possible_creation",
                failure["name_reconciliation"]["resolution_status"],
            )
            self.assertEqual(
                3, failure["name_reconciliation"]["inventory_poll_attempts"]
            )
            self.assertTrue(failure["manual_cleanup_required"])
            self.assertFalse(failure["retry_allowed"])
            self.assertEqual([1.0, 1.0], sleeps)
            self.assertFalse(any(call[0] == "DELETE" for call in rest_api.calls))

    def test_rest_fetch_can_lag_once_but_must_precede_ownership(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(initial_not_found=1)
            ownership, selected_rest, _ = self._create_owned(
                Path(temporary), rest_api=rest_api
            )
            expanded_gets = [
                call
                for call in selected_rest.calls
                if call[0] == "GET"
                and call[1].startswith("/pods/abc123xyz?")
                and "includeMachine=true" in call[1]
            ]
            self.assertEqual(3, len(expanded_gets))
            self.assertTrue(ownership.is_file())

    def test_rest_200_incomplete_metadata_is_polled_until_identity_is_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(incomplete_metadata_gets=2)
            graphql_api = FakeGraphQLApi()
            sleeps = []
            ownership = create_lifecycle(
                receipt_dir=Path(temporary) / "metadata-hydration",
                pod_name=POD_NAME,
                volume_id=VOLUME_ID,
                data_center_id=DATA_CENTER,
                max_usd_text="6",
                max_hours_text="1",
                execute=True,
                graphql_api=graphql_api,
                rest_api=rest_api,
                api_key=API_KEY,
                now=lambda: NOW,
                sleeper=sleeps.append,
                rest_fetch_attempts=3,
            )
            self.assertTrue(ownership.is_file())
            self.assertFalse(rest_api.deleted)
            self.assertEqual([1.0, 1.0], sleeps)
            direct_expanded_gets = [
                call
                for call in rest_api.calls
                if call[0] == "GET"
                and call[1].startswith("/pods/abc123xyz?")
            ]
            self.assertEqual(4, len(direct_expanded_gets))

    def test_persistent_incomplete_rest_metadata_is_rolled_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            rest_api = FakeRestApi(incomplete_metadata_gets=99)
            graphql_api = FakeGraphQLApi()
            sleeps = []
            with self.assertRaisesRegex(
                LifecycleError,
                "top-level corroboration remains incomplete.*rollback_verified=True",
            ):
                create_lifecycle(
                    receipt_dir=Path(temporary) / "metadata-never-hydrates",
                    pod_name=POD_NAME,
                    volume_id=VOLUME_ID,
                    data_center_id=DATA_CENTER,
                    max_usd_text="6",
                    max_hours_text="1",
                    execute=True,
                    graphql_api=graphql_api,
                    rest_api=rest_api,
                    api_key=API_KEY,
                    now=lambda: NOW,
                    sleeper=sleeps.append,
                    rest_fetch_attempts=3,
                )
            self.assertTrue(rest_api.deleted)
            self.assertEqual([1.0, 1.0], sleeps)
            failure = _load(
                Path(temporary)
                / "metadata-never-hydrates"
                / "CREATE_FAILURE.json"
            )
            self.assertEqual(
                "rest_corroboration_incomplete_or_mismatch",
                failure["failure_stage"],
            )
            self.assertIn("missing=costPerHr", failure["sanitized_summary"])
            self.assertTrue(failure["rollback_verified"])
            self.assertFalse(failure["manual_cleanup_required"])

    def test_status_verifies_identity_and_meters_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            output, exhausted = status_lifecycle(
                ownership_path=ownership,
                api=api,
                api_key=API_KEY,
                now=lambda: NOW + timedelta(minutes=30),
            )
            receipt = _load(output)
            self.assertFalse(exhausted)
            self.assertEqual(
                "2.99", receipt["budget_meter"]["conservative_estimated_compute_usd"]
            )
            self.assertEqual("1800", receipt["budget_meter"]["elapsed_seconds"])

    def test_terminate_dry_run_does_not_call_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            before = len(api.calls)
            output = terminate_lifecycle(
                ownership_path=ownership,
                execute=False,
                api=None,
                api_key=API_KEY,
            )
            self.assertEqual(before, len(api.calls))
            self.assertEqual("dry_run_no_api_call", _load(output)["status"])

    def test_terminate_requires_identity_then_verifies_both_views(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            # Price drift is metered conservatively but must never block cleanup.
            api.pod["costPerHr"] = "6.00"
            output = terminate_lifecycle(
                ownership_path=ownership,
                execute=True,
                api=api,
                api_key=API_KEY,
                now=lambda: NOW + timedelta(minutes=10),
                sleeper=lambda _seconds: None,
            )
            receipt = _load(output)
            self.assertEqual("deleted_verified", receipt["status"])
            self.assertEqual(204, receipt["delete_http_status"])
            self.assertEqual(404, receipt["post_delete_direct_http_status"])
            self.assertTrue(receipt["absent_from_account_inventory"])
            self.assertEqual(
                "6.00", receipt["budget_meter"]["metered_cost_per_hour_usd"]
            )
            self.assertEqual(1, len([call for call in api.calls if call[0] == "DELETE"]))

    def test_termination_uses_exact_id_and_nonce_even_if_config_now_differs(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            api.pod["imageName"] = "provider/config-drift:unexpected"
            output = terminate_lifecycle(
                ownership_path=ownership,
                execute=True,
                api=api,
                api_key=API_KEY,
                now=lambda: NOW + timedelta(minutes=5),
                sleeper=lambda _seconds: None,
            )
            receipt = _load(output)
            self.assertEqual("deleted_verified", receipt["status"])
            self.assertEqual(
                "config_unavailable_or_mismatch_cleanup_proceeded",
                receipt["predelete_corroboration"]["status"],
            )
            self.assertTrue(api.deleted)

    def test_termination_never_deletes_reused_id_with_wrong_nonce_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            api.pod["name"] = "somebody-elses-pod"
            with self.assertRaisesRegex(LifecycleError, "nonce name differs"):
                terminate_lifecycle(
                    ownership_path=ownership,
                    execute=True,
                    api=api,
                    api_key=API_KEY,
                )
            self.assertFalse(api.deleted)
            self.assertFalse(any(call[0] == "DELETE" for call in api.calls))

    def test_termination_records_already_absent_only_with_strict_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            api.deleted = True
            output = terminate_lifecycle(
                ownership_path=ownership,
                execute=True,
                api=api,
                api_key=API_KEY,
                now=lambda: NOW + timedelta(minutes=5),
            )
            receipt = _load(output)
            self.assertEqual("already_absent_verified", receipt["status"])
            self.assertIsNone(receipt["delete_http_status"])
            self.assertEqual(0, len([call for call in api.calls if call[0] == "DELETE"]))

    def test_malformed_inventory_can_never_prove_termination_absence(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            api.deleted = True
            api.additional_pods = [None]
            with self.assertRaisesRegex(LifecycleError, "malformed"):
                terminate_lifecycle(
                    ownership_path=ownership,
                    execute=True,
                    api=api,
                    api_key=API_KEY,
                )
            self.assertEqual(0, len([call for call in api.calls if call[0] == "DELETE"]))

    def test_tampered_ownership_and_secret_argv_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, api, _ = self._create_owned(Path(temporary))
            value = _load(ownership)
            value["pod"]["id"] = "evilpod1"
            ownership.write_text(json.dumps(value), encoding="utf-8")
            before = len(api.calls)
            with self.assertRaisesRegex(LifecycleError, "canonical JSON|self-hash"):
                terminate_lifecycle(
                    ownership_path=ownership,
                    execute=True,
                    api=api,
                    api_key=API_KEY,
                )
            self.assertEqual(before, len(api.calls))
        with self.assertRaisesRegex(LifecycleError, "credential"):
            reject_secret_argv(["create", f"--token={API_KEY}"], api_key=API_KEY)

    def test_stored_optional_hydration_status_must_match_observed_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            ownership, _, _ = self._create_owned(Path(temporary))
            value = _load(ownership)
            value["rest_corroboration"]["optional_false_field_status"][
                "locked"
            ] = "absent"
            value.pop("receipt_sha256")
            value["receipt_sha256"] = protocol.canonical_sha256(value)
            ownership.write_bytes(protocol.canonical_json_bytes(value) + b"\n")
            with self.assertRaisesRegex(
                LifecycleError, "stored REST corroboration differs"
            ):
                terminate_lifecycle(
                    ownership_path=ownership,
                    execute=False,
                    api=None,
                    api_key=API_KEY,
                )

    def test_rest_allowlist_never_permits_network_volume_mutation(self):
        client = RunPodRestClient(API_KEY)
        with self.assertRaisesRegex(LifecycleError, "outside the lifecycle allowlist"):
            client("DELETE", f"/networkvolumes/{VOLUME_ID}", None)
        with self.assertRaisesRegex(LifecycleError, "outside the lifecycle allowlist"):
            client("PATCH", f"/networkvolumes/{VOLUME_ID}", {"name": "bad"})
        with self.assertRaisesRegex(LifecycleError, "outside the lifecycle allowlist"):
            client("POST", "/pods/abc123xyz/update", {"locked": False})

    def test_graphql_read_allowlist_rejects_extra_filters_and_mutations(self):
        client = RunPodGraphQLClient(API_KEY)
        with self.assertRaisesRegex(LifecycleError, "outside the allowlist"):
            client(
                {
                    "query": GRAPHQL_POD_READ_QUERY,
                    "variables": {
                        "input": {"podId": "abc123xyz", "name": POD_NAME}
                    },
                }
            )
        with self.assertRaisesRegex(LifecycleError, "outside the lifecycle allowlist"):
            client(
                {
                    "query": "mutation unsafe { podTerminate(input: {}) }",
                    "variables": {},
                }
            )


if __name__ == "__main__":
    unittest.main()
