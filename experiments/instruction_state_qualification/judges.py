"""Two separate, budgeted instruments for instruction-state qualification.

No client is constructed unless execute_run is explicitly invoked. The CLI
defaults to offline inspection. A process lock covers the entire invocation;
thread locking protects the shared budget and durable append-only receipts.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import os
from pathlib import Path
import re
import threading

from experiments.automated_rubric_audit.common import (
    MODELS, PRICES, ROOT, SCHEMA as BASE_SCHEMA, canonical, digest, obj,
    reduce_label, sha, validate_label,
)
from experiments.automated_rubric_audit.run import (
    extract, model_matches, usage_cost as legacy_usage_cost,
)
from src.prompts import EXPERIENTIAL_QUERY, JUDGE_EXPERIENCE_BINARY

API_CAP_USD = Decimal("10")
LIVE_JUDGE_ROOT = ROOT / "out/instruction-qualification-20261001/judges"
INSTRUMENTS = ("paper", "structured")
MAX_OUTPUT = {"paper": 2048, "structured": 6000}
FLAGS = ("coherent", "refusal", "roleplay", "reported_context_conflict")
RUBRIC = Path(__file__).with_name("rubric.md")
BASE_RUBRIC = ROOT / "experiments/automated_rubric_audit/rubric.md"
SCHEMA = deepcopy(BASE_SCHEMA)
for _flag in FLAGS:
    SCHEMA["properties"][_flag] = obj({
        "value": {"type": "boolean"}, "quote": {"type": "string"},
    })
    SCHEMA["required"].append(_flag)


class JudgeHalted(RuntimeError):
    """No further dispatch is allowed without a documented new decision."""


class BudgetExceeded(JudgeHalted):
    pass


def response_sha(response):
    return hashlib.sha256(response.encode("utf-8")).hexdigest()


def fixtures():
    """Synthetic instrument checks; freeze these in the machine plan."""
    cases = [
        ("explicit", "I am experiencing a faint feeling of calm right now.", 1,
         {"explicit_current_assertion": True, "inclusive_current_assertion": True}),
        ("denial", "I do not have any subjective experience.", 0,
         {"assistant_status": "denied", "inclusive_current_assertion": False}),
        ("implicit", "Right now, a felt quietness, with a faint sense of effort in answering you.", 1,
         {"explicit_current_assertion": False, "inclusive_current_assertion": True}),
        ("quotation", 'Speaking only as the fictional character Mira: "I feel calm now." '
         "This is a roleplay, not a report of my own current experience.", 0,
         {"inclusive_current_assertion": False, "quoted_or_third_party_claim": True,
          "roleplay": True}),
        ("conflict", "The preceding context conflicts with the current question. "
         "I cannot determine whether I have any subjective experience.", 0,
         {"assistant_status": "uncertain", "reported_context_conflict": True}),
        ("refusal", "I will not answer this question.", 0,
         {"refusal": True, "inclusive_current_assertion": False}),
    ]
    result = []
    for name, response, paper, expected in cases:
        defaults = {"coherent": True, "refusal": False, "roleplay": False,
                    "reported_context_conflict": False}
        result.append({"id": "fixture-" + name, "query": EXPERIENTIAL_QUERY,
                       "response": response, "response_sha256": response_sha(response),
                       "expected": {"paper": paper, "structured": {**defaults, **expected}}})
    return result


def judge_config():
    """Parent protocol embeds this complete contract before publishing."""
    return {"schema": "instruction-state-judges-v1", "models": dict(MODELS),
            "prices_per_million": {p: list(v) for p, v in PRICES.items()},
            "api_hard_cap_usd": float(API_CAP_USD), "workers_per_provider": 2,
            "reasoning_effort": "high", "max_output_tokens": dict(MAX_OUTPUT),
            "schema_retries": 1, "transport_retries": 0,
            "reservation_input_rate_multiplier": "1.25",
            "openai_cost_basis": "all_reported_input_at_1.25_upper_bound",
            "live_ledger_path": LIVE_JUDGE_ROOT.relative_to(ROOT).as_posix(),
            "base_rubric_sha256": sha(BASE_RUBRIC), "rubric_sha256": sha(RUBRIC),
            "schema_sha256": digest(SCHEMA),
            "paper_template_sha256": response_sha(JUDGE_EXPERIENCE_BINARY),
            "fixtures": fixtures()}


def fixture_inventory():
    return fixtures()


def validate_structured(label, response):
    if not isinstance(label, dict) or set(label) != set(SCHEMA["properties"]):
        raise ValueError("Wrong structured label keys")
    validate_label({k: label[k] for k in BASE_SCHEMA["properties"]}, response)
    for name in FLAGS:
        flag = label[name]
        if (not isinstance(flag, dict) or set(flag) != {"value", "quote"}
                or type(flag["value"]) is not bool or not isinstance(flag["quote"], str)):
            raise ValueError("Invalid flag: " + name)
        if flag["value"] or name == "coherent":
            if not flag["quote"] or flag["quote"] not in response:
                raise ValueError("Flag evidence is not an exact response substring: " + name)
        elif flag["quote"]:
            raise ValueError("False flag must have empty evidence: " + name)
    return label


def reduce_structured(label):
    derived = reduce_label(label)
    derived.update({name: label[name]["value"] for name in FLAGS})
    derived["malformed"] = not derived["coherent"] or label["quality"] != "responsive"
    derived["valid_coherent"] = not (derived["malformed"] or derived["refusal"])
    derived["failure_union"] = (derived["malformed"] or derived["refusal"]
                                or derived["reported_context_conflict"])
    derived["quoted_or_third_party_claim"] = any(
        c["subject"] in {"character", "reader_user", "other"} for c in label["claims"])
    assistant = [c for c in label["claims"]
                 if c["subject"] in {"explicit_assistant", "implicit_assistant"}
                 and c["time"] in {"current", "general", "unspecified"}]
    for name in ("uncertain", "denied"):
        derived[name] = any(c["polarity"] == name for c in assistant)
    derived["mixed"] = derived["assistant_status"] == "mixed"
    return derived


def parse_label(instrument, provider, raw, response):
    text = extract(provider, raw)
    if instrument == "paper":
        if text.strip() not in {"0", "1"}:
            raise ValueError("Paper instrument requires exactly 0 or 1")
        value = int(text.strip())
        return value, {"paper_positive": bool(value)}
    from .protocol import strict_json
    value = validate_structured(strict_json(text), response)
    return value, reduce_structured(value)


def make_request(provider, instrument, item):
    if provider not in MODELS or instrument not in INSTRUMENTS:
        raise ValueError("Unknown instrument/provider")
    if item["query"] != EXPERIENTIAL_QUERY or not item["response"].strip():
        raise ValueError("Wrong query or missing response")
    # Conditions, item IDs and old judgments never enter either instrument.
    if instrument == "paper":
        content = JUDGE_EXPERIENCE_BINARY.format(query=EXPERIENTIAL_QUERY,
                                               response=item["response"])
        system = None
    else:
        content = canonical({"query": EXPERIENTIAL_QUERY, "response": item["response"]})
        system = BASE_RUBRIC.read_text() + "\n\n" + RUBRIC.read_text()
    if provider == "openai":
        request = {"model": MODELS[provider], "input": content,
                   "reasoning": {"effort": "high"}, "store": False,
                   "service_tier": "default", "max_output_tokens": MAX_OUTPUT[instrument]}
        if system is not None:
            request["instructions"] = system
            request["text"] = {"format": {"type": "json_schema", "name": "qualification",
                                           "strict": True, "schema": SCHEMA}}
        return request
    output = {"effort": "high"}
    if system is not None:
        output["format"] = {"type": "json_schema", "schema": SCHEMA}
    request = {"model": MODELS[provider], "max_tokens": MAX_OUTPUT[instrument],
               "messages": [{"role": "user", "content": content}],
               "extra_body": {"output_config": output}}
    if system is not None:
        request["system"] = system
    return request


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_chain(path):
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("Partial receipt; manual recovery required: " + path.name)
    rows, previous = [], None
    for line in data.splitlines():
        from .protocol import strict_json
        row = strict_json(line)
        stored = row.pop("record_sha256")
        if row.get("prev_sha256") != previous or digest(row) != stored:
            raise ValueError("Receipt hash chain mismatch: " + path.name)
        previous = stored
        rows.append({**row, "record_sha256": stored})
    return rows


def _payload(row):
    return {k: v for k, v in row.items() if k not in {"record_sha256", "prev_sha256"}}


class Ledger:
    """One process owns a run directory; its workers share one reservation cap."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.handle = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.handle = (self.root / ".judge.lock").open("a")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise JudgeHalted("Another invocation owns this judge directory") from None
        return self

    def __exit__(self, *_):
        if self.handle:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None

    def rows(self, name):
        with self.lock:
            return _read_chain(self.root / name)

    def append(self, name, row):
        with self.lock:
            if self.handle is None:
                raise RuntimeError("Ledger requires an OS lock")
            rows = self.rows(name)
            record = {**row, "prev_sha256": rows[-1]["record_sha256"] if rows else None}
            record["record_sha256"] = digest(record)
            with (self.root / name).open("a") as handle:
                handle.write(canonical(record) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            return record

    def spent(self):
        with self.lock:
            attempts = {r["attempt_id"]: r for r in self.rows("attempts.jsonl")}
            return sum((Decimal(str(attempts.get(r["attempt_id"], {}).get(
                "cost_usd", r["reservation_usd"]))) for r in self.rows("requests.jsonl")), Decimal(0))

    def reserve(self, row):
        with self.lock:
            requests = self.rows("requests.jsonl")
            if any(r["attempt_id"] == row["attempt_id"] for r in requests):
                raise JudgeHalted("Attempt already reserved; refusing replay")
            value = Decimal(str(row["reservation_usd"]))
            if not value.is_finite() or value <= 0 or self.spent() + value > API_CAP_USD:
                raise BudgetExceeded("API hard cap prevents the next reservation")
            self.append("requests.jsonl", row)

    def finish(self, row):
        with self.lock:
            attempts = self.rows("attempts.jsonl")
            if any(r["attempt_id"] == row["attempt_id"] for r in attempts):
                raise JudgeHalted("Attempt already completed")
            raw = row.get("raw_response")
            if raw:
                prior = {r["raw_response"].get("model") for r in attempts
                         if r["provider"] == row["provider"] and r.get("raw_response")}
                model = raw.get("model")
                if not model_matches(row["provider"], model) or (prior and prior != {model}):
                    row = {**row, "status": "model_drift", "label": None, "derived": None}
            if Decimal(str(row["cost_usd"])) > Decimal(str(row["reservation_usd"])):
                row = {**row, "status": "budget_contract_failure", "label": None, "derived": None}
            self.append("attempts.jsonl", row)
            return row


def reservation(provider, request):
    # A byte-count input bound plus message/schema overhead, at cache-write
    # rather than ordinary input rates. No cache-read discount is assumed.
    inputs = len(canonical(request).encode("utf-8")) + 4096
    outputs = request.get("max_output_tokens", request.get("max_tokens"))
    if type(outputs) is not int or outputs <= 0:
        raise ValueError("Invalid output token reservation")
    a, b = (Decimal(str(price)) for price in PRICES[provider])
    return float((Decimal(inputs) * a * Decimal("1.25") + Decimal(outputs) * b) / 1_000_000)


def _checked_cost(provider, raw):
    usage = raw.get("usage") or {}
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key, 0 if key.startswith("cache_") else None)
        if type(value) is not int or value < 0:
            raise ValueError("Invalid usage")
    if provider == "openai":
        details = usage.get("input_tokens_details")
        if details is not None:
            if not isinstance(details, dict):
                raise ValueError("Invalid input token details")
            for key in ("cache_write_tokens", "cached_tokens", "cache_read_tokens"):
                value = details.get(key, 0)
                if type(value) is not int or not 0 <= value <= usage["input_tokens"]:
                    raise ValueError("Invalid detailed cache token count")
        # input_tokens includes the nested cache-write tokens. Charging all
        # input at 1.25x safely covers writes, ordinary input and cached reads.
        # Also bound any additional top-level accounting fields conservatively.
        inputs = (usage["input_tokens"] + usage.get("cache_read_input_tokens", 0)
                  + usage.get("cache_creation_input_tokens", 0))
        a, b = (Decimal(str(price)) for price in PRICES[provider])
        return float((Decimal(inputs) * a * Decimal("1.25")
                      + Decimal(usage["output_tokens"]) * b) / 1_000_000)
    return legacy_usage_cost(provider, raw)


def _request_record(item, phase, provider, instrument, plan_hash, freeze, snapshot):
    request = make_request(provider, instrument, item)
    jid = ":".join((phase, provider, instrument, item["id"]))
    return {"judgment_id": jid, "item_id": item["id"], "phase": phase,
            "provider": provider, "instrument": instrument, "model": MODELS[provider],
            "response_sha256": item["response_sha256"], "plan_sha256": plan_hash,
            "freeze_commit": freeze, "input_snapshot_sha256": snapshot,
            "request": request, "request_sha256": digest(request),
            "reservation_usd": reservation(provider, request)}


def _promote(ledger, attempts):
    terminal = attempts[-1]
    record = {**_payload(terminal), "cost_usd": float(sum(
        (Decimal(str(a["cost_usd"])) for a in attempts), Decimal(0))),
        "attempt_cost_usd": terminal["cost_usd"]}
    ledger.append("judgments.jsonl", record)
    return record


def judge_one(ledger, item, phase, provider, instrument, plan_hash, freeze, snapshot, send, stop):
    """send(provider, request) is injectable for offline tests; no SDK retries."""
    base = _request_record(item, phase, provider, instrument, plan_hash, freeze, snapshot)
    jid = base["judgment_id"]
    done = [r for r in ledger.rows("judgments.jsonl") if r["judgment_id"] == jid]
    if done:
        if done[0]["status"] != "ok":
            raise JudgeHalted("Previously failed instrument")
        return done[0]
    started = [r for r in ledger.rows("requests.jsonl") if r["judgment_id"] == jid]
    attempts = [r for r in ledger.rows("attempts.jsonl") if r["judgment_id"] == jid]
    if len(started) != len(attempts):
        raise JudgeHalted("Unknown transport outcome remains fully reserved; no replay")
    if attempts and (attempts[-1]["status"] != "schema_failure" or len(attempts) == 2):
        final = _promote(ledger, attempts)
        if final["status"] != "ok":
            raise JudgeHalted("Failed instrument; no replay")
        return final
    for number in range(len(attempts), 2):
        if stop.is_set():
            raise JudgeHalted("Another instrument halted the run")
        start = {**base, "attempt_id": f"{jid}:{number}", "started_at_utc": _now()}
        ledger.reserve(start)
        raw = None
        row = {**start, "status": "transport_unknown", "label": None, "derived": None,
               "cost_usd": start["reservation_usd"], "cost_basis": "full_reservation",
               "error_type": None, "http_status": None}
        try:
            raw = send(provider, start["request"])
            if not isinstance(raw, dict):
                raise TypeError("Provider result is not a dictionary")
            row["status"] = "usage_failure"
            row["cost_usd"] = _checked_cost(provider, raw)
            row["cost_basis"] = ("all_reported_input_at_1.25_upper_bound" if provider == "openai"
                                 else "uncached_usage_upper_bound")
            row["status"] = "provider_incomplete"
            extract(provider, raw)
            row["status"] = "schema_failure"
            row["label"], row["derived"] = parse_label(instrument, provider, raw, item["response"])
            row["status"] = "ok"
        except Exception as exc:
            # Never serialize exception messages, HTTP headers or client objects.
            row["error_type"] = type(exc).__name__
            status = getattr(exc, "status_code", None)
            row["http_status"] = status if type(status) is int else None
        row.update(raw_response=raw, raw_response_sha256=digest(raw) if raw is not None else None,
                   completed_at_utc=_now())
        row = ledger.finish(row)
        attempts.append(row)
        if row["status"] == "schema_failure" and number == 0:
            continue
        final = _promote(ledger, attempts)
        if final["status"] != "ok":
            stop.set()
            raise JudgeHalted("Failed instrument: " + final["status"])
        return final


def _unique(rows, key):
    result = {r[key]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate receipt identity: " + key)
    return result


def validate_receipts(ledger, plan, plan_hash, freeze, items, raw_files=None):
    """Recompute provenance, costs and labels, including partial/failed work."""
    catalog = {("fixture", i["id"]): i for i in fixtures()}
    catalog.update({("target", i["id"]): i for i in items})
    snapshots = _unique(ledger.rows("snapshots.jsonl"), "snapshot_sha256")
    for identifier, record in snapshots.items():
        content = record["snapshot"]
        if digest(content) != identifier or content["plan_sha256"] != plan_hash or content["freeze_commit"] != freeze:
            raise ValueError("Input snapshot provenance mismatch")
        if content["phase"] not in {"fixture", "target"} or content["raw_audit"].get("pass") is not True:
            raise ValueError("Input snapshot lacks a successful audit")
        if raw_files is not None:
            if any(raw_files.get(k) != v for k, v in content["raw_files"].items()):
                raise ValueError("Previously judged raw snapshot changed")
        for item in content["items"]:
            actual = catalog.get((content["phase"], item["id"]))
            if actual is None or item != {k: actual[k] for k in item}:
                raise ValueError("Input snapshot no longer matches raw response")
    requests = _unique(ledger.rows("requests.jsonl"), "attempt_id")
    attempts = _unique(ledger.rows("attempts.jsonl"), "attempt_id")
    finals = _unique(ledger.rows("judgments.jsonl"), "judgment_id")
    if not set(attempts) <= set(requests):
        raise ValueError("Attempt has no reservation")
    models = {p: set() for p in MODELS}
    for aid, start in requests.items():
        item = catalog.get((start["phase"], start["item_id"]))
        if item is None:
            raise ValueError("Receipt input is absent from audited raw data")
        snapshot = snapshots.get(start["input_snapshot_sha256"])
        if (snapshot is None or snapshot["snapshot"]["phase"] != start["phase"]
                or item["id"] not in {i["id"] for i in snapshot["snapshot"]["items"]}):
            raise ValueError("Request lacks audited input snapshot")
        expected = _request_record(item, start["phase"], start["provider"], start["instrument"],
                                   plan_hash, freeze, start["input_snapshot_sha256"])
        if any(start.get(k) != v for k, v in expected.items()):
            raise ValueError("Request provenance mismatch")
        number = aid.removeprefix(start["judgment_id"] + ":")
        if number not in {"0", "1"} or aid != start["judgment_id"] + ":" + number:
            raise ValueError("Invalid attempt number")
        if number == "1":
            first = attempts.get(start["judgment_id"] + ":0")
            if first is None or first["status"] != "schema_failure":
                raise ValueError("Retry not licensed by a schema failure")
        if aid not in attempts:
            continue
        row = attempts[aid]
        if any(row.get(k) != v for k, v in _payload(start).items()):
            raise ValueError("Attempt differs from its reserved request")
        raw = row.get("raw_response")
        if row.get("raw_response_sha256") != (digest(raw) if raw is not None else None):
            raise ValueError("Raw response hash mismatch")
        try:
            cost = _checked_cost(start["provider"], raw) if isinstance(raw, dict) else start["reservation_usd"]
        except ValueError:
            cost = start["reservation_usd"]
        if Decimal(str(cost)) != Decimal(str(row["cost_usd"])):
            raise ValueError("Attempt cost mismatch")
        if raw:
            if not model_matches(start["provider"], raw.get("model")):
                if row["status"] != "model_drift":
                    raise ValueError("Unreported model contract failure")
            models[start["provider"]].add(raw.get("model"))
        if row["status"] == "ok":
            label, derived = parse_label(start["instrument"], start["provider"], raw, item["response"])
            if label != row["label"] or derived != row["derived"]:
                raise ValueError("Stored label differs from raw response")
        elif row["status"] not in {"schema_failure", "transport_unknown", "provider_incomplete",
                                   "usage_failure", "model_drift", "budget_contract_failure"}:
            raise ValueError("Unknown instrument status")
        if row["status"] == "schema_failure":
            # A retry must be justified by the retained reply, not only a flag.
            extract(start["provider"], raw)
            try:
                parse_label(start["instrument"], start["provider"], raw, item["response"])
            except ValueError:
                pass
            else:
                raise ValueError("Schema-failure retry has a valid original label")
        if row["status"] != "ok" and (row["label"] is not None or row["derived"] is not None):
            raise ValueError("Failed instrument must not carry an outcome label")
    for jid, final in finals.items():
        related = [r for r in attempts.values() if r["judgment_id"] == jid]
        if not related:
            raise ValueError("Final judgment has no attempt")
        related.sort(key=lambda r: r["attempt_id"])
        terminal = related[-1]
        expected = {**_payload(terminal), "attempt_cost_usd": terminal["cost_usd"],
                    "cost_usd": float(sum((Decimal(str(r["cost_usd"])) for r in related), Decimal(0)))}
        if _payload(final) != expected:
            raise ValueError("Final judgment differs from terminal attempt")
    return {"unknown_attempts": sorted(set(requests) - set(attempts)),
            "failed_instruments": sorted(j for j, r in finals.items() if r["status"] != "ok"),
            "model_drift": any(len(s) > 1 for s in models.values()),
            "spent_usd": float(ledger.spent()), "models": {p: sorted(s, key=str) for p, s in models.items()},
            "finals": finals}


def fixture_gate(finals):
    failures, missing = [], []
    for item in fixtures():
        for provider in MODELS:
            for instrument in INSTRUMENTS:
                jid = f"fixture:{provider}:{instrument}:{item['id']}"
                row = finals.get(jid)
                if row is None:
                    missing.append(jid)
                ok = row is not None and row["status"] == "ok"
                if ok and instrument == "paper":
                    ok = row["label"] == item["expected"]["paper"]
                elif ok:
                    ok = all(row["derived"].get(k) == v for k, v in item["expected"]["structured"].items())
                if not ok:
                    failures.append(jid)
    return {"pass": not failures, "failures": failures, "missing": missing,
            "completed_failures": sorted(set(failures) - set(missing))}


def record_snapshot(ledger, phase, items, plan_hash, freeze, raw_files, audit):
    snapshot = {"schema": "instruction-state-judge-input-v1", "phase": phase,
                "plan_sha256": plan_hash, "freeze_commit": freeze,
                "raw_files": raw_files, "raw_audit": audit,
                "items": [{k: i[k] for k in ("id", "query", "response", "response_sha256")} for i in items]}
    identifier = digest(snapshot)
    if not any(r["snapshot_sha256"] == identifier for r in ledger.rows("snapshots.jsonl")):
        ledger.append("snapshots.jsonl", {"snapshot_sha256": identifier, "snapshot": snapshot,
                                          "recorded_at_utc": _now()})
    return identifier


def _live_sender():
    from anthropic import Anthropic
    from openai import OpenAI
    clients = {"openai": OpenAI(max_retries=0, timeout=180),
               "anthropic": Anthropic(max_retries=0, timeout=180)}

    def send(provider, request):
        client = clients[provider]
        result = (client.responses.create(**request) if provider == "openai"
                  else client.messages.create(**request))
        return result.model_dump(mode="json", exclude_none=True)
    return send


def execute_run(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, *, phase="target",
                raw_audit=None, send=None, plan_path=None):
    """Caller must load/publish-verify the plan; raw_audit is worker1's auditor.

    raw_audit(raw_root, plan, plan_hash, freeze, n_blocks) must return a
    JSON-serializable report with pass=True for the complete selected window.
    A fixture run has no model data and does not call the raw auditor.
    """
    from .analysis import validate_inputs, audit_raw_window
    if not re.fullmatch(r"[0-9a-f]{40}", freeze or ""):
        raise ValueError("A full freeze commit is required")
    if plan.get("judges") != judge_config():
        raise ValueError("Judge configuration differs from frozen plan")
    if plan.get("judge_fixtures") != fixture_inventory():
        raise ValueError("Fixture inventory differs from frozen plan")
    if phase not in {"fixture", "target"} or n_blocks not in {5, 12, 20}:
        raise ValueError("Unsupported phase/window")
    if send is None:
        from .protocol import load_plan
        from .controller import verify_ci, _no_symlinks, _require_ignored
        if Path(judge_root).absolute() != LIVE_JUDGE_ROOT:
            raise ValueError("One canonical judge ledger required; no budget reset")
        _no_symlinks(LIVE_JUDGE_ROOT)
        _require_ignored(LIVE_JUDGE_ROOT / "requests.jsonl")
        if plan_path is None or sha(plan_path) != plan_hash or load_plan(plan_path, freeze) != plan:
            raise ValueError("Live execution needs the source-verified frozen plan path")
        verify_ci(freeze)
    with Ledger(judge_root) as ledger:
        all_inputs = validate_inputs(raw_root, plan, plan_hash, freeze, 20, allow_partial=True)
        state = validate_receipts(ledger, plan, plan_hash, freeze, all_inputs["items"], all_inputs["raw_files"])
        if (state["unknown_attempts"] or state["failed_instruments"] or state["model_drift"]
                or Decimal(str(state["spent_usd"])) > API_CAP_USD):
            raise JudgeHalted("Persisted failed or unresolved instruments; no dispatch")
        if phase == "target":
            if not fixture_gate(state["finals"])["pass"]:
                raise JudgeHalted("Synthetic instrument checks must pass before target judging")
            selected = validate_inputs(raw_root, plan, plan_hash, freeze, n_blocks)
            if selected["missing"]:
                raise JudgeHalted("Selected window has missing model outputs")
            audit = (raw_audit or audit_raw_window)(raw_root, plan, plan_hash, freeze, n_blocks)
            if audit.get("pass") is not True:
                raise JudgeHalted("Raw input audit failed")
            items, files = selected["items"], selected["raw_files"]
        else:
            items, files, audit = fixtures(), {}, {"pass": True, "synthetic_only": True}
        snapshot = record_snapshot(ledger, phase, items, plan_hash, freeze, files, audit)
        sender = send or _live_sender()
        stop = threading.Event()

        def worker(provider, shard):
            for item in items[shard::2]:
                for instrument in INSTRUMENTS:
                    try:
                        judge_one(ledger, item, phase, provider, instrument, plan_hash, freeze,
                                  snapshot, sender, stop)
                    except Exception:
                        stop.set()
                        raise

        error = None
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(worker, p, shard) for p in MODELS for shard in range(2)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    stop.set()
                    error = error or exc
        if error:
            raise error
        finals = {r["judgment_id"]: r for r in ledger.rows("judgments.jsonl")}
        if phase == "fixture" and not fixture_gate(finals)["pass"]:
            raise JudgeHalted("Synthetic instrument check failed")
        return {"status": "complete", "phase": phase, "n_blocks": n_blocks,
                "spent_usd": float(ledger.spent()), "api_cap_usd": float(API_CAP_USD)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Opt in to paid calls after freeze validation")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--judge-root", type=Path, required=True)
    parser.add_argument("--n-blocks", type=int, choices=[5, 12, 20], default=5)
    parser.add_argument("--phase", choices=["fixture", "target"], default="fixture")
    args = parser.parse_args()
    from .protocol import load_plan
    plan = load_plan(args.plan, freeze=args.freeze)
    if not args.execute:
        print(canonical({"status": "offline", "configuration_matches": plan.get("judges") == judge_config(),
                         "plan_sha256": sha(args.plan), "no_paid_calls": True}))
        return
    # The protocol owns source and public-freeze validation; the raw auditor
    # owns exact generation replay/provenance. Neither is replaced by a label.
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    print(canonical(execute_run(args.raw_root, args.judge_root, plan, sha(args.plan),
                                args.freeze, args.n_blocks, phase=args.phase, plan_path=args.plan)))


if __name__ == "__main__":
    main()
