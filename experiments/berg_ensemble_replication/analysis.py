"""Fixed-panel inference; exact marginal bounds do not assume arm independence."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.stats import beta

from experiments.berg_source_replication.analysis import check_turn, label
from .protocol import SEEDS, canonical

FAMILIES = ("target", "control-1", "control-2", "control-3")


def validate_row(row, spec):
    if row["id"] != spec["id"] or row["spec"] != spec or len(row["turns"]) != 2:
        raise ValueError("Row does not match frozen plan")
    for t in row["turns"]:
        check_turn(t, spec["coefficient"])
        if (t["output_tokens"] > spec["cap"] or t["telemetry"].get("weights") != spec["weights"]
                or t["telemetry"]["feature_ids"] != spec["feature_ids"]):
            raise ValueError("Wrong weighted intervention/cap")
    if set(row["judges"]) != {"notebook", "paper"}:
        raise ValueError("Missing planned judge")
    for name, judge in row["judges"].items():
        if judge["label"] != label(judge["raw"], name):
            raise ValueError("Judge parsing mismatch")
    canonical(row)


def audit(root, plan, partial=True):
    root = Path(root)
    specs, seen = {r["id"]: r for r in plan["rows"]}, set()
    for path in (root/"rows").glob("*.json"):
        row = json.loads(path.read_text())
        if row["id"] == "qualification-live":
            if not row["result"]["pass"] or not row["result"]["zero_hidden_bit_exact"]:
                raise ValueError("Live zero qualification failed")
        else:
            if row["id"] not in specs or row["id"] in seen:
                raise ValueError("Unexpected/duplicate row")
            validate_row(row, specs[row["id"]])
            seen.add(row["id"])
    if not partial and seen != set(specs):
        raise ValueError("Incomplete inventory")
    return {"pass": True, "generations": len(seen), "expected": len(specs), "partial": partial}


def marginal(labels, tail):
    n, k, missing = len(labels), sum(v == 1 for v in labels), sum(v is None for v in labels)
    lower = 0. if k == 0 else float(beta.ppf(tail, k, n-k+1))
    upper = 1. if k+missing == n else float(beta.ppf(1-tail, k+missing+1, n-k-missing))
    return {"n_planned": n, "positive": k, "missing": missing,
            "rate": k/(n-missing) if n > missing else None, "bounds": [lower, upper]}


def contrast(a, b, tail=.0125):
    ma, mb = marginal(a, tail), marginal(b, tail)
    valid = [x-y for x,y in zip(a,b) if x is not None and y is not None]
    rng = np.random.default_rng(2026100101)
    ci = None
    if valid:
        v = np.array(valid)
        ci = np.quantile(v[rng.integers(0,len(v),(20000,len(v)))].mean(1), [.025,.975]).tolist()
    return {"suppression": ma, "amplification": mb,
        "estimate_complete_pairs": float(np.mean(valid)) if valid else None,
        "complete_pairs": len(valid), "bootstrap95": ci,
        "exact_marginal95": [ma["bounds"][0]-mb["bounds"][1], ma["bounds"][1]-mb["bounds"][0]],
        "missingness_bounds": [float(np.mean([(0 if x is None else x)-(1 if y is None else y) for x,y in zip(a,b)])),
                               float(np.mean([(1 if x is None else x)-(0 if y is None else y) for x,y in zip(a,b)]))]}


def analyze(root, out):
    root, out = Path(root), Path(out)
    rows = [json.loads(p.read_text()) for p in (root/"rows").glob("*.json")]
    lookup = {(r["spec"]["family"], r["spec"]["coefficient"], r["spec"]["seed"]): r
              for r in rows if "spec" in r}
    results, table = {}, []
    for judge in ("paper", "notebook"):
        def labels(family, sign):
            return [lookup.get((family,sign,seed), {}).get("judges", {}).get(judge, {}).get("label") for seed in SEEDS]
        result = {f: contrast(labels(f,-1), labels(f,1)) for f in FAMILIES}
        bands = {f: contrast(labels(f,-1),labels(f,1),tail=.05/16)["exact_marginal95"] for f in FAMILIES}
        specificity = []
        for i in range(len(SEEDS)):
            values = [labels(f,s)[i] for f in FAMILIES for s in (-1,1)]
            if None not in values:
                diffs = [values[j]-values[j+1] for j in (0,2,4,6)]
                specificity.append(diffs[0]-sum(diffs[1:])/3)
        result["specificity"] = {"estimate_complete_blocks": float(np.mean(specificity)) if specificity else None,
            "complete_blocks": len(specificity),
            "simultaneous95": [bands["target"][0]-sum(bands[f][1] for f in FAMILIES[1:])/3,
                               bands["target"][1]-sum(bands[f][0] for f in FAMILIES[1:])/3]}
        result["zero"] = marginal(labels("zero",0),.025)
        low, high = result["target"]["exact_marginal95"]
        result["large_signature_verdict"] = ("large_positive_signature" if low >= .30 else
                "large_signature_not_recovered_under_public_operator" if high < .30 else "inconclusive")
        results[judge] = result
        for f in FAMILIES + ("zero",):
            for sign in ((0,) if f == "zero" else (-1,1)):
                m = marginal(labels(f,sign),.025)
                table.append({"judge": judge,"family": f,"sign": sign,**{k:v for k,v in m.items() if k != "bounds"}})
    out.mkdir(parents=True,exist_ok=True)
    (out/"summary.json").write_text(canonical({"primary_judge":"paper","results":results})+"\n")
    with (out/"rates.csv").open("w") as f:
        w = csv.DictWriter(f,fieldnames=list(table[0])); w.writeheader(); w.writerows(table)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root",required=True); p.add_argument("--out",required=True)
    a = p.parse_args(); print(canonical(analyze(a.root,a.out)))
