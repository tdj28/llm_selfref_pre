"""Synthetic CPU/mocked tests only; these do not establish CUDA qualification."""
from copy import deepcopy
from contextlib import contextmanager
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from experiments.kolibri_bootstrap_a3 import adapter as a, smoke as s, production as p
from experiments import kolibri_judge_transport as t
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_swap import production as prod, protocol, gpu_smoke as old, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from tests.test_kolibri_swap_production import FREEZE, NOW, write, tree_hashes, saved_controller, rechain_controller, finish_controller
from tests.test_kolibri_swap_controller import Clock, FakeAPI, saved_retrieval
from tests.test_kolibri_swap_runtime import senders, receipt
from tests.test_kolibri_judge_transport import TIMEOUT, filtered, judge_one, flaky

CARRY = "0.54409303377917539333333334"


def test_worker_delta_only_selects_a3_inspector_and_preserves_tools():
    source = a2.worker_script("cheap", FREEZE, protocol.PLAN, 900)
    result = a.worker_script("cheap", FREEZE, protocol.PLAN, 900)
    assert result.replace("experiments.kolibri_bootstrap_a3.smoke", "experiments.kolibri_swap.gpu_smoke") == source
    assert subprocess.run(["bash", "-n"], input=result, text=True, capture_output=True).returncode == 0
    assert a.worker_script("main", FREEZE, protocol.PLAN, 900) == a2.worker_script("main", FREEZE, protocol.PLAN, 900)


def test_unknown_role_cannot_contact_provider():
    api = Mock(side_effect=AssertionError("no calls"))
    for kind in ("other", ""):
        with pytest.raises(Halted, match="Unknown pod role"):
            a.Controller(FREEZE, kind, api)
    assert not api.called


@pytest.fixture
def linear():
    import torch
    class Method:
        block_quant = True
        weight_block_size = [128, 128]
        quant_config = NS(is_checkpoint_fp8_serialized=True)

    class SyntheticMarlin:
        block_quant, size_k_first, marlin_input_dtype = True, False, None

        def process_weights_after_loading(self, layer):
            # Deliberately synthetic reversible packing, not a CUDA operator test.
            layer.weight = torch.nn.Parameter(layer.weight.view(torch.int32), requires_grad=False)
            layer.weight_scale_inv = torch.nn.Parameter(layer.weight_scale_inv.to(torch.bfloat16) * 2,
                                                        requires_grad=False)

    tensors = {"a.weight": torch.arange(128 * 128).reshape(128, 128).remainder(8).float().to(torch.float8_e4m3fn),
               "a.weight_scale_inv": torch.ones(1, 1, dtype=torch.float32) / 128}
    return torch, Method, SyntheticMarlin, tensors


def make_linear(fixture, packed):
    torch, method, marlin, tensors = fixture
    layer = s.reference_layer(tensors, ["a"], "cpu")
    layer.quant_method = method()
    layer.quant_method.use_marlin = packed
    layer.quant_method.fp8_linear = marlin() if packed else NS()
    if packed:
        layer.quant_method.fp8_linear.process_weights_after_loading(layer)
        layer.workspace = NS(is_cuda=True, numel=lambda: 64, dtype=torch.int32)
    return layer, s.reference_layer(tensors, ["a"], "cpu")


@pytest.mark.parametrize("packed", [False, True])
def test_exact_checkpoint_and_operator_reconstruction_not_dtype_allowlist(linear, packed):
    torch, method, marlin, _ = linear
    layer, reference = make_linear(linear, packed)
    before = {name: tensor.detach().clone() for name, tensor in layer.named_parameters()}
    row = s.check_linear("synthetic.qkv", layer, reference, method, marlin)
    assert row["exact_checkpoint_reconstruction"] and row["storage"].startswith("official_marlin" if packed else "native")
    for name, tensor in layer.named_parameters():
        s.same_tensor(tensor, before[name], name)


@pytest.mark.parametrize("mutation", ["weight", "scale", "scale_dtype", "bf16_weight", "unknown_int32",
                                    "wrong_method", "serialized", "block", "geometry", "original_dtype",
                                    "marlin_mode", "workspace", "use_marlin"])
def test_packed_tamper_and_bf16_fallback_fail(linear, mutation):
    torch, method, marlin, _ = linear
    layer, reference = make_linear(linear, True)
    if mutation == "weight":
        layer.weight.data[0, 0] ^= 1
    elif mutation == "scale":
        layer.weight_scale_inv.data *= 2
    elif mutation == "scale_dtype":
        layer.weight_scale_inv = torch.nn.Parameter(layer.weight_scale_inv.float(), requires_grad=False)
    elif mutation == "bf16_weight":
        layer.weight = torch.nn.Parameter(layer.weight.to(torch.bfloat16), requires_grad=False)
    elif mutation == "unknown_int32":
        layer.quant_method.fp8_linear = NS()
        layer.quant_method.use_marlin = False
    elif mutation == "wrong_method":
        layer.quant_method = NS()
    elif mutation == "serialized":
        layer.quant_method.quant_config = NS(is_checkpoint_fp8_serialized=False)
    elif mutation == "block":
        layer.quant_method.weight_block_size = [64, 64]
    elif mutation == "geometry":
        layer.input_size_per_partition += 128
    elif mutation == "original_dtype":
        layer.orig_dtype = torch.float16
    elif mutation == "marlin_mode":
        layer.quant_method.fp8_linear.marlin_input_dtype = torch.float8_e4m3fn
    elif mutation == "workspace":
        layer.workspace.is_cuda = False
    else:
        layer.quant_method.use_marlin = False
    with pytest.raises(ValueError):
        s.check_linear("synthetic.qkv", layer, reference, method, marlin)


def test_diagnostics_include_all_modules_and_scale_shapes_before_assertions(linear):
    torch, _, _, _ = linear
    model = torch.nn.Module()
    model.qkv, _ = make_linear(linear, True)
    model.down, _ = make_linear(linear, False)
    records = s.diagnostics(model)
    assert [row["name"] for row in records] == ["", "qkv", "down"]
    assert records[1]["tensors"]["weight"]["dtype"] == "torch.int32"
    assert records[1]["tensors"]["weight_scale_inv"]["shape"] == [1, 1]
    assert "SyntheticMarlin" in records[1]["linear_kernel"]
    assert "Method" in records[1]["quant_method"]


@pytest.mark.parametrize("mutation", ["bf16", "negative", "nan", "scale_shape"])
def test_reference_rejects_non_fp8_or_bad_scales(linear, mutation):
    torch, _, _, tensors = linear
    if mutation == "bf16":
        tensors["a.weight"] = tensors["a.weight"].to(torch.bfloat16)
    elif mutation == "scale_shape":
        tensors["a.weight_scale_inv"] = torch.ones(2, 2)
    else:
        tensors["a.weight_scale_inv"][0, 0] = -1 if mutation == "negative" else float("nan")
    with pytest.raises(ValueError):
        s.reference_layer(tensors, ["a"], "cpu")


def test_qkv_and_gate_up_checkpoint_order_is_explicit():
    layer = NS(self_attn=NS(qkv_proj="qkv", o_proj="o"),
               mlp=NS(shared_experts=NS(gate_up_proj="gateup", down_proj="down")))
    rows = list(s.linear_specs(NS(model=NS(layers=[layer]))))
    assert rows[0][2] == ["model.layers.0.self_attn." + c + "_proj" for c in "qkv"]
    assert rows[2][2] == ["model.layers.0.mlp.shared_experts." + c + "_proj" for c in ("gate", "up")]


@pytest.mark.parametrize("passed", [True, False])
def test_atomic_full_report_keeps_named_failure_and_never_overwrites(tmp_path, monkeypatch, passed):
    path = tmp_path / "gpu-smoke.json"
    def qualify(root, mode, scratch, result):
        assert not path.exists()
        result["gpu"] = {"workers": [{"status": "passed" if passed else "failed",
                                      "modules": [{"name": "layer0.qkv"}], "linear_errors": ["synthetic"]}]}
        if passed:
            result["status"] = "passed"
        else:
            raise ValueError("Named worker failed")
    monkeypatch.setattr(s, "qualify", qualify)
    argv = ["--_worker", "--out", str(path), "--upstream", str(tmp_path)]
    assert s.main(argv) == (0 if passed else 1)
    value = json.loads(path.read_bytes())
    assert value["gpu"]["workers"][0]["modules"] == [{"name": "layer0.qkv"}]
    assert value["scientific_generation"] is False and value["timeout_seconds"] == 900
    before = path.read_bytes()
    with pytest.raises(ValueError, match="overwritten"):
        s.main(argv)
    assert path.read_bytes() == before and not list(tmp_path.glob("*.complete"))


def test_absolute_deadline_still_kills_worker_process_group(tmp_path, monkeypatch):
    process = Mock(pid=123)
    process.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 9), -9]
    popen, kill = Mock(return_value=process), Mock()
    monkeypatch.setattr(s.subprocess, "Popen", popen)
    monkeypatch.setattr(s.os, "killpg", kill)
    result = s.bounded_worker(tmp_path, "gpu", tmp_path, 9)
    assert result["status"] == "timeout"
    kill.assert_called_once_with(123, s.signal.SIGKILL)
    assert popen.call_args.kwargs["start_new_session"]
    assert "experiments.kolibri_bootstrap_a3.smoke" in popen.call_args.args[0]
    assert popen.call_args.kwargs["env"]["VLLM_USE_DEEP_GEMM_E8M0"] == "0"


def predecessor_fixture(tmp_path, monkeypatch):
    root = tmp_path / "a2"
    directory = root / "controller/cheap/retrievals/synthetic"
    write(directory / "gpu-smoke.json", {"status": "failed", "scientific_generation": False,
          "parser": {"official_passed": 70},
          "error": "Exception: Call to collective_rpc method failed: Linear is not FP8"})
    write(directory / "exit.json", {"exit_code": 1})
    (directory / "worker.log").write_text("Selected MarlinFP8ScaledMMLinearKernel for Fp8LinearMethod\n")
    write(root / "controller/cheap/final-retrieval.json", {"data": {"directory": str(directory)}})
    write(root / "controller/cheap/events.jsonl", {"synthetic": "closed"})
    monkeypatch.setattr(a2, "root", lambda: root)
    monkeypatch.setattr(a, "WORKER_SHA", protocol.sha(directory / "worker.log"))
    receipt = {"cost_usd": "0.3375595773666666666666666667", "closed_sha256": a.CLOSED_SHA,
               "retrieval_sha256": a.RETRIEVAL_SHA}
    monkeypatch.setattr(prod, "closed_receipt", lambda *args: deepcopy(receipt))
    monkeypatch.setattr(prod, "controller_events", lambda *args: ([], {"closed": {"data": {"pod_id": a.FAILED_POD}}}))
    prior = {"predecessor": {"exact_sum_usd": "0.20653345641250872666666666663",
                            "cost_usd": "0.20653345641250872666666667", "attempts": [{"synthetic": 0}, {"synthetic": 1}]}}
    return root, receipt, prior


def test_predecessor_keeps_three_attempts_and_prior_rounding(tmp_path, monkeypatch):
    root, receipt, prior = predecessor_fixture(tmp_path, monkeypatch)
    before = tree_hashes(root)
    result = a.predecessor(prior)
    assert len(result["attempts"]) == 3
    assert result["exact_sum_usd"] == "0.54409303377917539333333333333"
    assert result["prior_admission_plus_latest_usd"] == "0.5440930337791753933333333367"
    assert result["cost_usd"] == CARRY
    assert result["attempts"][-1]["cost_usd"] == receipt["cost_usd"]
    assert tree_hashes(root) == before
    receipt["closed_sha256"] = "0" * 64
    with pytest.raises(Halted, match="preserved"):
        a.predecessor(prior)


@pytest.mark.parametrize("spent,passes", [(".50", True), (".70", False)])
def test_all_prior_failures_count_toward_cleanup_and_cap(monkeypatch, spent, passes):
    ctl = object.__new__(a.Controller)
    ctl.kind, ctl.amendment = "cheap", {"predecessor": {"cost_usd": CARRY}}
    monkeypatch.setattr(a.old.Controller, "cost_check", lambda *args: Decimal(spent))
    if passes:
        assert ctl.cost_check({"cost": ".74"}) == Decimal(spent)
    else:
        with pytest.raises(Halted, match="Cumulative cheap"):
            ctl.cost_check({"cost": ".74"})


def test_owned_lifecycle_new_root_and_all_failed_pods_excluded(tmp_path, monkeypatch):
    plan = protocol.verify(protocol.ROOT / protocol.PLAN)
    body = (protocol.ROOT / protocol.PLAN).read_bytes()
    repo, base = tmp_path / "repo", tmp_path / "run"
    write(repo / a.AMENDMENT, {"predecessor": {"cost_usd": CARRY}})
    monkeypatch.setattr(protocol, "ROOT", repo)
    amendment = prod.load(repo / a.AMENDMENT)
    monkeypatch.setattr(a, "verify", lambda freeze: amendment)
    monkeypatch.setattr(protocol, "verify", lambda path: plan)
    monkeypatch.setattr(a.old, "canonical_root", lambda: base)
    monkeypatch.setattr(a.old, "quote", lambda api, kind: {"hourly_rate_usd": ".74", "storage_hourly_usd": ".10"})
    monkeypatch.setattr(a.old.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(body))
    key = repo / "synthetic-key"
    key.write_text("synthetic fixture, not a credential")
    key.with_suffix(".pub").write_text("ssh-ed25519 AAAA synthetic")
    monkeypatch.setattr(a.old.base, "KEY", key)
    clock = Clock()
    class API(FakeAPI):
        def request(self, method, path, body=None):
            status, value = super().request(method, path, body)
            if method == "POST":
                self.pod["cost"] = value["cost"] = ".74"
            return status, value
    api = API(clock)
    ctl = a.Controller(FREEZE, "cheap", api, clock=clock, sleep=clock.sleep)
    assert ctl.base == base / "bootstrap-a3/controller/cheap"
    for pod in (a.FAILED_POD, a2.FAILED_POD, a1.FAILED_POD):
        assert not ctl._new_pod({"id": pod}, {})
    ctl._ssh = Mock(side_effect=lambda pod, command, **kwargs: b"ready" if command == "printf ready" else b"dispatched")
    ctl.launch()
    upload = next(call.kwargs["data"] for call in ctl._ssh.call_args_list if "data" in call.kwargs)
    assert b"experiments.kolibri_bootstrap_a3.smoke" in upload
    assert api.calls.count(("POST", "/pods")) == 1
    with pytest.raises(ValueError, match="already attempted"):
        ctl.launch()
    saved_retrieval(ctl)
    clock.sleep(60)
    assert ctl.terminate()["data"]["get_status"] == 404


def test_candidate_and_tamper_are_offline_only(tmp_path, monkeypatch):
    prior = {"dependency_source_hashes": {}, "source_hashes": {}, "known_technical_outcomes": []}
    monkeypatch.setattr(a2, "verify", lambda: prior)
    monkeypatch.setattr(t, "verify", lambda path: prod.load(path))
    monkeypatch.setattr(a, "predecessor", lambda prior: {"cost_usd": CARRY})
    result = a.build()
    assert result["science_changed"] is result["research_outcomes_observed"] is False
    assert result["cheap_remaining_usd"] == "0.70590696622082460666666666"
    assert result["tiny_checkpoint_forward_and_kernels_changed"] is False
    monkeypatch.setattr(protocol, "ROOT", tmp_path)
    write(tmp_path / a.AMENDMENT, {"tampered": True})
    monkeypatch.setattr(a, "build", lambda: result)
    with pytest.raises(Halted, match="binding differs"):
        a.verify(FREEZE)


def test_frozen_original_a1_a2_and_judge_sources_unchanged():
    from experiments import kolibri_judge_transport as transport
    records = [prod.load(protocol.ROOT / path) for path in (protocol.PLAN, a1.AMENDMENT, a2.AMENDMENT, transport.PLAN)]
    hashes = {name: digest for record in records for name, digest in record["source_hashes"].items()}
    assert len(hashes) == 102
    assert all(protocol.sha(protocol.ROOT / name) == digest for name, digest in hashes.items())


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    original = protocol.ROOT
    plan = protocol.verify(original / protocol.PLAN)
    repo, root = tmp_path / "repo", tmp_path / "run/bootstrap-a3"
    for name in (*t.SOURCES, t.PLAN, protocol.PLAN):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes((original / name).read_bytes())
    (repo / "bridge.py").write_text("# Synthetic A3 binding, not production source\n")
    policy = prod.load(repo / t.PLAN)
    amendment = {"source_hashes": {"bridge.py": protocol.sha(repo / "bridge.py")},
        "dependency_source_hashes": {}, "predecessor": {"cost_usd": CARRY},
        "judge_policy": {"freeze": a.JUDGE_FREEZE, "path": t.PLAN, "sha256": protocol.sha(repo / t.PLAN),
                         "original_worker_freeze": a.A2_FREEZE, "policy_changed": False}}
    write(repo / a.AMENDMENT, amendment)
    monkeypatch.setattr(protocol, "ROOT", repo)
    return plan, root, amendment, policy


def qualified_controller(root, plan_hash, amendment):
    ledger = saved_controller(root, "cheap", closed=True, plan_hash=plan_hash)
    ledger.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT),
        "prior_cheap_usd": CARRY, "a2_freeze": a.A2_FREEZE})
    base = root / "controller/cheap"
    path = base / "retrievals/synthetic/gpu-smoke.json"
    value = prod.load(path)
    value.update(amendment="kolibri-bootstrap-a3-v1", parser={"official_passed": 70, "skipped": 0})
    value["gpu"].update(llm_options=old.LLM_OPTIONS, checkpoint={"fp8_matrices": 186},
        forward=[{"tokens": 8, "prompt_tokens": len(prompt)} for prompt in old.PROMPTS],
        workers=[{"status": "passed", "linear_errors": [], "layers": 6, "custom_routing_layers": 6,
                  "fp8_weights": True, "checkpoint_fp32_block_scales": True,
                  "modules": [{"name": "synthetic"}], "operator_sources": {"synthetic": "f" * 64},
                  "linears": [{"name": f"model.layers.{i}.{name}", "storage": "official_marlin_e4m3fn_packed_int32",
                               "exact_checkpoint_reconstruction": True} for i in range(6) for name in
                               ("self_attn.qkv_proj", "self_attn.o_proj", "mlp.shared_experts.gate_up_proj",
                                "mlp.shared_experts.down_proj")]}])
    write(path, value)
    rows = ledger.read()
    next(row for row in rows if row["id"] == "retrieval:6")["data"]["artifacts"]["gpu-smoke.json"] = protocol.sha(path)
    rechain_controller(base, rows)
    return value


def main_controller(root, plan_hash):
    ledger = saved_controller(root, "main", plan_hash=plan_hash)
    ledger.bind("controller:config", {"amendment_sha256": protocol.sha(protocol.ROOT / a.AMENDMENT),
        "prior_cheap_usd": CARRY, "a2_freeze": a.A2_FREEZE})
    return ledger


@contextmanager
def opened_bridge(bridge, local=None, judge=None):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", FREEZE, digest) as receipts:
        binding = p.bridge_binding(FREEZE, amendment, policy)
        if receipts.decision("judge_transport") is None:
            receipts.append("decision", {"name": "judge_transport", "value": binding})
        runner = p.Runner(plan, FREEZE, digest, ledger, receipts, local, judge,
                          amendment=amendment, transport_plan=policy, sleep=Mock())
        yield runner


@pytest.mark.parametrize("mutation", [None, "missing", "failed", "old_amendment", "no_modules", "linear",
                                    "forward", "carry", "GET200", "hash"])
def test_main_creation_requires_exact_a3_pass_and_get404(bridge, mutation):
    plan, root, amendment, _ = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    value = qualified_controller(root, digest, amendment)
    base, path = root / "controller/cheap", root / "controller/cheap/retrievals/synthetic/gpu-smoke.json"
    rows, _ = prod.controller_events(root, "cheap", digest, FREEZE)
    if mutation == "missing":
        path.unlink()
    elif mutation in {"failed", "old_amendment", "no_modules", "linear", "forward", "hash"}:
        if mutation in {"failed", "hash"}:
            value["status"] = "failed"
        elif mutation == "old_amendment":
            value["amendment"] = "kolibri-bootstrap-a2-v1"
        elif mutation == "no_modules":
            value["gpu"]["workers"][0]["modules"] = []
        elif mutation == "linear":
            value["gpu"]["workers"][0]["linears"].pop()
        else:
            value["gpu"]["forward"].pop()
        write(path, value)
        if mutation != "hash":
            next(row for row in rows if row["id"] == "retrieval:6")["data"]["artifacts"]["gpu-smoke.json"] = protocol.sha(path)
    elif mutation == "carry":
        next(row for row in rows if row["id"] == "controller:config")["data"]["prior_cheap_usd"] = "0"
    elif mutation == "GET200":
        next(row for row in rows if row["id"] == "closed")["data"]["get_status"] = 200
    rechain_controller(base, rows)
    ctl = object.__new__(a.Controller)
    ctl.out, ctl.freeze, ctl.plan_hash, ctl.amendment = root, FREEZE, digest, amendment
    ctl.kind, ctl.api, ctl.event = "main", Mock(writable=True), Mock(return_value=None)
    if mutation is None:
        before = tree_hashes(root)
        assert ctl.cheap_pass()["cost_usd"] == "0.25"
        assert tree_hashes(root) == before
    else:
        with pytest.raises((Halted, ValueError, OSError)):
            ctl.launch()
        ctl.api.inventory.assert_not_called()
        ctl.api.request.assert_not_called()


@pytest.mark.parametrize("mode", ["retry", "refusal", "external_stop"])
def test_bridge_reuses_exact_retry_missing_and_external_stop_safeguards(bridge, mode):
    _, good, _, _ = senders()
    seen = []
    holder = {}
    def sender(request):
        seen.append(request)
        if len(seen) == 1:
            if mode == "external_stop":
                holder["runner"].stop.set()
            return receipt(filtered(request, good)) if mode == "refusal" else TIMEOUT
        return good(request)
    with opened_bridge(bridge, judge=sender) as runner:
        holder["runner"] = runner
        runner.guard = Mock()
        if mode == "external_stop":
            with pytest.raises(Halted):
                judge_one(runner)
            assert len(seen) == 1 and runner.stop.is_set()
        else:
            result = judge_one(runner)
            assert result["status"] == ("ok" if mode == "retry" else "incomplete_judge")
            assert len(seen) == (2 if mode == "retry" else 1)
            report = runner.audit()
            assert report["physical_unresolved"] == 1
            assert report["terminal_refusal_calls"] if mode == "refusal" else report["pass"]
        for row in runner.receipts.records().values():
            assert row["metadata"]["freeze"] == FREEZE
            if "transport_retry" in row["metadata"]:
                assert row["metadata"]["transport_retry"]["operational_freeze"] == a.JUDGE_FREEZE
        assert runner._exchange.__func__ is t.Runner._exchange
        assert runner.logical_reader.__func__ is t.Runner.logical_reader


def test_full_owned_chain_generates_main_before_stop_retrieval_and_judge_tail(bridge):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    qualified_controller(root, digest, amendment)
    main = main_controller(root, digest)
    local, judge, generated, judged = senders()
    with opened_bridge(bridge, local, judge) as runner:
        runner.guard = a.StudyGuard(root, plan, FREEZE, digest, runner.ledger, amendment=amendment, clock=lambda: NOW)
        baseline = prod.StudyGuard(root, plan, FREEZE, digest, runner.ledger, clock=lambda: NOW)
        assert runner.guard.state()["gpu_usd"] == baseline.state()["gpu_usd"] + Decimal(CARRY)
        assert prod.phase(runner, "fixtures", root)["pass"]
        assert prod.phase(runner, "generate-screen-initial", root)["generation_calls"] == 12
        with pytest.raises(Halted):
            prod.phase(runner, "generate-screen", root)
        assert prod.phase(runner, "judge-screen-initial", root)["pass"]
        assert prod.phase(runner, "generate-screen", root)["generation_calls"] == 72
        assert prod.phase(runner, "judge-screen", root)["eligible_models"] == ["kolibri"]
        assert prod.phase(runner, "main-admission", root)["fits"]
        before_judges = len(judged)
        runner.sender = None
        assert prod.phase(runner, "generate-main", root)["generation_calls"] == 384
        assert len(generated) == 457 and len(judged) == before_judges
        assert prod.phase(runner, "stop-server", root)["deletion_verified"] is False
        assert (root / "controller/main/STOP_SERVER").is_file()
        with pytest.raises((Halted, KeyError)):
            prod.phase(runner, "judge-main", root)
        assert len(judged) == before_judges
        finish_controller(root, "main", main, plan_hash=digest)
        runner.sender = judge
        assert prod.phase(runner, "judge-main", root)["complete"]
        assert runner.audit()["generation_calls"] == 457
        write(root / "collection/runtime.json", prod.binding(plan, FREEZE, digest))
        for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", a.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
            p.save_bytes(root / "collection" / name, (protocol.ROOT / source).read_bytes())
    before = tree_hashes(root)
    with p.saved_runner(root, plan, digest, amendment, policy, FREEZE) as reader:
        assert reader.audit()["pass"] and len(reader.rows("main")) == 256
    assert tree_hashes(root) == before


@pytest.mark.parametrize("mutation", ["bridge_source", "judge_policy", "amendment", "worker_binding"])
def test_bridge_tamper_blocks_replay_or_dispatch(bridge, mutation):
    _, root, amendment, policy = bridge
    with opened_bridge(bridge) as runner:
        if mutation == "bridge_source":
            (protocol.ROOT / "bridge.py").write_text("# changed synthetic source\n")
        elif mutation == "judge_policy":
            changed = deepcopy(policy)
            changed["additional_attempts"] = 3
            write(protocol.ROOT / t.PLAN, changed)
        elif mutation == "amendment":
            write(protocol.ROOT / a.AMENDMENT, {**amendment, "predecessor": {"cost_usd": "0"}})
        else:
            runner.transport_plan["worker_freeze"] = FREEZE
        with pytest.raises(Halted):
            runner.check_sources()


def test_bridge_binds_exact_saved_plan_bytes_without_rewriting_policy(bridge):
    _, _, amendment, policy = bridge
    path = protocol.ROOT / t.PLAN
    before = path.read_bytes()
    binding = p.bridge_binding(FREEZE, amendment, policy)
    assert binding["amendment_sha256"] == protocol.sha(protocol.ROOT / a.AMENDMENT)
    assert binding["judge_policy_sha256"] == protocol.sha(path)
    assert binding["judge_policy_original_worker_freeze"] == a.A2_FREEZE
    assert binding["worker_freeze"] == FREEZE and binding["judge_operational_freeze"] == a.JUDGE_FREEZE
    assert path.read_bytes() == before
    with pytest.raises(Halted, match="Bridge input"):
        p.bridge_binding(FREEZE, {**amendment, "extra": True}, policy)


def test_exact_byte_bridge_saved_replay_and_cli_are_read_only(bridge, monkeypatch):
    plan, root, amendment, policy = bridge
    digest = protocol.sha(protocol.ROOT / protocol.PLAN)
    _, judge, _, _ = senders()
    with opened_bridge(bridge, judge=judge) as runner:
        runner.guard = Mock()
        assert judge_one(runner)["status"] == "ok"
        write(root / "collection/runtime.json", prod.binding(plan, FREEZE, digest))
        for name, source in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", a.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
            p.save_bytes(root / "collection" / name, (protocol.ROOT / source).read_bytes())
    before = tree_hashes(root)
    with p.saved_runner(root, plan, digest, amendment, policy, FREEZE) as reader:
        assert reader.audit()["physical_calls"] == 1
    monkeypatch.setattr(a, "verify", lambda freeze=None: deepcopy(amendment))
    monkeypatch.setattr(t, "verify", lambda path: deepcopy(policy))
    monkeypatch.setattr(protocol, "verify", lambda path: deepcopy(plan))
    monkeypatch.setattr(prod, "local_key", Mock(side_effect=AssertionError("no credentials")))
    monkeypatch.setattr(runtime, "http_sender", Mock(side_effect=AssertionError("no HTTP")))
    assert p.main(["--freeze", FREEZE, "--run-dir", str(root), "--phase", "audit"]) == 0
    assert tree_hashes(root) == before
    prod.local_key.assert_not_called()
    runtime.http_sender.assert_not_called()
