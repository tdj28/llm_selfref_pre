"""Read-only, exact-byte A1 history and its pre-research fixture gate."""
from copy import deepcopy
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, digest
from experiments.openrouter_swap.release import _load
from experiments.openrouter_swap_openweights_a1.runner import ExtensionRunner as A1Runner
from . import protocol as p

MAX_RAW = 128 * 1024 * 1024


def check(condition, message):
    if not condition:
        raise Halted(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def events_from_bytes(raw):
    check(raw and raw.endswith(b"\n") and len(raw) <= MAX_RAW, "Empty, torn or oversized journal")
    records, previous = [], None
    for number, line in enumerate(raw.splitlines(), 1):
        row = json.loads(line)
        check(isinstance(row, dict) and set(row) == {"seq", "previous", "utc", "kind", "data", "sha256"}, "Event schema changed")
        payload = {k: v for k, v in row.items() if k != "sha256"}
        check(type(row["seq"]) is int and row["seq"] == number and row["previous"] == previous
              and digest(payload) == row["sha256"] and common.canonical(row).encode() == line,
              "Journal hash chain or encoding mismatch")
        records.append(row)
        previous = row["sha256"]
    return records


def read_raw(root):
    root = Path(root)
    plain, compressed = root / "raw/events.jsonl", root / "raw/events.jsonl.gz"
    check(plain.exists() != compressed.exists(), "Exactly one journal representation required")
    path = plain if plain.exists() else compressed
    _no_symlinks(path)
    if path == plain:
        check(path.stat().st_size <= MAX_RAW, "Oversized journal")
        return path.read_bytes()
    with gzip.open(path, "rb") as stream:
        raw = stream.read(MAX_RAW + 1)
    check(len(raw) <= MAX_RAW, "Oversized compressed journal")
    return raw


class Snapshot:
    def __init__(self, rows, cap, screen_cap):
        self._rows = deepcopy(rows)
        self._by_id = {r["call_id"]: r for r in self._rows}
        check(len(self._by_id) == len(self._rows), "Duplicate snapshot ID")
        self.cap, self.screen_cap = cap, screen_cap

    def rows(self):
        return deepcopy(self._rows)

    def existing(self, call_id):
        return deepcopy(self._by_id.get(call_id))

    def spent(self):
        return sum((Decimal(r["cost_usd"]) for r in self._rows), Decimal(0))


def merged(events):
    calls = {}
    for event in events[1:]:
        row = event["data"]
        check(event["kind"] in {"reserve", "settle"}, "Unknown history event")
        if event["kind"] == "reserve":
            check(row["call_id"] not in calls, "Duplicate historical call")
        else:
            check(row["call_id"] in calls and calls[row["call_id"]]["status"] == "pending", "Duplicate or orphan settlement")
        calls.setdefault(row["call_id"], {}).update(deepcopy(row))
    return list(calls.values())


class Prefix(Snapshot):
    def __init__(self, root):
        self.root = Path(root).absolute()
        _no_symlinks(self.root)
        raw = read_raw(self.root)
        check(len(raw) == p.PREFIX["journal_bytes"] and sha(raw) == p.PREFIX["journal_sha256"], "A1 immutable prefix changed")
        events = events_from_bytes(raw)
        check(len(events) == p.PREFIX["events"] and events[-1]["sha256"] == p.PREFIX["head"], "A1 prefix boundary changed")
        plan_path = self.root / "PLAN.json"
        check(common.sha(plan_path) == p.PREFIX["plan_sha256"], "A1 plan bytes changed")
        self.plan, self.runtime = _load(plan_path), _load(self.root / "runtime.json")
        check(self.runtime == {"freeze": p.PREFIX["freeze"], "plan_sha256": p.PREFIX["plan_sha256"],
                               "plan_path": p.A1_PLAN, "budget": self.plan["budget"]}, "A1 runtime changed")
        rows = merged(events)
        cap, screen = p.Budget(**self.plan["budget"]).limits()
        super().__init__(rows, cap, screen)
        check(len(rows) == 92 and all(r["status"] == "settled" for r in rows)
              and self.spent() == p.PREFIX_COST, "A1 calls or spending changed")
        exceptions = [r for r in rows if r.get("over_reservation")]
        check(len(exceptions) == 1, "Historical exception is not exact")
        row, expected = exceptions[0], p.EXCEPTION
        check(all(row[k] == expected[k] for k in ("call_id", "request_sha256", "raw_sha256", "reservation_usd", "cost_usd")), "Historical receipt differs")
        for kind in ("reserve", "settle"):
            event = next(e for e in events if e["kind"] == kind and e["data"].get("call_id") == expected["call_id"])
            check(event["sha256"] == expected[kind + "_event_sha256"], "Historical exception event differs")
        self.audit = A1Runner(self.plan, p.PREFIX["freeze"], p.PREFIX["plan_sha256"], self).audit()
        boundary = next(e["seq"] - 1 for e in events if e["kind"] == "reserve" and e["data"]["phase"] != "fixtures")
        fixture_raw = b"".join(raw.splitlines(keepends=True)[:boundary])
        check(boundary == 53 and sha(fixture_raw) == p.PREFIX["fixture_prefix_sha256"], "Fixture prefix changed")
        fixture_view = Snapshot(merged(events[:boundary]), cap, screen)
        self.gate = A1Runner(self.plan, p.PREFIX["freeze"], p.PREFIX["plan_sha256"], fixture_view).require_fixtures()
        check(self.gate == _load(self.root / "fixture_gate.json") and self.gate["pass"], "A1 fixture gate differs from its prefix")
        self.files = {"PLAN.json", "runtime.json", "fixture_gate.json"}
        self.files.update(q.relative_to(self.root).as_posix() for q in (self.root / "launches").glob("*.json"))
        self.hashes = {name: common.sha(self.root / name) for name in self.files}
        self.raw = raw

    def assert_unchanged(self):
        check(sha(read_raw(self.root)) == p.PREFIX["journal_sha256"]
              and all(common.sha(self.root / n) == h for n, h in self.hashes.items()), "A1 history changed after validation")

    def acknowledged(self, row):
        return row["call_id"] == p.EXCEPTION["call_id"] and row == self.existing(row["call_id"])
