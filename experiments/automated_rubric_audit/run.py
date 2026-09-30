"""Budgeted, append-only execution of the frozen two-provider rubric audit."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .common import (BASE, CAPS, MODELS, PRICES, ROOT, SCHEMA, canonical, digest,
                     read_jsonl, reduce_label, sha, validate_label, write_json)


def now():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_plan(base, freeze):
    plan_path = base / "plan.json"
    plan = json.loads(plan_path.read_text())
    if sha(plan_path) != json.loads((base / "plan_hash.json").read_text())["sha256"]:
        raise ValueError("Plan hash mismatch")
    for path, expected in {**plan["source_hashes"], **plan["implementation_hashes"]}.items():
        if sha(ROOT / path) != expected:
            raise ValueError("Frozen file changed: " + path)
        committed = subprocess.check_output(["git", "show", f"{freeze}:{path}"], cwd=ROOT)
        import hashlib
        if hashlib.sha256(committed).hexdigest() != expected:
            raise ValueError("Freeze source mismatch: " + path)
    committed = subprocess.check_output(["git", "show", f"{freeze}:{plan_path.relative_to(ROOT)}"], cwd=ROOT)
    import hashlib
    if hashlib.sha256(committed).hexdigest() != sha(plan_path):
        raise ValueError("Plan is not in the freeze commit")
    remote = git("ls-remote", "origin", "refs/heads/main").split()[0]
    subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote], cwd=ROOT, check=True)
    return plan


def make_request(provider, item, plan):
    system = (ROOT / "experiments/automated_rubric_audit/rubric.md").read_text()
    content = canonical({"query": item["query"], "response": item["response"]})
    if provider == "openai":
        return {"model": MODELS[provider], "instructions": system, "input": content,
                "reasoning": {"effort": plan["reasoning_effort"]}, "store": False,
                "service_tier": "default", "max_output_tokens": plan["max_output_tokens"],
                "text": {"format": {"type": "json_schema", "name": "linguistic_audit",
                                     "strict": True, "schema": SCHEMA}}}
    return {"model": MODELS[provider], "system": system,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": plan["max_output_tokens"],
            "extra_body": {"output_config": {"effort": plan["reasoning_effort"],
                                               "format": {"type": "json_schema", "schema": SCHEMA}}}}


def reservation(provider, request):
    inputs = len(canonical(request).encode()) + 4096
    outputs = request.get("max_output_tokens", request.get("max_tokens"))
    a, b = PRICES[provider]
    return (inputs * a + outputs * b) / 1_000_000


def usage_cost(provider, raw):
    usage = raw.get("usage") or {}
    inp, out = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(inp, int) or not isinstance(out, int) or min(inp, out) < 0:
        raise ValueError("Missing or invalid usage")
    a, b = PRICES[provider]
    # Conservative upper bound: do not credit cache-read discounts.
    inp += usage.get("cache_read_input_tokens", 0)
    inp += 1.25 * usage.get("cache_creation_input_tokens", 0)
    return (inp * a + out * b) / 1_000_000


def extract(provider, raw):
    if provider == "openai":
        if raw.get("status") != "completed":
            raise ValueError("Incomplete provider response")
        return "".join(c.get("text", "") for o in raw.get("output", [])
                       if o.get("type") == "message" for c in o.get("content", [])
                       if c.get("type") == "output_text")
    if raw.get("stop_reason") != "end_turn":
        raise ValueError("Incomplete provider response")
    return "".join(c["text"] for c in raw.get("content", []) if c.get("type") == "text")


def model_matches(provider, model):
    import re
    return model == MODELS[provider] or bool(re.fullmatch(re.escape(MODELS[provider]) + r"-20[0-9-]+", model or ""))


def validate_state(base, plan, freeze):
    """Reject corrupt or stale durable state before any resume dispatch."""
    requests = read_jsonl(base / "requests.jsonl")
    attempts = read_jsonl(base / "attempts.jsonl")
    judgments = read_jsonl(base / "judgments.jsonl")
    for rows, key in [(requests, "attempt_id"), (attempts, "attempt_id"), (judgments, "judgment_id")]:
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError("Duplicate durable ledger identities")
    req = {r["attempt_id"]: r for r in requests}
    att = {r["attempt_id"]: r for r in attempts}
    if set(req) != set(att):
        raise ValueError("Unknown in-flight or unmatched attempts require documented recovery")
    models = {p: set() for p in MODELS}
    for aid, start in req.items():
        phase, provider, identifier, number = aid.split(":")
        if phase not in {"pilot", "target"} or provider not in MODELS or number not in {"0", "1"}:
            raise ValueError("Unexpected durable attempt identity")
        item = next(r for r in plan["pilot" if phase == "pilot" else "targets"] if r["annotation_id"] == identifier)
        expected = make_request(provider, item, plan)
        row = att[aid]
        for record in [start, row]:
            if (record["request"] != expected or record["request_sha256"] != digest(expected)
                    or record["freeze_commit"] != freeze or record["plan_sha256"] != sha(base / "plan.json")
                    or record["judgment_id"] != f"{phase}:{provider}:{identifier}"
                    or record["phase"] != phase or record["provider"] != provider
                    or record["annotation_id"] != identifier or record["model"] != MODELS[provider]
                    or record["reservation_usd"] != reservation(provider, expected)):
                raise ValueError("Durable request provenance mismatch")
        raw = row.get("raw_response")
        cost = usage_cost(provider, raw) if raw and raw.get("usage") else start["reservation_usd"]
        if abs(cost - row["cost_usd"]) > 1e-10 or cost > start["reservation_usd"]:
            raise ValueError("Durable budget contract violation")
        if raw:
            if not model_matches(provider, raw.get("model")):
                raise ValueError("Durable model contract violation")
            models[provider].add(raw["model"])
        if row["status"] == "ok":
            label = validate_label(json.loads(extract(provider, raw)), item["response"])
            if label != row["label"] or reduce_label(label) != row["derived"]:
                raise ValueError("Durable label mismatch")
        elif row["status"] not in {"invalid", "transport_error"}:
            raise ValueError("Invalid durable status")
    if any(len(s) > 1 for s in models.values()):
        raise ValueError("Durable model snapshot changed")
    for row in judgments:
        last = att[row["attempt_id"]]
        if any(row[k] != last[k] for k in last if k != "cost_usd"):
            raise ValueError("Final judgment differs from terminal attempt")
        total = sum(r["cost_usd"] for r in attempts if r["judgment_id"] == row["judgment_id"])
        if abs(total - row["cost_usd"]) > 1e-10:
            raise ValueError("Final judgment cost mismatch")
    ledger = Ledger(base)
    if any(ledger.spent(p) > CAPS[p] or ledger.halted[p] for p in MODELS):
        raise ValueError("Persisted budget or provider failure gate")


class Ledger:
    def __init__(self, base):
        self.base = base
        self.lock = threading.RLock()
        self.started = {r["attempt_id"]: r for r in read_jsonl(base / "requests.jsonl")}
        self.finished = {r["attempt_id"]: r for r in read_jsonl(base / "attempts.jsonl")}
        self.failures = {p: 0 for p in MODELS}
        self.halted = {p: False for p in MODELS}
        final_attempts = {}
        for row in self.finished.values():
            final_attempts[row.get("judgment_id", row["attempt_id"])] = row["attempt_id"]
        for row in self.finished.values():
            if final_attempts[row.get("judgment_id", row["attempt_id"])] != row["attempt_id"]:
                continue
            if "provider" not in row:
                continue
            p = row["provider"]
            self.failures[p] = self.failures[p] + 1 if row["status"] == "transport_error" else 0
            self.halted[p] |= self.failures[p] >= 3

    def rows(self, name):
        with self.lock:
            return read_jsonl(self.base / name)

    def record_failure(self, provider, failed):
        with self.lock:
            self.failures[provider] = self.failures[provider] + 1 if failed else 0
            self.halted[provider] |= self.failures[provider] >= 3
            return self.failures[provider]

    def append(self, name, row):
        with self.lock:
            self._append(name, row)

    def _append(self, name, row):
        with (self.base / name).open("a") as handle:
            handle.write(canonical(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def spent(self, provider):
        with self.lock:
            return sum(self.finished.get(k, {}).get("cost_usd", row["reservation_usd"])
                       for k, row in self.started.items() if row["provider"] == provider)

    def start(self, row):
        with self.lock:
            if row["attempt_id"] in self.started:
                raise ValueError("Attempt already dispatched; refusing duplicate")
            if self.spent(row["provider"]) + row["reservation_usd"] > CAPS[row["provider"]]:
                raise ValueError("Provider budget reservation would exceed cap")
            self._append("requests.jsonl", row)
            self.started[row["attempt_id"]] = row

    def finish(self, row):
        with self.lock:
            self._append("attempts.jsonl", row)
            self.finished[row["attempt_id"]] = row


def pilot_gate(base, plan):
    rows = [r for r in read_jsonl(base / "judgments.jsonl") if r["phase"] == "pilot"]
    expected = {r["annotation_id"]: r for r in plan["pilot"]}
    report = {"pass": True, "providers": {}}
    for provider in MODELS:
        selected = [r for r in rows if r["provider"] == provider]
        if len({r["annotation_id"] for r in selected}) != len(selected):
            raise ValueError("Duplicate pilot judgments")
        passed = []
        for row in selected:
            item = expected[row["annotation_id"]]
            if row["status"] == "ok":
                derived = reduce_label(validate_label(row["label"], item["response"]))
                if all(derived[k] == v for k, v in item["expected"].items()):
                    passed.append(row["annotation_id"])
        gate = (len(selected) == len(expected) and all(r["status"] == "ok" for r in selected)
                and len(passed) >= plan["pilot_gate_min_correct_per_model"]
                and set(plan["pilot_critical_ids"]) <= set(passed))
        avg = sum(r["cost_usd"] for r in selected) / len(selected) if selected else 0
        spent = Ledger(base).spent(provider)
        projected = spent + avg * len(plan["targets"]) * 1.25
        gate = gate and projected <= CAPS[provider]
        report["providers"][provider] = {"pass": gate, "n": len(selected), "correct": len(passed),
                                          "passed_ids": passed, "projected_usd_with_25pct_margin": projected}
        report["pass"] &= gate
    return report


def run_provider(provider, phase, plan, base, freeze, ledger, stop, shard=0):
    from openai import OpenAI
    from anthropic import Anthropic
    client = (OpenAI(max_retries=0, timeout=180) if provider == "openai"
              else Anthropic(max_retries=0, timeout=180))
    done = {r["judgment_id"] for r in ledger.rows("judgments.jsonl")}
    rows = plan["pilot"] if phase == "pilot" else plan["targets"]
    rows = rows[shard::plan["workers_per_provider"]]
    for item in rows:
        if stop.is_set():
            return
        if ledger.halted[provider]:
            raise ValueError("Persisted provider failure gate requires documented recovery")
        jid = f"{phase}:{provider}:{item['annotation_id']}"
        if jid in done:
            continue
        request = make_request(provider, item, plan)
        reserve = reservation(provider, request)
        base_row = {"judgment_id": jid, "phase": phase, "provider": provider,
                    "model": MODELS[provider], "annotation_id": item["annotation_id"],
                    "freeze_commit": freeze, "plan_sha256": sha(base / "plan.json"),
                    "request_sha256": digest(request)}
        previous = [r for r in ledger.rows("attempts.jsonl") if r["judgment_id"] == jid]
        started = [r for r in ledger.rows("requests.jsonl") if r["judgment_id"] == jid]
        if started:
            # Preserve completed-but-not-promoted responses; never pay twice on resume.
            if len(started) != len(previous):
                raise ValueError("Unknown in-flight request: manual recovery required; no automatic replay")
            final = previous[-1]
            ledger.append("judgments.jsonl", {**final, "cost_usd": sum(r["cost_usd"] for r in previous)})
            continue
        attempts = []
        for attempt in range(2):
            if stop.is_set():
                if attempts:
                    break
                return
            start = {**base_row, "attempt_id": f"{jid}:{attempt}", "started_at_utc": now(),
                     "reservation_usd": reserve, "request": request}
            ledger.start(start)
            raw = None
            cost = reserve
            status = "transport_error"
            label = derived = None
            http_status = None
            error_type = None
            prior_models = set()
            try:
                response = (client.responses.create(**request) if provider == "openai"
                            else client.messages.create(**request))
                raw = response.model_dump(mode="json", exclude_none=True)
                cost = usage_cost(provider, raw)
                status = "invalid"
                prior_models = {r["raw_response"]["model"] for r in ledger.rows("attempts.jsonl")
                                if r["provider"] == provider and r.get("raw_response")}
                if not model_matches(provider, raw.get("model")) or (prior_models and prior_models != {raw.get("model")}):
                    raise ValueError("Unexpected returned model")
                text = extract(provider, raw)
                label = validate_label(json.loads(text), item["response"])
                derived = reduce_label(label)
                status = "ok"
            except Exception as exc:
                error_type = type(exc).__name__
                http_status = getattr(exc, "status_code", None)
                # Do not serialize exception strings, headers, clients or credentials.
            row = {**start, "completed_at_utc": now(), "status": status, "label": label,
                   "derived": derived, "raw_response": raw, "cost_usd": cost,
                   "cost_basis": "uncached_usage_upper_bound" if raw else "unknown_usage_reserved",
                   "error_type": error_type, "http_status": http_status}
            ledger.finish(row)
            attempts.append(row)
            model_changed = raw and (not model_matches(provider, raw.get("model"))
                                     or (prior_models and prior_models != {raw.get("model")}))
            if cost > reserve or model_changed:
                stop.set()
                raise ValueError("Usage/model contract violation; stopping")
            if status == "transport_error" and http_status and (http_status == 429 or http_status >= 500) and attempt == 0:
                time.sleep(10)
                continue
            break
        final = {**attempts[-1], "cost_usd": sum(r["cost_usd"] for r in attempts)}
        ledger.append("judgments.jsonl", final)
        failures = ledger.record_failure(provider, final["status"] == "transport_error")
        print(f"{provider} {phase}: completed {item['annotation_id']} status={final['status']} "
              f"reserved/used upper bound=${ledger.spent(provider):.4f}", flush=True)
        if failures >= 3:
            stop.set()
            raise ValueError("Three consecutive provider transport failures")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pilot", "target"], required=True)
    parser.add_argument("--freeze", required=True)
    args = parser.parse_args()
    import fcntl
    lock_path = ROOT / "out/automated-rubric-v1.lock"
    lock_path.parent.mkdir(exist_ok=True)
    lock_handle = lock_path.open("a")
    fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = verify_plan(BASE, args.freeze)
    validate_state(BASE, plan, args.freeze)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    for name in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        if not os.environ.get(name):
            raise RuntimeError(name + " is unavailable")
    ledger = Ledger(BASE)
    if args.phase == "target":
        gate = pilot_gate(BASE, plan)
        write_json(BASE / "pilot_gate.json", gate)
        if not gate["pass"]:
            raise ValueError("Calibration gate failed; no target calls permitted")
    runtime_path = BASE / (args.phase + "_runtime.json")
    if not runtime_path.exists():
        write_json(runtime_path, {"started_at_utc": now(), "freeze_commit": args.freeze,
                                 "plan_sha256": sha(BASE / "plan.json"), "caps_usd": CAPS,
                                 "packages": {p: importlib.metadata.version(p) for p in ["openai", "anthropic", "httpx", "python-dotenv"]}})
    stop = threading.Event()
    workers = plan["workers_per_provider"]
    try:
        with ThreadPoolExecutor(max_workers=2 * workers) as pool:
            futures = [pool.submit(run_provider, p, args.phase, plan, BASE, args.freeze, ledger, stop, shard)
                       for p in MODELS for shard in range(workers)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    stop.set()
                    raise
    finally:
        from .progress import report_progress
        write_json(BASE / "progress.json", report_progress(BASE))
    if args.phase == "pilot":
        gate = pilot_gate(BASE, plan)
        write_json(BASE / "pilot_gate.json", gate)
        print("Pilot gate: " + str(gate["pass"]), flush=True)
        if not gate["pass"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
