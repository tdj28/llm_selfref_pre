"""Twelve untreated rows first, then unchanged conditional calibration and main."""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics

from experiments.berg_dose_ladder.runner import Study as LadderStudy
from experiments.sae_assay_diagnostic.runner import write_once
from .backend import Backend
from . import analysis, protocol


class Study(LadderStudy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.factory = Backend

    def execute(self):
        self.model()
        self.row("qualification-live", self.qualification)
        analysis.audit(self.out, self.plan, settled=True)
        self.barrier("qualification")
        zeros = analysis.zero_specs(self.plan)
        self.collect(zeros, first_five=False)
        gate = analysis.zero_screen([self.result(s["id"]) for s in zeros], self.plan)
        write_once(self.out/"zero_screen.json", gate)
        self.ledger.bind("zero-screen", {"kind": "zero_screen", "pass": gate["pass"],
                                        "sha256": protocol.sha(self.out/"zero_screen.json")})
        analysis.audit(self.out, self.plan, settled=True)
        selection = None
        if gate["pass"]:
            calibration = [s for s in self.plan["rows"] if s["phase"] == "calibration"]
            self.collect([s for s in calibration if s["family"] != "zero"], first_five=True)
            rows = [self.result(s["id"]) for s in calibration]
            selection = analysis.calibration_selection(rows, self.plan)
            write_once(self.out/"selection.json", selection)
            self.ledger.bind("selection", {"kind": "selection", "selected_dose": selection["selected_dose"],
                                          "sha256": protocol.sha(self.out/"selection.json")})
            if selection["pass"]:
                selected = [s for s in protocol.selected_rows(self.plan, selection["selected_dose"])
                            if s["phase"] == "main"]
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
        analysis.analyze(self.out, self.out/"analysis")
        write_once(self.out/"DONE-all.json", {"pass": True, "schema": "dose_exposure_completion_v1",
            "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "generations": len(self.completed)-1, "zero_screen_pass": gate["pass"],
            "main_run": bool(selection and selection["pass"]),
            "selected_dose": selection["selected_dose"] if selection else None,
            "stop_reason": None if gate["pass"] else "zero_screen_failed"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        parser.add_argument("--"+arg, required=True)
    args = parser.parse_args()
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
