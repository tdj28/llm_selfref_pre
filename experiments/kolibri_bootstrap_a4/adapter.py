"""A4 local installation and bounded read recovery; scientific bytes unchanged."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext, ROUND_CEILING
import hashlib
import json
import shlex
import shutil
import urllib.request
import uuid
from datetime import timedelta
import os
from pathlib import Path
import signal
import subprocess
import time

from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments.kolibri_bootstrap_a3 import adapter as a3
from experiments import kolibri_judge_transport as transport
from experiments.kolibri_swap import bootstrap, controller as old, production as prod, protocol
from experiments.openrouter_swap.ledger import _no_symlinks
from experiments.sae_assay_diagnostic.budget import EventLedger, _utc

AMENDMENT = "data/kolibri_bootstrap_a4/plan_v1_20261005/AMENDMENT.json"
A3_FREEZE = "bbfa8d1c02cb7d675f464a05cd0d817dcc56b188"
CAPS = {"cheap": Decimal("2"), "main": Decimal("23")}
LOCAL_VENV = "/tmp/kolibri-venv"
LOCAL_PIP_CACHE = "/tmp/kolibri-pip-cache"
MIN_LOCAL_FREE_BYTES = 35 * 1024**3
A2_FREEZE = "9333faaf8d38a579cc9815d7b068d6c90ade4abf"
JUDGE_FREEZE = "444a1a181f1056e24d18ebe89f93a941810dd2e4"
FAILED_POD = "5690kc571cn40g"
CLOSED_SHA = "518d09b9cebcd579068dba84920448f70d35f84c3e38e27dfa69608c551965b5"
RETRIEVAL_SHA = "707a299ff89ce0d56bf875f7d3012db8f424eeae70eb49692e786e80d26cb60e"
WORKER_SHA = "175be7ac9cc1f22ff96c49f042ea1fd81caf8a9a4bf10d66df0091da5822865e"


def root():
    return old.canonical_root() / "bootstrap-a4"


def predecessor(prior):
    base = a3.root()
    receipt = prod.closed_receipt(base, "cheap", a1.ORIGINAL_PLAN_SHA, A3_FREEZE)
    _, events = prod.controller_events(base, "cheap", a1.ORIGINAL_PLAN_SHA, A3_FREEZE)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    directory = Path(saved["data"]["directory"])
    log = (directory / "worker.log").read_bytes()
    prod.check(events["created"]["data"]["id"] == FAILED_POD
               and receipt["closed_sha256"] == CLOSED_SHA and receipt["retrieval_sha256"] == RETRIEVAL_SHA
               and protocol.sha(directory / "worker.log") == WORKER_SHA
               and not (directory / "gpu-smoke.json").exists()
               and prod.load(directory / "exit.json") == {"exit_code": 143}
               and any(row["data"].get("error_type") == "TimeoutError" for key, row in events.items()
                       if key.startswith("monitor-failure:"))
               and b"Installing collected packages:" in log and b"Successfully installed " not in log,
               "A3 is not the preserved pre-qualification installation/GET-timeout failure")
    latest = {"freeze": A3_FREEZE, "plan_sha256": a1.ORIGINAL_PLAN_SHA, "pod_id": FAILED_POD, **receipt,
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
             protocol.ROOT / "tests/test_kolibri_bootstrap_a4.py"]
    return {p.relative_to(protocol.ROOT).as_posix(): protocol.sha(p) for p in sorted(paths)}


def build():
    prior = a3.verify()
    policy = transport.verify(protocol.ROOT / transport.PLAN)
    prod.check(policy["worker_freeze"] == A2_FREEZE, "Original judge policy worker binding differs")
    carry = predecessor(prior)
    remaining = CAPS["cheap"] - Decimal(carry["cost_usd"])
    prod.check(remaining > 0, "Cumulative cheap allowance exhausted")
    return {"schema": "kolibri-bootstrap-a4-v1", "scientific_plan_sha256": a1.ORIGINAL_PLAN_SHA,
            "original_freeze": a1.ORIGINAL_FREEZE, "a3_freeze": A3_FREEZE,
            "a3_amendment_sha256": protocol.sha(protocol.ROOT / a3.AMENDMENT),
            "predecessor": carry, "source_hashes": sources(),
            "dependency_source_hashes": {**prior["dependency_source_hashes"], **prior["source_hashes"],
                                         **policy["source_hashes"]},
            "judge_policy": {"freeze": JUDGE_FREEZE, "path": transport.PLAN,
                             "sha256": protocol.sha(protocol.ROOT / transport.PLAN),
                             "original_worker_freeze": A2_FREEZE, "policy_changed": False},
            "cheap_total_cap_usd": "2", "cheap_remaining_usd": str(remaining), "main_cap_usd": "23",
            "gpu_total_cap_usd": "25", "study_total_cap_usd": "75",
            "run_root": "out/kolibri-swap-20261004/bootstrap-a4", "automatic_replacement": False,
            "science_changed": False, "research_outcomes_observed": False,
            "scope": "A4 owned cheap/main and collection; A3 CUDA computation and original judge policy unchanged",
            "known_technical_outcomes": [*prior["known_technical_outcomes"],
                "A3: installation incomplete; provider GET timeout triggered cleanup before CUDA qualification"],
            "worker_delta": "Venv and pip cache on container-local /tmp; mount/free-space preflight before installation",
            "local_free_bytes_required": MIN_LOCAL_FREE_BYTES,
            "provider_get_attempts": 3, "provider_get_backoff_seconds": [2, 5],
            "provider_mutation_retries": 0, "cleanup_get_inner_retries": 0,
            "tiny_checkpoint_forward_and_kernels_changed": False,
            "main_model_fp8_requirement_changed": False}


def verify(freeze=None):
    path = protocol.ROOT / AMENDMENT
    value = prod.load(path)
    prod.check(value == build(), "A4 source/predecessor amendment binding differs")
    if freeze is not None:
        a3.verify(freeze)
        subprocess.run(["git", "merge-base", "--is-ancestor", A3_FREEZE, freeze],
                       cwd=protocol.ROOT, check=True, timeout=10)
        for name, digest in {**value["source_hashes"], AMENDMENT: protocol.sha(path)}.items():
            body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            prod.check(hashlib.sha256(body).hexdigest() == digest, "A4 source absent from pushed freeze")
        subprocess.run(["git", "merge-base", "--is-ancestor", JUDGE_FREEZE, freeze],
                       cwd=protocol.ROOT, check=True, timeout=10)
        for name, digest in {**prod.load(protocol.ROOT / transport.PLAN)["source_hashes"],
                             transport.PLAN: value["judge_policy"]["sha256"]}.items():
            for commit in (JUDGE_FREEZE, freeze):
                body = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=protocol.ROOT)
                prod.check(hashlib.sha256(body).hexdigest() == digest, "Frozen judge policy bytes differ")
    return value


def storage_preflight():
    return """import json,os,pathlib,shutil
target=pathlib.Path('/tmp')
workspace=pathlib.Path('/workspace')
mounts=[]
for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines():
 fields=line.split(); separator=fields.index('-')
 mounts.append((pathlib.Path(fields[4]),fields[separator+1]))
matching=[(path,kind) for path,kind in mounts if path==target or path in target.parents]
mount,kind=max(matching,key=lambda row:len(row[0].parts))
free=shutil.disk_usage(target).free
record={'schema':'kolibri-a4-local-storage-v1','venv':'VENVDIR','pip_cache':'CACHEDIR',
 'filesystem':kind,'free_bytes':free,'minimum_free_bytes':MINFREE,
 'separate_from_workspace':target.stat().st_dev!=workspace.stat().st_dev}
print(json.dumps(record,sort_keys=True),flush=True)
assert kind in {'overlay','ext4','xfs','btrfs'}, 'Installation filesystem is not local disk'
assert record['separate_from_workspace'], 'Installation still shares workspace filesystem'
assert free>=MINFREE, 'Insufficient local space for locked wheels and installation'
assert not pathlib.Path('VENVDIR').exists(), 'Venv already exists on new owned pod'
""".replace("VENVDIR", LOCAL_VENV).replace("CACHEDIR", LOCAL_PIP_CACHE).replace("MINFREE", str(MIN_LOCAL_FREE_BYTES))


def storage_setup():
    return ("export PIP_CACHE_DIR=" + shlex.quote(LOCAL_PIP_CACHE) + " TMPDIR=/tmp\n"
            + shlex.join(["python3", "-c", storage_preflight()]) + "\n")


def worker_script(kind, freeze, relative, seconds):
    prod.check(kind in old.HARDWARE, "Unknown pod role")
    source = a3.worker_script(kind, freeze, relative, seconds)
    source = source.replace(bootstrap.REMOTE + "/venv", LOCAL_VENV)
    marker = "python3 -m venv " + LOCAL_VENV + "\n"
    prod.check(source.count(marker) == 1, "Frozen venv insertion point differs")
    return source.replace(marker, storage_setup() + marker)


class ReadRetryAPI:
    """Retry only transient GETs; never retry POST/DELETE or soften identities."""
    def __init__(self, api, guard, record, sleep):
        self.api, self.guard, self.record, self.sleep = api, guard, record, sleep
        self.writable, self.cleanup = api.writable, False

    def inventory(self):
        return old.base.RunPodV2.inventory(self)

    def request(self, method, path, body=None):
        if method != "GET" or self.cleanup:
            return self.api.request(method, path, body)
        for attempt, delay in enumerate((0, 2, 5), 1):
            self.guard(30 + delay)
            if delay:
                self.sleep(delay)
                self.guard(30)
            try:
                return self.api.request(method, path, body)
            except (TimeoutError, ConnectionError, RuntimeError, old.base.ApiError) as exc:
                eligible = (isinstance(exc, (TimeoutError, ConnectionError))
                    or isinstance(exc, old.base.ApiError) and exc.status in {408, 429, 500, 502, 503, 504}
                    or type(exc) is RuntimeError and str(exc) == "RunPod transport outcome unknown; do not retry mutation")
                if not eligible or attempt == 3:
                    raise
                self.record("provider-read-retry", {"attempt": attempt, "path": path, "error_type": type(exc).__name__})


def qualified_cheap(base, freeze, plan_hash, amendment):
    """Original hash/ownership/deletion checks plus the exact A3 qualification shape."""
    receipt = prod.closed_receipt(base, "cheap", plan_hash, freeze, smoke=True)
    _, events = prod.controller_events(base, "cheap", plan_hash, freeze)
    saved = prod.load(base / "controller/cheap/final-retrieval.json")
    smoke = prod.load(Path(saved["data"]["directory"]) / "gpu-smoke.json")
    config = events["controller:config"]["data"]
    prod.check(config.get("amendment_sha256") == protocol.sha(protocol.ROOT / AMENDMENT)
               and config.get("prior_cheap_usd") == amendment["predecessor"]["cost_usd"]
               and config.get("a3_freeze") == A3_FREEZE,
               "Cheap controller lacks A4 binding/carry")
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
               <= CAPS["cheap"], "Cumulative cheap allowance exceeded")
    return receipt


class Controller(a3.Controller):
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
            "image": bootstrap.IMAGE, "cap_usd": str(CAPS[kind]),
            "amendment_sha256": self.amendment_hash, "a3_freeze": A3_FREEZE,
            "prior_cheap_usd": self.amendment["predecessor"]["cost_usd"]})
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        if self.event("create-intent"):
            self._elapsed0 = self.elapsed()

        self.api = ReadRetryAPI(api, self.read_guard, self.record, self.sleep)

    def attempt_cap(self):
        return CAPS[self.kind] - (Decimal(self.amendment["predecessor"]["cost_usd"]) if self.kind == "cheap" else Decimal(0))

    def read_guard(self, horizon):
        intent = self.event("create-intent")
        if intent is None:
            return
        data = intent["data"]
        rate = Decimal(data["quote"]["hourly_rate_usd"]) + old.STORAGE
        prod.check(self.elapsed() + Decimal(horizon + old.CLEANUP_RESERVE_SECONDS)
                   <= self.attempt_cap() / rate * 3600
                   and self.clock() + timedelta(seconds=horizon) < _utc(data["deadline_utc"]),
                   "Read retry cannot fit frozen deadline and cleanup reserve")

    def cost_check(self, pod, horizon=60):
        spent = old.Controller.cost_check(self, pod, horizon)
        rate = Decimal(str(pod["cost"])) + old.STORAGE
        prod.check(spent + Decimal(horizon + old.CLEANUP_RESERVE_SECONDS) * rate / 3600 <= self.attempt_cap(),
                   "A4 cumulative startup/main subcap reached")
        return spent

    def terminate(self):
        previous = self.api.cleanup
        self.api.cleanup = True
        try:
            return super().terminate()
        finally:
            self.api.cleanup = previous

    def launch(self):
        prod.check(self.api.writable and not self.event("create-intent"), "Launch not authorized or already attempted")
        if self.kind == "main":
            self.cheap_pass()
        prod.check(shutil.disk_usage(self.base).free >= 4 * 1024**3, "Insufficient local retrieval space")
        url = "https://raw.githubusercontent.com/tdj28/llm_selfref_pre/" + self.freeze + "/" + self.relative
        with urllib.request.urlopen(url, timeout=30) as response:
            prod.check(hashlib.sha256(response.read()).hexdigest() == self.plan_hash, "Public prospective plan differs")
        blocked = sorted(p["id"] for p in self.api.inventory())
        quoted = old.quote(self.api, self.kind)
        prod.check(old.base.KEY.expanduser().is_file(), "Existing SSH private key is missing")
        key = Path(str(old.base.KEY.expanduser()) + ".pub").read_text().strip()
        request = old.payload(self.kind, old.PREFIX + self.kind + "-" + uuid.uuid4().hex[:12], key)
        rate = Decimal(quoted["hourly_rate_usd"]) + old.STORAGE
        seconds = min(old.SECONDS[self.kind], int(self.attempt_cap() / rate * 3600))
        prod.check(seconds > old.CLEANUP_RESERVE_SECONDS + 60, "No qualified work horizon remains")
        now = self.clock()
        intent = {"payload": request, "quote": quoted, "created_utc": now.isoformat(),
                  "deadline_utc": (now + timedelta(seconds=seconds - old.CLEANUP_RESERVE_SECONDS)).isoformat(),
                  "cleanup_deadline_utc": (now + timedelta(seconds=seconds)).isoformat(),
                  "blocked": blocked, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                  "cap_usd": str(self.attempt_cap())}
        self.ledger.bind("create-intent", intent)
        self._mono0, self._elapsed0 = time.monotonic(), Decimal(0)
        try:
            try:
                status, pod = self.api.request("POST", "/pods", request)
                prod.check(status == 201 and self._new_pod(pod, intent), "Ambiguous creation")
            except (old.base.ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
                pod = self.reconcile_create()
            self._register(pod)
            print(json.dumps({"created_owned_pod": pod["id"], "kind": self.kind,
                              "deadline_utc": intent["deadline_utc"]}), flush=True)
            self.start_worker()
        except BaseException as exc:
            self._cleanup_after_error("startup-failure", exc)
            raise
        return self.owned()

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
                   and config.get("a3_freeze") == A3_FREEZE, "Main controller lacks A4 binding/carry")

    def state(self, *args, **kwargs):
        result = super().state(*args, **kwargs)
        result["prior_cheap_usd"] = Decimal(self.amendment["predecessor"]["cost_usd"])
        result["gpu_usd"] += result["prior_cheap_usd"]
        prod.check(kwargs.get("permit_stop") or result["gpu_usd"] <= 25 and result["main_usd"] <= CAPS["main"],
                   "GPU/main allowance including all failures exhausted")
        return result

    def admission(self, runner):
        result = super().admission(runner)
        state = self.state(running=True)
        duration = Decimal(result["main_seconds_with_margin"])
        rate = Decimal(self.plan["budget"]["gpu_hourly_usd"]) + old.STORAGE
        prod.check(state["main_usd"] + duration * rate / 3600 <= CAPS["main"],
                   "Whole main cannot fit reduced A4 main allowance")
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
