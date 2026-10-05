"""One separately frozen bootstrap recovery, with no scientific-call retries."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol
from experiments.openrouter_swap.ledger import _no_symlinks
from experiments.sae_assay_diagnostic.budget import EventLedger, _number

ORIGINAL_FREEZE = "94d9913267925c39bf3e7086245db2dc40430c9d"
ORIGINAL_PLAN_SHA = "b3bf5539e89b20752073c68aee4045d2662c282264724d774b97b40263908609"
FAILED_POD = "2r5mg2qc6ffk84"
AMENDMENT = "data/kolibri_bootstrap_a1/plan_v1_20261004/AMENDMENT.json"
STATUS_ATTEMPTS = 3


def root():
    return old.canonical_root() / "bootstrap-a1"


def predecessor():
    base = old.canonical_root()
    receipt = prod.closed_receipt(base, "cheap", ORIGINAL_PLAN_SHA, ORIGINAL_FREEZE)
    _, events = prod.controller_events(base, "cheap", ORIGINAL_PLAN_SHA, ORIGINAL_FREEZE)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    directory = Path(saved["data"]["directory"])
    prod.check(events["closed"]["data"]["pod_id"] == FAILED_POD
               and (directory / "gpu-smoke.json").read_bytes() == b""
               and prod.load(directory / "exit.json") == {"exit_code": 143},
               "Predecessor is not the preserved incomplete smoke failure")
    return {"freeze": ORIGINAL_FREEZE, "plan_sha256": ORIGINAL_PLAN_SHA,
            "pod_id": FAILED_POD, **receipt,
            "events_file_sha256": protocol.sha(base / "controller/cheap/events.jsonl"),
            "retrieval_file_sha256": protocol.sha(base / "controller/cheap/final-retrieval.json")}


def sources():
    paths = [*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.md"),
             protocol.ROOT / "tests/test_kolibri_bootstrap_a1.py"]
    return {p.relative_to(protocol.ROOT).as_posix(): protocol.sha(p) for p in sorted(paths)}


def build():
    """Return a candidate only; caller owns review, writing, commit and push."""
    path = protocol.ROOT / protocol.PLAN
    plan = protocol.verify(path)
    prod.check(protocol.sha(path) == ORIGINAL_PLAN_SHA and plan["launch_authorized"],
               "Original scientific plan changed or lacks authority")
    prior = predecessor()
    remaining = old.CAPS["cheap"] - _number(prior["cost_usd"])
    prod.check(remaining > 0, "Original cumulative cheap allowance exhausted")
    return {"schema": "kolibri-bootstrap-a1-v1", "scientific_plan_sha256": ORIGINAL_PLAN_SHA,
            "original_freeze": ORIGINAL_FREEZE, "predecessor": prior,
            "source_hashes": sources(), "status_attempts": STATUS_ATTEMPTS,
            "cheap_total_cap_usd": "1.25", "cheap_remaining_usd": str(remaining),
            "gpu_total_cap_usd": "25", "study_total_cap_usd": "75",
            "run_root": "out/kolibri-swap-20261004/bootstrap-a1",
            "science_changed": False, "research_outcomes_observed": False,
            "known_technical_outcome": "empty smoke receipt; controller terminated worker; no CUDA verdict",
            "automatic_replacement": False}


def verify(freeze=None):
    path = protocol.ROOT / AMENDMENT
    value = prod.load(path)
    prod.check(value == build(), "Technical amendment/source/predecessor binding differs")
    if freeze is not None:
        protocol.verify(protocol.ROOT / protocol.PLAN, freeze)
        for name, digest in {**value["source_hashes"], AMENDMENT: protocol.sha(path)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(hashlib.sha256(body).hexdigest() == digest,
                       "Technical amendment is not in pushed freeze")
    return value


def status_command():
    # gpu_smoke creates its final file before computation. Existence is not a
    # settled receipt; only complete JSON is exposed under the original keys.
    code = """import json,pathlib,urllib.request
r=pathlib.Path('/workspace/kolibri/out'); result={'pending_json':[]}
for name in ['exit.json','gpu-smoke.json','runtime.json']:
 p=r/name
 if p.exists():
  try: value=json.loads(p.read_bytes())
  except (ValueError,UnicodeError): result['pending_json'].append(name)
  else:
   if not isinstance(value,dict): raise ValueError('Invalid worker JSON object')
   result[name]=value
result['log_bytes']=(r/'worker.log').stat().st_size if (r/'worker.log').exists() else 0
try:
 with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2) as v: result['ready']=v.status==200
except Exception: result['ready']=False
result['incomplete_after_exit']=bool(result['pending_json'] and 'exit.json' in result)
print(json.dumps(result))
"""
    return "python3 -c " + shlex.quote(code)


class Controller(old.Controller):
    def __init__(self, freeze, kind, api, *, run=subprocess.run, clock=old.base.now, sleep=time.sleep):
        prod.check(kind in old.HARDWARE, "Unknown pod role")
        self.amendment = verify(freeze)
        self.amendment_hash = protocol.sha(protocol.ROOT / AMENDMENT)
        self.plan_path, self.freeze, self.kind = protocol.ROOT / protocol.PLAN, freeze, kind
        self.plan = protocol.verify(self.plan_path)
        self.plan_hash, self.relative = ORIGINAL_PLAN_SHA, protocol.PLAN
        self.out, self.base = root(), root() / "controller" / kind
        _no_symlinks(self.base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": kind, "plan": self.relative,
            "image": bootstrap.IMAGE, "cap_usd": str(old.CAPS[kind]),
            "amendment_sha256": self.amendment_hash,
            "prior_cheap_usd": self.amendment["predecessor"]["cost_usd"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()

    def _new_pod(self, pod, intent):
        return pod.get("id") != FAILED_POD and super()._new_pod(pod, intent)

    def status(self):
        for attempt in range(1, STATUS_ATTEMPTS + 1):
            pod = self.get_pod()  # Ownership failures are never softened by retry.
            self.cost_check(pod, horizon=60)
            try:
                worker = old.base.strict_json(self._ssh(pod, status_command(), timeout=30))
                prod.check(isinstance(worker, dict) and type(worker.get("ready")) is bool
                           and isinstance(worker.get("pending_json"), list), "Invalid status snapshot")
                return {"pod": old.base.clean_pod(pod), "worker": worker}
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                self.record("status-read-failure", {"attempt": attempt, "error_type": type(exc).__name__})
                if attempt == STATUS_ATTEMPTS:
                    raise RuntimeError("Status snapshot failed after three bounded reads") from None
                self.sleep(5)

    def cost_check(self, pod, horizon=60):
        spent = super().cost_check(pod, horizon)
        if self.kind == "cheap":
            rate = _number(pod["cost"]) + old.STORAGE
            prior = _number(self.amendment["predecessor"]["cost_usd"])
            prod.check(prior + spent + Decimal(horizon + old.CLEANUP_RESERVE_SECONDS) * rate / 3600
                       <= old.CAPS["cheap"], "Cumulative cheap recovery allowance exhausted")
        return spent

    def cheap_pass(self):
        result = super().cheap_pass()
        receipt = prod.closed_receipt(self.out, "cheap", self.plan_hash, self.freeze, smoke=True)
        prod.check(_number(receipt["cost_usd"]) + _number(self.amendment["predecessor"]["cost_usd"])
                   <= old.CAPS["cheap"], "Cumulative cheap allowance exceeded")
        _, events = prod.controller_events(self.out, "cheap", self.plan_hash, self.freeze)
        prod.check(events["controller:config"]["data"]["amendment_sha256"] == self.amendment_hash,
                   "Cheap receipt is not bound to A1")
        return result


class StudyGuard(prod.StudyGuard):
    def __init__(self, *args, amendment, **kwargs):
        self.amendment = amendment
        super().__init__(*args, **kwargs)
        prod.check(_number(self.cheap["cost_usd"]) + _number(amendment["predecessor"]["cost_usd"])
                   <= old.CAPS["cheap"], "Cumulative cheap allowance exceeded")
        digest = protocol.sha(protocol.ROOT / AMENDMENT)
        for kind in ("cheap", "main"):
            _, events = prod.controller_events(self.root, kind, self.plan_hash, self.freeze)
            prod.check(events["controller:config"]["data"].get("amendment_sha256") == digest,
                       "Controller receipt lacks technical amendment binding")

    def state(self, *args, **kwargs):
        result = super().state(*args, **kwargs)
        result["prior_cheap_usd"] = _number(self.amendment["predecessor"]["cost_usd"])
        result["gpu_usd"] += result["prior_cheap_usd"]
        prod.check(kwargs.get("permit_stop") or result["gpu_usd"] <= Decimal("25"),
                   "GPU allowance including predecessor exhausted")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-amendment", action="store_true", help="Candidate JSON on stdout only")
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
    key = os.environ.get("RUNPOD_API_KEY")
    ctl = Controller(args.freeze, args.kind, old.base.RunPodV2(key, writable=args.execute))
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
