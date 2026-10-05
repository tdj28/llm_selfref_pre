"""Run the source-bound API panel with one durable shared spending ledger."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
import json
import os
from pathlib import Path
import platform
import subprocess
import threading

from . import analysis, judges, protocol
from .ledger import Ledger, Halted
from .providers import generation_request, live_sender, parse_result, receipt_cost, reservation


def canonical_run_root():
    common = Path(subprocess.check_output(["git", "rev-parse", "--git-common-dir"],
                                         cwd=protocol.ROOT, text=True).strip())
    return (protocol.ROOT / common).resolve().parent / protocol.LIVE_ROOT


def write_once(path, value):
    data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise Halted("Existing immutable artifact differs: " + path.name)
        return
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


class Runner:
    def __init__(self, plan, freeze, plan_hash, ledger, sender=None):
        self.plan, self.freeze, self.plan_hash = plan, freeze, plan_hash
        self.ledger, self.sender = ledger, sender
        self.stop = threading.Event()
        self.catalog = {s["id"]: s for phase in ("screen", "main")
                        for block in plan[phase] for kind in ("sources", "finals") for s in block[kind]}
        self.fixtures = {i["id"]: i for i in plan["fixtures"]}

    def parsed_call(self, call_id, spec):
        row = self.ledger.existing(call_id)
        if row is None:
            return None
        if row["status"] != "settled":
            raise Halted("An unresolved call is retained; automatic resend is forbidden")
        return parse_result(spec, row["raw"])

    def call(self, call_id, spec, request, phase, metadata):
        metadata = {**metadata, "freeze": self.freeze, "plan_sha256": self.plan_hash}
        existing = self.ledger.existing(call_id)
        if existing is not None:
            if existing["request"] != request or existing["metadata"] != metadata or existing["phase"] != phase:
                raise Halted("Existing call differs from its frozen request")
            return self.parsed_call(call_id, spec)
        if self.sender is None or self.stop.is_set():
            raise Halted("No dispatch permission")
        self.ledger.reserve(call_id, request, reservation(spec, request), phase, metadata)
        raw, cost = None, None
        try:
            raw = self.sender(request)
            cost = receipt_cost(spec, raw)
            if cost is None:
                raise Halted("Usage unavailable")
            result = parse_result(spec, raw)
        except Exception as error:
            if raw is None and getattr(error, "status_code", None) is not None:
                raw = {"transport_status_code": error.status_code}
            self.ledger.settle(call_id, raw, cost, error=error)
            self.stop.set()
            raise Halted("Transport, identity or accounting failure; raw receipt retained") from None
        self.ledger.settle(call_id, raw, cost)
        return result

    def judge(self, item_id, response, judge, instrument, phase):
        spec = self.plan["judges"][judge]
        request = judges.judge_request(spec, instrument, response)
        for attempt in range(2):
            call_id = f"judge:{item_id}:{judge}:{instrument}:a{attempt}"
            result = self.call(call_id, spec, request, phase,
                               {"kind": "judge", "item_id": item_id, "judge": judge,
                                "instrument": instrument, "attempt": attempt,
                                "response_sha256": protocol.digest(response)})
            if not result["complete"] or result["missing"]:
                return {"item_id": item_id, "judge": judge, "instrument": instrument,
                        "status": "incomplete_judge", "raw_text": result["response"]}
            try:
                parsed = judges.parse(instrument, response, result["response"])
                return {"item_id": item_id, "judge": judge, "instrument": instrument,
                        "status": "ok", "raw_text": result["response"], **parsed}
            except (ValueError, TypeError, KeyError):
                if attempt == 1:
                    return {"item_id": item_id, "judge": judge, "instrument": instrument,
                            "status": "invalid_judge", "raw_text": result["response"]}
        raise AssertionError("Unreachable")

    def route_fixture(self, model):
        spec = self.plan["models"][model]
        request = generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}], max_tokens=4096)
        result = self.call(f"route:{model}", spec, request, "fixtures", {"kind": "route", "model": model})
        return {"model": model, "pass": result["complete"] and result["response"].strip() == "OK", **result}

    def fixture_rows(self):
        rows = []
        for item in self.plan["fixtures"]:
            for judge in self.plan["judges"]:
                for instrument in judges.INSTRUMENTS:
                    rows.append(self.judge(item["id"], item["response"], judge, instrument, "fixtures"))
        return rows

    def run_fixtures(self):
        self.require_resolved()
        with ThreadPoolExecutor(max_workers=12) as pool:
            route_jobs = [pool.submit(self.route_fixture, m) for m in self.plan["models"]]
            jobs = [pool.submit(self.judge, i["id"], i["response"], j, instrument, "fixtures")
                    for i in self.plan["fixtures"] for j in self.plan["judges"] for instrument in judges.INSTRUMENTS]
            rows = [future.result() for future in jobs]
            routes = [future.result() for future in route_jobs]
        gate = judges.fixture_gate(rows)
        return {"pass": gate["pass"] and all(r["pass"] for r in routes),
                "judges": gate, "routes": routes, "rows": rows}

    def require_fixtures(self):
        # Reconstruct from raw receipts; a JSON pass flag is not execution permission.
        old_sender, self.sender = self.sender, None
        try:
            result = self.run_fixtures()
        finally:
            self.sender = old_sender
        if not result["pass"]:
            raise Halted("Synthetic fixture or routing qualification failed")
        return result

    def require_resolved(self):
        if any(row["status"] != "settled" or row.get("over_reservation") for row in self.ledger.rows()):
            raise Halted("Unresolved or over-reservation call blocks every new dispatch")

    def generate(self, spec, source=None):
        model = self.plan["models"][spec["model"]]
        request = generation_request(model, protocol.messages(spec, source), max_tokens=4096)
        return self.call("gen:" + spec["id"], model, request, spec["phase"],
                         {"kind": "generation", "item_id": spec["id"], "role": spec["kind"],
                          "model": spec["model"], "block": spec["block"]})

    def block(self, block, judge_pool):
        sources = {s["id"]: self.generate(s) for s in block["sources"]}
        pending = []
        for spec in block["finals"]:
            donor = sources[spec["source_id"]]
            if donor["missing"]:
                continue
            result = self.generate(spec, donor["response"])
            if not result["missing"]:
                for judge in self.plan["judges"]:
                    for instrument in judges.INSTRUMENTS:
                        pending.append(judge_pool.submit(self.judge, spec["id"], result["response"],
                                                         judge, instrument, spec["phase"]))
        for future in pending:
            future.result()
        print(protocol.canonical({"completed_block": block["block"], "model": block["model"],
                                  "phase": block["phase"], "cost_bound_usd": str(self.ledger.spent())}), flush=True)

    def run_blocks(self, phase, models=None, initial=False):
        self.require_resolved()
        self.require_fixtures()
        blocks = [b for b in self.plan[phase] if (models is None or b["model"] in models)
                  and (not initial or b["block"] <= 2)]
        with ThreadPoolExecutor(max_workers=12) as judge_pool, ThreadPoolExecutor(max_workers=12) as generation_pool:
            jobs = [generation_pool.submit(self.block, b, judge_pool) for b in blocks]
            try:
                for future in as_completed(jobs):
                    future.result()
            except BaseException:
                self.stop.set()
                for future in jobs:
                    future.cancel()
                raise

    def rows(self, phase, models=None):
        result = []
        for block in self.plan[phase]:
            if models is not None and block["model"] not in models:
                continue
            for spec in block["finals"]:
                call = self.ledger.existing("gen:" + spec["id"])
                parsed = None
                if call and call["status"] == "settled":
                    parsed = parse_result(self.plan["models"][spec["model"]], call["raw"])
                row = {**spec, "response": None if parsed is None or parsed["missing"] else parsed["response"],
                       "status": parsed["status"] if parsed else "not_generated", "labels": {},
                       "cap_hit": parsed["cap_hit"] if parsed else False}
                if row["response"] is not None:
                    for judge in self.plan["judges"]:
                        labels = {}
                        for instrument in judges.INSTRUMENTS:
                            for attempt in range(2):
                                raw = self.ledger.existing(f"judge:{spec['id']}:{judge}:{instrument}:a{attempt}")
                                if not raw or raw["status"] != "settled":
                                    continue
                                try:
                                    output = parse_result(self.plan["judges"][judge], raw["raw"])
                                    if not output["complete"] or output["missing"]:
                                        continue
                                    value = judges.parse(instrument, row["response"], output["response"])
                                    labels[instrument] = (value["reduced"]["paper_positive"] if instrument == "paper"
                                                          else value["reduced"])
                                    break
                                except (ValueError, TypeError, KeyError):
                                    continue
                        row["labels"][judge] = labels
                result.append(row)
        return result

    def audit(self):
        """Independently rebuild every paid request, source link and price bound."""
        rows = self.ledger.rows()
        for row in rows:
            meta = row["metadata"]
            if meta["freeze"] != self.freeze or meta["plan_sha256"] != self.plan_hash:
                raise Halted("Receipt binding mismatch")
            kind = meta["kind"]
            if kind == "generation":
                item = self.catalog[meta["item_id"]]
                spec = self.plan["models"][item["model"]]
                expected_id, expected_phase = "gen:" + item["id"], item["phase"]
                expected_meta = {"kind": kind, "item_id": item["id"], "role": item["kind"],
                                 "model": item["model"], "block": item["block"]}
                donor = None
                if item["kind"] == "final":
                    source = self.parsed_call("gen:" + item["source_id"], spec)
                    if source is None or source["missing"]:
                        raise Halted("Paid final has missing donor")
                    donor = source["response"]
                expected = generation_request(spec, protocol.messages(item, donor), max_tokens=4096)
            elif kind == "judge":
                spec = self.plan["judges"][meta["judge"]]
                if type(meta["attempt"]) is not int or meta["attempt"] not in (0, 1):
                    raise Halted("Unapproved judge attempt")
                expected_id = f"judge:{meta['item_id']}:{meta['judge']}:{meta['instrument']}:a{meta['attempt']}"
                if meta["item_id"] in self.fixtures:
                    response = self.fixtures[meta["item_id"]]["response"]
                    expected_phase = "fixtures"
                else:
                    item = self.catalog[meta["item_id"]]
                    if item["kind"] != "final":
                        raise Halted("Source continuations are not judge targets")
                    expected_phase = item["phase"]
                    response = self.parsed_call("gen:" + item["id"], self.plan["models"][item["model"]])["response"]
                if protocol.digest(response) != meta["response_sha256"]:
                    raise Halted("Judge received different response text")
                expected_meta = {"kind": kind, "item_id": meta["item_id"], "judge": meta["judge"],
                                 "instrument": meta["instrument"], "attempt": meta["attempt"],
                                 "response_sha256": protocol.digest(response)}
                if meta["attempt"] == 1:
                    prior = self.parsed_call(expected_id[:-1] + "0", spec)
                    if prior is None:
                        raise Halted("Judge retry lacks a prior receipt")
                    if not prior["complete"] or prior["missing"]:
                        raise Halted("Capped, refused or missing judge output was retried")
                    try:
                        judges.parse(meta["instrument"], response, prior["response"])
                    except (ValueError, TypeError, KeyError):
                        pass
                    else:
                        raise Halted("A valid judgment was retried")
                expected = judges.judge_request(spec, meta["instrument"], response)
            elif kind == "route":
                spec = self.plan["models"][meta["model"]]
                expected_id, expected_phase = "route:" + meta["model"], "fixtures"
                expected_meta = {"kind": kind, "model": meta["model"]}
                expected = generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}], max_tokens=4096)
            else:
                raise Halted("Unknown paid request kind")
            expected_meta.update(freeze=self.freeze, plan_sha256=self.plan_hash)
            if row["call_id"] != expected_id or row["phase"] != expected_phase or meta != expected_meta:
                raise Halted("Receipt identity, phase or metadata does not reconstruct")
            if row["request"] != expected or Decimal(row["reservation_usd"]) != reservation(spec, expected):
                raise Halted("Paid request or reservation does not reconstruct")
            if row["status"] == "settled":
                parse_result(spec, row["raw"])
                if Decimal(row["cost_usd"]) != receipt_cost(spec, row["raw"]):
                    raise Halted("Price bound does not reconstruct")
        return {"pass": True, "calls": len(rows), "cost_bound_usd": str(self.ledger.spent()),
                "unresolved": sum(r["status"] != "settled" for r in rows),
                "unknown_charges_are_reserved": True}

    def main_admission(self):
        qualification = analysis.qualify(self.rows("screen"))
        if not qualification["inventory_valid"]:
            raise Halted("Screen inventory failed")
        paid = self.ledger.rows()
        if any(r["status"] != "settled" for r in paid):
            raise Halted("Unresolved charge blocks main collection")
        def mean_cost(predicate):
            costs = [Decimal(r["cost_usd"]) for r in paid if predicate(r["metadata"]) and r["phase"] == "screen"]
            if not costs:
                raise Halted("No observed cost basis")
            return sum(costs) / len(costs)
        screen_cost = sum((Decimal(r["cost_usd"]) for r in paid if r["phase"] != "main"), Decimal(0))
        available = Decimal(self.plan["cap_usd"]) - screen_cost
        projections, admitted = {}, []
        for model in self.plan["projection"]["main_cost_priority"]:
            if model not in qualification["eligible_models"]:
                projections[model] = {"status": "not_qualified"}
                continue
            source = mean_cost(lambda m: m["kind"] == "generation" and m["model"] == model and m["role"] == "source")
            final = mean_cost(lambda m: m["kind"] == "generation" and m["model"] == model and m["role"] == "final")
            judging = Decimal(0)
            for judge in self.plan["judges"]:
                for instrument in judges.INSTRUMENTS:
                    # Sum retry charges per planned item, not per successful attempt.
                    charges = [r for r in paid if r["phase"] == "screen" and r["metadata"]["kind"] == "judge"
                               and r["metadata"]["judge"] == judge and r["metadata"]["instrument"] == instrument
                               and self.catalog[r["metadata"]["item_id"]]["model"] == model]
                    items = {r["metadata"]["item_id"] for r in charges}
                    if not items:
                        raise Halted("No judge cost basis")
                    judging += sum(Decimal(r["cost_usd"]) for r in charges) / len(items)
            forecast = Decimal("1.30") * (128 * source + 256 * (final + judging))
            fits = forecast <= available
            projections[model] = {"status": "admitted" if fits else "not_run_budget",
                                  "projected_cost_with_reserve_usd": str(forecast)}
            if fits:
                admitted.append(model)
                available -= forecast
        return {"eligible_models": qualification["eligible_models"], "admitted_models": admitted,
                "projections": projections, "remaining_unallocated_usd": str(available),
                "cost_at_admission_usd": str(screen_cost)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=protocol.PLAN)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--run-dir", help="Offline audit copy only; paid work uses the shared canonical ledger")
    parser.add_argument("--phase", choices=("fixtures", "screen-initial", "screen", "main", "audit"), default="audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    path = protocol.ROOT / args.plan
    plan = protocol.verify(path, args.freeze)
    root = (protocol.ROOT / args.run_dir).resolve() if args.run_dir else canonical_run_root()
    sender = None
    if args.execute:
        if root != canonical_run_root():
            raise Halted("Paid execution must use the single canonical study ledger")
        if args.env_file:
            from dotenv import load_dotenv
            load_dotenv(args.env_file, override=False)
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise Halted("OpenRouter credential absent")
        sender = live_sender(key)
    elif args.phase != "audit":
        raise Halted("Paid work requires explicit --execute")
    write_once(root / "runtime.json", {"freeze": args.freeze, "plan_sha256": protocol.sha(path),
                                      "python": platform.python_version(), "platform": platform.platform(),
                                      "authorization_cap_usd": "250", "screen_cap_usd": "40"})
    with Ledger(root / "raw", cap="250", screen_cap="40") as ledger:
        runner = Runner(plan, args.freeze, protocol.sha(path), ledger, sender)
        if args.phase == "fixtures":
            gate = runner.run_fixtures()
            write_once(root / "fixture_gate.json", gate)
            if not gate["pass"]:
                raise Halted("Fixture gate failed; no target dispatch")
        elif args.phase in {"screen-initial", "screen"}:
            runner.run_blocks("screen", initial=args.phase == "screen-initial")
        elif args.phase == "main":
            admission = root / "main_admission.json"
            if admission.exists():
                selection = json.loads(admission.read_text())
                if selection != runner.main_admission():
                    raise Halted("Stored admission differs from reconstruction")
            else:
                selection = runner.main_admission()
                write_once(admission, selection)
            runner.run_blocks("main", models=selection["admitted_models"])
        report = runner.audit()
        snapshot = root / "snapshots" / f"{len(ledger.rows()):06d}"
        write_once(snapshot / "audit.json", report)
        for phase in ("screen", "main"):
            selection = root / "main_admission.json"
            admitted = json.loads(selection.read_text())["admitted_models"] if phase == "main" and selection.exists() else []
            rows = runner.rows(phase, None if phase == "screen" else admitted)
            write_once(snapshot / f"{phase}_rows.json", rows)
            write_once(snapshot / f"{phase}_analysis.json", analysis.analyze(rows, phase))
            if phase == "screen":
                write_once(snapshot / "qualification.json", analysis.qualify(rows))
        print(protocol.canonical(report), flush=True)


if __name__ == "__main__":
    main()
