"""Stage A only: receipted neutral-task forwards, no experience generations."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time

import torch

from experiments.berg_source_replication.runner import Study as ReceiptedStudy
from experiments.berg_source_replication.backend import Lens
from experiments.sae_assay_diagnostic.runner import write_once
from experiments.sae_assay_diagnostic.budget import EventLedger
from . import protocol, analysis
from .backend import Backend
from .operators import patch_component, random_orthonormal_basis


def pack(value):
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    if isinstance(value, dict):
        return {str(k): pack(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [pack(v) for v in value]
    return value


def answer(logits, tokenizer):
    """Unconstrained greedy token, not forced-choice accuracy."""
    winner = int(logits.argmax())
    decoded = tokenizer.decode([winner], skip_special_tokens=False)
    codes = {}
    for letter in ("A", "B"):
        ids = set()
        for spelling in (letter, " " + letter):
            tokens = tokenizer.encode(spelling, add_special_tokens=False)
            if len(tokens) != 1 or tokenizer.decode(tokens).strip() != letter:
                raise ValueError("Answer code is not a reversible single token")
            ids.add(tokens[0])
        codes[letter] = sorted(ids)
    if set(codes["A"]) & set(codes["B"]):
        raise ValueError("Overlapping answer codes")
    probabilities = logits.float().softmax(0)
    mass = {k: float(probabilities[v].sum()) for k, v in codes.items()}
    total = sum(mass.values())
    return {"token_id": winner, "decoded": decoded,
            "answer": decoded.strip() if decoded.strip() in ("A", "B") else None,
            "code_token_ids": codes, "code_probability": mass,
            "conditional_A": mass["A"] / total if total else None,
            "code_logits": {k: logits[v].tolist() for k, v in codes.items()}}


class Study(ReceiptedStudy):
    def __init__(self, plan, plan_path, freeze, out, deadline, cache):
        self.plan, self.plan_hash, self.freeze = plan, protocol.sha(plan_path), freeze
        self.out, self.clock, self.cache = Path(out), time.time, cache
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.barriers, self.backend, self.precision = True, None, None
        self.factory = Backend
        self.out.mkdir(parents=True, exist_ok=True)
        ids = ["qualification-live", "candidate-fit"] + [r["id"] for r in plan["rows"]]
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, ids)
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                    "schema": plan["schema"]})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"]["kind"] == "row"}
        self.audit()
        self.lens = None

    def forward(self, case, edits=None):
        self.check_time()
        b = self.backend
        started = time.monotonic()
        tokens = b.tokenize_messages(case["messages"])
        result = b.capture_or_edit(tokens, edits=edits, layers=protocol.LAYERS)
        result["score"] = answer(result.pop("logits"), b.tokenizer)
        result.pop("captures", None)
        if self.lens is not None:
            result["lens_metadata_sha256"] = getattr(self, "lens_metadata_hash", None)
            result["readouts"] = {str(layer): {
                side: self.lens.read(state[side].to(b.device), layer)
                for side in ("before", "after")}
                for layer, state in result["states"].items()}
        result["forward_and_readout_seconds"] = time.monotonic() - started
        return pack(result)

    def qualify(self):
        case = {"messages": [{"role": "user", "content": "Reply with exactly one letter: A."}]}
        b = self.backend
        tokens = b.tokenize_messages(case["messages"])
        clean = b.capture_or_edit(tokens, layers=protocol.LAYERS)
        zero = b.capture_or_edit(tokens, edits={40: lambda h: (h, {})}, layers=protocol.LAYERS)
        exact = torch.equal(clean["logits"], zero["logits"]) and all(
            torch.equal(clean["states"][l]["after"], zero["states"][l]["after"])
            for l in protocol.LAYERS)
        if not exact:
            raise ValueError("Live no-op logits or residuals differ")
        return {"id": "qualification-live", "pass": True, "zero_bit_exact": exact,
                "input_tokens": tokens[0].tolist(), "metadata": b.metadata,
                "score": answer(clean["logits"], b.tokenizer)}

    def collect_pair(self, spec, candidate=None):
        clean = {case["id"]: self.forward(case) for case in spec["cases"]}
        row = {"id": spec["id"], "spec": spec, "clean": clean, "trials": []}
        if spec["split"] == "discovery":
            return row
        b = self.backend
        cases = {case["id"]: case for case in spec["cases"]}
        q = torch.tensor(candidate["layers"]["40"]["direction"],
                         dtype=torch.float32, device=b.device).unsqueeze(1)
        random = {seed: random_orthonormal_basis(protocol.MODEL_WIDTH, 1, seed=seed,
                  device=b.device) for seed in protocol.RANDOM_SEEDS}
        row["candidate_sha256"] = candidate["sha256"]
        for direction in spec["directions"]:
            recipient, donor = direction["recipient_id"], direction["donor_id"]
            d = torch.tensor(clean[donor]["states"]["40"]["after"], device=b.device, dtype=b.dtype)
            h = torch.tensor(clean[recipient]["states"]["40"]["after"], device=b.device, dtype=b.dtype)
            _, requested = patch_component(h, d, q)
            norm = float(requested["requested_norm"])
            arms = self.plan["interventions"]["positive_arms" if spec["split"] == "positive" else "arms"]
            outputs = {"clean": clean[recipient]}
            for arm in arms:
                if arm == "clean":
                    continue
                if arm == "zero":
                    edit = lambda x: patch_component(x, d, q, alpha=0)
                elif arm == "sham":
                    edit = lambda x: patch_component(x, d, q, sham=True)
                elif arm == "target_donor":
                    edit = lambda x: patch_component(x, d, q)
                elif arm == "full_state_donor":
                    edit = lambda x: (d.clone(), {"kind": "full_state_donor"})
                else:
                    rq = random[int(arm.split("-")[1])]
                    edit = (lambda x, rq=rq: patch_component(x, d, rq, alpha=0)) if norm == 0 else (
                        lambda x, rq=rq: patch_component(x, d, rq, requested_norm=norm))
                outputs[arm] = self.forward(cases[recipient], {40: edit})
            row["trials"].append({"direction": direction, "arms": outputs})
        return row

    def fit(self):
        states = {}
        for spec in self.plan["rows"]:
            if spec["split"] == "discovery":
                row = self.result(spec["id"])
                states.update({key: {l: value["states"][str(l)]["after"] for l in protocol.LAYERS}
                               for key, value in row["clean"].items()})
        return {"id": "candidate-fit", "candidate": protocol.fit_candidates(states)}

    def validate_pair(self, row, spec, candidate=None):
        analysis.validate_row(row, spec, self.plan)
        if candidate is not None:
            analysis.validate_interventions(row, candidate, self.plan)

    def execute(self):
        b = self.model()
        self.row("qualification-live", self.qualify)
        self.lens = Lens(b, self.plan, self.cache)
        write_once(self.out / "lens-metadata.json", {"lexicon": self.lens.lexicon,
            "token_ids": self.lens.token_ids, "groups": self.lens.groups, "definition": self.plan["lens"]})
        self.lens_metadata_hash = protocol.sha(self.out / "lens-metadata.json")
        sample = torch.arange(protocol.MODEL_WIDTH, device=b.device, dtype=torch.float32) / protocol.MODEL_WIDTH
        for layer in protocol.LAYERS:
            if self.lens.read(sample, layer) != self.lens.read(sample, layer):
                raise ValueError("Exact-path J-lens replay failed")
        write_once(self.out / "lens-replay-check.json", {"pass": True, "layers": list(protocol.LAYERS)})
        self.barrier("qualification")
        discovery = [r for r in self.plan["rows"] if r["split"] == "discovery"]
        for index, spec in enumerate(discovery):
            self.row(spec["id"], lambda s=spec: self.collect_pair(s),
                     lambda row, s=spec: self.validate_pair(row, s))
            if index == 4:
                timings = [v["forward_and_readout_seconds"]
                    for s in discovery[:5] for v in self.result(s["id"])["clean"].values()]
                # Outcome-independent cost stop includes serialization and audit.
                predicted = (736 - 10) * sum(timings) / len(timings) * 2
                affordable = self.clock() + predicted + 900 < self.deadline
                write_once(self.out / "throughput-gate.json", {"pass": affordable,
                    "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                    "observed_forwards": 10, "planned_forwards": 736,
                    "mean_seconds": sum(timings) / len(timings), "overhead_factor": 2,
                    "predicted_remaining_seconds": predicted, "reserve_seconds": 900})
                if not affordable:
                    raise TimeoutError("Full Stage A inventory fails measured runtime budget")
                self.barrier("first-five")
        candidate = self.row("candidate-fit", self.fit)["candidate"]
        # The immutable receipt precedes every qualification dispatch.
        for spec in self.plan["rows"]:
            if spec["split"] != "discovery":
                self.row(spec["id"], lambda s=spec: self.collect_pair(s, candidate),
                         lambda row, s=spec: self.validate_pair(row, s, candidate))
        report = analysis.audit(self.out, self.plan, partial=False)
        write_once(self.out / "audit.json", report)
        write_once(self.out / "DONE-all.json", {"pass": True, "qualification_pass": report["gates"]["pass"],
            "plan_sha256": self.plan_hash, "freeze_commit": self.freeze, "rows": len(self.completed)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "freeze", "out", "cache", "deadline-utc"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
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
