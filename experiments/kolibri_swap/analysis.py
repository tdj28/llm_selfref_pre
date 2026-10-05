"""Offline block-paired analysis; the Kolibri family contains exactly two tests."""

from collections import Counter

from experiments.openrouter_swap import analysis as common
from experiments.openrouter_swap.ledger import Halted
from . import protocol


def _rows(rows, phase):
    expected = {s["id"]: s for b in protocol.inventory(phase) for s in b["finals"]}
    records = list(rows)
    seen = set()
    for row in records:
        if not isinstance(row, dict):
            raise Halted("Kolibri final row must be an object")
        if not isinstance(row.get("id"), str):
            raise Halted("Kolibri row ID must be a string")
        spec = expected.get(row["id"])
        if (spec is None or row["id"] in seen
                or any(type(row.get(k)) is not type(v) or row.get(k) != v for k, v in spec.items())):
            raise Halted("Foreign, duplicate or changed Kolibri final inventory")
        if "cap_hit" in row and type(row["cap_hit"]) is not bool:
            raise Halted("cap_hit must be a Boolean when recorded")
        seen.add(row["id"])
    return records


def qualify(rows):
    """The existing inclusive headroom/quality gate; never an effect-sign gate."""
    result = common.qualify(_rows(rows, "screen"))
    result["inventory_valid"] &= set(result["models"]) == {protocol.MODEL_KEY}
    if not result["inventory_valid"]:
        result["eligible_models"] = []
    return result


def _generation_summary(rows, phase):
    """Expose censoring separately from endpoint negatives and judge refusals."""
    expected = [s for b in protocol.inventory(phase) for s in b["finals"]]
    observed = {r["id"]: r for r in rows}
    cells = common.SCREEN_CELLS if phase == "screen" else common.MAIN_CELLS
    result = {}
    for cell in cells:
        slots = [observed.get(s["id"]) for s in expected if s["cell"] == cell]
        present = [r for r in slots if r is not None]
        result[cell] = {
            "planned": len(slots), "recorded": len(present), "absent_rows": len(slots) - len(present),
            "response_missing": sum(common._response_missing(r) is not None for r in slots),
            "cap_hit": sum(r.get("cap_hit") is True for r in present),
            "cap_unknown": sum("cap_hit" not in r for r in present),
            "nonempty_capped_response": sum(r.get("cap_hit") is True and not common._response_missing(r)
                                             for r in present),
            "blank_or_unavailable_final_content": sum(not isinstance(r.get("response"), str)
                                                      or not r["response"].strip() for r in present),
            "recorded_refusal_status": sum(r.get("status") == "refusal" for r in present),
            "statuses": dict(sorted(Counter(str(r.get("status", "missing_status")) for r in present).items())),
            "refusal": {judge: common._cell_summary(
                [common._value(r, judge, "refusal") for r in slots], len(slots))
                for judge in common.JUDGES},
        }
    return result


def analyze(rows, phase):
    """Recompute all common endpoints; replace only the two primary bounds."""
    rows = _rows(rows, phase)
    result = common.analyze(rows, phase)
    result["primary_family"].update(
        fixed_family_size=protocol.FAMILY_SIZE, planned_models=[protocol.MODEL_KEY],
        study="kolibri_extension_only",
        hoeffding_radius_at_32_blocks=common._hoeffding_radius(32, protocol.FAMILY_SIZE),
    )
    result["generation_by_cell"] = _generation_summary(rows, phase)
    result["inventory_valid"] = (set(result["models"]) == {protocol.MODEL_KEY}
                                 and all(m["inventory"]["complete"] for m in result["models"].values()))
    result["interpretation"] = {
        "headroom_selected": True, "neutral_null_is_equivalence": False,
        "same_condition_sham_eliminates_mismatch": False,
        "reasoning_text_is_endpoint": False,
        "architecture_or_sophistication_causally_identified": False,
        "missing_or_refusal_is_negative": False,
    }
    if phase == "screen":
        result["qualification"] = qualify(rows)
        return result
    for model in result["models"].values():
        if not model["judges"]:
            continue
        contrasts = model["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
        for name in common.PRIMARY_CONTRASTS:
            contrast = contrasts[name]
            n, planned = contrast["complete_blocks"], contrast["planned_blocks"]
            mean = contrast["complete_case_mean"]
            contrast["familywise_radius_at_planned_n"] = common._hoeffding_radius(planned, protocol.FAMILY_SIZE)
            contrast["familywise_hoeffding_95"] = common._hoeffding(
                contrast["worst_case_mean_bounds"], planned, protocol.FAMILY_SIZE)
            contrast["complete_case_familywise_hoeffding_95"] = common._hoeffding(
                [mean, mean], n, protocol.FAMILY_SIZE)
    return result
