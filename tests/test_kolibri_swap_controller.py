from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tarfile

import pytest

from experiments.kolibri_swap import bootstrap as b, controller as c


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 4, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += timedelta(seconds=seconds)


class FakeAPI:
    writable = True

    def __init__(self, clock):
        self.clock = clock
        self.pod = None
        self.deleted = False
        self.calls = []
        self.delete_error = False
        self.delete_effect = True

    def inventory(self):
        return [{"id": "other-owned-by-someone-else", "name": "other-study"}] + (
            [deepcopy(self.pod)] if self.pod and not self.deleted else [])

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        if method == "POST":
            assert path == "/pods"
            self.pod = {**deepcopy(body), "id": "kolibri-owned-1", "status": "RUNNING",
                        "createdAt": self.clock().isoformat(), "cost": "4.59", "ssh": {}}
            return 201, deepcopy(self.pod)
        assert path == "/pods/kolibri-owned-1"
        if method == "DELETE":
            self.deleted = self.delete_effect
            if self.delete_error:
                raise RuntimeError("Synthetic unknown DELETE response")
            return 204, None
        assert method == "GET"
        if self.deleted:
            raise c.base.ApiError(404)
        return 200, deepcopy(self.pod)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    plan = root / c.protocol.PLAN
    plan.parent.mkdir(parents=True)
    plan.write_text("{}\n")
    out = root / "operational"
    monkeypatch.setattr(c, "ROOT", root)
    monkeypatch.setattr(c, "canonical_root", lambda: out)
    monkeypatch.setattr(c.protocol, "verify", lambda *a: {"synthetic_test": True})
    key = root / "synthetic-key"
    key.write_text("synthetic offline fixture, not a private key\n")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA synthetic\n")
    monkeypatch.setattr(c.base, "KEY", key)
    clock = Clock()
    api = FakeAPI(clock)
    controller = c.Controller(plan, "a" * 40, "main", api, out=out, clock=clock, sleep=clock.sleep)
    return controller, api, clock


def owned(setup):
    ctl, api, clock = setup
    name = c.PREFIX + ctl.kind + "-" + "a" * 12
    payload = c.payload(ctl.kind, name, "ssh-ed25519 AAAA synthetic")
    ctl.ledger.bind("create-intent", {
        "payload": payload, "quote": {"hourly_rate_usd": "4.59", "storage_hourly_usd": "0.10"},
        "created_utc": clock().isoformat(), "deadline_utc": (clock() + timedelta(seconds=17400)).isoformat(),
        "cleanup_deadline_utc": (clock() + timedelta(seconds=18000)).isoformat(),
        "blocked": ["other-owned-by-someone-else"], "plan_sha256": ctl.plan_hash,
        "freeze_commit": ctl.freeze, "cap_usd": "23.75"})
    _, pod = api.request("POST", "/pods", payload)
    ctl._register(pod)
    return ctl, api, clock


def saved_retrieval(ctl, files=None):
    files = {"exit.json": b'{"exit_code":0}\n'} if files is None else files
    directory = ctl.base / "retrievals" / "synthetic"
    directory.mkdir(parents=True)
    hashes = {}
    for name, content in files.items():
        (directory / name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    receipt = ctl.record("retrieval", {"pod_id": ctl.owned()["id"], "directory": str(directory),
                                      "artifacts": hashes, "retrieval_verified": True})
    ctl._final_receipt(receipt)
    return receipt


def tar_bytes(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, content, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(content) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                item.linkname = "../../private"
            archive.addfile(item, io.BytesIO(content) if item.size else None)
    return stream.getvalue()


def test_register_and_reconcile_are_idempotent_and_do_not_adopt_others(setup):
    ctl, api, _ = owned(setup)
    first = ctl.event("created")
    api.pod.update(status="STARTING", ssh={"direct": {"changed": "metadata"}})
    ctl._register(api.pod)
    ctl.reconcile()
    ctl.reconcile()
    assert ctl.event("created") == first
    assert sum(e["id"] == "pod:created:kolibri-owned-1" for e in ctl.ledger.read()) == 1
    assert sum(method == "POST" for method, _ in api.calls) == 1
    with pytest.raises(ValueError):
        ctl._register({**api.pod, "id": "other-owned-by-someone-else"})
    with pytest.raises(ValueError):
        ctl._register({**api.pod, "id": "another-new-id"})


def test_reconcile_repairs_created_event_before_registry_append(setup):
    ctl, api, _ = setup
    # Interrupt only registration, leaving the creation receipt durable.
    original = c.PodRegistry.register_created
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(c.PodRegistry, "register_created", lambda *a: (_ for _ in ()).throw(OSError("synthetic")))
        with pytest.raises(OSError):
            owned(setup)
    assert ctl.event("created") is not None
    assert ctl.event("pod:created:kolibri-owned-1") is None
    assert c.PodRegistry.register_created is original
    ctl.reconcile()
    assert ctl.event("pod:created:kolibri-owned-1") is not None
    assert sum(method == "POST" for method, _ in api.calls) == 1


def test_terminate_once_after_verified_retrieval_then_idempotent(setup):
    ctl, api, _ = owned(setup)
    receipt = saved_retrieval(ctl)
    ctl._final_receipt(receipt)
    assert ctl._verify_final() == receipt
    closed = ctl.terminate()
    assert closed["data"]["get_status"] == 404
    assert ctl.terminate() == closed
    assert api.calls.count(("DELETE", "/pods/kolibri-owned-1")) == 1
    assert all("other-owned" not in path for _, path in api.calls)


def test_retrieval_failure_is_recorded_but_does_not_strand_owned_compute(setup, monkeypatch):
    ctl, api, _ = owned(setup)
    monkeypatch.setattr(ctl, "retrieve", lambda **kw: (_ for _ in ()).throw(RuntimeError("Synthetic SSH failure")))
    closed = ctl.terminate()
    assert closed["data"]["get_status"] == 404 and api.deleted
    receipt = json.loads((ctl.base / "final-retrieval.json").read_text())
    assert receipt["data"]["recovery_failed"] is True
    assert receipt["data"]["retrieval_verified"] is False
    assert ctl.event("emergency-delete-permit")["data"]["diagnostics_verified"] is False


def test_corrupt_receipt_preserved_and_emergency_cleanup_still_deletes(setup):
    ctl, api, _ = owned(setup)
    saved_retrieval(ctl)
    path = ctl.base / "final-retrieval.json"
    path.write_text("damaged synthetic receipt\n")
    ctl.terminate()
    assert api.deleted
    assert path.read_text() == "damaged synthetic receipt\n"
    assert ctl.event("emergency-delete-permit") is not None


def test_uncertain_delete_is_get_reconciled_without_second_delete(setup):
    ctl, api, _ = owned(setup)
    saved_retrieval(ctl)
    api.delete_error = True
    assert ctl.terminate()["data"]["get_status"] == 404
    assert any(e["id"].startswith("delete-response-uncertain:") for e in ctl.ledger.read())
    assert api.calls.count(("DELETE", "/pods/kolibri-owned-1")) == 1


def test_unverified_delete_retains_reservation_and_only_reconciles_reads(setup):
    ctl, api, _ = owned(setup)
    saved_retrieval(ctl)
    api.delete_effect = False
    api.delete_error = True
    with pytest.raises(RuntimeError, match="unverified"):
        ctl.terminate()
    assert ctl.event("closed") is None
    assert any(e["id"].startswith("cleanup-unresolved:") for e in ctl.ledger.read())
    api.deleted = True
    assert ctl.terminate()["data"]["get_status"] == 404
    assert api.calls.count(("DELETE", "/pods/kolibri-owned-1")) == 1


@pytest.mark.parametrize("error", [RuntimeError("Synthetic status error"), KeyboardInterrupt()])
def test_monitor_cleans_up_status_errors_and_interrupts(setup, monkeypatch, error):
    ctl, api, _ = owned(setup)
    saved_retrieval(ctl)
    monkeypatch.setattr(ctl, "status", lambda: (_ for _ in ()).throw(error))
    with pytest.raises(type(error)):
        ctl.monitor()
    assert api.deleted and ctl.event("closed") is not None


def test_server_startup_has_75_minute_limit_and_ten_minute_cleanup_reserve(setup, monkeypatch):
    ctl, api, clock = owned(setup)
    saved_retrieval(ctl)
    clock.sleep(75 * 60)
    monkeypatch.setattr(ctl, "status", lambda: {"pod": deepcopy(api.pod), "worker": {"ready": False}})
    with pytest.raises(TimeoutError, match="75 minutes"):
        ctl.monitor()
    assert api.deleted
    assert c.CLEANUP_RESERVE_SECONDS == 600
    assert ctl.event("server-ready") is None


def test_ready_server_not_subject_to_startup_limit_and_normal_exit_cleans(setup, monkeypatch):
    ctl, api, clock = owned(setup)
    saved_retrieval(ctl)
    clock.sleep(74 * 60)
    states = iter([{"ready": True}, {"ready": True, "exit.json": {"exit_code": 0}}])
    monkeypatch.setattr(ctl, "status", lambda: {"pod": deepcopy(api.pod), "worker": next(states)})
    assert ctl.monitor()["data"]["get_status"] == 404
    assert ctl.event("server-ready") is not None


def test_launch_startup_exception_cleans_created_pod(setup, monkeypatch):
    ctl, api, _ = setup
    monkeypatch.setattr(ctl, "cheap_pass", lambda: {})
    monkeypatch.setattr(c, "quote", lambda *a: {"hourly_rate_usd": "4.59", "storage_hourly_usd": "0.10"})
    monkeypatch.setattr(c.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(ctl.plan_path.read_bytes()))
    monkeypatch.setattr(ctl, "start_worker", lambda: (_ for _ in ()).throw(TimeoutError("synthetic startup")))
    monkeypatch.setattr(ctl, "retrieve", lambda **kw: (_ for _ in ()).throw(RuntimeError("synthetic SSH unavailable")))
    with pytest.raises(TimeoutError):
        ctl.launch()
    assert api.deleted
    intent = ctl.event("create-intent")["data"]
    assert (c._utc(intent["cleanup_deadline_utc"]) - c._utc(intent["deadline_utc"])).total_seconds() == 600
    assert ctl.event("closed")["data"]["get_status"] == 404


@pytest.mark.parametrize("name,kind", [
    ("../worker.log", tarfile.REGTYPE), ("/worker.log", tarfile.REGTYPE), (".env", tarfile.REGTYPE),
    ("repo/worker.log", tarfile.REGTYPE), ("credentials.json", tarfile.REGTYPE),
    ("worker.log", tarfile.SYMTYPE), ("worker.log", tarfile.LNKTYPE),
    ("worker.log", tarfile.FIFOTYPE), ("worker.log", tarfile.DIRTYPE),
])
def test_tar_rejects_paths_links_special_files_and_nonoutput_inventory(tmp_path, name, kind):
    with pytest.raises((ValueError, tarfile.TarError)):
        c.verified_archive(tar_bytes([(name, b"synthetic", kind)]), tmp_path / "received")
    assert not (tmp_path / "received").exists()


def test_tar_hashes_exact_bytes_and_rejects_duplicates_and_linked_destination(tmp_path):
    raw = tar_bytes([("worker.log", b"a\r\nb\n", tarfile.REGTYPE), ("exit.json", b"{}", tarfile.REGTYPE)])
    hashes = c.verified_archive(raw, tmp_path / "received")
    assert hashes["worker.log"] == hashlib.sha256(b"a\r\nb\n").hexdigest()
    assert (tmp_path / "received/worker.log").read_bytes() == b"a\r\nb\n"
    with pytest.raises(ValueError):
        c.verified_archive(tar_bytes([("worker.log", b"a", tarfile.REGTYPE)] * 2), tmp_path / "duplicate")
    (tmp_path / "link").symlink_to(tmp_path / "received", target_is_directory=True)
    with pytest.raises(ValueError):
        c.verified_archive(raw, tmp_path / "link/child")


def test_remote_archive_exports_only_out_and_rejects_secret_or_link(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    (root / "worker.log").write_bytes(b"synthetic log\n")
    def command(pack):
        code = shlex.split(c.artifact_command(pack=pack))[2].replace("/workspace/kolibri/out", str(root))
        return subprocess.run([sys.executable, "-c", code], capture_output=True, check=False)
    manifest = json.loads(command(False).stdout)
    packed = command(True)
    assert packed.returncode == 0
    assert c.verified_archive(packed.stdout, tmp_path / "copy") == manifest
    (root / ".env").write_text("SYNTHETIC_SECRET=never-export\n")
    for pack in (False, True):
        result = command(pack)
        assert result.returncode != 0 and b"never-export" not in result.stdout + result.stderr
    (root / ".env").unlink()
    (root / "runtime.json").symlink_to(tmp_path / "outside")
    assert command(True).returncode != 0


def test_retrieval_compares_remote_before_after_and_local_hashes(setup, monkeypatch):
    ctl, api, _ = owned(setup)
    raw = tar_bytes([("exit.json", b'{"exit_code":0}', tarfile.REGTYPE)])
    hashes = {"exit.json": hashlib.sha256(b'{"exit_code":0}').hexdigest()}
    def ssh(pod, command, **kwargs):
        assert pod["id"] == api.pod["id"]
        if command == c.artifact_command():
            return json.dumps(hashes).encode()
        if command == c.artifact_command(pack=True):
            return raw
        if command == "mkdir -p /workspace/kolibri/out":
            return b""
        raise AssertionError(command)
    monkeypatch.setattr(ctl, "_ssh", ssh)
    receipt = ctl.retrieve(final=True)
    assert receipt["data"]["retrieval_verified"] is True
    assert ctl.retrieve(final=True) == receipt
    assert ctl._verify_final() == receipt


def write_stat(root, pid, *, state="S", group=100, session=100, start=10):
    path = root / str(pid) / "stat"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [state, "1", str(group), str(session)] + ["0"] * 15 + [str(start)]
    path.write_text(str(pid) + " (synthetic (nested) name) " + " ".join(fields))
    return path


def test_stop_group_kills_orphan_child_after_leader_exits(tmp_path):
    child = write_stat(tmp_path, 101, start=12)
    untouched = write_stat(tmp_path, 200, group=200, session=200, start=12)
    signals = []
    def killpg(pid, sig):
        signals.append((pid, sig))
        if sig == signal.SIGKILL:
            child.unlink()
    record = {"pid": 100, "pgid": 100, "session": 100, "start": "10"}
    b.stop_group(record, proc_root=tmp_path, killpg=killpg, sleep=lambda _: None)
    assert signals == [(100, signal.SIGCONT), (100, signal.SIGTERM), (100, signal.SIGKILL)]
    assert untouched.exists()
    b.stop_group(record, proc_root=tmp_path, killpg=killpg, sleep=lambda _: None)
    assert len(signals) == 3


def test_stop_group_refuses_reused_pid_and_never_reports_live_child_stopped(tmp_path):
    leader = write_stat(tmp_path, 100, start=11)
    record = {"pid": 100, "pgid": 100, "session": 100, "start": "10"}
    signals = []
    with pytest.raises(RuntimeError, match="identity"):
        b.stop_group(record, proc_root=tmp_path, killpg=lambda *a: signals.append(a), sleep=lambda _: None)
    assert signals == []
    leader.unlink()
    write_stat(tmp_path, 101, start=12)
    with pytest.raises(RuntimeError, match="did not stop"):
        b.stop_group(record, proc_root=tmp_path, killpg=lambda *a: signals.append(a), sleep=lambda _: None)


def test_bootstrap_is_syntax_valid_pinned_secret_free_and_exact_smoke_path():
    for kind in ("cheap", "main"):
        script = b.worker_script(kind, "a" * 40, c.protocol.PLAN, 3600)
        check = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
        assert check.returncode == 0, check.stderr
        assert "--require-hashes" in script
        assert "HF_HUB_DISABLE_IMPLICIT_TOKEN=1" in script
        assert "--branch codex/kolibri-swap-panel" in script
        if kind == "cheap":
            assert "--mode gpu" in script
            assert "--out /workspace/kolibri/out/gpu-smoke.json" in script
            assert "vllm serve" not in script
        else:
            assert "--host 127.0.0.1" in script and "--disable-log-requests" in script
    start = shlex.split(b.start_command(3600, "b" * 64))[2]
    stop = shlex.split(b.stop_command("b" * 64))[2]
    compile(start, "start", "exec")
    compile(stop, "stop", "exec")
    assert "start_new_session=True,env=env" in start
    assert "os.environ" not in start
    assert "OPENROUTER_API_KEY" not in start
    assert "RUNPOD_API_KEY" not in start
    assert "stop_group(d)" in stop
    assert "if not p.exists(): break" not in stop


@pytest.mark.parametrize("status,mode,scientific,accepted", [
    ("passed", "gpu", False, True), ("failed", "gpu", False, False),
    ("passed", "parser", False, False), ("passed", "gpu", True, False),
])
def test_cheap_pass_uses_actual_smoke_schema(setup, status, mode, scientific, accepted):
    main, api, clock = setup
    cheap = c.Controller(main.plan_path, main.freeze, "cheap", api,
                         out=main.out, clock=clock, sleep=clock.sleep)
    owned((cheap, api, clock))
    saved_retrieval(cheap, {
        "exit.json": b'{"exit_code":0}',
        "gpu-smoke.json": json.dumps({"status": status, "mode": mode,
                                      "scientific_generation": scientific}).encode()})
    cheap.ledger.bind("closed", {"pod_id": cheap.owned()["id"], "get_status": 404,
                                "compute_upper_bound_usd": "0.50"})
    if accepted:
        assert main.cheap_pass()["get_status"] == 404
    else:
        with pytest.raises(ValueError, match="did not pass"):
            main.cheap_pass()


def test_cleanup_survives_interrupt_during_retrieval(setup, monkeypatch):
    ctl, api, _ = owned(setup)
    monkeypatch.setattr(ctl, "retrieve", lambda **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert ctl.terminate()["data"]["get_status"] == 404
    assert api.deleted
    assert ctl.event("emergency-delete-permit") is not None


def test_delete_permit_crash_recovery_is_idempotent(setup):
    ctl, api, _ = owned(setup)
    saved_retrieval(ctl)
    path = ctl.base / "final-retrieval.json"
    registry = c.PodRegistry(ctl.ledger, ctl.event("create-intent")["data"]["blocked"])
    permit = registry.authorize_delete(api.pod["id"], {str(path): c.base.sha(path)})
    assert ctl.event("delete-intent") is None
    ctl.terminate()
    assert ctl.event("delete-intent")["data"]["permit_sha256"] == permit["sha256"]
    assert api.calls.count(("DELETE", "/pods/kolibri-owned-1")) == 1


def test_retrieval_hash_drift_is_not_a_verified_snapshot(setup, monkeypatch):
    ctl, _, _ = owned(setup)
    raw = tar_bytes([("worker.log", b"before", tarfile.REGTYPE)])
    calls = 0
    def ssh(pod, command, **kwargs):
        nonlocal calls
        if command == c.artifact_command():
            calls += 1
            content = b"before" if calls == 1 else b"after"
            return json.dumps({"worker.log": hashlib.sha256(content).hexdigest()}).encode()
        if command == c.artifact_command(pack=True):
            return raw
        return b""
    monkeypatch.setattr(ctl, "_ssh", ssh)
    with pytest.raises(ValueError, match="differ"):
        ctl.retrieve(final=True)
    assert not (ctl.base / "final-retrieval.json").exists()


def test_tar_size_limit_applies_before_artifact_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "MAX_ARCHIVE_BYTES", 32)
    raw = tar_bytes([("worker.log", b"x" * 100, tarfile.REGTYPE)])
    with pytest.raises(ValueError):
        c.verified_archive(raw, tmp_path / "received")
    assert not (tmp_path / "received").exists()
