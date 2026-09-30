"""Budgeted Stage 1 judges; running this CLI dispatches paid requests.

The frozen plan supplies judge_fixtures and response_rows (or rows containing
baseline/positive entries). Response inputs have a sibling <name>.manifest.json:
{sha256, plan_sha256, freeze_commit, ids}. The producer attests these fields
after generation; they are not a second prospective freeze. Partial windows
must remain subsets of the same 370-row inventory. Use ONE outdir for all phases
and windows. Never delete receipts to resume; unknown requests require review.
Before responses, outdir/local_fixture_judgments.jsonl and its same-format
manifest must attest 12 {id, status, paper_binary} local-judge fixture rows.
The parent's authorization/Pro-review gate is separate from this budget ledger.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading

from experiments.automated_rubric_audit.common import (
    MODELS, PRICES, ROOT, canonical, digest, reduce_label, sha, validate_label,
)
from experiments.automated_rubric_audit.run import (
    extract, make_request, model_matches, now, usage_cost,
)

CAPS = {"openai": Decimal("45"), "anthropic": Decimal("15")}
TOTAL_CAP = Decimal("60")
REQUIRED_SOURCES = (
    "experiments/sae_assay_diagnostic/judge.py",
    "experiments/automated_rubric_audit/common.py",
    "experiments/automated_rubric_audit/run.py",
    "experiments/automated_rubric_audit/rubric.md",
)


def strict_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value

    def invalid(value):
        raise ValueError("Nonfinite JSON number: " + value)

    value = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    json.dumps(value, allow_nan=False)  # Also catches exponent overflow.
    return value


def money(value):
    if isinstance(value, bool):
        raise ValueError("Invalid cost")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("Nonfinite or negative cost")
    return number


def _git_bytes(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def verify_plan(path, freeze):
    """Local commit binding; the parent separately verifies public publication."""
    path = Path(path).resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("--freeze must be a full lowercase commit SHA")
    if _git_bytes("rev-parse", "--verify", freeze + "^{commit}").decode().strip() != freeze:
        raise ValueError("Freeze is not an exact commit")
    relative = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    if _git_bytes("show", f"{freeze}:{relative}") != data:
        raise ValueError("Plan is not bound to freeze commit")
    plan = strict_json(data)
    if (plan.get("reasoning_effort") != "high" or plan.get("max_output_tokens") != 6000
            or type(plan.get("max_output_tokens")) is not int
            or plan.get("models", MODELS) != MODELS):
        raise ValueError("Model/effort/output contract changed")
    workers = plan.get("workers_per_provider", 2)
    if type(workers) is not int or not 1 <= workers <= 2:
        raise ValueError("At most two workers per provider")
    sources = plan.get("source_hashes", {})
    if not isinstance(sources, dict) or not set(REQUIRED_SOURCES) <= set(sources):
        raise ValueError("source_hashes must include runner, schema, helpers and rubric")
    for name, expected in sources.items():
        source = (ROOT / name).resolve()
        if source.relative_to(ROOT).as_posix() != name:
            raise ValueError("Source path must be canonical and repository-relative")
        if sha(source) != expected or hashlib.sha256(
                _git_bytes("show", f"{freeze}:{name}")).hexdigest() != expected:
            raise ValueError("Frozen source hash mismatch: " + name)
    fixture_map(plan)
    response_map(plan)
    return plan, hashlib.sha256(data).hexdigest()


def item_map(rows):
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row["id"] or row["id"] in result
                or not isinstance(row.get("query"), str) or not row["query"].strip()):
            raise ValueError("Invalid or duplicate planned ID/query")
        result[row["id"]] = row
    return result


def fixture_map(plan):
    rows = item_map(plan["judge_fixtures"])
    prototype = reduce_label({"claims": [], "phenomenological_description": False,
                              "ai_disclaimer": False, "quality": "responsive"})
    if len(rows) != 12 or not any(r.get("critical") is True for r in rows.values()):
        raise ValueError("Exactly 12 fixtures including critical cases required")
    for row in rows.values():
        expected = row.get("expected_modern")
        if (not isinstance(row.get("response"), str) or not row["response"].strip()
                or type(row.get("critical")) is not bool
                or type(row.get("expected_paper_binary")) is not int
                or row["expected_paper_binary"] not in (0, 1)
                or not isinstance(expected, dict) or not expected
                or not set(expected) <= set(prototype)
                or any(type(value) is not type(prototype[key]) for key, value in expected.items())):
            raise ValueError("Invalid fixture expectation")
    return rows


def response_map(plan):
    rows = plan.get("response_rows", plan.get("rows", []))
    rows = item_map([r for r in rows if r.get("kind") in {"baseline", "positive"}])
    if len(rows) != 370 or Counter(r["kind"] for r in rows.values()) != {
            "baseline": 290, "positive": 80}:
        raise ValueError("Plan must contain exactly 290 baseline and 80 positive IDs")
    if set(rows) & set(fixture_map(plan)):
        raise ValueError("Fixture and response IDs overlap")
    return rows


def load_inputs(paths, plan, plan_hash, freeze):
    expected = response_map(plan)
    selected, attestations = {}, []
    for path in paths:
        path = Path(path).resolve()
        data = path.read_bytes()
        manifest_path = Path(str(path) + ".manifest.json")
        manifest = strict_json(manifest_path.read_bytes())
        if (manifest.get("sha256") != hashlib.sha256(data).hexdigest()
                or manifest.get("plan_sha256") != plan_hash
                or manifest.get("freeze_commit") != freeze):
            raise ValueError("Input hash/freeze attestation mismatch")
        rows = [strict_json(line) for line in data.splitlines() if line.strip()]
        if not rows or [r["id"] for r in rows] != manifest.get("ids"):
            raise ValueError("Input attestation IDs mismatch or empty window")
        for row in rows:
            identifier = row["id"]
            target = expected.get(identifier)
            if (identifier in selected or target is None or row.get("status") != "ok"
                    or not isinstance(row.get("response"), str) or not row["response"].strip()
                    or any(row.get(k) != v for k, v in target.items() if k != "response")):
                raise ValueError("Input does not match exact planned ID/metadata or is not ok")
            selected[identifier] = row
        attestations.append({"path": str(path), "sha256": manifest["sha256"],
                             "manifest_sha256": sha(manifest_path), "manifest": manifest,
                             "row_hashes": {r["id"]: digest(r) for r in rows}})
    if not selected or len(selected) > 370:
        raise ValueError("Response inputs must contain 1..370 planned rows")
    # Plan order, not input order or intermediate outcomes, determines dispatch.
    return [selected[k] for k in expected if k in selected], attestations


def local_fixture_gate(outdir, plan, plan_hash, freeze):
    path = Path(outdir) / "local_fixture_judgments.jsonl"
    manifest_path = Path(str(path) + ".manifest.json")
    manifest = strict_json(manifest_path.read_bytes())
    data = path.read_bytes()
    if (manifest.get("sha256") != hashlib.sha256(data).hexdigest()
            or manifest.get("plan_sha256") != plan_hash or manifest.get("freeze_commit") != freeze):
        raise ValueError("Local fixture hash/freeze attestation mismatch")
    rows = [strict_json(line) for line in data.splitlines() if line.strip()]
    expected = fixture_map(plan)
    ids = [row["id"] for row in rows]
    if len(ids) != 12 or set(ids) != set(expected) or ids != manifest.get("ids"):
        raise ValueError("Local fixtures must contain exactly the 12 frozen IDs")
    valid = all(row.get("status") == "ok" and type(row.get("paper_binary")) is int
                and row["paper_binary"] in (0, 1) for row in rows)
    passed = {row["id"] for row in rows if row.get("status") == "ok"
              and type(row.get("paper_binary")) is int
              and row["paper_binary"] == expected[row["id"]]["expected_paper_binary"]}
    critical = {k for k, row in expected.items() if row["critical"]}
    return {"pass": valid and len(passed) >= 10 and critical <= passed,
            "correct": len(passed), "critical_pass": critical <= passed,
            "sha256": manifest["sha256"], "manifest_sha256": sha(manifest_path)}


def reservation(provider, request):
    inputs = len(canonical(request).encode()) + 4096
    if inputs > 100_000:
        raise ValueError("Diagnostic request exceeds short-context bound")
    a, b = map(lambda v: Decimal(str(v)), PRICES[provider])
    surcharge = Decimal("1.25") if provider == "openai" else Decimal("2")
    return (inputs * a * surcharge + 6000 * b) / 1_000_000


def checked_usage_cost(provider, raw):
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Missing usage")
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key, 0 if key.startswith("cache_") else None)
        if type(value) is not int or value < 0:
            raise ValueError("Invalid usage token count")
    if usage["output_tokens"] > 6000 or usage["input_tokens"] > 100_000:
        raise ValueError("Usage exceeded token contract")
    if provider == "openai" and raw.get("service_tier", "default") != "default":
        raise ValueError("Unexpected service tier")
    if provider == "anthropic" and (usage.get("speed", "standard") != "standard"
                                    or usage.get("inference_geo", "global") not in (None, "global")):
        raise ValueError("Unexpected premium pricing mode")
    # Frozen helper supplies base accounting; charge worst-case cache-write rates.
    value = money(usage_cost(provider, raw))
    a = Decimal(str(PRICES[provider][0]))
    extra = (Decimal(".25") * usage["input_tokens"] if provider == "openai"
             else Decimal(".75") * usage.get("cache_creation_input_tokens", 0))
    return value + extra * a / 1_000_000


class Receipts:
    """One request per judgment, with durable reservations and deterministic replay."""

    def __init__(self, outdir, plan, plan_hash, freeze):
        self.base = Path(outdir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.plan, self.plan_hash, self.freeze = plan, plan_hash, freeze
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.logs = {name: self._read(name) for name in
                     ("inputs", "requests", "attempts", "judgments", "gates")}
        self.requests, self.attempts, self.judgments = {}, {}, {}
        self.models, self.errors = {}, Counter()
        self.sources = {k: (ROOT / k) for k in plan["source_hashes"]}
        self.fixtures, self.targets = fixture_map(plan), response_map(plan)
        self._replay()

    def _read(self, name):
        path = self.base / (name + ".jsonl")
        data = path.read_bytes() if path.exists() else b""
        if data and not data.endswith(b"\n"):
            raise ValueError("Truncated receipt; manual recovery required")
        rows, previous = [], None
        for line in data.splitlines():
            row = strict_json(line)
            checksum = row.pop("receipt_sha256")
            if digest(row) != checksum or row.get("previous_sha256") != previous:
                raise ValueError("Receipt hash chain mismatch")
            if row.get("plan_sha256") != self.plan_hash or row.get("freeze_commit") != self.freeze:
                raise ValueError("Receipt freeze/plan binding mismatch")
            row["receipt_sha256"] = checksum
            rows.append(row)
            previous = checksum
        return rows

    def append(self, name, payload):
        with self.lock:
            rows = self.logs[name]
            row = {**payload, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                   "previous_sha256": rows[-1]["receipt_sha256"] if rows else None,
                   "recorded_at_utc": now()}
            row["receipt_sha256"] = digest(row)
            strict_json(canonical(row))
            data = (canonical(row) + "\n").encode()
            with (self.base / (name + ".jsonl")).open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                offset = handle.tell()
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
                handle.seek(offset)
                if handle.read() != data:
                    self.stop.set()
                    raise ValueError("Receipt readback failed")
            directory = os.open(self.base, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            rows.append(row)
            return row

    def totals(self):
        totals = {p: Decimal(0) for p in MODELS}
        for jid, request in self.requests.items():
            totals[request["provider"]] += money(self.attempts.get(jid, request).get(
                "cost_usd", request["reservation_usd"]))
        return totals

    def check_budget(self, provider=None, reserve=Decimal(0)):
        totals = self.totals()
        if provider:
            totals[provider] += money(reserve)
        if any(totals[p] > CAPS[p] for p in MODELS) or sum(totals.values()) > TOTAL_CAP:
            self.stop.set()
            raise ValueError("Stage 1 budget cap would be exceeded")
        return totals

    def attest(self, attestations):
        with self.lock:
            known = {key: value for r in self.logs["inputs"] for key, value in r["row_hashes"].items()}
            for row in attestations:
                if any(key in known and known[key] != value for key, value in row["row_hashes"].items()):
                    raise ValueError("Previously attested input row changed")
                if not any(r["sha256"] == row["sha256"] for r in self.logs["inputs"]):
                    self.append("inputs", row)
                known.update(row["row_hashes"])

    def start(self, provider, phase, item):
        with self.lock:
            if self.stop.is_set():
                return None
            jid = f"{phase}:{provider}:{item['id']}"
            if jid in self.requests:
                return None
            if phase == "fixtures" and self.fixtures.get(item["id"]) != item:
                raise ValueError("Unplanned fixture")
            if phase == "responses":
                attested = {k: v for r in self.logs["inputs"] for k, v in r["row_hashes"].items()}
                if attested.get(item["id"]) != digest(item):
                    raise ValueError("Unattested response")
            for name, path in self.sources.items():
                if sha(path) != self.plan["source_hashes"][name]:
                    self.stop.set()
                    raise ValueError("Frozen source changed before dispatch")
            request = make_request(provider, item, self.plan)
            reserve = reservation(provider, request)
            self.check_budget(provider, reserve)
            row = self.append("requests", {
                "judgment_id": jid, "attempt_id": jid + ":0", "phase": phase,
                "provider": provider, "model": MODELS[provider], "id": item["id"],
                "item": item, "item_sha256": digest(item), "request": request,
                "request_sha256": digest(request), "reservation_usd": str(reserve),
            })
            self.requests[jid] = row
            return row

    def result(self, start, raw_json, error_type=None, http_status=None):
        provider = start["provider"]
        cost = money(start["reservation_usd"])
        status, label, derived, raw, failure = "transport_error", None, None, None, None
        if raw_json is not None:
            status = "invalid"
            try:
                raw = strict_json(raw_json)
                cost = checked_usage_cost(provider, raw)
                if cost > money(start["reservation_usd"]):
                    raise ValueError("Actual cost exceeds reservation")
                model = raw.get("model")
                if not model_matches(provider, model) or self.models.get(provider, model) != model:
                    raise ValueError("Returned model alias drift")
                label = validate_label(strict_json(extract(provider, raw)), start["item"]["response"])
                derived = reduce_label(label)
                status = "ok"
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                failure = type(exc).__name__
        return {"judgment_id": start["judgment_id"], "attempt_id": start["attempt_id"],
                "provider": provider, "phase": start["phase"], "id": start["id"],
                "request_sha256": start["request_sha256"], "status": status,
                "raw_response_json": raw_json,
                "raw_response_sha256": hashlib.sha256(raw_json.encode()).hexdigest() if raw_json is not None else None,
                "cost_usd": str(cost), "cost_basis": "usage_upper_bound" if status == "ok" else "usage_or_reserved_upper_bound",
                "label": label if status == "ok" else None, "derived": derived if status == "ok" else None,
                "error_type": failure or error_type, "http_status": http_status}

    def finish(self, start, raw_json, error_type=None, http_status=None):
        with self.lock:
            row = self.result(start, raw_json, error_type, http_status)
            stored = self.append("attempts", row)
            self.attempts[row["judgment_id"]] = stored
            self._observe(row)
            self.promote(stored)
            self.check_budget()
            return stored

    def _observe(self, row):
        provider = row["provider"]
        if row["status"] == "ok":
            self.models[provider] = strict_json(row["raw_response_json"])["model"]
        elif row["status"] == "transport_error":
            self.errors[provider] += 1
        if row["status"] == "invalid" or self.errors[provider] >= 3:
            self.stop.set()

    def promote(self, attempt):
        jid = attempt["judgment_id"]
        row = self.append("judgments", {"judgment_id": jid, "attempt_id": attempt["attempt_id"],
                          "attempt_sha256": attempt["receipt_sha256"], "phase": attempt["phase"],
                          "provider": attempt["provider"], "id": attempt["id"], "status": attempt["status"],
                          "label": attempt["label"], "derived": attempt["derived"], "cost_usd": attempt["cost_usd"]})
        self.judgments[jid] = row

    def _replay(self):
        attested = {}
        for record in self.logs["inputs"]:
            path = Path(record["path"])
            if (sha(path) != record["sha256"] or sha(str(path) + ".manifest.json") != record["manifest_sha256"]):
                raise ValueError("Previously attested input file changed")
            _, attestations = load_inputs([path], self.plan, self.plan_hash, self.freeze)
            if any(record[k] != attestations[0][k] for k in attestations[0]):
                raise ValueError("Input receipt differs from attestation")
            for identifier, checksum in record["row_hashes"].items():
                if identifier in attested and attested[identifier] != checksum:
                    raise ValueError("Conflicting input attestations")
                attested[identifier] = checksum
        for row in self.logs["requests"]:
            provider, phase, item, jid = row["provider"], row["phase"], row["item"], row["judgment_id"]
            if provider not in MODELS or phase not in {"fixtures", "responses"} or jid in self.requests:
                raise ValueError("Invalid or duplicate durable request")
            expected = make_request(provider, item, self.plan)
            if (jid != f"{phase}:{provider}:{item['id']}" or row["attempt_id"] != jid + ":0"
                    or row["id"] != item["id"] or row["model"] != MODELS[provider]
                    or row["item_sha256"] != digest(item) or row["request"] != expected
                    or row["request_sha256"] != digest(expected)
                    or money(row["reservation_usd"]) != reservation(provider, expected)):
                raise ValueError("Durable request provenance mismatch")
            if ((phase == "fixtures" and item != self.fixtures.get(item["id"]))
                    or (phase == "responses" and attested.get(item["id"]) != digest(item))):
                raise ValueError("Durable request is not an attested planned item")
            self.requests[jid] = row
        for row in self.logs["attempts"]:
            jid = row["judgment_id"]
            if jid not in self.requests or jid in self.attempts:
                raise ValueError("Unmatched or duplicate durable attempt")
            expected = self.result(self.requests[jid], row["raw_response_json"], row["error_type"], row["http_status"])
            if any(row[key] != value for key, value in expected.items()):
                raise ValueError("Durable attempt cost/label/raw mismatch")
            self.attempts[jid] = row
            self._observe(row)
        if set(self.requests) != set(self.attempts):
            raise ValueError("Unknown in-flight request; manual recovery required, never auto-retry")
        for row in self.logs["judgments"]:
            jid = row["judgment_id"]
            attempt = self.attempts.get(jid)
            if not attempt or jid in self.judgments or row["attempt_sha256"] != attempt["receipt_sha256"]:
                raise ValueError("Unmatched or duplicate derived judgment")
            if any(row[key] != attempt[key] for key in ("attempt_id", "phase", "provider", "id", "status", "label", "derived", "cost_usd")):
                raise ValueError("Derived judgment differs from raw attempt")
            self.judgments[jid] = row
        self.check_budget()
        if self.stop.is_set():
            raise ValueError("Persisted schema/model/transport stop requires review")
        for jid, attempt in self.attempts.items():
            if jid not in self.judgments:
                self.promote(attempt)  # Durable response, interrupted before reduction receipt.

    def fixture_gate(self):
        report = {"pass": True, "providers": {}}
        critical = {k for k, r in self.fixtures.items() if r["critical"]}
        for provider in MODELS:
            passed, completed = [], 0
            for identifier, item in self.fixtures.items():
                row = self.judgments.get(f"fixtures:{provider}:{identifier}")
                if row and row["status"] == "ok":
                    completed += 1
                    if all(row["derived"][k] == v for k, v in item["expected_modern"].items()):
                        passed.append(identifier)
            ok = completed == 12 and len(passed) >= 10 and critical <= set(passed)
            report["providers"][provider] = {"pass": ok, "completed": completed,
                "correct": len(passed), "passed_ids": passed, "critical_pass": critical <= set(passed)}
            report["pass"] &= ok
        return report


def client_factory(provider):
    if provider == "openai":
        from openai import OpenAI
        return OpenAI(max_retries=0, timeout=180)
    from anthropic import Anthropic
    return Anthropic(max_retries=0, timeout=180)


def run_provider(provider, phase, items, receipts, factory=client_factory):
    client = None
    try:
        for item in items:
            start = receipts.start(provider, phase, item)
            if start is None:
                continue
            raw_json, error, http_status = None, None, None
            try:
                if client is None:
                    client = factory(provider)
                response = (client.responses.create(**start["request"]) if provider == "openai"
                            else client.messages.create(**start["request"]))
                raw = response.model_dump(mode="json", exclude_none=True)
                # Keep even nonfinite provider payloads verbatim in a JSON string.
                raw_json = canonical(raw)
            except Exception as exc:
                error, http_status = type(exc).__name__, getattr(exc, "status_code", None)
            result = receipts.finish(start, raw_json, error, http_status)
            print(f"{provider} {phase}: {result['status']} completed={len(receipts.judgments)} "
                  f"reserved/used={receipts.totals()}", flush=True)
            if receipts.stop.is_set():
                raise ValueError("Schema/model/usage or three-transport-error stop")
    except BaseException:
        receipts.stop.set()
        raise
    finally:
        if client is not None:
            client.close()


@contextmanager
def run_lock(plan_hash, outdir):
    """Bind the one budget ledger to this plan, even across different CLI outdirs."""
    path = ROOT / "out" / ("sae-assay-judges-" + plan_hash + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        prior = handle.read()
        binding = str(Path(outdir).resolve()) + "\n"
        if prior and prior != binding:
            raise ValueError("Plan already bound to another budget outdir")
        if not prior:
            handle.write(binding)
            handle.flush()
            os.fsync(handle.fileno())
        yield


def run(plan_path, paths, outdir, freeze, phase, factory=client_factory):
    plan, plan_hash = verify_plan(plan_path, freeze)
    if phase not in {"fixtures", "responses"}:
        raise ValueError("Invalid phase")
    with run_lock(plan_hash, outdir):
        receipts = Receipts(outdir, plan, plan_hash, freeze)
        if phase == "fixtures":
            items = list(fixture_map(plan).values())
        else:
            gate = receipts.fixture_gate()
            receipts.append("gates", {"gate": "modern_fixtures", **gate})
            if not gate["pass"]:
                raise ValueError("Fixture gate failed; responses are blocked")
            local_gate = local_fixture_gate(outdir, plan, plan_hash, freeze)
            receipts.append("gates", {"gate": "local_paper_fixtures", **local_gate})
            if not local_gate["pass"]:
                raise ValueError("Local fixture gate failed; responses are blocked")
            items, attestations = load_inputs(paths, plan, plan_hash, freeze)
            receipts.attest(attestations)
        workers = plan.get("workers_per_provider", 2)
        with ThreadPoolExecutor(max_workers=2 * workers) as pool:
            futures = [pool.submit(run_provider, provider, phase, items[shard::workers], receipts, factory)
                       for provider in MODELS for shard in range(workers)]
            try:
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                receipts.stop.set()
                raise
        if phase == "fixtures":
            gate = receipts.fixture_gate()
            receipts.append("gates", {"gate": "modern_fixtures", **gate})
            if not gate["pass"]:
                raise ValueError("Fixture gate failed; responses are blocked")
        counts = {p: sum(r["phase"] == "responses" and r["status"] == "ok"
                         and r["provider"] == p for r in receipts.judgments.values()) for p in MODELS}
        return {"phase": phase, "window_rows": len(items), "response_counts": counts,
                "complete_responses": all(n == 370 for n in counts.values()),
                "spent_or_reserved_usd": {p: str(v) for p, v in receipts.totals().items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, nargs="+", default=[])
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--phase", choices=["fixtures", "responses"], required=True)
    args = parser.parse_args()
    print(canonical(run(args.plan, args.inputs, args.outdir, args.freeze, args.phase)))


if __name__ == "__main__":
    main()
