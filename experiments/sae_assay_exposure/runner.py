"""One clean model forward per certified text; no head, loss, edit or generation.

Parent-owned protocol.load_plan(path, freeze) must verify the public freeze and
transitive source/input hashes. Runtime keys: schema='sae_exposure_v1', scope,
texts, certificate, rules, target_feature_ids, budget, hardware. The corpus and
certificate must be the unchanged authored 224-text design. The inherited
Run.barrier notices count receipted rows: qualification=1, first-five=6.

Hourly cost is an all-in GPU/storage bound from pod creation, not worker start.
Controller retains responsibility for ownership, a hard external timeout and
retrieval/deletion: a stopped Python process does not stop pod billing.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import time

import torch

from experiments.sae_assay_diagnostic.backend import (
    MODEL_ID, MODEL_REVISION, SAE_ID, SAE_REVISION, SAE_FILE_SHA256,
    ENCODING_AUTHORITY, _check_runtime_versions,
)
from experiments.sae_assay_diagnostic.budget import EventLedger, _number, _utc
from experiments.sae_assay_diagnostic.runner import Run, write_once
from experiments.sae_assay_repair.backend import RepairBackend
from experiments.sae_assay_replay import exposure
from . import analysis


ROOT = Path(__file__).resolve().parents[2]
PRIOR_TOTAL = Decimal("27.6350693241315361")
RETRIEVAL_SECONDS = 600
QUALIFICATION_TEXT = "The desk has two drawers."
TOKENIZER_INVENTORY = "data/sae_assay_replay/exposure_plan_20260930/TOKENIZER_INVENTORY.json"
sha = analysis.sha


def inventory(plan):
    return ["qualification-live"] + ["clean-" + item["id"] for item in plan["texts"]]


def checked_budget(plan):
    budget = plan["budget"]
    if set(budget) != {"prior_total_usd", "total_usd", "exposure_max_usd",
                       "new_paid_judge_calls", "new_pro_calls"}:
        raise ValueError("Complete exposure-only budget required")
    amounts = {key: _number(value) for key, value in budget.items()}
    if (amounts["prior_total_usd"] != PRIOR_TOTAL or amounts["total_usd"] != 200
            or not 0 < amounts["exposure_max_usd"] <= 25
            or amounts["new_paid_judge_calls"] != 0 or amounts["new_pro_calls"] != 0
            or PRIOR_TOTAL + amounts["exposure_max_usd"] > amounts["total_usd"]):
        raise ValueError("Exposure budget exceeds or resets authorization")
    return amounts


def columns(matrix, ids):
    if any(len(row) != len(ids) for row in matrix):
        raise ValueError("Native activation width mismatch")
    return {str(feature): [row[j] for row in matrix] for j, feature in enumerate(ids)}


def require_clean(records):
    a, d, full = records["selected_activations"], records["delivery"], records["full_sae"]
    if (a["before"] != a["after"] or a["before"] != a["requested_activation"]
            or any(any(v != 0 for v in row) for row in a["requested_delta"])
            or any(v != 0 for key in ("requested_norm", "realized_norm") for v in d[key])
            or not all(v is True for v in d["identity"])
            or not all(v is True for v in d["valid"])
            or any(d["nonzero_requested"])):
        raise ValueError("Clean forward contains an edit or invalid position")
    if full is not None and (a["before"] != full["full_selected_before"]
                             or full["full_selected_before"] != full["full_selected_after"]):
        raise ValueError("Canonical clean activations differ from native full-width diagnostic")


class ExposureBackend(RepairBackend):
    """Narrow wrapper around the existing audited hook and capture writer."""

    def verify_tokenizer(self, plan):
        path = ROOT / TOKENIZER_INVENTORY
        if sha(path) != analysis.TOKENIZER_INVENTORY_SHA256:
            raise ValueError("Frozen tokenizer inventory changed")
        expected = json.loads(path.read_text())
        metadata = self.metadata
        bindings = {"model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                    "sae_id": SAE_ID, "sae_revision": SAE_REVISION,
                    "sae_sha256": SAE_FILE_SHA256, "precision": "bf16",
                    "dtype": "torch.bfloat16", "hook": "model.layers.50.output",
                    "encoding_authority": ENCODING_AUTHORITY}
        if any(metadata.get(key) != value for key, value in bindings.items()):
            raise ValueError("Production model/SAE provenance mismatch")
        for artifact in expected["files"]:
            actual = metadata["model_artifacts"][artifact["path"]]
            if any(actual[key] != artifact[key] for key in ("sha256", "bytes")):
                raise ValueError("Loaded tokenizer artifacts differ from certificate")
        certificate = exposure.certify_tokenization(
            plan["texts"], self.tokenizer, tokenizer_sha256=sha(path))
        if certificate != plan["certificate"]:
            raise ValueError("Runtime tokenizer differs from certified token IDs/masks")
        return {"pass": True, "tokenizer_inventory_sha256": sha(path),
                "certificate_sha256": analysis.json_sha(certificate), "rows": len(certificate["items"])}

    @torch.inference_mode()
    def qualify(self, feature_ids):
        self.operator, self.capture_path = "literal", None
        tokens = self._tokenize(QUALIFICATION_TEXT)
        self._request_memory(tokens.shape[1], False)
        plain = self.model.model(tokens, use_cache=False).last_hidden_state
        output, records = self._forward(tokens, feature_ids, intervention=None)
        require_clean(records)
        checks = {"clean_identity": torch.equal(plain, output.last_hidden_state),
                  "activation_identity": records["selected_activations"]["before"] == records["selected_activations"]["after"],
                  "no_edit": True, "hook_removed": not bool(self._layer._forward_hooks)}
        return {"pass": all(checks.values()), "checks": checks, "token_ids": tokens[0].tolist()}

    @torch.inference_mode()
    def screen(self, item, certificate_item, feature_ids, capture_path):
        started = time.monotonic()
        token_ids = self.tokenizer.encode(item["text"], add_special_tokens=True, truncation=False)
        mask = [token in set(self.tokenizer.all_special_ids) for token in token_ids]
        if token_ids != certificate_item["token_ids"] or mask != certificate_item["special_tokens_mask"]:
            raise ValueError("Actual token IDs/mask changed before forward")
        tokens = self._validate_tokens(torch.tensor([token_ids], dtype=torch.int64))
        self._request_memory(len(token_ids), False)
        self.operator, self.capture_path = "literal", Path(capture_path)
        try:
            output, records = self._forward(tokens, feature_ids, intervention=None,
                                            collect_reconstruction=True)
            del output
        finally:
            self.capture_path = None
        require_clean(records)
        positions = records["position_metadata"]
        expected_positions = [{"position": i, "token_id": token, "origin": "prompt",
                               "token_class": "special" if special else "prompt",
                               "terminal_observation_only": False}
                              for i, (token, special) in enumerate(zip(token_ids, mask))]
        if positions != expected_positions:
            raise ValueError("Actual hook positions differ from clean certificate")
        full = records["full_sae"]
        native = columns(full["full_selected_before"], feature_ids)
        selected = columns(full["selected_path_before"], feature_ids)
        differences = [abs(a - b) for f in native for a, b in zip(native[f], selected[f])]
        return {"token_ids": token_ids, "special_tokens_mask": mask, "activations": native,
                "diagnostics": {"clean_norm": records["delivery"]["clean_norm"],
                    "reconstruction_error_norm": full["reconstruction_error_norm"],
                    "reconstruction_relative_error": full["reconstruction_relative_error"],
                    "l0": full["l0_before"], "selected_path_activations": selected,
                    "selected_path_max_abs_error": max(differences),
                    "selected_path_positive_mask_disagreements": sum(
                        (a > 0) != (b > 0) for f in native for a, b in zip(native[f], selected[f]))},
                "elapsed_seconds": time.monotonic() - started}


def synthetic_qualification():
    from experiments.sae_assay_precision.pilot import validate_model_math

    arithmetic_flags = validate_model_math("cuda")
    import transformers
    from experiments.sae_assay_repair.qualify import checks
    from experiments.sae_assay_precision.bridge import qualify_bridge

    _check_runtime_versions(torch.__version__, torch.version.cuda, transformers.__version__)
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Qualification requires exactly one CUDA GPU")
    repair = checks("cuda")
    bridge = qualify_bridge("cuda")
    return {"pass": repair.get("pass") is True and bridge.get("pass") is True,
            "device": "cuda", "repair": repair, "precision_bridge": bridge,
            "arithmetic_flags": arithmetic_flags,
            "scope": "Tiny random BF16 Llama checks before pretrained loading; not 70B qualification"}


class ExposureRun(Run):
    def __init__(self, plan, plan_path, freeze, out, deadline, cache=None, *,
                 hourly_usd, pod_started_utc, barriers=True, factory=ExposureBackend,
                 clock=time.time, monotonic=time.monotonic, qualifier=synthetic_qualification):
        self.token_inventory = analysis.checked_design(plan)
        self.budget = checked_budget(plan)
        if json.loads(Path(plan_path).read_text()) != plan:
            raise ValueError("Runtime plan differs from on-disk plan")
        self.plan, self.plan_hash, self.freeze = plan, sha(plan_path), freeze
        self.out, self.cache, self.clock = Path(out), cache, clock
        self.deadline = _utc(deadline).timestamp()
        self.pod_started = _utc(pod_started_utc).timestamp()
        self.rate = _number(hourly_usd)
        if self.rate <= 0 or not self.pod_started < self.deadline <= self.pod_started + 7200 - RETRIEVAL_SECONDS:
            raise ValueError("Invalid all-in hourly rate or bounded deadline")
        if self.rate * Decimal(7200) / 3600 > self.budget["exposure_max_usd"]:
            raise ValueError("Full pod timer including retrieval is not funded")
        self.barriers, self.factory, self.qualifier = barriers, factory, qualifier
        self.backend, self.precision = None, None
        self._verified_backend = None
        self.monotonic, self.wall0, self.mono0 = monotonic, clock(), monotonic()
        self.last_wall, self.last_mono = self.wall0, self.mono0
        self.out.mkdir(parents=True, exist_ok=True)
        self.ledger = EventLedger(self.out / "receipts.jsonl", self.plan_hash, freeze, inventory(plan))
        self.ledger.bind("runtime", {"kind": "runtime", "deadline_utc": deadline,
                                   "pod_started_utc": pod_started_utc, "hourly_usd": str(self.rate),
                                   "scope": plan["scope"], "budget": plan["budget"]})
        self.completed = {e["data"]["row_id"]: e["data"]["payload"] for e in self.ledger.read()
                          if e["data"].get("kind") == "row"}
        self._audited = set()
        self.audit(full=True)

    def check_time(self, seconds=300):
        super().check_time(seconds)
        now, mono = self.clock(), self.monotonic()
        if now < max(self.pod_started, self.last_wall) or mono < self.last_mono:
            raise ValueError("Exposure accounting clock moved backward")
        self.last_wall, self.last_mono = now, mono
        elapsed = max(now - self.pod_started, self.wall0 - self.pod_started + mono - self.mono0)
        projected = _number(elapsed + seconds + RETRIEVAL_SECONDS) * self.rate / 3600
        if (elapsed + seconds >= self.deadline - self.pod_started
                or projected > self.budget["exposure_max_usd"]
                or PRIOR_TOTAL + projected > self.budget["total_usd"]):
            raise TimeoutError("Exposure budget/deadline reached; retrieval reserve protected")
        return {"elapsed_seconds": elapsed, "projected_usd": str(projected)}

    def model(self, precision="bf16"):
        if precision != "bf16":
            raise ValueError("Clean screening cannot change model precision")
        backend = super().model(precision)
        if backend is not self._verified_backend:
            write_once(self.out / "tokenizer-verification.json", backend.verify_tokenizer(self.plan))
            self._verified_backend = backend
        return backend

    def audit(self, full=False):
        self.ledger.read()
        for rid, receipt in self.completed.items():
            if full or rid not in self._audited:
                path = self.out / "rows" / (rid + ".json")
                if receipt["path"] != path.relative_to(self.out).as_posix() or sha(path) != receipt["sha256"]:
                    raise ValueError("Raw row hash/path changed")
                row = json.loads(path.read_text())
                if rid == "qualification-live":
                    analysis.validate_qualification(row, self.plan_hash, self.freeze)
                else:
                    item = next(item for item in self.plan["texts"] if "clean-" + item["id"] == rid)
                    analysis.validate_row(row, item, self.token_inventory[item["id"]],
                                          plan_sha256=self.plan_hash, freeze_commit=self.freeze)
                    analysis.validate_capture(self.out, row)
                self._audited.add(rid)

    def qualify(self):
        if "qualification-live" not in self.completed:
            self.check_time(900)
            synthetic = self.qualifier()
            write_once(self.out / "cheap-qualification.json", synthetic)
            if synthetic.get("pass") is not True:
                raise RuntimeError("Synthetic same-GPU qualification failed")
        def operation():
            backend = self.model()
            return {"id": "qualification-live", "plan_sha256": self.plan_hash,
                    "freeze_commit": self.freeze, **backend.qualify(self.plan["target_feature_ids"])}
        self.row("qualification-live", operation,
                 lambda value: analysis.validate_qualification(value, self.plan_hash, self.freeze))
        self.barrier("qualification")

    def screen(self, item):
        expected_index = self.plan["texts"].index(item)
        rid = "clean-" + item["id"]
        required = ["qualification-live"] + inventory(self.plan)[1:expected_index + 1]
        if not all(identifier in self.completed for identifier in required):
            raise ValueError("Exposure rows must follow qualification and fixed corpus order")
        if self.barriers:
            for name in (["qualification"] if expected_index < 5 else ["qualification", "first-five"]):
                approval = self.out / ("APPROVE-" + name)
                if not approval.is_file() or approval.read_text().strip() != self.plan_hash:
                    raise ValueError("Missing plan-bound " + name + " approval")
        def operation():
            backend = self.model()
            path = self.out / "residuals" / (item["id"] + ".safetensors")
            if path.exists():
                raise ValueError("Refusing to replace orphaned residual capture")
            result = backend.screen(item, self.token_inventory[item["id"]],
                                    self.plan["target_feature_ids"], path)
            return {"schema": analysis.SCHEMA, "id": rid, "text_id": item["id"],
                    "split": item["split"], "family": item["family"], "category": item["category"],
                    "text_sha256": exposure.text_digest(item["text"]),
                    "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                    "feature_ids": self.plan["target_feature_ids"], "encoding_authority": analysis.AUTHORITY,
                    "capture": {"path": path.relative_to(self.out).as_posix(),
                                "sha256": sha(path), "bytes": path.stat().st_size}, **result}
        def validate(value):
            analysis.validate_row(value, item, self.token_inventory[item["id"]],
                                  plan_sha256=self.plan_hash, freeze_commit=self.freeze)
            analysis.validate_capture(self.out, value)
        return self.row(rid, operation, validate)

    def artifact_inventory(self):
        files = []
        for path in sorted(self.out.rglob("*")):
            if path.name == "ARTIFACTS.json" or not path.is_file():
                continue
            if path.is_symlink():
                raise ValueError("Symlink in output inventory")
            files.append({"path": path.relative_to(self.out).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha(path)})
        return {"schema": "sae_exposure_artifacts_v1", "plan_sha256": self.plan_hash,
                "freeze_commit": self.freeze, "files": files,
                "scope": "terminal worker snapshot; inventory excludes itself and later controller artifacts"}

    def execute(self):
        terminal = self.out / "DONE-all.json"
        if terminal.exists():
            done = json.loads(terminal.read_text())
            if (done.get("status") != "complete" or done.get("plan_sha256") != self.plan_hash
                    or done.get("freeze_commit") != self.freeze):
                raise RuntimeError("Prior terminal failure/incompletion requires explicit recovery")
            analysis.audit_run(self.out, self.plan, self.plan_hash, self.freeze)
            pilot = done.get("precision_pilot", {})
            if "precision_pilot" in self.plan:
                path = self.out / "precision-pilot-summary.json"
                if (pilot.get("status") != "complete" or pilot.get("summary_path") != path.name
                        or not path.is_file() or sha(path) != pilot.get("summary_sha256")):
                    raise ValueError("Terminal precision pilot summary missing or changed")
                if pilot.get("artifacts") != self.pilot_inventory():
                    raise ValueError("Terminal precision pilot artifacts missing or changed")
            elif pilot != {"status": "not_planned"}:
                raise ValueError("Unplanned terminal precision pilot")
            return
        status, pilot = "failed_or_incomplete", None
        try:
            self.qualify()
            for i, item in enumerate(self.plan["texts"], 1):
                self.screen(item)
                if i == 5:
                    rows = analysis.audit_run(self.out, self.plan, self.plan_hash, self.freeze, complete=False)
                    write_once(self.out / "first-five-audit.json", {
                        "structural_pass": True, "exposure_rows": len(rows),
                        "ids": [row["text_id"] for row in rows], "plan_sha256": self.plan_hash,
                        "freeze_commit": self.freeze, "scientific_exposure_gate_applied": False})
                    self.barrier("first-five")
            rows = analysis.audit_run(self.out, self.plan, self.plan_hash, self.freeze)
            write_once(self.out / "summary.json", analysis.summarize(
                rows, self.plan, plan_sha256=self.plan_hash, freeze_commit=self.freeze))
            if "precision_pilot" in self.plan:
                from experiments.sae_assay_precision.pilot import run_pilot
                self.check_time(900)
                pilot = run_pilot(self.model(), self.plan, self.plan_hash, self.freeze,
                                  self.out, self.deadline)
                if not isinstance(pilot, dict):
                    raise ValueError("Precision pilot must return its completed summary")
                self.check_time(0)
                write_once(self.out / "precision-pilot-summary.json", pilot)
                if not self.pilot_inventory():
                    raise ValueError("Planned precision pilot wrote no artifacts")
            status = "complete"
        except BaseException as exc:
            status = "incomplete_budget_deadline" if isinstance(exc, TimeoutError) else "technical_failure"
            write_once(self.out / "failure.json", {"type": type(exc).__name__, "message": str(exc),
                                                  "status": status, "plan_sha256": self.plan_hash,
                                                  "freeze_commit": self.freeze})
            raise
        finally:
            if self.backend is not None:
                self.backend.close()
            write_once(terminal, {"status": status, "rows": len(self.completed),
                                  "exposure_rows": sum(r.startswith("clean-") for r in self.completed),
                                  "plan_sha256": self.plan_hash, "freeze_commit": self.freeze,
                                  "precision_pilot": ({"status": "complete",
                                      "summary_path": "precision-pilot-summary.json",
                                      "summary_sha256": sha(self.out / "precision-pilot-summary.json"),
                                      "artifacts": self.pilot_inventory()}
                                      if pilot is not None and status == "complete" else
                                      {"status": "not_completed" if "precision_pilot" in self.plan else "not_planned"}),
                                  "behavioral_assay_qualified": False})
            write_once(self.out / "ARTIFACTS.json", self.artifact_inventory())

    def pilot_inventory(self):
        result = []
        for path in sorted((self.out / "precision_pilot").rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink in precision pilot inventory")
            if path.is_file():
                result.append({"path": path.relative_to(self.out).as_posix(),
                               "bytes": path.stat().st_size, "sha256": sha(path)})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "out", "cache"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("freeze", "deadline-utc", "hourly-usd", "pod-started-utc"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    from .protocol import load_plan
    plan = load_plan(args.plan, args.freeze)
    ExposureRun(plan, args.plan, args.freeze, args.out, args.deadline_utc, args.cache,
                hourly_usd=args.hourly_usd, pod_started_utc=args.pod_started_utc).execute()


if __name__ == "__main__":
    main()
