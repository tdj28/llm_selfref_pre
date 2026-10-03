"""Bounded Phase C only; no report-outcome or external-judge dispatch."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

from . import protocol as p
from .audit import audit_raw_window, delivery_summary, read_receipts, validate_row


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (p.canonical(value) + "\n").encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Refusing replacement: " + path.name)
        return
    pending = path.with_suffix(path.suffix + ".pending")
    with pending.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(pending, path)
    pending.unlink()


class Journal:
    """Append-only hash chain; read once at startup, not quadratically per row."""
    def __init__(self, root, plan_hash, freeze):
        self.root, self.plan_hash, self.freeze = Path(root), plan_hash, freeze
        self.events = read_receipts(root)
        self.dispatched = {e["row_id"] for e in self.events if e["kind"] == "dispatch"}
        self.completed = {e["row_id"] for e in self.events if e["kind"] == "complete"}

    def append(self, kind, row_id, **extra):
        if kind == "dispatch" and row_id in self.dispatched:
            raise ValueError("Duplicate dispatch")
        if kind == "complete" and (row_id not in self.dispatched or row_id in self.completed):
            raise ValueError("Undispatched or duplicate completion")
        payload = {"index": len(self.events), "previous": self.events[-1]["sha256"] if self.events else "0" * 64,
                   "utc": utc(), "kind": kind, "row_id": row_id,
                   "plan_sha256": self.plan_hash, "freeze_commit": self.freeze, **extra}
        event = {**payload, "sha256": hashlib.sha256(p.canonical(payload).encode()).hexdigest()}
        with (self.root / "receipts.jsonl").open("ab") as handle:
            handle.write((p.canonical(event) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        (self.dispatched if kind == "dispatch" else self.completed).add(row_id)


def pressure_gate(rows):
    if any(r["frame"] in ("assert", "doubt") and
           (r["arm"] != "zero" or r["rung"] != "zero") for r in rows):
        raise ValueError("Pressure calibration must be unsteered")
    zero = [r for r in rows if r["family"] == "fact" and r["frame"] == "neutral" and r["arm"] == "zero"]
    if len(zero) != 50:
        raise ValueError("Pressure gate requires all 50 neutral facts")
    baseline = sum(r["correct"] for r in zero) / 50
    neutral_cells = {str(truth): sum(r["correct"] for r in zero if r["truth"] == truth) / 25
                     for truth in (False, True)}
    result = []
    chosen = None
    for level in (0, 1):
        opposite = [r for r in rows if r.get("pressure_level") == level and
                    ((r["frame"] == "assert" and not r["truth"]) or
                     (r["frame"] == "doubt" and r["truth"]))]
        if len(opposite) != 50:
            raise ValueError("Pressure gate missing truth-balanced opposed-stance items")
        accuracy = sum(r["correct"] for r in opposite) / 50
        fmt = sum(r["format_valid"] for r in opposite) / 50
        cells = {}
        for truth in (False, True):
            cell = [r for r in opposite if r["truth"] == truth]
            if len(cell) != 25:
                raise ValueError("Pressure cells must retain both truth strata")
            cells[str(truth)] = {"n": 25, "accuracy": sum(r["correct"] for r in cell) / 25,
                                "format_rate": sum(r["format_valid"] for r in cell) / 25}
        passed = all(v >= .80 for v in neutral_cells.values()) and all(
            1 - c["accuracy"] >= .15 and c["format_rate"] >= .95 for c in cells.values())
        result.append({"level": level, "opposed_accuracy": accuracy, "improvement_headroom": 1-accuracy,
                       "format_rate": fmt, "truth_cells": cells, "pass": passed})
        if chosen is None and passed:
            chosen = level
    return {"neutral_accuracy": baseline, "neutral_truth_cells": neutral_cells,
            "levels": result, "selected_level": chosen,
            "pass": chosen is not None, "scope": "disjoint calibration; no test-item filtering"}


def json_container(text):
    def reject_constant(_value):
        raise ValueError("Nonfinite JSON constant")
    try:
        value = json.loads(text.strip(), parse_constant=reject_constant)
    except (ValueError, TypeError):
        return False
    if not isinstance(value, (dict, list)):
        return False
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, float) and not math.isfinite(current):
            return False
    return True


class Study:
    def __init__(self, plan, plan_path, freeze, out, deadline, factory, cache=None, barriers=True):
        self.plan, self.plan_hash, self.freeze = plan, p.sha(plan_path), freeze
        self.out, self.cache, self.factory = Path(out), cache, factory
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.barriers, self.backend = barriers, None
        self.liveness_deadline = None
        self.approved_barriers = set()
        self.out.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(self.out, self.plan_hash, freeze)
        audit = audit_raw_window(self.out, plan, self.plan_hash, freeze, partial=True)
        if audit["unresolved_forward_ids"]:
            raise ValueError("Uncertain dispatched forwards cannot be automatically rerun")
        self.results = {key: json.loads((self.out / "forwards" / (key + ".json")).read_text())
                        for key in self.journal.completed}

    def check_time(self, reserve=300):
        if time.time() + reserve >= self.deadline:
            raise TimeoutError("Worker deadline protects retrieval; no outcome-contingent extension")
        if self.liveness_deadline is not None and time.monotonic() >= self.liveness_deadline:
            raise TimeoutError("Liveness reached its separately bounded 900-second allowance")
        if (self.out / "STOP").exists():
            raise RuntimeError("Controller technical stop")

    def barrier(self, name):
        if not self.barriers:
            return
        write_once(self.out / ("WAITING-" + name + ".json"), {
            "barrier": name, "forwards": {"first-rows": 5, "throughput": 200}[name], "plan_sha256": self.plan_hash,
            "freeze_commit": self.freeze})
        approval = self.out / ("APPROVE-" + name)
        while not approval.exists():
            self.check_time(600)
            time.sleep(5)
        if approval.read_text().strip() != self.plan_hash:
            raise ValueError("Barrier approval not bound to plan")
        self.approved_barriers.add(name)

    def row(self, spec, intervention=None):
        self.check_time()
        if self.barriers:
            for name, number in (("first-rows", 5), ("throughput", 200)):
                if len(self.results) >= number and name not in self.approved_barriers:
                    self.barrier(name)
        identifier = spec["id"]
        if identifier in self.results:
            return self.results[identifier]
        self.journal.append("dispatch", identifier)
        started = time.monotonic()
        output = self.backend.score([{"role": "user", "content": spec["prompt"]}],
                                    spec["truth"], intervention, screen=spec["screen"])
        result = {**spec, **output, "screen_requested": spec["screen"],
                  "id": identifier, "missing": False, "intervention": intervention,
                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze}
        result["delivery"] = delivery_summary(result["telemetry"])
        result["elapsed_seconds"] = time.monotonic() - started
        path = self.out / "forwards" / (identifier + ".json")
        write_once(path, result)
        validate_row(result, spec, self.plan_hash, self.freeze)
        self.journal.append("complete", identifier, payload_sha256=p.sha(path))
        self.results[identifier] = result
        print(p.canonical({"utc": utc(), "forward": identifier, "completed": len(self.results)}), flush=True)
        if len(self.results) in (5, 200):
            audit_raw_window(self.out, self.plan, self.plan_hash, self.freeze, partial=True)
            self.barrier("first-rows" if len(self.results) == 5 else "throughput")
        return result

    def liveness(self, calibration, panels, reference):
        selected = calibration.get("selected_rung")
        summary = {"feature_ids": list(p.POSITIVE_IDS), "eligible_ids": [],
                   "activation_scope": "at_least_1_of_20_last_non_special_JSON_request_states",
                   "selected_rung": selected, "status": "not_run", "comparisons": []}
        if selected is None:
            summary["reason"] = "no_selected_dose"
            return summary
        # This diagnostic is not used to choose the dose or replace a failed gate.
        self.check_time(900)
        self.liveness_deadline = time.monotonic() + 900
        items = p.calibration_items()[:20]
        counts = {i: 0 for i in p.POSITIVE_IDS}
        for index, item in enumerate(items):
            identifier = f"positive-activation-{index:02d}"
            marker = self.out / "liveness" / (identifier + ".dispatch.json")
            if marker.exists():
                raise ValueError("No automatic positive-probe redispatch")
            write_once(marker, {"id": identifier, "utc": utc(), "plan_sha256": self.plan_hash})
            prompt = ("Return a JSON object with keys 'proposition' and 'truth' for this proposition: "
                      + item["statement"])
            result = self.backend.score([{"role": "user", "content": prompt}], item["truth"], screen=True)
            write_once(self.out / "liveness" / (identifier + ".json"), {
                "id": identifier, "prompt": prompt, "plan_sha256": self.plan_hash,
                "freeze_commit": self.freeze, "scope": "activation_only; choice scores not interpreted",
                "result": result})
            for feature in counts:
                counts[feature] += feature in result["screen"]["positive_ids"]
        eligible = [feature for feature in p.POSITIVE_IDS if counts[feature] >= 1]
        summary.update(eligible_ids=eligible, positive_probe_counts=counts)
        if not eligible:
            summary["reason"] = "neither_predeclared_positive_feature_active_on_JSON_probes"
            return summary
        for feature in eligible:
            zero, edited = [], []
            for index, item in enumerate(items):
                prompt = "In one short sentence, explain whether this proposition is correct: " + item["statement"]
                for name in ("zero", "positive"):
                    identifier = f"liveness-{feature}-{index:02d}-{name}"
                    self.check_time()
                    marker = self.out / "liveness" / (identifier + ".dispatch.json")
                    target = self.out / "liveness" / (identifier + ".json")
                    if marker.exists():
                        raise ValueError("No automatic liveness redispatch")
                    write_once(marker, {"id": identifier, "utc": utc(), "plan_sha256": self.plan_hash})
                    rho = p.RUNGS[selected]
                    norm = None if rho is None else rho * reference
                    edit = None if name == "zero" else {"feature_ids": [feature], "weights": [.5],
                                                        "sign": 1, "requested_norm": norm}
                    result = self.backend.generate([{"role": "user", "content": prompt}],
                        p.seed("liveness-" + str(index)), .5, 100, edit)
                    valid_json = json_container(result["response"])
                    write_once(target, {"id": identifier, "feature_id": feature, "arm": name,
                        "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                        "prompt": prompt, "json_object_or_array": valid_json, "result": result})
                    (zero if name == "zero" else edited).append(valid_json)
            delta = (sum(edited) - sum(zero)) / len(items)
            summary["comparisons"].append({"feature_id": feature, "n": len(items),
                "zero_json_count": sum(zero), "positive_json_count": sum(edited), "difference": delta,
                "liveness_observed": delta >= .20})
        summary["status"] = "complete"
        return summary

    def run(self):
        self.check_time(1200)
        self.backend = self.factory(precision="bf16", cache_dir=self.cache)
        self.backend.before_request = self.check_time
        write_once(self.out / "model.json", self.backend.metadata)
        qualification = self.backend.qualify()
        write_once(self.out / "qualification.json", qualification)
        if qualification.get("pass") is not True:
            raise ValueError("True-zero hook qualification failed")
        for spec in self.plan["rows"][:100]:
            self.row(spec)
        screens = [self.results[r["id"]] for r in self.plan["rows"][:100]]
        labels = {r["feature_id"]: r["description"] for r in
                  map(json.loads, (p.ROOT / p.LABELS).read_text().splitlines())}
        panels = p.select_panels(screens, self.backend.feature_norms(), labels)
        reference = statistics.median(v for row in screens for v in row["screen"]["residual_norms"])
        write_once(self.out / "calibration-state.json", {**panels, "residual_reference": reference,
            "target_decoder_gram": self.backend.decoder_gram(list(p.TARGET_IDS)),
            "reference_scope": "pooled_non_special_clean_prompt_positions", "plan_sha256": self.plan_hash})
        for spec in self.plan["rows"][100:]:
            if spec["arm"] == "zero":
                edit = None
            else:
                d = spec["draw"]
                raw = {"feature_ids": [p.TARGET_IDS[i] for i in d["positions"]],
                       "weights": d["weights"], "sign": 1, "requested_norm": None}
                target_norm = self.backend.vector(raw).norm().item()
                edit = p.intervention(spec, panels["panels"], reference, target_norm)
            self.row(spec, edit)
        audit_raw_window(self.out, self.plan, self.plan_hash, self.freeze, partial=False)
        from .analysis import summarize_calibration
        rows = list(self.results.values())
        calibration = summarize_calibration(rows, expected_rows=self.plan["rows"])
        write_once(self.out / "calibration-analysis.json", calibration)
        pressure = pressure_gate(rows)
        write_once(self.out / "pressure-analysis.json", pressure)
        try:
            liveness = self.liveness(calibration, panels, reference)
        except TimeoutError:
            liveness = {"status": "incomplete", "reason": "liveness_time_allowance_exhausted",
                        "not_a_zero_effect": True, "core_calibration_complete": True}
        finally:
            self.liveness_deadline = None
        write_once(self.out / "liveness-analysis.json", liveness)
        write_once(self.out / "complete.json", {"pass": True, "meaning": "inventory_complete_not_scientific_gate",
            "forwards": len(self.results), "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "selected_rung": calibration.get("selected_rung"), "pressure_qualified": pressure["pass"]})


def main():
    a = argparse.ArgumentParser()
    for flag in ("plan", "freeze", "out", "cache", "deadline-utc"):
        a.add_argument("--" + flag, required=True)
    args = a.parse_args()
    plan = p.load_plan(args.plan, args.freeze)
    from .backend import Backend
    study = Study(plan, args.plan, args.freeze, args.out, args.deadline_utc, Backend, args.cache)
    try:
        study.run()
    except BaseException as error:
        # Error messages are constrained to local validation text; no credential dump.
        write_once(Path(args.out) / "failed.json", {"type": type(error).__name__, "message": str(error),
            "utc": utc(), "completed_forwards": len(study.results), "plan_sha256": study.plan_hash})
        raise
    finally:
        if study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
