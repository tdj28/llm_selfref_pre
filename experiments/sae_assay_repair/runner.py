"""Fixed-inventory repair diagnostic. Never generates consciousness responses."""
import argparse
from copy import deepcopy
from datetime import datetime
import json
import math
from pathlib import Path
import time

import torch

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.fixtures import score_positive
from experiments.sae_assay_diagnostic.runner import Run, write_once, nondegenerate
from .backend import RepairBackend
from .protocol import ROOT, OPERATORS, canonical, load_plan, sha


def edit_id(operator, item, mode, strength):
    return f"edit-{operator}-{item['id']}-{mode}-{round(strength * 100):03d}"


def inventory(plan):
    result = ["qualification-live"]
    for item in plan["texts"]:
        result.append("clean-" + item["id"])
        for operator in OPERATORS:
            for mode in analysis.DIRECTIONS:
                for strength in plan["strengths"]:
                    result.append(edit_id(operator, item, mode, strength))
    result += ["context-" + context + "-" + item["id"]
               for context in plan["positive_contexts"]
               for item in plan["positive_control"]["calibration_texts"]]
    result += [row["id"] for row in plan["formatting_rows"]]
    return result


def for_operator(clean, operator):
    # Shared clean forwards, relabeled only in memory for paired gate routines.
    return [dict(row, group=operator) for row in clean]


def validate_row(row):
    check = analysis.validate_teacher_rows([row])
    if not check["pass"]:
        raise ValueError(canonical(check))
    t = row["result"]["telemetry"]
    full = t["full_sae"]
    for phase in ("before", "after"):
        if t["selected_activations"][phase] != full["full_selected_" + phase]:
            raise ValueError("Canonical reencoding differs from full diagnostic")
    if t["repair_operator"] != "literal" and row["mode"] != "zero" and row["strength"] != 0:
        n, k = len(row["result"]["token_ids"]), len(t["feature_ids"])
        for name in ("repair_requested_preact_delta", "repair_solve_residual",
                     "repair_solve_coefficients", "repair_desired_preact"):
            analysis._matrix(full.get(name), n, k, name)
        for shift, residual in zip(full["repair_requested_preact_delta"], full["repair_solve_residual"]):
            if any(abs(error) > 1e-3 * max(1., abs(request)) for request, error in zip(shift, residual)):
                raise ValueError("Solve residual exceeds frozen engineering tolerance")


def require_valid_gate(value):
    """A scientific failure is reportable; malformed-data gates must stop work."""
    if isinstance(value, dict):
        if "invalid_data" in value.get("failure_codes", []):
            raise ValueError("invalid_data in analysis gate")
        for child in value.values():
            require_valid_gate(child)
    elif isinstance(value, list):
        for child in value:
            require_valid_gate(child)


class RepairRun(Run):
    def __init__(self, plan, plan_path, freeze, out, deadline, factory=RepairBackend,
                 cache=None, barriers=True, clock=time.time):
        self.plan, self.plan_hash, self.freeze = plan, sha(plan_path), freeze
        self.out, self.clock, self.cache = Path(out), clock, cache
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.barriers, self.factory, self.backend = barriers, factory, None
        self.precision, self.notebook = None, None
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, inventory(plan))
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                   "prior_total_usd": plan["budget"]["prior_total_usd"],
                                   "stage": "post_stage1_engineering_repair"})
        self.completed = {r["data"]["row_id"]: r["data"]["payload"]
                          for r in self.ledger.read() if r["data"]["kind"] == "row"}
        self._audited = set()
        self.audit()

    def audit(self, full=False):
        self.ledger.read()
        for identifier, receipt in self.completed.items():
            if full or identifier not in self._audited:
                path = self.out / receipt["path"]
                if sha(path) != receipt["sha256"]:
                    raise ValueError("Raw row changed: " + identifier)
                row = json.loads(path.read_text())
                capture = row.get("capture")
                if capture and sha(self.out / capture["path"]) != capture["sha256"]:
                    raise ValueError("Residual capture changed")
                self._audited.add(identifier)

    def teacher_repair(self, item, operator="literal", mode="zero", strength=0, q90=None):
        identifier = "clean-" + item["id"] if mode == "zero" else edit_id(operator, item, mode, strength)
        def operation():
            backend = self.model()
            backend.operator = operator
            intervention = None if mode == "zero" else {
                "feature_ids": self.plan["target_feature_ids"], "mode": mode,
                "strength": strength, **({"q90": q90} if mode == "amplification" else {})}
            capture = None
            if mode == "zero":
                capture_path = self.out / "residuals" / (item["id"] + ".safetensors")
                backend.capture_path = capture_path
            result = backend.teacher(item["text"], self.plan["target_feature_ids"],
                                     intervention, collect_reconstruction=True)
            if mode == "zero":
                capture = {"path": capture_path.relative_to(self.out).as_posix(),
                           "sha256": sha(capture_path), "bytes": capture_path.stat().st_size}
            return {"id": identifier, "text_id": item["id"], "split": item["split"],
                    "category": item["category"], "corpus": item["corpus"],
                    "group": operator, "mode": mode, "strength": strength,
                    "capture": capture, "result": result}
        return self.row(identifier, operation, validate_row)

    def qualify_repair(self):
        def operation():
            backend = self.model()
            geometry = backend.geometry(self.plan["target_feature_ids"])
            geometry_receipt = {
                "feature_ids": self.plan["target_feature_ids"],
                "encoder_decoder_response": geometry.decoder_span.cpu().tolist(),
                "encoder_gram": geometry.encoder_min_norm.cpu().tolist(),
                "encoder_bias": geometry.bias.cpu().tolist(),
                "decoder_norms": torch.linalg.vector_norm(geometry.decoder, dim=0).cpu().tolist(),
                "conditions": {name: (float(getattr(geometry, name + "_condition"))
                    if math.isfinite(float(getattr(geometry, name + "_condition"))) else None)
                    for name in OPERATORS if name != "literal"},
                "scope": "Products/norms of selected native BF16 weights promoted to FP32; no model/SAE weights redistributed."}
            tokens = backend._tokenize("The desk has two drawers.")
            with torch.inference_mode():
                plain = backend.model.model(tokens, use_cache=False).last_hidden_state
            checks = {}
            for operator in OPERATORS:
                backend.operator = operator
                out, records = backend._forward(tokens, self.plan["target_feature_ids"], {
                    "feature_ids": self.plan["target_feature_ids"], "mode": "suppression", "strength": 0.})
                checks[operator + "_zero_identity"] = torch.equal(plain, out.last_hidden_state)
                checks[operator + "_activation_identity"] = (
                    records["selected_activations"]["before"] == records["selected_activations"]["after"])
            return {"id": "qualification-live", "pass": all(checks.values()), "checks": checks,
                    "geometry": geometry_receipt}
        result = self.row("qualification-live", operation)
        if not result["pass"]:
            raise RuntimeError("Live zero identity qualification failed")
        self.barrier("qualification")

    def target(self):
        calibration = [r for r in self.plan["texts"] if r["split"] == "calibration"]
        validation = [r for r in self.plan["texts"] if r["split"] == "validation"]
        clean = []
        for item in calibration:
            clean.append(self.teacher_repair(item))
            if len(clean) == 5:
                self.barrier("target-first5")
        q = analysis.calibration_q90(clean)
        write_once(self.out / "target-q90.json", q)
        require_valid_gate(q)
        reports, selected = {}, None
        if q["pass"]:
            available = []
            for operator in OPERATORS:
                if operator != "literal":
                    geometry = self.model().geometry(self.plan["target_feature_ids"])
                    condition = float(getattr(geometry, operator + "_condition"))
                    if not math.isfinite(condition) or condition > 1e6:
                        reports[operator] = {"pass": False, "unavailable": "singular_or_ill_conditioned",
                                             "condition": condition if math.isfinite(condition) else None}
                        write_once(self.out / ("calibration-" + operator + ".json"), reports[operator])
                        continue
                available.append(operator)
            shard = [item for item in calibration if item["corpus"] == "stage1_authored"
                     and item["id"].endswith("-01")]
            if len(shard) != 7:
                raise ValueError("Expected fixed seven-category nonzero shard")
            for operator in available:
                for strength in self.plan["strengths"]:
                    for mode in analysis.DIRECTIONS:
                        for item in shard:
                            self.teacher_repair(item, operator, mode, strength, q["q90"])
            self.barrier("repair-nonzero")
            for operator in OPERATORS:
                if operator not in available:
                    continue
                rows = for_operator(clean, operator)
                for strength in self.plan["strengths"]:
                    for mode in analysis.DIRECTIONS:
                        for item in calibration:
                            rows.append(self.teacher_repair(item, operator, mode, strength, q["q90"]))
                choice = analysis.select_strength(rows, operator)
                encoder = analysis.encoder_decision_report(rows, .5)
                subsets = {corpus: analysis.select_strength([r for r in rows if r["corpus"] == corpus], operator)
                           for corpus in sorted({r["corpus"] for r in rows})}
                require_valid_gate([choice, encoder, subsets])
                reports[operator] = {"pass": choice["pass"] and encoder["pass"],
                                     "selection": choice, "encoder": encoder,
                                     "corpus_sensitivities": subsets}
                write_once(self.out / ("calibration-" + operator + ".json"), reports[operator])
                if selected is None and reports[operator]["pass"]:
                    selected = {"operator": operator, "strength": choice["strength"], "selection": choice}
        write_once(self.out / "locked-selection.json", {"selected": selected, "calibration": reports})
        # Clean validation remains useful exposure evidence even if no recipe passes.
        val = [self.teacher_repair(item) for item in validation]
        validation_report = "no_selected_recipe_clean_exposure_only"
        if selected:
            operator, strength = selected["operator"], selected["strength"]
            rows = for_operator(val, operator)
            for mode in analysis.DIRECTIONS:
                rows += [self.teacher_repair(item, operator, mode, strength, q["q90"]) for item in validation]
            validation_report = {"gate": analysis.validate_selected(selected["selection"], rows),
                                 "encoder": analysis.encoder_decision_report(rows, strength)}
            require_valid_gate(validation_report)
        write_once(self.out / "target-final.json", {"selected": selected, "validation": validation_report,
                                                   "q90": q, "calibration": reports})

    def formatting(self):
        backend = self.model()
        backend.operator = "literal"
        for context in self.plan["positive_contexts"]:
            for item in self.plan["positive_control"]["calibration_texts"]:
                identifier = "context-" + context + "-" + item["id"]
                def operation(item=item, context=context, identifier=identifier):
                    started = time.perf_counter()
                    if context in ("raw", "instruction_raw"):
                        text = item["text"] if context == "raw" else "Return only JSON with no extra text.\n" + item["text"]
                        result = backend.teacher(text, [7688])
                    else:
                        messages = ([{"role": "user", "content": "Return only JSON with no extra text."},
                                     {"role": "assistant", "content": item["text"]}] if context == "assistant_chat"
                                    else [{"role": "user", "content": item["text"]}])
                        tokens = backend.tokenizer.apply_chat_template(messages, tokenize=True,
                            add_generation_prompt=False, return_tensors="pt")
                        tokens = backend._validate_tokens(tokens)
                        with torch.inference_mode():
                            result = backend._evaluate_tokens(tokens, tokens.shape[1], [7688], None, False, False, started)
                    return {"id": identifier, "context": context, "text_id": item["id"], "result": result}
                self.row(identifier, operation)
        rows = []
        for item in self.plan["formatting_rows"]:
            def operation(item=item):
                result = backend.generate([{"role": "user", "content": item["prompt"]}], item["seed"],
                                           item["temperature"], item["max_new_tokens"])
                return dict(item, result=result, status="ok", nondegenerate=nondegenerate(result),
                            strict_json_score=score_positive(result["response"]))
            rows.append(self.row(item["id"], operation))
        difference = sum(int(r["strict_json_score"]) * (1 if r["arm"] == "instruction" else -1)
                         for r in rows) / 20
        write_once(self.out / "formatting-summary.json", {
            "rows": len(rows), "instruction_minus_zero": difference,
            "counts": {arm: sum(r["strict_json_score"] for r in rows if r["arm"] == arm)
                       for arm in ("zero", "instruction")},
            "nondegenerate_counts": {arm: sum(r["nondegenerate"] for r in rows if r["arm"] == arm)
                                     for arm in ("zero", "instruction")},
            "scope": "Instruction assay only, not a successful SAE positive control."})


def main():
    parser = argparse.ArgumentParser()
    for name in ("plan", "out", "cache"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--deadline-utc", required=True)
    args = parser.parse_args()
    plan = load_plan(args.plan, args.freeze)
    run = RepairRun(plan, args.plan, args.freeze, args.out, args.deadline_utc, cache=args.cache)
    done_path = args.out / "DONE-all.json"
    if done_path.exists():
        done = json.loads(done_path.read_text())
        run.audit(full=True)
        if done != {"status": "complete", "rows": len(run.completed)}:
            raise RuntimeError("Prior run is incomplete; preserve it and use an explicit recovery plan")
        print(canonical({"already_complete": True, "rows": len(run.completed)}))
        return
    status = "failed_or_incomplete"
    try:
        run.qualify_repair()
        run.target()
        run.formatting()
        run.audit(full=True)
        status = "complete"
    except BaseException as exc:
        write_once(args.out / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        if run.backend:
            run.backend.close()
        write_once(args.out / "DONE-all.json", {"status": status, "rows": len(run.completed)})


if __name__ == "__main__":
    main()
