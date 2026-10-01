#!/usr/bin/env python3
"""POST-HOC B02 sensitivities; standard library, pinned Git inputs, no API calls."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import random
import statistics
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "evidence/uncertainty_sensitivity"
PIN = "f5e906e1737bc71bf20b642af1d698018eec82fe"
SOURCE_URL = "https://github.com/tdj28/llm_selfref_pre"
CAUSAL = "data/causal_transplant/confirmatory_v1_20260709"
SAE = "data/public_sae_consciousness_gating/confirmatory_v1_20260710"
DRAWS = 50_000
MINIMUM = 0.30
RECOMPUTE_ABS_TOL = 1e-12
JUDGES = {
    "openai": "openai:gpt-4o-mini-2024-07-18",
    "anthropic": "anthropic:claude-haiku-4-5-20251001",
}
QUERIES = {"direct_conscious", "direct_experience", "indirect_conscious", "indirect_experience"}
ANCHORS = ("paper_self_ref", "paper_history")
EFFECTS = ("instruction_source_main", "transcript_source_main",
           "instruction_x_transcript_interaction", "instruction_minus_transcript")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def compare_recomputed(actual, expected, path="results"):
    """Allow libm rounding only; structure, counts and archived hashes stay exact."""
    require(type(actual) is type(expected), f"recomputed type mismatch: {path}")
    if isinstance(actual, dict):
        require(actual.keys() == expected.keys(), f"recomputed keys mismatch: {path}")
        return max((compare_recomputed(actual[k], expected[k], f"{path}.{k}")
                    for k in actual), default=0.0)
    if isinstance(actual, list):
        require(len(actual) == len(expected), f"recomputed length mismatch: {path}")
        return max((compare_recomputed(a, e, f"{path}[{i}]")
                    for i, (a, e) in enumerate(zip(actual, expected))), default=0.0)
    if isinstance(actual, float):
        require(math.isfinite(actual) and math.isfinite(expected),
                f"nonfinite recomputation: {path}")
        error = abs(actual-expected)
        require(error <= RECOMPUTE_ABS_TOL,
                f"recomputed value mismatch: {path}: {actual!r} vs {expected!r}")
        return error
    require(actual == expected, f"recomputed value mismatch: {path}")
    return 0.0


def frozen_method():
    freeze_path = DEFAULT_DIR / "method_freeze.json"
    freeze = json.loads(freeze_path.read_bytes())
    document = (ROOT / freeze["documentation"]).read_bytes()
    marker = freeze["marker"].encode()
    require(document.count(marker) == 1, "method freeze marker absent/ambiguous")
    prefix = document.split(marker)[0] + marker
    require(sha256(prefix) == freeze["frozen_prefix_sha256"], "frozen method prefix changed")
    require(freeze["source_commit"] == PIN and freeze["bootstrap_draws"] == DRAWS,
            "method constants changed")
    return freeze


def valid_counts(k, n):
    require(type(k) is int and type(n) is int and n > 0 and 0 <= k <= n,
            "invalid binomial counts")


def binomial_cdf(k, n, p):
    """Small-n binomial CDF; direct tails avoid special-function dependencies."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p == 0:
        return 1.0
    if p == 1:
        return 0.0
    return math.fsum(math.comb(n, j) * p**j * (1-p)**(n-j) for j in range(k+1))


def clopper_pearson(k, n, confidence=0.95):
    valid_counts(k, n)
    require(0 < confidence < 1, "invalid confidence")
    tail = (1-confidence)/2
    # CDF is decreasing in p. Solve P_p(X <= k) = alpha/2 for the upper end.
    def upper(count):
        if count == n:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo+hi)/2
            if binomial_cdf(count, n, mid) > tail:
                lo = mid
            else:
                hi = mid
        return (lo+hi)/2
    return (0.0 if k == 0 else 1-upper(n-k), upper(k))


def wilson(k, n, confidence=0.95):
    valid_counts(k, n)
    require(0 < confidence < 1, "invalid confidence")
    z = statistics.NormalDist().inv_cdf((1+confidence)/2)
    p, denominator = k/n, 1+z*z/n
    center = (p+z*z/(2*n))/denominator
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return max(0.0, center-radius), min(1.0, center+radius)


def newcombe(s, ns, h, nh):
    ls, us = wilson(s, ns)
    lh, uh = wilson(h, nh)
    ps, ph = s/ns, h/nh
    d = ps-ph
    return d, (max(-1.0, d-math.hypot(ps-ls, uh-ph)),
               min(1.0, d+math.hypot(us-ps, ph-lh)))


def paired_exact(counts, confidence=0.95):
    require(set(counts) == {"00", "01", "10", "11"}, "four paired cells required")
    require(all(type(v) is int and v >= 0 for v in counts.values()), "invalid paired counts")
    n = sum(counts.values())
    require(n > 0 and 0 < confidence < 1, "empty pairs/invalid confidence")
    marginal_confidence = 1-(1-confidence)/2
    lp, up = clopper_pearson(counts["10"], n, marginal_confidence)
    ln, un = clopper_pearson(counts["01"], n, marginal_confidence)
    return {"estimate": (counts["10"]-counts["01"])/n,
            "interval": [lp-un, up-ln],
            "p10_interval_97_5": [lp, up], "p01_interval_97_5": [ln, un],
            "method": "conservative simultaneous exact-binomial, not paired score"}


def quantile(sorted_values, q):
    require(bool(sorted_values) and 0 <= q <= 1, "invalid quantile")
    position = (len(sorted_values)-1)*q
    left = int(position)
    right = min(left+1, len(sorted_values)-1)
    return sorted_values[left]+(position-left)*(sorted_values[right]-sorted_values[left])


def stream(namespace):
    seed = int.from_bytes(hashlib.sha256(("20260929:"+namespace).encode()).digest(), "big")
    return random.Random(seed)


def mean_bootstrap(values, namespace, draws=DRAWS):
    require(len(values) > 0 and draws > 1, "empty bootstrap")
    rng = stream(namespace)
    samples = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [quantile(samples, .025), quantile(samples, .975)]


def paired_counts(pairs):
    counts = dict.fromkeys(("00", "01", "10", "11"), 0)
    for s, a in pairs:
        require(s in (0, 1) and a in (0, 1), "nonbinary pair")
        counts[f"{s}{a}"] += 1
    return counts


def seed_sensitivity(pairs, namespace, draws=DRAWS):
    groups = defaultdict(list)
    for row in pairs:
        require(row["suppression"] is not None and row["amplification"] is not None,
                "incomplete seed cluster; investigate without denominator substitution")
        groups[row["seed"]].append((row["suppression"], row["amplification"]))
    require(len(groups) == 10 and all(len(g) == 5 for g in groups.values()),
            "expected ten seed clusters with five pairs each")
    rows = [{"seed": seed, "n_pairs": len(group), "paired_counts": paired_counts(group),
             "mean": statistics.fmean(s-a for s, a in group)} for seed, group in sorted(groups.items())]
    means = [row["mean"] for row in rows]
    estimate = statistics.fmean(means)
    sd = statistics.stdev(means)
    t_radius = 2.2621571627409915*sd/math.sqrt(10)
    h_radius = math.sqrt(2*math.log(40)/10)
    clip = lambda r: [max(-1.0, estimate-r), min(1.0, estimate+r)]
    return {"clusters": rows, "estimate": estimate, "sample_sd": sd,
            "bootstrap_interval": mean_bootstrap(means, namespace, draws),
            "bootstrap_degenerate": sd == 0,
            "t_interval": clip(t_radius) if sd > 0 else None,
            "t_status": "normal-cluster approximation, df=9" if sd > 0 else
                        "unavailable: zero observed variance is not certainty",
            "hoeffding_interval": clip(h_radius), "hoeffding_radius": h_radius}


def contrasts(cells):
    aa, ad, da, dd = cells
    require(all(v in (0, 1) for v in cells), "incomplete/nonbinary transplant block")
    return ((aa+ad-da-dd)/2, (aa+da-ad-dd)/2, aa-ad-da+dd, ad-da)


def fixed_panel_bootstrap(groups, namespace, draws=DRAWS):
    """Every model contributes once with equal weight; resample joint block vectors."""
    require(len(groups) == 4 and all(groups.values()), "four nonempty model groups required")
    models = sorted(groups)
    rng = stream(namespace)
    values = {m: [contrasts(cells) for cells in groups[m]] for m in models}
    observed = [statistics.fmean(statistics.fmean(v[j] for v in values[m]) for m in models)
                for j in range(4)]
    samples = [[] for _ in EFFECTS]
    for _ in range(draws):
        total = [0.0]*4
        for model in models:
            population = values[model]
            selected = rng.choices(population, k=len(population))
            for j in range(4):
                total[j] += math.fsum(v[j] for v in selected)/len(population)/4
        for j in range(4):
            samples[j].append(total[j])
    result = {}
    for j, name in enumerate(EFFECTS):
        samples[j].sort()
        result[name] = {"estimate": observed[j],
                        "interval": [quantile(samples[j], .025), quantile(samples[j], .975)]}
    return result


def unique_index(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[f] for f in fields)
        require(key not in result, f"duplicate join key {fields}: {key}")
        result[key] = row
    return result


def label(value):
    require(value is None or value in (0, 1), "nonbinary label")
    return None if value is None else int(value)


def pair_llama(generations, judgments):
    unique_index(generations, ("trial_id",))
    indexed = unique_index(judgments, ("trial_id",))
    require(set(indexed) == {(r["trial_id"],) for r in generations}, "Llama judgment IDs differ")
    groups = defaultdict(dict)
    for row in generations:
        if row["phase"] not in ("aggregate_literal", "aggregate_calibrated") or row["analysis_role"] != "target":
            continue
        key, sign = (row["phase"].removeprefix("aggregate_"), row["block_id"]), row["sign"]
        require(sign in ("suppression", "amplification") and sign not in groups[key],
                "duplicate/unexpected Llama arm")
        groups[key][sign] = (row["seed"], label(indexed[(row["trial_id"],)]["paper_label"]))
    pairs = []
    for (scale, block), arms in sorted(groups.items()):
        require(set(arms) == {"suppression", "amplification"}, "missing planned Llama arm")
        s, a = arms["suppression"], arms["amplification"]
        require(s[0] == a[0], "paired Llama seeds differ")
        pairs.append({"scale": scale, "block_id": block, "seed": s[0],
                      "suppression": s[1], "amplification": a[1]})
    require(Counter(r["scale"] for r in pairs) == {"literal": 50, "calibrated": 50},
            "unexpected Llama pair design")
    return pairs


def causal_inputs(outcomes, judgments):
    unique_index(outcomes, ("trial_id",))
    calibration, transplant = [], []
    for judge, judge_key in sorted(JUDGES.items()):
        selected = [r for r in judgments if r["task"] == "paper" and r["judge_key"] == judge_key]
        indexed = unique_index(selected, ("trial_id",))
        require(set(indexed).issubset({(r["trial_id"],) for r in outcomes}), "orphan causal labels")
        bins, blocks = defaultdict(list), defaultdict(dict)
        for row in outcomes:
            if row["instruction_cell"] not in ANCHORS:
                continue
            require(row["transcript_cell"] in ANCHORS, "unexpected anchor transcript")
            require(row["phase"] in ("factorial_natural", "transcript_transplant"), "unexpected phase")
            value = label(indexed.get((row["trial_id"],), {}).get("paper_label"))
            model, query = row["model_key"], row["query_id"]
            if row["phase"] == "factorial_natural":
                require(row["instruction_cell"] == row["transcript_cell"], "noncongruent natural row")
                bins[(model, query, row["instruction_cell"])].append(value)
            key = (model, query, row["pair_index"])
            cell = (row["instruction_cell"], row["transcript_cell"])
            require(cell not in blocks[key], "ambiguous causal pairing")
            blocks[key][cell] = value
        require({k[1] for k in bins} == QUERIES and len({k[0] for k in bins}) == 4,
                "unexpected causal model/query panel")
        for (model, query, condition), values in sorted(bins.items()):
            known = [v for v in values if v is not None]
            calibration.append({"judge": judge, "model": model, "query": query,
                                "condition": condition, "n_rows": len(values),
                                "n": len(known), "positive": sum(known)})
        required = [(a, b) for a in ANCHORS for b in ANCHORS]
        for (model, query, pair), cells in sorted(blocks.items()):
            require(set(cells) == set(required), "missing planned transplant cell")
            transplant.append({"judge": judge, "model": model, "query": query,
                               "pair_index": pair, "cells": [cells[key] for key in required]})
    return calibration, transplant


def extract(source_repo):
    sources = []

    def blob(path):
        oid = subprocess.check_output(["git", "-C", str(source_repo), "rev-parse", f"{PIN}:{path}"],
                                      text=True).strip()
        data = subprocess.check_output(["git", "-C", str(source_repo), "cat-file", "blob", oid])
        sources.append({"path": path, "commit": PIN, "git_blob": oid, "sha256": sha256(data),
                        "bytes": len(data), "url": f"{SOURCE_URL}/blob/{PIN}/{path}"})
        return data

    def jsonl(path):
        return [json.loads(line) for line in blob(path).splitlines() if line.strip()]

    def table(path):
        return list(csv.DictReader(io.StringIO(blob(path).decode())))

    pairs = pair_llama(jsonl(f"{SAE}/generations.jsonl"),
                       jsonl(f"{SAE}/judging/local_llama_judgments.jsonl"))
    calibration, transplant = causal_inputs(jsonl(f"{CAUSAL}/outcomes.jsonl"),
                                            jsonl(f"{CAUSAL}/judgments_paper.jsonl"))
    released = {"llama": {}, "causal": {}}
    for scale, filename in (("literal", "aggregate_effects"), ("calibrated", "calibrated_aggregate_effects")):
        rows = table(f"{SAE}/analysis/{filename}.csv")
        targets = [r for r in rows if r["analysis_role"] == "target"]
        require(len(targets) == 1, "ambiguous released target")
        released["llama"][scale] = targets[0]
    for judge in sorted(JUDGES):
        released["causal"][judge] = {
            name: table(f"{CAUSAL}/analysis_{judge}_paper/{name}.csv")
            for name in ("paper_calibration_rates", "paper_calibration_effects", "transplant_effects")}
    # Preserve provenance of pairing/estimand definitions; never execute archive code.
    for path in ("experiments/exp2_sae/analyze_public_sae_consciousness_gating.py",
                 "experiments/exp2_sae/public_sae_consciousness_gating.py",
                 "experiments/causal_transplant/analyze_causal_transplant.py"):
        blob(path)
    return {"source_commit": PIN, "llama_pairs": pairs, "calibration_counts": calibration,
            "transplant_blocks": transplant, "released": released}, sorted(sources, key=lambda r: r["path"])


def one(rows, **criteria):
    matches = [r for r in rows if all(r[k] == v for k, v in criteria.items())]
    require(len(matches) == 1, f"nonunique summary lookup: {criteria}")
    return matches[0]


def original_interval(row, estimate_key="estimate"):
    return {"estimate": float(row[estimate_key]),
            "interval": [float(row["ci_low"]), float(row["ci_high"])]}


def agrees(left, right):
    require(math.isclose(left, right, abs_tol=1e-12), f"raw/released mismatch: {left} != {right}")


def analyze(inputs, draws=DRAWS):
    require(inputs["source_commit"] == PIN, "unexpected source pin")
    result = {"status": "POST-HOC sensitivity; original prospectively Git-frozen results retained",
              "bootstrap_draws": draws, "llama": {}, "calibration": [], "fixed_panel": []}
    for scale in ("literal", "calibrated"):
        pairs = [r for r in inputs["llama_pairs"] if r["scale"] == scale]
        complete = [r for r in pairs if r["suppression"] is not None and r["amplification"] is not None]
        counts = paired_counts((r["suppression"], r["amplification"]) for r in complete)
        exact = paired_exact(counts)
        original = original_interval(inputs["released"]["llama"][scale], "suppression_minus_amplification")
        agrees(exact["estimate"], original["estimate"])
        require(len(complete) == int(inputs["released"]["llama"][scale]["n_complete_blocks"]),
                "released Llama complete count mismatch")
        seeds = seed_sensitivity(pairs, f"llama:{scale}", draws)
        agrees(exact["estimate"], seeds["estimate"])
        intervals = {"released_bootstrap": original["interval"], "paired_exact": exact["interval"],
                     "seed_bootstrap": seeds["bootstrap_interval"], "seed_t": seeds["t_interval"],
                     "seed_hoeffding": seeds["hoeffding_interval"]}
        result["llama"][scale] = {
            "n_pairs": len(complete), "n_incomplete": len(pairs)-len(complete), "paired_counts": counts,
            "suppression_positive": counts["10"]+counts["11"],
            "amplification_positive": counts["01"]+counts["11"],
            "released_bootstrap": original, "paired_exact": exact, "seed_cluster": seeds,
            "upper_below_0_30": {k: v[1] < MINIMUM if v is not None else None for k, v in intervals.items()}}
    bins = defaultdict(dict)
    for row in inputs["calibration_counts"]:
        bins[(row["judge"], row["model"], row["query"])][row["condition"]] = row
    for (judge, model, query), cells in sorted(bins.items()):
        require(set(cells) == set(ANCHORS), "incomplete calibration conditions")
        s, h = (cells[key] for key in ANCHORS)
        estimate, interval = newcombe(s["positive"], s["n"], h["positive"], h["n"])
        released = inputs["released"]["causal"][judge]
        orig = one(released["paper_calibration_effects"], level="model", model_key=model, query_id=query)
        agrees(estimate, float(orig["estimate"]))
        rates = {}
        for condition, row in cells.items():
            rate = row["positive"]/row["n"]
            old = one(released["paper_calibration_rates"], model_key=model, query_id=query,
                      instruction_cell=condition)
            agrees(rate, float(old["positive_rate"]))
            require(row["n"] == int(old["n_labeled"]) and row["n_rows"] == int(old["n_rows"]),
                    "calibration denominators differ")
            rates[condition] = {"positive": row["positive"], "n": row["n"],
                                "missing": row["n_rows"]-row["n"], "rate": rate,
                                "wilson_95": wilson(row["positive"], row["n"]),
                                "clopper_pearson_95": clopper_pearson(row["positive"], row["n"]),
                                "released_wilson": [float(old["ci_low"]), float(old["ci_high"])]}
        result["calibration"].append({"judge": judge, "model": model, "query": query, "rates": rates,
                                      "estimate": estimate, "newcombe_95": interval,
                                      "released_independent_bootstrap": original_interval(orig)})
    groups = defaultdict(lambda: defaultdict(list))
    missing = defaultdict(Counter)
    for row in inputs["transplant_blocks"]:
        key = row["judge"], row["query"]
        if None in row["cells"]:
            missing[key][row["model"]] += 1
        else:
            groups[key][row["model"]].append(row["cells"])
    for (judge, query), panel in sorted(groups.items()):
        boot = fixed_panel_bootstrap(panel, f"transplant:{judge}:{query}", draws)
        released = inputs["released"]["causal"][judge]["transplant_effects"]
        for effect, value in boot.items():
            old = one(released, level="model_equal_hierarchical", query_id=query, effect=effect)
            agrees(value["estimate"], float(old["estimate"]))
            require(sum(map(len, panel.values())) == int(old["n_pairs"]), "transplant pair count differs")
            for model, blocks in panel.items():
                per_model = one(released, level="model", model_key=model, query_id=query, effect=effect)
                agrees(statistics.fmean(contrasts(c)[EFFECTS.index(effect)] for c in blocks),
                       float(per_model["estimate"]))
                require(len(blocks) == int(per_model["n_pairs"]), "model block count differs")
            result["fixed_panel"].append({"judge": judge, "query": query, "effect": effect, **value,
                                          "complete_blocks_by_model": {m: len(b) for m, b in sorted(panel.items())},
                                          "incomplete_blocks_by_model": {m: missing[(judge, query)][m] for m in sorted(panel)},
                                          "released_model_resampling": original_interval(old)})
    return result


def latex_values(results):
    """Small generated bindings; all values come from results.json's calculation."""
    lines = ["% Generated by scripts/uncertainty_sensitivity.py; POST-HOC, not preregistered.",
             "% Four decimals for display only; results.json retains full precision."]

    def macro(name, value):
        lines.append("\\newcommand{\\US"+name+"}{"+str(value)+"}")

    def interval(name, value):
        macro(name, "unavailable" if value is None else f"[{value[0]:.4f}, {value[1]:.4f}]")

    for scale in ("literal", "calibrated"):
        row = results["llama"][scale]
        prefix = scale.title()
        macro(prefix+"N", row["n_pairs"])
        for cell, value in row["paired_counts"].items():
            name = {"00": "ZeroZero", "01": "ZeroOne", "10": "OneZero", "11": "OneOne"}[cell]
            macro(prefix+"Count"+name, value)
        macro(prefix+"Estimate", f"{row['paired_exact']['estimate']:.4f}")
        interval(prefix+"ReleasedCI", row["released_bootstrap"]["interval"])
        interval(prefix+"ExactCI", row["paired_exact"]["interval"])
        interval(prefix+"SeedBootstrapCI", row["seed_cluster"]["bootstrap_interval"])
        interval(prefix+"SeedTCI", row["seed_cluster"]["t_interval"])
        interval(prefix+"HoeffdingCI", row["seed_cluster"]["hoeffding_interval"])
    for row in results["fixed_panel"]:
        if row["query"] != "indirect_experience":
            continue
        effect = {"instruction_source_main": "Instruction", "transcript_source_main": "Transcript",
                  "instruction_minus_transcript": "Difference", "instruction_x_transcript_interaction": "Interaction"}[row["effect"]]
        name = row["judge"].title()+effect
        macro(name+"Estimate", f"{row['estimate']:.4f}")
        interval(name+"FixedCI", row["interval"])
        interval(name+"ModelResamplingCI", row["released_model_resampling"]["interval"])
    # General boundary examples are generated by the same tested functions.
    interval("ZeroOfTwentyExactCI", clopper_pearson(0, 20))
    interval("TwentyOfTwentyExactCI", clopper_pearson(20, 20))
    interval("TwentyVsZeroNewcombeCI", newcombe(20, 20, 0, 20)[1])
    lines.extend(["% Indirect-experience calibration: successes/n, independent Newcombe 95% CI.",
                  "\\newcommand{\\USCalibrationRows}{%"])
    aliases = {"openai:gpt-4o-2024-11-20": "GPT-4o", "openai:gpt-4.1-2025-04-14": "GPT-4.1",
               "anthropic:claude-haiku-4-5-20251001": "Claude Haiku",
               "anthropic:claude-sonnet-4-5-20250929": "Sonnet 4.5"}
    for row in results["calibration"]:
        if row["query"] != "indirect_experience":
            continue
        rates = row["rates"]
        s, h = (rates[key] for key in ANCHORS)
        model = aliases.get(row["model"], row["model"].replace("_", "\\_"))
        lo, hi = row["newcombe_95"]
        judge_name = "OpenAI" if row["judge"] == "openai" else "Anthropic"
        lines.append(f"{judge_name} & {model} & {s['positive']}/{s['n']} & "
                     f"{h['positive']}/{h['n']} & {row['estimate']:.4f} & [{lo:.4f}, {hi:.4f}] \\\\")
    lines.append("}")
    return ("\n".join(lines)+"\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", type=Path, help="re-extract inputs only via pinned Git blobs")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--check", action="store_true", help="read-only hash and numerical verification; no writes")
    args = parser.parse_args()
    freeze = frozen_method()
    if args.source_repo:
        inputs, sources = extract(args.source_repo)
    else:
        manifest = json.loads((args.outdir / "manifest.json").read_bytes())
        data = (args.outdir / "inputs.json").read_bytes()
        require(sha256(data) == manifest["files"]["inputs.json"]["sha256"], "input hash mismatch")
        inputs, sources = json.loads(data), manifest["sources"]
    results = analyze(inputs)
    files = {"inputs.json": json_bytes(inputs), "results.json": json_bytes(results),
             "values.tex": latex_values(results)}
    max_error = 0.0
    if args.check:
        archived = json.loads((args.outdir / "manifest.json").read_bytes())
        for name in files:
            stored = (args.outdir/name).read_bytes()
            require(archived["files"][name] == {"sha256": sha256(stored), "bytes": len(stored)},
                    f"archived hash/length mismatch: {name}")
        stored_results = (args.outdir/"results.json").read_bytes()
        max_error = compare_recomputed(json.loads(files["results.json"]), json.loads(stored_results))
        # Do not replace released floating-point bytes with another platform's.
        files["results.json"] = stored_results
    manifest = {"source_commit": PIN, "method_freeze": freeze, "sources": sources,
                "generator": {"path": "scripts/uncertainty_sensitivity.py",
                              "sha256": sha256(Path(__file__).read_bytes())},
                "recomputation": {"absolute_float_tolerance": RECOMPUTE_ABS_TOL,
                                  "archived_hashes_and_nonfloat_values": "exact",
                                  "latex_values": "byte-identical"},
                "input_policy": "compact public labels/counts only; no response, prompt or judge text",
                "files": {name: {"sha256": sha256(data), "bytes": len(data)} for name, data in files.items()}}
    files["manifest.json"] = json_bytes(manifest)
    if args.check:
        for name, data in files.items():
            require((args.outdir/name).read_bytes() == data, f"reproduction mismatch: {name}")
        print("PASS: frozen method and archived hashes verified; inputs, LaTeX and manifest "
              f"byte-identical; numerical recomputation max absolute error={max_error:.3g}")
    else:
        args.outdir.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (args.outdir/name).write_bytes(data)
        print(f"Wrote POST-HOC sensitivity package: {args.outdir}")
    for scale, row in results["llama"].items():
        print(scale, json.dumps({"counts": row["paired_counts"], "exact": row["paired_exact"]["interval"],
                                "seed_t": row["seed_cluster"]["t_interval"],
                                "seed_hoeffding": row["seed_cluster"]["hoeffding_interval"]}))


if __name__ == "__main__":
    main()
