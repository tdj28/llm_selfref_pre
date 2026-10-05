"""Reuse frozen execution/qualification with an explicit accounting adapter."""

from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import parse_result, reservation as common_reservation
from experiments.openrouter_swap.runner import Runner as CommonRunner
from experiments.openrouter_swap_openweights.runner import (
    ExtensionRunner as OriginalRunner, SharedLedger, private_request, _AuditView as PrivacyView,
)
from . import protocol
from .accounting import accounting, reservation


class _AuditView(PrivacyView):
    """Validate exact originals before presenting detached accounting fields."""

    def __init__(self, ledger, plan):
        self.ledger, self.records = ledger, {}
        specs = {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}
        self.accounting_records = []
        self.reservation_records = []
        for original in ledger.rows():
            row = deepcopy(original)
            request = row["request"]
            if common.digest(request) != row["request_sha256"]:
                raise Halted("Private request digest differs")
            if any(type(request["provider"].get(k)) is not type(v) or request["provider"][k] != v
                   for k, v in protocol.PRIVACY.items()):
                raise Halted("Receipt privacy policy differs")
            spec = specs[request["model"]]
            actual = reservation(spec, request)
            if Decimal(row["reservation_usd"]) != actual:
                raise Halted("Actual A1 reservation differs")
            if spec == protocol.MODELS["mistral"]:
                self.reservation_records.append({
                    "call_id": row["call_id"], "reservation_usd": str(actual),
                    "padding_usd": str(actual - common_reservation(spec, request)),
                    "padding_is_reported_charge": False,
                })
            for key in protocol.PRIVACY:
                del request["provider"][key]
            row["reservation_usd"] = str(common_reservation(spec, request))
            self.records[row["call_id"]] = row
            if row["status"] != "settled":
                continue
            raw = row["raw"]
            if common.digest(raw) != row["raw_sha256"]:
                raise Halted("Original raw digest differs")
            cost, record, projection = accounting(specs[row["request"]["model"]], raw)
            if cost is None or Decimal(row["cost_usd"]) != cost:
                raise Halted("Original accounting bound differs")
            if record is not None:
                self.accounting_records.append({"call_id": row["call_id"], **record})
                row["raw"] = projection


class ExtensionRunner(OriginalRunner):
    def __init__(self, plan, freeze, plan_hash, ledger, sender=None):
        from .production import validate
        self.budget = (protocol.verify_draft(plan) if plan["status"] == "offline_only_unfrozen"
                       else validate(plan))
        if sender is not None and (plan["status"] == "offline_only_unfrozen" or not isinstance(ledger, SharedLedger)):
            raise Halted("Production dispatch requires its A1 plan and shared ledger")
        cap, screen_cap = self.budget.limits()
        if ledger.cap != cap or ledger.screen_cap != screen_cap:
            raise Halted("Ledger must use explicit working-budget limits")
        self._existing_only = False
        self._design_hash = common.digest(plan)
        CommonRunner.__init__(self, deepcopy(plan), freeze, plan_hash, ledger, sender)

    def call(self, call_id, spec, request, phase, metadata):
        request = private_request(request)
        metadata = {**metadata, "freeze": self.freeze, "plan_sha256": self.plan_hash}
        existing = self.ledger.existing(call_id)
        if existing is not None:
            if existing["request"] != request or existing["metadata"] != metadata or existing["phase"] != phase:
                raise Halted("Existing call differs from its frozen request")
            return self.parsed_call(call_id, spec)
        if self._existing_only or self.sender is None or self.stop.is_set():
            raise Halted("No dispatch permission or required receipt absent")
        self.ledger.reserve(call_id, request, reservation(spec, request), phase, metadata)
        raw, cost = None, None
        try:
            raw = self.sender(request)
            cost, _, _ = accounting(spec, raw)
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

    def audit(self):
        from .production import validate
        if self.plan["status"] == "offline_only_unfrozen":
            protocol.verify_draft(self.plan)
        else:
            validate(self.plan)
        if common.digest(self.plan) != self._design_hash:
            raise Halted("In-memory design binding changed")
        view = _AuditView(self.ledger, self.plan)
        result = CommonRunner(self.plan, self.freeze, self.plan_hash, view).audit()
        return {**result, "accounting_projection": "mistral-accounting-a1-v1",
                "mistral_reservations": sorted(view.reservation_records, key=lambda r: r["call_id"]),
                "mistral_accounting": sorted(view.accounting_records, key=lambda r: r["call_id"])}
