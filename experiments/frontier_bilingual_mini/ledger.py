"""One append-only, process-locked $60 ledger for both paid phases."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import threading

from experiments.automated_rubric_audit.common import canonical, digest
from .providers import reservation, receipt_cost


class Halted(RuntimeError):
    """No automatic retry of failed or uncertain paid calls."""


class BudgetExceeded(Halted):
    pass


def no_symlinks(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink in ledger path")


def read_events(path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise Halted("Torn journal tail; preserve and reconcile, never silently truncate")
    result, previous = [], None
    for number, line in enumerate(raw.splitlines(), 1):
        row = json.loads(line)
        payload = {k: v for k, v in row.items() if k != "sha256"}
        if row.get("seq") != number or row.get("previous") != previous or digest(payload) != row.get("sha256"):
            raise Halted("Journal hash chain mismatch")
        previous = row["sha256"]
        result.append(row)
    return result


class Ledger:
    def __init__(self, root, binding):
        self.root, self.binding = Path(root).absolute(), binding
        self.mutex = threading.RLock()
        self.events, self.requests, self.results = [], {}, {}
        self.handle = None

    def __enter__(self):
        no_symlinks(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        no_symlinks(self.root / ".mini.lock")
        no_symlinks(self.root / "events.jsonl")
        self.handle = (self.root / ".mini.lock").open("a+b")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.events = read_events(self.root / "events.jsonl")
            if not self.events:
                self.append("binding", self.binding)
            if self.events[0]["kind"] != "binding" or self.events[0]["data"] != self.binding:
                raise Halted("Ledger belongs to another plan/freeze/budget")
            self._rebuild()
        except BaseException:
            self.handle.close()
            self.handle = None
            raise
        return self

    def __exit__(self, *_):
        if self.handle is not None:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
            self.handle = None

    def _rebuild(self):
        for event in self.events[1:]:
            kind, data = event["kind"], event["data"]
            if kind == "request":
                key = data["id"]
                if key in self.requests or key in self.results:
                    raise Halted("Duplicate request")
                if data["reservation_usd"] != str(reservation(data["model"], data["request"])):
                    raise Halted("Reservation changed")
                if self.spent() + Decimal(data["reservation_usd"]) > Decimal("60"):
                    raise Halted("Recorded dispatch exceeded hard cap")
                self.requests[key] = data
            elif kind == "result":
                key = data["id"]
                if key not in self.requests or key in self.results:
                    raise Halted("Unmatched or duplicate response")
                req = self.requests[key]
                if data["request_sha256"] != digest(req["request"]):
                    raise Halted("Response/request binding mismatch")
                self._check_cost(req, data)
                self.results[key] = data
            elif kind == "missing":
                key = data["id"]
                if key in self.requests or key in self.results or data.get("cost_usd") != "0":
                    raise Halted("Invalid unpaid missing slot")
                self.results[key] = data
            elif kind not in {"preflight", "projection", "complete"}:
                raise Halted("Unexpected journal event")

    def _snapshot_drift(self, req, raw):
        if not isinstance(raw, dict):
            return False
        prior = {r["raw"].get("model") for key, r in self.results.items()
                 if key in self.requests and self.requests[key]["model"] == req["model"]
                 and isinstance(r.get("raw"), dict)}
        return bool(prior and raw.get("model") not in prior)

    def _check_cost(self, req, result):
        raw = result.get("raw")
        try:
            cost = receipt_cost(req["model"], raw) if isinstance(raw, dict) else None
        except (ValueError, TypeError, KeyError):
            cost = None
        expected = Decimal(req["reservation_usd"]) if cost is None else cost
        if Decimal(result["cost_usd"]) != expected or result["cost_known"] != (cost is not None):
            raise Halted("Receipt cost does not reconstruct")
        drift = self._snapshot_drift(req, raw)
        if result.get("model_drift") is not drift:
            raise Halted("Receipt-order model snapshot drift does not reconstruct")
        fatal = (result["evaluated"].get("fatal", False) or cost is None
                 or expected > Decimal(req["reservation_usd"]) or drift)
        if result.get("fatal") is not fatal:
            raise Halted("Receipt fatal gate does not reconstruct")

    def append(self, kind, data):
        with self.mutex:
            if self.handle is None:
                raise Halted("Writer lock not held")
            row = {"seq": len(self.events) + 1, "previous": self.events[-1]["sha256"] if self.events else None,
                   "utc": datetime.now(timezone.utc).isoformat(), "kind": kind, "data": data}
            row["sha256"] = digest(row)
            with (self.root / "events.jsonl").open("ab") as handle:
                handle.write((canonical(row) + "\n").encode())
                handle.flush()
                os.fsync(handle.fileno())
            self.events.append(row)
            return row

    def spent(self):
        with self.mutex:
            return sum((Decimal(self.results[k]["cost_usd"] if k in self.results
                                else req["reservation_usd"]) for k, req in self.requests.items()), Decimal(0))

    def healthy(self):
        with self.mutex:
            if self.spent() > Decimal("60"):
                raise BudgetExceeded("$60 cap exceeded in returned usage; no more calls")
            # In-flight requests are allowed for concurrent workers, but not resume.
            if any(r.get("fatal") for r in self.results.values()):
                raise Halted("Persisted API/schema/model failure; no new dispatch")

    def require_resolved(self):
        self.healthy()
        if set(self.requests) - set(self.results):
            raise Halted("Uncertain dispatched call; no automatic retry or bulk resume")

    def start(self, key, model, request, metadata):
        with self.mutex:
            self.healthy()
            if set(metadata) & {"id", "model", "request", "request_sha256", "reservation_usd"}:
                raise ValueError("Metadata may not override request accounting")
            if key in self.results:
                return None
            if key in self.requests:
                raise Halted("Call already dispatched; do not retry")
            reserve = reservation(model, request)
            if self.spent() + reserve > Decimal("60"):
                raise BudgetExceeded("Next call reservation would exceed the shared $60 cap")
            row = {"id": key, "model": model, "request": request,
                   "request_sha256": digest(request), "reservation_usd": str(reserve), **metadata}
            self.append("request", row)
            self.requests[key] = row
            return row

    def finish(self, key, raw, evaluated, *, transport_error=None):
        with self.mutex:
            req = self.requests[key]
            if key in self.results:
                raise Halted("Duplicate response")
            try:
                cost = receipt_cost(req["model"], raw) if raw is not None else None
            except (ValueError, TypeError, KeyError):
                cost = None
            drift = self._snapshot_drift(req, raw)
            fatal = evaluated.get("fatal", False) or cost is None or drift
            if cost is not None and cost > Decimal(req["reservation_usd"]):
                fatal = True
            row = {"id": key, "request_sha256": req["request_sha256"], "raw": raw,
                   "cost_known": cost is not None, "cost_usd": str(cost if cost is not None else Decimal(req["reservation_usd"])),
                   "evaluated": evaluated, "fatal": fatal, "model_drift": drift,
                   "transport_error_type": transport_error}
            self.append("result", row)
            self.results[key] = row
            return row

    def missing(self, key, reason, dependency):
        with self.mutex:
            expected = {"id": key, "cost_usd": "0", "reason": reason, "dependency": dependency,
                        "evaluated": {"status": "missing", "response": None, "missing": True}, "fatal": False}
            if key in self.results:
                if self.results[key] != expected:
                    raise Halted("Missing slot changed")
                return
            if key in self.requests:
                raise Halted("Cannot replace a dispatched call with missingness")
            self.append("missing", expected)
            self.results[key] = expected
