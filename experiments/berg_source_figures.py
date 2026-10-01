"""Secondary baseline and delivered-coordinate figures for the source study."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from experiments.berg_source_replication.protocol import DEFAULT_SEEDS


def figures(root, secondary, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root, secondary, out = Path(root), Path(secondary), Path(out)
    if out.exists():
        raise FileExistsError(out)
    with (root/"analysis/curves.csv").open() as f:
        curves = list(csv.DictReader(f))
    with (secondary/"activation_changes.csv").open() as f:
        activations = list(csv.DictReader(f))
    out.mkdir(parents=True)
    written = []

    def save(fig, name):
        for ext in ("png", "pdf"):
            path = out/(name+"."+ext)
            fig.savefig(path, dpi=160)
            written.append(str(path))
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    settings = [(prompt, temperature, cap) for prompt in ("notebook", "paper")
                for temperature in (.5, .6) for cap in (128, 256)]
    for ax, judge in zip(axes, ("notebook", "paper")):
        values, labels = [], []
        for prompt, temperature, cap in settings:
            family = "feature-30032" if (prompt, temperature, cap) == ("notebook", .6, 128) else "baseline-bridge"
            cell = [r for r in curves if r["judge"] == judge and r["family"] == family
                    and float(r["coefficient"]) == 0 and r["prompt"] == prompt
                    and float(r["temperature"]) == temperature and int(r["cap"]) == cap]
            if len(cell) != 1 or int(cell[0]["valid"])+int(cell[0]["missing"]) != 10:
                raise ValueError("Incomplete or duplicate baseline cell")
            row = cell[0]
            values.append(float(row["rate"]) if row["rate"] else np.nan)
            labels.append(f"{row['positives']}/{row['valid']}")
        ax.bar(range(8), values, color=["#236d91"]*4+["#ae4b48"]*4)
        for x, value, label in zip(range(8), values, labels):
            ax.text(x, .04 if np.isnan(value) else value+.025, label, ha="center", fontsize=8)
        ax.set(ylim=(0, 1.15), title=judge.title()+" rubric", ylabel="Positive label fraction",
               xticks=range(8), xticklabels=[f"{p}\nT={t}, cap={c}" for p,t,c in settings])
        ax.tick_params(axis="x", labelrotation=60, labelsize=8)
    fig.suptitle("True-zero baseline: induction, temperature and length cap")
    fig.text(.5, .01, "Counts are positive/valid; ten fixed seeds per cell. Repeated zero copies are not pooled.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    save(fig, "baseline_bridge")

    features = (30032, 58667, 22004, 30686, 41533, 23893)
    fig, axes = plt.subplots(2, 6, figsize=(15, 6.5), squeeze=False)
    for col, feature in enumerate(features):
        for row_index, phase in enumerate(("prompt", "generated")):
            ax = axes[row_index, col]
            counts = []
            for sign, color, offset in ((-.7, "#236d91", -.16), (.7, "#ae4b48", .16)):
                selected = [r for r in activations if r["family"] == f"feature-{feature}"
                            and float(r["coefficient"]) == sign and r["turn"] == "2" and r["phase"] == phase]
                expected = set()
                for seed in DEFAULT_SEEDS:
                    identifier = f"feature-{feature}-{seed}-{sign:+.1f}-notebook-0.6-128"
                    source = json.loads((root/"rows"/(identifier+".json")).read_text())
                    if source["id"] != identifier or source["spec"]["feature_ids"] != [feature]:
                        raise ValueError("Wrong endpoint source row")
                    if phase == "prompt" or source["turns"][1]["output_tokens"] > 1:
                        expected.add(identifier)
                if (len({r["id"] for r in selected}) != len(selected)
                        or {r["id"] for r in selected} != expected
                        or any(int(r["feature_id"]) != feature for r in selected)):
                    raise ValueError("Incomplete or mismatched activation cases")
                counts.append(len(selected))
                for index, record in enumerate(sorted(selected, key=lambda r:int(r["seed"]))):
                    x = offset + (index-(len(selected)-1)/2)*.015
                    before, after = float(record["before_mean"]), float(record["after_mean"])
                    ax.plot([x, x+.8], [before, after], color=color, alpha=.35, lw=.7)
                    ax.scatter([x, x+.8], [before, after], color=color, s=10)
            ax.set(xticks=(0,.8), xticklabels=("Before", "After"), title=f"Feature {feature}" if row_index == 0 else "")
            ax.set_ylim(bottom=0)
            ax.text(.98,.98,f"n={counts[0]}/{counts[1]}",transform=ax.transAxes,
                    ha="right",va="top",fontsize=8)
            if col == 0: ax.set_ylabel("Last prompt" if phase == "prompt" else "Generated mean")
    fig.suptitle("Native SAE re-encoding: single-feature endpoints, second turn")
    fig.text(.5,.01,"Blue: -0.7; red: +0.7. Lines connect before/after within each seed and trajectory. "
             "n = blue/red cases; absent generated means are terminal-only. No population intervals.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1))
    save(fig,"native_reencoding")
    return written


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True); p.add_argument("--secondary", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(); print("\n".join(figures(a.root,a.secondary,a.out)))
