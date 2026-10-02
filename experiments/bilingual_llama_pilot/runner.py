"""Append-only bilingual generation with technical, never outcome-based, barriers."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from experiments.instruction_state_qualification.backend import Backend
from experiments.instruction_state_qualification.runner import (
    Study as DurableStudy, publish_bytes, write_once,
)
from experiments.sae_assay_diagnostic.budget import EventLedger
from . import prompts, protocol


class Study(DurableStudy):
    """Reuse the tested receipt/dispatch transport, not its qualification design."""

    def __init__(self, plan, plan_path, freeze, out, deadline, cache=None, *,
                 factory=Backend, clock=time.time, barriers=True, sleep=time.sleep,
                 allow_test=False):
        self.plan, self.plan_hash, self.freeze = plan, protocol.sha(plan_path), freeze
        self.out, self.cache, self.clock = Path(out), cache, clock
        parsed = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError("Deadline must be aware UTC")
        self.deadline, self.deadline_utc = parsed.timestamp(), deadline
        self.factory, self.barriers, self.sleep = factory, barriers, sleep
        self.allow_test, self.backend = allow_test, None
        if plan["blocks"] != protocol.inventory():
            raise ValueError("Exactly the twenty frozen bilingual blocks required")
        if json.loads(Path(plan_path).read_text()) != plan:
            raise ValueError("Plan object differs from hashed file")
        self.out.mkdir(parents=True, exist_ok=True)
        publish_bytes(self.out / "PLAN.json", Path(plan_path).read_bytes())
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze,
            ["qualification-live"] + [r["id"] for r in plan["blocks"]])
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
            "test_only_allowed": allow_test, "study": "bilingual_llama_measurement_pilot"})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"]
            for e in self.ledger.read() if e["data"]["kind"] == "row"}
        self.audit()

    def audit(self, partial=True):
        from .raw_audit import raw_audit
        return raw_audit(self.out, self.plan, partial=partial, allow_test=self.allow_test)

    def block(self, spec):
        generation = self.plan["generation"]
        sources = {s["id"]: self.generation(s["id"],
            prompts.source_messages(s["condition"], s["language"], spec["family"]),
            s["seed"], generation["induction_max_tokens"]) for s in spec["sources"]}
        responses = []
        for cell in spec["cells"]:
            source = protocol.source_for(spec, cell)
            identifier = source["id"] if source is not None else None
            text = sources[identifier]["response"] if identifier is not None else None
            record = {"id": cell["id"], "instruction": cell["instruction"],
                "transcript": cell["transcript"], "source_generation_id": identifier}
            if text is not None and not text.strip():
                record.update(status="blocked_empty_source", generation=None)
            else:
                messages = prompts.final_messages(cell["instruction"], cell["context_language"],
                    cell["output_language"], spec["family"], text)
                record.update(status="complete", generation=self.generation(cell["id"],
                    messages, cell["seed"], generation["final_max_tokens"]))
            responses.append(record)
        return {"id": spec["id"], "spec": spec, "sources": sources, "responses": responses}

    def barrier(self, name):
        expected_rows = {"qualification": 1, "first-two": 3}[name]
        if len(self.completed) < expected_rows:
            raise ValueError("Technical barrier lacks its complete raw inventory")
        write_once(self.out / ("WAITING-" + name + ".json"), {
            "barrier": name, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "rows": expected_rows})
        if callable(self.barriers):
            self.barriers(name, self)
        if self.barriers is False:
            if not self.allow_test:
                raise ValueError("Production barriers cannot be disabled")
            return
        path = self.out / ("APPROVE-" + name)
        while not path.exists():
            self.check_time(300)
            self.sleep(5)
        if path.read_text().strip() != self.plan_hash:
            raise ValueError("Technical approval is not bound to frozen plan")

    def _execute(self):
        if (self.out / "DONE-all.json").exists():
            self.audit(partial=False)
            return json.loads((self.out / "DONE-all.json").read_text())

        def qualify():
            model = self.model()
            self.check_time()
            return {"id": "qualification-live", "result": model.qualify()}

        qualification = self.row("qualification-live", qualify)
        if qualification["result"].get("pass") is not True:
            raise ValueError("Neutral numerical qualification failed")
        self.barrier("qualification")
        for index, spec in enumerate(self.plan["blocks"]):
            self.row(spec["id"], lambda s=spec: self.block(s))
            if index == 1:
                self.barrier("first-two")
        result = {"plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "rows": len(self.completed), "n_blocks": len(self.completed) - 1,
            "complete": True, "test_only": self.allow_test,
            "behavioral_qualified": False, "stage_b_started": False}
        write_once(self.out / "DONE-all.json", result)
        self.audit(partial=False)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "freeze", "out", "cache", "deadline-utc"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    plan = protocol.load_plan(args.plan, args.freeze)
    run = Study(plan, args.plan, args.freeze, args.out, args.deadline_utc, args.cache)
    try:
        run.execute()
    except Exception as exc:
        write_once(Path(args.out) / "failed.json", {"error_type": type(exc).__name__,
            "plan_sha256": run.plan_hash, "freeze_commit": run.freeze,
            "completed_rows": len(run.completed)})
        raise
    finally:
        if run.backend is not None:
            run.backend.close()


if __name__ == "__main__":
    main()
