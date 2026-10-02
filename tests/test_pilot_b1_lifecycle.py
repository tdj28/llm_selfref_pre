"""B1 lifecycle regression and carry-cost tests; no paid API or pod access.

The lifecycle tests are adapted from A1 into this separate successor file.
Original tests and modules remain unchanged for frozen-run reconstruction.
"""
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

from experiments.bilingual_llama_b1 import controller as c, protocol
from experiments.sae_assay_exposure_lifecycle_a1 import controller as corrected
from tests import test_instruction_state_controller as shared
from tests import test_sae_assay_controller as original

FREEZE, UTC, PUBLIC_KEY = original.FREEZE, original.UTC, original.PUBLIC_KEY


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in bilingual controller tests")
    monkeypatch.setattr("urllib.request.OpenerDirector.open", forbidden)
    monkeypatch.setattr("socket.socket.connect", forbidden)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.out = self.root / "out/bilingual-llama-b1-20261002"
        self.fixture = self.root / "fixture-proof.json"
        fixtures = [{"id": "fixture-synthetic"}]
        self.plan_data = {"budget": deepcopy(c.BUDGET), "blocks": protocol.inventory(),
                          "counts": {"generation_calls": 760}, "fixtures": fixtures}
        self.plan = self.root / c.PLAN_RELATIVE
        self.plan.parent.mkdir(parents=True)
        self.plan.write_bytes(c._canonical(self.plan_data))
        self.key = self.root / "key"
        self.key.write_text("synthetic placeholder only")
        self.key.with_suffix(".pub").write_text(PUBLIC_KEY)
        self.current, self.ticks = UTC, 0
        self.loader = Mock(side_effect=lambda *_: json.loads(self.plan.read_bytes()))
        self.public, self.ci = Mock(), Mock(return_value={"pass": True})
        for module, name, value in (
                (c, "ROOT", self.root), (c, "OWNED_OUT", self.out),
                (c, "load_plan", self.loader), (c, "_require_ignored", Mock()),
                (c, "verify_ci", self.ci), (c.base, "verify_public", self.public),
                (c.base, "KEY", self.key)):
            item = patch.object(module, name, value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.dict(os.environ, {"HF_TOKEN": "hf_placeholder_only",
            "RUNPOD_API_KEY": "rp_placeholder_only", "OPENAI_API_KEY": "openai_placeholder_only",
            "ANTHROPIC_API_KEY": "anthropic_placeholder_only"}, clear=True)
        item.start()
        self.addCleanup(item.stop)
        self.api = shared.FakeAPI(lambda: self.current)
        self.ctrl = self.controller()
        self.proof = {"schema": "bilingual-fixture-gate-b1", "plan_sha256": self.ctrl.plan_hash,
            "freeze_commit": FREEZE, "pass": True, "judgment_count": 128,
            "fixture_inventory_sha256": hashlib.sha256(c._canonical(fixtures)).hexdigest(),
            "receipts": {"judgments.jsonl": {"sha256": "a" * 64, "records": 128}}}
        self.fixture.write_bytes(c._canonical(self.proof))
        item = patch.object(c, "fixture_proof", Mock(return_value=self.proof))
        item.start()
        self.addCleanup(item.stop)
        self.approval = self.out / "user-approval.json"
        self.approval.write_bytes(c._canonical(c.approval_record(
            self.ctrl.plan_hash, FREEZE, c.BUDGET, "synthetic-user-request")))

    def controller(self, kind="cheap", **kwargs):
        defaults = {"launch": True, "approved_new_cap_usd": "200",
                    "approval_ref": "synthetic-user-request", "approval_file": self.out / "user-approval.json",
                    "fixture_gate": self.fixture}
        defaults.update(kwargs)
        ctrl = c.Controller(self.plan, FREEZE, self.out, kind, self.api,
            clock=lambda: self.current, sleep=Mock(), monotonic=lambda: self.ticks,
            run=Mock(side_effect=AssertionError("Unexpected subprocess")), **defaults)
        ctrl.disk_check = Mock()
        return ctrl

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)
        self.ticks += seconds

    launched = original.ControllerTests.launched
    snapshots = shared.ControllerTests.snapshots
    test_unknown_pod_never_accessed = original.ControllerTests.test_unknown_pod_never_accessed
    test_uncertain_post_reconciles_exact_name_without_second_post = original.ControllerTests.test_uncertain_post_reconciles_exact_name_without_second_post
    test_retrieval_pauses_resumes_and_never_approves = original.ControllerTests.test_retrieval_pauses_resumes_and_never_approves
    test_retrieval_failure_always_resumes = original.ControllerTests.test_retrieval_failure_always_resumes
    test_corrupt_snapshot_blocks_delete = original.ControllerTests.test_corrupt_snapshot_blocks_delete
    test_corruption_after_retrieval_blocks_delete = original.ControllerTests.test_corruption_after_retrieval_blocks_delete
    test_retrieve_before_delete_and_verified_closure = original.ControllerTests.test_retrieve_before_delete_and_verified_closure
    test_no_worker_startup_failure_can_be_closed = original.ControllerTests.test_no_worker_startup_failure_can_be_closed
    test_runtime_hardware_drift_and_cost_unknown_fail = original.ControllerTests.test_runtime_hardware_drift_and_cost_unknown_fail

    def complete_cheap(self):
        self.launched()
        self.snapshots(files={"DONE-all.json": b'{"pass":true,"scope":"tiny_cuda_exact_path"}',
            "tests.xml": b'<testsuites><testsuite tests="10" failures="0" errors="0" skipped="0"/></testsuites>',
            "controller-exit.json": b'{"exit_code":0}'})
        self.advance(c.CHEAP_SECONDS)
        return self.ctrl.terminate()

    def main_started(self):
        self.ctrl = self.controller("main")
        self.ctrl.cheap_receipt = Mock(return_value=Decimal("0.42"))
        self.launched()
        self.ctrl.ledger.bind("worker-started", {"utc": self.current.isoformat()})
        return self.ctrl

    def barrier(self, name="first-two", *, changed=None, timing=1):
        self.main_started()
        self.advance(1000)
        block_count = 2 if name == "first-two" else 0
        value = {"barrier": name, "rows": c.BARRIER_ROWS[name],
                 "plan_sha256": self.ctrl.plan_hash, "freeze_commit": FREEZE}
        files = {"WAITING-" + name + ".json": value, "_approvals": {}}
        if block_count:
            self.ctrl.ledger.bind("approved:qualification", {"plan_sha256": self.ctrl.plan_hash})
            files["_approvals"]["APPROVE-qualification"] = self.ctrl.plan_hash
        root = self.ctrl.base / "retrievals" / "snapshot"
        root.mkdir(parents=True)
        (root / ("WAITING-" + name + ".json")).write_bytes(c._canonical(value))
        names = [s["id"] for block in self.plan_data["blocks"][:block_count]
                 for s in [*block["sources"], *block["cells"]]]
        for identifier in names:
            path = root / "generations" / (identifier + ".json")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(c._canonical({"elapsed_seconds": timing}))
        receipt = self.ctrl.record("retrieval", {"directory": str(root),
            "pod_id": self.ctrl.owned()["id"], "artifacts": c.artifact_map(root)})
        report = {"pass": True, "production_eligible": True, "rows": c.BARRIER_ROWS[name],
                  "generations": len(names), "blocked_cells": 0, "partial_generation_ids": [],
                  "unresolved_generation_dispatches": []}
        report.update(changed or {})
        item = patch.object(c, "audit", Mock(return_value=report))
        item.start()
        self.addCleanup(item.stop)
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": files})
        self.ctrl._write_remote = Mock()
        return receipt, report, files

    def test_reused_helpers_have_no_foreign_namespace_or_budget(self):
        self.assertIs(c.Controller.signal_worker, corrected.Controller.signal_worker)
        for name in ("terminate", "retrieve", "_snapshot", "owned", "_exclusive", "_ssh", "reconcile_create"):
            self.assertIs(getattr(c.Controller, name), getattr(c.transport.Controller, name))
        self.assertIsNot(c.Controller.cheap_receipt, c.qualification.Controller.cheap_receipt)
        self.assertFalse(hasattr(c.Controller, "decision"))

    def test_authorization_fails_before_any_provider_or_public_access(self):
        for options in ({"launch": False}, {"approved_new_cap_usd": "45"},
                        {"approved_new_cap_usd": None}, {"approval_file": None}, {"approval_ref": None}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.controller(**options).launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_not_called()
        self.ci.assert_not_called()

    def test_missing_approval_is_not_created(self):
        self.approval.unlink()
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertFalse(self.approval.exists())
        self.assertEqual(self.api.calls, [])

    def test_canonical_paths_plan_and_approval_cannot_reset_budget(self):
        with self.assertRaises(ValueError):
            c.Controller(self.plan, FREEZE, self.root / "elsewhere", "cheap", self.api)
        linked = self.out / "linked.json"
        linked.symlink_to(self.approval)
        with self.assertRaises(ValueError):
            self.controller(approval_file=linked).launch()
        self.plan.write_bytes(c._canonical({**self.plan_data, "changed": True}))
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        with self.assertRaises(ValueError):
            self.controller()
        self.assertEqual(self.api.calls, [])

    def test_exact_freeze_ci_precedes_provider(self):
        self.ci.side_effect = ValueError("Hosted CI pending")
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_called_once_with(self.ctrl.plan_hash, c.PLAN_RELATIVE, FREEZE)

    def test_names_timers_reserves_and_no_adoption(self):
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertEqual(self.ctrl.base, self.out / "bilingual-llama-b1/cheap")
        self.assertTrue(self.api.pod["name"].startswith(c.PREFIX + "cheap-"))
        self.assertEqual(c._utc(intent["deadline_utc"]), UTC + timedelta(seconds=1200))
        self.assertEqual(c._utc(intent["hard_deadline_utc"]), UTC + timedelta(seconds=1800))
        self.assertEqual(intent["prior_total_usd"], "0")
        self.assertEqual(intent["contingency_used_usd"], "0")
        self.assertEqual(set(intent["offers"]), {"cheap", "main"})
        self.assertEqual(intent["payload"]["env"], {"PUBLIC_KEY": PUBLIC_KEY})
        for foreign in self.api.extra:
            self.assertIn(foreign["id"], intent["blocked"])
            self.assertFalse(self.ctrl._new_pod({**self.api.pod, "id": foreign["id"]}, intent))
        wrong = deepcopy(intent)
        wrong["payload"]["name"] = c.qualification.PREFIX + "cheap-012345abcdef"
        self.assertFalse(self.ctrl._new_pod({**self.api.pod, "name": wrong["payload"]["name"]}, wrong))
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_cheap_failed_or_unclosed_receipt_does_not_allow_main(self):
        with self.assertRaises(ValueError):
            self.controller("main").launch()
        self.assertEqual(self.api.calls, [])

    def test_cheap_receipt_cost_stays_in_new_namespace(self):
        self.complete_cheap()
        main = self.controller("main")
        self.assertEqual(main.cheap_receipt(), Decimal("0.42"))
        self.ctrl = main
        self.launched()
        intent = main.event("create-intent")["data"]
        self.assertEqual(Decimal(intent["prior_new_usd"]), Decimal("0.42"))
        self.assertEqual(main.hard_seconds, 18000)
        self.assertEqual(main.event("fixture-gate")["data"]["artifact_sha256"], c.sha(self.fixture))

    def test_both_rentals_require_fresh_fixture_before_network(self):
        for kind in ("cheap", "main"):
            for proof in (None, self.root / "missing.json"):
                ctrl = self.controller(kind, fixture_gate=proof)
                ctrl.cheap_receipt = Mock(return_value=Decimal("0.42"))
                with self.assertRaises(ValueError):
                    ctrl.launch()
        self.assertEqual(self.api.calls, [])
        self.public.assert_not_called()
        self.ci.assert_not_called()

    def test_full_lifetimes_cannot_borrow_contingency(self):
        self.ctrl = self.controller("main")
        self.ctrl.cheap_receipt = Mock(return_value=Decimal("11"))
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertFalse(any(m == "POST" for m, _, _ in self.api.calls))

    def test_live_clock_includes_retrieval_and_cannot_move_backwards(self):
        self.launched()
        self.advance(1100)
        self.ctrl.cost_check(self.api.pod, 60)
        self.advance(41)
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod, 60)
        self.current -= timedelta(seconds=100)
        with self.assertRaises(ValueError):
            self.ctrl.cost_check(self.api.pod)

    def test_only_hf_is_sent_on_stdin_and_never_in_ledger(self):
        self.main_started()
        self.ctrl._ssh = Mock(return_value=b"")
        with patch.object(c, "sparse_paths", return_value=[c.PLAN_RELATIVE]):
            self.ctrl.start_worker()
        calls = self.ctrl._ssh.call_args_list
        transfer = next(call for call in calls if "data" in call.kwargs)
        self.assertEqual(transfer.kwargs["data"], b"export HF_TOKEN=hf_placeholder_only\n")
        self.assertNotIn("hf_placeholder_only", transfer.args[1])
        script = calls[-1].args[1]
        self.assertIn("env -i", script)
        self.assertIn("worker-closing.json", script)
        self.assertIn("bilingual_llama_b1.runner", script)
        for secret in ("hf_placeholder_only", "rp_placeholder_only", "openai_placeholder_only", "anthropic_placeholder_only"):
            self.assertNotIn(secret, self.ctrl.ledger.path.read_text())
            self.assertNotIn(secret, script)
        with self.assertRaises(ValueError):
            self.ctrl.start_worker()

    def test_first_two_uses_all_76_manifest_timings_and_no_outcome(self):
        receipt, report, files = self.barrier(changed={"scientific_pass": False})
        self.ctrl.approve("first-two", self.ctrl.plan_hash)
        result = next(e["data"] for e in self.ctrl.ledger.read() if e["id"].startswith("throughput-gate:"))
        self.assertEqual(result["observed_generations"], 76)
        self.assertEqual(result["remaining_generation_seconds"], "684")
        self.assertEqual(result["projected_lifetime_seconds"], "3089.20")
        self.ctrl._write_remote.assert_called_once_with(self.api.pod, "APPROVE-first-two",
                                                       (self.ctrl.plan_hash + "\n").encode())
        self.assertIsNotNone(self.ctrl.event("approved:first-two"))

    def test_qualification_has_no_scientific_decision(self):
        self.barrier("qualification")
        self.ctrl.approve("qualification", self.ctrl.plan_hash)
        self.assertFalse(any(e["id"].startswith("throughput-gate:") for e in self.ctrl.ledger.read()))

    def test_incomplete_or_test_only_audit_blocks_approval(self):
        self.barrier()
        for change in ({"rows": 2}, {"pass": False}, {"production_eligible": False},
                       {"partial_generation_ids": ["partial"]}, {"unresolved_generation_dispatches": ["uncertain"]},
                       {"partial_generation_ids": None}, {"generations": 75}):
            original_report = deepcopy(c.audit.return_value)
            c.audit.return_value.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ctrl.approve("first-two", self.ctrl.plan_hash)
            c.audit.return_value = original_report
        self.ctrl._write_remote.assert_not_called()

    def test_live_binding_previous_approval_and_terminal_are_required(self):
        _, _, files = self.barrier()
        original_barrier = deepcopy(files["WAITING-first-two.json"])
        for change in ({"rows": True}, {"rows": 4}, {"freeze_commit": "b" * 40}, {"plan_sha256": "b" * 64}):
            files["WAITING-first-two.json"] = {**original_barrier, **change}
            with self.assertRaises(ValueError):
                self.ctrl.approve("first-two", self.ctrl.plan_hash)
        files["WAITING-first-two.json"] = original_barrier
        files["_approvals"].clear()
        with self.assertRaises(ValueError):
            self.ctrl.approve("first-two", self.ctrl.plan_hash)
        files["_approvals"]["APPROVE-qualification"] = self.ctrl.plan_hash
        files["DONE-all.json"] = {}
        with self.assertRaises(ValueError):
            self.ctrl.approve("first-two", self.ctrl.plan_hash)
        self.ctrl._write_remote.assert_not_called()

    def test_corrupt_or_incomplete_timing_inventory_cannot_approve(self):
        receipt, report, _ = self.barrier()
        path = Path(receipt["data"]["directory"]) / next(n for n in receipt["data"]["artifacts"] if n.startswith("generations/"))
        path.write_bytes(c._canonical({"elapsed_seconds": 100}))
        with self.assertRaises(ValueError):
            self.ctrl.approve("first-two", self.ctrl.plan_hash)
        self.ctrl._write_remote.assert_not_called()

    def test_audited_missing_outcome_is_not_a_scientific_gate(self):
        receipt, report, _ = self.barrier()
        root = Path(receipt["data"]["directory"])
        name = "generations/" + self.plan_data["blocks"][0]["cells"][0]["id"] + ".json"
        (root / name).unlink()
        self.ctrl.record("retrieval", {"directory": str(root), "pod_id": self.ctrl.owned()["id"],
                                       "artifacts": c.artifact_map(root)})
        report.update(generations=75, blocked_cells=1)
        self.ctrl.approve("first-two", self.ctrl.plan_hash)
        result = next(e["data"] for e in self.ctrl.ledger.read() if e["id"].startswith("throughput-gate:"))
        self.assertEqual(result["observed_generations"], 75)
        self.assertEqual(result["total_generations"], 760)

    def test_slow_first_two_has_no_bulk_approval(self):
        self.barrier(timing=20)
        self.advance(1000)
        with self.assertRaisesRegex(ValueError, "760 generations"):
            self.ctrl.approve("first-two", self.ctrl.plan_hash)
        self.ctrl._write_remote.assert_not_called()
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.assertEqual(self.ctrl.monitor(), "closed")

    def test_look_decisions_are_not_exposed(self):
        for name in ("first-five", "look12", "look20"):
            with self.assertRaises(ValueError):
                self.ctrl.approve(name, self.ctrl.plan_hash)
        self.assertFalse(hasattr(self.ctrl, "decision"))
        self.assertEqual(self.api.calls, [])

    def test_done_closes_without_any_judge_wait(self):
        self.main_started()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod, "files": {"DONE-all.json": {}}})
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.ctrl.retrieve = Mock()
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.ctrl.retrieve.assert_not_called()

    def test_judge_halt_closes_while_generation_is_active(self):
        self.main_started()
        self.ctrl.status = Mock(return_value={"pod": self.api.pod,
            "files": {"_progress": {"generations/active.json": [1, 1]}}})
        self.ctrl.retrieve = Mock(return_value={"data": {"artifacts": {}}})
        self.ctrl.close_until_verified = Mock(return_value="retrieved-and-closed")
        from experiments.bilingual_llama_b1.halt import write_halt
        def fail_judging(_):
            write_halt(self.out / "JUDGING-HALT.json", self.ctrl.plan_hash,
                       FREEZE, "JudgeHalted")
        self.ctrl.sleep = Mock(side_effect=fail_judging)
        self.assertEqual(self.ctrl.monitor(), "retrieved-and-closed")
        self.assertEqual(self.ctrl.status.call_count, 1)
        self.ctrl.close_until_verified.assert_called_once()
        self.assertTrue(any(e["id"].startswith("monitor-failed:") for e in self.ctrl.ledger.read()))

    def test_judge_halt_blocks_barrier_approval(self):
        self.barrier(timing=1)
        from experiments.bilingual_llama_b1.halt import write_halt
        write_halt(self.out / "JUDGING-HALT.json", self.ctrl.plan_hash, FREEZE, "JudgeHalted")
        with self.assertRaises(ValueError):
            self.ctrl.approve("first-two", self.ctrl.plan_hash)
        self.ctrl._write_remote.assert_not_called()

    def test_malformed_judge_halt_prevents_rental(self):
        (self.out / "JUDGING-HALT.json").write_text("{broken")
        with self.assertRaises(ValueError):
            self.ctrl.launch()
        self.assertEqual(self.api.calls, [])

    def test_monitor_counts_heartbeat_and_never_autoapproves(self):
        self.main_started()
        self.ctrl.cost_check = Mock()
        states = [{"pod": self.api.pod, "files": {"_progress": {"_progress": [i, i]}}} for i in range(3)]
        states.append({"pod": self.api.pod, "files": {"DONE-all.json": {}}})
        self.ctrl.status = Mock(side_effect=states)
        self.ctrl.retrieve = Mock(return_value={"data": {"artifacts": {}}})
        self.ctrl.sleep = Mock(side_effect=lambda _: self.advance(800))
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.assertEqual(self.ctrl.status.call_count, 4)
        self.assertFalse(any(e["id"].startswith("approved:") for e in self.ctrl.ledger.read()))

    def test_transient_monitor_failures_retry_then_close(self):
        self.launched()
        self.ctrl.status = Mock(side_effect=RuntimeError("transient SSH"))
        self.ctrl.close_until_verified = Mock(return_value="closed")
        self.assertEqual(self.ctrl.monitor(), "closed")
        self.assertEqual(self.ctrl.status.call_count, 3)
        self.assertEqual(self.ctrl.sleep.call_count, 2)

    def test_cleanup_retries_without_recreating(self):
        self.launched()
        self.ctrl.terminate = Mock(side_effect=[RuntimeError("retrieve"), ValueError("hash"), "closed"])
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.ctrl.close_until_verified(), "closed")
        self.assertEqual(self.ctrl.sleep.call_count, 2)
        self.assertEqual(sum(m == "POST" for m, _, _ in self.api.calls), 1)

    def test_delete_requires_direct_404_and_empty_owned_inventory(self):
        self.launched()
        self.snapshots()
        self.api.deleted = False
        request = self.api.request
        def keep_visible(method, path, body=None):
            if method == "DELETE":
                return 204, None
            return request(method, path, body)
        self.api.request = keep_visible
        with self.assertRaisesRegex(ValueError, "Deletion unverified"):
            self.ctrl.terminate()
        self.assertIsNone(self.ctrl.event("closed"))


def test_budget_exact_protocol_contract_and_no_contingency_reallocation():
    assert c.BUDGET == protocol.BUDGET
    assert (c.MAIN_SECONDS, c.CHEAP_SECONDS, c.RESERVE_SECONDS) == (18000, 1800, 600)
    assert c.checked_budget({"budget": protocol.BUDGET}) == c.BUDGET
    assert c.API_CAP_USD == Decimal("125")
    assert c.PRIOR_JUDGING_USD == Decimal("2.726282")
    assert c.GPU_CAP_USD + c.API_CAP_USD + c.TRANSLATION_QA_STORAGE_USD + c.CONTINGENCY_USD == Decimal("200")
    for change in ({"prior_usd": "79.8"}, {"gpu_cap_usd": "95"},
                   {"prior_judging_usd": "0"}, {"prior_judging_included_in_api_cap": False},
                   {"api_cap_usd": "90"}, {"total_usd": "202.726282"},
                   {"contingency_automatic_reallocation": True}, {"cheap_seconds": 1200}):
        with pytest.raises(ValueError):
            c.checked_budget({"budget": {**c.BUDGET, **change}})


def test_conservative_decimal_projection_and_exact_bounds():
    result = c.conservative_projection([1] * 76, elapsed_seconds=1000, hourly_usd="6.89", prior_gpu_usd="0.42")
    assert result["pass"] is True
    assert Decimal(result["projected_lifetime_seconds"]) == Decimal("3089.2")
    assert Decimal(result["projected_gpu_usd"]) == Decimal("0.42") + Decimal("3089.2") * Decimal("6.89") / 3600
    # All long calls count, including sources. Tokens/answer-only time cannot hide them.
    assert not c.conservative_projection([20] * 76, elapsed_seconds=2000,
        hourly_usd="6.89", prior_gpu_usd="0.42")["pass"]
    assert not c.conservative_projection([1] * 76, elapsed_seconds=1000,
        hourly_usd="6.89", prior_gpu_usd="44")["pass"]
    edge = Decimal(c.MAIN_SECONDS) - 1200 - Decimal("684") * Decimal("1.30")
    assert not c.conservative_projection([1] * 76, elapsed_seconds=edge,
        hourly_usd="1", prior_gpu_usd="0")["pass"]
    assert c.conservative_projection([1] * 76, elapsed_seconds=edge - Decimal("0.001"),
        hourly_usd="1", prior_gpu_usd="0")["pass"]


@pytest.mark.parametrize("timings", [[], [0], [-1], [True], [float("nan")], [float("inf")], [None], [1] * 760, [2000]])
def test_invalid_timings_fail_closed(timings):
    with pytest.raises(ValueError):
        c.conservative_projection(timings, elapsed_seconds=1000, hourly_usd="6.89", prior_gpu_usd="0")


def test_fixture_gate_hash_pass_inventory_and_safe_path(tmp_path, monkeypatch):
    path = tmp_path / "fixture.json"
    fixtures = [{"id": "synthetic"}]
    proof = {"plan_sha256": "a" * 64, "freeze_commit": FREEZE, "pass": True,
             "judgment_count": 128, "receipts": {"judgments.jsonl": {"sha256": "c" * 64}},
             "fixture_inventory_sha256": hashlib.sha256(c._canonical(fixtures)).hexdigest()}
    path.write_bytes(c._canonical(proof))
    plan = {"fixtures": fixtures}
    recompute = Mock(return_value=proof)
    monkeypatch.setattr(c, "fixture_proof", recompute)
    assert c.fixture_gate(path, plan, "a" * 64, FREEZE)["artifact_sha256"] == c.sha(path)
    recompute.assert_called_once_with(plan, "a" * 64, FREEZE)
    for change in ({"pass": False}, {"pass": 1}, {"fixture_inventory_sha256": "a" * 64},
                   {"judgment_count": 127}, {"receipts": {}}, {"plan_sha256": "b" * 64},
                   {"freeze_commit": "b" * 40}):
        path.write_bytes(c._canonical({**proof, **change}))
        with pytest.raises(ValueError):
            c.fixture_gate(path, plan, "a" * 64, FREEZE)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        c.fixture_gate(link, plan, "a" * 64, FREEZE)
    recompute.side_effect = ValueError("Actual receipts fail")
    path.write_bytes(c._canonical(proof))
    with pytest.raises(ValueError):
        c.fixture_gate(path, plan, "a" * 64, FREEZE)


def test_fixture_proof_reads_canonical_ledger_and_recomputes_gate(tmp_path, monkeypatch):
    from experiments.bilingual_llama_b1 import judges
    monkeypatch.setattr(c, "OWNED_OUT", tmp_path)
    root = tmp_path / "judges"
    root.mkdir()
    for name in (".judge.lock", "requests.jsonl", "attempts.jsonl", "judgments.jsonl", "snapshots.jsonl"):
        (root / name).touch()
    fixtures = judges.fixture_inventory()
    plan = {"budget": deepcopy(c.BUDGET), "fixtures": fixtures, "judges": judges.judge_config()}
    finals = {f"fixtures:{provider}:{instrument}:{item['id']}": {"status": "ok"}
              for item in fixtures for provider in judges.MODELS for instrument in judges.INSTRUMENTS}
    state = {"finals": finals, "translations": {}, "unknown_attempts": [], "failed_instruments": [],
             "model_drift": False, "budget_spent_usd": {"judges": "2.726282", "translation": 0}}
    validator = Mock(return_value=state)
    gate = Mock(return_value={"pass": True, "missing": [], "failures": []})
    projection = {"pass": True, "api_cap_usd": "125", "projected_total_usd": "20",
                  "spent_usd": "2.726282",
                  "by_instrument": {p + ":" + i: {"remaining_calls": 496}
                                    for p in judges.MODELS for i in judges.INSTRUMENTS}}
    project = Mock(return_value=projection)
    monkeypatch.setattr(judges, "validate_receipts", validator)
    monkeypatch.setattr(judges, "fixture_gate", gate)
    monkeypatch.setattr(judges, "project_budget", project)
    monkeypatch.setattr(judges.Ledger, "__enter__", Mock(side_effect=AssertionError("Write context forbidden")))
    before = c.artifact_map(root)
    result = c.fixture_proof(plan, "a" * 64, FREEZE)
    assert result["judgment_count"] == 128
    assert result["judge_budget_projection"] == projection
    assert result["prior_judging_usd"] == result["cumulative_judging_usd"] == "2.726282"
    assert result["inherited_a1_judging_usd"] == "0"
    assert result["new_fixture_calls"] == 0
    assert result["inherited_fixture_freeze"] == "5398dc657b6af3255e5938539f27255ffbe74b0d"
    project.assert_called_once_with([], [], plan)
    assert set(result["receipts"]) == set(judges.RECEIPT_FILES)
    assert all(binding == {"records": 0, "bytes": 0, "head_sha256": None,
                           "sha256": hashlib.sha256(b"").hexdigest()}
               for binding in result["receipts"].values())
    assert c.artifact_map(root) == before
    assert validator.call_args.args[0].root == root
    assert validator.call_args.args[1:] == (plan, "a" * 64, FREEZE, [])
    gate.assert_called_once_with(finals, fixtures)
    monkeypatch.setattr(c, "_require_ignored", Mock())
    published = c.write_fixture_proof(tmp_path / "fixture-gate.json", plan, "a" * 64, FREEZE)
    assert published == result
    assert c.fixture_gate(tmp_path / "fixture-gate.json", plan, "a" * 64, FREEZE)["artifact_sha256"] == c.sha(tmp_path / "fixture-gate.json")
    gate.return_value = {"pass": False}
    with pytest.raises(ValueError):
        c.fixture_proof(plan, "a" * 64, FREEZE)
    gate.return_value = {"pass": True}
    state["finals"] = dict(list(finals.items())[:-1])
    with pytest.raises(ValueError):
        c.fixture_proof(plan, "a" * 64, FREEZE)
    state["finals"] = finals
    for change in ({"pass": False}, {"projected_total_usd": "125.01"}, {"by_instrument": {}},
                   {"api_cap_usd": "140"}, {"spent_usd": "0"},
                   {"projected_total_usd": "2"}):
        project.return_value = {**projection, **change}
        with pytest.raises(ValueError):
            c.fixture_proof(plan, "a" * 64, FREEZE)
    project.return_value = projection
    for wrong in ("0", "5.452564"):
        state["budget_spent_usd"]["judges"] = wrong
        with pytest.raises(ValueError, match="carry"):
            c.fixture_proof(plan, "a" * 64, FREEZE)
    state["budget_spent_usd"]["judges"] = "2.726282"
    state["unknown_attempts"] = ["uncertain"]
    with pytest.raises(judges.JudgeHalted):
        c.fixture_proof(plan, "a" * 64, FREEZE)


def test_real_empty_judge_receipts_cannot_self_attest(tmp_path, monkeypatch):
    from experiments.bilingual_llama_b1 import judges
    monkeypatch.setattr(c, "OWNED_OUT", tmp_path)
    root = tmp_path / "judges"
    root.mkdir()
    for name in (".judge.lock", "requests.jsonl", "attempts.jsonl", "judgments.jsonl", "snapshots.jsonl"):
        (root / name).touch()
    plan = {"budget": deepcopy(c.BUDGET), "fixtures": judges.fixture_inventory(), "judges": judges.judge_config(),
            "translation_item_ids": protocol.translation_ids()}
    with pytest.raises(ValueError, match="Inherited fixture prefix changed or missing"):
        c.fixture_proof(plan, "a" * 64, FREEZE)


def test_proof_writer_is_explicit_write_once_and_outside_input_root(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "OWNED_OUT", tmp_path)
    monkeypatch.setattr(c, "_require_ignored", Mock())
    monkeypatch.setattr(c, "fixture_proof", Mock(return_value={"pass": True}))
    path = tmp_path / "fixture-proof.json"
    c.write_fixture_proof(path, {}, "a" * 64, FREEZE)
    c.write_fixture_proof(path, {}, "a" * 64, FREEZE)
    c.fixture_proof.return_value = {"pass": False}
    with pytest.raises(ValueError, match="never overwrite"):
        c.write_fixture_proof(path, {}, "a" * 64, FREEZE)
    with pytest.raises(ValueError):
        c.write_fixture_proof(tmp_path / "judges/proof.json", {}, "a" * 64, FREEZE)


@pytest.mark.parametrize("unsafe", [".env", "secrets/token.json", "weights/config.json",
    "experiments/model.safetensors", "data/weights.bin", "data/evil.env.json",
    "data/../key.json", "/tmp/a.py", "out/secret.json", "experiments/.hidden/x.py"])
def test_sparse_payload_rejects_secret_and_incidental_weights(monkeypatch, unsafe):
    monkeypatch.setattr(protocol, "source_paths", lambda: [unsafe])
    with pytest.raises(ValueError):
        c.sparse_paths({"input_hashes": {}})


def test_worker_shell_exact_runtime_venv_cuda_tests_and_no_judging(monkeypatch):
    monkeypatch.setattr(c, "sparse_paths", lambda: [c.PLAN_RELATIVE, *c.TESTS])
    for kind in ("cheap", "main"):
        script = c.worker_script(kind, c.PLAN_RELATIVE, FREEZE, UTC.isoformat())
        subprocess.run(["bash", "-n"], input=script, text=True, check=True, capture_output=True)
        assert "python3 -m venv --system-site-packages" in script
        assert c.REMOTE + "/venv/bin/python -m pip install" in script
        assert "git checkout --detach " + FREEZE in script
        assert "--no-checkout" in script and "sparse-checkout set --no-cone" in script
        assert "OPENAI_API_KEY" not in script and "RUNPOD_API_KEY" not in script
        assert "ANTHROPIC_API_KEY" not in script and "load_dotenv" not in script
        assert "look12" not in script and "look20" not in script
    cheap = c.worker_script("cheap", c.PLAN_RELATIVE, FREEZE, UTC.isoformat())
    assert "INSTRUCTION_TEST_DEVICE=cuda" in cheap
    assert all(name in cheap for name in c.TESTS)
    assert "tests/test_instruction_state_backend.py" in cheap
    assert "tests/test_pilot_b1_lifecycle.py" in cheap
    assert "-r experiments/bilingual_llama_b1/requirements-gpu.txt" in cheap
    main = c.worker_script("main", c.PLAN_RELATIVE, FREEZE, UTC.isoformat())
    assert "-m experiments.bilingual_llama_b1.runner" in main
    assert "--deadline-utc" in main


def test_cli_cannot_enable_mutations_implicitly(monkeypatch):
    api = Mock(side_effect=AssertionError("Provider construction forbidden"))
    monkeypatch.setattr(c.base, "RunPodV2", api)
    for action in ("create", "monitor", "retrieve", "status", "approve", "close", "reconcile", "decision"):
        with pytest.raises(SystemExit):
            c.main(["--freeze", FREEZE, "--kind", "main", "--action", action])
    with pytest.raises(SystemExit):
        c.main(["--freeze", FREEZE, "--kind", "main", "--action", "create", "--launch",
                "--approved-new-cap-usd", "200", "--approval-ref", "synthetic", "--approval-file", "synthetic"])
    api.assert_not_called()


def test_sparse_checkout_includes_all_hashed_inputs_and_shared_dependencies():
    plan = protocol.build_plan()
    paths = set(c.sparse_paths(plan))
    assert set(plan["input_hashes"]) <= paths
    assert set(plan["source_hashes"]) <= paths
    assert protocol.TOKEN_BINDINGS_PATH == "data/bilingual_llama_pilot/plan_20261001/token_bindings.json"
    assert protocol.TOKEN_BINDINGS_PATH in paths
    assert {
        "experiments/bilingual_llama_pilot/prompts.py",
        "experiments/bilingual_llama_pilot/analysis.py",
        "experiments/bilingual_llama_b1/runner.py",
        "experiments/bilingual_llama_b1/raw_audit.py",
        "experiments/bilingual_llama_b1/requirements-gpu.txt",
    } <= paths
    prior = protocol.PRIOR_RELEASE + "/"
    receipts = {name for name in plan["input_hashes"] if name.startswith(prior)}
    assert len(receipts) == 6
    assert {prior + "MANIFEST.json", prior + "AUDIT.json"} <= receipts
    assert len({name for name in receipts if name.endswith(".jsonl")}) == 4
    # The prospective B1 plan is generated only after these source tests pass.
    assert all((c.ROOT / name).is_file() for name in paths - {c.PLAN_RELATIVE})


def test_sparse_checkout_rejects_unbound_receipt_file(monkeypatch):
    monkeypatch.setattr(protocol, "source_paths", lambda: ["data/unbound.jsonl"])
    with pytest.raises(ValueError, match="Unsafe sparse"):
        c.sparse_paths({"input_hashes": {}})


def test_inherited_a1_fixtures_remain_disjoint_from_original_failed_gate():
    from experiments.bilingual_llama_b1 import judges
    from experiments.bilingual_llama_pilot import judges as original_judges
    current = {item["id"] for item in judges.fixture_inventory()}
    previous = {item["id"] for item in original_judges.fixture_inventory()}
    assert len(current) == len(previous) == 32
    assert not current & previous


def _make_run(tmp_path, backend=None, *, barriers=False):
    from experiments.bilingual_llama_b1.runner import Study
    from tests.test_instruction_state_runner import FakeBackend
    backend = backend or FakeBackend()
    messages = [{"role": "user", "content": "serialization fixture"}]
    rendered, ids = backend.serialize(messages)
    value = {"blocks": protocol.inventory(), "generation": dict(protocol.GENERATION),
        "budget": {"reserve_seconds": 600},
        "token_bindings": {"model_id": protocol.MODEL_ID, "revision": protocol.MODEL_REVISION,
            "tokenizer_files": {}, "cases": {"fixture": {"messages": messages,
                "input_token_ids": ids[0].tolist(),
                "rendered_input_sha256": hashlib.sha256(rendered.encode()).hexdigest()}}}}
    path = tmp_path / "plan.json"
    if not path.exists():
        path.write_text(protocol.canonical(value) + "\n")
    run = Study(value, path, "a" * 40, tmp_path / "out", "2100-01-01T00:00:00+00:00",
        factory=lambda **_: backend, clock=lambda: 0, barriers=barriers,
        allow_test=True, sleep=lambda _: (_ for _ in ()).throw(AssertionError("Unexpected wait")))
    return run, backend


def test_b1_runner_complete_fixed_inventory_and_no_rerun(tmp_path):
    from experiments.bilingual_llama_b1.raw_audit import items_from_raw
    from experiments.bilingual_llama_pilot import protocol as original_protocol
    seen = []

    def approve(name, run):
        seen.append((name, len(run.completed)))
        (run.out / ("APPROVE-" + name)).write_text(run.plan_hash)

    run, backend = _make_run(tmp_path, barriers=approve)
    assert run.plan["blocks"] == original_protocol.inventory()
    result = run.execute()
    assert result["n_blocks"] == 20 and result["complete"]
    assert not result["behavioral_qualified"] and not result["stage_b_started"]
    assert seen == [("qualification", 1), ("first-two", 3)]
    assert len(backend.calls) == 763
    assert run.audit(partial=False)["generations"] == 760
    assert run.ledger.read()[1]["data"]["study"] == "bilingual_llama_measurement_b1"
    assert len(items_from_raw(run.out, run.plan, n_blocks=20)) == 480
    restarted, fresh = _make_run(tmp_path)
    assert restarted.execute() == result and not fresh.calls


def test_b1_runner_uncertain_dispatch_not_retried(tmp_path):
    from tests.test_instruction_state_runner import FakeBackend
    run, _ = _make_run(tmp_path, FakeBackend(fail_at=6))
    with pytest.raises(RuntimeError, match="interrupted"):
        run.execute()
    assert len(run.audit()["unresolved_generation_dispatches"]) == 1
    resumed, fresh = _make_run(tmp_path)
    with pytest.raises(RuntimeError, match="Unresolved prior generation"):
        resumed.execute()
    assert fresh.calls == []


def test_b1_missing_source_remains_missing_and_transcripts_preserved(tmp_path):
    from tests.test_instruction_state_runner import FakeBackend
    spec = protocol.inventory()[0]
    target = next(s for s in spec["sources"] if s["condition"] == "self")
    run, _ = _make_run(tmp_path, FakeBackend(empty_seeds=[target["seed"]]))
    run.row("qualification-live", lambda: {"id": "qualification-live", "result": run.model().qualify()})
    row = run.row(spec["id"], lambda: run.block(spec))
    assert len(row["sources"]) == 14 and len(row["responses"]) == 28
    blocked = [r for r in row["responses"] if r["transcript"] == "self"]
    assert len(blocked) == 8
    assert all(r["status"] == "blocked_empty_source" and r["generation"] is None for r in blocked)
    assert run.audit()["blocked_cells"] == 8
    for response in row["responses"]:
        if response["generation"] is not None and response["source_generation_id"] is not None:
            source = row["sources"][response["source_generation_id"]]["response"]
            assert response["generation"]["messages"][1]["content"] == source
            assert source.startswith("  ")


def test_b1_raw_audit_rejects_corruption_and_v1_runtime(tmp_path):
    from experiments.bilingual_llama_b1.raw_audit import raw_audit
    from tests.test_bilingual_runner import make_run as make_original
    old, _ = make_original(tmp_path)
    with pytest.raises(ValueError, match="Runtime binding mismatch"):
        raw_audit(old.out, old.plan, allow_test=True)
    new_dir = tmp_path / "a1"
    new_dir.mkdir()
    run, _ = _make_run(new_dir)
    run.row("qualification-live", lambda: {"id": "qualification-live", "result": run.model().qualify()})
    path = run.out / "rows/qualification-live.json"
    value = json.loads(path.read_text())
    value["result"]["pass"] = False
    path.write_text(protocol.canonical(value) + "\n")
    with pytest.raises(ValueError, match="hash"):
        run.audit()


def test_b1_release_reuses_analysis_but_keeps_phases_distinct():
    from experiments.bilingual_llama_b1 import release
    from experiments.bilingual_llama_pilot import analysis
    assert release.analysis is analysis
    rows = {phase: {"phase": phase, "status": "ok", "item_id": "same-id",
        "provider": "openai", "instrument": "paper", "label": value}
        for phase, value in (("fixtures", 1), ("target", 0), ("translated", 1))}
    assert release.phase_labels(rows, phase="target") == {("same-id", "openai", "paper"): 0}
    assert release.phase_labels(rows, phase="translated") == {("translated:same-id", "openai", "paper"): 1}
    assert release.phase_labels({"bad": {"phase": "target", "status": "schema_failure"}}, phase="target") == {}
    with pytest.raises(ValueError, match="Duplicate"):
        release.phase_labels({"one": rows["target"], "two": rows["target"]}, phase="target")


def test_b1_release_never_overwrites_input_directory(tmp_path):
    from experiments.bilingual_llama_b1 import release
    raw, judge = tmp_path / "raw", tmp_path / "judge"
    raw.mkdir()
    judge.mkdir()
    (raw / "sentinel.json").write_text("{}\n")
    before = release._tree_hashes(raw)
    for destination in (raw, judge, raw / "derived", judge / "derived", tmp_path):
        with pytest.raises(ValueError, match="new derived-output"):
            release.reproduce(raw, judge, tmp_path / "unused-plan.json", FREEZE, destination)
    assert release._tree_hashes(raw) == before


def test_b1_release_manifest_has_public_file_inventory(tmp_path, monkeypatch):
    from experiments.bilingual_llama_b1 import release
    raw, judge, output = (tmp_path / name for name in ("raw", "judge", "derived"))
    raw.mkdir()
    judge.mkdir()
    (raw / "input.json").write_text("{}\n")
    path = tmp_path / "PLAN.json"
    path.write_text("{}\n")
    plan_hash = protocol.sha(path)
    plan = {"fixtures": [], "translation_item_ids": [str(i) for i in range(16)]}
    items = [{"id": str(i), "missing": True} for i in range(480)]
    selected = items[:16]
    translated = [{"id": item["id"], "source_item_id": item["id"]} for item in selected]
    state = {"finals": {str(i): {"phase": "fixtures", "status": "ok"} for i in range(128)},
        "translations": {}, "unknown_attempts": [], "failed_instruments": [], "model_drift": False,
        "spent_usd": 2.726282, "budget_spent_usd": {"judges": 2.726282, "translation": 0}, "models": {}}
    monkeypatch.setattr(release, "bind_sources", lambda *_: plan)
    monkeypatch.setattr(release, "raw_audit", lambda *a, **k: {"plan_sha256": plan_hash,
        "freeze_commit": FREEZE, "n_blocks": 20, "production_eligible": True})
    monkeypatch.setattr(release, "items_from_raw", lambda *a, **k: items)
    monkeypatch.setattr(release.judges, "normalize_items", lambda value: value)
    monkeypatch.setattr(release.judges, "validate_receipts", lambda *a: state)
    monkeypatch.setattr(release.judges, "fixture_gate", lambda *a: {"pass": True})
    monkeypatch.setattr(release, "selected_items", lambda *a: selected)
    monkeypatch.setattr(release, "translated_items", lambda *a: translated)
    monkeypatch.setattr(release.analysis, "analyze_items", lambda *a: {})
    monkeypatch.setattr(release.analysis, "analyze_translation_pairs", lambda *a: {})

    def outputs(result, out, **kwargs):
        out.mkdir()
        (out / "analysis.json").write_text(json.dumps(result) + "\n")
        (out / "counts.csv").write_text("condition,n\nmissing,480\n")

    monkeypatch.setattr(release.analysis, "write_outputs", outputs)
    result = release.reproduce(raw, judge, path, FREEZE, output)
    manifest = json.loads((output / "MANIFEST.json").read_text())
    assert result["pass"] and result["outputs"] == 2
    assert manifest["schema"] == "bilingual-analysis-manifest-b1"
    assert manifest["outputs"] == {item["path"]: item["sha256"] for item in manifest["files"]}
    assert isinstance(manifest["files"], list) and len(manifest["files"]) == 2
    for item in manifest["files"]:
        assert set(item) == {"path", "bytes", "sha256"}
        artifact = output / item["path"]
        assert artifact.stat().st_size == item["bytes"]
        assert protocol.sha(artifact) == item["sha256"]
    assert manifest["raw_input_hashes"] == release._tree_hashes(raw)
    assert manifest["judge_input_hashes"] == release._tree_hashes(judge)
    assert manifest["original_inputs_unchanged"] is True
