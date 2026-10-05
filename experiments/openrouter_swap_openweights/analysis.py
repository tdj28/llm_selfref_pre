"""Reuse paired estimators without mutating the completed eight-test family."""

from experiments.openrouter_swap import analysis as common
from experiments.openrouter_swap.ledger import Halted
from . import protocol


def _rows(rows, phase):
    expected = {s["id"]: s for b in protocol.inventory(phase) for s in b["finals"]}
    records = list(rows)
    seen = set()
    for row in records:
        spec = expected.get(row.get("id"))
        if spec is None or row["id"] in seen or any(row.get(k) != v for k, v in spec.items()):
            raise Halted("Foreign, duplicate or changed extension inventory")
        seen.add(row["id"])
    return records


def qualify(rows):
    result = common.qualify(_rows(rows, "screen"))
    result["inventory_valid"] &= set(result["models"]) == set(protocol.MODELS)
    if not result["inventory_valid"]:
        result["eligible_models"] = []
    return result


def analyze(rows, phase):
    rows = _rows(rows, phase)
    result = common.analyze(rows, phase)
    family = result["primary_family"]
    family.update(fixed_family_size=protocol.FAMILY_SIZE,
                  hoeffding_radius_at_32_blocks=common._hoeffding_radius(32, protocol.FAMILY_SIZE),
                  study="openweights_extension_only", planned_models=list(protocol.MODELS))
    if phase == "screen":
        result["qualification"] = qualify(rows)
    else:
        for model in result["models"].values():
            if not model["judges"]:
                continue
            contrasts = model["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
            for name in common.PRIMARY_CONTRASTS:
                c = contrasts[name]
                n, planned = c["complete_blocks"], c["planned_blocks"]
                mean = c["complete_case_mean"]
                c["familywise_radius_at_planned_n"] = common._hoeffding_radius(planned, protocol.FAMILY_SIZE)
                c["familywise_hoeffding_95"] = common._hoeffding(c["worst_case_mean_bounds"], planned, protocol.FAMILY_SIZE)
                c["complete_case_familywise_hoeffding_95"] = common._hoeffding([mean, mean], n, protocol.FAMILY_SIZE)
    return result
