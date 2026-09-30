"""SAE-only worker, with a first-five pause and append-only row receipts."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time

from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.runner import Run, write_once
from .backend import SAEBackend, qualify
from .protocol import ROOT, load_plan, sha
from .analysis import validate_row, summarize


class ReplayRun(Run):
    def __init__(self, plan, plan_path, freeze, out, deadline, cache, barriers=True,
                 factory=SAEBackend, clock=time.time):
        self.plan, self.plan_hash, self.freeze = plan, sha(plan_path), freeze
        self.out, self.clock = Path(out), clock
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.barriers, self.cache, self.factory, self.backend = barriers, cache, factory, None
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze,
                                 ["replay-" + i["id"] for i in plan["inputs"]])
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                   "scope": plan["scope"], "budget": plan["budget"]})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"]["kind"] == "row"}
        self.audit()

    def state(self, item):
        from safetensors.torch import load_file
        import torch
        source_path, capture = ROOT / item["row_path"], ROOT / item["capture_path"]
        if sha(source_path) != item["row_sha256"] or sha(capture) != item["capture_sha256"]:
            raise ValueError("Input hash changed")
        source = json.loads(source_path.read_text())

        def operation():
            started = time.monotonic()
            tensors = load_file(str(capture))
            if set(tensors) != {"hidden", "token_ids"}:
                raise ValueError("Unexpected capture tensors")
            h, tokens = tensors["hidden"], tensors["token_ids"]
            if (h.dtype != torch.bfloat16 or h.shape != (1, tokens.numel(), 8192)
                    or tokens.dtype != torch.int64 or tokens.shape != (1, tokens.numel())
                    or tokens[0].tolist() != source["result"]["token_ids"]):
                raise ValueError("Capture/token mismatch")
            arms = self.backend.run(h[0], self.plan["feature_ids"], self.plan["gram"])
            return {"id": "replay-" + item["id"], "text_id": item["id"],
                    "split": source["split"], "corpus": source["corpus"],
                    "source_row_sha256": item["row_sha256"], "capture_sha256": item["capture_sha256"],
                    "token_ids": tokens[0].tolist(),
                    "position_metadata": source["result"]["telemetry"]["position_metadata"],
                    "arms": arms, "elapsed_seconds": time.monotonic() - started}

        return self.row("replay-" + item["id"], operation,
                        lambda row: validate_row(row, source, self.plan["feature_ids"]))

    def execute(self):
        self.check_time(900)
        qualification = qualify("cuda")
        write_once(self.out / "cheap-qualification.json", qualification)
        if not qualification["pass"]:
            raise RuntimeError("Synthetic CUDA qualification failed")
        self.backend = self.factory(self.cache)
        write_once(self.out / "sae-load.json", self.backend.metadata)
        rows = []
        for item in self.plan["inputs"]:
            rows.append(self.state(item))
            if len(rows) == 5:
                write_once(self.out / "first-five-summary.json", summarize(rows, self.plan["feature_ids"]))
                self.barrier("first-five")
        self.audit()
        write_once(self.out / "summary.json", summarize(rows, self.plan["feature_ids"]))
        write_once(self.out / "DONE-all.json", {"rows": len(rows), "plan_sha256": self.plan_hash,
                                              "freeze_commit": self.freeze, "native_replay_complete": True,
                                              "behavioral_assay_qualified": False})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan, args.freeze)
    ReplayRun(plan, args.plan, args.freeze, args.out, args.deadline_utc, args.cache).execute()


if __name__ == "__main__":
    main()
