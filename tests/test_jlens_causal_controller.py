"""Offline lifecycle proof: synthetic local ledgers, fake API, no paid actions."""
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

import pytest

from experiments.jlens_causal_report import controller as c
from experiments.sae_assay_exposure_lifecycle_a1 import controller as corrected
from tests import test_sae_assay_controller as prior

FREEZE, UTC, PUBLIC_KEY = prior.FREEZE, prior.UTC, prior.PUBLIC_KEY
RELATIVE = "data/jlens_causal_report/stage_a_plan_20261001/PLAN.json"


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in controller tests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


class FakeAPI(prior.FakeAPI):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.extra = [{"id": "preexisting-untouchable", "name": c.PREFIX + "main-012345abcdef"}]

    def inventory(self):
        return super().inventory() + self.extra

    def request(self, method, path, body=None):
        try:
            return super().request(method, path, body)
        finally:
            if method == "POST" and self.pod:
                self.deleted = False
                self.pod.update(createdAt=self.clock().isoformat(), cost=self.catalog["price"]["secure"],
                                gpu={"id": self.catalog["id"], "count": 1, "memory": self.catalog["memory"]})


class ControllerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.out = self.root / "out/jlens-causal-20261001"
        self.plan = self.root / RELATIVE
        self.plan.parent.mkdir(parents=True)
        self.plan_data = {"budget": deepcopy(c.BUDGET), "stage": "A",
                          "rows": [{"id": "discovery-" + str(i), "split": "discovery"} for i in range(5)]}
        self.plan.write_text(json.dumps(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("synthetic not a private key")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: json.loads(self.plan.read_text()))
        self.public, self.ignored = Mock(), Mock()
        for target, value in (("experiments.jlens_causal_report.controller.ROOT", self.root),
                              ("experiments.jlens_causal_report.controller.OWNED_OUT", self.out),
                              ("experiments.jlens_causal_report.controller.load_plan", self.loader),
                              ("experiments.jlens_causal_report.controller._require_ignored", self.ignored),
                              ("experiments.sae_assay_diagnostic.controller.KEY", self.key),
                              ("experiments.sae_assay_diagnostic.controller.verify_public", self.public)):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {"HF_TOKEN": "hf_placeholder_only"}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = FakeAPI(lambda: self.current)
        self.ctrl = self.controller()
        self.approval = self.out / "user-approval.json"
        self.approval.write_text(json.dumps(c.approval_record(self.ctrl.plan_hash, FREEZE, c.BUDGET,
                                                            "synthetic-test-confirmation")))

    def controller(self, kind="cheap", **kwargs):
        defaults = {"launch": True, "approved_new_cap_usd": "15",
                    "approval_ref": "synthetic-test-confirmation",
                    "approval_file": self.out / "user-approval.json"}
        defaults.update(kwargs)
        ctrl = c.Controller(self.plan, FREEZE, self.out, kind, self.api,
                            clock=lambda: self.current, sleep=Mock(), monotonic=lambda: self.ticks,
                            run=Mock(side_effect=AssertionError("Unexpected subprocess")), **defaults)
        ctrl.disk_check = Mock()
        return ctrl

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)
        self.ticks += seconds

    launched = prior.ControllerTests.launched
    test_unknown_pod_never_accessed = prior.ControllerTests.test_unknown_pod_never_accessed
    test_retrieval_pauses_resumes_and_never_approves = prior.ControllerTests.test_retrieval_pauses_resumes_and_never_approves
    test_retrieval_failure_always_resumes = prior.ControllerTests.test_retrieval_failure_always_resumes
    test_corrupt_snapshot_blocks_delete = prior.ControllerTests.test_corrupt_snapshot_blocks_delete
    test_corruption_after_retrieval_blocks_delete = prior.ControllerTests.test_corruption_after_retrieval_blocks_delete
    test_retrieve_before_delete_and_verified_closure = prior.ControllerTests.test_retrieve_before_delete_and_verified_closure
    test_no_worker_startup_failure_can_be_closed = prior.ControllerTests.test_no_worker_startup_failure_can_be_closed
    test_uncertain_post_reconciles_exact_name_without_second_post = prior.ControllerTests.test_uncertain_post_reconciles_exact_name_without_second_post

    def snapshots(self, *, fail=False, corrupt=False, files=None):
        binding = {"worker_id": "c" * 32, "pod_id": self.ctrl.owned()["id"],
                   "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE}
        self.ctrl.ledger.bind("worker-intent", {**binding, "script_sha256": "b" * 64, "seconds": 120})
        if files is None:
            files = {"rows/row1.json": b'{"id":"row1"}\n', "controller.log": b"progress\n"}
        actions = []

        def ssh(_pod, command, **kwargs):
            if corrected.WORKER_SIGNAL_SCRIPT in shlex.split(command):
                action = json.loads(kwargs["data"])["action"]
                actions.append(action)
                result = {"action": action, "verified": True, "binding": binding,
                          "stopped": action == "stop", "dispatch_fenced": action == "stop",
                          "owned_group_quiescent": action == "stop",
                          "proof_scope": "recorded-worker-group-and-session"}
                if action == "stop":
                    files["controller-stopped.json"] = json.dumps(result).encode()
                return json.dumps(result).encode()
            return json.dumps({name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()

        def run(argv, **kwargs):
            self.assertEqual(argv[0], "rsync")
            for name, raw in files.items():
                path = Path(argv[-1]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw + (b"corrupt" if corrupt else b""))
            return subprocess.CompletedProcess(argv, int(fail), b"", b"")

        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=run)
        return actions

    def complete_cheap(self):
        self.launched()
        self.snapshots(files={"DONE-all.json": b'{"pass":true,"scope":"tiny_cuda_exact_path"}',
                              "tests.xml": b'<testsuites tests="10" failures="0"/>',
                              "controller-exit.json": b'{"exit_code":0}'})
        self.advance(1800)
        self.ctrl.terminate()

    def main_controller(self):
        self.api.catalog.update(id="NVIDIA B200", memory=180, price={"secure": 6.79})
        return self.controller("main")

    def test_inheritance_preserves_audited_lifecycle_and_worker_identity(self):
        self.assertIs(c.Controller.signal_worker, corrected.Controller.signal_worker)
        for name in ("terminate", "retrieve", "_snapshot", "_exclusive", "owned",
                     "_ssh", "reconcile_create", "close_until_verified"):
            self.assertIs(getattr(c.Controller, name), getattr(c.ensemble.Controller, name))

    def test_creation_requires_all_explicit_authority_before_network(self):
        for kwargs in ({"launch": False}, {"approved_new_cap_usd": None},
                       {"approved_new_cap_usd": "130"}, {"approved_new_cap_usd": "NaN"},
                       {"approval_ref": None}, {"approval_file": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.controller(**kwargs).launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_not_called()

    def test_confirmation_record_is_exact_and_bound_not_agent_review(self):
        original = json.loads(self.approval.read_text())
        for changes in ({"user_confirmed": False}, {"user_confirmed": 1}, {"phase": "B"},
                        {"approved_new_cap_usd": "130"}, {"plan_sha256": "b"*64},
                        {"budget_sha256": "c"*64}, {"freeze_commit": "b"*40},
                        {"approval_ref": "agent-review"}, {"pro_approved": True}):
            self.approval.write_text(json.dumps({**original, **changes}))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_approval_symlink_traversal_and_nonignored_files_fail(self):
        linked = self.out / "linked.json"
        linked.symlink_to(self.approval)
        for path in (linked, self.root / "approval.json", self.out / "../user-approval.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.controller(approval_file=path).launch()
        self.ignored.side_effect = ValueError("not ignored")
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_creation_records_approval_before_exactly_one_post(self):
        self.launched()
        authority, intent = self.ctrl.event("creation-approval"), self.ctrl.event("create-intent")
        self.assertLess(authority["seq"], intent["seq"])
        self.assertEqual(intent["data"]["approval_sha256"], authority["sha256"])
        self.assertIn("not Pro review", authority["data"]["authority"])
        self.assertEqual(intent["data"]["prior_total_usd"], "69.130940")
        self.assertEqual(c._utc(intent["data"]["deadline_utc"]), UTC + timedelta(seconds=1200))
        self.assertEqual(c._utc(intent["data"]["hard_deadline_utc"]), UTC + timedelta(seconds=1800))
        self.assertIn("preexisting-untouchable", intent["data"]["blocked"])
        self.assertTrue(self.api.pod["name"].startswith(c.PREFIX + "cheap-"))
        self.public.assert_called_once_with(self.ctrl.plan_hash, RELATIVE, FREEZE)
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_canonical_root_and_ledger_binding_prevent_spending_reset(self):
        with self.assertRaises(ValueError):
            c.Controller(self.plan, FREEZE, self.root / "alternate", "cheap", self.api)
        self.assertEqual(self.ctrl.base.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.ctrl.ledger.path.stat().st_mode & 0o777, 0o600)
        self.plan.write_text(json.dumps({**self.plan_data, "changed": True}))
        with self.assertRaises(ValueError):
            self.controller()
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_main_requires_real_cheap_receipt_and_carries_full_cost(self):
        main = self.main_controller()
        with self.assertRaises(ValueError, msg="must not manufacture absent cheap evidence"):
            main.launch()
        self.assertEqual(self.api.calls, [])
        self.api.catalog.update(id="NVIDIA GeForce RTX 4090", memory=24, price={"secure": .74})
        self.complete_cheap()
        self.assertEqual(main.cheap_receipt(), Decimal("0.42"))
        self.ctrl = self.main_controller()
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertEqual(Decimal(intent["prior_new_usd"]), Decimal("0.42"))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]) - self.current, timedelta(seconds=7200))
        self.assertEqual(c._utc(intent["deadline_utc"]) - self.current, timedelta(seconds=6600))
        self.advance(7200)
        closed = self.ctrl.terminate()["data"]
        self.assertTrue(closed["within_limits"])
        self.assertEqual(Decimal(closed["compute_upper_bound_usd"]), Decimal("13.78"))
        self.assertEqual(Decimal(closed["cumulative_upper_bound_usd"]), Decimal("83.330940"))

    def test_cheap_receipt_tampering_blocks_main(self):
        self.complete_cheap()
        main = self.main_controller()
        main.cheap_receipt()
        receipt = json.loads((self.ctrl.base / "final-retrieval.json").read_text())
        (Path(receipt["data"]["directory"]) / "tests.xml").write_text("changed")
        before = len(self.api.calls)
        with self.assertRaises(ValueError):
            main.launch()
        self.assertEqual(len(self.api.calls), before)

    def test_runtime_hardware_billing_storage_and_clock_drift(self):
        self.launched()
        self.ctrl.cost_check(self.api.pod)
        for changes in ({"id": "preexisting-untouchable"}, {"cost": None}, {"cost": .75},
                        {"disk": 51}, {"mounts": {"persistent": {"size": 251, "path": "/workspace"}}},
                        {"gpu": {"id": "NVIDIA B200", "count": 1, "memory": 180}},
                        {"gpu": {"id": "NVIDIA GeForce RTX 4090", "count": True, "memory": 24}}):
            with self.subTest(changes=changes), patch.dict(self.api.pod, changes), self.assertRaises(ValueError):
                self.ctrl.cost_check(self.api.pod)
        self.advance(1140)
        with self.assertRaises(ValueError, msg="600-second retrieval reserve must remain"):
            self.ctrl.cost_check(self.api.pod)
        self.current -= timedelta(seconds=1)
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod)

    def test_restart_does_not_reset_elapsed_or_permit_recreation(self):
        self.launched()
        self.advance(500)
        self.ctrl.cost_check(self.api.pod)
        self.ticks = 0
        restarted = self.controller()
        self.assertGreaterEqual(restarted._elapsed(restarted.event("create-intent")["data"]), 500)
        with self.assertRaises(ValueError):
            restarted.launch()

    def test_stalls_ignore_log_churn_and_survive_restart(self):
        self.launched()
        self.ctrl._check_progress({"_progress": {"controller.log": [1, 1]}})
        self.advance(1799)
        self.ctrl._check_progress({"_progress": {"controller.log": [99, 99]}})
        self.advance(1)
        with self.assertRaisesRegex(ValueError, "stalled"):
            self.ctrl._check_progress({"_progress": {"controller.log": [100, 100]}})
        files = {"_progress": {"rows/a.json": [1, 1]}}
        self.ctrl._check_progress(files)
        self.advance(900)
        restarted = self.controller()
        with self.assertRaisesRegex(ValueError, "stalled"):
            restarted._check_progress({**files, "WAITING-first-five.json": {}})
        with self.assertRaisesRegex(ValueError, "disappeared"):
            restarted._check_progress({"_progress": {}})

    def test_worker_dispatch_uses_corrected_identity_and_no_retry(self):
        self.launched()
        self.ctrl._ssh = Mock(return_value=b"")
        self.ctrl.start_worker()
        command = self.ctrl._ssh.call_args.args[1]
        self.assertIn("CODEX_EXPOSURE_WORKER_ID", command)
        self.assertIn("worker-closing.json", command)
        self.assertIn("JLENS_TEST_CUDA=1", command)
        self.assertNotIn("hf_placeholder_only", command)
        self.assertIn("plan_sha256", self.ctrl.event("worker-intent")["data"])
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_dispatch_failure_runs_owned_cleanup_without_second_create(self):
        self.ctrl.start_worker = Mock(side_effect=RuntimeError("synthetic dispatch failure"))
        self.ctrl.close_until_verified = Mock(return_value="closed")
        with self.assertRaises(RuntimeError):
            self.ctrl.launch()
        self.ctrl.close_until_verified.assert_called_once()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)
        self.assertTrue(any(r["id"].startswith("launch-failed:") for r in self.ctrl.ledger.read()))

    def test_lost_delete_response_only_reconciles_never_repeats_delete(self):
        self.launched()
        self.snapshots()
        request = self.api.request
        def lost(method, path, body=None):
            result = request(method, path, body)
            if method == "DELETE":
                raise RuntimeError("lost DELETE receipt")
            return result
        self.api.request = lost
        with self.assertRaises(RuntimeError):
            self.ctrl.terminate()
        closed = self.ctrl.terminate()
        self.assertEqual(closed["data"]["get_status"], 404)
        self.assertEqual(sum(m == "DELETE" for m, _, _ in self.api.calls), 1)
        self.assertFalse(any("preexisting-untouchable" in path for _, path, _ in self.api.calls))

    def barrier_snapshot(self, name, rows):
        barrier = {"barrier": name, "rows": rows, "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE}
        directory = self.ctrl.base / "retrievals" / name
        directory.mkdir(parents=True)
        filename = "WAITING-" + name + ".json"
        (directory / filename).write_text(json.dumps(barrier))
        (directory / "receipts.jsonl").write_text(json.dumps({
            "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE}) + "\n")
        (directory / "rows").mkdir()
        (directory / "rows/qualification-live.json").write_text('{"synthetic":true}')
        if name == "first-five":
            for row in self.plan_data["rows"]:
                (directory / "rows" / (row["id"] + ".json")).write_text(json.dumps({"clean": {
                    "first": {"forward_and_readout_seconds": .1},
                    "second": {"forward_and_readout_seconds": .1}}}))
            (directory / "throughput-gate.json").write_text(json.dumps({
                "pass": True, "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE,
                "observed_forwards": 10, "planned_forwards": 736, "overhead_factor": 2,
                "reserve_seconds": 900, "mean_seconds": .1, "predicted_remaining_seconds": 145.2}))
        receipt = self.ctrl.record("retrieval", {"pod_id": self.ctrl.owned()["id"],
            "directory": str(directory), "artifacts": {
                p.relative_to(directory).as_posix(): c.sha(p) for p in directory.rglob("*") if p.is_file()}})
        return receipt, {"pod": self.api.pod, "files": {filename: barrier, "_approvals": {}}}

    def prepare_main_barrier(self):
        self.ctrl = self.main_controller()
        self.ctrl.cheap_receipt = Mock(return_value=Decimal(".42"))
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": self.current.isoformat()})
        self.ctrl._ssh = Mock(return_value=b"")

    def test_barrier_requires_hash_snapshot_passing_audit_and_qualification_order(self):
        self.prepare_main_barrier()
        receipt, state = self.barrier_snapshot("qualification", 1)
        self.ctrl.status = Mock(return_value=state)
        with patch.object(c, "audit", return_value={"pass": False}):
            with self.assertRaises(ValueError):
                self.ctrl.approve("qualification", self.ctrl.plan_hash)
        self.ctrl._ssh.assert_not_called()
        with patch.object(c, "audit", return_value={"pass": True, "rows": 1}) as audit:
            self.ctrl.approve("qualification", self.ctrl.plan_hash)
            audit.assert_called_once_with(Path(receipt["data"]["directory"]), self.ctrl.plan, partial=True)
        receipt, state = self.barrier_snapshot("first-five", 6)
        self.ctrl.status.return_value = state
        with patch.object(c, "audit", return_value={"pass": True, "rows": 6}):
            with self.assertRaises(ValueError):
                self.ctrl.approve("first-five", self.ctrl.plan_hash)
            state["files"]["_approvals"]["APPROVE-qualification"] = self.ctrl.plan_hash
            self.ctrl.approve("first-five", self.ctrl.plan_hash)
        self.assertIsNotNone(self.ctrl.event("approved:first-five"))

    def test_monitor_audits_without_autoapproving_and_cleans_up_on_audit_failure(self):
        self.prepare_main_barrier()
        receipt, state = self.barrier_snapshot("qualification", 1)
        self.ctrl.status = Mock(return_value=state)
        self.ctrl.retrieve = Mock(return_value=receipt)
        self.ctrl.approve = Mock()
        self.ctrl.sleep = Mock(side_effect=InterruptedError("end one iteration"))
        with patch.object(c, "audit", return_value={"pass": True}), patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(InterruptedError):
                self.ctrl.monitor()
        self.ctrl.approve.assert_not_called()
        self.ctrl.close_until_verified = Mock(return_value="closed")
        with patch.object(c, "audit", return_value={"pass": False}):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.close_until_verified.assert_called_once()

    def test_main_startup_snapshot_does_not_require_nonexistent_runtime_rows(self):
        self.prepare_main_barrier()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {
            "_progress": {"controller.log": [100, 1]}}})
        self.ctrl.retrieve = Mock(return_value={"data": {"artifacts": {"controller.log": "unused"}}})
        self.ctrl.sleep = Mock(side_effect=InterruptedError("one startup iteration"))
        with patch.object(c, "audit") as audit, self.assertRaises(InterruptedError):
            self.ctrl.monitor()
        audit.assert_not_called()

    def test_barrier_rejects_empty_audit_and_runtime_freeze_drift(self):
        self.prepare_main_barrier()
        receipt, state = self.barrier_snapshot("qualification", 1)
        self.ctrl.status = Mock(return_value=state)
        with patch.object(c, "audit", return_value={"pass": True, "rows": 0}):
            with self.assertRaises(ValueError):
                self.ctrl.approve("qualification", self.ctrl.plan_hash)
        self.ctrl._ssh.assert_not_called()
        path = Path(receipt["data"]["directory"]) / "receipts.jsonl"
        path.write_text(json.dumps({"plan_sha256": self.ctrl.plan_hash, "freeze_commit": "b"*40}) + "\n")
        receipt["data"]["artifacts"]["receipts.jsonl"] = c.sha(path)
        forged = self.ctrl.record("retrieval", receipt["data"])
        with patch.object(c, "audit") as audit, self.assertRaisesRegex(ValueError, "plan/freeze"):
            self.ctrl._audit_receipt(forged)
        audit.assert_not_called()

    def test_cleanup_requires_no_fresh_creation_confirmation(self):
        self.launched()
        self.approval.unlink()
        self.ctrl.launch_enabled = False
        self.ctrl.terminate()
        self.assertTrue(self.api.deleted)

    def test_unknown_final_cost_does_not_claim_budget_compliance(self):
        self.launched()
        self.api.pod["cost"] = None
        result = self.ctrl.terminate()["data"]
        self.assertTrue(self.api.deleted)
        self.assertEqual(result["get_status"], 404)
        self.assertIsNone(result["compute_upper_bound_usd"])
        self.assertFalse(result["within_limits"])

    def test_monitor_unexpected_audit_failure_does_not_abandon_owned_pod(self):
        self.prepare_main_barrier()
        receipt, state = self.barrier_snapshot("qualification", 1)
        self.ctrl.status = Mock(return_value=state)
        self.ctrl.retrieve = Mock(return_value=receipt)
        self.ctrl.close_until_verified = Mock(return_value="closed")
        with patch.object(c, "audit", side_effect=AssertionError("unexpected numeric assertion")):
            self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.close_until_verified.assert_called_once()

    def test_throughput_gate_is_plan_bound_and_rechecks_remaining_time(self):
        self.prepare_main_barrier()
        receipt, _ = self.barrier_snapshot("first-five", 6)
        gate_path = Path(receipt["data"]["directory"]) / "throughput-gate.json"
        original = json.loads(gate_path.read_text())
        self.ctrl._throughput_gate(receipt)
        for change in ({"pass": False}, {"plan_sha256": "b"*64}, {"freeze_commit": "b"*40},
                       {"observed_forwards": 9}, {"planned_forwards": 738}, {"overhead_factor": 1},
                       {"reserve_seconds": 899}, {"mean_seconds": 0}, {"mean_seconds": .01},
                       {"predicted_remaining_seconds": 14.52}):
            gate_path.write_text(json.dumps({**original, **change}))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ctrl._throughput_gate(receipt)
        gate_path.write_text(json.dumps(original))
        self.advance(5600)
        with self.assertRaisesRegex(ValueError, "remaining worker deadline"):
            self.ctrl._throughput_gate(receipt)

    def test_full_final_audit_precedes_delete_even_for_negative_scientific_result(self):
        self.prepare_main_barrier()
        files = {"receipts.jsonl": (json.dumps({"plan_sha256": self.ctrl.plan_hash,
                    "freeze_commit": FREEZE}) + "\n").encode(),
                 "DONE-all.json": json.dumps({"pass": True, "qualification_pass": False,
                    "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE, "rows": 78}).encode()}
        self.snapshots(files=files)
        report = {"pass": True, "rows": 78, "gates": {"pass": False}}
        request = self.api.request
        def verify_order(method, path, body=None):
            if method == "DELETE":
                event = self.ctrl.event("final-scientific-audit")["data"]
                self.assertTrue(event["structural_pass"])
                self.assertFalse(event["qualification_pass"])
            return request(method, path, body)
        self.api.request = verify_order
        with patch.object(c, "audit", return_value=report) as audit:
            self.ctrl.terminate()
        self.assertEqual(audit.call_args.kwargs, {"partial": False})
        self.assertTrue(self.api.deleted)

    def test_failed_full_scientific_audit_retains_evidence_but_still_cleans_up(self):
        self.prepare_main_barrier()
        self.snapshots(files={"receipts.jsonl": (json.dumps({"plan_sha256": self.ctrl.plan_hash,
                              "freeze_commit": FREEZE}) + "\n").encode(),
                              "controller-exit.json": b'{"exit_code":1}'})
        with patch.object(c, "audit", side_effect=ValueError("synthetic incomplete inventory")) as audit:
            self.ctrl.terminate()
        audit.assert_called_once()
        self.assertFalse(audit.call_args.kwargs["partial"])
        self.assertEqual(self.ctrl.event("final-scientific-audit")["data"]["status"], "failed")
        self.assertTrue((self.ctrl.base / "final-retrieval.json").exists())
        self.assertTrue(self.api.deleted)

    def test_cli_default_preflight_never_constructs_api_or_approval(self):
        with patch.object(c.base, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
            c.main(["--plan", str(self.plan), "--freeze", FREEZE, "--kind", "main"])
        api.assert_not_called()
        self.public.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertEqual(result["network_calls"], 0)
        self.assertFalse(result["creation_authorized"])
        self.assertEqual(result["maximum_combined_usd"], "14.20")


def test_parent_budget_is_exact_not_a_controller_default():
    assert c.checked_budget(c.protocol.build_plan()) == c.BUDGET
    for field in c.BUDGET:
        incomplete = {key: value for key, value in c.BUDGET.items() if key != field}
        with pytest.raises(ValueError):
            c.checked_budget({"budget": incomplete})
    for field, value in [("new_cap_usd", "130"), ("prior_usd", "0"), ("total_usd", "201"),
                         ("new_pro_calls", 1), ("external_judge_calls", 1), ("main_seconds", 7201),
                         ("cheap_seconds", 1801), ("reserve_seconds", 599), ("new_pro_calls", False)]:
        with pytest.raises(ValueError):
            c.checked_budget({"budget": {**c.BUDGET, field: value}})


@pytest.mark.parametrize("kind", ["cheap", "main"])
def test_worker_exact_freeze_runtime_contract_and_shell_syntax(kind):
    script = c.worker_script(kind, RELATIVE, FREEZE, UTC.isoformat())
    syntax = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    assert "git checkout --detach " + FREEZE in script
    assert "experiments.jlens_causal_report.protocol import load_plan" in script
    assert "APPROVE" not in script and "RUNPOD_API_KEY" not in script
    if kind == "cheap":
        for suffix in ("operators", "backend", "protocol"):
            assert f"tests/test_jlens_causal_{suffix}.py" in script
        assert "JLENS_TEST_CUDA=1" in script
        assert "torch.cuda.is_available()" in script
        for suffix in ("runner", "analysis"):
            path = f"tests/test_jlens_causal_{suffix}.py"
            if (c.ROOT / path).is_file():
                assert path in script
    else:
        command = shlex.split(script.splitlines()[-1])
        assert command[1:4] == ["-u", "-m", "experiments.jlens_causal_report.runner"]
        assert command[4:] == ["--plan", RELATIVE, "--freeze", FREEZE, "--out", c.REMOTE + "/out",
                               "--cache", "/workspace/cache", "--deadline-utc", UTC.isoformat()]


@pytest.mark.parametrize("relative,freeze,kind,deadline", [
    ("../plan.json", FREEZE, "main", UTC.isoformat()),
    ("data/jlens_causal_report/../other", FREEZE, "main", UTC.isoformat()),
    (RELATIVE, "HEAD", "main", UTC.isoformat()),
    (RELATIVE, FREEZE, "qwen", UTC.isoformat()), (RELATIVE, FREEZE, "main", "not-a-date"),
])
def test_worker_validation(relative, freeze, kind, deadline):
    with pytest.raises(ValueError):
        c.worker_script(kind, relative, freeze, deadline)


@pytest.mark.parametrize("kind,ceiling,memory", [("cheap", .74, 24), ("main", 6.79, 180)])
def test_quote_hardware_caps_and_storage_no_fallback(kind, ceiling, memory):
    api = FakeAPI(lambda: UTC)
    api.catalog.update(id=c.base.HARDWARE[kind][0], memory=memory, price={"secure": ceiling})
    assert Decimal(c.base.quote(api, kind)["storage_hourly_usd"]) == Decimal(".10")
    for change in ({"availability": "NONE"}, {"price": {"secure": ceiling + .01}},
                   {"id": "fallback-gpu"}, {"secure": False}, {"memory": memory - 1}):
        with patch.dict(api.catalog, change), pytest.raises(ValueError):
            c.base.quote(api, kind)
    assert all(method == "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize("args", [
    ["--action", "launch"], ["--action", "launch", "--launch"],
    ["--action", "monitor"], ["--action", "terminate"],
    ["--action", "approve", "--launch"],
])
def test_cli_mutation_flags_fail_before_api(args):
    with patch.object(c.base, "RunPodV2") as api, pytest.raises(SystemExit):
        c.main(["--plan", "absent", "--freeze", FREEZE, "--kind", "cheap", *args])
    api.assert_not_called()


def test_output_is_ignored_in_actual_repo():
    c._require_ignored(c.OWNED_OUT / "not-created-approval.json")
    assert not (c.OWNED_OUT / "not-created-approval.json").exists()


def test_dispatch_arguments_match_actual_runner_parser():
    from experiments.jlens_causal_report import runner
    command = shlex.split(c.worker_script("main", RELATIVE, FREEZE, UTC.isoformat()).splitlines()[-1])
    with patch.object(runner.protocol, "load_plan", return_value={"synthetic": True}), \
            patch.object(runner, "Study") as study, patch("sys.argv", ["runner", *command[4:]]):
        runner.main()
    study.assert_called_once_with({"synthetic": True}, RELATIVE, FREEZE, c.REMOTE + "/out",
                                  UTC.isoformat(), "/workspace/cache")
    study.return_value.execute.assert_called_once_with()
