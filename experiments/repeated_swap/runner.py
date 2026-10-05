"""Reuse the audited swap requests with fresh IDs and repeated-answer checks."""

from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Ledger, Halted, BudgetExceeded
from experiments.openrouter_swap.providers import generation_request, reservation
from experiments.openrouter_swap.runner import Runner as CommonRunner
from . import protocol


def privacy(kind):
    return {"data_collection": "deny", **({"zdr": True} if kind == "judge" else {})}


class StudyLedger(Ledger):
    stage_limit = Decimal("130")

    def _check_budget(self, amount, phase):
        super()._check_budget(amount, phase)
        if self.spent() + amount > self.stage_limit:
            raise BudgetExceeded("Current technical-stage budget reached")


class AuditView:
    def __init__(self, ledger, plan):
        self.ledger, self.records = ledger, {}
        for original in ledger.rows():
            row = deepcopy(original)
            meta, request = row["metadata"], row["request"]
            kind = meta["kind"]
            spec = plan["judges"][meta["judge"]] if kind == "judge" else plan["models"][meta["model"]]
            if (common.digest(request) != row["request_sha256"] or
                    Decimal(row["reservation_usd"]) != reservation(spec, request)):
                raise Halted("Original request or reservation changed")
            for key, expected in privacy(kind).items():
                if type(request["provider"].get(key)) is not type(expected) or request["provider"][key] != expected:
                    raise Halted("Request privacy settings changed")
                del request["provider"][key]
            row["reservation_usd"] = str(reservation(spec, request))
            self.records[row["call_id"]] = row

    def rows(self):
        return deepcopy(list(self.records.values()))

    def existing(self, call_id):
        return deepcopy(self.records.get(call_id))

    def spent(self):
        return self.ledger.spent()


class Runner(CommonRunner):
    def route_fixture(self, model):
        spec = self.plan["models"][model]
        result = self.call(f"route:{model}", spec,
                           generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}]),
                           "fixtures", {"kind": "route", "model": model})
        return {**result, "model": model, "pass": result["complete"] and not result["missing"]
                and result["response"].strip() in self.plan.get("routing_acknowledgments", ["OK", "OK."])}

    def call(self, call_id, spec, request, phase, metadata):
        request = deepcopy(request)
        request["provider"].update(privacy(metadata["kind"]))
        return super().call(call_id, spec, request, phase, metadata)

    def audit(self):
        result = CommonRunner(self.plan, self.freeze, self.plan_hash,
                              AuditView(self.ledger, self.plan)).audit()
        requests = {}
        for row in self.ledger.rows():
            if row["metadata"]["kind"] != "generation":
                continue
            item = self.catalog[row["metadata"]["item_id"]]
            if item["kind"] != "final":
                continue
            key = (item["model"], item["block"], item["cell"])
            requests.setdefault(key, set()).add(row["request_sha256"])
        if any(len(hashes) != 1 for hashes in requests.values()):
            raise Halted("Replicates did not receive an identical fixed request")
        return {**result, "identical_repeat_requests": True,
                "independent_unit": "source_block", "planned_blocks_per_model": 32,
                "planned_draws_per_request": 3}

    def require_complete(self, initial=False):
        for block in self.plan["main"]:
            if initial and block["block"] > 2:
                continue
            model = self.plan["models"][block["model"]]
            for item in block["sources"]:
                if self.parsed_call("gen:" + item["id"], model) is None:
                    raise Halted("Missing planned source call")
            for item in block["finals"]:
                donor = self.parsed_call("gen:" + item["source_id"], model)
                if donor["missing"]:
                    continue
                response = self.parsed_call("gen:" + item["id"], model)
                if response is None:
                    raise Halted("Missing planned answer draw")
                if response["missing"]:
                    continue
                for judge in self.plan["judges"]:
                    for instrument in judges.INSTRUMENTS:
                        if self.ledger.existing(f"judge:{item['id']}:{judge}:{instrument}:a0") is None:
                            raise Halted("Missing planned judge call")

    def admission(self, available_credit):
        self.require_resolved()
        self.require_complete(initial=True)
        self.audit()
        paid = self.ledger.rows()
        forecasts = {}
        for model in self.plan["models"]:
            def mean(kind, role=None, judge=None, instrument=None):
                selected = [r for r in paid if r["metadata"]["kind"] == kind
                            and r["metadata"].get("item_id") in self.catalog
                            and self.catalog[r["metadata"]["item_id"]]["model"] == model
                            and self.catalog[r["metadata"]["item_id"]]["block"] <= 2
                            and (role is None or r["metadata"].get("role") == role)
                            and (judge is None or r["metadata"].get("judge") == judge)
                            and (instrument is None or r["metadata"].get("instrument") == instrument)]
                ids = {r["metadata"]["item_id"] for r in selected}
                if not ids:
                    raise Halted("Missing initial cost basis; no behavioral selection allowed")
                return sum((Decimal(r["cost_usd"]) for r in selected), Decimal(0)) / len(ids)
            unit_judging = sum((mean("judge", judge=j, instrument=i)
                                for j in self.plan["judges"] for i in judges.INSTRUMENTS), Decimal(0))
            forecasts[model] = Decimal("1.30") * (
                60 * mean("generation", role="source") +
                360 * (mean("generation", role="final") + unit_judging))
        remaining = sum(forecasts.values(), Decimal(0))
        budget = Decimal("130") - self.ledger.spent()
        funded = Decimal(str(available_credit)) - Decimal("45")
        return {"pass": remaining <= min(budget, funded),
                "outcome_selection": False, "models": list(self.plan["models"]),
                "observed_spend_usd": str(self.ledger.spent()),
                "remaining_forecast_with_30pct_reserve_usd": {m: str(v) for m, v in forecasts.items()},
                "available_study_budget_usd": str(budget),
                "available_credit_after_kolibri_reserve_usd": str(funded),
                "credit_snapshot_usd": str(available_credit), "kolibri_reserve_usd": "45"}
