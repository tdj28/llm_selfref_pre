"""Mini runner copied from 5398dc657b6a, rebound to the B1 budget proof.

The B1 proof reuses A1 fixtures; no fresh fixture calls or extra frontier budget.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import urllib.request

from experiments.automated_rubric_audit.common import canonical, digest, sha
from . import protocol, qualification
from .ledger import Ledger, Halted, no_symlinks
from .providers import MODELS, JUDGES, generation_request, generation_result, live_sender, model_matches, receipt_cost, reservation


def evaluate(model, raw, *, instrument=None, item=None):
    if not isinstance(raw, dict) or not model_matches(model, raw.get("model")) or not raw.get("id"):
        return {"status": "model_or_receipt_failure", "fatal": True}
    try:
        receipt_cost(model, raw)
    except (ValueError, TypeError, KeyError):
        return {"status": "usage_failure", "fatal": True}
    if instrument is None:
        return generation_result(model, raw)
    try:
        label, derived = protocol.judge_module().parse_label(instrument, MODELS[model]["provider"], raw, item["response"])
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"status": "judge_schema_or_completion_failure", "fatal": True}
    return {"status": "ok", "label": label, "derived": derived}


def specs(plan):
    return {s["id"]: s for block in plan["inventory"] for kind in ("sources", "finals") for s in block[kind]}


def item_from_result(spec, result):
    value = result.get("evaluated", {})
    return {**spec, "query": protocol.prompts.final_query(spec["language"], spec["language"]),
            "response": value.get("response") if not value.get("missing", True) else None,
            "missing": value.get("missing", True), "raw_status": value.get("status")}


def expected_call(key, plan, results):
    catalog = specs(plan)
    if key.startswith("gen:"):
        spec = catalog[key[4:]]
        source = None
        if spec["kind"] == "final":
            donor = results.get("gen:" + spec["source_id"])
            if donor is None or donor["evaluated"].get("missing", True):
                raise ValueError("Final request lacks an observed complete donor")
            source = donor["evaluated"]["response"]
        return spec["model"], generation_request(spec["model"], protocol.generation_messages(spec, source)), {
            "phase": spec["kind"], "item_id": spec["id"], "block": spec["block"]}
    _, identifier, provider, instrument = key.split(":")
    if instrument not in {"paper", "structured"} or provider not in JUDGES:
        raise ValueError("Unfrozen judge condition")
    spec = catalog[identifier]
    if spec["kind"] != "final":
        raise ValueError("Only final answers are judge targets")
    item = item_from_result(spec, results["gen:" + identifier])
    request = protocol.judge_module().make_request(provider, instrument, item)
    return JUDGES[provider], request, {"phase": "judge", "item_id": identifier, "block": spec["block"],
                                     "provider": provider, "instrument": instrument, "item_sha256": digest(item)}


def audit(ledger, plan, *, require_complete=False, allow_failures=False):
    """Rebuild every request and parsed result from raw receipts, not saved labels."""
    if not allow_failures:
        ledger.require_resolved()
    identities = {m: set() for m in MODELS}
    catalog = specs(plan)
    for key, req in ledger.requests.items():
        model, request, metadata = expected_call(key, plan, ledger.results)
        if (req["model"] != model or req["request"] != request or req["request_sha256"] != digest(request)
                or any(req.get(k) != v for k, v in metadata.items())):
            raise ValueError("Request does not reconstruct from frozen inventory")
        result = ledger.results.get(key)
        if result is None:
            if allow_failures:
                continue
            raise Halted("Unresolved request")
        if result["raw"] is None:
            if not allow_failures:
                raise Halted("Unknown charged call is preserved, not retried")
            if result["evaluated"] != {"status": "transport_unknown", "fatal": True}:
                raise ValueError("Transport failure record is inconsistent")
            continue
        item = item_from_result(catalog[req["item_id"]], ledger.results["gen:" + req["item_id"]]) if req["phase"] == "judge" else None
        expected = evaluate(model, result["raw"], instrument=req.get("instrument"), item=item)
        if expected != result["evaluated"]:
            raise ValueError("Saved response/label differs from receipt replay")
        identities[model].add(result["raw"].get("model"))
    if not allow_failures and any(len(values) > 1 for values in identities.values()):
        raise Halted("Actual API model snapshot drifted within the study")
    for key, result in ledger.results.items():
        if key in ledger.requests:
            continue
        dep = result["dependency"]
        if dep not in ledger.results or not ledger.results[dep]["evaluated"].get("missing", True):
            raise ValueError("Unpaid missing slot has no missing dependency")
        if key.startswith("gen:"):
            s = catalog[key[4:]]
            if s["kind"] != "final" or dep != "gen:" + s["source_id"] or result["reason"] != "missing_source":
                raise ValueError("Wrong missing source dependency")
        else:
            _, identifier, provider, instrument = key.split(":")
            if dep != "gen:" + identifier or provider not in JUDGES or instrument not in {"paper", "structured"}:
                raise ValueError("Wrong missing judge dependency")
    expected_ids = {"gen:" + s for s in catalog}
    expected_ids |= {f"judge:{s['id']}:{p}:{i}" for s in catalog.values() if s["kind"] == "final"
                     for p in JUDGES for i in ("paper", "structured")}
    if not set(ledger.results) <= expected_ids or require_complete and set(ledger.results) != expected_ids:
        raise ValueError("Unexpected or incomplete slot inventory")
    return {"schema": "frontier-mini-receipt-audit-v1", "complete": set(ledger.results) == expected_ids,
            "planned_slots": len(expected_ids), "recorded_slots": len(ledger.results),
            "paid_calls": len(ledger.requests),
            "missing_slots": len(set(ledger.results) - set(ledger.requests)),
            "uncollected_slots": len(expected_ids - set(ledger.results) - set(ledger.requests)),
            "cost_usd_upper_bound": str(ledger.spent()),
            "failed_calls": sorted(k for k, r in ledger.results.items() if r.get("fatal")),
            "unresolved_calls": sorted(set(ledger.requests) - set(ledger.results)),
            "dispatch_eligible": not any(r.get("fatal") for r in ledger.results.values())
                and set(ledger.requests) <= set(ledger.results) and ledger.spent() <= Decimal("60"),
            "model_snapshots": {k: sorted(v, key=str) for k, v in identities.items()}}


def project_cost(ledger, plan):
    """Recompute cost forecast only; never inspect scientific positive rates."""
    from collections import defaultdict

    costs = defaultdict(list)
    remaining = defaultdict(int)
    model_for = {}
    for key, req in ledger.requests.items():
        group = (req["phase"], req["model"], req.get("instrument"))
        costs[group].append(Decimal(ledger.results[key]["cost_usd"]))
        model_for[group] = req["model"]
    for block in plan["inventory"]:
        for phase in ("sources", "finals"):
            for spec in block[phase]:
                group = (spec["kind"], spec["model"], None)
                if "gen:" + spec["id"] not in ledger.results:
                    remaining[group] += 1
                if spec["kind"] == "final":
                    for p, model in JUDGES.items():
                        for instrument in ("paper", "structured"):
                            group = ("judge", model, instrument)
                            if f"judge:{spec['id']}:{p}:{instrument}" not in ledger.results:
                                remaining[group] += 1
    panels, total = {}, ledger.spent()
    for group, count in sorted(remaining.items(), key=str):
        if not costs[group]:
            raise Halted("Insufficient first-block cost observations")
        # Account for longer later continuations, including Chinese tokenization.
        allowance = (Decimal(plan["prebulk"]["input_allowance_bytes"]) / Decimal(plan["prebulk"]["forecast_bytes_per_token"])
                     * Decimal(MODELS[group[1]]["input_price"]) * Decimal("1.25") / 1_000_000)
        mean = sum(costs[group]) / len(costs[group])
        upper = Decimal("1.5") * (mean + allowance) * count
        total += upper
        panels[":".join(str(x) for x in group)] = {"observations": len(costs[group]), "remaining": count,
            "observed_mean_usd": str(mean), "input_allowance_usd": str(allowance), "forecast_usd": str(upper)}
    inflight = (max((reservation(r["model"], r["request"]) for r in ledger.requests.values()), default=Decimal(0))
                * plan["prebulk"]["inflight_reservations"] if remaining else Decimal(0))
    total += inflight
    return {"pass": total <= Decimal("60"), "spent_usd": str(ledger.spent()), "inflight_reserve_usd": str(inflight),
            "projected_total_usd": str(total), "cap_usd": "60", "by_group": panels}


def technical_gate(ledger, plan):
    block = plan["inventory"][0]
    rates, failures = {}, []
    # No pooling can hide a model/language failure behind easier cells.
    for model in MODELS:
        for language in protocol.LANGUAGES:
            for phase in ("sources", "finals"):
                selected = [s for s in block[phase] if s["model"] == model and s["language"] == language]
                good = sum(ledger.results["gen:" + s["id"]]["evaluated"].get("status") == "ok" for s in selected)
                rates[f"{model}:{language}:{phase}"] = {"complete": good, "planned": len(selected)}
                if Decimal(good) / len(selected) < Decimal("0.90"):
                    failures.append(f"{model}:{language}:{phase}")
    for s in block["finals"]:
        for p in JUDGES:
            for instrument in ("paper", "structured"):
                key = f"judge:{s['id']}:{p}:{instrument}"
                if ledger.results[key]["evaluated"]["status"] != "ok":
                    failures.append(key)
    return {"pass": not failures, "failures": failures, "completion": rates,
            "not_a_behavioral_effect_gate": True}


def execute(plan, plan_hash, freeze, root, qualification_hash, send, *, through_block=6):
    """Injected sender makes this routine fully offline-testable."""
    binding = {"plan_sha256": plan_hash, "freeze_commit": freeze, "hard_cap_usd": "60",
               "qualification_snapshot_sha256": qualification_hash}
    if not 1 <= through_block <= 6:
        raise ValueError("Block limit must lie in 1..6")
    with Ledger(root, binding) as ledger:
        audit(ledger, plan)
        stop = threading.Event()

        def call(key):
            if stop.is_set():
                raise Halted("Another worker stopped this batch")
            if key in ledger.results:
                return
            model, request, metadata = expected_call(key, plan, ledger.results)
            with ledger.mutex:
                if stop.is_set():
                    raise Halted("Another worker stopped this batch")
                try:
                    started = ledger.start(key, model, request, metadata)
                except Exception:
                    stop.set()
                    raise
            if started is None:
                return
            try:
                raw = send(MODELS[model]["provider"], request)
            except Exception as exc:
                ledger.finish(key, None, {"status": "transport_unknown", "fatal": True}, transport_error=type(exc).__name__)
                stop.set()
                raise Halted("Transport result uncertain; full reservation retained") from None
            item = None
            if metadata["phase"] == "judge":
                item = item_from_result(specs(plan)[metadata["item_id"]], ledger.results["gen:" + metadata["item_id"]])
            result = ledger.finish(key, raw, evaluate(model, raw, instrument=metadata.get("instrument"), item=item))
            if result["fatal"]:
                stop.set()
                raise Halted("Failed receipt/model/schema check; no retries")

        def batch(keys, workers):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(call, key) for key in keys]
                for future in futures:
                    future.result()
            audit(ledger, plan)

        for block in plan["inventory"][:through_block]:
            if block["block"] > 1:
                gate, forecast = technical_gate(ledger, plan), project_cost(ledger, plan)
                if not gate["pass"] or not forecast["pass"]:
                    raise Halted("Prebulk technical/cost gate failed; preserve partial inventory")
            batch(["gen:" + s["id"] for s in block["sources"]], 3)
            keys = []
            for spec in block["finals"]:
                key, dep = "gen:" + spec["id"], "gen:" + spec["source_id"]
                if ledger.results[dep]["evaluated"].get("missing", True):
                    ledger.missing(key, "missing_source", dep)
                else:
                    keys.append(key)
            batch(keys, 3)
            keys = []
            for spec in block["finals"]:
                dep = "gen:" + spec["id"]
                for p in JUDGES:
                    for instrument in ("paper", "structured"):
                        key = f"judge:{spec['id']}:{p}:{instrument}"
                        if ledger.results[dep]["evaluated"].get("missing", True):
                            ledger.missing(key, "missing_final", dep)
                        else:
                            keys.append(key)
            batch(keys, 4)
            gate = technical_gate(ledger, plan)
            forecast = project_cost(ledger, plan)
            ledger.append("projection", {"after_block": block["block"], "projection": forecast,
                                          "technical_gate": gate})
            if not gate["pass"] or not forecast["pass"]:
                raise Halted("Technical or budget forecast failed; do not expand the pilot")
        result = audit(ledger, plan, require_complete=through_block == 6)
        if result["complete"]:
            ledger.append("complete", result)
        return result


def verify_public(path, freeze):
    from experiments.instruction_state_qualification.controller import verify_ci

    relative = Path(path).resolve().relative_to(protocol.ROOT).as_posix()
    url = f"https://raw.githubusercontent.com/tdj28/llm_selfref_pre/{freeze}/{relative}"
    request = urllib.request.Request(url, headers={"User-Agent": "frontier-bilingual-b1/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.geturl() != url or hashlib.sha256(response.read()).hexdigest() != sha(path):
            raise ValueError("Prospective public plan unavailable or differs")
    return verify_ci(freeze)


def _write_once(path, value):
    raw = (canonical(value) + "\n").encode()
    no_symlinks(path)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Refusing to replace frozen runtime metadata")
    else:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--fixture-gate")
    parser.add_argument("--env-file")
    parser.add_argument("--approved-cap-usd", type=Decimal)
    parser.add_argument("--approval-ref")
    parser.add_argument("--through-block", type=int, default=6, choices=range(1, 7))
    args = parser.parse_args()
    plan = protocol.load_plan(args.plan, args.freeze)
    if not args.execute:
        print(canonical({"offline": True, "plan_sha256": sha(args.plan), "counts": plan["counts"], "cap_usd": "60"}))
        return
    if args.approved_cap_usd != Decimal("60") or not args.approval_ref:
        parser.error("Live execution requires the separate $60 approval and its reference")
    verify_public(args.plan, args.freeze)
    b1_path = protocol.ROOT / plan["b1_plan"]["path"]
    verify_public(b1_path, args.freeze)
    root = protocol.ROOT / protocol.LIVE_ROOT
    no_symlinks(root)
    ignored = subprocess.run(["git", "check-ignore", "--quiet", str(root / "events.jsonl")], cwd=protocol.ROOT)
    if ignored.returncode:
        raise ValueError("Canonical live ledger must be gitignored")
    root.mkdir(parents=True, exist_ok=True)
    snapshot_path = root / "qualification.json"
    no_symlinks(snapshot_path)
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text())
    else:
        if not args.fixture_gate:
            parser.error("New B1 --fixture-gate over the A1 prefix required on first execution")
        snapshot = qualification.capture(args.fixture_gate, plan, args.freeze)
        _write_once(snapshot_path, snapshot)
    qualified = qualification.verify_snapshot(snapshot, plan, args.freeze)
    _write_once(root / "approval.json", {"cap_usd": "60", "approval_ref": args.approval_ref,
               "plan_sha256": sha(args.plan), "freeze_commit": args.freeze})
    import importlib.metadata
    _write_once(root / "environment.json", {"python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: importlib.metadata.version(p) for p in ("openai", "anthropic", "numpy", "python-dotenv")}})
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    result = execute(plan, sha(args.plan), args.freeze, root, qualified["snapshot_sha256"], live_sender(),
                     through_block=args.through_block)
    print(canonical(result))


if __name__ == "__main__":
    main()
