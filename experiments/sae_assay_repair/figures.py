"""Display-only repair summaries; no threshold, recipe or endpoint selection."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .protocol import OPERATORS, TARGETS

LABELS = {"literal": "Literal decoder delta", "decoder_span": "Decoder-span correction",
          "encoder_min_norm": "Encoder minimum norm"}
COLORS = {"literal": "#52525b", "decoder_span": "#00796b", "encoder_min_norm": "#b3413a"}


def tables(run):
    final = json.loads((Path(run) / "target-final.json").read_text())
    gates, coordinates = [], []
    for operator in OPERATORS:
        report = final["calibration"].get(operator, {})
        if "selection" not in report:
            gates.append({"operator": operator, "status": report.get("unavailable", "not_run")})
            continue
        for dose in (.5, 1.):
            gate = report["selection"]["calibration"][str(dose)]
            for mode, arm in gate["directions"].items():
                gates.append({"operator": operator, "dose": dose, "direction": mode,
                    "status": "pass" if arm["pass"] else "fail",
                    "encoder_decision_pass": report.get("encoder", {}).get("pass"),
                    "failure_codes": ";".join(arm["failure_codes"]),
                    "residual_fidelity_pass_fraction": arm["numerical"]["pass_fraction"],
                    "norm_pass_fraction": arm["norm"]["pass_fraction"],
                    "neutral_nll_delta": arm["neutral_loss"]["paired_token_weighted_delta"]})
                for feature in arm["features"]:
                    coordinates.append({"operator": operator, "dose": dose, "direction": mode,
                        "feature_id": feature["feature_id"],
                        "median_paired_ratio": feature["paired_ratio"]["median"],
                        "eligible_positions": feature["eligible_positions"],
                        "eligible_texts": feature["eligible_texts"],
                        "exposure_pass": feature["exposure_pass"],
                        "efficacy_pass": feature["efficacy_pass"]})
    return gates, coordinates


def render(run, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    gates, rows = tables(run)
    for filename, values in (("gates.csv", gates), ("coordinates.csv", rows)):
        fields = list(dict.fromkeys(key for row in values for key in row))
        with (out / filename).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.2), sharex=True, sharey="row")
    x = np.arange(len(TARGETS))
    for col, dose in enumerate((.5, 1.)):
        for row_i, direction in enumerate(("suppression", "amplification")):
            ax = axes[row_i, col]
            for offset, operator in zip((-.16, 0, .16), OPERATORS):
                group = {r["feature_id"]: r for r in rows if
                         r["operator"] == operator and r["dose"] == dose and r["direction"] == direction}
                y = [group.get(i, {}).get("median_paired_ratio") for i in TARGETS]
                y = [np.nan if v is None else v for v in y]
                ax.plot(x + offset, y, "o", color=COLORS[operator], label=LABELS[operator], markersize=6)
                for j, feature in enumerate(TARGETS):
                    if feature in group and not group[feature]["exposure_pass"] and np.isfinite(y[j]):
                        ax.plot(x[j]+offset, y[j], "x", color="black", markersize=9, markeredgewidth=1)
            ax.axhline(.5, color="#737373", linewidth=1, linestyle="--")
            ax.set_title(f"{direction.capitalize()}, strength {dose:g}")
            ax.set_xticks(x, [str(i) for i in TARGETS])
            ax.grid(axis="y", color="#e5e5e5")
            ax.set_axisbelow(True)
    axes[0, 0].set_ylabel("Median after / before\nLower = stronger suppression")
    axes[1, 0].set_ylabel("Median achieved / requested increase\nHigher = stronger amplification")
    for row in axes:
        low, high = row[0].get_ylim()
        row[0].set_ylim(min(-.04, low), max(1.04, high))
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .935), ncol=3, frameon=False)
    fig.suptitle("Requested versus delivered SAE coordinate changes", y=.99, fontsize=14)
    fig.text(.5, .012, "Dashed: efficacy boundary. Cross: inadequate exposure. Fixed-text medians, not confidence intervals.",
             ha="center", fontsize=10)
    fig.subplots_adjust(left=.09, right=.985, bottom=.12, top=.825, hspace=.29, wspace=.10)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / ("coordinate-delivery." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)
    available = [g for g in gates if "dose" in g]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharey=True)
    labels = [f"{LABELS[g['operator']]}\n{g['direction']} {g['dose']:g}" for g in available]
    for ax, metric, title in zip(axes, ("residual_fidelity_pass_fraction", "norm_pass_fraction"),
                               ("Residual delivery fidelity", "Edit norm within 5% of clean state")):
        y = np.arange(len(available))
        ax.barh(y, [g[metric] if g[metric] is not None else 0 for g in available],
                color=[COLORS[g["operator"]] for g in available])
        ax.axvline(.95, color="#111111", linestyle="--", linewidth=1)
        ax.set_xlim(0, 1.02)
        ax.set_title(title)
        ax.set_xlabel("Fraction of applicable positions")
        ax.set_yticks(y, labels, fontsize=8)
        for i, g in enumerate(available):
            if g[metric] is None:
                ax.text(.02, i, "unavailable", va="center", fontsize=8)
    axes[0].invert_yaxis()
    fig.set_size_inches(11.5, max(5., len(available) * .49))
    fig.text(.5, .005, "Special positions are included in these frozen gates. Dashed: required 95%. All other gates still apply.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .025, 1, 1))
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / ("delivery-constraints." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)
    qualification = Path(run) / "rows/qualification-live.json"
    if qualification.is_file():
        geometry(json.loads(qualification.read_text())["geometry"], out)


def geometry(value, out):
    """Display pinned-weight geometry separately from intervention outcomes."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.3), layout="constrained")
    labels = [str(i) for i in value["feature_ids"]]
    matrices = [np.asarray(value[name]) for name in ("encoder_decoder_response", "encoder_gram")]
    scale = max(np.max(np.abs(matrix)) for matrix in matrices)
    for ax, matrix, title, xlabel in zip(axes, matrices,
            ("Encoder response to decoder directions: E D", "Encoder-direction Gram matrix: E E.T"),
            ("Decoder direction", "Encoder direction")):
        if matrix.shape != (len(labels), len(labels)) or not np.isfinite(matrix).all():
            raise ValueError("Invalid geometry matrix")
        im = ax.imshow(matrix, cmap="RdBu_r", vmin=-scale, vmax=scale)
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
        ax.set_yticks(range(len(labels)), labels)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Measured coordinate")
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=9,
                        color="white" if abs(matrix[i, j]) > .65 * scale else "black")
    fig.colorbar(im, ax=axes, shrink=.78, label="Preactivation response per unit direction")
    fig.suptitle("Decoder edits do not map one-for-one to preactivations", fontsize=14)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(Path(out) / ("coordinate-geometry." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


def mundane_controls(report, out):
    """Show contextual feature activity and an unsteered formatting check."""
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.9), layout="constrained")
    contexts = report["context_activity"]
    names = ["raw", "instruction_raw", "assistant_chat", "user_chat"]
    rates = [contexts[name]["positive"] / contexts[name]["positions"] for name in names]
    axes[0].bar(range(4), rates, color="#52525b", width=.6)
    axes[0].set_xticks(range(4), ["Bare JSON", "Instruction\n+ JSON", "Assistant\nchat", "User\nchat"])
    axes[0].set_ylim(0, max(.05, max(rates) * 1.4))
    axes[0].set_ylabel("Fraction of nonspecial positions active")
    axes[0].set_title("Feature 7688 across four contexts", fontsize=11)
    for i, name in enumerate(names):
        row = contexts[name]
        axes[0].text(i, rates[i], f"{row['positive']}/{row['positions']}", ha="center", va="bottom", fontsize=9)
    names = ["zero", "instruction"]
    values = [report["formatting"][name] for name in names]
    axes[1].bar(range(2), [v["strict_json"] / v["n"] for v in values],
                color=["#52525b", "#00796b"], width=.5)
    axes[1].set_xticks(range(2), ["No format instruction", "Explicit JSON instruction"])
    axes[1].set_ylabel("Prespecified flat-JSON record rate")
    axes[1].set_ylim(0, 1.13)
    axes[1].set_title("Behavioral endpoint check: no SAE intervention", fontsize=11)
    for i, row in enumerate(values):
        axes[1].text(i, row["strict_json"] / row["n"], f"{row['strict_json']}/{row['n']}",
                     ha="center", va="bottom", fontsize=10)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Mundane controls do not establish target-steering success", fontsize=13)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(Path(out) / ("mundane-controls." + suffix), dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    render(args.run, args.out)
