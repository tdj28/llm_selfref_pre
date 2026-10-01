"""Bootstrap-only retry; execute from the unchanged scientific checkout.

The original worker, machine plan and judge ledger remain at SCIENCE_FREEZE.
This separately committed controller carries the failed cheap rental and gives
one new cheap pod a longer work window. It does not change scientific gates.
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

from experiments.instruction_state_qualification import controller as old

SCIENCE_FREEZE = "0acf16548f7dfe0359ce6c19bf952725572697d5"
PLAN_HASH = "d614da0b4398ddc021300a177a2218009a48b74c4fe5952df2852d20f0ef9d0f"
FAILED_POD = "hspaphgeu0ytc0"
FAILED_COST = Decimal("0.1388858536333333333333333333")
FAILED_CLOSURE = "1eb4b900b53663167fd2aa8e241b502ef5245945bd04b00cac2037ec90e928b0"
NAMESPACE = "instruction-qualification-bootstrap-a1"
CHEAP_SECONDS = 1800
A1_ROOT = Path(__file__).resolve().parents[2]
A1_PATHS = (
    "experiments/instruction_qualification_bootstrap_a1/__init__.py",
    "experiments/instruction_qualification_bootstrap_a1/controller.py",
    "tests/test_qualification_bootstrap_a1.py",
    "docs/INSTRUCTION_STATE_BOOTSTRAP_A1_20261001.md",
)


def amendment_contract():
    return {"schema": "instruction-qualification-bootstrap-a1",
            "science_freeze": SCIENCE_FREEZE, "plan_sha256": PLAN_HASH,
            "failed_pod": FAILED_POD, "failed_gpu_usd": str(FAILED_COST),
            "failed_closure_sha256": FAILED_CLOSURE,
            "cheap_seconds": CHEAP_SECONDS, "main_seconds": old.MAIN_SECONDS,
            "budget": old.BUDGET, "namespace": NAMESPACE,
            "scientific_changes": [], "judge_ledger_reset": False}


def verify_amendment(freeze, *, network=True):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze or "") or freeze == SCIENCE_FREEZE:
        raise ValueError("Separate full amendment commit required")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=A1_ROOT,
                                       env=old.base.local_env(), timeout=30)
    if git("rev-parse", "HEAD").decode().strip() != freeze:
        raise ValueError("Amendment checkout HEAD differs")
    sources = {}
    for name in A1_PATHS:
        path = A1_ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing amendment source")
        raw = path.read_bytes()
        if raw != git("show", freeze + ":" + name):
            raise ValueError("Amendment source changed")
        sources[name] = hashlib.sha256(raw).hexdigest()
    if network:
        old.verify_ci(freeze)
        old.base.verify_public(sources[A1_PATHS[1]], A1_PATHS[1], freeze)
    return {"amendment_freeze": freeze, "sources": sources,
            "contract": amendment_contract()}


def failed_receipt(out):
    root = Path(out) / old.NAMESPACE / "cheap"
    ledger = old.EventLedger(root / "events.jsonl", PLAN_HASH, SCIENCE_FREEZE, [])
    events = {r["id"]: r for r in ledger.read()}
    closed = events.get("closed", {})
    value = closed.get("data", {})
    if (closed.get("sha256") != FAILED_CLOSURE or value.get("pod_id") != FAILED_POD
            or value.get("get_status") != 404 or value.get("within_limits") is not True
            or old._number(value.get("compute_upper_bound_usd")) != FAILED_COST):
        raise ValueError("Original failed rental/deletion/cost receipt changed")
    receipt = old.base.strict_json((root / "final-retrieval.json").read_bytes())
    directory = Path(receipt["data"]["directory"])
    if (events.get(receipt.get("id")) != receipt
            or not directory.is_relative_to(root / "retrievals")
            or old.artifact_map(directory) != receipt["data"]["artifacts"]):
        raise ValueError("Original failed evidence not hash-verified")
    return FAILED_COST


class Controller(old.Controller):
    def __init__(self, kind, amendment_freeze, api, *, launch=False,
                 approved_new_cap_usd=None, approval_ref=None, approval_file=None,
                 clock=old.base.now, sleep=time.sleep, monotonic=time.monotonic):
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
        self.failed_cost = failed_receipt(self.out)
        self.base = self.out / NAMESPACE / kind
        old._no_symlinks(self.base)
        old._require_ignored(self.base / "events.jsonl")
        for directory in (self.base.parent, self.base):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        self.api, self.run, self.clock = api, subprocess.run, clock
        self.sleep, self.monotonic, self.launch_enabled = sleep, monotonic, launch is True
        self.approved_new_cap_usd, self.approval_ref = approved_new_cap_usd, approval_ref
        self.approval_file = Path(approval_file).absolute() if approval_file else None
        self._wall0, self._mono0 = old._utc(clock()), old._number(monotonic())
        self._last_mono = self._mono0
        self.ledger = old.EventLedger(self.base / "events.jsonl", self.plan_hash, self.freeze, [])
        self.ledger.path.chmod(0o600)
        self._elapsed0 = max((old._number(r["data"]["elapsed_seconds"]) for r in self.ledger.read()
                             if "elapsed_seconds" in r["data"]), default=Decimal(0))
        self.hard_seconds = CHEAP_SECONDS if kind == "cheap" else old.MAIN_SECONDS
        self.ledger.bind("controller:config", {"kind": kind, "namespace": NAMESPACE,
            "plan_path": self.relative, "budget": self.budget,
            "hard_seconds": self.hard_seconds, "retrieval_seconds": old.RESERVE_SECONDS,
            "image": old.base.IMAGE, "amendment": self.amendment})

    def cheap_receipt(self):
        root = self.out / NAMESPACE / "cheap"
        old._no_symlinks(root)
        if not (root / "events.jsonl").is_file():
            raise ValueError("A1 cheap gate required")
        ledger = old.EventLedger(root / "events.jsonl", self.plan_hash, self.freeze, [])
        events = {r["id"]: r for r in ledger.read()}
        config = events.get("controller:config", {}).get("data", {})
        closed = events.get("closed", {}).get("data", {})
        if (config.get("amendment") != self.amendment or closed.get("get_status") != 404
                or closed.get("within_limits") is not True):
            raise ValueError("A1 cheap identity/cleanup not verified")
        receipt = old.base.strict_json((root / "final-retrieval.json").read_bytes())
        saved, directory = receipt["data"], Path(receipt["data"]["directory"])
        if (events.get(receipt.get("id")) != receipt or saved.get("pod_id") != closed.get("pod_id")
                or not directory.is_relative_to(root / "retrievals")
                or old.artifact_map(directory) != saved["artifacts"]):
            raise ValueError("A1 cheap artifact binding mismatch")
        if (old.base.strict_json((directory / "DONE-all.json").read_bytes()) !=
                {"pass": True, "scope": "tiny_cuda_exact_path"}
                or old.base.strict_json((directory / "controller-exit.json").read_bytes()) != {"exit_code": 0}):
            raise ValueError("A1 cheap tests did not finish successfully")
        suites = list(ET.parse(directory / "tests.xml").iter("testsuite"))
        if (not suites or sum(int(s.get("tests", "0")) for s in suites) != 176
                or any(int(s.get(k, "0")) for s in suites for k in ("failures", "errors", "skipped"))):
            raise ValueError("All 176 frozen cheap tests must pass without skips")
        return self.failed_cost + old._number(closed["compute_upper_bound_usd"])

    @old.transport.serialized
    def launch(self):
        if self.event("create-intent"):
            raise ValueError("Creation already attempted; reconcile only")
        approval = self._creation_approval()
        if old.load_plan(self.plan_path, self.freeze) != self.plan:
            raise ValueError("Science changed before dispatch")
        if verify_amendment(self.amendment["amendment_freeze"]) != self.amendment:
            raise ValueError("Operational amendment changed")
        if failed_receipt(self.out) != self.failed_cost:
            raise ValueError("Failed cost changed")
        self.disk_check()
        prior_new = self.cheap_receipt() if self.kind == "main" else self.failed_cost
        if self.kind == "main":
            token = os.environ.get("HF_TOKEN", "")
            if not token or any(c.isspace() for c in token):
                raise ValueError("HF_TOKEN missing/malformed")
        if not old.base.KEY.expanduser().is_file():
            raise ValueError("Existing SSH key required")
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
        created = old._utc(self.clock())
        rate = old._number(quoted["hourly_rate_usd"]) + old.base.STORAGE
        full_cost = prior_new + rate * self.hard_seconds / 3600
        if self.kind == "cheap":
            full_cost += (old._number(offers["main"]["hourly_rate_usd"]) + old.base.STORAGE) * old.MAIN_SECONDS / 3600
        if (full_cost > old.GPU_CAP_USD
                or full_cost + old.API_CAP_USD + old.EXTRA_RESERVE_USD > old.NEW_CAP_USD
                or old.PRIOR_USD + old.NEW_CAP_USD > old.TOTAL_USD):
            raise ValueError("Failure plus full future lifetimes do not fit original cap")
        authority = self.ledger.bind("creation-approval", {**approval, "amendment": self.amendment})
        intent = {"payload": payload, "quote": quoted, "blocked": blocked,
                  "created_utc": created.isoformat(),
                  "deadline_utc": (created + timedelta(seconds=self.hard_seconds - old.RESERVE_SECONDS)).isoformat(),
                  "hard_deadline_utc": (created + timedelta(seconds=self.hard_seconds)).isoformat(),
                  "prior_new_usd": str(prior_new), "prior_total_usd": str(old.PRIOR_USD),
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                  "approval_sha256": authority["sha256"], "ci": ci, "offers": offers,
                  "amendment": self.amendment}
        self.ledger.transact("create-intent", lambda _: intent)
        self._wall0, self._mono0 = created, old._number(self.monotonic())
        self._last_mono = self._mono0
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amendment-freeze", required=True)
    parser.add_argument("--kind", choices=("cheap", "main"), required=True)
    parser.add_argument("--action", choices=("inspect", "create", "monitor", "retrieve", "status",
                        "approve", "decision", "close", "reconcile"), default="inspect")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approved-new-cap-usd")
    parser.add_argument("--approval-ref")
    parser.add_argument("--approval-file")
    parser.add_argument("--barrier", choices=tuple(old.BARRIER_ROWS))
    parser.add_argument("--approve-plan-sha256")
    parser.add_argument("--decision-file")
    parser.add_argument("--judge-root")
    args = parser.parse_args(argv)
    if args.action == "inspect":
        print(json.dumps(verify_amendment(args.amendment_freeze, network=False), sort_keys=True))
        return
    if not args.launch:
        parser.error("All live lifecycle operations require --launch")
    from dotenv import load_dotenv
    load_dotenv(old.ROOT / ".env")
    c = Controller(args.kind, args.amendment_freeze,
                   old.base.RunPodV2(os.environ.get("RUNPOD_API_KEY"), writable=True), launch=True,
                   approved_new_cap_usd=args.approved_new_cap_usd, approval_ref=args.approval_ref,
                   approval_file=args.approval_file)
    if args.action == "create":
        c.launch()
        result = c.monitor()
    elif args.action == "approve":
        result = c.approve(args.barrier, args.approve_plan_sha256)
    elif args.action == "decision":
        result = c.decision(args.barrier, args.decision_file, judge_root=args.judge_root)
    elif args.action == "close":
        result = c.close_until_verified()
    else:
        result = getattr(c, args.action)()
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
