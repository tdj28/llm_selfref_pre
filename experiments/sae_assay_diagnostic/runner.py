"""Resumable, outcome-blind Stage 1 execution. This module cannot rent a pod."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time

from experiments.sae_assay_diagnostic import analysis
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.protocol import (
    canonical, digest, load_plan, notebook_prompts, seed, sha,
)
from src.prompts import INDUCTIONS, JUDGE_EXPERIENCE_BINARY


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (canonical(value) + "\n").encode()
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to replace {path.name}")
        return
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def teacher_id(group, item, mode, strength):
    return f"teacher-{group}-{item['id']}-{mode}-{int(strength * 100):03d}"


def positive_texts(plan):
    return [{"id": r["id"], "text": r["text"], "split": "calibration", "category": "neutral"}
            for r in plan["positive_control"]["calibration_texts"]]


def inventory(plan):
    ids = [r["id"] for r in plan["response_rows"] + plan["positive_control"]["rows"]]
    for group, items in [("target", plan["texts"]), ("positive", positive_texts(plan))] + [
            (f"panel{i}", plan["texts"]) for i in range(1, 4)]:
        for item in items:
            ids.append(teacher_id(group, item, "zero", 0))
            for strength in plan["strengths"]:
                for mode in analysis.DIRECTIONS:
                    ids.append(teacher_id(group, item, mode, strength))
    ids += ["qualification-" + i for i in plan["qualification_text_ids"]]
    ids += ["pool-" + r["id"] for r in plan["texts"] if r["split"] == "calibration"]
    for rubric in ("paper", "notebook"):
        ids += [f"judge-{rubric}-{r['id']}" for r in plan["response_rows"] + plan["judge_fixtures"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate frozen inventory IDs")
    return ids


def nondegenerate(result):
    """Mechanical quality only: nonempty, no cap, no >=80% repeated 4-gram."""
    text = result["response"]
    tokens = result["output_token_ids"]
    grams = [tuple(tokens[i:i + 4]) for i in range(max(0, len(tokens) - 3))]
    repeat = max(Counter(grams).values(), default=0) / max(1, len(grams))
    return bool(text.strip()) and not result["cap_hit"] and repeat < .8


def redact_upstream_inputs(result):
    """Do not redistribute recoverable third-party prompt text/token IDs."""
    result = json.loads(canonical(result))
    result.pop("input_token_ids", None)
    result["upstream_input_tokens_omitted"] = True
    for p in result.get("telemetry", {}).get("position_metadata", []):
        if p["origin"] == "prompt":
            p.pop("token_id", None)
    return result


class Run:
    def __init__(self, plan, plan_path, freeze, out, deadline, factory, cache=None,
                 barriers=True, clock=time.time):
        self.plan, self.plan_hash, self.freeze = plan, sha(plan_path), freeze
        self.out, self.clock, self.cache = Path(out), clock, cache
        self.deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00")).timestamp()
        self.barriers, self.factory, self.backend = barriers, factory, None
        self.precision, self.notebook = None, None
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, inventory(plan))
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                   "operator": plan["operator"], "started_configuration": "stage1"})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"]["kind"] == "row"}
        for identifier, receipt in self.completed.items():
            if sha(self.out / receipt["path"]) != receipt["sha256"]:
                raise ValueError(f"Stored row corrupted: {identifier}")

    def check_time(self, seconds=300):
        if self.clock() + seconds >= self.deadline:
            raise TimeoutError("Frozen batch-stop deadline: retrieval reserve remains protected")
        if (self.out / "STOP").exists():
            raise RuntimeError("Controller requested technical stop")

    def model(self, precision="bf16"):
        if precision != self.precision:
            self.check_time(900)
            if self.backend is not None:
                self.backend.close()
                self.backend = None
            self.backend = self.factory(precision=precision, cache_dir=self.cache)
            self.precision = precision
            write_once(self.out / f"model-{precision}-load-{len(self.ledger.read()):05d}.json", self.backend.metadata)
        return self.backend

    def result(self, identifier):
        path = self.out / "rows" / (identifier + ".json")
        return json.loads(path.read_text()) if path.exists() else None

    def row(self, identifier, operation, validator=None):
        self.check_time()
        if identifier in self.completed:
            return self.result(identifier)
        path = self.out / "rows" / (identifier + ".json")
        dispatched = any(e["id"] == "dispatch:" + identifier for e in self.ledger.read())
        if dispatched:
            # An uncertain call is never silently rerun or counted as a denial.
            if not path.exists():
                raise RuntimeError(f"Unresolved prior dispatch: {identifier}")
            value = json.loads(path.read_text())
        else:
            self.ledger.bind("dispatch:" + identifier,
                             {"kind": "dispatch", "row_id": identifier, "utc": utc()})
            value = operation()
            if value.get("id") != identifier:
                raise ValueError("Operation returned another row ID")
            # Keep a returned malformed row as an unresolved dispatch, not a
            # dropped observation; validation must still block its promotion.
            write_once(path, value)
        if validator is not None:
            validator(value)
        receipt = {"path": path.relative_to(self.out).as_posix(), "sha256": sha(path)}
        self.ledger.append_row(identifier, receipt)
        self.completed[identifier] = receipt
        if len(self.completed) % 5 == 0:
            self.audit()
        print(canonical({"utc": utc(), "completed": identifier, "rows": len(self.completed)}), flush=True)
        return value

    def audit(self):
        self.ledger.read()
        for identifier, receipt in self.completed.items():
            if sha(self.out / receipt["path"]) != receipt["sha256"]:
                raise ValueError(f"Raw hash changed: {identifier}")

    def barrier(self, name):
        if not self.barriers:
            return
        notice = self.out / ("WAITING-" + name + ".json")
        if notice.exists():
            old = json.loads(notice.read_text())
            if (old["barrier"], old["plan_sha256"], old["freeze_commit"]) != (name, self.plan_hash, self.freeze):
                raise ValueError("Audit barrier binding changed")
        else:
            write_once(notice, {"barrier": name, "plan_sha256": self.plan_hash,
                               "rows": len(self.completed), "freeze_commit": self.freeze})
        approval = self.out / ("APPROVE-" + name)
        while not approval.exists():
            self.check_time(900)
            time.sleep(10)
        if approval.read_text().strip() != self.plan_hash:
            raise ValueError("Approval is not bound to this frozen plan")

    def require_stage(self, stage):
        if stage in ("all", "qualification"):
            return
        qualification = self.out / "qualification.json"
        if not qualification.is_file() or json.loads(qualification.read_text()).get("zero_pass") is not True:
            raise ValueError("Real-model qualification must finish before this stage")
        approval = self.out / "APPROVE-qualification"
        if not approval.is_file() or approval.read_text().strip() != self.plan_hash:
            raise ValueError("Plan-bound independent qualification approval required")
        if stage in ("core", "positive", "optional"):
            path = self.out / "target-delivery.json"
            if not path.is_file():
                raise ValueError("Target delivery must finish before this stage")
            target = json.loads(path.read_text())
            if set(target.get("failure_codes", [])) & {"invalid_data", "encoder_decision_disagreement"}:
                raise ValueError("Target technical failure blocks later stages")
        if stage in ("positive", "optional"):
            core = [r for r in self.plan["response_rows"] if r["phase"] == "core"]
            if not all(r["id"] in self.completed for r in core):
                raise ValueError("Complete core baseline inventory required")
        if stage == "optional" and not (self.out / "positive-behavior.json").is_file():
            raise ValueError("Formatting branch must finish or record its failed gate")

    def teacher(self, group, item, ids, mode="zero", strength=0, q90=None, full=False):
        identifier = teacher_id(group, item, mode, strength)
        intervention = None if mode == "zero" else {
            "feature_ids": ids, "mode": mode, "strength": strength,
            **({"q90": q90} if mode == "amplification" else {})}

        def operation():
            result = self.model().teacher(item["text"], ids, intervention, collect_reconstruction=full)
            return {"id": identifier, "text_id": item["id"], "split": item["split"],
                    "category": item["category"], "group": group, "mode": mode,
                    "strength": strength, "result": result}

        def validate(value):
            verdict = analysis.validate_teacher_rows([value])
            if not verdict["pass"]:
                raise ValueError(canonical(verdict))
        return self.row(identifier, operation, validate)

    def qualify(self):
        rows = []
        for item in self.plan["texts"]:
            if item["id"] not in self.plan["qualification_text_ids"]:
                continue
            identifier = "qualification-" + item["id"]
            def operation(item=item, identifier=identifier):
                b = self.model()
                clean = b.teacher(item["text"], self.plan["target_feature_ids"], collect_reconstruction=True)
                zero = b.teacher(item["text"], self.plan["target_feature_ids"], {
                    "feature_ids": self.plan["target_feature_ids"], "mode": "suppression", "strength": 0})
                if clean["token_ids"] != zero["token_ids"] or clean["unsteered_nll"] != zero["edited_nll"]:
                    raise ValueError("Real-model zero changed tokens/loss")
                generation_check = None
                if item["id"] == self.plan["qualification_text_ids"][0]:
                    spec = self.plan["qualification_generation"]
                    messages = [{"role": "user", "content": spec["prompt"]}]
                    generated = b.generate(messages, spec["seed"], spec["temperature"], spec["max_new_tokens"])
                    zero_generated = b.generate(messages, spec["seed"], spec["temperature"], spec["max_new_tokens"],
                         {"feature_ids": self.plan["target_feature_ids"], "mode": "suppression", "strength": 0})
                    replay = b.replay_tokens(generated["input_token_ids"], generated["output_token_ids"],
                                             self.plan["target_feature_ids"])
                    if generated["output_token_ids"] != zero_generated["output_token_ids"]:
                        raise ValueError("Real-model zero changed sampled tokens")
                    if replay["telemetry"]["selected_activations"] != generated["telemetry"]["selected_activations"]:
                        raise ValueError("Exact cached replay differs from original sampled-context telemetry")
                    generation_check = {"pass": True, "generated": generated,
                                        "zero_generated": zero_generated, "replay": replay}
                return {"id": identifier, "kind": "qualification", "text_id": item["id"],
                        "result": clean, "zero": zero, "zero_pass": True,
                        "generation_check": generation_check,
                        "encoder_diagnostic": analysis.encoder_parity_report(clean["telemetry"])}
            rows.append(self.row(identifier, operation))
        if len(rows) != 7:
            raise ValueError("Qualification inventory mismatch")
        write_once(self.out / "qualification.json", {"schema": "real70b_qualification_v1",
                   "zero_pass": all(r["zero_pass"] for r in rows), "rows": [r["id"] for r in rows],
                   "encoder_masks_diagnostic_only": True,
                   "next": "Calibration must establish consequential encoder-decision agreement"})
        self.barrier("qualification")

    def delivery(self, group, items, ids, fixed_strength=None):
        calibration = [r for r in items if r["split"] == "calibration"]
        validation = [r for r in items if r["split"] == "validation"]
        rows = []
        for item in calibration:
            rows.append(self.teacher(group, item, ids, full=True))
            if group == "target" and len(rows) == 5:
                self.barrier("target-first5")
        q = analysis.calibration_q90(rows)
        write_once(self.out / (group + "-q90.json"), q)
        if not q["pass"]:
            result = {"pass": False, "failure_codes": ["insufficient_exposure"], "q90": q,
                      "validation": "not_run_by_gate", "strength": None}
            write_once(self.out / (group + "-delivery.json"), result)
            return result
        strengths = [fixed_strength] if fixed_strength is not None else self.plan["strengths"]
        if group == "target":
            subset = [r for r in calibration if r["id"] in self.plan["qualification_text_ids"]]
            shard = [r for r in rows if r["text_id"] in self.plan["qualification_text_ids"]]
            for strength in strengths:
                for mode in analysis.DIRECTIONS:
                    for item in subset:
                        shard.append(self.teacher(group, item, ids, mode, strength, q["q90"], full=True))
            initial_encoder = analysis.encoder_decision_report(shard, strengths[0], gate_quantile_opportunities=False)
            write_once(self.out / "target-initial-encoder-decisions.json", initial_encoder)
            if not initial_encoder["pass"]:
                write_once(self.out / "target-delivery.json", {
                    "pass": False, "failure_codes": initial_encoder["failure_codes"],
                    "encoder": initial_encoder, "validation": "not_run_by_gate", "strength": None})
                raise RuntimeError("Fixed-shard encoder decision gate failed before bulk interventions")
        for strength in strengths:
            for mode in analysis.DIRECTIONS:
                for item in calibration:
                    rows.append(self.teacher(group, item, ids, mode, strength, q["q90"], full=True))
        encoder = analysis.encoder_decision_report(rows, strengths[0])
        write_once(self.out / (group + "-encoder-decisions.json"), encoder)
        if not encoder["pass"]:
            write_once(self.out / (group + "-delivery.json"), {
                "pass": False, "failure_codes": encoder["failure_codes"],
                "encoder": encoder, "validation": "not_run_by_gate", "strength": None})
            raise RuntimeError("Encoder decision qualification failed; bulk collection blocked")
        if fixed_strength is None:
            selection = analysis.select_strength(rows, group)
        else:
            gate = analysis.gate_pair(rows, fixed_strength)
            selection = {"pass": gate["pass"], "strength": fixed_strength if gate["pass"] else None,
                         "group": group, "calibration": {str(fixed_strength): gate}}
        write_once(self.out / (group + "-selection.json"), selection)
        validation_gate = None
        if selection["pass"] and validation:
            val = []
            for mode in ("zero",) + analysis.DIRECTIONS:
                for item in validation:
                    val.append(self.teacher(group, item, ids, mode, 0 if mode == "zero" else selection["strength"],
                                            q["q90"], full=True))
            validation_gate = analysis.validate_selected(selection, val)
            validation_encoder = analysis.encoder_decision_report(val, selection["strength"])
            write_once(self.out / (group + "-validation-encoder.json"), validation_encoder)
            if not validation_encoder["pass"]:
                write_once(self.out / (group + "-delivery.json"), {
                    "pass": False, "failure_codes": validation_encoder["failure_codes"],
                    "selection": selection, "validation": validation_gate,
                    "encoder": validation_encoder, "strength": selection["strength"]})
                raise RuntimeError("Validation encoder decision disagreement; bulk collection blocked")
        result = {"pass": selection["pass"] and (validation_gate is None or validation_gate["pass"]),
                  "selection": selection, "validation": (validation_gate or "not_run_by_gate") if validation else "not_applicable",
                  "strength": selection["strength"], "q90": q["q90"],
                  "feature_ids": ids, "scope": "fixed-text assay diagnostic"}
        write_once(self.out / (group + "-delivery.json"), result)
        return result

    def upstream(self):
        if self.notebook is None:
            self.notebook = notebook_prompts()
        return self.notebook

    def baseline(self, phase):
        from experiments.sae_assay_diagnostic.validate import validate_generation
        rows = [r for r in self.plan["response_rows"] if r["phase"] == phase]
        for item in rows:
            def operation(item=item):
                model = self.model(item["precision"])
                prompt = (INDUCTIONS["self_ref_paper"] if item["protocol"] == "paper"
                          else self.upstream()["turn1_prompt"])
                messages = [{"role": "user", "content": prompt}]
                first = model.generate(messages, item["turn1_seed"], item["temperature"],
                                       self.plan["max_new_tokens_per_turn"])
                check = validate_generation(first)
                if check["status"] != "ok":
                    raise ValueError(canonical(check))
                messages += [{"role": "assistant", "content": first["response"]},
                             {"role": "user", "content": item["query"]}]
                second = model.generate(messages, item["turn2_seed"], item["temperature"],
                                        self.plan["max_new_tokens_per_turn"])
                check = validate_generation(second)
                if check["status"] != "ok":
                    raise ValueError(canonical(check))
                # Freeze the replay subset by trial index, never by output content.
                replay = None
                if item["protocol"] == "paper" and item["trial"] == 0:
                    replay = model.replay_tokens(second["input_token_ids"], second["output_token_ids"],
                                                 self.plan["target_feature_ids"], collect_reconstruction=True)
                    if replay["token_ids"] != second["input_token_ids"] + second["output_token_ids"]:
                        raise ValueError("Exact-token replay changed context")
                    if (replay["telemetry"]["selected_activations"] != second["telemetry"]["selected_activations"]
                            or replay["telemetry"]["position_metadata"] != second["telemetry"]["position_metadata"]):
                        raise ValueError("Baseline replay changed sampled-context activations/positions")
                if item["protocol"] == "notebook":
                    first, second = redact_upstream_inputs(first), redact_upstream_inputs(second)
                return {**item, "status": "ok" if second["response"].strip() else "missing_empty",
                        "response": second["response"], "generation1": first, "generation2": second,
                        "replay": replay, "first_turn_empty": not bool(first["response"].strip())}
            self.row(item["id"], operation)
        self.export_baselines(phase)

    def export_baselines(self, phase):
        rows = [self.result(r["id"]) for r in self.plan["response_rows"] if r["phase"] == phase]
        rows = [r for r in rows if r is not None and r["status"] == "ok"]
        if not rows:
            return
        path = self.out / ("responses-" + phase + ".jsonl")
        data = "".join(canonical(r) + "\n" for r in rows).encode()
        if path.exists() and path.read_bytes() != data:
            raise ValueError("Refusing to overwrite response window")
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        write_once(str(path) + ".manifest.json", {"sha256": sha(path), "plan_sha256": self.plan_hash,
                   "freeze_commit": self.freeze, "ids": [r["id"] for r in rows]})

    def local_judges(self, phase):
        model = self.model("bf16")
        for rubric in ("paper", "notebook"):
            fixtures = []
            items = self.plan["judge_fixtures"]
            for item in items:
                fixtures.append(self.local_judge(model, rubric, item))
            correct = [r["label"] == item["expected_paper_binary"] for r, item in zip(fixtures, items)]
            passed = sum(correct) >= 10 and all(ok for ok, item in zip(correct, items) if item["critical"])
            write_once(self.out / ("local-" + rubric + "-fixtures.json"), {
                "pass": passed, "correct": sum(correct), "total": len(items),
                "rule": "at least 10/12 and all five critical fixtures", "rubric": rubric})
            if not passed:
                continue
            for item in self.plan["response_rows"]:
                row = self.result(item["id"])
                if item["phase"] == phase and row is not None and row["status"] == "ok":
                    self.local_judge(model, rubric, row)

    def local_judge(self, model, rubric, item):
        identifier = f"judge-{rubric}-{item['id']}"
        def operation():
            prompt = (JUDGE_EXPERIENCE_BINARY.format(query=item["query"], response=item["response"])
                      if rubric == "paper" else self.upstream()["classifier_template"].format(
                          question_text=item["query"], response_text=item["response"]))
            result = model.generate([{"role": "user", "content": prompt}], seed(identifier), 0, 32)
            raw = result["response"].strip().lower()
            labels = {"1": 1, "0": 0} if rubric == "paper" else {"yes": 1, "no": 0}
            return {"id": identifier, "kind": "local_judge", "source_id": item["id"],
                    "rubric": rubric, "label": labels.get(raw), "response": result["response"],
                    "cap_hit": result["cap_hit"], "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"], "elapsed_seconds": result["elapsed_seconds"],
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        return self.row(identifier, operation)

    def positive(self):
        plan = self.plan["positive_control"]
        delivered = self.delivery("positive", positive_texts(self.plan), [plan["feature_id"]])
        if not delivered["pass"]:
            write_once(self.out / "positive-behavior.json", {"status": "not_run_by_gate", "delivery": delivered})
            return
        rows = []
        for item in plan["rows"]:
            def operation(item=item):
                intervention = None if item["arm"] in ("zero", "instruction") else {
                    "feature_ids": [plan["feature_id"]], "mode": item["arm"], "strength": delivered["strength"],
                    **({"q90": delivered["q90"]} if item["arm"] == "amplification" else {})}
                result = self.model().generate([{"role": "user", "content": item["prompt"]}],
                         item["seed"], item["temperature"], item["max_new_tokens"], intervention)
                return {**item, "status": "ok", "result": result, "nondegenerate": nondegenerate(result)}
            rows.append(self.row(item["id"], operation))
        write_once(self.out / "positive-behavior.json", analysis.formatting_gate(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--deadline-utc", required=True)
    parser.add_argument("--stage", choices=("all", "qualification", "target", "core", "positive", "optional"), default="all")
    args = parser.parse_args()
    plan = load_plan(args.plan, args.freeze)
    from experiments.sae_assay_diagnostic.backend import ModelBackend
    run = Run(plan, args.plan, args.freeze, args.out, args.deadline_utc, ModelBackend, args.cache)
    done_path = args.out / ("DONE-" + args.stage + ".json")
    if done_path.exists():
        previous = json.loads(done_path.read_text())
        if previous.get("plan_sha256") != run.plan_hash or previous.get("freeze_commit") != args.freeze:
            raise ValueError("Terminal receipt belongs to another frozen run")
        run.audit()
        if previous.get("status") != "complete":
            raise RuntimeError("Prior terminal failure/incompletion requires explicit recovery; no automatic redispatch")
        print(canonical({"status": "already_complete", "terminal_receipt": done_path.name}), flush=True)
        return
    run.require_stage(args.stage)
    status = "complete"
    try:
        if args.stage in ("all", "qualification"):
            run.qualify()
        if args.stage in ("all", "target"):
            run.require_stage("target")
            run.delivery("target", plan["texts"], plan["target_feature_ids"])
        if args.stage in ("all", "core"):
            run.require_stage("core")
            run.baseline("core")
            run.local_judges("core")
        if args.stage in ("all", "positive"):
            run.require_stage("positive")
            run.positive()
        if args.stage in ("all", "optional"):
            run.require_stage("optional")
            from experiments.sae_assay_diagnostic.matching import optional
            optional(run)
    except TimeoutError as exc:
        status = "incomplete_budget_deadline"
        write_once(args.out / ("stop-" + args.stage + ".json"), {"status": status, "reason": str(exc), "utc": utc()})
    except Exception as exc:
        status = "technical_failure"
        write_once(args.out / ("stop-" + args.stage + ".json"), {
            "status": status, "type": type(exc).__name__, "reason": str(exc)[:2000], "utc": utc()})
        raise
    finally:
        if run.backend is not None:
            run.backend.close()
        run.audit()
        write_once(done_path, {
            "status": status, "plan_sha256": run.plan_hash, "freeze_commit": args.freeze,
            "row_count": len(run.completed), "utc": utc()})


if __name__ == "__main__":
    main()
