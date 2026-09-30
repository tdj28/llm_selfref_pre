"""Offline A1 lifecycle proof; real protected-/proc integration runs on Linux."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
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
import unittest
from unittest.mock import Mock, patch

from experiments.sae_assay_exposure_lifecycle_a1 import controller as c, protocol as p
from tests import test_sae_assay_exposure_controller as prior


class ProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.remote, self.proc = self.root / "remote", self.root / "proc"
        (self.remote / "out").mkdir(parents=True)
        self.proc.mkdir()
        self.binding = {"worker_id": "c" * 32, "pod_id": "synthetic-owned",
                        "freeze_commit": "a" * 40, "plan_sha256": "b" * 64}
        self.signals, self.reads = [], []
        self.denied = set()
        read = Path.read_bytes

        def read_bytes(path):
            self.reads.append(path)
            if path in self.denied:
                raise PermissionError("protected fixture secret must not leak")
            return read(path)
        self.patch = patch.object(Path, "read_bytes", read_bytes)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        patcher = patch("os.killpg", side_effect=self.kill)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("time.sleep", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.process(531)
        self.denied.add(self.proc / "531/environ")

    def process(self, pid, *, marked=False, group=None, session=None, state="S", argv=None):
        directory = self.proc / str(pid)
        directory.mkdir(exist_ok=True)
        fields = [state, "1", str(group or pid), str(session or group or pid)] + ["0"] * 15 + ["1234"]
        (directory / "stat").write_text(str(pid) + " (fixture ) name) " + " ".join(fields))
        markers = ["CODEX_EXPOSURE_NAMESPACE=exposure-controller"] + [
            "CODEX_EXPOSURE_" + k.upper() + "=" + self.binding[v]
            for k, v in (("worker_id", "worker_id"), ("freeze", "freeze_commit"), ("pod_id", "pod_id"))]
        (directory / "environ").write_bytes(b"\0".join(s.encode() for s in markers) if marked else b"")
        command = argv if argv is not None else ["timeout", "120s", "env", *markers] if marked else ["foreign-service"]
        (directory / "cmdline").write_bytes(b"\0".join(s.encode() for s in command))

    def kill(self, pid, sig):
        self.signals.append((pid, sig))
        self.assertNotEqual(pid, 531)
        for directory in list(self.proc.iterdir()):
            fields = (directory / "stat").read_text().rsplit(") ", 1)[1].split()
            if fields[2] != str(pid):
                continue
            if sig in (signal.SIGTERM, signal.SIGKILL):
                shutil.rmtree(directory)
            else:
                fields[0] = "T" if sig == signal.SIGSTOP else "S"
                (directory / "stat").write_text(directory.name + " (fixture) " + " ".join(fields))

    def reconcile(self, action="stop"):
        return c.reconcile_worker(self.remote, self.binding, action, proc_root=self.proc)

    def test_known_group_pause_resume_stop_never_reads_foreign_environment(self):
        self.process(604, marked=True)
        self.process(605, group=604)
        (self.remote / "worker.pid").write_text("604\n")
        for action in ("pause", "resume", "stop"):
            self.assertTrue(self.reconcile(action)["verified"])
        self.assertEqual(self.signals, [(604, signal.SIGSTOP), (604, signal.SIGCONT),
                                        (604, signal.SIGCONT), (604, signal.SIGTERM)])
        self.assertNotIn(self.proc / "531/environ", self.reads)
        self.assertNotIn(self.proc / "531/cmdline", self.reads)
        self.assertTrue((self.proc / "531").exists())

    def test_owned_inaccessible_or_wrong_leader_remains_fail_closed(self):
        self.process(604, argv=["timeout", "120s", "not-our-markers"])
        (self.remote / "worker.pid").write_text("604\n")
        with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
            self.reconcile()
        self.denied.update({self.proc / "604/cmdline", self.proc / "604/environ"})
        with self.assertRaisesRegex(RuntimeError, "identity inaccessible"):
            self.reconcile()
        self.assertFalse(self.signals)
        self.assertFalse((self.remote / "out/controller-stopped.json").exists())

    def test_missing_pid_recovers_exact_timeout_not_foreign_protected_env(self):
        self.process(604, marked=True)
        self.process(605, group=604)
        result = self.reconcile()
        self.assertTrue(result["missing_pid"] and result["recovered_pid"])
        self.assertEqual(result["pid"], 604)
        self.assertNotIn(self.proc / "531/environ", self.reads)
        before = (self.remote / "out/controller-stopped.json").read_bytes()
        self.assertTrue(self.reconcile()["verified"])
        self.assertEqual(before, (self.remote / "out/controller-stopped.json").read_bytes())

    def test_missing_pid_no_worker_fences_without_reading_any_environ(self):
        result = self.reconcile()
        self.assertIsNone(result["pid"])
        self.assertTrue(result["dispatch_fenced"])
        self.assertFalse(any(path.name == "environ" for path in self.reads))
        self.assertFalse(self.signals)

    def test_missing_pid_inflight_ssh_and_multiple_groups_are_not_signalled(self):
        marker = "CODEX_EXPOSURE_WORKER_ID=" + self.binding["worker_id"]
        self.process(604, argv=["bash", "-c", "env " + marker + " some-command"])
        with self.assertRaisesRegex(RuntimeError, "in-flight"):
            self.reconcile()
        self.process(604, marked=True)
        self.process(701, marked=True)
        with self.assertRaisesRegex(RuntimeError, "ambiguous worker"):
            self.reconcile()
        self.assertFalse(self.signals)

    def test_signal_failure_or_incomplete_group_inventory_never_proves_stop(self):
        self.process(604, marked=True)
        (self.remote / "worker.pid").write_text("604")
        with patch("os.killpg", side_effect=PermissionError("synthetic")), self.assertRaises(PermissionError):
            self.reconcile()
        self.assertFalse((self.remote / "out/controller-stopped.json").exists())
        (self.proc / "531/stat").write_text("invalid")
        with self.assertRaisesRegex(RuntimeError, "stat inventory incomplete"):
            self.reconcile()

    def test_escaped_session_and_foreign_pid_fail_without_signals(self):
        self.process(604, marked=True)
        self.process(605, group=700, session=604)
        (self.remote / "worker.pid").write_text("604")
        with self.assertRaisesRegex(RuntimeError, "escaped"):
            self.reconcile()
        (self.remote / "worker.pid").write_text("531")
        with self.assertRaisesRegex(RuntimeError, "identity inaccessible"):
            self.reconcile()
        self.assertFalse(self.signals)

    def test_exact_marker_values_no_prefix_match(self):
        self.process(604, marked=True)
        for name in ("cmdline", "environ"):
            path = self.proc / "604" / name
            path.write_bytes(path.read_bytes().replace(self.binding["worker_id"].encode(), b"c" * 33))
        (self.remote / "worker.pid").write_text("604")
        with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
            self.reconcile()


class ControllerTests(unittest.TestCase):
    setUp = prior.ControllerTests.setUp
    launched = prior.ControllerTests.launched
    bind_worker = prior.ControllerTests.bind_worker

    def controller(self, kind="main", out=None):
        amendment = {"original_plan": {"path": "plan.json", "sha256": c.original.sha(self.plan)},
                     "budget": {**prior.BUDGET, "prior_total_usd": p.PRIOR_TOTAL, "exposure_max_usd": p.REMAINING},
                     "failed_startup": {"pod_id": p.FAILED_POD, "compute_upper_bound_usd": p.FAILED_COST}}
        path = self.root / "amendment.json"
        path.write_text(json.dumps(amendment))
        if not hasattr(self, "amendment_loader"):
            self.amendment_loader = Mock(return_value=amendment)
            patcher = patch.object(p, "load_plan", self.amendment_loader)
            patcher.start()
            self.addCleanup(patcher.stop)
        ctrl = c.Controller(self.plan, prior.FREEZE, out or self.root / "out", kind, self.api,
                            amendment_path=path, clock=lambda: self.current, sleep=Mock(),
                            monotonic=lambda: self.ticks, run=Mock(side_effect=AssertionError("Unexpected subprocess")))
        ctrl.disk_check = Mock()
        return ctrl

    def snapshots(self, *, fail=False, corrupt=False):
        binding = self.bind_worker()
        files = {"controller.log": b"synthetic bootstrap log\n"}
        actions = []
        def ssh(_pod, command, **kwargs):
            if c.WORKER_SIGNAL_SCRIPT in shlex.split(command):
                action = json.loads(kwargs["data"])["action"]
                actions.append(action)
                result = prior.ControllerTests.signal_result(action, binding)
                result.pop("no_matching_worker")
                result.update(owned_group_quiescent=True, proof_scope="recorded-worker-group-and-session")
                if action == "stop":
                    files["controller-stopped.json"] = json.dumps(result).encode()
                return json.dumps(result).encode()
            return json.dumps({name: c.original.hashlib.sha256(raw).hexdigest() for name, raw in files.items()}).encode()
        def run(argv, **_kwargs):
            self.assertEqual(argv[0], "rsync")
            for name, raw in files.items():
                path = Path(argv[-1]) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw + (b"corrupt" if corrupt else b""))
            return subprocess.CompletedProcess(argv, 1 if fail else 0, b"", b"")
        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=run)
        return actions

    test_preexisting_pod_cannot_be_claimed_mutated_or_deleted = prior.ControllerTests.test_preexisting_pod_cannot_be_claimed_mutated_or_deleted
    test_ambiguous_multiple_matches_never_pick_one = prior.ControllerTests.test_ambiguous_multiple_matches_never_pick_one
    test_unresolved_create_persists_no_second_post = prior.ControllerTests.test_unresolved_create_persists_no_second_post
    test_unknown_pod_never_accessed = prior.ControllerTests.test_unknown_pod_never_accessed
    test_corrupt_snapshot_blocks_delete = prior.ControllerTests.test_corrupt_snapshot_blocks_delete
    test_retrieval_failure_always_resumes = prior.ControllerTests.test_retrieval_failure_always_resumes
    test_retrieve_before_delete_and_verified_closure = prior.ControllerTests.test_retrieve_before_delete_and_verified_closure
    test_closing_fence_blocks_late_launch_and_child_before_work = prior.ControllerTests.test_closing_fence_blocks_late_launch_and_child_before_work

    def test_amended_creation_monitor_and_closure_accounting(self):
        self.launched()
        intent = self.ctrl.event("create-intent")["data"]
        self.assertEqual(intent["prior_total_usd"], p.PRIOR_TOTAL)
        self.assertEqual(intent["local_cap_usd"], p.REMAINING)
        self.assertIn(p.FAILED_POD, intent["blocked"])
        self.assertEqual(self.ctrl.plan["budget"], prior.BUDGET)
        self.assertEqual(self.public.call_count, 2)
        self.current += timedelta(seconds=100)
        spent = self.ctrl.cost_check(self.api.pod)
        accounting = next(e["data"] for e in reversed(self.ctrl.ledger.read()) if e["id"].startswith("accounting:"))
        self.assertEqual(Decimal(accounting["cumulative_projected_usd"]), c.PRIOR_TOTAL + Decimal(accounting["projected_usd"]))
        self.snapshots()
        self.ctrl.terminate()
        closure = self.ctrl.event("closed")["data"]
        self.assertEqual(Decimal(closure["cumulative_upper_bound_usd"]), c.PRIOR_TOTAL + spent)
        self.assertEqual(Decimal(closure["shared_subcap_upper_bound_usd"]), c.FAILED_COST + spent)
        self.assertEqual(closure["failed_startup_usd"], p.FAILED_COST)
        self.assertTrue(closure["within_limits"])
        self.assertTrue(self.api.deleted)

    def test_amendment_drift_blocks_all_creation_calls(self):
        self.amendment_loader.side_effect = ValueError("amendment drift")
        with self.assertRaisesRegex(ValueError, "amendment drift"):
            self.ctrl.launch()
        self.assertFalse(self.api.calls)

    def cleanup_scenario(self, live):
        harness = ProcessTests()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        def ssh(_pod, command, **kwargs):
            if c.WORKER_SIGNAL_SCRIPT in shlex.split(command):
                request = json.loads(kwargs["data"])
                self.assertEqual(request["binding"], harness.binding)
                return json.dumps(harness.reconcile(request["action"])).encode()
            if c.original.frozen.MANIFEST_SCRIPT in shlex.split(command):
                return json.dumps({path.relative_to(harness.remote / "out").as_posix(): c.original.sha(path)
                                   for path in (harness.remote / "out").rglob("*") if path.is_file()}).encode()
            if "nohup setsid timeout" in command:
                intent = self.ctrl.event("worker-intent")["data"]
                harness.binding = {key: intent[key] for key in harness.binding}
                if live:
                    harness.process(604, marked=True)
                (harness.remote / "out/controller.log").write_text("synthetic partial bootstrap\n")
                raise RuntimeError("uncertain synthetic launch")
            return b""
        def copy(argv, **kwargs):
            self.assertEqual(argv[0], "rsync")
            for path in (harness.remote / "out").rglob("*"):
                if path.is_file():
                    target = Path(argv[-1]) / path.relative_to(harness.remote / "out")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        self.ctrl._ssh, self.ctrl.run = Mock(side_effect=ssh), Mock(side_effect=copy)
        # A regression must fail promptly instead of exercising the retry loop.
        self.ctrl.close_until_verified = self.ctrl.terminate
        with self.assertRaisesRegex(RuntimeError, "uncertain synthetic launch"):
            self.ctrl.launch()
        self.assertTrue(self.api.deleted)
        self.assertNotIn(harness.proc / "531/environ", harness.reads)
        self.assertTrue((harness.proc / "531").exists())
        retrieval = json.loads((self.ctrl.base / "final-retrieval.json").read_text())["data"]
        self.assertIn("controller.log", retrieval["artifacts"])
        stopped = json.loads((Path(retrieval["directory"]) / "controller-stopped.json").read_text())
        self.assertTrue(stopped["owned_group_quiescent"])
        self.assertNotIn("no_matching_worker", stopped)
        self.assertEqual(stopped["recovered_pid"], live)
        self.assertEqual(stopped["proof_scope"], "recorded-worker-group-and-session" if live
                         else "fenced-dispatch-command-inventory")
        if live:
            self.assertEqual(harness.signals, [(604, signal.SIGCONT), (604, signal.SIGTERM)])
        else:
            self.assertFalse(harness.signals)

    def test_uncertain_launch_without_worker_retrieves_and_deletes_despite_protected_foreign(self):
        self.cleanup_scenario(False)

    def test_uncertain_launch_with_worker_recovers_retrieves_and_deletes_only_owned(self):
        self.cleanup_scenario(True)

    def test_budget_guard_uses_remaining_not_original_25_and_checks_clocks(self):
        self.launched()
        self.ctrl.budget["exposure_max_usd"] = Decimal(".001")
        with self.assertRaisesRegex(ValueError, "A1 budget"):
            self.ctrl.cost_check(self.api.pod)
        self.ctrl.budget["exposure_max_usd"] = c.MAX_NEW
        self.current -= timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "clock moved backward"):
            self.ctrl.cost_check(self.api.pod)

    def test_signal_wrapper_is_bound_and_does_not_expose_remote_stderr(self):
        self.launched()
        self.bind_worker()
        self.ctrl.run = Mock(return_value=subprocess.CompletedProcess([], 1, b"", b"SENSITIVE_FIXTURE"))
        with self.assertRaisesRegex(RuntimeError, "stderr withheld") as error:
            self.ctrl.signal_worker(self.api.pod, "stop")
        self.assertNotIn("SENSITIVE_FIXTURE", str(error.exception))
        self.assertIn(c.WORKER_SIGNAL_SCRIPT, shlex.split(self.ctrl.run.call_args.args[0][-1]))
        self.assertNotIn("SENSITIVE_FIXTURE", self.ctrl.ledger.path.read_text())

    def test_frozen_dispatch_and_runtime_are_inherited_without_global_mutation(self):
        self.assertIs(c.Controller.start_worker, c.original.Controller.start_worker)
        self.assertIs(c.Controller.retrieve, c.original.Controller.retrieve)
        self.assertIs(c.Controller.terminate, c.original.Controller.terminate)
        self.assertEqual(c.original.PRIOR_TOTAL, Decimal(prior.BUDGET["prior_total_usd"]))
        self.assertEqual(c.original.MAX_NEW, 25)
        self.assertIn("9>&- & pid=$!", c.original.dispatch_command("true", 120, {
            "worker_id": "c" * 32, "freeze_commit": prior.FREEZE, "pod_id": "synthetic-owned"}))


class ProtocolTests(unittest.TestCase):
    def test_real_original_plan_and_failure_projection_are_bound_without_writes(self):
        manifest = p.build_plan()
        self.assertEqual(manifest["original_plan"]["sha256"], p.ORIGINAL_SHA)
        self.assertEqual(manifest["original_plan"]["freeze_commit"], p.ORIGINAL_FREEZE)
        self.assertEqual(len(json.loads((p.ROOT / p.ORIGINAL_PLAN).read_text())["source_hashes"]), 53)
        self.assertEqual(manifest["budget"]["exposure_max_usd"], p.REMAINING)
        self.assertIn(p.DOCUMENT, manifest["source_hashes"])
        self.assertEqual(len(manifest["input_hashes"]), 7)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "PLAN.json"
            path.write_text(p.canonical(manifest) + "\n")
            self.assertEqual(p.load_plan(path), manifest)
            manifest["budget"]["exposure_max_usd"] = "25"
            path.write_text(p.canonical(manifest) + "\n")
            with self.assertRaisesRegex(ValueError, "drift"):
                p.load_plan(path)

    def test_cli_preflight_is_offline_and_read_only(self):
        amendment = {"original_plan": {"sha256": p.ORIGINAL_SHA}}
        with patch.object(p, "load_plan", return_value=amendment), patch.object(c.original, "preflight", return_value={"network_calls": 0}), \
                patch.object(c.original, "sha", return_value=p.ORIGINAL_SHA), patch.object(c.original, "RunPodV2") as api, \
                patch("sys.stdout", new_callable=io.StringIO) as output:
            c.main(["--plan", p.ORIGINAL_PLAN, "--amendment", p.MANIFEST_PATH, "--freeze", prior.FREEZE, "--out", "unused"])
        api.assert_not_called()
        value = json.loads(output.getvalue())
        self.assertEqual(value["prior_total_usd"], p.PRIOR_TOTAL)
        self.assertEqual(value["new_cap_usd"], p.REMAINING)
        self.assertEqual(value["network_calls"], 0)


@unittest.skipUnless(sys.platform == "linux", "Real protected /proc proof requires Linux")
class LinuxProcessTests(unittest.TestCase):
    def test_real_protected_foreign_environment_and_owned_verification(self):
        source = r'''
import ctypes,fcntl,json,os,pathlib,signal,subprocess,sys,tempfile,time,uuid
from experiments.sae_assay_exposure_lifecycle_a1 import controller as c
# Drop privileges only in this isolated test child, never in the test runner.
if os.geteuid()==0:
 os.setgroups([]); os.setgid(65534); os.setuid(65534)
def binding():
 return {'worker_id':uuid.uuid4().hex,'pod_id':'synthetic-ci-owned','freeze_commit':'a'*40,'plan_sha256':'b'*64}
def action(root,b,name):
 result=subprocess.run([sys.executable,'-c',c.WORKER_SIGNAL_SCRIPT],input=json.dumps(
  {'remote':str(root),'binding':b,'action':name}),text=True,capture_output=True,timeout=20)
 assert result.returncode==0,result.stderr
 return json.loads(result.stdout)
def command(root,b,script):
 return c.original.dispatch_command(script,120,b).replace(c.original.REMOTE,str(root))
with tempfile.TemporaryDirectory(prefix='exposure-a1-linux-') as folder:
 base=pathlib.Path(folder); protected=subprocess.Popen([sys.executable,'-c',
  'import ctypes,time; assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0; print("ready",flush=True); time.sleep(120)'],
  stdout=subprocess.PIPE,text=True,start_new_session=True)
 workers=[]
 try:
  assert protected.stdout.readline().strip()=='ready'
  try: pathlib.Path('/proc',str(protected.pid),'environ').read_bytes()
  except PermissionError: pass
  else: raise AssertionError('fixture environment was not protected')
  wrong=base/'wrong'; (wrong/'out').mkdir(parents=True); (wrong/'worker.pid').write_text(str(protected.pid))
  try: c.reconcile_worker(wrong,binding(),'stop')
  except RuntimeError as error: assert 'identity inaccessible' in str(error)
  else: raise AssertionError('unverified protected leader accepted')
  assert protected.poll() is None
  absent=base/'absent'; (absent/'out').mkdir(parents=True); b=binding()
  assert action(absent,b,'stop')['pid'] is None
  late=subprocess.run(['bash','-c',command(absent,b,'touch '+str(absent/'unexpected'))],capture_output=True,timeout=5)
  assert late.returncode!=0 and not (absent/'unexpected').exists()
  for missing in (False,True):
   root=base/str(missing); (root/'out').mkdir(parents=True); b=binding()
   launched=subprocess.run(['bash','-c',command(root,b,'touch '+str(root/'ready')+'\nsleep 120')],capture_output=True,timeout=5)
   assert launched.returncode==0,launched.stderr
   pid=int((root/'worker.pid').read_text()); workers.append((pid,b['worker_id']))
   deadline=time.monotonic()+5
   while not (root/'ready').exists():
    assert time.monotonic()<deadline
    time.sleep(.02)
   with (root/'worker-dispatch.lock').open('a') as lock:
    fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
   if missing: (root/'worker.pid').unlink()
   else:
    assert action(root,b,'pause')['verified']; assert action(root,b,'resume')['verified']
   result=action(root,b,'stop')
   assert result['pid']==pid and result['recovered_pid']==missing
   assert action(root,b,'stop')['verified']
   assert protected.poll() is None
 finally:
  for pid,worker_id in workers:
   try:
    marker=('CODEX_EXPOSURE_WORKER_ID='+worker_id).encode()
    if marker in pathlib.Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0') and os.getpgid(pid)==pid:
     os.killpg(pid,signal.SIGKILL)
   except (ProcessLookupError,FileNotFoundError): pass
  protected.terminate(); protected.wait(timeout=5)
print('protected-foreign-and-owned-proof-passed')
'''
        result = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "protected-foreign-and-owned-proof-passed")


if __name__ == "__main__":
    unittest.main()
