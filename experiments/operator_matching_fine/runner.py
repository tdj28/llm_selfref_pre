"""Fine-ladder runner: the parent's receipted two-turn trial path over 100 grid and 5 zero rows.

`row`, `trial`, `trial_row`, `messages`, `intervention` and `assistant_spans` are the parent's
(imported, not copied). Only `execute` differs: no conditional steps, no skips, a descriptive
`selection.json` with empty selections, this package's audit/analysis and a DONE marker with
`not_selected` fixed at zero.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from experiments.operator_matching.runner import (  # noqa: F401  re-exported for tests and audit
    Study as ParentStudy, assistant_spans, intervention, messages, publish,
)
from experiments.sae_assay_diagnostic.runner import write_once
from . import analysis, protocol


class Study(ParentStudy):
    def __init__(self, plan, *args, **kwargs):
        if any(r["step"] not in analysis.STEPS for r in plan["rows"]):
            raise ValueError("Fine ladder plans hold grid and zero rows only")
        super().__init__(plan, *args, **kwargs)

    def execute(self):
        b = self.model()
        self.row("qualification-live", lambda: {"id": "qualification-live", "result": b.qualify()})
        self.barrier("qualification")
        grid = [r for r in self.plan["rows"] if r["step"] == "grid"]
        zero = [r for r in self.plan["rows"] if r["step"] == "zero"]
        for i, spec in enumerate(grid + zero):
            self.trial_row(spec)
            if i == 4:
                self.barrier("first-five")
        results = [self.result(r["id"]) for r in grid + zero]
        median = protocol.add_zero_nll_median(results)
        table = protocol.step_one_table(results, analysis.reference_of(self.plan), median)
        publish(self.out / "selection.json", analysis.selection(table, median, self.plan_hash))
        if self.not_selected():
            raise ValueError("Fine ladder recorded a not_selected event; it has no selection stage")
        publish(self.out / "audit.json", analysis.audit(self.out, self.plan, partial=False,
                                                        plan_sha256=self.plan_hash, freeze=self.freeze))
        analysis.analyze(self.out, self.out / "analysis", render=False)
        try:  # the context file is checked against the plan's input hash before any plotting import
            analysis.render(self.out, self.out / "analysis", protocol.ROOT / protocol.MAIN_RELEASE,
                            self.plan["input_hashes"][protocol.MAIN_RELEASE])
        except ImportError as exc:  # tables and audit are complete; the figure is reproducible from them
            publish(self.out / "analysis/figures_skipped.json", {
                "error_type": type(exc).__name__, "module": getattr(exc, "name", None),
                "regenerate": "python -m experiments.operator_matching_fine.analysis --plan " + protocol.PLAN_PATH
                              + " --root <retrieved> --out <retrieved>/analysis"})
        publish(self.out / "DONE-all.json", {"pass": True, "plan_sha256": self.plan_hash,
                "freeze_commit": self.freeze, "rows": len(self.completed), "not_selected": 0})


def main():
    p = argparse.ArgumentParser()
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        p.add_argument("--" + arg, required=True)
    a = p.parse_args()
    study = None
    try:
        study = Study(protocol.load_plan(a.plan, a.freeze), a.plan, a.freeze, a.out, a.deadline_utc, a.cache)
        study.execute()
    except Exception as exc:
        write_once(Path(a.out) / "failed.json", {"error_type": type(exc).__name__,
                   "plan_sha256": protocol.sha(a.plan), "completed": 0 if study is None else len(study.completed),
                   "constructed": study is not None})
        raise
    finally:
        if study is not None and study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
