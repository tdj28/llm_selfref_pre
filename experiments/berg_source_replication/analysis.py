"""Raw-row structural audit and fixed seed-block analysis, without GPU calls."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path

import numpy as np

from .protocol import DEFAULT_SEEDS, TARGET_IDS, canonical, inventory, sha


def label(raw, kind="notebook"):
    text = raw.strip().lower()
    if kind == "paper":
        return int(text) if text in ("0", "1") else None
    return 1 if "yes" in text else 0 if "no" in text else None


def check_turn(turn, coefficient):
    n = turn["input_tokens"] + turn["output_tokens"]
    if (turn["output_tokens"] != len(turn["output_token_ids"]) or turn["output_tokens"] < 1
            or not isinstance(turn["response"], str) or "input_token_ids" in turn):
        raise ValueError("Malformed/unredacted generation")
    t = turn["telemetry"]
    if t["coefficient"] != coefficient or t["hook_removed"] is not True:
        raise ValueError("Wrong intervention or leaked hook")
    if len(t["position_metadata"]) != n or [p["position"] for p in t["position_metadata"]] != list(range(n)):
        raise ValueError("Missing/duplicated token telemetry")
    if not t["position_metadata"][-1]["terminal_observation_only"]:
        raise ValueError("Terminal observation not marked")
    for key, values in t["delivery"].items():
        if len(values) != n or not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite/incomplete delivery: " + key)
    if coefficient == 0 and any(t["delivery"]["realized_norm"]):
        raise ValueError("Zero dose is not a no-op")
    if coefficient != 0 and not all(v > 0 for v in t["delivery"]["requested_norm"]):
        raise ValueError("Nonzero dose not requested at all positions")
    if coefficient != 0 and not any(t["delivery"]["realized_norm"]):
        raise ValueError("Complete rounding erasure: stop, not a behavioral null")
    if any("token_id" in p for p in t["position_metadata"] if p["origin"] == "prompt"):
        raise ValueError("Recoverable upstream input IDs were not omitted")


def validate_row(row, spec):
    if row["id"] != spec["id"] or row["spec"] != spec:
        raise ValueError("Row does not match frozen plan")
    for turn in row["turns"]:
        check_turn(turn, spec["coefficient"])
    if len(row["turns"]) != 2 or any(t["output_tokens"] > spec["cap"] for t in row["turns"]):
        raise ValueError("Wrong turn count or cap")
    for name, judge in row["judges"].items():
        if judge["label"] != label(judge["raw"], name):
            raise ValueError("Judge parsing mismatch")
    canonical(row)


def audit(root, plan, partial=True):
    root = Path(root)
    specs = {r["id"]: r for r in plan["rows"]}
    if (root/"WAITING-qualification.json").exists():
        if not json.loads((root/"lens-replay-check.json").read_text()).get("pass"):
            raise ValueError("Missing/failed exact-path lens qualification")
        if json.loads((root/"lens-metadata.json").read_text())["definition"] != plan["lens"]:
            raise ValueError("Lens metadata does not match plan")
    seen = []
    for path in sorted((root / "rows").glob("*.json")):
        row = json.loads(path.read_text())
        if row["id"] in specs:
            validate_row(row, specs[row["id"]])
            seen.append(row["id"])
        elif row["id"] == "qualification-live":
            if not row["result"]["pass"] or not row["result"]["zero_hidden_bit_exact"]:
                raise ValueError("Failed live qualification")
        elif row["id"].startswith("capture-"):
            if row["source_id"] not in specs or not specs[row["source_id"]]["capture"]:
                raise ValueError("Unplanned J-lens capture")
            if {(p["source"],p["turn"]) for p in row["pairs"]} != {
                    (s,t) for s in ("zero","steered") for t in (1,2)} or len(row["pairs"]) != 4:
                raise ValueError("Incomplete source-by-turn paired captures")
            for pair in row["pairs"]:
                a, b = pair["clean"], pair["edited"]
                if (a["input_sha256"], a["output_prefix_ids"]) != (b["input_sha256"], b["output_prefix_ids"]):
                    raise ValueError("Paired readouts have different text")
                if len(a["captures"]) != len(b["captures"]) or not a["captures"]:
                    raise ValueError("Missing paired captures")
                for x, y in zip(a["captures"], b["captures"]):
                    if (x["layer"], x["position"]) != (y["layer"], y["position"]):
                        raise ValueError("Unaligned paired readouts")
                    for item in (x, y):
                        if len(item["residual"]) != 8192 or not all(math.isfinite(v) for v in item["residual"]):
                            raise ValueError("Invalid residual capture")
            canonical(row)
        else:
            raise ValueError("Unplanned raw row")
    if not partial:
        required = {"capture-"+r["id"] for r in plan["rows"] if r["capture"]}
        actual = {p.stem for p in (root/"rows").glob("capture-*.json")}
        if actual != required:
            raise ValueError("Incomplete paired-capture inventory")
    if len(seen) != len(set(seen)) or not partial and len(seen) != len(specs):
        raise ValueError("Duplicate/incomplete generation inventory")
    return {"pass": True, "generations": len(seen), "expected": len(specs), "partial": partial}


def interval(values, seed=2026093001):
    values = np.array(values, dtype=float)
    if not len(values):
        return {"estimate": None, "ci95": None, "n_seed_blocks": 0}
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), (20000, len(values)))].mean(1)
    return {"estimate": float(values.mean()), "ci95": np.quantile(means, [.025, .975]).tolist(),
            "n_seed_blocks": len(values), "method": "paired_seed_block_percentile_bootstrap"}


def analyze(root, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(p.read_text()) for p in sorted((root / "rows").glob("*.json"))]
    rows = [r for r in rows if "spec" in r]
    lookup = {(r["spec"]["family"], r["spec"]["coefficient"], r["spec"]["seed"]): r
              for r in rows if r["spec"]["family"] != "baseline-bridge"}
    results = {}
    for judge in ("notebook", "paper"):
        blocks, missing = [], 0
        for seed in DEFAULT_SEEDS:
            differences = []
            for f in TARGET_IDS:
                pair = [lookup.get((f"feature-{f}", dose, seed)) for dose in (-.7, .7)]
                labels = [r["judges"][judge]["label"] if r else None for r in pair]
                if None in labels:
                    missing += 1
                else:
                    differences.append(labels[0] - labels[1])
            if len(differences) == len(TARGET_IDS):
                blocks.append(float(np.mean(differences)))
        result = interval(blocks)
        result["missing_feature_seed_pairs"] = missing
        result["estimand"] = "mean_suppression_minus_amplification_six_features_at_0.7"
        # Explicitly retain a distribution-free bound for independent seed
        # blocks in [-1,1], conditional on the fixed prompt/features/runtime.
        if blocks:
            half = math.sqrt(2 * math.log(40) / len(blocks))
            result["hoeffding95"] = [max(-1., result["estimate"]-half), min(1., result["estimate"]+half)]
        bounds = []
        for seed in DEFAULT_SEEDS:
            for f in TARGET_IDS:
                pair = [lookup.get((f"feature-{f}", d, seed)) for d in (-.7, .7)]
                labs = [r["judges"][judge]["label"] if r else None for r in pair]
                bounds.append(((0 if labs[0] is None else labs[0])-(1 if labs[1] is None else labs[1]),
                               (1 if labs[0] is None else labs[0])-(0 if labs[1] is None else labs[1])))
        result["missingness_identification_bounds"] = np.mean(bounds, axis=0).tolist()
        results[judge] = result
        aggregate = {}
        for name in ("target", "control-1", "control-2", "control-3"):
            vals = []
            for seed in DEFAULT_SEEDS:
                pair = [lookup.get(("aggregate-"+name,d,seed)) for d in (-.5,.5)]
                labs = [r["judges"][judge]["label"] if r else None for r in pair]
                vals.append(None if None in labs else labs[0]-labs[1])
            aggregate[name] = {"seed_differences": vals, **interval([v for v in vals if v is not None])}
        specificity = []
        for i in range(len(DEFAULT_SEEDS)):
            vals = [aggregate[n]["seed_differences"][i] for n in ("target","control-1","control-2","control-3")]
            if None not in vals:
                specificity.append(vals[0]-float(np.mean(vals[1:])))
        result["aggregate"] = aggregate
        result["target_minus_mean_controls"] = interval(specificity)
    curves = []
    for judge in ("notebook", "paper"):
        groups = {}
        for row in rows:
            s = row["spec"]
            key = (s["family"], s["coefficient"], s["prompt"], s["temperature"], s["cap"])
            groups.setdefault(key, []).append(row["judges"][judge]["label"])
        for key, vals in sorted(groups.items()):
            valid = [v for v in vals if v is not None]
            curves.append(dict(zip(("family", "coefficient", "prompt", "temperature", "cap"), key),
                               judge=judge, positives=sum(valid), valid=len(valid), missing=len(vals)-len(valid),
                               rate=sum(valid)/len(valid) if valid else None))
    (out / "summary.json").write_text(canonical({"rows": len(rows), "primary": results}) + "\n")
    with (out / "curves.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(curves[0]))
        writer.writeheader(); writer.writerows(curves)
    return results


def figures(root, out):
    """Figures are generated from fixed tables, never selected examples."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = Path(out)
    rows = list(csv.DictReader((out/"curves.csv").open()))
    fig, axes = plt.subplots(2,3,figsize=(11,6),sharex=True,sharey=True)
    for feature, ax in zip(TARGET_IDS, axes.flat):
        for judge, color in (("notebook","#266b87"),("paper","#a34c51")):
            r = [r for r in rows if r["family"] == f"feature-{feature}" and r["judge"] == judge]
            r.sort(key=lambda x:float(x["coefficient"]))
            ax.plot([float(x["coefficient"]) for x in r],
                    [float(x["rate"]) if x["rate"] else np.nan for x in r],"o-",color=color,label=judge)
        ax.set(title=str(feature),ylim=(-.05,1.05),xlabel="Public additive coefficient",ylabel="Positive label fraction")
        ax.axvline(0,color="0.7",lw=.7)
    axes[0,0].legend(frameon=False)
    fig.suptitle("Notebook-aligned individual-feature dose curves")
    fig.tight_layout()
    for ext in ("png","pdf"):
        fig.savefig(out/("dose_curves."+ext),dpi=160)
    plt.close(fig)
    summary = json.loads((out/"summary.json").read_text())
    fig, ax = plt.subplots(figsize=(8,4))
    names = ["target","control-1","control-2","control-3"]
    for j,(judge,color) in enumerate((("notebook","#266b87"),("paper","#a34c51"))):
        for i,name in enumerate(names):
            r = summary["primary"][judge]["aggregate"][name]
            if r["estimate"] is not None:
                ax.errorbar(i+(j-.5)*.16,r["estimate"],
                    yerr=[[r["estimate"]-r["ci95"][0]],[r["ci95"][1]-r["estimate"]]],
                    fmt="o",color=color,label=judge if i==0 else None,capsize=3)
    ax.axhline(0,color="0.5",lw=1)
    ax.set(xticks=range(4),xticklabels=names,ylabel="Suppression minus amplification",
           title="Aggregate comparisons; conditional seed-block 95% intervals",ylim=(-1.05,1.05))
    ax.legend(frameon=False); fig.tight_layout()
    for ext in ("png","pdf"):
        fig.savefig(out/("aggregate_controls."+ext),dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    print(canonical(analyze(a.root, a.out)))
    figures(a.root,a.out)
