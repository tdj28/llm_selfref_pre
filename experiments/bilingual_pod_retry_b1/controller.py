"""One owner-authorized provisioning retry, run from the frozen B1 checkout.

The first HTTP 500 has no pod ID or deletion receipt. Reserve its possible
elapsed charge rather than asserting it cost nothing. This wrapper changes
neither the scientific worker nor the existing local judge ledger.
"""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from experiments.bilingual_llama_b1 import controller as old

SCIENCE_FREEZE = "c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb"
PLAN_HASH = "1f06e45c703b11f6d7c02535529fa69112bcfa640886a230550c689e1b1b3886"
ORIGINAL_INTENT_SHA = "78d564cdc7c772619e2c40807570a2e6690275c285038b7aad9745993d18111e"
ORIGINAL_NAME = "codex-bilingual-llama-b1-20261002-cheap-e08cbdeb733f"
ORIGINAL_UTC = "2026-10-02T18:41:20.202067+00:00"
ORIGINAL_RATE = Decimal("0.84")
AMBIGUOUS_RESERVE_USD = Decimal("8")
APPROVAL_REF = "owner-20261002-runpod-retry"
NAMESPACE = "bilingual-pod-retry-b1"
AMENDMENT_ROOT = Path(__file__).resolve().parents[2]
AMENDMENT_PATHS = (
    "experiments/bilingual_pod_retry_b1/__init__.py",
    "experiments/bilingual_pod_retry_b1/controller.py",
    "tests/test_pod_retry_b1.py",
    "docs/BILINGUAL_POD_RETRY_B1_20261002.md",
)


def amendment_contract():
    return {"schema": NAMESPACE, "science_freeze": SCIENCE_FREEZE,
            "plan_sha256": PLAN_HASH, "original_intent_sha256": ORIGINAL_INTENT_SHA,
            "original_name": ORIGINAL_NAME, "original_utc": ORIGINAL_UTC,
            "ambiguous_original_reserve_usd": str(AMBIGUOUS_RESERVE_USD),
            "original_hourly_bound_usd": str(ORIGINAL_RATE),
            "approval_ref": APPROVAL_REF, "budget": old.BUDGET,
            "scientific_changes": [], "new_fixture_calls": 0,
            "maximum_new_cheap_posts": 1, "judge_ledger_reset": False}


def verify_amendment(freeze, *, network=True):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze or "") or freeze == SCIENCE_FREEZE:
        raise ValueError("Separate full amendment commit required")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=AMENDMENT_ROOT,
                                       env=old.base.local_env(), timeout=30)
    if git("rev-parse", "HEAD").decode().strip() != freeze:
        raise ValueError("Amendment checkout HEAD differs")
    sources = {}
    for name in AMENDMENT_PATHS:
        path = AMENDMENT_ROOT / name
        old._no_symlinks(path)
        raw = path.read_bytes()
        if raw != git("show", freeze + ":" + name):
            raise ValueError("Amendment source changed")
        sources[name] = hashlib.sha256(raw).hexdigest()
    if network:
        old.verify_ci(freeze)
        old.base.verify_public(sources[AMENDMENT_PATHS[1]], AMENDMENT_PATHS[1], freeze)
    return {"amendment_freeze": freeze, "sources": sources, "contract": amendment_contract()}


def original_events(out):
    path = Path(out) / old.NAMESPACE / "cheap/events.jsonl"
    old._no_symlinks(path)
    if not path.is_file():
        raise ValueError("Original creation ledger required; no reset")
    events = {e["id"]: e for e in old.EventLedger(path, PLAN_HASH, SCIENCE_FREEZE, []).read()}
    intent = events.get("create-intent", {})
    data = intent.get("data", {})
    if (intent.get("sha256") != ORIGINAL_INTENT_SHA
            or data.get("payload", {}).get("name") != ORIGINAL_NAME
            or data.get("created_utc") != ORIGINAL_UTC
            or data.get("plan_sha256") != PLAN_HASH
            or data.get("freeze_commit") != SCIENCE_FREEZE
            or old._number(data.get("quote", {}).get("hourly_rate_usd")) + old.base.STORAGE != ORIGINAL_RATE
            or any(k in events for k in ("worker-intent", "worker-started"))):
        raise ValueError("Original unresolved creation identity changed or worker was dispatched")
    return events


def original_closed_cost(out, events):
    closed = events.get("closed", {}).get("data")
    if closed is None:
        return None
    root = Path(out) / old.NAMESPACE / "cheap"
    receipt_path = root / "final-retrieval.json"
    old._no_symlinks(receipt_path)
    receipt = old.base.strict_json(receipt_path.read_bytes())
    saved = receipt["data"]
    cost = old._number(closed.get("compute_upper_bound_usd"))
    if (closed.get("get_status") != 404 or not 0 <= cost <= AMBIGUOUS_RESERVE_USD
            or events.get(receipt.get("id")) != receipt
            or saved.get("pod_id") != closed.get("pod_id")):
        raise ValueError("Original cleanup not hash-verified within reserved cost")
    if saved.get("no_worker_dispatched") is True:
        owned = events.get("created", {}).get("data", {})
        if (saved.get("artifacts") != {} or "directory" in saved
                or not owned.get("id") or owned.get("id") != closed.get("pod_id")
                or any(saved.get("pod", {}).get(k) != owned.get(k) for k in ("id", "name", "createdAt"))
                or owned.get("name") != ORIGINAL_NAME):
            raise ValueError("Invalid no-worker cleanup evidence")
    else:
        directory = Path(saved.get("directory", ""))
        if (not directory.is_relative_to(root / "retrievals")
                or old.artifact_map(directory) != saved["artifacts"]):
            raise ValueError("Original cleanup artifacts changed")
    return cost


class Controller(old.Controller):
    def __init__(self, kind, amendment_freeze, api, *, launch=False,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 fixture_gate=None, run=subprocess.run, clock=old.base.now,
                 sleep=time.sleep, monotonic=time.monotonic):
        if kind not in old.base.HARDWARE:
            raise ValueError("Cheap or main required")
        self.plan_path = (old.ROOT / old.PLAN_RELATIVE).resolve()
        self.relative, self.freeze, self.kind = old.PLAN_RELATIVE, SCIENCE_FREEZE, kind
        self.plan = old.load_plan(self.plan_path, self.freeze)
        self.budget, self.plan_hash = old.checked_budget(self.plan), old.sha(self.plan_path)
        if self.plan_hash != PLAN_HASH:
            raise ValueError("Scientific plan changed")
        self.amendment = verify_amendment(amendment_freeze, network=False)
        self.out = old.OWNED_OUT
        original_events(self.out)
        self.base = self.out / NAMESPACE / kind
        old._no_symlinks(self.base)
        old._require_ignored(self.base / "events.jsonl")
        for directory in (self.base.parent, self.base):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock, self.sleep, self.monotonic = api, run, clock, sleep, monotonic
        self.launch_enabled = launch is True
        self.approved_new_cap_usd, self.approval_ref = approved_new_cap_usd, approval_ref
        self.approval_file = Path(approval_file).absolute() if approval_file else None
        self.fixture_gate_path = fixture_gate
        self._wall0, self._mono0 = old._utc(clock()), old._number(monotonic())
        self._last_mono = self._mono0
        self.ledger = old.EventLedger(self.base / "events.jsonl", self.plan_hash, self.freeze, [])
        self.ledger.path.chmod(0o600)
        self._elapsed0 = max((old._number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                             if "elapsed_seconds" in r["data"]), default=Decimal(0))
        self.hard_seconds = old.CHEAP_SECONDS if kind == "cheap" else old.MAIN_SECONDS
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
            "plan_path": self.relative, "budget": self.budget, "hard_seconds": self.hard_seconds,
            "retrieval_seconds": old.RESERVE_SECONDS, "image": old.base.IMAGE,
            "amendment": self.amendment})

    def _creation_approval(self):
        if self.approval_ref != APPROVAL_REF:
            raise ValueError("Explicit owner retry approval required")
        return {**super()._creation_approval(), "amendment": self.amendment}

    def guard_original(self, horizon_seconds=0):
        events = original_events(self.out)
        for kind in ("cheap", "main"):
            path = self.out / NAMESPACE / kind / "events.jsonl"
            if path.is_file() and any(e["id"] == "original-late-detected" for e in
                    old.EventLedger(path, PLAN_HASH, SCIENCE_FREEZE, []).read()):
                raise ValueError("Original late discovery permanently halted this retry")
        horizon = old._number(horizon_seconds)
        before = old._utc(self.clock())
        last = max([old._utc(ORIGINAL_UTC), self._wall0] + [
            old._utc(e["data"]["utc"]) for e in self.ledger.read()
            if e["id"].startswith("original-observation:")])
        if horizon < 0 or before < last:
            raise ValueError("Invalid original charge horizon")
        matches = [p for p in self.api.inventory() if p.get("name") == ORIGINAL_NAME]
        after = old._utc(self.clock())
        if after < before:
            raise ValueError("Original observation clock moved backward")
        elapsed = old._number((after - old._utc(ORIGINAL_UTC)).total_seconds())
        self.record("original-observation", {"utc": after.isoformat(),
            "exact_name": ORIGINAL_NAME, "matching_ids": [p.get("id") for p in matches],
            "original_intent_sha256": ORIGINAL_INTENT_SHA})
        if matches:
            self.ledger.bind("original-late-detected", {"utc": old._utc(self.clock()).isoformat(),
                "matching_ids": [p.get("id") for p in matches],
                "original_intent_sha256": ORIGINAL_INTENT_SHA})
            raise ValueError("Original pod appeared; close retry and reconcile original ownership")
        closed_cost = original_closed_cost(self.out, events)
        possible_cost = closed_cost if closed_cost is not None else (elapsed + horizon) * ORIGINAL_RATE / 3600
        if possible_cost > AMBIGUOUS_RESERVE_USD:
            raise ValueError("Unresolved original charge exceeds reserved horizon")
        return possible_cost

    def cheap_receipt(self):
        root = self.out / NAMESPACE / "cheap"
        old._no_symlinks(root)
        if not (root / "events.jsonl").is_file():
            raise ValueError("Retry cheap gate required before main")
        events = {e["id"]: e for e in old.EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, []).read()}
        closed = events.get("closed", {}).get("data", {})
        if (events.get("controller:config", {}).get("data", {}).get("amendment") != self.amendment
                or events.get("create-intent", {}).get("data", {}).get("prior_new_usd") != str(AMBIGUOUS_RESERVE_USD)
                or closed.get("within_limits") is not True or closed.get("get_status") != 404):
            raise ValueError("Retry cheap amendment/carry/cleanup mismatch")
        path = root / "final-retrieval.json"
        old._no_symlinks(path)
        receipt = old.base.strict_json(path.read_bytes())
        saved, directory = receipt["data"], Path(receipt["data"]["directory"])
        if (events.get(receipt.get("id")) != receipt or saved.get("pod_id") != closed.get("pod_id")
                or not directory.is_relative_to(root / "retrievals")
                or old.artifact_map(directory) != saved["artifacts"]):
            raise ValueError("Retry cheap evidence not hash-verified")
        if (old.base.strict_json((directory / "DONE-all.json").read_bytes()) !=
                {"pass": True, "scope": "tiny_cuda_exact_path"}
                or old.base.strict_json((directory / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("Retry cheap CUDA tests did not pass")
        suites = list(ET.parse(directory / "tests.xml").iter("testsuite"))
        if (not suites or sum(int(s.get("tests", "0")) for s in suites) == 0
                or any(int(s.get(k, "0")) for s in suites for k in ("failures", "errors", "skipped"))):
            raise ValueError("Cheap CUDA tests must run without failures or skips")
        cost = old._number(closed["compute_upper_bound_usd"])
        if cost < 0 or old._number(closed["cumulative_gpu_upper_bound_usd"]) != AMBIGUOUS_RESERVE_USD + cost:
            raise ValueError("Retry cheap cumulative accounting differs")
        return AMBIGUOUS_RESERVE_USD + cost

    @old.transport.serialized
    def launch(self):
        self._check_judging_halt()
        if self.event("create-intent"):
            raise ValueError("Creation already attempted; reconcile only")
        approval = self._creation_approval()
        if old.load_plan(self.plan_path, self.freeze) != self.plan or old.sha(self.plan_path) != self.plan_hash:
            raise ValueError("Scientific plan changed")
        if verify_amendment(self.amendment["amendment_freeze"]) != self.amendment:
            raise ValueError("Operational amendment changed")
        self.disk_check()
        fixture = old.fixture_gate(self.fixture_gate_path, self.plan, self.plan_hash, self.freeze)
        prior_new = self.cheap_receipt() if self.kind == "main" else AMBIGUOUS_RESERVE_USD
        future_seconds = self.hard_seconds + (old.MAIN_SECONDS if self.kind == "cheap" else 0)
        self.guard_original(future_seconds + old.RESERVE_SECONDS)
        if self.kind == "main":
            token = os.environ.get("HF_TOKEN", "")
            if not token or any(c.isspace() for c in token):
                raise ValueError("HF_TOKEN missing/malformed before rental")
        if not old.base.KEY.expanduser().is_file():
            raise ValueError("Existing private SSH key required")
        key = Path(str(old.base.KEY.expanduser()) + ".pub").read_text().strip()
        name = old.PREFIX + self.kind + "-" + uuid.uuid4().hex[:12]
        payload = old.base.create_payload(self.kind, old.base.PREFIX + self.kind + "-" + name[-12:], key)
        payload["name"] = name
        old.base.verify_public(self.plan_hash, self.relative, self.freeze)
        ci = old.verify_ci(self.freeze)
        blocked = sorted({old.base.BLOCKED} | {p["id"] for p in self.api.inventory()})
        old.PodRegistry(self.ledger, blocked)
        offers = {kind: old.base.quote(self.api, kind) for kind in ("cheap", "main")}
        quoted = offers[self.kind]
        rate = old._number(quoted["hourly_rate_usd"]) + old.base.STORAGE
        full_cost = prior_new + rate * self.hard_seconds / 3600
        if self.kind == "cheap":
            full_cost += (old._number(offers["main"]["hourly_rate_usd"]) + old.base.STORAGE) * old.MAIN_SECONDS / 3600
        if (full_cost > old.GPU_CAP_USD
                or full_cost + old.API_CAP_USD + old.TRANSLATION_QA_STORAGE_USD + old.CONTINGENCY_USD > old.NEW_CAP_USD):
            raise ValueError("Ambiguous reserve plus full GPU lifetimes exceed existing cap")
        self.guard_original(future_seconds + old.RESERVE_SECONDS)
        authority = self.ledger.bind("creation-approval", approval)
        self.ledger.bind("fixture-gate", fixture)
        created = old._utc(self.clock())
        intent = {"payload": payload, "quote": quoted, "blocked": blocked, "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=self.hard_seconds - old.RESERVE_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
                  "prior_new_usd": str(prior_new), "prior_total_usd": "0", "contingency_used_usd": "0",
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                  "approval_sha256": authority["sha256"], "ci": ci, "offers": offers,
                  "amendment": self.amendment}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, old._number(self.monotonic())
        self._last_mono = self._mono0
        self.guard_original(future_seconds + old.RESERVE_SECONDS)
        if not 0 <= (old._utc(self.clock()) - created).total_seconds() <= 60:
            raise ValueError("Stale creation intent")
        try:
            status, pod = self.api.request("POST", "/pods", payload)
            if status != 201 or not self._new_pod(pod, intent):
                raise ValueError("Ambiguous creation")
        except (old.base.ApiError, RuntimeError, ValueError, OSError, KeyError, TypeError):
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
        self.guard_original(old._number(horizon) + old.RESERVE_SECONDS)
        return super().cost_check(pod, horizon)


def reconcile_late_original(api, retry=None):
    """Only the first persisted intent can authorize cleanup of a late pod."""
    events = original_events(old.OWNED_OUT)
    matches = [p for p in api.inventory() if p.get("name") == ORIGINAL_NAME]
    if not matches:
        return {"exact_name": ORIGINAL_NAME, "matches": 0, "deletion_claimed": False}
    if retry is not None and retry.event("original-late-detected") is None:
        retry.ledger.bind("original-late-detected", {"utc": old._utc(retry.clock()).isoformat(),
            "matching_ids": [p.get("id") for p in matches],
            "original_intent_sha256": ORIGINAL_INTENT_SHA})
    if retry is not None and retry.event("created") and not retry.event("closed"):
        retry.close_until_verified()
    if len(matches) != 1:
        raise ValueError("Multiple original-name matches; ownership ambiguous")
    ctrl = old.Controller(old.ROOT / old.PLAN_RELATIVE, SCIENCE_FREEZE, old.OWNED_OUT,
                          "cheap", api, launch=True)
    pod, intent = matches[0], events["create-intent"]["data"]
    gpu = pod.get("gpu", {})
    if (not ctrl._new_pod(pod, intent)
            or any(pod.get(k) != intent["payload"][k] for k in ("cloud", "image", "disk", "mounts", "ports"))
            or gpu.get("id") != old.base.HARDWARE["cheap"][0]
            or gpu.get("count") != 1 or old._number(gpu.get("memory")) < old.base.HARDWARE["cheap"][2]):
        raise ValueError("Late original pod fails original ownership proof")
    # Register the exact fully validated observation. Re-fetching by name via
    # reconcile() could substitute an identity not covered by the checks above.
    if ctrl.event("created") is None:
        ctrl._register(pod)
    elif any(ctrl.owned().get(k) != pod.get(k) for k in ("id", "name", "createdAt")):
        raise ValueError("Late original differs from registered identity")
    return ctrl.close_until_verified()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment-freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("inspect", "create", "monitor", "retrieve", "status",
                                            "approve", "close", "reconcile"), default="inspect")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--fixture-gate")
    parser.add_argument("--barrier", choices=old.BARRIERS)
    parser.add_argument("--approve-plan-sha256")
    args = parser.parse_args(argv)
    if args.action == "inspect":
        print(json.dumps(verify_amendment(args.amendment_freeze, network=False), sort_keys=True))
        return
    if not args.launch:
        parser.error("Live lifecycle actions require --launch")
    api = old.base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True)
    ctrl = Controller(args.kind, args.amendment_freeze, api, launch=True,
                      approved_new_cap_usd=args.approved_new_cap_usd, approval_ref=args.approval_ref,
                      approval_file=args.approval_file, fixture_gate=args.fixture_gate)
    try:
        if args.action == "create":
            ctrl.launch()
            result = ctrl.monitor()
        elif args.action == "approve":
            result = ctrl.approve(args.barrier, args.approve_plan_sha256)
        elif args.action == "close":
            result = ctrl.close_until_verified()
        else:
            result = getattr(ctrl, args.action)()
        print(json.dumps(result, sort_keys=True), flush=True)
    finally:
        # This never starts a worker on the expired original intent.
        reconcile_late_original(api, retry=ctrl)


if __name__ == "__main__":
    main()
