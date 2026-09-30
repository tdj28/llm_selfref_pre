#!/usr/bin/env python3
"""Post-freeze, CPU-only descriptive reporting; never a release builder.

Run from the repository root with ``python -m scripts.report_sae_exposure``.
Requires complete audited clean exposure. An absent, failed, incomplete or
unauditable pilot gets explicit status and blank metrics, never zero effects.
Outputs go to a NEW directory outside the input run. No model is constructed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import re
import statistics

from experiments.sae_assay_exposure import analysis as clean
from experiments.sae_assay_precision import pilot
from experiments.sae_assay_replay import exposure


ROOT = Path(__file__).resolve().parents[1]
PLAN_SHA256 = "52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9"
MODES = pilot.MODES
MODE_LABELS = ("Native\nzero", "Precision\nsham", "Suppression", "Amplification")
REFERENCES = ("native_zero", "precision_sham")
PANELS = ("discovery_all", "discovery_selected", "validation", "representative")
FEATURE_FIELDS = (
    "nonspecial_denominator", "native_active_positions", "promoted_active_positions",
    "native_active_texts", "support_disagreements", "readout_shift_mean",
    "primary_eligible_native_active_positions", "paired_promoted_defined_positions",
    "paired_promoted_undefined_positions", "native_anchor_after_ratio_median",
    "paired_delta_over_requested_native_change_median", "paired_promoted_after_ratio_median",
    "paired_promoted_defined_only_after_ratio_median", "paired_promoted_fraction_median",
)
LOSS_FIELDS = ("paired_tokens", "delta_nll_mean", "kl_tokens", "kl_mean")
SCOPE = "Descriptive engineering components only; no global assay qualification or behavioral claim"


def read_json(path):
    def reject(value):
        raise ValueError("Nonfinite JSON: " + value)
    return json.loads(Path(path).read_text(), parse_constant=reject)


def file_record(path, relative_to):
    return {"path": path.relative_to(relative_to).as_posix(),
            "bytes": path.stat().st_size, "sha256": clean.sha(path)}


def load_plan(path, expected_sha256):
    path = Path(path)
    if not re.fullmatch("[0-9a-f]{64}", expected_sha256) or clean.sha(path) != expected_sha256:
        raise ValueError("Report plan hash mismatch")
    plan = read_json(path)
    if path.read_bytes() != (exposure.canonical(plan) + "\n").encode():
        raise ValueError("Noncanonical plan")
    clean.checked_design(plan)
    # Unlike the runtime loader, reporting does not require HEAD to be the old
    # freeze. It does require the actual bound source/input bytes to be intact.
    for key in ("source_hashes", "input_hashes"):
        if not isinstance(plan.get(key), dict) or not plan[key]:
            raise ValueError("Missing frozen " + key)
        for name, digest in plan[key].items():
            source = ROOT / name
            if Path(name).is_absolute() or ".." in Path(name).parts or clean.sha(source) != digest:
                raise ValueError("Frozen source/input drift: " + name)
    return plan


def audit_pilot(run, plan, plan_hash, freeze):
    root = run / pilot.DIRECTORY
    row_paths = sorted((root / "rows").glob("*.json"))
    status = {"status": "not_planned" if "precision_pilot" not in plan else "not_run",
              "observed_row_files": len(row_paths), "audited_rows": 0,
              "full_model_forwards": None, "audit_error": None}
    if "precision_pilot" not in plan:
        if root.exists():
            raise ValueError("Unplanned precision-pilot artifacts")
        return status, None, []
    if not root.exists():
        return status, None, []
    failed = (root / "failure.json").exists()
    status["status"] = "failed" if failed else "incomplete"
    if not (root / "summary.json").exists():
        return status, None, []
    try:
        audit = pilot.validate_run(run, plan, plan_hash, freeze)
        if audit.get("structural_pass") is not True:
            raise ValueError("Pilot structural audit did not pass")
        if failed:
            raise ValueError("Pilot has both failure and completion artifacts")
        rows = [read_json(path) for path in row_paths]
        summary = pilot.summarize(rows)
        if summary != read_json(root / "summary.json"):
            raise ValueError("Pilot summary reconstruction mismatch")
        if any(row["feature_ids"] != list(exposure.TARGETS) for row in rows):
            raise ValueError("Pilot must retain all six ordered feature IDs")
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        status.update(status="audit_failed", audit_error=f"{type(exc).__name__}: {exc}")
        return status, None, []
    status.update(status="complete", audited_rows=audit["row_count"],
                  full_model_forwards=summary["full_model_forwards"])
    return status, summary, rows


def load_audited(run, plan_path, freeze, *, expected_sha256=PLAN_SHA256):
    run, plan_path = Path(run), Path(plan_path)
    if not re.fullmatch("[0-9a-f]{40}", freeze):
        raise ValueError("Full freeze commit required")
    plan = load_plan(plan_path, expected_sha256)
    if not (run / "receipts.jsonl").is_file() or not (run / "receipts.jsonl").stat().st_size:
        raise ValueError("Missing or empty clean receipt ledger")
    rows = clean.audit_run(run, plan, expected_sha256, freeze)
    summary = clean.summarize(rows, plan, plan_sha256=expected_sha256, freeze_commit=freeze)
    if summary != read_json(run / "summary.json"):
        raise ValueError("Clean summary differs from audited raw reconstruction")
    status, precision, pilot_rows = audit_pilot(run, plan, expected_sha256, freeze)
    terminal = read_json(run / "DONE-all.json") if (run / "DONE-all.json").exists() else None
    if terminal is not None and (terminal.get("plan_sha256") != expected_sha256
                                 or terminal.get("freeze_commit") != freeze):
        raise ValueError("Worker terminal binding mismatch")
    synthetic = bool(precision and precision["test_only"])
    model_metadata = list(run.glob("model-*-load-*.json"))
    for path in model_metadata:
        synthetic = synthetic or bool(read_json(path).get("test_only"))
    paths = {run / "receipts.jsonl", run / "summary.json"}
    paths.update(model_metadata)
    paths.update((run / "rows").glob("*.json"))
    paths.update((run / "residuals").glob("*.safetensors"))
    paths.update(p for p in (run / pilot.DIRECTORY).rglob("*") if p.is_file())
    if terminal is not None:
        paths.add(run / "DONE-all.json")
    if any(path.is_symlink() or not path.resolve().is_relative_to(run.resolve()) for path in paths):
        raise ValueError("Reporting inputs cannot escape the run directory")
    return {"plan_sha256": expected_sha256, "freeze_commit": freeze, "clean": summary,
            "pilot_status": status, "pilot": precision, "pilot_rows": pilot_rows,
            "worker_status": terminal.get("status") if terminal else "no_terminal_receipt",
            "synthetic_only": synthetic, "inputs": [file_record(path, run) for path in sorted(paths)]}


def exposure_table(summary):
    panels = {"discovery_all": summary["panels"]["discovery"],
              "discovery_selected": summary["discovery"]["selected_panel"],
              "validation": summary["panels"]["validation"],
              "representative": summary["panels"]["representative"]}
    result = []
    for panel, values in panels.items():
        features = {row["feature_id"]: row for row in values["features"]}
        if set(features) != set(exposure.TARGETS) or len(values["features"]) != 6:
            raise ValueError("Incomplete six-feature exposure summary")
        for feature in exposure.TARGETS:
            result.append({"panel": panel, "feature_id": feature,
                "text_count": values["text_count"], "nonspecial_positions": values["nonspecial_positions"],
                **{key: features[feature][key] for key in ("active_positions", "active_texts", "active_families")},
                "minimum_positions": exposure.MIN_POSITIONS, "minimum_texts": exposure.MIN_TEXTS,
                "clean_exposure_minimum_met": features[feature]["exposure_minimum_met"],
                "role": "component_gate" if panel in ("discovery_selected", "validation") else "descriptive_only"})
    return result


def precision_tables(summary, status):
    delivery, features = [], []
    for mode in MODES:
        values = summary["modes"][mode] if summary is not None else None
        row = {"mode": mode, "pilot_status": status["status"],
               "text_count": summary["text_count"] if summary is not None else None}
        for key in ("all_positions", "nonspecial_positions", "nonzero_requests", "zero_requests"):
            row[key] = values[key] if values is not None else None
        for component in ("fidelity", "norm"):
            for key in ("passing_positions", "denominator", "fraction", "pass"):
                row[component + "_" + key] = values[component][key] if values is not None else None
        row["component_required_fraction"] = .95
        delivery.append(row)
        for feature in exposure.TARGETS:
            observed = values["features"][str(feature)] if values is not None else None
            features.append({"mode": mode, "feature_id": feature, "pilot_status": status["status"],
                             **{key: observed[key] if observed is not None else None for key in FEATURE_FIELDS}})
    return delivery, features


def _mean(values):
    return statistics.fmean(values) if values else None


def paired_losses(rows):
    """Same-position differences, then equal-weight text means; KL is directional.

    Native-to-sham KL cannot supply the unrecorded sham-to-native KL. The latter
    stays undefined even though its paired NLL difference can be computed.
    """
    by_text = {}
    for row in rows:
        group = by_text.setdefault(row["text_id"], {})
        if row["mode"] not in MODES or row["mode"] in group:
            raise ValueError("Unplanned or duplicate paired-loss row")
        group[row["mode"]] = row
    result = []
    for text_id, group in sorted(by_text.items()):
        if set(group) != set(MODES):
            raise ValueError("All four modes required for paired losses")
        for mode in MODES:
            row = group[mode]
            for reference in REFERENCES:
                baseline = group[reference]
                if (row["token_ids"] != baseline["token_ids"]
                        or row["special_tokens_mask"] != baseline["special_tokens_mask"]):
                    raise ValueError("Pairing requires exact shared tokens and special masks")
                n = len(row["token_ids"])
                divergences = row["kl_native_to_mode" if reference == "native_zero" else "kl_sham_to_mode"]
                if len(row["nll"]) != n or len(baseline["nll"]) != n or (divergences is not None and len(divergences) != n):
                    raise ValueError("Paired loss length mismatch")
                differences, kl = [], []
                for i, special in enumerate(row["special_tokens_mask"]):
                    left, right = row["nll"][i], baseline["nll"][i]
                    if not special and left is not None and right is not None:
                        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (left, right)):
                            raise ValueError("Invalid paired NLL")
                        differences.append(left - right)
                    if not special and divergences is not None and divergences[i] is not None:
                        value = divergences[i]
                        if type(value) not in (int, float) or not math.isfinite(value):
                            raise ValueError("Invalid paired KL")
                        kl.append(value)  # Retain negative roundoff; never clip.
                result.append({"text_id": text_id, "mode": mode, "reference": reference,
                               "paired_tokens": len(differences), "delta_nll_mean": _mean(differences),
                               "kl_tokens": len(kl), "kl_mean": _mean(kl)})
    return result


def loss_summary(pairs, status):
    result = []
    for mode in MODES:
        for reference in REFERENCES:
            group = [row for row in pairs if row["mode"] == mode and row["reference"] == reference]
            row = {"mode": mode, "reference": reference, "pilot_status": status["status"]}
            for name, mean, count in (("delta_nll", "delta_nll_mean", "paired_tokens"),
                                      ("kl", "kl_mean", "kl_tokens")):
                available = [r for r in group if r[mean] is not None]
                total = sum(r[count] for r in available)
                row[name + "_texts"] = len(available) if status["status"] == "complete" else None
                row[name + "_tokens"] = total if status["status"] == "complete" else None
                row[name + "_text_equal_mean"] = _mean([r[mean] for r in available])
                row[name + "_token_pooled_mean"] = math.fsum(r[mean] * r[count] for r in available) / total if total else None
            result.append(row)
    return result


def make_tables(bundle):
    delivery, features = precision_tables(bundle["pilot"], bundle["pilot_status"])
    pairs = paired_losses(bundle["pilot_rows"])
    return {"exposure": exposure_table(bundle["clean"]), "precision_delivery": delivery,
            "precision_features": features, "paired_losses_by_text": pairs,
            "paired_losses": loss_summary(pairs, bundle["pilot_status"])}


def figures(tables, bundle):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "savefig.dpi": 180})
    prefix = "SYNTHETIC TEST ONLY | " if bundle["synthetic_only"] else ""
    fig, axes = plt.subplots(2, 4, figsize=(14, 7.2))
    titles = ("Discovery: full panel", "Discovery: selected union", "Validation: fixed panel",
              "Representative: descriptive only")
    colors = ("#237C87", "#665D9F", "#C85554", "#C69B29")
    x = list(range(6))
    for j, panel in enumerate(PANELS):
        group = [r for r in tables["exposure"] if r["panel"] == panel]
        axes[0, j].set_title(titles[j] + f"\n{group[0]['text_count']} texts", fontsize=10)
        for i, (key, threshold) in enumerate((("active_positions", 100), ("active_texts", 6))):
            ax = axes[i, j]
            values = [r[key] for r in group]
            ax.bar(x, values, color=colors[j], width=.65, zorder=3)
            ax.axhline(threshold, color="#202020", linestyle="--", linewidth=1.0, zorder=4)
            ax.set_ylim(0, max(threshold, max(values)) * (1.8 if i == 0 else 1.22))
            if i == 0:
                ax.set_yscale("symlog", linthresh=100)
            else:
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.set_xticks(x, [str(f) for f in exposure.TARGETS], rotation=45, ha="right")
            ax.grid(axis="y", alpha=.18, zorder=0)
            for pos, value in enumerate(values):
                ax.annotate(str(value), (pos, value), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)
    axes[0, 0].set_ylabel("Active nonspecial positions\nsymlog, linear through 100")
    axes[1, 0].set_ylabel("Distinct active texts")
    fig.suptitle(prefix + "Clean native-SAE exposure | all six target IDs", fontsize=14)
    fig.text(.06, .035, "Dashed references: 100 positions and 6 texts. Representative panel is never pooled for gates.\n"
             "Authored families are the sampling unit; counts are descriptive, not independent draws. No behavioral qualification.", fontsize=9)
    fig.subplots_adjust(left=.07, right=.985, bottom=.17, top=.86, hspace=.50, wspace=.33)

    precision, axes2 = plt.subplots(2, 2, figsize=(12, 8))
    branches = list(range(4))
    status = bundle["pilot_status"]
    precision.suptitle(prefix + "Precision transport | " + status["status"].replace("_", " "), fontsize=14)
    for ax, component, title in zip(axes2[0], ("fidelity", "norm"), (
            "Fidelity: cosine >=0.95 and relative error <=0.20", "Norm: realized / clean <=0.05")):
        ax.set_title(title, fontsize=10)
        ax.axhline(.95, color="#202020", linestyle="--", linewidth=1)
        for pos, row in enumerate(tables["precision_delivery"]):
            value, n = row[component + "_fraction"], row[component + "_denominator"]
            if value is None:
                ax.text(pos, .13, "N/A" + (f"\nn={n}" if n is not None else "\nnot audited"), ha="center", fontsize=8)
            else:
                ax.bar(pos, value, color=colors[pos], width=.55)
                ax.text(pos, value + .035, f"{value:.3f}\nn={n}", ha="center", fontsize=8)
        ax.set_ylim(0, 1.25)
        ax.set_xlim(-.5, 3.5)
        ax.set_ylabel("Passing fraction")
        ax.set_xticks(branches, MODE_LABELS)
    for ax, metric, title in zip(axes2[1], ("delta_nll", "kl"), (
            "Paired NLL difference: mode minus reference", "Recorded directional KL: reference to mode")):
        ax.set_title(title, fontsize=10)
        ax.axhline(0, color="#777777", linewidth=.8)
        for reference, offset, color, marker in zip(REFERENCES, (-.1, .1), ("#237C87", "#C85554"), ("o", "s")):
            group = [r for r in tables["paired_losses"] if r["reference"] == reference]
            available = [(i, r[metric + "_text_equal_mean"]) for i, r in enumerate(group)
                         if r[metric + "_text_equal_mean"] is not None]
            ax.plot([i + offset for i, _ in available], [v for _, v in available],
                    linestyle="none", marker=marker, color=color, label=reference.replace("_", " "))
            for i, row in enumerate(group):
                if row[metric + "_text_equal_mean"] is None:
                    ax.text(i + offset, .04 if offset < 0 else .12, "N/A", transform=ax.get_xaxis_transform(),
                            color=color, ha="center", fontsize=8)
        ax.set_xticks(branches, MODE_LABELS)
        ax.set_xlim(-.5, 3.5)
        ax.set_ylabel("Text-equal mean (nats)")
        ax.grid(axis="y", alpha=.18)
        if status["status"] == "complete":
            ax.legend(frameon=False, loc="best", fontsize=8)
        else:
            ax.set_yticks([])
            ax.set_ylim(0, 1)
            ax.set_ylabel("Not evaluated")
            ax.text(.5, .5, "No audited pilot measurements", transform=ax.transAxes, ha="center")
    precision.text(.07, .035, "Fidelity denominator: nonzero requests. Norm denominator: nonzero realized edits. Dashed reference: 0.95.\n"
                   "NLL/KL use paired nonspecial scored tokens, then equal text weights. Unrecorded reverse KL is N/A.\n"
                   f"Audited pilot rows: {status['audited_rows']}; observed row files: {status['observed_row_files']}. "
                   "No global qualification; no inferential intervals.", fontsize=9)
    precision.subplots_adjust(left=.09, right=.97, top=.87, bottom=.19, hspace=.50, wspace=.30)
    return {"exposure_counts": fig, "precision_components": precision}


def write_report(bundle, out):
    """Write only derived artifacts to a new output directory."""
    out = Path(out)
    if out.exists():
        raise ValueError("Report output must be a new directory")
    tables = make_tables(bundle)
    charts = figures(tables, bundle)
    out.mkdir(parents=True, exist_ok=False)
    try:
        for name, rows in tables.items():
            fields = list(rows[0]) if rows else ["text_id", "mode", "reference", *LOSS_FIELDS]
            with (out / (name + ".csv")).open("x", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        for name, figure in charts.items():
            for extension in ("png", "pdf"):
                figure.savefig(out / (name + "." + extension), facecolor="white")
    finally:
        import matplotlib.pyplot as plt
        for figure in charts.values():
            plt.close(figure)
    report = {key: bundle[key] for key in ("plan_sha256", "freeze_commit", "pilot_status", "worker_status", "synthetic_only", "inputs")}
    report.update(schema="sae_exposure_descriptive_report_v1", scope=SCOPE,
                  report_script_sha256=clean.sha(Path(__file__)),
                  clean_audited_rows=bundle["clean"]["rows"],
                  methods={"exposure": "Frozen native clean counts and discovery-only selection; representative kept separate",
                           "loss": "Mode-minus-reference within matched nonspecial scored tokens; text-equal and token-pooled descriptive means",
                           "kl": "Recorded reference-to-mode direction only; preserve negative numerical roundoff",
                           "missing_pilot": "No partial scientific pooling; unaudited metrics remain blank"},
                  outputs=[file_record(path, out) for path in sorted(out.iterdir()) if path.is_file()])
    with (out / "REPORT.json").open("x") as handle:
        handle.write(exposure.canonical(report) + "\n")
    return report


def generate_report(run, plan, freeze, out, *, expected_sha256=PLAN_SHA256):
    run, out = Path(run).resolve(), Path(out).resolve()
    if out.exists() or out.is_relative_to(run):
        raise ValueError("Use a new report directory outside the input run")
    return write_report(load_audited(run, plan, freeze, expected_sha256=expected_sha256), out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("run", "plan", "out"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan-sha256", default=PLAN_SHA256)
    args = parser.parse_args()
    report = generate_report(args.run, args.plan, args.freeze, args.out, expected_sha256=args.plan_sha256)
    print(exposure.canonical({"report": str(args.out / "REPORT.json"), "pilot_status": report["pilot_status"]}))
    if report["pilot_status"]["status"] == "audit_failed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
