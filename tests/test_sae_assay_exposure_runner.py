"""Offline synthetic runner tests; never load pretrained models or use APIs."""
from datetime import datetime, timezone
import json
import socket
import sys
from types import ModuleType

import pytest
import torch
from safetensors.torch import save_file

from experiments.sae_assay_exposure import runner as r, analysis as a
from tests.test_sae_assay_exposure_analysis import fixture_plan, fixture_row


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    def forbidden(*args, **kwargs):
        raise AssertionError("No network in synthetic tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class SyntheticBackend:
    metadata = {"test_only": True, "pretrained_weights": False}

    def __init__(self, precision, cache_dir):
        assert precision == "bf16"
        self.calls, self.closed, self.verifications = [], False, 0

    def verify_tokenizer(self, plan):
        self.verifications += 1
        return {"pass": True, "test_only": True}

    def qualify(self, ids):
        self.calls.append("qualification")
        return {"pass": True, "token_ids": [1, 2],
                "checks": {"clean_identity": True, "activation_identity": True,
                           "no_edit": True, "hook_removed": True}}

    def screen(self, item, certificate, ids, path):
        self.calls.append(item["id"])
        n = len(certificate["token_ids"])
        path.parent.mkdir(parents=True, exist_ok=True)
        assert not path.exists()
        hidden = torch.zeros(1, n, 8192, dtype=torch.bfloat16)
        hidden[:, :, 0] = 1
        save_file({"hidden": hidden,
                   "token_ids": torch.tensor([certificate["token_ids"]], dtype=torch.int64)}, str(path))
        raw = fixture_row(item, certificate)
        return {key: raw[key] for key in ("token_ids", "special_tokens_mask", "activations",
                                        "diagnostics", "elapsed_seconds")}

    def close(self):
        self.closed = True


def make_run(tmp_path, monkeypatch, *, barriers=False, plan=None):
    plan = fixture_plan() if plan is None else plan
    path = tmp_path / "PLAN.json"
    r.write_once(path, plan)
    now = 1_790_805_000.
    utc = lambda seconds: datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    return r.ExposureRun(plan, path, "b" * 40, tmp_path / "out", utc(now + 6000),
                         hourly_usd="6.85", pod_started_utc=utc(now - 10),
                         barriers=barriers, factory=SyntheticBackend, clock=lambda: now,
                         qualifier=lambda: {"pass": True, "test_only": True})


def approve(run, name):
    (run.out / ("APPROVE-" + name)).write_text(run.plan_hash + "\n")


def test_full_224_inventory_barriers_pilot_and_repeat_without_model_calls(tmp_path, monkeypatch):
    plan = fixture_plan()
    plan["precision_pilot"] = {"texts": [row for row in plan["texts"]
                                         if row["split"] == "discovery" and row["id"].endswith("-01")]}
    run = make_run(tmp_path, monkeypatch, barriers=True, plan=plan)
    visits = []
    def barrier(name):
        visits.append((name, len(run.completed)))
        approve(run, name)
    monkeypatch.setattr(run, "barrier", barrier)
    module = ModuleType("experiments.sae_assay_precision.pilot")
    def pilot(backend, plan, plan_hash, freeze, out, deadline):
        assert len(run.completed) == 225 and not backend.closed
        assert (out / "summary.json").is_file()
        assert len(plan["precision_pilot"]["texts"]) == 12
        r.write_once(out / "precision_pilot" / "synthetic.json", {"test_only": True})
        return {"completed": True, "scientific_pass": False, "test_only": True}
    module.run_pilot = pilot
    monkeypatch.setitem(sys.modules, module.__name__, module)
    run.execute()
    assert visits == [("qualification", 1), ("first-five", 6)]
    assert run.backend.calls == ["qualification"] + [row["id"] for row in plan["texts"]]
    assert run.backend.verifications == 1 and run.backend.closed
    report = json.loads((run.out / "summary.json").read_text())
    assert report["structural_pass"] and not report["exposure_minima_met"]
    done = json.loads((run.out / "DONE-all.json").read_text())
    assert done["status"] == "complete" and done["exposure_rows"] == 224
    assert done["precision_pilot"]["summary_sha256"] == a.sha(run.out / "precision-pilot-summary.json")
    artifacts = json.loads((run.out / "ARTIFACTS.json").read_text())["files"]
    assert len([p for p in artifacts if p["path"].startswith("rows/")]) == 225
    assert len([p for p in artifacts if p["path"].startswith("residuals/")]) == 224
    assert sum(p["bytes"] for p in artifacts if p["path"].startswith("residuals/")) < 400_000_000
    before = list(run.backend.calls)
    run.execute()
    assert run.backend.calls == before
    # An extra pilot file does not become a clean exposure observation.
    assert len(a.audit_run(run.out, plan, run.plan_hash, run.freeze)) == 224
    pilot_path = run.out / "precision_pilot" / "synthetic.json"
    pilot_original = pilot_path.read_bytes()
    pilot_path.write_bytes(pilot_original + b" ")
    with pytest.raises(ValueError, match="pilot artifacts"):
        run.execute()
    pilot_path.write_bytes(pilot_original)
    first = run.out / "rows" / ("clean-" + plan["texts"][0]["id"] + ".json")
    first.write_bytes(first.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        run.execute()


def test_barrier_approvals_block_direct_dispatch(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch, barriers=True)
    monkeypatch.setattr(run, "barrier", lambda _: None)
    run.qualify()
    with pytest.raises(ValueError, match="qualification approval"):
        run.screen(run.plan["texts"][0])
    approve(run, "qualification")
    for item in run.plan["texts"][:5]:
        run.screen(item)
    with pytest.raises(ValueError, match="first-five approval"):
        run.screen(run.plan["texts"][5])
    assert len(run.backend.calls) == 6


def test_inherited_barrier_notices_count_qualification_then_five_exposures(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch, barriers=True)
    notices = []
    def local_approval(_seconds):
        for name in ("qualification", "first-five"):
            waiting = run.out / ("WAITING-" + name + ".json")
            if waiting.exists() and not (run.out / ("APPROVE-" + name)).exists():
                notices.append(json.loads(waiting.read_text()))
                approve(run, name)
    monkeypatch.setattr(r.time, "sleep", local_approval)
    run.qualify()
    for item in run.plan["texts"][:5]:
        run.screen(item)
    run.barrier("first-five")
    assert [(v["barrier"], v["rows"]) for v in notices] == [("qualification", 1), ("first-five", 6)]
    assert all(v["plan_sha256"] == run.plan_hash and v["freeze_commit"] == run.freeze for v in notices)


def test_duplicate_dispatch_payload_is_not_hidden_by_inventory_set(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.qualify()
    run.ledger.bind("another-dispatch-id", {"kind": "dispatch", "row_id": "qualification-live"})
    with pytest.raises(ValueError, match="dispatch"):
        a.audit_run(run.out, run.plan, run.plan_hash, run.freeze, complete=False)


def test_orphan_capture_and_extra_raw_are_not_ignored(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.qualify()
    residuals = run.out / "residuals"
    residuals.mkdir()
    orphan = residuals / "unplanned.safetensors"
    orphan.write_bytes(b"synthetic orphan")
    with pytest.raises(ValueError, match="orphaned"):
        a.audit_run(run.out, run.plan, run.plan_hash, run.freeze, complete=False)
    orphan.unlink()
    r.write_once(run.out / "rows" / "unplanned.json", {"test_only": True})
    with pytest.raises(ValueError, match="unplanned raw"):
        a.audit_run(run.out, run.plan, run.plan_hash, run.freeze, complete=False)


def test_uncertain_dispatch_not_retried_and_mutated_capture_rejected(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.qualify()
    first, second = run.plan["texts"][:2]
    run.screen(first)
    rid = "clean-" + second["id"]
    run.ledger.bind("dispatch:" + rid, {"kind": "dispatch", "row_id": rid})
    calls = list(run.backend.calls)
    with pytest.raises(RuntimeError, match="Unresolved prior dispatch"):
        run.screen(second)
    assert run.backend.calls == calls
    capture = run.out / "residuals" / (first["id"] + ".safetensors")
    capture.write_bytes(capture.read_bytes() + b" ")
    with pytest.raises(ValueError, match="capture hash"):
        run.audit(full=True)


def test_failed_synthetic_qualification_stops_before_model_load(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.qualifier = lambda: {"pass": False, "test_only": True}
    with pytest.raises(RuntimeError, match="Synthetic"):
        run.execute()
    assert run.backend is None and not run.completed
    assert json.loads((run.out / "DONE-all.json").read_text())["status"] == "technical_failure"
    assert (run.out / "ARTIFACTS.json").is_file()
    with pytest.raises(RuntimeError, match="Prior terminal"):
        run.execute()


@pytest.mark.parametrize("matmul_precision,tf32", [("highest", False), ("high", True)])
def test_preload_cuda_qualification_retains_reports_and_model_math(monkeypatch, matmul_precision, tf32):
    from experiments.sae_assay_repair import qualify
    from experiments.sae_assay_precision import bridge
    calls = []
    def repair(device):
        calls.append(("repair", device))
        return {"pass": True, "checks": {"tiny_repair": True}, "raw": "synthetic"}
    def precision(device):
        calls.append(("bridge", device))
        return {"pass": False, "checks": {"tiny_bridge": False}, "raw": "synthetic"}
    monkeypatch.setattr(qualify, "checks", repair)
    monkeypatch.setattr(bridge, "qualify_bridge", precision)
    monkeypatch.setattr(r, "_check_runtime_versions", lambda *args: None)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    monkeypatch.setattr(torch, "is_autocast_enabled", lambda device: False)
    monkeypatch.setattr(torch, "get_float32_matmul_precision", lambda: matmul_precision)
    monkeypatch.setattr(torch.backends.cuda.matmul, "allow_tf32", tf32)
    result = r.synthetic_qualification()
    assert calls == [("repair", "cuda"), ("bridge", "cuda")]
    assert result["pass"] is False
    assert result["repair"]["raw"] == result["precision_bridge"]["raw"] == "synthetic"
    assert result["arithmetic_flags"] == {
        "autocast_enabled": False, "allow_tf32": tf32, "float32_matmul_precision": matmul_precision}
    assert torch.backends.cuda.matmul.allow_tf32 is tf32
    assert torch.get_float32_matmul_precision() == matmul_precision


@pytest.mark.parametrize("autocast,matmul_precision,tf32,error", [
    (False, "medium", True, "medium matmul precision"),
    (True, "highest", False, "autocast disabled"),
])
def test_arithmetic_flags_fail_before_qualifier_or_model_calls(
        tmp_path, monkeypatch, autocast, matmul_precision, tf32, error):
    from experiments.sae_assay_repair import qualify
    from experiments.sae_assay_precision import bridge
    calls = []
    def forbidden(*args, **kwargs):
        calls.append("unexpected_call")
        raise AssertionError("Invalid math flags must stop before qualification or loading")
    monkeypatch.setattr(qualify, "checks", forbidden)
    monkeypatch.setattr(bridge, "qualify_bridge", forbidden)
    monkeypatch.setattr(r, "_check_runtime_versions", forbidden)
    monkeypatch.setattr(torch, "is_autocast_enabled", lambda device: autocast)
    monkeypatch.setattr(torch, "get_float32_matmul_precision", lambda: matmul_precision)
    monkeypatch.setattr(torch.backends.cuda.matmul, "allow_tf32", tf32)
    run = make_run(tmp_path, monkeypatch)
    run.qualifier, run.factory = r.synthetic_qualification, forbidden
    with pytest.raises(ValueError, match=error):
        run.execute()
    assert calls == [] and run.backend is None and not run.completed
    assert torch.is_autocast_enabled("cuda") is autocast
    assert torch.backends.cuda.matmul.allow_tf32 is tf32
    assert torch.get_float32_matmul_precision() == matmul_precision
    failure = json.loads((run.out / "failure.json").read_text())
    assert error in failure["message"]


@pytest.mark.parametrize("reason", ["deadline", "stop", "budget", "clock", "precision"])
def test_fail_closed_before_model_load(tmp_path, monkeypatch, reason):
    run = make_run(tmp_path, monkeypatch)
    if reason == "deadline":
        run.deadline = run.clock() + 1
    elif reason == "stop":
        (run.out / "STOP").touch()
    elif reason == "budget":
        run.budget["exposure_max_usd"] = r.Decimal("0.01")
    elif reason == "clock":
        run.last_wall += 1
    with pytest.raises((ValueError, RuntimeError, TimeoutError)):
        run.model("nf4" if reason == "precision" else "bf16")
    assert run.backend is None


def test_malformed_row_preserved_without_receipt(tmp_path, monkeypatch):
    run = make_run(tmp_path, monkeypatch)
    run.qualify()
    original = run.backend.screen
    def corrupt(*args):
        value = original(*args)
        value["activations"]["22004"][1] = -1
        return value
    monkeypatch.setattr(run.backend, "screen", corrupt)
    item = run.plan["texts"][0]
    with pytest.raises(ValueError, match="numeric"):
        run.screen(item)
    assert (run.out / "rows" / ("clean-" + item["id"] + ".json")).exists()
    assert "clean-" + item["id"] not in run.completed
    assert len(list((run.out / "residuals").glob("*"))) == 1


def test_one_clean_forward_uses_audited_capture_without_teacher_or_generation(tmp_path, monkeypatch):
    from experiments.sae_assay_diagnostic.qualify import tiny_backend
    from experiments.sae_assay_diagnostic.backend import SAE_KEYS
    source = tiny_backend("cpu")
    ids = [0, 3, 5, 7, 9, 11]
    backend = r.ExposureBackend.from_components_for_test(
        source.model, source.tokenizer, dict(zip(SAE_KEYS, source._sae)),
        layer_index=source.layer_index, default_feature_ids=ids)
    backend.tokenizer.encode = lambda text, **kwargs: backend.tokenizer(text)["input_ids"][0].tolist()
    text = "abcde"
    tokens = backend.tokenizer.encode(text)
    mask = [t in backend.tokenizer.all_special_ids for t in tokens]
    calls = []
    handle = backend.model.model.register_forward_hook(lambda *_: calls.append("forward"))
    def forbidden(*args, **kwargs):
        raise AssertionError("Head/teacher/generation forbidden")
    monkeypatch.setattr(backend, "teacher", forbidden)
    monkeypatch.setattr(backend, "generate", forbidden)
    monkeypatch.setattr(backend.model.lm_head, "forward", forbidden)
    try:
        result = backend.screen({"text": text}, {"token_ids": tokens, "special_tokens_mask": mask},
                                ids, tmp_path / "tiny.safetensors")
        assert calls == ["forward"]
        assert result["token_ids"] == tokens and result["special_tokens_mask"] == mask
        assert set(result["activations"]) == {str(f) for f in ids}
        assert (tmp_path / "tiny.safetensors").is_file()
        assert not backend._layer._forward_hooks
    finally:
        handle.remove()
        backend.close()
        source.close()
