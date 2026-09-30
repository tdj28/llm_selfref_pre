"""Offline lifecycle tests: no provider, SSH, weights, GPU or paid calls."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from experiments.sae_assay_replay import controller as c
from tests import test_sae_assay_controller as lifecycle

FREEZE, UTC, PUBLIC_KEY = lifecycle.FREEZE, lifecycle.UTC, lifecycle.PUBLIC_KEY
BUDGET = {"prior_total_usd": "27.3845359753", "total_usd": 200, "replay_max_usd": 4,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}
HARDWARE = {"gpu": "NVIDIA A40", "count": 1, "memory_gb": 48,
            "hourly_price_ceiling_usd": .49, "hard_seconds": 7200}


class FakeAPI(lifecycle.FakeAPI):
    def __init__(self, clock=lambda: UTC):
        super().__init__()
        self.clock, self.extra = clock, []
        self.catalog.update(id="NVIDIA A40", memory=48, price={"secure": .49})

    def inventory(self):
        return super().inventory() + self.extra

    def request(self, method, path, body=None):
        try:
            return super().request(method, path, body)
        finally:
            if method == "POST" and self.pod:
                self.pod.update(createdAt=self.clock().isoformat(), cost=self.catalog["price"]["secure"],
                                gpu={"id": c.HARDWARE["cheap"][0], "count": 1,
                                     "memory": 48, "vcpuCount": 16})


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan_data = {"budget": deepcopy(BUDGET), "hardware": deepcopy(HARDWARE)}
        self.plan.write_text(json.dumps(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("test-only private material")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: deepcopy(self.plan_data))
        self.public = Mock()
        for target, value in (("experiments.sae_assay_replay.controller.ROOT", self.root),
                              ("experiments.sae_assay_replay.controller.load_plan", self.loader),
                              ("experiments.sae_assay_replay.controller.verify_public", self.public),
                              ("experiments.sae_assay_diagnostic.controller.KEY", self.key),
                              ("experiments.sae_assay_diagnostic.controller.shutil.disk_usage",
                               Mock(return_value=Mock(free=20 * 1024 ** 3))),
                              ("urllib.request.OpenerDirector.open", Mock(side_effect=AssertionError("Network forbidden")))):
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

    def controller(self, kind="cheap", api=None):
        return c.Controller(self.plan, FREEZE, self.root / "out", kind, api or self.api,
                            clock=lambda: self.current, sleep=Mock(), monotonic=lambda: self.ticks,
                            run=Mock(side_effect=AssertionError("Unexpected subprocess")))

    launched = lifecycle.ControllerTests.launched
    snapshots = lifecycle.ControllerTests.snapshots
    test_unknown_pod_never_accessed = lifecycle.ControllerTests.test_unknown_pod_never_accessed
    test_retrieval_pauses_resumes_and_never_approves = lifecycle.ControllerTests.test_retrieval_pauses_resumes_and_never_approves
    test_retrieval_failure_always_resumes = lifecycle.ControllerTests.test_retrieval_failure_always_resumes
    test_corrupt_snapshot_blocks_delete = lifecycle.ControllerTests.test_corrupt_snapshot_blocks_delete
    test_corruption_after_retrieval_blocks_delete = lifecycle.ControllerTests.test_corruption_after_retrieval_blocks_delete
    test_retrieve_before_delete_and_verified_closure = lifecycle.ControllerTests.test_retrieve_before_delete_and_verified_closure
    test_no_worker_startup_failure_can_be_closed = lifecycle.ControllerTests.test_no_worker_startup_failure_can_be_closed
    test_low_disk_blocks_create_and_pull_without_mutating_remote = lifecycle.ControllerTests.test_low_disk_blocks_create_and_pull_without_mutating_remote
    test_lost_delete_response_can_be_confirmed_without_retry = lifecycle.ControllerTests.test_lost_delete_response_can_be_confirmed_without_retry
    test_uncertain_post_reconciles_exact_name_without_second_post = lifecycle.ControllerTests.test_uncertain_post_reconciles_exact_name_without_second_post

    def waiting_state(self, **changes):
        barrier = {"barrier": "first-five", "rows": 5, "plan_sha256": self.ctrl.plan_hash,
                   "freeze_commit": FREEZE, **changes}
        return {"pod": self.api.pod, "files": {c.WAITING[0]: barrier,
                "_progress": {"rows/first.json": [100, 1]}, "_approvals": {}}}

    def test_preflight_is_local_read_only_and_does_not_need_credentials(self):
        out = self.root / "never-created"
        with patch.object(c, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
            with patch.dict(os.environ, {}, clear=True):
                c.main(["--plan", str(self.plan), "--freeze", FREEZE, "--out", str(out)])
        result = json.loads(output.getvalue())
        self.assertTrue(result["preflight"])
        self.assertEqual(result["network_calls"], 0)
        self.assertEqual(result["maximum_timer_cost_usd"], "1.18")
        self.assertEqual(result["cumulative_ceiling_usd"], "31.3845359753")
        api.assert_not_called()
        self.public.assert_not_called()
        self.assertFalse(out.exists())

    def test_explicit_quote_only_uses_get_and_never_creates_namespace(self):
        out = self.root / "quote-only"
        with patch.object(c, "RunPodV2", return_value=self.api) as api, patch("sys.stdout", new_callable=io.StringIO):
            c.main(["--plan", str(self.plan), "--freeze", FREEZE, "--out", str(out), "--action", "quote"])
        api.assert_called_once_with("rp_dummy_test_only", writable=False)
        self.assertEqual([call[0] for call in self.api.calls], ["GET"])
        self.assertFalse(out.exists())

    def test_cli_mutation_needs_explicit_flag(self):
        for action in ("launch", "retrieve", "monitor", "approve", "terminate"):
            with self.subTest(action=action), patch.object(c, "RunPodV2") as api:
                with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                    c.main(["--plan", "missing", "--freeze", FREEZE, "--out", "missing", "--action", action])
                api.assert_not_called()

    def test_cli_launch_keeps_monitor_alive_and_approval_needs_hash(self):
        base = ["--plan", str(self.plan), "--freeze", FREEZE, "--out", str(self.ctrl.out), "--launch"]
        fake = Mock()
        fake.monitor.return_value = {"id": "closed"}
        with patch.object(c, "RunPodV2", return_value=self.api), patch.object(c, "Controller", return_value=fake):
            with patch("sys.stdout", new_callable=io.StringIO):
                c.main(base + ["--action", "launch"])
        self.assertEqual([call[0] for call in fake.method_calls], ["launch", "monitor"])
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            c.main(base + ["--action", "approve"])

    def test_loader_drift_stops_before_state_or_paid_calls(self):
        self.loader.assert_called_once_with(self.plan, FREEZE)
        self.loader.side_effect = ValueError("Source drift")
        with self.assertRaisesRegex(ValueError, "Source drift"):
            c.Controller(self.plan, FREEZE, self.root / "no-state", "cheap", self.api)
        self.assertFalse((self.root / "no-state").exists())
        with self.assertRaisesRegex(ValueError, "Source drift"):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_plan_byte_drift_stops_before_paid_calls(self):
        self.plan.write_text("changed")
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_only_cheap_exact_freeze_private_namespace(self):
        self.assertEqual(self.ctrl.base, self.ctrl.out / "replay-controller/cheap")
        self.assertEqual(self.ctrl.base.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.ctrl.ledger.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            self.controller("main")
        with self.assertRaises(ValueError):
            c.Controller(self.plan, "HEAD", self.ctrl.out, "cheap", self.api)
        with self.assertRaises(ValueError):
            c.Controller(self.plan, "b" * 40, self.ctrl.out, "cheap", self.api)
        for row in self.ctrl.ledger.read():
            self.assertEqual(row["plan_sha256"], self.ctrl.plan_hash)
            self.assertEqual(row["freeze_commit"], FREEZE)

    def test_symlink_namespace_rejected(self):
        out = self.root / "symlink-out"
        out.mkdir()
        (out / c.NAMESPACE).symlink_to(self.ctrl.base.parent, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            c.Controller(self.plan, FREEZE, out, "cheap", self.api)

    def test_budget_rejects_reset_expansion_missing_fields_or_paid_branches(self):
        changes = [{"prior_total_usd": "27.3845359752"}, {"prior_total_usd": 0},
                   {"prior_total_usd": 28}, {"total_usd": 201}, {"total_usd": 31},
                   {"replay_max_usd": 4.01}, {"replay_max_usd": 0}, {"replay_max_usd": True},
                   {"replay_max_usd": "NaN"}, {"replay_max_usd": "Infinity"},
                   {"new_paid_judge_calls": 1}, {"new_pro_calls": 1}, {"main_max_usd": 2}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                c.checked_budget({"budget": {**BUDGET, **change}, "hardware": HARDWARE})
        for missing in BUDGET:
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                c.checked_budget({"budget": {k: v for k, v in BUDGET.items() if k != missing}, "hardware": HARDWARE})
        self.assertEqual(c.checked_budget({"budget": BUDGET, "hardware": HARDWARE})["replay_max_usd"], 4)
        self.assertLess(c.PRIOR_TOTAL + c.MAX_NEW, 200)

    def test_full_timer_must_be_funded_before_create(self):
        self.plan_data["budget"]["replay_max_usd"] = 1
        self.plan.write_text(json.dumps(self.plan_data))
        ctrl = c.Controller(self.plan, FREEZE, self.root / "small-cap", "cheap", self.api)
        with self.assertRaisesRegex(ValueError, "not funded"):
            ctrl.launch()
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))

    def test_plan_hardware_must_match_this_freeze(self):
        for change in ({"gpu": "NVIDIA GeForce RTX 4090"}, {"count": 2}, {"memory_gb": 24},
                       {"hourly_price_ceiling_usd": .54}, {"hard_seconds": 7201}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "A40"):
                c.checked_budget({"budget": BUDGET, "hardware": {**HARDWARE, **change}})

    def test_unavailable_a40_never_falls_back_or_creates(self):
        self.api.catalog["availability"] = "NONE"
        with self.assertRaisesRegex(ValueError, "no fallback"):
            self.ctrl.launch()
        self.assertIsNone(self.ctrl.event("create-intent"))
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))
        catalogs = [path for _, path, _ in self.api.calls if path.startswith("/catalog/")]
        self.assertEqual(len(catalogs), 1)
        self.assertIn("NVIDIA%20A40", catalogs[0])

    def test_a40_catalog_rejects_wrong_gpu_memory_cloud_or_rate(self):
        for change in ({"id": "NVIDIA GeForce RTX 4090"}, {"memory": 24}, {"secure": False},
                       {"price": {"secure": .54}}, {"price": {"secure": None}},
                       {"price": {"secure": 0}}, {"price": {"secure": "NaN"}}):
            with self.subTest(change=change), patch.dict(self.api.catalog, change), self.assertRaises(ValueError):
                c.quote(self.api)

    def test_payload_quote_is_pinned_single_a6000_and_public_key_only(self):
        name = c.PREFIX + "cheap-012345abcdef"
        payload = c.create_payload("cheap", name, PUBLIC_KEY)
        self.assertEqual(payload["env"], {"PUBLIC_KEY": PUBLIC_KEY})
        self.assertEqual(payload["image"], c.frozen.IMAGE)
        self.assertEqual(payload["gpu"]["count"], 1)
        self.assertEqual(payload["gpu"]["id"], "NVIDIA A40")
        self.assertEqual(c.quote(self.api), {"hourly_rate_usd": "0.49", "storage_hourly_usd": "0.10"})
        for kind, pod_name, key in (("main", name, PUBLIC_KEY), ("cheap", c.frozen.PREFIX + name, PUBLIC_KEY),
                                     ("cheap", name, "private key"), ("cheap", name, PUBLIC_KEY + "\nEVIL=1")):
            with self.assertRaises(ValueError):
                c.create_payload(kind, pod_name, key)
        with self.assertRaises(ValueError):
            c.quote(self.api, "main")
        self.api.catalog["price"]["secure"] = .54
        with self.assertRaises(ValueError):
            c.quote(self.api)

    def test_create_once_freeze_deadline_cumulative_and_inventory_binding(self):
        self.api.extra = [{"id": "preexisting", "name": "another-task"}]
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertRegex(intent["payload"]["name"], r"^codex-sae-replay-20260930-cheap-[0-9a-f]{12}$")
        self.assertEqual(set(intent["blocked"]), {"preexisting", c.frozen.BLOCKED})
        self.assertEqual(intent["prior_total_usd"], "27.3845359753")
        self.assertEqual(intent["cumulative_ceiling_usd"], "31.3845359753")
        self.assertEqual(c._utc(intent["deadline_utc"]), UTC + timedelta(seconds=6600))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]), UTC + timedelta(seconds=7200))
        self.public.assert_called_once_with(self.ctrl.plan_hash, "plan.json", FREEZE)
        with self.assertRaises(ValueError):
            self.controller().launch()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_preexisting_id_is_never_claimed_or_deleted(self):
        self.api.extra = [{"id": "newowned1", "name": "another-task"}]
        with patch.object(self.ctrl, "start_worker") as worker, self.assertRaises(ValueError):
            self.ctrl.launch()
        worker.assert_not_called()
        self.assertIsNone(self.ctrl.event("created"))
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))

    def test_ssh_and_registration_reject_identity_or_old_namespace(self):
        self.launched()
        intent = deepcopy(self.ctrl.event("create-intent")["data"])
        for key, value in (("id", "preexisting"), ("name", "old-name"), ("createdAt", "2000-01-01T00:00:00+00:00")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.ctrl._ssh({**self.api.pod, key: value}, "mutate")
        intent["payload"]["name"] = c.frozen.PREFIX + "cheap-012345abcdef"
        self.assertFalse(self.ctrl._new_pod({**self.api.pod, "name": intent["payload"]["name"]}, intent))
        self.ctrl.run.assert_not_called()

    def test_unknown_create_persists_without_second_post(self):
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

    def test_clock_accounting_storage_reserve_and_restart(self):
        self.launched()
        self.ticks = 3600
        self.assertEqual(self.ctrl.cost_check(self.api.pod), Decimal(".59"))
        restarted = self.controller()
        self.ticks += 1
        self.assertGreater(restarted.cost_check(self.api.pod), Decimal(".59"))
        self.ticks = 6540
        with self.assertRaisesRegex(ValueError, "deadline"):
            self.ctrl.cost_check(self.api.pod)
        self.assertGreaterEqual(Decimal(self.ctrl.ledger.read()[-1]["data"]["elapsed_seconds"]), 6540)

    def test_backward_wall_or_monotonic_stops_work(self):
        self.launched()
        self.current += timedelta(seconds=120)
        self.ticks = 120
        self.ctrl.cost_check(self.api.pod)
        self.ticks = 119
        with self.assertRaisesRegex(ValueError, "clock moved backward"):
            self.ctrl.cost_check(self.api.pod)
        self.ticks = 121
        self.current = UTC
        with self.assertRaisesRegex(ValueError, "clock moved backward"):
            self.ctrl.cost_check(self.api.pod)

    def test_runtime_hardware_or_rate_drift_fails_closed(self):
        self.launched()
        for change in ({"cost": None}, {"cost": 0}, {"cost": .54}, {"image": "other"},
                       {"cloud": "COMMUNITY"}, {"id": "preexisting"}, {"gpu": None},
                       {"gpu": {"id": "NVIDIA B200", "count": 1}},
                       {"gpu": {"id": "NVIDIA GeForce RTX 4090", "count": 1, "memory": 24}},
                       {"gpu": {"id": c.HARDWARE["cheap"][0], "count": 1, "memory": 24}},
                       {"gpu": {"id": c.HARDWARE["cheap"][0], "count": True}},
                       {"gpu": {"id": c.HARDWARE["cheap"][0], "count": 2}}):
            with self.subTest(change=change), patch.dict(self.api.pod, change), self.assertRaises(ValueError):
                self.ctrl.cost_check(self.api.pod)

    def test_worker_contract_shell_syntax_source_and_no_other_paid_branch(self):
        script = c.worker_script("cheap", "data/replay plan.json", FREEZE, UTC.isoformat())
        subprocess.run(["/bin/bash", "-n"], input=script.encode(), check=True, capture_output=True)
        self.assertIn("git checkout --detach " + FREEZE, script)
        self.assertIn("from experiments.sae_assay_replay.protocol import load_plan", script)
        self.assertIn("python3 -m venv --system-site-packages", script)
        self.assertIn("/venv/bin/python -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt", script)
        self.assertIn("pip freeze --all", script)
        args = shlex.split(script.splitlines()[-1])
        self.assertEqual(args[:4], [c.frozen.REMOTE + "/venv/bin/python", "-u", "-m", "experiments.sae_assay_replay.runner"])
        self.assertEqual(args[4:], ["--plan", "data/replay plan.json", "--freeze", FREEZE,
                                   "--out", c.frozen.REMOTE + "/out", "--cache", "/workspace/cache",
                                   "--deadline-utc", UTC.isoformat()])
        for forbidden in ("--stage", "APPROVE", "API_KEY", "sae_assay_repair.runner", "sae_assay_diagnostic.runner"):
            self.assertNotIn(forbidden, script)
        for path in ("../old.json", "/plan.json", "", "data//plan.json", "./plan.json", "bad\nplan.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                c.worker_script("cheap", path, FREEZE, UTC.isoformat())
        with self.assertRaises(ValueError):
            c.worker_script("main", "plan.json", FREEZE, UTC.isoformat())

    def test_exit_trap_records_failure_and_removes_token(self):
        env_file = self.root / "hf.env"
        env_file.write_text("test-only")
        with patch.object(c.frozen, "REMOTE", str(self.root / "remote")), patch.object(c, "HF_ENV", str(env_file)):
            script = c.worker_script("cheap", "plan.json", FREEZE, UTC.isoformat())
        setup = "\n".join(script.splitlines()[:4]) + "\nexit 3\n"
        result = subprocess.run(["/bin/bash"], input=setup.encode(), capture_output=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertFalse(env_file.exists())
        self.assertEqual(json.loads((self.root / "remote/out/controller-exit.json").read_text()), {"exit_code": 3})

    def test_worker_only_streams_hf_token_over_stdin_and_never_restarts(self):
        self.launched()
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl.run = Mock(side_effect=run)
        self.ctrl.start_worker()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]["input"], b"export HF_TOKEN=hf_dummy_test_only\n")
        self.assertIn("/root/sae-replay-hf.env", calls[1][0][-1])
        self.assertIn("stat -c %a", calls[1][0][-1])
        self.assertIn("timeout --signal=TERM --kill-after=30s 6570s env -i", calls[2][0][-1])
        for argv, kwargs in calls:
            self.assertEqual(set(kwargs["env"]), {"PATH", "HOME", "LANG"})
            self.assertIn("ForwardAgent=no", argv)
            for secret in os.environ.values():
                self.assertNotIn(secret, " ".join(argv))
                self.assertNotIn(secret, self.ctrl.ledger.path.read_text())
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_status_has_first_five_and_progress_without_changing_frozen_globals(self):
        self.launched()
        remote = self.root / "remote-output"
        remote.mkdir()
        barrier = self.waiting_state()["files"][c.WAITING[0]]
        (remote / c.WAITING[0]).write_text(json.dumps(barrier))
        (remote / "APPROVE-first-five").write_text(self.ctrl.plan_hash + "\n")

        def ssh(_pod, command, **_kwargs):
            self.assertEqual(shlex.split(command), ["python3", "-c", c.STATUS_SCRIPT])
            with patch("pathlib.Path", return_value=remote), patch("sys.stdout", new_callable=io.StringIO) as output:
                exec(compile(c.STATUS_SCRIPT, "replay-status", "exec"), {})
            return output.getvalue().encode()

        self.ctrl._ssh = Mock(side_effect=ssh)
        files = self.ctrl.status()["files"]
        self.assertEqual(files[c.WAITING[0]], barrier)
        self.assertIn(c.WAITING[0], files["_progress"])
        self.assertEqual(files["_approvals"], {"APPROVE-first-five": self.ctrl.plan_hash})
        self.assertNotIn("first-five", c.frozen.STATUS_SCRIPT)
        self.assertEqual(c.frozen.WAITING, ("WAITING-qualification.json", "WAITING-target-first5.json"))

    def test_approval_requires_exact_live_barrier_and_explicit_matching_hash(self):
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
        self.ctrl._ssh = Mock(return_value=b"")
        self.ctrl.status = Mock(return_value=self.waiting_state())
        with self.assertRaises(ValueError):
            self.ctrl.approve_first_five("wrong hash")
        for change in ({"rows": 4}, {"rows": 6}, {"rows": True}, {"freeze_commit": "b" * 40},
                       {"plan_sha256": "b" * 64}, {"barrier": "qualification"}):
            self.ctrl.status.return_value = self.waiting_state(**change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ctrl.approve_first_five(self.ctrl.plan_hash)
        self.ctrl._ssh.assert_not_called()
        self.ctrl.status.return_value = self.waiting_state()
        result = self.ctrl.approve_first_five(self.ctrl.plan_hash)
        self.assertEqual(result["id"], "approved:first-five")
        call = self.ctrl._ssh.call_args
        self.assertEqual(call.kwargs["data"], (self.ctrl.plan_hash + "\n").encode())
        self.assertIn("APPROVE-first-five", call.args[1])
        self.assertNotIn(self.ctrl.plan_hash, call.args[1])

    def test_approval_script_is_idempotent_but_does_not_overwrite_wrong_approval(self):
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": UTC.isoformat()})
        self.ctrl.status = Mock(return_value=self.waiting_state())
        remote = self.root / "remote"
        (remote / "out").mkdir(parents=True)

        def ssh(_pod, command, **kwargs):
            result = subprocess.run(["/bin/bash", "-c", command], input=kwargs.get("data"), capture_output=True)
            if result.returncode:
                raise RuntimeError("Remote approval rejected")
            return result.stdout

        self.ctrl._ssh = Mock(side_effect=ssh)
        with patch.object(c.frozen, "REMOTE", str(remote)):
            self.ctrl.approve_first_five(self.ctrl.plan_hash)
            self.ctrl.approve_first_five(self.ctrl.plan_hash)
            approval = remote / "out/APPROVE-first-five"
            self.assertEqual(approval.read_text(), self.ctrl.plan_hash + "\n")
            approval.write_text("wrong-plan\n")
            with self.assertRaises(RuntimeError):
                self.ctrl.approve_first_five(self.ctrl.plan_hash)
            self.assertEqual(approval.read_text(), "wrong-plan\n")

    def test_monitor_retrieves_waiting_without_automatic_approval(self):
        self.launched()
        self.ctrl.status = Mock(return_value=self.waiting_state())
        self.ctrl.retrieve = Mock()
        self.ctrl.sleep = Mock(side_effect=InterruptedError("end-test"))
        with patch("sys.stdout", new_callable=io.StringIO) as output, self.assertRaises(InterruptedError):
            self.ctrl.monitor()
        self.assertIn("WAITING:", output.getvalue())
        self.ctrl.retrieve.assert_called_once_with()
        self.assertFalse(list(self.root.rglob("APPROVE-*")))
        self.assertIsNone(self.ctrl.event("approved:first-five"))

    def test_approved_stalled_worker_and_deadline_are_closed(self):
        self.launched()
        state = self.waiting_state()
        state["files"]["_approvals"]["APPROVE-first-five"] = self.ctrl.plan_hash
        self.ctrl.status = Mock(return_value=state)
        self.ctrl.retrieve = Mock()
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.ctrl.sleep = lambda _: setattr(self, "ticks", self.ticks + 901)
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.close_until_verified.assert_called_once_with()
        self.ctrl.close_until_verified.reset_mock()
        self.ticks = 6540
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.close_until_verified.assert_called_once_with()

    def test_live_status_and_partial_pull_failures_retry_then_close(self):
        self.launched()
        state = self.waiting_state()
        done = {"pod": self.api.pod, "files": {"controller-exit.json": {"exit_code": 1}}}
        self.ctrl.status = Mock(side_effect=[RuntimeError("unreachable"), state, state, done])
        self.ctrl.retrieve = Mock(side_effect=[RuntimeError("partial transfer retained"), {"snapshot": True}])
        self.ctrl.close_until_verified = Mock(return_value="closed")
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.assertEqual(self.ctrl.retrieve.call_count, 2)
        self.assertEqual(self.ctrl.sleep.call_count, 3)
        self.assertEqual(sum(r["id"].startswith("monitor-retry:") for r in self.ctrl.ledger.read()), 2)

    def test_cleanup_retries_partial_snapshot_preserving_failures_before_delete(self):
        self.launched()
        actions = self.snapshots(fail=True)
        original_run = self.ctrl.run.side_effect
        calls = 0

        def run(argv, **kwargs):
            nonlocal calls
            result = original_run(argv, **kwargs)
            calls += 1
            if calls >= 2:
                result.returncode = 0
            return result

        self.ctrl.run.side_effect = run
        with patch("sys.stdout", new_callable=io.StringIO):
            closed = self.ctrl.close_until_verified()
        self.assertEqual(closed["id"], "closed")
        self.assertEqual(actions, ["stop", "stop"])
        self.assertEqual(len(list((self.ctrl.base / "retrievals").iterdir())), 2)
        self.assertEqual(self.ctrl.event("delete-response")["data"]["status"], 204)
        self.assertEqual(sum(m == "DELETE" for m, _, _ in self.api.calls), 1)

    def test_cleanup_keeps_uncertain_delete_and_never_repeats_it(self):
        self.launched()
        original = self.api.request

        def delayed(method, path, body=None):
            if method == "DELETE":
                self.api.calls.append((method, path, body))
                raise RuntimeError("lost delete")
            return original(method, path, body)

        self.api.request = delayed
        count = 0

        def sleep(_):
            nonlocal count
            count += 1
            if count == 2:
                self.api.deleted = True

        self.ctrl.sleep = sleep
        with patch("sys.stdout", new_callable=io.StringIO):
            result = self.ctrl.close_until_verified()
        self.assertEqual(result["data"]["get_status"], 404)
        self.assertEqual(sum(m == "DELETE" for m, _, _ in self.api.calls), 1)
        self.assertIsNone(self.ctrl.event("delete-response"))

    def test_overrun_is_reported_not_hidden_and_closure_still_verified(self):
        self.launched()
        self.ticks = 7201
        self.current += timedelta(seconds=7201)
        closed = self.ctrl.terminate()["data"]
        self.assertFalse(closed["within_limits"])
        self.assertEqual(closed["get_status"], 404)
        self.assertGreater(Decimal(closed["compute_upper_bound_usd"]), Decimal("1.18"))
        self.assertEqual(Decimal(closed["cumulative_upper_bound_usd"]),
                         c.PRIOR_TOTAL + Decimal(closed["compute_upper_bound_usd"]))
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()
        with self.assertRaises(ValueError):
            self.ctrl.retrieve()

    def test_unknown_final_cost_retains_closure_without_false_budget_pass(self):
        self.launched()
        self.api.pod["cost"] = None
        closed = self.ctrl.terminate()["data"]
        self.assertIsNone(closed["compute_upper_bound_usd"])
        self.assertFalse(closed["within_limits"])
        self.assertTrue(self.api.deleted)

    def test_no_credential_or_disk_failure_creates_pod(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_startup_failure_is_retrieved_deleted_and_closed(self):
        with patch.object(self.ctrl, "start_worker", side_effect=TimeoutError("startup")):
            with self.assertRaises(TimeoutError):
                self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertTrue(self.ctrl.event("closed")["data"]["within_limits"])
        self.assertTrue((self.ctrl.base / "final-retrieval.json").exists())

    def test_snapshot_mutation_requires_writable_api(self):
        self.launched()
        self.api.writable = False
        for operation in (self.ctrl.retrieve, self.ctrl.terminate, self.ctrl.monitor, self.ctrl.start_worker):
            with self.assertRaises(ValueError):
                operation()
        self.ctrl.run.assert_not_called()

    def test_credentials_removed_before_delete_and_terminal_snapshot_retained(self):
        self.launched()
        self.snapshots()
        self.ctrl.ledger.bind("credential-intent", {"path": c.HF_ENV})
        self.ctrl.terminate()
        self.assertLess(self.ctrl.event("credential-removed")["seq"], self.ctrl.event("delete-intent")["seq"])
        commands = [call.args[1] for call in self.ctrl._ssh.call_args_list]
        self.assertIn("rm -f " + c.HF_ENV + "; test ! -e " + c.HF_ENV, commands)
        self.assertTrue((self.ctrl.base / "final-retrieval.json").exists())

    def test_source_parent_hardware_and_scripts_are_not_mutated(self):
        self.assertEqual(c.frozen.HARDWARE["cheap"], ("NVIDIA GeForce RTX 4090", Decimal(".74"), 24))
        self.assertNotEqual(c.HARDWARE, c.frozen.HARDWARE)
        self.assertNotIn("first-five", c.frozen.STATUS_SCRIPT)


class LoaderTests(unittest.TestCase):
    def test_loader_uses_only_parent_replay_protocol(self):
        module = types.ModuleType("experiments.sae_assay_replay.protocol")
        module.load_plan = Mock(return_value={"replay": True})
        with patch.dict("sys.modules", {module.__name__: module}):
            self.assertEqual(c.load_plan(Path("plan.json"), FREEZE), {"replay": True})
        module.load_plan.assert_called_once_with(Path("plan.json"), FREEZE)


if __name__ == "__main__":
    unittest.main()
