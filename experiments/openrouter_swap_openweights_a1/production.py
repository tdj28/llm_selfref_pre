"""Unexecuted production preparation. No import-time network or credential I/O."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.providers import _amount, live_sender, TransportError
from experiments.openrouter_swap.release import _load
from experiments.openrouter_swap.runner import write_once as _write_once
from scripts import audit_public_release as public_audit
from . import protocol
from .runner import ExtensionRunner, SharedLedger

PLAN = "data/openrouter_swap_openweights_a1/plan_v1/PLAN.json"
BRANCH = "refs/heads/codex/openrouter-swap-panel"
PHASES = ("fixtures", "screen-initial", "screen", "main")


def write_once(path, value):
    _no_symlinks(Path(path))
    _write_once(path, value)


def bytes_once(path, data):
    path = Path(path)
    _no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise Halted("Existing artifact differs")
    else:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())


def sha(value):
    return hashlib.sha256(value).hexdigest()


def _hex(value, length=64):
    return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def public_json(value):
    # Decode escapes before scanning; also expose embedded multiline assignments.
    for text in (common.canonical(value), "\n".join(_strings(value))):
        if public_audit.scan_bytes("openweights.json", text.encode("utf-8")):
            raise Halted("Public content scan failed")


def public_identifier(value, *, scope=False):
    pattern = r"[A-Za-z0-9][A-Za-z0-9 ._+(),-]{0,199}" if scope else r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}"
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise Halted("Public identifiers must be bounded labels, not private paths or correspondence")
    public_json(value)


def guarded_sender(api_key):
    send = live_sender(api_key)
    def checked(request):
        raw = send(request)
        if any(api_key in text for text in _strings(raw)):
            raise TransportError()
        return raw
    return checked


def _date(value, *, fresh=False, days=1):
    if (not isinstance(value, str) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value) is None):
        raise Halted("Explicit UTC timestamp required")
    stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise Halted("Explicit UTC timestamp required")
    if fresh and not timedelta(0) <= datetime.now(timezone.utc) - stamp <= timedelta(days=days):
        raise Halted("Budget or endpoint evidence is stale or future-dated")
    return stamp


def source_hashes():
    # Consume the old frozen inventory, not its broad glob (which now sees A1).
    if common.sha(common.ROOT / protocol.PREDECESSOR_RELEASE) != protocol.PREDECESSOR["release_sha256"]:
        raise Halted("Predecessor failure release changed")
    release = _load(common.ROOT / protocol.PREDECESSOR_RELEASE)
    if common.sha(common.ROOT / protocol.OLD_PLAN) != release["plan_sha256"]:
        raise Halted("Predecessor plan differs from its bound failure release")
    previous = _load(common.ROOT / protocol.OLD_PLAN)
    hashes = dict(previous["source_hashes"])
    if any(common.sha(common.ROOT / name) != digest for name, digest in hashes.items()):
        raise Halted("Predecessor frozen source changed")
    names = {protocol.OLD_PLAN, protocol.PREDECESSOR_RELEASE}
    names.update(p.relative_to(common.ROOT).as_posix()
                 for p in (common.ROOT / "experiments/openrouter_swap_openweights_a1").iterdir()
                 if p.is_file() and p.suffix in {".py", ".md"})
    names.update(p.relative_to(common.ROOT).as_posix()
                 for p in (common.ROOT / "tests").glob("test_openrouter_openweights_a1*.py"))
    hashes.update({name: common.sha(common.ROOT / name) for name in sorted(names)})
    return dict(sorted(hashes.items()))


def budget_carry(budget, record):
    if (Decimal(budget.hard_cap_usd) > 200
            or Decimal(budget.prior_spend_usd) < protocol.PRIOR_PANEL + protocol.FAILED_COST
            or Decimal(budget.screening_allowance_usd) + protocol.FAILED_COST > 25):
        raise Halted("A1 must retain cumulative provider and fixture/screen cost caps")
    carry = [r for r in record["prior_costs"] if r["id"] == "openweights-v1-through-failure"]
    if (len(carry) != 1 or Decimal(carry[0]["cost_bound_usd"]) < protocol.PRIOR_PANEL + protocol.FAILED_COST
            or carry[0]["evidence_sha256"] != protocol.PREDECESSOR["release_sha256"]):
        raise Halted("Failure release and all unresolved cost carry required")


def endpoint_capabilities(evidence, specs, *, fresh=False):
    if not isinstance(evidence, dict) or set(evidence) != set(specs):
        raise Halted("Saved endpoint evidence required for both models and judges")
    judge_ids = {s["id"] for s in protocol.JUDGES.values()}
    for model, spec in specs.items():
        record = evidence[model]
        if (not isinstance(record, dict) or set(record) != {
                "spec", "privacy", "checked_at_utc", "catalog_sha256", "catalog"}
                or common.canonical(record["spec"]) != common.canonical(spec)
                or common.canonical(record["privacy"]) != common.canonical(protocol.PRIVACY)
                or record["catalog_sha256"] != common.digest(record["catalog"])):
            raise Halted("Saved endpoint evidence or canonical catalog hash differs")
        _date(record["checked_at_utc"], fresh=fresh, days=7)
        catalog = record["catalog"]
        if (not isinstance(catalog, dict) or set(catalog) != {
                "checked_at_utc", "url", "endpoint", "zdr_catalog_url", "zdr_endpoint"}
                or catalog["checked_at_utc"] != record["checked_at_utc"]
                or catalog["url"] != f"https://openrouter.ai/api/v1/models/{model}/endpoints"
                or catalog["zdr_catalog_url"] != "https://openrouter.ai/api/v1/endpoints/zdr"):
            raise Halted("Exact public endpoint and ZDR snapshot required")
        for endpoint in (catalog["endpoint"], catalog["zdr_endpoint"]):
            if (not isinstance(endpoint, dict) or endpoint.get("model_id") != model or endpoint.get("tag") != spec["provider_slug"]
                    or endpoint.get("provider_name") != spec["provider_name"]):
                raise Halted("Endpoint or ZDR route identity differs")
            if type(endpoint.get("status")) is not int or endpoint["status"] != 0:
                raise Halted("Endpoint status must be integer zero")
            params = endpoint.get("supported_parameters")
            if not isinstance(params, list) or any(not isinstance(p, str) for p in params):
                raise Halted("Endpoint capability list required")
            required = {"reasoning", "reasoning_effort"}
            if model in judge_ids:
                required.update({"response_format", "structured_outputs"})
            if "temperature" in spec:
                required.add("temperature")
            if (not required <= set(params) or not {"max_tokens", "max_completion_tokens"} & set(params)
                    or type(endpoint.get("max_completion_tokens")) is not int
                    or endpoint["max_completion_tokens"] < (6000 if model in judge_ids else 4096)):
                raise Halted("Required endpoint capabilities unavailable")
            price = endpoint.get("pricing", {})
            if (not isinstance(price, dict) or _amount(price.get("prompt")) * 1_000_000 > _amount(spec["input_price"])
                    or _amount(price.get("completion")) * 1_000_000 > _amount(spec["output_price"])):
                raise Halted("Catalog pricing exceeds frozen ceilings")
    public_json(evidence)


def reconcile(budget, record, *, fresh=False, exact=False):
    if (not isinstance(record, dict) or set(record) != {"scope", "confirmed", "as_of_utc", "prior_costs", "external_commitments"}
            or record["confirmed"] is not True or record["scope"] != budget.scope):
        raise Halted("Explicit scope and reconciliation required")
    budget.limits()
    public_identifier(budget.scope, scope=True)
    _date(record["as_of_utc"], fresh=fresh)
    totals = []
    for name in ("prior_costs", "external_commitments"):
        rows, identifiers, total = record[name], set(), Decimal(0)
        if not isinstance(rows, list):
            raise Halted("Cost records must be explicit lists, including empty lists")
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"id", "cost_bound_usd", "evidence_sha256"} or not isinstance(row["id"], str)
                    or not row["id"].strip() or row["id"] in identifiers or not _hex(row["evidence_sha256"])):
                raise Halted("Cost evidence malformed or duplicated")
            public_identifier(row["id"])
            identifiers.add(row["id"])
            total += _amount(row["cost_bound_usd"])
        totals.append(total)
    frozen = [_amount(budget.prior_spend_usd), _amount(budget.external_commitments_usd)]
    if (exact and totals != frozen) or sum(totals) > sum(frozen):
        raise Halted("Reconciliation exceeds or differs from the reserved scope budget")
    public_json(record)
    budget_carry(budget, record)
    return totals


def finalize(draft, *, authorization=None, reconciliation=None, endpoint_evidence=None, fresh=True):
    budget = protocol.verify_draft(draft)
    budget.limits()
    if (not isinstance(authorization, dict) or set(authorization) != {"approval_id", "approved", "scope", "new_target_outcomes_seen"}
            or authorization["approved"] is not True or authorization["scope"] != budget.scope
            or authorization["new_target_outcomes_seen"] is not False
            or not isinstance(authorization["approval_id"], str) or not authorization["approval_id"].strip()):
        raise Halted("Explicit new collection approval and outcome-aware design required")
    public_identifier(authorization["approval_id"])
    reconcile(budget, reconciliation, fresh=fresh, exact=True)
    specs = {s["id"]: s for s in [*draft["models"].values(), *draft["judges"].values()]}
    endpoint_capabilities(endpoint_evidence, specs, fresh=fresh)
    result = {**deepcopy(draft), "schema": "openrouter-openweights-a1-production-v1", "status": "prospective_plan",
            "launch_authorized": True,
            "authorization": deepcopy(authorization), "reconciliation": deepcopy(reconciliation),
            "endpoint_evidence": deepcopy(endpoint_evidence), "source_hashes": source_hashes()}
    public_json(result)
    return result


def validate(plan):
    budget = protocol.Budget(**plan["budget"])
    expected = finalize(protocol.build_draft(budget=budget), authorization=plan["authorization"],
                        reconciliation=plan["reconciliation"], endpoint_evidence=plan["endpoint_evidence"], fresh=False)
    if common.canonical(expected) != common.canonical(plan):
        raise Halted("Production plan/source inventory differs")
    return budget


def verify_git(path, freeze, *, pushed=False):
    plan = _load(Path(path))
    validate(plan)
    if not _hex(freeze, 40):
        raise Halted("Full freeze SHA required")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=common.ROOT, stderr=subprocess.DEVNULL)
    for name, digest in plan["source_hashes"].items():
        if sha(git("show", f"{freeze}:{name}")) != digest:
            raise Halted("Frozen source differs")
    if git("show", f"{freeze}:{PLAN}") != Path(path).read_bytes():
        raise Halted("Plan bytes differ from freeze")
    proof = {"freeze": freeze, "branch": BRANCH, "remote_head": None}
    if pushed:
        remote = git("ls-remote", "origin", BRANCH).decode().split()
        if len(remote) != 2 or not _hex(remote[0], 40) or remote[1] != BRANCH:
            raise Halted("Pushed branch proof unavailable")
        git("merge-base", "--is-ancestor", freeze, remote[0])
        proof["remote_head"] = remote[0]
    return plan, proof


def canonical_root():
    git = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=common.ROOT, text=True).strip()
    return (common.ROOT / git).resolve().parent / "out/openrouter-openweights-a1-v1"


def load_key(env_file):
    if env_file is None:
        value = os.environ.get("OPENROUTER_API_KEY")
    else:
        from dotenv import dotenv_values
        path = Path(env_file).absolute()
        _no_symlinks(path)
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise Halted("Local credential file must be private to its owner")
        value = dotenv_values(path, interpolate=False).get("OPENROUTER_API_KEY")
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise Halted("OpenRouter credential unavailable")
    return value


def checkpoint(root, runner, kind):
    if kind == "main_admission" and any(r["phase"] == "main" for r in runner.ledger.rows()):
        raise Halted("Admission must precede every main call")
    value = runner.main_admission() if kind == "main_admission" else runner.audit()
    if kind == "initial_audit":
        runner.require_resolved(); runner.require_fixtures()
        runner.complete("screen", initial=True)
        if any(r["phase"] == "main" or (r["phase"] == "screen" and
               runner.catalog[r["metadata"]["item_id"]]["block"] > 2) for r in runner.ledger.rows()):
            raise Halted("Initial audit must precede screen completion")
    raw = (Path(root) / "raw/events.jsonl").read_bytes()
    return {"event_count": len(raw.splitlines()), "journal_prefix_sha256": sha(raw), "value": value}


def verify_checkpoint(raw, record, plan, runtime, kind):
    if (set(record) != {"event_count", "journal_prefix_sha256", "value"}
            or type(record["event_count"]) is not int or not 1 <= record["event_count"] <= len(raw.splitlines())):
        raise Halted("Checkpoint prefix invalid")
    prefix = b"".join(raw.splitlines(keepends=True)[:record["event_count"]])
    if sha(prefix) != record["journal_prefix_sha256"]:
        raise Halted("Checkpoint journal binding differs")
    cap, screen = protocol.Budget(**plan["budget"]).limits()
    with TemporaryDirectory() as temporary:
        root = Path(temporary).resolve(); (root / "raw").mkdir()
        (root / "raw/events.jsonl").write_bytes(prefix)
        with SharedLedger(root / "raw", cap=cap, screen_cap=screen) as ledger:
            runner = ExtensionRunner(plan, runtime["freeze"], runtime["plan_sha256"], ledger)
            if common.canonical(checkpoint(root, runner, kind)) != common.canonical(record):
                raise Halted("Checkpoint does not reconstruct")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", metavar="LOCAL_INPUTS_JSON")
    parser.add_argument("--freeze")
    parser.add_argument("--phase", choices=(*PHASES, "audit"), default="audit")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--approval")
    parser.add_argument("--reconciliation")
    parser.add_argument("--env-file")
    parser.add_argument("--run-dir", help="Offline audit only; launch always uses the shared canonical ledger")
    args = parser.parse_args(argv)
    try:
        path = common.ROOT / PLAN
        if args.finalize:
            if args.launch or args.freeze or path.exists():
                raise Halted("Finalization cannot launch or replace a plan")
            inputs = _load(Path(args.finalize))
            if set(inputs) != {"budget", "authorization", "reconciliation", "endpoint_evidence"}:
                raise Halted("Finalization inputs must be explicit and exact")
            draft = protocol.build_draft(budget=protocol.Budget(**inputs.pop("budget")))
            write_once(path, finalize(draft, **inputs))
            return
        if args.phase != "audit" and not args.launch:
            raise Halted("Collection requires explicit --launch")
        if args.launch and (args.run_dir or args.phase == "audit"):
            raise Halted("Launch must use the single canonical ledger and collection phase")
        plan = _load(path); budget = validate(plan)
        if args.launch:
            if args.approval != plan["authorization"]["approval_id"] or not args.reconciliation:
                raise Halted("Explicit matching approval and fresh reconciliation required")
            reconciliation = _load(Path(args.reconciliation))
            reconcile(budget, reconciliation, fresh=True)
            endpoint_capabilities(plan["endpoint_evidence"],
                {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}, fresh=True)
        plan, proof = verify_git(path, args.freeze, pushed=args.launch)
        root = Path(args.run_dir).absolute() if args.run_dir else canonical_root()
        _no_symlinks(root)
        runtime = {"freeze": args.freeze, "plan_sha256": common.sha(path), "plan_path": PLAN, "budget": plan["budget"]}
        if not args.launch:
            from .release import inspect_run
            print(common.canonical(inspect_run(root)["RELEASE.json"]))
            return
        sender = guarded_sender(load_key(args.env_file))
        cap, screen = budget.limits()
        with SharedLedger(root / "raw", cap=cap, screen_cap=screen) as ledger:
            bytes_once(root / "PLAN.json", path.read_bytes())
            write_once(root / "runtime.json", runtime)
            launch = {"phase": args.phase, "proof": proof, "reconciliation": reconciliation,
                      "plan_sha256": runtime["plan_sha256"], "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                      "event_count_before": len(read_events(root / "raw/events.jsonl"))}
            write_once(root / "launches" / (common.digest(launch) + ".json"), launch)
            runner = ExtensionRunner(plan, args.freeze, runtime["plan_sha256"], ledger, sender)
            runner.require_resolved()
            if args.phase == "fixtures":
                gate = runner.run_fixtures(); write_once(root / "fixture_gate.json", gate)
                if not gate["pass"]:
                    raise Halted("Technical fixtures failed; no target dispatch")
            elif args.phase == "screen-initial":
                runner.run_blocks("screen", initial=True)
                write_once(root / "initial_audit.json", checkpoint(root, runner, "initial_audit"))
            else:
                verify_checkpoint((root / "raw/events.jsonl").read_bytes(), _load(root / "initial_audit.json"), plan, runtime, "initial_audit")
                if args.phase == "screen":
                    runner.run_blocks("screen")
                else:
                    admission = root / "main_admission.json"
                    if not admission.exists():
                        write_once(admission, checkpoint(root, runner, "main_admission"))
                    verify_checkpoint((root / "raw/events.jsonl").read_bytes(), _load(admission), plan, runtime, "main_admission")
                    runner.run_blocks("main")
            print(common.canonical(runner.audit()))
    except (ValueError, TypeError, KeyError, OSError, Halted, subprocess.SubprocessError):
        parser.exit(1, "Openweights operation failed closed; records retained.\n")


if __name__ == "__main__":
    main()
