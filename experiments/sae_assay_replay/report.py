"""Rebuild descriptive tables and figures without changing raw replay files."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .analysis import audit
from .protocol import load_plan


def tables(result, ids, raw_rows):
    if not result["pass"] or not result["complete"]:
        raise ValueError("A complete, structurally valid replay is required")
    features, delivery = [], []
    for split, group in result["summary"]["splits"].items():
        for mode in ("suppression", "amplification"):
            arm = group["modes"][mode]
            for feature in ids:
                f = arm["features"][str(feature)]
                features.append({"historical_split": split, "mode": mode,
                                 "feature_id": feature, "positions": f["exposure"]["positions"],
                                 "texts": f["exposure"]["texts"], "exposure_pass": f["exposure"]["pass"],
                                 "native_median": f["native"]["median"], "native_pass": f["native"]["pass"],
                                 "selected_median": f["selected_width"]["median"],
                                 "selected_pass": f["selected_width"]["pass"]})
            d = arm["distributions"]["nonspecial"]
            requested_neighbors = []
            for row in raw_rows:
                if row["split"] != split:
                    continue
                a = row["arms"][mode]
                requested_neighbors.extend(v for v, requested, position in zip(
                    a["non_target_changed_count"], a["nonzero_requested"], row["position_metadata"])
                    if requested and position["token_class"] != "special")
            delivery.append({"historical_split": split, "mode": mode,
                             "fidelity_denominator": arm["fidelity"]["denominator"],
                             "fidelity_fraction": arm["fidelity"]["fraction"],
                             "norm_denominator": arm["norm"]["denominator"],
                             "norm_fraction": arm["norm"]["fraction"],
                             "zero_request_positions": arm["zero_requested_positions"],
                             "rounded_away_positions": arm["rounded_away_positions"],
                             "median_non_target_changed": d["non_target_changed_count"]["median"],
                             "requested_nonspecial_positions": len(requested_neighbors),
                             "median_non_target_changed_requested_only":
                                 float(np.median(requested_neighbors)) if requested_neighbors else None,
                             "median_non_target_change_norm": d["non_target_change_norm"]["median"],
                             "median_reconstruction_relative_error": d["reconstruction_relative_error"]["median"],
                             "all_components_pass": arm["native_components_pass"]})
    return features, delivery


def figures(features, delivery, ids, out):
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.dpi": 180,
                         "pdf.fonttype": 42, "font.family": "DejaVu Sans"})
    colors = {"calibration": "#087f8c", "validation": "#b34854"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), layout="constrained")
    y = np.arange(len(ids))
    for split, offset in (("calibration", -.12), ("validation", .12)):
        for col, mode in enumerate(("suppression", "amplification")):
            rows = [next(r for r in features if r["historical_split"] == split
                         and r["mode"] == mode and r["feature_id"] == f) for f in ids]
            axes[col].scatter([r["native_median"] if r["native_median"] is not None else np.nan for r in rows], y + offset,
                              c=colors[split], label="Historical " + split, s=34)
            for j, r in enumerate(rows):
                if r["native_median"] is None:
                    axes[col].text(0, j + offset, "N/A", color=colors[split], fontsize=7)
            if col == 0:
                axes[2].scatter([r["positions"] for r in rows], y + offset,
                                c=colors[split], s=34)
    for ax in axes:
        ax.set_yticks(y, [str(f) for f in ids])
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=.2)
    for ax in axes[:2]:
        ax.axvline(.5, color="#555555", linestyle="--", linewidth=1)
    for ax, mode in zip(axes[:2], ("suppression", "amplification")):
        values = [r["native_median"] for r in features
                  if r["mode"] == mode and r["native_median"] is not None]
        ax.set_xlim(min([0.] + values) - .03, max([1.] + values) * 1.08)
    axes[0].set_title("Suppression: lower is stronger")
    axes[0].set_xlabel("Median native after / before")
    axes[1].set_title("Amplification: higher is stronger")
    axes[1].set_xlabel("Median native increment / intended increment")
    axes[2].axvline(100, color="#555555", linestyle="--", linewidth=1)
    axes[2].set_xscale("symlog", linthresh=1)
    axes[2].set_xlim(0, max(125, max(r["positions"] for r in features) * 1.25))
    axes[2].set_title("Exposure: same for both signs")
    axes[2].set_xlabel("Active nonspecial positions (symlog; includes zero)")
    axes[0].legend(loc="best", fontsize=8)
    fig.suptitle("Native SAE-only replay on saved states; not behavioral validation", fontsize=12)
    for ext in ("png", "pdf"):
        fig.savefig(out / ("native_efficacy_exposure." + ext))
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout="constrained")
    labels = [r["historical_split"] + "\n" + r["mode"] for r in delivery]
    x = np.arange(len(delivery))
    fraction = lambda r, key: r[key] if r[key] is not None else np.nan
    axes[0].bar(x - .18, [fraction(r, "fidelity_fraction") for r in delivery], .36,
                color="#087f8c", label="Fidelity: nonzero requests")
    axes[0].bar(x + .18, [fraction(r, "norm_fraction") for r in delivery], .36,
                color="#7268a6", label="Norm: realized nonzero edits")
    axes[0].axhline(.95, color="#555555", linestyle="--", linewidth=1)
    axes[0].set_ylim(0, 1.06)
    axes[0].set_ylabel("Fraction meeting position-level limit")
    axes[0].set_title("Delivery checks use different denominators")
    axes[0].legend(fontsize=8, loc="lower left")
    for i, r in enumerate(delivery):
        for key, offset in (("fidelity_fraction", -.18), ("norm_fraction", .18)):
            if r[key] is None:
                axes[0].text(i + offset, .1, "N/A", ha="center", fontsize=8, rotation=90)
    axes[1].bar(x, [fraction(r, "median_non_target_changed_requested_only") for r in delivery], color="#b34854")
    axes[1].set_title("Effects outside the six selected coordinates")
    axes[1].set_ylabel("Median changed non-target coordinates\n(nonspecial positions with nonzero requests)")
    for i, r in enumerate(delivery):
        if r["median_non_target_changed_requested_only"] is None:
            axes[1].text(i, 0, "N/A", ha="center", fontsize=8)
    for ax in axes:
        ax.set_xticks(x, labels, fontsize=9)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Rounded delivery and off-target activation changes", fontsize=12)
    for ext in ("png", "pdf"):
        fig.savefig(out / ("native_delivery_neighbors." + ext))
    plt.close(fig)


def rebuild(run, plan_path, out):
    plan = load_plan(plan_path)
    result = audit(run, plan_path)
    rows = [json.loads(p.read_text()) for p in sorted((Path(run) / "rows").glob("*.json"))]
    features, delivery = tables(result, plan["feature_ids"], rows)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "audit.json").write_text(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                             allow_nan=False) + "\n")
    for name, rows in (("features.csv", features), ("delivery.csv", delivery)):
        with (out / name).open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    figures(features, delivery, plan["feature_ids"], out)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = rebuild(args.run, args.plan, args.out)
    print(json.dumps({"pass": result["pass"], "rows": result["rows"],
                      "behavioral_assay_qualified": False}))
