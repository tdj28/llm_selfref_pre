"""A3 owned lifecycle with source-bound runtime bridge and all failures carried."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext, ROUND_CEILING
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments import kolibri_judge_transport as transport
from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol
from experiments.openrouter_swap.ledger import _no_symlinks
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc

AMENDMENT = "data/kolibri_bootstrap_a3/plan_v1_20261005/AMENDMENT.json"
A2_FREEZE = "9333faaf8d38a579cc9815d7b068d6c90ade4abf"
JUDGE_FREEZE = "444a1a181f1056e24d18ebe89f93a941810dd2e4"
FAILED_POD = "nnftu0afnnrv65"
CLOSED_SHA = "9baa74abe49daef43037322434f7a3ca1ee47ab23b4ee356529c288913a39143"
RETRIEVAL_SHA = "1f718a44c5962e53275901ff765db8e76943bdf2232f0bd18bf54669c3df5bc5"
WORKER_SHA = "acea7d9585a2e9b895f5905376d999dac5dde324be4f9aec4771a4070e464ab9"


def root():
    return old.canonical_root() / "bootstrap-a3"


def predecessor(prior):
    base = a2.root()
    receipt = prod.closed_receipt(base, "cheap", a1.ORIGINAL_PLAN_SHA, A2_FREEZE)
    _, events = prod.controller_events(base, "cheap", a1.ORIGINAL_PLAN_SHA, A2_FREEZE)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    directory = Path(saved["data"]["directory"])
    smoke = prod.load(directory / "gpu-smoke.json")
    log = (directory / "worker.log").read_bytes()
    prod.check(events["closed"]["data"]["pod_id"] == FAILED_POD
               and receipt["closed_sha256"] == CLOSED_SHA and receipt["retrieval_sha256"] == RETRIEVAL_SHA
               and protocol.sha(directory / "worker.log") == WORKER_SHA
               and smoke["status"] == "failed" and smoke["scientific_generation"] is False
               and smoke["parser"]["official_passed"] == 70
               and smoke["error"] == "Exception: Call to collective_rpc method failed: Linear is not FP8"
               and prod.load(directory / "exit.json") == {"exit_code": 1}
               and b"Selected MarlinFP8ScaledMMLinearKernel for Fp8LinearMethod" in log,
               "A2 is not the preserved FP8 storage-assertion failure")
    latest = {"freeze": A2_FREEZE, "plan_sha256": a1.ORIGINAL_PLAN_SHA, "pod_id": FAILED_POD, **receipt,
              "events_file_sha256": protocol.sha(base / "controller/cheap/events.jsonl"),
              "retrieval_file_sha256": protocol.sha(base / "controller/cheap/final-retrieval.json")}
    with localcontext() as context:
        context.prec = 60
        exact = Decimal(prior["predecessor"]["exact_sum_usd"]) + Decimal(latest["cost_usd"])
        admission = Decimal(prior["predecessor"]["cost_usd"]) + Decimal(latest["cost_usd"])
        carry = admission.quantize(Decimal("1e-26"), rounding=ROUND_CEILING)
    return {"attempts": [*prior["predecessor"]["attempts"], latest], "exact_sum_usd": str(exact),
            "prior_admission_plus_latest_usd": str(admission), "cost_usd": str(carry)}


def sources():
    paths = [*Path(__file__).parent.glob("*.py"), *Path(__file__).parent.glob("*.md"),
             protocol.ROOT / "tests/test_kolibri_bootstrap_a3.py"]
    return {p.relative_to(protocol.ROOT).as_posix(): protocol.sha(p) for p in sorted(paths)}


def build():
    prior = a2.verify()
    policy = transport.verify(protocol.ROOT / transport.PLAN)
    prod.check(policy["worker_freeze"] == A2_FREEZE, "Original judge policy worker binding differs")
    carry = predecessor(prior)
    remaining = old.CAPS["cheap"] - Decimal(carry["cost_usd"])
    prod.check(remaining > 0, "Cumulative cheap allowance exhausted")
    return {"schema": "kolibri-bootstrap-a3-v1", "scientific_plan_sha256": a1.ORIGINAL_PLAN_SHA,
            "original_freeze": a1.ORIGINAL_FREEZE, "a2_freeze": A2_FREEZE,
            "a2_amendment_sha256": protocol.sha(protocol.ROOT / a2.AMENDMENT),
            "predecessor": carry, "source_hashes": sources(),
            "dependency_source_hashes": {**prior["dependency_source_hashes"], **prior["source_hashes"],
                                         **policy["source_hashes"]},
            "judge_policy": {"freeze": JUDGE_FREEZE, "path": transport.PLAN,
                             "sha256": protocol.sha(protocol.ROOT / transport.PLAN),
                             "original_worker_freeze": A2_FREEZE, "policy_changed": False},
            "cheap_total_cap_usd": "1.25", "cheap_remaining_usd": str(remaining),
            "gpu_total_cap_usd": "25", "study_total_cap_usd": "75",
            "run_root": "out/kolibri-swap-20261004/bootstrap-a3", "automatic_replacement": False,
            "science_changed": False, "research_outcomes_observed": False,
            "scope": "A3 cheap/main/collection root; main requires passed closed A3 cheap; frozen judge policy rebound explicitly",
            "known_technical_outcomes": [*prior["known_technical_outcomes"],
                "A2: synthetic forward completed; post-load assertion rejected official Marlin FP8 packing"],
            "worker_delta": "A2 tools unchanged; A3 named diagnostics and exact checkpoint/operator storage reconstruction",
            "tiny_checkpoint_forward_and_kernels_changed": False,
            "main_model_fp8_requirement_changed": False}


def verify(freeze=None):
    path = protocol.ROOT / AMENDMENT
    value = prod.load(path)
    prod.check(value == build(), "A3 source/predecessor amendment binding differs")
    if freeze is not None:
        a2.verify(freeze)
        for name, digest in {**value["source_hashes"], AMENDMENT: protocol.sha(path)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(hashlib.sha256(body).hexdigest() == digest, "A3 source absent from pushed freeze")
        subprocess.run(["git", "merge-base", "--is-ancestor", JUDGE_FREEZE, freeze],
                       cwd=protocol.ROOT, check=True, timeout=10)
        for name, digest in {**prod.load(protocol.ROOT / transport.PLAN)["source_hashes"],
                             transport.PLAN: value["judge_policy"]["sha256"]}.items():
            for commit in (JUDGE_FREEZE, freeze):
                body = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=protocol.ROOT)
                prod.check(hashlib.sha256(body).hexdigest() == digest, "Frozen judge policy bytes differ")
    return value


def worker_script(kind, freeze, relative, seconds):
    prod.check(kind in old.HARDWARE, "Unknown pod role")
    source = a2.worker_script(kind, freeze, relative, seconds)
    if kind == "main":
        return source
    marker = "-m experiments.kolibri_swap.gpu_smoke"
    prod.check(source.count(marker) == 1, "Frozen smoke entrypoint differs")
    return source.replace(marker, "-m experiments.kolibri_bootstrap_a3.smoke")


def qualified_cheap(base, freeze, plan_hash, amendment):
    """Original hash/ownership/deletion checks plus the exact A3 qualification shape."""
    receipt = prod.closed_receipt(base, "cheap", plan_hash, freeze, smoke=True)
    _, events = prod.controller_events(base, "cheap", plan_hash, freeze)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    smoke = prod.load(Path(saved["data"]["directory"]) / "gpu-smoke.json")
    config = events["controller:config"]["data"]
    prod.check(config.get("amendment_sha256") == protocol.sha(protocol.ROOT / AMENDMENT)
               and config.get("prior_cheap_usd") == amendment["predecessor"]["cost_usd"]
               and config.get("a2_freeze") == A2_FREEZE,
               "Cheap controller lacks A3 binding/carry")
    prod.check(smoke.get("amendment") == "kolibri-bootstrap-a3-v1"
               and smoke.get("parser", {}).get("official_passed") == 70
               and smoke["parser"].get("skipped") == 0, "A3 parser/qualification receipt absent")
    gpu = smoke["gpu"]
    workers = gpu.get("workers", [])
    prod.check(len(workers) == 1 and workers[0].get("status") == "passed"
               and workers[0].get("linear_errors") == []
               and workers[0].get("layers") == workers[0].get("custom_routing_layers") == 6
               and workers[0].get("fp8_weights") is True
               and workers[0].get("checkpoint_fp32_block_scales") is True
               and workers[0].get("modules") and workers[0].get("operator_sources"),
               "Named A3 worker qualification did not pass")
    expected = {f"model.layers.{i}.{name}" for i in range(6) for name in
                ("self_attn.qkv_proj", "self_attn.o_proj", "mlp.shared_experts.gate_up_proj", "mlp.shared_experts.down_proj")}
    linears = workers[0].get("linears", [])
    prod.check(len(linears) == 24 and {row.get("name") for row in linears} == expected
               and all(row.get("exact_checkpoint_reconstruction") is True and row.get("storage") in
                       {"official_marlin_e4m3fn_packed_int32", "native_e4m3fn_fp32_block_scales"} for row in linears),
               "A3 FP8 reconstruction inventory incomplete")
    from experiments.kolibri_swap import gpu_smoke
    prod.check(gpu.get("llm_options") == gpu_smoke.LLM_OPTIONS
               and gpu.get("checkpoint", {}).get("fp8_matrices") == 186
               and len(gpu.get("forward", [])) == 2
               and all(row.get("tokens") == gpu_smoke.MAX_TOKENS and row.get("prompt_tokens") == len(prompt)
                       for row, prompt in zip(gpu["forward"], gpu_smoke.PROMPTS)),
               "A3 synthetic forward/checkpoint receipt incomplete")
    prod.check(Decimal(receipt["cost_usd"]) + Decimal(amendment["predecessor"]["cost_usd"])
               <= old.CAPS["cheap"], "Cumulative cheap allowance exceeded")
    return receipt


class Controller(a2.Controller):
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
            "amendment_sha256": self.amendment_hash, "a2_freeze": A2_FREEZE,
            "prior_cheap_usd": self.amendment["predecessor"]["cost_usd"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()

    def _new_pod(self, pod, intent):
        return pod.get("id") != FAILED_POD and super()._new_pod(pod, intent)

    def cheap_pass(self):
        return qualified_cheap(self.out, self.freeze, self.plan_hash, self.amendment)

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
        self.cheap = qualified_cheap(self.root, self.freeze, self.plan_hash, amendment)
        _, events = prod.controller_events(self.root, "main", self.plan_hash, self.freeze)
        config = events["controller:config"]["data"]
        prod.check(config.get("amendment_sha256") == protocol.sha(protocol.ROOT / AMENDMENT)
                   and config.get("prior_cheap_usd") == amendment["predecessor"]["cost_usd"]
                   and config.get("a2_freeze") == A2_FREEZE, "Main controller lacks A3 binding/carry")

    def state(self, *args, **kwargs):
        result = super().state(*args, **kwargs)
        result["prior_cheap_usd"] = Decimal(self.amendment["predecessor"]["cost_usd"])
        result["gpu_usd"] += result["prior_cheap_usd"]
        prod.check(kwargs.get("permit_stop") or result["gpu_usd"] <= 25, "GPU allowance including all failures exhausted")
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
