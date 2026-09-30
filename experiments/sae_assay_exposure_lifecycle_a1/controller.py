"""A1 process inspection and cost carry-forward; no scientific/runtime changes.

The frozen launcher remains responsible for the shared flock, permanent closing
fence and closing fd9 in both background launcher and worker. Known-PID actions
need only stat/group inventory and exact leader identity, never foreign environ.
Missing-PID recovery discovers the frozen timeout launcher's exact argv markers;
in-flight shell candidates block reconciliation, but are never signalled.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import uuid

from experiments.sae_assay_exposure import controller as original
from experiments.sae_assay_diagnostic.budget import PodRegistry, _number, _utc
from . import protocol

PRIOR_TOTAL = Decimal(protocol.PRIOR_TOTAL)
MAX_NEW = Decimal(protocol.REMAINING)
FAILED_COST = Decimal(protocol.FAILED_COST)


def reconcile_worker(remote, binding, action, *, proc_root="/proc"):
    """Self-contained remote helper. Never read environments of foreign groups."""
    import fcntl
    import json
    import os
    from pathlib import Path
    import signal
    import stat
    import time

    root, proc = Path(remote), Path(proc_root)
    pidfile, fence = root / "worker.pid", root / "worker-closing.json"
    markers = [("CODEX_EXPOSURE_" + k + "=" + v).encode() for k, v in (
        ("NAMESPACE", "exposure-controller"), ("WORKER_ID", binding["worker_id"]),
        ("FREEZE", binding["freeze_commit"]), ("POD_ID", binding["pod_id"]))]

    def write_once(path, value):
        if path.is_symlink():
            raise RuntimeError("worker evidence symlink")
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise RuntimeError("worker evidence binding mismatch")
        else:
            with path.open("x") as stream:
                json.dump(value, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())

    def scan():
        table = {}
        for directory in proc.glob("[0-9]*"):
            try:
                fields = (directory / "stat").read_text().rsplit(") ", 1)[1].split()
                if fields[0] not in ("Z", "X"):
                    table[int(directory.name)] = {"state": fields[0], "group": int(fields[2]),
                                                  "session": int(fields[3]), "start": fields[19]}
            except (FileNotFoundError, ProcessLookupError):
                pass
            except (OSError, ValueError, IndexError):
                raise RuntimeError("worker process stat inventory incomplete") from None
        return table

    def argv(pid):
        return (proc / str(pid) / "cmdline").read_bytes().split(b"\0")

    def identity(pid):
        # The timeout leader has the markers as individual argv entries. Other
        # explicitly recorded leaders may prove them through exact environ keys.
        try:
            if all(marker in argv(pid) for marker in markers):
                return True
        except (FileNotFoundError, ProcessLookupError):
            return False
        except OSError:
            pass
        try:
            environment = (proc / str(pid) / "environ").read_bytes().split(b"\0")
            return all(marker in environment for marker in markers)
        except (FileNotFoundError, ProcessLookupError):
            return False
        except OSError:
            raise RuntimeError("owned worker leader identity inaccessible") from None

    def candidates(table):
        found = set()
        for pid in table:
            try:
                command = argv(pid)
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError:
                raise RuntimeError("missing-PID command inventory incomplete") from None
            if all(marker in command for marker in markers):
                found.add(pid)
            elif any(markers[1] in argument for argument in command):
                # Includes delayed SSH/bash launch strings and partial markers.
                # Do not signal their session even if it happens to be a leader.
                raise RuntimeError("in-flight or ambiguous worker launcher")
        return found

    def members(table, pid):
        return {p: value for p, value in table.items() if value["group"] == pid}

    def finish(pid, missing, recovered):
        result = {"action": action, "verified": True, "pid": pid, "binding": binding,
                  "missing_pid": missing, "recovered_pid": recovered}
        if action == "stop":
            result.update(stopped=True, dispatch_fenced=True, owned_group_quiescent=True,
                          proof_scope=("fenced-dispatch-command-inventory" if pid is None
                                       else "recorded-worker-group-and-session"))
            terminal = root / "out/controller-stopped.json"
            if terminal.is_symlink():
                raise RuntimeError("worker evidence symlink")
            if terminal.exists():
                old = json.loads(terminal.read_text())
                if (old.get("binding") != binding or old.get("stopped") is not True
                        or old.get("dispatch_fenced") is not True):
                    raise RuntimeError("worker stopped receipt binding mismatch")
            else:
                write_once(terminal, result)
        return result

    if action not in ("pause", "resume", "stop"):
        raise RuntimeError("invalid worker action")
    fd = os.open(root / "worker-dispatch.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError("invalid worker lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        if action == "stop":
            write_once(fence, binding)
        elif fence.exists():
            raise RuntimeError("worker lifecycle fenced")
        if pidfile.is_symlink():
            raise RuntimeError("worker PID symlink")
        table, missing, recovered = scan(), not pidfile.exists(), False
        if missing:
            found = candidates(table)
            if not found:
                if action != "stop":
                    raise RuntimeError("worker PID absent before stop")
                time.sleep(0.1)
                if candidates(scan()):
                    raise RuntimeError("worker appeared during reconciliation")
                return finish(None, True, False)
            groups = {table[p]["group"] for p in found}
            if len(groups) != 1:
                raise RuntimeError("ambiguous worker process groups")
            pid = next(iter(groups))
            leader = table.get(pid)
            command = argv(pid) if leader else []
            if (not leader or leader["session"] != pid or pid not in found
                    or not command or Path(os.fsdecode(command[0])).name != "timeout"
                    or not identity(pid)):
                raise RuntimeError("unbound live worker without PID")
            if action != "stop":
                raise RuntimeError("worker PID recovery requires stop")
            with pidfile.open("x") as stream:
                stream.write(str(pid) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            write_once(root / "out/controller-worker-reconciled.json",
                       {"binding": binding, "pid": pid, "start": leader["start"], "missing_pid": True})
            recovered = True
        else:
            raw = pidfile.read_text().strip()
            if not raw.isdecimal() or int(raw) <= 1:
                raise RuntimeError("invalid worker PID")
            pid = int(raw)
        live = members(table, pid)
        if any(v["session"] == pid and v["group"] != pid for v in table.values()):
            raise RuntimeError("worker session escaped owned group")
        if live:
            leader = table.get(pid)
            if (not leader or leader["group"] != pid or leader["session"] != pid or not identity(pid)
                    or any(v["session"] != pid for v in live.values())):
                raise RuntimeError("worker leader identity mismatch")
            start = leader["start"]

            def send(sig):
                current = scan()
                if not members(current, pid):
                    return
                if (any(v["session"] != pid for v in members(current, pid).values())
                        or pid in current and (current[pid]["start"] != start or not identity(pid))):
                    raise RuntimeError("worker identity changed before signal")
                try:
                    os.killpg(pid, sig)
                except ProcessLookupError:
                    pass

            if action == "resume":
                send(signal.SIGCONT)
            elif action == "pause":
                send(signal.SIGSTOP)
                for _ in range(100):
                    if all(v["state"] in ("T", "t") for v in members(scan(), pid).values()):
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("worker pause unverified")
            else:
                send(signal.SIGCONT)
                send(signal.SIGTERM)
                for _ in range(20):
                    if not members(scan(), pid):
                        break
                    time.sleep(0.5)
                if members(scan(), pid):
                    send(signal.SIGKILL)
                for _ in range(20):
                    if not members(scan(), pid):
                        break
                    time.sleep(0.5)
                else:
                    raise RuntimeError("worker did not stop")
        if action == "stop" and any(v["group"] == pid or v["session"] == pid for v in scan().values()):
            raise RuntimeError("owned worker group/session remains after stop")
        return finish(pid, missing, recovered)
    finally:
        os.close(fd)


WORKER_SIGNAL_SCRIPT = (inspect.getsource(reconcile_worker)
                        + "\nimport json,sys\nd=json.load(sys.stdin)\n"
                        + "print(json.dumps(reconcile_worker(d['remote'],d['binding'],d['action'])))\n")


class Controller(original.Controller):
    def __init__(self, plan_path, freeze, out, kind, api, *, amendment_path, **kwargs):
        self.amendment_path = Path(amendment_path).resolve()
        self.amendment = protocol.load_plan(self.amendment_path, freeze)
        self.amendment_hash = original.sha(self.amendment_path)
        self.amendment_relative = self.amendment_path.relative_to(original.ROOT).as_posix()
        super().__init__(plan_path, freeze, out, kind, api, **kwargs)
        if (self.relative != self.amendment["original_plan"]["path"]
                or self.plan_hash != self.amendment["original_plan"]["sha256"]):
            raise ValueError("A1 must execute the unchanged original forward plan")
        self.budget = {key: _number(value) for key, value in self.amendment["budget"].items()}
        if (self.budget["prior_total_usd"] != PRIOR_TOTAL or self.budget["exposure_max_usd"] != MAX_NEW
                or self.budget["total_usd"] != 200 or self.budget["new_paid_judge_calls"] != 0
                or self.budget["new_pro_calls"] != 0):
            raise ValueError("A1 operational budget changed")
        if self.event("create-intent") and not self.event("controller:a1"):
            raise ValueError("Cannot adopt an earlier controller's creation")
        self.ledger.bind("controller:a1", {"amendment_path": self.amendment_relative,
                         "amendment_sha256": self.amendment_hash, "budget": self.amendment["budget"],
                         "failed_startup": self.amendment["failed_startup"]})

    @original.serialized
    def launch(self):
        # The original launch embeds its old prior as a module constant. Keep
        # the same lifecycle checks, but bind the amended prior in the intent.
        if not self.api.writable or self.event("create-intent"):
            raise ValueError("Explicit fresh launch required; never repeat uncertain creation")
        if (protocol.load_plan(self.amendment_path, self.freeze) != self.amendment
                or original.sha(self.amendment_path) != self.amendment_hash
                or original.load_plan(self.plan_path, self.freeze) != self.plan
                or original.sha(self.plan_path) != self.plan_hash):
            raise ValueError("A1 amendment or original plan changed")
        self.disk_check()
        token = os.environ.get("HF_TOKEN", "")
        if not token or any(c.isspace() for c in token):
            raise ValueError("HF_TOKEN missing/malformed before creation")
        if not original.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key missing")
        key = Path(str(original.KEY.expanduser()) + ".pub").read_text().strip()
        payload = original.create_payload(self.kind, original.PREFIX + "main-" + uuid.uuid4().hex[:12], key)
        original.verify_public(self.plan_hash, self.relative, self.freeze)
        original.verify_public(self.amendment_hash, self.amendment_relative, self.freeze)
        blocked = sorted({original.frozen.BLOCKED, protocol.FAILED_POD} | {p["id"] for p in self.api.inventory()})
        PodRegistry(self.ledger, blocked)
        quoted, created = original.quote(self.api), _utc(self.clock())
        rate = _number(quoted["hourly_rate_usd"]) + _number(quoted["storage_hourly_usd"])
        cap = self.budget["exposure_max_usd"]
        if rate * original.HARD_SECONDS / 3600 > cap:
            raise ValueError("Full pod timer including retrieval is not funded")
        intent = {"payload": payload, "quote": quoted, "blocked": blocked,
                  "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=original.HARD_SECONDS - original.RETRIEVAL_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=original.HARD_SECONDS)).isoformat(),
                  "prior_total_usd": str(PRIOR_TOTAL), "local_cap_usd": str(cap),
                  "cumulative_ceiling_usd": str(PRIOR_TOTAL + cap), "failed_startup_usd": str(FAILED_COST),
                  "amendment_sha256": self.amendment_hash,
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, _number(self.monotonic())
        self._last_mono = self._mono0
        if not 0 <= (_utc(self.clock()) - created).total_seconds() <= 60:
            raise ValueError("Quote stale before creation; do not retry")
        try:
            status, pod = self.api.request("POST", "/pods", payload)
            if status != 201 or not self._new_pod(pod, intent):
                raise ValueError("Ambiguous creation response")
        except (original.ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
            pod = self.reconcile_create()
        self._register(pod)
        try:
            self.start_worker()
        except Exception as exc:
            self.record("launch-failed", {"error_type": type(exc).__name__})
            self.close_until_verified()
            raise
        return self.owned()

    def cost_check(self, pod, horizon=60):
        intent, owned = self.event("create-intent")["data"], self.owned()
        expected, quoted = intent["payload"], _number(intent["quote"]["hourly_rate_usd"])
        gpu = pod.get("gpu")
        if (any(pod.get(key) != owned[key] for key in ("id", "name", "createdAt"))
                or not 0 < _number(pod.get("cost")) <= quoted
                or not isinstance(gpu, dict) or gpu.get("id") != original.HARDWARE["main"][0]
                or type(gpu.get("count")) is not int or gpu["count"] != 1
                or _number(gpu.get("memory")) < original.HARDWARE["main"][2]
                or any(pod.get(key) != expected[key] for key in ("cloud", "image", "disk", "mounts", "ports"))):
            raise ValueError("Unknown billing rate, ownership or hardware drift")
        seconds, mono = _number(horizon), _number(self.monotonic())
        if seconds <= 0:
            raise ValueError("Positive monitoring horizon required")
        last_wall = max([self._wall0, _utc(intent["created_utc"])] + [
            _utc(row["data"]["utc"]) for row in self.ledger.read() if "elapsed_seconds" in row["data"]])
        if _utc(self.clock()) < last_wall or mono < self._last_mono:
            raise ValueError("A1 accounting clock moved backward")
        self._last_mono = mono
        elapsed, rate = self._elapsed(intent), quoted + original.STORAGE
        spent = elapsed * rate / 3600
        projected = spent + (seconds + original.RETRIEVAL_SECONDS) * rate / 3600
        self.record("accounting", {"utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
                    "compute_upper_bound_usd": str(spent), "projected_usd": str(projected),
                    "failed_startup_usd": str(FAILED_COST), "shared_subcap_projected_usd": str(FAILED_COST + projected),
                    "cumulative_projected_usd": str(PRIOR_TOTAL + projected)})
        if (elapsed + seconds >= original.HARD_SECONDS - original.RETRIEVAL_SECONDS
                or projected > self.budget["exposure_max_usd"]
                or PRIOR_TOTAL + projected > self.budget["total_usd"]):
            raise ValueError("A1 budget/retrieval reserve/deadline reached")
        return spent

    @original.serialized
    def signal_worker(self, pod, action):
        if not self.api.writable or action not in {"pause", "resume", "stop"}:
            raise ValueError("Explicit owned worker lifecycle action required")
        owned, event = self.owned(), self.event("worker-intent")
        if event is None or any(pod.get(k) != owned[k] for k in ("id", "name", "createdAt")):
            raise ValueError("No owned worker dispatch intent")
        binding = {key: event["data"].get(key) for key in ("worker_id", "pod_id", "plan_sha256", "freeze_commit")}
        if (not isinstance(binding["worker_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", binding["worker_id"])
                or binding["pod_id"] != owned["id"] or binding["plan_sha256"] != self.plan_hash
                or binding["freeze_commit"] != self.freeze):
            raise ValueError("Worker dispatch identity is not bound to this owned pod and plan")
        result = original.strict_json(self._ssh(pod, "python3 -c " + shlex.quote(WORKER_SIGNAL_SCRIPT),
                     data=json.dumps({"remote": original.REMOTE, "binding": binding, "action": action}).encode()))
        if (result.get("verified") is not True or result.get("action") != action or result.get("binding") != binding
                or action == "stop" and not all(result.get(k) is True for k in
                                                ("stopped", "dispatch_fenced", "owned_group_quiescent"))
                or action == "stop" and result.get("proof_scope") not in
                {"fenced-dispatch-command-inventory", "recorded-worker-group-and-session"}):
            raise ValueError("Owned worker signal/reconciliation unverified")
        return result

    def _confirm_closed(self, pod):
        if any(pod.get(k) != self.owned()[k] for k in ("id", "name", "createdAt")):
            raise ValueError("Unowned deletion receipt")
        try:
            self.api.request("GET", "/pods/" + pod["id"])
        except original.ApiError as exc:
            if exc.status != 404:
                raise
        else:
            raise ValueError("Deletion not verified")
        inventory = self.api.inventory()
        if pod["id"] in {item["id"] for item in inventory}:
            raise ValueError("Deleted pod still in inventory")
        intent = self.event("create-intent")["data"]
        elapsed = self._elapsed(intent)
        try:
            rate = max(_number(pod.get("cost")), _number(intent["quote"]["hourly_rate_usd"])) + original.STORAGE
            cost = elapsed * rate / 3600
        except ValueError:
            cost = None
        return self.ledger.transact("closed", lambda _: {
            "pod_id": pod["id"], "get_status": 404, "inventory_ids": sorted(p["id"] for p in inventory),
            "utc": _utc(self.clock()).isoformat(), "elapsed_seconds": str(elapsed),
            "compute_upper_bound_usd": None if cost is None else str(cost),
            "failed_startup_usd": str(FAILED_COST),
            "shared_subcap_upper_bound_usd": None if cost is None else str(FAILED_COST + cost),
            "cumulative_upper_bound_usd": None if cost is None else str(PRIOR_TOTAL + cost),
            "within_limits": (cost is not None and elapsed <= original.HARD_SECONDS
                              and cost <= self.budget["exposure_max_usd"]
                              and PRIOR_TOTAL + cost <= self.budget["total_usd"])})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("plan", "amendment", "freeze", "out"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--kind", choices=("main",), default="main")
    parser.add_argument("--action", choices=("preflight", "quote", "launch", "status", "monitor",
                                             "approve", "retrieve", "terminate", "reconcile"), default="preflight")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--barrier", choices=original.BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if (args.barrier or args.approve_plan_sha256) and args.action != "approve":
        parser.error("Approval arguments require --action approve")
    if args.action in {"launch", "monitor", "approve", "retrieve", "terminate"} and not args.launch:
        parser.error("Lifecycle mutation requires --launch")
    if args.action == "approve" and not (args.barrier and args.approve_plan_sha256):
        parser.error("Explicit barrier and original plan SHA required")
    if args.action in {"preflight", "quote"}:
        amendment = protocol.load_plan(args.amendment, args.freeze)
        result = original.preflight(args.plan, args.freeze)
        if original.sha(Path(args.plan)) != amendment["original_plan"]["sha256"]:
            raise ValueError("A1 original plan hash mismatch")
        result.update(amendment_sha256=original.sha(Path(args.amendment)),
                      failed_startup_usd=str(FAILED_COST), prior_total_usd=str(PRIOR_TOTAL),
                      new_cap_usd=str(MAX_NEW), cumulative_ceiling_usd=str(PRIOR_TOTAL + MAX_NEW))
        if args.action == "quote":
            result.update(quote=original.quote(original.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=False)),
                          network_calls=1)
    else:
        api = original.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.launch)
        controller = Controller(args.plan, args.freeze, args.out, args.kind, api, amendment_path=args.amendment)
        if args.action == "launch":
            controller.launch()
            result = controller.monitor()
        elif args.action == "approve":
            result = controller.approve(args.barrier, args.approve_plan_sha256)
        elif args.action == "terminate":
            result = controller.close_until_verified()
        else:
            result = getattr(controller, args.action)()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
