"""One CLI-only main retry, with immutable A4 qualification and cumulative costs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_CEILING
import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from experiments.kolibri_bootstrap_a4 import adapter as a4
from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol
from experiments.openrouter_swap.ledger import _no_symlinks
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc
from .cli import serve_argv, PARSER_SOURCES, WHEEL_SHA256

AMENDMENT = "data/kolibri_bootstrap_a5/plan_v1_20261005/AMENDMENT.json"
A4_FREEZE = "9b05876f0c68d31ee85de851bd8e0fd40acb6bb1"
A2_FREEZE, JUDGE_FREEZE = a4.A2_FREEZE, a4.JUDGE_FREEZE
FAILED_POD = "9j9m3kgnhct2m3"
QUALIFIED_POD = "go4bpsmwvev2ke"
CLOSED_SHA = "1a261cfa4730800c96c71c0d890e0c41d991a5b9710d19a5cf797e6b4f91f717"
RETRIEVAL_SHA = "1da31a257c4c973f9535969ffb1a214a2b146d0b2b92461ea5aa233d092857aa"
QUALIFIED_CLOSED_SHA = "6e146160c6cf658d4d4423e937cbbf968fd614229e3f83f9b718248bda1ec725"
QUALIFIED_RETRIEVAL_SHA = "acc5705019601cbf01d16642eedde741f23d663170f81e8598aab73b64676870"


def root():
    return old.canonical_root() / "bootstrap-a5"


def qualification(prior):
    receipt = a4.qualified_cheap(a4.root(), A4_FREEZE, a4.a1.ORIGINAL_PLAN_SHA, prior)
    _, events = prod.controller_events(a4.root(), "cheap", a4.a1.ORIGINAL_PLAN_SHA, A4_FREEZE)
    prod.check(events["created"]["data"]["id"] == QUALIFIED_POD
               and receipt["closed_sha256"] == QUALIFIED_CLOSED_SHA
               and receipt["retrieval_sha256"] == QUALIFIED_RETRIEVAL_SHA,
               "A4 qualified receipt differs")
    return receipt


def predecessor(prior):
    cheap = qualification(prior)
    base = a4.root()
    main = prod.closed_receipt(base, "main", a4.a1.ORIGINAL_PLAN_SHA, A4_FREEZE)
    _, events = prod.controller_events(base, "main", a4.a1.ORIGINAL_PLAN_SHA, A4_FREEZE)
    saved = prod.load(base / "controller/main/final-retrieval.json")
    directory = Path(saved["data"]["directory"])
    model = prod.load(directory / "model-files.json")
    frozen = prod.load(protocol.ROOT / protocol.PLAN)["metadata"]["model_artifacts"]["files"]
    observed = {row["path"]: row for row in model["files"]}
    prod.check(events["created"]["data"]["id"] == FAILED_POD
               and main["closed_sha256"] == CLOSED_SHA and main["retrieval_sha256"] == RETRIEVAL_SHA
               and "server-ready" not in events and not (base / "collection").exists()
               and prod.load(directory / "exit.json") == {"exit_code": 2}
               and b"vllm: error: unrecognized arguments: --disable-log-requests" in (directory / "worker.log").read_bytes()
               and model["verified"] and model["config_verified"] and model["weight_map_verified"]
               and model["revision"] == bootstrap.MODEL_REVISION and model["model"] == bootstrap.MODEL
               and model["plan_sha256"] == a4.a1.ORIGINAL_PLAN_SHA
               and model["frozen_files_verified"] == len(frozen)
               and all(observed[name]["sha256"] == value["sha256"]
                       and observed[name]["bytes"] == value["size"] for name, value in frozen.items()),
               "A4 is not the preserved pre-outcome CLI-only failure")
    latest = []
    for kind, pod, receipt in (("cheap", QUALIFIED_POD, cheap), ("main", FAILED_POD, main)):
        folder = base / "controller" / kind
        latest.append({"kind": kind, "freeze": A4_FREEZE, "plan_sha256": a4.a1.ORIGINAL_PLAN_SHA,
            "pod_id": pod, **receipt, "events_file_sha256": protocol.sha(folder / "events.jsonl"),
            "retrieval_file_sha256": protocol.sha(folder / "final-retrieval.json")})
    with localcontext() as context:
        context.prec = 60
        added = sum((Decimal(r["cost_usd"]) for r in latest), Decimal(0))
        exact = Decimal(prior["predecessor"]["exact_sum_usd"]) + added
        bound = Decimal(prior["predecessor"]["cost_usd"]) + added
        carry = bound.quantize(Decimal("1e-26"), rounding=ROUND_CEILING)
        remaining = a4.CAPS["main"] - Decimal(main["cost_usd"])
    return {"attempts": [*prior["predecessor"]["attempts"], *latest], "exact_sum_usd": str(exact),
        "prior_admission_plus_latest_usd": str(bound), "cost_usd": str(carry)}, cheap, str(remaining)


def sources():
    paths = [*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.md"),
             protocol.ROOT / "tests/test_kolibri_bootstrap_a5.py"]
    return {p.relative_to(protocol.ROOT).as_posix(): protocol.sha(p) for p in sorted(paths)}


def build():
    prior = a4.verify()
    carry, cheap, remaining = predecessor(prior)
    prod.check(Decimal(remaining) > 0 and Decimal(carry["cost_usd"]) + Decimal(remaining) <= 25,
               "Cumulative GPU allowance exhausted")
    return {"schema": "kolibri-bootstrap-a5-v1", "scientific_plan_sha256": a4.a1.ORIGINAL_PLAN_SHA,
        "original_freeze": a4.a1.ORIGINAL_FREEZE, "a4_freeze": A4_FREEZE,
        "a4_amendment_sha256": protocol.sha(protocol.ROOT / a4.AMENDMENT),
        "predecessor": carry, "qualification": {"freeze": A4_FREEZE, "pod_id": QUALIFIED_POD, **cheap},
        "source_hashes": sources(), "dependency_source_hashes": {
            **prior["dependency_source_hashes"], **prior["source_hashes"]}, "judge_policy": prior["judge_policy"],
        "main_cap_usd": remaining, "gpu_total_cap_usd": "25", "judge_cap_usd": "45",
        "storage_recovery_cap_usd": "5", "study_total_cap_usd": "75",
        "run_root": "out/kolibri-swap-20261004/bootstrap-a5", "new_cheap_pod": False,
        "automatic_replacement": False, "science_changed": False, "research_outcomes_observed": False,
        "known_technical_outcomes": [*prior["known_technical_outcomes"],
            "A4: CUDA qualification passed; main verified model files then rejected obsolete serve flag before startup"],
        "serve_argv": serve_argv(), "pinned_vllm_wheel_sha256": WHEEL_SHA256,
        "parser_source_hashes": PARSER_SOURCES, "cli_preflight_before_model_download": True,
        "qualification_computation_changed": False, "judge_policy_changed": False}


def verify(freeze=None):
    path = protocol.ROOT / AMENDMENT
    value = prod.load(path)
    prod.check(value == build(), "A5 source/predecessor binding differs")
    if freeze is not None:
        a4.verify(freeze)
        subprocess.run(["git", "merge-base", "--is-ancestor", A4_FREEZE, freeze],
                       cwd=protocol.ROOT, check=True, timeout=10)
        for name, digest in {**value["source_hashes"], AMENDMENT: protocol.sha(path)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(hashlib.sha256(body).hexdigest() == digest, "A5 source absent from pushed freeze")
    return value


def worker_script(kind, freeze, relative, seconds):
    prod.check(kind == "main", "A5 reuses A4 qualification; no new cheap pod")
    script = a4.worker_script(kind, freeze, relative, seconds)
    old_argv = serve_argv()[:-1] + ["--disable-log-requests"]
    old_line = shlex.join(old_argv)
    prod.check(script.count(old_line) == 1, "Frozen full production argv differs")
    marker = shlex.join([a4.LOCAL_VENV + "/bin/python", "-m", "experiments.kolibri_swap.model_files"])
    prod.check(script.count(marker) == 1, "Model download boundary differs")
    preflight = shlex.join([a4.LOCAL_VENV + "/bin/python", "-m", "experiments.kolibri_bootstrap_a5.cli"])
    return script.replace(old_line, shlex.join(serve_argv())).replace(marker, preflight + "\n" + marker)


class Controller(a4.Controller):
    def __init__(self, freeze, kind, api, *, run=subprocess.run, clock=old.base.now, sleep=time.sleep):
        prod.check(kind == "main", "A5 permits only one main retry")
        self.amendment = verify(freeze)
        self.amendment_hash = protocol.sha(protocol.ROOT / AMENDMENT)
        self.plan_path, self.freeze, self.kind = protocol.ROOT / protocol.PLAN, freeze, kind
        self.plan = protocol.verify(self.plan_path)
        self.plan_hash, self.relative = a4.a1.ORIGINAL_PLAN_SHA, protocol.PLAN
        self.out, self.base = root(), root() / "controller/main"
        _no_symlinks(self.base); self.base.mkdir(parents=True, exist_ok=True)
        self.api, self.run, self.clock, self.sleep = api, run, clock, sleep
        self.ledger = EventLedger(self.base / "events.jsonl", self.plan_hash, freeze, [])
        self.ledger.bind("controller:config", {"kind": kind, "plan": self.relative, "image": bootstrap.IMAGE,
            "cap_usd": self.amendment["main_cap_usd"], "amendment_sha256": self.amendment_hash,
            "a4_freeze": A4_FREEZE, "prior_gpu_usd": self.amendment["predecessor"]["cost_usd"],
            "qualification": self.amendment["qualification"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()
        self.api = a4.ReadRetryAPI(api, self.read_guard, self.record, self.sleep)

    def attempt_cap(self):
        return Decimal(self.amendment["main_cap_usd"])

    def cheap_pass(self):
        receipt = qualification(a4.verify())
        prod.check(self.amendment["qualification"] == {"freeze": A4_FREEZE, "pod_id": QUALIFIED_POD, **receipt},
                   "Reused qualification differs from A5 source-bound record")
        return receipt

    def _new_pod(self, pod, intent):
        return pod.get("id") not in {FAILED_POD, QUALIFIED_POD} and super()._new_pod(pod, intent)

    def start_worker(self):
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
    def __init__(self, root, plan, freeze, plan_hash, ledger, *, amendment, clock=None):
        self.root, self.plan, self.freeze, self.plan_hash, self.ledger = root, plan, freeze, plan_hash, ledger
        self.clock, self.amendment = clock or (lambda: datetime.now(timezone.utc)), amendment
        self.cheap = qualification(a4.verify())
        prod.check(amendment["qualification"] == {"freeze": A4_FREEZE, "pod_id": QUALIFIED_POD, **self.cheap},
                   "Production qualification differs")
        _, events = prod.controller_events(root, "main", plan_hash, freeze)
        cfg = events["controller:config"]["data"]
        prod.check(cfg.get("amendment_sha256") == protocol.sha(protocol.ROOT / AMENDMENT)
                   and cfg.get("a4_freeze") == A4_FREEZE and cfg.get("qualification") == amendment["qualification"]
                   and cfg.get("prior_gpu_usd") == amendment["predecessor"]["cost_usd"]
                   and cfg.get("cap_usd") == amendment["main_cap_usd"], "A5 main controller binding differs")

    def state(self, *args, **kwargs):
        result = super().state(*args, **kwargs)
        with localcontext() as context:
            context.prec = 60
            result["prior_gpu_usd"] = Decimal(self.amendment["predecessor"]["cost_usd"])
            result["gpu_usd"] = result["main_usd"] + result["prior_gpu_usd"]
        prod.check(kwargs.get("permit_stop") or result["gpu_usd"] <= 25
                   and result["main_usd"] <= Decimal(self.amendment["main_cap_usd"]), "Cumulative A5 GPU allowance exhausted")
        return result

    def admission(self, runner):
        result = super().admission(runner)
        state = self.state(running=True)
        duration = Decimal(result["main_seconds_with_margin"])
        rate = Decimal(self.plan["budget"]["gpu_hourly_usd"]) + old.STORAGE
        prod.check(state["main_usd"] + duration * rate / 3600 <= Decimal(self.amendment["main_cap_usd"]),
                   "Whole main cannot fit remaining A5 allowance")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-amendment", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--kind", choices=["main"])
    parser.add_argument("--action", choices=("launch", "monitor", "status", "terminate", "reconcile"), default="status")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.build_amendment:
        prod.check(not args.execute and args.kind is None and args.freeze is None, "Build is offline only")
        print(protocol.canonical(build())); return
    prod.check(args.kind == "main" and args.freeze is not None, "Main role and pushed freeze required")
    prod.check(args.action == "status" or args.execute, "Lifecycle mutation requires explicit execution")
    ctl = Controller(args.freeze, args.kind, old.base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=args.execute))
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        if args.action == "launch":
            ctl.launch(); result = ctl.monitor()
        else:
            result = getattr(ctl, args.action)()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(protocol.canonical({"receipt": result, "prior_gpu_usd": ctl.amendment["predecessor"]["cost_usd"]}))


if __name__ == "__main__":
    main()
