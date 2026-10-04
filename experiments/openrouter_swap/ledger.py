"""Durable reservations and immutable settlements for one study budget.

The context holds a nonblocking process lock; an RLock serializes threads.
``rows`` and ``existing`` return detached, merged call records, not events.
Pending calls are already charged at their full reservation. Reusing any
call_id is forbidden; an authorized retry needs a new ID (e.g. x:retry:1).
This ledger records accounting, not scientific or spending authorization.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading

from .providers import _amount, _canonical, _public_body

SCREEN_PHASES = frozenset({"fixture", "fixtures", "screen"})


class Halted(RuntimeError):
    """The ledger cannot authorize this dispatch or mutation."""


class BudgetExceeded(Halted):
    pass


def digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Halted("Symlink in ledger path")


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _signature(path):
    _no_symlinks(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def read_events(path):
    """Verify an existing journal without repairing or truncating any bytes."""
    path = Path(path).absolute()
    _no_symlinks(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\n"):
        raise Halted("Empty or torn journal; preserve and reconcile")
    events, previous = [], None
    try:
        for number, line in enumerate(raw.splitlines(), 1):
            row = json.loads(line)
            if not isinstance(row, dict) or set(row) != {
                    "seq", "previous", "utc", "kind", "data", "sha256"}:
                raise ValueError
            payload = {k: v for k, v in row.items() if k != "sha256"}
            if (type(row["seq"]) is not int or row["seq"] != number or
                    row["previous"] != previous or digest(payload) != row["sha256"] or
                    line != _canonical(row).encode("utf-8")):
                raise ValueError
            previous = row["sha256"]
            events.append(row)
    except (ValueError, TypeError, KeyError):
        raise Halted("Journal hash chain or encoding mismatch") from None
    return events


def _identity(call_id, phase):
    if not isinstance(call_id, str) or not call_id.strip():
        raise ValueError("A nonempty call ID is required")
    if not isinstance(phase, str) or not phase.strip() or phase != phase.strip().lower():
        raise ValueError("A lowercase phase without outer whitespace is required")


def _has_usage(raw):
    usage = raw.get("usage") if isinstance(raw, dict) else None
    return isinstance(usage, dict) and all(
        type(usage.get(k)) is int and usage[k] >= 0
        for k in ("prompt_tokens", "completion_tokens"))


class Ledger:
    def __init__(self, root, cap="250", screen_cap="40"):
        self.root = Path(root).absolute()
        self.cap, self.screen_cap = _amount(cap), _amount(screen_cap)
        self._mutex = threading.RLock()
        self._handle = None
        self._pid = None
        self._poisoned = False
        self._events, self._calls = [], {}
        self._journal_signature = None

    def __enter__(self):
        with self._mutex:
            if self._handle is not None:
                raise Halted("Ledger context is already open")
            _no_symlinks(self.root)
            self.root.mkdir(parents=True, exist_ok=True)
            for name in (".ledger.lock", "events.jsonl"):
                _no_symlinks(self.root / name)
            self._handle = (self.root / ".ledger.lock").open("a+b")
            try:
                try:
                    fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise Halted("Another process owns the ledger") from None
                self._pid = os.getpid()
                self._poisoned = False
                self._journal_signature = _signature(self.root / "events.jsonl")
                self._events = read_events(self.root / "events.jsonl")
                if _signature(self.root / "events.jsonl") != self._journal_signature:
                    raise Halted("Journal changed during verification")
                self._calls = {}
                binding = {"schema": "openrouter-swap-ledger-v1", "cap_usd": str(self.cap),
                           "screen_cap_usd": str(self.screen_cap),
                           "screen_phases": sorted(SCREEN_PHASES)}
                if not self._events:
                    _sync_directory(self.root.parent)
                    self._append("binding", binding)
                if self._events[0]["kind"] != "binding" or self._events[0]["data"] != binding:
                    raise Halted("Ledger budget binding changed")
                self._rebuild()
            except BaseException:
                self._handle.close()
                self._handle = None
                self._pid = None
                raise
            return self

    def __exit__(self, *_):
        with self._mutex:
            if self._handle is not None:
                try:
                    if self._pid == os.getpid() and not self._poisoned:
                        if read_events(self.root / "events.jsonl") != self._events:
                            raise Halted("Journal changed while locked")
                finally:
                    # A forked child must not unlock its parent's shared descriptor.
                    if self._pid == os.getpid():
                        fcntl.flock(self._handle, fcntl.LOCK_UN)
                    self._handle.close()
                    self._handle = None
                    self._pid = None

    def _require_open(self):
        if self._handle is None or self._pid != os.getpid() or self._poisoned:
            raise Halted("A healthy ledger context and process lock are required")

    def _append(self, kind, data):
        self._require_open()
        path = self.root / "events.jsonl"
        # Full replay is done on open/release. The exclusive lock owns writes;
        # this constant-time guard catches external changes between appends.
        if _signature(path) != self._journal_signature:
            self._poisoned = True
            raise Halted("Journal changed while locked")
        row = {"seq": len(self._events) + 1,
               "previous": self._events[-1]["sha256"] if self._events else None,
               "utc": datetime.now(timezone.utc).isoformat(), "kind": kind,
               "data": deepcopy(data)}
        row["sha256"] = digest(row)
        payload = (_canonical(row) + "\n").encode("utf-8")
        try:
            with path.open("ab") as handle:
                if handle.write(payload) != len(payload):
                    raise OSError("Short journal write")
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(self.root)
            self._journal_signature = _signature(path)
        except BaseException:
            self._poisoned = True
            raise
        self._events.append(row)

    def _screen_spent(self):
        return sum((Decimal(r["cost_usd"]) for r in self._calls.values()
                    if r["phase"] in SCREEN_PHASES), Decimal(0))

    def _check_budget(self, amount, phase):
        if self.spent() + amount > self.cap:
            raise BudgetExceeded("Reservation exceeds cumulative study cap")
        if self._screen_spent() + (amount if phase in SCREEN_PHASES else 0) > self.screen_cap:
            raise BudgetExceeded("Reservation exceeds shared fixtures/screen cap")
        if any(r.get("over_reservation") for r in self._calls.values()):
            raise Halted("Receipt exceeded its reservation; reconcile before new dispatch")

    def _rebuild(self):
        try:
            for event in self._events[1:]:
                row, kind = deepcopy(event["data"]), event["kind"]
                _public_body(row)
                if kind == "reserve":
                    if set(row) != {"call_id", "request", "request_sha256", "reservation_usd",
                                    "phase", "metadata", "status", "cost_usd", "cost_known"}:
                        raise ValueError
                    _identity(row["call_id"], row["phase"])
                    amount = _amount(row["reservation_usd"])
                    if (row["call_id"] in self._calls or amount <= 0 or
                            not isinstance(row["request"], dict) or not isinstance(row["metadata"], dict) or
                            row["request_sha256"] != digest(row["request"]) or row["status"] != "pending" or
                            row["cost_usd"] != row["reservation_usd"] or row["cost_known"] is not False):
                        raise ValueError
                    self._check_budget(amount, row["phase"])
                    self._calls[row["call_id"]] = row
                elif kind == "settle":
                    if set(row) != {"call_id", "request_sha256", "raw", "raw_sha256", "reported_cost_usd",
                                    "cost_usd", "cost_known", "status", "error_type", "over_reservation"}:
                        raise ValueError
                    start = self._calls[row["call_id"]]
                    if start["status"] != "pending" or row["request_sha256"] != start["request_sha256"]:
                        raise ValueError
                    if row != self._settlement(start, row["raw"], row["reported_cost_usd"], row["error_type"]):
                        raise ValueError
                    self._calls[row["call_id"]] = {**start, **row}
                else:
                    raise ValueError
        except (ValueError, TypeError, KeyError):
            raise Halted("Invalid journal accounting or event transition") from None

    def reserve(self, call_id, request, reservation, phase, metadata):
        """Fsync before returning dispatch permission; duplicate IDs always halt."""
        with self._mutex:
            self._require_open()
            _identity(call_id, phase)
            if call_id in self._calls:
                raise Halted("Call already reserved or completed; no automatic resend")
            amount = _amount(reservation)
            if amount <= 0 or not isinstance(request, dict) or not isinstance(metadata, dict):
                raise ValueError("Positive reservation, request and metadata dictionaries required")
            _public_body(request)
            _public_body(metadata)
            self._check_budget(amount, phase)
            row = {"call_id": call_id, "request": deepcopy(request), "request_sha256": digest(request),
                   "reservation_usd": str(amount), "phase": phase, "metadata": deepcopy(metadata),
                   "status": "pending", "cost_usd": str(amount), "cost_known": False}
            self._append("reserve", row)
            self._calls[call_id] = row
            return deepcopy(row)

    @staticmethod
    def _settlement(start, raw, cost, error_type):
        cost = None if cost is None else _amount(cost)
        reserve = Decimal(start["reservation_usd"])
        known = (cost is not None and error_type is None and _has_usage(raw)
                 and raw.get("error") is None)
        usage = raw.get("usage") if isinstance(raw, dict) else None
        documented = Decimal(0)
        if isinstance(usage, dict) and usage.get("cost") is not None:
            try:
                documented = _amount(usage["cost"])
            except ValueError:
                known = False
        # Incomplete token accounting cannot erase a larger documented charge.
        charged = max(cost, documented) if known else max(reserve, cost or Decimal(0), documented)
        return {"call_id": start["call_id"], "request_sha256": start["request_sha256"],
                "raw": deepcopy(raw), "raw_sha256": digest(raw) if raw is not None else None,
                "reported_cost_usd": str(cost) if cost is not None else None,
                "cost_usd": str(charged), "cost_known": known,
                "status": "settled" if known else "unresolved", "error_type": error_type,
                "over_reservation": charged > reserve}

    def settle(self, call_id, raw, cost, error=None):
        """Append exactly once, including failures; errors keep at least reserve.

        Pass receipt_cost's Decimal/None. Exception messages are never stored;
        arbitrary string errors become ``Error``. Even an overrun is retained,
        then blocks subsequent reservations rather than hiding already-billed cost.
        """
        with self._mutex:
            self._require_open()
            start = self._calls.get(call_id)
            if start is None or start["status"] != "pending":
                raise Halted("Settlement requires one unsettled reservation")
            if raw is not None and not isinstance(raw, dict):
                raise ValueError("Raw response must be a dictionary or None")
            _public_body(raw)
            error_type = (type(error).__name__ if isinstance(error, BaseException)
                          else "Error" if error is not None else None)
            row = self._settlement(start, raw, cost, error_type)
            self._append("settle", row)
            self._calls[call_id] = {**start, **row}
            return deepcopy(self._calls[call_id])

    def rows(self):
        """Return one detached merged record per call, in reservation order."""
        with self._mutex:
            self._require_open()
            return deepcopy(list(self._calls.values()))

    def spent(self, phase=None):
        """Return Decimal settled cost + full pending/unresolved reservations."""
        with self._mutex:
            self._require_open()
            return sum((Decimal(r["cost_usd"]) for r in self._calls.values()
                        if phase is None or r["phase"] == phase), Decimal(0))

    def existing(self, call_id):
        """Return a detached call record or None; never grants replay permission."""
        with self._mutex:
            self._require_open()
            return deepcopy(self._calls.get(call_id))
