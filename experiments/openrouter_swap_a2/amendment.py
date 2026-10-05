"""Run the separately authorized extension without the unavailable route."""

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
from experiments.openrouter_swap.runner import canonical_run_root as original_root
from experiments.openrouter_swap_a1 import amendment as a1

PLAN = "data/openrouter_swap/plan_a2_20261004/PLAN.json"
ACTIVE_MODELS = ("gemini", "sonnet", "opus")
PRIOR_COST = Decimal("0.26254046")
PRIORS = [
    {"label": "original", "path": ".", "freeze": a1.BASE_FREEZE,
     "plan_path": protocol.PLAN, "plan_sha256": a1.BASE_PLAN_HASH,
     "journal_sha256": a1.PRIOR_JOURNAL_HASH, "cost_bound_usd": str(a1.PRIOR_COST),
     "calls": 12, "target_calls": 0},
    {"label": "a1", "path": "a1", "freeze": "7f9be332411e0c2dc8e6d6c9993c235e9e0fcbf1",
     "plan_path": a1.PLAN,
     "plan_sha256": "659b7b40650baf43a1494d829c2559caef0e6840d9a7b78d40cbe249b9d209c7",
     "journal_sha256": "403d28a36167b874edab2eeae8fd0cb361e148474d258ea8cd4855553b17712b",
     "cost_bound_usd": "0.1290626", "calls": 12, "target_calls": 0},
]


def canonical_run_root():
    return original_root() / "a2"


def build():
    previous = a1.verify(protocol.ROOT / a1.PLAN)
    if protocol.sha(protocol.ROOT / a1.PLAN) != PRIORS[1]["plan_sha256"]:
        raise Halted("A1 plan changed")
    result = deepcopy(previous)
    result["schema"] = "openrouter-swap-a2"
    result["models"] = {name: previous["models"][name] for name in ACTIVE_MODELS}
    result["active_models"] = list(ACTIVE_MODELS)
    result["deferred_models"] = {
        "deepseek": {"status": "not_run_privacy_route_unavailable",
                     "reason": "Native provider excluded by account paid-model-training policy; no target outcomes exist.",
                     "future_dispatch": "Requires a separately frozen compatible route; never change privacy policy."}}
    result["prior_cost_usd"] = str(PRIOR_COST)
    result["cap_usd"] = str(Decimal("250") - PRIOR_COST)
    result["screen_cap_usd"] = str(Decimal("40") - PRIOR_COST)
    result.pop("prior_attempt")
    result["prior_attempts"] = deepcopy(PRIORS)
    result["amendment"] = {
        "reason": "Isolate the unavailable DeepSeek route so the three working routes can proceed.",
        "authorization": "Owner explicitly requested the other tests proceed while a compatible host is investigated.",
        "prior_outcomes": "24 technical/synthetic requests across two attempts; zero scientific responses.",
        "retained": ["all original inventory slots", "eight-comparison multiplicity family",
                     "prompts", "controls", "sample sizes", "rubrics", "eligibility", "analysis"],
        "fixtures": "Fresh three-model routing checks and complete unchanged 24-judgment gate.",
        "retry_rule": "No automatic transport retry; a new unresolved call halts dispatch.",
        "deferred_outcomes": "Missing, not negative; no outcome-based model exclusion.",
    }
    names = [p.relative_to(protocol.ROOT).as_posix()
             for p in (protocol.ROOT / "experiments/openrouter_swap_a2").glob("*")
             if p.suffix in {".py", ".md"}]
    names += [p.relative_to(protocol.ROOT).as_posix()
              for p in (protocol.ROOT / "tests").glob("test_openrouter_isolation*.py")]
    result["source_hashes"].update({name: protocol.sha(protocol.ROOT / name) for name in sorted(names)})
    return result


def verify(path, freeze=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    if protocol.canonical(plan) != protocol.canonical(build()):
        raise Halted("A2 plan differs from bound sources or declared change")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise Halted("Full A2 freeze required")
        for name, expected in plan["source_hashes"].items():
            raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise Halted("A2 source does not match public freeze")
        raw = subprocess.check_output(["git", "show", f"{freeze}:{PLAN}"], cwd=protocol.ROOT)
        if raw != path.read_bytes():
            raise Halted("A2 plan bytes differ from public freeze")
        remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/openrouter-swap-panel"],
                                         cwd=protocol.ROOT, text=True).split()
        if not remote or subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote[0]],
                                        cwd=protocol.ROOT).returncode:
            raise Halted("A2 freeze is not on the public branch")
    return plan


def verify_prior(root, binding):
    root = Path(root)
    if protocol.sha(root / "raw/events.jsonl") != binding["journal_sha256"]:
        raise Halted("Prior journal changed")
    runtime = json.loads((root / "runtime.json").read_text())
    if any(runtime[key] != binding[key] for key in ("freeze", "plan_sha256")):
        raise Halted("Prior runtime binding changed")
    path = protocol.ROOT / binding["plan_path"]
    if protocol.sha(path) != binding["plan_sha256"]:
        raise Halted("Prior plan changed")
    return json.loads(path.read_text())


def audit_prior(root, binding, ledger):
    plan = verify_prior(root, binding)
    audit = Runner(plan, binding["freeze"], binding["plan_sha256"], ledger).audit()
    rows = ledger.rows()
    if (len(rows) != binding["calls"] or audit["unresolved"] != 1
            or ledger.spent() != Decimal(binding["cost_bound_usd"])
            or any(row["phase"] != "fixtures" for row in rows)
            or any(row["metadata"]["kind"] == "generation" for row in rows)):
        raise Halted("Prior exposure or accounting differs from amendment")
    return audit


class IndependentRunner(Runner):
    def run_blocks(self, phase, models=None, initial=False):
        models = list(ACTIVE_MODELS) if models is None else list(models)
        if set(models) - set(ACTIVE_MODELS):
            raise Halted("Deferred model cannot dispatch under A2")
        return super().run_blocks(phase, models=models, initial=initial)

    def main_admission(self):
        result = super().main_admission()
        result["projections"]["deepseek"] = deepcopy(self.plan["deferred_models"]["deepseek"])
        return result


def qualification(rows, plan):
    result = analysis.qualify(rows)
    deferred = result["models"].get("deepseek")
    if deferred is not None:
        deferred["unrun_inventory_diagnostics"] = {
            "decision": deferred["decision"], "reason_codes": deferred["reason_codes"]}
        deferred["decision"] = "not_run"
        deferred["reason_codes"] = [plan["deferred_models"]["deepseek"]["status"]]
        deferred["disposition"] = deepcopy(plan["deferred_models"]["deepseek"])
    return result


def snapshot(root, runner):
    report = runner.audit()
    report.update(prior_cost_bound_usd=str(PRIOR_COST),
                  cumulative_cost_bound_usd=str(PRIOR_COST + runner.ledger.spent()),
                  deferred_models=runner.plan["deferred_models"])
    destination = root / "snapshots" / f"{len(runner.ledger.rows()):06d}"
    write_once(destination / "audit.json", report)
    for phase in ("screen", "main"):
        selection_path = root / "main_admission.json"
        admitted = json.loads(selection_path.read_text())["admitted_models"] if phase == "main" and selection_path.exists() else []
        rows = runner.rows(phase, None if phase == "screen" else admitted)
        write_once(destination / f"{phase}_rows.json", rows)
        write_once(destination / f"{phase}_analysis.json", analysis.analyze(rows, phase))
        if phase == "screen":
            write_once(destination / "qualification.json", qualification(rows, runner.plan))
    write_once(destination / "main_inventory.json", {
        "rows": runner.rows("main"), "deferred_models": runner.plan["deferred_models"],
        "scope": "Complete original inventory; estimates use only admitted models."})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=("fixtures", "screen-initial", "screen", "main", "audit"), default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    path = protocol.ROOT / PLAN
    if args.build:
        if args.execute or path.exists():
            raise Halted("Cannot overwrite a plan or dispatch during build")
        write_once(path, build())
        print(protocol.canonical({"plan_sha256": protocol.sha(path)}))
        return
    if not args.freeze:
        raise Halted("Public A2 freeze required")
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
        for binding in PRIORS:
            prior_root = original_root() / binding["path"]
            prior_plan = verify_prior(prior_root, binding)
            old = stack.enter_context(Ledger(prior_root / "raw", cap=prior_plan["cap_usd"],
                                            screen_cap=prior_plan["screen_cap_usd"]))
            audit_prior(prior_root, binding, old)
        write_once(root / "runtime.json", {
            "freeze": args.freeze, "plan_sha256": protocol.sha(path), "python": platform.python_version(),
            "platform": platform.platform(), "authorization_cap_usd": "250", "screen_cap_usd": "40",
            "prior_cost_bound_usd": str(PRIOR_COST), "prior_attempts": PRIORS,
        })
        ledger = stack.enter_context(Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]))
        runner = IndependentRunner(plan, args.freeze, protocol.sha(path), ledger, sender)
        try:
            if args.phase == "fixtures":
                gate = runner.run_fixtures()
                write_once(root / "fixture_gate.json", gate)
                if not gate["pass"]:
                    raise Halted("A2 fixture gate failed; no targets dispatched")
            elif args.phase in {"screen-initial", "screen"}:
                runner.run_blocks("screen", initial=args.phase == "screen-initial")
            elif args.phase == "main":
                selection = runner.main_admission()
                write_once(root / "main_admission.json", selection)
                runner.run_blocks("main", models=selection["admitted_models"])
        finally:
            print(protocol.canonical(snapshot(root, runner)), flush=True)


if __name__ == "__main__":
    main()
