"""One locked A2 delta; old IDs and old spending can never be reset."""
from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap.ledger import Halted, SCREEN_PHASES
from experiments.openrouter_swap_openweights.runner import SharedLedger
from .prefix import check, events_from_bytes


class DeltaLedger(SharedLedger):
    def __init__(self, root, prefix, *, cap, screen_cap):
        self.prefix = prefix
        self.prefix_ids = frozenset(r["call_id"] for r in prefix.rows())
        super().__init__(root, cap=cap, screen_cap=screen_cap)

    def _rebuild(self):
        self.prefix.assert_unchanged()
        super()._rebuild()
        check(not self.prefix_ids.intersection(self._calls)
              and all(r["phase"] in {"screen", "main"} for r in self._calls.values()), "A2 duplicated history or dispatched fixtures")

    def _check_budget(self, amount, phase):
        super()._check_budget(amount, phase)
        check(not any(r["status"] == "unresolved" for r in self._calls.values()), "Unresolved A2 call blocks dispatch")

    def reserve(self, call_id, request, reservation, phase, metadata):
        with self._mutex:
            self.prefix.assert_unchanged()
            check(call_id not in self.prefix_ids and phase in {"screen", "main"}, "No repeated A1 calls or new fixtures")
            return super().reserve(call_id, request, reservation, phase, metadata)


class ReplayDelta(DeltaLedger):
    """Use the frozen transition validator without opening or creating a lock."""
    def __init__(self, raw, prefix, *, cap, screen_cap):
        super().__init__(".", prefix, cap=cap, screen_cap=screen_cap)
        self._events = events_from_bytes(raw)
        check(self._events[0]["kind"] == "binding" and self._events[0]["data"] == {
            "schema": "openrouter-swap-ledger-v1", "cap_usd": str(self.cap),
            "screen_cap_usd": str(self.screen_cap), "screen_phases": sorted(SCREEN_PHASES)}, "Delta budget binding differs")
        self._rebuild()

    def _require_open(self):
        return None

    def reserve(self, *args, **kwargs):
        raise Halted("Read-only delta")

    def settle(self, *args, **kwargs):
        raise Halted("Read-only delta")


class CompositeLedger:
    def __init__(self, prefix, delta):
        check(delta.prefix is prefix, "Wrong immutable history")
        self.prefix, self.delta = prefix, delta
        self.cap, self.screen_cap = delta.cap, delta.screen_cap

    def rows(self):
        rows = self.prefix.rows() + self.delta.rows()
        check(len({r["call_id"] for r in rows}) == len(rows), "Duplicate prefix/delta call ID")
        return rows

    def existing(self, call_id):
        old, new = self.prefix.existing(call_id), self.delta.existing(call_id)
        check(old is None or new is None, "Duplicate prefix/delta call ID")
        return deepcopy(old if old is not None else new)

    def spent(self):
        return self.prefix.spent() + self.delta.spent()

    @property
    def holdback(self):
        return self.delta.holdback

    @holdback.setter
    def holdback(self, value):
        self.delta.holdback = Decimal(value)

    def reserve(self, *args, **kwargs):
        return self.delta.reserve(*args, **kwargs)

    def settle(self, *args, **kwargs):
        return self.delta.settle(*args, **kwargs)
