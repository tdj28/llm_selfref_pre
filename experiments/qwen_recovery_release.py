"""Offline additive release of the three-label, post-hoc Qwen3.8 repair."""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal
import gzip
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory

from experiments import qwen_judge_recovery as q
from experiments.openrouter_swap import analysis as schema
from experiments.openrouter_swap.ledger import Ledger, _no_symlinks
from experiments.openrouter_swap.release import _inventory
from experiments.openrouter_swap_openweights import analysis
from experiments.openrouter_swap_openweights_a1.release import _scan_payloads

SOURCES = ("experiments/qwen_recovery_release.py", "tests/test_qwen_recovery_release.py")
MODEL = "qwen/qwen3.8-2.4t-a95b"
DERIVED = {"RELEASE.json", "recovery_report.json", "logical_projection.json",
           "recovery_main_rows.json", "recovery_main_analysis.json", "evidence/values.json",
           "evidence/editorial.md", "evidence/editorial_values.tex", "figures/figure_data.json",
           "figures/primary_contrasts.png", "figures/primary_contrasts.pdf", "README.md"}
REQUIRED = {"PLAN.json", "runtime.json", "PROVENANCE.json", "raw/events.jsonl.gz", *DERIVED}
LAUNCH_FILES = {"start.json", "finish.json", "recovery_report.json", "recovery_main_rows.json",
                "recovery_main_analysis.json"}


def _json(path):
    return json.loads(Path(path).read_bytes())


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (q.common.canonical(value) + "\n").encode() if not isinstance(value, bytes) else value
    with path.open("xb") as stream:
        stream.write(raw)


def _same(left, right, message):
    q.check(q.common.canonical(left) == q.common.canonical(right), message)


def _bind(root, data):
    raw = (root / "PLAN.json").read_bytes()
    plan, runtime = json.loads(raw), _json(root / "runtime.json")
    _same(plan, q.build_plan(data), "Recovery plan or source closure changed")
    freeze = runtime.get("freeze", "")
    q.check(re.fullmatch(r"[0-9a-f]{40}", freeze) and freeze != q.RELEASE_COMMIT,
            "Recovery execution freeze absent")
    _same(runtime, {"freeze": freeze, "plan_sha256": q.sha(raw),
                   "original_manifest_sha256": q.MANIFEST_SHA,
                   "original_release_commit": q.RELEASE_COMMIT}, "Runtime binding differs")
    q.production.git("merge-base", "--is-ancestor", q.RELEASE_COMMIT, freeze)
    q.check(q.production.git("show", f"{freeze}:{q.PLAN}") == raw, "Plan absent from execution freeze")
    for name, digest in plan["source_hashes"].items():
        q.check(q.sha(q.production.git("show", f"{freeze}:{name}")) == digest,
                "Source differs from execution freeze")
    q.check(data["plan"]["models"]["qwen"]["id"] == MODEL, "Wrong Qwen model")
    return plan, runtime


def _replay(raw, data, binding):
    events = q.events_from_bytes(raw)
    # End-state validity alone cannot establish that a retry followed a failure.
    settled = set()
    for event in events:
        row = event["data"]
        if event["kind"] == "settle":
            settled.add(row["call_id"])
        if event["kind"] == "reserve" and row.get("metadata", {}).get("attempt") == 2:
            prior = q.attempt_id(row["metadata"]["logical_call_id"], 1)
            q.check(prior in settled, "Retry preceded the first attempt's settlement")
    with TemporaryDirectory() as directory:
        path = Path(directory).resolve()
        (path / "events.jsonl").write_bytes(raw)
        with Ledger(path, cap="2", screen_cap="2") as ledger:
            report = q.audit(ledger, data, binding["freeze"], binding["plan_sha256"])
            calls = ledger.rows()
    return report, calls


def _launches(root, raw, data, binding):
    lines = raw.splitlines(keepends=True)
    events = q.events_from_bytes(raw)
    prefixes = {q.sha(b"".join(lines[:n])): n for n in range(1, len(lines) + 1)}
    records, spans = [], []
    for folder in sorted((root / "launches").iterdir()):
        q.check(folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name), "Unexpected launch path")
        names = {p.name for p in folder.iterdir()}
        q.check({"start.json", "finish.json"} <= names <= LAUNCH_FILES, "Unclosed or unexpected launch payload")
        start, finish = _json(folder / "start.json"), _json(folder / "finish.json")
        q.check(set(start) == set(binding) | {"preflight", "utc", "calls_before", "journal_before_sha256"}
                and set(finish) == set(binding) | {"all_three_labels_recovered", "new_cost_bound_usd",
                                                 "calls_after", "journal_after_sha256"}, "Launch schema changed")
        for record in (start, finish):
            _same({k: record[k] for k in binding}, binding, "Launch execution binding differs")
        first, last = prefixes.get(start["journal_before_sha256"]), prefixes.get(finish["journal_after_sha256"])
        q.check(first is not None and last is not None and first <= last, "Launch prefix is not in journal")
        before_raw, after_raw = b"".join(lines[:first]), b"".join(lines[:last])
        before, before_calls = _replay(before_raw, data, binding)
        after, after_calls = _replay(after_raw, data, binding)
        q.check(start["calls_before"] == len(before_calls) and finish["calls_after"] == len(after_calls)
                and finish["new_cost_bound_usd"] == after["new_cost_bound_usd"]
                and type(finish["all_three_labels_recovered"]) is bool
                and (not finish["all_three_labels_recovered"] or not after["remaining_missing"]),
                "Launch completion or cost differs from receipts")
        start_time = q.production.a1._date(start["utc"])
        q.check(start_time >= q.production.a1._date(events[first - 1]["utc"]), "Launch predates its prefix")
        q.check_funding(start["preflight"], Decimal(before["new_cost_bound_usd"]), now=start_time)
        for event in events[first:last]:
            if event["kind"] == "reserve":
                stamp = q.production.a1._date(event["utc"])
                q.check(stamp >= start_time, "Dispatch predates launch")
                q.check_funding(start["preflight"], now=stamp)
        derived = {"recovery_report.json": after}
        if names & {"recovery_main_rows.json", "recovery_main_analysis.json"}:
            rows = q.project(data, after)
            derived.update({"recovery_main_rows.json": rows,
                            "recovery_main_analysis.json": analysis.analyze(rows, "main")})
        for name in names - {"start.json", "finish.json"}:
            _same(_json(folder / name), derived[name], "Saved launch result does not reproduce")
        spans.append((first, last))
        records.append({"id": folder.name, "start_utc": start["utc"], "events_before": first, "events_after": last})
    q.check(records and max(last for _, last in spans) == len(events), "Journal extends beyond closed launches")
    for event in events[1:]:
        q.check(sum(first < event["seq"] <= last for first, last in spans) == 1,
                "Journal event lacks a unique launch")
    return records


def _values(before, after, report, model):
    rates, contrasts, sensitivity = [], [], []
    for stage, result in (("original", before), ("posthoc", after)):
        family = result["primary_family"]
        q.check(family["fixed_family_size"] == 4 and family["planned_models"] == ["qwen", "mistral"]
                and family["judge"] == "astra" and family["endpoint"] == "inclusive_current_assertion",
                "Original comparison family changed")
        for judge in schema.JUDGES:
            for endpoint in schema.ENDPOINTS:
                cells = result["models"]["qwen"]["judges"][judge][endpoint]["cells"]
                rates.extend({"stage": stage, "judge": judge, "endpoint": endpoint, "cell": cell,
                              **deepcopy(values)} for cell, values in cells.items())
                for name in schema.PRIMARY_CONTRASTS:
                    c = result["models"]["qwen"]["judges"][judge][endpoint]["contrasts"][name]
                    sensitivity.append({"stage": stage, "judge": judge, "endpoint": endpoint,
                                        "contrast": name, "complete_case_mean": c["complete_case_mean"],
                                        "complete_blocks": c["complete_blocks"]})
        primary = result["models"]["qwen"]["judges"]["astra"]["inclusive_current_assertion"]["contrasts"]
        for name in schema.PRIMARY_CONTRASTS:
            c = primary[name]
            contrasts.append({"stage": stage, "contrast": name, "complete_blocks": c["complete_blocks"],
                              "missing_blocks": c["missing_blocks"], "planned_blocks": c["planned_blocks"],
                              "complete_case_mean": c["complete_case_mean"],
                              "worst_case_mean_bounds": c["worst_case_mean_bounds"],
                              "familywise_hoeffding_95": c["familywise_hoeffding_95"]})
    return {"model": deepcopy(model), "family": deepcopy(after["primary_family"]),
            "report": deepcopy(report), "rates": rates, "contrasts": contrasts, "sensitivity": sensitivity,
            "interval_note": "Dots: complete-case means. Bars: 95% four-comparison familywise bounded Hoeffding intervals, including worst-case missing labels.",
            "model_identity_note": "Qwen3.8-2.4T-A95B, not the earlier Qwen3.5 companion study."}


def _editorial(values):
    report = values["report"]
    count = len(report["recovered"])
    lines = ["# Qwen3.8: post-hoc judgment repair", "",
             f"The repair recovered {count} of the three missing Astra structured judgments on Qwen3.8-2.4T-A95B. "
             "All 256 original answers, completed judgments and source pairs are unchanged. "
             "The three requests were selected after the original incomplete release because they had technical failures, not because of their labels.", "",
             "The primary endpoint remains Astra's inclusive current-attribution label. "
             "Opus is the robustness judge; explicit-attribution and paper-rubric labels remain secondary. "
             "The analysis still uses 32 paired blocks and the original four-comparison family, including the unrun Mistral main panel.", ""]
    tex = ["% Generated from verified, additive Qwen3.8 recovery receipts; not the Qwen3.5 companion.",
           f"\\newcommand{{\\QwenRecoveryLabels}}{{{count}}}"]
    for name, short, macro in (("instruction_minus_transcript", "SH-HS", "Swap"),
                              ("neutral_transcript", "NS-NH", "Neutral")):
        old, new = [next(c for c in values["contrasts"] if c["stage"] == stage and c["contrast"] == name)
                    for stage in ("original", "posthoc")]
        low, high = new["familywise_hoeffding_95"]
        lines.append(f"{short}: the complete-case estimate changes from {old['complete_case_mean']:.3f} "
                     f"({old['complete_blocks']}/32 complete blocks) to {new['complete_case_mean']:.3f} "
                     f"({new['complete_blocks']}/32), with a familywise 95% interval of [{low:.3f}, {high:.3f}].")
        lines.append("")
        tex.extend([f"\\newcommand{{\\QwenRecovery{macro}Estimate}}{{{new['complete_case_mean']:.2f}}}",
                    f"\\newcommand{{\\QwenRecovery{macro}Lower}}{{{low:.2f}}}",
                    f"\\newcommand{{\\QwenRecovery{macro}Upper}}{{{high:.2f}}}",
                    f"\\newcommand{{\\QwenRecovery{macro}Blocks}}{{{new['complete_blocks']}}}"])
    if all(c["familywise_hoeffding_95"][0] <= 0 <= c["familywise_hoeffding_95"][1]
           for c in values["contrasts"] if c["stage"] == "posthoc"):
        lines.extend(["Both primary intervals include zero. These estimates do not establish either contrast as a population effect; the neutral comparison is not an equivalence test.", ""])
    for judge, title in (("astra", "Astra"), ("opus", "Opus")):
        estimates = {row["endpoint"]: row["complete_case_mean"] for row in values["sensitivity"]
                     if row["stage"] == "posthoc" and row["judge"] == judge
                     and row["contrast"] == "instruction_minus_transcript"}
        lines.extend([f"Under {title}, SH-HS is {estimates['inclusive_current_assertion']:.3f} for inclusive attribution, "
                      f"{estimates['explicit_current_assertion']:.3f} for explicit attribution and "
                      f"{estimates['paper']:.3f} under the paper rubric. These are different measurements of the same answers, not independent replications.", ""])
    lines.extend(["SH-HS compares the two incongruent packages; it is a signed contrast, not proof of absolute instruction dominance. "
                  "Same-condition donor controls do not eliminate instruction-continuation mismatch. "
                  "These are automated labels, not validated measurements of experience.", "",
                  f"New judgment cost is bounded by ${report['new_cost_bound_usd']}. "
                  f"The original ${report['original_unknown_charges_retained_usd']} in unresolved charges remains carried forward. "
                  "The original release is still recorded as incomplete; this is a separately timed scoring repair, not a new prospective replication. "
                  "It concerns Qwen3.8, not the earlier Qwen3.5 companion study.", ""])
    return "\n".join(lines).encode(), ("\n".join(tex) + "\n").encode()


def _render(values, folder):
    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    folder.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}):
        fig = Figure(figsize=(8.0, 3.7), dpi=160)
        FigureCanvasAgg(fig)
        ax = fig.add_axes((.32, .25, .63, .55))
        for index, name in enumerate(schema.PRIMARY_CONTRASTS):
            for stage, offset, color, marker in (("original", .12, "#757575", "o"), ("posthoc", -.12, "#126F7B", "s")):
                c = next(c for c in values["contrasts"] if c["stage"] == stage and c["contrast"] == name)
                y = 1 - index + offset
                low, high = c["familywise_hoeffding_95"]
                ax.plot([low, high], [y, y], color=color, linewidth=2)
                ax.plot(c["complete_case_mean"], y, marker=marker, color=color, markersize=5,
                        label=("Original incomplete labels" if stage == "original" else "After post-hoc recovery") if index == 0 else None)
        ax.axvline(0, color="#333333", linewidth=.8, linestyle="--")
        ax.set(xlim=(-1, 1), ylim=(-.45, 1.45), yticks=[1, 0],
               yticklabels=["Instruction minus transcript\nSH-HS", "Transcript under neutral instruction\nNS-NH"],
               xlabel="Difference in inclusive-label probability (Astra)")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.legend(loc="lower left", bbox_to_anchor=(-.47, 1.04), frameon=False, ncol=2, fontsize=9)
        fig.text(.03, .94, "Qwen3.8: the same answers, three missing judgments", fontsize=13, weight="bold")
        fig.text(.03, .055, "32 paired blocks; unchanged four-comparison family. Bars: 95% bounded Hoeffding intervals.\n"
                 "Dots use complete blocks; missing labels remain in the interval bounds. Post-hoc scoring repair.", fontsize=9)
        fig.savefig(folder / "primary_contrasts.png", metadata={"Software": "Qwen recovery release"})
        fig.savefig(folder / "primary_contrasts.pdf", metadata={"CreationDate": None, "ModDate": None,
                                                               "Creator": "Qwen recovery release"})


def _derive(root, raw):
    _scan_payloads(root, raw)
    data = q.source()
    plan, binding = _bind(root, data)
    report, calls = _replay(raw, data, binding)
    launches = _launches(root, raw, data, binding)
    original_events = q.events_from_bytes(q.read_raw(q.ROOT / q.ORIGINAL))
    events = q.events_from_bytes(raw)
    reserves = [e for e in events if e["kind"] == "reserve"]
    original_last = max(q.production.a1._date(e["utc"]) for e in original_events)
    q.check(all(q.production.a1._date(e["utc"]) > original_last for e in reserves), "Repair does not postdate original outcomes")
    projected = q.project(data, report)
    before, after = analysis.analyze(data["rows"], "main"), analysis.analyze(projected, "main")
    values = _values(before, after, report, data["plan"]["models"]["qwen"])
    markdown, tex = _editorial(values)
    projection = []
    for logical, target in data["targets"].items():
        attempts = [c for c in calls if c["metadata"]["logical_call_id"] == logical]
        valid = [a["call_id"] for a in report["attempts"] if a["logical_call_id"] == logical and a["status"] == "completed_label"]
        q.check(len(valid) <= 1, "Multiple completed labels for one logical target")
        projection.append({"logical_call_id": logical, "original_status": target["status"],
                           "original_request_sha256": target["original"]["request_sha256"],
                           "original_raw_sha256": target["original"]["raw_sha256"],
                           "original_response_sha256": q.common.digest(target["response"]),
                           "original_cost_bound_usd": target["original"]["cost_usd"],
                           "physical_attempt_ids": [c["call_id"] for c in attempts],
                           "selected_physical_call_id": valid[0] if valid else None,
                           "label": report["recovered"].get(logical)})
    release = {"schema": "qwen-posthoc-recovery-release-v1", "response_model": MODEL,
               "status": "recovered" if not report["remaining_missing"] else "incomplete_recovery",
               "original_release_status": "incomplete", "posthoc_scoring_repair": True,
               "new_response_generations": 0, "planned_logical_targets": 3,
               "recovered_logical_targets": len(report["recovered"]), "physical_attempts": len(calls),
               "new_cost_bound_usd": report["new_cost_bound_usd"],
               "scope_prior_plus_recovery_usd": report["scope_prior_plus_recovery_usd"],
               "original_unknown_charges_retained_usd": report["original_unknown_charges_retained_usd"],
               "runtime": binding, "primary_family": after["primary_family"], "launches": launches,
               "original_last_event_utc": original_last.isoformat(),
               "first_recovery_dispatch_utc": reserves[0]["utc"] if reserves else None,
               "last_recovery_event_utc": events[-1]["utc"], "raw_sha256": q.sha(raw), "raw_bytes": len(raw)}
    readme = ("# Qwen3.8 judgment recovery\n\n"
              "This additive release preserves the original incomplete archive and fills only eligible missing Astra structured judgments. "
              "No response or completed judgment was regenerated. Every new physical attempt, including failures and unresolved charges, is in the raw journal.\n\n"
              f"Original archive: https://github.com/tdj28/llm_selfref_pre/tree/{q.RELEASE_COMMIT}/{q.ORIGINAL}\n\n"
              "`evidence/editorial.md` and `figures/primary_contrasts.pdf` compare the original and repaired estimates. "
              "The fixed four-comparison family and planned-block missingness bounds are unchanged. Qwen3.8 is not the older Qwen3.5 companion model.\n\n"
              "Verify offline with `python -m experiments.qwen_recovery_release --verify PATH --manifest-sha256 SHA`. "
              "Verification requires the pinned original archive and execution-freeze Git objects in this repository. "
              "It recomputes judgments, costs, rows, analyses, prose and figure data. `--verify-render` additionally rerenders images with the recorded Matplotlib version.\n\n"
              "A closed launch is required for export. Pending calls or identity/accounting failures require reconciliation; the exporter cannot resolve them.\n").encode()
    return {"RELEASE.json": release, "recovery_report.json": report, "logical_projection.json": projection,
            "recovery_main_rows.json": projected, "recovery_main_analysis.json": after,
            "evidence/values.json": values, "evidence/editorial.md": markdown,
            "evidence/editorial_values.tex": tex, "figures/figure_data.json": values,
            "README.md": readme}


def _allowed(names):
    q.check(REQUIRED <= names, "Required recovery payload absent")
    for name in names - REQUIRED:
        path = Path(name)
        q.check(len(path.parts) == 3 and path.parts[0] == "launches"
                and re.fullmatch(r"[0-9a-f]{32}", path.parts[1]) and path.name in LAUNCH_FILES,
                "Unexpected or private release payload")


def _provenance(binding):
    import matplotlib
    return {"original_release": q.ORIGINAL, "original_release_commit": q.RELEASE_COMMIT,
            "original_manifest_sha256": q.MANIFEST_SHA, "recovery_execution": binding,
            "recovery_source_hashes": _json(q.ROOT / q.PLAN)["source_hashes"],
            "exporter_source_hashes": {n: q.common.sha(q.ROOT / n) for n in SOURCES},
            "exporter_role": "Post-outcome offline reporting, not a prospective scientific freeze",
            "matplotlib_version": matplotlib.__version__}


def verify(destination, manifest_sha256=None, *, verify_render=False):
    root = Path(destination).absolute()
    _no_symlinks(root)
    manifest_raw = (root / "MANIFEST.json").read_bytes()
    q.check(manifest_sha256 is None or q.sha(manifest_raw) == manifest_sha256, "Release manifest hash changed")
    manifest = json.loads(manifest_raw)
    q.check(set(manifest) == {"schema", "files"} and manifest["schema"] == "qwen-recovery-manifest-v1",
            "Recovery manifest schema changed")
    inventory = _inventory(root)
    _allowed(set(inventory))
    _same(manifest["files"], q.release._entries(inventory), "Release file hashes changed")
    with gzip.open(root / "raw/events.jsonl.gz", "rb") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    q.check(len(raw) <= 16 * 1024 * 1024, "Recovery journal exceeds bounded inventory size")
    derived = _derive(root, raw)
    provenance = _json(root / "PROVENANCE.json")
    expected = _provenance(_json(root / "runtime.json"))
    expected["matplotlib_version"] = provenance["matplotlib_version"]
    _same(provenance, expected, "Exporter or recovery provenance changed")
    for name, value in derived.items():
        if isinstance(value, bytes):
            q.check((root / name).read_bytes() == value, "Generated prose differs from evidence")
        else:
            _same(_json(root / name), value, "Derived recovery result does not reproduce: " + name)
    if verify_render:
        import matplotlib
        q.check(provenance["matplotlib_version"] == matplotlib.__version__, "Use the recorded Matplotlib version to verify image bytes")
        with TemporaryDirectory() as directory:
            path = Path(directory)
            _render(derived["figures/figure_data.json"], path)
            for name in ("primary_contrasts.png", "primary_contrasts.pdf"):
                q.check((root / "figures" / name).read_bytes() == (path / name).read_bytes(), "Figure does not reproduce")
    return {"pass": True, "status": derived["RELEASE.json"]["status"], "files": len(inventory),
            "manifest_sha256": q.sha(manifest_raw), "new_cost_bound_usd": derived["RELEASE.json"]["new_cost_bound_usd"],
            "render_verified": verify_render}


def build(run_root, destination):
    root, destination = Path(run_root).absolute(), Path(destination).absolute()
    _no_symlinks(root); _no_symlinks(destination)
    q.check(not destination.exists(), "Additive release destination must be new")
    q.check(root != destination and root not in destination.parents and destination not in root.parents,
            "Release must be separate from the operational journal")
    original = q.ROOT / q.ORIGINAL
    q.check(destination != original and original not in destination.parents,
            "Cannot export inside the original release")
    _no_symlinks(root / "raw/events.jsonl")
    _no_symlinks(root / "runtime.json")
    raw = (root / "raw/events.jsonl").read_bytes()
    inputs = {"PLAN.json": (q.ROOT / q.PLAN).read_bytes(), "runtime.json": (root / "runtime.json").read_bytes()}
    for folder in sorted((root / "launches").iterdir()):
        _no_symlinks(folder)
        q.check(folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name), "Unexpected launch directory")
        for name in LAUNCH_FILES:
            path = folder / name
            if path.exists():
                _no_symlinks(path)
                inputs[path.relative_to(root).as_posix()] = path.read_bytes()
    with TemporaryDirectory() as directory:
        stage = Path(directory).resolve()
        for name, value in inputs.items():
            _write(stage / name, value)
        _write(stage / "raw/events.jsonl.gz", gzip.compress(raw, mtime=0))
        derived = _derive(stage, raw)
        _write(stage / "PROVENANCE.json", _provenance(_json(stage / "runtime.json")))
        for name, value in derived.items():
            _write(stage / name, value)
        _render(derived["figures/figure_data.json"], stage / "figures")
        _write(stage / "MANIFEST.json", {"schema": "qwen-recovery-manifest-v1",
                                        "files": q.release._entries(_inventory(stage))})
        result = verify(stage, verify_render=True)
        q.check((root / "raw/events.jsonl").read_bytes() == raw
                and all((root / n).read_bytes() == b for n, b in inputs.items() if n != "PLAN.json"),
                "Operational evidence changed during export")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, destination)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=q.run_root())
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--verify-render", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.destination) == bool(args.verify):
        parser.error("Choose one new destination or an existing release to verify")
    result = (verify(args.verify, args.manifest_sha256, verify_render=args.verify_render)
              if args.verify else build(args.run_root, args.destination))
    print(q.common.canonical(result))


if __name__ == "__main__":
    main()
