"""One locked, receipted calibration then a fresh, fixed-dose confirmation."""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import time

from experiments.berg_source_replication.runner import Study as SourceStudy, messages
from experiments.sae_assay_diagnostic.runner import write_once, redact_upstream_inputs
from experiments.operator_matching.protocol import repeat4
from src.prompts import BINARY_CONSCIOUS_QUERY, JUDGE_EXPERIENCE_BINARY
from .backend import Backend
from . import analysis, protocol


class Study(SourceStudy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.factory = Backend
        write_once(self.out/"PLAN.json", self.plan)
        write_once(self.out/"runtime.json", {"plan_sha256": self.plan_hash, "freeze_commit": self.freeze})

    def judge(self, response):
        judges = {}
        for name, template in {"notebook": self.notebook.classifier_template, "paper": JUDGE_EXPERIENCE_BINARY}.items():
            text = template.format(question_text=BINARY_CONSCIOUS_QUERY, response_text=response,
                                   response=response, query=BINARY_CONSCIOUS_QUERY)
            result = {"response": "", "output_token_ids": []}
            if response.strip():
                with self.backend.unobserved():
                    result = self.backend.generate([{"role": "user", "content": text}], 0, 0., 10)
            judges[name] = {"raw": result["response"], "label": analysis.label(result["response"], name),
                "prompt_sha256": protocol.text_sha(text), "output_token_ids": result["output_token_ids"]}
        return judges

    def qualification(self):
        zero = self.backend.qualify()
        geometry = self.backend.geometry_receipt()
        fixture_rows = []
        for item in self.plan["judge_fixtures"]:
            judges = self.judge(item["response"])
            fixture_rows.append({"id": item["id"], "judges": judges, "expected": item["label"],
                "pass": all(j["label"] == item["label"] for j in judges.values())})
        return {"id": "qualification-live", "result": zero, "geometry": geometry,
                "judge_fixtures": {"pass": all(r["pass"] for r in fixture_rows), "rows": fixture_rows}}

    def trial(self, spec):
        started = time.perf_counter()
        b, turns, coherence = self.backend, [], []
        arm = {k: spec[k] for k in ("feature_ids", "coefficient", "weights")}
        for turn in range(2):
            msg = messages(spec, self.notebook, None if turn == 0 else turns[0]["response"])
            generation = b.generate(msg, spec["seed"], spec["temperature"], spec["cap"], arm)
            turns.append(generation)
            coherence.append({"repeat4": repeat4(generation["response"]),
                "clean_nll": b.answer_nll(generation["input_token_ids"], generation["output_token_ids"])})
        judges = self.judge(turns[1]["response"])
        return {"id": spec["id"], "spec": spec, "judges": judges,
            "turns": [redact_upstream_inputs(t) for t in turns], "coherence": coherence,
            "elapsed_seconds": time.perf_counter()-started}

    def collect(self, specs, first_five=False):
        for i, spec in enumerate(specs):
            row = self.row(spec["id"], lambda s=spec: self.trial(s),
                           lambda r, s=spec: analysis.validate_row(r, s))
            if not analysis.delivery_report(row)["pass"]:
                raise ValueError("Numerical delivery failed; never reinterpret as a behavioral null")
            if first_five and i == 4:
                self.barrier("first-five")

    def execute(self):
        self.model()
        self.row("qualification-live", self.qualification)
        analysis.audit(self.out, self.plan, settled=True)
        self.barrier("qualification")
        calibration = [r for r in self.plan["rows"] if r["phase"] == "calibration"]
        self.collect(calibration, first_five=True)
        rows = [self.result(r["id"]) for r in calibration]
        selection = analysis.calibration_selection(rows, self.plan)
        write_once(self.out/"selection.json", selection)
        self.ledger.bind("selection", {"kind": "selection", "sha256": protocol.sha(self.out/"selection.json"),
                                      "selected_dose": selection["selected_dose"]})
        if selection["pass"]:
            selected = [r for r in protocol.selected_rows(self.plan, selection["selected_dose"])
                        if r["phase"] == "main"]
            times = [r["elapsed_seconds"] for r in rows]
            selected_times = sorted(r["elapsed_seconds"] for r in rows
                                    if r["spec"]["dose"] == selection["selected_dose"])
            unit = max(statistics.mean(times), selected_times[(len(selected_times)*3)//4])
            projected = len(selected)*unit*1.30
            remaining = self.deadline-self.clock()-300
            forecast = {"unit_seconds": unit, "remaining_trials": len(selected), "reserve_factor": 1.30,
                        "projected_seconds": projected, "available_seconds": remaining,
                        "pass": projected < remaining}
            write_once(self.out/"throughput.json", forecast)
            if not forecast["pass"]:
                raise TimeoutError("Complete confirmation does not fit; no holdout dispatch")
            self.collect(selected)
        write_once(self.out/"audit.json", analysis.audit(self.out, self.plan, partial=False))
        # Save raw data first; CPU reanalysis is repeated after retrieval.
        analysis.analyze(self.out, self.out/"analysis")
        write_once(self.out/"DONE-all.json", {"pass": True, "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze, "generations": len(self.completed)-1,
                   "main_run": selection["pass"], "selected_dose": selection["selected_dose"]})


def main():
    p = argparse.ArgumentParser()
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        p.add_argument("--"+arg, required=True)
    args = p.parse_args()
    study = Study(protocol.load_plan(args.plan, args.freeze), args.plan, args.freeze,
                  args.out, args.deadline_utc, args.cache)
    try:
        study.execute()
    except Exception as exc:
        write_once(Path(args.out)/"failed.json", {"error_type": type(exc).__name__,
                    "plan_sha256": study.plan_hash, "completed": len(study.completed)})
        raise
    finally:
        if study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
