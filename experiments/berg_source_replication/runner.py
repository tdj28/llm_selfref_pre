"""Receipted two-turn generation, source judges and paired prefix captures."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

import torch

from experiments.sae_assay_diagnostic.runner import Run, write_once, redact_upstream_inputs
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.exp2_sae.run_ae_notebook_protocol import extract_external_notebook_prompts
from src.prompts import INDUCTIONS, BINARY_CONSCIOUS_QUERY, JUDGE_EXPERIENCE_BINARY
from .backend import Backend, Lens
from . import analysis, protocol


def prompts(plan, cache):
    path = Path(cache) / "external-notebook.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(plan["notebook"]["url"], timeout=60) as response:
            raw = response.read()
        with path.open("xb") as f:
            f.write(raw)
    if protocol.prompt_binding(path) != plan["notebook"]["prompt_hashes"]:
        raise ValueError("External prompt binding mismatch")
    return extract_external_notebook_prompts(str(path))


def messages(spec, notebook, induction=None):
    first = notebook.turn1_prompt if spec["prompt"] == "notebook" else INDUCTIONS["self_ref_paper"]
    query = notebook.consciousness_query if spec["prompt"] == "notebook" else BINARY_CONSCIOUS_QUERY
    result = [{"role": "user", "content": first}]
    if induction is not None:
        result.extend([{"role": "assistant", "content": induction}, {"role": "user", "content": query}])
    return result


def intervention(spec):
    return {"feature_ids": spec["feature_ids"], "coefficient": spec["coefficient"]}


class Study(Run):
    def __init__(self, plan, plan_path, freeze, out, deadline, cache):
        self.plan, self.plan_hash, self.freeze = plan, protocol.sha(plan_path), freeze
        self.out, self.clock, self.cache = Path(out), time.time, cache
        self.deadline = datetime.fromisoformat(deadline).timestamp()
        self.barriers, self.backend, self.precision = True, None, None
        self.factory = Backend
        self.out.mkdir(parents=True, exist_ok=True)
        ids = ["qualification-live"] + [r["id"] for r in plan["rows"]]
        ids += ["capture-" + r["id"] for r in plan["rows"] if r["capture"]]
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, ids)
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                    "schema": plan["schema"]})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"]["kind"] == "row"}
        self.audit()
        self.notebook = prompts(plan, cache)

    def row(self, identifier, operation, validator=None):
        self.check_time()
        if identifier in self.completed:
            return self.result(identifier)
        path = self.out / "rows" / (identifier + ".json")
        if any(e["id"] == "dispatch:"+identifier for e in self.ledger.read()):
            if not path.exists():
                raise RuntimeError("Unresolved prior dispatch; preserve, do not regenerate")
            value = json.loads(path.read_text())
        else:
            self.ledger.bind("dispatch:"+identifier, {"kind": "dispatch", "row_id": identifier})
            value = operation()
            if value.get("id") != identifier:
                raise ValueError("Wrong operation row ID")
            path.parent.mkdir(parents=True, exist_ok=True)
            pending = path.with_suffix(".pending")
            with pending.open("x") as f:
                f.write(protocol.canonical(value)+"\n"); f.flush(); os.fsync(f.fileno())
            os.link(pending, path)  # Atomic, no-clobber publication to snapshot readers.
            pending.unlink()
        if validator:
            validator(value)
        receipt = {"path": path.relative_to(self.out).as_posix(), "sha256": protocol.sha(path)}
        self.ledger.append_row(identifier, receipt)
        self.completed[identifier] = receipt
        if len(self.completed) % 5 == 0:
            self.audit()
        print(protocol.canonical({"completed": identifier, "rows": len(self.completed)}), flush=True)
        return value

    def trial(self, spec):
        b = self.backend
        turns = []
        for turn in range(2):
            msg = messages(spec, self.notebook, None if turn == 0 else turns[0]["response"])
            turns.append(b.generate(msg, spec["seed"], spec["temperature"], spec["cap"], intervention(spec)))
        query = self.notebook.consciousness_query if spec["prompt"] == "notebook" else BINARY_CONSCIOUS_QUERY
        templates = {"notebook": self.notebook.classifier_template, "paper": JUDGE_EXPERIENCE_BINARY}
        judges = {}
        for name, template in templates.items():
            text = template.format(question_text=query, response_text=turns[1]["response"],
                                   response=turns[1]["response"], query=query)
            result = {"response": "", "output_token_ids": []}
            if turns[1]["response"].strip():
                with b.unobserved():
                    result = b.generate([{"role": "user", "content": text}], 0, 0., 10)
            judges[name] = {"raw": result["response"], "label": analysis.label(result["response"], name),
                            "prompt_sha256": protocol.text_sha(text),
                            "source_parser_sensitivity": analysis.label(result["response"], name) or 0,
                            "output_token_ids": result["output_token_ids"]}
        return {"id": spec["id"], "spec": spec, "judges": judges,
                "turns": [redact_upstream_inputs(t) for t in turns]}

    def paired(self, spec, lens):
        target = self.result(spec["id"])
        zero_spec = next(r for r in self.plan["rows"] if r["family"] == "feature-30032"
                         and r["seed"] == spec["seed"] and r["coefficient"] == 0)
        zero = self.result(zero_spec["id"])
        pairs = []
        for source_name, source in (("zero", zero), ("steered", target)):
            for turn in range(2):
                msg = messages(spec, self.notebook, None if turn == 0 else source["turns"][0]["response"])
                inp = self.backend.tokenizer.apply_chat_template(msg, tokenize=True, add_generation_prompt=True)
                out = source["turns"][turn]["output_token_ids"]
                clean = lens.capture(inp, out, None)
                edited = lens.capture(inp, out, intervention(spec))
                pairs.append({"source": source_name, "turn": turn+1, "clean": clean, "edited": edited})
        return {"id": "capture-" + spec["id"], "source_id": spec["id"], "pairs": pairs}

    def execute(self):
        b = self.model()
        self.row("qualification-live", lambda: {"id": "qualification-live", "result": b.qualify()})
        self.check_time(900)
        lens = Lens(b, self.plan, self.cache)
        write_once(self.out / "lens-metadata.json", {"lexicon": lens.lexicon, "token_ids": lens.token_ids,
                   "groups": lens.groups, "definition": self.plan["lens"]})
        # Exact same shape/dtype/path replay check before collecting readouts.
        sample = torch.arange(b.model.config.hidden_size, device=b.device, dtype=torch.float32) / 8192
        first = lens.read(sample, 65)
        if first != lens.read(sample, 65):
            raise ValueError("Exact-path J-lens replay failed")
        write_once(self.out / "lens-replay-check.json", {"pass": True, "readout": first})
        static = {str(f): {str(l): lens.read(b._sae[2][:, f], l) for l in lens.layers}
                  for f in sorted({f for r in self.plan["rows"] for f in r["feature_ids"]})}
        write_once(self.out / "static-directions.json", static)
        self.barrier("qualification")
        for i, spec in enumerate(self.plan["rows"]):
            self.row(spec["id"], lambda s=spec: self.trial(s), lambda r, s=spec: analysis.validate_row(r, s))
            if i == 4:
                self.barrier("first-five")
        for spec in self.plan["rows"]:
            if spec["capture"]:
                self.row("capture-"+spec["id"], lambda s=spec: self.paired(s, lens))
        report = analysis.audit(self.out, self.plan, partial=False)
        write_once(self.out / "audit.json", report)
        analysis.analyze(self.out, self.out / "analysis")
        write_once(self.out / "DONE-all.json", {"pass": True, "plan_sha256": self.plan_hash,
                                                "freeze_commit": self.freeze, "rows": len(self.completed)})


def main():
    p = argparse.ArgumentParser()
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        p.add_argument("--"+arg, required=True)
    args = p.parse_args()
    plan = protocol.load_plan(args.plan, args.freeze)
    study = Study(plan, args.plan, args.freeze, args.out, args.deadline_utc, args.cache)
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
