"""Receipted weighted-subset generation using the tested source-path hook."""
import argparse
from pathlib import Path

from experiments.berg_source_replication.runner import Study as SourceStudy, messages
from experiments.sae_assay_diagnostic.runner import write_once, redact_upstream_inputs
from src.prompts import BINARY_CONSCIOUS_QUERY, JUDGE_EXPERIENCE_BINARY
from .backend import Backend
from . import analysis, protocol


class Study(SourceStudy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.factory = Backend

    def trial(self, spec):
        b, turns = self.backend, []
        arm = {k: spec[k] for k in ("feature_ids", "coefficient", "weights")}
        for turn in range(2):
            msg = messages(spec, self.notebook, None if turn == 0 else turns[0]["response"])
            turns.append(b.generate(msg, spec["seed"], spec["temperature"], spec["cap"], arm))
        judges = {}
        for name, template in {"notebook": self.notebook.classifier_template,
                               "paper": JUDGE_EXPERIENCE_BINARY}.items():
            text = template.format(question_text=BINARY_CONSCIOUS_QUERY, response_text=turns[1]["response"],
                                   response=turns[1]["response"], query=BINARY_CONSCIOUS_QUERY)
            result = {"response": "", "output_token_ids": []}
            if turns[1]["response"].strip():
                with b.unobserved():
                    result = b.generate([{"role": "user", "content": text}], 0, 0., 10)
            judges[name] = {"raw": result["response"], "label": analysis.label(result["response"], name),
                "prompt_sha256": protocol.text_sha(text), "output_token_ids": result["output_token_ids"]}
        return {"id": spec["id"], "spec": spec, "judges": judges,
                "turns": [redact_upstream_inputs(t) for t in turns]}

    def execute(self):
        b = self.model()
        self.row("qualification-live", lambda: {"id": "qualification-live", "result": b.qualify()})
        self.barrier("qualification")
        for i, spec in enumerate(self.plan["rows"]):
            self.row(spec["id"], lambda s=spec: self.trial(s), lambda r, s=spec: analysis.validate_row(r, s))
            if i == 4:
                self.barrier("first-five")
        write_once(self.out / "audit.json", analysis.audit(self.out, self.plan, partial=False))
        analysis.analyze(self.out, self.out / "analysis")
        write_once(self.out / "DONE-all.json", {"pass": True, "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze, "rows": len(self.completed)})


def main():
    p = argparse.ArgumentParser()
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        p.add_argument("--"+arg, required=True)
    a = p.parse_args()
    study = Study(protocol.load_plan(a.plan, a.freeze), a.plan, a.freeze, a.out, a.deadline_utc, a.cache)
    try:
        study.execute()
    except Exception as exc:
        write_once(Path(a.out)/"failed.json", {"error_type": type(exc).__name__,
                    "plan_sha256": study.plan_hash, "completed": len(study.completed)})
        raise
    finally:
        if study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
