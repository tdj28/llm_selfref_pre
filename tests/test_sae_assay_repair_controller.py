"""Offline repair lifecycle tests. No credentials, network, or GPU are used."""
from copy import deepcopy
from datetime import timedelta
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

from experiments.sae_assay_repair import controller as c
from tests import test_sae_assay_controller as lifecycle

FREEZE, UTC, PUBLIC_KEY = lifecycle.FREEZE, lifecycle.UTC, lifecycle.PUBLIC_KEY
BUDGET = {"prior_total_usd": "13.07885980328333333333333333", "total_usd": 200,
          "repair_max_usd": 40, "cheap_max_usd": 2, "main_max_usd": 38,
          "new_paid_judge_calls": 0, "new_pro_calls": 0}


class FakeAPI(lifecycle.FakeAPI):
    def __init__(self, kind="cheap", clock=lambda: UTC):
        super().__init__()
        self.kind, self.clock, self.extra = kind, clock, []
        gpu, rate, memory = c.HARDWARE[kind]
        self.catalog.update(id=gpu, memory=memory, price={"secure": float(rate)})

    def inventory(self):
        return super().inventory() + self.extra

    def request(self, method, path, body=None):
        try:
            return super().request(method, path, body)
        finally:
            if method == "POST" and self.pod:
                self.pod.update(id="newowned1" if self.kind == "cheap" else "newmain1",
                                createdAt=self.clock().isoformat(), cost=self.catalog["price"]["secure"],
                                # Response shape from archived diagnostic receipts, not POST input.
                                gpu={"id": self.catalog["id"], "count": 1,
                                     "memory": self.catalog["memory"], "vcpuCount": 16})


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan_data = {"budget": deepcopy(BUDGET)}
        self.plan.write_text(json.dumps(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("test-only private material")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: deepcopy(self.plan_data))
        self.public = Mock()
        for target, value in (("experiments.sae_assay_repair.controller.ROOT", self.root),
                              ("experiments.sae_assay_repair.controller.load_plan", self.loader),
                              ("experiments.sae_assay_repair.controller.verify_public", self.public),
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
        self.api = FakeAPI(clock=lambda: self.current)
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
    test_barriers_are_observed_not_approved = lifecycle.ControllerTests.test_barriers_are_observed_not_approved
    test_stalled_worker_is_retrieved_before_termination = lifecycle.ControllerTests.test_stalled_worker_is_retrieved_before_termination
    test_preserved_approved_barrier_does_not_disable_stall_guard = lifecycle.ControllerTests.test_preserved_approved_barrier_does_not_disable_stall_guard
    test_low_disk_blocks_create_and_pull_without_mutating_remote = lifecycle.ControllerTests.test_low_disk_blocks_create_and_pull_without_mutating_remote
    test_lost_delete_response_can_be_confirmed_without_retry = lifecycle.ControllerTests.test_lost_delete_response_can_be_confirmed_without_retry
    test_uncertain_post_reconciles_exact_name_without_second_post = lifecycle.ControllerTests.test_uncertain_post_reconciles_exact_name_without_second_post

    def qualify_cheap(self, *, passed=True, exit_code=0, approve=True, close=True, elapsed=300):
        self.launched()
        self.ctrl.ledger.bind("worker-intent", {"script_sha256": "b" * 64, "seconds": 1200})
        files = {"cheap-qualification.json": json.dumps({"pass": passed}).encode(),
                 "controller-exit.json": json.dumps({"exit_code": exit_code}).encode()}

        def ssh(pod, command, **_kwargs):
            if c.frozen.SIGNAL_SCRIPT in shlex.split(command):
                return json.dumps({"verified": True, "action": command.rsplit(" ", 1)[1]}).encode()
            return json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()

        def run(argv, **_kwargs):
            self.assertEqual(argv[0], "rsync")
            for name, raw in files.items():
                (Path(argv[-1]) / name).write_bytes(raw)
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=run)
        self.current += timedelta(seconds=elapsed)
        self.ticks += elapsed
        if close:
            self.ctrl.terminate()
        if approve:
            (self.ctrl.out / "APPROVE-cheap").write_text(self.ctrl.plan_hash + "\n")

    def test_default_cli_is_unpaid_without_loading_plan_or_credentials(self):
        for action in ("launch", "status", "retrieve", "monitor", "terminate", "reconcile"):
            with patch.object(c, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
                with patch.object(c, "load_plan") as loader, patch.dict(os.environ, {}, clear=True):
                    c.main(["--plan", "missing", "--freeze", FREEZE, "--out", "missing",
                            "--kind", "main", "--action", action])
            api.assert_not_called()
            loader.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["network_calls"], 0)
            self.assertTrue(json.loads(output.getvalue())["dry_run"])

    def test_repair_loader_validates_sources_and_freeze_before_private_state(self):
        self.loader.assert_called_once_with(self.plan, FREEZE)
        self.loader.side_effect = ValueError("Source drift")
        with self.assertRaisesRegex(ValueError, "Source drift"):
            self.controller("main")
        self.assertFalse((self.ctrl.out / c.NAMESPACE / "main").exists())
        with self.assertRaisesRegex(ValueError, "Source drift"):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_plan_drift_after_construction_blocks_launch(self):
        self.plan.write_text("changed")
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_private_namespace_and_freeze_binding(self):
        self.assertEqual(self.ctrl.base, self.ctrl.out / "repair-controller/cheap")
        self.assertEqual(self.ctrl.ledger.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ctrl.base.stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.ctrl.out / "controller").exists())
        for row in self.ctrl.ledger.read():
            self.assertEqual(row["plan_sha256"], self.ctrl.plan_hash)
            self.assertEqual(row["freeze_commit"], FREEZE)
        with self.assertRaises(ValueError):
            c.Controller(self.plan, "b" * 40, self.ctrl.out, "cheap", self.api)

    def test_budget_rejects_missing_prior_reset_expansion_and_new_calls(self):
        bad = [{"prior_total_usd": "0.86461"}, {"prior_total_usd": 0}, {"prior_total_usd": "NaN"},
               {"prior_total_usd": 14}, {"total_usd": 201}, {"total_usd": 50}, {"repair_max_usd": 41},
               {"cheap_max_usd": 3}, {"main_max_usd": 39}, {"repair_max_usd": 39},
               {"new_paid_judge_calls": 1}, {"new_pro_calls": 1}, {"cheap_max_usd": True}]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(ValueError):
                c.checked_budget({"budget": {**BUDGET, **change}})
        for missing in ("prior_total_usd", "repair_max_usd", "cheap_max_usd", "main_max_usd", "total_usd"):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                c.checked_budget({"budget": {key: value for key, value in BUDGET.items() if key != missing}})
        self.assertEqual(c.checked_budget({"budget": BUDGET})["prior_total_usd"], c.PRIOR_TOTAL)
        self.assertLessEqual(c.PRIOR_TOTAL + 2 + 38, Decimal("53.08"))

    def test_pinned_payload_quotes_names_and_public_key_only(self):
        for kind in ("cheap", "main"):
            api = FakeAPI(kind)
            payload = c.create_payload(kind, c.PREFIX + kind + "-012345abcdef", PUBLIC_KEY)
            self.assertEqual(payload["env"], {"PUBLIC_KEY": PUBLIC_KEY})
            self.assertEqual(payload["image"], c.frozen.IMAGE)
            self.assertEqual(payload["gpu"]["id"], c.HARDWARE[kind][0])
            quoted = c.quote(api, kind)
            self.assertEqual(Decimal(quoted["hourly_rate_usd"]), c.HARDWARE[kind][1])
            self.assertEqual(Decimal(quoted["storage_hourly_usd"]), Decimal(".10"))
            api.catalog["price"]["secure"] += .01
            with self.assertRaises(ValueError):
                c.quote(api, kind)
        for name, key in ((c.frozen.PREFIX + "cheap-012345abcdef", PUBLIC_KEY),
                          (c.PREFIX + "cheap-012345abcdef", "private key"),
                          (c.PREFIX + "cheap-012345abcdef", PUBLIC_KEY + "\nexport EVIL=1")):
            with self.assertRaises(ValueError):
                c.create_payload("cheap", name, key)

    def test_launch_records_exact_one_create_and_all_prior_costs(self):
        self.api.extra = [{"id": "preexisting", "name": "unrelated"}]
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertRegex(intent["payload"]["name"], r"^codex-sae-repair-20260930-cheap-[0-9a-f]{12}$")
        self.assertEqual(set(intent["blocked"]), {"preexisting", c.frozen.BLOCKED})
        self.assertEqual(Decimal(intent["prior_total_usd"]), c.PRIOR_TOTAL)
        self.assertEqual(Decimal(intent["local_cap_usd"]), 2)
        self.assertEqual(c._utc(intent["deadline_utc"]), UTC + timedelta(minutes=20))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]), UTC + timedelta(minutes=30))
        self.public.assert_called_once_with(self.ctrl.plan_hash, "plan.json", FREEZE)
        with self.assertRaises(ValueError):
            self.controller().launch()
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)

    def test_blocked_inventory_id_cannot_be_registered_or_ssh_accessed(self):
        self.api.extra = [{"id": "newowned1", "name": "preexisting"}]
        with patch.object(self.ctrl, "start_worker") as worker, self.assertRaises(ValueError):
            self.ctrl.launch()
        worker.assert_not_called()
        self.assertIsNone(self.ctrl.event("created"))
        self.assertFalse(any(method == "DELETE" for method, _, _ in self.api.calls))
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)

    def test_unresolved_create_is_never_retried_and_reconcile_is_read_only(self):
        original = self.api.request

        def lost(method, path, body=None):
            if method == "POST":
                self.api.calls.append((method, path, body))
                raise RuntimeError("unknown result")
            return original(method, path, body)

        self.api.request = lost
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.ctrl.launch()
        with self.assertRaises(ValueError):
            self.controller().launch()
        with self.assertRaisesRegex(RuntimeError, "unresolved"):
            self.controller().reconcile()
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)

    def test_main_requires_cheap_not_old_diagnostic_approval(self):
        (self.ctrl.out / "APPROVE-cheap").write_text(self.ctrl.plan_hash)
        old = self.ctrl.out / "controller/cheap"
        old.mkdir(parents=True)
        (old / "events.jsonl").write_text("historical diagnostic")
        with self.assertRaises(ValueError):
            self.controller("main").launch()
        self.assertEqual(self.api.calls, [])

    def test_main_requires_passed_cheap_and_successful_exit(self):
        self.qualify_cheap(passed=False)
        api = FakeAPI("main")
        with self.assertRaisesRegex(ValueError, "did not pass"):
            self.controller("main", api).launch()
        self.assertEqual(api.calls, [])

    def test_main_requires_successful_exit_not_only_pass_field(self):
        self.qualify_cheap(exit_code=124)
        api = FakeAPI("main")
        with self.assertRaisesRegex(ValueError, "did not pass"):
            self.controller("main", api).launch()
        self.assertEqual(api.calls, [])

    def test_main_requires_deletion_and_approval(self):
        self.qualify_cheap(close=False, approve=False)
        api = FakeAPI("main")
        main = self.controller("main", api)
        with self.assertRaises(ValueError):
            main.launch()
        (self.ctrl.out / "APPROVE-cheap").write_text(self.ctrl.plan_hash)
        with self.assertRaises(ValueError):
            main.launch()
        self.ctrl.terminate()
        (self.ctrl.out / "APPROVE-cheap").write_text("wrong hash")
        with self.assertRaisesRegex(ValueError, "plan hash"):
            main.launch()
        self.assertEqual(api.calls, [])

    def test_main_rechecks_cheap_retrieval_hashes(self):
        self.qualify_cheap()
        receipt = c.strict_json((self.ctrl.base / "final-retrieval.json").read_bytes())
        (Path(receipt["data"]["directory"]) / "cheap-qualification.json").write_text('{"pass":false}')
        api = FakeAPI("main")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            self.controller("main", api).launch()
        self.assertEqual(api.calls, [])

    def test_main_requires_cheap_hard_timer_even_when_under_two_dollars(self):
        self.qualify_cheap(elapsed=1801)
        api = FakeAPI("main")
        with self.assertRaisesRegex(ValueError, "within its limits"):
            self.controller("main", api).launch()
        self.assertEqual(api.calls, [])

    def test_main_fresh_b200_cap_timer_and_cumulative_closure(self):
        self.qualify_cheap()
        cheap = Decimal(self.ctrl.event("closed")["data"]["compute_upper_bound_usd"])
        api = FakeAPI("main", clock=lambda: self.current)
        main = self.controller("main", api)
        with patch.object(main, "start_worker"):
            main.launch()
        intent = main.event("create-intent")["data"]
        self.assertEqual(Decimal(intent["prior_repair_usd"]), cheap)
        self.assertEqual(Decimal(intent["cumulative_ceiling_usd"]), c.PRIOR_TOTAL + cheap + 38)
        self.assertEqual(Decimal(intent["local_cap_usd"]), 38)
        self.assertRegex(api.pod["name"], r"^codex-sae-repair-20260930-main-[0-9a-f]{12}$")
        self.assertEqual(c._utc(intent["hard_deadline_utc"]) - self.current, timedelta(hours=3))
        self.assertEqual(c._utc(intent["deadline_utc"]) - self.current, timedelta(minutes=170))
        self.current += timedelta(hours=2)
        self.ticks += 7200
        main.cost_check(api.pod)
        closed = main.terminate()["data"]
        self.assertEqual(Decimal(closed["compute_upper_bound_usd"]), Decimal("13.78"))
        self.assertEqual(Decimal(closed["cumulative_upper_bound_usd"]), c.PRIOR_TOTAL + cheap + Decimal("13.78"))
        self.assertTrue(closed["within_limits"])

    def test_cost_check_counts_storage_and_reserves_retrieval_time(self):
        self.launched()
        self.current += timedelta(minutes=5)
        self.ticks += 300
        self.assertEqual(self.ctrl.cost_check(self.api.pod), Decimal(".07"))
        accounted = self.ctrl.ledger.read()[-1]["data"]
        self.assertEqual(Decimal(accounted["projected_usd"]), Decimal(".224"))
        self.current = UTC + timedelta(minutes=19)
        self.ticks = 1140
        with self.assertRaisesRegex(ValueError, "deadline"):
            self.ctrl.cost_check(self.api.pod, 60)

    def test_full_walltime_must_fit_lower_plan_budget_before_creation(self):
        self.plan_data["budget"].update(cheap_max_usd=.4)
        self.plan.write_text(json.dumps(self.plan_data))
        other_out = self.root / "lower-budget"
        controller = c.Controller(self.plan, FREEZE, other_out, "cheap", self.api,
                                  clock=lambda: self.current, monotonic=lambda: self.ticks)
        with self.assertRaisesRegex(ValueError, "not funded"):
            controller.launch()
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))

    def test_monitor_stops_and_retrieves_at_cheap_deadline(self):
        self.launched()
        actions = self.snapshots()
        self.current = UTC + timedelta(minutes=20)
        self.ticks = 1200
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {}})
        result = self.ctrl.monitor()
        self.assertEqual(result["id"], "closed")
        self.assertEqual(actions, ["stop", "stop"])
        self.assertTrue((self.ctrl.base / "final-retrieval.json").exists())
        self.assertTrue(self.api.deleted)

    def test_monotonic_elapsed_and_restart_cannot_reset_deadline(self):
        self.launched()
        self.ticks = 1140
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod, 60)
        restarted = self.controller()
        self.ticks += 1
        with self.assertRaises(ValueError):
            restarted.cost_check(self.api.pod, 60)
        self.assertGreaterEqual(Decimal(restarted.ledger.read()[-1]["data"]["elapsed_seconds"]), 1141)

    def test_backward_clock_stops_work(self):
        self.launched()
        self.current += timedelta(seconds=120)
        self.ctrl.cost_check(self.api.pod)
        self.current = UTC
        with self.assertRaisesRegex(ValueError, "clock moved backward"):
            self.ctrl.cost_check(self.api.pod)

    def test_runtime_billing_hardware_and_ssh_ownership_fail_closed(self):
        self.launched()
        self.assertEqual(set(self.api.pod["gpu"]), {"id", "count", "memory", "vcpuCount"})
        self.ctrl.cost_check(self.api.pod)
        for change in ({"cost": None}, {"cost": 0}, {"cost": .75}, {"image": "other"},
                       {"cloud": "COMMUNITY"}, {"id": "preexisting"}, {"name": "preexisting"},
                       {"gpu": None}, {"gpu": []},
                       {"gpu": {"id": c.HARDWARE["main"][0], "count": 1}},
                       {"gpu": {"id": c.HARDWARE["cheap"][0], "count": 2}},
                       {"gpu": {"id": c.HARDWARE["cheap"][0], "count": True}}):
            with self.subTest(change=change), patch.dict(self.api.pod, change), self.assertRaises(ValueError):
                self.ctrl.cost_check(self.api.pod)
        with self.assertRaises(ValueError):
            self.ctrl._ssh({**self.api.pod, "id": "preexisting"}, "mutate")
        self.ctrl.run.assert_not_called()

    def test_worker_commands_shell_syntax_and_source_validation(self):
        for kind in ("cheap", "main"):
            script = c.worker_script(kind, "data/repair plan.json", FREEZE, UTC.isoformat())
            subprocess.run(["/bin/bash", "-n"], input=script.encode(), check=True, capture_output=True)
            self.assertIn("experiments.sae_assay_repair." + ("runner" if kind == "main" else "qualify"), script)
            self.assertIn("from experiments.sae_assay_repair.protocol import load_plan", script)
            self.assertIn("python3 -m venv --system-site-packages", script)
            self.assertIn("/venv/bin/python -m pip install -r experiments/sae_assay_diagnostic/requirements-gpu.txt", script)
            self.assertIn("pip freeze --all", script)
            self.assertNotIn("--stage", script)
            self.assertNotIn("APPROVE", script)
            self.assertNotIn("API_KEY", script)
            args = shlex.split(script.splitlines()[-1])
            if kind == "main":
                for flag in ("--plan", "--freeze", "--out", "--cache", "--deadline-utc"):
                    self.assertIn(flag, args)
            else:
                self.assertEqual(args[-2:], ["--out", c.frozen.REMOTE + "/out/cheap-qualification.json"])
        for path in ("../old/plan.json", "/plan.json", ""):
            with self.assertRaises(ValueError):
                c.worker_script("main", path, FREEZE, UTC.isoformat())

    def test_exit_trap_records_bootstrap_failure(self):
        with patch.object(c.frozen, "REMOTE", str(self.root / "remote")):
            script = c.worker_script("cheap", "plan.json", FREEZE, UTC.isoformat())
        setup = "\n".join(script.splitlines()[:4]) + "\nexit 3\n"
        result = subprocess.run(["/bin/bash"], input=setup.encode(), capture_output=True)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads((self.root / "remote/out/controller-exit.json").read_text()), {"exit_code": 3})

    def test_worker_dispatch_transfers_only_hf_via_stdin_and_scrubs_environment(self):
        self.launched()
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        self.ctrl.run = Mock(side_effect=run)
        self.ctrl.start_worker()
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]["input"], b"export HF_TOKEN=hf_dummy_test_only\n")
        self.assertIn("chmod 600", calls[1][0][-1])
        self.assertIn("timeout --signal=TERM --kill-after=30s 1170s env -i", calls[2][0][-1])
        for argv, kwargs in calls:
            self.assertIn("ForwardAgent=no", argv)
            self.assertNotIn("SendEnv", " ".join(argv))
            self.assertEqual(set(kwargs["env"]), {"PATH", "HOME", "LANG"})
            for secret in ("hf_dummy_test_only", "rp_dummy_test_only", "openai_dummy_test_only", "anthropic_dummy_test_only"):
                self.assertNotIn(secret, " ".join(argv))
                self.assertNotIn(secret, self.ctrl.ledger.path.read_text())
        self.assertEqual(self.ctrl.event("worker-intent")["data"]["freeze_commit"], FREEZE)
        self.assertEqual(self.ctrl.event("worker-intent")["data"]["plan_sha256"], self.ctrl.plan_hash)
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_ssh_readiness_retries_do_not_duplicate_worker(self):
        self.launched()
        self.ctrl._ssh = Mock(side_effect=[RuntimeError("not ready"), b"", b"", b""])
        self.ctrl.start_worker()
        self.ctrl.sleep.assert_called_once_with(15)
        self.assertEqual(len([row for row in self.ctrl.ledger.read() if row["id"] == "worker-intent"]), 1)

    def test_startup_failure_retrieves_and_deletes_only_new_pod(self):
        with patch.object(self.ctrl, "start_worker", side_effect=TimeoutError("startup")):
            with self.assertRaises(TimeoutError):
                self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertTrue(self.ctrl.event("closed")["data"]["within_limits"])
        self.assertEqual(next(r["data"] for r in self.ctrl.ledger.read() if r["id"].startswith("launch-failed:")),
                         {"error_type": "TimeoutError"})
        self.assertEqual([path for method, path, _ in self.api.calls if method == "DELETE"], ["/pods/newowned1"])

    def test_unknown_final_cost_preserves_closure_but_blocks_further_work(self):
        self.launched()
        self.api.pod["cost"] = None
        closed = self.ctrl.terminate()["data"]
        self.assertTrue(self.api.deleted)
        self.assertIsNone(closed["compute_upper_bound_usd"])
        self.assertFalse(closed["within_limits"])
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_monitor_keeps_frozen_sixty_second_poll_and_barrier_names(self):
        self.assertEqual(c.frozen.WAITING, ("WAITING-qualification.json", "WAITING-target-first5.json"))
        self.assertEqual(c.WAITING, (*c.frozen.WAITING, "WAITING-repair-nonzero.json"))
        self.launched()
        self.current = UTC + timedelta(minutes=15)
        self.ticks = 900
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {}})
        self.ctrl.retrieve = Mock()
        self.ctrl.cost_check = Mock(wraps=self.ctrl.cost_check)
        self.ctrl.sleep = Mock(side_effect=InterruptedError("end test"))
        with patch("sys.stdout", new_callable=io.StringIO), self.assertRaises(InterruptedError):
            self.ctrl.monitor()
        self.ctrl.cost_check.assert_called_once_with(self.api.pod, 60)
        self.ctrl.sleep.assert_called_once_with(60)

    def test_status_reads_all_three_barriers_and_preserves_progress_and_approvals(self):
        self.launched()
        remote = self.root / "mock-remote-out"
        remote.mkdir()
        for name in c.WAITING:
            (remote / name).write_text(json.dumps({"plan_sha256": self.ctrl.plan_hash, "rows": 84}))
        (remote / "controller-exit.json").write_text('{"exit_code":0}')
        (remote / "APPROVE-repair-nonzero").write_text(self.ctrl.plan_hash + "\n")

        def ssh(pod, command, **_kwargs):
            self.assertEqual(pod["id"], self.ctrl.owned()["id"])
            argv = shlex.split(command)
            self.assertEqual(argv, ["python3", "-c", c.STATUS_SCRIPT])
            with patch("pathlib.Path", return_value=remote), patch("sys.stdout", new_callable=io.StringIO) as output:
                exec(compile(argv[2], "repair-status", "exec"), {})
            return output.getvalue().encode()

        self.ctrl._ssh = Mock(side_effect=ssh)
        state = self.ctrl.status()
        for name in c.WAITING:
            self.assertEqual(state["files"][name]["plan_sha256"], self.ctrl.plan_hash)
            self.assertIn(name, state["files"]["_progress"])
        self.assertEqual(state["files"]["controller-exit.json"], {"exit_code": 0})
        self.assertEqual(state["files"]["_approvals"], {"APPROVE-repair-nonzero": self.ctrl.plan_hash})
        self.assertNotIn("WAITING-repair-nonzero.json", c.frozen.STATUS_SCRIPT)

    def test_nonzero_barrier_requires_matching_parent_approval_and_never_auto_approves(self):
        self.launched()
        for approval in (None, "wrong-plan", self.ctrl.plan_hash):
            with self.subTest(approval=approval):
                approvals = {} if approval is None else {"APPROVE-repair-nonzero": approval}
                self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {
                    "WAITING-repair-nonzero.json": {"plan_sha256": self.ctrl.plan_hash, "rows": 84},
                    "_approvals": approvals, "_progress": {"rows/nonzero.json": [1, 1]}}})
                self.ctrl.retrieve = Mock()
                self.ctrl.sleep = Mock(side_effect=InterruptedError("end test"))
                with patch("sys.stdout", new_callable=io.StringIO) as output, self.assertRaises(InterruptedError):
                    self.ctrl.monitor()
                self.assertEqual("WAITING:" in output.getvalue(), approval != self.ctrl.plan_hash)
                self.ctrl.retrieve.assert_called_once()
                self.ctrl.sleep.assert_called_once_with(60)
                self.assertFalse(list(self.root.rglob("APPROVE*")))

    def test_approved_nonzero_barrier_does_not_disable_stall_guard(self):
        self.launched()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {
            "WAITING-repair-nonzero.json": {"plan_sha256": self.ctrl.plan_hash, "rows": 84},
            "_approvals": {"APPROVE-repair-nonzero": self.ctrl.plan_hash},
            "_progress": {"rows/nonzero.json": [1, 1]}}})
        self.ctrl.cost_check, self.ctrl.retrieve, self.ctrl.quiesce = Mock(), Mock(), Mock()
        self.ctrl.terminate = Mock(return_value="closed")
        with patch.object(c.time, "monotonic", side_effect=[0, 0, 0, 0, 901]):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.quiesce.assert_called_once()
        self.ctrl.terminate.assert_called_once()


class LoaderTests(unittest.TestCase):
    def test_loader_delegates_to_repair_protocol_not_diagnostic(self):
        with patch("experiments.sae_assay_repair.protocol.load_plan", return_value={"repair": True}) as load:
            self.assertEqual(c.load_plan(Path("plan.json"), FREEZE), {"repair": True})
            load.assert_called_once_with(Path("plan.json"), FREEZE)


if __name__ == "__main__":
    unittest.main()
