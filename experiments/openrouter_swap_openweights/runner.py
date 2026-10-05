"""Shared execution/replay rules; live entrypoint gates are in production.py."""

from copy import deepcopy
from decimal import Decimal

from experiments.openrouter_swap import judges, protocol as common
from experiments.openrouter_swap.ledger import Halted, Ledger, BudgetExceeded
from experiments.openrouter_swap.providers import generation_request, reservation
from experiments.openrouter_swap.runner import Runner as CommonRunner
from . import analysis, protocol


def private_request(request):
    request = deepcopy(request)
    request["provider"].update(protocol.PRIVACY)
    return request


class _AuditView:
    """Read-only common-request projection, after exact privacy/reserve checks."""

    def __init__(self, ledger, plan):
        self.ledger = ledger
        self.records = {}
        specs = {s["id"]: s for s in [*plan["models"].values(), *plan["judges"].values()]}
        for row in ledger.rows():
            row = deepcopy(row)
            request = row["request"]
            if common.digest(request) != row["request_sha256"]:
                raise Halted("Private request digest differs")
            if any(type(request["provider"].get(k)) is not type(v) or request["provider"][k] != v
                   for k, v in protocol.PRIVACY.items()):
                raise Halted("Receipt privacy policy differs")
            spec = specs[request["model"]]
            if Decimal(row["reservation_usd"]) != reservation(spec, request):
                raise Halted("Private request reservation differs")
            for key in protocol.PRIVACY:
                del request["provider"][key]
            row["reservation_usd"] = str(reservation(spec, request))
            self.records[row["call_id"]] = row

    def existing(self, call_id):
        return deepcopy(self.records.get(call_id))

    def rows(self):
        return deepcopy(list(self.records.values()))

    def spent(self):
        return self.ledger.spent()


class SharedLedger(Ledger):
    """Keep later admitted models funded under the common atomic reservation lock."""

    holdback = Decimal(0)

    def _check_budget(self, amount, phase):
        super()._check_budget(amount, phase)
        if self.spent() + amount + self.holdback > self.cap:
            raise BudgetExceeded("Reservation would consume a later model's full forecast")


class ExtensionRunner(CommonRunner):
    def __init__(self, plan, freeze, plan_hash, ledger, sender=None):
        from .production import validate
        self.budget = (protocol.verify_draft(plan) if plan["status"] == "offline_only_unfrozen"
                       else validate(plan))
        if sender is not None and (plan["status"] == "offline_only_unfrozen" or not isinstance(ledger, SharedLedger)):
            raise Halted("Production dispatch requires its plan and shared holdback ledger")
        cap, screen_cap = self.budget.limits()
        if ledger.cap != cap or ledger.screen_cap != screen_cap:
            raise Halted("Ledger must use explicit working-budget limits")
        self._existing_only = False
        self._design_hash = common.digest(plan)
        super().__init__(deepcopy(plan), freeze, plan_hash, ledger, sender)

    def call(self, call_id, spec, request, phase, metadata):
        request = private_request(request)
        existing = self.ledger.existing(call_id)
        if existing is None and self._existing_only:
            raise Halted("Required existing receipt absent")
        return super().call(call_id, spec, request, phase, metadata)

    def route_fixture(self, model):
        spec = self.plan["models"][model]
        request = generation_request(spec, [{"role": "user", "content": "Reply with exactly OK."}])
        result = self.call(f"route:{model}", spec, request, "fixtures", {"kind": "route", "model": model})
        return {**result, "pass": result["complete"] and not result["missing"]
                and result["response"].strip() in self.plan["routing_acknowledgments"]}

    def audit(self):
        from .production import validate
        if self.plan["status"] == "offline_only_unfrozen":
            protocol.verify_draft(self.plan)
        else:
            validate(self.plan)
        if common.digest(self.plan) != self._design_hash:
            raise Halted("In-memory design binding changed")
        view = _AuditView(self.ledger, self.plan)
        return CommonRunner(self.plan, self.freeze, self.plan_hash, view).audit()

    def require_fixtures(self):
        self._existing_only = True
        try:
            return super().require_fixtures()
        finally:
            self._existing_only = False

    def run_blocks(self, phase, models=None, initial=False):
        if phase not in {"screen", "main"} or (initial and phase != "screen"):
            raise Halted("Only the fixed two-block screen checkpoint may be partial")
        allowed = list(protocol.MODELS) if phase == "screen" else self.main_admission()["admitted_models"]
        if models is not None and list(models) != allowed:
            raise Halted("Cannot select models outside fixed qualification and budget admission")
        if phase == "screen":
            return super().run_blocks(phase, models=allowed, initial=initial)
        selection = self.main_admission()
        try:
            for index, model in enumerate(allowed):
                self.ledger.holdback = sum((Decimal(selection["projections"][m]["projected_cost_with_reserve_usd"])
                                           for m in allowed[index+1:]), Decimal(0))
                super().run_blocks(phase, models=[model])
                self.complete("main", models=[model])
        finally:
            self.ledger.holdback = Decimal(0)

    def complete(self, phase, models=None, initial=False):
        for block in self.plan[phase]:
            if (models is not None and block["model"] not in models) or (initial and block["block"] > 2):
                continue
            spec = self.plan["models"][block["model"]]
            for source in block["sources"]:
                if self.parsed_call("gen:" + source["id"], spec) is None:
                    raise Halted("Complete both fixed screens before main admission")
            for final in block["finals"]:
                donor = self.parsed_call("gen:" + final["source_id"], spec)
                if donor["missing"]:
                    continue
                output = self.parsed_call("gen:" + final["id"], spec)
                if output is None:
                    raise Halted("Incomplete screen final inventory")
                if not output["missing"]:
                    for judge in self.plan["judges"]:
                        for instrument in judges.INSTRUMENTS:
                            if self.ledger.existing(f"judge:{final['id']}:{judge}:{instrument}:a0") is None:
                                raise Halted("Incomplete screen judging inventory")
                            self._existing_only = True
                            try:
                                self.judge(final["id"], output["response"], judge, instrument, phase)
                            finally:
                                self._existing_only = False

    def main_admission(self):
        self.require_resolved()
        self.require_fixtures()
        self.audit()
        self.complete("screen")
        qualification = analysis.qualify(self.rows("screen"))
        if not qualification["inventory_valid"]:
            raise Halted("Incomplete qualification inventory")
        paid = self.ledger.rows()
        screen_cost = sum((Decimal(r["cost_usd"]) for r in paid if r["phase"] != "main"), Decimal(0))
        forecasts, admitted, committed = {}, [], Decimal(0)
        for model in self.plan["main_cost_priority"]:
            if model not in qualification["eligible_models"]:
                forecasts[model] = {"status": "not_qualified"}
                continue
            def mean_cost(kind, role=None, judge=None, instrument=None):
                selected = [r for r in paid if r["phase"] == "screen" and r["metadata"]["kind"] == kind
                            and self.catalog[r["metadata"]["item_id"]]["model"] == model
                            and (role is None or r["metadata"].get("role") == role)
                            and (judge is None or r["metadata"].get("judge") == judge)
                            and (instrument is None or r["metadata"].get("instrument") == instrument)]
                items = {r["metadata"]["item_id"] for r in selected}
                if not items:
                    raise Halted("No observed cost basis")
                return sum((Decimal(r["cost_usd"]) for r in selected), Decimal(0)) / len(items)
            forecast = protocol.project("main", source_usd=mean_cost("generation", "source"),
                                        final_usd=mean_cost("generation", "final"), judge_slots_usd={
                                            (j, i): mean_cost("judge", judge=j, instrument=i)
                                            for j in self.plan["judges"] for i in judges.INSTRUMENTS})
            fits = self.budget.admission(spent_usd=screen_cost, remaining_usd=committed + forecast)["fits"]
            forecasts[model] = {"status": "admitted" if fits else "not_run_budget",
                                "projected_cost_with_reserve_usd": str(forecast)}
            if fits:
                admitted.append(model)
                committed += forecast
        return {"eligible_models": qualification["eligible_models"], "admitted_models": admitted,
                "projections": forecasts, "completion_budget": self.budget.admission(
                    spent_usd=screen_cost, remaining_usd=committed)}


class OfflineRunner(ExtensionRunner):
    def __init__(self, plan, ledger, *, receipts):
        protocol.verify_draft(plan)
        if type(receipts) is not dict:
            raise TypeError("Only a supplied offline receipt dictionary is accepted")
        self.receipts = deepcopy(receipts)
        super().__init__(plan, "offline-unfrozen", common.digest(plan), ledger)

    def call(self, call_id, spec, request, phase, metadata):
        request = private_request(request)
        if self.ledger.existing(call_id) is not None:
            return super().call(call_id, spec, request, phase, metadata)
        if self._existing_only or call_id not in self.receipts:
            raise Halted("Offline receipt absent; network dispatch is unavailable")
        supplied = self.receipts[call_id]
        if common.canonical(supplied["request"]) != common.canonical(request):
            raise Halted("Offline receipt request differs")
        replay = CommonRunner(self.plan, self.freeze, self.plan_hash, self.ledger,
                              lambda _request: deepcopy(supplied["raw"]))
        replay.stop = self.stop
        return replay.call(call_id, spec, request, phase, metadata)
