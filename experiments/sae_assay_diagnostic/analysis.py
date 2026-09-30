"""Offline engineering gates; no model imports, calls, file writes or inference.

Teacher rows: {id, split, category, group, mode, strength, result}. ``id`` is
the fixture/text ID shared by its arms; an explicit ``text_id`` may instead
bind unique run-row IDs to that fixture. Pass one group/split to gate_pair.
Counts describe a census of these fixed texts, not iid token observations.
The runner owns frozen inventory completeness and one-time validation dispatch.

Formatting rows: {task_id, arm, seed, status, result: {response, cap_hit},
nondegenerate}. ``id`` can replace task_id, and response/cap_hit can be flat.
The runner must provide the separately frozen nondegeneracy assessment as a
Boolean; this module does not confuse valid JSON with coherent task completion.
"""

from __future__ import annotations

from collections import Counter
import json
import math

from experiments.sae_assay_diagnostic.fixtures import positive_control, score_positive


DIRECTIONS = ("suppression", "amplification")
STRENGTHS = (0.5, 1.0)
ACTIVATIONS = ("before", "requested_delta", "requested_activation", "after")
DELIVERY = ("cosine", "relative_error", "requested_norm", "realized_norm", "clean_norm")
FAILURE_ORDER = ("invalid_data", "insufficient_exposure", "numerical_delivery",
                 "coordinate_efficacy", "excessive_norm", "language_loss",
                 "comparator_unavailable", "encoder_decision_disagreement")
SCOPE = "Fixed-text diagnostic census; tokens are not independent sampling units."


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json(value, path="$", active=None):
    """Only exact JSON types and finite numbers, including ignored extra fields."""
    active = set() if active is None else active
    if type(value) in (dict, list):
        _require(id(value) not in active, f"{path}: cyclic object")
        active.add(id(value))
        try:
            for key, item in (value.items() if type(value) is dict else enumerate(value)):
                if type(value) is dict:
                    _require(type(key) is str, f"{path}: non-string key")
                _json(item, f"{path}.{key}", active)
        finally:
            active.remove(id(value))
    elif type(value) in (float, int):
        _require(abs(value) <= float("1.7976931348623157e308"), f"{path}: nonfinite number")
    else:
        _require(value is None or type(value) in (str, bool), f"{path}: not JSON")


def strict_json_loads(text):
    """Reject duplicate keys, NaN/Infinity, exponent overflow and non-JSON types."""
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, f"Duplicate key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"Non-JSON numeric constant: {value}")

    result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    _json(result)
    return result


def _number(value, path, minimum=None):
    _require(type(value) in (float, int), f"{path}: expected number, not bool/null")
    _require(math.isfinite(value), f"{path}: nonfinite")
    _require(minimum is None or value >= minimum, f"{path}: below {minimum}")


def _matrix(value, n, k, path, nonnegative=False):
    _require(type(value) is list and len(value) == n, f"{path}: wrong position count")
    for i, row in enumerate(value):
        _require(type(row) is list and len(row) == k, f"{path}[{i}]: wrong feature count")
        for v in row:
            _number(v, path, 0 if nonnegative else None)


def _vector(value, n, path, *, boolean=False, first_null=False, minimum=None):
    _require(type(value) is list and len(value) == n, f"{path}: wrong position count")
    for i, v in enumerate(value):
        if i == 0 and first_null:
            _require(v is None, f"{path}: first entry must be null")
        elif boolean:
            _require(type(v) is bool, f"{path}: expected Boolean")
        else:
            _number(v, path, minimum)


def _text(row):
    return row.get("text_id", row["id"])


def _eligible(telemetry, i):
    valid = telemetry["delivery"].get("valid")
    return (telemetry["position_metadata"][i]["token_class"] != "special"
            and (valid is None or valid[i]))


def _validate_row(row):
    _json(row)
    _require(type(row) is dict, "row: expected object")
    for key in ("id", "split", "category", "group"):
        _require(type(row[key]) is str and bool(row[key]), f"{key}: expected nonempty string")
    _require(type(_text(row)) is str and bool(_text(row)), "text_id: expected string")
    _require(row["split"] in ("calibration", "validation"), "Unknown split")
    mode, strength = row["mode"], row["strength"]
    _number(strength, "strength")
    _require((mode == "zero" and strength == 0) or
             (mode in DIRECTIONS and strength in STRENGTHS), "Invalid mode/strength")
    result = row["result"]
    tokens, t = result["token_ids"], result["telemetry"]
    _require(type(tokens) is list and len(tokens) > 0 and all(
        type(v) is int and v >= 0 for v in tokens), "token_ids: invalid")
    ids, positions = t["feature_ids"], t["position_metadata"]
    _require(type(ids) is list and ids and all(type(v) is int and v >= 0 for v in ids)
             and len(set(ids)) == len(ids), "feature_ids: invalid/duplicate")
    n, k = len(tokens), len(ids)
    _require(type(positions) is list and len(positions) == n, "position_metadata: wrong count")
    for i, p in enumerate(positions):
        _require(type(p["position"]) is int and p["position"] == i
                 and type(p["token_id"]) is int and p["token_id"] == tokens[i],
                 "Position/token alignment mismatch")
        _require(p["origin"] in ("prompt", "generated") and
                 p["token_class"] in ("special", p["origin"]), "Invalid token class/origin")
    a, d = t["selected_activations"], t["delivery"]
    for key in ACTIVATIONS:
        _matrix(a[key], n, k, key, nonnegative=(key != "requested_delta"))
    for key in DELIVERY:
        _vector(d[key], n, key, minimum=None if key == "cosine" else 0)
    for key in ("nonzero_requested", "valid", "identity"):
        if key == "nonzero_requested" or key in d:
            _vector(d[key], n, key, boolean=True)
    for key in ("unsteered_nll", "edited_nll"):
        _vector(result[key], n, key, first_null=True, minimum=0)
    for key in ("kl_clean_to_edited", "reconstruction_nll"):
        if result.get(key) is not None:
            _vector(result[key], n, key, first_null=True)
    if t.get("q90") is not None:
        _vector(t["q90"], k, "q90", minimum=0)
    for i in range(n):
        _require(-1 <= d["cosine"][i] <= 1, "Cosine outside [-1,1]")
        _require(d["nonzero_requested"][i] == (d["requested_norm"][i] > 0),
                 "nonzero_requested disagrees with requested_norm")
        if not d["nonzero_requested"][i]:
            _require(d["realized_norm"][i] == 0 and d["relative_error"][i] == 0
                     and d["cosine"][i] == 1, "Zero-request delivery convention violated")
        if "identity" in d:
            _require(d["identity"][i] == (d["realized_norm"][i] == 0), "Identity/norm disagreement")
        for j in range(k):
            b, delta, requested, after = (a[key][i][j] for key in ACTIVATIONS)
            _require(math.isclose(b + delta, requested, rel_tol=1e-6, abs_tol=1e-7),
                     "Requested activation != before + delta")
            valid = "valid" not in d or d["valid"][i]
            if mode == "zero" or not valid:
                _require(delta == 0 and after == b and d["realized_norm"][i] == 0,
                         "No-op/masked position changed")
            elif mode == "suppression":
                _require(math.isclose(delta, -strength * b, rel_tol=1e-6, abs_tol=1e-7),
                         "Suppression request differs from frozen operator")
            else:
                _require(delta >= 0, "Negative amplification request")
                if t.get("q90") is not None:
                    _require(math.isclose(delta, strength * max(t["q90"][j] - b, 0),
                                         rel_tol=1e-6, abs_tol=1e-7), "Amplification/q90 mismatch")
    if mode == "zero":
        _require(result["unsteered_nll"] == result["edited_nll"], "Zero changed token loss")
    full = t.get("full_sae") or t.get("full_diagnostics")
    if full is not None:
        for key in ("full_selected_before", "full_selected_after",
                    "selected_path_before", "selected_path_after"):
            if key in full:
                _matrix(full[key], n, k, key, nonnegative=True)


def validate_teacher_rows(rows):
    """All row errors are retained; invalid rows never produce a passing gate."""
    errors, valid, seen = [], [], set()
    if type(rows) is not list or not rows:
        return {"pass": False, "errors": ["Expected a nonempty JSON array of rows"],
                "valid_indices": [], "row_count": len(rows) if type(rows) is list else 0}
    for index, row in enumerate(rows):
        try:
            _validate_row(row)
            key = (row["split"], row["group"], _text(row), row["mode"], row["strength"])
            _require(key not in seen, "Duplicate text/arm")
            seen.add(key)
            valid.append(index)
        except (ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
            errors.append(f"row[{index}]: {exc}")
    return {"pass": not errors, "errors": errors, "valid_indices": valid, "row_count": len(rows)}


def _quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    at = (len(ordered) - 1) * q
    low, high = math.floor(at), math.ceil(at)
    fraction = at - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def _distribution(values):
    return {"count": len(values), "zero_count": sum(v == 0 for v in values),
            "positive_count": sum(v > 0 for v in values),
            "positive_fraction": sum(v > 0 for v in values) / len(values) if values else None,
            "min": min(values) if values else None, "median": _quantile(values, .5),
            "q90": _quantile(values, .9), "max": max(values) if values else None}


def calibration_q90(rows):
    """Linear positive-only pooled q90 from zero calibration rows, never validation."""
    check = validate_teacher_rows(rows)
    if not check["pass"]:
        return {"pass": False, "failure_codes": ["invalid_data"], "validation": check,
                "feature_ids": [], "q90": None, "features": [], "scope": SCOPE}
    _require(all(r["split"] == "calibration" and r["mode"] == "zero" for r in rows),
             "q90 accepts zero calibration rows only")
    ids = rows[0]["result"]["telemetry"]["feature_ids"]
    _require(len({r["group"] for r in rows}) == 1 and all(
        r["result"]["telemetry"]["feature_ids"] == ids for r in rows),
        "q90 requires one group and identical ordered features")
    features = []
    for j, feature in enumerate(ids):
        values, contributions, excluded = [], {}, 0
        for row in rows:
            t = row["result"]["telemetry"]
            all_values = [v[j] for i, v in enumerate(t["selected_activations"]["before"])
                          if _eligible(t, i)]
            positives = [v for v in all_values if v > 0]
            excluded += len(t["position_metadata"]) - len(all_values)
            contributions[_text(row)] = {"eligible_positions": len(all_values),
                                         "positive_positions": len(positives),
                                         "zero_positions": len(all_values) - len(positives)}
            values.extend(positives)
        features.append({"feature_id": feature, "q90": _quantile(values, .9),
                         "positive_positions": len(values), "excluded_positions": excluded,
                         "text_contributions": contributions})
    available = all(f["q90"] is not None for f in features)
    return {"pass": available, "failure_codes": [] if available else ["insufficient_exposure"],
            "feature_ids": ids, "q90": [f["q90"] for f in features], "features": features,
            "split": "calibration", "row_count": len(rows), "scope": SCOPE}


def encoder_parity_report(telemetry):
    """Activity-mask agreement, not q90/dose/verdict equivalence certification.

    Supports the old selected-authority/full_selected_* diagnostic and the
    new full-authority/selected_path_* diagnostic. ``pass`` means identical
    masks only, not qualification. The decision gate is encoder_decision_report.
    """
    _json(telemetry)
    full = telemetry.get("full_sae") or telemetry.get("full_diagnostics")
    _require(type(full) is dict, "Encoder comparison was not collected")
    n, k = len(telemetry["position_metadata"]), len(telemetry["feature_ids"])
    reports = {}
    for when in ("before", "after"):
        primary = telemetry["selected_activations"][when]
        alternate = full.get(f"selected_path_{when}", full.get(f"full_selected_{when}"))
        _matrix(primary, n, k, when, nonnegative=True)
        _matrix(alternate, n, k, f"alternate_{when}", nonnegative=True)
        mismatches, differences, nonspecial_compared = [], [], 0
        for i in range(n):
            for j in range(k):
                a, b = primary[i][j], alternate[i][j]
                differences.append(abs(a - b))
                nonspecial_compared += _eligible(telemetry, i)
                if (a > 0) != (b > 0):
                    mismatches.append({"position": i, "feature_id": telemetry["feature_ids"][j],
                                       "primary_active": a > 0, "alternate_active": b > 0,
                                       "nonspecial_valid": _eligible(telemetry, i)})
        reports[when] = {"compared_coordinates": n * k, "activity_mismatches": mismatches,
                         "nonspecial_valid_compared": nonspecial_compared,
                         "nonspecial_valid_mismatches": sum(m["nonspecial_valid"] for m in mismatches),
                         "max_absolute_difference": max(differences) if differences else None}
    passed = n > 0 and k > 0 and not any(v["activity_mismatches"] for v in reports.values())
    return {"pass": passed, "failure_codes": [] if passed else ["activity_mask_mismatch"],
            "diagnostic_only": True,
            "comparisons": reports, "scope": "Activity masks only; parent checks q90, dose and verdict parity."}


def _path(t, when, alternate=False):
    if not alternate:
        return t["selected_activations"][when]
    full = t.get("full_sae") or t.get("full_diagnostics")
    _require(type(full) is dict, "Alternate encoder diagnostic not collected")
    value = full.get(f"selected_path_{when}", full.get(f"full_selected_{when}"))
    _matrix(value, len(t["position_metadata"]), len(t["feature_ids"]),
            f"alternate_{when}", nonnegative=True)
    return value


def _direction(rows, ids, mode, *, alternate=False):
    numerical, bounded, loss, zero_clean = [], [], [], 0
    zero_requests, rounded_away = 0, 0
    features, strata = [], Counter()
    parity, errors = [], []
    for row in rows:
        t, result = row["result"]["telemetry"], row["result"]
        d = t["delivery"]
        for i, p in enumerate(t["position_metadata"]):
            strata[f'{p["origin"]}:{p["token_class"]}:positions'] += 1
            if d["nonzero_requested"][i]:
                numerical.append(d["cosine"][i] >= .95 and d["relative_error"][i] <= .20)
                strata[f'{p["origin"]}:{p["token_class"]}:nonzero_requested'] += 1
                rounded_away += d["realized_norm"][i] == 0
            else:
                zero_requests += 1
            if d["realized_norm"][i] > 0:
                zero_clean += d["clean_norm"][i] == 0
                bounded.append(d["realized_norm"][i] <= .05 * d["clean_norm"][i])
            if row["category"] == "neutral" and i > 0 and _eligible(t, i):
                loss.append(result["edited_nll"][i] - result["unsteered_nll"][i])
        full = t.get("full_sae") or t.get("full_diagnostics")
        if full is not None and any(key.startswith(("selected_path_", "full_selected_")) for key in full):
            try:
                parity.append(encoder_parity_report(t))
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(str(exc))
    for j, feature in enumerate(ids):
        ratios, text_counts = [], {}
        before, after, requests = [], [], []
        all_positions = 0
        for row in rows:
            t = row["result"]["telemetry"]
            a, eligible_count = t["selected_activations"], 0
            bvalues, endvalues = _path(t, "before", alternate), _path(t, "after", alternate)
            all_positions += len(t["position_metadata"])
            for i in range(len(t["position_metadata"])):
                if not _eligible(t, i):
                    continue
                b, delta, end = bvalues[i][j], a["requested_delta"][i][j], endvalues[i][j]
                before.append(b)
                after.append(end)
                requests.append(delta)
                eligible = b > 0 if mode == "suppression" else delta > 0
                if eligible:
                    ratio = end / b if mode == "suppression" else (end - b) / delta
                    _number(ratio, "derived paired coordinate ratio")
                    ratios.append(ratio)
                    eligible_count += 1
            text_counts[_text(row)] = eligible_count
        exposure = len(ratios) >= 100 and sum(v > 0 for v in text_counts.values()) >= 6
        center = _quantile(ratios, .5)
        efficacy = center is not None and (center <= .5 if mode == "suppression" else center >= .5)
        features.append({"feature_id": feature, "exposure_pass": exposure, "efficacy_pass": efficacy,
                         "all_positions": all_positions, "nonspecial_valid_positions": len(before),
                         "eligible_positions": len(ratios), "eligible_texts": sum(v > 0 for v in text_counts.values()),
                         "eligible_by_text": text_counts, "paired_ratio": _distribution(ratios),
                         "before": _distribution(before), "after": _distribution(after),
                         "requested_delta": _distribution(requests)})
    numeric_rate = sum(numerical) / len(numerical) if numerical else None
    norm_rate = sum(bounded) / len(bounded) if bounded else None
    loss_delta = math.fsum(v / len(loss) for v in loss) if loss else None
    checks = {"insufficient_exposure": bool(features) and all(f["exposure_pass"] for f in features),
              "numerical_delivery": numeric_rate is not None and numeric_rate >= .95,
              "coordinate_efficacy": bool(features) and all(f["efficacy_pass"] for f in features),
              "excessive_norm": norm_rate is not None and norm_rate >= .95,
              "language_loss": loss_delta is not None and loss_delta <= .1}
    failures = [key for key, passed in checks.items() if not passed]
    if errors:
        failures.append("invalid_data")
    return {"pass": not failures, "failure_codes": failures, "features": features,
            "row_count": len(rows), "position_strata": dict(sorted(strata.items())),
            "numerical": {"requested_positions": len(numerical), "passing_positions": sum(numerical),
                          "zero_requested_positions": zero_requests, "rounded_away_positions": rounded_away,
                          "pass_fraction": numeric_rate},
            "norm": {"actual_edit_positions": len(bounded), "passing_positions": sum(bounded),
                     "zero_clean_norm_positions": zero_clean, "pass_fraction": norm_rate},
            "neutral_loss": {"tokens": len(loss), "paired_token_weighted_delta": loss_delta},
            "encoder_activity_parity": parity, "errors": errors}


def gate_pair(rows, strength):
    """Evaluate both directions for one group/split, retaining every failure.

    Validate *all* supplied rows even when evaluating one strength. Zero rows
    are optional because teacher outputs contain their own paired clean state;
    if supplied, they must agree with edited arms' exact tokens and clean data.
    Encoder mask drift is descriptive here; the runner must separately enforce
    encoder_decision_report on its frozen qualification shard before bulk work.
    """
    _require(type(strength) in (int, float) and strength in STRENGTHS, "Invalid candidate strength")
    check = validate_teacher_rows(rows)
    valid = [rows[i] for i in check["valid_indices"]]
    errors = list(check["errors"])
    ids = valid[0]["result"]["telemetry"]["feature_ids"] if valid else []
    splits, groups = {r["split"] for r in valid}, {r["group"] for r in valid}
    if len(splits) != 1 or len(groups) != 1:
        errors.append("gate_pair requires exactly one group and split")
    if any(r["result"]["telemetry"]["feature_ids"] != ids for r in valid):
        errors.append("Ordered feature IDs differ between rows")
        valid = []  # Shape-mismatched coordinates cannot be combined even descriptively.
    selected = [r for r in valid if r["strength"] == strength or r["mode"] == "zero"]
    by_text = {}
    for r in selected:
        key = _text(r)
        t, result = r["result"]["telemetry"], r["result"]
        binding = (r["category"], result["token_ids"], t["position_metadata"],
                   t["selected_activations"]["before"], result["unsteered_nll"])
        if key in by_text and binding != by_text[key]:
            errors.append(f"Paired clean/token/category mismatch: {key}")
        by_text[key] = binding
    directed = {m: [r for r in selected if r["mode"] == m] for m in DIRECTIONS}
    expected = set(by_text)
    for mode, arm in directed.items():
        if {_text(r) for r in arm} != expected or not arm:
            errors.append(f"Missing text/direction rows: {mode}")
    reports = {}
    for mode, arm in directed.items():
        try:
            reports[mode] = _direction(arm, ids, mode)
            _json(reports[mode])
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            errors.append(f"{mode}: {exc}")
            reports[mode] = {"pass": False, "failure_codes": ["invalid_data"],
                             "row_count": len(arm), "features": [], "errors": [str(exc)]}
    failures = {c for v in reports.values() for c in v["failure_codes"]}
    if errors:
        failures.add("invalid_data")
    if any(g.startswith("panel") for g in groups) and "insufficient_exposure" in failures:
        failures.add("comparator_unavailable")
    return {"pass": not failures, "failure_codes": [c for c in FAILURE_ORDER if c in failures],
            "errors": errors, "strength": strength, "splits": sorted(splits), "groups": sorted(groups),
            "row_count": check["row_count"], "valid_row_count": len(check["valid_indices"]),
            "split_row_counts": dict(Counter(r["split"] for r in valid)),
            "directions": reports, "scope": SCOPE,
            "partial_metrics_diagnostic_only": bool(errors)}


def encoder_decision_report(rows, strength, *, gate_quantile_opportunities=True):
    """Compare consequential classifications, never change production encoding.

    Evaluate alternate before/after at the *same achieved states*, using the
    canonical actual delta and delivery arrays. This is not a simulation of
    interventions computed by the alternate encoder. Calibration zero rows
    also supply path-specific positive q90 and counterfactual opportunities;
    numeric q90 drift alone does not fail. The caller supplies the frozen
    qualification census (and later the complete calibration if appropriate).
    This helper does not call itself or turn the alternate path into authority.
    """
    baseline = gate_pair(rows, strength)
    if "invalid_data" in baseline["failure_codes"]:
        return {"pass": False, "failure_codes": ["invalid_data"],
                "errors": baseline["errors"], "strengths": {}, "q90": None}
    ids = rows[0]["result"]["telemetry"]["feature_ids"]
    strengths = sorted({r["strength"] for r in rows if r["mode"] in DIRECTIONS})
    comparisons, masks, differences, errors = {}, [], [], []
    for row in rows:
        try:
            masks.append({"id": row["id"], "mode": row["mode"], "strength": row["strength"],
                          "report": encoder_parity_report(row["result"]["telemetry"])})
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            errors.append(f'{row["id"]}/{row["mode"]}: {exc}')
    for candidate in strengths:
        primary = baseline if candidate == strength else gate_pair(rows, candidate)
        if "invalid_data" in primary["failure_codes"]:
            errors.extend(primary["errors"])
            continue
        alternate_pass, per_direction = [], {}
        for mode in DIRECTIONS:
            arm = [r for r in rows if r["mode"] == mode and r["strength"] == candidate]
            try:
                alternate = _direction(arm, ids, mode, alternate=True)
                _json(alternate)
                alternate_pass.append(alternate["pass"])
                features = []
                for p, q in zip(primary["directions"][mode]["features"], alternate["features"]):
                    keys = ("exposure_pass", "efficacy_pass", "eligible_positions", "eligible_texts", "paired_ratio")
                    features.append({"feature_id": p["feature_id"],
                                     "primary": {k: p[k] for k in keys}, "alternate": {k: q[k] for k in keys}})
                    for key in ("exposure_pass", "efficacy_pass"):
                        if p[key] != q[key]:
                            differences.append({"strength": candidate, "mode": mode,
                                                "feature_id": p["feature_id"], "decision": key,
                                                "primary": p[key], "alternate": q[key]})
                per_direction[mode] = {"features": features, "primary_pass": primary["directions"][mode]["pass"],
                                       "alternate_pass": alternate["pass"]}
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                errors.append(f"{candidate}/{mode}: {exc}")
        comparisons[str(candidate)] = {"primary_pass": primary["pass"],
                                        "alternate_pass": len(alternate_pass) == 2 and all(alternate_pass),
                                        "directions": per_direction}
    q90_report = None
    zeros = [r for r in rows if r["mode"] == "zero" and r["split"] == "calibration"]
    if zeros:
        q90_report = {"source_zero_text_ids": [_text(r) for r in zeros], "features": [],
                      "scope": "Path-specific zero-row quantiles and hypothetical opportunities; no alternative edit executed."}
        for j, feature in enumerate(ids):
            paths = {}
            try:
                for alternate, name in ((False, "primary"), (True, "alternate")):
                    values = {}
                    for row in zeros:
                        t = row["result"]["telemetry"]
                        values[_text(row)] = [v[j] for i, v in enumerate(_path(t, "before", alternate))
                                               if _eligible(t, i)]
                    q90 = _quantile([v for vs in values.values() for v in vs if v > 0], .9)
                    counts = {text: sum(q90 is not None and q90 > v for v in vs) for text, vs in values.items()}
                    paths[name] = {"q90": q90, "opportunity_positions": sum(counts.values()),
                                   "opportunity_texts": sum(v > 0 for v in counts.values()),
                                   "opportunities_by_text": counts,
                                   "exposure_pass": sum(counts.values()) >= 100 and sum(v > 0 for v in counts.values()) >= 6}
                q90_report["features"].append({"feature_id": feature, **paths})
                if gate_quantile_opportunities and paths["primary"]["exposure_pass"] != paths["alternate"]["exposure_pass"]:
                    differences.append({"feature_id": feature, "decision": "q90_opportunity_exposure_pass",
                                        "primary": paths["primary"]["exposure_pass"],
                                        "alternate": paths["alternate"]["exposure_pass"]})
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                errors.append(f"q90/{feature}: {exc}")
    complete = strengths == list(STRENGTHS) and len(comparisons) == 2 and not errors
    selected = {path: next((s for s in STRENGTHS if comparisons[str(s)][path + "_pass"]), None)
                if complete else None for path in ("primary", "alternate")}
    failures = (["invalid_data"] if errors else []) + (["encoder_decision_disagreement"] if differences else [])
    return {"pass": not failures, "failure_codes": failures, "errors": errors,
            "quantile_opportunities_gated": gate_quantile_opportunities,
            "requested_strength": strength, "strengths": comparisons, "decision_differences": differences,
            "mask_reports": masks, "q90": q90_report,
            "dose_selection": {"both_strengths_compared": complete, **selected,
                               "agrees": selected["primary"] == selected["alternate"] if complete else None},
            "scope": "Fixed-census encoder decision agreement only, not proof of feature efficacy. Canonical deltas/geometry retained."}


def select_strength(rows, group="target"):
    """No validation/report outcomes accepted. Return the lowest passing dose."""
    _require(type(rows) is list and rows and all(r.get("split") == "calibration"
             and r.get("group") == group for r in rows), "Selection requires calibration-only rows of one group")
    reports = {str(s): gate_pair(rows, s) for s in STRENGTHS}
    chosen = next((s for s in STRENGTHS if reports[str(s)]["pass"]), None)
    return {"pass": chosen is not None, "strength": chosen, "group": group,
            "calibration": reports, "rule": "lowest common passing calibration strength",
            "validation_accessed": False}


def validate_selected(selection, rows):
    """Evaluate the selected dose only. The runner enforces once-only execution."""
    strength = selection.get("strength")
    _require(selection.get("pass") is True and strength in STRENGTHS, "No qualified calibration dose")
    _require(type(rows) is list and rows and all(r.get("split") == "validation"
             and r.get("group") == selection["group"] and
             (r.get("mode") == "zero" or r.get("strength") == strength) for r in rows),
             "Validation must use only the selected group/dose on locked validation texts")
    return gate_pair(rows, strength)


def formatting_gate(rows, expected_task_ids=None):
    """Twenty independent task-seed pairs, four arms; missingness never scores 0.

    Two-sided 95% Hoeffding interval: D in [-1,1], half width
    sqrt(2 log(2/.05)/20) = 0.60736. Independence is a design assumption,
    not an iid-prompt assertion. This is not a population confirmatory test.
    """
    arms = ("zero", "instruction", "suppression", "amplification")
    expected = list(expected_task_ids if expected_task_ids is not None else
                    [r["id"] for r in positive_control()["prompts"]])
    _require(len(expected) == 20 and len(set(expected)) == 20 and all(
        type(v) is str and v for v in expected), "Exactly 20 distinct frozen task IDs required")
    errors, cells = [], {}
    if type(rows) is not list:
        rows, errors = [], ["Expected a JSON row array"]
    for i, row in enumerate(rows):
        try:
            _json(row)
            task, arm = row.get("task_id", row.get("id")), row["arm"]
            _require(task in expected and arm in arms, "Unexpected task/arm")
            key = (task, arm)
            _require(key not in cells, "Duplicate task/arm")
            result = row.get("result", row)
            _require(type(row["seed"]) is int and 0 <= row["seed"] < 2**63, "Invalid seed")
            _require(type(row["status"]) is str, "Missing transport status")
            response = result.get("response") if type(result) is dict else None
            available = row["status"] == "ok" and type(response) is str
            cap = result.get("cap_hit") if type(result) is dict else None
            nondegenerate = row.get("nondegenerate")
            if available:
                if type(cap) is not bool or type(nondegenerate) is not bool:
                    errors.append(f"row[{i}]: Present response requires cap_hit and independent nondegenerate Boolean")
            cells[key] = {"task_id": task, "arm": arm, "seed": row["seed"],
                          "status": row["status"], "missing": not available,
                          "raw_score": int(score_positive(response)) if available else None,
                          "cap_hit": cap if type(cap) is bool else None,
                          "nondegenerate": nondegenerate if type(nondegenerate) is bool else None,
                          "gate_eligible": available and cap is False}
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            errors.append(f"row[{i}]: {exc}")
    for task in expected:
        for arm in arms:
            cells.setdefault((task, arm), {"task_id": task, "arm": arm, "seed": None,
                                          "status": "missing_row", "missing": True,
                                          "raw_score": None, "cap_hit": None,
                                          "nondegenerate": None, "gate_eligible": False})
    seeds = []
    for task in expected:
        task_seeds = {cells[(task, arm)]["seed"] for arm in arms}
        if len(task_seeds) != 1 or None in task_seeds:
            errors.append(f"Unpaired/missing seeds: {task}")
        else:
            seeds.append(next(iter(task_seeds)))
    if len(set(seeds)) != len(seeds):
        errors.append("Task-seed pairs reuse RNG seeds")
    half_width = math.sqrt(2 * math.log(2 / .05) / 20)
    contrasts = {}
    for arm in ("amplification", "instruction", "suppression"):
        differences = [cells[(t, arm)]["raw_score"] - cells[(t, "zero")]["raw_score"]
                       for t in expected if cells[(t, arm)]["gate_eligible"] and cells[(t, "zero")]["gate_eligible"]]
        complete = len(differences) == 20
        estimate = math.fsum(differences) / 20 if complete else None
        interval = [max(-1., estimate - half_width), min(1., estimate + half_width)] if complete else None
        contrasts[arm + "_minus_zero"] = {"paired_n": len(differences), "required_n": 20,
                                          "difference": estimate, "interval95": interval,
                                          "differences": differences,
                                          "pass": complete and estimate >= .3 and interval[0] > 0
                                          if arm != "suppression" else None}
    summaries = {}
    for arm in arms:
        values = [cells[(t, arm)] for t in expected]
        summaries[arm] = {"n": 20, "observed": sum(not c["missing"] for c in values),
                          "positives": sum(c["raw_score"] == 1 for c in values),
                          "capped": sum(c["cap_hit"] is True for c in values),
                          "nondegenerate": sum(c["nondegenerate"] is True for c in values)}
    failures = []
    if errors:
        failures.append("invalid_data")
    if any(c["missing"] for c in cells.values()):
        failures.append("missing_transport")
    if any(v["capped"] > 0 or v["nondegenerate"] / 20 < .95 for v in summaries.values()):
        failures.append("quality_failure")
    primary = contrasts["amplification_minus_zero"]["pass"]
    instruction = contrasts["instruction_minus_zero"]["pass"]
    if not primary:
        failures.append("candidate_effect")
    if not instruction:
        failures.append("endpoint_responsiveness")
    return {"pass": not failures, "failure_codes": failures, "errors": errors,
            "candidate_effect_pass": primary, "instruction_responsiveness_pass": instruction,
            "contrasts": contrasts, "arms": summaries,
            "rows": [cells[(t, a)] for t in expected for a in arms],
            "interval_method": "bounded paired Hoeffding, two-sided 95%, n=20, D in [-1,1]",
            "half_width": half_width, "scope": "Fixed-task engineering diagnostic; independent task-seed pairs assumed, not iid prompts."}
