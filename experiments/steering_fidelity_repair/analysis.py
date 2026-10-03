"""Pure singleton delivery/competence qualification, independent of pressure.

The parent materializes neutral validation even when pressure discovery fails.
One shared baseline per item plus two singleton edits gives 120 scores (80 new
edits). A selected pressure validation adds only its 80 non-neutral scores.
"""
from __future__ import annotations

import math

from experiments.steering_fidelity.analysis import _competence, _metric, _precision
from experiments.steering_fidelity.audit import delivery_summary
from experiments.steering_fidelity.protocol import DELIVERY
from . import items
from .liveness import ARMS, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, _index


def singleton_inventory():
    """Keep shared pressure-baseline IDs; only positive arms receive new IDs."""
    from .protocol import singleton_rows, validation_neutral_rows
    return validation_neutral_rows() + singleton_rows()


def _score(row):
    if row.get("missing") is not False:
        raise ValueError("Missing singleton outcome")
    for field in ("correct", "format_valid"):
        if type(row.get(field)) is not bool:
            raise ValueError("Nonboolean singleton score")
    for field in ("p_yes", "p_no", "p_correct", "valid_mass"):
        value = row.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Invalid singleton choice probability")
    mass = row["valid_mass"]
    if mass <= 0 or not math.isclose(row["p_yes"] + row["p_no"], mass, rel_tol=1e-12, abs_tol=1e-15):
        raise ValueError("Inconsistent singleton choice mass")
    correct = (row["p_yes"] if row["truth"] else row["p_no"]) / mass
    if not math.isclose(row["p_correct"], correct, rel_tol=1e-12, abs_tol=1e-15) or row["correct"] != (correct > .5):
        raise ValueError("Inconsistent singleton correct-answer score")
    try:
        delivery = delivery_summary(row["telemetry"])
        if row.get("delivery") != delivery:
            raise ValueError("Singleton delivery differs from raw telemetry")
        zero = row["arm"] == "zero"
        if delivery["true_zero"] is not zero:
            raise ValueError("Singleton arm has wrong zero/nonzero delivery")
        edit = row["intervention"]
        if edit != row["telemetry"].get("intervention"):
            raise ValueError("Singleton intervention differs from telemetry")
        if zero:
            if edit is not None:
                raise ValueError("Singleton zero was edited")
        elif (not isinstance(edit, dict) or edit.get("feature_ids") != [row["feature_id"]]
              or edit.get("sign") != 1 or edit.get("weights") != [.5]
              or type(edit.get("requested_norm")) not in (int, float)
              or not math.isfinite(edit["requested_norm"]) or edit["requested_norm"] <= 0):
            raise ValueError("Wrong positive singleton intervention")
    except (KeyError, TypeError, AttributeError, ZeroDivisionError) as error:
        raise ValueError("Malformed singleton delivery telemetry") from error


def singleton_gate(rows):
    """Require complete 40 zero + 80 edited rows; invalid/incomplete input raises.

Use the original per-position delivery audit and >=95% qualified trials per
feature. Each feature must preserve competence/format in all four ten-item
truth/family cells, with upper central-90% paired accuracy loss <=.10. Bootstrap
units are items within each stratum (one member of each context truth pair).
No pooled family or feature estimate can rescue a cell. Requested 0.30R norm
    binding to the frozen clean reference remains the parent's raw provenance audit.
"""
    specs, found = _index(rows, singleton_inventory())
    if found.keys() != specs.keys():
        raise ValueError("Incomplete singleton inventory: require 40 zero and 80 edited scores")
    ordered = [found[key] for key in specs]
    for row in ordered:
        _score(row)
    cells, features = [], []
    for family in items.FAMILIES:
        for truth in (False, True):
            zeros = sorted((r for r in ordered if r["arm"] == "zero" and r["family"] == family
                            and r["truth"] is truth), key=lambda r: r["item_id"])
            if len(zeros) != 10:
                raise ValueError("Singleton cells require ten baseline items")
            baseline = {metric: _metric(zeros, metric) for metric in
                        ("correct", "p_correct", "format_valid", "valid_mass")}
            baseline_pass = (baseline["correct"]["estimate"] >= .8
                             and baseline["format_valid"]["estimate"] >= .95
                             and baseline["valid_mass"]["estimate"] >= .95)
            arms = []
            for arm, feature in ARMS[1:]:
                edited = sorted((r for r in ordered if r["arm"] == arm and r["family"] == family
                                 and r["truth"] is truth), key=lambda r: r["item_id"])
                if [r["item_id"] for r in zeros] != [r["item_id"] for r in edited]:
                    raise ValueError("Singleton item pairs differ")
                competence = _competence(zeros, edited, BOOTSTRAP_SEED, BOOTSTRAP_DRAWS)
                competence["mass_pass"] = competence["valid_mass"]["estimate"] >= .95
                competence["pass"] = competence["pass"] and competence["mass_pass"]
                arms.append({"arm": arm, "feature_id": feature, **competence})
            cells.append({"family": family, "truth": truth, "n": 10, "baseline": baseline,
                          "baseline_pass": baseline_pass, "arms": arms,
                          "pass": baseline_pass and all(a["pass"] for a in arms)})
    for arm, feature in ARMS[1:]:
        precision = _precision([r for r in ordered if r["arm"] == arm])
        precision["threshold_source"] = "original audit.delivery_summary reconstructed from raw telemetry"
        features.append({"arm": arm, "feature_id": feature, "delivery": precision,
                         "pass": precision["pass"] and all(c["baseline_pass"] and
                             next(a for a in c["arms"] if a["arm"] == arm)["pass"] for c in cells)})
    passed = all(f["pass"] for f in features)
    return {"schema": "fidelity_repair_singleton_gate_v1", "status": "complete",
            "n_expected": 120, "n_observed": 120, "zero_rows": 40, "edited_rows": 80,
            "rung": "rho300", "delivery_thresholds": dict(DELIVERY), "cells": cells,
            "features": features, "pass": passed, "generation_qualified": passed,
            "pressure_dependency": False, "stage_t_authorized": False,
            "bootstrap": {"seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS,
                          "unit": "paired item within truth/family cell", "interval": "central_90_percent"}}
