from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

from experiments.kolibri_swap import protocol as p
from experiments.openrouter_swap import protocol as common


def items(phase):
    return [s for b in p.inventory(phase) for s in b["sources"] + b["finals"]]


def test_inventory_is_fresh_complete_and_deterministic():
    all_items = []
    for phase, blocks, sources, finals in (("screen", 12, 24, 48), ("main", 32, 128, 256)):
        panel = p.inventory(phase)
        assert panel == p.inventory(phase)
        assert len(panel) == blocks
        assert sum(len(b["sources"]) for b in panel) == sources
        assert sum(len(b["finals"]) for b in panel) == finals
        assert {b["model"] for b in panel} == {"kolibri"}
        assert sum(b["family"] == "a" for b in panel) == blocks // 2
        assert sum(b["family"] == "b" for b in panel) == blocks // 2
        for b in panel:
            source_map = {s["id"]: s for s in b["sources"]}
            for f in b["finals"]:
                donor = source_map[f["source_id"]]
                instruction, transcript, kind = common.CELLS[f["cell"]]
                assert (f["instruction"], f["transcript"]) == (instruction, transcript)
                assert donor["transcript"] == transcript
                assert donor["donor"] == kind
                assert (donor["block"], donor["family"]) == (f["block"], f["family"])
        all_items.extend(items(phase))
    assert len({s["id"] for s in all_items}) == 456
    assert len({s["seed"] for s in all_items}) == 456
    assert all(s["id"].startswith(p.NAMESPACE + "-") for s in all_items)
    assert all(type(s["seed"]) is int and 0 <= s["seed"] < 2**31 for s in all_items)
    with pytest.raises(ValueError):
        p.inventory("other")


def test_messages_are_exact_common_english_prompts_and_shams_are_independent():
    for spec in items("main"):
        source = None if spec["kind"] == "source" else "Synthetic final-only donor."
        assert p.messages(spec, source) == common.messages(spec, source)
        if spec["kind"] == "final":
            assert p.messages(spec, source)[1] == {"role": "assistant", "content": source}
    for block in p.inventory("main"):
        for condition in ("self", "history"):
            donors = [s for s in block["sources"] if s["transcript"] == condition]
            assert len(donors) == 2
            assert p.messages(donors[0]) == p.messages(donors[1])
            assert donors[0]["seed"] != donors[1]["seed"]


def test_fixed_science_judges_and_budget():
    plan = p.build({})
    assert plan["launch_authorized"] is False
    assert plan["status"] == "blocked_missing_metadata"
    assert plan["metadata_blockers"]
    assert list(plan["models"]) == ["kolibri"]
    assert p.MODEL["reasoning_effort"] == "medium"
    assert (p.MODEL["temperature"], p.MODEL["top_p"], p.MODEL["top_k"], p.MODEL["max_tokens"]) == (.5, 1, -1, 4096)
    assert p.JUDGES["astra"]["provider_slug"] == "azure/us"
    assert p.JUDGES["opus"]["provider_slug"] == "google-vertex/us"
    assert plan["analysis"]["primary_family_size"] == 2
    assert plan["analysis"]["primary_coefficients"] == {
        "instruction_minus_transcript": {"SH": 1, "HS": -1}, "neutral_transcript": {"NS": 1, "NH": -1}}
    assert plan["qualification"]["effect_sign_is_gate"] is False
    assert plan["qualification"]["both_judges_required"] is True
    b = plan["budget"]
    assert sum(Decimal(b[k]) for k in ("gpu_usd", "judges_usd", "storage_recovery_usd")) == Decimal("75")
    assert Decimal(b["gpu_smoke_usd"]) + Decimal(b["gpu_main_usd"]) == Decimal("25")
    assert b["combined_screen_stoploss_usd"] == "20"
    assert b["openrouter_account_cap_usd"] == "330"
    assert b["openrouter_external_commitments_usd"] == "130"
    assert (Decimal(b["openrouter_reserved_prior_usd"]) + Decimal(b["judges_usd"])
            + Decimal(b["openrouter_external_commitments_usd"])) == Decimal("311")
    assert Decimal(b["runpod_reserved_prior_usd"]) + Decimal(b["gpu_usd"]) <= 200
    external = plan["external_authorizations"]
    assert len(external) == 1
    assert external[0]["new_budget_usd"] == "130"
    assert external[0]["separate_from_kolibri_allowance"] is True
    assert external[0]["changes_kolibri_science"] is False


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "ROOT", tmp_path)
    (tmp_path / "code.py").write_text("# synthetic test source\n")
    (tmp_path / "accounting.json").write_text('{"synthetic": true}\n')
    monkeypatch.setattr(p, "source_paths", lambda: ["code.py"])
    snapshots = {}
    for spec in p.JUDGES.values():
        snapshots[spec["id"]] = {
            "url": "https://openrouter.ai/api/v1/models/" + spec["id"] + "/endpoints",
            "endpoint": {"tag": spec["provider_slug"], "pricing": {
                "prompt": str(Decimal(spec["input_price"]) / 1_000_000),
                "completion": str(Decimal(spec["output_price"]) / 1_000_000)}}}
    metadata = {
        **p.PINS, "approved": True,
        "gpu_hourly_usd": "4.59", "storage_hourly_usd": "0.01", "endpoint_snapshots": snapshots,
        "model_artifacts": {
            "files": {name: {"sha256": "c" * 64, "size": 100}
                      for name in ("config.json", "model.safetensors.index.json", "tokenizer.json",
                                   "tokenizer_config.json", "model-00001-of-00001.safetensors")},
            "weight_map": {"synthetic.weight": "model-00001-of-00001.safetensors"}},
        "spend_reconciliation": {"as_of": "2026-10-04T00:00:00Z",
                                 "openrouter_prior_and_reserved_usd": "136",
                                 "runpod_prior_and_reserved_usd": "50",
                                 "source_hashes": {"accounting.json": p.sha(tmp_path / "accounting.json")}},
    }
    return tmp_path, metadata


def write_plan(root, metadata):
    path = root / "PLAN.json"
    path.write_text(json.dumps(p.build(metadata), indent=2) + "\n")
    return path


def test_offline_build_verification_and_reconciliation_are_source_bound(isolated, monkeypatch):
    root, metadata = isolated
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline plan build made a process/network request")
    monkeypatch.setattr(p.subprocess, "check_output", forbidden)
    plan = p.build(metadata)
    assert plan["metadata_blockers"] == []
    assert plan["status"] == "ready_for_source_freeze"
    assert plan["launch_authorized"] is True
    assert plan["requires_pushed_freeze"] is True
    assert plan["owner_approval"]["approved"] is True
    assert plan["source_hashes"]["accounting.json"] == p.sha(root / "accounting.json")
    path = write_plan(root, metadata)
    assert p.verify(path) == plan
    (root / "accounting.json").write_text("changed synthetic record\n")
    with pytest.raises(ValueError, match="differs"):
        p.verify(path)


@pytest.mark.parametrize("key,value", [
    ("hf_revision", "main"), ("plugin_revision", "1.0.0"), ("vllm_version", "0.28.0"),
    ("plugin_wheel_sha256", "0" * 64), ("image_digest", "image:latest"),
    ("gpu_hourly_usd", "NaN"), ("gpu_hourly_usd", "0"), ("storage_hourly_usd", "-1"),
])
def test_bad_pins_and_prices_block_executable_freeze(isolated, key, value):
    root, metadata = isolated
    metadata[key] = value
    assert key in p.build(metadata)["metadata_blockers"]
    with pytest.raises(ValueError, match="Unresolved"):
        p.verify(write_plan(root, metadata), "a" * 40)


def test_endpoint_fallback_or_price_drift_and_unfunded_prior_are_blockers(isolated):
    _, metadata = isolated
    altered = deepcopy(metadata)
    altered["endpoint_snapshots"][p.JUDGES["astra"]["id"]]["endpoint"]["tag"] = "openai"
    assert "endpoint_snapshot:astra" in p.metadata_blockers(altered)
    altered = deepcopy(metadata)
    altered["endpoint_snapshots"][p.JUDGES["opus"]["id"]]["endpoint"]["pricing"]["completion"] = "0.001"
    assert "endpoint_snapshot:opus" in p.metadata_blockers(altered)
    for account, amount in (("openrouter", "155.01"), ("runpod", "175.01")):
        altered = deepcopy(metadata)
        altered["spend_reconciliation"][account + "_prior_and_reserved_usd"] = amount
        assert "spend_reconciliation" in p.metadata_blockers(altered)


def test_external_study_is_reserved_without_raising_kolibri_or_runpod_cap(isolated):
    _, metadata = isolated
    assert "spend_reconciliation" not in p.metadata_blockers(metadata)
    for account, exact_limit in (("openrouter", "155"), ("runpod", "175")):
        altered = deepcopy(metadata)
        altered["spend_reconciliation"][account + "_prior_and_reserved_usd"] = exact_limit
        assert "spend_reconciliation" not in p.metadata_blockers(altered)
        altered["spend_reconciliation"][account + "_prior_and_reserved_usd"] = str(Decimal(exact_limit) + Decimal("0.01"))
        assert "spend_reconciliation" in p.metadata_blockers(altered)
    # The larger owner account scope must not erase the external commitment.
    altered = deepcopy(metadata)
    altered["spend_reconciliation"]["openrouter_prior_and_reserved_usd"] = "200"
    assert "spend_reconciliation" in p.metadata_blockers(altered)
    plan = p.build(metadata)
    assert plan["owner_approval"]["new_budget_usd"] == "75"
    assert plan["budget"]["judges_usd"] == "45"
    assert plan["budget"]["gpu_usd"] == "25"


def test_approval_and_model_shard_manifest_are_required(isolated):
    _, metadata = isolated
    altered = deepcopy(metadata)
    altered.pop("approved")
    assert "owner_approval" in p.metadata_blockers(altered)
    assert not p.build(altered)["launch_authorized"]
    for edit in (lambda x: x["files"].pop("model-00001-of-00001.safetensors"),
                 lambda x: x["files"]["config.json"].update(sha256="not-a-hash"),
                 lambda x: x["files"]["config.json"].update(size=True),
                 lambda x: x.update(weight_map={}),
                 lambda x: x["files"].update({"../private": {"sha256": "f" * 64, "size": 12}})):
        altered = deepcopy(metadata)
        edit(altered["model_artifacts"])
        assert "model_artifacts" in p.metadata_blockers(altered)


def test_source_closure_binds_runtime_lock_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "ROOT", tmp_path)
    required = ["experiments/openrouter_swap/protocol.py", "experiments/openrouter_swap/analysis.py",
                "experiments/openrouter_swap/judges.py", "src/prompts.py",
                "experiments/bilingual_llama_pilot/prompts.py",
                "experiments/instruction_state_qualification/rubric.md",
                "experiments/automated_rubric_audit/rubric.md", "requirements-ci.txt"]
    additions = ["experiments/kolibri_swap/requirements-gpu.in",
                 "experiments/kolibri_swap/requirements-gpu.lock",
                 "experiments/kolibri_swap/bootstrap.sh", "experiments/kolibri_swap/runtime.py",
                 "experiments/kolibri_swap/controller.py", "experiments/kolibri_swap/budget_basis.json"]
    for name in required + additions:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic fixture\n")
    assert set(additions) <= set(p.source_paths())


def test_changed_inventory_settings_or_source_cannot_verify(isolated):
    root, metadata = isolated
    for change in (lambda x: x["screen"][0]["finals"][0].update(seed=1),
                   lambda x: x["models"]["kolibri"].update(temperature=1),
                   lambda x: x["analysis"].update(primary_family_size=1),
                   lambda x: x["budget"].update(new_total_usd="100")):
        path = write_plan(root, metadata)
        plan = json.loads(path.read_text())
        change(plan)
        path.write_text(json.dumps(plan))
        with pytest.raises(ValueError, match="differs"):
            p.verify(path)
    path = write_plan(root, metadata)
    (root / "code.py").write_text("# changed source\n")
    with pytest.raises(ValueError, match="differs"):
        p.verify(path)


def test_freeze_requires_exact_committed_bytes_and_pushed_branch(isolated, monkeypatch):
    root, metadata = isolated
    path = write_plan(root, metadata)
    freeze = "a" * 40
    calls = []
    def git_output(command, **kwargs):
        calls.append(command)
        if command[:2] == ["git", "show"]:
            revision, name = command[2].split(":", 1)
            assert revision == freeze
            return (root / name).read_bytes()
        assert command == ["git", "ls-remote", "origin", "refs/heads/" + p.BRANCH]
        return "b" * 40 + "\trefs/heads/" + p.BRANCH + "\n"
    monkeypatch.setattr(p.subprocess, "check_output", git_output)
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    assert p.verify(path, freeze)["metadata_blockers"] == []
    assert ["git", "show", freeze + ":accounting.json"] in calls
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match="pushed"):
        p.verify(path, freeze)
    def changed_commit(command, **kwargs):
        if command[:2] == ["git", "show"] and command[2].endswith(":code.py"):
            return b"tampered"
        return git_output(command, **kwargs)
    monkeypatch.setattr(p.subprocess, "check_output", changed_commit)
    with pytest.raises(ValueError, match="absent from freeze"):
        p.verify(path, freeze)


def test_actual_source_closure_includes_rubrics_without_unrelated_release_records():
    paths = p.source_paths()
    required = {"experiments/kolibri_swap/protocol.py", "experiments/kolibri_swap/analysis.py",
                "experiments/kolibri_swap/README.md", "experiments/openrouter_swap/analysis.py",
                "experiments/openrouter_swap/judges.py", "experiments/openrouter_swap/providers.py",
                "experiments/instruction_state_qualification/rubric.md",
                "experiments/automated_rubric_audit/rubric.md",
                "tests/test_kolibri_swap_protocol.py", "tests/test_kolibri_swap_analysis.py"}
    assert required <= set(paths)
    assert not any(name.startswith("data/") for name in paths)
    assert all((p.ROOT / name).is_file() for name in paths)
