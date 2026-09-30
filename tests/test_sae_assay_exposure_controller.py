"""Offline exposure lifecycle contract; no provider, SSH, weights or paid calls."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from experiments.sae_assay_exposure import controller as c
from tests import test_sae_assay_controller as lifecycle

FREEZE, UTC, PUBLIC_KEY = lifecycle.FREEZE, lifecycle.UTC, lifecycle.PUBLIC_KEY
BUDGET = {"prior_total_usd": "27.6350693241315361", "total_usd": 200, "exposure_max_usd": 25,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}
HARDWARE = {"gpu": "NVIDIA B200", "count": 1, "memory_gb": 180,
            "hourly_price_ceiling_usd": 6.79, "hard_seconds": 7200}
DEADLINE = (UTC + timedelta(seconds=6600)).isoformat()
WORKER_COST = {"hourly_usd": "6.89", "pod_started_utc": UTC.isoformat()}


class FakeAPI(lifecycle.FakeAPI):
    def __init__(self, clock=lambda: UTC):
        super().__init__()
        self.clock, self.extra = clock, []
        self.catalog.update(id="NVIDIA B200", memory=180, price={"secure": 6.79})

    def inventory(self):
        return super().inventory() + self.extra

    def request(self, method, path, body=None):
        try:
            return super().request(method, path, body)
        finally:
            if method == "POST" and self.pod:
                self.pod.update(createdAt=self.clock().isoformat(), cost=self.catalog["price"]["secure"],
                                gpu={"id": "NVIDIA B200", "count": 1, "memory": 180})


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan_data = {"schema": "sae_exposure_v1", "budget": deepcopy(BUDGET), "hardware": deepcopy(HARDWARE)}
        self.plan.write_text(json.dumps(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("test-only private material")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: deepcopy(self.plan_data))
        self.public = Mock()
        for target, value in (("experiments.sae_assay_exposure.controller.ROOT", self.root),
                              ("experiments.sae_assay_exposure.controller.KEY", self.key),
                              ("experiments.sae_assay_exposure.controller.load_plan", self.loader),
                              ("experiments.sae_assay_exposure.controller.verify_public", self.public),
                              ("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("Network forbidden"))),
                              ("socket.socket.connect", Mock(side_effect=AssertionError("Network forbidden")))):
            item = patch(target, value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.dict(os.environ, {"HF_TOKEN": "hf_dummy_test_only", "RUNPOD_API_KEY": "rp_dummy_test_only",
                                      "OPENAI_API_KEY": "openai_dummy_test_only",
                                      "ANTHROPIC_API_KEY": "anthropic_dummy_test_only"}, clear=True)
        item.start()
        self.addCleanup(item.stop)
        self.api = FakeAPI(lambda: self.current)
        self.ctrl = self.controller()

    def controller(self, kind="main", out=None):
        ctrl = c.Controller(self.plan, FREEZE, out or self.root / "out", kind, self.api,
                            clock=lambda: self.current, sleep=Mock(), monotonic=lambda: self.ticks,
                            run=Mock(side_effect=AssertionError("Unexpected subprocess")))
        ctrl.disk_check = Mock()
        return ctrl

    # Exercise the inherited implementations using this controller and its budget.
    launched = lifecycle.ControllerTests.launched
    test_unknown_pod_never_accessed = lifecycle.ControllerTests.test_unknown_pod_never_accessed
    test_retrieval_pauses_resumes_and_never_approves = lifecycle.ControllerTests.test_retrieval_pauses_resumes_and_never_approves
    test_retrieval_failure_always_resumes = lifecycle.ControllerTests.test_retrieval_failure_always_resumes
    test_corrupt_snapshot_blocks_delete = lifecycle.ControllerTests.test_corrupt_snapshot_blocks_delete
    test_corruption_after_retrieval_blocks_delete = lifecycle.ControllerTests.test_corruption_after_retrieval_blocks_delete
    test_retrieve_before_delete_and_verified_closure = lifecycle.ControllerTests.test_retrieve_before_delete_and_verified_closure
    test_no_worker_startup_failure_can_be_closed = lifecycle.ControllerTests.test_no_worker_startup_failure_can_be_closed
    test_lost_delete_response_can_be_confirmed_without_retry = lifecycle.ControllerTests.test_lost_delete_response_can_be_confirmed_without_retry
    test_uncertain_post_reconciles_exact_name_without_second_post = lifecycle.ControllerTests.test_uncertain_post_reconciles_exact_name_without_second_post

    def bind_worker(self):
        binding = {"worker_id": "c" * 32, "pod_id": self.ctrl.owned()["id"],
                   "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE}
        self.ctrl.ledger.bind("worker-intent", {**binding, "script_sha256": "b" * 64, "seconds": 120})
        return binding

    @staticmethod
    def signal_result(action, binding):
        return {"action": action, "verified": True, "binding": binding,
                "stopped": action == "stop", "dispatch_fenced": action == "stop",
                "no_matching_worker": action == "stop"}

    def snapshots(self, *, fail=False, corrupt=False):
        binding = self.bind_worker()
        files = {"rows/row1.json": b'{"id":"row1"}\n', "controller.log": b"progress\n"}
        actions = []

        def ssh(_pod, command, **kwargs):
            if c.WORKER_SIGNAL_SCRIPT in shlex.split(command):
                action = json.loads(kwargs["data"])["action"]
                actions.append(action)
                result = self.signal_result(action, binding)
                if action == "stop":
                    files["controller-stopped.json"] = json.dumps(result).encode()
                return json.dumps(result).encode()
            return json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()

        def run(argv, **_kwargs):
            self.assertEqual(argv[0], "rsync")
            for name, raw in files.items():
                path = Path(argv[-1]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw + (b"corrupt" if corrupt else b""))
            return subprocess.CompletedProcess(argv, 1 if fail else 0, b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=run)
        return actions

    def waiting_state(self, name="qualification", **changes):
        barrier = {"barrier": name, "rows": 6 if name == "first-five" else 1,
                   "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE, **changes}
        return {"pod": self.api.pod, "files": {"WAITING-" + name + ".json": barrier,
                "_progress": {"rows/first.json": [100, 1]}, "_approvals": {}}}

    def snapshot_barrier(self, state):
        directory = self.root / ("barrier-" + str(len(self.ctrl.ledger.read())))
        directory.mkdir()
        artifacts = {}
        for name, data in state["files"].items():
            if name.startswith("WAITING-"):
                (directory / name).write_text(json.dumps(data))
                artifacts[name] = c.sha(directory / name)
        return self.ctrl.record("retrieval", {"pod_id": self.ctrl.owned()["id"],
                                "directory": str(directory), "artifacts": artifacts})

    def test_preflight_is_offline_without_credentials_or_output_creation(self):
        out = self.root / "never-created"
        with patch.object(c, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
            with patch.dict(os.environ, {}, clear=True):
                c.main(["--plan", str(self.plan), "--freeze", FREEZE, "--out", str(out)])
        result = json.loads(output.getvalue())
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["maximum_timer_cost_usd"], "13.78")
        self.assertEqual(result["cumulative_ceiling_usd"], "52.6350693241315361")
        self.assertEqual(result["hard_seconds"], 7200)
        self.assertEqual(result["retrieval_seconds"], 600)
        api.assert_not_called()
        self.public.assert_not_called()
        self.assertFalse(out.exists())

    def test_exact_parent_budget_and_hardware_contract(self):
        self.assertEqual(c.checked_budget(self.plan_data)["exposure_max_usd"], 25)
        changes = [{"prior_total_usd": 0}, {"prior_total_usd": "27.6350693241315360"},
                   {"prior_total_usd": 28}, {"total_usd": 201}, {"total_usd": 52},
                   {"exposure_max_usd": 25.01}, {"exposure_max_usd": 0}, {"exposure_max_usd": True},
                   {"exposure_max_usd": "NaN"}, {"exposure_max_usd": "Infinity"},
                   {"new_paid_judge_calls": 1}, {"new_pro_calls": 1}, {"cheap_max_usd": 2}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                c.checked_budget({"budget": {**BUDGET, **change}, "hardware": HARDWARE})
        for missing in BUDGET:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                c.checked_budget({"budget": {k: v for k, v in BUDGET.items() if k != missing}, "hardware": HARDWARE})
        for change in ({"gpu": "NVIDIA A40"}, {"count": 2}, {"count": True}, {"memory_gb": 179},
                       {"hourly_price_ceiling_usd": 6.99}, {"hard_seconds": 7201}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                c.checked_budget({"budget": BUDGET, "hardware": {**HARDWARE, **change}})

    def test_quote_and_payload_single_b200_no_fallback(self):
        self.assertEqual(c.quote(self.api), {"hourly_rate_usd": "6.79", "storage_hourly_usd": "0.10"})
        payload = c.create_payload("main", c.PREFIX + "main-012345abcdef", PUBLIC_KEY)
        self.assertEqual(payload["env"], {"PUBLIC_KEY": PUBLIC_KEY})
        self.assertEqual(payload["gpu"], {"id": "NVIDIA B200", "count": 1, "minCudaVersion": "12.8"})
        self.assertEqual(payload["image"], c.IMAGE)
        for change in ({"id": "NVIDIA A40"}, {"memory": 179}, {"secure": False}, {"availability": "NONE"},
                       {"price": {"secure": 6.80}}, {"price": {"secure": None}}, {"price": {"secure": 0}}):
            with self.subTest(change=change), patch.dict(self.api.catalog, change), self.assertRaises(ValueError):
                self.ctrl.launch()
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))
        for kind in ("cheap", "other"):
            with self.assertRaises(ValueError):
                c.quote(self.api, kind)
            with self.assertRaises(ValueError):
                self.controller(kind)

    def test_namespace_freeze_and_private_permissions(self):
        self.assertEqual(self.ctrl.base, self.ctrl.out / "exposure-controller/main")
        self.assertEqual(self.ctrl.base.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.ctrl.ledger.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            c.Controller(self.plan, "HEAD", self.ctrl.out, "main", self.api)
        with self.assertRaises(ValueError):
            c.Controller(self.plan, "b" * 40, self.ctrl.out, "main", self.api)
        out = self.root / "symlink-out"
        out.mkdir()
        (out / c.NAMESPACE).symlink_to(self.ctrl.base.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.controller(out=out)

    def test_plan_or_source_drift_fails_before_provider_calls(self):
        self.plan.write_text("changed")
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.ctrl.launch()
        self.loader.side_effect = ValueError("Source drift")
        with self.assertRaisesRegex(ValueError, "Source drift"):
            self.controller(out=self.root / "no-state")
        self.assertFalse((self.root / "no-state").exists())
        self.assertEqual(self.api.calls, [])

    def test_full_timer_must_be_funded_before_creation(self):
        self.plan_data["budget"]["exposure_max_usd"] = 13
        self.plan.write_text(json.dumps(self.plan_data))
        with self.assertRaisesRegex(ValueError, "not funded"):
            self.controller(out=self.root / "small-cap").launch()
        self.assertFalse(any(m == "POST" for m, _, _ in self.api.calls))

    def test_inventory_owned_id_and_deadlines_are_bound_once(self):
        self.api.extra = [{"id": "preexisting", "name": "another-task"}]
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertRegex(intent["payload"]["name"], r"^codex-sae-exposure-20260930-main-[0-9a-f]{12}$")
        self.assertEqual(set(intent["blocked"]), {"preexisting", c.frozen.BLOCKED})
        self.assertEqual(intent["prior_total_usd"], BUDGET["prior_total_usd"])
        self.assertEqual(c._utc(intent["deadline_utc"]), UTC + timedelta(seconds=6600))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]), UTC + timedelta(seconds=7200))
        self.public.assert_called_once_with(self.ctrl.plan_hash, "plan.json", FREEZE)
        with self.assertRaises(ValueError):
            self.controller().launch()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)
        self.ctrl.terminate()
        self.assertIn("preexisting", self.ctrl.event("closed")["data"]["inventory_ids"])
        self.assertFalse(any("preexisting" in path for _, path, _ in self.api.calls))

    def test_preexisting_pod_cannot_be_claimed_mutated_or_deleted(self):
        self.api.extra = [{"id": "newowned1", "name": "another-task"}]
        with patch.object(self.ctrl, "start_worker") as worker, self.assertRaises(ValueError):
            self.ctrl.launch()
        worker.assert_not_called()
        self.assertIsNone(self.ctrl.event("created"))
        self.assertFalse(any(m == "DELETE" for m, _, _ in self.api.calls))
        self.ctrl.run.assert_not_called()

    def test_ambiguous_multiple_matches_never_pick_one(self):
        original = self.api.request

        def ambiguous(method, path, body=None):
            result = original(method, path, body)
            if method == "POST":
                self.api.extra.append({**self.api.pod, "id": "other-new"})
                raise RuntimeError("uncertain creation")
            return result

        self.api.request = ambiguous
        with self.assertRaisesRegex(ValueError, "Ambiguous exact-name"):
            self.ctrl.launch()
        self.assertIsNone(self.ctrl.event("created"))
        self.assertFalse(any(m == "DELETE" for m, _, _ in self.api.calls))
        with self.assertRaises(ValueError):
            self.controller().launch()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_unresolved_create_persists_no_second_post(self):
        original = self.api.request

        def lost(method, path, body=None):
            if method == "POST":
                self.api.calls.append((method, path, body))
                raise RuntimeError("uncertain")
            return original(method, path, body)

        self.api.request = lost
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.ctrl.launch()
        with self.assertRaises(ValueError):
            self.controller().launch()
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.controller().reconcile()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_ssh_rejects_changed_identity_without_subprocess(self):
        self.launched()
        for key, value in (("id", "preexisting"), ("name", "old-name"), ("createdAt", "2000-01-01T00:00:00+00:00")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.ctrl._ssh({**self.api.pod, key: value}, "mutate")
        self.ctrl.run.assert_not_called()

    def test_cost_storage_restart_and_backward_clock(self):
        self.launched()
        self.ticks = 3600
        self.assertEqual(self.ctrl.cost_check(self.api.pod), Decimal("6.89"))
        restarted = self.controller()
        self.ticks += 1
        self.assertGreater(restarted.cost_check(self.api.pod), Decimal("6.89"))
        self.ticks -= 2
        with self.assertRaisesRegex(ValueError, "clock moved backward"):
            restarted.cost_check(self.api.pod)
        self.ticks = 6540
        with self.assertRaisesRegex(ValueError, "deadline"):
            self.ctrl.cost_check(self.api.pod)

    def test_hardware_rate_and_memory_drift_fail_closed(self):
        self.launched()
        for change in ({"cost": None}, {"cost": 0}, {"cost": 6.80}, {"image": "other"},
                       {"cloud": "COMMUNITY"}, {"id": "preexisting"}, {"gpu": None},
                       {"gpu": {"id": "NVIDIA B200", "count": 1, "memory": 179}},
                       {"gpu": {"id": "NVIDIA B200", "count": True, "memory": 180}},
                       {"gpu": {"id": "NVIDIA B200", "count": 2, "memory": 180}}):
            with self.subTest(change=change), patch.dict(self.api.pod, change), self.assertRaises(ValueError):
                self.ctrl.cost_check(self.api.pod)

    def test_worker_shell_and_runner_interface(self):
        script = c.worker_script("main", "data/exposure plan.json", FREEZE, DEADLINE, **WORKER_COST)
        subprocess.run(["/bin/bash", "-n"], input=script.encode(), check=True, capture_output=True)
        command = shlex.split(script.splitlines()[-1])
        self.assertEqual(command[1:4], ["-u", "-m", "experiments.sae_assay_exposure.runner"])
        self.assertEqual(command[4:], ["--plan", "data/exposure plan.json", "--freeze", FREEZE,
                         "--out", c.REMOTE + "/out", "--cache", "/workspace/cache", "--deadline-utc", DEADLINE,
                         "--hourly-usd", "6.89", "--pod-started-utc", UTC.isoformat()])
        self.assertIn("git checkout --detach " + FREEZE, script)
        self.assertIn("experiments.sae_assay_exposure.protocol import load_plan", script)
        for unwanted in ("APPROVE", "--stage", "--no-barriers", "OPENAI_API_KEY", "RUNPOD_API_KEY", "generate("):
            self.assertNotIn(unwanted, script)
        for path in ("/absolute", "../escape", "a/../b", "", "-bad", "a\nb", "a//b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                c.worker_script("main", path, FREEZE, DEADLINE, **WORKER_COST)
        compile(c.STATUS_SCRIPT, "exposure-status", "exec")

    def test_worker_credentials_only_in_stdin_never_logs_or_provider_payload(self):
        self.launched()
        self.ctrl.run = Mock(side_effect=lambda argv, **_: subprocess.CompletedProcess(argv, 0, b"", b""))
        self.ctrl.start_worker()
        calls = self.ctrl.run.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1].kwargs["input"], b"export HF_TOKEN=hf_dummy_test_only\n")
        self.assertIn("stat -c %a", calls[1].args[0][-1])
        self.assertIn("6570s env -i", calls[2].args[0][-1])
        for call in calls:
            self.assertEqual(set(call.kwargs["env"]), {"PATH", "HOME", "LANG"})
            self.assertIn("ForwardAgent=no", call.args[0])
            for secret in os.environ.values():
                self.assertNotIn(secret, " ".join(call.args[0]))
                self.assertNotIn(secret, self.ctrl.ledger.path.read_text())
                self.assertNotIn(secret, json.dumps(self.api.calls))
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()
        self.ctrl.run = Mock(return_value=subprocess.CompletedProcess([], 1, b"", b"hf_dummy_test_only"))
        with self.assertRaises(RuntimeError) as error:
            self.ctrl._ssh(self.api.pod, "true")
        self.assertNotIn("hf_dummy_test_only", str(error.exception))

    def test_bootstrap_failure_preserves_exit_and_removes_credential(self):
        remote, env_file = self.root / "remote", self.root / "private-env"
        env_file.write_text("test credential")
        with patch.object(c, "REMOTE", str(remote)), patch.object(c, "HF_ENV", str(env_file)):
            script = c.worker_script("main", "plan.json", FREEZE, DEADLINE, **WORKER_COST)
        result = subprocess.run(["/bin/bash"], input=("\n".join(script.splitlines()[:4]) + "\nexit 3\n").encode(), capture_output=True)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(env_file.exists())
        self.assertEqual(json.loads((remote / "out/controller-exit.json").read_text()), {"exit_code": 3})

    def test_barriers_require_live_identity_snapshot_explicit_hash_and_order(self):
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
        self.ctrl._ssh = Mock(return_value=b"")
        self.ctrl.status = Mock(return_value=self.waiting_state())
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.ctrl.approve("qualification", self.ctrl.plan_hash)
        for change in ({"rows": True}, {"rows": -1}, {"rows": 0}, {"rows": 2}, {"freeze_commit": "b" * 40},
                       {"plan_sha256": "b" * 64}, {"barrier": "other"}):
            self.ctrl.status.return_value = self.waiting_state(**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ctrl.approve("qualification", self.ctrl.plan_hash)
        self.ctrl.status.return_value = self.waiting_state("first-five")
        self.snapshot_barrier(self.ctrl.status.return_value)
        with self.assertRaisesRegex(ValueError, "Qualification"):
            self.ctrl.approve_first_five(self.ctrl.plan_hash)
        self.ctrl.status.return_value = self.waiting_state()
        self.snapshot_barrier(self.ctrl.status.return_value)
        with self.assertRaises(ValueError):
            self.ctrl.approve("qualification", "wrong")
        self.ctrl._ssh.assert_not_called()
        self.assertEqual(self.ctrl.approve("qualification", self.ctrl.plan_hash)["id"], "approved:qualification")
        state = self.waiting_state("first-five")
        state["files"]["_approvals"]["APPROVE-qualification"] = self.ctrl.plan_hash
        self.ctrl.status.return_value = state
        self.assertEqual(self.ctrl.approve_first_five(self.ctrl.plan_hash)["id"], "approved:first-five")
        self.assertEqual(self.ctrl._ssh.call_args.kwargs["data"], (self.ctrl.plan_hash + "\n").encode())
        self.assertNotIn(self.ctrl.plan_hash, self.ctrl._ssh.call_args.args[1])

    def test_corrupt_or_changed_barrier_snapshot_blocks_approval(self):
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
        state = self.waiting_state()
        self.ctrl.status, self.ctrl._ssh = Mock(return_value=state), Mock()
        receipt = self.snapshot_barrier(state)
        (Path(receipt["data"]["directory"]) / c.WAITING[0]).write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            self.ctrl.approve("qualification", self.ctrl.plan_hash)
        self.ctrl._ssh.assert_not_called()

    def test_monitor_snapshots_each_barrier_but_never_approves(self):
        self.launched()
        self.ctrl.retrieve = Mock()
        self.ctrl.sleep = Mock(side_effect=InterruptedError("end-test"))
        for name in c.BARRIERS:
            self.ctrl.status = Mock(return_value=self.waiting_state(name))
            with patch("sys.stdout", new_callable=io.StringIO) as output, self.assertRaises(InterruptedError):
                self.ctrl.monitor()
            self.assertIn(name, output.getvalue())
        self.assertEqual(self.ctrl.retrieve.call_count, 2)
        self.assertFalse(any(row["id"].startswith("approved:") for row in self.ctrl.ledger.read()))

    def test_terminal_monitor_closes_and_unknown_cost_does_not_claim_budget_pass(self):
        self.launched()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {"DONE-all.json": {}}})
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.api.pod["cost"] = None
        closed = self.ctrl.terminate()["data"]
        self.assertIsNone(closed["compute_upper_bound_usd"])
        self.assertFalse(closed["within_limits"])

    def test_coherent_partial_snapshot_preserves_unfinished_files_and_blocks_moving_tree(self):
        self.launched()
        binding = self.bind_worker()
        files = {"rows/one.json": b'{"id":"one"}', "residuals/two.npy.partial": b"partial array bytes",
                 "precision/receipts.jsonl": b'{"kind":"precision"}\n',
                 "precision/raw/first.json": b'{"mode":"native_zero"}',
                 "precision/captures/first.npy": b"synthetic capture"}
        actions, moving = [], False

        def ssh(_pod, command, **kwargs):
            if c.WORKER_SIGNAL_SCRIPT in shlex.split(command):
                action = json.loads(kwargs["data"])["action"]
                actions.append(action)
                return json.dumps(self.signal_result(action, binding)).encode()
            return json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()

        def run(argv, **_kwargs):
            for name, raw in files.items():
                path = Path(argv[-1]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            if moving:
                files["residuals/two.npy.partial"] += b"changed"
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=run)
        receipt = self.ctrl.retrieve()
        self.assertEqual(set(receipt["data"]["artifacts"]), set(files))
        self.assertEqual(actions, ["pause", "resume"])
        moving = True
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.ctrl.retrieve()
        self.assertEqual(actions, ["pause", "resume", "pause", "resume"])
        self.assertFalse(self.api.deleted)
        self.assertEqual(len([r for r in self.ctrl.ledger.read() if r["id"].startswith("retrieval:")]), 1)

    def test_startup_failure_retrieves_deletes_and_preserves_sanitized_error(self):
        with patch.object(self.ctrl, "start_worker", side_effect=TimeoutError("hf_dummy_test_only")):
            with self.assertRaises(TimeoutError):
                self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertTrue(self.ctrl.event("closed")["data"]["within_limits"])
        self.assertNotIn("hf_dummy_test_only", self.ctrl.ledger.path.read_text())

    def test_read_only_or_closing_controller_cannot_mutate(self):
        self.launched()
        self.api.writable = False
        for operation in (self.ctrl.retrieve, self.ctrl.terminate, self.ctrl.monitor, self.ctrl.start_worker):
            with self.assertRaises(ValueError):
                operation()
        self.api.writable = True
        self.ctrl.ledger.bind("closing", {"pod_id": self.ctrl.owned()["id"]})
        for operation in (self.ctrl.retrieve, self.ctrl.start_worker):
            with self.assertRaises(ValueError):
                operation()
        self.ctrl.run.assert_not_called()

    def test_credentials_removed_before_delete_and_frozen_globals_unchanged(self):
        self.launched()
        self.snapshots()
        self.ctrl.ledger.bind("credential-intent", {"path": c.HF_ENV})
        self.ctrl.terminate()
        self.assertLess(self.ctrl.event("credential-removed")["seq"], self.ctrl.event("delete-intent")["seq"])
        self.assertEqual(c.frozen.HARDWARE["main"], ("NVIDIA B200", Decimal("6.79"), 180))
        self.assertEqual(c.lifecycle.HARDWARE, {"cheap": ("NVIDIA A40", Decimal(".49"), 48)})
        self.assertEqual(c.lifecycle.WAITING, ("WAITING-first-five.json",))
        self.assertEqual(c.HF_ENV, c.lifecycle.HF_ENV)
        self.assertEqual(c.REMOTE, c.frozen.REMOTE)
        self.assertEqual(c.HARD_SECONDS, 7200)

    def test_cli_launch_monitors_and_mutations_require_explicit_flag(self):
        base = ["--plan", str(self.plan), "--freeze", FREEZE, "--out", str(self.ctrl.out)]
        for action in ("launch", "retrieve", "monitor", "approve", "terminate"):
            with self.subTest(action=action), patch.object(c, "RunPodV2") as api:
                with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                    c.main(base + ["--action", action])
                api.assert_not_called()
        fake = Mock()
        fake.monitor.return_value = {"id": "closed"}
        with patch.object(c, "RunPodV2", return_value=self.api), patch.object(c, "Controller", return_value=fake):
            with patch("sys.stdout", new_callable=io.StringIO):
                c.main(base + ["--launch", "--action", "launch"])
        self.assertEqual([call[0] for call in fake.method_calls], ["launch", "monitor"])

    def runner_fixtures(self):
        try:
            from experiments.sae_assay_exposure import runner, protocol
            from tests.test_sae_assay_exposure_runner import SyntheticBackend
            from tests.test_sae_assay_exposure_analysis import fixture_plan
        except ModuleNotFoundError as exc:
            self.skipTest("Runner integration needs the CPU test dependencies: " + exc.name)
        return runner, protocol, SyntheticBackend, fixture_plan

    def remote_process_harness(self, *, live=False, ambiguous=False, signal_failure=False):
        """Execute the actual reconciler against a fake /proc, never signal a PID."""
        remote, proc = self.root / "fake-pod", self.root / "fake-proc"
        (remote / "out").mkdir(parents=True)
        proc.mkdir()
        kills = []

        def process(pid, binding=None, group=None):
            directory = proc / str(pid)
            directory.mkdir()
            fields = ["S", "1", str(group or pid), str(group or pid)] + ["0"] * 15 + ["1234"]
            (directory / "stat").write_text(str(pid) + " (fake worker) " + " ".join(fields))
            env = [] if binding is None else ["CODEX_EXPOSURE_NAMESPACE=" + c.NAMESPACE,
                "CODEX_EXPOSURE_WORKER_ID=" + binding["worker_id"],
                "CODEX_EXPOSURE_FREEZE=" + binding["freeze_commit"],
                "CODEX_EXPOSURE_POD_ID=" + binding["pod_id"]]
            (directory / "environ").write_bytes(b"\0".join(v.encode() for v in env))
            (directory / "cmdline").write_bytes(b"timeout\0synthetic-command\0")

        process(9999)  # An unrelated system/SSH process must never be signalled.

        def kill(pid, sig):
            kills.append((pid, sig))
            self.assertNotEqual(pid, 9999)
            if signal_failure:
                raise PermissionError("simulated signal failure")
            if sig in (signal.SIGTERM, signal.SIGKILL):
                for entry in list(proc.iterdir()):
                    fields = (entry / "stat").read_text().split(") ", 1)[1].split()
                    if fields[2] == str(pid):
                        shutil.rmtree(entry)

        def ssh(_pod, command, **kwargs):
            tokens = shlex.split(command)
            if c.WORKER_SIGNAL_SCRIPT in tokens:
                source = c.WORKER_SIGNAL_SCRIPT.replace("pathlib.Path('/proc')", "pathlib.Path(" + repr(str(proc)) + ")")
                with patch("sys.stdin", io.StringIO(kwargs["data"].decode())), patch("sys.stdout", new_callable=io.StringIO) as output:
                    with patch("os.killpg", side_effect=kill), patch("time.sleep", return_value=None):
                        try:
                            exec(compile(source, "owned-worker-reconciler", "exec"), {})
                        except SystemExit as exc:
                            self.assertEqual(exc.code, 0)
                return output.getvalue().encode()
            if c.frozen.MANIFEST_SCRIPT in tokens:
                return json.dumps({p.relative_to(remote / "out").as_posix(): c.sha(p)
                                   for p in (remote / "out").rglob("*") if p.is_file()}).encode()
            if "nohup setsid timeout" in command:
                intent = self.ctrl.event("worker-intent")["data"]
                if live:
                    process(4321, intent)
                    (remote / "out/controller.log").write_text("Synthetic partial bootstrap log\n")
                if ambiguous:
                    process(5678, intent)
                raise RuntimeError("simulated uncertain SSH dispatch")
            return b""

        def copy_snapshot(argv, **_kwargs):
            self.assertEqual(argv[0], "rsync")
            for source in (remote / "out").rglob("*"):
                if source.is_file():
                    destination = Path(argv[-1]) / source.relative_to(remote / "out")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=copy_snapshot)
        return remote, proc, kills

    def test_dispatch_failure_before_pid_closes_without_signals_after_proved_absence(self):
        remote, proc, kills = self.remote_process_harness()
        with patch.object(c, "REMOTE", str(remote)), self.assertRaisesRegex(RuntimeError, "uncertain SSH"):
            self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertIsNotNone(self.ctrl.event("worker-intent"))
        self.assertIsNone(self.ctrl.event("worker-started"))
        self.assertFalse((remote / "worker.pid").exists())
        self.assertTrue((remote / "worker-closing.json").is_file())
        receipt = json.loads((self.ctrl.base / "final-retrieval.json").read_text())["data"]
        stopped = json.loads((Path(receipt["directory"]) / "controller-stopped.json").read_text())
        self.assertTrue(stopped["missing_pid"] and stopped["dispatch_fenced"] and stopped["no_matching_worker"])
        self.assertEqual(stopped["binding"]["pod_id"], self.ctrl.owned()["id"])
        self.assertEqual(kills, [])
        self.assertTrue((proc / "9999").is_dir())
        self.assertLess(self.ctrl.event("delete-intent")["seq"], self.ctrl.event("closed")["seq"])

    def test_uncertain_dispatch_recovers_exact_owned_worker_and_preserves_logs(self):
        remote, proc, kills = self.remote_process_harness(live=True)
        with patch.object(c, "REMOTE", str(remote)), self.assertRaisesRegex(RuntimeError, "uncertain SSH"):
            self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertEqual((remote / "worker.pid").read_text(), "4321\n")
        self.assertEqual(kills, [(4321, signal.SIGCONT), (4321, signal.SIGTERM)])
        self.assertTrue((proc / "9999").is_dir())
        receipt = json.loads((self.ctrl.base / "final-retrieval.json").read_text())["data"]
        self.assertIn("controller.log", receipt["artifacts"])
        self.assertIn("controller-worker-reconciled.json", receipt["artifacts"])
        stopped = json.loads((Path(receipt["directory"]) / "controller-stopped.json").read_text())
        self.assertTrue(stopped["recovered_pid"])

    def test_ambiguous_live_dispatch_does_not_signal_or_delete(self):
        self.launched()
        remote, proc, kills = self.remote_process_harness(live=True, ambiguous=True)
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            with self.assertRaisesRegex(RuntimeError, "ambiguous worker"):
                self.ctrl.terminate()
        self.assertFalse(self.api.deleted)
        self.assertEqual(kills, [])
        self.assertTrue((proc / "4321").exists() and (proc / "5678").exists())
        self.assertFalse((self.ctrl.base / "final-retrieval.json").exists())

    def test_signal_failure_never_claims_stopped_or_permits_deletion(self):
        self.launched()
        remote, proc, kills = self.remote_process_harness(live=True, signal_failure=True)
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            with self.assertRaises(PermissionError):
                self.ctrl.terminate()
        self.assertFalse(self.api.deleted)
        self.assertEqual(kills, [(4321, signal.SIGCONT)])
        self.assertTrue((proc / "4321").exists())
        self.assertFalse((remote / "out/controller-stopped.json").exists())
        self.assertIsNone(self.ctrl.event("delete-intent"))

    def test_incomplete_process_scan_cannot_be_treated_as_no_worker(self):
        self.launched()
        remote, proc, kills = self.remote_process_harness()
        (proc / "9999/stat").write_text("unreadable process inventory")
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            with self.assertRaisesRegex(RuntimeError, "inventory incomplete"):
                self.ctrl.terminate()
        self.assertFalse(self.api.deleted)
        self.assertEqual(kills, [])
        self.assertFalse((remote / "out/controller-stopped.json").exists())

    def test_foreign_pid_file_never_signals_unmarked_system_process(self):
        self.launched()
        remote, proc, kills = self.remote_process_harness()
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            (remote / "worker.pid").write_text("9999\n")
            with self.assertRaisesRegex(RuntimeError, "leader identity mismatch"):
                self.ctrl.terminate()
        self.assertFalse(self.api.deleted)
        self.assertEqual(kills, [])
        self.assertTrue((proc / "9999").exists())

    def test_missing_pid_absence_reconciliation_can_repeat_without_receipt_rewrite(self):
        self.launched()
        remote, _, kills = self.remote_process_harness()
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            self.ctrl.signal_worker(self.api.pod, "stop")
            original = (remote / "out/controller-stopped.json").read_bytes()
            self.ctrl.signal_worker(self.api.pod, "stop")
            self.assertEqual((remote / "out/controller-stopped.json").read_bytes(), original)
            self.ctrl.terminate()
        self.assertTrue(self.api.deleted)
        self.assertEqual(kills, [])

    def test_stopped_reconciliation_is_idempotent_after_lost_ssh_response(self):
        self.launched()
        remote, _, kills = self.remote_process_harness(live=True)
        with patch.object(c, "REMOTE", str(remote)):
            with self.assertRaises(RuntimeError):
                self.ctrl.start_worker()
            first = self.ctrl.signal_worker(self.api.pod, "stop")
            original = (remote / "out/controller-stopped.json").read_bytes()
            second = self.ctrl.signal_worker(self.api.pod, "stop")
            self.assertEqual((remote / "out/controller-stopped.json").read_bytes(), original)
            self.ctrl.terminate()
        self.assertTrue(first["recovered_pid"])
        self.assertFalse(second["recovered_pid"])
        self.assertTrue(self.api.deleted)
        self.assertEqual(kills, [(4321, signal.SIGCONT), (4321, signal.SIGTERM)])

    def test_closing_fence_blocks_late_launch_and_child_before_work(self):
        remote = self.root / "fenced-remote"
        (remote / "out").mkdir(parents=True)
        (remote / "worker-closing.json").write_text("{}")
        binding = {"worker_id": "d" * 32, "pod_id": "owned-pod", "freeze_commit": FREEZE}
        bin_path = self.root / "bin"
        bin_path.mkdir()
        flock = bin_path / "flock"
        flock.write_text("#!" + sys.executable + "\nimport fcntl,sys\n"
                         "fcntl.flock(int(sys.argv[2]), fcntl.LOCK_UN if sys.argv[1]=='-u' else fcntl.LOCK_EX)\n")
        flock.chmod(0o700)
        with patch.object(c, "REMOTE", str(remote)):
            command = c.dispatch_command("touch " + shlex.quote(str(remote / "unexpected-work")), 600, binding)
        child = shlex.split(command)[shlex.split(command).index("-c") + 1]
        for executable in (command, child):
            result = subprocess.run(["/bin/bash", "-c", executable], capture_output=True,
                                    env={"PATH": str(bin_path) + ":/usr/bin:/bin"})
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((remote / "worker.pid").exists())
        self.assertFalse((remote / "unexpected-work").exists())
        self.assertFalse((remote / "out/controller.log").exists())
        self.assertEqual(command.count("flock -x 9"), 2)
        self.assertIn("9>&- & pid=$!", command)

    def test_actual_runner_parser_accepts_dispatch_quoted_rate_and_creation_time(self):
        runner, protocol, _, _ = self.runner_fixtures()
        self.api.catalog["price"]["secure"] = 6.20
        self.launched()
        self.current += timedelta(seconds=14)
        self.ticks += 14
        self.ctrl.run = Mock(side_effect=lambda argv, **_: subprocess.CompletedProcess(argv, 0, b"", b""))
        self.ctrl.start_worker()
        dispatch = shlex.split(self.ctrl.run.call_args.args[0][-1])
        script = dispatch[dispatch.index("-c") + 1]
        command = shlex.split(script.splitlines()[-1])
        intent = self.ctrl.event("create-intent")["data"]
        expected_rate = str(c._number(intent["quote"]["hourly_rate_usd"]) + c.STORAGE)
        with patch.object(protocol, "load_plan", return_value=self.plan_data) as loader:
            with patch.object(runner, "ExposureRun") as runtime, patch("sys.argv", ["runner", *command[4:]]):
                runner.main()
        loader.assert_called_once_with(Path(self.ctrl.relative), FREEZE)
        self.assertEqual(runtime.call_args.args, (self.plan_data, Path(self.ctrl.relative), FREEZE,
                         Path(c.REMOTE + "/out"), intent["deadline_utc"], Path("/workspace/cache")))
        self.assertEqual(runtime.call_args.kwargs, {"hourly_usd": expected_rate,
                                                  "pod_started_utc": intent["created_utc"]})
        self.assertEqual(Decimal(expected_rate), Decimal("6.30"))
        self.assertNotEqual(intent["created_utc"], self.current.isoformat())
        runtime.return_value.execute.assert_called_once_with()
        # Argparse must fail if the launcher ever drops either required field.
        for flag in ("--hourly-usd", "--pod-started-utc"):
            arguments = command[4:].copy()
            index = arguments.index(flag)
            del arguments[index:index + 2]
            with patch("sys.argv", ["runner", *arguments]), patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    runner.main()

    def test_actual_runner_barriers_roundtrip_through_snapshot_and_controller_approval(self):
        runner, _, backend, fixture_plan = self.runner_fixtures()
        self.plan_data = fixture_plan()
        self.plan.write_text(json.dumps(self.plan_data))
        self.ctrl = self.controller(out=self.root / "integration-controller")
        self.launched()
        binding = self.bind_worker()
        self.ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
        remote = self.root / "integration-pod"
        output = remote / "out"
        run = runner.ExposureRun(self.plan_data, self.plan, FREEZE, output, DEADLINE,
                                 hourly_usd="6.89", pod_started_utc=UTC.isoformat(),
                                 factory=backend, barriers=True, clock=lambda: UTC.timestamp(),
                                 monotonic=lambda: 0, qualifier=lambda: {"pass": True, "test_only": True})
        self.addCleanup(lambda: run.backend.close() if run.backend is not None else None)
        self.assertIs(type(run).barrier, runner.Run.barrier)

        class WaitingForAudit(Exception):
            pass

        real_check = run.check_time

        def bounded_wait(seconds=300):
            real_check(seconds)
            if any((output / name).is_file()
                   and not (output / name.replace("WAITING-", "APPROVE-").removesuffix(".json")).exists()
                   for name in c.WAITING):
                raise WaitingForAudit()

        # Interrupt only the wait, after the real inherited barrier wrote its
        # notice. Row writes, counts, hashes and controller approval remain real.
        run.check_time = bounded_wait
        actions = []

        def ssh(_pod, command, **kwargs):
            tokens = shlex.split(command)
            if c.WORKER_SIGNAL_SCRIPT in tokens:
                action = json.loads(kwargs["data"])["action"]
                actions.append(action)
                return json.dumps(self.signal_result(action, binding)).encode()
            if c.frozen.MANIFEST_SCRIPT in tokens:
                return json.dumps({p.relative_to(output).as_posix(): c.sha(p)
                                   for p in output.rglob("*") if p.is_file()}).encode()
            if c.STATUS_SCRIPT in tokens:
                files = {name: json.loads((output / name).read_text()) for name in c.WAITING
                         if (output / name).is_file()}
                files["_approvals"] = {p.name: p.read_text().strip() for p in output.glob("APPROVE-*")}
                return json.dumps(files).encode()
            result = subprocess.run(["/bin/bash", "-c", command], input=kwargs.get("data"),
                                    capture_output=True, env=c.frozen.local_env())
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        def copy_snapshot(argv, **_kwargs):
            self.assertEqual(argv[0], "rsync")
            for source in output.rglob("*"):
                if source.is_file():
                    destination = Path(argv[-1]) / source.relative_to(output)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=copy_snapshot)
        with patch.object(c, "REMOTE", str(remote)), patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(WaitingForAudit):
                run.qualify()
            qualification = json.loads((output / "WAITING-qualification.json").read_text())
            self.assertEqual(qualification["rows"], 1)
            self.ctrl.retrieve()
            self.ctrl.approve("qualification", self.ctrl.plan_hash)
            run.barrier("qualification")
            for item in run.plan["texts"][:5]:
                run.screen(item)
            with self.assertRaises(WaitingForAudit):
                run.barrier("first-five")
            first_five = json.loads((output / "WAITING-first-five.json").read_text())
            self.assertEqual(first_five["rows"], 6)
            receipt = self.ctrl.retrieve()
            self.ctrl.approve_first_five(self.ctrl.plan_hash)
            run.barrier("first-five")
        self.assertEqual(actions, ["pause", "resume", "pause", "resume"])
        self.assertEqual(len([p for p in receipt["data"]["artifacts"] if p.startswith("rows/")]), 6)
        self.assertEqual(len([p for p in receipt["data"]["artifacts"] if p.startswith("residuals/")]), 5)
        for name in c.BARRIERS:
            self.assertEqual((output / ("APPROVE-" + name)).read_text(), self.ctrl.plan_hash + "\n")
            self.assertIsNotNone(self.ctrl.event("approved:" + name))


class LoaderTests(unittest.TestCase):
    def test_loader_delegates_to_parent_exposure_protocol_only(self):
        module = types.ModuleType("experiments.sae_assay_exposure.protocol")
        module.load_plan = Mock(return_value={"schema": "sae_exposure_v1"})
        with patch.dict("sys.modules", {module.__name__: module}):
            self.assertEqual(c.load_plan(Path("plan.json"), FREEZE), {"schema": "sae_exposure_v1"})
        module.load_plan.assert_called_once_with(Path("plan.json"), FREEZE)


@unittest.skipUnless(sys.platform == "linux", "Real /proc/flock integration requires Linux")
class LinuxProcessIntegrationTests(unittest.TestCase):
    def test_real_process_reconciliation_fencing_and_descriptor_release(self):
        prefix = []
        if os.geteuid() != 0:
            sudo = shutil.which("sudo")
            if not sudo or subprocess.run([sudo, "-n", "true"], capture_output=True).returncode:
                self.skipTest("Complete /proc inventory requires root or passwordless sudo in CI")
            prefix = [sudo, "-n"]
        # The whole proof is one bounded Linux subprocess so root-owned fixtures
        # are cleaned there. No network, model, provider or existing PID is used.
        source = r'''
import fcntl,json,os,pathlib,signal,subprocess,sys,tempfile,time,uuid
from experiments.sae_assay_exposure import controller as c
def binding():
 return {'worker_id':uuid.uuid4().hex,'pod_id':'synthetic-ci-owned',
         'freeze_commit':'a'*40,'plan_sha256':'b'*64}
def stop(root,b):
 result=subprocess.run([sys.executable,'-c',c.WORKER_SIGNAL_SCRIPT],
   input=json.dumps({'remote':str(root),'binding':b,'action':'stop'}),
   text=True,capture_output=True,timeout=20)
 assert result.returncode==0, result.stderr
 return json.loads(result.stdout)
with tempfile.TemporaryDirectory(prefix='exposure-process-proof-') as temp:
 root=pathlib.Path(temp); absent=root/'absent'; (absent/'out').mkdir(parents=True)
 b=binding(); c.REMOTE=str(absent)
 first=stop(absent,b); before=(absent/'out/controller-stopped.json').read_bytes()
 assert first['missing_pid'] and first['no_matching_worker'] and first['pid'] is None
 assert stop(absent,b)['verified']
 assert (absent/'out/controller-stopped.json').read_bytes()==before
 command=c.dispatch_command('touch '+str(absent/'should-not-run'),120,b)
 late=subprocess.run(['bash','-c',command],capture_output=True,timeout=5)
 assert late.returncode!=0 and not (absent/'worker.pid').exists()
 assert not (absent/'should-not-run').exists()

 live=root/'live'; (live/'out').mkdir(parents=True); c.REMOTE=str(live); b=binding()
 marker=('CODEX_EXPOSURE_WORKER_ID='+b['worker_id']).encode()
 unrelated=subprocess.Popen(['sleep','120'],start_new_session=True)
 pid=None
 try:
  command=c.dispatch_command('touch '+str(live/'ready')+'\nsleep 120',120,b)
  launched=subprocess.run(['bash','-c',command],capture_output=True,timeout=5)
  assert launched.returncode==0, launched.stderr
  pid=int((live/'worker.pid').read_text())
  deadline=time.monotonic()+5
  while not (live/'ready').exists():
   assert time.monotonic()<deadline, 'owned child did not pass its launch gate'
   time.sleep(.02)
  assert os.getpgid(pid)==pid and marker in pathlib.Path('/proc',str(pid),'cmdline').read_bytes()
  # A running worker cannot retain either launch-gate lock descriptor.
  with (live/'worker-dispatch.lock').open('a') as lock:
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
   fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
  (live/'worker.pid').unlink()
  result=stop(live,b)
  assert result['recovered_pid'] and result['missing_pid'] and result['pid']==pid
  assert unrelated.poll() is None
  stopped=(live/'out/controller-stopped.json').read_bytes()
  assert stop(live,b)['verified']
  assert (live/'out/controller-stopped.json').read_bytes()==stopped
 finally:
  if pid is not None:
   try:
    proc=pathlib.Path('/proc',str(pid))
    if marker in (proc/'cmdline').read_bytes() or marker in (proc/'environ').read_bytes():
     if os.getpgid(pid)==pid: os.killpg(pid,signal.SIGKILL)
   except ProcessLookupError: pass
   except FileNotFoundError: pass
  unrelated.terminate(); unrelated.wait(timeout=5)
print(json.dumps({'absent_pid':True,'live_recovery':True,'late_launch_fenced':True,
                  'worker_lock_released':True,'unrelated_process_preserved':True}))
'''
        result = subprocess.run(prefix + [sys.executable, "-c", source], cwd=c.ROOT,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "absent_pid": True, "live_recovery": True, "late_launch_fenced": True,
            "worker_lock_released": True, "unrelated_process_preserved": True})


if __name__ == "__main__":
    unittest.main()
