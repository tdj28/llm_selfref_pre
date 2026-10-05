"""Budgeted owned-pod lifecycle; model judging and all API secrets stay local.

The main server stays behind SSH. Write STOP_SERVER only after generation has
finished (or an operational abort); the monitor retrieves hashes then deletes.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
import uuid

from experiments.sae_assay_diagnostic import controller as base
from experiments.sae_assay_diagnostic.budget import EventLedger, PodRegistry, _number, _utc
from . import bootstrap, protocol

ROOT = protocol.ROOT
PREFIX = "codex-kolibri-20261004-"
STORAGE = Decimal("0.10")
HARDWARE = {"cheap": ("NVIDIA GeForce RTX 4090", Decimal("0.74"), 24),
            "main": ("NVIDIA H200", Decimal("4.59"), 141)}
CAPS = {"cheap": Decimal("1.25"), "main": Decimal("23.75")}
SECONDS = {"cheap": 3000, "main": 18000}
CLEANUP_RESERVE_SECONDS = 600
SERVER_STARTUP_SECONDS = 75 * 60
MAX_ARCHIVE_BYTES = 128 * 1024**2
ARTIFACT_NAMES = frozenset({"exit.json", "gpu-smoke.json", "runtime.json", "pip-freeze.txt",
                            "upstream-tests.xml", "model-files.json", "worker.log"})


def artifact_command(*, pack=False):
    """Export only the declared diagnostic files under the worker's out folder."""
    code = """import hashlib,json,pathlib,stat,sys,tarfile
r=pathlib.Path('/workspace/kolibri/out')
allowed=ALLOWED
if any(p.is_symlink() for p in [r,*r.parents]) or not r.is_dir():
 raise ValueError('Unsafe output root')
files=[]; total=0
for p in sorted(r.iterdir()):
 s=p.lstat()
 if p.name not in allowed or not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
  raise ValueError('Unexpected or linked output artifact')
 total+=s.st_size
 if total>LIMIT: raise ValueError('Diagnostic archive exceeds bound')
 files.append(p)
if PACK:
 with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz',dereference=False) as t:
  for p in files: t.add(p,arcname=p.name,recursive=False)
else:
 result={}
 for p in files:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
  result[p.name]=h.hexdigest()
 print(json.dumps(result,sort_keys=True))
""".replace("ALLOWED", repr(sorted(ARTIFACT_NAMES))).replace("LIMIT", str(MAX_ARCHIVE_BYTES)).replace("PACK", repr(pack))
    return "python3 -c " + shlex.quote(code)


def check_manifest(value):
    if (not isinstance(value, dict) or not set(value) <= ARTIFACT_NAMES
            or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in value.values())):
        raise ValueError("Unsafe diagnostic manifest")
    return value


def canonical_root():
    common = Path(subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT, text=True).strip()).resolve()
    if common.name != ".git":
        raise ValueError("Shared repository root not found")
    return common.parent / "out/kolibri-swap-20261004"


def quote(api, kind):
    gpu, ceiling, minimum = HARDWARE[kind]
    _, item = api.request("GET", "/catalog/gpus/" + urllib.parse.quote(gpu, safe="")
                         + "?include=AVAILABILITY&product=POD&cloud=SECURE&count=1&minCudaVersion=13.0")
    rate = _number(item["price"]["secure"])
    if (item["id"] != gpu or item.get("secure") is not True or item["memory"] < minimum
            or item.get("availability") not in {"LOW", "MEDIUM", "HIGH"} or not 0 < rate <= ceiling):
        raise ValueError("No qualified hardware at the approved price")
    return {"hourly_rate_usd": str(rate), "storage_hourly_usd": str(STORAGE)}


def payload(kind, name, public_key):
    if not re.fullmatch(re.escape(PREFIX) + kind + r"-[0-9a-f]{12}", name):
        raise ValueError("Owned unique pod name required")
    if not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?", public_key):
        raise ValueError("Expected an existing public Ed25519 key")
    return {"name": name, "image": bootstrap.IMAGE, "cloud": "SECURE",
            "gpu": {"id": HARDWARE[kind][0], "count": 1, "minCudaVersion": "13.0"},
            "disk": 50, "mounts": {"persistent": {"size": 50 if kind == "cheap" else 200, "path": "/workspace"}},
            "ports": ["22/tcp"], "startSsh": True, "startJupyter": False,
            "env": {"PUBLIC_KEY": public_key}}


def verified_archive(raw, destination):
    """Accept the out-only inventory, never links, special files or hidden paths."""
    destination = Path(destination)
    if (not isinstance(raw, bytes) or len(raw) > MAX_ARCHIVE_BYTES
            or any(p.is_symlink() for p in [destination, *destination.parents])):
        raise ValueError("Unsafe diagnostic archive or destination")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members, size = [], 0
        names = set()
        for item in archive:
            size += item.size
            if len(members) >= len(ARTIFACT_NAMES) or item.size < 0 or size > MAX_ARCHIVE_BYTES:
                raise ValueError("Unexpectedly large diagnostic archive")
            name = PurePosixPath(item.name)
            if (not item.isfile() or item.issparse() or item.name not in ARTIFACT_NAMES
                    or name.is_absolute() or ".." in name.parts
                    or name.as_posix() != item.name or item.name in names
                    or any(part.startswith(".") for part in name.parts)):
                raise ValueError("Unsafe or duplicate diagnostic artifact")
            names.add(item.name)
            members.append(item)
        destination.mkdir(parents=True, exist_ok=False)
        hashes = {}
        for item in members:
            target = destination / item.name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = archive.extractfile(item).read()
            if len(content) != item.size:
                raise ValueError("Truncated diagnostic artifact")
            with target.open("xb") as stream:
                stream.write(content)
            hashes[item.name] = hashlib.sha256(content).hexdigest()
    return hashes


class Controller(base.Controller):
    def __init__(self, plan_path, freeze, kind, api, *, out=None, run=subprocess.run,
                 clock=base.now, sleep=time.sleep):
        if kind not in HARDWARE:
            raise ValueError("Unknown pod role")
        self.plan_path, self.freeze, self.kind = Path(plan_path).resolve(), freeze, kind
        self.plan = protocol.verify(self.plan_path, freeze)
        self.plan_hash = base.sha(self.plan_path)
        self.relative = self.plan_path.relative_to(ROOT).as_posix()
        self.out = Path(out) if out is not None else canonical_root()
        if self.out.absolute() != canonical_root():
            raise ValueError("Only the canonical spending ledger is allowed")
        self.base = self.out / "controller" / kind
        if any(p.is_symlink() for p in [self.out, self.base, *self.base.parents]):
            raise ValueError("Operational path contains a symlink")
        self.base.mkdir(parents=True, exist_ok=True)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": kind, "plan": self.relative,
                         "image": bootstrap.IMAGE, "cap_usd": str(CAPS[kind])})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()

    def elapsed(self):
        intent = self.event("create-intent")
        if not intent:
            return Decimal(0)
        prior = max((_number(e["data"]["elapsed_seconds"]) for e in self.ledger.read()
                     if "elapsed_seconds" in e["data"]), default=Decimal(0))
        wall = max(0, (self.clock() - _utc(intent["data"]["created_utc"])).total_seconds())
        monotonic = self._elapsed0 + _number(time.monotonic() - self._mono0)
        return max(prior, _number(wall), monotonic)

    def _new_pod(self, pod, intent):
        return (intent.get("freeze_commit") == self.freeze
                and intent.get("plan_sha256") == self.plan_hash
                and base.Controller._new_pod(self, pod, intent))

    def _register(self, pod):
        intent = self.event("create-intent")["data"]
        if not self._new_pod(pod, intent):
            raise ValueError("Pod does not match this owned creation intent")
        receipt = self.event("created")
        if receipt is None:
            receipt = self.ledger.bind("created", base.clean_pod(pod))
        elif any(pod.get(k) != receipt["data"].get(k) for k in ("id", "name", "createdAt")):
            raise ValueError("Cannot replace an owned creation receipt")
        registry = PodRegistry(self.ledger, intent["blocked"])
        registered = self.event("pod:created:" + pod["id"])
        required = [str(self.base / "final-retrieval.json")]
        if registered is None:
            registry.register_created(pod["id"], receipt["sha256"], required)
        elif (registered["data"]["creation_receipt_sha256"] != receipt["sha256"]
              or registered["data"]["required_artifacts"] != required):
            raise ValueError("Owned registration binding differs")
        return receipt

    def reconcile(self):
        """Repair a partial registration without a second POST or worker launch."""
        if not self.event("create-intent"):
            raise ValueError("No creation intent to reconcile")
        self._register(self.owned() if self.event("created") else self.reconcile_create())
        return self.owned()

    def _cleanup_after_error(self, stage, error):
        try:
            self.record(stage, {"error_type": type(error).__name__})
        finally:
            if not self.event("created"):
                self.reconcile()
            self.terminate()

    def cheap_pass(self):
        root = self.out / "controller/cheap"
        ledger = EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, [])
        events = {e["id"]: e for e in ledger.read()}
        closed = events.get("closed", {}).get("data", {})
        receipt = json.loads((root / "final-retrieval.json").read_text())
        created_id = events.get("created", {}).get("data", {}).get("id")
        if (events.get(receipt["id"]) != receipt or closed.get("get_status") != 404
                or not created_id or closed.get("pod_id") != created_id
                or receipt["data"].get("pod_id") != created_id
                or receipt["data"].get("retrieval_verified") is not True):
            raise ValueError("Cheap pod retrieval/deletion is not verified")
        directory = Path(receipt["data"]["directory"])
        if (not directory.is_absolute() or directory.parent != root / "retrievals"
                or any(p.is_symlink() for p in [directory, *directory.parents])):
            raise ValueError("Foreign or linked cheap retrieval directory")
        check_manifest(receipt["data"]["artifacts"])
        if any(base.sha(directory / name) != digest for name, digest in receipt["data"]["artifacts"].items()):
            raise ValueError("Cheap diagnostic hash mismatch")
        smoke = json.loads((directory / "gpu-smoke.json").read_text())
        if (json.loads((directory / "exit.json").read_text())["exit_code"] != 0
                or smoke.get("status") != "passed" or smoke.get("mode") != "gpu"
                or smoke.get("scientific_generation") is not False
                or _number(closed["compute_upper_bound_usd"]) > CAPS["cheap"]):
            raise ValueError("Cheap GPU qualification did not pass")
        return closed

    def launch(self):
        if not self.api.writable or self.event("create-intent"):
            raise ValueError("Launch not authorized or already attempted")
        if self.kind == "main":
            self.cheap_pass()
        if shutil.disk_usage(self.base).free < 4 * 1024**3:
            raise ValueError("Insufficient local retrieval space")
        url = "https://raw.githubusercontent.com/tdj28/llm_selfref_pre/" + self.freeze + "/" + self.relative
        with urllib.request.urlopen(url, timeout=30) as response:
            if hashlib.sha256(response.read()).hexdigest() != self.plan_hash:
                raise ValueError("Public prospective plan differs")
        inventory = self.api.inventory()
        blocked = sorted(p["id"] for p in inventory)
        quoted = quote(self.api, self.kind)
        key = Path(str(base.KEY.expanduser()) + ".pub").read_text().strip()
        if not base.KEY.expanduser().is_file():
            raise ValueError("Existing SSH private key is missing")
        request = payload(self.kind, PREFIX + self.kind + "-" + uuid.uuid4().hex[:12], key)
        rate = _number(quoted["hourly_rate_usd"]) + STORAGE
        seconds = min(SECONDS[self.kind], int(CAPS[self.kind] / rate * 3600))
        now = self.clock()
        intent = {"payload": request, "quote": quoted, "created_utc": now.isoformat(),
                  "deadline_utc": (now + timedelta(seconds=seconds - CLEANUP_RESERVE_SECONDS)).isoformat(),
                  "cleanup_deadline_utc": (now + timedelta(seconds=seconds)).isoformat(),
                  "blocked": blocked, "plan_sha256": self.plan_hash,
                  "freeze_commit": self.freeze, "cap_usd": str(CAPS[self.kind])}
        self.ledger.bind("create-intent", intent)
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        try:
            try:
                status, pod = self.api.request("POST", "/pods", request)
                if status != 201 or not self._new_pod(pod, intent):
                    raise ValueError("Ambiguous creation")
            except (base.ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
                pod = self.reconcile_create()
            self._register(pod)
            print(json.dumps({"created_owned_pod": pod["id"], "kind": self.kind,
                              "deadline_utc": intent["deadline_utc"]}), flush=True)
            self.start_worker()
        except BaseException as exc:
            self._cleanup_after_error("startup-failure", exc)
            raise
        return self.owned()

    def cost_check(self, pod, horizon=60):
        intent = self.event("create-intent")["data"]
        expected = intent["payload"]
        rate = _number(pod.get("cost"))
        if (not 0 < rate <= _number(intent["quote"]["hourly_rate_usd"])
                or any(pod.get(k) != expected[k] for k in ("image", "cloud", "disk", "mounts", "ports"))
                or pod["gpu"]["id"] != HARDWARE[self.kind][0] or pod["gpu"]["count"] != 1):
            raise ValueError("Unexpected hardware or billing")
        elapsed = self.elapsed()
        spent = elapsed * (rate + STORAGE) / 3600
        self.record("accounting", {"elapsed_seconds": str(elapsed), "upper_bound_usd": str(spent)})
        if (spent + Decimal(horizon + CLEANUP_RESERVE_SECONDS) * (rate + STORAGE) / 3600 > CAPS[self.kind]
                or self.clock() + timedelta(seconds=horizon) >= _utc(intent["deadline_utc"])):
            raise ValueError("Retrieval reserve reached")
        return spent

    def start_worker(self):
        if self.event("worker-intent"):
            raise ValueError("Worker was already dispatched")
        start = time.monotonic()
        while time.monotonic() - start < 1200:
            pod = self.get_pod()
            self.cost_check(pod)
            try:
                if self._ssh(pod, "printf ready", timeout=25) == b"ready":
                    break
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass
            self.sleep(10)
        else:
            raise RuntimeError("SSH startup deadline reached")
        remaining = int((_utc(self.event("create-intent")["data"]["deadline_utc"]) - self.clock()).total_seconds())
        script = bootstrap.worker_script(self.kind, self.freeze, self.relative, remaining)
        self._ssh(pod, "umask 077; mkdir -p /workspace/kolibri/out; test ! -e /workspace/kolibri/worker.sh; cat > /workspace/kolibri/worker.sh",
                  data=script.encode(), timeout=60)
        self.ledger.bind("worker-intent", {"sha256": hashlib.sha256(script.encode()).hexdigest(),
                         "seconds": remaining, "created_utc": self.clock().isoformat()})
        self._ssh(pod, bootstrap.start_command(remaining, self.plan_hash), timeout=60)
        self.ledger.bind("worker-started", {"pod_id": pod["id"]})

    def status(self):
        pod = self.get_pod()
        code = """import json,pathlib,urllib.request
r=pathlib.Path('/workspace/kolibri/out'); result={}
for name in ['exit.json','gpu-smoke.json','runtime.json']:
 p=r/name
 if p.exists(): result[name]=json.loads(p.read_text())
result['log_bytes']=(r/'worker.log').stat().st_size if (r/'worker.log').exists() else 0
try:
 with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as v: result['ready']=v.status==200
except Exception: result['ready']=False
print(json.dumps(result))
"""
        return {"pod": base.clean_pod(pod), "worker": json.loads(self._ssh(pod, "python3 -c " + shlex.quote(code), timeout=30))}

    def retrieve(self, *, final=False):
        if not final:
            raise ValueError("Only settled diagnostic snapshots are exported")
        if (self.base / "final-retrieval.json").exists():
            return self._verify_final()
        pod = self.get_pod()
        if self.event("worker-intent"):
            result = json.loads(self._ssh(pod, bootstrap.stop_command(self.plan_hash), timeout=40))
            if result != {"stopped": True, "binding": self.plan_hash}:
                raise ValueError("Worker stop unverified")
        self._ssh(pod, "mkdir -p /workspace/kolibri/out", timeout=30)
        before = check_manifest(base.strict_json(self._ssh(pod, artifact_command())))
        raw = self._ssh(pod, artifact_command(pack=True), timeout=180)
        target = self.base / "retrievals" / uuid.uuid4().hex
        local = verified_archive(raw, target)
        after = check_manifest(base.strict_json(self._ssh(pod, artifact_command())))
        if before != local or after != local:
            raise ValueError("Retrieved diagnostics differ from stopped worker")
        receipt = self.record("retrieval", {"pod_id": pod["id"], "directory": str(target),
                              "artifacts": local, "retrieval_verified": True})
        self._final_receipt(receipt)
        return receipt

    def _final_receipt(self, receipt):
        path = self.base / "final-retrieval.json"
        if path.is_symlink():
            raise ValueError("Linked retrieval receipt")
        if path.exists():
            if base.strict_json(path.read_bytes()) != receipt:
                raise ValueError("Cannot replace final retrieval receipt")
            return
        super()._final_receipt(receipt)

    def _verify_final(self):
        path = self.base / "final-retrieval.json"
        if path.is_symlink():
            raise ValueError("Linked retrieval receipt")
        receipt = base.strict_json(path.read_bytes())
        if self.event(receipt["id"]) != receipt or receipt["data"]["pod_id"] != self.owned()["id"]:
            raise ValueError("Retrieval receipt not bound to this owned pod")
        data = receipt["data"]
        check_manifest(data["artifacts"])
        if data.get("retrieval_verified") is not True:
            if data.get("recovery_failed") is not True or data["artifacts"]:
                raise ValueError("Invalid recovery-failure record")
            return receipt
        directory = Path(data["directory"])
        directory.resolve().relative_to((self.base / "retrievals").resolve())
        if any(p.is_symlink() for p in [directory, *directory.parents]):
            raise ValueError("Linked retrieval directory")
        for name, digest in data["artifacts"].items():
            artifact = directory / name
            if artifact.is_symlink() or not artifact.is_file() or base.sha(artifact) != digest:
                raise ValueError("Retrieved artifact missing or changed")
        return receipt

    def terminate(self):
        """Attempt bounded recovery, then delete owned compute even on SSH failure.

        A failed diagnostic recovery is recorded as failure, never as a passed
        smoke or a verified empty snapshot. Primary HTTP receipts live locally.
        An ambiguous DELETE is reconciled by GET only, never blindly repeated.
        """
        if not self.api.writable:
            raise ValueError("Termination requires explicit execution authority")
        if self.event("closed"):
            return self.event("closed")
        if self.event("delete-intent"):
            return self._confirm_closed(self.event("delete-intent")["data"]["pod"])
        self.reconcile()
        try:
            pod = self.get_pod()
        except base.ApiError as exc:
            if exc.status == 404:
                self.record("missing-before-delete", {"pod_id": self.owned()["id"], "get_status": 404})
                return self._confirm_closed(self.owned())
            # A temporary read failure must not strand an already bound pod.
            pod = self.owned()
        except (RuntimeError, OSError):
            pod = self.owned()
        recovery_failure = None
        try:
            if not (self.base / "final-retrieval.json").exists():
                self.retrieve(final=True)
            receipt = self._verify_final()
            if receipt["data"].get("retrieval_verified") is not True:
                recovery_failure = receipt
        except BaseException as exc:
            failure = self.record("retrieval-failed", {"pod_id": pod["id"],
                                  "error_type": type(exc).__name__, "recovery_failed": True,
                                  "retrieval_verified": False, "artifacts": {}})
            # Never overwrite a previous receipt, even when it has been damaged.
            if not (self.base / "final-retrieval.json").exists():
                self._final_receipt(failure)
            recovery_failure = failure
        manifest = self.base / "final-retrieval.json"
        registry = PodRegistry(self.ledger, self.event("create-intent")["data"]["blocked"])
        if recovery_failure is not None:
            permit = self.event("emergency-delete-permit")
            if permit is None:
                permit = self.ledger.bind("emergency-delete-permit", {
                    "pod_id": pod["id"], "creation_receipt_sha256": self.event("created")["sha256"],
                    "recovery_failure_sha256": recovery_failure["sha256"],
                    "reason": "bounded_owned_compute_cleanup_after_diagnostic_recovery_failure",
                    "diagnostics_verified": False})
            elif (permit["data"]["pod_id"] != pod["id"]
                  or permit["data"]["creation_receipt_sha256"] != self.event("created")["sha256"]):
                raise ValueError("Emergency cleanup ownership differs")
        else:
            hashes = {str(manifest): base.sha(manifest)}
            permit = self.event("pod:delete:" + pod["id"])
            if permit is None:
                permit = registry.authorize_delete(pod["id"], hashes)
            elif permit["data"]["artifacts"] != hashes:
                raise ValueError("Deletion permit differs from recovery receipt")
        self.ledger.bind("delete-intent", {"permit_sha256": permit["sha256"],
                         "pod_id": pod["id"], "pod": base.clean_pod(pod)})
        try:
            status, _ = self.api.request("DELETE", "/pods/" + pod["id"])
            if status not in {204, 404}:
                raise ValueError("Unexpected deletion response")
        except (base.ApiError, RuntimeError, OSError, ValueError) as exc:
            self.record("delete-response-uncertain", {"error_type": type(exc).__name__, "pod_id": pod["id"]})
        return self._confirm_closed(pod)

    def _confirm_closed(self, pod):
        for attempt in range(6):
            try:
                self.api.request("GET", "/pods/" + pod["id"])
            except base.ApiError as exc:
                if exc.status == 404:
                    break
            except (RuntimeError, OSError):
                pass
            if attempt < 5:
                self.sleep(5)
        else:
            self.record("cleanup-unresolved", {"pod_id": pod["id"], "direct_404_observed": False})
            raise RuntimeError("Owned pod deletion remains unverified; retain its reservation")
        quote_rate = _number(self.event("create-intent")["data"]["quote"]["hourly_rate_usd"])
        rate = max(_number(pod.get("cost") or quote_rate), quote_rate)
        elapsed = self.elapsed()
        return self.ledger.bind("closed", {"pod_id": pod["id"], "get_status": 404,
            "compute_upper_bound_usd": str(elapsed * (rate + STORAGE) / 3600),
            "elapsed_seconds": str(elapsed), "utc": self.clock().isoformat()})

    def monitor(self):
        if not self.api.writable:
            raise ValueError("Lifecycle monitor requires explicit execution authority")
        if self.event("closed"):
            return self.event("closed")
        last = None
        try:
            while True:
                state = self.status()
                self.record("health", state)
                state_key = (state["worker"].get("ready"), bool(state["worker"].get("exit.json")))
                if state_key != last:
                    print(json.dumps({"pod_id": state["pod"]["id"], "kind": self.kind, "worker": state["worker"]}), flush=True)
                    last = state_key
                if "exit.json" in state["worker"] or (self.base / "STOP_SERVER").exists():
                    break
                self.cost_check(state["pod"])
                if self.kind == "main" and not self.event("server-ready"):
                    if self.elapsed() >= SERVER_STARTUP_SECONDS:
                        raise TimeoutError("Model server did not become ready within 75 minutes")
                    if state["worker"].get("ready") is True:
                        self.ledger.bind("server-ready", {"elapsed_seconds": str(self.elapsed()),
                                         "utc": self.clock().isoformat()})
                self.sleep(30)
        except BaseException as exc:
            self._cleanup_after_error("monitor-failure", exc)
            raise
        return self.terminate()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=protocol.PLAN)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--kind", choices=HARDWARE, required=True)
    parser.add_argument("--action", choices=("launch", "monitor", "status", "terminate", "reconcile"), default="status")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.action != "status" and not args.execute:
        parser.error("Mutation requires explicit execution authority")
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        raise ValueError("RunPod credential missing from local environment")
    controller = Controller(ROOT / args.plan, args.freeze, args.kind, base.RunPodV2(key, writable=args.execute))
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        if args.action == "launch":
            controller.launch()
            result = controller.monitor()
        else:
            result = getattr(controller, args.action)()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
