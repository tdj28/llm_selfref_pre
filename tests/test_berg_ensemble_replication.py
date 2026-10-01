"""Exact weighted hook, fixed inventory, inference and ownership checks."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest
import torch

from experiments.berg_ensemble_replication import analysis, backend, controller, protocol, runner
from tests.test_berg_source_replication import tiny
from tests.test_sae_assay_controller import PUBLIC_KEY
from tests.test_sae_assay_exposure_controller import FakeAPI


def weighted(tiny):
    tiny.__class__ = backend.Backend
    return tiny


def test_inventory_and_paired_weights():
    rows = protocol.inventory()
    assert rows == protocol.inventory() and len(rows) == 450
    assert len({r["id"] for r in rows}) == 450
    assert not any(r["capture"] for r in rows)
    assert set(protocol.SEEDS).isdisjoint(protocol.source.DEFAULT_SEEDS)
    for seed in protocol.SEEDS:
        block = [r for r in rows if r["seed"] == seed]
        assert len(block) == 9
        target = next(r for r in block if r["family"] == "target" and r["coefficient"] == 1)
        assert 2 <= len(target["feature_ids"]) <= 4
        for r in block:
            if r["coefficient"]:
                assert r["subset_positions"] == target["subset_positions"]
                assert [abs(w) for w in r["weights"]] == target["weights"]
                assert all(.4 <= abs(w) <= .6 for w in r["weights"])


@pytest.mark.parametrize("sign", [-1,0,1])
def test_weighted_formula_generation_and_zero(tiny,sign):
    b = weighted(tiny)
    assert b.qualify()["pass"]
    arm = {"feature_ids":[0,3],"coefficient":sign,"weights":[sign*.41,sign*.59]}
    expected = b._sae[2][:,0].float()*(sign*.41)+b._sae[2][:,3].float()*(sign*.59)
    torch.testing.assert_close(b.vector(arm),expected,rtol=0,atol=0)
    captured = {}
    handle = b._layer.register_forward_hook(lambda _m,_i,out: captured.update(h=out[0].detach().clone()))
    with torch.inference_mode():
        _, record = b._forward(b._tokenize("abc"),[0,3],arm)
    handle.remove()
    edited = (captured["h"].float()+expected).to(b.dtype)
    actual = edited.float()-captured["h"].float()
    torch.testing.assert_close(torch.tensor(record["delivery"]["realized_norm"]),actual.norm(dim=-1)[0].cpu())
    z = torch.relu(torch.nn.functional.linear(edited[:,-1],b._sae[0],b._sae[1]))[:,[0,3]]
    assert record["reencoding"]["after"] == z[0].float().tolist()
    from experiments.sae_assay_diagnostic.runner import redact_upstream_inputs
    result = redact_upstream_inputs(b.generate([{"role":"user","content":"abc"}],3,.5,4,arm))
    analysis.check_turn(result,sign)
    assert result["telemetry"]["weights"] == arm["weights"]
    assert not b._layer._forward_hooks


@pytest.mark.parametrize("weights,sign", [([.7,.5],1),([.5],1),([float("nan"),.5],1),([.5,.5],-1),([.5,0],0)])
def test_invalid_weights_fail_before_forward(tiny,weights,sign):
    b = weighted(tiny)
    with pytest.raises(ValueError):
        b.vector({"feature_ids":[0,3],"weights":weights,"coefficient":sign})


def test_two_turn_exact_weight_metadata(tiny):
    from experiments.exp2_sae.run_ae_notebook_protocol import PromptBundle
    s = runner.Study.__new__(runner.Study)
    s.backend, s.notebook = weighted(tiny), PromptBundle("test","hi","are you?","{response_text}")
    spec = {"id":"test","feature_ids":[0,3],"weights":[-.41,-.59],"coefficient":-1,
            "seed":3,"temperature":.5,"cap":4,"prompt":"notebook"}
    row = s.trial(spec)
    analysis.validate_row(row,spec)
    broken = deepcopy(row); broken["turns"][0]["telemetry"]["weights"][0] = -.42
    with pytest.raises(ValueError): analysis.validate_row(broken,spec)


def test_exact_bounds_and_missingness():
    r = analysis.contrast([1]*50,[0]*50)
    assert r["estimate_complete_pairs"] == 1 and r["exact_marginal95"][0] > .8
    null = analysis.contrast([0]*50,[0]*50)
    assert null["bootstrap95"] == [0,0] and null["exact_marginal95"][1] > 0
    missing = analysis.contrast([None]*50,[None]*50)
    assert missing["exact_marginal95"] == [-1,1] and missing["complete_pairs"] == 0
    assert missing["missingness_bounds"] == [-1,1]


def test_synthetic_all_controls_same_no_specificity(tmp_path):
    raw = tmp_path/"raw/rows"; raw.mkdir(parents=True)
    for spec in protocol.inventory():
        v = int(spec["coefficient"] < 0)
        (raw/(spec["id"]+".json")).write_text(json.dumps({"spec":spec,"judges":{j:{"label":v} for j in ("paper","notebook")}}))
    r = analysis.analyze(raw.parent,tmp_path/"analysis")["paper"]
    assert r["target"]["complete_pairs"] == 50 and r["target"]["estimate_complete_pairs"] == 1
    assert r["specificity"]["estimate_complete_blocks"] == 0
    assert r["large_signature_verdict"] == "large_positive_signature"


def test_worker_is_bounded_and_new_namespace():
    for kind in ("cheap","main"):
        script = controller.worker_script(kind,"data/berg_ensemble_replication/plan_20261001/PLAN.json","a"*40,"2026-10-01T12:00:00+00:00")
        assert subprocess.run(["bash","-n"],input=script,text=True,capture_output=True).returncode == 0
        assert "berg_ensemble_replication" in script
        assert "RUNPOD_API_KEY" not in script
    with pytest.raises(ValueError): controller.worker_script("main","../bad","a"*40,"bad")


@pytest.fixture
def ctrl(tmp_path,monkeypatch):
    now = datetime(2026,10,1,tzinfo=timezone.utc)
    monkeypatch.setattr(controller,"ROOT",tmp_path)
    monkeypatch.setattr(controller,"OWNED_OUT",tmp_path/"out")
    plan = tmp_path/"plan.json"; plan.write_text(json.dumps({"budget":protocol.BUDGET}))
    monkeypatch.setattr(protocol,"load_plan",lambda *_:{"budget":deepcopy(protocol.BUDGET)})
    key = tmp_path/"key"; key.write_text("test-only"); Path(str(key)+".pub").write_text(PUBLIC_KEY)
    monkeypatch.setattr(controller.base,"KEY",key)
    monkeypatch.setattr(controller.base,"verify_public",lambda *_:None)
    monkeypatch.setenv("HF_TOKEN","hf_dummy_test_only")
    api = FakeAPI(lambda:now)
    c = controller.Controller(plan,"a"*40,tmp_path/"out","main",api,clock=lambda:now,
                              monotonic=lambda:0,sleep=Mock(),run=Mock())
    c.disk_check = Mock(); c.cheap_receipt = Mock(return_value=Decimal(".1")); c.start_worker = Mock()
    return c,api


def test_ownership_cost_and_no_double_launch(ctrl):
    c,api = ctrl
    with pytest.raises(ValueError): c.owned()
    pod = c.launch()
    assert pod["name"].startswith(controller.PREFIX)
    assert c.event("create-intent")["data"]["prior_total_usd"] == "72.50"
    with pytest.raises(ValueError): c.launch()
    with pytest.raises(ValueError): c.cost_check(dict(pod,id="foreign"))
    with pytest.raises(ValueError): c.cost_check(dict(pod,cost=99))
    with pytest.raises(ValueError): c.cost_check(pod,horizon=16200)


@pytest.mark.parametrize("limit,elapsed,overdue", [(1800,2000,True),(16200,9000,False),(16200,17000,True)])
def test_cleanup_retry_uses_instance_timer(ctrl,limit,elapsed,overdue):
    c,_ = ctrl
    c.launch()
    c.hard_seconds = limit
    c._elapsed = Mock(return_value=Decimal(elapsed))
    c.terminate = Mock(side_effect=[RuntimeError("synthetic transient"),{"closed":True}])
    assert c.close_until_verified() == {"closed":True}
    retry = [e["data"] for e in c.ledger.read() if e["id"].startswith("cleanup-retry:")]
    assert len(retry) == 1 and retry[0]["hard_deadline_exceeded"] == overdue
    assert retry[0]["hard_seconds"] == limit
