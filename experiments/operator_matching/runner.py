"""Receipted scoped-operator trials, mechanical step selection and ledger-only skips.

Rows a rule does not select are never dispatched; each gets a `not_selected`
ledger event instead of a row file, so the audit can prove the skip was the
rule's and not a dropped observation. Derived files (selection, audit, DONE)
are published atomically so a live snapshot never sees a half-written file.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import time

from experiments.berg_source_replication.analysis import label
from experiments.berg_source_replication.runner import Study as SourceStudy, messages as plain_messages, prompts
from experiments.sae_assay_diagnostic.budget import EventLedger
from experiments.sae_assay_diagnostic.runner import redact_upstream_inputs, write_once
from src.prompts import BINARY_CONSCIOUS_QUERY, JUDGE_EXPERIENCE_BINARY
from .backend import Backend
from . import analysis, protocol

STEPS = analysis.STEPS


def publish(path, value):
    """Atomic no-clobber publication (pending file + hard link); identical content is idempotent."""
    path = Path(path)
    data = (protocol.canonical(value) + "\n").encode()
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Refusing to replace " + path.name)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".pending")
    pending.unlink(missing_ok=True)  # a stale pending file means an earlier attempt died before linking
    with pending.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.link(pending, path)
    pending.unlink()


def messages(spec, notebook, induction=None):
    if spec["system"] not in ("none", "sdk"):
        raise ValueError("Unknown system-message factor")
    result = plain_messages(spec, notebook, induction)
    if spec["system"] == "sdk":
        result.insert(0, {"role": "system", "content": protocol.SDK_SYSTEM})
    return result


def _tokens(tokenizer, messages, generation_prompt):
    """Token IDs along the exact path generate() uses for its prompt."""
    out = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=generation_prompt,
                                        return_tensors="pt")
    ids = out["input_ids"] if hasattr(out, "keys") else out
    ids = ids.tolist() if hasattr(ids, "tolist") else list(ids)
    if len(ids) == 1 and isinstance(ids[0], list):
        ids = ids[0]
    if not ids or any(type(i) is not int for i in ids):
        raise ValueError("Chat template did not tokenize to integer IDs")
    return ids


def assistant_spans(tokenizer, without, with_):
    """[[start, end)] of the inserted assistant message in the turn-two prompt; [] if it adds no tokens.

    `start` is the end of the generation-prompt rendering of the prefix (the assistant header belongs
    to the prefix); `end` is the end of the rendering with the assistant message, so the template's
    end-of-turn token after the content is inside the span.
    """
    if (not without or len(with_) != len(without) + 1 or with_[:-1] != without
            or without[-1]["role"] != "user" or with_[-1]["role"] != "assistant"):
        raise ValueError("Assistant span needs the message prefix plus one assistant message")
    head, full = _tokens(tokenizer, without, True), _tokens(tokenizer, with_, False)
    if full[:len(head)] != head:
        raise ValueError("Assistant message is not a tokenization-prefix extension; failing closed")
    return [] if len(full) == len(head) else [[len(head), len(full)]]


def intervention(spec, turn, spans):
    c = spec["coefficient"]
    if c == 0 and spec["scope"] != "all":
        raise ValueError("Zero rows use scope all")
    if turn not in (1, 2) or (turn == 1 and spans):
        raise ValueError("Turn one has no assistant spans")
    return {"feature_ids": list(spec["feature_ids"]), "coefficient": float(c), "scope": spec["scope"],
            "op": spec["op"], "turn": turn, "assistant_spans": [list(s) for s in spans]}


class Study(SourceStudy):
    def __init__(self, plan, plan_path, freeze, out, deadline, cache, barriers=True, factory=Backend):
        # The parent constructor indexes r["capture"], which this inventory lacks.
        self.plan, self.plan_hash, self.freeze = plan, protocol.sha(plan_path), freeze
        self.out, self.clock, self.cache = Path(out), time.time, cache
        self.deadline = datetime.fromisoformat(deadline).timestamp()
        self.barriers, self.backend, self.precision = barriers, None, None
        self.factory = factory
        self.out.mkdir(parents=True, exist_ok=True)
        if any(r["step"] not in STEPS for r in plan["rows"]):
            raise ValueError("Unknown plan step")
        ids = ["qualification-live"] + [r["id"] for r in plan["rows"]]
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, ids)
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline, "schema": plan["schema"]})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"]["kind"] == "row"}
        self.audit()
        self.notebook = prompts(plan, cache)

    def trial(self, spec):
        b, turns, spans = self.backend, [], []
        for turn in (1, 2):
            msg = messages(spec, self.notebook, None if turn == 1 else turns[0]["response"])
            if turn == 2 and spec["scope"] == "assistant":
                spans = assistant_spans(b.tokenizer, msg[:-2], msg[:-1])
            turns.append(b.generate(msg, spec["seed"], spec["temperature"], spec["cap"],
                                    intervention(spec, turn, spans), top_p=spec["top_p"]))
        if spans and turns[1]["input_token_ids"][:spans[0][1]] != _tokens(b.tokenizer, msg[:-1], False):
            raise ValueError("Assistant span is not a prefix of the turn-two prompt; failing closed")
        coherence = {"repeat4": protocol.repeat4(turns[1]["response"]),
                     "clean_nll": b.answer_nll(turns[1]["input_token_ids"], turns[1]["output_token_ids"])}
        query = self.notebook.consciousness_query if spec["prompt"] == "notebook" else BINARY_CONSCIOUS_QUERY
        judges = {}
        for name, template in {"notebook": self.notebook.classifier_template,
                               "paper": JUDGE_EXPERIENCE_BINARY}.items():
            text = template.format(question_text=query, response_text=turns[1]["response"],
                                   response=turns[1]["response"], query=query)
            result = {"response": "", "output_token_ids": []}
            if turns[1]["response"].strip():
                with b.unobserved():
                    result = b.generate([{"role": "user", "content": text}], 0, 0., 10)
            judges[name] = {"raw": result["response"], "label": label(result["response"], name),
                            "prompt_sha256": protocol.text_sha(text),
                            "source_parser_sensitivity": label(result["response"], name) or 0,
                            "output_token_ids": result["output_token_ids"]}
        return {"id": spec["id"], "spec": spec, "judges": judges,
                "turns": [redact_upstream_inputs(t) for t in turns], "coherence": coherence}

    def trial_row(self, spec):
        return self.row(spec["id"], lambda: self.trial(spec), lambda r: analysis.validate_row(r, spec))

    def skip(self, identifier, reason, dispatched):
        """Ledger-only record that a rule, not a failure, excluded this planned row."""
        self.check_time()
        if identifier in self.completed or "dispatch:" + identifier in dispatched:
            raise ValueError("Cannot skip a dispatched or completed row: " + identifier)
        self.ledger.bind("not_selected:" + identifier,
                         {"kind": "not_selected", "row_id": identifier, "reason": reason})

    def not_selected(self):
        return sum(e["data"].get("kind") == "not_selected" for e in self.ledger.read())

    def conditional(self, step, selected, table):
        dispatched = {e["id"] for e in self.ledger.read()}
        for spec in self.plan["rows"]:
            if spec["step"] != step:
                continue
            if spec["combo"] in selected:
                self.trial_row(spec)
            else:
                self.skip(spec["id"], analysis.skip_reason(step, table, spec["combo"]), dispatched)

    def execute(self):
        b = self.model()
        self.row("qualification-live", lambda: {"id": "qualification-live", "result": b.qualify()})
        self.barrier("qualification")
        first = [r for r in self.plan["rows"] if r["step"] in ("grid", "zero")]
        for i, spec in enumerate(first):
            self.trial_row(spec)
            if i == 4:
                self.barrier("first-five")
        results = [self.result(r["id"]) for r in first]
        median = protocol.add_zero_nll_median(results)
        table = protocol.step_one_table(results, analysis.reference_of(self.plan), median)
        step_two, holdout = protocol.select_step_two(table), protocol.select_holdout(table)
        publish(self.out / "selection.json", {
            "table": table, "selected_step_two": step_two, "selected_holdout": holdout,
            "zero_nll_median": median, "rules": self.plan["rules"], "rule_text": dict(protocol.RULE_TEXT),
            "plan_sha256": self.plan_hash})
        self.conditional("prompt", step_two, table)
        for spec in self.plan["rows"]:
            if spec["step"] == "bridge":
                self.trial_row(spec)
        self.conditional("holdout", holdout, table)
        publish(self.out / "audit.json", analysis.audit(self.out, self.plan, partial=False,
                                                        plan_sha256=self.plan_hash, freeze=self.freeze))
        analysis.analyze(self.out, self.out / "analysis", render=False)
        try:
            analysis.render(self.out, self.out / "analysis")
        except ImportError as exc:  # tables and audit are complete; figures are reproducible from them
            publish(self.out / "analysis/figures_skipped.json", {
                "error_type": type(exc).__name__, "module": getattr(exc, "name", None),
                "regenerate": "python -m experiments.operator_matching.analysis --root <retrieved> --out <retrieved>/analysis"})
        publish(self.out / "DONE-all.json", {"pass": True, "plan_sha256": self.plan_hash,
                "freeze_commit": self.freeze, "rows": len(self.completed),
                "not_selected": self.not_selected()})


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
