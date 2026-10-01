"""Offline proof of qualification lifecycle. No model downloads or live APIs."""
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
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.parse

import pytest

from experiments.instruction_state_qualification import controller as c
from experiments.sae_assay_exposure_lifecycle_a1 import controller as corrected
from tests import test_sae_assay_controller as prior

FREEZE, UTC, PUBLIC_KEY = prior.FREEZE, prior.UTC, prior.PUBLIC_KEY


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in lifecycle tests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


class FakeAPI(prior.FakeAPI):
    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.extra = [{"id": "foreign-" + str(i), "name": c.PREFIX + "main-012345abcdef"}
                      for i in range(4)]
        self.offers = {kind: {"id": gpu, "memory": memory, "secure": True,
                             "price": {"secure": str(rate)}, "availability": "LOW"}
                       for kind, (gpu, rate, memory) in c.base.HARDWARE.items()}

    def inventory(self):
        return super().inventory() + self.extra

    def request(self, method, path, body=None):
        if path.startswith("/catalog/"):
            self.calls.append((method, path, body))
            name = urllib.parse.unquote(path.split("/catalog/gpus/")[1].split("?")[0])
            return 200, next(o for o in self.offers.values() if o["id"] == name)
        try:
            return super().request(method, path, body)
        finally:
            if method == "POST" and self.pod:
                offer = next(o for o in self.offers.values() if o["id"] == body["gpu"]["id"])
                self.deleted = False
                self.pod.update(createdAt=self.clock().isoformat(), cost=offer["price"]["secure"],
                                gpu={"id": offer["id"], "count": 1, "memory": offer["memory"]})


class ControllerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.out = self.root / "out/instruction-qualification-20261001"
        self.plan = self.root / c.PLAN_RELATIVE
        self.plan.parent.mkdir(parents=True)
        self.plan_data = {"budget": deepcopy(c.BUDGET), "blocks": [{"id": f"block-{i:02d}"} for i in range(1, 21)]}
        self.plan.write_text(json.dumps(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("synthetic not a private key")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: json.loads(self.plan.read_text()))
        self.public, self.ci, self.ignored = Mock(), Mock(return_value={"pass": True}), Mock()
        for target, value in (("experiments.instruction_state_qualification.controller.ROOT", self.root),
                              ("experiments.instruction_state_qualification.controller.OWNED_OUT", self.out),
                              ("experiments.instruction_state_qualification.controller.load_plan", self.loader),
                              ("experiments.instruction_state_qualification.controller._require_ignored", self.ignored),
                              ("experiments.instruction_state_qualification.controller.verify_ci", self.ci),
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
                                                            "synthetic-user-request")))

    def controller(self, kind="cheap", **kwargs):
        defaults = {"launch": True, "approved_new_cap_usd": "25",
                    "approval_ref": "synthetic-user-request", "approval_file": self.out / "user-approval.json"}
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
                              "tests.xml": b'<testsuites><testsuite tests="10" failures="0" errors="0" skipped="0"/></testsuites>',
                              "controller-exit.json": b'{"exit_code":0}'})
        self.advance(c.CHEAP_SECONDS)
        self.ctrl.terminate()

    def main_controller(self):
        return self.controller("main")

    def test_inherited_methods_do_not_reuse_foreign_budget_or_namespace(self):
        self.assertIs(c.Controller.signal_worker, corrected.Controller.signal_worker)
        for name in ("terminate", "retrieve", "_snapshot", "_exclusive", "owned", "_ssh", "reconcile_create"):
            self.assertIs(getattr(c.Controller, name), getattr(c.transport.Controller, name))
        self.assertIs(c.Controller.close_until_verified, c.ensemble.Controller.close_until_verified)
        self.assertIsNot(c.Controller.status, c.transport.Controller.status)

    def test_authorization_required_before_any_network(self):
        for kwargs in ({"launch": False}, {"approved_new_cap_usd": None}, {"approved_new_cap_usd": "200"},
                       {"approval_ref": None}, {"approval_file": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.controller(**kwargs).launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_not_called()
        self.ci.assert_not_called()

    def test_wrong_plan_approval_and_fake_review_are_rejected(self):
        original = json.loads(self.approval.read_text())
        for changed in ({"user_confirmed": 1}, {"scope": "all_experiments"}, {"approved_new_cap_usd": "130"},
                        {"plan_sha256": "b" * 64}, {"freeze_commit": "b" * 40},
                        {"approval_ref": "agent-review"}, {"human_reviewed": True}):
            self.approval.write_text(json.dumps({**original, **changed}))
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_missing_approval_is_not_created(self):
        self.approval.unlink()
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertFalse(self.approval.exists())
        self.assertEqual(self.api.calls, [])

    def test_namespace_and_approval_paths_cannot_reset_budget(self):
        with self.assertRaises(ValueError):
            c.Controller(self.plan, FREEZE, self.root / "elsewhere", "cheap", self.api)
        linked = self.out / "linked.json"
        linked.symlink_to(self.approval)
        with self.assertRaises(ValueError):
            self.controller(approval_file=linked).launch()
        self.plan.write_text(json.dumps({**self.plan_data, "changed": True}))
        with self.assertRaises(ValueError):
            self.controller()
        with self.assertRaises(ValueError):
            self.ctrl.launch()

    def test_public_ci_failure_precedes_runpod_calls(self):
        self.ci.side_effect = ValueError("Hosted tests pending")
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_called_once_with(self.ctrl.plan_hash, c.PLAN_RELATIVE, FREEZE)

    def test_both_offers_must_be_available_before_cheap_creation(self):
        self.api.offers["main"]["availability"] = "NONE"
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))

    def test_existing_four_pods_blocked_and_single_creation(self):
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertTrue({p["id"] for p in self.api.extra} <= set(intent["blocked"]))
        self.assertEqual(set(intent["offers"]), {"cheap", "main"})
        self.assertEqual(c._utc(intent["deadline_utc"]), UTC + timedelta(seconds=600))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]), UTC + timedelta(seconds=1200))
        self.assertTrue(self.api.pod["name"].startswith(c.PREFIX + "cheap-"))
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(sum(method == "POST" for method, _, _ in self.api.calls), 1)
        for foreign in self.api.extra:
            altered = {**self.api.pod, "id": foreign["id"]}
            self.assertFalse(self.ctrl._new_pod(altered, intent))

    def test_missing_cheap_gate_blocks_main_before_calls(self):
        with self.assertRaises(ValueError):
            self.main_controller().launch()
        self.assertEqual(self.api.calls, [])

    def test_cheap_receipt_carries_storage_cost_to_main(self):
        self.complete_cheap()
        main = self.main_controller()
        self.assertEqual(main.cheap_receipt(), Decimal("0.28"))
        self.ctrl = main
        self.launched()
        intent = main.event("create-intent")["data"]
        self.assertEqual(Decimal(intent["prior_new_usd"]), Decimal("0.28"))
        self.assertEqual(main.hard_seconds, 6600)

    def test_full_main_timer_cannot_borrow_api_or_reserve(self):
        self.ctrl = self.main_controller()
        self.ctrl.cheap_receipt = Mock(return_value=Decimal("1.4"))
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertFalse(any(method == "POST" for method, _, _ in self.api.calls))

    def test_hardware_price_and_storage_drift_rejected(self):
        self.launched()
        for changes in ({"cost": "0.75"}, {"cost": None}, {"gpu": None},
                        {"gpu": {"id": "NVIDIA B200", "count": 1, "memory": 180}},
                        {"disk": 500}, {"mounts": {}}, {"ports": ["8888/http"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.ctrl.cost_check({**self.api.pod, **changes})

    def test_retrieval_reserve_and_waiting_still_cost_money(self):
        self.launched()
        self.advance(539)
        self.ctrl.cost_check(self.api.pod, 60)
        self.advance(1)
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod, 60)
        self.assertTrue(any(r["data"].get("reserved_non_gpu_usd") == "11" for r in self.ctrl.ledger.read()))

    def test_clock_rollback_rejected(self):
        self.launched()
        self.advance(5)
        self.ctrl.cost_check(self.api.pod)
        self.current -= timedelta(seconds=1)
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod)

    def test_worker_transfers_only_hf_and_uses_corrected_dispatch(self):
        self.launched()
        self.ctrl._ssh = Mock(return_value=b"")
        self.ctrl.start_worker()
        data = [call.kwargs["data"] for call in self.ctrl._ssh.call_args_list if "data" in call.kwargs]
        self.assertEqual(data, [b"export HF_TOKEN=''\n"])
        command = self.ctrl._ssh.call_args.args[1]
        self.assertIn("env -i", command)
        self.assertIn("CODEX_EXPOSURE_NAMESPACE=exposure-controller", command)
        self.assertNotIn("OPENAI_API_KEY", command)
        self.assertNotIn("ANTHROPIC_API_KEY", command)
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def throughput_receipt(self, seconds=10):
        self.ctrl = self.main_controller()
        self.ctrl.cheap_receipt = Mock(return_value=Decimal("0.10"))
        self.launched()
        root = self.ctrl.base / "retrievals/throughput"
        (root / "rows").mkdir(parents=True)
        for spec in self.plan_data["blocks"][:5]:
            generation = {"elapsed_seconds": seconds}
            row = {"sources": {"self": generation, "history": generation},
                   "responses": [{"generation": generation} for _ in range(4)]}
            (root / "rows" / (spec["id"] + ".json")).write_text(json.dumps(row))
        return self.ctrl.record("retrieval", {"pod_id": self.api.pod["id"], "directory": str(root),
                                             "artifacts": c.artifact_map(root)})

    def test_first_five_projection_counts_startup_api_wait_and_retrieval(self):
        receipt = self.throughput_receipt()
        self.advance(600)
        report = self.ctrl._throughput_gate(receipt)
        self.assertEqual(Decimal(report["billed_elapsed_seconds"]), 600)
        self.assertEqual(Decimal(report["remaining_generation_seconds"]), 900)
        self.assertEqual(report["judge_wait_allowance_seconds"], 1200)
        self.assertEqual(report["runner_internal_reserve_seconds"], 600)
        self.assertEqual(Decimal(report["projected_lifetime_seconds"]), 4530)
        self.assertTrue(report["pass"])

    def test_first_five_projection_rejects_slow_or_overdue_work(self):
        receipt = self.throughput_receipt(100)
        self.advance(3200)
        with self.assertRaisesRegex(ValueError, "does not fit"):
            self.ctrl._throughput_gate(receipt)
        self.assertIsNone(self.ctrl.event("approved:first-five"))

    def test_first_five_projection_rejects_missing_timings(self):
        receipt = self.throughput_receipt(0)
        self.advance(600)
        with self.assertRaisesRegex(ValueError, "nonpositive"):
            self.ctrl._throughput_gate(receipt)

    def test_final_gpu_receipt_does_not_claim_local_api_cost(self):
        self.complete_cheap()
        result = self.ctrl.event("closed")["data"]
        self.assertEqual(Decimal(result["compute_upper_bound_usd"]), Decimal("0.28"))
        self.assertEqual(Decimal(result["cumulative_gpu_upper_bound_usd"]), Decimal("69.410940"))
        self.assertIn("not included", result["api_accounting"])
        self.assertNotIn("cumulative_upper_bound_usd", result)

    def test_cheap_failure_cannot_qualify_main(self):
        self.complete_cheap()
        receipt = json.loads((self.ctrl.base / "final-retrieval.json").read_text())
        (Path(receipt["data"]["directory"]) / "tests.xml").write_text("changed")
        with self.assertRaises(ValueError):
            self.main_controller().cheap_receipt()

    def look(self, name="look12"):
        self.ctrl = self.main_controller()
        self.ctrl.cheap_receipt = Mock(return_value=Decimal("0.10"))
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": self.current.isoformat()})
        for barrier in c.BARRIERS:
            self.ctrl.ledger.bind("approved:" + barrier, {"plan_sha256": self.ctrl.plan_hash})
        barrier = {"plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE,
                   "barrier": name, "rows": c.BARRIER_ROWS[name]}
        root = self.ctrl.base / "retrievals/synthetic"
        (root / "rows").mkdir(parents=True)
        (root / ("WAITING-" + name + ".json")).write_text(json.dumps(barrier))
        (root / "rows/qualification-live.json").write_text('{"result":{"pass":true}}')
        receipt = self.ctrl.record("retrieval", {"pod_id": self.api.pod["id"], "directory": str(root),
                                                "artifacts": c.artifact_map(root)})
        state = {"pod": deepcopy(self.api.pod), "files": {"WAITING-" + name + ".json": barrier,
                 "_approvals": {"APPROVE-" + n: self.ctrl.plan_hash for n in c.BARRIERS}}}
        self.ctrl.status = Mock(return_value=state)
        self.ctrl._ssh = Mock(return_value=b"")
        self.judge_root = self.out / "judges"
        self.judge_root.mkdir()
        (self.judge_root / "requests.jsonl").write_text("synthetic-ledger\n")
        self.result = {"plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE, "n_blocks": c.LOOKS[name],
                       "decision": "extend" if name == "look12" else "pass", "api_spent_usd": "1.20",
                       "providers": {"openai": {}, "anthropic": {}}, "reason_codes": ["synthetic"]}
        self.decision_path = self.out / "decision.json"
        self.decision_path.write_text(json.dumps(self.result))
        self.audit = Mock(return_value={"pass": True, "rows": c.BARRIER_ROWS[name]})
        patcher = patch.object(c, "audit", self.audit)
        patcher.start()
        self.addCleanup(patcher.stop)
        if name == "look20":
            prev = {"payload": {"decision": "extend", "plan_sha256": self.ctrl.plan_hash}}
            self.ctrl.ledger.bind("decision:look12", prev)
            state["files"]["DECISION-look12.json"] = prev["payload"]
        return state, receipt

    def test_decision_recomputes_and_binds_all_snapshot_hashes(self):
        _, receipt = self.look()
        def recompute(*args):
            self.assertEqual(args[-1], 12)
            self.assertEqual(getattr(self.ctrl, "_mutation_depth", 0), 0)
            return deepcopy(self.result)
        with patch.object(c, "analyze", side_effect=recompute) as analyze:
            event = self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.assertEqual(analyze.call_count, 1)
        payload = json.loads(self.ctrl._ssh.call_args.kwargs["data"])
        self.assertEqual(payload["source_snapshot_sha256"], receipt["sha256"])
        self.assertEqual(payload["source_artifacts"], receipt["data"]["artifacts"])
        self.assertEqual(payload["judge_artifacts"], c.artifact_map(self.judge_root))
        self.assertEqual(event["data"]["payload"], payload)

    def test_arbitrary_decision_json_rejected(self):
        self.look()
        self.decision_path.write_text(json.dumps({**self.result, "decision": "pass"}))
        with patch.object(c, "analyze", return_value=self.result), self.assertRaises(ValueError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.ctrl._ssh.assert_not_called()

    def test_unknown_judge_artifact_rejected_before_analysis(self):
        self.look()
        (self.judge_root / "unverified-labels.json").write_text("{}")
        with patch.object(c, "analyze") as analyze, self.assertRaises(ValueError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        analyze.assert_not_called()
        self.ctrl._ssh.assert_not_called()

    def test_corrupt_raw_and_wrong_rows_rejected(self):
        _, receipt = self.look()
        self.audit.return_value["rows"] = 12
        with self.assertRaises(ValueError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.audit.return_value["rows"] = 13
        (Path(receipt["data"]["directory"]) / "rows/qualification-live.json").write_text("changed")
        with self.assertRaises(ValueError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.ctrl._ssh.assert_not_called()

    def test_wrong_freeze_and_overbudget_decisions_rejected(self):
        self.look()
        for changed in ({"freeze_commit": "b" * 40}, {"api_spent_usd": "10.01"},
                        {"n_blocks": 20}, {"providers": {"openai": {}}}):
            result = {**self.result, **changed}
            self.decision_path.write_text(json.dumps(result))
            with patch.object(c, "analyze", return_value=result), self.assertRaises(ValueError):
                self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.ctrl._ssh.assert_not_called()

    def test_twenty_blocks_never_extend(self):
        self.look("look20")
        result = {**self.result, "decision": "extend"}
        self.decision_path.write_text(json.dumps(result))
        with patch.object(c, "analyze", return_value=result), self.assertRaises(ValueError):
            self.ctrl.decision("look20", self.decision_path, judge_root=self.judge_root)
        self.ctrl._ssh.assert_not_called()

    def test_terminated_during_analysis_never_publishes_decision(self):
        self.look()
        def analysis(*_):
            self.ctrl.ledger.bind("closing", {"pod_id": self.api.pod["id"]})
            return self.result
        with patch.object(c, "analyze", side_effect=analysis), self.assertRaises(ValueError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        self.ctrl._ssh.assert_not_called()

    def test_uncertain_decision_write_reconciles_only_exact_intent(self):
        self.look()
        self.ctrl._ssh.side_effect = RuntimeError("lost response")
        with patch.object(c, "analyze", return_value=self.result), self.assertRaises(RuntimeError):
            self.ctrl.decision("look12", self.decision_path, judge_root=self.judge_root)
        intent = self.ctrl.event("decision-intent:look12")
        self.assertIsNone(self.ctrl.event("decision:look12"))
        self.ctrl._reconcile_decisions({"DECISION-look12.json": intent["data"]["payload"]})
        self.assertEqual(self.ctrl.event("decision:look12")["data"], intent["data"])
        with self.assertRaises(ValueError):
            self.ctrl._reconcile_decisions({"DECISION-look20.json": {"decision": "pass"}})

    def test_monitor_waiting_does_not_autoapprove_or_bypass_cost_clock(self):
        state, receipt = self.look()
        self.ctrl.retrieve = Mock(return_value=receipt)
        self.ctrl.close_until_verified = Mock(return_value={"closed": True})
        self.ctrl.sleep = lambda seconds: self.advance(60 * 20)
        self.ctrl.monitor()
        self.assertTrue(self.ctrl.close_until_verified.called)
        self.assertGreaterEqual(self.ticks, 6000)
        self.assertFalse(self.ctrl._ssh.called)
        self.assertIsNone(self.ctrl.event("decision:look12"))
        self.assertTrue(any(r["data"].get("error_type") == "ValueError" for r in self.ctrl.ledger.read()))

    def test_status_script_includes_look_barriers_and_decisions(self):
        for name in c.BARRIER_ROWS:
            self.assertIn("WAITING-" + name + ".json", c.STATUS_SCRIPT)
        for name in c.LOOKS:
            self.assertIn("DECISION-" + name + ".json", c.STATUS_SCRIPT)
        compile(c.STATUS_SCRIPT, "<status>", "exec")

    def test_default_cli_is_offline(self):
        with patch.object(c.base, "RunPodV2") as api, patch("sys.stdout", new_callable=io.StringIO) as output:
            c.main(["--plan", str(self.plan), "--freeze", FREEZE, "--kind", "cheap"])
        api.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["network_calls"], 0)

    def test_all_live_cli_actions_need_explicit_launch(self):
        for action in ("create", "monitor", "retrieve", "status", "approve", "decision", "close", "reconcile"):
            with self.subTest(action=action), patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                c.main(["--freeze", FREEZE, "--kind", "cheap", "--action", action])


def test_worker_scripts_have_cuda_assertion_pinned_dependencies_and_no_judge_credentials():
    for kind in ("cheap", "main"):
        script = c.worker_script(kind, c.PLAN_RELATIVE, FREEZE, UTC.isoformat())
        subprocess.run(["bash", "-n"], input=script.encode(), check=True, capture_output=True)
        assert "experiments/sae_assay_diagnostic/requirements-gpu.txt" in script
        assert "OPENAI_API_KEY" not in script and "ANTHROPIC_API_KEY" not in script
        assert "git checkout --detach " + FREEZE in script
        assert "--single-branch --no-tags --depth=1" in script
        assert script.index("sparse-checkout set --no-cone --stdin") < script.index("git checkout --detach")
        assert script.index("Sparse runtime closure missing") < script.index(" -m pip install")
        assert script.count("git status --porcelain --untracked-files=no") == 1
        assert "'--untracked-files=no'" in script  # Physical-closure preflight also checks clean status.
        if kind == "cheap":
            assert "INSTRUCTION_TEST_DEVICE=cuda" in script
            assert "assert torch.cuda.is_available()" in script
            assert all(name in script for name in c.TESTS)
            assert "HF_HUB_OFFLINE=1" in script
        else:
            assert "experiments.instruction_state_qualification.runner" in script
            assert "--deadline-utc" in script


def test_sparse_inventory_includes_transitive_tests_and_binding_inputs():
    paths = c.sparse_paths()
    assert paths == sorted(set(paths))
    assert set(c.protocol.source_paths()) <= set(paths)
    assert {c.PLAN_RELATIVE, c.protocol.TOKEN_BINDINGS_PATH, c.protocol.PRIOR_BINDING_PATH,
            "tests/test_sae_assay_controller.py", "tests/__init__.py", "pytest.ini",
            "data/causal_transplant/confirmatory_v1_20260709/manifest.json"} <= set(paths)
    assert all(not path.endswith("/") for path in paths)


def test_exact_sparse_checkout_rehearsal_runs_real_plan_consumer(tmp_path):
    """Local file-only Git fixture: actual runtime closure, no remote service."""
    paths = c.sparse_paths()
    source, checkout = tmp_path / "source", tmp_path / "checkout"
    source.mkdir()
    for name in paths:
        if name == c.PLAN_RELATIVE:
            continue
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(c.protocol.ROOT / name, destination)
    plan = c.protocol.build_plan()
    (source / c.PLAN_RELATIVE).write_text(c.protocol.canonical(plan) + "\n")
    unneeded = source / "data/unrelated-large-artifact.bin"
    unneeded.write_bytes(b"not needed by this runtime\n" * 10000)
    env = {**c.base.local_env(), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    def git(*args, cwd=source):
        return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull, *args],
                                       cwd=cwd, env=env, stderr=subprocess.PIPE, text=True)
    git("init", "-q")
    git("add", "--force", "--", *paths, "data/unrelated-large-artifact.bin")
    git("-c", "user.email=test@example.invalid", "-c", "user.name=Offline Test", "commit", "-qm", "fixture")
    freeze = git("rev-parse", "HEAD").strip()
    git("clone", "--no-checkout", "--single-branch", "--no-tags", str(source), str(checkout), cwd=tmp_path)
    script = "\n".join(c.sparse_checkout_commands(freeze))
    subprocess.run(["bash", "-eu", "-c", script], cwd=checkout, env=env,
                   check=True, capture_output=True)
    assert all((checkout / name).is_file() for name in paths)
    assert not (checkout / "data/unrelated-large-artifact.bin").exists()
    assert git("status", "--porcelain", "--untracked-files=no", cwd=checkout) == ""
    consumer = ("from experiments.instruction_state_qualification.protocol import load_plan; "
                + "load_plan(" + repr(c.PLAN_RELATIVE) + "," + repr(freeze) + ")")
    subprocess.run([sys.executable, "-c", consumer], cwd=checkout, env=env,
                   check=True, capture_output=True)
    assert git("status", "--porcelain", "--untracked-files=no", cwd=checkout) == ""


def test_budget_partition_is_exact_and_does_not_double_count_contingency():
    assert c.checked_budget({"budget": deepcopy(c.BUDGET)}) == c.BUDGET
    assert c.GPU_CAP_USD + c.API_CAP_USD + c.EXTRA_RESERVE_USD == c.NEW_CAP_USD
    cost = sum((rate + c.base.STORAGE) * seconds / 3600 for rate, seconds in
               ((Decimal(".74"), c.CHEAP_SECONDS), (Decimal("6.79"), c.MAIN_SECONDS)))
    assert cost < c.GPU_CAP_USD
    for changes in ({"api_cap_usd": "12"}, {"gpu_cap_usd": "25"}, {"new_pro_calls": 1},
                    {"main_seconds": "6600"}, {"storage_reserve_usd": "0"}):
        with pytest.raises(ValueError):
            c.checked_budget({"budget": {**c.BUDGET, **changes}})


def test_ci_verifier_requires_full_success_inventory():
    names = ["Public release boundary"] + [label + " / Python " + version
             for label in ("Tests", "Current paper evidence", "Compile tracked sources") for version in ("3.10", "3.12")]
    runs = {"total_count": 1, "workflow_runs": [
        {"id": 123, "head_sha": FREEZE, "status": "completed", "conclusion": "success"}]}
    jobs = {"total_count": len(names), "jobs": [
        {"name": name, "status": "completed", "conclusion": "success"} for name in names]}
    def opener(values):
        fake = Mock()
        contexts = []
        for value in values:
            context = Mock()
            context.__enter__ = Mock(return_value=Mock(read=Mock(return_value=json.dumps(value).encode())))
            context.__exit__ = Mock(return_value=False)
            contexts.append(context)
        fake.open.side_effect = contexts
        return fake
    assert c.verify_ci(FREEZE, opener=opener([runs, jobs]))["pass"]
    for changed in ({"conclusion": "failure"}, {"status": "in_progress"}, {"head_sha": "b" * 40}):
        wrong = deepcopy(runs)
        wrong["workflow_runs"][0].update(changed)
        with pytest.raises(ValueError):
            c.verify_ci(FREEZE, opener=opener([wrong]))
    wrong = deepcopy(jobs)
    wrong["jobs"][0]["conclusion"] = "skipped"
    with pytest.raises(ValueError):
        c.verify_ci(FREEZE, opener=opener([runs, wrong]))
