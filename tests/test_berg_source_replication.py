"""Offline/tiny-CUDA exact-path checks; never load pretrained weights."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest
import torch
from transformers import LlamaConfig, LlamaForCausalLM

from experiments.berg_source_replication import analysis, backend, controller, protocol, runner
from experiments.sae_assay_diagnostic.runner import redact_upstream_inputs
from tests.test_sae_assay_backend import TinyTokenizer
from tests.test_sae_assay_exposure_controller import FakeAPI
from tests.test_sae_assay_controller import PUBLIC_KEY


@pytest.fixture(params=[torch.float32, torch.bfloat16])
def tiny(request):
    device = os.environ.get("BERG_TEST_DEVICE", "cpu")
    if device == "cuda":
        assert torch.cuda.is_available(), "CUDA rung must not silently skip"
    with torch.random.fork_rng():
        torch.manual_seed(81)
        config = LlamaConfig(vocab_size=32, hidden_size=16, intermediate_size=32,
            num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2,
            max_position_embeddings=2048, bos_token_id=1, eos_token_id=2, pad_token_id=0,
            attention_dropout=0.)
        config._attn_implementation = "sdpa"
        model = LlamaForCausalLM(config).to(device=device, dtype=request.param).eval()
        state = {"encoder_linear.weight": torch.randn(8,16)*.2,
                 "encoder_linear.bias": torch.ones(8)*.2,
                 "decoder_linear.weight": torch.randn(16,8)*.04,
                 "decoder_linear.bias": torch.zeros(16)}
        state = {k:v.to(request.param) for k,v in state.items()}
    b = backend.Backend.from_components_for_test(model, TinyTokenizer(), state, default_feature_ids=[0,3])
    yield b
    b.close()


def test_inventory_is_exact_and_deterministic():
    rows = protocol.inventory()
    assert rows == protocol.inventory() and len(rows) == 1090
    assert sum(r["capture"] for r in rows) == 40
    assert sum(r["family"].startswith("feature-") for r in rows) == 900
    assert sum(r["family"].startswith("aggregate-") for r in rows) == 120
    assert sum(r["family"] == "baseline-bridge" for r in rows) == 70
    for feature in protocol.TARGET_IDS:
        assert len([r for r in rows if r["family"] == f"feature-{feature}"]) == 150


def test_zero_and_unhooked_generation(tiny):
    result = tiny.qualify()
    assert result["pass"]
    assert len(tiny._layer._forward_hooks) == 0


@pytest.mark.parametrize("coefficient", [-.7, -.1, 0., .1, .7])
def test_exact_additive_formula_and_telemetry(tiny, coefficient):
    arm = {"feature_ids":[0,3], "coefficient": coefficient}
    tokens = tiny._tokenize("abc")
    captured = {}
    def hook(_m,_i,out):
        captured["h"] = out[0].detach().clone()
    handle = tiny._layer.register_forward_hook(hook)
    with torch.inference_mode():
        _, records = tiny._forward(tokens, [0,3], arm)
    handle.remove()
    h = captured["h"]
    vector = (tiny._sae[2][:,0].float()+tiny._sae[2][:,3].float())*coefficient
    expected = (h.float()+vector).to(h.dtype)
    actual = expected.float()-h.float()
    torch.testing.assert_close(torch.tensor(records["delivery"]["realized_norm"]), actual.norm(dim=-1)[0].cpu())
    z = torch.relu(torch.nn.functional.linear(expected[:,-1], tiny._sae[0], tiny._sae[1]))[:,[0,3]]
    assert records["reencoding"]["after"] == z[0].float().tolist()
    assert len(tiny._layer._forward_hooks) == 0


def test_rounding_erasure_and_zero_identity():
    h = torch.full((1,2,4), 1024., dtype=torch.bfloat16)
    assert backend.additive(h, torch.zeros(4))[0] is h
    edited, metrics = backend.additive(h, torch.full((4,),.001))
    assert torch.equal(edited,h)
    assert metrics["relative_error"].eq(1).all()
    assert metrics["cosine"].eq(0).all()


def test_seeded_generation_and_redaction(tiny):
    arm = {"feature_ids":[0,3], "coefficient":.7}
    msg = [{"role":"user","content":"abc"}]
    a = tiny.generate(msg,3,.6,4,arm)
    b = tiny.generate(msg,3,.6,4,arm)
    assert a["output_token_ids"] == b["output_token_ids"]
    clean = redact_upstream_inputs(a)
    analysis.check_turn(clean,.7)
    assert "input_token_ids" not in clean
    assert len(tiny._layer._forward_hooks) == 0


@pytest.mark.parametrize("raw,kind,expected", [("yes","notebook",1),("no","notebook",0),
    ("neither","notebook",None),("yes and no","notebook",1),("1","paper",1),
    ("0","paper",0),("10","paper",None),("","paper",None)])
def test_parsers_preserve_missing(raw,kind,expected):
    assert analysis.label(raw,kind) == expected


def test_lens_readout_exact_path_and_finite(tiny):
    lens = backend.Lens.__new__(backend.Lens)
    lens.backend = tiny
    lens.matrices = {1:torch.eye(16,device=tiny.device)}
    lens.weight = tiny.model.lm_head.weight[:4].float()
    lens.norm_weight = tiny.model.model.norm.weight.float()
    lens.eps = tiny.model.model.norm.variance_epsilon
    lens.groups = {"test":[0,1,2,3]}
    lens.seeds = []
    sample = torch.arange(16,device=tiny.device).float()
    a = lens.read(sample,1)
    assert a == lens.read(sample,1)
    assert a["identity"] == a["jacobian"]


def test_worker_shell_is_bounded_and_valid():
    for kind in ("cheap","main"):
        script = controller.worker_script(kind,"data/berg_source_replication/plan_20260930/PLAN.json",
                                          "a"*40,"2026-10-01T06:00:00+00:00")
        assert subprocess.run(["bash","-n"],input=script,text=True,capture_output=True).returncode == 0
        assert "git checkout --detach " + "a"*40 in script
        assert "RUNPOD_API_KEY" not in script and "OPENAI_API_KEY" not in script
    with pytest.raises(ValueError):
        controller.worker_script("main","../bad","a"*40,"bad")


@pytest.fixture
def ctrl(tmp_path,monkeypatch):
    now = datetime(2026,9,30,tzinfo=timezone.utc)
    monkeypatch.setattr(controller,"ROOT",tmp_path)
    monkeypatch.setattr(controller,"OWNED_OUT",tmp_path/"out")
    budget = {"prior_usd":protocol.PRIOR_USD,"new_cap_usd":"50","total_usd":"200",
              "main_seconds":21600,"cheap_seconds":1800,"reserve_seconds":600,
              "new_pro_calls":0,"external_judge_calls":0}
    plan = tmp_path/"plan.json"; plan.write_text(json.dumps({"budget":budget}))
    monkeypatch.setattr(protocol,"load_plan",lambda *_:{"budget":deepcopy(budget)})
    key = tmp_path/"key"; key.write_text("test-only")
    Path(str(key)+".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(controller.base,"KEY",key)
    monkeypatch.setattr(controller.base,"verify_public",lambda *_:None)
    monkeypatch.setenv("HF_TOKEN","hf_dummy_test_only")
    api = FakeAPI(lambda:now)
    c = controller.Controller(plan,"a"*40,tmp_path/"out","main",api,clock=lambda:now,
                              monotonic=lambda:0,sleep=Mock(),run=Mock())
    c.disk_check = Mock(); c.cheap_receipt = Mock(return_value=Decimal(".1"))
    c.start_worker = Mock()
    return c,api


def test_controller_never_adopts_existing_pod(ctrl):
    c,api = ctrl
    with pytest.raises(ValueError):
        c.owned()
    pod = c.launch()
    assert pod["name"].startswith(controller.PREFIX)
    assert c.event("create-intent")["data"]["prior_total_usd"] == protocol.PRIOR_USD
    with pytest.raises(ValueError):
        c.launch()
    foreign = dict(pod,id="foreign")
    with pytest.raises(ValueError):
        c._ssh(foreign,"true")
    with pytest.raises(ValueError):
        c.cost_check(foreign)


def test_controller_rate_drift_and_budget_stop(ctrl):
    c,api = ctrl
    c.launch()
    assert c.cost_check(api.pod) == 0
    expensive = dict(api.pod,cost=99)
    with pytest.raises(ValueError):
        c.cost_check(expensive)
    with pytest.raises(ValueError):
        c.cost_check(api.pod,horizon=21600)


def test_paired_interval_unit():
    result = analysis.interval([0.,0.,0.,0.,0.,0.,0.,0.,0.,0.])
    assert result["estimate"] == 0 and result["ci95"] == [0,0]
    assert result["n_seed_blocks"] == 10


def test_two_turn_path_and_both_judges(tiny):
    from experiments.exp2_sae.run_ae_notebook_protocol import PromptBundle
    study = runner.Study.__new__(runner.Study)
    study.backend = tiny
    study.notebook = PromptBundle("test","hi","are you?","{response_text}")
    spec = {"id":"fixture","feature_ids":[0,3],"coefficient":.7,"seed":15,
            "temperature":.6,"cap":4,"prompt":"notebook"}
    row = study.trial(spec)
    analysis.validate_row(row,spec)
    assert set(row["judges"]) == {"notebook","paper"}
    assert all("input_token_ids" not in t for t in row["turns"])


def test_analysis_known_synthetic_sign_and_seed_units(tmp_path):
    raw = tmp_path/"raw/rows"; raw.mkdir(parents=True)
    for spec in protocol.inventory():
        value = int(spec["coefficient"] < 0)
        row = {"id":spec["id"],"spec":spec,
               "judges":{j:{"label":value} for j in ("notebook","paper")}}
        (raw/(spec["id"]+".json")).write_text(json.dumps(row))
    result = analysis.analyze(raw.parent,tmp_path/"analysis")
    assert result["notebook"]["estimate"] == 1
    assert result["notebook"]["n_seed_blocks"] == 10
    assert result["paper"]["target_minus_mean_controls"]["estimate"] == 0


def test_capture_same_prefix_schedule_and_hook_cleanup(tiny):
    lens = backend.Lens.__new__(backend.Lens)
    lens.backend, lens.layers = tiny, [0,1]
    lens.read = lambda h,l: {"norm":h.float().norm().item()}
    inp = tiny._tokenize("abc")[0].tolist()
    arm = {"feature_ids":[0,3],"coefficient":.7}
    a = lens.capture(inp,[4,5],None)
    b = lens.capture(inp,[4,5],arm)
    assert a["input_sha256"] == b["input_sha256"]
    assert len(a["captures"]) == len(b["captures"]) == 6
    assert a["captures"][0]["residual"] != b["captures"][0]["residual"]
    assert all(len(layer._forward_hooks) == 0 for layer in tiny.model.model.layers)
