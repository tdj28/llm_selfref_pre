"""Saved-data-only, post-outcome geometry study. Never dispatches a model.

python -m experiments.sae_assay_repair.analyze_feasibility --run RELEASE --out FRESH
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .feasibility import active_support_projection, bf16_bounds, minimum_inequality, rounding_window
from .reproduce import verify_manifest


SCOPE = (
    "Exploratory conditional continuous geometry from saved Gram/preactivations. "
    "No new native BF16 readback, downstream model forward, NLL or behavioral outcome. "
    "Historical validation is previously observed data, not fresh validation."
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def distribution(values):
    x = np.asarray(values, dtype=float)
    return {"n": int(x.size), "min": float(x.min()) if x.size else None,
            "q25": float(np.quantile(x, .25)) if x.size else None,
            "median": float(np.median(x)) if x.size else None,
            "q75": float(np.quantile(x, .75)) if x.size else None,
            "max": float(x.max()) if x.size else None}


def opportunity_projection(gram, preactivation, before, q90, strength):
    """Most permissive simultaneous per-position version of old amp efficacy.

    Only impose >= half the requested activation increment, not exact targets
    or unchanged ineligible coordinates. This is not the median-level gate.
    """
    p, z = np.asarray(preactivation), np.asarray(before)
    delta = strength * np.maximum(q90 - z, 0)
    eligible = delta > 0
    norms = np.zeros(len(p))
    codes = eligible @ (1 << np.arange(len(gram)))
    for code in sorted(set(codes) - {0}):
        rows = codes == code
        selected = np.flatnonzero(eligible[np.flatnonzero(rows)[0]])
        bounds = (z + .5 * delta - p)[rows][:, selected]
        result = minimum_inequality(gram[np.ix_(selected, selected)], bounds)
        norms[rows] = result["norm"]
    single_norm = np.maximum(z + .5 * delta - p, 0) / np.sqrt(np.diag(gram))
    return {"norm": norms, "eligible": eligible, "single_norm": single_norm}


def single_feature_bound(needed, eligible, clean_norm, nonspecial, all_position_count):
    """Necessary condition only, granting all global norm exceptions to one ID.

    A passing median needs at least ceil(n/2) ratios >= .5 (necessary, not
    sufficient for even n). At most floor(.05*N) positions may exceed the norm
    gate even if EVERY position were edited. This deliberately overgrants
    exceptions, which makes an impossibility flag conservative in this ideal
    linear model. Native BF16 encoding is NOT this model.
    """
    mask = eligible & nonspecial
    n = int(mask.sum())
    possible = int((needed[mask] <= .05 * clean_norm[mask] + 1e-9 * clean_norm[mask]).sum())
    exceptions = int(all_position_count) // 20
    upper = min(n, possible + exceptions)
    return {"eligible_nonspecial_positions": n, "within_norm_necessary_bound": possible,
            "max_global_norm_exceptions_granted_to_this_feature": exceptions,
            "upper_bound_on_efficacious_positions": upper,
            "minimum_positions_needed_for_median": (n + 1) // 2,
            "linear_surrogate_median_impossible": bool(n and upper < (n + 1) // 2)}


def load_clean(run):
    manifest = verify_manifest(run)
    q = json.loads((run / "target-q90.json").read_text())
    geom = json.loads((run / "rows/qualification-live.json").read_text())["geometry"]
    ids = geom["feature_ids"]
    if ids != q["feature_ids"] or len(ids) != 6:
        raise ValueError("Feature IDs do not match")
    rows, seen = [], set()
    for path in sorted((run / "rows").glob("clean-*.json")):
        row = json.loads(path.read_text())
        t = row["result"]["telemetry"]
        if (path.name != row["id"] + ".json" or row["id"] != "clean-" + row["text_id"]
                or row["id"] in seen or row["mode"] != "zero" or row["strength"] != 0
                or t["feature_ids"] != ids or row["split"] not in ("calibration", "validation")):
            raise ValueError("Invalid/duplicate clean row")
        seen.add(row["id"])
        n = len(row["result"]["token_ids"])
        p = np.asarray(t["full_sae"]["fp32_preact_before"], dtype=float)
        z = np.asarray(t["selected_activations"]["before"], dtype=float)
        h = np.asarray(t["delivery"]["clean_norm"], dtype=float)
        positions = t["position_metadata"]
        if (p.shape != (n, 6) or z.shape != p.shape or h.shape != (n,) or len(positions) != n
                or not all(t["delivery"]["valid"]) or any(not np.isfinite(a).all() for a in (p, z, h))
                or (z < 0).any() or (h <= 0).any()):
            raise ValueError("Invalid clean position arrays")
        if [x["token_id"] for x in positions] != row["result"]["token_ids"]:
            raise ValueError("Clean tokens/position metadata differ")
        rows.append((row, p, z, h, np.array([x["token_class"] != "special" for x in positions])))
    if len(rows) != 544 or any(sum(r[0]["split"] == s for r in rows) != 272
                               for s in ("calibration", "validation")):
        raise ValueError("Expected the complete 544-state historical release")
    return manifest, ids, np.asarray(geom["encoder_gram"]), np.asarray(q["q90"], dtype=np.float32), rows


def analyze(run, out):
    run, out = Path(run).resolve(), Path(out).resolve()
    if out == run or run in out.parents or out.exists():
        raise ValueError("Output must be fresh and outside the immutable release")
    manifest, ids, gram, q90, clean = load_clean(run)
    results, bounds_table, proposal_table, positions = {}, [], [], []
    for split in ("calibration", "validation"):
        selected = [r for r in clean if r[0]["split"] == split]
        p = np.concatenate([r[1] for r in selected])
        z = np.concatenate([r[2] for r in selected])
        h = np.concatenate([r[3] for r in selected])
        ns = np.concatenate([r[4] for r in selected])
        qresults = {}
        for strength in (.5, 1.):
            opt = opportunity_projection(gram, p, z, q90, strength)
            features = []
            for j, fid in enumerate(ids):
                item = {"split": split, "strength": strength, "feature_id": fid,
                        **single_feature_bound(opt["single_norm"][:, j], opt["eligible"][:, j],
                                               h, ns, len(h))}
                features.append(item)
                bounds_table.append(item)
            qresults[str(strength)] = {
                "minimum_norm_fraction_all": distribution(opt["norm"] / h),
                "minimum_norm_fraction_nonspecial": distribution(opt["norm"][ns] / h[ns]),
                "nonspecial_simultaneous_within_five_percent": int((opt["norm"][ns] <= .05*h[ns]).sum()),
                "per_feature_necessary_bounds": features}
        prototypes = {}
        for mode in ("suppression", "amplification"):
            a = active_support_projection(gram, p, z, h, mode=mode)
            window = rounding_window(a, p, z, h)
            rho = a["norm"] / h
            rounding = bf16_bounds(rho)
            nz = rho > 0
            numerical_certificate = (rounding["relative_error_upper"] <= .20) & (rounding["cosine_lower"] >= .95)
            features = []
            for j, fid in enumerate(ids):
                eligible = (z[:, j] > 0) & ns
                ratios = (a["predicted_activation"][eligible, j] / z[eligible, j] if mode == "suppression"
                          else (a["predicted_activation"][eligible, j] - z[eligible, j]) / (.75*z[eligible, j]))
                center = float(np.median(ratios)) if len(ratios) else None
                item = {"split": split, "mode": mode, "feature_id": fid,
                        "active_nonspecial_positions": int(eligible.sum()), "predicted_median_ratio": center,
                        "continuous_ratio_criterion": bool(center is not None and
                                                          (center <= .5 if mode == "suppression" else center >= .5)),
                        "not_native_BF16_validation": True}
                w_after = window["predicted_activation"][eligible, j]
                w_ratio = (w_after / z[eligible, j] if mode == "suppression"
                           else (w_after - z[eligible, j]) / (.75*z[eligible, j]))
                dispatched = window["dispatch"][eligible]
                item.update(window_dispatched_active_positions=int(dispatched.sum()),
                            window_all_active_median=float(np.median(w_ratio)) if len(w_ratio) else None,
                            window_dispatched_median=float(np.median(w_ratio[dispatched])) if dispatched.any() else None)
                features.append(item)
                proposal_table.append(item)
            prototypes[mode] = {
                "requested_nonzero_positions": int(nz.sum()), "unchanged_positions": int((~nz).sum()),
                "capped_positions": int((a["scale"] < 1).sum()),
                "continuous_norm_fraction_nonzero": distribution(rho[nz]),
                "conditional_BF16_fidelity_certified_positions": int((nz & numerical_certificate).sum()),
                "conditional_BF16_fidelity_certified_fraction": float(numerical_certificate[nz].mean()) if nz.any() else None,
                "window_dispatched_positions": int(window["dispatch"].sum()),
                "window_all_dispatched_rounding_bounds_pass": bool(np.all(numerical_certificate[window["dispatch"]])),
                "not_certified_does_not_mean_failed": True,
                "max_inactive_preactivation_increase": float(a["inactive_preactivation_increase"].max()),
                "feature_surrogates": features}
            offset = 0
            for row, _, _, _, _ in selected:
                for i in range(len(row["result"]["token_ids"])):
                    index = offset + i
                    positions.append({"text_id": row["text_id"], "split": split, "corpus": row["corpus"],
                                      "position": i, "nonspecial": bool(ns[index]), "mode": mode,
                                      "active_coordinates": int((z[index] > 0).sum()),
                                      "continuous_norm_fraction": float(rho[index]),
                                      "projection_scale": float(a["scale"][index]),
                                      "window_dispatch": bool(window["dispatch"][index]),
                                      "conditional_rounding_fidelity_certificate": bool(nz[index] and numerical_certificate[index])})
                offset += len(row["result"]["token_ids"])
        onset = np.maximum(-p, 0)/np.sqrt(np.diag(gram))
        results[split] = {"texts": len(selected), "all_positions": len(h), "nonspecial_positions": int(ns.sum()),
                          "positive_native_positions": (z[ns] > 0).sum(axis=0).tolist(),
                          "native_vs_promoted_activity_mismatches": ((z[ns] > 0) != (p[ns] > 0)).sum(axis=0).tolist(),
                          "inactive_onset_alone_above_five_percent": ((z[ns] == 0) & (onset[ns] > .05*h[ns, None])).sum(axis=0).tolist(),
                          "old_amplification_relaxed_inequalities": qresults,
                          "active_support_075_cap004": prototypes}
    summary = {"schema": "sae_assay_offline_feasibility_v1", "scope": SCOPE,
               "source_freeze": manifest["freeze_commit"], "feature_ids": ids,
               "source_release_manifest_sha256": hashlib.sha256((run / "RELEASE_MANIFEST.json").read_bytes()).hexdigest(),
               "hypothesis_development_only": True, "fresh_validation_available": False,
               "qualification_status": "NOT_TESTED_NO_NATIVE_FORWARD_OR_LANGUAGE_CONTROL",
               "rounding_assumptions": "Finite normal round-to-nearest BF16 of exact h+r; no overflow/subnormal or prior arithmetic error; native re-encoding not covered.",
               "prototype_parameters": {"change": .75, "continuous_norm_cap": .04, "worst_case_native_norm_fraction_bound": .0440625,
                                        "optional_window_minimum_norm_fraction": .02,
                                        "new_estimand": "multiplicative change only in naturally active coordinates; not all-token q90 activation"},
               "splits": results}
    verify_manifest(run)
    out.mkdir(parents=True, exist_ok=False)
    (out / "SUMMARY.json").write_text(canonical(summary))
    for name, table in (("necessary_bounds.csv", bounds_table), ("prototype_coordinates.csv", proposal_table),
                        ("prototype_positions.csv", positions)):
        with (out / name).open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(table[0]))
            writer.writeheader()
            writer.writerows(table)
    source_paths = ["rows/qualification-live.json", "target-q90.json"] + ["rows/"+r[0]["id"]+".json" for r in clean]
    (out / "INPUTS.json").write_text(canonical({p: hashlib.sha256((run / p).read_bytes()).hexdigest() for p in source_paths}))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(args.run, args.out)
    print(canonical({"qualification_status": result["qualification_status"], "scope": result["scope"]}))
