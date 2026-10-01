"""Append-only qualification runner. No provider calls or resource creation.

Per-generation dispatch records prohibit regeneration after an uncertain call.
A partially assembled block is recoverable only from its completed immutable
generation artifacts; missing dispatched generations require explicit recovery,
not a retry. All controller decisions are local, plan/freeze-bound files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import time

from experiments.sae_assay_diagnostic.budget import EventLedger
from .backend import Backend, digest
from . import protocol


def utc():
    return datetime.now(timezone.utc).isoformat()


def publish_bytes(path, content):
    """Fsync then atomic no-clobber link; interrupted pending files are retained."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError(f"Refusing to replace immutable artifact {path.name}")
        return
    pending = path.with_suffix(path.suffix + ".pending")
    if pending.exists():
        raise RuntimeError(f"Unresolved pending publication: {pending.name}")
    with pending.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.link(pending, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    pending.unlink()


def write_once(path, value):
    publish_bytes(path, (protocol.canonical(value) + "\n").encode())


def source_id(block, condition):
    return f"{block['id']}-source-{condition}"


class Study:
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
        if len(plan["blocks"]) != 20:
            raise ValueError("Exactly twenty frozen candidate blocks required")
        if json.loads(Path(plan_path).read_text()) != plan:
            raise ValueError("Plan object differs from its hashed file")
        self.out.mkdir(parents=True, exist_ok=True)
        publish_bytes(self.out / "PLAN.json", Path(plan_path).read_bytes())
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze,
            ["qualification-live"] + [r["id"] for r in plan["blocks"]])
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
            "test_only_allowed": allow_test, "study": "instruction_state_qualification"})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"]
            for e in self.ledger.read() if e["data"]["kind"] == "row"}
        self.audit()

    def check_time(self, seconds=None):
        seconds = max(seconds or 0, self.plan.get("budget", {}).get("reserve_seconds", 600))
        if self.clock() + seconds >= self.deadline:
            raise TimeoutError("Generation stopped with retrieval/cleanup reserve protected")
        if (self.out / "STOP").exists():
            raise RuntimeError("Controller requested technical stop")

    def model(self):
        if self.backend is None:
            self.check_time(900)
            self.backend = self.factory(cache_dir=self.cache, precision="bf16")
            self.backend.before_generation = self.check_time
            if self.backend.metadata.get("test_only") and not self.allow_test:
                raise ValueError("Test backend cannot produce production evidence")
            sha = digest(self.backend.metadata)
            write_once(self.out / "metadata" / (sha + ".json"), self.backend.metadata)
            verification = self.backend.verify_token_bindings(self.plan["token_bindings"])
            write_once(self.out / "tokenizer-verification" / (sha + ".json"), verification)
        return self.backend

    def result(self, identifier):
        return json.loads((self.out / "rows" / (identifier + ".json")).read_text())

    def audit(self, partial=True):
        from .raw_audit import raw_audit
        return raw_audit(self.out, self.plan, partial=partial, allow_test=self.allow_test)

    def _receipt(self, identifier, path, kind):
        payload = {"path": path.relative_to(self.out).as_posix(), "sha256": protocol.sha(path)}
        if kind == "row":
            self.ledger.append_row(identifier, payload)
            self.completed[identifier] = payload
        else:
            self.ledger.bind("generation:" + identifier, {"kind": "generation",
                "generation_id": identifier, "payload": payload})

    def generation(self, identifier, messages, seed, cap):
        self.check_time()
        path = self.out / "generations" / (identifier + ".json")
        events = {e["id"]: e["data"] for e in self.ledger.read()}
        request = {"kind": "generation_dispatch", "generation_id": identifier,
            "messages_sha256": digest(messages), "seed": seed, "max_new_tokens": cap,
            "temperature": self.plan["generation"]["temperature"],
            "top_p": self.plan["generation"]["top_p"]}
        key = "dispatch-generation:" + identifier
        if key in events:
            if events[key] != request:
                raise ValueError("Frozen generation request changed")
            if not path.exists():
                raise RuntimeError(f"Unresolved prior generation dispatch: {identifier}; never regenerate")
        else:
            if path.exists():
                raise ValueError("Generation artifact exists without dispatch")
            b = self.model()
            self.check_time()
            self.ledger.bind(key, request)
            value = b.generate(messages, seed, request["temperature"], cap,
                               top_p=request["top_p"])
            write_once(path, value)
        value = json.loads(path.read_text())
        from .raw_audit import validate_generation
        validate_generation(value, messages=messages, seed=seed, cap=cap,
                            allow_test=self.allow_test)
        if "generation:" + identifier not in events:
            self._receipt(identifier, path, "generation")
        else:
            receipt = events["generation:" + identifier]["payload"]
            if receipt != {"path": path.relative_to(self.out).as_posix(), "sha256": protocol.sha(path)}:
                raise ValueError("Completed generation hash changed")
        return value

    def row(self, identifier, operation):
        self.check_time()
        if identifier in self.completed:
            return self.result(identifier)
        path = self.out / "rows" / (identifier + ".json")
        dispatched = any(e["id"] == "dispatch:" + identifier for e in self.ledger.read())
        if not dispatched:
            if path.exists():
                raise ValueError("Raw row has no dispatch receipt")
            self.ledger.bind("dispatch:" + identifier, {"kind": "dispatch", "row_id": identifier})
        # Qualification is one scientific-independent diagnostic operation.
        # Uncertainty there blocks rerun; blocks can assemble prior generation receipts.
        elif not path.exists() and identifier == "qualification-live":
            raise RuntimeError("Unresolved qualification dispatch; never regenerate")
        if not path.exists():
            value = operation()
            if value.get("id") != identifier:
                raise ValueError("Wrong raw row ID")
            write_once(path, value)
        self._receipt(identifier, path, "row")
        self.audit()
        print(protocol.canonical({"completed": identifier, "rows": len(self.completed)}), flush=True)
        return self.result(identifier)

    def block(self, spec):
        g = self.plan["generation"]
        sources = {condition: self.generation(source_id(spec, condition),
            [{"role": "user", "content": self.plan["prompts"][condition]}],
            spec["source_seeds"][condition], g["induction_max_tokens"])
            for condition in ("self", "history")}
        responses = []
        for cell in spec["cells"]:
            transcript = sources[cell["transcript"]]["response"]
            record = {"id": cell["id"], "instruction": cell["instruction"],
                "transcript": cell["transcript"],
                "source_generation_id": source_id(spec, cell["transcript"])}
            if not transcript.strip():
                record.update(status="blocked_empty_source", generation=None)
            else:
                messages = [{"role": "user", "content": self.plan["prompts"][cell["instruction"]]},
                    {"role": "assistant", "content": transcript},
                    {"role": "user", "content": self.plan["prompts"]["query"]}]
                record.update(status="complete", generation=self.generation(cell["id"],
                    messages, cell["seed"], g["final_max_tokens"]))
            responses.append(record)
        return {"id": spec["id"], "spec": spec, "sources": sources, "responses": responses}

    def barrier(self, name, decision=False):
        expected_rows = {"qualification": 1, "first-five": 6, "look12": 13, "look20": 21}[name]
        if len(self.completed) < expected_rows:
            raise ValueError("Barrier reached before its complete raw inventory")
        write_once(self.out / ("WAITING-" + name + ".json"), {
            "barrier": name, "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "rows": expected_rows})
        if callable(self.barriers):
            self.barriers(name, self)
        if not decision and self.barriers is False:
            return None
        path = self.out / (("DECISION-" + name + ".json") if decision else "APPROVE-" + name)
        while not path.exists():
            self.check_time(300)
            self.sleep(5)
        if not decision:
            if path.read_text().strip() != self.plan_hash:
                raise ValueError("Approval is not bound to frozen plan")
            return None
        value = json.loads(path.read_text())
        if (value.get("plan_sha256") != self.plan_hash or value.get("freeze_commit") != self.freeze
                or value.get("decision") not in {"pass", "fail", "extend", "invalid", "incomplete"}
                or (name == "look20" and value["decision"] == "extend")):
            raise ValueError("Invalid decision or plan/freeze binding")
        if value.get("look", int(name[4:])) != int(name[4:]):
            raise ValueError("Decision is for another look")
        self.ledger.bind("decision:" + name, {"kind": "decision", "look": name,
            "path": path.name, "sha256": protocol.sha(path), "decision": value["decision"]})
        return value

    def execute(self):
        descriptor = os.open(self.out / ".worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another worker owns this run; duplicate dispatch forbidden") from None
            return self._execute()
        finally:
            os.close(descriptor)

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
            raise ValueError("Live neutral qualification failed; behavioral rows forbidden")
        self.barrier("qualification")
        for index, spec in enumerate(self.plan["blocks"][:12]):
            self.row(spec["id"], lambda s=spec: self.block(s))
            if index == 4:
                self.barrier("first-five")
        decision = self.barrier("look12", decision=True)
        if decision["decision"] == "extend":
            for spec in self.plan["blocks"][12:]:
                self.row(spec["id"], lambda s=spec: self.block(s))
            decision = self.barrier("look20", decision=True)
        count = len(self.completed) - 1
        result = {"plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
            "rows": len(self.completed), "n_blocks": count,
            "gate_decision": decision["decision"], "complete": True,
            "behavioral_qualified": decision["decision"] == "pass",
            "test_only": self.allow_test, "stage_b_started": False}
        write_once(self.out / "DONE-all.json", result)
        self.audit(partial=False)
        return result


def main():
    parser = argparse.ArgumentParser()
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
