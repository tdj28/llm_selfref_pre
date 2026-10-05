"""Offline prospective simulation, never model inference or experimental data.

Run ``python -m experiments.berg_dose_ladder.power --out PLAN_DIR/POWER.json``.
Only this CLI writes, exclusively to the requested new file. Imports and
``build_report`` do not write. No calibration outcomes or eligibility gates
are simulated: these are fixed-N inference operating characteristics only.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import scipy

from .inference import cp_limits, discordance_counts

MIN_REPETITIONS = 20000
DEFAULT_SEED = 2026100401
ALPHA = .025
TARGET_N, PANEL_N = 96, 32
OBSERVED_PAIRS = tuple(itertools.product((0, 1, None), repeat=2))
COUNT_FIELDS = ("positive_definite", "positive_possible", "negative_definite", "negative_possible")
COUNT_MATRIX = np.array([[discordance_counts([a], [b])[key] for key in COUNT_FIELDS]
                         for a, b in OBSERVED_PAIRS], dtype=np.int64)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _validate_repetitions(repetitions, seed):
    if type(repetitions) is not int or repetitions < MIN_REPETITIONS:
        raise ValueError("At least 20000 simulation repetitions are required")
    if type(seed) is not int or seed < 0:
        raise ValueError("Simulation seed must be a nonnegative integer")


def cp_tables():
    """Precompute all counts, once, rather than beta inversions per replicate."""
    return {(n, tail): np.asarray([cp_limits(k, n, tail) for k in range(n+1)])
            for n, tail in ((TARGET_N, ALPHA/2), (TARGET_N, ALPHA/8), (PANEL_N, ALPHA/8))}


def observed_pair_probabilities(mean, discordance, missing_probability):
    """Independent per-label MCAR masks on a declared four-cell pair law.

    Concordant pairs split equally between 00 and 11. Thus arm marginals are
    (1+mean)/2 and (1-mean)/2; untreated baseline is not used to fix covariance.
    Worst-case inference does not require the simulation's MCAR assumption.
    """
    if (not all(np.isfinite(v) for v in (mean, discordance, missing_probability))
            or not abs(mean) <= discordance <= 1 or not 0 <= missing_probability <= 1):
        raise ValueError("Infeasible mean/discordance or missing probability")
    complete = {(1, 0): (discordance+mean)/2, (0, 1): (discordance-mean)/2,
                (0, 0): (1-discordance)/2, (1, 1): (1-discordance)/2}
    observed = dict.fromkeys(OBSERVED_PAIRS, 0.)
    for (a, b), probability in complete.items():
        for missing_a, missing_b in itertools.product((False, True), repeat=2):
            weight = probability
            for missing in (missing_a, missing_b):
                weight *= missing_probability if missing else 1-missing_probability
            observed[(None if missing_a else a, None if missing_b else b)] += weight
    return np.asarray([observed[pair] for pair in OBSERVED_PAIRS], dtype=float)


def vectorized_bounds(counts, table):
    """Same definite/possible rule as inference.py, for multinomial draws."""
    events = counts @ COUNT_MATRIX
    lower = table[events[:, 0], 0]-table[events[:, 3], 1]
    upper = table[events[:, 1], 1]-table[events[:, 2], 0]
    return lower, upper


def scenario_inventory():
    scenarios = []
    for mean in (0., .3, .8):
        target_qs = (.2, .5, 1.) if mean != .8 else (.2, .5, .8, .9, 1.)
        for target_q, control_q, missing, profile in itertools.product(
                target_qs, (.2, .5, 1.), (0., .05), ("homogeneous", "heterogeneous")):
            control_means = [0., 0., 0.] if profile == "homogeneous" else [-control_q/2, 0., control_q/2]
            scenarios.append({"id": f"mu{mean:g}-qt{target_q:g}-qc{control_q:g}-m{missing:g}-{profile}",
                "target_mean": mean, "target_discordance": target_q,
                "control_means": control_means, "control_discordances": [control_q]*3,
                "missing_probability_per_label": missing, "panel_profile": profile})
    for missing in (0., .05):
        scenarios.append({"id": f"shared-source-effect-m{missing:g}",
            "target_mean": .8, "target_discordance": 1.,
            "control_means": [.8]*3, "control_discordances": [1.]*3,
            "missing_probability_per_label": missing, "panel_profile": "shared_source_effect"})
    return scenarios


def _event_summary(event):
    count, n = int(np.count_nonzero(event)), int(event.size)
    lower, upper = cp_limits(count, n, .025)
    return {"count": count, "repetitions": n, "rate": count/n,
            "monte_carlo_95": [lower, upper]}


def _interval_summary(lower, upper):
    return {"lower_quantiles_05_50_95": np.quantile(lower, [.05, .5, .95]).tolist(),
            "upper_quantiles_05_50_95": np.quantile(upper, [.05, .5, .95]).tolist(),
            "median_width": float(np.median(upper-lower))}


def simulate_scenario(scenario, repetitions=MIN_REPETITIONS, seed=DEFAULT_SEED, tables=None):
    _validate_repetitions(repetitions, seed)
    tables = cp_tables() if tables is None else tables
    if len(scenario["control_means"]) != 3 or len(scenario["control_discordances"]) != 3:
        raise ValueError("Exactly three fixed panel distributions are required")
    missing = scenario["missing_probability_per_label"]
    probabilities = [observed_pair_probabilities(scenario["target_mean"],
                     scenario["target_discordance"], missing)]
    probabilities += [observed_pair_probabilities(mean, q, missing)
                      for mean, q in zip(scenario["control_means"], scenario["control_discordances"])]
    rng = np.random.default_rng(seed)
    target = rng.multinomial(TARGET_N, probabilities[0], size=repetitions)
    d_lower, d_upper = vectorized_bounds(target, tables[(TARGET_N, ALPHA/2)])
    s_lower, s_upper = vectorized_bounds(target, tables[(TARGET_N, ALPHA/8)])
    for probability in probabilities[1:]:
        controls = rng.multinomial(PANEL_N, probability, size=repetitions)
        lower, upper = vectorized_bounds(controls, tables[(PANEL_N, ALPHA/8)])
        s_lower -= upper/3
        s_upper -= lower/3
    mean = float(scenario["target_mean"])
    specificity = mean-sum(scenario["control_means"])/3
    positive = (d_lower >= .3) & (s_lower > 0)
    exclusion = d_upper < .3
    positive_null = mean <= .3 or specificity <= 0
    exclusion_null = mean >= .3
    return {"scenario": scenario, "status": "simulated", "seed": seed,
            "repetitions": repetitions, "true_target_gap": mean,
            "true_specificity": specificity,
            "decisions": {"large_specific": _event_summary(positive),
                          "exclude_target_gap_0.30": _event_summary(exclusion),
                          "inconclusive": _event_summary(~(positive | exclusion)),
                          "positive_null_rejection": _event_summary(positive & positive_null),
                          "exclusion_null_rejection": _event_summary(exclusion & exclusion_null),
                          "either_directional_error": _event_summary(
                              (positive & positive_null) | (exclusion & exclusion_null))},
            "coverage": {"target_individual_two_sided": _event_summary(
                             (d_lower <= mean) & (mean <= d_upper)),
                         "specificity_individual_two_sided": _event_summary(
                             (s_lower <= specificity) & (specificity <= s_upper))},
            "target_bounds": _interval_summary(d_lower, d_upper),
            "specificity_bounds": _interval_summary(s_lower, s_upper)}


def build_report(repetitions=MIN_REPETITIONS, seed=DEFAULT_SEED):
    _validate_repetitions(repetitions, seed)
    tables, results = cp_tables(), []
    for index, scenario in enumerate(scenario_inventory()):
        if abs(scenario["target_mean"]) > scenario["target_discordance"]:
            results.append({"scenario": scenario, "status": "infeasible_not_simulated",
                            "reason": "abs(mean difference) exceeds discordance probability"})
        else:
            results.append(simulate_scenario(scenario, repetitions, seed+index, tables))
    sources = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
               for name in ("inference.py", "power.py")}
    report = {"schema": "dose_ladder_prospective_power_v1", "prospective_simulation": True,
              "experiment_results": False, "experimental_rows_read": [],
              "eligibility_gates_simulated": False,
              "execution_authorization": False, "seed": seed, "repetitions_per_scenario": repetitions,
              "target_blocks": TARGET_N, "control_blocks_per_fixed_panel": [PANEL_N]*3,
              "calibration_trials": 204, "confirmation_trials": 480,
              "directional_alpha": ALPHA, "target_component_tail": ALPHA/2,
              "specificity_component_tail": ALPHA/8,
              "positive_rule": "L_D >= 0.30 AND L_S > 0 (intersection-union, alpha=0.025)",
              "exclusion_rule": "U_D < 0.30 (alpha=0.025)",
              "family_error_bound": .05, "joint_D_S_95_intervals": False,
              "assumptions": ["independent identically distributed seed blocks within each fixed stratum",
                  "target distribution does not depend on control-panel assignment",
                  "target and control sign-pairs independent in these simulation scenarios",
                  "sign-pair dependence set by declared discordance; concordant 00/11 equally likely",
                  "missingness independent per label (MCAR) in simulation; bounds remain worst-case",
                  "assumes a dose is selected; calibration, delivery and coherence gate probabilities not modeled",
                  "not unconditional study success power or a conditional-distribution analysis after main quality gating",
                  "no prompt, feature-population, natural-scale, or semantic-ablation generalization"],
              "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
              "source_sha256": sources, "scenarios": results}
    report["report_sha256"] = hashlib.sha256(_canonical(report).encode()).hexdigest()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="New prospective JSON report file")
    parser.add_argument("--repetitions", "--reps", type=int, default=MIN_REPETITIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    _validate_repetitions(args.repetitions, args.seed)
    if args.out.exists():
        raise FileExistsError("Refusing to overwrite prospective power report")
    report = build_report(args.repetitions, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        handle.write(_canonical(report)+"\n")
    print(_canonical({"out": str(args.out), "report_sha256": report["report_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
