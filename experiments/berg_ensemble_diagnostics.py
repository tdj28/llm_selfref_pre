"""Offline reporting for the fixed random-subset study; no outcome selection."""
import argparse
import json
from pathlib import Path

import numpy as np

from experiments.berg_source_diagnostics import activation_rows, delivery_rows, table


def figures(summary, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    families = ("target", "control-1", "control-2", "control-3")
    colors = {"paper":"#236d91", "notebook":"#ae4b48"}
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),sharey=True)
    for ax,judge in zip(axes,("paper","notebook")):
        result = summary[judge]
        for i,family in enumerate(families):
            row = result[family]
            estimate, (low,high) = row["estimate_complete_pairs"],row["exact_marginal95"]
            ax.vlines(i,low,high,color=colors[judge])
            ax.hlines((low,high),i-.06,i+.06,color=colors[judge])
            if estimate is not None: ax.plot(i,estimate,"o",color=colors[judge])
        ax.axhline(0,color="0.5",lw=.8)
        ax.axhline(.30,color="0.5",lw=.8,ls=":")
        ax.set(title=judge.title()+" rubric",xticks=range(4),xticklabels=families,
               ylim=(-1.05,1.05),ylabel="Suppression minus amplification")
        ax.tick_params(axis="x",labelrotation=15)
    fig.suptitle("Random-subset steering: 50 paired blocks")
    fig.text(.5,.01,"Points: complete pairs. Lines: conservative planned-denominator 95% bounds. Dotted: 0.30.",ha="center",fontsize=9)
    fig.tight_layout(rect=(0,.03,1,1))
    for ext in ("png","pdf"): fig.savefig(Path(out)/("aggregate_effects."+ext),dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),sharey=True)
    for ax,judge in zip(axes,("paper","notebook")):
        result = summary[judge]
        for offset,arm,color in ((-.18,"suppression","#236d91"),(.18,"amplification","#ae4b48")):
            values = [result[f][arm]["rate"] for f in families]
            ax.bar(np.arange(4)+offset,[np.nan if v is None else v for v in values],width=.34,label=arm,color=color)
        zero = result["zero"]["rate"]
        if zero is not None: ax.axhline(zero,color="#397454",ls="--",label="true zero")
        ax.set(title=judge.title()+" rubric",xticks=range(4),xticklabels=families,
               ylim=(0,1.05),ylabel="Positive label fraction among valid outputs")
        ax.tick_params(axis="x",labelrotation=15)
    axes[0].legend(frameon=False,fontsize=9)
    fig.suptitle("All target and matched-panel report rates")
    fig.tight_layout()
    for ext in ("png","pdf"): fig.savefig(Path(out)/("aggregate_rates."+ext),dpi=160)
    plt.close(fig)


def summarize(root,out,plan_path):
    from experiments.berg_ensemble_replication import analysis, protocol
    root, out = Path(root),Path(out)
    if out.exists(): raise FileExistsError(out)
    plan = protocol.load_plan(plan_path)
    audit = analysis.audit(root,plan,partial=False)
    out.mkdir(parents=True)
    results = analysis.analyze(root,out/"behavior")
    original = json.loads((root/"analysis/summary.json").read_text())["results"]
    if results != original: raise ValueError("Frozen aggregate analysis does not reproduce")
    delivery, activations, cases = [],[],[]
    quality = {"empty_turns":0,"capped_turns":0,"generated_tokens":0,"judge_missing":{"paper":0,"notebook":0}}
    for spec in plan["rows"]:
        row = json.loads((root/"rows"/(spec["id"]+".json")).read_text())
        delivery.extend(delivery_rows(row))
        local_activations = list(activation_rows(row))
        for a in local_activations:
            a["feature_weight"] = spec["weights"][spec["feature_ids"].index(a["feature_id"])]
            activations.append(a)
        for turn,t in enumerate(row["turns"],1):
            quality["empty_turns"] += not bool(t["response"].strip())
            quality["capped_turns"] += t["cap_hit"]
            quality["generated_tokens"] += t["output_tokens"]
            for phase in ("prompt","generated"):
                selected = [a for a in local_activations if a["turn"] == turn and a["phase"] == phase]
                if selected:
                    cases.append({"id":row["id"],"family":spec["family"],"seed":spec["seed"],
                        "sign":spec["coefficient"],"turn":turn,"phase":phase,"features":len(selected),
                        **{key:float(np.mean([a[key] for a in selected])) for key in
                           ("before_mean","after_mean","mean_change","before_active_fraction","after_active_fraction")}})
        for judge in quality["judge_missing"]: quality["judge_missing"][judge] += row["judges"][judge]["label"] is None
    table(out/"delivery.csv",delivery)
    table(out/"feature_reencoding.csv",activations)
    table(out/"case_reencoding.csv",cases)
    report = {"behavioral_rows":len(plan["rows"]),"audit":audit,"quality":quality,
        "primary_reproduced_exactly":True,"token_level_inference":False,
        "activation_summary":"Within-trial feature means; prompt = last prefill only; terminal-only states excluded",
        "coefficient_field":"sign only; actual per-feature weights retained in feature_reencoding.csv"}
    (out/"summary.json").write_text(protocol.canonical(report)+"\n")
    figures(results,out)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",required=True); p.add_argument("--out",required=True); p.add_argument("--plan",required=True)
    a = p.parse_args(); print(json.dumps(summarize(a.root,a.out,a.plan)))
