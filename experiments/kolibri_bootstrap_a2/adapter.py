"""Expose locked venv build tools, retaining both failed cheap attempts."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext, ROUND_CEILING
import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol
from experiments.openrouter_swap.ledger import _no_symlinks
from experiments.sae_assay_diagnostic.budget import EventLedger, _number, _utc

AMENDMENT = "data/kolibri_bootstrap_a2/plan_v1_20261005/AMENDMENT.json"
A1_FREEZE = "c9f0710abe6cced73fa6942c330a74dd346b190c"
FAILED_POD = "h6nig4tvgi9eex"
A1_CLOSED_SHA = "eb9ea027ef770a78e7e0cd99f7593f755b2bc0d6246b9a15ddefe83ef84915b0"
A1_RETRIEVAL_SHA = "c0e41ad4b5e84425f4bab4e39e637d4dd5243b2bfa0406c3b531449a79b8b119"
A1_WORKER_SHA = "a547cf4c4e50bb074ae825a2aeabad5edef7063ad056a3624995e40b5d444b02"


def root():
    return old.canonical_root() / "bootstrap-a2"


def predecessor(prior):
    base = a1.root()
    receipt = prod.closed_receipt(base, "cheap", a1.ORIGINAL_PLAN_SHA, A1_FREEZE)
    _, events = prod.controller_events(base, "cheap", a1.ORIGINAL_PLAN_SHA, A1_FREEZE)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    directory = Path(saved["data"]["directory"])
    smoke = prod.load(directory / "gpu-smoke.json")
    prod.check(events["closed"]["data"]["pod_id"] == FAILED_POD
               and receipt["closed_sha256"] == A1_CLOSED_SHA
               and receipt["retrieval_sha256"] == A1_RETRIEVAL_SHA
               and protocol.sha(directory / "worker.log") == A1_WORKER_SHA
               and smoke["status"] == "failed" and smoke["scientific_generation"] is False
               and smoke["parser"]["official_passed"] == 70
               and prod.load(directory / "exit.json") == {"exit_code": 1}
               and b"FileNotFoundError: [Errno 2] No such file or directory: 'ninja'" in (directory / "worker.log").read_bytes(),
               "A1 is not the preserved Ninja-path failure")
    latest = {"freeze": A1_FREEZE, "plan_sha256": a1.ORIGINAL_PLAN_SHA,
              "pod_id": FAILED_POD, **receipt,
              "events_file_sha256": protocol.sha(base / "controller/cheap/events.jsonl"),
              "retrieval_file_sha256": protocol.sha(base / "controller/cheap/final-retrieval.json")}
    with localcontext() as context:
        context.prec = 60
        total = Decimal(prior["predecessor"]["cost_usd"]) + Decimal(latest["cost_usd"])
        # Preserve exact individual costs; round only the admission carry upward.
        carry = total.quantize(Decimal("1e-26"), rounding=ROUND_CEILING)
    return {"attempts": [prior["predecessor"], latest], "exact_sum_usd": str(total), "cost_usd": str(carry)}


def sources():
    paths = [*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.md"),
             protocol.ROOT / "tests/test_kolibri_bootstrap_a2.py"]
    return {p.relative_to(protocol.ROOT).as_posix(): protocol.sha(p) for p in sorted(paths)}


def build():
    prior = a1.verify()
    carry = predecessor(prior)
    remaining = old.CAPS["cheap"] - Decimal(carry["cost_usd"])
    prod.check(remaining > 0, "Cumulative cheap allowance exhausted")
    return {"schema": "kolibri-bootstrap-a2-v1", "scientific_plan_sha256": a1.ORIGINAL_PLAN_SHA,
            "original_freeze": a1.ORIGINAL_FREEZE, "a1_freeze": A1_FREEZE,
            "a1_amendment_sha256": protocol.sha(protocol.ROOT / a1.AMENDMENT), "predecessor": carry,
            "source_hashes": sources(), "dependency_source_hashes": prior["source_hashes"],
            "status_attempts": a1.STATUS_ATTEMPTS, "cheap_total_cap_usd": "1.25",
            "cheap_remaining_usd": str(remaining), "gpu_total_cap_usd": "25", "study_total_cap_usd": "75",
            "run_root": "out/kolibri-swap-20261004/bootstrap-a2", "science_changed": False,
            "research_outcomes_observed": False, "automatic_replacement": False,
            "known_technical_outcomes": ["original: in-progress JSON race; no CUDA verdict",
                                         "A1: FlashInfer warmup cannot find installed Ninja; CUDA failed"],
            "worker_delta": "Prepend venv/bin to PATH; bounded Ninja/NVCC/C++ discovery/version checks in worker.log",
            "smoke_computation_changed": False, "hardware_and_kernels_changed": False}


def verify(freeze=None):
    path = protocol.ROOT / AMENDMENT
    value = prod.load(path)
    prod.check(value == build(), "A2 source/predecessor amendment binding differs")
    if freeze is not None:
        protocol.verify(protocol.ROOT / protocol.PLAN, freeze)
        hashes = {**value["source_hashes"], **value["dependency_source_hashes"],
                  a1.AMENDMENT: value["a1_amendment_sha256"], AMENDMENT: protocol.sha(path)}
        for name, digest in hashes.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(hashlib.sha256(body).hexdigest() == digest, "A2 dependency absent from pushed freeze")
    return value


def tool_preflight():
    return """import json,pathlib,shutil,subprocess,sys
from importlib.metadata import version
prefix=pathlib.Path(sys.executable).parent
ninja=shutil.which('ninja')
if ninja != str(prefix/'ninja'): raise RuntimeError('Locked venv Ninja is not on PATH')
distribution_version=version('ninja')
if distribution_version != '1.13.2': raise RuntimeError('Ninja distribution differs from frozen dependency lock')
tools={}
for name in ('ninja','nvcc','c++'):
 path=shutil.which(name)
 if path is None: raise RuntimeError('Required build tool absent: '+name)
 result=subprocess.run([path,'--version'],check=True,capture_output=True,text=True,timeout=20)
 banner=result.stdout.strip() or result.stderr.strip()
 if not banner: raise RuntimeError('Empty build-tool version banner: '+name)
 tools[name]={'path':path,'version':banner}
tools['ninja']['distribution_version']=distribution_version
print(json.dumps({'schema':'kolibri-build-tools-v1','tools':tools}),flush=True)
"""


def worker_script(kind, freeze, relative, seconds):
    original = bootstrap.worker_script(kind, freeze, relative, seconds)
    marker = bootstrap.REMOTE + "/venv/bin/python -m pip freeze --all > " + bootstrap.REMOTE + "/out/pip-freeze.txt\n"
    prod.check(original.count(marker) == 1, "Frozen worker insertion point changed")
    addition = ('export PATH="' + bootstrap.REMOTE + '/venv/bin:$PATH"\n'
                + shlex.join([bootstrap.REMOTE + "/venv/bin/python", "-c", tool_preflight()]) + "\n")
    return original.replace(marker, marker + addition)


class Controller(a1.Controller):
    def __init__(self, freeze, kind, api, *, run=subprocess.run, clock=old.base.now, sleep=time.sleep):
        prod.check(kind in old.HARDWARE, "Unknown pod role")
        self.amendment = verify(freeze)
        self.amendment_hash = protocol.sha(protocol.ROOT / AMENDMENT)
        self.plan_path, self.freeze, self.kind = protocol.ROOT / protocol.PLAN, freeze, kind
        self.plan = protocol.verify(self.plan_path)
        self.plan_hash, self.relative = a1.ORIGINAL_PLAN_SHA, protocol.PLAN
        self.out, self.base = root(), root() / "controller" / kind
        _no_symlinks(self.base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": kind, "plan": self.relative,
            "image": bootstrap.IMAGE, "cap_usd": str(old.CAPS[kind]),
            "amendment_sha256": self.amendment_hash, "a1_freeze": A1_FREEZE,
            "prior_cheap_usd": self.amendment["predecessor"]["cost_usd"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()

    def _new_pod(self, pod, intent):
        return pod.get("id") != FAILED_POD and super()._new_pod(pod, intent)

    def start_worker(self):
        # Same owned dispatch/timeout lifecycle; only worker_script differs.
        prod.check(not self.event("worker-intent"), "Worker was already dispatched")
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
        script = worker_script(self.kind, self.freeze, self.relative, remaining)
        self._ssh(pod, "umask 077; mkdir -p /workspace/kolibri/out; test ! -e /workspace/kolibri/worker.sh; cat > /workspace/kolibri/worker.sh",
                  data=script.encode(), timeout=60)
        self.ledger.bind("worker-intent", {"sha256": hashlib.sha256(script.encode()).hexdigest(),
                         "seconds": remaining, "created_utc": self.clock().isoformat()})
        self._ssh(pod, bootstrap.start_command(remaining, self.plan_hash), timeout=60)
        self.ledger.bind("worker-started", {"pod_id": pod["id"]})


class StudyGuard(prod.StudyGuard):
    def __init__(self, *args, amendment, **kwargs):
        self.amendment = amendment
        super().__init__(*args, **kwargs)
        prod.check(_number(self.cheap["cost_usd"]) + _number(amendment["predecessor"]["cost_usd"])
                   <= old.CAPS["cheap"], "Cumulative cheap allowance exceeded")
        for kind in ("cheap", "main"):
            _, events = prod.controller_events(self.root, kind, self.plan_hash, self.freeze)
            prod.check(events["controller:config"]["data"].get("amendment_sha256") == protocol.sha(protocol.ROOT / AMENDMENT),
                       "Controller receipt lacks A2 binding")

    def state(self, *args, **kwargs):
        result = super().state(*args, **kwargs)
        result["prior_cheap_usd"] = _number(self.amendment["predecessor"]["cost_usd"])
        result["gpu_usd"] += result["prior_cheap_usd"]
        prod.check(kwargs.get("permit_stop") or result["gpu_usd"] <= 25, "GPU allowance including both failures exhausted")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-amendment", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--kind", choices=old.HARDWARE)
    parser.add_argument("--action", choices=("launch", "monitor", "status", "terminate", "reconcile"), default="status")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.build_amendment:
        prod.check(not args.execute and args.kind is None and args.freeze is None, "Build is offline only")
        print(protocol.canonical(build()))
        return
    prod.check(args.kind is not None and args.freeze is not None, "Role and technical freeze required")
    prod.check(args.action == "status" or args.execute, "Lifecycle mutation requires explicit execution")
    ctl = Controller(args.freeze, args.kind, old.base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.execute))
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        if args.action == "launch":
            ctl.launch()
            result = ctl.monitor()
        else:
            result = getattr(ctl, args.action)()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(protocol.canonical({"receipt": result, "prior_cheap_usd": ctl.amendment["predecessor"]["cost_usd"]}))


if __name__ == "__main__":
    main()
