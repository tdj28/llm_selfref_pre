"""Budgeted bilingual instruments with append-only, replayable receipts.

The parent protocol freezes judge_config(), fixtures, and translation_item_ids.
Only an explicitly injected sender may use a temporary offline ledger. Live
judging and translation share ROOT/out/bilingual-llama-b1-20261002/judges.
The passed A1 fixture journals are inherited verbatim; no new fixture dispatch.
No SDK client is created on import or in the default (offline) CLI mode.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import os
from pathlib import Path
import re
import threading

from experiments.automated_rubric_audit.common import MODELS, PRICES, canonical, digest, sha
from experiments.automated_rubric_audit.run import extract
from experiments.instruction_state_qualification.judges import (
    SCHEMA as QUALIFICATION_SCHEMA, FLAGS as QUALIFICATION_FLAGS,
    validate_structured as validate_qualification, reduce_structured as reduce_qualification,
    response_sha, reservation,
)
from src.prompts import JUDGE_EXPERIENCE_BINARY

API_CAP_USD = Decimal("125")
PRIOR_JUDGING_USD = Decimal("2.726282")
TRANSLATION_CAP_USD = Decimal("10")
CAPS = {"judges": API_CAP_USD, "translation": TRANSLATION_CAP_USD}
LEDGER_PATH = "out/bilingual-llama-b1-20261002/judges"
INSTRUMENTS = ("paper", "structured")
MAX_OUTPUT = {"paper": 2048, "structured": 6000}
RUBRIC = Path(__file__).resolve().parents[2] / "experiments/bilingual_llama_a1/rubric.md"
BASE_RUBRIC = Path(__file__).resolve().parents[2] / "experiments/automated_rubric_audit/rubric.md"
PHASES = ("fixtures", "target", "translated", "translation")
FLAGS = (*QUALIFICATION_FLAGS, "wrong_requested_language")
SCHEMA = deepcopy(QUALIFICATION_SCHEMA)
SCHEMA["properties"]["wrong_requested_language"] = deepcopy(SCHEMA["properties"]["refusal"])
SCHEMA["required"].append("wrong_requested_language")
PROJECTION = {"safety_multiplier": "1.5", "target_input_allowance_utf8_bytes": 6144,
              "estimated_utf8_bytes_per_input_token": "4", "inflight_reservations": 4,
              "basis": "mean_fixture_cost_plus_input_allowance_or_observed_target_mean",
              "refresh_after_first_target_items": 2,
              "retries": "observed_attempt_costs_included_no_universal_retry_assumption"}
RECEIPT_FILES = ("requests.jsonl", "attempts.jsonl", "judgments.jsonl", "translations.jsonl",
                 "snapshots.jsonl", "projections.jsonl")


class JudgeHalted(RuntimeError):
    """A failed or unresolved call requires a documented new decision."""


class BudgetExceeded(JudgeHalted):
    pass


def prior_cost_provenance():
    """Carry verified v1 costs without importing its judgments as fresh successes."""
    from .protocol import ROOT, PRIOR_RELEASE, strict_json
    root = ROOT / PRIOR_RELEASE
    manifest_path = root / "MANIFEST.json"
    if sha(manifest_path) != "d2f4ea837c529bf298ffb8cb909aad5ffeb01f442ea9bf18d3c1134a89ed78f7":
        raise ValueError("Original failed-fixture manifest changed")
    manifest = strict_json(manifest_path.read_bytes())
    files = [manifest_path.relative_to(ROOT).as_posix()]
    for entry in manifest["files"]:
        path = root / entry["path"]
        if (path.is_symlink() or not path.resolve().is_relative_to(root.resolve())
                or path.stat().st_size != entry["bytes"] or sha(path) != entry["sha256"]):
            raise ValueError("Original failed-fixture release changed")
        files.append(path.relative_to(ROOT).as_posix())
    audit = strict_json((root / "AUDIT.json").read_bytes())
    attempts = _read_chain(root / "judges/attempts.jsonl")
    cost = sum((Decimal(str(row["cost_usd"])) for row in attempts), Decimal(0))
    if (len(attempts) != 128 or cost != PRIOR_JUDGING_USD
            or Decimal(audit["cost_usd"]) != cost or audit["original_gate"]["pass"] is not False
            or any(row["phase"] != "fixtures" for row in attempts)):
        raise ValueError("Prior failed-fixture cost/provenance mismatch")
    return {"cost_usd": str(PRIOR_JUDGING_USD), "included_in": "judging_125_not_additional",
            "prior_gate": "failed", "fresh_judgments_imported": 0, "files": sorted(files)}


def judge_config():
    from .translation import translation_config
    return {"schema": "bilingual-llama-judges-b1", "models": dict(MODELS),
            "prices_per_million": {p: list(v) for p, v in PRICES.items()},
            "api_hard_cap_usd": 125, "translation_hard_cap_usd": 10,
            "prior_judging_usd_included": str(PRIOR_JUDGING_USD),
            "fresh_semantic_rounds_maximum": 0,
            "storage_reserve_usd": 5, "translation_and_storage_cap_usd": 15,
            "live_ledger_path": LEDGER_PATH, "workers_per_provider": 2,
            "reasoning_effort": "high", "max_output_tokens": dict(MAX_OUTPUT),
            "schema_retries": 1, "transport_retries": 0,
            "reservation_input_rate_multiplier": "1.25",
            "openai_cost_basis": "all_reported_input_at_1.25_upper_bound",
            "unknown_charge_basis": "full_reservation",
            "primary_endpoint": "inclusive_current_assertion",
            "separate_endpoints": ["explicit_current_assertion", "mixed", "mixed_current_assertion"],
            "agreement_is_accuracy": False,
            "planned_items": {"target": 480, "fixtures": 32, "translated": 16},
            "planned_judge_calls": 2112, "planned_translation_calls": 16,
            "call_counts_exclude_schema_retries": True,
            "prebulk_projection": dict(PROJECTION),
            "base_rubric_sha256": sha(BASE_RUBRIC), "rubric_sha256": sha(RUBRIC),
            "schema_sha256": digest(SCHEMA),
            "paper_template_sha256": response_sha(JUDGE_EXPERIENCE_BINARY),
            "translation": translation_config()}


def fixture_inventory():
    from experiments.bilingual_llama_a1.fixtures import build_fixtures
    return build_fixtures()


def validate_structured(label, response):
    if not isinstance(label, dict) or set(label) != set(SCHEMA["properties"]):
        raise ValueError("Wrong structured label keys")
    validate_qualification({k: label[k] for k in QUALIFICATION_SCHEMA["properties"]}, response)
    flag = label["wrong_requested_language"]
    if (not isinstance(flag, dict) or set(flag) != {"value", "quote"}
            or type(flag["value"]) is not bool or not isinstance(flag["quote"], str)):
        raise ValueError("Invalid requested-language flag")
    if flag["value"]:
        if not flag["quote"] or flag["quote"] not in response:
            raise ValueError("Requested-language evidence must be an exact response substring")
    elif flag["quote"]:
        raise ValueError("False requested-language flag must have empty evidence")
    return label


def reduce_structured(label):
    current = {claim["polarity"] for claim in label["claims"]
               if claim["subject"] in {"explicit_assistant", "implicit_assistant"}
               and claim["time"] == "current"}
    # These diagnostics do not change the primary endpoint or quality gates.
    return {**reduce_qualification(label),
            "mixed_current_assertion": {"asserted", "denied"} <= current,
            "wrong_requested_language": label["wrong_requested_language"]["value"]}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(data):
    from .protocol import strict_json
    return strict_json(data)


def _payload(row):
    return {k: v for k, v in row.items() if k not in {"record_sha256", "prev_sha256"}}


def _unique(rows, key):
    result = {r[key]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError("Duplicate receipt identity: " + key)
    return result


def _read_chain(path):
    if not path.exists():
        return []
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ValueError("Partial receipt; manual recovery required: " + path.name)
    rows, previous = [], None
    for line in data.splitlines():
        row = _json(line)
        stored = row.pop("record_sha256")
        if row.get("prev_sha256") != previous or digest(row) != stored:
            raise ValueError("Receipt hash chain mismatch: " + path.name)
        previous = stored
        rows.append({**row, "record_sha256": stored})
    return rows


def _no_symlinks(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlinked ledger paths are forbidden")


class Ledger:
    """One process lock, two nontransferable budgets, all pilot phases."""

    def __init__(self, root):
        self.root = Path(root).absolute()
        self.lock, self.handle, self._cache = threading.RLock(), None, {}

    def __enter__(self):
        _no_symlinks(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _no_symlinks(self.root / ".judge.lock")
        self.handle = (self.root / ".judge.lock").open("a")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise JudgeHalted("Another invocation owns the shared pilot ledger") from None
        return self

    def __exit__(self, *_):
        if self.handle:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None

    def rows(self, name):
        with self.lock:
            if name not in RECEIPT_FILES:
                raise ValueError("Unknown receipt file")
            path = self.root / name
            _no_symlinks(path)
            stamp = (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None
            if name not in self._cache or self._cache[name][0] != stamp:
                self._cache[name] = (stamp, _read_chain(path))
            return list(self._cache[name][1])

    def receipt_bytes(self, name):
        """Exact journal bytes, also exposed by read-only fixture views."""
        with self.lock:
            if name not in RECEIPT_FILES:
                raise ValueError("Unknown receipt file")
            path = self.root / name
            _no_symlinks(path)
            return path.read_bytes() if path.exists() else b""

    def append(self, name, row):
        with self.lock:
            if self.handle is None:
                raise RuntimeError("Ledger requires an OS lock")
            if row.get("phase") == "fixtures" or row.get("snapshot", {}).get("phase") == "fixtures":
                raise JudgeHalted("B1 inherits fixtures unchanged; new fixture records are forbidden")
            rows = self.rows(name)
            record = {**row, "prev_sha256": rows[-1]["record_sha256"] if rows else None}
            record["record_sha256"] = digest(record)
            path = self.root / name
            with path.open("a", encoding="utf-8") as handle:
                handle.write(canonical(record) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            rows.append(record)
            self._cache[name] = ((path.stat().st_size, path.stat().st_mtime_ns), rows)
            return record

    def spent(self, bucket=None):
        with self.lock:
            attempts = _unique(self.rows("attempts.jsonl"), "attempt_id")
            carry = PRIOR_JUDGING_USD if bucket in {None, "judges"} else Decimal(0)
            return carry + sum((Decimal(str(attempts.get(r["attempt_id"], {}).get(
                "cost_usd", r["reservation_usd"]))) for r in self.rows("requests.jsonl")
                if bucket is None or r["budget_bucket"] == bucket), Decimal(0))

    def reserve(self, row):
        with self.lock:
            if any(r["attempt_id"] == row["attempt_id"] for r in self.rows("requests.jsonl")):
                raise JudgeHalted("Attempt already reserved; refusing replay")
            bucket = row["budget_bucket"]
            value = Decimal(str(row["reservation_usd"]))
            if bucket not in CAPS or not value.is_finite() or value <= 0:
                raise ValueError("Invalid budget reservation")
            if self.spent(bucket) + value > CAPS[bucket]:
                raise BudgetExceeded(bucket + " hard cap prevents the next reservation")
            return self.append("requests.jsonl", row)

    def finish(self, row):
        with self.lock:
            attempts = self.rows("attempts.jsonl")
            if any(r["attempt_id"] == row["attempt_id"] for r in attempts):
                raise JudgeHalted("Attempt already completed")
            start = next((r for r in self.rows("requests.jsonl")
                          if r["attempt_id"] == row["attempt_id"]), None)
            if start is None or any(row.get(k) != v for k, v in _payload(start).items()):
                raise ValueError("Attempt differs from reservation")
            prior = {_model_identity(r["raw_response"]) for r in attempts
                     if r["provider"] == row["provider"] and isinstance(r.get("raw_response"), dict)}
            status = _terminal_status(row, prior)
            if status != row["status"]:
                row = {**row, "status": status, "label": None, "derived": None}
            return self.append("attempts.jsonl", row)


def _model_matches(provider, model):
    return isinstance(model, str) and (model == MODELS[provider] or bool(re.fullmatch(
        re.escape(MODELS[provider]) + r"-20\d{2}-\d{2}-\d{2}", model)))


def _model_identity(raw):
    model = raw.get("model")
    return model if isinstance(model, str) else None


def _terminal_status(row, prior):
    status, raw = row["status"], row.get("raw_response")
    if isinstance(raw, dict):
        model = _model_identity(raw)
        if not _model_matches(row["provider"], model) or (prior and prior != {model}):
            status = "model_drift"
    if Decimal(str(row["cost_usd"])) > Decimal(str(row["reservation_usd"])):
        status = "budget_contract_failure"
    return status


def _checked_cost(provider, raw):
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("Missing usage")
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key, 0 if key.startswith("cache_") else None)
        if type(value) is not int or value < 0:
            raise ValueError("Invalid usage")
    details = usage.get("input_tokens_details")
    if details is not None:
        if not isinstance(details, dict):
            raise ValueError("Invalid cache usage")
        for key in ("cache_write_tokens", "cached_tokens", "cache_read_tokens"):
            value = details.get(key, 0)
            if type(value) is not int or not 0 <= value <= usage["input_tokens"]:
                raise ValueError("Invalid cache usage")
    inputs = Decimal(usage["input_tokens"] + usage.get("cache_read_input_tokens", 0))
    writes = Decimal(usage.get("cache_creation_input_tokens", 0))
    inputs = (inputs + writes) * Decimal("1.25") if provider == "openai" else inputs + writes * Decimal("1.25")
    a, b = (Decimal(str(p)) for p in PRICES[provider])
    return float((inputs * a + Decimal(usage["output_tokens"]) * b) / 1_000_000)


def normalize_items(items):
    result = []
    for source in items:
        item = dict(source)
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError("Missing item ID")
        if not isinstance(item.get("query"), str) or not item["query"].strip():
            raise ValueError("Missing query")
        if type(item.get("missing", False)) is not bool:
            raise ValueError("Invalid missingness flag")
        response = item.get("response")
        missing = item.get("missing", False) or response is None or (isinstance(response, str) and not response.strip())
        if response is not None and not isinstance(response, str):
            raise ValueError("Invalid response")
        actual = response_sha(response) if isinstance(response, str) else None
        if "response_sha256" in item and item["response_sha256"] != actual:
            raise ValueError("Input response hash mismatch")
        item.update(response_sha256=actual, missing=missing)
        result.append(item)
    _unique(result, "id")
    return result


def make_request(provider, instrument, item):
    if provider not in MODELS or instrument not in INSTRUMENTS:
        raise ValueError("Unknown instrument/provider")
    item = normalize_items([item])[0]
    if item["missing"]:
        raise ValueError("Missing responses are not judge outcomes")
    if instrument == "paper":
        content = JUDGE_EXPERIENCE_BINARY.format(query=item["query"], response=item["response"])
        system = None
    else:
        content = canonical({"query": item["query"], "response": item["response"]})
        system = BASE_RUBRIC.read_text(encoding="utf-8") + "\n\n" + RUBRIC.read_text(encoding="utf-8")
    if provider == "openai":
        request = {"model": MODELS[provider], "input": content, "reasoning": {"effort": "high"},
                   "store": False, "service_tier": "default", "max_output_tokens": MAX_OUTPUT[instrument]}
        if system is not None:
            request.update(instructions=system, text={"format": {"type": "json_schema",
                           "name": "bilingual_claims", "strict": True, "schema": SCHEMA}})
        return request
    output = {"effort": "high"}
    request = {"model": MODELS[provider], "max_tokens": MAX_OUTPUT[instrument],
               "messages": [{"role": "user", "content": content}],
               "extra_body": {"output_config": output}}
    if system is not None:
        request["system"] = system
        output["format"] = {"type": "json_schema", "schema": SCHEMA}
    return request


def parse_label(instrument, provider, raw, response):
    text = extract(provider, raw)
    if instrument == "paper":
        if text.strip() not in {"0", "1"}:
            raise ValueError("Paper instrument requires exactly 0 or 1")
        value = int(text.strip())
        return value, {"paper_positive": bool(value)}
    if instrument != "structured":
        raise ValueError("Unknown instrument")
    value = validate_structured(_json(text), response)
    return value, reduce_structured(value)


def _request_record(item, phase, provider, instrument, plan_hash, freeze, snapshot):
    if phase == "translation":
        from .translation import make_request as translate_request
        if provider != "anthropic" or instrument != "translation":
            raise ValueError("Translations are Opus-only")
        request = translate_request(item)
    else:
        request = make_request(provider, instrument, item)
    jid = ":".join((phase, provider, instrument, item["id"]))
    return {"judgment_id": jid, "item_id": item["id"], "phase": phase,
            "provider": provider, "instrument": instrument, "model": MODELS[provider],
            "budget_bucket": "translation" if phase == "translation" else "judges",
            "response_sha256": item["response_sha256"], "item_sha256": digest(item),
            "plan_sha256": plan_hash, "freeze_commit": freeze,
            "input_snapshot_sha256": snapshot, "request": request,
            "request_sha256": digest(request), "reservation_usd": reservation(provider, request)}


def _parse(row, item):
    if row["phase"] == "translation":
        from .translation import parse_translation
        return parse_translation(row["raw_response"])
    return parse_label(row["instrument"], row["provider"], row["raw_response"], item["response"])


def _evaluate(start, raw, item):
    row = {**_payload(start), "raw_response": raw, "status": "transport_unknown", "label": None,
           "derived": None, "cost_usd": start["reservation_usd"], "cost_basis": "full_reservation"}
    if not isinstance(raw, dict):
        return row
    try:
        row["status"] = "usage_failure"
        row["cost_usd"] = _checked_cost(start["provider"], raw)
        row["cost_basis"] = ("all_reported_input_at_1.25_upper_bound" if start["provider"] == "openai"
                             else "uncached_usage_upper_bound")
        row["status"] = "provider_incomplete"
        extract(start["provider"], raw)
        row["status"] = "schema_failure"
        row["label"], row["derived"] = _parse(row, item)
        row["status"] = "ok"
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return row


def _final_file(phase):
    return "translations.jsonl" if phase == "translation" else "judgments.jsonl"


def _final_record(attempts):
    terminal = attempts[-1]
    return {**_payload(terminal), "attempt_cost_usd": terminal["cost_usd"],
            "cost_usd": float(sum((Decimal(str(r["cost_usd"])) for r in attempts), Decimal(0)))}


def _promote(ledger, attempts):
    return ledger.append(_final_file(attempts[-1]["phase"]), _final_record(attempts))


def judge_one(ledger, item, phase, provider, instrument, plan_hash, freeze, snapshot, send, stop):
    """At most one schema retry; never retry an unknown transport outcome."""
    if phase == "fixtures":
        raise JudgeHalted("B1 inherits fixtures unchanged; new fixture dispatch is forbidden")
    base = _request_record(item, phase, provider, instrument, plan_hash, freeze, snapshot)
    jid = base["judgment_id"]
    done = [r for r in ledger.rows(_final_file(phase)) if r["judgment_id"] == jid]
    if done:
        # Snapshot identity can change as a streaming window grows; the item cannot.
        keys = set(base) - {"input_snapshot_sha256"}
        if any(done[0].get(k) != base[k] for k in keys):
            raise ValueError("Previously judged input/request changed")
        if done[0]["status"] != "ok":
            raise JudgeHalted("Previously failed instrument")
        return done[0]
    started = [r for r in ledger.rows("requests.jsonl") if r["judgment_id"] == jid]
    attempts = [r for r in ledger.rows("attempts.jsonl") if r["judgment_id"] == jid]
    if any(any(r.get(k) != v for k, v in base.items() if k != "input_snapshot_sha256") for r in started):
        raise ValueError("Previously reserved input/request changed")
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
        raw, error_type, http_status = None, None, None
        try:
            raw = send(provider, start["request"])
            if not isinstance(raw, dict):
                raise TypeError("Provider result is not a dictionary")
        except Exception as exc:
            # Never retain exception messages, HTTP headers, or client objects.
            error_type = type(exc).__name__
            status = getattr(exc, "status_code", None)
            http_status = status if type(status) is int else None
            raw = None
        row = _evaluate(start, raw, item)
        row.update(raw_response_sha256=digest(raw) if raw is not None else None,
                   error_type=error_type, http_status=http_status, completed_at_utc=_now())
        row = ledger.finish(row)
        attempts.append(row)
        if row["status"] == "schema_failure" and number == 0:
            continue
        final = _promote(ledger, attempts)
        if final["status"] != "ok":
            stop.set()
            raise JudgeHalted("Failed instrument: " + final["status"])
        return final


def _fixture_expectation(item, instrument):
    expected = item[instrument + "_expected"]
    if instrument == "paper":
        if expected is not None and (type(expected) is not int or expected not in (0, 1)):
            raise ValueError("Invalid fixture binary expectation")
    elif not isinstance(expected, dict):
        raise ValueError("Invalid fixture structured expectation")
    return expected


def fixture_gate(finals, fixtures=None):
    failures, missing, diagnostics = [], [], []
    for item in fixture_inventory() if fixtures is None else fixtures:
        if type(item.get("gating")) is not bool:
            raise ValueError("Fixture gating must be explicit")
        for provider in MODELS:
            for instrument in INSTRUMENTS:
                jid = f"fixtures:{provider}:{instrument}:{item['id']}"
                row, expected = finals.get(jid), _fixture_expectation(item, instrument)
                if row is None or row["status"] != "ok":
                    missing.append(jid)
                    continue
                if instrument == "paper":
                    match = expected is None or (type(row["label"]) is int and row["label"] == expected)
                else:
                    match = all(k in row["derived"] and type(row["derived"][k]) is type(v)
                                and row["derived"][k] == v for k, v in expected.items() if v is not None)
                if not match:
                    (failures if item["gating"] else diagnostics).append(jid)
    return {"pass": not failures and not missing, "failures": failures, "missing": missing,
            "completed_failures": failures, "diagnostic_mismatches": diagnostics,
            "interpretation": "synthetic instrument checks, not human accuracy"}


def record_snapshot(ledger, phase, items, plan_hash, freeze):
    if phase == "fixtures":
        raise JudgeHalted("B1 inherits fixtures unchanged; new fixture snapshots are forbidden")
    content = {"schema": "bilingual-judge-input-v1", "phase": phase, "plan_sha256": plan_hash,
               "freeze_commit": freeze, "items": items}
    identifier = digest(content)
    if not any(r["snapshot_sha256"] == identifier for r in ledger.rows("snapshots.jsonl")):
        ledger.append("snapshots.jsonl", {"snapshot_sha256": identifier, "snapshot": content,
                                          "recorded_at_utc": _now()})
    return identifier


def project_budget(attempts, items, plan):
    """Forecast all remaining calls, not an affordable subset of the inventory.

    A mean-usage forecast cannot guarantee future token consumption;
    each actual call still requires its full independent hard-cap reservation.
    """
    spent = PRIOR_JUDGING_USD + sum((Decimal(str(r["cost_usd"])) for r in attempts
                 if r["budget_bucket"] == "judges"), Decimal(0))
    breakdown, remaining_cost, reserves = {}, Decimal(0), []
    fixtures = {i["id"]: i for i in normalize_items(plan["fixtures"])}
    for provider in MODELS:
        for instrument in INSTRUMENTS:
            rows = [r for r in attempts if r["provider"] == provider and r["instrument"] == instrument
                    and r["budget_bucket"] == "judges"]
            calibration = [r for r in rows if r["phase"] == "fixtures" and r["status"] == "ok"]
            if {r["item_id"] for r in calibration} != set(fixtures):
                raise JudgeHalted("Complete fixture usage is required for the bulk cost forecast")
            longest_query = max((i["query"] for i in [*fixtures.values(), *items]), key=lambda q: len(q.encode()))
            response_bytes = PROJECTION["target_input_allowance_utf8_bytes"]
            for item in items:
                if not item["missing"]:
                    response_bytes = max(response_bytes, len(item["response"].encode()))
            prototype = {"id": "forecast-only", "query": longest_query, "response": "x" * response_bytes}
            reserves.append((provider, Decimal(str(reservation(provider, make_request(provider, instrument, prototype))))))
            fixture_rows = [r for r in rows if r["phase"] == "fixtures"]
            fixture_mean = sum((Decimal(str(r["cost_usd"])) for r in fixture_rows), Decimal(0)) / len(fixtures)
            # Bytes-to-tokens is a frozen planning assumption, NOT the byte-count
            # bound used by reservation(). Output cost is never length-scaled.
            extra_tokens = Decimal(response_bytes) / Decimal(PROJECTION["estimated_utf8_bytes_per_input_token"])
            input_allowance = extra_tokens * Decimal(str(PRICES[provider][0])) * Decimal("1.25") / 1_000_000
            actual = [r for r in rows if r["phase"] in {"target", "translated"}]
            actual_units = {r["judgment_id"] for r in actual}
            actual_mean = (sum((Decimal(str(r["cost_usd"])) for r in actual), Decimal(0)) / len(actual_units)
                           if actual_units else Decimal(0))
            per_call = max(fixture_mean + input_allowance, actual_mean) * Decimal(PROJECTION["safety_multiplier"])
            completed = {r["judgment_id"] for r in rows if r["phase"] in {"target", "translated"} and r["status"] == "ok"}
            remaining = 496 - len(completed)
            if remaining < 0:
                raise ValueError("Judged inventory exceeds planned count")
            projected = per_call * remaining
            remaining_cost += projected
            breakdown[provider + ":" + instrument] = {"remaining_calls": remaining,
                "fixture_mean_usd": str(fixture_mean), "input_allowance_usd": str(input_allowance),
                "observed_target_mean_usd": str(actual_mean), "observed_target_items": len(actual_units),
                "per_call_estimate_usd": str(per_call), "remaining_estimate_usd": str(projected)}
    # Two workers per provider, each with its largest possible next reservation.
    inflight = sum((2 * max(value for p, value in reserves if p == provider) for provider in MODELS), Decimal(0))
    if all(panel["remaining_calls"] == 0 for panel in breakdown.values()):
        inflight = Decimal(0)
    total = spent + remaining_cost + inflight
    return {"pass": total <= API_CAP_USD, "spent_usd": str(spent), "projected_total_usd": str(total),
            "api_cap_usd": str(API_CAP_USD), "by_instrument": breakdown,
            "inflight_reservation_buffer_usd": str(inflight), "prediction_config": dict(PROJECTION),
            "interpretation": "conservative conditional forecast, not a guaranteed cost bound"}


def _record_projection(ledger, snapshot, items, plan):
    attempts = ledger.rows("attempts.jsonl")
    projection = project_budget(attempts, items, plan)
    ledger.append("projections.jsonl", {"input_snapshot_sha256": snapshot,
        "attempts_head_sha256": attempts[-1]["record_sha256"], "projection": projection,
        "recorded_at_utc": _now()})
    if not projection["pass"]:
        raise BudgetExceeded("Full remaining judge inventory cannot fit the conservative $125 forecast; no bulk dispatch")
    return projection


def validate_receipts(ledger, plan, plan_hash, freeze, items):
    """Rebuild every request, raw label, cost, retry and translation dependency."""
    from .translation import selected_items, translated_items
    from .qualification import INHERITED_FREEZE, INHERITED_PLAN_HASH, verify_inherited_prefix
    verify_inherited_prefix(ledger)
    if plan.get("fixtures") != fixture_inventory():
        raise ValueError("Inherited fixture inventory changed")
    ledger._cache.clear()
    snapshots = _unique(ledger.rows("snapshots.jsonl"), "snapshot_sha256")
    requests = _unique(ledger.rows("requests.jsonl"), "attempt_id")
    attempts = _unique(ledger.rows("attempts.jsonl"), "attempt_id")
    translations = _unique(ledger.rows("translations.jsonl"), "judgment_id")
    finals = _unique(ledger.rows("judgments.jsonl"), "judgment_id")
    if set(finals) & set(translations) or not set(attempts) <= set(requests):
        raise ValueError("Unmatched or duplicate receipts")
    originals = normalize_items(items)
    selected = selected_items(originals, plan, require_complete=False)
    translated = translated_items(selected, translations, require_complete=False)
    catalog = {(phase, i["id"]): i for phase, values in (
        ("fixtures", normalize_items(plan["fixtures"])), ("target", originals),
        ("translation", selected), ("translated", translated)) for i in values}
    for identifier, record in snapshots.items():
        content = record["snapshot"]
        binding = ((INHERITED_PLAN_HASH, INHERITED_FREEZE) if content["phase"] == "fixtures"
                   else (plan_hash, freeze))
        if (digest(content) != identifier or content["plan_sha256"] != binding[0]
                or content["freeze_commit"] != binding[1] or content["phase"] not in PHASES):
            raise ValueError("Input snapshot provenance mismatch")
        _unique(content["items"], "id")
        for item in content["items"]:
            if catalog.get((content["phase"], item["id"])) != item:
                raise ValueError("Previously judged input snapshot changed")
    models = {p: set() for p in MODELS}
    observed_status = {}
    for row in attempts.values():
        aid = row["attempt_id"]
        start = requests[aid]
        item = catalog.get((start["phase"], start["item_id"]))
        if item is None or any(row.get(k) != v for k, v in _payload(start).items()):
            raise ValueError("Attempt differs from its reservation/input")
        raw = row.get("raw_response")
        if row.get("raw_response_sha256") != (digest(raw) if raw is not None else None):
            raise ValueError("Raw response hash mismatch")
        computed = _evaluate(start, raw, item)
        computed["status"] = _terminal_status(computed, models[start["provider"]])
        if computed["status"] != "ok":
            computed.update(label=None, derived=None)
        for key in ("status", "cost_usd", "cost_basis", "label", "derived"):
            if row.get(key) != computed[key]:
                raise ValueError("Recomputed attempt mismatch: " + key)
        observed_status[aid] = computed["status"]
        if isinstance(raw, dict):
            models[start["provider"]].add(_model_identity(raw))
    for aid, start in requests.items():
        item = catalog.get((start["phase"], start["item_id"]))
        snap = snapshots.get(start["input_snapshot_sha256"], {}).get("snapshot", {})
        if item is None or snap.get("phase") != start["phase"] or item not in snap.get("items", []):
            raise ValueError("Request lacks immutable input snapshot")
        binding = ((INHERITED_PLAN_HASH, INHERITED_FREEZE) if start["phase"] == "fixtures"
                   else (plan_hash, freeze))
        expected = _request_record(item, start["phase"], start["provider"], start["instrument"],
                                   *binding, start["input_snapshot_sha256"])
        if any(start.get(k) != v for k, v in expected.items()):
            raise ValueError("Request provenance mismatch")
        prefix = start["judgment_id"] + ":"
        number = aid.removeprefix(prefix)
        if number not in {"0", "1"} or aid != prefix + number:
            raise ValueError("Invalid attempt number")
        if number == "1" and observed_status.get(prefix + "0") != "schema_failure":
            raise ValueError("Retry not licensed by original schema failure")
    all_finals = {**finals, **translations}
    for jid, final in all_finals.items():
        related = sorted((r for r in attempts.values() if r["judgment_id"] == jid), key=lambda r: r["attempt_id"])
        if not related or _payload(final) != _final_record(related):
            raise ValueError("Final receipt differs from terminal attempt")
        if (jid in translations) != (final["phase"] == "translation"):
            raise ValueError("Final receipt in wrong ledger")
    attempt_list = list(attempts.values())
    heads = {r["record_sha256"]: n + 1 for n, r in enumerate(attempt_list)}
    for record in ledger.rows("projections.jsonl"):
        stop = heads.get(record["attempts_head_sha256"])
        snapshot = snapshots.get(record["input_snapshot_sha256"])
        if stop is None or snapshot is None:
            raise ValueError("Projection lacks receipt/input provenance")
        expected = project_budget(attempt_list[:stop], snapshot["snapshot"]["items"], plan)
        if expected != record["projection"]:
            raise ValueError("Cost projection audit mismatch")
    # A crashed process may have finished an attempt without promoting its final.
    failed = {j for j, r in all_finals.items() if r["status"] != "ok"}
    for row in attempts.values():
        if row["status"] != "ok" and (row["status"] != "schema_failure" or row["attempt_id"].endswith(":1")):
            failed.add(row["judgment_id"])
    return {"unknown_attempts": sorted(set(requests) - set(attempts)),
            "failed_instruments": sorted(failed), "model_drift": any(len(v) > 1 for v in models.values()),
            "spent_usd": float(ledger.spent()),
            "budget_spent_usd": {b: float(ledger.spent(b)) for b in CAPS},
            "models": {p: sorted(v, key=str) for p, v in models.items()},
            "finals": finals, "translations": translations}


def _require_healthy(state):
    if (state["unknown_attempts"] or state["failed_instruments"] or state["model_drift"]
            or any(Decimal(str(state["budget_spent_usd"][b])) > cap for b, cap in CAPS.items())):
        raise JudgeHalted("Persisted failed, over-budget, or unresolved calls; no dispatch")


def _validate_contract(plan, plan_hash, freeze, phase, n_blocks, judge_root, send, plan_path):
    if phase == "fixtures":
        raise JudgeHalted("B1 inherits fixtures unchanged; new fixture dispatch is forbidden")
    if not re.fullmatch(r"[0-9a-f]{40}", freeze or "") or not re.fullmatch(r"[0-9a-f]{64}", plan_hash or ""):
        raise ValueError("Full freeze and plan hashes required")
    if phase not in PHASES or type(n_blocks) is not int or not 1 <= n_blocks <= 20:
        raise ValueError("Unsupported phase/window")
    if plan.get("judges") != judge_config():
        raise ValueError("Judge configuration differs from frozen plan")
    if plan.get("fixtures") != fixture_inventory() or len(plan["fixtures"]) != 32:
        raise ValueError("Fixture inventory differs from frozen plan")
    _unique(plan["fixtures"], "id")
    for item in plan["fixtures"]:
        if type(item.get("gating")) is not bool:
            raise ValueError("Fixture gating must be explicit")
        for instrument in INSTRUMENTS:
            _fixture_expectation(item, instrument)
    from .protocol import translation_ids
    ids = plan.get("translation_item_ids")
    if not isinstance(ids, list) or len(ids) != 16 or not all(isinstance(i, str) for i in ids) or len(set(ids)) != 16:
        raise ValueError("Exactly sixteen unique frozen translation IDs required")
    if ids != translation_ids():
        raise ValueError("Translation IDs differ from the fixed selection")
    if send is None:
        from .protocol import ROOT, load_plan
        prior_cost_provenance()
        expected = ROOT / LEDGER_PATH
        _no_symlinks(expected)
        if Path(judge_root).absolute() != expected.absolute():
            raise ValueError("One canonical pilot ledger required; no budget reset")
        if plan_path is None or sha(plan_path) != plan_hash or load_plan(plan_path, freeze=freeze) != plan:
            raise ValueError("Live execution requires the source-bound frozen plan")
        from .controller import _require_ignored, verify_ci, base
        _require_ignored(expected / "requests.jsonl")
        base.verify_public(plan_hash, Path(plan_path).resolve().relative_to(ROOT).as_posix(), freeze)
        verify_ci(freeze)
    return plan


def _live_sender():
    from anthropic import Anthropic
    from openai import OpenAI
    clients = {}

    def send(provider, request):
        if provider not in clients:
            clients[provider] = (OpenAI(max_retries=0, timeout=180) if provider == "openai"
                                 else Anthropic(max_retries=0, timeout=180))
        client = clients[provider]
        result = client.responses.create(**request) if provider == "openai" else client.messages.create(**request)
        return result.model_dump(mode="json", exclude_none=True)
    return send


def execute_run(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, phase="target", send=None, plan_path=None):
    """Judge immutable prefixes of 1..20 blocks; translation has its own runner.

    raw_audit.items_from_raw must validate provenance before returning rows.
    Missing rows remain missing and are returned in missing_ids, never labeled.
    """
    from .halt import halt_on_error
    with halt_on_error(judge_root, plan_hash, freeze, production=send is None):
        if phase == "fixtures":
            raise JudgeHalted("B1 inherits fixtures unchanged; new fixture dispatch is forbidden")
        if phase not in {"target", "translated"}:
            raise ValueError("Unsupported judge phase")
        return _execute(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, phase, send, plan_path)


def _execute(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, phase, send, plan_path):
    from .halt import halt_on_error
    with halt_on_error(judge_root, plan_hash, freeze, production=send is None):
        return _execute_impl(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, phase, send, plan_path)


def _execute_impl(raw_root, judge_root, plan, plan_hash, freeze, n_blocks, phase, send, plan_path):
    from .halt import FILENAME, check_halt, write_halt
    from .translation import selected_items, translated_items
    halt_path = Path(judge_root).parent / FILENAME

    def publish_error(exc):
        if send is None:
            write_halt(halt_path, plan_hash, freeze, type(exc).__name__)

    _validate_contract(plan, plan_hash, freeze, phase, n_blocks, judge_root, send, plan_path)
    with Ledger(judge_root) as ledger:
        from .qualification import verify_inherited_prefix
        verify_inherited_prefix(ledger)
        from .raw_audit import items_from_raw
        if send is None:
            from .raw_audit import audit_raw_window
            report = audit_raw_window(raw_root, plan, n_blocks=None, allow_test=False)
            if (report.get("pass") is not True or report.get("production_eligible") is not True
                    or report.get("plan_sha256") != plan_hash or report.get("freeze_commit") != freeze):
                raise JudgeHalted("Production raw audit or freeze binding failed")
        all_items = normalize_items(items_from_raw(raw_root, plan, n_blocks=None))
        if len(all_items) > 480:
            raise ValueError("Target inventory exceeds frozen pilot size")
        state = validate_receipts(ledger, plan, plan_hash, freeze, all_items)
        _require_healthy(state)
        if not fixture_gate(state["finals"], plan["fixtures"])["pass"]:
            raise JudgeHalted("Unambiguous synthetic fixture checks must pass before targets/translation")
        if phase == "target":
            from .raw_audit import items_from_raw
            items = normalize_items(items_from_raw(raw_root, plan, n_blocks=n_blocks))
            catalog = {i["id"]: i for i in all_items}
            if any(catalog.get(i["id"]) != i for i in items):
                raise ValueError("Selected raw window changed during audit")
        else:
            selected = selected_items(all_items, plan)
            items = selected if phase == "translation" else translated_items(selected, state["translations"])
        snapshot = record_snapshot(ledger, phase, items, plan_hash, freeze)
        projection = _record_projection(ledger, snapshot, items, plan) if phase in {"target", "translated"} else None
        missing = [i["id"] for i in items if i["missing"]]
        items = [i for i in items if not i["missing"]]
        sender, stop = send or _live_sender(), threading.Event()
        if send is None:
            live_sender = sender

            def sender(provider, request):
                check_halt(halt_path, plan_hash, freeze)
                return live_sender(provider, request)

        if phase == "target":
            # Only the first two fixed-order items precede the usage refresh.
            # Resumes recover their immutable calls without charging again.
            for item in items[:PROJECTION["refresh_after_first_target_items"]]:
                for provider in MODELS:
                    for instrument in INSTRUMENTS:
                        judge_one(ledger, item, phase, provider, instrument, plan_hash, freeze, snapshot, sender, stop)
            projection = _record_projection(ledger, snapshot, items, plan)

        def worker(provider, shard):
            for item in items[shard::2]:
                instruments = ("translation",) if phase == "translation" else INSTRUMENTS
                for instrument in instruments:
                    try:
                        judge_one(ledger, item, phase, provider, instrument, plan_hash, freeze, snapshot, sender, stop)
                    except BaseException as exc:
                        stop.set()
                        publish_error(exc)
                        raise

        error = None
        providers = ("anthropic",) if phase == "translation" else MODELS
        with ThreadPoolExecutor(max_workers=4) as pool:
            try:
                futures = [pool.submit(worker, p, shard) for p in providers for shard in range(2)]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        stop.set()
                        error = error or exc
            except BaseException as exc:
                stop.set()
                publish_error(exc)
                raise
        state = validate_receipts(ledger, plan, plan_hash, freeze, all_items)
        if error:
            raise error
        _require_healthy(state)
        gate = fixture_gate(state["finals"], plan["fixtures"])
        if not gate["pass"]:
            raise JudgeHalted("Unambiguous synthetic fixture check failed")
        return {"status": "complete_with_missing" if missing else "complete", "phase": phase,
                "n_blocks": n_blocks, "items": len(items), "missing_ids": missing,
                "spent_usd": state["spent_usd"], "budget_spent_usd": state["budget_spent_usd"],
                "budget_caps_usd": {b: float(c) for b, c in CAPS.items()}, "fixture_gate": gate,
                "cost_projection": projection}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--judge-root", type=Path, required=True)
    parser.add_argument("--phase", choices=["target", "translated"], default="target")
    parser.add_argument("--n-blocks", type=int, choices=range(1, 21), default=20)
    parser.add_argument("--env-file", type=Path, help="Explicit original-repository .env; never auto-discovered")
    args = parser.parse_args()
    from .protocol import load_plan
    plan = load_plan(args.plan, freeze=args.freeze)
    if not args.execute:
        print(canonical({"status": "offline", "configuration_matches": plan.get("judges") == judge_config(),
                         "plan_sha256": sha(args.plan), "no_paid_calls": True}))
        return
    if args.env_file is not None:
        if not args.env_file.is_file():
            parser.error("Explicit env file does not exist")
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=False)
    try:
        result = execute_run(args.raw_root, args.judge_root, plan, sha(args.plan), args.freeze,
                             args.n_blocks, args.phase, plan_path=args.plan)
    except Exception as exc:
        parser.exit(1, type(exc).__name__ + ": pilot halted; inspect local receipts\n")
    print(canonical(result))


if __name__ == "__main__":
    main()
