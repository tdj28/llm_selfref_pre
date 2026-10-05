"""Source-bound recovery of the failed DeepSeek routing fixture, before targets."""

from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from experiments.openrouter_swap import analysis, protocol
from experiments.openrouter_swap.ledger import Ledger, Halted
from experiments.openrouter_swap.providers import ENDPOINT, TransportError, _public_body
from experiments.openrouter_swap.runner import Runner, write_once
from experiments.openrouter_swap.runner import canonical_run_root as prior_run_root

PLAN = "data/openrouter_swap/plan_a1_20261004/PLAN.json"
BASE_FREEZE = "f69362310217cbf947a940465c88e8d8c3b740b9"
BASE_PLAN_HASH = "de38292b7dc5cc4c8718595acfd7a137603afe0b419a239a5665489fe7e5c15e"
PRIOR_JOURNAL_HASH = "a5dedcae1b8415e0c81eb6c6f1262632d8f2da84e3512ee3fb88746bc2c7aee2"
PRIOR_COST = Decimal("0.13347786")


def error_receipt(status, body, key):
    """Retain only a bounded, credential-scrubbed provider error diagnostic."""
    result = {"transport_status_code": status, "error_body_sha256": hashlib.sha256(body).hexdigest()}
    try:
        value = json.loads(body).get("error", {})
    except (ValueError, AttributeError):
        value = {}
    message = value.get("message") if isinstance(value, dict) else None
    if isinstance(message, str):
        message = message.replace(key, "[credential removed]")
        message = re.sub(r"\b(?:sk-|hf_|ghp_)[A-Za-z0-9_-]+", "[credential removed]", message)
        result["error"] = {"message": message[:1000]}
    return result


def sender_for(key):
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = build_opener(NoRedirect)
    def send(request):
        failed, raw, status = False, None, None
        try:
            _public_body(request)
            body = protocol.canonical(request).encode()
            if key in body.decode():
                raise ValueError("Credential in request body")
            req = Request(ENDPOINT, data=body, headers={"Authorization": "Bearer " + key,
                                                      "Content-Type": "application/json"})
            with opener.open(req, timeout=180) as response:
                status = response.status
                if status != 200:
                    raise ValueError("Non-success HTTP status")
                payload = response.read().decode()
                if key in payload:
                    raise ValueError("Credential in response")
                raw = json.loads(payload)
                if not isinstance(raw, dict) or key in protocol.canonical(raw):
                    raise ValueError("Invalid or credential-bearing response")
                _public_body(raw)
        except HTTPError as error:
            status = error.code
            try:
                raw = error_receipt(status, error.read(65536), key)
            except Exception:
                failed = True
            finally:
                error.close()
        except Exception:
            failed = True
        if failed:
            raise TransportError(status)
        return raw
    return send


def canonical_run_root():
    return prior_run_root() / "a1"


def build():
    base_path = protocol.ROOT / protocol.PLAN
    base = protocol.verify(base_path)
    if protocol.sha(base_path) != BASE_PLAN_HASH:
        raise Halted("Original plan changed")
    result = deepcopy(base)
    result["schema"] = "openrouter-swap-a1"
    result["models"]["deepseek"].pop("temperature")
    result["prior_cost_usd"] = str(PRIOR_COST)
    result["cap_usd"] = str(Decimal("250") - PRIOR_COST)
    result["screen_cap_usd"] = str(Decimal("40") - PRIOR_COST)
    result["prior_attempt"] = {
        "freeze": BASE_FREEZE, "plan_sha256": BASE_PLAN_HASH,
        "journal_sha256": PRIOR_JOURNAL_HASH, "cost_bound_usd": str(PRIOR_COST),
        "calls": 12, "target_calls": 0, "failed_call": "route:deepseek",
        "http_status": 404, "full_failed_reservation_retained_usd": "0.02207436",
    }
    result["amendment"] = {
        "reason": "Remove a temperature setting documented as ignored in DeepSeek thinking mode; routing root cause remains unproven.",
        "prior_outcomes": "11 successful technical/synthetic receipts; one HTTP 404; no scientific responses.",
        "fixture_reexecution": "One fresh fixture phase only; all prior calls retained and charged.",
        "technical_retry_limit": 1,
        "unchanged": ["model IDs", "provider routes", "reasoning effort", "scientific prompts",
                      "sample size", "controls", "eligibility", "rubrics", "analysis"],
        "documentation": "https://api-docs.deepseek.com/guides/thinking_mode/",
    }
    names = [p.relative_to(protocol.ROOT).as_posix()
             for p in (protocol.ROOT / "experiments/openrouter_swap_a1").glob("*.py")]
    names += [p.relative_to(protocol.ROOT).as_posix()
              for p in (protocol.ROOT / "tests").glob("test_openrouter_recovery*.py")]
    names += ["docs/AMENDMENTS.md"]
    result["source_hashes"].update({p: protocol.sha(protocol.ROOT / p) for p in sorted(names)})
    return result


def verify(path, freeze=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    if protocol.canonical(plan) != protocol.canonical(build()):
        raise Halted("Amended plan differs from bound sources or declared change")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise Halted("Full amendment freeze required")
        for name, expected in plan["source_hashes"].items():
            raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise Halted("Amendment source does not match published freeze")
        raw = subprocess.check_output(["git", "show", f"{freeze}:{PLAN}"], cwd=protocol.ROOT)
        if raw != path.read_bytes():
            raise Halted("Amendment plan bytes do not match published freeze")
        remote = subprocess.check_output(["git", "ls-remote", "origin", "refs/heads/codex/openrouter-swap-panel"],
                                         cwd=protocol.ROOT, text=True).split()
        if not remote or subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote[0]],
                                        cwd=protocol.ROOT).returncode:
            raise Halted("Amendment freeze is not on the public branch")
    return plan


def verify_prior(root):
    """Hold the old ledger's process lock throughout every new paid phase."""
    root = Path(root)
    if protocol.sha(root / "raw/events.jsonl") != PRIOR_JOURNAL_HASH:
        raise Halted("Prior ledger changed; cumulative cost must be reconciled")
    runtime = json.loads((root / "runtime.json").read_text())
    if runtime["freeze"] != BASE_FREEZE or runtime["plan_sha256"] != BASE_PLAN_HASH:
        raise Halted("Prior runtime binding differs")
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    return plan


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
        raise Halted("Published amendment freeze required")
    plan = verify(path, args.freeze)
    prior = prior_run_root()
    prior_plan = verify_prior(prior)
    sender = None
    if args.execute:
        if args.env_file:
            from dotenv import load_dotenv
            load_dotenv(args.env_file, override=False)
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise Halted("OpenRouter credential absent")
        sender = sender_for(key)
    elif args.phase != "audit":
        raise Halted("Paid work requires explicit execution")
    root = canonical_run_root()
    with Ledger(prior / "raw") as old:
        verify_prior(prior)
        old_audit = Runner(prior_plan, BASE_FREEZE, BASE_PLAN_HASH, old).audit()
        if (old.spent() != PRIOR_COST or len(old.rows()) != 12
                or any(row["metadata"]["kind"] == "generation" for row in old.rows())
                or old_audit["unresolved"] != 1):
            raise Halted("Prior costs or outcome exposure do not match amendment")
        write_once(root / "runtime.json", {
            "freeze": args.freeze, "plan_sha256": protocol.sha(path), "python": platform.python_version(),
            "platform": platform.platform(), "authorization_cap_usd": "250", "screen_cap_usd": "40",
            "prior_cost_bound_usd": str(PRIOR_COST), "prior_journal_sha256": PRIOR_JOURNAL_HASH,
        })
        with Ledger(root / "raw", cap=plan["cap_usd"], screen_cap=plan["screen_cap_usd"]) as ledger:
            runner = Runner(plan, args.freeze, protocol.sha(path), ledger, sender)
            if args.phase == "fixtures":
                gate = runner.run_fixtures()
                write_once(root / "fixture_gate.json", gate)
                if not gate["pass"]:
                    raise Halted("Amended fixture gate failed; targets remain blocked")
            elif args.phase in {"screen-initial", "screen"}:
                runner.run_blocks("screen", initial=args.phase == "screen-initial")
            elif args.phase == "main":
                selection = runner.main_admission()
                write_once(root / "main_admission.json", selection)
                runner.run_blocks("main", models=selection["admitted_models"])
            report = runner.audit()
            report.update(prior_cost_bound_usd=str(PRIOR_COST),
                          cumulative_cost_bound_usd=str(PRIOR_COST + ledger.spent()))
            snapshot = root / "snapshots" / f"{len(ledger.rows()):06d}"
            write_once(snapshot / "audit.json", report)
            for phase in ("screen", "main"):
                selection_path = root / "main_admission.json"
                admitted = json.loads(selection_path.read_text())["admitted_models"] if phase == "main" and selection_path.exists() else []
                rows = runner.rows(phase, None if phase == "screen" else admitted)
                write_once(snapshot / f"{phase}_rows.json", rows)
                write_once(snapshot / f"{phase}_analysis.json", analysis.analyze(rows, phase))
                if phase == "screen":
                    write_once(snapshot / "qualification.json", analysis.qualify(rows))
            print(protocol.canonical(report), flush=True)


if __name__ == "__main__":
    main()
