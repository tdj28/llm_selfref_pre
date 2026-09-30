"""CPU-only controller tests: all HTTP, remote SSH and paid actions are mocked."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from experiments.sae_assay_diagnostic import controller as c
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _canonical

FREEZE = "a" * 40
UTC = datetime(2026, 9, 30, tzinfo=timezone.utc)
PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest test-only"


class FakeAPI:
    writable = True

    def __init__(self):
        self.calls, self.pod = [], None
        self.lost_response, self.deleted = False, False
        self.catalog = {"id": c.HARDWARE["cheap"][0], "memory": 24, "secure": True,
                        "price": {"secure": .74}, "availability": "LOW"}

    def inventory(self):
        self.calls.append(("GET", "/pods", None))
        return [{"id": c.BLOCKED, "name": "otherroom-sam2-pro6000"}] + (
            [self.pod] if self.pod and not self.deleted else [])

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/catalog/"):
            return 200, self.catalog
        if method == "POST":
            self.pod = {**body, "id": "newowned1", "createdAt": UTC.isoformat(),
                        "cost": .74, "status": "RUNNING",
                        "ssh": {"direct": {"host": "192.0.2.1", "port": 12345, "username": "root"}}}
            if self.lost_response:
                raise RuntimeError("simulated uncertain POST")
            return 201, self.pod
        if method == "DELETE":
            self.deleted = True
            return 204, None
        if self.deleted:
            raise c.ApiError(404)
        return 200, self.pod


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_text("{}\n")
        self.key = self.root / "key"
        self.key.write_text("test private material")
        self.key.chmod(0o600)
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        for target, value in (("experiments.sae_assay_diagnostic.protocol.ROOT", self.root),
                              ("experiments.sae_assay_diagnostic.protocol.load_plan", Mock(return_value={})),
                              ("experiments.sae_assay_diagnostic.controller.KEY", self.key),
                              ("experiments.sae_assay_diagnostic.controller.shutil.disk_usage", Mock(return_value=Mock(free=20 * 1024 ** 3))),
                              ("experiments.sae_assay_diagnostic.controller.verify_public", Mock())):
            item = patch(target, value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.dict(os.environ, {"HF_TOKEN": "hf_dummy_test_only", "RUNPOD_API_KEY": "rp_dummy_test_only",
                                      "OPENAI_API_KEY": "openai_dummy_test_only", "ANTHROPIC_API_KEY": "anthropic_dummy_test_only"})
        item.start()
        self.addCleanup(item.stop)
        self.api = FakeAPI()
        self.ctrl = c.Controller(self.plan, FREEZE, self.root / "out", "cheap", self.api,
                                 clock=lambda: UTC, sleep=Mock())

    def launched(self):
        with patch.object(self.ctrl, "start_worker"):
            self.ctrl.launch()
        return self.ctrl

    def snapshots(self, *, fail=False, corrupt=False):
        self.ctrl.ledger.bind("worker-intent", {"script_sha256": "b" * 64, "seconds": 120})
        files = {"rows/row1.json": b'{"id":"row1"}\n', "controller.log": b"progress\n"}
        actions = []

        def ssh(pod, command, **kwargs):
            if c.SIGNAL_SCRIPT in __import__("shlex").split(command):
                action = command.rsplit(" ", 1)[1]
                actions.append(action)
                if action == "stop":
                    files["controller-stopped.json"] = b'{"stopped":true}\n'
                return json.dumps({"verified": True, "action": action}).encode()
            return json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()

        def run(argv, **kwargs):
            self.assertEqual(argv[0], "rsync")
            destination = Path(argv[-1])
            for name, raw in files.items():
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw + (b"corrupt" if corrupt else b""))
            return subprocess.CompletedProcess(argv, 1 if fail else 0, b"", b"")

        self.ctrl._ssh = Mock(side_effect=ssh)
        self.ctrl.run = Mock(side_effect=run)
        return actions

    def test_default_cli_is_unpaid_even_without_valid_plan(self):
        with patch.object(c, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
            c.main(["--plan", "missing", "--freeze", FREEZE, "--out", "missing", "--kind", "main"])
        api.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())["dry_run"])

    def test_schema_and_public_key_only(self):
        payload = c.create_payload("cheap", c.PREFIX + "cheap-012345abcdef", PUBLIC_KEY)
        self.assertEqual(payload["gpu"], {"id": "NVIDIA GeForce RTX 4090", "count": 1, "minCudaVersion": "12.8"})
        self.assertEqual(payload["env"], {"PUBLIC_KEY": PUBLIC_KEY})
        self.assertEqual(payload["image"], "runpod/pytorch:" + c.IMAGE_TAG + "@" + c.IMAGE_DIGEST)
        self.assertEqual(payload["mounts"], {"persistent": {"size": 250, "path": "/workspace"}})
        self.assertFalse({"gpuTypeIds", "imageName"} & payload.keys())
        for key in ("private key", PUBLIC_KEY + "\nexport EVIL=1"):
            with self.assertRaises(ValueError):
                c.create_payload("cheap", payload["name"], key)

    def test_quote_fails_closed(self):
        self.assertEqual(c.quote(self.api, "cheap"), {"hourly_rate_usd": "0.74", "storage_hourly_usd": "0.10"})
        for replacement in ({"availability": "NONE"}, {"memory": 16}, {"secure": False},
                            {"price": {"secure": .75}}, {"price": {"secure": None}},
                            {"price": {"secure": float("nan")}}, {"price": {"secure": 0}}):
            with self.subTest(replacement=replacement), patch.dict(self.api.catalog, replacement), self.assertRaises(ValueError):
                c.quote(self.api, "cheap")

    def test_transport_guard_and_sanitized_headers(self):
        response = Mock(status=200)
        response.read.return_value = b'{}'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        api = c.RunPodV2("secret", opener=opener)
        for method, path in (("POST", "/pods"), ("DELETE", "/pods/newowned1"),
                             ("GET", "/pods/" + c.BLOCKED), ("GET", "//evil")):
            with self.assertRaises(ValueError):
                api.request(method, path)
        opener.open.assert_not_called()
        api.request("GET", "/catalog/gpus")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertIsNotNone(request.get_header("User-agent"))

    def test_inventory_paginates_and_rejects_repeated_cursor(self):
        api = c.RunPodV2("secret")
        api.request = Mock(side_effect=[(200, {"pods": [{"id": "a"}], "pagination": {"hasNextPage": True, "nextCursor": "next"}}),
                                       (200, {"pods": [{"id": "b"}], "pagination": {"hasNextPage": False}})])
        self.assertEqual([p["id"] for p in api.inventory()], ["a", "b"])
        self.assertIn("cursor=next", api.request.call_args.args[1])
        api.request = Mock(return_value=(200, {"pods": [], "pagination": {"hasNextPage": True, "nextCursor": "next"}}))
        with self.assertRaises(ValueError):
            api.inventory()

    def test_strict_json(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
            with self.assertRaises(ValueError):
                c.strict_json(text)

    def test_worker_contract_and_shell_syntax(self):
        for kind in ("cheap", "main"):
            script = c.worker_script(kind, "data/plan.json", FREEZE, UTC.isoformat())
            subprocess.run(["bash", "-n"], input=script.encode(), check=True, capture_output=True)
            self.assertIn("pip freeze --all", script)
            self.assertIn("python3 -m venv --system-site-packages", script)
            self.assertIn("/venv/bin/python -m pip install", script)
            self.assertNotIn("python3 -m pip install", script)
            self.assertNotIn("APPROVE", script)
            self.assertNotIn("RUNPOD_API_KEY", script)
            self.assertIn("--stage all" if kind == "main" else "--out /workspace/sae-assay/out/cheap-qualification.json", script)
        for script in (c.SIGNAL_SCRIPT, c.MANIFEST_SCRIPT, c.STATUS_SCRIPT):
            compile(script, "remote_script", "exec")

    def test_bootstrap_retry_carries_prior_spending_without_new_allowance(self):
        self.ctrl.plan = {"budget": {"prior_compute_usd": .0300157487}}
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertEqual(Decimal(intent["prior_compute_usd"]), Decimal("0.0300157487"))
        self.assertEqual(Decimal(intent["local_cap_usd"]), Decimal("4.9699842513"))

    def test_exit_trap_records_bootstrap_failure(self):
        with patch.object(c, "REMOTE", str(self.root / "remote")):
            script = c.worker_script("cheap", "plan.json", FREEZE, UTC.isoformat())
        setup = "\n".join(script.splitlines()[:4]) + "\nexit 3\n"
        result = subprocess.run(["bash"], input=setup.encode(), capture_output=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads((self.root / "remote/out/controller-exit.json").read_text()), {"exit_code": 3})

    def test_ssh_endpoint_and_environment(self):
        self.launched()
        args = c.ssh_args(self.api.pod, self.key, self.root / "known_hosts")
        self.assertIn("ForwardAgent=no", args)
        self.assertNotIn("SendEnv", " ".join(args))
        self.assertFalse({"HF_TOKEN", "RUNPOD_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"} & c.local_env().keys())
        for change in ({"host": "-oProxyCommand=evil"}, {"port": True}, {"username": "root;evil"}):
            with patch.dict(self.api.pod["ssh"]["direct"], change), self.assertRaises(ValueError):
                c.ssh_args(self.api.pod, self.key, self.root / "hosts")

    def test_launch_records_single_create_and_cheap_wall_cap(self):
        self.launched()
        intent = self.ctrl.event("create-intent")
        created = self.ctrl.event("created")
        self.assertLess(intent["seq"], created["seq"])
        self.assertEqual(c._utc(intent["data"]["deadline_utc"]), UTC + timedelta(minutes=35))
        self.assertIn(c.BLOCKED, intent["data"]["blocked"])
        self.assertEqual(self.ctrl.owned()["id"], "newowned1")
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)

    def test_uncertain_post_reconciles_exact_name_without_second_post(self):
        self.api.lost_response = True
        self.launched()
        self.assertEqual(self.ctrl.owned()["id"], "newowned1")
        self.assertTrue(any(r["id"].startswith("create-reconciled:") for r in self.ctrl.ledger.read()))
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)

    def test_unknown_pod_never_accessed(self):
        with self.assertRaises(ValueError):
            self.ctrl.get_pod()
        with self.assertRaises(ValueError):
            self.ctrl.terminate()
        self.assertEqual(self.api.calls, [])

    def test_main_requires_cheap_audit(self):
        main = c.Controller(self.plan, FREEZE, self.root / "out", "main", self.api, clock=lambda: UTC)
        with self.assertRaises(ValueError):
            main.launch()
        self.assertEqual(self.api.calls, [])

    def test_ssh_waits_for_daemon_and_transfers_only_hf_stdin(self):
        self.launched()
        self.ctrl._ssh = Mock(side_effect=[RuntimeError("not ready"), b"", b"", b""])
        self.ctrl.start_worker()
        self.ctrl.sleep.assert_called_with(15)
        calls = self.ctrl._ssh.call_args_list
        self.assertEqual(calls[0].args[1], "true")
        transfer = calls[2]
        self.assertEqual(transfer.kwargs["data"], b"export HF_TOKEN=hf_dummy_test_only\n")
        self.assertNotIn("hf_dummy_test_only", transfer.args[1])
        self.assertIn("chmod 600", transfer.args[1])
        dispatched = shlex.split(calls[3].args[1])
        self.assertEqual(dispatched[dispatched.index("env"):dispatched.index("bash")], [
            "env", "-i", "HOME=/root",
            "PATH=/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LD_LIBRARY_PATH=/usr/local/cuda/lib64",
        ])
        self.assertIn("--stage", c.worker_script("main", "plan.json", FREEZE, UTC.isoformat()))
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_runtime_hardware_drift_and_cost_unknown_fail(self):
        self.launched()
        self.ctrl.cost_check(self.api.pod)
        for change in ({"cost": None}, {"cost": 0}, {"cost": .75}, {"image": "other"}, {"cloud": "COMMUNITY"}):
            with patch.dict(self.api.pod, change), self.assertRaises(ValueError):
                self.ctrl.cost_check(self.api.pod)

    def test_retrieval_pauses_resumes_and_never_approves(self):
        self.launched()
        actions = self.snapshots()
        one = self.ctrl.retrieve()
        two = self.ctrl.retrieve()
        self.assertEqual(actions, ["pause", "resume", "pause", "resume"])
        self.assertNotEqual(one["data"]["directory"], two["data"]["directory"])
        self.assertIn("--link-dest=" + one["data"]["directory"], self.ctrl.run.call_args.args[0])
        self.assertFalse(list(self.root.rglob("APPROVE*")))
        self.assertEqual(len(one["data"]["artifacts"]), 2)

    def test_retrieval_failure_always_resumes(self):
        self.launched()
        actions = self.snapshots(fail=True)
        with self.assertRaises(RuntimeError):
            self.ctrl.retrieve()
        self.assertEqual(actions, ["pause", "resume"])
        self.assertFalse(self.api.deleted)

    def test_corrupt_snapshot_blocks_delete(self):
        self.launched()
        self.snapshots(corrupt=True)
        with self.assertRaises(ValueError):
            self.ctrl.terminate()
        self.assertFalse(self.api.deleted)
        self.assertIsNone(self.ctrl.event("delete-intent"))

    def test_corruption_after_retrieval_blocks_delete(self):
        self.launched()
        self.snapshots()
        receipt = self.ctrl.retrieve(final=True)
        (Path(receipt["data"]["directory"]) / "rows/row1.json").write_text("corrupted")
        with self.assertRaises(ValueError):
            self.ctrl.terminate()
        self.assertFalse(self.api.deleted)

    def test_retrieve_before_delete_and_verified_closure(self):
        self.launched()
        actions = self.snapshots()
        closed = self.ctrl.terminate()
        self.assertEqual(actions, ["stop"])
        self.assertTrue(self.api.deleted)
        self.assertEqual(closed["data"]["get_status"], 404)
        self.assertLess(self.ctrl.event("delete-intent")["seq"], closed["seq"])
        self.assertTrue((self.ctrl.base / "final-retrieval.json").is_file())
        self.assertFalse(any(c.BLOCKED in path for _, path, _ in self.api.calls))

    def test_no_worker_startup_failure_can_be_closed(self):
        self.launched()
        self.ctrl.terminate()
        self.assertTrue(self.api.deleted)
        self.assertTrue(c.strict_json((self.ctrl.base / "final-retrieval.json").read_bytes())["data"]["no_worker_dispatched"])

    def test_barriers_are_observed_not_approved(self):
        self.launched()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {c.WAITING[0]: {"plan_sha256": self.ctrl.plan_hash}, "_progress": {}}})
        self.ctrl.retrieve = Mock()
        self.ctrl.sleep = Mock(side_effect=InterruptedError("test stop"))
        with patch("sys.stdout", new_callable=io.StringIO), self.assertRaises(InterruptedError):
            self.ctrl.monitor()
        self.ctrl.retrieve.assert_called_once()
        self.assertFalse(list(self.root.rglob("APPROVE*")))

    def test_stalled_worker_is_retrieved_before_termination(self):
        self.launched()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {"_progress": {"rows/a.json": [1, 1]}}})
        self.ctrl.cost_check = Mock()
        self.ctrl.retrieve, self.ctrl.quiesce, self.ctrl.terminate = Mock(), Mock(), Mock(return_value="closed")
        with patch.object(c.time, "monotonic", side_effect=[0, 0, 0, 0, 901]):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.quiesce.assert_called_once()
        self.ctrl.terminate.assert_called_once()

    def test_preserved_approved_barrier_does_not_disable_stall_guard(self):
        self.launched()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {
            c.WAITING[0]: {}, "_approvals": {"APPROVE-qualification": self.ctrl.plan_hash},
            "_progress": {"rows/a.json": [1, 1]}}})
        self.ctrl.cost_check = Mock()
        self.ctrl.retrieve, self.ctrl.quiesce, self.ctrl.terminate = Mock(), Mock(), Mock(return_value="closed")
        with patch.object(c.time, "monotonic", side_effect=[0, 0, 0, 0, 901]):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.quiesce.assert_called_once()

    def test_low_disk_blocks_create_and_pull_without_mutating_remote(self):
        with patch.object(c.shutil, "disk_usage", return_value=Mock(free=8 * 1024 ** 3 - 1)):
            with self.assertRaises(ValueError):
                self.ctrl.launch()
            with self.assertRaises(ValueError):
                self.ctrl.retrieve()
        self.assertEqual(self.api.calls, [])

    def test_lost_delete_response_can_be_confirmed_without_retry(self):
        self.launched()
        self.snapshots()
        original = self.api.request

        def lost(method, path, body=None):
            result = original(method, path, body)
            if method == "DELETE":
                raise RuntimeError("lost response")
            return result

        self.api.request = lost
        with self.assertRaises(RuntimeError):
            self.ctrl.terminate()
        self.assertTrue(self.api.deleted)
        self.assertEqual(self.ctrl.terminate()["id"], "closed")
        self.assertEqual(sum(method == "DELETE" for method, _, _ in self.api.calls), 1)


if __name__ == "__main__":
    unittest.main()
