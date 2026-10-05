"""Local-only orchestration; no pod management or execution authority on import.

Use ReceiptJournal and the common judge Ledger as nested contexts. Production
senders come from http_sender, after the parent's freeze and lifecycle checks.
Generation is GPU billed: its exact HTTP bytes never acquire invented API costs
or provider identities. Projections are separate, explicitly derived records.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import urlsplit

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import (
    Halted, Ledger, _no_symlinks, _signature, _sync_directory, read_events,
)
from experiments.openrouter_swap.providers import (
    ENDPOINT, _amount, _public_body, parse_result, receipt_cost, reservation,
)
from experiments.openrouter_swap.runner import Runner as CommonRunner
from . import analysis, protocol

ROOT = Path(__file__).resolve().parents[2]
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
GENERATION_DEADLINE_SECONDS, JUDGE_DEADLINE_SECONDS = 300, 600
JUDGES, PRIVACY = protocol.JUDGES, protocol.PRIVACY


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate response field")
            result[key] = value
        return result
    value = json.loads(body, object_pairs_hook=pairs)
    common.canonical(value)  # Reject NaN, infinities and overflow.
    return value


def public_response(body, credential=None):
    """Check decoded keys and values as well as wire bytes; never print secrets."""
    if credential and credential.encode() in body:
        raise ValueError("Unsafe response")
    try:
        value = strict_json(body)
    except (ValueError, UnicodeError):
        # Invalid JSON is still retained unless it contains an escaped credential.
        if credential:
            decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)),
                             body.decode("utf-8", errors="replace"))
            if credential in decoded.replace(r"\/", "/"):
                raise ValueError("Unsafe response") from None
        return
    def check(item):
        if isinstance(item, str) and credential and credential in item:
            raise ValueError("Unsafe response")
        if isinstance(item, dict):
            for key, val in item.items():
                check(key)
                check(val)
        elif isinstance(item, list):
            for val in item:
                check(val)
    check(value)
    _public_body(value)


@dataclass(frozen=True)
class HTTPReceipt:
    status: int | None
    body: bytes
    elapsed_seconds: float
    error: str | None = None


def _http_worker(pipe, endpoint, payload, credential, output, seconds):
    """One POST, no proxy, redirects or retries; headers never cross IPC."""
    from urllib import error, request
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        headers = {"Content-Type": "application/json"}
        if credential is not None:
            headers["Authorization"] = "Bearer " + credential
        req = request.Request(endpoint, data=payload, headers=headers, method="POST")
        opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
        try:
            response = opener.open(req, timeout=seconds)
        except error.HTTPError as exc:
            response = exc
        with response, open(output, "xb", buffering=0) as stream:
            pipe.send({"status": response.code})
            count = 0
            while True:
                part = response.read1(65536)
                if not part:
                    break
                stream.write(part)
                count += len(part)
                if count > MAX_RESPONSE_BYTES:
                    raise ValueError("Oversized response")
            os.fsync(stream.fileno())
        pipe.send({"done": True})
    except BaseException:
        pipe.send({"error": "HTTPFailure"})
    finally:
        pipe.close()


def http_sender(endpoint, *, timeout_seconds, api_key=None):
    """Killable process deadline covers DNS/connect/TLS/upload/read, not just I/O.

    The private spool preserves partial response bytes on timeout. Sensitive
    echoes fail closed before public persistence; they are not redacted into a
    forged successful receipt. Callers retain the unresolved reservation.
    """
    parsed = urlsplit(endpoint)
    local = (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
             and parsed.port is not None and 0 < parsed.port < 65536
             and parsed.path == "/v1/chat/completions" and not parsed.username
             and not parsed.password and not parsed.query and not parsed.fragment)
    if not local and endpoint != ENDPOINT:
        raise ValueError("Only exact OpenRouter or loopback vLLM endpoint allowed")
    if local and api_key is not None:
        raise ValueError("Judge credentials must never reach the local generation server")
    if not local and (not isinstance(api_key, str) or not api_key or any(c.isspace() for c in api_key)):
        raise ValueError("Local OpenRouter credential required")
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 600:
        raise ValueError("Explicit bounded total HTTP deadline required")
    def send(request):
        _public_body(request)
        payload = common.canonical(request).encode()
        public_response(payload, api_key)
        start = time.monotonic()
        status, problem, done = None, None, False
        ctx = multiprocessing.get_context("spawn")
        receive, transmit = ctx.Pipe(duplex=False)
        with tempfile.TemporaryDirectory(prefix="kolibri-http-") as temporary:
            output = Path(temporary) / "body"
            worker = ctx.Process(target=_http_worker, args=(transmit, endpoint, payload, api_key,
                                                          str(output), timeout_seconds))
            try:
                worker.start()
                transmit.close()
                while not done and problem is None:
                    remaining = timeout_seconds - (time.monotonic() - start)
                    if remaining <= 0 or not receive.poll(max(0, remaining)):
                        problem = "TotalDeadlineExceeded"
                        break
                    try:
                        message = receive.recv()
                    except EOFError:
                        problem = "HTTPWorkerExited"
                        break
                    status = message.get("status", status)
                    done, problem = message.get("done", False), message.get("error")
            finally:
                if worker.pid is not None:
                    if worker.is_alive():
                        worker.terminate()
                    worker.join(.5)
                    if worker.is_alive():
                        worker.kill()
                        worker.join(.5)
                transmit.close()
                receive.close()
            body = output.read_bytes() if output.exists() else b""
            try:
                public_response(body, api_key)
            except ValueError:
                body, problem = b"", "UnsafeReceipt"
            return HTTPReceipt(status, body, time.monotonic() - start, problem)
    send._kolibri_live = True
    send.channel = "local" if local else "judge"
    send.timeout_seconds = timeout_seconds
    return send


def local_request(model, item_id, messages, seed=None):
    expected_seed = int(sha(item_id.encode())[:8], 16) & 0x7fffffff
    if seed is not None and (type(seed) is not int or seed != expected_seed):
        raise Halted("Frozen item seed differs from deterministic ID seed")
    seed = expected_seed
    return {"model": model["id"], "messages": deepcopy(messages), "max_tokens": 4096,
            "temperature": .5, "top_p": 1., "top_k": -1, "reasoning_effort": "medium",
            "chat_template_kwargs": {"reasoning_effort": "medium"},
            "seed": seed, "stream": False}


def local_result(model, raw):
    """No OpenRouter-shaped fake provider or price is added to local receipts."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
        raise ValueError("Local completion ID absent")
    if raw.get("model") != model["id"] or raw.get("error") is not None:
        raise ValueError("Local model/error receipt mismatch")
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("One local completion required")
    message = choices[0].get("message", {})
    if message.get("role") != "assistant" or message.get("content") is not None and not isinstance(message["content"], str):
        raise ValueError("Local assistant text required")
    usage = raw.get("usage", {})
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("prompt_tokens", "completion_tokens")):
        raise ValueError("Local token usage unavailable")
    stop = choices[0].get("finish_reason")
    if stop not in {"stop", "length", "content_filter", "refusal"}:
        raise ValueError("Unknown local finish reason")
    text = message.get("content") or ""
    refused = bool(message.get("refusal")) or stop in {"content_filter", "refusal"}
    missing = refused or not text.strip()
    cap = stop == "length"
    return {"schema": "kolibri-local-projection-v1", "derived_not_raw": True,
            "model": raw["model"], "response": text, "missing": missing, "refusal": refused,
            "complete": stop == "stop" and not refused, "cap_hit": cap, "stop_reason": stop,
            "status": "refusal" if refused else "incomplete" if cap else "empty" if missing else "ok",
            "reasoning_transplanted": False}


class ReceiptJournal:
    """Full requests and exact response bytes, with fsynced, hash-chained events."""
    def __init__(self, root, freeze, plan_hash):
        self.root = Path(root).absolute()
        self.binding = {"schema": "kolibri-http-journal-v1", "freeze": freeze, "plan_sha256": plan_hash}
        self.lock = None
        self.mutex = threading.RLock()
        self._cache = None

    def __enter__(self):
        _no_symlinks(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _no_symlinks(self.root / ".lock")
        self.lock = (self.root / ".lock").open("a+b")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.signature = _signature(self.root / "events.jsonl")
            self.events = read_events(self.root / "events.jsonl")
            if _signature(self.root / "events.jsonl") != self.signature:
                raise Halted("HTTP journal changed during open")
            self._cache = None
            if not self.events:
                self.append("binding", self.binding)
            if self.events[0]["kind"] != "binding" or self.events[0]["data"] != self.binding:
                raise Halted("HTTP journal source binding changed")
            self.records()
        except BaseException:
            self.lock.close()
            self.lock = None
            raise
        return self

    def __exit__(self, *_):
        try:
            if read_events(self.root / "events.jsonl") != self.events:
                raise Halted("HTTP journal changed while locked")
        finally:
            self.lock.close()
            self.lock = None

    def append(self, kind, data):
        with self.mutex:
            if self.lock is None or _signature(self.root / "events.jsonl") != self.signature:
                raise Halted("HTTP journal lock or signature changed")
            _public_body(data)
            event = {"seq": len(self.events)+1, "previous": self.events[-1]["sha256"] if self.events else None,
                     "utc": datetime.now(timezone.utc).isoformat(), "kind": kind, "data": deepcopy(data)}
            event["sha256"] = common.digest(event)
            with (self.root / "events.jsonl").open("ab") as handle:
                handle.write((common.canonical(event)+"\n").encode())
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(self.root)
            self.signature = _signature(self.root / "events.jsonl")
            self.events.append(event)
            if self._cache is not None:
                if kind == "dispatch":
                    self._cache[data["call_id"]] = {**deepcopy(data), "status": "pending"}
                elif kind == "response":
                    self._cache[data["call_id"]].update(deepcopy(data))

    def records(self, verify=False):
        with self.mutex:
            if self._cache is not None and not verify:
                return deepcopy(self._cache)
            records, decisions = {}, set()
            for event in self.events[1:]:
                data = deepcopy(event["data"])
                if event["kind"] == "dispatch":
                    if set(data) != {"call_id", "request", "request_sha256", "phase", "metadata", "channel"}:
                        raise Halted("Malformed dispatch")
                    _public_body(data)
                    call = data["call_id"]
                    if call in records or data["request_sha256"] != common.digest(data["request"]):
                        raise Halted("Duplicate or changed dispatch")
                    records[call] = {**data, "status": "pending"}
                elif event["kind"] == "response":
                    if (set(data) != {"call_id", "status", "http_status", "transport_error", "elapsed_seconds",
                                      "error_type", "body", "projection"}
                            or data["status"] not in {"received", "unresolved"}
                            or type(data["elapsed_seconds"]) not in (int, float)
                            or not math.isfinite(data["elapsed_seconds"]) or data["elapsed_seconds"] < 0
                            or data["http_status"] is not None and (type(data["http_status"]) is not int
                                                                   or not 100 <= data["http_status"] <= 599)):
                        raise Halted("Malformed HTTP response receipt")
                    call = data["call_id"]
                    if call not in records or records[call]["status"] != "pending":
                        raise Halted("Response lacks unique dispatch")
                    expected = "raw/" + sha(call.encode()) + ".bin"
                    if data["body"]["path"] != expected:
                        raise Halted("Unsafe response path")
                    path = self.root / expected
                    _no_symlinks(path)
                    body = path.read_bytes()
                    if (type(data["body"]["bytes"]) is not int or len(body) != data["body"]["bytes"]
                            or sha(body) != data["body"]["sha256"]):
                        raise Halted("Raw HTTP receipt changed")
                    records[call].update(data)
                elif event["kind"] == "decision":
                    if data["name"] in decisions:
                        raise Halted("Decision duplicated")
                    decisions.add(data["name"])
                else:
                    raise Halted("Unknown HTTP journal event")
            self._cache = records
            return deepcopy(records)

    def existing(self, call_id):
        with self.mutex:
            return deepcopy(self._cache.get(call_id))

    def unresolved(self, channel=None, phases=None):
        with self.mutex:
            return any(r["status"] != "received" for r in self._cache.values()
                       if (channel is None or r["channel"] == channel)
                       and (phases is None or r["phase"] in phases))

    def raw(self, record):
        return strict_json((self.root / record["body"]["path"]).read_bytes())

    def finish(self, call_id, receipt, projection, problem):
        with self.mutex:
            if not isinstance(receipt, HTTPReceipt) or type(receipt.body) is not bytes:
                raise Halted("Transport must return exact HTTPReceipt bytes")
            path = self.root / "raw" / (sha(call_id.encode()) + ".bin")
            _no_symlinks(path)
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as handle:
                handle.write(receipt.body)
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(path.parent)
            self.append("response", {"call_id": call_id, "status": "unresolved" if problem else "received",
                "http_status": receipt.status, "transport_error": receipt.error,
                "elapsed_seconds": receipt.elapsed_seconds, "error_type": problem,
                "body": {"path": path.relative_to(self.root).as_posix(), "bytes": len(receipt.body),
                         "sha256": sha(receipt.body)}, "projection": projection})

    def decision(self, name):
        return next((deepcopy(e["data"]["value"]) for e in self.events
                     if e["kind"] == "decision" and e["data"]["name"] == name), None)


class Runner(CommonRunner):
    """Parent supplies verified plan, canonical roots, transports and GPU evidence."""
    def __init__(self, plan, freeze, plan_hash, ledger, receipts, local_sender=None, judge_sender=None,
                 *, _freeze_verified=False):
        if not re.fullmatch(r"[0-9a-f]{40}", freeze) or not re.fullmatch(r"[0-9a-f]{64}", plan_hash):
            raise Halted("Full freeze and plan digest required")
        if (plan["judges"] != JUDGES or plan["models"] != protocol.MODELS
                or plan["fixtures"] != judges.fixture_items()
                or any(plan[p] != protocol.inventory(p) for p in ("screen", "main"))):
            raise Halted("Changed judge routes, fixtures or local model panel")
        if ledger.cap != Decimal("45") or not 0 < ledger.screen_cap <= Decimal("20"):
            raise Halted("Explicit judge-only budget binding required")
        if not 0 < ledger.screen_cap <= ledger.cap or receipts.binding != {
                "schema": "kolibri-http-journal-v1", "freeze": freeze, "plan_sha256": plan_hash}:
            raise Halted("Changed receipt or screening budget binding")
        self.receipts, self.local_sender = receipts, local_sender
        self._channel_locks = {name: threading.RLock() for name in ("local", "judge")}
        for sender, channel, seconds in ((local_sender, "local", 300), (judge_sender, "judge", 600)):
            if getattr(sender, "_kolibri_live", False) and (not _freeze_verified
                    or sender.channel != channel or sender.timeout_seconds != seconds):
                raise Halted("Live dispatch requires verified freeze and exact channel deadline")
        self._existing_only = False
        self._design_hash = common.digest(plan)
        super().__init__(deepcopy(plan), freeze, plan_hash, ledger, judge_sender)
        self.check_sources()
        self.audit()

    @classmethod
    def from_frozen(cls, plan_path, freeze, ledger, receipts, local_sender=None, judge_sender=None):
        plan = protocol.verify(plan_path, freeze)
        if not plan.get("launch_authorized") or plan.get("metadata_blockers"):
            raise Halted("Approved source freeze required")
        return cls(plan, freeze, protocol.sha(plan_path), ledger, receipts, local_sender, judge_sender,
                   _freeze_verified=True)

    def check_sources(self):
        if common.digest(self.plan) != self._design_hash or not self.plan.get("source_hashes"):
            raise Halted("Plan changed or source closure absent")
        for name, digest in self.plan["source_hashes"].items():
            path = ROOT / name
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise Halted("Unsafe source path")
            _no_symlinks(path)
            if sha(path.read_bytes()) != digest:
                raise Halted("Frozen source bytes changed")

    def _exchange(self, call_id, request, phase, metadata, channel, sender, spec):
        with self._channel_locks[channel]:
            return self._exchange_locked(call_id, request, phase, metadata, channel, sender, spec)

    def _exchange_locked(self, call_id, request, phase, metadata, channel, sender, spec):
        self.check_sources()
        existing = self.receipts.existing(call_id)
        dispatch = {"call_id": call_id, "request": request, "request_sha256": common.digest(request),
                    "phase": phase, "metadata": {**metadata, "freeze": self.freeze, "plan_sha256": self.plan_hash},
                    "channel": channel}
        if existing is not None:
            if any(existing[k] != value for k, value in dispatch.items()) or existing["status"] != "received":
                raise Halted("Changed or unresolved request; no automatic resend")
            return existing["projection"]
        if sender is None or self._existing_only or channel == "judge" and self.stop.is_set():
            raise Halted("No new dispatch permission")
        self.require_resolved(channel=channel)
        # Snapshot both journals atomically, but never hold locks during HTTP.
        with self.ledger._mutex, self.receipts.mutex:
            if channel == "judge":
                self.ledger.reserve(call_id, request, reservation(spec, request), phase, dispatch["metadata"])
            self.receipts.append("dispatch", dispatch)
        raw, cost, result, problem = None, None, None, None
        try:
            receipt = sender(deepcopy(request))
            if not isinstance(receipt, HTTPReceipt):
                raise TypeError("Exact HTTPReceipt required")
        except Exception:
            receipt = HTTPReceipt(None, b"", 0., "TransportException")
        try:
            raw = strict_json(receipt.body)
            _public_body(raw)
            if channel == "judge":
                cost = receipt_cost(spec, raw)
            if receipt.error is not None or receipt.status != 200:
                raise ValueError("Ambiguous or unsuccessful HTTP request")
            if channel == "local":
                result = local_result(spec, raw)
            else:
                if cost is None:
                    raise ValueError("Judge accounting unavailable")
                result = parse_result(spec, raw)
        except Exception as exc:
            problem = type(exc).__name__
        with self.ledger._mutex, self.receipts.mutex:
            self.receipts.finish(call_id, receipt, result, problem)
            if channel == "judge":
                self.ledger.settle(call_id, raw if isinstance(raw, dict) else None, cost,
                                   error=ValueError() if problem else None)
        if problem:
            if channel == "judge":
                self.stop.set()
            raise Halted("HTTP/receipt failure retained; no automatic retry")
        return result

    def call(self, call_id, spec, request, phase, metadata):
        request = deepcopy(request)
        request["provider"].update(PRIVACY)
        if "temperature" in request:
            raise Halted("Judge temperature must not be sent")
        return self._exchange(call_id, request, phase, metadata, "judge", self.sender, spec)

    def parsed_call(self, call_id, spec):
        row = self.receipts.existing(call_id)
        if row is None:
            return None
        if row["status"] != "received":
            raise Halted("Unresolved HTTP receipt cannot be replayed")
        return row["projection"]

    def generate(self, item, source=None):
        if item != self.catalog[item["id"]]:
            raise Halted("Unplanned generation")
        if item["kind"] == "final":
            donor = self.parsed_call("gen:" + item["source_id"], self.plan["models"][item["model"]])
            if donor is None or donor["missing"] or source != donor["response"]:
                raise Halted("Final requires exact donor final content, never reasoning")
        model = self.plan["models"][item["model"]]
        request = local_request(model, item["id"], common.messages(item, source), item["seed"])
        return self._exchange("gen:" + item["id"], request, item["phase"],
            {"kind": "generation", "item_id": item["id"], "role": item["kind"],
             "model": item["model"], "block": item["block"]}, "local", self.local_sender, model)

    def route_fixture(self, model):
        spec = self.plan["models"][model]
        call_id = "route:" + model
        request = local_request(spec, call_id, [{"role": "user", "content": "Reply with exactly OK."}])
        result = self._exchange(call_id, request, "fixtures", {"kind": "route", "model": model},
                                "local", self.local_sender, spec)
        return {**result, "pass": result["complete"] and not result["missing"]
                and result["response"].strip() in ("OK", "OK.")}

    def run_fixtures(self):
        self.require_resolved()
        routes = [self.route_fixture(m) for m in self.plan["models"]]
        rows = self.fixture_rows()
        gate = judges.fixture_gate(rows)
        return {"pass": gate["pass"] and all(r["pass"] for r in routes), "judges": gate, "routes": routes}

    def require_fixtures(self):
        result = self.fixture_gate()
        if not result["pass"]:
            raise Halted("Fixture gate failed")
        return result

    def require_resolved(self, channel=None, phases=None):
        selected = lambda r: phases is None or r["phase"] in phases
        with self.ledger._mutex:
            if channel != "local" and any(selected(r) and (r["status"] != "settled" or r.get("over_reservation"))
                                          for r in self.ledger._calls.values()):
                raise Halted("Unresolved or over-reservation judge call")
        if self.receipts.unresolved(channel, phases):
            raise Halted("Unresolved local or judge request blocks dispatch")

    def rows(self, phase, models=None):
        rows = []
        for block in self.plan[phase]:
            for item in block["finals"]:
                record = self.receipts.existing("gen:" + item["id"])
                output = record["projection"] if record and record["status"] == "received" else None
                row = {**item, "response": None if output is None or output["missing"] else output["response"],
                       "status": output["status"] if output else record["status"] if record else "not_generated",
                       "cap_hit": output["cap_hit"] if output else False, "labels": {}}
                if row["response"] is not None:
                    for judge in self.plan["judges"]:
                        row["labels"][judge] = {}
                        for instrument in judges.INSTRUMENTS:
                            for attempt in (0, 1):
                                rec = self.receipts.existing(f"judge:{item['id']}:{judge}:{instrument}:a{attempt}")
                                if rec is None or rec["status"] != "received":
                                    continue
                                value = rec["projection"]
                                if not value["complete"] or value["missing"]:
                                    continue
                                try:
                                    parsed = judges.parse(instrument, row["response"], value["response"])["reduced"]
                                except (ValueError, KeyError, TypeError):
                                    continue
                                row["labels"][judge][instrument] = parsed["paper_positive"] if instrument == "paper" else parsed
                                break
                rows.append(row)
        return rows

    def complete(self, phase, initial=False):
        self.complete_generation(phase, initial)
        for block in self.plan[phase]:
            if initial and block["block"] > 2:
                continue
            for item in block["finals"]:
                output = self.parsed_call("gen:"+item["id"], self.plan["models"][item["model"]])
                if output is None or output["missing"]:
                    continue
                for judge in self.plan["judges"]:
                    for instrument in judges.INSTRUMENTS:
                        for attempt in (0, 1):
                            rec = self.receipts.existing(f"judge:{item['id']}:{judge}:{instrument}:a{attempt}")
                            if rec is None or rec["status"] != "received":
                                raise Halted("Judging inventory incomplete")
                            value = rec["projection"]
                            if not value["complete"] or value["missing"]:
                                break
                            try:
                                judges.parse(instrument, output["response"], value["response"])
                            except (ValueError, KeyError, TypeError):
                                continue
                            break

    def initial_audit(self):
        self.require_fixtures()
        self.complete("screen", initial=True)
        self.audit()
        selected = {call: row for call, row in self.receipts.records().items()
                    if row["phase"] == "fixtures" or row["phase"] == "screen" and
                    self.catalog[row["metadata"]["item_id"]]["block"] <= 2}
        return {"pass": True, "blocks": [1, 2], "receipts_sha256": common.digest(selected)}

    def approve_initial(self, report):
        if report != self.initial_audit():
            raise Halted("Initial audit approval differs")
        if self.receipts.decision("screen_initial") == report:
            return
        self.receipts.append("decision", {"name": "screen_initial", "value": report})

    def _stage(self, phase, initial=False):
        if phase not in {"screen", "main"} or initial and phase != "screen":
            raise Halted("Invalid collection stage")
        self.require_resolved(channel="local")
        # Fixture replay reads existing records only and must not wait for target judges.
        if not self.fixture_gate()["pass"]:
            raise Halted("Fixture gate failed")
        if phase == "screen" and not initial and self.receipts.decision("screen_initial") != self.initial_audit():
            raise Halted("Two-block local audit approval required before bulk screen")
        if phase == "main":
            admission = self.receipts.decision("main_admission")
            if admission is None or admission != self.main_admission(**admission["evidence"]) or not admission["fits"]:
                raise Halted("Qualified measured main admission required")
    def generate_blocks(self, phase, initial=False):
        """Generation-only phase; never submits or waits for target judges."""
        self._stage(phase, initial)
        for block in self.plan[phase]:
            if initial and block["block"] > 2:
                continue
            sources = {item["id"]: self.generate(item) for item in block["sources"]}
            for item in block["finals"]:
                donor = sources[item["source_id"]]
                if not donor["missing"]:
                    self.generate(item, donor["response"])
        return self.complete_generation(phase, initial)

    def judge_blocks(self, phase, initial=False):
        """Judge saved final content only; safe after the parent deletes the GPU."""
        if phase not in {"screen", "main"}:
            raise Halted("Invalid judging stage")
        self.require_resolved(channel="judge")
        for block in self.plan[phase]:
            if initial and block["block"] > 2:
                continue
            for item in block["finals"]:
                record = self.receipts.existing("gen:"+item["id"])
                if record is None or record["status"] != "received" or record["projection"]["missing"]:
                    continue
                for judge in self.plan["judges"]:
                    for instrument in judges.INSTRUMENTS:
                        self.judge(item["id"], record["projection"]["response"], judge, instrument, phase)
        return self.rows(phase)

    def complete_generation(self, phase, initial=False):
        observed, skipped = [], []
        for block in self.plan[phase]:
            if initial and block["block"] > 2:
                continue
            for item in block["sources"] + block["finals"]:
                if item["kind"] == "final":
                    donor = self.parsed_call("gen:"+item["source_id"], self.plan["models"][item["model"]])
                    if donor is not None and donor["missing"]:
                        skipped.append(item["id"])
                        continue
                value = self.parsed_call("gen:"+item["id"], self.plan["models"][item["model"]])
                if value is None:
                    raise Halted("Generation inventory incomplete")
                observed.append(item["id"])
        return {"complete": True, "phase": phase, "initial": initial, "generation_calls": len(observed),
                "skipped_missing_donor": skipped, "judge_completion_required": False}

    def run_blocks(self, phase, models=None, initial=False):
        self.generate_blocks(phase, initial)
        return self.judge_blocks(phase, initial)

    def fixture_gate(self):
        # No sender toggles: safe while a separate target-judge channel is active.
        rows, routes = [], []
        records = self.receipts.records(verify=True)
        for model in self.plan["models"]:
            rec = records.get("route:"+model)
            value = rec["projection"] if rec and rec["status"] == "received" else None
            routes.append(bool(value and value["complete"] and not value["missing"]
                               and value["response"].strip() in ("OK", "OK.")))
        for item in self.plan["fixtures"]:
            for judge in self.plan["judges"]:
                for instrument in judges.INSTRUMENTS:
                    result = {"item_id": item["id"], "judge": judge, "instrument": instrument,
                              "status": "missing", "raw_text": ""}
                    for attempt in (0, 1):
                        rec = records.get(f"judge:{item['id']}:{judge}:{instrument}:a{attempt}")
                        value = rec["projection"] if rec and rec["status"] == "received" else None
                        if not value or not value["complete"] or value["missing"]:
                            continue
                        try:
                            judges.parse(instrument, item["response"], value["response"])
                        except (ValueError, KeyError, TypeError):
                            continue
                        result.update(status="ok", raw_text=value["response"])
                        break
                    rows.append(result)
        gate = judges.fixture_gate(rows)
        return {"pass": gate["pass"] and all(routes), "judges": gate, "routes": routes}

    def qualification(self):
        self.complete("screen")
        return analysis.qualify(self.rows("screen"))

    def main_admission(self, *, gpu_spent_usd, gpu_hourly_rate_usd, gpu_remaining_seconds,
                       storage_bound_usd, remaining_overhead_seconds):
        self.require_resolved(phases={"fixtures", "screen"})
        if not self.fixture_gate()["pass"]:
            raise Halted("Fixture gate failed")
        self.complete("screen")
        self.audit()
        evidence = {"gpu_spent_usd": gpu_spent_usd, "gpu_hourly_rate_usd": gpu_hourly_rate_usd,
                    "gpu_remaining_seconds": gpu_remaining_seconds, "storage_bound_usd": storage_bound_usd,
                    "remaining_overhead_seconds": remaining_overhead_seconds}
        values = {k: _amount(v) for k,v in evidence.items()}
        if values["gpu_hourly_rate_usd"] != Decimal(self.plan["budget"]["gpu_hourly_usd"]):
            raise Halted("GPU rate must match the frozen rental price")
        qualification = analysis.qualify(self.rows("screen"))
        observed = [r for r in self.receipts.records().values() if r["phase"] == "screen"]
        def mean(channel, role=None, judge=None, instrument=None, cost=False):
            selected = [r for r in observed if r["channel"] == channel
                        and (role is None or r["metadata"].get("role") == role)
                        and (judge is None or r["metadata"].get("judge") == judge)
                        and (instrument is None or r["metadata"].get("instrument") == instrument)]
            ids = {r["metadata"]["item_id"] for r in selected}
            if not ids:
                raise Halted("Missing measured cost/time basis")
            return sum((Decimal(self.ledger.existing(r["call_id"])["cost_usd"]) if cost else
                        Decimal(str(r["elapsed_seconds"])) for r in selected), Decimal(0))/len(ids)
        judge_cost = sum((mean("judge", judge=j, instrument=i, cost=True)
                          for j in self.plan["judges"] for i in judges.INSTRUMENTS), Decimal(0))
        # Separate phases permit GPU deletion before the remote judge tail.
        seconds = Decimal("1.30")*(128*mean("local", "source") + 256*mean("local", "final"))
        seconds += values["remaining_overhead_seconds"]
        api_forecast = Decimal("1.30")*256*judge_cost
        api_before = sum((Decimal(r["cost_usd"]) for r in self.ledger.rows() if r["phase"] != "main"), Decimal(0))
        gpu_total = values["gpu_spent_usd"] + seconds*values["gpu_hourly_rate_usd"]/3600
        api_total = api_before + api_forecast
        total = gpu_total + api_total + values["storage_bound_usd"]
        qualified = qualification["inventory_valid"] and set(qualification["eligible_models"]) == set(self.plan["models"])
        fits = qualified and gpu_total <= 25 and api_total <= 45 and values["storage_bound_usd"] <= 5 and total <= 75 and seconds <= values["gpu_remaining_seconds"]
        return {"fits": fits, "qualified": qualified, "evidence": evidence,
                "main_seconds_with_margin": str(seconds), "judge_main_with_margin_usd": str(api_forecast),
                "gpu_completion_usd": str(gpu_total), "judge_completion_usd": str(api_total),
                "combined_completion_usd": str(total), "margin": "1.30"}

    def approve_main(self, admission):
        if admission != self.main_admission(**admission["evidence"]) or not admission["fits"]:
            raise Halted("Main admission does not reconstruct")
        if self.receipts.decision("main_admission") == admission:
            return
        self.receipts.append("decision", {"name": "main_admission", "value": admission})

    def audit(self):
        with self.ledger._mutex, self.receipts.mutex:
            return self._audit_locked()

    def serialization_audit(self, tokenizer_directory):
        """Offline reconstruction, not a capture of the server's internal tokens.

        Load only hash-bound local bytes in an isolated directory, with network
        and custom tokenizer code disabled. Keep every dispatched local request,
        including pending/failed receipts; count agreement cannot prove identity.
        """
        from importlib.metadata import version
        from transformers import AutoTokenizer
        with self.ledger._mutex, self.receipts.mutex:
            receipt_audit = self._audit_locked()
            records = deepcopy(self.receipts.records())
            head = self.receipts.events[-1]["sha256"]
        inventory = self.plan["metadata"]["model_artifacts"]["files"]
        files = {}
        with tempfile.TemporaryDirectory(prefix="kolibri-tokenizer-audit-") as temporary:
            for name in ("config.json", "tokenizer_config.json", "tokenizer.json"):
                path = Path(tokenizer_directory) / name
                _no_symlinks(path)
                body = path.read_bytes()
                expected = inventory[name]
                if len(body) != expected["size"] or sha(body) != expected["sha256"]:
                    raise Halted("Local tokenizer artifact differs from frozen PLAN")
                files[name] = {"bytes": len(body), "sha256": sha(body)}
                (Path(temporary) / name).write_bytes(body)
            config = strict_json((Path(temporary) / "tokenizer_config.json").read_bytes())
            if not isinstance(config.get("chat_template"), str) or not config["chat_template"]:
                raise Halted("Frozen tokenizer lacks an unambiguous chat template")
            tokenizer = AutoTokenizer.from_pretrained(temporary, local_files_only=True,
                                                       trust_remote_code=False, use_fast=True)
            contexts = []
            for call_id, row in records.items():
                if row["channel"] != "local":
                    continue
                request = row["request"]
                kwargs = {"add_generation_prompt": True, "continue_final_message": False,
                          **request["chat_template_kwargs"]}
                rendered = tokenizer.apply_chat_template(request["messages"], tokenize=False, **kwargs)
                tokens = tokenizer.apply_chat_template(request["messages"], tokenize=True, **kwargs)
                if (not isinstance(rendered, str) or not isinstance(tokens, list)
                        or not tokens or any(type(t) is not int or t < 0 for t in tokens)
                        or tokenizer.encode(rendered, add_special_tokens=False) != tokens):
                    raise Halted("Local rendering/tokenization is inconsistent")
                reported = (self.receipts.raw(row)["usage"]["prompt_tokens"]
                            if row["status"] == "received" else None)
                contexts.append({"call_id": call_id, "phase": row["phase"],
                    "request_sha256": common.digest(request), "receipt_status": row["status"],
                    "response_sha256": row.get("body", {}).get("sha256"),
                    "messages": request["messages"], "template_kwargs": kwargs,
                    "rendered_text": rendered, "rendered_sha256": sha(rendered.encode()),
                    "token_ids": tokens, "derived_prompt_tokens": len(tokens),
                    "reported_prompt_tokens": reported,
                    "count_matches": None if reported is None else len(tokens) == reported,
                    "fits_server_context_with_output_cap": len(tokens) + request["max_tokens"] <= 16384})
        return {"schema": "kolibri-derived-serialization-v1", "derived_not_raw": True,
            "server_internal_tokens_captured": False, "count_agreement_proves_token_identity": False,
            "truncation_applied": False, "server_max_model_len": 16384,
            "freeze": self.freeze, "plan_sha256": self.plan_hash, "http_head_sha256": head,
            "receipt_audit": receipt_audit, "tokenizer_files": files, "tokenizer_config": config,
            "implementation": {"class": type(tokenizer).__name__,
                "transformers": version("transformers"), "tokenizers": version("tokenizers")},
            "contexts": contexts, "count_mismatches": sum(c["count_matches"] is False for c in contexts),
            "counts_unavailable": sum(c["count_matches"] is None for c in contexts),
            "context_overflows": sum(not c["fits_server_context_with_output_cap"] for c in contexts)}

    def _audit_locked(self):
        self.check_sources()
        records = self.receipts.records(verify=True)
        expected_files = {"events.jsonl", ".lock"} | {
            row["body"]["path"] for row in records.values() if "body" in row}
        actual_files = set()
        for path in self.receipts.root.rglob("*"):
            _no_symlinks(path)
            if path.is_file():
                actual_files.add(path.relative_to(self.receipts.root).as_posix())
        if actual_files != expected_files:
            raise Halted("Extra or missing HTTP receipt file; preserve and reconcile")
        paid = {r["call_id"]: r for r in self.ledger.rows()}
        for call_id, row in records.items():
            meta = row["metadata"]
            kind = meta["kind"]
            if kind == "generation":
                item = self.catalog[meta["item_id"]]
                spec = self.plan["models"][item["model"]]
                donor = None
                if item["kind"] == "final":
                    source = self.parsed_call("gen:"+item["source_id"], spec)
                    if source is None or source["missing"]:
                        raise Halted("Final has missing donor")
                    donor = source["response"]
                expected = local_request(spec, item["id"], common.messages(item, donor), item["seed"])
                identity, phase, channel = "gen:"+item["id"], item["phase"], "local"
                expected_meta = {"kind": kind, "item_id": item["id"], "role": item["kind"],
                                 "model": item["model"], "block": item["block"]}
            elif kind == "route":
                spec = self.plan["models"][meta["model"]]
                identity, phase, channel = "route:"+meta["model"], "fixtures", "local"
                expected = local_request(spec, identity, [{"role": "user", "content": "Reply with exactly OK."}])
                expected_meta = {"kind": kind, "model": meta["model"]}
            elif kind == "judge":
                spec = self.plan["judges"][meta["judge"]]
                if type(meta["attempt"]) is not int or meta["attempt"] not in (0, 1):
                    raise Halted("Unapproved judge attempt")
                identity = f"judge:{meta['item_id']}:{meta['judge']}:{meta['instrument']}:a{meta['attempt']}"
                if meta["item_id"] in self.fixtures:
                    response, phase = self.fixtures[meta["item_id"]]["response"], "fixtures"
                else:
                    item = self.catalog[meta["item_id"]]
                    if item["kind"] != "final":
                        raise Halted("Sources cannot be judge targets")
                    output = self.parsed_call("gen:"+item["id"], self.plan["models"][item["model"]])
                    if output is None or output["missing"]:
                        raise Halted("Judge lacks final content")
                    response, phase = output["response"], item["phase"]
                if meta["attempt"] == 1:
                    prior = records.get(identity[:-1]+"0")
                    value = prior["projection"] if prior and prior["status"] == "received" else None
                    if value is None or not value["complete"] or value["missing"]:
                        raise Halted("Ambiguous or capped judgment was retried")
                    try:
                        judges.parse(meta["instrument"], response, value["response"])
                    except (ValueError, KeyError, TypeError):
                        pass
                    else:
                        raise Halted("Valid judgment was retried")
                expected = judges.judge_request(spec, meta["instrument"], response)
                expected["provider"].update(PRIVACY)
                channel = "judge"
                expected_meta = {"kind": kind, "item_id": meta["item_id"], "judge": meta["judge"],
                    "instrument": meta["instrument"], "attempt": meta["attempt"], "response_sha256": common.digest(response)}
            else:
                raise Halted("Unknown call kind")
            expected_meta.update(freeze=self.freeze, plan_sha256=self.plan_hash)
            if (call_id != identity or row["phase"] != phase or row["channel"] != channel
                    or meta != expected_meta or common.canonical(row["request"]) != common.canonical(expected)):
                raise Halted("Request, source, seed or privacy fails reconstruction")
            if channel == "judge":
                bill = paid.pop(call_id, None)
                if bill is None or bill["request"] != expected or bill["metadata"] != meta or bill["phase"] != phase or Decimal(bill["reservation_usd"]) != reservation(spec, expected):
                    raise Halted("Judge ledger differs from exact HTTP request")
            if row["status"] == "received":
                raw = self.receipts.raw(row)
                projection = local_result(spec, raw) if channel == "local" else parse_result(spec, raw)
                if row["http_status"] != 200 or row["transport_error"] is not None or row["error_type"] is not None or row["projection"] != projection:
                    raise Halted("Derived projection differs from raw HTTP response")
                if channel == "judge" and (bill["raw"] != raw or bill["status"] != "settled" or Decimal(bill["cost_usd"]) != receipt_cost(spec, raw)):
                    raise Halted("Judge cost/receipt does not reconstruct")
            elif row["status"] == "unresolved":
                if row["projection"] is not None or row["error_type"] is None:
                    raise Halted("Unresolved response has a fabricated projection")
                try:
                    raw = self.receipts.raw(row)
                except (ValueError, UnicodeError):
                    raw = None
                if channel == "judge" and (bill["status"] != "unresolved" or
                        bill["raw"] != (raw if isinstance(raw, dict) else None)):
                    raise Halted("Unresolved judge raw receipt differs")
            elif channel == "judge" and bill["status"] != "pending":
                raise Halted("Pending HTTP request differs from judge reservation")
        if paid:
            raise Halted("Judge ledger has an orphan reservation; preserve and reconcile")
        return {"pass": True, "calls": len(records), "generation_calls": sum(r["channel"] == "local" for r in records.values()),
                "judge_cost_bound_usd": str(self.ledger.spent()), "gpu_cost_included": False,
                "unresolved": sum(r["status"] != "received" for r in records.values())}
