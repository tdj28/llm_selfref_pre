"""Resume existing IDs without regenerating calls or rewriting their provenance."""
from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import protocol as common
from experiments.openrouter_swap.ledger import Halted
from experiments.openrouter_swap.providers import parse_result, reservation as common_reservation
from experiments.openrouter_swap.runner import Runner as CommonRunner
from experiments.openrouter_swap_openweights.runner import ExtensionRunner as OriginalRunner, private_request
from experiments.openrouter_swap_openweights_a1.accounting import accounting, reservation as a1_reservation
from experiments.openrouter_swap_openweights_a1.production import public_json
from . import protocol as p
from .ledger import CompositeLedger, DeltaLedger
from .prefix import Snapshot, check


def reservation(spec, request):
    padding = (Decimal(3 * request["max_tokens"]) * Decimal(spec["output_price"]) / 1_000_000
               if spec == p.MODELS["mistral"] else Decimal(0))
    return common_reservation(spec, request) + padding


class AuditView(Snapshot):
    """Verify original epochs/privacy/accounting before detached projections."""
    def __init__(self, ledger, plan, freeze, plan_hash):
        ledger.prefix.assert_unchanged()
        specs = {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}
        rows, disclosures = [], []
        for original in ledger.rows():
            row = deepcopy(original)
            historical = ledger.prefix.existing(row["call_id"])
            epoch = p.PREFIX if historical is not None else {"freeze": freeze, "plan_sha256": plan_hash}
            check(historical is None or historical == original, "Historical receipt changed")
            check(row["metadata"]["freeze"] == epoch["freeze"]
                  and row["metadata"]["plan_sha256"] == epoch["plan_sha256"], "Original epoch binding differs")
            request, spec = row["request"], specs[row["request"]["model"]]
            check(common.digest(request) == row["request_sha256"], "Original request digest differs")
            check(all(type(request["provider"].get(k)) is type(v) and request["provider"][k] == v
                      for k, v in p.PRIVACY.items()), "Original privacy policy differs")
            reserve = (a1_reservation if historical is not None else reservation)(spec, request)
            check(Decimal(row["reservation_usd"]) == reserve, "Original reservation differs")
            record = {"call_id": row["call_id"], "epoch": "A1" if historical is not None else "A2",
                "original_freeze": epoch["freeze"], "original_plan_sha256": epoch["plan_sha256"],
                "request_sha256": row["request_sha256"], "reservation_usd": row["reservation_usd"],
                "padding_usd": str(reserve - common_reservation(spec, request)),
                "historical_overreservation_acknowledged": historical is not None and ledger.prefix.acknowledged(original)}
            if row["status"] == "settled":
                check(common.digest(row["raw"]) == row["raw_sha256"], "Original raw digest differs")
                cost, detail, projected = accounting(spec, row["raw"])
                check(cost is not None and Decimal(row["cost_usd"]) == cost, "Original conservative cost differs")
                record["accounting"] = detail
                row["raw"] = projected
            for key in p.PRIVACY:
                del request["provider"][key]
            row["reservation_usd"] = str(common_reservation(spec, request))
            row["metadata"].update(freeze=freeze, plan_sha256=plan_hash)
            rows.append(row)
            disclosures.append(record)
        super().__init__(rows, ledger.cap, ledger.screen_cap)
        self.disclosures = disclosures


class ContinuationRunner(OriginalRunner):
    def __init__(self, plan, freeze, plan_hash, ledger, sender=None):
        from .production import validate
        self.budget = p.ForecastBudget(**validate(plan).__dict__)
        check(isinstance(ledger, CompositeLedger), "A2 requires the immutable-prefix composite ledger")
        check(sender is None or type(ledger.delta) is DeltaLedger, "Live dispatch requires a locked canonical delta")
        check((ledger.cap, ledger.screen_cap) == self.budget.limits(), "A2 remaining budget differs")
        self._existing_only = False
        self._design_hash = common.digest(plan)
        CommonRunner.__init__(self, deepcopy(plan), freeze, plan_hash, ledger, sender)

    def require_resolved(self):
        self.ledger.prefix.assert_unchanged()
        for row in self.ledger.rows():
            check(row["status"] == "settled" and
                  (not row.get("over_reservation") or self.ledger.prefix.acknowledged(row)),
                  "Unresolved or new over-reservation call blocks dispatch")

    def run_fixtures(self):
        self.ledger.prefix.assert_unchanged()
        return deepcopy(self.ledger.prefix.gate)

    def require_fixtures(self):
        return self.run_fixtures()

    def call(self, call_id, spec, request, phase, metadata):
        request = private_request(request)
        old = self.ledger.prefix.existing(call_id)
        epoch = p.PREFIX if old is not None else {"freeze": self.freeze, "plan_sha256": self.plan_hash}
        metadata = {**metadata, "freeze": epoch["freeze"], "plan_sha256": epoch["plan_sha256"]}
        existing = self.ledger.existing(call_id)
        if existing is not None:
            check(existing["request"] == request and existing["metadata"] == metadata
                  and existing["phase"] == phase, "Existing call differs from its original frozen request")
            return self.parsed_call(call_id, spec)
        check(phase in {"screen", "main"} and metadata["kind"] != "route", "No new fixture calls")
        check(not self._existing_only and self.sender is not None and not self.stop.is_set(), "No dispatch permission")
        public_json(metadata)
        self.ledger.reserve(call_id, request, reservation(spec, request), phase, metadata)
        raw, cost = None, None
        try:
            raw = self.sender(request)
            cost, _, _ = accounting(spec, raw)
            check(cost is not None, "Usage unavailable")
            result = parse_result(spec, raw)
        except Exception as error:
            if raw is None and getattr(error, "status_code", None) is not None:
                raw = {"transport_status_code": error.status_code}
            self.ledger.settle(call_id, raw, cost, error=error)
            self.stop.set()
            raise Halted("Transport, identity or accounting failure; receipt retained") from None
        settled = self.ledger.settle(call_id, raw, cost)
        if settled["over_reservation"]:
            self.stop.set()
            raise Halted("New receipt exceeded A2 reservation; no automatic continuation")
        return result

    def audit(self):
        from .production import validate
        validate(self.plan)
        check(common.digest(self.plan) == self._design_hash, "In-memory continuation plan changed")
        view = AuditView(self.ledger, self.plan, self.freeze, self.plan_hash)
        result = CommonRunner(self.plan, self.freeze, self.plan_hash, view).audit()
        return {**result, "prefix_calls": 92, "delta_calls": len(self.ledger.delta.rows()),
                "prefix_cost_already_in_prior_usd": str(p.PREFIX_COST),
                "delta_cost_bound_usd": str(self.ledger.delta.spent()),
                "scope_cost_plus_commitments_usd": str(p.PRIOR + self.ledger.delta.spent()
                    + Decimal(self.budget.external_commitments_usd)),
                "acknowledged_historical_overreservation": deepcopy(p.EXCEPTION),
                "unacknowledged_overreservations": [r["call_id"] for r in self.ledger.delta.rows() if r.get("over_reservation")],
                "detached_audit_projection": "verified-original-epoch-privacy-reservation-and-usage-v1",
                "projection_disclosures": view.disclosures}
