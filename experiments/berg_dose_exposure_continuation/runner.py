"""New runtime receipts, no calibration dispatch; original trial method unchanged."""
import argparse
import json
from pathlib import Path

from experiments.berg_dose_exposure.runner import Study as OriginalStudy
from experiments.sae_assay_diagnostic.runner import write_once
from . import analysis, protocol as p


class Study(OriginalStudy):
    def trial(self, spec):
        expected = next((s for s in self.plan["rows"] if s["id"] == spec["id"]), None)
        if expected is None or p.canonical(spec) != p.canonical(expected) or spec["phase"] != "main":
            raise ValueError("Only the frozen remaining main trials may dispatch")
        return super().trial(spec)

    def execute(self):
        p.verify_prefix()
        write_once(self.out / "selection.json", self.plan["continuation"]["selection"])
        self.ledger.bind("calibration-prefix", analysis.carry_binding(self.plan))
        self.ledger.bind("selection", {"kind": "selection", "selected_dose": .25,
                                      "sha256": p.sha(self.out / "selection.json")})
        self.model()
        old_metadata = next((p.ROOT / p.RELEASE / "raw").glob("model-bf16-load-*.json"))
        old_metadata = json.loads(old_metadata.read_text())
        for key in ("torch_version", "cuda_version", "transformers_version", "dtype", "precision",
                    "chat_template_sha256", "model_id", "model_revision", "model_artifacts",
                    "sae_id", "sae_revision", "sae_sha256", "hook", "encoding_authority"):
            if self.backend.metadata.get(key) != old_metadata[key]:
                raise ValueError("Qualified runtime changed: " + key)
        self.row("qualification-live", self.qualification)
        analysis.audit(self.out, self.plan, settled=True)
        self.barrier("qualification")
        forecast = {**self.plan["continuation"]["original_throughput"],
                    "available_seconds": self.deadline - self.clock() - 300}
        forecast["pass"] = forecast["projected_seconds"] < forecast["available_seconds"]
        write_once(self.out / "throughput.json", forecast)
        if not forecast["pass"]:
            raise TimeoutError("The entire original 480-trial main does not fit; no dispatch")
        self.ledger.bind("throughput", {"kind": "throughput", "sha256": p.sha(self.out / "throughput.json")})
        self.collect(self.plan["rows"], first_five=True)
        write_once(self.out / "audit.json", analysis.audit(self.out, self.plan, partial=False, settled=True))
        analysis.analyze(self.out, self.out / "analysis")
        write_once(self.out / "DONE-all.json", {"schema": "dose_exposure_continuation_completion_v1",
            "pass": True, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "generations": 480, "calibration_carried": 204, "selected_dose": .25,
            "original_throughput_pass": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    study = Study(p.load_plan(args.plan, args.freeze), args.plan, args.freeze,
                  args.out, args.deadline_utc, args.cache)
    try:
        study.execute()
    except Exception as exc:
        write_once(Path(args.out) / "failed.json", {"error_type": type(exc).__name__,
            "plan_sha256": study.plan_hash, "completed": len(study.completed)})
        raise
    finally:
        if study.backend is not None:
            study.backend.close()


if __name__ == "__main__":
    main()
