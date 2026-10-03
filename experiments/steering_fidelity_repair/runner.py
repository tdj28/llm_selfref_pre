"""Execute only the frozen fresh instruments; all report-study gates stay closed."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from . import protocol as p
from .pressure_gate import discovery_gate, validation_gate
from experiments.steering_fidelity.runner import Journal, utc, write_once
from experiments.steering_fidelity.audit import delivery_summary


class Study:
    def __init__(self, plan, plan_path, freeze, out, deadline, factory, cache=None, barriers=True):
        self.plan, self.plan_hash, self.freeze = plan, p.sha(plan_path), freeze
        self.out, self.cache, self.factory = Path(out), cache, factory
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.backend, self.barriers = None, barriers
        self.results, self.approved_barriers = {}, set()
        self.liveness_deadline = None
        self.out.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(self.out, self.plan_hash, freeze)
        if self.journal.events or any((self.out / "forwards").glob("*.json")):
            raise ValueError("Repair pilot cannot automatically redispatch or resume model outcomes")

    def check_time(self, reserve=300):
        if time.time() + reserve >= self.deadline:
            raise TimeoutError("Worker deadline protects retrieval; no result-dependent extension")
        if self.liveness_deadline is not None and time.monotonic() >= self.liveness_deadline:
            raise TimeoutError("JSON branch reached its fixed 900-second allowance")
        if (self.out / "STOP").exists():
            raise RuntimeError("Controller technical stop")

    def barrier(self, name):
        if not self.barriers or name in self.approved_barriers:
            return
        write_once(self.out / ("WAITING-" + name + ".json"), {
            "barrier": name, "forwards": {"first-rows": 5, "throughput": 20}[name],
            "plan_sha256": self.plan_hash, "freeze_commit": self.freeze})
        approval = self.out / ("APPROVE-" + name)
        while not approval.exists():
            self.check_time(600)
            time.sleep(5)
        if approval.read_text().strip() != self.plan_hash:
            raise ValueError("Barrier approval not bound to plan")
        self.approved_barriers.add(name)

    def decision(self, name, value):
        record = {"decision": value, "plan_sha256": self.plan_hash,
                  "freeze_commit": self.freeze,
                  "after_receipt_sha256": self.journal.events[-1]["sha256"],
                  "stage_t_authorized": False}
        write_once(self.out / (name + "-decision.json"), record)
        return value

    def row(self, spec):
        from .audit import validate_row, audit_raw_window
        self.check_time()
        if spec["id"] in self.results:
            raise ValueError("Duplicate pilot row")
        edit = p.intervention(spec)
        self.journal.append("dispatch", spec["id"])
        started = time.monotonic()
        messages = [{"role": "user", "content": spec["prompt"]}]
        if spec["task"] == "choice":
            result = self.backend.score(messages, spec["truth"], edit, screen=False)
            output = {**result, "delivery": delivery_summary(result["telemetry"])}
        elif spec["task"] == "teacher":
            from .activation_probe import teacher_probe
            output = {"probe": teacher_probe(self.backend, messages, spec["continuation"], p.POSITIVE_IDS)}
        elif spec["task"] == "generation":
            from .activation_probe import generated_probe
            output = generated_probe(self.backend, messages, p.POSITIVE_IDS,
                seed=spec["seed"], temperature=spec["temperature"],
                max_new_tokens=spec["max_new_tokens"], intervention=edit)
        else:
            raise ValueError("Unknown pilot task")
        row = {**spec, **output, "missing": False, "intervention": edit,
               "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
               "elapsed_seconds": time.monotonic() - started}
        path = self.out / "forwards" / (spec["id"] + ".json")
        # Preserve even an invalid returned payload before failing its structural check.
        write_once(path, row)
        validate_row(row, spec, self.plan_hash, self.freeze, self.plan)
        self.journal.append("complete", spec["id"], payload_sha256=p.sha(path))
        self.results[spec["id"]] = row
        print(p.canonical({"utc": utc(), "forward": spec["id"], "completed": len(self.results)}), flush=True)
        if len(self.results) in (5, 20):
            audit_raw_window(self.out, self.plan, self.plan_hash, self.freeze, partial=True)
            self.barrier("first-rows" if len(self.results) == 5 else "throughput")
        return row

    def collect(self, specs):
        return [self.row(s) for s in specs]

    def run(self):
        from .analysis import singleton_gate
        from .liveness import summarize
        from .audit import audit_raw_window
        self.check_time(1200)
        self.backend = self.factory(precision="bf16", cache_dir=self.cache)
        self.backend.before_request = self.check_time
        write_once(self.out / "model.json", self.backend.metadata)
        qualification = self.backend.qualify()
        write_once(self.out / "qualification.json", qualification)
        if qualification.get("pass") is not True:
            raise ValueError("True-zero hook qualification failed")
        discovery = self.collect(self.plan["discovery_rows"])
        selected = self.decision("discovery", discovery_gate(discovery))["selected"]
        neutral = self.collect(self.plan["validation_neutral_rows"])
        if selected is None:
            validation = {"status": "not_run", "reason": "no_discovery_candidate_passed",
                          "pass": False, "stage_t_authorized": False}
        else:
            pressured = self.collect(self.plan["validation_rows"][selected])
            validation = validation_gate(neutral + pressured, selected)
        self.decision("validation", validation)
        edited = self.collect(self.plan["singleton_rows"])
        singleton = self.decision("singleton", singleton_gate(neutral + edited))
        self.check_time(900)
        self.liveness_deadline = time.monotonic() + 900
        teacher = self.collect(self.plan["teacher_rows"])
        generated = self.collect(self.plan["generation_rows"]) if singleton["pass"] else []
        liveness = self.decision("liveness", summarize(teacher, generated, singleton_pass=singleton["pass"]))
        self.liveness_deadline = None
        audit = audit_raw_window(self.out, self.plan, self.plan_hash, self.freeze, partial=False)
        write_once(self.out / "audit.json", audit)
        write_once(self.out / "complete.json", {
            "pass": True, "meaning": "conditional_inventory_complete_not_scientific_gate",
            "forwards": len(self.results), "plan_sha256": self.plan_hash,
            "freeze_commit": self.freeze, "pressure_pass": validation["pass"],
            "singleton_pass": singleton["pass"], "liveness_pass": liveness["pass"],
            "stage_t_authorized": False, "e_only_fallback": False})


def main():
    parser = argparse.ArgumentParser()
    for flag in ("plan", "freeze", "out", "cache", "deadline-utc"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    plan = p.load_plan(args.plan, args.freeze)
    from experiments.steering_fidelity.backend import Backend
    study = Study(plan, args.plan, args.freeze, args.out, args.deadline_utc, Backend, args.cache)
    try:
        study.run()
    except BaseException as error:
        write_once(Path(args.out) / "failed.json", {"type": type(error).__name__,
            "message": str(error), "utc": utc(), "completed_forwards": len(study.results),
            "plan_sha256": study.plan_hash, "freeze_commit": args.freeze})
        raise
    finally:
        if study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
