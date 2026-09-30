"""Frozen optional comparator branch; importing performs no model/network work.

Selection uses calibration activations and decoder geometry only. Three panels
are assigned sequentially, never rematched after delivery or outcome inspection.
optional(run) delegates execution to the parent's guarded, resumable runner.
"""

from __future__ import annotations

import math
from pathlib import Path

from experiments.sae_assay_diagnostic import analysis


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _positive(value, name):
    _require(type(value) in (int, float) and math.isfinite(value) and value > 0,
             f"Missing/nonpositive/nonfinite {name}")
    return value


def _load(path):
    return analysis.strict_json_loads(Path(path).read_text())


def _assignment(costs):
    """Hungarian optimum with exact-cost, ascending-column lexicographic ties.

    No epsilon perturbation changes the objective. Targets retain frozen order;
    callers sort candidate IDs. Infinity is internal only, never released JSON.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    matrix = np.asarray(costs, dtype=float)
    r, c = linear_sum_assignment(matrix)
    _require(len(r) == len(matrix), "Incomplete comparator assignment")
    optimum = math.fsum(float(matrix[i, j]) for i, j in zip(r, c))
    _require(math.isfinite(optimum), "Infeasible comparator assignment")
    chosen, available, prefix = [], list(range(matrix.shape[1])), []
    for i in range(len(matrix)):
        for j in available:
            if not math.isfinite(matrix[i, j]):
                continue
            remaining = [v for v in available if v != j]
            suffix = []
            if i + 1 < len(matrix):
                try:
                    rr, cc = linear_sum_assignment(matrix[i + 1:, remaining])
                    suffix = [float(matrix[i + 1 + x, remaining[y]]) for x, y in zip(rr, cc)]
                    if len(suffix) != len(matrix) - i - 1:
                        continue
                except ValueError:
                    continue
            if math.fsum(prefix + [float(matrix[i, j])] + suffix) == optimum:
                chosen.append(j)
                prefix.append(float(matrix[i, j]))
                available.remove(j)
                break
        else:
            raise ValueError("Could not preserve Hungarian optimum in exact-cost tie resolution")
    return chosen, optimum


def match_panels(rows, metadata, target_ids, matching):
    """Return three disjoint six-feature panels or the preserved partial failure."""
    candidates = matching["candidate_ids"]
    _require(len(target_ids) == 6 and len(set(target_ids)) == 6 and all(
        type(v) is int and 0 <= v < 65536 for v in target_ids), "Six distinct targets required")
    _require(len(candidates) == 512 and len(set(candidates)) == 512 and all(
        type(v) is int and 0 <= v < 65536 for v in candidates), "Frozen 512-ID pool required")
    excluded = set(target_ids) | set(matching["excluded_previous_ids"])
    _require(not excluded.intersection(candidates), "Candidate pool includes excluded/target IDs")
    _require(matching["method"] == "sequential_hungarian_log_distance_no_relaxation", "Unknown matching method")
    for key in ("norm_ratio", "positive_frequency_ratio", "positive_q90_ratio"):
        lo, hi = matching[key]
        _positive(lo, key)
        _require(type(hi) in (int, float) and math.isfinite(hi) and hi >= lo, "Invalid matching caliper")
    _require(type(matching["max_abs_target_cosine"]) in (int, float)
             and 0 <= matching["max_abs_target_cosine"] <= 1, "Invalid cosine caliper")
    q = analysis.calibration_q90(rows)
    _require("invalid_data" not in q["failure_codes"], "Malformed pool telemetry")
    expected = list(target_ids) + list(candidates)
    _require(q["feature_ids"] == expected and metadata["feature_ids"] == expected
             and metadata["target_ids"] == list(target_ids), "Pool/metadata feature order differs from plan")
    analysis._json(metadata)
    entries = metadata["features"]
    _require(len(entries) == len(expected) and [r["feature_id"] for r in entries] == expected,
             "Decoder metadata incomplete, duplicate or reordered")
    stats = {}
    for activation, decoder in zip(q["features"], entries):
        total = sum(v["eligible_positions"] for v in activation["text_contributions"].values())
        norm = _positive(decoder["decoder_norm"], "decoder norm")
        cosine = decoder["max_abs_target_cosine"]
        _require(type(cosine) in (int, float) and math.isfinite(cosine) and cosine >= 0, "Invalid cosine")
        stats[activation["feature_id"]] = {
            "feature_id": activation["feature_id"], "decoder_norm": norm,
            "positive_frequency": activation["positive_positions"] / total if total else None,
            "positive_q90": activation["q90"], "max_abs_target_cosine": cosine,
            "positions": total, "positive_positions": activation["positive_positions"]}
    result = {"pass": False, "failure_codes": [], "panels": [], "candidate_statistics":
              [stats[i] for i in sorted(stats)], "method": matching["method"],
              "cost": "sum(abs(log(candidate/target))) over norm, positive frequency and positive q90",
              "ties": "lexicographic ascending candidate IDs at identical Hungarian optimum, frozen target order",
              "rematching_after_delivery": False}
    if any(not stats[t]["positive_frequency"] or stats[t]["positive_q90"] is None for t in target_ids):
        result.update(failure_codes=["comparator_unavailable"], reason="Target unavailable in pool calibration")
        return result
    available = sorted(candidates)
    for panel in range(1, 4):
        costs, admissible = [], {}
        for target in target_ids:
            line = []
            for candidate in available:
                p, c = stats[target], stats[candidate]
                ratios = {}
                allowed = c["max_abs_target_cosine"] <= matching["max_abs_target_cosine"]
                for name, key in (("decoder_norm", "norm_ratio"),
                                  ("positive_frequency", "positive_frequency_ratio"),
                                  ("positive_q90", "positive_q90_ratio")):
                    ratio = c[name] / p[name] if c[name] is not None and c[name] > 0 else None
                    ratios[name] = ratio
                    allowed = allowed and ratio is not None and matching[key][0] <= ratio <= matching[key][1]
                cost = math.fsum(abs(math.log(v)) for v in ratios.values()) if allowed else math.inf
                line.append(cost)
                if allowed:
                    admissible[(target, candidate)] = ratios
            costs.append(line)
        try:
            columns, total_cost = _assignment(costs)
        except ValueError as exc:
            result.update(failure_codes=["comparator_unavailable"], failed_panel=panel, reason=str(exc),
                          admissible_candidate_counts={str(t): sum(math.isfinite(v) for v in line)
                                                       for t, line in zip(target_ids, costs)})
            return result
        selected = [available[j] for j in columns]
        result["panels"].append({"group": f"panel{panel}", "feature_ids": selected,
                                  "total_cost": total_cost, "pairs": [
            {"target_id": t, "candidate_id": c, "ratios": admissible[(t, c)],
             "cost": costs[i][columns[i]]} for i, (t, c) in enumerate(zip(target_ids, selected))]})
        available = [c for c in available if c not in selected]
    result["pass"] = True
    return result


def achieved_norm_match(target_rows, panel_rows, bounds=(.8, 1.25)):
    """Calibration-only magnitude matching on the union of actual edited positions.

    Both arrays use the identical position mask. A zero in either arm is kept;
    independently filtering positive norms would hide exposure differences.
    """
    for rows in (target_rows, panel_rows):
        _require(analysis.validate_teacher_rows(rows)["pass"], "Invalid delivered-norm telemetry")
        _require(all(r["split"] == "calibration" for r in rows), "Norm matching is calibration-only")
    lo, hi = bounds
    _positive(lo, "norm-ratio lower bound")
    _require(type(hi) in (int, float) and math.isfinite(hi) and hi >= lo, "Invalid norm-ratio upper bound")
    reports = {}
    for mode in analysis.DIRECTIONS:
        def index(rows):
            chosen = [r for r in rows if r["mode"] == mode]
            indexed = {r.get("text_id", r["id"]): r for r in chosen}
            _require(len(chosen) == len(indexed) and indexed, "One dose and complete direction required")
            return indexed
        targets, panels = index(target_rows), index(panel_rows)
        _require(set(targets) == set(panels), "Target/panel norm text inventory differs")
        tnorm, pnorm, all_positions = [], [], 0
        for text in sorted(targets):
            left, right = targets[text], panels[text]
            t, p = left["result"]["telemetry"], right["result"]["telemetry"]
            _require(left["strength"] == right["strength"] and left["category"] == right["category"]
                     and left["result"]["token_ids"] == right["result"]["token_ids"]
                     and t["position_metadata"] == p["position_metadata"]
                     and t["delivery"]["clean_norm"] == p["delivery"]["clean_norm"],
                     "Unpaired target/panel dose, tokens or clean states")
            a, b = t["delivery"]["realized_norm"], p["delivery"]["realized_norm"]
            all_positions += len(a)
            for x, y in zip(a, b):
                if x > 0 or y > 0:
                    tnorm.append(x)
                    pnorm.append(y)
        quantiles = {}
        for name, q in (("median", .5), ("p90", .9)):
            t, p = analysis._quantile(tnorm, q), analysis._quantile(pnorm, q)
            ratio = p / t if t is not None and t > 0 else None
            _require(ratio is None or math.isfinite(ratio), "Nonfinite delivered-norm ratio")
            quantiles[name] = {"target": t, "panel": p, "ratio": ratio,
                               "pass": ratio is not None and lo <= ratio <= hi}
        reports[mode] = {"pass": all(v["pass"] for v in quantiles.values()), "quantiles": quantiles,
                         "all_positions": all_positions, "paired_edit_positions": len(tnorm),
                         "target_zero_positions": sum(v == 0 for v in tnorm),
                         "panel_zero_positions": sum(v == 0 for v in pnorm)}
    return {"pass": all(r["pass"] for r in reports.values()), "directions": reports,
            "bounds": list(bounds), "scope": "Fixed calibration census; shared union-of-actual-edits mask including specials."}


def remainder_budget(run):
    """Whole 210-row remainder admission, never select cells to fit the budget."""
    plan = run.plan
    core = [r for r in plan["response_rows"] if r["phase"] == "core"]
    optional = [r for r in plan["response_rows"] if r["phase"] == "optional"]
    _require(len(core) == 80 and len(optional) == 210, "Frozen 80-core/210-remainder inventory required")
    errors, core_times, judges = [], [], {}
    for item in core:
        row = run.result(item["id"])
        try:
            core_times.append(sum(_positive(row[k]["elapsed_seconds"], "core generation time")
                                  for k in ("generation1", "generation2")))
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(f'{item["id"]}: {exc}')
    for rubric in ("paper", "notebook"):
        path = run.out / f"local-{rubric}-fixtures.json"
        if not path.exists():
            errors.append(f"Missing {rubric} fixture verdict")
            continue
        fixture = _load(path)
        if fixture.get("pass") is False:
            judges[rubric] = {"status": "not_run_by_gate", "estimated_seconds": 0}
            continue
        if fixture.get("pass") is not True:
            errors.append(f"Malformed {rubric} fixture verdict")
            continue
        times = []
        for item in core:
            response = run.result(item["id"])
            if response is None or response.get("status") != "ok":
                continue
            row = run.result(f'judge-{rubric}-{item["id"]}')
            try:
                times.append(_positive(row["elapsed_seconds"], "local judge time"))
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(f'{rubric}/{item["id"]}: {exc}')
        if not times:
            errors.append(f"No measured {rubric} judge times")
        judges[rubric] = {"measured_calls": len(times), "max_seconds": max(times) if times else None,
                          "estimated_seconds": 210 * max(times) if times else None}
    remaining = run.deadline - run.clock()
    _require(math.isfinite(remaining), "Nonfinite deadline/clock")
    baseline_estimate = 3 * (math.fsum(core_times) / 80) * 210 if not errors else None
    estimate = (baseline_estimate + 1200 +
                math.fsum(v["estimated_seconds"] for v in judges.values())) if not errors else None
    return {"pass": estimate is not None and estimate + 1800 < remaining,
            "errors": errors, "core_rows_measured": len(core_times),
            "baseline_estimate_seconds": baseline_estimate,
            "reload_seconds": 1200, "judge_estimates": judges, "estimate_seconds": estimate,
            "retrieval_release_reserve_seconds": 1800, "remaining_seconds_at_admission": remaining,
            "rule": "3 * mean complete core trial generation time * 210 + 20min reload + 210 * max observed time per eligible local rubric; preserve 30min reserve"}


def optional(run):
    """Execute only this runner's optional branch; no provider/pod management."""
    from experiments.sae_assay_diagnostic.runner import teacher_id, write_once

    destination = run.out / "optional.json"
    if destination.exists():
        return _load(destination)

    def finish(status, **details):
        result = {"status": status, **details}
        write_once(destination, result)
        return result

    target_path = run.out / "target-delivery.json"
    if not target_path.exists() or _load(target_path).get("pass") is not True:
        return finish("not_run_by_gate", reason="Target delivery did not pass")
    target = _load(target_path)
    _require(type(target.get("strength")) in (int, float) and
             target["strength"] in analysis.STRENGTHS, "Invalid frozen target strength")
    core = [r for r in run.plan["response_rows"] if r["phase"] == "core"]
    if len(core) != 80 or any(run.result(r["id"]) is None for r in core):
        return finish("not_run_by_gate", reason="Complete 80-row core must precede optional work")
    pool = run.plan["matching"]["candidate_ids"]
    _require(run.plan["positive_control"]["feature_id"] not in pool, "Candidate pool includes positive control")
    targets = run.plan["target_feature_ids"]
    ids = targets + pool
    calibration = [r for r in run.plan["texts"] if r["split"] == "calibration"]
    _require(len(calibration) == 48, "Exactly 48 frozen calibration texts required")
    started = any(run.result("pool-" + item["id"]) is not None for item in calibration)
    try:
        run.check_time(1800)
        rows = []
        for item in calibration:
            run.check_time(1800)
            identifier = "pool-" + item["id"]

            def operation(item=item, identifier=identifier):
                result = run.model().teacher(item["text"], ids, collect_reconstruction=False)
                return {"id": identifier, "text_id": item["id"], "group": "pool", "mode": "zero",
                        "strength": 0, "split": "calibration", "category": item["category"], "result": result}

            def validate(row):
                _require(analysis.validate_teacher_rows([row])["pass"], "Invalid pool teacher row")

            started = True
            rows.append(run.row(identifier, operation, validate))
        metadata_path = run.out / "pool-decoder-metadata.json"
        if metadata_path.exists():
            metadata = _load(metadata_path)
        else:
            metadata = run.model().feature_metadata(ids, targets)
            write_once(metadata_path, metadata)
        matched = match_panels(rows, metadata, targets, run.plan["matching"])
        write_once(run.out / "optional-matching.json", matched)
        if not matched["pass"]:
            return finish("not_run_by_gate", reason="No three admissible panels", matching=matched)
        panel_results = []
        for panel in matched["panels"]:
            run.check_time(1800)
            delivered = run.delivery(panel["group"], run.plan["texts"], panel["feature_ids"],
                                     fixed_strength=target["strength"])
            norms = None
            if delivered["pass"]:
                def raw(group):
                    return [run.result(teacher_id(group, item, mode, target["strength"]))
                            for item in calibration for mode in analysis.DIRECTIONS]
                norms = achieved_norm_match(raw("target"), raw(panel["group"]),
                            run.plan["matching"]["achieved_edit_median_and_p90_ratio"])
            panel_results.append({"group": panel["group"], "delivery": delivered, "norm_match": norms,
                                  "pass": delivered["pass"] and norms is not None and norms["pass"]})
            write_once(run.out / (panel["group"] + "-norm-match.json"), panel_results[-1])
        write_once(run.out / "optional-panel-qualification.json", {"panels": panel_results})
        if not all(r["pass"] for r in panel_results):
            return finish("not_run_by_gate", reason="Fixed comparator panel failed; no rematching", panels=panel_results)
        budget = remainder_budget(run)
        if not budget["pass"]:
            remainder_started = any(run.result(r["id"]) is not None for r in run.plan["response_rows"]
                                    if r["phase"] == "optional")
            return finish("incomplete" if remainder_started else "not_run_budget",
                          reason="Complete remainder not conservatively affordable", budget=budget,
                          remainder_status="incomplete" if remainder_started else "not_run_budget", panels=panel_results)
        admission = run.out / "optional-remainder-admission.json"
        if not admission.exists():
            write_once(admission, budget)
        run.check_time(budget["estimate_seconds"] + 1800)
        run.baseline("optional")
        _require(all(run.result(r["id"]) is not None for r in run.plan["response_rows"] if r["phase"] == "optional"),
                 "Optional baseline returned with missing planned rows")
        run.local_judges("optional")
        return finish("complete", panels=panel_results, budget=budget,
                      response_inventory=[r["id"] for r in run.plan["response_rows"] if r["phase"] == "optional"])
    except TimeoutError as exc:
        return finish("incomplete" if started else "not_run_budget", reason=str(exc),
                      remainder_status="not_run_budget", raw_rows_preserved=True)
