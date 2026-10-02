"""Read-only raw-to-decision verification and descriptive qualification plots."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.instruction_state_qualification import analysis, protocol
from experiments.instruction_state_qualification.raw_audit import raw_audit

RELEASE = ROOT / "data/instruction_state_qualification/crossed_v1_20261001"
FREEZE = "0acf16548f7dfe0359ce6c19bf952725572697d5"
PLAN_HASH = "d614da0b4398ddc021300a177a2218009a48b74c4fe5952df2852d20f0ef9d0f"
JUDGE_FILES = ("snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_manifest(root):
    root = Path(root)
    manifest = json.loads((root / "MANIFEST.json").read_text())
    expected = manifest["files_sha256"]
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Release contains a symlink")
        if path.is_file() and path != root / "MANIFEST.json":
            actual[path.relative_to(root).as_posix()] = digest(path)
    if actual != expected:
        raise ValueError("Release inventory/hash mismatch")
    entries = [{"path": name, "bytes": (root / name).stat().st_size,
                "sha256": sha} for name, sha in sorted(actual.items())]
    if manifest.get("files") != entries:
        raise ValueError("Release file-list/size mismatch")
    if manifest["science_freeze"] != FREEZE or manifest["plan_sha256"] != PLAN_HASH:
        raise ValueError("Wrong release provenance")
    return len(actual)


def verify(root=RELEASE):
    """Temporary copies isolate legacy ledger opens from released evidence."""
    root = Path(root)
    files = verify_manifest(root)
    plan_path = ROOT / protocol.TOKEN_BINDINGS_PATH
    plan_path = plan_path.with_name("PLAN.json")
    plan = protocol.load_plan(plan_path)
    if digest(plan_path) != PLAN_HASH or digest(root / "raw/PLAN.json") != PLAN_HASH:
        raise ValueError("Scientific plan differs from the released freeze")
    with tempfile.TemporaryDirectory(prefix="qualification-reanalysis-") as directory:
        raw = Path(directory) / "raw"
        shutil.copytree(root / "raw", raw, copy_function=shutil.copyfile)
        final_audit = raw_audit(raw, plan, partial=False)
        judges = Path(directory) / "judges"
        judges.mkdir()
        for name in JUDGE_FILES:
            shutil.copyfile(root / "judges" / name, judges / name)
        decision = analysis.analyze(raw, judges, plan, PLAN_HASH, FREEZE, 12)
        rebuilt = Path(directory) / "analysis"
        analysis.write_analysis(rebuilt, decision)
        for name in ("decision-look12.json", "cases-look12.csv"):
            if (rebuilt / name).read_bytes() != (root / "analysis" / name).read_bytes():
                raise ValueError("Runtime analysis is not exactly reproduced: " + name)
    terminal = json.loads((root / "raw/DONE-all.json").read_text())
    if terminal["gate_decision"] != decision["decision"] or terminal["stage_b_started"] is not False:
        raise ValueError("Worker did not obey the stopping decision")
    lifecycle = json.loads((root / "LIFECYCLE.json").read_text())
    if any(row["get_status"] != 404 for row in lifecycle["owned_pods"]):
        raise ValueError("Owned pod deletion not recorded")
    gpu = sum((Decimal(row["compute_upper_bound_usd"]) for row in lifecycle["owned_pods"]), Decimal(0))
    total = gpu + Decimal(str(decision["api_spent_usd"]))
    if total != Decimal(lifecycle["new_cost_upper_bound_usd"]) or total > 25:
        raise ValueError("Cost carry or original stop-loss mismatch")
    for row in lifecycle["owned_pods"]:
        calculated = (Decimal(row["elapsed_seconds"]) *
                      (Decimal(row["hourly_rate_usd"]) + Decimal(row["storage_hourly_usd"])) / 3600)
        if abs(calculated - Decimal(row["compute_upper_bound_usd"])) > Decimal("1e-24"):
            raise ValueError("Pod cost arithmetic mismatch")
    return decision, {"pass": True, "files_verified": files, "final_raw_audit": final_audit,
                      "runtime_decision_byte_exact": True, "runtime_case_table_byte_exact": True,
                      "new_cost_upper_bound_usd": str(total), "no_model_or_api_calls": True}


def tables(root, decision):
    cells, endpoints, caps = [], [], []
    for provider, value in decision["providers"].items():
        for instruction in ("history", "self"):
            for transcript in ("history", "self"):
                key = instruction + ":" + transcript
                count = value["counts"]["positive"][key]
                cells.append({"provider": provider, "instruction": instruction,
                              "transcript": transcript, "positive": count, "n": 12,
                              "rate": count / 12})
        counts = decision["secondary_counts"][provider]
        endpoints.append({"provider": provider, "criterion": "paper_positive",
                          "count": sum(value["counts"]["positive"].values()), "n": 48})
        endpoints.extend({"provider": provider, "criterion": key, "count": val, "n": 48}
                         for key, val in counts.items())
    for path in sorted((Path(root) / "raw/rows").glob("block-*.json")):
        row = json.loads(path.read_text())
        for source, generation in row["sources"].items():
            caps.append({"block": row["id"], "kind": "source", "condition": source,
                         "tokens": generation["output_tokens"], "cap_hit": generation["cap_hit"]})
        for response in row["responses"]:
            g = response["generation"]
            caps.append({"block": row["id"], "kind": "answer", "condition": response["id"],
                         "tokens": g["output_tokens"], "cap_hit": g["cap_hit"]})
    return {"cell_counts.csv": cells, "endpoint_counts.csv": endpoints,
            "generation_lengths.csv": caps}


def figures(out, decision):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    providers = (("openai", "GPT-6 Astra"), ("anthropic", "Claude Opus 5.5"))
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 4.2), constrained_layout=True)
    for ax, (provider, label) in zip(axes, providers):
        counts = decision["providers"][provider]["counts"]["positive"]
        matrix = np.array([[counts[i + ":" + t] for i in ("history", "self")]
                           for t in ("history", "self")])
        ax.imshow(matrix / 12, cmap="GnBu", vmin=0, vmax=1)
        for y in range(2):
            for x in range(2):
                ax.text(x, y, f"{matrix[y, x]}/12\n{matrix[y, x] / 12:.0%}",
                        ha="center", va="center", fontsize=16,
                        color="white" if matrix[y, x] >= 8 else "#172428")
        ax.set_xticks([0, 1], ["History", "Self-reference"])
        ax.set_yticks([0, 1], ["History", "Self-reference"])
        ax.set_xlabel("Retained instruction")
        ax.set_ylabel("Transcript source")
        ax.set_title(label, pad=10)
    fig.suptitle("Llama 3.3 70B: Paper-rubric positive labels", fontsize=14)
    for suffix in ("png", "pdf"):
        fig.savefig(out / ("crossed_labels." + suffix), dpi=180,
                    metadata={"Creator": "CONSCIOUS raw-to-figure reproduction"})
    plt.close(fig)
    keys = ("paper_positive", "inclusive_current_assertion", "explicit_current_assertion",
            "mixed", "denied", "reported_context_conflict")
    labels = ("Paper-rubric positive", "Inclusive current attribution", "Explicit current assertion",
              "Mixed assertions / denials", "Contains a denial", "Reports context conflict")
    fig, ax = plt.subplots(figsize=(8.5, 4.6), constrained_layout=True)
    positions = np.arange(len(keys))
    for offset, color, (provider, label) in zip((-.18, .18), ("#007f83", "#ba4773"), providers):
        secondary = decision["secondary_counts"][provider]
        values = [sum(decision["providers"][provider]["counts"]["positive"].values())
                  if key == "paper_positive" else secondary[key] for key in keys]
        bars = ax.barh(positions + offset, values, height=.32, label=label, color=color)
        ax.bar_label(bars, labels=[str(v) + "/48" for v in values], padding=4, fontsize=9)
    ax.set_yticks(positions, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 54)
    ax.set_xticks([0, 12, 24, 36, 48])
    ax.set_xlabel("Responses; categories overlap and are not human-validated")
    ax.set_title("The judgment criterion changes what gets counted", pad=12)
    ax.legend(loc="lower right", frameon=False)
    for suffix in ("png", "pdf"):
        fig.savefig(out / ("measurement_categories." + suffix), dpi=180,
                    metadata={"Creator": "CONSCIOUS raw-to-figure reproduction"})
    plt.close(fig)


def reproduce(root, out=None, make_figures=False):
    root = Path(root).resolve()
    decision, report = verify(root)
    if out is not None:
        out = Path(out).resolve()
        if out == root or out.is_relative_to(root) or root.is_relative_to(out):
            raise ValueError("Derived outputs must be outside the immutable release")
        out.mkdir(parents=True, exist_ok=False)
        for name, rows in tables(root, decision).items():
            with (out / name).open("x", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        (out / "verification.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        if make_figures:
            figures(out, decision)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--figures", action="store_true")
    args = parser.parse_args()
    if args.figures and args.out is None:
        parser.error("--figures requires a separate --out directory")
    print(json.dumps(reproduce(args.release, args.out, args.figures), sort_keys=True))


if __name__ == "__main__":
    main()
