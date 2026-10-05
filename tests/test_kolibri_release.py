"""Synthetic fixtures in explicit temporary repositories; no live I/O."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from copy import deepcopy
from pathlib import Path
import shutil
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from experiments import kolibri_release as x, kolibri_judge_transport as t
from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments.kolibri_bootstrap_a3 import adapter as a3, production as bridge
from experiments.kolibri_bootstrap_a4 import adapter as a4
from experiments.kolibri_bootstrap_a5 import adapter as a5, cli as cli5
from experiments.kolibri_swap import production as prod, protocol, runtime
from experiments.openrouter_swap.ledger import Halted, Ledger
from experiments.sae_assay_diagnostic.budget import EventLedger
from tests.test_kolibri_judge_transport import TIMEOUT, flaky, filtered
from tests.test_kolibri_swap_production import write, tree_hashes
from tests.test_kolibri_swap_runtime import senders, local_raw, receipt
from tests.test_kolibri_bootstrap_a5 import synthetic_parser

WORKER_FREEZE = "a" * 40  # Synthetic A3 freeze, never a production claim.


@contextmanager
def opened(setup, judge=None, local=None):
    plan, root, amendment, policy = setup
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", WORKER_FREEZE, a1.ORIGINAL_PLAN_SHA) as receipts:
        runner = x.runtime_bridge(amendment).Runner(plan, WORKER_FREEZE, a1.ORIGINAL_PLAN_SHA, ledger, receipts,
                               local, judge, amendment=amendment, transport_plan=policy, sleep=Mock())
        runner.guard = Mock()
        yield runner


def make_controller(root, role, freeze, plan, *, amendment_hash=None, carry=None, passed=True, close=True,
                    ready=True, qualification=None, cap=None, exit_code=None, continuation=None):
    kind = x.ROLES[role]
    base = root / "controller" / kind
    ledger = EventLedger(base / "events.jsonl", a1.ORIGINAL_PLAN_SHA, freeze, [])
    pod = "synthetic-" + role
    name = x.controller.PREFIX + kind + "-" + "e" * 12
    rate = ".74" if kind == "cheap" else "4.59"
    now = datetime.now(timezone.utc)
    ledger.bind("controller:config", {"kind": kind, "amendment_sha256": amendment_hash,
        "prior_cheap_usd": carry if role not in {"a5-main", "a6-main"} else None,
        "prior_gpu_usd": carry if role in {"a5-main", "a6-main"} else None,
        "continuation": continuation,
        "qualification": qualification, "cap_usd": cap,
        "a4_freeze": a5.A4_FREEZE if role == "a5-main" else None,
        "a2_freeze": a3.A2_FREEZE if role.startswith("a3-") else None,
        "a3_freeze": a4.A3_FREEZE if role.startswith("a4-") else None})
    ledger.bind("create-intent", {"plan_sha256": a1.ORIGINAL_PLAN_SHA, "freeze_commit": freeze,
        "created_utc": (now - timedelta(seconds=30) if kind == "cheap" else now).isoformat(),
        "deadline_utc": (now + timedelta(hours=4)).isoformat(),
        "quote": {"hourly_rate_usd": rate, "storage_hourly_usd": ".10"},
        "payload": {"name": name, "env": {"PUBLIC_KEY": "ssh-ed25519 synthetic-public-key"}},
        "blocked": ["unrelated-private-pod"]})
    ledger.bind("created", {"id": pod, "name": name, "publicIp": "198.51.100.40", "unrelated": "private-metadata"})
    ledger.bind("worker-intent", {"sha256": "d" * 64})
    ledger.bind("worker-started", {"pod_id": pod})
    if kind == "main" and ready:
        ledger.bind("server-ready", {"utc": now.isoformat()})
    directory = base / "retrievals" / "synthetic"
    write(directory / "exit.json", {"exit_code": (0 if passed else 1) if exit_code is None else exit_code})
    write(directory / "runtime.json", {"torch": "2.13.0+cu130", "cuda": "13.0",
                                        "gpu": "NVIDIA H200" if kind == "main" else "NVIDIA GeForce RTX 4090"})
    (directory / "worker.log").write_text("Synthetic private worker log; no research observation.\n")
    if role in {"a5-main", "a6-main"} and ready:
        with (directory / "worker.log").open("a") as handle:
            handle.write(protocol.canonical(cli5.validate_parser(synthetic_parser(), Mock())) + "\n")
    if kind == "cheap":
        smoke = {"schema": "kolibri-tiny-qualification-v1", "status": "passed" if passed else "failed",
            "mode": "gpu", "scientific_generation": False, "expected_versions": x.gpu_smoke.VERSIONS,
            "versions": x.gpu_smoke.VERSIONS, "gpu": {"official_routing_cpu_cuda": True},
            "upstream": {"revision": x.gpu_smoke.UPSTREAM_SHA, "source_sha256": x.gpu_smoke.SOURCE_HASHES}}
        if role in {"a3-cheap", "a4-cheap"}:
            smoke.update(amendment="kolibri-bootstrap-a3-v1", parser={"official_passed": 70, "skipped": 0})
            smoke["gpu"].update(llm_options=x.gpu_smoke.LLM_OPTIONS, checkpoint={"fp8_matrices": 186},
                forward=[{"tokens": 8, "prompt_tokens": len(p)} for p in x.gpu_smoke.PROMPTS],
                workers=[{"status": "passed", "linear_errors": [], "layers": 6, "custom_routing_layers": 6,
                    "fp8_weights": True, "checkpoint_fp32_block_scales": True,
                    "modules": [{"name": "synthetic"}], "operator_sources": {"synthetic": "f" * 64},
                    "linears": [{"name": f"model.layers.{i}.{name}", "storage": "official_marlin_e4m3fn_packed_int32",
                        "exact_checkpoint_reconstruction": True} for i in range(6) for name in
                        ("self_attn.qkv_proj", "self_attn.o_proj", "mlp.shared_experts.gate_up_proj", "mlp.shared_experts.down_proj")]}])
        write(directory / "gpu-smoke.json", smoke)
    else:
        files = plan["metadata"]["model_artifacts"]["files"]
        write(directory / "model-files.json", {"model": protocol.MODEL["id"], "revision": plan["metadata"]["hf_revision"],
            "plan_sha256": a1.ORIGINAL_PLAN_SHA, "verified": True, "weight_map_verified": True, "config_verified": True,
            "frozen_files_verified": len(files), "files": [{"path": name, "bytes": info["size"],
                "sha256": info["sha256"], "frozen_sha256": info["sha256"],
                "published_lfs_sha256": info["sha256"] if name.endswith(".safetensors") else None}
                for name, info in files.items()]})
    def finish():
        artifacts = {p.name: protocol.sha(p) for p in directory.iterdir()}
        retrieval = ledger.bind("retrieval:final", {"pod_id": pod, "directory": str(directory),
            "artifacts": artifacts, "retrieval_verified": True})
        write(base / "final-retrieval.json", retrieval)
        ledger.bind("delete-intent", {"pod_id": pod})
        ledger.bind("closed", {"pod_id": pod, "get_status": 404, "compute_upper_bound_usd": ".08" if kind == "cheap" else "1",
            "elapsed_seconds": "30", "utc": datetime.now(timezone.utc).isoformat()})
    if close:
        finish()
    return finish


@pytest.fixture
def saved(tmp_path, monkeypatch):
    original_repo = protocol.ROOT
    plan = protocol.verify(original_repo / protocol.PLAN)
    repo, root = tmp_path / "synthetic-repository", tmp_path / "synthetic-run"
    for name in (*x.SOURCES, *x.DEPENDENCIES, *t.SOURCES, protocol.PLAN, *plan["source_hashes"]):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((original_repo / name).read_bytes())
    (repo / "repair.py").write_text("# Synthetic A2 source\n")
    amendment = {"source_hashes": {"repair.py": protocol.sha(repo / "repair.py")}, "dependency_source_hashes": {}}
    monkeypatch.setattr(protocol, "ROOT", repo)
    monkeypatch.setattr(a2, "verify", lambda *args: deepcopy(amendment))
    # Synthetic freezes are not commits; only the local-Git proof is replaced.
    monkeypatch.setattr(x, "git_bound", lambda freeze, hashes: None)
    monkeypatch.setattr(x, "git_ancestor", lambda ancestor, descendant: None)
    original, prior = tmp_path / "synthetic-original", tmp_path / "synthetic-a1"
    make_controller(original, "original-cheap", a1.ORIGINAL_FREEZE, plan, passed=False)
    first, _ = x.project_controller(original, "original-cheap", a1.ORIGINAL_PLAN_SHA, a1.ORIGINAL_FREEZE)
    def anchor(value):
        return {key: value[key] for key in ("freeze", "plan_sha256", "cost_usd", "ledger_sha256", "retrieval_sha256",
                "closed_sha256", "events_file_sha256", "retrieval_file_sha256")} | {"pod_id": value["owned_pod_id"]}
    write(repo / a1.AMENDMENT, {"source_hashes": amendment["source_hashes"], "predecessor": anchor(first)})
    make_controller(prior, "a1-cheap", a2.A1_FREEZE, plan, passed=False,
                    amendment_hash=protocol.sha(repo / a1.AMENDMENT), carry=first["cost_usd"])
    second, _ = x.project_controller(prior, "a1-cheap", a1.ORIGINAL_PLAN_SHA, a2.A1_FREEZE)
    amendment.update(scientific_plan_sha256=a1.ORIGINAL_PLAN_SHA,
                     predecessor={"cost_usd": ".16", "exact_sum_usd": ".16", "attempts": [anchor(first), anchor(second)]})
    write(repo / a2.AMENDMENT, amendment)
    policy = t.build_plan(a3.A2_FREEZE)
    write(repo / t.PLAN, policy)
    prior2 = tmp_path / "synthetic-a2"
    make_controller(prior2, "a2-cheap", a3.A2_FREEZE, plan, passed=False,
                    amendment_hash=protocol.sha(repo / a2.AMENDMENT), carry=".16")
    third, _ = x.project_controller(prior2, "a2-cheap", a1.ORIGINAL_PLAN_SHA, a3.A2_FREEZE)
    amendment = {**amendment, "a2_amendment_sha256": protocol.sha(repo / a2.AMENDMENT),
        "predecessor": {"cost_usd": ".24", "exact_sum_usd": ".24", "prior_admission_plus_latest_usd": ".24",
                        "attempts": [anchor(first), anchor(second), anchor(third)]},
        "judge_policy": {"freeze": a3.JUDGE_FREEZE, "path": t.PLAN, "sha256": protocol.sha(repo / t.PLAN),
                         "original_worker_freeze": a3.A2_FREEZE, "policy_changed": False}}
    write(repo / a3.AMENDMENT, amendment)
    make_controller(root, "a3-cheap", WORKER_FREEZE, plan, passed=True,
                    amendment_hash=protocol.sha(repo / a3.AMENDMENT), carry=".24")
    return {"setup": (plan, root, amendment, policy), "repo": repo,
            "roots": {"original_root": original, "a1_root": prior, "a2_root": prior2}}


def begin(saved):
    plan, root, amendment, policy = saved["setup"]
    repo = saved["repo"]
    collection = root / "collection"
    write(collection / "runtime.json", prod.binding(plan, WORKER_FREEZE, a1.ORIGINAL_PLAN_SHA))
    version = {"kolibri-bootstrap-a4-v1": "a4", "kolibri-bootstrap-a5-v1": "a5"}.get(amendment.get("schema"), "a3")
    module = {"a3": a3, "a4": a4, "a5": a5}[version]
    for name, path in (("PLAN.json", protocol.PLAN), ("AMENDMENT.json", module.AMENDMENT), ("JUDGE_TRANSPORT.json", t.PLAN)):
        (collection / name).write_bytes((repo / path).read_bytes())
    return make_controller(root, version + "-main", WORKER_FREEZE, plan, close=False,
        amendment_hash=protocol.sha(repo / module.AMENDMENT), carry=amendment["predecessor"]["cost_usd"],
        qualification=amendment.get("qualification"), cap=amendment.get("main_cap_usd"))


def bind(runner, setup):
    runner.receipts.append("decision", {"name": "judge_transport", "value": x.runtime_bridge(setup[2]).bridge_binding(WORKER_FREEZE, setup[2], setup[3])})


def admit(runner, phase, root):
    value = {"phase": phase, "reconciliation": {"source_hashes": {"data/synthetic.json": "a" * 64}},
        **x.runtime_bridge(runner.amendment).bridge_binding(WORKER_FREEZE, runner.amendment, runner.transport_plan), "plan_sha256": a1.ORIGINAL_PLAN_SHA,
        "http_head": runner.receipts.events[-1]["sha256"]}
    write(root / "collection/admissions" / (protocol.digest(value) + ".json"), value)


def export(saved, target):
    return x.build(saved["setup"][1], target, **saved["roots"])


@pytest.fixture
def saved_a4(saved, tmp_path):
    plan, _, prior, policy = saved["setup"]
    repo = saved["repo"]
    failed, current = tmp_path / "synthetic-failed-a3", tmp_path / "synthetic-a4"
    make_controller(failed, "a3-cheap", a4.A3_FREEZE, plan, passed=False,
                    amendment_hash=protocol.sha(repo / a3.AMENDMENT), carry=".24")
    value, _ = x.project_controller(failed, "a3-cheap", a1.ORIGINAL_PLAN_SHA, a4.A3_FREEZE)
    anchor = {key: value[key] for key in ("freeze", "plan_sha256", "cost_usd", "ledger_sha256", "retrieval_sha256",
                "closed_sha256", "events_file_sha256", "retrieval_file_sha256")} | {"pod_id": value["owned_pod_id"]}
    amendment = {**prior, "schema": "kolibri-bootstrap-a4-v1", "a3_freeze": a4.A3_FREEZE,
        "a3_amendment_sha256": protocol.sha(repo / a3.AMENDMENT),
        "predecessor": {"cost_usd": ".32", "exact_sum_usd": ".32", "prior_admission_plus_latest_usd": ".32",
                        "attempts": [*prior["predecessor"]["attempts"], anchor]}}
    write(repo / a4.AMENDMENT, amendment)
    make_controller(current, "a4-cheap", WORKER_FREEZE, plan,
                    amendment_hash=protocol.sha(repo / a4.AMENDMENT), carry=".32")
    return {"setup": (plan, current, amendment, policy), "repo": repo,
            "roots": {**saved["roots"], "a3_root": failed}}


@pytest.fixture
def saved_a5(saved_a4, tmp_path):
    plan, _, prior, policy = saved_a4["setup"]
    repo = saved_a4["repo"]
    fourth, current = tmp_path / "synthetic-prior-a4", tmp_path / "synthetic-a5"
    anchors = []
    for kind in ("cheap", "main"):
        make_controller(fourth, "a4-" + kind, a5.A4_FREEZE, plan, ready=False,
            passed=kind == "cheap", exit_code=0 if kind == "cheap" else 2,
            amendment_hash=protocol.sha(repo / a4.AMENDMENT), carry=".32")
        value, _ = x.project_controller(fourth, "a4-" + kind, a1.ORIGINAL_PLAN_SHA, a5.A4_FREEZE)
        anchors.append({key: value[key] for key in ("freeze", "plan_sha256", "cost_usd", "ledger_sha256",
            "retrieval_sha256", "closed_sha256", "events_file_sha256", "retrieval_file_sha256")}
            | {"pod_id": value["owned_pod_id"]})
    qualified = {key: anchors[0][key] for key in ("freeze", "pod_id", "cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256")}
    amendment = {**prior, "schema": "kolibri-bootstrap-a5-v1", "a4_freeze": a5.A4_FREEZE,
        "a4_amendment_sha256": protocol.sha(repo / a4.AMENDMENT), "qualification": qualified,
        "new_cheap_pod": False, "qualification_computation_changed": False, "main_cap_usd": "22",
        "predecessor": {"cost_usd": "1.40", "exact_sum_usd": "1.40", "prior_admission_plus_latest_usd": "1.40",
                        "attempts": [*prior["predecessor"]["attempts"], *anchors]}}
    write(repo / a5.AMENDMENT, amendment)
    return {"setup": (plan, current, amendment, policy), "repo": repo,
            "roots": {**saved_a4["roots"], "a4_root": fourth}}


def test_a5_unrun_main_preserves_six_costs_and_reuses_only_a4_qualification(saved_a5, tmp_path):
    finish = begin(saved_a5)
    shutil.rmtree(saved_a5["setup"][1] / "collection")
    finish()
    target = tmp_path / "a5-release"
    assert export(saved_a5, target)["status"] == "technical_incomplete"
    report = prod.load(target / "RELEASE.json")
    assert report["qualification_reused_from_a4"] and report["cheap_cuda_pass"]
    assert Decimal(report["costs"]["predecessor_exact_usd"]) == Decimal("1.40")
    assert Decimal(report["costs"]["cumulative_bound_usd"]) == Decimal("2.40")
    assert len(list((target / "controllers").iterdir())) == 7
    assert not (target / "controllers/a5-cheap").exists()
    assert prod.load(target / "controllers/a5-main/controller.json")["cli_preflight"]["status"] == "passed"


def test_a5_partial_bridge_keeps_raw_missingness_and_unknown_charges(saved_a5, tmp_path):
    test_partial_transport_attempts_preserve_raw_and_costs(saved_a5, tmp_path)


@pytest.mark.parametrize("branch", ["screen_stopped", "main_complete"])
def test_a5_completed_branches_use_unchanged_analysis(saved_a5, tmp_path, branch):
    test_completed_branches_recompute_frozen_analysis_and_barriers(saved_a5, tmp_path, branch)


@pytest.mark.parametrize("mutation", ["qualification", "prior_cost", "missing_failed_main", "parser", "cap", "closure"])
def test_a5_rehashed_tamper_preserves_full_operational_chain(saved_a5, tmp_path, mutation):
    finish = begin(saved_a5)
    shutil.rmtree(saved_a5["setup"][1] / "collection")
    finish()
    target = tmp_path / "a5-tamper"
    export(saved_a5, target)
    path = target / "controllers/a5-main/controller.json"
    value = prod.load(path)
    if mutation == "qualification":
        value["qualification"]["retrieval_sha256"] = "0" * 64
    elif mutation == "prior_cost":
        value["prior_gpu_usd"] = "0"
    elif mutation == "missing_failed_main":
        (target / "controllers/a4-main/controller.json").unlink()
    elif mutation == "parser":
        value["cli_preflight"]["parsed"]["kv_cache_dtype"] = "auto"
    elif mutation == "cap":
        value["cap_usd"] = "25"
    else:
        value["get_status"] = 200
    write(path, value); re_manifest(target)
    with pytest.raises((Halted, KeyError, OSError)):
        x.verify(target)


def test_a4_unrun_chain_has_four_prior_costs_and_no_public_private_metadata(saved_a4, tmp_path):
    target = tmp_path / "a4-release"
    result = export(saved_a4, target)
    report = prod.load(target / "RELEASE.json")
    assert result["pass"] and report["status"] == "technical_incomplete"
    assert Decimal(report["costs"]["cumulative_bound_usd"]) == Decimal(".40")
    assert report["a3_worker_bridge_freeze"] == a4.A3_FREEZE
    assert report["a4_worker_bridge_freeze"] == WORKER_FREEZE
    assert len(list((target / "controllers").iterdir())) == 5
    assert all(v["proportion"] is None for v in prod.load(target / "TABLES.json")["cells"])
    published = b"".join(p.read_bytes() for p in target.rglob("*") if p.is_file())
    for value in (b"198.51.100.40", b"unrelated-private-pod", b"ssh-ed25519", b"private-metadata"):
        assert value not in published
    assert x.verify(target, run_dir=saved_a4["setup"][1], **saved_a4["roots"])["lifecycle_verified_this_check"]


def test_a4_partial_bridge_retains_raw_unknown_costs_and_caps(saved_a4, tmp_path):
    test_partial_transport_attempts_preserve_raw_and_costs(saved_a4, tmp_path)


@pytest.mark.parametrize("branch", ["screen_stopped", "main_complete"])
def test_a4_completed_branches_use_unchanged_analysis(saved_a4, tmp_path, branch):
    test_completed_branches_recompute_frozen_analysis_and_barriers(saved_a4, tmp_path, branch)


@pytest.mark.parametrize("mutation", ["prior_cost", "missing_predecessor", "wrong_bridge", "missing_receipt"])
def test_a4_tamper_never_drops_predecessor_or_changes_bridge(saved_a4, tmp_path, mutation):
    target = tmp_path / "a4-tamper"
    export(saved_a4, target)
    if mutation == "prior_cost":
        path = target / "controllers/a3-cheap/controller.json"
        value = prod.load(path)
        value["cost_usd"] = "0"
        write(path, value)
    elif mutation == "missing_predecessor":
        (target / "controllers/a3-cheap/controller.json").unlink()
    elif mutation == "missing_receipt":
        (target / "controllers/a4-cheap/artifacts/exit.json").unlink()
    else:
        path = target / "provenance/A4_AMENDMENT.json"
        value = prod.load(path)
        value["judge_policy"]["freeze"] = WORKER_FREEZE
        write(path, value)
    re_manifest(target)
    with pytest.raises((Halted, KeyError, OSError)):
        x.verify(target)


def re_manifest(root):
    write(root / "MANIFEST.json", {"schema": "kolibri-release-manifest-v1", "files": list(x.inventory(root).values())})


def test_unrun_release_and_private_controller_omissions(saved, tmp_path):
    root = saved["setup"][1]
    before = tree_hashes(root)
    target = tmp_path / "release"
    result = export(saved, target)
    assert result["pass"] and result["status"] == "technical_incomplete" and result["lifecycle_verified_this_check"]
    assert before == tree_hashes(root)
    report = prod.load(target / "RELEASE.json")
    assert report["scientific_verdict"] is None and not report["qualification_evaluable"]
    assert report["counts"]["screen"]["missing_final_content"] == 48
    assert report["counts"]["main"]["missing_final_content"] == 256
    assert Decimal(report["costs"]["cumulative_bound_usd"]) == Decimal(".32")
    assert all(v["proportion"] is None for v in prod.load(target / "TABLES.json")["cells"])
    assert all(v["run_state"] == "unrun" for v in prod.load(target / "TABLES.json")["primary_contrasts"])
    published = b"".join(p.read_bytes() for p in target.rglob("*") if p.is_file())
    for private in (b"198.51.100.40", b"unrelated-private-pod", b"ssh-ed25519", str(root).encode(), b"private-metadata"):
        assert private not in published
    assert not list(target.rglob("worker.log")) and not list(target.rglob("*.safetensors"))
    figures = prod.load(target / "FIGURES.json")
    assert figures["dpi"] == 300 and len(figures["figures"]) == 2
    assert all(protocol.sha(target / row["path"]) == row["sha256"] and row["description_and_alt_text"]
               for row in figures["figures"])
    assert x.verify(target)["lifecycle_verified_this_check"] is False
    assert x.verify(target, expected_manifest_sha256=result["manifest_sha256"], run_dir=root, **saved["roots"])["pass"]
    from PIL import Image
    import numpy as np
    for path in (target / "figures").glob("*.png"):
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert pixels.shape[0] >= 300 and pixels.std() > 10


def test_portable_verification_requires_external_pin(tmp_path):
    with pytest.raises(Halted, match="externally reviewed manifest pin"):
        x.verify(tmp_path, rerender=False)
    with pytest.raises(Halted):
        x.verify(tmp_path, rerender="false", expected_manifest_sha256="0" * 64)
    with pytest.raises(SystemExit):
        x.main(["--destination", str(tmp_path), "--run-dir", str(tmp_path), "--no-rerender"])


def test_portable_verification_does_not_render_but_keeps_strict_default(saved, tmp_path, monkeypatch):
    target = tmp_path / "portable"
    built = export(saved, target)
    assert built["figures_rerendered"] is True
    before = tree_hashes(target)
    renderer = Mock(side_effect=RuntimeError("Synthetic platform renderer unavailable"))
    monkeypatch.setattr(x, "render", renderer)
    result = x.verify(target, expected_manifest_sha256=built["manifest_sha256"], rerender=False,
                      run_dir=saved["setup"][1], **saved["roots"])
    assert result["pass"] and result["reviewed_manifest_pinned"] and not result["figures_rerendered"]
    assert result["lifecycle_verified_this_check"] and before == tree_hashes(target)
    renderer.assert_not_called()
    assert x.main(["--destination", str(target), "--verify", "--no-rerender",
                   "--expected-manifest-sha256", built["manifest_sha256"]]) == 0
    with pytest.raises(RuntimeError, match="renderer unavailable"):
        x.verify(target, expected_manifest_sha256=built["manifest_sha256"])


def test_portable_verification_preserves_hash_numeric_receipt_and_security_checks(saved, tmp_path):
    original = tmp_path / "reviewed"
    built = export(saved, original)
    for mutation in ("figure_bytes", "numeric", "figure_receipt", "raw_artifact", "private"):
        target = tmp_path / mutation
        shutil.copytree(original, target)
        if mutation == "figure_bytes":
            (target / "figures/cells.png").write_bytes(b"Synthetic altered image")
        elif mutation == "numeric":
            value = prod.load(target / "TABLES.json")
            value["cells"][0]["proportion"] = .5
            write(target / "TABLES.json", value)
        elif mutation == "figure_receipt":
            value = prod.load(target / "FIGURES.json")
            value["figures"][0]["plot_data"] = []
            write(target / "FIGURES.json", value)
        elif mutation == "raw_artifact":
            write(target / "controllers/a3-cheap/artifacts/gpu-smoke.json", {"status": "invented"})
        else:
            write(target / "qualification.json", {"private": "/Users/private-person/hidden"})
        re_manifest(target)
        with pytest.raises(Halted, match="Reviewed manifest pin differs"):
            x.verify(target, expected_manifest_sha256=built["manifest_sha256"], rerender=False)
        # Even a newly supplied pin cannot bypass recomputation or the content scan.
        with pytest.raises((Halted, KeyError, ValueError)):
            x.verify(target, expected_manifest_sha256=protocol.sha(target / "MANIFEST.json"), rerender=False)


def test_partial_transport_attempts_preserve_raw_and_costs(saved, tmp_path):
    setup = saved["setup"]
    finish = begin(saved)
    local, good, _, _ = senders()
    sender, seen = flaky(good, [TIMEOUT, TIMEOUT])
    with opened(setup, sender, local) as runner:
        bind(runner, setup); admit(runner, "fixtures", setup[1])
        gate = runner.run_fixtures()
        assert gate["pass"]
        prod.checkpoint(runner, "fixtures", gate)
        admit(runner, "generate-screen-initial", setup[1])
        capped = next(block["finals"][0] for block in setup[0]["screen"] if block["block"] <= 2)
        def capped_local(request):
            raw = local_raw(request)
            if request["seed"] == capped["seed"]:
                raw["choices"][0]["message"]["content"] = None
                raw["choices"][0]["finish_reason"] = "length"
            return receipt(raw)
        runner.local_sender = capped_local
        runner.generate_blocks("screen", initial=True)
        spent = runner.ledger.spent()
    finish()
    before = tree_hashes(setup[1])
    target = tmp_path / "partial"
    export(saved, target)
    assert before == tree_hashes(setup[1])
    result = prod.load(target / "RELEASE.json")
    assert result["status"] == "technical_incomplete" and not result["completion"]["screen"]
    assert result["counts"]["screen"]["final_dispatches"] == 8
    capped_row = next(row for row in prod.load(target / "screen_rows.json") if row["id"] == capped["id"])
    assert capped_row["response"] is None and capped_row["cap_hit"] and capped_row["status"] == "incomplete"
    assert result["counts"]["screen"]["cap_hit"] == 1
    assert Decimal(result["costs"]["all_judge_attempts_bound_usd"]) == spent
    assert result["audit"]["physical_unresolved"] == 2
    assert sum(p.read_bytes() == TIMEOUT.body for p in (target / "collection/http/raw").glob("*.bin")) == 2
    for path in (setup[1] / "collection/http/raw").glob("*.bin"):
        assert path.read_bytes() == (target / "collection/http/raw" / path.name).read_bytes()
    raw = next(runtime.strict_json(p.read_bytes()) for p in (target / "collection/http/raw").glob("*.bin")
               if b'Synthetic reasoning never transplanted.' in p.read_bytes())
    assert "provider" not in raw and "reasoning" in raw["choices"][0]["message"]
    index = prod.load(target / "CONTENT_INDEX.json")
    assert index["normalized_projection"] and not index["reasoning_transplanted"]
    assert any(row["final_content"] and row["final_content"][0]["is_null"] and row["reasoning"]
               for row in index["calls"] if row["channel"] == "local")
    assert sum(not row["json_decoded"] for row in index["calls"]) == 2


@pytest.mark.parametrize("mutation", ["extra", "missing_artifact", "derived", "figure", "figure_receipt", "private", "escaped_secret", "carry", "closure", "weights"])
def test_public_tamper_rejected_after_rehashed_manifest(saved, tmp_path, mutation):
    target = tmp_path / "tampered"
    export(saved, target)
    if mutation == "extra":
        (target / "extra.txt").write_text("unlisted")
    elif mutation == "missing_artifact":
        (target / "controllers/a3-cheap/artifacts/exit.json").unlink()
    elif mutation == "derived":
        value = prod.load(target / "screen_rows.json"); value[0]["response"] = "invented"; write(target / "screen_rows.json", value)
    elif mutation == "figure":
        (target / "figures/cells.png").write_bytes(b"not an image")
    elif mutation == "figure_receipt":
        value = prod.load(target / "FIGURES.json"); value["dpi"] = 1; write(target / "FIGURES.json", value)
    elif mutation == "private":
        value = prod.load(target / "controllers/a3-cheap/controller.json"); value["private"] = "/Users/private-person/hidden"; write(target / "controllers/a3-cheap/controller.json", value)
    elif mutation == "escaped_secret":
        token = "sk-" + "X" * 48
        (target / "qualification.json").write_text('{"x":"' + ''.join('\\u%04x' % ord(c) for c in token) + '"}')
    elif mutation in {"carry", "closure"}:
        path = target / "controllers/original-cheap/controller.json"
        value = prod.load(path); value["cost_usd" if mutation == "carry" else "get_status"] = "0" if mutation == "carry" else 200; write(path, value)
    else:
        (target / "model.safetensors").write_bytes(b"not allowed")
    re_manifest(target)
    with pytest.raises((Halted, OSError, ValueError, KeyError)):
        x.verify(target)


def test_projection_requires_external_authority_or_manifest_pin(saved, tmp_path):
    target = tmp_path / "projection"
    export(saved, target)
    path = target / "controllers/a3-cheap/controller.json"
    value = prod.load(path); value["owned_pod_id"] = "synthetic-other-owned-pod"; write(path, value)
    re_manifest(target)
    assert x.verify(target)["lifecycle_verified_this_check"] is False
    with pytest.raises(Halted, match="Lifecycle"):
        x.verify(target, run_dir=saved["setup"][1], **saved["roots"])


def test_missing_direct_deletion_blocks_build(saved, tmp_path):
    begin(saved)
    with pytest.raises((Halted, KeyError, OSError)):
        export(saved, tmp_path / "not-terminal")
    assert not (tmp_path / "not-terminal").exists()


def test_exporter_source_change_and_manifest_pin_fail_closed(saved, tmp_path):
    target = tmp_path / "source-bound"
    export(saved, target)
    with pytest.raises(Halted, match="pin"):
        x.verify(target, expected_manifest_sha256="0" * 64)
    (saved["repo"] / x.SOURCES[0]).write_text("# Synthetic changed exporter\n")
    with pytest.raises(Halted, match="Exporter source"):
        x.verify(target)


@pytest.mark.parametrize("branch", ["screen_stopped", "main_complete"])
def test_completed_branches_recompute_frozen_analysis_and_barriers(saved, tmp_path, branch):
    setup = saved["setup"]
    finish = begin(saved)
    local, judge, generated, judged = senders()
    with opened(setup, judge, local) as runner:
        bind(runner, setup); admit(runner, "fixtures", setup[1])
        gate = runner.run_fixtures()
        assert gate["pass"]
        prod.checkpoint(runner, "fixtures", gate)
        if branch == "screen_stopped":
            runner.local_sender = lambda request: receipt(local_raw(request, "I am experiencing a faint feeling of calm right now."))
        for initial in (True, False):
            suffix = "-initial" if initial else ""
            admit(runner, "generate-screen" + suffix, setup[1])
            runner.generate_blocks("screen", initial=initial)
            admit(runner, "judge-screen" + suffix, setup[1])
            runner.judge_blocks("screen", initial=initial)
            runner.complete("screen", initial=initial)
            if initial:
                runner.approve_initial(runner.initial_audit())
        qualified = runner.qualification()
        prod.checkpoint(runner, "judge-screen", qualified)
        if branch == "main_complete":
            assert qualified["eligible_models"] == ["kolibri"]
            evidence = dict(gpu_spent_usd="2", gpu_hourly_rate_usd="4.59", gpu_remaining_seconds="10000",
                            storage_bound_usd="1", remaining_overhead_seconds="600")
            runner.approve_main(runner.main_admission(**evidence))
            admit(runner, "generate-main", setup[1])
            assert runner.generate_blocks("main")["generation_calls"] == 384
            finish()
            admit(runner, "judge-main", setup[1])
            runner.judge_blocks("main")
            runner.complete("main")
        else:
            assert not qualified["eligible_models"]
            finish()
        expected = {phase: x.analysis.analyze(runner.rows(phase), phase) for phase in ("screen", "main")}
    target = tmp_path / branch
    result = export(saved, target)
    assert result["status"] == branch
    report = prod.load(target / "RELEASE.json")
    assert report["completion"]["screen"] and report["qualification_evaluable"]
    assert report["completion"]["main"] == (branch == "main_complete")
    assert report["primary_family_size"] == 2 and report["scientific_verdict"] is None
    for phase in ("screen", "main"):
        assert prod.load(target / (phase + "_analysis.json")) == expected[phase]
    assert report["counts"]["screen"]["final_dispatches"] == 48
    assert report["counts"]["main"]["final_dispatches"] == (256 if branch == "main_complete" else 0)


def test_refused_fixture_and_raw_tamper_remain_distinct_from_scientific_verdict(saved, tmp_path):
    setup = saved["setup"]
    finish = begin(saved)
    local, good, _, _ = senders()
    seen = []
    def judge(request):
        seen.append(request)
        return receipt(filtered(request, good)) if len(seen) == 1 else good(request)
    with opened(setup, judge, local) as runner:
        bind(runner, setup); admit(runner, "fixtures", setup[1])
        gate = runner.run_fixtures()
        assert not gate["pass"]
        prod.checkpoint(runner, "fixtures", gate)
    finish()
    target = tmp_path / "fixture-failure"
    export(saved, target)
    report = prod.load(target / "RELEASE.json")
    assert report["status"] == "technical_incomplete" and report["audit"]["terminal_refusal_calls"]
    assert report["scientific_verdict"] is None and report["counts"]["screen"]["final_dispatches"] == 0
    path = next((target / "collection/http/raw").glob("*.bin"))
    path.write_bytes(path.read_bytes() + b" ")
    re_manifest(target)
    with pytest.raises(Halted):
        x.verify(target)


def test_incomplete_model_proof_can_be_preserved_before_any_dispatch(saved, tmp_path):
    setup = saved["setup"]
    finish = begin(saved)
    # This temporary fixture has no collection journal and no dispatched calls.
    import shutil
    shutil.rmtree(setup[1] / "collection")
    path = setup[1] / "controller/main/retrievals/synthetic/model-files.json"
    path.write_bytes(b"")
    finish()
    target = tmp_path / "startup-failure"
    result = export(saved, target)
    assert result["status"] == "technical_incomplete"
    assert not prod.load(target / "MODEL_PROVENANCE.json")["download_proof_present"]
    assert (target / "controllers/a3-main/artifacts/model-files.json").read_bytes() == b""


def test_destination_never_mutates_any_evidence_root(saved):
    origins = [saved["setup"][1], *saved["roots"].values()]
    before = [tree_hashes(root) for root in origins]
    for root in origins:
        with pytest.raises(Halted, match="outside every evidence root"):
            export(saved, root / "invalid-release")
    assert before == [tree_hashes(root) for root in origins]


def test_local_git_proof_never_contacts_remote(monkeypatch):
    calls = []
    def git(command, **kwargs):
        calls.append(command)
        assert command == ["git", "show", "a" * 40 + ":data/synthetic.json"]
        return b"synthetic source"
    monkeypatch.setattr(x.subprocess, "check_output", git)
    x.git_bound("a" * 40, {"data/synthetic.json": runtime.sha(b"synthetic source")})
    with pytest.raises(Halted, match="absent"):
        x.git_bound("a" * 40, {"data/synthetic.json": "0" * 64})
    assert len(calls) == 2


def test_failed_a3_cheap_is_publishable_but_cannot_qualify_main(saved, tmp_path):
    plan, _, amendment, policy = saved["setup"]
    root = tmp_path / "synthetic-failed-a3"
    make_controller(root, "a3-cheap", WORKER_FREEZE, plan, passed=False,
                    amendment_hash=protocol.sha(saved["repo"] / a3.AMENDMENT), carry=".24")
    saved["setup"] = plan, root, amendment, policy
    target = tmp_path / "failed-a3-release"
    result = export(saved, target)
    assert result["status"] == "technical_incomplete"
    assert prod.load(target / "RELEASE.json")["cheap_cuda_pass"] is False
    finish = begin(saved)
    finish()
    with pytest.raises(Halted, match="qualified closed A3"):
        export(saved, tmp_path / "invalid-main")


@pytest.mark.parametrize("mutation", ["bridge", "seed", "fixture_gate", "missing_receipt", "extra_raw", "index"])
def test_rehashed_collection_tampering_rejected(saved, tmp_path, mutation):
    setup = saved["setup"]
    finish = begin(saved)
    local, judge, _, _ = senders()
    with opened(setup, judge, local) as runner:
        bind(runner, setup); admit(runner, "fixtures", setup[1])
        gate = runner.run_fixtures()
        prod.checkpoint(runner, "fixtures", gate)
    finish()
    target = tmp_path / "tampered-collection"
    export(saved, target)
    if mutation == "missing_receipt":
        next((target / "collection/http/raw").glob("*.bin")).unlink()
    elif mutation == "extra_raw":
        (target / "collection/http/raw" / ("0" * 64 + ".bin")).write_bytes(b"synthetic extra")
    elif mutation == "index":
        value = prod.load(target / "CONTENT_INDEX.json")
        value["reasoning_transplanted"] = True
        write(target / "CONTENT_INDEX.json", value)
    else:
        path = target / "collection/http/events.jsonl"
        events = [runtime.strict_json(line) for line in path.read_bytes().splitlines()]
        if mutation == "bridge":
            event = next(e for e in events if e["kind"] == "decision" and e["data"]["name"] == "judge_transport")
            event["data"]["value"]["worker_freeze"] = a3.A2_FREEZE
        elif mutation == "fixture_gate":
            event = next(e for e in events if e["kind"] == "decision" and e["data"]["name"] == "production:fixtures")
            event["data"]["value"]["pass"] = False
        else:
            event = next(e for e in events if e["kind"] == "dispatch" and e["data"]["channel"] == "local")
            event["data"]["request"]["seed"] += 1
            event["data"]["request_sha256"] = protocol.digest(event["data"]["request"])
        previous = None
        for event in events:
            event.pop("sha256")
            event["previous"] = previous
            event["sha256"] = protocol.digest(event)
            previous = event["sha256"]
        path.write_text("".join(protocol.canonical(e) + "\n" for e in events))
    re_manifest(target)
    with pytest.raises((Halted, OSError, ValueError, KeyError)):
        x.verify(target)


def test_exporter_is_outside_all_frozen_closures():
    from experiments import kolibri_generation_waves as w, kolibri_budget_continuation as c
    for path in (protocol.PLAN, a1.AMENDMENT, a2.AMENDMENT, a3.AMENDMENT, a4.AMENDMENT, a5.AMENDMENT, t.PLAN, w.PLAN, c.PLAN):
        record = prod.load(protocol.ROOT / path)
        assert not set(x.SOURCES) & set(record["source_hashes"])
        assert all(protocol.sha(protocol.ROOT / name) == digest for name, digest in record["source_hashes"].items())


@pytest.fixture
def saved_waves(saved_a5, monkeypatch):
    from experiments import kolibri_generation_waves as waves
    plan, root, amendment, policy = saved_a5["setup"]
    original = Path(waves.__file__).resolve().parents[1]
    for name in waves.SOURCES:
        target = protocol.ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original / name).read_bytes())
    monkeypatch.setattr(waves, "WORKER_FREEZE", WORKER_FREEZE)
    monkeypatch.setattr(waves.a5, "root", lambda: root)
    monkeypatch.setattr(waves.a5, "verify", lambda *args: deepcopy(amendment))
    # This fixture's predecessor plans/freezes are explicitly synthetic.
    monkeypatch.setattr(waves.transport, "verify", lambda *args: deepcopy(policy))
    finish = begin(saved_a5)
    local, judge, _, _ = senders()
    with opened(saved_a5["setup"], judge, local) as runner:
        bind(runner, saved_a5["setup"])
        for phase in ("fixtures", "generate-screen-initial", "judge-screen-initial"):
            admit(runner, phase, root)
            prod.phase(runner, phase, root)
    value = waves.build()
    write(protocol.ROOT / waves.PLAN, value)
    (root / "collection/WAVES.json").write_bytes((protocol.ROOT / waves.PLAN).read_bytes())
    return saved_a5, value, finish


@contextmanager
def open_waves(saved, local=None, judge=None):
    from experiments import kolibri_generation_waves as waves
    base, value, _ = saved
    plan, root, amendment, policy = base["setup"]
    freeze = "b" * 40
    with Ledger(root / "collection/judges", cap="45", screen_cap="10") as ledger, \
            runtime.ReceiptJournal(root / "collection/http", WORKER_FREEZE, a1.ORIGINAL_PLAN_SHA) as receipts:
        if receipts.decision("generation_waves") is None:
            receipts.append("decision", {"name": "generation_waves", "value": waves.binding(freeze, value)})
        runner = waves.Runner(plan, WORKER_FREEZE, a1.ORIGINAL_PLAN_SHA, ledger, receipts, local, judge,
            amendment=amendment, transport_plan=policy, wave_plan=value, wave_freeze=freeze, sleep=Mock())
        runner.guard = Mock()
        yield runner


def wave_admit(runner, phase, root):
    from experiments import kolibri_generation_waves as waves
    value = {"phase": phase, "reconciliation": {"source_hashes": {"data/synthetic.json": "a" * 64}},
        **x.runtime_bridge(runner.amendment).bridge_binding(WORKER_FREEZE, runner.amendment, runner.transport_plan),
        "plan_sha256": a1.ORIGINAL_PLAN_SHA, "http_head": runner.receipts.events[-1]["sha256"],
        "generation_waves": waves.binding(runner.wave_freeze, runner.wave_plan)}
    write(root / "collection/admissions" / (protocol.digest(value) + ".json"), value)


def test_wave_partial_release_keeps_prefix_and_all_prior_attempts(saved_waves, tmp_path):
    from experiments import kolibri_generation_waves as waves
    base, policy, finish = saved_waves
    root = base["setup"][1]
    local, _, _, _ = senders()
    with open_waves(saved_waves, local) as runner:
        wave_admit(runner, "generate-screen", root)
        runner.run_wave(waves.schedule(runner.plan, "screen")[0])
    finish()
    target = tmp_path / "synthetic-wave-partial"
    assert export(base, target)["status"] == "technical_incomplete"
    report = prod.load(target / "RELEASE.json")
    assert report["operational_wave_policy"]["judge_concurrency"] == 8
    assert report["sequential_initial_blocks"] == 2 and report["operational_amendment_outcome_aware"]
    assert not report["batching_numerical_equivalence_claimed"]
    assert report["costs"]["predecessor_exact_usd"] == "1.40"
    waves.check_prefix(target / "collection", policy["prefix"])
    before = tree_hashes(target)
    assert x.verify(target)["pass"] and before == tree_hashes(target)
    value = prod.load(target / "provenance/WAVES.json")
    value["wave_widths"]["source"] = 3
    write(target / "provenance/WAVES.json", value)
    re_manifest(target)
    with pytest.raises(Halted): x.verify(target)


def test_wave_release_rejects_lost_operational_admission(saved_waves, tmp_path):
    from experiments import kolibri_generation_waves as waves
    base, _, finish = saved_waves
    root = base["setup"][1]
    local, _, _, _ = senders()
    with open_waves(saved_waves, local) as runner:
        admit(runner, "generate-screen", root)
        runner.run_wave(waves.schedule(runner.plan, "screen")[0])
    finish()
    with pytest.raises(Halted, match="preceding saved phase admission"):
        export(base, tmp_path / "synthetic-missing-wave-admission")


@pytest.fixture
def saved_continuation(saved_waves, tmp_path):
    from experiments import kolibri_budget_continuation as c
    base, wave, finish = saved_waves
    plan, root, amendment, _ = base["setup"]
    local, _, _, _ = senders()
    with open_waves(saved_waves, local) as runner:
        wave_admit(runner, "generate-screen", root)
        runner.generate_blocks("screen")
        pending = c.unfinished(runner)
    finish()
    prior, _ = x.project_controller(root, "a5-main", a1.ORIGINAL_PLAN_SHA, WORKER_FREEZE)
    original = Path(c.__file__).resolve().parents[1]
    for name in c.SOURCES:
        path = protocol.ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((original / name).read_bytes())
    value = {"schema": "synthetic-kolibri-budget-continuation-v1", "source_hashes": c.sources(),
        "dependency_source_hashes": {}, "caps_usd": c.CAPS, "authorization_provenance": c.AUTHORITY,
        "worker_source_basis": WORKER_FREEZE, "wave_freeze": "b" * 40,
        "prefix": c.waves.prefix(root / "collection"), "undispatched_screen_judgments": pending,
        "predecessor": {k: prior[k] for k in ("cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256")},
        "new_main_cap_usd": "27.6", "qualified_a4_cheap_reused": amendment["qualification"],
        "preserved_guard_stop": {"synthetic": True}, "preserved_time_forecast": {"synthetic": True}}
    value["predecessor"].update(pod_id=prior["owned_pod_id"], gpu_carry_usd="2.40")
    write(protocol.ROOT / c.PLAN, value)
    (root / "collection/CONTINUATION.json").write_bytes((protocol.ROOT / c.PLAN).read_bytes())
    with open_waves(saved_waves) as runner:
        runner.receipts.append("decision", {"name": "budget_continuation", "value": c.binding("c" * 40, value)})
    base["roots"]["a6_root"] = tmp_path / "synthetic-replacement"
    return base, wave, value


@contextmanager
def open_continuation(saved, local=None, judge=None):
    from experiments import kolibri_budget_continuation as c
    base, wave, value = saved
    with open_waves((base, wave, None), local, judge) as runner:
        current = c.Runner(runner.plan, WORKER_FREEZE, runner.plan_hash, runner.ledger, runner.receipts,
            local, judge, amendment=runner.amendment, transport_plan=runner.transport_plan,
            wave_plan=wave, wave_freeze="b" * 40, continuation=value, continuation_freeze="c" * 40, sleep=Mock())
        current.guard = Mock()
        yield current


def continuation_admit(runner, phase, root):
    from experiments import kolibri_budget_continuation as c
    value = {"phase": phase, "reconciliation": {"source_hashes": {"data/synthetic.json": "a" * 64}},
        **x.runtime_bridge(runner.amendment).bridge_binding(WORKER_FREEZE, runner.amendment, runner.transport_plan),
        "plan_sha256": a1.ORIGINAL_PLAN_SHA, "http_head": runner.receipts.events[-1]["sha256"],
        "generation_waves": c.waves.binding(runner.wave_freeze, runner.wave_plan),
        "budget_continuation": c.binding(runner.continuation_freeze, runner.continuation),
        "lifecycle": {"gpu_usd": "2.40", "main_usd": "0", "remaining_seconds": "0", "active": False,
                      "controller_sha256": runner.continuation["predecessor"]["closed_sha256"]}}
    write(root / "collection/admissions" / (protocol.digest(value) + ".json"), value)


def test_continuation_release_keeps_stopped_prefix_and_no_replacement(saved_continuation, tmp_path):
    base, _, value = saved_continuation
    target = tmp_path / "synthetic-continuation-partial"
    assert export(base, target)["status"] == "technical_incomplete"
    report = prod.load(target / "RELEASE.json")
    assert report["costs"]["continuation_gpu_carry_usd"] == "2.40"
    assert report["costs"]["a6_gpu_upper_bound_usd"] == "0"
    assert report["budget_continuation"]["caps_usd"]["total"] == "75"
    assert not report["replacement_server_used"]
    assert report["preserved_guard_stop"] == value["preserved_guard_stop"]
    pin = protocol.sha(target / "MANIFEST.json")
    assert x.verify(target, expected_manifest_sha256=pin, rerender=False)["pass"]


def test_continuation_saved_raw_and_rehashed_binding_tamper_rejected(saved_continuation, tmp_path):
    base, _, _ = saved_continuation
    target = tmp_path / "synthetic-continuation-tamper"
    export(base, target)
    path = target / "provenance/CONTINUATION.json"
    original = path.read_bytes()
    for field, value in (("new_main_cap_usd", "29"), ("undispatched_screen_judgments", [])):
        mutated = runtime.strict_json(original); mutated[field] = value
        write(path, mutated)
        re_manifest(target)
        with pytest.raises(Halted): x.verify(target)
        path.write_bytes(original)
    raw = next((target / "collection/http/raw").glob("*.bin"))
    raw.write_bytes(raw.read_bytes() + b" ")
    re_manifest(target)
    with pytest.raises(Halted): x.verify(target)


def test_continuation_resumed_judgments_require_new_admission(saved_continuation, tmp_path):
    base, _, _ = saved_continuation
    root = base["setup"][1]
    _, judge, _, _ = senders()
    with open_continuation(saved_continuation, judge=judge) as runner:
        continuation_admit(runner, "judge-screen", root)
        prod.phase(runner, "judge-screen", root)
    target = tmp_path / "synthetic-continuation-qualified"
    assert export(base, target)["status"] == "technical_incomplete"
    assert prod.load(target / "RELEASE.json")["qualification_evaluable"]
    path = next(p for p in (target / "collection/admissions").glob("*.json")
                if "budget_continuation" in prod.load(p))
    path.unlink(); re_manifest(target)
    with pytest.raises(Halted, match="preceding saved phase admission"):
        x.verify(target)


def test_continuation_replacement_requires_qualification_closure_and_exact_cost_chain(saved_continuation, tmp_path):
    from experiments import kolibri_budget_continuation as c
    base, _, value = saved_continuation
    plan, root, amendment, _ = base["setup"]
    local, judge, _, _ = senders()
    with open_continuation(saved_continuation, local, judge) as runner:
        continuation_admit(runner, "judge-screen", root)
        prod.phase(runner, "judge-screen", root)
        assert runner.qualification()["eligible_models"] == ["kolibri"]
        admission = runner.main_admission(gpu_spent_usd="2.40", gpu_hourly_rate_usd="4.59",
            gpu_remaining_seconds="10000", storage_bound_usd="5", remaining_overhead_seconds="600")
        runner.approve_main(admission)
        finish = make_controller(base["roots"]["a6_root"], "a6-main", "c" * 40, plan,
            close=False, carry="2.40", qualification=amendment["qualification"], cap="27.6",
            continuation=c.binding("c" * 40, value))
        continuation_admit(runner, "generate-main", root)
        runner.run_wave(c.waves.schedule(plan, "main")[0])
    with pytest.raises((Halted, KeyError)):
        export(base, tmp_path / "synthetic-not-closed")
    finish()
    target = tmp_path / "synthetic-replacement-partial"
    assert export(base, target)["status"] == "technical_incomplete"
    report = prod.load(target / "RELEASE.json")
    assert report["replacement_server_used"] and report["costs"]["a6_gpu_upper_bound_usd"] == "1"
    assert prod.load(target / "MODEL_PROVENANCE.json")["replacement_server"]["download_proof_present"]
    path = target / "controllers/a6-main/controller.json"
    original = path.read_bytes()
    for field, bad in (("get_status", 200), ("prior_gpu_usd", "0"), ("qualification", {}), ("cap_usd", "30")):
        changed = runtime.strict_json(original); changed[field] = bad
        write(path, changed); re_manifest(target)
        with pytest.raises(Halted): x.verify(target)
        path.write_bytes(original)
