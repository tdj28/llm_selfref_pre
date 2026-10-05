"""Preserve the failed literal-OK gate and reuse its complete technical data."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

from experiments.openrouter_swap import analysis, protocol
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.openrouter_swap.runner import Runner, write_once
from experiments.openrouter_swap_a1 import amendment as a1
from experiments.openrouter_swap_a2 import amendment as a2

PLAN = "data/openrouter_swap/plan_a3_20261004/PLAN.json"
ACTIVE_MODELS = a2.ACTIVE_MODELS
PRIOR_COST = Decimal("0.62048546")
PRIORS = [*deepcopy(a2.PRIORS), {
    "label": "a2", "path": "a2", "freeze": "bae7b50d6e2eb2213ea7a4518904ef268c600042",
    "plan_path": a2.PLAN,
    "plan_sha256": "7205ff349219b71bfbc8f83656e547acecd58767e60d07024a061793eb87a56e",
    "journal_sha256": "bd5dafe93b1d03822daf24f43f2b0d56e07caa5499a6e9462877fdb1daf61640",
    "cost_bound_usd": "0.357945", "calls": 27, "target_calls": 0, "unresolved": 0,
}]


def canonical_run_root():
    return a2.original_root() / "a3"


def adjudicate_gate(gate):
    routes = gate["routes"]
    route_pass = (len(routes) == 3 and
                  {r["model"] for r in routes} == {protocol.MODELS[m]["id"] for m in ACTIVE_MODELS} and
                  all(r["complete"] and not r["missing"] and
                      r["response"].strip() in {"OK", "OK."} for r in routes))
    return {"pass": gate["judges"]["pass"] and route_pass,
            "original_gate": deepcopy(gate), "reused_from": "complete A2 raw fixture inventory",
            "routing_rule": "Complete nonmissing acknowledgment, exactly OK or OK. after outer whitespace removal."}


def build():
    result = deepcopy(a2.verify(protocol.ROOT / a2.PLAN))
    if protocol.sha(protocol.ROOT / a2.PLAN) != PRIORS[2]["plan_sha256"]:
        raise Halted("A2 plan changed")
    result.update(schema="openrouter-swap-a3", prior_attempts=deepcopy(PRIORS),
                  prior_cost_usd=str(PRIOR_COST), cap_usd=str(Decimal("250") - PRIOR_COST),
                  screen_cap_usd=str(Decimal("40") - PRIOR_COST))
    result["amendment"] = {
        "reason": "Gemini's valid routing response was OK. rather than literal OK.",
        "observed": "All 24 A2 judge fixtures pass; 27 settled technical calls; zero scientific outcomes.",
        "rule": "Accept OK or OK. only in routing acknowledgments; preserve the failed original gate.",
        "reuse": "All A2 fixtures are reused without resampling; new targets have their own ledger.",
        "scientific_changes": [],
    }
    names = [p.relative_to(protocol.ROOT).as_posix()
             for p in (protocol.ROOT / "experiments/openrouter_swap_a3").glob("*")
             if p.suffix in {".py", ".md"}]
    names += ["tests/test_openrouter_punctuation.py"]
    result["source_hashes"].update({name: protocol.sha(protocol.ROOT / name) for name in sorted(names)})
    return result


def verify(path, freeze=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    if protocol.canonical(plan) != protocol.canonical(build()):
        raise Halted("A3 plan differs from bound sources")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise Halted("Full A3 freeze required")
        for name, expected in plan["source_hashes"].items():
            raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise Halted("A3 source differs from public freeze")
        if subprocess.check_output(["git", "show", f"{freeze}:{PLAN}"], cwd=protocol.ROOT) != path.read_bytes():
            raise Halted("A3 plan differs from public freeze")
        remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/openrouter-swap-panel"],
                                         cwd=protocol.ROOT, text=True).split()
        if not remote or subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote[0]],
                                        cwd=protocol.ROOT).returncode:
            raise Halted("A3 freeze is not on public branch")
    return plan


class A3Runner(a2.IndependentRunner):
    def __init__(self, *args, fixture_gate, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixture_gate = deepcopy(fixture_gate)

    def run_fixtures(self):
        self.require_resolved()
        return deepcopy(self.fixture_gate)

    def require_fixtures(self):
        gate = self.run_fixtures()
        if not gate["pass"]:
            raise Halted("Reconstructed A2 fixture gate does not satisfy A3")
        return gate


def snapshot(root, runner):
    report = runner.audit()
    report.update(prior_cost_bound_usd=str(PRIOR_COST),
                  cumulative_cost_bound_usd=str(PRIOR_COST + runner.ledger.spent()),
                  deferred_models=runner.plan["deferred_models"])
    destination = root / "snapshots" / f"{len(runner.ledger.rows()):06d}"
    write_once(destination / "audit.json", report)
    for phase in ("screen", "main"):
        path = root / "main_admission.json"
        admitted = json.loads(path.read_text())["admitted_models"] if phase == "main" and path.exists() else []
        rows = runner.rows(phase, None if phase == "screen" else admitted)
        write_once(destination / f"{phase}_rows.json", rows)
        write_once(destination / f"{phase}_analysis.json", analysis.analyze(rows, phase))
        if phase == "screen":
            write_once(destination / "qualification.json", a2.qualification(rows, runner.plan))
    write_once(destination / "main_inventory.json", {
        "rows": runner.rows("main"), "deferred_models": runner.plan["deferred_models"],
        "scope": "Complete original inventory; estimates use only admitted models."})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=("screen-initial", "screen", "main", "audit"), default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    path = protocol.ROOT / PLAN
    if args.build:
        if args.execute or path.exists():
            raise Halted("Cannot overwrite plan or dispatch during build")
        write_once(path, build())
        print(protocol.canonical({"plan_sha256": protocol.sha(path)}))
        return
    if not args.freeze:
        raise Halted("Public A3 freeze required")
    plan = verify(path, args.freeze)
    sender = None
    if args.execute:
        if args.env_file:
            from dotenv import load_dotenv
            load_dotenv(args.env_file, override=False)
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise Halted("OpenRouter credential absent")
        sender = a1.sender_for(key)
    elif args.phase != "audit":
        raise Halted("Paid dispatch requires explicit execution")
    root = canonical_run_root()
    with ExitStack() as stack:
        fixture_gate = None
        for binding in PRIORS:
            prior_root = a2.original_root() / binding["path"]
            prior_plan = a2.verify_prior(prior_root, binding)
            old = stack.enter_context(Ledger(prior_root / "raw", cap=prior_plan["cap_usd"],
                                            screen_cap=prior_plan["screen_cap_usd"]))
            prior = Runner(prior_plan, binding["freeze"], binding["plan_sha256"], old)
            report = prior.audit()
            if (report["calls"] != binding["calls"] or report["unresolved"] != binding.get("unresolved", 1)
                    or old.spent() != Decimal(binding["cost_bound_usd"])
                    or any(r["phase"] != "fixtures" or r["metadata"]["kind"] == "generation" for r in old.rows())):
                raise Halted("Prior accounting or exposure changed")
            if binding["label"] == "a2":
                fixture_gate = adjudicate_gate(prior.run_fixtures())
        if fixture_gate is None or not fixture_gate["pass"]:
            raise Halted("Reconstructed technical fixtures do not qualify")
        write_once(root / "runtime.json", {
            "freeze": args.freeze, "plan_sha256": protocol.sha(path), "python": platform.python_version(),
            "platform": platform.platform(), "authorization_cap_usd": "250", "screen_cap_usd": "40",
            "prior_cost_bound_usd": str(PRIOR_COST), "prior_attempts": PRIORS})
        write_once(root / "fixture_gate.json", fixture_gate)
        ledger = stack.enter_context(Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]))
        runner = A3Runner(plan, args.freeze, protocol.sha(path), ledger, sender, fixture_gate=fixture_gate)
        try:
            if args.phase in {"screen-initial", "screen"}:
                runner.run_blocks("screen", initial=args.phase == "screen-initial")
            elif args.phase == "main":
                selection = runner.main_admission()
                write_once(root / "main_admission.json", selection)
                runner.run_blocks("main", models=selection["admitted_models"])
        finally:
            print(protocol.canonical(snapshot(root, runner)), flush=True)


if __name__ == "__main__":
    main()
